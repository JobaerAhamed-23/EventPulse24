---
run: run-eventpulse24-005
work_item: architecture-contracts
intent: project-scaffold
mode: confirm
checkpoint: plan
revision: 2 (plan review: 7 points + 6 minor applied)
approved_at: 2026-10-27
---

# Implementation Plan: AD-2 Architecture Contracts

## Approach

Make the layering rules machine-checked, and prove each rule catches a planted violation. There are three tools, each used where it is precise:

| Rule | Tool | Why this tool |
|---|---|---|
| Import direction between packages (layers, cross-app models, adapter independence, provider SDKs) | **import-linter 2.15** (`[tool.importlinter]` in `pyproject.toml`) | Sees the whole import graph, including indirect chains |
| `domain` imports **only the stdlib** | AST test over `domain/**` with `sys.stdlib_module_names` | import-linter can only forbid packages it's told about. An allowlist is the only way to say "stdlib only". |
| `os.environ` / `os.getenv` outside `config/` | **Ruff `TID251` banned-api** | Catches attribute use (`os.environ[...]`, `from os import environ`), not just imports |
| Database calls name their alias (hand-off from schema-router-spike) | AST test | Ruff has no custom rules |
| Project models use `UUIDv7Model` (hand-off from shared-foundations) | System check `eventpulse.E005` | Same place as E001–E004; fails `manage.py check` |

**New dev dependency:** `import-linter==2.15` (released 2026-09-04; brings `grimp` 3.18). I probed it against our tree in a scratch copy:
- the proposed layers already pass on the current code
- `apps | adapters` is accepted
- an import of an **uninstalled** SDK (`anthropic`) is still detected, so we don't need to install SDKs to ban them

### 1. import-linter contracts (`backend/pyproject.toml`)

`root_packages`: `domain`, `apps`, `ports`, `adapters`, `config`, `worker`, `shared`. `include_external_packages = true`, so Django and the SDKs are visible.

| Contract | Type | Rule |
|---|---|---|
| **AD-2 layers point inward; AD-1 runtimes don't import each other's surface** | `layers` | `config \| worker` → `apps \| adapters` → `ports` → `domain` → `shared`. Higher may import lower, never the reverse. **`config \| worker` are independent** *(review 3)*: the API surface (`config.api`, `config.urls`) and the worker runtime never import each other. Celery finds tasks and beat entries by dotted string, so `config/celery.py` needs no `worker` import. `apps \| adapters` are independent: apps reach adapters only through ports and settings. |
| **AD-1 worker doesn't import the API surface** | `forbidden` | `worker` must not import `apps.*.api` (the per-app Ninja routers) *(review 3)* |
| **AD-2 domain is pure** | `forbidden` | `domain` must not import `django`, `ninja`, `pydantic`, `psycopg`, `celery`, or `shared`, **except** `shared.constants` and `shared.ids` (`ignore_imports`, unmatched-ignore alerting off because nothing imports them yet). This is the import-linter half; the AST test below is the strict allowlist. |
| **AD-2 no cross-app models** ×6 | `protected` | `apps.<X>.models` may be imported only by `apps.<X>` (one contract per app). Other apps call `apps.<X>.services`. |
| **AD-2 adapters are independent** | `independence` | `adapters.*` siblings never import each other |
| **AD-8 LLM SDKs only in adapters.llm** | `forbidden`, **`allow_indirect_imports = true`** *(review 1)* | No module outside `adapters.llm` imports `anthropic`, `voyageai`, `openai` or `instructor` **directly**. Indirect chains are allowed: `config`/`worker` wiring in `adapters.llm` (`config → adapters.llm → anthropic`) is the intended path, and the layers contract already blocks `apps → adapters`. |
| **Stripe SDK only in adapters.billing** | `forbidden`, **`allow_indirect_imports = true`** | The same, for `stripe` |

- `shared` sits at the bottom: it is the utility layer (constants, ids, error schemas, retention). It may import Django but nothing of ours above it.
- **Deliberate loosening** *(review, minor)*: the spine has `ports` importing `domain` only. Under these layers, `ports` may also import all of `shared`, including the Django-using modules (`shared.errors`, `shared.models`). That's acceptable while ports are Protocols over plain types; it's recorded in coding-standards. Tightening it is a forbidden contract (`ports` → `django`) if it ever matters.
- **Cross-app calls go through services** *(review 2)*: `apps.catalog → apps.ingestion.services → apps.ingestion.models` is the intended chain. Confirmed in import-linter 2.15's source: `protected` only checks **direct** importers (`find_modules_that_directly_import`; the docstring says "only *directly* imported by"). A planted test pins this, so a future import-linter that followed chains would fail loudly instead of silently breaking every service call.
- **`apps.<X>` can't import `apps.identity.models` either.** Code that needs the user type uses `django.contrib.auth.get_user_model()`, or `settings.AUTH_USER_MODEL` in FKs. Recorded in coding-standards.
- Tests (`tests/`) aren't a root package, so they may import anything.

**Coverage guards:** tests assert that
- every top-level package in `backend/` (except `tests`) is listed in `root_packages`
- **every `adapters/<x>` package is accounted for** in the SDK contracts' source lists, and every `apps/<x>` has its `protected` contract *(review, minor)*

A new package or adapter can't silently escape the contracts.

### 2. `domain` is stdlib-only (AST)

**A deliberate departure from AD-2 as written** *(review 4)*: the spine and coding-standards say `domain` imports the stdlib only. This item allows exactly `shared.constants` and `shared.ids`, both stdlib-only themselves, so thresholds live once (AD-8/AD-16/AD-21) without passing every constant as a parameter. It is recorded as a run decision, and coding-standards is reworded: "stdlib, plus `shared.constants` and `shared.ids`, which are themselves stdlib-only".

`tests/architecture/test_stdlib_only.py` parses every `domain/**/*.py`, plus `shared/constants.py`, `shared/ids.py` **and `shared/__init__.py`**. The package `__init__` runs on every `from shared.constants import …`, so a Django import there would leak into `domain` even though the AST of `domain` itself looks clean *(review 4)*. Every import's top-level name must be in `sys.stdlib_module_names`. The only exceptions are relative imports inside `domain`, `domain.*` itself, and `shared.constants` / `shared.ids`. The existing fresh-interpreter guard (`test_domain_is_django_free.py`) stays: it covers the **import-time** half of the last acceptance criterion.

### 3. `os.environ` ban (Ruff)

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"os.environ".msg  = "Read configuration from config.env (pydantic-settings), not os.environ."
"os.environb".msg = "…same…"
"os.getenv".msg   = "…same…"
"os.getenvb".msg  = "…same…"
```

- `TID` is added to `select`.
- Per-file ignores for `TID251`:
  - `config/**`: the only place the environment is read
  - `manage.py`: Django's bootstrap `setdefault`
  - `tests/**`: tests build subprocess environments
- The future Celery app module goes in **`config/celery.py`** (the standard Django layout), so its `os.environ.setdefault("DJANGO_SETTINGS_MODULE", …)` falls under `config/**` and needs no new exemption *(review, minor)*. Noted in the `ports-fakes-and-worker` work item.
- `TID252` (relative parent imports) comes with `TID`; the tree has none.

### 4. Database calls name their alias (AST)

This turns the "always pass `using=`" coding standard into a check. `tests/architecture/test_database_alias.py` scans all root packages and fails on:
- `transaction.atomic(...)` / `atomic(...)` **without a `using=` keyword**, and the bare decorator `@transaction.atomic` / `@atomic`
- `transaction.on_commit(...)` without `using=`: it also defaults to personal
- `.using("<string literal>")` and `connections["<string literal>"]`: use `PERSONAL` / `CATALOG` from `shared.db`
- **a string literal or `None` as the `using=` keyword** of any call (`atomic(using="personal")`, `on_commit(fn, using="catalog")`, `using=None`) *(review 6)*
- `from django.db import connection`: the singular `connection` is always `default`

`config/databases.py` builds the aliases from `SCHEMA_FOR_ALIAS` and uses none of these, so the clean tree passes.

**Known limitation**, listed in coding-standards *(review, minor)*: the scanner works on syntax, so it misses `django.db.connection` reached through `import django.db`, aliasing (`from django.db import transaction as tx` is caught; `t = transaction; t.atomic()` is not), and calls built dynamically. Code review covers those.

### 5. `eventpulse.E005`: project models use `UUIDv7Model`

In `config/checks.py`, the same pattern as E001–E004 (a pure function plus a wrapper, tagged `models`):
- **Scope** *(review 5)*: every concrete model whose module's top-level package is one of **our root packages** (`apps`, `adapters`, `worker`, `shared`, `config`, `ports`, `domain`), not just `apps.`.
- **It must subclass `shared.models.UUIDv7Model`.**
- **Auto-created M2M through tables are skipped**, as in E003. `identity.User`'s `groups` / `user_permissions` through models live in `apps.identity.models` and use integer ids.
- Django's models and the test probes are out of scope (their modules aren't ours). `identity.User` already passes.

**Where the AD-8 cost-row model goes** (coding-standards note, so the gateway item doesn't stall) *(review 5)*: AD-8 says the gateway writes "a per-call cost row in the same transaction as the result".
- Under `apps | adapters`, the gateway can't import an app's models. So the model lives in **`adapters/llm/models.py`**, with `adapters.llm` registered as a Django app.
- It must pass every check: routed in `DATABASE_ROUTING` (E001; `catalog`, beside the ingestion results it accounts for), a retention category (E003; `NOT_USER_DATA`, with no user id stored), and `UUIDv7Model` (E005, which now sees it).
- The caller's command opens `atomic(using=CATALOG)`, and the gateway writes the row inside it.
- The FR-29 dashboard (`editorial`) reads costs **through a port query**, not by importing `adapters.llm.models`, which `apps | adapters` forbids.
- This is an adapter writing to the database, which AD-5 normally forbids. AD-8's explicit rule is the named exception.

### 6. Make and docs

- `make lint-imports` runs `uv run --directory backend lint-imports`.
- `make lint-backend` runs ruff, **then `lint-imports`**, so one command covers all static rules (and CI calls one target).
- README / setup docs gain one line. `tech-stack.md` gets `import-linter 2.15`. The CI gates in `testing-standards.md` already list `lint-imports`.
- coding-standards: the rules are marked as enforced, with where each lives; the user-type note.

## Proving enforcement (planted violations)

`tests/architecture/test_import_contracts.py`:
- **Clean tree:** `lint-imports` exits 0 on the real tree.
- **Planted:** a fixture copies the root packages and `pyproject.toml` into `tmp_path`, plants violating modules, and runs `lint-imports --no-cache` there. **`PYTHONPATH` is replaced with `tmp_path`, not prepended**, so an inherited path containing `backend/` can't shadow the copy *(review, minor)*. Each case asserts the exit code and that **the set of broken contracts equals exactly the expected set** *(review 7)*, so a planted import that broke two contracts, or a mutation that "passes" for the wrong reason, is caught. **The real tree is never modified.** One case per contract:

| Planted module | Expected broken contract |
|---|---|
| `domain/_planted.py`: `import django` | domain is pure |
| `domain/_planted.py`: `from shared import retention` | domain is pure |
| `ports/_planted.py`: `import apps.catalog` | layers |
| `shared/_planted.py`: `import config.env` | layers |
| `apps/catalog/_planted.py`: `import adapters.email` | layers (`apps \| adapters`) |
| `apps/catalog/_planted.py`: `import apps.ingestion.models` | no cross-app models (ingestion) |
| `adapters/email/_planted.py`: `import adapters.llm` | adapters independent |
| `apps/catalog/_planted.py`: `import anthropic` | LLM SDKs |
| `apps/delivery/_planted.py`: `import stripe` | Stripe SDK |
| `adapters/email/_planted.py`: `import apps.identity` *(review, minor)* | layers |
| `domain/_planted.py`: `import ports` *(review, minor)* | layers (only: "domain is pure" covers external packages and `shared`; the layers contract owns internal direction) |
| `config/_planted.py`: `import worker` *(review 3)* | layers (`config \| worker`) |
| `worker/_planted.py`: `import config.api` *(review 3)* | layers (`config \| worker`) |
| `worker/_planted.py`: `import apps.catalog.api` *(review 3)* | worker doesn't import the API surface |

The **allowed** controls (exit 0, nothing broken):
- `domain` → `shared.constants` passes
- `apps.ingestion` → its own models passes
- **`apps.catalog` → `apps.ingestion.services` → `apps.ingestion.models`** passes *(review 2)*
- `adapters.llm` → `anthropic` passes
- **`worker/_planted.py`: `import adapters.llm`, where `adapters/llm/_planted.py` imports `anthropic`**, passes *(review 1)*
- **`config/_planted.py`: `import adapters.llm`**, the same chain, passes

The other three rules get their own planted cases:
- **Stdlib-only:** the AST checker runs on a temp `domain` file importing `requests`, and on a relative import that escapes `domain`. Both fail; `from domain import x`, `import datetime` and `from shared.constants import …` pass.
- **`os.environ`:** `ruff check --stdin-filename <path> -` with the project config:
  - `os.environ["X"]`, `os.getenv("X")` and `from os import environ` under `apps/x.py` → `TID251`
  - the same under `config/x.py`, `manage.py` and `tests/x.py` → clean
- **Database alias:** the scanner on source snippets. Each forbidden form is reported, including `atomic(using="personal")`, `on_commit(fn, using="catalog")` and `atomic(using=None)` *(review 6)*. `atomic(using=CATALOG)`, `.using(PERSONAL)` and `connections[CATALOG]` are clean.

`tests/config/test_checks.py` (+4): E005 for a model under `apps.*` **and one under `adapters.*`** without the base; none once it subclasses `UUIDv7Model`; auto-created through tables skipped; Django and test models ignored.

**Mutation checks** (each reverted after):
- drop the layers contract
- drop one `protected` contract
- set `allow_indirect_imports` back to false on the AD-8 contract (the `worker → adapters.llm → anthropic` control must fail)
- make `config | worker` dependent again (`config : worker`)
- remove `django` from the domain forbidden list
- loosen the stdlib allowlist
- remove the `os.environ` banned-api entry
- the scanner ignores `on_commit`
- E005 disabled

## Files to Create

| File | Purpose |
|------|---------|
| `backend/tests/architecture/__init__.py` | Package |
| `backend/tests/architecture/test_import_contracts.py` | Clean run, planted violations, root-package coverage |
| `backend/tests/architecture/test_stdlib_only.py` | AST allowlist for `domain` (+ `shared.constants`, `shared.ids`) |
| `backend/tests/architecture/test_env_access.py` | Ruff `TID251` via stdin |
| `backend/tests/architecture/test_database_alias.py` | Alias scanner + real-tree run |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/pyproject.toml`, `backend/uv.lock` | `import-linter==2.15` (dev); `[tool.importlinter]` contracts; Ruff `TID` + banned-api + per-file ignores |
| `backend/config/checks.py` | E005 |
| `backend/tests/config/test_checks.py` | E005 tests |
| `Makefile` | `lint-imports`; `lint-backend` runs it |
| `README.md`, `docs/setup/{ubuntu,macos}.md` | `make lint-imports` |
| `.specs-fire/standards/{tech-stack,coding-standards}.md` | Dependency; rules marked as enforced, with the tool for each; user-type note; **AD-2 wording for `shared.constants` / `shared.ids`**; ports-may-import-shared loosening; AD-8 cost-row placement; scanner limitations |
| `.specs-fire/intents/project-scaffold/work-items/ports-fakes-and-worker.md` | Celery app in `config/celery.py`; tasks referenced by string (no `config → worker` import) |
| `.specs-fire/intents/project-scaffold/work-items/ci-pipeline.md` | `make lint-backend` now includes `lint-imports` |

## Not in this item

- **Frontend rules** (only `lib/api/` may call the backend, AD-19) belong to `frontend-skeleton`.
- **Retention-category review in migrations** (spine Migrations convention): E003/E004 already enforce it.
