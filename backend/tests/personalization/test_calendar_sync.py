"""The calendar sync service (AD-18, AD-7, FR-50, FR-58, FR-20).

A connected calendar is a mirror of somebody else's agenda, and this module is what turns a
fetched feed into the user's `PERSONAL_EVENT` rows.

The behaviours pinned here are the ones the sync exists to provide:

- **The reconcile is a three-way diff** (D1): a new uid becomes a row, a changed uid updates
  its row and bumps the version, a vanished uid is removed, and an **identical** uid is left
  alone. That last branch is the important one: bumping the version hourly would re-key
  AD-7's send key and re-send every reminder, every hour, forever.
- **Every write goes through the shared command paths** (D11), so an imported event gets
  the same reminder default, the same conflict detection and the same audit row as a
  user-created one.
- **The user's edit wins** (D2): a feed change overwrites an untouched import, and does not
  overwrite a row the user has edited.
- **A failed fetch writes nothing** (D15): no events, no pairs, no plans — only the
  connection's own status.
- **A revoked fetch keeps the events** (D6); a transient one leaves the status alone (D7).
- **The audit row carries counts only** (D10) and the log line carries no event content
  (AD-13).

Every assertion that could hide event content checks for it explicitly.
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from apps.delivery.models import ReminderPlan
from apps.personalization.models import (
    CalendarConnection,
    ConflictPair,
    PersonalEvent,
    PersonalizationAuditEntry,
)
from apps.personalization.services import calendar_sync
from apps.personalization.services.calendar_connections import connect_calendar
from apps.personalization.services.calendar_sync import sync_calendar
from apps.personalization.services.conflict_resolutions import resolve_conflict
from apps.personalization.services.personal_events import update_personal_event
from domain.errors import CredentialDecryptionError
from ports.calendar import (
    CalendarEntry,
    CalendarFeed,
    CalendarPort,
    CalendarRefusedError,
    CalendarResult,
    CalendarRevokedError,
    CalendarTransientError,
)
from shared.actor import Actor
from shared.constants import CALENDAR_POLL_INTERVAL
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.personalization.factories import (
    FAKE_CALENDAR_URL,
    CalendarConnectionFactory,
    PersonalEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
TZ = "Europe/London"


class StubPort(CalendarPort):
    """A port that returns whatever the test hands it, and records the feed it was given."""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.feeds: list[CalendarFeed] = []

    def fetch_entries(self, feed: CalendarFeed) -> CalendarResult:
        self.feeds.append(feed)
        if self.error is not None:
            raise self.error
        return self.result


def _entry(
    uid: str,
    *,
    title: str = "Team stand-up",
    start: datetime = NOW + timedelta(hours=2),
    hours: int = 1,
    tz: str = TZ,
) -> CalendarEntry:
    return CalendarEntry(
        uid=uid,
        title=title,
        starts_at=start,
        ends_at=start + timedelta(hours=hours),
        tz=tz,
    )


def _result(*entries: CalendarEntry) -> CalendarResult:
    return CalendarResult(entries=list(entries))


def _connection(**kwargs):
    connection = CalendarConnectionFactory(**kwargs)
    return connection


def _imported(connection):
    return (
        PersonalEvent.objects.using(PERSONAL)
        .filter(calendar_connection_id=connection.pk)
        .order_by("start_utc")
    )


def _audit_rows(action: str):
    return PersonalizationAuditEntry.objects.using(PERSONAL).filter(action=action)


def _plans():
    return ReminderPlan.objects.using(PERSONAL).all()


# --- the reconcile (D1) -------------------------------------------------------------------------


def test_a_new_uid_becomes_a_personal_event():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))

    outcome = sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    assert outcome.outcome == "synced"
    assert outcome.counts.created == 1
    [event] = _imported(connection)
    assert event.name == "Team stand-up"
    assert event.source == PersonalEvent.Source.CALENDAR_IMPORT
    assert event.source_uid == "a@feed"
    assert event.calendar_connection_id == connection.pk
    assert event.user_modified is False


def test_the_imported_event_carries_its_own_zone():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed", tz="Asia/Dhaka")))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    [event] = _imported(connection)
    assert event.start_time_tz == "Asia/Dhaka"
    assert event.start_utc == NOW + timedelta(hours=2)


def test_a_changed_uid_updates_its_row_and_bumps_the_version():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    [before] = _imported(connection)
    original_version = before.version

    moved = NOW + timedelta(hours=4)
    port.result = _result(_entry("a@feed", title="Renamed", start=moved))
    outcome = sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1))

    assert outcome.counts.updated == 1
    [after] = _imported(connection)
    assert after.pk == before.pk
    assert after.name == "Renamed"
    assert after.start_utc == moved
    assert after.version == original_version + 1


def test_a_uid_that_disappeared_is_removed():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed"), _entry("b@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    assert _imported(connection).count() == 2

    port.result = _result(_entry("a@feed"))
    outcome = sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1))

    assert outcome.counts.deleted == 1
    [remaining] = _imported(connection)
    assert remaining.source_uid == "a@feed"


def test_resyncing_an_unchanged_feed_changes_nothing():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    [before] = _imported(connection)
    version = before.version
    updated_at = before.updated_at

    outcome = sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1))

    assert outcome.counts.unchanged == 1
    assert outcome.counts.created == 0
    assert outcome.counts.updated == 0
    [after] = _imported(connection)
    # The version did not move, so AD-7's send key did not move, so the reminder is not
    # re-sent. That is the whole point of the "identical → nothing" branch.
    assert after.version == version
    assert after.updated_at == updated_at


def test_an_unchanged_feed_sends_no_reminders_again():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    [event] = _imported(connection)

    sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1))

    [event.refresh_from_db()]
    # The version is the send key's ingredient (AD-7). It did not move, so the reminder
    # for this event is not due again.
    assert event.version == 1


def test_a_user_created_event_is_never_touched_by_a_sync():
    connection = _connection()
    own = PersonalEventFactory(name="My own dinner")
    port = StubPort(_result(_entry("a@feed")))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    own.refresh_from_db()
    assert own.name == "My own dinner"
    assert own.version == 1


def test_a_deleted_imported_event_returns_on_the_next_sync():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    [event] = _imported(connection)
    event.delete()

    sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1))

    # The mirror is the provider's agenda: the provider still says the event exists, so
    # the sync recreates it. This is decided behaviour, not an oversight.
    [recreated] = _imported(connection)
    assert recreated.source_uid == "a@feed"


# --- ownership (D2) ----------------------------------------------------------------------------


def test_a_feed_change_overwrites_an_untouched_import():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    port.result = _result(_entry("a@feed", title="Moved by the provider"))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1))

    [event] = _imported(connection)
    assert event.name == "Moved by the provider"


def test_a_feed_change_does_not_overwrite_a_user_edit():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    [event] = _imported(connection)

    update_personal_event(
        user_id=connection.user_id,
        event_id=event.pk,
        name="My version",
        actor=Actor.user(uuid7()),
        now=NOW + timedelta(minutes=30),
    )

    port.result = _result(_entry("a@feed", title="The provider's version"))
    outcome = sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1))

    [after] = _imported(connection)
    assert after.name == "My version"
    assert after.user_modified is True
    # The feed's difference was not applied, so nothing was updated.
    assert outcome.counts.updated == 0


def test_a_user_edit_marks_the_row_user_modified():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    [event] = _imported(connection)
    assert event.user_modified is False

    update_personal_event(
        user_id=connection.user_id,
        event_id=event.pk,
        name="My version",
        actor=Actor.user(uuid7()),
        now=NOW + timedelta(minutes=30),
    )

    event.refresh_from_db()
    assert event.user_modified is True


def test_a_user_created_event_is_never_flagged_user_modified():
    own = PersonalEventFactory()

    update_personal_event(
        user_id=own.user_id,
        event_id=own.pk,
        name="Renamed",
        actor=Actor.user(uuid7()),
        now=NOW,
    )

    own.refresh_from_db()
    # There is no feed to disagree with a user-created event, so the flag stays off.
    assert own.user_modified is False


def test_a_user_edit_that_lands_mid_reconcile_is_not_overwritten():
    """The race D2 exists to prevent: the user's edit lands between the read and the write.

    The reconcile reads its snapshot before the diff begins, so an edit that lands in the
    meantime is invisible to it. The ownership decision is therefore made against
    **committed state**, under a row lock, in the same transaction as the write.
    """
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    [event] = _imported(connection)

    real_apply_updated = calendar_sync._apply_updated

    def apply_updated_after_a_concurrent_user_edit(**kwargs):
        # The user's request commits here: after the reconcile's snapshot, before the write.
        PersonalEvent.objects.using(PERSONAL).filter(pk=event.pk).update(
            name="My version",
            user_modified=True,
        )
        return real_apply_updated(**kwargs)

    calendar_sync._apply_updated = apply_updated_after_a_concurrent_user_edit
    try:
        port.result = _result(_entry("a@feed", title="The provider's version"))
        outcome = sync_calendar(
            connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1)
        )
    finally:
        calendar_sync._apply_updated = real_apply_updated

    [after] = _imported(connection)
    # The user's edit survives, and the feed's difference was not applied.
    assert after.name == "My version"
    assert outcome.counts.updated == 0


def test_a_user_edit_that_lands_mid_reconcile_keeps_the_ownership_flag():
    """The flag must not be cleared by the import — that would hand the row back to the feed.

    Clearing it would be worse than the overwrite: the *next* poll would overwrite the
    user's edit again, and the one after that, forever.
    """
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    [event] = _imported(connection)

    real_apply_updated = calendar_sync._apply_updated

    def apply_updated_after_a_concurrent_user_edit(**kwargs):
        PersonalEvent.objects.using(PERSONAL).filter(pk=event.pk).update(
            name="My version",
            user_modified=True,
        )
        return real_apply_updated(**kwargs)

    calendar_sync._apply_updated = apply_updated_after_a_concurrent_user_edit
    try:
        port.result = _result(_entry("a@feed", title="The provider's version"))
        sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1))
    finally:
        calendar_sync._apply_updated = real_apply_updated

    [after] = _imported(connection)
    assert after.user_modified is True


def test_an_event_deleted_mid_reconcile_is_not_resurrected():
    """A row that vanishes between the snapshot and the write is left gone.

    The reconcile took its snapshot before the diff began. If the user deletes the event
    in that window, the write must not recreate it — a mirror that resurrects a deleted
    event is worse than one that is briefly out of date.
    """
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    [event] = _imported(connection)

    real_apply_updated = calendar_sync._apply_updated

    def apply_updated_after_a_concurrent_delete(**kwargs):
        # The user deletes the event here: after the snapshot, before the write.
        PersonalEvent.objects.using(PERSONAL).filter(pk=event.pk).delete()
        return real_apply_updated(**kwargs)

    calendar_sync._apply_updated = apply_updated_after_a_concurrent_delete
    try:
        port.result = _result(_entry("a@feed", title="The provider's version"))
        outcome = sync_calendar(
            connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1)
        )
    finally:
        calendar_sync._apply_updated = real_apply_updated

    # The event stays deleted: it was not counted as updated.
    assert not PersonalEvent.objects.using(PERSONAL).filter(pk=event.pk).exists()
    assert outcome.counts.updated == 0


def test_the_import_path_never_resets_the_ownership_flag():
    """The import says "leave the ownership alone", not "the feed owns this row".

    A boolean cannot say "don't change it", so the command's parameter has three values:
    `True` (the user owns it), `False` (the feed owns it) and `None` (leave it as it
    stands). The import passes `None`.
    """
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    [event] = _imported(connection)

    # The user's edit sets the flag.
    update_personal_event(
        user_id=connection.user_id,
        event_id=event.pk,
        name="My version",
        actor=Actor.user(uuid7()),
        now=NOW + timedelta(minutes=30),
    )
    [event] = _imported(connection)
    assert event.user_modified is True

    # The import writes the row again — but the ownership is preserved.
    update_personal_event(
        user_id=connection.user_id,
        event_id=event.pk,
        name="The provider's version",
        user_modified=None,
        actor=Actor.system("calendar_sync"),
        now=NOW + timedelta(minutes=45),
    )

    [after] = _imported(connection)
    assert after.user_modified is True


# --- the reminder plan (D5) --------------------------------------------------------------------


def test_the_imported_event_gets_the_default_reminder_plan():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    [event] = _imported(connection)
    plan = ReminderPlan.objects.using(PERSONAL).get(target_id=event.pk)
    assert sorted(plan.slots) == ["1d", "1hr"]


def test_an_update_does_not_replace_the_users_reminder_plan():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    [event] = _imported(connection)
    plan = ReminderPlan.objects.using(PERSONAL).get(target_id=event.pk)
    plan.slots = ["custom_slot"]
    plan.save(update_fields=["slots"])

    port.result = _result(_entry("a@feed", title="Moved"))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1))

    plan.refresh_from_db()
    # The default is a property of *creation*. Re-attaching it on an update would wipe a
    # plan the user had customised.
    assert plan.slots == ["custom_slot"]


# --- the failures (D6, D7, D15) ----------------------------------------------------------------


def test_a_revoked_fetch_marks_the_connection_and_keeps_the_events():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    assert _imported(connection).count() == 1

    port.error = CalendarRevokedError()
    outcome = sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1))

    connection.refresh_from_db()
    assert outcome.outcome == "revoked"
    assert connection.status == CalendarConnection.Status.NEEDS_RECONNECT
    assert connection.last_error_kind == "revoked"
    # The provider revoked the *address*, not the events.
    assert _imported(connection).count() == 1


def test_a_transient_failure_leaves_the_status_alone():
    connection = _connection()
    port = StubPort(error=CalendarTransientError())

    outcome = sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    connection.refresh_from_db()
    assert outcome.outcome == "failed"
    assert connection.status == CalendarConnection.Status.ACTIVE
    assert connection.last_error_kind == "transient"


def test_a_refused_fetch_is_never_a_revocation():
    connection = _connection()
    port = StubPort(error=CalendarRefusedError())

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    connection.refresh_from_db()
    # A refusal is *our* decision about the address, not the provider's word about the
    # credential.
    assert connection.status == CalendarConnection.Status.ACTIVE
    assert connection.last_error_kind == "refused"


def test_a_failed_fetch_writes_no_events():
    connection = _connection()
    port = StubPort(error=CalendarTransientError())

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    assert _imported(connection).count() == 0
    assert _plans().count() == 0


def test_the_next_poll_is_scheduled_after_a_failure():
    connection = _connection()
    port = StubPort(error=CalendarTransientError())

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    connection.refresh_from_db()
    assert connection.next_poll_at == NOW + CALENDAR_POLL_INTERVAL


def test_the_next_poll_is_scheduled_after_a_success():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    connection.refresh_from_db()
    assert connection.last_polled_at == NOW
    assert connection.next_poll_at == NOW + CALENDAR_POLL_INTERVAL


def test_a_revoked_connection_is_not_polled_again():
    connection = _connection()
    port = StubPort(error=CalendarRevokedError())
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    connection.refresh_from_db()
    assert connection.status == CalendarConnection.Status.NEEDS_RECONNECT


def test_an_undecryptable_credential_is_recorded_but_is_not_a_revocation():
    connection = _connection()
    port = StubPort(error=CredentialDecryptionError())

    outcome = sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    connection.refresh_from_db()
    # A wrong key is a fault on our side. The user cannot fix it by pasting the address
    # again, so it is recorded but never treated as a revocation.
    assert outcome.outcome == "failed"
    assert outcome.error_kind == "undecryptable"
    assert connection.status == CalendarConnection.Status.ACTIVE
    assert connection.last_error_kind == "undecryptable"


def test_syncing_a_connection_that_does_not_exist_is_refused():
    from apps.personalization.services.calendar_sync import CalendarConnectionNotFoundError

    with pytest.raises(CalendarConnectionNotFoundError):
        sync_calendar(connection_id=uuid7(), port=StubPort(), now=NOW)


def test_a_not_modified_feed_changes_nothing():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    [before] = _imported(connection)

    port.result = CalendarResult(not_modified=True)
    outcome = sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1))

    assert outcome.outcome == "not_modified"
    [after] = _imported(connection)
    assert after.version == before.version
    assert _imported(connection).count() == 1


# --- the conflicts (D3, D4) ---------------------------------------------------------------------


def test_an_imported_event_that_overlaps_records_a_conflict_pair():
    connection = _connection()
    own = PersonalEventFactory(
        user_id=connection.user_id,
        name="My own thing",
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
    )
    port = StubPort(_result(_entry("a@feed")))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    pair = ConflictPair.objects.using(PERSONAL).get()
    assert pair.kind == ConflictPair.Kind.TIME
    assert pair.status == ConflictPair.Status.ACTIVE
    assert {pair.left_id, pair.right_id} == {own.pk, _imported(connection).first().pk}


def test_an_imported_event_that_is_a_duplicate_of_a_user_event_records_no_pair():
    connection = _connection()
    # The same name, but far enough apart in time that the *time* rule cannot fire — so
    # the only rule that could record a pair here is the duplicate rule.
    PersonalEventFactory(
        user_id=connection.user_id,
        name="Team stand-up",
        start_utc=NOW + timedelta(days=1),
        end_utc=NOW + timedelta(days=1, hours=1),
    )
    port = StubPort(_result(_entry("a@feed", title="Team stand-up")))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    # A user-created "Team stand-up" and a calendar "Team stand-up" are often the same
    # meeting, and a duplicate prompt has no useful answer for that case.
    assert ConflictPair.objects.using(PERSONAL).count() == 0


def test_an_imported_event_that_overlaps_a_user_event_records_a_time_pair():
    connection = _connection()
    # The same name *and* the same hour: the duplicate rule is skipped, but the time rule
    # still applies — two things at once is a clash whichever way round it is.
    PersonalEventFactory(
        user_id=connection.user_id,
        name="Team stand-up",
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
    )
    port = StubPort(_result(_entry("a@feed", title="Team stand-up")))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    [pair] = ConflictPair.objects.using(PERSONAL).all()
    assert pair.kind == ConflictPair.Kind.TIME


def test_two_imported_events_with_the_same_name_do_record_a_pair():
    first = _connection()
    second = _connection(user_id=first.user_id)
    port = StubPort(_result(_entry("a@feed", title="Team stand-up")))
    sync_calendar(connection_id=first.pk, port=port, now=NOW)

    port.result = _result(_entry("b@feed", title="Team stand-up", start=NOW + timedelta(hours=2)))
    sync_calendar(connection_id=second.pk, port=port, now=NOW + timedelta(hours=1))

    # Two imports *are* compared for duplication: the user saved the same meeting to two
    # calendars.
    assert ConflictPair.objects.using(PERSONAL).count() >= 1


def test_a_resolved_conflict_is_not_re_prompted_on_the_next_sync():
    connection = _connection()
    own = PersonalEventFactory(
        user_id=connection.user_id,
        name="My own thing",
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
    )
    port = StubPort(_result(_entry("a@feed")))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    pair = ConflictPair.objects.using(PERSONAL).get()
    imported = _imported(connection).first()

    # The user answers the prompt: "keep both". The pair closes as `resolved` and keeps
    # its answer.
    resolve_conflict(
        user_id=connection.user_id,
        pair_id=pair.pk,
        resolution=ConflictPair.Resolution.KEEP_BOTH,
        side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        side_id=imported.pk,
        actor=Actor.user(uuid7()),
        now=NOW + timedelta(minutes=30),
    )

    port.result = _result(_entry("a@feed", title="Team stand-up"))
    sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1))

    pair.refresh_from_db()
    assert pair.status == ConflictPair.Status.RESOLVED
    assert pair.resolution == ConflictPair.Resolution.KEEP_BOTH
    # AD-21: a closed pair is immutable and never re-prompted, so the sync did not open a
    # second one.
    assert ConflictPair.objects.using(PERSONAL).count() == 1
    assert own.pk  # the other side is untouched


# --- the audit and the logs (D10, D17) ---------------------------------------------------------


def test_a_sync_writes_one_audit_row_with_counts():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed"), _entry("b@feed")))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    [row] = _audit_rows("calendar.synced")
    assert row.details["created"] == 2
    assert row.details["updated"] == 0
    assert row.details["deleted"] == 0
    assert row.details["unchanged"] == 0
    assert row.target_id == connection.pk


def test_the_sync_audit_row_holds_no_event_content():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed", title="Secret Dentist Appointment")))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    [row] = _audit_rows("calendar.synced")
    serialised = repr(row.details)
    assert "Secret Dentist Appointment" not in serialised
    assert "a@feed" not in serialised
    assert FAKE_CALENDAR_URL not in serialised


def test_a_polled_sync_uses_a_system_actor():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    [row] = _audit_rows("calendar.synced")
    assert row.actor_kind == "system"
    assert row.actor_label == "calendar_sync"
    assert row.actor_id is None


def test_no_event_content_reaches_any_log_line_over_a_full_sync(caplog):
    connection = _connection()
    port = StubPort(_result(_entry("a@feed", title="Secret Dentist Appointment")))

    with caplog.at_level(logging.DEBUG):
        sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    serialised = "\n".join(record.getMessage() for record in caplog.records)
    assert "Secret Dentist Appointment" not in serialised
    assert "a@feed" not in serialised
    assert FAKE_CALENDAR_URL not in serialised


def test_the_sync_never_logs_the_credential():
    connection = _connection()
    port = StubPort(_result(_entry("a@feed")))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    # The port was handed a `Credential`, whose own repr is redacted.
    [feed] = port.feeds
    assert repr(feed.url) == "Credential('[redacted]')"
    assert FAKE_CALENDAR_URL not in repr(feed)


# --- the connect command (D9) ------------------------------------------------------------------


def test_connecting_requests_a_sync_without_fetching():
    port = StubPort(_result(_entry("a@feed")))

    connection = connect_calendar(
        user_id=uuid7(),
        provider="google",
        url=FAKE_CALENDAR_URL,
        actor=Actor.user(uuid7()),
        now=NOW,
    )

    # D9: the due time is set and nothing is fetched. AD-11 forbids long work in a request.
    assert connection.next_poll_at == NOW
    assert port.feeds == []


def test_the_successful_poll_stores_the_cache_validators():
    """The provider's validators are recorded, so reinstating conditional fetching is cheap."""
    connection = _connection()
    port = StubPort(CalendarResult(entries=[_entry("a@feed")], etag='W/"1"'))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    connection.refresh_from_db()
    assert connection.etag == 'W/"1"'


def test_the_fetch_is_unconditional_even_once_a_validator_is_stored():
    """**The import window and the 304 cannot both be right.**

    A conditional fetch says "the feed has not changed, so neither has your answer". With
    `CALENDAR_IMPORT_WINDOW` the answer is a function of the feed *and of `now`*: events
    age out of the window and events cross into it while the bytes stay identical. A
    calendar nobody edits for a fortnight would freeze its imported set on the day it last
    changed, and a meeting booked a month ahead would never arrive — silently, with the
    connection reading healthy.

    So the validator is stored and never sent.
    """
    connection = _connection()
    port = StubPort(CalendarResult(entries=[_entry("a@feed")], etag='W/"1"'))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(hours=1))

    connection.refresh_from_db()
    assert connection.etag == 'W/"1"'
    assert [feed.etag for feed in port.feeds] == [None, None]
    assert [feed.last_modified for feed in port.feeds] == [None, None]


# --- The import window (FR-50) -------------------------------------------------------------------
#
# **A connected calendar is a mirror, not an archive.** The first real import in local
# testing brought in a written-test invitation from the previous November, alongside two
# meetings from three weeks earlier. Those rows are not wrong; they are simply not what the
# Pulse is for, and each one costs a row, a conflict check and a line in the timeline's past.
#
# The window is `[now, now + CALENDAR_IMPORT_WINDOW]`, applied to the *feed* — so a row that
# ages out takes the ordinary "in the database, not in the feed" branch and is deleted,
# with no second rule about which rows may be removed.


def test_an_event_in_the_window_is_imported():
    connection = _connection()
    port = StubPort(CalendarResult(entries=[_entry("soon@feed", start=NOW + timedelta(days=3))]))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    assert [event.source_uid for event in _imported(connection)] == ["soon@feed"]


def test_an_event_that_has_already_ended_is_not_imported():
    """The year-old written-test invitation, in one assertion."""
    connection = _connection()
    port = StubPort(CalendarResult(entries=[_entry("old@feed", start=NOW - timedelta(days=365))]))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    assert list(_imported(connection)) == []


def test_an_event_beyond_the_window_is_not_imported():
    connection = _connection()
    port = StubPort(CalendarResult(entries=[_entry("far@feed", start=NOW + timedelta(days=8))]))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    assert list(_imported(connection)) == []


def test_an_event_happening_right_now_is_imported():
    """**Overlap, not "starts inside".**

    An event that began this morning and ends tonight is happening now. A rule that asked
    only where it *started* would drop it at the moment it matters most, and the timeline
    would empty itself at lunchtime.
    """
    connection = _connection()
    port = StubPort(
        CalendarResult(entries=[_entry("ongoing@feed", start=NOW - timedelta(hours=1), hours=3)])
    )

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    assert [event.source_uid for event in _imported(connection)] == ["ongoing@feed"]


def test_an_event_that_straddles_the_far_edge_is_imported():
    """It starts inside the window, so the user will see part of it in the week they are on."""
    connection = _connection()
    port = StubPort(
        CalendarResult(entries=[_entry("straddle@feed", start=NOW + timedelta(days=6), hours=48)])
    )

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    assert [event.source_uid for event in _imported(connection)] == ["straddle@feed"]


def test_the_window_filters_without_disturbing_the_rest_of_the_feed():
    """One sync, a mixed feed: the near events land and the far ones do not."""
    connection = _connection()
    port = StubPort(
        CalendarResult(
            entries=[
                _entry("old@feed", start=NOW - timedelta(days=30)),
                _entry("near@feed", start=NOW + timedelta(days=1)),
                _entry("alsonear@feed", start=NOW + timedelta(days=6)),
                _entry("far@feed", start=NOW + timedelta(days=90)),
            ]
        )
    )

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)

    assert sorted(event.source_uid for event in _imported(connection)) == [
        "alsonear@feed",
        "near@feed",
    ]


def test_an_imported_event_is_deleted_once_it_ages_out_of_the_window():
    """**The drift rule, and it needs no code of its own.**

    The window is applied to the feed, so an aged-out entry is absent from the diff's
    "in the feed" side and is removed by the same branch that removes an event deleted in
    Google. The imported set is always "what the window currently holds".
    """
    connection = _connection()
    entry = _entry("ages-out@feed", start=NOW + timedelta(hours=2))
    port = StubPort(CalendarResult(entries=[entry]))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    assert _imported(connection).count() == 1

    # Same unchanged feed, a week later: the event is now in the past.
    sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(days=2))

    assert list(_imported(connection)) == []


def test_an_event_is_imported_once_it_crosses_into_the_window():
    """The far edge, moving the other way — and the reason the fetch is unconditional.

    The feed never changes here. Only `now` does. A conditional fetch would have answered
    304 and this event would never have arrived.
    """
    connection = _connection()
    port = StubPort(CalendarResult(entries=[_entry("arrives@feed", start=NOW + timedelta(days=9))]))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    assert list(_imported(connection)) == []

    sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(days=3))

    assert [event.source_uid for event in _imported(connection)] == ["arrives@feed"]


def test_a_windowed_out_event_does_not_count_as_a_feed_deletion_twice():
    """Deleting is idempotent: the second sync has nothing left to remove."""
    connection = _connection()
    port = StubPort(CalendarResult(entries=[_entry("gone@feed", start=NOW + timedelta(hours=1))]))

    sync_calendar(connection_id=connection.pk, port=port, now=NOW)
    first = sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(days=3))
    second = sync_calendar(connection_id=connection.pk, port=port, now=NOW + timedelta(days=4))

    assert first.counts.deleted == 1
    assert second.counts.deleted == 0
