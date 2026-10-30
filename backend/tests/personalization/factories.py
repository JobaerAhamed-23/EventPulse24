"""factory_boy factories for the `personalization` models. Deterministic: fixed UTC instants,
explicit IANA zones, seeded Faker, sequences for every unique value.
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import factory
import factory.random
from factory.django import DjangoModelFactory

from apps.personalization.models import (
    CalendarConnection,
    ConflictPair,
    DigestComposition,
    DigestPreference,
    PersonalEvent,
    PersonalizationAuditEntry,
    PulseDigest,
    SavedEvent,
)
from shared.db import PERSONAL
from shared.ids import uuid7

factory.random.reseed_random("eventpulse24-personalization")

# 2026-11-05 19:30 in Los Angeles (PST, after the 2026-11-01 DST end).
FIRST_START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)
TZ = "America/Los_Angeles"

#: The local day the digest factories use, and the instant it was composed at.
LOCAL_DATE = date(2026, 11, 6)
COMPOSED_AT = datetime(2026, 11, 6, 16, 0, tzinfo=UTC)


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


#: A secret-looking calendar address. The long opaque segment is what every provider puts
#: in the path, and what the redaction patterns are tuned for.
FAKE_CALENDAR_URL = (
    "https://calendar.google.com/calendar/ical/ZmFrZXNlY3JldHNlY3JldHNlY3JldHNlY3JldA/basic.ics"
)


class CalendarConnectionFactory(PersonalFactory):
    """A connected calendar.

    The credential is written through the model, so the factory stores an **encrypted**
    value — the factory never puts a plaintext credential into the column.
    """

    class Meta:
        model = CalendarConnection

    user_id = factory.LazyFunction(uuid7)
    provider = CalendarConnection.Provider.GOOGLE
    credential = FAKE_CALENDAR_URL
    credential_fingerprint = factory.Sequence(lambda n: f"{n:064x}")
    status = CalendarConnection.Status.ACTIVE
    display_label = "Work"


class DigestPreferenceFactory(PersonalFactory):
    """One user's digest preference: when, where, and what.

    **No city by default.** `NULL` is a real state — "we do not know where this user
    is" — and a factory that defaulted to a city would make every test that did not care
    about the city depend on it. The opt-out defaults to *included*, which is PRD
    `[ASSUMPTION-7]`.
    """

    class Meta:
        model = DigestPreference

    user_id = factory.LazyFunction(uuid7)
    delivery_time = factory.LazyFunction(lambda: time(9, 0))
    timezone = TZ
    city = None
    city_source = None
    include_personal_events = True


class PulseDigestFactory(PersonalFactory):
    """One user's digest for one local day.

    The user is fresh per row by default, so two digests for the same user and the same
    day need the user passed explicitly — which is exactly what the uniqueness test does.
    """

    class Meta:
        model = PulseDigest

    user_id = factory.LazyFunction(uuid7)
    local_date = LOCAL_DATE
    timezone = TZ
    composed_at = COMPOSED_AT
    is_empty = False


class DigestCompositionFactory(PersonalFactory):
    """One event's persisted explanation within a digest.

    **Public by default**: a public composition carries a Source Badge and a catalog
    `event_version`, and a personal one carries neither (D7). The default is the shape
    that satisfies the check constraint as written, so a factory-created row is valid
    without the test having to spell out the whole shape.
    """

    class Meta:
        model = DigestComposition

    digest_id = factory.LazyFunction(uuid7)
    user_id = factory.LazyFunction(uuid7)
    # The catalog Event's id, by value. There is no catalog Event behind it: the tests
    # that need one create it in the catalog schema.
    event_id = factory.LazyFunction(uuid7)
    event_kind = DigestComposition.EventKind.PUBLIC
    slot = DigestComposition.Slot.MUST_KNOW
    score = Decimal("0.83")
    bucket = 4
    tags = ["nearby", "tonight"]
    source_badge = "official_site"
    event_version = 1
    composed_at = COMPOSED_AT
