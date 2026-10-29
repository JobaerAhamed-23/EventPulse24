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
