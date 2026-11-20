---
id: stored-city-is-the-picked-city
title: The stored city is the picked city
intent: city-picker-and-auto-collection
complexity: high
mode: validate
status: in_progress
depends_on:
  - city-catalog-dataset
created: 2026-11-20
---

# Work Item: The stored city is the picked city

## Description

Delete the silent rewrite. `digest_preferences.resolve_home_city()` currently replaces any
city outside `list_supported_cities()` with `PREVIEW_FALLBACK_CITY` and marks it
`fallback`. A city in the curated catalog must be stored exactly as picked, with the source
the caller named.

This is the single most important item in the intent, and the one the user named as "the
one thing to avoid". It is also the one that can be shipped and verified on its own.

The coverage check is not removed, it is **re-based**: the question changes from "can the
preview serve this city today?" to "is this a city a person may pick?". A city in the
catalog is answerable; a city outside it is refused outright rather than rewritten.

## Acceptance Criteria

- [ ] `resolve_home_city(city=<in catalog>, source="choice")` returns that city's catalog `name` and `"choice"` — never `PREVIEW_FALLBACK_CITY`.
- [ ] A city **not** in the catalog is **refused** with a validation error carrying the rejected city, not silently rewritten. The API returns 4xx and stores nothing.
- [ ] `city=None` still stores nothing and clears an existing city — unchanged, and still distinct from a refusal.
- [ ] An over-long city (> `GEO_CITY_MAX_LENGTH`) is refused the same way, not rewritten.
- [ ] The geo path keeps its fallback: a *header-inferred* city outside the catalog still resolves to `PREVIEW_FALLBACK_CITY` with `source="fallback"`, because nobody chose it and an inferred city must not be refused back to the user.
- [ ] `store_fallback_city()` and `backfill_home_cities()` are unchanged — they are server-chosen, not user-chosen.
- [ ] Existing rows with `city_source="fallback"` are left exactly as they are. No migration touches them.
- [ ] A test asserts that for every city in the catalog, `resolve_home_city` returns that city — parameterised over the dataset, so a future catalog row cannot regress it.
- [ ] A test asserts the refusal path writes **no** `DigestPreference` row and **no** audit row.
- [ ] The AD-13 discipline holds: the refused city is in the API error for the caller, and **not** in any audit `details` or log line.

## Technical Notes

The geo-versus-choice distinction is the subtle part and must not be collapsed. Two callers
reach this function:

- **the user picking from the dropdown** (`source="choice"`) — their choice is authoritative
  and a city outside the catalog is a client bug, so it is refused loudly;
- **the geo header** (`source="geo"`) — nobody chose it, so an uncoverable value falls back
  silently exactly as it does today. Refusing it would turn an edge's guess into a 4xx on a
  path the user never asked for.

`_canonical()` currently resolves spelling against `list_supported_cities`. It should
resolve against the catalog instead, and its `raise ValueError` invariant guard stays —
the caller still checks membership first, and the raise is still the type-checker's proof
that the check happened.

`home-city.tsx` already replaces its optimistic value with the server's answer, so it needs
no change for this item to be observable; the user sees their city stick immediately.

## Dependencies

- city-catalog-dataset
