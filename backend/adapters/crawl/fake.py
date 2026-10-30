"""Local stand-in for source fetches: recorded fixtures, no network (AD-9).

`<fixtures_dir>/index.json` maps a URL to an entry:
    {"file": "venue.rss", "content_type": "application/rss+xml",
     "etag": "\\"v1\\"", "last_modified": "Wed, 04 Nov 2026 10:00:00 GMT",
     "simulate": "timeout" | "too_large" | "blocked" | "network" | "content" | "redirects"
                 | {"status": 503}}
Only `file` and `content_type` are required (`file` may be omitted when `simulate` is set).
The index is validated once, when the adapter is built (and by system check eventpulse.E006),
never on a fetch. Conditional requests follow RFC 9110: If-None-Match wins; a 304 needs a
validator on both sides.
"""

import json
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from ports.fetch import (
    NOT_MODIFIED,
    FetchBlockedError,
    FetchContentError,
    FetchError,
    FetchHTTPError,
    FetchLimits,
    FetchNetworkError,
    FetchRedirectError,
    FetchResult,
    FetchTimeoutError,
    FetchTooLargeError,
    SourceFetchPort,
)

INDEX_FILE = "index.json"
SIMULATED = {
    "timeout": FetchTimeoutError,
    "too_large": FetchTooLargeError,
    "blocked": FetchBlockedError,
    "network": FetchNetworkError,
    "content": FetchContentError,
    "redirects": FetchRedirectError,
}


@dataclass(frozen=True)
class Fixture:
    content_type: str
    path: Path | None = None
    etag: str | None = None
    last_modified: str | None = None
    simulate: str | int | None = None  # a SIMULATED key, or an HTTP status


def _http_date(value: str | None):
    if value is None:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def load_index(fixtures_dir: Path) -> dict[str, Fixture]:
    """Parse and validate the fixture index; raises ImproperlyConfigured with the reason."""
    root = Path(fixtures_dir).resolve()
    try:
        raw = json.loads((root / INDEX_FILE).read_text())
    except FileNotFoundError:
        raise ImproperlyConfigured(f"No {INDEX_FILE} in SOURCE_FIXTURES_DIR ({root}).") from None
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(f"{INDEX_FILE} is not valid JSON: {exc}") from None
    if not isinstance(raw, dict):
        raise ImproperlyConfigured(f"{INDEX_FILE} must map URLs to fixtures.")

    index = {}
    for url, entry in raw.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("content_type"), str):
            raise ImproperlyConfigured(f"Fixture for {url} needs a content_type.")
        simulate = entry.get("simulate")
        if isinstance(simulate, dict):
            simulate = simulate.get("status")
            if not isinstance(simulate, int) or not 300 <= simulate <= 599:
                raise ImproperlyConfigured(f"Fixture for {url}: simulate status must be 300-599.")
        elif simulate is not None and simulate not in SIMULATED:
            raise ImproperlyConfigured(f"Fixture for {url}: unknown simulate {simulate!r}.")
        path = None
        if entry.get("file") is not None:
            path = (root / entry["file"]).resolve()
            if not path.is_relative_to(root):
                raise ImproperlyConfigured(f"Fixture for {url} points outside the fixtures dir.")
            if not path.is_file():
                raise ImproperlyConfigured(f"Fixture file for {url} is missing.")
        elif simulate is None:
            raise ImproperlyConfigured(f"Fixture for {url} needs a file or a simulate.")
        if entry.get("last_modified") is not None and _http_date(entry["last_modified"]) is None:
            raise ImproperlyConfigured(f"Fixture for {url}: last_modified isn't an HTTP date.")
        index[url] = Fixture(
            content_type=entry["content_type"],
            path=path,
            etag=entry.get("etag"),
            last_modified=entry.get("last_modified"),
            simulate=simulate,
        )
    return index


def _simulated_error(simulate: str | int) -> FetchError:
    if isinstance(simulate, int):
        return FetchHTTPError(simulate)
    return SIMULATED[simulate]("simulated")


def _not_modified(fixture: Fixture, etag: str | None, last_modified: str | None) -> bool:
    if etag is not None:  # If-None-Match takes precedence over If-Modified-Since
        return fixture.etag is not None and etag == fixture.etag
    stored, since = _http_date(fixture.last_modified), _http_date(last_modified)
    return stored is not None and since is not None and stored <= since


class FakeFetchAdapter(SourceFetchPort):
    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._index = load_index(fixtures_dir or settings.SOURCE_FETCH["fixtures_dir"])

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
    ) -> FetchResult:
        # `allow_cross_host_redirect` and `limits` are accepted and ignored: a fixture is
        # served directly, so there is no redirect chain to relax and no body to bound.
        # `credential` is accepted and ignored for the same reason: a fixture is read
        # from disk, so no URL is ever written to a log here.
        fixture = self._index.get(url)
        if fixture is None:
            raise FetchHTTPError(404)
        if fixture.simulate is not None:
            raise _simulated_error(fixture.simulate)
        if _not_modified(fixture, etag, last_modified):
            return FetchResult(
                status=NOT_MODIFIED,
                final_url=url,
                content_type=fixture.content_type,
                etag=fixture.etag or etag,
                last_modified=fixture.last_modified or last_modified,
            )
        try:
            body = fixture.path.read_bytes()
        except OSError as exc:  # removed after startup: still a port error, never a raw one
            raise FetchNetworkError("fixture_unreadable") from exc
        return FetchResult(
            status=200,
            final_url=url,
            content_type=fixture.content_type,
            body=body,
            etag=fixture.etag,
            last_modified=fixture.last_modified,
        )
