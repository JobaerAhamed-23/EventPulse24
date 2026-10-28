---
id: run-eventpulse24-014
scope: single
work_items:
  - id: source-registry-commands-admin
    intent: event-catalog-ingestion
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-28T10:52:10.609Z
completed: 2026-10-28T11:47:26.363Z
---

# Run: run-eventpulse24-014

## Scope
single (1 work item)

## Work Items
1. **source-registry-commands-admin** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/apps/ingestion/services/source_registry.py`: Source and ToS-review commands, FR-17 guard, ensure_can_ingest
- `backend/apps/ingestion/services/venue_registry.py`: register_venue, set_venue_timezone
- `backend/tests/ingestion/test_source_registry.py`: Source command tests incl. tos_status invariant and rollback
- `backend/tests/ingestion/test_venue_registry.py`: Venue command tests
- `backend/tests/ingestion/test_admin.py`: Admin through the test client
- `backend/tests/architecture/test_no_direct_writes.py`: No ORM writes in admin/API modules

## Files Modified
- `backend/apps/ingestion/admin.py`: CommandAdmin, ReadOnlyAdmin and six ModelAdmins calling commands
- `backend/config/urls.py`: Route /admin/
- `backend/config/settings.py`: Comment: admin routed
- `backend/shared/constants.py`: DEFAULT_INGESTION_CADENCE, INGESTION_CADENCE_MIN
- `backend/tests/architecture/checkers.py`: direct_write_calls, surface_files
- `backend/tests/ingestion/test_domain_parity.py`: Cadence map parity test
- `backend/tests/config/test_project.py`: admin-not-routed test replaced by admin-routed
- `.specs-fire/standards/coding-standards.md`: Source Registry, admin-as-command-client, no-direct-writes scan
- `.specs-fire/intents/event-catalog-ingestion/brief.md`: Venue renames open item
- `.specs-fire/intents/event-catalog-ingestion/work-items/ingest-pipeline-and-lifecycle.md`: ensure_can_ingest on the locked row; host-change note
- `.specs-fire/intents/event-catalog-ingestion/work-items/real-feeds-and-e2e-proof.md`: Editorial group AC

## Decisions
(none)


## Summary

- Work items completed: 1
- Files created: 6
- Files modified: 11
- Tests added: 161
- Coverage: 99.03%
- Completed: 2026-10-28T11:47:26.363Z
