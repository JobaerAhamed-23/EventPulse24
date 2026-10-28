"""An in-memory network for HttpFetchAdapter tests: no sockets, no DNS, a controllable clock.

It replaces only the two things the adapter injects: `getaddrinfo` and the TCP connector under
`GuardedBackend`. Everything above them runs for real: httpx redirects and timeouts, httpcore's
HTTP/1.1 framing (h11), the guard, the deadline and the decoder. Streams record what they're
asked to do (TLS arguments, closes), and `Delay` items advance the fake clock, raising httpcore's
timeouts exactly as a real socket would when a delay exceeds the operation's timeout.
"""

import socket
from collections.abc import Callable
from dataclasses import dataclass, field

import httpcore

from adapters.crawl.http import FetchLimits, HttpFetchAdapter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class Delay:
    seconds: float


@dataclass(frozen=True)
class Request:
    method: str
    target: str
    headers: dict[str, str]  # lowercased names


Responder = Callable[[Request], list]


def response(
    status: int,
    body: bytes = b"",
    *,
    headers: dict[str, str] | None = None,
    parts: list | None = None,
) -> list:
    """Raw HTTP/1.1 response items. `parts` streams the body (bytes and Delays) until close."""
    all_headers = {"Connection": "close", **(headers or {})}
    if parts is None:
        all_headers.setdefault("Content-Length", str(len(body)))
        parts = [body] if body else []
    head = f"HTTP/1.1 {status} X\r\n" + "".join(f"{k}: {v}\r\n" for k, v in all_headers.items())
    return [(head + "\r\n").encode(), *parts]


def always(*items) -> Responder:
    return lambda request: list(items)


def _parse(raw: bytes) -> Request:
    head = raw.split(b"\r\n\r\n", 1)[0].decode("latin-1").split("\r\n")
    method, target, _version = head[0].split(" ", 2)
    headers = {}
    for line in head[1:]:
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return Request(method, target, headers)


class ScriptedStream(httpcore.NetworkStream):
    def __init__(self, network: "ScriptedNetwork", responder: Responder) -> None:
        self._network = network
        self._responder = responder
        self._sent = b""
        self._pending: list | None = None

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._sent += buffer

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if self._pending is None:
            request = _parse(self._sent)
            self._network.requests.append(request)
            self._pending = list(self._responder(request))
        while self._pending:
            item = self._pending[0]
            if isinstance(item, Delay):
                if timeout is not None and item.seconds > timeout:
                    self._network.clock.advance(timeout)
                    item.seconds -= timeout
                    raise httpcore.ReadTimeout("scripted read timeout")
                self._network.clock.advance(item.seconds)
                self._pending.pop(0)
                continue
            data, rest = item[:max_bytes], item[max_bytes:]
            if rest:
                self._pending[0] = rest
            else:
                self._pending.pop(0)
            return data
        return b""

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self._network.tls.append({"ssl_context": ssl_context, "server_hostname": server_hostname})
        if self._network.tls_delay > (timeout if timeout is not None else float("inf")):
            self._network.clock.advance(timeout)
            raise httpcore.ConnectTimeout("scripted TLS timeout")
        self._network.clock.advance(self._network.tls_delay)
        return self

    def close(self) -> None:
        self._network.closed += 1

    def get_extra_info(self, info: str):
        return None


class ScriptedConnector(httpcore.NetworkBackend):
    def __init__(self, network: "ScriptedNetwork") -> None:
        self._network = network

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self._network.connects.append((host, port, timeout))
        delay = self._network.connect_delays.get(host, 0.0)
        if timeout is not None and delay > timeout:
            self._network.clock.advance(timeout)
            raise httpcore.ConnectTimeout("scripted connect timeout")
        self._network.clock.advance(delay)
        responder = self._network.servers.get((host, port))
        if responder is None:
            raise httpcore.ConnectError("scripted connection refused")
        return ScriptedStream(self._network, responder)


@dataclass
class ScriptedNetwork:
    """DNS records, servers per (ip, port), and a record of what the adapter did."""

    dns: dict[str, list[str] | Callable[[], list[tuple]]] = field(default_factory=dict)
    servers: dict[tuple[str, int], Responder] = field(default_factory=dict)
    connect_delays: dict[str, float] = field(default_factory=dict)
    tls_delay: float = 0.0
    clock: FakeClock = field(default_factory=FakeClock)
    connects: list[tuple] = field(default_factory=list)
    requests: list[Request] = field(default_factory=list)
    tls: list[dict] = field(default_factory=list)
    closed: int = 0

    def serve(self, host: str, ip: str, responder: Responder, port: int = 80) -> None:
        self.dns.setdefault(host, [])
        if isinstance(self.dns[host], list) and ip not in self.dns[host]:
            self.dns[host].append(ip)
        self.servers[(ip, port)] = responder

    def getaddrinfo(self, host, port, family=0, type=0, proto=0, flags=0):
        entry = self.dns.get(host)
        if entry is None:
            raise socket.gaierror(socket.EAI_NONAME, "scripted: no such host")
        if callable(entry):
            return entry()
        return [
            (
                socket.AF_INET6 if ":" in ip else socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (ip, port, 0, 0) if ":" in ip else (ip, port),
            )
            for ip in entry
        ]

    def adapter(self, **limits) -> HttpFetchAdapter:
        return HttpFetchAdapter(
            FetchLimits(user_agent="EventPulse24-Test/1.0", **limits),
            getaddrinfo=self.getaddrinfo,
            connector=ScriptedConnector(self),
            clock=self.clock,
        )
