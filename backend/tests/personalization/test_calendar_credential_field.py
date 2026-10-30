"""The `EncryptedTextField` itself (AD-18).

These are the unit tests for the field, away from the model that uses it. The model's
behaviour — the round trip, the constraints, the leaks — is pinned in
`test_calendar_connection_model.py`; this file covers the field's *own* branches, which
the model tests exercise only indirectly.

The branches that matter most are the ones that decide what ends up in the column:

- a value that is already an envelope is stored as it is;
- an empty string is the cleared state, and the cleared state is `NULL`;
- `value_to_string` serialises the **ciphertext**, never the plaintext;
- a missing or malformed key raises `ImproperlyConfigured`, not something a caller has to
  guess at.
"""

import base64

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.personalization.credentials import encrypt
from apps.personalization.fields import EncryptedTextField
from shared.credential_key import KEY_BYTES, parse_key

SECRET = "https://calendar.google.com/calendar/ical/SECRETSECRETSECRET/basic.ics"


@pytest.fixture
def field():
    """A field bound to a name.

    `set_attributes_from_name` is what gives the field its `attname` and `name`; a field
    that was never bound to a model cannot resolve an attribute off an instance, which is
    what `value_from_object` does.
    """
    bound = EncryptedTextField()
    bound.set_attributes_from_name("credential")
    return bound


@pytest.fixture
def key(settings):
    return parse_key(settings.CALENDAR_CREDENTIAL_KEY)


# ─── The write path ────────────────────────────────────────────────────────────


def test_the_write_path_encrypts(field):
    prepared = field.get_prep_value(SECRET)

    assert prepared.startswith("EPENC1.")
    assert SECRET not in prepared


def test_none_stays_none(field):
    assert field.get_prep_value(None) is None


def test_an_empty_string_becomes_null(field):
    """The cleared state is `NULL`, which is unambiguous in a way `''` is not."""
    assert field.get_prep_value("") is None


def test_a_non_string_is_coerced_to_text(field):
    """A non-string is stringified rather than crashing the write."""
    prepared = field.get_prep_value(12345)

    assert prepared.startswith("EPENC1.")
    assert "12345" not in prepared


def test_an_already_encrypted_value_is_stored_as_it_is(field, key):
    """An envelope is not encrypted again — that would be ciphertext-of-ciphertext."""
    envelope = encrypt(SECRET, key)

    assert field.get_prep_value(envelope) == envelope


def test_two_writes_of_the_same_value_differ(field):
    """A fresh nonce every time, so the column never reveals which rows share a value."""
    first = field.get_prep_value(SECRET)
    second = field.get_prep_value(SECRET)

    assert first != second


# ─── The read path ─────────────────────────────────────────────────────────────


def test_the_read_path_decrypts(field, key):
    envelope = encrypt(SECRET, key)

    assert field.from_db_value(envelope, None, None) == SECRET


def test_the_read_path_passes_null_through(field):
    assert field.from_db_value(None, None, None) is None


def test_to_python_decrypts_an_envelope(field, key):
    envelope = encrypt(SECRET, key)

    assert field.to_python(envelope) == SECRET


def test_to_python_passes_a_plaintext_through(field):
    """A value assigned in Python is a plaintext; `to_python` must not try to decrypt it."""
    assert field.to_python(SECRET) == SECRET


def test_to_python_passes_null_through(field):
    assert field.to_python(None) is None


def test_to_python_of_a_broken_envelope_raises(field):
    from domain.errors import CredentialDecryptionError

    with pytest.raises(CredentialDecryptionError):
        field.to_python("EPENC1.k1.broken")


# ─── The serialisation path ────────────────────────────────────────────────────


def test_value_to_string_yields_the_ciphertext(field):
    """The serialised form is ciphertext, so `dumpdata` never leaks the address."""

    class Holder:
        credential = SECRET

    serialised = field.value_to_string(Holder())

    assert serialised.startswith("EPENC1.")
    assert SECRET not in serialised


def test_value_to_string_of_null_is_null(field):
    class Holder:
        credential = None

    assert field.value_to_string(Holder()) is None


def test_value_to_string_of_an_envelope_is_that_envelope(field, key):
    """A value that was read back from the database is already an envelope.

    The model's attribute holds the *plaintext*, so this branch is reached when a
    caller assigns an envelope directly. It must be serialised as it is, not encrypted
    again.
    """
    envelope = encrypt(SECRET, key)

    class Holder:
        credential = envelope

    assert field.value_to_string(Holder()) == envelope


# ─── The key ───────────────────────────────────────────────────────────────────


def test_a_missing_key_is_an_improper_configuration(settings):
    """A missing key is an operator fault, and it surfaces as Django's own error."""
    settings.CALENDAR_CREDENTIAL_KEY = ""

    with pytest.raises(ImproperlyConfigured) as caught:
        EncryptedTextField().get_prep_value(SECRET)

    assert "CALENDAR_CREDENTIAL_KEY" in str(caught.value)


def test_a_malformed_key_is_an_improper_configuration(settings):
    settings.CALENDAR_CREDENTIAL_KEY = "not-a-key"

    with pytest.raises(ImproperlyConfigured):
        EncryptedTextField().get_prep_value(SECRET)


def test_a_malformed_key_never_echoes_the_key(settings):
    """The error names the variable, not its value: the value is a secret."""
    raw = "k1." + base64.urlsafe_b64encode(b"z" * KEY_BYTES).rstrip(b"=").decode("ascii")
    settings.CALENDAR_CREDENTIAL_KEY = raw[:20] + "!"

    with pytest.raises(ImproperlyConfigured) as caught:
        EncryptedTextField().get_prep_value(SECRET)

    assert raw[:20] not in str(caught.value)
