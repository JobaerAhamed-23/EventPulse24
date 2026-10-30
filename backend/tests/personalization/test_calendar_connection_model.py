"""The `CalendarConnection` model and the encrypted credential (AD-18, FR-50).

The properties pinned here are the ones the work item names:

- the raw column holds **ciphertext**, not the address;
- the credential round-trips, and a wrong key fails loudly;
- the address never reaches a `repr`, the admin, a log line, or a serialised form;
- the source/connection constraint holds both ways;
- `(connection, uid)` is unique, so a re-sync upserts rather than duplicates;
- no relation crosses the AD-3 wall.

The "raw column" assertions use SQL, not the ORM: the ORM decrypts on the way out, so
reading through it proves nothing about what is *stored*.
"""

import base64
import logging

import pytest
from django.core import serializers
from django.db import IntegrityError, connections, transaction

from apps.personalization.models import CalendarConnection, PersonalEvent
from domain.errors import CredentialDecryptionError
from shared.credential_key import KEY_BYTES
from shared.db import PERSONAL
from shared.retention import RetentionCategory
from tests.personalization.factories import (
    FAKE_CALENDAR_URL,
    CalendarConnectionFactory,
    PersonalEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

#: The address's recognisable fragments. None of them may appear in the stored column.
HOST = "calendar.google.com"
PATH_SEGMENT = "ZmFrZXNlY3JldHNlY3JldHNlY3JldHNlY3JldA"


def _other_key() -> str:
    """A second valid key, for the wrong-key test."""
    return "k9." + base64.urlsafe_b64encode(b"z" * KEY_BYTES).rstrip(b"=").decode("ascii")


def _raw_credential(connection_id) -> str:
    """The credential exactly as it is stored, read with SQL."""
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "SELECT credential FROM personal.personalization_calendarconnection WHERE id = %s",
            [connection_id],
        )
        row = cursor.fetchone()
    return row[0] if row else None


# ─── The stored column is ciphertext ───────────────────────────────────────────


def test_the_raw_column_is_ciphertext():
    """The stored value holds neither the address nor any recognisable fragment of it.

    Read with SQL, because the ORM decrypts on the way out and would prove nothing.
    """
    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)

    raw = _raw_credential(connection.pk)

    assert raw is not None
    assert FAKE_CALENDAR_URL not in raw
    assert HOST not in raw
    assert PATH_SEGMENT not in raw
    assert "calendar" not in raw


def test_the_raw_column_looks_like_an_envelope():
    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)

    raw = _raw_credential(connection.pk)

    assert raw.startswith("EPENC1.")
    assert len(raw.split(".")) == 4


def test_the_credential_round_trips():
    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)

    reloaded = CalendarConnection.objects.using(PERSONAL).get(pk=connection.pk)

    assert reloaded.credential == FAKE_CALENDAR_URL


def test_a_wrong_key_fails_loudly(settings):
    """A wrong key raises. It never yields None or an empty string.

    A silent empty string would look like "this connection has no credential", and the
    poll would then report a revoked address for what is really a key fault.
    """
    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)
    settings.CALENDAR_CREDENTIAL_KEY = _other_key()

    with pytest.raises(CredentialDecryptionError):
        CalendarConnection.objects.using(PERSONAL).get(pk=connection.pk)


def test_the_key_is_not_the_secret_key(settings):
    """The credential key is separate from `SECRET_KEY` (AD-18).

    One leaked session key must not decrypt every stored calendar credential.
    """
    from django.conf import settings as django_settings

    assert django_settings.CALENDAR_CREDENTIAL_KEY != django_settings.SECRET_KEY


def test_a_write_through_update_is_also_encrypted():
    """`update()` bypasses `save()`, so the field's `get_prep_value` is the only guard.

    A custom field is what makes this safe: there is no second code path that could
    forget to encrypt.
    """
    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)

    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        credential="https://example.com/other-secret-path/basic.ics"
    )

    raw = _raw_credential(connection.pk)
    assert "example.com" not in raw
    assert raw.startswith("EPENC1.")


def test_an_already_encrypted_value_is_not_encrypted_again():
    """A value that has been round-tripped is stored as it is.

    Without this, a `loaddata` fixture — or a copy of an existing row — would be stored
    as ciphertext-of-ciphertext. Reading it back would decrypt once and hand the caller
    an `EPENC1.…` string where the provider's address should be: silently wrong, and only
    visible at fetch time.
    """
    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)
    raw = _raw_credential(connection.pk)

    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(credential=raw)

    assert _raw_credential(connection.pk) == raw
    assert connection.credential == FAKE_CALENDAR_URL


def test_a_dumped_connection_reloads_as_the_same_credential(settings):
    """The dump/load round trip is exact: one encryption, not two.

    The serialised payload is a *fresh* encryption of the plaintext attribute — a fresh
    nonce every time, so it is not byte-identical to the stored ciphertext. What must
    hold is that it is one layer of encryption and not two: it decrypts to the address,
    not to an `EPENC1.…` string.
    """
    import json

    from apps.personalization.credentials import decrypt
    from shared.credential_key import parse_key

    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)
    dumped = serializers.serialize("json", [connection])

    # What `loaddata` would write: the serialised ciphertext.
    payload = json.loads(dumped)[0]["fields"]["credential"]
    assert payload.startswith("EPENC1.")
    assert FAKE_CALENDAR_URL not in payload

    # Exactly one layer of encryption: the payload decrypts to the address.
    key = parse_key(settings.CALENDAR_CREDENTIAL_KEY)
    assert decrypt(payload, key) == FAKE_CALENDAR_URL

    # And loading it back does not decrypt twice.
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(credential=payload)
    reloaded = CalendarConnection.objects.using(PERSONAL).get(pk=connection.pk)
    assert reloaded.credential == FAKE_CALENDAR_URL


# ─── Nothing leaks ─────────────────────────────────────────────────────────────


def test_the_model_repr_holds_no_credential():
    """`Model.__repr__` uses `__str__`, so `__str__` is what the admin shows too."""
    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)

    assert FAKE_CALENDAR_URL not in repr(connection)
    assert HOST not in repr(connection)
    assert FAKE_CALENDAR_URL not in str(connection)
    assert HOST not in str(connection)


def test_the_model_str_names_only_the_provider():
    connection = CalendarConnectionFactory(
        credential=FAKE_CALENDAR_URL, provider=CalendarConnection.Provider.GOOGLE
    )

    assert str(connection) == "google calendar"


def test_the_credential_appears_in_no_log_line(caplog):
    """The assertion is on the **serialised** output, so a formatter that redacted the
    wrong field would fail."""
    with caplog.at_level(logging.INFO):
        connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)
        CalendarConnection.objects.using(PERSONAL).get(pk=connection.pk)

    lines = "\n".join(record.getMessage() for record in caplog.records)
    assert FAKE_CALENDAR_URL not in lines
    assert HOST not in lines


def test_the_fingerprint_is_not_allowlisted():
    """The fingerprint is a stable identifier of a secret, so it must never be an
    allowlisted log field."""
    from adapters.logging.redaction import ALLOWED_FIELDS

    assert "credential" not in ALLOWED_FIELDS
    assert "credential_fingerprint" not in ALLOWED_FIELDS


def test_dumped_data_holds_no_credential():
    """Django's serializers go through `value_to_string`, which yields the ciphertext."""
    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)

    dumped = serializers.serialize("json", [connection])

    assert FAKE_CALENDAR_URL not in dumped
    assert HOST not in dumped
    assert "EPENC1." in dumped


def test_the_admin_excludes_the_credential():
    """The credential is excluded, not made readonly.

    A readonly field is still rendered into the page, which would put the ciphertext in
    the operator's browser. Excluded means it never leaves the server.
    """
    from django.contrib import admin

    model_admin = admin.site._registry[CalendarConnection]

    assert "credential" not in model_admin.list_display
    assert "credential_fingerprint" not in model_admin.list_display

    fieldsets = model_admin.fieldsets or ()
    rendered = {field for _, options in fieldsets for field in options.get("fields", ())}
    assert "credential" not in rendered
    assert "credential_fingerprint" not in rendered

    assert "credential" not in (model_admin.readonly_fields or ())
    assert not model_admin.has_add_permission(None)
    assert not model_admin.has_change_permission(None)
    assert not model_admin.has_delete_permission(None)


# ─── The model ─────────────────────────────────────────────────────────────────


def test_the_connection_lives_in_the_personal_schema():
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            """
            SELECT table_schema FROM information_schema.tables
            WHERE table_name = 'personalization_calendarconnection'
            """
        )
        row = cursor.fetchone()

    assert row is not None
    assert row[0] == "personal"


def test_the_connection_has_no_relation_fields():
    """No foreign key at all: the user is held by value, and the connection crosses no
    schema (AD-3, OQ-8)."""
    relations = [f for f in CalendarConnection._meta.get_fields() if f.is_relation]

    assert relations == []


def test_the_user_is_held_by_value():
    connection = CalendarConnectionFactory()

    assert isinstance(connection.user_id, type(connection.id))
    assert CalendarConnection._meta.get_field("user_id").remote_field is None


def test_the_retention_category_is_account_identity():
    """AD-15: "Personal email addresses and calendar credentials: while active; encrypted
    at rest; purged on disconnect or account deletion"."""
    assert CalendarConnection.retention_category is RetentionCategory.ACCOUNT_IDENTITY


def test_the_provider_choices_are_the_three_supported():
    values = {value for value, _ in CalendarConnection.Provider.choices}

    assert values == {"google", "apple", "outlook"}


def test_the_status_choices_are_the_three_states():
    values = {value for value, _ in CalendarConnection.Status.choices}

    assert values == {"active", "needs_reconnect", "disconnected"}


# ─── The constraints ───────────────────────────────────────────────────────────


def test_an_active_connection_must_have_a_credential():
    """D7's state machine, held by the database."""
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        CalendarConnection.objects.using(PERSONAL).create(
            user_id=CalendarConnectionFactory().user_id,
            provider=CalendarConnection.Provider.GOOGLE,
            credential=None,
            credential_fingerprint="a" * 64,
            status=CalendarConnection.Status.ACTIVE,
        )


def test_a_disconnected_connection_must_not_have_a_credential():
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        CalendarConnection.objects.using(PERSONAL).create(
            user_id=CalendarConnectionFactory().user_id,
            provider=CalendarConnection.Provider.GOOGLE,
            credential=FAKE_CALENDAR_URL,
            credential_fingerprint="b" * 64,
            status=CalendarConnection.Status.DISCONNECTED,
        )


def test_the_same_calendar_cannot_be_connected_twice():
    """The fingerprint's uniqueness: one calendar per user."""
    connection = CalendarConnectionFactory(credential_fingerprint="c" * 64)

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        CalendarConnection.objects.using(PERSONAL).create(
            user_id=connection.user_id,
            provider=CalendarConnection.Provider.APPLE,
            credential=FAKE_CALENDAR_URL,
            credential_fingerprint="c" * 64,
            status=CalendarConnection.Status.ACTIVE,
        )


def test_two_users_may_connect_the_same_calendar():
    """The constraint is per user: the fingerprint is not globally unique."""
    CalendarConnectionFactory(credential_fingerprint="d" * 64)
    CalendarConnectionFactory(credential_fingerprint="d" * 64)

    assert CalendarConnection.objects.using(PERSONAL).count() == 2


# ─── PersonalEvent: the source/connection rule ────────────────────────────────


def test_an_imported_event_needs_a_connection():
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        PersonalEvent.objects.using(PERSONAL).create(
            user_id=CalendarConnectionFactory().user_id,
            name="Imported",
            start_utc=PersonalEventFactory().start_utc,
            end_utc=PersonalEventFactory().end_utc,
            start_time_tz="America/Los_Angeles",
            source=PersonalEvent.Source.CALENDAR_IMPORT,
            calendar_connection_id=None,
        )


def test_a_user_created_event_needs_no_connection():
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        PersonalEvent.objects.using(PERSONAL).create(
            user_id=CalendarConnectionFactory().user_id,
            name="Mine",
            start_utc=PersonalEventFactory().start_utc,
            end_utc=PersonalEventFactory().end_utc,
            start_time_tz="America/Los_Angeles",
            source=PersonalEvent.Source.USER_CREATED,
            calendar_connection_id=CalendarConnectionFactory().pk,
        )


def test_an_imported_event_with_a_connection_is_accepted():
    connection = CalendarConnectionFactory()

    event = PersonalEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        name="Imported",
        start_utc=PersonalEventFactory().start_utc,
        end_utc=PersonalEventFactory().end_utc,
        start_time_tz="America/Los_Angeles",
        source=PersonalEvent.Source.CALENDAR_IMPORT,
        calendar_connection_id=connection.pk,
        source_uid="uid-1",
    )

    assert event.pk is not None


def test_the_same_uid_cannot_be_imported_twice():
    """A re-sync upserts on (connection, uid) instead of duplicating."""
    connection = CalendarConnectionFactory()
    common = {
        "user_id": connection.user_id,
        "name": "Imported",
        "start_utc": PersonalEventFactory().start_utc,
        "end_utc": PersonalEventFactory().end_utc,
        "start_time_tz": "America/Los_Angeles",
        "source": PersonalEvent.Source.CALENDAR_IMPORT,
        "calendar_connection_id": connection.pk,
        "source_uid": "uid-1",
    }
    PersonalEvent.objects.using(PERSONAL).create(**common)

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        PersonalEvent.objects.using(PERSONAL).create(**common)


def test_many_user_created_events_may_have_no_uid():
    """Postgres treats NULLs as distinct in a unique constraint."""
    for _ in range(3):
        PersonalEventFactory()

    assert PersonalEvent.objects.using(PERSONAL).count() == 3


def test_the_calendar_import_source_fits_the_column():
    """`source`'s column is 16 characters wide and the new value is 15."""
    assert len(PersonalEvent.Source.CALENDAR_IMPORT) <= 16
