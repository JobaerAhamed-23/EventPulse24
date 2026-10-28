---
id: ci-pipeline
title: CI Pipeline (GitHub Actions)
intent: project-scaffold
complexity: medium
mode: confirm
status: completed
depends_on:
  - architecture-contracts
  - health-round-trip
created: 2026-10-27
run_id: run-eventpulse24-009
completed_at: 2026-10-28T04:32:34.607Z
---

# Work Item: CI Pipeline (GitHub Actions)

## Description

Run every quality gate on each push and pull request in GitHub Actions.

## Acceptance Criteria

- [ ] Workflow `.github/workflows/ci.yml` triggers on push and pull_request
- [ ] Backend job: services `pgvector/pgvector:pg18` (with the same init script) and Redis; uv with Python 3.13; runs `ruff check`, `ruff format --check`, `lint-imports`, `manage.py check`, `makemigrations --check`, `pytest --cov` with a `fail_under` gate (100% for `domain/`)
- [ ] Contract job: export OpenAPI, regenerate the TS client, fail if `git diff` shows changes (AD-19)
- [ ] Frontend job: pnpm install (cached), `lint`, `typecheck`, `test`
- [ ] Dependency caching for uv and pnpm
- [ ] Verified: workflow is green on a PR; a deliberately broken contract makes it red

## Technical Notes

- axe-core / Playwright gates arrive with the first real surfaces, not in this intent.
- **From schema-router-spike:**
  - GitHub Actions service containers can't mount `docker/postgres/init/` as `docker-entrypoint-initdb.d`. CI must run `docker/postgres/init/01-schemas-and-roles.sh` explicitly against the service (psql with `PGHOST`/`PGPORT`, `POSTGRES_USER`, `POSTGRES_DB`, `EP_*_PASSWORD`) to get the schemas, roles, test template DB and `ep_owner CREATEDB`.
  - `makemigrations --check` needs a live database (it runs the migration-history consistency check), so it needs the service and env values too.
- **From backend-skeleton:** importing `config.env` requires `DJANGO_SECRET_KEY`, `DATABASE_URL_CATALOG`, `DATABASE_URL_PERSONAL`, `DATABASE_URL_OWNER` (tests run as owner) and `REDIS_URL`; set test values in the workflow `env:`.
- **From architecture-contracts:** `make lint-backend` runs `ruff check`, `ruff format --check` and `lint-imports` CI can call that one target. `tests/architecture/` runs inside `pytest`: it shells out to `lint-imports` and `ruff`, both in the uv dev group.
- **From frontend-skeleton:**
  - Node from `.nvmrc` (`actions/setup-node` with `node-version-file: .nvmrc`; must be ≥24.15 or `pnpm install` stops on `engineStrict`)
  - pnpm via corepack, at `frontend/package.json` `packageManager` (`pnpm@12.15.0`); cache the pnpm store
  - `make web-install`, `make lint-web` (ESLint + typecheck incl. `next typegen` + Prettier check), `make test-web`, and `pnpm --dir frontend build`
  - the build downloads Google fonts (`next/font`), so it needs network
  - `frontend/styles/tokens.test.ts` reads `_bmad-output/.../DESIGN.md`, so a full checkout is needed
- **From health-round-trip:**
  - Contract job: `make client` (needs the backend env, but no database: the schema export only imports Django), then `git diff --exit-code frontend/lib/api/`. `backend/tests/api/test_contract.py` covers the schema half inside `pytest` too.
  - `tests/api/test_health.py` needs the Redis service (the all-up case pings it) and both database aliases.
  - `frontend/tests/lint-rules.test.ts` runs ESLint through its Node API inside Vitest (about 1 s).

## Dependencies

- architecture-contracts
- health-round-trip
