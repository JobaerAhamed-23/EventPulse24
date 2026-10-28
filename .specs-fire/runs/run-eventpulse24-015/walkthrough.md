---
run: run-eventpulse24-015
work_item: ingest-pipeline-and-lifecycle
intent: event-catalog-ingestion
generated: 2026-10-28
mode: validate
---

# Implementation Walkthrough: Ingest Pipeline & Event Lifecycle

## Summary

`ingest_source(source_id)` turns a registered Source into catalog rows. It takes a per-source run lock and re-checks FR-13/FR-17 on a locked row. It fetches with the stored validators, parses, then resolves and writes each candidate in its own transaction, under the identity advisory locks. It closes with the source's fetch state, the last-seen marks and one audit row of counts.

The pieces it maintains:
- **Lifecycle:** changes bump `event_version` once per kind, each with an `EventStateChange` and a post-commit propagation enqueue. A move beyond 30 days from the **original** start supersedes the Event in the D7 order.
- **Silent updates:** title, description and URL changes, and the publication gates, update the Event with no version bump.
- **The outbox:** a placeholder consumer and a reconciler (AD-17). Wiring the reconciler into the tick is left to `ingestion-scheduling`.

Nothing is written to `personal`.

## Structure Overview

```
ingest_source ─ run lock (session advisory) ─ guard on locked row ─ fetch ─ parse
   │ for each candidate:  ingest_item  (own atomic)
   │     venue registry lookup ─ content hash ─ unchanged? ─ resolve_tz ─ gates
   │     identity advisory locks ─ bound Event (chain-follow) ─ live set ─ dedup.resolve
   │     └─ event_writes: create │ lifecycle (k statements) │ supersede (D7) │ silent
   │                       └─ EventStateChange ─ on_commit(robust) ─ outbox._send ─► worker
   └ _close: source state · bulk last_seen · write_audit(counts) · "Ingest finished" log
worker.tasks: propagate_state_change (no-op, leaves propagated_at NULL) · reconcile_outbox
```

## Architecture

### Pattern Used

A command service over pure domain decisions. Every judgement is made by `domain.timezones`, `domain.confidence`, `domain.dedup` and `domain.lifecycle`. The services look up rows, take locks and write.

The resolve-and-write stage (`ingest_item`) takes a `ParsedCandidate`, so the later LLM/HTML path is just another producer of candidates.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `apps/ingestion/services/ingest_source.py` | The run: `IngestReport`, `source_run_key`, lock, guard, fetch, parse, item loop, `_close` |
| `apps/ingestion/services/ingest_item.py` | `IngestRun`, the venue lookup, payload and hash, the tz outcome, locks, live set, dispatch, record upsert |
| `apps/ingestion/services/event_writes.py` | `IncomingEvent`, `facts_of`, `create_event` (slug retry), `apply_lifecycle_change`, `apply_silent_update`, `supersede_event` |
| `apps/ingestion/services/outbox.py` | `_send` seam, `enqueue_propagation`, `mark_propagated`, `reconcile_outbox` |
| `apps/ingestion/services/slugs.py` | `mint_slug` |
| `apps/ingestion/migrations/0002_ingest_pipeline.py` | `original_start_utc` (backfilled with the guard briefly disabled), `match_notes`, `fetched_url`, `reinstated`, the replaced `guard_event_write` |
| `tests/ingestion/test_ingest_{source,lifecycle,identity,tz,concurrency}.py`, `test_outbox.py`, `test_slugs.py` | 77 tests |
| `tests/ingestion/conftest.py`, `pipeline_support.py`, `event_writes_support.py` | The autouse `sent_jobs` recorder, `ScriptedFetchPort`, ICS builders, an `IncomingEvent` builder |

### Modified

| File | Changes |
|------|---------|
| `apps/ingestion/models.py` | The four schema additions |
| `domain/lifecycle.py` | `NOT_YET_STORED` is empty |
| `shared/constants.py` | `EXTRACTION_CONFIDENCE_STRUCTURED`, `OUTBOX_RECONCILE_AFTER`, `OUTBOX_RECONCILE_BATCH` |
| `adapters/logging/redaction.py` | `outcome` plus six count fields |
| `worker/tasks.py` | Two tasks; `tick()` is untouched |
| `tests/ingestion/factories.py`, `test_triggers.py`, `tests/domain/test_lifecycle.py` | `original_start_utc`; the live-function parity test (P6); the `NOT_YET_STORED` pin |
| `coding-standards.md`, `brief.md` | The pipeline rules; editorial override of re-gating, as an open item |

## Domain Model

- **`Event.original_start_utc`**: the start an Event was created with. The trigger sets it equal to the start on insert and rejects any later change.
- **`EventStateChange.Kind.REINSTATED`**: an un-cancel, or postponed → scheduled at the same start.
- **`ExtractedRecord.match_notes`**: `{"rule", "review_signals"}` or `{"ambiguous"}`, kept for the review queue.
- **`Source.fetched_url`**: the last final URL, which is the parse base.
- **Value objects:** `IncomingEvent`, `IngestRun` and `IngestReport`.

## Key Implementation Details

### 1. k kinds take k statements (D9)

The trigger allows `event_version` to stay or rise by 1 per statement. `apply_lifecycle_change` writes every fact at v+1, then one bump-only UPDATE for each further kind. A state change of version v+i is recorded for each kind, with the facts that kind is about (P5).

### 2. Owner-wins, with the binding kept (D8)

Only `Event.source` updates an Event's facts. Other sources' items are bound, and their disagreement stays in their payload. A record bound to a superseded Event follows `superseded_by` to the live end.

### 3. The hash includes the resolution inputs (D7)

`content_hash` covers the payload **and** the matched venue's ID and tz. An editor adding a venue tz therefore re-resolves rejected items on the next run, with no forced re-ingest. Ambiguous items are always re-resolved.

### 4. Concurrency

- **Run level:** `pg_try_advisory_lock(source_run_key)`. A second run gets `already_running`.
- **Item level:** `pg_advisory_xact_lock` for each identity key, in sorted order, with one item per transaction.
- **The race test** puts a barrier in `_live_events`. Without the locks, both items reach it, see nothing, and create two Events (a probe confirmed this). With them, the second waits and binds.

## Security Considerations

| Concern | Approach |
|---------|----------|
| FR-17 crawl and paused sources | `ensure_can_ingest` runs on the locked, fresh row before any fetch. A refusal writes nothing. |
| Untrusted source content (AD-9) | Plain text in the payload and the Event, never rendered. The pipeline never creates venues, so a feed can't seed the timezone registry. |
| A moved source (cross-host redirect) | Never followed. It is stored as `source_moved`, and re-registration resets its ToS review. |
| Log redaction (AD-13) | Counts, IDs and an outcome slug only. A test asserts a title never reaches the JSON output. |
| The `personal` wall (AD-3) | A test compares every personal model's row count before and after a full ingest. |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| A re-ingest of an unchanged feed should be cheap | A hash comparison per item with no lock or transaction, then one bulk `last_seen_at` UPDATE each for records and Events at close. |
| Identity lookups | `event_rule_b_idx (venue_fingerprint, start_time_utc)` and `event_canonical_url_idx`. The live set is only the rows matching the candidate's keys. |
| Venue lookups | Cached per run, by name, city and country. The registry's countries are read once per run. |
| No long transactions | Nothing is held open across the network fetch. Each item commits on its own. |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| D1–D19 | As in `ingest-pipeline-and-lifecycle-design.md` | Approved at Checkpoint 1 |
| P1 | The gates follow every new resolution, silently | A stale 1.00 would publish a guessed time. The editorial override is an open item in the brief. |
| P2 | Exactly 0.90 is tested by injection | No `resolve_tz` row produces 0.90. The domain test pins the boundary. |
| P3 | The backfill runs with `event_guard_update` disabled | The trigger rejects any UPDATE of a superseded row. |
| P4 | An injectable `now` instead of a time library | Nothing else needs a frozen clock. |
| P5 | Each state change carries its kind's facts | Each row reads on its own. |
| P6 | The parity test reads the live function | 0002 replaced 0001's text. |
| P7 | `outcome` and the six count fields allowlisted | IDs, counts and slugs only. |
| P8 | A parse failure drops the stored validators | Otherwise a bad body would read as "not modified" from then on. |
| F1 (review) | `rejected_update` advances `last_seen_at` | The item was seen. |
| F2 (review) | `on_commit(..., robust=True)` | A broker outage must not miscount a committed item or skip its other enqueues. |

## Deviations from Plan

- **The code-review fixes F1 and F2.** You approved both. Each has a regression test, and reverting either fix makes its test fail.
- **One helper not in the plan:** `tests/ingestion/event_writes_support.py` (an `IncomingEvent` builder for the slug-collision tests). It is test-only.
- **The design's two departures are implemented as approved.** Title, description and URL changes are silent. The reconciler's tick wiring is in `ingestion-scheduling`'s ACs, recorded at Checkpoint 1.

## Dependencies Added

None. Celery was already a dependency; the outbox reaches it through `celery.current_app`.

## How to Verify

1. **Run the pipeline tests**
   ```bash
   cd backend && uv run pytest -q tests/ingestion
   ```
   Expected: all pass, about 600 tests, including the concurrency tests (they need about 4 seconds).

2. **Run all the gates**
   ```bash
   make lint-backend && make manage ARGS="check" && make manage ARGS="makemigrations --check --dry-run" && make coverage-backend
   ```
   Expected: 13 contracts kept, no issues, no changes, 1562 passed, 99.14% overall, 100% `domain/`.

3. **Ingest the recorded ICS fixture into the dev database by hand.** This uses the fake fetch adapter and makes no network calls.
   ```bash
   make manage ARGS='shell -c "from datetime import timedelta; from apps.ingestion.services.source_registry import register_source; from apps.ingestion.services.ingest_source import ingest_source; from adapters.crawl.fake import FakeFetchAdapter; from shared.actor import Actor; s = register_source(actor=Actor.system(\"manual_check\"), name=\"Fixture calendar\", source_type=\"other\", url=\"https://fixtures.example.test/calendar.ics\", acquisition_method=\"ics\", tz_coverage=\"partial\"); print(ingest_source(s.id, fetch_port=FakeFetchAdapter()))"'
   ```
   Expected: `outcome='ok'` with `new: 6`, `rejected:tz_unresolvable: 2`, `tz_review_pending: 2` and `skipped:no_event_start: 1`. The Events show in `/admin/` under Events.

   Because registration checks for duplicate feeds, the command can be run once per database. Pause the source afterwards if you don't want it scheduled later.

## Test Coverage

- **Tests added:** 86 (1476 → 1562). That is:
  - 77 in the new pipeline, outbox and slug files
  - 3 new trigger tests
  - 6 alias-scan checks generated for the new modules
- **Coverage:** 99.14% overall. All five new service modules are at 100%, and `domain/` is at 100%.
- **Mutation probes:** 14 planted bugs, each caught (12 from the plan plus the 2 review fixes).
- **Status:** all passing.

## Ready for Review

- [x] All acceptance criteria met, including the handed-on ones
- [x] Tests passing, and each key test shown able to fail
- [x] Code-review findings fixed with your approval
- [x] Standards, brief and later items updated
- [x] Developer notes captured

## Developer Notes

- **Never batch candidates into one transaction.** The identity locks are only deadlock-free one item at a time (D4).
- **Pass `original_start_utc` to `classify_change`, never the current start.** The drift test catches the mistake.
- **New lifecycle columns** must go in `Event.LIFECYCLE_FIELDS`, `EventFacts`/`LIFECYCLE_FACTS`, *and* the trigger, in one migration. The parity tests read the live function.
- **Testing the outbox:** the autouse `sent_jobs` fixture replaces `outbox._send`. Use `django_capture_on_commit_callbacks(using=CATALOG, execute=True)` to see enqueues in non-transactional tests.
- **The `REJECT` gate is unhandled on purpose** (`_PUBLICATION` has no `REJECT` key). The LLM extraction path must decide what a rejected extraction writes.
- **`ingestion-scheduling` should call `ingest_source`** from its Celery task and management command, and wire `worker.tasks.reconcile_outbox` into the tick without making `tick()` itself touch the database.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-015*
