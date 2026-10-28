---
run: run-eventpulse24-006
work_item: ports-fakes-and-worker
intent: project-scaffold
generated: 2026-10-27
mode: confirm
---

# Implementation Walkthrough: Ports, Fake Adapters & Worker Skeleton

## Summary

The apps now have five **ports**, the plugs they use to reach outside services: LLM, embeddings, email, billing and calendar. Behind each is a **local stand-in**, chosen by `ADAPTER_MODE` (default `fake`), so no API keys are needed. Email is the exception: it really sends, over SMTP to Mailpit.

The **worker runtime** exists: Celery 5.6.3 on Redis :6380, with one static 60-second `tick` that beat schedules and the worker logs. Every worker log line goes through the project's redacting JSON logger and carries a trace id, including the trace id of whatever enqueued the job.

This run happened on the **Mac**, which was set up from scratch with `docs/setup/macos.md`; that was the guide's first real run. The suite grew from 346 to 429 tests, 13/13 mutations were caught, and both live checks passed.

## Structure Overview

```text
apps (later)                      config / worker (composition roots)
   │  get_email_port() …              │
   ▼                                  ▼
ports.registry ──reads──► settings.ADAPTERS ◄── config/adapters.py (table per ADAPTER_MODE)
   │  import_string + issubclass check
   ▼
ports/{llm,embedding,email,billing,calendar}.py   ← ABCs over frozen dataclasses
   ▲ implemented by
adapters/{llm/fake, email/smtp, email/memory, billing/fake, calendar/fake}

beat ──(every 60 s, "worker.tasks.tick")──► Redis :6380 ──► worker (--pool solo) ──► worker.tasks.tick → log "Tick"
        before_task_publish: trace_id header        task_prerun: bind header or mint · task_postrun: reset
```

- **Apps never import adapters.** The `apps | adapters` contract forbids it. They ask the port's registry, which reads `settings.ADAPTERS`.
- **AD-20 lives in the port.** `EmailPort.send` is final and checks the stream, the bulk unsubscribe URL and the idempotency key. Adapters only implement `_deliver`.
- **`config` and `worker` never import each other.** The Celery app (`config/celery.py`) names the task and the beat entry by dotted string.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/ports/email.py` | `Stream`, `EmailMessage`, `SendResult`, `EmailPort` (final `send` with the AD-20 rules; adapters implement `_deliver`) |
| `backend/ports/llm.py` | `LLMRequest` (instructions kept apart from `untrusted_content`, AD-9), `LLMResult` (tokens, `cost_micros`) |
| `backend/ports/embedding.py` | `embed(texts, *, dimensions)` → vectors + cost |
| `backend/ports/billing.py` | Checkout and portal sessions for `ProPlan` monthly/yearly |
| `backend/ports/calendar.py` | `Credential` (value never in repr/str), `CalendarFeed`, `CalendarEntry` (UTC, title kept out of repr) |
| `backend/ports/registry.py` | `get_<x>_port()`: resolves `settings.ADAPTERS`, checks the subclass, `ImproperlyConfigured` otherwise |
| `backend/adapters/email/smtp.py` | Django mail → Mailpit; `X-EventPulse-Stream`, `X-EventPulse-Idempotency-Key`, RFC 8058 headers on bulk |
| `backend/adapters/email/memory.py` | Records sends, for tests |
| `backend/adapters/llm/fake.py` | Deterministic fake LLM and embeddings (hash-based unit vectors) |
| `backend/adapters/billing/fake.py`, `adapters/calendar/fake.py` | Placeholder sessions; two fixed UTC entries |
| `backend/config/adapters.py` | `fake` table; `real` raises, listing the missing adapters |
| `backend/config/celery.py` | Celery app, 60 s `beat_schedule`, `setup_logging` handler, trace-id signals |
| `backend/config/management/commands/send_test_email.py` | `make send-test-email` |
| `backend/worker/tasks.py` | `tick` |
| Tests | `tests/ports/` (2 files), `tests/worker/` (2), `tests/config/test_adapters.py`, `tests/config/test_send_test_email.py`, `tests/adapters/test_email_smtp.py`, `tests/adapters/test_fakes.py` |

### Modified

| File | Changes |
|------|---------|
| `backend/config/settings.py` | `ADAPTERS`; `MAILERS` (Django 6.1) pointing at Mailpit; `CELERY_*` (broker, no results, UTC, no root-logger hijack) |
| `backend/config/__init__.py` | Exposes `celery_app` (standard Django + Celery layout) |
| `backend/adapters/logging/formatter.py` | Framework loggers: exception arguments → `<TypeName>`; `celery.app.trace` keeps only `name`/`id`/`runtime`/`description` |
| `backend/adapters/logging/redaction.py` | URL passwords scrubbed even with an empty user (`redis://:pw@host`) |
| `backend/pyproject.toml`, `uv.lock` | `celery[redis]==5.6.3` |
| `Makefile` | `worker`, `beat`, `send-test-email` |
| `.gitignore` | `backend/.celery/` (beat schedule + pidfile) |
| `README.md`, `docs/setup/{macos,ubuntu}.md` | Worker and beat section (exactly one beat), Mailpit check; macOS: Docker Desktop CLI PATH |
| `.specs-fire/standards/{tech-stack,coding-standards}.md` | Versions and pool; registry pattern; email rules; Celery logging and trace rules |
| `health-round-trip.md` | Hand-off for `make dev` |

## Key Implementation Details

### 1. "Send without a stream is a type error" (AD-20)

`stream` is keyword-only with **no default**, so Python itself raises `TypeError` when it's missing. `send` also rejects a plain `"bulk"` string or `None` (`TypeError`), a bulk message without `unsubscribe_url`, and an empty `idempotency_key` (`ValueError`). `@final` tells type checkers that adapters must not override `send`. No static type checker runs yet (mypy is still "proposed"), so the runtime raise is the enforcement.

### 2. Adapter selection

`ADAPTER_MODE` → `config/adapters.adapter_paths()` → `settings.ADAPTERS` (dotted strings) → `ports.registry` → `import_string` + `issubclass`.

- There's no caching, so `settings` overrides in tests take effect immediately.
- `real` stops startup with `ADAPTER_MODE=real is not available yet: no real adapter for billing, calendar, email, embedding, llm.`

### 3. Trace id into jobs (AD-13)

- `before_task_publish` adds the current trace id to the task headers.
- `task_prerun` binds it, but only if it matches the same pattern the API accepts. Otherwise, as with every beat tick, it mints a fresh one.
- `task_postrun` resets exactly the token that prerun created.
- This is proven end to end by an in-process worker on an in-memory broker.

### 4. Celery's own log lines

Celery logs `succeeded …: <return value>` and `raised …: <exception text>`. Both could carry personal data, and exception text is never logged under AD-13. The formatter now withholds them. Tasks return `None` by convention.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Port depth | Small starter set (user) | Feature intents reshape them; the AC needs typed shapes now |
| Worker pool | `--pool solo` on **both** OSes (user) | Prefork is broken on macOS under Celery 5.6.3; one identical setup on both machines |
| Password-only URL scrub | Fixed in this run (user) | Managed Redis URLs often have no user part |
| Ports as ABCs | Not Protocols | Incomplete adapters fail when instantiated; the registry can check `issubclass` |
| `ADAPTER_MODE=real` | Fails at startup | Never silently run stand-ins where real services are expected |
| Email settings | Django 6.1 `MAILERS` | `EMAIL_HOST`/`EMAIL_PORT` raise `RemovedInDjango2028Warning` |
| Second-beat guard | Pidfile in `backend/.celery/` | Cheap local enforcement of "exactly one beat" |
| Worker node name | `eventpulse24-worker` | `celery@<host>.local` was being scrubbed as `[email]` |

## Deviations from Plan

- **Worker pool:** the plan said `--concurrency 2` (prefork). The live run showed prefork crashing every task on macOS, and the user chose `--pool solo` on both machines.
- **Email config:** the plan said `EMAIL_HOST`/`EMAIL_PORT`; Django 6.1's `MAILERS` is used instead (deprecation).
- **Logging fix is broader than planned:** besides `celery.app.trace`, exception *arguments* to any framework logger are reduced to their type (it covers `celery.worker.request`'s `Task handler raised error: %r`).
- **Additions from review:**
  - `@final` on `send`
  - the `send_test_email` tests
  - the password-only URL scrub, approved by the user. It touches `redaction.py` from run-004.
- **`--hostname eventpulse24-worker`:** not in the plan. Added after the live run showed `[email] ready.`

## Dependencies Added

| Package | Why |
|---------|-----|
| `celery[redis]` 5.6.3 | Worker + beat (pins the spine's version) |
| `kombu` 5.6.2, `redis` 6.4.0, `billiard` 4.2.x, `vine`, `amqp`, `click*`, `tzlocal`, … | Celery's dependencies. redis-py is capped below 6.5 by kombu. |

## How to Verify

1. **Tests and gates**
   ```bash
   make test-backend    # 429 passed
   make lint-backend    # ruff clean, 12 contracts kept
   ```
2. **The tick** (three terminals, with `make up` already done)
   ```bash
   make worker
   make beat
   ```
   Expected: within ~60 s the worker prints `{"logger": "worker.tasks", "message": "Tick", "trace_id": "…", "job": "tick"}`, then one every 60 s. Each has a different trace id.
3. **Exactly one beat**: run `make beat` in a third terminal. Expected: `ERROR: Pidfile (.celery/beat.pid) already exists.`
4. **Email**
   ```bash
   make send-test-email
   make send-test-email STREAM=bulk
   ```
   Expected: both appear at <http://127.0.0.1:8025>. Headers show `X-Eventpulse-Stream: transactional` / `bulk`, and the bulk one has `List-Unsubscribe` + `List-Unsubscribe-Post`.
5. **Real mode fails fast**: `make manage ARGS=check ADAPTER_MODE=real`. Pass it as a `make` argument: the Makefile includes `.env`, which overrides an environment variable set before `make`. Expected: `ImproperlyConfigured: ADAPTER_MODE=real is not available yet: no real adapter for billing, calendar, email, embedding, llm.`

## Test Coverage

- Tests added: 66 (+17 automatic database-alias cases for the new files)
- Coverage: not measured yet (`pytest-cov` comes with `ci-pipeline`)
- Status: all passing (429)

## Developer Notes

- **macOS + Celery prefork:** billiard spawns children on macOS, and Celery 5.6.3 then skips `setup_worker_optimizations`. Every task dies with `ValueError: not enough values to unpack (expected 3, got 0)`, and because the formatter withholds the message, all you see in our logs is `ValueError` with a `RemoteTraceback`. Use `--pool solo`, or `FORKED_BY_MULTIPROCESSING=1` if prefork is ever needed locally.
- **Docker Desktop on macOS:** after a fresh install, its CLI is in `~/.docker/bin`. That directory is on `PATH` only in **new** terminals (Docker adds it to `~/.zprofile`).
- **Celery's test worker re-runs `django.setup()`,** which re-applies `settings.LOGGING` and drops root handlers added before the worker started. Attach capture handlers after `start_worker` begins. `start_worker` also makes its app the default; restore the project app afterwards.
- **The in-memory broker needs about 4 s to stop a test worker;** `shutdown_timeout` below that fails.
- **Mailpit displays header names in canonical form** (`X-Eventpulse-Stream`); headers are case-insensitive.
- **Mutation tests that swap equal-length strings** can hit stale `.pyc` files (same size, same mtime second). Clear `__pycache__` before re-running.
- **Beat's schedule file** remembers the last run, so after a restart the first tick can fire immediately. That's expected.

## Ready for Review

- [x] All acceptance criteria met (verified on macOS; Ubuntu uses the same commands)
- [x] Tests passing (429)
- [x] No critical issues (review: 2 auto-fixes, 1 approved security fix, 2 low-value items recorded)
- [x] Documentation updated (README, both setup guides, standards, hand-off)
- [x] Developer notes captured

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-006*
