---
id: city-provider-templates
title: City-parameterized provider templates
intent: city-picker-and-auto-collection
complexity: medium
mode: confirm
status: pending
depends_on: [city-catalog-dataset]
created: 2026-11-20
---

# Work Item: City-parameterized provider templates

## Description

The registry of providers whose feed URL is a pure function of a city — the thing that
makes "pick a city, get sources" possible at all. Each template maps a `CityChoice` to a
`SourceSpec`, or to `None` when it cannot serve that city.

Ordered by FR-17's acquisition hierarchy: API before JSON-LD, never crawl.

Pure and checked in, so that which providers exist for which cities is a code-reviewed
fact rather than a runtime surprise.

## Acceptance Criteria

- [ ] `domain/city_providers.py` defines a frozen `SourceSpec(name, source_type, url, acquisition_method, tz_coverage)` and an ordered tuple of templates.
- [ ] Each template is a pure function `CityChoice -> SourceSpec | None`. `None` means "this provider cannot serve this city" and is a normal answer.
- [ ] Templates are ordered by FR-17 priority: `api` before `jsonld`/`rss`/`ics`.
- [ ] **No template may emit `acquisition_method="crawl"`** — asserted by a test over the whole registry, because `ensure_can_ingest` would refuse it and nothing automatic can approve a `TosReview`.
- [ ] A Ticketmaster Discovery API template is included, restricted to the countries it actually covers, returning `None` elsewhere rather than minting a source that will always be empty.
- [ ] Any template emitting `acquisition_method="api"` is covered by a parser in `PARSERS` — **`api` has none today**, so this item is inert for the API tier until `api-source-parser` lands. A test asserts every method the registry can emit has a registered parser, so a future template cannot silently emit an unparseable method.
- [ ] A JSON-LD city-directory template is included, built from `country_slug` and a city slug.
- [ ] Every emitted `url` is well-formed and <= 2048 characters — asserted across the full cross-product of catalog x templates, not a sample.
- [ ] `resolve(city)` returns the specs for a city in template order, skipping `None`s, and returns an empty tuple for a city no template covers.
- [ ] Stdlib only. No network, no database, no Django.

## Technical Notes

**The API tier does not work without `api-source-parser`.** `parsers/__init__.py` registers
only `jsonld`, `rss`, `ics` and `email_ics`; `parse()` returns `unsupported_method` for
`api`, `partnership` and `crawl`. This was missed in the first draft of this item. The
templates here are pure data and can be written independently, but provisioning must not
register an `api` source before the parser exists — hence the dependency added to
`city-provisioning-service`.

**Ticketmaster's `city` query parameter is not confirmed in the official v2 parameter
table** — it appears in third-party guides only. Verify it against live docs during the
run before building on it; if it is absent, the fallback is `countryCode` plus client-side
city filtering, or dropping the template to JSON-LD only. Do not assume it works.

The free developer tier is documented at 5,000 calls/day and 5 req/sec. At a 4-hour
cadence that is roughly 850 provisioned cities before the daily quota binds — comfortable,
but it is a real ceiling and the probation item is what keeps it from being reached by
dead cities.

The Eventbrite `/d/{country_slug}--{city_slug}/events/` shape is proven by
`seed_dhaka_live.py`, but that command's own docstring calls it "a local-development
source, not a production one" because Eventbrite's Terms restrict automated access and
point at their API. Either settle that question in this item or ship the template disabled
behind configuration — do not quietly promote a source the codebase has already flagged.

The slug a provider wants is not `domain.cities.mint_city_slug()`. That function mints our
own FR-27 URL segment and must not be re-pointed at a third party's URL scheme; a
provider's slugging belongs to its own template.

## Dependencies

- city-catalog-dataset
