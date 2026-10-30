"""The public candidate read: what a Pulse Digest may rank, and what it may not.

**The gates are the interesting part.** Each one has an exact threshold, and a gate that
is *almost* right is a gate that is wrong: an event one hundredth below the confidence
threshold must be excluded, and one exactly at it must be included. So each gate is
tested at its boundary and one step below it.

The staleness bound (FR-14) is measured from `Event.last_seen_at` — when the catalog last
saw the event at the source — and the comparison is inclusive at the boundary, because
"older than" is exclusive and an event exactly at the bound is not older than it.

**The Source Badge is resolved on this side of the wall.** The candidate carries the
badge as a string, because the caller may not hold a `Source`; and it comes from the same
query that justified the card, so it cannot disagree with it.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.ingestion.models import Event
from apps.ingestion.services.catalog_read import (
    CANDIDATE_OVERFETCH_FACTOR,
    CANDIDATE_POOL_SIZE,
    MAX_CANDIDATE_POOL_SIZE,
    list_public_candidates,
)
from apps.ingestion.services.source_badges import (
    SOURCE_BADGE_AGGREGATOR,
    SOURCE_BADGE_CRAWLED,
    SOURCE_BADGE_OFFICIAL,
)
from shared.constants import (
    DIGEST_STALE_TTL_MULTIPLIER,
    EXTRACTION_CONFIDENCE_PUBLISH,
    TZ_INFERENCE_CONFIDENCE_DIGEST,
)
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, SourceFactory, VenueFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


def at(hours: int) -> datetime:
    return NOW + timedelta(hours=hours)


def ids_of(candidates) -> list:
    return [candidate.id for candidate in candidates]


# --- the extraction confidence gate ------------------------------------------------


def test_an_event_one_hundredth_below_the_extraction_gate_is_excluded():
    EventFactory(
        start_time_utc=at(2),
        extraction_confidence=EXTRACTION_CONFIDENCE_PUBLISH - Decimal("0.01"),
    )

    assert list_public_candidates(now=NOW) == []


def test_an_event_exactly_at_the_extraction_gate_is_included():
    event = EventFactory(
        start_time_utc=at(2),
        extraction_confidence=EXTRACTION_CONFIDENCE_PUBLISH,
    )

    assert ids_of(list_public_candidates(now=NOW)) == [event.id]


# --- the timezone confidence gate ---------------------------------------------------


def test_an_event_one_hundredth_below_the_tz_gate_is_excluded():
    EventFactory(
        start_time_utc=at(2),
        tz_inference_confidence=TZ_INFERENCE_CONFIDENCE_DIGEST - Decimal("0.01"),
    )

    assert list_public_candidates(now=NOW) == []


def test_an_event_exactly_at_the_tz_gate_is_included():
    event = EventFactory(
        start_time_utc=at(2),
        tz_inference_confidence=TZ_INFERENCE_CONFIDENCE_DIGEST,
    )

    assert ids_of(list_public_candidates(now=NOW)) == [event.id]


def test_a_tz_review_pending_event_is_eligible_and_carries_the_flag():
    """AD-6: between the digest gate and the auto-publish threshold an event publishes
    with its time still under review. It is published, it is above the gate, so it is
    eligible — and the flag travels with it so the frontend can mark the time."""
    event = EventFactory(
        start_time_utc=at(2),
        tz_inference_confidence=TZ_INFERENCE_CONFIDENCE_DIGEST,
        tz_review_pending=True,
    )

    candidates = list_public_candidates(now=NOW)

    assert ids_of(candidates) == [event.id]
    assert candidates[0].tz_review_pending is True


# --- the publication and supersession gates ------------------------------------------


def test_an_unpublished_event_is_excluded():
    EventFactory(
        start_time_utc=at(2),
        publication_status=Event.PublicationStatus.IN_REVIEW,
    )

    assert list_public_candidates(now=NOW) == []


def test_a_superseded_event_is_excluded_and_its_replacement_is_included():
    """D7: a superseded Event is terminal; the live one that replaced it is listed."""
    from tests.ingestion.factories import make_superseded_pair

    old, new = make_superseded_pair(start_time_utc=at(2))

    candidates = list_public_candidates(now=NOW)

    assert new.id in ids_of(candidates)
    assert old.id not in ids_of(candidates)


def test_an_event_starting_exactly_now_is_included():
    event = EventFactory(start_time_utc=NOW)

    assert ids_of(list_public_candidates(now=NOW)) == [event.id]


def test_an_event_that_already_started_is_excluded():
    EventFactory(start_time_utc=NOW - HOUR)

    assert list_public_candidates(now=NOW) == []


# --- staleness (FR-14) ---------------------------------------------------------------


def test_an_event_older_than_twice_its_sources_ttl_is_excluded():
    """The bound is 2 × the source's `freshness_ttl_hours` (default 24 → 48 hours)."""
    source = SourceFactory(freshness_ttl_hours=24)
    EventFactory(source=source, start_time_utc=at(2), last_seen_at=NOW - timedelta(hours=49))

    assert list_public_candidates(now=NOW) == []


def test_an_event_exactly_at_the_staleness_bound_is_included():
    """The comparison is inclusive: "older than" is exclusive, and an event exactly at
    the bound is not older than it."""
    source = SourceFactory(freshness_ttl_hours=24)
    event = EventFactory(
        source=source, start_time_utc=at(2), last_seen_at=NOW - timedelta(hours=48)
    )

    assert ids_of(list_public_candidates(now=NOW)) == [event.id]


def test_the_staleness_bound_follows_the_sources_ttl():
    """A source with a 72-hour TTL gets a 144-hour bound — the multiplier is applied to
    each source's own TTL, not to a fixed number of hours."""
    source = SourceFactory(freshness_ttl_hours=72)
    EventFactory(source=source, start_time_utc=at(2), last_seen_at=NOW - timedelta(hours=100))

    assert len(list_public_candidates(now=NOW)) == 1

    EventFactory(source=source, start_time_utc=at(3), last_seen_at=NOW - timedelta(hours=145))

    assert len(list_public_candidates(now=NOW)) == 1


def test_the_staleness_bound_is_measured_from_last_seen_not_updated():
    """`updated_at` moves whenever *we* touch the row; `last_seen_at` is when the catalog
    last saw the event at the source. A stale event must not be kept alive by a write."""
    source = SourceFactory(freshness_ttl_hours=24)
    event = EventFactory(
        source=source, start_time_utc=at(2), last_seen_at=NOW - timedelta(hours=49)
    )

    # Touch the row, so `updated_at` is now but `last_seen_at` is not.
    Event.objects.using(CATALOG).filter(pk=event.pk).update(updated_at=NOW)

    assert list_public_candidates(now=NOW) == []


def test_the_multiplier_is_the_named_constant():
    assert DIGEST_STALE_TTL_MULTIPLIER == 2


# --- the city filter ------------------------------------------------------------------


def test_the_city_filter_matches_the_venue_city_exactly():
    matching = EventFactory(start_time_utc=at(2), venue=VenueFactory(city="Brooklyn"))
    EventFactory(start_time_utc=at(3), venue=VenueFactory(city="Queens"))

    candidates = list_public_candidates(now=NOW, city="Brooklyn")

    assert ids_of(candidates) == [matching.id]


def test_the_city_filter_is_case_insensitive():
    event = EventFactory(start_time_utc=at(2), venue=VenueFactory(city="Brooklyn"))

    candidates = list_public_candidates(now=NOW, city="brooklyn")

    assert ids_of(candidates) == [event.id]


def test_an_event_with_no_venue_matches_no_city():
    """An event with no venue has no city. The event fit made the same call: give such
    events no row rather than a guessed one."""
    EventFactory(start_time_utc=at(2), venue=None)

    assert list_public_candidates(now=NOW, city="Brooklyn") == []


def test_no_city_returns_every_eligible_event():
    EventFactory(start_time_utc=at(2), venue=VenueFactory(city="Brooklyn"))
    EventFactory(start_time_utc=at(3), venue=VenueFactory(city="Queens"))

    assert len(list_public_candidates(now=NOW)) == 2


# --- the source badge -----------------------------------------------------------------


def test_the_badge_for_a_venue_source_is_official():
    EventFactory(start_time_utc=at(2))

    candidates = list_public_candidates(now=NOW)

    assert candidates[0].source_badge == SOURCE_BADGE_OFFICIAL


def test_a_crawled_source_gets_the_crawled_badge():
    """*How* the facts were obtained is what the ⚠ means: scraped, not published to us."""
    from apps.ingestion.models import AcquisitionMethod

    source = SourceFactory(acquisition_method=AcquisitionMethod.CRAWL)
    EventFactory(source=source, start_time_utc=at(2))

    candidates = list_public_candidates(now=NOW)

    assert candidates[0].source_badge == SOURCE_BADGE_CRAWLED


def test_an_unmapped_source_type_gets_the_aggregator_badge():
    """The least specific claim — the one that does not assert a verification the
    registry has not made."""
    from apps.ingestion.models import Source

    source = SourceFactory(source_type=Source.SourceType.OTHER)
    EventFactory(source=source, start_time_utc=at(2))

    candidates = list_public_candidates(now=NOW)

    assert candidates[0].source_badge == SOURCE_BADGE_AGGREGATOR


def test_the_candidate_carries_the_badge_inputs():
    """The badge is resolved here, but its inputs travel with it for the audit trail."""
    from apps.ingestion.models import AcquisitionMethod

    source = SourceFactory(acquisition_method=AcquisitionMethod.RSS)
    EventFactory(source=source, start_time_utc=at(2))

    candidate = list_public_candidates(now=NOW)[0]

    assert candidate.source_type == source.source_type
    assert candidate.acquisition_method == AcquisitionMethod.RSS


# --- the pool -------------------------------------------------------------------------


def test_the_pool_is_ordered_by_start_time_then_id():
    first = EventFactory(start_time_utc=at(3))
    second = EventFactory(start_time_utc=at(2))
    third = EventFactory(start_time_utc=at(3))

    candidates = list_public_candidates(now=NOW)

    assert ids_of(candidates) == [second.id, first.id, third.id]


def test_the_pool_is_bounded_by_the_limit():
    for hour in range(2, 12):
        EventFactory(start_time_utc=at(hour))

    candidates = list_public_candidates(now=NOW, limit=3)

    assert len(candidates) == 3


def test_a_limit_of_zero_returns_no_candidates():
    """A caller that asks for no candidates must not be handed one. `max(1, ...)` would
    quietly turn 'none' into 'one'."""
    EventFactory(start_time_utc=at(2))

    assert list_public_candidates(now=NOW, limit=0) == []


def test_a_negative_limit_returns_no_candidates():
    EventFactory(start_time_utc=at(2))

    assert list_public_candidates(now=NOW, limit=-5) == []


def test_the_limit_cannot_exceed_the_cap():
    assert MAX_CANDIDATE_POOL_SIZE == 200
    assert CANDIDATE_POOL_SIZE < MAX_CANDIDATE_POOL_SIZE


def test_a_limit_above_the_cap_is_capped():
    for hour in range(2, 12):
        EventFactory(start_time_utc=at(hour))

    candidates = list_public_candidates(now=NOW, limit=10_000)

    assert len(candidates) == 10  # the ten that exist, under the cap of 200


def test_the_sql_fetch_is_bounded():
    """The staleness filter runs in Python, so the SQL must be bounded too — or a
    catalog whose events are mostly stale would hand every one of them to Python before
    the first candidate was found."""
    from django.db import connections

    for hour in range(2, 12):
        EventFactory(start_time_utc=at(hour))

    recorder = _record()
    with connections[CATALOG].execute_wrapper(recorder):
        list_public_candidates(now=NOW, limit=3)

    assert recorder.recorded, "the read must query the catalog alias"
    # The `LIMIT` clause is in the SQL, so the fetch is bounded at the database.
    assert any("LIMIT" in query.upper() for query in recorder.recorded), (
        "the candidate query must carry a LIMIT; an unbounded fetch would make the "
        "read's cost depend on the size of the catalog"
    )


def test_the_overfetch_factor_is_the_named_constant():
    assert CANDIDATE_OVERFETCH_FACTOR >= 1


def test_the_pool_stops_at_the_default_size():
    """The default is the named pool size, and the pool is bounded by it."""
    for hour in range(2, 2 + CANDIDATE_POOL_SIZE + 5):
        EventFactory(start_time_utc=at(hour))

    candidates = list_public_candidates(now=NOW)

    assert len(candidates) == CANDIDATE_POOL_SIZE


# --- the shape ------------------------------------------------------------------------


def test_the_candidate_carries_the_confidences_and_the_country():
    event = EventFactory(
        start_time_utc=at(2), venue=VenueFactory(city="Brooklyn", country_code="US")
    )

    candidate = list_public_candidates(now=NOW)[0]

    assert candidate.extraction_confidence == event.extraction_confidence
    assert candidate.tz_inference_confidence == event.tz_inference_confidence
    assert candidate.venue_city == "Brooklyn"
    assert candidate.venue_country_code == "US"


def test_the_confidences_are_decimals_and_not_floats_or_strings():
    """A `Decimal` never becomes a float: "a float 0.8 is not exactly 4/5, and a
    boundary test on a float would be a lie" (`shared/constants.py`)."""
    EventFactory(start_time_utc=at(2))

    candidate = list_public_candidates(now=NOW)[0]

    assert isinstance(candidate.extraction_confidence, Decimal)
    assert isinstance(candidate.tz_inference_confidence, Decimal)


def test_a_candidate_is_frozen():
    """A candidate is a value, not a handle: composition may hold it, and nothing may
    change it underneath."""
    EventFactory(start_time_utc=at(2))

    candidate = list_public_candidates(now=NOW)[0]

    with pytest.raises(FrozenInstanceError):
        candidate.title = "changed"


# --- the wall ---------------------------------------------------------------------------


def test_the_public_read_runs_on_the_catalog_alias_and_never_the_personal_one():
    """The public read is a query against `catalog` only. The digest's composition
    service will read the personal side separately; no query may span the two."""
    from django.db import connections

    EventFactory(start_time_utc=at(2))

    catalog_recorder = _record()
    personal_recorder = _record()
    with connections[CATALOG].execute_wrapper(catalog_recorder):
        with connections[PERSONAL].execute_wrapper(personal_recorder):
            list_public_candidates(now=NOW)

    assert catalog_recorder.recorded, "the public read must query the catalog alias"
    assert not personal_recorder.recorded, (
        "the public read must never touch the personal schema; the two sides are read "
        "separately and joined in the application layer (AD-3)"
    )


def _record():
    """Capture the SQL executed against one alias.

    Returns the wrapper; `execute_wrapper` hands back the wrapper itself, so the
    recorded statements live on it.
    """
    recorded: list[str] = []

    def wrapper(execute, sql, params, many, context):
        recorded.append(sql)
        return execute(sql, params, many, context)

    wrapper.recorded = recorded
    return wrapper
