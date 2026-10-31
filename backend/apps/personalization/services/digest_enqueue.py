"""Enqueueing a digest composition from the onboarding path (AD-11, FR-1).

**`personalization` cannot import `worker` or `config`** (the layers contract), so the
job is sent by name through the Celery app `config/__init__` loads. `_send` is the
single seam, and tests replace it. This is the same shape `apps.ingestion.services.outbox`
uses for AD-17's propagation, and for the same reason.

**What this module does and does not do.** It **enqueues**; it does not compose. AD-11's
rule is that "a request handler's job is to validate, enqueue, and return", and
composing reads three candidate pools and scores them — that is worker work. The
`compose_digest` service is never called from here, and a test asserts the API modules
do not import it.

**The enqueue runs after the transaction commits.** A job enqueued *inside* the
transaction would find no preference yet — the worker's transaction could not see an
uncommitted row — and would compose nothing. So the caller registers this with
`transaction.on_commit`, and the enqueue happens once the command's work is durable.

**A failed enqueue does not fail the onboarding.** `on_commit(..., robust=True)` means
a broker that is down logs the failure and lets the transaction stand. The user has
finished onboarding either way; what they have not got is a digest, and the scheduler
will compose one on its next pass — because the dispatcher finds users whose delivery
time has arrived and who have no digest for the local date. **The scheduler is the
backstop, and the enqueue is the fast path.**

**One digest per user, one enqueue.** The composition is idempotent, so a duplicated
enqueue — a retried request, two workers — produces one digest and writes nothing the
second time.
"""

from uuid import UUID

from celery import current_app

COMPOSE_DIGEST_TASK = "worker.tasks.compose_digest"


def _send(task_name: str, args: list[str]) -> None:
    current_app.send_task(task_name, args=args)


def enqueue_digest_composition(user_id: UUID) -> None:
    """Queue one user's digest composition. Run it from `on_commit(using=PERSONAL)` only.

    **The user id is the only argument, and it is a UUID.** No email, no city, no
    delivery time — the worker reads what it needs from the rows, and nothing about the
    user travels through the broker (AD-13).
    """
    _send(COMPOSE_DIGEST_TASK, [str(user_id)])


__all__ = [
    "COMPOSE_DIGEST_TASK",
    "enqueue_digest_composition",
]
