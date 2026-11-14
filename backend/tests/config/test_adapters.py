"""ADAPTER_MODE picks the adapter table; `real` fails at startup until real adapters exist."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from config.adapters import FAKE_ADAPTERS, REAL_ADAPTERS, THROTTLE_ADAPTERS, adapter_paths
from ports.registry import PORT_KEYS


def test_fake_mode_maps_every_port_to_an_implementation():
    paths = adapter_paths("fake")

    for port, key in PORT_KEYS.items():
        assert issubclass(import_string(paths[key]), port), key


def test_fake_mode_returns_a_copy():
    adapter_paths("fake")["email"] = "changed"

    assert FAKE_ADAPTERS["email"] == "adapters.email.smtp.SmtpEmailAdapter"


def test_real_mode_fails_and_names_every_missing_adapter():
    """**`embedding` is no longer on the list, and that is the point.**

    FR-25 added the real Voyage adapter, so `adapters.llm.voyage.VoyageEmbeddingAdapter`
    is in the real table. `llm` and `email` still have no real adapter, so real mode
    still refuses to boot — which is correct: this item ships embeddings, not go-live.
    """
    with pytest.raises(ImproperlyConfigured) as excinfo:
        adapter_paths("real")

    assert str(excinfo.value) == (
        "ADAPTER_MODE=real is not available yet: no real adapter for email, llm."
    )


def test_real_mode_has_the_voyage_embedding_adapter():
    """FR-25: the real embedding adapter is the one that reaches Voyage."""
    assert REAL_ADAPTERS["embedding"] == "adapters.llm.voyage.VoyageEmbeddingAdapter"


def test_the_real_embedding_adapter_implements_the_port():
    from django.utils.module_loading import import_string

    from ports.embedding import EmbeddingPort

    adapter = import_string(REAL_ADAPTERS["embedding"])

    assert issubclass(adapter, EmbeddingPort)


def test_settings_use_the_fake_table_by_default(settings):
    """The settings carry the fake table — unless an override names another port.

    The local `.env` sets `THROTTLE_ADAPTER=redis`, so the *whole* table is not
    necessarily the fake one. What the test means is "the mode's table, with any
    per-port override applied" — so it compares against the table the mode would
    produce, with the overrides the environment actually names.
    """
    assert settings.ADAPTERS["throttle"] in THROTTLE_ADAPTERS.values()
    assert {k: v for k, v in settings.ADAPTERS.items() if k != "throttle"} == {
        k: v for k, v in FAKE_ADAPTERS.items() if k != "throttle"
    }


def test_fake_mode_fetches_from_fixtures_by_default():
    assert adapter_paths("fake")["fetch"] == "adapters.crawl.fake.FakeFetchAdapter"


def test_source_fetch_http_swaps_only_the_fetch_adapter():
    paths = adapter_paths("fake", "http")

    assert paths["fetch"] == "adapters.crawl.http.HttpFetchAdapter"
    assert {k: v for k, v in paths.items() if k != "fetch"} == {
        k: v for k, v in FAKE_ADAPTERS.items() if k != "fetch"
    }


def test_the_throttle_adapter_defaults_to_the_mode():
    """Unset: follow ADAPTER_MODE, exactly as the fetch port does."""
    assert adapter_paths("fake")["throttle"] == FAKE_ADAPTERS["throttle"]
    assert adapter_paths("fake", throttle="memory")["throttle"] == FAKE_ADAPTERS["throttle"]


def test_the_throttle_adapter_redis_swaps_only_the_throttle_adapter():
    """The throttle's counter store is the one thing a local run cannot fake.

    Every other port's fake is stateless, so a local run loses nothing by faking it. The
    throttle's counters are the product's rate limits and the save cap, and they are read
    by the API, spent by the API and cleared by the seed command — three processes that
    must see one set of numbers. So the override moves that one port and nothing else.
    """
    paths = adapter_paths("fake", throttle="redis")

    assert paths["throttle"] == "adapters.throttle.redis.RedisThrottleAdapter"
    assert {k: v for k, v in paths.items() if k != "throttle"} == {
        k: v for k, v in FAKE_ADAPTERS.items() if k != "throttle"
    }


def test_the_throttle_adapter_names_an_implementation_that_satisfies_the_port():
    from ports.throttle import ThrottlePort

    for path in THROTTLE_ADAPTERS.values():
        assert issubclass(import_string(path), ThrottlePort), path


def test_the_throttle_override_does_not_change_the_fetch_override():
    """The two overrides are independent: naming one does not disturb the other."""
    paths = adapter_paths("fake", "http", "redis")

    assert paths["fetch"] == "adapters.crawl.http.HttpFetchAdapter"
    assert paths["throttle"] == "adapters.throttle.redis.RedisThrottleAdapter"


def test_real_mode_has_the_http_fetch_adapter():
    assert REAL_ADAPTERS["fetch"] == "adapters.crawl.http.HttpFetchAdapter"


def test_real_mode_has_the_ics_calendar_adapter():
    """One adapter for all three providers: they all publish iCalendar."""
    assert REAL_ADAPTERS["calendar"] == "adapters.calendar.ics.IcsCalendarAdapter"


def test_the_real_calendar_adapter_implements_the_port():
    from django.utils.module_loading import import_string

    from ports.calendar import CalendarPort

    adapter = import_string(REAL_ADAPTERS["calendar"])

    assert issubclass(adapter, CalendarPort)


def test_real_mode_has_the_header_geo_adapter():
    """The real geo adapter reads the edge's header — no vendor, no lookup.

    The `real` mode is not yet selectable (four ports still have no real adapter), so
    the real table is checked here one entry at a time rather than by reaching the
    `return dict(REAL_ADAPTERS)` line.
    """
    assert REAL_ADAPTERS["geo"] == "adapters.geo.header.HeaderGeoAdapter"


def test_the_real_geo_adapter_implements_the_port():
    from django.utils.module_loading import import_string

    from ports.geo import GeoPort

    adapter = import_string(REAL_ADAPTERS["geo"])

    assert issubclass(adapter, GeoPort)
