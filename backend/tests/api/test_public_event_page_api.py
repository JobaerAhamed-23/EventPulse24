"""The public event page endpoint: `GET /api/catalog/events/by-slug/{slug}`.

The AC's list: a published upcoming event, a published **past** event (the case
`get_event` deliberately refuses), an `in_review` event, a superseded event with and
without a live successor, an unknown slug, an event with no venue, and a request
carrying a session cookie proving the response does not vary by it.

**The route is a separate segment, not a second type on the same one.** The catalog
router already serves `/events/{event_id}` with `event_id: UUID`, and two routes cannot
share one path segment with different types. `by-slug` keeps the UUID read — and every
caller of it — untouched.

**The response must not vary by the session.** A response that varies on the cookie is
not cacheable, and a shared cache that stored one variant under a key that ignores the
cookie would serve one visitor's response to another. So the test that sends a session
cookie asserts the body is byte-identical to the anonymous one.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import connections
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.ingestion.models import Event
from shared.db import CATALOG, PERSONAL
from shared.errors import ErrorOut
from tests.ingestion.factories import EventFactory, VenueFactory, make_superseded_pair

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

HOUR = timedelta(hours=1)
# Far enough ahead that a test's events are always "upcoming" for the reads that bound
# by the real now.
BASE = timezone.now() + timedelta(days=30)


def get_page(slug, **kwargs):
    return Client().get(f"/api/catalog/events/by-slug/{slug}", **kwargs)


def _wire_time(instant):
    """The wire form of an instant: ISO-8601 with a `Z`, to the millisecond.

    Django's JSON encoder drops the microseconds beyond the millisecond, so the
    expectation is built the same way the response is.
    """
    return instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def test_the_page_returns_the_event():
    event = EventFactory(start_time_utc=BASE + HOUR)

    response = get_page(event.slug)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(event.id)
    assert body["slug"] == event.slug
    assert body["title"] == event.title


def test_a_past_event_still_resolves():
    """The case `get_event` refuses: the page stays addressable and stays indexed."""
    event = EventFactory(start_time_utc=timezone.now() - HOUR)

    response = get_page(event.slug)

    assert response.status_code == 200
    assert response.json()["id"] == str(event.id)


def test_the_same_event_is_a_404_by_id_once_it_has_started():
    """The two reads answer different questions, and this proves they still differ."""
    event = EventFactory(start_time_utc=timezone.now() - HOUR)

    by_slug = get_page(event.slug)
    by_id = Client().get(f"/api/catalog/events/{event.id}")

    assert by_slug.status_code == 200
    assert by_id.status_code == 404


def test_the_body_carries_every_field_the_page_and_its_json_ld_need():
    venue = VenueFactory(name="Town Hall", city="Brooklyn", country_code="US")
    event = EventFactory(
        start_time_utc=BASE + HOUR,
        end_time_utc=BASE + 2 * HOUR,
        venue=venue,
        title="Winter Sessions",
        description="An evening of quiet music.",
        canonical_url="https://events.example.test/winter-sessions",
        is_sold_out=True,
    )

    body = get_page(event.slug).json()

    assert set(body) == {
        "id",
        "slug",
        "title",
        "description",
        "canonical_url",
        "start_time_utc",
        "start_time_tz",
        "end_time_utc",
        "venue_name",
        "venue_address",
        "venue_city",
        "venue_country_code",
        "status",
        "is_sold_out",
        "event_version",
        "source_name",
        "tz_review_pending",
        "schema_org",
    }
    assert body["title"] == "Winter Sessions"
    assert body["description"] == "An evening of quiet music."
    # The wire form is ISO-8601 with a `Z`; the instant is the Event's own, to the
    # millisecond Django's encoder keeps.
    assert body["start_time_utc"] == _wire_time(event.start_time_utc)
    assert body["end_time_utc"] == _wire_time(event.end_time_utc)
    assert body["start_time_tz"] == event.start_time_tz
    assert body["venue_name"] == "Town Hall"
    assert body["venue_address"] == "Town Hall, Brooklyn, US"
    assert body["venue_city"] == "Brooklyn"
    assert body["venue_country_code"] == "US"
    assert body["canonical_url"] == "https://events.example.test/winter-sessions"
    assert body["status"] == Event.Status.SCHEDULED
    assert body["is_sold_out"] is True
    assert body["event_version"] == event.event_version
    assert body["source_name"] == event.source.name


def test_the_body_carries_the_iana_timezone_the_json_ld_requires():
    """ARCHITECTURE-SPINE.md:166 — the public JSON-LD needs the IANA zone name."""
    event = EventFactory(start_time_utc=BASE + HOUR)

    body = get_page(event.slug).json()

    assert body["start_time_tz"] == event.start_time_tz
    assert "/" in body["start_time_tz"]


def test_the_body_carries_the_finished_structured_data():
    """AD-12: *"Schema.org `Event` JSON-LD is emitted from the same data the page renders."*

    The page embeds what it is given, so the object has to be **on the wire** — built by
    the server, from the same read, rather than assembled by the frontend from fields that
    could drift apart.
    """
    event = EventFactory(start_time_utc=BASE + HOUR, title="Winter Sessions")

    body = get_page(event.slug).json()

    schema_org = body["schema_org"]
    assert schema_org["@context"] == "https://schema.org"
    assert schema_org["@type"] == "Event"
    assert schema_org["name"] == "Winter Sessions"


def test_the_structured_data_agrees_with_the_page_it_travels_with():
    """The guarantee, stated as a comparison.

    If the JSON-LD and the visible page could disagree, the page would earn a
    structured-data penalty. So the two are compared field by field, here.
    """
    venue = VenueFactory(name="Town Hall", city="Brooklyn", country_code="US")
    event = EventFactory(
        start_time_utc=BASE + HOUR,
        end_time_utc=BASE + 2 * HOUR,
        venue=venue,
        title="Winter Sessions",
        description="An evening of quiet music.",
        is_sold_out=True,
    )

    body = get_page(event.slug).json()
    schema_org = body["schema_org"]

    assert schema_org["name"] == body["title"]
    assert schema_org["description"] == body["description"]
    assert schema_org["location"]["name"] == body["venue_name"]
    assert schema_org["eventStatus"].endswith("EventScheduled")
    assert schema_org["offers"]["availability"].endswith("SoldOut")


def test_the_structured_data_carries_the_timezone_offset_not_a_bare_utc():
    """The AC: the times are emitted with the offset implied by `start_time_tz`.

    The strongest form of this: the emitted local time must be the **event's own wall
    clock**, not the UTC one. An event at 01:38 UTC in New York is 20:38 the previous
    evening locally, and a structured-data field that said "01:38" would be stating the
    wrong hour of the day.
    """
    event = EventFactory(start_time_utc=BASE + HOUR, start_time_tz="America/New_York")

    schema_org = get_page(event.slug).json()["schema_org"]
    start_date = schema_org["startDate"]

    assert start_date.endswith("-05:00")
    local_wall_clock = event.start_time_utc.astimezone(ZoneInfo("America/New_York"))
    assert start_date.startswith(local_wall_clock.strftime("%Y-%m-%dT%H:%M:%S"))


def test_an_event_with_no_venue_has_no_location_in_the_structured_data():
    """A venue-less event omits `location` rather than emitting an empty `Place`."""
    event = EventFactory(start_time_utc=BASE + HOUR, venue=None)

    schema_org = get_page(event.slug).json()["schema_org"]

    assert "location" not in schema_org


def test_the_structured_data_never_carries_a_price():
    """The registry knows no price, so the structured data states no price."""
    event = EventFactory(start_time_utc=BASE + HOUR)

    schema_org = get_page(event.slug).json()["schema_org"]

    assert "price" not in schema_org["offers"]
    assert "priceCurrency" not in schema_org["offers"]


def test_the_body_carries_the_event_version_the_revalidation_work_item_needs():
    event = EventFactory(start_time_utc=BASE + HOUR)

    body = get_page(event.slug).json()

    assert body["event_version"] == event.event_version
    assert body["event_version"] >= 1


def test_an_in_review_event_is_a_404():
    event = EventFactory(
        start_time_utc=BASE + HOUR, publication_status=Event.PublicationStatus.IN_REVIEW
    )

    response = get_page(event.slug)

    assert response.status_code == 404


def test_an_in_review_event_is_a_404_not_a_200_with_a_hidden_flag():
    """The model's own comment: "not digest-eligible, not publicly listed"."""
    event = EventFactory(
        start_time_utc=BASE + HOUR, publication_status=Event.PublicationStatus.IN_REVIEW
    )

    body = get_page(event.slug).json()

    assert "id" not in body
    assert body["code"] == "not_found"


def test_a_superseded_event_is_a_404():
    old, _ = make_superseded_pair(start_time_utc=BASE + HOUR)

    response = get_page(old.slug)

    assert response.status_code == 404


def test_a_superseded_event_directs_to_its_live_successor():
    """The link a crawler already holds resolves forward rather than dying."""
    old, new = make_superseded_pair(start_time_utc=BASE + HOUR)

    body = get_page(old.slug).json()

    assert body["code"] == "not_found"
    assert body["details"]["superseded_by_slug"] == new.slug


def test_the_successor_resolves_at_its_own_slug():
    old, new = make_superseded_pair(start_time_utc=BASE + HOUR)

    response = get_page(new.slug)

    assert response.status_code == 200
    assert response.json()["id"] == str(new.id)


def test_an_unknown_slug_is_a_clean_404():
    response = get_page("no-such-event")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert body["message"] == "We couldn't find that event."
    ErrorOut.model_validate(body)


def test_an_unknown_slug_is_not_a_500():
    response = get_page("no-such-event")

    assert response.status_code == 404
    assert response.status_code < 500


def test_an_unknown_slug_is_cacheable_as_such():
    """A crawler that asks for a URL that does not exist should not hammer the origin."""
    response = get_page("no-such-event")

    assert "Cache-Control" in response.headers


def test_the_404_carries_the_same_cache_headers_as_the_200():
    """The headers are set before the read, so the not-found keeps them too."""
    event = EventFactory(start_time_utc=BASE + HOUR)

    found = get_page(event.slug)
    missing = get_page("no-such-event")

    assert missing.headers["Cache-Control"] == found.headers["Cache-Control"]
    assert missing.headers.get("Vary") == found.headers.get("Vary")


def test_a_successful_page_is_cacheable():
    event = EventFactory(start_time_utc=BASE + HOUR)

    response = get_page(event.slug)

    assert response.headers["Cache-Control"].startswith("public")


def test_the_response_does_not_vary_by_the_cookie():
    """`Vary` is what makes the caching claim true.

    A response that varies on the cookie is not cacheable, and a shared cache that stored
    one variant under a key that ignores the cookie would serve one visitor's body to
    another. So nothing session-related may appear in `Vary`.
    """
    event = EventFactory(start_time_utc=BASE + HOUR)

    response = get_page(event.slug)

    vary = response.headers.get("Vary", "")
    assert "cookie" not in vary.lower()
    assert vary


def test_the_response_does_not_vary_by_the_session():
    """A shared cache that ignored the cookie would serve one visitor's body to another."""
    event = EventFactory(start_time_utc=BASE + HOUR)

    anonymous = Client().get(f"/api/catalog/events/by-slug/{event.slug}")
    with_session = Client().get(
        f"/api/catalog/events/by-slug/{event.slug}",
        headers={"Cookie": "sessionid=whatever-the-browser-had"},
    )

    assert with_session.status_code == 200
    assert with_session.content == anonymous.content


def test_the_page_never_queries_the_personal_schema():
    """AD-12, at its strongest: not "does not return personal data" — does not *query*
    `personal`. The personal alias is wrapped and the count of personal queries must be
    zero. The strongest statement about a leak is that the query never happened."""
    event = EventFactory(start_time_utc=BASE + HOUR)

    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        Client().get(f"/api/catalog/events/by-slug/{event.slug}")

    assert len(personal_queries) == 0, "the public page queried the personal schema: " + "; ".join(
        str(q["sql"]) for q in personal_queries
    )


def test_a_404_never_queries_the_personal_schema():
    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        Client().get("/api/catalog/events/by-slug/no-such-event")

    assert len(personal_queries) == 0


def test_the_response_sets_no_session_cookie():
    event = EventFactory(start_time_utc=BASE + HOUR)

    response = get_page(event.slug)

    assert "Set-Cookie" not in response.headers


def test_a_404_sets_no_session_cookie():
    response = get_page("no-such-event")

    assert "Set-Cookie" not in response.headers


def test_an_event_with_no_venue_resolves_and_carries_no_venue_facts():
    event = EventFactory(start_time_utc=BASE + HOUR, venue=None)

    response = get_page(event.slug)

    assert response.status_code == 200
    body = response.json()
    assert body["venue_name"] is None
    assert body["venue_address"] is None
    assert body["venue_city"] is None
    assert body["venue_country_code"] is None


def test_a_cancelled_event_still_resolves_and_says_so():
    """The page reports the status rather than hiding the event."""
    event = EventFactory(start_time_utc=BASE + HOUR, status=Event.Status.CANCELLED)

    response = get_page(event.slug)

    assert response.status_code == 200
    assert response.json()["status"] == Event.Status.CANCELLED


def test_the_slug_match_is_exact():
    """Two case variants would be two URLs for one page — a duplicate-URL fault."""
    event = EventFactory(start_time_utc=BASE + HOUR)

    response = get_page(event.slug.upper())

    assert response.status_code == 404


def test_the_response_never_carries_the_raw_source_payload():
    EventFactory(start_time_utc=BASE + HOUR, description="Stripped source text")

    body = get_page(EventFactory(start_time_utc=BASE + HOUR).slug).json()

    assert "payload" not in body
    assert "Stripped source text" not in str(body)


def test_the_endpoint_is_in_the_openapi_schema():
    schema = Client().get("/api/openapi.json").json()

    assert "/api/catalog/events/by-slug/{slug}" in schema["paths"]


def test_the_uuid_route_still_works():
    """The slug route is a new segment; it did not take the UUID one over."""
    event = EventFactory(start_time_utc=BASE + HOUR)

    response = Client().get(f"/api/catalog/events/{event.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(event.id)
