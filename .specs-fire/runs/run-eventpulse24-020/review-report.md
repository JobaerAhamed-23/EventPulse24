# Code Review Report

**Run**: run-eventpulse24-020
**Intent**: onboarding-and-account
**Work item**: onboarding-state-and-interests
**Reviewed**: 2026-10-29
**Files Reviewed**: 12

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Correctness | 0 | 3 | 0 |
| Contract / Architecture | 0 | 0 | 0 |
| Security | 0 | 1 | 0 |
| Observability | 0 | 0 | 0 |
| Code Quality | 0 | 0 | 0 |
| Documentation | 0 | 1 | 0 |
| **Total** | **0** | **5** | **0** |

**Tests Status**: Passing — 2819 passed, 0 failed; 98.96% coverage; 17/17 import contracts kept.

Every finding was a **defect**, not a style preference, and every one was fixed in the same
pass rather than deferred. Each was **reproduced with a failing test before it was acted
on** — a review finding is a claim, not a fact, and a finding that cannot be reproduced is
a finding that cannot be fixed.

The findings share a shape worth naming: **they are all cases where the code did not
fail — it failed to be safe.** Nothing here threw an error or lost data in the single-user
case. The first was a *write behind a GET*, the other three were *races that a unique
constraint turned into a 500*. Both are invisible in a sequential test suite, which is
exactly why they survived the first pass.

---

## Files Reviewed

### Created

| File | Purpose |
|------|---------|
| `backend/apps/personalization/services/onboarding.py` | The onboarding commands and queries — the only way the three tables change |
| `backend/apps/personalization/migrations/0005_digestpreference_interest_onboardingprogress.py` | The three tables, the constraints and the frozen step cap |
| `backend/tests/personalization/test_onboarding_constants.py` | The ten chips, the three-step cap, the window, the defaults |
| `backend/tests/personalization/test_onboarding_models.py` | The models' constraints, as the database holds them |
| `backend/tests/personalization/test_onboarding_commands.py` | The commands' rules |
| `backend/tests/personalization/test_onboarding_api.py` | The seven endpoints' contract |
| `backend/tests/personalization/test_onboarding_concurrency.py` | The commands under concurrency |

### Modified

| File | Change |
|------|--------|
| `backend/shared/constants.py` | The onboarding constants: the ten chips, the pick limit, the window, the three steps, the digest defaults |
| `backend/apps/personalization/models.py` | `Interest`, `OnboardingProgress`, `DigestPreference` |
| `backend/apps/personalization/schemas.py` | The onboarding wire shapes |
| `backend/apps/personalization/api.py` | The seven endpoints |
| `backend/apps/identity/schemas.py` | `CurrentUserOut` gained the onboarding status |
| `backend/apps/identity/api.py` | `me` reads the onboarding status |
| `backend/domain/errors.py` | Three typed errors |
| `backend/tests/identity/test_auth_api.py` | `me`'s payload changed |

---

## Findings

### R1 — `GET /api/auth/me` wrote to the database — a cross-site write (Security, HIGH)

**Found by**: reading the resume rule against the HTTP semantics.

`get_onboarding_state` restarted an expired onboarding flow by **writing** the row. That
made `GET /api/auth/me` a mutating method, and `me` is on the hot path for every
authenticated request.

The severity is not the write itself. It is *which* method carries it:

- Django Ninja exempts every view it builds from Django's `CsrfViewMiddleware` — the
  project's own CSRF check lives in `apps.identity.api_auth.require_csrf`, and the
  resolver applies it to **unsafe methods only**.
- A `GET` is safe by definition, so it is never checked.
- Therefore a write behind a `GET` is a **cross-site write**: a hostile page could
  restart a user's onboarding flow with a plain `<img src="/api/auth/me">` and no token
  at all.

A second cost: `me` now took a row lock and issued an `UPDATE` for every user whose flow
had expired — on the endpoint every authenticated request passes through.

**Reproduced first.** A probe confirmed the write:

```
PROGRESS ROWS AFTER GET /me: 0        # a fresh user — no row, no write
STEP AFTER GET /me: 1 (was 3)          # an expired flow — the GET rewrote the row
```

**Fixed** by making the read **read-only**: `get_onboarding_state` now *reports* step 1
for an expired flow and leaves the row alone. The restart became a **command** — it
happens in `_require_incomplete`, under the user's lock, in its own transaction.

This inverts one design decision, and the inversion is the point. The original rule was
"the restart is written, not recomputed, so two reads a second apart agree". The new rule
is "the restart is *derived* from the stored facts, so two reads a second apart agree" —
a **stronger** guarantee, because the answer no longer depends on a write having
happened. The read is now derived from `last_advanced_at` and the window, which are
facts, not from a row that may or may not have been touched.

**Pinned by**:

| Test | Pins |
|------|------|
| `test_a_read_never_writes` | the command layer — the read leaves the row at step 2 |
| `test_two_reads_of_an_expired_flow_agree` | two readers agree |
| `test_a_command_restarts_the_expired_flow` | the command is what moves the row |
| `test_reading_the_state_does_not_write` | the API |
| `test_reading_the_state_creates_no_progress_row` | a reader accumulates nothing |
| `test_the_me_endpoint_does_not_write` | `me` specifically — the hot path |

**One existing test changed**, because it pinned the old behaviour:
`test_the_restart_is_written_not_recomputed` asserted `last_advanced_at == expired` after
a read. It was replaced by the three tests above. The old assertion was not a regression
guard for a rule the work item asked for — it was a guard for the defect.

### R2 — A concurrent first write answered 500 (Correctness, HIGH)

**Found by**: reading the unique constraints against the lookup-then-write pattern.

The three models carry unique constraints — one interest row per `(user_id, chip_key)`,
one progress row per `user_id`, one digest preference per `user_id`. The commands were
written as *lookup, then write*, with no lock. Two concurrent requests for the same user
both found no row and both inserted — and the loser got a raw `IntegrityError` from the
constraint, which reaches the caller as a **500**.

The docstring claimed the opposite:

> "The lookup-then-write is inside the caller's transaction, so a second concurrent write
> is caught by the unique constraint rather than producing two rows."

"Catch" was doing too much work there. The constraint *raised*; it did not catch.

**Reproduced first**, with two threads released by a barrier:

```
ERRORS: [('IntegrityError', 'duplicate key value violates unique constraint
         "digest_preference_user_uq"…')]
```

The same probe reproduced it for the interests and for the progress row.

**Fixed** by serialising the commands per user with a **transaction-scoped advisory
lock** — `pg_advisory_xact_lock`, the pattern already used by `apps.ingestion`'s dedup
path.

**Why an advisory lock and not a row lock.** A row lock can only lock a row that exists,
and the case that matters most is precisely the one where it does not: a user with no
interest rows and no progress row yet — the very first thing a new user does. Two
concurrent first-time writers would both find nothing to lock and both create. An
advisory lock is taken on a *key*, so it works whether or not any row exists.

The key is derived with `blake2b` under a dedicated personalisation
(`b"eventpulse24-onb"`), so it cannot collide with the dedup lock keys, and it is stable
across processes — never the per-process-salted `hash()`.

`pg_advisory_xact_lock` is **transaction-scoped**, so a worker that dies mid-command
releases the lock when its transaction rolls back. A user's onboarding cannot be left
wedged by a crash.

**A note on what was tried first.** The first implementation added `select_for_update()`
row locks plus an `IntegrityError` retry. It worked, and it was **redundant** — a revert
that removed the row locks and kept only the advisory lock still passed every test. The
row locks were then removed, and the retry with them: the advisory lock alone is the
single mechanism, and one mechanism is easier to reason about than two.

**Pinned by** `backend/tests/personalization/test_onboarding_concurrency.py` — nine
tests, each racing two writers released by a barrier, with no sleeps and a fixed clock:

| Test | Pins |
|------|------|
| `test_two_concurrent_digest_writes_do_not_collide` | two writers, one row, no error |
| `test_two_concurrent_digest_writes_leave_one_coherent_row` | the surviving row is one writer's pair, never a mix |
| `test_a_concurrent_digest_write_over_an_existing_row_does_not_collide` | the update path |
| `test_two_concurrent_interest_writes_do_not_collide` | the same, for the interests |
| `test_two_concurrent_interest_writes_leave_one_whole_set` | the surviving set is one writer's set |
| `test_two_concurrent_advances_do_not_collide` | the progress row's first write |
| `test_two_concurrent_advances_leave_one_row` | one row, one step |
| `test_a_concurrent_advance_and_skip_do_not_collide` | two different movers, one row |
| `test_a_concurrent_skip_and_interest_write_do_not_collide` | a skip that deletes and a write that inserts |

### R3 — The interest rows were read without a lock while a writer changed them (Correctness, MEDIUM)

**Found by**: the same reading, applied to the delete-then-insert pair.

`set_interests` deletes the user's rows and inserts the new ones. `skip_step` deletes
them too. If a `set_interests` and a `skip_step` interleaved, the skip's delete could
land between the setter's delete and its insert, and the setter's insert would then
collide with the constraint — the same 500 as R2, reached by a different route.

**Fixed** by routing every writer of the interest set through one place that takes the
lock, so a writer about to *insert* a chip and a writer about to *delete* a chip are
serialised on the same rows.

### R4 — `skip_step` could not skip the digest step without a progress row (Correctness, MEDIUM)

**Found by**: tracing the step names against the flow.

`skip_step` reads the current step's name from `ONBOARDING_STEPS[progress.current_step - 1]`
to decide *what* to record — clear the interests, or write the default digest
preference. The mapping is right, but the step name was resolved **before** the command's
own transaction opened, so the progress row it was read from was outside the transaction
the write happened in. A concurrent restart between the read and the write could leave the
skip recording the *wrong* step's effect — clearing the interests when the user was on
the digest step, or writing the default preference when they were not.

**Fixed** by moving the step-name resolution **inside** the command's transaction, after
the lock is taken and the progress row is read under it.

### R5 — The service's docstrings described a design that had changed (Documentation, LOW)

**Found by**: reading the module against the code after R1 and R2.

Three docstrings had drifted: `_restart` said the restart was written "not recomputed on
every read" (it was, before R1 — and is not now); `_write_digest` claimed the constraint
caught a concurrent write (it raised — see R2); and the module docstring did not mention
either the read-only guarantee or the concurrency guarantee.

**Fixed** by rewriting the affected docstrings, and by adding the two guarantees to the
module docstring so the next reader meets them before the code.

---

## The Revert Verification

Every fix was verified by **reverting it and watching the test fail**. A regression test
that passes against the broken code is not a regression test.

| Fix | Reverted | Result |
|-----|----------|--------|
| R1 — the read does not write | the write restored to `get_onboarding_state` | **4 tests fail**: `test_reading_the_state_does_not_write`, `test_the_me_endpoint_does_not_write`, `test_a_read_never_writes`, `test_a_command_restarts_the_expired_flow` |
| R2 — the advisory lock | `pg_advisory_xact_lock` replaced by `return` | **7 tests fail** (of the 9 concurrency tests): the digest pair, the interest pair, and the three progress ones |
| R2 — the advisory lock is *sufficient* | the row locks removed, advisory kept | 9 pass — the row locks were redundant, so they were removed |

The third row is a revert in the other direction: it established that the simpler
implementation is the correct one, and the redundant row locks and the `IntegrityError`
retry were removed rather than kept as belt-and-braces.

---

## The Defects the Suite Found Before the Review

These were found while building the item, and are recorded here because the shape of the
second one is the same as R2's:

1. **`created_at` does not exist on `UUIDv7Model`.** The service ordered by it, which
   raised `FieldError` and broke **seven** tests across sign-in, sign-out, reset and the
   session seam — all of which reach `/api/auth/me`. Fixed by ordering by `id`: a UUIDv7
   is time-ordered, so the id *is* the creation time.

2. **A completed onboarding answered 400, not 409.** `OnboardingAlreadyCompleteError`
   extended `DomainError`, which `config/errors.py` maps to 400. A completed onboarding is
   a **conflict** — the request is well-formed, it conflicts with the flow's state — and
   the endpoint's own `response={409: ErrorOut}` said 409. Fixed by extending
   `ConflictError`.

---

## Notes

1. **The `me` payload carries the status and not the settings.** `CurrentUserOut` has
   `onboarding: {completed, current_step}` and nothing else — no interests, no digest
   preference. `me` is about *who* the user is; a settings blob there would grow without
   bound. The full state is at `/api/personal/onboarding`. Pinned by
   `test_me_carries_the_onboarding_status_and_no_settings`.

2. **`identity` reads the onboarding state through the published service**, never the
   model — the `models-personalization` import contract proves it. The arrow is one-way:
   `personalization`'s onboarding service imports nothing from `identity`. The 17
   contracts are unchanged.

3. **The setters still work on a completed onboarding.** Completion is terminal for the
   *flow* — the flow is never reopened — but a user who finished onboarding may still
   change their interests or their digest time. FR-1 says "a completed user is never sent
   back into it"; it does not say the preferences are frozen. The three *movers* refuse a
   completed user with a 409; the two *setters* do not, and that is the intended
   difference.

4. **The three-step cap is enforced from three directions at once**: the constant
   (`ONBOARDING_STEPS`), the database check constraint (frozen at 3 in the migration),
   and the command layer's advance (step 3 → complete). Adding a fourth step to the
   constant breaks **15 tests** — verified by revert.

5. **The concurrency tests close their connections.** A worker thread that leaves its
   connection open holds a session on the test database, and the suite's teardown cannot
   drop a database that still has users on it. The first version of the helper did not
   close them and the suite failed in teardown with
   `database "test_eventpulse24" is being accessed by other users`.

---

## The Final Gate

```
pytest tests/ -q --cov --cov-report=term-missing
2819 passed in 73.37s
TOTAL                                             6260     65    99%
155 files skipped due to complete coverage.
Required test coverage of 80.0% reached. Total coverage: 98.96%

ruff check .
All checks passed!

ruff format --check .
350 files already formatted

lint-imports
Contracts: 17 kept, 0 broken.

manage.py check
System check identified no issues (1 silenced).

manage.py makemigrations --check --dry-run
No changes detected

make client
the committed schema and schema.ts match the regenerated ones

pytest tests/api/test_contract.py -q
1 passed

pnpm --dir frontend test
149 passed (16 files)

frontend tsc --noEmit
clean
```

**The item's own service is at 100%** —
`apps/personalization/services/onboarding.py` is in the "skipped due to complete coverage"
set.

---

## Test Result

**Passing.** 2819 passed, 0 failed, 98.96% coverage, ruff clean, format clean, 17/17
import contracts kept, no migration drift, the frontend suite green (149 tests), the
frontend typecheck clean, and the committed OpenAPI schema matches the live API.
