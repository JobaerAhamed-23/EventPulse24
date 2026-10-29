"""The catalog's view of an ICS file: `ParsedCandidate`s.

The parsing itself moved to `formats/ics/`, because the calendar adapter parses ICS too
and there must be one implementation. This module is the *catalog's* half: it turns the
format's facts into the catalog's shape — the identity decision, the URL resolved against
the source's base, the status hint, the venue name.

**The identity rule.** `domain.dedup.ics_item_id` keys an item by its UID, plus the
instance start for a recurring instance, so weekly instances that share one UID stay
distinct under rule (a). A master with an RRULE and each RECURRENCE-ID override are
different instances, so they get different ids — and an override of the master's own
instance replaces it. An event with no UID gets a derived id from its URL, title and
start.

**Times are handed over as written.** The pipeline resolves them (`domain.timezones`),
because only it knows the venue's zone.
"""

from datetime import UTC, date, datetime

from apps.ingestion.parsers.text import derived_id, http_url, item_id
from apps.ingestion.parsers.types import ParsedCandidate, ParseResult, SourceContext, StatusHint
from domain.dedup import ics_item_id
from formats.ics.events import IcsEvent
from formats.ics.parser import parse_ics as parse_ics_events
from formats.times import at_midnight
from shared.ids import series_id


def _instance_utc(value) -> datetime:
    """The UTC instant identifying a recurrence instance (floating/date read as UTC, id only)."""
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return at_midnight(value).replace(tzinfo=UTC)
    raise TypeError("a recurrence instance needs a date or a datetime")


def _candidate(event: IcsEvent, context: SourceContext) -> ParsedCandidate:
    """One ICS event as the catalog wants it."""
    uid = event.uid
    recurrence_id = event.recurrence_id
    in_series = bool(uid) and (recurrence_id is not None or event.has_rrule)
    url = http_url(event.url, context.source_url)
    if not uid:
        source_item = derived_id(url, event.title, event.raw.get("DTSTART", ""))
    elif in_series:
        # The instance key is an *instant*: a master's own start, or the override's
        # RECURRENCE-ID. Both are aware, so an override of the master's own instance
        # collides with it and replaces it rather than duplicating it.
        #
        # A *floating* start names no moment, so `start_instant` is None for it — and a
        # floating master still needs an id, so it falls back to the wall clock read as
        # UTC, exactly as the id of a floating override's RECURRENCE-ID is read.
        instance = recurrence_id if recurrence_id is not None else event.start_instant
        if instance is None:
            instance = event.start
        source_item = ics_item_id(uid, _instance_utc(instance))
    else:
        source_item = uid

    return ParsedCandidate(
        source_event_id=item_id(source_item),
        title=event.title,
        canonical_url=url,
        start=event.start,
        start_zone=event.start_zone,
        start_raw=event.raw.get("DTSTART", ""),
        end=event.end,
        end_raw=event.raw.get("DTEND"),
        all_day=event.all_day,
        venue_name=event.location,
        description=event.description,
        status=StatusHint.CANCELLED if event.status == "CANCELLED" else StatusHint.SCHEDULED,
        series_id=series_id(context.source_id, uid) if in_series else None,
        raw=event.raw,
    )


def parse_ics(content: bytes, context: SourceContext) -> ParseResult:
    """Parse an ICS file into the catalog's candidates."""
    parsed = parse_ics_events(content)
    result = ParseResult()
    if parsed.error is not None:
        result.error = parsed.error
        return result
    # The shared parser's skips are the catalog's skips: an event with no title or no
    # start was counted there, and the catalog must report the same reasons.
    result.skipped.update(parsed.skipped)
    for event in parsed.events:
        if result.full:
            result.skip("too_many_items")
            continue
        try:
            candidate = _candidate(event, context)
        except Exception:  # one malformed event never stops the rest
            result.skip("unreadable_event")
            continue
        # An override replaces its master's instance, whichever comes first in the file.
        result.add(candidate, priority=1 if event.recurrence_id is not None else 0)
    return result
