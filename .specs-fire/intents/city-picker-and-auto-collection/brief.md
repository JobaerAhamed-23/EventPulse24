---
id: city-picker-and-auto-collection
title: City Picker Over a Curated World List, With Automatic Collection
status: in_progress
created: 2026-11-20
---

# Intent: City Picker Over a Curated World List, With Automatic Collection

## Goal

Make the city picker a map of the world rather than a mirror of what has already been
ingested, and make selecting a city *the request to collect it*.

Three guarantees, in priority order:

1. **The stored city is the picked city.** Never silently rewritten to anything else.
2. **The heading never lies.** If the page says "Events in Chittagong", it shows
   Chittagong's events or an honest account of why it shows none.
3. **Selecting a city starts collection automatically**, and the city then rides the same
   scheduled refresh loop that keeps every other city fresh.

## Users

Anyone whose city is not one of the handful the catalog has already ingested. Today they
cannot select their city at all — and if they arrive at it by any other route, the server
stores `New York City` instead and the product shows another city's events under a
heading that names theirs.

## Problem

Three faults, stacked:

- **The dropdown is derived from the catalog.** `preview_read.list_supported_cities()`
  offers a city only when it has an upcoming published event with a current Event Fit. A
  city with a real events scene that nothing has ingested is not offerable, so it cannot
  be asked for, so it is never ingested.
- **The server silently rewrites the choice.** `digest_preferences.resolve_home_city()`
  replaces any city outside that derived set with `PREVIEW_FALLBACK_CITY = "New York
  City"` and marks `city_source="fallback"`. `home-city.tsx` is a `<select>` rather than
  a text box *because of* this rewrite — its own docstring says typing "Chittagong"
  "would appear to work and quietly store somewhere else".
- **There is no way to ask for a city.** No coverage-request surface exists anywhere in
  the codebase. A user whose city is uncovered has no route at all.

## Success Criteria

- The picker offers a large curated list of world cities, independent of what has been
  ingested. It stays a `<select>`; no free-text entry.
- A picked city is stored exactly as picked. `PREVIEW_FALLBACK_CITY` is never written as
  the result of a user's choice.
- Picking a city with no data mints its `City` row and provisions sources for it
  automatically, with no human in the loop.
- A provisioned city is claimed by the existing scheduler on the next tick and refreshed
  at its cadence thereafter — the same loop that keeps Lisbon fresh.
- The surface distinguishes four states and says something different and true for each:
  **collecting** (provisioned, not yet yielded), **live-but-quiet** (covered, nothing in
  the window), **no sources** (ran, never yielded), **paused** (an editor stopped it).
- A city whose collection yields nothing says so honestly and offers a coverage request,
  recorded once per city.
- The user's choice survives the city leaving the offered list, its events drying up, or
  an editor pausing its sources.
- No country dropdown, no country column on `DigestPreference`, no country filter, no
  "cities near you".
- Browse's layout, its two tiers, its search box and the event pipeline are unchanged.

## Constraints

- **FR-17 acquisition hierarchy.** Provisioned sources may be `api`, `jsonld`, `rss` or
  `ics` only. `crawl` is forbidden — `ensure_can_ingest()` refuses it without an approved
  `TosReview`, and nothing automatic can approve one.
- **D5 holds: the pipeline never creates a venue.** The cold-start timezone problem is
  solved with a city zone carried on the source, not by auto-registering venues.
- **AD-13.** A city is weak location data. It stays out of audit `details` and out of logs.
- **AD-3 / `models-ingestion`.** `apps.catalog` and `apps.personalization` reach catalog
  data only through `apps.ingestion`'s published read interfaces.
- **AD-16.** `ingestion` remains the sole writer of `Source`, `City` and `Venue`.
- **No LLM.** There is no production `LLMPort.complete()` adapter in this codebase —
  `adapters/llm/` holds only `fake.py` and `voyage.py` (embeddings). There is no
  web-search port either. LLM-assisted source discovery is explicitly **out of scope**;
  see Notes.

## Notes

### The cold-start timezone problem, and why the catalog carries a zone

`ingest_item._venue_for` never creates a venue (D5), so a brand-new city resolves
`venue=None` for every candidate. `domain.timezones.resolve_tz` then has nothing to read a
naive or date-only time in, and returns `TZ_UNRESOLVABLE`.

This is not hypothetical: `seed_dhaka_live.py` documents that the Eventbrite `/d/`
directory — the most city-parameterizable feed shape available — emits **date-only**
`startDate`. Without a fix, provisioning Chittagong would fetch successfully, parse
successfully, and reject every candidate, forever, while the page said "collecting".

The fix is one new link in the fallback chain: `venue_tz` -> `source.city_tz`, with
`city_tz` populated at provisioning time from the curated catalog's zone column. Its
confidence scores below `TZ_SCORE_VENUE_REGISTRY`, because a city zone is weaker evidence
than a specific venue's. The change is strictly additive — existing sources carry no
`city_tz` and behave exactly as they do today.

### Honest scope: most of the world will land in "no sources"

No automatic mechanism can conjure event data for a city where no machine-readable feed
is published. The provider stack (Ticketmaster Discovery API first, per FR-17's
API-over-JSON-LD order, then JSON-LD city directories) covers North America, Europe and
Australia well and most of South Asia and Africa not at all. Chittagong itself will very
likely reach `yielded_nothing`.

That is the designed outcome, not a defect. What this intent delivers for such a city is:
it is selectable, the heading tells the truth, the system genuinely tried, it says so
honestly, and there is a coverage request to file. It does not deliver data that does not
exist.

### Why LLM-assisted discovery is deferred, and what it would look like

Deferred because it changes the *yield rate*, not the feature: every state, every string
and every guarantee above is identical with or without it. Building it now means building
AD-8's LLM gateway from scratch plus a web-search capability that does not exist plus an
amendment to the `http-client` import contract — before there is any evidence about which
cities actually need it. Ship the deterministic version, measure which cities reach
`yielded_nothing`, then decide.

When it is built, the shape is: the LLM proposes candidate URLs; `parsers.parse()` is the
validator; only candidates that parse as `jsonld`/`rss`/`ics` with at least one valid
Event auto-activate (no ToS gate under FR-17); anything HTML-only goes to the editorial
queue and is never auto-activated. The LLM is never trusted — the parser is. A
hallucinated URL 404s and costs one wasted fetch.

### Decisions taken during capture

- **City list source:** a checked-in curated dataset (user's choice), carrying
  `(name, country_code, country_slug, region, tz)`.
- **Same-named cities:** the dropdown *label* disambiguates ("Portland, Oregon"); the
  stored *value* is the catalog's city string ("Portland, OR"), which `split_region()`
  already parses into `("portland", "or")`. No country on `DigestPreference`.
- **Existing `city_source="fallback"` rows:** left alone. `citySourceNote()` already
  labels them honestly, and nulling them would push a surprise empty Browse onto people
  who never asked for one. They repick whenever they like — and now the pick sticks.
