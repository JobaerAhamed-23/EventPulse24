"""The public catalog's read endpoints (AD-12, AD-19).

`GET /api/catalog/events` lists the upcoming published events; `GET /api/catalog/events/{id}`
returns one; `GET /api/catalog/events/by-slug/{slug}` returns the page facts for a public
page (FR-26); `GET /api/catalog/cities/by-slug/{slug}` returns the page facts for a city
page (FR-27); `GET /api/catalog/url-feed` lists every publicly addressable URL, with the
time each last really changed. All of them work with no session and set no cookie: the
public surface never depends on a session (AD-12), so the responses stay cacheable.

**Two reads by key, two different questions.** `/events/{event_id}` is keyed on a UUID
and answers *"what may a person browse?"* — its rule is that an event which has already
started reads as not found, which is right for a digest. `/events/by-slug/{slug}` is keyed
on the slug and answers *"what is this URL?"* — and there **a past event still resolves**,
because a page that 404s the moment the doors open throws away every bit of ranking it
spent months earning. They are separate endpoints and separate read functions, not one
read with a flag: the two meanings are load-bearing, and a flag would put them one
parameter apart.

**The city page answers the same kind of question — "what is this URL?" — with the same
consequence.** A city page for a city below the publishing threshold is not a 404: it
comes back with `is_published=false` and no events, and the frontend shows "coming soon".
The same reasoning applies: a city page that 404s once its events have passed would throw
away the ranking it spent months earning.

**The URL feed is the third of that kind.** It answers *"which URLs does this site
serve?"* — the sitemap's question — and it is fed by the same rules the two page reads
apply, so a URL in the sitemap is a URL that serves and a URL that serves is a URL in the
sitemap. A sitemap that lists a 404 is a crawl-budget leak.

The data comes from `apps.ingestion.services.catalog_read`,
`apps.ingestion.services.city_read` and `apps.ingestion.services.url_feed_read`, the
published read interfaces.
This module never imports `apps.ingestion.models` (import contract `models-ingestion`), and
it never writes: the catalog is read-only here, and `ingestion` is the sole writer (AD-4,
AD-16).
"""

from uuid import UUID

from django.http import HttpResponse
from django.utils import timezone
from ninja import Query, Router, Status

from apps.catalog.schemas import (
    CityPageOut,
    CityPageQuery,
    EventListOut,
    EventOut,
    EventPage,
    PublicEventPageOut,
    UrlFeedOut,
    UrlFeedQuery,
)
from apps.ingestion.services.catalog_read import (
    EventNotFoundError,
    get_public_event,
    get_public_event_by_slug,
    list_public_events,
)
from apps.ingestion.services.city_read import CityNotFoundError, get_city_page
from apps.ingestion.services.url_feed_read import list_url_feed
from shared.constants import PUBLIC_PAGE_CACHE_CONTROL, PUBLIC_PAGE_VARY
from shared.errors import ErrorOut

router = Router(tags=["catalog"])

# A module-level singleton, so the query-parameter model is declared once. `Query(...)` is
# what makes `EventPage` a set of query parameters: without it a schema-typed argument
# becomes a request *body*, and the query string would be ignored (B008).
EVENT_PAGE_QUERY = Query(...)
CITY_PAGE_QUERY = Query(...)
URL_FEED_QUERY = Query(...)


def _cacheable(response: HttpResponse) -> HttpResponse:
    """Mark a response as a public, cacheable, per-URL response.

    **`Vary` carries nothing session-related.** A response that varies on the cookie is
    not cacheable, and — worse — a shared cache that stores one variant under a key that
    ignores the cookie would serve one visitor's response to another. The public page sets
    no cookie and reads no session, so the response is identical for everyone and the
    cache key is the URL.

    The response object is the one django-ninja injects into a view parameter annotated
    as `HttpResponse` — it is the *same* object ninja fills with the body afterwards, so
    the headers set here survive.
    """
    response["Cache-Control"] = PUBLIC_PAGE_CACHE_CONTROL
    response["Vary"] = PUBLIC_PAGE_VARY
    return response


@router.get(
    "/events",
    response={200: EventListOut},
    summary="List upcoming public events",
    description=(
        "Published, non-superseded events that have not started yet, soonest first. "
        "Optional city and date-range filters. No session is used and none is set."
    ),
)
def list_events(request, filters: EventPage = EVENT_PAGE_QUERY):
    """The public event list. `filters` carries the query parameters."""
    items, total = list_public_events(
        now=timezone.now(),
        city=filters.city,
        starts_after=filters.starts_after,
        starts_before=filters.starts_before,
        page=filters.page,
        page_size=filters.page_size,
    )
    page = filters.page
    page_size = filters.page_size
    return EventListOut(
        items=[EventOut.from_public_event(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        has_next=page * page_size < total,
    )


@router.get(
    "/events/{event_id}",
    response={200: EventOut, 404: ErrorOut},
    summary="Get one public event",
    description=(
        "One published event by id. An event that is not public — or that has already "
        "started — reads as not found, the same set the list shows. "
        "No session is used and none is set."
    ),
)
def get_event(request, event_id: UUID):
    """One public event. Raises `EventNotFoundError` (a 404) when there isn't one."""
    return EventOut.from_public_event(get_public_event(event_id=event_id, now=timezone.now()))


@router.get(
    "/events/by-slug/{slug}",
    response={200: PublicEventPageOut, 404: ErrorOut},
    summary="Get one public event page, by slug",
    description=(
        "One published event by slug — the read behind `/events/{slug}` (FR-26). "
        "Unlike the listing's read, an event that has already happened still resolves: "
        "the page stays addressable and stays indexed. An event that is not public "
        "reads as not found. No session is used and none is set."
    ),
)
def get_event_page(request, response: HttpResponse, slug: str):
    """One public event's page facts.

    **The not-found is handled here rather than left to the exception handler.** An
    unknown slug is a clean, cacheable answer — a crawler that asks for a URL that does
    not exist should not hammer the origin — but django-ninja's exception path builds a
    *fresh* response, which would drop the cache headers set on the injected response.
    Catching it here keeps them on the 404.
    """
    _cacheable(response)
    try:
        page = get_public_event_by_slug(slug=slug)
    except EventNotFoundError as exc:
        return Status(
            404,
            ErrorOut(code=exc.code, message=exc.message, details=exc.details),
        )
    return PublicEventPageOut.from_public_event_page(page)


@router.get(
    "/cities/by-slug/{slug}",
    response={200: CityPageOut, 404: ErrorOut},
    summary="Get one city page, by slug",
    description=(
        "One city page — the read behind `/events-in-{city}` (FR-27). A paged listing "
        "of the city's upcoming public events, best Event Fit first, each with the "
        "persisted fit's score and tags. A city below the publishing threshold comes "
        "back with `is_published=false` and no events, which the page renders as "
        "'coming soon' — it does not 404, because a URL that vanishes after ranking "
        "throws away every bit of ranking it earned. An unknown slug is a 404. "
        "No session is used and none is set."
    ),
)
def get_city(request, response: HttpResponse, slug: str, params: CityPageQuery = CITY_PAGE_QUERY):
    """One city page's facts.

    **The not-found is handled here rather than left to the exception handler**, for the
    same reason the event page's 404 is: the exception path builds a *fresh* response,
    which would drop the cache headers set on the injected response. Catching it here
    keeps them on the 404.
    """
    _cacheable(response)
    try:
        page = get_city_page(
            slug=slug,
            now=timezone.now(),
            page=params.page,
            page_size=params.page_size,
        )
    except CityNotFoundError as exc:
        return Status(
            404,
            ErrorOut(code=exc.code, message=exc.message, details=exc.details),
        )
    return CityPageOut.from_city_page(page)


@router.get(
    "/url-feed",
    response={200: UrlFeedOut},
    summary="List the site's publicly addressable URLs",
    description=(
        "One page of the public URL feed: every publicly addressable page — a public "
        "event's page and a qualifying city's page — with the time each last really "
        "changed. This is the sitemap's source, so it lists exactly the URLs the site "
        "serves: no unpublished event, no superseded event, and no city below the "
        "publishing threshold. "
        "The read is paged and bounded, because it grows with the catalog. "
        "No session is used and none is set."
    ),
)
def get_url_feed(request, response: HttpResponse, params: UrlFeedQuery = URL_FEED_QUERY):
    """One page of the public URL feed.

    **Cacheable, exactly as the two page reads are.** The response is identical for
    everyone — no session is read and none is set — so the cache key is the URL, and
    `Vary` carries nothing session-related.
    """
    _cacheable(response)
    feed = list_url_feed(
        now=timezone.now(),
        page=params.page,
        page_size=params.page_size,
    )
    return UrlFeedOut.from_url_feed_page(feed)
