"""FR-60 timezone outcomes in the pipeline (AD-6; pipeline design D6, D7, D13; plan P1, P2)."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from apps.ingestion.models import Event, ExtractedRecord, Venue
from apps.ingestion.services import ingest_item as item_module
from apps.ingestion.services.ingest_source import ingest_source
from apps.ingestion.services.source_registry import update_source
from apps.ingestion.services.venue_registry import register_venue, set_venue_timezone
from domain.timezones import resolve_tz
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar, ics_source, vevent

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

STAFF = Actor.user(uuid7())


def _run(source, *events: str):
    return ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(calendar(*events)))


def _floating(uid: str, start: str, **kw) -> str:
    return vevent(uid, start, tzid=None, location="The Fillmore", **kw)


@pytest.fixture
def source():
    return ics_source(city="San Francisco")


@pytest.fixture
def fillmore():
    return register_venue(
        actor=STAFF, name="The Fillmore", city="San Francisco", country_code="US", tz="US/Pacific"
    )


@pytest.mark.usefixtures("fillmore")
@pytest.mark.parametrize(
    ("start", "confidence", "publication", "flagged", "count_flag"),
    [
        # 2026-11-01 01:30 happens twice in Los Angeles (DST ends): fold cap 0.80.
        ("20261101T013000", "0.80", "published", True, "tz_review_pending"),
        # 2027-03-14 02:30 doesn't exist in Los Angeles (DST starts): gap cap 0.65.
        ("20270314T023000", "0.65", "in_review", False, "in_review"),
        # An ordinary evening, read in the registry zone: C1, 0.95.
        ("20261105T200000", "0.95", "published", False, None),
    ],
)
def test_venue_registry_time_is_gated_by_its_confidence(
    source, start, confidence, publication, flagged, count_flag
):
    report = _run(source, _floating("show@f", start))

    event = Event.objects.using(CATALOG).get()
    assert event.tz_inference_confidence == Decimal(confidence)
    assert (event.publication_status, event.tz_review_pending) == (publication, flagged)
    assert report.counts == {"new": 1, **({count_flag: 1} if count_flag else {})}


@pytest.mark.usefixtures("fillmore")
def test_confidence_of_exactly_0_90_publishes_unflagged(source, monkeypatch):
    # The C1b city-zone row now scores exactly 0.90 and is covered below on its own terms.
    # This one keeps testing the *boundary* independently of which row happens to sit on it,
    # so the gate stays pinned even if that score is ever retuned (AD-8: scores are anchors).
    def at_0_90(*args, **kwargs):
        return replace(resolve_tz(*args, **kwargs), confidence=Decimal("0.90"))

    monkeypatch.setattr(item_module, "resolve_tz", at_0_90)

    _run(source, _floating("show@f", "20261105T200000"))

    event = Event.objects.using(CATALOG).get()
    assert (event.tz_inference_confidence, event.publication_status, event.tz_review_pending) == (
        Decimal("0.90"),
        "published",
        False,
    )


def test_none_tier_never_becomes_an_event(source):
    report = _run(source, _floating("show@f", "20261105T200000"))

    record = ExtractedRecord.objects.using(CATALOG).get()
    assert report.counts == {"rejected:tz_unresolvable": 1}
    assert (record.resolution, record.reject_reason, record.event_id) == (
        "rejected",
        "tz_unresolvable",
        None,
    )
    assert not Event.objects.using(CATALOG).exists()


def test_venue_tz_added_later_resolves_the_rejected_item(source):
    venue = register_venue(
        actor=STAFF, name="The Fillmore", city="San Francisco", country_code="US"
    )
    _run(source, _floating("show@f", "20261105T200000"))

    set_venue_timezone(actor=STAFF, venue_id=venue.id, tz="America/Los_Angeles")
    report = _run(source, _floating("show@f", "20261105T200000"))  # the same bytes

    assert report.counts == {"new": 1}
    record = ExtractedRecord.objects.using(CATALOG).get()
    assert (record.resolution, record.reject_reason) == ("resolved", "")


@pytest.mark.usefixtures("fillmore")
def test_resolved_item_that_loses_its_zone_keeps_its_event(source):
    _run(source, vevent("show@f", "20261105T200000", tzid="America/Los_Angeles"))
    before = Event.objects.using(CATALOG).get()

    report = _run(source, vevent("show@f", "20261105T200000", tzid=None))  # no venue either

    assert report.counts == {"rejected_update:tz_unresolvable": 1}
    after = Event.objects.using(CATALOG).get()
    assert (after.pk, after.event_version, after.start_time_utc) == (
        before.pk,
        1,
        before.start_time_utc,
    )
    record = ExtractedRecord.objects.using(CATALOG).get()
    assert record.resolution == "resolved"
    assert record.last_seen_at > before.last_seen_at  # seen, though not applied


@pytest.mark.usefixtures("fillmore")
def test_same_facts_with_new_confidence_regate_silently(source):
    # Plan P1: the gates follow each resolution even when no fact changed.
    explicit = vevent(
        "show@f", "20261105T200000", tzid="America/Los_Angeles", location="The Fillmore"
    )
    _run(source, explicit)  # A1, the venue's zone agrees: 1.00

    report = _run(source, _floating("show@f", "20261105T200000"))  # same instant, C1, 0.95

    event = Event.objects.using(CATALOG).get()
    assert report.counts == {"unchanged": 1}
    assert (event.tz_inference_confidence, event.event_version) == (Decimal("0.95"), 1)


@pytest.mark.usefixtures("fillmore")
def test_publication_follows_each_new_resolution_both_ways(source):
    _run(source, _floating("show@f", "20261105T200000"))  # C1, 0.95

    # A zone that disagrees with the venue's (A3): 0.60, the item's own zone sets the time.
    _run(
        source,
        vevent("show@f", "20261105T200000", tzid="America/New_York", location="The Fillmore"),
    )
    dropped = Event.objects.using(CATALOG).get()
    _run(source, _floating("show@f", "20261105T200000"))
    restored = Event.objects.using(CATALOG).get()

    assert (dropped.publication_status, dropped.tz_inference_confidence) == (
        "in_review",
        Decimal("0.60"),
    )
    assert (restored.publication_status, restored.tz_inference_confidence) == (
        "published",
        Decimal("0.95"),
    )
    assert restored.pk == dropped.pk


@pytest.mark.usefixtures("fillmore")
def test_all_day_and_overnight_times_arrive_normalized(source):
    _run(
        source,
        vevent(
            "fair@f",
            "20261114",
            tzid=None,
            location="The Fillmore",
            end="20261116",
            extra=["X-NOTE:all day"],
        )
        .replace("DTSTART:", "DTSTART;VALUE=DATE:")
        .replace("DTEND:", "DTEND;VALUE=DATE:"),
        _floating("late@f", "20261105T220000", end="20261105T020000"),
    )

    fair = Event.objects.using(CATALOG).get(source_event_id="fair@f")
    late = Event.objects.using(CATALOG).get(source_event_id="late@f")
    assert fair.start_time_local == "2026-11-14T00:00:00"
    assert fair.end_time_utc > fair.start_time_utc
    assert late.end_time_utc == datetime(2026, 11, 6, 10, 0, tzinfo=UTC)  # 02:00 next day
    assert late.end_time_utc > late.start_time_utc


# --- C1b: the source's city zone, and the cold start it exists for --------------------------
#
# `_venue_for` never creates a venue (D5), so a freshly provisioned city has none and every
# naive or date-only time rejects as `tz_unresolvable`. The city zone is the last link in the
# chain. Chittagong stands in for the real case: the Eventbrite `/d/` directory the Dhaka seed
# documents emits date-only `startDate`, with no venue we are allowed to invent.

CHITTAGONG = "Asia/Dhaka"


@pytest.fixture
def provisioned():
    """A source for a city with a zone and no registered venues — a brand-new city."""
    return ics_source(city="Chittagong", city_tz=CHITTAGONG, tz_coverage="none")


def _date_only(uid: str, date: str) -> str:
    return vevent(uid, date, tzid=None).replace("DTSTART:", "DTSTART;VALUE=DATE:")


def test_date_only_time_in_a_city_with_no_venue_publishes_on_the_city_zone(provisioned):
    # The whole point of the item: without city_tz this run rejects every candidate and the
    # city shows "collecting" forever.
    report = _run(provisioned, _date_only("show@c", "20261114"))

    event = Event.objects.using(CATALOG).get()
    assert report.counts == {"new": 1}
    assert event.tz_inference_confidence == Decimal("0.90")
    assert (event.publication_status, event.tz_review_pending) == ("published", False)
    assert event.start_time_tz == CHITTAGONG
    assert event.start_time_local == "2026-11-14T00:00:00"


def test_the_same_feed_without_a_city_zone_still_rejects():
    # The control. Identical bytes, identical source but for the one field.
    report = _run(ics_source(city="Chittagong"), _date_only("show@c", "20261114"))

    assert report.counts == {"rejected:tz_unresolvable": 1}
    assert not Event.objects.using(CATALOG).exists()


def test_a_naive_time_in_a_city_with_no_venue_reads_in_the_city_zone(provisioned):
    _run(provisioned, _floating("show@c", "20261105T200000"))

    event = Event.objects.using(CATALOG).get()
    assert event.start_time_utc == datetime(2026, 11, 5, 14, 0, tzinfo=UTC)  # 20:00 +06
    assert event.tz_inference_confidence == Decimal("0.90")


@pytest.mark.usefixtures("fillmore")
def test_a_registered_venue_still_outranks_the_city_zone():
    # Precedence, asserted through the pipeline and not only in the domain: the venue's own
    # zone decides, and the event is scored at the venue row, not the city row.
    source = ics_source(city="San Francisco", city_tz="Asia/Dhaka")

    _run(source, _floating("show@f", "20261105T200000"))

    event = Event.objects.using(CATALOG).get()
    assert event.start_time_tz == "America/Los_Angeles"
    assert event.tz_inference_confidence == Decimal("0.95")


def test_city_zone_added_later_resolves_the_rejected_item():
    # D7's rule, applied to the new field: `_content_hash` carries city_tz, so a source that
    # gains a zone re-resolves the items it already rejected. Without city_tz in the hash the
    # payload is unchanged, the item is skipped as unchanged, and it stays rejected forever —
    # which is the one case the zone was added for.
    source = ics_source(city="Chittagong")
    _run(source, _date_only("show@c", "20261114"))

    updated = update_source(actor=STAFF, source_id=source.id, changes={"city_tz": CHITTAGONG})
    report = _run(updated, _date_only("show@c", "20261114"))  # the same bytes

    assert report.counts == {"new": 1}
    record = ExtractedRecord.objects.using(CATALOG).get()
    assert (record.resolution, record.reject_reason) == ("resolved", "")


def test_no_venue_is_ever_created_for_a_provisioned_city(provisioned):
    # D5 holds. The cold start is solved with a zone on the source, not by inventing a venue.
    _run(provisioned, _date_only("show@c", "20261114"))

    assert not Venue.objects.using(CATALOG).exists()
    assert Event.objects.using(CATALOG).get().venue_id is None
