"""Celery app for the worker runtime (AD-1, AD-7). Settings come from Django (`CELERY_*`).

`config` and `worker` never import each other (AD-1), so tasks and beat entries are named by
dotted string. Run with `make worker` and exactly one `make beat`.
"""

import os

from celery import Celery
from celery.signals import before_task_publish, setup_logging, task_postrun, task_prerun

from adapters.logging.context import bind_trace_id, current_trace_id, reset_trace_id
from config.middleware import INBOUND_TRACE_ID
from shared.ids import uuid7

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

TRACE_HEADER = "trace_id"
TICK_SECONDS = 60.0

app = Celery("eventpulse24", include=["worker.tasks"])
app.config_from_object("django.conf:settings", namespace="CELERY")

# AD-7: one static tick. The broker carries this tick and pipeline jobs, never the reminder
# schedule; that lives in Postgres and is swept from here. No django-celery-beat.
app.conf.beat_schedule = {
    "tick": {"task": "worker.tasks.tick", "schedule": TICK_SECONDS},
}


@setup_logging.connect
def keep_django_logging(**kwargs) -> None:
    """AD-13: settings.LOGGING (applied by django.setup()) stays the only sink.

    Connecting this handler stops Celery installing its own, unredacted handlers.
    """


@before_task_publish.connect
def attach_trace_id(headers: dict | None = None, **kwargs) -> None:
    trace_id = current_trace_id()
    if trace_id and headers is not None:
        headers.setdefault(TRACE_HEADER, trace_id)


# task id -> context token, so postrun resets exactly what prerun bound.
_trace_tokens = {}


@task_prerun.connect
def bind_task_trace_id(task_id: str | None = None, task=None, **kwargs) -> None:
    inbound = getattr(task.request, TRACE_HEADER, None) if task is not None else None
    if isinstance(inbound, str) and INBOUND_TRACE_ID.fullmatch(inbound):
        trace_id = inbound
    else:
        # Beat ticks (and anything enqueued outside a request) start a trace of their own.
        trace_id = uuid7().hex
    _trace_tokens[task_id] = bind_trace_id(trace_id)


@task_postrun.connect
def reset_task_trace_id(task_id: str | None = None, **kwargs) -> None:
    token = _trace_tokens.pop(task_id, None)
    if token is not None:
        reset_trace_id(token)
