"""The encrypted model field (AD-18).

`EncryptedTextField` is a `TextField` whose **stored** value is ciphertext. Every write
path encrypts; every read path decrypts. The Python attribute holds the plaintext, because
the service needs it, but the column never does.

Why a field rather than explicit encrypt/decrypt in the service layer: with a field,
encryption is enforced at *one* place. A service, an admin, a management command, a test
factory and a future script are all covered by construction. With explicit calls,
encryption is a convention that a new code path can forget — and the failure mode is a
plaintext credential in a database column.

Design: .specs-fire/intents/onboarding-and-account/work-items/
calendar-connection-model-design.md (decisions D4, D11).
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

from apps.personalization.credentials import (
    decrypt,
    encrypt,
    is_envelope,
)
from shared.credential_key import (
    KEY_ENV_VAR,
    InvalidCredentialKey,
    ParsedKey,
    parse_key,
)


def _current_key() -> ParsedKey:
    """The configured key, parsed.

    Read from `settings` per call rather than at import: the settings module validates the
    key once at startup (D5), and reading it lazily here is what lets a test override it
    with `override_settings`. The parse is cached by the raw string, so a repeated read is
    a dict lookup and a *different* raw string (a test's wrong key) is a different entry.

    A malformed key raises `ImproperlyConfigured`, not the raw `InvalidCredentialKey`: the
    field is reached from a model's `save()`, and an operator fault should surface as
    Django's own configuration error wherever it happens to be caught.
    """
    raw = getattr(settings, "CALENDAR_CREDENTIAL_KEY", "")
    if not raw:
        raise ImproperlyConfigured(
            f"{KEY_ENV_VAR} is not set. The calendar credential cannot be read or written "
            f"without it, and there is no fallback."
        )
    try:
        return parse_key(raw)
    except InvalidCredentialKey as exc:
        raise ImproperlyConfigured(str(exc)) from exc


class EncryptedTextField(models.TextField):
    """A text column whose stored value is ciphertext (AD-18).

    The column is nullable, and `NULL` is the *cleared* state: a disconnect destroys the
    credential by setting it to `NULL`, which is unambiguous in a way that an empty string
    is not.

    `value_to_string` yields the **ciphertext**, not the plaintext. Django's serializers go
    through it, so `dumpdata` — and any future export — produces ciphertext without
    having to remember to.
    """

    description = "Text encrypted at rest with the application-level credential key"

    def db_type(self, connection):
        return "text"

    def get_prep_value(self, value):
        """Encrypt on the way into the database.

        Every write path goes through here, including `QuerySet.update()`, so there is no
        way to write a plaintext credential into the column.

        A value that is **already an envelope** is stored as it is, not encrypted again.
        Without this, a value that has been round-tripped — a `loaddata` fixture, or a
        copy of an existing row — would be stored as ciphertext-of-ciphertext, and reading
        it back would decrypt once and hand the caller an `EPENC1.…` string where the
        provider's address should be: silently wrong, and only visible at fetch time.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        if value == "":
            # An empty credential is the cleared state, and the cleared state is NULL.
            return None
        if is_envelope(value):
            return value
        return encrypt(value, _current_key())

    def from_db_value(self, value, expression, connection):
        """Decrypt on the way out of the database."""
        if value is None:
            return None
        return decrypt(value, _current_key())

    def to_python(self, value):
        """Decrypt an envelope; pass a plaintext through.

        A value read from the database is always an envelope. A value assigned in Python is
        a plaintext. The prefix tells them apart.
        """
        if value is None:
            return None
        if is_envelope(value):
            return decrypt(value, _current_key())
        return value

    def value_to_string(self, obj):
        """Serialise the **ciphertext**.

        Django's serializers call this, so `dumpdata` and any export yield ciphertext. The
        plaintext is never part of a serialised representation.
        """
        value = self.value_from_object(obj)
        if value is None:
            return None
        if is_envelope(value):
            return value
        # The attribute holds a plaintext (assigned in Python, not yet saved). Serialise
        # its encrypted form rather than the plaintext.
        return encrypt(value, _current_key())
