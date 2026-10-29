---
run: run-eventpulse24-020
work_item: onboarding-state-and-interests
intent: onboarding-and-account
generated: 2026-10-29
status: passing
---

# Test Report: Onboarding State & Interests (FR-1)

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Item-scoped | 104 | 0 | 0 | 100% (the item's modules) |
| **Total (whole backend)** | **2819** | **0** | **0** | **98.96%** |

The 104 item-scoped tests are a subset of the 2819-test backend suite. The whole backend
suite is **2819 passed, 0 failed** in 73.37s; coverage is **98.96%** across 6260
statements, with **155 files at 100%**.

**Every module this item created or changed is at 100%** — notably
`apps/personalization/services/onboarding.py`. The 65 uncovered statements are pre-existing
gaps elsewhere in the codebase.

## Test Commands

```bash
# The item's own tests
cd backend && .venv/bin/python -m pytest \
    tests/personalization/test_onboarding_constants.py \
    tests/personalization/test_onboarding_models.py \
    tests/personalization/test_onboarding_commands.py \
    tests/personalization/test_onboarding_api.py -q

# The whole backend suite, with coverage
cd backend && .venv/bin/python -m pytest tests/ -q --cov --cov-report=term-missing

# The linter and the format check
cd backend && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .

# The import contracts
cd backend && .venv/bin/lint-imports

# Django's own checks and the migration drift
cd backend && .venv/bin/python manage.py check
cd backend && .venv/bin/python manage.py makemigrations --check --dry-run

# AD-19: the schema and the TypeScript client regenerate with no drift
make client

# The frontend suite (the client is regenerated from the OpenAPI schema)
pnpm --dir frontend test
```

## What Was Added

| File | Tests | Covers |
|------|-------|--------|
| `backend/tests/personalization/test_onboarding_constants.py` | 11 | The ten chips, their order and their uniqueness; the three-step cap derived from the tuple; the 7-day window; the default digest time and zone |
| `backend/tests/personalization/test_onboarding_models.py` | 17 | The three models: the user held by value, the uniqueness constraints, the step range check, the retention categories, the wall-clock time |
| `backend/tests/personalization/test_onboarding_commands.py` | 42 | The commands: replace semantics, the pick limit, the unknown key, the zone and time validation, the step transitions, the resume window, the terminal state |
| `backend/tests/personalization/test_onboarding_api.py` | 26 | The seven endpoints: the chip list, the 401s, the two setters, the three movers, the CSRF refusal, the session scoping, and the safe-methods guarantee |
| `backend/tests/personalization/test_onboarding_concurrency.py` | 9 | The commands under concurrency: two writers, one row, no `IntegrityError` |

## What Was Changed in the Existing Tests

Exactly one existing test file changed, and it changed because the `me` payload changed:

`backend/tests/identity/test_auth_api.py` — `me` now carries the onboarding status, so
`test_me_returns_the_id_the_email_and_the_onboarding_status_and_nothing_else` asserts the
payload includes `{"onboarding": {"completed": False, "current_step": 1}}`. A companion
test, `test_me_carries_the_onboarding_status_and_no_settings`, gives the user interests
and a digest preference and asserts that **neither** appears on `me` — the status is on
`me`; the settings are not.

## The Properties Pinned

### The chips live in one place

- `test_the_chip_list_comes_from_the_constant` — the API projects the constant, so the
  labels exist exactly once.
- `test_the_chip_labels_are_the_ten_in_order` — the order the step-2 mockup shows.
- `test_the_chip_keys_are_unique_slugs` — a key is a stable identifier; a duplicate key
  would orphan a user's stored pick.

### The pick limit is three

- `test_more_than_three_picks_is_refused` — the extra picks are **refused**, not
  silently dropped, and nothing is written.
- `test_exactly_three_picks_are_allowed` — the limit is three, not two.

### The key is the contract, the label is prose

- `test_an_unknown_chip_key_is_refused` — the offending key is **named** in
  `details["chip_key"]`, so the caller can say which one it got wrong.
- `test_a_label_is_not_a_key` — "Tech & meetups" is refused; the API takes keys.

### The interests replace, they do not accumulate

- `test_setting_interests_replaces_the_set` — three chips then one leaves one.
- `test_zero_picks_is_valid_and_clears_the_set` — zero is how the step is skipped, and it
  clears.
- `test_a_duplicate_key_in_one_call_is_deduplicated` — a repeated key is deduplicated, not
  refused: it is not a mistake worth a refusal.

### The digest preference is validated by the shared validator

- `test_a_non_iana_timezone_is_refused` — the same validator personal events use.
- `test_an_ambiguous_timezone_is_refused` — a fixed offset is not a zone an event can
  happen in.
- `test_the_zone_is_stored_canonically` — "Etc/UTC" is stored as "UTC".
- `test_a_delivery_time_with_an_offset_is_refused` — a wall clock carries no offset.
- `test_a_delivery_time_that_is_not_a_time_is_refused` — the service refuses a non-time
  even though the API's schema already guarantees one: the service is a published
  interface, and other callers reach it without the schema.

### The resume window is inclusive and the restart is written

- `test_a_user_is_resumed_at_the_same_step_within_the_window` — one second inside.
- `test_a_user_at_the_window_boundary_is_still_resumed` — **at** exactly the window, the
  step is kept.
- `test_onboarding_restarts_at_step_one_after_the_window` — one second beyond, the flow
  starts again.
- `test_the_restart_is_written_not_recomputed` — two reads a second apart agree about the
  step, because the restart is a row, not a calculation.
- `test_a_write_against_an_expired_progress_row_restarts_it` — the write sees the same
  expiry the read does, so a user who comes back after the window and *advances* starts
  from step 1, not from the step they left weeks ago.

### Completion is terminal

- `test_a_completed_user_is_never_sent_back_into_onboarding`.
- `test_a_completed_user_stays_complete_after_the_window_expires` — completion outranks
  the resume rule; the window never reopens a finished flow.
- `test_advancing_a_completed_onboarding_is_refused`,
  `test_skipping_a_completed_onboarding_is_refused`,
  `test_skipping_all_twice_is_refused` — the refusal is at the command, so the row is
  untouched.

### Every step can be skipped with empty input

- `test_every_step_can_be_skipped_with_empty_input` — three skips, no input at all, and
  the flow completes.
- `test_skipping_the_digest_step_writes_the_default_preference` — the default is
  **written**, not assumed, so `delivery` reads one row rather than branching on "was it
  set?".
- `test_skip_all_writes_the_default_digest_preference` and
  `test_skip_all_clears_the_interests`.

### The database is the backstop

- `test_the_same_chip_cannot_be_held_twice` — written directly, bypassing the service, so
  it pins the **constraint** rather than the command's replace semantics.
- `test_a_user_has_one_progress_row`, `test_a_user_has_one_digest_preference`.
- `test_the_step_must_be_inside_the_three_step_range` — steps 4 and 0 are refused by the
  database; 1, 2 and 3 are accepted.
- `test_an_interest_holds_the_user_by_value` — OQ-8: no relation to `User`, no
  `GenericForeignKey`; `not Model._meta.related_objects`.

## Acceptance Criteria Validation

| Criterion | Result | Where it is pinned |
|-----------|--------|-------------------|
| The ten interest chips exist in one place, keys and labels separate | ✅ | `test_onboarding_constants.py` (11 tests); the API projects the constant |
| At most 3 picks; a fourth is refused, not dropped | ✅ | `test_more_than_three_picks_is_refused`, `test_exactly_three_picks_are_allowed` |
| Interests **replace**, and zero is valid | ✅ | `test_setting_interests_replaces_the_set`, `test_zero_picks_is_valid_and_clears_the_set` |
| An unknown key is refused and named | ✅ | `test_an_unknown_chip_key_is_refused`, `test_a_label_is_not_a_key` |
| The digest zone is validated by the shared validator; the canonical name is stored | ✅ | `test_a_non_iana_timezone_is_refused`, `test_an_ambiguous_timezone_is_refused`, `test_the_zone_is_stored_canonically` |
| The digest preference is one row per user | ✅ | `test_the_digest_preference_is_one_row_per_user`, `test_a_user_has_one_digest_preference` |
| A user is resumed at the same step within 7 days; the window is inclusive | ✅ | `test_a_user_at_the_window_boundary_is_still_resumed`, `test_onboarding_restarts_at_step_one_after_the_window` |
| The flow has at most 3 user-visible steps | ✅ | `test_the_step_count_is_derived_from_the_steps`; the DB check constraint; `test_advancing_past_the_last_step_completes_the_onboarding` |
| Every step can be skipped, and no step requires any input | ✅ | `test_every_step_can_be_skipped_with_empty_input`, `test_skip_all_completes_the_onboarding` |
| Completion is terminal | ✅ | the four terminal-state tests in `test_onboarding_commands.py` |
| The onboarding endpoints live under `/api/personal/onboarding` and require a session | ✅ | `test_onboarding_api.py` — the 401 on every endpoint, the CSRF 403 |
| `GET /api/auth/me` carries the onboarding status and nothing else | ✅ | `test_me_carries_the_onboarding_status_and_no_settings` |
| The user is held by value (OQ-8) | ✅ | `test_an_interest_holds_the_user_by_value`, `test_a_progress_row_holds_the_user_by_value`, `test_a_digest_preference_holds_the_user_by_value` |
| Every concrete model declares a retention category (AD-15) | ✅ | the three retention-category tests |
| Writes are named commands with an audit row (AD-5) | ✅ | the commands take an explicit `Actor` and `now`, never `request` |
| OpenAPI regenerates; the client regenerates with `make client` | ✅ | `make client` was re-run and committed; `tests/api/test_contract.py::test_committed_openapi_schema_matches_the_live_api` passes |
| The import contracts pass | ✅ | `lint-imports`: 17 kept, 0 broken |
| No migration drift | ✅ | `makemigrations --check --dry-run` → No changes detected |

## Reverting Each Fix

Every rule was verified by **reverting it and watching the test fail**. A regression test
that passes against the broken code is not a regression test.

| # | Rule | Reverted | Result |
|---|------|----------|--------|
| 1 | The window is inclusive | `>` → `>=` | `test_a_user_at_the_window_boundary_is_still_resumed` fails (`assert 1 == 3`) |
| 2 | Completion is terminal | the raise removed | 5 tests fail; the API answers 200 instead of 409 |
| 3 | The interests replace | the `delete()` removed | 4 tests fail (`At index 0 diff: 'tech_meetups' != 'family_kids'`) |
| 4 | The IANA refusal | the raw name returned | 3 tests fail; the API answers 200 instead of 422 |
| 5 | The 3-pick limit | compared against the chip count | 2 tests fail; the API answers 200 instead of 422 |
| 6 | The unknown key | `continue` | 3 tests fail; the API answers 200 instead of 422 |
| 7 | The default is written | the `elif` gutted | 1 test fails (`assert None == datetime.time(9, 0)`) |
| 8 | The 3-step cap | `+ 1` | **15 tests** fail, including the step-count test |

All eight reverts were restored and the suite re-run green afterwards; `git diff --stat`
confirmed no revert artifacts remained.

### The review's reverts

The code review found five more defects, each reproduced with a failing test before it was
fixed, and each verified by reverting it:

| Fix | Reverted | Result |
|-----|----------|--------|
| The read never writes | the write restored to `get_onboarding_state` | **4 tests fail**: `test_reading_the_state_does_not_write`, `test_the_me_endpoint_does_not_write`, `test_a_read_never_writes`, `test_a_command_restarts_the_expired_flow` |
| The advisory lock | `pg_advisory_xact_lock` replaced by `return` | **7 of the 9** concurrency tests fail: the digest pair, the interest pair, and the three progress ones |
| The advisory lock is sufficient | the row locks removed, advisory kept | 9 pass — the row locks were redundant, so they were removed rather than kept |

The third row is a revert in the other direction: it established that the **simpler**
implementation is the correct one.

## Notes on the Implementation

Two defects were found by the suite while this item was being built, and both are fixed
and regression-tested:

1. **`created_at` does not exist on `UUIDv7Model`.** The service ordered the interests and
   the digest preference by `created_at`, which raised
   `FieldError: Cannot resolve keyword 'created_at' into field`. This broke seven tests —
   sign-in, sign-out, reset and the session-seam tests — because they all reach
   `/api/auth/me`, and `me` now reads the onboarding state. **Fixed** by ordering by `id`:
   a UUIDv7 is time-ordered, so the id *is* the creation time. The service's docstring now
   says so, because the reason is not obvious.

2. **A completed onboarding answered 400, not 409.** `OnboardingAlreadyCompleteError`
   extended `DomainError`, which `config/errors.py` maps to 400. A completed onboarding is
   a **conflict** — the request is well-formed but conflicts with the flow's state — and
   the endpoint's own `response={409: ErrorOut}` declaration said 409. **Fixed** by making
   the error extend `ConflictError`. The test
   `test_advancing_a_completed_onboarding_is_refused` now pins the 409.

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

## What This Item Does Not Cover

- The **frontend** onboarding flow — `frontend-onboarding-flow` owns the three steps, the
  chip grid and the digest picker.
- The **calendar connect API** — step 1's calendar connection belongs to
  `calendar-connect-api`; this flow only records that the step was passed.
- The **Pulse Digest** consuming the delivery time and the zone — the preference is
  stored here; the delivery job reads it in `pulse-preview-api-and-geo`.
- **Interests for ranking** — the picks are stored and served; nothing consumes them for
  ranking yet.
- A **Pro tier** — there is no subscription entity yet.

### Test Result

**Passing.** 2819 passed, 0 failed, 98.96% coverage, 100% on the new service, ruff clean,
format clean, 17/17 import contracts kept, no migration drift, the frontend suite green
(149 tests), the frontend typecheck clean, and the committed OpenAPI schema matches the
live API.
