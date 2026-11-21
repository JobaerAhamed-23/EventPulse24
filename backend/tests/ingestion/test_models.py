"""Catalog data model: constraints, the D7 supersede order, PROTECT and retention.

Constraint violations are asserted by the database's constraint name, so a test can't pass on
some other error. Design: catalog-data-model-design.md.
"""

from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal

import psycopg
import pytest
from django.apps import apps
from django.db import DataError, IntegrityError, connections, models, transaction
from django.db.models import F

from apps.ingestion.models import Event, EventStateChange, ExtractedRecord, Source
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from shared.retention import RetentionCategory
from tests.ingestion.factories import (
    FIRST_START,
    EventFactory,
    EventStateChangeFactory,
    ExtractedRecordFactory,
    IngestionAuditEntryFactory,
    SourceFactory,
    VenueFactory,
    make_superseded_pair,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])


@contextmanager
def violates(constraint: str):
    """Expect the block to fail on exactly this named constraint (rolled back to a savepoint)."""
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic(using=CATALOG):
        yield
    assert excinfo.value.__cause__.diag.constraint_name == constraint


@contextmanager
def event_insert_guard_disabled():
    """Reach a check the insert trigger would otherwise pre-empt. Rolled back with the test."""
    with connections[CATALOG].cursor() as cursor:
        cursor.execute("ALTER TABLE catalog.ingestion_event DISABLE TRIGGER event_guard_insert")
    yield


def bump(event: Event, **changes) -> None:
    """A lifecycle update the event guard accepts: the change plus event_version + 1."""
    Event.objects.using(CATALOG).filter(pk=event.pk).update(
        event_version=F("event_version") + 1, **changes
    )


# --- Identity (D2, D3, D22) ---------------------------------------------------------------


def test_extracted_record_second_row_for_same_source_item_rejected():
    record = ExtractedRecordFactory()

    with violates("extracted_record_source_item_uq"):
        ExtractedRecordFactory(
            event=EventFactory(source=record.source), source_event_id=record.source_event_id
        )


def test_event_second_live_event_for_same_source_item_rejected():
    event = EventFactory()

    with violates("event_live_source_item_uq"):
        EventFactory(source=event.source, source_event_id=event.source_event_id)


def test_event_superseded_and_live_event_may_share_source_item():
    old, new = make_superseded_pair()

    assert (old.source_id, old.source_event_id) == (new.source_id, new.source_event_id)
    assert old.status == Event.Status.SUPERSEDED
    assert old.superseded_by_id == new.id


def test_event_same_canonical_url_twice_allowed():
    event = EventFactory()

    EventFactory(canonical_url=event.canonical_url)  # D3: index only, no unique constraint


@pytest.mark.parametrize(
    ("factory", "constraint"),
    [
        (EventFactory, "event_source_event_id_nonempty_ck"),
        (ExtractedRecordFactory, "extracted_record_source_event_id_nonempty_ck"),
    ],
)
def test_empty_source_event_id_rejected(factory, constraint):
    with violates(constraint):
        factory(source_event_id="")


def test_event_duplicate_slug_rejected():
    event = EventFactory()

    with violates("event_slug_uq"):
        EventFactory(slug=event.slug)


def test_venue_duplicate_fingerprint_rejected():
    venue = VenueFactory()

    with violates("venue_fingerprint_uq"):
        VenueFactory(venue_fingerprint=venue.venue_fingerprint)


# --- Time and confidence (D8, D9) ---------------------------------------------------------


@pytest.mark.parametrize("field", ["tz_inference_confidence", "extraction_confidence"])
def test_event_null_confidence_rejected(field):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic(using=CATALOG):
        EventFactory(**{field: None})

    assert isinstance(excinfo.value.__cause__, psycopg.errors.NotNullViolation)
    assert excinfo.value.__cause__.diag.column_name == field


@pytest.mark.parametrize(
    ("field", "constraint"),
    [
        ("tz_inference_confidence", "event_tz_conf_range_ck"),
        ("extraction_confidence", "event_extr_conf_range_ck"),
    ],
)
@pytest.mark.parametrize("value", [Decimal("-0.01"), Decimal("1.01")])
def test_event_confidence_out_of_range_rejected(field, constraint, value):
    with violates(constraint):
        EventFactory(**{field: value})


@pytest.mark.parametrize(
    ("field", "constraint"),
    [
        ("tz_inference_confidence", "extracted_record_tz_conf_range_ck"),
        ("extraction_confidence", "extracted_record_extr_conf_range_ck"),
    ],
)
def test_extracted_record_confidence_out_of_range_rejected(field, constraint):
    with violates(constraint):
        ExtractedRecordFactory(**{field: Decimal("1.50")})


def test_extracted_record_null_tz_confidence_allowed():
    ExtractedRecordFactory(
        event=None,
        resolution=ExtractedRecord.Resolution.REJECTED,
        reject_reason="tz_none",
        tz_inference_confidence=None,
    )


@pytest.mark.parametrize(
    "value",
    ["2026-11-05 19:30:00", "2026-11-05T19:30+08", "nineteen characters"],
    ids=["space-separator", "offset", "free-text"],
)
def test_event_start_time_local_bad_shape_rejected(value):
    with violates("event_start_time_local_format_ck"):
        EventFactory(start_time_local=value)


def test_event_start_time_local_with_microseconds_rejected():
    with pytest.raises(DataError), transaction.atomic(using=CATALOG):
        EventFactory(start_time_local="2026-11-05T19:30:00.000001")  # longer than varchar(19)


def test_event_end_before_start_rejected():
    with violates("event_end_after_start_ck"):
        EventFactory(start_time_utc=FIRST_START, end_time_utc=FIRST_START - timedelta(hours=1))


# --- Lifecycle and versioning (D7, D10) ----------------------------------------------------


def test_event_superseded_without_superseded_by_rejected():
    event = EventFactory()

    with violates("event_superseded_consistent_ck"):
        bump(event, status=Event.Status.SUPERSEDED)


def test_event_superseded_by_without_superseded_status_rejected():
    event, other = EventFactory(), EventFactory()

    with violates("event_superseded_consistent_ck"):
        bump(event, superseded_by_id=other.id)


def test_event_superseded_by_itself_rejected():
    event = EventFactory()

    with violates("event_not_self_superseded_ck"):
        bump(event, status=Event.Status.SUPERSEDED, superseded_by_id=event.id)


def test_event_version_zero_rejected():
    with event_insert_guard_disabled(), violates("event_version_positive_ck"):
        EventFactory(event_version=0)


def test_state_change_version_zero_rejected():
    with violates("state_change_version_positive_ck"):
        EventStateChangeFactory(event_version=0)


def test_state_change_duplicate_event_version_rejected():
    change = EventStateChangeFactory()

    with violates("state_change_version_uq"):
        EventStateChangeFactory(event=change.event, event_version=change.event_version)


def test_supersede_in_design_order_succeeds():
    old = EventFactory()
    record = ExtractedRecordFactory(event=old, source=old.source)
    new_id = uuid7()

    with transaction.atomic(using=CATALOG):
        bump(old, status=Event.Status.SUPERSEDED, superseded_by_id=new_id)
        new = EventFactory(
            id=new_id,
            source=old.source,
            source_event_id=old.source_event_id,
            start_time_utc=old.start_time_utc + timedelta(days=45),
        )
        ExtractedRecord.objects.using(CATALOG).filter(pk=record.pk).update(event=new)
        EventStateChangeFactory(
            event=old, kind=EventStateChange.Kind.SUPERSEDED, event_version=2, after={"id": new_id}
        )

    old.refresh_from_db(using=CATALOG)
    record.refresh_from_db(using=CATALOG)
    assert (old.status, old.superseded_by_id, old.event_version) == ("superseded", new.id, 2)
    assert record.event_id == new.id


def test_supersede_in_reverse_order_rejected_even_inside_one_transaction():
    # D7 steps 3 then 2: the FK to the new id could wait (deferred), but the partial unique
    # index can't, so inserting the new Event while the old one is still live fails at once.
    old = EventFactory()
    new_id = uuid7()

    with violates("event_live_source_item_uq"):
        EventFactory(
            id=new_id,
            source=old.source,
            source_event_id=old.source_event_id,
            start_time_utc=old.start_time_utc + timedelta(days=45),
        )
        bump(old, status=Event.Status.SUPERSEDED, superseded_by_id=new_id)

    old.refresh_from_db(using=CATALOG)
    assert old.status == Event.Status.SCHEDULED


# --- Resolution and actors (D17, D21) -----------------------------------------------------


@pytest.mark.parametrize(
    ("resolution", "with_event", "reject_reason"),
    [
        ("resolved", False, ""),
        ("resolved", True, "tz_none"),
        ("rejected", True, "tz_none"),
        ("rejected", False, ""),
        ("ambiguous", True, ""),
        ("ambiguous", False, "tz_none"),
    ],
)
def test_extracted_record_inconsistent_resolution_rejected(resolution, with_event, reject_reason):
    event = EventFactory()

    with violates("extracted_record_resolution_ck"):
        ExtractedRecordFactory(
            event=event if with_event else None,
            source=event.source,
            source_event_id="item-under-test",
            resolution=resolution,
            reject_reason=reject_reason,
        )


@pytest.mark.parametrize(
    ("resolution", "with_event", "reject_reason"),
    [("resolved", True, ""), ("rejected", False, "tz_none"), ("ambiguous", False, "")],
)
def test_extracted_record_consistent_resolution_allowed(resolution, with_event, reject_reason):
    event = EventFactory()

    ExtractedRecordFactory(
        event=event if with_event else None,
        source=event.source,
        source_event_id="item-under-test",
        resolution=resolution,
        reject_reason=reject_reason,
    )


INVALID_ACTORS = [
    {"actor_kind": "user", "actor_id": None, "actor_label": ""},
    {"actor_kind": "user", "actor_id": uuid7(), "actor_label": "ingest_pipeline"},
    {"actor_kind": "system", "actor_id": uuid7(), "actor_label": "ingest_pipeline"},
    {"actor_kind": "system", "actor_id": None, "actor_label": ""},
]
ACTOR_IDS = ["user-no-id", "user-with-label", "system-with-id", "system-no-label"]


@pytest.mark.parametrize("actor", INVALID_ACTORS, ids=ACTOR_IDS)
def test_audit_entry_invalid_actor_rejected(actor):
    with violates("ingestion_ingestionauditentry_actor_ck"):
        IngestionAuditEntryFactory(**actor)


@pytest.mark.parametrize("actor", INVALID_ACTORS, ids=ACTOR_IDS)
def test_state_change_invalid_actor_rejected(actor):
    with violates("state_change_actor_ck"):
        EventStateChangeFactory(**actor)


def test_audit_entry_user_actor_allowed():
    IngestionAuditEntryFactory(actor_kind="user", actor_id=uuid7(), actor_label="")


# --- Model-wide rules (D19, D20) ----------------------------------------------------------

INGESTION_MODELS = list(apps.get_app_config("ingestion").get_models())


def test_ingestion_has_the_fourteen_designed_models():
    # The seven from catalog-data-model-design.md, plus EventFit (AD-10, FR-26), City
    # (FR-27, city-canonicalization-design.md), RevalidationRequest (FR-26, FR-27,
    # revalidation-signal-design.md), ReviewItem (FR-57, review-queue-model-design.md),
    # SourceObservation (FR-16, editorial-review-commands): the editorial verdicts the
    # reliability score is computed from, stored as facts rather than as a score,
    # SourceReliabilityScore (FR-16, reliability-recompute-and-escalation): the week's
    # score for a source, kept as a history so a spike can be seen, and CityProvisioning
    # (city-picker-and-auto-collection): what we did about a city, so the surface can
    # tell the truth about it.
    assert {m.__name__ for m in INGESTION_MODELS} == {
        "Source",
        "TosReview",
        "Venue",
        "City",
        "Event",
        "ExtractedRecord",
        "EventFit",
        "EventStateChange",
        "IngestionAuditEntry",
        "RevalidationRequest",
        "ReviewItem",
        "SourceObservation",
        "SourceReliabilityScore",
        "CityProvisioning",
    }


def test_every_ingestion_foreign_key_is_protect():
    foreign_keys = [
        field
        for model in INGESTION_MODELS
        for field in model._meta.get_fields()
        if isinstance(field, models.ForeignKey)
    ]

    assert foreign_keys  # the meta-test would pass vacuously on an empty list
    assert {f"{f.model.__name__}.{f.name}": f.remote_field.on_delete for f in foreign_keys} == {
        f"{f.model.__name__}.{f.name}": models.PROTECT for f in foreign_keys
    }


def test_ingestion_retention_categories():
    assert {m.__name__: m.retention_category for m in INGESTION_MODELS} == {
        "City": RetentionCategory.SOURCE_REGISTRY,
        "Source": RetentionCategory.SOURCE_REGISTRY,
        "TosReview": RetentionCategory.TOS_REVIEW_RECORDS,
        "Venue": RetentionCategory.SOURCE_REGISTRY,
        "Event": RetentionCategory.SOURCE_REGISTRY,
        "ExtractedRecord": RetentionCategory.SOURCE_REGISTRY,
        "EventFit": RetentionCategory.SOURCE_REGISTRY,
        "EventStateChange": RetentionCategory.SOURCE_REGISTRY,
        "IngestionAuditEntry": RetentionCategory.AUDIT_LOG,
        "RevalidationRequest": RetentionCategory.SOURCE_REGISTRY,
        "ReviewItem": RetentionCategory.SOURCE_REGISTRY,
        "SourceObservation": RetentionCategory.SOURCE_REGISTRY,
        "SourceReliabilityScore": RetentionCategory.SOURCE_REGISTRY,
        "CityProvisioning": RetentionCategory.SOURCE_REGISTRY,
    }


def test_source_zero_cadence_rejected():
    with violates("source_cadence_positive_ck"):
        SourceFactory(ingestion_cadence=timedelta(0))


# --- FR-53: the cadence ceilings, enforced by the database ---------------------------------------


def test_high_priority_source_over_its_ceiling_rejected():
    with violates("source_cadence_within_priority_ceiling_ck"):
        SourceFactory(acquisition_method="api", ingestion_cadence=timedelta(hours=4, seconds=1))


def test_high_priority_source_at_its_ceiling_accepted():
    source = SourceFactory(acquisition_method="api", ingestion_cadence=timedelta(hours=4))

    assert source.ingestion_cadence == timedelta(hours=4)


def test_lower_priority_source_over_its_ceiling_rejected():
    with violates("source_cadence_within_priority_ceiling_ck"):
        SourceFactory(acquisition_method="rss", ingestion_cadence=timedelta(hours=24, seconds=1))


def test_lower_priority_source_at_its_ceiling_accepted():
    source = SourceFactory(acquisition_method="rss", ingestion_cadence=timedelta(hours=24))

    assert source.ingestion_cadence == timedelta(hours=24)


def test_the_constraint_holds_when_the_python_path_is_bypassed():
    """The constraint is the backstop: the registry's cleaner can be skipped, and the row
    still cannot hold a cadence the guarantee cannot support.
    """
    source = SourceFactory(acquisition_method="rss", ingestion_cadence=timedelta(hours=24))

    with violates("source_cadence_within_priority_ceiling_ck"):
        Source.objects.using(CATALOG).filter(pk=source.pk).update(
            ingestion_cadence=timedelta(hours=24, seconds=1)
        )


def test_the_constraint_holds_when_the_method_changes():
    """Moving a 24-hour row to `api` is over the high tier's ceiling — the row cannot become
    that, whatever wrote it.
    """
    source = SourceFactory(acquisition_method="rss", ingestion_cadence=timedelta(hours=24))

    with violates("source_cadence_within_priority_ceiling_ck"):
        Source.objects.using(CATALOG).filter(pk=source.pk).update(acquisition_method="api")
