---
id: run-eventpulse24-016
scope: single
work_items:
  - id: ingestion-scheduling
    intent: event-catalog-ingestion
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-28T12:32:06.978Z
completed: 2026-10-28T12:43:25.919Z
---

# Run: run-eventpulse24-016

## Scope
single (1 work item)

## Work Items
1. **ingestion-scheduling** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/apps/ingestion/services/scheduling.py`: claim_due_sources, flag_stale_sources, release_claim
- `backend/apps/ingestion/migrations/0003_source_ingest_claim.py`: Source.ingest_claimed_at and the due index
- `backend/config/management/commands/ingest_source.py`: ingest_source <id> [--sync]
- `backend/tests/ingestion/test_scheduling.py`: Due, claims, stale
- `backend/tests/worker/test_scheduling_tasks.py`: Tick and tasks
- `backend/tests/worker/conftest.py`: Enqueue recorder
- `backend/tests/config/test_ingest_source_command.py`: Management command

## Files Modified
- `backend/worker/tasks.py`: tick enqueues; schedule_sources and ingest_source tasks; _enqueue and _now seams
- `backend/apps/ingestion/models.py`: ingest_claimed_at, source_due_idx
- `backend/apps/ingestion/admin.py`: Claim shown read-only
- `backend/shared/constants.py`: Scheduling constants
- `.specs-fire/standards/coding-standards.md`: Scheduling rules

## Decisions
(none)


## Summary

- Work items completed: 1
- Files created: 7
- Files modified: 5
- Tests added: 45
- Coverage: 99.16%
- Completed: 2026-10-28T12:43:25.919Z
