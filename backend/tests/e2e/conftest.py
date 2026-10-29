"""The broker seams the end-to-end test drives instead of Redis.

`tests/worker/conftest.py` has the same recorder, but it only applies to that package. The
end-to-end test runs the tick and the pipeline jobs inline, so it needs the recorder too, and
the outbox seam so a state change never reaches a broker.
"""

import pytest

from apps.ingestion.services import outbox
from worker import tasks


@pytest.fixture(autouse=True)
def enqueued(monkeypatch):
    jobs: list[tuple[str, tuple]] = []
    monkeypatch.setattr(tasks, "_enqueue", lambda task, *args: jobs.append((task.name, args)))
    return jobs


@pytest.fixture(autouse=True)
def sent_jobs(monkeypatch):
    sent: list[tuple[str, tuple]] = []
    monkeypatch.setattr(outbox, "_send", lambda task, *args: sent.append((task, args)))
    return sent
