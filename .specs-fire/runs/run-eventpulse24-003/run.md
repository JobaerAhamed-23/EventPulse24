---
id: run-eventpulse24-003
scope: single
work_items:
  - id: schema-router-spike
    intent: project-scaffold
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-27T09:53:49.997Z
completed: 2026-10-27T11:20:13.522Z
---

# Run: run-eventpulse24-003

## Scope
single (1 work item)

## Work Items
1. **schema-router-spike** (validate) — completed


## Current Item
(all completed)

## Files Created
- `backend/shared/db.py`: PERSONAL / CATALOG alias constants
- `backend/config/databases.py`: build_databases(): two aliases, role selection, per-alias search_path (merged into URL OPTIONS), ATOMIC_REQUESTS off, shared TEST settings
- `backend/config/db_router.py`: SchemaRouter driven by settings.DATABASE_ROUTING; fails closed
- `backend/config/checks.py`: eventpulse.E001 (unrouted app) / E002 (cross-alias relation) as pure functions + thin registered wrappers
- `backend/config/apps.py`: ConfigConfig registers the checks
- `backend/config/settings_test.py`: Owner role, probe apps installed and routed
- `backend/apps/identity/migrations/0001_initial.py`: Custom User migration
- `backend/tests/conftest.py`: django_db_setup override: both aliases, same-test-DB guard, catalog migrate, DB ACL re-apply, close_all before teardown
- `backend/tests/wall/**`: Probe apps (catalog_probe.Thing, personal_probe.Note) + schema placement, ORM wall, role isolation, transaction tests
- `backend/tests/config/test_databases.py`: 11 tests for build_databases
- `backend/tests/config/test_router.py`: 11 router tests
- `backend/tests/config/test_checks.py`: 8 system-check tests with isolate_apps

## Files Modified
- `docker/postgres/init/01-schemas-and-roles.sh`: Idempotent; per-DB setup for main DB and test template; ep_owner CREATEDB; role search_paths
- `scripts/db-check.sh`: Checks template + CREATEDB
- `Makefile`: db-init, migrate (owner, both aliases); makemigrations formats; .PHONY
- `backend/config/env.py`: DJANGO_DB_ROLE; owner URL optional unless role=owner
- `backend/config/settings.py`: DATABASES via build_databases, router, DATABASE_ROUTING, AUTH_USER_MODEL
- `backend/apps/identity/models.py, admin.py`: Custom User(AbstractUser)
- `backend/tests/config/test_env.py, test_project.py`: Role key, owner URL validator, config app, AUTH_USER_MODEL
- `backend/pyproject.toml`: Ruff: tests ignore S608, migrations ignore E501
- `.env.example`: DJANGO_DB_ROLE=runtime
- `README.md, docs/setup/ubuntu.md, docs/setup/macos.md`: make migrate, make db-init for existing volumes
- `.specs-fire/standards/{coding,testing}-standards.md, system-architecture.md, tech-stack.md`: Schema wall, using= rule, OQ-8, multi-DB tests, Neon pooling note
- `.specs-fire/intents/project-scaffold/work-items/schema-router-spike.md`: Criteria 1/2/4 reworded per D1a
- `.specs-fire/intents/project-scaffold/work-items/ci-pipeline.md`: CI notes: init script, makemigrations --check needs DB, env values
- `_bmad-output/.../ARCHITECTURE-SPINE.md`: OQ-8: no catalog FK to User/ContentType; per-schema audit table

## Decisions
- **Aliases**: default = schema personal, catalog = schema catalog; constants in shared/db.py (Django requires default; User must share an alias with personal data)
- **Acceptance criteria (D1a)**: Criteria 1/2/4 reworded: personal alias -> default (= personal schema); migrate --database=default (Follows D1; spine intent (two entries, two schemas) unchanged)
- **Django's own tables**: auth, contenttypes, sessions, admin, identity -> personal (Users and sessions are personal data; account deletion stays personal-scoped)
- **Custom user**: identity.User(AbstractUser) now (Avoids the known mid-project AUTH_USER_MODEL migration trap)
- **Router**: Map-driven, fails closed (unmapped raises / False); allow_relation compares models, not _state.db (No silent fallback to personal)
- **System checks**: eventpulse.E001 / E002 as pure functions + wrappers honouring app_configs (Fail manage.py check and CI before any migration)
- **search_path**: OPTIONS options merged into URL OPTIONS + role-level ALTER ROLE (Owner spans both schemas; role default survives poolers; merge keeps sslmode (code review S1))
- **Roles**: DJANGO_DB_ROLE runtime (DML-only per schema) / owner (migrate, tests) (Runtime never holds DDL credentials)
- **ATOMIC_REQUESTS**: False inside each alias (Would wrap only one schema and suggest cross-schema atomicity)
- **Test database**: One test DB from eventpulse24_test_template; conftest migrates catalog, re-applies DB ACL, guards same-DB, closes all connections before teardown (Mirrors production; Django 6.1.2 migrates only the first alias of a signature and mirrors copy only NAME)
- **Probe models**: Test-only apps under tests/wall, migrations via documented command (Spike models never ship)
- **Django 6.1 findings**: Cross-DB subquery ValueError only with explicit .using(); plain inner query -> 'relation does not exist'; MigrationRecorder bypasses router (Recorded in coding-standards anti-patterns and tests)
- **OQ-8 raised**: No catalog FK to User/ContentType; per-schema audit table (E002 consequence; affects shared-foundations and AD-5)


## Summary

- Work items completed: 1
- Files created: 12
- Files modified: 14
- Tests added: 41
- Coverage: 0%
- Completed: 2026-10-27T11:20:13.522Z
