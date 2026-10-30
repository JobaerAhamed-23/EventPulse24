"""The Pulse Preview's wire shapes (AD-19).

The surface owns the contract, so the shapes live here and not in the service that
fills them. The data comes from `apps.ingestion.services.preview_read`, which owns the
query and hands over plain data.

**Two indicators, two fields, never one substituted for the other (AD-10).** `score` is
the **Event Fit** — the session-free 1–5 "this is a good fit for this city". `source_badge`
is the **Source Badge** (FR-23) — where the facts came from. They look nothing alike and
mean nothing alike, and a card that carried one where the other belonged would be a lie
about either.

**The times are UTC plus an explicit IANA zone** (AD-6). Display conversion is the
frontend's job; the server does not guess a locale.
"""

from datetime import datetime
from uuid import UUID

from ninja import Schema

from apps.ingestion.services.preview_read import PreviewCard

#: How the resolved city was chosen. The frontend needs this to say the right thing:
#: "Showing events near Brooklyn" (geo) versus "No preview available in Queens yet"
#: (query) versus the fallback (fallback).
CITY_SOURCE_GEO = "geo"
CITY_SOURCE_QUERY = "query"
CITY_SOURCE_FALLBACK = "fallback"


class PreviewCardOut(Schema):
    """One card in the Pulse Preview."""

    id: UUID
    slug: str
    title: str
    start_time_utc: datetime
    start_time_tz: str
    venue_name: str | None = None
    city: str
    #: The persisted Event Fit: 1–5, best is 5 (AD-10).
    score: int
    #: The persisted Why-this tag keys, in order. The labels are the frontend's.
    tags: list[str]
    source_name: str
    #: The Source Badge type (FR-23). The label and the glyph are the frontend's.
    source_badge: str

    @classmethod
    def from_preview_card(cls, card: PreviewCard) -> "PreviewCardOut":
        """Project the read interface's plain data onto the wire shape."""
        return cls(
            id=card.id,
            slug=card.slug,
            title=card.title,
            start_time_utc=card.start_time_utc,
            start_time_tz=card.start_time_tz,
            venue_name=card.venue_name,
            city=card.city,
            score=card.score,
            tags=list(card.tags),
            source_name=card.source_name,
            source_badge=card.source_badge,
        )


class PreviewOut(Schema):
    """The preview for a city.

    **`city` is always present**, even when `items` is empty: the empty case is a city
    the catalog does not cover, and the frontend shows "No preview available in {city}
    yet." — it needs the name to say it. It is never another city's name: an
    unsupported explicit city returns an empty preview carrying **that** city's name.
    """

    city: str
    #: `geo`, `query` or `fallback` — how the city was resolved.
    city_source: str
    items: list[PreviewCardOut]


class PreviewCitiesOut(Schema):
    """The supported cities, for the one-tap city picker."""

    cities: list[str]


__all__ = [
    "CITY_SOURCE_FALLBACK",
    "CITY_SOURCE_GEO",
    "CITY_SOURCE_QUERY",
    "PreviewCardOut",
    "PreviewCitiesOut",
    "PreviewOut",
]
