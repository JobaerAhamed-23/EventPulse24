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
        (
            0,
            [
                "worker.tasks.schedule_sources",
                "worker.tasks.schedule_calendars",
                "worker.tasks.schedule_digests",
                "worker.tasks.sweep_due_sends",
                "worker.tasks.reconcile_outbox",
                "worker.tasks.reconcile_revalidation",
                "worker.tasks.refresh_event_fits",
            ],
        ),
        (
            5,
            [
                "worker.tasks.schedule_sources",
                "worker.tasks.schedule_calendars",
                "worker.tasks.schedule_digests",
                "worker.tasks.sweep_due_sends",
                "worker.tasks.reconcile_outbox",
                "worker.tasks.reconcile_revalidation",
            ],
        ),
        (
            15,
            [
                "worker.tasks.schedule_sources",
                "worker.tasks.schedule_calendars",
                "worker.tasks.schedule_digests",
                "worker.tasks.sweep_due_sends",
                "worker.tasks.reconcile_outbox",
                "worker.tasks.reconcile_revalidation",
                "worker.tasks.refresh_event_fits",
            ],
        ),
        (
            1,
            [
                "worker.tasks.schedule_sources",
                "worker.tasks.schedule_calendars",
                "worker.tasks.schedule_digests",
                "worker.tasks.sweep_due_sends",
            ],
        ),
        (
            4,
            [
                "worker.tasks.schedule_sources",
                "worker.tasks.schedule_calendars",
                "worker.tasks.schedule_digests",
                "worker.tasks.sweep_due_sends",
            ],
        ),
        # Minute 30 is a multiple of 15 and of 5, so both the refresh and the reconciler run.
        (
            30,
            [
                "worker.tasks.schedule_sources",
                "worker.tasks.schedule_calendars",
                "worker.tasks.schedule_digests",
                "worker.tasks.sweep_due_sends",
                "worker.tasks.reconcile_outbox",
                "worker.tasks.reconcile_revalidation",
                "worker.tasks.refresh_event_fits",
            ],
        ),
        # Every multiple of 15 is also a multiple of 5, so the refresh always lands on a
        # reconciler minute. The two cadences nest; the refresh never runs alone.
        (
            45,
            [
                "worker.tasks.schedule_sources",
                "worker.tasks.schedule_calendars",
                "worker.tasks.schedule_digests",
                "worker.tasks.sweep_due_sends",
                "worker.tasks.reconcile_outbox",
                "worker.tasks.reconcile_revalidation",
                "worker.tasks.refresh_event_fits",
            ],
        ),
    ],
)
def test_tick_enqueues_scheduling_every_time_and_the_reconciler_every_5_minutes(
    monkeypatch, enqueued, minute, jobs
):
    """The tick's enqueue list, pinned minute by minute.

    **The digest dispatcher runs on every beat, and it does not nest.** The
    reconciler's cadence is a divisor of the tick's; the digest dispatcher's is not,
    because "due" is a per-user *local wall clock* comparison — a minute-modulo rule
    would compose everyone at the same instant regardless of the hour they asked for.
    So the digest dispatcher appears in every row above, and the two cadences that
    nest (the reconciler's and the refresh's) are the ones that vary.

    **The send sweep appears in every row too**, for the same kind of reason: a send's
    `due_at` is a *point in time*, not a minute-of-day, so a minute-modulo rule would be
    arbitrary. It runs on every beat; an empty batch is a no-op.
    """
    _at(monkeypatch, NOW.replace(minute=minute))

    assert tasks.tick() is None
    assert [name for name, _ in enqueued] == jobs


def test_the_event_fit_refresh_runs_every_fifteen_minutes(monkeypatch):
    """The refresh cadence is what keeps "tonight" from going stale (AD-10).

    The tick keeps no state, so the cadence is approximate — the same way the
    reconciler's five minutes is. What matters is that the refresh happens, and often
    enough that a tag is not a quarter of an evening out of date.
    """
    sent: list[str] = []

    def record(task, *args):
        sent.append(task.name)

    monkeypatch.setattr(tasks, "_enqueue", record)

    ran_at = []
    for minute in range(0, 60):
        sent.clear()
        _at(monkeypatch, NOW.replace(minute=minute))
        tasks.tick()
        if "worker.tasks.refresh_event_fits" in sent:
            ran_at.append(minute)

    assert ran_at == [0, 15, 30, 45], "the refresh runs four times an hour, every 15 minutes"


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


# --- refresh_event_fits: the staleness refresh (AD-10) -------------------------------


@pytest.mark.django_db(databases=[CATALOG])
def test_the_refresh_task_recomputes_the_fits(caplog):
    """The tick's answer to "tonight" going stale: a writer, not a render-time
    computation.

    The task writes the rows; the read serves them. AD-10's rule is that the *render*
    never computes, and this is the other half of it — something has to.
    """
    from apps.ingestion.models import EventFit
    from tests.ingestion.factories import EventFactory

    event = EventFactory(start_time_utc=timezone.now() + timedelta(hours=2))
    EventFit.objects.using(CATALOG).create(
        event=event,
        city=event.venue.city,
        score=1,
        tags=[],
        event_version=event.event_version,
        computed_at=timezone.now(),
    )

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        assert tasks.refresh_event_fits() is None

    refreshed = EventFit.objects.using(CATALOG).get(event=event)
    assert refreshed.score == 5, "the fit was recomputed, not served stale"
    [record] = [r for r in caplog.records if r.name == "worker.tasks"]
    assert record.job == "refresh_event_fits"


@pytest.mark.django_db(databases=[CATALOG])
def test_the_refresh_task_survives_an_empty_catalog():
    assert tasks.refresh_event_fits() is None


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
