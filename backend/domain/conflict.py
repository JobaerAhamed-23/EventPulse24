"""Schedule conflicts and duplicate detection (AD-21, FR-33, FR-58). Stdlib only.

Two rules live here, and they are deliberately separate:

- `conflicts` decides whether two UTC intervals overlap by **strictly more than 15 minutes**
  (AD-21). It is the one overlap function: the Pulse Card, the Timeline and `/conflicts` all
  read the same `CONFLICT_PAIR` rows, so they cannot disagree about whether a pair overlaps.
  It runs on save, on Personal Event create, edit or import, and on AD-17 propagation — never
  at render (AD-21).
- `is_duplicate` decides whether two personal events are likely the same event (FR-58): the
  same name and a start within 24 hours.

Both rules are structural, never semantic: no embeddings, no LLM call, no similarity service.
The duplicate rule reuses `domain.dedup`'s normalisation and Jaccard arithmetic rather than
declaring a second one, so a title folds the same way in both paths — "Café Night" cannot be
two different things depending on which rule asked.

Times are UTC instants and are compared as given. Nothing here reads a clock, touches a
database or imports Django: the caller supplies the intervals.
"""

from datetime import UTC, datetime

from domain.dedup import jaccard, title_fingerprint
from domain.errors import InvalidIntervalError
from domain.timezones import to_instant
from shared.constants import (
    CONFLICT_MIN_OVERLAP,
    DUPLICATE_START_WINDOW,
    TITLE_TOKEN_OVERLAP_MIN,
)

# Stands in for "no end time": an open-ended interval runs to the end of representable time.
# A real end is always earlier, so `min()` picks the real one. It is timezone-aware, because
# every instant this module compares against is aware.
_NO_END = datetime.max.replace(tzinfo=UTC)


def _interval_end(start: datetime, end: datetime | None) -> datetime:
    """The end of an interval, treating a missing end as open-ended.

    `start` is already an instant; `end` is normalised the same way, so the validity check
    and the overlap arithmetic compare like with like.
    """
    if end is None:
        return _NO_END
    end = to_instant(end)
    if end < start:
        raise InvalidIntervalError(details={"start": start.isoformat(), "end": end.isoformat()})
    return end


def conflicts(
    a_start: datetime,
    a_end: datetime | None,
    b_start: datetime,
    b_end: datetime | None,
) -> bool:
    """True when two UTC intervals overlap by strictly more than 15 minutes (AD-21, FR-33).

    Exactly 15 minutes is not a conflict; 15 minutes and one second is. A missing end time
    means the interval is open-ended, so it overlaps everything after it — the safe reading
    for a double-booking guard. An interval with no duration at all (`end == start`) occupies
    no time and never conflicts.
    """
    a_start, a_finish = to_instant(a_start), _interval_end(a_start, a_end)
    b_start, b_finish = to_instant(b_start), _interval_end(b_start, b_end)
    overlap = min(a_finish, b_finish) - max(a_start, b_start)
    return overlap > CONFLICT_MIN_OVERLAP


def is_duplicate(
    a_name: str | None,
    a_start: datetime,
    b_name: str | None,
    b_start: datetime,
) -> bool:
    """True when two personal events are likely the same event (FR-58).

    The names overlap by at least 80% on tokens — the same threshold, and the same
    normalisation and Jaccard arithmetic, the identity rule uses — and the two starts are
    within 24 hours of each other. The window is absolute: a candidate that started 23 hours
    *earlier* is within it.
    """
    if abs(to_instant(a_start) - to_instant(b_start)) > DUPLICATE_START_WINDOW:
        return False
    return jaccard(title_fingerprint(a_name), title_fingerprint(b_name)) >= TITLE_TOKEN_OVERLAP_MIN
