"""The sweep worker task (AD-7, AD-13, AD-20).

**What these tests pin.**

- The **tick enqueues the sweep on every beat** — a send's `due_at` is a point in time,
  not a minute-of-day, so a minute-modulo rule would be arbitrary.
- The tick **still touches no database**, so a slow sweep cannot delay the next tick.
- The tick **still uses exactly one static 60-second beat** — no new `beat_schedule` entry.
- The task **resolves the recipient through `identity`'s published read**, never by
  reading the `User` table itself (the `models-identity` import contract).
- The task **logs counts and never an address** (AD-13).
- A failure in the sweep **does not reach Celery as a retry** — the rows own the outcome.
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from django.db import connections

from adapters.email.memory import InMemoryEmailAdapter
from apps.delivery.models import ScheduledSend
from shared.db import CATALOG, PERSONAL
from tests.delivery.factories import ScheduledSendFactory
from tests.identity.factories import UserFactory
from worker import tasks

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

DUE = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)


# --- The tick -------------------------------------------------------------------------------


def test_the_tick_enqueues_the_sweep(enqueued):
    tasks.tick()

    assert ("worker.tasks.sweep_due_sends", ()) in enqueued


def test_the_sweep_runs_on_every_beat(enqueued):
    """A send's `due_at` is a point in time, not a minute-of-day."""
    for _ in range(5):
        tasks.tick()

    assert [name for name, _ in enqueued].count("worker.tasks.sweep_due_sends") == 5


def test_the_tick_still_uses_exactly_one_static_beat():
    """**No new `beat_schedule` entry.** `TICK_SECONDS == 60.0` already satisfies AD-7's
    "≤60s intervals", so the sweep hangs off the existing tick."""
    from config.celery import TICK_SECONDS, app

    assert app.conf.beat_schedule == {"tick": {"task": "worker.tasks.tick", "schedule": 60.0}}
    assert TICK_SECONDS == 60.0


def test_the_tick_touches_no_database():
    """The tick enqueues and nothing else — a slow sweep cannot delay the next tick.

    The check is on the queries, on **both** aliases: a query on either one during the
    tick is a failure, whatever wrote it. The sweep runs in its own enqueued job, so the
    tick's own cost is a handful of dict lookups.
    """
    from django.test.utils import CaptureQueriesContext

    with (
        CaptureQueriesContext(connections[PERSONAL]) as personal,
        CaptureQueriesContext(connections[CATALOG]) as catalog,
    ):
        tasks.tick()

    assert not personal.captured_queries
    assert not catalog.captured_queries


# --- The sweep task --------------------------------------------------------------------------


def test_the_sweep_task_sends_a_due_row(monkeypatch):
    user = UserFactory(email="maya@example.com")
    ScheduledSendFactory(user_id=user.pk, due_at=datetime.now(UTC) - timedelta(minutes=1))
    port = InMemoryEmailAdapter()
    monkeypatch.setattr(tasks, "get_email_port", lambda: port)

    tasks.sweep_due_sends()

    assert len(port.sent) == 1


def test_the_sweep_task_resolves_the_recipient_through_identity(monkeypatch):
    """`delivery` may not read the `User` table — the `models-identity` import contract
    enforces it. The address comes from `identity`'s published read."""
    user = UserFactory(email="maya@example.com")
    row = ScheduledSendFactory(user_id=user.pk, due_at=datetime.now(UTC) - timedelta(minutes=1))
    port = InMemoryEmailAdapter()
    monkeypatch.setattr(tasks, "get_email_port", lambda: port)

    tasks.sweep_due_sends()

    assert port.sent
    assert port.sent[0].message.to == "maya@example.com"
    assert row.user_id == user.pk


def test_the_sweep_task_marks_the_row_sent(monkeypatch):
    user = UserFactory(email="maya@example.com")
    row = ScheduledSendFactory(user_id=user.pk, due_at=datetime.now(UTC) - timedelta(minutes=1))
    port = InMemoryEmailAdapter()
    monkeypatch.setattr(tasks, "get_email_port", lambda: port)

    tasks.sweep_due_sends()

    stored = ScheduledSend.objects.using(PERSONAL).get(pk=row.pk)
    assert stored.status == ScheduledSend.Status.SENT


def test_the_sweep_task_logs_counts_and_no_address(monkeypatch, caplog):
    """AD-13: the log line carries counts and the job name, never the address."""
    user = UserFactory(email="maya@example.com")
    ScheduledSendFactory(user_id=user.pk, due_at=datetime.now(UTC) - timedelta(minutes=1))
    port = InMemoryEmailAdapter()
    monkeypatch.setattr(tasks, "get_email_port", lambda: port)

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        tasks.sweep_due_sends()

    [record] = [r for r in caplog.records if r.name == "worker.tasks"]
    assert record.getMessage() == "Sends swept"
    assert record.job == "sweep_due_sends"
    assert record.sent == 1
    assert "maya@example.com" not in caplog.text


def test_the_sweep_task_swallows_an_unexpected_failure(monkeypatch, caplog):
    """The rows own the outcome, so a job-level failure must not re-run the batch.

    A Celery retry would find the rows claimed and do nothing — a retry that cannot help.
    """

    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "get_email_port", boom)

    with caplog.at_level(logging.WARNING, logger="worker.tasks"):
        result = tasks.sweep_due_sends()

    assert result is None
    [record] = [r for r in caplog.records if r.name == "worker.tasks"]
    assert record.getMessage() == "Send sweep failed"
    assert record.error_type == "RuntimeError"


# --- The task names ----------------------------------------------------------------------------


def test_the_task_is_registered_under_its_dotted_name():
    from config.celery import app

    app.loader.import_default_modules()

    assert app.tasks["worker.tasks.sweep_due_sends"] is tasks.sweep_due_sends._get_current_object()


def test_the_task_runs_through_celery():
    result = tasks.sweep_due_sends.apply()

    assert result.successful()
    assert result.result is None
