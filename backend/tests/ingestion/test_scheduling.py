"""Scheduling commands (FR-13, AD-7; run-016 plan S1, S2, S4, S5): due selection, claims, stale
flags. Every clock is an explicit `now`.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from django.db import connections, transaction
from django.utils import timezone

from apps.ingestion.models import IngestionAuditEntry, Source
from apps.ingestion.services.ingest_source import ingest_source
from apps.ingestion.services.scheduling import (
    claim_due_sources,
    flag_stale_sources,
    release_claim,
)
from shared.constants import INGEST_CLAIM_TTL
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import SourceFactory
from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
CADENCE = timedelta(hours=4)
SECOND = timedelta(seconds=1)


def _source(**overrides) -> Source:
    return SourceFactory(ingestion_cadence=CADENCE, **overrides)


def _registered_at(source: Source, when: datetime) -> Source:
    Source.objects.using(CATALOG).filter(pk=source.pk).update(created_at=when)
    source.refresh_from_db(using=CATALOG)
    return source


def _reload(source: Source) -> Source:
    source.refresh_from_db(using=CATALOG)
    return source


# --- Due selection (S1) -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("since_attempt", "due"),
    [
        (CADENCE - SECOND, False),
        (CADENCE, True),  # exactly one cadence: due
        (CADENCE + SECOND, True),
    ],
)
def test_due_at_the_cadence_boundary(since_attempt, due):
    source = _source(last_attempted_at=NOW - since_attempt)

    assert claim_due_sources(now=NOW) == ([source.pk] if due else [])


def test_never_attempted_source_is_due_at_once():
    source = _source()

    assert claim_due_sources(now=NOW) == [source.pk]


def test_failing_source_waits_a_cadence_after_its_last_attempt():
    # Last success long ago, but attempted a minute ago: not due again until the cadence passes.
    source = _source(
        last_ingested_at=NOW - timedelta(days=3),
        last_attempted_at=NOW - timedelta(minutes=1),
        consecutive_failures=5,
    )

    assert claim_due_sources(now=NOW) == []
    assert claim_due_sources(now=NOW + CADENCE - timedelta(minutes=1)) == [source.pk]


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "paused"},
        {"acquisition_method": "crawl", "tos_status": "not_reviewed"},
        {"acquisition_method": "crawl", "tos_status": "rejected"},
    ],
)
def test_refused_sources_are_never_due(overrides):
    _source(**overrides)

    assert claim_due_sources(now=NOW) == []


def test_approved_crawl_source_is_due():
    source = _source(acquisition_method="crawl", tos_status="approved")

    assert claim_due_sources(now=NOW) == [source.pk]


def test_least_recently_attempted_first_and_batch_limited():
    never = _source()
    old = _source(last_attempted_at=NOW - timedelta(days=2))
    older = _source(last_attempted_at=NOW - timedelta(days=3))

    assert claim_due_sources(now=NOW, limit=2) == [never.pk, older.pk]
    assert claim_due_sources(now=NOW, limit=2) == [old.pk]


# --- Claims (S2) ------------------------------------------------------------------------------


def test_claimed_source_is_not_enqueued_again_by_the_next_tick():
    source = _source()

    first = claim_due_sources(now=NOW)
    second = claim_due_sources(now=NOW + timedelta(minutes=1))

    assert (first, second) == ([source.pk], [])
    assert _reload(source).ingest_claimed_at == NOW


def test_released_claim_lets_the_source_be_claimed_when_due_again():
    source = _source(acquisition_method="ics")
    claim_due_sources(now=NOW)
    ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(calendar()))
    release_claim(source.pk)

    assert _reload(source).ingest_claimed_at is None
    # The run just set last_attempted_at to the real clock.
    assert claim_due_sources(now=timezone.now() + timedelta(minutes=1)) == []
    assert claim_due_sources(now=timezone.now() + CADENCE + SECOND) == [source.pk]


@pytest.mark.parametrize(
    ("age", "reclaimed"), [(INGEST_CLAIM_TTL - SECOND, False), (INGEST_CLAIM_TTL, True)]
)
def test_a_lost_jobs_claim_expires_after_the_ttl(age, reclaimed):
    source = _source(ingest_claimed_at=NOW - age)

    assert claim_due_sources(now=NOW) == ([source.pk] if reclaimed else [])


def test_each_claim_is_audited_as_the_scheduler():
    source = _source()

    claim_due_sources(now=NOW)

    [entry] = IngestionAuditEntry.objects.using(CATALOG).filter(target_id=source.pk)
    assert (entry.action, entry.actor_kind, entry.actor_label) == (
        "claim_ingest",
        "system",
        "scheduler",
    )


@pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)
def test_two_schedulers_at_once_claim_disjoint_sources():
    """SKIP LOCKED: while one scheduler holds its rows, the other takes the rest."""
    sources = [_source() for _ in range(4)]
    holding, release = threading.Event(), threading.Event()
    results = {}

    def first_scheduler():
        try:  # this thread's own connection
            with transaction.atomic(using=CATALOG):
                ids = list(
                    Source.objects.using(CATALOG)
                    .select_for_update()
                    .filter(pk__in=[s.pk for s in sources[:2]])
                    .values_list("pk", flat=True)
                )
                results["held"] = ids
                holding.set()
                release.wait(timeout=10)
        finally:
            connections.close_all()

    thread = threading.Thread(target=first_scheduler)
    thread.start()
    holding.wait(timeout=10)
    try:
        claimed = claim_due_sources(now=NOW)
    finally:
        release.set()
        thread.join(timeout=10)

    assert sorted(claimed) == sorted(
        s.pk for s in sources[2:]
    )  # never blocked, never the held ones


# --- Freshness (S4) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("since_success", "stale"),
    [
        (2 * CADENCE - SECOND, False),
        (2 * CADENCE, True),  # exactly 2x cadence: stale
        (2 * CADENCE + SECOND, True),
    ],
)
def test_stale_at_exactly_twice_the_cadence(since_success, stale):
    source = _source(last_ingested_at=NOW - since_success)

    assert flag_stale_sources(now=NOW) == int(stale)
    assert _reload(source).stale_since == (NOW if stale else None)


def test_never_ingested_source_is_measured_from_registration():
    fresh = _registered_at(_source(), NOW - 2 * CADENCE + SECOND)
    old = _registered_at(_source(), NOW - 2 * CADENCE)

    flag_stale_sources(now=NOW)

    assert (_reload(fresh).stale_since, _reload(old).stale_since) == (None, NOW)


def test_paused_source_is_never_flagged():
    source = _source(status="paused", last_ingested_at=NOW - timedelta(days=30))

    assert flag_stale_sources(now=NOW) == 0
    assert _reload(source).stale_since is None


def test_flag_is_set_once_and_audited():
    source = _source(last_ingested_at=NOW - timedelta(days=1))

    flag_stale_sources(now=NOW)
    again = flag_stale_sources(now=NOW + timedelta(hours=1))

    assert (again, _reload(source).stale_since) == (0, NOW)  # the first flag time is kept
    [entry] = IngestionAuditEntry.objects.using(CATALOG).filter(target_id=source.pk)
    assert (entry.action, entry.actor_label) == ("flag_stale", "freshness")


def test_next_successful_run_clears_the_flag():
    source = _source(acquisition_method="ics", last_ingested_at=NOW - timedelta(days=1))
    flag_stale_sources(now=NOW)

    ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(calendar()))

    assert _reload(source).stale_since is None
