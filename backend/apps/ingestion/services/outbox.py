"""The AD-17 outbox: enqueue propagation for committed state changes, and the reconciler that
re-enqueues the ones nobody has propagated.

`ingestion` can't import `worker` or `config` (layers), so jobs are sent by task name through
the Celery app `config/__init__` loads. `_send` is the single seam; tests replace it.
"""

from datetime import datetime
from uuid import UUID

from celery import current_app
from django.utils import timezone

from apps.ingestion.models import EventStateChange
from shared.constants import OUTBOX_RECONCILE_AFTER, OUTBOX_RECONCILE_BATCH
from shared.db import CATALOG

PROPAGATE_TASK = "worker.tasks.propagate_state_change"


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
