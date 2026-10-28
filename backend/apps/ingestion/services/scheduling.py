"""Ingestion scheduling commands (FR-13 freshness, AD-7): which sources run, and which are stale.

The 60 s tick never touches the database; it enqueues `worker.tasks.schedule_sources`, which
calls these. Claims are taken with `FOR UPDATE SKIP LOCKED`, so two schedulers never claim one
source, and a claimed source is never enqueued again until its job releases it or the claim
expires (`INGEST_CLAIM_TTL`). The pipeline's own run lock is the backstop (run-015 D2).
"""

from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.db.models import DateTimeField, DurationField, ExpressionWrapper, F, Q, Value

from apps.ingestion.models import AcquisitionMethod, Source
from apps.ingestion.services.audit import write_audit
from shared.actor import Actor
from shared.constants import INGEST_CLAIM_TTL, SCHEDULE_BATCH, STALE_AFTER_CADENCES
from shared.db import CATALOG

SCHEDULER = Actor.system("scheduler")
FRESHNESS = Actor.system("freshness")


def _minus(now: datetime, interval) -> ExpressionWrapper:
    return ExpressionWrapper(Value(now) - interval, output_field=DateTimeField())


def _schedulable():
    # Active, and not refused by FR-17: a crawl source runs only with an approved review.
    return (
        Source.objects.using(CATALOG)
        .filter(status=Source.Status.ACTIVE)
        .exclude(Q(acquisition_method=AcquisitionMethod.CRAWL) & ~Q(tos_status="approved"))
    )


def claim_due_sources(*, now: datetime, limit: int = SCHEDULE_BATCH) -> list[UUID]:
    """Claim up to `limit` due sources, least recently attempted first; returns their ids.

    Due: never attempted, or `last_attempted_at + cadence <= now`. Keyed on the last attempt,
    not the last success, so a failing source is retried at its cadence instead of on every
    tick (run-016 plan S1). Each claim is audited.
    """
    with transaction.atomic(using=CATALOG):
        ids = list(
            _schedulable()
            .select_for_update(skip_locked=True)
            .filter(
                Q(ingest_claimed_at__isnull=True)
                | Q(ingest_claimed_at__lte=now - INGEST_CLAIM_TTL)  # a lost job's claim
            )
            .filter(
                Q(last_attempted_at__isnull=True)
                | Q(last_attempted_at__lte=_minus(now, F("ingestion_cadence")))
            )
            .order_by(F("last_attempted_at").asc(nulls_first=True), "id")
            .values_list("id", flat=True)[:limit]
        )
        Source.objects.using(CATALOG).filter(pk__in=ids).update(ingest_claimed_at=now)
        for source_id in ids:
            write_audit(
                actor=SCHEDULER, action="claim_ingest", target_type="source", target_id=source_id
            )
    return ids


def release_claim(source_id: UUID) -> None:
    """End a claim when its job ends, however it ended. Not audited: the run's own
    `ingest_source` audit row (or the job's "Ingest skipped" log line) closes the claim.
    """
    Source.objects.using(CATALOG).filter(pk=source_id).update(ingest_claimed_at=None)


def flag_stale_sources(*, now: datetime) -> int:
    """Flag active sources with no successful ingestion within 2x their cadence (FR-13).

    Inclusive: exactly 2x is stale. A never-ingested source counts from its registration. The
    pipeline clears the flag on its next success (run-015 D16). Each flag is audited.
    """
    window = ExpressionWrapper(
        F("ingestion_cadence") * STALE_AFTER_CADENCES, output_field=DurationField()
    )
    stale_at = _minus(now, window)
    with transaction.atomic(using=CATALOG):
        ids = list(
            _schedulable()
            .select_for_update(skip_locked=True)
            .filter(stale_since__isnull=True)
            .filter(
                Q(last_ingested_at__lte=stale_at)
                | Q(last_ingested_at__isnull=True, created_at__lte=stale_at)
            )
            .values_list("id", flat=True)
        )
        Source.objects.using(CATALOG).filter(pk__in=ids).update(stale_since=now)
        for source_id in ids:
            write_audit(
                actor=FRESHNESS, action="flag_stale", target_type="source", target_id=source_id
            )
    return len(ids)
