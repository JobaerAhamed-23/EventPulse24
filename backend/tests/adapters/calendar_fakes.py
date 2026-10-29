"""A scripted fetch port for the calendar adapter's tests: no sockets, no network.

The adapter's own logic — the scheme rules, the status mapping, the parsing, the identity,
the credential's non-leakage — is exercised through this. The *fetch* itself is exercised
separately, against the real `HttpFetchAdapter` on the scripted network
(`tests/adapters/scripted_network.py`), so both halves are proven without a socket.

`ScriptedFetch` records what it was asked for, so a test can assert on the URL it was
given, the validators it sent, and whether it was allowed to cross hosts.
"""

from dataclasses import dataclass, field
from uuid import UUID

from ports.fetch import FetchLimits, FetchResult


@dataclass
class FetchCall:
    """One call to the fetch port: what was asked, and what was allowed."""

    url: str
    etag: str | None = None
    last_modified: str | None = None
    source_id: UUID | None = None
    allow_cross_host_redirect: bool = False
    limits: FetchLimits | None = None


@dataclass
class ScriptedFetch:
    """A fetch port that returns a fixed result, or raises a fixed error.

    `result` and `error` are mutually exclusive: an error, when given, is raised instead
    of the result. `calls` records every call, in order.
    """

    result: FetchResult | None = None
    error: Exception | None = None
    calls: list[FetchCall] = field(default_factory=list)

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
        self.calls.append(
            FetchCall(
                url=url,
                etag=etag,
                last_modified=last_modified,
                source_id=source_id,
                allow_cross_host_redirect=allow_cross_host_redirect,
                limits=limits,
            )
        )
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("ScriptedFetch was called with neither a result nor an error")
        return self.result


def ics_result(
    body: bytes,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    status: int = 200,
) -> FetchResult:
    """A 200 with an ICS body — the ordinary successful fetch."""
    return FetchResult(
        status=status,
        final_url="https://calendar.example.test/feed.ics",
        content_type="text/calendar",
        body=body,
        etag=etag,
        last_modified=last_modified,
    )
