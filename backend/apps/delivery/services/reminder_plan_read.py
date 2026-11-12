"""The published read of one event's Reminder Plan, with its **computed delivery times**.

**What this module exists for.** The picker has to dim a chip whose reminder falls inside
Quiet Hours and show *"Will deliver at 8:00 am Saturday"* — and it cannot compute that
itself. Shipping the quiet window to the browser and shifting it there would put a second
implementation of the shift in TypeScript, where DST and midnight-crossing would be
rediscovered and got wrong differently. The server already knows; let it say (AD-16, AD-7).

**So the shift happens here, server-side, and the client renders the answer.** The
client's job is to *render* a dimmed chip and a tooltip; it is never asked to decide
whether an instant is inside a window.

**The three facts this read needs, and where each comes from:**

- **the event's start and version** — `personalization`'s published reads
  (`get_personal_event`, `get_saved_event`). AD-3: `delivery` reads the other side's
  models through its published service, never by importing them.
- **the user's zone** — `personalization.services.digest_preferences.get_delivery_settings`,
  the same read the minting path uses.
- **the user's quiet window** — `delivery.services.notification_preferences.get_preference`.
  The window is `delivery`'s own row, on the hot path.

**The query count is bounded and independent of the slot count.** The plan is one query,
the preference one, the zone one, the target one — and the per-slot delivery times are
computed **in Python** over those facts, not with a query per slot. Four slots cost the
same four queries as one.

**`deferred_to` is `delivery_at` when deferred, and `None` otherwise.** That is not a
convenience — it is what `shift_to_sendable` already guarantees. The shift returns *the
window's end* when it defers, and the window's end is the instant the send goes out. So
there is one instant, not two, and no second computation of "which day does this window
end on" — which `shift_to_sendable` owns and would have to be duplicated to answer
separately.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.delivery.models import ReminderPlan
from apps.delivery.services.notification_preferences import get_preference
from apps.delivery.services.scheduled_sends import SendTarget, slot_due_at, slot_offset
from domain.quiet_hours import Window
from shared.constants import DEFAULT_DIGEST_TIMEZONE
from shared.db import PERSONAL

#: The kind of personal-side record a plan is about. `ReminderPlan.TargetKind`'s two
#: values, in the tree's own vocabulary — **not** `ScheduledSend.Kind`, which is a
#: different enumeration (a send's kind says whether it is a digest, an event reminder or
#: a personal reminder; a plan's kind says which side of the user's calendar the plan
#: belongs to). `delivery_messages._facts_for` already tabulates the two.
TargetKind = str


@dataclass(frozen=True)
class SlotDelivery:
    """One slot, and when its reminder will actually go out.

    `delivery_at` is the **post-Quiet-Hours** instant — the true send time, the same one
    the minting path stores in `due_at`. `deferred` says whether the shift moved it, and
    `deferred_to` is the window's end when it did.

    `delivery_at` is `None` for a slot with no computable offset — a malformed custom
    slot id. The plan's own validator refuses such a slot on write, so this is a
    defensive branch rather than an expected state.
    """

    slot: str
    delivery_at: datetime | None
    deferred: bool
    deferred_to: datetime | None


@dataclass(frozen=True)
class ReminderPlanView:
    """The plan, its target, and each slot's computed delivery time.

    `slots` is the stored list, in the stored order — the order the user chose, which is
    the order the picker renders.
    """

    user_id: UUID
    target_kind: TargetKind
    target_id: UUID
    slots: tuple[str, ...]
    deliveries: tuple[SlotDelivery, ...]


class ReminderTargetNotFoundError(Exception):
    """The named target does not exist, is not the caller's, or is of the other kind.

    **Not a `NotFoundError` subclass on purpose** — the API layer raises the shared
    404 envelope itself, and this module stays free of the HTTP layer's vocabulary. The
    message says nothing about what exists: a 404 must not confirm that another user's
    event is there (no existence leak).
    """


def _zone_for(user_id: UUID) -> str:
    """The user's IANA zone, read through `personalization`'s published interface (AD-3).

    Falls back to `DEFAULT_DIGEST_TIMEZONE` rather than guessing: a guessed zone shows a
    reminder at the wrong hour, and looks like a bug in the reminder rather than in the
    guess. This is the same read — and the same fallback — the minting path uses, so the
    time the picker shows is the time the send gets.
    """
    from apps.personalization.services.digest_preferences import get_delivery_settings

    settings = get_delivery_settings(user_id=user_id)
    return settings.timezone if settings else DEFAULT_DIGEST_TIMEZONE


def _resolve_target(*, user_id: UUID, target_kind: TargetKind, target_id: UUID) -> SendTarget:
    """Resolve the target into the `SendTarget` the minting service needs.

    **The target is resolved *first*, before anything is written.** A caller can name
    `(target_kind="saved_event", target_id=<a personal event's id>)`. The plan row is
    unique on `(user_id, target_kind, target_id)`, so that would be a well-formed row
    about a nonsense target — and its sends would be minted with the wrong kind's key.

    The resolution is what produces the `SendTarget` the minting service needs anyway
    (the start instant, the version, the catalog event id), so **the validation is free**:
    there is no separate "is this target real?" check to drift from the read.

    A target that is missing, un-saved, or of the other kind is the same refusal: a
    `ReminderTargetNotFoundError`. The API turns it into the shared 404 envelope.
    """
    if target_kind == ReminderPlan.TargetKind.PERSONAL_EVENT:
        from apps.personalization.services.personal_events import (
            PersonalEventNotFoundError,
            get_personal_event,
        )

        try:
            event = get_personal_event(user_id=user_id, event_id=target_id)
        except PersonalEventNotFoundError:
            raise ReminderTargetNotFoundError from None
        return SendTarget(
            target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT.value,
            target_id=event.id,
            start_utc=event.start_utc,
            version=event.version,
        )

    if target_kind == ReminderPlan.TargetKind.SAVED_EVENT:
        from apps.personalization.services.saved_events import (
            SavedEventNotFoundError,
            get_saved_event,
        )

        try:
            saved = get_saved_event(user_id=user_id, event_id=target_id)
        except SavedEventNotFoundError:
            raise ReminderTargetNotFoundError from None
        # A saved event's `target_id` is the **catalog** event's id — the tree's convention
        # (see `delivery_messages._public_event_facts` and `send_keys.event_reminder_key`).
        # `catalog_event_id` is what the send key is minted from, so the key names the
        # catalog event while the plan's own `target_id` names the save's target.
        return SendTarget(
            target_kind=ReminderPlan.TargetKind.SAVED_EVENT.value,
            target_id=target_id,
            start_utc=saved.start_utc,
            version=saved.event_version,
            catalog_event_id=target_id,
        )

    raise ReminderTargetNotFoundError


def resolve_target(*, user_id: UUID, target_kind: TargetKind, target_id: UUID) -> SendTarget:
    """The target as the minting service needs it. Published for the write path too.

    The read and the write resolve the target through **this one function**, so a plan
    cannot be read for a target the write would refuse — the two can never disagree about
    what a target is.
    """
    return _resolve_target(user_id=user_id, target_kind=target_kind, target_id=target_id)


def compute_deliveries(
    *,
    slots: tuple[str, ...],
    start_utc: datetime,
    zone: str,
    window: Window | None,
) -> tuple[SlotDelivery, ...]:
    """Each slot's post-Quiet-Hours delivery time, in the plan's stored order.

    **The shift is applied here and only here.** `slot_due_at` is the same published
    function the minting path uses, so the time the picker shows is the time the send
    gets — by construction, not by two implementations agreeing.

    `deferred` is decided by comparing the shifted instant with the unshifted one, and
    `deferred_to` is the shifted instant — because the shift returns **the window's end**
    when it defers. There is one instant, not two.
    """
    deliveries = []
    for slot in slots:
        offset = slot_offset(slot)
        if offset is None:
            # A slot with no offset has no delivery time. The validator refuses such a slot
            # on write, so this is defensive — and the answer is "no time", never a guess.
            deliveries.append(
                SlotDelivery(slot=slot, delivery_at=None, deferred=False, deferred_to=None)
            )
            continue
        shifted = slot_due_at(start_utc=start_utc, slot=slot, zone=zone, window=window)
        # The unshifted instant: the same arithmetic without the Quiet Hours window. It is
        # computed here rather than asked of `shift_to_sendable` because the shift's
        # contract is "the instant to send", not "the instant to send and whether it
        # moved" — asking it for both would be a second rule.
        base = start_utc - offset
        deferred = shifted != base
        deliveries.append(
            SlotDelivery(
                slot=slot,
                delivery_at=shifted,
                deferred=deferred,
                deferred_to=shifted if deferred else None,
            )
        )
    return tuple(deliveries)


def read_plan(
    *,
    user_id: UUID,
    target_kind: TargetKind,
    target_id: UUID,
) -> ReminderPlanView:
    """The user's plan for one event, with each slot's computed delivery time.

    **A plan that does not exist is an empty plan, not a 404.** The picker's empty state
    reads *"No reminders. You'll still see this event in Pulse Digest."* — and FR-9's *"0
    slots = no reminders (still in feed)"* means "no plan" and "a plan with no slots" are
    the same thing to the user. The `PUT` attaches the plan when it is missing, so the
    picker can render the empty state and then save into it.

    The target is still resolved — so a target that does not exist, or is not the
    caller's, or is of the other kind, is a 404 rather than an empty plan for a
    nonsense target.
    """
    target = _resolve_target(user_id=user_id, target_kind=target_kind, target_id=target_id)
    return read_plan_for(
        user_id=user_id,
        target_kind=target_kind,
        target_id=target_id,
        target=target,
    )


def read_plan_for(
    *,
    user_id: UUID,
    target_kind: TargetKind,
    target_id: UUID,
    target: SendTarget,
) -> ReminderPlanView:
    """The plan, read against a target the caller has **already resolved**.

    **This is the write path's read-back.** The `PUT` resolves the target first — it has
    to, because the `SendTarget` is what the minting service needs — and then reads the
    saved plan back so the response carries the delivery times the next `GET` would.
    Resolving it a second time would re-read the event, the preference and the zone for
    facts the write already had, so the write path comes here instead.

    The plan itself is still read from the database: the read-back is about what was
    **saved**, and the plan row is what was saved.
    """
    plan = (
        ReminderPlan.objects.using(PERSONAL)
        .filter(user_id=user_id, target_kind=target_kind, target_id=target_id)
        .first()
    )
    slots = tuple(plan.slots) if plan is not None else ()

    preference = get_preference(user_id=user_id)
    zone = _zone_for(user_id)
    deliveries = compute_deliveries(
        slots=slots,
        start_utc=target.start_utc,
        zone=zone,
        window=preference.effective_quiet_hours,
    )
    return ReminderPlanView(
        user_id=user_id,
        target_kind=target_kind,
        target_id=target_id,
        slots=slots,
        deliveries=deliveries,
    )


__all__ = [
    "ReminderPlanView",
    "ReminderTargetNotFoundError",
    "SlotDelivery",
    "TargetKind",
    "compute_deliveries",
    "read_plan",
    "read_plan_for",
    "resolve_target",
]
