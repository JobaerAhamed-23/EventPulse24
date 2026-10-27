---
id: ports-fakes-and-worker
title: Ports, Fake Adapters & Worker Skeleton
intent: project-scaffold
complexity: medium
mode: confirm
status: completed
depends_on:
  - shared-foundations
created: 2026-10-27
run_id: run-eventpulse24-006
completed_at: 2026-10-27T15:11:25.178Z
---

# Work Item: Ports, Fake Adapters & Worker Skeleton

## Description

Define the port interfaces the apps will depend on, provide fake (local) adapters selected by config so nothing needs API keys, and stand up the Celery worker + beat with the AD-7 tick seed.

## Acceptance Criteria

- [ ] `ports/` defines interfaces for `LLMPort`, `EmbeddingPort`, `EmailPort`, `BillingPort`, `CalendarPort` using Protocols / ABCs with typed inputs/outputs
- [ ] `EmailPort.send` **requires** a `stream` argument (`Stream.TRANSACTIONAL` / `Stream.BULK`); omitting it is a type error (AD-20)
- [ ] Fake adapters for each port; email fake (or SMTP adapter) delivers to Mailpit; adapter selection comes from settings (`ADAPTER_MODE=fake` default)
- [ ] Celery app configured with Redis (:6380) broker; static `beat_schedule` in code with one 60s `tick` task that does nothing but log; no `django-celery-beat`
- [ ] `make worker` and `make beat` run them locally; docs note **exactly one** beat process
- [ ] Tests: adapter selection by config; email send without stream fails type-check/raises; tick task callable
- [ ] Verified manually: beat schedules the tick, worker logs it within ~60s; a test email appears in Mailpit UI at :8025

## Technical Notes

- AD-7: the broker carries the tick and pipeline jobs only — never the reminder schedule. The tick here is a no-op seed for the later due-index sweep.
- AD-8: no module imports a provider SDK; the real LLM gateway is a later intent.

## Dependencies

- shared-foundations

## Hand-offs from earlier runs

- **Trace id into jobs** (shared-foundations, AD-13): send `current_trace_id()` with each task (Celery headers) and bind it with `adapters.logging.context.bind_trace_id` around execution (`task_prerun` / `task_postrun`, or a base task class), so worker log lines carry the request's trace id.
- **Worker logging goes through `settings.LOGGING`**: set `worker_hijack_root_logger = False`, so Celery doesn't replace the redacting JSON handler. Worker code logs under `worker.*` (a project logger: constant messages, args never interpolated). `celery.*` loggers are treated as framework loggers (interpolated, then scrubbed).
- **Where the Celery app goes** (architecture-contracts): `config/celery.py`, the standard Django layout. Its `os.environ.setdefault("DJANGO_SETTINGS_MODULE", …)` is covered by the `config/**` Ruff exemption. `config` and `worker` must not import each other (`config | worker` layer, AD-1), so reference tasks and beat entries by **dotted string** (`autodiscover_tasks`, `"worker.tasks.tick"`), never by import.
- **Worker code may not import `apps.*.api`** (`worker-not-api` contract). Call services.
