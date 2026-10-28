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


class PermissionDeniedError(DomainError):
    """For personal data the caller doesn't own, raise NotFoundError instead (no existence leak)."""

    code = "permission_denied"
    default_message = "You don't have access to this."


class ConflictError(DomainError):
    code = "conflict"
    default_message = "This changed since you last looked. Refresh and try again."
