---
run: run-eventpulse24-057
work_item: city-catalog-dataset
intent: city-picker-and-auto-collection
generated: 2026-11-20
status: complete
---

# Code Review: The curated world-city catalog

## Files Reviewed

| File | Lines | Role |
|------|-------|------|
| `backend/domain/city_catalog.py` | 368 | New — `CityChoice`, `WORLD_CITIES` (165 rows), `lookup`, `choices`, `is_known` |
| `backend/tests/domain/test_city_catalog.py` | 240 | New — 39 tests, whole-dataset invariants |

No existing file was modified.

## Project Tooling

| Tool | Result |
|------|--------|
| `ruff check` (pyproject, line-length 100) | All checks passed |
| `ruff format --check` | Both files formatted |
| `lint-imports` (import-linter, AD-2 contracts) | 21 contracts kept, 0 broken |
| `pytest` (full backend suite) | 7720 passed, 0 failed |
| Coverage gates | `domain/` 100%, overall 97.41% (floor 80%) |

Two issues surfaced by `ruff` during implementation were fixed before the report: `E501`
(long lines in the data table, resolved by `ruff format`) and `B017` (`pytest.raises(Exception)`
on the frozen-row test, narrowed to `FrozenInstanceError`, which is the actual contract —
a blind `Exception` would have passed on a typo in the attribute name).

## Findings

### 1. [Correctness] `_country`'s row annotation did not describe the rows it is given — FIXED

**File**: `domain/city_catalog.py:95`

The signature read `*rows: tuple[str, str, str] | str`, but the dataset passes four-element
rows wherever a city sits in a zone other than its country's first — `("Monterrey", "", "",
"America/Monterrey")`, every US row outside Eastern, `("Calgary, AB", "ab", "Alberta",
"America/Edmonton")`. The code handled them correctly; the annotation simply lied about
them, and the docstring listed only two of the three shapes.

Widened to `tuple[str, ...] | str` and the docstring now names all three shapes. No
behavioural change — the runtime unpacking `(*row, tz)[:4]` was already right.

**Risk**: none. Annotation and prose only.

### 2. [Testing] Nothing stopped two rows from rendering the same label — FIXED

**File**: `tests/domain/test_city_catalog.py` (new test), `domain/city_catalog.py` (docstring)

`label` is the string the picker renders. The dataset had invariants for identity
uniqueness and lookup-key uniqueness, but none for label uniqueness — so a future row
could be added that is a perfectly distinct *city* while being indistinguishable in the
*dropdown*. That is the failure `domain.cities.collapse_aliases` already names in its own
docstring: offering two identical entries "asks the reader a question with no answer".

Added `TestEveryRowHoldsUp::test_no_two_rows_share_a_label`, over the whole dataset. It
passes on the current 165 rows — verified it is not vacuous by planting a second row that
labels as "Portland, Oregon" without colliding on identity, which it caught. The `label`
docstring now states the constraint rather than disclaiming it.

**Risk**: low. A test addition and a docstring; no production behaviour changed. Full
suite re-run after the change: 7720 passed, `domain/` still 100%.

## Deliberately Not Changed

- **`label` when a hand-built row has a `region` but no comma in `name`.** `label` strips
  the qualifier with `name.rsplit(",", 1)`, so a row written as `CityChoice(name="Portland
  OR", region="or", ...)` would render "Portland OR, Oregon". No catalog row is written
  that way, and `test_every_name_round_trips_through_split_region` does not reject it
  (`split_region` reads the qualifier with or without the comma). Left alone on purpose:
  the alternative is re-deriving the base from `split_region`, which returns the folded
  lowercase key and would render "portland, Oregon" — worse, and it would put a
  display string at the mercy of the identity folding. The stored form is the catalog's
  to write, and every row in it writes the comma.
- **`choices()` sorts on every call** rather than at import. 165 rows is nothing, and a
  module-level sorted tuple would be a second thing to keep in step with `WORLD_CITIES`.
- **Country rows are not split into their own per-country tuples.** The `_country` helper
  already writes each country's four columns once; a further split buys nothing and makes
  the data harder to read top to bottom.
- **`country_slug` is not derived from `country_name`.** "United States" → "united-states"
  works for most rows but not for every country a future row might add, and a slug that is
  wrong silently mints a wrong provisioning URL in `city-provider-templates`. A column
  that is read is safer than a derivation that is assumed.

## Security

Nothing applicable. The module is a frozen, checked-in data table with no I/O, no
database, no user input reaching it except the `lookup` argument, which is folded through
the same `split_region` the rest of `domain` uses and can only ever select a row or return
`None`. No secrets, no injection surface, no network.

## Architecture

Clean against AD-2: stdlib plus `domain.cities`, no Django (enforced by the pre-existing
`test_domain_is_django_free.py`, which walks every module in `domain` in a fresh
interpreter and picked this one up for free). Placement in `domain/` is right — it is pure
data that `domain.cities` must agree with, and the agreement is asserted rather than
assumed. `test_domain_api.py` (AD-4) likewise picked up the new public API with no change.

## Summary

| | Count |
|---|---|
| Auto-fixed | 2 (annotation widened, label-uniqueness invariant added) |
| Pending suggestions | 0 |
| Skipped | 0 |

Both fixes were applied and the full suite re-run. No findings left open.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
