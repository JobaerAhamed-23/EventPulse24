# Tech Stack

## Overview

EventPulse24 is an AI-powered event discovery and notification platform. The backend is a Django modular monolith that runs as two Python runtimes from one repository: an **API runtime** (Django Ninja) and a **worker runtime** (Celery worker + beat). It is served to a separate **Next.js frontend**, which is a client of the generated OpenAPI contract and shares no domain code with the backend.

Versions were verified as current on 2026-09-04 (Architecture Spine §Stack). Once the code exists, the lockfiles own them.

## Core Technologies

### Language

**Primary**: Python (backend), TypeScript (frontend)
**Version**: Python **3.13 pinned** (the only version that both Django 6.1 and Celery 5.6.3 declare), TypeScript 5.x

### Framework

**Framework**: Django + Django Ninja (backend), Next.js App Router (frontend)
**Version**: Django 6.1.2, Django Ninja 1.7.1, Next.js 16.3.8 (Active LTS). Django and Ninja are patch bumps over the spine's 6.1.1 / 1.7.0, taken at scaffold time (run-eventpulse24-002)
**Rationale**: Django models are the entities and Django admin is the MVP editorial and AI-cost surface (AD-2, AD-14). Ninja generates the OpenAPI contract from Pydantic schemas (AD-19). Next 16 `cacheComponents` and `partialPrefetching` make ISR'd public event pages viable at scale (AD-12).

### Runtime

**Runtime**: CPython (API + worker), Node.js (frontend build/SSR)
**Version**: Python 3.13, **Node.js 24 LTS (≥24.15)**. Node 20 is end of life (April 2026), and Vitest 5 / jsdom 30 need it (user decision, run-eventpulse24-007). Enforced by `engineStrict` in `frontend/pnpm-workspace.yaml`, `make doctor`, and `.nvmrc`.

## Data Layer

### Database

**Type**: Relational + vector
**Database**: PostgreSQL on Neon, with pgvector
**Version**: PostgreSQL 18, pgvector 0.8.6 (above the 0.8.4 HNSW vacuum-corruption fix)

Two schemas: `catalog` (public events) and `personal` (user data). They are exposed as **two Django `DATABASES` entries** behind a router, with no cross-schema FKs, joins or transactions (AD-3).

### ORM / Data Access

**Tool**: Django ORM + `pgvector` Django integration
**Rationale**: One entity representation (the model). Vector similarity is raw SQL in any stack, so no second ORM is used.

### Caching

**Solution**: Redis (managed) as the Celery broker. It carries **only** the periodic tick and the pipeline jobs, **never** the reminder schedule (AD-7). LLM prompt caching lives in the gateway (AD-8). Public pages are cached by Vercel ISR.

## API Layer

### API Style

**Style**: REST via Django Ninja. Typed Pydantic request/response schemas in `apps/*/schemas.py`. Error shape is `{ code, message, details? }`.

### Documentation

**Tool**: Django Ninja's OpenAPI schema is the single source of truth. The frontend TS client in `frontend/lib/api/` is generated from it in CI and never hand-edited (AD-19).

## Frontend

### UI Framework

**Framework**: Next.js (App Router) + React
**Version**: Next.js 16.3.8, React 19.2.9 (16.4 / 19.3 exist; staying on the spine's 16.3 / 19.2 lines)

### Styling

**Approach**: Tailwind CSS 4.x over a CSS-custom-property design token layer (`frontend/styles/`). **No component library** (no Material, no shadcn). Use vanilla components, `<dialog>` for modals and sheets, and a hand-rolled tooltip. Dark theme is the default via `data-theme="dark"` on `<html>`, with no `prefers-color-scheme` auto-switch. There is one 240ms opacity transition and no animation library.

### State Management

**Solution**: Server components + the generated API client. No global client state library is adopted at MVP.

## Infrastructure

### Hosting

**Platform**:
- Frontend: Vercel. Hobby while building, **Pro mandatory before Stripe checkout is enabled** (hard launch gate).
- API runtime: an always-on Python host (e.g. Railway Hobby, ~$5/mo).
- Worker runtime: Celery worker + **exactly one** beat process. Run locally in Phase 0, as an always-on process in Phase 1.
- Database: Neon PG18 (free tier in Phase 0). Neon PITR gives RPO <1h and RTO <4h.
- Email: Resend or Postmark, with two streams (transactional and bulk) and RFC 8058 one-click unsubscribe (AD-20).
- Billing: Stripe Checkout + Customer Portal.
- Environments: `local` → `preview` (per-PR Neon branch) → `production`.

### Containerization

Not configured. To be decided at first scaffold.

### CI/CD

**Platform**: GitHub Actions

## External AI Services

- **Anthropic** (`anthropic` 1.3.0, `instructor` 1.16.0): `claude-haiku-4-5` primary, `claude-sonnet-5` fallback, same SDK and gateway (AD-8)
- **Voyage AI** (`voyageai`, pin at build time): `voyage-4-lite` embeddings, quantized (int8/binary) and Matryoshka-truncated to 512 or 256 dims
- All model calls go through `backend/adapters/llm/` only. Every call writes a cost row.

## Development Tools

### Package Manager

**Manager**: `uv` (backend) · `pnpm` (frontend). Python 3.13 is selected by `requires-python`, not a `.python-version` file (that file breaks pyenv-installed `uv` shims).

### Build Tool

**Tool**: Next.js build (frontend). No build step for the backend.

### Linting

**Linter**: Ruff + `import-linter` (backend, where `import-linter` enforces AD-2) · ESLint with `eslint-config-next` (frontend)
**Config**: `pyproject.toml` / `.importlinter` · `eslint.config.mjs`

### Formatting

**Formatter**: Ruff format (backend) · Prettier (frontend)
**Config**: `pyproject.toml` · `.prettierrc`

## Dependencies

### Production Dependencies

- `django` (6.1.2): web framework, ORM, admin
- `django-ninja` (1.7.1): typed API + OpenAPI generation
- `pydantic` (2.13.5): schemas, extraction models
- `pydantic-settings` (2.16.1): typed startup config
- `psycopg[binary]` (3.3.6): PostgreSQL driver
- `dj-database-url` (3.1.2): parses `DATABASE_URL_*` into Django `DATABASES`
- `celery[redis]` (5.6.3): worker + beat (static `beat_schedule`, **no** `django-celery-beat`). Locally the worker runs `--pool solo`: the prefork pool breaks on macOS under Celery 5.6.3 (run-eventpulse24-006)
- `redis` (6.4.0): broker client. kombu 5.6.2 caps it below 6.5, so "current" (8.x) isn't installable.
- `pgvector` (0.5.0): vector fields
- `anthropic` (1.3.0): Claude SDK, used via the gateway only
- `instructor` (1.16.0): structured extraction
- `voyageai` (verify before pinning): embeddings
- `stripe` (verify before pinning): billing
- `next` (16.3.8), `react` / `react-dom` (19.2.9), `tailwindcss` + `@tailwindcss/postcss` (4.3.3): frontend

### Development Dependencies

- `pytest`, `pytest-django`: backend tests
- `factory-boy` 3.3.3 (pulls in `faker`): per-app test factories; catalog factories subclass `tests/ingestion/factories.py::CatalogFactory` (run-eventpulse24-010)
- `import-linter` 2.15: AD-1/AD-2/AD-8 import contracts (`[tool.importlinter]` in `backend/pyproject.toml`, `make lint-imports`)
- `ruff`: lint + format
- `mypy` (proposed): type checking
- `vitest` (5.0.5) + `jsdom` (30.1) + `@vitejs/plugin-react` (6.1.2), `@testing-library/react` (16.3.3) / `dom` / `jest-dom`: frontend unit tests
- `typescript` (5.9.3; TS 7 exists, not adopted), `eslint` (9.39) + `eslint-config-next` (16.3.8) + `typescript-eslint` (8.72, one copy only) + `eslint-config-prettier`, `prettier` (3.9): frontend tooling. **ESLint 9 is marked "no longer supported" by npm**, but `eslint-plugin-react` / `jsx-a11y` / `import` (via `eslint-config-next`) declare ESLint ≤9. Move to 10 when `eslint-config-next` does.
- `@playwright/test` + `@axe-core/playwright`: E2E + accessibility gate
- `openapi-typescript` (7.13.0): generates `frontend/lib/api/schema.ts` from the committed `openapi.json` (`make client`)
- `openapi-fetch` (0.17.0, runtime): typed `fetch` over the generated `paths`, used only in `lib/backend-client.ts`
- `concurrently` (10.0.6): runs the four app processes for `make dev`

## Version Requirements

| Tool | Minimum Version | Recommended |
|------|-----------------|-------------|
| Python | 3.13 | 3.13 (pinned) |
| Node.js | 24.15 | 24 LTS |
| PostgreSQL | 18 | 18 (Neon) |
| pgvector | 0.8.4 | 0.8.6 |
| Django | 6.1 | 6.1.2 |
| Next.js | 16 | 16.3.4 |

---
*Generated by specs.md - fabriqa.ai FIRE Flow*
