---
run: run-eventpulse24-029
work_item: test-clock-seam
intent: browse-surface
generated: 2026-11-12
status: passed
---

# Test Report: A Clock Seam for the Tests — Fix the 17 Date-Expiry Failures

## Summary

| Run | Command | Result |
|---|---|---|
| **Before** (baseline, `feature/browse-surface` at branch point) | `pytest -q --reuse-db` | `17 failed, 6723 passed in 628.84s` |
| **After** | `pytest -q --reuse-db` | **`6740 passed in 733.56s`** |

The counts reconcile exactly: 6723 + 17 = 6740. Every previously failing test now passes, and
no previously passing test broke.

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| **Total** | **6742** | **0** | **0** |

Final count is 6742: the 6740 above plus the two new `domain/` tests added to close the
coverage gate (Issue 5).

### Coverage gates

| Gate | Required | Measured | Result |
|---|---|---|---|
| Overall | ≥ 80% | **98.67%** | pass |
| `domain/` | 100% | **100%** (1071 statements, **0 missed**) | pass |

## The 17, named individually

The acceptance criteria require the starting state to be auditable rather than asserted. All
17 were collected from the baseline run's `-rf` summary:

| # | Test | File |
|---|---|---|
| 1 | `test_a_custom_slot_is_minted` | `tests/delivery/test_reminder_plan_api.py` |
| 2 | `test_a_saved_plan_and_its_sends_move_together` | `tests/delivery/test_reminder_plan_api.py` |
| 3 | `test_the_whole_personal_event_and_save_flow_holds_together` | `tests/e2e/test_personal_events_and_saved_catalog.py` |
| 4 | `test_a_save_is_idempotent_and_one_row` | `tests/e2e/test_save_race.py` |
| 5 | `test_a_save_that_does_not_race_is_not_stale` | `tests/e2e/test_save_race.py` |
| 6 | `test_a_save_that_races_a_postponement_reports_itself_stale` | `tests/e2e/test_save_race.py` |
| 7 | `test_a_snapshot_survives_a_catalog_postponement_unchanged` | `tests/e2e/test_save_race.py` |
| 8 | `test_a_clashing_save_answers_409_with_a_pair_the_resolve_endpoint_can_close` | `tests/e2e/test_timeline_and_conflict_proof.py` |
| 9 | `test_a_closed_pair_is_never_re_prompted` | `tests/e2e/test_timeline_and_conflict_proof.py` |
| 10 | `test_a_resolution_naming_a_side_outside_the_pair_is_refused` | `tests/e2e/test_timeline_and_conflict_proof.py` |
| 11 | `test_a_second_user_sees_none_of_the_first_users_pairs_or_blocks` | `tests/e2e/test_timeline_and_conflict_proof.py` |
| 12 | `test_delete_new_removes_the_personal_event_and_clears_the_indicator` | `tests/e2e/test_timeline_and_conflict_proof.py` |
| 13 | `test_edit_new_keeps_both_events_and_clears_the_indicator` | `tests/e2e/test_timeline_and_conflict_proof.py` |
| 14 | `test_skip_public_releases_the_save_and_clears_the_indicator` | `tests/e2e/test_timeline_and_conflict_proof.py` |
| 15 | `test_the_indicator_follows_the_overlap_and_not_the_events_own_span` | `tests/e2e/test_timeline_and_conflict_proof.py` |
| 16 | `test_the_week_the_review_and_the_resolution_are_one_pair` | `tests/e2e/test_timeline_and_conflict_proof.py` |
| 17 | `test_a_city_lastmod_is_the_latest_of_its_events` | `tests/ingestion/test_url_feed_read.py` |

**The count did not grow since run 028.** That run reported 17 and this one measured 17. The
growth it warned about (16 → 17 mid-run) did not continue in the eight days since.

## What was actually wrong

14 of the 17 failed with `not_found` — `"We couldn't find that event."` The events are present
in the database and the read path filters to events that have not started yet, so the API was
correctly refusing them. Two sources of fixed dates combine:

1. **The tests' own literals** — `START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)` and similar.
2. **The seed fixtures** — `tests/fixtures/sources/` carries event dates from 2026-11-03 to
   2026-12-01, hardcoded in the fixture files themselves.

And the structural cause: three of the five files **already declared a `NOW`** and threaded it
into every service call. The seam existed at the service layer and at `domain/`, where
functions take `now` as a parameter. It stopped at HTTP — a view calls `timezone.now()` itself,
so requests were answered against the wall clock while their data sat at the declared `NOW`.
The two agreed when the files were written and drifted apart as the date passed.

`test_reminder_plan_api.py:49` states the intent that was never mechanised:

> *"The instant every test measures from. Pinned so a reminder's due time is a fact, not a
> function of when the suite happened to run."*

## Acceptance Criteria Validation

- ✅ **`make test-backend` exits 0 with no failures and no new skips or `xfail`s** — `6740 passed`,
  0 skipped. No `skip` or `xfail` marker was added.
- ✅ **The exact count of previously failing tests is recorded, named individually** — the table
  above, collected from the baseline run.
- ✅ **The fix is a seam, not a bulk rewrite of literals to later dates** — `freezegun==1.5.5`
  added to the dev group; every pre-existing date literal is unchanged.
- ✅ **A test asserting behaviour at a fixed instant states that instant explicitly** — each of
  the five modules freezes at a named `NOW` constant.
- ✅ **Each repaired test can still fail** — three mutations, below; all three broke their tests.
- ✅ **`make lint-backend` and `make lint-imports` green** — "All checks passed!", **19 import
  contracts kept, 0 broken**. See Issues: this gate was *red on `main`* before this item.
- ✅ **`coverage-backend` gates (≥80% overall, 100% `domain/`)** — 98.67% overall, `domain/` at
  100% with 0 missed statements. See Issue 5: this gate had **never been evaluated** in the
  state the branch was in.

## Mutation checks — proof the repaired tests can still fail

Each mutation was applied to **production** code, the test run, and the change reverted. A
repaired test that cannot fail is a test that was not repaired.

| Mutation | File | Test | Result |
|---|---|---|---|
| `stale = after.event_version > current.event_version` → `stale = False` | `apps/personalization/services/saved_events.py:200` | `test_a_save_that_races_a_postponement_reports_itself_stale` | **FAILED** — `assert False is True` |
| `mint_for_plan` early `return 0` | `apps/delivery/services/scheduled_sends.py:352` | `test_a_custom_slot_is_minted`, `test_a_saved_plan_and_its_sends_move_together` | **both FAILED** — `assert set() == {'1d','1hr','2d','5d'}` |
| `Max(last_modified)` → `Min(last_modified)` | `apps/ingestion/services/url_feed_read.py:264` | `test_a_city_lastmod_is_the_latest_of_its_events` | **FAILED** — returned the creation instant instead of the change |

After restoration: `grep -rn "MUTATION" --include=*.py .` → **0**, and `git status` shows **no
production file modified**.

## Issues Found

| # | Issue | Severity | Status |
|---|---|---|---|
| 1 | Two of the 17 were **genuine test bugs**, not date expiry — exposed by the freeze | medium | **fixed** |
| 2 | `make lint-backend` was **already red on `main`** | medium | **fixed** |
| 3 | `test_a_custom_slot_is_minted` never asserts the custom slot's **due time** | low | **open — follow-up** |
| 4 | Backend suite takes **12 minutes**; `pytest-xdist` not installed | low | **open — follow-up** |
| 5 | `domain/` coverage gate was at **99%** and had never been evaluated | medium | **fixed** |

### Issue 1 — two genuine test bugs

- **`test_a_saved_plan_and_its_sends_move_together`** asserted four slots (`5d`, `2d`, `1d`,
  `1hr`) against an event **1 day 14 hours** away. A `5d` or `2d` reminder for it would be due
  in the past, and `mint_for_plan` documents that it does not mint those: *"A slot whose moment
  has already passed is not minted."* **The production code was right and the test was wrong.**
  Fixed by adding `FAR_AFTERNOON_START = AFTERNOON_START + timedelta(days=7)` — the same 6pm
  local wall time a week later. Both dates are PST (US DST ended 2026-11-01), so the
  quiet-hours property `AFTERNOON_START` was chosen for is unchanged.
- **`test_a_city_lastmod_is_the_latest_of_its_events`** created its city's events *after* the
  state change it called "latest". Since a `lastmod` is `COALESCE(last state change, the
  event's creation)`, the creation always won and the assertion compared against the wrong
  value. Fixed by creating the events a day back. The `Max → Min` mutation confirms the
  assertion now discriminates: it returned the creation instant, which is what the old
  arrangement would have made the correct answer.

### Issue 2 — lint was red on `main`

Two `DTZ001` errors in `tests/domain/test_weekly_quiet_hours.py`, introduced by commit
`54ecf50` (run 027's per-day quiet hours). Verified pre-existing by running ruff against
`git show main:...` of that file, and ruff's pinned version (0.17.3) is unchanged by this
item's dependency addition. **Runs 027 and 028 both closed with this gate red.**

Fixed, but deliberately **not** by stamping `tzinfo=UTC` on the values. `_ends_covering(window,
local: datetime)` reads only `.date()` and `.time()`, and its docstring calls the values it
returns naive — the parameter is a *wall clock*, not an instant. A `tzinfo` there would assert
something the value does not mean. So:

- line 210 became `date(2026, 3, 8)`, which is all the assertion ever used;
- line 265 carries `# noqa: DTZ001` with the reason written next to it.

### Issue 3 — a weak test, found by accident, left open

The first mutation attempt disabled custom-slot offset resolution
(`minutes = custom_slot_minutes(slot)` → `None` in `reminder_plans.slot_offsets`) and
`test_a_custom_slot_is_minted` **still passed**. It asserts the send exists with slot
`custom:90` and status `PENDING`, but never asserts **when it is due** — so the "90 minutes"
in the slot id is unverified, and a regression minting it at the wrong time would not be
caught.

Not fixed here: it is outside this work item's acceptance criteria, and widening scope
silently is what this run is meant to stop doing. Recorded as a follow-up.

### Issue 5 — the domain coverage gate had never run

`domain/` carries a hard 100% gate. It measured **99%** — three uncovered statements, all in
`domain/quiet_hours.py` (lines 79, 145, 255).

**Proven pre-existing, not caused by this work.** The same three lines are uncovered with this
item's test changes stashed (`git stash push tests/`, re-measure, identical result: `69 3 96%
79, 145, 255`). `git blame` puts lines 79 and 255 in commit `f75e1149` and line 145 in
`54ecf50` — all before this branch.

**Why nobody saw it.** The target is two commands and `make` stops at the first failure:

```make
coverage-backend:
	$(UV_BACKEND) pytest --cov --cov-report=term                          # exits 1 with 17 failures
	$(UV_BACKEND) coverage report --include='domain/*' --fail-under=100   # never ran
```

So the domain gate has not been evaluated since those failures appeared. This is the third
red gate this item uncovered, and all three were masked the same way — the first failure hid
the rest.

**Resolution**, approved by Jobaer rather than taken unilaterally, since one part needed a
production-code edit this item had promised not to make:

| Line | What it is | Fix |
|---|---|---|
| 79 | the non-crossing-midnight branch of `QuietHours.covers` | new test `test_covers_daytime_window_inside_and_outside_its_bounds` |
| 145 | `return None` when no schedule is configured | new test `test_no_schedule_at_all_covers_nothing` |
| 255 | the final `return`, documented `Unreachable` | `# pragma: no cover` with the reason written beside it |

Line 79 is worth noting: the module already declares `AFTERNOON = QuietHours(start=time(13, 0),
end=time(14, 0))` with the comment *"An ordinary window that does not cross midnight, to prove
one branch serves both shapes"* — and then never calls `covers` on it. The test the file
intended was missing.

Both new tests were mutation-checked: `covers`'s non-crossing branch forced to `False`, and
`_window_beginning_on(None, …)` made to return a window instead of `None`. **Both tests
failed**, then the mutations were reverted.

### Issue 4 — the suite is slow

12m13s for 6,740 tests. `pytest-xdist` is not installed; `-n auto` would likely cut this
several-fold. Raised at checkpoint 1 and explicitly declined for this item, so it stays a
follow-up rather than scope creep.

## Files Changed

The date-expiry fix itself changed **no production code** — that bug was entirely in what the
tests could control. One production line was later edited to close the coverage gate (Issue
5), and it is a `pragma` comment, not behaviour.

| File | Change |
|---|---|
| `backend/pyproject.toml` | `freezegun==1.5.5` added to the `dev` group, exact-pinned per house convention |
| `backend/uv.lock` | regenerated — adds freezegun only, no other version moved |
| `backend/tests/e2e/test_save_race.py` | `NOW = START - timedelta(days=1)`; autouse freeze, `tick=True` |
| `backend/tests/e2e/test_personal_events_and_saved_catalog.py` | `NOW = START - timedelta(days=1)`; autouse freeze, `tick=True` |
| `backend/tests/e2e/test_timeline_and_conflict_proof.py` | autouse freeze at the existing `NOW`, `tick=True` |
| `backend/tests/delivery/test_reminder_plan_api.py` | autouse freeze at the existing `NOW`; `FAR_AFTERNOON_START` added (Issue 1) |
| `backend/tests/ingestion/test_url_feed_read.py` | autouse freeze at the existing `NOW`; events created a day back (Issue 1) |
| `backend/tests/domain/test_weekly_quiet_hours.py` | two `DTZ001` lint errors resolved (Issue 2); `test_no_schedule_at_all_covers_nothing` added (Issue 5) |
| `backend/tests/domain/test_quiet_hours.py` | `test_covers_daytime_window_inside_and_outside_its_bounds` added (Issue 5) |
| `backend/domain/quiet_hours.py` | **the one production edit** — `# pragma: no cover` on the unreachable final return (Issue 5) |

**Why `tick=True` everywhere.** A hard freeze mints UUIDv7 keys that share a timestamp prefix,
and these modules assert on row identity and ordering. `tick=True` starts at the stated instant
and lets time advance from there, which keeps UUID7 monotonic while still placing the fixtures
in the future.

## The three risks from the plan, resolved

The plan named three things that could block the approach and promised to check rather than
assume them.

1. **UUIDv7 ordering** — handled by `tick=True`. The ordering assertions in
   `test_a_save_is_idempotent_and_one_row` and the timeline proof's pair tests all pass.
2. **Celery eager tasks inheriting the frozen clock** — they do, and that is the wanted
   behaviour. No task compared a frozen `now` against a real-clock timestamp.
3. **Postgres `now()` is not frozen** — **this one bit, exactly as predicted.** It is the
   mechanism behind Issue 1's `lastmod` failure: rows written under the freeze carry the
   frozen instant, which still out-ranked a fixture value set earlier. The plan said the fix
   would be to pin the fixture rather than widen the assertion, and that is what was done —
   the events are created at `NOW - DAY`, and the mutation check proves the assertion still
   discriminates.

## Test Commands

```bash
# The suite
make test-backend

# The gates
make coverage-backend

# Lint and the import contracts
make lint-backend
```

## Ready for Completion

- [x] All tests passing — 6742 passed, 0 failed
- [x] Coverage target met — 98.67% overall, `domain/` 100% with 0 missed
- [x] All acceptance criteria validated (bar coverage)
- [x] No critical issues open — two open issues, both low, both recorded as follow-ups

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-029*
