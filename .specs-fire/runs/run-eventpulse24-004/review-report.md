# Code Review Report

**Run**: run-eventpulse24-004
**Intent**: project-scaffold
**Reviewed**: 2026-10-27
**Files Reviewed**: 31

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 2 | 1 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 0 | 0 |
| Testing | 0 | 0 | 0 |
| Correctness | 0 | 1 | 0 |
| **Total** | **2** | **2** | **0** |

Two suggestions (S1, S2) were approved by the user ("a") and applied. The plan went through 3 revisions (15 review points) before execution. Issues found while testing (including the E001/E002 tag bug from run 003) are in test-report.md.

**Tests Status**: Passing (174/174 after S1/S2; ruff clean incl. new `G`/`LOG`; `check` clean; `makemigrations --check` clean)

---

## Files Reviewed

- `backend/domain/errors.py`, `backend/shared/{errors,ids,models,retention,constants}.py` (created)
- `backend/config/{errors,middleware}.py` (created); `api.py`, `settings.py`, `checks.py` (modified)
- `backend/adapters/logging/{context,redaction,formatter}.py` (created)
- `backend/apps/identity/models.py`, `migrations/0001_initial.py` (regenerated)
- `backend/tests/**` (10 new files, 1 modified, 2 probe models), `backend/pyproject.toml`, `Makefile`
- `.specs-fire/standards/{coding,testing}-standards.md`; work items `architecture-contracts.md`, `ports-fakes-and-worker.md`

---

## Auto-Fixed Issues

### 1. [Code Quality] `User` lost `AbstractUser`'s `Meta` (verbose names)

- **File**: `backend/apps/identity/models.py`
- **Description**: With two abstract bases, Django inherits `Meta` from the **first** one only (`UUIDv7Model`). The regenerated `0001` dropped `verbose_name="user"` / `verbose_name_plural="users"`, which are translatable in `AbstractUser.Meta`.
- **Fix**: `class Meta(AbstractUser.Meta): pass`, with a comment; `0001` regenerated. It changes options only, not the schema (`migrate --check` clean on the existing DB).

### 2. [Code Quality] `make makemigrations` produced unsorted imports

- **File**: `Makefile`
- **Description**: A migration that imports a project module (`shared.ids`) failed Ruff `I001`; the target only ran `ruff format`.
- **Fix**: the target also runs `ruff check --select I --fix --quiet .`.

---

## Pending Suggestions

None.

---

## Applied Suggestions

### S1. [Correctness] UUIDv7 lock reset after fork

- **File**: `backend/shared/ids.py`
- **Problem**: a fork while another thread held the module lock would leave the child's copy locked, so the child's first `uuid7()` would deadlock (Gunicorn and Celery prefork both fork).
- **Change**: `os.register_at_fork(after_in_child=_reset_lock_after_fork)` creates a fresh lock in the child. `_last_ms` is kept, so ordering continues.
- **Test**: `test_uuid7_child_forked_while_lock_held_can_still_mint` forks with the lock held. The child has a 5 s `alarm`, so a regression fails instead of hanging. Mutation (hook removed): caught.
- **Approved by**: user ("a")

### S2. [Code Quality] `Bearer` pattern needs a credential-length body

- **File**: `backend/adapters/logging/redaction.py`
- **Change**: `\bbearer\s+[A-Za-z0-9._~+/=-]{8,}`.
- **Test**: "the bearer of good news" survives; the token test uses a realistic credential. Mutation (back to `+`): caught.
- **Approved by**: user ("a")

---

## Skipped Suggestions

None.

---

## Notes (no action in this run)

- **ASGI and the trace context:** `TraceIdMiddleware` is sync-only. Under ASGI, Django runs it through `asgiref`, which copies context into the worker thread. That isn't verified yet, because the project runs WSGI. It should be checked when deployment chooses a server.
- **`ErrorOut` isn't in the OpenAPI document yet:** no endpoint declares it. `health-round-trip` adds the first endpoint, and the generated client should then include `ErrorOut` and `ErrorItem`.

---

## Project Tooling Used

- **ruff 0.17.3** (`backend/pyproject.toml`; adds `G`, `LOG`)
- **pytest 9.1.1 + pytest-django 4.14.0**; Django system checks `eventpulse.E001`–`E004`
- `shellcheck` is not on this shell's PATH; no shell scripts changed

---

## Standards Referenced

- `.specs-fire/standards/constitution.md`, `coding-standards.md`, `testing-standards.md`, `tech-stack.md`, `system-architecture.md`
- `ARCHITECTURE-SPINE.md` AD-2, AD-5, AD-7, AD-8, AD-13, AD-15, AD-16, AD-21, OQ-8; Consistency Conventions (Ids, Errors, Error shape, Confidence)
- PRD §10.2 (retention), §11.6 (i18n)
