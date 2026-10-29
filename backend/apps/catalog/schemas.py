"""The public catalog's wire shapes (AD-19).

Request and response shapes are Pydantic schemas, never ad-hoc dicts. These live in the
`catalog` app because the surface owns the contract; the data comes from
`apps.ingestion.services.catalog_read`, which owns the query and hands over plain data.

Times are UTC plus an explicit IANA timezone: display conversion is the frontend's job
(AD-6). No raw source payload is exposed (AD-9) — the Event's stripped `description` and
the `ExtractedRecord.payload` never appear here.
"""

from datetime import datetime
from uuid import UUID

from ninja import Field, Schema

from apps.ingestion.services.catalog_read import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PublicEvent,
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
