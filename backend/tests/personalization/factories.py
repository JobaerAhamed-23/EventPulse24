"""factory_boy factories for the `personalization` models. Deterministic: fixed UTC instants,
explicit IANA zones, seeded Faker, sequences for every unique value.
"""

from datetime import UTC, datetime, timedelta

import factory
import factory.random
from factory.django import DjangoModelFactory

from apps.personalization.models import (
    ConflictPair,
    PersonalEvent,
    PersonalizationAuditEntry,
    SavedEvent,
)
from shared.db import PERSONAL
from shared.ids import uuid7

factory.random.reseed_random("eventpulse24-personalization")

# 2026-11-05 19:30 in Los Angeles (PST, after the 2026-11-01 DST end).
FIRST_START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)
TZ = "America/Los_Angeles"


class PersonalFactory(DjangoModelFactory):
    """Writes on the personal alias explicitly, never through the router's default.

    `skip_postgeneration_save` stops factory_boy's second `save()`, which the append-only
    audit model rejects.
    """

    class Meta:
        abstract = True
        database = PERSONAL
        skip_postgeneration_save = True


class PersonalEventFactory(PersonalFactory):
    class Meta:
        model = PersonalEvent

    user_id = factory.LazyFunction(uuid7)
    name = factory.Sequence(lambda n: f"Personal Event {n}")
    start_utc = FIRST_START
    end_utc = FIRST_START + timedelta(hours=2)
    start_time_tz = TZ
    location = factory.Sequence(lambda n: f"{n} Example Street")
    notes = "Notes."


class SavedEventFactory(PersonalFactory):
    class Meta:
        model = SavedEvent

    user_id = factory.LazyFunction(uuid7)
    # The catalog Event's id, by value. There is no catalog Event behind it: the tests that
    # need one create it in the catalog schema.
    event_id = factory.LazyFunction(uuid7)
    start_utc = FIRST_START
    end_utc = FIRST_START + timedelta(hours=2)
    event_version = 1


class ConflictPairFactory(PersonalFactory):
    class Meta:
        model = ConflictPair

    user_id = factory.LazyFunction(uuid7)
    kind = ConflictPair.Kind.TIME
    left_kind = ConflictPair.SideKind.PERSONAL_EVENT
    left_id = factory.LazyFunction(uuid7)
    right_kind = ConflictPair.SideKind.SAVED_EVENT
    right_id = factory.LazyFunction(uuid7)


class PersonalizationAuditEntryFactory(PersonalFactory):
    class Meta:
        model = PersonalizationAuditEntry

    actor_kind = "system"
    actor_label = "personalization"
    action = "create_personal_event"
    target_type = "personal_event"
    target_id = factory.LazyFunction(uuid7)
