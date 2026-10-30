"""The Source Badge types, and the mapping from a source to one (EXPERIENCE.md §4, PRD FR-23).

**Why this is its own module.** The badge is a fact about *how a source's facts were
obtained*, and it is needed by two reads on the catalog side: the Pulse Preview's cards
and the Pulse Digest's candidate pool. The Preview's read lives in `preview_read`, which
imports the Event Fit — and `catalog_read`, which the digest's read lives in, must not
pull the Event Fit into its import graph, because `personalization` imports `catalog_read`
and the `event-fit-separation` contract exists precisely to keep the Event Fit away from
`personalization` (AD-10).

So the mapping lives here, in a module that imports nothing but the `Source` model's
*choices*. Both reads import it, and neither imports the other.

**The badge is a type, not a label and not an icon.** `EXPERIENCE.md §4` owns the label
("Official", "Community", "Listing site") and the glyph; the server states the fact. The
same rule the Event Fit tags follow: the server states facts, the client speaks the
user's language.

**The mapping takes plain values, not a model.** `source_badge_for_type` takes the
source's `source_type` and `acquisition_method` as strings, so a caller that may not
hold a `Source` model instance can still ask the question.

**What this module imports.** `apps.ingestion.models`, for the `Source` model's
choices — legal from `apps.ingestion.services` (the `models-ingestion` contract allows
`apps.ingestion` to import `apps.ingestion.models`) and no heavier than `catalog_read`
already is, since that module imports the `Event` model too. It imports **no** module
outside `apps.ingestion` and **no** module from `apps.ingestion.event_fit`: a leaf that
`catalog_read` can import without dragging the Event Fit in behind it.
"""

from apps.ingestion.models import Source

# The Source Badge types (EXPERIENCE.md §4, PRD FR-23). The server names the type; the
# client owns the label and the glyph.
SOURCE_BADGE_OFFICIAL = "official_site"
SOURCE_BADGE_COMMUNITY = "community"
SOURCE_BADGE_AGGREGATOR = "aggregator"
SOURCE_BADGE_CRAWLED = "crawled_html"

#: The badge type for each `Source.source_type`.
#:
#: `venue` and `promoter` are the source's own site — the "Official" badge. `community`
#: and `government` are community-maintained feeds. `ticketing` and `media` are third
#: parties, so the event was "aggregated from a public listing".
_BY_SOURCE_TYPE = {
    Source.SourceType.VENUE: SOURCE_BADGE_OFFICIAL,
    Source.SourceType.PROMOTER: SOURCE_BADGE_OFFICIAL,
    Source.SourceType.COMMUNITY: SOURCE_BADGE_COMMUNITY,
    Source.SourceType.GOVERNMENT: SOURCE_BADGE_COMMUNITY,
    Source.SourceType.TICKETING: SOURCE_BADGE_AGGREGATOR,
    Source.SourceType.MEDIA: SOURCE_BADGE_AGGREGATOR,
}


def source_badge_for_type(*, source_type: str, acquisition_method: str) -> str:
    """The Source Badge type for a source's type and how its facts were obtained.

    A source whose type is not in the table is an aggregator — the least specific
    claim, and the one that does not assert a verification the registry has not made.
    A source acquired by crawling gets the crawled badge regardless of its type,
    because *how* the facts were obtained is what the ⚠ means: "this was scraped, not
    published to us".
    """
    if acquisition_method == "crawl":
        return SOURCE_BADGE_CRAWLED
    return _BY_SOURCE_TYPE.get(source_type, SOURCE_BADGE_AGGREGATOR)


__all__ = [
    "SOURCE_BADGE_AGGREGATOR",
    "SOURCE_BADGE_COMMUNITY",
    "SOURCE_BADGE_CRAWLED",
    "SOURCE_BADGE_OFFICIAL",
    "source_badge_for_type",
]
