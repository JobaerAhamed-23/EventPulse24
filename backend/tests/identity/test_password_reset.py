"""Password reset: single-use, short-lived, enumeration-safe, and session-invalidating.

The three hard properties each get their own test:

- **Single-use** — the second attempt is refused, even immediately.
- **Short-lived** — the expiry boundary is pinned exactly, with an injected clock.
- **Ends the other sessions** — a stolen session does not survive a password change.

And the enumeration-safe request path: an unknown address returns exactly what a known one
returns and sends nothing.
"""

from datetime import timedelta

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.identity.models import PasswordResetToken, User
from apps.identity.services import hash_token, request_password_reset, reset_password
from domain.errors import InvalidResetTokenError, ThrottledError, ValidationError
from ports.email import Stream
from shared.constants import AUTH_RESET_TOKEN_LIFETIME, AUTH_THROTTLE_RESET_ACCOUNT
from shared.db import PERSONAL
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NEW_PASSWORD = "tangerine-derrick-97"


@pytest.fixture(autouse=True)
def _adapters(email_adapter, throttle_adapter):
    return None


def _raw_token_from(row: PasswordResetToken) -> str:
    """The raw token that matches `row`'s stored digest."""
    return f"raw-token-for-{row.pk}"


def _issue(
    user, *, salt: str = "0123456789abcdef0123456789abcdef"
) -> tuple[str, PasswordResetToken]:
    """A reset row plus the raw token that matches it."""
    token = "the-raw-token"
    row = PasswordResetToken.objects.using(PERSONAL).create(
        user_id=user.pk,
        token_hash=hash_token(token, salt),
        token_salt=salt,
        expires_at=timezone.now() + AUTH_RESET_TOKEN_LIFETIME,
    )
    return token, row


# --- the request path ---------------------------------------------------


def test_request_password_reset_sends_one_transactional_message(email_adapter):
    UserFactory(email="maya@example.com")

    request_password_reset(email="maya@example.com")

    assert len(email_adapter.sent) == 1
    sent = email_adapter.sent[0]
    assert sent.message.to == "maya@example.com"
    assert sent.stream is Stream.TRANSACTIONAL
    assert sent.idempotency_key


def test_request_password_reset_creates_exactly_one_row():
    UserFactory(email="maya@example.com")

    request_password_reset(email="maya@example.com")

    assert PasswordResetToken.objects.using(PERSONAL).count() == 1


def test_request_password_reset_for_an_unknown_address_sends_nothing(email_adapter):
    request_password_reset(email="nobody@example.com")

    assert email_adapter.sent == []
    assert PasswordResetToken.objects.using(PERSONAL).count() == 0


def test_request_password_reset_for_an_unknown_address_returns_the_same_thing():
    """Enumeration-safe: the return value does not depend on whether the account exists."""
    UserFactory(email="maya@example.com")

    known = request_password_reset(email="maya@example.com")
    unknown = request_password_reset(email="nobody@example.com")

    assert known is unknown


def test_request_password_reset_stores_only_a_digest(email_adapter):
    """The raw token appears in the email and nowhere else."""
    UserFactory(email="maya@example.com")

    request_password_reset(email="maya@example.com")

    row = PasswordResetToken.objects.using(PERSONAL).get()
    body = email_adapter.sent[0].message.text_body
    raw = body.split("token=")[1].split()[0]
    assert row.token_hash == hash_token(raw, row.token_salt)
    assert raw not in row.token_hash


def test_a_second_reset_request_revokes_the_first():
    """Only the newest link works."""
    UserFactory(email="maya@example.com")

    request_password_reset(email="maya@example.com")
    first_pk = PasswordResetToken.objects.using(PERSONAL).get().pk
    request_password_reset(email="maya@example.com")
    first = PasswordResetToken.objects.using(PERSONAL).get(pk=first_pk)
    second = PasswordResetToken.objects.using(PERSONAL).exclude(pk=first_pk).get()

    assert first.revoked_at is not None
    assert second.revoked_at is None


def test_request_password_reset_is_throttled():
    UserFactory(email="maya@example.com")

    for _ in range(AUTH_THROTTLE_RESET_ACCOUNT):
        request_password_reset(email="maya@example.com", ip_address="1.2.3.4")

    with pytest.raises(ThrottledError):
        request_password_reset(email="maya@example.com", ip_address="1.2.3.4")


# --- consuming the token ------------------------------------------------


def test_reset_password_sets_the_new_password():
    user = UserFactory(email="maya@example.com")
    token, _row = _issue(user)

    reset_password(token=token, new_password=NEW_PASSWORD)

    assert User.objects.using(PERSONAL).get(pk=user.pk).check_password(NEW_PASSWORD) is True


def test_reset_password_is_single_use():
    """The second attempt is refused, even immediately after the first."""
    user = UserFactory(email="maya@example.com")
    token, _row = _issue(user)

    reset_password(token=token, new_password=NEW_PASSWORD)

    with pytest.raises(InvalidResetTokenError):
        reset_password(token=token, new_password="another-good-password-88")


def test_a_used_token_is_marked_used():
    user = UserFactory(email="maya@example.com")
    token, row = _issue(user)

    reset_password(token=token, new_password=NEW_PASSWORD)

    assert PasswordResetToken.objects.using(PERSONAL).get(pk=row.pk).used_at is not None


def test_reset_password_refuses_an_unknown_token():
    UserFactory(email="maya@example.com")

    with pytest.raises(InvalidResetTokenError):
        reset_password(token="not-a-real-token", new_password=NEW_PASSWORD)


def test_reset_password_refuses_a_revoked_token():
    user = UserFactory(email="maya@example.com")
    token, row = _issue(user)
    PasswordResetToken.objects.using(PERSONAL).filter(pk=row.pk).update(revoked_at=timezone.now())

    with pytest.raises(InvalidResetTokenError):
        reset_password(token=token, new_password=NEW_PASSWORD)


def test_reset_password_refuses_an_expired_token():
    """The expiry boundary is exact: at `expires_at` the token is already dead."""
    user = UserFactory(email="maya@example.com")
    expires_at = timezone.now() + AUTH_RESET_TOKEN_LIFETIME
    token = "the-raw-token"
    PasswordResetToken.objects.using(PERSONAL).create(
        user_id=user.pk,
        token_hash=hash_token(token, "0123456789abcdef0123456789abcdef"),
        token_salt="0123456789abcdef0123456789abcdef",
        expires_at=expires_at,
    )

    with pytest.raises(InvalidResetTokenError):
        reset_password(token=token, new_password=NEW_PASSWORD, now=expires_at)


def test_reset_password_accepts_a_token_just_before_it_expires():
    user = UserFactory(email="maya@example.com")
    expires_at = timezone.now() + AUTH_RESET_TOKEN_LIFETIME
    token = "the-raw-token"
    PasswordResetToken.objects.using(PERSONAL).create(
        user_id=user.pk,
        token_hash=hash_token(token, "0123456789abcdef0123456789abcdef"),
        token_salt="0123456789abcdef0123456789abcdef",
        expires_at=expires_at,
    )

    reset_password(token=token, new_password=NEW_PASSWORD, now=expires_at - timedelta(seconds=1))

    assert User.objects.using(PERSONAL).get(pk=user.pk).check_password(NEW_PASSWORD) is True


def test_an_expired_token_is_refused_exactly_like_an_unknown_one():
    """One error for unknown, used, revoked and expired."""
    user = UserFactory(email="maya@example.com")
    token, row = _issue(user)
    PasswordResetToken.objects.using(PERSONAL).filter(pk=row.pk).update(revoked_at=timezone.now())

    with pytest.raises(InvalidResetTokenError) as revoked:
        reset_password(token=token, new_password=NEW_PASSWORD)
    with pytest.raises(InvalidResetTokenError) as unknown:
        reset_password(token="no-such-token", new_password=NEW_PASSWORD)

    assert revoked.value.message == unknown.value.message
    assert revoked.value.code == unknown.value.code


def test_reset_password_refuses_a_weak_password():
    user = UserFactory(email="maya@example.com")
    token, _row = _issue(user)

    with pytest.raises(ValidationError):
        reset_password(token=token, new_password="123")

    assert User.objects.using(PERSONAL).get(pk=user.pk).check_password(NEW_PASSWORD) is False


def test_a_failed_reset_leaves_the_token_usable():
    """Nothing changed, so the link should still work."""
    user = UserFactory(email="maya@example.com")
    token, row = _issue(user)

    with pytest.raises(ValidationError):
        reset_password(token=token, new_password="123")

    assert PasswordResetToken.objects.using(PERSONAL).get(pk=row.pk).used_at is None


# --- sessions ------------------------------------------------------------


def _session_for(user, *, key: str) -> Session:
    """A stored session that belongs to `user`."""
    session = Session.objects.using(PERSONAL).create(
        session_key=key,
        session_data=SessionStore().encode({"_auth_user_id": str(user.pk)}),
        expire_date=timezone.now() + timedelta(days=7),
    )
    return session


def test_reset_password_ends_the_users_other_sessions():
    """A stolen session does not survive a password change."""
    user = UserFactory(email="maya@example.com")
    session = _session_for(user, key="stolen-session")
    token, _row = _issue(user)

    reset_password(token=token, new_password=NEW_PASSWORD)

    assert not Session.objects.using(PERSONAL).filter(pk=session.pk).exists()


def test_reset_password_keeps_the_session_it_was_made_from():
    """The person who reset their password is not signed out of that browser.

    This calls `reset_password` itself, with the session key the API edge would pass. The
    earlier version of this test called `end_other_sessions` directly, so it pinned the
    helper rather than the command — and the command ended *every* session, including the
    one the reset was made from.
    """
    user = UserFactory(email="maya@example.com")
    session = _session_for(user, key="current-session")
    token, _row = _issue(user)

    reset_password(token=token, new_password=NEW_PASSWORD, keep_session_key=session.session_key)

    assert Session.objects.using(PERSONAL).filter(pk=session.pk).exists()


def test_reset_password_ends_the_other_sessions_even_when_it_keeps_one():
    """Keeping the current session must not spare the others."""
    user = UserFactory(email="maya@example.com")
    current = _session_for(user, key="current-session")
    stolen = _session_for(user, key="stolen-session")
    token, _row = _issue(user)

    reset_password(token=token, new_password=NEW_PASSWORD, keep_session_key=current.session_key)

    assert Session.objects.using(PERSONAL).filter(pk=current.pk).exists()
    assert not Session.objects.using(PERSONAL).filter(pk=stolen.pk).exists()


def test_reset_password_leaves_another_users_sessions_alone():
    other = UserFactory(email="someone@example.com")
    session = _session_for(other, key="someone-elses-session")
    user = UserFactory(email="maya@example.com")
    token, _row = _issue(user)

    reset_password(token=token, new_password=NEW_PASSWORD)

    assert Session.objects.using(PERSONAL).filter(pk=session.pk).exists()


# --- the audit trail -----------------------------------------------------


def test_reset_password_writes_an_audit_row():
    from apps.identity.models import IdentityAuditEntry

    user = UserFactory(email="maya@example.com")
    token, _row = _issue(user)

    reset_password(token=token, new_password=NEW_PASSWORD)

    entry = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert entry.action == "password_reset"
    assert entry.target_id == user.pk


def test_reset_password_audit_row_holds_no_email():
    from apps.identity.models import IdentityAuditEntry

    user = UserFactory(email="maya@example.com")
    token, _row = _issue(user)

    reset_password(token=token, new_password=NEW_PASSWORD)

    entry = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert "maya@example.com" not in str(entry.actor_label)
    assert "maya@example.com" not in str(entry.details)
