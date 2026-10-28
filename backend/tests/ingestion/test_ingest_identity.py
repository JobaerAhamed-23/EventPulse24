"""Event Identity in the pipeline (FR-15, AD-4; pipeline design D5, D8): rules (a)/(b)/(c),
owner-wins facts, ambiguity, supersede-chain rebinding and the venue registry lookup.
"""

from datetime import UTC, datetime

import pytest

from apps.ingestion.models import Event, ExtractedRecord, Venue
from apps.ingestion.services.ingest_source import ingest_source
from apps.ingestion.services.venue_registry import register_venue
from domain.dedup import canonical_url
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import EventFactory, ExtractedRecordFactory
from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar, ics_source, vevent

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

STAFF = Actor.user(uuid7())
FLOATING = {"tzid": None}  # a naive wall-clock time: only the venue registry can place it
SHOW_URL = "https://fillmore.example.test/shows/42"


def _run(source, *events: str):
    return ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(calendar(*events)))


def _record(source) -> ExtractedRecord:
    return ExtractedRecord.objects.using(CATALOG).get(source=source)


@pytest.fixture
def fillmore() -> Venue:
    return register_venue(
        actor=STAFF,
        name="The Fillmore",
        city="San Francisco",
        country_code="US",
        tz="America/Los_Angeles",
    )


@pytest.fixture
def venue_feed():
    return ics_source(city="San Francisco", url="https://fillmore.example.test/cal.ics")


@pytest.fixture
def ticketing_feed():
    return ics_source(city="San Francisco", url="https://tickets.example.test/sf.ics")


def test_registry_venue_resolves_a_floating_time_in_its_zone(fillmore, venue_feed):
    report = _run(venue_feed, vevent("show@f", "20261105T200000", location="Fillmore", **FLOATING))

    event = Event.objects.using(CATALOG).get()
    assert report.counts == {"new": 1}
    assert (event.venue_id, event.venue_fingerprint) == (fillmore.pk, fillmore.venue_fingerprint)
    assert (event.start_time_tz, event.start_time_utc) == (
        "America/Los_Angeles",
        datetime(2026, 11, 6, 4, 0, tzinfo=UTC),
    )


def test_venue_without_country_matches_only_when_unambiguous(fillmore, venue_feed):
    register_venue(actor=STAFF, name="The Fillmore", city="San Francisco", country_code="PH")

    report = _run(venue_feed, vevent("show@f", "20261105T200000", location="Fillmore", **FLOATING))

    assert report.counts == {"rejected:tz_unresolvable": 1}  # two countries match: no venue
    assert not Event.objects.using(CATALOG).exists()


def test_rule_b_binds_a_second_source_to_the_first_sources_event(
    fillmore, venue_feed, ticketing_feed
):
    _run(
        venue_feed,
        vevent("show@f", "20261105T200000", summary="Jazz Night", location="Fillmore", **FLOATING),
    )

    report = _run(
        ticketing_feed,
        vevent(
            "t-99", "20261105T200000", summary="Jazz Night!", location="The Fillmore", **FLOATING
        ),
    )

    [event] = Event.objects.using(CATALOG).all()
    assert report.counts == {"bound_other_source": 1}
    record = _record(ticketing_feed)
    assert (record.event_id, record.match_notes) == (
        event.pk,
        {"rule": "b", "review_signals": []},
    )


def test_rule_c_binds_by_canonical_url_and_instant(venue_feed, ticketing_feed):
    _run(venue_feed, vevent("show@f", "20261105T193000", url=SHOW_URL))

    report = _run(
        ticketing_feed,
        vevent("t-1", "20261105T193000", summary="Other words", url=SHOW_URL + "?utm_source=x"),
    )

    [event] = Event.objects.using(CATALOG).all()
    assert report.counts == {"bound_other_source": 1}
    assert _record(ticketing_feed).match_notes["rule"] == "c"
    assert event.canonical_url == canonical_url(SHOW_URL)


def test_same_url_at_another_instant_is_a_distinct_event(venue_feed, ticketing_feed):
    _run(venue_feed, vevent("show@f", "20261105T193000", url=SHOW_URL))

    _run(ticketing_feed, vevent("t-1", "20261112T193000", url=SHOW_URL))

    assert Event.objects.using(CATALOG).count() == 2


def test_only_the_origin_source_changes_an_events_facts(venue_feed, ticketing_feed):
    _run(venue_feed, vevent("show@f", "20261105T193000", url=SHOW_URL))
    _run(ticketing_feed, vevent("t-1", "20261105T193000", url=SHOW_URL))

    report = _run(
        ticketing_feed, vevent("t-1", "20261105T193000", url=SHOW_URL, status="CANCELLED")
    )

    event = Event.objects.using(CATALOG).get()
    assert report.counts == {"bound_other_source": 1}
    assert (event.status, event.event_version) == ("scheduled", 1)
    assert _record(ticketing_feed).payload["status"] == "cancelled"  # kept as evidence


def test_two_matching_events_leave_the_item_ambiguous_and_unbound(venue_feed, ticketing_feed):
    start = datetime(2026, 11, 6, 0, 30, tzinfo=UTC)
    first = EventFactory(canonical_url=canonical_url(SHOW_URL), start_time_utc=start)
    second = EventFactory(canonical_url=canonical_url(SHOW_URL), start_time_utc=start)
    ExtractedRecordFactory(event=first)
    ExtractedRecordFactory(event=second)
    other = ics_source(url="https://third.example.test/cal.ics")

    report = _run(other, vevent("x-1", "20261105T193000", url=SHOW_URL))
    again = _run(other, vevent("x-1", "20261105T193000", url=SHOW_URL))

    record = _record(other)
    assert report.counts == again.counts == {"ambiguous": 1}  # re-resolved, never "unchanged"
    assert (record.resolution, record.event_id) == ("ambiguous", None)
    assert record.match_notes == {"ambiguous": sorted([str(first.pk), str(second.pk)])}
    assert Event.objects.using(CATALOG).count() == 2


def test_item_bound_to_a_superseded_event_rebinds_to_its_successor(venue_feed, ticketing_feed):
    _run(venue_feed, vevent("show@f", "20261105T193000", url=SHOW_URL))
    _run(ticketing_feed, vevent("t-1", "20261105T193000", url=SHOW_URL))
    _run(venue_feed, vevent("show@f", "20261222T193000", url=SHOW_URL))  # supersedes

    report = _run(ticketing_feed, vevent("t-1", "20261105T193000", url=SHOW_URL, summary="New"))

    successor = Event.objects.using(CATALOG).get(status="scheduled")
    assert report.counts == {"bound_other_source": 1}
    assert _record(ticketing_feed).event_id == successor.pk
