---
run: run-eventpulse24-017
work_item: public-catalog-read-api
intent: event-catalog-ingestion
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at: 
---

# Implementation Plan: Public Catalog Read API

## Approach

> **Needs your call:** decisions **D1–D7** below.

The `catalog` app publishes the two read endpoints; the `ingestion` app publishes the read
interface they call. The wall is one-way: `catalog` → `ingestion.services`, never
`apps.ingestion.models` (contract `models-ingestion`).

```
GET /api/catalog/events?city=&start=&end=&page=&page_size=
        │
        ▼
apps/catalog/api.py ──► apps/ingestion/services/catalog_read.py   (the published interface)
        │                        │
        │                        └─► Event.objects.using(CATALOG) ... (select_related venue/source)
        │
        └─► apps/catalog/schemas.py  (EventOut, EventListOut)
```

**New read interface `backend/apps/ingestion/services/catalog_read.py`** — the only place that
touches `apps.ingestion.models` for reading:

| Function | Returns |
|---|---|
| `list_public_events(*, now, city=None, starts_after=None, starts_before=None, page=1, page_size=DEFAULT)` | `(items, total)` — `items` are `Event` rows, already ordered and sliced |
| `get_public_event(*, event_id)` | one `Event` row |

It returns **model instances**, not dicts: the shapes live in `apps/catalog/schemas.py`, and
the wall rule is that the catalog app owns the wire format. The service layer owns the
query, which is the AD-2 "cross-module calls go through the target app's published service
interface" rule.

**The query (D2):**

```python
Event.objects.using(CATALOG)
    .filter(publication_status=Event.PublicationStatus.PUBLISHED)   # excludes in_review
    .exclude(status=Event.Status.SUPERSEDED)                       # superseded is terminal
    .filter(start_time_utc__gte=now)                               # "upcoming"
    .select_related("venue", "source")
```

`publication_status` already excludes `in_review`; `status != superseded` excludes the
terminal ones. A `tz_review_pending` Event is `publication_status = published` (the FR-60
partial tier publishes with a flag), so it is included and carries the flag — exactly what
the AC asks.

**Ordering (D3):** `start_time_utc` ascending, then `id` as the tiebreak. `id` is a UUIDv7,
so it is time-ordered and stable — the same start time always returns the same page.

**Filters:** `city` matches `venue__city` (case-insensitively, exact — not a fuzzy search);
the date range filters on `start_time_utc` (`starts_after` inclusive, `starts_before`
inclusive). A `venue` that is `NULL` is excluded by a city filter, and is fine without one.

**The `catalog` app's HTTP layer:**

- `apps/catalog/schemas.py` — `EventOut` (the AC's response schema), `EventListOut`
  (the paginated envelope), `EventPage` (query params).
- `apps/catalog/api.py` — two routes on a `Router(tags=["catalog"])`.
- `config/api.py` — `api.add_router("/catalog", catalog_router)`.

**Pagination (D4):** an explicit envelope, not Ninja's built-in pagination. Ninja's
`PageNumberPagination` emits `{items, count}` with no `page`, `page_size`, `total` or
`has_next`, which forces the frontend to recompute pagination from two different numbers.
The envelope is `{items, page, page_size, total, has_next}` — one place the frontend reads.

**No session (D5):** the endpoints never touch `request.session`, and the response must carry
**no `Set-Cookie` header**. Django's `SessionMiddleware` only sets a cookie when the session
is *modified*; a plain read never modifies it, so no cookie is written. The test asserts
`Set-Cookie` is absent — that is the real proof of AD-12, not the absence of a session read.

**Errors:** `get_public_event` raises `EventNotFoundError(NotFoundError)` → `config/errors.py`
maps it to **404** with the shared `{code, message}` body. The endpoint declares
`response={404: ErrorOut}` so the shape is in the OpenAPI schema (AD-19).

**No raw payload (AD-9):** `EventOut` carries only the AC's named fields. The Event model's
`description` and the `ExtractedRecord.payload` never appear. `description` in particular is
stripped plain text from an untrusted source, so it is not published here — the AC does not
list it.

### Decisions that need your call

| # | Question | Proposed choice | Why |
|---|---|---|---|
| **D1** | **Does the detail URL use the id or the slug?** | **`/api/catalog/events/{event_id}` — the UUID.** The *public web page* uses the slug (the spine's Ids convention: "Public URLs use a slug, never the PK"), but that is the frontend page route, not the API route. The API is a machine contract that the generated TS client consumes; a UUID is a stable, type-checkable identifier, and the schema can declare it as `UUID` so the client gets it typed. The slug is also a different thing entirely — it is minted from the title and can be long, and a page route lives in Next.js. The AC itself says "`GET /api/catalog/events/{id}`", and the response schema lists `id` — so `id` it is. **The response also carries `slug`**, so the frontend can build the page route (`/events/{slug}`) without a second lookup. | The AC names `{id}` twice and lists `id` in the response schema. The slug belongs to the later FR-26–28 page intent, which is explicitly out of scope. Carrying `slug` in the payload keeps the page route possible. |
| **D2** | What exactly does "upcoming" mean? | **`start_time_utc >= now`**, where `now` is the request time. A past event disappears from the list. | "Upcoming published events" (AC). Events with no start are impossible (`start_time_utc` is required). A **cancelled** event still has a start time in the future, so it would still be listed — is that right? See D5. |
| **D3** | Ordering | `start_time_utc` ascending, then `id` ascending as the tiebreak. | The natural order for an events list. The `id` tiebreak makes pagination deterministic when two events share a start time — without it, page 2 could repeat or skip an item. |
| **D4** | Pagination shape and default size | An explicit envelope `{items, page, page_size, total, has_next}`, `page` defaults to 1, `page_size` defaults to **20** and is capped at **100**. | Ninja's built-in pagination gives `{items, count}` only, so the client would have to derive the rest. The envelope is explicit in the OpenAPI schema, which is what AD-19 wants. The caps keep a public endpoint from being asked for the whole catalog in one request. |
| **D5** | Is a **cancelled** event listed? | **Yes — cancelled events are still listed**, with `status: "cancelled"`. `in_review` and `superseded` are the only exclusions the AC names. | The AC names exactly two exclusions. A cancelled event is still a public fact (someone may want to know it was cancelled), and the response carries `status` so the frontend can style it. `status` in the response is only useful if more than one value can appear. |
| **D6** | Is a **`postponed`** event listed? | **Yes**, same reasoning: `status: "postponed"` with its start time. | Same as D5. |
| **D7** | The `tz_review_pending` flag | Returned as a boolean `tz_review_pending` field on each event, alongside `status`. | The AC says "a `tz_review_pending` event included with that flag in the response". The flag is the reason the frontend would want to show "venue time approximated". |

### Deviations from the work item

- **D1**: the API route uses the UUID, not the slug. The spine's "public URLs use a slug"
  rule is honoured on the *page* route (the frontend's `/events/{slug}`), not on the API
  route; the slug travels in the payload so that route is buildable.
- The list envelope adds `page`, `page_size`, `total` and `has_next` beyond the minimum
  "paginated"; the AC names no exact shape.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/services/catalog_read.py` | The published read interface: `list_public_events`, `get_public_event`, and the `EventNotFoundError` |
| `backend/apps/catalog/schemas.py` | `EventOut`, `EventListOut`, `EventPage` (the query params) — the wire shapes (AD-19) |
| `backend/apps/catalog/api.py` | The two routes: `GET /api/catalog/events` and `GET /api/catalog/events/{event_id}` |
| `backend/tests/api/test_catalog_api.py` | The AC's test list: ordering, pagination, filters, exclusions, the tz flag, the 404 shape, anonymous access, no `Set-Cookie` |
| `backend/tests/api/test_catalog_read_service.py` | The read interface on its own: the query's filters and ordering, without the HTTP layer |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/config/api.py` | `api.add_router("/catalog", catalog_router)` |
| `backend/apps/ingestion/services/__init__.py` | Nothing needed if the catalog app imports the module path directly — check the existing convention first |
| `.specs-fire/standards/coding-standards.md` | The catalog-read rules: the published interface, the `now` seam, the exclusions, the pagination envelope |

`frontend/lib/api/openapi.json` and `frontend/lib/api/schema.ts` are **regenerated** by
`make client` (AD-19), not hand-edited. `backend/tests/api/test_contract.py` fails until
that is done.

## Tests

The work item's tests, mapped to files:

| Work-item test | File |
|---|---|
| List ordering (`start_time_utc`, then `id`) | `tests/api/test_catalog_api.py` |
| Pagination: the page size, the envelope (`total`, `has_next`), and no repeats or skips across pages | same |
| Filters: `city`, the date range; a city that matches nothing | same |
| `in_review` and superseded excluded; a `tz_review_pending` event included with the flag | same |
| The 404 shape (`{code, message}`, via `config/errors.py`) | same |
| An anonymous request succeeds (no auth, no login) | same |
| No `Set-Cookie` header on either endpoint | same |
| The response carries no raw payload (no `description`, no `payload`) | same |
| The read service on its own: the exclusions and the ordering, the `now` boundary | `tests/api/test_catalog_read_service.py` |

No pipeline is needed: the tests use the factories (`EventFactory`, `make_superseded_pair`).

Before the test report I'll run mutation probes, checking that each of these bugs is caught:
- `publication_status` filter dropped (an `in_review` event leaks into the list)
- the `superseded` exclusion dropped
- the `start_time_utc >= now` filter dropped (a past event leaks in)
- the `id` tiebreak dropped (pagination becomes unstable)
- the `city` filter dropped
- `EventNotFoundError` raised as a plain `Exception` (no 404)
- a `Set-Cookie` header appearing

## Technical Details

- **Gates:** `make lint-backend`, `make manage ARGS="check"`,
  `make manage ARGS="makemigrations --check --dry-run"`, `make coverage-backend`
  (≥ 80% overall, 100% `domain/`). `domain/` is untouched.
- **Import contracts:** `apps.catalog` imports `apps.ingestion.services.catalog_read`, never
  `apps.ingestion.models` (`models-ingestion` keeps passing). The `layers` contract holds:
  `apps` → `shared`/`domain` only.
- **No migration.** The models don't change.
- **No session.** The endpoints never read or write `request.session`; no `Set-Cookie` is
  emitted (AD-12).
- **No write.** `apps/catalog/api.py` is a surface: the
  `tests/architecture/test_no_direct_writes.py` scan forbids a `.save()`/`.create()` there.
- **`now`:** the endpoint uses the request time, `timezone.now()`. The read service takes an
  explicit `now` parameter, like every other command in this project — no time-freezing
  library (run-016 P6/S6).
- **The response times:** `start_time_utc` and `end_time_utc` are ISO-8601 with the UTC
  offset; `start_time_tz` is the IANA name (AD-6). The frontend converts for display.
- **Generated client:** `make client` rewrites `frontend/lib/api/openapi.json` and
  `frontend/lib/api/schema.ts`. `backend/tests/api/test_contract.py` compares the committed
  schema with the live API and must pass.

---
*Plan saved. Awaiting approval at Checkpoint 1.*
