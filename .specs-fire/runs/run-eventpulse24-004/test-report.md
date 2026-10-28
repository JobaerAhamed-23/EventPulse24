---
run: run-eventpulse24-004
work_item: shared-foundations
intent: project-scaffold
generated: 2026-10-27
status: passed
---

# Test Report: Shared Foundations

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| New: unit and config (errors, ids, constants, retention, logging, logging config, checks, `User`) | 73 | 0 | 0 | n/a |
| New: API (error mapping, trace id through Django `Client`) | 29 | 0 | 0 | n/a |
| Existing suite (unchanged) | 72 | 0 | 0 | n/a |
| **Total (pytest)** | **174** (was 72) | 0 | 0 | n/a |
| Mutation checks (deliberate breakage caught) | 18/18 | 0 | 0 | n/a |

Coverage measurement arrives with `ci-pipeline`.

## Acceptance Criteria Validation

- ✅ **`DomainError` base with a stable `code`, plus `NotFoundError`, `ValidationError`, `PermissionDeniedError`, `ConflictError`.** `domain/errors.py`; `tests/domain/test_errors.py` (16). The domain-is-Django-free guard covers the new module.
- ✅ **One Ninja exception handler maps `DomainError` → HTTP status + `{code, message, details?}`; no per-endpoint mapping.** `config/errors.py::install_error_handlers`, installed once in `config/api.py`. `tests/api/test_errors.py` (20) pins the exact bodies, including framework errors and the single `details.errors` shape.
- ✅ **`shared/ids.py` generates UUIDv7, and a base model mixin uses it as the primary key.** `shared/ids.py`, `shared/models.py::UUIDv7Model`; `identity.User` uses it. Tested: layout, top-bit-clear seed, 10k strictly increasing, counter overflow, clock going backwards, `uuid` column in `personal`.
- ✅ **Structured JSON logger with an allowlist; any other field redacted; email- and token-shaped values redacted even inside allowed fields.** `adapters/logging/`; `tests/adapters/test_logging.py` (24), including no-false-positive cases and the "free text never reaches the sink" cases from the plan reviews.
- ✅ **Trace/request id attached to every log line from the API edge.** `TraceIdMiddleware` (first in `MIDDLEWARE`) plus a formatter fallback for Django's post-middleware `django.request` line. `tests/api/test_trace_id.py` (9).
- ✅ **`shared/retention.py` registry; a system check errors on any model without a category.** `eventpulse.E003` / `E004` on every concrete model (fail-closed, broader than the criterion).
- ✅ **`shared/constants.py`: gates 0.5 / 0.7, tz gate 0.7, default plan `1d + 1hr`, conflict overlap 15 min.** Plus `SEND_KEY_SEPARATOR`; stdlib-only (fresh-interpreter test).
- ✅ **Tests: error handler shape; UUIDv7 ordering; logger redacts an email and a token; `manage.py check` fails for an undeclared test model and passes once declared.** The last one runs on isolated models (`test_model_without_retention_reported_as_e003_until_declared`). A plain `call_command("check")` passes on the project and **fails** when routing is broken, which proves plain `check` now runs the project checks (see Issues).

## Tests Written

| File | Tests | Covers |
|---|---|---|
| `tests/domain/test_errors.py` | 16 | Codes, calm defaults (no `!`), custom message/details, subclassing |
| `tests/shared/test_ids.py` | 7 | RFC layout, timestamp, seed headroom, ordering, overflow, clock backwards, fork with the lock held (S1) |
| `tests/shared/test_constants.py` | 5 | Spine values, slots, separator, no Django on import |
| `tests/shared/test_retention.py` | 5 | 9 PRD categories, full coverage, `User`/sessions → `ACCOUNT_IDENTITY`, framework map |
| `tests/adapters/test_logging.py` | 25 | Shape, allowlist, email/token patterns, false positives, args never interpolated, exceptions without messages, non-JSON values, nesting |
| `tests/api/test_errors.py` | 20 | Every mapping + exact body; one `errors` shape for 3 sources; `django.security` warning; 500 vs `DEBUG` re-raise; project API wired |
| `tests/api/test_trace_id.py` | 9 | Minted/echoed id; same id on every line incl. `django.request` 404; inbound validation (≤36); context reset |
| `tests/config/test_logging_config.py` | 5 | No Django handlers, no admin mail, one JSON root handler, SQL at WARNING, middleware first |
| `tests/config/test_checks.py` | +7 | E003 until declared, E004, through tables, framework map, wrapper, plain `check` passes and runs E001 |
| `tests/identity/test_user.py` | 3 | UUIDv7 before save, `uuid` column in `personal`, persisted |

## Mutation Checks (each reverted after)

| Deliberate break | Result |
|---|---|
| Formatter keeps non-allowlisted fields | 1 failed |
| Email pattern removed | 4 failed |
| Project logger interpolates args | 1 failed |
| `str(exc)` added to exception output | 1 failed |
| Prefix patterns lose `\b` / minimum length | 4 failed |
| E003 disabled | 1 failed |
| E004 disabled | 1 failed |
| UUIDv7 counter not monotonic | 3 failed |
| 500 handler leaks exception text | 1 failed |
| `TraceIdMiddleware` removed | 8 failed |
| Django's default handlers left on `django` | 2 failed |
| Routing check tagged `database` again | 1 failed |
| No `django.security` warning | 1 failed |
| Pydantic `input` echoed in `details` | 1 failed |
| Sessions mapped to `ACCOUNT_CONTENT` | 1 failed |
| Middleware doesn't put the id on the request | 1 failed |
| UUIDv7 fork hook removed (review S1) | 1 failed (child killed by its 5 s alarm) |
| `Bearer` pattern without minimum length (review S2) | 1 failed |

## Runtime Verification

- **Dev DB:** `make reset-db FORCE=1` → `db-check` ready → `make migrate` (38 migrations) → 172 passed → `check` clean → `makemigrations --check` no changes. This is the path the Mac takes.
- **Real server** (`runserver`, then curl):
  - `X-Request-ID` echoed
  - every line is JSON
  - `?email=a@b.com` in the access line logged as `[email]`
  - `request` and `server_time` extras logged as `[redacted]`
  - Django's 404 line now carries the trace id (it was `null` before the fix below)

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| **E001/E002 never ran on a plain `manage.py check`** (from run 003). They were registered with the `database` tag, which Django skips unless `--database` is passed; they only ran inside `migrate`. | High | Fixed: re-tagged `models` (they don't touch the DB); E003/E004 use the same tag; regression test `test_plain_manage_py_check_runs_the_routing_check` |
| Django logs 4xx/5xx on `django.request` **after** the middleware chain returns, so those lines had `trace_id: null` | Medium | Fixed: the middleware also sets `request.trace_id`, and the formatter falls back to `record.request.trace_id`; regression test |
| `logger.exception` in the 500 handler relied on an implicit `sys.exc_info()` (Ruff `LOG004`, newly enabled) | Low | Fixed: `logger.error(..., exc_info=exc)` |
| `LogRecord` attribute set built with `dict \| set` (TypeError at logging setup) | Low | Fixed during execution |
| `make makemigrations` output failed isort (`I001`) when a migration imports a project module (`shared.ids`) | Low | Fixed: the target also runs `ruff check --select I --fix` |

`shellcheck` isn't on this shell's PATH. No shell scripts changed in this run.

## Ready for Completion

- [x] All tests passing
- [x] Coverage target met (n/a until ci-pipeline)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-004*
