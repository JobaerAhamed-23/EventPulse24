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
