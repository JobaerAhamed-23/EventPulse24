"""Event lifecycle decisions (AD-4, AD-17). Stdlib only.

- `classify_time_move`: a start-time move within ±30 days of the **original** start keeps the
  `event_id`; beyond it the Event is superseded. Measuring from the original (not the current)
  start means several small moves can't drift past the window unnoticed.
- `classify_change`: compares the stored facts of an Event with freshly ingested ones and names
  every kind of change, most important first. The caller appends one state change per kind.
"""

from dataclasses import dataclass, fields
from datetime import datetime
from enum import StrEnum

from domain.timezones import canonical_zone, to_instant
from shared.constants import POSTPONEMENT_WINDOW


class TimeMove(StrEnum):
    SAME = "same"
    WITHIN_WINDOW = "within_window"
    SUPERSEDE = "supersede"


class EventStatus(StrEnum):
    SCHEDULED = "scheduled"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class ChangeKind(StrEnum):
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    # Cancelled -> live again, or postponed -> scheduled at the same start. Not a stored
    # EventStateChange kind yet: ingest-pipeline-and-lifecycle decides (NOT_YET_STORED).
    REINSTATED = "reinstated"
    POSTPONED = "postponed"
    TIME_MOVED = "time_moved"
    SOLD_OUT = "sold_out"  # either direction; the facts carry which
    DETAIL_CHANGED = "detail_changed"


PRECEDENCE = tuple(ChangeKind)  # declaration order above is most to least important
NOT_YET_STORED = frozenset({ChangeKind.REINSTATED})


@dataclass(frozen=True)
class EventFacts:
    """What ingestion knows about an Event at one moment, as plain values."""

    start_utc: datetime
    end_utc: datetime | None
    start_time_tz: str
    status: EventStatus
    is_sold_out: bool
    venue_fingerprint: str
    title: str
    description: str
    canonical_url: str


# Facts whose change needs an event_version bump (mirrors Event.LIFECYCLE_FIELDS, which adds
# superseded_by; tests/ingestion/test_domain_parity.py keeps them in step).
LIFECYCLE_FACTS = frozenset(
    {"start_utc", "end_utc", "start_time_tz", "status", "is_sold_out", "venue_fingerprint"}
)
_DETAIL_FACTS = frozenset(
    {"start_time_tz", "venue_fingerprint", "title", "description", "canonical_url"}
)


@dataclass(frozen=True)
class Change:
    kinds: tuple[ChangeKind, ...]  # ordered by PRECEDENCE
    fields: frozenset[str]  # EventFacts field names that differ
    is_lifecycle: bool  # True when a LIFECYCLE_FACTS field changed: event_version must bump


def classify_time_move(original_start_utc: datetime, new_start_utc: datetime) -> TimeMove:
    """Where a new start falls relative to the original one (inclusive ±30 days)."""
    original, new = to_instant(original_start_utc), to_instant(new_start_utc)
    if new == original:
        return TimeMove.SAME
    if abs(new - original) <= POSTPONEMENT_WINDOW:
        return TimeMove.WITHIN_WINDOW
    return TimeMove.SUPERSEDE


def _comparable(name: str, value):
    if isinstance(value, datetime):
        return to_instant(value)
    if name == "start_time_tz":  # US/Eastern and America/New_York are one zone, not a change
        return canonical_zone(value) or value
    return value


def classify_change(
    stored: EventFacts, incoming: EventFacts, original_start_utc: datetime
) -> Change | None:
    """Every kind of change from `stored` to `incoming`, or None if nothing changed.

    Cancellation outranks everything: a cancellation that also moves the date is a
    cancellation, not a new (already cancelled) Event.
    """
    if EventStatus.SUPERSEDED in (stored.status, incoming.status):
        raise ValueError("a superseded Event is terminal and can't change")
    changed = frozenset(
        f.name
        for f in fields(EventFacts)
        if _comparable(f.name, getattr(stored, f.name))
        != _comparable(f.name, getattr(incoming, f.name))
    )
    if not changed:
        return None

    kinds: set[ChangeKind] = set()
    cancelled = incoming.status == EventStatus.CANCELLED
    start_moved = "start_utc" in changed
    if cancelled and stored.status != EventStatus.CANCELLED:
        kinds.add(ChangeKind.CANCELLED)
    superseded = (
        start_moved
        and not cancelled
        and classify_time_move(original_start_utc, incoming.start_utc) is TimeMove.SUPERSEDE
    )
    if superseded:
        kinds.add(ChangeKind.SUPERSEDED)
    if stored.status == EventStatus.CANCELLED and not cancelled:
        kinds.add(ChangeKind.REINSTATED)
    if incoming.status == EventStatus.POSTPONED and stored.status != EventStatus.POSTPONED:
        kinds.add(ChangeKind.POSTPONED)
    if (
        stored.status == EventStatus.POSTPONED
        and incoming.status == EventStatus.SCHEDULED
        and not start_moved
    ):
        kinds.add(ChangeKind.REINSTATED)
    if (start_moved or "end_utc" in changed) and not (cancelled or superseded):
        kinds.add(ChangeKind.TIME_MOVED)
    if "is_sold_out" in changed:
        kinds.add(ChangeKind.SOLD_OUT)
    if changed & _DETAIL_FACTS:
        kinds.add(ChangeKind.DETAIL_CHANGED)

    return Change(
        kinds=tuple(kind for kind in PRECEDENCE if kind in kinds),
        fields=changed,
        is_lifecycle=bool(changed & LIFECYCLE_FACTS),
    )
