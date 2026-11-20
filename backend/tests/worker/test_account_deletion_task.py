"""The account-deletion worker task: the grace period expiring into a destruction.

**What these tests pin.**

- The **tick enqueues the job on every beat**. A grace period is measured in days, and a
  promise measured in days is not owed at the next five-minute boundary — but a day late
  is a day late, so the job looks every tick and destroys only what is actually due.
- **The job destroys an account whose grace has expired**, and **leaves one alone whose
  grace has not**. The second half is the one that matters: a job that destroyed
  accounts early would make the grace period a lie, and the person would have no way to
  tell.
- **It drains**, so a batch of accounts after an outage clears in one pass.
- **One account that fails does not hold the others hostage.**
- **A cancelled request is never destroyed**, because cancelling removed the row the job
  looks for.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.identity.models import DeletionRequest, User
from apps.identity.services.deletion import cancel_account_deletion, request_account_deletion
from shared.db import CATALOG, PERSONAL
from tests.identity.factories import UserFactory
from worker import tasks

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])


def requested(user):
    """A pending request whose grace period has already expired."""
    request_account_deletion(user_id=user.pk, now=timezone.now() - timedelta(days=31))
    return DeletionRequest.objects.get(user_id=user.pk)


def pending(user):
    """A pending request whose grace period has not expired."""
    request_account_deletion(user_id=user.pk, now=timezone.now())
    return DeletionRequest.objects.get(user_id=user.pk)


# ── The tick ───────────────────────────────────────────────────────────────────────


def test_the_tick_enqueues_the_deletion_job_every_beat(monkeypatch):
    """Every beat rather than on a modulo cadence: the promise is thirty days, and a
    promise measured in days is not owed at the next five-minute boundary."""
    enqueued = []
    monkeypatch.setattr(tasks, "_enqueue", lambda task, *args: enqueued.append(task.name))

    tasks.tick()

    assert "worker.tasks.destroy_due_accounts" in enqueued


# ── The job ────────────────────────────────────────────────────────────────────────


def test_it_destroys_an_account_whose_grace_has_expired():
    user = UserFactory()
    requested(user)

    tasks.destroy_due_accounts()

    assert not User.objects.filter(pk=user.pk).exists()


def test_it_leaves_an_account_whose_grace_has_not_expired_alone():
    """**The half that keeps the promise honest.**

    A job that destroyed accounts early would make the thirty-day grace period a lie,
    and the person would have no way to tell — until their account vanished.
    """
    user = UserFactory()
    pending(user)

    tasks.destroy_due_accounts()

    assert User.objects.filter(pk=user.pk).exists()
    assert DeletionRequest.objects.filter(user_id=user.pk).count() == 1


def test_it_leaves_an_account_with_no_request_alone():
    """**No request, no destruction.** The job asks for the requests that are due; an
    account nobody asked about is not among them."""
    user = UserFactory()

    tasks.destroy_due_accounts()

    assert User.objects.filter(pk=user.pk).exists()


def test_a_cancelled_request_is_never_destroyed():
    """**Cancelling actually stops the destruction.**"""
    user = UserFactory()
    requested(user)
    cancel_account_deletion(user_id=user.pk)

    tasks.destroy_due_accounts()

    assert User.objects.filter(pk=user.pk).exists()


def test_it_drains_rather_than_taking_one():
    """**A batch after an outage clears in one pass**, the same shape as the export
    dispatcher."""
    users = [UserFactory() for _ in range(3)]
    for user in users:
        requested(user)

    tasks.destroy_due_accounts()

    assert not User.objects.filter(pk__in=[user.pk for user in users]).exists()


def test_one_account_that_fails_does_not_hold_the_others_hostage(monkeypatch):
    """**A failure on one account must not strand every other person's deletion.**

    The request row stays, so the next tick tries again — but the other accounts are not
    made to wait for the broken one.
    """
    broken = UserFactory()
    working = UserFactory()
    requested(broken)
    requested(working)

    from apps.identity.services import deletion as deletion_service

    original = deletion_service.destroy_account
    calls = []

    def flaky(*, user_id):
        calls.append(user_id)
        if user_id == broken.pk:
            raise RuntimeError("the row is locked")
        return original(user_id=user_id)

    monkeypatch.setattr(deletion_service, "destroy_account", flaky)

    tasks.destroy_due_accounts()

    assert not User.objects.filter(pk=working.pk).exists()
    assert User.objects.filter(pk=broken.pk).exists()


def test_the_job_reports_how_many_it_destroyed(monkeypatch):
    """**The count is logged**, so a responder can see the job is doing its work."""
    import logging

    user = UserFactory()
    requested(user)

    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture()
    logger = logging.getLogger("worker.tasks")
    logger.addHandler(handler)
    previous = logger.level
    logger.setLevel(logging.INFO)
    try:
        tasks.destroy_due_accounts()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)

    destroyed = [r for r in records if r.msg == "Accounts destroyed"]
    assert destroyed, "the job did not report what it destroyed"
    assert destroyed[0].count == 1
