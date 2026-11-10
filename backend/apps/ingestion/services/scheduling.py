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
from domain.sources import HIGH_PRIORITY, LOWER_PRIORITY
from shared.actor import Actor
from shared.constants import (
    HIGH_PRIORITY_CADENCE_MAX,
    HIGH_PRIORITY_METHODS,
    INGEST_CLAIM_TTL,
    LOW_PRIORITY_CADENCE_MAX,
    SCHEDULE_BATCH,
    STALE_AFTER_CADENCES,
)
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


def report_cadence_floor_breaches(*, now: datetime) -> int:
    """Count the sources that have not successfully ingested inside their tier's ceiling.

    **This is FR-53's guarantee, stated as a check.** "A cancelled event is detected by the
    system within 4 hours for high-priority sources" is only true if the source was
    *successfully* ingested within the last 4 hours. A source that is polled on time but keeps
    failing has met its polling floor and broken its detection floor — and a source that is
    not polled at all has broken both.

    **It is about `last_ingested_at`, not `last_attempted_at`.** A failed poll detects
    nothing, so an attempt is not evidence the guarantee was kept.

    **A never-ingested source counts from its registration** — the same convention
    `flag_stale_sources` uses.

    **Inclusive at the boundary**, like `flag_stale_sources`: a source last ingested exactly
    its ceiling ago has been outside its window for exactly that long, so it is a breach.
    The guarantee is "detected *within* 4 hours", and at the instant the window closes the
    promise has expired — the same convention the stale flag uses ("exactly 2x is stale").

    ---

    **Why this is not `flag_stale_sources`.** That one fires at 2x the *row's own* cadence,
    which an operator controls, and it is a question about the data's freshness. This one
    fires at 1x the *tier's* ceiling, which nobody controls, and it is a question about the
    promise. The two differ in both directions:

    - A high-priority source polled every 15 minutes that fails is flagged stale after 30
      minutes — **before** its 4-hour window. That is noise: the product surfaces a failure
      it has not yet broken a promise about.
    - A high-priority source at a 4-hour cadence that fails is flagged stale after 8 hours —
      **4 hours after the promise broke.** That is silence.

    So the floor check asks the promise question directly, for every source in the tier,
    regardless of what cadence the row happens to carry.

    **Two queries, one per tier.** The window is per-tier and the tier is *derived* from the
    method rather than stored, so it cannot be a column comparison — there is no ceiling
    column to compare against. Two indexed queries over a registry of hundreds of rows are
    cheaper than a second source of truth that could disagree with the method.

    **A count, not a list.** The caller logs it; a source id or name is not needed to
    surface it, and the codebase's convention is ids and counts in logs (AD-13).
    """
    breaches = 0
    for tier, ceiling in (
        (HIGH_PRIORITY, HIGH_PRIORITY_CADENCE_MAX),
        (LOWER_PRIORITY, LOW_PRIORITY_CADENCE_MAX),
    ):
        window = now - ceiling
        candidates = _schedulable().filter(
            Q(last_ingested_at__lte=window)
            | Q(last_ingested_at__isnull=True, created_at__lte=window)
        )
        if tier == HIGH_PRIORITY:
            candidates = candidates.filter(acquisition_method__in=HIGH_PRIORITY_METHODS)
        else:
            # The lower tier is "not a high-priority method", exactly as the derivation
            # and the database constraint say — so the two cannot disagree about a
            # method that did not exist when they were written.
            candidates = candidates.exclude(acquisition_method__in=HIGH_PRIORITY_METHODS)
        breaches += candidates.count()
    return breaches
