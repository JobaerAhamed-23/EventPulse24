---
run: run-eventpulse24-016
work_item: ingestion-scheduling
intent: event-catalog-ingestion
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at: 2026-10-28T12:33:39Z
---

# Implementation Plan: Ingestion Scheduling

## Approach

> **Needs your call:** decisions **S1–S7** below.

The 60-second tick stays the only beat entry, and it **never touches the database**: `tests/worker/test_tick.py` runs `tick()` with no database access and expects exactly one `worker.tasks` log record. So the tick only *enqueues*:

```
beat (60 s) ─► tick()                                  no DB, one "Tick" log record
                 ├─ enqueue schedule_sources                  every tick
                 └─ enqueue reconcile_outbox                  when now.minute % 5 == 0 (S3)
schedule_sources ─► apps.ingestion.services.scheduling
                     ├─ flag_stale_sources(now)               sets stale_since (2× cadence)
                     └─ claim_due_sources(now) -> [ids]       claims, then enqueue ingest_source per id
ingest_source(id) ─► apps.ingestion.services.ingest_source    (run-015) + releases the claim
```

**New command module `apps/ingestion/services/scheduling.py`:**
- `claim_due_sources(*, now, limit=SCHEDULE_BATCH) -> list[UUID]`: one `UPDATE … WHERE id IN (SELECT … FOR UPDATE SKIP LOCKED) RETURNING id`, so two schedulers never claim the same row.
- `flag_stale_sources(*, now) -> int`
- `release_claim(source_id)`

Each writes one audit row only when it changed something. Two **system** actors are used: `scheduler` for claims, `freshness` for stale flags.

**Worker tasks** (`worker/tasks.py`), each wrapping one command and returning `None`:
- `schedule_sources()`
- `ingest_source(source_id)`, which calls `apps.ingestion.services.ingest_source.ingest_source`. A refusal (paused, or crawl without ToS) is logged at `INFO` with its error code, not raised.
- `reconcile_outbox`, already there

Jobs are sent through one seam, `worker.tasks._enqueue(task, *args)` (`task.delay`). `tests/worker/conftest.py` replaces it with an autouse recorder, so `test_tick.py` itself stays unchanged and no test reaches Redis.

**Management command `ingest_source <source_id> [--sync]`** in `config/management/commands/`, next to `send_test_email`:
- `--sync` runs the ingestion command inline and prints the `IngestReport` (outcome, error code, counts).
- Without `--sync` it enqueues `worker.tasks.ingest_source` by name, through `config.celery.app.send_task`. `config` may import `apps` and its own Celery app, but never `worker`.

### Decisions that need your call

| # | Question | Proposed choice | Why |
|---|---|---|---|
| **S1** | When is a source due? The AC says `last_ingested_at + cadence <= now`. | Due when **active**, not ruled out by FR-17 (crawl needs `tos_status = approved`), not currently claimed, and `coalesce(last_attempted_at, created_at) + cadence <= now`. A source never attempted is due straight away (`last_attempted_at IS NULL`). | Keyed on the last *success*, a failing source would be due on **every** tick once its claim cleared: one request a minute to a site that is already failing. Keying on the last *attempt* retries at the declared cadence, which respects the feed (item 9's "no aggressive polling"). For a healthy source the two are the same, because every attempt that succeeds sets both. This is a deviation from the AC wording. |
| **S2** | How double runs are prevented | A new nullable **`Source.ingest_claimed_at`** column (migration `0003`). Claiming sets it; the `ingest_source` task clears it in a `finally`. A claim older than **`INGEST_CLAIM_TTL = 1 hour`** counts as lost (a worker died), so the source becomes claimable again. The pipeline's session lock (run-015 D2) stays the backstop against two runs executing at once. | The AC asks that a source "already queued or running is not enqueued again". The run lock only covers *running*, and a queued job can sit in Redis for minutes, so the queue state needs a column. `SKIP LOCKED` keeps two schedulers off one row. The TTL makes a lost job self-heal without an operator. |
| **S3** | When the tick enqueues the reconciler (every 5 minutes) | When `now.minute % 5 == 0` (UTC), the tick enqueues `reconcile_outbox`. That runs about once per 5 minutes; a drifted beat may run it twice in a minute or skip one window. | The tick must not touch the database, so it can't remember when it last ran. Both failure modes are harmless: reconciling is idempotent, and rows only wait longer. |
| **S4** | Freshness rule | `flag_stale_sources` sets `stale_since = now` on every active source with no stale flag where `coalesce(last_ingested_at, created_at) + 2 × cadence <= now`. "Exactly 2× cadence" is stale (inclusive). Paused sources are never flagged. The pipeline clears the flag on any success (run-015). | This is FR-13's consequence, measured from the last *success*, unlike S1. A never-ingested source counts from its registration. |
| **S5** | Batch size per tick | `SCHEDULE_BATCH = 100` claims per tick, oldest attempt first. | It bounds the work and the jobs enqueued per tick. The 40-source floor is far below it, and the rest are claimed on the next tick. |
| **S6** | Testing the clock (the work item says "use time freezing") | Every command takes `now`, and the tick's 5-minute rule takes it through a small `_now()` seam that tests patch. **No time-freezing library is added**, the same as run-015 P4. | Every time-dependent decision is an explicit parameter, so each boundary is testable at the exact second. |
| **S7** | A refused source inside the job (paused, or crawl without approval, after it was claimed) | The task catches `SourcePausedError`, `CrawlNeedsTosReviewError` and `SourceNotFoundError`, logs `INFO "Ingest skipped"` with `source_id` and `error_code`, and releases the claim. Anything else is raised to Celery after the claim is released. | A pause between claiming and running is expected and should not show up as a failure. Unexpected errors stay visible. |

### Deviations from the work item

- **S1** keys due-ness on the last attempt, not the last success.
- **S2** adds a column (migration 0003). The AC allowed it ("a claim timestamp … on `Source`").
- The 5-minute reconciler cadence is approximate (S3).

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/services/scheduling.py` | `claim_due_sources`, `flag_stale_sources`, `release_claim` |
| `backend/apps/ingestion/migrations/0003_source_ingest_claim.py` | `Source.ingest_claimed_at`, plus a partial index for due selection (`status = 'active'`) |
| `backend/config/management/commands/ingest_source.py` | `ingest_source <source_id> [--sync]` |
| `backend/tests/worker/conftest.py` | Autouse recorder for `worker.tasks._enqueue` |
| `backend/tests/worker/test_scheduling_tasks.py` | The tick's enqueues (every tick, the 5-minute rule), `schedule_sources`, the `ingest_source` task (claim release, refusal logging, error re-raise) |
| `backend/tests/ingestion/test_scheduling.py` | Due boundaries, paused/crawl never due, no duplicate claim across two ticks, claim TTL, `SKIP LOCKED` between two schedulers, stale flag at exactly 2×, audit rows |
| `backend/tests/config/test_ingest_source_command.py` | `--sync` output and errors; the enqueue path by name |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/worker/tasks.py` | `_enqueue`, `_now`; `tick()` enqueues; `schedule_sources` and `ingest_source` tasks. The `Tick` log line is unchanged. |
| `backend/apps/ingestion/models.py` | `Source.ingest_claimed_at` |
| `backend/shared/constants.py` | `INGEST_CLAIM_TTL`, `SCHEDULE_BATCH`, `STALE_AFTER_CADENCES = 2`, `OUTBOX_RECONCILE_EVERY_MINUTES = 5` |
| `backend/apps/ingestion/admin.py` | The stale flag is already listed. Add `ingest_claimed_at` to the read-only "Ingestion state" fields. |
| `.specs-fire/standards/coding-standards.md` | The scheduling rules: the tick never touches the database, claims, and due-ness by last attempt |

`tests/worker/test_tick.py` is **not modified**, and `beat_schedule` stays exactly one 60-second tick.

## Tests

The work item's tests, mapped to files:

| Work-item test | File |
|---|---|
| Due selection at cadence boundaries: one second before, exactly at, and after; never attempted; a failing source waits a cadence (S1) | `tests/ingestion/test_scheduling.py` |
| A paused source is never due; an unapproved crawl source is never due | same |
| No duplicate enqueue across two ticks; a claim past its TTL is reclaimed; two concurrent schedulers claim disjoint sets (`transaction=True`, threads) | same |
| Stale flagging at exactly 2× cadence (inclusive), not at 2× minus one second; never-ingested measured from `created_at`; paused never flagged; cleared by the next successful run | same |
| The management command: `--sync` prints the report; an unknown or paused source gives a `CommandError`; the async path sends `worker.tasks.ingest_source` by name | `tests/config/test_ingest_source_command.py` |
| `beat_schedule` unchanged | the existing `tests/worker/test_tick.py`, run as is |
| The tick enqueues `schedule_sources` every tick and `reconcile_outbox` only on minute % 5 = 0, with no DB access (the tick test has no `django_db` mark) | `tests/worker/test_scheduling_tasks.py` |
| The job releases its claim on success, on refusal and on an unexpected error | same |

Before the test report I'll run mutation probes, checking that each of these bugs is caught:
- `SKIP LOCKED` removed
- claims not cleared
- `>=` changed to `>` at each boundary
- a paused source left schedulable
- the tick querying the database

## Technical Details

- **Gates:** lint, check, makemigrations check, coverage (≥ 80% overall, 100% `domain/`). `domain/` is untouched.
- **Import contracts:**
  - `worker.tasks` imports `apps.ingestion.services.{scheduling, ingest_source, outbox, source_registry}`, never an API module (`worker-not-api`).
  - The management command lives in `config`, which may import `apps` and `config.celery`, never `worker`.
- **Migration 0003 is the only schema change.**

---
*Plan approved at Checkpoint 1. Execution follows.*
