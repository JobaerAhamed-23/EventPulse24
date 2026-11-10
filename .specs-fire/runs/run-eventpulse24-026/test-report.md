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
