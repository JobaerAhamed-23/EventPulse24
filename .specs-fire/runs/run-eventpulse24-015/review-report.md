# Code Review Report

**Run**: run-eventpulse24-015
**Intent**: event-catalog-ingestion
**Reviewed**: 2026-10-28
**Files Reviewed**: 27

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 2 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture / Reliability | 0 | 1 | 0 |
| Correctness | 0 | 1 | 0 |
| Performance | 1 | 0 | 0 |
| **Total** | **3** | **2** | **0** |

**Tests Status**: Passing. After the fixes: 1562 passed, 99.14% overall, 100% `domain/`, 13 import contracts kept, `check` and `makemigrations --check` clean.

---

## Files Reviewed

**Created:**
- `backend/apps/ingestion/services/ingest_source.py`, `ingest_item.py`, `event_writes.py`, `outbox.py`, `slugs.py`
- `backend/apps/ingestion/migrations/0002_ingest_pipeline.py`
- the tests: `tests/ingestion/conftest.py`, `pipeline_support.py`, `event_writes_support.py`, and `test_ingest_{source,lifecycle,identity,tz,concurrency}.py`, `test_outbox.py`, `test_slugs.py`

**Modified:**
- code: `apps/ingestion/models.py`, `domain/lifecycle.py`, `shared/constants.py`, `adapters/logging/redaction.py`, `worker/tasks.py`
- tests: `tests/ingestion/factories.py`, `test_triggers.py`, `tests/domain/test_lifecycle.py`
- docs: `coding-standards.md`, `brief.md`

---

## Auto-Fixed Issues

1. **[Code Quality] An `__import__("zoneinfo")` hack and a tuple assignment in a test.** In `test_ingest_source.py`, replaced with a plain import and two statements.
2. **[Code Quality] Garbage left in a list comprehension.** In `test_ingest_concurrency.py`, a leftover `... if False else ...` was replaced with a named helper. It was caught before the test ever ran.
3. **[Performance] `registry_countries` read every venue's country.** It used `set(rows)` and now uses `rows.distinct()`. The behavior is the same.

Ruff format re-wrapped five test files. There is no behavior change in any of these.

---

## Applied Suggestions (approved by the user)

### F2. [Reliability / AD-17] A broker failure after commit was miscounted, and it skipped the item's other enqueues

- **Found by:** reading `event_writes._record_change`. Django runs `on_commit` callbacks when the item's `atomic` exits, so an exception from `send_task` propagates out of `ingest_item` *after* the commit.
- **Probe:** `_send` raising `ConnectionError`, with `transaction=True`.
  - The run reported `{'failed:ConnectionError': 1}`, but the Event was at version 3 with 2 committed state changes.
  - Only the first callback ran; the second enqueue was never attempted.
- **Fix:** `transaction.on_commit(..., using=CATALOG, robust=True)`. Django logs the failure through the `django.db.backends.base` logger; our formatter reduces the exception to its type. Every later callback still runs, and the 5-minute reconciler re-sends what was lost.
- **Test:** `test_broker_failure_after_commit_neither_fails_the_item_nor_skips_other_enqueues` asserts `{"updated": 1}`, versions [2, 3] committed, and both enqueues attempted. Reverting the fix fails it.

### F1. [Correctness] A `rejected_update` item didn't advance `last_seen_at`

- **Probe:** `ADVANCED False` after a resolved item lost its zone.
- **Impact:** a later "disappeared from feed" job keyed on `last_seen_at` would treat a still-listed item as gone.
- **Fix:** update only the record's `last_seen_at`. The binding and the Event stay untouched (D13).
- **Test:** `test_resolved_item_that_loses_its_zone_keeps_its_event` now asserts the advance. Reverting the fix fails it.

---

## Checked and found fine (no change)

| Concern | Result |
|---|---|
| A secondary source binding to an Event while its origin supersedes it at the same time | Serialized by the row lock both take: the secondary's `select_for_update` and the origin's retiring UPDATE. If the origin wins, the secondary binds to the now-superseded row and rebinds on its next ingest (chain-following, tested). Nothing crashes. |
| Reading the `ExtractedRecord` outside the item transaction | Only the source's own runs write its records, and the run lock (D2) allows one at a time. Probed: removing the run lock is caught. |
| `rejected` records skipped while their hash is unchanged | They're deterministic for the same inputs, and the hash includes the venue tz, so a registry fix re-resolves them (tested). |
| A `REJECT` gate for structured sources | Unreachable at extraction 1.00. `_PUBLICATION` has no `REJECT` key on purpose: the LLM path must add its handling. |
| Untrusted content (AD-9) | Text is stored plain in the payload and the Event and never rendered. The log line was tested to contain no title text. |
| Migration 0002 on a database with superseded rows | The backfill runs with `event_guard_update` disabled inside the migration's transaction (plan P3). It was applied to the dev database. |

## Known limitations (accepted in the design)

- **Owner-wins** means a cancellation reported only by a secondary source is kept as evidence (`payload.status`, counts) and not applied. Cross-source authority belongs to a later intent.
- **The reconciler re-sends unpropagated rows** every 5 minutes, up to 500, until the real consumer exists. It is wired to the tick in `ingestion-scheduling`.
