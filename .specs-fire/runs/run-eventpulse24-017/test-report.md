---
run: run-eventpulse24-017
work_item: public-catalog-read-api
intent: event-catalog-ingestion
generated: 2026-10-28
status: passed
---

# Test Report: Public Catalog Read API

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Endpoint tests: `tests/api/test_catalog_api.py` | 21 new | 0 | 0 | `apps/catalog/api.py` + `schemas.py` 100% |
| Read interface: `tests/api/test_catalog_read_service.py` | 20 new | 0 | 0 | `catalog_read.py` 100% |
| Mutation probes: `tests/api/mutation_probe_catalog.py` | 9 probes, 9 caught | 0 | 0 | — |
| **Total suite** | **1649** (1608 before + 41 new) | 0 | 0 | **98.95%** overall · 100% `domain/` |

**Gates:**
- `ruff check .`: clean. `ruff format --check .`: 240 files already formatted.
- `lint-imports`: 13 contracts kept, 0 broken.
- `manage.py check`: no issues (0 silenced).
- `makemigrations --check --dry-run`: no changes detected — no migration was needed.
- `pytest --cov`: 98.95% overall (gate 80%); `domain/` 100% (gate 100%).
- `make client` → `git diff --exit-code frontend/lib/api/`: clean, the committed client matches the live API.
- `frontend`: `pnpm lint` and `pnpm typecheck` clean.
- `tests/architecture/`: 257 passed, including the `models-ingestion` and no-direct-writes scans.

## Mutation probes

Each bug below was applied to the real implementation, the catalog tests were run, and the code was restored. A probe that passes the suite means the tests don't prove that rule.

| # | Planted bug | Result |
|---|-------------|--------|
| 1 | The `publication_status` filter is dropped (an `in_review` event leaks into the list) | caught — 1 failed, 9 passed |
| 2 | The superseded exclusion is dropped | caught — 1 failed, 10 passed |
| 3 | The upcoming filter is dropped (an event that already started leaks in) | caught — 1 failed, 12 passed |
| 4 | The `id` tiebreak is dropped (the order is no longer total) | caught — 1 failed, 3 passed |
| 5 | The city filter is dropped | caught — 1 failed, 29 passed |
| 6 | The date-range filter is dropped | caught — 1 failed, 32 passed |
| 7 | The page size is not applied (pagination returns everything) | caught — 1 failed, 4 passed |
| 8 | A missing event raises a plain `Exception` instead of the domain error (no 404) | caught — 1 failed, 14 passed |
| 9 | The query parameters are read from the body instead of the query string | caught — 1 failed, 3 passed |

**All 9 probes were caught by the suite.**

## Acceptance Criteria Validation

- ✅ **A published read interface for upcoming published events and for one event by id.**
  `apps/ingestion/services/catalog_read.py` publishes `list_public_events(...)` and
  `get_public_event(event_id=...)`. The list never returns an `in_review` event (the
  `publication_status` filter) and never returns a superseded event (the `status` exclusion).
  Rejected candidates never become Events at all, so they cannot appear.
  - **Deviation D1:** the interface hands over a frozen dataclass `PublicEvent`, not a model
    instance. The plan proposed model instances. The dataclass is strictly stronger: the
    caller never holds a reference to `apps.ingestion.models`, so the wall holds without
    either side knowing the other's models.
- ✅ **`catalog` does not import `apps.ingestion.models`; contract `models-ingestion` passes.**
  `apps/catalog/api.py` and `apps/catalog/schemas.py` import only
  `apps.ingestion.services.catalog_read`. `lint-imports` reports 13 contracts kept, 0 broken,
  and `tests/architecture/test_import_contracts.py` passes.
- ✅ **`GET /api/catalog/events` is a paginated list of upcoming published events with optional
  `city` and date-range filters.**
  Filters are `city`, `starts_after`, `starts_before` (both inclusive), plus `page` and
  `page_size`. The envelope is `{items, page, page_size, total, has_next}`.
- ✅ **`GET /api/catalog/events/{id}` returns one event, or a `NotFoundError` through the shared
  error handler.**
  `get_public_event` raises `EventNotFoundError(NotFoundError)`; `config/errors.py` maps it to
  404 with the shared `{code, message}` body. The endpoint declares `response={404: ErrorOut}`,
  so the shape is in the OpenAPI schema.
  - **Note:** the AC writes `{id}`; the route uses `{event_id}` (a UUID). The response also
    carries `slug`, so the later public page route (`/events/{slug}`) is buildable without a
    second lookup.
- ✅ **Both endpoints work with no session or cookie, and they set no session (AD-12).**
  The endpoints never touch `request.session`. The tests assert `Set-Cookie` is absent from
  both responses — the real proof, since `SessionMiddleware` only writes a cookie when the
  session is modified. An anonymous request succeeds with a 200.
- ✅ **Response schema.**
  `id`, `slug`, `title`, `canonical_url`, `start_time_utc`, `start_time_tz`, `end_time_utc`,
  `venue_name`, `venue_city`, `status`, `event_version`, `source_name`, `tz_review_pending`.
  Times are UTC plus an explicit IANA tz; display conversion is left to the frontend (AD-6).
  - **Deviation D2:** the response carries `slug` and `tz_review_pending` beyond the AC's
    minimum list. `slug` keeps the page route possible; `tz_review_pending` is the flag the
    AC asks to be visible on a `tz_review_pending` event.
- ✅ **No raw source payload is exposed (AD-9).**
  The Event's stripped `description` and `ExtractedRecord.payload` never appear. The tests
  assert the exact field set and that no source text appears anywhere in the body.
- ✅ **The OpenAPI schema is regenerated and `frontend/lib/api/` is regenerated; the CI contract
  check passes.**
  `make client` reproduces `frontend/lib/api/openapi.json` and `frontend/lib/api/schema.ts`
  byte-for-byte (`git diff --exit-code` clean). `tests/api/test_contract.py` compares the
  committed schema with the live API and passes.
- ✅ **Tests: list ordering and pagination.** Ordering is `start_time_utc` ascending, then `id`
  ascending — the UUIDv7 tiebreak makes the order total, so two events sharing a start time
  can't fall on both pages. The tests assert the order, the `total`/`has_next` envelope, and
  that pages neither repeat nor skip.
- ✅ **Tests: filters.** `city` (exact, case-insensitive), `starts_after`, `starts_before`
  (inclusive), a city that matches nothing, an event without a venue, and a case-insensitive
  city match.
- ✅ **Tests: `in_review` and superseded excluded; a `tz_review_pending` event included with the
  flag.** All four cases are covered at both the service and the endpoint layer. A
  `tz_review_pending` event is `publication_status = published`, so it is listed and carries
  `tz_review_pending: true`.
- ✅ **Tests: 404 shape.** `{code: "not_found", message: "We couldn't find that event."}`,
  validated against `shared.errors.ErrorOut`.
- ✅ **Tests: an anonymous request succeeds.** A plain `Client()` with no sign-in gets a 200.
- ✅ **Tests: no `Set-Cookie` session header.** Asserted on both endpoints, and on the 404.

## Notes

- **The list endpoint's exclusions are exactly the two the AC names.** `in_review` and
  `superseded` are excluded. `cancelled` and `postponed` events **are** listed, carrying their
  `status` — a cancelled event is still a public fact, and a `status` field that can only ever
  be `scheduled` would not be worth carrying. This follows the AC's wording; it is recorded
  here because it is the one place the reading could differ.
- **The pagination clamps are defence in depth.** The service clamps `page` to `>= 1` and
  `page_size` to `[1, 100]`, while the endpoint echoes the *unclamped* `filters.page` and
  `filters.page_size` and computes `has_next` from them. Through HTTP this is unreachable:
  `EventPage` declares `ge=1` / `le=100`, so an out-of-range value is rejected with a 422
  before the endpoint runs (verified directly). The inconsistency is latent, not live — it
  would only surface for a future direct caller of the service. Recorded as a review
  suggestion rather than a fix, so the change stays minimal.
- **The `worker-not-api` import contract was tightened, not weakened.** `config.api` was added
  to `forbidden_modules`, because `config.api` assembles the app routers and so reaches
  `apps.*.api` transitively. The planted-violation test was updated to expect **two** broken
  contracts (`layers` and `worker-not-api`) for `import config.api` instead of one.
- **No migration.** The models did not change.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-017*
