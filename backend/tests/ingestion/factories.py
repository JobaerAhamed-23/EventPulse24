"""factory_boy factories for the `ingestion` catalog models. Deterministic: fixed UTC instants,
explicit IANA zones, seeded Faker, sequences for every unique value.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import factory
import factory.random
from django.db import transaction
from django.db.models import F
from factory.django import DjangoModelFactory

from apps.ingestion.models import (
    AcquisitionMethod,
    Event,
    EventStateChange,
    ExtractedRecord,
    IngestionAuditEntry,
    ReviewItem,
    Source,
    TosReview,
    Venue,
)
from shared.db import CATALOG
from shared.ids import uuid7

factory.random.reseed_random("eventpulse24-ingestion")

VENUE_TZ = "America/Los_Angeles"
# 2026-11-05 19:30 in Los Angeles (PST, after the 2026-11-01 DST end).
FIRST_START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)


def local_wall_clock(instant: datetime, tz: str) -> str:
    """The normalized `start_time_local` form: no offset, no microseconds (design D8)."""
    return instant.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%dT%H:%M:%S")


class CatalogFactory(DjangoModelFactory):
    """Writes on the catalog alias explicitly, never through the router's default.

    `skip_postgeneration_save` stops factory_boy's second `save()`, which append-only models
    reject.
    """

    class Meta:
        abstract = True
        database = CATALOG
        skip_postgeneration_save = True


class SourceFactory(CatalogFactory):
    class Meta:
        model = Source

    name = factory.Sequence(lambda n: f"Source {n}")
    source_type = Source.SourceType.VENUE
    url = factory.Sequence(lambda n: f"https://source{n}.example.test/events.rss")
    acquisition_method = AcquisitionMethod.RSS
    ingestion_cadence = timedelta(hours=4)
    tz_coverage = Source.TzCoverage.FULL


class TosReviewFactory(CatalogFactory):
    class Meta:
        model = TosReview

    source = factory.SubFactory(SourceFactory)
    decision = TosReview.Decision.APPROVED
    acquisition_method = factory.SelfAttribute("source.acquisition_method")
    reviewed_by_id = factory.LazyFunction(uuid7)


class VenueFactory(CatalogFactory):
    class Meta:
        model = Venue

    name = factory.Sequence(lambda n: f"Venue {n}")
    city = "Los Angeles"
    country_code = "US"
    venue_fingerprint = factory.Sequence(lambda n: f"venue-{n}|los angeles")
    tz = VENUE_TZ


class EventFactory(CatalogFactory):
    """A published, scheduled Event at version 1: the only shape the insert guard accepts."""

    class Meta:
        model = Event

    source = factory.SubFactory(SourceFactory)
    source_event_id = factory.Sequence(lambda n: f"item-{n}")
    slug = factory.Sequence(lambda n: f"event-{n}")
    title = factory.Faker("sentence", nb_words=4)
    title_fingerprint = factory.LazyAttribute(lambda o: o.title.lower())
    canonical_url = factory.Sequence(lambda n: f"https://source.example.test/events/{n}")
    venue = factory.SubFactory(VenueFactory)
    venue_fingerprint = factory.LazyAttribute(
        lambda o: o.venue.venue_fingerprint if o.venue else ""
    )
    start_time_utc = factory.Sequence(lambda n: FIRST_START + timedelta(days=n))
    original_start_utc = factory.SelfAttribute("start_time_utc")  # the insert guard requires it
    start_time_tz = VENUE_TZ
    start_time_local = factory.LazyAttribute(
        lambda o: local_wall_clock(o.start_time_utc, o.start_time_tz)
    )
    tz_inference_confidence = Decimal("1.00")
    extraction_confidence = Decimal("1.00")


class ExtractedRecordFactory(CatalogFactory):
    class Meta:
        model = ExtractedRecord

    # Bound to an Event by default; pass event=None for a rejected or ambiguous item.
    event = factory.SubFactory(EventFactory)
    source = factory.Maybe(
        "event",
        yes_declaration=factory.SelfAttribute("event.source"),
        no_declaration=factory.SubFactory(SourceFactory),
    )
    source_event_id = factory.LazyAttributeSequence(
        lambda o, n: o.event.source_event_id if o.event else f"record-{n}"
    )
    payload = factory.LazyAttribute(lambda o: {"title": o.event.title if o.event else "Untitled"})
    content_hash = factory.Sequence(lambda n: f"{n:064x}")
    extraction_confidence = Decimal("1.00")
    tz_inference_confidence = Decimal("1.00")
    resolution = ExtractedRecord.Resolution.RESOLVED


class EventStateChangeFactory(CatalogFactory):
    """Each change gets its own Event; pass explicit versions for several on one Event."""

    class Meta:
        model = EventStateChange

    event = factory.SubFactory(EventFactory)
    kind = EventStateChange.Kind.DETAIL_CHANGED
    event_version = 2
    before = factory.LazyAttribute(lambda o: {"title": o.event.title})
    after = {"title": "Renamed"}
    actor_kind = "system"
    actor_label = "ingest_pipeline"


class ReviewItemFactory(CatalogFactory):
    """An open `in_review` item on its own Event. Tests that need a report or a source item
    pass `reason`, the target and (for a report) `due_at` and a tally explicitly."""

    class Meta:
        model = ReviewItem

    reason = ReviewItem.Reason.IN_REVIEW
    event = factory.SubFactory(EventFactory)


class IngestionAuditEntryFactory(CatalogFactory):
    class Meta:
        model = IngestionAuditEntry

    actor_kind = "system"
    actor_label = "ingest_pipeline"
    action = "register_source"
    target_type = "source"
    target_id = factory.LazyFunction(uuid7)


def make_superseded_pair(**overrides) -> tuple[Event, Event]:
    """Supersede an Event in the design D7 order; returns (old, new), both saved.

    A superseded Event can't be inserted directly (the insert guard), so this is the only way
    tests get one.
    """
    old = EventFactory(**overrides)
    new_id = uuid7()
    with transaction.atomic(using=CATALOG):
        Event.objects.using(CATALOG).filter(pk=old.pk).update(
            status=Event.Status.SUPERSEDED,
            superseded_by_id=new_id,
            event_version=F("event_version") + 1,
        )
        new = EventFactory(
            id=new_id,
            source=old.source,
            source_event_id=old.source_event_id,
            venue=old.venue,
            start_time_utc=old.start_time_utc + timedelta(days=60),
        )
    old.refresh_from_db(using=CATALOG)
    return old, new
