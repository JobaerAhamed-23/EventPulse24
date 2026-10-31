"""The first-digest enqueue (D5): the onboarding path that starts the digest running.

**The properties a user would notice if they broke.**

- Finishing the onboarding **queues the first digest**, so the user does not have to
  wait for the next scheduler pass to see their first card.
- The enqueue happens **after the transaction commits** — a job enqueued inside the
  transaction would run before the preference was durable, find nothing, and compose
  nothing.
- A **broker outage does not fail the onboarding**. The user has finished onboarding
  either way; what they have not got is a digest, and the scheduler is the backstop.
- The enqueue happens **once**, and the job carries **only the user id**.

**On the `on_commit` callbacks.** `pytest`'s `django_db` fixture wraps every test in a
transaction that is rolled back, so Django's `on_commit` callbacks never fire on their
own. The fixture below **captures** them instead — the same thing Django's own
`captureOnCommitCallbacks` does — so a test can see both halves: the callback is
*registered* by the command, and it *sends the job* when it is run.

**The clock is fixed throughout** — no test sleeps.
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from django.db import transaction

from apps.personalization.services import digest_enqueue
from apps.personalization.services.onboarding import (
    advance_step,
    skip_all,
    skip_step,
)
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def sent(monkeypatch):
    """Record the jobs the onboarding path enqueues instead of publishing them."""
    jobs: list[tuple[str, list]] = []
    monkeypatch.setattr(digest_enqueue, "_send", lambda name, args: jobs.append((name, list(args))))
    return jobs


@pytest.fixture
def on_commit(monkeypatch):
    """Capture the `on_commit` callbacks the command registers.

    **The real `on_commit` is kept in place** — only the *dispatch* is intercepted, so
    the command still registers through Django's own machinery and the captured list is
    exactly what Django would have run at commit time.

    Returns the list of captured callbacks; run them with `run()`.
    """
    captured: list = []
    original = transaction.on_commit

    def capture(func, using=None, robust=False):
        captured.append((func, using, robust))
        return original(func, using=using, robust=robust)

    monkeypatch.setattr(transaction, "on_commit", capture)

    def run():
        """Run the captured callbacks **the way Django's runner does**.

        **The `robust` flag is honoured here, not by the callback.** Django's
        `run_and_clear_commit_hooks` catches a robust callback's exception and logs it;
        a plain one is allowed to escape. The captured tuple carries the flag, so the
        same distinction is available here.
        """
        import logging

        for func, _using, robust in captured:
            if robust:
                try:
                    func()
                except Exception:
                    logging.getLogger("django.db.backends.base").exception(
                        "Error calling %s in on_commit().", getattr(func, "__qualname__", func)
                    )
            else:
                func()

    run.captured = captured
    return run


def actor(user_id):
    return Actor.user(user_id)


def complete_by_advancing(user_id):
    """Advance past all three steps."""
    for _ in range(3):
        advance_step(user_id=user_id, actor=actor(user_id), now=NOW)


# --- The enqueue happens -------------------------------------------------------------------


def test_advancing_past_the_last_step_queues_the_first_digest(sent, on_commit):
    user_id = uuid7()

    complete_by_advancing(user_id)
    on_commit()

    assert sent == [("worker.tasks.compose_digest", [str(user_id)])]


def test_skipping_the_last_step_queues_the_first_digest(sent, on_commit):
    user_id = uuid7()
    for _ in range(2):
        skip_step(user_id=user_id, actor=actor(user_id), now=NOW)

    skip_step(user_id=user_id, actor=actor(user_id), now=NOW)
    on_commit()

    assert sent == [("worker.tasks.compose_digest", [str(user_id)])]


def test_skipping_everything_queues_the_first_digest(sent, on_commit):
    user_id = uuid7()

    skip_all(user_id=user_id, actor=actor(user_id), now=NOW)
    on_commit()

    assert sent == [("worker.tasks.compose_digest", [str(user_id)])]


def test_an_earlier_step_queues_nothing(sent, on_commit):
    """Only the *completion* queues the digest — a user at step 2 is not finished, and
    their digest preference may not even exist yet."""
    user_id = uuid7()

    advance_step(user_id=user_id, actor=actor(user_id), now=NOW)
    skip_step(user_id=user_id, actor=actor(user_id), now=NOW)
    on_commit()

    assert sent == []


def test_the_enqueue_happens_once(sent, on_commit):
    """A completed onboarding is terminal, so a second completion attempt is refused —
    and a second enqueue would compose the same digest twice (harmlessly, but pointlessly)."""
    user_id = uuid7()

    complete_by_advancing(user_id)
    on_commit()

    assert len(sent) == 1


def test_only_the_user_id_travels(sent, on_commit):
    """**Nothing about the user goes through the broker** (AD-13): no email, no city, no
    delivery time. The worker reads what it needs from the rows."""
    user_id = uuid7()

    complete_by_advancing(user_id)
    on_commit()

    [(_, args)] = sent
    assert len(args) == 1
    assert UUID(args[0]) == user_id


# --- The enqueue happens after the commit ----------------------------------------------------


def test_the_enqueue_waits_for_the_commit(sent, on_commit):
    """**The enqueue is registered, not performed.**

    A job enqueued *inside* the transaction would run before the commit and find no
    preference — it would compose nothing, and the user would have no digest at all.

    So the enqueue is registered with `on_commit`, and it runs when the command's work
    is durable. The observable half of that is the `sent` list being empty until the
    commit happens.
    """
    user_id = uuid7()

    complete_by_advancing(user_id)

    # Nothing yet: the transaction has not committed.
    assert sent == []

    on_commit()

    assert len(sent) == 1


def test_the_enqueue_is_registered_on_the_personal_alias(on_commit):
    """**The callback belongs to the transaction that wrote the rows.** The preference
    lives in the `personal` schema, so the callback is registered on that alias —
    otherwise it could fire against a different connection's commit."""
    user_id = uuid7()

    complete_by_advancing(user_id)

    [_func, using, _robust] = on_commit.captured[0]
    assert using == PERSONAL


def test_a_broker_outage_does_not_fail_the_onboarding(monkeypatch, on_commit):
    """**A failed enqueue does not fail the onboarding.** The user has finished
    onboarding either way; what they have not got is a digest, and the scheduler will
    compose one on its next pass.

    The callback is registered with `robust=True`, so a raising `_send` is logged and
    swallowed — the onboarding's own return value is unaffected.
    """

    def refuse(name, args):
        raise RuntimeError("broker down")

    monkeypatch.setattr(digest_enqueue, "_send", refuse)
    user_id = uuid7()

    state = skip_all(user_id=user_id, actor=actor(user_id), now=NOW)

    assert state.completed is True

    # The callback is robust: running it does not raise.
    [_func, _using, robust] = on_commit.captured[0]
    assert robust is True
    on_commit()


def test_a_robust_callback_does_not_raise_when_the_broker_is_down(on_commit):
    """Django's `robust=True` is what makes the difference: the failure is logged, and
    the transaction stands.

    **The flag is honoured by Django's runner, not by the callback.** The callback
    always raises; the runner is what catches a robust one. The fixture's `run()`
    reproduces that distinction, so the test drives it rather than Django's own
    machinery — which refuses to run inside an atomic block, and the test's
    transaction is one.

    The comparison is the point: a plain callback lets the exception out, and that is
    exactly what the onboarding path must not do.
    """

    def boom():
        raise RuntimeError("broker down")

    transaction.on_commit(boom, using=PERSONAL, robust=True)

    on_commit()  # the robust one is swallowed — and logged

    # And the plain one is not: the exception escapes.
    transaction.on_commit(boom, using=PERSONAL, robust=False)

    with pytest.raises(RuntimeError):
        for func, _using, robust in on_commit.captured:
            if not robust:
                func()
