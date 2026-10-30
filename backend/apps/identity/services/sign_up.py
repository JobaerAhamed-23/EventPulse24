"""Sign-up: create an account, enumeration-safely (AD-18).

`sign_up(email, password)` creates a `User`. Two rules make it safe to expose:

- **The outcome shape never depends on whether the address was already taken.** A caller
  who signs up with an existing address gets the same result as one who signs up with a
  new one. The existing account holder is told by transactional email instead — that is
  the only way *they* learn of it, and it reaches them, not the caller.

- **The email is unique case-insensitively, and the database enforces it.** The value is
  normalised (trimmed and lowercased) before it is written, so a unique index on it *is* a
  case-insensitive unique index. The constraint is what makes two concurrent sign-ups for
  the same address safe: the loser gets an `IntegrityError`, which this service catches and
  turns into the same outcome.

The password goes through Django's configured hashers and `AUTH_PASSWORD_VALIDATORS`. A
weak password is refused with a calm, specific message, before any row is created.

The service takes explicit arguments and never a `request` (the spine: "Auth resolved at the
API edge").
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction

from apps.identity.models import User
from apps.identity.services import audit as audit_service
from apps.identity.services.throttle import is_throttled
from apps.personalization.services.digest_preferences import SOURCE_CHOICE, set_home_city
from domain.errors import ThrottledError, ValidationError
from ports.email import EmailMessage, Stream
from ports.registry import get_email_port
from shared.actor import Actor
from shared.db import PERSONAL
from shared.errors import ErrorItem


@dataclass(frozen=True)
class SignUpOutcome:
    """What a caller learns after a sign-up attempt.

    There is deliberately no field that says whether the account was created or already
    existed. `SignUpOutcome()` is the same value either way, so a caller cannot tell.
    """

    accepted: bool = True


def sign_up(
    *,
    email: str,
    password: str,
    ip_address: str | None = None,
    city: str | None = None,
) -> SignUpOutcome:
    """Create an account, or accept the attempt without revealing a duplicate.

    Args:
        email: The address to sign up with. Normalised before it is stored.
        password: The plain password. It is hashed by Django and never stored, logged or
            returned.
        ip_address: The caller's IP, used only for the throttle. Never logged.
        city: The visitor's home city, carried across from the preview choice. Optional,
            and stored by `personalization`'s published service — `identity` does not
            reach into another app's tables (AD-2).

    Raises:
        ThrottledError: Too many attempts.
        ValidationError: The password is too weak, or the email is not an address.
    """
    normalised = User.objects.normalise_email(email)
    if not normalised:
        raise ValidationError(
            "Enter an email address.",
            details={"errors": [ErrorItem(loc=["email"], msg="Enter an email address.")]},
        )

    if is_throttled("sign_up", ip_address=ip_address, normalised_email=normalised):
        raise ThrottledError()

    _validate_password(password, email=normalised)

    # The account and its audit row commit together, or neither does (AD-5).
    #
    # The `IntegrityError` catch must cover **only the insert**. If it also covered the
    # audit write, an infrastructure failure would roll the account back, report success
    # to the caller, and send the holder a "someone tried to sign up with your email"
    # notice for an account that does not exist.
    #
    # The insert gets its own nested `atomic` block — a savepoint — so its
    # `IntegrityError` can be caught here, at the point of the insert, while the outer
    # block still holds the account and the audit row in one transaction. Raising out of
    # the savepoint rolls back to it and leaves the outer transaction usable.
    with transaction.atomic(using=PERSONAL):
        try:
            with transaction.atomic(using=PERSONAL):
                user = User.objects.create_user(email=normalised, password=password)
        except IntegrityError:
            # The unique constraint fired: the address is taken (or a concurrent
            # sign-up won the race). The caller learns nothing. The account holder is
            # notified by email instead.
            #
            # Rolling back to the savepoint clears the failed insert; the outer
            # transaction is untouched and commits empty.
            _notify_existing_holder(normalised)
            return SignUpOutcome()

        # An `IntegrityError` from the audit row's own integrity is a real failure, not a
        # duplicate: there is no `except` for it, so it propagates and the account rolls
        # back with it. No account exists without its audit row.
        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="sign_up",
            target_type="User",
            target_id=user.pk,
            details={"method": "password"},
        )

    # The city is stored **after** the account commits, and only when the account was
    # actually created. A duplicate sign-up returns above, before this line — so a
    # duplicate never overwrites the real account holder's city. That matters: the
    # duplicate path is the one an attacker reaches, and it must not be able to change
    # another account's stored preferences.
    #
    # **The city is outside the account's transaction on purpose.** The account is the
    # thing that must not be half-made: an account that exists without its audit row is
    # a hole, and one that exists without a city is merely a user whose city we do not
    # know yet — a state the digest already handles, and one the backfill fills. So if
    # the city write fails, the account stands and the city is missing; the opposite
    # trade — rolling the account back because a city could not be stored — would lose
    # a real sign-up over a preference, and would leave the caller with a 500 for an
    # account that might or might not exist.
    #
    # The city is optional, and a caller that sends none stores none. "We do not know
    # where this user is" is a real state, and it is what an account has when the visitor
    # made no preview choice.
    if city is not None:
        set_home_city(
            user_id=user.pk,
            city=city,
            source=SOURCE_CHOICE,
            actor=Actor.user(user.pk),
            now=datetime.now(UTC),
        )

    return SignUpOutcome()


def _validate_password(password: str, *, email: str) -> None:
    """Run Django's configured password validators and report their messages calmly.

    The validator messages can name the email (the similarity validator does). They reach
    the user who is signing up — they supplied the address — and they are never logged.
    """
    user = User(email=email)
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        items = [ErrorItem(loc=["password"], msg=message) for message in exc.messages]
        raise ValidationError(
            "That password doesn't meet our requirements.",
            details={"errors": items},
        ) from exc


def _notify_existing_holder(normalised_email: str) -> None:
    """Tell the account holder that someone tried to sign up with their address.

    The notice goes to the **existing holder**, never back to the caller. The caller
    already got the same outcome shape as for a new address, so this reveals nothing to
    them.
    """
    message = EmailMessage(
        to=normalised_email,
        subject="Someone tried to sign up with your email",
        text_body=(
            "Hi,\n\n"
            "Someone tried to create an EventPulse24 account with this email address.\n\n"
            "If that was you, sign in instead — or reset your password to choose a new "
            "one. If it wasn't you, no account was created and nothing has changed.\n"
        ),
    )
    get_email_port().send(
        message,
        stream=Stream.TRANSACTIONAL,
        idempotency_key=_notice_key(normalised_email),
    )


def _notice_key(normalised_email: str) -> str:
    """The idempotency key for the notice.

    It is built from a digest of the address, never the address itself: the key is stored
    by the email provider and logged by adapters (AD-13).
    """
    digest = hashlib.sha256(normalised_email.encode("utf-8")).hexdigest()[:32]
    return f"auth_signup_notice:{digest}"
