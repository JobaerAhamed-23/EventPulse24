"""The user's local week — one rule, shared by the reader and the writer.

**Why this is a module and not a private helper.** `digest_dates.py` exists for the
same reason: the rule "which local day is this instant" must not be computed twice, or
the writer and the reader drift and the user is told "nothing today" while holding three
cards. The timeline is the second reader of a day rule, so it gets the same treatment —
one module, one rule, both sides call it.

**A week is not 168 hours.** The week is cut at **local midnight** in the user's zone,
so the Monday–Sunday week is 167 hours when a spring-forward falls inside it and 169
when a fall-back does. Computing the bounds by adding 24 hours to a UTC instant would
put the boundary on the wrong side of the transition, and an event at 23:30 local would
land on the wrong day.

So every bound here is computed **by conversion**: a local wall clock is read in the
zone, and the resulting UTC instants are the bounds. `zoneinfo` does the DST work, and
the arithmetic never sees a transition.

**Monday, not Sunday.** The week starts on Monday in every locale this product
supports, and the UX spine's week grid is Mon–Sun. `date.weekday()` is 0 for Monday,
so Monday is the week's first day.

**An unknown zone falls back to UTC rather than raising.** The same reasoning as
`digest_dates.local_date_for`: the zone is validated at write time by the onboarding
command, so an unknown name means hand-edited data, not that the timeline should fail.
The failure mode is a wrong day, not a missing week.

**The functions are pure.** They take instants and zone names and return instants and
dates — no database, no clock, no settings. That is what makes a DST week testable
without a fixture that has to be right twice a year.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.constants import DEFAULT_DIGEST_TIMEZONE

#: The number of days in a week. Seven, always — a DST week is a different *number of
#: hours*, never a different number of days.
DAYS_IN_WEEK = 7


def _zone(zone_name: str) -> ZoneInfo:
    """The zone, or UTC when the name is not one.

    An unknown zone falls back rather than raising, for the reason in the module
    docstring: a hand-edited zone name must not take the user's timeline away.
    """
    try:
        return ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_DIGEST_TIMEZONE)


def week_start_for(*, day: date, zone_name: str) -> date:
    """The local Monday of the week that contains `day`.

    `day` is read as a **local** date, so "the week containing 2026-11-04" is the week
    whose Monday is 2026-11-02 — regardless of what UTC says about that instant.
    """
    return day - timedelta(days=day.weekday())


def week_days(*, day: date, zone_name: str) -> tuple[date, ...]:
    """The seven local dates of the week containing `day`, Monday first.

    `zone_name` is not used to cut the days — a *date* is already a local date — but it
    is part of the signature so a caller cannot pass a week without saying whose week
    it is. The days are the same seven dates whatever the zone; only their *bounds* are
    zone-dependent.
    """
    monday = week_start_for(day=day, zone_name=zone_name)
    return tuple(monday + timedelta(days=offset) for offset in range(DAYS_IN_WEEK))


def day_bounds(*, local_date: date, zone_name: str) -> tuple[datetime, datetime]:
    """The UTC instants that bound one local day in `zone_name`.

    The returned end is **exclusive** — it is the next local midnight. A day is 23, 24
    or 25 hours long, depending on the transition, and the arithmetic here never
    assumes which.

    The local midnight is read with `fold=0`: where a transition makes midnight itself
    ambiguous, the **first** occurrence is the day's start. A zone whose transition
    happens exactly at midnight is vanishingly rare, and taking the first occurrence is
    the same choice `domain.timezones.read_wall_clock` makes for a folded wall clock.
    """
    zone = _zone(zone_name)
    start = datetime.combine(local_date, time.min).replace(tzinfo=zone, fold=0)
    end = datetime.combine(local_date + timedelta(days=1), time.min).replace(tzinfo=zone, fold=0)
    return start.astimezone(UTC), end.astimezone(UTC)


def week_bounds(*, day: date, zone_name: str) -> tuple[datetime, datetime]:
    """The UTC instants that bound the local week containing `day`.

    The start is the local Monday's midnight and the end is the local Sunday's next
    midnight — **exclusive**, so an event starting exactly at the end is outside the
    week and one starting exactly at the start is inside it.
    """
    monday = week_start_for(day=day, zone_name=zone_name)
    sunday = monday + timedelta(days=DAYS_IN_WEEK - 1)
    start, _ = day_bounds(local_date=monday, zone_name=zone_name)
    _, end = day_bounds(local_date=sunday, zone_name=zone_name)
    return start, end


def local_date_at(*, instant: datetime, zone_name: str) -> date:
    """The local calendar date of an instant in `zone_name`.

    The same rule as `digest_dates.local_date_for`, and for the same reason: two copies
    of "which day is this" is one too many.
    """
    return instant.astimezone(_zone(zone_name)).date()


def days_covered(
    *,
    start_utc: datetime,
    end_utc: datetime | None,
    zone_name: str,
    limit: date | None = None,
) -> tuple[date, ...]:
    """The local dates an event covers, in order.

    **An event is placed on the day its local start falls on** — that is the rule the
    acceptance criteria name, and it is the rule the *screen* draws: a block that starts
    at 23:30 Friday is a Friday block even if it runs into Saturday.

    **But a multi-day event appears on every day it covers** (FR-33 (e): *"indicator
    repeats on each day-cell the event spans"*). So the days are the start's local date
    through the end's local date, inclusive.

    **An open-ended event** — one with no end — covers every day from its start onward.
    It has no end to convert, so the range runs to `limit` (the caller passes the week's
    last day) or, with no limit, to the start's own date alone.

    **A zero-length event** covers exactly one day: its start's. An event that ends
    exactly at midnight belongs to the day it *started* — the exclusive end instant is
    the next day's start, so the end's local date is the next day and the range would
    otherwise include a day the event does not touch.

    `limit` caps the result. It exists so an open-ended event cannot make the caller
    build a list of dates from 1970 to the end of time.
    """
    zone = _zone(zone_name)
    first = start_utc.astimezone(zone).date()

    if end_utc is None:
        # An open-ended event has no end to convert, so there is no last day to read off
        # it. It runs from its start onward — which means it covers **every** day from
        # its start to the limit. With no limit there is no day after the start to name,
        # so it covers its start alone.
        last = limit if limit is not None else first
    else:
        # An event that ends exactly at a local midnight ends at the *start* of the
        # next day, so the last day it touches is the day before that.
        end_local = end_utc.astimezone(zone)
        last = (end_local - timedelta(microseconds=1)).astimezone(zone).date()

    if last < first:
        # An event whose end precedes its start is malformed data, not a week-long
        # event. It covers the day it starts.
        last = first

    if limit is not None and limit < first:
        return ()

    days: list[date] = []
    cursor = first
    while cursor <= last:
        days.append(cursor)
        cursor += timedelta(days=1)
    return tuple(days)


def overlaps_day(
    *,
    start_utc: datetime,
    end_utc: datetime | None,
    local_date: date,
    zone_name: str,
) -> bool:
    """Whether an event covers the given local day.

    The test is against the **day's own interval**, not the event's start. That is what
    makes the cross-midnight indicator fire on every day-cell the event spans: an event
    running from Friday 22:00 to Saturday 02:00 overlaps Friday's interval and
    Saturday's, and the indicator belongs on both.

    An open-ended event overlaps a day when it started at or before that day's end.

    **The day's start is inclusive and its end is exclusive**, so an event ending
    exactly at midnight does not touch the next day.
    """
    day_start, day_end = day_bounds(local_date=local_date, zone_name=zone_name)
    if start_utc >= day_end:
        return False
    if end_utc is None:
        return True
    return end_utc > day_start


__all__ = [
    "DAYS_IN_WEEK",
    "day_bounds",
    "days_covered",
    "local_date_at",
    "overlaps_day",
    "week_bounds",
    "week_days",
    "week_start_for",
]
