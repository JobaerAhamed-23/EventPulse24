---
id: health-round-trip
title: Health Round-Trip & make dev
intent: project-scaffold
complexity: medium
mode: confirm
status: completed
depends_on:
  - schema-router-spike
  - shared-foundations
  - ports-fakes-and-worker
  - frontend-skeleton
created: 2026-10-27
run_id: run-eventpulse24-008
completed_at: 2026-10-27T16:19:54.732Z
---

# Work Item: Health Round-Trip & make dev

## Description

Wire the stack end to end: a health endpoint that touches both schemas and Redis, the generated OpenAPI → TypeScript client, a Next.js page that renders it, and one command that runs everything.

## Acceptance Criteria

- [ ] `GET /api/health` (Ninja, Pydantic response schema) returns per-component status for `catalog` DB, `personal` DB and Redis, using the shared error shape on failure
- [ ] `make openapi` exports the schema to a committed file; `make client` generates the TS client into `frontend/lib/api/` (e.g. `openapi-typescript`), never hand-edited
- [ ] A Next.js page (e.g. `/dev/health`) fetches via the generated client and shows each component's status
- [ ] CORS / API base URL configured from env for local dev
- [ ] `make dev` starts API, worker, beat and Next.js together with readable, prefixed output and clean Ctrl-C shutdown, on Linux and macOS
- [ ] Tests: health endpoint returns ok with services up and a structured error when a component is down
- [ ] Verified on **both** Ubuntu and macOS: following the setup doc from a clean clone ends with the health page all green

## Technical Notes

- AD-19: the OpenAPI schema is the single source of truth for the boundary.

## Hand-offs from earlier runs

- **Worker and beat** (ports-fakes-and-worker): `make dev` runs `make worker` (`--pool solo`, the same on both OSes) and **exactly one** `make beat`. Beat's pidfile (`backend/.celery/beat.pid`) makes a second beat refuse to start, so `make dev` must not start beat if one is already running. On Ctrl-C, stop beat cleanly (SIGTERM) so it removes the pidfile.
- **Redis in the health check:** the broker URL is `settings.CELERY_BROKER_URL` (from `REDIS_URL`).

## Dependencies

- schema-router-spike
- shared-foundations
- ports-fakes-and-worker
- frontend-skeleton
