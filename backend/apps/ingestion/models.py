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


class City(UUIDv7Model):
    """A canonical place, and the FR-27 URL it is published at (design: city-canonicalization).

    Cities arrive as free text on a venue — "Brooklyn", "brooklyn ", "Brooklyn, NY". This row
    is the one place each of those resolves to, so a city page has a stable address and a name
    a human chose rather than whichever spelling happened to be ingested first.

    **Identity is `(normalized_key, region, country_code)`, never the key alone.** `Portland,
    OR` and `Portland, ME` both key as `portland`; the region is what keeps them apart, and
    `domain.cities` refuses to discard it for exactly that reason. The consequence is accepted:
    "Brooklyn" and "Brooklyn, NY" are two rows here, and FR-27's ">5 events" threshold is what
    keeps the thinner one from being published.

    `slug` is minted once and never re-minted, like `Event.slug`: an indexed city page must
    not move.

    `retention_category` is `SOURCE_REGISTRY`: a city holds no user-derived data.
    """

    retention_category = RetentionCategory.SOURCE_REGISTRY

    # The FR-27 URL segment: "brooklyn", "brooklyn-ny", "brooklyn-ny-us" as collisions escalate.
    slug = models.SlugField(max_length=120)
    # As written by the first venue to name it; never re-cased (NYC, Sao Paulo keep their shape).
    name = models.CharField(max_length=100)
    country_code = models.CharField(max_length=2)
    # `domain.cities.normalize_city`: case, whitespace, punctuation and accents folded.
    normalized_key = models.CharField(max_length=100)
    # The trailing qualifier when one was written ("ny", "or"); "" when none was.
    region = models.CharField(max_length=16, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["slug"], name="city_slug_uq"),
            models.UniqueConstraint(
                fields=["normalized_key", "region", "country_code"],
                name="city_identity_uq",
            ),
            models.CheckConstraint(condition=~Q(slug=""), name="city_slug_nonempty_ck"),
            models.CheckConstraint(condition=~Q(name=""), name="city_name_nonempty_ck"),
            models.CheckConstraint(condition=~Q(normalized_key=""), name="city_key_nonempty_ck"),
        ]

    def __str__(self) -> str:
        return f"{self.name}{f', {self.region.upper()}' if self.region else ''}"


class Venue(UUIDv7Model):
    """Venue registry: the FR-60 `partial` tier's timezone source and the identity venue key."""

    retention_category = RetentionCategory.SOURCE_REGISTRY

    name = models.CharField(max_length=200)
    # The city **as written**. Never rewritten: `domain.dedup.venue_fingerprint` is computed
    # from this string, so changing it would re-identify the venue and corrupt event dedup.
    city = models.CharField(max_length=100)
    # The canonical city this resolves to (FR-27). Null when the venue named no city — the
    # rule Event Fit already follows: no row, rather than a guess.
    city_ref = models.ForeignKey(
        City, on_delete=models.PROTECT, null=True, blank=True, related_name="venues"
    )
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


class EventFit(UUIDv7Model):
    """One Event's fit for one city: a 1–5 score and the tag keys (AD-10, FR-26).

    **Event Fit** is the non-personalized half of AD-10's two kinds of explanation. It is
    keyed by `(event, city)` — the same event fits a Brooklyn preview and a New York one
    differently, and "tonight" is the same for both but "in_brooklyn" is not.

    The row is **persisted and served as it stands** (AD-10: "never recomputed at render").
    `event_version` is the Event version the fit was computed from: a row whose
    `event_version` no longer matches its Event is **stale** and is never served. The
    staleness check is the read's job, not a trigger's, because the refresh is a writer's
    work.

    `tags` is a JSON array of tag keys, in the fixed order the domain function produces.
    It is an array rather than a table because the set is small, closed, and always read
    whole — there is no query that asks "which events are tagged 'tonight'?".

    `retention_category` is `SOURCE_REGISTRY`: this row holds no user-derived data. It is
    catalog content about a catalog event.
    """

    retention_category = RetentionCategory.SOURCE_REGISTRY

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="event_fits")
    # The venue's city, as written on the Venue row. The Event Fit row exists per city, so
    # an event with no venue city has no row at all (work item: "an event without a venue
    # city gets no Event Fit row and doesn't appear in the preview, rather than being
    # guessed").
    city = models.CharField(max_length=100)
    # The canonical city, copied from the venue as `city` already is. Null for a fit written
    # before the backfill reached it; the city page reads by this, the preview still by `city`.
    city_ref = models.ForeignKey(
        City, on_delete=models.PROTECT, null=True, blank=True, related_name="event_fits"
    )
    score = models.PositiveSmallIntegerField()
    tags = models.JSONField(default=list, encoder=DjangoJSONEncoder)
    # The Event version this fit was computed from. A mismatch means stale.
    event_version = models.PositiveIntegerField()
    computed_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "city"], name="event_fit_event_city_uq"),
            models.CheckConstraint(
                condition=Q(score__gte=1) & Q(score__lte=5), name="event_fit_score_range_ck"
            ),
            models.CheckConstraint(
                condition=Q(event_version__gte=1), name="event_fit_version_positive_ck"
            ),
            models.CheckConstraint(condition=~Q(city=""), name="event_fit_city_nonempty_ck"),
        ]
        indexes = [
            # The preview reads by city, ordered by score then start time.
            models.Index(fields=["city", "score"], name="event_fit_city_score_idx"),
            # The FR-27 city page reads the same way, but by the canonical city.
            models.Index(fields=["city_ref", "score"], name="event_fit_city_ref_score_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_id} in {self.city}: {self.score}"


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


class RevalidationRequest(UUIDv7Model):
    """The revalidation outbox: one public page set that must be rebuilt (FR-26, FR-27).

    **This is the AD-17 outbox's shape, for a different consumer.** AD-17's outbox is
    `EventStateChange.propagated_at`, and it cannot be reused here for two reasons. Its
    `EventStateChange` table is append-only with exactly one mutable column — `propagated_at`
    — and that column belongs to the *personal* propagation, which is still a reserved slot
    (`worker.tasks.propagate_state_change`). And the two have genuinely different
    lifecycles: AD-17's propagation is per-user and may happen long after any number of
    changes, while a revalidation is per-event and must happen after a specific one.

    **The row is written in the same transaction as the change that caused it.** That is
    what makes "never lost" true: if the broker is down at enqueue time, or the process dies
    between the commit and the enqueue, the row is still there, and the reconciler finds it.
    AD-17's guarantee, applied to a new signal.

    **`paths` is computed once, at enqueue time**, and holds the concrete paths to rebuild.
    The frontend revalidates what it is given and infers nothing, so the cascade rules live
    in one place — `domain.revalidation` — and a path computed at delivery time (from a row
    that has since moved again) cannot drift from the change that caused it.

    **One open request per event.** Two lifecycle changes in quick succession produce one
    open request, not two: the second updates the open row's `event_version` and `paths`.
    That is the enqueue-side idempotency. The delivery side needs no dedup table, because
    rebuilding a page twice is harmless — `revalidatePath` is idempotent by construction.
    """

    class State(models.TextChoices):
        OPEN = "open"  # waiting to be delivered
        DELIVERED = "delivered"  # the frontend acknowledged it
        EXHAUSTED = "exhausted"  # too many failed attempts; kept and surfaced, not retried
        FAILED = "failed"  # permanently refused (a wrong secret); not retried

    retention_category = RetentionCategory.SOURCE_REGISTRY

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="revalidation_requests")
    # The Event's version this signal is about. The frontend skips a rebuild whose data is
    # older than this, so an older page can never be cached over a newer one.
    event_version = models.PositiveIntegerField()
    # The concrete paths to rebuild, computed by `domain.revalidation.paths_for_event`.
    paths = models.JSONField(default=list, encoder=DjangoJSONEncoder)
    state = models.CharField(max_length=16, choices=State.choices, default=State.OPEN)
    attempts = models.PositiveIntegerField(default=0)
    # A reason slug only (AD-13) — never a URL, never a response body, never a stack trace.
    last_error = models.CharField(max_length=32, blank=True, default="")
    requested_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # One open request per event: a second change updates the open row rather than
            # opening a second one.
            models.UniqueConstraint(
                fields=["event"],
                condition=Q(state="open"),
                name="revalidation_open_event_uq",
            ),
            models.CheckConstraint(
                condition=Q(event_version__gte=1), name="revalidation_version_positive_ck"
            ),
            models.CheckConstraint(
                condition=Q(attempts__gte=0), name="revalidation_attempts_nonnegative_ck"
            ),
        ]
        indexes = [
            # The reconciler's access path: the open rows, oldest first.
            models.Index(
                fields=["requested_at"],
                condition=Q(state="open"),
                name="revalidation_open_idx",
            ),
        ]
