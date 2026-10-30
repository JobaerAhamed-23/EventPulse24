"""The Event Fit read: the preview's top N for a city (AD-10, FR-26).

**This module is separate from `catalog_read` on purpose.** `catalog_read` is the public
catalog interface, and `personalization` legitimately reads it — saving an event to your
calendar needs the event's public facts. But AD-10 forbids the two kinds of explanation
from crossing, and a *module-level* wall is the only kind that cannot be argued with: if
the Event Fit read lived beside the public-event read, "does `personalization` import the
Event Fit?" would be a question about import *names* rather than about modules, and a
single added name would open the door.

So the Event Fit read is its own module. `personalization` may import
`catalog_read`; it may not import this one. That is a structural fact about the tree,
not a convention someone has to remember.

**What this read does.** It serves the **persisted** Event Fit row: the score and the
tags were decided when the fit was written, and this read only reads them. Nothing here
computes a fit (AD-10: "never recomputed at render").

**It never reads `personal`.** Event Fit is the session-free explanation: a visitor with
no account gets this and nothing else (AD-12). The personalized explanation is a
different thing, owned by `personalization`, and the two are never substituted for one
another — that substitution is the trust-collapse failure AD-10 calls company-ending.

**`now` is an explicit parameter**, like every other read here: no time-freezing library,
and each boundary is testable at the exact second.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.ingestion.models import Event, EventFit
from shared.db import CATALOG

# How many events the Pulse Preview shows by default. Three is what fits on the preview
# surface without scrolling, and it is the number the work item names.
DEFAULT_PREVIEW_SIZE = 3
MAX_PREVIEW_SIZE = 20


@dataclass(frozen=True)
class EventFitPreviewEntry:
    """One event in the preview: the event's public facts and its persisted fit.

    The fit is the **persisted row**, served as it stands. Nothing here is computed: the
    score and the tags were decided when the fit was written, and this read only reads
    them (AD-10).
    """

    id: UUID
    slug: str
    title: str
    start_time_utc: datetime
    start_time_tz: str
    venue_name: str | None
    city: str
    score: int
    tags: tuple[str, ...]
    event_version: int
    tz_review_pending: bool


def list_event_fit_for_city(
    *,
    city: str,
    now: datetime,
    limit: int = DEFAULT_PREVIEW_SIZE,
) -> list[EventFitPreviewEntry]:
    """The top N upcoming public events for a city, best Event Fit first.

    The ordering is **score descending, then start time ascending** — the fit is the
    reason an event is in the preview, and among equally good fits the sooner one is the
    more useful one.

    **A stale row is never served.** A fit records the Event version it was computed
    from; if the Event has moved on since, the fit describes an event that no longer
    exists and is skipped. The row is not deleted here — the refresh rewrites it — so a
    fit that is stale for a moment is simply absent from the preview rather than wrong.

    **Only published, upcoming, non-superseded events appear.** An `in_review` event is
    not publicly listed (AD-6, AD-8), a superseded event is terminal (D7), and an event
    that has already started is not coming.
    """
    limit = max(1, min(limit, MAX_PREVIEW_SIZE))
    rows = (
        EventFit.objects.using(CATALOG)
        .filter(city__iexact=city.strip())
        .select_related("event", "event__venue")
        .filter(event__publication_status=Event.PublicationStatus.PUBLISHED)
        .exclude(event__status=Event.Status.SUPERSEDED)
        .filter(event__start_time_utc__gte=now)
        .order_by("-score", "event__start_time_utc", "event_id")
    )

    entries: list[EventFitPreviewEntry] = []
    for row in rows:
        event = row.event
        if row.event_version != event.event_version:
            continue  # stale: the Event changed after this fit was computed
        entries.append(
            EventFitPreviewEntry(
                id=event.id,
                slug=event.slug,
                title=event.title,
                start_time_utc=event.start_time_utc,
                start_time_tz=event.start_time_tz,
                venue_name=event.venue.name if event.venue else None,
                city=row.city,
                score=row.score,
                tags=tuple(row.tags),
                event_version=event.event_version,
                tz_review_pending=event.tz_review_pending,
            )
        )
        if len(entries) >= limit:
            break
    return entries


__all__ = [
    "DEFAULT_PREVIEW_SIZE",
    "MAX_PREVIEW_SIZE",
    "EventFitPreviewEntry",
    "list_event_fit_for_city",
]
