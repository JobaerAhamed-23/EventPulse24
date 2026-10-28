---
id: public-catalog-read-api
title: Public Catalog Read API
intent: event-catalog-ingestion
complexity: medium
mode: confirm
status: pending
depends_on: [catalog-data-model]
created: 2026-10-28
---

# Work Item: Public Catalog Read API

## Description

Expose ingested events through a public, session-free read endpoint in the `catalog` app. The endpoint reads through `ingestion`'s published read interface, and the generated TypeScript client is regenerated (AD-12, AD-19). This proves catalog data reaches the API contract, ready for the later browse and city-page intent.

## Acceptance Criteria

- [ ] `apps/ingestion` publishes a read interface (a service or query module) for upcoming published events and for one event by id. It never returns superseded events or events in `in_review` in the list. Rejected candidates never become Events, so they can't appear.
- [ ] The `catalog` app does not import `apps.ingestion.models`: contract `models-ingestion` still passes.
- [ ] `GET /api/catalog/events` is a paginated list of upcoming published events with optional `city` and date-range filters.
- [ ] `GET /api/catalog/events/{id}` returns one event, or a `NotFoundError` through the shared error handler.
- [ ] Both endpoints work with no session or cookie, and they set no session (AD-12).
- [ ] Response schema:
  - id, title, canonical URL
  - `start_time_utc` and `start_time_tz` (IANA)
  - end time
  - venue name and city
  - status
  - `event_version`
  - source name

  Times are UTC plus an explicit tz, and display conversion is left to the frontend (AD-6). No raw source payload is exposed (AD-9).
- [ ] The OpenAPI schema is regenerated and `frontend/lib/api/` is regenerated. The existing CI contract check (generated client matches schema) passes.
- [ ] Tests (factories, no pipeline needed):
  - list ordering and pagination
  - filters
  - `in_review` and superseded events excluded, and a `tz_review_pending` event included with that flag in the response
  - 404 shape
  - an anonymous request succeeds
  - no `Set-Cookie` session header

## Technical Notes

- **Spine references:** AD-12 (the public surface never depends on a session), AD-19 (generated contract), AD-3 (single schema, no cross-wall join), AD-2 (catalog reads via ingestion's interface).
- **Out of scope:** SEO, schema.org JSON-LD output, and any Next.js page. Those belong to the FR-26–28 intent.

## Dependencies

- catalog-data-model
