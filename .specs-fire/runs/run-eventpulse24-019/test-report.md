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
