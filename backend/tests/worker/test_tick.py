"""AD-7 seed: one static 60s tick in code; the worker runs it and only logs."""

import logging

from config.celery import TICK_SECONDS, app
from worker.tasks import tick


def test_beat_schedule_is_exactly_one_60s_tick():
    assert app.conf.beat_schedule == {"tick": {"task": "worker.tasks.tick", "schedule": 60.0}}
    assert TICK_SECONDS == 60.0


def test_tick_task_is_registered_under_the_scheduled_name():
    app.loader.import_default_modules()

    # shared_task returns a proxy; the registered task is what it resolves to.
    assert app.tasks["worker.tasks.tick"] is tick._get_current_object()


def test_tick_logs_and_returns_nothing(caplog):
    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        result = tick()

    assert result is None
    [record] = [r for r in caplog.records if r.name == "worker.tasks"]
    assert record.getMessage() == "Tick"
    assert record.job == "tick"


def test_tick_runs_through_celery():
    result = tick.apply()

    assert result.successful()
    assert result.result is None


def test_worker_keeps_our_logging():
    # AD-13: Celery must not replace the redacting root handler from settings.LOGGING.
    assert app.conf.worker_hijack_root_logger is False
    assert app.conf.task_ignore_result is True
    assert app.conf.broker_url.startswith("redis://")
