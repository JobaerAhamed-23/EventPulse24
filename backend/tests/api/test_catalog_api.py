"""The public catalog endpoints: `GET /api/catalog/events` and `.../events/{id}`.

The AC's list: ordering and pagination, filters, `in_review` and superseded excluded, a
`tz_review_pending` event included with the flag, the 404 shape, an anonymous request
succeeding, and no `Set-Cookie` session header.

The endpoint lists everything that has not started yet, so a test's own events are always
in the list along with any other test's. Assertions therefore count *this test's* events
and check their order and membership, never a bare total that depends on the rest of the
suite. The one exception is a test that needs an exact total, and it uses a city no other
test uses.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.test import Client
from django.utils import timezone

from apps.ingestion.models import Event
from shared.db import CATALOG, PERSONAL
from shared.errors import ErrorOut
from tests.ingestion.factories import EventFactory, VenueFactory, make_superseded_pair

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

HOUR = timedelta(hours=1)
# Far enough ahead that a test's events are always "upcoming" for the endpoint, which
# bounds the list by the real now.
BASE = timezone.now() + timedelta(days=30)


def get_list(**params):
    return Client().get("/api/catalog/events", params)


def get_event(event_id):
    return Client().get(f"/api/catalog/events/{event_id}")


def ids_of(items):
    return [item["id"] for item in items]


def test_list_returns_the_public_events_in_start_order():
    later = EventFactory(start_time_utc=BASE + 2 * HOUR)
    sooner = EventFactory(start_time_utc=BASE + HOUR)

    body = get_list().json()

    listed = ids_of(body["items"])
    assert listed.index(str(sooner.id)) < listed.index(str(later.id))


def test_list_body_carries_the_response_schema():
    event = EventFactory(start_time_utc=BASE + HOUR)

    body = get_list().json()

    item = next(entry for entry in body["items"] if entry["id"] == str(event.id))
    assert set(item) == {
        "id",
        "slug",
        "title",
        "canonical_url",
        "start_time_utc",
        "start_time_tz",
        "end_time_utc",
        "venue_name",
        "venue_city",
        "status",
        "event_version",
        "source_name",
        "tz_review_pending",
    }
    assert item["title"] == event.title
    assert item["slug"] == event.slug
    assert item["canonical_url"] == event.canonical_url
    assert item["start_time_tz"] == event.start_time_tz
    assert item["venue_name"] == event.venue.name
    assert item["venue_city"] == event.venue.city
    assert item["status"] == Event.Status.SCHEDULED
    assert item["event_version"] == 1
    assert item["source_name"] == event.source.name
    assert item["tz_review_pending"] is False


def test_list_response_never_carries_the_raw_source_payload():
    EventFactory(start_time_utc=BASE + HOUR, description="Stripped source text")

    body = get_list().json()

    assert "description" not in body["items"][0]
    assert "payload" not in body["items"][0]
    assert "Stripped source text" not in str(body)


def test_list_pagination_reports_the_total_and_has_next():
    for index in range(3):
        EventFactory(start_time_utc=BASE + (index + 1) * HOUR)

    body = get_list(page_size=2).json()

    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total"] >= 3
    assert body["has_next"] is True
    assert len(body["items"]) == 2


def test_list_last_page_has_no_next():
    for index in range(2):
        EventFactory(start_time_utc=BASE + (index + 1) * HOUR)

    body = get_list(page_size=2).json()

    assert body["has_next"] is False


def test_list_pages_do_not_repeat_or_skip():
    expected = [
        str(EventFactory(start_time_utc=BASE + (index + 1) * HOUR).id) for index in range(5)
    ]

    seen = []
    for page in (1, 2, 3):
        body = get_list(page=page, page_size=2).json()
        seen += ids_of(body["items"])

    # Every event this test created appears exactly once across the three pages.
    assert sorted(event_id for event_id in seen if event_id in expected) == sorted(expected)
    assert len(seen) == len(set(seen))


def test_list_city_filter():
    city = "Filtertown"
    venue = VenueFactory(city=city)
    EventFactory(start_time_utc=BASE + HOUR, venue=venue)

    body = get_list(city=city).json()

    assert body["total"] == 1
    assert body["items"][0]["venue_city"] == city


def test_list_city_filter_ignores_the_case():
    city = "Casetown"
    venue = VenueFactory(city=city)
    EventFactory(start_time_utc=BASE + HOUR, venue=venue)

    body = get_list(city=city.lower()).json()

    assert body["total"] == 1
    assert body["items"][0]["venue_city"] == city


def test_list_date_range_filter():
    inside = EventFactory(start_time_utc=BASE + 2 * HOUR)
    EventFactory(start_time_utc=BASE + 4 * HOUR)

    body = get_list(
        starts_after=(BASE + 2 * HOUR).isoformat(), starts_before=(BASE + 2 * HOUR).isoformat()
    ).json()

    assert ids_of(body["items"]) == [str(inside.id)]


def test_list_excludes_in_review_events():
    event = EventFactory(
        start_time_utc=BASE + HOUR, publication_status=Event.PublicationStatus.IN_REVIEW
    )

    body = get_list().json()

    assert str(event.id) not in ids_of(body["items"])


def test_list_excludes_superseded_events_and_lists_the_replacement():
    old, new = make_superseded_pair(start_time_utc=BASE + HOUR)

    body = get_list().json()

    listed = ids_of(body["items"])
    assert str(old.id) not in listed
    assert str(new.id) in listed


def test_list_includes_a_tz_review_pending_event_with_the_flag():
    event = EventFactory(start_time_utc=BASE + HOUR, tz_review_pending=True)

    body = get_list().json()

    item = next(entry for entry in body["items"] if entry["id"] == str(event.id))
    assert item["tz_review_pending"] is True


def test_list_excludes_events_that_already_started():
    event = EventFactory(start_time_utc=timezone.now() - HOUR)

    body = get_list().json()

    assert str(event.id) not in ids_of(body["items"])


def test_get_event_returns_the_event():
    event = EventFactory(start_time_utc=BASE + HOUR)

    response = get_event(event.id)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(event.id)
    assert body["title"] == event.title
    assert body["slug"] == event.slug


def test_get_event_returns_the_shared_not_found_shape():
    response = get_event(uuid4())

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert body["message"] == "We couldn't find that event."
    ErrorOut.model_validate(body)


def test_get_event_for_an_in_review_event_is_not_found():
    event = EventFactory(
        start_time_utc=BASE + HOUR, publication_status=Event.PublicationStatus.IN_REVIEW
    )

    response = get_event(event.id)

    assert response.status_code == 404


def test_get_event_for_a_superseded_event_is_not_found():
    old, _ = make_superseded_pair(start_time_utc=BASE + HOUR)

    response = get_event(old.id)

    assert response.status_code == 404


def test_get_event_for_an_event_that_has_already_started_is_not_found():
    """The detail shows the same set the list does: published, not superseded, not started."""
    event = EventFactory(start_time_utc=timezone.now() - HOUR)

    response = get_event(event.id)

    assert response.status_code == 404


def test_anonymous_request_succeeds_without_signing_in():
    event = EventFactory(start_time_utc=BASE + HOUR)

    response = Client().get("/api/catalog/events")

    assert response.status_code == 200
    assert str(event.id) in ids_of(response.json()["items"])


def test_neither_endpoint_sets_a_session_cookie():
    event = EventFactory(start_time_utc=BASE + HOUR)

    list_response = Client().get("/api/catalog/events")
    event_response = Client().get(f"/api/catalog/events/{event.id}")

    assert "Set-Cookie" not in list_response.headers
    assert "Set-Cookie" not in event_response.headers


def test_a_404_sets_no_session_cookie():
    response = Client().get(f"/api/catalog/events/{uuid4()}")

    assert "Set-Cookie" not in response.headers


def test_the_endpoints_are_in_the_openapi_schema():
    schema = Client().get("/api/openapi.json").json()

    assert "/api/catalog/events" in schema["paths"]
    assert "/api/catalog/events/{event_id}" in schema["paths"]
