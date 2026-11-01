"""factory_boy factories for the `delivery` models. Deterministic: fixed UTC instants, seeded
Faker, sequences for every unique value.
"""

from datetime import UTC, datetime

import factory
import factory.random
from factory.django import DjangoModelFactory

from apps.delivery.models import DeliveryAuditEntry, ReminderPlan, ScheduledSend
from apps.delivery.send_keys import event_reminder_key
from ports.email import Stream
from shared.db import PERSONAL
from shared.ids import uuid7

factory.random.reseed_random("eventpulse24-delivery")


class DeliveryFactory(DjangoModelFactory):
    """Writes on the personal alias explicitly, never through the router's default.

    `skip_postgeneration_save` stops factory_boy's second `save()`, which the append-only
    audit model rejects.
    """

    class Meta:
        abstract = True
        database = PERSONAL
        skip_postgeneration_save = True


class ReminderPlanFactory(DeliveryFactory):
    class Meta:
        model = ReminderPlan

    user_id = factory.LazyFunction(uuid7)
    target_kind = ReminderPlan.TargetKind.PERSONAL_EVENT
    # The personal-side record the plan belongs to, by value. No personal event needs to
    # exist: the plan holds the reference by value, like every other cross-module id here.
    target_id = factory.LazyFunction(uuid7)
    slots = ["1d", "1hr"]


class ScheduledSendFactory(DeliveryFactory):
    """One pending `event_reminder`, due at a fixed instant.

    The send key is built from the same `send_keys` builder production uses, so a factory row
    is never a shape the real minting path could not produce.

    **`slot_at` is set to the same instant as `due_at`** — a factory row is *not* deferred,
    so the two coincide. That is a real state (a slot outside the Quiet Hours window) and it
    keeps a factory row re-timeable: the rewrite shifts `slot_at` and gets `due_at` back.
    """

    class Meta:
        model = ScheduledSend

    user_id = factory.LazyFunction(uuid7)
    kind = ScheduledSend.Kind.EVENT_REMINDER
    target_kind = ReminderPlan.TargetKind.SAVED_EVENT
    target_id = factory.LazyFunction(uuid7)
    slot = "1d"
    event_version = 1
    stream = Stream.TRANSACTIONAL.value
    slot_at = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
    due_at = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
    status = ScheduledSend.Status.PENDING

    @factory.lazy_attribute
    def send_key(self):
        return event_reminder_key(
            user_id=self.user_id,
            event_id=self.target_id,
            slot=self.slot,
            event_version=self.event_version,
        )


class DeliveryAuditEntryFactory(DeliveryFactory):
    class Meta:
        model = DeliveryAuditEntry

    actor_kind = "system"
    actor_label = "delivery"
    action = "reminder_plan.attached_default"
    target_type = "personal_event"
    target_id = factory.LazyFunction(uuid7)
