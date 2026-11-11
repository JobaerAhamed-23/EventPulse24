---
run: run-eventpulse24-026
work_item: review-queue-model
intent: trust-loop
generated: 2026-11-10T14:40:00Z
status: passed (16 pre-existing, unrelated failures recorded below)
---

# Test Report: Something to queue onto — the ReviewItem and the editorial group

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit and database (new files) | 70 | 0 | 0 | `review_queue.py` 99% |
| Integration (registries, seed, e2e grant) | 236 | 0 | 0 | — |
| **Targeted total** | **306** | **0** | **0** | — |
| Full backend suite | 5764 | 16 | 0 | — |

**The 16 full-suite failures existed before this item and are unrelated.** Each one was run on a clean `HEAD` (`git stash -u`) and fails identically there:

- `tests/e2e/test_timeline_and_conflict_proof.py`: 9 tests
- `tests/e2e/test_save_race.py`: 4 tests
- `tests/e2e/test_personal_events_and_saved_catalog.py::test_the_whole_personal_event_and_save_flow_holds_together`
- `tests/delivery/test_reminder_plan_api.py::test_a_saved_plan_and_its_sends_move_together`
- `tests/ingestion/test_url_feed_read.py::test_a_city_lastmod_is_the_latest_of_its_events`

**Cause:** their fixtures hard-code event starts such as `datetime(2026, 11, 6, 3, 30, tzinfo=UTC)` (`tests/e2e/test_save_race.py:42`), which is now in the past (today is 2026-11-10). Saving a past event answers 404 ("We couldn't find that event."), the 2d and 5d reminder slots have already passed, and the sitemap `lastmod` falls back to *now*. This is a test-clock defect, not a product defect. It is recorded as a follow-up and is **not fixed inside this item**.

## Acceptance Criteria Validation

- ✅ **`ReviewItem` in `apps/ingestion/models.py`, schema `catalog`, written only by `ingestion`.** The model is there. `tests/wall/test_schema_placement.py` places it in catalog, and `tests/architecture/test_write_ownership.py` gives `ingestion` as its owner.
- ✅ **The reason/target `CheckConstraint`.** `review_item_target_ck` refuses an event item with a source as well, an event item with no target, and a source item with an event. The tests assert the constraint by name.
- ✅ **Priority and SLA.** `due_at = raised + 24h` is set on a report's first raise and never moved by a bump. `review_item_due_ck` refuses a report with no deadline and a deadline on any other reason. `REVIEW_SLA_USER_REPORTED` lives in `shared/constants.py`.
- ✅ **No user identity across the wall.** The row has no user column. A report-raised audit row is `system/event_report` with `actor_id IS NULL`. *Added during review:* the command now **refuses** a report raised as a user actor, so D4 is enforced rather than trusted.
- ✅ **At most one open item per (target, reason).** Two partial unique constraints are tested for both target kinds. A bump increments the right tally. A second reason on the same event is allowed, and so is a new item after a close.
- ✅ **Lifecycle and the closed-item guard.** `review_item_resolution_ck` covers D6 (a)–(d), each case tested. `catalog.guard_review_item` refuses re-opening, refuses a bump of a resolved row, refuses changes to the fixed columns, and refuses delete except inside a retention purge.
- ✅ **`raise_review_item` is idempotent under concurrency and audited.** The two-thread barrier test gives one row with `report_count == 2` and two audit rows. A deterministic seam test covers an item closed between the refused insert and the lock. The item and its audit row roll back with the caller's transaction.
- ✅ **The editorial group's grants**, ⚠️ **deviating from the AC as approved in design D9.** They are set by `seed_local_stack.EDITORIAL_GRANTS`, not a data migration, because `auth` lives in `personal` and ingestion migrations run only on `catalog`. The group holds exactly 14 codenames: `change_reviewitem` and `view_reviewitem` are present, and `add_reviewitem` and `delete_reviewitem` are not.
- ✅ **A retention category is declared.** `SOURCE_REGISTRY` is asserted in two places.
- ✅ **The tests named in the AC** are all present. See the next section.

## Tests Written

### Unit Tests

- `backend/tests/ingestion/test_review_item_model.py` has 47 tests. They cover: each constraint by name; every D6 resolution shape; the trigger's immutability, fixed columns and delete rules; `FIXED_FIELDS` parity with the trigger body; every category having one tally column; `report_count`; and retention.
- `backend/tests/ingestion/test_review_queue.py` has 22 tests. They cover: raise; bump; the deadline staying put; a raise after a close; the closed-row race seam; audit actions and details; D4 anonymity; the D4 refusal; each validation refusal writing nothing; and rollback with the caller.

### Integration Tests

- `backend/tests/ingestion/test_review_queue_concurrency.py`: two committed connections racing through a barrier.
- `backend/tests/e2e/test_end_to_end.py` (modified): the grant set has 14 codenames, with no add or delete on `reviewitem`.
- `backend/tests/ingestion/test_models.py`, `tests/wall/test_schema_placement.py` and `tests/architecture/test_write_ownership.py` (modified): `ReviewItem` is registered in each model registry.

## Showing the tests can fail (mutation probes)

| Probe | Expected to fail | Result |
|-------|------------------|--------|
| Remove the trigger's `OLD.status = 'resolved'` block and its `raised_at` comparison | Re-open, resolved bump, `raised_at` change, parity | **Exactly those 4 failed**, 42 passed. Restored. |
| Replace the savepoint insert and recover with a naive check-then-insert (no recovery) | Only the concurrency test; sequential tests can't see it | **Only `test_two_reports_racing…` failed**, with the expected `IntegrityError` on `review_item_open_event_reason_uq`. Restored. |
| Extend `EDITORIAL_GRANTS` before updating the e2e expectation | The grant-set test | **Failed** ("Extra items in the left set"). Then updated. |
| Disable the D4 user-actor guard | The new refusal test | **Exactly that test failed**, 21 passed. Restored. |

## Test Commands

```bash
# The item's tests
cd backend && uv run pytest tests/ingestion/test_review_item_model.py tests/ingestion/test_review_queue.py tests/ingestion/test_review_queue_concurrency.py

# The full suite and the checks
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run lint-imports \
  && uv run python manage.py check && uv run python manage.py makemigrations --check --dry-run

# Coverage of the new command
cd backend && uv run coverage run -m pytest tests/ingestion/test_review_*.py && uv run coverage report --include=apps/ingestion/services/review_queue.py -m
```

## Coverage Details

| Module | Statements | Branches | Functions | Lines |
|--------|------------|----------|-----------|-------|
| `apps/ingestion/services/review_queue.py` | 99% | — | 100% | 99% (line 129 uncovered) |

Line 129 re-raises an `IntegrityError` that is *not* the open-unique collision. It can't be reached through the public API today: `_checked` refuses every target and reason mismatch before the insert, and the FK constraints are deferred to commit, so they don't fire inside the savepoint. It is kept as a guard against a future constraint being swallowed.

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| 16 date-dependent test failures already on `HEAD` (fixtures hard-code 2026-11-06 starts) | Medium (CI red on `main` from 2026-11-06) | Pre-existing; recorded as a follow-up, not fixed in this item |
| The editorial group in production relies on a command named "local" (D9) | Low | A known gap from the design; a `sync_editorial_group` command is offered as a follow-up |
| Local DB had `ingestion.0007` unapplied | Info | Applied with `make migrate` along with 0008 |

## Ready for Completion

- [x] All tests passing for this item. The 16 full-suite failures existed before it and are unrelated.
- [x] Coverage target met (80% overall gate; the new command is at 99%)
- [x] All acceptance criteria validated (D9's group mechanism is a deviation approved at checkpoint 1)
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-026*

---

## Work Item: event-rejection-state

### Test Results

| Suite | File | Tests |
|---|---|---|
| Trigger (raw SQL, below the ORM) | `tests/ingestion/test_rejected_triggers.py` | 10 |
| Commands | `tests/ingestion/test_editorial_state.py` | 15 |
| Read absence | `tests/ingestion/test_rejected_absence.py` | 9 |
| Ingestion re-entry | `tests/ingestion/test_rejected_reentry.py` | 6 |
| Propagation to savers | `tests/worker/test_propagation_rejection.py` | 10 |
| End-to-end proof | `tests/e2e/test_rejection_proof.py` | 3 |
| Map parity (extended) | `tests/worker/test_propagation_tasks.py` | +1 new, 2 rewritten |
| **New/changed total** | | **54** |

- **Passed: 5829 · Failed: 0 (of this work item) · Skipped: 0**
- Full backend suite: **5829 passed, 16 failed** — all 16 failures **pre-existing**, see below.
- Coverage: **99% overall** (gate 80%) · **`domain/` 100%** (gate 100%) · `editorial_state.py` **100%**

### Pre-existing failures (not caused by this work item)

Sixteen tests fail on this branch. They were **verified against clean `HEAD` with this work
item's changes stashed, and the identical sixteen fail there**, so they are inherited, not
introduced:

```
tests/e2e/test_save_race.py                      (4)
tests/e2e/test_timeline_and_conflict_proof.py    (9)
tests/e2e/test_personal_events_and_saved_catalog.py (1)
tests/delivery/test_reminder_plan_api.py         (1)
tests/ingestion/test_url_feed_read.py            (1)
```

They share a signature: each seeds the fixture sources, ingests them, and then reads the
catalog bounded by the **wall clock**. The public read drops an event that has already
started, so the saves 404 and the `lastmod` assertions compare against `now`. The fixture
feeds' dates have been overtaken by the calendar. **This is a latent time bomb in the
fixtures, not a regression**, and it is logged as carried work rather than fixed here —
fixing it is not in this work item's scope and would have hidden whether this item broke
anything.

### Mutation Probes

`tests/ingestion/mutation_probe_rejection.py` — **11 probes, all 11 caught.**

Each plants one real bug and asserts the suite fails. The two that matter most are 3 and 4,
because they falsify the design's central claim — that a reject needs *two* writes:

| # | Planted bug | Caught by |
|---|---|---|
| 1 | The catalog read's publication filter dropped | absence, e2e |
| 2 | The public page serves a rejected event by slug | absence, e2e |
| 3 | **The reject writes no state change** (hides the event, reminders keep firing) | propagation, e2e |
| 4 | **`delisted` keeps the sends** instead of cancelling | propagation, e2e |
| 5 | The notice suppression dropped (a reject emails the user a lie) | propagation, e2e |
| 6 | The ingestion freeze dropped (next poll republishes it) | re-entry |
| 7 | The freeze applied on the lifecycle path but not the detail path | re-entry |
| 8 | The version is not bumped (no version for the outbox row) | commands, propagation, e2e |
| 9 | The reject is no longer idempotent | commands |
| 10 | A job may reject or reinstate (AD-14 attribution lost) | commands |
| 11 | `delisted` closes conflict pairs (the AD-21 defect walked into) | propagation, maps |

### Acceptance Criteria Validation

| Criterion | Status | Evidence |
|---|---|---|
| The design picks one representation and records why; states what a saved user sees | ✅ | `event-rejection-state-design.md` D1–D10. A saved user sees nothing: card reads "event no longer available", reminders stop, no email. D4 records why silence beats both "cancelled" (false for a duplicate) and invented copy. |
| Never deleted; absent from every public read; one test per read, each failing when the filter is removed | ✅ | 9 absence tests across catalog list/detail/batch, public URL, digest candidates, URL feed, Event Fit; probes 1–2 prove they fail when a filter is dropped. |
| Cannot re-enter by ingestion; design states whether a re-send re-queues | ✅ | `test_rejected_reentry.py` (6). D9: a re-send raises **no** new review item; probes 6–7. |
| Reversible only by an editor, through a command | ✅ | `reinstate_event`; system actor refused (AD-14); `test_ingestion_never_writes_a_relisted_change`; probe 10. |
| Saved users handled as the design decides, proved end-to-end, including the AD-17/AD-21 defect interaction | ✅ | `test_rejection_proof.py`: reminders cancelled, zero emails sent through the real sweep + memory adapter, conflict pair survives a reject→reinstate round trip. |
| Migration and trigger changes come with tests for legal and illegal transitions | ✅ | 10 trigger tests: 4 legal transitions, the same 4 refused without a bump, plus the `in_review → published` regression guard and the not-terminal check. |
| Exhaustive lifecycle maps: existing tests extended, not bypassed | ✅ | The two map tests are **narrowed to their stated invariant** ("an event that moved") and scoped to classified kinds; a third test makes the exemption structural, failing if any `ChangeKind` is ever mapped NONE + CANCEL. |

### Gates

| Gate | Result |
|---|---|
| `ruff check` | ✅ All checks passed |
| `ruff format --check` | ✅ 552 files already formatted |
| `lint-imports` | ✅ 19 contracts kept, 0 broken |
| `manage.py check` (AD-15 retention) | ✅ no issues |
| `makemigrations --check --dry-run` | ✅ No changes detected |
| Coverage 80% overall / 100% `domain/` | ✅ 99% / 100% |
| OpenAPI client contract | ✅ `tests/api/test_contract.py` passes — **no API change in this item** |
| Frontend lint / typecheck | n/a — no frontend file changed |

---

## Work Item: reliability-score-domain

### Test Results

| Suite | File | Tests |
|---|---|---|
| Domain arithmetic | `tests/domain/test_reliability.py` | 42 |
| Constants pinned | `tests/shared/test_constants.py` | +6 |
| **New total** | | **48** |

- **Passed: 5879 · Failed: 0 (of this work item)**
- Coverage: **99% overall** (gate 80%) · **`domain/` 100%** (gate 100%) · `domain/reliability.py` **100%**
- Full suite: 16 failures, the **same pre-existing sixteen** documented under the previous
  work item. Unchanged in count and identity.

### Acceptance Criteria Validation

| Criterion | Status | Evidence |
|---|---|---|
| `domain/reliability.py` exposes `posterior_mean`, `reliability_score`, `should_escalate`, `is_spike` | ✅ | Plus `weekly_negative_rate` (D2's input) and `checked_count` / `checked_rate` |
| Two-decimal `Decimal` in [0, 1]; floats refused like `checked_confidence` | ✅ | `test_rates_refuse_floats`, `test_counts_refuse_floats`, plus the exhaustive range/quantize properties |
| **Resolve FR-16's min-N / floor tension and record it** | ✅ | **D1: the posterior moves, clamped at 0.32 below 30 observations.** Confirmed with the user 2026-11-10. Recorded in the module docstring, beside the constants, and in `test_the_new_source_floor_matches_the_posterior_after_five_or_six_failures`, which pins *where 0.32 comes from* (between 5 and 6 straight failures — not the n=29 floor of 0.13) |
| **Define "3× drop" exactly** | ✅ | **D2: a 3× rise in the smoothed week-over-week rate of negative observations**, not a ratio of scores. Confirmed with the user. `test_a_ratio_of_scores_could_not_have_fired` pins the arithmetic that forced the change |
| All six constants in `shared/constants.py`, pinned by `tests/shared/test_constants.py` | ✅ | α, β, min-N, floor, escalation line, spike multiplier — 6 new tests |
| a new source at 0.50 | ✅ | `test_reliability_score_of_a_new_source_is_the_prior_mean` |
| one negative not cratering the score | ✅ | `test_posterior_mean_one_negative_does_not_crater_the_score` (0.45, not 0.00) |
| the floor under 30 observations | ✅ | `test_reliability_score_is_floored_under_the_minimum` (n = 6, 10, 29) |
| the boundary at exactly 30 | ✅ | `test_reliability_score_floor_lifts_at_exactly_thirty` (0.32 → 0.13) |
| escalation at 0.29/0.30 with n = 29/30 | ✅ | Parametrised over all four corners, plus the exclusive-threshold test |
| spike at the threshold and just below | ✅ | `is_spike` at exactly 3× fires; 2.9× does not |
| float refusal | ✅ | Floats, `Decimal`s where `int` is wanted, **`bool`**, negatives, >2 decimals, out-of-range |
| property: score always in [0, 1]; monotone in negatives | ✅ | Exhaustive over n = 0..200 (`hypothesis` is not a dependency, so loops rather than a new package). Monotone in positives too, and the floor property across every split below 30 |

### Two extra invariants pinned beyond the AC

- `test_a_floored_new_source_can_never_escalate` — walks every n below 30 and asserts the
  clamp cannot suppress an escalation. The floor (0.32) sits above the escalation line
  (0.30), so it structurally cannot; this asserts it rather than trusting it.
- `test_a_ratio_of_scores_could_not_have_fired` — fails if a future change to the floor or
  the multiplier quietly revives the broken reading of spike detection.

### Gates

| Gate | Result |
|---|---|
| `ruff check` | ✅ All checks passed |
| `ruff format --check` | ✅ 554 files already formatted |
| `lint-imports` (incl. `domain-pure`) | ✅ 19 contracts kept, 0 broken |
| `manage.py check` | ✅ no issues |
| `makemigrations --check --dry-run` | ✅ No changes detected |
| Coverage 80% / 100% `domain/` | ✅ 99% / 100% |
| OpenAPI client contract | n/a — no API change |
| Frontend | n/a — no frontend file changed |

---

## Work Item: review-intake-and-backfill

### Test Results

| Suite | File | Tests |
|---|---|---|
| Intake, withdrawal, the in-transaction invariant | `tests/ingestion/test_review_intake.py` | 11 |
| Backfill and the command | `tests/ingestion/test_backfill_review_items.py` | 11 |
| **New total** | | **22** |

- **Passed: 5906 · Failed: 0 (of this work item)**
- Coverage: **99% overall** · **`domain/` 100%** · `review_intake.py` + `backfill_review_items.py` **100%**
- Full suite: the same **16 pre-existing failures**, unchanged in count and identity.

### Mutation Probes

`tests/ingestion/mutation_probe_trust_loop.py` (renamed from `mutation_probe_rejection.py` —
one probe file per intent). **16 probes, all 16 caught**: 1–11 from `event-rejection-state`,
12–16 new.

| # | Planted bug | Caught by |
|---|---|---|
| 12 | A new event in review gets no ticket — the stranding bug restored | intake |
| 13 | **The ticket is raised best-effort** (`try/except`), outside the write's failure path | intake |
| 14 | Re-gating out of review no longer withdraws the ticket | intake |
| 15 | A published-but-flagged event raises a ticket after all (D1 reversed) | intake |
| 16 | The backfill stops excluding already-ticketed events (idempotence lost) | backfill |

**Probe 13 is the one the AC asked for.** It is also where the plan was sharpened during
implementation: a rollback test alone would *not* have proved "same transaction", because a
raise deferred to `on_commit` also produces no item on a rollback. The invariant is instead
tested the other way round — **if the raise fails, the Event must not exist either** — which
is true only when the two share a transaction, and which probe 13 breaks.

### Acceptance Criteria Validation

| Criterion | Status | Evidence |
|---|---|---|
| Every path into `in_review` raises an item **in the same catalog transaction** | ✅ | Four call sites in `ingest_item`, beside the existing `_write_fit` calls. `test_an_event_is_not_written_at_all_if_its_ticket_cannot_be_raised` + probe 13 |
| The confidence-below-0.7 extraction gate wired through the same call; driven by a synthetic low-confidence `IncomingEvent` | ✅ | `test_a_low_extraction_confidence_event_gets_a_ticket` at `extraction_confidence = 0.60`. The sync keys off the **resulting publication status**, so FR-14's path needs no change here at all |
| Backfill, idempotent | ✅ | `backfill_review_items` command. Idempotent for two independent reasons — the query excludes ticketed events, and `raise_review_item` refuses to stack. 11 tests incl. batching, `--dry-run`, superseded/rejected/published exclusions |
| An event leaving `in_review` by a non-editorial route closes or orphans its item in a defined way | ✅ | **Withdrawn, system actor.** Re-gate-out and supersede both tested; the editorial routes are explicitly out of scope and `test_rejecting_an_in_review_event_leaves_its_item_open` pins the documented gap |
| **Settles the brief's open question on flagged events** | ✅ | **D1: they stay out of the queue.** Confirmed with the user. `test_a_flagged_event_gets_no_ticket` + probe 15 |
| the in-transaction invariant, via a probe | ✅ | Probe 13 |
| the backfill's idempotence | ✅ | `test_the_backfill_is_idempotent` + probe 16 |
| the low-extraction-confidence path | ✅ | Above |
| the flagged-event decision | ✅ | Above |

### Gates

| Gate | Result |
|---|---|
| `ruff check` / `ruff format --check` | ✅ 558 files formatted, all checks passed |
| `lint-imports` | ✅ 19 contracts kept, 0 broken |
| `manage.py check` / `makemigrations --check` | ✅ no issues / **no migration needed** |
| Coverage 80% / 100% `domain/` | ✅ 99% / 100% |
| OpenAPI contract / frontend | n/a — neither changed |

---

## Work Item: event-report-api

### Test Results

| Suite | File | Tests |
|---|---|---|
| Report service, throttle, outbox, AD-3 | `tests/personalization/test_event_reports.py` | 15 |
| Endpoint contract | `tests/personalization/test_event_report_api.py` | 14 |
| Category vocabulary + limits pinned | `tests/shared/test_constants.py` | +4 |
| Write ownership (AD-16) | `tests/architecture/test_write_ownership.py` | +1 entry |
| Tick cadence | `tests/worker/test_scheduling_tasks.py` | 5 parametrisations extended |
| **New total** | | **33** |

- **Passed: 5947 · Failed: 0 (of this work item)**
- Coverage: **99% overall** · **`domain/` 100%** · `event_reports.py` **100%**
- Full suite: **16 pre-existing failures**, back to the established set.

### Two of the project's own tests caught this work item mid-flight

Both were doing exactly their job, and both are recorded because they are the reason the
change is safe rather than merely finished:

1. **`test_write_ownership`** failed with *"tables with no owner in TABLE_OWNERS:
   ['personalization_eventreport']"*. AD-16 requires every table to have one owning app. The
   map was extended with `personalization` and the reason why.
2. **`test_tick_enqueues_scheduling_every_time_and_the_reconciler_every_5_minutes`** failed
   on all five parametrisations, because it enumerates the *exact* set of jobs the tick
   enqueues at each minute. Adding `reconcile_event_reports` had to be declared there. A test
   that merely asserted "the reconciler is among them" would have let a silently-dropped job
   through.

### Mutation Probes

`mutation_probe_trust_loop.py` — **21 probes, all 21 caught** (1–11 rejection, 12–16 intake,
17–21 new).

| # | Planted bug | Caught by |
|---|---|---|
| 17 | **The report is raised as the reporter** — their id reaches a `catalog` audit row every editor can read | service |
| 18 | The throttle is checked *after* the idempotence shortcut, so a repeat is free | service |
| 19 | `raised_at` is never stamped, so the reconciler raises it again (double counting) | service |
| 20 | The visibility check is dropped, so the endpoint can probe hidden events | contract |
| 21 | The response leaks queue state back to the client | contract |

### Acceptance Criteria Validation

| Criterion | Status | Evidence |
|---|---|---|
| `EventReport` in `personal`; user, event id by value, category, timestamp; four categories; **no free text**; retention declared | ✅ | `ACCOUNT_CONTENT`; `manage.py check` passes the AD-15 registry; a `CheckConstraint` pins the four |
| Session-scoped, CSRF-protected POST taking `{event_id, category}`; response gives only what the toast needs | ✅ | `CsrfClient` tests; `test_the_response_carries_nothing_but_the_toast` + probe 21 |
| **5 per user per day through the throttle port**, not hand-rolled; the sixth a distinct documented error | ✅ | `ports.registry.get_throttle_port`; 429 `rate_limited` with `retry_after_seconds`; deterministic via the adapter's injected clock |
| The plan defines what a repeat does; it must not inflate the count; a test pins it | ✅ | **D1:** unique on `(user, event, category)`; `test_the_same_user_reporting_twice_counts_once` and `test_two_users_reporting_the_same_thing_count_twice` |
| Each accepted report calls `raise_review_item` with the event and category, **never the user** | ✅ | Via `raise_user_report` (D3); `test_the_review_item_carries_no_user_identity` and `test_the_catalog_audit_row_carries_no_user_identity` + probe 17 |
| **Visibility never changes on a report** | ✅ | `test_a_reported_event_is_still_public` — list, candidates and detail |
| Unknown or non-visible events refused as the Detail read refuses them | ✅ | 404 for unknown, `in_review`, `rejected` and superseded; `test_an_in_review_event_is_not_found` asserts the body is **byte-identical** to an unknown id's + probe 20 |
| Stores the facts FR-16's "upheld" definition will need | ✅ | `(user, event, category, created_at)` per report; the anonymous per-category tally on the ReviewItem |
| **OpenAPI regenerated and `schema.ts` rebuilt in the same change (AD-19)** | ✅ | `make client`; +234 lines; regeneration verified **idempotent** (byte-identical on a second run); `tests/api/test_contract.py` passes |
| Contract tests: shape, each category, invalid category, rate limit, signed out, unknown/hidden event, AD-3 property | ✅ | All 14 contract tests, plus the two AD-3 property tests in the service suite |

### Gates

| Gate | Result |
|---|---|
| `ruff check` / `ruff format --check` | ✅ 562 files formatted, all checks passed |
| `lint-imports` | ✅ 19 contracts kept, 0 broken |
| `manage.py check` (AD-15) / `makemigrations --check` | ✅ no issues / no changes detected |
| Coverage 80% / 100% `domain/` | ✅ 99% / 100% |
| **OpenAPI client contract (AD-19)** | ✅ regenerated, idempotent, contract test green |
| **Frontend lint + typecheck** | ✅ eslint clean; `next typegen && tsc --noEmit` clean |

---

## Work Item: editorial-review-commands

### Test Results

| Suite | File | Tests |
|---|---|---|
| The four commands and every refusal | `tests/ingestion/test_editorial_review.py` | 30 |
| The editorial lock (D1), both halves | `tests/ingestion/test_editorial_lock.py` | 4 |
| The rewritten gap tests | `tests/ingestion/test_review_intake.py` | 2 rewritten |
| Model/retention/schema inventories | `test_models.py`, `test_schema_placement.py`, `test_write_ownership.py` | 4 extended |
| **New total** | | **40** |

- **Passed: 5988 · Failed: 0 (of this work item)**
- Coverage: **99% overall** · **`domain/` 100%** · `editorial_review.py` **100%**
- Full suite: back to the **16 pre-existing failures**.

### Four of the project's own tests caught this work item

Every one of them was an exhaustive inventory, and every one was right to fail:

1. `test_ingestion_has_the_eleven_designed_models` — now twelve, with `SourceObservation`
   and the reason it exists.
2. `test_ingestion_retention_categories` — AD-15 wants a category per model.
3. `test_catalog_schema_holds_only_catalog_tables` — the AD-3 wall's own inventory.
4. `test_write_ownership` — AD-16 wants an owning app per table.

A codebase where adding a model is silent is one where a model can land on the wrong side of
the schema wall unnoticed. All four were extended with the reasoning, not just the name.

### Mutation Probes

`mutation_probe_trust_loop.py` — **27 probes, all 27 caught** (22–27 new).

| # | Planted bug | Caught by |
|---|---|---|
| 22 | A verdict closes only the clicked item, not the event's others (D2 lost) | editorial |
| 23 | The stale-version guard is dropped — an editor overwrites an unseen update | editorial |
| 24 | A system actor may record a verdict (AD-14 lost) | editorial |
| 25 | No FR-16 observation is recorded, so the score has no input | editorial |
| 26 | A venue edit keeps the old fingerprint, so the venue silently never moves | editorial |
| 27 | **The content-hash skip is removed — the editorial lock disappears** | lock |

**Probe 27 is the one that makes D1 honest.** The lock is enforced by an *absence* — there is
no lock code — which is exactly the kind of rule a later tidy-up deletes without noticing.
The probe removes the short-circuit in `ingest_item` and the lock tests fail, so the absence
is now load-bearing and provably so.

### Acceptance Criteria Validation

| Criterion | Status | Evidence |
|---|---|---|
| `approve_review_item` publishes or confirms; closes `approved` | ✅ | Both paths tested; a reported event stays published |
| `edit_and_publish` corrects a bounded field set, then publishes; a lifecycle change bumps the version and appends an `EventStateChange` exactly like ingestion; closes `edited` | ✅ | Goes through `apply_lifecycle_change` itself — no parallel path. A title-only edit uses `apply_silent_update` and notifies nobody |
| `reject_review_item` applies `event-rejection-state`'s representation; closes `rejected` | ✅ | Calls `editorial_state.reject_event`; the `delisted` change appears on the outbox |
| `dismiss_source_item` closes without changing the source | ✅ | `test_dismissing_never_touches_the_source` compares **every column** before and after |
| Every command: editor actor required, attributed, audited, one catalog transaction | ✅ | 4 refusal tests + audit assertions + probe 24 |
| **Stale-safe** on both the item and the event version | ✅ | `ConflictError` with `item_already_resolved` / `event_version_stale` + probe 23 |
| **An FR-16 observation per resolution**, attributed to the owning source; the edit's shape agreed or deferred | ✅ | `SourceObservation`, one per item (unique constraint). **`edited` is its own kind and its sign is deferred** to `reliability-recompute-and-escalation` — stored as a fact, not a score, which is what the AC asked for |
| An editorial edit is not undone by the next poll; the plan states the rule and a test pins it | ✅ | **D1:** the content-hash skip *is* the rule. 4 tests + probe 27 |

### Gates

| Gate | Result |
|---|---|
| `ruff check` / `ruff format --check` | ✅ 566 files formatted, all checks passed |
| `lint-imports` | ✅ 19 contracts kept, 0 broken |
| `manage.py check` (AD-15) / `makemigrations --check` | ✅ no issues / no changes detected |
| Coverage 80% / 100% `domain/` | ✅ 99% / 100% |
| OpenAPI / frontend | n/a — no API or frontend change |

---

## Work Item: editorial-admin-queue

**Where an editor actually works — the review queue in Django admin** — medium, confirm mode.

### Test Results

| Suite | File | Tests |
|---|---|---|
| The queue in the admin, driven through the test client | `tests/editorial/test_admin_queue.py` | 26 |
| The access matrix, in the rule and through the admin | `tests/editorial/test_access.py` | 29 |
| **New total** | | **55** |

- **Passed: 55 · Failed: 0**
- Coverage: **99% overall** · `review_queue_read.py` **90%** · `editorial/services/review_queue.py` **94%**
- Full suite: **16 pre-existing failures** — all 16 confirmed failing at `HEAD` with none of
  this work item's changes, in a scratch worktree. This work item **broke none and fixed
  two** (the OpenAPI client-sync contract tests, by the earlier regeneration in this run).

### The pre-existing failures are not mine, and here is the proof

Sixteen tests fail in `tests/e2e/` and `tests/ingestion/test_url_feed_read.py`. Before
writing this item off as "someone else's problem", the baseline was measured: the same
tests were run at `HEAD` (`10b9de5`) in a throwaway worktree with the project's `.env`
copied in.

| | Failed | Passed |
|---|---|---|
| At `HEAD`, without this work item | 18 | 5764 |
| With this work item | 16 | 6036 |

Diffing the two failure sets: **two fixed, zero broken.** The two fixed were
`test_delivery_contract.py::test_the_generated_client_is_in_sync_with_the_document` and
`test_state_change_contract.py::test_the_generated_client_is_in_sync_with_the_document`.

The failures themselves are unrelated to the editorial queue — they are about published
events in the personal API returning 404, and a city feed's `last_modified` tracking
`now` instead of the latest event's timestamp.

### The access matrix, including every negative case

The AC asks for four cases and says *"each case is tested, including the negative ones."*
Twenty-nine tests, in two layers — the rule itself, and the same matrix through the admin:

| Who | Rule | Changelist | Action |
|---|---|---|---|
| Editorial group member (staff, **not** a superuser) | ✅ allowed | 200 | works |
| Staff with the permission granted **directly**, no group | ✅ allowed | 200 | works |
| Superuser | ✅ allowed | — | — |
| Staff with an *unrelated* ingestion permission | ❌ refused | 403 | — |
| Staff with no permission at all | ❌ refused | 403 | — |
| Signed in, **not** staff | ❌ refused | 302 → login | — |
| Anonymous | ❌ refused | 302 → login | — |
| Refused user attempting an action | ❌ refused | 403 | **nothing written** |

Two rows are worth naming:

- **`test_superuser_is_not_required`** asserts `user.is_superuser is False` *and* that the
  user may review. The AC's positive case is a plain group member, so the suite would fail
  if the grant regressed into "superuser is how you get in".
- **`test_a_staff_user_with_an_unrelated_permission_is_refused`** pins that holding *some*
  ingestion permission is not the same as holding the review one. Without it, "staff
  without the group" could pass for the wrong reason.

The refusal of a *staff without the group* is Django's own model-permission check, and it
needs no code — but it needs a test, or the next change to the group grant would go
unnoticed.

### The code review found two CRITICAL defects that 41 passing tests had missed

An independent review of this item found two defects that the suite of 41 tests did not
catch. Both are now fixed, and both have regression tests. They are recorded here
because **the shape of the gap is the lesson**, not the bugs themselves.

**1. A read-only viewer could approve, reject, dismiss and edit-and-publish.**
`may_review` accepted *either* review permission, and the admin used that one function
for both the view gate and the change gate — so `view_reviewitem` alone opened the write
gate. Six regression tests now pin the split: `may_view` for reading, `may_review` for
`change_reviewitem` only, and a view-only user may not approve, reject, dismiss or edit.

The subtlety: Django's `@admin.action(permissions=["change"])` is **advisory**. It filters
the action out of the dropdown, but the changelist's gate is
`has_view_or_change_permission` — which a read-only viewer satisfies — and
`response_action` resolves the action *by name* from the POST without a second check. The
enforcing check therefore lives in `_verdict`, the helper all three actions share.

**2. The staleness lock was absent in production, and every test passed anyway.**
The `expected_event_version` field was declared on the form but named in **no fieldset**,
and Django only renders fields that appear in a fieldset — so the page contained no token
input at all. With the field also `required=False`, a real browser posted no token and
the optimistic lock silently did not run.

**Why 41 tests missed both:** the tests hand-built the POST body and always included the
token, and the permission tests used a user holding *both* permissions. A test that posts
what the code expects cannot catch a field the page never rendered.

The two new tests that would have caught them are cheap and read the **rendered page**:
`test_the_change_page_carries_the_expected_event_version` asserts the input is in the
HTML with the right value, and `test_a_view_only_user_cannot_approve` (and its three
siblings) exercises the matrix with the *weakest* permission rather than the group.

### Acceptance Criteria Validation

| Criterion | Status | Evidence |
|---|---|---|
| A `ReviewItem` changelist, **open items first**, then by priority and `due_at` | ✅ | `test_changelist_lists_open_items_first`, `test_changelist_orders_by_priority_then_deadline`, `test_changelist_orders_reports_by_due_at_within_a_priority_band` — all assert **relative positions in the rendered HTML**, not the queryset's order |
| `user_reported` items past their 24h SLA **visibly marked** | ✅ | `test_changelist_marks_a_report_past_its_sla` — asserts `icon-yes.svg` on the overdue row and `icon-no.svg` on the one inside its window |
| A non-report item is never marked overdue | ✅ | `test_changelist_does_not_mark_a_non_report_item_overdue` — only `user_reported` carries a deadline (D8), so "overdue" cannot be true of the others |
| Filterable by reason, status and source | ✅ | `test_changelist_is_filterable_by_reason_status_and_source` — the source filter keys on `source__id__exact`, which is what `RelatedFieldListFilter` actually uses |
| The page shows the event's current facts, or the source's score history for a source item | ✅ | `test_change_page_shows_the_facts_an_editor_decides_on`, `test_change_page_for_a_source_item_shows_its_verdict_history` |
| The source and its badge | ✅ | The source's name is on the page; the badge comes from `services.source_badges` |
| The report count **with category tallies** | ✅ | `"wrong venue: 3"` and `"duplicate: 1"` appear in the rendered page |
| **No reporter identities** | ✅ | `test_change_page_shows_no_reporter_identities` — asserts the words "reporter" and "reported by" are absent. The `ReviewItem` row has no user column at all (D4), so there is nothing to show |
| Approve, Edit and Reject (and Dismiss, for source items) **call the `editorial-review-commands` services** | ✅ | Four tests: each asserts the item's status *and* resolution changed, the event's publication status changed, and exactly one audit row exists with the editor's id |
| A command's refusal (stale version or already-closed item) **shows on the form, not as a 500** | ✅ | `test_an_action_on_an_already_resolved_item_reports_a_refusal`, `test_edit_form_shows_a_stale_version_refusal_on_the_form`, `test_edit_form_shows_an_already_resolved_refusal_on_the_form` — each asserts **200**, the message on the page, and **that nothing was written** |
| Edit uses a form **limited to editable fields**, and its `clean()` runs the command's own checks | ✅ | `test_edit_form_offers_only_the_editable_fields` asserts `title`/`start_time_utc` are present and `slug`/`publication_status`/`extraction_confidence` are not. `test_edit_form_with_nothing_changed_shows_a_refusal` proves `clean()` runs the command's checks — "Nothing to change" is the command's refusal, surfaced by the form |
| **Delete is disabled** on every editorial model view | ✅ | `test_delete_returns_403` — and the row survives |
| **No admin action bypasses a command** | ✅ | `test_no_action_bypasses_a_command` asserts the audit rows for the item are exactly `["review_item_raised", "review_item_approved"]`. An admin that wrote the row itself would leave no second row |
| The summary shows the queue size, the age of the oldest open item, and the count of SLA breaches | ✅ | `test_changelist_shows_the_three_fr57_metrics` — asserts the `QueueSummary` **in the context** *and* the three `data-field` markers in the body |
| The summary **counts open items only** | ✅ | `test_changelist_summary_counts_open_items_only` — a resolved item is history and is not counted |
| The metrics are **computed by an `ingestion` read service, not in the template** | ✅ | The context carries a `QueueSummary` computed by `services.review_queue_read`. The template only lays it out — and it *cannot* compute the age, because Django templates have no arithmetic |
| **Access:** group member may see and act; non-staff and staff-without-the-group are refused; superuser is not required; every case tested | ✅ | The 29-test matrix above |
| Tests drive the admin through the Django test client | ✅ | Every test in `test_admin_queue.py` goes through `client.get`/`client.post` against `admin:ingestion_reviewitem_changelist` and `admin:ingestion_reviewitem_change` |

### The one test that proves the queue cannot drift from its own summary

`test_changelist_orders_by_priority_then_deadline` and
`test_changelist_shows_the_three_fr57_metrics` assert against **different** orderings of
the same data — the rendered row order, and the summary's counts. The priority expression
is applied in the database as one `Case/When` (`shared.constants.REVIEW_PRIORITY`), and
the **same** expression object is used by the read service and by the admin's
`get_queryset`. If two implementations of "priority" ever disagreed, the page would
describe a queue that does not exist — so the mapping lives in one place, and
`review_queue_read.priority_expression()` is public for exactly that reason.

### What the implementation taught us, and what it cost

Two things did not work the way the plan assumed, and both were Django's own machinery
rather than our code. They are recorded in `plan.md` under "As built", because a plan that
silently differs from the code is worse than no plan.

1. **A `ModelForm` over `Event` broke the readonly panels and the redirect.**
   `helpers.AdminReadonlyField.contents()` reads `obj = self.form.instance`, and
   `save_form` returns `form.save(commit=False)` — so the panels got the wrong object and
   the post-save redirect went to the *event's* URL. The fix is a `ModelForm` whose
   `Meta.model` is `ReviewItem`, whose `Meta.fields` is `()`, and whose event fields are
   declared by hand. The instance is the review item; the *fields* describe the event.

2. **An event item's source is one hop away.** D1 says a target is an Event *or* a Source,
   never both — so `item.source` is null for the item kind that matters, and the source
   panels rendered as dashes until both the read service and the admin resolved it as
   `item.source or item.event.source`.

Neither was found by reading the code. Both were found by a test that rendered the page
and looked at it.

### Gates

| Gate | Result |
|---|---|
| `ruff check` / `ruff format --check` | ✅ all checks passed · 571 files formatted |
| `lint-imports` | ✅ **19 contracts kept, 0 broken** — the `models-ingestion` contract holds with the `ModelAdmin` in `ingestion` |
| `manage.py check` (AD-15) / `makemigrations --check` | ✅ no issues / no changes detected |
| Coverage 80% / 100% `domain/` | ✅ 99% / 100% |
| `pytest tests/architecture/` | ✅ 898 passed |
| OpenAPI / frontend | n/a — no API or frontend change |
| **Admin surface** | ✅ the queue appears under **Ingestion**, confirmed in the browser with the user |
| **After the code review** | ✅ `tests/editorial/` **55 passed** · full suite **6050 passed**, still exactly the 16 pre-existing failures |


---

## Work Item: reliability-recompute-and-escalation

*FR-16's second half: the score that remembers — history, weekly recompute, and escalation.*

**What this work item had to get right.** FR-16 names four things that are easy to get
subtly wrong, and each one is a *counting* question:

- what an editorial verdict is worth to the score,
- whether one verdict on an event with five reports counts once or five times,
- when a source is due for a recompute,
- and what an escalation is allowed to do (FR-16: *"escalation, never removal"*).

So the tests are mostly about **the sign of each verdict** and about **one verdict counting
once**, and the assertions are on values rather than on the absence of a line of code.

### The four new test files

| File | Tests | What it pins |
|---|---|---|
| `tests/ingestion/test_reliability_score.py` | **27** | The counting table, the five-reports-one-verdict rule, the ISO week, the weekly guarantee, the 0.50 prior, and the idempotence of a re-run |
| `tests/ingestion/test_reliability_escalation.py` | **13** | The low-score path, the spike path, no duplicate escalation, the audit rows, and the never-removal assertion |
| `tests/ingestion/test_reliability_worker.py` | **12** | The tick asks on every beat, the job decides who is due, and the claim writes nothing |
| `tests/ingestion/test_reliability_score_model.py` | **16** | The named constraints and the table's own trigger, proven on the database with raw SQL |
| `tests/worker/test_scheduling_tasks.py` (modified) | **20** | The tick enqueues `worker.tasks.recompute_reliability` on every beat |

**88 passed** across those five files.

### The ACs, and the test that meets each

| AC | Test | Note |
|---|---|---|
| One row per (source, computation); the score, the counts, and a computed-at | `test_the_database_refuses_a_second_row_for_the_same_source_and_period`, `test_the_row_records_the_counts_it_was_computed_from` | The constraint is proven **on the database**, not through the service — a service-only test would pass even if the constraint were missing |
| The current score is cheaply readable; no row reads as the 0.50 prior | `test_a_source_with_no_score_reads_as_the_prior` | Asserts against `domain.reliability.reliability_score(0, 0)` rather than a second copy of `0.50` |
| **Reject = negative** | `test_a_rejection_is_negative` | |
| **Approve = positive** | `test_an_approval_is_positive` | |
| **Edit = the design decides** (design D4) | `test_an_edit_is_negative` | Negative: the source's facts were wrong and an editor had to change them |
| **A user report counts only when upheld**, and *upheld* is defined (design D7) | `test_a_report_on_an_approved_event_counts_for_nothing`, `test_a_report_on_an_edited_event_is_upheld` | "Upheld" means the verdict on the reported event was `rejected` or `edited` |
| **One editorial verdict on an event with five reports counts once** | `test_five_reports_and_one_verdict_count_once` | Asserts `negatives == 1` **and** `negatives != 5` — the second assertion is the point |
| …and the five reports are **not lost** | `test_the_five_reports_are_still_recorded_as_a_fact` | The report count is frozen onto the observation, because the reports themselves live in `personal` and are purged with the account |
| **Dismissals** are a named, unimplemented input (design D5, D6) | `test_a_dismissal_is_neutral` | **Neutral, not absent**: the row exists, and contributes to neither count |
| The recompute job is enqueued from the existing `worker.tasks.tick` | `test_the_tick_enqueues_the_recompute_on_every_beat` | A weekly cadence is **not** a minute-modulo rule, so the tick asks and the job decides |
| **Idempotent within a period** (no duplicate row) | `test_a_re_run_in_the_same_period_writes_no_second_row`, `test_the_database_refuses_a_second_row_for_the_same_source_and_period` | |
| …and a re-run **refreshes** rather than leaving a stale score | `test_a_re_run_refreshes_the_score_rather_than_leaving_it_stale` | A score a week stale is a score that is wrong |
| **The weekly guarantee** — a source not recomputed for 7 days is due | `test_a_source_not_recomputed_for_seven_days_is_due`, `test_a_source_scored_last_week_is_due_today` | |
| **Escalation on the low-score path** | `test_a_low_score_with_thirty_observations_raises_a_review_item`, `test_a_low_score_with_fewer_than_thirty_observations_raises_nothing` | Both halves of the threshold; the second is the one that matters — twenty rejections give 0.17 but n is under 30, so there is not enough evidence to act on |
| **Escalation on the spike path** | `test_a_spike_raises_a_review_item_even_while_the_score_is_healthy` | Last week 2/40 bad, this week 24/40 — a 4.1× rise while the cumulative score is still respectable. A rule that only fired on the cumulative score would miss this |
| …and a steady bad rate is **not** a spike | `test_a_steady_bad_rate_is_not_a_spike` | The same badness every week is not a spike |
| …and a first week **cannot** spike | `test_a_source_with_no_previous_week_cannot_spike` | The domain module's small-sample suppression makes this safe to pass unconditionally |
| Escalation goes through `raise_review_item(source, reason=source_reliability)` | `test_a_low_score_with_thirty_observations_raises_a_review_item` | The queue's own rule is **called**, not reimplemented |
| **Bumped, not duplicated** | `test_a_second_escalation_bumps_the_item_rather_than_opening_a_second`, `test_the_bump_is_audited` | |
| **Never removal (FR-16)** — no path pauses, hides or deprioritises ingestion | `test_an_escalation_changes_nothing_about_the_source`, `test_an_escalated_source_is_still_ingesting_on_schedule`, `test_the_escalation_does_not_hide_the_events` | Asserted on **values**, not on the absence of a line — trusting the absence of a line is trusting the source. Nine `Source` columns are compared before and after |
| AD-5: the recompute writes an audit row in its transaction | `test_the_recompute_is_audited_with_its_counts` | The audit row carries the counts the score came from, so the number can be checked later |
| AD-15: every model names its retention category | `test_the_table_declares_the_source_registry_retention_category` | |

### Three tests that are worth their weight on their own

**1. The five-reports rule is structural, not arithmetic.**
`test_five_reports_and_one_verdict_count_once` does not multiply by zero and divide — the
storage makes multiplication impossible. `SourceObservation.source_observation_item_uq`
permits **one observation per review item**, and all of an event's reports live on one
`user_reported` item, so a verdict on that event can only ever close one item and record
one observation. The test asserts the *weight* (`negatives == 1`) and the *fact*
(`report_count == 5`) separately, because they are two different claims.

**2. The never-removal test compares values, not absences.**
`test_an_escalation_changes_nothing_about_the_source` reads nine columns — `status`,
`ingestion_cadence`, `last_ingested_at`, `last_attempted_at`, `consecutive_failures`,
`stale_since`, `freshness_ttl_hours`, `tz_coverage`, `tos_status` — before and after an
escalation, and asserts the two dictionaries are equal. A reader could not argue that the
source was paused *before* the escalation, because the test compares the whole tuple. A
second test starts from an active source and checks it is still active *and* still due
afterwards, and a third asserts the source's published events are untouched.

**3. The append-only rule is proven on the database, not through the service.**
`tests/ingestion/test_reliability_score_model.py` writes raw SQL against the catalog
connection and asserts the failure names the **named constraint** — so a test cannot pass
because some other rule happened to fire:

| Test | Asserts |
|---|---|
| `test_a_second_row_for_the_same_source_and_period_is_refused` | `source_reliability_score_period_uq` |
| `test_a_score_outside_the_unit_range_is_refused` | `source_reliability_score_range_ck` |
| `test_a_period_that_is_not_a_week_start_is_refused` | `source_reliability_score_week_ck` — the row is a *week*, not a moment |
| `test_a_row_cannot_be_deleted` | the trigger's own message |
| `test_a_row_can_be_deleted_inside_a_retention_purge` | `SET LOCAL eventpulse.retention_purge = 'on'` is the one way a history row goes away |
| `test_the_source_cannot_change` / `test_the_period_cannot_change` | "source and period are fixed" |
| `test_a_same_period_refresh_is_allowed` | the four computed columns may move — the exception the AC's idempotence needs |
| `test_the_python_guard_names_the_same_columns_the_trigger_allows` | the Python guard and the trigger **cannot drift**: the trigger's body is read with `pg_get_functiondef` and compared |

### The cross-database decision, and why the wall holds

Design D9 chose: **record the observation at resolution time**, from the item's own
tallies. The job never reads `personal`.

This is the load-bearing choice for AD-3. The alternative — the job counting
`personal.EventReport` rows — would have put a cross-database read in the weekly path.
Under D9 the *editor's verdict* is the event that crosses the wall, and it crosses it once,
at the moment the verdict is made, as a `catalog` row. The five reports are counted there
and then, and the count is frozen onto the observation.

The wall is therefore not merely respected; it is **invisible to the weekly job**, which
only ever reads `catalog`.

### What the implementation taught us, and what it cost

Three things did not work the way the plan assumed. All three are recorded in `plan.md`
under "As built", because a plan that silently differs from the code is worse than no plan.

1. **The shared append-only trigger could not carry this table.**
   `catalog.forbid_history_mutation` allows exactly **one** column to go from NULL to a
   value — an outbox's `propagated_at`. This row's same-period refresh rewrites four
   non-nullable columns at once (`score`, `positives`, `negatives`, `computed_at`), which
   the shared trigger would refuse. And that refresh is exactly what the AC's idempotence
   requires: *"a re-run writes no duplicate row"* — and a score that is a week stale is a
   score that is wrong. So the table got **its own trigger**, `catalog.guard_reliability_score()`,
   written out in full and **narrow**: the source and the period are fixed, the id and the
   creation time are immutable, and the four computed columns may move. **This is a
   divergence from the design doc**, which said "append-only with one exception" — the
   design doc assumed the shared trigger would do, and it would not.

2. **The escalation *creates* the item, so the item cannot be fetched before the first
   recompute.** `test_the_bump_is_audited` originally read the `ReviewItem` before the
   first `recompute_source` and got `ReviewItem.DoesNotExist`. The item is the escalation's
   *output*, not its input. The test now fetches it after the first recompute.

3. **An append-only guard refuses to rewrite a row, so an unknown-kind observation has to
   be *created*, not updated.** `test_an_unknown_kind_is_refused_rather_than_skipped`
   originally tried `SourceObservation.objects.filter(...).update(kind="invented")` and
   hit `AppendOnlyViolation` — which is the guard working correctly. The row is now
   created directly with the unknown kind.

### Gates

| Gate | Result |
|---|---|
| `pytest` (full suite) | ✅ **6124 passed, 16 failed** — the 16 are the **pre-existing** failures, verified by stashing the branch and re-running at HEAD |
| `pytest` (the four new files + the modified worker file) | ✅ **88 passed** |
| `ruff check` / `ruff format --check` | ✅ all checks passed · 577 files formatted |
| `lint-imports` | ✅ **19 contracts kept, 0 broken** |
| `manage.py check` (AD-15) / `makemigrations --check --dry-run` | ✅ no issues (3 silenced) / no changes detected |
| Coverage `domain/` (AD-8) | ✅ **100%** (1010 statements) |

### The pre-existing failures, verified as pre-existing

The suite ends with 16 failures. They are not this work item's, and the branch was
verified rather than assumed: the changes were stashed, the same files were re-run at
HEAD, and the **same 16** failed with the same names.

```
tests/delivery/test_reminder_plan_api.py::test_a_saved_plan_and_its_sends_move_together
tests/e2e/test_personal_events_and_saved_catalog.py::test_the_whole_personal_event_and_save_flow_holds_together
tests/e2e/test_save_race.py::test_a_save_that_races_a_postponement_reports_itself_stale
tests/e2e/test_save_race.py::test_a_save_that_does_not_race_is_not_stale
tests/e2e/test_save_race.py::test_a_snapshot_survives_a_catalog_postponement_unchanged
tests/e2e/test_save_race.py::test_a_save_is_idempotent_and_one_row
tests/e2e/test_timeline_and_conflict_proof.py::… (9 tests)
tests/ingestion/test_url_feed_read.py::test_a_city_lastmod_is_the_latest_of_its_events
```

They are the personalisation/e2e save-conflict suite and the URL-feed `last_modified`
test — untouched by this work item, and owed to the earlier intents in this run.

### Three architecture tests that had to learn about the new table

Adding a table is never just adding a table. Three maps had to learn about
`ingestion_sourcereliabilityscore`, and each of them is a map whose *whole job* is to
catch an unowned table:

- `tests/architecture/test_write_ownership.py` — `TABLE_OWNERS` now claims it for
  `ingestion`. AD-16: `ingestion` owns it, and it is written only by the ingestion
  recompute service.
- `tests/wall/test_schema_placement.py` — it is a **catalog** table. Each row is a week's
  score for a source: a standing fact about the catalog, carrying no user identity, so it
  sits on the catalog side of the AD-3 wall.
- `tests/ingestion/test_models.py` — the designed-model count went from twelve to
  thirteen, and the retention-category map gained
  `SourceReliabilityScore: SOURCE_REGISTRY`.

The third is worth a note: a score is a **standing fact about a source**, not user data,
so it is purged with the source registry rather than with an account. That is why the
table's own trigger permits deletion inside a retention purge — and why that one case is
the *only* way a history row goes away.

### After the code review

The review found **two CRITICAL defects** — a claim that prevented nothing, and a write
that could race — plus five more. All are fixed, and the suite grew by **16 tests** to
cover what the gaps had hidden:

| Added test | What it pins |
|---|---|
| `test_the_counting_table_holds_the_signs_it_promises` | The table's **values**, not just its key set. A sign flip would have passed every other test in the suite, because every other test *reads* the table to work out what to expect |
| `test_the_escalation_threshold_counts_the_same_observations_the_score_does` | One N, not two: the score's floor and the escalation's min-N count the same observations |
| `test_two_writes_for_the_same_period_leave_one_row` | The write cannot collide — the `SELECT`-then-`INSERT` race is closed |
| `test_a_second_claim_does_not_return_a_claimed_source` | **The test the old, lock-only claim failed** |
| `test_a_released_claim_can_be_claimed_again` | A source whose recompute failed is retried on the next tick |
| `test_a_stale_claim_is_reclaimed` / `test_a_fresh_claim_is_not_reclaimed` | Both sides of the claim TTL |
| `test_one_failing_source_does_not_lose_the_rest_of_the_batch` | The batch is not all-or-nothing |
| `test_a_failed_source_releases_its_claim` | A failed source is not stranded |
| `test_the_runtime_role_cannot_delete_the_row` / `…_cannot_update_the_row_wholesale` / `…_can_refresh_the_computed_columns` | The third layer of the append-only standard: the privileges |
| `test_change_page_for_a_source_item_shows_the_stored_score` / `…_shows_the_prior_for_a_source_that_has_not_been_scored` | The admin shows the **stored** score, and the prior when there is none |

**After the fixes:** the four reliability files + the worker file + `tests/editorial/` are
**157 passed** (68 before the review), and the full suite is **6140 passed, 16 failed** —
the same 16 pre-existing failures, verified by stashing the branch and re-running at HEAD.

### The one lesson the review found

**A lock is not a claim when the work happens in a different transaction.** The design
doc's D10 promised that two overlapping ticks cannot recompute the same source twice, and
the code implemented something that *sounded* like it — a `FOR UPDATE SKIP LOCKED` claim,
the same words the scheduler's claim uses. But the scheduler's claim is *also* persisted
to a column, and the reliability claim was not. The lock was released by the transaction
that took it, and the recompute — the thing the lock existed to protect — ran after that
release. Nothing contradicted the other on the page.

The generalisable form: **when a lock is meant to protect work in another transaction, a
persisted marker is the mechanism, not the lock.** And the test that catches it is one
assertion: claim twice, assert the second claim returns nothing.

---

## Work Item: ranking-consumes-reliability

The proof this item exists for is **two otherwise-identical events, one from a source
scored 0.2 and one from a source scored 0.8, ranking in that order** — and the term
being *load-bearing* rather than decorative. So the tests were written around that
sentence, and then **every proof was checked by breaking the code**.

### The three layers of proof

| Layer | What it proves | Where |
| --- | --- | --- |
| **Domain** | The term moves the score, by exactly its weight, and does so in **every** slot | `tests/domain/test_ranking.py` |
| **Service** | The *stored* score reaches the card, and the read costs **no extra query** | `tests/personalization/test_digest_composition.py` |
| **Architecture** | A read never recomputes, a stored explanation is never rewritten, and the ranking never writes FR-16's score | `tests/architecture/test_ad10_explanation_persistence.py` |

The domain layer is arithmetic; the service layer is the one that goes **through the
database**, and it is the one that proves the value *travels*.

### The domain proofs

```python
LOW_RELIABILITY = Decimal("0.20")
HIGH_RELIABILITY = Decimal("0.80")
EXPECTED_RELIABILITY_DELTA = Decimal("0.15")   # the raw arithmetic
EXPECTED_OBSERVED_DELTA = Decimal("0.16")      # the observable gap between two cards
```

**Two numbers, because both are true.** The raw difference is `0.25 × (0.80 − 0.20) =
0.15`. The *observable* difference is **0.16**, because each score is quantised to two
decimals **after** the sum, so each is rounded from its own raw value. A test asserting
only 0.15 would have failed; a test asserting only 0.16 would have looked like the
weight was 0.26. Both are pinned, and the comment says why they differ.

The tests:

- `test_the_reliability_term_moves_the_score` — the two scores differ at all.
- `test_the_reliability_term_moves_the_score_by_exactly_its_weight` — the difference is
  the weight times the reliability gap, and it is *only* that.
- `test_the_two_reliabilities_differ_by_the_term_and_nothing_else` — the two scores are
  exactly the hand-computed sums.
- `test_a_better_source_ranks_above_a_worse_one_in_slot_1` / `_slot_2` / `_slot_3` —
  **the AC's proof, once per slot that uses the term.**
- `test_slot_3_does_not_invert_the_reliability` — FR-5 *multiplies by* reliability (a
  quality gate, not a popularity term); inverting it would make Slot 3 structurally
  prefer the least reliable sources.
- `test_the_reliability_term_is_at_fr22s_published_weight` — 0.25, FR-22's `w2`.
- `test_the_prior_contributes_like_any_term_with_no_opinion` — the prior's own
  contribution is `0.125`, which quantises to **0.12** (`ROUND_HALF_EVEN`), not 0.13.
- `test_the_reliability_input_is_required` — `RankingInputs` has **no** default for the
  term, so a construction site cannot forget it silently.

### The service proofs, and the N+1

- `test_the_source_reliability_reaches_the_card` — **two users, one event, one day.** The
  composition is a no-op for a user who already has a digest, and the candidate read
  drops an event that has started, so the two compositions have to be for different
  users at the same `NOW` against the same event. Everything is identical except the
  source's score.
- `test_an_unscored_source_is_at_the_prior` — the unscored card falls **strictly
  between** a source at 0.00 and a source at 0.80. Only the prior sits there.
- `test_the_composition_costs_no_query_per_candidate` — **the N+1 proof.** One
  candidate's catalog query count must equal ten candidates'. The read already does
  `select_related("venue", "source")`, so the score is a column on a row that is already
  there.
- `test_a_source_reliability_of_zero_still_scores_the_other_terms` — the worst possible
  source does not zero the card. The term is one of five.

### The architecture proofs

- `test_the_composition_never_rewrites_a_stored_explanation` — the composition may
  `bulk_create` its rows and may not `update`, `save`, `update_or_create` or
  `get_or_create` an existing one. A stored Relevance Pulse is **history**: its inputs
  were never persisted, so it cannot be recomputed under the formula that wrote it, and a
  rewrite would change a user's archive under them.
- `test_the_hysteresis_rule_is_not_a_cross_composition_carrier` — every
  `apply_hysteresis` call must pass `previous_bucket` and `previous_score` as the
  **literal** `None`. A carried-forward bucket would let a weight change be absorbed by
  the no-flicker band, so a card's dots would depend on which formula wrote the previous
  row — two formulas in production at once.
- `test_the_ranking_consumes_the_reliability_score_and_never_writes_it` — the ranking
  reads FR-16's score and never writes it. **AST-based**, because a name match fails on
  correct code: the composition writes `source_reliability=reliability_score(0, 0)`, a
  keyword argument whose value happens to be a function with the same name.

### Every proof was checked by breaking the code

| Mutation | Result |
| --- | --- |
| Remove the reliability term from `relevance_score` | ✅ **12 failures** — every domain reliability test, all three slot-ordering tests, both service tests |
| Replace the prior with `Decimal("0.00")` | ✅ caught — **and it was not caught before the review** (see below) |
| Look the score up per candidate (N+1) | ✅ caught — "12 catalog queries for ten candidates and 2 for one" |
| Insert an `.update()` on the compositions | ✅ caught — "A persisted Relevance Pulse is history" |
| Carry a previous bucket into `apply_hysteresis` | ✅ caught — the composition must pass `None` literally |
| Plant a `source.reliability_score = ...` assignment | ✅ caught — with the line and column named |
| Move the interest weight in the e2e probe | ✅ caught — all 10 contract probes go red |

### The false green the review found

`test_an_unscored_source_is_at_the_prior` claimed that an unscored source contributes
the prior **and not a zero**, and asserted `score > Decimal("0.00")` — which is true of
*any* reliability value, including zero, because four other terms contribute — plus
`reliability_score(0, 0) == Decimal("0.50")`, which asserts a **domain constant**, not
the composition's behaviour.

**Replacing the prior with `Decimal("0.00")` left all 63 tests in the file green.** The
test passed while the product did the exact thing its name says it prevents.

The rewrite makes the assertion relative — the only shape that can fail — and the same
mutation now fails with a message naming which comparison broke. The rewrite's *first*
attempt was itself wrong (three separate events, when the composition's three slots hold
three different events), and that failure is recorded in the design's D14.8 rather than
quietly fixed.

### The false green in the e2e probe

Probe #5 hard-coded `RANKING_WEIGHT_INTEREST = Decimal("0.45")`. After this item the
constant is `0.35`, so the probe's edit would have found **nothing to replace** and the
suite would have stayed green — a probe that proves nothing while looking like a pass.
The literal was moved and a script confirmed the probe literal and the constant literal
**match**.

### The pin, and the amendment it points at

- `test_ranking_weights_are_pinned` — the five weights, their sum of 1.00, and the
  amendment reference.
- `test_the_ranking_weights_have_an_amendment_that_says_so` — reads
  `docs/adr/ADR-0025.md` and checks it lists every weight it claims to authorise.

**Two ways to move a weight, and both fail CI**: move the weight and leave the
reference (the number assertion fails), or move the weight *and* update the reference
string (the ADR-document assertion fails, because the new weight is not in the ADR's
table and the ADR is a human document). The third leg is the e2e probe.

### Results

| Gate | Result |
| --- | --- |
| `pytest` (full suite) | ✅ **6158 passed, 16 failed** — the 16 verified as pre-existing by stashing the branch and re-running at HEAD |
| `pytest tests/architecture/ tests/domain/ tests/personalization/ tests/shared/` | ✅ **2882 passed** |
| `pytest tests/domain/ --cov=domain` | ✅ 643 passed · `domain/ranking.py` at **100%** |
| `pytest tests/e2e/mutation_probe_contract_e2e.py` | ✅ all **10** contract probes caught |
| `ruff check` / `ruff format --check` | ✅ all checks passed · 578 files formatted |
| `lint-imports` | ✅ 19 kept, 0 broken |
| `manage.py check` / `makemigrations --check --dry-run` | ✅ no issues (3 silenced) / no changes detected |

**No new failures.** The 16 are the run's standing failures — the personalisation/e2e
save-conflict suite and the URL-feed `last_modified` test — untouched by this work item
and owed to the earlier intents in this run.

---

## Work Item: frontend-report-control

*The small flag: "Report this event" on the Detail screen.*

### Test Results

| Suite | File | Tests |
| --- | --- | --- |
| The control (component) | `components/detail/event-report-control.test.tsx` | **36** (created) |
| The flag's page-level presence and absence | `tests/event-detail-a11y.test.tsx` | **+3** (created) |
| axe over the open modal | `tests/event-detail-a11y.test.tsx` | **+1** (created) |
| The Detail Screen's section list | `app/events/[id]/page.test.tsx` | 1 assertion removed, 1 stub extended |
| The endpoint's coverage in the contract | `tests/ad19-endpoint-coverage.test.ts` | +1 endpoint row |
| **New/changed total** | | **41** |

- **Frontend suite: 107 files, 1810 tests, all passed.**
- **Backend suite: 6158 passed, 16 failed** — the same 16 pre-existing failures, listed
  below. This item changes no backend code, so the number is expected to be identical.
- `tsc --noEmit` clean · `eslint .` clean · `prettier --check .` clean.

### The sixteen failures are inherited, not introduced

```
tests/e2e/test_save_race.py                            (4)
tests/e2e/test_timeline_and_conflict_proof.py          (9)
tests/e2e/test_personal_events_and_saved_catalog.py    (1)
tests/delivery/test_reminder_plan_api.py               (1)
tests/ingestion/test_url_feed_read.py                  (1)
```

They are the run's standing failures: fixtures hard-code event starts such as
`2026-11-06`, which is now in the past, so saving a past event answers 404 and the
`lastmod` assertions compare against *now*. They were verified against clean `HEAD` in
work item 9 and are **untouched by this item** — this item writes no backend file.

### The mutation probes — 33 probes, 33 caught

The house rule for this run is that **no proof is accepted by inspection**. Every
assertion in this item was proved able to fail by planting one real defect and watching
the suite go red.

`tests/report-control-mutation-probe.mjs` — **24 probes, 24 caught.** Each probe checks
its pattern **exists** before it edits anything; a missing pattern is reported as
**BROKEN**, which counts as a failure. (This is the exact defect found in work item 9's
e2e probe, whose hard-coded weight literal no longer existed, so its edit found nothing
and the suite stayed green while proving nothing. The same trap is closed here.)

The probes that matter most are the ones that attack the item's **central claims**:

| # | Planted defect | Caught by |
| --- | --- | --- |
| 1 | **Choosing an option also submits it** — the post carries the newly chosen category | "does not submit when an option is chosen" (both the call count and the body) |
| 2 | **The event is visibly marked as reported** — the flag becomes "Reported" | "leaves the event visibly unchanged" |
| 3 | **The toast becomes a second status region** | "does not add a second status region" |
| 4 | **The rate limit is swallowed** instead of shown | "shows the API's message inline" |
| 5 | **The rate limit closes the modal** instead of staying open | "leaves the modal open" |
| 6 | **A network failure clears the selection** | "keeps the selection, so the user does not choose again" |
| 7 | **A network failure leaves the Submit disabled** — no retry | "offers a retry — the Submit is live again" |
| 8 | **The options stop being a radio group** | "is a radio group" |
| 9 | **Two options can be checked at once** | "keeps exactly one option checked at a time" |
| 10 | **The option's accessible name swallows the description** | the four-label test and `getByRole("radio", { name })` |
| 11 | **The focus does not return to the flag** | "returns the focus to the flag" |
| 12 | **The heading no longer takes the focus when the modal opens** | "moves the focus to the heading when it opens" |
| 13 | **The request body carries a hand-written shape** | the body equality assertion |
| 14 | **The request goes around the generated client** | "goes through the generated client" |
| 15 | **A fifth category is offered** / **a free-text field is added** | "offers exactly four options" / "has no free-text field" |
| 16 | **The flag is styled as a primary button** | "is visually subordinate to Save and Share" |
| 17 | **The modal is not dismissible** — Escape no longer closes it | "closes on the Escape key" |
| 18 | **The success toast says something else** | "shows the toast" |
| 19 | **The modal does not close on success** | "closes the modal" |
| 20 | **The toast's live region is only rendered once there is a message** | "keeps the toast's live region in the DOM before there is a message" |

`tests/report-flag-page-probe.mjs` — **2 probes, 2 caught.** These are the **page-level**
claims, and they are proved in the file that renders the **real** action row
(`tests/event-detail-a11y.test.tsx`) — because `app/events/[id]/page.test.tsx` stubs
`DetailActions` out and cannot see the flag at all.

| # | Planted defect | Caught by |
| --- | --- | --- |
| 1 | **The action row renders for an anonymous reader** — the `personal` gate is lifted | "is absent for an anonymous reader" and "is gone for an anonymous reader in the same way Save is" |
| 2 | **The report flag is removed from the action row** | "is there for a signed-in reader" |

**Probe 1 is the load-bearing half.** A page that rendered the flag for *everyone* would
satisfy "the flag is there for a signed-in reader" and fail nothing — so the anonymous
case gets its own probe, and it is proved to fail.

`tests/ad19-client-break.mjs` — **7 probes, 7 caught** (unchanged by this item; re-run to
confirm the new endpoint row did not weaken the contract gate).

### The one existing test this item breaks — and what replaced it

`frontend/app/events/[id]/page.test.tsx:1137` asserted the Detail Screen renders **no**
"report this event" text. It was written when the feature did not ship, and it is now
wrong by design.

**The one assertion was removed**; the test's other three assertions — reviews, similar
events, "attended" — are **untouched**. The `DetailActions` **stub** gained a
`<button>Report this event</button>` so the removal is not true for the wrong reason: the
stub now mirrors the real row.

**The positive form of the claim lives where the real row renders** —
`tests/event-detail-a11y.test.tsx`:

- "is there for a signed-in reader" — the flag is present.
- "is absent for an anonymous reader" — it is not.
- "is gone for an anonymous reader in the same way Save is" — Save and the flag share
  one fate, because they share one `if`.

This is not a test bent to fit the code. The test's purpose is "the Detail Screen ships
only the sections that have shipped"; the report control is now one of them, and a test
asserting a shipped section was absent would be the defect.

### Acceptance Criteria Validation

| Criterion | Status | Evidence |
| --- | --- | --- |
| A flag control in the secondary row, visually subordinate to Save and Share | ✅ | `components/detail/detail-actions.tsx` renders `<EventReportControl />` after `<ShareControl />`. "is visually subordinate to Save and Share" asserts the **absence** of `bg-accent-terracotta`, `bg-surface-elevated` and `border-border-subtle` — subordination as the absence of the other two's tokens. Probe 16 proves the assertion can fail. |
| The accessible name is "Report this event"; the icon alone is not the label | ✅ | `aria-label="Report this event"`, the glyph is `aria-hidden="true"`, and "shows the words as well as the glyph" asserts both the text and the hidden glyph. Probe 1 proves the name assertion can fail. |
| The modal offers exactly four single-select options, worded exactly as FR-59 | ✅ | "offers exactly four options" (a count), "words the four options exactly as FR-59 words them" (the four verbatim strings), "is a radio group", "keeps exactly one option checked at a time", "leaves the chosen option checked when the same one is pressed again". Probes 8, 9 and 15. |
| No free-text field | ✅ | "has no free-text field" asserts **no textbox at all** — not a disabled one — plus no `textarea` and no `input`. Probe 15. |
| Submit is disabled until an option is chosen | ✅ | "disables the Submit until an option is chosen". |
| Choosing + submitting is a single further action (choosing does not submit) | ✅ | "does not submit when an option is chosen" asserts **no request at all** *and* that no call carried the newly chosen category. Probe 1. |
| On success: the toast, the modal closes, focus returns to the flag | ✅ | "shows the toast" (FR-59's exact words), "closes the modal", "returns the focus to the flag" (WCAG 2.4.3 — the browser's default dumps a keyboard user at `<body>`). Probes 18, 19, 11. |
| The rate limit renders as a calm inline message | ✅ | Four tests: the API's **own** message verbatim (`lib/api-errors.ts` exists so the frontend quotes the API), inside the modal and not as a toast, the modal **stays open** ("a modal that closed on a refused report would tell the user it went somewhere"), and the selection is kept. Probes 4, 5. |
| A network failure leaves the modal open, the selection preserved, with a retry | ✅ | Four tests: the modal is open, the selection is preserved, the Submit is live again, no success toast, and the retry sends the **same** category. Probes 6, 7. |
| Signed out: the plan states the behaviour and a test pins it | ✅ | **Hidden**, and hidden by inheritance — the whole action row is already inside `{personal ? … : null}` (`app/events/[id]/page.tsx:477`), so the flag inherits Save's behaviour from the same `if` and **cannot drift from it**. The plan states this (decision 1) and rejects sign-in routing: "a control that always ends at a sign-in wall is a control that does nothing, plus three taps." Pinned by "is absent for an anonymous reader" and "is gone for an anonymous reader in the same way Save is". Page probe 1 proves the pin can fail. |
| The event never visibly changes after a report | ✅ | "leaves the event visibly unchanged" asserts the body says nothing matching `/reported/i` **and** the flag still reads "Report this event". Probe 2. This is FR-59's own rule — "a single report does not auto-reject an event" — and it is why the report is a private signal, not a state. |
| The modal traps focus, Esc closes it, the options are a radio group, axe is clean | ✅ | The native `<dialog>` gives the focus trap with no JavaScript. "closes on the Escape key" asserts the `cancel` event's default is **not** prevented; "moves the focus to the heading when it opens"; "is a radio group" with `aria-checked`. The axe case audits `document.body` with the modal open and asserts zero serious or critical violations, with `color-contrast` disabled explicitly as in every other case in that file. |
| Vitest component tests cover rendering, selection, submission, success, the rate limit, network failure and the signed-out state | ✅ | 36 component tests in six describes — the flag, the modal, the submission, the success, the rate limit, a network failure — plus the signed-out state in the a11y file. |
| Generated API types; no hand-written request shapes (AD-19) | ✅ | `type ReportBody = components["schemas"]["EventReportIn"]` and `ReportCategory = ReportBody["category"]` — the four `value`s are typed by the **generated** union, so a category outside the contract is a **compile error**. The body is `const body: ReportBody = { event_id: eventId, category: selected }`. Probes 13, 14 prove the shape and the client path are both asserted. The endpoint is registered in `tests/ad19-endpoint-coverage.test.ts` with its operation id and its caller. |

### Issues Found

| Issue | Severity | Status |
| --- | --- | --- |
| The AC says "the existing Playwright and axe gates cover it" — **Playwright is not in this repository** (no `playwright.config.ts`, no `@playwright/test` dependency, no e2e runner) | Medium | **Gap reported, not claimed as satisfied.** The **axe half** is honoured in the house's own way: a Vitest + axe-core case in `tests/event-detail-a11y.test.tsx`, the file that already is the Detail Screen's axe gate. The **Playwright half** is recorded as a gap. |
| The mockup's **daily report counter** does not ship | Low | No endpoint carries the tally, and FR-59 rejects the visible counterpart. Recorded in the design. |
| The mockup's **pre-emptively disabled Submit** does not ship | Low | The client cannot know the user is on their sixth report; the server's limit is discovered by attempting and rendered calmly. Recorded in the design. |
| The mockup's **repeat-reporter warning** does not ship | Medium | It needs the user's editorial rejection history, and no endpoint carries it. **A remaining FR-59 consequence** — carried forward, not silently dropped. |
| The backend's 16 standing failures | Medium | Pre-existing; owed to the earlier intents in this run. Untouched here. |

### Ready for Completion

- [x] All tests passing for this item — 1810 frontend tests, no new failure anywhere.
- [x] Every acceptance criterion validated, with the evidence named above.
- [x] **Every assertion proved able to fail** — 33 probes, 33 caught, none BROKEN.
- [x] The one existing test this item breaks was handled honestly: one assertion removed,
  three untouched, the positive form added where the real row renders.
- [x] The one gap (Playwright) is reported as a gap, not papered over.

### After the review

The code review auto-fixed **R1** — the `Message` union's `"failed"` member and
`FAILED_MESSAGE`, which no code path could reach (every failure sets `refusal`, not
`message`). The union is now `type Message = "reported"`, and its docstring says why
there is no failure toast.

**The probe moved with the code.** The mutation probe hard-codes the toast's source
line, so the fix would have left that probe with a pattern that no longer existed — the
exact trap this item's probes exist to catch. It was moved, and the probes were re-run:

| Gate | Result |
| --- | --- |
| `vitest run` (the whole frontend suite) | ✅ **107 files, 1810 tests, all passed** — unchanged by the fix |
| `tsc --noEmit` | ✅ clean |
| `eslint .` | ✅ clean |
| `prettier --check .` | ✅ "All matched files use Prettier code style!" |
| `report-control-mutation-probe.mjs` | ✅ **24/24 caught** — the live-region probe's pattern moved with the code |
| `report-flag-page-probe.mjs` | ✅ **2/2 caught** |
| `ad19-client-break.mjs` | ✅ **7/7 caught** |

**One gap carried forward, not closed:** the shared `Sheet` does not listen for the
native `<dialog>`'s `close` event, so a real browser's Escape closes the dialog while
React's `open` state stays `true`. This item is the `Sheet`'s fourth caller and inherits
the behaviour; it does not introduce it. It is also **untestable here** — jsdom does not
implement `dialog.close()` (verified: `dialog.close is not a function`). The fix belongs
in `Sheet`, where it would serve all four call sites at once.
