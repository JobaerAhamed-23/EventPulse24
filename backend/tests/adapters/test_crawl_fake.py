"""FakeFetchAdapter: fixtures validated up front, RFC 9110 conditionals, simulated failures."""

import json

import pytest
from django.core.exceptions import ImproperlyConfigured

from adapters.crawl.fake import FakeFetchAdapter, load_index
from ports.fetch import (
    FetchBlockedError,
    FetchContentError,
    FetchHTTPError,
    FetchNetworkError,
    FetchRedirectError,
    FetchTimeoutError,
    FetchTooLargeError,
)

URL = "https://fixtures.example.test/feed.rss"
DATE = "Wed, 04 Nov 2026 10:00:00 GMT"
LATER = "Thu, 05 Nov 2026 10:00:00 GMT"
EARLIER = "Tue, 03 Nov 2026 10:00:00 GMT"


@pytest.fixture
def fixtures(tmp_path):
    (tmp_path / "feed.rss").write_bytes(b"<rss/>")

    def write(index: dict):
        (tmp_path / "index.json").write_text(json.dumps(index))
        return tmp_path

    return write


def entry(**extra):
    return {"file": "feed.rss", "content_type": "application/rss+xml", **extra}


def test_serves_the_fixture_with_its_validators(fixtures):
    adapter = FakeFetchAdapter(fixtures({URL: entry(etag='"v1"', last_modified=DATE)}))

    result = adapter.fetch(URL)

    assert (result.status, result.body, result.content_type) == (
        200,
        b"<rss/>",
        "application/rss+xml",
    )
    assert (result.etag, result.last_modified, result.final_url) == ('"v1"', DATE, URL)


def test_matching_etag_is_not_modified(fixtures):
    adapter = FakeFetchAdapter(fixtures({URL: entry(etag='"v1"')}))

    result = adapter.fetch(URL, etag='"v1"')

    assert result.not_modified and result.body == b"" and result.etag == '"v1"'


def test_different_etag_is_a_full_response(fixtures):
    assert (
        FakeFetchAdapter(fixtures({URL: entry(etag='"v2"')})).fetch(URL, etag='"v1"').status == 200
    )


def test_no_validator_on_either_side_is_never_not_modified(fixtures):
    adapter = FakeFetchAdapter(fixtures({URL: entry()}))

    assert adapter.fetch(URL).status == 200
    assert adapter.fetch(URL, etag='"v1"').status == 200  # the entry has no etag


@pytest.mark.parametrize(
    ("since", "status"), [(DATE, 304), (LATER, 304), (EARLIER, 200), ("garbage", 200)]
)
def test_if_modified_since_compares_dates(fixtures, since, status):
    adapter = FakeFetchAdapter(fixtures({URL: entry(last_modified=DATE)}))

    assert adapter.fetch(URL, last_modified=since).status == status


def test_if_none_match_takes_precedence_over_if_modified_since(fixtures):
    adapter = FakeFetchAdapter(fixtures({URL: entry(etag='"v2"', last_modified=DATE)}))

    assert adapter.fetch(URL, etag='"v1"', last_modified=LATER).status == 200


def test_fixture_removed_after_startup_is_a_port_error(fixtures):
    directory = fixtures({URL: entry()})
    adapter = FakeFetchAdapter(directory)
    (directory / "feed.rss").unlink()

    with pytest.raises(FetchNetworkError) as excinfo:
        adapter.fetch(URL)

    assert excinfo.value.reason == "fixture_unreadable"


def test_unknown_url_is_a_404(fixtures):
    with pytest.raises(FetchHTTPError) as excinfo:
        FakeFetchAdapter(fixtures({URL: entry()})).fetch("https://elsewhere.example.test/")

    assert excinfo.value.status == 404


@pytest.mark.parametrize(
    ("simulate", "error"),
    [
        ("timeout", FetchTimeoutError),
        ("too_large", FetchTooLargeError),
        ("blocked", FetchBlockedError),
        ("network", FetchNetworkError),
        ("content", FetchContentError),
        ("redirects", FetchRedirectError),
        ({"status": 503}, FetchHTTPError),
    ],
    ids=str,
)
def test_simulated_failures(fixtures, simulate, error):
    adapter = FakeFetchAdapter(
        fixtures({URL: {"content_type": "text/plain", "simulate": simulate}})
    )

    with pytest.raises(error):
        adapter.fetch(URL)


@pytest.mark.parametrize(
    ("index", "message"),
    [
        ({URL: entry(file="../../.env")}, "outside the fixtures dir"),
        ({URL: entry(file="missing.rss")}, "is missing"),
        ({URL: {"file": "feed.rss"}}, "content_type"),
        ({URL: {"content_type": "text/plain"}}, "a file or a simulate"),
        ({URL: entry(simulate="explode")}, "unknown simulate"),
        ({URL: entry(simulate={"status": 200})}, "300-599"),
        ({URL: entry(last_modified="yesterday")}, "HTTP date"),
        (["not", "a", "map"], "map URLs"),
    ],
    ids=[
        "escape",
        "missing-file",
        "no-content-type",
        "no-file",
        "bad-simulate",
        "bad-status",
        "bad-date",
        "not-a-map",
    ],
)
def test_invalid_index_fails_when_the_adapter_is_built(fixtures, index, message):
    with pytest.raises(ImproperlyConfigured, match=message):
        FakeFetchAdapter(fixtures(index))


def test_missing_or_broken_index_fails_up_front(tmp_path):
    with pytest.raises(ImproperlyConfigured, match="No index.json"):
        load_index(tmp_path)

    (tmp_path / "index.json").write_text("{not json")
    with pytest.raises(ImproperlyConfigured, match="not valid JSON"):
        load_index(tmp_path)


def test_default_fixtures_dir_from_settings_is_valid():
    adapter = FakeFetchAdapter()

    result = adapter.fetch("https://fixtures.example.test/sample.rss")

    assert result.status == 200 and b"<rss" in result.body


def test_registry_builds_the_fake_fetch_adapter_by_default(settings):
    """**The fake table is pinned, not inherited from the developer's `.env`.**

    `SOURCE_FETCH` overrides this port on its own, and a developer who has set it — to
    crawl real feeds, or because `CALENDAR_ADAPTER=ics` requires it — would otherwise see
    this fail for a configuration choice rather than for a defect. What the test means is
    "fake mode builds the fake adapter", so it states fake mode.
    """
    from config.adapters import FAKE_ADAPTERS
    from ports.registry import get_fetch_port

    settings.ADAPTERS = dict(FAKE_ADAPTERS)

    assert isinstance(get_fetch_port(), FakeFetchAdapter)


def test_registry_builds_the_http_adapter_with_limits_from_settings(settings):
    from adapters.crawl.http import HttpFetchAdapter
    from ports.registry import get_fetch_port

    settings.ADAPTERS = {**settings.ADAPTERS, "fetch": "adapters.crawl.http.HttpFetchAdapter"}

    adapter = get_fetch_port()

    assert isinstance(adapter, HttpFetchAdapter)
    assert adapter._limits.allowed_ports == frozenset({80, 443})
    assert adapter._limits.max_bytes == settings.SOURCE_FETCH["max_bytes"]
    assert adapter._limits.user_agent.startswith("EventPulse24-SourceFetcher/")
