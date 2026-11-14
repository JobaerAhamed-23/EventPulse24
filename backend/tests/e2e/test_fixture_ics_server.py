"""The fixture ICS server behaves, over a real TLS socket, through the real fetch adapter.

The server is a tool for the end-to-end proof, so it needs its own proof: a server that
silently answers 200 when asked for 410 would make the revocation step of the scenario
prove nothing.

**Why this goes through `HttpFetchAdapter` and not `httpx` directly.** The proof's whole
point is that the *real* fetch path is exercised — the SSRF guard, the connect-time
address check, the conditional headers, the status mapping. A test that used a plain
`httpx.get` would prove the server works while the proof it serves proves something
else. So this test drives the server through the same adapter the scenario will use.
"""

import pytest

from adapters.crawl.http import FetchLimits, HttpFetchAdapter
from ports.fetch import FetchHTTPError
from tests.fixture_ics_server import (
    ETAG,
    FIXTURE_ICS,
    LAST_MODIFIED,
    STATUS_GONE,
    STATUS_NOT_MODIFIED,
    STATUS_OK,
    FixtureIcsServer,
    fixture_today,
    rebased_ics,
)


@pytest.fixture
def server():
    with FixtureIcsServer() as running:
        yield running


@pytest.fixture
def adapter(server):
    """A fetch adapter that trusts the fixture's certificate and admits its port.

    Both overrides are the ones the proof uses, and both are *additions* rather than
    relaxations: the certificate is added to httpx's own trust store (verification stays
    on), and the port is added to the allowlist.

    The address policy is **not** overridden here. The loopback is admitted by the
    test-only allowance — the explicit `allow_loopback_fetch()` block, which is refused
    outside the test settings — and by nothing else. That is the whole point of the
    allowance: the proof reaches the fixture server through the sanctioned seam, and
    every other test in the suite keeps the real deny table.

    **The block spans the whole test, not just construction.** The adapter resolves its
    policy once, in `__init__`, so the adapter and every fetch it makes have to happen
    inside the allowance. Holding it open for the test's duration is what makes that
    true by construction rather than by remembering to re-enter it at each call.
    """
    from ports.fetch_policy import allow_loopback_fetch, fetch_deny_policy

    with allow_loopback_fetch():
        adapter = HttpFetchAdapter(
            FetchLimits(
                user_agent="EventPulse24-Test/1.0",
                allowed_ports=frozenset({server.port}),
            ),
            deny=fetch_deny_policy(),
            ssl_context=server.ssl_context(),
        )
        yield adapter


def test_the_server_serves_the_fixture_feed(adapter, server):
    """The fixture's contents, **rebased onto the running week**.

    The file's dates are fixed; `rebased_ics` shifts the events by whole weeks so they
    always sit inside the import window. The server serves that, so this compares against
    the same transformation rather than against the bytes on disk.
    """
    result = adapter.fetch(server.url("/feed.ics"))

    assert result.status == STATUS_OK
    assert result.body == rebased_ics(FIXTURE_ICS.read_bytes(), today=fixture_today())
    assert result.etag == ETAG
    assert result.last_modified == LAST_MODIFIED


def test_the_served_feed_keeps_the_fixture_untouched_on_disk():
    """Rebasing happens on the way out; the fixture file is never rewritten."""
    assert b"20261112T180000" in FIXTURE_ICS.read_bytes()


def test_the_server_records_what_it_was_asked_for(adapter, server):
    adapter.fetch(server.url("/feed.ics"))

    assert len(server.requests) == 1
    request = server.requests[0]
    assert request.method == "GET"
    assert request.path == "/feed.ics"
    assert request.user_agent == "EventPulse24-Test/1.0"
    assert request.cookie is None, "no cookie is ever sent (AD-13)"
    assert request.is_conditional is False


def test_the_server_answers_304_and_the_validator_travels(adapter, server):
    """A conditional request is answered 304, and the validator went out."""
    server.serve_not_modified()

    result = adapter.fetch(server.url("/feed.ics"), etag=ETAG, last_modified=LAST_MODIFIED)

    assert result.status == STATUS_NOT_MODIFIED
    assert result.body == b""
    assert result.etag == ETAG
    assert result.last_modified == LAST_MODIFIED

    request = server.requests[0]
    assert request.if_none_match == ETAG
    assert request.if_modified_since == LAST_MODIFIED
    assert request.is_conditional is True


def test_the_server_answers_410(adapter, server):
    """The revocation: a 410, and the adapter maps it to a status error."""
    server.serve_gone()

    with pytest.raises(FetchHTTPError) as excinfo:
        adapter.fetch(server.url("/feed.ics"))

    assert excinfo.value.status == STATUS_GONE


def test_the_switch_changes_only_what_it_should(adapter, server):
    """200 → 304 → 410, in one run, on the same server.

    This is the shape the scenario walks, so it is worth proving the switch is
    immediate and the server does not need restarting.

    The 304 carries the validator, because the adapter treats a 304 without one as an
    error — a provider answering "not modified" to a request that never said what it
    had is not a not-modified answer.
    """
    assert adapter.fetch(server.url("/feed.ics")).status == STATUS_OK

    server.serve_not_modified()
    assert adapter.fetch(server.url("/feed.ics"), etag=ETAG).status == STATUS_NOT_MODIFIED

    server.serve_gone()
    with pytest.raises(FetchHTTPError):
        adapter.fetch(server.url("/feed.ics"))

    assert [request.path for request in server.requests] == ["/feed.ics"] * 3


def test_the_reset_forgets_the_recorded_requests(adapter, server):
    adapter.fetch(server.url("/feed.ics"))
    assert len(server.requests) == 1

    server.reset()
    assert server.requests == []
    assert server.status == STATUS_OK


def test_the_server_binds_an_ephemeral_loopback_port(server):
    """The port is real, on loopback, and not a guess."""
    assert server.port > 0
    assert server.url("/feed.ics").startswith(f"https://127.0.0.1:{server.port}/")


def test_the_client_still_verifies_the_certificate(server):
    """Trusting the fixture is an *addition*; verification is not switched off.

    A client that does not trust the fixture's certificate must be refused — which
    proves the proof's client is verifying, and not merely talking to whatever answers.
    """
    import httpx

    with httpx.Client(trust_env=False) as client:
        with pytest.raises(httpx.ConnectError):
            client.get(server.url("/feed.ics"))


def test_the_certificate_covers_the_ip_address(server):
    """The certificate names `127.0.0.1` as an IP, not as a DNS name.

    The proof connects to an IP literal, and a certificate carrying only a hostname
    would fail the hostname check — so the SAN has to be an IP address.
    """
    from cryptography import x509

    certificate = x509.load_pem_x509_certificate(server.certificate_path.read_bytes())
    sans = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    addresses = sans.value.get_values_for_type(x509.IPAddress)
    assert [str(address) for address in addresses] == ["127.0.0.1"]
