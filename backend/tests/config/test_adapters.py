"""ADAPTER_MODE picks the adapter table; `real` fails at startup until real adapters exist."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from config.adapters import FAKE_ADAPTERS, REAL_ADAPTERS, adapter_paths
from ports.registry import PORT_KEYS


def test_fake_mode_maps_every_port_to_an_implementation():
    paths = adapter_paths("fake")

    for port, key in PORT_KEYS.items():
        assert issubclass(import_string(paths[key]), port), key


def test_fake_mode_returns_a_copy():
    adapter_paths("fake")["email"] = "changed"

    assert FAKE_ADAPTERS["email"] == "adapters.email.smtp.SmtpEmailAdapter"


def test_real_mode_fails_and_names_every_missing_adapter():
    with pytest.raises(ImproperlyConfigured) as excinfo:
        adapter_paths("real")

    assert str(excinfo.value) == (
        "ADAPTER_MODE=real is not available yet: "
        "no real adapter for billing, email, embedding, llm."
    )


def test_settings_use_the_fake_table_by_default(settings):
    assert settings.ADAPTERS == FAKE_ADAPTERS


def test_fake_mode_fetches_from_fixtures_by_default():
    assert adapter_paths("fake")["fetch"] == "adapters.crawl.fake.FakeFetchAdapter"


def test_source_fetch_http_swaps_only_the_fetch_adapter():
    paths = adapter_paths("fake", "http")

    assert paths["fetch"] == "adapters.crawl.http.HttpFetchAdapter"
    assert {k: v for k, v in paths.items() if k != "fetch"} == {
        k: v for k, v in FAKE_ADAPTERS.items() if k != "fetch"
    }


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
