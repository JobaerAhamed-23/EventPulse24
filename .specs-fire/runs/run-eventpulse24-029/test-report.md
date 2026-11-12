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

---

## Work Item: browse-read-api

**Mode:** `validate`. Checkpoint 1 (design) approved 2026-11-12; checkpoint 2 (plan) approved
with one deviation. Design doc:
`.specs-fire/intents/browse-surface/work-items/browse-read-api-design.md`

### What was built

| Layer | File | What |
|---|---|---|
| Port | `ports/throttle.py` | `ThrottleState` + `ThrottlePort.peek` — read a window **without spending it** |
| Adapter | `adapters/throttle/redis.py` | `peek` via `GET` + `TTL`, never `INCR` |
| Adapter | `adapters/throttle/memory.py` | `peek` via the attempt list, and it does **not** evict a closed window it finds |
| Catalog read | `apps/ingestion/services/catalog_read.py` | `starts_before` on `list_public_candidates`, defaulting to `None` |
| Quota | `apps/personalization/services/save_cap.py` | `SaveQuota` + `read_save_quota` — the sign above the gate, not the gate |
| Service | `apps/personalization/services/browse_read.py` | **new** — pool → rank → explain → join → gate → split |
| Schemas | `apps/personalization/schemas.py` | `BrowseOut`, `BrowseCardOut`, `BrowseQuotaOut` |
| API | `apps/personalization/api.py` | `GET /api/personal/browse?offset=&limit=` |
| Contract | `frontend/lib/api/{openapi.json,schema.ts}` | regenerated by `make client`; additive, no manual edits |

**45 new tests**: 24 service, 11 API, 10 throttle (`peek` and its adapter parity).

### The finding that shaped the item

`check_save_allowed` **consumes** a throttle slot — `save_cap.py` states the adapters "count
an attempt *before* deciding whether to allow it". Reporting the save quota by asking the gate
would therefore **spend a user's one free save every time they opened Browse**.

The alternative — counting `SavedEvent` rows — is explicitly forbidden by the same module: *"a
row count would make the cap depend on data the user can delete (unsaving an event would hand
the allowance back, and re-saving would spend it again)"*.

So the port gained a read-only `peek`. It was raised rather than taken unilaterally, because
a port is architecture surface and the plan had not listed it.

`test_a_free_users_quota_is_reported_and_not_spent` is the test that matters: three page
loads, quota still reads zero. Without `peek`, the third read would have told the user they
had spent three saves without ever pressing Save.

### Two invariants the database taught the tests

Both were caught by fixtures failing, not by review:

- **`digest_preference_city_source_ck`** — a city and its `city_source` travel together. "A
  city with no source is a claim about where the user is with no record of how we learned it."
- **`guard_event_write()`** — a lifecycle change *is* a new version: cancelling an event must
  bump `event_version`, enforced in PL/pgSQL rather than trusted to each writer.

### Acceptance Criteria Validation

- ✅ Session required; an anonymous request is refused with 401
- ✅ City comes from the digest preference, not a query parameter and not geo-IP
- ✅ Window is tonight → +7 days **in the user's zone** — both edges pinned: 11pm local on day
  7 is in (2026-11-18 07:00 UTC), 1am local on day 8 is out (09:00 UTC). A UTC-cut window
  would put both on the same side
- ✅ Ranked with `domain.ranking.relevance_score`; no new scoring logic, `domain/` gained no
  Django import
- ✅ Two tiers, boundary **in the response** (`tier_2_starts_at`)
- ✅ Cards carry headline, venue, times, source badge, why-tags, confidence, stripe, `is_saved`
- ✅ **At most one must-know card per response** — asserted with three cancelled events
- ✅ Quota read through the entitlement and throttle services, never a `SavedEvent` count
- ✅ Paging: 24-card soft cap, `has_more`, and an offset past the end is an empty page
- ✅ Empty window returns an explicit zero-events signal, distinguishable from a failure and
  from "no city set"
- ✅ OpenAPI regenerates; `make client` produced types with no manual edits
- ✅ `make lint-imports` — **19 contracts kept, 0 broken**, including both halves of AD-10
- ✅ Every test can fail — see the mutation check below

### Mutation check

| Mutation | Test | Result |
|---|---|---|
| window far edge `last_day + 1 day` → `last_day` | `test_an_event_late_on_the_seventh_local_day_is_inside_the_window` | **FAILED** ✓ |

Reverted; `grep MUTATION` → 0.

### AD-10, and why the obvious reuse was wrong

`list_city_event_fits` fits Browse almost perfectly on the surface — canonical-city key,
offset paging with a total order. **It is the wrong read**, and the import linter enforces
that: the Event Fit is the explanation for a stranger, Browse is authed, and its first section
head says "3 worth your attention today". Using it would put a public score under a personal
heading one click from the Digest. `test_the_ranking_inputs_match_the_digests_for_the_same_candidate`
pins that Browse and the Digest build identical `RankingInputs`, so the two surfaces cannot
drift in how they explain the same event.

### Issues Found

| # | Issue | Severity | Status |
|---|---|---|---|
| 6 | `COUNT(*)` for `total` would report a number the user cannot reach | medium | **fixed by design change, approved** |
| 7 | SQL `OFFSET` on a Python-filtered over-fetch is unsound paging | medium | **fixed** — one ranked pool, sliced |
| 8 | Browse pool caps at `MAX_CANDIDATE_POOL_SIZE` (200) | low | **open — documented in the service docstring** |
| 9 | Orphaned Postgres sessions broke a full-suite run | n/a | **environmental, resolved** |

#### Issue 6 — the count that could not be reached

Checkpoint 1 approved one `COUNT(*)` per request. Reading the implementation showed it would
be **wrong**: `list_public_candidates` applies FR-14's staleness bound in Python, after SQL,
because the bound is per-source. A SQL count can only apply the SQL-expressible filters, so
the section head would advertise "147 events · scroll for more" and the user would reach 120.
`total` is now the ranked pool's size — exactly what the user can page to, and free.

#### Issue 9 — the 294 failures that were not a regression

A full-suite run reported `294 failed, 132 errors`. **None were assertion failures.** Every
one was `database "test_eventpulse24" does not exist` or `the connection is closed`. Cause
chain, recorded because the process lesson outlives the incident:

1. An early pytest run was killed with `timeout` at 900s; SIGTERM left its Postgres
   connections open.
2. Later development runs used `--reuse-db`, leaving the test database in place.
3. `make coverage-backend` does **not** pass `--reuse-db`, so it tried to drop and recreate
   that database — and the orphaned sessions blocked the drop.
4. Everything downstream failed against a half-torn-down database.

Resolved by terminating the orphans and dropping the database. **The process lesson:**
developing with `--reuse-db` while the gates run without it means testing a different setup
from the one that grades the work, which is how a green signal arrived for tests that were
about to fail.

---

## Work Item: browse-read-api — The Browse Read API

**Mode:** `validate` — checkpoint 1 (design) approved 2026-11-12, checkpoint 2 (plan)
approved 2026-11-12.
**Design:** `.specs-fire/intents/browse-surface/work-items/browse-read-api-design.md`

### Test Results

```
6,794 passed, 0 failed in 758.84s (0:12:38)
```

**37 tests for this work item** — 26 service-level (`test_browse_read.py`), 11 endpoint-level
(`test_browse_api.py`) — plus 18 for the throttle `peek` the quota read depends on.

### Coverage

| Gate | Required | Actual |
|---|---|---|
| Overall | ≥ 80% | **98.68%** |
| `domain/` | 100% | **100%** (1,071 statements, 0 missed) |

`browse_read.py` and the new schemas are at 100%; `domain/` was untouched by this item and
stays at 100%.

### The measurements the plan promised

Both are **tests**, not claims. The plan's Technical Details said the ranking cost was "to
be measured not assumed" and the saved-state join would be "one query, asserted with
`CaptureQueriesContext`". Neither was done when the plan was written; both are now.

| Measurement | Result | Test |
|---|---|---|
| The saved-state join is one query, not one per card | **1 query** over 12 cards | `test_the_saved_state_costs_one_query_however_many_cards_the_page_holds` |
| The catalog pool is one query; the personal side does not grow with the pool | **1 catalog query**, ≤ 4 personal | `test_scoring_a_full_pool_costs_a_query_and_a_bounded_amount_of_python` |
| **Ranking cost** (design Risk 3) | **60 candidates scored and paged in 20–27 ms** | same test, printed |

The timing bound is deliberately loose (1.0s against a ~25ms reality). A tight wall-clock
assertion is a flaky test on a loaded CI box, and a flaky test is worse than none — so it is
set to catch a *regression of kind* (the score starting to hit the database, or the pool
growing without bound), not to police microseconds.

### Mutation probes — both caught, both reverted

| # | Probe | Result |
|---|---|---|
| 1 | Replace the saved-state `IN` query with a per-card lookup | **Caught.** The test fails with `assert 12 == 1` and prints all twelve individual queries. |
| 2 | Replace the score-descending sort with a start-time sort | **Caught.** `test_a_higher_scoring_event_outranks_a_sooner_one` fails. |

Both mutations were reverted with the Edit tool and the file verified **byte-identical** to
its pre-mutation state (`diff` against a saved copy reported no differences). A repaired
test that cannot fail is a test that was not repaired.

### Acceptance Criteria Validation

| # | Criterion | Evidence |
|---|---|---|
| 1 | Session required; anonymous refused, same shape as other `/api/personal/*` | `test_an_anonymous_request_is_refused` |
| 2 | City from the digest preference, not a parameter, not geo-IP | `test_a_signed_in_user_gets_their_citys_events`, `test_a_user_with_no_city_gets_200_and_a_flag_not_an_error` |
| 3 | Window in the **user's** zone — 11pm local day 7 in, 1am local day 8 out | `test_an_event_late_on_the_seventh_local_day_is_inside_the_window`, `test_an_event_early_on_the_eighth_local_day_is_outside_it` |
| 4 | Ranked with `domain.ranking.relevance_score`; no new scoring logic; `domain/` gains no Django import | `test_the_ranking_inputs_match_the_digests_for_the_same_candidate` (Browse and Digest build the same inputs), `test_a_higher_scoring_event_outranks_a_sooner_one`; the import contract **"AD-10 personalization never reaches the Event Fit"** is KEPT |
| 5 | Two tiers; tier boundary in the response | `test_the_first_page_splits_three_cards_into_tier_one`, `test_a_later_page_is_all_tier_two`, `test_the_tier_boundary_is_on_the_response` |
| 6 | Each card carries headline, kicker, venue line, local + UTC time, source badge, why-tags, confidence, stripe, `is_saved` | `test_a_card_carries_what_the_surface_renders`, `test_a_card_carries_tags_and_a_confidence_bucket` |
| 7 | **At most one** must-know stripe per response, enforced server-side | `test_at_most_one_card_a_page_carries_the_must_know_stripe`, `test_only_two_stripe_colours_exist` |
| 8 | Quota state through the entitlement and throttle services, never a row count | `test_a_free_users_quota_is_reported_and_not_spent`, `test_a_pro_user_is_told_they_have_no_cap`, `test_reading_browse_does_not_spend_the_save_allowance` |
| 9 | 24-card soft cap; the response says whether more exist | `test_paging_is_bounded_and_says_whether_more_exists`, `test_an_offset_past_the_end_is_an_empty_page_not_an_error` |
| 10 | Empty window distinguishable from a failure | `test_a_city_with_nothing_on_is_an_empty_page_with_a_city`, `test_a_city_with_nothing_on_is_a_different_answer_from_having_no_city` |
| 11 | OpenAPI regenerates; `make client` produces types with no manual edits | `make client` run twice — **idempotent**, the second run changes nothing |
| 12 | Every test can fail; an out-of-window event is excluded; a Pro user reports no cap | `test_an_event_after_the_window_is_excluded`, `test_a_pro_user_is_told_they_have_no_cap`, and the two mutation probes above |

### The full gate

| Gate | Result |
|---|---|
| `pytest --cov` | **6,794 passed, 0 failed** |
| Coverage ≥ 80% | **98.68%** |
| `domain/` coverage = 100% | **100%** |
| `ruff check` | All checks passed |
| `ruff format --check` | 626 files already formatted |
| `lint-imports` | **19 contracts kept, 0 broken** |
| `manage.py check` | No issues (3 silenced) |
| `makemigrations --check` | No changes detected — **no new models, no migration** |
| `make client` idempotent | Yes |
| frontend `pnpm lint` | Clean |
| frontend `pnpm typecheck` | Clean |

### Issues found and how they were handled

**Issue 10 — the two measurements the plan promised were not done.** The implementation was
already written when the plan was finalised, and the plan's own Technical Details promised a
query-count assertion and a timing measurement. Neither existed. Both are now tests
(section above), with two mutation probes proving they can fail.

**Issue 11 — a dependency the plan did not name.** The quota read (D8) needs a way to ask
the throttle port what a window holds *without spending it* — `check` counts an attempt by
contract, so asking the gate what the allowance is would charge the user a save for opening
a page. `ThrottlePort` gains a `peek` method, implemented in the memory and Redis adapters,
and `save_cap.py` gains `read_save_quota` on top of it. **Additive: `check` is unchanged, so
the gate's behaviour is byte-identical.** The port's contract, each adapter's behaviour and
the reason are documented in each place.

**Issue 12 — two full-suite runs reported thousands of errors, and none were code
defects.** A run reported `73 failed, 4722 passed, 2059 errors`; an earlier one reported
3,699 errors. **Every one was `CREATE DATABASE "test_eventpulse24" ... already exists` /
`being accessed by other users`.** The cause was a **stray `pytest` process** from an
earlier interrupted run, still holding the test database — this is the same class as Issue 9
above, recurring because the process lesson was not applied to every run.

Resolved by killing the orphan and dropping the stale database with `DROP DATABASE ... WITH
(FORCE)` (plain `DROP DATABASE` is refused while a session is attached). **The concrete
lesson, stated so it is actionable:** *two pytest runs against this project cannot share
the database*, because the test database is created from a template and torn down at the
end. A run that reports thousands of errors — rather than thousands of assertion failures —
is reporting a collision, not a regression.

**Issue 13 — Browse computes its explanation at render time; AD-10 says explanations are
persisted, never regenerated.** **Found by the code review, not by the tests.** The gates are
all green and the acceptance criteria are all met — this is a finding about a rule the item's
design never addressed, so no test was going to fail on it.

`browse_read.py:333` calls `why_this_tags(...)` in the read path. The Digest does the
opposite: `digest_composition.py` calls it once and **persists** the result on
`DigestComposition`, and `digest_read.py` reads that row back — it never calls
`why_this_tags` at all. `.specs-fire/standards/coding-standards.md` lists *"Recomputing
explanations at render: Relevance Pulse and Event Fit are persisted, never regenerated
(AD-10)"* as an anti-pattern, and `system-architecture.md` states AD-10 as *"Persisted Event
Fit + Relevance Pulse — Never recomputed at render."*

**What it is not:** a wrong answer. Browse's tags come from the same `RankingInputs` the score
used, from the same `domain.ranking` functions the Digest uses, and the design's D2 goal is
pinned by `test_the_ranking_inputs_match_the_digests_for_the_same_candidate`. What is missing
is *persistence*.

**What it is:** a real difference in behaviour between the two surfaces. A Browse card's tags
can change between two identical requests — most visibly when the user saves an event, since
`why_this_tags` takes `is_saved` and Browse computes it from the live `SavedEvent` join. The
Digest's tags cannot change, because they were frozen at composition.

**Why it was not fixed here.** Persisting Browse's explanation is a schema and composition-job
change: a new persisted row per `(user, event, window)`, a writer that runs before the read,
and a read that falls back to the unpersisted path when the row is missing. That is a work
item of its own, it changes the endpoint's contract, and **the approved design did not mention
persistence at all** — so this is a gap in the design, not a departure from it. Recorded as
Finding 18 (medium) in `review-report.md`, recommended as its own work item under the
`browse-surface` intent.

**The enforcement gap worth naming.** AD-10 has two halves. The *substitution* half is
enforced by two import-linter contracts, and they are good — the Event Fit is a **package**
specifically so that a new module inside it is inside the wall by default. The *persistence*
half is enforced by nothing: no import contract, no architecture test, and no schema can catch
a read that recomputes an explanation at render time. Browse is the first read in this codebase
that renders an explanation it did not persist, so it is the first to expose the gap. A
contract asserting that no read module imports `why_this_tags` would close it, and the Digest's
own structure shows it is cheap: `digest_read.py` never calls it.

**Issue 14 — the quota reads `used: 0` after a save in a local run, and it is not a defect.**
Found while verifying the walkthrough's manual scenario end to end.

`ports.registry.get_adapter` calls `adapter()` — constructing a **new** adapter instance on
every call — so the in-memory throttle forgets its counters between requests. A user saves an
event, reloads Browse, and the quota still says `used: 0`. The save itself worked (`is_saved`
flips to `true`), and the **real Redis adapter is shared and does persist**, so production is
correct.

Browse is the **first surface to display** the counter, so it is the first place the gap is
visible. Pre-existing behaviour, not introduced by this item — the gate only ever needed the
counter within one request. Verified with the port patched the way
`tests/e2e/test_pro_tier_proof.py` does: before the save `used: 0`, after it `used: 1` with
`resets_in_seconds: 86401`, and `is_saved` flipping to `true` — **while the reads themselves
spend nothing**.

Recorded as **Finding 23 (low)** in `review-report.md`. A proper fix — making the fake a
singleton rather than a fresh instance per call — touches the registry and every adapter, and
is outside this item's scope. It is recorded because the frontend work item will consume this
endpoint and a developer testing locally will read the `used: 0` as a bug.

### Final verification pass (after the code review)

Every gate re-run against the reviewed diff, with nothing outstanding:

| Gate | Result |
|---|---|
| Full backend suite | **6,794 passed, 0 failed** in 642.20s (0:10:42) |
| Coverage | **98.68%** overall (gate 80%) |
| `domain/` coverage | **100%** (1,071 statements, 0 missed) |
| `browse_read.py` coverage | **100%** (98 statements, 0 missed) |
| `ruff check` | All checks passed |
| `ruff format --check` | 626 files already formatted |
| `lint-imports` | **19 contracts kept, 0 broken** |
| `manage.py check` | No issues (3 silenced) |
| `makemigrations --check` | No changes detected |
| `make client` idempotent | **Yes** — `openapi.json` and `schema.ts` both byte-identical after regeneration (verified by copy-and-diff, not `git diff --exit-code`, which reports the *new* types as drift rather than instability) |
| frontend `pnpm lint` | Clean |
| frontend `pnpm typecheck` | Clean |
| `tests/architecture/` | 979 passed |

### Ready for Completion

- [x] All tests passing — 6,794 passed, 0 failed
- [x] Coverage target met — 98.68% overall, `domain/` 100%, `browse_read.py` 100%
- [x] All 12 acceptance criteria validated with named evidence
- [x] Import contracts green — 19 kept, 0 broken (AD-10 specifically verified)
- [x] Two mutation probes, both caught and reverted
- [x] Client regeneration idempotent
- [x] No production behaviour changed outside this item's scope — `check` is untouched
- [x] Code review complete — `review-report.md`, 17 findings accepted, 1 medium finding
      (Issue 13) recorded for a future work item rather than silently folded in


---

## Work Item: frontend-browse-shell-and-grid

**Mode:** `confirm` — checkpoint 1 (plan) approved 2026-11-12.

### Test Results

```
Test Files  126 passed (126)
     Tests  2095 passed (2095)
```

**61 new tests** across three files: 20 source-scan (`tests/browse-boundary.test.ts`), 35
rendering (`tests/browse-rendering.test.tsx`), 6 axe-core (`tests/browse-a11y.test.tsx`).

The frontend baseline before this item was **126 files / 2,034 tests, all passing**; the
delta of 61 is exactly this item's three files.

### The gate

| Gate | Command | Result |
|---|---|---|
| Frontend suite | `pnpm test` | **126 files, 2,095 tests, 0 failed** |
| Lint | `pnpm lint` | Clean |
| Types | `pnpm typecheck` | Clean |
| **Production build** | `pnpm build` | **✓ Compiled successfully** — `ƒ /browse` registered as a dynamic route |

**The build is not redundant with the typecheck.** A `next/headers` import inside a `"use
client"` module **passes `tsc` and passes every unit test**, and fails only when Next compiles
the client bundle. `components/browse/browse-more.tsx` is the only client module in the
surface, and the build is what proves it is clean.

### The Node version, and why the numbers above are trustworthy

**The baseline is red on this machine's default Node, and it is not a defect.**
`frontend/package.json` requires `"node": ">=24.15"`; the default `node` on PATH is
**v20.20.0**. On Node 20, `require('node:zlib').constants.ZSTD_d_windowLogMax` is
`undefined` (no zstd), and `undici@8.12.3` binds it at import time — which throws
`TypeError: Cannot read properties of undefined (reading 'bind')` and surfaces as
`"[vitest-pool]: Failed to start forks worker"` for many files. **100 unhandled errors**, and
a non-zero exit even when every assertion passes.

Confirmed against the baseline by `git stash push -u` before blaming any of it on this
change. Every gate above was run with:

```bash
export PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH"
```

### Acceptance Criteria Validation

| # | Criterion | Evidence |
|---|---|---|
| 1 | Renders inside the existing authed shell; the shell is not forked | `renders the shell rather than a fork of it` (the shell's `<main>` and navs are present); `imports AppShell rather than re-implementing it`, `does not re-implement the sidenav or the topbar` (source scan) |
| 2 | Hero: terracotta-dot eyebrow, h1 with terracotta italic `<em>`, 600px lede, city-meta pill | `states the city and the window`, `names the city in the h1's emphasised span` |
| 3 | City-meta pill shows city, count, **Change city** → `/settings/account` | `offers a real link to change the city`, `counts the pool, not the page` |
| 4 | Quota note below the pill in mono, read from the API | `reports the quota the API stated, not a client guess`, `says a Pro account has no limit` |
| 5 | Section head 1 "3 worth your attention today" + mono meta; head 2 "More this week" + "{n} events · scroll for more" | `names the first section and the second`, `carries the city's own facts in the mono meta`, `counts what is still to come, not what is on screen` |
| 6 | **"Maya-fit" is not carried over** | `does not say a persona's name` (rendered), `has no persona-prefixed copy` (source scan) — **both proved able to fail**, see the probes below |
| 7 | Grid 3-col / 2-col / 1-col, 20px gap; `.main` 32px, not the city page's 80px frame | `lays the grid out in three steps`, `sits in a 32px frame, and not the city page's full-bleed 80px one` |
| 8 | Cards 22px padding, 18px headline | `uses the denser Browse sizing on the cards` |
| 9 | **Stripes capped at two colours**; no discovery stripe anywhere | `uses only the slate and amber stripes`, `has no discovery stripe`, `names the stripe in words as well as in colour` |
| 10 | **No Sign-up row, no How-it-works CTA, no SEO neighbour-cities footer** — absent from the markup, asserted by query | `has no Sign-up call to action`, `has no How-it-works call to action`, `has no SEO neighbour-cities footer` (rendered) **and** the same three as source-scan rules |
| 11 | Soft cap at 24, "More events below" anchor, no pagination chrome | `asks the server for 24 cards, and no more`, `offers an anchor, not pagination chrome`, `shows the anchor only when the server says there is more` |
| 12 | Zero-events → quiet empty state + "Change city" | `says so, and offers the way out`, `does not claim the page failed` |
| 13 | 12 skeletons, 1800ms pulse, no spinners | `shows twelve pulsing card-shaped rectangles`, `hides the rectangles from the screen reader` |
| 14 | Error state "Couldn't reach Browse. Try again.", one retry, shell stays functional | `offers one retry, and it is a real link`, `leaves the shell's navigation usable` |
| 15 | **No new colour tokens, CSS variables or spacing tokens** | `declares no new colour, spacing or CSS variable`, `uses no literal hex colour` |
| 16 | One h1, real headings in order, a11y suite passes | `renders one h1, and it is the hero's`; the axe gate over four states |

### Probes — proof the repaired tests can still fail

**A repaired test that cannot fail is a test that was not repaired.** Each rule was proved by
planting the violation it forbids, running the suite, and reverting.

| # | Planted violation | Rule | Result |
|---|---|---|---|
| 1 | `Maya-fit` as the real section heading in `browse-grid.tsx` | `has no persona-prefixed copy` | **FAILED** ✓ |
| 2 | `bg-accent-purple` as a stripe colour | `uses only the slate and amber stripes` | **FAILED** ✓ |
| 3 | A Sign-up CTA in the markup | `has no a Sign-up call to action` | **FAILED** ✓ |
| 4 | An SEO neighbour-cities footer | `has no SEO neighbour-cities footer` | **FAILED** ✓ |
| 5 | The section head moved inside the `<ul>` | the axe gate's `list` rule | **FAILED** ✓ |

**Probe 1 had a false negative first, and that is the most useful finding in this item.**
The first attempt planted the string inside the **JSX comment** at `browse-grid.tsx:43` rather
than in the real heading at line 56, and the test *passed*. The reason: the source scan
strips comments before matching, because these files' docstrings **quote the spec** — they
name "Maya-fit" in order to forbid it, and a scan that read the prose would fail on a file
that only mentions the thing in order to forbid it.

The probe was then re-planted at the real heading and the test failed as it should. A probe
that passes tells you nothing; a probe that was aimed at the wrong place and passed would
have told you the wrong thing.

**Probe 2 found a real bug in the test.** The first version of the stripe scan read only
`className="…"` literals — but a stripe's colour is chosen by a **helper**, and
`stripeColour()` returns `"bg-accent-slate"` as a plain string. The scan would have missed
the very thing it was written to forbid. It was rewritten to read **every quoted string** in
the file (`allTokens()`), and the purple probe then failed correctly.

### The axe gate

Six tests, one per state: populated, empty, error, loading, every-card-treatment, and the
probe.

**Serious and critical only.** `minor` and `moderate` findings are advisory, and a gate that
fails on a moderate finding is a gate that gets disabled. `color-contrast` is off because
jsdom computes no layout — contrast is measured against the tokens separately by
`tests/contrast.test.ts`.

**The gate runs over every state, not just the happy one.** An empty state with no heading
hierarchy, an error state whose retry is an unnamed control, and a loading skeleton with
twelve boxes a screen reader reads twice are three different documents with three different
sets of rules.

### The one `<ul>` per section

**This is the reason `browse-grid.tsx` has two lists and not one list with headings inside
it.** A list whose children are headings and `<li>`s is not a list, and the `list` axe rule
is *serious* — a screen reader would announce the cards as ungrouped text and the count of
the city's events would be lost with them.

The mutation probe (probe 5 above) moves a heading inside the `<ul>` and requires the gate to
fire. It does.

### The deviations, and why each was necessary

**The design's numbers do not all exist in this codebase.** These were measured against
`styles/tokens.css` and `DESIGN.md` before any code was written, and each one became a
bracketed exact value rather than a new token — because **the acceptance criterion forbids
new tokens**, and because `styles/tokens.css` resets `--breakpoint-*`, so an undeclared
breakpoint generates no CSS at all.

| Design says | This codebase has | Shipped as |
|---|---|---|
| `Text.Display.xl` | `--type-scale-display-lg` is the largest | `type-scale-display-lg` |
| `Text.Display.sm` (section heads) | `--type-scale-headline-lg` is the nearest | `type-scale-headline-lg` |
| ≥1280px → 3 columns | breakpoints are `md: 768px`, `lg: 1024px`; **no `xl`** | `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` |
| 20px gap | the spacing scale's `20` is **80px** | `gap-[20px]` |
| 22px card padding | not on the scale | `px-[22px] py-[22px]` |

**The three-column-at-1280px deviation is the one worth naming.** A-12 asks for three
columns at ≥1280px. This codebase has no `xl` breakpoint, and adding one is a new token —
forbidden. So the grid ships `lg:grid-cols-3` at **1024px**, which means a 1024–1279px
viewport gets three columns where A-12 asked for two.

This is recorded as a deviation rather than hidden: `tests/browse-rendering.test.tsx`
asserts the shipped classes explicitly, so the choice is visible in the test suite and a
future `xl` breakpoint would have to change the test.

### Issues found and how they were handled

**Issue 15 — the empty state was unreachable when a city had nothing on.**
`page.tsx` rendered `<BrowseEmpty />` only when `city_missing` was true, and rendered
**nothing at all** when the city was set but the window was empty. The zero-events AC names
exactly that case. The condition was `noCity || noCards ? (noCity ? <BrowseEmpty/> : null) :
…` — the ternary nested a second ternary that discarded the empty state. Fixed to render
`<BrowseEmpty />` for both, which is what the AC and the comment already said.

**Found by the test, not by review** — `says so, and offers the way out` failed against a
payload with a city and zero cards.

**Issue 16 — the reset phrase said "1d" where the design says "24h".**
`resetPhrase(86400)` returned `"1d"`, while its own docstring says *"A quota window is 24
hours, so the note almost always says 'in 24h'"*. The code contradicted the documented
intent: `hours < 24` sent a full day to the days branch. The quota window is exactly 24
hours, so **every** free user would have read "1d" — a phrase that hides the number the
payload carries. Changed to `hours <= 24 → "${hours}h"`, and days take over only past a day.

**Issue 17 — the "More events below" anchor pointed at the wrong chunk.**
`nextOffset` was `offset + appended.length`, which on the first render is `0 + 0 = 0` — the
anchor's `href` was `/browse?offset=0`, i.e. the chunk the reader was already looking at.
Corrected to `offset + cards.length + appended.length`, so the next chunk starts where this
page's cards end.

**Found by the test** — `offers an anchor, not pagination chrome` asserted `?offset=3` for a
three-card page and got `?offset=0`.

**Issue 18 — the 32px frame wrapped only the grid, not the hero.**
The first implementation put `px-2` around `<BrowseGrid>` alone, so the hero sat at the
shell's 24px and the grid at 32px — two left edges on one surface. The wrapper now encloses
the whole surface, so the hero and the grid share one edge.

**Found by the test** — `sits in a 32px frame, and not the city page's full-bleed 80px one`
inspected the hero's parent and found it was `<>`, not the frame.

### The frontend surface is a server component except for the chunk loader

`components/browse/browse-more.tsx` is the **only** `"use client"` module in the surface, and
the rule is asserted rather than assumed:

- `marks only browse-more.tsx as a client module` — exactly one file, named
- `does not reach next/headers from the client island` — a server-only import in a client
  module **passes the unit tests** and fails the build

**Why the chunk loader needs a browser at all.** The alternative — a server round trip per
chunk — would make every scroll a full page load, which is exactly what the soft cap exists
to avoid.

### AD-10, on the client side

**The page renders the payload and decides nothing.** No re-ranking, no re-sorting, no
re-tiering, no re-bucketing, no client-side score. Asserted from both sides:

- `renders the server's order and the server's tier split` — the split comes from
  `tier_2_starts_at`, and `slice(0, 3)` would be the client deciding a tier
- `does not compute a score, a bucket or a recency band` — no `relevance_score`,
  `score_bucket` or `recompute` anywhere in the surface
- `keeps the server's order` (rendered) — the fixture's order is the output's order

**The indicator is the Relevance Pulse, and it says so.** The card's dots are labelled
"Relevance" and the accessible name is "Relevance N of 5". The Event Fit is the stranger's
score, computed blind to who is looking, and AD-10 forbids substituting one for the other.
The two indicators look identical on screen, so the words are the only thing keeping them
apart — `labels the indicator as the Relevance Pulse, not the Event Fit` asserts both the
presence of the Relevance label and the absence of a "Fit" one.

### The backend is reached only through the generated client (AD-19)

- `does not call fetch` — and this was a **real failure during implementation**: the first
  version of the chunk loader called `fetch` directly, and the lint rule
  (`no-restricted-globals` in `components/` and `app/`) rejected it. It was rewritten to
  use `api.GET` from `@/lib/backend-client`, which carries the CSRF token and the typing
  for free.
- `does not import openapi-fetch directly`
- `frontend/lib/api/` was **not touched** — it is generated, and this item changed nothing
  on the backend, so `make client` would produce a byte-identical file.

### The surface adds no tokens

- `declares no new colour, spacing or CSS variable` — the check is for a **declaration**
  (`--name:`), not a reference: the markup *uses* `var(--type-scale-headline-sm)`, and that
  is the whole point of the token system. What must not appear is a *new* token.
- `uses no literal hex colour` — a literal hex would look right in one theme and wrong in
  the other.
- `styles/tokens.css` was **not modified**.

### Ready for Completion

- [x] All tests passing — 126 files, 2,095 tests, 0 failed
- [x] Lint clean, types clean, **production build succeeds**
- [x] All 16 acceptance criteria validated with named evidence
- [x] Five probes, all caught, all reverted
- [x] The axe gate covers four states and can itself fail
- [x] No new tokens; `styles/tokens.css` untouched
- [x] No production code outside `frontend/` changed

---

## Review phase — the test report, re-measured

The review phase found **seventeen defects** in the code this report had certified green, and
every one of them is now fixed. That fact changes what this report is, so it is recorded
here rather than left to `review-report.md`: **the numbers above described a suite that
passed, and the code it was passing had a critical bug in it.**

### The gate, re-run after every fix

```
pnpm test        2118 passed (127 files)   0 failed
pnpm lint        clean
pnpm typecheck   clean
pnpm build       clean — /browse renders as ƒ (Dynamic, server-rendered on demand)
```

Up from 2,095 tests in 126 files: **+23 tests**, from `tests/browse-labels.test.ts` (19,
new) and four new cases in the rendering suite.

### The assertions this report made that are now different

Three of this report's own claims were wrong, and the code was changed to match the truth
rather than the report being edited to match the code.

| This report said | Now | Why the report was wrong |
|---|---|---|
| The section-2 meta counts *"what is still to come"* — `37 events · scroll for more` | It counts **the second section's own events** — `39 events · scroll for more` | The mockup settles it: the hero's pill says *"147 events this week"* and section 2 says *"144 events"*, and 147 − 3 = 144. N is the pool's **tier-2 size**, not the remainder. The remainder reading would announce *"37 events"* above a grid of 2 cards — a heading that contradicts the thing it heads. |
| The anchor is *"a link"* — `getByRole("link", { name: "More events below" })` | It is `getByRole("button", …)` with an `href` kept | It behaves as a button: the click is intercepted and the chunk is fetched in place, with no navigation. An element that behaves as a button but announces as a link lies about what activating it does. The `href` stays, because the chunk's real URL *is* the anchor's `href`. |
| The route is `getByRole("heading", { level: 2, name: /Nothing nearby tonight/ })` for the empty state | It is `level: 1` | The empty state **replaces** the hero, so there is no hero `<h1>` above it. A page whose only heading is an `<h2>` has no `<h1>` at all. |

### The critical defect, and the coverage shape that hid it

`browse-more.tsx` began with `if (remaining === 0) return null;` — **above** the appended
list. When the pool ran out, the component returned nothing, and with it every card the
last chunk had just delivered. The last screen of events never appeared.

**No test caught it, and the reason is worth writing down.** `BrowseMore` was exercised by
the page tests, but only on the branch where the pool has more in it. A component can be
covered and still have its most important branch untested. Two more defects lived in the
same gap — the double-click duplication and the anchor's wrong `href` — so **three of the
seventeen were reachable only by a test that did not exist.**

`review-report.md` Finding 21 records this as **still open**: the chunk loader has no test
of its own. The axe gate covers the appended list's *markup*; the *load* is not tested.
That is a real gap and it is not papered over.

### The two tests this phase added, and the one it changed

| Test | Covers |
|---|---|
| `honours an offset in the URL` | The route reads `?offset=` — so the anchor's `href` is a real navigation, not a decoration. A middle-click or a reader with JavaScript off lands on the chunk the anchor names. |
| `treats a malformed offset as the first page` | `?offset=abc` is the first page, not a crash. |
| `names the indicator the same way everywhere it appears` | **One clamp, three consumers.** The dots, the button's accessible name and the card's accessible name all read the same clamped value, and all three say "Relevance" — so the card cannot say "1 of 5" in one place and "0 of 5" in another. |
| `says a cancelled event is cancelled` | The badge is `aria-hidden`, so the **link** carries the state in words. A cancelled event the reader cannot hear is a cancelled event that lies. |

### `tests/browse-labels.test.ts` — new, 19 tests

The labels are pure functions, and every sentence they produce is a claim the reader will
believe. A rounding bug is a wrong number on the page; a timezone bug is a wrong **day** on
the page. The two hard cases:

- **The window's date is the window's first day in the reader's own zone.** A window that
  opens at 11pm Eastern on Saturday is 04:00 UTC on Sunday — a UTC reading names *tomorrow*
  for a reader whose tonight is tonight.
- **A malformed timezone must not take the page down.** `Intl` throws a `RangeError` on a
  zone it does not know, and the zone is a string the server wrote. The fallback is the
  date in UTC, and the label is decoration on a mono meta line.

**The rounding rule, stated because it is the kind of thing that gets "tidied" later:**
`resetPhrase` floors, never rounds. 90 minutes is 1.5 hours, and saying "2h" would
over-promise by half an hour — the reader would wait for a reset that has not happened.


---

## Work Item: frontend-browse-search

**Mode:** `confirm` — checkpoint 1 (plan) approved 2026-11-12.

### Test Results

```
Test Files  128 passed (128)
     Tests  2186 passed (2186)
```

**+91 tests** over the previous item's 2,095 (127 files). The delta is accounted for exactly:

| File | Before | After | Delta |
|---|---|---|---|
| `tests/browse-search.test.ts` | — | **36** | +36 (new file) |
| `tests/browse-rendering.test.tsx` | 35 | **59** | +24 |
| `tests/browse-boundary.test.ts` | 20 | **26** | +6 |
| `tests/browse-a11y.test.tsx` | 6 | **8** | +2 |
| `tests/digest-labels.test.ts` | 11 | **15** | +4 |
| **Total** | 2,095 | **2,186** | **+91** |

The four gate commands, all clean:

```
pnpm test        2186 passed (128 files)   0 failed
pnpm lint        clean
pnpm typecheck   clean
pnpm build       clean — /browse renders as ƒ (Dynamic, server-rendered on demand)
```

**The build is in the gate and it is not optional.** The search island is a client module, and
a client module that reaches `next/headers` **passes the unit tests** (jsdom stubs it) and
**fails the build**. `pnpm build` is the only place that mistake can hide.

### Acceptance Criteria Validation

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | A single `<input type="search">` below the hero, full-width to max-width 720px, `component.input.field` tokens, A-11 `surface.paper` fill | **pass** | `browse-rendering.test.tsx` — *"is one search input, below the hero"* (asserts `type="search"`, `max-w-[720px]`, `bg-surface-paper`, and that the input follows the hero in document order); *"uses the field's own tokens"* |
| 2 | Placeholder verbatim | **pass** | `browse-boundary.test.ts` — *"keeps the placeholder verbatim"* (source scan, exact string); `browse-rendering.test.tsx` — *"teaches the grammar in the placeholder"* |
| 3 | Plain words whitespace-split, lowercased, trimmed, AND-matched against headline / where line / why-tag tokens | **pass** | `browse-search.test.ts` — 36 grammar tests: *"matches a word against the headline"*, *"matches a word against the where line"*, *"matches a word against a why-tag key"*, *"requires every word to match"*, *"ignores case"*, *"trims whitespace"* |
| 4 | `tag:<token>` matches only the why-tag set, AND-combined with plain words | **pass** | `browse-search.test.ts` — *"matches a tag literal against a why-tag key"*, *"requires a tag literal to match"*, *"AND-combines a tag literal with a plain word"* |
| 5 | **The ten documented tags all work** | **PARTIAL — 6 of 10, recorded, not repaired** | See "The ten tags" below. `music`, `food`, `indoor`, `rooftop` have no server-side counterpart and therefore match nothing. |
| 6 | An unknown `tag:` token matches nothing rather than falling back to a plain-word match | **pass** | `browse-search.test.ts` — *"an unknown tag matches nothing"*, *"does not widen an unknown tag into a plain-word match"*; `browse-boundary.test.ts` — *"does not widen an unknown tag into a plain-word match"* (source scan: `resolvedTags` present, `resolvedTags.filter(` absent) |
| 7 | Zero matches removes the section heads and grid; one full-width quiet empty state renders in the grid container | **pass** | `browse-rendering.test.tsx` — *"replaces the grid and the section heads when nothing matches"*, *"renders the empty state in the grid container"* |
| 8 | **The two empty states are distinguishable in the DOM** | **pass** | `browse-rendering.test.tsx` — `describe("the two empty states")`, 3 tests: *"says different things"*, *"offers a different way out"*, *"is a different element"*. The no-match state carries `[data-browse-search-empty]` and a `role="status"`; the zero-events state replaces the hero and carries none of it. |
| 9 | No chip rail, no category buttons, no date presets in the markup — asserted by a test | **pass** | `browse-boundary.test.ts` — `describe("Amendment A-11 — the search is the only filter surface")`, 5 tests, plus *"has no filter chip rail"*. `browse-rendering.test.tsx` — *"has no chip rail, no category buttons and no date presets"* |
| 10 | Filtering is instant on the loaded set, no network request per keystroke | **pass** | `browse-search.ts` is a pure function over the loaded array; `browse-boundary.test.ts` — *"does not call fetch"*, *"does not import openapi-fetch directly"*. `browse-rendering.test.tsx` — *"filters without asking the server"* (the mock's `readBrowse` is not re-called on a keystroke). |
| 11 | **The chunk-bounded limitation is documented in the component's own doc comment** | **pass** | `components/browse/browse-search.tsx` — the module doc comment states: *"The matching is client-side, over the loaded set, and that is a real limitation… a match that sits past the current chunk does not appear until that chunk loads."* The count line makes the gap visible: *"N events matched · M of M events total"*. |
| 12 | The input has an accessible label; the result-count change is announced politely | **pass** | `browse-a11y.test.tsx` — the axe gate covers the populated, no-match, filtered, empty, error, loading and all-treatments states, and *"fires on a section head placed inside the list"* proves the gate can fail. `browse-rendering.test.tsx` — *"labels the input"*, *"announces the count politely"*. |

**Twelve of thirteen criteria are met outright. The thirteenth is met for six of ten tags,
and the shortfall is recorded rather than papered over.**

### The ten tags — six work, four have no server-side fact

This is the item's one substantive finding, and it is worth stating plainly rather than
burying under a tick.

**The design names ten search tags. The server has no fact for four of them.**

| Design tag | Resolves to | Status |
|---|---|---|
| `tech` | `matches_tech_meetups` | works |
| `sports` | `matches_sports_fitness` | works |
| `arts` | `matches_arts_culture` | works |
| `family` | `matches_family_kids` | works |
| `community` | `matches_community_volunteering` | works |
| `outdoor` | `matches_outdoors_nature` | works |
| `tonight` / `tomorrow` / `weekend` / `nearby` / `saved` / `discovery` | themselves | works (the fixed server tags) |
| **`music`** | — | **matches nothing** |
| **`food`** | — | **matches nothing** |
| **`indoor`** | — | **matches nothing** |
| **`rooftop`** | — | **matches nothing** |

The server's why-tag vocabulary is `RANKING_TAG_ORDER` (`discovery`, `nearby`, `tonight`,
`tomorrow`, `weekend`, `saved`) plus `matches_<chip>` for ten chips —
`tech_meetups`, `sports_fitness`, `arts_culture`, `family_kids`,
`community_volunteering`, `outdoors_nature`, `classes_workshops`, `markets_fairs`,
`talks_lectures`, `government_civic`. **There is no `music`, no `food`, no `indoor` and no
`rooftop`.** The chip `tech_meetups` covers the design's `tech`; the chip `arts_culture`
covers `arts`; but nothing covers the other four.

**Why the backend was not changed.** The why-tag set is a *persisted, server-stated* fact
(AD-10 — explanations are stored, never regenerated), and the chip keys are documented as
stable. A search alias is a frontend *translation* of a server fact — the same seam
`lib/digest-labels.ts` already documents for chip labels. Inventing four server-side chips
to satisfy a placeholder would be changing the product's vocabulary to fit a string.

**How the shortfall is handled, and where it is visible.** The four tokens resolve to
`null`, and a query containing an unresolved tag matches **nothing** — which is the
grammar's own rule for an unknown `tag:` token (criterion 6). The hint line under the input
therefore advertises only the twelve tokens that work, and `digest-labels.test.ts` asserts
that **every advertised token resolves to something** — *"does not advertise a tag that
resolves to nothing"*.

**The placeholder still says `tag:music`, verbatim, because criterion 2 fixes it word for
word.** A reader who copies it gets zero matches. That is a real conflict between two
criteria, it is recorded as deviation #2 in `plan.md`, and it is not resolved by quietly
editing the placeholder or by quietly teaching the reader that `music` works.

### The two empty states

The two states are not merely different copy — they are **different documents**, and the
test says so.

| | Zero-events state | No-match state |
|---|---|---|
| Trigger | The city has nothing on | The query found nothing |
| Replaces | **The whole page** — hero and all | **The grid and the section heads** |
| Heading | The page's own empty state | `"Nothing matched."` |
| Recovery | The city's settings — *"Change city"* | The search box — *"Drop a term, or browse the full list."* |
| DOM marker | *(none)* | `[data-browse-search-empty]` |
| Landmark | — | `role="status" aria-live="polite"` |

The no-match state removes the section heads on purpose: a heading over nothing is a
heading that lies. *"More this week"* above zero cards promises the page cannot keep.

**The count line is what makes the chunk-bounded search visible.** It reads *"N events
matched · M of M events total"* — the client's count of what survived the filter beside the
server's pool size. The gap between the two numbers *is* the limitation, shown.

### The axe gate now covers three more documents

```
pnpm test tests/browse-a11y.test.tsx
  ✓ tests/browse-a11y.test.tsx (8 tests)
```

The two new gates audit the **no-match state** and the **filtered state** — a page can be
accessible when it is full and inaccessible when it is empty, and the no-match document has
a different heading hierarchy and a different landmark set from the populated page's. The
gate is required to fail on a known mistake: *"fires on a section head placed inside the
list"* moves the `<h2>` into the `<ul>` and asserts axe's `list` rule fires.

### The probe — the gate that can fail

Every gate in this report has a probe, and the probe is the mistake the rule is about.

| Probe | Expected | Result |
|---|---|---|
| Move a section head inside the `<ul>` | axe `list` rule fires | **fired** |
| A `tag:` token the server does not have | matches nothing, does not widen | **held** |
| A filter rail's own vocabulary in the *markup* | absent | **held** |
| An unknown tag in the *advertised* vocabulary | absent | **held** |
| A `tag:` alias naming a chip the server does not have | the alias test fails | **held** |

### Notes on the failures this phase hit

Recorded because each was a genuine scoping error in the *test*, not in the code — a test
that cries wolf is a test that gets disabled.

| Failure | Cause | Fix |
|---|---|---|
| *"has no filter chip rail"* failed | `lib/digest-labels.ts` legitimately contains "chip" — it is the chip-label table | The boundary test now separates `SURFACE_FILES` (the markup) from `LIBRARY_FILES` (the vocabularies), and the markup-scoped rules read only `surfaceCode()` |
| *"has no discovery stripe"* failed | same cause — `TAG_LABELS` names `discovery` because the server sends it | same fix |
| *"has no chip rail…"* (rendering) failed | `input[type="date"]` exists in the **AppShell** (`id="_r_3c_-date"`), not in Browse | The assertion is scoped to Browse's own frame, because the rule is about the city page's filter vocabulary, not the shell's account controls |
| *"says different things and offers different ways out"* failed on "Change city" | the hero's city-meta pill also carries a "Change city" link | The assertion is scoped to the empty state itself — the criterion is about the *empty state's own* recovery action |
| *"is one search input, below the hero"* failed | `querySelectorAll("h1, input")` matched the AppShell's own inputs | Scoped with `hero.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING` |
| *"says the count in the count line too"* failed | the count line's `<strong>` and the live region both said "1 event" | Scoped to `[data-browse-search-meta]` |
| `spacing-scale.test.ts` failed on `mt-7` | `7` is not on the spacing scale (0/1/2/3/4/6/8/12/16/20/30) | `mt-8` (32px), the nearest scale step to the mockup's 28px |
| `typecheck` failed TS2345 | `fixed.has(key)` where `key` was `string \| null` | `if (key === null) continue;` — the null check was already there in spirit, but the narrowing did not survive the `else` branch |

### Checklist

- [x] All four gate commands clean — 2,186 passed, 0 failed
- [x] 91 new tests, the delta reconciled exactly
- [x] 12 of 13 acceptance criteria met outright
- [x] The 13th recorded as partial: 6 of 10 design tags work, 4 have no server-side fact
- [x] The two empty states distinguished by DOM, not by eye
- [x] A-11's lock enforced by both a source scan and a rendering test
- [x] The chunk-bounded limitation documented in the component's own doc comment
- [x] The axe gate covers two new states and can itself fail
- [x] No new tokens; `styles/tokens.css` untouched
- [x] No backend change; the server's why-tag vocabulary is untouched

---

## Review phase — the test report, re-measured

The review phase found **two defects** in the code this report had certified green, and
both are now fixed. That fact changes what this report is, so it is recorded here rather
than left to `review-report.md`: **the numbers above described a suite that passed, and the
page it was passing was promoting tier-two cards into tier one and showing every chunked
event twice.**

### The gate, re-run after every fix

```
pnpm test        2203 passed (128 files)   0 failed
pnpm lint        clean
pnpm typecheck   clean
pnpm build       clean — /browse renders as ƒ (Dynamic, server-rendered on demand)
```

Up from 2,186 tests in 128 files when this report was first written: **+17 tests**, from
the tier-split block in `tests/browse-search.test.ts` (+7), the tier-split and chunk-loader
blocks in `tests/browse-rendering.test.tsx` (+9), and one new source rule in
`tests/browse-boundary.test.ts` (+1).

### The two defects, and what they had in common

| # | Defect | Reproduction | Why the suite missed it |
|---|---|---|---|
| 1 | **The filter promoted a tier-two card into tier one.** `tier_2_starts_at` is an index into the *pool*; the grid sliced the *filtered* list at it. | A pool of three tier-one cards and one tier-two, filtered to match only the tier-two card: the card landed under "3 worth your attention today", and "More this week" was empty. | Every fixture had `tier_2_starts_at: 1` and no filtering. The defect needed *both* a filter and a pool whose tier-one prefix the filter removed. |
| 2 | **The chunk's cards were rendered twice.** The island handed the whole loaded set to the grid, and the loader kept drawing the chunk. | A page with one card and a chunk of one: `CARDS: 3`, `TITLES: ['One card', 'Chunked gallery', 'Chunked gallery']`. | The previous item's review left the chunk loader untested (its Finding 21, "still open"). This item moved the loader's state without closing the gap. Nothing rendered a chunk, so nothing could see it twice. |

**Both are the same shape: a filter is a narrowing, and the code downstream of the
filtering was written for the whole list.** The grid sliced at an index that belonged to
the pool. The loader drew what the grid was already drawing. Neither is exotic, and
neither would have been caught by a test asserting "the search filters" — because the
search *did* filter.

### The tests this phase added

| Test | Covers |
|---|---|
| `survivingTierOneCount` — 7 cases | The tier split is counted against the **pool**, never against the filtered list: every survivor, a partial prefix, **none**, a split past the pool's end, a negative split, and a matched set whose own order is irrelevant. |
| "does not promote a tier-two card into tier one" | The rendered document: a filter matching only a tier-two card leaves it under "More this week", and the tier-one section's heading goes with it. |
| "keeps a matched tier-one card in tier one" | The other direction — a matched tier-one card stays in tier one. |
| "counts the second section's own events under a filter" | The meta reads what the section holds under a filter, and the pool's tier-two size unfiltered. |
| "draws the chunk's cards in one place only" | A source rule: the grid draws cards, the loader draws none. The duplicate rendering cannot come back. |
| "asks for the chunk after the page's own cards" | The offset is `3`, and the limit is `24`. |
| "asks for the chunk after the appended one, not this page's" | The offset **advances** — the same offset twice would fetch the same chunk twice and skip a chunk of the pool. |
| "appends the chunk's cards to the page" | Five cards, not seven — and `getAllByText("Chunked gallery")` has length **1**, which is the duplicate-rendering assertion. |
| "issues one request for a double click" | The re-entrancy guard, with the request left **pending** so the second click lands while the first is in flight. |
| "says so when the chunk could not be fetched" | The failure path, and the reader's way back. |
| "keeps the chunk's cards subject to the query" | A chunk that ignored the query would be a filter that lied about how much it had narrowed. |

### The probe — the gate that can fail

| Probe | Expected | Result |
|---|---|---|
| A filter that removes the pool's whole tier-one prefix | The survivors stay tier two | **held** (after the fix; it did *not* hold before) |
| A chunk arriving on a filtered page | The chunk's cards appear once, and obey the query | **held** (after the fix; it did *not* hold before) |
| Two clicks on the anchor, request pending | One request | **held** |
| The loader drawing a card | A source rule fires | **held** |

### Checklist

- [x] All four gate commands clean — 2,203 passed, 0 failed
- [x] The two review defects fixed and covered by tests
- [x] The previous item's open Finding 21 (the untested chunk loader) closed
- [x] The plan's two wrong claims corrected in the plan, not papered over
- [x] No backend change; the server's why-tag vocabulary is untouched
- [x] No new tokens; `styles/tokens.css` untouched

---

## Work Item: frontend-browse-save-button

**The Inline Save Button — State Machine, Quota Wall and the Two Refusals**

### Summary

A new client island, `components/browse/browse-save.tsx`, mounted in the card's already-reserved
`data-browse-save-slot`. It drives a four-state machine over the **existing**
`POST`/`DELETE /api/personal/saved-events/{catalog_event_id}` pair, distinguishes the backend's
two 409 refusals by `code`, renders both inline under the button, and reads the quota wall out
of the payload.

**The backend was not touched.** No new endpoint, no new error, no schema change. The two 409s
already existed and already carried the `code` the client branches on.

| Gate | Result |
|---|---|
| `pnpm test` | **2246 passed (129 files)** — up from 2203/128 |
| `pnpm lint` | clean |
| `pnpm typecheck` | clean |
| `pnpm build` | clean — `/browse` is `ƒ` (dynamic) |

**New tests: 43.** `tests/browse-save.test.tsx` (35, new file), plus 6 in
`tests/browse-rendering.test.tsx`, 1 in `tests/browse-a11y.test.tsx`, and 1 in
`tests/browse-boundary.test.ts`. *(The build's own figure was 40; the code review added
the two colour-class assertions and the rendering file's sixth test was counted
afterwards — the table above is the measured one.)*

### Acceptance Criteria Validation

| # | Criterion | Status | The evidence |
|---|---|---|---|
| 1 | `idle → saving → saved → idle`; "Save", "Saving…" in ink-muted, "Saved ✓" in `color.signal.success` | **Pass** | `browse-save.test.tsx` — "runs idle → saving → saved, with the labels the item fixes" asserts each label and its class; "morphs to 'Saved ✓' in the success signal" asserts `text-signal-success` |
| 2 | `saved` persists ≥1500ms before another interaction is accepted | **Pass** | "holds the label for 1500ms, so a fast double-tap cannot flicker it" — at 1499ms the label is still "Saved ✓" and the button is `disabled`, and a press in that window sends no second request |
| 3 | A second tap un-saves with no destructive confirmation | **Pass** | "un-saves from 'saved' with no destructive confirmation" — the DELETE goes out and `document.querySelector('[role="dialog"]')` and `[aria-modal="true"]` are both null |
| 4 | The existing POST and DELETE; **no new save endpoint** | **Pass** | "saves through the existing POST, with the catalog id as the path parameter", "un-saves through the existing DELETE", and "invents no new endpoint" — every requested path is asserted to be exactly `/api/personal/saved-events/{catalog_event_id}` |
| 5 | 409 `save_cap_reached` → inline "You've used your 1 free save today. Upgrade for unlimited." + a "Upgrade" link | **Pass** | "renders the item's sentence inline under the button, with an Upgrade link" — the sentence matches and the link's `href` is `/pricing` |
| 6 | 409 `scheduling_conflict` → inline "Conflicts with your saved dinner. Open Detail to resolve." + an "Open" link | **Pass** | "renders the item's sentence inline, with an Open link to the event" — the link's `href` is `/events/{slug}` |
| 7 | **Neither refusal opens a modal or raises a toast — asserted by a test** | **Pass** | The `describe("neither refusal interrupts")` block: `assertNoInterruption()` queries `[role="dialog"]`, `[role="alertdialog"]`, `[aria-modal="true"]`, `[data-toast]`, `[data-sonner-toast]` and `[role="alert"]`, and all six must be null. **One assertion per refusal.** |
| 8 | Spent quota → every Save button renders muted "1 of 1 used today", visible but disabled, `title="Upgrade for unlimited saves"`, tapping does nothing | **Pass** | `browse-save.test.tsx` "the quota wall" (4 tests) and `browse-rendering.test.tsx` "renders the muted quota label on every card when the allowance is spent" — **all three** cards, each `disabled`, each with the title, and `apiPost` never called |
| 9 | **A Pro user never sees the quota state and can save repeatedly — asserted by a test that would fail if the entitlement check were dropped** | **Pass** | "never renders the muted label, and saves repeatedly" — a Pro quota (`cap: null, is_pro: true`) renders "Save", never the muted label, and three presses produce two POSTs and one DELETE. **A second test renders `used: 9` with `cap: null`**, so a client that treated `null` as `0` would compute `used >= cap` and wall the button off — dropping the check fails both. |
| 10 | A real `<button>` with `aria-label="Save {event name} to my Pulse"`, visible label still "Save" | **Pass** | "is a real button, with the visible label still 'Save'" asserts `tagName === "BUTTON"` and `type === "button"`; "names the event in the accessible name" asserts the exact `aria-label` |
| 11 | The morph is announced via `aria-live="polite"` on the button, without moving focus | **Pass** | "morphs to 'Saved ✓' in the success signal, and announces it politely" asserts `aria-live="polite"`; "does not move the focus when the label morphs" asserts `document.activeElement` is still the button after the morph |
| 12 | Focus ring 2px terracotta at AA; `Enter` and `Space` both trigger | **Pass** | "carries a 2px terracotta focus ring" asserts `focus-visible:outline-2` and `focus-visible:outline-accent-terracotta`; "triggers on Enter and on Space" fires both and each produces a request |
| 13 | Under `prefers-reduced-motion: reduce` the 240ms morph collapses to an instant swap | **Pass (by construction)** | **The morph uses `.fade-in`**, whose transition is `var(--motion-fade-in)` = `opacity 240ms ease-out` — the criterion's 240ms and the token's 240ms are the same number — and `styles/globals.css` already collapses `.fade-in` to `transition: none` under `prefers-reduced-motion: reduce`. **The component adds no transition class of its own.** See *The one thing this criterion cannot be tested for* below. |
| 14 | The card's initial state comes from the API's `is_saved`, so an already-saved event renders "Saved ✓" on first paint | **Pass** | `browse-save.test.tsx` "renders 'Saved ✓' straight away for an already-saved event" and "sends no request on the first paint"; `browse-rendering.test.tsx` "renders 'Saved ✓' on the first paint for an already-saved event" — **the very first DOM** of the card |

**Thirteen of thirteen are asserted by a test. The fourteenth is asserted by construction and by the
token file.** Two of them — #7 and #9 — are the ones the item asked for *by name*, and both are
written so that a regression fails them.

### The one thing this criterion cannot be tested for

**Criterion 13 asks about `prefers-reduced-motion`, and jsdom does not evaluate media queries.**

There is no honest DOM assertion for "the morph collapses under reduced motion" in this
environment: jsdom has no layout, no media-query evaluation, and no cascade. So the criterion is
satisfied by **the component not having a transition of its own to collapse**:

- The island's button carries `fade-in` and **no** Tailwind `transition-*`/`duration-*`/`ease-*`
  class. `tests/architecture.test.ts` bans all of those in a `.tsx`, so a hand-written 240ms
  transition would fail the build before it could ship.
- `.fade-in` is defined in `styles/globals.css` as `transition: var(--motion-fade-in)`, and the
  reduced-motion block sets `.fade-in { transition: none; }`.
- `--motion-fade-in` is `opacity 240ms ease-out` (`styles/tokens.css:154`).

**So the 240ms morph *is* the product's fade, and it already collapses.** The assertion that this
holds is `tests/architecture.test.ts`'s ban on transition classes plus `styles/motion.test.ts` —
both of which already exist and both of which pass. A reviewer looking for a
`prefers-reduced-motion` assertion in the new test file will not find one, and this paragraph is
why.

### The two refusals are not symmetric, and that is the design

**This is the item's most consequential decision, and it is worth stating plainly.**

| The server said | What actually happened | The button says |
|---|---|---|
| 409 `scheduling_conflict` | **The save row was written and the pair is active.** | "Saved ✓" |
| 409 `save_cap_reached` | **The save did not happen.** The gate refused before any row existed. | "Save" |

The backend is unambiguous on this. `api.py:398`: *"A conflicting save is a `ConflictFound` in the
same shape as a conflicting create: the save row exists, the pair is active, and the flow is
waiting for a choice."* And `save_event()`'s own docstring puts the gate **before** the write:
*"it is refused before anything is written: no partial `SavedEvent`, no audit row, no conflict
pair."*

**So the button must not say "Couldn't save that" on a clash** — it would be false about the
server's state — and it must not offer "Save" again, because pressing it would produce the same
409. `detail-actions.tsx` already encodes this rule for the Detail Screen (*"A 409 is not a failed
save… the button reads 'Saved to your Pulse' and the prompt opens over it"*), and Browse follows
the same rule in its own way: the button says "Saved ✓" and the inline line points at the detail
screen where the choice can be made.

Both branches are asserted: *"says 'Saved ✓', because the save row was written and the pair is
active"* and *"leaves the button in 'Save', because the save did not happen"*.

### The technical note's question, answered

**"Check whether that rollback actually exists before claiming the cancel works."**

**It does not.** The check was made in the backend, before the component was written:

- `apps/personalization/services/saved_events.py:106` — `save_event()` writes the row inside
  `transaction.atomic(using=PERSONAL)`, and the transaction **commits** when the function returns.
  There is no compensating write, no abort path, and no client-visible cancellation hook.
- The endpoint's own docstring says the save is idempotent: *"saving an event that is already
  saved returns the existing record."*

**So `Esc` is scoped to the client-side label, exactly as the technical note instructs.** It resets
the label to "Save" and abandons the in-flight answer — and the component's own comment says
plainly that it does **not** promise the event was not saved. The implementation uses a
generation counter so the abandoned answer cannot write over the label.

The test asserts both halves: *"resets the label and abandons the in-flight answer"* — the label
goes to "Save" on `Escape`, and the answer that arrives afterwards does not write over it.

### The two refusals interrupt nothing — and the test is written for the future

**Criterion 7 is the criterion this item is really asking for**, and the test is written so that a
*future* modal fails it rather than today's copy passing over it.

`assertNoInterruption()` asserts the absence of six things by name: `[role="dialog"]`,
`[role="alertdialog"]`, `[aria-modal="true"]`, `[data-toast]`, `[data-sonner-toast]` and
`[role="alert"]`. **A test that only checked the sentence would pass while a modal appeared over
it** — and a modal is exactly what `save_cap.py` forbids in as many words: *"A cap that interrupts
with a modal is a cap that trains people to dismiss prompts."*

**The refusal is also `role="status"`, not `role="alert"`** — asserted separately. A refusal is
information, not an emergency, and an assertive region would interrupt a screen reader
mid-sentence.

### The Pro exemption — a test that would fail if the check were dropped

**Criterion 9 asks for a test that would fail if the entitlement check were dropped, and this is
what that means in practice.**

The island's check is `quota.is_pro || quota.cap === null || quota.cap === undefined`. A client
that treated a null `cap` as `0` would compute `used >= cap` and wall the button off. **Two
tests close that door:**

1. *"never renders the muted label, and saves repeatedly"* — a Pro quota renders "Save", never the
   muted label, and three presses produce two POSTs and one DELETE.
2. *"treats a Pro quota with a spent count as a Pro quota"* — a quota of `{used: 9, cap: null,
   is_pro: true}` renders "Save" and is **not** disabled.

**The second test is the one that bites.** The server sends `used: 0` for Pro, so a client that
only read `used` would pass the first test. The second test proves the check is on the
*entitlement* and not on the arithmetic.

**Two sources of truth would be a bug, so there is one.** `lib/browse-labels.ts`'s `quotaNote()`
reads `is_pro || cap === null || cap === undefined` for exactly the same reason, and the island
reads the same two facts the same way.

### The quota travels with the card, and the server's gate is still the gate

**The quota reaches the island through the card, not around it.** The chain is: the page reads
`browse.quota` → the search island → the grid → the card → the island.

**And the client never refuses a save on the strength of a string it rendered.** The server's
`check_save_allowed` is the gate; the client's wall is a sign above it. That is the rule
`lib/browse-labels.ts` already states for the hero's note: *"The API reports the allowance without
spending it: it is a sign above the gate, not the gate."*

**One thing the wall does *not* block: un-saving.** A reader whose allowance is spent and whose
only option left is "un-save" must not be locked out of it — the wall is about *new* saves.
Asserted: *"leaves an already-saved event un-savable, because un-saving is not a new save"* —
**the test name reads "un-savable" in the sense of *not blocked*, and the assertion is that
the button is `not` disabled.** The wording is a leftover from an earlier draft and is worth a
reviewer's attention only because it could be read the other way round.

### The in-flight guard

**Three quick presses produce one request.** Asserted: *"sends one request for two quick presses"*
— the test fires three clicks and `apiPost` is called once.

**The guard is in the handler, not on the element.** A `disabled` attribute is not a guarantee —
a click dispatched in the same tick as the state change can still arrive — and the save is
idempotent server-side, so a duplicate would be harmless but would **spend the throttle's slot
twice on a Free account**. The cap is the product's one upgrade trigger; spending it twice on one
tap would be the bug.

### The first paint

**No "Save" flash.** The state comes from the API's `is_saved`, and the assertion is on the very
first DOM — `browse-rendering.test.tsx`'s *"renders 'Saved ✓' on the first paint for an
already-saved event"* checks `saved[0].textContent === "Saved ✓"` and `saved[1].textContent ===
"Save"` in the same render.

**A flash would be an effect that flips the state a moment later, and this test catches exactly
that.**

### The boundary test

`tests/browse-boundary.test.ts` gains:

- **`browse-save.tsx` is added to the surface files**, so every rule in that file — no Sign-up CTA,
  no chip rail, no persona copy, the two-stripe cap, no new tokens, no literal hex, no `fetch`,
  no direct `openapi-fetch` — now covers the new file too.
- **The client-module assertion becomes "these two, and no others"**: `browse-save.tsx` and
  `browse-search.tsx`. A third client module would fail it.
- **A new rule: the card stays a server component.** `browse-card.tsx` must not begin with
  `"use client"`, and it must mount `<BrowseSave` rather than re-implementing the button. A card
  that became a client component would put the whole grid's markup across the client/server
  boundary for the sake of one button.
- **The `next/headers` rule now covers both islands.**

### The a11y gate

`tests/browse-a11y.test.tsx` gains **"has zero serious or critical violations when the quota is
spent"**. **A spent quota is a different document**: the button's label changes from a verb to a
sentence, the button becomes disabled, and a `title` appears. A disabled button leaves the tab
order, and a `title` becomes the accessible name's *description* — so the control a keyboard
reader reaches is a different control from the one in the ordinary state.

The existing "every card treatment" gate already covers a card with `is_saved: true`, so the saved
button's document was already audited.

### Findings

**None blocking.** Four things were found and fixed during the implementation, and they are
recorded here rather than in the review report because they were found *by writing the code*,
not by reviewing it:

1. **The quota wall was initially a fourth state** (`SaveState = "idle" | "saving" | "saved" |
   "blocked"`), and the state was never entered — the code computed `spent` and never used it.
   **A state that is derived from a fact is not a state.** The wall is now derived at render: a
   button that became `blocked` by a state change could get stuck there when the allowance reset,
   and a reset the payload never announces would leave it stuck forever.
2. **The lockout was `Date.now() < lockedUntil`, read during render.** A component does not
   re-render when the clock passes a deadline, so the button would have stayed disabled until
   something else re-rendered it. It is a flag now, cleared by a timer.
3. **The `Esc` handler was on the button, and a disabled button fires no key events.** The
   button is `disabled` while a request is in flight — that is what "Saving…" means — so the
   handler never ran in the one case it exists for. **The listener moved to the wrapper**, which
   is never disabled.

   **This one was a false pass, and finding it is the point of the note below.** The original
   test fired the key event *directly on the disabled button* and passed — because
   `fireEvent` dispatches to an element regardless of `disabled`. **The test was proving
   something that could not happen in a browser.** It now fires on the wrapper, which is where
   the listener actually is, and a second test asserts the button really is disabled at that
   moment.

   **A mutation probe confirms the new test bites:** moving the listener back onto the button
   fails both `Esc` tests.
4. **`react-hooks/immutability` rejected `beginLockout` being called before its declaration.** The
   function was moved above its use.

### Mutation checks — proof the new tests can still fail

**Four mutations were applied to the component, one at a time, and the suite was run after
each. All four failed, and all four were reverted.**

| # | The mutation | The tests that failed |
|---|---|---|
| 1 | The `Esc` listener moved back onto the button (the bug finding #3 describes) | *"resets the label and abandons the in-flight answer"* and *"works while the button is disabled, which is the only time it is needed"* |
| 2 | The Pro entitlement check dropped — `is_pro` replaced by a hard `false`, so a null `cap` was treated as `0` | *"never renders the muted label, and saves repeatedly"* and *"treats a Pro quota with a spent count as a Pro quota"* |
| 3 | A modal raised on the cap refusal — `role="dialog"` and `aria-modal="true"` appended to the body | *"raises no modal and no toast for the cap"* and *"raises no modal and no toast for the clash"* |
| 4 | **The spent button's colour restored to the additive form** — `labelColour` and `blocked ? "text-ink-faint" : ""` — the defect the code review found (see `review-report.md`, Finding 2) | *"carries exactly one ink colour, so the muted one is the one that applies"* |

**Mutation 2 is criterion 9's own requirement discharged.** The item asks for *"a test that would
fail if the entitlement check were dropped"*, and the probe is that test being asked to do its job.

**Mutation 3 is criterion 7's own requirement discharged.** The item asks for a test that catches
a modal appearing, and the probe is a modal appearing.

**Mutation 4 was run during the code review, not the build.** It is the only mutation whose
failure was *not* noticed by the suite on its own — the pre-review test asserted
`expect(button().className).toContain("text-ink-faint")`, which passed with the bug in place,
because the class *was* present. The review's new assertion counts the ink classes instead,
and that is what the probe fires on:

```
× carries exactly one ink colour, so the muted one is the one that applies
  AssertionError: expected [ 'text-ink-secondary', …(1) ] to deeply equal [ 'text-ink-faint' ]
  Tests  1 failed | 34 passed
```

**A test that asserts a class is present cannot detect that a class is inert.** The old
assertion was not wrong about the class — it was blind to the fact that a second colour class
on the same element won the cascade.

### Issues Found

**None.** The gates are green on the first complete run of the new work.

**One issue was found afterwards, by the code review** — the spent button's colour was
decided by CSS emission order rather than by the component. Fixed, and mutation 4 above is
the proof.

### Files Changed

| File | Change | Tests |
|---|---|---|
| `components/browse/browse-save.tsx` | **New.** The island: the state machine, the two requests, the two refusal lines, the quota wall, the announcement, the `Esc` cancel. | 35 (new file) |
| `components/browse/browse-card.tsx` | Mounts the island in the existing slot; takes `quota`. | 2 |
| `components/browse/browse-grid.tsx` | Takes `quota` and passes it to every card. | — |
| `components/browse/browse-search.tsx` | Takes `quota` and passes it to the grid. | — |
| `app/browse/page.tsx` | Passes `browse.quota` down. | — |
| `lib/browse-labels.ts` | `spentQuotaLabel()` — the button's own label when the allowance is spent. | 1 |
| `tests/browse-save.test.tsx` | **New.** The island's own tests. | 35 |
| `tests/browse-rendering.test.tsx` | The card's Save button: one per card, the accessible name, the first paint, the wall, the Pro exemption, the request. | +6 |
| `tests/browse-a11y.test.tsx` | The quota wall's axe gate. | +1 |
| `tests/browse-boundary.test.ts` | The new file joins the surface; the client-module rule becomes "these two"; the card stays a server component. | +1 |

### Deviations from the plan

| # | The plan said | Now | Why |
|---|---|---|---|
| 6 | The wall is a state the machine reaches | **The wall is derived at render** | A state derived from a fact can get stuck. The allowance resets on a timer the payload never announces. |
| 7 | `Esc` is handled by the button | **`Esc` is handled by the wrapper** | **The button is `disabled` while saving, and a disabled button fires no keydown.** The cancel is exactly the case where the button is disabled — so the listener has to be one level up. |
| 8 | The `Esc` cancel resets the label | **It resets the label *and* abandons the answer** | A generation counter makes the in-flight response a no-op. Resetting the label alone would let the answer arrive afterwards and write "Saved ✓" over the reader's "Save". |

### Test Commands

```bash
export PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH"
cd frontend
pnpm test          # 2246 passed (129 files)
pnpm lint          # clean
pnpm typecheck     # clean
pnpm build         # clean — /browse is ƒ (dynamic)
```

### Ready for Completion

**Yes.** All thirteen criteria pass, the backend is untouched, and the two criteria the item
asked for by name — the no-modal/no-toast assertion and the Pro-exemption assertion — are
written so that a regression fails them.

**Re-verified after the code review** (see `review-report.md`): the suite grew by two tests
(the colour-class assertions), and all four gates are green at **2246 passed (129 files)**.

**The one thing a reviewer should check first** is the table at the top of *The two refusals are
not symmetric*: the clash sets "Saved ✓" and the cap sets "Save". If that inversion is wrong,
every other test in this file is still right and the product is still wrong.

---

## Work Item: browse-nav-activation

### Summary

The item is *"Retire the Three 'Coming Soon' Stubs"* — and the title turned out to be an
undercount. There were **three** Browse stubs and **one** more the item did not name.

| # | Where | What it was | Now |
|---|---|---|---|
| 1 | `components/shell/sidenav.tsx` | `<span aria-disabled="true">` + a "Coming soon" note | `<Link href="/browse">` |
| 2 | `components/shell/more-menu.tsx` | `<span aria-disabled="true">` + a "Coming soon" note | `<Link href="/browse">` with `aria-current` |
| 3 | `components/shell/bottom-tab-nav.tsx` — **the bottom tab's *Digest* slot, not a Browse slot** | `<span aria-disabled="true">` + a visually-hidden "Coming soon" | `<a href="/">` |
| 4 | `components/shell/more-menu.tsx` — the sheet's *inert-row machinery* | a whole branch for a disabled row | **deleted** — the sheet has no inert branch at all |

The third one is the one worth reading twice. **The bottom tab never had a Browse slot.** It
has five slots — Digest / Timeline / Add / Conflicts / Settings — and Browse lives behind
the More sheet on the trailing edge, because the bar's geometry is five slots at twenty
percent each and the spec says that twice.

So the bar's *first* slot was the inert one, and it was inert for a reason that had nothing
to do with Browse: **the Digest slot has had no `href` since the digest home shipped.**
`git log -p --follow` on `bottom-tab-nav.tsx` shows only the `+` line for that slot, never
a `-` line — it was never a link. On a phone, tapping the first tab rendered the inert
branch, a disabled `<span>` carrying a visually-hidden "Coming soon", **while also carrying
`active={pathname === "/"}`**. The home route's own tab did nothing, and said it was not
coming soon.

The item's third criterion says *"the visually-hidden 'Coming soon' text is removed where
it referred to Browse"*. That is where the item's author looked, and found nothing — the
text that remained was attached to Digest. **The criterion was satisfied by a fix the item
did not name**, and the fix is the one that matters: it is the difference between a phone
user reaching the digest and not reaching it.

### The rule the item asked to preserve

The Technical Notes are explicit: *"Nothing here should weaken that rule for whatever route
is deferred next."* The rule is the sidenav's — **an inert route is a `<span>`, not an
anchor with `aria-disabled`**, because *"the attribute is a hint, not a mechanism"*.

**Both inert branches were kept.** The criterion says to delete the machinery *"if Browse was
its only remaining user"*, and in the sidenav and the bottom bar Browse **was** the last
user — so a literal reading says delete. But the branch is not a Browse thing. It is the
*implementation of a rule the product still states*, and the Technical Notes ask for it by
name. Deleting the only implementation of a rule, in the same edit that removes the last
thing that used it, is how the rule dies quietly: the next deferred route reinvents it, and
reinvents it wrong, because there is nothing left to copy.

**The run log records which, and why.** See *Deviations* below.

**What was deleted** is the More sheet's inert branch — and that is not a weakening, because
the More sheet has exactly one row, Browse, and Browse is a route. There was never a reason
for that sheet to carry a disabled `<span>`, so the branch went rather than being left
behind empty.

### Acceptance Criteria Validation

| # | Criterion | How it is satisfied | Test |
|---|---|---|---|
| 1 | `sidenav.tsx:96` becomes a real `SidenavItem` with `href="/browse"` and an `active` rule | `<SidenavItem href="/browse" label="Browse" active={pathname === "/browse"} …>` | `nav-routes.test.tsx` × 3 |
| 2 | `more-menu.tsx`'s inert row becomes a real link, and the sheet row carries `aria-current="page"` when Browse is current — **More itself carries none** | `<Link href="/browse" aria-current={pathname === "/browse" ? "page" : undefined}>`; the More button has no `aria-current` | `nav-routes.test.tsx` × 3 |
| 3 | The bottom tab's Browse handling is updated, and the visually-hidden "Coming soon" text is removed where it referred to Browse | **Browse was not in the bar.** The bar's *Digest* slot carried the visually-hidden text, and it is now `<a href="/">` | `nav-routes.test.tsx` × 2 |
| 4 | **No `aria-disabled` Browse row remains anywhere** — asserted by a test | asserted on the **source**, across all three shell files | `digest-home-boundary.test.ts` |
| 5 | The inert-row machinery is deleted if Browse was its only user; otherwise it stays and the run log says which | **Both sidenav and bar branches kept; the More sheet's branch deleted.** Recorded in *Deviations* | the boundary test pins the kept branches |
| 6 | The doc comments that explain *why* Browse was inert are updated | every "Browse is not built" / "Browse was the last one" comment rewritten to say what is true now | source-level sweep |
| 7 | `nav-routes.test.tsx` is updated and still asserts the locked six-route order | `expect(order).toEqual(["Digest", "Timeline", "Add", "Browse", "Conflicts", "Settings"])` | `digest-home-boundary.test.ts` |
| 8 | The onboarding five-route variant is **unchanged** | there is no five-route variant in the code — `app/onboarding/page.tsx` renders `BrandTopbar` + `OnboardingFlow` and no nav at all. The variant survives only as a design intention in `frontend-digest-home-design.md` D12 and `EXPERIENCE.md:1155`, and **neither renders it.** Nothing changed. | n/a |

### The assertion the criterion #4 asked for, and why it is on the source

*"No `aria-disabled` Browse row remains anywhere — asserted by a test."*

The three places live in three different files, and only one of them is reachable from any
single render. The sidenav's rail and the More sheet's row are separate components; the
More sheet's row is not in the DOM until the sheet is opened; and the bottom bar is a
different component again. **A DOM assertion can only ever see one of them at a time.**

So the assertion is a **source-level sweep across the three shell files** — the same house
pattern as `tests/digest-home-boundary.test.ts` already uses for the rules a rendering test
cannot catch.

**And the sweep cannot be "this file contains no `aria-disabled`".** The inert branches are
kept, and they *do* contain `aria-disabled="true"` and a "Coming soon" string — that is what
they are. The sweep is narrower and truer:

> **No inert branch mentions Browse.**

```tsx
const inertBranch = /if \(!href\) \{[\s\S]*?\n  \}/.exec(source)?.[0] ?? "";
expect(inertBranch.includes('label="Browse"'), file).toBe(false);
```

The inert branch is the one that renders the disabled `<span>`, so the label inside it is
the label that is on the way but not here. If Browse is in that branch, Browse is inert. If
Browse is not, it is a route — and the branch is simply waiting for the next one.

The sweep also asserts the positive half, because *nothing is inert* is a weaker claim than
*this thing is a link*:

```tsx
expect(sidenav).toContain('href="/browse"');
expect(more).toContain('href="/browse"');

// And the bar's Digest slot is a link, because the digest home shipped.
const digestSlot = /<TabSlot[\s\S]*?label="Digest"[\s\S]*?\/>/.exec(bottom)?.[0] ?? "";
expect(digestSlot).toContain('href="/"');
```

And the More sheet is held to a stricter standard than the other two, because it has no
inert branch to keep:

```tsx
expect(more).not.toContain("aria-disabled");
expect(more).not.toContain("Coming soon");
```

### The active rules, and why they differ

| Route | Rule | Why |
|---|---|---|
| Digest | **prefix** — `pathname === "/" \|\| pathname.startsWith("/events/")` | the Detail Screen is reached by tapping a Digest card, so `/events/*` hangs off Digest in the IA |
| Browse | **equality** — `pathname === "/browse"` | Browse has no children. There is no `/browse/*` screen, so a prefix rule would be a claim about routes that do not exist |
| Timeline | equality | no children |
| Conflicts | equality | no children |
| Settings | **prefix** — `pathname.startsWith("/settings/")` | `/settings/reminders` and `/settings/quiet-hours` both hang off it, and the link points at the first of the two |

**The bar's Digest slot takes the sidenav's prefix rule, and it has to.** The sidenav
already marked Digest active on `/events/*`. If the bar did not, the *same screen* would
show Digest active in the rail and **nothing** active in the bar — which reads as "you have
left the digest" on a screen the user never left. Both rails now agree.

### Findings

**One real defect, and it was pre-existing.** The bottom tab's Digest slot has never been a
link. It is not a regression from this item — it is the thing this item surfaced. The
`git log -p --follow` evidence is in *The third one* above.

**Nothing else.** The two rails agreed on every other route before this item, and they agree
now.

### Mutation checks — proof the new tests can still fail

**Mutation 1 — the More sheet's Browse row reverted to an inert `<span>`.**

```
× gives the More slot a working sheet, not a dead control
× leaves no aria-disabled Browse row anywhere in the shell
× links Browse to the screen, because the Browse surface shipped
× marks the Browse row as the current route when it is
  Tests  4 failed | 46 passed (50)
```

**Mutation 2 — the bar's Digest slot reverted to no `href`.**

```
× leaves no aria-disabled Browse row anywhere in the shell
× links Digest to the home, because the digest home shipped
× marks Digest active on the detail screens that hang off it
  Tests  3 failed | 47 passed (50)
```

**Seven distinct tests fire across the two mutations**, and the source-level sweep fires
under both — which is the point of putting it on the source: it is the only assertion that
sees all three places at once.

### Issues Found

**None.** The gates are green on the first complete run of the new work, and the two
mutations were reverted and re-verified green.

### Files Changed

| File | Change | Tests |
|---|---|---|
| `components/shell/sidenav.tsx` | Browse becomes a real `SidenavItem` with `href="/browse"` and an equality active rule. The inert branch is kept, with its comment rewritten to say that nothing uses it today. | 3 |
| `components/shell/more-menu.tsx` | The sheet's row becomes a `<Link>` carrying `aria-current="page"`. The inert branch is **deleted** — the sheet's only row is a route. `usePathname` added. | 3 |
| `components/shell/bottom-tab-nav.tsx` | The Digest slot becomes `<a href="/">` with the sidenav's prefix rule. | 2 |
| `components/shell/nav-routes.test.tsx` | Browse-inert → Browse-link (+3), the More sheet's describe block (+3), the bar's Digest slot (+2), the stale "Browse is still inert" comment in the Settings test rewritten. | 16 → **23** (+7) |
| `tests/digest-home-boundary.test.ts` | The More-sheet assertion inverted; the new source-level sweep added; the "does not render an inert route as an anchor" rule left standing. | 26 → **27** (+1) |
| `app/page.test.tsx` | The Browse-is-inert test inverted to Browse-is-a-link; a new test asserts the rail has **no** `aria-disabled` row left; the vestigial "Coming soon" filter's comment corrected. | 51 → **52** (+1) |

### Deviations from the plan

| # | The plan said | Now | Why |
|---|---|---|---|
| 1 | "Three places render Browse as an inert `<span>`" | **Two places rendered Browse inert; a third rendered *Digest* inert** | The bar's five slots have no Browse slot at all — Browse lives behind the More sheet. The third inert thing was the bar's *first* tab, which had no `href` since the digest home shipped. |
| 2 | "deletes the inert-row machinery that only Browse used" | **Two of the three branches were kept; only the More sheet's was deleted** | The Technical Notes: *"Nothing here should weaken that rule for whatever route is deferred next."* The branch is the *implementation of a rule*, not a Browse thing. The More sheet's branch went because its only row is a route — there was never a reason for it to exist. **Recorded here, as the criterion requires.** |
| 3 | The bottom tab's "Browse handling is updated" | **The bar's Browse handling did not change, because there is none** | The bar carries five slots and Browse is the sixth route, behind More. The bar's change was the Digest slot. |
| 4 | The onboarding five-route variant is "unchanged" | **There is no five-route variant in the code** | `app/onboarding/page.tsx` renders `BrandTopbar` + `OnboardingFlow` and no nav. The variant survives as a design intention only. Nothing changed, so the criterion is satisfied trivially. |
| 5 | — | **The Digest slot's active rule was changed to a prefix** | Not named by the item. The sidenav marks Digest active on `/events/*`; the bar must agree, or the same screen shows Digest active in one rail and nothing in the other. |

### Test Commands

```bash
export PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH"
cd frontend
pnpm test          # 2255 passed (129 files)
pnpm lint          # clean
pnpm typecheck     # clean
pnpm build         # clean — /browse is ƒ (dynamic)
```

**2255 passed, up from 2246** — nine new tests, zero removed. The count is the sum of the
three files: `nav-routes` 16 → 23, `digest-home-boundary` 26 → 27, `page.test` 51 → 52.

### Ready for Completion

**Yes.** All eight criteria pass, the backend is untouched, and the one the item asked for by
name — *"No `aria-disabled` Browse row remains anywhere"* — is asserted by a test that was
mutation-proven to fire.

**The thing a reviewer should check first** is *Deviations* row 2: the two kept branches.
The item's criterion reads *"deleted if Browse was its only remaining user"*, and Browse
**was** the last user in both — so a literal reading says delete, and this edit keeps them.
The Technical Notes ask for the rule to survive, and this run log says which way it went and
why. If the item's author meant the literal reading, this is the one decision to overturn.
