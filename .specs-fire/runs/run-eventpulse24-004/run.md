---
id: run-eventpulse24-004
scope: single
work_items:
  - id: shared-foundations
    intent: project-scaffold
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-27T11:33:35.928Z
completed: 2026-10-27T12:51:07.174Z
---

# Run: run-eventpulse24-004

## Scope
single (1 work item)

## Work Items
1. **shared-foundations** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/domain/errors.py`: DomainError + NotFoundError, ValidationError, PermissionDeniedError, ConflictError; calm defaults
- `backend/shared/errors.py`: ErrorOut / ErrorItem wire schemas
- `backend/shared/ids.py`: RFC 9562 uuid7(): per-process monotonic, top-bit-clear counter seed, fork-safe lock
- `backend/shared/models.py`: UUIDv7Model abstract base
- `backend/shared/retention.py`: RetentionCategory (9 PRD + NOT_USER_DATA), PRD_CATEGORIES, FRAMEWORK_RETENTION, retention_registry()
- `backend/shared/constants.py`: Confidence gates, ReminderSlot, DEFAULT_REMINDER_PLAN, CONFLICT_MIN_OVERLAP, SEND_KEY_SEPARATOR (stdlib only)
- `backend/config/errors.py`: install_error_handlers: the single exception -> HTTP mapping, one errors shape
- `backend/config/middleware.py`: TraceIdMiddleware: X-Request-ID, context binding, request.trace_id
- `backend/adapters/logging/{context,redaction,formatter}.py`: Trace context, allowlist + scrub patterns, JsonFormatter
- `backend/tests/{domain/test_errors,shared/*,adapters/test_logging,api/test_errors,api/error_api,api/test_trace_id,api/trace_urls,config/test_logging_config,identity/test_user}.py`: 102 new tests

## Files Modified
- `backend/config/api.py`: install_error_handlers(api)
- `backend/config/settings.py`: TraceIdMiddleware first; LOGGING with Django handlers removed; DEFAULT_AUTO_FIELD comment
- `backend/config/checks.py`: E003/E004 retention checks; all project checks re-tagged models (were database: skipped by plain check)
- `backend/apps/identity/models.py, migrations/0001_initial.py`: User(UUIDv7Model, AbstractUser) with AbstractUser.Meta; 0001 regenerated
- `backend/tests/wall/{catalog_probe,personal_probe}/models.py`: retention_category declared
- `backend/tests/config/test_checks.py`: +7 retention and plain-check tests
- `backend/pyproject.toml`: Ruff G and LOG rules
- `Makefile`: makemigrations sorts imports before formatting
- `.specs-fire/standards/coding-standards.md`: Errors, no-existence-leak rule, logging rules, retention, UUIDv7Model, send keys, audit-log design (OQ-8)
- `.specs-fire/standards/testing-standards.md`: Log assertions via JsonFormatter
- `.specs-fire/intents/project-scaffold/work-items/{architecture-contracts,ports-fakes-and-worker}.md`: Hand-offs

## Decisions
- **Error location and mapping**: Types in domain/errors.py (no HTTP); status by MRO in config/errors.py; ErrorOut in shared (Domain stays HTTP-free; apps must not import config)
- **Framework errors**: Same {code,message,details?} shape; Django PermissionDenied 403, SuspiciousOperation 400 + django.security warning, Django ValidationError 422; DEBUG re-raises (One error type for the generated client; keep security signal and debug page)
- **Validation details**: details.errors = [{loc, msg}] for pydantic, Django keyed and unkeyed (One parser on the frontend; pydantic input not echoed)
- **UUIDv7**: Own RFC 9562 implementation, minted in Python, fork-safe (Python 3.13 lacks uuid7; commands need the id before save)
- **Log redaction**: Allowlisted extras; project loggers never interpolate args; exception messages never logged; template still scrubbed (Patterns can't recognise free text; G lint misses positional args and bare variables)
- **Django log handlers**: Removed (django, django.server handlers []); SQL logging at WARNING (mail_admins/console would bypass redaction)
- **Trace id**: X-Request-ID, inbound accepted only if [A-Za-z0-9-]{8,36}; also on request for post-middleware django.request lines (No log injection; 404/500 lines keep the id)
- **Retention scope**: Every concrete model declares (fail-closed), NOT_USER_DATA explicit; 9 PRD categories (A model can't slip past by omission; PRD has 9 bullets (spine says 7))
- **Sessions retention**: ACCOUNT_IDENTITY (Credential: dies on expiry/logout, immediately on deletion)
- **Send-key separator**: : (SEND_KEY_SEPARATOR) (Keeps UUIDs as 36-char runs so keys survive log scrubbing)
- **Check tags**: E001-E004 tagged models, not database (Django skips database-tagged checks on plain manage.py check)
- **Audit log**: Deferred to the first named command; design recorded (per-app tables, actor by id) (Not in this item's criteria; OQ-8)


## Summary

- Work items completed: 1
- Files created: 10
- Files modified: 11
- Tests added: 102
- Coverage: 0%
- Completed: 2026-10-27T12:51:07.174Z
