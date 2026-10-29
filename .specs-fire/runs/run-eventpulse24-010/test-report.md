---
run: run-eventpulse24-010
work_item: catalog-data-model
intent: event-catalog-ingestion
generated: 2026-10-28
status: passed
---

# Test Report: Catalog Data Model

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit (no database) | 24 new | 0 | 0 | 100% on `shared/actor.py`, `shared/models.py` |
| Integration (real Postgres, both schemas) | 117 new | 0 | 0 | 98% `apps/ingestion/models.py`, 100% `apps/ingestion/services/audit.py` |
| **Total suite** | **579** (438 before this run + 141 new) | 0 | 0 | **97.46%** overall · **100%** `domain/` |

The unit count includes 3 tests that `tests/architecture/test_database_alias.py` generates automatically for the three new project files.

## Acceptance Criteria Validation

From `catalog-data-model.md`:

- ✅ **All seven models in `apps/ingestion/models.py`, routed to `catalog`, extend `UUIDv7Model`, and pass E001–E005.** `manage.py check` is clean. `test_ingestion_has_the_seven_designed_models` and `test_catalog_schema_holds_only_catalog_tables` pass, and `test_personal_schema_holds_no_ingestion_table` confirms none landed in `personal`.
- ✅ **`Source` fields, `tos_status` cache, no cadence default, D16 fields.** The model matches the design. `source_cadence_positive_ck` is tested.
- ✅ **`TosReview` is its own table** (`TOS_REVIEW_RECORDS`), with `reviewed_by_id` stored by value. Covered by the retention test.
- ✅ **`Venue`:** fingerprint unique constraint (`venue_fingerprint_uq` tested) and a nullable `tz`.
- ✅ **`Event` fields and constraints:** each is tested by constraint name:
  - the non-empty ID, confidence NOT NULL and range, and `start_time_local` format (3 bad shapes, plus microseconds rejected as too long)
  - end ≥ start, the superseded consistency check (both directions), and self-supersede
  - `event_version` ≥ 1, and the unique slug
- ✅ **Identity constraints (D2, D3, D22):**
  - a second `ExtractedRecord` for one source item is rejected
  - a second live Event is rejected, while a superseded Event plus a live one is allowed
  - a duplicate canonical URL is allowed
  - an empty `source_event_id` is rejected on both tables
- ✅ **`ExtractedRecord`:** one row per item. All 6 invalid resolution combinations are rejected and the 3 valid ones accepted. A NULL tz confidence is allowed.
- ✅ **`EventStateChange` append-only (three layers) and the D23 conditional update:**
  - triggers: `test_triggers.py`, raw SQL
  - grants: `test_grants.py`, which asserts `InsufficientPrivilege` exactly
  - Python guards: `test_guards.py`
  - the D23 retry returns 0 and raises nothing
- ✅ **Event guard:** these cases are each tested with raw SQL:
  - superseded is terminal
  - a version decrease or a jump of +2 is rejected
  - each of the 7 lifecycle columns needs +1
  - a non-lifecycle change at the same version is allowed
  - an insert at a version other than 1, or as superseded, is rejected
  - the trigger's column list matches `Event.LIFECYCLE_FIELDS`
- ✅ **Supersede order (D7):** the specified order succeeds, and the record is repointed to the new Event. Inserting the new Event first fails on `event_live_source_item_uq`.
- ✅ **Audit log:** abstract `AuditEntry`, `Actor`, and an append-only `IngestionAuditEntry`. The actor check rejects all 4 invalid combinations on both actor tables. `write_audit` raises with no transaction open, and also with only a `PERSONAL` transaction open (`transaction=True`).
- ✅ **Constants:** `TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH = 0.90` and `SERIES_ID_NAMESPACE` are pinned and tested. The `series_id` golden value is tested.
- ✅ **Retention categories per model:** `test_ingestion_retention_categories`.
- ✅ **No catalog FK to `User`/`ContentType`:** E002 is clean. Every FK in the app is `PROTECT` (meta-test).
- ✅ **A single forward-only `0001_initial`, applied cleanly; `personal` untouched.** Applied, reversed to zero, and re-applied on the dev database (see below). The migration's privilege assertion is proven to raise when a REVOKE is missing.
- ✅ **Factories:** deterministic (seeded Faker, sequences, UTC plus IANA, no microseconds), with `CatalogFactory` on the `CATALOG` alias.

## Tests Written

### Unit Tests

- `tests/shared/test_actor.py` (14): constructors, 6 invalid combinations, and 6 bad system labels (email, a capitalized name, a leading digit, too short, a hyphen, a space)
- `tests/shared/test_ids.py` (+4): `series_id` golden value, determinism, sensitivity to key and source, and a ValueError on an empty key
- `tests/shared/test_constants.py` (+1, plus 1 assertion in an existing test): the new constants
- `tests/architecture/test_stdlib_only.py` (+2): `shared/actor.py` imports no project module, and the check catches a planted project import

### Integration Tests

- `tests/ingestion/test_models.py` (52): constraints by name, supersede order, resolution and actor checks, PROTECT and retention meta-tests
- `tests/ingestion/test_triggers.py` (25): append-only and Event-guard triggers via raw SQL, the purge setting, and the lifecycle-column parity check
- `tests/ingestion/test_guards.py` (26): model (including `force_update` on a freshly built instance), QuerySet, related-manager and base-manager guards, and the D23 conditional update
- `tests/ingestion/test_grants.py` (8): `ep_catalog` denials (exactly `InsufficientPrivilege`), the allowed `propagated_at` update, INSERT/SELECT privileges, and the migration's privilege assertion
- `tests/ingestion/test_audit.py` (5): `write_audit` inside a catalog transaction, with no transaction, with only a `PERSONAL` transaction, and a positional call
- `tests/wall/test_schema_placement.py` (+1, with one existing test extended): the catalog schema now holds the seven `ingestion_*` tables, and none are in `personal`

## Test Commands

```bash
# Run all tests
make test-backend

# Run with coverage (both gates: ≥80% overall, 100% domain/)
make coverage-backend
```

## Coverage Details

| Module | Lines |
|--------|-------|
| `apps/ingestion/models.py` | 98% (3 `__str__` methods not exercised) |
| `apps/ingestion/services/audit.py` | 100% |
| `shared/actor.py` | 100% |
| `shared/models.py` | 100% |
| `shared/ids.py` | 97% (line 28 is the pre-existing fork hook, unchanged) |
| `domain/` | 100% |
| **Total** | **97.46%** |

## Other Gates

- `make lint-backend`: ruff check and format clean; import-linter 12 contracts kept, 0 broken
- `manage.py check`: no issues
- `makemigrations --check --dry-run`: no changes detected
- **Migration round trip** on the dev database:
  - `migrate`: 7 tables in `catalog`, 4 triggers, 2 functions, and `ep_catalog` limited to INSERT/SELECT plus UPDATE on `propagated_at`
  - `migrate ingestion zero`: 0 tables, 0 functions and 0 triggers left
  - `migrate` again: applied cleanly

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| Django wraps PL/pgSQL `RAISE EXCEPTION` (P0001) as `ProgrammingError`, not `InternalError`, so the test catches `DatabaseError` and asserts the psycopg cause | Low | Fixed in test |
| `ExtractedRecordFactory` derived `source` from `event`, which fails when `event=None` | Low | Fixed: `factory.Maybe` |
| `factory.random` must be imported explicitly | Low | Fixed |
| Docker Desktop was stopped at run start; it was started (`systemctl --user start docker-desktop`) and the stack brought up with `make up` | Info | Resolved |

## Ready for Completion

- [x] All tests passing (579/579, re-run after the code-review fixes)
- [x] Coverage target met (80% overall: 97.46%; 100% `domain/`)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-010*
