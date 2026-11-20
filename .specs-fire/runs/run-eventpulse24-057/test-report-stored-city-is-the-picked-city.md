---
run: run-eventpulse24-057
work_item: stored-city-is-the-picked-city
intent: city-picker-and-auto-collection
generated: 2026-11-20
status: passed
---

# Test Report: The stored city is the picked city

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Rule (new, whole-dataset) | 682 | 0 | 0 | — |
| Commands (rewritten) | 42 | 0 | 0 | — |
| API (new) | 11 | 0 | 0 | — |
| Backend suite (full) | 8617 | 0 | 0 | 97.44% |
| **Total** | **8617** | **0** | **0** | **97.44%** |

`domain/` at **100%**. `onboarding.py`, `domain/errors.py`, `domain/city_catalog.py` and the
four schema/API modules at **100%**. `digest_preferences.py` at **98%** — up from 94% at
HEAD, and the two lines still uncovered are the pre-existing `get_delivery_settings_for`
batched reader, which this item does not touch. `lint-imports` 21 contracts kept, 0
broken. Frontend `typecheck` passes against the regenerated client.

## Acceptance Criteria Validation

- ✅ **A catalog city is stored exactly as picked, with `city_source="choice"`, and never
  as `PREVIEW_FALLBACK_CITY`** — `test_every_catalog_city_resolves_to_itself` (all 166
  rows), `test_a_catalog_city_is_stored_as_it_was_picked`,
  `test_a_catalog_city_is_stored_in_the_catalogs_spelling`. The refusal path is the
  negative of this: `test_a_city_outside_the_catalog_is_refused_on_a_choice`.
- ✅ **A city outside the catalog is refused with a validation error carrying the
  rejected city; the API returns 4xx and stores nothing** — `UnknownHomeCityError`
  (a `ValidationError`, so 422 via `config/errors.py`). `details` carries
  `rejected_city`. The API-level proof is `test_a_city_outside_the_catalog_is_answered_with_422`
  and `test_a_refused_city_stores_nothing`.
- ✅ **`city=None` still stores nothing and clears; it is distinct from a refusal** —
  `test_an_absent_city_is_not_a_refusal` (returns `(None, None)`, does not raise) and
  `test_an_absent_city_clears_the_stored_one_and_is_not_a_refusal` (clears, does not
  raise). The two are separated by the fact that one raises and one does not.
- ✅ **An over-long city is refused the same way** —
  `test_an_over_long_city_is_refused_on_a_choice`, carrying the same
  `rejected_city` and the same error class.
- ✅ **The geo path keeps its fallback** — a header-inferred city outside the catalog
  still resolves to `PREVIEW_FALLBACK_CITY` with `source="fallback"`:
  `test_a_geo_city_outside_the_catalog_still_falls_back`,
  `test_an_over_long_geo_city_still_falls_back`. A geo city *inside* the catalog keeps
  `source="geo"`: `test_a_geo_city_in_the_catalog_keeps_its_own_source`.
- ✅ **`store_fallback_city()` and `backfill_home_cities()` unchanged** —
  `test_the_fallback_is_stored_as_it_is`, `test_the_backfill_still_writes_the_fallback`,
  `test_the_backfill_never_overwrites_a_city_that_was_picked`. The backfill's
  idempotency and the management command are covered in the rewritten command file.
- ✅ **Existing `city_source="fallback"` rows left alone; no migration touches them** —
  `test_an_existing_fallback_row_is_left_alone` asserts the row still reads `fallback`
  after the backfill. The only migration this item adds is
  `0018_digestpreference_city_source_seed`, which is an `AlterField` on the **choices**
  of `city_source` and moves **no rows** — Django does not enforce choices at the
  database level.
- ✅ **A test parameterised over the dataset so a future catalog row cannot regress
  it** — three parameterised tests over all 166 `WORLD_CITIES` rows:
  `test_every_catalog_city_resolves_to_itself`,
  `test_every_catalog_city_resolves_from_a_differently_spelled_request`,
  `test_every_catalog_city_is_stored_as_itself`, and
  `test_the_stored_city_is_always_a_city_the_catalog_holds`. A row added tomorrow is
  covered without anyone touching the file.
- ✅ **A test asserting the refusal path writes no `DigestPreference` row and no audit
  row** — `test_a_refused_city_writes_no_preference_row` and
  `test_a_refused_city_writes_no_audit_row`, plus
  `test_a_refused_city_does_not_disturb_a_city_already_stored`. **Both halves are
  asserted**, so an implementation that wrote and *then* raised cannot pass.
- ✅ **AD-13: the refused city is in the API error and not in any audit `details` or log
  line** — `test_a_refused_city_is_in_the_error_and_in_no_audit_detail` and
  `test_the_refused_city_is_in_the_response_and_in_no_audit_row`. The message does not
  quote the value (`test_the_refusal_message_does_not_quote_the_city`); the value is in
  `details`, which is machine-readable data for the caller that sent it.

## The decisions taken at the checkpoint

| Decision | Chosen | Where it is tested |
|---|---|---|
| The refusal's status | **422** (`ValidationError`) | `test_the_refusal_is_a_validation_error`; `test_a_city_outside_the_catalog_is_answered_with_422` |
| The refused city is echoed | In `details["rejected_city"]`, **not** in the message | `test_the_refusal_carries_the_rejected_city`, `test_the_refusal_message_does_not_quote_the_city` |
| The branch is on `source`, not on the city | choice → refuse; geo → fallback | `test_a_city_outside_the_catalog_is_refused_on_a_choice`, `test_a_geo_city_outside_the_catalog_still_falls_back` |
| No migration of existing rows | The `fallback` rows keep reading `fallback` | `test_an_existing_fallback_row_is_left_alone` |

## Tests Written

**`tests/personalization/test_stored_city_is_the_picked_city.py` (new, 682 cases)** — the
item's own proof, kept apart from the command tests.

*The whole dataset (4 × 166 = 664 cases)*: every catalog row resolves to itself; every
row resolves to the catalog's spelling from a differently-spelled request; every row is
stored as itself through the command; every stored city is one the catalog holds.

*The refusal (11)*: refused on a choice; carries the rejected city; the message does not
quote it; it is a `ValidationError`; over-long refused; empty refused; **no preference
row**; **no audit row**; the city is in the error and in no audit detail; an earlier
stored city is undisturbed.

*`None` is not a refusal (2)*: absent stays absent; absent clears and does not raise.

*The geo path (3)*: outside the catalog falls back; over-long falls back; inside the
catalog keeps `source="geo"`.

*The server's own city (3)*: a seed city is stored verbatim; a seed city is not refused;
an over-long seed city falls back.

*What did not change (5)*: the fallback is stored as it is; the backfill writes the
fallback; the backfill never overwrites a picked city; an existing `fallback` row is left
alone; a pick replaces a fallback row with the picked city.

**`tests/api/test_digest_preference_api.py` (new, 11)** — the endpoint's HTTP shape, over
a real session with a real CSRF token: a catalog city answers 200 and stores exactly
what was sent; a city outside the catalog answers 422 with the project's one error shape
and names the rejected value; **nothing is stored**; an earlier city is undisturbed; the
timezone rule is untouched; the endpoint still requires a session.

**`tests/personalization/test_digest_preferences.py` (rewritten, 42)** — the
coverage-rule tests this item inverts, rewritten rather than deleted. The old file
asserted the rewrite with fake city names (`"Zzyzx-covered-city"`) and a `covered_city`
fixture that built venues and events; the rewrite uses real catalog cities
("Chittagong", "Kathmandu") and no catalog database, because the rule no longer reads one.

**`tests/personalization/test_onboarding_api.py` (2 changed)** — two tests asserted the
rewrite directly: `city == "New York City"` and `city_source == "fallback"` for a
"Brooklyn" pick. "Brooklyn" *is* in the curated catalog, so the answer is now
`city == "Brooklyn"` and `city_source == "choice"`. Those assertions were the bug, in
test form.

**`tests/config/test_seed_browse_catalog.py` (1 new)** — the seeded city is labelled
`seed`.

## Mutation Check

Every whole-dataset invariant was mutated and the mutation reverted. **The rule that a
test must be able to fail.**

| Mutation | Result |
|---|---|
| `lookup` always misses | **501 of 516 failed** in the rule file alone; 520 across the three new files |
| `resolve_home_city` returns `""` instead of `row.name` | **513 failed** across the three new files |
| The old silent rewrite restored — a choice outside the catalog falls back | **23 failed** across the three files, and every one of them is a refusal test: `test_a_city_outside_the_catalog_is_refused_on_a_choice`, `test_the_refusal_carries_the_rejected_city`, `test_a_refused_city_writes_no_preference_row`, `test_a_refused_city_writes_no_audit_row`, `test_a_city_outside_the_catalog_is_answered_with_422`, `test_a_refused_city_stores_nothing`, and the rest |
| `resolve_home_city` returns the **caller's** spelling instead of the catalog's | **170 failed**, including `test_the_stored_city_is_always_a_city_the_catalog_holds` — the replacement for the `_canonical` invariant guard this item deleted |

The third mutation is the important one: it is **the old bug, put back**, and 23 tests
across all three files catch it. A test that could not fail would have made the item
unproven.

## Two findings the mutation check surfaced

**1. `_canonical` became dead code.** The plan said its `raise ValueError` invariant
guard would stay. It did not — `resolve_home_city` now returns `row.name` directly and
nothing calls `_canonical` any more. It was a helper whose only caller had been folded
into the function above it. It is **deleted**, and its test with it; the invariant it
guarded is now enforced at the one place a city is stored, and pinned by
`test_the_stored_city_is_always_a_city_the_catalog_holds` over the whole dataset. The
fourth mutation above is the proof that the replacement can fail.

**2. "Montgomery" was not in the curated catalog.** The local dev seed's city — the one
`config/local_feeds.json` registers as a real source and `config/browse_seed.json`'s
sibling `local_feeds.fixtures.json` fills with venues — was **not pickable**. Under the
old rule that was harmless: it was stored as the fallback and the surface showed New
York City. Under this item's rule it would be **refused**, and the picker (which today
reads `preview/cities`) would offer a city the server answers with a 422.

The catalog gained the row: `("Montgomery", "", "", "America/Chicago")` — no region
qualifier, because the string the seed's venue and its source already use is plain
"Montgomery", and a qualified "Montgomery, AL" would key differently and resolve to
nothing. It sits in `America/Chicago` (Central Time), not the country's
`America/New_York` default. The catalog's own whole-dataset invariants hold over the new
row, and the label is "Montgomery, United States", the same shape as "Brooklyn,
United States".

**Every city the repository mentions is now in the catalog**, checked over every JSON
file under `backend/config/` and `backend/tests/fixtures/`: `Montgomery` resolves, and
the only other is "Fixtureville" — the seed's fictional city, which is not a reader's
pick and is handled by the third writer below.

## The third writer: the seed's own city

The seed writes "Fixtureville" — a **fictional** city for a local walk-through. It is not
in the catalog and never could be. Under the new rule the seed's write was **refused**,
and 26 tests in `tests/config/test_seed_browse_catalog.py` failed for that reason.

The fix is not to bend the seed's city into a real one — its venues, its events and its
accounts' city would then disagree, and the Browse surface the walk-through exists to
show would be empty. The fix is to say what the seed **is**: the **server choosing** a
city, with no reader in the story at all. That is the same situation as the fallback,
which is exempted from the catalog check for exactly that reason.

So `city_source` gained a fifth value, `seed`:

- `resolve_home_city` stores a `seed` city **verbatim** (`SOURCE_SEED`);
- `set_digest_preference` takes a `city_source`, defaulting to `SOURCE_CHOICE` — every
  browser path that sets a city is a reader picking one;
- the seed passes `city_source=SOURCE_SEED`;
- `DigestPreference.CitySource` gains `SEED`, with migration `0018`, which moves **no
  rows** (Django does not enforce choices at the database level, so this is an
  `AlterField` on the Python-side vocabulary and nothing else).

The four original sources describe how a **reader's** city arrives; the fifth does not,
and the model's own docstring now says so.

## Test Commands

```bash
uv run --directory backend pytest tests/personalization/test_stored_city_is_the_picked_city.py -q
uv run --directory backend pytest tests/personalization/test_digest_preferences.py -q
uv run --directory backend pytest tests/api/test_digest_preference_api.py -q
uv run --directory backend pytest tests/config/test_seed_browse_catalog.py -q
make test-backend && make coverage-backend
make client && uv run --directory backend pytest tests/api/test_contract.py -q
make lint-imports
```

## Issues Found

Four, all fixed, detailed in `review-report-stored-city-is-the-picked-city.md`: the dead
`_canonical` and its uncovered success path; the seed's fictional city being refused;
"Montgomery" being missing from the catalog; and two pre-existing API tests asserting
the rewrite.

The OpenAPI contract and the generated TypeScript client were regenerated (`make client`);
`tests/api/test_contract.py` enforces that they match the live API. The change is
**description-only** — the schema shape did not move.

## Ready for Completion

- [x] All tests passing (8617, zero failures)
- [x] Coverage met (100% on every changed module except `digest_preferences.py` at 98%, up from 94%; 100% `domain/`; 97.44% overall)
- [x] All 10 acceptance criteria validated
- [x] Every whole-dataset invariant mutation-checked
- [x] Frontend contract regenerated and typechecking

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
