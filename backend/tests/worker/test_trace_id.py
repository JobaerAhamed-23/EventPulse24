"""AD-13: a job's log lines carry the trace id of whatever enqueued it, or a fresh one."""

import io
import json
import logging
import threading
from types import SimpleNamespace

import pytest
from celery import Celery
from celery.contrib.testing.worker import start_worker
from celery.signals import task_postrun

from adapters.logging.context import bind_trace_id, current_trace_id, reset_trace_id
from adapters.logging.formatter import JsonFormatter
from config.celery import (
    TRACE_HEADER,
    attach_trace_id,
    bind_task_trace_id,
    reset_task_trace_id,
)
from config.celery import app as project_app

TRACE_ID = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def traced():
    token = bind_trace_id(TRACE_ID)
    yield TRACE_ID
    reset_trace_id(token)


def fake_task(**headers):
    return SimpleNamespace(request=SimpleNamespace(**headers))


def test_publish_adds_the_current_trace_id_header(traced):
    headers = {}

    attach_trace_id(headers=headers)

    assert headers == {TRACE_HEADER: traced}


def test_publish_outside_a_trace_adds_nothing():
    headers = {}

    attach_trace_id(headers=headers)

    assert headers == {}


def test_prerun_binds_inbound_trace_id_and_postrun_resets_it():
    bind_task_trace_id(task_id="t-1", task=fake_task(**{TRACE_HEADER: TRACE_ID}))
    try:
        assert current_trace_id() == TRACE_ID
    finally:
        reset_task_trace_id(task_id="t-1")

    assert current_trace_id() is None


@pytest.mark.parametrize("inbound", [None, "", "short", "x" * 37, "abc\ninjected-line"])
def test_prerun_without_a_valid_header_mints_a_fresh_trace_id(inbound):
    bind_task_trace_id(task_id="t-2", task=fake_task(**{TRACE_HEADER: inbound}))
    try:
        minted = current_trace_id()
    finally:
        reset_task_trace_id(task_id="t-2")

    assert minted != inbound
    assert len(minted) == 32
    assert int(minted, 16)


def test_postrun_for_an_unknown_task_is_a_no_op(traced):
    reset_task_trace_id(task_id="never-started")

    assert current_trace_id() == traced


def capture_json_lines():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logging.getLogger().addHandler(handler)
    return handler, lambda: [json.loads(line) for line in stream.getvalue().splitlines()]


@pytest.fixture
def restore_default_app():
    yield
    # start_worker makes its app the current/default one; put the project's back.
    project_app.set_current()
    project_app.set_default()


def test_trace_id_crosses_a_real_enqueue_and_execution(traced, restore_default_app):
    # An in-process worker on an in-memory broker; the signal handlers are the real ones.
    # Takes ~5 s: the in-memory transport needs ~4 s to shut the worker down.
    test_app = Celery("trace-test", broker="memory://", set_as_current=False)
    test_app.conf.task_ignore_result = True
    test_app.conf.worker_hijack_root_logger = False
    test_app.loader.import_module("worker.tasks")
    done = threading.Event()

    def finished(**kwargs):
        done.set()

    task_postrun.connect(finished, weak=False)
    handler = None
    try:
        with start_worker(test_app, pool="solo", perform_ping_check=False, loglevel="INFO"):
            # Attached after start: the worker's django.setup() re-applies settings.LOGGING.
            handler, log_lines = capture_json_lines()
            test_app.send_task("worker.tasks.tick")
            assert done.wait(timeout=10), "the worker never ran the tick"
    finally:
        task_postrun.disconnect(finished)
        if handler is not None:
            logging.getLogger().removeHandler(handler)

    [tick_line] = [line for line in log_lines() if line["logger"] == "worker.tasks"]
    assert tick_line["message"] == "Tick"
    assert tick_line["trace_id"] == traced
