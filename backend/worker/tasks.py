"""Worker tasks. Beat and the Celery app find these by dotted string (`config/celery.py`).

Each task wraps one `ingestion` command and returns None (Celery would otherwise log the return
value). Jobs are sent through `_enqueue`, the single seam tests replace.
"""

import logging
from datetime import datetime
from uuid import UUID

from celery import shared_task
from django.utils import timezone

from apps.ingestion.services import outbox, scheduling
from apps.ingestion.services.ingest_source import ingest_source as run_ingest
from apps.ingestion.services.source_registry import (
    CrawlNeedsTosReviewError,
    SourceNotFoundError,
    SourcePausedError,
)
from shared.constants import OUTBOX_RECONCILE_EVERY_MINUTES

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return timezone.now()


def _enqueue(task, *args) -> None:
    task.delay(*args)


@shared_task(name="worker.tasks.tick")
def tick() -> None:
    """The periodic tick (AD-7): the only beat entry. It enqueues and never touches the
    database, so a slow query can't delay the next tick.

    Every tick: `schedule_sources`. When the UTC minute is a multiple of 5: `reconcile_outbox`
    (the tick keeps no state, so the 5-minute cadence is approximate; both jobs are idempotent).
    """
    _enqueue(schedule_sources)
    if _now().minute % OUTBOX_RECONCILE_EVERY_MINUTES == 0:
        _enqueue(reconcile_outbox)
    logger.info("Tick", extra={"job": "tick"})


@shared_task(name="worker.tasks.schedule_sources")
def schedule_sources() -> None:
    """Flag stale sources, claim the due ones and enqueue one ingest job per claim (FR-13)."""
    now = _now()
    stale = scheduling.flag_stale_sources(now=now)
    claimed = scheduling.claim_due_sources(now=now)
    enqueued = 0
    for source_id in claimed:
        try:
            _enqueue(ingest_source, str(source_id))
            enqueued += 1
        except Exception as exc:  # broker down: free the claim so the next tick retries
            scheduling.release_claim(source_id)
            logger.warning(
                "Ingest not enqueued",
                extra={"source_id": source_id, "error_type": type(exc).__name__},
            )
    logger.info("Sources scheduled", extra={"job": "schedule_sources", "count": enqueued})
    if stale:
        logger.warning("Sources stale", extra={"job": "schedule_sources", "count": stale})


@shared_task(name="worker.tasks.ingest_source")
def ingest_source(source_id: str) -> None:
    """Run one source's ingest and release its claim, whatever happens (run-016 plan S7).

    A source refused since it was claimed (paused, crawl without approval, removed) is
    skipped quietly; any other error reaches Celery.
    """
    try:
        run_ingest(UUID(source_id))
    except (SourcePausedError, CrawlNeedsTosReviewError, SourceNotFoundError) as exc:
        logger.info("Ingest skipped", extra={"source_id": source_id, "error_code": exc.code})
    finally:
        scheduling.release_claim(UUID(source_id))


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
