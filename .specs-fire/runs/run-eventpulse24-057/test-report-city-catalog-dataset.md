---
run: run-eventpulse24-057
work_item: city-catalog-dataset
intent: city-picker-and-auto-collection
generated: 2026-11-20
status: passed
---

# Test Report: The curated world-city catalog

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Domain unit (new) | 39 | 0 | 0 | 100% |
| Backend suite (full) | 7720 | 0 | 0 | 97.41% |
| **Total** | **7720** | **0** | **0** | **97.41%** |

`domain/city_catalog.py`: **100%** statement coverage, which the second CI gate
(`coverage report --include='domain/*' --fail-under=100`) requires and which passed.

## Acceptance Criteria Validation

- ✅ **`domain/city_catalog.py` defines a frozen `CityChoice` and a module-level tuple** — `CityChoice` is a `@dataclass(frozen=True)`; `WORLD_CITIES` is a tuple of **165 rows**. Frozenness is pinned by `TestCityChoiceIsPureData::test_a_row_is_frozen` (expects `FrozenInstanceError`). The row carries the planned seven columns rather than the five the work item sketched: `country_name` and `region_name` were added at plan time so `label` can disambiguate without a 50-state table inside `domain`.
- ✅ **Broad spread of countries and regions, well beyond what is ingested, with a same-named pair** — 165 cities across **95 countries** and all six inhabited tz areas. `TestTheCatalogIsAMapOfTheWorld` asserts ≥50 countries and that `{Africa, America, Asia, Australia, Europe, Pacific}` are all present; `test_offers_cities_that_have_never_been_ingested` pins Chittagong and Reykjavik. The Portland, OR / Portland, ME pair has its own test class.
- ✅ **`name` is the string stored on `DigestPreference`** — rows store `"Portland, OR"`, never `"Portland, Oregon"`. `TestLabel::test_the_label_is_never_the_stored_value` asserts over the whole dataset that the two forms never coincide, so it is never ambiguous which one was written.
- ✅ **A `label` derivation produces the display form without storing it** — `CityChoice.label` is a property, computed, never a column. Pinned for both shapes: `"Sydney, New South Wales"` (qualifier replaced by its display form) and `"Chittagong, Bangladesh"` (no qualifier, placed by country).
- ✅ **`lookup(name)` is case- and spacing-insensitive, `None` for a miss** — `TestLookup` pins `"Portland, OR"`, `"portland, or"`, `"  PORTLAND ,  OR  "` and `"Portland OR"` all resolving to the same row, and `None` for `None`, `""`, `"   "`, `"Fixtureville"` and `"Atlantis"`.
- ✅ **Every row's `tz` loads via `zoneinfo` and passes `canonical_zone` — whole dataset** — `test_every_tz_loads_and_is_canonical` iterates all 165 rows and reports the offending `(name, tz)` pairs. Verified to fail on a planted `tz="EST"` row.
- ✅ **Every row's `name` round-trips through `split_region()` — whole dataset** — `test_every_name_round_trips_through_split_region` compares `split_region(row.name)` against `(row.identity.key, row.region)` for all 165. Verified to fail on a planted `"Chiang Mai"` row, whose trailing `"Mai"` `split_region` reads as a region qualifier.
- ✅ **No two rows share a `(key, region, country_code)` identity — whole dataset** — `test_no_two_rows_share_an_identity`. A **stricter** companion was added: `test_no_two_rows_share_a_lookup_key` on `(key, region)` alone, because `lookup` is handed a bare stored string with no country and a collision there would make it return one of two countries at random.
- ✅ **Every `country_code` is two uppercase letters** — `test_every_country_code_is_two_uppercase_letters`, whole dataset, regex `[A-Z]{2}`.
- ✅ **Stdlib only; no Django, no database** — the module imports `dataclasses` plus `domain.cities`. The pre-existing `test_domain_is_django_free.py` walks every module in `domain` in a fresh interpreter, so it picked up `city_catalog` with no change and passed; `lint-imports` reports 21 contracts kept, 0 broken.

## Tests Written

### Unit Tests

- `backend/tests/domain/test_city_catalog.py` — 39 tests in six classes:
  - `TestEveryRowHoldsUp` (11) — the whole-dataset invariants: tz canonical, `split_region` round-trip, identity uniqueness, lookup-key uniqueness, label uniqueness, country-code shape, slug shape, non-empty name/country, region shape, region-and-display-name paired, one country code ⇒ one country name and slug.
  - `TestTheCatalogIsAMapOfTheWorld` (6) — country breadth, continent breadth, the already-ingested cities (Dhaka, Lisbon, Brooklyn) still pickable, cities never ingested offered anyway.
  - `TestThePortlandPair` (3) — two identities, one key; told apart by label; each keeps its own zone.
  - `TestLookup` (11) — spelling-insensitivity, misses, `"Brooklyn"` vs `"Brooklyn, NY"`, `is_known`.
  - `TestLabel` (4) — qualifier replaced by display form, country fallback, label never equals `name`, every label places the city.
  - `TestChoices` (2) — every row exactly once, alphabetical by label.
  - `TestCityChoiceIsPureData` (2) — frozen; a hand-built row behaves like a catalog one.

### Integration Tests

(none — the item is a pure `domain` module with no database and no I/O, per AD-2.)

## Test Commands

```bash
# The new tests alone
uv run --directory backend pytest tests/domain/test_city_catalog.py -q

# Full backend suite
make test-backend

# Both coverage gates (>=80% overall, 100% for domain/)
make coverage-backend
uv run --directory backend coverage report --include='domain/*' --fail-under=100
```

## Coverage Details

| Module | Statements | Missing | Lines |
|--------|------------|---------|-------|
| `domain/city_catalog.py` | 100% | 0 | 100% |
| `domain/` (gate) | 100% | 0 | 100% |
| backend overall | 97.41% | — | 97.41% |

## Mutation Check

The user's standing rule is that a test must be able to fail, so each whole-dataset
invariant was run against a deliberately bad row before the report was written. Every one
of them caught its own defect and nothing else:

| Planted defect | Caught by |
|---|---|
| `tz="EST"` (loads, but not a canonical geographic zone) | `test_every_tz_loads_and_is_canonical` |
| `"Chiang Mai"` — trailing `"Mai"` reads as a region qualifier | `test_every_name_round_trips_through_split_region` |
| `country_code="th"` (lowercase) | `test_every_country_code_is_two_uppercase_letters` |
| `country_slug="Thailand!"` | `test_every_country_slug_is_url_safe` |
| `region_name` set with no `region` | `test_a_region_has_a_display_name_and_a_display_name_has_a_region` |
| A duplicate Dhaka row | `test_no_two_rows_share_an_identity`, `test_no_two_rows_share_a_lookup_key` |
| `name="   "` | `test_every_row_has_a_name_and_a_country_name` |
| `"Bangla Desh"` under country code `BD` | `test_one_country_code_means_one_country_name_and_slug` |
| `region="ORE"` (uppercase, 3 chars) | `test_every_region_is_lowercase_alphabetic_and_short_enough` |
| A second row labelled "Portland, Oregon" | `test_no_two_rows_share_a_label` (added at review) |

## Issues Found

No test failures. Code review raised two findings, both fixed and re-verified — see
`review-report.md`. One open decision was closed before implementation began:
the catalog's size. It was put to the user, who kept the planned ~150 — the dataset landed
at 165 rows across 95 countries. See the walkthrough's Decisions section.

## Ready for Completion

- [x] All tests passing (7720, zero failures)
- [x] Coverage target met (100% for `domain/`, 97.41% overall against an 80% floor)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
