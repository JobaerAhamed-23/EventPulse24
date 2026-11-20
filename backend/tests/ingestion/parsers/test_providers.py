"""`api`-method dispatch (FR-17's top tier): which reader, and what happens when there is none.

The package's standing promise is bytes in, candidates out, never an exception. For this
parser the interesting half is the *negative* space — an unknown host, a provider error
envelope, bytes that are not JSON — because an `api` source is registered by an operator
and the pipeline has to report what went wrong rather than die or, worse, quietly say the
city has no events.
"""

import json
import re
from pathlib import Path
from uuid import UUID

import pytest

from apps.ingestion.models import AcquisitionMethod
from apps.ingestion.parsers import PARSERS, parse
from apps.ingestion.parsers.providers import READERS, parse_api
from apps.ingestion.parsers.types import SourceContext

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "sources"
SOURCE = UUID(int=11)
DISCOVERY = "https://app.ticketmaster.com/discovery/v2/events.json?city=Dhaka"


def context(url: str = DISCOVERY) -> SourceContext:
    return SourceContext(SOURCE, url)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestRegistration:
    def test_api_has_a_parser_at_last(self):
        # The gap this item exists to close: AcquisitionMethod had seven values and PARSERS
        # had four, so an `api` source could never produce a single event.
        assert PARSERS["api"] is parse_api

    @pytest.mark.parametrize("method", ["partnership", "crawl"])
    def test_partnership_and_crawl_stay_unsupported(self, method):
        # Deliberately still absent (AC 12). Both need an agreement or an approved ToS review
        # before anything is read, and widening FR-17's hierarchy is not this item's business.
        assert method in AcquisitionMethod.values
        assert parse(method, b"{}", context()).error == "unsupported_method"

    def test_every_registered_method_is_a_real_acquisition_method(self):
        assert set(PARSERS) <= set(AcquisitionMethod.values)


class TestDispatch:
    def test_a_known_host_reaches_its_reader(self):
        result = parse_api(fixture("ticketmaster-events.json"), context())

        assert result.error is None
        assert result.candidates

    @pytest.mark.parametrize(
        "url",
        [
            "https://app.ticketmaster.com.evil.test/discovery/v2/events.json",
            "https://notticketmaster.com/discovery/v2/events.json",
            "https://ticketmaster.com/discovery/v2/events.json",
            "https://app.ticketmaster.com.co/discovery/v2/events.json",
        ],
    )
    def test_a_lookalike_host_is_not_our_provider(self, url):
        # The whole reason dispatch is an exact-match dict. A suffix match would hand an
        # attacker-chosen document to a reader that trusts its shape — and `provider_keys`
        # matches the same way, where the stake is our API key rather than our credulity.
        assert parse_api(fixture("ticketmaster-events.json"), context(url)).error == (
            "unknown_api_provider"
        )

    def test_an_unregistered_host_reports_rather_than_raises(self):
        result = parse_api(b"{}", context("https://some-other-provider.example.test/v1/events"))

        assert result.error == "unknown_api_provider"
        assert result.candidates == []

    def test_an_unparseable_source_url_reports_rather_than_raises(self):
        assert parse_api(b"{}", context("http://[")).error == "unknown_api_provider"

    def test_dispatch_is_case_insensitive_on_the_host(self):
        assert parse_api(fixture("ticketmaster-events.json"), context(DISCOVERY.upper())).candidates

    def test_every_reader_host_is_lowercase(self):
        # The lookup lowercases the URL's host, so an uppercase key would be unreachable.
        assert [host for host in READERS if host != host.lower()] == []


class TestADocumentWeCannotRead:
    @pytest.mark.parametrize(
        "content",
        [b"", b"not json at all", b"{", b"\xff\xfe\x00", json.dumps([1, 2, 3]).encode()],
        ids=["empty", "prose", "truncated", "invalid-utf8", "json-but-not-an-object"],
    )
    def test_malformed_content_is_a_clean_result(self, content):
        result = parse_api(content, context())

        assert result.candidates == []
        assert result.error in {"invalid_json", None}

    @pytest.mark.parametrize("name", ["ticketmaster-fault.json", "ticketmaster-errors.json"])
    def test_a_provider_error_envelope_is_an_error_not_an_empty_page(self, name):
        # The distinction that matters: "the provider said no" must not reach a reader as
        # "this city has no events". One is a bad key or a rate limit; the other is a claim
        # about the world.
        assert parse_api(fixture(name), context()).error == "provider_error"

    def test_an_empty_page_is_a_real_answer_not_an_error(self):
        result = parse_api(fixture("ticketmaster-empty.json"), context())

        assert (result.error, result.candidates) == (None, [])

    def test_parse_never_raises_whatever_the_bytes(self):
        # `parse()` has a catch-all for a parser that breaks its promise; this asserts this
        # parser does not need it.
        for content in (b"", b"[]", b"null", b'{"_embedded": {"events": "not a list"}}'):
            assert parse("api", content, context()).error != "parser_failure"


class TestNoFixtureCarriesAKey:
    """AC 11. A recorded fixture is the obvious place for a live key to get committed."""

    KEY_SHAPED = re.compile(r"(?i)apikey=\S|[A-Za-z0-9]{24,}")

    @pytest.mark.parametrize(
        "path", sorted(FIXTURES.glob("ticketmaster-*.json")), ids=lambda p: p.name
    )
    def test_fixture_has_nothing_key_shaped_in_it(self, path):
        found = self.KEY_SHAPED.findall(path.read_text())

        assert found == [], f"{path.name} may contain a credential: {found}"

    def test_the_scan_would_catch_one(self):
        # Guards the guard: a test that cannot fail proves nothing.
        assert self.KEY_SHAPED.findall('{"url": "https://x/?apikey=k9SdF3mQ2pZxAa1bCc4dEe7f"}')
