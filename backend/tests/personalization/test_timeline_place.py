"""The Timeline block's `place` (FR-32, EXPERIENCE.md §13).

**Why the block carries a place at all.** §13's density table says a desktop Timeline
event-block *adds* its location on hover and focus. The block could not: `TimelineBlockOut`
carried eight fields and none of them said where the event was. This is the server half —
the screen reveals what it is given and picks nothing.

**What is pinned here:**

- a public block carries its **venue's name**;
- it falls back to the **city** when the venue has no name;
- it is **null** when the catalog no longer holds the event — an *unknown* place, not an
  absent one, which is the same degradation `name` and `state` already make;
- a **personal** block carries the user's own location, and null when they gave none;
- the place is carried through the **per-day rebuild**, so a multi-day event has it on
  every day it covers;
- and the week read still makes **no query per block** — the place is free because the
  catalog batch already `select_related`s the venue, and a refactor that dropped that
  would be invisible without this assertion.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test.utils import CaptureQueriesContext

from apps.ingestion.models import Event
from apps.personalization.services.timeline import TimelineBlockKind, read_timeline_week
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import (
    DigestPreferenceFactory,
    PersonalEventFactory,
    SavedEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

TZ = "America/Los_Angeles"
WEDNESDAY = date(2026, 11, 4)


def local_midnight(day: date, zone: str = TZ) -> datetime:
    from datetime import UTC

    return datetime.combine(day, time.min).replace(tzinfo=ZoneInfo(zone)).astimezone(UTC)


START = local_midnight(WEDNESDAY) + timedelta(hours=17)


def make_user(email="place@example.test"):
    user = User.objects.create_user(email=email, password="pw")
    DigestPreferenceFactory(user_id=user.pk, timezone=TZ)
    return user


def blocks_for(user):
    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))
    return [block for day in week.days for block in day.blocks]


def save_a_public_event(user, *, venue_name="Barbican", city="London"):
    event = EventFactory(
        start_time_utc=START,
        end_time_utc=START + timedelta(hours=2),
        venue=VenueFactory(name=venue_name, city=city),
    )
    SavedEventFactory(
        user_id=user.pk,
        event_id=event.id,
        start_utc=START,
        end_utc=START + timedelta(hours=2),
        event_version=1,
    )
    return event


class TestAPublicBlock:
    def test_carries_the_venue_name(self):
        user = make_user()
        save_a_public_event(user)

        assert [b.place for b in blocks_for(user)] == ["Barbican"]

    def test_falls_back_to_the_city_when_the_venue_has_no_name(self):
        """A city tells a reader less than a venue, and more than nothing — the same
        fallback the Pulse Card makes."""
        user = make_user()
        save_a_public_event(user, venue_name="", city="London")

        assert [b.place for b in blocks_for(user)] == ["London"]

    def test_is_null_when_the_catalog_no_longer_holds_the_event(self):
        """An **unknown** place, not an absent one. The block is still drawn — the save is
        the user's own record and its snapshot still has a time."""
        user = make_user()
        event = save_a_public_event(user)
        # `get_public_events` returns only PUBLISHED, non-superseded events, so an
        # event moved back to review is one the catalog "no longer holds" for this read.
        Event.objects.using(CATALOG).filter(pk=event.id).update(
            publication_status=Event.PublicationStatus.IN_REVIEW
        )

        blocks = blocks_for(user)
        assert [b.kind for b in blocks] == [TimelineBlockKind.PUBLIC]
        assert blocks[0].place is None
        # The degradation matches the fields that already degrade this way.
        assert blocks[0].name is None


class TestAPersonalBlock:
    def test_carries_the_users_own_location(self):
        user = make_user()
        PersonalEventFactory(
            user_id=user.pk,
            name="Coffee with Sam",
            start_utc=START,
            end_utc=START + timedelta(hours=1),
            start_time_tz=TZ,
            location="Blue Bottle, Hayes Valley",
        )

        assert [b.place for b in blocks_for(user)] == ["Blue Bottle, Hayes Valley"]

    def test_is_null_when_they_gave_none(self):
        user = make_user()
        PersonalEventFactory(
            user_id=user.pk,
            name="Think",
            start_utc=START,
            end_utc=START + timedelta(hours=1),
            start_time_tz=TZ,
            location=None,
        )

        assert [b.place for b in blocks_for(user)] == [None]


class TestTheRebuild:
    def test_a_multi_day_event_keeps_its_place_on_every_day(self):
        """The per-day rebuild copies the block field by field, so a field added to the
        dataclass and not to that rebuild is silently dropped — invisibly, until a screen
        renders nothing."""
        user = make_user()
        start = local_midnight(WEDNESDAY) + timedelta(hours=22)
        event = EventFactory(
            start_time_utc=start,
            end_time_utc=start + timedelta(hours=6),  # across local midnight
            venue=VenueFactory(name="Barbican", city="London"),
        )
        SavedEventFactory(
            user_id=user.pk,
            event_id=event.id,
            start_utc=start,
            end_utc=start + timedelta(hours=6),
            event_version=1,
        )

        places = [b.place for b in blocks_for(user)]

        assert len(places) == 2, "the event covers two local days"
        assert places == ["Barbican", "Barbican"]


class TestTheCost:
    def test_the_place_adds_no_query_per_block(self):
        """The place is free because the catalog batch already `select_related`s the
        venue. A refactor that dropped that would add one query per saved event per
        week-read, and nothing else would notice."""
        user = make_user()
        for index in range(4):
            save_a_public_event(user, venue_name=f"Venue {index}", city="London")

        with (
            CaptureQueriesContext(connections[PERSONAL]) as personal,
            CaptureQueriesContext(connections[CATALOG]) as catalog,
        ):
            blocks = blocks_for(user)

        assert len(blocks) == 4
        assert all(b.place is not None for b in blocks)
        # The catalog is read once for the whole week, whatever the number of saves.
        assert len(catalog.captured_queries) <= 2, catalog.captured_queries
        assert len(personal.captured_queries) <= 8, personal.captured_queries
