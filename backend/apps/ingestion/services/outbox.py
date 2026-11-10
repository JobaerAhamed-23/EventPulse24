"""The AD-17 outbox: enqueue propagation for committed state changes, and the reconciler that
re-enqueues the ones nobody has propagated.

`ingestion` can't import `worker` or `config` (layers), so jobs are sent by task name through
the Celery app `config/__init__` loads. `_send` is the single seam; tests replace it.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from celery import current_app
from django.utils import timezone

from apps.ingestion.models import EventStateChange
from shared.constants import OUTBOX_RECONCILE_AFTER, OUTBOX_RECONCILE_BATCH
from shared.db import CATALOG

PROPAGATE_TASK = "worker.tasks.propagate_state_change"


@dataclass(frozen=True)
class StateChangeFacts:
    """One `EVENT_STATE_CHANGE` as plain data.

    Deliberately not the model, matching `catalog_read.PublicEvent`: the consumer of this
    outbox is `worker`, which may not import `apps.ingestion.models` (AD-2), and a caller
    holding the model could write it — `ingestion` is the sole writer of `catalog` (AD-4).

    `before` and `after` carry **only the facts this kind changed** (`event_writes._kind_facts`),
    so `after` has `start_utc` for a `time_moved` and nothing of the sort for a `sold_out`.
    The propagation reads the new time from here rather than from the live Event, because a
    poll appends one change per kind and the live Event already holds the *last* kind's
    facts — pairing this change's version with those times would be wrong whenever more than
    one change is in flight.
    """

    id: UUID
    event_id: UUID
    kind: str
    event_version: int
    before: dict[str, Any]
    after: dict[str, Any]
    occurred_at: datetime
    propagated_at: datetime | None


def get_state_change(state_change_id: UUID) -> StateChangeFacts | None:
    """One state change as plain data, or None when there is no such row.

    None rather than an exception: a task holding an id for a row that no longer exists has
    nothing to do, and that is not an error worth waking anyone for.
    """
    row = EventStateChange.objects.using(CATALOG).filter(pk=state_change_id).first()
    if row is None:
        return None
    return StateChangeFacts(
        id=row.id,
        event_id=row.event_id,
        kind=row.kind,
        event_version=row.event_version,
        before=dict(row.before),
        after=dict(row.after),
        occurred_at=row.occurred_at,
        propagated_at=row.propagated_at,
    )


def count_unpropagated_since(*, cutoff: datetime) -> int:
    """How many state changes have been unpropagated since before `cutoff` (AD-17).

    **Published for the worker's alarm, because `EventStateChange` is append-only.** There is
    no attempts counter to bound a poisoned change with — `append_only_mutable` is
    `{"propagated_at"}` and the trigger binds every role — so the bound is on *silence*: a
    change nobody can propagate is surfaced rather than timed out. Setting `propagated_at`
    to stop the churn would claim a propagation that never happened and strand that user on
    the old state forever.
    """
    return (
        EventStateChange.objects.using(CATALOG)
        .filter(propagated_at__isnull=True, occurred_at__lt=cutoff)
        .count()
    )


def _send(task_name: str, args: list[str]) -> None:
    current_app.send_task(task_name, args=args)


def enqueue_propagation(state_change_id: UUID) -> None:
    """Queue one state change for propagation. Run it from `on_commit(using=CATALOG)` only."""
    _send(PROPAGATE_TASK, [str(state_change_id)])


def mark_propagated(state_change_id: UUID, *, now: datetime | None = None) -> bool:
    """Record that a state change reached `personal` (design D23). False if it already had.

    The conditional form is idempotent under the job's retries and the reconciler.
    """
    updated = (
        EventStateChange.objects.using(CATALOG)
        .filter(pk=state_change_id, propagated_at__isnull=True)
        .update(propagated_at=now or timezone.now())
    )
    return updated == 1


def reconcile_outbox(*, now: datetime | None = None, limit: int = OUTBOX_RECONCILE_BATCH) -> int:
    """Re-enqueue the oldest state changes unpropagated for longer than
    `OUTBOX_RECONCILE_AFTER`, at most `limit` of them. Returns how many were enqueued.
    """
    cutoff = (now or timezone.now()) - OUTBOX_RECONCILE_AFTER
    ids = list(
        EventStateChange.objects.using(CATALOG)
        .filter(propagated_at__isnull=True, occurred_at__lt=cutoff)
        .order_by("occurred_at", "id")
        .values_list("id", flat=True)[:limit]
    )
    for state_change_id in ids:
        enqueue_propagation(state_change_id)
    return len(ids)
