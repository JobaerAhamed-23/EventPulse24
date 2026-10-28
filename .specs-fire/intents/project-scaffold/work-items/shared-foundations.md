---
id: shared-foundations
title: Shared Foundations
intent: project-scaffold
complexity: medium
mode: confirm
status: completed
depends_on:
  - backend-skeleton
created: 2026-10-27
run_id: run-eventpulse24-004
completed_at: 2026-10-27T12:51:07.174Z
---

# Work Item: Shared Foundations

## Description

Build the cross-cutting pieces every later feature depends on: error model and its single HTTP mapping, ids, PII-safe logging, the retention registry and its system check, and the shared constants module.

## Acceptance Criteria

- [ ] `shared/errors.py` (or `domain/errors.py`): `DomainError` base with a stable `code`; a few generic subclasses (`NotFoundError`, `ValidationError`, `PermissionDeniedError`, `ConflictError`)
- [ ] One Ninja exception handler maps `DomainError` → HTTP status + `{code, message, details?}`; no per-endpoint mapping
- [ ] `shared/ids.py` generates UUIDv7 and a base model mixin uses it as the primary key
- [ ] `adapters/logging/` provides a structured JSON logger with an **allowlist** of loggable fields; any other field is redacted; email-shaped and token-shaped values are redacted even inside allowed fields
- [ ] Trace/request id is attached to every log line from the API edge
- [ ] `shared/retention.py` registry: models declare a retention category class attribute; a Django system check errors on any model holding user-derived data without one
- [ ] `shared/constants.py`: extraction confidence gates (0.5 / 0.7), tz-inference gate (0.7), default reminder plan `1d + 1hr`, conflict overlap 15 min
- [ ] Tests: error handler shape; UUIDv7 ordering; logger redacts an email and a token; `manage.py check` fails for an undeclared test model and passes once declared

## Technical Notes

- AD-13 (redact at the logger, not call sites), AD-15 (retention is a table property), AD-16 (default plan is one constant).
- Error `message` follows the UX voice: calm, no urgency, no emoji.

## Dependencies

- backend-skeleton
