"""factory_boy factories for the `delivery` models. Deterministic: fixed UTC instants, seeded
Faker, sequences for every unique value.
"""

import factory
import factory.random
from factory.django import DjangoModelFactory

from apps.delivery.models import DeliveryAuditEntry, ReminderPlan
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


class DeliveryAuditEntryFactory(DeliveryFactory):
    class Meta:
        model = DeliveryAuditEntry

    actor_kind = "system"
    actor_label = "delivery"
    action = "reminder_plan.attached_default"
    target_type = "personal_event"
    target_id = factory.LazyFunction(uuid7)
