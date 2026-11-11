"""The weekly recompute, as the worker runs it: the tick asks, the job decides.

**The weekly guarantee, end to end.** The tick enqueues the job on every beat (there is no
`minute % 10080`), and the job recomputes every source that has no row for the current
period. A source scored last week is due again today, and a source scored today is not.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from apps.ingestion.models import (
    ReviewItem,
    Source,
    SourceObservation,
    SourceReliabilityScore,
)
from apps.ingestion.services import reliability as services_reliability
from apps.ingestion.services.reliability import (
    claim_due_sources,
    period_start_for,
    recompute_due,
    release_claim,
)
from apps.ingestion.services.review_queue import raise_review_item
from shared.actor import Actor
from shared.constants import RELIABILITY_CLAIM_TTL
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, SourceFactory
from worker import tasks

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
SYSTEM = Actor.system("ingest_pipeline")
THIS_WEEK = date(2026, 11, 9)
LAST_WEEK = date(2026, 11, 2)


def _observation(source: Source, kind: str, *, occurred_at: datetime) -> SourceObservation:
    event = EventFactory(source=source)
    item = raise_review_item(
        event=event, reason=ReviewItem.Reason.IN_REVIEW, actor=SYSTEM, now=occurred_at
    ).item
    return SourceObservation.objects.using(CATALOG).create(
        source=source,
        kind=kind,
        event=event,
        review_item=item,
        occurred_at=occurred_at,
        actor_kind=SYSTEM.kind,
        actor_id=SYSTEM.id,
        actor_label=SYSTEM.label,
    )


# ── The tick asks ─────────────────────────────────────────────────────────────────────────


def test_the_tick_enqueues_the_recompute_on_every_beat(monkeypatch):
    """**A weekly cadence is not a minute-modulo rule**, so the job is asked every minute
    and decides for itself. The `tick` enqueue table in `tests/worker/` pins that; this
    test pins it from the job's side.
    """
    sent: list[str] = []

    def record(task, *args):
        sent.append(task.name)

    monkeypatch.setattr(tasks, "_enqueue", record)
    monkeypatch.setattr(tasks, "_now", lambda: NOW)

    tasks.tick()

    assert "worker.tasks.recompute_reliability" in sent


# ── The job decides ───────────────────────────────────────────────────────────────────────


def test_the_job_recomputes_a_source_that_has_no_row_for_this_week():
    source = SourceFactory()
    _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)

    results = recompute_due(now=NOW)

    assert [r.source_id for r in results] == [source.pk]
    assert SourceReliabilityScore.objects.using(CATALOG).filter(source=source).count() == 1


def test_the_job_skips_a_source_scored_this_week():
    """**The weekly guarantee, from the other side.** A source scored today is not due
    again today — the job would otherwise rewrite the same row every minute."""
    source = SourceFactory()
    SourceReliabilityScore.objects.using(CATALOG).create(
        source=source,
        period_start=THIS_WEEK,
        score=Decimal("0.50"),
        positives=0,
        negatives=0,
        computed_at=NOW,
    )

    results = recompute_due(now=NOW)

    assert results == []


def test_a_source_scored_last_week_is_due_today():
    """**The guarantee in the form the AC states it**: a source not recomputed for seven
    days is due."""
    source = SourceFactory()
    SourceReliabilityScore.objects.using(CATALOG).create(
        source=source,
        period_start=LAST_WEEK,
        score=Decimal("0.50"),
        positives=0,
        negatives=0,
        computed_at=NOW - timedelta(days=7),
    )

    results = recompute_due(now=NOW)

    assert [r.source_id for r in results] == [source.pk]


def test_the_job_leaves_the_existing_row_alone_and_adds_a_new_one():
    """**One row per period.** Last week's row stays — the spike rule needs it — and this
    week's row is added beside it."""
    source = SourceFactory()
    SourceReliabilityScore.objects.using(CATALOG).create(
        source=source,
        period_start=LAST_WEEK,
        score=Decimal("0.50"),
        positives=0,
        negatives=0,
        computed_at=NOW - timedelta(days=7),
    )

    recompute_due(now=NOW)

    periods = set(
        SourceReliabilityScore.objects.using(CATALOG)
        .filter(source=source)
        .values_list("period_start", flat=True)
    )
    assert periods == {LAST_WEEK, THIS_WEEK}


def test_the_job_escalates_through_the_task():
    """**The task wires the service to the worker**, so the escalation path is reachable
    from a beat and not only from a test of the service."""
    source = SourceFactory()
    for index in range(30):
        _observation(
            source, SourceObservation.Kind.REJECTED, occurred_at=NOW - timedelta(days=index)
        )

    tasks.recompute_reliability()

    assert (
        ReviewItem.objects.using(CATALOG)
        .filter(source=source, reason=ReviewItem.Reason.SOURCE_RELIABILITY)
        .exists()
    )


def test_the_task_is_a_no_op_when_nothing_is_due():
    """**An empty batch is a no-op**, exactly as the digest dispatcher's is."""
    tasks.recompute_reliability()

    assert not SourceReliabilityScore.objects.using(CATALOG).exists()


# ── The claim ─────────────────────────────────────────────────────────────────────────────


def test_the_claim_returns_the_due_sources():
    source = SourceFactory()

    claimed = claim_due_sources(now=NOW)

    assert source.pk in claimed


def test_the_claim_skips_a_source_already_scored_this_week():
    source = SourceFactory()
    SourceReliabilityScore.objects.using(CATALOG).create(
        source=source,
        period_start=THIS_WEEK,
        score=Decimal("0.50"),
        positives=0,
        negatives=0,
        computed_at=NOW,
    )

    claimed = claim_due_sources(now=NOW)

    assert source.pk not in claimed


def test_the_claim_writes_only_the_claim_marker():
    """**The claim writes one column, and it is the claim marker.**

    It does not write the score, the score's timestamp, or anything else about the source —
    the claim is a fact about the job's work, not about the source. So a crash between the
    claim and the recompute leaves a marker to clear, not a half-written score.
    """
    source = SourceFactory()
    before = Source.objects.using(CATALOG).get(pk=source.pk)

    claim_due_sources(now=NOW)

    after = Source.objects.using(CATALOG).get(pk=source.pk)
    assert after.reliability_score == before.reliability_score
    assert after.reliability_scored_at == before.reliability_scored_at
    assert after.status == before.status
    assert after.reliability_claimed_at == NOW


def test_a_second_claim_does_not_return_a_claimed_source():
    """**The claim is what stops two overlapping ticks from recomputing the same source.**

    This is the test the old, lock-only claim failed. A `FOR UPDATE SKIP LOCKED` released
    with the claim's transaction prevents nothing, because the recompute runs in its *own*
    transaction — so two ticks both claimed the same source and both recomputed it. The
    marker outlives the transaction that took it, which is what makes the claim a claim.
    """
    source = SourceFactory()

    first = claim_due_sources(now=NOW)
    second = claim_due_sources(now=NOW)

    assert source.pk in first
    assert source.pk not in second


def test_a_released_claim_can_be_claimed_again():
    """**The claim ends when the job ends.** A source that was claimed and then released is
    due again immediately — which is what happens to a source whose recompute failed."""
    source = SourceFactory()

    claim_due_sources(now=NOW)
    release_claim(source.pk)

    assert source.pk in claim_due_sources(now=NOW)


def test_a_stale_claim_is_reclaimed():
    """**A claim older than the TTL is a lost job**, so the source is claimed again rather
    than being skipped for the rest of the week."""
    source = SourceFactory()
    Source.objects.using(CATALOG).filter(pk=source.pk).update(
        reliability_claimed_at=NOW - RELIABILITY_CLAIM_TTL - timedelta(minutes=1)
    )

    assert source.pk in claim_due_sources(now=NOW)


def test_a_fresh_claim_is_not_reclaimed():
    """**The other half of the TTL rule**: a claim that is still within the TTL is
    respected, so a second tick does not steal a source that is being worked on."""
    source = SourceFactory()
    Source.objects.using(CATALOG).filter(pk=source.pk).update(
        reliability_claimed_at=NOW - RELIABILITY_CLAIM_TTL + timedelta(minutes=1)
    )

    assert source.pk not in claim_due_sources(now=NOW)


def test_the_claim_leaves_a_paused_source_alone():
    """**Only active sources are scored.** A paused source is not ingesting, so its score
    is not changing."""
    source = SourceFactory(status=Source.Status.PAUSED)

    claimed = claim_due_sources(now=NOW)

    assert source.pk not in claimed


# ── The period ────────────────────────────────────────────────────────────────────────────


def test_the_period_is_the_monday_of_the_week():
    assert period_start_for(NOW) == THIS_WEEK


# ── One source's failure does not lose the others ─────────────────────────────────────────


def test_one_failing_source_does_not_lose_the_rest_of_the_batch(monkeypatch):
    """**A batch is not all-or-nothing.**

    Without the per-source guard, one source that raises aborts the loop and every
    remaining source is silently skipped for the week — which is the same shape of failure
    as a job that never ran at all, and much harder to see.
    """
    good = SourceFactory()
    bad = SourceFactory()

    real = services_reliability.recompute_source

    def explode_on_bad(**kwargs):
        if kwargs["source_id"] == bad.pk:
            raise RuntimeError("this source is broken")
        return real(**kwargs)

    monkeypatch.setattr(services_reliability, "recompute_source", explode_on_bad)

    results = services_reliability.recompute_due(now=NOW)

    assert [r.source_id for r in results] == [good.pk]
    assert SourceReliabilityScore.objects.using(CATALOG).filter(source=good).count() == 1


def test_a_failed_source_releases_its_claim(monkeypatch):
    """**A failed source is retried on the next tick**, rather than being stranded until
    the claim TTL expires."""
    source = SourceFactory()

    def explode(**kwargs):
        raise RuntimeError("this source is broken")

    monkeypatch.setattr(services_reliability, "recompute_source", explode)

    services_reliability.recompute_due(now=NOW)

    source.refresh_from_db(using=CATALOG)
    assert source.reliability_claimed_at is None
