# Code Review Report

**Run**: run-eventpulse24-019
**Intent**: personal-events-and-saved-catalog
**Work Item**: repo-hygiene-cleanup
**Reviewed**: 2026-10-29
**Files Reviewed**: 3

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 0 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 0 | 0 |
| Testing | 0 | 0 | 0 |
| **Total** | **0** | **0** | **0** |

**Tests Status**: Passing — 1742/1742 (backend 1691, frontend 51), 0 failed, 0 skipped.

---

## Files Reviewed

- `.specs-fire/runs/run-eventpulse24-019/plan.md` (created — implementation plan)
- `.specs-fire/runs/run-eventpulse24-019/test-report.md` (created — test report)
- `.specs-fire/state.yaml` (modified — FIRE run record, written by `init-run.cjs` / `update-phase.cjs`)

### Production code touched

**None.** This work item is a hygiene item and it changed no source file. The 10 directories it
removed were all untracked and empty, so they appear nowhere in `git diff` — Git never saw them.
The only tracked modification in the tree is `.specs-fire/state.yaml`, and that file is owned by
the FIRE scripts (`init-run.cjs`, `update-phase.cjs`), not hand-edited.

This is the strongest form of the reviewer's mandate here: there is no production diff to review
for correctness, coupling or security, because there is no production diff.

---

## Auto-Fixed Issues

No auto-fixes applied.

`ruff check --fix --diff` produced no output — the backend tree was already clean, and this item
introduced no Python. `make lint-imports` reported **13 contracts kept, 0 broken** across 179
files and 400 dependencies, confirming the cleanup did not disturb any architecture contract
(including `models-personalization` and `models-delivery`, which will become load-bearing in
items ③ and ④).

---

## Applied Suggestions

No suggestions were applied.

---

## Skipped Suggestions

No suggestions were skipped.

---

## Project Tooling Used

The following project linters were detected and used:

- **ruff**: `backend/pyproject.toml`
- **import-linter**: `backend/pyproject.toml`
- **pytest / pytest-django**: `backend/pyproject.toml`
- **Vitest**: `frontend/package.json`
- **ESLint**: `frontend/eslint.config.mjs`

---

## Standards Referenced

- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`
- `.specs-fire/standards/constitution.md`
- `.specs-fire/standards/tech-stack.md`
- `.specs-fire/standards/system-architecture.md`

---

## Verification Performed

| Check | Command | Result |
|-------|---------|--------|
| Backend suite | `cd backend && uv run pytest -q -p no:randomly` | 1691 passed, 0 failed, 0 skipped |
| Backend coverage | `cd backend && uv run pytest -q --cov --cov-report=term` | 99.08% total; `domain/` 100%; 80% gate met |
| Frontend suite | `cd frontend && pnpm vitest run` | 51 passed / 9 files |
| Python lint | `cd backend && uv run ruff check` | All checks passed |
| Import contracts | `make lint-imports` | 13 kept, 0 broken |
| Duplicate files | glob over 12 AppleDouble suffixes | 0 |
| Duplicate directories | `find . -type d -name '* 2*'` | 0 |
| Tracked duplicates | `git ls-files \| grep ' 2'` | 0 |

---

## Verdict

**Approved.** The cleanup is behaviour-neutral — backend and frontend test counts are identical
before and after, all lint and import-contract gates are green, and the working tree contains no
unintended modifications. The work item's acceptance criteria are met.

One correction is carried into the test report rather than being papered over: the work item's
premise of ~30 duplicate **files** was stale, because those files had already been removed
outside this session before the item ran. What remained were 10 **empty duplicate directories**,
which the file-glob the acceptance criteria specify does not match. Both the files and the
directories are now at zero.

---

## Work Item: conflict-domain-and-constants

### Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 1 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 1 | 0 | 0 |
| Testing | 1 | 0 | 0 |
| **Total** | **3** | **0** | **0** |

**Tests Status**: Passing — 1725/1725 backend, 0 failed, 0 skipped. `domain/` coverage 100%.

### Files Reviewed

- `backend/domain/conflict.py` (created) — the overlap function and the duplicate rule
- `backend/tests/domain/test_conflict.py` (created) — 31 golden tests
- `backend/shared/constants.py` (modified) — renamed one constant, added one
- `backend/domain/dedup.py` (modified) — import rename only
- `backend/domain/errors.py` (modified) — added `InvalidIntervalError`
- `backend/tests/shared/test_constants.py` (modified) — updated for the rename, pinned the new constant

### Auto-Fixed Issues

These were found by the review itself and fixed without changing behaviour beyond the fix.

#### 1. [Architecture] Instants were compared without normalisation

- **File**: `backend/domain/conflict.py`
- **Description**: The first implementation compared the caller's datetimes directly. A naive
  datetime mixed with an aware one raised `TypeError: can't compare offset-naive and
  offset-aware datetimes` from deep inside `min()`/`max()` — a confusing message with no
  indication of which argument was wrong. The same applied to `is_duplicate`'s
  `abs(a_start - b_start)`.
- **Fix**: Both functions now normalise through `domain.timezones.to_instant`, which is the
  codebase's existing convention (`domain/timezones.py` raises
  `TypeError("expected an aware datetime")` for a naive value). This gives three things at
  once: a clear error for naive input, normalisation to UTC regardless of the caller's zone,
  and truncation to whole seconds — matching how `domain.dedup.match` compares instants.
- **Diff**:

```diff
-from domain.dedup import jaccard, title_fingerprint
+from domain.dedup import jaccard, title_fingerprint
 from domain.errors import InvalidIntervalError
+from domain.timezones import to_instant

-    a_finish, b_finish = _interval_end(a_start, a_end), _interval_end(b_start, b_end)
+    a_start, a_finish = to_instant(a_start), _interval_end(a_start, a_end)
+    b_start, b_finish = to_instant(b_start), _interval_end(b_start, b_end)

-    if abs(a_start - b_start) > DUPLICATE_START_WINDOW:
+    if abs(to_instant(a_start) - to_instant(b_start)) > DUPLICATE_START_WINDOW:
```

`_interval_end` normalises `end` the same way *before* the validity check, so the check and the
overlap arithmetic always compare like with like — a start of `10:00:00.9` with an end of
`10:00:00.1` cannot slip through as valid.

#### 2. [Testing] Five tests added for the normalisation behaviour

- **File**: `backend/tests/domain/test_conflict.py`
- **Description**: The normalisation fix introduced behaviour that no test pinned. Added:
  `test_conflicts_rejects_a_naive_datetime`, `test_is_duplicate_rejects_a_naive_datetime`,
  `test_conflicts_compares_instants_in_another_zone`,
  `test_is_duplicate_compares_instants_in_another_zone`, and
  `test_conflicts_ignores_sub_second_precision`.
- **Note**: The naive datetimes are built with `datetime.fromisoformat(...)`, the convention
  `tests/domain/test_timezones.py` already uses, so ruff's `DTZ001` does not fire on a
  deliberate naive value.

#### 3. [Code Quality] A speculative public helper was removed

- **File**: `backend/domain/conflict.py`
- **Description**: The first draft also exposed `name_overlap(a_name, b_name) -> float`, a public
  function returning a float similarity ratio. Nothing called it, the work item asked for one
  duplicate-rule function rather than two, and returning a float would have thrown away the
  exactness `Fraction` buys — a float `0.8` is not exactly 4/5, which is the whole reason the
  threshold is a `Fraction`. Removed before review; `is_duplicate` is the single public
  duplicate-rule entry point.

### Findings Considered and Rejected

- **`conflicts` taking an interval dataclass instead of four datetimes.** The standards pin the
  four-argument signature (`coding-standards.md` §"Pure domain function" and
  `testing-standards.md` §"Test Structure" both show `conflicts(a_start, a_end, b_start, b_end)`),
  and the work item's acceptance criteria describe it the same way. A dataclass would be
  nicer to call but would contradict the standards for no functional gain.
- **A separate `DUPLICATE_NAME_OVERLAP_MIN` constant.** Rejected in favour of sharing
  `TITLE_TOKEN_OVERLAP_MIN` — see the test report's note on the rename. The PRD uses the same
  wording ("≥80% Jaccard overlap on tokens") for both rules, so two constants could only drift.
- **Treating an open-ended event as conflicting with nothing.** That would silently under-detect
  double-bookings, which is the failure mode this whole rule exists to prevent. The open-ended
  interval runs to the end of representable time.

### Security

No security surface. The module is pure logic over datetimes and strings: no I/O, no
subprocess, no deserialisation, no user input reaching an interpreter. The names are compared
through `domain.dedup`'s existing tokeniser and never interpreted.

### Architecture

- `domain/conflict.py` imports only `datetime`, `domain.dedup`, `domain.errors`,
  `domain.timezones` and `shared.constants`. The `domain-pure` import-linter contract holds
  (13 kept, 0 broken), and `tests/architecture/test_stdlib_only.py` passes.
- `tests/domain/test_domain_is_django_free.py` walks every `domain/` module in a fresh
  interpreter and confirms Django is never loaded — it now covers `domain.conflict.py`
  automatically.
- `tests/domain/test_domain_api.py` scans every public domain API for embedding or similarity
  inputs and passes.
- The duplicate rule reuses `domain.dedup`'s `title_fingerprint` and `jaccard` rather than
  declaring a second normaliser, so the identity rule and the duplicate rule cannot disagree.
  `test_is_duplicate_matches_the_identity_rule_threshold_exactly` pins that agreement.
- `InvalidIntervalError` subclasses the existing `ValidationError`, so `config/errors.py`'s
  existing mapping already covers it as a 400. No HTTP surface changed, so no mapping change
  was needed.

### Project Tooling Used

- **ruff**: `backend/pyproject.toml` (`ruff check`, `ruff format --check`)
- **import-linter**: `backend/pyproject.toml` (`make lint-imports`)
- **pytest / pytest-django**: `backend/pyproject.toml` (full suite + coverage gates)
- **Django system checks**: `python manage.py check`

### Standards Referenced

- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`
- `.specs-fire/standards/constitution.md`
- `.specs-fire/standards/tech-stack.md`
- `.specs-fire/standards/system-architecture.md`

### Verdict

**Approved.** The two rules are pure, pinned at their exact boundaries, reuse the existing
identity machinery rather than duplicating it, and satisfy every architecture contract. The
three auto-fixes were re-verified by the full suite (1725 passing) and the coverage gates
(`domain/` 100%, overall 99.09%).

---

## Work Item: personalization-models

### Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 1 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 1 | 0 | 0 |
| Testing | 1 | 0 | 0 |
| **Total** | **3** | **0** | **0** |

**Tests Status**: Passing — 1795/1795 backend, 0 failed, 0 skipped. `domain/` coverage 100%,
`apps/personalization/models.py` coverage 100%.

### Files Reviewed

- `backend/apps/personalization/models.py` (created) — the four models
- `backend/apps/personalization/migrations/0001_initial.py` (created) — schema, two triggers, grants
- `backend/tests/personalization/factories.py` (created) — the four factories
- `backend/tests/personalization/test_models.py` (created) — 35 constraint tests
- `backend/tests/personalization/test_model_structure.py` (created) — 13 structural tests
- `backend/tests/personalization/test_triggers.py` (created) — 9 raw-SQL trigger tests
- `backend/tests/personalization/test_grants.py` (created) — 8 role-privilege tests
- `backend/tests/wall/test_schema_placement.py` (modified) — schema placement + cross-schema FK checks
- `backend/shared/retention.py` (modified) — the `ACCOUNT_CONTENT` comment
- `.specs-fire/intents/personal-events-and-saved-catalog/work-items/personalization-models-design.md`
  (created) — the Checkpoint 1 design doc (D1–D28)

### Auto-Fixed Issues

#### 1. [Code Quality] The sides-differ check constraint was inverted

- **File**: `backend/apps/personalization/models.py`
- **Description**: `conflict_pair_sides_differ_ck` was written as
  `left_kind = right_kind OR left_id = right_id` — which is the condition for the two sides
  being *the same record*, not for them differing. Every legal conflict pair was rejected by
  Postgres: 17 tests failed with
  `violates check constraint "conflict_pair_sides_differ_ck"`. The constraint caught the
  opposite of what it claimed.
- **Fix**: Negate the conjunction. The sides differ unless the kind *and* the id both match:
  ```python
  models.CheckConstraint(
      condition=~(
          models.Q(left_kind=models.F("right_kind"))
          & models.Q(left_id=models.F("right_id"))
      ),
      name="conflict_pair_sides_differ_ck",
  ),
  ```
  The migration was regenerated and re-applied, and `test_conflict_pair_rejects_the_same_side_twice`
  now pins the rejection.

#### 2. [Architecture] The `ConflictPair` docstring claimed the model normalised its own sides

- **File**: `backend/apps/personalization/models.py`
- **Description**: The docstring said the unique constraint "is symmetric only if the two sides
  are normalised before writing — lexicographically on `(kind, id)`". Read literally, that
  attributes the normalisation to the model. Nothing does it: the model cannot know which
  side is "new", and the normalisation is a command-layer concern. The docstring was
  over-claiming, and the AD-21 design puts the write protocol in the command layer.
- **Fix**: The docstring now states the obligation and names its owner:
  > The unique constraint below is symmetric only if the two sides are normalised before
  > writing — lexicographically on `(kind, id)` — so `(A, B)` and `(B, A)` are one row.
  > That normalisation belongs to the command layer, which is this table's only writer.

  The obligation is carried into work item ⑤ (`personalization-write-services`), which owns
  the commands, and is recorded as a known gap in the test report rather than left implicit.

#### 3. [Code Quality] The `ACCOUNT_CONTENT` retention comment named only two of three record types

- **File**: `backend/shared/retention.py`
- **Description**: The category covers personal events, saved events *and* the conflicts
  between them, but the comment listed only the first two. AD-15 makes this registry exactly
  what the retention sweep, account deletion and the FR-52 export read, so an incomplete
  description here is a documentation defect in the one place a reader trusts.
- **Fix**: The comment now names the conflict pairs as well:
  ```python
  # Personal events + saved events + the conflicts between them: while the account is
  # active; purged ≤30 days after deletion.
  ACCOUNT_CONTENT = "account_content"
  ```

#### 4. [Testing] A test pinning the trigger's blast radius

- **File**: `backend/tests/personalization/test_triggers.py`
- **Description**: The `guard_conflict_pair` trigger rejects a change to `status`,
  `resolution` or `resolved_at` on a closed pair. A first reading of "a resolved pair is
  immutable" suggests freezing the whole row — but `updated_at` moves on every save, so
  freezing the whole row would make a resolved row un-saveable. Nothing pinned which columns
  the trigger actually guards.
- **Fix**: Added `test_resolved_pair_unrelated_field_may_be_updated`, which updates
  `updated_at` on a resolved pair and asserts the pair's three state columns are untouched.
  Together with `test_active_pair_unrelated_field_may_be_updated`, the trigger's contract is
  now stated in both directions: it guards three columns, not the row.

### Findings Considered and Rejected

- **A `GenericForeignKey` for the conflict sides.** Rejected by OQ-8 and by AD-21: the side is
  a `(kind, id)` pair held by value, and a `GenericForeignKey` would reintroduce a relation to
  `ContentType`. The structural test `test_no_personal_model_relates_to_user_or_content_type`
  makes a regression fail the build.
- **Separate nullable FK columns per side** (`personal_event_id`, `saved_event_id`). Rejected:
  it would need `ON DELETE` semantics across two tables, could not express the symmetry the
  unique constraint needs, and every FK would have to point at a table the wall forbids
  relating to.
- **Guarding the closed-pair immutability in Python rather than in a trigger.** Rejected in
  favour of the trigger, matching the `catalog.guard_event_write` precedent: a closed pair must
  stay closed even against a write that bypasses the ORM.
- **An index on `ConflictPair` over the pair columns.** Rejected: the conflict list and the
  Pulse Card indicator both read a user's *open* pairs, which the `(user_id, status)` index
  serves. An index over the unordered pair would duplicate the unique constraint's index.
- **Revoking `UPDATE`/`DELETE` on the audit table from `ep_personal` entirely.** Rejected: the
  table is shared with the framework's own audit rows and the grant is scoped per table, so the
  migration revokes on the audit table and the trigger guards the rest.

### Security

- **The append-only audit table is enforced at the database, not in the application.**
  `personal.forbid_history_mutation` raises `restrict_violation` on any `UPDATE` or `DELETE`,
  and the migration additionally revokes `UPDATE`/`DELETE` on the table from `ep_personal`.
  `test_grants.py` asserts the runtime role gets exactly `InsufficientPrivilege` — not a
  generic failure — and `test_audit_entry_delete_rejected` proves the trigger fires for a
  delete.
- **The migration asserts its own grants applied.** The `GRANTS` block ends with a
  `has_table_privilege` check that raises if `ep_personal` still holds `UPDATE` or `DELETE` on
  the audit table. A migration that silently failed to revoke would fail loudly at apply time
  rather than at first use. `test_migration_privilege_assertion_fails_when_revoke_missing`
  imports the migration module and proves the assertion raises when the revoke is absent.
- **No cross-schema FK exists in either direction.** `personal` has no `USAGE` on `catalog`, so
  a FK to a catalog table could not even be created by the runtime role; and the wall test
  asserts, against `information_schema`, that no FK in `personal` targets `catalog` and none in
  `catalog` targets `personal`.
- **No user input reaches an interpreter.** The models declare choices and check constraints;
  the IANA timezone name is validated at the command boundary (item ⑤), because a database
  check cannot see the timezone database — the model docstring says so explicitly.

### Architecture

- **AD-3 (the schema wall).** All four tables live in `personal`; `catalog` holds none of them.
  The `event_id` on `SavedEvent` is a plain `UUIDField` — the structural proof is that
  `field.remote_field is None`, which the test asserts alongside
  `not isinstance(field, models.ForeignKey)`.
- **AD-16 (write ownership).** `personalization` owns `PersonalEvent`, `SavedEvent` and
  `ConflictPair`; `delivery` owns `REMINDER_PLAN`. `test_personal_event_declares_no_reminder_plan_field`
  asserts no field on `PersonalEvent` mentions a reminder plan, so the ownership boundary
  cannot be quietly crossed by a future column.
- **AD-5 (audit).** `PersonalizationAuditEntry` extends the shared `AuditEntry`, so the actor
  is stored by value and the table is append-only.
- **AD-15 (retention).** Each of the four models declares a `retention_category`; `manage.py check`
  passes with `eventpulse.E003`/`E004` armed, which is the standing proof that no concrete
  model is left undeclared.
- **AD-6 (UTC).** `start_utc`/`end_utc` are the storage truth and `start_time_tz` carries the
  IANA zone the user meant; the check constraint holds the interval coherent
  (`end_utc >= start_utc`, or open-ended).
- **AD-21 (conflict semantics).** The 15-minute overlap threshold lives in `domain/conflict.py`
  from item ② and is not duplicated in the model layer. The model only holds the *record* of a
  detected conflict — `status`/`resolution`/`resolved_at` — and the check constraints encode
  the three legal shapes of that state.
- **Import contracts.** `make lint-imports` reports **13 kept, 0 broken**; `models-personalization`
  and `domain-pure` both hold.
- **`manage.py check`** passes with no issues and nothing silenced.

### Project Tooling Used

- **ruff**: `backend/pyproject.toml` (`ruff check`, `ruff format --check`)
- **import-linter**: `backend/pyproject.toml` (`make lint-imports`)
- **pytest / pytest-django**: `backend/pyproject.toml` (full suite + coverage gates)
- **Django system checks**: `python manage.py check`, `makemigrations --check --dry-run`
- **Vitest**: `frontend/package.json` (regression check — no frontend source touched)

### Standards Referenced

- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`
- `.specs-fire/standards/constitution.md`
- `.specs-fire/standards/tech-stack.md`
- `.specs-fire/standards/system-architecture.md`

### Verification Performed

| Check | Command | Result |
|-------|---------|--------|
| Backend suite | `cd backend && uv run pytest -q -p no:randomly` | 1795 passed, 0 failed, 0 skipped |
| Backend coverage | `cd backend && uv run pytest -q --cov --cov-report=term` | 99.11% total; `domain/` 100%; `apps/personalization/models.py` 100%; 80% gate met |
| Frontend suite | `cd frontend && pnpm vitest run` | 51 passed / 9 files |
| Python lint | `cd backend && uv run ruff check` | All checks passed |
| Format | `cd backend && uv run ruff format --check` | 255 files already formatted |
| Auto-fix diff | `cd backend && uv run ruff check --fix --diff` | no output — no auto-fixes available |
| Import contracts | `make lint-imports` | 13 kept, 0 broken |
| Django checks | `uv run python manage.py check` | no issues (0 silenced) |
| Migrations in sync | `uv run python manage.py makemigrations --check --dry-run` | No changes detected |
| Migration reverse | `DJANGO_DB_ROLE=owner ... migrate personalization --database=default zero` | applied cleanly, then re-applied with `make migrate` |

### Verdict

**Approved.** The four models hold the invariants the database can hold, and everything the
database cannot hold is deferred to the command layer (item ⑤) with the obligation written
down rather than implied. The wall, the ownership boundary, the retention declaration and the
append-only audit table are each proven by a test that fails if the guarantee is broken — the
structural tests read metadata rather than behaviour, so a future "helpful" `ForeignKey` breaks
the build instead of quietly making a cross-schema join possible.

The four auto-fixes were re-verified by the full suite (1795 passing) and the coverage gates
(`domain/` 100%, `apps/personalization/models.py` 100%, overall 99.11%).

---

## Work Item: delivery-reminder-plan-owner

### Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 1 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 1 | 0 | 0 |
| Testing | 1 | 0 | 0 |
| **Total** | **3** | **0** | **0** |

**Tests Status**: Passing — 1853/1853 backend, 0 failed, 0 skipped. `domain/` coverage 100%,
`apps/delivery/services/` coverage 100%.

### Files Reviewed

- `backend/apps/delivery/models.py` (created) — `ReminderPlan` and `DeliveryAuditEntry`
- `backend/apps/delivery/migrations/0001_initial.py` (created) — the schema, the append-only trigger, the grants
- `backend/apps/delivery/services/reminder_plans.py` (created) — the published service
- `backend/apps/delivery/services/audit.py` (created) — `write_audit`
- `backend/shared/constants.py` (modified) — `CUSTOM_SLOT_PREFIX`, `REMINDER_PLAN_MAX_SLOTS`
- `backend/config/settings.py` (modified) — `SILENCED_SYSTEM_CHECKS`
- `backend/tests/delivery/factories.py` (created) — the two factories
- `backend/tests/delivery/test_models.py` (created) — 8 tests
- `backend/tests/delivery/test_reminder_plans.py` (created) — 24 tests
- `backend/tests/delivery/test_ownership.py` (created) — 9 tests
- `backend/tests/delivery/test_triggers_and_grants.py` (created) — 8 tests
- `backend/tests/delivery/test_audit.py` (created) — 4 tests
- `backend/tests/wall/test_schema_placement.py` (modified) — the delivery tables' placement

### Auto-Fixed Issues

#### 1. [Blocking, found in testing] The slot-count check constraint never rejected anything

The first implementation used `models.Q(slots__len__lte=4)`. Django's `JSONField` has **no**
`__len` lookup, so it resolved through the generic string-length lookup and rendered:

```sql
CHECK (((slots -> 'len'::text) <= '4'::jsonb))
```

That reads a **key** named `"len"` out of the JSON value. For an array like `["1d","1hr"]` it
yields `NULL`, and a CHECK that evaluates to `NULL` **passes** — the bound would have accepted
any number of slots, silently, forever. The constraint was green and the rule was absent.

Fixed with `jsonb_array_length`, the function that actually means "the number of elements in
this array". The `output_field=BooleanField()` is load-bearing: without it Django's
`CheckConstraint` rejects the `Q` outright, and with the `RawSQL` nested in a `Q` the schema
editor raises "Cannot filter against a non-conditional expression". The applied constraint is
now `CHECK ((jsonb_array_length(slots) <= 4))`, verified against the live database, and
`test_reminder_plan_rejects_a_fifth_slot` proves it rejects.

#### 2. [Architecture] `target_kind` was an unvalidated string

The service took `target_kind: str`. Django's `choices` are not enforced on save, so a caller
could pass `"calendar_event"` and the row would be written with a kind nothing else
understands — the plan would exist but could never be found again by a reader that filters on
a valid kind.

Fixed by making the kind a closed set at the command boundary: the commands now accept
`ReminderPlan.TargetKind | str` and normalise through `_target_kind_value`, which raises
`UnknownTargetKindError` for anything outside the two kinds. The enum member is the
preferred form, exactly as `Event.Status` is used in
`apps/ingestion/services/event_writes.py`. Three tests cover it.

#### 3. [Code Quality] The offset lookup constructed an enum member from a possibly-custom slot

`slot_offsets` called `ReminderSlot(slot)`. A custom slot is not a member of the enum, so
the constructor raised `ValueError: 'custom:mine' is not a valid ReminderSlot` instead of
returning "no offset". Fixed by looking the mapping up by the slot's own value: `ReminderSlot`
is a `StrEnum`, so its members hash as their string values and
`REMINDER_SLOT_OFFSET.get(slot)` finds the named tiers and finds nothing for a custom slot —
which is the intended behaviour, since a custom slot's offset is the caller's to supply.

### Findings Considered and Rejected

- **A nullable FK per target type** (`personal_event_id`, `saved_event_id`). Rejected: it would
  need two FKs to tables owned by another module — which `models-delivery` forbids `delivery`
  from importing — plus `ON DELETE` semantics across both, and it could not express "exactly
  one target". The `(target_kind, target_id)` pair needs no relation at all.
- **A separate `REMINDER_PLAN_SLOT` table.** Rejected: four nullable columns or a child table
  both add a second table and a join for a bounded list of at most four values. The list is
  the value; a JSON array is the honest shape, and AD-7's send key wants the slot *value*.
- **Fixed columns for the four named tiers plus one custom column.** Rejected: the custom
  slot's id does not fit a column of a known length, and the plan's slot order would be lost.
- **`SILENCED_SYSTEM_CHECKS` for `models.W045` being too broad.** Considered and accepted.
  `W045` is one warning *class* about one technique, the technique is deliberate, and its only
  use site carries a comment saying why. The alternative — leaving a warning in
  `manage.py check` — is worse, and the project treats a clean check as a gate.
- **The service writing an audit row on an idempotent re-attach.** Considered and kept: the
  audit row records the `created` flag, so a reader can tell a first attach from a repeat,
  and an audit log that skipped no-op calls would under-record what the user asked for.

### Security

- **The audit table is append-only in the database.** `personal.forbid_delivery_history_mutation`
  raises `restrict_violation` on any `UPDATE` or `DELETE`, and the migration additionally
  revokes `UPDATE`/`DELETE` from `ep_personal`. The runtime role's privileges were verified
  against the live database: `UPDATE` false, `DELETE` false, `INSERT` true.
- **The migration asserts its own grants applied.** The `GRANTS` block ends with a
  `has_table_privilege` check that raises if `ep_personal` still holds `UPDATE` or `DELETE`.
  `test_migration_privilege_assertion_fails_when_revoke_missing` imports the migration module
  and proves the assertion raises when the revoke is absent — a migration that silently
  failed to revoke would fail loudly at apply time rather than at first use.
- **The trigger lives in `personal`, not `catalog`.** `ep_personal` has no `USAGE` on
  `catalog`, so a trigger function living there would fail to resolve at the moment it fires
  — for *every* write, not just a forbidden one. The copy in `personal` is simpler too: the
  audit table has no settable column, so it needs no `TG_ARGV[0]` branch.
- **No user input reaches an interpreter.** The slot list is a bounded set of known strings;
  an unknown slot is rejected with a `ValidationError` before it reaches the database.
- **A custom slot's id is validated by prefix.** A slot that is neither a named tier nor
  prefixed with `custom:` is rejected, so a slot can never be confused with a named tier in
  AD-7's send key.

### Architecture

- **AD-16 (write ownership) is enforced, not merely intended.** The `models-delivery` import
  contract holds (13 kept, 0 broken), and `test_ownership.py` reads the import graph directly:
  no module outside `apps/delivery` imports `apps.delivery.models`. The test walks the AST of
  every Python file under `apps/`, so a future "helpful" direct import breaks the build rather
  than quietly making a cross-module write possible.
- **The service hands over plain data.** `PlanSlots` is a frozen dataclass, not a model
  instance, so a caller never holds a reference to `apps.delivery.models`.
  `test_the_service_does_not_leak_the_model_to_its_callers` pins it.
- **AD-3 (the wall) holds.** The plan references the personal-side record by value; both
  target kinds live in `personal`, and `catalog` holds none of the delivery tables.
  `test_no_foreign_key_crosses_from_personal_to_catalog` still passes.
- **AD-15 (retention).** The plan declares `ACCOUNT_CONTENT`; `manage.py check` passes with
  `eventpulse.E003`/`E004` armed.
- **AD-7 (relative offsets).** The plan holds relative offsets only, never absolute times, so
  a postponement re-propagated by AD-17 moves the computed due times without touching the
  plan.
- **AD-5 (audit).** Every command writes an audit row in the same transaction as its
  mutation, and `write_audit` refuses to run outside a personal transaction.

### Project Tooling Used

- **ruff**: `backend/pyproject.toml` (`ruff check`, `ruff format --check`)
- **import-linter**: `backend/pyproject.toml` (`make lint-imports`)
- **pytest / pytest-django**: `backend/pyproject.toml` (full suite + coverage gates)
- **Django system checks**: `python manage.py check`, `makemigrations --check --dry-run`
- **Vitest**: `frontend/package.json` (regression check — no frontend source touched)

### Standards Referenced

- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`
- `.specs-fire/standards/constitution.md`
- `.specs-fire/standards/tech-stack.md`
- `.specs-fire/standards/system-architecture.md`

### Verification Performed

| Check | Command | Result |
|-------|---------|--------|
| Backend suite | `cd backend && uv run pytest -q -p no:randomly` | 1853 passed, 0 failed, 0 skipped |
| Backend coverage | `cd backend && uv run pytest -q --cov --cov-report=term` | 99.14% total; `domain/` 100%; `apps/delivery/services/` 100%; 80% gate met |
| Frontend suite | `cd frontend && pnpm vitest run` | 51 passed / 9 files |
| Python lint | `cd backend && uv run ruff check` | All checks passed |
| Format | `cd backend && uv run ruff format --check` | 265 files already formatted |
| Import contracts | `make lint-imports` | 13 kept, 0 broken |
| Django checks | `uv run python manage.py check` | no issues (1 silenced: `models.W045`) |
| Migrations in sync | `uv run python manage.py makemigrations --check --dry-run` | No changes detected |
| Migration reverse | `DJANGO_DB_ROLE=owner ... migrate delivery --database=default zero` | applied cleanly, then re-applied with `make migrate` |
| Applied constraints | `pg_get_constraintdef` on `personal.delivery_reminderplan` | `CHECK ((jsonb_array_length(slots) <= 4))` |
| Runtime role grants | `has_table_privilege('ep_personal', ...)` | UPDATE false, DELETE false, INSERT true |

### Verdict

**Approved.** The plan holds the invariants the database can hold, the ownership boundary is
enforced by a contract and proven by a test that reads the import graph, and the offset
arithmetic has exactly one source.

One thing the review changed the shape of: the slot-count bound. The first implementation
produced a check constraint that looked right in the model and was green in every test run,
and would nevertheless have accepted a plan with any number of slots. It is worth naming
plainly: a constraint that never fires is worse than no constraint, because it reads as
protection. The live-database check (`pg_get_constraintdef`) is now part of this item's
verification, so the rule is proved where it is enforced rather than where it is declared.

The three auto-fixes were re-verified by the full suite (1853 passing) and the coverage gates
(`domain/` 100%, `apps/delivery/services/` 100%, overall 99.14%).

## Work Item: personalization-write-services

### Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 2 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 3 | 0 | 0 |
| Testing | 1 | 0 | 0 |
| **Total** | **6** | **0** | **0** |

**Tests Status**: Passing — 1969/1969 backend, 0 failed, 0 skipped. `domain/` coverage 100%,
`apps/personalization/services/` coverage 100%.

### Files Reviewed

- `backend/apps/personalization/services/audit.py` (created) — the `personal` audit writer
- `backend/apps/personalization/services/conflicts.py` (created) — detection on write, the side
  normalisation, the pair lifecycle
- `backend/apps/personalization/services/conflict_resolutions.py` (created) — the forced choice
- `backend/apps/personalization/services/personal_events.py` (created) — create / update / delete
- `backend/apps/personalization/services/saved_events.py` (created) — save / unsave / re-stamp
- `backend/shared/constants.py` (modified) — `CONFLICT_SCAN_WINDOW`
- `backend/tests/personalization/test_personal_events.py` (created) — 27 tests
- `backend/tests/personalization/test_saved_events.py` (created) — 17 tests
- `backend/tests/personalization/test_conflict_resolutions.py` (created) — 18 tests
- `backend/tests/personalization/test_conflicts.py` (created) — 24 tests
- `backend/tests/personalization/test_audit.py` (created) — 7 tests
- `backend/tests/personalization/test_ownership.py` (created) — 12 tests

### Auto-Fixed Issues

#### 1. [Blocking, found in testing] A candidate with no id was compared against itself, and the pair row was written with a NULL side

`Candidate.id` is `None` before the row exists. The scan did `.exclude(pk=candidate.id)`
unconditionally — but `pk=None` excludes **nothing**, so the candidate's own row came back
into the scan and was compared against itself. The pair row was then written with
`right_id=NULL`, and the database refused it:

```
IntegrityError: null value in column "right_id" of relation
"personalization_conflictpair" violates not-null constraint
```

Two fixes, both in `conflicts.py`:

- The exclusion is now applied **only when the candidate has an id** — there is nothing to
  exclude before the row exists.
- `record_detected_conflicts` now **skips** a conflict whose sides have no id, rather than
  writing a row it cannot fill. A pair names both sides by id; a conflict found against an
  unsaved candidate has nothing to point at. The commands call the recorder *after* the row
  is written, so every recorded conflict has two real ids in practice — the skip is the
  safety net for a caller that breaks that order.

`test_a_conflict_found_against_an_unsaved_candidate_is_not_written` pins it.

#### 2. [Blocking, found in testing] `delete_new` cleared the pair instead of resolving it

The first implementation ran the deletion first, and `delete_personal_event` →
`close_pairs_for_side` closed the pair as `cleared_by_state_change` with a **NULL**
resolution. The acceptance criterion says the opposite: "The `ConflictResolution` value is
recorded for **every** prompt, including those resolved by editing or deleting."

The model's `conflict_pair_status_ck` settles the question: a `cleared_by_state_change` pair
must carry a NULL resolution, so a pair the user answered can never be a cleared one. The
resolution is now recorded **first**, as `status=resolved` + the resolution, for every
answered prompt whatever the button; the deletion then goes through `delete_personal_event`
as before, so there is still one path to delete an event and one audit trail for it.

`cleared_by_state_change` is reserved for a pair that ended because a side went away
*without* the user answering — an unrelated delete, an unsave, a propagation-driven close.
This is the distinction the whole status column exists to record, so it is worth stating
plainly: **answered** and **ended** are different facts, and only one of them is a
resolution.

#### 3. [Blocking, found in testing] `update_saved_event_snapshot` detected new conflicts but never closed the stale ones

The propagation-driven snapshot update re-ran detection, so a *new* overlap was recorded —
but the pair that the moved event no longer clashed with stayed `active`. The `/conflicts`
list would then claim a clash that was not there.

The fix is a new shared helper, `reconcile_pairs_for_side`, in `conflicts.py`: it re-judges
the active pairs naming one side and closes the ones that no longer overlap, as
`cleared_by_state_change` with a NULL resolution. Both call sites use it — the snapshot
update, and `personal_events._reconcile_pairs` for a user's edit.

#### 4. [Code Quality] A redundant third catalog read in `save_event` — and the wrong one

The first implementation read the catalog's version *before* opening the transaction and
again after the commit. The pre-transaction read was not merely redundant — it was wrong. A
version read before the transaction opened could be older than the one the snapshot records,
which would make the post-commit check meaningless. AD-21's protocol is the two-read shape:

```
t0   transaction.atomic(using=PERSONAL)
       read catalog_event.version   (inside the tx, on the catalog alias)
       write SavedEvent(start_utc, end_utc, version)
       write ConflictPair rows; write_audit
t1   commit
t2   read catalog_event.version    (non-transactional)
t3   if t2.version > t0.version: → the snapshot is stale
```

The read that stamps the snapshot is **inside** the transaction, which narrows the race
window to the write itself. The module docstring, the design doc (D27/D28 and the sequence
diagram) and `plan.md` were all updated to match the code.

#### 5. [Code Quality] `MissingTimezoneError` inherited `InvalidIntervalError`

Wrong base class: it must be a `ValidationError` so `config/errors.py` maps it to a 422
rather than a 500. The base was corrected and the import updated.

#### 6. [Testing] `unsave_event` wrote a NULL `target_id`

The audit row read `saved.id` *after* `saved.delete()`, and the id was gone:

```
IntegrityError: null value in column "target_id" of relation
"personalization_auditentry" violates not-null constraint
```

The id is now captured before the delete.

### Findings Considered and Rejected

- **A `dismiss` resolution.** Rejected, and it is more than a preference: FR-58 says "There
  is no 'dismiss' resolution — the user must make an explicit choice", and the AC says the
  `ConflictResolution` value is recorded for **every** prompt. A dismissable prompt would
  produce a closed pair with a NULL resolution and no recorded answer — exactly the shape
  that `cleared_by_state_change` already means, so it would make the status column
  ambiguous. `test_there_is_no_dismiss_resolution` pins that the enum has no such member.
- **Recording the resolution *after* the action.** Rejected. If the action fails, the pair
  would still be `active` and the user would be prompted again for a choice they had
  already made; and if the action succeeds but the recording fails, the choice would be lost
  while its effect persisted. Recording first means the audit trail shows what the user
  chose even if the follow-up edit lands later.
- **Calling `delivery`'s plan attach outside the `personal` transaction.** Rejected: a plan
  failure would then leave an event with no plan — a state FR-20 says does not exist. The
  nested `atomic` on the same alias is a savepoint, so the two commit or roll back together.
  `test_a_plan_failure_rolls_the_creation_back` monkeypatches `attach_default_plan` to raise
  and asserts that neither the event nor the plan survives.
- **Attaching the default plan on every edit.** Rejected: FR-20's default is a property of
  *creation*, and re-attaching on edit would reset a plan the user had customised through
  FR-9's picker. `test_updating_an_event_does_not_reset_the_plan` pins that the slots stay
  as the user left them.
- **Deleting the reminder plan row when the event is deleted.** Rejected: AD-16 gives
  `REMINDER_PLAN` to `delivery`, and `personalization` may not write it. Deleting the plan is
  `delivery`'s call, and it has no such command yet. The leftover row is inert, and
  `test_deleting_an_event_leaves_the_reminder_plan_row` pins that it stays.
- **Joining `catalog` to render the Timeline or the conflicts list.** Rejected: AD-21 says
  the personal side holds its own snapshot and never joins `catalog`. The saved event's
  snapshot carries the catalog's `event_version`, so staleness is detectable without a join.
- **Repairing a stale snapshot inside `save_event`.** Rejected: the repair is a separate
  command (`update_saved_event_snapshot`) with an explicit version rule, and AD-21 says the
  save *requests* re-propagation rather than doing it. The save reports `stale` and writes
  an audit row saying so; the repairing service lands in this item so the AD-17 job is a
  thin caller later.
- **Closing a pair as `cleared_by_state_change` when the user deletes the new event.** This
  was the first implementation and it was wrong — see auto-fix 2.

### Security

- **No user input reaches an interpreter.** The zone goes through `canonical_zone`, the
  interval through the model's own check, and the resolution through the `ConflictPair.
  Resolution` enum. Anything outside the three the prompt offers is refused with a
  `ValidationError` before it reaches the database.
- **Ownership is checked on every command.** A pair that is not the caller's raises
  `ConflictPairNotFoundError`; a personal event that is not the caller's raises
  `PersonalEventNotFoundError`; a save that is not the caller's raises
  `SavedEventNotFoundError`. None of them leak whether another user's record exists — the
  message is the same either way.
- **A floating local time is refused, not guessed.** `MissingTimezoneError` demands an
  explicit IANA zone, because the user's wall clock and the event's zone are not the same
  thing and guessing one from the other is how an event lands an hour out on the wrong side
  of a DST boundary.
- **The audit row carries no free text.** `details` is a JSON mapping of ids, kinds, versions
  and ISO instants — never a name the user typed. `actor_label` holds a system job name, and
  a user actor is stored by id only.

### Architecture

- **AD-16 (write ownership) is enforced by a contract and proven by a test.** The
  `models-delivery` contract holds (13 kept, 0 broken), and `test_ownership.py` reads the
  services' own source: `personal_events.py` imports exactly `attach_default_plan` from
  `delivery` and never `ReminderPlan`; `saved_events.py` imports exactly `get_public_event`
  from `ingestion` and never `apps.ingestion.models`.
- **AD-3 (the wall) holds.** The catalog is read through `ingestion`'s published read
  interface, which hands over plain data (`PublicEvent`). `personalization` never imports the
  catalog's models, so the wall holds without either side knowing the other's models.
- **AD-21 (detection on write, never at render).** Every command that changes a time calls
  `detect_conflicts`; nothing in a read path does. The Pulse Card, the Timeline and
  `/conflicts` all read the same `CONFLICT_PAIR` rows, so the indicator is symmetric by
  construction.
- **AD-21 (the save race).** The protocol is the two-read shape above, and the staleness is
  **reported** — in the return value and in an audit row — rather than silently accepted or
  silently repaired.
- **AD-21 (immutability).** A closed pair is never re-opened: `record_detected_conflicts`
  skips a closed pair, and `resolve_conflict` refuses one with
  `ConflictAlreadyResolvedError`. The check comes before the write, so the user never sees
  a raw `RestrictViolation` from the database's trigger.
- **AD-5 (audit).** Every command writes its audit row in the same transaction as its
  mutation, and `write_audit` refuses to run outside a `personal` transaction —
  `test_a_row_written_in_a_rolled_back_transaction_does_not_survive` proves the row goes
  with the mutation.
- **AD-7 (the version only rises).** `update_personal_event` increments with `F("version") + 1`
  so the bump is atomic against a concurrent write.
- **One overlap function.** The rules live in `domain/conflict.py`; the service layer decides
  *which* events to compare and *what* to write, and never re-implements a rule. `domain/` is
  at 100% coverage.

### Project Tooling Used

- **ruff**: `backend/pyproject.toml` (`ruff check`, `ruff format --check`)
- **import-linter**: `backend/pyproject.toml` (`make lint-imports`)
- **pytest / pytest-django**: `backend/pyproject.toml` (full suite + coverage gates)
- **Django system checks**: `python manage.py check`, `makemigrations --check --dry-run`
- **Vitest**: `frontend/package.json` (regression check — no frontend source touched)

### Standards Referenced

- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`
- `.specs-fire/standards/constitution.md`
- `.specs-fire/standards/tech-stack.md`
- `.specs-fire/standards/system-architecture.md`

### Verification Performed

| Check | Command | Result |
|-------|---------|--------|
| Backend suite | `cd backend && uv run pytest -q -p no:randomly` | 1969 passed, 0 failed, 0 skipped |
| Backend coverage | `cd backend && uv run pytest -q --cov --cov-report=term` | 99.21% total; `domain/` 100%; `apps/personalization/services/` 100%; 80% gate met |
| Frontend suite | `cd frontend && pnpm vitest run` | 51 passed / 9 files |
| Python lint | `cd backend && uv run ruff check` | All checks passed |
| Format | `cd backend && uv run ruff format --check` | 276 files already formatted |
| Import contracts | `make lint-imports` | 13 kept, 0 broken |
| Django checks | `uv run python manage.py check` | no issues (1 silenced: `models.W045`) |
| Migrations in sync | `uv run python manage.py makemigrations --check --dry-run` | No changes detected |

### Verdict

**Approved.** The write services hold the boundaries the architecture depends on — one owner
per table, one transaction per mutation, one audit row per change — and each boundary is
proven by a test rather than asserted in a docstring.

Two things the review changed the shape of, and both are worth naming. The first was the
**status column's meaning**: a pair the user answered and a pair that ended because the
world moved are different facts, and the first implementation let the second overwrite the
first. The second was the **save race**, where an extra catalog read looked like harmless
belt-and-braces but was in fact the one read that could make the staleness check meaningless.

The auto-fixes were re-verified by the full suite (1969 passing) and the coverage gates
(`domain/` 100%, `apps/personalization/services/` 100%, overall 99.21%).

---

## Work Item ⑥ — `personal-events-api`

**Reviewed:** the personal-events HTTP surface — create, list, get, edit, delete, and answer
a conflict prompt.

### Summary

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | The list endpoint used the *response* schema as its query model, so `?starts_after=…` was accepted and ignored | **High** | Fixed — dedicated `PersonalEventListQuery` |
| 2 | The resolve endpoint passed a placeholder `new_side_id`, so `existing_side_id` was always null and `delete_new` would delete the wrong event | **High** | Fixed — `new_side_id` moved into the request body |
| 3 | The create endpoint returned a bare value against `response={201: …}`, which Ninja answers with a 500 | **High** | Fixed — `ninja.Status(201, …)` |
| 4 | The 409's conflict payload was typed as the generic `ErrorOut`, whose `details` is an untyped dict — invisible to a generated client | **High** | Fixed — `SchedulingConflictOut` narrows `details` |
| 5 | `@router.delete(...)` was reported as a direct ORM write by the architecture checker | Medium | Fixed — decorator position excluded, both sides pinned by tests |
| 6 | `api.py` imported `apps.personalization.models`, against the module's own stated rule | Medium | Fixed — the side-kind constants are published from the service layer |
| 7 | The personal list has no pagination, while the catalog list does | Low | Left — the personal list is bounded by one user's own events; item ⑦ may revisit |

### Files Reviewed

| File | Verdict |
|---|---|
| `backend/apps/personalization/api.py` | Thin, as intended: resolves the user, parses the body, calls the service, projects plain data back. No ORM, no models import, no business rule. |
| `backend/apps/personalization/schemas.py` | Pydantic shapes with `from_*` projections. The action set is a closed `Literal`, so a dismiss is inexpressible. |
| `backend/apps/personalization/auth.py` | One function, so the onboarding intent replaces it in one place. |
| `backend/domain/errors.py` | `SchedulingConflictError(ConflictError)` — 409 *and* carries `details`. |
| `backend/config/api.py` | The personal router is registered with the opposite comment to the catalog's, because the two surfaces differ in exactly that way. |
| `backend/apps/personalization/services/conflicts.py` | The published side-kind constants. |
| `backend/tests/architecture/checkers.py` | The decorator exemption. |

### Findings Considered and Rejected

- **A `HttpError` for the 409.** It cannot carry `details`, and the shared handler flattens
  it to `{code, message}` — the conflict payload would have been lost. A *domain* error
  maps to 409 along the MRO *and* carries `details`. Rejected.
- **Letting the API layer infer the new side from the pair row.** The row stores both sides
  sorted, so it cannot say which side is newer. The client's request is the only place that
  asymmetry exists, and it has to come back with the answer. Rejected.
- **Inferring the new side by kind.** The pair could be personal↔saved, in which case the
  new side is not necessarily the personal one. The body carries the id; the endpoint is
  about personal events, so the kind is fixed by the endpoint. Rejected.
- **A `PersonalEventListOut` that also carried the query fields.** One schema serving two
  purposes would put `starts_after` in the *response* body too — the client would read a
  field that is never meaningful there. Rejected.

### Security

- **The user id comes from the session, never from the payload.** No endpoint accepts one,
  and `test_no_endpoint_accepts_a_user_id` posts one and proves the event still belongs to
  the signed-in user.
- **A cross-user attempt is 404, not 403.** A 403 confirms the record exists; a 404 does
  not, so the endpoint cannot be used to probe for another user's ids. Pinned for get, edit,
  delete and resolve.
- **An anonymous request is 401 on all six endpoints**, with the project's calm message.
- **The `delete_new` action cannot name a saved event.** The body carries an id, not a kind;
  the endpoint resolves conflicts on personal events, so the side is fixed.

### Architecture

- **The layer is thin.** It never imports `apps.personalization.models` and never touches
  the ORM. Both are proven by tests, not just stated.
- **The conflict detection runs on write** (AD-21) — the create command detects, and the
  endpoint only projects what the service found. There is no render-time detection anywhere
  in the surface.
- **The 409 does not complete the flow.** The pair is `active` with no resolution, and
  `test_a_conflicting_create_leaves_the_pair_active` pins that there is no code path that
  completes a conflicted creation without a `ConflictResolution`.
- **The three actions come from the service's `RESOLUTIONS_BY_KIND`**, so the schema cannot
  offer a dismiss. The OpenAPI enum is a closed set of four values, and the conflict
  payload's `actions` list has exactly three entries.

### Tooling

- The architecture checker's blanket "any attribute call" rule was correct for `save` and
  `bulk_create` but wrong for a route decorator. Narrowing it to exclude decorator position
  keeps the check strict where it matters: `test_a_write_next_to_a_route_decorator_is_still_reported`
  proves a real `obj.delete()` in the same function is still caught.

### Verification

| Check | Command | Result |
|---|---|---|
| Backend suite | `cd backend && uv run pytest -q --cov` | **2023 passed**, 99.28% total; `domain/` 100% |
| New module coverage | `coverage report --include='apps/personalization/*,domain/errors.py'` | **100%** across all 16 files |
| Python lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | 279 files already formatted |
| Import contracts | `uv run lint-imports` | 13 kept, 0 broken |
| Django checks | `uv run python manage.py check` | no issues (1 silenced) |
| Migrations in sync | `uv run python manage.py makemigrations --check --dry-run` | No changes detected |
| Frontend suite | `pnpm --dir frontend test` | 51 passed / 9 files |
| Frontend lint | `pnpm --dir frontend lint` / `typecheck` / `format:check` | clean |
| Contract | `make client` | `openapi.json` and `schema.ts` regenerated, committed |

### Verdict

**Approved.** The surface holds the two properties the personal data depends on: the user
comes from the session and cannot be talked out of by a payload, and a conflict cannot
complete without an explicit choice.

Three things the review changed the shape of, and all three are worth naming. The first was
the **list endpoint's query model** — a filter the client can send but the server ignores is
a contract that lies, and the schema had been quietly accepting one. The second was the
**409's payload**, which was reaching the client as an untyped dictionary: the frontend has
to render the three actions (FR-58), and it could not read a single field of them. The third
was the **architecture checker's decorator rule**, which had been quietly wrong about what a
write is — a route decorator registers an endpoint; it does not delete a record.

The auto-fixes were re-verified by the full suite (2023 passing) and the coverage gates
(`domain/` 100%, `apps/personalization/` 100%, overall 99.28%).

---

## Work Item ⑦ — `saved-events-api`

### Summary

The HTTP surface over saving and unsaving a public catalog event: three endpoints on the
session-based personal router, backed by a new `list_saved_events` service read.

The review's attention went to three things: **whether the saveability rule lives in one
place**, **whether the response can be shown to the user without lying**, and **whether
the contract the client generates from is honest**.

### Files Reviewed

| File | Change |
|---|---|
| `backend/apps/ingestion/services/catalog_read.py` | `get_public_event` gained an optional `now` bound. |
| `backend/apps/catalog/api.py` | The detail endpoint now bounds by `now`. |
| `backend/apps/personalization/services/saved_events.py` | `SaveResult.created`; the first read bounded, the race check left unbounded; `list_saved_events` added. |
| `backend/apps/personalization/schemas.py` | `SavedEventOut`, `SavedEventListOut`, `SavedEventListQuery`. |
| `backend/apps/personalization/api.py` | The three endpoints. |
| `backend/tests/personalization/test_saved_events_api.py` | New — 30 tests. |
| `backend/tests/personalization/test_saved_events.py` | +4 tests for the list read. |
| `backend/tests/api/test_catalog_read_service.py` | +2 tests for the `now` bound. |
| `backend/tests/api/test_catalog_api.py` | +1 test for the detail endpoint's bound. |
| `frontend/lib/api/openapi.json`, `schema.ts` | Regenerated by `make client`; never hand-edited (AD-19). |

### Auto-Fixed Issues

1. **The published catalog read contradicted its own docstring.** `catalog_read`'s module
   docstring states that "only published, non-superseded, **upcoming** events are visible",
   but `get_public_event` never applied the "upcoming" half — only `list_public_events`
   did. The detail endpoint therefore returned events that had already started, and a save
   could take an event into a personal calendar after it had begun.

   **Fixed at the source**, not in the caller. `get_public_event` took an optional `now`;
   passing it applies the bound, and not passing it skips it. The alternative — filtering
   in `personalization` — would have left the catalog's rule living in two places, one of
   them private and one of them a copy that could drift.

2. **The save's first read was unbounded.** With the rule now available, the service's
   saveability read passes `now`, so an event an hour old is a 404 and nothing is written.

3. **The race check would have failed saves for the wrong reason.** The *second* read —
   the one that asks only whether the version moved — is deliberately **not** bounded.
   Re-applying the "not started" rule there would fail a save whose event merely *began*
   while the write was in flight, which is not a reason to refuse and not a reason to lose
   the snapshot. The two reads answer different questions; the code says so at each.

4. **The API could not distinguish a first save from a repeat.** `update_or_create` returns
   the existing row on a repeat, but the service did not report it. `SaveResult.created`
   now carries it, and the endpoint answers 201 then 200 (D59).

5. **The list endpoint ignored the bounds its own service accepted.**
   `list_saved_events` took `starts_after`/`starts_before`; the API never passed them. A
   filter the client can send and the server ignores is a contract that lies — the same
   defect item ⑥ found in the personal-events list. Fixed with `SavedEventListQuery` and a
   wire-through, and pinned by a test at both the service and the HTTP layer.

6. **Three race stubs took the old read's signature.** The two pre-existing stubs in
   `test_saved_events.py` and the new one in `test_saved_events_api.py` all had to accept
   `now`. Fixed.

7. **A test's `Event` update needed the catalog's write guard.** The catalog requires
   `event_version + 1` on any lifecycle change to an `Event`; the race test's update
   bumped only the version it was simulating and tripped the guard. Fixed by moving the
   start time and the version together.

### Findings Considered and Rejected

- **Moving the save endpoints onto the catalog router** (`POST /api/public-events/{id}/save`,
  the path the work item names). Rejected: the catalog router is **session-free** (AD-12),
  and a save writes personal data. A mutation of personal data cannot sit on a router whose
  every other endpoint works without a session — the surface would be lying about two of
  its endpoints. The path still names the **catalog** event's id, because the resource
  being saved is a catalog event; the router is the personal one, because that is where the
  session and the scoping live. Recorded as D56.

- **Answering 404 with a null-titled row for a save whose catalog event has gone.** Rejected:
  the display fields come from the catalog at read time, so such a row has no title to
  show, and a half-empty card is worse than an omission. The list omits it and reports the
  count in `omitted`, so the client can tell the user "2 saved events are no longer
  available" — nothing is hidden, and nothing is rendered half-empty. Recorded as D57.

- **Presenting a stale snapshot as current.** Rejected: AD-21's race is real, and a wrong
  time on the user's calendar is worse than an admitted one. The response carries `stale`
  and `current_version`, and the service writes the audit entry that asks for
  re-propagation. The client is told; it is never misled. Recorded as D58.

- **Filtering the saved list by the catalog's current start time instead of the
  snapshot's.** Rejected: the list returns the snapshot's time, so a bound applied to a
  different value would let the filter and the item disagree about which event is which.
  The bound applies to the snapshot, and the test says so.

### Security

- **The scoping cannot be talked out of by a payload.** Every request resolves exactly one
  user from the session (`apps.personalization.auth`), and no endpoint accepts a user id
  as input. `test_no_endpoint_accepts_a_user_id` posts a `user_id` in the body and asserts
  the save belongs to the signed-in user.
- **Cross-user access reads as absence, not refusal.** Un-saving another user's save is a
  **404, not a 403** — a 403 would confirm that the resource exists. The other user's save
  survives the attempt.
- **The catalog is reached through a published interface.** `apps.personalization.api`
  imports `apps.ingestion.services.catalog_read`, never `apps.ingestion.models`; a test
  parses the module's AST and asserts the import is absent.
- **The endpoints are session-based.** All three refuse an anonymous request with 401 and
  the shared `not_authenticated` shape.

### Architecture

- **No cross-schema write.** The save writes only `personal`; the catalog is read only.
  The catalog's event id is stored **by value** in the personal row, so no foreign key
  spans the two schemas (AD-3).
- **The service reads the personal side only.** The display fields are the API layer's to
  resolve, one event at a time — which is what lets a vanished catalog event be counted
  rather than hidden.
- **Conflict detection runs on write** (AD-21). The save command detects; the endpoint
  only projects what the service found. There is no render-time detection on this surface.
- **The 409's payload is typed.** `SchedulingConflictOut` narrows `ErrorOut.details`, so a
  generated client can read the three actions (FR-58) — the same fix item ⑥ made for the
  personal-event create.
- **The layer stays thin.** The API resolves the user, parses the body, calls the
  published service, and projects plain data. It never touches the ORM directly, and never
  imports `apps.personalization.models`.

### Tooling

- The client's `openapi.json` and `schema.ts` were regenerated with `make client` and are
  committed. `test_committed_openapi_schema_matches_the_live_api` fails loudly if they
  drift.
- `ruff check` found an unused import in the new test file and `ruff format` found two
  files to reflow; both were fixed and re-verified.

### Standards Referenced

- **AD-3** — the two schemas are separate; the catalog id is stored by value.
- **AD-5** — every mutation writes an audit entry in the same transaction.
- **AD-6** — times cross the wire as UTC plus an explicit IANA zone.
- **AD-9** — no raw source payload and no unstripped internal field in a response.
- **AD-12** — the session-free rule applies to the *public* catalog; the personal surface
  is session-based by design, and the review kept the save off the catalog router for
  exactly this reason.
- **AD-19** — the contract is generated; the client is never hand-edited.
- **AD-21** — the snapshot is read from the personal side, the conflict is detected on
  write, and the save re-reads the catalog's version after the commit and reports the
  staleness.
- **FR-33** — a public event can be taken into the user's own calendar.
- **FR-58** — a clashing save returns the three actions, and the flow cannot complete
  without an explicit choice.

### Verification

| Check | Command | Result |
|---|---|---|
| Backend suite | `cd backend && uv run pytest -q --cov` | **2060 passed**, 99.29% total; `domain/` 100% |
| Python lint | `uv run ruff check` | All checks passed |
| Format | `uv run ruff format --check` | 280 files already formatted |
| Import contracts | `uv run lint-imports` | 13 kept, 0 broken |
| Django checks | `uv run python manage.py check` | no issues (1 silenced) |
| Migrations in sync | `uv run python manage.py makemigrations --check --dry-run` | No changes detected |
| Frontend suite | `pnpm --dir frontend vitest run` | 51 passed / 9 files |
| Frontend lint | `pnpm --dir frontend lint` / `typecheck` / `format:check` | clean |
| Contract | `make client` | `openapi.json` and `schema.ts` regenerated, committed |

### Verdict

**Approved.** The surface holds the three properties the saved-events data depends on: the
user comes from the session and cannot be talked out of by a payload, a save of something
that is not public is refused rather than half-done, and a snapshot that may be behind the
catalog is *reported* as behind rather than shown as current.

The review's most consequential find was not in `personalization` at all — it was that
`ingestion`'s published read contradicted its own documented rule. Fixing it at the
source, rather than copying the rule into a caller, is the difference between one place
that owns the rule and two that could drift.

Two gaps are recorded rather than hidden: **FR-48's free-tier quota is not enforced**
(the `identity` subscription model does not exist yet, and the save endpoints are where it
will land), and **AD-17's propagation job is not implemented** (the protocol is exposed
and audited; the job that acts on it is later work). Neither is a defect in this item —
both are named in the work item's own boundaries — but the Pro tier intent needs the first
one to know where to put it.
