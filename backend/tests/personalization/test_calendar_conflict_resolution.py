"""The imported-event conflict rules and the reconnect command (D3, D9).

Two things are pinned here, and they are the two places where a calendar import is *not*
indistinguishable from a user-created event:

- **"Delete the new one" is refused for an imported event** (D3). The imported event is
  the provider's: deleting the row would make the event vanish for an hour and then come
  back at the next poll, so the button would be a lie. The pair stays active and
  answerable with a choice that works.
- **Reconnect** replaces a revoked credential, brings the row back to `active` and
  requests a sync — and it **keeps the imported events**, because the provider revoked the
  *address*, not the events (D6, D9).
"""

from datetime import UTC, datetime, timedelta

import pytest

from apps.personalization.models import (
    CalendarConnection,
    ConflictPair,
    PersonalEvent,
    SavedEvent,
)
from apps.personalization.services.calendar_connections import (
    connect_calendar,
    reconnect_calendar,
)
from apps.personalization.services.calendar_sync import claim_due_connections, sync_calendar
from apps.personalization.services.conflict_resolutions import (
    IllegalResolutionError,
    ImportedEventNotDeletableError,
    resolve_conflict,
)
from domain.errors import InvalidCalendarCredentialError
from ports.calendar import CalendarEntry, CalendarResult
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.personalization.factories import (
    FAKE_CALENDAR_URL,
    CalendarConnectionFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
OTHER_URL = "https://example.com/other/calendar/basic.ics"


def _actor() -> Actor:
    return Actor.user(uuid7())


class StubPort:
    def __init__(self, *entries: CalendarEntry):
        self.entries = list(entries)

    def fetch_entries(self, feed):
        return CalendarResult(entries=list(self.entries))


def _entry(uid="a@feed", title="Team stand-up"):
    return CalendarEntry(
        uid=uid,
        title=title,
        starts_at=NOW + timedelta(hours=2),
        ends_at=NOW + timedelta(hours=3),
        tz="Europe/London",
    )


def _imported_event(connection) -> PersonalEvent:
    return PersonalEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        name="Overlapping meeting",
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
        start_time_tz="Europe/London",
        source=PersonalEvent.Source.CALENDAR_IMPORT,
        calendar_connection_id=connection.pk,
        source_uid="a@feed",
    )


def _pair(user_id, left_id, right_id) -> ConflictPair:
    return ConflictPair.objects.using(PERSONAL).create(
        user_id=user_id,
        kind=ConflictPair.Kind.TIME,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=left_id,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=right_id,
        status=ConflictPair.Status.ACTIVE,
        detected_at=NOW,
    )


# --- "delete the new one" and an imported event (D3) ------------------------------------------


def test_delete_new_is_refused_when_the_new_side_is_an_imported_event():
    connection = CalendarConnectionFactory()
    own = PersonalEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        name="My own thing",
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
        start_time_tz="Europe/London",
    )
    imported = _imported_event(connection)
    pair = _pair(connection.user_id, own.pk, imported.pk)

    with pytest.raises(ImportedEventNotDeletableError):
        resolve_conflict(
            user_id=connection.user_id,
            pair_id=pair.pk,
            resolution=ConflictPair.Resolution.DELETE_NEW,
            side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
            side_id=imported.pk,
            actor=_actor(),
            now=NOW,
        )


def test_the_refusal_leaves_the_pair_active_and_the_event_alone():
    connection = CalendarConnectionFactory()
    own = PersonalEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        name="My own thing",
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
        start_time_tz="Europe/London",
    )
    imported = _imported_event(connection)
    pair = _pair(connection.user_id, own.pk, imported.pk)

    with pytest.raises(ImportedEventNotDeletableError):
        resolve_conflict(
            user_id=connection.user_id,
            pair_id=pair.pk,
            resolution=ConflictPair.Resolution.DELETE_NEW,
            side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
            side_id=imported.pk,
            actor=_actor(),
            now=NOW,
        )

    pair.refresh_from_db()
    # The pair is still answerable — with "keep both" or "edit the new one".
    assert pair.status == ConflictPair.Status.ACTIVE
    assert pair.resolution is None
    assert PersonalEvent.objects.using(PERSONAL).filter(pk=imported.pk).exists()


def test_keep_both_is_offered_for_an_imported_event():
    connection = CalendarConnectionFactory()
    own = PersonalEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        name="My own thing",
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
        start_time_tz="Europe/London",
    )
    imported = _imported_event(connection)
    pair = _pair(connection.user_id, own.pk, imported.pk)

    resolution = resolve_conflict(
        user_id=connection.user_id,
        pair_id=pair.pk,
        resolution=ConflictPair.Resolution.KEEP_BOTH,
        side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        side_id=imported.pk,
        actor=_actor(),
        now=NOW,
    )

    assert resolution.resolution == ConflictPair.Resolution.KEEP_BOTH
    assert PersonalEvent.objects.using(PERSONAL).filter(pk=imported.pk).exists()


def test_edit_new_is_offered_for_an_imported_event():
    connection = CalendarConnectionFactory()
    own = PersonalEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        name="My own thing",
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
        start_time_tz="Europe/London",
    )
    imported = _imported_event(connection)
    pair = _pair(connection.user_id, own.pk, imported.pk)

    resolution = resolve_conflict(
        user_id=connection.user_id,
        pair_id=pair.pk,
        resolution=ConflictPair.Resolution.EDIT_NEW,
        side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        side_id=imported.pk,
        actor=_actor(),
        now=NOW,
    )

    assert resolution.resolution == ConflictPair.Resolution.EDIT_NEW
    assert resolution.action_side_id == imported.pk


def test_delete_new_still_works_for_a_user_created_event():
    connection = CalendarConnectionFactory()
    own = PersonalEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        name="My own thing",
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
        start_time_tz="Europe/London",
    )
    other = PersonalEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        name="Another thing",
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
        start_time_tz="Europe/London",
    )
    pair = _pair(connection.user_id, own.pk, other.pk)

    resolution = resolve_conflict(
        user_id=connection.user_id,
        pair_id=pair.pk,
        resolution=ConflictPair.Resolution.DELETE_NEW,
        side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        side_id=other.pk,
        actor=_actor(),
        now=NOW,
    )

    assert resolution.resolution == ConflictPair.Resolution.DELETE_NEW
    assert not PersonalEvent.objects.using(PERSONAL).filter(pk=other.pk).exists()


def test_a_saved_event_side_is_never_refused_as_an_import():
    # A saved event is the user's own save of a public event, so it is never imported and
    # is always the user's to remove. The imported-event refusal must not touch it: the
    # action legal against a saved side is `skip_public`, which releases the save, and it
    # is refused by the *side* rule rather than by the import rule.
    connection = CalendarConnectionFactory()
    saved = SavedEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        event_id=uuid7(),
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
        event_version=1,
    )
    own = PersonalEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        name="My own thing",
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
        start_time_tz="Europe/London",
    )
    pair = ConflictPair.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        kind=ConflictPair.Kind.TIME,
        left_kind=ConflictPair.SideKind.SAVED_EVENT,
        left_id=saved.pk,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=own.pk,
        status=ConflictPair.Status.ACTIVE,
        detected_at=NOW,
    )

    resolution = resolve_conflict(
        user_id=connection.user_id,
        pair_id=pair.pk,
        resolution=ConflictPair.Resolution.SKIP_PUBLIC,
        side_kind=ConflictPair.SideKind.SAVED_EVENT,
        side_id=saved.pk,
        actor=_actor(),
        now=NOW,
    )

    assert resolution.resolution == ConflictPair.Resolution.SKIP_PUBLIC


def test_delete_new_on_a_saved_event_side_is_refused_as_an_illegal_action():
    # A save cannot be deleted — it can be released. So `delete_new` is not legal against
    # a saved side, and the refusal is the *side* rule (an illegal resolution), not the
    # import rule and not the delete command's not-found error.
    connection = CalendarConnectionFactory()
    saved = SavedEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        event_id=uuid7(),
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
        event_version=1,
    )
    own = PersonalEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        name="My own thing",
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
        start_time_tz="Europe/London",
    )
    pair = ConflictPair.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        kind=ConflictPair.Kind.TIME,
        left_kind=ConflictPair.SideKind.SAVED_EVENT,
        left_id=saved.pk,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=own.pk,
        status=ConflictPair.Status.ACTIVE,
        detected_at=NOW,
    )

    with pytest.raises(IllegalResolutionError):
        resolve_conflict(
            user_id=connection.user_id,
            pair_id=pair.pk,
            resolution=ConflictPair.Resolution.DELETE_NEW,
            side_kind=ConflictPair.SideKind.SAVED_EVENT,
            side_id=saved.pk,
            actor=_actor(),
            now=NOW,
        )

    # The save is untouched, and the pair is still answerable.
    assert SavedEvent.objects.using(PERSONAL).filter(pk=saved.pk).exists()
    pair.refresh_from_db()
    assert pair.status == ConflictPair.Status.ACTIVE


def test_delete_new_for_a_side_that_is_gone_is_not_a_refusal():
    # The event is already gone, so there is nothing left to delete and nothing to
    # refuse: the caller's delete would be a no-op either way.
    connection = CalendarConnectionFactory()
    gone = uuid7()
    pair = ConflictPair.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        kind=ConflictPair.Kind.TIME,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=gone,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=uuid7(),
        status=ConflictPair.Status.ACTIVE,
        detected_at=NOW,
    )

    resolution = resolve_conflict(
        user_id=connection.user_id,
        pair_id=pair.pk,
        resolution=ConflictPair.Resolution.KEEP_BOTH,
        side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        side_id=gone,
        actor=_actor(),
        now=NOW,
    )

    assert resolution.resolution == ConflictPair.Resolution.KEEP_BOTH


# --- the reconnect command (D6, D9) ------------------------------------------------------------


def test_reconnect_replaces_the_credential_and_brings_the_row_back():
    connection = CalendarConnectionFactory(status=CalendarConnection.Status.NEEDS_RECONNECT)
    original_fingerprint = connection.credential_fingerprint

    reconnected = reconnect_calendar(
        connection=connection,
        url=OTHER_URL,
        actor=_actor(),
        now=NOW,
    )

    reconnected.refresh_from_db()
    assert reconnected.status == CalendarConnection.Status.ACTIVE
    assert reconnected.credential_fingerprint != original_fingerprint
    assert reconnected.last_error_kind is None


def test_reconnect_requests_a_sync():
    connection = CalendarConnectionFactory(status=CalendarConnection.Status.NEEDS_RECONNECT)

    reconnected = reconnect_calendar(
        connection=connection,
        url=OTHER_URL,
        actor=_actor(),
        now=NOW,
    )

    # D9: due immediately, so the dispatcher syncs it within a tick.
    assert reconnected.next_poll_at == NOW


def test_reconnect_keeps_the_imported_events():
    connection = CalendarConnectionFactory(status=CalendarConnection.Status.NEEDS_RECONNECT)
    imported = _imported_event(connection)

    reconnect_calendar(connection=connection, url=OTHER_URL, actor=_actor(), now=NOW)

    # The provider revoked the *address*, not the events (D6).
    assert PersonalEvent.objects.using(PERSONAL).filter(pk=imported.pk).exists()


def test_reconnect_clears_the_stale_cache_validators():
    connection = CalendarConnectionFactory(
        status=CalendarConnection.Status.NEEDS_RECONNECT,
        etag='W/"old"',
        last_modified="Mon, 01 Nov 2026 00:00:00 GMT",
    )

    reconnected = reconnect_calendar(
        connection=connection,
        url=OTHER_URL,
        actor=_actor(),
        now=NOW,
    )

    # The old validators belong to the old credential's feed. Keeping them would make the
    # provider answer 304 for a feed it has never seen this address's events in.
    assert reconnected.etag is None
    assert reconnected.last_modified is None


def test_reconnect_clears_a_claim_left_behind_by_a_dead_worker():
    """A stale claim must not hide the reconnected calendar from the dispatcher.

    The row becomes `active` and due immediately (D9). But a claim left behind by a
    worker that died mid-sync would keep the dispatcher from picking it up until the
    claim expired — so the user's first sync after reconnecting would wait up to
    `CALENDAR_CLAIM_TTL` for no reason.
    """
    connection = CalendarConnectionFactory(
        status=CalendarConnection.Status.NEEDS_RECONNECT,
        next_poll_at=None,
    )
    # The worker died holding the claim.
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        sync_claimed_at=NOW,
    )

    reconnect_calendar(connection=connection, url=OTHER_URL, actor=_actor(), now=NOW)

    # Read the row, not the instance.
    row = CalendarConnection.objects.using(PERSONAL).get(pk=connection.pk)
    assert row.sync_claimed_at is None


def test_a_reconnected_calendar_is_claimed_on_the_next_tick():
    """The whole point of clearing the claim: the calendar is synced within a tick."""
    connection = CalendarConnectionFactory(
        status=CalendarConnection.Status.NEEDS_RECONNECT,
        next_poll_at=None,
    )
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        sync_claimed_at=NOW,
    )

    reconnect_calendar(connection=connection, url=OTHER_URL, actor=_actor(), now=NOW)

    claimed = claim_due_connections(now=NOW + timedelta(seconds=61))
    assert claimed == [connection.pk]


def test_connecting_clears_a_claim_left_behind_by_a_dead_worker():
    # The same defect on the `connect_calendar` path, which reuses a waiting row.
    connection = CalendarConnectionFactory(
        status=CalendarConnection.Status.NEEDS_RECONNECT,
        next_poll_at=None,
    )
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        sync_claimed_at=NOW,
    )

    connect_calendar(
        user_id=connection.user_id,
        provider="google",
        url=OTHER_URL,
        actor=_actor(),
        now=NOW,
    )

    row = CalendarConnection.objects.using(PERSONAL).get(pk=connection.pk)
    assert row.sync_claimed_at is None


def test_reconnect_can_rename_the_calendar():
    connection = CalendarConnectionFactory(
        status=CalendarConnection.Status.NEEDS_RECONNECT,
        display_label="Work",
    )

    reconnected = reconnect_calendar(
        connection=connection,
        url=OTHER_URL,
        display_label="Personal",
        actor=_actor(),
        now=NOW,
    )

    assert reconnected.display_label == "Personal"


def test_reconnect_keeps_the_label_when_none_is_given():
    connection = CalendarConnectionFactory(
        status=CalendarConnection.Status.NEEDS_RECONNECT,
        display_label="Work",
    )

    reconnected = reconnect_calendar(
        connection=connection,
        url=OTHER_URL,
        actor=_actor(),
        now=NOW,
    )

    # A reconnect that says nothing about the name must not erase the name the user gave.
    assert reconnected.display_label == "Work"


def test_reconnect_writes_its_own_audit_row():
    from apps.personalization.models import PersonalizationAuditEntry

    connection = CalendarConnectionFactory(status=CalendarConnection.Status.NEEDS_RECONNECT)

    reconnect_calendar(connection=connection, url=OTHER_URL, actor=_actor(), now=NOW)

    [row] = (
        PersonalizationAuditEntry.objects.using(PERSONAL)
        .filter(action="calendar.reconnected")
        .all()
    )
    assert row.target_id == connection.pk
    assert OTHER_URL not in repr(row.details)


def test_reconnecting_an_active_connection_is_refused():
    connection = CalendarConnectionFactory(status=CalendarConnection.Status.ACTIVE)

    with pytest.raises(InvalidCalendarCredentialError):
        reconnect_calendar(connection=connection, url=OTHER_URL, actor=_actor(), now=NOW)


def test_reconnecting_a_disconnected_connection_is_refused():
    connection = CalendarConnectionFactory(
        status=CalendarConnection.Status.DISCONNECTED, credential=None
    )

    with pytest.raises(InvalidCalendarCredentialError):
        reconnect_calendar(connection=connection, url=OTHER_URL, actor=_actor(), now=NOW)


def test_connecting_a_needs_reconnect_connection_reuses_the_row():
    # The earlier item's behaviour, preserved: a reconnect through `connect_calendar`
    # reuses the waiting row rather than creating a second one.
    connection = CalendarConnectionFactory(status=CalendarConnection.Status.NEEDS_RECONNECT)

    result = connect_calendar(
        user_id=connection.user_id,
        provider="google",
        url=OTHER_URL,
        actor=_actor(),
        now=NOW,
    )

    assert result.pk == connection.pk
    assert result.status == CalendarConnection.Status.ACTIVE
    assert (
        CalendarConnection.objects.using(PERSONAL).filter(user_id=connection.user_id).count() == 1
    )


def test_connecting_requests_a_sync_without_fetching():
    connection = connect_calendar(
        user_id=uuid7(),
        provider="google",
        url=FAKE_CALENDAR_URL,
        actor=_actor(),
        now=NOW,
    )

    # D9: the due time is set and nothing is fetched — AD-11 forbids long work in a
    # request, and a fetch can take 30 seconds.
    assert connection.next_poll_at == NOW


def test_a_reconnected_connection_is_pollable_again():
    connection = CalendarConnectionFactory(
        status=CalendarConnection.Status.NEEDS_RECONNECT,
        next_poll_at=None,
    )
    reconnect_calendar(connection=connection, url=OTHER_URL, actor=_actor(), now=NOW)

    port = StubPort(_entry())
    outcome = sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    assert outcome.outcome == "synced"
    assert (
        PersonalEvent.objects.using(PERSONAL).filter(calendar_connection_id=connection.pk).exists()
    )
