# Test report: `event-detail-api`

**Work item**: `event-detail-api`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-31

---

## What was built

| File | Kind | What it is |
|---|---|---|
| `backend/apps/personalization/detail_api.py` | new | `GET /api/events/{id}` and `POST /api/events/{id}/opened` — two audiences, two handlers, two rules |
| `backend/apps/personalization/services/detail_read.py` | new | `read_event_detail(*, event_id, user_id, now) -> EventDetail` — the read of the persisted rows |
| `backend/apps/personalization/services/neighbor_count.py` | new | `count_neighbors(*, event_id, now) -> NeighborCount` — the k-anonymous count, bucketed before the number is formed |
| `backend/apps/personalization/services/detail_opens.py` | new | `record_detail_open(...)` — the named command, with its audit row |
| `backend/apps/personalization/models.py` | modified | `EventDetailOpen` — the qualifying-signal model |
| `backend/apps/personalization/migrations/0010_eventdetailopen.py` | new | the migration for it |
| `backend/apps/personalization/schemas.py` | modified | `WhyThisOut`, `DetailPersonalOut`, `EventDetailFactsOut`, `EventDetailOut` |
| `backend/apps/ingestion/services/catalog_read.py` | modified | `PublicEventDetail` and `get_public_event_detail` |
| `backend/config/api.py` | modified | the `/events` router mounted |
| `backend/tests/architecture/test_write_ownership.py` | modified | `personalization_eventdetailopen` added to `TABLE_OWNERS` |
| `backend/tests/personalization/factories.py` | modified | `EventDetailOpenFactory` |
| `backend/tests/personalization/test_event_detail_api.py` | new | 52 tests |
| `frontend/lib/api/openapi.json` | modified | the regenerated contract |
| `frontend/lib/api/schema.ts` | modified | the regenerated TypeScript client |

## The test file

**52 tests**, in eight groups:

| Group | Tests | What it pins |
|---|---|---|
| the public facts | 6 | the catalog's own fields through the published interface; the instant plus the zone; sold-out; a non-public event is a 404; an event that has started is a 404; an unknown event is a 404 |
| the breakdown is persisted, not recomputed | 5 | the composition's own tags, bucket and badge; a composition from three days ago is still found; the most recent composition wins; no composition is an explicit absence, not an empty breakdown; **the ranking is never called**; the read does not reach the Event Fit |
| the anonymous caller | 5 | no breakdown, no bucket, no saved state; **the `personal` schema is never queried**; another user's explanation is invisible; the Event Fit is not reached |
| the saved state | 3 | the user's own save row; an unsaved event is not saved; another user's save is not yours |
| the neighbor count | 14 | 4 is suppressed; 5 appears; every bucket boundary (5/9/10/24/25/99/100/101); the pure `bucket_for` at every bound; **the payload never carries an exact count**; the window's outside; the window's boundary; a user who saved and opened counts once; the count is tier-agnostic; the count does not grow with the neighbour count |
| the detail-open signal | 6 | the signal is recorded; it makes the user a neighbour; it is recorded once per `(user, event)`; it stores nothing but the pair and the time; an anonymous caller is refused; the `GET` writes nothing |
| the contract | 3 | the endpoint is in the OpenAPI schema; the endpoint takes no `user_id` parameter; reviews and similar-events are absent |
| the service level | 3 | the service reads the breakdown and the count together; the service gives an anonymous caller no personal state; the exact instant at the window's boundary |

## The acceptance criteria, one by one

| Criterion | How it is met | Test |
|---|---|---|
| the public facts come from `catalog_read`'s published interface, never the models, never the Event Fit | `get_public_event_detail` returns a frozen dataclass; the read imports no `apps.ingestion.models` | `test_the_detail_carries_the_events_public_facts`, plus the `models-ingestion` import contract |
| the breakdown reads the most recent composition, whatever day it was composed, with its persisted tags, bucket and badge | `_most_recent_composition` orders by `-composed_at, -id` and reads the row's own values | `test_the_breakdown_comes_from_a_composition_made_today`, `test_the_breakdown_comes_from_a_composition_made_three_days_ago`, `test_the_most_recent_composition_wins` |
| no composition means no explanation — an explicit absence; the ranking is not called | `why_this` is `None`; `domain/ranking.py` is monkeypatched to raise | `test_no_composition_means_an_explicit_absence`, `test_the_read_never_calls_the_ranking` |
| an anonymous caller gets the public facts and nothing personal; the Event Fit is not reached | `user_id is None` short-circuits before any personal query | `test_an_anonymous_caller_gets_the_public_facts`, `test_an_anonymous_caller_gets_nothing_personal`, `test_the_anonymous_path_never_queries_the_personal_schema`, `test_the_read_does_not_reach_the_event_fit` |
| a qualifying user saved **or** opened in the last 30 days | the union of `SavedEvent` and `EventDetailOpen`, each windowed on its own timestamp | `test_a_save_outside_the_window_does_not_qualify`, `test_an_open_outside_the_window_does_not_qualify` |
| the threshold is ≥5; below it the count is silently suppressed | `bucket_for` returns `None` below 5, and `None` is the absence of a bucket, not a fourth key | `test_four_neighbors_are_suppressed`, `test_the_bucket_function_is_the_rule` |
| buckets are 5–9 / 10–24 / 25–99 / 100+ | the four keys, with inclusive upper bounds | `test_the_buckets_are_the_ones_fr_24_names` (parametrised at 8 counts), `test_the_bucket_function_is_the_rule` |
| exact counts are never exposed — not even as a number the frontend chooses not to show | there is **no count field** on the dataclass or on the schema; the assertion is on the payload's shape | `test_the_payload_never_carries_an_exact_count` |
| the count is tier-agnostic | the assertion is on the **shape of the SQL that runs**: no tier predicate on the signal queries | `test_the_count_is_tier_agnostic` |
| "same area" is city equality, and the deviation is named | D6 names it in the module docstring and in the brief; the count filters on the event | (a design decision, documented — and the event's city is read to exclude venue-less events) |
| opening the detail is recorded as a qualifying signal; a named command with an audit entry; it does not block the read | `record_detail_open` is the named command, writes the audit row in the same transaction; the read never calls it | `test_the_open_signal_is_recorded`, `test_the_read_writes_nothing` |
| similar-events and the reviews count do not ship — absent, not present-and-empty | neither appears on the payload | `test_the_payload_never_carries_an_exact_count` (the shape assertion covers it) |
| sold-out state flows through | `is_sold_out` is on the facts | `test_the_sold_out_state_flows_through` |
| Pydantic schemas, generated client, no hand-written types | `EventDetailFactsOut`, `DetailPersonalOut`, `EventDetailOut`; `make client` run and the diff committed | `test_the_endpoint_is_in_the_openapi_schema` |
| the neighbour counts at 4, 5, 9, 10, 24, 25, 99, 100 and 101 | the parametrised boundary test, plus the pure function's own boundaries | `test_the_buckets_are_the_ones_fr_24_names`, `test_the_bucket_function_is_the_rule` |
| the 30-day window at its boundary | pinned at the **service**, where `now` is a parameter, so the instant is exact | `test_a_save_exactly_on_the_window_boundary_qualifies`, `test_a_save_one_second_inside_the_window_qualifies` |
| the detail-open signal recorded once per the stated rule | one row per `(user, event)`, the timestamp refreshed | `test_the_open_signal_is_recorded_once_per_pair` |

## The gate

```
uv run pytest --cov --cov-report=term-missing -q
→ 3802 passed, 99.17% total coverage

uv run ruff check .
→ All checks passed!

uv run ruff format --check .
→ 410 files already formatted

uv run lint-imports
→ Contracts: 19 kept, 0 broken.

uv run coverage report --include='domain/*' --fail-under=100
→ TOTAL 750 0 100%

uv run python manage.py makemigrations --check --dry-run
→ No changes detected

pnpm --dir frontend typecheck
→ Types generated successfully

pnpm --dir frontend lint
→ (clean)

pnpm --dir frontend format:check
→ All matched files use Prettier code style!
```

**Both new service modules are at 100% coverage** — `detail_read.py`, `neighbor_count.py` and
`detail_opens.py` do not appear in the coverage report, which lists only files with a miss.

## The failures the tests found

Six, and every one of them was a real defect — in the implementation, in the test, or in
the design.

1. **`Status.HTTP_204_NO_CONTENT` does not exist.** The detail-open `POST` returned a
   500 on every call. Django Ninja's `Status` class has no such constant; the codebase's
   own convention is `Status(204, None)`, and the endpoint now uses it. This was a
   plain typo-level mistake in the implementation, and the test that caught it was the
   one that asserted a 204.

2. **Two tests could not create two users.** The test file's `make_user` had a fixed
   email, and `identity_user.user_email_uq` is a real constraint. The helper now
   generates a unique email by default — the rule the constraint was already stating.

3. **The datetime assertion compared strings, not instants.** Ninja serializes an
   instant to millisecond precision with a `Z` suffix; Python's `.isoformat()` keeps
   microseconds and an `+00:00` offset. The two strings differ for a timestamp that is
   the *same instant*. The test now parses the wire value and compares the instants
   within a millisecond — the wire format's precision is a serialization detail, not the
   contract, and the contract is "an instant in UTC, plus the zone separately".

4. **The window's boundary was untestable at the endpoint.** The endpoint resolves `now`
   from the wall clock, so `NOW - 30 days` (pinned at import) is a few milliseconds
   *older* than the service's own `now - 30 days`, and an inclusive boundary that should
   have qualified was one hair outside the window. **The boundary is now pinned at the
   service**, where `now` is a parameter and the instant is exactly expressible, and a
   second test covers one second inside it. The endpoint-level tests keep a margin.

5. **A neighbour count was wrong by one.** The test that a user who both saved and
   opened counts *once* set up 3 neighbours plus that user — 4 distinct users, below the
   threshold of 5, so the bucket was correctly `None` and the test was wrong. Fixed to
   4 neighbours, and a **second** test was added for the case where the arithmetic
   matters: 4 distinct users (one of whom has both signals) stay below the threshold,
   while a multiplication of their signals would have pushed the count to 5 and made the
   bucket appear. The two tests together pin the union, not the count of signals.

6. **The tier-agnostic test asserted on prose.** It read the module's source and
   asserted the word "pro" was absent — and the module's own docstring says "Pro and
   Free users count identically", so the test failed on its own explanation. The
   assertion is now on **the SQL that actually runs**: the two signal queries are
   located in the captured query log and asserted to carry no tier or subscription
   predicate. A prose grep was never a meaningful test of a query's shape.

## What the tests do **not** cover

- **The composition itself.** `test_digest_composition.py` owns it. This item reads what
  it wrote.
- **The Event Fit.** The architecture contract `AD-10 personalization never reaches the
  Event Fit` and `AD-10 the Event Fit is computed on the catalog side` both hold, and the
  test file monkeypatches the read to raise if it is reached.
- **The frontend's rendering of the bucket keys.** `frontend-event-detail` owns it. The
  server states "few"; the client speaks the user's language.
- **The retention of `EventDetailOpen`.** The model carries `PREFERENCE_SIGNALS` and the
  **30-day query window** is shorter than the **12-month deletion policy** — a recorded
  gap, named in D5. The deletion job itself is not this item's work.
- **The `POST`'s CSRF behaviour under a real cross-origin attack.** The endpoint uses the
  shared `current_user` seam, which runs the CSRF check on unsafe methods. What is
  pinned here is the *shape* — the read writes nothing, and the signal needs a session.
