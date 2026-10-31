# Code Review Report

**Run**: run-eventpulse24-021
**Intent**: pulse-digest-and-trust
**Work item**: digest-user-preferences
**Reviewed**: 2026-10-30
**Files Reviewed**: 11

---

## Summary

| Category | Applied | Skipped |
|----------|---------|---------|
| Code Quality | 2 | 0 |
| Correctness | 3 | 0 |
| Security | 0 | 0 |
| Architecture | 1 | 0 |
| Testing | 1 | 0 |
| **Total** | **7** | **0** |

**Tests Status**: Passing — 3535 passed, 0 failed; `domain/` at 100%;
`digest_preferences.py` at 100%

> All seven fixes were applied without a checkpoint because each is either mechanical
> and reversible (a duplicated block, a dead branch, a misleading docstring) or is
> covered by a test that was **verified to fail against the broken code** (the three
> correctness fixes). The full suite, the coverage gates, the import contracts and the
> frontend lint were re-run after the last change.

---

## Files Reviewed

- `backend/apps/personalization/models.py` (modified) — `DigestPreference`'s three new columns, the `CitySource` enum, the agreement constraint
- `backend/apps/personalization/services/digest_preferences.py` (created) — the commands, the coverage rule, the backfill
- `backend/apps/personalization/services/onboarding.py` (modified) — `set_digest_preference` gains the city and the flag
- `backend/apps/personalization/schemas.py` (modified) — `DigestPreferenceIn`/`Out`
- `backend/apps/personalization/api.py` (modified) — the endpoint carries the new fields
- `backend/apps/identity/services/sign_up.py` (modified) — the sign-up carry
- `backend/apps/identity/schemas.py` (modified) — `SignUpIn.city`
- `backend/apps/identity/api.py` (modified) — the endpoint passes the city through
- `backend/config/management/commands/backfill_digest_cities.py` (created) — the idempotent backfill
- `backend/tests/personalization/test_digest_preferences.py` (created) — 33 tests
- `backend/tests/personalization/test_digest_preference_model.py` (created) — 11 tests

---

## Applied Issues

### 1. [Correctness] `_write_preference` could not tell "leave the city alone" from "clear the city"

- **File**: `backend/apps/personalization/services/digest_preferences.py`
- **Description**: The upsert took `city` and `city_source` as `None`-or-value, and the
  branch that wrote them was guarded on `if city is not None or city_source is not None:`.
  A resolved `(None, None)` — which is exactly what "the user has no city" produces —
  therefore **skipped the write entirely**, and the stored city was never cleared.

  The docstring claimed the opposite: *"the stored city is never cleared — contradicting
  the design's D5/D8 intent"*. So the code and its own documentation disagreed.

  Two consequences, one of them serious:

  1. **The city could never be cleared.** A user who had a city and then declined
     location inference kept the old one — showing them events near a place they said
     they were not.
  2. **The backfill wrote nothing while claiming to write the fallback.** It called
     `set_home_city(city=None, ...)`, which took the same skip path. The command
     reported "Filled N accounts" and filled zero cities.

- **Fix**: An explicit `set_city` flag. `set_city=True` means *this call is about the
  city*, and then `city=None` means **clear it**. `set_city=False` (the default) leaves
  the stored city untouched.

  A sentinel would have had to mean "clear" in one call and "leave alone" in another,
  which is the same ambiguity the flag removes. The distinction is made by the caller,
  which is the only place that knows which it meant.

- **Pinned by**: `test_an_absent_city_clears_the_stored_one`,
  `test_the_backfill_fills_the_accounts_without_a_city`.

### 2. [Correctness] The backfill's source was rewritten from `backfill` to `fallback`

- **File**: `backend/apps/personalization/services/digest_preferences.py`
- **Description**: The backfill wrote `PREVIEW_FALLBACK_CITY` through `set_home_city`,
  which ran the **coverage check** — and the fallback is by definition the city the
  catalog may not currently serve. So the check replaced the fallback with the fallback
  and rewrote the source from `backfill` to `fallback`.

  The consequence defeats the point of the `city_source` column. A backfilled city
  became indistinguishable from a city the catalog rejected, so the digest could not
  say "we do not have your city yet" for one of them — which is the whole reason D14
  introduced the column.

- **Fix**: A separate `store_fallback_city` command that stores the fallback **as it
  is**, under the source the caller names. The coverage rule applies to a *caller's*
  city; the server chose this one, so there is nothing to check.

- **Pinned by**: `test_the_backfill_fills_the_accounts_without_a_city` (the source
  assertion), and `test_the_backfill_command_fills_the_accounts`.

### 3. [Correctness] The delivery time and the city were two commits

- **File**: `backend/apps/personalization/services/onboarding.py`
- **Description**: `set_digest_preference` wrote the delivery time inside its
  transaction, then called `set_home_city` **after** the transaction closed. A request
  that set both was therefore two commits, and the second could fail on its own.

  A half-applied digest preference is worse than a failed one: the row would say "8am"
  while the city said nothing changed, and **neither half would be wrong on its own** —
  which is the kind of state nobody notices until a user does.

- **Fix**: The city is written **inside** the delivery-time transaction. Django's nested
  `atomic` blocks use savepoints, so the inner command joins the outer transaction and
  rolls back with it.

- **Pinned by**: `test_a_failing_city_write_rolls_the_delivery_time_back`, which
  patches the city write to raise and asserts the delivery time was rolled back with
  it. **Verified by mutation**: against the two-commit version the test fails with

  ```
  assert (<DigestPreference: digest at 08:30:00 America/New_York> is None or 8 == 9)
  ```

### 4. [Code Quality] The audit-write block was duplicated

- **File**: `backend/apps/personalization/services/digest_preferences.py`
- **Description**: `set_home_city` and `store_fallback_city` each wrote the same audit
  row, with the same `details={"has_city": ..., "at": ...}`. Two copies of a privacy
  rule is two places for the rule to be edited wrong — and this particular rule is
  "the city never goes in the details".

- **Fix**: One `_write_city_audit` helper, called by both. The rule now has one home.

### 5. [Code Quality] `_canonical` had an unreachable branch

- **File**: `backend/apps/personalization/services/digest_preferences.py`
- **Description**: `_canonical` ended with `return city.strip()` — a branch that returns
  a city the catalog does not hold. It was unreachable, because the only caller checks
  `supported.supports(wanted)` first. Coverage confirmed it: line 188 was the module's
  one uncovered line.

  A branch that cannot be taken is still a branch a future caller can reach, and what it
  returns — a city under a spelling the catalog does not file events under — is exactly
  the bug the function exists to prevent.

- **Fix**: The unreachable fallback became a `raise ValueError`, and the docstring
  records the invariant: the caller has already checked, so a caller that does not
  fails loudly instead of quietly storing the wrong spelling.

- **Pinned by**: `test_the_canonical_lookup_fails_loudly_when_the_catalog_does_not_hold_the_city`.

### 6. [Documentation] The API contract promised a clearing it cannot express

- **File**: `backend/apps/personalization/schemas.py`, `backend/apps/personalization/api.py`
- **Description**: The schema's docstring said *"Clearing is explicit — a `null` city —
  never an omission."* That is false. In Pydantic a `null` city and an omitted city
  are the **same value**, so the shape cannot tell "leave it alone" from "clear it".

  A contract that promises something the shape cannot deliver is worse than no
  contract: a client written against it would send `city: null` expecting a clear, and
  get a leave-alone.

- **Fix**: The claim is inverted and the limitation is stated. A `null` city means
  **leave it alone**, and clearing is **not offered through this endpoint at all** — the
  service can clear it (`set_home_city(city=None)`), and a future settings endpoint may
  expose it through a shape that can distinguish the two.

  The alternative — consulting Pydantic's `model_fields_set` to tell "omitted" from
  "null" — was considered and **rejected**: the codebase uses that pattern nowhere, and
  introducing it for one field would make the contract's meaning depend on a subtlety
  a client author has to know.

- **Design**: D12 in the design doc now argues this rather than asserting the opposite.

### 7. [Testing] The atomicity claim was untested

- **File**: `backend/tests/personalization/test_digest_preferences.py`
- **Description**: Finding 3's fix was made without a test, so nothing would have
  caught a later regression to the two-commit shape.

- **Fix**: `test_a_failing_city_write_rolls_the_delivery_time_back`.

  The patch is applied to `onboarding`'s own namespace, because `onboarding` imports
  `set_home_city` by name — patching `digest_preferences.set_home_city` leaves the
  already-bound name in place and the failure never happens. The first attempt patched
  the wrong module and failed with `DID NOT RAISE RuntimeError`, which is how the
  mistake was caught.

---

## Considered and Not Changed

### The sign-up's city write is outside the account's transaction

**Kept, and argued.** The account is the thing that must not be half-made. An account
that exists without its audit row is a hole; an account that exists without a city is
merely a user whose city we do not know yet — a state the digest already handles (D5)
and one the backfill fills (D9). Rolling the account back because a city could not be
stored would lose a real sign-up over a preference, and would leave the caller with a
500 for an account that might or might not exist.

The reasoning is now in the service's comment rather than implicit, and the decision is
**D15** in the design doc — so the next reader sees the trade rather than the outcome.

### The city is not encrypted

**Kept, and it was already decided (D10).** The email address is encrypted because it
is a *credential* — it authenticates. A city is not a credential and authenticates
nothing. Encrypting it would make it unqueryable and unindexable for no gain.

---

## Verification

```
backend pytest                 3535 passed, 0 failed
backend coverage               99.11% overall; 176 files at 100%
backend coverage domain/*      100.00% (the AD-2 purity gate)
digest_preferences.py          100% (87 statements, 0 missed)
ruff check / format            All checks passed / 393 files formatted
import-linter                  19 contracts kept, 0 broken
makemigrations --check         No changes detected
make db-check                  database ready
make migrate                   0009 applied to both aliases
make lint-web                  eslint, tsc --noEmit and prettier all clean
make test-web                  429 passed
```

**The three correctness fixes were each verified by mutation** — the test covering each
one was confirmed to fail against the code it covers, and to pass against the fix.
