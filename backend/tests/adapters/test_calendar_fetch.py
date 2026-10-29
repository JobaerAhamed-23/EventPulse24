"""The calendar fetch through the *real* hardened client: the SSRF policy still holds.

The adapter's own logic is proven in `test_calendar_ics.py`, against a scripted fetch.
This file proves the fetch *underneath* it — the shared `HttpFetchAdapter` — with the
calendar's one relaxation in force.

**What the relaxation changes and what it does not.** `allow_cross_host_redirect=True`
lets the *host* differ between hops, because every provider redirects the address the
user pasted to a CDN host. It does **not** relax the address policy: the check happens
at connect time on every hop, so a redirect to a private address is still refused.

Every test here runs on the scripted network — real httpx, real httpcore, no socket.
"""

import pytest

from adapters.crawl.http import HttpFetchAdapter
from ports.fetch import (
    FetchBlockedError,
    FetchLimits,
    FetchNetworkError,
    FetchTooLargeError,
)
from tests.adapters.scripted_network import ScriptedNetwork, always, response

#: Real public addresses — the documentation ranges (TEST-NET) are *denied* by the
#: address policy, so a test that used them would pass for the wrong reason.
PUBLIC = "93.184.215.14"
CDN = "1.1.1.1"
PRIVATE = "169.254.169.254"


def redirect(location: str, status: int = 302) -> list:
    return response(status, headers={"Location": location})


def limits(**overrides) -> FetchLimits:
    return FetchLimits(user_agent="EventPulse24-Test/1.0", **overrides)


def adapter_for(network: ScriptedNetwork, **overrides) -> HttpFetchAdapter:
    return network.adapter(**overrides)


# ─── The cross-host relaxation ────────────────────────────────────────────────


def test_a_cross_host_redirect_is_followed_when_it_is_allowed():
    network = ScriptedNetwork()
    network.serve(
        "calendar.example.test",
        PUBLIC,
        always(*redirect("https://cdn.example.test/feed.ics")),
        port=443,
    )
    network.serve(
        "cdn.example.test",
        CDN,
        always(*response(200, b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")),
        port=443,
    )

    result = adapter_for(network).fetch(
        "https://calendar.example.test/feed.ics", allow_cross_host_redirect=True
    )

    assert result.status == 200
    assert [request.target for request in network.requests] == [
        "/feed.ics",
        "/feed.ics",
    ]


def test_a_cross_host_redirect_is_refused_by_default():
    """A source fetch keeps same-host-only redirects; the default is unchanged."""
    network = ScriptedNetwork()
    network.serve(
        "calendar.example.test",
        PUBLIC,
        always(*redirect("https://cdn.example.test/feed.ics")),
        port=443,
    )
    network.serve("cdn.example.test", CDN, always(*response(200, b"body")), port=443)

    with pytest.raises(FetchBlockedError) as excinfo:
        adapter_for(network).fetch("https://calendar.example.test/feed.ics")

    assert excinfo.value.reason == "cross_host_redirect"


# ─── The address policy, on every hop ─────────────────────────────────────────


def test_a_redirect_to_a_private_address_is_refused_even_when_cross_host_is_allowed():
    """The relaxation is about the *host*, never the address."""
    network = ScriptedNetwork()
    network.serve(
        "calendar.example.test",
        PUBLIC,
        always(*redirect(f"http://{PRIVATE}/latest/meta-data/")),
        port=443,
    )
    network.serve("169.254.169.254", PRIVATE, always(*response(200, b"secret")), port=443)

    with pytest.raises(FetchBlockedError) as excinfo:
        adapter_for(network).fetch(
            "https://calendar.example.test/feed.ics", allow_cross_host_redirect=True
        )

    assert excinfo.value.reason == "address"


def test_a_private_address_is_refused_on_the_first_hop():
    network = ScriptedNetwork()
    network.serve("calendar.example.test", PRIVATE, always(*response(200, b"secret")), port=443)

    with pytest.raises(FetchBlockedError) as excinfo:
        adapter_for(network).fetch(
            "https://calendar.example.test/feed.ics", allow_cross_host_redirect=True
        )

    assert excinfo.value.reason == "address"


def test_a_private_address_behind_a_public_host_is_refused():
    """DNS rebinding: the host resolves to a private address. The check is at connect time."""
    network = ScriptedNetwork()
    network.serve("calendar.example.test", PRIVATE, always(*response(200, b"secret")), port=443)

    with pytest.raises(FetchBlockedError) as excinfo:
        adapter_for(network).fetch(
            "https://calendar.example.test/feed.ics", allow_cross_host_redirect=True
        )

    assert excinfo.value.reason == "address"


def test_a_redirect_to_a_non_standard_port_is_refused():
    network = ScriptedNetwork()
    network.serve(
        "calendar.example.test",
        PUBLIC,
        always(*redirect("https://cdn.example.test:8443/feed.ics")),
        port=443,
    )
    network.serve("cdn.example.test", CDN, always(*response(200, b"body")), port=443)

    with pytest.raises(FetchBlockedError) as excinfo:
        adapter_for(network).fetch(
            "https://calendar.example.test/feed.ics", allow_cross_host_redirect=True
        )

    assert excinfo.value.reason == "port"


def test_a_redirect_with_credentials_in_the_url_is_refused():
    network = ScriptedNetwork()
    network.serve(
        "calendar.example.test",
        PUBLIC,
        always(*redirect("https://user:pass@cdn.example.test/feed.ics")),
        port=443,
    )
    network.serve("cdn.example.test", CDN, always(*response(200, b"body")), port=443)

    with pytest.raises(FetchBlockedError) as excinfo:
        adapter_for(network).fetch(
            "https://calendar.example.test/feed.ics", allow_cross_host_redirect=True
        )

    assert excinfo.value.reason == "userinfo"


# ─── The limits ───────────────────────────────────────────────────────────────


def test_a_body_over_the_budget_is_refused():
    network = ScriptedNetwork()
    body = b"x" * 2000
    network.serve("calendar.example.test", PUBLIC, always(*response(200, body)), port=443)

    with pytest.raises(FetchTooLargeError):
        adapter_for(network, max_bytes=1000).fetch(
            "https://calendar.example.test/feed.ics", allow_cross_host_redirect=True
        )


def test_a_per_call_limit_is_the_one_that_applies():
    """A caller with a different shape brings its own budget — and it is honoured.

    This is the calendar's case: a 5 MB decoded budget instead of the source's 10 MB, so
    the guard is the *same code* with different numbers, not a second copy of it.
    """
    network = ScriptedNetwork()
    body = b"x" * 2000
    network.serve("calendar.example.test", PUBLIC, always(*response(200, body)), port=443)

    with pytest.raises(FetchTooLargeError):
        adapter_for(network, max_bytes=10_000).fetch(
            "https://calendar.example.test/feed.ics",
            allow_cross_host_redirect=True,
            limits=FetchLimits(user_agent="EventPulse24-Calendar/1.0", max_bytes=1000),
        )


def test_the_default_limit_still_applies_when_no_limit_is_given():
    """A source fetch without a limit keeps the source budget."""
    network = ScriptedNetwork()
    body = b"x" * 2000
    network.serve("calendar.example.test", PUBLIC, always(*response(200, body)), port=443)

    with pytest.raises(FetchTooLargeError):
        adapter_for(network, max_bytes=1000).fetch(
            "https://calendar.example.test/feed.ics", allow_cross_host_redirect=True
        )


def test_a_gzip_bomb_is_refused():
    """A calendar feed compresses extremely well — which is exactly the shape of a bomb."""
    import gzip

    network = ScriptedNetwork()
    bomb = gzip.compress(b"x" * (2 * 1024 * 1024))
    network.serve(
        "calendar.example.test",
        PUBLIC,
        always(*response(200, bomb, headers={"Content-Encoding": "gzip"})),
        port=443,
    )

    with pytest.raises(FetchTooLargeError):
        adapter_for(network, max_bytes=64 * 1024).fetch(
            "https://calendar.example.test/feed.ics", allow_cross_host_redirect=True
        )


def test_a_redirect_loop_is_refused():
    network = ScriptedNetwork()
    network.serve(
        "calendar.example.test",
        PUBLIC,
        always(*redirect("https://calendar.example.test/feed.ics")),
        port=443,
    )

    with pytest.raises(Exception) as excinfo:
        adapter_for(network, max_redirects=3).fetch(
            "https://calendar.example.test/feed.ics", allow_cross_host_redirect=True
        )

    assert excinfo.value.reason == "too_many_redirects"


def test_a_dead_host_is_a_network_error():
    network = ScriptedNetwork()

    with pytest.raises(FetchNetworkError):
        adapter_for(network).fetch(
            "https://nowhere.example.test/feed.ics", allow_cross_host_redirect=True
        )


# ─── The credential never reaches the log ─────────────────────────────────────


def test_the_fetch_log_line_carries_no_url(caplog):
    """The crawl adapter's log line has ids and counts only — never a URL (AD-13)."""
    import logging

    network = ScriptedNetwork()
    network.serve("calendar.example.test", PUBLIC, always(*response(200, b"body")), port=443)

    with caplog.at_level(logging.DEBUG):
        adapter_for(network).fetch(
            "https://calendar.example.test/private-abc123/basic.ics",
            allow_cross_host_redirect=True,
        )

    assert "calendar.example.test" not in caplog.text
    assert "private-abc123" not in caplog.text
