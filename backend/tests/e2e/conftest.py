"""The broker seams the end-to-end test drives instead of Redis.

`tests/worker/conftest.py` has the same recorder, but it only applies to that package. The
end-to-end test runs the tick and the pipeline jobs inline, so it needs the recorder too, and
the outbox seam so a state change never reaches a broker.

**The revalidation outbox has its own seam, and it is patched here too.** The three
outboxes in this codebase each hand their job to the broker through their *own* `_send`:

- `worker/tasks.py`'s `_enqueue` — the periodic tick's jobs;
- `apps/ingestion/services/outbox.py`'s `_send` — the personal propagation (AD-17);
- `apps/ingestion/services/revalidation.py`'s `_send` — the public page rebuild (FR-26).

**The third one was missing, and it was missing silently.** `revalidation.enqueue_revalidation`
calls `_send(REVALIDATE_TASK, [str(request_id)])`, and with the seam unpatched that call
reaches Celery's `current_app.send_task` — which, with no broker configured, raises inside
a `transaction.on_commit` callback. The enqueue would then either blow up the test or,
worse, reach a broker the test does not own. **So the seam is patched here, and the
`revalidation_sent` fixture records what would have been sent.**

The fixture is `autouse`, like the other two: a proof that observes a signal must not have
to remember to install the recorder, and a proof that forgets would otherwise reach the
network — which is the one thing an end-to-end proof must never do.
"""

import pytest

from apps.ingestion.services import outbox, revalidation
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


@pytest.fixture(autouse=True)
def revalidation_sent(monkeypatch):
    """The revalidation outbox's own seam — the public page rebuild's hand-off.

    **The recorder holds `(task_name, args)`, the same shape the other two hold.** The
    task name is the dotted string the worker registers the task under
    (`worker.tasks.revalidate_public_pages`), and the argument is the request's id as a
    string — so a proof can assert *which* request was offered to the broker and then
    open that row and read its paths.
    """
    sent: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        revalidation, "_send", lambda task_name, args: sent.append((task_name, args))
    )
    return sent
