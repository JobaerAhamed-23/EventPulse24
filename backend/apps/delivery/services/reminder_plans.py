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
from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.delivery.models import ReminderPlan
from apps.delivery.services.audit import write_audit
from domain.errors import NotFoundError, ValidationError
from shared.actor import Actor
from shared.constants import (
    CUSTOM_SLOT_PREFIX,
    DEFAULT_REMINDER_PLAN,
    REMINDER_PLAN_MAX_SLOTS,
    REMINDER_SLOT_OFFSET,
    ReminderSlot,
)
from shared.db import PERSONAL

# FR-9: "up to 4 reminder slots". The database enforces the same bound
# (`reminder_plan_slots_max_4_ck`); the service checks it too, so the rule reads in one place
# and the caller gets a readable error instead of a database error.
MAX_SLOTS = REMINDER_PLAN_MAX_SLOTS

# The four named tiers, by value. A custom slot is identified by its own id and is not a
# member of the enum, so it is looked up separately.
_NAMED_SLOTS = frozenset(slot.value for slot in ReminderSlot)


class ReminderPlanNotFoundError(NotFoundError):
    """The event has no reminder plan."""

    default_message = "We couldn't find that reminder plan."


class TooManySlotsError(ValidationError):
    """More than FR-9's four slots were requested."""

    default_message = f"A reminder plan holds at most {MAX_SLOTS} reminders."


class UnknownSlotError(ValidationError):
    """A slot that is neither a named tier nor a custom slot id."""

    default_message = "That reminder time isn't one we recognise."


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


def _validate_slots(slots: tuple[str, ...]) -> None:
    if len(slots) > MAX_SLOTS:
        raise TooManySlotsError(details={"max_slots": MAX_SLOTS, "given": len(slots)})
    for slot in slots:
        # A named tier, or a custom slot: the user's own id (AD-7's send key names the custom
        # slot by id). A custom slot is identified by a prefix, so it can never be mistaken
        # for one of the four named tiers.
        if slot in _NAMED_SLOTS:
            continue
        if not slot.startswith(CUSTOM_SLOT_PREFIX):
            raise UnknownSlotError(details={"slot": slot})
    if len(set(slots)) != len(slots):
        raise ValidationError("A reminder plan holds each slot once.")


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
    """Give an event the default plan — 1d + 1hr (FR-20).

    FR-9 and FR-20 share one default, `shared.constants.DEFAULT_REMINDER_PLAN`; it is never a
    second literal (AD-16). Attaching to an event that already has a plan **replaces** it with
    the default, so the command is idempotent: calling it twice leaves one plan with the
    default slots.
    """
    kind = _target_kind_value(target_kind)
    slots = tuple(slot.value for slot in DEFAULT_REMINDER_PLAN)
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
        write_audit(
            actor=actor,
            action="reminder_plan.slots_set",
            target_type=kind,
            target_id=target_id,
            details={"slots": list(slots), "at": now.isoformat()},
        )
    return _to_plan_slots(plan)


def remove_all_reminders(
    *,
    user_id: UUID,
    target_kind: ReminderPlan.TargetKind | str,
    target_id: UUID,
    actor: Actor,
    now: datetime,
) -> PlanSlots:
    """Remove every reminder from the event's plan (FR-9, FR-20).

    The plan row survives with no slots: "no reminders" is a state the user chose, not the
    absence of a plan.
    """
    return set_plan_slots(
        user_id=user_id,
        target_kind=target_kind,
        target_id=target_id,
        slots=(),
        actor=actor,
        now=now,
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
    arithmetic (AD-16). A custom slot has no offset here — the caller supplies its own — so
    it is left out of the result rather than guessed at.
    """
    offsets = []
    for slot in slots:
        # `ReminderSlot` is a StrEnum, so its members hash as their string value and the
        # mapping can be looked up by the slot's own value. A custom slot is not a member of
        # the enum, so the lookup simply finds nothing for it.
        offset = REMINDER_SLOT_OFFSET.get(slot)
        if offset is not None:
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
    "set_plan_slots",
    "slot_offsets",
]
