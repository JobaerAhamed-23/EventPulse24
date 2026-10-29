"""The credential crypto (AD-18): the envelope, and the fingerprint.

These are the pure unit tests. They need no database and no settings — `credentials.py`
takes the key as an argument and reads nothing from the environment.

The **key's format** is tested separately, in `tests/shared/test_credential_key.py`: it
lives in `shared.credential_key`, which is stdlib-only, so `config` can validate a key at
startup without reaching the cipher.

The properties pinned here are the ones the storage format exists to provide:

- the envelope is self-describing, so a key can be rotated without a schema change;
- the same plaintext encrypts to two different ciphertexts (a fresh nonce every time);
- the fingerprint is **keyed**, so it cannot be computed without the key.
"""

import base64

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from apps.personalization.credentials import (
    AAD,
    ENVELOPE_PREFIX,
    NONCE_BYTES,
    decrypt,
    encrypt,
    fingerprint,
    is_envelope,
    normalise_for_fingerprint,
)
from domain.errors import CredentialDecryptionError
from shared.credential_key import KEY_BYTES, b64encode, parse_key

SECRET = "https://calendar.google.com/calendar/ical/SECRETSECRETSECRET/basic.ics"


def _raw_key(seed: bytes = b"a") -> str:
    """A valid `<key_id>.<base64url-32-bytes>` value."""
    key = (seed * KEY_BYTES)[:KEY_BYTES]
    return "k1." + base64.urlsafe_b64encode(key).rstrip(b"=").decode("ascii")


@pytest.fixture
def key():
    return parse_key(_raw_key())


# ─── The envelope ──────────────────────────────────────────────────────────────


def test_the_envelope_is_self_describing(key):
    envelope = encrypt(SECRET, key)

    prefix, key_id, nonce, ciphertext = envelope.split(".")
    assert prefix == ENVELOPE_PREFIX
    assert key_id == "k1"
    assert nonce and ciphertext


def test_the_envelope_carries_the_key_id(key):
    """A row encrypted with a retired key must be identifiable without decrypting it."""
    envelope = encrypt(SECRET, key)

    assert envelope.split(".")[1] == key.key_id


def test_the_envelope_is_not_the_plaintext(key):
    envelope = encrypt(SECRET, key)

    assert SECRET not in envelope
    assert "calendar.google.com" not in envelope


def test_the_envelope_round_trips(key):
    envelope = encrypt(SECRET, key)

    assert decrypt(envelope, key) == SECRET


def test_encrypting_twice_gives_different_ciphertexts(key):
    """A fresh nonce every time: encrypting the same address twice differs."""
    first = encrypt(SECRET, key)
    second = encrypt(SECRET, key)

    assert first != second
    assert decrypt(first, key) == decrypt(second, key) == SECRET


def test_the_nonce_is_not_derived_from_the_plaintext(key, monkeypatch):
    """A nonce that repeats under one key leaks the XOR of two plaintexts.

    The nonce comes from the CSPRNG and is never derived from the message, so two
    encryptions of the same plaintext carry different nonces.
    """
    first = encrypt(SECRET, key)
    second = encrypt(SECRET, key)

    assert first.split(".")[2] != second.split(".")[2]


def test_the_nonce_is_random(key, monkeypatch):
    """The nonce comes from the OS CSPRNG, never from a deterministic source."""
    import apps.personalization.credentials as credentials

    seen = []

    def fake_urandom(n):
        seen.append(n)
        return bytes(range(n))

    monkeypatch.setattr(credentials.os, "urandom", fake_urandom)

    encrypt(SECRET, key)

    assert seen == [credentials.NONCE_BYTES]


def test_a_wrong_key_fails_loudly(key):
    """A wrong key raises. It never returns None or an empty string.

    A silent empty string would look like "this connection has no credential", and the
    poll would then report a revoked address for what is really a key fault.
    """
    envelope = encrypt(SECRET, key)
    other = parse_key(_raw_key(b"z"))

    with pytest.raises(CredentialDecryptionError):
        decrypt(envelope, other)


def test_a_tampered_ciphertext_fails_loudly(key):
    envelope = encrypt(SECRET, key)
    prefix, key_id, nonce, ciphertext = envelope.split(".")
    flipped = "A" if ciphertext[0] != "A" else "B"
    tampered = ".".join((prefix, key_id, nonce, flipped + ciphertext[1:]))

    with pytest.raises(CredentialDecryptionError):
        decrypt(tampered, key)


def test_a_malformed_envelope_fails_loudly(key):
    with pytest.raises(CredentialDecryptionError):
        decrypt("not-an-envelope", key)

    with pytest.raises(CredentialDecryptionError):
        decrypt("EPENC1.k1.toofewparts", key)


def test_an_envelope_with_unreadable_base64_fails_loudly(key):
    """A nonce or ciphertext that is not base64url is a corrupt row, not a crash.

    The decoder refuses a character outside the alphabet, so a stray `$` in the stored
    value raises rather than decoding to different bytes.
    """
    envelope = encrypt(SECRET, key)
    prefix, key_id, _, ciphertext = envelope.split(".")

    with pytest.raises(CredentialDecryptionError):
        decrypt(".".join((prefix, key_id, "not$base64", ciphertext)), key)

    with pytest.raises(CredentialDecryptionError):
        decrypt(".".join((prefix, key_id, "AAAA", "not$base64")), key)


def test_an_envelope_from_another_key_id_is_refused(key):
    envelope = encrypt(SECRET, key)
    prefix, _, nonce, ciphertext = envelope.split(".")
    other_id = ".".join((prefix, "k9", nonce, ciphertext))

    with pytest.raises(CredentialDecryptionError):
        decrypt(other_id, key)


def test_a_structurally_impossible_envelope_fails_loudly(key):
    """A bad nonce length is a corrupt row, not a crash.

    `cryptography` raises a bare `ValueError` for a nonce it cannot use. A raw
    `ValueError` escaping this module would break the promise that **every** failure is
    a `CredentialDecryptionError` — the caller would have to know which of
    cryptography's exceptions to expect.
    """
    envelope = encrypt(SECRET, key)
    prefix, key_id, _, ciphertext = envelope.split(".")
    short_nonce = ".".join((prefix, key_id, "AAAA", ciphertext))

    with pytest.raises(CredentialDecryptionError):
        decrypt(short_nonce, key)


def test_a_short_ciphertext_fails_loudly(key):
    """A ciphertext shorter than GCM's tag cannot be authenticated."""
    envelope = encrypt(SECRET, key)
    prefix, key_id, nonce, _ = envelope.split(".")
    short_ciphertext = ".".join((prefix, key_id, nonce, "AAAA"))

    with pytest.raises(CredentialDecryptionError):
        decrypt(short_ciphertext, key)


def test_a_non_text_plaintext_fails_loudly(key):
    """A column that decrypts to bytes that are not text is a corrupt row.

    The credential is a URL, so the plaintext is text. Anything else means the column
    holds something that was never written by this module.
    """
    nonce = b"\x00" * NONCE_BYTES
    ciphertext = AESGCM(key.key).encrypt(nonce, b"\xff\xfe\xfd", AAD)
    envelope = ".".join((ENVELOPE_PREFIX, key.key_id, b64encode(nonce), b64encode(ciphertext)))

    with pytest.raises(CredentialDecryptionError):
        decrypt(envelope, key)


def test_is_envelope_recognises_only_our_format(key):
    assert is_envelope(encrypt(SECRET, key)) is True
    assert is_envelope(SECRET) is False
    assert is_envelope("EPENC2.k1.a.b") is False


# ─── The fingerprint ───────────────────────────────────────────────────────────


def test_the_fingerprint_is_stable(key):
    assert fingerprint(SECRET, key) == fingerprint(SECRET, key)


def test_the_fingerprint_differs_for_a_different_address(key):
    other = "https://calendar.google.com/calendar/ical/OTHEROTHEROTHER/basic.ics"

    assert fingerprint(SECRET, key) != fingerprint(other, key)


def test_the_fingerprint_is_keyed(key):
    """Two keys give two fingerprints, so the column leaks nothing without the key.

    A plain hash would be identical under both keys, and an attacker with the database
    could confirm a guessed address by comparing digests.
    """
    other = parse_key(_raw_key(b"z"))

    assert fingerprint(SECRET, key) != fingerprint(SECRET, other)


def test_the_fingerprint_ignores_the_scheme_and_host_case(key):
    upper = "HTTPS://Calendar.Google.COM/calendar/ical/SECRETSECRETSECRET/basic.ics"

    assert fingerprint(upper, key) == fingerprint(SECRET, key)


def test_the_fingerprint_keeps_the_path_case(key):
    """A provider's secret path segment is case-sensitive.

    Lowercasing it would name a *different* address, so two different calendars would
    collide on one fingerprint.
    """
    lower = "https://calendar.google.com/calendar/ical/secretsecretsecret/basic.ics"

    assert fingerprint(lower, key) != fingerprint(SECRET, key)


def test_the_normalisation_lowercases_only_the_scheme_and_host():
    normalised = normalise_for_fingerprint(
        "HTTPS://Calendar.Google.COM/Calendar/ICAL/Secret/basic.ics"
    )

    assert normalised == "https://calendar.google.com/Calendar/ICAL/Secret/basic.ics"


def test_the_normalisation_leaves_a_trailing_slash_alone():
    """Some providers treat a trailing slash as significant."""
    normalised = normalise_for_fingerprint("https://example.com/feed/")

    assert normalised.endswith("/feed/")


def test_the_normalisation_of_a_non_url_falls_back_to_the_trimmed_text(key):
    """A value that is not a URL is fingerprinted as it stands.

    The shape check refuses a non-URL before it is ever stored, so this branch is
    defensive: it must not raise, because `fingerprint` is called on a path where a
    crash would be worse than an imprecise digest.
    """
    normalised = normalise_for_fingerprint("  not-a-url  ")

    assert normalised == "not-a-url"
    assert fingerprint("  not-a-url  ", key) == fingerprint("not-a-url", key)
