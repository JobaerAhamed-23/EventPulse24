"""Worker tasks. Beat and the Celery app find these by dotted string (`config/celery.py`)."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="worker.tasks.tick")
def tick() -> None:
    """The periodic tick (AD-7 seed). Logs and does nothing else yet.

    The due-index sweep and the AD-17 outbox reconciler attach here later. Tasks return
    nothing: Celery's own log lines would otherwise carry the return value.
    """
    logger.info("Tick", extra={"job": "tick"})
