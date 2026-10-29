"""Event times exactly as written, plus the two normalizations parsers own.

- All-day: a date-only start is local midnight; the end is the next midnight (exclusive), or
  start + 1 day when none is given.
- Overnight: an end earlier than its start ("22:00-02:00") rolls forward one day; if it's still
  earlier, the end is dropped.
Nothing here converts to UTC: `domain.timezones.resolve_tz` does that.

**This module is format-agnostic.** RSS, JSON-LD and iCalendar all carry an all-day span
and an overnight end, and all three normalise them the same way — so the rules live here,
once, rather than in each format's own module.
"""

from datetime import date, datetime, time, timedelta


def parse_iso(value: object) -> datetime | date | None:
    """An ISO 8601 date or datetime as written (naive, or aware with its offset), else None."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if len(text) == 10:
            return date.fromisoformat(text)
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def at_midnight(day: date) -> datetime:
    return datetime.combine(day, time())


def all_day_span(start: date, end: date | None) -> tuple[datetime, datetime]:
    begin = at_midnight(start)
    finish = at_midnight(end) if end and end > start else begin + timedelta(days=1)
    return begin, finish


def _comparable(a: datetime, b: datetime) -> bool:
    if (a.tzinfo is None) != (b.tzinfo is None):
        return False
    return a.tzinfo is None or a.utcoffset() == b.utcoffset()


def roll_overnight(start: datetime, end: datetime | None) -> tuple[datetime | None, bool]:
    """(end, dropped): roll an end before its start by one day, or drop it if that's not enough.

    Ends in a different representation from the start (naive vs aware, or another offset)
    are left for the timezone resolver.
    """
    if end is None or not _comparable(start, end) or end >= start:
        return end, False
    rolled = end + timedelta(days=1)
    if rolled >= start:
        return rolled, False
    return None, True
