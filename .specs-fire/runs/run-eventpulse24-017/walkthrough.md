---
run: run-eventpulse24-017
work_item: public-catalog-read-api
intent: event-catalog-ingestion
generated: 2026-10-28
mode: confirm
---

# Implementation Walkthrough: Public Catalog Read API

## Summary

The ingested `catalog` is now readable through a public, session-free HTTP API. Two routes
were added — a paginated list of upcoming published events and a single-event lookup — and the
read query lives behind a published interface in the `ingestion` app, so the `catalog` app never
touches `apps.ingestion.models` and the import wall holds. The OpenAPI schema and the
generated TypeScript client were regenerated, so the frontend can consume the catalog through
the same generated contract every other endpoint uses.

## Structure Overview

The work is a three-layer slice of the existing clean-architecture spine. Nothing new was
introduced structurally: the `catalog` app already existed as the public read surface, and the
`ingestion` app already owned the catalog models. This run filled in the read path between
them.

```text
Browser / frontend client
        │
        ▼
GET /api/catalog/events          GET /api/catalog/events/{event_id}
        │                                   │
        ▼                                   ▼
apps/catalog/api.py               apps/catalog/api.py
  (routes, request → service)        (route, request → service)
        │                                   │
        │  calls the published interface    │
        └───────────────┬───────────────────┘
                        ▼
        apps/ingestion/services/catalog_read.py
          (owns the query; hands over plain data)
                        │
                        ▼
        apps/ingestion/models.Event  ──►  catalog schema
          (read via .using(CATALOG))         (select_related venue, source)
```

Two deliberate boundaries shape this:

- **The query lives in `ingestion`, the shapes live in `catalog`.** The `ingestion` app owns
  the data and the rules about what is public; the `catalog` app owns the wire contract. This
  is AD-2's rule that a cross-module call goes through the target app's published service
  interface, and AD-19's rule that the surface owns the contract.
- **The interface hands over a frozen dataclass, not a model instance.** The `catalog` app
  receives a `PublicEvent` value it can read without ever holding a reference to
  `apps.ingestion.models`. The wall holds without either side knowing the other's models —
  a stronger guarantee than "we were careful not to import it".

### Architecture

**Pattern:** Service layer with a one-way dependency, over the existing clean-architecture
spine. The `catalog` app depends on `ingestion`'s published service; `ingestion` depends on
nothing in `catalog`. There is no cycle and no shared ORM state.

```text
┌─────────────────────────────────────────┐
│  Presentation  apps/catalog/api.py       │  routes, no writes, no session
├─────────────────────────────────────────┤
│  Contract      apps/catalog/schemas.py   │  EventOut, EventListOut, EventPage
├─────────────────────────────────────────┤
│  Application   apps/ingestion/services/  │  list_public_events
│                catalog_read.py           │  get_public_event
├─────────────────────────────────────────┤
│  Domain        apps/ingestion/models     │  Event (read-only here)
├─────────────────────────────────────────┤
│  Foundation    domain/ shared/           │  errors, ids, db aliases
└─────────────────────────────────────────┘
```

### Domain Model

No new entities were created — the models already existed from `catalog-data-model`
(run-010). This run defines no new persisted state.

| Value Object | Properties | Constraints |
|--------------|------------|-------------|
| `PublicEvent` (frozen dataclass) | `id`, `slug`, `title`, `canonical_url`, `start_time_utc`, `start_time_tz`, `end_time_utc`, `venue_name`, `venue_city`, `status`, `event_version`, `source_name`, `tz_review_pending` | Carries exactly the published fields. The Event's stripped `description` and the `ExtractedRecord.payload` are structurally absent (AD-9). |

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/services/catalog_read.py` | The published read interface: `list_public_events`, `get_public_event`, `EventNotFoundError`, and the frozen `PublicEvent` dataclass |
| `backend/apps/catalog/schemas.py` | `EventOut`, `EventListOut`, `EventPage` — the wire shapes and the query-parameter model (AD-19) |
| `backend/apps/catalog/api.py` | The two routes on a `Router(tags=["catalog"])` |
| `backend/tests/api/test_catalog_api.py` | The endpoint tests (21) |
| `backend/tests/api/test_catalog_read_service.py` | The read-interface tests (20) |
| `backend/tests/api/mutation_probe_catalog.py` | The 9 mutation probes |
| `frontend/lib/api/openapi.json` | The regenerated OpenAPI schema |
| `frontend/lib/api/schema.ts` | The regenerated TypeScript client types |

### Modified

| File | Changes |
|------|---------|
| `backend/config/api.py` | `api.add_router("/catalog", catalog_router)` |
| `backend/pyproject.toml` | `config.api` added to the `worker-not-api` contract's forbidden modules |
| `backend/tests/architecture/test_import_contracts.py` | The planted `import config.api` violation now expects two broken contracts instead of one |

`frontend/lib/api/` is **generated** by `make client` and was never hand-edited (AD-19).

## Key Implementation Details

### 1. What is public is decided in one place

`catalog_read._public_events()` is the single definition of "public":

- `publication_status = published` — this alone excludes `in_review` events, which are not
  digest-eligible and not publicly listed (AD-6, AD-8).
- `status != superseded` — a superseded Event is terminal; the live one that replaced it is
  listed instead.
- `start_time_utc >= now` — "upcoming". A past event leaves the list.
- `select_related("venue", "source")` — the venue and source come along in the same query, so
  serialising the page costs no extra round trips.

A `tz_review_pending` event is `publication_status = published` (the FR-60 partial tier
publishes with a flag), so it **is** listed and carries `tz_review_pending: true`. That is
exactly what the acceptance criteria ask for.

### 2. The ordering is total, so pagination is stable

Ordering is `start_time_utc` ascending, then `id` ascending. The `id` is a UUIDv7, so it is
time-ordered and stable. Two events sharing a start time therefore always come back in the
same order, and page 2 can neither repeat nor skip one. Without the tiebreak the order would
be at the database's discretion, and pagination would be unreliable.

### 3. The pagination envelope is explicit

The response is `{items, page, page_size, total, has_next}` — not Ninja's built-in
`{items, count}`. The built-in shape forces the frontend to derive the rest of the paging
state from two different numbers; the envelope puts everything the client needs in one place,
and it is explicit in the OpenAPI schema, which is what AD-19 wants. `page` defaults to 1,
`page_size` to 20, capped at 100 so a public endpoint can't be asked for the whole catalog in
one request.

### 4. The query parameters are bound correctly

`EventPage` is bound with `Query(...)`:

```python
EVENT_PAGE_QUERY = Query(...)
def list_events(request, filters: EventPage = EVENT_PAGE_QUERY):
```

Without `Query(...)`, a schema-typed argument becomes a request **body** and the query string
would be silently ignored. A module-level singleton keeps the parameter model declared once.
Mutation probe 9 plants exactly this bug and confirms the tests catch it.

### 5. `now` is an explicit parameter, not a hidden clock

The endpoint passes `timezone.now()`; the service takes `now` as an explicit argument. This
matches every other command in the project — no time-freezing library — and it makes every
boundary testable at the exact second. A test asserts an event starting *exactly* at `now` is
included, and another asserts one that already started is not.

### 6. A hidden event reads as absent

`get_public_event` applies the same public filter as the list, so an `in_review` or superseded
event is a 404, not a 403 and not a 200 with a hidden flag. The public catalog has one truth.
`EventNotFoundError` subclasses `domain.errors.NotFoundError`, so `config/errors.py` maps it
to **404** with the shared `{code, message}` body — no per-endpoint `try/except` anywhere.
The endpoint declares `response={404: ErrorOut}`, so the error shape is in the OpenAPI schema
too.

## Security Considerations

| Concern | Approach |
|---------|----------|
| **Session independence (AD-12)** | The endpoints never read or write `request.session`. The tests assert `Set-Cookie` is absent from both responses *and* from the 404. This is the real proof: `SessionMiddleware` only writes a cookie when the session is modified, and a plain read never modifies it. |
| **Untrusted source content (AD-9)** | The response carries only the named published fields. The Event's stripped `description` (plain text from an untrusted source) and the raw `ExtractedRecord.payload` are structurally absent from `PublicEvent` and `EventOut`. A test asserts the exact field set and that no source text appears in the body. |
| **No writes from a surface** | `apps/catalog/api.py` contains no `.save()`, `.create()`, `.update()`, `.delete()` or upsert. The `ingestion` app remains the sole writer of catalog entities (AD-16). The syntactic scan in `tests/architecture/test_no_direct_writes.py` enforces it. |
| **Existence leaks** | A non-public event returns the same 404 as an unknown id. The response does not distinguish "doesn't exist" from "not published". |
| **Resource exhaustion** | `page_size` is capped at 100 by the schema, so a caller can't request the whole catalog in one response. Out-of-range values are rejected with a 422 before the endpoint runs. |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| **No N+1 queries** | `select_related("venue", "source")` loads the venue and source with the event rows, so serialising a page of 20 events costs one query, not 41. |
| **Index-backed ordering and filtering** | The Event model carries `event_listing_idx` on `(publication_status, status, start_time_utc)`, which matches the list query's filter and sort columns. `venue__city__iexact` joins the venue table. |
| **Count without loading** | `total` comes from `queryset.count()`, so the total never drags the whole matching set into memory. |
| **Bounded work per request** | The queryset is sliced before the rows are materialised, so only one page is ever loaded. |
| **Schema wall respected** | The query runs through `.using(CATALOG)`, so it touches only the catalog schema. |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D1 — the detail route key** | The UUID (`id`), not the slug | The AC names `{id}` twice and lists `id` in the response schema. The slug belongs to the later FR-26–28 page intent, and a slug is a different thing from a machine identifier. The response also carries `slug`, so the frontend can build the page route `/events/{slug}` without a second lookup. |
| **D2 — what "upcoming" means** | `start_time_utc >= now`, at the request time | "Upcoming published events" (AC). A past event disappears from the list. |
| **D3 — ordering** | `start_time_utc` ascending, then `id` ascending | The natural order for an events list, and the `id` tiebreak makes the order *total*, so pagination is deterministic when two events share a start time. |
| **D4 — pagination shape** | An explicit `{items, page, page_size, total, has_next}`; `page` 1, `page_size` 20, capped at 100 | Ninja's built-in pagination gives `{items, count}` only, so the client would have to derive the rest. The envelope is explicit in the OpenAPI schema, which is what AD-19 wants. The caps keep a public endpoint from being asked for everything at once. |
| **D5/D6 — cancelled and postponed events** | Both are listed, carrying their `status` | The AC names exactly two exclusions (`in_review`, `superseded`). A cancelled event is still a public fact, and a `status` field that could only ever be `scheduled` would not be worth carrying. |
| **D7 — the `tz_review_pending` flag** | A boolean field alongside `status` | The AC asks for the flag on a `tz_review_pending` event. It is what the frontend needs to show "venue time approximated". |
| **The interface hands over plain data** | A frozen dataclass `PublicEvent`, not model instances | Deviation from the plan, and stricter: the caller never holds a reference to `apps.ingestion.models`, so the import wall holds without either side knowing the other's models. |

## Deviations from Plan

- **The read interface returns a frozen dataclass, not model instances.** The plan proposed
  returning `Event` rows and letting the catalog app shape them. The implementation hands over
  `PublicEvent` values instead. This is strictly stronger for the import contract: the caller
  cannot reach a model even by accident, and the set of published fields is fixed at the
  interface rather than at the call site.
- **The response carries `slug` and `tz_review_pending` beyond the AC's minimum list.**
  `slug` keeps the later public page route possible; `tz_review_pending` is the flag the AC
  asks to be visible.
- **The route parameter is `{event_id}`, not `{id}`.** The AC writes `{id}`; `event_id` is
  clearer in the generated schema and the identifier's type is still `UUID`.
- **The `worker-not-api` import contract was tightened.** `config.api` was *added* to the
  forbidden modules, because it assembles the app routers and so reaches `apps.*.api`
  transitively. The planted-violation test was updated to expect two broken contracts instead
  of one — which matches the new, stricter behaviour.

## Dependencies Added

None. No new package was added to `pyproject.toml` or any lockfile.

## How to Verify

1. **Run the catalog tests**

   ```bash
   cd backend && uv run --directory . python -m pytest tests/api/test_catalog_api.py tests/api/test_catalog_read_service.py -v
   ```

   Expected: 41 passed.

2. **Run the full backend suite with coverage**

   ```bash
   cd backend && uv run --directory . python -m pytest --cov=. --cov-report=term-missing -q
   ```

   Expected: 1649 passed, overall coverage 98.95%, `domain/` 100%.

3. **Prove the tests actually catch the bugs (mutation probes)**

   ```bash
   cd backend && uv run --directory . python tests/api/mutation_probe_catalog.py
   ```

   Expected: `All 9 probes were caught by the suite.`

4. **Check the import walls and the linters**

   ```bash
   cd backend && uv run --directory . lint-imports && uv run --directory . ruff check . && uv run --directory . ruff format --check .
   ```

   Expected: 13 contracts kept, 0 broken; "All checks passed!"; "240 files already formatted".

5. **Check the contract is regenerated and in sync (AD-19)**

   ```bash
   make client && git diff --exit-code frontend/lib/api/
   ```

   Expected: no diff — the committed schema and client match the live API.

6. **Check the frontend still builds against the new client**

   ```bash
   cd frontend && pnpm lint && pnpm typecheck
   ```

   Expected: both clean.

7. **Call the API by hand**

   ```bash
   cd backend && uv run --directory . python manage.py runserver 127.0.0.1:8000
   ```

   ```bash
   curl -i "http://127.0.0.1:8000/api/catalog/events?city=Los%20Angeles&page_size=5"
   curl -i "http://127.0.0.1:8000/api/catalog/events/<a-uuid>"
   curl -i "http://127.0.0.1:8000/api/catalog/events/<a-random-uuid>"
   ```

   Expected: a 200 with `{items, page, page_size, total, has_next}`; a 200 for a published
   event; a 404 with `{"code": "not_found", "message": "We couldn't find that event."}`. In
   every case, **no `Set-Cookie` header**.

## Test Coverage

- Tests added: **41** (21 endpoint + 20 read interface)
- Mutation probes: **9**, all caught
- Coverage: **98.95%** overall; the three new modules are at **100%**
- Status: **passing** — 1649 passed, 0 failed, 0 skipped

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Developer notes captured
- [ ] A frontend page consuming the API (explicitly out of scope — the FR-26–28 intent)

## Developer Notes

- **`config.api` is part of the API surface.** When you add a router to `config/api.py`, the
  worker can now reach `apps.*.api` through it. That is why `config.api` was added to the
  `worker-not-api` contract's forbidden modules. If you add another router, the contract
  already covers it — no change needed.
- **`Query(...)` is load-bearing.** `EventPage` must stay bound with `Query(...)`. Without it,
  Ninja treats a schema-typed argument as a request body and the query string is ignored —
  the filters would silently stop working. Mutation probe 9 guards this.
- **`PublicEvent` is frozen.** If you need a new published field, add it to the dataclass, to
  `_to_public_event`, and to `EventOut` — and then to `EventOut.from_public_event`, which
  projects the dataclass onto the wire shape with `vars()`. A field added to one and not the
  others will surface as a `TypeError` in the endpoint, not silently.
- **The service clamps, the schema validates.** `list_public_events` clamps `page` and
  `page_size`; `EventPage` rejects out-of-range values with a 422. The endpoint echoes the
  schema's values, not the service's clamped ones. This is currently consistent because the
  schema bounds are stricter than the clamps, but it is a latent inconsistency: if you widen
  one, widen the other. It is recorded as CONFIRM-1 in the review report.
- **The list endpoint's scope is "upcoming", not "all".** A past event simply isn't there.
  If a later intent needs a historical view (for the digest, say), that is a different query,
  not a change to this one.
- **`has_next` is computed from the page and the total**, not from whether the current page
  came back full. A page past the end returns zero items and `has_next: false`.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-017*
