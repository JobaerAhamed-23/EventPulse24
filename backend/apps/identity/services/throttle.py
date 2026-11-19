"""Rate limiting for the public auth operations (PRD §11.2).

Three operations are limited: sign-in, sign-up and password-reset request. Each is limited
**per IP** and **per account identifier**, and both are checked. One host cannot spray many
accounts, and one account cannot be sprayed from many hosts.

Two properties matter beyond the counting:

- **The account key is a digest, never the raw email.** A Redis key containing an email
  would put the address in `KEYS` output and in any monitoring dashboard, which AD-13
  forbids. The digest is a key-hygiene measure, not a confidentiality one — the input space
  is small — but it keeps the address out of the store.
- **The check runs before the account is looked up.** A tripped limit therefore says
  nothing about whether the account exists: the caller learns that *they* are being
  throttled, which is the same answer for every address.

The limits are the named constants in `shared/constants.py`.

**A seed can give the allowance back.** `reset_sign_in_throttle` clears the sign-in
windows for a set of accounts and an address, and it exists so that the repeatable seed
starts from a full allowance. It clears the counters, not the rules — the limits are
unchanged, and a reader is still refused the eleventh sign-in in an hour.
"""

import hashlib
from collections.abc import Iterable

from ports.registry import get_throttle_port
from shared.constants import (
    AUTH_THROTTLE_EMAIL_CHANGE_ACCOUNT,
    AUTH_THROTTLE_EMAIL_CHANGE_IP,
    AUTH_THROTTLE_RESET_ACCOUNT,
    AUTH_THROTTLE_RESET_IP,
    AUTH_THROTTLE_SIGN_IN_ACCOUNT,
    AUTH_THROTTLE_SIGN_IN_IP,
    AUTH_THROTTLE_SIGN_UP_ACCOUNT,
    AUTH_THROTTLE_SIGN_UP_IP,
    AUTH_THROTTLE_WINDOW_SECONDS,
)

# The three limited operations, and the (per-IP limit, per-account limit) for each.
LIMITS: dict[str, tuple[int, int]] = {
    "sign_in": (AUTH_THROTTLE_SIGN_IN_IP, AUTH_THROTTLE_SIGN_IN_ACCOUNT),
    "sign_up": (AUTH_THROTTLE_SIGN_UP_IP, AUTH_THROTTLE_SIGN_UP_ACCOUNT),
    "reset": (AUTH_THROTTLE_RESET_IP, AUTH_THROTTLE_RESET_ACCOUNT),
    # An email-change request sends mail to an address the *requester* typed, so an
    # unlimited endpoint is a mailer pointed at anyone. **Its account key digests the
    # account's own address, not the requested one** — keying on the target would let one
    # account spray many victims at full allowance and would open a counter bucket per
    # victim address.
    "email_change": (AUTH_THROTTLE_EMAIL_CHANGE_IP, AUTH_THROTTLE_EMAIL_CHANGE_ACCOUNT),
}

#: The IP part of a key is the address as the edge gave it. It is never logged.
_UNKNOWN_IP = "unknown"


def ip_key(operation: str, ip_address: str | None) -> str:
    """The per-IP counter key."""
    return f"auth:{operation}:ip:{ip_address or _UNKNOWN_IP}"


def account_key(operation: str, normalised_email: str) -> str:
    """The per-account counter key: the operation and a digest of the email.

    The email is lowercased first, so `Maya@Example.com` and `maya@example.com` share one
    bucket. Without that, the per-account limit would be trivially bypassed by varying the
    casing. The lowercasing is done here rather than trusted from the caller, because the
    caller is the thing an attacker controls.
    """
    digest = hashlib.sha256(normalised_email.strip().lower().encode("utf-8")).hexdigest()
    return f"auth:{operation}:acct:{digest}"


def is_throttled(operation: str, *, ip_address: str | None, normalised_email: str) -> bool:
    """Count one attempt against both limits and say whether it is allowed.

    Returns True when the attempt must be refused. The caller answers with a 429 whose
    message says nothing about the account.
    """
    ip_limit, account_limit = LIMITS[operation]
    port = get_throttle_port()
    window = AUTH_THROTTLE_WINDOW_SECONDS

    # The IP is checked first. Both are checked: either one tripping refuses the attempt.
    ip_decision = port.check(ip_key(operation, ip_address), limit=ip_limit, window_seconds=window)
    if not ip_decision.allowed:
        return True

    account_decision = port.check(
        account_key(operation, normalised_email), limit=account_limit, window_seconds=window
    )
    return not account_decision.allowed


def reset_sign_in_throttle(*, ip_address: str | None, emails: Iterable[str]) -> None:
    """Give these sign-in attempts back: clear the sign-in windows.

    **This exists for the repeatable seed, and it is the auth twin of
    `reset_save_allowance`.** The sign-in limits are ten an hour per IP and five an hour
    per account, and the end-to-end suite signs in six times — from **one IP**, because
    the whole suite runs on one machine against one stack. So the suite's own sign-ins
    spend the very allowance a real reader would spend, and a second run inside the hour
    finds the window already up: the sign-in is refused with a 429 and the test fails for
    a reason that has nothing to do with the code under test.

    **The limits themselves are not touched.** This clears the counters, not the rules:
    `AUTH_THROTTLE_SIGN_IN_IP` is still ten and `AUTH_THROTTLE_SIGN_IN_ACCOUNT` is still
    five, and a reader who signs in ten times in an hour is still refused the eleventh.
    What changes is that a *seeded* run starts from a full allowance instead of from
    whatever the previous run left behind.

    **Both counters are cleared, and both have to be.** The per-IP counter is the one
    that trips first for a single-machine suite — six sign-ins from one address is inside
    the limit, but six more from the next run is not — and the per-account counter is
    the one that trips first for an account the suite signs in as more than once. Leaving
    either behind would make the suite's repeatability depend on which limit happened to
    be reached first.

    **The account key is the digest of the normalised address, so the addresses given
    here are normalised the same way before they are keyed.** `account_key` lowercases
    and strips, and the address the sign-in endpoint uses is normalised by
    `UserManager.normalise_email`, so a caller that passed `Maya@Example.com` would
    otherwise clear a key that the sign-in never writes.

    Args:
        ip_address: The address the callers sign in from. Cleared for the sign-in
            operation only.
        emails: The accounts' addresses. Cleared for the sign-in operation only — the
            sign-up and reset windows are not touched, because a seeded run signs in and
            does nothing else.
    """
    port = get_throttle_port()
    port.reset(ip_key("sign_in", ip_address))
    for email in emails:
        port.reset(account_key("sign_in", email.strip().lower()))
