"""Public Event slugs (spine Ids convention; design D15, pipeline design D18).

`<title>-<venue-local date>-<id tail>`: minted once at creation and never changed, so a
retitled Event keeps its URL. The UUIDv7's random tail makes a collision practically
impossible; the caller retries once with the long tail if the unique constraint still trips.
"""

from uuid import UUID

from django.utils.text import slugify

TITLE_PART_MAX = 80
SHORT_TAIL = 6
LONG_TAIL = 12


def mint_slug(title: str, start_time_local: str, event_id: UUID, *, long: bool = False) -> str:
    """An ASCII slug; titles that slugify to nothing (non-Latin scripts) become "event"."""
    title_part = slugify(title)[:TITLE_PART_MAX].strip("-") or "event"
    tail = event_id.hex[-(LONG_TAIL if long else SHORT_TAIL) :]
    return f"{title_part}-{start_time_local[:10]}-{tail}"
