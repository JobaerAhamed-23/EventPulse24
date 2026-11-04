"""The city page endpoint: `GET /api/catalog/cities/by-slug/{slug}`.

The AC's list: a city above the threshold across two pages, a city at exactly 5 and at
exactly 6 events, an empty city, a city whose only fits are stale, an unknown city slug,
ordering with tied scores, and a request carrying a session cookie proving the response
does not vary by it.

**The route is a separate segment, not a second type on the same one.** The catalog
router already serves `/events/{event_id}` with `event_id: UUID`, and two routes cannot
share one path segment with different types. `cities/by-slug` keeps every other route
untouched.

**The response must not vary by the session.** A response that varies on the cookie is
not cacheable, and a shared cache that stored one variant under a key that ignores the
cookie would serve one visitor's response to another. So the test that sends a session
cookie asserts the body is byte-identical to the anonymous one.
"""

from datetime import timedelta

import pytest
from django.db import connections
from django.db.models import F
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.ingestion.models import City, Event, EventFit
from shared.db import CATALOG, PERSONAL
from shared.errors import ErrorOut
from tests.ingestion.factories import EventFactory, VenueFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

HOUR = timedelta(hours=1)
# Far enough ahead that a test's events are always "upcoming" for the read, which bounds
# the listing by the real now.
BASE = timezone.now() + timedelta(days=30)

# A city no other test uses, so the counts are exact.
CITY_SLUG = "api-testville"


def get_page(slug, **params):
    return Client().get(f"/api/catalog/cities/by-slug/{slug}", params)


def _city(slug: str = CITY_SLUG, name: str = "Api Testville") -> City:
    """A canonical city row, written the way `resolve_city` writes one."""
    return City.objects.using(CATALOG).create(
        slug=slug,
        name=name,
        country_code="US",
        normalized_key=name.lower(),
        region="",
    )


def _event(city: City, *, hours: float = 2, **overrides) -> Event:
    """An event in the city's venue, starting `hours` after `BASE`."""
    venue = VenueFactory(city=city.name, country_code="US")
    venue.city_ref = city
    venue.save(using=CATALOG)
    return EventFactory(start_time_utc=BASE + timedelta(hours=hours), venue=venue, **overrides)


def _fit(event: Event, *, city: City, score: int = 4, version: int | None = None) -> EventFit:
    """A fit row for an event in a city."""
    return EventFit.objects.using(CATALOG).create(
        event=event,
        city=city.name,
        city_ref=city,
        score=score,
        tags=["tonight"],
        event_version=version if version is not None else event.event_version,
        computed_at=BASE,
    )


def _city_with_events(count: int, *, city: City | None = None, score: int = 4) -> City:
    """A city with `count` upcoming, published, current fits."""
    city = city or _city()
    for n in range(count):
        _fit(_event(city, hours=2 + n), city=city, score=score)
    return city


def ids_of(items):
    return [item["id"] for item in items]


# ── The endpoint answers ──────────────────────────────────────────────────────────


def test_the_page_returns_the_city():
    city = _city_with_events(6)

    response = get_page(city.slug)

    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == city.slug
    assert body["name"] == city.name
    assert body["country_code"] == "US"


def test_the_body_carries_every_field_the_page_needs():
    city = _city_with_events(6)

    body = get_page(city.slug).json()

    assert set(body) == {
        "slug",
        "name",
        "country_code",
        "region",
        "is_published",
        "event_count",
        "items",
        "page",
        "page_size",
        "has_next",
    }


def test_the_body_carries_the_event_facts_the_page_shows():
    """The page shows the event and its fit: the score, the tags, the time, the venue."""
    city = _city_with_events(6)
    event = _event(city, hours=3, title="Winter Sessions", is_sold_out=True)
    _fit(event, city=city, score=5)

    body = get_page(city.slug).json()
    item = next(i for i in body["items"] if i["id"] == str(event.id))

    assert item["title"] == "Winter Sessions"
    assert item["score"] == 5
    assert item["tags"] == ["tonight"]
    assert item["start_time_tz"] == event.start_time_tz
    assert item["venue_name"] == event.venue.name
    assert item["is_sold_out"] is True
    assert item["event_version"] == event.event_version


def test_the_events_carry_the_canonical_city_name():
    """Every event on the page carries the **canonical** city's name.

    A fit row stores the venue's own spelling of the city, and the preview is keyed on
    that free text. This page is keyed on the canonical city and its heading is the
    canonical name, so the free text would put two spellings under one heading.
    """
    city = _city_with_events(6)
    event = _event(city, hours=3)
    fit = _fit(event, city=city, score=5)
    EventFit.objects.using(CATALOG).filter(pk=fit.pk).update(city="  brooklyn  ")

    body = get_page(city.slug).json()

    assert body["name"] == "Api Testville"
    assert {item["city"] for item in body["items"]} == {"Api Testville"}


# ── The threshold ─────────────────────────────────────────────────────────────────


def test_a_city_with_exactly_five_events_is_not_published():
    """FR-27 says ">5 events", which means **more than** five."""
    city = _city_with_events(5)

    body = get_page(city.slug).json()

    assert body["event_count"] == 5
    assert body["is_published"] is False


def test_a_city_with_exactly_six_events_is_published():
    city = _city_with_events(6)

    body = get_page(city.slug).json()

    assert body["event_count"] == 6
    assert body["is_published"] is True


# ── The graceful degradation ──────────────────────────────────────────────────────


def test_an_empty_city_is_a_200_with_no_events():
    """FR-27: "a city page degrades gracefully when no events are present".

    **Not a 404 and not an error.** The city exists; its page has nothing on it yet.
    """
    city = _city()

    response = get_page(city.slug)

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["event_count"] == 0
    assert body["is_published"] is False


def test_a_sparse_city_still_answers_with_its_identity():
    """The page is about a *city*, so even a sparse one says which city it is."""
    city = _city_with_events(2)

    body = get_page(city.slug).json()

    assert body["name"] == city.name
    assert body["slug"] == city.slug


def test_a_city_whose_only_fits_are_stale_does_not_qualify():
    """The count and the listing are computed by the same filters."""
    city = _city_with_events(6)
    Event.objects.using(CATALOG).update(event_version=F("event_version") + 1)

    body = get_page(city.slug).json()

    assert body["event_count"] == 0
    assert body["is_published"] is False
    assert body["items"] == []


def test_an_unknown_city_slug_is_a_clean_404():
    response = get_page("no-such-city")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert body["message"] == "We couldn't find that city."
    ErrorOut.model_validate(body)


def test_an_unknown_city_slug_is_not_a_500():
    response = get_page("no-such-city")

    assert response.status_code < 500


def test_the_slug_match_is_exact():
    """Two case variants would be two URLs for one page — a duplicate-URL fault."""
    city = _city_with_events(6)

    response = get_page(city.slug.upper())

    assert response.status_code == 404


# ── The ordering ──────────────────────────────────────────────────────────────────


def test_the_best_fit_comes_first():
    """The fit is the reason an event is on the page, so the score leads."""
    city = _city()
    worse = _event(city, hours=2)
    better = _event(city, hours=48)
    _fit(worse, city=city, score=3)
    _fit(better, city=city, score=5)

    body = get_page(city.slug).json()

    assert ids_of(body["items"]).index(str(better.id)) < ids_of(body["items"]).index(str(worse.id))


def test_a_score_tie_is_broken_on_the_start_time():
    """Two events with the same fit: the sooner one is the more useful one."""
    city = _city()
    later = _event(city, hours=48)
    sooner = _event(city, hours=2)
    _fit(later, city=city, score=3)
    _fit(sooner, city=city, score=3)

    body = get_page(city.slug).json()

    assert ids_of(body["items"]) == [str(sooner.id), str(later.id)]


def test_a_tied_score_and_tied_time_still_have_a_defined_order():
    """The tiebreak is the event id, so the order is total and two requests agree."""
    city = _city()
    first = _event(city, hours=2)
    second = _event(city, hours=2)
    _fit(first, city=city, score=3)
    _fit(second, city=city, score=3)

    one = ids_of(get_page(city.slug).json()["items"])
    two = ids_of(get_page(city.slug).json()["items"])

    assert one == two
    assert set(one) == {str(first.id), str(second.id)}


# ── The paging ────────────────────────────────────────────────────────────────────


def test_a_city_above_the_threshold_pages_across_two_pages():
    """The listing is unbounded, and a crawler walks it a page at a time."""
    city = _city_with_events(7)
    everything = ids_of(get_page(city.slug).json()["items"])

    first = get_page(city.slug, page=1, page_size=3).json()
    second = get_page(city.slug, page=2, page_size=3).json()
    third = get_page(city.slug, page=3, page_size=3).json()

    walked = [*ids_of(first["items"]), *ids_of(second["items"]), *ids_of(third["items"])]
    assert walked == everything, "the walk visits every event, in order"
    assert len(set(walked)) == len(walked), "and visits none of them twice"


def test_a_page_beyond_the_last_one_is_empty_rather_than_an_error():
    """A crawler walking off the end of a listing is doing something ordinary."""
    city = _city_with_events(3)

    response = get_page(city.slug, page=99, page_size=3)

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["has_next"] is False


def test_the_page_size_is_capped_by_the_schema():
    """A request cannot ask for a city's whole history in one response."""
    from shared.constants import CITY_PAGE_MAX_PAGE_SIZE

    response = get_page(CITY_SLUG, page_size=CITY_PAGE_MAX_PAGE_SIZE + 1000)

    assert response.status_code == 422, "the ceiling is enforced at the edge"


def test_has_next_says_whether_there_is_another_page():
    city = _city_with_events(3)

    first = get_page(city.slug, page=1, page_size=2).json()
    second = get_page(city.slug, page=2, page_size=2).json()

    assert first["has_next"] is True
    assert second["has_next"] is False


def test_an_off_season_city_has_no_next_page():
    """**The paging flag is measured against the listing, not against the
    qualification.**

    A city whose events have all passed still qualifies — six events in the window —
    but its listing is empty. `has_next` must be `False`: a crawler that is told there
    is a next page on an empty page follows it, and follows it again, forever.
    """
    city = _city()
    for n in range(6):
        event = _event(city, hours=-24 * (n + 30))
        _fit(event, city=city, score=4)

    body = get_page(city.slug).json()

    assert body["items"] == [], "nothing is upcoming"
    assert body["event_count"] == 6, "but the city still qualifies"
    assert body["is_published"] is True
    assert body["has_next"] is False, "and there is no page to go to"


def test_has_next_is_measured_against_the_upcoming_count():
    """The listing's total is the denominator for the paging flag."""
    city = _city()
    for n in range(3):
        _fit(_event(city, hours=-24 * (n + 30)), city=city, score=4)
    for n in range(3):
        _fit(_event(city, hours=2 + n), city=city, score=4)

    body = get_page(city.slug, page=1, page_size=2).json()

    assert body["event_count"] == 6, "all six qualify"
    assert len(body["items"]) == 2, "but only the upcoming three are listed"
    assert body["has_next"] is True, "there is a third upcoming event to page to"

    last = get_page(city.slug, page=2, page_size=2).json()
    assert len(last["items"]) == 1
    assert last["has_next"] is False


def test_a_page_below_one_is_refused():
    """The query schema bounds the page number, so a nonsense one is a 422."""
    response = get_page(CITY_SLUG, page=0)

    assert response.status_code == 422


# ── AD-12: no session, no personal, no cookie ─────────────────────────────────────


def test_the_response_does_not_vary_by_the_session():
    """A shared cache that ignored the cookie would serve one visitor's body to another."""
    city = _city_with_events(6)

    anonymous = Client().get(f"/api/catalog/cities/by-slug/{city.slug}")
    with_session = Client().get(
        f"/api/catalog/cities/by-slug/{city.slug}",
        headers={"Cookie": "sessionid=whatever-the-browser-had"},
    )

    assert with_session.status_code == 200
    assert with_session.content == anonymous.content


def test_the_response_does_not_vary_by_the_cookie():
    """`Vary` is what makes the caching claim true."""
    city = _city_with_events(6)

    response = get_page(city.slug)

    vary = response.headers.get("Vary", "")
    assert "cookie" not in vary.lower()
    assert vary


def test_the_response_sets_no_session_cookie():
    city = _city_with_events(6)

    response = get_page(city.slug)

    assert "Set-Cookie" not in response.headers


def test_a_404_sets_no_session_cookie():
    response = get_page("no-such-city")

    assert "Set-Cookie" not in response.headers


def test_the_page_never_queries_the_personal_schema():
    """AD-12, at its strongest: does not *query* `personal`. The strongest statement
    about a leak is that the query never happened."""
    city = _city_with_events(6)

    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        Client().get(f"/api/catalog/cities/by-slug/{city.slug}")

    assert len(personal_queries) == 0, "the city page queried the personal schema: " + "; ".join(
        str(q["sql"]) for q in personal_queries
    )


def test_the_page_costs_a_bounded_number_of_queries():
    """The city page is a cached, public, crawler-facing URL — it has to be cheap.

    **Three queries**: the city, the counts, and the listing. The two counts used to be
    two separate loads of the same rows, which made four; they are one load now, split
    in Python, because the upcoming rows are a subset of the qualifying ones. The
    listing is a genuinely different query — the counts are ordered by start time and
    the listing by score — so it cannot be folded in.

    The number is asserted so that a future change that adds a query has to say so.
    """
    city = _city_with_events(6)

    with CaptureQueriesContext(connections[CATALOG]) as queries:
        response = Client().get(f"/api/catalog/cities/by-slug/{city.slug}")

    assert response.status_code == 200
    assert len(queries) == 3, "the city, the counts, and the listing: " + "; ".join(
        str(q["sql"])[:120] for q in queries
    )


def test_a_404_never_queries_the_personal_schema():
    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        Client().get("/api/catalog/cities/by-slug/no-such-city")

    assert len(personal_queries) == 0


def test_a_successful_page_is_cacheable():
    city = _city_with_events(6)

    response = get_page(city.slug)

    assert response.headers["Cache-Control"].startswith("public")


def test_an_unknown_slug_is_cacheable_as_such():
    """A crawler that asks for a URL that does not exist should not hammer the origin."""
    response = get_page("no-such-city")

    assert "Cache-Control" in response.headers


def test_the_404_carries_the_same_cache_headers_as_the_200():
    """The headers are set before the read, so the not-found keeps them too."""
    city = _city_with_events(6)

    found = get_page(city.slug)
    missing = get_page("no-such-city")

    assert missing.headers["Cache-Control"] == found.headers["Cache-Control"]
    assert missing.headers.get("Vary") == found.headers.get("Vary")


# ── The contract ──────────────────────────────────────────────────────────────────


def test_the_endpoint_is_in_the_openapi_schema():
    schema = Client().get("/api/openapi.json").json()

    assert "/api/catalog/cities/by-slug/{slug}" in schema["paths"]


def test_the_event_routes_still_work():
    """The city route is a new segment; it did not take any other one over."""
    event = EventFactory(start_time_utc=BASE + HOUR)

    by_slug = Client().get(f"/api/catalog/events/by-slug/{event.slug}")
    by_id = Client().get(f"/api/catalog/events/{event.id}")

    assert by_slug.status_code == 200
    assert by_id.status_code == 200


def test_the_response_never_carries_the_raw_source_payload():
    """AD-9: the stripped description is display content; the raw payload is not."""
    city = _city_with_events(6)
    event = _event(city, hours=3, description="Stripped source text")
    _fit(event, city=city, score=4)

    body = get_page(city.slug).json()

    assert "payload" not in str(body)
    assert "Stripped source text" in str(body)
