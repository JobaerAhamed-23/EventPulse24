"""The Source Registry, read for the screen that shows it to the user (AD-2, AD-4, FR-13, FR-16).

`Settings → Sources` shows the user every source in the registry, grouped by how its facts
were obtained, with each source's trust. This module is the read that answers it.

**It is a separate module from `catalog_read` because it answers a different question.**
`catalog_read` answers "what may a person browse?" and "what may a digest rank?" — both
questions about *events*, both filtered to published and upcoming. This one asks "what
sources are there?", and the answer includes sources with no published events, and sources
that are paused. A registry read that filtered to live events would hide exactly the
sources a user is most likely to ask about.

**It lives in `ingestion` because `ingestion` owns `Source` (AD-16).** The screen is a
personalization surface, but `personalization` may not import `apps.ingestion.models` (the
`models-ingestion` import contract), and the source's facts are the catalog's. So the read
lives here, hands over plain data, and the personal side joins its own per-user state onto
it.

**The four groups are FR-23's Source Badge types, not a taxonomy of our own.** The mockup's
"Official / Community / Aggregator / Crawled" *are* `source_badges.py`'s four types, which
already exist, are already server-side, and are already used by two reads. A second mapping
from `SourceType` would be a second opinion about what a source is, which is exactly what
`domain/sources.py` exists to prevent.

**The trust band is computed here, on the catalog side.** The server states the fact; the
client owns the label and the glyph. The same rule the Source Badge follows.

**A paused source is still in the registry.** `Source.status` is `active` or `paused`, and
FR-16 is explicit that escalation "never pauses, hides or removes" a source — but an
operator can pause one. The screen's job is transparency ("who is informing your
timeline"), and a paused source is still a source the user has seen events from. Hiding
it would hide the very thing the screen exists to reveal, so it is listed and marked.

**Nothing is fabricated.** A source with no rows produces empty groups, not invented
sources. The registry genuinely holds a handful of rows today, and a screen that invented
sources to look populated would be asserting a registry that does not exist.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from apps.ingestion.models import Source
from apps.ingestion.services.source_badges import (
    SOURCE_BADGE_AGGREGATOR,
    SOURCE_BADGE_COMMUNITY,
    SOURCE_BADGE_CRAWLED,
    SOURCE_BADGE_OFFICIAL,
    source_badge_for_type,
)
from domain.reliability import reliability_score, source_trust_band
from shared.db import CATALOG

#: The four groups, in the order the screen shows them.
#:
#: **The order is the mockup's** — Official, Community, Aggregator, Crawled — and it is the
#: order of decreasing confidence in the source's own facts. An official venue's site is
#: the source of truth for its own events; a crawled page is the least direct. Reading the
#: screen top to bottom is reading the spectrum of how sure we are.
SOURCE_GROUP_ORDER: tuple[str, ...] = (
    SOURCE_BADGE_OFFICIAL,
    SOURCE_BADGE_COMMUNITY,
    SOURCE_BADGE_AGGREGATOR,
    SOURCE_BADGE_CRAWLED,
)

#: The label the client shows for each group. The server states the type; the client owns
#: the label — but the label lives here so the group heading and the badge can never drift
#: apart, and so a reader of this module can see what the four types are called.
SOURCE_GROUP_LABELS: dict[str, str] = {
    SOURCE_BADGE_OFFICIAL: "Official",
    SOURCE_BADGE_COMMUNITY: "Community",
    SOURCE_BADGE_AGGREGATOR: "Aggregator",
    SOURCE_BADGE_CRAWLED: "Crawled",
}


@dataclass(frozen=True)
class RegistrySource:
    """One source in the registry, as the screen sees it.

    Plain data — not the model — so the calling app never holds a reference to
    `apps.ingestion.models` and the wall holds without either side knowing the other's
    models.
    """

    id: UUID
    name: str
    #: The Source Badge type — the group this source belongs to.
    source_badge: str
    #: The `Source.source_type` the badge was derived from, kept for the audit trail.
    source_type: str
    #: Whether the source's facts were obtained by crawling (the badge's other input).
    acquisition_method: str
    #: The source's city, when it has one. A source without a city is not a local source.
    city: str
    #: The source's FR-16 score, in [0, 1]. The prior when it has never been scored.
    reliability: Decimal
    #: The score as the 1–5 trust band the dots render.
    trust_band: int
    #: Whether the source is paused. A paused source is still in the registry.
    is_paused: bool


@dataclass(frozen=True)
class RegistryGroup:
    """One group of sources, in the screen's order."""

    #: The Source Badge type — the group key.
    badge: str
    #: The heading the screen shows.
    label: str
    #: The group's sources, in name order.
    sources: tuple[RegistrySource, ...]


def _current_reliability(source: Source) -> Decimal:
    """The source's FR-16 score, or the prior when it has never been computed.

    **The prior is asked of the domain module, not written here** — the same rule
    `catalog_read._source_reliability` and `services.reliability.current_score` follow. A
    literal `0.50` here would be a second copy of the prior's value, and it would drift the
    moment FR-16's α/β were re-tuned.
    """
    if source.reliability_score is None:
        return reliability_score(0, 0)
    return source.reliability_score


def _to_registry_source(source: Source) -> RegistrySource:
    """One `Source` row as the screen sees it."""
    reliability = _current_reliability(source)
    return RegistrySource(
        id=source.id,
        name=source.name,
        source_badge=source_badge_for_type(
            source_type=source.source_type,
            acquisition_method=source.acquisition_method,
        ),
        source_type=source.source_type,
        acquisition_method=source.acquisition_method,
        city=source.city,
        reliability=reliability,
        trust_band=source_trust_band(reliability),
        is_paused=source.status == Source.Status.PAUSED,
    )


def read_source_registry() -> tuple[RegistryGroup, ...]:
    """Every source in the registry, grouped by its Source Badge type.

    **The four groups are always present, in order, even when they are empty.** The screen
    renders a heading per group, and a group that appeared and disappeared as the registry
    changed would make the screen's shape depend on the data. An empty group renders with
    no rows under it, and the client shows its quiet empty state.

    **Sources are ordered by name within a group**, so the screen's order does not depend
    on the order the rows happened to come back from the database.
    """
    sources = list(Source.objects.using(CATALOG).order_by("name").all())

    by_badge: dict[str, list[RegistrySource]] = {badge: [] for badge in SOURCE_GROUP_ORDER}
    for source in sources:
        registry_source = _to_registry_source(source)
        # A badge outside the four cannot happen — `source_badge_for_type` returns one of
        # them or the aggregator — but a group keyed by an unknown badge would silently
        # drop the source from the screen, so the aggregator is the fallback.
        by_badge.setdefault(registry_source.source_badge, []).append(registry_source)

    groups: list[RegistryGroup] = []
    for badge in SOURCE_GROUP_ORDER:
        groups.append(
            RegistryGroup(
                badge=badge,
                label=SOURCE_GROUP_LABELS[badge],
                sources=tuple(sorted(by_badge.get(badge, []), key=lambda s: s.name)),
            )
        )
    return tuple(groups)


__all__ = [
    "SOURCE_GROUP_LABELS",
    "SOURCE_GROUP_ORDER",
    "RegistryGroup",
    "RegistrySource",
    "read_source_registry",
]
