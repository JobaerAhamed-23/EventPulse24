"""Local development accounts: get-or-create, for a seeded stack (AD-2, AD-18).

**This is not a way to make accounts.** `sign_up` is the way to make accounts, and it is
the only one that is safe to expose to a stranger: it refuses a weak password, it
enumeration-safely declines an address that is already taken, and it tells the *existing
holder* by email rather than telling the caller.

This service exists for the other case: a **seed**. The local stack needs accounts it can
sign into with a known password, repeatedly, on a machine that has no mail server and no
real inbox — and it needs the same accounts to come back the same way every time the seed
runs. `sign_up` is the wrong tool for that, for two reasons that are not stylistic:

- **It emails the existing holder.** A second run of the seed would tell the seeded
  address that "someone tried to sign up with your email" — a notice that is false, aimed
  at an address that is a fixture, on every single re-run.
- **It cannot say what it did.** The outcome shape deliberately carries no
  "created or existed" flag, because to a stranger that flag is an account-existence
  oracle. To a seed command it is the only thing worth knowing.

So the enumeration-safety and the outcome shape live in `sign_up`, and this module is the
**seed-only** door: it is not wired to any endpoint, it is not throttled, and it says
plainly what it did.

**Why it is a service and not a query in the management command.** AD-2's `models-identity`
contract says only `apps.identity` may import `apps.identity.models`; the command lives in
`config`, so it cannot reach the `User` row at all. The command asks this service, which
is the same wall every other caller goes through.

**Why the password is not validated.** `AUTH_PASSWORD_VALIDATORS` are a rule about
*strangers'* passwords. A fixture password is a fixture: it is checked by nothing and
grants nothing but the seeded account. The validators would refuse the obvious local
passwords that make a seed reproducible ("browse-free-local"), and a seed that cannot be
reproduced is not a seed. **This is safe only because nothing here is reachable from the
network** — there is no endpoint that calls it, and `config/urls.py` does not expose it.

**The audit row is written.** An account exists without its audit row only if something
bypasses the command layer, and this module is a command. The action name says what
happened — `seed_account_created` — so an audit reader can tell a seeded account from a
real one. The **address is not in the details** (AD-13): the action names the account and
the row is one lookup away.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.identity.models import User
from apps.identity.services import audit as audit_service
from shared.actor import Actor
from shared.db import PERSONAL


@dataclass(frozen=True)
class AccountOutcome:
    """What `ensure_account` did, and which account it did it to.

    **The `created` flag is the whole point of this module**, and it is safe here for the
    reason it is not safe in `sign_up`: no stranger can reach this. A seed command needs to
    say "created 2, already had 0"; an endpoint must not be able to say "that address
    exists".
    """

    user_id: UUID
    email: str
    created: bool


def ensure_account(*, email: str, password: str) -> AccountOutcome:
    """The account for this address and password, creating it if it is not there yet.

    **Idempotent, and that is the point.** The address is the key: the same call twice
    leaves one account, and the second call reports `created=False`. The email is
    normalised exactly as `sign_up` normalises it — trimmed and lowercased — so
    `Maya@Example.com` and `maya@example.com` are one account and not two.

    **An existing account's password is not changed.** The seed's job is to make an
    account exist, not to reset a password behind the holder's back; a re-run against a
    machine where somebody has changed the fixture password should not silently change it
    back. The password is only ever set on creation.

    **The password is not validated.** See this module's docstring: the validators are a
    rule about strangers' passwords, and this is not reachable by a stranger.
    """
    normalised = User.objects.normalise_email(email)
    if not normalised:
        raise ValueError("An email address is required.")

    with transaction.atomic(using=PERSONAL):
        existing = User.objects.using(PERSONAL).filter(email=normalised).first()
        if existing is not None:
            return AccountOutcome(user_id=existing.pk, email=normalised, created=False)

        try:
            # The insert gets its own savepoint, so an `IntegrityError` from the unique
            # constraint can be caught here without poisoning the outer transaction —
            # the same shape `sign_up` uses, for the same reason.
            with transaction.atomic(using=PERSONAL):
                user = User.objects.db_manager(PERSONAL).create_user(
                    email=normalised,
                    password=password,
                )
        except IntegrityError:
            # A concurrent seed created it first. The account exists either way, which is
            # what the caller asked for.
            winner = User.objects.using(PERSONAL).filter(email=normalised).first()
            if winner is None:  # pragma: no cover — the constraint fired, so it is there
                raise
            return AccountOutcome(user_id=winner.pk, email=normalised, created=False)

        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="seed_account_created",
            target_type="User",
            target_id=user.pk,
            details={"method": "password", "at": datetime.now(UTC).isoformat()},
        )

    return AccountOutcome(user_id=user.pk, email=normalised, created=True)


__all__ = ["AccountOutcome", "ensure_account"]
