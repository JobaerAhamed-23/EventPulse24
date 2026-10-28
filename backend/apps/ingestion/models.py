"""Catalog entities. `ingestion` is their sole writer (AD-4, AD-16); all live in schema `catalog`.

Design: .specs-fire/intents/event-catalog-ingestion/work-items/catalog-data-model-design.md
(decisions D1-D23). Integrity the database can hold is a constraint or a trigger in
migration 0001; what it can't (IANA validity, identity matching) belongs to the commands.
"""

from datetime import timedelta
from typing import ClassVar

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from shared.models import (
    ActorColumns,
    AppendOnlyModel,
    AuditEntry,
    UUIDv7Model,
    actor_check,
)
from shared.retention import RetentionCategory


def _confidence_field(**kwargs) -> models.DecimalField:
    # numeric(3,2) in [0, 1] (spine Consistency Conventions); the range is a check constraint.
    return models.DecimalField(max_digits=3, decimal_places=2, **kwargs)


def _confidence_range(field: str, name: str) -> models.CheckConstraint:
    return models.CheckConstraint(
        condition=Q(**{f"{field}__gte": 0, f"{field}__lte": 1}), name=name
    )


class AcquisitionMethod(models.TextChoices):
    """FR-17 priority order, highest first: crawl is the last resort and needs a ToS review."""

    API = "api"
    PARTNERSHIP = "partnership"
    JSONLD = "jsonld"
    RSS = "rss"
    ICS = "ics"
    EMAIL_ICS = "email_ics"
    CRAWL = "crawl"


class Source(UUIDv7Model):
    """One event source in the Source Registry (FR-13). Paused, never deleted."""

    class SourceType(models.TextChoices):
        VENUE = "venue"
        PROMOTER = "promoter"
        TICKETING = "ticketing"
        COMMUNITY = "community"
        GOVERNMENT = "government"
        MEDIA = "media"
        OTHER = "other"

    class TosStatus(models.TextChoices):
        NOT_REVIEWED = "not_reviewed"
        APPROVED = "approved"
        REJECTED = "rejected"

    class Status(models.TextChoices):
        ACTIVE = "active"
        PAUSED = "paused"

    class TzCoverage(models.TextChoices):
        FULL = "full"
        PARTIAL = "partial"
        NONE = "none"

    retention_category = RetentionCategory.SOURCE_REGISTRY

    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=16, choices=SourceType.choices)
    url = models.URLField(max_length=2048)
    city = models.CharField(max_length=100, blank=True)
    acquisition_method = models.CharField(max_length=16, choices=AcquisitionMethod.choices)
    # Cache of the latest TosReview for the current method (D13). Only record_tos_review and
    # update_source write it.
    tos_status = models.CharField(
        max_length=16, choices=TosStatus.choices, default=TosStatus.NOT_REVIEWED
    )
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    # No default: register_source applies the per-method default (D16).
    ingestion_cadence = models.DurationField()
    freshness_ttl_hours = models.PositiveSmallIntegerField(default=24)
    tz_coverage = models.CharField(max_length=8, choices=TzCoverage.choices)
    etag = models.CharField(max_length=512, blank=True)
    last_modified = models.CharField(max_length=64, blank=True)
    # The last fetch's final URL, after same-host redirects; the parse base for relative links.
    fetched_url = models.URLField(max_length=2048, blank=True)
    last_ingested_at = models.DateTimeField(null=True, blank=True)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_error_code = models.CharField(max_length=64, blank=True)
    stale_since = models.DateTimeField(null=True, blank=True)
    # Set when the scheduler enqueues a run, cleared when the run's job ends: a claimed source is
    # never enqueued twice. A claim older than INGEST_CLAIM_TTL is a lost job.
    ingest_claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(ingestion_cadence__gt=timedelta(0)), name="source_cadence_positive_ck"
            ),
        ]
        indexes = [
            # Due selection scans active sources by last attempt (scheduling.claim_due_sources).
            models.Index(
                fields=["last_attempted_at"],
                condition=Q(status="active"),
                name="source_due_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class TosReview(UUIDv7Model):
    """A logged ToS review of one acquisition method for one source (FR-17). Kept 7 years."""

    class Decision(models.TextChoices):
        APPROVED = "approved"
        REJECTED = "rejected"

    retention_category = RetentionCategory.TOS_REVIEW_RECORDS

    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="tos_reviews")
    decision = models.CharField(max_length=16, choices=Decision.choices)
    acquisition_method = models.CharField(max_length=16, choices=AcquisitionMethod.choices)
    reviewed_by_id = models.UUIDField()  # by value, no FK across the AD-3 wall (OQ-8)
    reviewed_at = models.DateTimeField(default=timezone.now)
    evidence_url = models.URLField(max_length=2048, blank=True)
    notes = models.TextField(blank=True)


class Venue(UUIDv7Model):
    """Venue registry: the FR-60 `partial` tier's timezone source and the identity venue key."""

    retention_category = RetentionCategory.SOURCE_REGISTRY

    name = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    country_code = models.CharField(max_length=2)
    venue_fingerprint = models.CharField(max_length=128)
    # IANA name; unknown until editorial adds it. Without it a venue can't rescue a partial-tier
    # event (D14).
    tz = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["venue_fingerprint"], name="venue_fingerprint_uq"),
        ]

    def __str__(self) -> str:
        return f"{self.name}, {self.city}"


class Event(UUIDv7Model):
    """A canonical public Event (Glossary). Identity is structural (AD-4); time is UTC plus an
    explicit IANA tz (AD-6).

    The `catalog.guard_event_write` trigger makes `superseded` terminal and requires
    `event_version + 1` with every lifecycle-column change (LIFECYCLE_FIELDS).
    """

    class PublicationStatus(models.TextChoices):
        PUBLISHED = "published"
        IN_REVIEW = "in_review"  # not digest-eligible, not publicly listed (AD-6, AD-8)

    class Status(models.TextChoices):
        SCHEDULED = "scheduled"
        POSTPONED = "postponed"  # date to be announced
        CANCELLED = "cancelled"
        SUPERSEDED = "superseded"  # terminal; see superseded_by (D7)

    # Mirrors the trigger in migration 0001: a change to any of these needs a version bump.
    LIFECYCLE_FIELDS: ClassVar[tuple[str, ...]] = (
        "start_time_utc",
        "end_time_utc",
        "start_time_tz",
        "status",
        "is_sold_out",
        "venue",
        "superseded_by",
    )

    retention_category = RetentionCategory.SOURCE_REGISTRY

    # Origin: the source item that first produced this Event (identity rule (a) lives on
    # ExtractedRecord, D2).
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="events")
    source_event_id = models.CharField(max_length=512)
    slug = models.SlugField(max_length=200)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)  # parser-stripped plain text, never HTML (AD-9)
    canonical_url = models.URLField(max_length=2048, blank=True)
    venue = models.ForeignKey(
        Venue, on_delete=models.PROTECT, null=True, blank=True, related_name="events"
    )
    # Copied at ingest so a venue rename never changes this Event's identity (D14).
    venue_fingerprint = models.CharField(max_length=128, blank=True)
    title_fingerprint = models.CharField(max_length=512)
    start_time_utc = models.DateTimeField()
    # The start this Event was created with; the ±30-day supersede rule measures from it (AD-4).
    # The guard trigger sets it equal to start_time_utc on insert and freezes it.
    original_start_utc = models.DateTimeField()
    end_time_utc = models.DateTimeField(null=True, blank=True)
    # Normalized wall-clock time as the source wrote it, no offset; evidence only, never
    # computed on (D8). The raw text is in ExtractedRecord.payload.
    start_time_local = models.CharField(max_length=19)
    start_time_tz = models.CharField(max_length=64)  # IANA name, validated by the command
    tz_inference_confidence = _confidence_field()
    extraction_confidence = _confidence_field()
    tz_review_pending = models.BooleanField(default=False)  # 0.70 <= tz confidence < 0.90 (D6)
    publication_status = models.CharField(
        max_length=16, choices=PublicationStatus.choices, default=PublicationStatus.PUBLISHED
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)
    is_sold_out = models.BooleanField(default=False)
    event_version = models.PositiveIntegerField(default=1)
    series_id = models.UUIDField(null=True, blank=True)  # shared.ids.series_id (D11)
    superseded_by = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="supersedes"
    )
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # One live Event per source item; a superseded one may share it (D3). Partial, so
            # it can't be deferred: supersede must retire the old row first (D7).
            models.UniqueConstraint(
                fields=["source", "source_event_id"],
                condition=~Q(status="superseded"),
                name="event_live_source_item_uq",
            ),
            models.UniqueConstraint(fields=["slug"], name="event_slug_uq"),
            models.CheckConstraint(
                condition=~Q(source_event_id=""), name="event_source_event_id_nonempty_ck"
            ),
            _confidence_range("tz_inference_confidence", "event_tz_conf_range_ck"),
            _confidence_range("extraction_confidence", "event_extr_conf_range_ck"),
            models.CheckConstraint(
                condition=Q(end_time_utc__isnull=True) | Q(end_time_utc__gte=F("start_time_utc")),
                name="event_end_after_start_ck",
            ),
            models.CheckConstraint(
                condition=(Q(status="superseded") & Q(superseded_by__isnull=False))
                | (~Q(status="superseded") & Q(superseded_by__isnull=True)),
                name="event_superseded_consistent_ck",
            ),
            models.CheckConstraint(
                condition=Q(superseded_by__isnull=True) | ~Q(superseded_by=F("id")),
                name="event_not_self_superseded_ck",
            ),
            models.CheckConstraint(
                condition=Q(event_version__gte=1), name="event_version_positive_ck"
            ),
            models.CheckConstraint(
                condition=Q(start_time_local__regex=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"),
                name="event_start_time_local_format_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["venue_fingerprint", "start_time_utc"], name="event_rule_b_idx"),
            models.Index(fields=["canonical_url"], name="event_canonical_url_idx"),
            models.Index(
                fields=["publication_status", "status", "start_time_utc"], name="event_listing_idx"
            ),
            models.Index(fields=["series_id"], name="event_series_idx"),
        ]

    def __str__(self) -> str:
        return self.title


class ExtractedRecord(UUIDv7Model):
    """One source item, bound to its current Event (D2). Upserted on every ingest; the rule (a)
    authority. A rejected or ambiguous item has no Event (D5, D21).
    """

    class Resolution(models.TextChoices):
        RESOLVED = "resolved"
        REJECTED = "rejected"
        # Matches more than one live Event, or rules disagree: never auto-merged (FR-15).
        AMBIGUOUS = "ambiguous"

    retention_category = RetentionCategory.SOURCE_REGISTRY

    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="extracted_records")
    source_event_id = models.CharField(max_length=512)
    # Normalized, text-only candidate plus the as-written time; data, never rendered (AD-9).
    payload = models.JSONField(encoder=DjangoJSONEncoder)
    content_hash = models.CharField(max_length=64)  # sha256 hex of the normalized payload
    extraction_confidence = _confidence_field()
    tz_inference_confidence = _confidence_field(
        null=True, blank=True
    )  # none for a none-tier reject
    resolution = models.CharField(max_length=16, choices=Resolution.choices)
    reject_reason = models.CharField(max_length=64, blank=True)
    event = models.ForeignKey(
        Event, on_delete=models.PROTECT, null=True, blank=True, related_name="extracted_records"
    )
    # How identity was decided: {"rule": "a|b|c", "review_signals": [...], "ambiguous": [...]},
    # kept for the future review queue (ingest-pipeline-and-lifecycle-design.md D8).
    match_notes = models.JSONField(default=dict, encoder=DjangoJSONEncoder, blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    last_changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_event_id"], name="extracted_record_source_item_uq"
            ),
            models.CheckConstraint(
                condition=~Q(source_event_id=""),
                name="extracted_record_source_event_id_nonempty_ck",
            ),
            _confidence_range("extraction_confidence", "extracted_record_extr_conf_range_ck"),
            _confidence_range("tz_inference_confidence", "extracted_record_tz_conf_range_ck"),
            models.CheckConstraint(
                condition=(Q(resolution="resolved") & Q(event__isnull=False) & Q(reject_reason=""))
                | (Q(resolution="rejected") & Q(event__isnull=True) & ~Q(reject_reason=""))
                | (Q(resolution="ambiguous") & Q(event__isnull=True) & Q(reject_reason="")),
                name="extracted_record_resolution_ck",
            ),
        ]


class EventStateChange(AppendOnlyModel, ActorColumns, UUIDv7Model):
    """One entry of an Event's `state_history` and the AD-17 outbox row for it.

    Append-only (grants + trigger + these guards, D12). `propagated_at` is set once, only with
    `filter(propagated_at__isnull=True).update(propagated_at=...)` (D23).
    """

    class Kind(models.TextChoices):
        TIME_MOVED = "time_moved"
        POSTPONED = "postponed"
        CANCELLED = "cancelled"
        REINSTATED = "reinstated"  # cancelled -> live again, or postponed -> scheduled (D12)
        SOLD_OUT = "sold_out"
        DETAIL_CHANGED = "detail_changed"
        SUPERSEDED = "superseded"

    retention_category = RetentionCategory.SOURCE_REGISTRY
    append_only_mutable = frozenset({"propagated_at"})

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="state_changes")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    event_version = models.PositiveIntegerField()  # the Event's version after this change
    before = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    after = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    occurred_at = models.DateTimeField(default=timezone.now)
    propagated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        base_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(
                fields=["event", "event_version"], name="state_change_version_uq"
            ),
            models.CheckConstraint(
                condition=Q(event_version__gte=1), name="state_change_version_positive_ck"
            ),
            actor_check("state_change_actor_ck"),
        ]
        indexes = [
            models.Index(
                fields=["occurred_at"],
                condition=Q(propagated_at__isnull=True),
                name="state_change_unpropagated_idx",
            ),
        ]


class IngestionAuditEntry(AuditEntry):
    """The `ingestion` audit log (AD-5). Append-only; written only through `write_audit`."""

    retention_category = RetentionCategory.AUDIT_LOG
