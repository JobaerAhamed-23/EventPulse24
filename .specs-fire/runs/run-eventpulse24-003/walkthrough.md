---
run: run-eventpulse24-003
work_item: schema-router-spike
intent: project-scaffold
generated: 2026-10-27
mode: validate
---

# Implementation Walkthrough: AD-3 Schema Router Spike

## Summary

The AD-3 data wall now exists and is proven. One Postgres database holds two schemas, and Django reaches them through two aliases: `default` (schema `personal`) and `catalog`. The app connects with DML-only roles, one per schema. A map-driven router and two system checks (`eventpulse.E001` and `E002`) make a cross-schema relation fail at check time and at runtime. 72 tests pass against a real test database built from a template; the suite went from 21 to 72. The design went through 3 revisions and the plan through 3 before execution. One code-review fix (S1) was applied.

## Structure Overview

`settings.DATABASE_ROUTING` is the only place that says which app lives in which schema. Four things read it:
- `build_databases()` creates one connection entry per alias. Each entry gets its own role and its own `search_path`.
- the `SchemaRouter` sends reads, writes, relations and migrations to the right alias
- the system checks fail on an unmapped app or a cross-alias relation
- the test settings, which add two test-only probe apps

Postgres enforces the same split. The init script creates the schemas, the owner role and the two runtime roles, plus the default privileges that grant migrated tables to the right runtime role. Tests use a template database, so the test DB copies all of this.

## Architecture

### Pattern Used

There are two layers of defence. The ORM refuses cross-schema relations (router and checks), and Postgres refuses cross-schema access (roles and grants). Either layer catches the mistake on its own.

### Layer Structure

```text
settings.DATABASE_ROUTING  (one map: app → alias)
   ├─► config/checks.py     E001 unmapped app · E002 cross-alias relation   (manage.py check / CI)
   ├─► config/db_router.py  read/write/migrate/relation, fail-closed         (runtime)
   └─► config/databases.py  alias → role URL + search_path                  (connection)
                                │
        default ──► ep_personal ──► schema personal  (identity, personalization, delivery, Django tables)
        catalog ──► ep_catalog  ──► schema catalog   (ingestion, catalog, editorial)
        ep_owner (DDL) ── only `make migrate` and tests
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/shared/db.py` | `PERSONAL = "default"`, `CATALOG = "catalog"` |
| `backend/config/databases.py` | `build_databases()`: role choice, per-alias `search_path`, `ATOMIC_REQUESTS` off, shared TEST settings |
| `backend/config/db_router.py` | `SchemaRouter`, fails closed |
| `backend/config/checks.py`, `apps.py` | `eventpulse.E001` and `E002` (pure functions plus wrappers), registered in `ready()` |
| `backend/config/settings_test.py` | Owner role; probe apps installed and routed |
| `backend/apps/identity/migrations/0001_initial.py` | Custom `User` |
| `backend/tests/conftest.py` | Sets up both aliases on one test DB: guard, migrate catalog, re-apply the DB ACL, clean teardown |
| `backend/tests/wall/**` | Probe apps; schema-placement, ORM-wall, role-isolation and transaction tests |
| `backend/tests/config/test_{databases,router,checks}.py` | Unit tests for the three config modules |

### Modified

| File | Changes |
|------|---------|
| `docker/postgres/init/01-schemas-and-roles.sh` | Idempotent; sets up the main DB and the test template; `ep_owner CREATEDB`; role `search_path` |
| `scripts/db-check.sh` | Checks the template and `CREATEDB` |
| `Makefile` | `db-init`, `migrate` (owner, both aliases); `makemigrations` formats its output |
| `backend/config/env.py`, `settings.py` | `DJANGO_DB_ROLE`; owner URL optional unless role is owner; DATABASES, router, routing map, `AUTH_USER_MODEL` |
| `backend/apps/identity/{models,admin}.py` | `User(AbstractUser)` |
| `backend/pyproject.toml` | Ruff: tests ignore `S608`, migrations ignore `E501` |
| `.env.example`, `README.md`, `docs/setup/{ubuntu,macos}.md` | `DJANGO_DB_ROLE`, `make migrate`, `make db-init` for existing volumes |
| `.specs-fire/standards/*`, work items, `ARCHITECTURE-SPINE.md` | Schema-wall and `using=` rules, multi-DB test rules, Neon note, OQ-8, CI notes, criteria reworded (D1a) |

## Domain Model

### Entities

| Entity | Properties | Business Rules |
|--------|------------|----------------|
| `identity.User` | `AbstractUser` fields, no extras | Lives in `personal`. The PK moves to UUIDv7 in `shared-foundations` by rewriting `0001`. |

The probe models `catalog_probe.Thing` and `personal_probe.Note` are test-only and never ship.

## Key Implementation Details

### 1. Why `default` is personal

Django requires a `default` alias. Personal rows FK to the user, and Django refuses relations across aliases even on the same database. So `User` and all personal data share `default`. Code never writes the literal `"default"`; it imports `PERSONAL` / `CATALOG` from `shared/db.py`. Acceptance criteria 1, 2 and 4 were reworded to match (D1a).

### 2. Fail-closed routing

- An unmapped app raises `ImproperlyConfigured` on read or write instead of falling back to personal.
- `allow_migrate` and `allow_relation` return False for unmapped apps.
- `allow_relation` compares the two models through the map, not `_state.db`, so an instance loaded with a stray `.using()` can't get through.

### 3. One test DB, two aliases

Both aliases have the same TEST settings, so Django creates one test DB and mirrors the second alias onto it. A mirror copies only `NAME`, so each alias keeps its own `search_path`.

Django migrates only the first alias, so the conftest override does the rest:
1. sets up both aliases on every run, even a single test file
2. refuses to continue if the two aliases don't share the test DB
3. migrates `catalog`
4. re-applies the database-level grants, which a template doesn't copy
5. closes all connections before teardown

### 4. Connection options are merged (code review S1)

`dj_database_url` turns URL query parameters into `OPTIONS`, for example Neon's `sslmode=require`. `build_databases` now adds `search_path` to those options instead of replacing them. Before, production would have quietly lost its SSL requirement.

## Security Considerations

| Concern | Approach |
|---------|----------|
| Cross-schema reads | Each runtime role has USAGE and DML on its own schema only. A test proves `ep_catalog` can't read `personal` and vice versa. |
| DDL at runtime | Runtime roles can't CREATE in their own schema or in `public` (tested). Only `ep_owner` migrates. |
| Database access | `REVOKE ALL … FROM PUBLIC`; CONNECT/TEMPORARY only for the three roles, on the dev DB and the test DB |
| Owner credentials | `DATABASE_URL_OWNER` is required only when `DJANGO_DB_ROLE=owner`, so a production runtime environment never holds it |
| TLS | URL `sslmode` is kept (S1) |
| Local-only privilege | `ep_owner CREATEDB` exists only in the local init script |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| Connection count | Two aliases mean up to 2 connections per request or worker, kept open by `CONN_MAX_AGE=60`. Size Neon and pool limits for that (system-architecture Constraints). |
| Pooled endpoint | Neon's transaction-mode pooler ignores the `options` startup parameter. Runtime connections rely on the role-level `search_path`, which is already set, and migrations must use the direct endpoint. |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Aliases (D1) | `default` = personal, `catalog` = catalog | Django requires `default`; `User` must share an alias with personal data |
| Criteria (D1a) | 1/2/4 say `default` (= `personal` schema) | Follows D1; the spine's intent is unchanged |
| Django tables (D2) | auth, contenttypes, sessions, admin, identity → personal | Personal data; account deletion stays in one schema |
| Custom user (D3) | `identity.User` now | Avoids the known `AUTH_USER_MODEL` migration trap |
| Router (D5) | Map-driven, fail-closed, compares models | No silent fallback to personal |
| Checks (D6) | E001/E002 as pure functions + thin wrappers | Testable with isolated models; fail before any migration |
| `search_path` (D7) | Connection option merged into URL options, plus role default | Owner spans both schemas; the role default survives poolers; `sslmode` kept |
| Roles (D8) | `DJANGO_DB_ROLE` runtime / owner | The app runs DML-only |
| `ATOMIC_REQUESTS` (D9) | False inside each alias | It would wrap only one schema |
| Test DB (D10) | One test DB from a template, plus a conftest override | Mirrors production; matches Django 6.1.2 mirror behaviour |
| Probe models (D13) | Test-only apps with a documented migration command | Spike models never ship |

## Deviations from Plan

- **conftest teardown closes all connections first.** This wasn't in the plan. A single-file run failed at teardown with "test_eventpulse24 is being accessed by other users": the `catalog` alias held its own connection, and Django closes only the first alias's before DROP.
- **The guard tears down before exiting and reports the names captured beforehand.** Before this, it left test DBs behind and printed the restored names.
- **Ruff `S608` is ignored for `tests/**`.** The probe SQL is built from module constants, not input.
- **Code review S1** (`OPTIONS` merge plus 2 tests) was added after review.

## Dependencies Added

None.

## How to Verify

1. **Upgrade an existing database volume** (this machine and the Mac)
   ```bash
   make db-init && make db-check
   ```
   Expected: only "already exists" notices; every check `ok`, including the template and `CREATEDB`

2. **Migrate as the owner**
   ```bash
   make migrate
   ```
   Expected: both aliases migrate; a second run applies nothing

3. **Tests, lint, checks**
   ```bash
   make test-backend && make lint-backend && make manage ARGS="check"
   ```
   Expected: `72 passed`, `All checks passed!`, `System check identified no issues`

4. **The wall holds when used by hand**
   ```bash
   make psql   # then: SET ROLE ep_catalog; SELECT * FROM personal.identity_user;
   ```
   Expected: `permission denied for schema personal`

## Test Coverage

- Tests added: 51 (21 → 72), plus 9/9 mutation checks and 9 dev-DB integration steps (test-report.md)
- Coverage: not measured yet (added by `ci-pipeline`)
- Status: passing

## Ready for Review

- [x] All acceptance criteria met (criteria 1, 2 and 4 as reworded by D1a)
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated
- [x] Developer notes captured

## Developer Notes

- **On the Mac, after pulling:**
  1. Copy the new `DJANGO_DB_ROLE` key from `.env.example` into `.env` (`make doctor` flags it).
  2. Run `make db-init` to upgrade the existing volume in place.
  3. Run `make migrate`, then `make test-backend`.
  4. If the volume is disposable, `make reset-db` also works.
- **Always pass `using=`.** A bare `transaction.atomic()` targets personal. No transaction spans both schemas.
- **A test that touches `catalog`** needs `@pytest.mark.django_db(databases=[PERSONAL, CATALOG])`. A test that observes commits needs `transaction=True`.
- **Cross-schema subqueries:** with an explicit `.using()` you get a `ValueError`; without it, a `ProgrammingError` "relation does not exist". Both fail; neither is a bug to work around.
- **`django_migrations` lists every app in both schemas.** This is normal Django multi-DB behaviour, because `MigrationRecorder` bypasses the router.
- **Don't run `make db-init` during a test run.** The template can't be copied while something is connected to it.
- **OQ-8 (spine):** catalog models can't FK to `User` or `ContentType`, so there's no `GenericForeignKey` on catalog models, and the AD-5 audit log needs one table per schema with the actor stored by id.
- **Neon (deployment intent):** drop `OPTIONS["options"]` for pooled runtime connections, migrate on the direct endpoint, and size pools for 2 aliases.
- **For `shared-foundations`:** rewrite `identity/0001` for the UUIDv7 PK while there's no real data (`make reset-db` on both machines), and design the audit log per OQ-8.
- **For `architecture-contracts`:** the Ruff `os.environ` ban must exempt `manage.py`. Consider a lint rule for an alias-less `atomic()` / `.using()`.
- **For `ci-pipeline`:** see the notes in its work item (run the init script explicitly, `makemigrations --check` needs the database, test env values).
- **FIRE tooling:** `run.md` frontmatter was synced by hand at each checkpoint and phase change.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-003*
