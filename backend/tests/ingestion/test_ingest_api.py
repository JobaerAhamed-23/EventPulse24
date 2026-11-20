"""The `api` acquisition tier end to end (FR-17): the key, and the time it resolves.

Two claims are tested here that neither the parser tests nor the domain tests can make on
their own:

1. **A Ticketmaster response resolves perfectly cold.** No registered venue, no
   `source.city_tz`, nothing known about the city — and the event still publishes at
   `Tier.FULL` with confidence 1.00. That is why FR-17 puts this tier first.
2. **The API key never lands anywhere it can be read later.** It is added for the one
   fetch and stripped from everything the fetch reports back.
"""

from decimal import Decimal
from pathlib import Path

import pytest
from django.test import override_settings

from apps.ingestion.models import Event, Source, Venue
from apps.ingestion.services.ingest_source import ingest_source
from apps.ingestion.services.provider_keys import authorized_url, strip_key
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import SourceFactory
from tests.ingestion.pipeline_support import ScriptedFetchPort, ok

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "sources"
DISCOVERY = "https://app.ticketmaster.com/discovery/v2/events.json?city=New+York&countryCode=US"
KEY = "k9SdF3mQ2pZxAa1bCc4dEe7f"


def body(name: str = "ticketmaster-events.json") -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture
def api_source():
    """An `api` source whose stored URL carries no key — the shape provisioning writes."""
    return SourceFactory(
        acquisition_method="api",
        url=DISCOVERY,
        city="New York",
        tz_coverage=Source.TzCoverage.FULL,
    )


def _run(source, port=None, name="ticketmaster-events.json"):
    port = port or ScriptedFetchPort().serve(ok(body(name), url=DISCOVERY))
    return ingest_source(source.id, fetch_port=port), port


class TestTheApiTierResolvesCold:
    def test_an_api_event_publishes_at_full_confidence_with_nothing_else_known(self, api_source):
        report, _ = _run(api_source)

        event = Event.objects.using(CATALOG).get(source_event_id="G5diZ9K1avWuW")
        assert report.counts["new"] == 4
        assert event.tz_inference_confidence == Decimal("1.00")
        assert event.publication_status == "published"
        assert event.tz_review_pending is False
        assert event.start_time_tz == "America/New_York"

    def test_it_needed_no_venue_and_no_city_zone(self, api_source):
        # The two fallbacks the rest of this intent builds. Neither is in play here, which
        # is the point: this tier is the one that works in a city we have never seen.
        _run(api_source)

        assert api_source.city_tz == ""
        assert not Venue.objects.using(CATALOG).exists()
        assert Event.objects.using(CATALOG).filter(venue__isnull=False).count() == 0

    def test_every_event_on_the_page_resolves_at_the_full_tier(self, api_source):
        # Not one lucky row: all four, including the all-day one, carry an IANA zone, so all
        # four reach row A1 at 1.00. A venue reading would be 0.95 and a city zone 0.90.
        _run(api_source)

        confidences = {e.tz_inference_confidence for e in Event.objects.using(CATALOG)}

        assert confidences == {Decimal("1.00")}

    def test_an_api_source_was_inert_before_this_parser_existed(self, api_source):
        # Regression guard for the gap this item closed: with no PARSERS["api"] the run
        # ended `parse_failed` / `parse_unsupported_method` and wrote nothing.
        report, _ = _run(api_source)

        assert report.outcome != "parse_failed"
        assert Event.objects.using(CATALOG).exists()


class TestTheKeyNeverLandsAnywhere:
    @override_settings(TICKETMASTER_API_KEY=KEY)
    def test_the_key_is_added_for_the_fetch_and_marked_as_a_credential(self, api_source):
        _, port = _run(api_source)

        [call] = port.calls
        assert f"apikey={KEY}" in call["url"]
        # The flag that stops httpx writing the URL it is fetching.
        assert call["credential"] is True

    @override_settings(TICKETMASTER_API_KEY=KEY)
    def test_the_stored_source_url_still_has_no_key(self, api_source):
        _run(api_source)

        stored = Source.objects.using(CATALOG).get(pk=api_source.pk)
        assert "apikey" not in stored.url
        assert KEY not in stored.url

    @override_settings(TICKETMASTER_API_KEY=KEY)
    def test_the_key_is_stripped_from_whatever_the_fetch_reports_back(self, api_source):
        # Belt and braces: the provider wrote the key into its own final URL. It must not
        # reach `fetched_url`, which is a column, nor the parser's base URL.
        echoed = ok(body(), url=f"{DISCOVERY}&apikey={KEY}")

        _run(api_source, ScriptedFetchPort().serve(echoed))

        stored = Source.objects.using(CATALOG).get(pk=api_source.pk)
        assert KEY not in stored.fetched_url
        assert "apikey" not in stored.fetched_url

    def test_without_a_configured_key_the_url_is_fetched_unchanged(self, api_source):
        # A deployment with no key must still boot and still run. The provider answers 401
        # and the source records it, which is a fact an editor can see.
        with override_settings(TICKETMASTER_API_KEY=""):
            _, port = _run(api_source)

        [call] = port.calls
        assert call["url"] == DISCOVERY
        assert call["credential"] is False

    @override_settings(TICKETMASTER_API_KEY=KEY)
    def test_a_non_provider_source_is_untouched(self):
        rss = SourceFactory(url="https://feeds.example.test/events.rss")
        port = ScriptedFetchPort().serve(
            ok(b"<rss></rss>", url="https://feeds.example.test/events.rss")
        )

        ingest_source(rss.id, fetch_port=port)

        [call] = port.calls
        assert call["url"] == "https://feeds.example.test/events.rss"
        assert call["credential"] is False


class TestTheKeyLookupIsTotal:
    """`provider_keys` runs on every fetch, including the ones it has nothing to do with."""

    @pytest.mark.parametrize("url", ["http://[", "", "not a url at all", "mailto:x@y.test"])
    def test_a_url_it_cannot_parse_is_simply_not_a_provider(self, url):
        assert authorized_url(url) == (url, False)
        assert strip_key(url) == url


class TestWhatTheProviderSaysNo:
    def test_a_provider_error_envelope_fails_the_run_rather_than_emptying_the_city(
        self, api_source
    ):
        # The distinction worth protecting: a bad key or a rate limit is not "this city has
        # no events". The run fails and the source records why.
        report, _ = _run(api_source, name="ticketmaster-fault.json")

        assert report.outcome == "parse_failed"
        assert not Event.objects.using(CATALOG).exists()

    def test_an_empty_page_is_a_successful_run_with_nothing_in_it(self, api_source):
        report, _ = _run(api_source, name="ticketmaster-empty.json")

        assert report.outcome == "ok"
        assert not Event.objects.using(CATALOG).exists()
