---
run: run-eventpulse24-010
work_item: catalog-data-model
intent: event-catalog-ingestion
generated: 2026-10-28
mode: validate
---

# Implementation Walkthrough: Catalog Data Model

## Summary

The `catalog` schema now holds the seven `ingestion`-owned tables that the rest of the "Event Catalog & Structured Ingestion" intent writes to:

- `Source` and `TosReview`
- `Venue`
- `Event`
- `ExtractedRecord`
- `EventStateChange` (state history plus the AD-17 outbox)
- `IngestionAuditEntry`

The invariants from the approved design (revision 2, plus the Checkpoint 2 amendments) are enforced where the database can hold them:

- **Identity:** one live Event per source item, and one `ExtractedRecord` per source item.
- **Time:** UTC plus an explicit IANA tz, with NOT NULL confidence values in `[0, 1]`.
- **Lifecycle:** versions move only by +1, lifecycle changes need a bump, and `superseded` is terminal.
- **History:** append-only, through grants, triggers and Python guards.

Nothing writes these tables yet. Commands, parsers, the pipeline and the API are later work items. This run is the foundation, proven by 141 new tests.

## Structure Overview

```text
                 schema catalog (alias CATALOG) — owned and written only by apps.ingestion
 TosReview ─n:1─► Source ◄─origin── Event ──superseded_by (terminal)──► Event
                    ▲                 │ ▲
                    │ 1:n             │ └── ExtractedRecord (one row per source item; rule (a) UQ;
                    └─────────────────┘                      resolution check)
                                      │ 1:n  UQ(event, event_version)
                                      ▼
                              EventStateChange ── append-only; propagated_at NULL → value once
 Venue ◄── Event.venue (nullable), venue_fingerprint copied onto Event
 IngestionAuditEntry ── append-only; actor by value, no FK, no personal data in actor_label

 shared/: Actor (value object) · ActorColumns + actor_check() · AppendOnlyModel/QuerySet ·
          AuditEntry (abstract) · series_id() · TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH
```

## Architecture

### Pattern Used

The modular monolith continues to use the owning-app pattern (AD-16). Every catalog entity is owned by `apps.ingestion`. Shared abstract bases and value objects live in `shared/`, so later apps reuse them: each app gets its own audit table built on `AuditEntry`, and any history table can be built on `AppendOnlyModel`. Integrity is layered, from the strongest layer to the earliest one to fail:

### Layer Structure

```text
 Python   AppendOnlyModel.save/delete · AppendOnlyQuerySet (update/delete/bulk_* ) · base manager
 ───────  fails fast, readable AppendOnlyViolation
 Grants   ep_catalog: REVOKE UPDATE, DELETE; GRANT UPDATE (propagated_at)  + DO-block assertion
 ───────  binds the runtime role the app actually uses
 Triggers forbid_history_mutation('propagated_at' | none) · guard_event_write (INSERT + UPDATE)
 ───────  binds every role, raw SQL included
 Checks   unique (incl. partial), check constraints, NOT NULL
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/migrations/0001_initial.py` | Tables, constraints, indexes, 2 trigger functions and 4 triggers, `ep_catalog` REVOKE/GRANT with a privilege assertion |
| `backend/apps/ingestion/services/audit.py` | `write_audit(*, actor, action, target_type, target_id, details)` and `AuditOutsideCatalogTransaction` |
| `backend/shared/actor.py` | `Actor`: a user ID, or a system job-name label (stdlib only) |
| `backend/tests/roles.py` | `run_as` and `expect_denied` for runtime-role privilege tests |
| `backend/tests/ingestion/factories.py` | Deterministic factories on `CatalogFactory`, and `make_superseded_pair()` |
| `backend/tests/ingestion/test_models.py` | Constraints by name, the D7 order, and the PROTECT and retention meta-tests |
| `backend/tests/ingestion/test_triggers.py` | Raw-SQL trigger tests |
| `backend/tests/ingestion/test_grants.py` | `ep_catalog` privileges, and the migration's privilege assertion |
| `backend/tests/ingestion/test_guards.py` | Python guards, and the D23 conditional update |
| `backend/tests/ingestion/test_audit.py` | `write_audit` |
| `backend/tests/shared/test_actor.py` | `Actor` validation |

### Modified

| File | Changes |
|------|---------|
| `backend/apps/ingestion/models.py` | The seven models |
| `backend/shared/models.py` | The append-only machinery, `ActorColumns`, `actor_check()`, and the abstract `AuditEntry` |
| `backend/shared/constants.py` | `TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH = 0.90`, `SERIES_ID_NAMESPACE` |
| `backend/shared/ids.py` | `series_id()` (UUIDv5) |
| `backend/tests/wall/test_schema_placement.py` | Expects the seven `ingestion_*` tables in `catalog` and none in `personal` |
| `backend/tests/wall/test_role_isolation.py` | Imports `run_as` from `tests/roles.py` |
| `backend/tests/architecture/checkers.py`, `test_stdlib_only.py` | A separate stdlib-only check for `shared/actor.py` |
| `backend/tests/shared/test_ids.py`, `test_constants.py` | Tests for the new helper and constants |
| `backend/pyproject.toml`, `backend/uv.lock` | `factory-boy==3.3.3` (dev) |
| `.specs-fire/standards/*.md` | Coding, testing and tech-stack standards updated |
| `catalog-data-model-design.md` | "Amendments at Checkpoint 2" |

## Domain Model

### Entities

| Entity | Properties | Business Rules |
|--------|------------|----------------|
| Source | method, `tos_status`, cadence, `tz_coverage`, fetch and freshness state | Paused, never deleted. `tos_status` is a cache of `TosReview`, reset when the method changes (item 5). Cadence must be > 0. |
| TosReview | decision, method, reviewer ID (by value) | Its own table, because ToS records are kept 7 years |
| Venue | name, city, country, unique fingerprint, nullable IANA tz | Without a tz, a venue can't rescue a `partial`-tier event |
| Event | identity tuple, UTC start/end, local wall-clock time, IANA tz, two confidence values, publication and lifecycle status, sold out, version, series, `superseded_by` | Inserted at version 1. A lifecycle change needs +1. `superseded` is terminal. One live Event per source item. |
| ExtractedRecord | source item, payload, hash, confidence values, resolution | One per source item. Resolved ⇒ an Event and no reason; rejected ⇒ a reason and no Event; ambiguous ⇒ neither. |
| EventStateChange | kind, version, before/after, `propagated_at`, actor | Append-only. `propagated_at` goes NULL → value once. Unique `(event, version)`. |
| IngestionAuditEntry | actor, action, target, details | Append-only. Written only inside a catalog transaction. |

### Value Objects

| Value Object | Properties | Constraints |
|--------------|------------|-------------|
| Actor | kind, id, label | A user has a UUID and no label. A system actor has no ID and a label matching `^[a-z][a-z0-9_]+$`. |
| series_id | UUIDv5 of `"{source_id}:{series_key}"` | Pinned namespace; golden-value test |

## Key Implementation Details

### 1. Supersede order (D7)

The partial unique index `event_live_source_item_uq` can't be deferred, so the old Event must leave the live set before the new one enters it:

1. Mint the new ID.
2. Retire the old Event, setting `superseded_by` and +1 in one UPDATE. The FK to the not-yet-inserted row is allowed because Django's FKs are `DEFERRABLE INITIALLY DEFERRED`.
3. Insert the new Event.
4. Repoint the `ExtractedRecord`.
5. Append the state change.

A test proves that the reverse order fails even inside one transaction.

### 2. The Event guard (`catalog.guard_event_write`)

It fires on INSERT and UPDATE:

- **INSERT:** must be version 1 and not superseded.
- **UPDATE:** the version may only stay the same or rise by 1, and any change to `Event.LIFECYCLE_FIELDS` at the same version is rejected. That closes stale overwrites by in-memory instances.

A test keeps the trigger's column list and `Event.LIFECYCLE_FIELDS` in step.

### 3. A generic append-only trigger

`forbid_history_mutation()` takes the one settable column as a trigger argument. Unchanged-row equality is checked with `to_jsonb(NEW) - col IS NOT DISTINCT FROM to_jsonb(OLD) - col`, so columns added later are covered automatically. DELETE is allowed only under `SET LOCAL eventpulse.retention_purge = 'on'`.

### 4. Migration safety

- After the REVOKE/GRANT, a `DO $$` block raises unless the privileges are exactly right. A REVOKE by a non-owner only warns.
- The `reverse_sql` drops the triggers and both functions.
- Proven on the dev database: migrate, then zero (no tables, functions or triggers left), then migrate again.

### 5. `write_audit`

It is keyword-only, and raises `AuditOutsideCatalogTransaction` unless `connections[CATALOG].in_atomic_block`. A `PERSONAL`-only transaction is rejected too (tested with `transaction=True`).

## Security Considerations

| Concern | Approach |
|---------|----------|
| Tampering with history or audit | Three layers: runtime-role grants, triggers that bind every role, and Python guards. Remaining gaps, accepted: the owner role can TRUNCATE or disable a trigger, and any role can set the purge flag, though only the owner holds DELETE. |
| Personal data crossing the AD-3 wall | Actors are stored by value with no FK. A check plus `Actor` validation keep usernames and emails out of `actor_label`. |
| Untrusted source content (AD-9) | `payload` and `description` are plain-text data. Nothing renders them in this run. |
| Silent privilege misconfiguration | The migration fails if the REVOKE/GRANT didn't apply, and a test proves the assertion fires. |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| Identity rule (b) lookup | Index on `(venue_fingerprint, start_time_utc)` |
| Identity rule (c) lookup | Index on `canonical_url`. Long-URL handling is deferred to item 6 (btree row limit). |
| Public listing | Index on `(publication_status, status, start_time_utc)` |
| AD-17 reconciler | Partial index on `occurred_at WHERE propagated_at IS NULL` |
| Recurring series | Index on `series_id` |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Append-only enforcement | Grants + triggers + Python guards (`shared.models.AppendOnlyModel`) | Each layer covers a different attacker or mistake, and the machinery is reusable by every app |
| Event guard scope | INSERT and UPDATE; version stays or rises by 1; a lifecycle change needs +1 | Blocks forged inserts and stale overwrites (plan review #17) |
| Migration privilege safety | DO-block assertion; reverse drops triggers and functions | A non-owner REVOKE only warns; the zero-and-reapply round trip is proven |
| Test location | `backend/tests/<module>/` | Matches the repo; standard corrected |
| Branch name | Keep `event-catalog-ingestion` | Your decision, recorded as an exception to the constitution's `PROD-NNNN-<slug>` rule |
| Review suggestions | All 3 applied | You approved them; no schema change |

## Deviations from Plan

The plan's ten deviations from the design were approved at Checkpoint 2 and recorded in the design doc's "Amendments at Checkpoint 2" section. During execution:

- **`Actor` check values:** the check uses string values (`ActorKind.USER.value`), so the migration doesn't import `shared.actor`. Enum members would have made the migration depend on that enum staying unchanged.
- **Django error class:** Django wraps PL/pgSQL `RAISE EXCEPTION` (P0001) as `ProgrammingError`, so the assertion test catches `DatabaseError` and asserts the psycopg cause.
- **Code review:** 3 suggestions applied, all approved by you: the `force_update` guard gap, the `ActorColumns` base, and the real reverse-order D7 test.

## Dependencies Added

| Package | Why Needed |
|---------|------------|
| `factory-boy==3.3.3` (dev) | Required by the testing standards for per-app factories |
| `faker==40.43.0` (dev, transitive) | Pulled in by factory-boy; seeded for deterministic data |

## How to Verify

1. **Bring up the stack and apply the migrations**
   ```bash
   make up && make migrate
   ```
   Expected: `Applying ingestion.0001_initial... OK`, or "No migrations to apply" if already applied.

2. **Check placement, triggers and grants**
   ```bash
   docker compose exec -T postgres psql -U postgres -d eventpulse24 -c "\dt catalog.ingestion_*" -c "select event_object_table, trigger_name from information_schema.triggers where trigger_schema='catalog'"
   ```
   Expected: 7 tables in `catalog`, and 4 trigger rows covering 6 events.

3. **Run the round trip**
   ```bash
   cd backend && DJANGO_DB_ROLE=owner uv run python manage.py migrate ingestion zero --database=catalog && cd .. && make migrate
   ```
   Expected: both succeed, with no "already exists" error.

4. **Run the gates**
   ```bash
   make lint-backend && make manage ARGS="check" && make manage ARGS="makemigrations --check --dry-run" && make coverage-backend
   ```
   Expected: 12 contracts kept, no issues, no changes, 579 passed, 97.46% overall and 100% `domain/`.

5. **Try to rewrite history**
   ```bash
   cd backend && uv run pytest -q tests/ingestion
   ```
   Expected: 141 passed. `test_triggers.py` and `test_grants.py` show that both the triggers and the runtime role refuse to rewrite history.

## Test Coverage

- Tests added: 141. The suite went from 438 to 579.
- Coverage: 97.46% overall, 100% for `domain/`. `apps/ingestion/models.py` is at 98%; only the `__str__` methods are uncovered.
- Status: all passing

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated: coding, testing and tech-stack standards, and the design amendments
- [x] Developer notes captured

## Developer Notes

- **Superseded Events can't be built by a factory,** because the insert guard rejects them. Use `make_superseded_pair()`.
- **Inserting an Event at version > 1** fails by design. Insert at version 1, then bump.
- **Testing a check constraint that a trigger pre-empts,** such as `event_version_positive_ck`: disable the trigger inside the test transaction (`ALTER TABLE … DISABLE TRIGGER`). It is rolled back with the test. See `event_insert_guard_disabled()`.
- **Runtime-role tests** open their own connection and can't see uncommitted rows. Use `transaction=True`, create rows with factories, and reference them by ID.
- **Extending `Event.LIFECYCLE_FIELDS`** means changing the trigger in a new migration as well. `test_event_trigger_lifecycle_columns_match_model` fails otherwise.
- **Purging history** (the future AD-15 sweep): `SET LOCAL eventpulse.retention_purge = 'on'` inside the transaction, as a role holding DELETE. Today only the owner holds it.
- **Local Docker:** Docker Desktop was stopped at the start of this run and was started with `systemctl --user start docker-desktop`.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-010*
