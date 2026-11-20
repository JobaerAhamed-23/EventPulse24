"""Provider templates: which sources exist for a city, and in what order to try them.

**This is the thing that makes "pick a city, get sources" possible at all.** A reader picks
Chittagong; something has to know that Chittagong has a Ticketmaster Discovery API, that the
URL is `.../events.json?city=Chittagong&countryCode=BD`, and that the API is the tier to try
first. That knowledge lives here, as code, and it is **pure**: no network, no database, no
Django. Which providers exist for which cities is a **code-reviewed fact**, not a runtime
surprise.

**The order is FR-17's, and it is not ours to rearrange.** FR-17: official APIs >
partnerships > RSS/JSON-LD > email/ICS > crawling, last resort. `AcquisitionMethod`'s own
docstring says "FR-17 priority order, highest first", and the pipeline's ingest guard
(`ensure_can_ingest`) refuses a crawl source without an approved ToS review — a thing no
automatic process can grant. So **no template may emit `crawl`**, and a test asserts it over
the whole registry rather than trusting this paragraph.

**`None` is a normal answer.** A template returns `None` for a city it cannot serve, and
`resolve()` skips it. That is the design, not a gap: a source minted for a city the provider
does not serve would be fetched, found empty, and then read as a failure of *our*
collection rather than a fact about the provider.

**No template carries an API key.** A key in a URL is a **credential**, not an identifier:
`Source.url` is a column read by the admin and dumped by any backup, and
`register_source` writes its fields into an audit row kept for 24 months. So the key is
added at fetch time by `apps.ingestion.services.provider_keys.authorized_url`, which marks
the request `credential=True` so the HTTP library does not log the URL, and removed again by
`strip_key` before anything stores it. **This module therefore emits a key-less URL, and a
test asserts it** — a template that baked a key in would put that secret into every audit
row for every city.

**The vocabularies are restated here, and a test holds them to the model's.** `domain` is
stdlib-only and may not import `apps.ingestion.models` (AD-3's `models-ingestion`
contract), so `SOURCE_TYPES`, `ACQUISITION_METHODS` and `TZ_COVERAGES` are plain constants
here. Restating a vocabulary is a place two truths could grow apart, so
`tests/domain/test_city_providers.py` asserts every constant is a member of the model's
vocabulary — if `AcquisitionMethod` gains a value, this registry cannot drift from it
silently. That test is the guard; these constants are the copy.

**A provider's slugging belongs to the provider.** `domain.cities.mint_city_slug` mints
*our* FR-27 URL segment ("brooklyn-ny-us") and must never be re-pointed at a third party's
URL scheme. Each template therefore brings its own slug, local to that template and to that
provider's convention.
"""

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode

from domain.city_catalog import CityChoice

# ── The vocabularies, restated (see the module docstring) ──────────────────────────────────

#: `Source.SourceType` — what kind of organisation the source is.
SOURCE_TYPES = frozenset(
    {
        "venue",
        "promoter",
        "ticketing",
        "community",
        "government",
        "media",
        "other",
    }
)

#: `AcquisitionMethod` — how the source is acquired. FR-17's order, highest first.
#:
#: **A tuple, not a set, because the order is the meaning.** `AcquisitionMethod`'s own
#: docstring says "FR-17 priority order, highest first", and the ingest guard
#: (`ensure_can_ingest`) refuses a crawl source without an approved ToS review — a thing no
#: automatic process can grant. So the tier order is a fact this module rests on, and a set
#: would throw that fact away. `ACQUISITION_METHOD_SET` is the set view, for membership
#: tests.
ACQUISITION_METHODS: tuple[str, ...] = (
    "api",
    "partnership",
    "jsonld",
    "rss",
    "ics",
    "email_ics",
    "crawl",
)

#: The same vocabulary, as a set, for membership tests.
ACQUISITION_METHOD_SET = frozenset(ACQUISITION_METHODS)


#: `Source.TzCoverage` — how much of the source's timezone the source states for itself.
TZ_COVERAGES = frozenset({"full", "partial", "none"})

# ── What a template produces ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceSpec:
    """A proposed source for one city: everything `register_source` needs, and nothing else.

    **The field names are the registry's own.** `Source.url`, `Source.source_type`,
    `Source.acquisition_method` and `Source.tz_coverage` — so a spec is a `Source` row
    that has not been written yet, and the registry's cleaner (`clean_source_input`)
    validates it under exactly the rules the row will meet.

    **`tz_coverage` is a claim the provider supports, not one we want.** A source that
    states no timezone anywhere covers none of them ("none"), and every one of its events
    leans on its venue or the city's zone for one. Claiming "partial" where the feed says
    nothing would be a claim about our catalogue that the feed does not back.
    """

    name: str
    source_type: str
    url: str
    acquisition_method: str
    tz_coverage: str


@dataclass(frozen=True)
class ProviderTemplate:
    """One provider's rule for turning a city into a source.

    **`build` is a pure function**: the same city always produces the same spec, and it
    never touches the network or the database. That is what makes the registry a code-
    reviewed fact — the whole registry can be evaluated in a test, over every city, with no
    side effects at all.

    **`enabled` is a legal fact, not a preference.** A provider whose terms we have not
    cleared stays in the registry with `enabled=False`, so its URL shape and its tests
    survive and the day a person clears it, one constant changes. A template that was
    *omitted* would have to be rewritten, and a template that was *enabled* would be
    promoting a source the codebase has already flagged.

    **A disabled template produces nothing.** `resolve()` skips it, so it can never yield a
    `SourceSpec` and can never be registered. "Disabled" is therefore safe, not merely
    quiet.
    """

    key: str
    method: str
    build: Callable[[CityChoice], SourceSpec | None]
    enabled: bool = True


# ── Ticketmaster Discovery API ─────────────────────────────────────────────────────────────

#: Where Ticketmaster's Discovery API lives. **Exact host** — the parser and the key
#: injector both match exactly, never by suffix, so a look-alike host is never handed our
#: key and never handed a document the reader trusts.
TICKETMASTER_HOST = "app.ticketmaster.com"

#: The countries whose cities Ticketmaster's Discovery API actually serves.
#:
#: **This is a reviewed list, not the provider's whole footprint.** Ticketmaster states its
#: coverage in prose — "New Zealand, United Kingdom, Ireland, other European countries, and
#: more" — and says more countries are added continuously, so no fixed list of theirs is a
#: fact we could hold. What we hold is the list that is **true today** for the countries the
#: catalog has cities in, and widening it is a reviewed commit — the right ceremony for "we
#: now know Ticketmaster serves Brazil".
#:
#: **Every country here is one the catalog has a city in**, asserted by a test. A constant
#: naming a country with no city would be a claim about coverage that nothing exercises.
#:
#: **A city outside this set gets no Ticketmaster source**, and that is the point: minting
#: one would mint a source that answers empty forever.
TICKETMASTER_COUNTRIES = frozenset(
    {
        # North America
        "US",
        "CA",
        "MX",
        # Oceania
        "AU",
        "NZ",
        # Western Europe
        "GB",
        "IE",
        "NL",
        "BE",
        "DE",
        "ES",
        "PT",
        "FR",
        "IT",
        "AT",
        "CH",
        "DK",
        "SE",
        "NO",
        "FI",
    }
)

#: Discovery v2's maximum page size. The default is 20, and a source that only ever sees
#: the first 20 of a city's events goes stale silently — the reader is shown a city that
#: looks empty because we stopped reading at page one.
#:
#: **`size` is per page, not a total.** Discovery's own paging is a fetch-layer concern, so
#: the template asks for the fullest first page it can and leaves the rest to the fetcher.
TICKETMASTER_PAGE_SIZE = 100


def _ticketmaster_spec(city: CityChoice) -> SourceSpec | None:
    """The Discovery API spec for `city`, or None where Ticketmaster does not serve it.

    **The city and the country come from the same row**, so they cannot disagree — the
    alternative, a country filtered from somewhere else, would be a way to mint a source
    that answers about the wrong place.

    **The city is the row's own name**, which may carry a region qualifier ("Portland, OR")
    — the same string the catalog stores on a preference, so the source and the reader's
    city say the same thing.
    """
    if city.country_code not in TICKETMASTER_COUNTRIES:
        return None

    query = urlencode(
        {
            "city": city.name,
            "countryCode": city.country_code,
            "size": TICKETMASTER_PAGE_SIZE,
        }
    )
    return SourceSpec(
        name=f"Ticketmaster — {city.label}",
        source_type="ticketing",
        url=f"https://{TICKETMASTER_HOST}/discovery/v2/events.json?{query}",
        acquisition_method="api",
        # **Discovery states a zone on every event** (`dates.timezone`), which is why this
        # is the only tier that resolves perfectly in a city we have never seen before.
        tz_coverage="full",
    )


# ── Eventbrite city directory (JSON-LD) ────────────────────────────────────────────────────

#: Where Eventbrite's city directories live.
EVENTBRITE_HOST = "www.eventbrite.com"


def _eventbrite_city_slug(city: CityChoice) -> str:
    """The city segment Eventbrite's own URL uses.

    **Eventbrite's slugging, not ours.** `domain.cities.mint_city_slug` mints our FR-27 URL
    segment and must not be re-pointed at a third party's URL scheme. Eventbrite's shape is
    the one `config/management/commands/seed_dhaka_live.py` fetches and parses:
    `https://www.eventbrite.com/d/bangladesh--dhaka/events/`.

    **The region's qualifier is carried, because dropping it makes two cities one.**
    "Portland, OR" and "Portland, ME" are two different cities in the catalog, and
    Eventbrite's shape has one city segment and a separate country segment — so a slug of
    "portland" for both would mint the **same URL twice**. `register_source` refuses a
    duplicate URL, so the second Portland would be refused rather than served, and the
    reader in Maine would be shown Oregon's events.

    So the region's own qualifier goes into the city segment: "portland-or" and
    "portland-me". A city with no qualifier keeps its plain name, which is the shape
    `seed_dhaka_live.py` proves ("bangladesh--dhaka").
    """
    base = city.name.rsplit(",", 1)[0].strip() if city.region else city.name
    slug = base.lower().replace(" ", "-")
    if city.region:
        slug = f"{slug}-{city.region}"
    return slug


def _eventbrite_spec(city: CityChoice) -> SourceSpec | None:
    """The Eventbrite directory spec for `city`, or None where there is no directory.

    **The URL shape is proven by running code**: `seed_dhaka_live.py` registers, fetches
    and parses this shape, and the JSON-LD parser follows the directory page's `ItemList`
    through to each `Event` node. It is the one structured, crawl-free path we have actually
    exercised.

    **It is disabled, and that is a legal fact rather than a preference.** Eventbrite's own
    Terms restrict automated access and point at their API, and `seed_dhaka_live.py` says so
    in its own docstring: "a local-development source, not a production one". Enabling this
    template without a terms review would promote a source the codebase has already
    flagged — which is precisely what this registry exists to prevent.

    So the template ships **in** the registry with `enabled=False`: its URL shape and its
    tests survive, and the day a person clears the terms, one constant changes.
    """
    slug = _eventbrite_city_slug(city)
    return SourceSpec(
        name=f"Eventbrite — {city.label}",
        source_type="ticketing",
        url=f"https://{EVENTBRITE_HOST}/d/{city.country_slug}--{slug}/events/",
        acquisition_method="jsonld",
        # The directory page states no timezone anywhere, so the source covers none of them
        # and every event leans on its venue for one.
        tz_coverage="none",
    )


# ── The registry ────────────────────────────────────────────────────────────────────────────

#: Every provider template, in FR-17's order: the API tier first, the structured tier
#: after it, and nothing that needs a ToS review a person has not given.
#:
#: **The order is the point.** `resolve()` returns the specs in this order, so a city with
#: two providers is tried against the API first — the tier that resolves a date and a zone
#: without borrowing either from a venue.
PROVIDER_TEMPLATES: tuple[ProviderTemplate, ...] = (
    ProviderTemplate(
        key="ticketmaster",
        method="api",
        build=_ticketmaster_spec,
        enabled=True,
    ),
    ProviderTemplate(
        key="eventbrite-directory",
        method="jsonld",
        build=_eventbrite_spec,
        # **Eventbrite's Terms restrict automated access and point at their API.**
        # `seed_dhaka_live.py` already says so, and this is not the place to overrule it:
        # the URL shape is proven and kept, and the source is not promoted until a person
        # has reviewed the terms. Flip this to True after that review.
        enabled=False,
    ),
)


def resolve(city: CityChoice) -> tuple[SourceSpec, ...]:
    """The source specs for `city`, in template order, skipping the ones that decline.

    **An empty tuple is a normal answer, not a failure.** A city no template covers gets
    no sources, and the caller records that as its own state ("no providers") rather than
    treating it as an error. A city in a country Ticketmaster does not serve, with the
    JSON-LD template disabled, is exactly that.

    **A disabled template contributes nothing.** It is skipped whole, so it cannot yield a
    spec and cannot be registered — which is what makes "disabled" a safe thing to ship.
    """
    specs: list[SourceSpec] = []
    for template in PROVIDER_TEMPLATES:
        if not template.enabled:
            continue
        spec = template.build(city)
        if spec is not None:
            specs.append(spec)
    return tuple(specs)


__all__ = [
    "ACQUISITION_METHODS",
    "ACQUISITION_METHOD_SET",
    "PROVIDER_TEMPLATES",
    "SOURCE_TYPES",
    "TICKETMASTER_COUNTRIES",
    "TICKETMASTER_HOST",
    "TICKETMASTER_PAGE_SIZE",
    "TZ_COVERAGES",
    "ProviderTemplate",
    "SourceSpec",
    "resolve",
]
