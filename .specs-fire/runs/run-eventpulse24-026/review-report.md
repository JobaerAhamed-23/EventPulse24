# Code Review Report

**Run**: run-eventpulse24-026
**Intent**: trust-loop
**Work item**: review-queue-model
**Reviewed**: 2026-11-10T14:40:00Z
**Files Reviewed**: 13

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 2 | 0 | 0 |
| Security | 0 | 1 | 0 |
| Architecture | 0 | 0 | 0 |
| Testing | 0 | 1 | 0 |
| **Total** | **2** | **2** | **0** |

**Tests Status**: Passing (306 targeted). The full suite's 16 failures existed before this item and are unrelated (see `test-report.md`).

---

## Files Reviewed

- `backend/apps/ingestion/models.py` (modified)
- `backend/apps/ingestion/migrations/0008_reviewitem.py` (created)
- `backend/apps/ingestion/services/review_queue.py` (created)
- `backend/shared/constants.py` (modified)
- `backend/config/management/commands/seed_local_stack.py` (modified)
- `backend/tests/ingestion/factories.py` (modified)
- `backend/tests/ingestion/test_review_item_model.py` (created)
- `backend/tests/ingestion/test_review_queue.py` (created)
- `backend/tests/ingestion/test_review_queue_concurrency.py` (created)
- `backend/tests/e2e/test_end_to_end.py` (modified)
- `backend/tests/ingestion/test_models.py` (modified)
- `backend/tests/wall/test_schema_placement.py` (modified)
- `backend/tests/architecture/test_write_ownership.py` (modified)

---

## Auto-Fixed Issues

### 1. [Code Quality] Import order in the generated migration

- **File**: `backend/apps/ingestion/migrations/0008_reviewitem.py:3`
- **Description**: ruff I001. Django's generator put `shared.ids` among the third-party imports. Fixed by `ruff check --fix`.

### 2. [Code Quality] Line too long, plus formatting

- **File**: `backend/apps/ingestion/services/review_queue.py:79`
- **Description**: E501 (103 > 100) on the `RuntimeError` line with its `pragma`. The call was wrapped, and `ruff format` was applied to three new files. No semantic change; tests re-run green.

---

## Applied Suggestions

### 1. [Security] Enforce D4 instead of trusting the caller

- **File**: `backend/apps/ingestion/services/review_queue.py` (`raise_review_item`)
- **Description**: The command refuses `reason=user_reported` from any non-system actor, with a `ValueError`. That's a programming error, so it isn't mapped to HTTP.
- **Rationale**: The audit row lives in `catalog`, and the editorial group holds `view_ingestionauditentry`. A future caller passing `Actor.user(reporter)` would silently show editors who reported what. The design relied on the caller remembering this, and a guard is cheaper than that trust.
- **Risk Level**: Low. There are no callers yet. Non-report reasons are unaffected, and a test covers an editor raising `in_review`.
- **Approved**: 2026-11-10 ("go")
- **Tests**: `test_a_report_raised_as_the_reporter_is_refused_and_writes_nothing` and `test_an_editor_may_raise_a_non_report_item`. Probe: with the guard disabled, the first fails.

### 2. [Testing] Pin `REPORT_FIELDS` to `ReportCategory`

- **File**: `backend/tests/ingestion/test_review_item_model.py`
- **Description**: Asserts that every category has exactly one `reports_*` column and vice versa.
- **Rationale**: A fifth category added without a column would otherwise surface as a `KeyError` inside a live bump.
- **Risk Level**: None (test only).
- **Approved**: 2026-11-10 ("go")

---

## Skipped Suggestions

No suggestions were skipped.

**Considered and not raised:**
- `Event` gaining a 14th `PROTECT` foreign key could block a future retention sweep. There is no catalog sweep yet, and the other 13 foreign keys raise the same question, so it is not specific to this item.
- `withdrawn`'s system label is checked as non-empty, not against `SYSTEM_LABEL`'s regex. `Actor` enforces the regex in Python, and every writer goes through a command.

---

## Project Tooling Used

- **ruff** (lint and format): `backend/pyproject.toml`
- **import-linter** (19 contracts kept): `backend/pyproject.toml`
- **Django system checks** (E001–E005) and `makemigrations --check`

---

## Standards Referenced

- `.specs-fire/standards/constitution.md`
- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`
