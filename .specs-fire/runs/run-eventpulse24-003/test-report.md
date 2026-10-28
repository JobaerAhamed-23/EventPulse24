---
run: run-eventpulse24-003
work_item: schema-router-spike
intent: project-scaffold
generated: 2026-10-27
status: passed
---

# Test Report: AD-3 Schema Router Spike

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit (config: env, databases, router, checks, project) | 51 | 0 | 0 | n/a |
| Integration (wall tests against the migrated test DB) | 17 | 0 | 0 | n/a |
| Other (API, domain guard) | 4 | 0 | 0 | n/a |
| **Total (pytest)** | **72** | 0 | 0 | n/a |
| Mutation checks (deliberate breakage caught) | 9/9 | 0 | 0 | n/a |
| Dev-DB integration steps | 9 | 0 | 0 | n/a |

Coverage measurement arrives with `ci-pipeline`.

## Acceptance Criteria Validation

- ✅ **`DATABASES` has `default` (= `personal` schema) and `catalog` entries, each with its own role and `search_path`.** `test_databases.py` (runtime users, owner users, search_path per alias). Live: the app connects as `ep_personal` / `ep_catalog`.
- ✅ **Router maps each app to its schema for read/write/relation/migrate.** `test_router.py` (11 tests), including fail-closed for unmapped apps and relation by model map.
- ✅ **`allow_relation` False across the two databases; Django's own tables have a documented home.** Framework tables + `identity_user` in `personal`, `catalog` holds only its own `django_migrations` (`test_schema_placement.py`; live `information_schema` on the dev DB).
- ✅ **`migrate --database=catalog` and `--database=default` each create tables only in their own schema.** Dev DB and test DB both verified; `public` has no tables.
- ✅ **Test: a cross-schema FK is refused (ORM / system check), and a cross-schema join can't be expressed.**
  - `eventpulse.E002` for FK and M2M (isolated models)
  - in-memory assignment refused by the router
  - explicit `.using(CATALOG)` subquery → `ValueError`
  - plain subquery → `ProgrammingError`
- ✅ **Test: `ep_catalog` can't read `personal.*` and vice versa.** Plus both runtime roles denied `CREATE TABLE` in their own schema and in `public`, and positive SELECT/INSERT on their own tables (`test_role_isolation.py`, 8 tests).
- ✅ **Test: `transaction.atomic(using=…)` is per-schema.** `transaction=True`: a personal write inside a raised catalog `atomic` survives; distinct `pg_backend_pid()` per alias.
- ✅ **Spike models are test-only.** `tests/wall/{catalog_probe,personal_probe}`, installed only by `config.settings_test`.
- ✅ **Findings recorded and raised against the spine.** OQ-8 added; Django 6.1 findings in the walkthrough.

## Tests Written

### Unit Tests

- `tests/config/test_env.py` (+3): `DJANGO_DB_ROLE` isolated; owner URL optional at runtime, required (`ValidationError`) at owner, accepted when given
- `tests/config/test_databases.py` (11): role selection, role from env, `search_path` per alias, URL query options (`sslmode`) kept alongside `search_path` (code review S1), per-alias `ATOMIC_REQUESTS=False`, identical TEST settings, owner without URL → `ImproperlyConfigured`
- `tests/config/test_router.py` (11): mapped read/write, unmapped read/write raise, `allow_migrate` own alias only, unmapped False, relation same/cross/unmapped, ignores `_state.db`
- `tests/config/test_checks.py` (8): E002 FK + M2M, same-alias none, in-memory router refusal, E001, no-models app ignored, project routing complete, wrapper honours `app_configs`
- `tests/config/test_project.py` (+2): `config` app installed, `AUTH_USER_MODEL`

### Integration Tests

- `tests/wall/test_schema_placement.py` (4): personal/catalog/public table sets; per-alias `current_schema()` and `django_migrations`
- `tests/wall/test_orm_wall.py` (3): explicit-using subquery `ValueError`, plain subquery `ProgrammingError` (raises outside `atomic`), same-alias FK save
- `tests/wall/test_role_isolation.py` (8): allowed own-schema DML, denied cross-schema reads, denied DDL (own schema + public)
- `tests/wall/test_transactions.py` (2): per-schema rollback, distinct backend PIDs

### Dev-DB integration (in the design's order)

1. `make db-check` **before** `db-init` → FAIL on template + `CREATEDB` (correctly detected)
2. `make db-init` twice → idempotent (only "already exists" notices); `db-check` green
3. Runtime-role `migrate --database=default` and `--database=catalog` on the **unmigrated** DB → `MigrationSchemaMissing: … permission denied for schema personal/catalog`
4. `make migrate` (owner) → applied; second run applies nothing
5. `information_schema`: personal = framework + `identity_user`; catalog = `django_migrations` only; public = none. Table owner `ep_owner`; `ep_personal` has exactly SELECT/INSERT/UPDATE/DELETE
6. App as runtime roles: ORM read works, `showmigrations` works (connected as `ep_personal` / `ep_catalog`)
7. **Partial runs:** each wall file alone, plus a non-wall + single-wall mix → all green, **dev DB probe tables: 0**, no leftover test DBs
8. **Guard:** a settings variant putting `catalog` on another test DB → pytest exit code 1, "Refusing to migrate … {'default': 'test_eventpulse24', 'catalog': 'test_eventpulse24_other'}", test DBs dropped, dev DB untouched
9. **Fresh machine path:** `make reset-db FORCE=1` (first-boot init) → `db-check` ready → `make migrate` (38 migrations) → 70 passed (72 after code review S1, re-run)

### Mutation checks (each reverted after)

| Deliberate break | Result |
|---|---|
| `allow_relation` always True | 4 failed |
| `allow_relation` trusts `_state.db` | 2 failed |
| unmapped `db_for_read` falls back to default | 1 failed |
| E002 disabled | 2 failed |
| E001 disabled | 2 failed |
| check wrapper ignores passed `app_configs` | 1 failed |
| `search_path` option dropped | 9 failed |
| `ATOMIC_REQUESTS` True | 4 failed |
| `OPTIONS` replaced instead of merged (pre-S1 code) | 2 failed |

## Test Commands

```bash
make db-init && make db-check
make migrate
make test-backend
make lint-backend
make manage ARGS="check"
```

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| Single-file wall runs errored at teardown: "database test_eventpulse24 is being accessed by other users" (the `catalog` alias keeps its own persistent connection; Django closes only the first alias's before DROP) | Medium | Fixed: `connections.close_all()` before `teardown_databases` |
| Guard exit left the just-created test DBs behind | Low | Fixed: guard tears down before `pytest.exit` |
| Guard message reported names after teardown had restored them (misleading) | Low | Fixed: names captured before teardown |
| Ruff S608 on probe SQL built from module constants in tests; one E501 | Low | Fixed: `S608` allowed for `tests/**` with rationale; formatted |

## Ready for Completion

- [x] All tests passing
- [x] Coverage target met (n/a until ci-pipeline)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-003*
