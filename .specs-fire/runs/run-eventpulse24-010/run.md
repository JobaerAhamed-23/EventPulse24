---
id: run-eventpulse24-010
scope: single
work_items:
  - id: catalog-data-model
    intent: event-catalog-ingestion
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-28T07:03:24.721Z
completed: 2026-10-28T08:06:49.432Z
---

# Run: run-eventpulse24-010

## Scope
single (1 work item)

## Work Items
1. **catalog-data-model** (validate) — completed


## Current Item
(all completed)

## Files Created
- `backend/apps/ingestion/migrations/0001_initial.py`: Seven catalog tables, constraints, indexes; append-only and Event-guard triggers; ep_catalog REVOKE/GRANT with a privilege assertion
- `backend/apps/ingestion/services/audit.py`: write_audit(*, actor, action, target_type, target_id, details) and AuditOutsideCatalogTransaction
- `backend/shared/actor.py`: Actor value object (user id or system job-name label), stdlib only
- `backend/tests/roles.py`: run_as / expect_denied helpers for runtime-role privilege tests
- `backend/tests/ingestion/factories.py`: Deterministic CatalogFactory-based factories and make_superseded_pair
- `backend/tests/ingestion/test_models.py`: Constraints by name, D7 supersede order, PROTECT and retention meta-tests
- `backend/tests/ingestion/test_triggers.py`: Raw-SQL tests of the append-only and Event-guard triggers
- `backend/tests/ingestion/test_grants.py`: ep_catalog privilege tests and the migration's privilege assertion
- `backend/tests/ingestion/test_guards.py`: Python model/QuerySet/related-manager append-only guards and D23 conditional update
- `backend/tests/ingestion/test_audit.py`: write_audit transaction requirement and actor storage
- `backend/tests/ingestion/__init__.py`: Package marker
- `backend/tests/shared/test_actor.py`: Actor validation

## Files Modified
- `backend/apps/ingestion/models.py`: Source, TosReview, Venue, Event, ExtractedRecord, EventStateChange, IngestionAuditEntry
- `backend/shared/models.py`: AppendOnlyViolation/QuerySet/Model, ActorColumns, actor_check(), abstract AuditEntry
- `backend/shared/constants.py`: TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH (0.90), SERIES_ID_NAMESPACE
- `backend/shared/ids.py`: series_id(source_id, series_key) UUIDv5 helper
- `backend/tests/wall/test_schema_placement.py`: Catalog schema now expects the seven ingestion tables; none in personal
- `backend/tests/wall/test_role_isolation.py`: Imports run_as from tests/roles.py
- `backend/tests/architecture/checkers.py`: SHARED_STDLIB_ONLY_FILES and an allowed-modules parameter
- `backend/tests/architecture/test_stdlib_only.py`: Checks shared/actor.py imports no project module
- `backend/tests/shared/test_ids.py`: series_id golden-value tests
- `backend/tests/shared/test_constants.py`: New constants asserted
- `backend/pyproject.toml`: Dev dependency factory-boy==3.3.3
- `backend/uv.lock`: Locked factory-boy 3.3.3 and faker 40.43.0
- `.specs-fire/standards/coding-standards.md`: Actor, write_audit, three-layer append-only convention, outbox update, Event versioning, series ids
- `.specs-fire/standards/testing-standards.md`: Test location, role helpers, raw-SQL trigger tests, CatalogFactory
- `.specs-fire/standards/tech-stack.md`: factory-boy recorded
- `.specs-fire/intents/event-catalog-ingestion/work-items/catalog-data-model-design.md`: Amendments at Checkpoint 2

## Decisions
- **Append-only enforcement**: Grants + triggers + Python guards (shared.models.AppendOnlyModel) (Grants bind the runtime role, triggers bind every role, Python fails fast; reusable by every app's audit table)
- **Event guard scope**: BEFORE INSERT and UPDATE; version stays or rises by 1; lifecycle change needs +1 (Blocks forged inserts and stale overwrites (plan review #17))
- **Migration privilege safety**: DO-block assertion after REVOKE/GRANT; reverse drops triggers and functions (A non-owner REVOKE only warns; zero-and-reapply proven clean)
- **Test location**: backend/tests/<module>/ (tests/ingestion/) (Matches the repo; testing-standards corrected)
- **Branch name**: Keep event-catalog-ingestion (User decision: exception to constitution PROD-NNNN-<slug>, same as setup-specsmd)
- **Review suggestions**: All 3 applied (force_update guard, ActorColumns, real D7 reverse-order test) (User approved; no schema change)


## Summary

- Work items completed: 1
- Files created: 12
- Files modified: 16
- Tests added: 141
- Coverage: 97.46%
- Completed: 2026-10-28T08:06:49.432Z
