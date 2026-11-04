"""The Schema.org `Event` projection for the public page (FR-26, AD-12). Stdlib only.

AD-12 says the structured data is *"emitted from the same data the page renders"*, and this
module is how that becomes true rather than aspirational. It takes the public read's payload
— plain data, already fetched — and produces the finished Schema.org object. There is no
second query, no clock read and no database access, so the JSON-LD cannot disagree with the
page: **there is only one source**, and this is a projection of it.

**The output is a `dict`, not a model.** JSON-LD *is* JSON. A dataclass would need a second
step to become the wire shape, and that step is exactly where two sources of truth would
drift apart. The page embeds what it is given, verbatim.

**Nothing is invented.** Per ASSUMPTION-9, the public page reflects the registry's source of
truth only. So a value the registry does not hold is **omitted**, never filled with a
plausible one — and the omissions are the interesting part:

| Property | Source | Omitted when |
| --- | --- | --- |
| `eventAttendanceMode` | nothing — the registry has no such field | always, today |
| `offers.price` | nothing — the registry knows no price | always |
| `offers.availability` | `is_sold_out` | never |
| `location` | the venue | the event has no venue |
| `organizer` | nothing | always |

**`offers` carries no price.** The registry knows whether an event is sold out and does not
know what it costs, so the `Offer` says exactly that. An `Offer` with an `availability` and
no `price` is a valid Schema.org object; a fabricated `"price": "0"` is a claim about the
world that nobody made.

**`eventAttendanceMode` is omitted rather than defaulted.** The registry says nothing about
how an event is attended, and defaulting to `Offline` would be a guess that a crawler would
read as fact. The value is accepted as an optional argument so the day the registry learns
it, the change is one line at the call site and nothing here moves.

**The times carry the offset the zone had at that instant.** `startDate` is the start read in
the event's own IANA zone — not a UTC timestamp relabelled. That matters across a DST
boundary: an event that starts at 23:30 EDT and ends at 01:30 EST has **two different
offsets**, and one offset for both would state a false end time. So `endDate` resolves its
own offset at its own instant.

**`superseded` produces no `eventStatus`.** It is terminal, the public read 404s it before
it ever builds a payload, and Schema.org's `EventStatus` vocabulary has no term for it.
There is no honest mapping, so there is none.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from domain.timezones import UTC_ZONE, canonical_zone
from shared.constants import (
    SCHEMA_ORG_AVAILABILITY_IN_STOCK,
    SCHEMA_ORG_AVAILABILITY_SOLD_OUT,
    SCHEMA_ORG_CONTEXT,
    SCHEMA_ORG_EVENT_STATUS,
    SCHEMA_ORG_EVENT_TYPE,
    SCHEMA_ORG_OFFER_TYPE,
    SCHEMA_ORG_PLACE_TYPE,
    SCHEMA_ORG_POSTAL_ADDRESS_TYPE,
)


def _zone(name: str) -> ZoneInfo:
    """The event's own zone, validated through the module that owns zone decisions.

    An unknown zone falls back to UTC rather than raising, for the reason
    `domain/event_fit.py` gives: a zone on an `Event` was validated at write time, so an
    unknown name here means the data is older or hand-edited — not that the event is invalid.
    A structured-data warning on one page is a worse answer than a page that states the time
    in UTC.

    `canonical_zone` loads the zone to check it, so a canonical name always loads again —
    there is no second failure mode to handle here.
    """
    canonical = canonical_zone(name)
    if canonical is None:
        return ZoneInfo(UTC_ZONE)
    return ZoneInfo(canonical)


def _zoned(instant: datetime, zone: ZoneInfo) -> str:
    """An instant read in `zone`, with the offset that zone had **at that instant**.

    `astimezone` resolves the offset for the instant being converted, which is what makes
    the DST fall-back correct: the same `America/New_York` zone yields `-04:00` in July and
    `-05:00` in January, and an event that straddles the boundary carries both.

    **A naive datetime is refused, not assumed.** `astimezone` would silently read a naive
    value as UTC and then convert it — turning 18:30 into 08:30-04:00, a ten-hour lie
    about the event's start time, and a lie that would reach a search result. `Event`
    stores UTC (AD-6), so a naive value means a caller passed the wrong thing; the honest
    answer is to refuse it.
    """
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("the instant must be timezone-aware; a naive datetime has no instant")
    return instant.astimezone(zone).isoformat()


def _location(
    *,
    venue_name: str | None,
    venue_city: str | None,
    venue_country_code: str | None,
) -> dict[str, object] | None:
    """The `Place` for a venue, or None when there is no venue.

    **A venue-less event omits `location` entirely** rather than emitting an empty `Place`.
    An empty `Place` is a node that says nothing and validates — the kind of thing that
    draws a structured-data warning.

    The address carries only the parts the registry holds: `addressLocality` (the city) and
    `addressCountry` (the country code). **There is no `streetAddress`**, because `Venue`
    has no address column, and inventing a street line would put a fiction in the structured
    data.
    """
    if not venue_name:
        return None

    address: dict[str, object] = {"@type": SCHEMA_ORG_POSTAL_ADDRESS_TYPE}
    if venue_city:
        address["addressLocality"] = venue_city
    if venue_country_code:
        address["addressCountry"] = venue_country_code

    return {
        "@type": SCHEMA_ORG_PLACE_TYPE,
        "name": venue_name,
        "address": address,
    }


def _offers(is_sold_out: bool) -> dict[str, object]:
    """The `Offer`: availability, and **no price**.

    The registry knows whether an event is sold out. It does not know what it costs, and a
    price that nobody set is worse than a missing one — so only `availability` is stated.
    """
    return {
        "@type": SCHEMA_ORG_OFFER_TYPE,
        "availability": (
            SCHEMA_ORG_AVAILABILITY_SOLD_OUT if is_sold_out else SCHEMA_ORG_AVAILABILITY_IN_STOCK
        ),
    }


def project_schema_org_event(
    *,
    title: str,
    description: str,
    start_time_utc: datetime,
    start_time_tz: str,
    status: str,
    is_sold_out: bool,
    end_time_utc: datetime | None = None,
    venue_name: str | None = None,
    venue_city: str | None = None,
    venue_country_code: str | None = None,
    canonical_url: str | None = None,
    attendance_mode: str | None = None,
) -> dict[str, object]:
    """The Schema.org `Event` for one public event.

    A pure function over plain data: it takes the payload the public read already has, and
    returns the finished object the page embeds verbatim. No query, no clock, no randomness —
    the same inputs always give the same output.

    `attendance_mode` is the Schema.org `eventAttendanceMode` IRI, and is **None today**,
    because the registry has no attendance mode to read. It is accepted here so the
    vocabulary has one home and the day the registry learns the value, the call site changes
    and nothing in this module does.

    `status` is `Event.status` by value. A status with no Schema.org term — `superseded` —
    produces **no** `eventStatus` property rather than a wrong one.
    """
    zone = _zone(start_time_tz)

    event: dict[str, object] = {
        "@context": SCHEMA_ORG_CONTEXT,
        "@type": SCHEMA_ORG_EVENT_TYPE,
        "name": title,
        "startDate": _zoned(start_time_utc, zone),
    }

    if end_time_utc is not None:
        event["endDate"] = _zoned(end_time_utc, zone)

    if description:
        event["description"] = description

    if canonical_url:
        event["url"] = canonical_url

    # A status with no Schema.org term yields no property. The vocabulary is closed and the
    # map has no default, so a status the map does not know is a fact we cannot state.
    event_status = SCHEMA_ORG_EVENT_STATUS.get(status)
    if event_status is not None:
        event["eventStatus"] = event_status

    if attendance_mode is not None:
        event["eventAttendanceMode"] = attendance_mode

    location = _location(
        venue_name=venue_name,
        venue_city=venue_city,
        venue_country_code=venue_country_code,
    )
    if location is not None:
        event["location"] = location

    event["offers"] = _offers(is_sold_out)

    return event


__all__ = [
    "project_schema_org_event",
]
