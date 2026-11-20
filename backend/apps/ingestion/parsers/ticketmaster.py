"""Ticketmaster Discovery v2 responses (FR-17's top acquisition tier).

**Why this tier leads.** Discovery returns `dates.start.dateTime` — an exact UTC instant —
*and* `dates.timezone`, an IANA zone. That is FR-60 row A1: confidence 1.00 at `Tier.FULL`,
with no registered venue and no `source.city_tz` to fall back on. It is the only acquisition
method that resolves perfectly in a city we have never seen before, which is why FR-17 puts
it first and why the city zone is a safety net rather than the plan.

**Pure and total, like every parser here.** `json.loads` in a `try`, every field read
through `.get`, every list indexed defensively. A response shape we did not expect produces
fewer candidates and a `skipped` count, never an exception — the package's standing promise.

**Times are handed over as written.** `domain.timezones` resolves them. That is why
`start_raw` carries the provider's own string even when `start` was built from two fields.
"""

import json
from datetime import datetime
from typing import Any

from apps.ingestion.parsers.text import http_url, item_id, plain_text
from apps.ingestion.parsers.types import (
    MAX_CITY,
    MAX_DESCRIPTION,
    MAX_TITLE,
    MAX_VENUE_NAME,
    ParsedCandidate,
    ParseResult,
    SourceContext,
    StatusHint,
)
from formats.times import at_midnight, parse_iso

#: `dates.status.code` -> what it means for the catalog.
#:
#: Discovery v2 spells it "canceled"; the adjacent Discovery Feed docs spell it "cancelled".
#: Both are accepted rather than betting on which endpoint answered.
#:
#: **`offsale` is deliberately not a status.** It means "outside the public on-sale window",
#: which covers an event that has not gone on sale yet as well as one that has sold out, and
#: presale inventory can still exist during it. Reading it as `sold_out` would mislabel
#: events that are simply not on sale yet, so `sold_out` stays False and the catalog says
#: only what the provider actually claimed.
STATUS = {
    "canceled": StatusHint.CANCELLED,
    "cancelled": StatusHint.CANCELLED,
    "postponed": StatusHint.POSTPONED,
    "rescheduled": StatusHint.POSTPONED,
}


def _mapping(value: object) -> dict[str, Any]:
    """`value` when it is a JSON object, else an empty one — so `.get` chains never raise."""
    return value if isinstance(value, dict) else {}


def _sequence(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _start(dates: dict[str, Any]) -> tuple[datetime, str, bool] | None:
    """`(start, start_raw, all_day)` as the provider wrote it, or None if there is no time.

    Three shapes, in descending order of what the provider knows. An event with none of
    them (`dateTBA` with no local date) has no event time at all, and a guess would create
    a wrong-time event — the same rule the RSS parser applies to `pubDate`.
    """
    start = _mapping(dates.get("start"))
    exact = parse_iso(_text(start.get("dateTime")))
    if isinstance(exact, datetime):
        return exact, _text(start.get("dateTime")), False

    local_date = _text(start.get("localDate"))
    day = parse_iso(local_date)
    if day is None:
        return None
    local_time = _text(start.get("localTime"))
    if local_time:
        wall = parse_iso(f"{local_date}T{local_time}")
        if isinstance(wall, datetime):
            return wall, f"{local_date} {local_time}", False
    if isinstance(day, datetime):
        return day, local_date, False
    # A date with no time: `noSpecificTime` or `timeTBA`. Midnight, flagged all-day, which
    # is what the ICS parser does with a VALUE=DATE DTSTART.
    return at_midnight(day), local_date, True


def _venue(event: dict[str, Any]) -> tuple[str, str, str]:
    venues = _sequence(_mapping(event.get("_embedded")).get("venues"))
    venue = _mapping(venues[0]) if venues else {}
    country = _mapping(venue.get("country"))
    return (
        plain_text(_text(venue.get("name")), MAX_VENUE_NAME),
        plain_text(_text(_mapping(venue.get("city")).get("name")), MAX_CITY),
        _text(country.get("countryCode")).upper()[:2],
    )


def _event(event: dict[str, Any], result: ParseResult) -> None:
    source_event_id = _text(event.get("id"))
    if not source_event_id:
        # The provider's own id is what makes a re-ingest dedupe instead of duplicate. An
        # event without one cannot be followed between runs, so it is not taken at all.
        result.skip("no_source_event_id")
        return
    title = plain_text(_text(event.get("name")), MAX_TITLE)
    if not title:
        result.skip("no_title")
        return
    dates = _mapping(event.get("dates"))
    started = _start(dates)
    if started is None:
        result.skip("no_event_start")
        return
    start, start_raw, all_day = started
    zone = _text(dates.get("timezone"))
    venue_name, venue_city, venue_country = _venue(event)
    status_code = _text(_mapping(dates.get("status")).get("code")).lower()
    result.add(
        ParsedCandidate(
            source_event_id=item_id(source_event_id),
            title=title,
            canonical_url=http_url(event.get("url")),
            start=start,
            start_zone=zone or None,
            start_raw=start_raw,
            all_day=all_day,
            venue_name=venue_name,
            venue_city=venue_city,
            venue_country=venue_country,
            description=plain_text(
                _text(event.get("info")) or _text(event.get("pleaseNote")), MAX_DESCRIPTION
            ),
            status=STATUS.get(status_code, StatusHint.SCHEDULED),
            raw={
                key: value
                for key, value in (
                    ("start_raw", start_raw),
                    ("timezone", zone),
                    ("status", status_code),
                )
                if value
            },
        )
    )


def read(content: bytes, context: SourceContext) -> ParseResult:
    """Candidates from one Discovery v2 search response."""
    result = ParseResult()
    try:
        payload = json.loads(content)
    except (ValueError, UnicodeDecodeError):
        return ParseResult(error="invalid_json")
    payload = _mapping(payload)
    if payload.get("fault") or payload.get("errors"):
        # The provider answered, and said no — a rate limit, a bad key, a bad parameter.
        # That is a failed document, not an empty one: reporting it as zero events would
        # read as "this city has nothing", which is a different and much worse claim.
        return ParseResult(error="provider_error")
    events = _sequence(_mapping(payload.get("_embedded")).get("events"))
    # A page with no `_embedded` is a real, successful "no events match". Not an error.
    for event in events:
        if result.full:
            result.skip("too_many_items", len(events) - len(result.candidates))
            break
        _event(_mapping(event), result)
    return result
