"""One end-to-end fetch over a real socket: the real resolver and httpcore's real connect loop.

The scripted network replaces the connector everywhere else. Here the address policy and the
port allowlist are overridden to admit this loopback listener (and nothing else changes).
"""

import gzip
import socket
import threading

import pytest

from adapters.crawl.address_policy import is_denied
from adapters.crawl.http import FetchLimits, HttpFetchAdapter
from ports.fetch import FetchBlockedError

BODY = b"<rss><channel><title>Loopback</title></channel></rss>"


@pytest.fixture
def listener():
    server = socket.create_server(("127.0.0.1", 0))
    port = server.getsockname()[1]
    seen = []

    def serve_one():
        connection, _ = server.accept()
        with connection:
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = connection.recv(4096)
                if not chunk:  # the teardown's wake-up connection
                    return
                request += chunk
            seen.append(request)
            payload = gzip.compress(BODY)
            connection.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nConnection: close\r\n"
                + f"Content-Length: {len(payload)}\r\n\r\n".encode()
                + payload
            )

    thread = threading.Thread(target=serve_one, daemon=True)
    thread.start()
    yield port, seen
    if thread.is_alive():  # closing a listener doesn't wake accept() on Linux; connecting does
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
    thread.join(timeout=5)
    server.close()


def test_real_socket_fetch_through_the_guard(listener):
    port, seen = listener
    adapter = HttpFetchAdapter(
        FetchLimits(user_agent="EventPulse24-Test/1.0", allowed_ports=frozenset({port})),
        deny=lambda address: False,  # admit loopback for this test only
    )

    result = adapter.fetch(f"http://127.0.0.1:{port}/feed")

    assert (result.status, result.body) == (200, BODY)
    assert b"user-agent: eventpulse24-test/1.0" in seen[0].lower()


def test_the_real_policy_refuses_the_same_listener(listener):
    port, seen = listener
    adapter = HttpFetchAdapter(
        FetchLimits(user_agent="EventPulse24-Test/1.0", allowed_ports=frozenset({port})),
        deny=is_denied,
    )

    with pytest.raises(FetchBlockedError):
        adapter.fetch(f"http://127.0.0.1:{port}/feed")

    assert seen == []
