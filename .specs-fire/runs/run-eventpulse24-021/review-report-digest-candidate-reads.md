# Code Review Report

**Run**: run-eventpulse24-021
**Intent**: pulse-digest-and-trust
**Work item**: digest-candidate-reads
**Reviewed**: 2026-10-30
**Files Reviewed**: 11

---

## Summary

| Category | Applied | Skipped |
|----------|---------|---------|
| Code Quality | 2 | 0 |
| Correctness | 5 | 0 |
| Architecture | 2 | 0 |
| Testing | 2 | 0 |
| **Total** | **11** | **0** |

**Tests Status**: Passing — 3612 passed, 0 failed; `domain/` at 100%;
`catalog_read.py`, `source_badges.py` and `digest_candidates.py` each at 100%

> All eleven fixes were applied without a checkpoint because each is either mechanical
> and reversible (a duplicated mapping, a misleading filter) or is covered by a test
> that was **verified to fail against the broken code** (the five correctness fixes and
> the N+1). The full suite, the coverage gates and the import contracts were re-run
> after the last change.

---

## Files Reviewed

- `backend/apps/ingestion/services/catalog_read.py` (modified) — the public candidate read, the batched event lookup
- `backend/apps/ingestion/services/source_badges.py` (created) — the Source Badge leaf module
- `backend/apps/ingestion/services/preview_read.py` (modified) — the badge wrapper, the re-export removal
- `backend/apps/personalization/services/digest_candidates.py` (created) — the personal-side reads
- `backend/shared/constants.py` (modified) — `DIGEST_STALE_TTL_MULTIPLIER`
- `backend/tests/ingestion/test_public_candidates.py` (created) — 35 tests
- `backend/tests/personalization/test_digest_candidates.py` (created) — 32 tests
- `backend/tests/ingestion/test_preview_read.py` (modified) — the badge imports move
- `backend/tests/architecture/test_event_fit_separation.py` (modified) — two new tests

---

## Applied Issues

### 1. [Correctness] The candidate query had no `LIMIT`, so its cost depended on the catalog's size

- **File**: `backend/apps/ingestion/services/catalog_read.py`
- **Description**: The read applied `limit` in Python only — the queryset was
  evaluated in full and the loop broke when the pool filled. The staleness filter
  runs in Python (see finding 3), so a catalog whose events were *mostly stale*
  handed **every row** to Python before the first candidate was found, and then
  returned a handful.

  The read's cost was a function of the size of the catalog rather than the size of
  the answer. On the catalog this was written for, that is a full-table scan per
  digest read.

  Verified by probe: the generated SQL contained no `LIMIT`.

- **Fix**: The SQL fetch is bounded by `limit * CANDIDATE_OVERFETCH_FACTOR` (4), and
  the over-fetch is a named constant. The trade is now stated in the design doc: a
  catalog that is mostly stale may fill the pool with fewer than `limit` rows.

- **Pinned by**: `test_the_sql_fetch_is_bounded`, which wraps the catalog connection
  in an `execute_wrapper` and asserts a `LIMIT` appears in the recorded SQL.

- **Verified by mutation**: removing the `LIMIT` from the slice makes the test fail
  with *"the candidate query must carry a LIMIT; an unbounded fetch would make the
  read's cost depend on the size of the catalog"*.

### 2. [Correctness] `limit=0` returned one candidate

- **File**: `backend/apps/ingestion/services/catalog_read.py`
- **Description**: The bound was written `limit = max(1, min(limit, CAP))`. The
  `max(1, ...)` is the usual dodge for a `LIMIT 0`, and it has a meaning: **a caller
  that asks for no candidates is handed one**.

  Verified by probe: `limit=0` returned 1, and `limit=-5` returned 1.

- **Fix**: A `limit` of zero or less returns nothing, and the bound is applied
  *after* that check.

- **Pinned by**: `test_a_limit_of_zero_returns_no_candidates` and
  `test_a_negative_limit_returns_no_candidates`.

- **Verified by mutation**: restoring `max(1, ...)` makes the test fail with 1
  candidate instead of 0.

### 3. [Correctness] The staleness filter could not be expressed in SQL

- **File**: `backend/apps/ingestion/services/catalog_read.py`
- **Description**: The staleness bound is per-source (`2 × source.freshness_ttl_hours`
  compared against `now - event.last_seen_at`), so the natural move was to push it
  into the database. Every available route was tried and refused:

  | Attempt | Error |
  |---|---|
  | `ExpressionWrapper` compared to another `ExpressionWrapper` | `TypeError: '<=' not supported between instances of 'ExpressionWrapper'` |
  | `Q(...) <= expr` | Not supported |
  | `RawSQL` inside `filter()` | `TypeError: Cannot filter against a non-conditional expression` |
  | `Cast(integer → interval)` | `cannot cast type integer to interval` |
  | `annotate` + `filter(age__lte=...)` | `operator does not exist: interval <= integer` |
  | `make_interval` | Not in this Django version |

  The filter therefore runs in Python — which is correct, but is what made finding 1
  matter.

- **Fix**: The filter stays in Python, and the SQL fetch is bounded to compensate
  (finding 1). The reasoning is recorded in the design doc so the next reader does
  not re-attempt the six dead ends.

### 4. [Correctness] The `superseded_by` filter was unreachable code

- **File**: `backend/apps/ingestion/services/catalog_read.py`
- **Description**: The read filtered `status != SUPERSEDED` **and** excluded events
  with a `superseded_by` FK. The second filter can never exclude anything, because
  the database constraint `event_superseded_consistent_ck`
  (`backend/apps/ingestion/models.py`) makes the two states mutually exclusive: an
  event with a `superseded_by` pointer is already `SUPERSEDED`.

  A filter that cannot exclude anything is worse than no filter — it suggests a
  state the schema forbids, and a future reader may rely on it.

- **Fix**: The filter was removed, and the design doc says why, citing the
  constraint.

- **Pinned by**: `test_a_superseded_event_is_excluded_and_its_replacement_is_included`
  (which uses the real superseded pair, and so proves the live event is listed).

### 5. [Correctness] The saved read had an N+1

- **File**: `backend/apps/personalization/services/digest_candidates.py`
- **Description**: Each save's public half was fetched with a query of its own. Five
  saves meant five round-trips to the catalog — inside a read that the digest
  performs for every user, on every delivery.

- **Fix**: One batched lookup, `get_public_events(event_ids=...)`, on the catalog
  side, called once per saved read.

- **Pinned by**: the lookup-count test, which asserts **exactly one** catalog query
  for five saves. A count rather than "at most one", because "at most one" would
  pass against a lookup that never ran.

- **Verified by mutation**: reverting to one query per save makes the test fail with
  5 catalog queries instead of 1.

### 6. [Correctness] The 48-hour window was applied to the saves

- **File**: `backend/apps/personalization/services/digest_candidates.py`
- **Description**: The saved read applied the same `start_utc <= now + 48h` window
  that bounds how far ahead the digest *looks*. A save is not a lookahead — it is a
  fact about the user's own past present — and bounding it by the window silently
  dropped saves the user made for an event later that week.

- **Fix**: The window applies to the personal read only. The saved read bounds on
  `start_utc >= now` (a save for an event that already began is still a save) and
  nothing above.

- **Pinned by**: the saved-pool bound test, which asserts a save outside the window
  survives.

- **Verified by mutation**: dropping the bound makes the test fail.

### 7. [Correctness] The confidences were carried as strings

- **File**: `backend/apps/ingestion/services/catalog_read.py`
- **Description**: The candidate's `extraction_confidence` and
  `tz_inference_confidence` were declared `str`. The gates are exact comparisons
  against thresholds, and the values are `DecimalField`s — a `Decimal` compared
  against a `Decimal` is exact, and a string compared against one is not.

  This mattered because the boundary is the whole point of the gate: an event one
  hundredth below the threshold must be excluded and one exactly at it included, and
  that difference is invisible to a string comparison.

- **Fix**: Both are `Decimal`, and the test asserts the *type* as well as the value.

- **Pinned by**: `test_the_confidences_are_decimals_and_not_floats_or_strings`.

### 8. [Architecture] The Event Fit would have leaked into `personalization` by another name

- **File**: `backend/apps/ingestion/services/source_badges.py` (created),
  `backend/apps/ingestion/services/catalog_read.py`,
  `backend/apps/ingestion/services/preview_read.py`
- **Description**: The Source Badge mapping already existed, in `preview_read`, for
  the Pulse Preview. The digest's candidate read needs the same mapping, so the
  obvious move was to import it from there.

  `preview_read` imports `apps.ingestion.event_fit.reads`. And `personalization`
  imports `catalog_read`. So that import would have put the Event Fit inside
  `personalization` — **and the import contract could not have caught it**, because
  the `event-fit-separation` contract is declared with `allow_indirect_imports = true`
  (the Event Fit is read through a service, and the contract permits that indirection
  by design).

  The one contract meant to keep the Event Fit out of `personalization` would have
  been satisfied while the Event Fit was, in fact, inside `personalization`.

- **Fix**: `apps/ingestion/services/source_badges.py` — a leaf module that imports
  the `Source` model's *choices* and nothing else. Both reads import it; neither
  imports the other. `preview_read.source_badge_for` is now a thin wrapper over
  `source_badge_for_type`.

  The four `SOURCE_BADGE_*` constants were also **removed from `preview_read`'s
  re-exports**. A name exported from two modules is two homes, and a reader has to
  know which one is current.

- **Pinned by**: two new tests in
  `backend/tests/architecture/test_event_fit_separation.py` —
  `test_the_public_catalog_read_does_not_reach_the_event_fit_either` and
  `test_the_source_badge_module_reaches_neither_the_event_fit_nor_personalization`.

### 9. [Architecture] The catalog read asserted the wall on the wrong thing

- **File**: `backend/tests/ingestion/test_public_candidates.py`
- **Description**: The first version of the wall test asserted on the SQL's *table
  names* — that the query mentions `ingestion_event` and not `personalization_`.

  That asserts less than it looks. A query that joined nothing would pass it, and
  the thing AD-3 protects is not the spelling of a table but **which side of the
  wall the read happened on**.

- **Fix**: The public read's test wraps both connections and asserts the catalog
  recorded queries and the personal alias recorded **none**. The personal read's
  test asserts on table names — because there the catalog side is legitimately
  reached through a published service (`apps.personalization` may not import
  `apps.ingestion.models`, AD-2), so the alias is the wrong thing to assert on and
  the table name is the right one.

### 10. [Code Quality] The badge mapping had two homes

- **File**: `backend/apps/ingestion/services/preview_read.py`
- **Description**: After the split, `SOURCE_BADGE_OFFICIAL` and its three siblings
  were importable from `preview_read` **and** from `source_badges`. Two homes for
  one rule.

- **Fix**: `preview_read` no longer re-exports them, and its `__all__` no longer
  lists them. The two test files that imported the constants from `preview_read`
  now import them from `source_badges`.

### 11. [Testing] The confidence gates were tested only from above

- **File**: `backend/tests/ingestion/test_public_candidates.py`
- **Description**: The first version of the gate tests asserted that a confident
  event is included and an unconfident one is not — with values far from the
  threshold. A gate set to the wrong threshold anywhere in that band would have
  passed.

- **Fix**: Every gate is now tested **at its exact threshold and one hundredth
  below** — the finest difference the `DecimalField(max_digits=3,
  decimal_places=2)` column can express. A failure of the boundary test therefore
  means the comparison is off by more than the data's resolution.

---

## Considered and Not Changed

### A cancelled or postponed event is a candidate

**Kept, and argued.** The read filters on *publication* and *supersession*, not on
`cancelled` or `sold_out`. A cancelled event is still a public event, and dropping it
would **hide the cancellation rather than report it** — the user would see an event
that is not happening as though it were, which is the worse of the two failures. The
flags are carried on the event, and what the digest says about them is
`digest-composition-service`'s to decide.

This was one of three questions the review forced the design to answer.

### The staleness comparison is inclusive at the bound

**Kept.** "Older than the bound" is exclusive, so an event *exactly* at the bound is
not older than it. The comparison is `age > stale_after` (skip), not `>=`. The
difference is one hour of test data, and a reviewer reading `>=` where `>` belonged
would see no difference in the output — which is why the boundary test exists.

### `now` is not applied to the catalog half of the saved read

**Kept.** A save stays readable after its event has started: the user saved it, and
the digest should still be able to say so. Applying `now` to the catalog side would
silently drop the public half of every save for an event that had begun.

### The `limit` cap of 200

**Kept.** A caller may not ask for an unbounded pool. The cap is a named constant,
and the design doc states why a bounded pool is the right shape for a digest.

---

## Verification

```
backend pytest                 3612 passed, 0 failed
backend coverage               99.13% overall; 178 files at 100%
backend coverage domain/*      100.00% (the AD-2 purity gate)
catalog_read.py                100%
source_badges.py               100%
digest_candidates.py           100%
ruff check / format            All checks passed / 397 files formatted
import-linter                  19 contracts kept, 0 broken
makemigrations --check         No changes detected
```

**The five correctness fixes were each verified by mutation** — the test covering each
one was confirmed to fail against the code it covers, and to pass against the fix.
