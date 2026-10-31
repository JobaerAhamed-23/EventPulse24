---
run: run-eventpulse24-022
work_item: conflict-list-api
intent: timeline-and-conflicts
generated: 2026-10-31T06:33:07Z
status: passed
---

# Test Report: The conflict list — every pair, both sides, by name

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit | 0 | 0 | 0 | — |
| Integration | 20 | 0 | 0 | 100% |
| **Total (this work item)** | **20** | **0** | **0** | **100%** |

**Full backend suite**: 3946 passed, 1 failed (pre-existing, see Issues), 98.69% overall
coverage, 100% on `domain/`.

## Acceptance Criteria Validation

- ✅ **Returns `{active: [...], resolved: [...]}` for the caller only; anonymous is 401** —
  `test_the_list_holds_only_the_callers_pairs`,
  `test_another_users_pairs_are_not_in_the_list`,
  `test_an_anonymous_caller_is_refused`,
  `test_the_endpoint_does_not_reveal_another_users_pairs`.
- ✅ **Each pair carries `pair_id`, `kind`, `status`, both sides as
  `{kind, id, name, start_time_utc, end_time_utc, start_time_tz}`, and the allowed
  actions from the one `RESOLUTIONS_BY_KIND`** —
  `test_a_pair_carries_both_sides`, `test_an_active_pair_offers_the_actions_for_its_kind`,
  `test_a_duplicate_pair_offers_the_actions_for_its_kind`,
  `test_a_resolved_pair_carries_its_resolution_and_no_actions`.
- ✅ **A saved side is named by its catalog title, in one batched read for the whole list
  (no per-pair query)** — `test_a_saved_side_is_named_by_its_catalog_title`,
  `test_the_list_costs_one_catalog_read_for_every_saved_side`.
- ✅ **A saved side whose catalog event is gone reads as an explicit "event no longer
  available" state** — `test_a_deleted_saved_event_reads_as_no_longer_available`. The same
  explicit state covers a deleted personal event and a deleted save row.
- ✅ **`cleared_by_state_change` pairs are not presented as a user's choice — excluded, and
  documented in the endpoint description** — `test_a_cleared_pair_is_not_listed`.
- ✅ **Ordering: active by the earlier side's start, soonest first; resolved by resolution
  time, newest first** — `test_active_pairs_are_ordered_by_the_earlier_side_soonest_first`,
  `test_resolved_pairs_are_ordered_by_resolution_time_newest_first`.
- ✅ **The query count is bounded and independent of the number of pairs** —
  `test_the_query_count_does_not_grow_with_the_number_of_pairs` (asserts equal counts for
  1 pair and 10 pairs, and ≤ 6 total).
- ✅ **Pydantic schemas and the regenerated client; no hand-written types** —
  `make client` run; `backend/tests/api/test_contract.py` passes against the committed
  schema; `frontend/lib/api/` regenerated (+314 lines, no deletions).
- ✅ **Tests: ownership; both side kinds in both positions; a deleted saved event; each
  status; ordering; the query bound** — 20 tests, listed above.

## Tests Written

### Unit Tests

None — the service is a read over the database, so every rule it has is proved against a
real Postgres with both schemas.

### Integration Tests

- `backend/tests/personalization/test_conflict_list.py` — 20 tests:
  ownership (4), both sides named (3), a side that is gone (3), statuses (4), ordering
  (2), the query bound (2), the API surface (3).

## Test Commands

```bash
# This work item's tests
cd backend && uv run --directory . python -m pytest tests/personalization/test_conflict_list.py -q

# Run with coverage
cd backend && uv run --directory . python -m pytest --cov=. --cov-report=term-missing -q

# The domain gate
cd backend && uv run --directory . python -m pytest --cov=domain --cov-report=term -q
```

## Coverage Details

| Module | Lines | Missing |
|--------|-------|---------|
| `apps/personalization/services/conflict_list.py` | 100% | — |
| `backend/domain/` (the 100% gate) | 100% | — |
| **Overall (80% gate)** | **98.69%** | — |

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| `tests/personalization/test_digest_scheduling.py::test_the_command_composes_only_the_due_users` fails | Low | **Pre-existing — not caused by this work item.** Verified by stashing this work item's changes and re-running: it fails identically on a clean tree. The test is time-of-day dependent (it computes "one hour forward" from the wall clock, so it breaks near midnight local). Left alone: fixing an unrelated flaky test is not this work item's job. |
| The side lookup leaked another user's event name | **High — caught by a test** | **Fixed.** The pair is scoped to the caller, but the *side* lookup was scoped only by id, so a pair naming another user's event read their event's name. Both side lookups now filter on `user_id` as well as the ids, so a side naming a row the caller does not own reads as unavailable — the same explicit state as a deleted side, and no leak. |
| `_side_key` was dead code | Low | **Fixed.** Written during the first pass and never used; deleted. |
| `ruff format` and `ruff check` | Low | **Fixed.** Reformatted; `ruff check` and `ruff format --check` both clean. |

## Gate Results

| Gate | Result |
|------|--------|
| `pytest` (full backend suite) | 3946 passed, 1 pre-existing failure |
| Coverage — overall (gate 80%) | 98.69% ✅ |
| Coverage — `domain/` (gate 100%) | 100% ✅ |
| `ruff check .` | ✅ All checks passed |
| `ruff format --check .` | ✅ 426 files already formatted |
| `lint-imports` | ✅ 19 contracts kept, 0 broken |
| `python manage.py check` | ✅ No issues |
| `makemigrations --check --dry-run` | ✅ No changes detected (no schema change) |
| `make client` + `git diff --exit-code frontend/lib/api/` | ✅ Client regenerated and committed; contract test passes |

## Ready for Completion

- [x] All tests passing (the one failure is pre-existing and unrelated)
- [x] Coverage target met (98.69% overall, 100% on `domain/`, 100% on the new service)
- [x] All acceptance criteria validated
- [x] No critical issues open

---

## Work Item: saved-public-conflict-resolution

### Test Results

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit | 0 | 0 | 0 | — |
| Integration | 24 | 0 | 0 | 99% |
| **Total (this work item)** | **24** | **0** | **0** | **99%** |

**Full backend suite**: 3972 passed, 3 failed (all pre-existing, see Issues), 99.12%
overall coverage, 100% on `domain/`.
**Frontend suite**: 806 passed, 0 failed (59 files).

### Acceptance Criteria Validation

- ✅ **`skip_public` releases the save and records the resolution on the pair as
  `resolved` — not `cleared_by_state_change`** —
  `test_skipping_public_releases_the_save_and_records_the_resolution`,
  `test_skipping_public_records_the_resolution_on_the_pair`.
- ✅ **The action decides which side it acts on: `delete_new` refuses a saved side and
  `skip_public` refuses a personal side** —
  `test_delete_new_is_refused_against_a_saved_side`,
  `test_skip_public_is_refused_against_a_personal_side`,
  `test_a_duplicate_pair_with_a_saved_side_refuses_update_existing_on_the_saved_side`.
- ✅ **A side that is not one of the pair's two is refused outright** —
  `test_a_side_that_is_not_in_the_pair_is_refused`.
- ✅ **Another user's pair and another user's save are not reachable** —
  `test_another_users_pair_is_not_found`,
  `test_a_side_belonging_to_another_user_is_not_reachable`.
- ✅ **"Skip public" is answered, not abandoned: the unsave leaves this one pair alone** —
  `test_skipping_public_writes_both_audit_rows` (the pair's `conflict.resolved` row and
  the save's `saved_event.unsaved` row), and the pair keeps `resolution="skip_public"`.
- ✅ **One audit trail per fact, and one path to delete and one to unsave** — the delete
  goes through `delete_personal_event` and the unsave through `unsave_event`, so each
  fact has exactly one trail.
- ✅ **The prompt's action set is three; the list's is the union across the pair's sides**
  — `test_a_saved_side_offers_skip_public_instead_of_delete_new`,
  `test_a_duplicate_pair_with_a_saved_side_offers_the_same_three`,
  `test_the_personal_side_offers_are_unchanged`.
- ✅ **The migration is forwards-only and a superset for both kinds** —
  `test_the_resolution_constraint_accepts_skip_public_for_both_kinds`,
  `test_an_existing_resolved_pair_still_satisfies_the_constraint`,
  `test_the_resolution_constraint_still_refuses_an_unknown_resolution`,
  `test_a_cleared_pair_still_carries_a_null_resolution`.
- ✅ **The whole thing works over HTTP** —
  `test_the_save_to_409_to_resolve_round_trip_works_on_the_api`.
- ✅ **A closed pair is immutable (AD-21)** — `test_answering_twice_is_refused`.

### Tests Written

#### Integration Tests

- `backend/tests/personalization/test_saved_public_conflict_resolution.py` — 24 tests:
  the action sets (3), skip public (5), the refusals (7), the duplicate kind (2), the
  migration constraint (5), the endpoint (1), and the already-answered pair (1).

### Test Commands

```bash
# This work item's tests
cd backend && uv run pytest tests/personalization/test_saved_public_conflict_resolution.py -q

# The full backend suite, with the coverage gates
make coverage-backend

# The frontend, after the client regeneration
make lint-web && make test-web
```

### Coverage Details

| Module | Lines | Missing |
|--------|-------|---------|
| `apps/personalization/services/conflict_resolutions.py` | 99% | 415 |
| `backend/domain/` (the 100% gate) | 100% | — |
| **Overall (80% gate)** | **99.12%** | — |

### Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| `test_the_most_recent_composition_lookup_uses_the_index` failed under `--cov` | Low | **Fixed.** A **pre-existing** flake, exposed by this work item's 52 extra tests changing the table statistics the planner sees: the test asserted on the planner's *chosen* plan, and on a three-row table Postgres legitimately prefers a sequential scan — so which way it fell depended on the statistics at that moment, not on the code. The test now sets `enable_seqscan = off` for the plan, so it asks the question it means to ask ("is there an index the planner may use?"). **Proved not vacuous** with a mutation probe: removing `digest_comp_user_event_idx` (model + migration + applied) makes the test fail. The probe was reverted and `makemigrations --check` reports no changes. |
| `test_the_command_composes_only_the_due_users`, `test_the_command_releases_the_claim_when_a_composition_fails`, `test_the_local_day_is_the_users_and_not_the_servers` fail | Low | **Pre-existing — not caused by this work item.** Verified by stashing this work item's changes and re-running the full suite: they fail identically on a clean tree. They are time-of-day dependent (they compute "one hour forward" from the wall clock). Left alone: fixing unrelated flaky tests is not this work item's job. |
| The `update_existing` action was offered against a **saved** side, where it has no meaning | Medium | **Fixed.** The action opens the **personal** side in the edit sheet; a save has no edit sheet. The validation now checks the named side's kind against the **action's own target** (`_target_side_kind`), not against a set keyed by the named side — so `update_existing` against a saved side is refused. |
| The frontend still spoke the old contract | Medium | **Fixed.** The client's `ConflictOut` gained `new_side`/`other_side` and the resolve body changed from `new_side_id` to `side: {kind, id}`. `conflict-resolution.tsx`, `personal-events-panel.tsx`, `detail-actions.tsx` and the two test fixtures were updated, `make client` regenerated the schema, and the frontend suite is green. |

### Gate Results

| Gate | Result |
|------|--------|
| `pytest` (full backend suite) | 3972 passed, 3 pre-existing failures |
| Coverage — overall (gate 80%) | 99.12% ✅ |
| Coverage — `domain/` (gate 100%) | 100% ✅ |
| `ruff check .` | ✅ All checks passed |
| `ruff format --check .` | ✅ 428 files already formatted |
| `lint-imports` | ✅ 19 contracts kept, 0 broken |
| `makemigrations --check --dry-run` | ✅ No changes detected |
| `make client` | ✅ Regenerated; `skip_public` and `ConflictSideRef` present in the schema |
| `make lint-web` (eslint + tsc + prettier) | ✅ Clean |
| `make test-web` (Vitest) | ✅ 806 passed, 59 files |

### Ready for Completion

- [x] All tests passing (the three failures are pre-existing and unrelated)
- [x] Coverage target met (99.12% overall, 100% on `domain/`, 99% on the changed service)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-022*

---

## Work Item: timeline-week-api

### Test Results

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit | 0 | 0 | 0 | — |
| Integration | 43 | 0 | 0 | 100% |
| **Total (this work item)** | **43** | **0** | **0** | **100%** |

**Full backend suite**: 4027 passed, 1 failed (pre-existing, see Issues), 98.73% overall
coverage, 100% on `domain/`. **Frontend suite**: 806 passed, 0 failed (59 files).

### Acceptance Criteria Validation

- ✅ **`week` is any date in the wanted week; the response names the week's Monday and
  Sunday and returns seven days, each with its date and its blocks. A malformed value is
  a 422.** — `test_the_endpoint_names_the_week_and_returns_seven_days`,
  `test_a_malformed_week_is_a_422`, `test_a_week_is_monday_to_sunday_and_a_mid_week_date_selects_the_week_around_it`,
  `test_the_seven_days_are_returned_for_an_empty_week`.
- ✅ **Days are cut in the user's timezone (the digest preference zone, falling back to
  UTC), not the server's; an event is placed on the day its local start falls on.** —
  `test_the_week_is_cut_in_the_users_zone_and_the_response_names_it`,
  `test_the_week_falls_back_to_utc_when_the_user_has_no_preference`,
  `test_the_days_are_the_users_zone_and_not_the_servers`,
  `test_an_event_at_23_30_local_is_on_that_local_day`,
  `test_a_missing_week_means_the_current_week_in_the_users_zone`.
- ✅ **A block carries `kind`, the id the screen acts on, name, start, end, the event's own
  zone, and `conflict`.** — `test_the_blocks_are_the_personal_events_and_the_saved_events_merged`,
  `test_a_public_block_carries_the_catalog_event_id_and_the_catalog_title`,
  `test_the_endpoint_returns_the_blocks_with_their_kind_and_indicator`.
- ✅ **`conflict` is true for both sides of an active pair, and stays true after `keep
  both`.** — `test_the_indicator_is_true_for_both_sides_of_an_active_pair`,
  `test_the_indicator_is_still_true_after_keep_both`,
  `test_the_indicator_is_true_for_the_saved_side_of_a_pair`.
- ✅ **`conflict` is false otherwise.** —
  `test_the_indicator_is_false_after_every_other_resolution` (parametrized over
  `edit_new`, `delete_new`, `update_existing` and `skip_public`),
  `test_the_indicator_is_false_for_a_cleared_by_state_change_pair`,
  `test_the_indicator_is_false_when_the_pairs_other_side_has_gone`.
- ✅ **Cross-midnight: a personal event running past midnight appears on each day it
  covers, and the indicator fires on the day-cell whose interval contains the overlap.**
  — `test_a_cross_midnight_event_appears_on_each_day_it_covers`,
  `test_a_cross_midnight_event_covers_both_days_it_spans`,
  `test_the_indicator_repeats_on_each_day_cell_a_multi_day_event_spans`,
  `test_the_indicator_follows_the_pairs_overlap_and_not_the_blocks_own_span`.
- ✅ **Reads are range-bounded and the query count is independent of the number of
  events.** — `test_an_event_that_started_before_the_week_still_appears_on_the_day_it_covers`
  (the overlap bound, not a start bound),
  `test_the_query_count_does_not_grow_with_the_number_of_events` (asserts equal counts for
  1 event and 10, and **exactly 5** total).
- ✅ **Caller only; anonymous is 401. Schemas and regenerated client.** —
  `test_the_read_holds_only_the_callers_events`, `test_an_anonymous_caller_is_refused`;
  `make client` run; `backend/tests/api/test_contract.py` passes against the committed
  schema.
- ✅ **Tests: week boundaries in a non-UTC zone (including a DST change week), an event at
  23:30 local, a cross-midnight event, both indicator states, a saved event whose catalog
  event disappeared, and an empty week.** — 43 tests, listed above.
  The DST week is pinned two ways:
  `test_the_week_bounds_are_the_local_midnights_and_a_dst_week_is_not_168_hours` (the week
  containing a spring-forward is **167 hours**, the week containing a fall-back is
  **169**, and a plain week is **168**).

### Tests Written

#### Integration Tests

- `backend/tests/personalization/test_timeline.py` — 43 tests:
  the pure day arithmetic (10), the service (25), the endpoint (8).

  The **pure** half needs no database at all: `timeline_days.py` takes instants and zone
  names and returns instants and dates, so a DST week is testable without a fixture that
  has to be right twice a year.

### Test Commands

```bash
# This work item's tests
cd backend && uv run --directory . python -m pytest tests/personalization/test_timeline.py -q

# The full backend suite, with the coverage gates
cd backend && uv run --directory . python -m pytest --cov=. --cov-report=term-missing -q
cd backend && uv run --directory . python -m pytest --cov=domain --cov-report=term -q

# The frontend, after the client regeneration
make lint-web && make test-web
```

### Coverage Details

| Module | Lines | Missing |
|--------|-------|---------|
| `apps/personalization/services/timeline.py` | 100% | — |
| `apps/personalization/services/timeline_days.py` | 100% | — |
| `backend/domain/` (the 100% gate) | 100% | — |
| **Overall (80% gate)** | **98.73%** | — |

### Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| The indicator was computed against the **block's own span**, not the **pair's overlap** | **High — caught by a test** | **Fixed.** The AC says the indicator "fires on the day-cell whose interval contains the overlap", and the overlap is between the two *conflicting* events. The first implementation tested the block's span, so an event running Friday 22:00 → Saturday 02:00 that clashes only on Saturday lit **both** cells. The service now computes the pair's window — the intersection of the two sides' intervals for a **time** pair, and the span the two sides share for a **duplicate** pair — and tests it against each day's own interval. Pinned by `test_the_indicator_follows_the_pairs_overlap_and_not_the_blocks_own_span`. |
| An **open-ended** event covered only its start day | **High — caught by a test** | **Fixed.** `days_covered` set `last = first` for an event with no end, contradicting its own docstring ("covers every day from its start onward"). An open-ended event now runs to the `limit` — the week's last day — so it appears on every day from its start. The `limit` is what stops an open-ended event from building a list of dates from 1970 to the end of time. Pinned by `test_an_open_ended_event_covers_every_day_from_its_start` and `test_an_open_ended_event_appears_on_every_day_of_the_week_from_its_start`. |
| The `days_covered` loop's `limit` check was inside the loop, so it truncated the **last** day rather than capping it | Medium | **Fixed.** The `cursor > limit` check broke *after* appending, which meant an open-ended event stopped one day short of the limit. The check now sits on the `last` value, and the loop runs to it. |
| A **duplicate** pair's window was untested — and untestable as written | Medium | **Fixed.** A duplicate pair has no time overlap to intersect, so its window is the span the two sides share. The rule is now stated in `_side_window` and pinned by `test_the_indicator_follows_a_duplicate_pair_onto_the_day_the_duplicate_sits`. |
| Two tests shared a name, so one **shadowed** the other and never ran | Medium | **Fixed.** `test_an_open_ended_event_covers_every_day_from_its_start` existed twice — once for the pure arithmetic and once for the service — and the second shadowed the first. Caught by `ruff check` (F811). The service one is now `test_an_open_ended_event_appears_on_every_day_of_the_week_from_its_start`, and both run. |
| The test fixtures wrote Wednesday-afternoon times but the test user had **no zone**, so the days were cut in UTC | Medium | **Fixed.** The fixture's `local_midnight(WEDNESDAY) + 17h` is 17:00 in Los Angeles, which is 01:00 UTC on Thursday — so the events landed on the wrong day. The test user now has a digest preference in `TZ`, because the zone is part of the user's calendar rather than an accident of the test, and `in_zone()` moves it when a test needs another zone. |
| The factory's `end=None` meant "the default", not "no end" | Low | **Fixed.** An open-ended event's "no end" is `None`, and the factory's default is also a two-hour event — so `end=None` could not express "no end". A `NO_END` sentinel does. |
| `test_the_local_day_is_the_users_and_not_the_servers` fails | Low | **Pre-existing — not caused by this work item.** Verified by stashing this work item's changes and re-running: it fails identically on a clean tree. The test is time-of-day dependent (it compares today in Tokyo against today in Los Angeles, which is the same date for most of the day). Left alone: fixing an unrelated flaky test is not this work item's job. |
| `ruff format` and `ruff check` | Low | **Fixed.** Reformatted; `ruff check` and `ruff format --check` both clean. |

### Mutation Probes

The three rules the work item exists to pin were each broken on purpose, to prove the
tests can fail. **All three probes were reverted**, and `makemigrations --check` reports
no changes.

| Probe | Break | Tests that failed |
|-------|-------|-------------------|
| 1 | The `keep_both` clause in the indicator projection replaced with `delete_new` | `test_the_indicator_is_still_true_after_keep_both`, `test_the_indicator_is_false_after_every_other_resolution[time-delete_new]` |
| 2 | The indicator's overlap test changed from the **pair's** window to the **block's own span** | `test_the_indicator_repeats_on_each_day_cell_a_multi_day_event_spans`, `test_the_indicator_follows_the_pairs_overlap_and_not_the_blocks_own_span` |
| 3 | The overlap bound's lower filter changed from `end_utc >= window_start OR end_utc IS NULL` to `start_utc >= window_start` | `test_an_event_that_started_before_the_week_still_appears_on_the_day_it_covers` |

### Gate Results

| Gate | Result |
|------|--------|
| `pytest` (full backend suite) | 4027 passed, 1 pre-existing failure |
| Coverage — overall (gate 80%) | 98.73% ✅ |
| Coverage — `domain/` (gate 100%) | 100% ✅ |
| Coverage — the two new modules | 100% / 100% ✅ |
| `ruff check .` | ✅ All checks passed |
| `ruff format --check .` | ✅ 431 files already formatted |
| `lint-imports` | ✅ 19 contracts kept, 0 broken |
| `python manage.py check` | ✅ No issues |
| `makemigrations --check --dry-run` | ✅ No changes detected (no schema change) |
| `make client` + `tests/api/test_contract.py` | ✅ Regenerated and committed; contract test passes |
| `make lint-web` (eslint + tsc + prettier) | ✅ Clean |
| `make test-web` (Vitest) | ✅ 806 passed, 59 files |

### Ready for Completion

- [x] All tests passing (the one failure is pre-existing and unrelated)
- [x] Coverage target met (98.73% overall, 100% on `domain/`, 100% on both new modules)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-022*

---

## Work Item: frontend-timeline

### Test Results

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit | 24 | 0 | 0 | — |
| Component | 26 | 0 | 0 | — |
| Integration (page) | 18 | 0 | 0 | — |
| Accessibility | 5 | 0 | 0 | — |
| **Total (this work item)** | **73** | **0** | **0** | — |

**Full frontend suite**: 877 passed, 0 failed (66 files) — up from 806 in 59 files.
**Backend**: unchanged by this work item; the last full run was 4027 passed, 1 pre-existing
failure.

### Acceptance Criteria Validation

Every criterion below is pinned by a test that was **written for it**, and every test was
run.

- ✅ **The visible week lives in the URL; reload, back and share keep it** —
  `app/timeline/page.test.tsx`: "sends the week it was given to the read",
  "keeps the previous and next week in the URL", "does not roll the last day into the
  next week", "does not roll the first day back into the previous week".
- ✅ **A malformed week is a failure, not a guess** — "does not forward a malformed week,
  because guessing would be a lie".
- ✅ **The desktop draws all seven days side by side; the mobile draws one day at a time;
  both are in the DOM and the CSS picks** — "draws seven columns in the server's order",
  "shows the day the URL names", "falls back to today when the URL names no day".
- ✅ **The server states the fact; the page renders it** — the grid test asserts the
  columns' `aria-label`s are the server's seven dates **in the server's order**, and the
  read test asserts the payload is passed through untouched.
- ✅ **The week is a local week, cut at local midnight in the user's zone** — the page
  renders the zone the server named (`America/New_York`) and the day arithmetic is
  pinned in `lib/timeline-dates.test.ts`: "reads the date's own weekday, not the
  instant's", "does not skip a day across a DST boundary".
- ✅ **A personal block carries the warm stripe *and* the "Personal" label** —
  `components/timeline/timeline-panel.test.tsx`: "pairs a personal block's stripe with
  the word 'Personal'".
- ✅ **A public block carries the cool stripe *and* the "Public event" label** — "pairs a
  public block's stripe with the words 'Public event'".
- ✅ **The conflict indicator appears when the API says so, and not when it does not** —
  "appears when the API says the block is in conflict", "does not appear when the API
  says it is not".
- ✅ **The accessible name is name + time + kind** — "is the name, the time, and the
  kind".
- ✅ **A block with no name says "Event no longer available"** — "says 'Event no longer
  available' for a block with no name".
- ✅ **A public block links to `/events/:id`** — "sends a public block to the event's
  detail page".
- ✅ **A personal block opens the edit sheet** — "opens the edit sheet for a personal
  block": the `<dialog>` is closed before the click and open after it.
- ✅ **An empty day says "Quiet day."** — "says 'Quiet day.' in a day with no events".
- ✅ **An empty week says "Your week is quiet." and offers one link to `/`** — "replaces
  the grid with the quiet line and one link to the digest".
- ✅ **The error says "Couldn't reach Timeline. Try again." and offers a retry** — "says
  it could not reach the Timeline and offers a retry", "keeps the week in the retry link".
- ✅ **The skeleton draws seven columns and no day labels** —
  `components/timeline/timeline-states.test.tsx`: "draws seven columns", "draws no day
  labels", "is hidden from the screen reader, because it says nothing".
- ✅ **The read carries the visitor's cookies** — `lib/timeline-read.test.ts`: "reads the
  week with the visitor's cookies".
- ✅ **A failure to answer is not an empty week** — `lib/timeline-read.test.ts`: "answers
  'unavailable' when there is no API to ask", "…when the request fails", "…when the API
  answers with an error"; and `app/timeline/page.test.tsx`: "does not redirect when the
  API is unreachable, because a blip is not a logout".
- ✅ **Timeline is a real route in both rails** — `components/shell/timeline-nav.test.tsx`:
  the sidenav row and the bottom-tab slot both link to `/timeline` and carry
  `aria-current="page"` when it is the current route, while Browse / Conflicts /
  Settings stay inert.
- ✅ **axe-core reports zero serious or critical violations** — `tests/timeline-a11y.test.tsx`
  audits the full week, the quiet week, the error state and the skeleton.

### Tests Written

#### Unit Tests

- `frontend/lib/timeline-dates.test.ts` — 24 tests: the weekday of a calendar date (4),
  the day of the month (1), the day arithmetic (5), the date's validity (3), the written
  forms (4), today (1).
- `frontend/lib/timeline-read.test.ts` — 6 tests: the cookies (1), the week parameter
  (2), the three ways of failing to answer (3).

#### Component Tests

- `frontend/components/timeline/timeline-panel.test.tsx` — 12 tests: the category
  pairing (2), the conflict indicator (2), the accessible name (2), what a block does
  (2), the time line (4).
- `frontend/components/timeline/timeline-states.test.tsx` — 3 tests: the skeleton's
  shape.
- `frontend/components/shell/timeline-nav.test.tsx` — 8 tests: the sidenav (4), the
  bottom tab (4).

#### Integration Tests

- `frontend/app/timeline/page.test.tsx` — 18 tests: the routing decision (3), the week
  in the URL (4), the header (1), the desktop grid (3), the quiet week (1), the mobile
  day (4), the failure state (2).

#### Accessibility Tests

- `frontend/tests/timeline-a11y.test.tsx` — 5 tests: the axe-core gate over four
  documents, plus the assertion that the audit ran over a real surface (the shell's
  landmarks are in the document).

### Test Commands

```bash
# This work item's tests
cd frontend && npx vitest run app/timeline components/timeline components/shell/timeline-nav.test.tsx lib/timeline-read.test.ts lib/timeline-dates.test.ts tests/timeline-a11y.test.tsx

# The full frontend suite
cd frontend && npx vitest run

# Lint, type-check, format
make lint-web

# The production build
cd frontend && npx next build
```

### Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| The panel **synced a prop into state in an effect**, so a render between the two would show the wrong event | **High — caught by `react-hooks/set-state-in-effect`** | **Fixed.** `PersonalEventsPanel` now *derives* the editing event during render (`driven` / `drivenEvent` / `editing` / `formOpen`), and the effect is gone. The lint rule was right: copying an id into a `useState` made two sources of truth. The form's key follows the driven event, so naming a second event remounts the form with that event's values. |
| The `openEdit` signature took a `highlight` flag and **threw it away** | Low | **Fixed.** `setHighlightStartTime(false)` became `setHighlightStartTime(highlight)`, so the conflict sheet's "edit the new one" path actually pre-highlights the conflicting time. Caught by `@typescript-eslint/no-unused-vars`. |
| The skeleton used `h-10`, which is **off the spacing scale** | Low | **Fixed.** The spacing-scale gate caught it (`tests/spacing-scale.test.ts`); the rectangles are now `h-[40px]` — an exact size, in brackets, as the house rule says. |
| The page duplicated the block markup in a second file | Medium | **Fixed during implementation.** A `timeline-grid.tsx` server component was written alongside the client panel; it was deleted and both layouts moved into `timeline-panel.tsx`, with the shared `TimelineBlockView` extracted so the markup exists once. |
| The `mondayOf` helper existed in **two** places — the page and the dates module | Low | **Fixed.** The page's local copy is the one that remains (it needs the calendar-week rule the page owns), and `timeline-dates.ts` has its own `weekdayIndex`; the dates module's test pins the arithmetic both use. |
| The block's time line **named the zone twice** — "Mon, Nov 2 · 9:00 AM EST – 10:30 AM EST" | Medium | **Fixed.** `cardTime` prints the zone inline, so keeping the start's string whole repeated it. The range now strips both ends' inline zones and prints the zone once, at the end: "Mon, Nov 2 · 9:00 AM – 10:30 AM EST". Pinned by "prints the range, with the zone named once". |
| `blockTime` built a **regular expression from the zone's name** | Medium | **Fixed.** A zone's short name is a rendered string — whatever the platform's `Intl` says — so a regex built from it would have to escape it, and a name carrying a metacharacter would throw or strip the wrong text. The zone is now **counted off the end** of the string, which cannot go wrong. Pinned by "does not build a pattern from the zone's name". |
| The Timeline's blocks were mapped to personal events with a **fabricated `version: 1`** | Medium | **Fixed.** `PersonalEventOut.version` is the optimistic-locking counter, and the Timeline's block payload carries no version — so `1` was an invented fact about the event. The panel's `editingEvents` prop now takes a **narrow `PersonalEventSeed`** — the shape the sheet actually reads — so a caller that lacks a version does not have to invent one. A caller holding a full `PersonalEventOut` still passes one unchanged. The conflict sheet's two `openEdit` calls dropped their `version: 1` for the same reason. |
| `tsc` reported duplicate `PageProps` / `LayoutProps` in `.next/types` | Low | **Not a code issue.** The generated route types were stale from a build before `/timeline` existed. `next typegen` (which `make lint-web` runs) regenerates them; `tsc --noEmit` is clean. |

### Gate Results

| Gate | Result |
|------|--------|
| `make lint-web` (eslint + `tsc --noEmit` + prettier) | ✅ Clean |
| `npx vitest run` (full frontend suite) | ✅ 877 passed, 66 files |
| `npx next build` | ✅ Compiled; `ƒ /timeline` registered |
| `tests/spacing-scale.test.ts` | ✅ Passes (the `h-10` caught above was fixed) |
| `tests/timeline-a11y.test.tsx` (axe-core) | ✅ Zero serious or critical violations in four documents |
| Backend suite | Unchanged by this work item — 4027 passed, 1 pre-existing failure |

### Ready for Completion

- [x] All tests passing (877 in the frontend suite, 0 failures)
- [x] Every acceptance criterion pinned by a named test
- [x] The axe-core gate passes over every state
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-022*
