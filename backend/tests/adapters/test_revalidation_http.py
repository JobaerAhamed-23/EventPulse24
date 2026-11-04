"""The HTTP revalidation adapter: what it sends, and what it makes of the answer.

**This is the one module that carries the shared secret over the wire**, so its tests are
about the secret and the host as much as about the outcome:

- The secret goes in an `Authorization` header, never in the URL and never in the body.
- The URL comes from configuration. There is no path in which a caller chooses the host.
- Redirects are not followed — a 301 to another host would carry the token with it.
- **Every failure is an outcome, never an exception.** A frontend that is down is the
  normal condition this signal is designed to survive.
"""

import httpx
import pytest

from adapters.revalidation import http as module
from adapters.revalidation.http import DELIVERED_STATUSES, HttpRevalidationAdapter
from ports.revalidation import RevalidationOutcome, RevalidationRequest

SECRET = "a-shared-secret"
URL = "http://frontend.internal:3000/revalidate"


class _StubClient:
    """Stands in for `httpx.Client`. Records the call and answers with a canned response."""

    calls: list[dict] = []
    response: httpx.Response | None = None
    raises: Exception | None = None

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        type(self).calls.append({"init": kwargs})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, *, json=None, headers=None):
        type(self).calls.append({"url": url, "json": json, "headers": headers})
        if type(self).raises is not None:
            raise type(self).raises
        return type(self).response


@pytest.fixture
def stub(monkeypatch):
    _StubClient.calls = []
    _StubClient.response = httpx.Response(204)
    _StubClient.raises = None
    monkeypatch.setattr(module.httpx, "Client", _StubClient)
    return _StubClient


@pytest.fixture
def adapter():
    return HttpRevalidationAdapter(url=URL, secret=SECRET, timeout=3.0)


def _request() -> RevalidationRequest:
    return RevalidationRequest(paths=("/events/jazz-night", "/events-in-brooklyn"), event_version=7)


@pytest.mark.parametrize("status", sorted(DELIVERED_STATUSES))
def test_a_2xx_is_a_delivery(stub, adapter, status):
    stub.response = httpx.Response(status)

    result = adapter.revalidate(_request())

    assert result.outcome is RevalidationOutcome.DELIVERED
    assert result.status == status


def test_the_secret_goes_in_the_header_and_not_in_the_url_or_the_body(stub, adapter):
    adapter.revalidate(_request())

    [call] = [c for c in stub.calls if "url" in c]
    assert call["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert SECRET not in call["url"]
    assert SECRET not in str(call["json"])


def test_the_body_carries_the_paths_and_the_version(stub, adapter):
    adapter.revalidate(_request())

    [call] = [c for c in stub.calls if "url" in c]
    assert call["json"] == {
        "paths": ["/events/jazz-night", "/events-in-brooklyn"],
        "event_version": 7,
    }


def test_the_url_comes_from_configuration(stub, adapter):
    """**There is no path in which a caller chooses the host**, so there is no SSRF surface
    here at all — and no address policy is needed, because the host is ours."""
    adapter.revalidate(_request())

    [call] = [c for c in stub.calls if "url" in c]
    assert call["url"] == URL


def test_redirects_are_not_followed(stub, adapter):
    """**A 301 to another host would carry the bearer token with it.**"""
    stub.response = httpx.Response(301, headers={"Location": "http://elsewhere.example/"})

    result = adapter.revalidate(_request())

    assert result.outcome is RevalidationOutcome.UNAVAILABLE
    assert result.status == 301
    [init] = [c for c in stub.calls if "init" in c]
    assert init["init"]["follow_redirects"] is False


@pytest.mark.parametrize("status", [401, 403])
def test_a_refusal_is_unauthorized_and_is_not_retryable(stub, adapter, status):
    stub.response = httpx.Response(status)

    result = adapter.revalidate(_request())

    assert result.outcome is RevalidationOutcome.UNAUTHORIZED
    assert result.outcome.is_retryable is False
    assert result.status == status


@pytest.mark.parametrize("status", [400, 404, 500, 502, 503])
def test_any_other_status_is_unavailable_and_is_retryable(stub, adapter, status):
    stub.response = httpx.Response(status)

    result = adapter.revalidate(_request())

    assert result.outcome is RevalidationOutcome.UNAVAILABLE
    assert result.outcome.is_retryable is True
    assert result.status == status


def test_a_timeout_is_a_timeout(stub, adapter):
    stub.raises = httpx.TimeoutException("too slow")

    result = adapter.revalidate(_request())

    assert result.outcome is RevalidationOutcome.TIMEOUT
    assert result.outcome.is_retryable is True


def test_a_network_error_is_a_network_error(stub, adapter):
    stub.raises = httpx.ConnectError("no route")

    result = adapter.revalidate(_request())

    assert result.outcome is RevalidationOutcome.NETWORK
    assert result.outcome.is_retryable is True


def test_a_delivery_never_raises(stub, adapter):
    """**A frontend that is down is an outcome, not an exception** — the signal is designed
    to survive exactly this."""
    stub.raises = httpx.ConnectError("no route")

    assert adapter.revalidate(_request()).outcome is RevalidationOutcome.NETWORK


def test_the_reason_is_a_slug(stub, adapter):
    """**The reason recorded on the row is a slug only** — never a URL, never a body
    (AD-13)."""
    stub.response = httpx.Response(500)

    assert adapter.revalidate(_request()).outcome.reason == "unavailable"


def test_the_timeout_is_bounded(stub, adapter):
    adapter.revalidate(_request())

    [init] = [c for c in stub.calls if "init" in c]
    assert init["init"]["timeout"] == 3.0


def test_the_adapter_falls_back_to_the_settings(stub, monkeypatch):
    """**The URL and the secret come from the deployment's settings** when the adapter is
    built with none."""
    monkeypatch.setattr(module.settings, "FRONTEND_REVALIDATION_URL", URL)
    monkeypatch.setattr(module.settings, "REVALIDATION_SECRET", SECRET)
    monkeypatch.setattr(module.settings, "REVALIDATION_TIMEOUT_SECONDS", 5.0)

    HttpRevalidationAdapter().revalidate(_request())

    [call] = [c for c in stub.calls if "url" in c]
    assert call["url"] == URL
    assert call["headers"]["Authorization"] == f"Bearer {SECRET}"
    [init] = [c for c in stub.calls if "init" in c]
    assert init["init"]["timeout"] == 5.0
