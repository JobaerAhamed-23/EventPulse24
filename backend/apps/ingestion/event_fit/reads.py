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

**Two reads, two keys, one set of rules.** The Pulse Preview asks *"what is in the
preview for the city somebody typed?"* and is keyed on the fit row's free-text `city`.
The SEO city page asks *"what is this URL?"* and is keyed on the canonical `City`. The
rules that decide which rows either may serve — published, not superseded, upcoming, not
stale, score-then-start ordering — are **one queryset** (`_published_upcoming_fits`) and
one staleness check (`_is_current`). The two reads are two keys onto that, not two
implementations of it: a second copy of the rules would be a second place for the
staleness rule to live, and the two surfaces would eventually disagree about whether an
event belongs to a city.

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

from django.db.models import QuerySet

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


@dataclass(frozen=True)
class CityEventFitEntry:
    """One event on a city page: the event's public facts and its persisted fit.

    **This is not `EventFitPreviewEntry`, and widening that one was the alternative.**
    The preview's entry is what the preview's card is built from, and the city page
    shows more: the description, the status, the sold-out flag and the canonical URL.
    Adding those to the preview's shape would put them on the preview's contract too,
    and the preview's contract is not the city page's to change. The same reasoning that
    gave `PublicEvent` and `PublicEventDetail` separate shapes applies here.

    **The rules are still shared.** Only the *shape* differs; both entries come from
    the same queryset and the same staleness check, so the two surfaces cannot disagree
    about which events belong to a city.
    """

    id: UUID
    slug: str
    title: str
    description: str
    canonical_url: str
    start_time_utc: datetime
    start_time_tz: str
    end_time_utc: datetime | None
    venue_name: str | None
    city: str
    score: int
    tags: tuple[str, ...]
    status: str
    is_sold_out: bool
    event_version: int
    tz_review_pending: bool


def _published_upcoming_fits(*, now: datetime) -> QuerySet:
    """The Event Fit rows a public surface may serve: published, upcoming, not superseded.

    **These are the rules, written once.** The Pulse Preview and the SEO city page are
    two surfaces reading the same kind of thing, and the rules that decide *which* rows
    they may serve are the same rules — so they are one queryset, and the two reads are
    two *keys* onto it rather than two implementations of it. A second implementation
    would be a second place for the staleness rule to live, and the two surfaces would
    eventually disagree about whether an event belongs to a city.

    - **published only** — an `in_review` event is not publicly listed (AD-6, AD-8);
    - **not superseded** — a superseded Event is terminal and its live replacement is
      listed instead (D7);
    - **upcoming** — `start_time_utc >= now`; an event that has already started is not
      coming;
    - **ordered by score descending, then start time ascending** — the fit is the reason
      an event is on the page, and among equally good fits the sooner one is the more
      useful one. `event_id` breaks the remaining tie, so the order is *total*: two rows
      that agree on score and start time cannot swap places between pages. The id is a
      UUIDv7, so the tiebreak is also time-ordered.

    **The staleness skip is not here, because it cannot be.** A fit records the Event
    version it was computed from, and a row whose `event_version` no longer matches its
    Event describes an event that no longer exists. That comparison is between two
    columns of *joined* rows, so it is made in Python by the readers below.
    """
    return (
        EventFit.objects.using(CATALOG)
        .select_related("event", "event__venue")
        .filter(event__publication_status=Event.PublicationStatus.PUBLISHED)
        .exclude(event__status=Event.Status.SUPERSEDED)
        .filter(event__start_time_utc__gte=now)
        .order_by("-score", "event__start_time_utc", "event_id")
    )


def _is_current(row: EventFit) -> bool:
    """Whether a fit row still describes the event it was computed from.

    **A stale row is absent, never wrong.** A fit records the Event version it was
    computed from; if the Event has moved on since, the fit describes an event that no
    longer exists. The row is not deleted here — the refresh rewrites it — so a fit that
    is stale for a moment is simply absent from the page rather than serving a score and
    a tag set that describe a different event.
    """
    return row.event_version == row.event.event_version


def _to_preview_entry(row: EventFit) -> EventFitPreviewEntry:
    """The fit row projected onto the plain-data shape the surfaces read."""
    event = row.event
    return EventFitPreviewEntry(
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


def _to_city_entry(row: EventFit) -> CityEventFitEntry:
    """The fit row projected onto the city page's shape.

    **The score and the tags come off the row as they stand** — the fit was computed
    when the row was written, and neither this read nor the render recomputes them
    (AD-10). The event's other facts are read from the Event the fit points at.
    """
    event = row.event
    return CityEventFitEntry(
        id=event.id,
        slug=event.slug,
        title=event.title,
        description=event.description,
        canonical_url=event.canonical_url,
        start_time_utc=event.start_time_utc,
        start_time_tz=event.start_time_tz,
        end_time_utc=event.end_time_utc,
        venue_name=event.venue.name if event.venue else None,
        city=row.city,
        score=row.score,
        tags=tuple(row.tags),
        status=event.status,
        is_sold_out=event.is_sold_out,
        event_version=event.event_version,
        tz_review_pending=event.tz_review_pending,
    )


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

    **The city is matched as free text, case-insensitively**, on the fit row's own
    `city` column. That is the preview's key, and it is why the city page has a
    *different* one: the preview answers "what is in the preview for the city somebody
    typed?", and the page answers "what is this URL?" — and the second needs the
    canonical `City`, not a spelling.
    """
    limit = max(1, min(limit, MAX_PREVIEW_SIZE))
    rows = _published_upcoming_fits(now=now).filter(city__iexact=city.strip())

    entries: list[EventFitPreviewEntry] = []
    for row in rows:
        if not _is_current(row):
            continue  # stale: the Event changed after this fit was computed
        entries.append(_to_preview_entry(row))
        if len(entries) >= limit:
            break
    return entries


def list_city_event_fits(
    *,
    city_ref_id: UUID,
    now: datetime,
    offset: int = 0,
    limit: int | None = None,
) -> list[CityEventFitEntry]:
    """The city's upcoming public events, best Event Fit first, from an offset.

    **The same rules as the preview's read, keyed on the canonical `City`.** The
    staleness skip, the publication filters, the upcoming bound and the ordering all
    come from `_published_upcoming_fits` — there is one implementation of them, and this
    read is a second *key* onto it rather than a second copy of it.

    **The key is the canonical city's id, not its name.** `Brooklyn` and `Brooklyn, NY`
    are two `City` rows by construction (the identity is key + region + country), and
    the slug is what addresses them. Matching on the name would put the two spellings
    on one page; matching on the id puts each on its own.

    **Paging is by offset**, and the order is total — score, then start time, then the
    event id — so a row cannot move between pages. An offset beyond the last page
    returns **empty**, not an error: a caller asking for a page that does not exist is
    asking a reasonable question.

    **The offset is applied in Python, not in SQL, and that is the price of the
    staleness rule.** A SQL `OFFSET` counts *rows*, and a stale row is a row the
    listing must not show — so an SQL offset would count the wrong things and the
    pages would overlap. Skipping in Python keeps the page boundaries on exactly the
    rows that are served. The cost is that a deep page walks past the rows it skips;
    the mitigation is the page-size ceiling and the fact that a city's fit rows are
    bounded by the size of the city, not by the size of the database.

    **`offset` and `limit` are clamped rather than rejected.** A negative offset is
    treated as zero and a negative limit as no limit, because the only caller is a
    public endpoint and a bad page number should not be a 500.
    """
    offset = max(0, offset)
    rows = _published_upcoming_fits(now=now).filter(city_ref_id=city_ref_id)

    entries: list[CityEventFitEntry] = []
    skipped = 0
    for row in rows:
        if not _is_current(row):
            continue  # stale: the Event changed after this fit was computed
        if skipped < offset:
            skipped += 1
            continue
        entries.append(_to_city_entry(row))
        if limit is not None and len(entries) >= limit:
            break
    return entries


__all__ = [
    "DEFAULT_PREVIEW_SIZE",
    "MAX_PREVIEW_SIZE",
    "CityEventFitEntry",
    "EventFitPreviewEntry",
    "list_city_event_fits",
    "list_event_fit_for_city",
]
