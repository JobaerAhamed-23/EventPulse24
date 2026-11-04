"""Revalidation port (FR-26, FR-27): tell the frontend that a public page is stale.

The backend pushes a **cache instruction** to the frontend — "rebuild these paths" — and the
frontend rebuilds from the same public read it would use on a cold request. The signal
carries **no event data**: no title, no status, no time, no venue. It carries a list of paths
and a version number, so the direction of data flow is unchanged and AD-19 is untouched: the
frontend still holds no domain logic and still gets every fact through the generated client.

**Why this is a port and not `SourceFetchPort`.** Three reasons, each disqualifying on its
own:

1. **`SourceFetchPort` is GET-only.** `fetch` has no method, no body and no header parameter.
   Revalidation is a POST with a JSON body and a bearer token.
2. **The semantics are opposite.** `SourceFetchPort` retrieves *untrusted public content*
   from a *third party*, under a *source budget* (size, time, ports, redirects). Revalidation
   posts *our own secret* to *our own deploy*. Reusing that transport would put a credential
   on a path built for handling untrusted input — and its default `allowed_ports` is
   `{80, 443}`, which a self-hosted frontend on :3000 would fail.
3. **The `http-client` import contract forbids an app from importing `httpx` at all.** A port
   is the only way an app may reach an HTTP client, so a new port and a new adapter are the
   project's own answer to "the backend must make an outbound call".

Like every other port here, this is an ABC over frozen dataclasses and imports no Django.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum


class RevalidationOutcome(StrEnum):
    """What the frontend said, as the backend understands it.

    **The distinction that matters is retryable vs not.** A frontend that is down, slow or
    erroring will very likely be fine in five minutes, so the signal is retried. A frontend
    that answers *401* is telling us our secret is wrong, and retrying with the same wrong
    secret forever is noise — so that is permanent, and it is surfaced rather than retried.
    """

    DELIVERED = "delivered"  # the frontend acknowledged it
    UNAUTHORIZED = "unauthorized"  # the secret is wrong — permanent, never retried
    UNAVAILABLE = "unavailable"  # the frontend is down or erroring — retryable
    TIMEOUT = "timeout"  # the frontend did not answer in time — retryable
    NETWORK = "network"  # the frontend could not be reached — retryable
    BAD_STATUS = "bad_status"  # an unexpected status — retryable

    @property
    def is_retryable(self) -> bool:
        """Whether a delivery that failed this way is worth trying again."""
        return self is not RevalidationOutcome.UNAUTHORIZED

    @property
    def reason(self) -> str:
        """The slug recorded on the row. Never a URL, never a body (AD-13)."""
        return self.value


@dataclass(frozen=True)
class RevalidationResult:
    """One delivery attempt's outcome."""

    outcome: RevalidationOutcome
    #: The HTTP status the frontend answered with, when there was one.
    status: int | None = None


@dataclass(frozen=True)
class RevalidationRequest:
    """One signal: the paths to rebuild, and the version they must not be older than."""

    paths: tuple[str, ...] = field(default_factory=tuple)
    event_version: int = 1


class RevalidationPort(ABC):
    """Delivers a revalidation signal to the frontend deploy.

    Adapters implement `revalidate`. Implementations must not raise for an expected
    failure — a frontend that is down is an *outcome*, not an exception — and must not
    follow a redirect to a different host.
    """

    @abstractmethod
    def revalidate(self, request: RevalidationRequest) -> RevalidationResult:
        """Deliver one signal. Never raises for a failed delivery."""
        ...
