"""Worker tasks. Beat and the Celery app find these by dotted string (`config/celery.py`).

Each task wraps one `ingestion` command and returns None (Celery would otherwise log the return
value). Jobs are sent through `_enqueue`, the single seam tests replace.
"""

import logging
from datetime import datetime
from uuid import UUID

from celery import shared_task
from django.utils import timezone

from apps.ingestion.event_fit.writes import refresh_stale_event_fits
from apps.ingestion.services import outbox, scheduling
from apps.ingestion.services.ingest_source import ingest_source as run_ingest
from apps.ingestion.services.source_registry import (
    CrawlNeedsTosReviewError,
    SourceNotFoundError,
    SourcePausedError,
)
from apps.personalization.services import calendar_sync, digest_scheduling
from apps.personalization.services.digest_composition import compose_digest
from ports.registry import get_calendar_port
from shared.actor import Actor
from shared.constants import (
    EVENT_FIT_REFRESH_BATCH_SIZE,
    EVENT_FIT_REFRESH_EVERY_MINUTES,
    OUTBOX_RECONCILE_EVERY_MINUTES,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return timezone.now()


def _enqueue(task, *args) -> None:
    task.delay(*args)


@shared_task(name="worker.tasks.tick")
def tick() -> None:
    """The periodic tick (AD-7): the only beat entry. It enqueues and never touches the
    database, so a slow query can't delay the next tick.

    Every tick: `schedule_sources`, `schedule_calendars` and `schedule_digests`. When the
    UTC minute is a multiple of 5: `reconcile_outbox` (the tick keeps no state, so the
    5-minute cadence is approximate; both jobs are idempotent). When the minute is a
    multiple of 15: `refresh_event_fits`, which recomputes the Event Fit rows so that
    "tonight" does not go stale (AD-10).

    The two cadences nest — every multiple of 15 is also a multiple of 5 — so the refresh
    always lands on a reconciler minute. That is a consequence of the numbers, not a
    design: the refresh's cadence is a divisor of the reconciler's, and if the two are
    ever made independent, the tick test that pins the enqueue order will say so.

    **The digest dispatcher's cadence does NOT nest, and it is not a minute-modulo
    rule.** `schedule_digests` runs on every tick because "due" is a *per-user local
    wall clock* comparison — a user whose delivery time is 9:00 becomes due at 9:00 in
    their own zone, and a minute-modulo rule would compose everyone at the same instant
    regardless of the hour they asked for. The dispatcher itself does the per-user
    comparison; the tick only asks it to look.
    """
    _enqueue(schedule_sources)
    _enqueue(schedule_calendars)
    _enqueue(schedule_digests)
    if _now().minute % OUTBOX_RECONCILE_EVERY_MINUTES == 0:
        _enqueue(reconcile_outbox)
    if _now().minute % EVENT_FIT_REFRESH_EVERY_MINUTES == 0:
        _enqueue(refresh_event_fits)
    logger.info("Tick", extra={"job": "tick"})


@shared_task(name="worker.tasks.refresh_event_fits")
def refresh_event_fits() -> None:
    """Recompute every published event's Event Fit row (AD-10, FR-26).

    **This is the staleness refresh.** "Tonight" is a statement about *now*, so a
    persisted tag goes stale as the clock moves — not only when the event changes. The
    refresh is a **writer**: it recomputes the rows and persists them, so the read path
    serves them as they stand and computes nothing (AD-10: "never recomputed at render").

    It runs on a cadence, so a tag can be up to one interval out of date. That is the
    trade-off, and it is stated in the plan rather than hidden: the alternative —
    computing at read — is what AD-10 forbids.

    The work is bounded: one pass over the published events, in batches, each batch in its
    own transaction.
    """
    written = refresh_stale_event_fits(
        now=_now(),
        actor=Actor.system("event_fit_refresh"),
        batch_size=EVENT_FIT_REFRESH_BATCH_SIZE,
    )
    logger.info("Event fits refreshed", extra={"job": "refresh_event_fits", "count": written})


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


@shared_task(name="worker.tasks.schedule_digests")
def schedule_digests() -> None:
    """Claim the users whose digest is due and enqueue one composition job per claim (D1).

    This mirrors `schedule_calendars` exactly: the tick enqueues the dispatcher, the
    dispatcher claims what is due, and each claim becomes one job. The claim is atomic
    (`FOR UPDATE SKIP LOCKED`), so two overlapping ticks never compose the same user's
    digest twice, and a claim older than `DIGEST_CLAIM_TTL` is a lost job and becomes
    claimable again.

    **"Due" is the user's own local wall clock reaching their delivery time**, and the
    dispatcher composes *at or before* that time so the digest exists when the user
    arrives. **It sends nothing** — the send is the delivery intent's job.

    A user that could not be enqueued has its claim released, so the next tick retries
    it rather than leaving it claimed until the TTL expires.
    """
    now = _now()
    claimed = digest_scheduling.claim_due_digests(now=now)
    enqueued = 0
    for user_id in claimed:
        try:
            _enqueue(compose_digest_task, str(user_id))
            enqueued += 1
        except Exception as exc:  # broker down: free the claim so the next tick retries
            digest_scheduling.release_claim(user_id)
            logger.warning(
                "Digest not enqueued",
                extra={"user_id": str(user_id), "error_type": type(exc).__name__},
            )
    logger.info("Digests scheduled", extra={"job": "schedule_digests", "count": enqueued})


@shared_task(name="worker.tasks.compose_digest")
def compose_digest_task(user_id: str) -> None:
    """Compose one user's digest and release the claim, whatever happens (D4).

    **The composition is idempotent.** A digest already exists for this `(user,
    local_date)`, so the service returns it with `created=False` and writes nothing. A
    duplicated job — the first one lost to a broker hiccup, a retried enqueue — is
    therefore harmless, and does not need a de-duplication of its own.

    **The claim is released in a `finally`**, so a crash cannot leave a user claimed
    until the TTL expires. An unexpected error is re-raised so Celery sees it and the
    job is retried; the log line names the job and the error's type, and **no PII**
    (AD-13) — a user id is a UUID, and it is already one indexed read away.
    """
    identifier = UUID(user_id)
    try:
        result = compose_digest(
            user_id=identifier,
            actor=Actor.system("digest_composer"),
            now=_now(),
        )
        logger.info(
            "Digest composed",
            extra={
                "job": "compose_digest",
                "user_id": str(identifier),
                # Not `created`: `LogRecord` already has a field by that name, and
                # `extra` may not shadow one.
                "digest_created": result.created,
                "is_empty": result.is_empty,
            },
        )
    except Exception as exc:
        logger.warning(
            "Digest composition failed",
            extra={
                "job": "compose_digest",
                "user_id": str(identifier),
                "error_type": type(exc).__name__,
            },
        )
        raise
    finally:
        digest_scheduling.release_claim(identifier)
