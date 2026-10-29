"""The tick's enqueues and the scheduling tasks (AD-7; run-016 plan S3, S7)."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.ingestion.models import Source
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import SourceFactory
from worker import tasks

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def _at(monkeypatch, when: datetime) -> None:
    monkeypatch.setattr(tasks, "_now", lambda: when)


# --- tick: enqueue only, no database (this module's tick tests have no django_db mark) -------


@pytest.mark.parametrize(
    ("minute", "jobs"),
    [
        (0, ["worker.tasks.schedule_sources", "worker.tasks.reconcile_outbox"]),
        (5, ["worker.tasks.schedule_sources", "worker.tasks.reconcile_outbox"]),
        (1, ["worker.tasks.schedule_sources"]),
        (4, ["worker.tasks.schedule_sources"]),
    ],
)
def test_tick_enqueues_scheduling_every_time_and_the_reconciler_every_5_minutes(
    monkeypatch, enqueued, minute, jobs
):
    _at(monkeypatch, NOW.replace(minute=minute))

    assert tasks.tick() is None
    assert [name for name, _ in enqueued] == jobs


def test_enqueue_seam_uses_delay(monkeypatch):
    sent = []

    class Task:
        def delay(self, *args):
            sent.append(args)

    monkeypatch.undo()  # the real _enqueue, not the autouse recorder
    tasks._enqueue(Task(), "a", "b")

    assert sent == [("a", "b")]


def test_now_is_aware_utc():
    assert tasks._now().utcoffset() == timedelta(0)


# --- schedule_sources ---------------------------------------------------------------------------


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_schedule_sources_claims_due_sources_and_enqueues_one_job_each(
    monkeypatch, enqueued, caplog
):
    now = timezone.now()  # registration (created_at) uses the real clock too
    _at(monkeypatch, now)
    due = SourceFactory(ingestion_cadence=timedelta(hours=4))
    SourceFactory(status="paused")
    stale = SourceFactory(
        ingestion_cadence=timedelta(hours=4),
        last_ingested_at=now - timedelta(days=1),
        last_attempted_at=now - timedelta(minutes=5),
    )

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        tasks.schedule_sources()
        tasks.schedule_sources()  # the next tick: nothing new to enqueue

    assert enqueued == [("worker.tasks.ingest_source", (str(due.pk),))]
    stale.refresh_from_db(using=CATALOG)
    assert stale.stale_since == now
    messages = [(r.getMessage(), r.count) for r in caplog.records if r.name == "worker.tasks"]
    assert messages == [("Sources scheduled", 1), ("Sources stale", 1), ("Sources scheduled", 0)]


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_failed_enqueue_releases_that_claim_and_continues(monkeypatch, caplog):
    monkeypatch.setattr(tasks, "_now", timezone.now)
    sources = [SourceFactory() for _ in range(3)]
    sent = []

    def flaky_broker(task, *args):
        if args[0] == str(sources[1].pk):
            raise ConnectionError("broker down")
        sent.append(args[0])

    monkeypatch.setattr(tasks, "_enqueue", flaky_broker)

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        tasks.schedule_sources()

    claimed = {s.pk: s.ingest_claimed_at is not None for s in Source.objects.using(CATALOG).all()}
    assert sorted(sent) == sorted(str(s.pk) for s in (sources[0], sources[2]))
    assert claimed == {sources[0].pk: True, sources[1].pk: False, sources[2].pk: True}
    warning = next(r for r in caplog.records if r.getMessage() == "Ingest not enqueued")
    assert (warning.source_id, warning.error_type) == (sources[1].pk, "ConnectionError")
    scheduled = next(r for r in caplog.records if r.getMessage() == "Sources scheduled")
    assert scheduled.count == 2


# --- ingest_source task (S7) -----------------------------------------------------------------


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_ingest_task_runs_the_command_and_releases_the_claim(monkeypatch):
    source = SourceFactory(ingest_claimed_at=NOW)
    ran = []
    monkeypatch.setattr(tasks, "run_ingest", lambda source_id: ran.append(source_id))

    assert tasks.ingest_source(str(source.pk)) is None

    assert ran == [source.pk]
    assert Source.objects.using(CATALOG).get(pk=source.pk).ingest_claimed_at is None


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"status": "paused"}, "source_paused"),
        ({"acquisition_method": "crawl", "tos_status": "rejected"}, "crawl_needs_tos_review"),
    ],
)
def test_ingest_task_skips_a_source_refused_since_its_claim(overrides, code, caplog):
    source = SourceFactory(ingest_claimed_at=NOW, **overrides)

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        tasks.ingest_source(str(source.pk))

    [record] = [r for r in caplog.records if r.name == "worker.tasks"]
    assert (record.getMessage(), record.error_code, record.source_id) == (
        "Ingest skipped",
        code,
        str(source.pk),
    )
    assert Source.objects.using(CATALOG).get(pk=source.pk).ingest_claimed_at is None


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_ingest_task_releases_the_claim_and_reraises_unexpected_errors(monkeypatch):
    source = SourceFactory(ingest_claimed_at=NOW)

    def crash(source_id):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(tasks, "run_ingest", crash)

    with pytest.raises(RuntimeError):
        tasks.ingest_source(str(source.pk))
    assert Source.objects.using(CATALOG).get(pk=source.pk).ingest_claimed_at is None
