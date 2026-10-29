"""Sign-in: authenticate an email and a password, timing-equalised (AD-18).

`authenticate(email, password)` returns the user, or one generic failure. A wrong password
and an unknown email are **indistinguishable** in result and in message.

The timing is equalised too, which is the part that is easy to get wrong. The unknown-email
path still performs a password hash check, against a dummy hash, so the two paths cost the
same:

- The dummy hash is computed **once at import time**, from a random password nobody knows.
  It is a hash of nothing in particular, used only to make the two paths take the same
  time. It authenticates nothing.
- The test monkeypatches `django.contrib.auth.hashers.check_password` with a recorder and
  asserts it was called on the unknown-email path. Removing the equalisation fails the
  suite, which is the point: an "optimisation" that returns early on an unknown email
  turns the endpoint into an account-existence oracle.

The service takes explicit arguments and never a `request` (the spine: "Auth resolved at the
API edge").
"""

import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction

from apps.identity.models import User
from apps.identity.services import audit as audit_service
from apps.identity.services.throttle import is_throttled
from domain.errors import AuthenticationFailedError, ThrottledError
from shared.actor import Actor
from shared.db import PERSONAL

#: The hash the unknown-email path checks against. Computed once, at import time, from a
#: random password. It is here rather than in `shared/constants.py` because that module is
#: stdlib-only (`domain` imports it, and the `domain-pure` contract forbids Django there).
DUMMY_PASSWORD_HASH = make_password(secrets.token_urlsafe(32))


def authenticate(*, email: str, password: str, ip_address: str | None = None) -> User:
    """Return the user for a correct email and password.

    Args:
        email: The address to sign in with. Normalised before it is looked up.
        password: The plain password. It is checked against the stored hash and never
            stored or logged.
        ip_address: The caller's IP, used only for the throttle. Never logged.

    Raises:
        ThrottledError: Too many attempts.
        AuthenticationFailedError: The email and password did not match. The same error,
            with the same message, for a wrong password and for an unknown email.
    """
    normalised = User.objects.normalise_email(email)

    if is_throttled("sign_in", ip_address=ip_address, normalised_email=normalised):
        raise ThrottledError()

    user = User.objects.filter(email=normalised).first()

    if user is None:
        # The equalisation path: a real hash check, against a hash of a random password.
        # Without it, an unknown email would answer far faster than a wrong password, and
        # the difference is an account-existence oracle.
        check_password(password, DUMMY_PASSWORD_HASH)
        raise AuthenticationFailedError()

    if not check_password(password, user.password):
        raise AuthenticationFailedError()

    # A successful sign-in is audited (D14): `actor_kind="user"`, the actor id, and
    # `details={"method": "password"}` — a count-like value, never free text and never
    # the address (AD-13). The row is written in its own transaction, so an audit
    # failure cannot turn a successful sign-in into a failed one.
    with transaction.atomic(using=PERSONAL):
        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="sign_in",
            target_type="User",
            target_id=user.pk,
            details={"method": "password"},
        )

    return user
