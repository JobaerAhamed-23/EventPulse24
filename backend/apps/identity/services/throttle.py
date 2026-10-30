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
"""

import hashlib

from ports.registry import get_throttle_port
from shared.constants import (
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
