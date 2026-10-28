---
run: run-eventpulse24-010
work_item: catalog-data-model
intent: event-catalog-ingestion
mode: validate
checkpoint: plan (Checkpoint 2 of 2)
approved_at: 2026-10-28T07:48:07Z
revision: 2 (plan review: 10 must-fix + 9 should-fix applied)
---

# Implementation Plan: Catalog Data Model

## Approach

> **Needs your call**
> 1. **Branch name.** `constitution.md` requires `PROD-NNNN-<short-slug>`. The current branch, `event-catalog-ingestion`, does **not** follow that rule, and neither did the earlier `setup-specsmd`. Rename before the PR, or keep the name and record the exception.
> 2. **Test location.** Tests go in `backend/tests/ingestion/`, matching the repo's existing per-module layout (`tests/identity/`, `tests/shared/`). `testing-standards.md` says `tests/apps/<module>/`, and this run corrects the standard to match the repo.
> 3. **New dev dependency `factory-boy==3.3.3`,** which pulls in `faker`. The testing standards require it, but the approved design said "no new third-party packages". See [Deviations from the design](#deviations-from-the-design).

This plan builds the approved design `catalog-data-model-design.md` (revision 2), with the deviations listed below. "ADs" means the spine's numbered architecture decisions (AD-1 to AD-21). A "catalog transaction" always means a block opened with `transaction.atomic(using=CATALOG)`.

**Steps, in order:**

1. **Dependency:** `uv add --dev factory-boy==3.3.3`.
2. **Stdlib pieces:**
   - `shared/actor.py` (`Actor`, validated)
   - `shared/ids.py::series_id()`
   - the two new constants in `shared/constants.py`
3. **Abstract `AuditEntry`** in `shared/models.py`, with the actor check named `%(app_label)s_%(class)s_actor_ck`.
4. **Models** in `apps/ingestion/models.py`:
   - every check constraint, unique constraint and index from the design
   - `DjangoJSONEncoder` on every JSON field
   - the append-only manager, QuerySet and model guards
   - `base_manager_name`
5. **Migration:** generate `0001_initial` with `make makemigrations ARGS="ingestion"`, then append the `RunSQL`: two functions, four triggers, REVOKE/GRANT, and the privilege assertion.
6. **Migration round trip on the dev database:**
   - `make migrate`, then check placement, triggers and grants with `psql`
   - `make manage ARGS="migrate ingestion zero --database=catalog"`, then confirm that no `ingestion_*` table, trigger or function is left
   - `make migrate` again

   Repeat this round trip after **any** edit to the `RunSQL`.
7. **`services/audit.py::write_audit`.**
8. **Test helpers:**
   - `tests/roles.py`, which moves `run_as` out of the wall test and adds `expect_denied`
   - `tests/ingestion/factories.py`
9. **Tests**, plus the edits to `tests/wall/test_schema_placement.py`, `tests/shared/test_constants.py`, `tests/shared/test_ids.py` and `tests/architecture/`.
10. **Standards:** edit `tech-stack.md`, `coding-standards.md` and `testing-standards.md`, and add an "Amendments at Checkpoint 2" section to the design doc.
11. **Gates:**
    - `make lint-backend` (ruff and import-linter)
    - `manage.py check`
    - `makemigrations --check --dry-run`
    - `make coverage-backend`

    The repo has no type checker, so there is no "types" gate.

### Deviations from the design

| # | Design said | Plan does | Why |
|---|---|---|---|
| 1 | "No new third-party packages" | Adds dev dependency `factory-boy==3.3.3` (with `faker`) | `testing-standards.md` requires factory_boy, and it is not installed |
| 2 | Not mentioned | Moves `run_as` into `tests/roles.py`, accepting several statements and reporting which one failed. Adds `expect_denied`. | The grant tests need it, and the wall tests share it |
| 3 | Only `coding-standards.md` is edited | Also edits `tech-stack.md` (factory-boy) and `testing-standards.md` (test location, `expect_denied`) | Keep the standards true to the repo |
| 4 | The checklist ends with "lint, types, …" | No types gate | The repo has no mypy or pyright |
| 5 | D11: `series_id` is minted by domain code | `shared/ids.py::series_id(source_id, series_key)`, with a golden-value test. Domain calls it. | One minting path for every caller (review #19). `shared/ids` is already a stdlib-only module that domain may import. |
| 6 | D12: QuerySet `update()` is allowed when its only keyword is `propagated_at` | Also rejects `update(propagated_at=None)`, `bulk_create(update_conflicts=True)`, and any `update_fields`/`fields` set other than `{"propagated_at"}`. Sets `base_manager_name`. | Closes the related-object and upsert paths (review #11) |
| 7 | D10/D12: the event guard covers UPDATE only, and blocks a version decrease and changes to a superseded row | It also fires `BEFORE INSERT`: a new Event must have `event_version = 1` and a status other than `superseded`. On UPDATE, `event_version` may only stay the same or rise by exactly 1, and a change to any **lifecycle column** with the version unchanged is rejected. | Blocks the stale-overwrite and forged-insert paths (review #17). D7's supersede UPDATE bumps the version, so it still passes. |
| 8 | D17: the actor check exists only on the audit table | `EventStateChange` also gets `actor_label`, plus the same named actor check | State changes have actors too: the pipeline is a system actor (review #16) |
| 9 | Not specified | `JSONField(encoder=DjangoJSONEncoder)` on `payload`, `before`, `after` and `details` | Decimal, datetime and UUID values must serialize (review #13) |
| 10 | D18: `Actor(kind, id, label)` | `Actor.__post_init__` validates kind and ID together. A system label must match `^[a-z][a-z0-9_]+$`. | An email or username can't become a label (review #12) |

**Lifecycle columns,** for the event guard and deviation 7: `start_time_utc`, `end_time_utc`, `start_time_tz`, `status`, `is_sold_out`, `venue_id` and `superseded_by_id`. A change to any of them must come with `event_version + 1`. Changes to other columns, such as `last_seen_at`, `title` or `description`, don't need one. Item 6 (`ingest-pipeline-and-lifecycle`) decides which detail edits are lifecycle changes, and may extend this list in its own migration.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/shared/actor.py` | `Actor` value object (stdlib only) |
| `backend/apps/ingestion/migrations/0001_initial.py` | Tables, constraints, indexes, triggers, grants and the privilege assertion |
| `backend/apps/ingestion/services/audit.py` | `write_audit()` and `AuditOutsideCatalogTransaction` |
| `backend/tests/roles.py` | `run_as()`, `expect_denied()` |
| `backend/tests/ingestion/__init__.py` | Package marker |
| `backend/tests/ingestion/factories.py` | `CatalogFactory` base plus one factory per model |
| `backend/tests/ingestion/test_models.py` | Constraints, the supersede order, retention, PROTECT |
| `backend/tests/ingestion/test_triggers.py` | Database triggers, tested with raw SQL |
| `backend/tests/ingestion/test_grants.py` | `ep_catalog` privileges |
| `backend/tests/ingestion/test_guards.py` | Python model, manager and QuerySet guards |
| `backend/tests/ingestion/test_audit.py` | `write_audit` |
| `backend/tests/shared/test_actor.py` | `Actor` validation |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/ingestion/models.py` | The seven models, the guards and `base_manager_name` |
| `backend/shared/models.py` | Abstract `AuditEntry`, with the actor check named per app and class |
| `backend/shared/constants.py` | `TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH`, `SERIES_ID_NAMESPACE` |
| `backend/shared/ids.py` | `series_id(source_id, series_key)` (uuid5) |
| `backend/tests/shared/test_constants.py` | Assert the new constants |
| `backend/tests/shared/test_ids.py` | `series_id` golden-value and determinism tests |
| `backend/tests/wall/test_schema_placement.py` | Expected `catalog` tables become `{"catalog_probe_thing", "django_migrations"}` plus the seven `ingestion_*` tables (review #1) |
| `backend/tests/wall/test_role_isolation.py` | Import `run_as` from `tests/roles.py`. Assertions are untouched; only the import changes. |
| `backend/tests/architecture/checkers.py` | A new `SHARED_STDLIB_ONLY_FILES = ("shared/actor.py",)`, separate from the domain-import list, with its own comment (review #9) |
| `backend/tests/architecture/test_stdlib_only.py` | Parametrize over the new list too, asserting no non-stdlib and no project imports |
| `backend/pyproject.toml`, `backend/uv.lock` | Dev dependency `factory-boy==3.3.3` |
| `.specs-fire/standards/tech-stack.md` | Record factory-boy |
| `.specs-fire/standards/coding-standards.md` | `Actor`, `write_audit`, the three-layer append-only convention, the event guard's lifecycle columns, the conditional outbox update |
| `.specs-fire/standards/testing-standards.md` | Test location, `CatalogFactory`, `expect_denied`, raw-SQL trigger tests |
| `.specs-fire/intents/event-catalog-ingestion/work-items/catalog-data-model-design.md` | An "Amendments at Checkpoint 2" section listing deviations 5–10 |

## Tests

| Test File | Coverage |
|-----------|----------|
| `tests/ingestion/test_models.py` | **Constraints, each asserted by constraint name:**<br>• Unique: `ExtractedRecord (source, source_event_id)`; a second **live** Event for one source item is rejected while a superseded one plus a live one is allowed; unique `slug`; duplicate `(event, event_version)`; duplicate `venue_fingerprint`.<br>• Checks: `event_version = 0`; empty `source_event_id` on both tables; NULL and out-of-range confidence on Event; bad `start_time_local` (microseconds, an offset, free text); end before start; superseded vs `superseded_by` mismatch in both directions; self-supersede.<br>• Resolution: all six invalid `resolution × event × reject_reason` combinations.<br>• Actor: all four invalid actor combinations, on both the audit table and `EventStateChange`.<br>**Supersede order (D7):** the specified order succeeds; inserting first fails on `event_live_source_item_uq`.<br>**Meta-tests:** every FK in the app is `PROTECT` (D20), and the retention category per model. |
| `tests/ingestion/test_triggers.py` | **Raw SQL** through `connections[CATALOG].cursor()`, inside `transaction.atomic(using=CATALOG)` savepoints. The Python guards are never in the path. Each test asserts that `excinfo.value.__cause__` is `psycopg.errors.RestrictViolation` and checks the message.<br>• **State changes:** UPDATE of `kind` rejected; `propagated_at` NULL→value allowed; value→other rejected; `propagated_at` plus another column rejected; DELETE rejected; DELETE allowed under `SET LOCAL eventpulse.retention_purge = 'on'`.<br>• **Audit:** UPDATE and DELETE rejected.<br>• **Event UPDATE:** any change to a superseded row rejected; version decrease rejected; version +2 rejected; a lifecycle-column change at the same version rejected; a lifecycle change with +1 allowed; a `last_seen_at`-only change at the same version allowed.<br>• **Event INSERT:** `event_version ≠ 1` rejected; `status = 'superseded'` rejected. |
| `tests/ingestion/test_grants.py` | `transaction=True`. Rows are created by factories (owner role, committed). Then `expect_denied(ep_catalog_url, sql)` runs **one** statement against those rows by ID and asserts `type(error) is psycopg.errors.InsufficientPrivilege` **exactly**, so a trigger's `RestrictViolation` can't stand in for a missing REVOKE.<br>• UPDATE of `kind` on a state change: denied.<br>• DELETE of a state change: denied.<br>• Audit UPDATE: denied.<br>• Audit DELETE: denied.<br>• UPDATE of `propagated_at`: allowed (via `run_as`).<br>• INSERT into both tables: allowed (via `run_as`). |
| `tests/ingestion/test_guards.py` | **Model:**<br>• `save()` on an existing row raises.<br>• `save(update_fields={"propagated_at"})` and `save(update_fields=("propagated_at",))` are allowed.<br>• `save(update_fields=["propagated_at", "kind"])` raises.<br>• `delete()` raises.<br>**State-change QuerySet:**<br>• `delete()` raises.<br>• `update(kind=…)` raises.<br>• `update(propagated_at=None)` raises.<br>• `filter(propagated_at__isnull=True).update(propagated_at=…)` returns 1.<br>• The **D23 retry** of the same call returns 0 and raises nothing.<br>• `bulk_update` with any field set other than `{"propagated_at"}` raises.<br>• `bulk_create(update_conflicts=True)` raises.<br>**Audit QuerySet:** `update()`, `delete()` and `bulk_update()` all raise.<br>**Related objects:** `event.state_changes.all().delete()` raises, proving `base_manager_name`. |
| `tests/ingestion/test_audit.py` | `write_audit` cases:<br>• writes inside a catalog transaction<br>• a user actor stores no label<br>• a system actor stores its label<br>• `transaction=True`, no transaction open: raises `AuditOutsideCatalogTransaction`<br>• `transaction=True`, only `atomic(using=PERSONAL)` open: raises (review #6)<br>• keyword-only signature: a positional call raises `TypeError` |
| `tests/shared/test_actor.py` | `Actor.user(uuid)` has no label. `Actor.system("ingest_pipeline")` is accepted. These are rejected: a user with a label, a user with no ID, a system actor with an ID, a system actor with an empty label, a label with `@` or uppercase or a leading digit, and an unknown kind. |
| `tests/shared/test_ids.py`, `test_constants.py` | `series_id` golden value for a fixed `(source_id, series_key)`; the same inputs give the same ID; a different key gives a different ID; the namespace constant's value |
| `tests/wall/test_schema_placement.py` | The `catalog` schema holds exactly the probe, `django_migrations` and the seven `ingestion_*` tables. This replaces the `information_schema` test the earlier plan put in `test_models.py`. |
| Existing suite | Green. That includes `manage.py check` (E001–E005), `makemigrations --check`, import-linter, and both stdlib-only checks. |

## Technical Details

**Factories** (`tests/ingestion/factories.py`):
- `CatalogFactory(DjangoModelFactory)` is abstract, with `Meta.database = CATALOG` and `skip_postgeneration_save = True`.
  - The database is explicit so tests don't depend on the router. factory_boy only calls `.using()` when the database isn't `default`; with the default it uses the bare manager, and the router happens to route correctly.
  - `skip_postgeneration_save` stops a second `save()` that would trip the append-only guard.
- Faker is seeded once in the module (`factory.random.reseed_random(...)`).
- Times are fixed UTC instants, each paired with an IANA tz.
- `start_time_local` is generated with `strftime("%Y-%m-%dT%H:%M:%S")`, so it never carries microseconds.
- Each `EventStateChangeFactory` gets its own Event via `SubFactory`, so `event_version` needs no Sequence. When a test needs several changes on one Event, it passes explicit consecutive versions.
- Superseded Events are never built by a factory, because the INSERT guard forbids inserting one. Tests build them through a `make_superseded_pair()` helper that follows the D7 order, so `superseded_by` always points at a real saved row.

**`tests/roles.py`:**
- `run_as(role_url, *statements)`:
  - opens a `psycopg` connection as the role, against the test database, and starts with `SET lock_timeout = '2s'`
  - runs each statement in order and **always rolls back**
  - returns the last statement's rows (or `None`), which is exactly the old single-statement behavior, so the wall tests keep working
  - on failure, re-raises the original psycopg exception with a note: `statement {i} of {n}: {sql}`
- `expect_denied(role_url, *setup, denied)`:
  - runs the setup statements, which **must** succeed (a setup failure fails the test with its index)
  - then runs `denied` and returns its exception only if `type(exc) is InsufficientPrivilege`; any other error, or no error, fails the test

**`write_audit(*, actor: Actor, action: str, target_type: str, target_id: UUID, details: Mapping | None = None) -> IngestionAuditEntry`.** It raises `AuditOutsideCatalogTransaction` (a `RuntimeError` subclass) unless `connections[CATALOG].in_atomic_block`. That is a programming error, not a domain error, so it is never mapped to HTTP.

**Migration `RunSQL`** (forward):
- **Functions:** `catalog.forbid_history_mutation()` (design D12) and `catalog.guard_event_write()`, which has an INSERT branch and an UPDATE branch. The design called it `guard_event_update()`; it is renamed because it now covers INSERT too (deviation 7).
- **Triggers:**
  - `eventstatechange_append_only` and `ingestionauditentry_append_only`: `BEFORE UPDATE OR DELETE`
  - `event_guard_insert`: `BEFORE INSERT`
  - `event_guard_update`: `BEFORE UPDATE`
- **Grants:**
  - `REVOKE UPDATE, DELETE ON ingestion_eventstatechange, ingestion_ingestionauditentry FROM ep_catalog;`
  - `GRANT UPDATE (propagated_at) ON ingestion_eventstatechange TO ep_catalog;`
- **Privilege assertion:** a `DO $$ … $$` block raises `EXCEPTION` unless all of these hold:
  - `NOT has_table_privilege('ep_catalog', 'ingestion_eventstatechange', 'UPDATE')`
  - `NOT has_table_privilege('ep_catalog', 'ingestion_eventstatechange', 'DELETE')`
  - `NOT has_table_privilege('ep_catalog', 'ingestion_ingestionauditentry', 'UPDATE')`
  - `NOT has_table_privilege('ep_catalog', 'ingestion_ingestionauditentry', 'DELETE')`
  - `has_column_privilege('ep_catalog', 'ingestion_eventstatechange', 'propagated_at', 'UPDATE')`

  A REVOKE issued by a non-owner only warns, so this assertion turns a silent no-op into a failed migration.

**Migration `reverse_sql`:**
- Drop the four triggers.
- `DROP FUNCTION catalog.forbid_history_mutation(); DROP FUNCTION catalog.guard_event_write();`
- Re-grant UPDATE and DELETE to `ep_catalog`.

It runs before Django drops the tables, so after `migrate ingestion zero` **no function is left behind**, and re-applying the migration doesn't hit "function already exists". Step 6 proves this.

## Based on Design Doc

Reference: `.specs-fire/intents/event-catalog-ingestion/work-items/catalog-data-model-design.md` (revision 2, Checkpoint 1 approved 2026-10-28T06:53:33Z). Implementation follows its Key Decisions D1–D23 and Implementation Checklist, as amended by the deviations above.

---
*Plan approved at Checkpoint 2 (2026-10-28T07:48:07Z). Branch-name exception recorded: keep `event-catalog-ingestion`.*
