"""The published interface over Reminder Plans (AD-16, AD-7, FR-9, FR-20).

`delivery` owns `REMINDER_PLAN`. `personalization` calls **this module** to attach the
default plan when it creates a `PERSONAL_EVENT` (FR-20); it never imports
`apps.delivery.models`, which the import-linter contract `models-delivery` forbids. The
boundary crossing sits on the rare path — personal-event creation — so that "edit the plan,
reschedule its sends" stays inside the module AD-17 makes the sole rewriter of
`SCHEDULED_SEND`.

Three commands, all named and audited (AD-5):

- `attach_default_plan` — the FR-20 default, 1d + 1hr.
- `set_plan_slots` — the FR-9 picker: replace the chosen slots.
- `remove_all_reminders` — FR-9/FR-20: an empty plan is a valid state, not an error.

The plan holds **relative** offsets before the event start, so it survives a postponement:
when AD-17 re-propagates an event's new start, the plan's slots do not change and only the
computed due times move.

Plain data in and out, `now` passed explicitly rather than read from the clock, and no
`request` object — the `apps/ingestion/services/` convention.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction

from apps.delivery.models import ReminderPlan
from apps.delivery.services import slots as slots_rule
from apps.delivery.services.audit import write_audit
from apps.delivery.services.notification_preferences import default_slots_for
from apps.delivery.services.scheduled_sends import (
    SendTarget,
    cancel_sends_for_targets,
    resync_plan,
)
from apps.delivery.services.slots import custom_slot_minutes
from domain.errors import NotFoundError, ValidationError
from shared.actor import Actor
from shared.constants import (
    CUSTOM_SLOT_PREFIX,
    REMINDER_SLOT_OFFSET,
)
from shared.db import PERSONAL

# FR-9's slot rule lives in `slots.py`, not here: `notification_preferences` validates the
# same list for the stored default (FR-20) and this module reads that default, so keeping the
# rule here would make the dependency circular. Re-exported so existing callers and tests that
# import these names from `reminder_plans` keep working.
MAX_SLOTS = slots_rule.MAX_SLOTS
TooManySlotsError = slots_rule.TooManySlotsError
UnknownSlotError = slots_rule.UnknownSlotError
_validate_slots = slots_rule.validate_slots


class ReminderPlanNotFoundError(NotFoundError):
    """The event has no reminder plan."""

    default_message = "We couldn't find that reminder plan."


class UnknownTargetKindError(ValidationError):
    """A target that is neither a personal event nor a saved event."""

    default_message = "That kind of event isn't one we can set reminders for."


@dataclass(frozen=True)
class PlanSlots:
    """A plan's slots, as plain data — the caller never holds a model instance."""

    user_id: UUID
    target_kind: str
    target_id: UUID
    slots: tuple[str, ...]


def _target_kind_value(target_kind: ReminderPlan.TargetKind | str) -> str:
    """The stored kind, rejecting anything that is not one of the two.

    The kind is a closed set, so the command takes the enum member rather than a bare
    string: an invalid kind is then impossible to express, exactly as `Event.Status` is used
    in `apps.ingestion.services.event_writes`.
    """
    if isinstance(target_kind, ReminderPlan.TargetKind):
        return target_kind.value
    try:
        return ReminderPlan.TargetKind(target_kind).value
    except ValueError:
        raise UnknownTargetKindError(details={"target_kind": str(target_kind)}) from None


def _to_plan_slots(plan: ReminderPlan) -> PlanSlots:
    return PlanSlots(
        user_id=plan.user_id,
        target_kind=plan.target_kind,
        target_id=plan.target_id,
        slots=tuple(plan.slots),
    )


def attach_default_plan(
    *,
    user_id: UUID,
    target_kind: ReminderPlan.TargetKind | str,
    target_id: UUID,
    actor: Actor,
    now: datetime,
) -> PlanSlots:
    """Give an event the user's default plan (FR-20).

    **The default is the user's own**, read from `NOTIFICATION_PREFERENCE`, falling back to
    `shared.constants.DEFAULT_REMINDER_PLAN` (1d + 1hr) for a user who has never set one. Until
    `/settings/reminders` existed the constant *was* the default, with no way to change it —
    which is why TRACEABILITY.md could only find FR-20 "by adjacency". The constant is still
    the one literal and is never duplicated (AD-16); it is now the fallback rather than the
    only answer.

    An explicitly empty default is honoured: a user who chose "no reminders by default" gets a
    plan with no slots, which FR-9 makes a valid state ("0 slots = no reminders (still in
    feed)").

    Attaching to an event that already has a plan **replaces** it, so the command is
    idempotent: calling it twice leaves one plan with the same slots.
    """
    kind = _target_kind_value(target_kind)
    slots = default_slots_for(user_id=user_id)
    _validate_slots(slots)
    with transaction.atomic(using=PERSONAL):
        plan, created = ReminderPlan.objects.using(PERSONAL).update_or_create(
            user_id=user_id,
            target_kind=kind,
            target_id=target_id,
            defaults={"slots": list(slots)},
        )
        write_audit(
            actor=actor,
            action="reminder_plan.attached_default",
            target_type=kind,
            target_id=target_id,
            details={"slots": list(slots), "created": created, "at": now.isoformat()},
        )
    return _to_plan_slots(plan)


def set_plan_slots(
    *,
    user_id: UUID,
    target_kind: ReminderPlan.TargetKind | str,
    target_id: UUID,
    slots: tuple[str, ...],
    actor: Actor,
    now: datetime,
    send_target: SendTarget | None = None,
) -> PlanSlots:
    """Replace the event's slots with the user's choice (FR-9).

    An empty tuple is legal: FR-9 says "0 slots = no reminders (still in feed)". The plan row
    stays, holding no slots, so the event keeps its plan identity and the user's "no
    reminders" is distinguishable from "never configured".
    """
    kind = _target_kind_value(target_kind)
    _validate_slots(slots)
    with transaction.atomic(using=PERSONAL):
        try:
            plan = ReminderPlan.objects.using(PERSONAL).get(
                user_id=user_id, target_kind=kind, target_id=target_id
            )
        except ReminderPlan.DoesNotExist:
            raise ReminderPlanNotFoundError(details={"target_id": str(target_id)}) from None
        plan.slots = list(slots)
        plan.save(update_fields=["slots", "updated_at"])
        # The plan and its sends move together or not at all. `send_target` carries the start
        # time and version the keys are minted from, which only the caller knows — `delivery`
        # may not read `apps.personalization.models` (AD-3). A caller that omits it (an
        # internal command with no event in hand) still cancels nothing silently: the plan is
        # the source of truth and `resync_plan` is called by the API that has the target.
        if send_target is not None:
            resync_plan(
                user_id=user_id, target=send_target, slots=tuple(slots), actor=actor, now=now
            )
        write_audit(
            actor=actor,
            action="reminder_plan.slots_set",
            target_type=kind,
            target_id=target_id,
            details={"slots": list(slots), "at": now.isoformat()},
        )
    return _to_plan_slots(plan)


def save_plan_slots(
    *,
    user_id: UUID,
    target_kind: ReminderPlan.TargetKind | str,
    target_id: UUID,
    slots: tuple[str, ...],
    actor: Actor,
    now: datetime,
    send_target: SendTarget,
) -> PlanSlots:
    """Save the event's slots, **attaching the plan when it has none** (FR-9).

    **`set_plan_slots` plus one branch, in one transaction.** The branch exists because
    **a saved public event has no plan at all**: `create_personal_event` calls
    `attach_default_plan` (FR-20), but `save_event` does not. So `set_plan_slots` — which
    raises `ReminderPlanNotFoundError` when the row is missing — would 404 for every saved
    event, and the picker would be dead on arrival for the surface it is built for.

    Attaching first and setting second would be **two transactions**, and the plan's sends
    would move separately from the plan. Here both happen inside one
    `transaction.atomic(using=PERSONAL)`, so the plan and its sends move together or not
    at all — the same guarantee `set_plan_slots` gives, extended to the attach case.

    **`set_plan_slots` itself is unchanged.** Other callers depend on its 404 — a command
    that names an event with no plan is a command that named the wrong event, and a
    silent attach would paper over that.

    `send_target` is **required**, not optional: this is the API's entry point, and the
    target has already been resolved by the caller (which is what proves the target
    exists and is the caller's). The send target carries the start time and version the
    keys are minted from, which only the caller knows — `delivery` may not read
    `apps.personalization.models` (AD-3).
    """
    kind = _target_kind_value(target_kind)
    _validate_slots(slots)
    with transaction.atomic(using=PERSONAL):
        plan, created = ReminderPlan.objects.using(PERSONAL).get_or_create(
            user_id=user_id,
            target_kind=kind,
            target_id=target_id,
            defaults={"slots": list(slots)},
        )
        if not created:
            plan.slots = list(slots)
            plan.save(update_fields=["slots", "updated_at"])
        # The plan and its sends move together or not at all. This is the whole point of
        # the command: a plan saved without its sends changing is a plan that does nothing.
        resync_plan(user_id=user_id, target=send_target, slots=tuple(slots), actor=actor, now=now)
        write_audit(
            actor=actor,
            action="reminder_plan.slots_set",
            target_type=kind,
            target_id=target_id,
            details={"slots": list(slots), "created": created, "at": now.isoformat()},
        )
    return _to_plan_slots(plan)


def remove_all_reminders(
    *,
    user_id: UUID,
    target_kind: ReminderPlan.TargetKind | str,
    target_id: UUID,
    actor: Actor,
    now: datetime,
    send_target: SendTarget | None = None,
) -> PlanSlots:
    """Remove every reminder from the event's plan (FR-9, FR-20).

    The plan row survives with no slots: "no reminders" is a state the user chose, not the
    absence of a plan. Its pending sends are cancelled in the same transaction.
    """
    return set_plan_slots(
        user_id=user_id,
        target_kind=target_kind,
        target_id=target_id,
        slots=(),
        actor=actor,
        now=now,
        send_target=send_target,
    )


def remove_plans_for_targets(
    *,
    user_id: UUID,
    target_kind: ReminderPlan.TargetKind | str,
    target_ids: tuple[UUID, ...],
    actor: Actor,
    now: datetime,
) -> int:
    """Delete the plans of several targets at once, and return how many were removed.

    A calendar disconnect purges the connection's imported events, and every one of them
    carried a plan. `personalization` may not write `REMINDER_PLAN` (AD-16) — it calls this,
    the owner, to do it.

    The plans are **deleted**, not emptied: unlike `remove_all_reminders` — where the user
    chose "no reminders" and the row is the record of that choice — here the target itself is
    gone, so a row holding no slots would be a plan for an event that no longer exists.

    The delete is a single statement, so it is one database round trip for any number of
    targets. A target with no plan is simply not counted; `target_ids` may name events that
    were never given one.

    **One audit row per removed plan** (AD-5: one row per mutation). A bulk command that
    wrote one row would have to name no target, and a row that names no target cannot say
    *what* changed — the audit log's whole job. So each deleted plan gets its own row,
    carrying its target's id. The cost is one row per event on a disconnect, which is the
    same cost the event deletions themselves incur.
    """
    kind = _target_kind_value(target_kind)
    if not target_ids:
        return 0
    with transaction.atomic(using=PERSONAL):
        plans = list(
            ReminderPlan.objects.using(PERSONAL).filter(
                user_id=user_id, target_kind=kind, target_id__in=target_ids
            )
        )
        if not plans:
            return 0
        target_ids_removed = [plan.target_id for plan in plans]
        ReminderPlan.objects.using(PERSONAL).filter(pk__in=[plan.pk for plan in plans]).delete()
        # The target is gone, so its pending sends must go with it — **in this transaction**.
        # A plan deleted without its sends cancelled leaves reminders for an event that no
        # longer exists, and nothing would ever come back to clean them up.
        cancel_sends_for_targets(
            user_id=user_id,
            targets=[(kind, target_id) for target_id in target_ids_removed],
            actor=actor,
            now=now,
        )
        for target_id in target_ids_removed:
            write_audit(
                actor=actor,
                action="reminder_plan.removed_for_target",
                target_type=kind,
                target_id=target_id,
                details={"at": now.isoformat()},
            )
    return len(target_ids_removed)


def get_plan(
    *,
    user_id: UUID,
    target_kind: ReminderPlan.TargetKind | str,
    target_id: UUID,
) -> PlanSlots:
    """The event's plan, or a not-found error when it has none."""
    kind = _target_kind_value(target_kind)
    try:
        plan = ReminderPlan.objects.using(PERSONAL).get(
            user_id=user_id, target_kind=kind, target_id=target_id
        )
    except ReminderPlan.DoesNotExist:
        raise ReminderPlanNotFoundError(details={"target_id": str(target_id)}) from None
    return _to_plan_slots(plan)


def slot_offsets(*, start_utc: datetime, slots: tuple[str, ...]) -> tuple[datetime, ...]:
    """The absolute times of the given slots, each before the event start.

    `shared.constants.REMINDER_SLOT_OFFSET` is the single source of slot → offset
    arithmetic for the named tiers (AD-16), and a custom slot's offset is **in its id** —
    `custom:90` is 90 minutes. Both are read here, so a custom slot is no longer left out
    of the result the way it was when its offset lived nowhere.
    """
    offsets = []
    for slot in slots:
        # `ReminderSlot` is a StrEnum, so its members hash as their string value and the
        # mapping can be looked up by the slot's own value. A custom slot is not a member of
        # the enum, so the lookup simply finds nothing for it — and its own offset is read
        # from its id instead.
        offset = REMINDER_SLOT_OFFSET.get(slot)
        if offset is None:
            minutes = custom_slot_minutes(slot)
            if minutes is None:
                continue
            offset = timedelta(minutes=minutes)
        offsets.append(start_utc - offset)
    return tuple(sorted(offsets))


__all__ = [
    "CUSTOM_SLOT_PREFIX",
    "MAX_SLOTS",
    "PlanSlots",
    "ReminderPlanNotFoundError",
    "TooManySlotsError",
    "UnknownSlotError",
    "UnknownTargetKindError",
    "attach_default_plan",
    "get_plan",
    "remove_all_reminders",
    "remove_plans_for_targets",
    "save_plan_slots",
    "set_plan_slots",
    "slot_offsets",
]
