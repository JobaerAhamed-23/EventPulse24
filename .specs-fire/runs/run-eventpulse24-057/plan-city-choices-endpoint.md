---
run: run-eventpulse24-057
work_item: city-choices-endpoint
intent: city-picker-and-auto-collection
mode: confirm
checkpoint: plan-approval
status: approved
approved_at: 2026-11-20
---

# Implementation Plan: The picker's choices endpoint

## Approach

`GET /api/public/cities` returns the curated catalog as `{ value, label }` pairs. It runs
**no query at all** — the answer is a projection of `domain.city_catalog`, the way
`ranking_transparency_api` projects `shared.constants`. The nearest precedent in this
codebase is that endpoint, not the preview's.

### A separate module, not a new route in `preview_api.py`

This is the part worth getting right, because the whole item exists to end a confusion.

`GET /api/public/preview/cities` answers **"which cities can the preview actually serve
right now?"** — a live question about ingested events, computed from `EventFit`. The new
endpoint answers **"which cities may a reader pick?"** — a static question about the
curated catalog, true whether or not a single event has been ingested.

Putting the second route inside `preview_api.py`, under the `/preview/` prefix, would file
the answer to the second question under the name of the first. That is precisely the
mistake the work item is correcting. So: a new `apps/catalog/cities_api.py` with its own
router, mounted at `/public`, giving `GET /api/public/cities`.

`list_supported_cities()` is untouched in behaviour. Its docstring gains a paragraph saying
what it is — the preview's coverage answer — and what it is not.

## The two open calls, decided at the checkpoint

Both were put to the user and both recommendations were taken: **throttled with its own
scope**, and **a new longer cache TTL**. The reasoning below is kept as the record.

### 1. Should the endpoint be throttled?

Its sibling `/preview/cities` is throttled per IP with its own scope. This one does no
database work, calls no port and allocates one list — serving it is **cheaper than checking
the throttle**, which is a Redis round-trip.

**Recommendation: throttle it anyway, with its own scope (`cities`).** Not because this
response is expensive, but because "every anonymous route on this surface is throttled" is
an invariant someone can hold in their head, while "throttled unless it happens to be
cheap" is a judgement each new route re-litigates — and the endpoint that is cheap today is
the one that quietly grows a query later.

The honest cost: a throttle port outage turns a static list into a 429, and the picker has
nothing to show. If you would rather this route never depend on Redis, say so — it is a
defensible answer and the opposite of the recommendation.

### 2. How long should it be cacheable for?

The preview's `PREVIEW_CACHE_CONTROL` is `max-age=60, s-maxage=300` — short, because the
preview's content changes as events are ingested. **This list changes only when code
ships.**

**Recommendation: a new `CITY_CHOICES_CACHE_CONTROL`,
`public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800`.** An hour in the
browser, a day at the edge, and a week of serving a stale copy while it refreshes.

The consequence to accept: after a deploy that adds a city, an edge cache may keep offering
yesterday's list for up to a day. For a picker whose answer is "roughly 165 cities, grown
one PR at a time", that seems right — but it is a product call, not a technical one, and
reusing the preview's 60/300 is the conservative alternative.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/catalog/cities_api.py` | The router and the one route |
| `backend/tests/api/test_cities_api.py` | Shape, order, anonymity, caching, (throttle) |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/catalog/preview_schemas.py` | `CityChoiceOut(value, label)` and `CityChoicesOut(cities)` |
| `backend/config/api.py` | `api.add_router("/public", cities_router)` |
| `backend/shared/constants.py` | `CITY_CHOICES_CACHE_CONTROL` *(call 2)* |
| `backend/apps/ingestion/services/preview_read.py` | `list_supported_cities` docstring: what it answers, and that it is not the picker's source (AC 5) |
| `backend/tests/architecture/test_preview_anonymity.py` | Generalise `PREVIEW_MODULES` to cover every anonymous surface and add the new ones (AC 7) |
| `backend/tests/architecture/test_no_direct_writes.py` | The hand-maintained surface-file count, 26 → 27 |

## Technical Details

**The response shape is an object, not a bare array.**

```json
{ "cities": [ { "value": "Portland, OR", "label": "Portland, Oregon" }, … ] }
```

Matching `PreviewCitiesOut`'s `{ "cities": [...] }`. A bare top-level array cannot grow a
sibling field later without breaking every client, and this one may well want a count or a
catalog version.

**`value` is what gets stored, `label` is what gets shown.** Straight from `CityChoice`:
`value = row.name` ("Portland, OR"), `label = row.label` ("Portland, Oregon"). Item 1
already asserts over the whole dataset that the two never coincide and that no two rows
share either — so the `<select>` cannot show a reader two identical options, and whatever
comes back can be stored verbatim.

**The order comes from `choices()`, which sorts in Python under `str.casefold`.** Item 1
built it that way, and AC 3 requires it for the reason `list_supported_cities` already
documents at length: a database `ORDER BY` on text is a locale collation, so two
deployments with different locales would order the picker differently. There is no database
here at all, which makes the requirement free — but the test asserting it still belongs.

**No session, no `personal`, no `request.user`.** The response is identical for every
caller, which is what makes it cacheable; AD-12 and cacheability are the same fact.

## Tests

| Test File | Coverage |
|-----------|----------|
| `tests/api/test_cities_api.py` | 200 with every catalog row, once; `value`/`label` exactly the catalog's `name`/`label`; alphabetical under `casefold` including a case the database would order differently; an anonymous and a signed-in request get **identical bytes**; the cache headers; `Vary` carries nothing session-related; no `Set-Cookie`; the endpoint issues **zero queries** (`django_assert_num_queries(0)`); a city absent from the preview's coverage is still offered — the item's whole point; (throttle behaviour, per call 1) |
| `tests/architecture/test_preview_anonymity.py` | The new modules carry no `request.user` and no `personal` (AC 7) |
| `tests/architecture/test_no_direct_writes.py` | The new surface file is in the AD-5 list |
| `tests/ingestion/test_preview_read.py` | Unchanged — `list_supported_cities`'s behaviour must not move (AC 5) |

The query-count assertion is the one that enforces the technical note: "the catalog is
static, so this endpoint can be served without a database query at all. Do not add a
database read to make it feel symmetrical with the preview endpoint."

## Risks

| Risk | Mitigation |
|---|---|
| The new route shadows or is shadowed by `/public/preview/...` | Two routers on one prefix is the pattern `/settings` already uses with five. A test hits both routes in one run |
| The picker starts disagreeing with what Browse can serve | It is *supposed* to. `browse-collecting-states` (item 9) is where a picked city with no events is explained to the reader, and `city-coverage-request` (item 10) is the escape hatch |
| Frontend still reads `preview/cities` | Item 11 (`home-city-dropdown-catalog`) rewires it, and AC 6 explicitly leaves `home-city.tsx`'s stale docstring to that item |

---
*Plan approved at the checkpoint (confirm mode). Execution follows.*
