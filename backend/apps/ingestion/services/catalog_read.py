"""The published read interface over the catalog (AD-2, AD-4, AD-12).

The `catalog` app reads events through here, never through `apps.ingestion.models`
(import contract `models-ingestion`). This module owns the *query*; the wire shapes live in
`apps/catalog/schemas.py`, because the surface owns the contract (AD-19).

The interface hands over plain data — a frozen dataclass, not a model instance — so the
calling app never holds a reference to `apps.ingestion.models` and the wall holds without
either side knowing the other's models.

Only published, non-superseded, upcoming events are visible. An `in_review` event is not
digest-eligible and not publicly listed (AD-6, AD-8), and a superseded Event is terminal:
the live one that replaced it is listed instead (D7). A `tz_review_pending` event is
published and *is* listed, carrying the flag so the frontend can mark its time as
approximated.

`now` is an explicit parameter, like every other command here: no time-freezing library, and
each boundary is testable at the exact second.

**Two reads, two questions.** `list_public_events` answers "what may a person browse?".
`list_public_candidates` answers "what may a Pulse Digest rank?" — a stricter question,
answered by a stricter set of gates (the digest's confidence thresholds and FR-14's
staleness bound), and it carries the extra facts composition needs (the Source Badge, the
venue's country, the confidences). They are separate functions rather than one function
with flags, because the public catalog's meaning is load-bearing: `list_supported_cities`
decides which cities the preview may offer, and a parameter that could switch the public
list's gates off would put that at risk.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from django.db.models import QuerySet

from apps.ingestion.models import Event
from apps.ingestion.services.chip_matching import chip_keys_for
from apps.ingestion.services.source_badges import source_badge_for_type
from domain.errors import NotFoundError
from shared.constants import (
    DIGEST_STALE_TTL_MULTIPLIER,
    EXTRACTION_CONFIDENCE_PUBLISH,
    TZ_INFERENCE_CONFIDENCE_DIGEST,
)
from shared.db import CATALOG

# A page of public events. The cap keeps one request from asking for the whole catalog.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# The candidate pool a digest ranks from.
#
# Not a page size. A digest has three slots, and filling them with *distinct* events after
# scoring needs more than three candidates — a candidate can lose on time of day, on
# bucket, or to a duplicate of a higher-scoring event. Sixty is several times the three
# slots and several times the preview's three cards, which leaves room to fill every slot
# from a crowded city without the pool itself becoming the ranking's tiebreaker.
#
# The read runs once per user per day, so the pool has to be cheap for *all* the users, not
# just one: sixty rows with the venue and the source joined is one indexed query per user
# per day. The cap stops a caller asking for the whole catalog by accident.
CANDIDATE_POOL_SIZE = 60
MAX_CANDIDATE_POOL_SIZE = 200

#: How many rows the SQL may fetch for every candidate the caller asked for.
#:
#: FR-14's staleness bound is per source, so it cannot be expressed in SQL — the rows it
#: excludes are dropped in Python. This factor buys room for those rows: a pool whose
#: events are mostly fresh fills from the first page, and a pool that is mostly stale may
#: fill with fewer than `limit` rows rather than fetching the whole catalog.
#:
#: The trade is deliberate. The alternative — fetching everything to be sure — makes the
#: read's cost depend on the size of the catalog, and this read runs once per user per
#: day.
CANDIDATE_OVERFETCH_FACTOR = 4


class EventNotFoundError(NotFoundError):
    """The requested event isn't in the public catalog (or was never published)."""

    default_message = "We couldn't find that event."


@dataclass(frozen=True)
class PublicEvent:
    """One public event as plain data.

    Deliberately not the model: the caller gets a value it can read without importing
    `apps.ingestion.models`. The fields are the ones the public catalog publishes.
    """

    id: UUID
    slug: str
    title: str
    canonical_url: str
    start_time_utc: datetime
    start_time_tz: str
    end_time_utc: datetime | None
    venue_name: str | None
    venue_city: str | None
    status: str
    event_version: int
    source_name: str
    tz_review_pending: bool


def _public_events() -> QuerySet:
    """Published, not superseded. The venue and source come along in the same query."""
    return (
        Event.objects.using(CATALOG)
        .filter(publication_status=Event.PublicationStatus.PUBLISHED)
        .exclude(status=Event.Status.SUPERSEDED)
        .select_related("venue", "source")
    )


def _to_public_event(event: Event) -> PublicEvent:
    venue = event.venue
    return PublicEvent(
        id=event.id,
        slug=event.slug,
        title=event.title,
        canonical_url=event.canonical_url,
        start_time_utc=event.start_time_utc,
        start_time_tz=event.start_time_tz,
        end_time_utc=event.end_time_utc,
        venue_name=venue.name if venue else None,
        venue_city=venue.city if venue else None,
        status=event.status,
        event_version=event.event_version,
        source_name=event.source.name,
        tz_review_pending=event.tz_review_pending,
    )


def list_public_events(
    *,
    now: datetime,
    city: str | None = None,
    starts_after: datetime | None = None,
    starts_before: datetime | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[PublicEvent], int]:
    """The upcoming public events, soonest start first, and the total count of that set.

    `now` bounds the list to events that have not started yet. `city` matches the venue's
    city exactly, case-insensitively; an event without a venue has no city and never
    matches. `starts_after` and `starts_before` are inclusive bounds on the start time.

    Ordering is `start_time_utc` then `id`: the id tiebreak makes the order total, so two
    events sharing a start time can't fall on both pages (the UUIDv7 is time-ordered, so
    the tiebreak is stable).
    """
    queryset = _public_events().filter(start_time_utc__gte=now)
    if city:
        queryset = queryset.filter(venue__city__iexact=city)
    if starts_after is not None:
        queryset = queryset.filter(start_time_utc__gte=starts_after)
    if starts_before is not None:
        queryset = queryset.filter(start_time_utc__lte=starts_before)

    queryset = queryset.order_by("start_time_utc", "id")
    total = queryset.count()
    page = max(page, 1)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    offset = (page - 1) * page_size
    items = [_to_public_event(event) for event in queryset[offset : offset + page_size]]
    return items, total


def get_public_event(*, event_id: UUID, now: datetime | None = None) -> PublicEvent:
    """One public event by id.

    An event that isn't public (unpublished, `in_review`) or that was superseded is not
    found: the public catalog has one truth, and a hidden event reads as absent.

    **`now` bounds by "has not started yet".** It is the rule the module's own docstring
    states — "Only published, non-superseded, **upcoming** events are visible" — and it is
    the set a *save* may draw from: you take an event into your calendar while it is still
    ahead of you. Pass `now` to enforce it.

    Passing `now=None` skips the bound, and that is deliberate: a record of something the
    user already saved has to stay readable after the event has started. The user's own
    calendar does not un-save an event because it began.
    """
    queryset = _public_events()
    if now is not None:
        queryset = queryset.filter(start_time_utc__gte=now)
    try:
        event = queryset.get(pk=event_id)
    except Event.DoesNotExist:
        raise EventNotFoundError(details={"event_id": str(event_id)}) from None
    return _to_public_event(event)


@dataclass(frozen=True)
class PublicEventCandidate:
    """One public event as a *digest candidate*: the facts composition may rank on.

    Plain data — not the model — so the calling app never holds a reference to
    `apps.ingestion.models` and the wall holds without either side knowing the other's
    models.

    **This is not `PublicEvent`.** The public event is the public catalog's wire shape;
    this one carries the extra facts a digest needs and the public surface never reads —
    the confidences that gated it, the badge that says where the facts came from, the
    source's staleness window. Widening `PublicEvent` would put digest-only fields on the
    public catalog's contract.

    **`source_badge` is resolved here, on the catalog side, not by the caller.** The badge
    is a mapping from a `Source` to a claim about how its facts were obtained, and the
    caller is not allowed to hold a `Source`. Carrying the inputs instead would mean
    copying the mapping table into the app that may not know about `Source`, and the two
    copies would drift.
    """

    id: UUID
    slug: str
    title: str
    canonical_url: str
    start_time_utc: datetime
    start_time_tz: str
    end_time_utc: datetime | None
    venue_name: str | None
    venue_city: str | None
    venue_country_code: str | None
    status: str
    event_version: int
    source_name: str
    #: The Source Badge type — the server names the type, the client owns the label.
    source_badge: str
    #: The `Source.source_type` the badge was derived from, kept for the audit trail.
    source_type: str
    #: Whether the source's facts were obtained by crawling (the badge's other input).
    acquisition_method: str
    #: The gate that admitted this event, carried so a digest can say why it is eligible.
    #: A `Decimal`, not a float and not a string: `shared/constants.py` is explicit that
    #: "a float 0.8 is not exactly 4/5, and a boundary test on a float would be a lie".
    extraction_confidence: Decimal
    tz_inference_confidence: Decimal
    #: Whether the timezone is still under review — the event is eligible, but its time is
    #: approximated and the frontend marks it as such.
    tz_review_pending: bool
    #: When the catalog last saw the event at the source. FR-14's staleness bound is
    #: measured from here.
    last_seen_at: datetime
    #: The interest-chip keys this event belongs to, matched from its own title and
    #: description (FR-1). The user's half of the interest overlap is the chips they
    #: picked at onboarding; this is the event's half, and without it the largest term
    #: in the Relevance Pulse would be pinned to zero.
    chip_keys: tuple[str, ...] = ()


def _to_public_candidate(event: Event) -> PublicEventCandidate:
    venue = event.venue
    source = event.source
    return PublicEventCandidate(
        id=event.id,
        slug=event.slug,
        title=event.title,
        canonical_url=event.canonical_url,
        start_time_utc=event.start_time_utc,
        start_time_tz=event.start_time_tz,
        end_time_utc=event.end_time_utc,
        venue_name=venue.name if venue else None,
        venue_city=venue.city if venue else None,
        venue_country_code=venue.country_code if venue else None,
        status=event.status,
        event_version=event.event_version,
        source_name=source.name,
        source_badge=source_badge_for_type(
            source_type=source.source_type,
            acquisition_method=source.acquisition_method,
        ),
        source_type=source.source_type,
        acquisition_method=source.acquisition_method,
        extraction_confidence=event.extraction_confidence,
        tz_inference_confidence=event.tz_inference_confidence,
        tz_review_pending=event.tz_review_pending,
        last_seen_at=event.last_seen_at,
        chip_keys=chip_keys_for(title=event.title, description=event.description),
    )


def list_public_candidates(
    *,
    now: datetime,
    city: str | None = None,
    limit: int = CANDIDATE_POOL_SIZE,
) -> list[PublicEventCandidate]:
    """The public events a digest may rank, soonest first.

    **Every gate is the shared constant** (AD-8), applied in the database:

    - `extraction_confidence >= EXTRACTION_CONFIDENCE_PUBLISH` — below it the event is
      "never published to a Pulse Digest";
    - `tz_inference_confidence >= TZ_INFERENCE_CONFIDENCE_DIGEST` — AD-6: below 0.7 an
      Event is "not eligible for any Pulse Digest until editorial review completes";
    - published, not superseded, and starting in the future.

    Both bounds are **inclusive**: an event one hundredth below the gate is excluded, one
    exactly at it is included. The thresholds are `Decimal`s and the columns are
    `DecimalField`s, so no float ever appears in the comparison — a float 0.7 is slightly
    below Decimal 0.70 and would land an event in the wrong band.

    **A `tz_review_pending` event is eligible.** Between the digest gate and the
    auto-publish threshold an event publishes *with* its time still under review: it is
    published, it is above the gate, and its time is approximated. The flag travels with
    it so the frontend can mark the time.

    **A superseded event is excluded by its status alone.** The database holds the
    supersession consistent — `event_superseded_consistent_ck` says a superseded Event
    names its replacement and a live one names none — so a row with `status != superseded`
    and a `superseded_by` pointer cannot exist. The pointer is therefore not filtered on
    separately: a second filter for a state the database forbids would be a second thing
    to keep true, and it could only ever be true in the same rows the status filter
    already admits.

    **A cancelled or postponed event is a candidate.** `status` is filtered for
    `superseded` and nothing else, so `cancelled` and `postponed` events reach the pool.
    That is the same set the public catalog lists — the two reads must not disagree about
    what exists — and what happens to a cancelled event is the composition service's call:
    a cancelled event is still a real event with a real place in the user's city, and
    dropping it here would hide the cancellation rather than report it. The card can mark
    it. **This is stated here rather than left implicit**, because a digest offering a
    cancelled event is the kind of thing a user notices.

    **Staleness (FR-14).** An event last seen at the source more than
    `DIGEST_STALE_TTL_MULTIPLIER × source.freshness_ttl_hours` ago is not surfaced in a
    fresh digest. The bound is measured from `Event.last_seen_at` — when the catalog last
    saw the event — not from `updated_at`, which moves whenever we touch the row. The
    comparison is **inclusive** at the boundary: "older than" is exclusive, and an event
    exactly at the bound is not older than it.

    **`now` must be timezone-aware.** Every read in this codebase takes an aware instant;
    a naive one is a caller's bug and Django's own comparison will say so first.

    **City matching is equality, case-insensitive.** `Venue` has no coordinates, so
    "nearby" is a band — same city, same country, elsewhere — and this read matches the
    city exactly. An event with no venue has no city and never matches: the event fit made
    the same call, giving such events no row rather than a guessed one. With no city, the
    read returns every eligible event, which is what the serendipity slot wants for a user
    whose city is not known.

    **The pool is bounded** by `limit`, capped at `MAX_CANDIDATE_POOL_SIZE`. A `limit` of
    zero or less returns nothing: a caller that asks for no candidates must not be handed
    one.
    """
    if limit <= 0:
        return []
    limit = min(limit, MAX_CANDIDATE_POOL_SIZE)

    # FR-14's bound is per source, because the TTL is a per-source fact. The database
    # cannot compare a column against another column times a multiplier, so the bound is
    # computed per row and applied in Python — after the SQL has already narrowed the set
    # by the gates that *can* be expressed there.
    #
    # **The SQL fetch is bounded too.** Without a `LIMIT`, a catalog whose events are
    # mostly stale would hand every one of them to Python before the first candidate was
    # found, and the read's cost would depend on the size of the catalog rather than on
    # the size of the pool. The over-fetch factor buys room for the stale rows the Python
    # filter will drop: a pool whose rows are mostly fresh fills from the first page.
    #
    # The trade is deliberate and stated: a catalog that is *mostly* stale may fill the
    # pool from fewer than `limit` rows, even though fresher events exist further out.
    # The alternative — fetching the whole catalog to be sure — costs more than the pool
    # is ever worth, and this read runs once per user per day.
    queryset = (
        Event.objects.using(CATALOG)
        .filter(publication_status=Event.PublicationStatus.PUBLISHED)
        .exclude(status=Event.Status.SUPERSEDED)
        .filter(extraction_confidence__gte=EXTRACTION_CONFIDENCE_PUBLISH)
        .filter(tz_inference_confidence__gte=TZ_INFERENCE_CONFIDENCE_DIGEST)
        .filter(start_time_utc__gte=now)
        .select_related("venue", "source")
    )
    if city:
        queryset = queryset.filter(venue__city__iexact=city)

    candidates: list[PublicEventCandidate] = []
    for event in queryset.order_by("start_time_utc", "id")[: limit * CANDIDATE_OVERFETCH_FACTOR]:
        source = event.source
        age = now - event.last_seen_at
        stale_after = timedelta(hours=source.freshness_ttl_hours) * DIGEST_STALE_TTL_MULTIPLIER
        if age > stale_after:
            continue
        candidates.append(_to_public_candidate(event))
        if len(candidates) >= limit:
            break
    return candidates


def get_public_events(*, event_ids: set[UUID]) -> dict[UUID, PublicEvent]:
    """Several public events by id, in **one** query.

    A lookup, not a join: the ids are the catalog's, the query runs against the
    `catalog` alias, and the result is plain data — so the wall holds exactly as it does
    for `get_public_event`.

    **Why a batch.** A user's saved events are resolved one by one, and a user with five
    saves would cost five round-trips to the catalog. This read is once per user per day,
    so five round-trips is five round-trips *times every user*. The batch is the same
    query with an `IN` clause instead of five queries with an `=`.

    **An id that is not public is simply absent from the result.** The caller asks what
    the catalog still holds, and an event that is unpublished, in review or superseded is
    not public — so it is not in the map. The caller decides what an absent event means;
    for a save, it means the catalog no longer has it.

    `now` is not applied: a save stays readable after its event has started, so the
    bound would exclude exactly the records the caller is asking about. The caller's own
    bound, on the snapshot, is the one that applies.
    """
    if not event_ids:
        return {}

    events = (
        Event.objects.using(CATALOG)
        .filter(publication_status=Event.PublicationStatus.PUBLISHED)
        .exclude(status=Event.Status.SUPERSEDED)
        .filter(pk__in=event_ids)
        .select_related("venue", "source")
    )
    return {event.id: _to_public_event(event) for event in events}


__all__ = [
    "CANDIDATE_OVERFETCH_FACTOR",
    "CANDIDATE_POOL_SIZE",
    "DEFAULT_PAGE_SIZE",
    "MAX_CANDIDATE_POOL_SIZE",
    "MAX_PAGE_SIZE",
    "EventNotFoundError",
    "PublicEvent",
    "PublicEventCandidate",
    "get_public_event",
    "get_public_events",
    "list_public_candidates",
    "list_public_events",
]
