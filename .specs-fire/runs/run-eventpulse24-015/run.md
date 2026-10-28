---
id: run-eventpulse24-015
scope: single
work_items:
  - id: ingest-pipeline-and-lifecycle
    intent: event-catalog-ingestion
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-28T12:00:14.861Z
completed: 2026-10-28T12:28:01.669Z
---

# Run: run-eventpulse24-015

## Scope
single (1 work item)

## Work Items
1. **ingest-pipeline-and-lifecycle** (validate) — completed


## Current Item
(all completed)

## Files Created
- `backend/apps/ingestion/services/ingest_source.py`: The run: lock, guard, fetch, parse, item loop, close-out, audit, log
- `backend/apps/ingestion/services/ingest_item.py`: One candidate: venue, tz, identity locks, resolve, write
- `backend/apps/ingestion/services/event_writes.py`: Create, lifecycle update (k statements), supersede (D7), silent update
- `backend/apps/ingestion/services/outbox.py`: Enqueue seam, mark_propagated, reconcile_outbox
- `backend/apps/ingestion/services/slugs.py`: mint_slug
- `backend/apps/ingestion/migrations/0002_ingest_pipeline.py`: original_start_utc, reinstated, match_notes, fetched_url, guard function
- `backend/tests/ingestion/test_ingest_*.py, test_outbox.py, test_slugs.py, conftest.py, pipeline_support.py, test_event_writes_support.py`: Pipeline tests and support

## Files Modified
- `backend/apps/ingestion/models.py`: Four schema additions
- `backend/domain/lifecycle.py`: NOT_YET_STORED empty
- `backend/shared/constants.py`: Structured confidence, outbox constants
- `backend/adapters/logging/redaction.py`: Run-count log fields
- `backend/worker/tasks.py`: propagate_state_change, reconcile_outbox
- `backend/tests/ingestion/factories.py`: original_start_utc
- `backend/tests/ingestion/test_triggers.py`: Live-function parity, original-start tests
- `backend/tests/domain/test_lifecycle.py`: NOT_YET_STORED empty
- `.specs-fire/standards/coding-standards.md`: Ingest pipeline rules
- `.specs-fire/intents/event-catalog-ingestion/brief.md`: Editorial override of re-gating

## Decisions
(none)


## Summary

- Work items completed: 1
- Files created: 7
- Files modified: 10
- Tests added: 86
- Coverage: 99.14%
- Completed: 2026-10-28T12:28:01.669Z
