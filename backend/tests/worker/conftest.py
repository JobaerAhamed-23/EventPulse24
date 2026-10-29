"""Shared fixtures for the worker tests."""

import pytest

from worker import tasks


@pytest.fixture(autouse=True)
def enqueued(monkeypatch):
    """Record every job a task enqueues instead of publishing it to the broker (Redis)."""
    jobs: list[tuple[str, tuple]] = []
    monkeypatch.setattr(tasks, "_enqueue", lambda task, *args: jobs.append((task.name, args)))
    return jobs
