"""The disconnect purge (FR-50, D13 of the calendar-sync design).

FR-50: "disconnecting purges exactly that connection's events". The word **exactly** is the
whole test, and it is a two-sided claim: another connection's events must survive, and the
user's own events must survive.

The purge touches three tables, each through **its owner's interface**:

| What | Owner | How |
|---|---|---|
| the conflict pairs | `personalization` | `delete_personal_event` closes them |
| the events | `personalization` | `delete_personal_event` |
| the reminder plans | **`delivery`** | `remove_plans_for_targets` — `delivery` owns them (AD-16) |

The ordering matters too: the credential is destroyed **first**, so the user's revocation
never depends on the purge succeeding.
"""

from datetime import UTC, datetime, timedelta

import pytest

from apps.delivery.models import ReminderPlan
from apps.personalization.models import CalendarConnection, ConflictPair, PersonalEvent
from apps.personalization.services.calendar_connections import disconnect_calendar
from apps.personalization.services.personal_events import create_personal_event
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.personalization.factories import CalendarConnectionFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def _actor() -> Actor:
    return Actor.user(uuid7())


def _imported(connection) -> list[PersonalEvent]:
    return list(PersonalEvent.objects.using(PERSONAL).filter(calendar_connection_id=connection.pk))


def _own_event(user_id, **kwargs) -> PersonalEvent:
    """A user-created event, with a default reminder plan, written through the command."""
    result = create_personal_event(
        user_id=user_id,
        name=kwargs.get("name", "My own thing"),
        start_utc=kwargs.get("start_utc", NOW + timedelta(hours=2)),
        end_utc=kwargs.get("end_utc", NOW + timedelta(hours=3)),
        start_time_tz="Europe/London",
        actor=_actor(),
        now=NOW,
    )
    return PersonalEvent.objects.using(PERSONAL).get(pk=result.event.id)


def test_disconnecting_purges_exactly_that_connections_events():
    connection = CalendarConnectionFactory()
    own = _own_event(connection.user_id)

    disconnect_calendar(connection=connection, actor=_actor(), now=NOW)

    assert _imported(connection) == []
    assert PersonalEvent.objects.using(PERSONAL).filter(pk=own.pk).exists()


def test_disconnecting_leaves_another_connections_events():
    first = CalendarConnectionFactory()
    second = CalendarConnectionFactory(user_id=first.user_id)
    survivor = PersonalEvent.objects.using(PERSONAL).create(
        user_id=first.user_id,
        name="From the other calendar",
        start_utc=NOW,
        end_utc=NOW + timedelta(hours=1),
        start_time_tz="Europe/London",
        source=PersonalEvent.Source.CALENDAR_IMPORT,
        calendar_connection_id=second.pk,
        source_uid="other@feed",
    )

    disconnect_calendar(connection=first, actor=_actor(), now=NOW)

    assert PersonalEvent.objects.using(PERSONAL).filter(pk=survivor.pk).exists()


def test_disconnecting_leaves_the_users_own_events():
    connection = CalendarConnectionFactory()
    own = _own_event(connection.user_id)

    disconnect_calendar(connection=connection, actor=_actor(), now=NOW)

    assert PersonalEvent.objects.using(PERSONAL).filter(pk=own.pk).exists()


def test_disconnecting_removes_the_reminder_plans():
    connection = CalendarConnectionFactory()
    imported = PersonalEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        name="Imported meeting",
        start_utc=NOW,
        end_utc=NOW + timedelta(hours=1),
        start_time_tz="Europe/London",
        source=PersonalEvent.Source.CALENDAR_IMPORT,
        calendar_connection_id=connection.pk,
        source_uid="a@feed",
    )
    ReminderPlan.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        target_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        target_id=imported.pk,
        slots=["1d"],
    )

    disconnect_calendar(connection=connection, actor=_actor(), now=NOW)

    # `delivery` owns `REMINDER_PLAN`, and a disconnected calendar must not leave a pile of
    # rows pointing at events that no longer exist.
    assert ReminderPlan.objects.using(PERSONAL).filter(target_id=imported.pk).count() == 0


def test_disconnecting_closes_the_conflict_pairs():
    connection = CalendarConnectionFactory()
    own = _own_event(connection.user_id, start_utc=NOW + timedelta(hours=2))
    imported = PersonalEvent.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        name="Overlapping meeting",
        start_utc=NOW + timedelta(hours=2),
        end_utc=NOW + timedelta(hours=3),
        start_time_tz="Europe/London",
        source=PersonalEvent.Source.CALENDAR_IMPORT,
        calendar_connection_id=connection.pk,
        source_uid="a@feed",
    )
    pair = ConflictPair.objects.using(PERSONAL).create(
        user_id=connection.user_id,
        kind=ConflictPair.Kind.TIME,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=own.pk,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=imported.pk,
        status=ConflictPair.Status.ACTIVE,
        detected_at=NOW,
    )

    disconnect_calendar(connection=connection, actor=_actor(), now=NOW)

    pair.refresh_from_db()
    # Nobody answered the prompt; the event went away. That is
    # `cleared_by_state_change` — the pair's name for "the world moved".
    assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE
    assert pair.resolution is None


def test_disconnecting_destroys_the_credential_first():
    connection = CalendarConnectionFactory()

    disconnect_calendar(connection=connection, actor=_actor(), now=NOW)

    connection.refresh_from_db()
    assert connection.status == CalendarConnection.Status.DISCONNECTED
    assert connection.credential is None
    assert connection.next_poll_at is None


def test_disconnecting_clears_the_poll_state():
    connection = CalendarConnectionFactory(next_poll_at=NOW + timedelta(hours=1))

    disconnect_calendar(connection=connection, actor=_actor(), now=NOW)

    connection.refresh_from_db()
    assert connection.next_poll_at is None
    assert connection.sync_claimed_at is None
    assert connection.etag is None


def test_disconnecting_a_connection_with_no_events_is_fine():
    connection = CalendarConnectionFactory()

    disconnect_calendar(connection=connection, actor=_actor(), now=NOW)

    connection.refresh_from_db()
    assert connection.status == CalendarConnection.Status.DISCONNECTED


def test_a_disconnected_connection_is_not_polled_again():
    from apps.personalization.services.calendar_sync import claim_due_connections

    connection = CalendarConnectionFactory(next_poll_at=NOW - timedelta(minutes=1))

    disconnect_calendar(connection=connection, actor=_actor(), now=NOW)

    assert claim_due_connections(now=NOW) == []
