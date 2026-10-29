"""iCalendar (RFC 5545) VEVENTs: bytes in, `IcsEvent`s out.

Moved here from `apps/ingestion/parsers/ics.py` so that the catalog pipeline and the
calendar adapter share one implementation. The **behaviour is unchanged**: same
all-day spans, same overnight rolls, same Windows zone mapping, same isolation of one
malformed VEVENT from the rest, same "never raises" promise.

What changed is the *output shape*. The old parser produced the catalog's
`ParsedCandidate`, which carried the catalog's identity decisions. This one produces
`IcsEvent`s — the format's own facts — and leaves identity and time resolution to the
caller.

Times are handed over as written: a `TZID` time is a naive wall-clock time with
`start_zone` set to that TZID (Windows names mapped to IANA), a `Z` time is aware UTC, a
floating time is naive with no zone, and a `VALUE=DATE` is an all-day event. An end
written differently from its start is converted into the start's form, because the
timezone resolver reads both alike.

Recurrence is never expanded. A master with RRULE is one event for its own DTSTART, and
each RECURRENCE-ID override is another; `has_rrule` and `recurrence_id` say which is
which, because the *identity* of the two differs.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from icalendar import Calendar

from formats.ics.events import IcsEvent
from formats.ics.windows_zones import map_zone
from formats.text import (
    MAX_DESCRIPTION,
    MAX_TITLE,
    MAX_VENUE_NAME,
    plain_text,
)
from formats.times import all_day_span, at_midnight, roll_overnight

#: The most events one file may hold. The rest are counted, not parsed. A calendar feed
#: is a single person's calendar, so this is generous — but the parser must be bounded
#: against a hostile file, and the byte limit bounds the file before this does.
MAX_EVENTS = 5_000


@dataclass
class IcsParseResult:
    """What one ICS file said. Never an exception: the parser does not raise."""

    events: list[IcsEvent] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)  # reason -> count
    error: str | None = None  # the whole document was unreadable

    def skip(self, reason: str, count: int = 1) -> None:
        """Count an event that was not read. The reason is a slug, never a value."""
        self.skipped[reason] += count

    @property
    def full(self) -> bool:
        return len(self.events) >= MAX_EVENTS


def _raw(prop) -> str:
    value = prop.to_ical().decode("utf-8", "replace")
    tzid = prop.params.get("TZID")
    return f"TZID={tzid}:{value}" if tzid else value


def _is_date(value) -> bool:
    return isinstance(value, date) and not isinstance(value, datetime)


def _as_written(prop) -> tuple[datetime | date, str | None]:
    """(value, zone): a TZID time as its naive wall clock plus the zone name."""
    value, tzid = prop.dt, prop.params.get("TZID")
    if isinstance(value, datetime) and tzid:
        return value.replace(tzinfo=None), map_zone(tzid)
    return value, None


def _align_end(end_value, start_value, start_zone: str | None):
    """The end in the start's representation, or None if it can't be placed."""
    if not isinstance(end_value, datetime) or not isinstance(start_value, datetime):
        return None
    if start_zone is not None:  # start is a wall clock in its TZID
        if end_value.tzinfo is None:
            return end_value
        return end_value.astimezone(start_value.tzinfo).replace(tzinfo=None)
    if start_value.tzinfo is not None:  # start is an exact instant
        return end_value.astimezone(UTC) if end_value.tzinfo is not None else None
    return end_value if end_value.tzinfo is None else None  # floating start


def _instance_utc(value) -> datetime:
    """The UTC instant identifying a recurrence instance (floating/date read as UTC, id only)."""
    if _is_date(value):
        return at_midnight(value).replace(tzinfo=UTC)
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _instant_of(value) -> datetime | None:
    """The aware instant a start or RECURRENCE-ID denotes, or None if it is a date.

    A `TZID` time is aware — `icalendar` resolved it through the file's own VTIMEZONE — so
    this is the real instant. A floating time is naive: it denotes no instant at all, and
    a date denotes one only when read as a UTC day.
    """
    if _is_date(value):
        return at_midnight(value).replace(tzinfo=UTC)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    return None


def _event(event, result: IcsParseResult) -> None:
    dtstart = event.get("DTSTART")
    if dtstart is None:
        result.skip("no_event_start")
        return
    title = plain_text(event.get("SUMMARY"), MAX_TITLE)
    if not title:
        result.skip("no_title")
        return
    resolved_start = dtstart.dt
    start, zone = _as_written(dtstart)
    raw = {"DTSTART": _raw(dtstart)}
    # The aware value the file wrote: `icalendar` resolves a TZID time through the file's
    # own VTIMEZONE. This is the event's *instant*, and it is what an override's
    # RECURRENCE-ID is compared against.
    start_instant = _instant_of(resolved_start)

    end = None
    end_zone = None
    dtend, duration = event.get("DTEND"), event.get("DURATION")
    if dtend is not None:
        raw["DTEND"] = _raw(dtend)
    if _is_date(start):
        end_day = dtend.dt if dtend is not None and _is_date(dtend.dt) else None
        if end_day is None and duration is not None:
            end_day = start + duration.dt
        start, end = all_day_span(start, end_day)
    else:
        if dtend is not None:
            end = _align_end(dtend.dt, resolved_start, zone)
            end_zone = zone
        elif duration is not None:
            end = start + duration.dt
        end, dropped = roll_overnight(start, end)
        if dropped:
            result.skip("end_before_start")

    recurrence_id = event.get("RECURRENCE-ID")
    if recurrence_id is not None:
        raw["RECURRENCE-ID"] = _raw(recurrence_id)

    status = str(event.get("STATUS", "")).strip().upper()
    result.events.append(
        IcsEvent(
            uid=str(event.get("UID", "")).strip(),
            title=title,
            start=start,
            end=end,
            start_zone=zone,
            end_zone=end_zone,
            all_day=_is_date(dtstart.dt),
            status=status,
            location=plain_text(event.get("LOCATION"), MAX_VENUE_NAME),
            description=plain_text(event.get("DESCRIPTION"), MAX_DESCRIPTION),
            url=str(event.get("URL", "") or ""),
            recurrence_id=recurrence_id.dt if recurrence_id is not None else None,
            has_rrule=event.get("RRULE") is not None,
            raw=raw,
            start_instant=start_instant,
        )
    )


def parse_ics(content: bytes) -> IcsParseResult:
    """Parse an ICS file into its events. Never raises.

    A file that cannot be read at all yields `error="invalid_ics"` and no events; one
    malformed VEVENT is counted and the rest of the file is still parsed.
    """
    result = IcsParseResult()
    try:
        calendar = Calendar.from_ical(content)
        events = calendar.walk("VEVENT")
    except Exception:  # icalendar raises ValueError and others on malformed input
        result.error = "invalid_ics"
        return result
    for event in events:
        if result.full:
            result.skip("too_many_items")
            continue
        try:
            _event(event, result)
        except Exception:  # one malformed VEVENT never stops the rest
            result.skip("unreadable_event")
    return result
