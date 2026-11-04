"""The SEO city page's published read: the events for `/events-in-{city}` (FR-27).

**Why this module exists.** The city page is a *public* surface (AD-12), so its endpoint
lives in `apps/catalog` — and `apps.catalog` may not import `apps.ingestion.models`
(import contract `models-ingestion`). The Event Fit read,
`apps.ingestion.event_fit.reads`, imports that model directly, so `apps.catalog` cannot
reach the Event Fit through it either. This module is the published read interface, and
it lives *inside* `apps.ingestion` for the same reason `preview_read` does: the contract
holds, and it hands over plain data.

**What a city page is.** FR-27: *"The system publishes 'Events in [city]' pages with
structured data, ranked organically"* and *"A city page exists for every city in the
Source Registry with >5 events."* So a city page is an **unbounded, paged listing** of a
city's events, addressed by the city's canonical slug.

**The listing and the qualification measure different things, on purpose.**

- The **listing** shows *upcoming* events. A page headed "events in Brooklyn" that leads
  with last week's is a page nobody comes back to.
- The **qualification** asks a different question — *has this city ever had enough events
  to deserve a page?* — and counts over a **broader window**
  (`CITY_PAGE_QUALIFICATION_WINDOW`).

Without the broader window a city's page would wink out of existence the moment its last
event started: a URL that 404s after ranking is worse than one that never ranked. With
it, the page persists and shows "coming soon" between seasons, which is exactly what
FR-27 asks for — *"a city page degrades gracefully when no events are present (shows
'coming soon' copy)"*.

**The count and the listing are computed by the same filters.** A city cannot show three
events on a page that claimed it qualified. The staleness rule is a comparison between
two joined columns, so it cannot be expressed in SQL — the count therefore **loads the
rows** rather than issuing a `COUNT(*)`, because a `COUNT(*)` would count stale fits the
listing would not show.

**This module never reads `personal` and never touches a session** (AD-12). The city
page is served to visitors with no account, and its response is identical for everyone,
which is what makes it cacheable.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.ingestion.event_fit.reads import CityEventFitEntry, list_city_event_fits
from apps.ingestion.models import City, Event, EventFit
from domain.errors import NotFoundError
from shared.constants import (
    CITY_PAGE_DEFAULT_PAGE_SIZE,
    CITY_PAGE_EVENT_THRESHOLD,
    CITY_PAGE_MAX_PAGE_SIZE,
    CITY_PAGE_QUALIFICATION_WINDOW,
)
from shared.db import CATALOG

#: How many events the city page returns per page by default.
DEFAULT_CITY_PAGE_SIZE = CITY_PAGE_DEFAULT_PAGE_SIZE
#: The ceiling. A page size above it is clamped, not refused.
MAX_CITY_PAGE_SIZE = CITY_PAGE_MAX_PAGE_SIZE


class CityNotFoundError(NotFoundError):
    """There is no city at that slug.

    **Not found, not forbidden.** A 403 would confirm that the slug exists but the caller
    may not see it, and there is no such thing here: a slug either addresses a city or it
    does not. The slug is a public address and the answer is the same for everybody.
    """

    default_message = "We couldn't find that city."


@dataclass(frozen=True)
class CityPageEvent:
    """One event on a city page.

    Plain data — not the model — so the calling app never holds a reference to
    `apps.ingestion.models` and the wall holds without either side knowing the other's
    models.
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


@dataclass(frozen=True)
class CityPage:
    """One city page: the city's identity, its events, and whether it is published.

    **`is_published` is the FR-27 threshold, and it is computed by the listing's own
    filters.** A city page exists for a city with more than `CITY_PAGE_EVENT_THRESHOLD`
    events; below that it is not published, and the frontend shows the "coming soon"
    state rather than a listing.

    **`event_count` is the qualifying count**, not the number of items on this page. It
    is what the threshold was decided on. It is **not** what `has_next` is measured
    against — see `has_next` below.
    """

    #: The canonical slug — the URL segment.
    slug: str
    #: The city's display name, as first written.
    name: str
    country_code: str
    region: str
    #: Whether the city qualifies for a published page (FR-27).
    is_published: bool
    #: How many events the city has, counted by the listing's filters.
    event_count: int
    #: This page's events.
    items: tuple[CityPageEvent, ...]
    page: int
    page_size: int
    #: Whether there is a page after this one — measured against the **listing's** total,
    #: not the qualifying count. A city between seasons has a qualifying count of six and
    #: an empty listing; it has no next page, and saying otherwise would send a crawler
    #: to an empty page forever.
    has_next: bool


def _city_by_slug(*, slug: str) -> City | None:
    """The city at this slug, or None.

    **The match is exact, not case-insensitive.** Slugs are lowercase by construction,
    so a case-insensitive match would make `/events-in-Brooklyn` and
    `/events-in-brooklyn` two URLs for one page — a duplicate-URL fault for a crawler,
    and the wrong answer for a link somebody was given. This is the same rule the public
    event page's slug lookup follows.
    """
    return City.objects.using(CATALOG).filter(slug=slug).first()


def _current_rows(*, city_ref_id: UUID, since: datetime) -> list[EventFit]:
    """The city's Event Fit rows in the window, with the stale ones dropped.

    **The staleness skip happens here, not in SQL.** A fit records the Event version it
    was computed from, and a row whose `event_version` no longer matches its Event
    describes an event that no longer exists. Comparing two joined columns is not
    something SQL can do in one `WHERE`, so the rows are loaded and the comparison is
    made in Python — the same rule the listing uses, so the count and the listing can
    never disagree.

    **The same publication filters as the listing**: published, not superseded.
    """
    rows = (
        EventFit.objects.using(CATALOG)
        .filter(city_ref_id=city_ref_id)
        .select_related("event", "event__venue")
        .filter(event__publication_status=Event.PublicationStatus.PUBLISHED)
        .exclude(event__status=Event.Status.SUPERSEDED)
        .filter(event__start_time_utc__gte=since)
        .order_by("event__start_time_utc", "event_id")
    )
    return [row for row in rows if row.event_version == row.event.event_version]


def _counts(*, city_ref_id: UUID, now: datetime) -> tuple[int, int]:
    """The city's two counts — the qualifying one and the upcoming one — in **one** load.

    **They come from a single query because one set of rows answers both questions.**
    The qualification window looks back `CITY_PAGE_QUALIFICATION_WINDOW` days and the
    listing looks forward from `now`, so the upcoming rows are a **subset** of the
    qualifying rows: one load of the wider set, split in Python by where the event
    starts, gives both numbers. Two separate loads would scan the same rows twice to
    produce two numbers that differ by a comparison.

    Returns `(qualifying_count, upcoming_count)`:

    - **the qualifying count** is over the window — *has this city ever had enough
      events to deserve a page?* — and it is what FR-27's threshold is decided on;
    - **the upcoming count** is what is actually on the listing — *what is on it?* — and
      it is what `has_next` is measured against.

    **The two are different numbers, and using one for the other's question is a bug.**
    A city between seasons has six qualifying events and an empty listing; measuring
    `has_next` against six would tell a crawler there is a next page on a page with
    nothing on it, and it would follow it forever.

    **The window is inclusive of its lower edge.** An event exactly
    `CITY_PAGE_QUALIFICATION_WINDOW` old is inside it.
    """
    since = now - CITY_PAGE_QUALIFICATION_WINDOW
    rows = _current_rows(city_ref_id=city_ref_id, since=since)
    qualifying = len(rows)
    upcoming = sum(1 for row in rows if row.event.start_time_utc >= now)
    return qualifying, upcoming


def _to_city_page_event(entry: CityEventFitEntry, *, city_name: str) -> CityPageEvent:
    """The Event Fit read's entry projected onto the city page's own shape.

    **The score and the tags are carried as stored** — the fit was computed when the row
    was written, and nothing here recomputes it (AD-10). The projection is a reshape, not
    a calculation.

    **The city is the canonical city's name, not the fit row's free text.** The fit row
    stores whatever spelling the venue wrote — `"Brooklyn"`, `"brooklyn "`,
    `"Brooklyn, NY"` — and on a page keyed on the canonical city those spellings would
    show up side by side under one heading. The page's own heading is the canonical
    name, so each event's city is that same name. The free text is still what the
    *preview* is keyed on, and that is the preview's business.
    """
    return CityPageEvent(
        id=entry.id,
        slug=entry.slug,
        title=entry.title,
        description=entry.description,
        canonical_url=entry.canonical_url,
        start_time_utc=entry.start_time_utc,
        start_time_tz=entry.start_time_tz,
        end_time_utc=entry.end_time_utc,
        venue_name=entry.venue_name,
        city=city_name,
        score=entry.score,
        tags=entry.tags,
        status=entry.status,
        is_sold_out=entry.is_sold_out,
        event_version=entry.event_version,
        tz_review_pending=entry.tz_review_pending,
    )


def get_city_page(
    *,
    slug: str,
    now: datetime,
    page: int = 1,
    page_size: int = DEFAULT_CITY_PAGE_SIZE,
) -> CityPage:
    """One city page: the city's events, and whether it is published.

    **The unknown slug is a 404; the sparse city is a 200.** Those are different
    questions and they get different answers. An unknown slug is a URL that does not
    exist, and saying so is the honest response. A known city with too few events is a
    real city whose page is not published — and FR-27 asks that it *degrade gracefully*,
    not that it disappear. So the page comes back with `is_published=False` and an empty
    listing, and the frontend renders "coming soon".

    **The threshold is counted by the listing's filters** (`_count_qualifying_events`),
    so a city cannot show three events on a page that claimed it qualified.

    **Paging is bounded and past the end is empty, not an error.** A request for a page
    beyond the last one returns the same page shape with no items. A crawler walking off
    the end of a listing is doing something ordinary.

    **`has_next` is measured against the listing's total, not the qualifying count.**
    The qualifying count spans the window and the listing spans the future, so they are
    different numbers — and a city between seasons has the first without the second.
    Measuring the paging flag against the qualifying count would tell a crawler there is
    a next page on a page with nothing on it, and it would follow that forever.
    """
    city = _city_by_slug(slug=slug)
    if city is None:
        raise CityNotFoundError(details={"slug": slug})

    page = max(1, page)
    page_size = max(1, min(page_size, MAX_CITY_PAGE_SIZE))

    event_count, upcoming_count = _counts(city_ref_id=city.pk, now=now)
    is_published = event_count > CITY_PAGE_EVENT_THRESHOLD

    offset = (page - 1) * page_size
    entries = list_city_event_fits(
        city_ref_id=city.pk,
        now=now,
        offset=offset,
        limit=page_size,
    )

    items = tuple(_to_city_page_event(entry, city_name=city.name) for entry in entries)

    return CityPage(
        slug=city.slug,
        name=city.name,
        country_code=city.country_code,
        region=city.region,
        is_published=is_published,
        event_count=event_count,
        items=items,
        page=page,
        page_size=page_size,
        has_next=offset + len(items) < upcoming_count,
    )


__all__ = [
    "DEFAULT_CITY_PAGE_SIZE",
    "MAX_CITY_PAGE_SIZE",
    "CityNotFoundError",
    "CityPage",
    "CityPageEvent",
    "get_city_page",
]
