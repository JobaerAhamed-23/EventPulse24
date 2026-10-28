---
run: run-eventpulse24-016
work_item: ingestion-scheduling
intent: event-catalog-ingestion
generated: 2026-10-28
mode: confirm
---

# Implementation Walkthrough: Ingestion Scheduling

## Summary

Sources now ingest on their own cadence, driven by the single 60-second beat tick (AD-7).
- **The tick never touches the database.** It enqueues `schedule_sources` every minute, and `reconcile_outbox` when the UTC minute is a multiple of 5.
- **`schedule_sources`** flags sources with no successful ingestion within 2× their cadence. It then claims due sources with `FOR UPDATE SKIP LOCKED` and enqueues one `ingest_source` job per claim. The job runs run-015's command and releases the claim however it ends.
- **`manage.py ingest_source <id> [--sync]`** runs one source now, inline or as a job.

## Structure Overview

```
beat ─60 s─► tick()  [no DB]
               ├─ _enqueue(schedule_sources)                  every tick
               └─ _enqueue(reconcile_outbox)                  minute % 5 == 0
schedule_sources ─► scheduling.flag_stale_sources(now)        stale_since, audited ("freshness")
                 └► scheduling.claim_due_sources(now)          ingest_claimed_at, audited ("scheduler")
                      └─ per id: _enqueue(ingest_source)       a failed enqueue releases its claim
ingest_source(id) ─► services.ingest_source (run-015) ─ finally: scheduling.release_claim(id)
manage.py ingest_source <id> --sync ─► services.ingest_source;  without --sync ─► send_task by name
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `apps/ingestion/services/scheduling.py` | `claim_due_sources`, `flag_stale_sources`, `release_claim` |
| `apps/ingestion/migrations/0003_source_ingest_claim.py` | `Source.ingest_claimed_at` and the partial index `source_due_idx` |
| `config/management/commands/ingest_source.py` | The management command |
| `tests/ingestion/test_scheduling.py`, `tests/worker/test_scheduling_tasks.py`, `tests/worker/conftest.py`, `tests/config/test_ingest_source_command.py` | 42 tests and the enqueue recorder |

### Modified

| File | Changes |
|------|---------|
| `worker/tasks.py` | The `_enqueue` and `_now` seams; `tick()` enqueues (its log line is unchanged); the `schedule_sources` and `ingest_source` tasks |
| `apps/ingestion/models.py`, `admin.py` | The claim column and index; the claim shown read-only in admin |
| `shared/constants.py` | `SCHEDULE_BATCH`, `INGEST_CLAIM_TTL`, `STALE_AFTER_CADENCES`, `OUTBOX_RECONCILE_EVERY_MINUTES` |
| `.specs-fire/standards/coding-standards.md` | The scheduling rules |

## Key Implementation Details

1. **The database-free tick.** `test_tick.py` (unchanged) calls `tick()` with no database access and asserts one log record. All database work moved into the `schedule_sources` job. A mutation probe confirmed that a database call in the tick fails that unmodified test.
2. **Due by last attempt, stale by last success (S1, S4).** A failing source is retried once per cadence, not every minute, and it becomes stale (2× cadence since the last success) so an operator sees it.
3. **Claims (S2).** The claim covers "queued", which the run lock can't see. `SKIP LOCKED` keeps two schedulers apart. Every way a job can end releases its claim (success, refusal, error, failed enqueue), and the 1-hour TTL is the safety net for a dead worker.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| S1 | Due = never attempted, or `last_attempted_at + cadence <= now` | Don't hammer failing feeds |
| S2 | `ingest_claimed_at` with `SKIP LOCKED`, a 1-hour TTL, released in `finally` | Covers queued jobs, not just running ones |
| S3 | Reconciler when `minute % 5 == 0` | The tick keeps no state; reconciling is idempotent |
| S4 | Stale at ≥ 2× cadence since the last success (or registration); paused never flagged | FR-13 |
| S5 | 100 claims per tick | Bounded work |
| S6 | Explicit `now` and a `_now` seam; no time library | Every boundary tested to the second |
| S7 | A source refused after its claim → `INFO "Ingest skipped"` and the claim released | A pause isn't a failure |
| Review | A failed enqueue releases that claim and continues | A broker blip mustn't block scheduling for an hour |

## Deviations from Plan

- **S1, clarified in implementation.** The plan wrote `coalesce(last_attempted_at, created_at) + cadence` but also said never-attempted sources are due at once. The code follows the second statement: a never-attempted source is due immediately, so a new source ingests on the next tick.
- **The review fix** (released claims on a failed enqueue), which you approved.
- **`release_claim` writes no audit row.** The run's own `ingest_source` audit row, or the job's "Ingest skipped" log line, closes the claim. Claims and stale flags are audited.

## Dependencies Added

None.

## How to Verify

1. **Run the gates**
   ```bash
   make lint-backend && make manage ARGS="check" && make manage ARGS="makemigrations --check --dry-run" && make coverage-backend
   ```
   Expected: 13 contracts kept, no issues, no changes, 1607 passed, 99.16% overall.
2. **See it live (manual, local stack)**
   ```bash
   make up && make migrate && make dev   # API, worker, beat, web
   ```
   Register an ICS source pointing at a fixture URL in admin, with fake fetch (the default). Within about a minute the worker log shows `Sources scheduled` (count 1), then `Ingest finished`. Events appear in admin, and the source's `Ingestion state` shows `last_ingested_at` set and the claim cleared.

   For a one-off run:
   ```bash
   make manage ARGS="ingest_source <source_id> --sync"
   ```

## Test Coverage

- **Tests added:** 45 (42 in the new files, plus 3 generated alias checks). The suite went from 1562 to 1607.
- **Coverage:** 99.16% overall, and 100% for `scheduling.py`, `worker/tasks.py`, the management command and `domain/`.
- **Mutation probes:** 11 planted bugs, all caught.

## Ready for Review

- [x] All acceptance criteria met
- [x] `test_tick.py` and the beat schedule unchanged
- [x] The review finding fixed with your approval
- [x] Standards updated

## Developer Notes

- **Never call a task's `.delay()` directly in `worker/tasks.py`.** Use `_enqueue`, so tests record it instead of publishing to Redis. This run leaked 4 jobs into the dev broker before the recorder existed; they were inspected and deleted.
- **A new periodic job** goes into `tick()` as an enqueue, never as a beat entry, and never as a query in the tick itself.
- **The dev queue** can be inspected with `docker compose exec redis redis-cli LRANGE celery 0 -1`.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-016*
