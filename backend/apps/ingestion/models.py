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
from django.db.models.expressions import RawSQL
from django.utils import timezone
from pgvector.django import VectorField

from shared.constants import (
    FR25_EMBEDDING_DIMENSIONS,
    HIGH_PRIORITY_CADENCE_MAX,
    HIGH_PRIORITY_METHODS,
    LOW_PRIORITY_CADENCE_MAX,
)
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

    class PausedReason(models.TextChoices):
        """Why a source is paused.

        **Two reasons, and the surface says different things for each.** An editor who
        pauses a source has decided something about the world; the probation has decided
        something about the *yield*. A city whose sources were all paused by hand says
        `paused`; a city whose sources were all paused for zero yield says
        `yielded_nothing`.
        """

        MANUAL = "manual", "Paused by an editor"
        ZERO_YIELD = "zero_yield", "Paused after three runs with no yield"

    class TzCoverage(models.TextChoices):
        FULL = "full"
        PARTIAL = "partial"
        NONE = "none"

    retention_category = RetentionCategory.SOURCE_REGISTRY

    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=16, choices=SourceType.choices)
    url = models.URLField(max_length=2048)
    city = models.CharField(max_length=100, blank=True)
    # The IANA zone of `city`, set at provisioning time from the curated catalog. The last
    # link in FR-60's fallback chain (row C1b): `_venue_for` never creates a venue (D5), so
    # without it a brand-new city rejects every naive or date-only time as `tz_unresolvable`
    # and publishes nothing, forever. Blank on every source that predates this, and a blank
    # one changes no behaviour at all. Validated through `domain.timezones.canonical_zone`
    # on write, like a venue's tz.
    city_tz = models.CharField(max_length=64, blank=True)
    # The canonical `City` this source belongs to, set at provisioning time.
    #
    # **`city` above is a string; this is the link.** A source's city is written as free
    # text — "Brooklyn", "brooklyn ", "Brooklyn, NY" — because a venue names a city the
    # way it is written. But the provisioning service resolves a city *once*, from the
    # curated catalog, and hands the resolved row over. The probation needs "every source
    # for a city" to decide `yielded_nothing`, and a text join on a name that is "as
    # written by the first venue to name it" would miss rows.
    #
    # **Null on every source that was not provisioned.** A hand-registered seed has no
    # city, and a blank one changes no behaviour at all. `PROTECT`ed, like every other
    # ingestion foreign key: a city must not lose its sources without anybody deciding to.
    city_ref = models.ForeignKey(
        "City",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sources",
    )
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
    # How many consecutive runs this source completed **successfully and produced
    # nothing**.
    #
    # **A different counter from `consecutive_failures`, and never the same one.** A
    # source can fetch perfectly and publish nothing, and conflating the two loses the
    # distinction this counter exists to preserve: `consecutive_failures` says "the feed
    # is broken", this says "the feed is fine and has nothing for us".
    #
    # At `ZERO_YIELD_RUN_THRESHOLD` the probation pauses the source (audited, never
    # deleted) and, if every source of the city is paused that way, the city says
    # `yielded_nothing` rather than "collecting" forever.
    consecutive_zero_yield_runs = models.PositiveIntegerField(default=0)
    # Why this source is paused, when it is.
    #
    # **Two reasons, and the surface says different things for each.** An editor who
    # pauses a source has decided something about the world; the probation has decided
    # something about the *yield*. A city whose sources were all paused by hand says
    # `paused`; a city whose sources were all paused for zero yield says
    # `yielded_nothing`. The difference is a fact, not a tone.
    #
    # **Blank means "we do not know"** — a source paused before this column existed, or
    # by a path that does not set the reason. The probation reads blank as a hand-pause,
    # because "somebody paused this" is a stronger claim than "the probation paused this",
    # and only the probation's own pauses should produce `yielded_nothing`.
    paused_reason = models.CharField(max_length=32, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    stale_since = models.DateTimeField(null=True, blank=True)
    # Set when the scheduler enqueues a run, cleared when the run's job ends: a claimed source is
    # never enqueued twice. A claim older than INGEST_CLAIM_TTL is a lost job.
    ingest_claimed_at = models.DateTimeField(null=True, blank=True)
    # FR-16's Source Reliability Score, denormalised onto the source (design
    # reliability-recompute-and-escalation D1).
    #
    # **The field answers "what is this source's score right now?"; the history answers "what
    # was it last week?"** A field cannot answer the second — that is the spike rule's question
    # — so the field is not a substitute for `SourceReliabilityScore`, it is the cheap half.
    #
    # **Null until the first recompute, and it means "not yet computed", not "bad".** A source
    # with no score reads as the 0.50 prior through the read service; the column is only ever
    # written by the recompute job, in the same transaction as the row it computed, so the two
    # cannot disagree.
    #
    # **Never a reason to pause.** FR-16 is explicit: escalation, never removal. Nothing in
    # that item writes `status`, `ingestion_cadence` or any other column of this row, and a
    # test asserts the row is unchanged after an escalation.
    reliability_score = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    reliability_scored_at = models.DateTimeField(null=True, blank=True)
    # FR-16: the weekly recompute's claim marker, on the same shape as `ingest_claimed_at`.
    # Set when the recompute job claims the source, cleared when it finishes.
    #
    # **The claim has to be persisted to be a claim.** A `SELECT ... FOR UPDATE SKIP LOCKED`
    # that releases its lock with its transaction prevents nothing: the recompute runs in its
    # own transaction, so two overlapping ticks both get the same source. The marker is what
    # makes the claim outlive the transaction that took it — the same reason the scheduler's
    # claim is a column and not a lock (design D10).
    #
    # **A claim older than RELIABILITY_CLAIM_TTL is a lost job**, and the source is claimed
    # again rather than being skipped forever.
    reliability_claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(ingestion_cadence__gt=timedelta(0)), name="source_cadence_positive_ck"
            ),
            # FR-53: a source's cadence may not exceed its tier's ceiling, so a cancellation
            # can be detected inside the window the product promises.
            #
            # **The "else" branch is "not a high-priority method", not "a lower-priority
            # method".** That is deliberate: the Python derivation treats any method outside
            # the high set as lower-priority, and the two layers must agree exactly. A
            # method added later — or one outside the choices — gets the 24-hour ceiling
            # until someone classifies it, which is safe by default: a new acquisition
            # method cannot opt itself out of the guarantee by being unclassified.
            models.CheckConstraint(
                condition=(
                    Q(acquisition_method__in=HIGH_PRIORITY_METHODS)
                    & Q(ingestion_cadence__lte=HIGH_PRIORITY_CADENCE_MAX)
                )
                | (
                    ~Q(acquisition_method__in=HIGH_PRIORITY_METHODS)
                    & Q(ingestion_cadence__lte=LOW_PRIORITY_CADENCE_MAX)
                ),
                name="source_cadence_within_priority_ceiling_ck",
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


class CityProvisioning(UUIDv7Model):
    """What we did about a city, so the surface can tell the truth about it.

    **One row per city, ever.** The `OneToOneField` is the idempotency guarantee at the
    database level: a second provisioning of the same city cannot create a second row, so
    "provisioning is idempotent" is a fact the schema holds rather than a promise the
    service makes.

    **The row holds no city *name*.** It holds the `City` foreign key, which identifies the
    city without restating where a reader lives. AD-13's discipline: the audit row says
    *that* a city was provisioned; the value stays out of the log. (A `Source`'s own city is
    a public fact about a place and lives on the source row — a different thing, and this
    item does not touch it.)

    **`status` is the sentence the surface reads.** `collecting` is the honest word for
    "we registered sources and are waiting for events" — the city has no events until the
    scheduler has run and a source has answered, and saying otherwise would be a claim we
    cannot keep.

    **The city is `PROTECT`ed, not cascaded.** A `City` is never deleted — `Venue` and
    `EventFit` already protect it — so the rule is academic today. But a cascading
    delete would mean that a city could one day lose its provisioning record without
    anybody deciding to, and the row is the sentence the surface reads about a city. If a
    city is ever to be removed, that has to be a decision somebody makes.
    """

    retention_category = RetentionCategory.SOURCE_REGISTRY

    class Status(models.TextChoices):
        #: Sources registered; we are waiting for the first events.
        COLLECTING = "collecting"
        #: The city has published events. Written by the ingest path, not by provisioning.
        LIVE = "live"
        #: No template covers this city — or every template needs a credential this
        #: deployment does not have. A normal outcome, not an error.
        NO_PROVIDERS = "no_providers"
        #: Providers exist, but their events produced nothing. Written after an ingest
        #: cycle, not by provisioning.
        YIELDED_NOTHING = "yielded_nothing"
        #: Provisioning stopped for this city. Written by the probation job.
        PAUSED = "paused"
        #: Provisioning failed. `last_error_code` says why, and the row is left alone —
        #: a reader's later pick is not a retry request.
        FAILED = "failed"

    city = models.OneToOneField(
        City, on_delete=models.PROTECT, related_name="provisioning", primary_key=False
    )
    status = models.CharField(max_length=16, choices=Status.choices)
    #: How many sources this provisioning registered. A count, never a list — the sources
    #: themselves are rows, and this is the sentence "how many did we get".
    source_count = models.PositiveIntegerField(default=0)
    #: The failure that stopped provisioning, when one did. Blank when none — the same
    #: shape `Source.last_error_code` uses, so one vocabulary reads both.
    last_error_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~Q(status=""), name="city_provisioning_status_ck"),
        ]

    def __str__(self) -> str:
        return f"{self.city_id}: {self.status}"


class CityCoverageRequest(UUIDv7Model):
    """A reader asked us to cover a city we have not covered.

    **The fallback for the cities automatic collection cannot reach.** When a city's
    provisioning says `no_providers`, `failed`, `yielded_nothing` or `paused`, the
    surface says so and offers the reader the one way out: ask us to go and cover it.
    This row is what that ask becomes.

    **One row per city, enforced by the database.** The `UniqueConstraint` is the
    guarantee, not a promise the service makes — a second writer that did not know
    about the first would be stopped by PostgreSQL rather than by a code path nobody
    remembered to write. **The constraint is *named***, so a test can assert that it
    was that constraint which refused the duplicate and not something else.

    **The row carries no user id.** It is about a *place*, and it says two things:
    which city, and how many people have asked. The count is a **counter column**, not
    a per-user join table — the editorial question is "how many people want this city
    covered?", and the answer to that is a number. A per-user answer would put a user
    id beside a city, which is the pairing AD-13 is careful about, and nobody could
    act on it: the reader's own state is in their own session, and the count is what
    editorial reads.

    **The city is `PROTECT`ed.** A `City` is never deleted, and a cascading delete
    would mean a request could vanish without anybody deciding to — the same argument
    `CityProvisioning` makes about its own row.

    **The city is never minted here.** This row is raised for a city we already have:
    a city we have never heard of is a *pick*, and a pick provisions
    (`services/city_provisioning.py`). Minting one from a request would put a place
    into the registry that no reader chose, and would do it every time somebody
    opened a page.
    """

    retention_category = RetentionCategory.SOURCE_REGISTRY

    #: The city that was asked for. A relation, never a restated name — the name is a
    #: location, and AD-13 keeps locations out of the rows that cross into the log.
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="coverage_requests")
    #: How many readers have asked for this city. **A count, never a list** — the same
    #: shape `CityProvisioning.source_count` uses, and for the same reason: the
    #: sources are rows, and this is the sentence "how many did we get".
    request_count = models.PositiveIntegerField(default=1)
    #: When the request was **first** raised. It does not move on a later request —
    #: "when did somebody first tell us about this city" is the editorial question, and
    #: a timestamp that moved would answer a different one.
    created_at = models.DateTimeField(auto_now_add=True)
    #: When the request was last raised. `created_at` is the first time; this is the
    #: most recent.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["city"], name="city_coverage_request_city_uq"),
            models.CheckConstraint(
                condition=Q(request_count__gte=1), name="city_coverage_request_count_ck"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.city_id}: {self.request_count}"


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
        # An editor's FR-57 verdict: this listing is bad. Never a delete (`editorial_state`).
        #
        # **This is not `Event.Status`.** `Status` is what the *source* claims about whether
        # the event happens; `rejected` is what *we* claim about the listing. A duplicate
        # listing's underlying event still happens, so `status = cancelled` would be false.
        #
        # Every public read filters `publication_status == PUBLISHED` by equality, so a
        # rejected Event is absent from all of them with no read change. Invisibility is
        # only half of a reject, though: see `EventStateChange.Kind.DELISTED` for the half
        # that reaches the people who saved it.
        REJECTED = "rejected"

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
    # FR-25: the event's embedding vector — the thing the dismissal cluster compares.
    #
    # **It is nullable, and null means "not embedded yet", not "empty".** The backfill is
    # a resumable command, not a migration: a migration that backfilled would embed the
    # whole corpus inside a schema transaction, and a corpus is too big to hold a
    # transaction open for. So the column is added empty and filled afterwards, and an
    # event with no vector is simply absent from the cluster's candidates — a missing
    # vector is not a zero vector, and a zero vector would be a real point that happens
    # to be at the origin, which is not the same thing at all.
    #
    # **The `vector` type lives in `public`, not `catalog`.** The init script installs
    # `CREATE EXTENSION IF NOT EXISTS vector` in `public`, so the column type is written
    # `public.vector(256)` and the migration says so explicitly.
    #
    # **256 dimensions, because `voyage-4-lite` is a Matryoshka model.** The spine pins
    # 256 or 512; 256 is half the storage for the same cosine at the same threshold.
    #
    # **It is not in `LIFECYCLE_FIELDS`.** The vector is a derived reading of the event's
    # text, not a fact about the event's identity or schedule — so changing it does not
    # bump `event_version` and does not supersede the row. The embedding can be
    # recomputed for the same event any number of times.
    embedding = VectorField(dimensions=FR25_EMBEDDING_DIMENSIONS, null=True, blank=True)
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
        # An editor rejected the listing, and this is the half of that verdict which
        # travels. `publication_status = rejected` hides the Event; it bumps no version and
        # writes no row, so on its own it would leave every saver's reminders firing for an
        # event editorial has ruled bad. This kind rides the AD-17 outbox to cancel them.
        #
        # **Named for the consequence, not the verdict.** `rejected` is already taken twice
        # over — `domain.confidence.Gate.REJECT` means "never becomes an Event", and
        # `ReviewItem.resolution` has `withdrawn` for a system close. Three words for "no"
        # that mean three different things would be unreadable, so the outbox carries what
        # happened to the listing rather than what the editor clicked.
        DELISTED = "delisted"
        RELISTED = "relisted"  # an editor reversed a rejection; ingestion never can

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


class SourceObservation(AppendOnlyModel, ActorColumns, UUIDv7Model):
    """One editorial verdict, recorded against the Source whose event it was about (FR-16).

    **The input side of the Source Reliability Score, stored as a fact and never as a score.**
    `domain/reliability.py` holds the arithmetic and takes plain counts; this is the table
    those counts come from. Keeping them apart is what lets the score be recomputed from
    scratch at any time, and what makes a week-over-week comparison possible at all.

    **Why a table rather than the audit log.** Every command here writes an
    `IngestionAuditEntry` too, and the counts could in principle be scraped from it — but
    they would have to be read out of a JSON column, and the audit log's retention is 24
    months (AD-15) while a Source's reliability is meant to be a standing fact about it.

    **`edited` is its own kind, and its sign is decided** (design
    `reliability-recompute-and-escalation` D4): an edit is **negative**, because the source's
    facts were wrong and an editor had to change them. `dismissed` is **neutral** (D5) — an
    editor looked at a `source_reliability` item and found no fault in the source, which is
    not a check of any of its events. The signs themselves live once, in
    `shared.constants.OBSERVATION_SIGNS`, and both the recorder and the recompute job read
    that table, so there is one counting rule and not two.

    **One verdict is one observation, however many reports it carried** (D8). The
    `source_observation_item_uq` constraint is what makes that true — an event's reports all
    live on one `user_reported` item, so a verdict on that event can only ever close one item
    and therefore record one observation. `report_count` keeps the *fact* of the five without
    multiplying the *weight* of the verdict.

    Append-only: a verdict is history the moment it is recorded.
    """

    class Kind(models.TextChoices):
        APPROVED = "approved"  # FR-16 positive
        REJECTED = "rejected"  # FR-16 negative
        EDITED = "edited"  # FR-16 negative: the source's facts were wrong (design D4)
        DISMISSED = "dismissed"  # FR-25's named input; neutral (design D5, D6)

    retention_category = RetentionCategory.SOURCE_REGISTRY

    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="observations")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    # The event the verdict was about. Null for a `source_reliability` item, which is about
    # the Source itself and names no event.
    event = models.ForeignKey(
        "Event", on_delete=models.PROTECT, null=True, blank=True, related_name="observations"
    )
    review_item = models.ForeignKey(
        "ReviewItem", on_delete=models.PROTECT, related_name="observations"
    )
    # How many user reports the verdict's item carried when it was closed (design D8).
    #
    # **A count, never a list.** The reports themselves live in `personal.EventReport` and are
    # purged with the account; the tally on the `ReviewItem` is the only cross-wall-safe record
    # of them, and this column freezes it at the moment of the verdict.
    #
    # **It does not multiply the observation.** One verdict counts as one negative however many
    # reports it answered — the sign is read once from `OBSERVATION_SIGNS`, and the count is
    # carried as a fact beside it.
    report_count = models.PositiveIntegerField(default=0)
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        base_manager_name = "objects"
        constraints = [
            # One observation per resolution. A verdict is recorded once; a second row for the
            # same item would double-count the source.
            models.UniqueConstraint(fields=["review_item"], name="source_observation_item_uq"),
            actor_check("source_observation_actor_ck"),
        ]
        indexes = [
            # The recompute's query: one source's observations, newest first, for the
            # posterior and the week-over-week rate.
            models.Index(fields=["source", "-occurred_at"], name="source_observation_src_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.source_id}: {self.kind}"


class SourceReliabilityScore(AppendOnlyModel, UUIDv7Model):
    """One computation of FR-16's score for one source, for one week (design D2).

    **The output side of the score, stored as a conclusion and never as a fact.**
    `SourceObservation` records what happened; this records what was concluded from it. Keeping
    the two apart is what lets the score be recomputed from scratch at any time, and what makes
    a week-over-week comparison possible at all — a single field on `Source` cannot answer
    "what was it last week?".

    **One row per (source, period), and the period is the key.** `period_start` is the ISO
    Monday 00:00 UTC of the week the row computes, and the unique constraint on
    `(source, period_start)` **is** the idempotence guarantee: a re-run within the same period
    collides and **updates** the row rather than inserting a second one. A score that is a
    week stale is a score that is wrong, so the re-run refreshes rather than skips.

    **Append-only, with one exception, and the exception is narrow.** A computed row is
    history the moment it is computed — that is what makes it comparable week to week. The one
    thing that may change is the *same period's* conclusion: `score`, `positives`, `negatives`
    and `computed_at`, and nothing else. The `catalog.guard_reliability_score` trigger
    enforces exactly that: the source and the period are fixed, and the rest may be rewritten
    only within the period the row already names.

    **The score is `domain/reliability.py`'s output, never a second implementation.** The
    arithmetic lives there; this table stores what it returned.
    """

    #: The columns a same-period refresh may rewrite. The trigger names the same set; a test
    #: compares the two, so the Python guard and the database guard cannot drift.
    append_only_mutable = frozenset({"score", "positives", "negatives", "computed_at"})

    retention_category = RetentionCategory.SOURCE_REGISTRY

    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="reliability_scores")
    # The Monday 00:00 UTC of the week this row computes. A `DateField`, not a datetime: a
    # week is a calendar date, and `date_trunc('week', ...)` is a date.
    period_start = models.DateField()
    # The score FR-16 asks for: the posterior, floored at 0.32 until 30 observations.
    score = models.DecimalField(max_digits=4, decimal_places=2)
    # The counts the score was computed from, so a row can be checked without re-reading the
    # observations — and so the weekly rates can be derived from the same history.
    positives = models.PositiveIntegerField(default=0)
    negatives = models.PositiveIntegerField(default=0)
    computed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        base_manager_name = "objects"
        constraints = [
            # The idempotence guarantee, enforced by Postgres rather than by good manners.
            models.UniqueConstraint(
                fields=["source", "period_start"], name="source_reliability_score_period_uq"
            ),
            models.CheckConstraint(
                condition=Q(score__gte=0, score__lte=1), name="source_reliability_score_range_ck"
            ),
            # It is a week, not a moment. `date_trunc('week', ...)` is Postgres's own
            # ISO-week-to-Monday truncation, so the database and the service agree on where
            # a week starts without either of them hard-coding an offset.
            models.CheckConstraint(
                condition=Q(period_start=RawSQL("date_trunc('week', period_start)", [])),
                name="source_reliability_score_week_ck",
            ),
        ]
        indexes = [
            # The recompute's predecessor lookup: one source's rows, newest first.
            models.Index(fields=["source", "-period_start"], name="reliability_score_period_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.source_id}: {self.score} ({self.period_start})"


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


class ReviewItem(UUIDv7Model):
    """One entry in the FR-57 editorial review queue (design: review-queue-model D1-D12).

    **A target is an Event or a Source, never both (D1).** `user_reported` and `in_review` are
    about an Event; `source_reliability` (FR-16 escalation) is about a Source. Both are
    `catalog` rows, so the references are real foreign keys (AD-3 only forbids relations
    across the schema wall).

    **At most one open item per (target, reason) (D2).** A second raise bumps the open row's
    tallies and `last_raised_at` (`services.review_queue.raise_review_item`); a raise after
    the item closed opens a new row, so a verdict is history and is never re-opened.

    **No user identity (D4, AD-3).** A report reaches this row as a category tally only. The
    reporter lives in `personal.EventReport`; even the audit row for a report-raised item is
    written as a system actor.

    **A resolved row is immutable, and a row is never deleted (D7)**: the
    `catalog.guard_review_item` trigger in migration 0008 holds both, and fixes `FIXED_FIELDS`
    on an open row too. Delete is allowed only inside a retention purge.
    """

    class Reason(models.TextChoices):
        USER_REPORTED = "user_reported"  # FR-59: raised by an EventReport; 24h SLA
        IN_REVIEW = "in_review"  # the event is quarantined (publication_status = in_review)
        SOURCE_RELIABILITY = "source_reliability"  # FR-16 escalation; targets a Source

    class Status(models.TextChoices):
        OPEN = "open"
        RESOLVED = "resolved"

    class Resolution(models.TextChoices):
        APPROVED = "approved"  # event items, by an editor
        EDITED = "edited"  # event items, by an editor
        REJECTED = "rejected"  # event items, by an editor
        DISMISSED = "dismissed"  # source items, by an editor: no action on the source
        WITHDRAWN = "withdrawn"  # either, by the system: the target left review another way

    class ReportCategory(models.TextChoices):
        """FR-59's four categories, the one vocabulary `EventReport` also uses (D3)."""

        WRONG_DATE_TIME = "wrong_date_time"
        WRONG_VENUE = "wrong_venue"
        DOES_NOT_EXIST = "does_not_exist"
        DUPLICATE = "duplicate"

    # The column each category's tally lives in (D3). `report_count` is their sum.
    REPORT_FIELDS: ClassVar[dict[str, str]] = {
        ReportCategory.WRONG_DATE_TIME: "reports_wrong_date_time",
        ReportCategory.WRONG_VENUE: "reports_wrong_venue",
        ReportCategory.DOES_NOT_EXIST: "reports_does_not_exist",
        ReportCategory.DUPLICATE: "reports_duplicate",
    }
    # Fixed for the row's whole life, open or not (D7). The trigger names the same columns;
    # tests/ingestion/test_review_item_model.py compares the two.
    FIXED_FIELDS: ClassVar[tuple[str, ...]] = ("reason", "event", "source", "raised_at")

    retention_category = RetentionCategory.SOURCE_REGISTRY

    reason = models.CharField(max_length=24, choices=Reason.choices)
    event = models.ForeignKey(
        Event, on_delete=models.PROTECT, null=True, blank=True, related_name="review_items"
    )
    source = models.ForeignKey(
        Source, on_delete=models.PROTECT, null=True, blank=True, related_name="review_items"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    resolution = models.CharField(max_length=16, choices=Resolution.choices, blank=True, default="")

    reports_wrong_date_time = models.PositiveIntegerField(default=0)
    reports_wrong_venue = models.PositiveIntegerField(default=0)
    reports_does_not_exist = models.PositiveIntegerField(default=0)
    reports_duplicate = models.PositiveIntegerField(default=0)

    raised_at = models.DateTimeField(default=timezone.now)
    last_raised_at = models.DateTimeField(default=timezone.now)
    # FR-57's 24h SLA, from the first report; only `user_reported` has one (D8).
    due_at = models.DateTimeField(null=True, blank=True)

    # Who resolved it, by value (`shared.actor.Actor` rules, D5). Empty while open.
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by_kind = models.CharField(max_length=16, blank=True, default="")
    resolved_by_id = models.UUIDField(null=True, blank=True)
    resolved_by_label = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def report_count(self) -> int:
        return sum(getattr(self, column) for column in self.REPORT_FIELDS.values())

    class Meta:
        constraints = [
            # D1: the reason decides the target, and exactly one target is set.
            models.CheckConstraint(
                condition=(
                    Q(
                        reason__in=["user_reported", "in_review"],
                        event__isnull=False,
                        source__isnull=True,
                    )
                    | Q(reason="source_reliability", source__isnull=False, event__isnull=True)
                ),
                name="review_item_target_ck",
            ),
            # D2: one open item per (target, reason). NULLs are distinct, so each constraint
            # only bites its own kind of target.
            models.UniqueConstraint(
                fields=["event", "reason"],
                condition=Q(status="open"),
                name="review_item_open_event_reason_uq",
            ),
            models.UniqueConstraint(
                fields=["source", "reason"],
                condition=Q(status="open"),
                name="review_item_open_source_reason_uq",
            ),
            # D3: tallies belong to user reports only.
            models.CheckConstraint(
                condition=Q(reason="user_reported")
                | Q(
                    reports_wrong_date_time=0,
                    reports_wrong_venue=0,
                    reports_does_not_exist=0,
                    reports_duplicate=0,
                ),
                name="review_item_tallies_ck",
            ),
            # D8: the SLA exists exactly when the reason is a user report.
            models.CheckConstraint(
                condition=Q(reason="user_reported", due_at__isnull=False)
                | (~Q(reason="user_reported") & Q(due_at__isnull=True)),
                name="review_item_due_ck",
            ),
            # D6: (a) open carries no resolution; (b)-(d) resolved carries all of it, the
            # resolver follows the Actor rules, an editor's verdict fits the target, and only
            # `withdrawn` may be recorded by the system.
            models.CheckConstraint(
                condition=(
                    Q(
                        status="open",
                        resolution="",
                        resolved_at__isnull=True,
                        resolved_by_kind="",
                        resolved_by_id__isnull=True,
                        resolved_by_label="",
                    )
                    | Q(
                        status="resolved",
                        resolution__in=["approved", "edited", "rejected"],
                        event__isnull=False,
                        resolved_at__isnull=False,
                        resolved_by_kind="user",
                        resolved_by_id__isnull=False,
                        resolved_by_label="",
                    )
                    | Q(
                        status="resolved",
                        resolution="dismissed",
                        source__isnull=False,
                        resolved_at__isnull=False,
                        resolved_by_kind="user",
                        resolved_by_id__isnull=False,
                        resolved_by_label="",
                    )
                    | (
                        Q(
                            status="resolved",
                            resolution="withdrawn",
                            resolved_at__isnull=False,
                            resolved_by_kind="system",
                            resolved_by_id__isnull=True,
                        )
                        & ~Q(resolved_by_label="")
                    )
                ),
                name="review_item_resolution_ck",
            ),
        ]
        indexes = [
            # D12: the queue's access path — open items, deadline first, then oldest.
            models.Index(
                fields=["due_at", "raised_at"],
                condition=Q(status="open"),
                name="review_item_open_idx",
            ),
        ]
