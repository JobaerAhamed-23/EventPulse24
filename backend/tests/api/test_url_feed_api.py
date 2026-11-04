"""The URL feed endpoint: `GET /api/catalog/url-feed`.

The AC's list: a feed that lists the public event pages and the qualifying city pages,
the exclusions (an `in_review` event, a superseded event, a below-threshold city), the
`lastmod` being the event's real last change, the page boundary, and a request carrying
a session cookie proving the response does not vary by it.

**This endpoint is the sitemap's source.** Every claim it makes is a claim about a URL
the site actually serves — so a URL in the sitemap is a URL that serves, and a URL that
serves is a URL in the sitemap. The membership rules are not this module's invention:
they are the two page reads' rules, and the exclusion tests below are the ones that
would fail if the feed drifted away from them.

**The session-free claim is load-bearing here.** The feed is fetched by crawlers, with
no account and no cookie, and a response that varied by the cookie would be uncacheable
and would leak one visitor's response to another.
"""

from datetime import datetime, timedelta

import pytest
from django.db import connections
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.ingestion.models import City, Event, EventFit, EventStateChange
from shared.db import CATALOG, PERSONAL
from shared.errors import ErrorOut
from tests.ingestion.factories import (
    EventFactory,
    EventStateChangeFactory,
    VenueFactory,
    make_superseded_pair,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
# Far enough ahead that a test's events are always inside the qualification window.
BASE = timezone.now() + timedelta(days=30)

# A city no other test uses, so the counts are exact.
CITY_SLUG = "feed-api-testville"


def get_feed(**params):
    return Client().get("/api/catalog/url-feed", params)


def _city(slug: str = CITY_SLUG, name: str = "Feed Api Testville") -> City:
    """A canonical city row, written the way `resolve_city` writes one."""
    return City.objects.using(CATALOG).create(
        slug=slug,
        name=name,
        country_code="US",
        normalized_key=name.lower(),
        region="",
    )


def _event(*, city: City | None = None, hours: float = 2, **overrides) -> Event:
    """An event, published and scheduled by default."""
    venue = VenueFactory(city=city.name if city else "Los Angeles", country_code="US")
    if city is not None:
        venue.city_ref = city
        venue.save(using=CATALOG)
    return EventFactory(start_time_utc=BASE + timedelta(hours=hours), venue=venue, **overrides)


def _fit(event: Event, *, city: City) -> EventFit:
    """A fit row for an event in a city."""
    return EventFit.objects.using(CATALOG).create(
        event=event,
        city=city.name,
        city_ref=city,
        score=4,
        tags=["tonight"],
        event_version=event.event_version,
        computed_at=BASE,
    )


def _city_with_events(count: int) -> City:
    """A city with `count` published, current fits."""
    city = _city()
    for n in range(count):
        _fit(_event(city=city, hours=2 + n), city=city)
    return city


def paths_of(body) -> list[str]:
    return [item["path"] for item in body["items"]]


def _as_datetime(value: str) -> datetime:
    """The wire's timestamp, parsed back into a datetime.

    **The comparison is on instants, not on strings, and at the wire's precision.**
    The JSON carries an ISO-8601 timestamp with a `Z` suffix, and the millisecond is
    all it keeps — Django's JSON encoder rounds to milliseconds, while the column
    holds microseconds. So the comparison truncates to the millisecond; without that,
    two spellings of the same instant would look like two different instants.
    """
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(microsecond=(parsed.microsecond // 1000) * 1000)


def _truncated(moment: datetime) -> datetime:
    """A moment at the wire's precision."""
    return moment.replace(microsecond=(moment.microsecond // 1000) * 1000)


# ── The endpoint answers ──────────────────────────────────────────────────────────


def test_the_feed_lists_the_public_event_pages():
    event = _event()

    body = get_feed().json()

    assert f"/events/{event.slug}" in paths_of(body)


def test_the_feed_lists_the_qualifying_city_pages():
    city = _city_with_events(6)

    body = get_feed().json()

    assert f"/events-in-{city.slug}" in paths_of(body)


def test_the_body_carries_every_field_the_sitemap_needs():
    """A sitemap entry needs a URL and a `lastmod`. The kind is there so the renderer
    can tell the two page types apart if it ever needs to."""
    _event()

    body = get_feed().json()

    assert set(body) == {"items", "page", "page_size", "total", "has_next"}
    assert set(body["items"][0]) == {"path", "kind", "last_modified"}


def test_the_kinds_are_the_two_public_page_types():
    event = _event()
    city = _city_with_events(6)

    body = get_feed().json()
    kinds = {item["path"]: item["kind"] for item in body["items"]}

    assert kinds[f"/events/{event.slug}"] == "event"
    assert kinds[f"/events-in-{city.slug}"] == "city"


def test_the_path_is_a_path_and_not_a_url():
    """The origin is the frontend's business. A backend that emitted absolute URLs
    would have to know how the frontend is deployed."""
    _event()

    body = get_feed().json()

    assert body["items"][0]["path"].startswith("/")


# ── The exclusions: the feed is the public surface and nothing else ───────────────


def test_an_in_review_event_is_not_in_the_feed():
    """A sitemap that lists a 404 is a crawl-budget leak."""
    _event(publication_status=Event.PublicationStatus.IN_REVIEW)

    body = get_feed().json()

    assert paths_of(body) == []


def test_a_superseded_event_is_not_in_the_feed():
    old, _new = make_superseded_pair()

    body = get_feed().json()

    assert f"/events/{old.slug}" not in paths_of(body)


def test_the_successor_of_a_superseded_event_is_in_the_feed():
    _old, new = make_superseded_pair()

    body = get_feed().json()

    assert f"/events/{new.slug}" in paths_of(body)


def test_a_below_threshold_city_is_not_in_the_feed():
    """FR-27's threshold is `> 5`, so a city with exactly five has no published page."""
    _city_with_events(5)

    body = get_feed().json()

    assert not [path for path in paths_of(body) if path.startswith("/events-in-")]


def test_a_city_above_the_threshold_is_in_the_feed():
    city = _city_with_events(6)

    body = get_feed().json()

    assert f"/events-in-{city.slug}" in paths_of(body)


def test_a_past_event_is_still_in_the_feed():
    """A page for an event that already happened stays addressable and stays indexed."""
    past = _event(hours=-48)

    body = get_feed().json()

    assert f"/events/{past.slug}" in paths_of(body)


# ── `lastmod`: the event's real last change ───────────────────────────────────────


def test_the_lastmod_of_an_unchanged_event_is_its_creation():
    event = _event()

    body = get_feed().json()

    entry = next(i for i in body["items"] if i["path"] == f"/events/{event.slug}")
    assert _as_datetime(entry["last_modified"]) == _truncated(event.created_at)


def test_the_lastmod_is_the_state_change_time():
    """**Not** `Event.updated_at` — that column is `auto_now`, and every production
    write goes through `QuerySet.update()`, which never touches `auto_now`. It is
    frozen at creation and would report "this page has never changed"."""
    event = _event()
    changed_at = BASE - timedelta(days=3)
    EventStateChange.objects.using(CATALOG).create(
        event=event,
        kind=EventStateChange.Kind.TIME_MOVED,
        event_version=event.event_version,
        before={"start_utc": event.start_time_utc},
        after={"start_utc": event.start_time_utc + DAY},
        actor_kind="system",
        actor_label="ingest_pipeline",
        occurred_at=changed_at,
    )

    body = get_feed().json()

    entry = next(i for i in body["items"] if i["path"] == f"/events/{event.slug}")
    assert _as_datetime(entry["last_modified"]) == _truncated(changed_at)


def test_the_lastmod_is_not_the_frozen_updated_at():
    event = _event()
    EventStateChangeFactory(event=event, event_version=event.event_version, occurred_at=BASE - DAY)

    body = get_feed().json()

    entry = next(i for i in body["items"] if i["path"] == f"/events/{event.slug}")
    assert _as_datetime(entry["last_modified"]) == _truncated(BASE - DAY)
    assert _as_datetime(entry["last_modified"]) != event.updated_at


def test_a_city_lastmod_is_the_latest_of_its_events():
    city = _city_with_events(6)
    latest = BASE - timedelta(hours=2)
    target = city.event_fits.order_by("id").first().event
    EventStateChange.objects.using(CATALOG).create(
        event=target,
        kind=EventStateChange.Kind.DETAIL_CHANGED,
        event_version=target.event_version,
        before={"title": target.title},
        after={"title": "Renamed"},
        actor_kind="system",
        actor_label="ingest_pipeline",
        occurred_at=latest,
    )

    body = get_feed().json()

    entry = next(i for i in body["items"] if i["path"] == f"/events-in-{city.slug}")
    assert _as_datetime(entry["last_modified"]) == _truncated(latest)


# ── The paging ────────────────────────────────────────────────────────────────────


def test_the_page_holds_the_requested_number_of_urls():
    for n in range(5):
        _event(hours=n)

    body = get_feed(page=1, page_size=2).json()

    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total"] == 5
    assert body["has_next"] is True


def test_two_pages_never_overlap_and_never_skip_a_url():
    for n in range(5):
        _event(hours=n)

    walked = []
    for page in (1, 2, 3):
        walked.extend(paths_of(get_feed(page=page, page_size=2).json()))

    assert len(walked) == 5
    assert len(set(walked)) == 5


def test_a_page_beyond_the_last_one_is_empty_and_not_an_error():
    """A crawler walking off the end of a listing is doing something ordinary."""
    _event()

    response = get_feed(page=9, page_size=10)

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["has_next"] is False


def test_a_page_below_one_is_refused():
    """The edge refuses a bad request with a 422 — a caller that asks for page zero
    has made a mistake, and quietly handing it page one would hide the mistake."""
    response = get_feed(page=0)

    assert response.status_code == 422


def test_the_page_size_is_capped_by_the_schema():
    from shared.constants import URL_FEED_MAX_PAGE_SIZE

    response = get_feed(page_size=URL_FEED_MAX_PAGE_SIZE + 1000)

    assert response.status_code == 422


# ── AD-12: no session, no personal, no cookie ─────────────────────────────────────


def test_the_response_does_not_vary_by_the_session():
    _event()

    anonymous = Client().get("/api/catalog/url-feed")
    with_session = Client().get(
        "/api/catalog/url-feed",
        headers={"Cookie": "sessionid=whatever-the-browser-had"},
    )

    assert with_session.status_code == 200
    assert with_session.content == anonymous.content


def test_the_response_does_not_vary_by_the_cookie():
    _event()

    response = get_feed()

    vary = response.headers.get("Vary", "")
    assert "cookie" not in vary.lower()
    assert vary


def test_the_response_sets_no_session_cookie():
    _event()

    response = get_feed()

    assert "Set-Cookie" not in response.headers


def test_the_feed_never_queries_the_personal_schema():
    """AD-12, at its strongest: the query never happened."""
    _event()

    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        Client().get("/api/catalog/url-feed")

    assert len(personal_queries) == 0, "the feed queried the personal schema: " + "; ".join(
        str(q["sql"]) for q in personal_queries
    )


def test_the_feed_costs_a_bounded_number_of_queries():
    """The feed is a crawler-facing URL that grows with the catalog, so its cost must
    not grow with it.

    **Four queries**: the events' count, the cities' count, and the two slices the page
    needs. The count and the slice of each half come from the *same* queryset, so
    counting one rule and slicing another cannot leave a page boundary in the wrong
    place. The number is asserted so that a future change that adds a query has to say
    so — the first draft of this read counted twice and cost six.
    """
    _event()

    with CaptureQueriesContext(connections[CATALOG]) as queries:
        response = Client().get("/api/catalog/url-feed")

    assert response.status_code == 200
    assert len(queries) == 4, "the two counts and the two slices: " + "; ".join(
        str(q["sql"])[:120] for q in queries
    )


def test_a_successful_feed_is_cacheable():
    _event()

    response = get_feed()

    assert response.headers["Cache-Control"].startswith("public")


# ── The contract ──────────────────────────────────────────────────────────────────


def test_the_endpoint_is_in_the_openapi_schema():
    schema = Client().get("/api/openapi.json").json()

    assert "/api/catalog/url-feed" in schema["paths"]


def test_the_error_shape_is_the_shared_one():
    """The 422 is the project's own error shape, not a bare list of messages."""
    response = get_feed(page=0)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_request"
    ErrorOut.model_validate(body)


def test_the_feed_never_carries_the_raw_source_payload():
    """AD-9: the feed carries paths and times, and nothing else."""
    event = _event(description="Stripped source text")

    body = get_feed().json()

    assert "payload" not in str(body)
    assert "Stripped source text" not in str(body)
    assert f"/events/{event.slug}" in paths_of(body)
