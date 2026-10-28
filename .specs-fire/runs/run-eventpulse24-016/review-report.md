# Code Review Report

**Run**: run-eventpulse24-016
**Intent**: event-catalog-ingestion
**Reviewed**: 2026-10-28
**Files Reviewed**: 13

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 1 | 0 | 0 |
| Reliability | 0 | 1 | 0 |
| **Total** | **1** | **1** | **0** |

**Tests Status**: Passing. After the fix: 1607 passed, 99.16% overall, 100% `domain/`, 13 contracts kept.

## Files Reviewed

- **Code:**
  - `apps/ingestion/services/scheduling.py` and `apps/ingestion/migrations/0003_source_ingest_claim.py` (created)
  - `config/management/commands/ingest_source.py` (created)
  - `worker/tasks.py`, `apps/ingestion/models.py`, `apps/ingestion/admin.py`, `shared/constants.py` (modified)
- **Tests:**
  - `tests/ingestion/test_scheduling.py`, `tests/worker/test_scheduling_tasks.py`, `tests/worker/conftest.py`, `tests/config/test_ingest_source_command.py` (created)
- **Docs:** `.specs-fire/standards/coding-standards.md` (modified)

## Auto-Fixed Issues

1. **[Code Quality] Two needless function-local imports** (`django.utils.timezone`, `django.db.transaction`) in `test_scheduling.py`, moved to the top. Ruff format reformatted 2 files. There is no behavior change.

## Applied Suggestions (approved by the user)

### 1. [Reliability] A failed enqueue left every claimed source stuck for an hour

- **Found by:** reading `schedule_sources`. The loop enqueued without a guard, after the claims had committed.
- **Probe:** `_enqueue` raising `ConnectionError` with 3 due sources. The task raised and **all 3 stayed claimed**, so no tick would schedule them until the 1-hour TTL.
- **Fix (your choice):** each enqueue is guarded. On failure the task releases that claim, logs `WARNING "Ingest not enqueued"` with `source_id` and `error_type`, and continues. The `Sources scheduled` count is the number actually enqueued.
- **Test:** `test_failed_enqueue_releases_that_claim_and_continues`. With the broker failing for the middle source, the other two are enqueued and still claimed, the middle one is unclaimed, and the warning and count are correct. Reverting the release fails the test.
- I also caught and fixed a bug in my first draft of this test: a condition that could never be true, so the broker never failed.

## Checked and found fine (no change)

| Concern | Result |
|---|---|
| Stale flags skip FR-17-refused crawl sources | Intended: a source that can't run isn't "stale", it is blocked. Its `tos_status` shows in admin. |
| A run longer than the 1-hour claim TTL | The next tick may re-claim it. The second job hits the pipeline's run lock (`already_running`), releases the claim and exits, so there's no double ingest. It costs one no-op job per tick until the run ends. Accepted: fetches have a total timeout far below an hour. |
| `--sync` doesn't touch claims | Correct: a manual run isn't scheduler state. If a scheduled job runs at the same moment, the run lock arbitrates. |
| `ingest_source` task given a malformed ID | `UUID()` raises inside the `try`, and `finally` raises again on the same value. That only happens through a hand-made enqueue; the scheduler always sends real IDs. Not worth extra code. |
