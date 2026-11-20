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


class InvalidEmailChangeTokenError(ValidationError):
    """The email-change token was unknown, used, revoked, expired — or lost the race.

    **One error for all five cases**, the same rule `InvalidResetTokenError` states: a
    message that distinguished them would be an oracle for guessing tokens (AD-18).

    **The fifth case is the one this flow has and the reset flow does not.** Between the
    request and the confirmation, another account can claim the address; the confirmation
    then loses on `user_email_uq`. That is not a different kind of failure to the person
    holding the link — their address is unavailable and the link did not work — so it is
    not a different error.

    **It is its own class rather than a reuse of `InvalidResetTokenError`** so the two
    flows' refusals cannot be confused, by a caller or by a test.
    """

    code = "invalid_email_change_token"
    default_message = "That link isn't valid anymore. Ask for a new one."


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


class SaveCapReached(ConflictError):
    """The account has used the saves its tier allows in this window (FR-49).

    **A conflict, not a rate limit.** The request is well-formed and the event is
    perfectly saveable; it is the *state of the account* that refuses it, because the
    account has already spent its allowance. A 429 would say "come back later", and the
    remedy here is not to wait — it is to upgrade. So this is a 409, the same shape as
    `CalendarProviderCapReached`, which is the reference for the payload too.

    **Its own `code`, because the save endpoint already answers 409.** A conflicting save
    answers 409 with `SchedulingConflictError`, and the two must be told apart by the
    client without guessing. `save_cap_reached` and `calendar_cap_reached` are different
    facts about different limits.

    **`details` carries the cap and one upgrade sentence** — `{"cap", "upgrade_hint"}`, and
    nothing else. The hint is an **inline** prompt with a quiet "Upgrade" link, not a modal
    (EXPERIENCE.md §3, the Free-tier cap prompt), so the payload carries no modal-shaped
    field at all: no `modal`, no `title`, no `actions`, no `dismissable`.
    """

    code = "save_cap_reached"
    default_message = "You've used your free save for today."


class QuietHoursProRequired(ConflictError):
    """Per-weekday quiet hours are a Pro feature, and this account is not Pro (FR-51).

    **A conflict, not a 403.** The request is well-formed and the windows are perfectly
    storable; it is the *state of the account* that refuses them. A 403 would say "you may
    not do this", and the remedy here is not a permission grant — it is an upgrade. That is
    the same reasoning that made `SaveCapReached` and `CalendarProviderCapReached` 409s, and
    this carries their payload for the same reason.

    **`details` carries `{"cap", "upgrade_hint"}`** — the cap being the one window a Free
    account gets — so the inline upgrade prompt built for the save cap renders this with no
    new component and no new copy path. As there, the payload carries **no modal-shaped
    field**: no `modal`, no `title`, no `actions`, no `dismissable`. A paywall that
    interrupts is the thing this product's posture is against.

    **It refuses the write, never the read.** A lapsed Pro user's seven windows are their
    own data and are never deleted, so they can always be read back; what a lapse removes is
    their effect and the ability to change them. The read reports both the stored overrides
    and the effective week, so nobody is shown seven windows that are not in force.
    """

    code = "quiet_hours_pro_required"
    default_message = "Setting a different window for each day is part of Pro."


class InvalidCollectionOrderError(ValidationError):
    """A reorder did not name this user's collections exactly once each (FR-49).

    **A client can send this, so it cannot be a `ValueError`.** The reorder body comes
    straight off the wire, and a `ValueError` from the command layer reaches the caller as
    a 500 — a server error for a request the server understood perfectly and chose to
    refuse. This is a 422 with a sentence, like any other refused input.

    **A partial list is refused rather than completed.** The collections it does not name
    would have to be placed somewhere this code invented, and an order nobody asked for is
    worse than a refusal.
    """

    code = "invalid_collection_order"
    default_message = "That ordering doesn't match your collections."


class CollectionsProRequired(ConflictError):
    """Named collections are a Pro feature, and this account is not Pro (FR-49).

    **A conflict, not a 403.** The request is well-formed and the collection is perfectly
    storable; what refuses it is the *state of the account*, and the remedy is not a
    permission grant but an upgrade. The same reasoning that made `SaveCapReached`,
    `CalendarProviderCapReached` and `QuietHoursProRequired` 409s, and this carries their
    payload for the same reason.

    **`details` carries `{"cap", "upgrade_hint"}`** — the cap being zero, which is what a
    Free account gets — so the inline prompt built for the save cap renders this with no new
    component and no new copy path. As there, the payload carries **no modal-shaped field**:
    no `modal`, no `title`, no `actions`, no `dismissable`.

    **It refuses the two operations that add, never the ones that read or tidy.** A lapsed
    Pro user keeps their collections, keeps reading them, and keeps renaming, reordering,
    unassigning and deleting — what they lose is the ability to make the set bigger. The
    brief forbids deleting a downgraded user's data, and a gate that froze their own names
    and ordering would be punishing them for lapsing rather than bounding a tier.
    """

    code = "collections_pro_required"
    default_message = "Collections are part of Pro."


class CollectionNameTaken(ConflictError):
    """This user already has a collection with this name (FR-49).

    **A conflict, not a validation error.** The name is perfectly well-formed; what refuses
    it is the state of the account — a collection already holds it. That is the same
    distinction `AlreadySubscribedError` draws, and it is why the status is 409 rather than
    422: nothing about the request needs correcting except the user's mind.

    **Names are compared case-insensitively**, so "Weekend" collides with "weekend".
    `saved_collection_user_name_uq` folds the case in the database; this error is what that
    constraint looks like once it reaches a person. A list showing both spellings as two
    collections would read as a bug to whoever made them.
    """

    code = "collection_name_taken"
    default_message = "You already have a collection with that name."


class CollectionNotFoundError(NotFoundError):
    """The collection doesn't exist, or isn't the caller's (FR-49).

    **One error for both cases, deliberately** — the same choice `SavedEventNotFoundError`
    made. Telling a caller "it exists but is not yours" would confirm the existence of
    another user's collection, and a name is user-written content.
    """

    code = "collection_not_found"
    default_message = "We couldn't find that collection."


class CalendarConnectionNotFoundError(NotFoundError):
    """The calendar connection does not exist, or is not the caller's (FR-50).

    **Not found, not forbidden.** A 403 would confirm that the record exists, so a
    caller could probe for other users' connection ids by watching for 403 instead of
    404. A 404 says nothing about what exists — the same rule the personal-events
    endpoints follow.
    """

    code = "calendar_connection_not_found"
    default_message = "We couldn't find that calendar connection."


class CalendarNotSyncable(ConflictError):
    """The connection is the caller's, but it is in no state to be synced (FR-50).

    **A conflict, not a not-found.** The caller has already been shown this connection in
    their own list, so pretending it does not exist would contradict the screen they are
    looking at. What is wrong is its *state*: a `needs_reconnect` connection holds a
    credential the provider has already rejected, and a `disconnected` one holds none at
    all. Neither can be fetched with, and neither is fixed by asking again.

    The remedy is a different action — reconnect — so the message names it.
    """

    code = "calendar_not_syncable"
    default_message = "That calendar isn't connected right now. Reconnect it first."


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


class EventAlreadyRetiredError(ConflictError):
    """The event has already been retired, so it cannot be retired again.

    Retiring is how a listing leaves the catalog for good (FR-13: never deleted, only
    superseded). Doing it twice would leave a second replacement row that nothing points
    at, so the second attempt is refused rather than half-done.
    """

    code = "event_already_retired"
    default_message = "That event has already been retired."


class AlreadySubscribedError(ConflictError):
    """The caller already holds a live subscription, so a second checkout is refused (FR-48).

    **A conflict, not a bad request.** The request is well-formed and the plan is one this
    product sells; it conflicts with the *state of the account*, which is what a 409 means.
    A 400 would say "your request was wrong", and it was not.

    The refusal points at the portal, because that is where an existing subscription is
    actually managed — changing card, changing plan, cancelling. Sending a paying user to
    a second checkout would create a second subscription they then have to notice and
    cancel, which is a worse outcome than being told where to go.

    `details` carries the portal path so the frontend can offer one clear next step rather
    than inventing a route of its own.
    """

    code = "already_subscribed"
    default_message = "Your Pro subscription is already active."


class NoSubscriptionError(ConflictError):
    """The caller asked for the customer portal but holds no subscription (FR-48).

    The portal is where a **paying** user manages their plan, card and cancellation. A user
    with no subscription has no customer reference, so there is nothing for the provider to
    open a session against — and saying so plainly is better than letting the caller reach
    the provider and receive an error about a customer that does not exist.

    It is a **conflict**, not a malformed request: the request is well-formed; the account's
    state is what refuses it. The message says plainly that there is no subscription to
    manage, because the only sensible next step for someone with no subscription is to start
    one — and the frontend decides where that step leads.
    """

    code = "no_subscription"
    default_message = "You don't have a subscription to manage yet."
