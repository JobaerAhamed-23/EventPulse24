# Code Review Report

**Run**: run-eventpulse24-010
**Intent**: event-catalog-ingestion
**Reviewed**: 2026-10-28
**Files Reviewed**: 24 (12 created, 12 modified)

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 0 | 1 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 1 | 0 |
| Testing | 0 | 1 | 0 |
| **Total** | **0** | **3** | **0** |

**Tests Status**: Passing (579/579 after the applied suggestions)

---

## Files Reviewed

**Production code:**
- `backend/apps/ingestion/models.py` (modified)
- `backend/apps/ingestion/migrations/0001_initial.py` (created)
- `backend/apps/ingestion/services/audit.py` (created)
- `backend/shared/actor.py` (created)
- `backend/shared/models.py` (modified)
- `backend/shared/constants.py` (modified)
- `backend/shared/ids.py` (modified)

**Tests:**
- `backend/tests/roles.py` (created)
- `backend/tests/ingestion/` (created): `factories.py`, `test_models.py`, `test_triggers.py`, `test_grants.py`, `test_guards.py`, `test_audit.py`
- `backend/tests/shared/test_actor.py` (created)
- Modified: `backend/tests/shared/test_ids.py`, `test_constants.py`, `tests/wall/test_schema_placement.py`, `test_role_isolation.py`, `tests/architecture/checkers.py`, `test_stdlib_only.py`

**Configuration:** `backend/pyproject.toml`, `backend/uv.lock` (modified)

---

## Auto-Fixed Issues

No auto-fixes applied. `ruff check` and `ruff format` were already clean, and there are no unused imports, debug statements, or formatting issues.

---

## Suggestions (all 3 approved by the user and applied)

### 1. [Architecture] `save(force_update=True)` on a fresh instance skips the Python append-only guard

- **File**: `backend/shared/models.py` (`AppendOnlyModel.save`)
- **Finding**: the guard only checks `not self._state.adding`. A newly built instance with an existing primary key, saved with `force_update=True`, takes Django's UPDATE path with no Python check.
- **Verified by a probe**: the database trigger still rejects it (`IntegrityError` caused by `RestrictViolation`), so no data is at risk. Only the fail-fast layer is missing.
- **Change**: treat `force_update=True` like an existing row, and add a test.
- **Risk**: Low
- **Applied**: `AppendOnlyModel.save` now also guards `force_update=True`. Test: `test_state_change_force_update_of_fresh_instance_raises`.

### 2. [Code Quality] Actor columns are defined twice

- **Files**: `backend/shared/models.py` (`AuditEntry`) and `backend/apps/ingestion/models.py` (`EventStateChange`)
- **Finding**: `actor_kind`, `actor_id` and `actor_label` are declared identically in both, alongside `actor_check()`.
- **Change**: move them into an abstract `ActorColumns` base in `shared/models.py`, used by both. Field definitions are unchanged, so there is no schema change; `makemigrations --check` confirms it.
- **Risk**: Low
- **Applied**: `shared.models.ActorColumns` is used by `AuditEntry` and `EventStateChange`. `makemigrations --check` reports no changes.

### 3. [Testing] The D7 reverse-order test duplicates another test

- **File**: `backend/tests/ingestion/test_models.py`
- **Finding**: `test_supersede_inserting_new_event_first_rejected` has the same body as `test_event_second_live_event_for_same_source_item_rejected`.
- **Change**: make it run the real reverse order inside one transaction (insert the new Event with its minted ID, *then* try to retire the old one). That shows step 3 before step 2 fails on the non-deferrable index, which is what D7 claims.
- **Risk**: Low
- **Applied**: renamed to `test_supersede_in_reverse_order_rejected_even_inside_one_transaction`. It also asserts the old Event is still `scheduled` afterwards.

**Re-run after applying:** ruff clean; import-linter 12 kept; `manage.py makemigrations --check` no changes; 579 passed; coverage 97.46% overall, 100% `domain/`.

---

## Notes (no action)

- **`Event.canonical_url` index:** a btree on `varchar(2048)` can exceed the roughly 2.7 KB index row limit for very long URLs. This is already deferred to `ingest-pipeline-and-lifecycle` (normalize and cap, or a hashed lookup column).
- **`Source.url` has no unique constraint,** so duplicate sources are possible. This belongs to `source-registry-commands-admin`, which has validation in its commands.
- **Coverage:** three `__str__` methods are not covered (`models.py` at 98%). Left as is.
