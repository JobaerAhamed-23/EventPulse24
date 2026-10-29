"""The Reminder Plan and its audit log (AD-16, AD-7, FR-9, FR-20).

`delivery` owns `REMINDER_PLAN`. `personalization` never writes this table: it calls
`delivery`'s published service (`apps.delivery.services.reminder_plans`) to attach the
default plan when it creates a `PERSONAL_EVENT`. The import-linter contract
`models-delivery` enforces that boundary at build time.

The plan holds **relative** offsets before the event start, never absolute times, so it
survives a postponement: when AD-17 re-propagates an event's new start, the plan's slots
are unchanged and only the computed due times move.

The plan is attached to the *personal-side* record it belongs to, by value. A saved public
event's catalog row lives in the `catalog` schema and AD-3 forbids a FK across that wall;
both target tables here live in `personal`, so `(target_kind, target_id)` needs no relation
at all.
"""

from django.db import models
from django.db.models.expressions import RawSQL

from shared.models import AuditEntry, UUIDv7Model
from shared.retention import RetentionCategory

# FR-9's "up to 4" bound, as a Postgres expression. Django's `__len` transform does not do
# this: on a JSON *array* it renders `(slots -> 'len') <= '4'`, which reads a key named
# "len" and yields NULL for every array — and a CHECK that evaluates to NULL passes. The
# array's element count is `jsonb_array_length`, which is what the bound actually means.
SLOTS_MAX = 4
_SLOTS_LENGTH_AT_MOST_4 = models.Q(
    RawSQL(
        "jsonb_array_length(slots) <= %s",
        (SLOTS_MAX,),
        output_field=models.BooleanField(),
    )
)


class ReminderPlan(UUIDv7Model):
    """One user's reminder slots for one event (FR-9).

    A user can save a plan with **0 to 4** slots (FR-9: "0 slots = no reminders (still in
    feed)"; FR-20: "The user can remove all reminders"). An empty plan is a valid state,
    not an error.

    The slots are the values `5d`, `2d`, `1d`, `1hr` — the `shared.constants.ReminderSlot`
    enum, reused and never redeclared (AD-16) — plus at most one custom slot, whose id is
    the user's own. AD-7's send key names the slot as "the custom slot's id", so a slot is
    a *value*, not an offset: the offset arithmetic lives in one place,
    `shared.constants.REMINDER_SLOT_OFFSET`.

    Pulse Ping is **not** a slot. The PRD Glossary is explicit: "Pulse Ping is NOT part of
    any Reminder Plan" — it is a separate, global per-day notification (FR-10). Nothing in
    this model can express it.
    """

    class TargetKind(models.TextChoices):
        """Which kind of personal-side record the plan belongs to.

        A plan attaches to a personal event (FR-20) or to a saved public event (FR-9's
        picker). The kind is stored beside the id because a UUID alone cannot say what it
        refers to — the same reasoning as `ConflictPair.SideKind`.
        """

        PERSONAL_EVENT = "personal_event"
        SAVED_EVENT = "saved_event"

    retention_category = RetentionCategory.ACCOUNT_CONTENT

    # The user, by value (OQ-8): no relation to User, no GenericForeignKey.
    user_id = models.UUIDField()
    # The personal-side record the plan belongs to, by value. `target_id` is the id of a
    # `personalization` row in the `personal` schema — never a catalog Event, which lives
    # behind the AD-3 wall.
    target_kind = models.CharField(max_length=16, choices=TargetKind.choices)
    target_id = models.UUIDField()
    # The chosen slots, in order. At most 4 (FR-9). Each is a `ReminderSlot` value or a
    # custom slot id.
    slots = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # One plan per event: re-attaching updates the row rather than adding another.
            models.UniqueConstraint(
                fields=["user_id", "target_kind", "target_id"], name="reminder_plan_target_uq"
            ),
            # FR-9's "up to 4". The list is a JSON array, so the bound is a length check.
            models.CheckConstraint(
                condition=_SLOTS_LENGTH_AT_MOST_4, name="reminder_plan_slots_max_4_ck"
            ),
        ]
        indexes = [
            # The scheduler finds every plan of one user; AD-7's sweep reads them per user.
            models.Index(fields=["user_id"], name="reminder_plan_user_idx"),
        ]

    def __str__(self) -> str:
        slots = ", ".join(self.slots) if self.slots else "none"
        return f"{self.target_kind} plan [{slots}]"


class DeliveryAuditEntry(AuditEntry):
    """The `delivery` audit log (AD-5). Append-only; written only through `write_audit`."""

    retention_category = RetentionCategory.AUDIT_LOG
