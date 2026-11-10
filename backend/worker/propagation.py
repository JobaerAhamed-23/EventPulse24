"""AD-17's propagation consumer: one catalog state change, applied to every user it touches.

This is the caller between two finished halves. `ingestion` appends a versioned
`EVENT_STATE_CHANGE` in the same `catalog` transaction as the change and enqueues on commit;
`personalization` and `delivery` each publish a version-gated service that applies it. Nothing
joined them until now.

**It lives in `worker` rather than in an app, on purpose.** AD-17's "Prevents" clause names
"`ingestion` reaching across the wall to fix it directly", and a loop inside `apps.ingestion`
that writes `personal` through published services would satisfy every import contract while
reading as exactly that. It is also nobody's flow: `personalization` owns saves, `delivery`
owns sends, `ingestion` owns the catalog, and the propagation is the *job* that joins them.

**It writes nothing itself.** Every mutation goes through the owning module's published
command (AD-16), and this module imports no app's models.

**There is no per-user marker, and that is the design.** AD-17 keys propagation
`(state_change_id, user_id)`, which reads like a table of "user 7 is done with change X". It
is not needed, because every service called here is version-gated *and* stores the version it
applied on the row it applied it to — `SavedEvent.event_version`, `ScheduledSend.event_version`,
`StateChangeNotice.event_version`. That is the same fact a marker would hold, written in the
same transaction as the work it describes, so it cannot disagree with it. A retried partial run
re-walks every saver; the ones already applied cost one indexed read each and change nothing.

**So this module adds no gate of its own.** A second gate in the caller could refuse work a
service would have accepted, and nothing would ever come back to repair it.

**The order is personalization, then delivery, then the notice**, and only one order is
survivable. AD-3 forbids a transaction spanning the two schemas, so a crash between them is
permanent. Sends-first would leave a user whose reminders are re-minted for the new time while
their Timeline still shows the old one — a reminder contradicting the calendar it came from.
Snapshot-first leaves sends carrying the old version, which the sweep's AD-17 guard already
*holds* rather than sends; the next tick rewrites them. The notice is last because it describes
a state both halves have made true.
"""

import logging
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from apps.delivery.services.reminder_plan_read import (
    ReminderTargetNotFoundError,
    resolve_target,
)
from apps.delivery.services.reminder_plans import ReminderPlanNotFoundError, get_plan
from apps.delivery.services.scheduled_sends import apply_lifecycle_change
from apps.delivery.services.state_notices import raise_state_notice
from apps.ingestion.services import outbox
from apps.ingestion.services.catalog_read import get_public_events
from apps.personalization.services.saved_events import (
    cancel_saved_event,
    list_savers_for_event,
    reinstate_saved_event,
    update_saved_event_snapshot,
)
from shared.actor import Actor
from shared.constants import (
    LIFECYCLE_PERSONAL_BEHAVIOUR,
    SAVERS_PAGE,
    LifecyclePersonalBehaviour,
)

logger = logging.getLogger(__name__)


class PropagationCursorStalled(RuntimeError):
    """The keyset cursor did not move between pages (a programming error).

    Raised rather than tolerated because the alternative is silent: a worker that re-reads
    page one forever makes no progress, raises nothing, and looks exactly like a slow job.
    """


#: The actor every write in this job is attributed to (AD-5). A system actor, because no user
#: asked for any of it: a source changed and the tree is catching up.
PROPAGATOR = Actor.system("propagation")


@dataclass(frozen=True)
class PropagationResult:
    """What one run of one state change did.

    `failed` is the count of users whose apply raised. It is what decides whether
    `propagated_at` is set: a change is propagated only when *every* affected user is done
    (AD-17), so a single failure leaves the row for the reconciler to re-offer.
    """

    state_change_id: UUID
    users: int = 0
    applied: int = 0
    failed: int = 0
    marked: bool = False
    missing: bool = False


def propagate(*, state_change_id: UUID, now: datetime) -> PropagationResult:
    """Apply one state change to every user who saved its event. AD-17's consumer.

    **A change with no savers is the common case and must be the fast one.** An unsaved
    event's state change touches nobody, and it marks propagated immediately rather than
    churning the outbox until the reconciler gives up — which it never would, since there is
    no attempts counter on an append-only row.

    **`mark_propagated` runs only when nothing raised.** A partial run leaves the row
    unpropagated, the reconciler re-offers it, the users already applied no-op, and the rest
    are retried. That is the whole recovery story, and it needs no state beyond the versions
    the services already store.
    """
    change = outbox.get_state_change(state_change_id)
    if change is None:
        # The row is gone. Nothing to do, and doing something would be the bug.
        logger.debug("State change not found", extra={"state_change_id": str(state_change_id)})
        return PropagationResult(state_change_id=state_change_id, missing=True)

    if change.propagated_at is not None:
        # Already done. The reconciler and a retried enqueue can both land here.
        return PropagationResult(state_change_id=state_change_id, marked=False)

    # **One catalog read for the whole change, not one per user.** Every user is notified
    # about the same event, so the event's current start is the same fact for all of them.
    # `get_public_events` is a batch read precisely so a caller with many events pays one
    # round-trip; asking it once per saver would undo that on the one path that scales with
    # the saver count.
    event_start = _current_start(change.event_id)

    result = _apply_to_savers(change=change, now=now, event_start=event_start)

    if result.failed == 0:
        marked = outbox.mark_propagated(state_change_id, now=now)
        result = PropagationResult(
            state_change_id=state_change_id,
            users=result.users,
            applied=result.applied,
            failed=0,
            marked=marked,
        )
    return result


def _apply_to_savers(
    *, change: outbox.StateChangeFacts, now: datetime, event_start: datetime | None
) -> PropagationResult:
    """Walk every saver of the event, one page and one user at a time.

    **Keyset-paged, not offset** (`list_savers_for_event`): propagation runs while people are
    saving and unsaving the same event, and an offset page skips a row whenever an earlier one
    is deleted between pages — a user silently missed by a change that reached everyone else.

    **One user's failure does not stop the others.** The loop records it and continues, so a
    single poisoned row cannot hold a popular event's whole propagation hostage. The change
    stays unpropagated, which is what surfaces it.
    """
    users = applied = failed = 0
    after: UUID | None = None

    while True:
        page = list_savers_for_event(event_id=change.event_id, after=after, limit=SAVERS_PAGE)
        if not page:
            break
        for saver in page:
            users += 1
            try:
                _apply_to_user(
                    change=change, user_id=saver.user_id, now=now, event_start=event_start
                )
            except Exception:  # noqa: BLE001 — one user's failure is not the job's
                failed += 1
                # **Ids only, never a title or an address** (AD-13). The event's title lives
                # in `catalog` and a user's address in `identity`; neither belongs in a log
                # line, and the two ids are enough to replay this by hand.
                logger.exception(
                    "Propagation failed for one user",
                    extra={
                        "job": "propagate_state_change",
                        "state_change_id": str(change.id),
                        "event_id": str(change.event_id),
                        "user_id": str(saver.user_id),
                        "kind": change.kind,
                    },
                )
            else:
                applied += 1
        # **The cursor must strictly advance, and this says so out loud.** It does today:
        # `list_savers_for_event` orders by `id` and filters `id__gt=after`, so each page
        # starts past the last. But the failure mode if that ever stopped being true is a
        # worker looping on page one forever — no error, no progress, and a job that cannot
        # be distinguished from a slow one. A programming error should be loud, so it is
        # raised rather than tolerated, and it escapes the per-user handler deliberately:
        # this is not one user's failure.
        if after is not None and page[-1].id <= after:
            raise PropagationCursorStalled(
                f"saver cursor did not advance past {after} for state change {change.id}"
            )
        after = page[-1].id

    return PropagationResult(state_change_id=change.id, users=users, applied=applied, failed=failed)


def _apply_to_user(
    *, change: outbox.StateChangeFacts, user_id: UUID, now: datetime, event_start: datetime | None
) -> None:
    """Apply one change to one user: snapshot, then sends, then the notice.

    Each step is its own `personal` transaction, inside the service that owns it. They are
    deliberately **not** wrapped in one transaction here: AD-17 asks for the *user* to be the
    unit, and each service already makes its own write atomic. Wrapping them would also put a
    `personal` transaction around the catalog read `delivery` needs, which is the shape AD-3
    exists to forbid.
    """
    behaviour = LIFECYCLE_PERSONAL_BEHAVIOUR[change.kind]

    if behaviour is LifecyclePersonalBehaviour.RESTAMP:
        start_utc, end_utc = _moved_times(change)
        if start_utc is not None:
            update_saved_event_snapshot(
                event_id=change.event_id,
                user_id=user_id,
                new_version=change.event_version,
                new_start_utc=start_utc,
                new_end_utc=end_utc,
                actor=PROPAGATOR,
                now=now,
            )
    elif behaviour is LifecyclePersonalBehaviour.CANCEL:
        cancel_saved_event(
            event_id=change.event_id,
            user_id=user_id,
            new_version=change.event_version,
            actor=PROPAGATOR,
            now=now,
        )
    elif behaviour is LifecyclePersonalBehaviour.REINSTATE:
        reinstate_saved_event(
            event_id=change.event_id,
            user_id=user_id,
            new_version=change.event_version,
            actor=PROPAGATOR,
            now=now,
        )
    # `NONE` writes nothing on the personal side: see `LIFECYCLE_PERSONAL_BEHAVIOUR`.

    _apply_sends(change=change, user_id=user_id, now=now)

    raise_state_notice(
        user_id=user_id,
        event_id=change.event_id,
        state_change_id=change.id,
        change_kind=change.kind,
        event_version=change.event_version,
        event_start_utc=event_start,
        actor=PROPAGATOR,
        now=now,
        # **The change's own facts, by value.** `raise_state_notice` decides whether a
        # `detail_changed` is worth notifying — a venue move is the PRD's "moved to [new
        # location]", a typo fix is not — and that decision is about the change rather
        # than the kind. Passing the facts by value keeps AD-3's wall intact: no
        # transaction here spans `catalog` and `personal`.
        before=change.before,
        after=change.after,
    )


def _apply_sends(*, change: outbox.StateChangeFacts, user_id: UUID, now: datetime) -> None:
    """The `delivery` half: rewrite, cancel or re-stamp this user's sends for the event.

    **Every kind reaches here, including the two the personal side skips.** A `sold_out` or
    `detail_changed` moves nothing the snapshot stores, but it still bumps the catalog's
    version — so the sweep's AD-17 guard has already *held* this user's pending sends, and
    `apply_lifecycle_change`'s `KEEP` branch clearing `held_at` is the hold's only exit.

    **The target is resolved through `reminder_plan_read.resolve_target`**, the one resolver
    the plan's read and write already share, so this job cannot disagree with the rest of the
    tree about what a target is. A target that no longer resolves — the save is gone — means
    there is nothing of this user's to rewrite.
    """
    try:
        target = resolve_target(
            user_id=user_id, target_kind="saved_event", target_id=change.event_id
        )
    except ReminderTargetNotFoundError:
        return

    # **The version comes from the change, not from the resolved target.** `resolve_target`
    # reads it off the `SavedEvent` snapshot, and for a `sold_out` or `detail_changed` the
    # snapshot deliberately never moves (`LIFECYCLE_PERSONAL_BEHAVIOUR`) — so the target
    # would carry the *old* version, `apply_lifecycle_change` would find nothing stale, and
    # `held_at` would never be cleared. The hold's only exit would silently stop working for
    # exactly the two kinds that most often cause one.
    target = replace(target, version=change.event_version)

    try:
        slots = get_plan(
            user_id=user_id, target_kind="saved_event", target_id=change.event_id
        ).slots
    except ReminderPlanNotFoundError:
        # A save with no Reminder Plan is the ordinary case — `save_event` attaches none.
        # There is nothing to re-mint, but the lifecycle still has to run: a `KEEP` change
        # re-stamps and releases held rows, and a `CANCEL` cancels whatever is pending.
        slots = ()

    apply_lifecycle_change(
        user_id=user_id,
        target=target,
        kind=change.kind,
        slots=slots,
        actor=PROPAGATOR,
        now=now,
    )


def _moved_times(change: outbox.StateChangeFacts) -> tuple[datetime | None, datetime | None]:
    """The new start and end this change carries, or `(None, None)` if it carries no time.

    Read from the change's own `after`, never from the live Event. A poll appends one state
    change per kind, so the live Event already holds the *last* kind's facts — pairing this
    change's version with those times would stamp a snapshot that never existed.
    """
    start = change.after.get("start_utc")
    if start is None:
        return None, None
    return _as_datetime(start), _as_datetime(change.after.get("end_utc"))


def _as_datetime(value) -> datetime | None:
    """`before`/`after` are JSON, so an instant comes back as an ISO string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _current_start(event_id: UUID) -> datetime | None:
    """The event's current start, for the notice's Quiet-Hours lead margin.

    **Deliberately the live value and not the change's.** The margin asks "would deferring
    this notice push it past the point of being useful", which is a question about when the
    event *now* starts. None when the catalog no longer holds it — a supersede, or a source
    that dropped it — and the notice is then deferred unconditionally, because there is no
    start to be late for.

    **Called once per state change, not once per user.** Every user is notified about the
    same event, so the answer is the same for all of them; asking the catalog again for each
    saver would turn one read into one-per-saver on the one path that scales with the saver
    count.
    """
    public = get_public_events(event_ids={event_id}).get(event_id)
    return public.start_time_utc if public is not None else None


def count_stuck_propagations(*, now: datetime) -> int:
    """How many state changes have gone unpropagated past the alarm threshold.

    Published for `worker.tasks.report_stuck_propagation`, which reports and never repairs:
    `EventStateChange` is append-only, so there is no counter to retire a poisoned change
    with, and marking it propagated to stop the churn would claim a propagation that never
    happened.
    """
    from shared.constants import PROPAGATION_ALARM_AFTER

    return outbox.count_unpropagated_since(cutoff=now - PROPAGATION_ALARM_AFTER)


__all__ = [
    "PROPAGATOR",
    "PropagationCursorStalled",
    "PropagationResult",
    "count_stuck_propagations",
    "propagate",
]
