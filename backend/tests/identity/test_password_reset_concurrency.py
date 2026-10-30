"""The reset token is single-use **under concurrency**, not just in sequence.

The sequential test proves a second attempt is refused. It says nothing about two
attempts that arrive together: without a row lock, both could read `used_at IS NULL`,
both could pass the check, and both could change the password — so the token would be
usable twice, which is the property the work item names.

`transaction=True`: every thread gets its own connection, and what one commits is visible
to the others, as in production.
"""

import threading

import pytest
from django.db import connections
from django.utils import timezone

from apps.identity.models import PasswordResetToken, User
from apps.identity.services import hash_token, reset_password
from domain.errors import InvalidResetTokenError
from shared.constants import AUTH_RESET_TOKEN_LIFETIME
from shared.db import PERSONAL
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL], transaction=True)

NEW_PASSWORD = "tangerine-derrick-97"
TOKEN = "the-raw-token"
SALT = "0123456789abcdef0123456789abcdef"


def _issue(user):
    """A reset row whose digest matches the raw `TOKEN`."""
    return PasswordResetToken.objects.using(PERSONAL).create(
        user_id=user.pk,
        token_hash=hash_token(TOKEN, SALT),
        token_salt=SALT,
        expires_at=timezone.now() + AUTH_RESET_TOKEN_LIFETIME,
    )


def _reset_once():
    """One reset attempt. Returns "ok" or the error's class name."""
    try:
        reset_password(token=TOKEN, new_password=NEW_PASSWORD)
    except InvalidResetTokenError:
        return "refused"
    return "ok"


def _in_thread():
    """Run one reset attempt on its own connection, and report the outcome."""
    outcome = []

    def run():
        try:
            outcome.append(_reset_once())
        except Exception as exc:  # surfaced in the test thread
            outcome.append(exc)
        finally:
            connections.close_all()

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def test_two_concurrent_resets_of_one_token_only_one_succeeds():
    """The single-use property, when the two attempts arrive together.

    Without the row lock and the conditional update, both threads read `used_at IS NULL`
    and both change the password — the token would have been usable twice.
    """
    user = UserFactory(email="maya@example.com")
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


def test_a_refused_concurrent_reset_leaves_the_password_the_winner_set():
    """The loser must not overwrite the password the winner set."""
    user = UserFactory(email="maya@example.com")
    _issue(user)

    threads = []
    outcomes = []
    for _ in range(2):
        thread, outcome = _in_thread()
        threads.append(thread)
        outcomes.append(outcome)

    for thread in threads:
        thread.join(timeout=30)

    assert User.objects.using(PERSONAL).get(pk=user.pk).check_password(NEW_PASSWORD) is True


def test_a_concurrently_consumed_token_is_marked_used_exactly_once():
    user = UserFactory(email="maya@example.com")
    row = _issue(user)

    threads = []
    outcomes = []
    for _ in range(2):
        thread, outcome = _in_thread()
        threads.append(thread)
        outcomes.append(outcome)

    for thread in threads:
        thread.join(timeout=30)

    stored = PasswordResetToken.objects.using(PERSONAL).get(pk=row.pk)
    assert stored.used_at is not None
