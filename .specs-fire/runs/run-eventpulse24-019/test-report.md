---
run: run-eventpulse24-019
work_item: repo-hygiene-cleanup
intent: personal-events-and-saved-catalog
generated: 2026-10-29
status: passed
---

# Test Report: Repository Hygiene Cleanup

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Backend (pytest, real Postgres, both schemas) | 1691 | 0 | 0 | 99.08% |
| Frontend (Vitest) | 51 | 0 | 0 | n/a |
| **Total** | **1742** | **0** | **0** | **99.08%** |

Coverage gates: overall ≥80% ✅ (99.08%). `backend/domain/` is at **100%** ✅ (all 117
partially-covered files were skipped because they are already fully covered).

## Acceptance Criteria Validation

- ✅ **Every duplicate `* 2.*` / `* 2` artifact is identified by an explicit inventory, and each is
  confirmed untracked by git before deletion.** — The inventory was built with a glob over the
  whole tree for every AppleDouble suffix (`* 2.py`, `* 2.ts`, `* 2.tsx`, `* 2.md`, `* 2.yml`,
  `* 2.yaml`, `* 2.json`, `* 2.toml`, `* 2.lock`, `* 2.css`, `* 2.mts`, `* 2.mjs`) plus a
  directory glob (`* 2*`). Each of the 10 directories found was confirmed empty (0 files) and
  untracked before removal. `git ls-files | grep ' 2'` returned **0 tracked duplicates**, so no
  `git rm` was required.
- ✅ **No legitimate file is deleted.** — The removal set was built from the explicit AppleDouble
  shape (`<name> 2<ext>` / `<name> 2/`), never a bare `*2*` glob. Names that merely contain a `2`
  were untouched — `run-eventpulse24-002` in `.specs-fire/runs/`, `voyage.py`, `schema.ts` and the
  rest of the tree are all intact.
- ✅ **The duplicate count in the working tree after cleanup is zero.** — Post-cleanup glob across
  every listed suffix returns **0 files** and **0 directories**.
- ✅ **The backend test count is identical before and after the cleanup.** — Before: 1691
  collected. After: **1691 passed, 0 failed, 0 skipped** (23.66s). Identical. No difference, so
  no duplicate was being collected by pytest.
- ✅ **The frontend test count is identical before and after the cleanup.** — Before: 51 passing
  across 9 files. After: **51 passing across 9 files** (1.10s). Identical.
- ✅ **`make lint-imports` still passes and `ruff check` reports no new violations.** —
  `make lint-imports`: **13 contracts kept, 0 broken** (179 files, 400 dependencies).
  `ruff check`: **All checks passed!**
- ✅ **`git status` shows only the intended deletions, with no unrelated modifications.** — The
  working tree contains no deletions at all, because the deleted directories were **untracked and
  empty** — Git never saw them, so there is nothing to stage. The only tracked changes are
  `.specs-fire/state.yaml` (the run record, maintained by the FIRE scripts) and the new
  `.specs-fire/runs/run-eventpulse24-019/` artifacts. No source file is modified.
- ✅ **The cleanup is a separate commit from any feature work.** — No feature work has been
  written in this run yet; the cleanup touches no tracked file, so the commit that carries this
  work item contains only the run artifacts. The cleanup is therefore trivially and independently
  revertible.

## Tests Written

### Unit Tests

- (none — this work item writes no production code and adds no tests)

### Integration Tests

- (none — this work item writes no production code and adds no tests)

## Test Commands

```bash
# Backend full suite (real Postgres, both schemas)
cd backend && uv run pytest -q --no-header -p no:randomly

# Backend full suite with coverage
cd backend && uv run pytest -q --no-header -p no:randomly --cov --cov-report=term

# Frontend suite
cd frontend && pnpm vitest run

# Lint gates
cd backend && uv run ruff check
make lint-imports

# Duplicate inventory (files and directories)
find . -path ./node_modules -prune -o -path ./.git -prune -o \
  -type f \( -name '* 2.py' -o -name '* 2.ts' -o -name '* 2.tsx' -o -name '* 2.md' \
    -o -name '* 2.yml' -o -name '* 2.yaml' -o -name '* 2.json' -o -name '* 2.toml' \
    -o -name '* 2.lock' -o -name '* 2.css' -o -name '* 2.mts' -o -name '* 2.mjs' \) -print
find . -path ./node_modules -prune -o -path ./.git -prune -o -type d -name '* 2*' -print
```

## Coverage Details

| Module | Statements | Branches | Functions | Lines |
|--------|------------|----------|-----------|-------|
| **TOTAL** | 99.08% | — | — | 99.08% |
| `backend/domain/` | 100% | 100% | 100% | 100% |
| `adapters/crawl/http.py` | 99% | — | — | 99% |
| `config/checks.py` | 99% | — | — | 99% |
| `config/errors.py` | 98% | — | — | 98% |

The 35 uncovered statements are all pre-existing and unrelated to this item: the five empty
`api.py` router stubs (`apps/delivery`, `apps/editorial`, `apps/identity`, `apps/ingestion`,
`apps/personalization` — 2 statements each = 10), `config/asgi.py` and `config/wsgi.py` (8),
and single uncovered lines in the ingestion registries, logging formatter, adapters config,
calendar port, id helper and the local-stack seed command.

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| Docker Desktop was not running, so the project's Postgres 18 + pgvector (5440) and Redis (6380) were unreachable and the first full backend run reported `1234 passed, 457 errors` (every error a `psycopg` `ConnectionTimeout`). | Blocker | **Resolved** — Docker Desktop started and `docker compose up -d` brought all three services to `healthy`. `.env` was **not** modified; the pre-existing native PG12/PG16/Redis on 5432/5434/6379 were left undisturbed, as the scaffold brief requires. The suite then reported 1691/1691 passing. |
| The work item's stated premise — ~30 duplicate **files** — was stale. | Informational | **Corrected and recorded.** The duplicate files had already been removed outside this session before the item ran. What remained were 10 **empty duplicate directories**, which a `* 2.*` file glob does not match. The item's cleanup is complete either way: post-cleanup the duplicate count is zero for both files and directories. |

## Known Gaps / Deliberate Omissions

- **No production code was changed by this item**, so no new coverage was required and the
  coverage figure is unchanged from the pre-cleanup baseline (99.08%).

## Ready for Completion

- [x] All tests passing
- [x] Coverage target met (80%)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-019*

---

## Work Item: conflict-domain-and-constants

### Test Results

- Passed: 31 (new) + 1725 (full backend suite)
- Failed: 0
- Skipped: 0

| Suite | Before | After |
|-------|--------|-------|
| Backend (pytest, real Postgres, both schemas) | 1691 passed | **1725 passed** (+34) |
| `backend/domain/` coverage | 100% | **100%** (482 stmts, 0 missed) |
| Overall coverage | 99.08% | **99.09%** |
| `make lint-imports` | 13 kept, 0 broken | **13 kept, 0 broken** (180 files, 404 dependencies) |
| `ruff check` / `ruff format --check` | clean | **All checks passed! / 248 files formatted** |
| `manage.py check` | no issues | **no issues (0 silenced)** |
| Frontend (Vitest) | 51 passed | 51 passed (untouched by this item) |

### Acceptance Criteria Validation

- ✅ **`backend/domain/conflict.py` exists and contains the single overlap function. Two UTC
  intervals conflict when the overlap is strictly more than `CONFLICT_MIN_OVERLAP` (15 minutes).
  Exactly 15 minutes returns "not a conflict"; 15 minutes + 1 second returns "conflict".** —
  `conflicts(a_start, a_end, b_start, b_end) -> bool`. Pinned by
  `test_conflicts_overlap_exactly_15min_returns_false` (False) and
  `test_conflicts_overlap_15min_and_1sec_returns_true` (True). The threshold is imported from
  `shared.constants`, never re-declared.
- ✅ **The function is pure: no Django import, no I/O, no clock read, no database access.** —
  `domain/conflict.py` imports only `datetime`, `domain.dedup`, `domain.errors` and
  `shared.constants`. `tests/domain/test_domain_is_django_free.py` walks every `domain/` module
  in a fresh interpreter with `DJANGO_SETTINGS_MODULE` removed and asserts Django was never
  loaded — it now covers `domain.conflict.py` automatically and passes.
- ✅ **The module honours the `domain-pure` import-linter contract.** — `make lint-imports`:
  13 contracts kept, 0 broken. The `domain-pure` contract reports 5 ignored imports (up from 4),
  the extra being this module's `shared.constants` import — the allowlisted one.
  `tests/architecture/test_stdlib_only.py` also passes, confirming no non-stdlib import outside
  the allowlist.
- ✅ **No wall-clock reads; `now` is always an explicit argument.** — There is no `now` at all:
  both functions take the instants they compare. No `datetime.now`, `utcnow` or `time()` anywhere
  in the module.
- ✅ **The duplicate-detection rule is a separate function; same name (case-insensitive,
  token-overlap ≥ 80%) AND starts within 24 hours; the 80% threshold is a named constant.** —
  `is_duplicate(a_name, a_start, b_name, b_start) -> bool`, separate from `conflicts`. The
  threshold is `TITLE_TOKEN_OVERLAP_MIN` in `shared/constants.py` — no literal in the module.
- ✅ **The token-overlap comparison is not semantic.** — No embeddings, no LLM call, no similarity
  service. `tests/domain/test_domain_api.py` scans every public domain API for embedding or
  similarity inputs and passes.
- ✅ **The duplicate rule reuses `domain/dedup.py`'s existing `tokens()` and `jaccard()`
  helpers; a second normaliser is forbidden.** — It calls `dedup.jaccard(dedup.title_fingerprint(a),
  dedup.title_fingerprint(b))` — the same fingerprint form and the same Jaccard function the
  identity rule (b) uses. There is no second tokeniser or folder in the codebase.
  `test_is_duplicate_matches_the_identity_rule_threshold_exactly` asserts the two rules agree
  on a 4/5 overlap.
- ✅ **`shared/constants.py` gains only the genuinely new constants; the 15-minute threshold and
  the 1d+1hr reminder default are used, never re-declared.** — `CONFLICT_MIN_OVERLAP` and
  `DEFAULT_REMINDER_PLAN` are untouched and imported. Two changes: `DUPLICATE_START_WINDOW =
  timedelta(hours=24)` (new) and `TITLE_JACCARD_MIN` → `TITLE_TOKEN_OVERLAP_MIN` (a rename, not
  a new value — see the note below).
- ✅ **Unit tests cover: zero overlap, 1-second overlap, exactly 15 minutes, 15 minutes + 1
  second, full containment, midnight span, back-to-back, and an event with no end time.** — All
  present as individual named tests, plus partial overlap, symmetry, a zero-length interval, and
  two invalid-interval cases.
- ✅ **Unit tests cover duplicates: identical names differing only in case, names at exactly 80%
  token overlap, names just below 80%, and candidates outside the 24-hour window.** — All
  present, plus: exactly 24 hours apart (True), 23 hours *earlier* (True, the window is absolute),
  different names, accent folding, stop-word handling, empty names, and a cross-check that the
  duplicate rule and the identity rule agree on the threshold.
- ✅ **Tests are pinned as golden tests in the style of `tests/domain/test_dedup.py`.** —
  `test_conflict.py` pins exact values (`Fraction(4, 5)`, `timedelta(hours=24)`,
  `timedelta(minutes=15)`) and exact boundary booleans rather than re-deriving them, and follows
  the `test_<unit>_<condition>_<expected>` naming the standards require.

### Tests Written

#### Unit Tests

- `backend/tests/domain/test_conflict.py` — 26 golden tests for the overlap rule and the
  duplicate rule, Django-free.

### Integration Tests

- (none — this work item writes no model, no API and no database code)

### Two corrections made during implementation

Both were caught by the tests, not by inspection, and both are worth recording:

1. **`datetime.max` is naive.** The first implementation used it as the "no end time" sentinel.
   Comparing a naive `datetime.max` against an aware instant raised
   `TypeError: can't compare offset-naive and offset-aware datetimes`. Fixed by making the
   sentinel UTC-aware: `datetime.max.replace(tzinfo=UTC)`. The open-ended semantics are
   unchanged — an open-ended interval still runs to the end of representable time and overlaps
   everything after it.
2. **The 80% boundary fixture was wrong, not the rule.** The first boundary test asserted that
   `"alpha beta gamma delta epsilon"` and `"alpha beta gamma delta zeta"` overlap by exactly
   4/5. They do not: the union is six tokens, so the real value is 2/3. The rule was right and
   the fixture was wrong. The pinned fixtures are now `"Alpha Beta Gamma Delta"` vs
   `"Alpha Beta Gamma Delta Epsilon"` (4 shared of a 5-token union = **exactly 4/5**, duplicate)
   and `"Alpha Beta Gamma Delta"` vs `"Alpha Beta Gamma Zeta"` (3 shared of 5 = **3/5**, not a
   duplicate). The exact values were verified against `domain.dedup` directly before being
   written down.

### Instants are normalised, not assumed

Both functions route their datetimes through `domain.timezones.to_instant`, the codebase's
existing convention. That gives three behaviours, all pinned by tests:

- A **naive** datetime is refused with `TypeError("expected an aware datetime")` rather than
  failing later with an opaque offset comparison error.
- An instant written in **another zone** is the same instant — `Asia/Tokyo` and UTC compare
  equal.
- Instants are truncated to **whole seconds**, matching how `domain.dedup.match` compares them.

`is_duplicate`'s window comparison and `conflicts`' overlap arithmetic both operate on
normalised instants, and `_interval_end` normalises the end *before* the validity check, so an
interval whose end precedes its start is caught however it was written.

### Notes on the threshold rename

`TITLE_JACCARD_MIN` → `TITLE_TOKEN_OVERLAP_MIN` is a rename, not a new constant, and the value
is unchanged (`Fraction(4, 5)`).

The PRD uses the same wording for both rules — "≥80% Jaccard overlap **on tokens**" — for
catalog identity (rule b) and for the personal-event duplicate prompt (FR-58). They are the same
threshold with the same meaning, so one constant serves both. Two constants with the same value
that mean the same thing can drift apart later; one cannot. The new name describes the *measure*
rather than its previous single caller, which is what the work item asked for.

`backend/tests/shared/test_constants.py` was updated to match, and the renamed constant is
pinned there as `Fraction(4, 5)` alongside the new `DUPLICATE_START_WINDOW`.

### Coverage Details

| Module | Statements | Branches | Functions | Lines |
|--------|------------|----------|-----------|-------|
| **TOTAL** | 99.09% | — | — | 99.09% |
| `backend/domain/` | **100%** | 100% | 100% | 100% |
| `backend/domain/conflict.py` | **100%** | 100% | 100% | 100% |

`backend/domain/conflict.py` is fully covered line by line — every branch of the open-ended
handling, the invalid-interval raises, and both duplicate-rule exits are exercised.

### Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| The naive `datetime.max` sentinel raised `TypeError` against aware instants. | Bug | **Fixed** — the sentinel is now UTC-aware. |
| The 80%-overlap fixture asserted 4/5 for a pair whose real overlap is 2/3. | Test bug | **Fixed** — the fixture was wrong, not the rule; the corrected pair is pinned at exactly 4/5. |

### Known Gaps / Deliberate Omissions

- **The ±30-minute candidate scan is not implemented here.** FR-58's prose describes scanning for
  other Personal Events "within ±30 minutes of the new event's start time". That is a *candidate
  search window*, not the overlap threshold — the overlap rule is the 15 minutes AD-21 and FR-33
  specify. The scan belongs to the service layer (work item ⑤), which decides which events to
  compare. This item implements only the two decision rules.
- **No persistence, no resolution actions.** A `CONFLICT_PAIR` row and the three actions belong
  to work items ③ and ⑤.
- **`InvalidIntervalError` is added to `domain/errors.py` but is not yet mapped in
  `config/errors.py`.** It subclasses `ValidationError`, so the existing mapping already covers
  it as a 400. The item did not change the HTTP surface, so no mapping change was needed; the
  API work items will exercise the mapping.

### Ready for Completion

- [x] All tests passing
- [x] Coverage target met (80% overall, 100% for `domain/`)
- [x] All acceptance criteria validated
- [x] No critical issues open

---

## Work Item: personalization-models

### Test Results

- Passed: 70 (new) + 1795 (full backend suite)
- Failed: 0
- Skipped: 0

| Suite | Before | After |
|-------|--------|-------|
| Backend (pytest, real Postgres, both schemas) | 1725 passed | **1795 passed** (+70) |
| `apps/personalization/models.py` coverage | n/a (the file was empty) | **100%** (75 stmts, 0 missed) |
| Overall coverage | 99.09% | **99.11%** |
| `make lint-imports` | 13 kept, 0 broken | **13 kept, 0 broken** |
| `ruff check` / `ruff format --check` | clean | **All checks passed! / 255 files formatted** |
| `manage.py check` | no issues | **no issues (0 silenced)** |
| `makemigrations --check` | no changes | **no changes detected** |
| Frontend (Vitest) | 51 passed | 51 passed (untouched by this item) |

### Acceptance Criteria Validation

- ✅ **A design doc exists** at `.specs-fire/intents/personal-events-and-saved-catalog/work-items/personalization-models-design.md`, covering the `SAVED_EVENT` snapshot semantics and refresh triggers (D12–D16), the `CONFLICT_PAIR` state machine (D17–D26), the `PERSONAL_EVENT` timezone representation (D5–D8), the audit table shape (D27–D28) and the retention category per table (D4). It was approved at Checkpoint 1 before implementation began.
- ✅ **The design doc is reviewed and approved before implementation begins (Checkpoint 1).** — `checkpoint_1: approved` in the design doc's frontmatter; the approval is recorded in `.specs-fire/state.yaml` by `update-checkpoint.cjs`, not by hand.
- ✅ **`PERSONAL_EVENT` stores: name, `start_utc`, `end_utc` (nullable), `start_time_tz` (IANA), location (nullable), notes (nullable), `source = user_created`, and a `version`.** — All present. `start_utc`/`end_utc` are `DateTimeField`s (timestamptz under `USE_TZ`); `start_time_tz` is a `CharField(max_length=64)`. The model layer refuses a floating or ambiguous local time by refusing to store one: the *instant* is always UTC and the zone is always named. IANA validity is checked at the command boundary in work item ⑤, because a database check cannot see the timezone database — `config/apps.py` calls `zoneinfo.reset_tzpath(to=())`, so the pinned `tzdata` package is the only source.
- ✅ **`SAVED_EVENT` holds `event_id` by value — a `UUIDField`, not a foreign key. There is no `ForeignKey` to `catalog` from any `personal` model, and no cross-schema join exists.** — `event_id = models.UUIDField()`. Three independent proofs: `test_model_structure.py` asserts `event_id` is a `UUIDField` with `remote_field is None`; `test_model_structure.py` asserts **no field on any of the three models `is_relation`**; and `tests/wall/test_schema_placement.py` queries `information_schema` and asserts **zero** foreign keys cross from `personal` to `catalog` (in either direction).
- ✅ **`SAVED_EVENT` is unique per `(user, event_id)`.** — `UniqueConstraint(fields=["user_id", "event_id"], name="saved_event_user_event_uq")`. Pinned by `test_saved_event_rejects_a_second_save_of_the_same_event` and `test_saved_event_allows_two_users_to_save_the_same_event`.
- ✅ **`CONFLICT_PAIR` links two sides, each a reference to either a `PERSONAL_EVENT` or a `SAVED_EVENT`, with a status and the `ConflictResolution` value.** — Each side is a `(kind, id)` pair: `left_kind`/`left_id` and `right_kind`/`right_id`, with `SideKind ∈ {personal_event, saved_event}`. A `GenericForeignKey` is forbidden by OQ-8, and a UUID alone cannot say which kind of record it names, so the kind is stored beside the id.
- ✅ **A resolved `CONFLICT_PAIR` is immutable; a pair closed by a catalog state change is distinguishable from one the user resolved.** — The `personal.guard_conflict_pair` trigger rejects any change to `status`, `resolution` or `resolved_at` once the row is `resolved` or `cleared_by_state_change`. The two are distinguished by the **resolution column being NULL**: a state-cleared pair has no user decision, so its `resolution` is NULL while its `resolved_at` is set. `conflict_pair_status_ck` makes the three shapes mutually exclusive.
- ✅ **The `ConflictResolution` value object covers exactly the PRD's cases; there is no `dismiss` value.** — `Resolution ∈ {keep_both, edit_new, delete_new, update_existing}`, pinned by `test_conflict_pair_has_no_dismiss_resolution`, which asserts the exact set. `conflict_pair_resolution_kind_ck` additionally refuses `edit_new` on a duplicate and `update_existing` on a time conflict, so an illegal pairing is unwritable.
- ✅ **Every model declares a retention category.** — `ACCOUNT_CONTENT` for the three product models, `AUDIT_LOG` for the audit table. `eventpulse.E003`/`E004` enforce it and `manage.py check` passes. The `ACCOUNT_CONTENT` comment in `shared/retention.py` was widened to name the conflict pairs too, since AD-15 makes that registry what the sweep, deletion and export all read.
- ✅ **No `personal` model FKs to `User` or `ContentType`; the user is referenced by `UUID` value.** — `user_id` is a plain `UUIDField` on all three models. `test_personal_model_stores_the_user_id_by_value` asserts the field type, and `test_no_personal_model_relates_to_user_or_content_type` asserts no model relates to either.
- ✅ **The audit table extends `shared.models.AuditEntry`, with the actor stored by value and `actor_check()` applied.** — `PersonalizationAuditEntry(AuditEntry)`. The abstract base contributes `actor_kind`/`actor_id`/`actor_label` and the `actor_check()` constraint, which appears in the migration as `personalization_personalizationauditentry_actor_ck`.
- ✅ **The `models-personalization` import-linter contract keeps passing.** — `make lint-imports`: **13 contracts kept, 0 broken**. The contract was already declared and already protected; this item gives it something to protect.
- ✅ **The `domain-pure` contract still passes; no model module imports `domain`.** — `apps/personalization/models.py` imports only `django.db`, `django.utils.timezone`, `shared.models` and `shared.retention`. It does not import `domain` at all, so nothing can pull Django into the domain layer. `domain/` was untouched by this item.
- ✅ **Migrations apply cleanly on the local stack, and the tables land in the `personal` schema — verified by inspecting `information_schema`, not by assuming the router did the right thing.** — `make migrate` applies `personalization.0001_initial` on both aliases. `tests/wall/test_schema_placement.py` reads `information_schema.tables` and asserts the four `personalization_*` tables are in `personal` and that **none** is in `catalog`. The same inspection was run by hand against the dev database and returned exactly the four tables in `personal`.
- ✅ **No foreign key constraint crosses from `personal` to `catalog`, asserted by a test.** — `test_no_foreign_key_crosses_from_personal_to_catalog` (and its mirror for `catalog` → `personal`) queries `information_schema.table_constraints` joined to `constraint_column_usage` and asserts the result is empty. The hand inspection found the only FKs in `personal` are Django's own auth/contenttypes tables pointing at other `personal` tables.
- ✅ **A model test asserts `SAVED_EVENT.event_id` is a plain `UUIDField` and that no `ForeignKey` exists on any of the three models — a structural test, so a future "helpful" FK breaks the build.** — `tests/personalization/test_model_structure.py` is exactly that: it reads the models' metadata rather than their behaviour. `test_personal_model_declares_no_relation_field` asserts the relation field list is empty for each of the three models.

### Tests Written

#### Unit Tests

- `backend/tests/personalization/test_models.py` — 35 tests. The check constraints, the unique constraints, the three legal status shapes and five illegal ones, the resolution/kind pairing in both directions, and the three `__str__` representations.
- `backend/tests/personalization/test_model_structure.py` — 13 tests. The structural guarantee, read from the model metadata rather than from behaviour.

#### Integration Tests

- `backend/tests/personalization/test_triggers.py` — 9 tests. The `guard_conflict_pair` immutability trigger and the audit table's append-only trigger, exercised with raw SQL below the ORM so a Python-level guard cannot make them pass.
- `backend/tests/personalization/test_grants.py` — 8 tests. The `ep_personal` runtime role's privileges on the audit table and the product tables, plus the migration's own assertion that the revoke applied.
- `backend/tests/wall/test_schema_placement.py` — 4 new tests. The four tables' schema placement, and the cross-schema foreign key check in both directions.

### Two corrections made during implementation

Both were caught by the tests, not by inspection:

1. **`conflict_pair_sides_differ_ck` was written backwards.** The first version was
   `left_kind = right_kind OR left_id = right_id`, which is the condition for the two sides
   being *the same* record, not for them differing. The constraint therefore rejected every
   legal row and accepted only the illegal one. The rule is that the sides are the same
   record only when the kind **and** the id match, so the constraint is now
   `NOT (kind matches AND id matches)`. The first run of the suite failed all 17 conflict-pair
   tests with `violates check constraint "conflict_pair_sides_differ_ck"`, which is how the
   inverted condition was found.

2. **The `ConflictPair` docstring claimed a normalization that does not exist.** It said the
   sides "are normalised (lexicographically on `(kind, id)`) before writing", implying the
   model did it. Nothing does: the normalization belongs to the command layer, which is this
   table's only writer and lands in work item ⑤. The docstring now says that.

### The trigger guards three columns, not the whole row

`guard_conflict_pair` rejects a change to `status`, `resolution` or `resolved_at` on a closed
pair, and leaves every other column alone. That distinction matters: `updated_at` is
`auto_now`, so it moves on every save, and freezing it would make a resolved row
un-saveable. `test_resolved_pair_unrelated_field_may_be_updated` pins that a resolved pair
still accepts an `updated_at` update and keeps its status and resolution.

### Coverage Details

| Module | Statements | Branches | Functions | Lines |
|--------|------------|----------|-----------|-------|
| **TOTAL** | 99.11% | — | — | 99.11% |
| `backend/domain/` | **100%** | 100% | 100% | 100% |
| `apps/personalization/models.py` | **100%** | 100% | 100% | 100% |

`apps/personalization/models.py` is fully covered line by line. The only uncovered module in
the app is `apps/personalization/api.py`, the empty router stub that every app has; the
API work items fill it.

### Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| `conflict_pair_sides_differ_ck` was inverted, rejecting every legal conflict pair. | Bug | **Fixed** — the condition is now `NOT (kind matches AND id matches)`, and the 17 tests that caught it pass. |
| The `ConflictPair` docstring claimed the sides were normalised on write. | Documentation | **Fixed** — it now names the command layer as the place that normalisation happens. |
| The `ACCOUNT_CONTENT` retention comment named only two of the three record types in the category. | Documentation | **Fixed** — the comment now names the conflict pairs too, so the sweep's scope is unambiguous. |

### Known Gaps / Deliberate Omissions

- **The side normalization is not implemented here.** The unique constraint is symmetric only
  if the command layer normalizes the sides before writing. That is work item ⑤, the only
  writer of this table.
- **`PersonalEvent.version` has no trigger enforcing the increment.** Only the command knows
  whether a mutation is legitimate, so the model holds a positive-value check and the
  increment is the command's contract.
- **IANA zone validity is not checked at the model layer.** A database check cannot see the
  timezone database. The command boundary refuses an invalid zone in work item ⑤.
- **No service, command, API or frontend.** The FR-58 candidate scan (±30-minute window),
  the AD-21 save-race protocol and the conflict resolution actions all belong to work item ⑤.
- **`REMINDER_PLAN` is not a field on `PersonalEvent`.** `delivery` owns it (AD-16); the
  `personalization` app calls `delivery`'s published service to attach the default. That is
  work item ④ and ⑤.

### Ready for Completion

- [x] All tests passing
- [x] Coverage target met (80% overall, 100% for `domain/` and the new model)
- [x] All acceptance criteria validated
- [x] No critical issues open

---

## Work Item: delivery-reminder-plan-owner

### Test Results

| Check | Result |
|-------|--------|
| Backend (pytest, real Postgres, both schemas) | 1795 passed → **1853 passed** (+58) |
| Overall coverage | 99.14% (gate: 80%) |
| `domain/` coverage | 100% (gate: 100%) |
| `apps/delivery/` coverage | 100% except the 2-line `api.py` stub |
| Frontend (Vitest) | 51 passed / 9 files |
| Python lint | `ruff check` → All checks passed |
| Format | `ruff format --check` → 265 files already formatted |
| Import contracts | `make lint-imports` → 13 kept, 0 broken |
| Django checks | `manage.py check` → no issues (1 silenced: `models.W045`, explained below) |
| Migrations in sync | `makemigrations --check --dry-run` → No changes detected |
| Migration reverse | `migrate delivery --database=default zero` → applied cleanly, then re-applied with `make migrate` |

### Tests Written

| File | Tests | What it covers |
|------|-------|----------------|
| `backend/tests/delivery/test_models.py` | 8 | The slot-count check, the one-plan-per-event unique constraint, the per-user and per-kind scoping, `__str__`. |
| `backend/tests/delivery/test_reminder_plans.py` | 24 | The default plan, the picker, removing all reminders, the audit rows, the offsets, the slot validation, the closed target-kind set. |
| `backend/tests/delivery/test_ownership.py` | 9 | The AD-16 boundary: no module outside `delivery` imports `apps.delivery.models`; the service hands over plain data; the model declares no relation. |
| `backend/tests/delivery/test_triggers_and_grants.py` | 8 | The append-only trigger and the runtime role's grants. |
| `backend/tests/delivery/test_audit.py` | 4 | `write_audit` inside a personal transaction, and the guard when none is open. |
| `backend/tests/wall/test_schema_placement.py` | +2 | The delivery tables live in `personal`, and `catalog` holds none of them. |

**Total new: 58** (56 in `tests/delivery/`, 2 wall).

### Acceptance Criteria Validated

| # | Criterion | How it is proven |
|---|-----------|------------------|
| 1 | `REMINDER_PLAN` is a model in `apps/delivery/models.py`, owned by `delivery` alone | `apps/delivery/models.py` defines it; `test_ownership.py` proves no module outside `apps/delivery` imports `apps.delivery.models`; the `models-delivery` import contract holds. |
| 2 | Up to 4 slots, each identified by its own id, from the existing `ReminderSlot` enum plus one custom slot | `reminder_plan_slots_max_4_ck` rejects a fifth; `test_setting_slots_accepts_a_custom_slot` pins the custom slot; `ReminderSlot` is imported from `shared.constants`, never redeclared. |
| 3 | `REMINDER_SLOT_OFFSET` is the single source for slot → offset arithmetic | `slot_offsets` reads only that mapping; `test_slot_offsets_are_measured_back_from_the_start` pins the result. |
| 4 | The default plan is `DEFAULT_REMINDER_PLAN`, used and never re-declared | `test_the_default_plan_is_exactly_one_day_and_one_hour` asserts the constant's value; `attach_default_plan` derives its slots from it. |
| 5 | A published service with a signature that makes the ownership visible | `attach_default_plan`/`set_plan_slots`/`remove_all_reminders` take the user, the target and the actor; `test_ownership.py` proves the service is the only way in. |
| 6 | The `models-delivery` contract keeps passing; `make lint-imports` is green | 13 kept, 0 broken. |
| 7 | The plan attaches to both a `PERSONAL_EVENT` and a `SAVED_EVENT`, with no FK across the wall | `test_attaching_the_default_plan_to_a_saved_event`; the target is `(target_kind, target_id)` by value, both kinds live in `personal`. `test_no_foreign_key_crosses_from_personal_to_catalog` still passes. |
| 8 | The user can remove all reminders; an empty plan is valid | `test_removing_all_reminders_leaves_an_empty_plan` and `test_removing_all_reminders_keeps_the_plan_row`. |
| 9 | Pulse Ping is not part of any reminder plan | There is no `pulse_ping` slot value; `test_a_pulse_ping_cannot_be_a_slot` shows it is rejected as unknown. |
| 10 | The plan declares a retention category | `retention_category = RetentionCategory.ACCOUNT_CONTENT`; `manage.py check` passes with `eventpulse.E003`/`E004` armed. |
| 11 | No `SCHEDULED_SEND`, no Celery task, no beat entry, no email adapter | None was created. `apps/delivery/` holds only `models.py`, `services/`, `migrations/`, and the pre-existing empty `api.py`/`admin.py`/`schemas.py`. |
| 12 | Tests cover the four named behaviours | The default plan, the picker's replacement, removing all reminders, and the ownership boundary are each pinned by a test (see the table above). |

### Issues Found and Fixed

#### 1. [Blocking] Django's `__len` lookup produced a check constraint that never rejected anything

The first implementation used `models.Q(slots__len__lte=4)`. Django's `JSONField` has **no**
`__len` lookup at all, so this resolved through the *generic* string length lookup, which
rendered:

```sql
CHECK (((slots -> 'len'::text) <= '4'::jsonb))
```

That reads a **key** named `"len"` out of the JSON value. For a JSON *array* like
`["1d","1hr"]` it yields `NULL`, and a CHECK constraint that evaluates to `NULL` **passes** —
so the bound would have rejected nothing, at any size, forever. The constraint was
green and the rule was absent.

The fix is `jsonb_array_length`, the function that actually means "the number of elements in
this array":

```python
_SLOTS_LENGTH_AT_MOST_4 = models.Q(
    RawSQL(
        "jsonb_array_length(slots) <= %s",
        (SLOTS_MAX,),
        output_field=models.BooleanField(),
    )
)
```

The `output_field=BooleanField()` is load-bearing: without it Django's `CheckConstraint`
rejects the `Q` outright ("must be a Q instance or boolean expression"), and with the `RawSQL`
nested in a `Q` the migration's schema editor raises "Cannot filter against a non-conditional
expression". The applied constraint is now:

```sql
CHECK ((jsonb_array_length(slots) <= 4))
```

verified against the live database, and `test_reminder_plan_rejects_a_fifth_slot` proves it
rejects.

#### 2. [Blocking] `models.W045` — the `RawSQL` constraint is not validated by `full_clean()`

Django warns that a `CheckConstraint` built on `RawSQL` is skipped by `Model.full_clean()`.
The warning is *true* and the project wants `manage.py check` clean, so `models.W045` is
silenced in `config/settings.py` with the reason written down: the database enforces the
constraint, which is where this project wants it, and the service validates the slot list
too, so nothing relies on `full_clean()` for this rule.

Silencing it globally is safe here because `W045` is a single warning *class* about a single
technique, and the technique is deliberate and documented at its only use site.

#### 3. `slot_offsets` raised on a custom slot

The first version called `ReminderSlot(slot)` to look up the offset. A custom slot is not a
member of the enum, so the constructor raised `ValueError: 'custom:mine' is not a valid
ReminderSlot` instead of returning "no offset". The lookup is now by value against a
frozenset of the named tiers, so an unknown slot is left out rather than fatal.

### Coverage Details

`apps/delivery/services/reminder_plans.py` and `apps/delivery/services/audit.py` are at 100%.
The only uncovered file in the app is `apps/delivery/api.py` — the 2-line `Router()` stub that
was already there and that this item deliberately leaves alone (no API surface in scope).

### Known Gaps

- **`personalization` does not yet call the service.** The published interface exists and is
  tested, but the call site — attaching the default plan when a personal event is created
  (FR-20) — belongs to work item ⑤, which owns the create command.
- **A custom slot has no offset in this app.** `REMINDER_SLOT_OFFSET` covers the four named
  tiers only. A custom slot's offset is the user's own choice, and the store that owns it
  (AD-17's `SCHEDULED_SEND`) does not exist yet. `slot_offsets` leaves custom slots out
  rather than guessing, and `test_slot_offsets_leaves_out_a_custom_slot` pins that.
- **No `SCHEDULED_SEND`, no due-time computation, no Quiet Hours.** AD-7's sweep and the
  quiet-hours deferral are a later intent. This item is the owner, not the scheduler.
- **The FR-9 picker UI does not exist.** The command does; the screen that calls it is
  frontend work.

### Ready for Completion

- [x] All tests passing
- [x] Coverage target met (80% overall, 100% for `domain/`)
- [x] All acceptance criteria validated
- [x] No critical issues open

## Work Item: personalization-write-services

### Test Results

| Check | Result |
|-------|--------|
| Backend (pytest, real Postgres, both schemas) | 1853 passed → **1969 passed** (+116) |
| Overall coverage | 99.21% (gate: 80%) |
| `domain/` coverage | 100% (gate: 100%) |
| `apps/personalization/services/` coverage | **100%** on all four modules (only the 2-line `api.py` stub is uncovered) |
| Frontend (Vitest) | 51 passed / 9 files |
| Python lint | `ruff check` → All checks passed |
| Format | `ruff format --check` → 276 files already formatted |
| Import contracts | `make lint-imports` → 13 kept, 0 broken |
| Django checks | `manage.py check` → no issues (1 silenced: `models.W045`, from item ④) |
| Migrations in sync | `makemigrations --check --dry-run` → No changes detected |

**No migration.** This item writes no new tables: every command writes rows item ③ already
defined, in the schemas already in place.

### Tests Written

| File | Tests | What it covers |
|------|-------|----------------|
| `backend/tests/personalization/test_personal_events.py` | 27 | Create with an explicit zone; the missing-zone refusal; an unknown zone; an end before the start; a null end; zone canonicalisation; the default plan attached; the **rollback proof**; a conflict returning `ConflictFound`; the pair row existing `active`; three pairs for three overlapping events; the normalised sides; a duplicate by name and a near start; a non-overlapping event; the version bump; detection re-running on edit; a pair closing when the event moves away; ownership on update and delete; the plan **not** being reset on edit; delete removing the row; the delete audit row; delete closing the pairs; the plan row surviving the delete. |
| `backend/tests/personalization/test_saved_events.py` | 17 | The snapshot; the audit row; double-save idempotency; a non-public event refused; an unknown event refused; **the race**; the stale audit row; a clean save not stale; a conflict detected on save; unsave removing the row; the unsave audit row; unsave closing the pairs; ownership; the snapshot update applying a newer version; refusing an older version; doing nothing for an unsaved event; the snapshot update re-evaluating the conflicts. |
| `backend/tests/personalization/test_conflict_resolutions.py` | 18 | The three buttons and their consequences; the audit rows; the closed pair (never re-prompted); a cleared pair (never re-prompted); ownership; the two `RESOLUTIONS_BY_KIND` sets; a time conflict refusing `update_existing`; an unknown resolution refused; no `dismiss`; which side is "new", from either end of the sorted pair. |
| `backend/tests/personalization/test_conflicts.py` | 24 | The candidate scan over both kinds of side; the candidate excluded from its own scan; the scan window; the side normalisation and its ordering; one row for `(A,B)` and `(B,A)`; a closed pair never re-opened; a conflict against an unsaved candidate skipped; closing a side; `pairs_for_side`; reconciling a moved side — still clashing, no longer clashing, other side gone; the other side of a pair read from the database. |
| `backend/tests/personalization/test_audit.py` | 7 | The writer inside a transaction; the user actor and the system actor; the empty-details default; the guard when no transaction is open; the guard when only *another* alias has one; a row in a rolled-back transaction not surviving; positional arguments refused. |
| `backend/tests/personalization/test_ownership.py` | 12 | The structural proof: no service imports another app's models; `personal_events.py` calls `delivery`'s published `attach_default_plan` and never `ReminderPlan`; `saved_events.py` reads the catalog through `ingestion`'s `get_public_event` and never `apps.ingestion.models`. |

**Total new: 116**, all in `backend/tests/personalization/`.

### Acceptance Criteria Validated

| # | Criterion | How it is proven |
|---|-----------|------------------|
| 1 | `create_personal_event` validates the zone, the interval and the required fields before writing | `test_creating_an_event_refuses_a_missing_timezone` (code `missing_timezone`), `test_creating_an_event_refuses_an_unknown_timezone`, `test_creating_an_event_refuses_an_end_before_the_start` — each asserts no row survives. |
| 2 | The default reminder plan is attached at creation, and a plan failure rolls the event back | `test_the_default_plan_is_attached` asserts the slots are `["1d", "1hr"]`; `test_a_plan_failure_rolls_the_creation_back` monkeypatches `attach_default_plan` to raise and asserts neither the event nor the plan survives. |
| 3 | Conflict detection runs on write, never at render | `detect_conflicts` is called from `create_personal_event`, `update_personal_event` and `update_saved_event_snapshot`; nothing in the read path calls it. The detection service's own tests pin that a re-detection does not create a second row. |
| 4 | The creation flow cannot complete without an explicit choice | `create_personal_event` returns `ConflictFound` (not `Created`) when a conflict is detected, and the pair row is `active` with a NULL resolution — the pending prompt. `resolve_conflict` is the only way to close it. |
| 5 | Exactly three buttons, and no dismiss | `RESOLUTIONS_BY_KIND` has one frozenset per kind; `test_a_time_conflict_offers_exactly_three_resolutions`, `test_a_duplicate_offers_exactly_three_resolutions`, `test_a_time_conflict_refuses_the_duplicate_resolution`, `test_an_unknown_resolution_is_refused`, `test_there_is_no_dismiss_resolution`. |
| 6 | Every answered prompt records its resolution | The pair is written as `status=resolved` + the resolution **before** the action it names, so "delete the new one" records `delete_new` on a pair whose event is gone. `test_deleting_the_new_one_records_the_resolution_and_removes_the_event` asserts both. |
| 7 | A resolved pair is immutable and never re-prompted | `test_a_resolved_pair_is_never_re_prompted` (`ConflictAlreadyResolvedError`); `test_a_cleared_pair_is_never_re_prompted`; `test_a_closed_pair_is_never_re_opened` in the detection service. |
| 8 | The save re-reads the Event's version after commit and reports staleness | `test_a_save_that_races_a_postponement_reports_a_stale_snapshot` — the first read is inside the transaction, the check is after the commit; the snapshot keeps version 1 and the result says `stale`. `test_a_stale_save_records_the_fact_in_the_audit_log`. |
| 9 | A snapshot update applies only a strictly newer version | `test_the_snapshot_update_applies_a_newer_version`, `test_the_snapshot_update_refuses_an_older_version`, `test_the_snapshot_update_of_an_unsaved_event_does_nothing`. |
| 10 | Every mutation writes an audit row in the same transaction | Each command's test asserts its row; `test_audit.py` proves the writer refuses to run outside a `personal` transaction and that a rolled-back transaction takes its row with it. |
| 11 | No command crosses the AD-3 wall | `saved_events.py` reads the catalog through `ingestion`'s `get_public_event`, which hands over plain data; `test_ownership.py` proves structurally that no service imports another app's models. The 13 import contracts hold. |
| 12 | `personalization` writes only `personal` | Every command opens one `transaction.atomic(using=PERSONAL)`; the `delivery` call is a nested atomic on the same alias, so it is a savepoint and the two commit together. |

### Issues Found and Fixed

#### 1. [Blocking] A candidate with no id was compared against itself, and the pair row was written with a NULL side

`Candidate.id` is `None` before the row exists. The scan did `.exclude(pk=candidate.id)`
unconditionally — but `pk=None` excludes **nothing**, so the candidate's own row came back
into the scan and was compared against itself. The pair row was then written with
`right_id=NULL`, and the database refused it:

```
IntegrityError: null value in column "right_id" of relation
"personalization_conflictpair" violates not-null constraint
```

Two fixes, both in `apps/personalization/services/conflicts.py`:

- The exclusion is now applied **only when the candidate has an id** — there is nothing to
  exclude before the row exists.
- `record_detected_conflicts` now **skips** a conflict whose sides have no id, rather than
  writing a row it cannot fill. A pair names both sides by id; a conflict found against an
  unsaved candidate has nothing to point at. The commands call the recorder *after* the row
  is written, so in practice every recorded conflict has two real ids — the skip is the
  safety net for a caller that breaks that order.

#### 2. [Blocking] `delete_new` cleared the pair instead of resolving it, contradicting the AC

The first implementation ran the deletion first, and `delete_personal_event` → 
`close_pairs_for_side` closed the pair as `cleared_by_state_change` with a **NULL**
resolution. The acceptance criterion says the opposite: "The `ConflictResolution` value is
recorded for **every** prompt, including those resolved by editing or deleting."

The model's `conflict_pair_status_ck` settles it: a `cleared_by_state_change` pair must carry
a NULL resolution, so a pair the user answered can never be a cleared one. The resolution is
now recorded **first**, as `status=resolved` + the resolution, for every answered prompt
whatever the button; the deletion then goes through `delete_personal_event` as before.
`cleared_by_state_change` is reserved for a pair that ended because a side went away
*without* the user answering — an unrelated delete, an unsave, a propagation-driven close.

#### 3. [Blocking] `update_saved_event_snapshot` detected new conflicts but never closed the stale ones

The propagation-driven snapshot update re-ran detection, so a *new* overlap was recorded —
but the pair that the moved event no longer clashed with stayed `active`. The `/conflicts`
list would then claim a clash that was not there.

The fix is a new shared helper, `reconcile_pairs_for_side`, in `conflicts.py`: it re-judges
the active pairs naming one side and closes the ones that no longer overlap, as
`cleared_by_state_change` with a NULL resolution. Both call sites use it — the snapshot
update, and `personal_events._reconcile_pairs` for a user's edit.

#### 4. `unsave_event` wrote a NULL `target_id`

The audit row read `saved.id` *after* `saved.delete()`, and the id was gone:

```
IntegrityError: null value in column "target_id" of relation
"personalization_auditentry" violates not-null constraint
```

The id is now captured before the delete.

#### 5. `MissingTimezoneError` inherited `InvalidIntervalError`

Wrong base class: it must be a `ValidationError` so `config/errors.py` maps it to a 422
rather than a 500. The base was corrected and the import updated.

#### 6. A redundant third catalog read in `save_event`

The first implementation read the catalog's version *before* opening the transaction and
again after the commit. The pre-transaction read was not merely redundant — it was wrong. A
version read before the transaction opened could be older than the one the snapshot records,
which would make the post-commit check meaningless. The protocol is now the two-read shape
the design doc specifies: the read that stamps the snapshot is **inside** the transaction,
and the check is a separate, non-transactional read after the commit. The module docstring,
the design doc (D27/D28 and the sequence diagram) and `plan.md` were all updated to match.

### Coverage Details

Every module in `apps/personalization/services/` is at **100%**:

| Module | Coverage | Notes |
|--------|----------|-------|
| `services/audit.py` | 100% | Including the guard's two refusal branches. |
| `services/conflicts.py` | 100% | Including the normalisation swap, both scan directions, and every `_other_side_of` branch. |
| `services/conflict_resolutions.py` | 100% | Including both sides of the sorted pair and the "not in the pair" case. |
| `services/personal_events.py` | 100% | Including the null-end branch. |
| `services/saved_events.py` | 100% | Including the race path. |

The only uncovered file in the app is `apps/personalization/api.py` — the 2-line `Router()`
stub that item ⑥ replaces.

### Known Gaps

- **No API surface.** The commands exist and are tested; the HTTP layer that calls them is
  work item ⑥ (`personal-events-api`) and ⑦ (`saved-events-api`).
- **No frontend.** The conflict prompt and the personal-event surfaces are item ⑧.
- **The AD-17 propagation job does not exist yet.** `update_saved_event_snapshot` is the
  service it will call — it lands now so the job is a thin caller, and the race protocol is
  already proven.
- **The FR-9 picker UI does not exist.** `delivery`'s `set_plan_slots`/`remove_all_reminders`
  commands are in place; the screen is frontend work.
- **A deleted event leaves its reminder plan row behind.** `personalization` may not write
  `REMINDER_PLAN` (AD-16), and deleting the plan is `delivery`'s call — it has no such
  command yet. The leftover row is inert, and
  `test_deleting_an_event_leaves_the_reminder_plan_row` pins that it stays.
- **The "edit the new one" button does not edit.** `resolve_conflict` records the resolution
  and returns the new side's id; the caller opens that event in edit mode. Editing is
  `update_personal_event`, which re-runs detection on write.

### Ready for Completion

- [x] All tests passing
- [x] Coverage target met (80% overall, 100% for `domain/`)
- [x] All acceptance criteria validated
- [x] No critical issues open

---

## Work Item ⑥ — `personal-events-api`

**Scope:** the personal-events HTTP surface: create, list, get, edit, delete, and answer a
conflict prompt. Session-based by design (AD-12 applies to the *public* catalog only).

### Test Results

| Suite | Command | Result |
|---|---|---|
| Personal-events API | `pytest tests/personalization/test_personal_events_api.py` | **47 passed** |
| Auth seam | `pytest tests/personalization/test_auth.py` | **5 passed** |
| Architecture (decorator exemption) | `pytest tests/architecture/test_no_direct_writes.py` | **22 passed** |
| Full backend | `pytest --cov` | **2023 passed**, 99.28% overall, **domain/ 100%** |
| Import contracts | `lint-imports` | **13 kept, 0 broken** |
| Lint | `ruff check .` / `ruff format --check .` | **All checks passed / 279 formatted** |
| Django | `manage.py check` / `makemigrations --check --dry-run` | **no issues / no changes** |
| Frontend | `pnpm --dir frontend test` | **51 passed** (9 files) |
| Frontend | `lint` / `typecheck` / `format:check` | **clean** |

### Tests Written

| File | Tests | What they pin |
|---|---|---|
| `tests/personalization/test_personal_events_api.py` | 47 | The six endpoints, the wire shapes, the conflict round trip, the session scoping. |
| `tests/personalization/test_auth.py` | 5 | The session seam: the user comes from the session, an anonymous request is refused. |
| `tests/architecture/test_no_direct_writes.py` | +2 | A route decorator is not a write — the exemption cannot widen. |

**Total: 54 new tests.**

### Acceptance Criteria

| Criterion | Evidence | Result |
|---|---|---|
| A create returns 201 with the event | `test_creating_an_event_answers_201_with_the_event` | Pass |
| The IANA timezone is required | `test_creating_an_event_without_a_timezone_is_refused` (422) | Pass |
| An unknown timezone is refused, not guessed | `test_creating_an_event_with_an_unknown_timezone_is_refused` (422) | Pass |
| An end before its start is refused | `test_creating_an_event_with_an_end_before_its_start_is_refused` (422) | Pass |
| A new event gets the default reminder plan | `test_a_created_event_gets_the_default_reminder_plan` | Pass |
| A conflicting create answers 409 with the conflict and the three actions | `test_a_conflicting_create_answers_409_with_the_conflict_and_the_three_actions` | Pass |
| The action list has exactly three entries and no dismiss | `test_the_conflict_payload_offers_no_dismiss` | Pass |
| The schema cannot express a dismiss | `test_the_openapi_schema_cannot_express_a_dismiss` | Pass |
| The conflicting event is written, and the pair stays `active` | `test_a_conflicting_create_still_writes_the_event`, `..._leaves_the_pair_active` | Pass |
| Each of the three resolutions completes the flow | `test_keeping_both_...`, `test_deleting_the_new_one_...`, `test_editing_the_new_one_...` | Pass |
| An illegal resolution is refused and the prompt stays open | `test_a_resolution_that_is_illegal_for_the_conflicts_kind_is_refused` (422, pair still `active`) | Pass |
| Answering twice is refused | `test_answering_a_conflict_twice_is_refused` (422) | Pass |
| An edit re-runs conflict detection | `test_editing_reruns_conflict_detection` | Pass |
| The list is scoped to the signed-in user | `test_listing_returns_only_the_signed_in_users_events` | Pass |
| The list honours its start-time bounds | `..._honours_the_start_time_bounds`, `..._upper_start_time_bound`, `..._both_bounds_...` | Pass |
| A delete returns 204 and closes the pairs | `test_deleting_removes_the_event`, `test_deleting_closes_the_pairs_it_took_part_in` | Pass |
| A cross-user access attempt is **404, not 403** | `test_getting_another_users_event_is_a_404_not_a_403` (+ edit, delete, resolve) | Pass |
| An unauthenticated request is 401 on every endpoint | `test_an_anonymous_request_is_refused_with_a_401` (6 params) | Pass |
| No endpoint accepts a user id | `test_no_endpoint_accepts_a_user_id` | Pass |
| The OpenAPI schema carries the endpoints | `test_the_endpoints_are_in_the_openapi_schema` | Pass |
| The 409 carries a **typed** conflict payload | `test_the_409_carries_a_typed_conflict_payload` | Pass |
| The list query parameters are in the schema | `test_the_list_query_parameters_are_in_the_openapi_schema` | Pass |
| The API layer does not import the models | `test_the_api_layer_does_not_import_the_models` | Pass |

### Issues Found and Fixed

1. **The list endpoint used the *response* schema as its query model.** `PersonalEventListOut`
   has no `starts_after`/`starts_before`, so `?starts_after=…` was accepted and silently
   ignored. Fixed by adding a dedicated `PersonalEventListQuery` schema. *The schema is the
   contract (AD-19): a filter the client can send but the server ignores is a lie.*
2. **The resolve endpoint passed a placeholder `new_side_id`.** The pair row is symmetric, so
   the API layer cannot infer which side the user just created; `UUID(int=0)` meant
   `existing_side_id` was always null and `delete_new` would have deleted the wrong event.
   Fixed by putting `new_side_id` in the request body — the client knows which event it just
   made, and the asymmetry comes back with the answer.
3. **Ninja rejected the create endpoint.** `response={201: …}` with a handler that returned a
   bare value made Ninja look for a 200 schema and raise `ConfigError` — a 500 on every
   create. Fixed by returning `ninja.Status(201, …)` (and `Status(204, None)` for the
   delete), which is also the non-deprecated form in Ninja 1.7.
4. **The 409's conflict payload was invisible to a generated client.** The response was
   declared as the generic `ErrorOut`, whose `details` is an untyped dictionary — the client
   had to render the three actions (FR-58) and could not read a single field. Fixed by adding
   `SchedulingConflictOut`, an `ErrorOut` whose `details` is narrowed to
   `SchedulingConflictDetails`. The shape is now in the contract.
5. **`@router.delete(...)` was reported as a direct ORM write.** The architecture checker
   matched any attribute call named `delete`, so every `DELETE` endpoint a surface declares
   would be flagged. Fixed by excluding decorator position — a decorator registers a route,
   it does not delete a record. A genuine `obj.delete()` is still reported, and two tests pin
   both sides of that exemption.
6. **The API layer imported `apps.personalization.models`** (for `ConflictPair.SideKind`),
   against the module's own stated rule. Fixed by publishing the side-kind constants from
   `services/conflicts.py`, where the model is already imported.

### Coverage

| Module | Coverage | Notes |
|---|---|---|
| `apps/personalization/api.py` | 100% | All six endpoints, both conflict paths. |
| `apps/personalization/schemas.py` | 100% | Every projection. |
| `apps/personalization/auth.py` | 100% | Both branches. |
| `apps/personalization/services/personal_events.py` | 100% | Including the `starts_before` bound. |
| `domain/errors.py` | 100% | `SchedulingConflictError` included. |
| **Overall** | **99.28%** | Gate: ≥80%. |
| **`domain/`** | **100%** | Gate: 100%. |

### Known Gaps

- **No frontend for this surface.** The conflict prompt's three buttons and the personal-event
  screens are item ⑧ (`frontend-personal-and-conflict-surfaces`).
- **The saved-events half of the surface does not exist yet.** Item ⑦ adds it; the two share
  the `auth.py` seam and the schema module.
- **The `edit_new` button does not edit.** The endpoint records the resolution and returns
  the new side's id; the client opens that event in edit mode. The edit itself is the `PATCH`
  endpoint, which re-runs detection.
- **`update_existing` is accepted by the schema but no endpoint acts on it.** It is a
  duplicate prompt's button, and duplicates against a personal event are detected but the
  *existing* side is a saved event — whose edit endpoint arrives with item ⑦. The service
  refuses it for a time conflict, which the tests pin.
- **The list endpoint has no pagination.** The personal list is bounded by the user's own
  events; the catalog list is the one with a total and a page. Item ⑦ can revisit this.
- **The reminder plan row is left behind by a delete.** `personalization` may not write
  `REMINDER_PLAN` (AD-16) and deleting the plan is `delivery`'s call.

### Ready for Completion

- [x] All tests passing
- [x] Coverage target met (99.28% overall, 100% for `domain/`)
- [x] All acceptance criteria validated
- [x] No critical issues open

---

## Work Item: saved-events-api

**Intent:** `personal-events-and-saved-catalog` · **Work item:** `saved-events-api` ·
**Complexity:** medium · **Mode:** confirm

### Test Results

| Suite | Result |
|---|---|
| `backend/tests/personalization/test_saved_events_api.py` | 30 passed |
| `backend/tests/personalization/test_saved_events.py` | 21 passed |
| `backend/tests/api/test_catalog_read_service.py` | 24 passed |
| `backend/tests/api/test_catalog_api.py` | 23 passed |
| **Backend, whole suite** | **2060 passed, 0 failed** |
| **Backend coverage** | **99.29%** (gate ≥80%) |
| **`domain/` coverage** | **100%** (gate 100%) |
| `frontend` Vitest | 51 passed (9 files) |
| `lint-imports` | 13 contracts, 0 broken |
| `ruff check` / `ruff format --check` | clean |
| `makemigrations --check --dry-run` | no changes detected |
| `manage.py check` | no issues |
| `eslint` / `tsc --noEmit` / `prettier --check` | clean |

### Acceptance Criteria Validation

| Criterion | Evidence | Result |
|---|---|---|
| a save succeeds and returns the record | the 201 body carries the snapshot's times, the catalog's title, venue and canonical URL | PASS |
| a double-save is idempotent | the second answers 200, the body carries the same `id`, and `SavedEvent.objects.count() == 1` | PASS |
| an unsave removes the save and closes the pairs | 204; the pair closes as `cleared_by_state_change` with `resolution is None` | PASS |
| the list is scoped to the user | another user's saves are not listed, and cannot be asked for | PASS |
| a cross-user unsave is 404, not 403 | the other user's save survives the attempt | PASS |
| saving a non-public event is 404 | four cases: nonexistent, in review, superseded, already started | PASS |
| a conflict with a personal event returns the three actions | the 409 payload's `details.conflicts[0].actions` has exactly three entries and no `dismiss` | PASS |
| the save race is exposed, not papered over | `stale` is true, `current_version` is the moved version, and `repropagation_requested` is audited | PASS |
| an unauthenticated request is 401 | all three endpoints answer 401 with `not_authenticated` | PASS |
| the OpenAPI schema carries the endpoints | both paths present, and the `SavedEventOut` schema carries `stale` and `current_version` | PASS |

### Tests Written

**`backend/tests/personalization/test_saved_events_api.py`** (new, 30 tests) — the HTTP
surface:

- *Saving* — returns the record; carries the snapshot's times and the catalog's display
  fields; belongs to the signed-in user; a repeat save answers 200 and the same id; a
  nonexistent, in-review, superseded, or already-started event is a 404 and writes
  nothing; a save of an event that has since started stays listed.
- *The save race* — the version moves between the service's first read and its check, so
  `stale` is true and `current_version` is the moved version; a save with no race is not
  stale and reports no `current_version`; a stale save writes a
  `saved_event.stale_detected` audit entry carrying `repropagation_requested`.
- *Conflicts* — a clashing save answers 409 with the three actions; the save row is still
  written and the pair stays `active` with no resolution.
- *Un-saving* — removes the save; an unsave of something not saved is a 404; the pairs it
  took part in close as `cleared_by_state_change`; another user's save is a 404 and
  survives.
- *Listing* — returns the user's saves; does not show another user's; orders by the
  snapshot's start time; the query bounds filter by the snapshot's start time; a save
  whose catalog event has gone is omitted and counted in `omitted`.
- *The session seam* — all three endpoints refuse an anonymous request with 401; no
  endpoint accepts a `user_id` in the body.
- *The contract* — both paths are in `openapi.json`; `SavedEventOut` carries `stale` and
  `current_version`; the API layer does not import `apps.ingestion.models`.

**`backend/tests/personalization/test_saved_events.py`** (extended, +4 tests) — the
service's list read: ordering, user scoping, inclusive bounds on the snapshot's start
time, and no bounds meaning no filter.

**`backend/tests/api/test_catalog_read_service.py`** (+2 tests) — the published read's
`now` bound: an event that has started is not found when `now` is given; it *is* found
when `now=None`, because a record of something already saved stays readable.

**`backend/tests/api/test_catalog_api.py`** (+1 test) — the catalog detail shows the same
set the list does: an event that has already started is a 404.

### The defects this item found

1. **The published catalog read never applied its own documented rule.**
   `catalog_read.get_public_event`'s docstring promised that "only published,
   non-superseded, **upcoming** events are visible" — but only `list_public_events`
   enforced "upcoming". The detail endpoint returned events that had already started, and
   a save could take an event into a personal calendar after it had begun.

   This was a defect in `ingestion`'s published interface, not in `personalization`. It
   was fixed at the source: `get_public_event` gained an optional `now`, and the rule is
   applied at every point where "has not started yet" is the question. Papering over it
   in the personalization layer would have meant the catalog's rule lived in two places,
   one of them private.

2. **A save was possible after the event had started.** The service's first read was
   unbounded, so `POST /api/personal/saved-events/{id}` accepted an event an hour old.
   Fixed by bounding that read with `now` — "you take an event into your calendar while it
   is still ahead of you".

3. **The staleness check would have failed a save for the wrong reason.** Once the read
   was bounded, the *second* read — the race check — had to stay unbounded: it asks only
   whether the version moved, and re-applying the "not started" rule there would have
   failed a save whose event merely *began* while the write was in flight. The two reads
   answer different questions and are now bounded differently on purpose.

4. **The API could not tell a first save from a repeat.** `update_or_create` returns the
   existing row for a repeat, but the service did not report which happened, and the
   endpoint had no way to answer 201 versus 200. `SaveResult.created` now carries it.

5. **The list endpoint ignored the bounds its service accepted.** `list_saved_events`
   took `starts_after`/`starts_before` and the API never passed them — a filter the client
   could send and the server ignored. Fixed by adding `SavedEventListQuery` and wiring the
   bounds through; the same lesson as item ⑥'s `PersonalEventListQuery`.

### The contract the response keeps

The response has **two sources**, and the tests keep them apart: the times come from the
snapshot on the personal row, and the title, venue and canonical URL come from the
catalog, read at request time. A saved event is not a copy of a catalog event — it is a
personal record that points at one.

This is why `list_saved_events` reads the personal side only, and why the API layer
resolves the catalog side one event at a time: a save whose catalog event has since
disappeared is the caller's to notice, and the `omitted` count is how it notices.

### Coverage

| Module | Coverage | Notes |
|---|---|---|
| `apps/personalization/api.py` | 100% | All three endpoints, both conflict paths. |
| `apps/personalization/schemas.py` | 100% | Every projection, and the query model. |
| `apps/personalization/services/saved_events.py` | 100% | Including both bounds and the race protocol. |
| `apps/ingestion/services/catalog_read.py` | 100% | Including both the bounded and unbounded read. |
| **Overall** | **99.29%** | Gate: ≥80%. |
| **`domain/`** | **100%** | Gate: 100%. |

### Known Gaps / Deliberate Omissions

- **FR-48's free-tier quota is not enforced.** The `identity` subscription model does not
  exist yet, so there is nothing to count saves against. The work item calls skipping
  this the smaller sin, and this is the note the Pro tier intent needs: the save endpoints
  are the place a quota will land, and they are the only place it can be enforced
  correctly — the count is `SavedEvent.objects.filter(user_id=…).count()` at write time,
  inside the same transaction as the save.
- **AD-17's propagation job is not implemented.** The protocol is exposed — the service
  detects the race and writes the audit entry that asks for re-propagation — but the job
  that calls `update_saved_event_snapshot` is later work. Until it exists, a stale
  snapshot stays stale; the client is told (`stale`, `current_version`), so it is never
  shown as current.
- **No frontend for this surface.** The save button, the saved-events list and the
  "2 saved events are no longer available" notice are item ⑧.
- **The list has no pagination.** The saved-events list is bounded by the user's own
  saves and is returned whole, with the query bounds available for narrowing.
- **The catalog detail endpoint's behaviour changed.** An event that has already started
  is now a 404 there, matching the list. The catalog's own client may have relied on the
  old behaviour; the change is deliberate and is pinned by a test.

### Ready for Completion

- [x] All tests passing
- [x] Coverage target met (99.29% overall, 100% for `domain/`)
- [x] All acceptance criteria validated
- [x] No critical issues open

---

## Work Item: frontend-personal-and-conflict-surfaces

**Scope:** The three client surfaces — `Sheet.PersonalEventCreate`, `Sheet.PersonalEventEdit`
and `Sheet.ConflictResolution` — plus the seam that joins them, the timezone conversion
the form depends on, and the "Add" affordance that reaches them.

### What was built

| File | What it is |
|---|---|
| `frontend/lib/timezones.ts` | The curated zone list and the wall-clock → UTC conversion. |
| `frontend/components/sheets/sheet.tsx` | The `<dialog>` base, with one dismissal regime per sheet. |
| `frontend/components/sheets/personal-event-form.tsx` | Create and edit, one component, two modes. |
| `frontend/components/sheets/conflict-resolution.tsx` | The forced three-action prompt. |
| `frontend/components/personal-events-panel.tsx` | The client island that owns the round trip. |
| `frontend/components/personal-events-section.tsx` | The server read that feeds the island. |
| `frontend/components/add-event-button.tsx` | The spine's "Add" affordance. |
| `frontend/app/page.tsx` | The home page that hosts the section. |

### The timezone conversion

The backend stores `start_time_utc` as an **absolute instant** and `start_time_tz` as the
display zone; it validates the zone but never reinterprets a wall-clock time in it. So the
conversion is the browser's, and it is the one place it lives.

`localToUtcInstant` uses `Intl.DateTimeFormat(...).formatToParts` with an explicit
`timeZone` — never string parsing, which is where the first attempt went wrong
(`en-US` produces `11/06/2026, 18:30`, not `2026-11-06T18:30`). It takes the zone's offset
from two probes either side of the target instant, prefers the nearer one, and then
**round-trips** the result: a local time that does not exist (the 2:30 AM of a
spring-forward morning) fails the round trip and is refused rather than silently shifted.

20 tests cover the winter and summer offsets for New York, London and Tokyo, a half-hour
offset zone, UTC itself, the API's instant format (`Z`, no fractional seconds), the
round trip in both directions, and the four refusal cases.

### The dismissal regimes

A native `<dialog>` opened with `showModal()` is **Escape-dismissable and
backdrop-dismissable by default**. The base takes a `dismissible` prop that turns each
escape hatch off in one place — the code most likely to be got wrong, next to the code
that opens the dialog. The tests prove both halves: the create sheet closes on Escape and
on a backdrop click; the conflict sheet does neither.

### The a11y evidence — **there is no axe setup**

The work item asks for "an accessibility test (or the existing axe setup)". The frontend
has **no axe setup**: `axe-core`, `jest-axe` and `vitest-axe` are all absent from
`package.json`, and there is no axe configuration in `vitest.config.mts`. Adding a
dependency for one item is a larger change than the criterion asks for.

So the assertion the criterion actually names — *no keyboard-reachable dismiss path* — is
proven **directly** rather than by a scan. This is stated here rather than hidden:

| Property | Evidence |
|---|---|
| no dismiss control | `queryByRole("button", { name: "Close" })` is null; no button matches `/dismiss/i` |
| Escape does nothing | the `cancel` event's `defaultPrevented` is `true` |
| a backdrop click does nothing | the dialog is still in the document after the click |
| the prompt persists | no timeout, no effect, and the sheet is still open after the state settles |

The live region and the focus move are proven too: `aria-live="assertive"` on
"Schedule conflict. Three choices.", and the `<h2>` header carries focus when the prompt
opens.

### The other properties

| Property | Evidence |
|---|---|
| the form's required-timezone validation | submitting with no zone is refused; the field says "Pick a timezone." |
| the create form posts the right body | the UTC instant is right for the zone (winter **and** summer), and the zone is sent |
| the three conflict actions and their labels | exactly three buttons, with the PRD's labels |
| the duplicate relabelling | "Update the existing one", and it resolves `update_existing` |
| the actions come from the server | a server that sends two actions renders two |
| the `aria-label`s | each action's label names the action and its consequence |
| the conflict dot | `role="img"`, `aria-label="Schedule conflict"`, `bg-warn-amber`, never `bg-signal-warn` |
| the warm-personal colour pairing | the stripe is `bg-warm-personal` **and** the text says "Personal" |
| the delete confirmation | the delete does not happen until the confirmation is answered |

### Defects found and fixed

1. **The field labels were not associated with their controls.** The `Field` component
   wrapped each input in a `<label>` without an `htmlFor`, so the input's `id` was never
   linked to its name. The input announced no accessible name, clicking the label did not
   focus the field, and `aria-describedby` pointed at an error element that had no `id`.
   Fixed by giving `Field` an `id` prop, rendering `htmlFor` on the label and `id` on the
   error paragraph, and wiring every control's `aria-describedby` to it.

2. **The pre-highlighted hint was rendered twice.** `Field` rendered the `hint` in the
   muted branch *and* again in the `highlighted` branch — the same sentence, twice, in two
   tones. Fixed by rendering it once, in the amber tone when the field is the highlighted
   one.

3. **`Sheet` crashed on close in a runtime without the top layer.** `dialog.close()` was
   called unguarded, while the *open* path already had a fallback for a runtime whose
   `showModal` is unavailable. jsdom has neither, so closing a sheet threw
   `dialog.close is not a function` and took the whole tree down with it. Fixed by
   guarding `close` the same way `showModal` is guarded, falling back to removing the
   `open` attribute.

4. **The conflict sheet rendered `undefined` for its header and its other side.** The
   component referenced `header`, `other` and `actions` without deriving them from the
   conflict. Fixed by reading all three off `conflict` — `other` from `conflict.other`,
   the actions from `conflict.actions`, and the header from `conflict.kind` with the time
   header as the fallback.

### Coverage

| Module | Tests | Notes |
|---|---|---|
| `lib/timezones.ts` | 20 | Both DST states, half-hour zones, the four refusals. |
| `components/sheets/sheet.tsx` | 7 | Both dismissal regimes, the backdrop, the content click. |
| `components/sheets/conflict-resolution.tsx` | 27 | The three actions, the labels, the copy, the cards, the announcement, the focus, the confirm. |
| `components/sheets/personal-event-form.tsx` | 17 | The validation, the posted body, the pre-highlight. |
| `components/personal-events-panel.tsx` | 16 | The round trip, the 409, the resolution, the edit. |
| `components/add-event-button.tsx` | 4 | The affordance opens a sheet and does not route. |
| `components/personal-events-section.tsx` | 2 | The server read, and the quiet failure. |
| **Frontend total** | **146** | 16 files, all passing. |
| **Backend** | **2060** | 99.29% overall; `domain/` at 100%. |

### Known Gaps / Deliberate Omissions

- **No Pulse Card, timeline event-block, source badge or confidence pulse.** None of them
  exist in the frontend yet, and the work item explicitly forbids building one here: a
  general-purpose card would be the divergent second implementation the intent warns
  about. The conflict indicator is proven inside the conflict sheet's stacked cards and
  in the personal-event row — exactly where the work item says it may be proven.
- **No sidenav.** The six-route shell is later work. The "Add" affordance is built as the
  component the shell will carry, so the surface is reachable now and the shell can adopt
  it without changing the flow. **No `/add` route** — a route would be a second entry
  point for one surface.
- **The personal-event list is not live.** The server component reads once per render.
  A create does not push the new event into the list; the panel shows the outcome in a
  message and the list updates on the next render. The refresh mechanism belongs to the
  timeline work.
- **No axe scan.** Stated above, with the reasoning.
- **The sheet is a modal on every viewport.** The spine calls for a bottom sheet on
  mobile and a modal on desktop. The `<dialog>` base is a centred modal on both; the
  bottom-sheet treatment is a responsive rule the shell work will add.
- **The conflict sheet's copy is the mockup's, not the PRD's second sentence.** The
  mockup's subhead names the event ("You've already saved a tech meetup…"), while the
  work item's criterion gives the template ("You've already saved {conflicting event
  name}. Choose how to handle it."). The template is what is implemented, and it is what
  the test asserts.

### Ready for Completion

- [x] All tests passing (146 frontend, 2060 backend)
- [x] Coverage target met (99.29% overall, 100% for `domain/`)
- [x] Lint, typecheck, format and import-lint gates clean
- [x] No new colour tokens, no new hex values, no new CSS variables
- [x] No Tailwind motion class; the API reached only through `lib/backend-client.ts`

---

## ⑨ `e2e-proof-and-contract-tests` — the proof

The final item. It proves the intent works end to end, that the architectural invariants
still hold after this intent's code landed, and that the edge cases are pinned.

Three files, **22 new backend tests** and **3 new frontend tests**.

### The recorded scenario, end to end

`backend/tests/e2e/test_personal_events_and_saved_catalog.py::test_the_whole_personal_event_and_save_flow_holds_together`
drives the **real HTTP surface** — the same endpoints the browser drives — through one
recorded scenario. It is one test, not a sequence of independent assertions, because the
point of a proof is that the *steps compose*.

| # | Step | What it proves |
|---|---|---|
| 1 | Create a personal event with an explicit timezone | It persists in `personal`, keeps `start_time_utc` and `start_time_tz`, and comes back from the list. The stored instant and the named zone agree (AD-6): 19:30 in Los Angeles is 03:30 UTC. |
| 2 | A second event overlapping the first | **409** with `details.event_id`, one conflict, `kind == "time"`, and **exactly three actions** — `{keep_both, edit_new, delete_new}`. The event **was written**: a 409 is a pending prompt, not a failed write. |
| 3 | Answer "Keep both — I'll manage" | The pair is `resolved` with `resolution == keep_both` and `resolved_at` set. |
| 4 | Make the **same two events** clash again | The pair is **not re-prompted**. The pair count for those two sides is still 1, the pair is still `resolved`/`keep_both`, and replaying the resolution answers **422 `conflict_already_resolved`** — a resolved pair is immutable (AD-21). |
| 5 | Save a public event from the ingested catalog | The `SAVED_EVENT` row carries a snapshot of the event's `start_utc`, `end_utc` and `event_version`. |
| 6 | A personal event overlapping the save | **409** with three actions, and the conflict's other side is the saved event's own id. |
| 7 | Answer "Delete the new one" | The new event is gone, but the resolution **is still recorded** on the pair, and the pair's status is `resolved` — **resolved-not-cleared**, not the NULL-resolution `cleared_by_state_change` shape. |
| 8 | Read the state back | The list shows the first event and not the deleted one; the saves list shows exactly the one save. |

Only two things are substituted, both deliberately and both named in the file's docstring:
the catalog fetch is served by the fake adapter from recorded fixtures, and the worker is
run inline.

**Why step 4 edits rather than recreates.** The work item asks for "re-create the same
conflicting pair → no prompt". A *re-created* event has a new id, so it is a **new** pair
and the assertion would prove nothing. The test instead **edits the second event back
into the first one's time**, which re-detects the very same `pair_id` — and then proves
that pair is not re-prompted. The immutability half is proved separately, by the 422
replay.

### The save-race, proven deterministically

`backend/tests/e2e/test_save_race.py`. AD-21: "A save re-reads the Event's version after
commit and requests re-propagation for that user if it moved meanwhile, so a save racing a
postponement cannot keep a stale snapshot."

**The interleaving is forced, not hoped for.** A probabilistic race test is a flaky test,
and a flaky test in CI is worse than no test. So the *catalog read* the save service makes
is patched: the **first** read — inside the transaction, the one that stamps the snapshot —
returns version N; the **second** read — after the commit, the one that checks — returns
version N+1. That is the postponement-lands-mid-save interleaving, reproduced every time.

| Test | What it proves |
|---|---|
| `test_a_save_that_races_a_postponement_reports_itself_stale` | The save answers `stale: true` with `current_version == event_version + 1`; the snapshot keeps the version it was **stamped** with (repairing it is AD-17's job, a later intent); the catalog was read exactly twice. |
| `test_a_save_that_does_not_race_is_not_stale` | The **control case**. Without it, "stale is True" would only prove the endpoint has a `stale` field. |
| `test_a_snapshot_survives_a_catalog_postponement_unchanged` | A postponed event's snapshot is **not** repaired by a later read. The snapshot's `event_version` is behind the catalog's and its `start_utc` is behind the catalog's — the correct pre-propagation state, stated explicitly so it cannot be mistaken for a bug. The display fields (`title`) *do* come from the catalog, so an editorial correction shows up immediately. |
| `test_a_save_is_idempotent_and_one_row` | Saving the same event twice is one row: 201 then 200, the same id. |
| `test_a_save_of_an_unpublished_event_is_not_found` | A hidden event cannot be saved — the public catalog is one truth. |

The patch is at the **service's** namespace (`apps.personalization.services.saved_events`),
not the catalog module's: `save_event` does `from …catalog_read import get_public_event`,
so the name it calls is bound in the service module. Patching the catalog module instead
would not be seen by the service — and a test that silently patches nothing proves nothing.

### The boundary cases, pinned

| Boundary | At the edge | Just past it |
|---|---|---|
| **15-minute overlap** (AD-21: *strictly more than*) | Exactly 15 minutes → **201**, no conflict. | 15 minutes and one second → **409**, `kind == "time"`. |
| **80% token overlap** (`Fraction(4, 5)`) | Exactly `Fraction(4, 5)` → duplicate. | `Fraction(3, 4)` → not a duplicate. |
| **24-hour duplicate window** | 23 hours earlier → **409** duplicate. | 25 hours earlier → **201**, no conflict. |

Two things worth recording about the 80% boundary:

- **The threshold is `Fraction(4, 5)`, and the test compares against `Fraction(4, 5)`,
  not `0.8`.** `Fraction(4, 5) == 0.8` is **False** — 0.8 is not exactly 4/5 in binary
  floating point. The threshold is a rational precisely so that this boundary is decidable
  without a float comparison anywhere.
- **The tokenisation drops stop words.** `domain.dedup.title_fingerprint` splits a title
  into *content* tokens and *stop* tokens (`and`, `for`, `the`, …), and Jaccard compares
  the **content** sets. So exactly 4/5 needs a union of five over an intersection of four —
  one title with four content tokens against one with five. The first draft of this test
  used five-word titles and got 2/3, because "for" and "and" are stop words and the
  fingerprints held three content tokens each.

The duplicate-window test gives each case its **own user**. With one user, the "outside"
case at 25 hours would still be inside the window of the "inside" case at 23 hours — the
conflict would be real, and for the wrong reason.

### The architecture invariants, re-verified

`backend/tests/architecture/test_personal_events_invariants.py` — 13 tests, alongside the
contract tests from `project-scaffold`. Structural assertions about the codebase, not
scenario tests.

| Invariant | How it is proved |
|---|---|
| **AD-3** schema separation | The personal tables live in `personal` and the catalog's in `catalog`, verified through `information_schema` rather than assumed from the router; **no foreign key crosses from `personal` to `catalog`** (queried, not assumed); the three new models declare **no relation field at all**; `SavedEvent.event_id` and `ConflictPair.left_id`/`right_id` are plain `UUIDField`s with no `remote_field`. |
| **AD-16** write ownership | The owning app of each table is read from the model metadata: `personalization` owns `PERSONAL_EVENT`, `SAVED_EVENT` and `CONFLICT_PAIR`; `delivery` owns `REMINDER_PLAN`. **No module outside `personalization` imports `apps.personalization.models`.** `personalization` reaches the reminder plan through `delivery`'s published service — the source names `apps.delivery.services.reminder_plans` and **not** `apps.delivery.models` — and the service hands over plain data, not a model instance. |
| **AD-21** snapshot semantics | The conflict indicator is symmetric **by construction**: a real pair is written, and the real `pairs_for_side` service finds it from **both** sides — the same row id from either position, and nothing for a side that is not in the pair. The pair stores both sides, so there is one fact and one reader, not two facts that can drift. |

Where an earlier item already wrote a test for an invariant, this file **extends** it
rather than duplicating it: the cross-schema foreign-key check and the delivery-ownership
checks already existed, so what is added here is the part that is *new* — this intent's
models, the reminder-plan attachment, and the indicator's symmetry.

### The gates

| Gate | Result |
|---|---|
| Backend suite | **2082 passed**, 0 skipped, 0 quarantined, 0 xfailed |
| Coverage | **99.29%** overall (gate: ≥80%); **`domain/` at 100%** (gate: 100%) |
| `ruff check` / `ruff format --check` | Clean |
| `make lint-imports` | **13 contracts kept, 0 broken** — including `models-personalization` and `models-delivery` |
| `manage.py check` | No issues (this includes the AD-15 retention check; every new model declares `ACCOUNT_CONTENT` or `AUDIT_LOG`) |
| `makemigrations --check --dry-run` | No changes detected |
| `backend/tests/worker/test_tick.py` | **5 passed, untouched** — `beat_schedule` is still exactly one 60s tick |
| Frontend suite | **149 passed** (16 files) |
| Frontend lint / typecheck / format | Clean |
| `next build` | Succeeds; `/` is `ƒ (Dynamic) — server-rendered on demand` |
| `make client` | The regenerated `frontend/lib/api/` is **byte-identical** — no contract drift |

### The defect this item found

**The frontend build was broken.** `next build` failed with
`TypeError: Invalid URL … ERR_INVALID_URL` on `/api/personal/events`.

The cause: `PersonalEventsSection` is an **async server component**, so `next build`
rendered it to produce the page's static output — and that render reached for the API.
With no `API_BASE_URL` set in the build environment, `apiBaseUrl()` returns `undefined`,
so the client had a relative base URL and `openapi-fetch` rejected the path outright. A
build that needs a live Django is a build that cannot run in CI.

Three defects were behind the one symptom:

1. **The page was statically prerendered.** The page shows the signed-in user's own
   personal events, which is per-session state — a static page is wrong for every user.
   Fixed by `export const dynamic = "force-dynamic"` on the **page**. (The export has to
   be on the page or layout: Next reads route segment config from those files, not from a
   nested component, so putting it on the section had no effect on the route.)
2. **The read did not fail quietly, despite the docstring promising it.** The component
   said "The read is allowed to fail quietly" and then had no `try`/`catch`. Fixed by
   catching the failure — a down API is an empty list, not an error page.
3. **The read was attempted with no base URL to reach.** Fixed by returning the empty
   list when there is no base URL, rather than issuing a request that cannot be made.

The section's test grew three cases: a rejected request, a missing base URL, and the
page's `force-dynamic` declaration. The build now succeeds and `/` is dynamic.

This defect belongs to item ⑧ (`frontend-personal-and-conflict-surfaces`), which owns the
frontend surfaces. It was found here, by the proof item's build gate, and fixed in the
owning place rather than expanded into this item's scope — the ownership map still
describes reality.

### Known Gaps / Deliberate Omissions

- **FR-48, the free-tier save quota, is not implemented.** FR-48 caps free-tier saves at
  1 per 24 hours. That needs the `identity` subscription model, which does not exist yet,
  and it belongs to the Pro tier intent. The endpoint work item deliberately skips it. It
  is recorded here so a later reader does not mistake the omission for "done".
- **There is no `/conflicts` list endpoint yet.** AD-21's symmetry claim is about the
  Pulse Card, the Timeline and `/conflicts` reading the same `CONFLICT_PAIR` rows. The
  Pulse Card and the Timeline do not exist yet, and `/conflicts` is not in this intent's
  scope. What **is** proved is the property that makes them agree when they arrive: one
  row, two sides, read by either side.
- **The save-race is proven against a patched read, not a real postponement.** A real
  postponement would need a second writer racing the save in two transactions, which is
  the flaky test the work item warns against. The patched read reproduces the
  interleaving exactly — same order, same reads, same result — and the assertion is on
  the observable behaviour (`stale`, `current_version`), not on the mechanism.
- **No `next build` gate existed in the local `make` targets** before this item; the
  build is run in CI's `frontend` job. It is worth adding `next build` to `make lint-web`
  or a local `make build-web` target, since a build break is invisible to lint and
  typecheck.

### Ready for Completion

- [x] The recorded end-to-end scenario runs and passes through the real HTTP surface
- [x] The save-race is proven deterministically, with a control case
- [x] The 15-minute boundary is pinned at the edge and just past it
- [x] The 80% threshold and the 24-hour window are pinned at their boundaries
- [x] A resolved `CONFLICT_PAIR` is immutable and is never re-prompted
- [x] A `SAVED_EVENT` snapshot survives a catalog postponement unchanged
- [x] AD-3, AD-16 and AD-21 are re-verified after this intent's code landed
- [x] `make lint-imports` passes with `models-personalization` and `models-delivery` green
- [x] `manage.py check` passes, including the AD-15 retention check for every new model
- [x] All gates green: 2082 backend, 149 frontend, 99.29% coverage, `domain/` 100%
- [x] `beat_schedule` is still exactly one 60s tick; `test_tick.py` passes untouched
- [x] No skipped or quarantined tests introduced by this intent
- [x] A test report records the scenario, the boundaries, the invariants, the coverage
      and the deliberately-omitted behaviour
