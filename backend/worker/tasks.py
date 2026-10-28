"""Worker tasks. Beat and the Celery app find these by dotted string (`config/celery.py`)."""

import logging

from celery import shared_task

from apps.ingestion.services import outbox

logger = logging.getLogger(__name__)


@shared_task(name="worker.tasks.tick")
def tick() -> None:
    """The periodic tick (AD-7 seed). Logs and does nothing else yet.

    The due-index sweep and the AD-17 outbox reconciler attach here later. Tasks return
    nothing: Celery's own log lines would otherwise carry the return value.
    """
    logger.info("Tick", extra={"job": "tick"})


@shared_task(name="worker.tasks.propagate_state_change")
def propagate_state_change(state_change_id: str) -> None:
    """AD-17 placeholder consumer: no propagation into `personal` exists yet (FR-53-55).

    It deliberately leaves `propagated_at` NULL: marking the row would claim a propagation that
    never happened, and the real consumer would then skip it. The reconciler keeps re-offering
    it until that consumer arrives.
    """
    logger.debug("State change not propagated yet", extra={"state_change_id": state_change_id})


@shared_task(name="worker.tasks.reconcile_outbox")
def reconcile_outbox() -> None:
    """Re-enqueue state changes left unpropagated (AD-17). Scheduled by ingestion-scheduling."""
    count = outbox.reconcile_outbox()
    logger.info("Outbox reconciled", extra={"job": "reconcile_outbox", "count": count})
