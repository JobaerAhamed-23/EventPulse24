"""The Pulse Preview endpoints: `GET /api/public/preview` and `.../preview/cities` (FR-2).

The acceptance criteria this file covers, one at a time: the geo hit, the geo miss
falling back to NYC, an explicit override, an unsupported city returning empty, the
opt-out skipping geo, identical responses with and without a session, the per-IP limit,
and fewer than 3 events.

**The opt-out test plants a geo port that raises if it is called.** "The geo port is not
consulted" is a stronger claim than "it is consulted and the answer ignored", and only
the stronger claim can be checked. A test that merely asserted the *result* would pass
against an implementation that called the port and threw the answer away — which is
exactly the implementation the work item is worried about.

**The session test compares bytes.** `response.content`, not `response.json()` — two
different bodies can compare equal as JSON and differ in bytes, and the byte comparison
is the one that catches a whitespace or key-order difference that a cache would treat as
two responses.
"""

from datetime import timedelta

import pytest
from django.db.models import F
from django.test import Client
from django.utils import timezone

from apps.ingestion.event_fit.writes import write_event_fit
from apps.ingestion.models import Event, EventFit
from shared.actor import Actor
from shared.constants import GEO_CITY_MAX_LENGTH, PREVIEW_FALLBACK_CITY
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, SourceFactory, VenueFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

ACTOR = Actor.system("preview_test")
HOUR = timedelta(hours=1)
# Far enough ahead that a test's events are always "upcoming" for the endpoint, which
# bounds the preview by the real now.
BASE = timezone.now() + timedelta(days=30)

# A city no other test uses, so the supported-cities assertions can be exact.
SOLO_CITY = "Zzyzx-preview-city"


@pytest.fixture
def throttle_adapter(monkeypatch):
    """One in-memory throttle adapter, shared by every request in the test.

    `ports.registry.get_adapter` builds a **fresh** adapter on every call, so the
    in-memory fake's counters would not survive from one request to the next — and the
    limit would never be reached. The adapter therefore has to be a singleton for the
    duration of the test, which is what the identity tests do for the same reason.

    The clock is injected, so the window boundary can be pinned exactly rather than
    waited for.
    """
    from adapters.throttle.memory import InMemoryThrottleAdapter

    clock = {"now": 1_000_000.0}
    adapter = InMemoryThrottleAdapter(now=lambda: clock["now"])
    monkeypatch.setattr("apps.catalog.preview_api.get_throttle_port", lambda: adapter)
    adapter.test_clock = clock  # type: ignore[attr-defined]
    return adapter


def make_event(city: str, *, source=None, score: int = 4):
    """A published event in `city`, with an Event Fit written for it."""
    venue = VenueFactory(city=city, venue_fingerprint=f"venue-{city}|{city}")
    overrides = {
        "venue": venue,
        "start_time_utc": BASE,
        "start_time_tz": "America/New_York",
    }
    if source is not None:
        overrides["source"] = source
    event = EventFactory(**overrides)
    row = write_event_fit(event=event, now=timezone.now(), actor=ACTOR)
    if row is not None:
        EventFit.objects.using(CATALOG).filter(pk=row.pk).update(score=score)
    return event


def get_preview(**params):
    return Client().get("/api/public/preview", params)


def get_cities():
    return Client().get("/api/public/preview/cities")


# ── The geo hit ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("fake_city", [SOLO_CITY])
def test_the_geo_city_is_used_when_there_is_no_city_parameter(settings, fake_city):
    """FR-2: "Geo-IP is the default city." The fake adapter is the geo port here."""
    make_event(fake_city)
    settings.GEO_FAKE_CITY = fake_city

    body = get_preview().json()

    assert body["city"] == fake_city
    assert body["city_source"] == "geo"
    assert len(body["items"]) == 1


# ── The geo miss, falling back to NYC ──────────────────────────────────────────────


def test_a_geo_miss_falls_back_to_the_fallback_city(settings):
    """No location at all → the named fallback city."""
    settings.GEO_FAKE_CITY = None
    make_event(PREVIEW_FALLBACK_CITY)

    body = get_preview().json()

    assert body["city"] == PREVIEW_FALLBACK_CITY
    assert body["city_source"] == "fallback"


def test_a_geo_city_outside_the_supported_set_falls_back(settings):
    """The edge guessed, and the guess is a city the catalog does not cover.

    The visitor did not choose it, so the fallback is right: an empty preview because
    the edge guessed wrong would be a page that says "nothing near Nowhere".
    """
    settings.GEO_FAKE_CITY = "Nowhere-in-particular"
    make_event(PREVIEW_FALLBACK_CITY)

    body = get_preview().json()

    assert body["city"] == PREVIEW_FALLBACK_CITY
    assert body["city_source"] == "fallback"
    assert len(body["items"]) == 1


# ── An explicit override ───────────────────────────────────────────────────────────


def test_an_explicit_city_overrides_geo(settings):
    """FR-2: "one-tap change to override" — the "Change" action."""
    settings.GEO_FAKE_CITY = "Nowhere-in-particular"
    make_event(SOLO_CITY)

    body = get_preview(city=SOLO_CITY).json()

    assert body["city"] == SOLO_CITY
    assert body["city_source"] == "query"
    assert len(body["items"]) == 1


def test_an_explicit_city_is_matched_case_insensitively():
    """A person types "brooklyn", not "Brooklyn". They are the same city."""
    make_event("Brooklyn")

    body = get_preview(city="brooklyn").json()

    assert body["city_source"] == "query"
    assert len(body["items"]) == 1


def test_the_catalogs_own_spelling_of_a_city_is_the_one_returned():
    """The heading the visitor sees is the spelling the events are filed under.

    The city came from a header, so it is the *edge's* spelling. The events are
    filed under the catalog's. A preview headed "brooklyn" listing the events filed
    under "Brooklyn" is a heading nobody can search for.
    """
    make_event("Brooklyn")

    body = get_preview(city="  BROOKLYN  ").json()

    assert body["city"] == "Brooklyn"


def test_a_city_the_catalog_does_not_hold_is_returned_as_it_was_given():
    """The defensive branch of the canonicalisation, and its rule.

    The catalog's spelling is used when there is one. When there is not — a city the
    catalog does not cover, or a spelling it does not hold — the name the caller gave
    is returned, trimmed. A caller must never be handed a *different* city's name.
    """
    from apps.catalog.preview_api import _canonical
    from apps.ingestion.services.preview_read import PreviewCities

    supported = PreviewCities(cities=("Brooklyn",))

    assert _canonical(supported, "  brooklyn ") == "Brooklyn"
    assert _canonical(supported, "  Nowhere  ") == "Nowhere"


def test_an_over_long_city_is_not_a_city(settings):
    """The explicit city is caller-supplied too, so it is bounded like the header.

    The geo header is length-bounded in the adapter, for exactly the same reason: a
    city name is short, and a value that is not short is not a city. A `?city=` value
    is written by the caller just as much as a header is, so it gets the *same*
    bound.

    An over-long city is treated as no city at all: the request falls through to geo
    and then to the fallback, rather than echoing the caller's megabytes back in the
    response.
    """
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)

    body = get_preview(city="B" * (GEO_CITY_MAX_LENGTH + 1)).json()

    assert body["city"] == SOLO_CITY
    assert body["city_source"] == "geo"


def test_a_city_at_the_bound_is_accepted(settings):
    """The bound is a bound and not a truncation: a city at the limit is still a city."""
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)

    at_bound = "B" * GEO_CITY_MAX_LENGTH

    body = get_preview(city=at_bound).json()

    assert body["city"] == at_bound
    assert body["city_source"] == "query"


# ── An unsupported explicit city returns empty ──────────────────────────────────────


def test_an_unsupported_explicit_city_returns_an_empty_preview_with_its_own_name():
    """The work item's rule, and the honest one.

    It never returns another city's events under that name — the frontend shows "No
    preview available in {city} yet.", and it needs the requested city's name to say it.
    """
    make_event(SOLO_CITY)

    body = get_preview(city="Queens").json()

    assert body["city"] == "Queens"
    assert body["city_source"] == "query"
    assert body["items"] == []


def test_an_unsupported_explicit_city_does_not_show_the_fallback_s_events():
    """The failure this rule exists to prevent.

    If the fallback's cards appeared under "Queens", the heading would be a lie — and a
    visitor would tap "Save" on an event that is not near them.
    """
    make_event(PREVIEW_FALLBACK_CITY)

    body = get_preview(city="Queens").json()

    assert body["items"] == []


# ── The opt-out ────────────────────────────────────────────────────────────────────


def test_the_opt_out_does_not_consult_the_geo_port(monkeypatch):
    """FR-2: "Don't use my location" suppresses geo-IP.

    The geo port is **not called**. The planted port raises if it is, so this test fails
    against an implementation that calls it and ignores the answer — which is the
    implementation the work item is worried about.
    """
    make_event(PREVIEW_FALLBACK_CITY)

    def exploding_port():
        raise AssertionError("the geo port must not be consulted when the visitor opted out")

    monkeypatch.setattr("apps.catalog.preview_api.get_geo_port", exploding_port)

    response = get_preview(use_geo="false")
    body = response.json()

    assert response.status_code == 200
    assert body["city"] == PREVIEW_FALLBACK_CITY
    assert body["city_source"] == "fallback"


def test_the_opt_out_ignores_a_geo_city_that_would_otherwise_win(settings):
    """The end-to-end version: even a good geo city loses to the opt-out."""
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)
    make_event(PREVIEW_FALLBACK_CITY)

    body = get_preview(use_geo="false").json()

    assert body["city"] == PREVIEW_FALLBACK_CITY
    assert body["city_source"] == "fallback"


# ── No session ─────────────────────────────────────────────────────────────────────


def test_the_response_is_identical_signed_in_and_unsigned(settings):
    """AD-12: the public surface does not depend on a session.

    The bodies are compared **byte for byte**. `response.json()` would compare them as
    data and miss a difference in whitespace or key order — and a cache treats two
    different byte strings as two different responses.
    """
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)

    anonymous = get_preview()
    signed_in = _signed_in_client().get("/api/public/preview")

    assert signed_in.status_code == anonymous.status_code == 200
    assert signed_in.content == anonymous.content


def test_the_cities_response_is_identical_signed_in_and_unsigned():
    make_event(SOLO_CITY)

    anonymous = get_cities()
    signed_in = _signed_in_client().get("/api/public/preview/cities")

    assert signed_in.status_code == anonymous.status_code == 200
    assert signed_in.content == anonymous.content


def test_the_preview_sets_no_session_cookie():
    """A response that sets a cookie is a response that depends on something."""
    make_event(SOLO_CITY)

    response = get_preview()

    assert "sessionid" not in response.cookies
    assert "Set-Cookie" not in response.headers


def _signed_in_client() -> Client:
    """A client with a signed-in session.

    The session is Django's own, set directly — the preview never reads it, and this is
    only here to prove that having one changes nothing.
    """
    from apps.identity.models import User

    user = User.objects.create_user(email="preview-user@example.test", password="pw")
    client = Client()
    client.force_login(user)
    return client


# ── Cacheable ──────────────────────────────────────────────────────────────────────


def test_the_response_is_cacheable_as_a_public_document():
    make_event(SOLO_CITY)

    response = get_preview()

    assert "public" in response.headers["Cache-Control"]
    assert "max-age" in response.headers["Cache-Control"]


def test_the_response_does_not_vary_on_the_cookie():
    """A response that varies on the cookie is not cacheable.

    Worse: a shared cache that stores one variant under a key that ignores the cookie
    would serve one visitor's response to another.
    """
    make_event(SOLO_CITY)

    response = get_preview()

    vary = response.headers.get("Vary", "")
    assert "cookie" not in vary.lower()


# ── The per-IP limit ───────────────────────────────────────────────────────────────


def test_the_ip_limit_is_enforced(settings, throttle_adapter):
    """PRD §11.2: the public endpoints are rate limited per IP."""
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)

    client = Client()
    statuses = [client.get("/api/public/preview").status_code for _ in range(61)]

    assert statuses[:60] == [200] * 60
    assert statuses[60] == 429


def test_a_refused_request_says_when_to_retry(settings, throttle_adapter):
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)

    client = Client()
    for _ in range(61):
        response = client.get("/api/public/preview")

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


def test_the_limit_is_per_ip(settings, throttle_adapter):
    """One host cannot spend another host's budget."""
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)

    first = Client(REMOTE_ADDR="198.51.100.4")
    for _ in range(61):
        first.get("/api/public/preview")

    # A different caller address, on the same settings.
    other = Client(REMOTE_ADDR="203.0.113.7")

    assert other.get("/api/public/preview").status_code == 200


def test_a_refused_request_is_not_cached(settings, throttle_adapter):
    """A 429 is not content. Caching it would keep serving the refusal."""
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)

    client = Client()
    for _ in range(61):
        response = client.get("/api/public/preview")

    assert response.status_code == 429
    assert response.headers["Cache-Control"] == "no-store"


def test_the_cities_endpoint_is_rate_limited_too(settings, throttle_adapter):
    """The limit protects the endpoint *family*, not one route.

    Otherwise the cities endpoint would be a way around the limit: spend the preview's
    budget on the preview and then hammer the cities list, which costs the server the
    same work.
    """
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)

    client = Client()
    statuses = [client.get("/api/public/preview/cities").status_code for _ in range(61)]

    assert statuses[:60] == [200] * 60
    assert statuses[60] == 429


def test_a_refused_cities_request_is_not_cached(settings, throttle_adapter):
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)

    client = Client()
    for _ in range(61):
        response = client.get("/api/public/preview/cities")

    assert response.status_code == 429
    assert response.headers["Cache-Control"] == "no-store"
    assert int(response.headers["Retry-After"]) > 0


def test_the_cities_endpoint_has_its_own_budget(settings, throttle_adapter):
    """The two routes are counted separately, so one cannot spend the other's.

    They share a limit and a window but not a counter: a visitor who asks for the
    preview sixty times and then for the cities list gets the cities list.
    """
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)

    client = Client()
    for _ in range(60):
        client.get("/api/public/preview")

    assert client.get("/api/public/preview/cities").status_code == 200


# ── The caller address ─────────────────────────────────────────────────────────────


def test_the_forwarded_header_is_ignored_by_default(settings, throttle_adapter):
    """The header is attacker-controlled unless the deployment says otherwise.

    Next's rewrite forwards the browser's headers as they arrived, so a browser that
    sets `X-Forwarded-For` has that value reach Django unchanged. Trusting it
    unconditionally let any caller mint a fresh throttle bucket per request — the limit
    would have been no limit at all.
    """
    settings.TRUST_FORWARDED_FOR = False
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)

    client = Client(REMOTE_ADDR="198.51.100.4")
    statuses = [
        client.get("/api/public/preview", headers={"x-forwarded-for": "203.0.113.99"}).status_code
        for _ in range(61)
    ]

    assert statuses[:60] == [200] * 60
    assert statuses[60] == 429, "the forged header must not have bought a fresh bucket"


def test_the_forwarded_header_is_used_when_the_deployment_trusts_it(settings, throttle_adapter):
    """Behind a proxy that sets the header itself, the real address is the first hop."""
    settings.TRUST_FORWARDED_FOR = True
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)

    client = Client(REMOTE_ADDR="198.51.100.4")
    statuses = [
        client.get("/api/public/preview", headers={"x-forwarded-for": "203.0.113.99"}).status_code
        for _ in range(61)
    ]

    assert statuses[:60] == [200] * 60
    assert statuses[60] == 429


def test_a_forwarded_header_that_is_not_an_address_is_refused(settings, throttle_adapter):
    """The value must parse as an IP address, so a caller cannot pad the key with text.

    A key padded with arbitrary text is not a key: it is a fresh bucket per request,
    which is the thing the limit exists to prevent.
    """
    settings.TRUST_FORWARDED_FOR = True
    settings.GEO_FAKE_CITY = SOLO_CITY
    make_event(SOLO_CITY)

    client = Client(REMOTE_ADDR="198.51.100.4")
    statuses = [
        client.get("/api/public/preview", headers={"x-forwarded-for": "not-an-address"}).status_code
        for _ in range(61)
    ]

    assert statuses[:60] == [200] * 60
    assert statuses[60] == 429


# ── Fewer than three events ────────────────────────────────────────────────────────


def test_a_city_with_one_event_returns_one_card():
    """Fewer than 3 events is a real state, and it is not an error."""
    make_event(SOLO_CITY)

    body = get_preview(city=SOLO_CITY).json()

    assert len(body["items"]) == 1


def test_a_city_with_no_events_returns_no_cards():
    make_event(SOLO_CITY)

    body = get_preview(city="Nowhere-at-all").json()

    assert body["items"] == []


def test_the_preview_returns_at_most_three_cards():
    for index in range(5):
        venue = VenueFactory(city=SOLO_CITY, venue_fingerprint=f"venue-{index}|{SOLO_CITY}")
        event = EventFactory(
            venue=venue,
            start_time_utc=BASE + index * HOUR,
            start_time_tz="America/New_York",
        )
        write_event_fit(event=event, now=timezone.now(), actor=ACTOR)

    body = get_preview(city=SOLO_CITY).json()

    assert len(body["items"]) == 3


# ── The card's shape ───────────────────────────────────────────────────────────────


def test_a_card_carries_the_event_fit_and_the_source_badge():
    source = SourceFactory(source_type="venue")
    make_event(SOLO_CITY, source=source)

    body = get_preview(city=SOLO_CITY).json()

    card = body["items"][0]
    assert set(card) == {
        "id",
        "slug",
        "title",
        "start_time_utc",
        "start_time_tz",
        "venue_name",
        "city",
        "score",
        "tags",
        "source_name",
        "source_badge",
    }
    assert 1 <= card["score"] <= 5
    assert isinstance(card["tags"], list)
    assert card["source_name"] == source.name
    assert card["source_badge"] == "official_site"


def test_the_card_never_carries_a_personal_field():
    """AD-10 and AD-12: the preview is the session-free explanation."""
    make_event(SOLO_CITY)

    body = get_preview(city=SOLO_CITY).json()

    assert "relevance" not in str(body).lower()
    assert "user" not in str(body).lower()


# ── The supported cities ───────────────────────────────────────────────────────────


def test_the_cities_endpoint_lists_the_supported_cities():
    make_event(SOLO_CITY)

    body = get_cities().json()

    assert SOLO_CITY in body["cities"]


def test_the_cities_are_listed_alphabetically():
    """A picker whose order changes between requests is a picker nobody can use.

    The *why* the order is the code's and not the database's is checked structurally
    in `tests/architecture/test_preview_anonymity.py`: a text `ORDER BY` is a locale
    collation, and two deployments with different locales would list the same cities
    in a different order. Here the check is that the order the picker shows really is
    an alphabet.
    """
    for city in ("Zebra-preview", "Alpha-preview", "Mango-preview"):
        make_event(city)

    body = get_cities().json()

    listed = [name for name in body["cities"] if name.endswith("-preview")]
    assert listed == sorted(listed, key=str.casefold)


def test_a_city_with_no_upcoming_fit_is_not_supported():
    """A city with events but no fits is a city the preview cannot serve."""
    EventFactory(
        venue=VenueFactory(city="No-fit-city", venue_fingerprint="venue-nofit|No-fit-city"),
        start_time_utc=BASE,
        start_time_tz="America/New_York",
    )

    body = get_cities().json()

    assert "No-fit-city" not in body["cities"]


def test_a_stale_fit_does_not_make_its_city_supported():
    """A fit whose event has moved on describes an event that no longer exists.

    The version is bumped by one rather than set to a large number: the database's
    `guard_event_write` trigger only allows the version to stay or rise by 1.
    """
    event = make_event("Stale-fit-city")
    Event.objects.using(CATALOG).filter(pk=event.pk).update(event_version=F("event_version") + 1)

    body = get_cities().json()

    assert "Stale-fit-city" not in body["cities"]


# ── The response's shape ───────────────────────────────────────────────────────────


def test_the_preview_body_carries_the_city_and_its_source():
    make_event(SOLO_CITY)

    body = get_preview(city=SOLO_CITY).json()

    assert set(body) == {"city", "city_source", "items"}
    assert body["city_source"] in {"geo", "query", "fallback"}


def test_an_empty_preview_still_carries_the_city():
    """The frontend's empty state needs the name to say "No preview available in {city} yet."""
    body = get_preview(city="Queens").json()

    assert body["city"] == "Queens"
    assert body["items"] == []
