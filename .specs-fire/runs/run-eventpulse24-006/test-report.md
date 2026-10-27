---
run: run-eventpulse24-006
work_item: ports-fakes-and-worker
intent: project-scaffold
generated: 2026-10-27
status: passed
machine: macOS 26.4.1 (Apple Silicon), Docker Desktop 29.9.2
---

# Test Report: Ports, Fake Adapters & Worker Skeleton

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Email port, AD-20 (`tests/ports/test_email_port.py`) | 10 | 0 | 0 | n/a |
| Adapter registry (`tests/ports/test_registry.py`) | 12 | 0 | 0 | n/a |
| `ADAPTER_MODE` tables (`tests/config/test_adapters.py`) | 4 | 0 | 0 | n/a |
| SMTP adapter via the test outbox (`tests/adapters/test_email_smtp.py`) | 2 | 0 | 0 | n/a |
| Fake LLM / embedding / billing / calendar, `Credential` (`tests/adapters/test_fakes.py`) | 11 | 0 | 0 | n/a |
| Celery log-line redaction (added to `tests/adapters/test_logging.py`) | 4 | 0 | 0 | n/a |
| Password-only URL scrubbing (review fix, `tests/adapters/test_logging.py`) | 5 | 0 | 0 | n/a |
| `send_test_email` command (review fix, `tests/config/test_send_test_email.py`) | 3 | 0 | 0 | n/a |
| Tick + beat schedule (`tests/worker/test_tick.py`) | 5 | 0 | 0 | n/a |
| Trace id into jobs, incl. one real in-process worker (`tests/worker/test_trace_id.py`) | 10 | 0 | 0 | n/a |
| Database-alias scan: one case per new project file (existing test) | +17 | 0 | 0 | n/a |
| Existing suite (unchanged) | 346 | 0 | 0 | n/a |
| **Total (pytest)** | **429** (was 346) | 0 | 0 | n/a |
| `make lint-backend` (ruff, format, `lint-imports`) | clean; 12 contracts kept | | | |
| `manage.py check` / `makemigrations --check` | no issues / no changes | | | |
| Mutation checks | 13/13 caught | | | |

Coverage isn't measured yet: `pytest-cov` comes with `ci-pipeline`. The suite runs in about 7.8 s; the real-worker trace test accounts for about 5 s, because the in-memory broker needs about 4 s to shut the worker down. Shorter shutdown timeouts fail.

## Acceptance Criteria Validation

- ✅ **`ports/` defines `LLMPort`, `EmbeddingPort`, `EmailPort`, `BillingPort`, `CalendarPort` with typed inputs/outputs.** Abstract classes over frozen dataclasses, using the starter shapes the user chose. An adapter missing a method can't be instantiated (tested).
- ✅ **`EmailPort.send` requires `stream`; omitting it is a type error (AD-20).** `stream` is keyword-only with no default, so omitting it raises `TypeError`. A plain string or `None` also raises `TypeError`. Both checks are tested, and the signature is pinned by a test. No static type checker is configured (mypy is still "proposed"), so "raises" is the half of the criterion that's met. The same check also requires `unsubscribe_url` on bulk sends (RFC 8058) and an `idempotency_key` (AD-7).
- ✅ **Fake adapters for each port; email delivers to Mailpit; selection comes from settings (`ADAPTER_MODE=fake` default).** `config/adapters.py` → `settings.ADAPTERS` → `ports.registry`. `ADAPTER_MODE=real` fails at startup, naming every missing adapter.
- ✅ **Celery with the Redis :6380 broker; static `beat_schedule` with one 60 s no-op `tick`; no `django-celery-beat`.**
- ✅ **`make worker` and `make beat` run them locally; docs say exactly one beat.** Covered in the README and both setup guides. `make beat`'s pidfile makes a second beat refuse to start (verified).
- ✅ **Tests: adapter selection by config; email without stream fails; tick callable.**
- ✅ **Verified manually** (see below).

Hand-offs delivered:
- **Trace id into jobs:** the publish header plus prerun/postrun binding. Proven end to end through a real worker.
- **`worker_hijack_root_logger = False`**, plus a `setup_logging` handler. Every worker line is JSON through `settings.LOGGING`.
- **Celery app in `config/celery.py`**, with tasks named by dotted string. No `config ↔ worker` import; the layers contract is still kept.

## Manual Verification (macOS, this session)

1. **Tick:** `make worker` + `make beat`. Beat logged `Sending due task tick (worker.tasks.tick)`. The worker logged `{"logger": "worker.tasks", "message": "Tick", "job": "tick", "trace_id": "01a17de3…"}` at 15:03:40 and again at 15:04:39 (59 s apart), each with a fresh trace id. Celery's "succeeded" line ended in `[withheld]`. Every worker line was JSON.
2. **Exactly one beat:** a second `make beat` exited with `ERROR: Pidfile (.celery/beat.pid) already exists. Seems we're already running?`. After a clean stop, the pidfile is removed.
3. **Mailpit:**
   - `make send-test-email` and `make send-test-email STREAM=bulk TO=reader@example.test` both appeared in Mailpit (API at :8025).
   - Headers: `X-Eventpulse-Stream: transactional` / `bulk` and `X-Eventpulse-Idempotency-Key: test-email:<uuid7>`.
   - The bulk message also had `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click`.
4. **macOS setup guide:** followed from scratch in this session (Docker Desktop, `make env`, `doctor`, `up`, `db-check`, `migrate`). Everything passed. This is the first macOS run of the guide (it was pending since run-eventpulse24-001).

## Issues Found During Execution

| Issue | Resolution |
|---|---|
| **Celery prefork pool broken on macOS.** billiard spawns children; Celery 5.6.3 skips `setup_worker_optimizations` for spawned children, so every task failed with `ValueError: not enough values to unpack (expected 3, got 0)` | User decision: `make worker` uses `--pool solo` on **both** OSes. The `FORKED_BY_MULTIPROCESSING=1` workaround also worked, but was declined. |
| Celery's `succeeded …: <return value>` / `raised …: <exc>` lines would log payloads and exception text (AD-13) | `JsonFormatter`: allowlisted keys for `celery.app.trace`; exception arguments to framework loggers become `<TypeName>` |
| Worker node name `celery@Jobaers-MacBook-Air.local` was scrubbed to `[email]` | `--hostname eventpulse24-worker` (no `.host` part) |
| Django 6.1 deprecates `EMAIL_HOST` / `EMAIL_PORT` (`RemovedInDjango2028Warning`) | `MAILERS` setting instead; the suite runs clean with `-W error::DeprecationWarning` |
| The test worker's `django.setup()` re-applies `settings.LOGGING` and drops handlers added earlier | The test attaches its capture handler after the worker starts, and restores the project app as the default afterwards |

## Mutation Checks (each reverted after)

All caught: stream type check removed · `stream` given a default · bulk unsubscribe check removed · registry subclass check removed · `real` mode silently using fakes · `celery.app.trace` allowlist removed · exception arguments interpolated · tick every 30 s · trace header not attached · inbound trace id not validated · postrun not resetting · bulk unsubscribe headers dropped · URL scrubber requiring a user part again (review fix).

## Ready for Review

- [x] All tests passing
- [x] Lint and the 12 import contracts clean
- [x] All acceptance criteria validated (on macOS; Ubuntu runs the same commands)
- [x] Manual verification done
