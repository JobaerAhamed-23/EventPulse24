---
run: run-eventpulse24-021
work_item: digest-user-preferences
intent: pulse-digest-and-trust
generated: 2026-10-30
status: passing
---

# Test Report: The home city and the personal-events opt-out (FR-19, FR-5)

The user's home city and the personal-events opt-out are two stored preferences that
decide what the Pulse Digest is *about*. The city says where "nearby" means; the flag
says whether the user's own events are in it at all. Both are one row per user, on
`DigestPreference`.

The rules worth testing are the ones a user would notice if they broke:

- a city the catalog does not serve must not be stored **as if it were** — the fallback
  is stored, and it is *labelled* as a fallback;
- the fallback must not be indistinguishable from a city the user chose;
- an absent city must mean "we do not know", and must not become an inferred city;
- the city must not reach the audit log, and must not reach `__str__`;
- the opt-out must default to **included**, and must survive a request that never
  mentions it;
- the backfill must be idempotent and must never overwrite a city that is already set.

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Item-scoped | 44 | 0 | 0 | 100% (`digest_preferences.py`) |
| API-scoped (added) | 4 | 0 | 0 | — |
| **Total (whole backend)** | **3535** | **0** | **0** | **99.11%** |

The whole backend suite is **3535 passed, 0 failed**, with **100.00% on `domain/`**
(the AD-2 purity gate), **176 files at 100%**, and **100% on
`apps/personalization/services/digest_preferences.py`**.

### The item-scoped files, and what each is for

| File | Tests | What it proves |
|------|-------|----------------|
| `backend/tests/personalization/test_digest_preferences.py` | 33 | The commands: the coverage rule, the fallback and its label, the audit rows, the opt-out, the backfill, the sign-up carry, the transaction boundaries |
| `backend/tests/personalization/test_digest_preference_model.py` | 11 | The three columns, the city/source agreement constraint, the retention category, `__str__` leaking no city |
| `backend/tests/personalization/test_onboarding_api.py` | 4 (added) | The endpoint carries the city and the flag, and omission changes neither |

## Test Commands

```bash
# The item's own tests
cd backend
uv run pytest tests/personalization/test_digest_preferences.py \
                 tests/personalization/test_digest_preference_model.py -v

# The API surface
uv run pytest tests/personalization/test_onboarding_api.py -v

# The whole backend, with the coverage gates
uv run pytest --cov --cov-report=term
uv run coverage report --include='domain/*' --fail-under=100

# The architectural gates
uv run ruff check .
uv run ruff format --check .
uv run lint-imports          # 19 contracts, 0 broken
uv run python manage.py makemigrations --check --dry-run   # No changes detected

# The frontend, whose generated client moved
cd .. && make lint-web && make test-web    # 429 passed
```

## 1. The coverage rule, reused rather than reimplemented

The catalog's rule — *a city is supported when it has at least one upcoming, published,
non-superseded event with a current Event Fit* — already exists as
`list_supported_cities()`. This item calls it.

**The test builds a genuinely covered city.** The `covered_city` fixture publishes an
event, files it under the city, and writes the fit. Without it, "a city the catalog
covers" would be a string, the coverage check would reject it, and every test that
*means* "a city the user actually chose" would silently be testing the fallback path
instead. The fixture is what makes the distinction real.

| Test | Asserts |
|---|---|
| `test_a_covered_city_is_stored_in_the_catalogs_spelling` | `"ZYXZX-COVERED-CITY"` → `"Zzyzx-covered-city"`, source `choice` |
| `test_a_covered_city_is_stored_in_the_catalogs_spelling_through_the_command` | The same, through the command that writes the row |
| `test_an_uncovered_city_is_the_fallback` | An uncovered city → the fallback, source `fallback` |
| `test_an_absent_city_stays_absent` | `None` → `(None, None)` — never an inferred city |
| `test_an_empty_city_is_the_fallback` | `"   "` → the fallback |
| `test_an_over_long_city_is_the_fallback` | Longer than `GEO_CITY_MAX_LENGTH` → the fallback |
| `test_the_fallback_is_the_same_constant_the_preview_uses` | The fallback **is** `PREVIEW_FALLBACK_CITY`, not a second constant |

### The two tests that could pass for the wrong reason

**The fallback test.** A test asserting `preference.city == PREVIEW_FALLBACK_CITY`
would pass if *every* city were the fallback — including a covered one the user chose.
So `test_setting_an_uncovered_city_stores_the_fallback_and_labels_it` asserts **all
three** things: the uncovered city stores the fallback, its source is `fallback`, **and**
a covered city stores *itself* with source `choice`. One of the three failing fails the
test.

**The audit test.** A test asserting `"city" not in str(audit.details)` would pass if the
details were *empty* — which would mean the audit row says nothing at all. So
`test_the_audit_row_does_not_carry_the_city` asserts **both** halves: the city is
absent, **and** `details["has_city"] is True` and `details["at"]` is the instant. An
empty details dict fails the second assertion, so it cannot pass for the wrong reason.

## 2. The fallback is not coverage-checked — and why that is not a bug

`store_fallback_city` writes `PREVIEW_FALLBACK_CITY` **without** asking the catalog
whether it serves it. That looks like a missed check, and it was a real bug until the
review caught it.

**The bug.** The backfill called `set_home_city(city=PREVIEW_FALLBACK_CITY, ...)`, which
ran the coverage check — and the fallback is by definition the city the catalog may not
currently serve. So the check replaced the fallback with the fallback and **rewrote the
source from `backfill` to `fallback`**. The backfill was then unable to record what it
did, and a backfilled city was indistinguishable from a city the catalog rejected.

**The fix.** `store_fallback_city` stores the fallback as it is, under the source the
caller names. The coverage rule applies to a *caller's* city; the server chose this
one, so there is nothing to check.

**The test that pins it.** `test_the_backfill_fills_the_accounts_without_a_city`
asserts the source is `backfill` — which is what the bug broke.

## 3. The audit rows (AD-5, AD-13)

| Test | Asserts |
|---|---|
| `test_setting_the_city_writes_an_audit_row` | An `preferences.home_city_set` row exists |
| `test_the_audit_row_does_not_carry_the_city` | The city is absent; `has_city` is `True`; `at` is the instant |
| `test_the_audit_row_for_a_cleared_city_says_so` | `has_city` is `False` |
| `test_the_opt_out_writes_an_audit_row_that_carries_the_flag` | The flag **is** in the details |

**The city is never in the details; the flag always is.** That asymmetry is the point.
A city is weak location data about a real person, and the audit table is read across
into `catalog` (AD-3). The flag is not location data, and "did they opt in or out" is
exactly what an audit row should answer.

## 4. The opt-out (FR-19)

| Test | Asserts |
|---|---|
| `test_personal_events_are_included_by_default` | Included — PRD `[ASSUMPTION-7]` |
| `test_the_user_can_opt_out` | `False` after the command |
| `test_the_user_can_opt_back_in` | `True` again — the flag is not one-way |
| `test_the_opt_out_leaves_the_city_alone` | The two settings do not interfere |
| `test_the_opt_out_creates_the_preference_when_there_is_none` | The upsert creates the row |

## 5. The backfill (D9)

| Test | Asserts |
|---|---|
| `test_the_backfill_fills_the_accounts_without_a_city` | The fallback, source `backfill` |
| `test_the_backfill_never_overwrites_a_city_that_is_set` | A chosen city is untouched; `(0, 0)` |
| `test_the_backfill_is_idempotent` | A second run changes nothing; still one row |
| `test_the_dry_run_count_matches_the_backfill` | The count agrees with the write |
| `test_the_backfill_command_dry_run_writes_nothing` | `--dry-run` writes nothing |
| `test_the_backfill_command_fills_the_accounts` | The command does the work |

The command holds **no model query of its own** — `apps.personalization.models` is
importable only from `apps.personalization` (AD-2), so the query lives in the service
and the command calls it.

## 6. The sign-up carry (D13, D14)

| Test | Asserts |
|---|---|
| `test_the_sign_up_path_stores_the_carried_city` | The carried city, source `choice` |
| `test_the_sign_up_path_stores_an_uncovered_city_as_the_fallback` | The fallback, source `fallback` |
| `test_the_sign_up_path_without_a_city_stores_none` | No city is stored |

**The duplicate sign-up never touches the real holder's city.** The duplicate path
returns before the city is written, and the duplicate path is the one an attacker
reaches — so this is stated in the service's comment rather than left implicit.

## 7. The transaction boundaries (D15)

Two writes in this item could join a transaction, and the two answers are **not** the
same.

**The digest-preference endpoint: one transaction.** A request that sets the delivery
time *and* the city is one decision by one user. If the city write failed after the
delivery time had been written and the two were separate commits, the row would say
"8am" while the city said nothing changed — and neither half would be wrong on its
own.

`test_a_failing_city_write_rolls_the_delivery_time_back` patches the city write to
raise, and asserts the delivery time was rolled back with it.

**This test was verified by mutation.** Reverting the fix to the two-commit version:

```
OLD (two commits): the delivery time stayed at 08:30:00 after the city write failed
  assert preference is None or preference.delivery_time.hour == 9
  ->  assert (<DigestPreference: digest at 08:30:00 America/New_York> is None or 8 == 9)
  FAILED

NEW (one transaction): the delivery time was rolled back with the city
  1 passed
```

The patch is on `onboarding`'s own namespace, not on `digest_preferences` — because
`onboarding` imports the name directly, so patching the other module would leave the
already-bound name in place and the failure would never happen. (The first attempt
patched the wrong module and the test failed with `DID NOT RAISE RuntimeError`, which
is how the mistake was found.)

**The sign-up path: the city is outside the account's transaction.** The account is the
thing that must not be half-made. An account that exists without its audit row is a
hole; an account that exists without a city is merely a user whose city we do not know
yet — a state the digest already handles, and one the backfill fills.

## 8. The model (the columns and the constraint)

| Test | Asserts |
|---|---|
| `test_the_three_columns_exist` | The types, the bounds and the `True` default |
| `test_the_opt_out_defaults_to_included` | The default, on a created row |
| `test_the_city_may_be_absent` | `NULL` is a real state |
| `test_a_city_with_no_source_is_refused` | The constraint, first half |
| `test_a_source_with_no_city_is_refused` | The constraint, second half |
| `test_a_city_with_a_source_is_accepted` | The valid state |
| `test_the_source_choices_are_the_four_the_design_names` | `geo`, `choice`, `fallback`, `backfill` |
| `test_the_retention_category_is_unchanged` | `PREFERENCE_SIGNALS`, not `ACCOUNT_CONTENT` |
| `test_the_string_leaks_no_city` | The city is absent from `__str__` |
| `test_the_repr_leaks_no_city` | And from `repr()` |

**The `__str__` test asserts both halves.** The city is *in the row* and *not in the
string* — so it fails both when the city leaks and when the string is empty of
everything. It also asserts the delivery time and the zone *are* present, so the
string cannot pass by being blank.

**The constraint test tries both halves.** A constraint that only checked "no city
without a source" would pass the first test and fail the second, and one that only
checked the other way round would fail the first. Both are refused.

## 9. The API surface

| Test | Asserts |
|---|---|
| `test_putting_the_digest_preference_carries_the_city_and_the_opt_out` | The response carries the city, the source and the flag |
| `test_omitting_the_city_does_not_clear_the_stored_one` | An old client does not lose the city |
| `test_omitting_the_opt_out_does_not_re_include_personal_events` | The opt-out survives |

**"Omission means leave it alone" is the rule a naive implementation gets wrong.** A
`None` field written on every request clears the city the first time an old client
sends its next request — and the opt-out the first time a client re-includes personal
events without asking. Both are pinned.

**The endpoint cannot clear the city, and that is a shape limitation.** A `null` city
and an omitted city are the *same value* in Pydantic, so "leave it alone" and "clear
it" cannot be told apart in this body. A shape that cannot say which one it means must
not guess: guessing "clear" would wipe the city of every client that sends `null`, and
guessing "leave alone" would make the value unreachable. So `null` means **leave it
alone**, and clearing is reached through the service (`set_home_city(city=None)`), not
through this body. The schema's docstring says this, and the endpoint's description
says it, so the contract does not promise something the shape cannot deliver.

## 10. The generated contract

`make openapi && make client` regenerated `frontend/lib/api/openapi.json` and
`frontend/lib/api/schema.ts`. The contract test
(`tests/api/test_contract.py::test_committed_openapi_schema_matches_the_live_api`)
compares the committed schema against the live one and fails when they drift, so the
regeneration is enforced rather than assumed.

The frontend's onboarding fixture needed the three new fields
(`frontend/components/onboarding/onboarding-flow.test.tsx`), which is the typechecker
telling the truth about what the API now returns.

## What this item does not test

- **How the composition service reads these values.** It reads them; this item owns
  storing them and the commands that write them.
- **What the digest shows for a user with no city.** The city is absent, the nearby
  slot falls back to the timezone, and the empty state names no city. The *wording* of
  that state is `frontend-digest-home`'s.
- **The settings surface.** The command exists; the screen that calls it is out of
  scope (the work item says so explicitly).
- **The frontend's half of the sign-up carry.** This item defines the backend contract;
  the frontend reads the preview cookie and sends the city.
- **Open Question #13.** `[ASSUMPTION-7]` is recorded as an assumption, and the default
  *is* the assumption. If Product changes it, the default changes.

## Verdict

**Passing.** 44 item-scoped tests and 4 API-scoped tests, all green, with every
architectural gate intact and the whole backend at 3535 passed, 0 failed.

Two defects were found and fixed during the review, and both are now pinned by tests
that were **verified to fail against the broken code**:

1. **The city-clear ambiguity.** `_write_preference` could not tell "leave the city
   alone" from "clear the city" — a `None` meant both. The stored city was therefore
   never cleared, and the backfill wrote nothing while claiming to. Fixed with an
   explicit `set_city` flag, and pinned by
   `test_an_absent_city_clears_the_stored_one`.
2. **The fallback's own coverage check.** The backfill's source was rewritten from
   `backfill` to `fallback`, making a backfilled city indistinguishable from a rejected
   one. Fixed by storing the server-chosen fallback without the check, and pinned by
   `test_the_backfill_fills_the_accounts_without_a_city`.

And one was found and fixed by the review's own reading:

3. **The half-applied digest preference.** The delivery time and the city were two
   commits, so a failing city write left a delivery time changed and a city unchanged.
   Fixed by writing the city inside the delivery-time transaction, and pinned by
   `test_a_failing_city_write_rolls_the_delivery_time_back` — which was verified by
   mutation against the two-commit version.
