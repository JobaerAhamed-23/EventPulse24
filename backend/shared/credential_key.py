"""The credential key's **format** (AD-18). Stdlib only.

This module parses `CALENDAR_CREDENTIAL_KEY` into a key and the id it is known by. It does
not encrypt anything: the cipher lives in `apps.personalization.credentials`, which is the
only module allowed to reach the `cryptography` library.

The split exists so that `config` can validate the key at startup without dragging the
cipher into the settings layer. `config` is above `apps` in AD-2's layering, so a
`config → apps.personalization` import would point the wrong way — and it would make the
settings module able to reach the key-handling code, which is exactly what the
`crypto-library` import contract exists to prevent. So the *format* lives here, in
`shared`, where it is pure and importable from anywhere above the cipher.

Stdlib only, and no `django` import: `parse_key` raises `ImproperlyConfigured`, which
`django.core.exceptions` provides, but that import would make `shared` depend on Django.
The exception is raised by the caller instead — `config.env` wraps this function and
raises the Django error, so the format check and the configuration error stay separate.

Design: .specs-fire/intents/onboarding-and-account/work-items/
calendar-connection-model-design.md (decisions D3, D5).
"""

import base64
import binascii
import re
from dataclasses import dataclass

#: AES-256: a 32-byte key. A shorter key is refused rather than stretched — stretching is
#: a policy decision (PBKDF2 rounds vs HKDF), and doing it implicitly would make the
#: stored key format ambiguous.
KEY_BYTES = 32

#: The key id is short and safe, because it lands in a column an operator might one day
#: display. It is not free text.
KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

#: The environment variable that carries the key. Named in every error message, so the
#: operator is told exactly what to set.
KEY_ENV_VAR = "CALENDAR_CREDENTIAL_KEY"


class InvalidCredentialKey(ValueError):
    """The credential key is missing or malformed.

    A `ValueError` rather than a Django or domain error: this module is pure, and the
    caller decides which error type fits — `config.env` turns it into
    `ImproperlyConfigured`, because a missing key is an operator fault that is never
    mapped to HTTP.
    """


@dataclass(frozen=True)
class ParsedKey:
    """A key and the id it is known by.

    `key_id` is written into every envelope produced under this key, so a row can be
    traced back to the key that encrypted it without decrypting anything.
    """

    key_id: str
    key: bytes

    def __post_init__(self) -> None:
        if len(self.key) != KEY_BYTES:
            raise ValueError(f"A credential key is {KEY_BYTES} bytes, not {len(self.key)}.")


def b64encode(raw: bytes) -> str:
    """base64url, unpadded. A padded encoding would put `=` in the envelope, and the
    envelope is split on `.` — `=` is harmless there, but unpadded is one fewer thing to
    get wrong and the padding has to be restored on the way back either way."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


#: The base64url alphabet, unpadded. A value outside it is an error, not something to skip.
B64URL_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def b64decode(text: str) -> bytes:
    """The inverse of `b64encode`, restoring the padding.

    **Strict**: a character outside the base64url alphabet is an error, not something to
    skip. Python's default `urlsafe_b64decode` silently discards such characters, so a
    value with a stray character would decode to *different bytes* — and if the result
    happened to be the right length it would be accepted while the operator's key was not
    the key in use. A key that is not exactly the key is worse than a key that is
    refused, so the alphabet is checked first and the decode is strict.
    """
    if not isinstance(text, str):
        raise ValueError("A base64url value is text, not bytes.")
    stray = set(text) - B64URL_ALPHABET
    if stray:
        raise ValueError(
            f"A base64url value contains a character outside the alphabet: {sorted(stray)[0]!r}."
        )
    padding = "=" * (-len(text) % 4)
    return base64.b64decode(text + padding, altchars=b"-_", validate=True)


def parse_key(raw: str) -> ParsedKey:
    """Parse `CALENDAR_CREDENTIAL_KEY` into a `ParsedKey`.

    The format is `<key_id>.<base64url-32-bytes>` — for example `k1.aGVsbG8...`. The id and
    the key live in one variable so they cannot drift apart: rotating the key means writing
    a new value, and the id in the envelope then says which key wrote each row.

    A missing or malformed value raises `InvalidCredentialKey`, never a fallback. There is
    no default and no derivation from `SECRET_KEY`: the credential key is separate from the
    session key on purpose (AD-18), and a silent fallback would defeat that.
    """
    if not raw or not raw.strip():
        raise InvalidCredentialKey(
            f"{KEY_ENV_VAR} is not set. It must be '<key_id>.<base64url-encoded "
            f"{KEY_BYTES}-byte key>'. It is required: the calendar credential is encrypted "
            f"with it, and there is no fallback to DJANGO_SECRET_KEY."
        )

    text = raw.strip()
    key_id, separator, encoded = text.partition(".")
    if not separator:
        raise InvalidCredentialKey(
            f"{KEY_ENV_VAR} is malformed. It must be '<key_id>.<base64url-encoded "
            f"{KEY_BYTES}-byte key>'."
        )
    if not KEY_ID_PATTERN.match(key_id):
        raise InvalidCredentialKey(
            f"{KEY_ENV_VAR} has an invalid key id. It must be 1-32 characters of "
            f"letters, digits, '_' or '-'."
        )

    try:
        key = b64decode(encoded)
    except (binascii.Error, ValueError) as exc:
        raise InvalidCredentialKey(f"{KEY_ENV_VAR} is not valid base64url.") from exc

    if len(key) != KEY_BYTES:
        raise InvalidCredentialKey(
            f"{KEY_ENV_VAR} must hold a {KEY_BYTES}-byte key, but it holds {len(key)} bytes."
        )
    return ParsedKey(key_id=key_id, key=key)


__all__ = [
    "KEY_BYTES",
    "KEY_ENV_VAR",
    "KEY_ID_PATTERN",
    "InvalidCredentialKey",
    "ParsedKey",
    "b64decode",
    "b64encode",
    "parse_key",
]
