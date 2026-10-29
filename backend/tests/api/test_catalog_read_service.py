"""The published catalog read interface: what is visible, and in what order.

These test the service on its own, without the HTTP layer. The endpoint tests live in
test_catalog_api.py.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apps.ingestion.models import Event
from apps.ingestion.services.catalog_read import (
    EventNotFoundError,
    get_public_event,
    list_public_events,
)
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import EventFactory, VenueFactory, make_superseded_pair

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def at(hours: int) -> datetime:
    return NOW + timedelta(hours=hours)


def test_list_returns_only_upcoming_events():
    past = EventFactory(start_time_utc=NOW - HOUR)
    future = EventFactory(start_time_utc=NOW + HOUR)

    items, total = list_public_events(now=NOW)

    assert total == 1
    assert [item.id for item in items] == [future.id]
    assert past.id not in {item.id for item in items}


def test_event_starting_exactly_now_is_included():
    EventFactory(start_time_utc=NOW)

    items, total = list_public_events(now=NOW)

    assert total == 1
    assert len(items) == 1


def test_list_orders_by_start_time_then_id():
    first = EventFactory(start_time_utc=NOW + 2 * HOUR)
    second = EventFactory(start_time_utc=NOW + HOUR)
    third = EventFactory(start_time_utc=NOW + 2 * HOUR)

    items, _ = list_public_events(now=NOW)

    assert [item.id for item in items] == [second.id, first.id, third.id]


def test_events_sharing_a_start_time_are_ordered_by_id():
    """The tiebreak makes the order total, so pagination can't repeat or skip one.

    The two events are created in the opposite order to their ids, so a query that ordered
    by the start time alone would be at the database's discretion.
    """
    start = NOW + HOUR
    ids = sorted([uuid7(), uuid7()])
    for event_id in reversed(ids):
        EventFactory(id=event_id, start_time_utc=start)

    items, _ = list_public_events(now=NOW)

    assert [item.id for item in items] == ids


def test_events_sharing_a_start_time_survive_pagination():
    """A tiebreak the database may not apply would let one event fall on both pages."""
    start = NOW + HOUR
    ids = sorted([uuid7() for _ in range(4)])
    for event_id in reversed(ids):
        EventFactory(id=event_id, start_time_utc=start)

    page_one, total = list_public_events(now=NOW, page=1, page_size=2)
    page_two, _ = list_public_events(now=NOW, page=2, page_size=2)

    assert total == 4
    seen = [item.id for item in [*page_one, *page_two]]
    assert seen == ids
    assert len(seen) == len(set(seen))


def test_in_review_events_are_excluded():
    EventFactory(start_time_utc=NOW + HOUR, publication_status=Event.PublicationStatus.IN_REVIEW)

    items, total = list_public_events(now=NOW)

    assert total == 0
    assert items == []


def test_superseded_events_are_excluded_and_their_replacement_is_listed():
    old, new = make_superseded_pair(start_time_utc=NOW + HOUR)

    items, total = list_public_events(now=NOW)

    assert total == 1
    assert [item.id for item in items] == [new.id]
    assert old.id not in {item.id for item in items}


def test_tz_review_pending_event_is_listed_with_the_flag():
    EventFactory(start_time_utc=NOW + HOUR, tz_review_pending=True)

    items, total = list_public_events(now=NOW)

    assert total == 1
    assert items[0].tz_review_pending is True


def test_city_filter_matches_the_venue_city_case_insensitively():
    venue = VenueFactory(city="Los Angeles")
    EventFactory(start_time_utc=NOW + HOUR, venue=venue)
    EventFactory(start_time_utc=NOW + HOUR, venue=VenueFactory(city="Chicago"))

    items, total = list_public_events(now=NOW, city="los angeles")

    assert total == 1
    assert items[0].venue_city == "Los Angeles"


def test_city_filter_that_matches_nothing_returns_nothing():
    EventFactory(start_time_utc=NOW + HOUR)

    items, total = list_public_events(now=NOW, city="Nowhere")

    assert total == 0
    assert items == []


def test_event_without_a_venue_never_matches_a_city():
    EventFactory(start_time_utc=NOW + HOUR, venue=None)

    items, total = list_public_events(now=NOW, city="Los Angeles")

    assert total == 0
    assert items == []


def test_date_bounds_are_inclusive():
    inside = EventFactory(start_time_utc=NOW + 2 * HOUR)
    before = EventFactory(start_time_utc=NOW + HOUR)
    after = EventFactory(start_time_utc=NOW + 3 * HOUR)

    items, total = list_public_events(
        now=NOW, starts_after=NOW + 2 * HOUR, starts_before=NOW + 2 * HOUR
    )

    assert total == 1
    assert [item.id for item in items] == [inside.id]
    assert before.id not in {item.id for item in items}
    assert after.id not in {item.id for item in items}


def test_pagination_splits_without_repeats_or_skips():
    expected = []
    for index in range(5):
        expected.append(EventFactory(start_time_utc=NOW + (index + 1) * HOUR).id)

    page_one, total = list_public_events(now=NOW, page=1, page_size=2)
    page_two, _ = list_public_events(now=NOW, page=2, page_size=2)
    page_three, _ = list_public_events(now=NOW, page=3, page_size=2)

    assert total == 5
    seen = [item.id for item in [*page_one, *page_two, *page_three]]
    assert seen == expected


def test_page_beyond_the_end_is_empty():
    EventFactory(start_time_utc=NOW + HOUR)

    items, total = list_public_events(now=NOW, page=9, page_size=20)

    assert total == 1
    assert items == []


def test_page_size_is_capped():
    EventFactory(start_time_utc=NOW + HOUR)

    items, _ = list_public_events(now=NOW, page_size=10_000)

    assert len(items) == 1


def test_get_public_event_returns_the_event():
    event = EventFactory(start_time_utc=NOW + HOUR)

    found = get_public_event(event_id=event.id)

    assert found.id == event.id
    assert found.slug == event.slug
    assert found.title == event.title
    assert found.start_time_tz == event.start_time_tz
    assert found.source_name == event.source.name
    assert found.venue_name == event.venue.name
    assert found.venue_city == event.venue.city


def test_get_public_event_raises_not_found_for_an_in_review_event():
    event = EventFactory(
        start_time_utc=NOW + HOUR, publication_status=Event.PublicationStatus.IN_REVIEW
    )

    with pytest.raises(EventNotFoundError):
        get_public_event(event_id=event.id)


def test_get_public_event_raises_not_found_for_a_superseded_event():
    old, _ = make_superseded_pair(start_time_utc=NOW + HOUR)

    with pytest.raises(EventNotFoundError):
        get_public_event(event_id=old.id)


def test_get_public_event_raises_not_found_for_an_unknown_id():
    with pytest.raises(EventNotFoundError):
        get_public_event(event_id=uuid4())


def test_get_public_event_raises_not_found_for_an_event_that_has_started():
    """The `now` bound is the module's own documented rule: only *upcoming* events are visible."""
    event = EventFactory(start_time_utc=NOW - HOUR)

    with pytest.raises(EventNotFoundError):
        get_public_event(event_id=event.id, now=NOW)


def test_get_public_event_without_a_now_bound_returns_a_started_event():
    """A record of something already saved stays readable after the event has begun."""
    event = EventFactory(start_time_utc=NOW - HOUR)

    found = get_public_event(event_id=event.id)

    assert found.id == event.id


def test_public_event_carries_no_raw_source_payload():
    event = EventFactory(start_time_utc=NOW + HOUR, description="Stripped source text")

    found = get_public_event(event_id=event.id)

    assert not hasattr(found, "description")
    assert not hasattr(found, "payload")
