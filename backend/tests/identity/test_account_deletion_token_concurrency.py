"""The cancel token is single-use **under concurrency**, not just in sequence.

The sequential test proves a second attempt is refused. It says nothing about two
attempts that arrive together: without a row lock, both could find the pending request,
both could delete it, and both could report a cancellation — so the token would have
been usable twice, and the audit trail would carry two cancellations for one request.

**This is the property the mail's promise depends on.** The notice says the link "works
only once". A link that works twice is a link that could be followed by a reader of
somebody else's inbox, and a second use would cancel a *new* deletion the account had
since asked for.

`transaction=True`: every thread gets its own connection, and what one commits is visible
to the others, as in production.
"""

import threading

import pytest
from django.db import connections

from apps.identity.models import DeletionRequest, User
from apps.identity.services.deletion import (
    cancel_account_deletion_with_token,
    request_account_deletion,
)
from shared.db import PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL], transaction=True)

TOKEN = "the-raw-cancel-token"
SALT = "0123456789abcdef0123456789abcdef"


def _issue(user):
    """A pending request whose digest matches the raw `TOKEN`."""
    from apps.identity.services import tokens as token_service

    return DeletionRequest.objects.using(PERSONAL).create(
        user_id=user.pk,
        token_hash=token_service.hash_token(TOKEN, SALT),
        token_salt=SALT,
        scheduled_for=request_account_deletion(user_id=user.pk).scheduled_for,
    )


def _cancel_once():
    """One cancellation attempt. Returns "ok" or "refused"."""
    if cancel_account_deletion_with_token(token=TOKEN):
        return "ok"
    return "refused"


def _in_thread():
    """Run one cancellation attempt on its own connection, and report the outcome."""
    outcome = []

    def run():
        try:
            outcome.append(_cancel_once())
        except Exception as exc:  # surfaced in the test thread
            outcome.append(exc)
        finally:
            connections.close_all()

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def test_two_concurrent_cancellations_of_one_token_only_one_succeeds():
    """The single-use property, when the two attempts arrive together.

    **Without the row lock, both threads read the pending request and both delete it** —
    and the token would have been usable twice.
    """
    user = User.objects.create_user(email="maya@example.com", password="pw")
    _issue(user)

    threads = []
    outcomes = []
    for _ in range(2):
        thread, outcome = _in_thread()
        threads.append(thread)
        outcomes.append(outcome)

    for thread in threads:
        thread.join(timeout=30)

    results = [o[0] for o in outcomes if o]
    assert sorted(results) == ["ok", "refused"], f"expected exactly one success, got {results}"


def test_a_concurrently_cancelled_request_is_recorded_exactly_once():
    """**The audit trail must not carry two cancellations for one request.**

    The winner writes the row; the loser writes nothing, because it never found a
    pending request to cancel.
    """
    from apps.identity.models import IdentityAuditEntry

    user = User.objects.create_user(email="maya@example.com", password="pw")
    _issue(user)

    threads = []
    outcomes = []
    for _ in range(2):
        thread, outcome = _in_thread()
        threads.append(thread)
        outcomes.append(outcome)

    for thread in threads:
        thread.join(timeout=30)

    cancellations = list(
        IdentityAuditEntry.objects.filter(
            actor_id=user.pk, action="account_deletion_cancelled"
        ).values_list("action", flat=True)
    )
    assert len(cancellations) == 1
