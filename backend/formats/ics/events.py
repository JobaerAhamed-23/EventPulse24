"""The facts an ICS file states about one event (RFC 5545).

`IcsEvent` is the **intersection** of what the two consumers need: the catalog's
`ParsedCandidate` and the calendar's `CalendarEntry` both need these, and both need
things this shape deliberately does not carry.

**What it does not carry, and why.** The catalog's candidate holds `source_event_id` (an
identity decision), `canonical_url` (resolved against the source's base URL) and
`venue_name` (a catalog concept). The calendar has no source URL, no venue registry and
no identity policy — so the shared shape leaves all three out and each consumer decides
them itself.

**What it does carry that neither consumer's own type could.** The `RECURRENCE-ID` and
the `has_rrule` flag. Both consumers need to know whether an event is a series master,
an instance override, or a plain event, and the flag has to survive the parse because the
*identity* depends on it: a master and its override must not share an id.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class IcsEvent:
    """One VEVENT, as the file wrote it.

    The times are **as written**, never converted: `start` is a naive wall clock when
    the event named a zone (`start_zone`), aware UTC when it wrote `Z`, and naive with
    no zone when it floated. `end` is in the same representation as `start`, or None when
    the file did not give one that could be placed.
    """

    uid: str  # the UID exactly as written ("" when the event has none)
    title: str
    start: datetime | None  # None when the event has no DTSTART
    end: datetime | None
    start_zone: str | None  # IANA name (Windows names mapped), None when floating
    end_zone: str | None
    all_day: bool
    status: str  # "CANCELLED", or "" for anything else
    location: str
    description: str
    url: str  # the URL as written; a consumer resolves it against its own base
    recurrence_id: datetime | None  # the RECURRENCE-ID instant, when this is an override
    has_rrule: bool
    raw: dict[str, str] = field(default_factory=dict)  # the as-written fields
    start_instant: datetime | None = None
    """The event's start as an *instant* — the aware value the file wrote, before the
    wall-clock projection.

    This is **not** `start`: `start` is a naive wall clock when the event named a zone,
    because that is how the catalog hands times over. But an event's *identity* needs an
    instant, and an override's `RECURRENCE-ID` is an instant too — so a master and the
    override of its own instance must be keyed the same way, or they would not collide
    and the override would duplicate the master instead of replacing it.
    """
