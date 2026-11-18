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
from django.db.models import Q

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
from apps.personalization.services.digest_enqueue import (
    enqueue_digest_composition_on_commit,
)
from apps.personalization.services.save_cap import check_save_allowed
from domain.errors import NotFoundError
from shared.actor import Actor
from shared.constants import SAVERS_PAGE
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

    `created` says whether this call made the save or found an existing one. The API needs
    it: a first save is a creation (201) and a repeat is the same record returned again
    (200). The save itself is idempotent either way — one row, never two.
    """

    saved: SavedEventSnapshot
    conflicts: tuple[DetectedConflict, ...] = ()
    stale: bool = False
    current_version: int | None = None
    created: bool = False


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

    **The Free-tier save cap (FR-49) is enforced here, and its position is the design.**
    The order is: the idempotence check, then the gate, then the write. A repeat save of an
    already-saved event is the same row returned again — nothing new is saved, so nothing is
    spent on it, and it is not gated. A *new* save is what the cap is about, and it is
    refused before anything is written: no partial `SavedEvent`, no audit row, no conflict
    pair. See `save_cap.py` for why the refusal cannot cost the user any time.
    """
    with transaction.atomic(using=PERSONAL):
        # The first read, inside the transaction: the version the snapshot is stamped with.
        # Reading it inside the transaction rather than outside narrows the race window to
        # the write itself — a version read before the transaction opened could be older than
        # the one the snapshot records, which would make the staleness check below useless.
        #
        # It is bounded by `now`: only an event that has not started yet is saveable. An
        # event that is not public at all — unpublished, in review, superseded — is not
        # found here either, and the save is refused with a 404.
        current = get_public_event(event_id=event_id, now=now)

        # The idempotence lookup, before the gate. A save that already exists is not a new
        # save: it is the same row, returned again (a 200 rather than a 201), and it spends
        # nothing. The gate is about how many saves a user *makes*, and a user who re-saves
        # an event they already saved has made none.
        existing = (
            SavedEvent.objects.using(PERSONAL).filter(user_id=user_id, event_id=event_id).first()
        )
        if existing is not None:
            saved = existing
            created = False
        else:
            # The gate, before the write. It refuses here — inside the transaction, before
            # any row exists — so a refused save changes nothing at all.
            check_save_allowed(user_id=user_id)
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
        # **A new save is a new candidate, so the day's empty digest is recomposed.**
        # Only a *new* one: a repeat save is the same row returned again and changes no
        # pool, so it has nothing to recompose. The composition replaces an empty digest
        # and never a composed one (AD-10).
        if created:
            enqueue_digest_composition_on_commit(user_id)

    # The third read: the check. If the catalog's version moved past the one the snapshot was
    # stamped with, a postponement landed while we were writing, and the snapshot is stale.
    #
    # It is **not** bounded by `now`. The first read already decided the event was saveable;
    # re-applying that rule here would fail the save if the event merely *started* while we
    # were writing — which is not a reason to refuse, and not a reason to lose the snapshot.
    # This read is only asking whether the version moved.
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
        created=created,
    )


def unsave_event(
    *,
    user_id: UUID,
    event_id: UUID,
    actor: Actor,
    now: datetime,
    keep_pair: UUID | None = None,
) -> None:
    """Remove a save and close the pairs it took part in (AD-21).

    The pairs close as `cleared_by_state_change`: the pair ended because a side went away,
    which AD-21 says is *not* a user resolution.

    **`keep_pair` names one pair to leave open.** The conflict-resolution flow answers a
    prompt *and* releases a save: it records the user's answer on the pair first, then
    unsaves. Without the exclusion, the unsave would close that pair as
    `cleared_by_state_change` — NULLing the answer the user just gave, and turning their
    choice into "nobody answered". The exclusion says "this pair is being answered, not
    abandoned".

    **The Reminder Plan goes with the save, and so do its pending sends.** A plan for a
    saved event is addressed by the catalog event's id and resolved through
    `reminder_plan_read.resolve_target`, which 404s once the save is gone — so a plan that
    outlives its save reads as "no plan" while still holding live `SCHEDULED_SEND` rows
    that nothing re-resolves before sending. The user would keep getting reminders for an
    event they removed, which is the opposite of what unsaving asks for.
    `delivery.remove_plans_for_targets` deletes the plan **and** cancels those sends in one
    transaction; `personalization` may not write `REMINDER_PLAN` itself (AD-16), and the
    calendar disconnect already calls the same service for the same reason
    (`calendar_connections.py`: "the target itself is gone").

    It also keeps AD-17's population well defined. Propagation iterates
    `list_savers_for_event`, and an orphaned plan's owner is not a saver — so its held
    sends would never be released by `apply_lifecycle_change` and would sit held forever,
    tripping `report_held_sends` with nothing able to clear them.
    """
    # Imported inside the function. `delivery` reaches `personalization` through
    # function-local imports throughout (`reminder_plan_read`, `scheduled_sends`) precisely
    # to keep this cycle open; a module-level import here would close it from this side.
    from apps.delivery.services.reminder_plans import remove_plans_for_targets

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
            keep_pair=keep_pair,
        )
        saved.delete()
        # After the save is gone, so the plan cannot be removed by a transaction that then
        # rolls the save back. `target_id` is the **catalog** event's id — the tree's
        # convention for a saved event's target.
        removed = remove_plans_for_targets(
            user_id=user_id,
            target_kind="saved_event",
            target_ids=(event_id,),
            actor=actor,
            now=now,
        )
        write_audit(
            actor=actor,
            action="saved_event.unsaved",
            target_type="saved_event",
            target_id=saved_id,
            details={"event_id": str(event_id), "reminder_plans_removed": removed},
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


def cancel_saved_event(
    *,
    event_id: UUID,
    user_id: UUID,
    new_version: int,
    actor: Actor,
    now: datetime,
) -> bool:
    """Apply a cancellation or supersede to one user's save. True if it applied.

    The other half of `update_saved_event_snapshot`, and deliberately its twin: the same
    version gate, the same single `personal` transaction, the same audit shape. AD-17's
    consumer calls one or the other depending on the change's kind, and a reader should see
    them as a pair.

    **No row is deleted and no flag is written.** The user made that save; it stays, and
    *whether the event is happening* is the catalog's fact, not a copy of it kept here.
    Every surface that shows a save already does a batched published read of the catalog on
    the same request (`timeline`, `conflict_list`, `digest_candidates`), and the
    `PublicEvent` it already receives carries `status`. A mirrored column would be a second
    source of truth that only this function updates — so between the cancellation and its
    propagation it would disagree with the catalog the reader has *already fetched*, making
    the column-reader staler than the one that ignores it.

    What is durable here is the **conflicts**. A pair exists because two of the user's
    events overlap in time; once one side is not happening, the overlap is not a conflict
    and the prompt should stop being asked. The pairs close as `cleared_by_state_change` —
    AD-21's own name for "a side went away, and the user did not choose this" — which keeps
    them out of `RESOLVED`, where a user's own answer lives.

    **A cancelled public event never touches a personal event** (FR-55). Only this save's
    own pairs close; the personal event on the other side of them is not read and not
    written.

    `superseded` arrives here too (AD-4). On the personal side an event replaced beyond
    ±30 days is a cancellation: AD-17 is explicit that "users are notified and re-save;
    plans are never silently migrated", so nothing follows `superseded_by`.
    """
    with transaction.atomic(using=PERSONAL):
        saved = (
            SavedEvent.objects.using(PERSONAL).filter(user_id=user_id, event_id=event_id).first()
        )
        if saved is None:
            return False
        if new_version <= saved.event_version:
            return False  # older or the same: an out-of-order or duplicate propagation
        # The version is stamped even though no snapshot field moved, so that a *later*
        # out-of-order change is still gated against this one. Without the bump, a
        # cancellation followed by the reinstatement that preceded it would both apply.
        saved.event_version = new_version
        saved.save(using=PERSONAL, update_fields=["event_version", "updated_at"])
        close_pairs_for_side(
            user_id=user_id,
            kind=ConflictPair.SideKind.SAVED_EVENT,
            side_id=saved.id,
            now=now,
        )
        write_audit(
            actor=actor,
            action="saved_event.cancelled",
            target_type="saved_event",
            target_id=saved.id,
            details={"event_id": str(event_id), "event_version": new_version},
        )
        return True


def reinstate_saved_event(
    *,
    event_id: UUID,
    user_id: UUID,
    new_version: int,
    actor: Actor,
    now: datetime,
) -> bool:
    """Reverse a cancellation for one user's save, as far as the invariants allow. True if applied.

    **The save itself comes back completely.** `cancel_saved_event` writes no flag, so there
    is none to clear: the row was never marked, and every surface reads the catalog, which
    now says `scheduled` again. The Timeline, the digest and the detail page are correct the
    moment the catalog is.

    **The conflict pairs do not, and this is a known hole — not an oversight.** Two
    invariants meet here and leave no room:

    - AD-17 requires a cancellation to *close conflicts*, which `cancel_saved_event` does as
      `cleared_by_state_change`.
    - AD-21's D24 makes a closed pair **immutable**, enforced by the `guard_conflict_pair`
      trigger (`IntegrityError: a closed ConflictPair ... is immutable`), and
      `conflict_pair_pair_uq` forbids a second row for the same two sides.

    So a pair closed by a cancellation can be neither reopened nor replaced, by this service
    or by anything else. A user whose saved event clashed with a personal event, was
    cancelled, and is then reinstated **does not get the conflict prompt back**, even though
    the clash is real again. `record_detected_conflicts` skips that pair deliberately
    ("closed: never re-prompted (AD-21)") rather than raising.

    **So this service does not re-run detection, and that is deliberate.** The obvious
    implementation calls `detect_conflicts` here, mirroring `update_saved_event_snapshot`.
    It was written that way first and a mutation proved it dead: deleting the detection
    broke no test, because there is no overlap it could find that is not already recorded.

    Every path that can bring an overlap into existence detects it as it writes —
    `save_event`, `update_saved_event_snapshot`, and `create_personal_event` /
    `update_personal_event`. A `SavedEvent` row carries no cancelled flag (that is this
    item's D1: liveness is read from the catalog, never mirrored), so a personal event
    created *while* the save was dead is detected against it at that moment, by the command
    that created it. By the time a reinstatement arrives, every live overlap already has its
    pair, and the one the cancellation closed can never come back.

    `update_saved_event_snapshot` genuinely needs its detection: the save **moved**, so the
    overlap geometry changed under rows nobody else is going to re-judge. A reinstatement
    moves nothing. Keeping a detection call here would be code that claims to restore
    conflicts while provably restoring none — worse than stating the limit.

    So what is left is the version bump and the audit row, and the version bump is the part
    that matters: without it a later out-of-order change would be gated against the
    cancellation's version instead of this one.

    Closing the hole needs a spine amendment, not a code change: either AD-17 stops closing
    conflicts on a cancellation (and the readers filter on the catalog's status instead,
    which is D1 again), or AD-21's D24 gains an exception for a pair cleared by a state
    change that later reverses. Recorded as an open amendment on the intent brief.

    **The snapshot's time is not touched.** A reinstatement says the event is happening
    again, not that it moved; a move is always its own `time_moved` change (one state change
    per kind), which `update_saved_event_snapshot` applies.
    """
    with transaction.atomic(using=PERSONAL):
        saved = (
            SavedEvent.objects.using(PERSONAL).filter(user_id=user_id, event_id=event_id).first()
        )
        if saved is None:
            return False
        if new_version <= saved.event_version:
            return False  # older or the same: an out-of-order or duplicate propagation
        saved.event_version = new_version
        saved.save(using=PERSONAL, update_fields=["event_version", "updated_at"])
        write_audit(
            actor=actor,
            action="saved_event.reinstated",
            target_type="saved_event",
            target_id=saved.id,
            details={"event_id": str(event_id), "event_version": new_version},
        )
        return True


def list_savers_for_event(
    *,
    event_id: UUID,
    after: UUID | None = None,
    limit: int = SAVERS_PAGE,
) -> list[SavedEventSnapshot]:
    """One page of the saves of one event, across all users — AD-17's reverse read.

    Every other read in this module is addressed by `(user_id, event_id)`, because every
    other caller is acting for one user. A state change names only an event, so propagation
    had nothing to iterate; this is that read. The index it uses already exists and was
    built for it: `saved_event_event_idx`, "AD-17 propagation finds every save of one event,
    across all users".

    **Keyset, not offset.** `after` is the last `id` of the previous page, and `id` is a
    UUIDv7, so ordering by it is ordering by creation. Propagation runs while people are
    saving and unsaving the same event, and an offset page skips a row whenever an earlier
    one is deleted between pages — a user silently missed by a change that reached everyone
    else. A keyset page cannot skip: it names where it stopped.

    **`limit` is a page, not a cap.** The caller pages to exhaustion; this only bounds one
    round trip, so a popular event costs many small index scans instead of one long
    transaction. A read that stopped at `limit` would make a state change reach some savers
    and not others, which is the failure AD-17's per-user idempotency exists to rule out.

    **This crosses no wall.** It reads `personal` only and returns plain data; the catalog
    event whose change prompted it is the caller's, already in hand.
    """
    if limit <= 0:
        return []
    queryset = SavedEvent.objects.using(PERSONAL).filter(event_id=event_id)
    if after is not None:
        queryset = queryset.filter(id__gt=after)
    return [_snapshot(saved) for saved in queryset.order_by("id")[:limit]]


def get_saved_event(*, user_id: UUID, event_id: UUID) -> SavedEventSnapshot:
    """One of the user's own saves, or `SavedEventNotFoundError`.

    **Keyed by the catalog event's id**, not by the save row's own id — the tree's
    convention for a saved event's target (see `delivery_messages._public_event_facts`,
    which reads the target through `get_public_event`, and `send_keys.event_reminder_key`,
    which puts the catalog event id in the key). A plan for a saved event is addressed by
    that id, so the read that resolves the target is addressed by it too.

    **A save belonging to another user reads as not found, not as forbidden.** A 403 would
    confirm that the record exists, so the endpoint could be used to probe for other
    users' saved event ids. A 404 says nothing about what exists.

    This is also what makes *"a saved event the user has since un-saved"* a 404: the save
    is the target, and without a published read for one save there is no way to tell
    "never saved" from "un-saved".
    """
    saved = SavedEvent.objects.using(PERSONAL).filter(user_id=user_id, event_id=event_id).first()
    if saved is None:
        raise SavedEventNotFoundError(details={"event_id": str(event_id)})
    return _snapshot(saved)


def list_saved_events(
    *,
    user_id: UUID,
    starts_after: datetime | None = None,
    starts_before: datetime | None = None,
    overlaps_after: datetime | None = None,
    overlaps_before: datetime | None = None,
) -> list[SavedEventSnapshot]:
    """The user's own saved events, soonest first.

    The list is scoped to `user_id` and to nothing else. A save belongs to exactly one
    user, so there is no visibility rule to apply beyond ownership — and no way to ask
    for another user's saves at all.

    The bounds are inclusive and apply to the **snapshot's** start time, not the catalog's
    current one. A save's snapshot is what the user's own calendar shows (AD-21), so the
    bound has to be applied to the same value the list returns — otherwise the filter and
    the item would disagree about which event is which.

    **The `overlaps_*` bounds ask a different question, and both kinds of bound can be
    given at once.** `starts_after` / `starts_before` ask *"which saves **start** in this
    window?"*. `overlaps_after` / `overlaps_before` ask *"which saves **touch** this
    window?"* — and the two answers differ. A save that started on the Sunday before the
    week and runs into Monday touches Monday without starting in the week, so a
    start-bounded read misses it. The Timeline needs the overlap rule; the digest's list
    needs the start rule. Each bound is optional, and with neither the list is every save
    the user has.

    **An open-ended save is never excluded by the lower overlap bound.** `end_utc` is
    nullable, and a save with no end runs from its start onward — so the filter is
    `end_utc >= window_start OR end_utc IS NULL`.

    The window's end is **exclusive**: a save starting exactly at `overlaps_before` is
    outside the window.

    **This reads the personal side only.** The display fields come from `catalog`, and the
    API layer resolves them separately, one event at a time — a save whose catalog event
    has since disappeared is the caller's to notice, not this function's to hide.
    """
    queryset = SavedEvent.objects.using(PERSONAL).filter(user_id=user_id)
    if starts_after is not None:
        queryset = queryset.filter(start_utc__gte=starts_after)
    if starts_before is not None:
        queryset = queryset.filter(start_utc__lte=starts_before)
    if overlaps_after is not None:
        queryset = queryset.filter(Q(end_utc__gte=overlaps_after) | Q(end_utc__isnull=True))
    if overlaps_before is not None:
        queryset = queryset.filter(start_utc__lt=overlaps_before)
    return [_snapshot(saved) for saved in queryset.order_by("start_utc", "id")]


__all__ = [
    "SaveResult",
    "SavedEventNotFoundError",
    "SavedEventSnapshot",
    "cancel_saved_event",
    "get_saved_event",
    "list_saved_events",
    "list_savers_for_event",
    "reinstate_saved_event",
    "save_event",
    "unsave_event",
    "update_saved_event_snapshot",
]
