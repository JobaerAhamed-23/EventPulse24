"""HTTP source fetches, hardened against SSRF and hostile responses (AD-9, AD-13).

httpx frames HTTP and follows redirects; this module owns everything else:

- Addresses: every TCP connection goes through `GuardedBackend.connect_tcp`, which resolves the
  host itself, refuses the host if any address is denied (`address_policy`), and connects only to
  an address it vetted. The check happens at connect time on every redirect hop, so DNS rebinding
  can't bypass it; TLS still verifies the original hostname (httpcore passes it as SNI).
- Ports: only `allowed_ports`, checked on the URL, on every hop, and again in `connect_tcp`.
- Redirects: same host only (a leading `www.` ignored); FR-17's ToS review covers one host.
  A caller may ask for cross-host redirects (`allow_cross_host_redirect`) — a calendar
  provider serves the feed from a CDN host. The relaxation is about the *host* only:
  the address policy still applies at connect time on every hop.
- Time: one `Deadline` covers DNS, connect, TLS, header bytes, body and every hop; each network
  operation gets min(its own timeout, the time remaining).
- Size: the body is read raw and decompressed here with an output budget, so neither a gzip
  bomb nor stacked encodings can exceed `max_bytes`.
- Logs: one record per fetch with ids and counts only; httpx/httpcore loggers stay at WARNING
  (settings.LOGGING) because they log URLs and hosts.

One `httpx.Client` per fetch, closed afterwards; no cookie is ever sent.
"""

import logging
import socket
import threading
import time
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
from uuid import UUID

import httpcore
import httpx
from django.conf import settings

from adapters.crawl.address_policy import is_denied
from ports.fetch import (
    NOT_MODIFIED,
    FetchBlockedError,
    FetchContentError,
    FetchError,
    FetchHTTPError,
    FetchNetworkError,
    FetchRedirectError,
    FetchResult,
    FetchTimeoutError,
    FetchTooLargeError,
    SourceFetchPort,
)
from ports.fetch import FetchLimits as _PortFetchLimits

logger = logging.getLogger(__name__)

SUCCESS_STATUSES = frozenset({200, 203})
DEFAULT_PORTS = {"http": 80, "https": 443}

Clock = Callable[[], float]
GetAddrInfo = Callable[..., list[tuple]]
AddressPolicy = Callable[[IPv4Address | IPv6Address], bool]


@dataclass(frozen=True)
class FetchLimits(_PortFetchLimits):
    """The source fetch's own limits, read from the deployment's settings.

    The *shape* lives in `ports.fetch`, so a caller whose content is a different shape
    (a calendar feed) can hand the adapter its own bounds. Only the *reading* of the
    settings is here, because `ports` never imports Django.
    """

    @classmethod
    def from_settings(cls) -> "FetchLimits":
        config = settings.SOURCE_FETCH
        return cls(
            user_agent=config["user_agent"],
            max_bytes=config["max_bytes"],
            dns_timeout=config["dns_timeout"],
            connect_timeout=config["connect_timeout"],
            read_timeout=config["read_timeout"],
            write_timeout=config["write_timeout"],
            total_timeout=config["total_timeout"],
            max_redirects=config["max_redirects"],
            allowed_ports=frozenset(config["allowed_ports"]),
        )


class Deadline:
    """The total time budget of one fetch."""

    def __init__(self, seconds: float, clock: Clock = time.monotonic) -> None:
        self._clock = clock
        self._end = clock() + seconds

    def budget(self, timeout: float | None) -> float:
        """min(timeout, remaining); raises once nothing remains."""
        remaining = self._end - self._clock()
        if remaining <= 0:
            raise FetchTimeoutError("deadline")
        return remaining if timeout is None else min(timeout, remaining)


class DeadlineStream(httpcore.NetworkStream):
    """Caps every read, write and TLS handshake by the fetch deadline."""

    def __init__(self, stream: httpcore.NetworkStream, deadline: Deadline) -> None:
        self._stream = stream
        self._deadline = deadline

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._stream.read(max_bytes, self._deadline.budget(timeout))

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._stream.write(buffer, self._deadline.budget(timeout))

    def close(self) -> None:
        self._stream.close()

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        stream = self._stream.start_tls(
            ssl_context, server_hostname, self._deadline.budget(timeout)
        )
        return DeadlineStream(stream, self._deadline)

    def get_extra_info(self, info: str):
        return self._stream.get_extra_info(info)


class GuardedBackend(httpcore.NetworkBackend):
    """Resolves, vets and connects. The only way this adapter opens a socket."""

    def __init__(
        self,
        limits: FetchLimits,
        deadline: Deadline,
        *,
        getaddrinfo: GetAddrInfo = socket.getaddrinfo,
        connector: httpcore.NetworkBackend | None = None,
        deny: AddressPolicy = is_denied,
    ) -> None:
        self._limits = limits
        self._deadline = deadline
        self._getaddrinfo = getaddrinfo
        self._connector = connector or httpcore.SyncBackend()
        self._deny = deny

    def _resolve(self, host: str, port: int) -> list[tuple]:
        """getaddrinfo with a timeout. It runs on a one-shot daemon thread that exits when the
        lookup returns, so no idle threads linger (they'd make a later fork() unsafe); only a
        lookup that hangs past its budget outlives the fetch.
        """
        outcome: dict[str, object] = {}

        def lookup() -> None:
            try:
                outcome["result"] = self._getaddrinfo(
                    host, port, 0, socket.SOCK_STREAM, socket.IPPROTO_TCP
                )
            except OSError as exc:  # socket.gaierror included
                outcome["error"] = exc

        thread = threading.Thread(target=lookup, name="fetch-dns", daemon=True)
        thread.start()
        thread.join(self._deadline.budget(self._limits.dns_timeout))
        if thread.is_alive():
            raise FetchTimeoutError("dns")
        if "error" in outcome:
            raise FetchNetworkError("dns") from outcome["error"]
        return outcome["result"]

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable | None = None,
    ) -> httpcore.NetworkStream:
        if port not in self._limits.allowed_ports:
            raise FetchBlockedError("port")
        literals: dict[str, IPv4Address | IPv6Address] = {}  # ordered, de-duplicated
        for family, _type, _proto, _name, sockaddr in self._resolve(host, port):
            address = ip_address(sockaddr[0].split("%", 1)[0])
            scope = sockaddr[3] if family == socket.AF_INET6 and len(sockaddr) > 3 else 0
            literals.setdefault(f"{address}%{scope}" if scope else str(address), address)
        if not literals:
            raise FetchNetworkError("dns_empty")
        if any(self._deny(address) for address in literals.values()):
            raise FetchBlockedError("address")

        last_error: Exception | None = None
        for literal in literals:
            try:
                stream = self._connector.connect_tcp(
                    literal,
                    port,
                    timeout=self._deadline.budget(timeout or self._limits.connect_timeout),
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout, OSError) as exc:
                last_error = exc
                continue
            return DeadlineStream(stream, self._deadline)
        if isinstance(last_error, httpcore.ConnectTimeout):
            raise FetchTimeoutError("connect") from last_error
        raise FetchNetworkError("connect") from last_error


class GuardedTransport(httpx.HTTPTransport):
    """httpx's transport with its connection pool rebuilt around a `GuardedBackend`.

    httpx 0.28 has no public way to pass a network backend; `_pool` is replaced instead.
    tests/adapters/test_crawl_http.py has a tripwire for an httpx upgrade that breaks this.
    """

    def __init__(self, backend: GuardedBackend) -> None:
        super().__init__(retries=0, trust_env=False)
        self._pool = httpcore.ConnectionPool(
            ssl_context=httpx.create_ssl_context(trust_env=False),
            max_connections=4,
            max_keepalive_connections=0,
            retries=0,
            network_backend=backend,
        )


# --- Content decoding ------------------------------------------------------------------------


class _Decoder:
    """Incremental zlib decoding that never produces more than the caller's budget + 1."""

    def __init__(self, wbits: int) -> None:
        self._wbits = wbits
        self._object = zlib.decompressobj(wbits)
        self._started = False

    def decode(self, data: bytes, limit: int) -> bytes:
        try:
            return self._decode(data, limit)
        except zlib.error:
            if self._wbits == zlib.MAX_WBITS and not self._started:  # deflate sent raw
                self._wbits = -zlib.MAX_WBITS
                self._object = zlib.decompressobj(self._wbits)
                return self.decode(data, limit)
            raise FetchContentError("corrupt") from None

    def _decode(self, data: bytes, limit: int) -> bytes:
        output = bytearray()
        pending = data
        while pending and len(output) <= limit:
            output += self._object.decompress(pending, limit + 1 - len(output))
            pending = self._object.unconsumed_tail
            self._started = True
        return bytes(output)

    def finish(self, limit: int) -> bytes:
        try:
            tail = self._object.flush(limit + 1)
        except zlib.error:
            raise FetchContentError("corrupt") from None
        if not self._object.eof:
            raise FetchContentError("truncated")
        return tail


def _decoder_for(content_encoding: str | None) -> _Decoder | None:
    codings = [c.strip().lower() for c in (content_encoding or "").split(",") if c.strip()]
    codings = [c for c in codings if c != "identity"]
    if not codings:
        return None
    if len(codings) > 1:
        raise FetchContentError("stacked_encoding")
    if codings[0] in ("gzip", "x-gzip"):
        return _Decoder(zlib.MAX_WBITS | 16)
    if codings[0] == "deflate":
        return _Decoder(zlib.MAX_WBITS)
    raise FetchContentError("unsupported_encoding")


# --- The adapter -----------------------------------------------------------------------------


def _same_host(a: str, b: str) -> bool:
    return a.lower().removeprefix("www.") == b.lower().removeprefix("www.")


def _as_fetch_error(exc: BaseException) -> FetchError:
    """Map anything raised during a fetch to a port error (httpcore may wrap ours)."""
    link: BaseException | None = exc
    visited: set[int] = set()
    while link is not None and id(link) not in visited:
        if isinstance(link, FetchError):
            return link
        visited.add(id(link))
        link = link.__cause__ or link.__context__
    if isinstance(exc, httpx.UnsupportedProtocol):
        return FetchBlockedError("scheme")
    if isinstance(exc, httpx.TimeoutException):
        return FetchTimeoutError(type(exc).__name__.lower())
    if isinstance(exc, httpx.TooManyRedirects):
        return FetchRedirectError("too_many_redirects")
    if isinstance(exc, httpx.DecodingError):
        return FetchContentError("decoding")
    if isinstance(exc, httpx.InvalidURL):
        return FetchBlockedError("invalid_url")
    return FetchNetworkError(type(exc).__name__.lower())


_MAPPED = (FetchError, httpx.HTTPError, httpx.InvalidURL, httpx.StreamError, OSError)


class HttpFetchAdapter(SourceFetchPort):
    def __init__(
        self,
        limits: FetchLimits | None = None,
        *,
        getaddrinfo: GetAddrInfo = socket.getaddrinfo,
        connector: httpcore.NetworkBackend | None = None,
        deny: AddressPolicy = is_denied,
        clock: Clock = time.monotonic,
    ) -> None:
        self._limits = limits or FetchLimits.from_settings()
        self._getaddrinfo = getaddrinfo
        self._connector = connector
        self._deny = deny
        self._clock = clock

    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        source_id: UUID | None = None,
        allow_cross_host_redirect: bool = False,
        limits: FetchLimits | None = None,
    ) -> FetchResult:
        started = time.monotonic()
        status, size, error_code = None, 0, None
        try:
            result = self._fetch(
                url, etag, last_modified, allow_cross_host_redirect, limits or self._limits
            )
            status, size = result.status, len(result.body)
            return result
        except _MAPPED as exc:
            error = _as_fetch_error(exc)
            error_code = error.code
            status = getattr(error, "status", None)
            if error is exc:
                raise
            raise error from exc
        finally:
            logger.info(
                "Source fetch",
                extra={
                    "job": "fetch",
                    "source_id": str(source_id) if source_id else None,
                    "status_code": status,
                    "byte_count": size,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "error_code": error_code,
                },
            )

    def _check_target(
        self,
        target: httpx.URL,
        origin_host: str | None = None,
        allow_cross_host_redirect: bool = False,
        limits: FetchLimits | None = None,
    ) -> None:
        bounds = limits or self._limits
        if target.scheme not in DEFAULT_PORTS:
            raise FetchBlockedError("scheme")
        if target.userinfo:
            raise FetchBlockedError("userinfo")
        if (target.port or DEFAULT_PORTS[target.scheme]) not in bounds.allowed_ports:
            raise FetchBlockedError("port")
        if (
            origin_host is not None
            and not allow_cross_host_redirect
            and not _same_host(target.host, origin_host)
        ):
            raise FetchBlockedError("cross_host_redirect")

    def _fetch(
        self,
        url: str,
        etag: str | None,
        last_modified: str | None,
        allow_cross_host_redirect: bool = False,
        limits: FetchLimits | None = None,
    ) -> FetchResult:
        bounds = limits or self._limits
        target = httpx.URL(url)
        self._check_target(target, limits=bounds)
        origin_host = target.host

        def check_hop(request: httpx.Request) -> None:
            self._check_target(request.url, origin_host, allow_cross_host_redirect, bounds)
            # No cookies, ever: a cookie-policy jar doesn't work here (httpx copies the jar into
            # a default-policy one), so drop the header on every hop before it's sent.
            request.headers.pop("Cookie", None)

        deadline = Deadline(bounds.total_timeout, self._clock)
        backend = GuardedBackend(
            bounds,
            deadline,
            getaddrinfo=self._getaddrinfo,
            connector=self._connector,
            deny=self._deny,
        )
        headers = {"User-Agent": bounds.user_agent, "Accept-Encoding": "gzip, deflate"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        with (
            httpx.Client(
                transport=GuardedTransport(backend),
                follow_redirects=True,
                max_redirects=bounds.max_redirects,
                trust_env=False,
                timeout=httpx.Timeout(
                    connect=bounds.connect_timeout,
                    read=bounds.read_timeout,
                    write=bounds.write_timeout,
                    pool=bounds.connect_timeout,
                ),
                event_hooks={"request": [check_hop]},
            ) as client,
            client.stream("GET", target, headers=headers) as response,
        ):
            final_url = str(response.url)
            content_type = response.headers.get("content-type")
            if response.status_code == NOT_MODIFIED:
                if not (etag or last_modified) or response.history:
                    raise FetchHTTPError(NOT_MODIFIED)
                return FetchResult(
                    status=NOT_MODIFIED,
                    final_url=final_url,
                    content_type=content_type,
                    etag=response.headers.get("etag") or etag,
                    last_modified=response.headers.get("last-modified") or last_modified,
                )
            if response.status_code not in SUCCESS_STATUSES:
                raise FetchHTTPError(response.status_code)
            body = self._read_body(response, bounds)
            return FetchResult(
                status=response.status_code,
                final_url=final_url,
                content_type=content_type,
                body=body,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
            )

    def _read_body(self, response: httpx.Response, limits: FetchLimits | None = None) -> bytes:
        limit = (limits or self._limits).max_bytes
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            raise FetchTooLargeError("content_length")
        decoder = _decoder_for(response.headers.get("content-encoding"))
        body = bytearray()
        raw_size = 0
        for chunk in response.iter_raw():
            raw_size += len(chunk)
            if raw_size > limit:
                raise FetchTooLargeError("raw_bytes")
            body += decoder.decode(chunk, limit - len(body)) if decoder else chunk
            if len(body) > limit:
                raise FetchTooLargeError("decoded_bytes")
        if decoder:
            body += decoder.finish(limit - len(body))
            if len(body) > limit:
                raise FetchTooLargeError("decoded_bytes")
        return bytes(body)
