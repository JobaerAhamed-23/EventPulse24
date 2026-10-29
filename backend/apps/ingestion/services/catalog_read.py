"""The published read interface over the catalog (AD-2, AD-4, AD-12).

The `catalog` app reads events through here, never through `apps.ingestion.models`
(import contract `models-ingestion`). This module owns the *query*; the wire shapes live in
`apps/catalog/schemas.py`, because the surface owns the contract (AD-19).

The interface hands over plain data — a frozen dataclass, not a model instance — so the
calling app never holds a reference to `apps.ingestion.models` and the wall holds without
either side knowing the other's models.

Only published, non-superseded, upcoming events are visible. An `in_review` event is not
digest-eligible and not publicly listed (AD-6, AD-8), and a superseded Event is terminal:
the live one that replaced it is listed instead (D7). A `tz_review_pending` event is
published and *is* listed, carrying the flag so the frontend can mark its time as
approximated.

`now` is an explicit parameter, like every other command here: no time-freezing library, and
each boundary is testable at the exact second.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import QuerySet

from apps.ingestion.models import Event
from domain.errors import NotFoundError
from shared.db import CATALOG

# A page of public events. The cap keeps one request from asking for the whole catalog.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class EventNotFoundError(NotFoundError):
    """The requested event isn't in the public catalog (or was never published)."""

    default_message = "We couldn't find that event."


@dataclass(frozen=True)
class PublicEvent:
    """One public event as plain data.

    Deliberately not the model: the caller gets a value it can read without importing
    `apps.ingestion.models`. The fields are the ones the public catalog publishes.
    """

    id: UUID
    slug: str
    title: str
    canonical_url: str
    start_time_utc: datetime
    start_time_tz: str
    end_time_utc: datetime | None
    venue_name: str | None
    venue_city: str | None
    status: str
    event_version: int
    source_name: str
    tz_review_pending: bool


def _public_events() -> QuerySet:
    """Published, not superseded. The venue and source come along in the same query."""
    return (
        Event.objects.using(CATALOG)
        .filter(publication_status=Event.PublicationStatus.PUBLISHED)
        .exclude(status=Event.Status.SUPERSEDED)
        .select_related("venue", "source")
    )


def _to_public_event(event: Event) -> PublicEvent:
    venue = event.venue
    return PublicEvent(
        id=event.id,
        slug=event.slug,
        title=event.title,
        canonical_url=event.canonical_url,
        start_time_utc=event.start_time_utc,
        start_time_tz=event.start_time_tz,
        end_time_utc=event.end_time_utc,
        venue_name=venue.name if venue else None,
        venue_city=venue.city if venue else None,
        status=event.status,
        event_version=event.event_version,
        source_name=event.source.name,
        tz_review_pending=event.tz_review_pending,
    )


def list_public_events(
    *,
    now: datetime,
    city: str | None = None,
    starts_after: datetime | None = None,
    starts_before: datetime | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[PublicEvent], int]:
    """The upcoming public events, soonest start first, and the total count of that set.

    `now` bounds the list to events that have not started yet. `city` matches the venue's
    city exactly, case-insensitively; an event without a venue has no city and never
    matches. `starts_after` and `starts_before` are inclusive bounds on the start time.

    Ordering is `start_time_utc` then `id`: the id tiebreak makes the order total, so two
    events sharing a start time can't fall on both pages (the UUIDv7 is time-ordered, so
    the tiebreak is stable).
    """
    queryset = _public_events().filter(start_time_utc__gte=now)
    if city:
        queryset = queryset.filter(venue__city__iexact=city)
    if starts_after is not None:
        queryset = queryset.filter(start_time_utc__gte=starts_after)
    if starts_before is not None:
        queryset = queryset.filter(start_time_utc__lte=starts_before)

    queryset = queryset.order_by("start_time_utc", "id")
    total = queryset.count()
    page = max(page, 1)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    offset = (page - 1) * page_size
    items = [_to_public_event(event) for event in queryset[offset : offset + page_size]]
    return items, total


def get_public_event(*, event_id: UUID, now: datetime | None = None) -> PublicEvent:
    """One public event by id.

    An event that isn't public (unpublished, `in_review`) or that was superseded is not
    found: the public catalog has one truth, and a hidden event reads as absent.

    **`now` bounds by "has not started yet".** It is the rule the module's own docstring
    states — "Only published, non-superseded, **upcoming** events are visible" — and it is
    the set a *save* may draw from: you take an event into your calendar while it is still
    ahead of you. Pass `now` to enforce it.

    Passing `now=None` skips the bound, and that is deliberate: a record of something the
    user already saved has to stay readable after the event has started. The user's own
    calendar does not un-save an event because it began.
    """
    queryset = _public_events()
    if now is not None:
        queryset = queryset.filter(start_time_utc__gte=now)
    try:
        event = queryset.get(pk=event_id)
    except Event.DoesNotExist:
        raise EventNotFoundError(details={"event_id": str(event_id)}) from None
    return _to_public_event(event)


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "EventNotFoundError",
    "PublicEvent",
    "get_public_event",
    "list_public_events",
]
