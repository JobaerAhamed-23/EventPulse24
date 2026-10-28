---
run: run-eventpulse24-002
work_item: backend-skeleton
intent: project-scaffold
mode: confirm
checkpoint: plan
approved_at: 2026-10-27
revision: 2 (plan review: 14 points applied)
---

# Implementation Plan: Backend Skeleton (Django + Ninja, layered tree)

## Approach

Create `backend/` as a **uv** project pinned to Python 3.13. `backend/` is the import root, so the spine's layers are top-level packages:

- `config` (the Django project)
- `domain`, `apps`, `ports`, `adapters`, `worker`, `shared`

The six MVP modules are registered Django apps under `apps/`, with the spine's file set and no models. Configuration is one pydantic-settings object in `config/env.py`, validated at import of `config.settings`. It reads the repo-root `.env`, **located from the file's own path**, not the working directory, and fails fast on a missing secret key or an invalid value. Django Ninja is mounted at `/api/`, with OpenAPI docs at `/api/docs`. Ruff and pytest are configured in `pyproject.toml`. Make targets run everything via `uv run --directory backend`, so `manage.py` and the pytest/ruff config resolve from `backend/`.

**Domain stays Django-free from day one.** The guard test imports every `domain` module in a **fresh Python subprocess** and asserts `django` never entered `sys.modules`. It can't be fooled by Django already being loaded in the pytest process, and the whole suite runs in one pytest invocation.

**Versions:** take the latest **patch** releases of the spine's pins, and keep the spine's minor lines. The bumps are recorded in `tech-stack.md` and the work item, and in run.md's Decisions at completion.

| Package | Spine | Used | Why |
|---|---|---|---|
| Django | 6.1.1 | **6.1.2** | Patch release (security/bug fixes) |
| django-ninja | 1.7.0 | **1.7.1** | Patch release |
| pydantic | 2.13.5 | 2.13.5 | Already the latest 2.13 patch; 2.14 is a minor bump, not taken without need |
| pydantic-settings | "current" | 2.16.1 | Current; provides `NoDecode` (needed for comma-separated lists) |
| psycopg[binary] | — | 3.3.x | Postgres driver (needed by `DATABASES`) |
| dj-database-url | — | 3.1.x | Parse the `DATABASE_URL_*` values from `.env` into Django's format |
| ruff / pytest / pytest-django (dev) | — | 0.17.x / 9.1.x / 4.14.x | Lint + format, tests |

## Files to Create

| File | Purpose |
|------|---------|
| `backend/pyproject.toml` | uv project, `requires-python = "==3.13.*"`, pinned deps + `dev` group; `[tool.ruff]` (line 100, py313, rules `E,F,I,B,UP,S,DTZ`, first-party = the 7 packages, tests may `assert`/`subprocess`); `[tool.pytest.ini_options]` (`DJANGO_SETTINGS_MODULE=config.settings`, `testpaths=tests`) |
| `backend/uv.lock` | Committed lockfile |
| `backend/.python-version` | `3.13`, so uv picks the right interpreter on both machines |
| `backend/manage.py` | Django entry point |
| `backend/config/__init__.py`, `settings.py`, `urls.py`, `asgi.py`, `wsgi.py` | Django project. Settings come only from `config/env.py`. `TIME_ZONE="UTC"`, `USE_TZ=True` (AD-6). `urls.py` mounts **only** `api/` (see Admin below) |
| `backend/config/env.py` | `Settings(BaseSettings)`, `env_file = Path(__file__).resolve().parents[2] / ".env"`, `extra="ignore"`. Fields: `django_secret_key` (required, no default), `django_debug` (default `False`), `django_allowed_hosts: Annotated[list[str], NoDecode]` with a `field_validator` that splits on commas and strips blanks, `database_url_owner/catalog/personal`, `redis_url`, `smtp_host/port`, `adapter_mode: Literal["fake","real"]`. **The only module allowed to read the environment** |
| `backend/config/api.py` | `NinjaAPI(title="EventPulse24 API", version="0.1.0")`. Docs at `/api/docs`, schema at `/api/openapi.json` (the AD-19 source of truth later) |
| `backend/apps/__init__.py` | Package marker |
| `backend/apps/{ingestion,catalog,personalization,delivery,identity,editorial}/` | Each: `__init__.py`, `apps.py` (AppConfig, label = module name), empty `models.py`, `services/__init__.py`, `api.py` (empty Ninja `Router`), `schemas.py`, `admin.py`, `migrations/__init__.py`, plus a one-line docstring stating the module's ownership from AD-16 |
| `backend/domain/__init__.py` | Docstring: pure logic, stdlib only, no Django, no entities (AD-2) |
| `backend/ports/__init__.py`, `backend/shared/__init__.py`, `backend/worker/__init__.py` | Package markers with a layer-purpose docstring |
| `backend/adapters/__init__.py` + `{llm,email,calendar,crawl,billing,logging}/__init__.py` | Adapter packages, empty |
| `backend/tests/__init__.py`, `tests/domain/test_domain_is_django_free.py` | Runs `sys.executable -c …` in a subprocess (cwd `backend/`, `DJANGO_SETTINGS_MODULE` removed from its env) that walks `domain` with `pkgutil`, imports each module, and exits non-zero if `django` is in `sys.modules`. The test asserts exit 0 and shows stderr on failure |
| `backend/tests/config/test_env.py` | Loads from explicit env values with `Settings(_env_file=None)`. Missing secret key uses `monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)` + `_env_file=None` → `ValidationError`. `DJANGO_ALLOWED_HOSTS="a, b,,c"` → `["a","b","c"]`. Invalid `adapter_mode` rejected. `DEBUG` defaults to `False`. The env file path resolves to the repo root regardless of cwd |
| `backend/tests/config/test_project.py` | All 6 apps installed with the right labels; `ninja` installed; `manage.py check` passes; `TIME_ZONE == "UTC"` and `USE_TZ`; no `admin/` URL is mounted |
| `backend/tests/api/test_openapi.py` | `GET /api/openapi.json` → 200 with title/version; `GET /api/docs` → 200 |

## Files to Modify

| File | Changes |
|------|---------|
| `.env.example` | Add `DJANGO_SECRET_KEY` (local-only value, contains no `$` or `#`), `DJANGO_DEBUG=true`, `DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost`. Extend the header comment: values must not contain `$` **or `#`** (make treats `#` as a comment) |
| `.env` (local, not committed) | Append the same three keys so this machine keeps working |
| `scripts/doctor.sh` | New **Config** section: every key in `.env.example` must exist in `.env`. Missing keys → `[FAIL]` listing them, with the hint "copy them from .env.example". This catches stale `.env` files on either machine after every future change |
| `docs/setup/ubuntu.md`, `docs/setup/macos.md` | Short "Updating an existing `.env`" note: when `make doctor` reports missing keys, copy them from `.env.example` |
| `Makefile` | Add `api` (runserver on `127.0.0.1:$API_PORT`), `manage` (`ARGS=…`), `test-backend` (`pytest`), `lint-backend` (`ruff check` + `ruff format --check`), `fmt-backend`. All use `uv run --directory backend`. Widen the `help` column from `%-10s` to `%-14s` |
| `README.md` | Add `backend/` to the repository layout table and `make api` / `make test-backend` to the quick start |
| `.specs-fire/standards/tech-stack.md` | Django 6.1.1 → 6.1.2, django-ninja 1.7.0 → 1.7.1 (with the note "patch bumps at scaffold time"); add psycopg and dj-database-url to production dependencies |
| `.specs-fire/intents/project-scaffold/work-items/backend-skeleton.md` | Acceptance criterion pins updated to Django 6.1.2 / django-ninja 1.7.1 |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/domain/test_domain_is_django_free.py` | Domain importable without Django (fresh subprocess) |
| `backend/tests/config/test_env.py` | Typed config: required key, comma-list parsing, validation, cwd-independent `.env` path |
| `backend/tests/config/test_project.py` | App registry (6 apps + ninja), timezone settings, system check, no admin URL |
| `backend/tests/api/test_openapi.py` | Ninja mounted, docs and schema served |
| `make lint-backend` | Ruff check + format check clean |
| `make doctor` | New config check: passes with the updated `.env`; a temporarily removed key → `[FAIL]` naming it |
| manual | `make api` → `/api/docs` returns 200 (curl) |

## Technical Details

- **Single placeholder database.** `DATABASES["default"]` points at `DATABASE_URL_OWNER`. The `catalog`/`personal` split, router and roles belong to `schema-router-spike`. No migrations are run in this item, and the tests don't touch the database.
- **Admin: installed, not mounted.** `django.contrib.admin`, `auth`, `contenttypes`, `sessions`, `messages` and `staticfiles` are in `INSTALLED_APPS`, because the spine makes Django admin the MVP surface for FR-29/FR-57 (AD-14). `/admin/` is **not** routed yet: its tables (auth, sessions, admin log) have no home until `schema-router-spike` decides which schema Django's own tables live in. Mounting it now would invite running migrations against the placeholder DB.
- **`ninja` in `INSTALLED_APPS`** so the docs page uses Ninja's bundled templates and static files instead of relying on a CDN.
- **Primary keys.** `DEFAULT_AUTO_FIELD` is set to `BigAutoField` only to silence Django's warning. The UUIDv7 base model arrives in `shared-foundations` and becomes the convention.
- **`worker/` is a plain package for now.** `ports-fakes-and-worker` decides whether it becomes an installed app for management commands.
- **No API routers registered yet.** The empty per-app routers exist so the pattern is visible; the first endpoint (`/api/health`) is added by `health-round-trip`.
- **Security defaults.** `DEBUG` defaults to `False` in code (only `.env` turns it on). The secret key has no code default. `ALLOWED_HOSTS` comes from env.
- **Enforcement comes later.** `import-linter` contracts and the `os.environ` ban are `architecture-contracts`. This item only follows the rules.
- **CI needs test env values.** Settings require `DJANGO_SECRET_KEY` and the `DATABASE_URL_*` values. `ci-pipeline` must supply test values (workflow `env:` or a CI `.env` copied from `.env.example`), or `config.settings` will refuse to import. Recorded here so that item picks it up.
- **FIRE tooling gap.** `update-checkpoint.cjs` updates `state.yaml` but not `run.md`'s frontmatter. `run.md` is synced by hand at each checkpoint change, so the two stay consistent.
