"""The Timeline week read — one week, day by day, conflicts decided (FR-32, FR-33).

`ConflictPair`'s own docstring says the Pulse Card indicator, the Timeline indicator and
`/conflicts` all read the pair rows — so these tests pin what the Timeline's read has to
give back.

**What is pinned here:**

- **The day arithmetic** (pure, no database): a week is Monday to Sunday; the bounds are
  the local midnights, so a DST week is not 168 hours; an event at 23:30 local is on that
  local day; a cross-midnight event covers both days it spans; an open-ended event covers
  every day from its start.
- **The service**: seven days for an empty week; the personal events and the saved events,
  merged; a public block carries the **catalog** event's id; a save whose catalog event
  disappeared has no title and is still shown; the indicator is true for both sides of an
  active pair and **stays true after `keep_both`**; it is false after every other
  resolution; the indicator repeats on each day-cell a multi-day event spans.
- **The bounds**: the query count does not grow with the number of events, and the read is
  scoped to the caller.
- **The endpoint**: the response names the week's Monday and Sunday and returns seven
  days; a missing `week` means the current week in the user's zone; a malformed `week` is
  a 422; an anonymous caller is a 401.
"""

from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test.utils import CaptureQueriesContext

from apps.personalization.models import ConflictPair, DigestPreference
from apps.personalization.services.timeline import TimelineBlockKind, read_timeline_week
from apps.personalization.services.timeline_days import (
    DAYS_IN_WEEK,
    day_bounds,
    days_covered,
    local_date_at,
    overlaps_day,
    week_bounds,
    week_days,
    week_start_for,
)
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.ingestion.factories import EventFactory
from tests.personalization.factories import (
    ConflictPairFactory,
    DigestPreferenceFactory,
    PersonalEventFactory,
    SavedEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

TZ = "America/Los_Angeles"
HOUR = timedelta(hours=1)

#: 2026-11-04 is a Wednesday. The week around it runs Monday 2026-11-02 to Sunday
#: 2026-11-08.
WEDNESDAY = date(2026, 11, 4)
MONDAY = date(2026, 11, 2)
SUNDAY = date(2026, 11, 8)


def make_user(email="sam@example.test"):
    """A real user with a real pk — the session resolves to this one.

    **The user has a digest preference in `TZ`.** The days are cut in the user's zone, and
    the fixtures are written in `TZ`'s wall clock — so a user with no preference (and so
    no zone, and so UTC) would have its Wednesday-afternoon fixtures land on Thursday.
    The zone is part of the user's calendar, not an accident of the test.
    """
    user = User.objects.create_user(email=email, password="pw")
    DigestPreferenceFactory(user_id=user.pk, timezone=TZ)
    return user


def in_zone(user, zone: str):
    """Put the user's calendar in another zone.

    The preference is one row per user, so this **updates** the row the factory wrote
    rather than adding a second one — two rows would make "the user's zone" ambiguous,
    and the read takes the last one.
    """
    DigestPreference.objects.using(PERSONAL).filter(user_id=user.pk).update(timezone=zone)


def signed_in(user=None):
    """A client whose session identifies `user`."""
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


def local_midnight(day: date, zone: str = TZ) -> datetime:
    """The UTC instant of a local midnight, for building test fixtures."""
    return datetime.combine(day, time.min).replace(tzinfo=ZoneInfo(zone)).astimezone(UTC)


#: The sentinel for "no end" — `None` is the *value* an open-ended event has, and the
#: factory's own default is a two-hour event, so the two cannot be told apart by `None`.
NO_END = object()


def personal_event(user, *, name="Coffee with Sam", start=None, end=None, tz=TZ):
    """A personal event on the user's calendar.

    `end=NO_END` makes an **open-ended** event — one with no end at all. `end=None` means
    "the default", a two-hour event, because `None` is what the factory's own default
    means, and an event's real "no end" has to be said differently.
    """
    start = start or local_midnight(WEDNESDAY) + timedelta(hours=17)
    end_utc = None if end is NO_END else (end or start + timedelta(hours=2))
    return PersonalEventFactory(
        user_id=user.pk,
        name=name,
        start_utc=start,
        end_utc=end_utc,
        start_time_tz=tz,
    )


def saved_event(user, *, event=None, start=None, end=None):
    """A save of a public catalog event, with the catalog event behind it."""
    start = start or local_midnight(WEDNESDAY) + timedelta(hours=17)
    if event is None:
        event = EventFactory(start_time_utc=start, end_time_utc=start + timedelta(hours=2))
    saved = SavedEventFactory(
        user_id=user.pk,
        event_id=event.id,
        start_utc=start,
        end_utc=end if end is not None else start + timedelta(hours=2),
        event_version=1,
    )
    return saved, event


def pair(user, *, left_kind, left_id, right_kind, right_id, kind="time", **extra):
    """A conflict pair for the user, with the sides in the row's normalised order.

    The row is normalised on `(kind, id)`, so the test sorts the sides the same way the
    command layer does — otherwise the factory writes a row the unique constraint would
    reject.
    """
    sides = sorted(
        [(left_kind, left_id), (right_kind, right_id)],
        key=lambda side: (side[0], str(side[1])),
    )
    return ConflictPairFactory(
        user_id=user.pk,
        kind=kind,
        left_kind=sides[0][0],
        left_id=sides[0][1],
        right_kind=sides[1][0],
        right_id=sides[1][1],
        **extra,
    )


def blocks_on(week, day):
    """The blocks of one day of a read week, by name."""
    return {block.name for cell in week.days if cell.date == day for block in cell.blocks}


# --- The pure day arithmetic ------------------------------------------------------------------


def test_a_week_is_monday_to_sunday_and_a_mid_week_date_selects_the_week_around_it():
    """The week starts on Monday, and any date in it names that week.

    The user's week is Monday to Sunday in every locale this product supports, and the
    week's grid is Mon–Sun — so a Wednesday names the Monday-to-Sunday week around it.
    """
    assert week_start_for(day=WEDNESDAY, zone_name=TZ) == MONDAY
    assert week_start_for(day=MONDAY, zone_name=TZ) == MONDAY
    assert week_start_for(day=SUNDAY, zone_name=TZ) == MONDAY

    assert week_days(day=WEDNESDAY, zone_name=TZ) == (
        date(2026, 11, 2),
        date(2026, 11, 3),
        date(2026, 11, 4),
        date(2026, 11, 5),
        date(2026, 11, 6),
        date(2026, 11, 7),
        date(2026, 11, 8),
    )
    assert len(week_days(day=WEDNESDAY, zone_name=TZ)) == DAYS_IN_WEEK


def test_the_week_bounds_are_the_local_midnights_and_a_dst_week_is_not_168_hours():
    """A week is cut at local midnight, so a DST week is 167 or 169 hours — never 168.

    Computing the bounds by adding 24 hours to a UTC instant would put the boundary on the
    wrong side of the transition, and an event at 23:30 local would land on the wrong day.
    """
    start, end = week_bounds(day=date(2026, 11, 2), zone_name=TZ)

    # A plain week — no transition inside it — is the ordinary 168 hours.
    assert start == local_midnight(MONDAY)
    assert end == local_midnight(date(2026, 11, 9))
    assert (end - start) == timedelta(hours=168)

    # The US DST start is 2027-03-14 (a Sunday). The week that *contains* the transition is
    # Mon 2027-03-08 to Sun 2027-03-14 — and it loses an hour, because the clock skips
    # from 02:00 to 03:00 on the Sunday morning.
    spring_start, spring_end = week_bounds(day=date(2027, 3, 10), zone_name=TZ)
    assert spring_start == local_midnight(date(2027, 3, 8))
    assert spring_end == local_midnight(date(2027, 3, 15))
    assert (spring_end - spring_start).total_seconds() / 3600 == 167

    # The US DST end is 2026-11-01 (a Sunday), so the week containing it is Mon 2026-10-26
    # to Sun 2026-11-01 — and it gains an hour, because the clock goes back from 02:00 to
    # 01:00 on the Sunday morning.
    fall_start, fall_end = week_bounds(day=date(2026, 10, 28), zone_name=TZ)
    assert fall_start == local_midnight(date(2026, 10, 26))
    assert fall_end == local_midnight(date(2026, 11, 2))
    assert (fall_end - fall_start).total_seconds() / 3600 == 169


def test_an_event_at_23_30_local_is_on_that_local_day():
    """A late-evening event is on the day it starts, in the user's zone.

    23:30 local on Friday is Friday's block, whatever UTC says about that instant — and
    the same wall clock in Los Angeles is a different instant in UTC. The event runs to
    00:30, so it *touches* Saturday too; Friday is still the day it starts on.
    """
    # 2026-11-06 23:30 in Los Angeles (PST) is 2026-11-07 07:30 UTC — the next UTC day.
    instant = datetime(2026, 11, 7, 7, 30, tzinfo=UTC)

    assert local_date_at(instant=instant, zone_name=TZ) == date(2026, 11, 6)

    # An event that ends before midnight touches only Friday.
    covered = days_covered(
        start_utc=instant,
        end_utc=datetime(2026, 11, 7, 7, 45, tzinfo=UTC),
        zone_name=TZ,
    )
    assert covered == (date(2026, 11, 6),)

    # One that runs past midnight touches Friday *and* Saturday.
    covered = days_covered(
        start_utc=instant,
        end_utc=datetime(2026, 11, 7, 8, 30, tzinfo=UTC),
        zone_name=TZ,
    )
    assert covered == (date(2026, 11, 6), date(2026, 11, 7))


def test_a_cross_midnight_event_covers_both_days_it_spans():
    """An event running past midnight appears on each day it covers.

    A block from Friday 22:00 to Saturday 02:00 is a Friday block *and* a Saturday block.
    """
    friday_evening = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)  # Friday 22:00 PST
    saturday_morning = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)  # Saturday 02:00 PST

    covered = days_covered(
        start_utc=friday_evening,
        end_utc=saturday_morning,
        zone_name=TZ,
    )
    assert covered == (date(2026, 11, 6), date(2026, 11, 7))


def test_an_open_ended_event_covers_every_day_from_its_start():
    """An event with no end covers every day from its start onward.

    It has no end to convert, so the range runs to the limit — and the caller passes the
    week's last day, so an open-ended event cannot make the caller build a list of dates
    from 1970 to the end of time.
    """
    wednesday = local_midnight(WEDNESDAY) + timedelta(hours=9)

    covered = days_covered(
        start_utc=wednesday,
        end_utc=None,
        zone_name=TZ,
        limit=SUNDAY,
    )
    assert covered == (
        date(2026, 11, 4),
        date(2026, 11, 5),
        date(2026, 11, 6),
        date(2026, 11, 7),
        date(2026, 11, 8),
    )


def test_an_unknown_zone_falls_back_to_utc_rather_than_raising():
    """A hand-edited zone name must not take the user's timeline away.

    The zone is validated at write time by the onboarding command, so an unknown name
    means hand-edited data — not that the timeline should fail. The failure mode is a
    wrong day, not a missing week.
    """
    instant = datetime(2026, 11, 7, 7, 30, tzinfo=UTC)

    assert local_date_at(instant=instant, zone_name="Not/AZone") == date(2026, 11, 7)
    assert local_date_at(instant=instant, zone_name="Not/AZone") == local_date_at(
        instant=instant, zone_name="UTC"
    )


def test_an_event_whose_end_precedes_its_start_covers_the_day_it_starts():
    """Malformed data is not a week-long event.

    The end precedes the start, so the range would be empty — and an event that covers no
    day would be an event the user cannot see. It covers the day it starts.

    The end has to be on an **earlier day** for the range to be empty: an end earlier on
    the *same* day still lands on that day's date, so the range is one day either way.
    """
    start = local_midnight(WEDNESDAY) + timedelta(hours=9)

    covered = days_covered(
        start_utc=start,
        end_utc=local_midnight(date(2026, 11, 3)) + timedelta(hours=9),
        zone_name=TZ,
    )
    assert covered == (WEDNESDAY,)


def test_a_limit_before_the_first_day_covers_nothing():
    """An event that starts after the week's last day is on no day of that week."""
    wednesday = local_midnight(WEDNESDAY) + timedelta(hours=9)

    covered = days_covered(
        start_utc=wednesday,
        end_utc=wednesday + timedelta(hours=1),
        zone_name=TZ,
        limit=date(2026, 11, 3),  # before the event's own day
    )
    assert covered == ()


def test_an_open_ended_event_overlaps_every_day_from_its_start():
    """An open-ended event overlaps a day when it started at or before that day's end.

    It has no end, so it runs onward — and the day's own interval is what the test is made
    against.
    """
    wednesday = local_midnight(WEDNESDAY) + timedelta(hours=9)

    assert overlaps_day(
        start_utc=wednesday,
        end_utc=None,
        local_date=WEDNESDAY,
        zone_name=TZ,
    )
    assert overlaps_day(
        start_utc=wednesday,
        end_utc=None,
        local_date=SUNDAY,
        zone_name=TZ,
    )
    # A day that ended before the event started does not overlap it.
    assert not overlaps_day(
        start_utc=wednesday,
        end_utc=None,
        local_date=date(2026, 11, 3),
        zone_name=TZ,
    )


def test_a_zero_length_event_covers_one_day():
    """An event that starts and ends at the same instant covers exactly one day.

    And an event that ends exactly at midnight belongs to the day it *started*: the end
    instant is exclusive, so the range would otherwise include a day the event does not
    touch.
    """
    friday_evening = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)  # Friday 22:00 PST
    saturday_midnight = datetime(2026, 11, 7, 8, 0, tzinfo=UTC)  # Saturday 00:00 PST

    assert days_covered(
        start_utc=friday_evening,
        end_utc=friday_evening,
        zone_name=TZ,
    ) == (date(2026, 11, 6),)

    assert days_covered(
        start_utc=friday_evening,
        end_utc=saturday_midnight,
        zone_name=TZ,
    ) == (date(2026, 11, 6),)


def test_the_days_are_the_users_zone_and_not_the_servers():
    """The same instant is a different local day in a different zone.

    2026-11-07 02:00 UTC is still Friday in Los Angeles and already Saturday in Berlin —
    so a user in Berlin and a user in Los Angeles get different days out of the same
    event.
    """
    instant = datetime(2026, 11, 7, 2, 0, tzinfo=UTC)

    assert local_date_at(instant=instant, zone_name="America/Los_Angeles") == date(2026, 11, 6)
    assert local_date_at(instant=instant, zone_name="Europe/Berlin") == date(2026, 11, 7)


def test_the_overlap_test_is_against_the_days_own_interval():
    """A block overlaps a day when it touches that day's interval.

    The day-cell's own interval is what the test is made against, so a conflict that falls
    on Saturday lights Saturday's cell even though the event starts on Friday.
    """
    friday_evening = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)  # Friday 22:00 PST
    saturday_morning = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)  # Saturday 02:00 PST

    assert overlaps_day(
        start_utc=friday_evening,
        end_utc=saturday_morning,
        local_date=date(2026, 11, 6),
        zone_name=TZ,
    )
    assert overlaps_day(
        start_utc=friday_evening,
        end_utc=saturday_morning,
        local_date=date(2026, 11, 7),
        zone_name=TZ,
    )
    assert not overlaps_day(
        start_utc=friday_evening,
        end_utc=saturday_morning,
        local_date=date(2026, 11, 8),
        zone_name=TZ,
    )


def test_the_day_bounds_are_the_local_midnights_with_an_exclusive_end():
    """A day's bounds are its local midnights, and the end is exclusive.

    The end is the next local midnight, so a day is 23, 24 or 25 hours long depending on
    the transition — and the arithmetic never assumes which.
    """
    start, end = day_bounds(local_date=date(2026, 11, 6), zone_name=TZ)

    assert start == datetime(2026, 11, 6, 8, 0, tzinfo=UTC)  # 00:00 PST
    assert end == datetime(2026, 11, 7, 8, 0, tzinfo=UTC)  # 00:00 PST the next day
    assert (end - start) == timedelta(hours=24)


# --- The service -------------------------------------------------------------------------------


def test_the_seven_days_are_returned_for_an_empty_week():
    """An empty week still has seven day cells.

    The screen draws seven columns, so it must not have to know whether the week has
    anything in it.
    """
    user = make_user()

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    assert len(week.days) == DAYS_IN_WEEK
    assert [day.date for day in week.days] == list(week_days(day=WEDNESDAY, zone_name=TZ))
    assert all(day.blocks == () for day in week.days)


def test_the_blocks_are_the_personal_events_and_the_saved_events_merged():
    """Both kinds of event appear, on the day they start."""
    user = make_user()
    personal_event(user, name="Coffee with Sam")
    saved_event(user)

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    wednesday = next(day for day in week.days if day.date == WEDNESDAY)
    kinds = {block.kind for block in wednesday.blocks}
    assert kinds == {TimelineBlockKind.PERSONAL, TimelineBlockKind.PUBLIC}
    assert len(wednesday.blocks) == 2


def test_a_public_block_carries_the_catalog_event_id_and_the_catalog_title():
    """A public block names the **catalog** event, so the screen can route to it.

    The save row's id is the user's own record; the id the screen acts on is the catalog
    event's, because the screen routes to `/events/:id`.
    """
    user = make_user()
    saved, public = saved_event(user)

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    wednesday = next(day for day in week.days if day.date == WEDNESDAY)
    block = next(b for b in wednesday.blocks if b.kind == TimelineBlockKind.PUBLIC)
    assert block.id == public.id
    assert block.id != saved.id
    assert block.name == public.title


def test_a_save_whose_catalog_event_disappeared_has_no_title_and_is_still_shown():
    """The save is the user's own record, so the block is still drawn.

    Its snapshot still has a time — so the block has a place on the week — but the catalog
    no longer holds the event, so there is no title to give.
    """
    user = make_user()
    saved = SavedEventFactory(
        user_id=user.pk,
        event_id=uuid4(),  # a catalog event that was never there
        start_utc=local_midnight(WEDNESDAY) + timedelta(hours=17),
        end_utc=local_midnight(WEDNESDAY) + timedelta(hours=19),
        event_version=1,
    )

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    wednesday = next(day for day in week.days if day.date == WEDNESDAY)
    block = next(b for b in wednesday.blocks if b.kind == TimelineBlockKind.PUBLIC)
    assert block.id == saved.event_id
    assert block.name is None
    assert block.start_time_utc == saved.start_utc


def test_the_indicator_is_true_for_both_sides_of_an_active_pair():
    """An active pair flags both of its sides."""
    user = make_user()
    first = personal_event(user, name="Coffee with Sam")
    second = personal_event(
        user,
        name="Coffee with Alex",
        start=local_midnight(WEDNESDAY) + timedelta(hours=18),
    )
    pair(
        user,
        left_kind="personal_event",
        left_id=first.id,
        right_kind="personal_event",
        right_id=second.id,
    )

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    wednesday = next(day for day in week.days if day.date == WEDNESDAY)
    assert all(block.conflict for block in wednesday.blocks)


def test_the_indicator_is_still_true_after_keep_both():
    """FR-58: "Keep both" leaves a permanent, calm reminder on both events.

    This is the rule no existing projection implements — the digest's card projection and
    the digest's candidate projection are both active-only, which is right for a card
    showing *open* conflicts and wrong for a timeline block.
    """
    user = make_user()
    first = personal_event(user, name="Coffee with Sam")
    second = personal_event(
        user,
        name="Coffee with Alex",
        start=local_midnight(WEDNESDAY) + timedelta(hours=18),
    )
    pair(
        user,
        left_kind="personal_event",
        left_id=first.id,
        right_kind="personal_event",
        right_id=second.id,
        status=ConflictPair.Status.RESOLVED,
        resolution=ConflictPair.Resolution.KEEP_BOTH,
        resolved_at=local_midnight(WEDNESDAY),
    )

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    wednesday = next(day for day in week.days if day.date == WEDNESDAY)
    assert all(block.conflict for block in wednesday.blocks)


@pytest.mark.parametrize(
    "kind,resolution",
    [
        ("time", ConflictPair.Resolution.EDIT_NEW),
        ("time", ConflictPair.Resolution.DELETE_NEW),
        ("duplicate", ConflictPair.Resolution.UPDATE_EXISTING),
        ("time", ConflictPair.Resolution.SKIP_PUBLIC),
    ],
)
def test_the_indicator_is_false_after_every_other_resolution(kind, resolution):
    """Every resolution other than "Keep both" removes the reminder.

    The conflict the user was reminded about is gone, so the indicator goes with it.

    **Each resolution is paired with a kind that allows it.** The model's CHECK constraint
    refuses `update_existing` on a time pair and `edit_new` on a duplicate pair, so
    asking for one against the wrong kind would be refused by the database before the
    indicator was ever read.
    """
    user = make_user()
    first = personal_event(user, name="Coffee with Sam")
    second = personal_event(
        user,
        name="Coffee with Alex",
        start=local_midnight(WEDNESDAY) + timedelta(hours=18),
    )
    pair(
        user,
        left_kind="personal_event",
        left_id=first.id,
        right_kind="personal_event",
        right_id=second.id,
        kind=kind,
        status=ConflictPair.Status.RESOLVED,
        resolution=resolution,
        resolved_at=local_midnight(WEDNESDAY),
    )

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    wednesday = next(day for day in week.days if day.date == WEDNESDAY)
    assert not any(block.conflict for block in wednesday.blocks)


def test_the_indicator_is_true_for_the_saved_side_of_a_pair():
    """A pair's saved side carries the indicator too.

    The pair names the **save row's** id and the public block carries the **catalog**
    event's id — and the bridge between them is the save row. A pair whose sides are a
    personal event and a save lights both blocks.
    """
    user = make_user()
    event = personal_event(user, name="Coffee with Sam")
    saved, _ = saved_event(user, start=local_midnight(WEDNESDAY) + timedelta(hours=18))
    pair(
        user,
        left_kind="personal_event",
        left_id=event.id,
        right_kind="saved_event",
        right_id=saved.id,
    )

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    wednesday = next(day for day in week.days if day.date == WEDNESDAY)
    assert all(block.conflict for block in wednesday.blocks)


def test_the_indicator_follows_a_duplicate_pair_onto_the_day_the_duplicate_sits():
    """A duplicate pair's window is the span of its two sides.

    The two sides are the *same event* twice — the same name, with starts within 24 hours
    — so there is no overlap to intersect. The window is the span they share, and the
    indicator lands on the day the duplicate actually sits rather than on a day neither
    side touches.
    """
    user = make_user()
    first = personal_event(
        user,
        name="Poetry reading",
        start=local_midnight(WEDNESDAY) + timedelta(hours=9),
    )
    second = personal_event(
        user,
        name="Poetry reading",
        start=local_midnight(WEDNESDAY) + timedelta(hours=10),
    )
    pair(
        user,
        left_kind="personal_event",
        left_id=first.id,
        right_kind="personal_event",
        right_id=second.id,
        kind="duplicate",
    )

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    wednesday = next(day for day in week.days if day.date == WEDNESDAY)
    thursday = next(day for day in week.days if day.date == date(2026, 11, 5))
    # The duplicate sits on Wednesday, so Wednesday's cell is the one that lights.
    assert all(block.conflict for block in wednesday.blocks)
    assert thursday.blocks == ()


def test_the_indicator_is_false_for_a_cleared_by_state_change_pair():
    """A pair closed by a state change was never answered by the user.

    Nobody chose it, and the side that caused it went away — so it carries no reminder.
    """
    user = make_user()
    first = personal_event(user, name="Coffee with Sam")
    second = personal_event(
        user,
        name="Coffee with Alex",
        start=local_midnight(WEDNESDAY) + timedelta(hours=18),
    )
    pair(
        user,
        left_kind="personal_event",
        left_id=first.id,
        right_kind="personal_event",
        right_id=second.id,
        status=ConflictPair.Status.CLEARED_BY_STATE_CHANGE,
        resolved_at=local_midnight(WEDNESDAY),
    )

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    wednesday = next(day for day in week.days if day.date == WEDNESDAY)
    assert not any(block.conflict for block in wednesday.blocks)


def test_the_indicator_repeats_on_each_day_cell_a_multi_day_event_spans():
    """FR-33 (e): the indicator fires on every day-cell the event spans.

    The conflict falls on Saturday — the second day of a Friday-to-Saturday event — so
    Saturday's cell is the one that lights up, and Friday's does not, because the overlap
    the pair records is not on Friday's interval.
    """
    user = make_user()
    friday = date(2026, 11, 6)
    saturday = date(2026, 11, 7)

    friday_evening = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)  # Friday 22:00 PST
    saturday_morning = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)  # Saturday 02:00 PST

    first = personal_event(
        user,
        name="Late shift",
        start=friday_evening,
        end=saturday_morning,
    )
    second = personal_event(
        user,
        name="Early breakfast",
        start=datetime(2026, 11, 7, 9, 0, tzinfo=UTC),  # Saturday 01:00 PST
        end=datetime(2026, 11, 7, 10, 0, tzinfo=UTC),
    )
    pair(
        user,
        left_kind="personal_event",
        left_id=first.id,
        right_kind="personal_event",
        right_id=second.id,
    )

    week = read_timeline_week(user_id=user.pk, day=friday, now=local_midnight(friday))

    friday_cell = next(day for day in week.days if day.date == friday)
    saturday_cell = next(day for day in week.days if day.date == saturday)

    # The block is on both days — it covers them.
    assert {b.name for b in friday_cell.blocks} == {"Late shift"}
    assert {b.name for b in saturday_cell.blocks} == {"Late shift", "Early breakfast"}

    # The indicator is on the cell whose interval contains the overlap.
    assert next(b for b in saturday_cell.blocks if b.name == "Late shift").conflict
    assert not next(b for b in friday_cell.blocks if b.name == "Late shift").conflict


def test_a_cross_midnight_event_appears_on_each_day_it_covers():
    """An event running past midnight appears on each day it covers."""
    user = make_user()
    friday_evening = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)  # Friday 22:00 PST
    saturday_morning = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)  # Saturday 02:00 PST
    personal_event(user, name="Late shift", start=friday_evening, end=saturday_morning)

    week = read_timeline_week(user_id=user.pk, day=date(2026, 11, 6), now=local_midnight(MONDAY))

    assert "Late shift" in blocks_on(week, date(2026, 11, 6))
    assert "Late shift" in blocks_on(week, date(2026, 11, 7))


def test_an_event_that_started_before_the_week_still_appears_on_the_day_it_covers():
    """The read is **overlap**-bounded, not start-bounded.

    An event that started on the Sunday before the week and runs into Monday is a block on
    Monday's cell — and a start-bounded read excludes it. The same goes for an open-ended
    event: it has no end, so it runs from its start onward and covers every day after it.
    """
    user = make_user()
    sunday_evening = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)  # Sunday 22:00 PST
    monday_morning = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)  # Monday 02:00 PST
    personal_event(user, name="Overnight", start=sunday_evening, end=monday_morning)

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    assert "Overnight" in blocks_on(week, MONDAY)


def test_an_open_ended_event_appears_on_every_day_of_the_week_from_its_start():
    """An event with no end appears on every day of the week from its start."""
    user = make_user()
    personal_event(
        user,
        name="Ongoing",
        start=local_midnight(WEDNESDAY) + timedelta(hours=9),
        end=NO_END,
    )

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    for day in (WEDNESDAY, date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 7), SUNDAY):
        assert "Ongoing" in blocks_on(week, day)
    assert "Ongoing" not in blocks_on(week, MONDAY)
    assert "Ongoing" not in blocks_on(week, date(2026, 11, 3))


def test_the_indicator_follows_the_pairs_overlap_and_not_the_blocks_own_span():
    """The indicator fires on the day-cell whose interval contains the **overlap**.

    The block spans Friday and Saturday, but the clash with the other event is on Friday
    only — so Friday's cell is the one that lights. The block's own span says the event
    covers both days; the *pair's* overlap says the conflict is on one of them, and the AC
    names the overlap.
    """
    user = make_user()
    friday = date(2026, 11, 6)
    saturday = date(2026, 11, 7)

    friday_evening = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)  # Friday 22:00 PST
    saturday_morning = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)  # Saturday 02:00 PST

    overnight = personal_event(
        user,
        name="Overnight",
        start=friday_evening,
        end=saturday_morning,
    )
    # A Friday-afternoon event that the overnight one does **not** overlap: it ends
    # before the overnight one starts.
    personal_event(
        user,
        name="Afternoon",
        start=datetime(2026, 11, 6, 21, 0, tzinfo=UTC),  # Friday 13:00 PST
        end=datetime(2026, 11, 6, 22, 0, tzinfo=UTC),
    )
    # A pair between the overnight event and something inside it — the overlap is on
    # Saturday only.
    clash = personal_event(
        user,
        name="Saturday thing",
        start=datetime(2026, 11, 7, 9, 0, tzinfo=UTC),  # Saturday 01:00 PST
        end=datetime(2026, 11, 7, 10, 0, tzinfo=UTC),
    )
    pair(
        user,
        left_kind="personal_event",
        left_id=overnight.id,
        right_kind="personal_event",
        right_id=clash.id,
    )

    week = read_timeline_week(user_id=user.pk, day=friday, now=local_midnight(friday))

    friday_cell = next(day for day in week.days if day.date == friday)
    saturday_cell = next(day for day in week.days if day.date == saturday)

    assert not next(b for b in friday_cell.blocks if b.name == "Overnight").conflict
    assert next(b for b in saturday_cell.blocks if b.name == "Overnight").conflict


def test_the_indicator_is_false_when_the_pairs_other_side_has_gone():
    """A pair whose other side has gone is not the user's standing reminder.

    The side that remains is still drawn — it is the user's own event — but there is no
    conflict left to remind them of, because the other event is gone.
    """
    user = make_user()
    event = personal_event(user, name="Coffee with Sam")
    pair(
        user,
        left_kind="personal_event",
        left_id=event.id,
        right_kind="personal_event",
        right_id=uuid4(),  # a personal event that is not there
    )

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    wednesday = next(day for day in week.days if day.date == WEDNESDAY)
    assert not any(block.conflict for block in wednesday.blocks)


def test_the_blocks_are_ordered_by_start_then_id():
    user = make_user()
    personal_event(user, name="Later", start=local_midnight(WEDNESDAY) + timedelta(hours=20))
    personal_event(user, name="Earlier", start=local_midnight(WEDNESDAY) + timedelta(hours=9))

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    wednesday = next(day for day in week.days if day.date == WEDNESDAY)
    assert [block.name for block in wednesday.blocks] == ["Earlier", "Later"]


def test_the_week_is_cut_in_the_users_zone_and_the_response_names_it():
    """The days are the user's zone, and the response names the week it returned."""
    user = make_user()
    in_zone(user, "Europe/Berlin")

    week = read_timeline_week(
        user_id=user.pk,
        day=date(2026, 11, 4),
        now=datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
    )

    assert week.timezone == "Europe/Berlin"
    assert week.week_start == MONDAY
    assert week.week_end == SUNDAY


def test_the_week_falls_back_to_utc_when_the_user_has_no_preference():
    """A user with no digest preference has no zone, so the week is cut in UTC."""
    user = make_user()
    DigestPreference.objects.using(PERSONAL).filter(user_id=user.pk).delete()

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    assert week.timezone == "UTC"


def test_the_read_holds_only_the_callers_events():
    """Another user's events are not in the week."""
    user = make_user()
    other = make_user("other@example.test")
    personal_event(user, name="Mine")
    personal_event(other, name="Theirs")

    week = read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    assert "Mine" in blocks_on(week, WEDNESDAY)
    assert "Theirs" not in blocks_on(week, WEDNESDAY)


def test_the_query_count_does_not_grow_with_the_number_of_events():
    """The read costs a constant number of queries, whatever the user has on.

    A read that cost one query per event would get slower exactly when the user's calendar
    gets busy — so the count is the same for one event and for ten.
    """
    user = make_user()
    personal_event(user, name="Only")
    saved_event(user)

    with (
        CaptureQueriesContext(connections[PERSONAL]) as one_personal,
        CaptureQueriesContext(connections[CATALOG]) as one_catalog,
    ):
        read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    for index in range(9):
        personal_event(user, name=f"Extra {index}", start=local_midnight(WEDNESDAY))
        saved_event(user, start=local_midnight(WEDNESDAY))

    with (
        CaptureQueriesContext(connections[PERSONAL]) as ten_personal,
        CaptureQueriesContext(connections[CATALOG]) as ten_catalog,
    ):
        read_timeline_week(user_id=user.pk, day=WEDNESDAY, now=local_midnight(WEDNESDAY))

    assert len(ten_personal) == len(one_personal)
    assert len(ten_catalog) == len(one_catalog)
    # The five reads: the preference, the personal events, the saved events, the pairs,
    # and the one batched catalog read.
    assert len(one_personal) + len(one_catalog) == 5


# --- The endpoint -----------------------------------------------------------------------------


def test_the_endpoint_names_the_week_and_returns_seven_days():
    """The response names the week's Monday and Sunday, and has seven day cells."""
    user = make_user()
    personal_event(user, name="Coffee with Sam")

    payload = signed_in(user).get("/api/personal/timeline?week=2026-11-04").json()

    assert payload["week_start"] == "2026-11-02"
    assert payload["week_end"] == "2026-11-08"
    assert payload["timezone"] == TZ
    assert len(payload["days"]) == 7
    assert [day["date"] for day in payload["days"]] == [
        "2026-11-02",
        "2026-11-03",
        "2026-11-04",
        "2026-11-05",
        "2026-11-06",
        "2026-11-07",
        "2026-11-08",
    ]


def test_the_endpoint_returns_the_blocks_with_their_kind_and_indicator():
    """The block carries its kind, its id, its name, its times, its zone and the flag."""
    user = make_user()
    event = personal_event(user, name="Coffee with Sam")
    other = personal_event(
        user,
        name="Coffee with Alex",
        start=local_midnight(WEDNESDAY) + timedelta(hours=18),
    )
    pair(
        user,
        left_kind="personal_event",
        left_id=event.id,
        right_kind="personal_event",
        right_id=other.id,
    )

    payload = signed_in(user).get("/api/personal/timeline?week=2026-11-04").json()

    wednesday = next(day for day in payload["days"] if day["date"] == "2026-11-04")
    block = wednesday["blocks"][0]
    assert block["kind"] == "personal"
    assert block["id"] == str(event.id)
    assert block["name"] == "Coffee with Sam"
    assert block["start_time_tz"] == TZ
    assert block["conflict"] is True
    assert block["end_time_utc"] is not None


def test_a_missing_week_means_the_current_week_in_the_users_zone():
    """With no `week`, the current week in the user's own zone is returned.

    The server's date is not the user's date, and which Monday is "this week" depends on
    the zone — so the zone is read before the week is chosen, and the week is the one
    containing **today in the user's zone**, not today on the server.
    """
    user = make_user()
    in_zone(user, "Europe/Berlin")

    # An instant where the two zones name **different weeks**: 23:30 UTC on Sunday the 8th
    # is already Monday the 9th in Berlin, so the server's week ends on the 8th and
    # Berlin's starts on the 9th.
    now = datetime(2026, 11, 8, 23, 30, tzinfo=UTC)
    assert local_date_at(instant=now, zone_name="UTC") == date(2026, 11, 8)
    assert local_date_at(instant=now, zone_name="Europe/Berlin") == date(2026, 11, 9)

    week = read_timeline_week(user_id=user.pk, day=None, now=now)

    # The Berlin week, not the server's.
    assert week.week_start == date(2026, 11, 9)
    assert week.week_end == date(2026, 11, 15)
    assert week.timezone == "Europe/Berlin"


def test_the_endpoint_with_no_week_returns_the_current_week():
    """The endpoint with no `week` returns seven days of the current week.

    Which week depends on the wall clock, so the assertion is about the shape rather than
    about a particular date: seven days, a Monday, and a Sunday seven days later.
    """
    user = make_user()

    payload = signed_in(user).get("/api/personal/timeline").json()

    assert len(payload["days"]) == 7
    assert payload["timezone"] == TZ
    week_start = date.fromisoformat(payload["week_start"])
    week_end = date.fromisoformat(payload["week_end"])
    assert week_start.weekday() == 0
    assert week_end.weekday() == 6
    assert week_end - week_start == timedelta(days=6)


def test_a_malformed_week_is_a_422():
    """A malformed `week` is refused by the parameter's own validation."""
    user = make_user()

    response = signed_in(user).get("/api/personal/timeline?week=not-a-date")

    assert response.status_code == 422


def test_an_anonymous_caller_is_refused():
    """The timeline is the caller's alone, so an anonymous caller is refused."""
    client = CsrfClient()

    response = client.get("/api/personal/timeline")

    assert response.status_code == 401
