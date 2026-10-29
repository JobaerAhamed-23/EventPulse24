"""The calendar-connection commands (AD-18, FR-50): connect, disconnect, purge, reveal.

These are the **only** way a `CalendarConnection` changes (AD-16). The properties pinned
here are the ones the commands exist to provide:

- connect writes one row and one audit row, and the audit row carries no secret;
- the same calendar cannot be connected twice;
- the Free-tier cap refuses the second provider;
- a `needs_reconnect` connection still occupies a slot — a user cannot walk past the cap
  by waiting for a failure;
- reconnecting updates the row in place rather than creating a second one;
- disconnect clears the credential **and** writes an audit row, in one transaction;
- the purge removes exactly the events that connection imported;
- reveal returns a redacted `Credential`, and a cleared credential is refused.

Every assertion that could hide a secret checks for it explicitly.
"""

from datetime import UTC, datetime

import pytest
from django.db import connections, transaction

from apps.personalization.models import CalendarConnection, PersonalEvent
from apps.personalization.services.calendar_connections import (
    connect_calendar,
    disconnect_calendar,
    purge_connection_events,
    reveal_credential,
)
from domain.errors import (
    CalendarProviderCapReached,
    CredentialDecryptionError,
    InvalidCalendarCredentialError,
)
from ports.calendar import Credential
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.personalization.factories import (
    FAKE_CALENDAR_URL,
    CalendarConnectionFactory,
    PersonalEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

OTHER_URL = "https://example.com/other/calendar/basic.ics"


def _actor() -> Actor:
    return Actor.user(uuid7())


def _audit_rows(action: str):
    from apps.personalization.models import PersonalizationAuditEntry

    return PersonalizationAuditEntry.objects.using(PERSONAL).filter(action=action)


def _raw_credential(connection_id) -> str | None:
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "SELECT credential FROM personal.personalization_calendarconnection WHERE id = %s",
            [connection_id],
        )
        row = cursor.fetchone()
    return row[0] if row else None


# ─── connect ───────────────────────────────────────────────────────────────────


def test_connect_writes_one_row():
    user_id = uuid7()

    connection = connect_calendar(
        user_id=user_id,
        provider="google",
        url=FAKE_CALENDAR_URL,
        actor=_actor(),
    )

    assert CalendarConnection.objects.using(PERSONAL).count() == 1
    assert connection.pk is not None
    assert connection.user_id == user_id
    assert connection.provider == "google"
    assert connection.status == CalendarConnection.Status.ACTIVE


def test_connect_stores_the_address_encrypted():
    connection = connect_calendar(
        user_id=uuid7(),
        provider="google",
        url=FAKE_CALENDAR_URL,
        actor=_actor(),
    )

    raw = _raw_credential(connection.pk)

    assert raw.startswith("EPENC1.")
    assert FAKE_CALENDAR_URL not in raw
    assert "calendar.google.com" not in raw
    # …but it round-trips through the ORM.
    assert connection.credential == FAKE_CALENDAR_URL


def test_connect_writes_one_audit_row():
    actor = _actor()

    connection = connect_calendar(
        user_id=uuid7(),
        provider="google",
        url=FAKE_CALENDAR_URL,
        actor=actor,
    )

    rows = _audit_rows("calendar.connected")
    assert rows.count() == 1
    row = rows.get()
    assert row.target_type == "calendar_connection"
    assert row.target_id == connection.pk
    assert row.actor_kind == actor.kind
    assert row.actor_id == actor.id


def test_the_audit_row_carries_no_secret():
    """The audit row is read by operators and crosses the schema wall (AD-13)."""
    connect_calendar(
        user_id=uuid7(),
        provider="google",
        url=FAKE_CALENDAR_URL,
        actor=_actor(),
    )

    row = _audit_rows("calendar.connected").get()

    assert FAKE_CALENDAR_URL not in str(row.details)
    assert "calendar.google.com" not in str(row.details)
    assert "credential" not in row.details
    assert row.details["provider"] == "google"


def test_the_audit_row_records_when_it_happened():
    """The moment is stamped, so the audit trail reads as a sequence of events."""
    moment = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)

    connect_calendar(
        user_id=uuid7(),
        provider="google",
        url=FAKE_CALENDAR_URL,
        actor=_actor(),
        now=moment,
    )

    row = _audit_rows("calendar.connected").get()

    assert row.details["at"] == moment.isoformat()


def test_the_address_is_never_logged(caplog):
    import logging

    with caplog.at_level(logging.INFO):
        connect_calendar(
            user_id=uuid7(),
            provider="google",
            url=FAKE_CALENDAR_URL,
            actor=_actor(),
        )

    lines = "\n".join(record.getMessage() for record in caplog.records)
    assert FAKE_CALENDAR_URL not in lines
    assert "calendar.google.com" not in lines


def test_the_same_calendar_cannot_be_connected_twice():
    """The fingerprint's uniqueness, enforced at the command boundary."""
    user_id = uuid7()
    connect_calendar(
        user_id=user_id,
        provider="google",
        url=FAKE_CALENDAR_URL,
        actor=_actor(),
    )

    with pytest.raises(InvalidCalendarCredentialError):
        connect_calendar(
            user_id=user_id,
            provider="google",
            url=FAKE_CALENDAR_URL,
            actor=_actor(),
        )

    assert CalendarConnection.objects.using(PERSONAL).count() == 1


def test_the_same_calendar_address_with_different_case_is_the_same_calendar():
    """The fingerprint normalises the scheme and host, so this is the same calendar."""
    user_id = uuid7()
    connect_calendar(
        user_id=user_id,
        provider="google",
        url=FAKE_CALENDAR_URL,
        actor=_actor(),
    )

    upper = FAKE_CALENDAR_URL.replace("https://calendar", "HTTPS://Calendar")
    with pytest.raises(InvalidCalendarCredentialError):
        connect_calendar(
            user_id=user_id,
            provider="google",
            url=upper,
            actor=_actor(),
        )


def test_two_users_may_connect_the_same_calendar():
    connect_calendar(user_id=uuid7(), provider="google", url=FAKE_CALENDAR_URL, actor=_actor())
    connect_calendar(user_id=uuid7(), provider="google", url=FAKE_CALENDAR_URL, actor=_actor())

    assert CalendarConnection.objects.using(PERSONAL).count() == 2


def test_connecting_the_same_calendar_twice_is_not_a_cap_problem():
    """The more specific truth wins: "already connected", not "plan limit".

    The cap counts *distinct* calendars. Reporting a plan limit for a calendar the user
    already has would send them to the wrong screen.
    """
    user_id = uuid7()
    connect_calendar(user_id=user_id, provider="google", url=FAKE_CALENDAR_URL, actor=_actor())

    with pytest.raises(InvalidCalendarCredentialError):
        connect_calendar(user_id=user_id, provider="google", url=FAKE_CALENDAR_URL, actor=_actor())


def test_a_needs_reconnect_row_is_reused_not_duplicated():
    """The Free tier is one calendar, so a `needs_reconnect` row is the user's one slot.

    The next connect reuses it — with whatever address the user pastes — rather than
    creating a second row. The provider revoked the old secret, so the new address has a
    new fingerprint; matching the row by fingerprint would create a second row and take
    a second slot.
    """
    user_id = uuid7()
    first = connect_calendar(
        user_id=user_id, provider="google", url=FAKE_CALENDAR_URL, actor=_actor()
    )
    CalendarConnection.objects.using(PERSONAL).filter(pk=first.pk).update(
        status=CalendarConnection.Status.NEEDS_RECONNECT
    )

    reconnected = connect_calendar(
        user_id=user_id, provider="google", url=OTHER_URL, actor=_actor()
    )

    assert reconnected.pk == first.pk
    assert CalendarConnection.objects.using(PERSONAL).filter(user_id=user_id).count() == 1
    assert reconnected.credential == OTHER_URL


# ─── the address is validated ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not-a-url",
        "ftp://calendar.google.com/feed.ics",
        "file:///etc/passwd",
        "//calendar.google.com/feed.ics",
        "https://",
    ],
)
def test_a_bad_address_is_refused(url):
    with pytest.raises(InvalidCalendarCredentialError):
        connect_calendar(
            user_id=uuid7(),
            provider="google",
            url=url,
            actor=_actor(),
        )

    assert CalendarConnection.objects.using(PERSONAL).count() == 0


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@calendar.google.com/feed.ics",
        "https://user@calendar.google.com/feed.ics",
    ],
)
def test_an_address_with_credentials_in_it_is_refused(url):
    """`https://user:pass@host/...` carries a second secret."""
    with pytest.raises(InvalidCalendarCredentialError):
        connect_calendar(
            user_id=uuid7(),
            provider="google",
            url=url,
            actor=_actor(),
        )


def test_the_refusal_never_echoes_the_address():
    """The error can reach an HTTP response (AD-13).

    The address here is refused for its *shape* (credentials in the userinfo part), but
    the refusal still must not repeat it.
    """
    url = "https://user:SECRETSECRET@calendar.google.com/calendar/ical/basic.ics"

    with pytest.raises(InvalidCalendarCredentialError) as excinfo:
        connect_calendar(user_id=uuid7(), provider="google", url=url, actor=_actor())

    assert url not in str(excinfo.value)
    assert "SECRETSECRET" not in str(excinfo.value)
    assert url not in str(excinfo.value.details)
    assert "SECRETSECRET" not in str(excinfo.value.details)


@pytest.mark.parametrize(
    "url",
    [
        "http://calendar.example.com/feed.ics",
        "https://calendar.example.com/feed.ics",
        "webcal://calendar.example.com/feed.ics",
        "webcals://calendar.example.com/feed.ics",
    ],
)
def test_the_four_schemes_are_accepted(url):
    connection = connect_calendar(
        user_id=uuid7(),
        provider="google",
        url=url,
        actor=_actor(),
    )

    assert connection.pk is not None


def test_the_address_is_stored_as_the_user_typed_it():
    """The stored form is what the user recognises; the adapter normalises at fetch."""
    url = "  https://calendar.example.com/feed.ics  "

    connection = connect_calendar(
        user_id=uuid7(),
        provider="google",
        url=url,
        actor=_actor(),
    )

    assert connection.credential == "https://calendar.example.com/feed.ics"


# ─── the Free-tier cap ─────────────────────────────────────────────────────────


def test_a_malformed_key_is_refused_loudly(settings):
    """A key that was rotated wrongly under a running process is a fault, not a refusal.

    The settings load refuses a malformed key at startup (D5), so this branch only fires
    when the key was changed underneath a live process. It must still fail loudly: a
    silently-defaulted key would write credentials under the wrong key, and every one of
    them would be unreadable afterwards.
    """
    settings.CALENDAR_CREDENTIAL_KEY = "not-a-valid-key"

    with pytest.raises(CredentialDecryptionError):
        connect_calendar(
            user_id=uuid7(),
            provider="google",
            url=FAKE_CALENDAR_URL,
            actor=_actor(),
        )

    assert CalendarConnection.objects.using(PERSONAL).count() == 0


def test_the_cap_refuses_a_second_provider():
    """Free tier is one calendar provider."""
    user_id = uuid7()
    connect_calendar(user_id=user_id, provider="google", url=FAKE_CALENDAR_URL, actor=_actor())

    with pytest.raises(CalendarProviderCapReached):
        connect_calendar(user_id=user_id, provider="apple", url=OTHER_URL, actor=_actor())

    assert CalendarConnection.objects.using(PERSONAL).filter(user_id=user_id).count() == 1


def test_a_needs_reconnect_connection_still_occupies_a_slot():
    """The user has not given it up, so the slot is not free.

    The Free tier is one calendar. A `needs_reconnect` row **is** that slot, so the
    user's next connect is the reconnect of that row — it never becomes a *second*
    connection. If the slot were released, a user could connect past the cap by waiting
    for a failure and then adding another calendar alongside the broken one.
    """
    user_id = uuid7()
    connection = connect_calendar(
        user_id=user_id, provider="google", url=FAKE_CALENDAR_URL, actor=_actor()
    )
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        status=CalendarConnection.Status.NEEDS_RECONNECT
    )

    connect_calendar(user_id=user_id, provider="apple", url=OTHER_URL, actor=_actor())

    # One row, not two: the `needs_reconnect` row was reused, so the slot was never
    # released and the cap was never passed.
    assert CalendarConnection.objects.using(PERSONAL).filter(user_id=user_id).count() == 1


def test_a_disconnected_connection_frees_the_slot():
    """The user gave it up, so the slot is theirs again."""
    user_id = uuid7()
    connection = connect_calendar(
        user_id=user_id, provider="google", url=FAKE_CALENDAR_URL, actor=_actor()
    )
    disconnect_calendar(connection=connection, actor=_actor())

    second = connect_calendar(user_id=user_id, provider="apple", url=OTHER_URL, actor=_actor())

    assert second.pk is not None
    assert CalendarConnection.objects.using(PERSONAL).filter(user_id=user_id).count() == 2


def test_the_cap_is_per_user():
    connect_calendar(user_id=uuid7(), provider="google", url=FAKE_CALENDAR_URL, actor=_actor())
    other = connect_calendar(
        user_id=uuid7(), provider="google", url=FAKE_CALENDAR_URL, actor=_actor()
    )

    assert other.pk is not None


# ─── reconnect ────────────────────────────────────────────────────────────────


def test_reconnecting_updates_the_row_in_place():
    """A reconnect is not a second row for the same calendar."""
    user_id = uuid7()
    connection = connect_calendar(
        user_id=user_id, provider="google", url=FAKE_CALENDAR_URL, actor=_actor()
    )
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        status=CalendarConnection.Status.NEEDS_RECONNECT
    )

    reconnected = connect_calendar(
        user_id=user_id,
        provider="apple",
        url=OTHER_URL,
        display_label="Personal",
        actor=_actor(),
    )

    assert reconnected.pk == connection.pk
    assert CalendarConnection.objects.using(PERSONAL).count() == 1
    assert reconnected.provider == "apple"
    assert reconnected.status == CalendarConnection.Status.ACTIVE
    assert reconnected.credential == OTHER_URL
    assert reconnected.display_label == "Personal"


def test_reconnecting_writes_its_own_audit_row():
    user_id = uuid7()
    connection = connect_calendar(
        user_id=user_id, provider="google", url=FAKE_CALENDAR_URL, actor=_actor()
    )
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        status=CalendarConnection.Status.NEEDS_RECONNECT
    )

    connect_calendar(user_id=user_id, provider="apple", url=OTHER_URL, actor=_actor())

    assert _audit_rows("calendar.connected").count() == 1
    assert _audit_rows("calendar.reconnected").count() == 1


def test_reconnecting_clears_the_error_state():
    user_id = uuid7()
    connection = connect_calendar(
        user_id=user_id, provider="google", url=FAKE_CALENDAR_URL, actor=_actor()
    )
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        status=CalendarConnection.Status.NEEDS_RECONNECT,
        last_error_kind="revoked",
        last_error_at="2026-01-01T00:00:00Z",
    )

    reconnected = connect_calendar(user_id=user_id, provider="apple", url=OTHER_URL, actor=_actor())

    assert reconnected.last_error_kind is None
    assert reconnected.last_error_at is None


def test_reconnecting_does_not_bypass_the_cap():
    """A reconnect reuses the user's own slot; it does not add one."""
    user_id = uuid7()
    connection = connect_calendar(
        user_id=user_id, provider="google", url=FAKE_CALENDAR_URL, actor=_actor()
    )
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        status=CalendarConnection.Status.NEEDS_RECONNECT
    )

    reconnected = connect_calendar(
        user_id=user_id, provider="google", url=FAKE_CALENDAR_URL, actor=_actor()
    )

    assert reconnected.pk == connection.pk
    assert CalendarConnection.objects.using(PERSONAL).count() == 1


# ─── disconnect ────────────────────────────────────────────────────────────────


def test_disconnect_clears_the_credential():
    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)

    disconnect_calendar(connection=connection, actor=_actor())

    connection.refresh_from_db()
    assert connection.status == CalendarConnection.Status.DISCONNECTED
    assert connection.credential is None


def test_disconnect_destroys_the_ciphertext_in_the_column():
    """The row stays (the retention sweep removes it later), but the secret is gone."""
    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)

    disconnect_calendar(connection=connection, actor=_actor())

    assert _raw_credential(connection.pk) is None


def test_disconnect_writes_one_audit_row():
    connection = CalendarConnectionFactory()

    disconnect_calendar(connection=connection, actor=_actor())

    rows = _audit_rows("calendar.disconnected")
    assert rows.count() == 1
    row = rows.get()
    assert row.target_type == "calendar_connection"
    assert row.target_id == connection.pk
    assert row.details["provider"] == connection.provider


def test_disconnect_clears_the_error_and_schedule():
    connection = CalendarConnectionFactory()
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        last_error_kind="transient",
        last_error_at="2026-01-01T00:00:00Z",
        next_poll_at="2026-01-01T00:00:00Z",
    )

    disconnect_calendar(connection=connection, actor=_actor())

    connection.refresh_from_db()
    assert connection.last_error_kind is None
    assert connection.last_error_at is None
    assert connection.next_poll_at is None


def test_disconnect_leaves_the_row_for_the_sweep():
    """AD-15: the row is purged by the retention sweep, not deleted by the command."""
    connection = CalendarConnectionFactory()

    disconnect_calendar(connection=connection, actor=_actor())

    assert CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).exists()


def test_disconnect_commits_the_audit_row_with_the_mutation():
    """AD-5: "the user disconnected this" and "the credential is gone" commit together."""
    connection = CalendarConnectionFactory()

    with pytest.raises(RuntimeError):
        with transaction.atomic(using=PERSONAL):
            disconnect_calendar(connection=connection, actor=_actor())
            raise RuntimeError("boom")

    assert _audit_rows("calendar.disconnected").count() == 0
    connection.refresh_from_db()
    assert connection.credential is not None


# ─── purge ────────────────────────────────────────────────────────────────────


def test_the_purge_removes_exactly_that_connections_events():
    connection = CalendarConnectionFactory()
    other = CalendarConnectionFactory()

    mine = PersonalEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        name="Imported",
        start_utc="2026-11-06T03:30:00Z",
        end_utc="2026-11-06T05:30:00Z",
        start_time_tz="America/Los_Angeles",
        source=PersonalEvent.Source.CALENDAR_IMPORT,
        calendar_connection_id=connection.pk,
        source_uid="uid-1",
    )
    theirs = PersonalEvent.objects.using(PERSONAL).create(
        user_id=other.user_id,
        name="Theirs",
        start_utc="2026-11-06T03:30:00Z",
        end_utc="2026-11-06T05:30:00Z",
        start_time_tz="America/Los_Angeles",
        source=PersonalEvent.Source.CALENDAR_IMPORT,
        calendar_connection_id=other.pk,
        source_uid="uid-1",
    )
    user_created = PersonalEventFactory()

    deleted = purge_connection_events(connection=connection)

    assert deleted == 1
    assert not PersonalEvent.objects.using(PERSONAL).filter(pk=mine.pk).exists()
    assert PersonalEvent.objects.using(PERSONAL).filter(pk=theirs.pk).exists()
    assert PersonalEvent.objects.using(PERSONAL).filter(pk=user_created.pk).exists()


def test_the_purge_leaves_a_user_created_event_alone():
    """A user-created event has no connection, so no purge can reach it."""
    event = PersonalEventFactory()

    purge_connection_events(connection=CalendarConnectionFactory())

    assert PersonalEvent.objects.using(PERSONAL).filter(pk=event.pk).exists()


def test_the_purge_of_an_empty_connection_is_zero():
    assert purge_connection_events(connection=CalendarConnectionFactory()) == 0


# ─── reveal ───────────────────────────────────────────────────────────────────


def test_reveal_returns_a_credential():
    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)

    credential = reveal_credential(connection=connection)

    assert isinstance(credential, Credential)
    assert credential.reveal() == FAKE_CALENDAR_URL


def test_the_revealed_credential_cannot_be_printed():
    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)

    credential = reveal_credential(connection=connection)

    assert FAKE_CALENDAR_URL not in repr(credential)
    assert FAKE_CALENDAR_URL not in str(credential)
    assert "redacted" in repr(credential)


def test_revealing_a_cleared_credential_is_refused():
    """A cleared credential is a deliberate state, not a fault."""
    connection = CalendarConnectionFactory(credential=FAKE_CALENDAR_URL)
    disconnect_calendar(connection=connection, actor=_actor())
    connection.refresh_from_db()

    with pytest.raises(CredentialDecryptionError):
        reveal_credential(connection=connection)


def test_revealing_a_disconnected_connection_is_refused():
    connection = CalendarConnectionFactory()
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        status=CalendarConnection.Status.DISCONNECTED, credential=None
    )
    connection.refresh_from_db()

    with pytest.raises(CredentialDecryptionError):
        reveal_credential(connection=connection)
