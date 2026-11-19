"""Bearer tokens that prove one thing, once: the digest, and the scan that finds a row.

**Two flows mint tokens of this shape** — a password reset, and an email change — and they
want the same five properties, for the same reasons `PasswordResetToken`'s docstring
records: the raw token is never stored (AD-18), the row is single-use, short-lived,
revocable, and the user is held by value (OQ-8).

**This module exists so the *scan* is written once.** It is the subtle half: it locks, it
tolerates a digest collision across salts, and it refuses to let an expired row shadow a
valid one. A second copy of that reasoning in a second flow is a second place for it to
drift, and a drift here is a security regression rather than a bug — which is why it was
extracted **before** the email-change flow was written rather than after, while the
password-reset suite was still its only caller and could prove it unchanged.

What is *not* here is anything about what a token authorises. Consuming a row, deciding
what a valid one lets the caller do, and what to audit, all belong to the command that
owns the flow.
"""

import hashlib
import secrets

from shared.db import PERSONAL

#: The entropy of a token, in bytes. `token_urlsafe` turns it into a URL-safe string.
TOKEN_BYTES = 32

#: The salt's entropy, in bytes.
SALT_BYTES = 16


def hash_token(token: str, salt: str) -> str:
    """The digest of a token, for one salt. Hex, 64 characters."""
    return hashlib.sha256(f"{salt}{token}".encode()).hexdigest()


def mint_token() -> tuple[str, str]:
    """A fresh `(token, salt)` pair. The token is the only copy that will ever exist."""
    return secrets.token_urlsafe(TOKEN_BYTES), secrets.token_hex(SALT_BYTES)


def find_outstanding(model, token: str, now):
    """The outstanding row of `model` whose token matches the raw `token`, or `None`.

    `model` must carry `token_hash`, `token_salt`, `expires_at`, `used_at` and
    `revoked_at` — the five fields this scan reads.

    The digest depends on the row's own salt, so each outstanding row is checked in turn
    against its own salt. There are at most a handful of outstanding rows per account, and
    the comparison is constant time.

    The rows are read with `select_for_update()`, so two concurrent attempts at the same
    token serialise on the row lock: the second waits, then sees `used_at` set and is
    refused. Without the lock, both could read `used_at IS NULL` and both could act —
    which would break the single-use property under concurrency.

    An expired row does **not** stop the scan. The token is matched by digest, and two
    rows may share a raw token value (different salts, different accounts). If the first
    match is expired, the scan continues, so a later valid row is still reachable.
    """
    candidates = (
        model.objects.using(PERSONAL)
        .select_for_update()
        .filter(used_at__isnull=True, revoked_at__isnull=True)
    )
    for row in candidates:
        if not secrets.compare_digest(row.token_hash, hash_token(token, row.token_salt)):
            continue
        if row.expires_at <= now:
            # Expired. Refused exactly like an unknown token — but the scan continues, so
            # an expired row cannot shadow a valid one further down.
            continue
        return row
    return None
