---
run: run-eventpulse24-004
work_item: shared-foundations
intent: project-scaffold
mode: confirm
checkpoint: plan
revision: 3 (plan reviews: 10 points, then 5 more)
approved_at: 2026-10-27
---

# Implementation Plan: Shared Foundations

## Approach

This item builds the pieces that every later feature uses. Each one is small and depends on nothing new: **no new packages**.

| Piece | Where | Rule it serves |
|---|---|---|
| Error types | `domain/errors.py` (stdlib only) | Spine: domain errors are defined in `domain/` |
| Error wire shape + HTTP mapping | `shared/errors.py` (`ErrorOut` schema), `config/errors.py` (handlers, installed once on the API) | One mapping point, `{code, message, details?}` |
| UUIDv7 ids | `shared/ids.py` (stdlib only), `shared/models.py` (`UUIDv7Model` base) | Ids convention |
| PII-safe JSON logging | `adapters/logging/` (formatter, redaction, trace context) | AD-13 |
| Trace id at the API edge | `config/middleware.py` | AD-13 trace context |
| Retention registry + check | `shared/retention.py`, checks in `config/checks.py` | AD-15 |
| Shared constants | `shared/constants.py` (stdlib only) | AD-8, AD-6, AD-16, AD-21 |

It also carries out the hand-off from the schema-router spike: **`identity.User` moves to a UUIDv7 primary key** by rewriting `identity/0001` while no real data exists.

### 1. Errors

`domain/errors.py`:
- `DomainError(Exception)` has a class-level `code` slug and a `default_message`.
- An instance takes an optional `message` and optional `details: dict`.
- Generic subclasses, each with a calm default message (UX voice: no urgency, no exclamation marks, no emoji):

| Class | `code` | Default message | HTTP |
|---|---|---|---|
| `DomainError` | `domain_error` | "Something didn't work as expected." | 400 |
| `NotFoundError` | `not_found` | "We couldn't find that." | 404 |
| `ValidationError` | `invalid_input` | "Some details need another look." | 422 |
| `PermissionDeniedError` | `permission_denied` | "You don't have access to this." | 403 |
| `ConflictError` | `conflict` | "This changed since you last looked. Refresh and try again." | 409 |

- The HTTP status is **not** stored on the error, because `domain` knows nothing about HTTP. `config/errors.py` holds `STATUS_BY_ERROR` and looks a status up by walking the exception's MRO. So a later `EventNotFoundError(NotFoundError)` maps to 404 with no new entry.
- `install_error_handlers(api)` registers these handlers, and `config/api.py` calls it once:
  - `DomainError` → status from the map; body `{code, message}`, plus `details` only when given
  - Ninja's request `ValidationError` → 422 `invalid_request`
  - **One shape for field errors** *(review 2.2)*: whenever `details` carries validation errors, it is `{"errors": [{"loc": [...], "msg": str}]}`. The three sources are converted into it:
    - Ninja/pydantic: `loc` and `msg` kept; `type`, `input`, `ctx` and `url` dropped (`input` would echo the submitted value)
    - Django field-keyed (`message_dict`): one item per message, `loc: [field]`, with `__all__` → `loc: []`
    - Django un-keyed (`messages`): `loc: []`

    `shared/errors.py` defines `ErrorItem {loc: list[str | int], msg: str}`, so OpenAPI documents the shape. coding-standards asks domain `ValidationError` raisers to use the same `errors` shape in `details`. `test_errors.py` pins the exact body for all three sources.
  - `HttpError` (also `AuthenticationError`, `AuthorizationError` and `Throttled`) → a code slug derived from the status (`not_authenticated`, `permission_denied`, `rate_limited`, …)
  - `Http404` → `not_found`
  - Django's own HTTP-meaning exceptions, which Ninja's default would re-raise for Django to map *(review 4)*:
    - `django.core.exceptions.PermissionDenied` → 403 `permission_denied`
    - `SuspiciousOperation` and its subclasses → 400 `bad_request`. `DisallowedHost` is not an example here: `CommonMiddleware` raises it before Ninja runs, so Django keeps handling it *(review 2.3)*. Catching it in Ninja would hide Django's security signal, so the handler **logs it at WARNING on `django.security.<ClassName>`**, as Django does. The message is constant, with `error_type`, and the exception text isn't logged.
    - `django.core.exceptions.ValidationError` (e.g. from `full_clean()`) → **422 `invalid_input`**, with `details` in the shape above. **Why 422, not 500:** a command may legitimately use `full_clean()` as its validation step. Treating a user's bad input as a server fault would page on-call for a user error.
  - any other `Exception`:
    - **`DEBUG` off:** 500 `internal_error`. It is logged with `logger.exception`, and the response never contains the exception text.
    - **`DEBUG` on:** re-raised, so local development keeps Django's debug page and `django.request` logging *(review, minor)*.

  This way **every** API error, including framework ones, has the same shape, so the generated client sees exactly one error type.
- `shared/errors.py` defines `ErrorOut` (Ninja Schema: `code`, `message`, `details: dict | None`). Endpoints use it in `response={404: ErrorOut}`, so it appears in OpenAPI (AD-19). It lives in `shared` because `apps` must not import `config`.
- **Name clash.** The work item names the class `ValidationError`, which matches pydantic's and Django's. I keep the name it asks for. Call sites import it as `from domain.errors import ValidationError` or as `errors.ValidationError`. A note goes in coding-standards.

### 2. UUIDv7

- Python 3.13's `uuid` has no `uuid7` (that arrives in 3.14). `shared/ids.py::uuid7()` implements RFC 9562 in about 25 lines, stdlib only:
  - a 48-bit Unix time in milliseconds
  - a 12-bit counter, kept monotonic within the process under a lock (RFC 9562 §6.2, method 1). Each new millisecond seeds it with `secrets.randbits(11)`: the **top bit is cleared**, so there are at least 2048 increments of headroom before an overflow borrows a future millisecond *(review 8)*.
  - 62 random bits
- If the counter overflows, or the clock goes backwards, it borrows the next millisecond. **Ids from one process are always strictly increasing.**
- A comment says to replace it with `uuid.uuid7` when the project moves to Python 3.14.
- `shared/models.py::UUIDv7Model`, an abstract model: `id = UUIDField(primary_key=True, default=uuid7, editable=False)`.
- **The id is minted in Python, not by Postgres 18's `uuidv7()`.** Commands then have the id before `save()`, which they need for audit rows and for idempotency keys minted at creation (AD-7).
- `DEFAULT_AUTO_FIELD` stays `BigAutoField`. It only affects Django's own models (Group, Permission, LogEntry).
- **`identity.User(UUIDv7Model, AbstractUser)`**:
  1. Delete `identity/0001_initial.py` and regenerate it.
  2. Recreate the dev DB: `make reset-db FORCE=1`, then `make migrate`.

  The probe `Note.owner` FK picks up the new column type with no change to its migration. **On the Mac:** `make reset-db && make migrate` (walkthrough note).

### 3. Logging (AD-13)

Call sites keep using plain `logging.getLogger(__name__)`. They write a **constant message**, and put data in `extra={...}`. Redaction happens in the formatter, so it doesn't depend on call-site discipline.

`adapters/logging/`:

- `context.py`: a `trace_id` `ContextVar` with `bind_trace_id()`, `reset_trace_id()` and `current_trace_id()`. It works under WSGI, ASGI and, later, in the worker.
- `redaction.py`:
  - `ALLOWED_FIELDS` (frozenset): ids (`event_id`, `source_id`, `user_id`, `state_change_id`, `send_id`, `idempotency_key`), counts and durations (`count`, `duration_ms`, `attempt`), the LLM accounting fields (`model`, `input_tokens`, `output_tokens`, `cost_micros`), and `stream`, `slot`, `status_code`, `method`, `error_code`, `error_type`, `job`.
  - `scrub(value)`: replaces email-shaped substrings with `[email]` (including `%40`-encoded ones) and token-shaped substrings with `[token]`. Every token pattern is **anchored and has a minimum body length**, so it can't fire inside ordinary words *(review 2)*:
    - provider prefixes need a word boundary and at least 16 body characters: `\b(?:sk|rk|pk|ghp|whsec|sk_live|sk-ant)[-_][A-Za-z0-9_-]{16,}`, `\bxox[abprs]-[A-Za-z0-9-]{16,}`. So `network_check`, `work_item` and `task-…` are untouched.
    - JWTs: `\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}`
    - `Bearer <credential>`
    - credentials in a URL: `://user:pass@`
    - `token=`, `key=`, `secret=`, `password=`, `signature=` query values
    - `webcal://` URLs and Google `private-…` ICS segments
    - any unbroken `[A-Za-z0-9_-]` run of **40 or more** characters. It can't hit an id, because a dashed UUID is 36 characters, a hex UUID or trace id is 32, and send keys are `:`-separated (below).
  - Nested dicts and lists are scrubbed recursively. **Values that aren't JSON-native** (`UUID`, `Decimal`, `datetime`, models) go through `str()` before scrubbing, and the final `json.dumps(..., default=str)` is a second safety net, so one log call can never crash the handler *(review 6)*.
- **Send-key separator fixed now** *(review 2)*. `shared/constants.py` gains `SEND_KEY_SEPARATOR = ":"`, so AD-7's `user_id · event_reminder · event_id · slot · event_version` is minted as `<uuid>:event_reminder:<uuid>:1d:3`. Each UUID stays a 36-character run and the whole key survives logging. A test logs a realistic key and asserts it comes out unchanged.
- `formatter.py::JsonFormatter`: one JSON object per line:
  - `ts`: UTC ISO-8601, milliseconds
  - `level`, `logger`
  - `message` *(review 1)*:
    - **Project loggers** (names under `apps`, `domain`, `adapters`, `config`, `worker`, `shared`): the **template** `record.msg` only, never interpolated. If the call passed positional args, the line gets `"args": "[redacted]"`. `logger.info("Saved %s", event.title)` therefore logs `"Saved %s"` with `args` redacted, and the title never reaches the sink, whatever the lint does. **The template is still pattern-scrubbed** (a deliberate exception to review 2.4). Nothing enforces that it is a literal: `G` catches f-strings, `.format`, `%` and `+`, but not `logger.info(user.email)` or `logger.info(title)`. Scrubbing catches the email case, at the cost of a long identifier in a hand-written sentence becoming `[token]`, which is rare.
    - **Framework loggers** (`django.*`, third-party), which rely on `%s`: interpolated, then scrubbed.
  - **Not scrubbed:** `exc_stack` (code only: paths, function names, source lines, never runtime values, *review 2.4*) and `trace_id`. `trace_id` comes from the context: either minted or validated at the edge (below).
  - every `extra` field: kept and scrubbed if allowlisted, otherwise its key with the value `"[redacted]"`. Standard `LogRecord` attributes are excluded from extras.
  - exceptions *(review 5)*:
    - **`exc_type`**: the qualified type name, followed through the `__cause__` / `__context__` chain
    - **`exc_stack`**: the formatted stack frames (file, line, function, source line)
    - **`str(exc)` is never logged, for any logger.** That closes the pydantic `input_value='<title>'` case, `IntegrityError`'s `Key (email)=(…)` and any other exception that echoes user content. The cost is losing the message text, such as a constraint name, in logs. Locally, the `DEBUG` re-raise still shows the full exception on the debug page. This goes in coding-standards.
- `settings.LOGGING` *(review 2.1)*: one stdout handler with `JsonFormatter`, root at INFO, `disable_existing_loggers=False`. Django's own handlers are **removed**, not just bypassed. Django's `DEFAULT_LOGGING` is applied first and attaches:
  - `console`, on `django` when `DEBUG` is on: an unredacted second copy of every line
  - `mail_admins`, on `django` when `DEBUG` is off: it emails the full request and traceback with no redaction, a PII side channel even though `ADMINS` is empty today
  - its own handler on `django.server`, with `propagate: False`

  So `LOGGING["loggers"]` sets:
  - `"django": {"handlers": [], "level": "INFO", "propagate": True}`
  - `"django.server": {"handlers": [], "level": "INFO", "propagate": True}`
  - **`"django.db.backends": {"level": "WARNING"}`**: at DEBUG it logs SQL with parameter values (titles), which patterns can only partly scrub

  A test asserts that `django` and `django.server` have no handlers of their own, that no `AdminEmailHandler` is attached anywhere, that both propagate to the root's single JSON handler, and that `django.db.backends` is at WARNING.
- Ruff gains the `G` (logging-format) and `LOG` rules. **This is hygiene, not the guarantee:** `G` doesn't catch positional args. The guarantee is the formatter rule above.
- **The remaining limit, named in coding-standards:** free text inside an **allowlisted** field (e.g. someone puts a title into `error_code`) can't be detected by patterns. Allowlisted fields are ids, counts and slugs by definition, so never put free text in one.

### 4. Trace id at the API edge

`config/middleware.py::TraceIdMiddleware` runs **first** in `MIDDLEWARE`:
- It takes an inbound `X-Request-ID` only if it matches `^[A-Za-z0-9-]{8,36}$`. That allows a UUID at most, so nothing can inject into the logs and nothing reaches the 40-character token rule *(review 2)*. Otherwise it mints `uuid7().hex`.
- It binds the id for the request and resets it in `finally`.
- It echoes the id in the `X-Request-ID` response header.

Propagating the id into worker jobs belongs to `ports-fakes-and-worker` and is handed over.

### 5. Retention registry (AD-15)

`shared/retention.py::RetentionCategory(StrEnum)` has one member per PRD §10.2 bullet (**9 bullets**, review 3), each with a comment giving its window, plus one exemption:

| Member | PRD §10.2 window |
|---|---|
| `ACCOUNT_CONTENT` | Personal and saved events: while the account is active; purged ≤30 days after deletion |
| `ACCOUNT_IDENTITY` | Personal email addresses and calendar credentials: while active; purged on disconnect or deletion; encrypted |
| `PREFERENCE_SIGNALS` | 12 months rolling |
| `EMAIL_DELIVERY_EVENTS` | 90 days, then aggregated counts |
| `AUDIT_LOG` | 24 months |
| `SOURCE_REGISTRY` | Event date range + 12 months, then archived |
| `TOS_REVIEW_RECORDS` | 7 years |
| `BILLING_RECORDS` | 7 years |
| `ANALYTICS_AGGREGATES` | Anonymized aggregates: kept indefinitely, no PII |
| `NOT_USER_DATA` | **Not a PRD category.** An explicit exemption for tables with no user-derived data. Never shown in the "What we store" inventory. |

- `PRD_CATEGORIES` is the 9 PRD members, without the exemption. The future "What we store" page and export read it. A test pins it to PRD §10.2.
- The spine says "seven", but the PRD has nine. Noted in the walkthrough.
- Models declare `retention_category = RetentionCategory.X`.
- Models we don't own are covered in one dict, `FRAMEWORK_RETENTION`:
  - `sessions.session` → **`ACCOUNT_IDENTITY`** *(review 9)*: an auth credential that dies on expiry or logout, and immediately on account deletion. Expired sessions are cleared by the future sweep via `clearsessions`.
  - `admin.logentry` → `AUDIT_LOG`
  - `auth.group`, `auth.permission`, `contenttypes.contenttype` → `NOT_USER_DATA`
- `retention_registry()` returns `{model: category}` for every concrete model. The future sweep, deletion and export (FR-52) all read it.
- **Fail-closed scope:** *every* concrete installed model must have a category, either its own or from the framework map. The check doesn't try to decide which models hold "user-derived data"; a model with no user data says so with `NOT_USER_DATA`. This mirrors E001: a new app or a new model can't slip past by omission. Auto-created M2M through tables are skipped, because they go with their owner.
- Checks in `config/checks.py`, written as pure functions plus thin wrappers, the same pattern as E001/E002:
  - **`eventpulse.E003`**: a model has no retention category
  - **`eventpulse.E004`**: the declared value isn't a `RetentionCategory`
- Declarations added:
  - `identity.User` → `ACCOUNT_IDENTITY`
  - the probes: `Thing` → `NOT_USER_DATA`, `Note` → `ACCOUNT_CONTENT`

### 6. Constants (`shared/constants.py`, stdlib only)

```text
EXTRACTION_CONFIDENCE_REJECT  = Decimal("0.50")   # below: auto-reject (AD-8)
EXTRACTION_CONFIDENCE_PUBLISH = Decimal("0.70")   # below: editorial review, never in a digest (AD-8)
TZ_INFERENCE_CONFIDENCE_DIGEST = Decimal("0.70")  # below: not digest-eligible until reviewed (AD-6)
ReminderSlot(StrEnum): FIVE_DAYS="5d", TWO_DAYS="2d", ONE_DAY="1d", ONE_HOUR="1hr"
REMINDER_SLOT_OFFSET = {slot: timedelta}
DEFAULT_REMINDER_PLAN = (ReminderSlot.ONE_DAY, ReminderSlot.ONE_HOUR)   # FR-9 = FR-20 (AD-16)
CONFLICT_MIN_OVERLAP = timedelta(minutes=15)      # strictly more than this conflicts (FR-33, AD-21)
SEND_KEY_SEPARATOR = ":"                          # AD-7 key parts; keeps each UUID a 36-char run
```

- The gates are `Decimal` values, matching the spine's `numeric(3,2)`.
- **Layering question for `architecture-contracts`:** `domain/conflict.py` and `domain/confidence.py` will need these values, but AD-2 allows `domain` the stdlib only. `shared/constants.py` is therefore kept stdlib-only, with a fresh-interpreter guard test like the domain one. Two options remain:
  - the import-linter contract explicitly allows `domain → shared.constants`
  - domain functions take thresholds as parameters

  `architecture-contracts` decides; I recommend the first.

## Not in this item (proposed)

- **The AD-5 audit log is not built here.** It isn't in this item's acceptance criteria, and no named command exists yet to write it. The OQ-8 design, recorded in coding-standards so the first command builds it this way:
  - an abstract `AuditEntry` base: UUIDv7 id, `at`, `actor_id` stored by value, `action`, `target_type`, `target_id`, `details`
  - one concrete table **per owning app**, so the table sits in its app's schema, its owner is the only writer (AD-16), and E002 can't trip
  - category `AUDIT_LOG`
- **A primary-key rule** (project models must use `UUIDv7Model`) belongs with the other static rules → handed to `architecture-contracts`.
- **i18n of error messages** (PRD §11.6): the defaults are plain English strings in `domain`. They get extracted when the i18n catalogue is set up → noted for `frontend-skeleton` / i18n.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/domain/errors.py` | `DomainError` + 4 generic subclasses |
| `backend/shared/errors.py` | `ErrorOut`, `ErrorItem` schemas |
| `backend/shared/ids.py` | `uuid7()` |
| `backend/shared/models.py` | `UUIDv7Model` |
| `backend/shared/retention.py` | `RetentionCategory`, `PRD_CATEGORIES`, `FRAMEWORK_RETENTION`, `retention_category_of()`, `retention_registry()` |
| `backend/shared/constants.py` | Gates, reminder slots/plan, conflict overlap, `SEND_KEY_SEPARATOR` |
| `backend/config/errors.py` | `STATUS_BY_ERROR`, `install_error_handlers(api)` |
| `backend/config/middleware.py` | `TraceIdMiddleware` |
| `backend/adapters/logging/{context,redaction,formatter}.py` | Trace context, allowlist + scrub, JSON formatter |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/config/api.py` | `install_error_handlers(api)` |
| `backend/config/settings.py` | `TraceIdMiddleware` first; `LOGGING` |
| `backend/config/checks.py` | E003/E004: pure function + registered wrapper |
| `backend/apps/identity/models.py`, `migrations/0001_initial.py` | `UUIDv7Model` base, `retention_category`; migration regenerated |
| `backend/tests/wall/{catalog_probe,personal_probe}/models.py` | `retention_category` (class attributes only, so no migration change) |
| `backend/pyproject.toml` | Ruff `G`, `LOG` |
| `.specs-fire/standards/coding-standards.md` | Error types/location, `ValidationError` name note; **in personal-data paths, raise `NotFoundError`, not `PermissionDeniedError`, for a resource the caller doesn't own (no existence leak, review 7)**; logging rules (constant messages, data only in allowlisted extras, project-logger args never interpolated, exception messages never logged, no free text in allowlisted fields); `SEND_KEY_SEPARATOR`; retention declaration + E003/E004; `UUIDv7Model`; audit-log design (OQ-8) |
| `.specs-fire/standards/testing-standards.md` | Asserting on logs via the JSON formatter |
| `.specs-fire/intents/project-scaffold/work-items/{architecture-contracts,ports-fakes-and-worker}.md` | Hand-offs: `domain → shared.constants`, PK rule, `os.environ`/`manage.py`, alias-less `atomic()` lint; trace id into jobs |

## Tests

| File | Covers |
|------|--------|
| `tests/domain/test_errors.py` (no Django) | Codes, default and custom messages, details; subclasses are `DomainError`; no `!` in default messages |
| `tests/shared/test_ids.py` (no DB) | Version 7 + RFC variant; 10k ids strictly increasing; frozen clock (counter overflow → next ms, still increasing); clock going backwards → still increasing; timestamp within the current ms window; uniqueness |
| `tests/shared/test_constants.py` | Spine values; default plan is `1d + 1hr`; offsets; `SEND_KEY_SEPARATOR`; fresh-interpreter guard: `shared.constants` and `shared.ids` load no Django |
| `tests/shared/test_retention.py` | `PRD_CATEGORIES` is exactly the 9 PRD §10.2 bullets, and `NOT_USER_DATA` isn't among them; `sessions.session` → `ACCOUNT_IDENTITY`; registry covers every installed model; `User` → `ACCOUNT_IDENTITY`; framework map entries |
| `tests/adapters/test_logging.py` (no DB) | JSON line shape and UTC `ts`; allowlisted field kept; non-allowlisted field `[redacted]`; **email redacted inside an allowed field**; **JWT, `Bearer`, `sk-ant-…`, URL credentials, `token=` and a secret ICS URL redacted**; **no false positives**: `network_check`, `work_item`, `task-runner`, a dashed UUID, a hex trace id and a **realistic `:`-separated send key** all survive; **a project logger with a positional arg logs the template plus `args: [redacted]`, and the title never appears**; a framework logger is interpolated and scrubbed; **an exception carrying a title/email in its message logs `exc_type` + `exc_stack` and the message text appears nowhere**, including through a `__cause__` chain; a 48-character function name appears intact in `exc_stack`; **`UUID`/`Decimal`/`datetime` and an arbitrary object in extras don't crash and serialise as strings**; nested values scrubbed |
| `tests/api/test_errors.py` | Throwaway `NinjaAPI` + `install_error_handlers` + Ninja `TestClient`: each error → status + exact body; `details` present or absent; an `EventNotFoundError(NotFoundError)` subclass → 404; request validation → 422 `invalid_request`; **all three validation sources produce exactly `details.errors = [{loc, msg}]`** (pydantic `input` not echoed; `__all__` → `loc: []`); `HttpError(401)` → `not_authenticated`; `Http404`; **Django `PermissionDenied` → 403, `SuspiciousOperation` → 400 **and a WARNING on `django.security.SuspiciousOperation` without the exception text**, Django `ValidationError` → 422 `invalid_input` with field details**; an unhandled exception with `DEBUG=False` → 500 `internal_error`, no exception text in the body, logged; with `DEBUG=True` → re-raised; the real `config.api.api` maps `DomainError` (via `api.on_exception`) |
| `tests/api/test_trace_id.py` | Through Django's `Client` with a test URLconf: header minted (32 hex); a valid inbound id (≤36 chars) is echoed; an invalid one, or a 37-char one, is replaced; **every log line from the request carries the same `trace_id` as the header**; context reset after the request |
| `tests/config/test_checks.py` (+) | E003 for an undeclared isolated model, **and gone once it is declared**; E004 for a bad value; auto-created through tables ignored; framework map honoured; wrapper honours `app_configs`; the real project passes `check` |
| `tests/config/test_logging_config.py` | `django` / `django.server` have no own handlers and propagate; no `AdminEmailHandler` anywhere; root has exactly the JSON handler; `django.db.backends` at WARNING; `TraceIdMiddleware` is first |
| `tests/identity/test_user.py` | `User` pk is a version-7 UUID set before save; the DB column is `uuid` in schema `personal` |

**Mutation checks** (each reverted after):
- the formatter keeps non-allowlisted fields
- the email pattern is removed
- **a project logger with a positional arg is interpolated** *(review 1)*
- `str(exc)` added back to the exception output
- the prefix patterns lose their `\b` / minimum length (false positives return)
- E003 is disabled
- the counter isn't monotonic
- the handler leaks the exception text
- Django's default `console` / `mail_admins` handlers left on `django`
- the middleware is removed

## Order of work

1. ids + models + User/migration
2. reset the dev DB, migrate, and run the suite
3. constants
4. errors and handlers
5. logging + middleware
6. retention + checks
7. standards and hand-offs
8. full suite, lint, `check`, mutations
