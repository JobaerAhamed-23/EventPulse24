---
run: run-eventpulse24-057
work_item: city-catalog-dataset
intent: city-picker-and-auto-collection
generated: 2026-11-20
mode: confirm
---

# Implementation Walkthrough: The curated world-city catalog

## Summary

The city picker now has a world to offer. `domain/city_catalog.py` is a checked-in,
stdlib-only table of **165 cities across 95 countries**, each row carrying the four things
everything downstream needs: the string to store, the country, the trailing region
qualifier where one is needed to keep two same-named cities apart, and the IANA timezone.

The commit message on this branch set the bar — *the city picker should be a map of the
world, not a mirror of the catalog* — and that is the line this module draws. It offers
Chittagong whether or not a single Chittagong event has ever been ingested. Finding those
events is `city-provisioning-service`'s job, three items from now; this one just makes the
place pickable, and gives provisioning the zone it will need to read a date-only event
time before any venue in that city exists.

Nothing existing was touched. `domain/cities.py` is imported, not changed.

## Structure Overview

```text
backend/
├── domain/
│   ├── cities.py          (unchanged — imported for split_region, city_identity)
│   ├── timezones.py       (unchanged — its canonical_zone is the tz test's oracle)
│   └── city_catalog.py    NEW — CityChoice, WORLD_CITIES, lookup, choices, is_known
└── tests/domain/
    └── test_city_catalog.py   NEW — 39 tests, every invariant over the whole dataset
```

## Architecture

### Pattern Used

Pure data in `domain/`, per AD-2. No Django, no database, no I/O, no network. The module
is a frozen tuple plus four functions, and an index built once at import so `lookup` is a
dict hit rather than a scan — the same shape `domain.cities._ALIAS_INDEX` already uses.

Two pre-existing structural tests walk every module in `domain` and so picked this one up
with no change at all: `test_domain_is_django_free.py` (AD-2, runs in a fresh interpreter
so a leak cannot hide behind pytest-django) and `test_domain_api.py` (AD-4). `lint-imports`
reports 21 contracts kept, 0 broken.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/domain/city_catalog.py` | `CityChoice`, the 165-row `WORLD_CITIES` tuple, `lookup`, `choices`, `is_known` |
| `backend/tests/domain/test_city_catalog.py` | 39 tests — whole-dataset invariants and lookup/label behaviour |

### Modified

| File | Changes |
|------|---------|
| (none) | |

## Domain Model

### `CityChoice`

| Field | What it is | Who reads it |
|-------|------------|--------------|
| `name` | **The stored value**: `"Portland, OR"`, `"Dhaka"` | `DigestPreference.city`, `split_region`, `venue_fingerprint` |
| `country_code` | ISO 3166-1 alpha-2, uppercase | `CityIdentity` — part of identity |
| `country_name` | `"United States"` | `label` only |
| `country_slug` | `"united-states"` | URL templating in `city-provider-templates`. **Not** identity |
| `region` | What `split_region` yields: `"or"`, `""` | `CityIdentity` — part of identity |
| `region_name` | `"Oregon"`, `""` | `label` only |
| `tz` | IANA zone, canonical | `city-provisioning-service`, `source-city-timezone` |

Derived, never stored: `label` (`"Portland, Oregon"`) and `identity`
(`city_identity(name, country_code)`).

### The three rules the dataset lives by

1. **`name` is what gets written; `label` is what gets read.** A preference will hold
   `"Portland, OR"` — a string the existing catalog already understands — and the picker
   will show "Portland, Oregon". This is what keeps PRD §5 ("no country field on my
   preference") true while still letting the dropdown disambiguate. A whole-dataset test
   asserts the two forms never coincide, so it is never ambiguous which one was stored.
2. **Each row declares what `split_region` will make of its name**, and a test proves it.
   `split_region` reads a trailing alphabetic run of ≤3 characters as a qualifier. Declare
   it, and a bad row is a red test at commit time; re-derive it downstream, and a bad row
   is a wrong city page in production.
3. **Every invariant runs over all 165 rows, never a sample.** Your standing rule is that
   a test must be able to fail, so each one was run against a deliberately planted bad row
   before this was written — nine defects, nine catches, listed in `test-report.md`.

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Catalog size** (the open call from planning) | ~150 hand-verified rows — landed at 165 across 95 countries | **Put to you before implementation and you kept the planned size.** A generated list of thousands would carry wrong zones and qualifiers that fight `split_region`, and the invariant tests would turn into something the data was tuned to pass rather than a check on data a person read. Growing it is one line per city — that is the point of a checked-in list. `city-coverage-request` (item 10) is the escape hatch for a reader whose city is not here yet. |
| Where the uniqueness line is drawn | Stricter than the work item asked | The AC required `(key, region, country_code)` to be unique. `lookup` is handed a bare stored string with **no** country, so a collision on `(key, region)` alone would make it return one of two countries at random. Both are asserted. |
| Label uniqueness | Added at code review | `label` is what the dropdown renders. Two rows rendering the same string ask the reader a question with no answer — `collapse_aliases` already names that failure for two spellings of one city. |
| `CITY_ALIAS_GROUPS` not used here | Kept separate, deliberately | That table says which written forms name the same place; this one says which places may be picked. Routing a lookup through it would let an alias resolve to a row whose `tz` and country were never verified for that spelling. |
| `region` and `region_name` as two columns | Two columns, not a derivation | `region` must be exactly what `split_region` emits because it is part of `CityIdentity`; `region_name` is what a human reads. Deriving one from the other means a table of every state and province inside `domain` — more surface than one short column. |
| `"Brooklyn"` carried without a qualifier | Kept as-is | It is the string already stored on real preferences and registered venues (`tests/personalization/*`, the Browse seed). `"Brooklyn, NY"` would be a *different city* under `domain.cities` rules, so changing it would have been a silent regression. `lookup("Brooklyn, NY")` correctly returns `None`, and there is a test saying so. |
| `country_slug` read, not derived | A column | `"United States"` → `"united-states"` works for most countries and not all, and a wrong slug silently mints a wrong provisioning URL in `city-provider-templates`. |

## The Portland pair

`dedup.venue_fingerprint` warns about this pair by name, and `domain/cities.py` built its
whole identity rule around not merging them. The catalog honours it as a worked case:

| | `Portland, OR` | `Portland, ME` |
|---|---|---|
| stored `name` | `"Portland, OR"` | `"Portland, ME"` |
| identity | `("portland", "or", "US")` | `("portland", "me", "US")` |
| `label` | "Portland, Oregon" | "Portland, Maine" |
| `tz` | `America/Los_Angeles` | `America/New_York` |

Same key, two identities, two labels, and — the part that matters for provisioning —
two different zones. `TestThePortlandPair` pins all three.

## What This Unblocks

| Item | What it takes from here |
|---|---|
| `city-choices-endpoint` | `choices()` — every row, alphabetical by label |
| `stored-city-is-the-picked-city` | `lookup()` / `is_known()` — is this stored string a real choice? |
| `city-provider-templates` | `country_slug` + `name` → `/d/bangladesh--chittagong/` |
| `city-provisioning-service` | `tz` — the load-bearing column; reads a date-only event time in a city with no registered venue |
| `home-city-dropdown-catalog` | `label` — the disambiguating display form |

`source-city-timezone` and `api-source-parser` are the two remaining items with no
dependency on this one.

## Verification

```bash
uv run --directory backend pytest tests/domain/test_city_catalog.py -q   # 39 passed
make test-backend                                                        # 7720 passed
make coverage-backend                                                    # 97.41% overall
uv run --directory backend coverage report --include='domain/*' --fail-under=100   # 100%
uv run --directory backend lint-imports                                  # 21 kept, 0 broken
```

Full detail in `test-report.md` (including the mutation check) and `review-report.md`.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
