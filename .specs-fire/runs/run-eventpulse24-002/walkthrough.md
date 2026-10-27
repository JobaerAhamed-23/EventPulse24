---
run: run-eventpulse24-002
work_item: backend-skeleton
intent: project-scaffold
generated: 2026-10-27
mode: confirm
---

# Implementation Walkthrough: Backend Skeleton (Django + Ninja, layered tree)

## Summary

`backend/` is now a uv-managed Python 3.13 project with the architecture spine's layered tree, the six MVP modules as registered Django apps, typed fail-fast configuration, and Django Ninja serving its OpenAPI contract at `/api/`. Ruff and pytest are configured; 21 tests cover config, project wiring, the API mount, and a Django-free guard for `domain`. The plan went through a 14-point review (revision 2) before execution, and every point is implemented and tested.

## Structure Overview

`backend/` is the import root. `config/` is the Django project. Its `env.py` is the single point where the environment is read, and `settings.py` derives everything from it. The six apps sit under `apps/` with identical shapes (models, services, api router, schemas, admin, migrations). The layer packages (`domain`, `ports`, `adapters/*`, `shared`, `worker`) exist empty, with docstrings stating their rule. Make targets run every backend command from the repo root through `uv run --directory backend`.

## Architecture

### Pattern Used

Modular monolith with ports and adapters (spine "Design Paradigm"). Layers point inward; only the API surface exists so far.

### Layer Structure

```text
config (settings · urls · api)  ──►  apps/<module> (models · services · api · schemas · admin)
                                        │
                                        ├──► ports ──► domain (stdlib only)
adapters/<tech> ──► ports ──────────────┘
.env ──► config/env.py (pydantic-settings) ──► config/settings.py   [only env reader]
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/pyproject.toml`, `backend/uv.lock` | uv project, pins, ruff + pytest config |
| `backend/manage.py` | Django entry point |
| `backend/config/env.py` | Typed settings, `.env` located from file path, comma-list hosts |
| `backend/config/settings.py` | Django settings, UTC, placeholder DB, admin installed |
| `backend/config/api.py`, `urls.py`, `asgi.py`, `wsgi.py` | Ninja API at `/api/`, entry points |
| `backend/apps/<6 modules>/…` | AppConfig + empty models/services/api/schemas/admin/migrations |
| `backend/{domain,ports,shared,worker,adapters/*}/__init__.py` | Layer packages |
| `backend/tests/**` | 21 tests (domain guard, config, project wiring, API) |

### Modified

| File | Changes |
|------|---------|
| `.env.example` | Django keys; `$`/`#` warning |
| `scripts/doctor.sh` | Config check (`.env` vs `.env.example` keys) |
| `Makefile` | `api`, `manage`, `test-backend`, `lint-backend`, `fmt-backend`; help width |
| `README.md`, `docs/setup/{ubuntu,macos}.md` | Backend commands; "Updating an existing `.env`" |
| `.specs-fire/standards/tech-stack.md`, work item | Version bumps, new deps, no `.python-version` |

## Key Implementation Details

### 1. One reader of the environment

`config/env.py` builds `env = Settings()` once. The `.env` path is `Path(__file__).resolve().parents[2] / ".env"`, so it loads the same file from any working directory (verified with `env -i` from a foreign directory). `DJANGO_SECRET_KEY` has no default: a missing key stops startup.

### 2. Comma-separated hosts

`Annotated[list[str], NoDecode]` stops pydantic-settings from JSON-decoding the value, and a `mode="before"` validator splits on commas and drops blanks.

### 3. Domain purity is checked in a fresh interpreter

The guard imports every `domain` module in a subprocess and fails if any `django` module was loaded. A second test prepends `import django` to the same check and expects failure, proving the guard works.

### 4. Admin installed, not routed

The contrib apps are present (Django admin is the MVP surface for FR-29/FR-57), but `/admin/` returns 404 until `schema-router-spike` decides where Django's own tables live.

## Security Considerations

| Concern | Approach |
|---------|----------|
| Secret key | Required, no code default; local value in `.env.example` marked local-only |
| Debug | Defaults to `False` in code; only `.env` enables it |
| Hosts | `ALLOWED_HOSTS` from env; local default `127.0.0.1,localhost` |
| Dev server | `make api` binds `127.0.0.1` only |
| Admin | Not routed yet |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Django / Ninja versions | 6.1.2 / 1.7.1 | Latest patches of the spine's minor lines |
| Python selection | `requires-python` only, no `.python-version` | pyenv reads `.python-version` and broke the pyenv-installed `uv` shim |
| Admin | Installed, not routed | Table placement belongs to the AD-3 spike |
| Domain guard | Fresh subprocess + negative test | Can't be masked by Django already being loaded |
| Stale `.env` | doctor Config check | Catches missing keys on both machines going forward |
| `.env` parsing | `dj-database-url` | Well-known, tiny; turns the URLs into Django `DATABASES` dicts |

## Deviations from Plan

- **`backend/.python-version` not created.** On this machine `uv` is a pyenv shim (installed under pyenv's Python 3.12.3). pyenv also reads `.python-version`, so a `3.13` file inside `backend/` made the shim fail. `requires-python = "==3.13.*"` already makes uv select 3.13, so the file was dropped. Recorded in tech-stack.md and run.md Decisions.
- **Ruff per-file ignores for tests** also include `S105`/`S106` (fake secrets in fixtures), not only `S101`/`S603`.

## Dependencies Added

| Package | Why Needed |
|---------|------------|
| `django==6.1.2` | Web framework, ORM, admin |
| `django-ninja==1.7.1` | Typed API + OpenAPI |
| `pydantic==2.13.5` | Schemas |
| `pydantic-settings==2.16.1` | Typed env config (`NoDecode`) |
| `psycopg[binary]==3.3.6` | PostgreSQL driver |
| `dj-database-url==3.1.2` | Parse `DATABASE_URL_*` |
| `pytest==9.1.1`, `pytest-django==4.14.0`, `ruff==0.17.3` (dev) | Tests, lint, format |

## How to Verify

1. **Tests and lint**
   ```bash
   make test-backend && make lint-backend
   ```
   Expected: `21 passed`, `All checks passed!`, files already formatted

2. **Django system check**
   ```bash
   make manage ARGS="check"
   ```
   Expected: `System check identified no issues`

3. **Run the API**
   ```bash
   make api   # then open http://127.0.0.1:8000/api/docs
   ```
   Expected: Swagger UI titled "EventPulse24 API 0.1.0" (no endpoints yet)

4. **Config drift check**
   ```bash
   make doctor
   ```
   Expected: `[ ok ] .env has every key from .env.example`

## Test Coverage

- Tests added: 21
- Coverage: not measured yet (added by `ci-pipeline`; `domain/` is empty)
- Status: passing

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated (if applicable)
- [x] Developer notes captured

## Developer Notes

- **On the Mac:** after pulling, `make doctor` will report the three new `DJANGO_*` keys missing from its `.env`. Copy them from `.env.example`.
- **pyenv users:** don't add a `.python-version` to `backend/`. uv picks 3.13 from `pyproject.toml`. Installing uv standalone (`curl … | sh` or `brew install uv`) avoids the shim issue entirely.
- **For `architecture-contracts`:** the Ruff `os.environ` ban must exempt `manage.py` (Django bootstrap `setdefault`).
- **For `ci-pipeline`:** importing `config.env` requires `DJANGO_SECRET_KEY` and the `DATABASE_URL_*`/`REDIS_URL` values. Provide test values in the workflow.
- **FIRE tooling:** `update-checkpoint.cjs` / `update-phase.cjs` update `state.yaml` only; `run.md` frontmatter was synced by hand at each change.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-002*
