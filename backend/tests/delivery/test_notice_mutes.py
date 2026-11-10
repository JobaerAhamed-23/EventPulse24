"""The per-event notice mute (FR-55): what it silences, and what it deliberately does not.

`EVENT_NOTICE_MUTE` is `delivery`-owned (AD-16) and lives in its own table rather than on
`REMINDER_PLAN`, where FR-11's per-event *reminder* opt-out lives. That precedent looks like
it should transfer and does not — a saved public event usually has no plan at all, and an
unsave now deletes the plan, so a mute stored there would vanish with the save. The test
`test_a_mute_survives_an_unsave_and_a_re_save` is that reasoning made executable.

The interaction tests — a muted event raising no notice, and a terminal change reaching one
anyway — live in `test_state_notices.py`, beside the rule they belong to.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.delivery.models import DeliveryAuditEntry, EventNoticeMute, ScheduledSend
from apps.delivery.services.mutes import (
    is_muted,
    mute_event_notices,
    muted_event_ids,
    unmute_event_notices,
)
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 1, 20, 0, tzinfo=UTC)
USER = uuid7()
EVENT = uuid7()


def actor(user_id=USER):
    return Actor.user(user_id)


# --- Muting and unmuting -------------------------------------------------------------------------


def test_muting_records_the_mute():
    result = mute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    assert result.muted is True
    assert result.changed is True
    assert is_muted(user_id=USER, event_id=EVENT)


def test_unmuting_removes_it():
    mute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    result = unmute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    assert result.muted is False
    assert result.changed is True
    assert not is_muted(user_id=USER, event_id=EVENT)


def test_unmuting_something_never_muted_reports_no_change():
    """A success, not an error — but it must not claim to have changed anything."""
    result = unmute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    assert result.changed is False


def test_a_mute_is_scoped_to_one_user_and_one_event():
    other_user, other_event = uuid7(), uuid7()
    mute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    assert not is_muted(user_id=other_user, event_id=EVENT)
    assert not is_muted(user_id=USER, event_id=other_event)


def test_muting_an_event_the_catalog_does_not_hold_is_allowed():
    """No existence check, on purpose.

    The id names a row in `catalog`, which this module may not read in a write transaction
    (AD-3) — and requiring the event to exist would make the mute fail in exactly the case
    a user most wants it, an event mid-supersede.
    """
    result = mute_event_notices(user_id=USER, event_id=uuid4(), actor=actor(), now=NOW)

    assert result.changed is True


# --- The audit trail -----------------------------------------------------------------------------


def test_muting_writes_an_audit_row():
    mute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    entry = DeliveryAuditEntry.objects.using(PERSONAL).get(
        target_id=EVENT, action="event_notice_mute.muted"
    )
    assert entry.actor_id == USER


def test_unmuting_writes_an_audit_row():
    mute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    unmute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    assert (
        DeliveryAuditEntry.objects.using(PERSONAL)
        .filter(target_id=EVENT, action="event_notice_mute.unmuted")
        .exists()
    )


def test_a_no_op_mute_writes_no_audit_row():
    """AD-5 is one row per mutation. A second mute mutates nothing."""
    mute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    mute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    assert (
        DeliveryAuditEntry.objects.using(PERSONAL)
        .filter(target_id=EVENT, action="event_notice_mute.muted")
        .count()
        == 1
    )


def test_a_no_op_unmute_writes_no_audit_row():
    unmute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    assert (
        not DeliveryAuditEntry.objects.using(PERSONAL)
        .filter(action="event_notice_mute.unmuted")
        .exists()
    )


# --- The batched read ----------------------------------------------------------------------------


def test_muted_event_ids_answers_for_many_events_in_one_query():
    """A list rendering a mute control per row must not cost a query per row."""
    from django.db import connections
    from django.test.utils import CaptureQueriesContext

    muted_one, muted_two, loud = uuid7(), uuid7(), uuid7()
    mute_event_notices(user_id=USER, event_id=muted_one, actor=actor(), now=NOW)
    mute_event_notices(user_id=USER, event_id=muted_two, actor=actor(), now=NOW)

    with CaptureQueriesContext(connections[PERSONAL]) as captured:
        found = muted_event_ids(user_id=USER, event_ids={muted_one, muted_two, loud})

    assert found == {muted_one, muted_two}
    assert len(captured) == 1


def test_muted_event_ids_with_no_ids_asks_nothing():
    from django.db import connections
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connections[PERSONAL]) as captured:
        assert muted_event_ids(user_id=USER, event_ids=set()) == set()

    assert len(captured) == 0


def test_muted_event_ids_is_scoped_to_the_user():
    mute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    assert muted_event_ids(user_id=uuid7(), event_ids={EVENT}) == set()


# --- Why it is not on the Reminder Plan ----------------------------------------------------------


def test_a_mute_survives_an_unsave_and_a_re_save():
    """The reason this is its own table.

    `unsave_event` deletes the event's `REMINDER_PLAN` and cancels its sends. A mute stored
    on the plan would go with it, and the user would be silently un-muted by an action that
    had nothing to do with notices.
    """
    from apps.delivery.models import ReminderPlan

    mute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)
    ReminderPlan.objects.using(PERSONAL).create(
        user_id=USER, target_kind="saved_event", target_id=EVENT, slots=["1d"]
    )

    # What an unsave does to the plan, by the same route `remove_plans_for_targets` takes.
    ReminderPlan.objects.using(PERSONAL).filter(user_id=USER, target_id=EVENT).delete()

    assert is_muted(user_id=USER, event_id=EVENT)


def test_a_mute_does_not_touch_the_events_reminders():
    """A mute silences the correction, not the event."""
    from apps.delivery.models import ReminderPlan

    plan = ReminderPlan.objects.using(PERSONAL).create(
        user_id=USER, target_kind="saved_event", target_id=EVENT, slots=["1d", "1hr"]
    )

    mute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    plan.refresh_from_db()
    assert plan.slots == ["1d", "1hr"]
    assert (
        ScheduledSend.objects.using(PERSONAL)
        .filter(user_id=USER, target_id=EVENT, status=ScheduledSend.Status.CANCELLED)
        .count()
        == 0
    )


def test_muting_does_not_create_a_reminder_plan():
    from apps.delivery.models import ReminderPlan

    mute_event_notices(user_id=USER, event_id=EVENT, actor=actor(), now=NOW)

    assert not ReminderPlan.objects.using(PERSONAL).filter(user_id=USER).exists()
    assert EventNoticeMute.objects.using(PERSONAL).filter(user_id=USER).count() == 1
