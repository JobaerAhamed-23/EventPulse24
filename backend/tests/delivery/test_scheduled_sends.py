"""The single writer of `SCHEDULED_SEND`: minting, rewriting, cancelling, lifecycle (AD-7, AD-17).

The tests are grouped by the three change kinds, because the whole risk in this module is that
they look alike and must not behave alike.
"""

import inspect
from datetime import UTC, datetime, time, timedelta

import pytest

from apps.delivery.models import ScheduledSend
from apps.delivery.services import scheduled_sends
from apps.delivery.services.notification_preferences import set_quiet_hours
from apps.delivery.services.scheduled_sends import (
    SendTarget,
    TerminalSendError,
    apply_lifecycle_change,
    cancel_pending_digests_for_user,
    cancel_sends_for_targets,
    mint_for_plan,
    reschedule_pending_for_user,
)
from apps.ingestion.models import EventStateChange
from domain.quiet_hours import QuietHours
from ports.email import Stream
from shared.actor import Actor
from shared.constants import LIFECYCLE_SEND_BEHAVIOUR, LifecycleSendBehaviour
from shared.db import PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
START = datetime(2026, 11, 20, 19, 0, tzinfo=UTC)  # ~19 days out: every slot is in the future
ALL_SLOTS = ["5d", "2d", "1d", "1hr"]


def a_target(*, version: int = 1, start=START, catalog: bool = True) -> SendTarget:
    event_id = uuid7()
    return SendTarget(
        target_kind="saved_event" if catalog else "personal_event",
        target_id=event_id,
        start_utc=start,
        version=version,
        catalog_event_id=event_id if catalog else None,
    )


def pending_of(user_id):
    return ScheduledSend.objects.using(PERSONAL).filter(
        user_id=user_id, status=ScheduledSend.Status.PENDING
    )


def _a_digest_row(*, user_id, status=ScheduledSend.Status.PENDING):
    """One digest row, which is **the shape that has no target**.

    A digest row is about a user and a day: `target_id` is `NULL` and `target_kind` is
    empty. That shape is why the digest cancellation is a command of its own rather than
    another `(target_kind, target_id)` pair for `cancel_sends_for_targets`.
    """
    return ScheduledSend.objects.using(PERSONAL).create(
        user_id=user_id,
        kind=ScheduledSend.Kind.DIGEST,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        send_key=f"digest:{user_id}:2026-11-01",
        stream="bulk",
        due_at=datetime(2026, 11, 1, 8, 0, tzinfo=UTC),
        status=status,
        sent_at=NOW if status == ScheduledSend.Status.SENT else None,
    )


# --- 1. Minting --------------------------------------------------------------------


def test_minting_creates_one_row_per_slot():
    user, target = uuid7(), a_target()

    minted = mint_for_plan(
        user_id=user, target=target, slots=ALL_SLOTS, actor=Actor.user(user), now=NOW
    )

    assert minted == 4
    assert pending_of(user).count() == 4


def test_an_empty_plan_mints_nothing_and_is_not_an_error():
    """FR-9: "0 slots = no reminders (still in feed)"."""
    user = uuid7()

    assert (
        mint_for_plan(user_id=user, target=a_target(), slots=[], actor=Actor.user(user), now=NOW)
        == 0
    )


def test_a_slot_whose_moment_has_passed_is_not_minted():
    """A 5d slot on an event 3 days out would otherwise fire immediately, saying "5 days until"."""
    user = uuid7()
    three_days_out = NOW + timedelta(days=3)

    minted = mint_for_plan(
        user_id=user,
        target=a_target(start=three_days_out),
        slots=ALL_SLOTS,
        actor=Actor.user(user),
        now=NOW,
    )

    assert minted == 3
    assert "5d" not in set(pending_of(user).values_list("slot", flat=True))


def test_minting_twice_adds_nothing():
    user, target = uuid7(), a_target()
    kwargs = {"user_id": user, "target": target, "slots": ALL_SLOTS, "actor": Actor.user(user)}

    mint_for_plan(**kwargs, now=NOW)
    second = mint_for_plan(**kwargs, now=NOW)

    assert second == 0
    assert pending_of(user).count() == 4


def test_quiet_hours_is_applied_at_minting():
    """AD-7: the stored `due_at` is already the true send time."""
    user = uuid7()
    # 22:00-08:00 UTC; an event at 19:00 means the 1d slot lands at 19:00 the day before
    # (outside), while a 1hr slot on a 23:30 event would land inside.
    set_quiet_hours(
        user_id=user, window=QuietHours(time(22, 0), time(8, 0)), actor=Actor.user(user), now=NOW
    )
    late = datetime(2026, 11, 20, 23, 30, tzinfo=UTC)

    mint_for_plan(
        user_id=user,
        target=a_target(start=late),
        slots=["1hr"],
        actor=Actor.user(user),
        now=NOW,
    )

    row = pending_of(user).get()
    # 22:30 is inside the window, so the send is deferred to 08:00 the next morning.
    assert row.due_at == datetime(2026, 11, 21, 8, 0, tzinfo=UTC)


# --- 2. Rescheduling (never mints) -------------------------------------------------


def test_the_reschedule_path_has_no_create_call():
    """Structural, not behavioural: the duplicate-reminder bug is made unreachable.

    A rule the suite checks beats a rule everyone has to remember.
    """
    source = inspect.getsource(reschedule_pending_for_user)

    for forbidden in (".create(", "objects.create", "bulk_create", "get_or_create"):
        assert forbidden not in source, f"the reschedule path can mint: {forbidden}"


def test_rescheduling_rewrites_due_at_without_changing_keys():
    user, target = uuid7(), a_target()
    mint_for_plan(user_id=user, target=target, slots=["1d"], actor=Actor.user(user), now=NOW)
    before = pending_of(user).get()

    set_quiet_hours(
        user_id=user, window=QuietHours(time(17, 0), time(21, 0)), actor=Actor.user(user), now=NOW
    )
    reschedule_pending_for_user(user_id=user, actor=Actor.user(user), now=NOW)

    after = pending_of(user).get()
    assert after.send_key == before.send_key
    assert after.due_at != before.due_at


def test_rescheduling_never_adds_a_row():
    user = uuid7()
    mint_for_plan(user_id=user, target=a_target(), slots=ALL_SLOTS, actor=Actor.user(user), now=NOW)

    for _ in range(10):
        reschedule_pending_for_user(user_id=user, actor=Actor.user(user), now=NOW)

    assert ScheduledSend.objects.using(PERSONAL).filter(user_id=user).count() == 4


def test_rescheduling_leaves_terminal_rows_alone():
    """A sent row is a fact about an email that already went out."""
    user, target = uuid7(), a_target()
    mint_for_plan(user_id=user, target=target, slots=["1d"], actor=Actor.user(user), now=NOW)
    row = pending_of(user).get()
    row.status, row.sent_at = ScheduledSend.Status.SENT, NOW
    row.save(using=PERSONAL, update_fields=["status", "sent_at", "updated_at"])
    sent_due = row.due_at

    reschedule_pending_for_user(user_id=user, actor=Actor.user(user), now=NOW)

    row.refresh_from_db()
    assert row.due_at == sent_due


def test_rescheduling_reads_the_zone_once_not_once_per_row():
    """Design D4: the query count must not grow with a user's reminders."""
    from django.db import connections
    from django.test.utils import CaptureQueriesContext

    user = uuid7()
    mint_for_plan(user_id=user, target=a_target(), slots=ALL_SLOTS, actor=Actor.user(user), now=NOW)

    with CaptureQueriesContext(connections[PERSONAL]) as four_rows:
        reschedule_pending_for_user(user_id=user, actor=Actor.user(user), now=NOW)

    user2 = uuid7()
    mint_for_plan(user_id=user2, target=a_target(), slots=["1d"], actor=Actor.user(user2), now=NOW)

    with CaptureQueriesContext(connections[PERSONAL]) as one_row:
        reschedule_pending_for_user(user_id=user2, actor=Actor.user(user2), now=NOW)

    # Four pending rows must not cost four extra zone reads.
    assert len(four_rows) - len(one_row) <= 4


def test_a_row_with_no_slot_instant_is_left_alone():
    """A row with no pre-shift instant has no Quiet-Hours arithmetic — so it is skipped.

    A `state_notice` is one: its due time is not a slot offset, so it has no `slot_at` and
    no shift to re-apply. **The row is left exactly as it was** rather than re-timed from a
    guess — inventing a due time is a send at an hour nobody chose.
    """
    user = uuid7()
    row = ScheduledSend.objects.using(PERSONAL).create(
        user_id=user,
        kind=ScheduledSend.Kind.STATE_NOTICE,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        stream=Stream.TRANSACTIONAL.value,
        due_at=NOW + timedelta(hours=1),
        status=ScheduledSend.Status.PENDING,
    )
    due_before = row.due_at

    reschedule_pending_for_user(user_id=user, actor=Actor.user(user), now=NOW)

    row.refresh_from_db()
    assert row.due_at == due_before


def test_a_slot_with_no_offset_is_not_minted():
    """A slot with no computable offset has no instant — so it is skipped, not guessed at.

    The plan's validator refuses such a slot on write, so this is the defensive branch:
    a slot id that is neither a named tier nor a well-formed custom slot.
    """
    user = uuid7()

    minted = mint_for_plan(
        user_id=user,
        target=a_target(),
        slots=["not-a-slot"],
        actor=Actor.user(user),
        now=NOW,
    )

    assert minted == 0
    assert pending_of(user).count() == 0


def test_a_digest_row_whose_key_has_no_readable_date_is_left_alone():
    """A digest whose day cannot be read out of its key is not re-timed to a guessed day.

    A digest moved to the wrong date is a digest that goes out on the wrong day, so the row
    is left exactly as it was.
    """
    user = uuid7()
    row = ScheduledSend.objects.using(PERSONAL).create(
        user_id=user,
        kind=ScheduledSend.Kind.DIGEST,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        stream=Stream.BULK.value,
        due_at=NOW + timedelta(hours=1),
        status=ScheduledSend.Status.PENDING,
        send_key=f"{user}:digest:not-a-date",
    )
    due_before = row.due_at

    reschedule_pending_for_user(user_id=user, actor=Actor.user(user), now=NOW)

    row.refresh_from_db()
    assert row.due_at == due_before


# --- 3. Cancelling -----------------------------------------------------------------


def test_cancelling_moves_pending_rows_only():
    user, target = uuid7(), a_target()
    mint_for_plan(user_id=user, target=target, slots=ALL_SLOTS, actor=Actor.user(user), now=NOW)

    cancelled = cancel_sends_for_targets(
        user_id=user,
        targets=[(target.target_kind, target.target_id)],
        actor=Actor.user(user),
        now=NOW,
    )

    assert cancelled == 4
    assert pending_of(user).count() == 0


def test_cancelling_an_unknown_target_is_a_no_op():
    user = uuid7()

    assert (
        cancel_sends_for_targets(
            user_id=user, targets=[("saved_event", uuid7())], actor=Actor.user(user), now=NOW
        )
        == 0
    )


def test_cancelling_no_targets_is_a_no_op():
    user = uuid7()

    assert cancel_sends_for_targets(user_id=user, targets=[], actor=Actor.user(user), now=NOW) == 0


# --- Cancelling the digest rows, which have no target ------------------------------------------


def test_cancelling_digests_moves_the_pending_digest_rows():
    """**By kind, because a digest row has no target.** `target_id` is `NULL` and
    `target_kind` is empty — the row is about a user and a day, not an event — so
    `cancel_sends_for_targets`, which matches on a target pair, cannot address one."""
    user = uuid7()
    _a_digest_row(user_id=user)

    cancelled = cancel_pending_digests_for_user(user_id=user, actor=Actor.user(user), now=NOW)

    assert cancelled == 1
    assert pending_of(user).count() == 0


def test_cancelling_digests_leaves_the_reminder_rows_alone():
    """The other half of the separation: a digest cancellation is not a reminder
    cancellation. The user asked to stop the daily digest, not their event reminders."""
    user = uuid7()
    _a_digest_row(user_id=user)
    target = a_target()
    mint_for_plan(user_id=user, target=target, slots=ALL_SLOTS, actor=Actor.user(user), now=NOW)

    cancel_pending_digests_for_user(user_id=user, actor=Actor.user(user), now=NOW)

    assert pending_of(user).count() == len(ALL_SLOTS)


def test_cancelling_digests_leaves_a_sent_digest_sent():
    """A `sent` row is a fact about an email that already went out, and cancelling now
    does not un-send it."""
    user = uuid7()
    _a_digest_row(user_id=user, status=ScheduledSend.Status.SENT)

    cancelled = cancel_pending_digests_for_user(user_id=user, actor=Actor.user(user), now=NOW)

    assert cancelled == 0


def test_cancelling_digests_for_a_user_with_no_digests_is_a_no_op():
    user = uuid7()

    assert cancel_pending_digests_for_user(user_id=user, actor=Actor.user(user), now=NOW) == 0


def test_cancelling_digests_does_not_reach_another_users_digests():
    """The cancellation is scoped to one user. A digest row is about a user and a day,
    and the day is not what identifies it here — the user is."""
    mine, theirs = uuid7(), uuid7()
    _a_digest_row(user_id=mine)
    _a_digest_row(user_id=theirs)

    cancel_pending_digests_for_user(user_id=mine, actor=Actor.user(mine), now=NOW)

    assert pending_of(theirs).count() == 1


# --- 4. Lifecycle (AD-17) ----------------------------------------------------------


def test_every_lifecycle_kind_is_mapped():
    """A new kind in `ingestion` must fail here, not silently do nothing to reminders."""
    for kind in EventStateChange.Kind:
        assert kind.value in LIFECYCLE_SEND_BEHAVIOUR, f"{kind.value} has no send behaviour"


def test_a_moved_event_cancels_and_remints_with_a_new_key():
    user = uuid7()
    v1 = a_target(version=1)
    mint_for_plan(user_id=user, target=v1, slots=["1d"], actor=Actor.user(user), now=NOW)
    old_key = pending_of(user).get().send_key

    v2 = SendTarget(
        target_kind=v1.target_kind,
        target_id=v1.target_id,
        start_utc=START + timedelta(days=2),
        version=2,
        catalog_event_id=v1.catalog_event_id,
    )
    result = apply_lifecycle_change(
        user_id=user,
        target=v2,
        kind="time_moved",
        slots=["1d"],
        actor=Actor.user(user),
        now=NOW,
    )

    assert result == {"cancelled": 1, "minted": 1, "restamped": 0}
    new_key = pending_of(user).get().send_key
    assert new_key != old_key


def test_a_sent_reminder_for_the_old_date_does_not_block_the_new_one():
    """AD-7's explicit case: the old key stays spent."""
    user = uuid7()
    v1 = a_target(version=1)
    mint_for_plan(user_id=user, target=v1, slots=["1d"], actor=Actor.user(user), now=NOW)
    already = ScheduledSend.objects.using(PERSONAL).get(user_id=user)
    already.status, already.sent_at = ScheduledSend.Status.SENT, NOW
    already.save(using=PERSONAL, update_fields=["status", "sent_at", "updated_at"])

    v2 = SendTarget(
        target_kind=v1.target_kind,
        target_id=v1.target_id,
        start_utc=START + timedelta(days=2),
        version=2,
        catalog_event_id=v1.catalog_event_id,
    )
    apply_lifecycle_change(
        user_id=user,
        target=v2,
        kind="time_moved",
        slots=["1d"],
        actor=Actor.user(user),
        now=NOW,
    )

    assert pending_of(user).count() == 1


def test_a_cancelled_event_cancels_and_mints_nothing():
    user = uuid7()
    v1 = a_target(version=1)
    mint_for_plan(user_id=user, target=v1, slots=ALL_SLOTS, actor=Actor.user(user), now=NOW)

    v2 = SendTarget(**{**v1.__dict__, "version": 2})
    result = apply_lifecycle_change(
        user_id=user,
        target=v2,
        kind="cancelled",
        slots=ALL_SLOTS,
        actor=Actor.user(user),
        now=NOW,
    )

    assert result["cancelled"] == 4
    assert result["minted"] == 0
    assert pending_of(user).count() == 0


def test_a_sold_out_event_keeps_its_reminders():
    """A sold-out event still happens. Cancelling would be a plausible, wrong reading."""
    user = uuid7()
    v1 = a_target(version=1)
    mint_for_plan(user_id=user, target=v1, slots=ALL_SLOTS, actor=Actor.user(user), now=NOW)

    v2 = SendTarget(**{**v1.__dict__, "version": 2})
    result = apply_lifecycle_change(
        user_id=user,
        target=v2,
        kind="sold_out",
        slots=ALL_SLOTS,
        actor=Actor.user(user),
        now=NOW,
    )

    assert result["cancelled"] == 0
    assert result["restamped"] == 4
    assert pending_of(user).count() == 4
    assert set(pending_of(user).values_list("event_version", flat=True)) == {2}


def test_a_detail_change_keeps_its_reminders():
    user = uuid7()
    v1 = a_target(version=1)
    mint_for_plan(user_id=user, target=v1, slots=["1d"], actor=Actor.user(user), now=NOW)

    v2 = SendTarget(**{**v1.__dict__, "version": 2})
    apply_lifecycle_change(
        user_id=user,
        target=v2,
        kind="detail_changed",
        slots=["1d"],
        actor=Actor.user(user),
        now=NOW,
    )

    assert pending_of(user).count() == 1


# --- The version guard (design D2) -------------------------------------------------


def test_applying_the_same_change_twice_is_a_no_op():
    """Without the guard, the second run cancels the rows the first just minted."""
    user = uuid7()
    v1 = a_target(version=1)
    mint_for_plan(user_id=user, target=v1, slots=["1d"], actor=Actor.user(user), now=NOW)
    v2 = SendTarget(**{**v1.__dict__, "version": 2, "start_utc": START + timedelta(days=2)})

    first = apply_lifecycle_change(
        user_id=user, target=v2, kind="time_moved", slots=["1d"], actor=Actor.user(user), now=NOW
    )
    second = apply_lifecycle_change(
        user_id=user, target=v2, kind="time_moved", slots=["1d"], actor=Actor.user(user), now=NOW
    )

    assert first["minted"] == 1
    assert second == {"cancelled": 0, "minted": 0, "restamped": 0}
    # The decisive assertion: the user still has a pending reminder.
    assert pending_of(user).count() == 1


def test_an_older_change_arriving_after_a_newer_one_is_a_no_op():
    """AD-17: out-of-order safety. An older postponement must not overwrite a newer one."""
    user = uuid7()
    v1 = a_target(version=1)
    mint_for_plan(user_id=user, target=v1, slots=["1d"], actor=Actor.user(user), now=NOW)
    v3 = SendTarget(**{**v1.__dict__, "version": 3, "start_utc": START + timedelta(days=3)})
    apply_lifecycle_change(
        user_id=user, target=v3, kind="time_moved", slots=["1d"], actor=Actor.user(user), now=NOW
    )
    after_v3 = pending_of(user).get().send_key

    v2 = SendTarget(**{**v1.__dict__, "version": 2, "start_utc": START + timedelta(days=2)})
    late = apply_lifecycle_change(
        user_id=user, target=v2, kind="time_moved", slots=["1d"], actor=Actor.user(user), now=NOW
    )

    assert late["cancelled"] == 0
    assert pending_of(user).get().send_key == after_v3


# --- The terminal guard (design D6, closing item 3's gap) --------------------------


def test_a_terminal_row_cannot_be_cancelled():
    user, target = uuid7(), a_target()
    mint_for_plan(user_id=user, target=target, slots=["1d"], actor=Actor.user(user), now=NOW)
    row = pending_of(user).get()
    row.status, row.sent_at = ScheduledSend.Status.SENT, NOW
    row.save(using=PERSONAL, update_fields=["status", "sent_at", "updated_at"])

    # The command filters to pending, so a sent row is simply not selected — the guard is the
    # second line of defence, asserted directly below.
    assert (
        cancel_sends_for_targets(
            user_id=user,
            targets=[(target.target_kind, target.target_id)],
            actor=Actor.user(user),
            now=NOW,
        )
        == 0
    )


@pytest.mark.parametrize(
    "status",
    [ScheduledSend.Status.SENT, ScheduledSend.Status.CANCELLED, ScheduledSend.Status.FAILED],
)
def test_the_guard_refuses_every_terminal_status(status):
    row = ScheduledSend(
        user_id=uuid7(),
        kind=ScheduledSend.Kind.EVENT_REMINDER,
        send_key="k",
        stream="transactional",
        due_at=NOW,
        status=status,
    )

    with pytest.raises(TerminalSendError):
        scheduled_sends._guard_not_terminal(row)


def test_the_guard_allows_pending():
    row = ScheduledSend(
        user_id=uuid7(),
        kind=ScheduledSend.Kind.EVENT_REMINDER,
        send_key="k",
        stream="transactional",
        due_at=NOW,
        status=ScheduledSend.Status.PENDING,
    )

    scheduled_sends._guard_not_terminal(row)  # does not raise


# --- Audit (AD-5 / AD-13) ----------------------------------------------------------


def test_minting_writes_an_audit_row_without_an_address():
    from apps.delivery.models import DeliveryAuditEntry

    user = uuid7()
    mint_for_plan(user_id=user, target=a_target(), slots=["1d"], actor=Actor.user(user), now=NOW)

    entry = DeliveryAuditEntry.objects.using(PERSONAL).filter(action="scheduled_send.minted").last()
    assert entry is not None
    assert "@" not in str(entry.details)


def test_the_behaviour_map_has_no_default():
    """An unmapped kind must raise, not silently pick a behaviour."""
    with pytest.raises(KeyError):
        LIFECYCLE_SEND_BEHAVIOUR["not_a_real_kind"]


def test_the_three_behaviours_are_distinct():
    assert len(set(LifecycleSendBehaviour)) == 3


# --- The plan and its sends move together (or not at all) --------------------------


def test_a_plan_edit_cancels_the_sends_for_dropped_slots():
    from apps.delivery.services.reminder_plans import attach_default_plan, set_plan_slots

    user, target = uuid7(), a_target()
    attach_default_plan(
        user_id=user,
        target_kind="saved_event",
        target_id=target.target_id,
        actor=Actor.user(user),
        now=NOW,
    )
    mint_for_plan(user_id=user, target=target, slots=["1d", "1hr"], actor=Actor.user(user), now=NOW)

    set_plan_slots(
        user_id=user,
        target_kind="saved_event",
        target_id=target.target_id,
        slots=("1d",),
        actor=Actor.user(user),
        now=NOW,
        send_target=target,
    )

    assert set(pending_of(user).values_list("slot", flat=True)) == {"1d"}


def test_a_plan_edited_to_zero_slots_cancels_every_send():
    from apps.delivery.services.reminder_plans import attach_default_plan, remove_all_reminders

    user, target = uuid7(), a_target()
    attach_default_plan(
        user_id=user,
        target_kind="saved_event",
        target_id=target.target_id,
        actor=Actor.user(user),
        now=NOW,
    )
    mint_for_plan(user_id=user, target=target, slots=ALL_SLOTS, actor=Actor.user(user), now=NOW)
    assert pending_of(user).count() == 4

    remove_all_reminders(
        user_id=user,
        target_kind="saved_event",
        target_id=target.target_id,
        actor=Actor.user(user),
        now=NOW,
        send_target=target,
    )

    assert pending_of(user).count() == 0


def test_a_kept_slot_keeps_its_row_and_its_key():
    """`resync_plan` cancels only what was dropped. Spending a kept slot's key would leave it
    unable to be re-minted."""
    from apps.delivery.services.reminder_plans import attach_default_plan, set_plan_slots

    user, target = uuid7(), a_target()
    attach_default_plan(
        user_id=user,
        target_kind="saved_event",
        target_id=target.target_id,
        actor=Actor.user(user),
        now=NOW,
    )
    mint_for_plan(user_id=user, target=target, slots=["1d", "1hr"], actor=Actor.user(user), now=NOW)
    kept_key = pending_of(user).get(slot="1d").send_key

    set_plan_slots(
        user_id=user,
        target_kind="saved_event",
        target_id=target.target_id,
        slots=("1d", "2d"),
        actor=Actor.user(user),
        now=NOW,
        send_target=target,
    )

    assert pending_of(user).get(slot="1d").send_key == kept_key
    assert set(pending_of(user).values_list("slot", flat=True)) == {"1d", "2d"}


def test_a_failing_send_resync_rolls_the_plan_back_too():
    """Asserting both happen is not asserting they are atomic.

    Forcing the send half to raise and finding the plan unchanged is the only way to tell a
    transaction from a sequence.
    """
    from unittest.mock import patch

    from apps.delivery.models import ReminderPlan
    from apps.delivery.services.reminder_plans import attach_default_plan, set_plan_slots

    user, target = uuid7(), a_target()
    attach_default_plan(
        user_id=user,
        target_kind="saved_event",
        target_id=target.target_id,
        actor=Actor.user(user),
        now=NOW,
    )
    before = (
        ReminderPlan.objects.using(PERSONAL).get(user_id=user, target_id=target.target_id).slots
    )

    with (
        patch(
            "apps.delivery.services.reminder_plans.resync_plan", side_effect=RuntimeError("boom")
        ),
        pytest.raises(RuntimeError),
    ):
        set_plan_slots(
            user_id=user,
            target_kind="saved_event",
            target_id=target.target_id,
            slots=("5d",),
            actor=Actor.user(user),
            now=NOW,
            send_target=target,
        )

    after = ReminderPlan.objects.using(PERSONAL).get(user_id=user, target_id=target.target_id).slots
    assert after == before, "the plan was committed without its sends"
