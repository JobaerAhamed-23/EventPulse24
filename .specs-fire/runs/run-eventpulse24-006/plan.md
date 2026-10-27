---
run: run-eventpulse24-006
work_item: ports-fakes-and-worker
intent: project-scaffold
mode: confirm
checkpoint: plan
approved_at: 2026-10-27
---

# Implementation Plan: Ports, Fake Adapters & Worker Skeleton

## Approach

Three parts:

1. **Ports**: the plugs the apps use to reach outside services.
2. **Adapters**: the local stand-ins behind each plug, picked by `ADAPTER_MODE`.
3. **The worker runtime**: Celery worker + beat with a no-op 60-second tick.

Port depth is the **small starter set** the user chose: 1–2 actions per port, taken from what the spine and PRD already say. Feature intents reshape them later.

Environment: this run executes on the **Mac**. It was set up in this session by following `docs/setup/macos.md`: Docker Desktop, `make up`, `make db-check`, `make migrate`. The baseline is 346 passed, lint clean, and 12/12 import contracts kept.

### 1. Ports (`backend/ports/`): abstract base classes over plain frozen dataclasses

**Why ABCs, not Protocols:**
- an adapter missing a method fails when it's **instantiated**, not at first call
- the registry can check `issubclass(adapter, EmailPort)` and give a clear error when settings point at the wrong class

| Module | Port | Starter actions (typed inputs → outputs) |
|---|---|---|
| `ports/email.py` | `EmailPort` | `send(message: EmailMessage, *, stream: Stream, idempotency_key: str) -> SendResult` |
| `ports/llm.py` | `LLMPort` | `complete(request: LLMRequest) -> LLMResult`. The request keeps `instructions` and `untrusted_content` apart, so the adapter can always delimit source text (AD-9). The result carries `model`, `input_tokens`, `output_tokens` and `cost_micros`, ready for the AD-8 cost row. |
| `ports/embedding.py` | `EmbeddingPort` | `embed(texts: Sequence[str], *, dimensions: int) -> EmbeddingResult` (vectors, model, tokens, cost). `dimensions` is passed in because the spine leaves 512 vs 256 open. |
| `ports/billing.py` | `BillingPort` | `create_checkout(customer: BillingCustomer, plan: ProPlan, *, success_url, cancel_url) -> CheckoutSession`, and `create_portal_session(customer_ref, *, return_url) -> PortalSession` (FR-48..52) |
| `ports/calendar.py` | `CalendarPort` | `fetch_entries(feed: CalendarFeed) -> list[CalendarEntry]`. Read-only ICS import (AD-18). The feed URL is a `Credential` whose `repr`/`str` never show the value. Entry times are aware UTC (AD-6). |

**AD-20 lives in the port, not in each adapter.** `EmailPort.send` is a concrete method that every adapter inherits. It checks the rules once, then calls the adapter's abstract `_deliver(...)`:
- **`stream` is keyword-only with no default**: omitting it raises `TypeError` ("a send with no stream is a type error, not a default")
- a plain string such as `"bulk"` instead of a `Stream` also raises `TypeError`, so a typo can't slip through
- a `BULK` send without `unsubscribe_url` raises `ValueError` (RFC 8058 is a property of the port, per AD-20)
- **`idempotency_key` is required too** (AD-7: "every send carries a stable idempotency key"). This is one step beyond the starter `send(to, subject, body, stream)` I described, because the spine requires it on every send.

No type checker is configured yet (mypy is still "proposed" in tech-stack). The acceptance criterion's "fails type-check/raises" is met by the **raise**, plus a test that pins the signature: `stream` keyword-only and without a default.

### 2. Adapter selection by settings

Apps can't import adapters (the `apps | adapters` contract). They get one through the port, and settings decide which:

- **`config/adapters.py`**: a table of dotted paths per mode. `ADAPTER_MODE=fake` (the default) maps every port to its local adapter.
- **`ADAPTER_MODE=real` stops startup with a clear message**: "no real adapters exist yet (llm, embedding, email, billing, calendar)". That's better than silently running fakes in what someone believes is a real environment. The later intents that add real adapters fill in the `real` column.
- `settings.ADAPTERS = adapter_paths(env.adapter_mode)`
- **`ports/registry.py`**: `get_email_port()`, `get_llm_port()`, `get_embedding_port()`, `get_billing_port()` and `get_calendar_port()`.
  - Each one reads `settings.ADAPTERS[...]`, imports the class by dotted string, and checks that it subclasses the port. Otherwise it raises `ImproperlyConfigured`.
  - No caching, so `settings` overrides in tests just work.
- **Decision to note:** the registry makes `ports` import `django.conf` (settings + `import_string`). Only `ports/registry.py` does. The port modules themselves stay plain Python. This goes into coding-standards next to the existing "ports may import shared" loosening.

| Port | Local adapter (`fake` mode) | Behaviour |
|---|---|---|
| email | `adapters/email/smtp.py` `SmtpEmailAdapter` | Real SMTP to **Mailpit** via Django's mail (`EMAIL_HOST`/`PORT` from `SMTP_HOST`/`SMTP_PORT`). Adds an `X-EventPulse-Stream` header, so you can see the stream in Mailpit. Adds `List-Unsubscribe` + `List-Unsubscribe-Post: List-Unsubscribe=One-Click` on bulk mail, and an `X-EventPulse-Idempotency-Key` header. |
| email (tests) | `adapters/email/memory.py` `InMemoryEmailAdapter` | Records each send (message, stream, key) for assertions |
| llm | `adapters/llm/fake.py` `FakeLLMAdapter` | Deterministic text, word-count "tokens", cost 0, model `"fake"` |
| embedding | `adapters/llm/fake.py` `FakeEmbeddingAdapter` | Lives under `adapters/llm` because AD-8 puts embeddings behind the same gateway. Deterministic vectors (same text gives the same vector) built from a hash, unit length, `dimensions` long. |
| billing | `adapters/billing/fake.py` `FakeBillingAdapter` | Returns local placeholder URLs and a fake session id. Nothing is charged. |
| calendar | `adapters/calendar/fake.py` `FakeCalendarAdapter` | Returns a small fixed set of entries in UTC |

None of these import a provider SDK (AD-8). The `llm-sdk` and `stripe-sdk` contracts keep that true.

### 3. Worker runtime (Celery 5.6.3 + Redis on :6380)

**Dependency:** `celery[redis]==5.6.3`. It brings kombu 5.6.2 and redis-py **6.4.0**. kombu caps redis-py below 6.5, so tech-stack's "redis (current)" becomes 6.4.0 with that reason recorded.

**`config/celery.py`** (the standard Django layout; `config/__init__.py` exposes `celery_app`, so the API runtime can enqueue later):
- `Celery("eventpulse24")`, configured from Django settings (`CELERY_*`):
  - broker = `REDIS_URL`
  - no result backend (`task_ignore_result`)
  - UTC
  - `broker_connection_retry_on_startup`
- **`include=["worker.tasks"]`, by dotted string**: `config` and `worker` must not import each other (AD-1).
- **Static `beat_schedule` in code:** exactly one entry, `"tick"` → `"worker.tasks.tick"` every 60 s. No `django-celery-beat`.
- **Logging stays ours (AD-13):**
  - `worker_hijack_root_logger = False`
  - a `setup_logging` signal handler, so Celery doesn't install its own handlers and our redacting JSON handler from `settings.LOGGING` (already applied by `django.setup()`) is the only sink
- **Trace id into jobs (AD-13 hand-off):**
  - `before_task_publish` adds `current_trace_id()` to the task headers
  - `task_prerun` binds it with `bind_trace_id`. A task with no trace id (every beat tick) gets a fresh one, so worker lines are never untraced.
  - `task_postrun` resets it

**`worker/tasks.py`**:
- `tick`: logs `"Tick"` under `worker.tasks` with `extra={"job": "tick"}` and does nothing else
- comment: AD-7 seed. The due-index sweep and the AD-17 reconciler attach here later; the broker never carries the reminder schedule.

**Decision to note: Celery's own task log lines (AD-13 gap found while checking).** Celery logs `succeeded …: <return value>` and `raised …: <exception message>` on `celery.app.trace`. Today those go through as framework lines: interpolated, then only pattern-scrubbed. That breaks the rule that **exception messages are never logged**, and return values could carry personal data.
- **Fix:** `JsonFormatter` keeps only `name`, `id`, `runtime` and `description` from that logger's arguments, and replaces the return value and exception text with `[withheld]`.
- Exceptions still log their type chain and stack frames, as they do everywhere else.

**Local commands:**
- `make worker`: `celery -A config worker --loglevel INFO --concurrency 2`
- `make beat`: `celery -A config beat`, with its schedule file and **pidfile in `backend/.celery/`** (git-ignored)
  - The pidfile is a cheap guard: **a second beat refuses to start** while the first is running. Two beats would fire every tick twice.
  - The docs say to run **exactly one** beat.
- `make send-test-email TO=you@example.test`: runs a small `manage.py send_test_email` command, in `config/management/commands/` (the composition root). It sends one transactional email through `get_email_port()` to Mailpit.

### Hand-off to `health-round-trip`

`make dev` must start `worker` and `beat` (one beat) alongside the API and Next.js.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/ports/email.py` | `Stream`, `EmailMessage`, `SendResult`, `EmailPort` (AD-20 rules in `send`, adapters implement `_deliver`) |
| `backend/ports/llm.py` | `LLMRequest`, `LLMResult`, `LLMPort` |
| `backend/ports/embedding.py` | `EmbeddingResult`, `EmbeddingPort` |
| `backend/ports/billing.py` | `ProPlan`, `BillingCustomer`, `CheckoutSession`, `PortalSession`, `BillingPort` |
| `backend/ports/calendar.py` | `Credential`, `CalendarFeed`, `CalendarEntry`, `CalendarPort` |
| `backend/ports/registry.py` | `get_<x>_port()`: dotted path from settings, subclass check |
| `backend/adapters/email/smtp.py` | `SmtpEmailAdapter` (Mailpit locally) |
| `backend/adapters/email/memory.py` | `InMemoryEmailAdapter` (tests) |
| `backend/adapters/llm/fake.py` | `FakeLLMAdapter`, `FakeEmbeddingAdapter` |
| `backend/adapters/billing/fake.py` | `FakeBillingAdapter` |
| `backend/adapters/calendar/fake.py` | `FakeCalendarAdapter` |
| `backend/config/adapters.py` | Adapter table per `ADAPTER_MODE`; `real` fails fast |
| `backend/config/celery.py` | Celery app, beat schedule, logging + trace-id signals |
| `backend/config/management/__init__.py`, `commands/__init__.py`, `commands/send_test_email.py` | Manual Mailpit check |
| `backend/worker/tasks.py` | `tick` |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/pyproject.toml`, `backend/uv.lock` | `celery[redis]==5.6.3` |
| `backend/config/__init__.py` | Expose `celery_app` |
| `backend/config/settings.py` | `ADAPTERS`; `EMAIL_BACKEND`/`EMAIL_HOST`/`EMAIL_PORT` from env; `CELERY_*` settings |
| `backend/adapters/logging/formatter.py` | Withhold return values and exception text from `celery.app.trace` lines |
| `Makefile` | `worker`, `beat`, `send-test-email` |
| `.gitignore` | `backend/.celery/` |
| `README.md`, `docs/setup/macos.md`, `docs/setup/ubuntu.md` | Running the worker and beat (exactly one beat), and the Mailpit check. macOS: Docker Desktop's CLI lives in `~/.docker/bin`, which is on PATH only in new terminals. |
| `.specs-fire/standards/tech-stack.md` | Celery 5.6.3 with redis extra, redis-py 6.4.0 (kombu cap) |
| `.specs-fire/standards/coding-standards.md` | How apps get an adapter (`ports.registry`); `ports/registry.py` may import `django.conf`; AD-20 lives in `EmailPort.send`; Celery tasks return nothing worth logging |
| `.specs-fire/intents/project-scaffold/work-items/health-round-trip.md` | Hand-off: `make dev` runs one worker and exactly one beat |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/ports/test_email_port.py` | Send without `stream` → `TypeError`; `stream="bulk"` (a str) → `TypeError`; bulk without `unsubscribe_url` → `ValueError`; signature pin: `stream` keyword-only, no default; valid sends reach `_deliver` |
| `backend/tests/ports/test_registry.py` | Each getter returns the configured class; switching `settings.ADAPTERS` switches the adapter; unknown path → `ImproperlyConfigured`; class that isn't a subclass of the port → `ImproperlyConfigured` |
| `backend/tests/config/test_adapters.py` | `fake` mode maps every port to a subclass of that port; `real` mode fails with the missing list |
| `backend/tests/adapters/test_email_smtp.py` | Through Django's test outbox: recipient, subject, body; stream header; `List-Unsubscribe` + `-Post` on bulk only; idempotency header |
| `backend/tests/adapters/test_fakes.py` | Fake LLM is deterministic with token counts; fake embeddings are deterministic, unit length and the right size; billing returns URLs; calendar entries are aware UTC; `Credential` never shows its value in `repr`/`str` |
| `backend/tests/adapters/test_logging.py` (extend) | `celery.app.trace` success line withholds the return value; failure line withholds the exception text and still has the type |
| `backend/tests/worker/test_tick.py` | `tick` is callable and logs `"Tick"` on `worker.tasks` with `job=tick`; `tick.apply()` succeeds; `beat_schedule` has exactly one entry (`tick`, 60 s, registered task name); worker logging isn't hijacked |
| `backend/tests/worker/test_trace_id.py` | Publish adds the current trace id header; prerun binds it and postrun resets it; no header → a fresh id is minted. If Celery's in-process test worker works with an in-memory broker, one end-to-end test proves the id crosses a real enqueue → execute. |

**Manual verification:**
1. `make worker` + `make beat`: a `"Tick"` line appears in the worker's JSON logs within ~60 s, with a trace id. A second `make beat` refuses to start.
2. `make send-test-email`: the message appears in Mailpit at http://localhost:8025, with the stream header visible.

**Gates:** `make lint-backend` (ruff + 12 contracts) and the full suite (346 + new), all passing.

## Not in this item

- **Real adapters** (Anthropic/Voyage gateway, Resend/Postmark, Stripe, ICS parsing): later intents
- The AD-8 cost-row model, the due-index sweep, propagation and the reconciler: later intents
- A **crawl** port: the work item names five ports; `adapters/crawl/` stays empty until ingestion needs it
- mypy: still "proposed"
- `make dev`: belongs to `health-round-trip`

---
*Plan approved at checkpoint. Execution follows.*
