"""The AD-17 outbox (pipeline design D14, D15; data-model design D23) and its worker tasks."""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from apps.ingestion.models import EventStateChange
from apps.ingestion.services import outbox
from apps.ingestion.services.outbox import (
    PROPAGATE_TASK,
    enqueue_propagation,
    mark_propagated,
    reconcile_outbox,
)
from shared.constants import OUTBOX_RECONCILE_AFTER
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import EventStateChangeFactory
from worker import tasks

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
REAL_SEND = outbox._send  # captured before the autouse recorder replaces it


def _change(age: timedelta, *, propagated: bool = False) -> EventStateChange:
    return EventStateChangeFactory(occurred_at=NOW - age, propagated_at=NOW if propagated else None)


def test_enqueue_propagation_sends_the_task_by_name(sent_jobs):
    change_id = uuid7()

    enqueue_propagation(change_id)

    assert sent_jobs == [(PROPAGATE_TASK, [str(change_id)])]


def test_send_goes_through_the_loaded_celery_app(monkeypatch):
    sent = []
    monkeypatch.setattr(
        outbox.current_app, "send_task", lambda name, args: sent.append((name, args))
    )

    REAL_SEND("worker.tasks.x", ["1"])

    assert sent == [("worker.tasks.x", ["1"])]


def test_reconcile_enqueues_only_rows_unpropagated_past_the_age_oldest_first(sent_jobs):
    oldest = _change(timedelta(hours=2))
    older = _change(OUTBOX_RECONCILE_AFTER + timedelta(seconds=1))
    _change(OUTBOX_RECONCILE_AFTER)  # exactly 5 minutes: not yet
    _change(timedelta(minutes=1))
    _change(timedelta(hours=3), propagated=True)

    count = reconcile_outbox(now=NOW)

    assert count == 2
    assert sent_jobs == [(PROPAGATE_TASK, [str(oldest.pk)]), (PROPAGATE_TASK, [str(older.pk)])]


def test_reconcile_respects_the_batch_limit(sent_jobs):
    rows = [_change(timedelta(hours=h)) for h in (3, 2, 1)]

    assert reconcile_outbox(now=NOW, limit=2) == 2
    assert [args[0] for _, args in sent_jobs] == [str(rows[0].pk), str(rows[1].pk)]


def test_mark_propagated_is_idempotent():
    change = _change(timedelta(hours=1))

    assert mark_propagated(change.pk, now=NOW) is True
    assert mark_propagated(change.pk, now=NOW + timedelta(hours=1)) is False

    change.refresh_from_db(using=CATALOG)
    assert change.propagated_at == NOW


def test_the_consumer_marks_a_change_nobody_saved_as_propagated(caplog):
    """The replacement for the placeholder's test, and the inverse of what it asserted.

    Until `propagation-consumer`, this task deliberately left `propagated_at` NULL so the
    reconciler would keep re-offering the row until a real consumer arrived. It has arrived,
    and the most common case is this one: an unsaved event's state change touches nobody.

    It must mark propagated immediately rather than churn. There is no attempts counter on
    an append-only row to retire it with, so a change that never marks is a change the
    reconciler offers forever.
    """
    change = _change(timedelta(hours=1))

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        result = tasks.propagate_state_change(str(change.pk))

    assert result is None
    change.refresh_from_db(using=CATALOG)
    assert change.propagated_at is not None
    [record] = [r for r in caplog.records if r.name == "worker.tasks"]
    assert (record.getMessage(), record.users) == ("State change propagated", 0)


def test_the_consumer_does_nothing_for_a_change_that_no_longer_exists():
    """A task holding an id for a vanished row has nothing to do, and that is not an error."""
    assert tasks.propagate_state_change(str(uuid7())) is None


def test_reconcile_task_calls_the_command_and_logs_the_count(monkeypatch, caplog):
    monkeypatch.setattr(outbox, "reconcile_outbox", lambda: 7)

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        assert tasks.reconcile_outbox() is None

    [record] = [r for r in caplog.records if r.name == "worker.tasks"]
    assert (record.getMessage(), record.count, record.job) == (
        "Outbox reconciled",
        7,
        "reconcile_outbox",
    )
