"""The `delivery` published service: the commands `personalization` calls (AD-16, FR-9, FR-20).

Each command is a named, audited mutation (AD-5). The tests pin the *behaviour* — the default
plan, the picker's replacement, the empty plan — rather than the ORM calls behind it.
"""

from datetime import UTC, datetime

import pytest

from apps.delivery.models import DeliveryAuditEntry, ReminderPlan
from apps.delivery.services.reminder_plans import (
    PlanSlots,
    ReminderPlanNotFoundError,
    TooManySlotsError,
    UnknownSlotError,
    UnknownTargetKindError,
    attach_default_plan,
    get_plan,
    remove_all_reminders,
    remove_plans_for_targets,
    set_plan_slots,
    slot_offsets,
)
from domain.errors import ValidationError
from shared.actor import Actor
from shared.constants import CUSTOM_SLOT_PREFIX, DEFAULT_REMINDER_PLAN, ReminderSlot
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.delivery.factories import ReminderPlanFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
USER = uuid7()
TARGET = uuid7()


# --- The default plan (FR-20) -----------------------------------------------------------------


def test_the_default_plan_is_exactly_one_day_and_one_hour():
    # AD-16: "FR-9 and FR-20 both hardcode the default plan as 1d + 1hr. It is one named
    # constant in `shared/` ... never two literals that can drift apart."
    assert DEFAULT_REMINDER_PLAN == (ReminderSlot.ONE_DAY, ReminderSlot.ONE_HOUR)
    assert [slot.value for slot in DEFAULT_REMINDER_PLAN] == ["1d", "1hr"]


def test_attaching_the_default_plan_creates_the_plan():
    plan = attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert plan.slots == ("1d", "1hr")
    assert ReminderPlan.objects.get(pk=plan_target_pk(plan)).slots == ["1d", "1hr"]


def plan_target_pk(plan: PlanSlots) -> object:
    return ReminderPlan.objects.get(
        user_id=plan.user_id, target_kind=plan.target_kind, target_id=plan.target_id
    ).pk


def test_attaching_the_default_plan_to_a_saved_event():
    # FR-9's picker applies to a saved public event. The plan holds the *personal-side* row
    # by value, so no catalog event is involved and no wall is crossed.
    plan = attach_default_plan(
        user_id=USER,
        target_kind="saved_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert plan.target_kind == "saved_event"
    assert plan.slots == ("1d", "1hr")


def test_attaching_the_default_plan_twice_keeps_one_plan():
    # The command is idempotent: re-attaching updates the row rather than adding another.
    for _ in range(2):
        attach_default_plan(
            user_id=USER,
            target_kind="personal_event",
            target_id=TARGET,
            actor=Actor.user(USER),
            now=NOW,
        )

    assert ReminderPlan.objects.filter(user_id=USER, target_id=TARGET).count() == 1


def test_attaching_the_default_plan_replaces_the_users_own_slots():
    attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )
    set_plan_slots(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        slots=("5d",),
        actor=Actor.user(USER),
        now=NOW,
    )

    attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert get_plan(user_id=USER, target_kind="personal_event", target_id=TARGET).slots == (
        "1d",
        "1hr",
    )


# --- The picker (FR-9) ------------------------------------------------------------------------


def test_setting_slots_replaces_the_previous_slots():
    attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    plan = set_plan_slots(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        slots=("5d", "2d"),
        actor=Actor.user(USER),
        now=NOW,
    )

    assert plan.slots == ("5d", "2d")


def test_setting_slots_accepts_a_custom_slot():
    # FR-9: "The system also supports a custom slot." AD-7's send key names it by its id.
    #
    # The id **is** the offset now: `custom:90` is 90 minutes before the event. The slot
    # carries its own meaning, so there is no second place for the number and the two
    # cannot disagree — and a custom slot is finally computable, so it can be minted.
    custom = f"{CUSTOM_SLOT_PREFIX}90"
    attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    plan = set_plan_slots(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        slots=("1d", custom),
        actor=Actor.user(USER),
        now=NOW,
    )

    assert plan.slots == ("1d", custom)


def test_setting_slots_rejects_a_fifth_slot():
    attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    with pytest.raises(TooManySlotsError):
        set_plan_slots(
            user_id=USER,
            target_kind="personal_event",
            target_id=TARGET,
            slots=("5d", "2d", "1d", "1hr", "custom:mine"),
            actor=Actor.user(USER),
            now=NOW,
        )


def test_setting_slots_rejects_an_unknown_slot():
    attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    with pytest.raises(UnknownSlotError):
        set_plan_slots(
            user_id=USER,
            target_kind="personal_event",
            target_id=TARGET,
            slots=("3d",),
            actor=Actor.user(USER),
            now=NOW,
        )


def test_setting_slots_rejects_a_repeated_slot():
    attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    with pytest.raises(ValidationError):
        set_plan_slots(
            user_id=USER,
            target_kind="personal_event",
            target_id=TARGET,
            slots=("1d", "1d"),
            actor=Actor.user(USER),
            now=NOW,
        )


def test_setting_slots_on_an_event_without_a_plan_is_not_found():
    with pytest.raises(ReminderPlanNotFoundError):
        set_plan_slots(
            user_id=USER,
            target_kind="personal_event",
            target_id=uuid7(),
            slots=("1d",),
            actor=Actor.user(USER),
            now=NOW,
        )


def test_a_pulse_ping_cannot_be_a_slot():
    # The PRD Glossary: "Pulse Ping is NOT part of any Reminder Plan." There is no slot value
    # that expresses it, so no slot can be one.
    attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    with pytest.raises(UnknownSlotError):
        set_plan_slots(
            user_id=USER,
            target_kind="personal_event",
            target_id=TARGET,
            slots=("pulse_ping",),
            actor=Actor.user(USER),
            now=NOW,
        )


# --- Removing every reminder (FR-9, FR-20) ---------------------------------------------------


def test_removing_all_reminders_leaves_an_empty_plan():
    attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    plan = remove_all_reminders(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    # FR-20: "The user can remove all reminders." An empty plan is a valid state.
    assert plan.slots == ()
    assert ReminderPlan.objects.get(user_id=USER, target_id=TARGET).slots == []


def test_removing_all_reminders_keeps_the_plan_row():
    # "No reminders" is a state the user chose, not the absence of a plan.
    attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    remove_all_reminders(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert ReminderPlan.objects.filter(user_id=USER, target_id=TARGET).count() == 1


# --- The audit log (AD-5) ---------------------------------------------------------------------


def test_attaching_the_default_plan_writes_an_audit_row():
    attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    entry = DeliveryAuditEntry.objects.get(target_id=TARGET)

    assert entry.action == "reminder_plan.attached_default"
    assert entry.actor_kind == "user"
    assert entry.actor_id == USER
    assert entry.details["slots"] == ["1d", "1hr"]


def test_setting_slots_writes_an_audit_row():
    attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    set_plan_slots(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        slots=("5d",),
        actor=Actor.user(USER),
        now=NOW,
    )

    assert (
        DeliveryAuditEntry.objects.filter(
            target_id=TARGET, action="reminder_plan.slots_set"
        ).count()
        == 1
    )


def test_removing_all_reminders_writes_an_audit_row():
    attach_default_plan(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    remove_all_reminders(
        user_id=USER,
        target_kind="personal_event",
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert (
        DeliveryAuditEntry.objects.filter(
            target_id=TARGET, action="reminder_plan.slots_set"
        ).count()
        == 1
    )


# --- Reading a plan ---------------------------------------------------------------------------


def test_getting_a_plan_returns_its_slots():
    ReminderPlanFactory.create(user_id=USER, target_kind="personal_event", target_id=TARGET)

    plan = get_plan(user_id=USER, target_kind="personal_event", target_id=TARGET)

    assert plan.slots == ("1d", "1hr")


def test_getting_a_missing_plan_is_not_found():
    with pytest.raises(ReminderPlanNotFoundError):
        get_plan(user_id=USER, target_kind="personal_event", target_id=uuid7())


# --- The target kind (a closed set) ------------------------------------------------------------


def test_the_target_kind_may_be_given_as_the_enum_member():
    # The kind is a closed set, so the command takes the enum member: an invalid kind is
    # then impossible to express.
    plan = attach_default_plan(
        user_id=USER,
        target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT,
        target_id=TARGET,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert plan.target_kind == "personal_event"


def test_an_unknown_target_kind_is_rejected():
    with pytest.raises(UnknownTargetKindError):
        attach_default_plan(
            user_id=USER,
            target_kind="calendar_event",
            target_id=TARGET,
            actor=Actor.user(USER),
            now=NOW,
        )


def test_an_unknown_target_kind_is_rejected_when_reading():
    with pytest.raises(UnknownTargetKindError):
        get_plan(user_id=USER, target_kind="calendar_event", target_id=TARGET)


# --- Offsets (AD-7, AD-16) -------------------------------------------------------------------


def test_slot_offsets_are_measured_back_from_the_start():
    start = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)

    offsets = slot_offsets(start_utc=start, slots=("1d", "1hr"))

    assert offsets == (
        datetime(2026, 11, 5, 3, 30, tzinfo=UTC),
        datetime(2026, 11, 6, 2, 30, tzinfo=UTC),
    )


def test_slot_offsets_reads_a_custom_slots_offset_from_its_id():
    # A custom slot's id **is** its offset now: `custom:90` is 90 minutes before the event.
    # So the offset is not looked up in `REMINDER_SLOT_OFFSET` and not left out — it is read
    # from the slot itself, and the two cannot disagree.
    start = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)

    offsets = slot_offsets(start_utc=start, slots=("1d", "custom:90"))

    assert offsets == (
        datetime(2026, 11, 5, 3, 30, tzinfo=UTC),
        datetime(2026, 11, 6, 2, 0, tzinfo=UTC),
    )


def test_slot_offsets_leaves_out_a_slot_that_carries_no_offset():
    """A slot whose id is neither a named tier nor a custom slot has no offset at all.

    The validator refuses such a slot on write, so this is defensive — and the answer is
    "leave it out", never a guessed offset.
    """
    start = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)

    offsets = slot_offsets(start_utc=start, slots=("1d", "custom:soon"))

    assert offsets == (datetime(2026, 11, 5, 3, 30, tzinfo=UTC),)


# --- Removing the plans of several targets (D13) ----------------------------------------------


def test_removing_the_plans_of_several_targets_deletes_them():
    first, second = uuid7(), uuid7()
    for target in (first, second):
        ReminderPlanFactory(user_id=USER, target_id=target, slots=["1d"])

    removed = remove_plans_for_targets(
        user_id=USER,
        target_kind="personal_event",
        target_ids=(first, second),
        actor=Actor.system("calendar_sync"),
        now=NOW,
    )

    assert removed == 2
    assert ReminderPlan.objects.using(PERSONAL).filter(target_id__in=[first, second]).count() == 0


def test_removing_the_plans_of_no_targets_removes_nothing():
    assert (
        remove_plans_for_targets(
            user_id=USER,
            target_kind="personal_event",
            target_ids=(),
            actor=Actor.system("calendar_sync"),
            now=NOW,
        )
        == 0
    )


def test_removing_the_plans_leaves_another_users_plans_alone():
    mine, theirs = uuid7(), uuid7()
    ReminderPlanFactory(user_id=USER, target_id=mine, slots=["1d"])
    ReminderPlanFactory(user_id=uuid7(), target_id=theirs, slots=["1d"])

    remove_plans_for_targets(
        user_id=USER,
        target_kind="personal_event",
        target_ids=(mine, theirs),
        actor=Actor.system("calendar_sync"),
        now=NOW,
    )

    assert ReminderPlan.objects.using(PERSONAL).filter(target_id=theirs).count() == 1


def test_removing_the_plans_writes_one_audit_row_per_plan():
    first, second = uuid7(), uuid7()
    for target in (first, second):
        ReminderPlanFactory(user_id=USER, target_id=target, slots=["1d"])

    remove_plans_for_targets(
        user_id=USER,
        target_kind="personal_event",
        target_ids=(first, second),
        actor=Actor.system("calendar_sync"),
        now=NOW,
    )

    # AD-5: one row per mutation, and each row names the plan it removed.
    rows = DeliveryAuditEntry.objects.using(PERSONAL).filter(
        action="reminder_plan.removed_for_target"
    )
    assert rows.count() == 2
    assert {row.target_id for row in rows} == {first, second}


# --- The default plan is the user's own (FR-20) -------------------------------------------------


def test_attaching_the_default_plan_uses_the_users_stored_default():
    """FR-20 closes here: the default stopped being a constant the user could not change."""
    from apps.delivery.services.notification_preferences import set_default_reminder_slots

    user, target = uuid7(), uuid7()
    set_default_reminder_slots(
        user_id=user, slots=[ReminderSlot.FIVE_DAYS.value], actor=Actor.user(user), now=NOW
    )

    plan = attach_default_plan(
        user_id=user,
        target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT,
        target_id=target,
        actor=Actor.user(user),
        now=NOW,
    )

    assert plan.slots == (ReminderSlot.FIVE_DAYS.value,)


def test_attaching_the_default_plan_falls_back_to_the_constant():
    """AD-16: the constant is still the one literal, now as the fallback."""
    user = uuid7()

    plan = attach_default_plan(
        user_id=user,
        target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT,
        target_id=uuid7(),
        actor=Actor.user(user),
        now=NOW,
    )

    assert plan.slots == tuple(slot.value for slot in DEFAULT_REMINDER_PLAN)


def test_attaching_the_default_plan_honours_an_empty_default():
    """A user who chose "no reminders by default" means it — FR-9 makes 0 slots valid."""
    from apps.delivery.services.notification_preferences import set_default_reminder_slots

    user = uuid7()
    set_default_reminder_slots(user_id=user, slots=[], actor=Actor.user(user), now=NOW)

    plan = attach_default_plan(
        user_id=user,
        target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT,
        target_id=uuid7(),
        actor=Actor.user(user),
        now=NOW,
    )

    assert plan.slots == ()


def test_changing_the_default_does_not_rewrite_existing_plans():
    """The misreading that would silently rewrite choices the user made deliberately."""
    from apps.delivery.services.notification_preferences import set_default_reminder_slots

    user, target = uuid7(), uuid7()
    attach_default_plan(
        user_id=user,
        target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT,
        target_id=target,
        actor=Actor.user(user),
        now=NOW,
    )

    set_default_reminder_slots(
        user_id=user, slots=[ReminderSlot.FIVE_DAYS.value], actor=Actor.user(user), now=NOW
    )

    unchanged = get_plan(
        user_id=user, target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT, target_id=target
    )
    assert unchanged.slots == tuple(slot.value for slot in DEFAULT_REMINDER_PLAN)
