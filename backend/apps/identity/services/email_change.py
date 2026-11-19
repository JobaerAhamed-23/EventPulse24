"""Moving the login: request a change, and confirm one (AD-5, AD-18).

`User.email` is `USERNAME_FIELD`. Changing it moves the credential a person signs in
with, so **the new address is proven before the login moves**:

- `request_email_change(user_id, new_email)` records an unproven claim and returns what
  the mail needs. **Nothing about the account changes**, and the caller cannot tell a free
  address from one another account already holds.
- `confirm_email_change(token)` consumes the proof and moves the login, once.

**Most of the hard thinking here is `password_reset`'s, reused rather than repeated.** The
token's five properties — digest at rest, single-use, short-lived, revocable, user held by
value — and the scan that finds a row are shared through `services/tokens.py`. What is
genuinely new is below.

**Why a taken address is answered with silence.** `request_password_reset` is
enumeration-safe: an unknown address returns exactly what a known one returns. The mirror
of that here is that an address **another account already holds** must return exactly what
a free one returns — otherwise this endpoint answers *"does an account exist at this
address?"* for anyone who asks. So nothing is written and nothing is sent. **In particular
no mail goes to the taken address**: a mail there would be the oracle in another form, and
a way to send mail to a stranger by typing their address.

**The timing of that path is not constant**, and that is a known, accepted exposure: it
skips a row write. `request_password_reset` accepts the same exposure for the same reason,
and closing it would mean writing rows for addresses that can never be confirmed.

**Why the race is lost at the constraint and not at a pre-check.** Between the request and
the confirmation, another account can claim the address. Checking again at confirm time
narrows the window but does not close it — two confirmations can both pass the check and
then both write. **`user_email_uq` is the only thing that actually arbitrates**, so the
write is attempted and the `IntegrityError` is the answer. It is reported as the same
refusal as every other failure, because to the person holding the link there is no
difference: the address is unavailable and the link did not work.

**Why other sessions are not ended.** `reset_password` ends them, and copying it looks
prudent. It is not, and the reason is specific. Django's session auth hash is an HMAC over
the **password** field, so a password change invalidates every session by itself — which
is why `reset_password` has to pass `keep_session_key` and re-stamp, *rescuing* one
session from a logout the framework already imposed. An email change touches no password,
so nothing is invalidated and ending sessions would be a new, deliberate logout. And it
would not defend the case it appears to: an attacker holding a live session requests a
change to **their own** address, so a logout at confirm time signs out the victim, not the
attacker. What defends that case is the warning sent to the old address — the next work
item's job — together with the throttle here.
"""

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.identity.models import PendingEmailChange, User
from apps.identity.services import audit as audit_service
from apps.identity.services import tokens as token_service
from apps.identity.services.throttle import is_throttled
from domain.errors import InvalidEmailChangeTokenError, ThrottledError, ValidationError
from shared.actor import Actor
from shared.constants import AUTH_EMAIL_CHANGE_TOKEN_LIFETIME
from shared.db import PERSONAL
from shared.errors import ErrorItem

#: The two refusals that are safe to state plainly, as the person who typed them reads
#: them. **Neither echoes the address back** (AD-13) — the field is named, the value is
#: not.
_NO_ADDRESS = "Enter an email address."
_SAME_ADDRESS = "That's already your email address."


@dataclass(frozen=True)
class EmailChangeRequest:
    """What the mail item needs, and nothing more.

    **The raw token exists only here and in the link.** It is never stored, never logged
    and never audited, so this object is the one and only copy on its way out.

    **Both addresses are carried** because two different messages are owed: the
    confirmation goes to the new address, and the warning that a change was asked for goes
    to the old one. A caller holding only one of them could not send both.

    **`row_id` is here to be the send's idempotency key**, the way `request_password_reset`
    keys its send on the token row's primary key — not for the mail to display.
    """

    token: str
    new_email: str
    old_email: str
    row_id: object
    expires_at: object


def request_email_change(
    *, user_id, new_email: str, ip_address: str | None = None
) -> EmailChangeRequest | None:
    """Ask to move the login to `new_email`.

    Returns what the mails need, or **`None` when nothing is to be sent** — which is both
    the "address already taken" case and any other dead end. A caller must not infer
    anything from `None`; that is the whole point of it.

    Args:
        user_id: The account asking.
        new_email: The address to move to. Normalised before anything is done with it.
        ip_address: The caller's IP, used only for the throttle. Never logged.

    Raises:
        ThrottledError: Too many requests.
        ValidationError: The address is the one the account already has.
    """
    normalised = User.objects.normalise_email(new_email)
    user = User.objects.using(PERSONAL).get(pk=user_id)

    # **Keyed on the account's own address**, not the requested one — see the module
    # docstring. The throttle runs first, so a tripped limit says nothing about the
    # address that was typed.
    if is_throttled("email_change", ip_address=ip_address, normalised_email=user.email):
        raise ThrottledError()

    if not normalised:
        raise ValidationError(
            _NO_ADDRESS,
            details={"errors": [ErrorItem(loc=["new_email"], msg=_NO_ADDRESS)]},
        )

    # **Not a refusal to hide.** Asking to change your address to the one you already have
    # is a mistake about your own account, not a probe of someone else's, so it is
    # answered plainly.
    if normalised == user.email:
        raise ValidationError(
            _SAME_ADDRESS,
            details={"errors": [ErrorItem(loc=["new_email"], msg=_SAME_ADDRESS)]},
        )

    # **Taken by another account: silence.** No row, no mail, and a return value the
    # caller cannot distinguish from the free-address path.
    if User.objects.using(PERSONAL).filter(email=normalised).exclude(pk=user.pk).exists():
        return None

    token, salt = token_service.mint_token()
    expires_at = timezone.now() + AUTH_EMAIL_CHANGE_TOKEN_LIFETIME

    with transaction.atomic(using=PERSONAL):
        # A new request supersedes any outstanding one: two live links for one account
        # would be two ways in.
        PendingEmailChange.objects.using(PERSONAL).filter(
            user_id=user.pk, used_at__isnull=True, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())

        row = PendingEmailChange.objects.using(PERSONAL).create(
            user_id=user.pk,
            new_email=normalised,
            token_hash=token_service.hash_token(token, salt),
            token_salt=salt,
            expires_at=expires_at,
        )

        # **No address in the details** (AD-13). That a change was requested is the fact
        # worth keeping; which address it was for is PII, and the row itself holds it.
        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="email_change_requested",
            target_type="User",
            target_id=user.pk,
            details={"method": "token"},
        )

    return EmailChangeRequest(
        token=token,
        new_email=normalised,
        old_email=user.email,
        row_id=row.pk,
        expires_at=expires_at,
    )


def cancel_email_change(*, user_id) -> int:
    """Call off any outstanding change for this account. Returns how many were revoked.

    **This is the user-facing half of the warning mail's remedy.** The mail tells someone
    who did not ask for the change that a password reset stops it; this is the gentler
    route for the much commoner case — the account holder changed their mind, or mistyped
    the address and would rather start again than wait a day for a link they cannot use.

    **Cancelling when nothing is pending is not an error.** The caller's intent — *"have
    no pending change"* — is satisfied either way, which is the rule `sign_out` already
    follows for signing out when nobody is signed in. An endpoint that refused would make
    every client check first, and the check would race with the cancel anyway.

    **Revoked, not deleted.** `revoked_at` is what the row's check constraint is built
    around, and a deleted row would lose the fact that a change was asked for and called
    off — which is exactly the history an account holder investigating a takeover wants.
    """
    with transaction.atomic(using=PERSONAL):
        revoked = (
            PendingEmailChange.objects.using(PERSONAL)
            .filter(user_id=user_id, used_at__isnull=True, revoked_at__isnull=True)
            .update(revoked_at=timezone.now())
        )

        # **Audited even when nothing was pending.** That somebody pressed cancel is the
        # fact worth keeping; whether there happened to be a row is not. No address in
        # the details (AD-13).
        audit_service.write_audit(
            actor=Actor.user(user_id),
            action="email_change_cancelled",
            target_type="User",
            target_id=user_id,
            details={"method": "user"},
        )

    return revoked


def confirm_email_change(*, token: str, now=None) -> User:
    """Consume a token and move the login to the address it proves.

    Args:
        token: The raw token from the confirmation link.
        now: The moment to compare the expiry against. Defaults to the current time; a
            test passes a fixed value to pin the expiry boundary.

    Returns:
        The user, with the new login address.

    Raises:
        InvalidEmailChangeTokenError: The token is unknown, used, revoked, expired — or
            the address was claimed by someone else in the meantime. **One error for all
            five**, so the response never says which it was.
    """
    moment = now or timezone.now()

    with transaction.atomic(using=PERSONAL):
        row = token_service.find_outstanding(PendingEmailChange, token, moment)
        if row is None:
            raise InvalidEmailChangeTokenError()

        user = User.objects.using(PERSONAL).get(pk=row.user_id)

        # Consume in the same transaction as the move. The update is conditional on
        # `used_at` still being null, so the **database** is the arbiter of single-use and
        # not just the row lock: if another attempt got there first this updates zero
        # rows, and the attempt is refused.
        consumed = (
            PendingEmailChange.objects.using(PERSONAL)
            .filter(pk=row.pk, used_at__isnull=True)
            .update(used_at=moment)
        )
        if consumed == 0:
            raise InvalidEmailChangeTokenError()

        user.email = row.new_email
        try:
            # **The constraint is the arbiter.** A pre-check would narrow the race and not
            # close it. `savepoint` so the IntegrityError does not poison the outer
            # transaction — without it, nothing after this could run, including the raise
            # being reported cleanly.
            with transaction.atomic(using=PERSONAL):
                user.save(using=PERSONAL, update_fields=["email"])
        except IntegrityError as exc:
            # Someone else holds the address now. Same refusal as every other failure.
            #
            # **The raise rolls the whole transaction back, so the row is left
            # unconsumed**, and that is deliberate rather than overlooked. It is
            # `reset_password`'s rule — *"if the change fails, the consumption rolls back
            # with it ... nothing changed, so the link should still work"* — and the
            # alternative, marking a token used by a change that did not happen, would
            # record something untrue.
            #
            # **The link is then useless but harmless**: the address it names belongs to
            # someone else, so every retry takes this same branch, and the next request
            # revokes this row anyway. Nothing is left that could move a login.
            raise InvalidEmailChangeTokenError() from exc

        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="email_change_confirmed",
            target_type="User",
            target_id=user.pk,
            details={"method": "token"},
        )

    # **No session is ended** — see the module docstring. An email change invalidates no
    # session auth hash, and ending sessions here would sign out the victim rather than an
    # attacker.
    return user
