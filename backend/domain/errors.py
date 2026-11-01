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


class InvalidQuietHoursWindowError(ValidationError):
    """A Quiet Hours window whose start equals its end (FR-12).

    With a pair of local wall clocks that is the only way to express "the whole day", and
    there is no reading of it worth storing: "defer every send forever" is the worst
    possible behaviour for a product whose promise is one notification a day.

    **`domain.quiet_hours` treats `start == end` as disabled and returns the instant
    unchanged** — it never raises, because a pure shift must stay total. The refusal lives
    in the command layer instead, which rejects the window on write so that "no quiet
    hours" has exactly one spelling: a null pair. This error is what it raises.
    """

    code = "invalid_quiet_hours_window"
    default_message = "A quiet window needs a start and an end that differ."


class PermissionDeniedError(DomainError):
    """For personal data the caller doesn't own, raise NotFoundError instead (no existence leak)."""

    code = "permission_denied"
    default_message = "You don't have access to this."


class NotAuthenticatedError(DomainError):
    """The request carried no signed-in account.

    This is a **refusal**, not a malformed request, so it is a 401 rather than the 422 a
    `ValidationError` would give. It is raised at the API edge, after the domain has
    decided that the request may not proceed.

    The code and the message are the same for every unauthenticated request, so the
    refusal says nothing about what the caller was trying to reach.
    """

    code = "not_authenticated"
    default_message = "Please sign in to continue."


class AuthenticationFailedError(NotAuthenticatedError):
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


class CsrfError(DomainError):
    """The request carried no usable CSRF token, and was refused (D13).

    A **refusal**, not a malformed request: the request was well-formed, it just could
    not be shown to come from this site. It is a 403, and it has its own code so the
    frontend can tell it apart from a permission problem — the remedy is different. A
    CSRF failure means "fetch a fresh token and try again"; a permission failure does
    not.

    The message says nothing about *why* the check failed. Django's own reasons — a
    missing cookie, a missing header, a token that does not match, an origin that is not
    trusted — are not the caller's business, and telling them apart would be a way of
    probing the check.
    """

    code = "csrf_failed"
    default_message = "Your session needs refreshing. Reload the page and try again."


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


class CalendarProviderCapReached(ConflictError):
    """The account already has as many connected calendars as its tier allows (FR-50).

    The Free-tier cap is one provider. The user is shown a calm upgrade message, not a
    modal; the API layer decides how, this error only says the cap was hit.

    **This is a conflict, not a bad request.** The address the user pasted is perfectly
    good — it is the *state of the account* that refuses it, because the account already
    holds the one calendar its plan allows. The request was well-formed and conflicts
    with the account, which is what a 409 means; a 400 would say "your request was
    wrong", and it was not. (This is the same reasoning that makes a completed
    onboarding a 409 rather than a 400.)
    """

    code = "calendar_cap_reached"
    default_message = "You've connected the calendars your plan allows."


class CalendarConnectionNotFoundError(NotFoundError):
    """The calendar connection does not exist, or is not the caller's (FR-50).

    **Not found, not forbidden.** A 403 would confirm that the record exists, so a
    caller could probe for other users' connection ids by watching for 403 instead of
    404. A 404 says nothing about what exists — the same rule the personal-events
    endpoints follow.
    """

    code = "calendar_connection_not_found"
    default_message = "We couldn't find that calendar connection."


class TooManyInterestsError(ValidationError):
    """The user picked more interest chips than the flow allows (FR-1).

    FR-1 caps the picks at 3. The extra picks are refused rather than silently dropped,
    because a silently dropped pick leaves the user looking at a chip they chose and is
    not there.
    """

    code = "too_many_interests"
    default_message = "You can pick up to three interests."


class UnknownInterestError(ValidationError):
    """One of the picked interest chips is not one we offer (FR-1).

    The chip list is a fixed constant, so an unknown key means the caller sent something
    that was never on offer. The offending key is named in `details` — it is not
    sensitive (the list is public), and naming it lets the caller see *which* pick was
    wrong.
    """

    code = "unknown_interest"
    default_message = "That isn't one of the interests we offer."


class OnboardingAlreadyCompleteError(ConflictError):
    """The onboarding flow has already finished, so it cannot be moved (FR-1).

    Completion is **terminal**: a user who finished onboarding is never sent back into
    it. The refusal is at the command layer, so every caller gets it rather than only the
    HTTP edge.

    It is a **conflict**, not a malformed request: the request is well-formed, it just
    conflicts with the flow's current state. That makes it a 409, which is what the
    frontend branches on.
    """

    code = "onboarding_already_complete"
    default_message = "You've already finished setting things up."
