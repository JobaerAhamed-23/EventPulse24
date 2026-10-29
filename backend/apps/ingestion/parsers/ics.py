"""iCalendar (RFC 5545) VEVENTs, for ICS-by-URL sources and, later, the email-ICS mailbox.

Times are handed over as written: a `TZID` time is a naive wall-clock time with `start_zone`
set to that TZID (Windows names mapped to IANA), a `Z` time is aware UTC, a floating time is
naive with no zone, and a `VALUE=DATE` is an all-day event. An end written differently from
its start is converted into the start's form, because the timezone resolver reads both alike.

Recurrence is never expanded. A master with RRULE is one candidate for its own DTSTART, and each
RECURRENCE-ID override is another; both share `series_id(source_id, UID)` and are keyed by
`ics_item_id(UID, instance start)`, so an override of the master's own instance updates it.
"""

from datetime import UTC, date, datetime

from icalendar import Calendar

from apps.ingestion.parsers.text import derived_id, http_url, item_id, plain_text
from apps.ingestion.parsers.times import all_day_span, at_midnight, roll_overnight
from apps.ingestion.parsers.types import (
    MAX_DESCRIPTION,
    MAX_TITLE,
    MAX_VENUE_NAME,
    ParsedCandidate,
    ParseResult,
    SourceContext,
    StatusHint,
)
from apps.ingestion.parsers.windows_zones import map_zone
from domain.dedup import ics_item_id
from shared.ids import series_id


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


def _event(event, context: SourceContext, result: ParseResult) -> None:
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

    end = None
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
        elif duration is not None:
            end = start + duration.dt
        end, dropped = roll_overnight(start, end)
        if dropped:
            result.skip("end_before_start")

    uid = str(event.get("UID", "")).strip()
    recurrence_id = event.get("RECURRENCE-ID")
    in_series = bool(uid) and (recurrence_id is not None or event.get("RRULE") is not None)
    url = http_url(str(event.get("URL", "")), context.source_url)
    if not uid:
        source_item = derived_id(url, title, raw["DTSTART"])
    elif in_series:
        instance = recurrence_id.dt if recurrence_id is not None else resolved_start
        source_item = ics_item_id(uid, _instance_utc(instance))
    else:
        source_item = uid
    if recurrence_id is not None:
        raw["RECURRENCE-ID"] = _raw(recurrence_id)

    status = str(event.get("STATUS", "")).strip().upper()
    result.add(
        ParsedCandidate(
            source_event_id=item_id(source_item),
            title=title,
            canonical_url=url,
            start=start,
            start_zone=zone,
            start_raw=raw["DTSTART"],
            end=end,
            end_raw=raw.get("DTEND"),
            all_day=_is_date(dtstart.dt),
            venue_name=plain_text(event.get("LOCATION"), MAX_VENUE_NAME),
            description=plain_text(event.get("DESCRIPTION"), MAX_DESCRIPTION),
            status=StatusHint.CANCELLED if status == "CANCELLED" else StatusHint.SCHEDULED,
            series_id=series_id(context.source_id, uid) if in_series else None,
            raw=raw,
        ),
        # An override replaces its master's instance, whichever comes first in the file.
        priority=1 if recurrence_id is not None else 0,
    )


def parse_ics(content: bytes, context: SourceContext) -> ParseResult:
    result = ParseResult()
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
            _event(event, context, result)
        except Exception:  # one malformed VEVENT never stops the rest
            result.skip("unreadable_event")
    return result
