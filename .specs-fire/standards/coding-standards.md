# Coding Standards

## Overview

The Architecture Spine's ADs and Consistency Conventions bind these standards. Where a rule here cites an AD, the AD wins in any conflict. Terminology comes from the PRD §3 Glossary, used verbatim.

## Code Formatting

**Tool**: Ruff format (Python) · Prettier (TypeScript)
**Config**: `pyproject.toml` · `frontend/.prettierrc`
**Enforcement**: pre-commit + CI check

### Key Settings

- **Line length**: 100 (Python), 100 (TS)
- **Quotes**: double (Python), double (TS)
- **Trailing commas**: always (multi-line)

## Linting

**Tool**: Ruff + `import-linter` (Python) · ESLint with `eslint-config-next` (TS)
**Base Config**: Ruff `E,F,I,B,UP,S,DTZ,G,LOG` · `next/core-web-vitals` + `@typescript-eslint/strict`
**Strictness**: strict. CI fails on any violation.

### Key Rules

All of these are enforced by `make lint-backend` (Ruff + `lint-imports`) or by tests/checks; `tests/architecture/` plants a violation for each and asserts it is caught.

- **Layers** (import-linter `layers`, AD-1/AD-2): `config | worker` → `apps | adapters` → `ports` → `domain` → `shared`. Higher may import lower, never the reverse.
  - `config` (the API surface and composition root) and `worker` never import each other (AD-1). Celery finds tasks and beat entries by dotted string; the Celery app lives in `config/celery.py`.
  - `apps` and `adapters` never import each other: apps reach adapters through `ports` and settings.
  - **Deliberate loosening:** `ports` may import all of `shared`, including modules that use Django (the spine says `ports` → `domain` only). That's acceptable while ports are abstract classes over plain types.
  - **How an app gets an adapter:** `ports.registry.get_<x>_port()` (`get_email_port()`, `get_llm_port()`, …). It resolves the dotted path in `settings.ADAPTERS`, which `config/adapters.py` builds from `ADAPTER_MODE`, and checks the class implements the port. **`ports/registry.py` is the only `ports` module that imports Django** (`django.conf`, `import_string`); port modules stay plain Python. Never import an adapter from an app; tests may construct one directly (e.g. `InMemoryEmailAdapter`).
  - **Ports are ABCs over frozen dataclasses** (`ports/<x>.py`). A new port gets a key in `ports.registry.PORT_KEYS` and an entry in every `config/adapters.py` table. `ADAPTER_MODE=real` fails at startup until every port has a real adapter.
- **`worker-not-api`** (import-linter): `worker` never imports `apps.*.api` (AD-1).
- **`domain-pure`** (import-linter + `tests/architecture/test_stdlib_only.py`): `backend/domain/` imports the **stdlib, plus `shared.constants` and `shared.ids`**, which are themselves stdlib-only (as is `shared/__init__.py`). It must be importable without Django. **This is a deliberate departure from AD-2's "stdlib only"**, recorded in run-eventpulse24-005: it lets thresholds live once (AD-8/AD-16/AD-21).
- **`models-<app>`** (import-linter `protected`, one per app): only `apps.<X>` imports `apps.<X>.models`; other apps call `apps.<X>.services` (the chain through services is allowed; the contract checks direct imports). For the user type, use `get_user_model()` or `settings.AUTH_USER_MODEL`, never `apps.identity.models` from another app.
- **`adapters-independent`** (import-linter): adapters never import other adapters (AD-2).
- **`llm-sdk` / `stripe-sdk`** (import-linter): only `adapters.llm` imports `anthropic`, `voyageai`, `openai` or `instructor` **directly**, and only `adapters.billing` imports `stripe` (AD-8). Wiring the adapter in (`config → adapters.llm → anthropic`) is allowed.
- **New top-level packages and adapters** must be added to `[tool.importlinter]` (`root_packages`, the SDK contracts' sources, a `models-<app>` contract); a coverage test fails otherwise.
- **`eventpulse.E005`**: every concrete model in our packages subclasses `shared.models.UUIDv7Model` (auto-created M2M through tables excepted).
- **Database alias** (`tests/architecture/test_database_alias.py`, AD-3): `transaction.atomic()` / `on_commit()` always pass `using=`; no bare `@atomic`; no string literal or `None` as an alias (`using=`, `.using()`, `connections[...]`); no `from django.db import connection`. **Known limitation:** the scan is syntactic. It misses `django.db.connection` reached through `import django.db`, re-bound names (`t = transaction; t.atomic()`), and dynamically built calls. Review covers those.
- `DTZ*`: error. No naive datetimes. Everything is `timestamptz` UTC (AD-6)
- `S*` (bandit): error. Treat source content as untrusted (AD-9)
- **`os.environ` / `os.environb` / `os.getenv` / `os.getenvb`** (Ruff `TID251` banned-api): only under `backend/config/` (pydantic-settings), plus `manage.py` (bootstrap) and `tests/`.
- Frontend imports from `frontend/lib/api/` only for backend access. No hand-written fetch to backend routes (AD-19)

## Naming Conventions

### Variables and Functions

| Element | Convention | Example |
|---------|------------|---------|
| Entities (models) | PRD Glossary term, PascalCase | `PulseDigest`, `ReminderPlan`, `SavedEvent` |
| Python functions/vars | snake_case | `compose_digest` |
| Service modules | verb phrase | `compose_digest.py` |
| Queries | `get_` / `list_` prefix | `list_saved_events` |
| Commands (writes) | imperative verb | `save_event`, `resolve_conflict` |
| Domain errors | `...Error` subclass in `domain/` | `ConflictWindowError` |
| Error codes | stable snake_case slug | `event_not_found` |
| TS variables/functions | camelCase | `fetchDigest` |
| UI components | UX spine names exactly | `Card.PulseDigest`, `Input.ReminderSlot`, `Surface.Timeline` |
| Constants/thresholds | UPPER_SNAKE in `shared/` | `EXTRACTION_CONFIDENCE_PUBLISH = 0.7` |

### Files and Folders

- **Backend modules**: `snake_case.py`, one concept per module (e.g. `quiet_hours.py`)
- **Frontend files**: `kebab-case.ts(x)` (e.g. `pulse-digest-card.tsx`)
- **Django apps**: the six MVP modules only: `ingestion`, `catalog`, `personalization`, `delivery`, `identity`, `editorial`

## File Organization

### Project Structure

```
backend/
  config/          # settings, urls, asgi, database router
  domain/          # pure logic: stdlib only, no django, no entity classes
  apps/<module>/   # models · services · api · schemas · admin
  ports/           # interfaces the apps require
  adapters/        # llm/ email/ calendar/ crawl/ billing/ logging/
  worker/          # management commands: sweep loop, pipeline, retention
  shared/          # errors, ids, time, confidence thresholds, retention registry
frontend/
  app/             # next.js app router: surfaces + public event pages
  components/      # vanilla components over the token layer (no UI kit)
  lib/api/         # GENERATED from OpenAPI, never hand-edited
  styles/          # design tokens as CSS custom properties
```

### Conventions

- **Write ownership**: each entity has exactly one owning app (AD-16 table). Only the owner writes it.
- **Mutations**: every write is a named command in `apps/<owner>/services/` that owns its validation and an audit-log write in the same transaction (AD-5). Route handlers, jobs and adapters never write directly.
- **Schema wall**: two aliases on one Postgres. `default` = schema `personal`, `catalog` = schema `catalog`. `settings.DATABASE_ROUTING` maps every app with models to one of them (`eventpulse.E001` fails otherwise). Cross by id only, with no relation field (`eventpulse.E002` fails otherwise). Compose in the application layer (AD-3).
- **Always pass `using=`**: import `PERSONAL` / `CATALOG` from `shared.db` and pass them to `transaction.atomic(using=…)`, `.using(…)` and raw `connections[…]`. A bare `transaction.atomic()` silently means personal. No transaction spans both schemas; operations touching both are ordered and idempotent.
- **Catalog models never relate to `User` or `ContentType`** (both live in `personal`): no `GenericForeignKey` on catalog models; store an actor/user id by value (spine OQ-8).
- **Request handlers** validate, enqueue and return. Crawl, extraction, embedding and bulk send run in the worker (AD-11).
- **Shared constants** (confidence gates, default reminder plan `1d + 1hr`, quiet-hours rules) live once, in `shared/` (AD-16, AD-8).
- **Retention** (AD-15): **every** concrete model sets `retention_category = RetentionCategory.<X>` (`shared/retention.py`). A model with no user-derived data says so with `NOT_USER_DATA`; models we don't own go in `FRAMEWORK_RETENTION`. `eventpulse.E003` (missing) and `E004` (not a `RetentionCategory`) fail `manage.py check`. Sweep, deletion and export read `retention_registry()`. `PRD_CATEGORIES` (the 9 PRD §10.2 categories, without the exemption) is what users see.
- **Ids**: project models subclass `shared.models.UUIDv7Model` (UUIDv7 minted in Python, so a command has the id before `save()`). Public URLs use a slug, never the PK.
- **Send keys** (AD-7): join the parts with `shared.constants.SEND_KEY_SEPARATOR` (`:`), never `-` or `_`. That keeps each UUID a 36-character run, so keys survive log scrubbing.
- **LLM cost rows** (AD-8): the gateway writes "a per-call cost row in the same transaction as the result".
  - Under `apps | adapters`, the gateway can't import an app's models, so the model lives in **`adapters/llm/models.py`**, with `adapters.llm` registered as a Django app.
  - It must pass every check: routed to `catalog` in `DATABASE_ROUTING` (E001), `NOT_USER_DATA` with no user id stored (E003), and `UUIDv7Model` (E005).
  - The calling command opens `atomic(using=CATALOG)`, and the gateway writes the row inside it.
  - The FR-29 dashboard (`editorial`) reads costs through a **port query**, never by importing `adapters.llm.models`.
  - An adapter writing rows is AD-5's one named exception, by AD-8's explicit rule.
- **Audit log** (AD-5, spine OQ-8), built with the first named command: an abstract `AuditEntry` base (UUIDv7 id, `at`, `actor_id` stored by value with no FK, `action`, `target_type`, `target_id`, `details`), and **one concrete table per owning app**, so it sits in that app's schema, its owner is the only writer (AD-16), and E002 can't trip. Category `AUDIT_LOG`.

## Import Order

```python
# 1. stdlib
from datetime import datetime, UTC

# 2. third-party
from django.db import transaction
from ninja import Router

# 3. first-party, inner to outer
from domain.conflict import overlaps
from shared.errors import NotFoundError
from ports.email import EmailPort, Stream
from apps.delivery.services import schedule_sends
```

**Rules**:
- Ruff `I` (isort) enforces grouping: stdlib → third-party → first-party
- Dependencies point inward: `domain` ← `ports` ← `apps`/`adapters` ← surfaces
- Never import another app's `models`. Import its `services` (published interface).
- Frontend: `react`/`next` → third-party → `@/lib/api` → `@/components` → relative

## Error Handling

### Pattern

**Approach**: explicit domain exception types, mapped to HTTP **once** in a Django Ninja exception handler

### Guidelines

- Domain errors live in `domain/errors.py`: `DomainError` and the generic `NotFoundError`, `ValidationError`, `PermissionDeniedError`, `ConflictError`. Subclass them for specifics (`EventNotFoundError(NotFoundError)` is a 404 automatically). Never raise a bare `Exception`.
- `domain.errors.ValidationError` shares its name with pydantic's and Django's. Import it from `domain.errors` explicitly, or as `errors.ValidationError`.
- No per-endpoint try/except to build HTTP responses. `config/errors.py` is the only mapping: status by class (walking the MRO), body `{ code, message, details? }`. Framework errors (request validation, `HttpError`, `Http404`, Django `PermissionDenied` / `SuspiciousOperation` / `ValidationError`, crashes) get the same shape.
- Endpoints raise domain errors, not Ninja's `HttpError`. An `HttpError`'s own text is never shown; it gets a stable code and a calm message.
- Field errors always use `details = {"errors": [{"loc": [...], "msg": str}]}` (`shared.errors.ErrorItem`), including in a domain `ValidationError`. Declare responses with `shared.errors.ErrorOut`.
- **No existence leaks:** in personal-data paths, raise `NotFoundError`, not `PermissionDeniedError`, for a resource the caller doesn't own.
- `message` follows the UX voice: calm, no urgency language, no emoji
- LLM retry and fallback live only in the gateway. Callers never retry (AD-8).
- Operations spanning both schemas are ordered and idempotent, never "atomic" (AD-3)
- Sends are at-least-once with dedupe on the idempotency key minted at row creation (AD-7)

### Example

```python
# apps/ingestion/services/get_event.py
from domain.errors import NotFoundError

class EventNotFoundError(NotFoundError):  # code "not_found", HTTP 404 via config/errors.py
    default_message = "That event isn't available."

raise EventNotFoundError(details={"event_id": str(event_id)})
```

## Logging

**Tool**: `backend/adapters/logging/` (`JsonFormatter`, allowlist + pattern redaction) wired as the only handler in `settings.LOGGING` (Django's own handlers are removed) + a trace id per request (`config.middleware.TraceIdMiddleware`, `X-Request-ID`)
**Format**: JSON, one object per line, with trace context propagated across extraction → dedup → personalization → delivery

### Log Levels

| Level | Usage |
|-------|-------|
| ERROR | Failed operations needing attention (gateway fallback exhausted, send failure) |
| WARNING | Degraded paths (fallback model used, source paused, row `held_for_propagation`) |
| INFO | Lifecycle milestones (run started/finished, sweep tick summary, state change propagated) |
| DEBUG | Local diagnostics only. Off in production. |

### Guidelines

**How to log** (AD-13): `logger = logging.getLogger(__name__)`, then a **constant message** with the data in `extra`:

```python
logger.info("Reminder sent", extra={"send_id": send.id, "idempotency_key": key, "stream": stream})
```

- Only fields in `adapters/logging/redaction.ALLOWED_FIELDS` are kept (scrubbed for email/token shapes); any other `extra` field is logged as `[redacted]`. Adding a field to the allowlist is a reviewed change: ids, counts, durations and slugs only, **never free text**. Patterns can't recognise a title inside an allowed field.
- Project loggers (`apps`, `domain`, `adapters`, `config`, `worker`, `shared`) **never interpolate args**: `logger.info("Saved %s", title)` logs `"Saved %s"` with `args: [redacted]`. Ruff `G` forbids f-strings, `.format`, `%` and `+` in log calls. Never pass a variable as the message.
- Exception **messages are never logged**, only the type chain and the stack frames (they echo user input). Locally, `DEBUG` re-raises API errors so the debug page shows the full text.
- Framework loggers are interpolated, but an exception passed as an argument is reduced to `<TypeName>`, and `celery.app.trace` keeps only the task `name`, `id`, `runtime` and `description` (its return value and exception text are `[withheld]`). **Celery tasks return `None`**: report results through the database or a log line with allowlisted fields.
- **Jobs carry the trace id** (`config/celery.py`): it travels in the task's `trace_id` header from the code that enqueues it; a job without one (every beat tick) gets a fresh id. `settings.LOGGING` stays the worker's only sink (`setup_logging` is handled, `worker_hijack_root_logger = False`).
- Use `logger.error(..., exc_info=exc)` outside an `except` block (Ruff `LOG004`).

**Always log**:
- Ids (`event_id`, `source_id`, `user_id` as UUID, `state_change_id`), counts, durations
- LLM model, token counts and cost (also persisted as a cost row)
- Idempotency keys on send attempts

**Never log** (enforced by the logger allowlist, AD-13):
- Email addresses, names, or any PII
- OAuth tokens, secret ICS URLs, API keys
- Personal event content (titles, notes, attendees)
- Raw source HTML or prompt bodies

## Comments and Documentation

### When to Comment

- Cite the AD or FR when code exists to satisfy one (`# AD-7: key minted once, never from due_at`)
- Explain *why*, never *what*
- Mark accepted trade-offs explicitly where the spine names one

### Documentation Format

**Functions**: concise docstring for public service and domain functions (one-line summary, then args and raises if non-obvious)
**Classes**: docstring stating the Glossary term and owning module

## Code Patterns

### Preferred Patterns

#### Pure domain function

Algorithmic core with no I/O, testable without a database.

```python
# domain/conflict.py
from datetime import datetime, timedelta

CONFLICT_MIN_OVERLAP = timedelta(minutes=15)

def conflicts(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Two UTC intervals conflict when they overlap by strictly more than 15 minutes (FR-33)."""
    overlap = min(a_end, b_end) - max(a_start, b_start)
    return overlap > CONFLICT_MIN_OVERLAP
```

#### Named command with actor

Services take an explicit actor, never a `request`.

```python
# apps/personalization/services/save_event.py
def save_event(*, actor: User, event_id: UUID) -> SavedEvent:
    with transaction.atomic(using=PERSONAL):  # from shared.db
        saved = SavedEvent.objects.create(...)  # routed to PERSONAL by SchemaRouter
        write_audit(actor=actor, action="save_event", target=saved.id)
    return saved
```

### Anti-Patterns to Avoid

- **Embedding similarity as identity**: cosine ≥0.95 only routes to editorial review. Event Identity tuple decides (AD-4).
- **Per-reminder Celery task / platform cron**: the schedule lives only in `ScheduledSend` rows, swept every ≤60s (AD-7)
- **Recomputing explanations at render**: Relevance Pulse and Event Fit are persisted, never regenerated (AD-10)
- **Cross-schema join or FK**: the router and `eventpulse.E002` forbid it, so don't work around it. An inner queryset from the other schema raises `ValueError` with `.using()`, and "relation does not exist" without it (AD-3)
- **Event Fit substituted for Relevance Pulse** (or vice versa) (AD-10)
- **Session-dependent public pages** (AD-12)
- **Email send without an explicit stream** (AD-20). `EmailPort.send` enforces it for every adapter: `stream` is keyword-only with no default and must be a `Stream`; bulk needs `unsubscribe_url` (RFC 8058); every send needs an `idempotency_key` (AD-7). Adapters implement `_deliver`, never `send`.
- **Hand-editing `frontend/lib/api/`** (AD-19)
- **Component kits or animation libraries in the frontend**: UI system "None" is binding
- **Floats for money**: integer minor units + ISO-4217

---
*Generated by specs.md - fabriqa.ai FIRE Flow*
