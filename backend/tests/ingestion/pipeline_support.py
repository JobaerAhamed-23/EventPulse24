"""Test support for the ingest pipeline: a scripted fetch port and small feed builders.

The recorded fixtures (`tests/fixtures/sources/`, served by `FakeFetchAdapter`) cover first
ingests and error paths; lifecycle sequences need a body that changes between runs, which
`ScriptedFetchPort` serves.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import timedelta

from apps.ingestion.models import Source
from ports.fetch import FetchError, FetchLimits, FetchResult, SourceFetchPort
from tests.ingestion.factories import SourceFactory


@dataclass
class ScriptedFetchPort(SourceFetchPort):
    """Serves the queued responses in order; the last one repeats. Records each call."""

    responses: list[FetchResult | FetchError] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)

    def serve(self, *responses: FetchResult | FetchError | bytes | str) -> "ScriptedFetchPort":
        self.responses = [ok(r) if isinstance(r, bytes | str) else r for r in responses]
        return self

    def fetch(
        self,
        url,
        *,
        etag=None,
        last_modified=None,
        source_id=None,
        allow_cross_host_redirect=False,
        limits: FetchLimits | None = None,
        credential: bool = False,
    ) -> FetchResult:
        self.calls.append({"url": url, "etag": etag, "last_modified": last_modified})
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, FetchError):
            raise response
        return response


def ok(body: bytes | str, *, url: str = "https://feeds.example.test/cal.ics", **kw) -> FetchResult:
    content = body.encode() if isinstance(body, str) else body
    return FetchResult(status=200, final_url=url, content_type="text/calendar", body=content, **kw)


def vevent(
    uid: str,
    start: str,
    *,
    summary: str = "Jazz Night",
    tzid: str | None = "America/New_York",
    end: str | None = None,
    status: str | None = None,
    location: str | None = None,
    url: str | None = None,
    description: str | None = None,
    extra: Iterable[str] = (),
) -> str:
    """One VEVENT. `start` is `YYYYMMDDTHHMMSS` (add `Z` for UTC, and pass tzid=None)."""
    tz = f";TZID={tzid}" if tzid else ""
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"SUMMARY:{summary}", f"DTSTART{tz}:{start}"]
    if end:
        lines.append(f"DTEND{tz}:{end}")
    for name, value in (
        ("STATUS", status),
        ("LOCATION", location),
        ("URL", url),
        ("DESCRIPTION", description),
    ):
        if value:
            lines.append(f"{name}:{value}")
    lines += [*extra, "END:VEVENT"]
    return "\r\n".join(lines)


def calendar(*events: str) -> str:
    body = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//EventPulse24 tests//EN", *events]
    return "\r\n".join([*body, "END:VCALENDAR", ""])


def ics_source(**overrides) -> Source:
    defaults = {
        "acquisition_method": "ics",
        "url": "https://feeds.example.test/cal.ics",
        "ingestion_cadence": timedelta(hours=4),
    }
    return SourceFactory(**(defaults | overrides))
