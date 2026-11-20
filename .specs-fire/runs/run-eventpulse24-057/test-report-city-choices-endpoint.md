---
run: run-eventpulse24-057
work_item: city-choices-endpoint
intent: city-picker-and-auto-collection
generated: 2026-11-20
status: passed
---

# Test Report: The picker's choices endpoint

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| API (new) | 18 | 0 | 0 | 100% |
| Architecture (widened) | 1105 | 0 | 0 | — |
| Backend suite (full) | 7907 | 0 | 0 | 97.44% |
| **Total** | **7907** | **0** | **0** | **97.44%** |

`cities_api.py` and `public_surface.py` at **100%**. `domain/` still 100%. `lint-imports`
21 contracts kept, 0 broken. Frontend `typecheck` passes against the regenerated client.

## Acceptance Criteria Validation

- ✅ **A public endpoint returns the catalog as an ordered list of `{ value, label }`** — `GET /api/public/cities`. `test_every_catalog_row_is_offered_exactly_once` asserts all 165 rows, once each.
- ✅ **`value` is the catalog's `name`; `label` is the disambiguated display form** — pinned on the Portland pair and Chittagong. `test_every_value_round_trips_through_the_catalog` additionally asserts every `value` resolves through `lookup()`, so whatever the picker sends back is storable verbatim — which is what `stored-city-is-the-picked-city` will rely on.
- ✅ **Alphabetical by label under `str.casefold`, in Python, never a database `ORDER BY`** — the order is asserted equal to `domain.city_catalog.choices()`, and separately to `sorted(labels, key=str.casefold)`. There is no database involved at all, which is asserted directly (below).
- ✅ **Identical for every caller; reads no session and no `personal`** — `test_a_signed_in_and_an_anonymous_request_get_identical_bytes` compares `response.content`, not parsed JSON, following the preview suite's reasoning that two bodies can be equal as JSON and differ as bytes, and a cache sees bytes. Plus: no `Set-Cookie`, `Vary` carries nothing session-related, and the architecture guard checks the *source* for `request.user`/`personal`.
- ✅ **`list_supported_cities()` unchanged in behaviour, docstring amended** — no code changed; `tests/ingestion` passes untouched. The docstring now states what it answers ("which cities can the preview show cards for right now?"), what it does not ("the picker's source"), and the failure that conflating them caused.
- ✅ **`home-city.tsx`'s stale docstring left to the item that rewires it** — not touched here, per AC 6.
- ✅ **An architecture test asserts the endpoint touches no `personal` model** — `tests/architecture/test_preview_anonymity.py` now covers `cities_api.py`, `public_surface.py` and the preview's modules under one `PUBLIC_SURFACE_MODULES` list.

## The decisions taken at the checkpoint

| Decision | Chosen | Where it is tested |
|---|---|---|
| Throttle the endpoint | Yes, own scope `cities` | `TestItIsThrottled`: the limit, a 429 carrying `Retry-After`, the refusal being `no-store`, and isolation from **both** preview routes |
| Cache TTL | New `CITY_CHOICES_CACHE_CONTROL`: 1h browser / 1d edge / 1w stale-while-revalidate | `test_the_response_is_publicly_cacheable_for_longer_than_the_preview` |

## Tests Written — `tests/api/test_cities_api.py` (18)

**What is offered** (6): every row once; `value`/`label` on the Portland pair and
Chittagong; every value round-trips through `lookup`; the order equals `choices()`; the
casefold sort; and **`test_a_city_with_no_events_is_still_offered`** — the load-bearing one,
asserting `list_supported_cities()` returns nothing while Chittagong and Dhaka are both
offered. That is the item in one assertion.

**Anonymous and cacheable** (5): identical bytes signed-in vs anonymous; no cookie; the
longer cache headers; `Vary` free of `Cookie`/`Authorization`; and **zero queries on both
database aliases**.

**Throttled** (4): the limit, the retry hint, no-store on refusal, and scope isolation from
each preview route.

**Not disturbing the preview** (2): both routers answer on the shared `/public` prefix; the
two city lists demonstrably answer different questions.

**Shape** (1): the response is an object, not a bare array.

## Mutation Check

| Mutation | Result |
|---|---|
| A database read added to the view | `test_the_endpoint_runs_no_query_at_all` fails — the technical note is enforced, not merely written |
| Throttle scope changed from `cities` to `preview` | **First attempt: nothing failed.** The test checked `/preview/cities`, whose scope is `preview:cities`, so it could not have detected a collision with `/preview`. Strengthened to parametrize over both preview routes; the mutation is now caught |

The first result is the useful one: a test of mine could not fail, and the mutation check is
what found it. It is recorded here rather than quietly fixed.

## Test Commands

```bash
uv run --directory backend pytest tests/api/test_cities_api.py -q
uv run --directory backend pytest tests/architecture -q
make test-backend && make coverage-backend
make client && uv run --directory backend pytest tests/api/test_contract.py -q
pnpm --dir frontend typecheck
```

## Issues Found

Four, all fixed, detailed in `review-report-city-choices-endpoint.md`: a cross-module
private import (resolved by extracting `public_surface.py`), a fixed-count architecture
assertion that would break on any added public route, a test of mine that could not fail,
and an assertion of mine that rested on incidental properties of today's data.

The OpenAPI contract and the generated TypeScript client were regenerated (`make client`);
`tests/api/test_contract.py` enforces that they match the live API.

## Ready for Completion

- [x] All tests passing (7907, zero failures)
- [x] Coverage met (100% new modules, 100% `domain/`, 97.44% overall)
- [x] All 7 acceptance criteria validated
- [x] Frontend contract regenerated and typechecking

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
