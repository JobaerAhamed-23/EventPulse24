# Code Review Report

**Run**: run-eventpulse24-003
**Intent**: project-scaffold
**Reviewed**: 2026-10-27
**Files Reviewed**: 38

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 0 | 1 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 0 | 1 |
| Testing | 0 | 0 | 0 |
| **Total** | **0** | **1** | **1** |

One suggestion (S1) was approved by the user and applied. The design (3 revisions) and plan (3 revisions) were externally reviewed before execution; issues found while testing are in test-report.md.

**Tests Status**: Passing (72/72 after S1; ruff clean; shellcheck clean)

---

## Files Reviewed

- `docker/postgres/init/01-schemas-and-roles.sh`, `scripts/db-check.sh`, `Makefile` (modified)
- `backend/config/{databases,db_router,checks,apps,settings_test}.py` (created); `env.py`, `settings.py` (modified)
- `backend/shared/db.py` (created)
- `backend/apps/identity/{models,admin}.py`, `migrations/0001_initial.py`
- `backend/tests/conftest.py`, `tests/wall/**` (probe apps + 4 test modules), `tests/config/test_{databases,router,checks}.py` (created); `test_env.py`, `test_project.py` (modified)
- `backend/pyproject.toml`, `.env.example`, `README.md`, `docs/setup/{ubuntu,macos}.md`
- `.specs-fire/standards/{coding,testing}-standards.md`, `system-architecture.md`; work items `schema-router-spike.md`, `ci-pipeline.md`; design doc; spine OQ-8

---

## Pending Suggestions

None.

---

## Applied Suggestions

### 1. [Correctness] `build_databases` dropped connection options from the URL

- **File**: `backend/config/databases.py:35-36`
- **Description**: `dj_database_url.parse()` turns URL query parameters into `OPTIONS` (verified: `…?sslmode=require` → `{'sslmode': 'require'}`). The code replaced `OPTIONS` with only the `search_path`, silently discarding `sslmode=require`, which Neon URLs carry. Locally nothing broke (no TLS).
- **Change**: merge instead of replace: `config.setdefault("OPTIONS", {})["options"] = …`, with a comment saying why.
- **Test**: `test_build_databases_url_query_options_kept_alongside_search_path[runtime|owner]` (+2). Against the old line both fail (mutation verified).
- **Approved by**: user ("apply it")

---

## Skipped Suggestions

### 1. [Architecture] Lint rule for bare `transaction.atomic()` / `.using()` without an alias

- **File**: n/a (project-wide)
- **Description**: `default` means personal, so an alias-less `transaction.atomic()` silently targets personal.
- **Rationale**: Enforcement belongs with the other static rules.
- **Risk Level**: Low
- **Reason Skipped**: Out of scope; handed to `architecture-contracts` (design "Findings to hand on"); convention documented in coding-standards.

---

## Project Tooling Used

- **ruff 0.17.3** (`backend/pyproject.toml`; tests now also ignore `S608`, migrations ignore `E501`)
- **shellcheck** (`-s sh`) on `doctor.sh`, `db-check.sh`, init script
- **pytest 9.1.1 + pytest-django 4.14.0**; Django system checks (`eventpulse.E001`/`E002`)

---

## Standards Referenced

- `.specs-fire/standards/constitution.md`, `coding-standards.md`, `testing-standards.md`, `tech-stack.md`, `system-architecture.md`
- `.specs-fire/intents/project-scaffold/work-items/schema-router-spike-design.md` (revision 3)
- `ARCHITECTURE-SPINE.md` AD-2, AD-3, AD-5, AD-14, AD-16
