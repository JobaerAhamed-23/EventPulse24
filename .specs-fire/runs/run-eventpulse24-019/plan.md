---
run: run-eventpulse24-019
work_item: repo-hygiene-cleanup
intent: personal-events-and-saved-catalog
mode: autopilot
checkpoint: none
approved_at: n/a
---

# Implementation Plan: Repository Hygiene Cleanup

## Approach

Inventory every macOS AppleDouble duplicate in the working tree, separate the *files* from the
*directories*, confirm each candidate is untracked by git before removal, then prove the cleanup
is behaviour-neutral by recording the backend and frontend test counts before and after.

The work item's premise was that ~30 duplicate **files** (`Makefile 2.py`, `README 2.md`,
`domain/confidence 2.py`, `apps/personalization/api 2.py`, …) were present. That premise turned
out to be **stale**: by the time this item was executed the duplicate files had already been
removed outside this session. What remained were ~10 **empty duplicate directories** — the
`… 2/` folders that survive their files, and that a `find -name '* 2.*'` file glob does not
match.

The cleanup therefore proceeds in two passes:

1. **Inventory.** Glob for both duplicate *files* (`* 2.py`, `* 2.ts`, `* 2.tsx`, `* 2.md`,
   `* 2.yml`, `* 2.yaml`, `* 2.json`, `* 2.toml`, `* 2.lock`, `* 2.css`, `* 2.mts`, `* 2.mjs`)
   and duplicate *directories* (`* 2*`). For each hit, cross-check `git ls-files` to determine
   tracked vs. untracked.
2. **Removal.** Delete only what is (a) untracked, (b) empty, and (c) not referenced by the
   `Makefile`, `scripts/`, `.github/workflows/` or `frontend/package.json`.
3. **Proof.** Re-run the full backend suite (1691 tests) and the frontend suite (51 tests) against
   the real Postgres and confirm both counts are identical to the pre-cleanup baseline.

### Correctness safeguards

- **Legitimate names are not touched.** A name merely *containing* a `2` — `run-eventpulse24-002`,
  `voyage.py`, `schema.ts` — is not a duplicate. The removal set is built from the explicit
  AppleDouble shape (`<name> 2<ext>` / `<name> 2/`), never from a bare `*2*` glob.
- **Tracked duplicates would be removed with `git rm`.** None were found, so nothing in the
  removal set needed a git-tracked removal.
- **No feature work in this commit.** The cleanup is its own commit, revertible independently.

## Files to Create

| File | Purpose |
|------|---------|
| (none) | |

## Files to Modify

| File | Changes |
|------|---------|
| (none) | |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/` (full suite) | Regression proof: 1691 tests, count identical before and after |
| `frontend/tests/` + `frontend/app/` (Vitest) | Regression proof: 51 tests, count identical before and after |

## Technical Details

### Pre-cleanup inventory

**Duplicate files — 0 found.** A glob across the whole tree for every AppleDouble suffix returned
zero hits. The ~30 duplicate files described in the work item description (and confirmed present
during the planning phase) had already been deleted before this item ran. This is recorded rather
than claimed as work done here.

**Duplicate directories — 10 found, all empty and all untracked:**

| Path | Files inside | Tracked? |
|------|--------------|----------|
| `docker/postgres 2` | 0 | untracked |
| `frontend/app/dev 2` | 0 | untracked |
| `frontend/.next/server/middleware 2` | 0 | untracked |
| `frontend/.next/server/app 2` | 0 | untracked |
| `frontend/.next/server/chunks 2` | 0 | untracked |
| `frontend/.next/server/pages 2` | 0 | untracked |
| `frontend/.next/build/chunks 2` | 0 | untracked |
| `frontend/lib/api 2` | 0 | untracked |
| `.specs-fire/intents 2` | 0 | untracked |
| `backend/tests/fixtures/sources 2` | 0 | untracked |
| `.specsmd/fire 2` | 0 | untracked |

Each was confirmed empty (`0 files`) before removal. The removal had to be iterative: the first
`rmdir` exposed nine further nested duplicates, and a second `find -depth -type d -empty -delete`
pass cleared the rest.

### Reference check

The only `grep` hits for the duplicate names were the search pattern itself and a `2>/dev/null`
redirection inside `scripts/db-check.sh` — neither references a duplicate path. `Makefile`,
`scripts/`, `.github/workflows/` and `frontend/package.json` reference no duplicate.

### `__pycache__` duplicates

Remaining `__pycache__` directories with numeric suffixes are gitignored
(`.gitignore:7: __pycache__/`), regenerate harmlessly, and are not AppleDouble artifacts. Left
alone.

### Environment blocker, resolved

The first full backend run produced `1234 passed, 457 errors` — every error a
`psycopg` `ConnectionTimeout`. Root cause: **Docker Desktop was not running**, so the project's
Postgres 18 + pgvector (host port 5440) and Redis (6380) were unreachable. Only a native
Postgres on 5432 was listening — and the scaffold brief explicitly forbids disturbing the
pre-existing native PG12/PG16/Redis instances.

Resolved the prescribed way rather than by repointing `.env`: started Docker Desktop and ran
`docker compose up -d`. All three services reached `healthy`
(`pgvector/pgvector:0.8.6-pg18` on 5440, `redis:8-alpine` on 6380, `axllent/mailpit:v1.32` on
1025/8025). `.env` was **not** modified — the pre-existing native services on 5432/5434/6379
were left untouched.

### Baseline

| Suite | Before | After |
|-------|--------|-------|
| Backend (pytest, real Postgres, both schemas) | 1691 collected | **1691 passed** |
| Frontend (Vitest) | 51 passing / 9 files | **51 passing / 9 files** |
| `ruff check` | clean | **All checks passed!** |
| `make lint-imports` | 13 kept, 0 broken | **13 kept, 0 broken** |

---
*Autopilot mode — 0 checkpoints. Plan recorded for review; execution follows.*

---

## Work Item: conflict-domain-and-constants

### Approach

Implement `backend/domain/conflict.py`: the single pure overlap function AD-21 mandates, plus the
separate FR-58 duplicate-detection rule. Pure logic — no models, no database, no API.

**The overlap function.** The signature is pinned by the project standards
(`.specs-fire/standards/coding-standards.md` §"Pure domain function" and
`.specs-fire/standards/testing-standards.md` §"Test Structure"):

```python
def conflicts(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
```

Two UTC intervals conflict when their overlap is **strictly more than** `CONFLICT_MIN_OVERLAP`
(15 minutes, already in `shared/constants.py` — used, never re-declared). Exactly 15 minutes is
**not** a conflict; 15 minutes + 1 second **is**.

**The threshold's source of truth.** AD-21 states the rule; the work item and the testing
standards agree. Note that FR-58's prose ("scans for other Personal Events within ±30 minutes of
the new event's start time") describes a **candidate scan window** around the start, not the
overlap threshold — the two are not in conflict: the scan finds candidates, the overlap function
decides. This item implements the overlap function only; the candidate scan belongs to the
service layer (work item ⑤).

**Intervals with no end.** `end_time_utc` is nullable on the catalog's Event, and the personal
event form's end time is optional. So the function must handle `end=None`. The rule is
"two UTC intervals conflict when they overlap", and an event with no end has an **open-ended**
interval `[start, ∞)`. Treating it as unbounded makes it overlap everything after it — which is
the honest reading of "this event has no known end" and is the *safe* direction for a
double-booking guard. A zero-length interval (`end == start`) is a different matter: it occupies
no time at all and can never overlap by more than 15 minutes, so it never conflicts.

**Purity.** `domain/conflict.py` imports only the stdlib plus `shared.constants` — the two
allowlisted by the `domain-pure` import-linter contract. No Django, no clock read, no I/O. The
existing `tests/domain/test_domain_is_django_free.py` walks **every** `domain/` module in a fresh
interpreter, so the new module is covered for Django-freedom with no extra test. The
`tests/domain/test_domain_api.py` scan likewise picks up the new module automatically and
asserts no public API takes an embedding or similarity input — the duplicate rule is structural,
never semantic.

**The duplicate rule.** A separate function, per FR-58: a likely duplicate when another event
has the same name (case-insensitive, ≥80% token overlap) **and** starts within 24 hours.

It reuses `domain/dedup.py`'s existing public helpers — `tokens()` and `jaccard()` — rather than
declaring a second normaliser. This matters: `dedup.tokens()` folds case, drops Latin/Greek/
Cyrillic accents, keeps CJK dakuten, and splits unspaced scripts into bigrams. A second
normaliser would fold "Café Night" differently in the duplicate prompt than in the dedup path,
which is exactly the drift AD-21 exists to prevent. `jaccard()` takes two *fingerprints*, so the
rule computes `title_fingerprint()` on each name and compares — the same machinery rule (b) uses.

**The threshold constant.** `TITLE_JACCARD_MIN` is already `Fraction(4, 5)` — exactly 80%, and
already used by the dedup path. The work item asks whether the duplicate rule should share it or
declare its own. **Decision: share it.** Both are the same threshold — "≥80% Jaccard overlap on
tokens" — differing only in what they are applied to (catalog identity vs. a user-facing
duplicate prompt). Two constants with the same value that mean the same thing can drift apart
later; one constant named for what it means cannot. It is renamed `TITLE_TOKEN_OVERLAP_MIN` to
describe the measure rather than its current single caller, and the PRD's wording matches: the
PRD says "≥80% Jaccard overlap **on tokens**" for both the identity rule and the duplicate rule.

A float `0.8` would not be exactly 4/5, so the boundary test would be a lie. `Fraction` stays.

**The 24-hour window.** A new constant, `DUPLICATE_START_WINDOW = timedelta(hours=24)`. "Starts
within 24 hours" is read as an **absolute** difference between start instants (not a signed
one-sided window), so a candidate 23 hours *earlier* counts as within the window. The PRD says
"starts within 24 hours", which is symmetric phrasing.

**Error handling.** An interval whose end precedes its start is invalid input. Rather than a bare
`ValueError`, the module raises a domain error from `domain/errors.py` so the HTTP mapping in
`config/errors.py` stays in one place. A new `InvalidIntervalError(ValidationError)` is added
there.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/domain/conflict.py` | The single overlap function and the FR-58 duplicate rule |
| `backend/tests/domain/test_conflict.py` | Golden tests for both rules, Django-free |

### Files to Modify

| File | Changes |
|------|---------|
| `backend/shared/constants.py` | Rename `TITLE_JACCARD_MIN` → `TITLE_TOKEN_OVERLAP_MIN`; add `DUPLICATE_START_WINDOW` |
| `backend/domain/dedup.py` | Import the renamed constant |
| `backend/domain/errors.py` | Add `InvalidIntervalError` |
| `backend/tests/shared/test_constants.py` | Update the renamed import and pin the new constants |

### Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/domain/test_conflict.py` | Overlap boundaries (0, 1s, exactly 15m, 15m+1s, containment, midnight span, back-to-back, no end) and duplicate rules (case, 80% boundary, just-below, outside 24h) |

### Technical Details

**Overlap arithmetic.** The standard interval-overlap formula:

```python
overlap = min(a_end, b_end) - max(a_start, b_start)
return overlap > CONFLICT_MIN_OVERLAP
```

This is negative for disjoint intervals and zero for back-to-back ones — both correctly below
the threshold. For an open-ended interval, `min(a_end, b_end)` needs an infinite sentinel, so
`datetime.max` stands in for "no end".

**Golden tests.** `tests/domain/test_dedup.py` pins behaviour with exact expected values rather
than re-deriving it, so a change to normalisation or arithmetic fails loudly instead of silently
re-baselining. `test_conflict.py` follows the same style: exact boundary values, parametrised
with readable `ids=`, and the domain's `test_<unit>_<condition>_<expected>` naming
(`test_conflicts_overlap_exactly_15min_returns_false` is the standard's own worked example).

**What this item must not do.** It touches no model, no migration, no API and no frontend. It
does not implement the candidate scan (±30-minute window), the persistence of a `CONFLICT_PAIR`,
or the resolution actions — those belong to work items ③ and ⑤.


---

## Work Item: personalization-models

### Approach

Create the four `personalization`-owned models in the `personal` schema, with one forward-only
migration that carries the constraints, the indexes, the conflict-pair immutability trigger and
the audit table's append-only trigger plus grants.

The work splits into three layers, following the `ingestion` precedent exactly:

1. **Models** (`apps/personalization/models.py`). Pure declarations. Every invariant the
   database can hold is a constraint; nothing here reads a clock or touches the network.
2. **Migration** (`apps/personalization/migrations/0001_initial.py`). Generated by
   `makemigrations`, then hand-edited to add the two triggers and the grant block. The grant
   block *asserts* the revoke applied, because a `REVOKE` by a non-owner merely warns.
3. **Tests.** One file per concern: model/constraint behaviour, the structural guarantee (no
   relation anywhere), the trigger behaviour, schema placement, and role isolation.

### Key design decisions

These come from the approved design doc
(`.specs-fire/intents/personal-events-and-saved-catalog/work-items/personalization-models-design.md`);
the full rationale is there. The ones that shape the code:

| Decision | Choice |
|----------|--------|
| `SavedEvent.event_id` | A **plain `UUIDField`**, never a `ForeignKey`. The structural test asserts the field type. |
| `PersonalEvent.start_time_tz` | An IANA name in a `CharField(max_length=64)`. Validated at the command boundary in work item ⑤, not by a database check — a check cannot see the tz database. |
| `ConflictPair` sides | `(kind, id)` pairs by value. `kind ∈ {personal_event, saved_event}`. No `GenericForeignKey` (OQ-8). |
| `ConflictResolution` | A `TextChoices` with the PRD's four values: `keep_both`, `edit_new`, `delete_new`, `update_existing`. **No `dismiss`.** |
| Pair status | `active` / `resolved` / `cleared_by_state_change`, with `resolution` **nullable** — a state-cleared pair carries no user decision, and that NULL is what distinguishes it. |
| Resolved pair immutability | A **database trigger** (`guard_conflict_pair`), not just a Python guard. Precedent: `catalog.guard_event_write`. |
| The `personal` append-only function | Its **own** copy, not `catalog.forbid_history_mutation()`. `ep_personal` has no `USAGE` on `catalog`, so the shared function would fail to resolve at *every* write, not just a forbidden one. |
| `PersonalEvent.version` | A positive integer with a check, but **no** trigger enforcing the increment. Only the command knows whether a mutation is legitimate; a trigger would have to guess. |
| `PersonalEvent` delete | Unprotected. FR-18 says the user may delete one. The command layer handles any open conflict (item ⑤). |

### Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/personalization/models.py` | The four models: `PersonalEvent`, `SavedEvent`, `ConflictPair`, `PersonalizationAuditEntry`. Overwrites the empty file. |
| `backend/apps/personalization/migrations/0001_initial.py` | Tables, constraints, indexes, the `guard_conflict_pair` trigger, the `personal.forbid_history_mutation` function, the audit trigger, and the `ep_personal` grant block with its assertion. |
| `backend/tests/personalization/__init__.py` | The test package. |
| `backend/tests/personalization/factories.py` | `factory_boy` factories for the three models, writing explicitly on `PERSONAL`. |
| `backend/tests/personalization/test_models.py` | Field defaults, the check constraints, the unique constraint, the status shapes and the resolution/kind pairing. |
| `backend/tests/personalization/test_model_structure.py` | The structural guarantee: no relation field on any of the three models, `event_id` is a plain `UUIDField`, no relation to `User`. |
| `backend/tests/personalization/test_triggers.py` | The `guard_conflict_pair` immutability trigger and the audit table's append-only trigger, below the ORM. |
| `backend/tests/personalization/test_grants.py` | The `ep_personal` runtime role cannot update or delete the audit table; the grant assertion fails when the revoke is missing. |

### Files to Modify

| File | Changes |
|------|---------|
| `backend/tests/wall/test_schema_placement.py` | Assert the four new tables are in `personal`, and that `catalog` still holds only catalog tables. Read from `information_schema`, not assumed. |
| `backend/tests/wall/test_role_isolation.py` | Assert `ep_personal` cannot read `catalog` tables even now that `personal` has product tables. |

No production file outside `apps/personalization/` changes. `settings.DATABASE_ROUTING` already
routes `personalization` to `PERSONAL`, so `eventpulse.E001` stays green with no settings edit.

### Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/personalization/test_models.py` | `PersonalEvent`: the end-after-start check, the positive-version check, `source` defaults to `user_created`, the open-ended (NULL end) case. `SavedEvent`: the `(user_id, event_id)` uniqueness, the positive `event_version` check, the NULL end. `ConflictPair`: the three legal status shapes, the three illegal ones, sides-must-differ, the four legal resolutions, the illegal `dismiss`, and the kind/resolution pairing (`edit_new` is time-only, `update_existing` is duplicate-only). |
| `backend/tests/personalization/test_model_structure.py` | For each of the three models: no field `is_relation`. `SavedEvent.event_id` is a `UUIDField` and not a `ForeignKey`. No model declares a relation to `User` or `ContentType`. |
| `backend/tests/personalization/test_triggers.py` | A `resolved` pair refuses an update to its status, resolution or `resolved_at`; a `cleared_by_state_change` pair likewise; an `active` pair may still be updated. The audit table refuses an update and a delete. |
| `backend/tests/personalization/test_grants.py` | `ep_personal` cannot update or delete the audit row (exactly `InsufficientPrivilege` — a trigger's `RestrictViolation` must not pass for a missing `REVOKE`); the migration's own assertion raises when the revoke is missing. |
| `backend/tests/wall/test_schema_placement.py` | The four tables are in `personal`; `catalog` is unchanged; no `personal` table appears in `catalog`. |
| `backend/tests/wall/test_role_isolation.py` | `ep_personal` still cannot read a `catalog` table. |

### Technical Details

**Migration generation.** `uv run python manage.py makemigrations personalization` writes
`0001_initial.py`. The hand-written SQL is appended below the generated operations, following
`ingestion/0001_initial.py`: module-level `TRIGGERS`, `DROP_TRIGGERS`, `GRANTS` and
`UNDO_GRANTS` string constants, wired into `RunSQL` operations. `ingestion`'s test imports
`apps.ingestion.migrations.0001_initial` to assert the grant block raises — this item's
`test_grants.py` does the same with `apps.personalization.migrations.0001_initial`.

**The `personal` trigger function is simpler than the catalog one.** The catalog version takes
a `TG_ARGV[0]` naming a column that may go from NULL to a value (an outbox's `propagated_at`).
The personal audit table has no such column, so the personal copy omits that branch entirely
and rejects every UPDATE and DELETE, allowing DELETE only under
`SET LOCAL eventpulse.retention_purge = 'on'`.

**`skip_postgeneration_save` in the factories.** The audit model is append-only, so
factory_boy's second `save()` would be rejected — exactly the reason
`ingestion`'s `CatalogFactory` sets it.

**The database connection for trigger tests.** `tests/wall/test_schema_placement.py` reads
through `connections[PERSONAL]`; the trigger tests use the same alias, so the trigger is
exercised on the `personal` connection rather than the `catalog` one.

**Gates to run before the item closes.**

```bash
cd backend && uv run python manage.py makemigrations personalization --check
cd backend && uv run python manage.py check
cd backend && uv run pytest -q --no-header -p no:randomly
cd backend && uv run ruff check && uv run ruff format --check
make lint-imports
cd frontend && pnpm vitest run
```

**What this item must not do.** It writes no service, no command, no API and no frontend. It
does not implement the FR-58 candidate scan (±30-minute window), the save-race protocol
(AD-21's re-read-after-commit), or the conflict resolution actions — those belong to work
item ⑤, which is the only writer of these tables.

### Based on Design Doc

Reference: `.specs-fire/intents/personal-events-and-saved-catalog/work-items/personalization-models-design.md`

---

## Work Item: delivery-reminder-plan-owner

**Mode**: confirm | **Complexity**: medium
**Design doc**: not required (medium complexity — a plan section in this file is the design).

### Approach

AD-16 gives `REMINDER_PLAN` exactly one owner: `delivery`. `personalization` never writes the
table; it calls `delivery`'s published service. This item builds that minimum:

1. The `REMINDER_PLAN` model in `apps/delivery/models.py`.
2. A published service in `apps/delivery/services/reminder_plans.py` that `personalization`
   calls to attach the default plan and to edit or empty it.
3. The migration, the tests, and the retention declaration.

It builds **nothing else**: no `SCHEDULED_SEND`, no Celery task, no beat entry, no email
adapter, no quiet hours. Those are a later intent. The `import-linter` contract
`models-delivery` is already declared and already enforced by the build, so the boundary is
real rather than aspirational — this item just has to honour it.

### The attachment mechanism (the one design decision that needs care)

FR-9's picker applies to public events the user saved, and FR-20's default applies to a
personal event. So one plan must attach to **both** a `PERSONAL_EVENT` and a `SAVED_EVENT`.
A `SAVED_EVENT`'s catalog event lives in the `catalog` schema, and AD-3 forbids a FK across
that wall.

**Decision: the plan references the personal-side record it belongs to, by value.**

- `target_kind` — `personal_event` | `saved_event`
- `target_id` — the UUID of that personal-side row

Both live in the `personal` schema and both are owned by `personalization`, so the plan
holds a reference to a row in its own schema and crosses no wall. The catalog event's
absolute time is not needed by the plan at all: slot offsets are **relative** offsets
before the event start (`5d`, `2d`, `1d`, `1hr`), so the plan stays valid when the event is
postponed and AD-17 re-propagates the snapshot.

This mirrors `ConflictPair`, which already stores its two sides as a `(kind, id)` pair by
value for exactly the same reason (OQ-8 forbids `GenericForeignKey`).

**Alternative rejected**: a nullable FK column per target type (`personal_event_id`,
`saved_event_id`). It would need two FKs to two tables owned by another module — which the
`models-personalization` contract forbids `delivery` from importing — plus `ON DELETE`
semantics across both, and it could not express "exactly one target". The `(kind, id)` pair
needs no relation at all.

### Key design decisions

| # | Decision | Why |
|---|----------|-----|
| 1 | `REMINDER_PLAN` lives in `apps/delivery/models.py` | AD-16: `delivery` owns it, and `models-delivery` already protects it. |
| 2 | The target is a `(target_kind, target_id)` pair held by value | Attaches to both a personal event and a saved event with no cross-schema FK and no relation to a module `delivery` does not own. |
| 3 | `target_kind` is a `TextChoices` of `personal_event` / `saved_event` | A UUID alone cannot say what it points at — the same reasoning as `ConflictPair.SideKind`. |
| 4 | `user_id` is a UUID column, not a FK | OQ-8: no model relates to `User`. The user is stored by value. |
| 5 | The slots are a JSON list of slot values, ≤4 entries | The PRD allows "up to 4 slots chosen from 5d/2d/1d/1hr plus one custom slot". A fixed column per slot would not allow a custom slot id, and AD-7's send key says the slot is "the custom slot's **id**" — so a slot is a value, not an offset. |
| 6 | The slot values come from `shared.constants.ReminderSlot` | The enum already exists. AD-16: "never two literals that can drift apart." A custom slot is a value outside the enum, stored as a string id. |
| 7 | `REMINDER_SLOT_OFFSET` is the only source of slot → offset arithmetic | It already exists; the service uses it and never computes an offset itself. |
| 8 | `DEFAULT_REMINDER_PLAN` is the only source of the default | AD-16's contested rule: one named constant, used by both FR-9 and FR-20. |
| 9 | An empty slot list is legal | FR-9: "0 slots = no reminders (still in feed)"; FR-20: "The user can remove all reminders." |
| 10 | The model has no slot for Pulse Ping | The PRD Glossary: "Pulse Ping is NOT part of any Reminder Plan." Nothing in the model can express it. |
| 11 | Unique on `(user_id, target_kind, target_id)` | One plan per event. Re-attaching is an update, not a second row. |
| 12 | `retention_category = ACCOUNT_CONTENT` | It is user-derived content tied to the account. |
| 13 | The service takes the actor and writes an audit row in the same transaction | AD-5: every mutation is a named command with an audit-log write in the same transaction. |
| 14 | `delivery` gets its own audit table | AD-16: each owning app has its own concrete audit table, so the app is its only writer. |

### Files to create

| File | Purpose |
|------|---------|
| `backend/apps/delivery/models.py` | `ReminderPlan` (and `DeliveryAuditEntry`). |
| `backend/apps/delivery/migrations/0001_initial.py` | The schema. |
| `backend/apps/delivery/services/reminder_plans.py` | The published service: attach the default, set slots, remove all. |
| `backend/apps/delivery/services/audit.py` | `write_audit`, mirroring `apps/ingestion/services/audit.py`. |
| `backend/tests/delivery/factories.py` | `ReminderPlanFactory`. |
| `backend/tests/delivery/test_models.py` | The model's constraints and structure. |
| `backend/tests/delivery/test_reminder_plans.py` | The service's behaviour. |
| `backend/tests/delivery/test_ownership.py` | The AD-16 boundary: `personalization` cannot write the table. |

### Files to modify

| File | Change |
|------|--------|
| `backend/tests/wall/test_schema_placement.py` | Assert the `delivery` tables live in `personal` and that no FK crosses to `catalog`. |
| `.specs-fire/runs/run-eventpulse24-019/test-report.md` | The item's results. |

### Tests

| Test | What it pins |
|------|--------------|
| `test_default_plan_is_exactly_one_day_and_one_hour` | `DEFAULT_REMINDER_PLAN` is `(1d, 1hr)` and the attached plan says so. |
| `test_attaching_the_default_plan_creates_the_plan` | The service writes the plan with the default slots. |
| `test_attaching_the_default_plan_to_a_saved_event` | The same service attaches to a `SAVED_EVENT`, by value — no catalog FK. |
| `test_removing_all_reminders_leaves_an_empty_plan` | FR-9/FR-20: an empty plan is valid, not an error. |
| `test_setting_slots_replaces_the_previous_slots` | FR-9: the user can edit a saved plan. |
| `test_the_plan_rejects_a_fifth_slot` | The PRD's "up to 4" bound. |
| `test_the_plan_rejects_an_unknown_target_kind` | The kind is a closed set. |
| `test_the_plan_rejects_a_second_plan_for_the_same_event` | One plan per event. |
| `test_the_service_writes_an_audit_row` | AD-5. |
| `test_personalization_cannot_import_the_delivery_models` | The AD-16 boundary, asserted structurally. |
| `test_the_service_is_importable_by_personalization_without_the_models` | The published interface is reachable. |
| `test_no_delivery_table_has_a_foreign_key_to_catalog` | AD-3. |

### Technical details

- **Schema**: `delivery` is already in `DATABASE_ROUTING[PERSONAL]`, so the tables land in
  `personal` with no routing change.
- **Audit**: `DeliveryAuditEntry` extends the shared `AuditEntry`, so it inherits the
  append-only trigger machinery from item ③'s migration pattern: the `forbid_history_mutation`
  trigger plus the `REVOKE UPDATE, DELETE` grant from `ep_personal`.
- **Service shape**: plain data in and out, `now` passed explicitly rather than read from the
  clock, no `request` object — the `apps/ingestion/services/` convention.
- **Offset arithmetic**: the service exposes `slot_offsets(plan)` built from
  `REMINDER_SLOT_OFFSET`, so the only place that maps a slot to an offset is `shared/`.

### Gates to run before the item closes.

```bash
cd backend && uv run python manage.py makemigrations delivery --check
cd backend && uv run python manage.py check
cd backend && uv run pytest -q --no-header -p no:randomly
cd backend && uv run ruff check && uv run ruff format --check
make lint-imports
cd frontend && pnpm vitest run
```

**What this item must not do.** It writes no `SCHEDULED_SEND`, no Celery task, no beat entry,
no email adapter, no quiet-hours logic, and no API surface. It does not implement the
per-event picker UI. It does not wire the plan into AD-7's send key — that belongs with
`SCHEDULED_SEND`, which this item deliberately does not create.
