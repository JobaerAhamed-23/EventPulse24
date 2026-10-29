"""The save commands (AD-21, FR-33): save a public event, unsave it, and re-stamp its snapshot.

A save is a **personal record**: a `SavedEvent` row in `personal` holding the catalog Event's
id *by value* plus a snapshot of its time. The Timeline and conflict detection read the
snapshot and never join `catalog` (AD-21).

The interesting part is the race. AD-21: "A save re-reads the Event's version after commit and
requests re-propagation for that user if it moved meanwhile, so a save racing a postponement
cannot keep a stale snapshot." AD-3 forbids a transaction spanning `catalog` and `personal`, so
the protocol is necessarily:

    read the catalog version   (inside the personal-only transaction)
    write the snapshot          (in the same transaction)
    commit
    read the catalog version   (non-transactional)
    if it moved, the snapshot is stale — say so

The first read is inside the transaction on purpose: a version read before the transaction
opened could be older than the one the snapshot records, which would make the check after the
commit meaningless.

This is the same shape AD-17's sweep uses: "the claim transaction is **`personal`-only** ...
the sweep reads the Event's current `event_version` through `ingestion`'s read interface — a
separate, non-transactional read."

The catalog is read through `ingestion`'s published interface, which hands over plain data
(`PublicEvent`), so this module never imports `apps.ingestion.models` and the wall holds
without either side knowing the other's models.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.ingestion.services.catalog_read import get_public_event
from apps.personalization.models import ConflictPair, SavedEvent
from apps.personalization.services.audit import write_audit
from apps.personalization.services.conflicts import (
    Candidate,
    DetectedConflict,
    close_pairs_for_side,
    detect_conflicts,
    reconcile_pairs_for_side,
    record_detected_conflicts,
)
from domain.errors import NotFoundError
from shared.actor import Actor
from shared.db import PERSONAL


class SavedEventNotFoundError(NotFoundError):
    """The save doesn't exist, or isn't the caller's."""

    default_message = "We couldn't find that saved event."


@dataclass(frozen=True)
class SavedEventSnapshot:
    """A save as plain data."""

    id: UUID
    user_id: UUID
    event_id: UUID
    start_utc: datetime
    end_utc: datetime | None
    event_version: int


@dataclass(frozen=True)
class SaveResult:
    """The outcome of a save.

    `stale` says the snapshot may already be out of date: the catalog's version moved between
    the read that stamped the snapshot and the read that checked it. The caller asks for
    re-propagation for that user — it does not repair the snapshot itself, because repairing
    it is the propagation service's job (`update_saved_event_snapshot`).
    """

    saved: SavedEventSnapshot
    conflicts: tuple[DetectedConflict, ...] = ()
    stale: bool = False
    current_version: int | None = None


def _snapshot(saved: SavedEvent) -> SavedEventSnapshot:
    return SavedEventSnapshot(
        id=saved.id,
        user_id=saved.user_id,
        event_id=saved.event_id,
        start_utc=saved.start_utc,
        end_utc=saved.end_utc,
        event_version=saved.event_version,
    )


def save_event(
    *,
    user_id: UUID,
    event_id: UUID,
    actor: Actor,
    now: datetime,
) -> SaveResult:
    """Save a public event, with the AD-21 race protocol (AD-21, FR-33).

    The snapshot is stamped with the catalog Event's version, read **inside** the transaction
    immediately before the write — reading it outside would widen the race window to the whole
    transaction. After the commit the version is read again; if it moved, the result says the
    snapshot is stale and the caller requests re-propagation.

    Saving the same event twice is idempotent: one row, not two.
    """
    with transaction.atomic(using=PERSONAL):
        # The first read, inside the transaction: the version the snapshot is stamped with.
        # Reading it inside the transaction rather than outside narrows the race window to
        # the write itself — a version read before the transaction opened could be older than
        # the one the snapshot records, which would make the staleness check below useless.
        current = get_public_event(event_id=event_id)
        saved, created = SavedEvent.objects.using(PERSONAL).update_or_create(
            user_id=user_id,
            event_id=event_id,
            defaults={
                "start_utc": current.start_time_utc,
                "end_utc": current.end_time_utc,
                "event_version": current.event_version,
                "saved_at": now,
            },
        )
        candidate = Candidate(
            kind=ConflictPair.SideKind.SAVED_EVENT,
            id=saved.id,
            # A saved public event has no name in `personal`: the title lives in `catalog` and
            # is not copied into the snapshot. The catalog's title is used for the duplicate
            # rule, which is the only rule that needs one.
            name=current.title,
            start_utc=saved.start_utc,
            end_utc=saved.end_utc,
        )
        detected = detect_conflicts(user_id=user_id, candidate=candidate)
        conflicts = tuple(
            record_detected_conflicts(user_id=user_id, detected=detected, actor=actor, now=now)
        )
        write_audit(
            actor=actor,
            action="saved_event.saved",
            target_type="saved_event",
            target_id=saved.id,
            details={
                "event_id": str(event_id),
                "event_version": current.event_version,
                "created": created,
                "conflicts": [c.kind for c in conflicts],
            },
        )
        snapshot = _snapshot(saved)

    # The third read: the check. If the catalog's version moved past the one the snapshot was
    # stamped with, a postponement landed while we were writing, and the snapshot is stale.
    after = get_public_event(event_id=event_id)
    stale = after.event_version > current.event_version
    if stale:
        write_audit(
            actor=actor,
            action="saved_event.stale_detected",
            target_type="saved_event",
            target_id=snapshot.id,
            details={
                "event_id": str(event_id),
                "stamped_version": current.event_version,
                "current_version": after.event_version,
                "repropagation_requested": True,
            },
        )
    return SaveResult(
        saved=snapshot,
        conflicts=conflicts,
        stale=stale,
        current_version=after.event_version,
    )


def unsave_event(
    *,
    user_id: UUID,
    event_id: UUID,
    actor: Actor,
    now: datetime,
) -> None:
    """Remove a save and close the pairs it took part in (AD-21).

    The pairs close as `cleared_by_state_change`: the pair ended because a side went away,
    which AD-21 says is *not* a user resolution.
    """
    with transaction.atomic(using=PERSONAL):
        saved = (
            SavedEvent.objects.using(PERSONAL).filter(user_id=user_id, event_id=event_id).first()
        )
        if saved is None:
            raise SavedEventNotFoundError(details={"event_id": str(event_id)})
        saved_id = saved.id
        close_pairs_for_side(
            user_id=user_id,
            kind=ConflictPair.SideKind.SAVED_EVENT,
            side_id=saved_id,
            now=now,
        )
        saved.delete()
        write_audit(
            actor=actor,
            action="saved_event.unsaved",
            target_type="saved_event",
            target_id=saved_id,
            details={"event_id": str(event_id)},
        )


def update_saved_event_snapshot(
    *,
    event_id: UUID,
    user_id: UUID,
    new_version: int,
    new_start_utc: datetime,
    new_end_utc: datetime | None,
    actor: Actor,
    now: datetime,
) -> bool:
    """Re-stamp a save's snapshot after a catalog change. True if it applied.

    This is the service AD-17's propagation job calls: "**`personalization`** updates the
    `SAVED_EVENT` snapshot and re-evaluates `CONFLICT_PAIR`s (AD-21)."

    The change applies **only if** `new_version` is greater than the version already stored —
    so a retried, partial or out-of-order propagation can neither double-apply nor let an
    older postponement overwrite a newer one.

    The conflicts are re-evaluated here too, because a moved event changes whether it still
    clashes with the user's personal events.
    """
    with transaction.atomic(using=PERSONAL):
        saved = (
            SavedEvent.objects.using(PERSONAL).filter(user_id=user_id, event_id=event_id).first()
        )
        if saved is None:
            return False
        if new_version <= saved.event_version:
            return False  # older or the same: an out-of-order or duplicate propagation
        saved.start_utc = new_start_utc
        saved.end_utc = new_end_utc
        saved.event_version = new_version
        saved.save(update_fields=["start_utc", "end_utc", "event_version", "updated_at"])
        candidate = Candidate(
            kind=ConflictPair.SideKind.SAVED_EVENT,
            id=saved.id,
            name=f"saved {event_id}",
            start_utc=new_start_utc,
            end_utc=new_end_utc,
        )
        # The save moved, so the pairs that referenced its old time are re-judged: one that no
        # longer overlaps closes, one that still overlaps stays, and a new overlap creates a
        # new pair.
        reconcile_pairs_for_side(
            user_id=user_id,
            kind=ConflictPair.SideKind.SAVED_EVENT,
            side_id=saved.id,
            side=candidate.side,
            now=now,
        )
        detected = detect_conflicts(user_id=user_id, candidate=candidate)
        record_detected_conflicts(user_id=user_id, detected=detected, actor=actor, now=now)
        write_audit(
            actor=actor,
            action="saved_event.snapshot_updated",
            target_type="saved_event",
            target_id=saved.id,
            details={
                "event_id": str(event_id),
                "event_version": new_version,
                "start_utc": new_start_utc.isoformat(),
            },
        )
        return True


__all__ = [
    "SaveResult",
    "SavedEventNotFoundError",
    "SavedEventSnapshot",
    "save_event",
    "unsave_event",
    "update_saved_event_snapshot",
]
