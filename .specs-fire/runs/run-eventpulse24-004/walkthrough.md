---
run: run-eventpulse24-004
work_item: shared-foundations
intent: project-scaffold
generated: 2026-10-27
mode: confirm
---

# Implementation Walkthrough: Shared Foundations

## Summary

This run adds the cross-cutting pieces that every feature builds on:
- one error model with a single HTTP mapping
- UUIDv7 ids, now the primary key of `User`
- a JSON logger that redacts by allowlist and by pattern
- a trace id on every request
- a fail-closed retention registry with system checks
- the shared constants module

The suite grew from 72 to 174 tests, and 18 deliberate breakages were all caught. The plan went through 3 revisions (15 review points). While building, I found and fixed a bug from run 003: the AD-3 checks never ran on a plain `manage.py check`.

## Structure Overview

- **Errors:** `domain` defines *what* went wrong (error types with a stable code and a calm message), `shared` defines the *wire shape*, and `config` alone decides the *HTTP status*.
- **Logging:** call sites keep using the standard `logging` module. Everything else is inside `adapters/logging`: one formatter decides what reaches the sink, and the middleware binds a trace id that the formatter adds to every line.
- **Retention:** a class attribute on every model, a framework map for models we don't own, and two system checks.
- **Ids and constants:** stdlib-only modules, so `domain` can be allowed to import them.

## Architecture

### Pattern Used

Single mapping points. Errors map to HTTP in one module, and logs are redacted in one formatter. That way the rules don't depend on every call site remembering them (AD-13, the spine's Errors convention).

### Layer Structure

```text
domain/errors.py  (types, codes, calm messages; no HTTP, no Django)
      │ raised by services
config/errors.py  (status by MRO, {code,message,details?}) ◄── installed once on config/api.py
shared/errors.py  (ErrorOut / ErrorItem: the OpenAPI wire shape)

call site: logger.info("Constant", extra={...})
      └► root handler ─► adapters/logging/formatter.JsonFormatter
                           ├─ redaction: ALLOWED_FIELDS + scrub patterns
                           └─ context: trace_id ◄── config/middleware.TraceIdMiddleware (X-Request-ID)

model.retention_category / FRAMEWORK_RETENTION ─► retention_registry() ─► E003/E004 (manage.py check)
                                                                       └► sweep / deletion / export (later)
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/domain/errors.py` | `DomainError` + 4 generic errors |
| `backend/shared/errors.py` | `ErrorOut`, `ErrorItem` |
| `backend/shared/ids.py`, `shared/models.py` | `uuid7()`, `UUIDv7Model` |
| `backend/shared/retention.py` | Categories, PRD list, framework map, registry |
| `backend/shared/constants.py` | Gates, reminder slots/plan, conflict overlap, send-key separator |
| `backend/config/errors.py` | The exception → HTTP mapping |
| `backend/config/middleware.py` | `TraceIdMiddleware` |
| `backend/adapters/logging/{context,redaction,formatter}.py` | Trace context, redaction, JSON formatter |
| `backend/tests/…` (10 files) | 102 new tests |

### Modified

| File | Changes |
|------|---------|
| `backend/config/{api,settings,checks}.py` | Handlers installed; middleware first; `LOGGING`; E003/E004; checks re-tagged `models` |
| `backend/apps/identity/models.py`, `migrations/0001_initial.py` | UUIDv7 PK, retention, `AbstractUser.Meta`; regenerated |
| `backend/tests/wall/*/models.py`, `tests/config/test_checks.py` | Retention declared; +7 tests |
| `backend/pyproject.toml`, `Makefile` | Ruff `G`/`LOG`; `makemigrations` sorts imports |
| `.specs-fire/standards/{coding,testing}-standards.md` | Errors, logging, retention, ids, send keys, audit-log design; log assertions |
| `work-items/{architecture-contracts,ports-fakes-and-worker}.md` | Hand-offs |

## Domain Model

### Entities

| Entity | Properties | Business Rules |
|--------|------------|----------------|
| `identity.User` | `AbstractUser` + UUIDv7 `id` | Retention `ACCOUNT_IDENTITY`; lives in `personal` |

### Value Objects

| Value Object | Properties | Constraints |
|--------------|------------|-------------|
| `RetentionCategory` | 9 PRD categories + `NOT_USER_DATA` | The exemption is never shown to users (`PRD_CATEGORIES` excludes it) |
| `ReminderSlot` | `5d`, `2d`, `1d`, `1hr` | Default plan `1d + 1hr` (AD-16) |

## Key Implementation Details

### 1. One error shape, everywhere

- Domain errors, Ninja request validation, `HttpError`, `Http404`, Django's `PermissionDenied`, `SuspiciousOperation` and `ValidationError`, and crashes all return `{code, message, details?}`.
- Validation errors from all three sources become `details.errors = [{loc, msg}]`. Pydantic's `input` is dropped, so submitted values aren't echoed back.
- An `HttpError`'s own text is never shown.
- With `DEBUG` off, a crash is a calm 500, logged with its type and stack. With `DEBUG` on, it re-raises, so you get Django's debug page.

### 2. What reaches a log sink

- Only allowlisted `extra` fields survive. They are scrubbed for email- and token-shaped values; any other field becomes `[redacted]`.
- **Project loggers never interpolate args.** `logger.info("Saved %s", title)` logs `"Saved %s"` with `args: [redacted]`.
- **Exception messages are never logged**, only the type chain and stack frames.
- **Token patterns are anchored**, so `network_check`, `work_item`, "bearer of good news", UUIDs, trace ids and `:`-separated send keys are not mangled.
- Django's own handlers are removed. `mail_admins` would have emailed unredacted tracebacks.

### 3. Trace id

The middleware runs first:
- A valid inbound `X-Request-ID` (8–36 characters of `[A-Za-z0-9-]`) is accepted; otherwise a 32-hex id is minted.
- The id is bound to the context, set on `request.trace_id`, and echoed in the response header.
- The request attribute exists because Django logs 4xx/5xx on `django.request` *after* the middleware chain returns. Before the fix, those lines had no trace id.

### 4. UUIDv7

- RFC 9562 method 1: a 48-bit millisecond timestamp, a 12-bit counter seeded with its top bit clear, and 62 random bits.
- Ids are strictly increasing within a process, including on counter overflow and when the clock goes backwards.
- The lock is recreated after `fork`, so a Gunicorn or Celery child can't inherit a locked lock.
- The id is minted in Python, so commands have it before `save()`.

### 5. Retention, fail-closed

- Every concrete model must declare a category; `NOT_USER_DATA` is the explicit exemption.
- `E003` reports a missing category, and `E004` a value that isn't a category.
- Sessions are `ACCOUNT_IDENTITY`: a credential that dies on logout, expiry or account deletion.
- Admin `LogEntry` is `AUDIT_LOG`.

## Security Considerations

| Concern | Approach |
|---------|----------|
| PII in logs (AD-13) | Allowlist, anchored patterns, no arg interpolation for project loggers, no exception messages, no Django mail/console handlers, SQL logging capped at WARNING |
| Log injection | Inbound trace id must be `[A-Za-z0-9-]{8,36}` |
| Error leakage | No exception text, `HttpError` text or pydantic `input` in responses |
| Existence leaks | Coding standard: `NotFoundError`, not `PermissionDeniedError`, for personal resources the caller doesn't own |
| Security signal | `SuspiciousOperation` logged on `django.security.<Class>` at WARNING |
| Retention | Every table declares its category, so the sweep, deletion and export can't miss one |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Error location | Types in `domain`, status in `config`, wire shape in `shared` | Domain stays HTTP-free; `apps` mustn't import `config` |
| Framework errors | Same shape; Django `ValidationError` → 422 | One error type for the generated client; user input isn't a server fault |
| Validation details | `[{loc, msg}]` for all sources | One parser in the frontend |
| UUIDv7 | Own implementation, minted in Python, fork-safe | Python 3.13 has no `uuid7`; the id is needed before `save()` |
| Log message templates | Still pattern-scrubbed (one review point deliberately not followed) | Nothing enforces a literal message: `G` misses `logger.info(user.email)` |
| Retention scope | All models, explicit exemption | Fail-closed, like E001 |
| Send keys | `:` separator | UUIDs stay 36-character runs and survive scrubbing |
| Check tags | `models`, not `database` | Django skips `database` checks on a plain `check` |
| Audit log | Deferred, design recorded | Not in the acceptance criteria; no command exists yet (OQ-8) |

## Deviations from Plan

- **E001/E002 re-tagged** from `database` to `models`, with a regression test. This wasn't planned; it fixes a run 003 bug found while adding E003/E004.
- **`request.trace_id` fallback** in the middleware and formatter. Found by running the real server.
- **`User.Meta(AbstractUser.Meta)`**: the regenerated migration had lost the verbose names (code review auto-fix).
- **`make makemigrations` also sorts imports**: the generated migration failed `I001`.
- **The 500 handler uses `logger.error(..., exc_info=exc)`**, not `logger.exception` (newly enabled Ruff `LOG004`).
- **Review S1/S2 applied**: fork-safe lock, and a minimum length for `Bearer` credentials.

## Dependencies Added

None.

## How to Verify

1. **Reset and migrate** (the user's primary key type changed)
   ```bash
   make reset-db && make migrate
   ```
   Expected: 38 migrations applied

2. **Tests, lint, checks**
   ```bash
   make test-backend && make lint-backend && make manage ARGS="check"
   ```
   Expected: `174 passed`, `All checks passed!`, `System check identified no issues`

3. **See the logs and the trace id**
   ```bash
   make api
   curl -si -H "X-Request-ID: 3f2c9a1e-7b8d-4f6a-9c0e-5b2d7a1f4c8e" "http://127.0.0.1:8000/api/openapi.json?email=a@b.com" | grep -i x-request-id
   curl -s http://127.0.0.1:8000/api/nope
   ```
   Expected: the header is echoed; the server prints JSON lines; the access line shows `?email=[email]`; the 404 line on `django.request` carries the trace id. If port 8000 is busy (`make doctor` warns), change `API_PORT` in `.env`.

4. **The retention check bites**
   Remove `retention_category` from `apps/identity/models.py`, then run `make manage ARGS="check"`.
   Expected: `eventpulse.E003`. Restore the line afterwards.

## Test Coverage

- Tests added: 102 (72 → 174), plus 18/18 mutation checks
- Coverage: not measured yet (added by `ci-pipeline`)
- Status: passing

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated (coding and testing standards, hand-offs)
- [x] Developer notes captured

## Developer Notes

- **On the Mac, after pulling:** `make reset-db && make migrate && make test-backend`. The `User` id is now a UUID, so the old volume can't be migrated in place (there's no real data).
- **Logging how-to:** `logger.info("Constant message", extra={"event_id": ..., "count": ...})`. To log a new field, add it to `ALLOWED_FIELDS` in a reviewed change: ids, counts and slugs only.
- **Asserting on logs in tests:** `caplog` records are pre-redaction. To check what reaches the sink, attach a handler with `JsonFormatter` (see `tests/api/test_trace_id.py`).
- **Retention counts:** PRD §10.2 lists **9** categories; the spine's AD-15 says "seven". The code follows the PRD. The spine wording should be corrected by the architect.
- **ASGI:** `TraceIdMiddleware` is sync-only. Check that the context propagates under ASGI when the deployment picks a server.
- **`ErrorOut` in OpenAPI** appears once an endpoint declares it (`health-round-trip`).
- **Port 8000 on this machine** is held by another project's PyCharm `runserver`. That's unrelated to this repo.
- **For `architecture-contracts`** (in its work item): allow `domain` → `shared.constants` / `shared.ids`; a PK rule (`UUIDv7Model`); `os.environ` ban exempting `manage.py`; alias-less `atomic()` lint.
- **For `ports-fakes-and-worker`** (in its work item): pass the trace id into Celery tasks and bind it around execution; set `worker_hijack_root_logger = False`.
- **FIRE tooling:** run.md frontmatter was synced by hand at each checkpoint and phase change.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-004*
