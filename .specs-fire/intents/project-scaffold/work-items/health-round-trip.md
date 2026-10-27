---
id: health-round-trip
title: Health Round-Trip & make dev
intent: project-scaffold
complexity: medium
mode: confirm
status: pending
depends_on: [schema-router-spike, shared-foundations, ports-fakes-and-worker, frontend-skeleton]
created: 2026-10-27
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

## Dependencies

- schema-router-spike
- shared-foundations
- ports-fakes-and-worker
- frontend-skeleton
