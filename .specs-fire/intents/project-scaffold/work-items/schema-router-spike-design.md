---
work_item: schema-router-spike
intent: project-scaffold
created: 2026-10-27
mode: validate
checkpoint_1: approved
revision: 3 (design review: 16 + 3 points applied)
---

# Design: AD-3 Schema Router Spike

## Summary

Make the AD-3 data wall real in Django 6.1. Public event data lives in Postgres schema `catalog`, personal user data in schema `personal`. They are exposed as **two Django database aliases on one Postgres**, each with its own role and `search_path`, behind a router driven by an explicit app → alias map. The ORM refuses cross-schema relations and subqueries. Project system checks refuse cross-schema relation fields and unmapped apps at `manage.py check` time, and the router fails closed at runtime. Migrations run as the owner role; the app runs as least-privilege runtime roles. A minimal custom user model is set now, before auth is first migrated. The spike proves all of this with tests against a real test database that has both schemas, and records the Django 6.1 findings plus one architecture consequence for the spine.

## Scope

**In Scope:**
- Database aliases, router (fail-closed), app → alias map, connection `search_path`
- Owner (migrate/test) vs runtime role selection; owner URL optional at runtime
- Where Django's own tables live; minimal `identity.User` + `AUTH_USER_MODEL`
- First real migrations of the framework apps and `identity` (into `personal`)
- Test-database strategy for two schemas in one Postgres; the multi-database test rule
- System checks `eventpulse.E001` (unmapped app) and `eventpulse.E002` (cross-alias relation field)
- Throwaway probe apps (test-only) and the tests proving the wall, both denied and allowed
- `make migrate` / `make db-init`; idempotent init script + test template DB
- Notes handed to `ci-pipeline`, `shared-foundations` and `architecture-contracts`; spine OQ-8

**Out of Scope:**
- Any feature model or field on `User` beyond `AbstractUser` (identity feature work)
- UUIDv7 primary key for `User` (`shared-foundations` introduces `shared/ids.py` and rewrites `identity/0001` while no real data exists)
- Mounting `/admin/` (possible after this item; done when admin is first needed)
- Retention registry (`shared-foundations`)
- Neon / pooled-connection deployment (later deployment intent; risk recorded)

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D1. Aliases** | `default` → schema **`personal`**; `catalog` → schema **`catalog`**. Code never writes the literal: `shared/db.py` exports `PERSONAL = "default"`, `CATALOG = "catalog"` | Django requires a `default` alias. `identity` owns USER (AD-16), and personal rows FK to the user, so the user table must share an alias with personal data (Django refuses relations across aliases even on the same DB). **Rejected:** a third `personal` alias next to `default`, which splits `auth_user` from `SavedEvent`; and `default = {}`, which breaks `createsuperuser`, `migrate` defaults, pytest-django and Celery's Django fixup |
| **D1a. Acceptance-criterion changes** | Every criterion naming a `personal` *alias* is reworded, and the changes are logged in run.md Decisions. **Criterion 1:** "`catalog` and `personal` entries" → "`default` (= `personal` schema) and `catalog` entries". **Criterion 2:** "→ `personal`" → "→ alias `default` (schema `personal`)". **Criterion 4:** "`migrate --database=catalog` and `--database=personal`" → "`--database=catalog` and `--database=default`" | So the review step doesn't flag D1 as unmet; the spine's intent (two entries, two schemas) is unchanged |
| **D2. Django's own tables** | `auth`, `contenttypes`, `sessions`, `admin` and `identity` → `default` (= `personal`) | Users and sessions are personal data. Account deletion stays `personal`-scoped (AD-3) and admin's `LogEntry` FKs to the user. Each schema gets its own `django_migrations` |
| **D3. Custom user now** | `apps/identity/models.py`: `class User(AbstractUser)` with no extra fields; `AUTH_USER_MODEL = "identity.User"`; migration `identity/0001` | Django recommends a custom user model at project start, and this item is the first to migrate auth on both machines. About 10 lines now removes a known migration trap. The probe `Note.owner` points at `settings.AUTH_USER_MODEL` |
| **D4. Routing source of truth** | `settings.DATABASE_ROUTING = {CATALOG: {"ingestion", "catalog", "editorial"}, PERSONAL: {"identity", "personalization", "delivery", "auth", "contenttypes", "sessions", "admin"}}`; `alias(app_label)` looks it up | One explicit map, matching the spine's schema table |
| **D5. Router behavior** | `db_for_read` / `db_for_write`: mapped alias; **unmapped app → raise `ImproperlyConfigured`** (never return `None`, which would fall back to `default`/personal). `allow_migrate(db, app)`: `db == alias(app)`; **unmapped → False**. `allow_relation(a, b)`: compares **models by the map**, `alias(a._meta.app_label) == alias(b._meta.app_label)`; **unmapped → False** | Fail-closed at runtime as well as at check time. Comparing models rather than `_state.db` follows the routing map and can't be fooled by an instance loaded with a stray `.using()` |
| **D6. System checks** | **`eventpulse.E001`**: an installed app with models is missing from `DATABASE_ROUTING`. **`eventpulse.E002`**: a relation field (FK/O2O/M2M) whose ends map to different aliases. The logic lives in **pure functions over explicit inputs**: `find_unmapped_apps(app_configs, routing)` and `find_cross_alias_relations(models, routing)`. The registered checks are thin wrappers that use the `app_configs` Django passes in (e.g. `manage.py check identity`), fall back to all app configs only when it is `None`, take models from those app configs, and pass `settings.DATABASE_ROUTING` *(updated at plan review)*. Registered from `config.apps.ConfigConfig.ready()` | Makes the mistake fail `manage.py check` and CI before any migration. Namespaced IDs can't be confused with Django's own. A check function only sees the global registry, so tests call the pure functions directly with isolated models |
| **D7. `search_path`** | Each alias sets `OPTIONS = {"options": "-c search_path=<schema>,public"}` **plus** the role-level `ALTER ROLE … SET search_path` from the init script | The connection option is needed for the owner role, which spans both schemas. The role default is what survives a transaction-mode pooler. `public` stays only for the `vector` type; CREATE on `public` is revoked |
| **D8. Role selection** | `DJANGO_DB_ROLE = runtime` (default) → `default` uses `DATABASE_URL_PERSONAL` (ep_personal), `catalog` uses `DATABASE_URL_CATALOG` (ep_catalog). `owner` → both aliases use `DATABASE_URL_OWNER` (ep_owner) with their own `search_path`. Built by `config/databases.py::build_databases(env)`. **`DATABASE_URL_OWNER` becomes optional and is required only when role = owner** (model validator) | The app runs DML-only, and a production runtime environment never has to hold DDL credentials. Default privileges `FOR ROLE ep_owner` grant migrated tables to the right runtime role automatically |
| **D9. Transactions** | `"ATOMIC_REQUESTS": False` pinned with a comment **inside each alias** built by `build_databases` (Django reads it per database entry; a top-level setting does nothing) *(updated at plan review)* | It would wrap only `default`, giving the false impression that a request is atomic across both schemas |
| **D10. Test database** | **One** test DB `test_eventpulse24` from template **`eventpulse24_test_template`** (schemas, grants, extension, default privileges, no tables) via `TEST={"NAME":…, "TEMPLATE":…}` on both aliases. Same signature, so Django creates and migrates it once for `default`. A session fixture in `tests/conftest.py` then (a) runs `migrate --database=catalog` and (b) re-applies the database-level `REVOKE ALL … FROM PUBLIC` + `GRANT CONNECT, TEMPORARY` to the three roles, because a template copies schemas and default privileges but **not** database-level ACLs. Tests connect as **owner** via `config/settings_test.py` | Mirrors production: one DB, two schemas, so DB-level isolation is testable. Verified in Django 6.1.2: only the first alias of a signature is migrated, and mirrors copy only `NAME`, so `catalog` keeps its `search_path` |
| **D11. Multi-database test rule** | A test touching `catalog` must declare `@pytest.mark.django_db(databases=[PERSONAL, CATALOG])`; pytest-django otherwise allows only `default` ("Database queries to 'catalog' are not allowed"). Tests that observe commits use `transaction=True`. Added to `testing-standards.md` beside the "always pass `using=`" rule in `coding-standards.md` | Makes the convention explicit before feature work starts |
| **D12. Init script** | Per-database setup applied to `eventpulse24` **and** the template; `ALTER ROLE ep_owner CREATEDB` (local only); template owned by `ep_owner`, `IS_TEMPLATE true`; fully idempotent; `make db-init` re-applies it to a running container without data loss | The template must carry schemas and default privileges, which are per-database. `CREATEDB` lets the owner create the test DB. Idempotency lets both machines upgrade in place |
| **D13. Proof models** | Test-only apps `tests/wall/catalog_probe` (`Thing`) and `tests/wall/personal_probe` (`Note`), installed and routed only by `settings_test`. Their migrations are generated with a documented command (below), **not** `make makemigrations`, which runs under the normal settings where the probes aren't installed | AC: spike models are never shipped |

## Data Models Affected

### Creates
- **`identity.User`** (real): `AbstractUser` fields, BigAutoField PK for now. Lands in `personal`
- **`catalog_probe.Thing`** (test-only): `id`, `name`. Lands in `catalog`
- **`personal_probe.Note`** (test-only): `id`, `text`, `owner → AUTH_USER_MODEL`. Lands in `personal`; proves same-alias FKs work
- **Framework tables** (real): `django_content_type`, `auth_group`/`auth_permission`, `django_session`, `django_admin_log`, `django_migrations` in `personal`; `django_migrations` in `catalog`

## Technical Approach

### Architecture

```
                 DJANGO_DB_ROLE=runtime (app)            DJANGO_DB_ROLE=owner (make migrate, tests)
alias "default" ─ ep_personal  search_path=personal,public │ ep_owner  search_path=personal,public
alias "catalog" ─ ep_catalog   search_path=catalog,public  │ ep_owner  search_path=catalog,public
                         │                                          │
                         └────────── one Postgres DB: eventpulse24 ─┘
                                     ├─ schema personal  (identity, personalization, delivery,
                                     │                    auth, contenttypes, sessions, admin)
                                     ├─ schema catalog   (ingestion, catalog, editorial)
                                     └─ schema public    (vector extension only; no CREATE)

SchemaRouter  ← settings.DATABASE_ROUTING (app label → alias; unmapped = error/False)
  db_for_read/db_for_write(model) = alias(app_label)        unmapped → ImproperlyConfigured
  allow_relation(a, b)            = alias(a's app) == alias(b's app)   unmapped → False
  allow_migrate(db, app_label)    = db == alias(app_label)           unmapped → False
config.checks  eventpulse.E001 unmapped app · eventpulse.E002 cross-alias relation field
```

### Database Changes

```sql
-- init script (idempotent), schema setup applied to eventpulse24 AND eventpulse24_test_template
ALTER ROLE ep_owner CREATEDB;                                         -- local/test only
SELECT 'CREATE DATABASE eventpulse24_test_template OWNER ep_owner'
 WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'eventpulse24_test_template') \gexec
-- per database: schemas catalog/personal owned by ep_owner, USAGE + default DML grants
-- per runtime role, REVOKE CREATE ON SCHEMA public, CREATE EXTENSION vector  (as today)
ALTER DATABASE eventpulse24_test_template WITH IS_TEMPLATE true;
```

- `make migrate` = `DJANGO_DB_ROLE=owner manage.py migrate --database=default`, then `--database=catalog`.
- Probe migrations: `cd backend && DJANGO_SETTINGS_MODULE=config.settings_test uv run python manage.py makemigrations catalog_probe personal_probe` (documented in `tests/wall/__init__.py`).

## Dependencies

- `local-infra-and-setup-docs` (init script, roles), `backend-skeleton` (settings, env)

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `docker/postgres/init/01-schemas-and-roles.sh` | Modify | Per-DB setup; template DB; `CREATEDB`; idempotent |
| `backend/config/databases.py` | Create | `build_databases(env)`: aliases, roles, `search_path`, per-alias `ATOMIC_REQUESTS=False`, TEST settings |
| `backend/config/db_router.py` | Create | Fail-closed `SchemaRouter` driven by `DATABASE_ROUTING` |
| `backend/config/checks.py`, `backend/config/apps.py` | Create | `eventpulse.E001`/`E002`, registered by `ConfigConfig.ready()` |
| `backend/config/settings.py` | Modify | `DATABASES`, `DATABASE_ROUTERS`, `DATABASE_ROUTING`, `AUTH_USER_MODEL`, `config.apps.ConfigConfig` (no top-level `ATOMIC_REQUESTS`; see D9) |
| `backend/config/settings_test.py` | Create | Owner role, probe apps + routing, test DB/template |
| `backend/config/env.py` | Modify | `django_db_role`; `database_url_owner: str \| None`, required when owner |
| `backend/shared/db.py` | Create | `PERSONAL`, `CATALOG` |
| `backend/apps/identity/models.py`, `apps/identity/migrations/0001_initial.py`, `apps/identity/admin.py` | Modify/Create | Minimal `User`; registered with `UserAdmin` (admin still unrouted) |
| `backend/pyproject.toml` | Modify | pytest `DJANGO_SETTINGS_MODULE = config.settings_test` |
| `backend/tests/conftest.py` | Create | Session fixture: migrate `catalog`; re-apply DB-level ACL |
| `backend/tests/wall/{catalog_probe,personal_probe}/` | Create | Probe apps (models + migrations) |
| `backend/tests/wall/test_*.py`, `backend/tests/config/test_databases.py` | Create | Wall + role-selection tests |
| `.env.example` | Modify | `DJANGO_DB_ROLE=runtime` |
| `Makefile` | Modify | `migrate`, `makemigrations`, `db-init` |
| `scripts/db-check.sh` | Modify | Template DB exists; `ep_owner` has `CREATEDB` |
| `docs/setup/{ubuntu,macos}.md` | Modify | `make db-init` for existing volumes; `make migrate` in first-run steps |
| `.specs-fire/standards/coding-standards.md` | Modify | `using=PERSONAL` example; "always pass `using=`"; alias map |
| `.specs-fire/standards/testing-standards.md` | Modify | Multi-database test rule (D11) |
| `.specs-fire/intents/project-scaffold/work-items/schema-router-spike.md` | Modify | D1a criterion wording (criteria 1, 2, 4) |
| `.specs-fire/intents/project-scaffold/work-items/ci-pipeline.md` | Modify | CI notes (below) |
| `_bmad-output/planning-artifacts/architecture/…/ARCHITECTURE-SPINE.md` | Modify | **OQ-8** added to Open Questions (E002 consequence); no AD text changed |

### Tests that prove the wall

| Test | Proves |
|------|--------|
| Probe, `identity_user` and framework tables are in the expected schema (`information_schema.tables`) | `allow_migrate` + `search_path` |
| Each schema has its own `django_migrations`; no `identity_user` / `auth_*` in `catalog` | Per-alias migration state |
| `Note.objects.filter(id__in=Thing.objects.using(CATALOG).values("id"))` raises `ValueError` ("Subqueries aren't allowed across different databases"). The plain form (no `.using()`) compiles on `default`, where `catalog` isn't on the search path, and raises `ProgrammingError` ("relation does not exist"), asserted inside `atomic()` *(corrected at plan review: Django only raises the `ValueError` when the inner query was given `.using()`)* | A cross-schema join cannot be expressed through the ORM, either way |
| `@isolate_apps("tests.wall.catalog_probe", "tests.wall.personal_probe")`: **both** models are defined inside the block, a throwaway `CatalogSide` (`app_label="catalog_probe"`) and a `PersonalSide` (`app_label="personal_probe"`) with an FK to `CatalogSide`, so the FK resolves within the isolated registry. Assigning a `CatalogSide()` instance raises the router's `ValueError` (in memory, no table). Separately, the real `Note.owner = user` works | `allow_relation` by model map, refused across and allowed within |
| `find_cross_alias_relations([CatalogSide, PersonalSide], routing)` → one `eventpulse.E002` for `PersonalSide`'s FK; a same-alias pair → none. `find_unmapped_apps` with a config missing from the map → `eventpulse.E001`. Plus the real `manage.py check` passes on the actual project | The mistake fails `manage.py check`; the checks are tested on explicit inputs |
| Router on an unmapped app: `db_for_read`/`db_for_write` raise `ImproperlyConfigured`; `allow_migrate`/`allow_relation` → False | Fail-closed runtime routing |
| **Denied:** raw connection as `ep_catalog` → `SELECT … FROM personal.*` denied, and the reverse; neither runtime role can `CREATE TABLE` | DB-level isolation in the migrated test DB |
| **Allowed:** `ep_catalog` can `SELECT`/`INSERT` on `catalog.catalog_probe_thing`; `ep_personal` can on `personal.personal_probe_note` | Default privileges reached migrated tables (otherwise only visible when the real app runs) |
| `transaction=True` test: a committed `default` write survives a raised `atomic(using=CATALOG)` block; the two connections are distinct objects | "No transaction spans both schemas", the documented accepted cost |
| `build_databases` for runtime/owner → users, `search_path`, TEST; owner URL missing → valid in runtime, `ValidationError` in owner | Role selection and D8 |
| **Integration, in this order:** (1) on the dev DB, which currently has **no** migrations applied, `DJANGO_DB_ROLE=runtime manage.py migrate` **fails** with permission denied (it must create `django_migrations`); (2) `make migrate` (owner) succeeds; (3) `make db-check` | Runtime roles can't run DDL, tested against a real pending state |

## Security Considerations

- **Least privilege at runtime**: the app never holds DDL rights, and with D8 a runtime environment doesn't even receive the owner URL.
- **Owner role**: only `make migrate` and tests use it. `CREATEDB` is granted by the **local** init script only; production owner roles must not have it (deployment intent).
- **`public` schema**: CREATE revoked, so nothing can shadow names via the search path.
- **Test DB ACL**: re-applied by the test fixture (D10), so the test DB isn't connectable by `PUBLIC`.

## Integration Points

| System | Type | Purpose |
|--------|------|---------|
| PostgreSQL 18 (Docker; Neon later) | Database | Two schemas, three roles |
| pytest-django | Test infra | `django_db_setup` extended to migrate `catalog` + re-apply ACL |
| Django system checks | Tooling | `eventpulse.E001`/`E002` in `manage.py check` and CI |

## Findings to hand on

- **E002 consequence (spine OQ-8, walkthrough):** no catalog model can FK to `ContentType` or `User`, because both live in `personal`. Therefore:
  - no `GenericForeignKey` on catalog models
  - **AD-5's audit log** ("audit-log write in the same transaction as the mutation") needs **one audit table per schema**, with the actor stored by id, no FK
  - this changes how `shared-foundations` and AD-5 are built
- **For `ci-pipeline`** (added to its work item):
  - GitHub Actions service containers can't mount `docker-entrypoint-initdb.d`, so CI must run `docker/postgres/init/01-schemas-and-roles.sh` explicitly (psql against the service) to get the schemas, roles, template DB and `CREATEDB`
  - `makemigrations --check` needs a live DB (it runs the migration consistency check), so it needs the service and env values too
  - provide test env values (`DJANGO_SECRET_KEY`, `DATABASE_URL_*`, `REDIS_URL`)
- **For `shared-foundations`:**
  - `User` adopts the UUIDv7 PK by rewriting `identity/0001` (no real data yet; `make reset-db` on both machines)
  - the audit-log design follows OQ-8
- **For `architecture-contracts`:** consider a lint rule for `transaction.atomic()` / `.using()` without an explicit alias.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Neon's pooled endpoint (PgBouncer, transaction mode) doesn't accept the `options` startup parameter, and two aliases mean up to 2 connections per request/worker (×2 with `conn_max_age=60` keeping them open)** | High (prod connectivity and connection limits) | Role-level `search_path` already set for both runtime roles. The deployment intent must drop `OPTIONS` for pooled runtime connections, run migrations on the direct endpoint, and size `conn_max_age` / pool limits for 2 aliases. Recorded in tech-stack/system-architecture |
| Bare `default` reads as "default", not "personal": `transaction.atomic()` with no `using` silently targets personal | Medium | `shared/db.py` constants, the "always pass `using=`" rule, code review; lint rule proposed to `architecture-contracts` |
| `User` PK changes when UUIDv7 arrives | Low | Rewrite `identity/0001` in `shared-foundations` while no real data exists; `make reset-db` on both machines (documented) |
| Django/pytest-django change how mirrored aliases are set up | Medium | The schema-placement test fails loudly if `catalog` isn't migrated; behaviour confirmed in Django 6.1.2 source |
| Template DB can't be copied while someone is connected to it | Low | Only `make db-init` connects to it, briefly; don't run it during tests. The test DB creation error names the cause |
| `django_migrations` records every app's migrations as applied in both schemas (Django multi-DB behavior) | Low | Expected; documented so it isn't mistaken for a bug |
| Existing volumes (this machine + Mac) predate the template/CREATEDB changes | Low | `make db-init` applies the idempotent script in place; `make db-check` flags it if missing |

## Implementation Checklist

- [ ] Init script: per-DB function, template DB, `CREATEDB`, idempotent; `make db-init`; db-check additions; apply to the running container
- [ ] `config/env.py`: `django_db_role`, optional owner URL + validator; `.env.example` key
- [ ] `shared/db.py` alias constants
- [ ] `config/databases.py` (`build_databases`) + tests
- [ ] `config/db_router.py` (fail-closed) + `DATABASE_ROUTING` in settings; `ATOMIC_REQUESTS=False` per alias in `build_databases`
- [ ] `config/checks.py`: pure `find_unmapped_apps` / `find_cross_alias_relations` + thin registered wrappers (`eventpulse.E001`/`E002`); `config/apps.py`; installed
- [ ] `identity.User` + `AUTH_USER_MODEL` + `identity/0001` + admin registration
- [ ] `config/settings_test.py`; pytest points at it; `tests/conftest.py` (migrate `catalog`, re-apply DB ACL)
- [ ] Probe apps + migrations via the documented command
- [ ] Wall tests (placement, per-schema `django_migrations`, cross-DB subquery, `allow_relation`, router fail-closed, checks, denied **and** allowed grants, per-schema transactions with `transaction=True`)
- [ ] Integration in order: runtime-role `migrate` fails on the unmigrated dev DB, then `make migrate` (owner), then `make db-check`; `make test-backend`, `make lint-backend`, `manage.py check`
- [ ] Standards (coding + testing), work-item criteria 1/2/4 (D1a), ci-pipeline notes, spine OQ-8, docs (`db-init`, `migrate`); record Django 6.1 findings in walkthrough

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-10-27 (revision 3)*
