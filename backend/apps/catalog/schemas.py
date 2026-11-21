"""The public catalog's wire shapes (AD-19).

Request and response shapes are Pydantic schemas, never ad-hoc dicts. These live in the
`catalog` app because the surface owns the contract; the data comes from
`apps.ingestion.services.catalog_read`, which owns the query and hands over plain data.

Times are UTC plus an explicit IANA timezone: display conversion is the frontend's job
(AD-6). No raw source payload is exposed (AD-9) — the Event's stripped `description` and
the `ExtractedRecord.payload` never appear here.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.ingestion.services.catalog_read import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PublicEvent,
    PublicEventPage,
)
from apps.ingestion.services.city_read import (
    DEFAULT_CITY_PAGE_SIZE,
    MAX_CITY_PAGE_SIZE,
    CityPage,
    CityPageEvent,
)
from apps.ingestion.services.url_feed_read import (
    DEFAULT_URL_FEED_PAGE_SIZE,
    MAX_URL_FEED_PAGE_SIZE,
    UrlFeedPage,
)


class EventOut(Schema):
    """One public event.

    `id` is the stable identifier the API is keyed by; `slug` is the public page route's
    key (the spine's Ids convention: a page URL uses the slug, never the PK).
    """

    id: UUID
    slug: str
    title: str
    canonical_url: str
    start_time_utc: datetime
    start_time_tz: str
    end_time_utc: datetime | None = None
    venue_name: str | None = None
    venue_city: str | None = None
    status: str
    event_version: int
    source_name: str
    tz_review_pending: bool = False

    @classmethod
    def from_public_event(cls, event: PublicEvent) -> "EventOut":
        """Project the read interface's plain data onto the wire shape."""
        return cls(**vars(event))


class EventListOut(Schema):
    """One page of the public catalog, and what the frontend needs to page through it."""

    items: list[EventOut]
    page: int
    page_size: int
    total: int
    has_next: bool


class EventPage(Schema):
    """The list endpoint's query parameters.

    `city` matches the venue's city exactly, case-insensitively. The date bounds are
    inclusive and apply to the start time.
    """

    city: str | None = None
    starts_after: datetime | None = None
    starts_before: datetime | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class PublicEventPageOut(Schema):
    """One public event's page facts.

    **A separate shape from `EventOut`, deliberately.** `EventOut` is built by
    `cls(**vars(event))` over `PublicEvent`, so widening it would change the *catalog
    listing's* contract as well — and the listing's contract is not the public page's to
    change. The same reasoning that gave the Detail Screen its own shape applies here.

    **The fields are the JSON-LD's inputs (AD-12).** ARCHITECTURE-SPINE.md:166 requires
    the Schema.org `Event` JSON-LD to be *"emitted from the same data the page renders"*.
    So the page's payload carries the title, the description, both times, the zone, the
    venue's name and address parts, the canonical URL, the status, the sold-out flag and
    the version — one read, everything the page needs.

    **`schema_org` is the finished structured data**, projected from the fields above by
    `domain.schema_org` and carried on the DTO. The page embeds it verbatim: it does not
    build a second object, so it cannot disagree with the one it renders.

    **`event_version` is here because the revalidation work item needs it** to prove a
    cached page is current.
    """

    id: UUID
    slug: str
    title: str
    description: str
    canonical_url: str
    start_time_utc: datetime
    start_time_tz: str
    end_time_utc: datetime | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    venue_city: str | None = None
    venue_country_code: str | None = None
    status: str
    is_sold_out: bool
    event_version: int
    source_name: str
    tz_review_pending: bool = False
    #: The Schema.org `Event` object. A plain JSON object, not a typed shape: the page
    #: embeds it inside a `<script type="application/ld+json">` block, and a typed model
    #: would only add a reshape step between the projection and the wire.
    schema_org: dict[str, object]

    @classmethod
    def from_public_event_page(cls, event: PublicEventPage) -> "PublicEventPageOut":
        """Project the read interface's plain data onto the wire shape."""
        return cls(**vars(event))


class CityPageEventOut(Schema):
    """One event on a city page.

    **The score and the tags are the persisted Event Fit, served as stored** (AD-10).
    The page shows what the fit says, not what a fresh computation would say — so a
    score of 1 on an event that would now score 5 is shown as 1, and the reason is that
    the fit has not been recomputed yet.
    """

    id: UUID
    slug: str
    title: str
    description: str
    canonical_url: str
    start_time_utc: datetime
    start_time_tz: str
    end_time_utc: datetime | None = None
    venue_name: str | None = None
    city: str
    score: int
    tags: list[str]
    status: str
    is_sold_out: bool
    event_version: int
    tz_review_pending: bool = False

    @classmethod
    def from_city_page_event(cls, event: CityPageEvent) -> "CityPageEventOut":
        """Project the read interface's plain data onto the wire shape."""
        return cls(
            id=event.id,
            slug=event.slug,
            title=event.title,
            description=event.description,
            canonical_url=event.canonical_url,
            start_time_utc=event.start_time_utc,
            start_time_tz=event.start_time_tz,
            end_time_utc=event.end_time_utc,
            venue_name=event.venue_name,
            city=event.city,
            score=event.score,
            tags=list(event.tags),
            status=event.status,
            is_sold_out=event.is_sold_out,
            event_version=event.event_version,
            tz_review_pending=event.tz_review_pending,
        )


class CityPageOut(Schema):
    """One city page: the city's identity, its events, and whether it is published.

    **`is_published` is FR-27's threshold, computed by the listing's own filters.** A
    city with more than the threshold's events is published; a city with fewer is not,
    and the frontend renders "coming soon" rather than a listing. **The city page
    degrades; it does not 404** — a URL that vanishes after ranking throws away every
    bit of ranking it earned.

    **`event_count` is the qualifying count**, not the number of items on this page. It
    is the number the threshold was decided on. `has_next` is measured against the
    **listing's** total instead — the two counts answer different questions, and a city
    between seasons has the first without the second.

    **`city_collection_status` is a different question from `is_published`.** The
    threshold asks whether the city has enough events on record to deserve a page; the
    status asks whether our collection of it is working. **The threshold decides whether
    the page shows a listing; the status only ever adds a sentence to the sparse
    state**, and never removes the "coming soon" copy — which is true of the threshold
    whatever the collection is doing.
    """

    slug: str
    name: str
    country_code: str
    region: str
    is_published: bool
    event_count: int
    items: list[CityPageEventOut]
    page: int
    page_size: int
    has_next: bool
    #: How the collection of this city is going — the `CityProvisioning.Status` value, or
    #: `""` when the city was never provisioned. **A fact about a place, not about a
    #: reader**, so it is cacheable with the rest of the response (AD-12).
    city_collection_status: str = ""

    @classmethod
    def from_city_page(cls, page: CityPage) -> "CityPageOut":
        """Project the read interface's plain data onto the wire shape."""
        return cls(
            slug=page.slug,
            name=page.name,
            country_code=page.country_code,
            region=page.region,
            is_published=page.is_published,
            event_count=page.event_count,
            items=[CityPageEventOut.from_city_page_event(item) for item in page.items],
            page=page.page,
            page_size=page.page_size,
            has_next=page.has_next,
            city_collection_status=page.city_collection_status,
        )


class CityPageQuery(Schema):
    """The city page endpoint's query parameters.

    **`page` and `page_size` are bounded at the edge, and the edge is a refusal.**
    A page below one or a page size above the ceiling is a **422**, not a silent
    adjustment — a caller that asks for 10,000 events a page has made a mistake, and
    quietly handing it 50 would hide the mistake from it.

    The service below the surface **clamps** rather than refuses, because it is also
    called directly by code that is not an HTTP request and should not raise a
    validation error. The two layers answer the same question in the way that suits
    each: a bad request is refused, a bad internal call is bounded.
    """

    page: int = Field(1, ge=1)
    page_size: int = Field(DEFAULT_CITY_PAGE_SIZE, ge=1, le=MAX_CITY_PAGE_SIZE)


class UrlFeedEntryOut(Schema):
    """One publicly addressable URL, and when it last changed.

    **`path` is a path, not a URL.** The origin is the frontend's business — the sitemap
    resolves each path against the site's own public origin — so the backend hands over
    a path and never an absolute URL. That keeps the backend free of any knowledge of
    how the frontend is deployed, and it keeps one origin in one place.

    **`kind` is a closed vocabulary.** `event` and `city` are the two kinds of public
    page the site serves, and a third kind would have to be declared here too — a kind
    that exists on only one side of the wire is a kind nobody can serve.

    **`last_modified` is the page's real last change.** It is derived from the event's
    state history, not from a timestamp of convenience, so a crawler is told the truth
    about what moved.
    """

    path: str
    kind: Literal["event", "city"]
    last_modified: datetime


class UrlFeedOut(Schema):
    """One page of the public URL feed, and what the caller needs to page through it.

    **`total` is the size of the whole feed**, so a caller can decide how many children
    its sitemap index needs before it fetches the first child — and that is exactly what
    the sitemap's index route does.

    **`has_next` is measured against `total`**, so a caller knows when to stop without
    fetching a page that would be empty.
    """

    items: list[UrlFeedEntryOut]
    page: int
    page_size: int
    total: int
    has_next: bool

    @classmethod
    def from_url_feed_page(cls, page: UrlFeedPage) -> "UrlFeedOut":
        """Project the read interface's plain data onto the wire shape."""
        return cls(
            items=[
                UrlFeedEntryOut(
                    path=item.path,
                    kind=item.kind,
                    last_modified=item.last_modified,
                )
                for item in page.items
            ],
            page=page.page,
            page_size=page.page_size,
            total=page.total,
            has_next=page.has_next,
        )


class UrlFeedQuery(Schema):
    """The URL feed endpoint's query parameters.

    **Bounded at the edge, and the edge is a refusal** — the same rule the city page's
    query follows, for the same reason: this read grows with the catalog, and a caller
    that asks for a million URLs at once has made a mistake. The service below the
    surface clamps rather than refuses, because it is also called directly by code that
    is not an HTTP request.
    """

    page: int = Field(1, ge=1)
    page_size: int = Field(DEFAULT_URL_FEED_PAGE_SIZE, ge=1, le=MAX_URL_FEED_PAGE_SIZE)
