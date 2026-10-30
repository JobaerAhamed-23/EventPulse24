"""The geo port and its two adapters (FR-2).

The header is **untrusted input** — it came from the caller — and this file is where
that is pinned: the value is length-bounded, URL-decoded **exactly once**, and
normalized into a city shape.

The "exactly once" part is the one that matters most. Decoding twice is how
`%252e%252e%252f` becomes `../`: the first decode turns it into `%2e%2e%2f`, which
looks encoded and innocent, and the second decode turns it into a path traversal.
"""

import pytest
from django.test import override_settings

from adapters.geo.fake import FakeGeoAdapter
from adapters.geo.header import HeaderGeoAdapter, normalize_city
from ports.geo import GeoPort
from shared.constants import GEO_CITY_MAX_LENGTH, GEO_HEADER_NAME

pytestmark = pytest.mark.django_db


# ── The real adapter: reading the header ───────────────────────────────────────────


def test_the_header_adapter_reads_the_geo_header():
    adapter = HeaderGeoAdapter()

    assert adapter.resolve_city({GEO_HEADER_NAME: "Brooklyn"}) == "Brooklyn"


def test_the_header_is_read_case_insensitively():
    """HTTP header names are case-insensitive, and the port takes a plain mapping.

    Django's `request.headers` folds them; a plain mapping might not. The adapter does
    the folding itself rather than assuming the caller's mapping is a Django one.
    """
    adapter = HeaderGeoAdapter()

    assert adapter.resolve_city({"X-Vercel-IP-City": "Brooklyn"}) == "Brooklyn"


def test_a_missing_header_is_no_location():
    adapter = HeaderGeoAdapter()

    assert adapter.resolve_city({}) is None
    assert adapter.resolve_city({"user-agent": "curl"}) is None


def test_the_header_value_is_length_bounded():
    """A 10 KB "city" is not a city, it is an attempt to put a value somewhere it should not go."""
    adapter = HeaderGeoAdapter()

    too_long = "B" * (GEO_CITY_MAX_LENGTH + 1)

    assert adapter.resolve_city({GEO_HEADER_NAME: too_long}) is None


def test_a_value_at_the_bound_is_accepted():
    adapter = HeaderGeoAdapter()

    at_bound = "B" * GEO_CITY_MAX_LENGTH

    assert adapter.resolve_city({GEO_HEADER_NAME: at_bound}) == at_bound


def test_the_header_is_url_decoded_exactly_once():
    """One decode, not two.

    `%2520` is a space that was encoded twice. One decode turns it into `%20` — still
    encoded. A second decode would turn it into a space, and that is the same shape of
    mistake that turns `%252e%252e%252f` into `../`.

    The space is the probe because it survives the city's shape: a space is inside the
    allowed set, so the difference between "decoded once" and "decoded twice" is visible
    in the result.
    """
    adapter = HeaderGeoAdapter()

    assert adapter.resolve_city({GEO_HEADER_NAME: "Brooklyn%2520NY"}) == "Brooklyn20NY"


def test_an_ordinary_encoded_header_is_decoded():
    """The edge encodes the city, because a raw header cannot carry every character.

    `%20` is a space; one decode turns it into a space.
    """
    adapter = HeaderGeoAdapter()

    assert adapter.resolve_city({GEO_HEADER_NAME: "Brooklyn%20NY"}) == "Brooklyn NY"


def test_a_character_outside_the_city_shape_is_dropped_after_decoding():
    """The decode happens first, and the shape check second.

    `%2C` is a comma. The edge sends `Brooklyn%2CNY` for "Brooklyn, NY", and a comma is
    not part of a city's shape, so it is dropped — the result is `BrooklynNY`, not
    `Brooklyn,NY`. A comma is also a SQL-ish and a path-ish character, so dropping it
    rather than keeping it is the point of the shape check.
    """
    adapter = HeaderGeoAdapter()

    assert adapter.resolve_city({GEO_HEADER_NAME: "Brooklyn%2CNY"}) == "BrooklynNY"


def test_a_double_encoded_traversal_is_not_decoded_into_one():
    """The end-to-end version of the once-only rule.

    After one decode the value is `%2e%2e%2f` — which contains a path separator only
    after a *second* decode, so it must never become `../`.
    """
    adapter = HeaderGeoAdapter()

    resolved = adapter.resolve_city({GEO_HEADER_NAME: "%252e%252e%252f"})

    assert resolved is not None
    assert "/" not in resolved
    assert ".." not in resolved


def test_the_header_adapter_does_no_lookup_and_calls_no_vendor():
    """The adapter reads a header. That is the whole of it.

    There is no database access, no HTTP call and no clock in the module — so a test can
    assert the *shape* of the adapter rather than merely that it returns something.
    """
    import inspect

    from adapters.geo import header as header_module

    source = inspect.getsource(header_module)

    for forbidden in ("django.db", "httpx", "requests", "urllib.request", "socket"):
        assert forbidden not in source, f"the geo adapter must not reach {forbidden}"


# ── Normalizing a city ─────────────────────────────────────────────────────────────


def test_normalizing_collapses_whitespace():
    assert normalize_city("  Brooklyn   NY ") == "Brooklyn NY"


def test_normalizing_drops_characters_outside_the_city_shape():
    """Dropped, not replaced — so the output is inside the allowed set by construction."""
    assert normalize_city("Brooklyn/NY") == "BrooklynNY"
    assert normalize_city("<script>") == "script"


def test_normalizing_nothing_is_nothing():
    assert normalize_city("") is None
    assert normalize_city("   ") is None
    assert normalize_city("///") is None


def test_normalizing_keeps_the_characters_a_city_name_needs():
    assert normalize_city("New York City") == "New York City"
    assert normalize_city("St. John's") == "St John's"
    assert normalize_city("Saint-Denis") == "Saint-Denis"


# ── The fake adapter ───────────────────────────────────────────────────────────────


def test_the_fake_reports_its_configured_city():
    with override_settings(GEO_FAKE_CITY="Brooklyn"):
        assert FakeGeoAdapter().resolve_city({}) == "Brooklyn"


def test_the_fake_reports_no_location_when_none_is_configured():
    """The geo-miss branch: with nothing configured, the fake says nothing."""
    with override_settings(GEO_FAKE_CITY=None):
        assert FakeGeoAdapter().resolve_city({}) is None


def test_the_fake_ignores_the_headers():
    """The fake is deterministic. A test that wants the header's behaviour reaches for
    the real adapter."""
    with override_settings(GEO_FAKE_CITY="Brooklyn"):
        assert FakeGeoAdapter().resolve_city({GEO_HEADER_NAME: "Queens"}) == "Brooklyn"


# ── The port ───────────────────────────────────────────────────────────────────────


def test_both_adapters_implement_the_port():
    """The registry resolves the adapter by the port's type, so the two must agree."""
    assert isinstance(HeaderGeoAdapter(), GeoPort)
    assert isinstance(FakeGeoAdapter(), GeoPort)


def test_the_port_takes_headers_and_not_a_request():
    """The port's signature is the design: a bag of headers in, a city out.

    A port whose input were a `request` would let an adapter reach the session, the
    cookies and the host's middleware — and the code would depend on the host (AD-1).
    """
    import inspect

    signature = inspect.signature(GeoPort.resolve_city)
    annotation = signature.parameters["headers"].annotation

    assert "Mapping" in str(annotation)


def test_the_registry_resolves_the_geo_port():
    from ports.registry import get_geo_port

    assert isinstance(get_geo_port(), GeoPort)
