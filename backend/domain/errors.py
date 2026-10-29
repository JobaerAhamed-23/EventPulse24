"""Domain error types. The HTTP mapping happens once, in config/errors.py.

Default messages follow the UX voice: calm, no urgency, no exclamation marks, no emoji.
"""

from typing import Any


class DomainError(Exception):
    """Base for every expected failure. `code` is a stable machine-readable slug."""

    code: str = "domain_error"
    default_message: str = "Something didn't work as expected."

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None):
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class NotFoundError(DomainError):
    code = "not_found"
    default_message = "We couldn't find that."


class ValidationError(DomainError):
    """Input breaks a rule. Put field errors in details as {"errors": [{"loc", "msg"}]}."""

    code = "invalid_input"
    default_message = "Some details need another look."


class InvalidTimezoneError(ValidationError):
    """A timezone that must be valid isn't (for example a venue registry entry)."""

    code = "invalid_timezone"
    default_message = "That timezone isn't one we recognise."


class InvalidIntervalError(ValidationError):
    """An interval whose end precedes its start."""

    code = "invalid_interval"
    default_message = "That time range doesn't make sense."


class PermissionDeniedError(DomainError):
    """For personal data the caller doesn't own, raise NotFoundError instead (no existence leak)."""

    code = "permission_denied"
    default_message = "You don't have access to this."


class AuthenticationFailedError(ValidationError):
    """The email and password did not match.

    One error for both failures: a wrong password and an unknown email are
    indistinguishable in result and in message (AD-18). The message must not say which
    one it was.
    """

    code = "invalid_credentials"
    default_message = "That email and password don't match."


class InvalidResetTokenError(ValidationError):
    """The reset token was unknown, used, revoked or expired.

    One error for all four cases, so the response never says which one it was (AD-18).
    """

    code = "invalid_reset_token"
    default_message = "That reset link isn't valid anymore. Ask for a new one."


class ThrottledError(DomainError):
    """Too many attempts.

    The message never says whether the account exists: the throttle runs before the
    account is looked up (AD-18).
    """

    code = "rate_limited"
    default_message = "That's a lot of requests. Try again in a little while."


class ConflictError(DomainError):
    code = "conflict"
    default_message = "This changed since you last looked. Refresh and try again."


class SchedulingConflictError(ConflictError):
    """A new event clashes with one the user already has, and the user must choose.

    FR-58's forced choice: the flow cannot complete until the user picks one of the three
    actions, so this is a 409 that carries the conflict and the actions in `details`.

    `details` holds plain data — `{"event_id": ..., "conflicts": [...]}` — because
    `domain` is pure stdlib and cannot import an app's schemas. The API layer builds it.
    """

    code = "scheduling_conflict"
    default_message = "That clashes with something else already on your calendar."


class CredentialDecryptionError(DomainError):
    """A stored credential could not be decrypted (AD-18).

    The wrong key, a corrupted column, or a key that has been retired. This is **not**
    "there is no credential": a cleared credential is a deliberate state (a disconnect
    destroyed it), and collapsing the two would make a key fault look like a revoked
    calendar address — and the poll would then tell the user to reconnect, which fixes
    nothing.
    """

    code = "credential_unreadable"
    default_message = "We couldn't read that calendar connection."


class InvalidCalendarCredentialError(ValidationError):
    """The calendar address failed the shape check.

    Empty, no scheme, an unsupported scheme, or credentials embedded in the userinfo
    component (`https://user:pass@host/...`). The address itself is never echoed back:
    it is a secret, and this error can reach an HTTP response (AD-13).
    """

    code = "invalid_calendar_credential"
    default_message = "That calendar address doesn't look right."


class CalendarProviderCapReached(DomainError):
    """The account already has as many connected calendars as its tier allows (FR-50).

    The Free-tier cap is one provider. The user is shown a calm upgrade message, not a
    modal; the API layer decides how, this error only says the cap was hit.
    """

    code = "calendar_cap_reached"
    default_message = "You've connected the calendars your plan allows."
