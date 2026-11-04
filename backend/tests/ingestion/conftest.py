"""Shared fixtures for the ingestion tests."""

import pytest

from apps.ingestion.services import outbox, revalidation


@pytest.fixture(autouse=True)
def sent_jobs(monkeypatch):
    """Record every job the ingestion services send instead of reaching the Celery broker (Redis).

    **Both outboxes are captured.** AD-17's personal propagation and the revalidation
    signal (FR-26, FR-27) each have their own `_send` seam, and a test that saw only one
    of them would be blind to the other's jobs.
    """
    jobs: list[tuple[str, list[str]]] = []
    record = lambda name, args: jobs.append((name, list(args)))  # noqa: E731
    monkeypatch.setattr(outbox, "_send", record)
    monkeypatch.setattr(revalidation, "_send", record)
    return jobs
