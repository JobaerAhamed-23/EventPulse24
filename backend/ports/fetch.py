"""Source fetch port (AD-9): retrieves public source content as untrusted bytes.

Adapters return bytes and metadata and never interpret them. Every failure is one of the
`FetchError` subclasses below; no library exception crosses the port. Error `details` carry only
a reason slug (and an HTTP status), never a host, IP or URL (AD-13).

Separate from `CalendarPort`, which handles credential-bearing personal ICS (AD-18).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from domain.errors import DomainError

NOT_MODIFIED = 304


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
    """We refused the target: scheme, port, userinfo, address, or a cross-host redirect."""

    code = "fetch_blocked"


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
    ) -> FetchResult: ...
