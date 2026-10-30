"""Source fetch port (AD-9): retrieves public source content as untrusted bytes.

Adapters return bytes and metadata and never interpret them. Every failure is one of the
`FetchError` subclasses below; no library exception crosses the port. Error `details` carry only
a reason slug (and an HTTP status), never a host, IP or URL (AD-13).

Separate from `CalendarPort`, which handles credential-bearing personal ICS (AD-18).

**`allow_cross_host_redirect` is the one policy a caller may ask for.** It defaults to
`False`, so every source fetch keeps same-host-only redirects. See the note below for who
asks, and why the address policy is unaffected.

**`limits` is the second.** It defaults to `None` — the adapter's own configured limits —
so every source fetch keeps the source budget. A caller whose content is a different
shape (a calendar feed) passes its own `FetchLimits`; the size, time and port bounds are
then the caller's, and the *address policy* is still the adapter's.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import UUID

from domain.errors import DomainError

NOT_MODIFIED = 304


@dataclass(frozen=True)
class FetchLimits:
    """The bounds of one fetch: size, time and ports.

    This lives in the **port**, not in the adapter, because a caller may ask for its own
    limits: a calendar feed is a different shape from an RSS page, and the calendar
    adapter has its own named constants (a 5 MB decoded budget, a 5 s connect timeout).

    The dataclass is plain Python — `ports` never imports Django — so the adapter builds
    one from settings, and a caller builds one from its own constants.
    """

    user_agent: str
    max_bytes: int = 10 * 1024 * 1024
    dns_timeout: float = 3.0
    connect_timeout: float = 5.0
    read_timeout: float = 15.0
    write_timeout: float = 5.0
    total_timeout: float = 30.0
    max_redirects: int = 5
    allowed_ports: frozenset[int] = field(default_factory=lambda: frozenset({80, 443}))


@dataclass(frozen=True)
class FetchResult:
    status: int  # 200, 203, or 304
    final_url: str  # after same-host redirects
    content_type: str | None
    body: bytes = b""  # decoded; empty for a 304
    etag: str | None = None
    last_modified: str | None = None

    @property
    def not_modified(self) -> bool:
        return self.status == NOT_MODIFIED


class FetchError(DomainError):
    code = "fetch_failed"
    default_message = "We couldn't fetch that source."

    def __init__(self, reason: str, **details: int | str) -> None:
        super().__init__(details={"reason": reason, **details})
        self.reason = reason


class FetchTimeoutError(FetchError):
    code = "fetch_timeout"


class FetchTooLargeError(FetchError):
    code = "fetch_too_large"


class FetchBlockedError(FetchError):
    """We refused the target: scheme, port, userinfo, address, or a cross-host redirect.

    Every reason here is a **policy refusal** — our own decision, not the provider's.
    `POLICY_REFUSAL_REASONS` is that list, so a caller can tell "we would not go there"
    from "the fetch failed" without string-matching the reasons itself.
    """

    code = "fetch_blocked"

    #: The reasons this error is raised with — the transport's own vocabulary.
    POLICY_REFUSAL_REASONS = frozenset(
        {"scheme", "userinfo", "port", "address", "cross_host_redirect"}
    )

    @property
    def is_policy_refusal(self) -> bool:
        """Whether this refusal was ours — so a caller must not blame the provider."""
        return self.reason in self.POLICY_REFUSAL_REASONS


class FetchHTTPError(FetchError):
    code = "fetch_http_error"

    def __init__(self, status: int) -> None:
        super().__init__("http_status", status=status)
        self.status = status


class FetchRedirectError(FetchError):
    code = "fetch_too_many_redirects"


class FetchContentError(FetchError):
    """Unsupported, stacked or corrupt content encoding."""

    code = "fetch_bad_content"


class FetchNetworkError(FetchError):
    code = "fetch_network_error"


class SourceFetchPort(ABC):
    @abstractmethod
    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        source_id: UUID | None = None,
        allow_cross_host_redirect: bool = False,
        limits: FetchLimits | None = None,
        credential: bool = False,
    ) -> FetchResult: ...


# Why a caller may ask for the URL to be treated as a credential.
#
# **httpx logs the request URL.** At INFO it emits `HTTP Request: GET <full URL>
# "<status>"`, and for a calendar that URL *is* the credential (AD-18): the path
# carries the provider's token. The project's answer so far has been to pin the
# `httpx` and `httpcore` loggers to WARNING in `settings.LOGGING`, which works — but
# it is a *deployment-wide* answer to a *per-fetch* fact, and it silences those
# loggers for ordinary source fetches too, where the URL is an identifier worth
# keeping.
#
# The end-to-end proof found the gap. It lowered the `httpx` logger into its
# credential-leak sweep — deliberately, because that logger is the one most likely to
# carry the secret — and the sweep failed on the calendar's own request URL.
#
# So the fact is now carried where it belongs: **the caller that holds a credential
# says so**, and the transport stops the HTTP library from writing the URL. A source
# fetch does not ask, so its URL is still logged when the deployment wants it to be.
#
# This is an *addition* to the WARNING pin, not a replacement: the pin stays, because
# a transport that is handed a credential-bearing URL by a caller who forgot to say so
# must still not write it.


# Why a caller may ask for a cross-host redirect.
#
# A *source* fetch follows same-host redirects only: the URL was configured by an
# operator, and a redirect to another host is a surprise worth refusing.
#
# A *calendar* fetch is different, and the difference is the caller's, not the
# transport's. All three providers redirect the address the user pasted: Apple's
# `webcal://p01-calendars.icloud.com` answers 302 with an `icloud.com` CDN host, and
# Google's private ICS address answers 302 with `googleusercontent.com`. The address is
# the user's own credential and they are pointing it at a provider; the provider is
# entitled to move the file.
#
# **This relaxes the host, never the address.** The address policy still applies at
# connect time on every hop, so a redirect to `http://169.254.169.254/` is refused
# whatever host it came from.
