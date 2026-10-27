---
id: ci-pipeline
title: CI Pipeline (GitHub Actions)
intent: project-scaffold
complexity: medium
mode: confirm
status: pending
depends_on: [architecture-contracts, health-round-trip]
created: 2026-10-27
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

## Dependencies

- architecture-contracts
- health-round-trip
