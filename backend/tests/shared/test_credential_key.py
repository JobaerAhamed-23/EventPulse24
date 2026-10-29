"""The credential key's **format** (AD-18).

`shared.credential_key` holds the key's shape and nothing else: it cannot encrypt, so a
module that may validate a key (such as `config`) cannot read a credential with it. The
cipher lives in `apps.personalization.credentials` and is tested there.

These are the pure unit tests: no database, no settings, no Django.

The properties pinned here are the ones the format exists to provide:

- a missing or malformed key is **refused loudly**, never defaulted or stretched;
- the key id is safe to put in a column an operator might one day display;
- the key and its id live in one value, so they cannot drift apart;
- the exception is a plain `ValueError`, so the caller chooses the error type — a missing
  key is an operator fault, and `config` turns it into Django's `ImproperlyConfigured`.
"""

import base64

import pytest

from shared.credential_key import (
    KEY_BYTES,
    KEY_ENV_VAR,
    KEY_ID_PATTERN,
    InvalidCredentialKey,
    ParsedKey,
    b64decode,
    b64encode,
    parse_key,
)


def _raw_key(seed: bytes = b"a") -> str:
    """A valid `<key_id>.<base64url-32-bytes>` value."""
    key = (seed * KEY_BYTES)[:KEY_BYTES]
    return "k1." + base64.urlsafe_b64encode(key).rstrip(b"=").decode("ascii")


# ─── The key ───────────────────────────────────────────────────────────────────


def test_a_valid_key_parses():
    parsed = parse_key(_raw_key())

    assert parsed.key_id == "k1"
    assert len(parsed.key) == KEY_BYTES


def test_a_missing_key_is_refused():
    with pytest.raises(InvalidCredentialKey) as excinfo:
        parse_key("")

    assert KEY_ENV_VAR in str(excinfo.value)


def test_a_blank_key_is_refused():
    with pytest.raises(InvalidCredentialKey):
        parse_key("   ")


def test_a_none_key_is_refused():
    with pytest.raises(InvalidCredentialKey):
        parse_key(None)


def test_a_key_without_a_key_id_is_refused():
    with pytest.raises(InvalidCredentialKey) as excinfo:
        parse_key(base64.urlsafe_b64encode(b"a" * KEY_BYTES).rstrip(b"=").decode())

    assert KEY_ENV_VAR in str(excinfo.value)


def test_a_short_key_is_refused():
    """A 16-byte key is refused rather than stretched.

    Stretching is a policy decision (PBKDF2 rounds vs HKDF), and doing it implicitly would
    make the stored key format ambiguous.
    """
    short = base64.urlsafe_b64encode(b"a" * 16).rstrip(b"=").decode()

    with pytest.raises(InvalidCredentialKey) as excinfo:
        parse_key(f"k1.{short}")

    assert "32" in str(excinfo.value)


def test_a_long_key_is_refused():
    long_key = base64.urlsafe_b64encode(b"a" * 64).rstrip(b"=").decode()

    with pytest.raises(InvalidCredentialKey):
        parse_key(f"k1.{long_key}")


def test_a_key_that_is_not_base64_is_refused():
    with pytest.raises(InvalidCredentialKey):
        parse_key("k1.not-valid-base64!!")


def test_a_key_with_a_stray_character_is_refused():
    """A key that decodes to 32 bytes is not *accepted* — it is a different key.

    Python's default base64 decoding silently discards characters outside the alphabet.
    A value with a stray character must be refused outright, not silently shortened into
    some other 32 bytes: the key in use would not be the key the operator wrote.
    """
    encoded = base64.urlsafe_b64encode(b"a" * 32).rstrip(b"=").decode()
    stray = encoded[:5] + "$" + encoded[5:]

    with pytest.raises(InvalidCredentialKey):
        parse_key(f"k1.{stray}")


def test_a_key_with_a_space_is_refused():
    encoded = base64.urlsafe_b64encode(b"a" * 32).rstrip(b"=").decode()

    with pytest.raises(InvalidCredentialKey):
        parse_key(f"k1.{encoded[:5]} {encoded[5:]}")


def test_a_key_with_a_standard_base64_character_is_refused():
    """`+` and `/` are the standard alphabet, not the URL-safe one.

    A key pasted from a standard-base64 tool would decode to *different bytes* under a
    decoder that accepted both alphabets, so it is refused rather than reinterpreted.
    """
    with pytest.raises(InvalidCredentialKey):
        parse_key("k1.ab+cd/ef")


def test_a_key_id_with_unsafe_characters_is_refused():
    """The key id lands in a column an operator might one day display."""
    encoded = base64.urlsafe_b64encode(b"a" * KEY_BYTES).rstrip(b"=").decode()

    with pytest.raises(InvalidCredentialKey):
        parse_key(f"k 1 <script>.{encoded}")


def test_the_key_id_pattern_allows_only_safe_characters():
    assert KEY_ID_PATTERN.match("k1")
    assert KEY_ID_PATTERN.match("key-2026_v2")
    assert not KEY_ID_PATTERN.match("")
    assert not KEY_ID_PATTERN.match("k 1")
    assert not KEY_ID_PATTERN.match("k.1")
    assert not KEY_ID_PATTERN.match("k1;drop")


def test_a_very_long_key_id_is_refused():
    encoded = base64.urlsafe_b64encode(b"a" * KEY_BYTES).rstrip(b"=").decode()

    with pytest.raises(InvalidCredentialKey):
        parse_key(f"{'k' * 33}.{encoded}")


def test_the_key_is_surrounded_by_whitespace_is_accepted():
    """An operator pasting the value into a `.env` file adds whitespace."""
    parsed = parse_key(f"  {_raw_key()}  ")

    assert parsed.key_id == "k1"


def test_a_parsed_key_rejects_a_wrong_length():
    with pytest.raises(ValueError):
        ParsedKey(key_id="k1", key=b"short")


def test_the_key_id_is_never_the_secret():
    """The key id goes into every envelope, so it must be the *id*, not the key."""
    parsed = parse_key(_raw_key())

    assert parsed.key_id == "k1"
    assert parsed.key != parsed.key_id.encode("ascii")


# ─── The base64url helpers ─────────────────────────────────────────────────────


def test_the_encoding_round_trips():
    raw = b"\x00\x01\x02\xfd\xfe\xff"

    assert b64decode(b64encode(raw)) == raw


def test_the_encoding_is_unpadded():
    """A padded encoding would put `=` in the envelope."""
    encoded = b64encode(b"a" * 32)

    assert "=" not in encoded


def test_the_encoding_is_url_safe():
    encoded = b64encode(bytes(range(256)) * 1)

    assert "+" not in encoded
    assert "/" not in encoded


def test_the_encoding_is_ascii():
    assert b64encode(b"a" * 32).isascii()


def test_the_decoder_refuses_a_character_outside_the_alphabet():
    """A stray character is an error, not something to skip.

    Python's default decoder discards it, which would silently turn one key into
    another.
    """
    with pytest.raises(ValueError):
        b64decode("YWFh$YWFh")


def test_the_decoder_refuses_the_standard_base64_alphabet():
    with pytest.raises(ValueError):
        b64decode("ab+cd/ef")


def test_the_decoder_refuses_non_text():
    with pytest.raises(ValueError):
        b64decode(b"YWFh")
