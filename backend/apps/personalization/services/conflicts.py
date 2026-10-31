"""Conflict detection on write (AD-21, FR-58, FR-33).

This module is the service layer around the one overlap function. `domain/conflict.py` decides
whether two intervals clash and whether two events look like the same event; this module
decides *which* events to compare and *what* to write when they do.

Three jobs:

- **Gather candidates.** A candidate event is compared against the user's other personal
  events and their saved events, inside a bounded window. The scan is a range query on
  `(user_id, start_utc)`, not a full scan of the user's history.
- **Call the domain.** `domain.conflict.conflicts` (overlap) and `domain.conflict.is_duplicate`
  (same event). The rules live in one place; this module never re-implements them.
- **Normalise the sides.** A `ConflictPair` row holds two sides by value, and its unique
  constraint is symmetric only if the sides are sorted. `(A, B)` and `(B, A)` are one row, or
  the same conflict is detected twice and the user is prompted twice. The model's own
  docstring names this as the command layer's responsibility.

Detection runs **on write only** — never at render (AD-21). The Pulse Card, the Timeline and
`/conflicts` all read the same `CONFLICT_PAIR` rows, so the indicator is symmetric by
construction.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Q, QuerySet

from apps.personalization.models import ConflictPair, PersonalEvent, SavedEvent
from domain.conflict import conflicts as intervals_conflict
from domain.conflict import is_duplicate
from shared.actor import Actor
from shared.constants import CONFLICT_SCAN_WINDOW, DUPLICATE_START_WINDOW
from shared.db import PERSONAL

#: The two kinds of record a conflict side can name, published as plain strings.
#:
#: The values live on `ConflictPair.SideKind`, but the API layer must not import
#: `apps.personalization.models` — it is the surface, and the surface reads the app's
#: *published* interface, not its tables. So the constants are re-published here, where the
#: model is already imported, and the API layer takes them from here.
PERSONAL_EVENT_SIDE = ConflictPair.SideKind.PERSONAL_EVENT
SAVED_EVENT_SIDE = ConflictPair.SideKind.SAVED_EVENT


@dataclass(frozen=True)
class ConflictSide:
    """One side of a conflict, as plain data."""

    kind: str  # "personal_event" | "saved_event"
    id: UUID
    name: str
    start_utc: datetime
    end_utc: datetime | None


@dataclass(frozen=True)
class DetectedConflict:
    """One conflict the user must answer.

    `new_side` is the event the user just created or saved; `other_side` is the one it
    clashes with. The pair row itself is symmetric — it stores both sides sorted — so the
    prompt's asymmetry has to live here, or "Delete the new one" would not know which event
    to delete.
    """

    kind: str  # "time" | "duplicate"
    new_side: ConflictSide
    other_side: ConflictSide
    pair_id: UUID | None  # None until the pair is written


@dataclass(frozen=True)
class Candidate:
    """The event being written, as the detector sees it."""

    kind: str  # "personal_event" | "saved_event"
    id: UUID | None  # None before the row exists
    name: str
    start_utc: datetime
    end_utc: datetime | None

    @property
    def side(self) -> ConflictSide:
        return ConflictSide(
            kind=self.kind,
            id=self.id,
            name=self.name,
            start_utc=self.start_utc,
            end_utc=self.end_utc,
        )


def _personal_side(event: PersonalEvent) -> ConflictSide:
    return ConflictSide(
        kind=ConflictPair.SideKind.PERSONAL_EVENT,
        id=event.id,
        name=event.name,
        start_utc=event.start_utc,
        end_utc=event.end_utc,
    )


def _saved_side(event: SavedEvent) -> ConflictSide:
    # A saved public event has no name of its own in `personal`: the title lives in `catalog`
    # and is not copied into the snapshot. The id stands in for the label here.
    return ConflictSide(
        kind=ConflictPair.SideKind.SAVED_EVENT,
        id=event.id,
        name=f"saved {event.event_id}",
        start_utc=event.start_utc,
        end_utc=event.end_utc,
    )


def _normalise(left: ConflictSide, right: ConflictSide) -> tuple[ConflictSide, ConflictSide]:
    """The two sides in a fixed order, so `(A, B)` and `(B, A)` are one row.

    Lexicographic on `(kind, id)`: the kind first, then the id as the tiebreak. The order is
    total — two different sides always differ on at least one of the two.
    """
    if (left.kind, str(left.id)) <= (right.kind, str(right.id)):
        return left, right
    return right, left


def _window(candidate: Candidate) -> tuple[datetime, datetime]:
    """The starts that could possibly clash with the candidate.

    Two windows, and the wider one wins: the overlap rule needs a candidate within
    `CONFLICT_SCAN_WINDOW` of the new start to be worth comparing, and the duplicate rule
    needs one within `DUPLICATE_START_WINDOW`. An event that is an hour away cannot overlap,
    but it can be a duplicate, so the scan has to reach that far.
    """
    window = max(CONFLICT_SCAN_WINDOW, DUPLICATE_START_WINDOW)
    return candidate.start_utc - window, candidate.start_utc + window


def _candidate_personal_events(user_id: UUID, candidate: Candidate) -> QuerySet:
    low, high = _window(candidate)
    queryset = PersonalEvent.objects.using(PERSONAL).filter(
        user_id=user_id, start_utc__gte=low, start_utc__lte=high
    )
    if candidate.id is not None:
        queryset = queryset.exclude(pk=candidate.id)
    return queryset


def _candidate_saved_events(user_id: UUID, candidate: Candidate) -> QuerySet:
    low, high = _window(candidate)
    queryset = SavedEvent.objects.using(PERSONAL).filter(
        user_id=user_id, start_utc__gte=low, start_utc__lte=high
    )
    if candidate.id is not None:
        queryset = queryset.exclude(pk=candidate.id)
    return queryset


def detect_conflicts(
    *,
    user_id: UUID,
    candidate: Candidate,
    include_duplicates: bool = True,
) -> list[DetectedConflict]:
    """The conflicts the candidate has with the user's other events.

    A time conflict is two intervals overlapping by more than 15 minutes. A duplicate is two
    events whose names overlap by at least 80% on tokens and whose starts are within 24 hours.

    A pair that satisfies both rules is recorded once, as a **duplicate**: the duplicate claim
    is the stronger one (it asserts these are the same event), and `update_existing` is the
    resolution that acts on it.

    **`include_duplicates=False` drops the duplicate rule and keeps the time rule** (D12 of
    the calendar-sync design). A background import uses it: the user typed "Dinner" and
    their work calendar also has a "Dinner" is not a clash worth a prompt — it is two
    different events that happen to share a word. The time rule still applies, because an
    imported meeting that overlaps a saved one genuinely is a clash the user needs to know
    about.
    """
    found: list[DetectedConflict] = []
    for event in _candidate_personal_events(user_id, candidate):
        side = _personal_side(event)
        found.extend(_compare(candidate.side, side, include_duplicates=include_duplicates))
    for event in _candidate_saved_events(user_id, candidate):
        side = _saved_side(event)
        found.extend(_compare(candidate.side, side, include_duplicates=include_duplicates))
    return found


def _compare(
    new_side: ConflictSide,
    other: ConflictSide,
    *,
    include_duplicates: bool = True,
) -> list[DetectedConflict]:
    """The conflicts between two sides, if any. The candidate is always the new side."""
    if intervals_conflict(
        new_side.start_utc,
        new_side.end_utc,
        other.start_utc,
        other.end_utc,
    ):
        return [DetectedConflict(kind="time", new_side=new_side, other_side=other, pair_id=None)]
    if include_duplicates and is_duplicate(
        new_side.name, new_side.start_utc, other.name, other.start_utc
    ):
        return [
            DetectedConflict(kind="duplicate", new_side=new_side, other_side=other, pair_id=None)
        ]
    return []


def _pair_exists(user_id: UUID, left: ConflictSide, right: ConflictSide) -> ConflictPair | None:
    return (
        ConflictPair.objects.using(PERSONAL)
        .filter(
            user_id=user_id,
            left_kind=left.kind,
            left_id=left.id,
            right_kind=right.kind,
            right_id=right.id,
        )
        .first()
    )


def record_detected_conflicts(
    *,
    user_id: UUID,
    detected: list[DetectedConflict],
    actor: Actor,
    now: datetime,
) -> list[DetectedConflict]:
    """Write the detected pairs, and return them with their pair ids.

    A pair that already exists and is still `active` is left alone. A pair that was closed —
    resolved by the user, or cleared because a side went away — is **never re-opened**: AD-21
    says a resolved pair is immutable and never re-prompted, and the database's
    `guard_conflict_pair` trigger would refuse the write anyway. Checking first means the user
    never sees a raw `RestrictViolation`.

    A conflict whose sides have no id is **skipped**, not written. A `Candidate` may be
    detected before its row exists (`Candidate.id is None`), but a pair row stores both sides
    by id and cannot hold a NULL — so a conflict found against an unsaved candidate has
    nothing to point at. The commands call this *after* the row is written, so in practice
    every recorded conflict has two real ids; the skip is the safety net for a caller that
    breaks that order.

    Must run inside the caller's `transaction.atomic(using=PERSONAL)`.
    """
    recorded: list[DetectedConflict] = []
    for conflict in detected:
        if conflict.new_side.id is None or conflict.other_side.id is None:
            continue  # a pair names both sides by id; there is nothing to point at
        left, right = _normalise(conflict.new_side, conflict.other_side)
        existing = _pair_exists(user_id, left, right)
        if existing is not None:
            if existing.status != ConflictPair.Status.ACTIVE:
                continue  # closed: never re-prompted (AD-21)
            pair = existing
        else:
            pair = ConflictPair.objects.using(PERSONAL).create(
                user_id=user_id,
                kind=conflict.kind,
                left_kind=left.kind,
                left_id=left.id,
                right_kind=right.kind,
                right_id=right.id,
                status=ConflictPair.Status.ACTIVE,
                detected_at=now,
            )
        recorded.append(
            DetectedConflict(
                kind=conflict.kind,
                new_side=conflict.new_side,
                other_side=conflict.other_side,
                pair_id=pair.id,
            )
        )
    return recorded


def close_pairs_for_side(
    *,
    user_id: UUID,
    kind: str,
    side_id: UUID,
    now: datetime,
    keep_pair: UUID | None = None,
) -> int:
    """Close the active pairs naming one side, because that side went away.

    A delete and an unsave both end a pair without the user making a choice, so the pair
    closes as `cleared_by_state_change` — AD-21's name for "not a user resolution". The
    resolution stays NULL, which is exactly what makes a cleared pair distinguishable from a
    resolved one.

    **`keep_pair` names one pair to leave alone.** The conflict-resolution flow answers a
    prompt *and* removes a side: it records the user's answer on the pair first, then
    unsaves the saved side. Without the exclusion, the unsave would close that pair as
    `cleared_by_state_change` — NULLing the answer the user just gave and turning their
    choice into "nobody answered". The exclusion says "this pair is being answered, not
    abandoned", and it is stated explicitly rather than left to the pair's status
    happening to be `resolved` already.

    Must run inside the caller's `transaction.atomic(using=PERSONAL)`.
    """
    side_filter = Q(left_kind=kind, left_id=side_id) | Q(right_kind=kind, right_id=side_id)
    queryset = (
        ConflictPair.objects.using(PERSONAL)
        .filter(
            user_id=user_id,
            status=ConflictPair.Status.ACTIVE,
        )
        .filter(side_filter)
    )
    if keep_pair is not None:
        queryset = queryset.exclude(pk=keep_pair)
    return queryset.update(
        status=ConflictPair.Status.CLEARED_BY_STATE_CHANGE,
        resolution=None,
        resolved_at=now,
    )


def pairs_for_side(*, user_id: UUID, kind: str, side_id: UUID) -> QuerySet:
    """Every pair naming one side, active or closed."""
    side_filter = Q(left_kind=kind, left_id=side_id) | Q(right_kind=kind, right_id=side_id)
    return ConflictPair.objects.using(PERSONAL).filter(user_id=user_id).filter(side_filter)


def reconcile_pairs_for_side(
    *,
    user_id: UUID,
    kind: str,
    side_id: UUID,
    side: ConflictSide,
    now: datetime,
) -> int:
    """Close the active pairs naming one side that no longer clash, and return how many.

    A pair is a claim about two events' *current* times. When one of them moves — an edit, a
    postponement propagated onto a save — a pair that no longer overlaps has to close, or the
    `/conflicts` list would claim a clash that is not there.

    The pair closes as `cleared_by_state_change`: nobody answered it, the world moved. That is
    AD-21's name for the case, and the model's `conflict_pair_status_ck` requires the
    resolution to be NULL for it.

    Must run inside the caller's `transaction.atomic(using=PERSONAL)`.
    """
    closed = 0
    for pair in pairs_for_side(user_id=user_id, kind=kind, side_id=side_id).filter(
        status=ConflictPair.Status.ACTIVE
    ):
        other = _other_side_of(pair, kind, side_id)
        if other is None:
            continue
        if not intervals_conflict(side.start_utc, side.end_utc, other.start_utc, other.end_utc):
            pair.status = ConflictPair.Status.CLEARED_BY_STATE_CHANGE
            pair.resolution = None
            pair.resolved_at = now
            pair.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])
            closed += 1
    return closed


def _other_side_of(pair: ConflictPair, kind: str, side_id: UUID) -> ConflictSide | None:
    """The other side of a pair, read from the database, or None if it is gone."""
    if pair.left_kind == kind and pair.left_id == side_id:
        other_kind, other_id = pair.right_kind, pair.right_id
    elif pair.right_kind == kind and pair.right_id == side_id:
        other_kind, other_id = pair.left_kind, pair.left_id
    else:
        return None
    if other_kind == ConflictPair.SideKind.SAVED_EVENT:
        saved = SavedEvent.objects.using(PERSONAL).filter(pk=other_id).first()
        if saved is None:
            return None
        return _saved_side(saved)
    event = PersonalEvent.objects.using(PERSONAL).filter(pk=other_id).first()
    if event is None:
        return None
    return _personal_side(event)


__all__ = [
    "Candidate",
    "ConflictSide",
    "DetectedConflict",
    "PERSONAL_EVENT_SIDE",
    "SAVED_EVENT_SIDE",
    "close_pairs_for_side",
    "detect_conflicts",
    "pairs_for_side",
    "reconcile_pairs_for_side",
    "record_detected_conflicts",
]
