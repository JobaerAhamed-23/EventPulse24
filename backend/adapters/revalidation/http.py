"""HTTP revalidation adapter: POSTs a cache instruction to the frontend (FR-26, FR-27).

This is the **second** module in the project allowed to import `httpx` — the first is
`adapters.crawl.http`, which fetches third-party sources. The `http-client` import contract
names this adapter explicitly, so the widening of that contract is a deliberate, visible edit
rather than something that happened.

**What is different from a source fetch, and why it matters:**

- **The URL comes from configuration, never from a request.** A source fetch's URL comes from
  an operator-configured source; this one's comes from `settings.FRONTEND_REVALIDATION_URL`.
  There is no path in which a caller can choose the host, so there is no SSRF surface here at
  all — and no address policy is needed, because the host is ours and was named by us.
- **Redirects are not followed.** A 301 to another host would carry the bearer token with
  it. The adapter refuses to follow a redirect, full stop.
- **The body is ours and the response is not read.** A 2xx is a delivery; anything else is an
  outcome. The response body is never read, never logged and never stored — it could contain
  anything, and the row records a reason slug only (AD-13).
- **The secret never appears in a log line.** httpx logs the request URL at INFO; the URL
  here is ours and carries no secret, but the *header* does, and httpx does not log headers.
  The adapter logs the outcome and the status, never the request.

**Every failure is an outcome, never an exception.** A frontend that is down is the normal
condition this signal is designed to survive, so it must not become an exception that
escapes into the worker.
"""

import logging

import httpx
from django.conf import settings

from ports.revalidation import (
    RevalidationOutcome,
    RevalidationPort,
    RevalidationRequest,
    RevalidationResult,
)

logger = logging.getLogger(__name__)

#: The statuses that mean "the frontend took the signal".
DELIVERED_STATUSES = frozenset({200, 202, 204})


class HttpRevalidationAdapter(RevalidationPort):
    """Posts the signal to the frontend's revalidation route handler.

    Args:
        url: The frontend's revalidation URL. Defaults to the deployment's setting.
        secret: The shared secret. Defaults to the deployment's setting.
        timeout: How long to wait for an answer, in seconds.
    """

    def __init__(
        self,
        url: str | None = None,
        secret: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._url = url
        self._secret = secret
        self._timeout = timeout

    def _resolved_url(self) -> str:
        return self._url or settings.FRONTEND_REVALIDATION_URL

    def _resolved_secret(self) -> str:
        return self._secret or settings.REVALIDATION_SECRET

    def _resolved_timeout(self) -> float:
        if self._timeout is not None:
            return self._timeout
        return settings.REVALIDATION_TIMEOUT_SECONDS

    def revalidate(self, request: RevalidationRequest) -> RevalidationResult:
        """Deliver one signal. Never raises for a failed delivery."""
        url = self._resolved_url()
        secret = self._resolved_secret()
        payload = {"paths": list(request.paths), "event_version": request.event_version}

        try:
            with httpx.Client(
                timeout=self._resolved_timeout(),
                follow_redirects=False,  # a redirect would carry the bearer token elsewhere
            ) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {secret}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.TimeoutException:
            logger.warning("Revalidation timed out", extra={"job": "revalidate"})
            return RevalidationResult(outcome=RevalidationOutcome.TIMEOUT)
        except httpx.HTTPError:
            logger.warning("Revalidation unreachable", extra={"job": "revalidate"})
            return RevalidationResult(outcome=RevalidationOutcome.NETWORK)

        status = response.status_code
        if status in DELIVERED_STATUSES:
            logger.info("Revalidation delivered", extra={"job": "revalidate", "status": status})
            return RevalidationResult(outcome=RevalidationOutcome.DELIVERED, status=status)
        if status in (401, 403):
            # The secret is wrong. Retrying with the same wrong secret forever is noise; the
            # backend records this as permanent and surfaces it.
            logger.error(
                "Revalidation refused: the secret is wrong",
                extra={"job": "revalidate", "status": status},
            )
            return RevalidationResult(outcome=RevalidationOutcome.UNAUTHORIZED, status=status)
        logger.warning("Revalidation failed", extra={"job": "revalidate", "status": status})
        return RevalidationResult(outcome=RevalidationOutcome.UNAVAILABLE, status=status)
