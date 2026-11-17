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

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.delivery.services.notice_state import NoticeSummary
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


class QuietHoursOverrideOut(Schema):
    """One weekday's quiet-hours window, as stored (FR-51).

    `weekday` is **Monday 0 through Sunday 6** — `date.weekday()`, the same numbering the
    domain and the table use, because a second numbering is a conversion waiting to be got
    wrong.

    **These are the windows the user stored, not necessarily the ones in force.** A lapsed
    Pro account still has its seven here, because they are the user's own data and are never
    deleted. What is actually applied is `effective_quiet_hours`.
    """

    weekday: int
    start: time
    end: time


class EffectiveQuietHoursOut(Schema):
    """One weekday of the schedule the delivery path will actually use (FR-51).

    **Read-only, and derived.** It is the base window with a Pro account's overrides laid
    over it; for a Free or lapsed account it is the base window on all seven days whatever
    `quiet_hours_overrides` holds. It exists so a lapsed user is never shown seven windows
    that are not in force — the one honest answer to "when will I actually be quiet".

    `quiet_hours` is `null` on a day with no quiet hours at all.
    """

    weekday: int
    quiet_hours: QuietHoursOut | None


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
    #: The per-weekday overrides as stored. Empty for an account that has never set any.
    quiet_hours_overrides: list[QuietHoursOverrideOut]
    #: **Read-only.** Seven entries, Monday first: what the scheduler will actually apply.
    effective_quiet_hours: list[EffectiveQuietHoursOut]
    default_reminder_slots: list[str]
    digest: DigestScheduleOut
    #: Whether the daily Pulse Ping is on (FR-10). `true` for a user who has never
    #: turned it off, which is the default and the common case.
    pulse_ping: bool

    @classmethod
    def from_view(cls, view: NotificationSettingsView) -> "NotificationSettingsOut":
        """Project the read's plain data onto the wire shape."""
        window = view.quiet_hours
        effective = view.effective_quiet_hours
        return cls(
            quiet_hours=(
                QuietHoursOut(start=window.start, end=window.end) if window is not None else None
            ),
            quiet_hours_overrides=[
                QuietHoursOverrideOut(weekday=weekday, start=override.start, end=override.end)
                for weekday, override in sorted(view.quiet_hours_overrides.items())
            ],
            effective_quiet_hours=[
                EffectiveQuietHoursOut(
                    weekday=weekday,
                    quiet_hours=(
                        QuietHoursOut(start=day.start, end=day.end) if day is not None else None
                    ),
                )
                for weekday, day in enumerate(effective.windows)
            ],
            default_reminder_slots=list(view.default_reminder_slots),
            digest=DigestScheduleOut(delivery_time=view.delivery_time, timezone=view.timezone),
            pulse_ping=view.pulse_ping,
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


class QuietHoursOverrideIn(Schema):
    """One weekday's quiet-hours window to save (FR-51).

    `weekday` is Monday 0 through Sunday 6. A full-day window (`start == end`) is refused
    here exactly as it is for the base window, and **the whole list is validated before any
    of it is written**, so a bad seventh window does not leave six applied.
    """

    weekday: int = Field(ge=0, le=6, description="Monday 0 through Sunday 6.")
    start: time = Field(description="When quiet hours begin that day, as a local wall clock.")
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
    quiet_hours_overrides: list[QuietHoursOverrideIn] | None = Field(
        default=None,
        description=(
            "A quiet-hours window per weekday — **a Pro feature**. Omit this field to "
            "leave your per-day windows alone; send `[]` to remove them all and go back "
            "to one window for the whole week. The list **replaces** your weekdays rather "
            "than merging into them, and the whole week is applied in one transaction. A "
            "Free account sending a non-empty list is refused with an upgrade hint."
        ),
    )
    pulse_ping: bool | None = Field(
        default=None,
        description=(
            "Whether the daily **Pulse Ping** should be on. **Omit this field to leave it "
            "alone**; send `true` to turn the Ping on and `false` to turn it off.\n\n"
            "**Turning it off cancels the digest sends already pending for you**, so the "
            "mail you just turned off is not delivered afterwards — and it leaves every "
            "reminder plan alone. The two scopes never touch: this is the daily digest, "
            "not your event reminders.\n\n"
            "**Turning it back on does not resurrect what was cancelled.** Those sends "
            "were for days that have passed; the next one is minted fresh."
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


# ── The state-change notices (FR-54) and the per-event mute (FR-55) ──────────────


class NoticeOut(Schema):
    """One state-change notice, as the digest strip shows it.

    **The notice's own facts, and no more.** The server states what changed and what it
    means; the client renders it. The change's *content* — the before/after values — is
    deliberately absent: it is source payload, and it is the one place a title or a venue
    name could leak into a response (AD-13). `change_kind` is the vocabulary
    `domain.lifecycle.ChangeKind` defines, carried through unchanged.

    **`event_id` is the catalog event's id, by value.** The client routes to the event's
    page, and the notice row holds no relation to the catalog (AD-3).

    **`seen_at` and `dismissed_at` are the two different acts.** `seen_at` is when the
    notice was put in front of the user — not an act by them. `dismissed_at` is when they
    closed it. A notice can be seen and not dismissed, and a client that cannot tell them
    apart would render a dismissed notice as still open.

    **(Today, a dismissal sets both — but the strip's read deliberately does not mark
    notices seen.** A `GET` that writes is the shape CSRF exists to stop, and
    `apps/personalization/detail_api.py` refuses it for the Detail Screen. So `seen_at` is
    `None` until the user closes the notice. The two stay separate fields because the
    moment something *does* mark a notice seen on render, they will say different things.

    **`dismissed_at` is `None` on every notice the strip returns**, because the strip is
    the queue of *open* notices. It is on the wire anyway so the same shape serves the
    Detail banner, which deliberately reports a dismissed notice too.
    """

    #: The notice's own id. The dismiss endpoint names it.
    id: UUID
    #: The catalog event's id, by value (AD-3). The client routes to it.
    event_id: UUID
    #: `domain.lifecycle.ChangeKind`'s vocabulary, carried through unchanged.
    change_kind: str
    #: The event version the change carried.
    event_version: int
    #: The user's local date when the notice was raised — what the one-per-day cap is
    #: keyed on.
    local_date: date
    #: When the notice was first put in front of the user, or `None` if it never was.
    seen_at: datetime | None = None
    #: When the user closed it, or `None` while it is still open.
    dismissed_at: datetime | None = None
    #: When the notice was raised. The strip orders by this, newest first.
    created_at: datetime

    @classmethod
    def from_summary(cls, summary: NoticeSummary) -> "NoticeOut":
        """Project the service's plain data onto the wire shape."""
        return cls(
            id=summary.id,
            event_id=summary.event_id,
            change_kind=summary.change_kind,
            event_version=summary.event_version,
            local_date=summary.local_date,
            seen_at=summary.seen_at,
            dismissed_at=summary.dismissed_at,
            created_at=summary.created_at,
        )


class NoticeListOut(Schema):
    """The signed-in user's open notices, newest first.

    **A list, and nothing else.** There is no total, no `next` cursor, no page — the strip
    shows a few and there is no inbox to page through (FR-54). A `total` would invite the
    client to build an inbox, and an inbox is how "one calm correction" becomes a
    notification centre.

    **`items` is empty, not absent, when the user has no open notices.** An empty list is
    the shape; `None` would be a second spelling of the same fact.
    """

    #: The open notices, newest first, at most `NOTICE_STRIP_LIMIT` of them.
    items: list[NoticeOut] = []


class NoticeDismissOut(Schema):
    """The outcome of dismissing one notice.

    **`dismissed` and `changed` are two different facts, and the client needs both.**
    `dismissed` is the notice's *state* — it is dismissed now. `changed` says whether
    **this call** is what made it so.

    **The distinction is what makes an idempotent write honest.** Dismissing an
    already-dismissed notice is a success, not an error — but a response that claimed
    `changed: true` for it would tell the screen to redraw something that did not move.
    `changed: false` says "it was already dismissed; nothing changed", which is the truth
    and is also what lets the client skip the redraw.

    **The same shape as the mute's** (`EventMuteOut`), because both are "a state and
    whether this call moved it".
    """

    #: The notice's id — the one that was named.
    id: UUID
    #: The notice's state: it is dismissed.
    dismissed: bool = True
    #: Whether **this call** is what dismissed it. False when it was already dismissed.
    changed: bool = False


class EventMuteOut(Schema):
    """The outcome of muting or unmuting one event's state-change notices.

    **It mirrors `MuteResult` exactly**, because that dataclass already carries the two
    facts the client needs and no third: `muted` is the event's *state* after the call,
    and `changed` says whether **this call** moved it.

    **Muting an already-muted event is a success, not an error** — and `changed: false` is
    what says so honestly. A client that redrew on `changed` would redraw a control that
    did not move.

    **`event_id` is in the response** so the client can confirm which event the answer is
    about, without having to trust that the request and the response were about the same
    thing.

    **This says nothing about the event itself.** A mute silences the correction, not the
    event: reminders still fire on the user's Reminder Plan and the event still places in
    the Pulse Digest (FR-55). The shape carries no field that could be read as "the event
    is off".
    """

    #: The catalog event's id, by value (AD-3).
    event_id: UUID
    #: Whether the event's notices are muted now. False after an unmute.
    muted: bool
    #: Whether **this call** moved the state. False when it was already there.
    changed: bool
