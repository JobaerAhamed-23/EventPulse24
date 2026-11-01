"""Applying an unsubscribe, and cancelling what it stops (FR-11, FR-10, AD-7, AD-16).

**The properties under test are the separation ones.** FR-11: a reminder's link stops
*that event's* reminders; the digest's link stops *the Pulse Ping*. They are different
user decisions about different things, and **one never touches the other**.

So the centre of this file is a pair of tests that assert the separation in both
directions:

- A reminder unsubscribe **leaves every reminder plan for other events alone** and
  **leaves the Pulse Ping alone**.
- A Ping unsubscribe **touches no reminder plan at all**.

And both scopes **cancel their own pending sends**, so the mail the user just turned off
is not delivered afterwards.
"""

from datetime import UTC, datetime

import pytest

from apps.delivery.models import NotificationPreference, ReminderPlan, ScheduledSend
from apps.delivery.services.unsubscribes import (
    pulse_ping_unsubscribed,
    unsubscribe_event_reminders,
    unsubscribe_pulse_ping,
)
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.delivery.factories import ReminderPlanFactory, ScheduledSendFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)


def _actor(user_id) -> Actor:
    return Actor.user(user_id)


# --- The event scope -----------------------------------------------------------------------------


def test_the_event_scope_empties_the_plan():
    """**A zero-slot plan is already a valid state** — FR-9: "0 slots = no reminders (still
    in feed)". So "unsubscribed from this event's reminders" and "no reminders on this
    event" are the same fact, and one representation says both."""
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d", "1hr"])

    unsubscribe_event_reminders(
        user_id=user,
        target_id=plan.target_id,
        actor=_actor(user),
        now=NOW,
    )

    plan.refresh_from_db()
    assert plan.slots == []


def test_the_event_scope_cancels_that_events_pending_sends():
    """**Cancelling, not swallowing.** A row left pending would be claimed by the sweep,
    rendered and sent — and the user would receive the very mail they just turned off."""
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    row = ScheduledSendFactory(
        user_id=user,
        target_kind=plan.target_kind,
        target_id=plan.target_id,
    )

    result = unsubscribe_event_reminders(
        user_id=user,
        target_id=plan.target_id,
        actor=_actor(user),
        now=NOW,
    )

    row.refresh_from_db()
    assert row.status == ScheduledSend.Status.CANCELLED
    assert result.cancelled == 1


def test_the_event_scope_leaves_other_events_alone():
    """One event's reminders can be off while another event's are on — which is exactly
    why the scope is a plan rather than a flag on the user's preference row."""
    user = uuid7()
    mine = ReminderPlanFactory(user_id=user, slots=["1d"])
    theirs = ReminderPlanFactory(user_id=user, slots=["1d"])

    unsubscribe_event_reminders(
        user_id=user,
        target_id=mine.target_id,
        actor=_actor(user),
        now=NOW,
    )

    theirs.refresh_from_db()
    assert theirs.slots == ["1d"]


def test_the_event_scope_leaves_the_pulse_ping_alone():
    """**FR-11's whole point.** The user asked to stop *this event's* reminders and not
    everything, so the daily digest keeps arriving."""
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])

    unsubscribe_event_reminders(
        user_id=user,
        target_id=plan.target_id,
        actor=_actor(user),
        now=NOW,
    )

    assert pulse_ping_unsubscribed(user_id=user) is False


def test_the_event_scope_leaves_other_users_pending_sends_alone():
    user = uuid7()
    other = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    their_row = ScheduledSendFactory(
        user_id=other,
        target_kind=plan.target_kind,
        target_id=plan.target_id,
    )

    unsubscribe_event_reminders(
        user_id=user,
        target_id=plan.target_id,
        actor=_actor(user),
        now=NOW,
    )

    their_row.refresh_from_db()
    assert their_row.status == ScheduledSend.Status.PENDING


def test_the_event_scope_on_an_event_with_no_plan_is_a_no_op():
    """There was nothing to stop, so the answer says so. Not an error: the user reached
    the link from a mail about an event whose plan has since been removed."""
    user = uuid7()

    result = unsubscribe_event_reminders(
        user_id=user,
        target_id=uuid7(),
        actor=_actor(user),
        now=NOW,
    )

    assert result.changed is False
    assert result.already_unsubscribed is True
    assert result.cancelled == 0


def test_unsubscribing_twice_is_a_no_op():
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])

    first = unsubscribe_event_reminders(
        user_id=user,
        target_id=plan.target_id,
        actor=_actor(user),
        now=NOW,
    )
    second = unsubscribe_event_reminders(
        user_id=user,
        target_id=plan.target_id,
        actor=_actor(user),
        now=NOW,
    )

    assert first.changed is True
    assert second.changed is False
    assert second.already_unsubscribed is True


def test_the_event_scope_leaves_a_sent_send_sent():
    """A `sent` row is a fact about an email that already went out, and unsubscribing now
    does not un-send it."""
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    row = ScheduledSendFactory(
        user_id=user,
        target_kind=plan.target_kind,
        target_id=plan.target_id,
        status=ScheduledSend.Status.SENT,
        sent_at=NOW,
    )

    unsubscribe_event_reminders(
        user_id=user,
        target_id=plan.target_id,
        actor=_actor(user),
        now=NOW,
    )

    row.refresh_from_db()
    assert row.status == ScheduledSend.Status.SENT


# --- The Ping scope ------------------------------------------------------------------------------


def test_the_ping_scope_turns_the_ping_off():
    user = uuid7()

    result = unsubscribe_pulse_ping(user_id=user, actor=_actor(user), now=NOW)

    assert result.changed is True
    assert pulse_ping_unsubscribed(user_id=user) is True


def test_the_ping_scope_cancels_the_pending_digest_sends():
    """**By kind, because a digest row has no target.** `ScheduledSend.target_id` is
    `NULL` for a digest — the row is about a user and a day, not an event."""
    user = uuid7()
    row = ScheduledSendFactory(
        user_id=user,
        kind=ScheduledSend.Kind.DIGEST,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
    )

    result = unsubscribe_pulse_ping(user_id=user, actor=_actor(user), now=NOW)

    row.refresh_from_db()
    assert row.status == ScheduledSend.Status.CANCELLED
    assert result.cancelled == 1


def test_the_ping_scope_touches_no_reminder_plan():
    """**The Ping scope, and only the Ping scope.** No reminder plan is read and none is
    written — the user asked to stop the daily digest, not their event reminders."""
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d", "1hr"])

    unsubscribe_pulse_ping(user_id=user, actor=_actor(user), now=NOW)

    plan.refresh_from_db()
    assert plan.slots == ["1d", "1hr"]


def test_the_ping_scope_leaves_the_pending_reminder_sends_alone():
    """The other half of the separation, at the level of the sends themselves."""
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    row = ScheduledSendFactory(
        user_id=user,
        target_kind=plan.target_kind,
        target_id=plan.target_id,
    )

    unsubscribe_pulse_ping(user_id=user, actor=_actor(user), now=NOW)

    row.refresh_from_db()
    assert row.status == ScheduledSend.Status.PENDING


def test_unsubscribing_from_the_ping_twice_is_a_no_op():
    user = uuid7()

    first = unsubscribe_pulse_ping(user_id=user, actor=_actor(user), now=NOW)
    second = unsubscribe_pulse_ping(user_id=user, actor=_actor(user), now=NOW)

    assert first.changed is True
    assert second.changed is False
    assert second.already_unsubscribed is True


def test_the_ping_scope_leaves_a_sent_digest_sent():
    user = uuid7()
    row = ScheduledSendFactory(
        user_id=user,
        kind=ScheduledSend.Kind.DIGEST,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        status=ScheduledSend.Status.SENT,
        sent_at=NOW,
    )

    unsubscribe_pulse_ping(user_id=user, actor=_actor(user), now=NOW)

    row.refresh_from_db()
    assert row.status == ScheduledSend.Status.SENT


# --- The read that creates nothing ---------------------------------------------------------------


def test_asking_whether_the_ping_is_off_creates_nothing():
    """A user who has never opened settings has not unsubscribed, and asking the question
    must not be the thing that creates their preferences."""
    user = uuid7()

    assert pulse_ping_unsubscribed(user_id=user) is False
    assert NotificationPreference.objects.using(PERSONAL).filter(user_id=user).count() == 0


# --- The audit rows carry no address (AD-13) -----------------------------------------------------


def test_the_audit_rows_carry_no_address():
    """Ids and counts only. An address in an audit `details` dict would be PII in a table
    that crosses into `catalog`."""
    from apps.delivery.models import DeliveryAuditEntry

    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])

    unsubscribe_event_reminders(
        user_id=user,
        target_id=plan.target_id,
        actor=_actor(user),
        now=NOW,
    )

    rows = DeliveryAuditEntry.objects.using(PERSONAL).filter(action="unsubscribe.event_reminders")
    assert rows.exists()
    for row in rows:
        details = row.details or {}
        for value in details.values():
            assert "@" not in str(value)


# --- The plan's own kind is read, never inferred -------------------------------------------------


def test_the_event_scope_works_for_a_saved_public_event_too():
    """The plan says which kind of record it is about, and the command **reads** that
    rather than carrying the kind in the token — so the two cannot disagree."""
    user = uuid7()
    plan = ReminderPlanFactory(
        user_id=user,
        target_kind=ReminderPlan.TargetKind.SAVED_EVENT,
        slots=["1d"],
    )
    row = ScheduledSendFactory(
        user_id=user,
        target_kind=ReminderPlan.TargetKind.SAVED_EVENT,
        target_id=plan.target_id,
    )

    unsubscribe_event_reminders(
        user_id=user,
        target_id=plan.target_id,
        actor=_actor(user),
        now=NOW,
    )

    plan.refresh_from_db()
    row.refresh_from_db()
    assert plan.slots == []
    assert row.status == ScheduledSend.Status.CANCELLED
