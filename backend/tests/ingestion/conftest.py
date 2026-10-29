"""Shared fixtures for the ingestion tests."""

import pytest

from apps.ingestion.services import outbox


@pytest.fixture(autouse=True)
def sent_jobs(monkeypatch):
    """Record every job the outbox sends instead of reaching the Celery broker (Redis)."""
    jobs: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(outbox, "_send", lambda name, args: jobs.append((name, list(args))))
    return jobs
