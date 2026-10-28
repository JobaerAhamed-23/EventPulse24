# Code Review Report

**Run**: run-eventpulse24-005
**Intent**: project-scaffold
**Reviewed**: 2026-10-27
**Files Reviewed**: 19

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 0 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 0 | 0 |
| Testing | 1 | 0 | 0 |
| **Total** | **1** | **0** | **0** |

No suggestions are pending. The plan went through 2 revisions (7 points + 6 minor) before execution.

**Tests Status**: Passing (346/346; ruff clean; `lint-imports` 12 kept; `check` clean)

---

## Files Reviewed

- `backend/pyproject.toml` (import-linter contracts, Ruff `TID` + banned-api + per-file ignores), `backend/uv.lock`
- `backend/config/checks.py` (E005), `backend/tests/config/test_checks.py`
- `backend/tests/architecture/{checkers,test_import_contracts,test_stdlib_only,test_database_alias,test_env_access}.py`
- `Makefile`, `README.md`, `docs/setup/{ubuntu,macos}.md`
- `.specs-fire/standards/{coding-standards,tech-stack}.md`; work items `ci-pipeline.md`, `ports-fakes-and-worker.md`

---

## Auto-Fixed Issues

### 1. [Testing] The root-package list lived in three places, and only one was checked

- **Files**: `backend/pyproject.toml` (`root_packages`), `backend/config/checks.py` (`PROJECT_PACKAGES`, E005 scope), `backend/tests/architecture/checkers.py` (`ROOT_PACKAGES`, scanner scope)
- **Description**: the coverage guard compared only `root_packages` with the directories on disk. Adding a package there but not in `PROJECT_PACKAGES` would quietly exempt its models from E005, and leaving it out of `ROOT_PACKAGES` would exempt its files from the alias scanner.
- **Fix**: `test_package_lists_agree` asserts that all three sets are equal. Mutation (`worker` dropped from `PROJECT_PACKAGES`): caught.

---

## Pending Suggestions

None.

---

## Skipped Suggestions

None.

---

## Checked and Fine

- **Every contract is pinned by an exact-set planted case, and allowed paths by controls.** Mutating each contract config or checker made a test fail (12/12).
- **The plants are isolated:** a copy under `tmp_path`, `PYTHONPATH` replaced, `--no-cache`. The real tree was confirmed unchanged after the mutation runs (no `.bak` files left, and `lint-imports` is still 12 kept).
- **`.import_linter_cache/`** ignores itself (its own `.gitignore`), so it won't be committed.
- **The scanner's scope is all our packages, including migrations;** none of the generated code trips it.
- **The domain-pure ignores** use `unmatched_ignore_imports_alerting = "none"`. Nothing imports `shared.constants` yet, and "error" would otherwise fail the clean tree.

---

## Project Tooling Used

- **import-linter 2.15** (grimp 3.18): `make lint-imports`, in `make lint-backend`
- **ruff 0.17.3** (adds `TID`)
- **pytest 9.1.1 + pytest-django 4.14.0**; system checks `eventpulse.E001`–`E005`

---

## Standards Referenced

- `.specs-fire/standards/constitution.md`, `coding-standards.md`, `testing-standards.md`, `tech-stack.md`, `system-architecture.md`
- `ARCHITECTURE-SPINE.md` AD-1, AD-2, AD-3, AD-5, AD-8, OQ-8
