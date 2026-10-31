"""The Pulse Preview's published read: the cards for a city, and the supported cities (FR-2).

**Why this module exists.** The Pulse Preview is a *public* surface (AD-12), so it lives
in `apps/catalog` — and `apps.catalog` may not import `apps.ingestion.models` (import
contract `models-ingestion`). The Event Fit read, `apps.ingestion.event_fit.reads`,
imports that model directly, so `apps.catalog` cannot reach the Event Fit through it
either. The work item asks that "the endpoint reads `catalog` only through `ingestion`'s
published read interface", and this module is that interface: it lives *inside*
`apps.ingestion`, so the contract holds, and it hands over plain data.

**What it adds to the fit read.** The Event Fit read carries the score, the tags and the
event's public facts. It does **not** carry the Source Badge inputs, because the badge is
a function of the *source*, and the fit read deliberately does not join the source — a
fit is about an event's fit, not about where it came from. This module joins it and
derives the badge type.

**The Source Badge is a type, not a label and not an icon.** `EXPERIENCE.md §4` owns the
label ("Official", "Community", "Listing site") and the glyph; the server states the
fact. The same rule the Event Fit tags follow: the server states facts, the client
speaks the user's language.

**`user_imported` is not producible here.** A user-imported event is a *personal* event,
and FR-2 puts "personal event surfacing in Pulse Preview" out of scope. The UX spec
names five badge types; this surface can only ever produce four of them, and the
mapping says so rather than pretending otherwise.

**The supported cities are derived, not configured.** A hard-coded city list is a list
that goes stale the moment a source in a new city is ingested, and the picker would then
offer a city the preview cannot fill. The supported set is exactly the set of cities
that have at least one upcoming, published, non-superseded event **with a current Event
Fit** — because a city with events but no fits is a city the preview cannot serve.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.ingestion.event_fit.reads import (
    DEFAULT_PREVIEW_SIZE,
    list_event_fit_for_city,
)
from apps.ingestion.models import Event, EventFit, Source
from apps.ingestion.services.source_badges import source_badge_for_type
from shared.db import CATALOG

# The Source Badge types live in `source_badges`, because two reads on the catalog side
# need the mapping and this module imports the Event Fit — which `catalog_read` must not
# pull in, since `personalization` imports `catalog_read` and the `event-fit-separation`
# contract exists to keep the Event Fit away from `personalization` (AD-10).
#
# **They are not re-exported here.** One rule, one home: a name exported from two
# modules is two homes, and a reader has to know which one is current. This module was
# their home before the split; `source_badges` is it now.


@dataclass(frozen=True)
class PreviewCard:
    """One card in the Pulse Preview: the event's public facts, its fit, and its badge.

    Plain data — not a model — so the calling app never holds a reference to
    `apps.ingestion.models` and the wall holds without either side knowing the other's
    models.
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
    source_name: str
    source_badge: str


@dataclass(frozen=True)
class PreviewCities:
    """The supported cities, and whether one of them is supported."""

    cities: tuple[str, ...]

    def supports(self, city: str) -> bool:
        """Whether the preview can serve `city`.

        The comparison is case-insensitive, because the city arrives from a query
        parameter or a header — both of which a person types — and "brooklyn" and
        "Brooklyn" are the same city. The *spelling* that comes back is the catalog's.
        """
        wanted = city.strip().casefold()
        return any(name.casefold() == wanted for name in self.cities)


def source_badge_for(source: Source) -> str:
    """The Source Badge type for a source.

    A thin wrapper over `source_badges.source_badge_for_type`, for the callers that hold
    a `Source`. The rule itself lives in `source_badges` so that the digest's candidate
    read can ask the same question without importing the Event Fit.
    """
    return source_badge_for_type(
        source_type=source.source_type,
        acquisition_method=source.acquisition_method,
    )


def list_supported_cities(*, now: datetime) -> PreviewCities:
    """The cities the preview can serve, alphabetically.

    **A city is supported when it has at least one upcoming, published, non-superseded
    event with a *current* Event Fit.** The "current" half matters: a fit whose
    `event_version` no longer matches its event describes an event that no longer
    exists, and serving that city would offer a preview that is empty for a reason the
    caller cannot see.

    **Alphabetical, because a picker whose order changes between requests is a picker
    nobody can find anything in.**

    **The sort is done in Python, once, and the database is not asked to sort at all.**
    A database's `ORDER BY` on text is a **locale collation** — `en_US.UTF-8` ignores
    punctuation at the primary level and orders case in a locale-specific way — so two
    deployments with different locales would list the same cities in a different order,
    and the picker would change shape between environments. `str.casefold` is the same
    everywhere, so it is the sort that decides. Leaving the database order off also
    means the result cannot depend on the order the rows happened to come back in.
    """
    rows = (
        EventFit.objects.using(CATALOG)
        .filter(event__publication_status=Event.PublicationStatus.PUBLISHED)
        .exclude(event__status=Event.Status.SUPERSEDED)
        .filter(event__start_time_utc__gte=now)
        .select_related("event")
    )

    names: list[str] = []
    for row in rows:
        if row.event_version != row.event.event_version:
            continue  # stale: the Event changed after this fit was computed
        name = row.city.strip()
        if name and name.casefold() not in {existing.casefold() for existing in names}:
            names.append(name)

    return PreviewCities(cities=tuple(sorted(names, key=str.casefold)))


def list_preview_cards(
    *,
    city: str,
    now: datetime,
    limit: int = DEFAULT_PREVIEW_SIZE,
) -> list[PreviewCard]:
    """The preview's cards for `city`, best Event Fit first.

    The cards are the Event Fit read's rows **plus** the Source Badge inputs. The fit
    read decides which events appear and in what order; this module only adds the
    badge and projects the result onto the wire shape.

    **An empty list is a real answer.** An unsupported city gets one, and the caller
    shows "No preview available in {city} yet." — it never shows another city's events
    under the requested name.
    """
    entries = list_event_fit_for_city(city=city, now=now, limit=limit)
    if not entries:
        return []

    event_ids = [entry.id for entry in entries]
    sources = _sources_for(event_ids)

    cards: list[PreviewCard] = []
    for entry in entries:
        source = sources.get(entry.id)
        if source is None:
            # Every Event has a Source (a non-null FK), so this cannot happen. It is
            # handled rather than assumed because a card without a badge would be a
            # card that violates FR-23 ("a Pulse Card always shows a Source Badge"),
            # and a crash here would take the whole preview down over one missing row.
            continue
        cards.append(
            PreviewCard(
                id=entry.id,
                slug=entry.slug,
                title=entry.title,
                start_time_utc=entry.start_time_utc,
                start_time_tz=entry.start_time_tz,
                venue_name=entry.venue_name,
                city=entry.city,
                score=entry.score,
                tags=entry.tags,
                source_name=source.name,
                source_badge=source_badge_for(source),
            )
        )
    return cards


def _sources_for(event_ids: list[UUID]) -> dict[UUID, Source]:
    """The source of each of these events, by event id.

    One query, keyed by event id — the preview shows three cards, and three queries
    would be three round-trips for three rows.
    """
    if not event_ids:
        return {}
    rows = Event.objects.using(CATALOG).filter(pk__in=event_ids).select_related("source")
    return {row.pk: row.source for row in rows}


__all__ = [
    "PreviewCard",
    "PreviewCities",
    "list_preview_cards",
    "list_supported_cities",
    "source_badge_for",
]
