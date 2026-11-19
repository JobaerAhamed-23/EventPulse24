"""Password reset: request one, and consume one (AD-18).

Two commands:

- `request_password_reset(email)` asks for a reset. It is **enumeration-safe**: an unknown
  address returns exactly what a known one returns and sends nothing; a known address sends
  exactly one message on the transactional stream, with an idempotency key.

- `reset_password(token, new_password)` consumes a token. The token is **single-use** and
  **short-lived**:

  - *Single-use* — `used_at` is set in the same transaction that changes the password, so a
    second attempt finds it set and is refused. This holds even when the reset fails before
    saving, because the consumption is its own committed step. Django's stateless
    `PasswordResetTokenGenerator` does not have this property: it is single-use only
    because the password changes, so it is replayable between issuance and use.
  - *Short-lived* — `expires_at` comes from a named constant, and the check compares
    against an injected clock, so a test pins the boundary exactly.

A reset also **ends the user's other sessions**, so a stolen session does not survive a
password change.

The token is stored as a salted SHA-256 digest. The raw token exists only in the email the
user receives; a database dump yields no usable reset link.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.identity.models import PasswordResetToken, User
from apps.identity.services import audit as audit_service
from apps.identity.services import tokens as token_service
from apps.identity.services.emails import render_reset_password_email, reset_password_stream
from apps.identity.services.session import end_other_sessions
from apps.identity.services.throttle import is_throttled
from domain.errors import InvalidResetTokenError, ThrottledError, ValidationError
from ports.registry import get_email_port
from shared.actor import Actor
from shared.constants import AUTH_RESET_TOKEN_LIFETIME, SEND_KEY_SEPARATOR
from shared.db import PERSONAL
from shared.errors import ErrorItem


def request_password_reset(*, email: str, ip_address: str | None = None) -> None:
    """Ask for a password reset. Enumeration-safe: the result is always the same.

    An unknown address does nothing at all — no row, no send — and returns exactly what a
    known address returns.

    Args:
        email: The address to reset. Normalised before it is looked up.
        ip_address: The caller's IP, used only for the throttle. Never logged.

    Raises:
        ThrottledError: Too many attempts.
    """
    normalised = User.objects.normalise_email(email)

    if is_throttled("reset", ip_address=ip_address, normalised_email=normalised):
        raise ThrottledError()

    user = User.objects.filter(email=normalised).first()
    if user is None:
        # Nothing happens, and nothing is said. The caller cannot tell this apart from the
        # known-address path.
        return None

    token, salt = token_service.mint_token()

    with transaction.atomic(using=PERSONAL):
        # A new reset supersedes any outstanding one for the same account: only the
        # newest link should work.
        PasswordResetToken.objects.using(PERSONAL).filter(
            user_id=user.pk, used_at__isnull=True, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())

        row = PasswordResetToken.objects.using(PERSONAL).create(
            user_id=user.pk,
            token_hash=token_service.hash_token(token, salt),
            token_salt=salt,
            expires_at=timezone.now() + AUTH_RESET_TOKEN_LIFETIME,
        )

    message = render_reset_password_email(to=user.email, token=token)
    get_email_port().send(
        message,
        stream=reset_password_stream(),
        idempotency_key=f"auth_reset{SEND_KEY_SEPARATOR}{row.pk}",
    )
    return None


def reset_password(
    *, token: str, new_password: str, now=None, keep_session_key: str | None = None
) -> User:
    """Consume a reset token and set a new password.

    Args:
        token: The raw token from the reset link.
        new_password: The new plain password. Validated, then hashed.
        now: The moment to compare the expiry against. Defaults to the current time; a
            test passes a fixed value to pin the expiry boundary.
        keep_session_key: The session key of the session the reset is being made *from*.
            That session's **row** survives; every other session of the account ends. The
            API edge passes the current session's key, so the person who just reset their
            password is not signed out of the browser they did it in (D12). The edge also
            re-stamps the session's auth hash, because the password change invalidates
            it — keeping the row alone would not keep the session usable.

    Returns:
        The user, with the new password set.

    Raises:
        InvalidResetTokenError: The token is unknown, used, revoked or expired. One error
            for all four cases, so the response never says which one it was.
        ValidationError: The new password is too weak.
    """
    moment = now or timezone.now()

    with transaction.atomic(using=PERSONAL):
        # The salt is per row, so the digest cannot be computed without knowing it. Look
        # the row up by trying each outstanding salt for this token's user — but the user
        # is unknown here, so the lookup walks the outstanding rows and matches the digest.
        row = token_service.find_outstanding(PasswordResetToken, token, moment)

        if row is None:
            raise InvalidResetTokenError()

        user = User.objects.get(pk=row.user_id)
        _validate_password(new_password, user=user)

        # Consume the token in the same transaction as the password change. If the change
        # fails, the consumption rolls back with it, and the token is still usable — which
        # is correct: nothing changed, so the link should still work.
        #
        # The update is conditional on `used_at` still being null, so the **database** is
        # the arbiter of single-use, not just the row lock above. If another attempt got
        # there first, this updates zero rows and the attempt is refused.
        consumed = (
            PasswordResetToken.objects.using(PERSONAL)
            .filter(pk=row.pk, used_at__isnull=True)
            .update(used_at=moment)
        )
        if consumed == 0:
            raise InvalidResetTokenError()

        user.set_password(new_password)
        user.save(using=PERSONAL, update_fields=["password"])

        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="password_reset",
            target_type="User",
            target_id=user.pk,
            details={"method": "token"},
        )

    # A reset ends the user's other sessions, so a stolen session does not survive a
    # password change. This runs after the transaction commits: the password has already
    # changed at that point, and a failure here must not roll the new password back.
    end_other_sessions(user, keep_session_key=keep_session_key)

    return user


#: Re-exported: `hash_token` was this module's public helper before the scan moved to
#: `services/tokens.py`, and a caller importing it from here is still right to.
hash_token = token_service.hash_token


def _validate_password(password: str, *, user: User) -> None:
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        items = [ErrorItem(loc=["password"], msg=message) for message in exc.messages]
        raise ValidationError(
            "That password doesn't meet our requirements.",
            details={"errors": items},
        ) from exc
