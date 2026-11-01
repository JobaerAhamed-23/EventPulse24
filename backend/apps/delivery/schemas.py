"""The Reminder Plan and notification-settings wire shapes (AD-19).

Request and response shapes are Pydantic schemas, never ad-hoc dicts. These live in the
`delivery` app because the surface owns the contract; the data comes from
`apps.delivery.services`, which owns the queries and hands over plain data.

**The delivery time is the server's answer, not the client's arithmetic.** Each slot
carries the instant its reminder will *actually* go out — the post-Quiet-Hours instant —
together with a flag saying whether it was deferred and the window end it was deferred
to. The client renders that; it never recomputes it. Shipping the quiet window to the
browser and shifting it there would put a second implementation of the shift in
TypeScript, where DST and midnight-crossing would be rediscovered and got wrong
differently.

**Times are UTC instants.** Display conversion is the frontend's job (AD-6), and the
server does not know what timezone the chip is being rendered in.

**The settings shapes carry wall clocks, not instants.** A Quiet Hours window and a digest
delivery time are *wall clocks* — "22:00 to 08:00" and "09:00" mean nine in the morning
where the user is. They are read in the user's own zone, and a zone-less wall clock is
meaningless, which is why the delivery time arrives **paired with its zone** in one
nested object rather than as two loose fields.
"""

from datetime import datetime, time
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.delivery.services.preferences_read import NotificationSettingsView
from apps.delivery.services.reminder_plan_read import ReminderPlanView, SlotDelivery

#: The two kinds of personal-side record a plan can belong to. `ReminderPlan.TargetKind`'s
#: vocabulary, spelled as a `Literal` so a client generated from this schema cannot send
#: a third kind — the server would refuse it anyway, but the generated type says so first.
TargetKind = Literal["personal_event", "saved_event"]


class ReminderSlotDeliveryOut(Schema):
    """One slot, and when its reminder will actually go out.

    `delivery_at` is the **post-Quiet-Hours** instant: the true send time, the same one
    stored in the send's `due_at`. A slot whose moment has already passed still carries
    its instant — the picker shows what the plan says, and the client decides whether a
    past instant is worth rendering differently.

    `deferred` says whether Quiet Hours moved it. `deferred_to` is the **window's end**
    when it did, and `None` when it did not — the tooltip reads *"Will deliver at {end of
    quiet hours}"*, so the client needs that instant and nothing else.

    `delivery_at` is `None` only for a slot with no computable offset, which the plan's
    own validator refuses on write; it is defensive, not expected.
    """

    slot: str
    delivery_at: datetime | None = None
    deferred: bool
    deferred_to: datetime | None = None

    @classmethod
    def from_delivery(cls, delivery: SlotDelivery) -> "ReminderSlotDeliveryOut":
        """Project the service's plain data onto the wire shape."""
        return cls(
            slot=delivery.slot,
            delivery_at=delivery.delivery_at,
            deferred=delivery.deferred,
            deferred_to=delivery.deferred_to,
        )


class ReminderPlanOut(Schema):
    """One event's Reminder Plan, with each slot's computed delivery time.

    `slots` is the stored list in the stored order, and `deliveries` carries one entry
    per slot in the same order — the picker renders them together, so the two lists
    cannot disagree.
    """

    target_kind: TargetKind
    target_id: UUID
    slots: list[str]
    deliveries: list[ReminderSlotDeliveryOut]

    @classmethod
    def from_view(cls, view: ReminderPlanView) -> "ReminderPlanOut":
        """Project the read's plain data onto the wire shape."""
        return cls(
            target_kind=view.target_kind,
            target_id=view.target_id,
            slots=list(view.slots),
            deliveries=[
                ReminderSlotDeliveryOut.from_delivery(delivery) for delivery in view.deliveries
            ],
        )


class ReminderPlanIn(Schema):
    """The plan to save.

    **0 to 4 slots**, and at most one custom slot. **Zero is a valid save** — FR-9: *"0
    slots = no reminders (still in feed)"* — and it is not a delete: the plan row
    survives, so "the user chose no reminders" stays distinguishable from "the user never
    configured a plan".

    **A custom slot's id carries its offset**: `custom:90` is 90 minutes before the
    event. The bound is the product's — **15 minutes to 30 days** before the event, from
    EXPERIENCE.md — and an out-of-range offset is refused rather than snapped here; the
    client snaps it back, and the server refuses it either way.
    """

    slots: list[str] = Field(
        default_factory=list,
        description=(
            "The reminder slots to save: 0 to 4 of `5d`, `2d`, `1d`, `1hr`, plus at most "
            "one custom slot. A custom slot is `custom:<minutes>`, where `<minutes>` is "
            "an integer from 15 (fifteen minutes before the event) to 43200 (thirty "
            "days before the event). An empty list is valid and means 'no reminders'."
        ),
    )


# ── The notification settings ────────────────────────────────────────────────────


class QuietHoursOut(Schema):
    """The Quiet Hours window — two local wall clocks.

    `start` and `end` are **wall clocks in the user's own zone**, not instants. A window
    that crosses midnight is the normal case, not a special one: `22:00` to `08:00` means
    the night, and the server does the arithmetic.

    The window is `null` on the wire when the user has turned quiet hours **off** — and
    only then. "Never configured" is not a state the window can hold, because reading the
    preference creates it with the defaults.
    """

    start: time
    end: time


class DigestScheduleOut(Schema):
    """When and where the daily digest is due.

    `delivery_time` is a **local wall clock** — "09:00" means nine in the morning where the
    user is — and `timezone` is the IANA zone it is a clock in. They are one object because
    they are one fact: a clock without its zone is not a schedule.
    """

    delivery_time: time
    timezone: str


class NotificationSettingsOut(Schema):
    """One user's notification settings — all four facts, in one response.

    **One call, one response.** The window and the default slots live on `delivery`'s
    `NotificationPreference`; the delivery time and the zone live on `personalization`'s
    `DigestPreference`. The split is real and the client should never see it.
    """

    quiet_hours: QuietHoursOut | None
    default_reminder_slots: list[str]
    digest: DigestScheduleOut

    @classmethod
    def from_view(cls, view: NotificationSettingsView) -> "NotificationSettingsOut":
        """Project the read's plain data onto the wire shape."""
        window = view.quiet_hours
        return cls(
            quiet_hours=(
                QuietHoursOut(start=window.start, end=window.end) if window is not None else None
            ),
            default_reminder_slots=list(view.default_reminder_slots),
            digest=DigestScheduleOut(delivery_time=view.delivery_time, timezone=view.timezone),
        )


class QuietHoursIn(Schema):
    """A Quiet Hours window to save — two local wall clocks.

    **A full-day window is refused.** `start == end` means "quiet all day", which is not a
    window but the absence of one, and it is the same statement spelled differently from
    "no quiet hours" — so it is refused rather than stored, and "off" has exactly one
    spelling on the wire (`null`).
    """

    start: time = Field(description="When quiet hours begin, as a local wall clock.")
    end: time = Field(description="When quiet hours end, as a local wall clock.")


class DigestScheduleIn(Schema):
    """The digest delivery time and the zone it is a clock in.

    **Both or neither.** A wall clock without its zone is not a schedule, so the two cannot
    be changed apart and cannot be half-applied.
    """

    delivery_time: time = Field(description="When the daily digest is due, as a local wall clock.")
    timezone: str = Field(description="The IANA zone the delivery time is a clock in.")


class NotificationSettingsIn(Schema):
    """The settings to save — **only the ones mentioned**.

    **Every field is optional, and an omitted field means "leave it alone".** This is a
    patch, not a replacement: a client that changes the quiet hours must not clear the
    default plan, and a client that only moves the delivery time must not reset the
    window.

    **`quiet_hours` is the one field where `null` is a value.** An omitted
    `quiet_hours` leaves the window alone; a `null` one turns quiet hours **off**. The
    two are told apart by the field's *presence in the request*, not by a sentinel, and
    the distinction survives because the server reads which fields the client actually
    sent.

    **The default slots are validated by the same validator the per-event plan uses** — the
    same 0-to-4 rule, the same named tiers, the same custom-slot grammar, the same errors.
    An empty list is valid and means "new plans start with no reminders".
    """

    quiet_hours: QuietHoursIn | None = Field(
        default=None,
        description=(
            "The Quiet Hours window, as two local wall clocks. **Omit this field to leave "
            "the window alone; send `null` to turn quiet hours off.** A full-day window "
            "(the same clock twice) is refused."
        ),
    )
    default_reminder_slots: list[str] | None = Field(
        default=None,
        description=(
            "The reminder slots a newly attached plan starts with: 0 to 4 of `5d`, `2d`, "
            "`1d`, `1hr`, plus at most one custom slot (`custom:<minutes>`, 15 minutes to "
            "30 days before the event). **Omit this field to leave the default alone**; "
            "an empty list means 'no reminders by default'. Changing it does not alter "
            "plans that already exist."
        ),
    )
    digest: DigestScheduleIn | None = Field(
        default=None,
        description=(
            "When and where the daily digest is due. **Omit this field to leave it "
            "alone.** The delivery time is a local wall clock and the timezone is the "
            "IANA zone it is a clock in; both are required together."
        ),
    )
