"""Calendar port (AD-18): read-only ICS/webcal import; every provider credential is a credential.

**Three outcomes, not one.** A calendar credential can be *revoked* (the provider says
it is no longer valid — the user must reconnect), *transient* (the provider had a bad
afternoon — the connection is fine), or *refused* (**we** declined to fetch: a blocked
address, a blocked scheme, an oversized body). Only the first marks a connection
revoked, so a transient failure never asks the user to reconnect a calendar that works.

The distinction is the point of the typed errors: a caller that catches
`CalendarRevokedError` knows the user must be prompted; a caller that catches
`CalendarTransientError` knows it must try again later; a caller that catches
`CalendarRefusedError` knows the address itself was the problem.

**A 304 is a success, not a failure.** The feed has not changed and the caller keeps
what it has, so `not_modified` is a flag on the result rather than an exception — the
same convention `ports.fetch.FetchResult` uses.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from domain.errors import DomainError


class CalendarError(DomainError):
    """Base for every calendar failure.

    Never carries the URL, the host, or the path: the secret ICS URL *is* the
    credential (AD-18), and an exception message ends up in logs and traces (AD-13).
    """

    code = "calendar_failed"
    default_message = "We couldn't read that calendar."


class CalendarRevokedError(CalendarError):
    """The provider says the credential is no longer valid. The user must reconnect."""

    code = "calendar_revoked"
    default_message = "That calendar's access was revoked. Please reconnect it."


class CalendarTransientError(CalendarError):
    """A temporary failure: 5xx, a timeout, a network error, a malformed response.

    A transient failure must never mark a connection revoked — the provider may simply
    have had a bad afternoon, and asking the user to reconnect a working calendar is
    worse than trying again.
    """

    code = "calendar_transient"
    default_message = "That calendar didn't respond. We'll try again."


class CalendarRefusedError(CalendarError):
    """We refused to fetch: a blocked scheme, a blocked address, an oversized body.

    This is *our* refusal, not the provider's — so it must never mark a calendar
    revoked. A user pointing their calendar at a private address has a problem with
    the address, not with their access.
    """

    code = "calendar_refused"
    default_message = "That calendar address wasn't allowed."


class Credential:
    """A secret (e.g. a secret ICS URL). Its value never appears in `repr`, `str` or logs."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Credential('[redacted]')"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Credential) and other._value == self._value

    def __hash__(self) -> int:
        return hash(self._value)


@dataclass(frozen=True)
class CalendarFeed:
    """What to fetch, and the validators from the last fetch.

    `etag` and `last_modified` are the provider's opaque cache validators. They are
    sent back as conditional headers, so an unchanged feed costs one 304 instead of a
    full download. They are not secrets, but they are per-connection state and never
    reach a log line.
    """

    url: Credential
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True)
class CalendarEntry:
    uid: str
    title: str = field(repr=False)  # personal event content (AD-13)
    starts_at: datetime  # aware, UTC (AD-6)
    ends_at: datetime
    tz: str  # IANA name the entry was authored in


@dataclass(frozen=True)
class CalendarResult:
    """What one fetch produced.

    `not_modified` is True when the provider answered 304: `entries` is empty and the
    caller keeps what it already has. The validators are the *new* ones, to be stored
    for the next fetch.
    """

    entries: list[CalendarEntry] = field(default_factory=list)
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


class CalendarPort(ABC):
    @abstractmethod
    def fetch_entries(self, feed: CalendarFeed) -> CalendarResult: ...
