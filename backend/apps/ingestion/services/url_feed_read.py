"""The public URL feed: every publicly addressable page, and when it last changed.

**What this read is for.** The sitemap is not a list somebody keeps — it is a
projection of the *public surface*, read from the same place the public pages read their
facts. A hand-maintained sitemap is stale the first time the pipeline runs, and a
sitemap that lists a URL which 404s is a crawl-budget leak: the crawler spends a fetch
to learn that the URL does not exist. So this read answers exactly one question —
**"which URLs does this site serve, and when did each last move?"** — and the sitemap
renders the answer.

**Why it lives inside `apps.ingestion`.** The `models-ingestion` import contract (AD-2)
means `apps.catalog` may not import `apps.ingestion.models`, so the catalog's endpoint
cannot reach the Event, the City or the Event Fit directly. This module is the published
read interface, exactly as `city_read.py` is, and it hands over plain frozen dataclasses.

**The membership is the public surface, exactly.** An entry appears here if and only if
the corresponding page is publicly addressable:

- an **event** is published and not superseded, with **no time bound** — because
  `get_public_event_by_slug` answers *"what is this URL?"* and there **a past event
  still resolves**: *"a page for an event that already happened stays addressable and
  stays indexed."* Excluding past events would under-report the surface, and the public
  pages would exist unlisted;
- a **city** qualifies when its qualifying count over
  `CITY_PAGE_QUALIFICATION_WINDOW` is `> CITY_PAGE_EVENT_THRESHOLD` — FR-27's threshold,
  computed by the **listing's own filters**, so the feed and the city page can never
  disagree about whether a city is published.

**`lastmod` is the event's real last change, not a timestamp of convenience.**
`Event.updated_at` is `auto_now`, and every production write goes through
`QuerySet.update()` — which does not touch `auto_now`. `updated_at` is therefore frozen
at creation and would tell a crawler a page had never changed. The honest basis is
`EventStateChange.occurred_at`: the state change table is **append-only** (enforced three
ways — the Python manager, the `catalog.forbid_history_mutation` trigger and the runtime
grants), and **every `event_version` bump has exactly one row** (`event_writes.py` writes
one row per change kind, and `(event, event_version)` is unique). A brand-new event at
version 1 has no row, so `Event.created_at` is the fallback.

**A city's `lastmod` is the max over its qualifying events' lastmods.** A city page
changes when one of its events changes, so that is the truth about what moved. A city
that has no qualifying events is not in the feed at all, so it has no `lastmod`.

**The read is paged and bounded.** This read grows with the catalog, so it must never be
an unbounded scan: the endpoint bounds `page` and `page_size` at the edge (a 422), and
the service clamps below that.

**This module never reads `personal` and never touches a session** (AD-12). The feed is
served to visitors with no account, and its response is identical for everyone — which is
what makes it cacheable, and what lets a crawler fetch it.
"""

from dataclasses import dataclass
from datetime import datetime

from django.db.models import Count, DateTimeField, F, Max, OuterRef, Subquery
from django.db.models.functions import Coalesce

from apps.ingestion.models import Event, EventFit, EventStateChange
from domain.revalidation import CITY_PATH_PREFIX, EVENT_PATH_PREFIX
from shared.constants import (
    CITY_PAGE_EVENT_THRESHOLD,
    CITY_PAGE_QUALIFICATION_WINDOW,
    URL_FEED_DEFAULT_PAGE_SIZE,
    URL_FEED_MAX_PAGE_SIZE,
)
from shared.db import CATALOG

#: How many URLs a feed page carries by default.
DEFAULT_URL_FEED_PAGE_SIZE = URL_FEED_DEFAULT_PAGE_SIZE
#: The ceiling. A page size above it is clamped, not refused.
MAX_URL_FEED_PAGE_SIZE = URL_FEED_MAX_PAGE_SIZE


class UrlFeedKind:
    """The two kinds of public page the feed carries.

    **A plain string holder, not a `StrEnum`.** The value crosses onto the wire, and the
    wire shape is a Pydantic schema with its own literal type — so the wire's vocabulary
    is declared once, in the schema, and this class is the read's own name for the same
    two things. A third kind would have to be added in both places, which is the point:
    a kind that exists on only one side of the wall is a kind nobody can serve.
    """

    EVENT = "event"
    CITY = "city"


@dataclass(frozen=True)
class UrlFeedEntry:
    """One publicly addressable URL, and when it last changed.

    Plain data — not the model — so the calling app never holds a reference to
    `apps.ingestion.models` and the wall holds without either side knowing the other's
    models.

    **`path` is a path, not a URL.** It is the site's own public path — `/events/{slug}`
    or `/events-in-{city}` — and the origin is the frontend's business (AD-12: the
    frontend resolves URLs against its own `metadataBase`). The path is built from the
    **same prefixes the revalidation signal uses** (`domain/revalidation.py`), so the
    sitemap's URLs and the signal's paths cannot drift apart.
    """

    path: str
    kind: str
    last_modified: datetime


@dataclass(frozen=True)
class UrlFeedPage:
    """One page of the feed, and what the caller needs to page through it.

    **`total` is the size of the whole feed**, so a caller can decide how many children
    its sitemap index needs before it fetches the first child. **`has_next` is measured
    against that total** — the same rule the city page follows, and for the same reason:
    the two numbers answer different questions, and using one for the other's question is
    a bug.
    """

    items: tuple[UrlFeedEntry, ...]
    page: int
    page_size: int
    total: int
    has_next: bool


def _last_modified(*, pk_col: str, version_col: str, created_col: str):
    """The per-event `lastmod`: the last state change, or the event's creation.

    **The state's own row, not a re-derived number.** `EventStateChange.event_version` is
    the Event's version *after* the change, and the unique constraint
    `(event, event_version)` means there is at most one row per version. So the row
    whose version equals the Event's current version **is** the last change — and it is
    the last change by definition, because the version only ever rises.

    **The fallback is inside the coalesce.** `COALESCE(state_change.occurred_at,
    event.created_at)` — an event that has never changed has no state-change row, and
    its creation is the honest answer for a page that has never moved.

    **A silent update does not move it.** `apply_silent_update` writes a title, a
    description and a URL with **no** version bump and **no** state-change row, so by
    this rule the `lastmod` does not move. That is the AC's own rule stated honestly:
    `lastmod` is derived from the event's *real* last change, and a silent update is
    explicitly not a change of that kind.

    **The expression is flat, and it is parameterised by column name.** The obvious
    shape — a `Subquery` over `Event` that itself contains a `Subquery` over the state
    changes — does not work: `OuterRef` inside the inner subquery resolves against the
    *inner* queryset's model, so the outer reference points at the wrong table and
    Django raises `FieldError: Cannot resolve keyword 'event_id' into field`. This flat
    form resolves `OuterRef` against whichever queryset the expression is attached to,
    which is what lets the same expression serve both the event side and the city side:

    - on the **Event** queryset: `pk_col="pk"`, `version_col="event_version"`,
      `created_col="created_at"`;
    - on the **EventFit** queryset: `pk_col="event_id"`,
      `version_col="event__event_version"`, `created_col="event__created_at"` — the
      fit's own event id, and the joined event's version and creation.
    """
    state_change = Subquery(
        EventStateChange.objects.using(CATALOG)
        .filter(event=OuterRef(pk_col), event_version=OuterRef(version_col))
        .values("occurred_at")[:1],
        output_field=DateTimeField(),
    )
    return Coalesce(
        state_change,
        F(created_col),
        output_field=DateTimeField(),
    )


def _event_queryset():
    """The queryset of the public event URLs, in feed order.

    **Published, not superseded, and no time bound.** The same two filters
    `catalog_read._public_events` applies — the public surface's own definition of
    "public" — and the same deliberate absence of a time bound, because
    `get_public_event_by_slug` serves a past event and a page that exists is a page a
    crawler should be able to find.

    **The `lastmod` is a correlated subquery per event**, so the ordering and the
    slicing are a single query with a single index scan. Ordering is by slug: the feed is
    a *set of URLs*, and slug is the one key on the Event that is unique, stable and
    never re-minted (`event_slug_uq`, and `services/slugs.py` never re-mints a slug on
    retitle). A page boundary is therefore unambiguous, and two pages cannot overlap.

    **The queryset is built here and sliced elsewhere**, so the caller can count the
    whole set and take a slice of it from the *same* rule — one definition of "public",
    counted and sliced alike.
    """
    last_modified = _last_modified(
        pk_col="pk", version_col="event_version", created_col="created_at"
    )
    return (
        Event.objects.using(CATALOG)
        .filter(publication_status=Event.PublicationStatus.PUBLISHED)
        .exclude(status=Event.Status.SUPERSEDED)
        .annotate(last_modified=last_modified)
        .order_by("slug")
    )


def _event_entries(*, queryset, offset: int, limit: int) -> list[UrlFeedEntry]:
    """A slice of the public event URLs."""
    rows = queryset[offset : offset + limit]
    return [
        UrlFeedEntry(
            path=f"{EVENT_PATH_PREFIX}{row.slug}",
            kind=UrlFeedKind.EVENT,
            last_modified=row.last_modified,
        )
        for row in rows
    ]


def _city_queryset(*, now: datetime):
    """The queryset of the qualifying city URLs, in feed order.

    **The qualification is FR-27's threshold over the listing's own filters.** The
    window is `CITY_PAGE_QUALIFICATION_WINDOW` — a year — so a city that had a season
    last year still qualifies; the comparison is `> CITY_PAGE_EVENT_THRESHOLD`, so a
    city with exactly five does not qualify and one with exactly six does.

    **The staleness rule is in the SQL, and it is the same rule the listing uses.** The
    comparison `EventFit.event_version == Event.event_version` is between two joined
    columns, and Django expresses it as `event_version = ("ingestion_event".
    "event_version")` with an INNER JOIN — so the count and the listing are computed by
    **one** rule and cannot disagree. (This contradicts the docstrings in `city_read.py`
    and `event_fit/reads.py`, which say the comparison "cannot be expressed in SQL"; it
    can, and the measurement is in the review report.)

    **The `lastmod` is the max over the qualifying events' lastmods** — the same
    per-event expression the event side uses, aggregated.

    **The aggregation wraps the expression directly, not an intermediate annotation.**
    Annotating `event_last_modified` first and then taking `Max` of it would put the
    raw per-event expression into the `GROUP BY` — the `SELECT` list would carry a
    non-aggregate column, and PostgreSQL would group by it, splitting each city into
    one group per event and dropping every group below the threshold. `Max(expression)`
    keeps the expression inside the aggregate, so the `GROUP BY` stays on the city.

    **A city with no `city_ref` on its fit row is not a city page.** The backfill links
    venues to their canonical city, and a fit written before the backfill reached it has
    a null `city_ref` — so it has no page to list.
    """
    last_modified = _last_modified(
        pk_col="event_id",
        version_col="event__event_version",
        created_col="event__created_at",
    )
    since = now - CITY_PAGE_QUALIFICATION_WINDOW
    return (
        EventFit.objects.using(CATALOG)
        .filter(
            event__publication_status=Event.PublicationStatus.PUBLISHED,
            event__start_time_utc__gte=since,
            event_version=F("event__event_version"),
        )
        .exclude(event__status=Event.Status.SUPERSEDED)
        .exclude(city_ref__isnull=True)
        .values("city_ref_id", "city_ref__slug")
        .annotate(
            qualifying=Count("event_id"),
            last_modified=Max(last_modified),
        )
        .filter(qualifying__gt=CITY_PAGE_EVENT_THRESHOLD)
        .order_by("city_ref__slug")
    )


def _city_entries(*, queryset, offset: int, limit: int) -> list[UrlFeedEntry]:
    """A slice of the qualifying city URLs."""
    rows = queryset[offset : offset + limit]
    return [
        UrlFeedEntry(
            path=f"{CITY_PATH_PREFIX}{row['city_ref__slug']}",
            kind=UrlFeedKind.CITY,
            last_modified=row["last_modified"],
        )
        for row in rows
    ]


def list_url_feed(
    *, now: datetime, page: int = 1, page_size: int = DEFAULT_URL_FEED_PAGE_SIZE
) -> UrlFeedPage:
    """One page of the public URL feed, and the total size of the feed.

    **The feed is one flat list, and it is ordered by kind then path.** The events come
    first, then the cities, and each group is ordered by its own key. A single total
    order means a page boundary is unambiguous: two pages cannot overlap, and no URL is
    served twice or missed.

    **The page is a slice of the concatenation, not of each half.** The two halves are
    counted separately — the events' count and the cities' count — and then the page is
    taken from the *joined* list. Slicing each half separately and concatenating would
    serve up to `2 * page_size` URLs on a page and would leave a hole in the middle of
    the feed, and a sitemap built from that would have both: a page that overflows the
    50,000-URL ceiling and URLs that appear on no page at all.

    **Paging is bounded and past the end is empty, not an error.** A request for a page
    beyond the last one returns the same page shape with no items. A crawler walking off
    the end of a listing is doing something ordinary.

    **`page` and `page_size` are clamped, not refused.** The edge above this one — the
    HTTP boundary — refuses a bad request with a 422, because a caller that asks for
    10,000 URLs a page has made a mistake. This function is also called directly, by
    code that is not an HTTP request, and should not raise a validation error. The two
    layers answer the same question in the way that suits each: a bad request is
    refused, a bad internal call is bounded.
    """
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_URL_FEED_PAGE_SIZE))

    offset = (page - 1) * page_size
    end = offset + page_size

    # The events' count is needed to know where the cities begin, so it is read first.
    # **Two counts, then at most two slices** — and the slices are bounded by the page,
    # never by the size of the catalog.
    #
    # **The counts and the slices come from the same queryset.** Counting one rule and
    # slicing another would let the two disagree about how many events there are, and a
    # page boundary computed from a stale count would skip a URL or repeat one. So each
    # side builds its queryset once, counts it, and slices the same queryset.
    events = _event_queryset()
    cities = _city_queryset(now=now)
    event_total = events.count()
    city_total = cities.count()

    items: list[UrlFeedEntry] = []
    if offset < event_total:
        # The page starts inside the events. It may end inside them too, or run over into
        # the cities — and only the part that is inside the events is taken from them.
        take = min(end, event_total) - offset
        items.extend(_event_entries(queryset=events, offset=offset, limit=take))
    if end > event_total:
        # The page reaches into the cities. The city's own offset is measured from the
        # start of the cities, so the two halves join without a gap.
        city_offset = max(0, offset - event_total)
        take = end - max(offset, event_total)
        items.extend(_city_entries(queryset=cities, offset=city_offset, limit=take))

    total = event_total + city_total
    return UrlFeedPage(
        items=tuple(items),
        page=page,
        page_size=page_size,
        total=total,
        has_next=end < total,
    )


__all__ = [
    "DEFAULT_URL_FEED_PAGE_SIZE",
    "MAX_URL_FEED_PAGE_SIZE",
    "UrlFeedEntry",
    "UrlFeedKind",
    "UrlFeedPage",
    "list_url_feed",
]
