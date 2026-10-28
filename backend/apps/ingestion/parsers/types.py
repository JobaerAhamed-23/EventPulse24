"""What a structured parser returns (FR-14 structured path, FR-56).

Candidates carry facts exactly as the source wrote them. Parsers never decide a UTC instant, a
timezone tier or an identity: `domain.timezones.resolve_tz` and `domain.dedup` do, in the
pipeline. Text fields are plain text (AD-9) and capped to the catalog's column sizes.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

MAX_TITLE = 500  # Event.title
MAX_DESCRIPTION = 10_000
MAX_VENUE_NAME = 200  # Venue.name
MAX_CITY = 100  # Venue.city
MAX_URL = 2048  # Event.canonical_url
MAX_SOURCE_EVENT_ID = 512  # Event/ExtractedRecord.source_event_id
MAX_ITEMS = 5_000  # per document; the rest are counted, not parsed


class StatusHint(StrEnum):
    SCHEDULED = "scheduled"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class SourceContext:
    source_id: UUID
    source_url: str  # base for relative links


@dataclass(frozen=True)
class ParsedCandidate:
    source_event_id: str  # never empty
    title: str
    canonical_url: str  # absolute http(s) as given, or ""
    start: datetime  # naive wall-clock time, or aware with the source's fixed offset
    start_zone: str | None  # zone name as written (Windows names mapped to IANA)
    start_raw: str  # the text exactly as written
    end: datetime | None = None  # same representation as `start`
    end_raw: str | None = None
    all_day: bool = False
    venue_name: str = ""
    venue_city: str = ""
    venue_country: str = ""  # ISO 3166 alpha-2 when given
    description: str = ""
    status: StatusHint = StatusHint.SCHEDULED
    sold_out: bool = False
    series_id: UUID | None = None
    raw: dict[str, str] = field(default_factory=dict)  # as-written fields for the payload


@dataclass
class ParseResult:
    candidates: list[ParsedCandidate] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)  # reason -> count
    error: str | None = None  # the whole document was unreadable
    # source_event_id -> (position in candidates, priority): one candidate per source item.
    _ids: dict[str, tuple[int, int]] = field(default_factory=dict, repr=False)

    def skip(self, reason: str, count: int = 1) -> None:
        self.skipped[reason] += count

    def add(self, candidate: ParsedCandidate, priority: int = 0) -> None:
        """Keep one candidate per `source_event_id` (rule (a) would merge them anyway).

        A higher priority replaces an earlier candidate in place (an ICS RECURRENCE-ID override
        beats its master's instance, whichever comes first in the file). Otherwise the first is
        kept; an equal-priority repeat is counted as `duplicate_id`.
        """
        found = self._ids.get(candidate.source_event_id)
        if found is None:
            self._ids[candidate.source_event_id] = (len(self.candidates), priority)
            self.candidates.append(candidate)
            return
        position, existing = found
        if priority > existing:
            self.candidates[position] = candidate
            self._ids[candidate.source_event_id] = (position, priority)
        elif priority == existing:
            self.skip("duplicate_id")

    @property
    def full(self) -> bool:
        return len(self.candidates) >= MAX_ITEMS
