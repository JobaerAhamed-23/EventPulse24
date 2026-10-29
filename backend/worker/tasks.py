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
from apps.personalization.services import calendar_sync
from ports.registry import get_calendar_port
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

    Every tick: `schedule_sources` and `schedule_calendars`. When the UTC minute is a multiple of 5:
    `reconcile_outbox` (the tick keeps no state, so the 5-minute cadence is approximate; both jobs
    are idempotent).
    """
    _enqueue(schedule_sources)
    _enqueue(schedule_calendars)
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


@shared_task(name="worker.tasks.schedule_calendars")
def schedule_calendars() -> None:
    """Claim the due calendar connections and enqueue one sync job per claim (D8).

    This mirrors `schedule_sources` exactly: the tick enqueues the dispatcher, the
    dispatcher claims what is due, and each claim becomes one job. The claim is atomic
    (`FOR UPDATE SKIP LOCKED`), so two overlapping ticks never sync the same connection
    twice, and a claim older than `CALENDAR_CLAIM_TTL` is a lost job and becomes claimable
    again.

    A connection that could not be enqueued has its claim released, so the next tick
    retries it rather than leaving it claimed until the TTL expires.
    """
    now = _now()
    claimed = calendar_sync.claim_due_connections(now=now)
    enqueued = 0
    for connection_id in claimed:
        try:
            _enqueue(sync_calendar, str(connection_id))
            enqueued += 1
        except Exception as exc:  # broker down: free the claim so the next tick retries
            calendar_sync.release_claim(connection_id)
            logger.warning(
                "Calendar sync not enqueued",
                extra={"connection_id": str(connection_id), "error_type": type(exc).__name__},
            )
    logger.info("Calendars scheduled", extra={"job": "schedule_calendars", "count": enqueued})


@shared_task(name="worker.tasks.sync_calendar")
def sync_calendar(connection_id: str) -> None:
    """Sync one connected calendar and release its claim, whatever happens (D8).

    The sync's own failures are recorded on the connection — a revoked credential marks the
    connection `needs_reconnect` and keeps the imported events (D6) — so they do not reach
    Celery as a retry. A revoked credential will not become valid by trying again.

    **An unexpected failure is recorded too.** The four failures the sync handles each
    write the next poll time. An error it does not handle would skip that, and the
    connection would be due again on the very next 60-second tick — and on every tick
    after that, forever, fetching the user's calendar 1,440 times a day. So the error is
    recorded on the row before the claim is released, and the connection is retried at the
    poll cadence rather than the tick cadence.
    """
    identifier = UUID(connection_id)
    try:
        calendar_sync.sync_calendar(
            connection_id=identifier,
            port=get_calendar_port(),
            now=_now(),
        )
    except Exception as exc:
        calendar_sync.record_unexpected_failure(
            connection_id=identifier,
            error_kind=f"unexpected:{type(exc).__name__}",
            now=_now(),
        )
        logger.warning(
            "Calendar sync failed unexpectedly",
            extra={"connection_id": str(identifier), "error_type": type(exc).__name__},
        )
        raise
    finally:
        calendar_sync.release_claim(identifier)


@shared_task(name="worker.tasks.reconcile_outbox")
def reconcile_outbox() -> None:
    """Re-enqueue state changes left unpropagated (AD-17). Scheduled by ingestion-scheduling."""
    count = outbox.reconcile_outbox()
    logger.info("Outbox reconciled", extra={"job": "reconcile_outbox", "count": count})
