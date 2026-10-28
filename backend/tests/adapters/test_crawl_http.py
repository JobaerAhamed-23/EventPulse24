"""HttpFetchAdapter on the scripted network: real httpx/httpcore, no sockets, no DNS."""

import gzip
import logging
import ssl
import threading
import zlib

import httpx
import pytest

from adapters.crawl.http import GuardedBackend, GuardedTransport
from ports.fetch import (
    FetchBlockedError,
    FetchContentError,
    FetchError,
    FetchHTTPError,
    FetchNetworkError,
    FetchRedirectError,
    FetchTimeoutError,
    FetchTooLargeError,
)
from tests.adapters.scripted_network import Delay, ScriptedNetwork, always, response

HOST = "feeds.example.test"
URL = f"http://{HOST}/events.rss"
PUBLIC, PUBLIC_2, PRIVATE = "93.184.215.14", "1.1.1.1", "10.0.0.5"
RSS = b"<rss><channel><title>Events</title></channel></rss>"


@pytest.fixture
def net() -> ScriptedNetwork:
    return ScriptedNetwork()


def serve_ok(net, body=RSS, headers=None, host=HOST, ip=PUBLIC, port=80):
    net.serve(host, ip, always(*response(200, body, headers=headers)), port=port)


def redirect(location, status=302):
    return always(*response(status, headers={"Location": location}))


# --- Success and conditional requests --------------------------------------------------------


@pytest.mark.parametrize("status", [200, 203])
def test_success_returns_body_and_validators(net, status):
    validators = {"ETag": '"v7"', "Last-Modified": "Wed, 04 Nov 2026 10:00:00 GMT"}
    net.serve(
        HOST,
        PUBLIC,
        always(
            *response(status, RSS, headers={"Content-Type": "application/rss+xml", **validators})
        ),
    )

    result = net.adapter().fetch(URL)

    assert (result.status, result.body, result.content_type) == (status, RSS, "application/rss+xml")
    assert (result.etag, result.last_modified) == ('"v7"', "Wed, 04 Nov 2026 10:00:00 GMT")
    assert result.final_url == URL
    assert not result.not_modified


@pytest.mark.parametrize("status", [204, 206, 404, 500, 503])
def test_other_statuses_raise_http_error(net, status):
    net.serve(HOST, PUBLIC, always(*response(status)))

    with pytest.raises(FetchHTTPError) as excinfo:
        net.adapter().fetch(URL)

    assert excinfo.value.status == status
    assert excinfo.value.details == {"reason": "http_status", "status": status}


def test_missing_content_type_is_none(net):
    serve_ok(net)

    assert net.adapter().fetch(URL).content_type is None


def test_conditional_headers_and_identifying_user_agent_sent(net):
    serve_ok(net)

    net.adapter().fetch(URL, etag='"v7"', last_modified="Wed, 04 Nov 2026 10:00:00 GMT")

    sent = net.requests[0].headers
    assert sent["if-none-match"] == '"v7"'
    assert sent["if-modified-since"] == "Wed, 04 Nov 2026 10:00:00 GMT"
    assert sent["user-agent"] == "EventPulse24-Test/1.0"
    assert sent["accept-encoding"] == "gzip, deflate"


def test_304_with_validator_keeps_the_stored_etag_when_omitted(net):
    net.serve(HOST, PUBLIC, always(*response(304)))

    result = net.adapter().fetch(URL, etag='"v7"', last_modified="Wed, 04 Nov 2026 10:00:00 GMT")

    assert result.not_modified and result.body == b""
    assert (result.etag, result.last_modified) == ('"v7"', "Wed, 04 Nov 2026 10:00:00 GMT")


def test_304_without_a_validator_sent_is_refused(net):
    net.serve(HOST, PUBLIC, always(*response(304)))

    with pytest.raises(FetchHTTPError) as excinfo:
        net.adapter().fetch(URL)

    assert excinfo.value.status == 304


def test_304_after_a_redirect_is_refused(net):
    net.serve(
        HOST,
        PUBLIC,
        lambda request: (
            response(301, headers={"Location": "/moved.rss"})
            if request.target == "/events.rss"
            else response(304)
        ),
    )

    with pytest.raises(FetchHTTPError):
        net.adapter().fetch(URL, etag='"v7"')


# --- Content encoding and size ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("encoding", "compress"),
    [
        ("gzip", gzip.compress),
        ("x-gzip", gzip.compress),
        ("deflate", zlib.compress),  # zlib-wrapped
        ("deflate", lambda data: zlib.compress(data)[2:-4]),  # raw deflate, as some servers send
        ("identity", lambda data: data),
    ],
    ids=["gzip", "x-gzip", "deflate-zlib", "deflate-raw", "identity"],
)
def test_supported_encodings_are_decoded(net, encoding, compress):
    serve_ok(net, compress(RSS), headers={"Content-Encoding": encoding})

    assert net.adapter().fetch(URL).body == RSS


@pytest.mark.parametrize(
    "encoding", ["gzip, gzip", "gzip,deflate", "br", "zstd", "compress"], ids=str
)
def test_stacked_or_unsupported_encodings_are_refused(net, encoding):
    serve_ok(net, b"whatever", headers={"Content-Encoding": encoding})

    with pytest.raises(FetchContentError):
        net.adapter().fetch(URL)


@pytest.mark.parametrize(
    "body", [b"not gzip at all", gzip.compress(RSS)[:-10]], ids=["corrupt", "truncated"]
)
def test_corrupt_or_truncated_gzip_is_refused(net, body):
    serve_ok(net, body, headers={"Content-Encoding": "gzip"})

    with pytest.raises(FetchContentError):
        net.adapter().fetch(URL)


def test_gzip_bomb_stops_at_the_decoded_limit(net):
    bomb = gzip.compress(b"\0" * 5_000_000)  # ~5 KB on the wire, 5 MB decoded
    serve_ok(net, bomb, headers={"Content-Encoding": "gzip"})

    with pytest.raises(FetchTooLargeError) as excinfo:
        net.adapter(max_bytes=100_000).fetch(URL)

    assert excinfo.value.reason == "decoded_bytes"


def test_declared_content_length_over_the_limit_is_refused_before_reading(net):
    net.serve(HOST, PUBLIC, always(*response(200, headers={"Content-Length": "999999"}, parts=[])))

    with pytest.raises(FetchTooLargeError) as excinfo:
        net.adapter(max_bytes=1000).fetch(URL)

    assert excinfo.value.reason == "content_length"


def test_streamed_body_without_length_stops_at_the_limit(net):
    net.serve(HOST, PUBLIC, always(*response(200, parts=[b"x" * 600, b"x" * 600])))

    with pytest.raises(FetchTooLargeError):
        net.adapter(max_bytes=1000).fetch(URL)


def test_body_exactly_at_the_limit_is_accepted(net):
    serve_ok(net, b"x" * 1000)

    assert len(net.adapter(max_bytes=1000).fetch(URL).body) == 1000


# --- The deadline (injected clock) -----------------------------------------------------------


def test_deadline_covers_slow_dns(net):
    def slow_lookup():
        net.clock.advance(31)
        return [(2, 1, 6, "", (PUBLIC, 80))]

    net.dns[HOST] = slow_lookup
    net.servers[(PUBLIC, 80)] = always(*response(200, RSS))

    with pytest.raises(FetchTimeoutError):
        net.adapter().fetch(URL)

    assert net.connects == []  # the deadline was spent before connecting


def test_dns_lookup_that_hangs_times_out(net):
    released = threading.Event()
    net.dns[HOST] = lambda: released.wait(5) and []

    try:
        with pytest.raises(FetchTimeoutError) as excinfo:
            net.adapter(dns_timeout=0.05).fetch(URL)
    finally:
        released.set()

    assert excinfo.value.reason == "dns"


def test_deadline_covers_slow_connects_across_several_addresses(net):
    net.dns[HOST] = [PUBLIC, PUBLIC_2]
    net.connect_delays = {PUBLIC: 20, PUBLIC_2: 20}  # each under the 30 s connect timeout
    net.servers[(PUBLIC_2, 80)] = always(*response(200, RSS))

    with pytest.raises(FetchTimeoutError):
        net.adapter(connect_timeout=30).fetch(URL)

    assert net.connects[1][2] == pytest.approx(10)  # the second attempt got only what remained


def test_deadline_covers_the_tls_handshake(net):
    serve_ok(net, port=443)
    net.tls_delay = 40

    with pytest.raises(FetchTimeoutError):
        net.adapter().fetch(f"https://{HOST}/events.rss")


def test_deadline_covers_headers_sent_a_byte_at_a_time(net):
    head = response(200, RSS)[0]
    drip = [part for byte in head for part in (Delay(1), bytes([byte]))]
    net.serve(HOST, PUBLIC, always(*drip, RSS))

    with pytest.raises(FetchTimeoutError):
        net.adapter().fetch(URL)  # each byte is under the read timeout; the total isn't


def test_read_timeout_on_a_stalled_body(net):
    net.serve(HOST, PUBLIC, always(*response(200, parts=[b"x", Delay(20)])))

    with pytest.raises(FetchTimeoutError):
        net.adapter().fetch(URL)


def test_deadline_covers_every_redirect_hop(net):
    # Three hops of 12 s each: every read is under the 15 s read timeout, the sum isn't.
    hops = {"/events.rss": "/2", "/2": "/3", "/3": "/4"}
    net.serve(
        HOST,
        PUBLIC,
        lambda request: [Delay(12), *response(302, headers={"Location": hops[request.target]})],
    )

    with pytest.raises(FetchTimeoutError):
        net.adapter().fetch(URL)

    assert len(net.requests) == 3


# --- Guard, ports and redirects --------------------------------------------------------------


def test_redirect_from_public_to_private_host_is_refused(net):
    net.serve(HOST, PUBLIC, redirect(f"http://{HOST}/internal"))
    net.dns["internal.example.test"] = [PRIVATE]
    net.serve(HOST, PUBLIC, redirect("http://internal.example.test/admin"))

    with pytest.raises(FetchBlockedError) as excinfo:
        net.adapter().fetch(URL)

    assert excinfo.value.reason == "cross_host_redirect"
    assert all(host != PRIVATE for host, _, _ in net.connects)


def test_same_host_resolving_to_a_private_address_on_a_later_hop_is_refused(net):
    # DNS rebinding: the first lookup is public, the second (next hop) private.
    answers = iter([[PUBLIC], [PRIVATE]])
    net.dns[HOST] = lambda: [(2, 1, 6, "", (ip, 80)) for ip in next(answers)]
    net.servers[(PUBLIC, 80)] = redirect("/next")

    with pytest.raises(FetchBlockedError) as excinfo:
        net.adapter().fetch(URL)

    assert excinfo.value.reason == "address"
    assert [host for host, _, _ in net.connects] == [PUBLIC]


@pytest.mark.parametrize(
    "location", ["http://other.example.test/feed", "https://cdn.example.net/x"]
)
def test_cross_host_redirect_is_refused(net, location):
    net.serve(HOST, PUBLIC, redirect(location))

    with pytest.raises(FetchBlockedError) as excinfo:
        net.adapter().fetch(URL)

    assert excinfo.value.reason == "cross_host_redirect"


def test_same_host_redirects_including_to_https_and_www_are_followed(net):
    net.serve(HOST, PUBLIC, redirect(f"https://www.{HOST}/events.rss", status=301))
    net.serve(f"www.{HOST}", PUBLIC, always(*response(200, RSS)), port=443)

    result = net.adapter().fetch(URL)

    assert result.body == RSS
    assert result.final_url == f"https://www.{HOST}/events.rss"


def test_redirect_to_a_disallowed_port_is_refused(net):
    net.serve(HOST, PUBLIC, redirect(f"http://{HOST}:6379/"))

    with pytest.raises(FetchBlockedError) as excinfo:
        net.adapter().fetch(URL)

    assert excinfo.value.reason == "port"


def test_port_is_rechecked_inside_connect(net):
    # Belt and braces: even if a hop slipped past the URL check, connect_tcp refuses the port.
    from adapters.crawl.http import Deadline, FetchLimits

    backend = GuardedBackend(
        FetchLimits(user_agent="t"), Deadline(30, net.clock), getaddrinfo=net.getaddrinfo
    )

    with pytest.raises(FetchBlockedError) as excinfo:
        backend.connect_tcp(HOST, 6379)

    assert excinfo.value.reason == "port"


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        (f"http://{PUBLIC}:6379/", "port"),
        (f"http://{HOST}:5432/", "port"),
        (f"ftp://{HOST}/feed", "scheme"),
        ("file:///etc/passwd", "scheme"),
        (f"http://user:secret@{HOST}/feed", "userinfo"),
        ("http://[::1", "invalid_url"),
    ],
)
def test_unacceptable_urls_are_refused_before_connecting(net, url, reason):
    with pytest.raises(FetchBlockedError) as excinfo:
        net.adapter().fetch(url)

    assert excinfo.value.reason == reason
    assert net.connects == []


def test_redirect_to_another_scheme_is_refused(net):
    net.serve(HOST, PUBLIC, redirect(f"ftp://{HOST}/feed"))

    with pytest.raises(FetchBlockedError) as excinfo:
        net.adapter().fetch(URL)

    assert excinfo.value.reason == "scheme"


def test_too_many_redirects(net):
    net.serve(
        HOST, PUBLIC, lambda request: response(302, headers={"Location": request.target + "x"})
    )

    with pytest.raises(FetchRedirectError):
        net.adapter(max_redirects=5).fetch(URL)

    assert len(net.requests) == 6


@pytest.mark.parametrize(
    "addresses", [[PUBLIC, PRIVATE], [PRIVATE, PUBLIC], ["::ffff:127.0.0.1"]], ids=str
)
def test_host_with_any_denied_address_is_refused_without_connecting(net, addresses):
    net.dns[HOST] = addresses
    net.servers[(PUBLIC, 80)] = always(*response(200, RSS))

    with pytest.raises(FetchBlockedError) as excinfo:
        net.adapter().fetch(URL)

    assert excinfo.value.reason == "address"
    assert net.connects == []


def test_unknown_host_is_a_network_error(net):
    with pytest.raises(FetchNetworkError) as excinfo:
        net.adapter().fetch(URL)

    assert excinfo.value.reason == "dns"


def test_empty_resolution_is_a_network_error(net):
    net.dns[HOST] = list

    with pytest.raises(FetchNetworkError) as excinfo:
        net.adapter().fetch(URL)

    assert excinfo.value.reason == "dns_empty"


def test_duplicate_addresses_are_tried_once_and_refusal_is_a_network_error(net):
    net.dns[HOST] = [PUBLIC, PUBLIC]  # no server: connection refused

    with pytest.raises(FetchNetworkError) as excinfo:
        net.adapter().fetch(URL)

    assert excinfo.value.reason == "connect"
    assert [host for host, _, _ in net.connects] == [PUBLIC]


def test_falls_back_to_the_next_address_when_one_refuses(net):
    net.dns[HOST] = [PUBLIC, PUBLIC_2]
    net.servers[(PUBLIC_2, 80)] = always(*response(200, RSS))

    assert net.adapter().fetch(URL).body == RSS
    assert [host for host, _, _ in net.connects] == [PUBLIC, PUBLIC_2]


# --- TLS, proxies, cookies, lifecycle --------------------------------------------------------


def test_tls_verifies_the_origin_hostname_not_the_pinned_ip(net):
    serve_ok(net, port=443)

    net.adapter().fetch(f"https://{HOST}/events.rss")

    [tls] = net.tls
    assert tls["server_hostname"] == HOST
    assert tls["ssl_context"].verify_mode == ssl.CERT_REQUIRED
    assert tls["ssl_context"].check_hostname is True
    assert net.connects[0][0] == PUBLIC


def test_proxy_environment_never_bypasses_the_guard(net, monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(name, "http://203.0.113.66:3128")
    net.dns[HOST] = [PRIVATE]

    with pytest.raises(FetchBlockedError):
        net.adapter().fetch(URL)

    assert all(host != "203.0.113.66" for host, _, _ in net.connects)


def test_cookies_are_never_sent_back(net):
    net.serve(
        HOST,
        PUBLIC,
        lambda request: (
            response(302, headers={"Location": "/next", "Set-Cookie": "session=abc; Path=/"})
            if request.target == "/events.rss"
            else response(200, RSS)
        ),
    )

    net.adapter().fetch(URL)

    assert "cookie" not in net.requests[1].headers


def test_connections_are_closed_after_each_fetch(net):
    serve_ok(net)

    net.adapter().fetch(URL)

    assert net.closed >= 1


def test_transport_pool_uses_the_guarded_backend():
    # Tripwire: httpx 0.28 has no public hook; an upgrade that renames `_pool` must fail here.
    from adapters.crawl.http import Deadline, FetchLimits

    backend = GuardedBackend(FetchLimits(user_agent="t"), Deadline(30))
    transport = GuardedTransport(backend)

    assert transport._pool._network_backend is backend


# --- Errors and logs -------------------------------------------------------------------------


def test_every_error_detail_is_free_of_hosts_and_urls(net):
    net.serve(HOST, PUBLIC, redirect("http://other.example.test/x"))

    with pytest.raises(FetchError) as excinfo:
        net.adapter().fetch(URL)

    rendered = repr(excinfo.value.details) + str(excinfo.value)
    assert "example" not in rendered and PUBLIC not in rendered


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (httpx.ReadTimeout("t"), FetchTimeoutError),
        (httpx.ConnectTimeout("t"), FetchTimeoutError),
        (httpx.TooManyRedirects("r"), FetchRedirectError),
        (httpx.DecodingError("d"), FetchContentError),
        (httpx.InvalidURL("u"), FetchBlockedError),
        (httpx.UnsupportedProtocol("p"), FetchBlockedError),
        (httpx.RemoteProtocolError("p"), FetchNetworkError),
        (httpx.ReadError("r"), FetchNetworkError),
        (httpx.StreamConsumed(), FetchNetworkError),
        (OSError("o"), FetchNetworkError),
    ],
    ids=lambda value: type(value).__name__,
)
def test_library_exceptions_map_to_port_errors(net, monkeypatch, raised, expected):
    serve_ok(net)

    def explode(*args, **kwargs):
        raise raised

    monkeypatch.setattr(httpx.Client, "stream", explode)

    with pytest.raises(expected):
        net.adapter().fetch(URL)


def test_port_error_raised_inside_httpcore_is_unwrapped(net):
    wrapped = httpx.ConnectError("wrapper")
    wrapped.__cause__ = FetchBlockedError("address")

    from adapters.crawl.http import _as_fetch_error

    assert isinstance(_as_fetch_error(wrapped), FetchBlockedError)


def test_logs_carry_ids_and_counts_but_never_a_url_host_or_ip(net, caplog):
    net.serve(
        HOST,
        PUBLIC,
        lambda request: (
            response(302, headers={"Location": "/moved?token=abc"})
            if request.target == "/events.rss"
            else response(200, RSS)
        ),
    )
    caplog.set_level(logging.DEBUG)

    net.adapter().fetch(URL)

    for record in caplog.records:
        rendered = f"{record.getMessage()} {record.args!r} {vars(record)!r}"
        assert HOST not in rendered and PUBLIC not in rendered and "token" not in rendered
    [ours] = [r for r in caplog.records if r.name == "adapters.crawl.http"]
    assert (ours.job, ours.status_code, ours.byte_count) == ("fetch", 200, len(RSS))
