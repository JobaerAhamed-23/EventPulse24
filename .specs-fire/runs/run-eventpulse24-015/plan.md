---
run: run-eventpulse24-015
work_item: ingest-pipeline-and-lifecycle
intent: event-catalog-ingestion
mode: validate
checkpoint: plan (Checkpoint 2 of 2)
approved_at: 2026-10-28T12:06:57Z
design_doc: .specs-fire/intents/event-catalog-ingestion/work-items/ingest-pipeline-and-lifecycle-design.md
---

# Implementation Plan: Ingest Pipeline & Event Lifecycle

## Approach

This plan implements the approved design (D1–D19, departures 1–2) as written.

> **Needs your call:** plan-level decisions **P1–P8** below. Each one fills a gap the design leaves open, or corrects a fact I checked in the code while planning.

### Module layout (`apps/ingestion/services/`)

| Module | Public interface | Design |
|---|---|---|
| `ingest_source.py` | `ingest_source(source_id, *, actor=Actor.system("ingest_pipeline"), fetch_port=None) -> IngestReport`, `IngestReport` | D1–D3, D16, D17 |
| `ingest_item.py` | `ingest_item(run, candidate) -> str` (the outcome key counted by the run) | D4–D8, D13, D19 |
| `event_writes.py` | `create_event`, `apply_lifecycle_change`, `supersede_event`, `apply_silent_update` | D9–D11, D18 |
| `outbox.py` | `enqueue_propagation`, `mark_propagated`, `reconcile_outbox(*, now=None, limit=OUTBOX_RECONCILE_BATCH)` | D14, D15, design D23 |
| `slugs.py` | `mint_slug(title, start_time_local, event_id, long=False)` | D18 |

Supporting pieces:
- **`IngestRun`** is a private dataclass that carries what one run needs: the source, actor, venue cache, counts and the unchanged-record IDs. It exists so `ingest_item` doesn't take a dozen parameters.
- **The enqueue seam** is `outbox._send(task_name, args)`, which calls `celery.current_app.send_task`. Tests replace `_send` with an autouse recorder in `tests/ingestion/conftest.py`, so no test ever reaches Redis.
- **Worker tasks** (`worker/tasks.py`):
  - `propagate_state_change(state_change_id)` logs at `DEBUG` with `state_change_id` and leaves the row unpropagated.
  - `reconcile_outbox()` calls the command.
  - Both return `None`, and neither touches `tick()`.

### Per-item flow (`ingest_item`, one `atomic(using=CATALOG)`)

1. **Prepare the input.** Build the payload (the candidate's fields as written, `series_id` as a string). Look up the venue (D5, cached per run). Compute `content_hash` over `{payload, venue_id, venue_tz}` (D7).
2. **Lock the item.** `SELECT … FOR UPDATE` the `ExtractedRecord`. If its hash is unchanged and it is resolved or rejected, return `unchanged`; the run bulk-updates `last_seen_at` at the end.
3. **Resolve the timezone.** `resolve_tz(...)`. On a `TzRejection`, a record that was resolved stays bound (`rejected_update:<reason>`). Otherwise the record is upserted as rejected (`rejected:<reason>`).
4. **Take the identity locks.** `pg_advisory_xact_lock` on each of `identity_lock_keys(candidate)`, in order.
5. **Find the bound Event.** It is the record's Event, followed along `superseded_by` to the live end (D8).
6. **Load the live set.** Non-superseded Events matching `(venue_fingerprint, start_time_utc)` or `(canonical_url, start_time_utc)`, with the empty-string keys skipped, plus each one's `bound_source_ids` from resolved records. Then call `dedup.resolve(...)`.
7. **Dispatch on the result:**
   - **`New`:** `create_event` (counted as `new`, plus `in_review` or `tz_review_pending` as applicable).
   - **`Matched` whose Event belongs to this source:** `classify_change`. The result is either `None` (`unchanged`), `apply_silent_update` (`silent_updated`), `apply_lifecycle_change` (`updated`) or `supersede_event` (`superseded`).
   - **`Matched` whose Event belongs to another source:** bind the record only (`bound_other_source`).
   - **`Ambiguous`:** an unbound record (`ambiguous`).
8. **Upsert the record.** Payload, hash, confidences, resolution, Event, `match_notes`, `last_seen_at`, and `last_changed_at` when the hash changed.

`apply_lifecycle_change` sends one UPDATE with every changed fact plus `event_version + 1`. Each further kind is a bump-only UPDATE. One `EventStateChange` is written per kind, at versions v+1..v+k, and each gets an `on_commit` enqueue.

### Decisions that need your call

| # | Question | Proposed choice | Why |
|---|---|---|---|
| **P1** | What happens to publication when the origin source updates an existing Event? The design covers creation only. | `tz_inference_confidence`, `tz_review_pending` and `publication_status` **follow each new resolution**, through the same `combine_gates`. They are not lifecycle fields, so the change is silent. A published Event can therefore drop to `in_review`, and the reverse. | The gates describe the data as it is now. Keeping a stale 1.00 after the source drops its zone would publish a guessed time. Once editorial review exists, an editorial decision has to override this; that is for the editorial intent, and I'll record it in the brief. |
| **P2** | The work item asks for a test that "exactly 0.90 publishes unflagged". | No `resolve_tz` row produces 0.90: the scores are 1.00, 0.95, 0.85 and 0.60, with caps of 0.80 and 0.65. The pipeline test therefore **injects** a `TzResolution` with confidence 0.90 by patching the pipeline's `resolve_tz` reference, and asserts published with no flag. The 0.65 and 0.80 cases come from real DST gap and fold fixtures (C1 capped). | It still proves the pipeline gates inclusively through `domain.confidence`. The 0.90 boundary itself is already pinned in `tests/domain/test_confidence.py`. |
| **P3** | Backfilling `original_start_utc` in migration 0002 | The backfill UPDATE runs between `ALTER TABLE catalog.ingestion_event DISABLE TRIGGER event_guard_update` and `ENABLE`. The migration runs as the owner role. Then `SET NOT NULL`, then `CREATE OR REPLACE` the function. | The existing trigger rejects **any** UPDATE of a superseded row, so a plain backfill fails as soon as one exists. The window is inside the migration's own transaction. |
| **P4** | Freezing time in tests: the repo has no freezegun or time-machine | Don't add a dependency. `reconcile_outbox(now=…)` takes an injectable clock. Pipeline timestamps come from `timezone.now()` and are asserted against bounds captured around the call. The ±30-day cases are driven by event times, not the wall clock. | The testing standards say "freeze time explicitly". An explicit parameter does that, and nothing else needs a frozen clock. |
| **P5** | What a state change's `before` and `after` contain | The changed facts relevant to its kind: status kinds get `status` (plus start and end if they moved); `time_moved` gets `start_utc`, `end_utc` and `start_time_tz`; `sold_out` gets `is_sold_out`; `detail_changed` gets the detail fields that changed; `superseded` gets `superseded_by` and the new `start_utc`. Values are JSON through `DjangoJSONEncoder`. | Each row reads on its own for the future consumer. Rows with identical full diffs would hide which kind meant what. |
| **P6** | Keeping the trigger-parity test true after migration 0002 | `test_event_trigger_lifecycle_columns_match_model` reads the **live** function with `pg_get_functiondef('catalog.guard_event_write'::regproc)`, instead of 0001's SQL string. | After `CREATE OR REPLACE`, 0001's text no longer describes the database. |
| **P7** | Logging | `ALLOWED_FIELDS` gains `outcome` (a slug) and `new_count`, `updated_count`, `unchanged_count`, `rejected_count`, `ambiguous_count` and `failed_count` (integers). The log line is `INFO "Ingest finished"` with `source_id`, `outcome`, the counts, `error_code` and `duration_ms`. | D17 names the counts. `outcome` is a fixed slug set and never free text. |
| **P8** | Clearing `last_error_code` after a parse failure, when a 304 follows | A 304 counts as success (D16), so it clears `last_error_code` and resets `consecutive_failures`. But if the previous run's body failed to parse, the cached validators would hide the bad body forever. So **a parse failure clears the stored `etag` and `last_modified`**, and the next fetch is a full one. | Without this, a body that fails to parse once would read as "fine, not modified" from then on. |

### Deviations from the design

None in behavior. P1, P5, P7 and P8 fill gaps the design leaves open. P2 and P3 correct facts about the code. P6 keeps an existing test honest.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/services/ingest_source.py` | The run: lock, guard, fetch, parse, item loop, close-out, audit, log |
| `backend/apps/ingestion/services/ingest_item.py` | One candidate, from resolution to write |
| `backend/apps/ingestion/services/event_writes.py` | Create, lifecycle update, supersede (D7 order), silent update |
| `backend/apps/ingestion/services/outbox.py` | The enqueue seam, `mark_propagated`, `reconcile_outbox` |
| `backend/apps/ingestion/services/slugs.py` | `mint_slug` |
| `backend/apps/ingestion/migrations/0002_ingest_pipeline.py` | The four schema changes, the backfill (P3) and the replaced guard function |
| `backend/tests/ingestion/conftest.py` | Autouse recorder for `outbox._send` |
| `backend/tests/ingestion/pipeline_support.py` | `ScriptedFetchPort`, an ICS/JSON-LD body builder, source helpers |
| `backend/tests/ingestion/test_ingest_source.py` | Run-level: guard, fetch and parse outcomes, 304, audit, log, idempotency, first ingest of each recorded fixture |
| `backend/tests/ingestion/test_ingest_lifecycle.py` | Cancel, move within 30 days, supersede, cumulative drift, reinstate, multi-kind, silent update, rollback |
| `backend/tests/ingestion/test_ingest_identity.py` | Rules (b) and (c), owner-wins, series, ambiguity, chain rebinding, the venue country fallback |
| `backend/tests/ingestion/test_ingest_tz.py` | none / 0.65 / 0.80 / 0.90 (P2), `rejected_update`, recovery after `set_venue_timezone`, all-day and overnight |
| `backend/tests/ingestion/test_ingest_concurrency.py` | `transaction=True` threads: two sources racing on one happening, a second run returning `already_running`, the lock released after an error |
| `backend/tests/ingestion/test_outbox.py` | `on_commit` enqueue, the reconcile age and batch, `mark_propagated` idempotency, the worker tasks |
| `backend/tests/ingestion/test_slugs.py` | Shape, empty-title fallback, collision retry |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/ingestion/models.py` | `Event.original_start_utc`, `EventStateChange.Kind.REINSTATED`, `ExtractedRecord.match_notes`, `Source.fetched_url` |
| `backend/domain/lifecycle.py` | `NOT_YET_STORED = frozenset()`, and the `REINSTATED` comment |
| `backend/shared/constants.py` | `EXTRACTION_CONFIDENCE_STRUCTURED`, `OUTBOX_RECONCILE_AFTER`, `OUTBOX_RECONCILE_BATCH` |
| `backend/adapters/logging/redaction.py` | The P7 fields |
| `backend/worker/tasks.py` | `propagate_state_change`, `reconcile_outbox` |
| `backend/tests/ingestion/factories.py` | `original_start_utc` on `EventFactory`, so the insert guard passes |
| `backend/tests/ingestion/test_triggers.py` | P6, plus tests for inserting with a different `original_start_utc` and for changing it |
| `backend/tests/ingestion/test_domain_parity.py` | `NOT_YET_STORED` is empty |
| `.specs-fire/standards/coding-standards.md` | The pipeline rules |
| `.specs-fire/intents/event-catalog-ingestion/brief.md` | Under "Still open": editorial decisions must override automatic re-gating (P1) |

Already done at Checkpoint 1: `ingestion-scheduling.md` now carries the reconciler tick wiring and the freshness split.

## Tests

The work item's tests, mapped to files:

| Work-item test | File |
|---|---|
| First ingest creates events (JSON-LD, RSS, Atom, ICS fixtures) | `test_ingest_source.py` |
| Re-ingest is a no-op | `test_ingest_source.py` |
| Cancelled → bump plus one state change | `test_ingest_lifecycle.py` |
| A move within 30 days keeps the ID | `test_ingest_lifecycle.py` |
| A move beyond 30 days supersedes (both Events plus the repointed record) | `test_ingest_lifecycle.py` |
| A recurring series → distinct IDs sharing `series_id` | `test_ingest_identity.py` |
| tz none rejected / 0.65 `in_review` / 0.80 flagged / 0.90 unflagged | `test_ingest_tz.py` |
| Rule (b) across two sources, rule (c) by URL | `test_ingest_identity.py` |
| An error forced after the Event write rolls back the state change | `test_ingest_lifecycle.py` (`transaction=True`) |
| Every `simulate` fetch error, 304, cross-host redirect, `final_url`, parse error | `test_ingest_source.py` |
| Advisory lock, `already_running`, nothing written to `personal` | `test_ingest_concurrency.py`, `test_ingest_source.py` |

Every new test must be able to fail. Before the test report I'll run mutation probes, planting a bug and checking a test catches it:
- the identity locks are skipped
- the version bump is merged into one +k UPDATE
- owner-wins is removed
- the hash ignores the venue tz
- the superseded chain isn't followed
- `propagated_at` is set by the placeholder
- the parse failure keeps its validators

## Technical Details

- **Gates:**
  - `make lint-backend`
  - `manage.py check`
  - `makemigrations --check --dry-run`, run after 0002 is committed in this run
  - `make coverage-backend`: ≥ 80% overall, and 100% for `domain/`, which changes in one line
- **Import contracts:**
  - `apps.ingestion.services.*` imports `domain`, `ports`, `shared`, `celery` (only in `outbox._send`) and its own app.
  - `worker.tasks` imports `apps.ingestion.services.outbox`, and no `api` module (`worker-not-api`).
- **No `personal` writes.** A test snapshots the row counts of every `personal` table before and after a full ingest.
- **Docker:** the stack is up (Postgres, Redis and Mailpit healthy). Migration 0002 is applied to the dev database by `make migrate` before the gates run.

---
*Plan approved at Checkpoint 2. Execution follows.*
