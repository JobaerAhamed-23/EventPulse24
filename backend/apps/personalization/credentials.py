"""Encrypting the calendar credential (AD-18).

The secret ICS/webcal address **is** the credential: Google classifies it as a secret and
offers a reset for it (PRD FR-50). Anyone who can read the `personal` schema can therefore
impersonate the user against their provider until the address is reset. So the stored value
is ciphertext, and this module is the only place that produces it.

Design: .specs-fire/intents/onboarding-and-account/work-items/
calendar-connection-model-design.md (decisions D1-D6, D11).

Three properties, and every decision below serves one of them:

- **The stored value is ciphertext.** AES-256-GCM (D1), in a self-describing envelope that
  can carry a key id (D2), under an application-level key that is separate from
  `SECRET_KEY` (D3).
- **The plaintext exists in as few places as possible.** The model field decrypts it; the
  service wraps it in `ports.calendar.Credential`; nothing else ever sees a bare string.
- **Rotation stays possible.** The envelope names the key that wrote it, so a rotation can
  be a data operation rather than a schema change.

The **key's format** is not defined here: it lives in `shared.credential_key`, which is
stdlib-only. That split keeps `config` — which validates the key at startup — from
reaching the cipher, so the `crypto-library` import contract can hold (D12). The cipher
itself is defined here and nowhere else.

**There is no logger here.** Every statement this module could log would be about a
credential, and there is nothing about a credential that is safe to say (AD-13).
"""

import binascii
import hmac
import os
from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from domain.errors import CredentialDecryptionError
from shared.credential_key import (
    KEY_BYTES,
    KEY_ENV_VAR,
    ParsedKey,
    b64decode,
    b64encode,
    parse_key,
)

#: The envelope's format version. A different format gets a different prefix.
ENVELOPE_PREFIX = "EPENC1"

#: The number of parts in an envelope: prefix, key id, nonce, ciphertext.
ENVELOPE_PARTS = 4

#: GCM's standard nonce length. 96 bits, fresh per encryption, never derived: a reused
#: nonce under one key leaks the XOR of two plaintexts and breaks authentication.
NONCE_BYTES = 12

#: The additional authenticated data. A fixed string, NOT the row id: binding to the row id
#: would make the ciphertext non-portable and would break any migration that rewrites ids.
#: A fixed AAD already prevents cross-purpose confusion — a ciphertext produced for another
#: field or table will not decrypt under this key.
AAD = b"eventpulse24.calendar_connection.credential"


def encrypt(plaintext: str, key: ParsedKey) -> str:
    """Encrypt `plaintext` into an envelope.

    The envelope is `EPENC1.<key_id>.<nonce>.<ciphertext>`, base64url throughout. The
    ciphertext includes GCM's 16-byte tag, so a tampered envelope fails to decrypt rather
    than decrypting to something else.

    A fresh random nonce every time, so encrypting the same address twice yields two
    different ciphertexts.
    """
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(key.key).encrypt(nonce, plaintext.encode("utf-8"), AAD)
    return ".".join((ENVELOPE_PREFIX, key.key_id, b64encode(nonce), b64encode(ciphertext)))


def is_envelope(value: str) -> bool:
    """Whether `value` looks like an envelope this module produced."""
    return isinstance(value, str) and value.startswith(f"{ENVELOPE_PREFIX}.")


def decrypt(envelope: str, key: ParsedKey) -> str:
    """Decrypt an envelope, or raise `CredentialDecryptionError`.

    Every failure mode — a malformed envelope, the wrong key, a tampered ciphertext — is
    the same error. The caller cannot tell them apart, and neither can an attacker: the
    error never says whether the envelope was well-formed.

    It never returns `None` or `""` on failure. A silent empty string would look like
    "this connection has no credential", and the poll would then mark the connection as
    revoked — misreporting a key fault as a revoked address (D7).
    """
    if not isinstance(envelope, str) or not is_envelope(envelope):
        raise CredentialDecryptionError("The stored credential is not a readable encrypted value.")

    parts = envelope.split(".")
    if len(parts) != ENVELOPE_PARTS:
        raise CredentialDecryptionError("The stored credential is not a readable encrypted value.")

    _, key_id, encoded_nonce, encoded_ciphertext = parts
    try:
        nonce = b64decode(encoded_nonce)
        ciphertext = b64decode(encoded_ciphertext)
    except (binascii.Error, ValueError) as exc:
        raise CredentialDecryptionError(
            "The stored credential is not a readable encrypted value."
        ) from exc

    if key_id != key.key_id:
        # The row was written with a different key. The id is in the envelope precisely so
        # this is detectable without decrypting.
        raise CredentialDecryptionError(
            f"The stored credential was written with key {key_id!r}, not {key.key_id!r}."
        )

    try:
        plaintext = AESGCM(key.key).decrypt(nonce, ciphertext, AAD)
    except InvalidTag as exc:
        # The wrong key, or a tampered ciphertext. GCM cannot tell them apart, and neither
        # should the caller.
        raise CredentialDecryptionError(
            "The stored credential could not be decrypted with the configured key."
        ) from exc
    except ValueError as exc:
        # A structurally impossible envelope: a nonce of the wrong length, a ciphertext
        # shorter than GCM's tag. `cryptography` raises a bare `ValueError` here, and a
        # raw `ValueError` escaping this module would break the promise that every
        # failure is a `CredentialDecryptionError` — the caller would have to know which
        # of cryptography's exceptions to expect.
        raise CredentialDecryptionError(
            "The stored credential is not a readable encrypted value."
        ) from exc

    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        # The column decrypts but holds bytes that are not text. That is a corrupt row,
        # not a key fault, and it is still one failure to the caller.
        raise CredentialDecryptionError(
            "The stored credential is not a readable encrypted value."
        ) from exc


def normalise_for_fingerprint(url: str) -> str:
    """The form of an address that identifies the calendar it points at.

    The scheme and the host are lowercased; the path and the query are left exactly as
    typed, because a provider's secret path segment is case-sensitive and lowercasing it
    would name a *different* address. A trailing slash is not touched either: some
    providers treat it as significant.

    The point of this normalisation is that one calendar typed two ways is one calendar.
    """
    text = url.strip()
    parts = urlsplit(text)
    if not parts.scheme or not parts.netloc:
        # Not a URL this module can normalise; the shape check rejects it before it is
        # ever stored. Fingerprint the trimmed text as-is rather than raising here.
        return text
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path,
            parts.query,
            parts.fragment,
        )
    )


def fingerprint(url: str, key: ParsedKey) -> str:
    """A keyed digest of the normalised address, hex.

    Keyed (HMAC-SHA256) rather than a plain hash on purpose: a plain SHA-256 of the
    address is deterministic, so an attacker holding the database could confirm a guessed
    address by comparing digests. With an HMAC keyed by the application key, nobody
    without the key can compute the expected digest for any candidate address — so the
    column reveals nothing about which calendars are connected beyond how many.

    The digest identifies the calendar for the uniqueness constraint, so "is this address
    already connected?" is one indexed lookup instead of decrypting every one of the
    user's rows (D6).

    It is one-way, and it is never returned by the API or shown in the admin.
    """
    normalised = normalise_for_fingerprint(url).encode("utf-8")
    return hmac.new(key.key, normalised, sha256).hexdigest()


__all__ = [
    "AAD",
    "ENVELOPE_PREFIX",
    "KEY_ENV_VAR",
    "KEY_BYTES",
    "NONCE_BYTES",
    "ParsedKey",
    "decrypt",
    "encrypt",
    "fingerprint",
    "is_envelope",
    "normalise_for_fingerprint",
    "parse_key",
]
