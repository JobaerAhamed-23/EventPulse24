"""Ticketmaster Discovery v2 reader: the recorded response, field by field.

The claim this file has to hold up is FR-17's: that the API tier resolves a time perfectly
in a city we have never seen. That rests on the provider giving both an exact instant and
an IANA zone, and on this reader handing both over **as written** so `domain.timezones` can
do its job. Everything else is mapping, and mapping is checked against a recorded fixture
rather than a hand-built dict, so a change in the provider's shape shows up here.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from apps.ingestion.parsers.ticketmaster import read
from apps.ingestion.parsers.types import MAX_ITEMS, SourceContext, StatusHint

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "sources"
CONTEXT = SourceContext(UUID(int=11), "https://app.ticketmaster.com/discovery/v2/events.json")


def wall(text: str) -> datetime:
    """A naive wall-clock time, as a source without an instant writes it."""
    return datetime.fromisoformat(text)


@pytest.fixture(scope="module")
def parsed():
    return read((FIXTURES / "ticketmaster-events.json").read_bytes(), CONTEXT)


@pytest.fixture(scope="module")
def by_id(parsed):
    return {candidate.source_event_id: candidate for candidate in parsed.candidates}


def one(**event) -> list:
    payload = {"_embedded": {"events": [{"id": "e1", "name": "Show", **event}]}}
    return read(json.dumps(payload).encode(), CONTEXT).candidates


class TestTheWholeRecordedPage:
    def test_every_readable_event_becomes_a_candidate(self, parsed):
        # Five events in the fixture; the dateTBA one has no event time and is skipped.
        assert len(parsed.candidates) == 4
        assert parsed.skipped == {"no_event_start": 1}
        assert parsed.error is None

    def test_the_provider_id_is_the_source_event_id(self, by_id):
        # AC 10: a re-ingest dedupes rather than duplicates, which needs the provider's id.
        assert set(by_id) == {
            "G5diZ9K1avWuW",
            "G5diZ9K2bxWvX",
            "G5diZ9K3cyWwY",
            "G5diZ9K4dzWxZ",
        }


class TestTheTimeTheApiTierExistsFor:
    def test_an_exact_instant_and_a_zone_are_both_handed_over(self, by_id):
        # This is the whole reason FR-17 puts `api` first: with these two fields, resolve_tz
        # reaches row A1 — confidence 1.00, Tier.FULL — with no venue and no city zone.
        candidate = by_id["G5diZ9K1avWuW"]

        assert candidate.start == datetime(2026, 11, 15, 1, 0, tzinfo=UTC)
        assert candidate.start_zone == "America/New_York"
        assert candidate.start_raw == "2026-11-15T01:00:00Z"
        assert candidate.all_day is False

    def test_a_local_date_and_time_without_an_instant_stay_naive(self, by_id):
        # The provider knows the wall-clock time and the zone but gives no UTC instant.
        # Still row A1 — the parser does not do the arithmetic, resolve_tz does.
        candidate = by_id["G5diZ9K2bxWvX"]

        assert candidate.start == wall("2026-11-20T19:30")
        assert candidate.start.tzinfo is None
        assert candidate.start_zone == "Asia/Dhaka"
        assert candidate.start_raw == "2026-11-20 19:30:00"

    def test_a_date_with_no_time_is_all_day_at_midnight(self, by_id):
        candidate = by_id["G5diZ9K3cyWwY"]

        assert candidate.start == wall("2026-12-05T00:00")
        assert candidate.all_day is True
        assert candidate.start_zone == "Europe/Lisbon"

    def test_an_event_with_no_date_at_all_is_skipped_not_guessed(self):
        # `dateTBA`. A publication date or "today" would create a wrong-time event — the
        # same rule the RSS parser applies to pubDate.
        result = read(
            json.dumps(
                {"_embedded": {"events": [{"id": "e1", "name": "Show", "dates": {"start": {}}}]}}
            ).encode(),
            CONTEXT,
        )

        assert (result.candidates, result.skipped) == ([], {"no_event_start": 1})

    def test_a_local_date_that_carries_its_own_time_is_not_all_day(self):
        # Defensive: `localDate` is documented as a date, but a provider that writes a full
        # datetime into it has given a time, and treating that as midnight would move the
        # event by hours.
        [candidate] = one(dates={"start": {"localDate": "2026-11-14T20:00:00"}})

        assert candidate.start == wall("2026-11-14T20:00")
        assert candidate.all_day is False

    def test_a_zone_the_provider_omits_is_none_not_empty(self):
        [candidate] = one(dates={"start": {"localDate": "2026-11-14", "localTime": "20:00:00"}})

        assert candidate.start_zone is None


class TestStatus:
    @pytest.mark.parametrize(
        ("code", "status"),
        [
            ("onsale", StatusHint.SCHEDULED),
            ("offsale", StatusHint.SCHEDULED),
            ("canceled", StatusHint.CANCELLED),
            ("cancelled", StatusHint.CANCELLED),
            ("postponed", StatusHint.POSTPONED),
            ("rescheduled", StatusHint.POSTPONED),
            ("something-new", StatusHint.SCHEDULED),
            ("", StatusHint.SCHEDULED),
        ],
    )
    def test_the_provider_status_maps_to_a_catalog_status(self, code, status):
        [candidate] = one(
            dates={"start": {"localDate": "2026-11-14"}, "status": {"code": code}},
        )

        assert candidate.status is status

    def test_offsale_is_never_read_as_sold_out(self, by_id):
        # "Outside the on-sale window" covers an event that has not gone on sale yet, and
        # presale inventory can exist during it. Calling it sold out would mislabel events.
        assert by_id["G5diZ9K2bxWvX"].sold_out is False
        assert all(not c.sold_out for c in by_id.values())


class TestVenueAndText:
    def test_the_venue_city_and_country_come_through(self, by_id):
        # `_venue_for` and EventFit both key on these.
        candidate = by_id["G5diZ9K1avWuW"]

        assert candidate.venue_name == "Madison Square Garden"
        assert candidate.venue_city == "New York"
        assert candidate.venue_country == "US"

    def test_an_event_with_no_venue_block_is_still_a_candidate(self, by_id):
        candidate = by_id["G5diZ9K4dzWxZ"]

        assert (candidate.venue_name, candidate.venue_city, candidate.venue_country) == ("", "", "")

    def test_description_prefers_info_and_falls_back_to_please_note(self, by_id):
        assert by_id["G5diZ9K1avWuW"].description == "Doors open at 7pm. All ages."
        assert by_id["G5diZ9K2bxWvX"].description == "Seating is unreserved."

    def test_the_canonical_url_is_kept_when_absolute_and_dropped_otherwise(self, by_id):
        assert by_id["G5diZ9K1avWuW"].canonical_url.startswith("https://www.ticketmaster.com/")
        assert by_id["G5diZ9K3cyWwY"].canonical_url == ""  # the fixture gives none

        [candidate] = one(dates={"start": {"localDate": "2026-11-14"}}, url="javascript:alert(1)")
        assert candidate.canonical_url == ""

    def test_the_country_code_is_two_uppercase_letters(self, by_id):
        [candidate] = one(
            dates={"start": {"localDate": "2026-11-14"}},
            _embedded={"venues": [{"country": {"countryCode": "bd"}}]},
        )

        assert candidate.venue_country == "BD"
        assert all(len(c.venue_country) in (0, 2) for c in by_id.values())


class TestItIsTotal:
    @pytest.mark.parametrize(
        "payload",
        [
            {"_embedded": None},
            {"_embedded": {"events": None}},
            {"_embedded": {"events": [None, 7, "a string"]}},
            {"_embedded": {"events": [{"id": "e1", "name": "S", "dates": "not an object"}]}},
            {"_embedded": {"events": [{"id": "e1", "name": "S", "_embedded": {"venues": {}}}]}},
            {"_embedded": {"events": [{"id": 7, "name": "S"}]}},
        ],
        ids=[
            "null-embedded",
            "null-events",
            "junk-events",
            "dates-not-object",
            "venues-not-list",
            "id-not-string",
        ],
    )
    def test_an_unexpected_shape_yields_fewer_candidates_never_an_exception(self, payload):
        result = read(json.dumps(payload).encode(), CONTEXT)

        assert result.error is None
        assert isinstance(result.candidates, list)

    def test_an_event_without_a_title_is_skipped(self):
        result = read(
            json.dumps({"_embedded": {"events": [{"id": "e1", "name": "   "}]}}).encode(), CONTEXT
        )

        assert (result.candidates, result.skipped) == ([], {"no_title": 1})

    def test_an_event_without_an_id_is_skipped(self):
        # No provider id means no way to follow it between runs, so it is not taken at all.
        result = read(json.dumps({"_embedded": {"events": [{"name": "Show"}]}}).encode(), CONTEXT)

        assert (result.candidates, result.skipped) == ([], {"no_source_event_id": 1})

    def test_a_page_larger_than_the_cap_stops_at_it(self):
        events = [
            {"id": f"e{n}", "name": "Show", "dates": {"start": {"localDate": "2026-11-14"}}}
            for n in range(MAX_ITEMS + 10)
        ]

        result = read(json.dumps({"_embedded": {"events": events}}).encode(), CONTEXT)

        assert len(result.candidates) == MAX_ITEMS
        assert result.skipped["too_many_items"] == 10

    def test_a_repeated_provider_id_is_counted_once(self):
        events = [
            {"id": "same", "name": "Show", "dates": {"start": {"localDate": "2026-11-14"}}}
        ] * 2

        result = read(json.dumps({"_embedded": {"events": events}}).encode(), CONTEXT)

        assert len(result.candidates) == 1
        assert result.skipped["duplicate_id"] == 1
