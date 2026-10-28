"""The public catalog's read endpoints (AD-12, AD-19).

`GET /api/catalog/events` lists the upcoming published events; `GET /api/catalog/events/{id}`
returns one. Both work with no session and set no cookie: the public surface never depends
on a session (AD-12), so the responses stay cacheable.

The data comes from `apps.ingestion.services.catalog_read`, the published read interface.
This module never imports `apps.ingestion.models` (import contract `models-ingestion`), and
it never writes: the catalog is read-only here, and `ingestion` is the sole writer (AD-4,
AD-16).
"""

from uuid import UUID

from django.utils import timezone
from ninja import Query, Router

from apps.catalog.schemas import EventListOut, EventOut, EventPage
from apps.ingestion.services.catalog_read import get_public_event, list_public_events
from shared.errors import ErrorOut

router = Router(tags=["catalog"])

# A module-level singleton, so the query-parameter model is declared once. `Query(...)` is
# what makes `EventPage` a set of query parameters: without it a schema-typed argument
# becomes a request *body*, and the query string would be ignored (B008).
EVENT_PAGE_QUERY = Query(...)


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
        "One published event by id. An event that is not public reads as not found. "
        "No session is used and none is set."
    ),
)
def get_event(request, event_id: UUID):
    """One public event. Raises `EventNotFoundError` (a 404) when there isn't one."""
    return EventOut.from_public_event(get_public_event(event_id=event_id))
