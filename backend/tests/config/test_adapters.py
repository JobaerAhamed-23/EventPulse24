"""ADAPTER_MODE picks the adapter table; `real` fails at startup until real adapters exist."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from config.adapters import (
    BLOB_ADAPTERS,
    CALENDAR_ADAPTERS,
    FAKE_ADAPTERS,
    FETCH_ADAPTERS,
    REAL_ADAPTERS,
    THROTTLE_ADAPTERS,
    adapter_paths,
)
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


#: The ports a developer's `.env` may redirect without changing the mode.
#:
#: Each has its own variable — `THROTTLE_ADAPTER`, `SOURCE_FETCH`, `CALENDAR_ADAPTER`,
#: `BLOB_ADAPTER` — and the local `.env` genuinely sets some of them:
#: `THROTTLE_ADAPTER=redis` always, and `CALENDAR_ADAPTER=ics` with `SOURCE_FETCH=http` on
#: a machine importing a real calendar.
#:
#: **`blob` is here because the *test settings* override it**, not because `.env` does:
#: `config/settings_test.py` points it at the in-memory adapter so the suite dials no
#: object store. That is exactly the "mode's table with a per-port override applied" case
#: this map describes.
OVERRIDABLE = {
    "throttle": THROTTLE_ADAPTERS,
    "fetch": FETCH_ADAPTERS,
    "calendar": CALENDAR_ADAPTERS,
    "blob": BLOB_ADAPTERS,
}


def test_settings_use_the_fake_table_by_default(settings):
    """The settings carry the fake table — except for ports an override names.

    The *whole* table is not necessarily the fake one, because three ports are
    individually redirectable and the local `.env` uses that. What the test means is "the
    mode's table, with any per-port override applied": every overridable port holds one of
    its own legal values, and every other port is exactly what fake mode says.
    """
    for port, choices in OVERRIDABLE.items():
        assert settings.ADAPTERS[port] in choices.values(), port

    assert {k: v for k, v in settings.ADAPTERS.items() if k not in OVERRIDABLE} == {
        k: v for k, v in FAKE_ADAPTERS.items() if k not in OVERRIDABLE
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


# --- CALENDAR_ADAPTER ---------------------------------------------------------------------------
#
# The override that lets a local run import a *real* calendar while every other adapter stays
# fake. It exists because the calendar fake is the one stand-in a developer cannot see: it
# returns two well-formed events for any address, so a connected Google calendar looks healthy,
# recent and error-free while showing somebody else's events.


def test_the_calendar_adapter_defaults_to_the_mode():
    """Unset: follow ADAPTER_MODE, exactly as the fetch and throttle ports do.

    **The default local stack is unchanged.** A developer who adds nothing to their `.env`
    keeps the fake importer they have today.
    """
    assert adapter_paths("fake")["calendar"] == FAKE_ADAPTERS["calendar"]
    assert adapter_paths("fake", calendar="fake")["calendar"] == FAKE_ADAPTERS["calendar"]


def test_the_calendar_adapter_ics_swaps_only_the_calendar_adapter():
    paths = adapter_paths("fake", calendar="ics")

    assert paths["calendar"] == "adapters.calendar.ics.IcsCalendarAdapter"
    assert {k: v for k, v in paths.items() if k != "calendar"} == {
        k: v for k, v in FAKE_ADAPTERS.items() if k != "calendar"
    }


def test_every_calendar_adapter_satisfies_the_port():
    from ports.calendar import CalendarPort

    for path in CALENDAR_ADAPTERS.values():
        assert issubclass(import_string(path), CalendarPort), path


def test_the_three_overrides_are_independent():
    """Naming one does not disturb the others."""
    paths = adapter_paths("fake", "http", "redis", "ics")

    assert paths["fetch"] == "adapters.crawl.http.HttpFetchAdapter"
    assert paths["throttle"] == "adapters.throttle.redis.RedisThrottleAdapter"
    assert paths["calendar"] == "adapters.calendar.ics.IcsCalendarAdapter"


# --- the object store ---


def test_blob_adapter_overrides_only_that_port():
    """Like SOURCE_FETCH, THROTTLE_ADAPTER and CALENDAR_ADAPTER: it names one adapter and
    leaves every other port on the table the mode chose."""
    paths = adapter_paths("fake", blob="memory")

    assert paths["blob"] == BLOB_ADAPTERS["memory"]
    assert paths["email"] == FAKE_ADAPTERS["email"]


def test_an_unset_blob_override_follows_the_mode():
    """The default local stack is unchanged: fake mode still stores bytes for real."""
    assert adapter_paths("fake")["blob"] == FAKE_ADAPTERS["blob"]


def test_fake_mode_stores_bytes_for_real_like_email_sends_for_real():
    """**MinIO is Mailpit for bytes.** A fake object store would let a wrong endpoint, a
    missing bucket or an unsigned URL pass the local stack and fail at a deploy."""
    assert adapter_paths("fake")["blob"] == BLOB_ADAPTERS["s3"]


def test_both_blob_adapters_implement_the_port():
    from ports.blob import BlobPort

    for path in BLOB_ADAPTERS.values():
        assert issubclass(import_string(path), BlobPort), path
