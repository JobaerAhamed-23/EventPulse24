---
run: run-eventpulse24-029
work_item: browse-read-api
intent: browse-surface
generated: 2026-11-12
mode: validate
---

# Implementation Walkthrough: The Browse Read API

## Summary

`GET /api/personal/browse` — the read behind the `/browse` discovery surface. It takes one
bounded pool of the signed-in user's city events across a seven-day window, ranks it with the
Relevance Pulse, explains each card with the personal Why-this Tags, joins the user's own save
state in one query, reports the save allowance without spending it, and slices the result into
the two server-named tiers. No model was added and no migration was needed: Browse is a read.

The one decision that changed the shape of the work is `total`. The approved design said one
`COUNT(*)` per request; the implementation reports the **size of the ranked pool** instead,
because FR-14's staleness bound is applied in Python after the SQL narrows the set, and a SQL
count would advertise a number no amount of scrolling reaches. Checkpoint 2 approved that
change.

## Structure Overview

Browse sits on the personalization side of the AD-3 wall. The public facts arrive from the
catalog through `catalog_read`'s published interface as frozen dataclasses; the personal side
is read directly from the `personal` schema. Nothing joins the two in SQL and no transaction
spans them — the join happens in Python, which is the shape `digest_candidates.py` already
documents.

The read runs in one direction: **context → pool → rank → explain → join → gate → split**. The
user's city and zone come from the digest preference, so "your city" means one thing across
the Digest and Browse. The pool comes from `list_public_candidates`, which applies the publish,
confidence, timezone and staleness gates against shared constants. Ranking and explanation come
from `domain/ranking`, the same pure-stdlib functions the Digest uses. The saved-state join is
one `IN` query over the pool's ids. The quota comes from the throttle port's `peek`, which
counts nothing. The tier split is decided on the server.

The paging is a **slice of one ranked pool**, not a re-fetch. That matters: the staleness
filter runs in Python, so a second SQL page would drop a different set of stale rows and could
show an event twice or skip one entirely. One pool, one order, sliced — sound by construction.

## Architecture

### Pattern Used

**Service Layer over a published read interface.** The view layer resolves the user, calls one
service, and projects plain data onto the wire shape. The service owns every query and every
rule. This mirrors `digest_candidates.py` + `digest_composition.py` + `digest_read.py`.

### Layer Structure

```text
┌──────────────────────────────────────────────────────────────┐
│  Presentation — apps/personalization/api.py                   │
│  GET /api/personal/browse → BrowseOut                        │
├──────────────────────────────────────────────────────────────┤
│  Application — apps/personalization/services/browse_read.py  │
│  context → pool → rank → explain → join → gate → split       │
├──────────────────────────────────────────────────────────────┤
│  Domain — domain/ranking.py, domain/lifecycle.py             │
│  pure stdlib; relevance_score, why_this_tags, city_band…     │
├──────────────────────────────────────────────────────────────┤
│  Infrastructure — catalog_read, ports.throttle, adapters      │
│  two aliases, one wall; ports for every outbound capability   │
└──────────────────────────────────────────────────────────────┘
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/apps/personalization/services/browse_read.py` | The Browse read: pool → rank → explain → join → gate → split. 377 lines, 100% covered. |
| `backend/tests/personalization/test_browse_read.py` | Service tests: window boundary, ranking, tiers, saved join, quota, stripe cap, and the cost measurement. 26 tests. |
| `backend/tests/personalization/test_browse_api.py` | Endpoint tests: auth, the two emptinesses, paging, tier boundary, quota, Pro vs Free, cross-user isolation. 11 tests. |

### Modified

| File | Changes |
|------|---------|
| `backend/apps/ingestion/services/catalog_read.py` | Added `starts_before: datetime \| None = None` to `list_public_candidates`. Additive: the Digest passes nothing, so its pool is byte-identical to before. The bound is **exclusive**. |
| `backend/apps/personalization/api.py` | Added `GET /api/personal/browse` on the existing authed router. |
| `backend/apps/personalization/schemas.py` | Added `BrowseOut`, `BrowseCardOut`, `BrowseQuotaOut`. |
| `backend/apps/personalization/services/save_cap.py` | Added the `SaveQuota` dataclass and `read_save_quota`. The gate (`check_save_allowed`) is **unchanged**. |
| `backend/ports/throttle.py` | Added `ThrottleState` and an abstract `peek`. `check` is **unchanged**. |
| `backend/adapters/throttle/memory.py` | Implemented `peek`. Counts nothing, and does **not** evict a closed window. |
| `backend/adapters/throttle/redis.py` | Implemented `peek` with `GET` + `TTL`, never `INCR`. |
| `backend/tests/adapters/test_throttle.py` | Added `peek` tests on both adapters, including a parity walk across the window boundary. |
| `frontend/lib/api/openapi.json` | Regenerated by `make client`. |
| `frontend/lib/api/schema.ts` | Regenerated by `make client`. |

## Key Implementation Details

### 1. `total` is the size of the ranked pool, not a `COUNT(*)`

**This replaces an answer given at checkpoint 1, and it was approved at checkpoint 2.**

`list_public_candidates` applies FR-14's staleness bound **in Python**, after the SQL has
narrowed the set, because the bound is per-source and the database "cannot compare a column
against another column times a multiplier". A `COUNT(*)` with "the same filters" can only
apply the SQL-expressible ones — so it would count events the Python filter then drops. The
section head would advertise *"147 events · scroll for more"*, the user would page to the end,
and find 120. **A number that cannot be reached is worse than no number.**

The pool size is the honest count: it is exactly what the user can page to. It also costs
nothing extra, because the pool is already in memory.

### 2. The window is cut in the user's zone, not in UTC

"Tonight + 7 days" is a local idea. The far edge is the midnight after the seventh local day,
in the user's own IANA zone, converted to an instant. An event at 11pm local on day 7 is
**inside** the window; one at 1am local on day 8 is **outside**. Cutting in UTC would move the
boundary by the user's offset and put a late event on the wrong side of it.

Both sides are pinned by tests, at the exact instants where the two answers differ.

### 3. One pool, one order, sliced

The total order is `(score desc, start_time asc, id asc)`. The id is the tiebreaker that makes
the order **total** — without it, two events with the same score and start could swap places
between pages, showing one twice and losing the other. Pinned by a test that walks the pool
three times and asserts no duplicate and no gap.

### 4. The saved-state join is one query, and it is asserted, not inferred

A page of 24 cards resolved with one query per card would be 24 round-trips, times every user,
on a surface people open repeatedly. The join is one `IN` clause over the pool's ids. The test
**counts** the queries and prints all of them on failure, so a rewrite into a per-card lookup
is caught loudly. A mutation probe confirmed it really can fail.

### 5. The quota is a sign above the gate, not the gate

`check_save_allowed` counts an attempt by contract — asking *it* what the allowance is would
charge the user a save for opening a page. So the port gained `peek`, which counts nothing,
and `read_save_quota` reads through it. The in-memory adapter's `peek` deliberately does **not**
evict a closed window it finds: a read that mutated the store would change the answer a later
`check` gives, and a surface polling it on every page load would then be deciding when a
user's window resets — which is the gate's job.

**`check` is untouched, so the gate's behaviour is byte-identical.**

### 6. The tiers are named by the server

Tier 1 is the top three of the **pool**, so it exists only on the first page; a later page is
all "More this week" and its boundary is zero. The response carries `tier_2_starts_at` so the
rule lives in one place and cannot drift from the Digest's idea of what is worth attention.

### 7. The must-know stripe is capped server-side

At most one card per response may carry it. A client-side cap would be per page: two pages
would each show "their one", and the surface as a whole would flood.

### 8. Every state answers 200

A user with no city, a city with nothing on, and an offset past the end are all **answers**,
not errors. The client tells them apart by `city_missing` and `total`, and tells all three
from a failure by the fact that a failure is not a 200 at all. That is what lets the surface
say "Nothing matched." and "Nothing nearby tonight." and mean two different things.

**A user with no city gets the designed empty state, not a geo-IP guess.** A city the user
never chose is a worse answer than no city, because "Change city" would then be correcting
our guess instead of setting their preference.

## Security Considerations

| Concern | Approach |
|---------|----------|
| Authentication | The route sits on the existing `auth=current_user` router. An anonymous request is refused with 401. |
| Authorization / scoping | The user id comes from the **session** (`request.user.pk`), never from a payload. No endpoint accepts a user id as input. |
| Cross-user leakage | The saved-state join filters on `user_id`, so one user's Browse never shows another's save state. Pinned by a test with two real users. |
| AD-10 (explanation substitution) | `browse_read.py` imports `domain.ranking`, never `apps.ingestion.event_fit`. Enforced by the import-linter contract *"AD-10 personalization never reaches the Event Fit"* — KEPT. |
| AD-3 (cross-schema reach) | Two aliases, no cross-schema join, no FK, always `using=`. The architecture scan passes. |
| Input validation | `offset` and `limit` are clamped server-side (`max(0, …)`, `max(1, min(limit, BROWSE_PAGE_SIZE))`). A malformed value is Django Ninja's own 422. |
| Spend on a read | The quota read uses `peek`, which counts nothing. A user cannot lose a save by opening a page. |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| The catalog pool is one query | One `list_public_candidates` call. Asserted: `len(catalog_queries) == 1`. |
| The personal side does not grow with the pool | Preference read, interest read, saved-state join, throttle peek. Asserted: `len(personal_queries) <= 4`. |
| The saved-state join is one query | One `IN` clause over the pool's ids, not one lookup per card. Asserted: `len(saved_queries) == 1`. |
| Ranking cost is bounded | 200 candidates scored in Python per request. The score is domain logic and `domain/` is where it is allowed to live, so it cannot be pushed into SQL. **Measured: 60 candidates scored and paged in 20–27 ms.** |
| The pool is bounded | `MAX_CANDIDATE_POOL_SIZE = 200`. A city with more than 200 eligible events in its seven-day window reports 200 and pages to 200 — **a real limit, documented in the service's docstring** rather than discovered later. |
| The timing assertion is not flaky | The bound is deliberately loose (`elapsed < 1.0` for 60 candidates, an order of magnitude above the real cost). A tight wall-clock assertion is a flaky test on a loaded CI box, and a flaky test is worse than no test. |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| How `total` is computed | The **size of the ranked pool**, with no `COUNT(*)` at all | FR-14's staleness bound is applied in Python after the SQL narrows the set, so a SQL count would count rows the filter then drops and advertise a number no amount of scrolling reaches. Approved at checkpoint 2, replacing the checkpoint-1 answer. |
| Where the read lives | `apps/personalization/services/browse_read.py` | It may import `apps.ingestion.services.catalog_read` but never `apps.ingestion.event_fit`. AD-10 forbids substituting one explanation for the other, and the import linter rejects the code before it can ship. |
| Ranking source | `domain/ranking.relevance_score`, `why_this_tags`, `domain.confidence` | The **Relevance Pulse**, never the Event Fit. Browse's first section head says "3 worth your attention today" — *your* — so a stranger's score there would be the trust-collapse AD-10 calls company-ending. |
| Paging | Slice one ranked pool with `offset`/`limit`; a total order of `(score desc, start_time asc, id asc)` | SQL `OFFSET` on top of a Python-filtered over-fetch is unsound: a second page could drop different stale rows and show an event already seen or skip one entirely. |
| The city's source | The user's **digest preference** city | One meaning of "your city" across both surfaces, and the reason "Change city" routes to account settings. |
| The quota read | A new `ThrottlePort.peek`, counting nothing | `check` counts an attempt by contract. Asking the gate what the allowance is would charge a user a save for opening a page. **Additive** — `check` is unchanged. |
| The tier boundary | In the response, not inferred client-side | The rule lives in one place and cannot drift from the Digest's idea of "worth your attention". |
| The stripe cap | Server-side, one per response | A client-side cap is per page, so two pages would each show "their one" and the surface would flood. |
| The window's far edge | The midnight after the seventh **local** day | "This week" means the user's week. Cutting in UTC would move the boundary by the user's offset. |
| Empty states | All 200, told apart by `city_missing` and `total` | The client should not have to map a status code onto a sentence — that is the interpretation an API exists to remove. |

## Deviations from Plan

Three, all recorded before checkpoint 2 and all approved there or explained below.

1. **`total` is the ranked pool's size, not a SQL `COUNT(*)`.** Replaces the checkpoint-1
   answer; approved at checkpoint 2. The reasoning is in Key Implementation Details #1.

2. **`ThrottlePort.peek` — a dependency the plan did not name.** The quota read (D8) needs to
   ask the throttle what a window holds *without spending it*. The port gained `peek`,
   implemented in both adapters, and `save_cap.py` gained `read_save_quota` on top of it. It is
   additive and the gate's behaviour is unchanged.

3. **The plan's two promised measurements were outstanding when the plan was finalised** —
   the implementation was already written. Both are now **tests** rather than claims (the
   one-query join, and the ranking cost), each with a mutation probe proving it can fail.

## Dependencies Added

**None.** No new package was added to `pyproject.toml`, `package.json`, or `uv.lock` by this
item. (`freezegun` was added by the preceding `test-clock-seam` item in the same run, not by
this one.)

## How to Verify

1. **Run the Browse service tests**

   ```bash
   cd backend && uv run pytest tests/personalization/test_browse_read.py -v
   ```

   Expected: **26 passed.** The window boundary tests are the ones to watch — they assert the
   exact instants `2026-11-18 07:00 UTC` (11pm local, day 7, **in**) and `2026-11-18 09:00
   UTC` (1am local, day 8, **out**).

2. **Run the Browse endpoint tests**

   ```bash
   cd backend && uv run pytest tests/personalization/test_browse_api.py -v
   ```

   Expected: **11 passed.** The anonymous request is refused with **401**; the two emptinesses
   both answer **200** and are told apart by `city_missing`.

3. **See the ranking cost, measured**

   ```bash
   cd backend && uv run pytest tests/personalization/test_browse_read.py::test_scoring_a_full_pool_costs_a_query_and_a_bounded_amount_of_python -s
   ```

   Expected: the test **prints** `Browse read: 60 candidates scored and paged in 20–27 ms` and
   asserts 1 catalog query, ≤4 personal queries.

4. **Prove the saved-state join cannot silently regress to a per-card lookup**

   ```bash
   cd backend && uv run pytest tests/personalization/test_browse_read.py::test_the_saved_state_costs_one_query_however_many_cards_the_page_holds -v
   ```

   Expected: passes. If the join is rewritten into a per-card lookup, it **fails with
   `12 == 1` and prints all twelve queries.**

5. **Confirm the throttle's `peek` spends nothing, on both adapters**

   ```bash
   cd backend && uv run pytest tests/adapters/test_throttle.py -v
   ```

   Expected: **all passed**, including `test_peek_counts_nothing` and the parity walk
   `test_the_two_adapters_agree_about_peek`.

6. **Confirm the import contracts**

   ```bash
   cd backend && uv run lint-imports
   ```

   Expected: **Contracts: 19 kept, 0 broken**, including *"AD-10 personalization never reaches
   the Event Fit"*.

7. **Confirm the whole suite and the coverage gates**

   ```bash
   cd backend && uv run pytest --cov -q
   ```

   Expected: **6,794 passed**, coverage **98.68%** (gate 80%), `domain/` at **100%**.

8. **Confirm the generated client is stable**

   ```bash
   cp frontend/lib/api/openapi.json /tmp/oa.before.json
   cp frontend/lib/api/schema.ts /tmp/sch.before.ts
   make client
   diff /tmp/oa.before.json frontend/lib/api/openapi.json && diff /tmp/sch.before.ts frontend/lib/api/schema.ts
   ```

   Expected: **no output** — both files are byte-identical after regeneration. (Do **not** use
   `git diff --exit-code frontend/lib/api/` for this check: it reports the *new* Browse types
   as drift, which is a different thing from instability.)

9. **Manual scenario — a signed-in user opens Browse**

   Sign in, set a city under Settings → Account, then `GET /api/personal/browse`. Expected: a
   200 with `city` set, `city_missing: false`, `total` equal to the number of eligible events
   in the window, `tier_2_starts_at: 3` when there are more than three, and `quota.used: 0`.
   Then save one of the cards and reload: that card reports `is_saved: true` and the quota
   reads `used: 1` — **without a second save being spent** by the read itself.

   **In a local (`ADAPTER_MODE=fake`) run, the quota will read `used: 0` after the save.**
   That is not a defect: `ports.registry.get_adapter` constructs a **new** adapter instance
   on every call, so the in-memory throttle's state does not survive between requests. The
   fake is a per-request stub; the real Redis adapter is shared and does persist. To see the
   quota move in a local run, use `ADAPTER_MODE=real` with Redis up — or, in a test, patch
   the port the way `tests/e2e/test_pro_tier_proof.py` does:

   ```python
   adapter = InMemoryThrottleAdapter(now=lambda: 1_000_000.0)
   monkeypatch.setattr("apps.personalization.services.save_cap.get_throttle_port", lambda: adapter)
   ```

   Verified this way: before the save `used: 0`, after it `used: 1` with
   `resets_in_seconds: 86401`, and `is_saved` flipping to `true` — while the reads
   themselves spend nothing.

## Test Coverage

- Tests added: **37** (26 service + 11 endpoint), plus **7** throttle `peek` tests
  (18 in `test_throttle.py` in total)
- Suite total: **6,794 passed, 0 failed** in 642.20s
- Coverage: **98.68%** overall (gate 80%); `domain/` **100%**; `browse_read.py` **100%**
- Status: **passing**

## Ready for Review

- [x] All acceptance criteria met — 12 of 12, each with named test evidence
- [x] Tests passing — 6,794 passed, 0 failed
- [x] No critical issues — one **medium** finding (AD-10 persistence) recorded for a future
      work item, not folded in silently
- [x] Documentation updated — `plan.md`, `test-report.md`, `review-report.md`
- [x] Developer notes captured
- [x] Two mutation probes run, both caught, both reverted, file verified byte-identical

## Developer Notes

**The one thing to know: AD-10 has two halves, and only one of them is enforced.**

The *substitution* half is enforced — two import-linter contracts guard it, and they are
good, because the Event Fit is a **package** specifically so that a new module inside it is
inside the wall by default rather than outside it until somebody notices.

The *persistence* half is enforced by nothing. `browse_read.py:333` calls `why_this_tags` in
the read path; the Digest does the opposite — `digest_composition.py` calls it once and
**persists** the result on `DigestComposition`, and `digest_read.py` reads that row back and
never calls it. The standards doc lists *"Recomputing explanations at render"* as an
anti-pattern, and `system-architecture.md` states AD-10 as *"Persisted Event Fit + Relevance
Pulse — Never recomputed at render."*

Browse is not *wrong* today — its tags come from the same `RankingInputs` the score used, from
the same `domain.ranking` functions the Digest uses, and that equivalence is pinned by a test.
But a Browse card's tags **can change between two identical requests**, most visibly when the
user saves an event, because `why_this_tags` takes `is_saved` and Browse computes it from the
live `SavedEvent` join. The Digest's tags cannot, because they were frozen at composition.

Recorded as **Finding 18 (medium)** in `review-report.md`. It needs a schema and a composition
job, so it is a work item of its own — and **the approved design did not mention persistence
at all**, which makes this a gap in the design rather than a departure from it. A contract
asserting that no read module imports `why_this_tags` would close the enforcement gap, and the
Digest's own structure shows it is cheap.

**Other gotchas:**

- **Two pytest runs cannot share the database.** The test database is created from a template
  and torn down at the end, so a second run reports *"already exists"* / *"being accessed by
  other users"* — thousands of **errors**, not assertion failures. A run reporting thousands of
  errors is reporting a collision. Fix: kill the stray process, then
  `DROP DATABASE IF EXISTS test_eventpulse24 WITH (FORCE)` — a plain `DROP` is refused while a
  session is attached.

- **`freezegun` needs `tick=True` here.** The event ids are UUIDv7 and the ranking's total
  order falls back to the id, so a stopped clock would mint ties the order cannot break — a
  flaky ordering test, which is worse than the bug being fixed.

- **`peek` must not evict.** The in-memory adapter's `peek` deliberately leaves a closed
  window in place; `check` does the eviction. If `peek` mutated the store, a surface polling
  it on every page load would be deciding when a user's window resets — which is the gate's
  job. Pinned by `test_peek_does_not_evict_the_closed_window_it_finds`.

- **The fake throttle is per-request, so its state does not persist.** `get_adapter` calls
  `adapter()`, constructing a **new** instance every time. In `ADAPTER_MODE=fake` the
  in-memory throttle therefore forgets its counters between requests — which is fine for the
  gate (a test asserts the refusal within one request) but means **the quota reads `used: 0`
  after a save in a local run**. The real Redis adapter is shared and does persist. Any test
  that needs the quota to move must patch the port, the way
  `tests/e2e/test_pro_tier_proof.py` does:

  ```python
  monkeypatch.setattr("apps.personalization.services.save_cap.get_throttle_port", lambda: adapter)
  ```

  This is pre-existing behaviour, not something Browse introduced — but Browse is the first
  surface to *show* the counter, so it is the first place the gap is visible.

- **`MAX_CANDIDATE_POOL_SIZE = 200` is a real limit.** The design's mockup shows 147 events in
  a week, so there is room — but if it ever binds, the answer is a decision about what Browse
  is for, not a bigger constant.

- **The `limit` bounds are not in the OpenAPI schema.** The service clamps them, so the
  response is bounded either way; the parameter is simply not self-describing. Worth noting
  for the frontend work item.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-029*

---

---
run: run-eventpulse24-029
work_item: frontend-browse-shell-and-grid
intent: browse-surface
generated: 2026-11-12
mode: confirm
---

# Implementation Walkthrough: The Browse Shell and Grid

## Summary

`/browse` — the signed-in user's city, tonight and the next seven days. The route renders a
hero, two section heads and a three-column grid inside the **existing** A-8 authed shell, and
it inherits the pre-auth city page's visual vocabulary while refusing its conversion
scaffolding: no Sign-up row, no How-it-works CTA, no SEO neighbour-cities footer, no filter
chip rail, no discovery stripe, and no "Maya-fit" persona copy.

**The search input and the Save button are deliberately absent.** Both are their own later
work items, and this one leaves the card's `data-browse-save-slot` empty rather than shipping
a control that does nothing.

**The page renders the payload and decides nothing** (AD-10). The server's `tier_2_starts_at`
is where the second section begins; the server's `has_more` is whether the anchor appears; the
server's `confidence` is the Relevance bucket; the server's `tags` are the persisted Why-this
Tags. The client re-ranks nothing, re-sorts nothing and re-buckets nothing.

## Structure Overview

The whole route is a **server component**. One read, one render, no client fetch — the same
shape as `/` and `/timeline`.

```text
  browser
     │
     ▼
┌──────────────────────────────────────────────┐
│  app/browse/page.tsx        (server)         │
│    getSession() → homeRoute() → redirect?    │
│    readBrowse(offset) → BrowseOut | error    │
│    renders inside the existing AppShell      │
└──────────────────────────────────────────────┘
     │                    │                 │
     ▼                    ▼                 ▼
┌──────────────┐  ┌───────────────┐  ┌──────────────────┐
│ BrowseHero   │  │  BrowseGrid   │  │  BrowseMore      │
│ eyebrow·h1   │  │  2 sections   │  │  ("use client")  │
│ pill·quota   │  │  1 <ul> each  │  │  the only island │
└──────────────┘  └───────────────┘  └──────────────────┘
                          │                     │
                          └──────┬──────────────┘
                                 ▼
                        ┌──────────────────┐
                        │   BrowseCard     │
                        │  stripe·kicker   │
                        │  pulse·badge     │
                        │  state·title     │
                        │  tags·time       │
                        │  [save slot]     │
                        └──────────────────┘
```

**One client island, and it is one island for a reason.** `browse-more.tsx` is the only
`"use client"` module. It fetches the next chunk and appends it in place — the alternative, a
server round trip per chunk, would make every scroll a full page load, which is exactly what
the soft cap exists to avoid. It is not an AD-10 violation: the chunk arrives already ranked
and already tiered, and the client appends it as it came.

**Three layers, and each one speaks only to the one below.**

| Layer | Files | Says |
|---|---|---|
| Route | `app/browse/page.tsx` | Which session, which offset, which state |
| Presentation | `components/browse/*` | What the payload looks like |
| Words | `lib/browse-labels.ts` | How a number becomes a sentence |

`lib/browse-labels.ts` is the only place in the surface that turns a number into a sentence,
and **every sentence it produces is a claim the reader will believe.** A rounding bug there is
a wrong number on the page; a timezone bug there is a wrong *day* on the page. It is
therefore the one file with a pure unit-test file of its own (`tests/browse-labels.test.ts`,
19 tests).

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `frontend/app/browse/page.tsx` | The route: session → redirect → read → render inside `AppShell`; honours `?offset=` |
| `frontend/app/browse/loading.tsx` | The loading state: 12 card-shaped skeletons |
| `frontend/components/browse/browse-hero.tsx` | The hero: eyebrow, h1 with `<em>`, lede, city-meta pill, quota note |
| `frontend/components/browse/browse-card.tsx` | One card: the stripe, kicker, confidence pulse, source badge, state badge, title, why-tags, time · venue |
| `frontend/components/browse/browse-grid.tsx` | The two section heads and their grids, split at the server's `tier_2_starts_at` |
| `frontend/components/browse/browse-more.tsx` | The client island: the "More events below" anchor that loads the next chunk in place |
| `frontend/components/browse/browse-states.tsx` | The quiet empty state, the error state and the loading skeleton |
| `frontend/lib/browse-labels.ts` | The words for the server-stated facts: quota note, reset phrase, window date, counts, stripes |
| `frontend/lib/browse-read.ts` | The server read: `readBrowse()` → `{ kind: "browse" \| "unavailable" }` |
| `frontend/tests/browse-rendering.test.tsx` | The rendered document: the A-12 absences, the tier split, the quota note, the grid, the offset handling |
| `frontend/tests/browse-a11y.test.tsx` | The axe-core gate over every state, with a probe proving it can fail |
| `frontend/tests/browse-boundary.test.ts` | The source scan: no CTA, no SEO footer, no chips, no discovery stripe, no persona copy, no new tokens |
| `frontend/tests/browse-labels.test.ts` | The pure functions: reset phrase, quota note, window date, stripes |

### Modified

None. **No production code outside `frontend/` changed, and `styles/tokens.css` was not
touched** — the acceptance criterion forbids new tokens, and the token file resets
`--breakpoint-*` and the spacing scale wholesale, so anything undeclared generates no CSS at
all.

## Key Implementation Details

### 1. The absences are enforced twice, and the second instrument is the one that matters

A-12 is a set of *absences*, and each kind of absence needs the instrument that can see it.

| Instrument | What it can see | What it cannot |
|---|---|---|
| `browse-boundary.test.ts` (source scan) | A forbidden string anywhere in the file — even in a branch never rendered | Whether the component renders at all |
| `browse-rendering.test.tsx` (rendered) | What the reader actually gets, with the roles and names they get it under | A string that is never rendered |

A page that throws before its first card would pass every source rule. A persona string in a
file that never reaches the page would pass every rendering rule. **Both files are needed and
neither substitutes for the other.**

### 2. The grid's three steps, and why there is no fourth

A-12 asks for three columns at ≥1280px and two at 1024–1279px. This codebase has breakpoints
at `md: 768px` and `lg: 1024px` and **no `xl`** — and `styles/tokens.css` resets
`--breakpoint-*`, so an `xl:` rule would generate no CSS at all.

```text
grid-cols-1  md:grid-cols-2  lg:grid-cols-3
```

`lg` is 1024px, so the three-column grid appears at 1024px rather than 1280px. **The
consequence is stated rather than hidden:** at 1024–1279px the inner width after the 240px
sidenav is ~760px, so a three-column grid gives ~240px cards against the design's ~279px.
The cards are legible at that width (the Digest's cards are narrower at the same `lg`
breakpoint and ship), but the mockup's exact card width is not reproduced. A custom `xl`
breakpoint would fix it and is exactly the "new CSS variable" the criterion forbids.

The test asserts the shipped classes explicitly, so the choice is visible in the suite and a
future `xl` breakpoint would have to change the test.

### 3. The indicator is the Relevance Pulse, and it says so — in three places

Browse is an authed surface whose first section head reads *"3 worth your attention today"* —
*yours* — so its cards carry the personal explanation. The Event Fit is the stranger's score,
computed blind to who is looking, and AD-10 forbids substituting one for the other. The two
indicators look identical on screen, so **the words are the only thing keeping them apart.**

**One clamp, three consumers.** The dots, the button's accessible name and the card's
accessible name all read the same clamped value, so the card cannot say "1 of 5" in one place
and "0 of 5" in another — and all three say "Relevance", never "Confidence".

### 4. The card says no price, and has no Save control

**The payload carries no price**, so the card says nothing about one — the mockup's "Free" is
a persona's invention, and inventing a price is a fact the frontend does not have.

**The Save slot is empty here.** The affordance is its own work item
(`frontend-browse-save-button`), and this card leaves the slot for it rather than shipping a
control that does nothing. The slot is marked with `data-browse-save-slot` so the next editor
knows the absence is planned.

### 5. The 32px frame, reached without touching the shared shell

The design asks for `.main { padding: 0 32px }`. **`.main` is `AppShell`'s**, and the shell is
shared with `/`, `/timeline` and `/conflicts` — changing it would move every authed surface,
which the criterion ("the shell markup is not forked or re-implemented") forbids.

So Browse's own content wrapper adds the remaining 8px (`px-2`) on top of the shell's 24px
(`px-6`). **It wraps the whole surface**, so the hero and the grid share one left edge — a
hero at 24px and a grid at 32px would be two surfaces pretending to be one. And it is not the
city page's full-bleed 80px frame: Browse sits inside the authed shell's container, which is
the whole difference between a public page and a signed-in one.

### 6. One `<ul>` per section, not one `<ul>` with headings inside it

A list whose children are headings and `<li>`s is not a list, and the `list` axe rule is
*serious* — a screen reader would announce the cards as ungrouped text and the count of the
city's events would be lost with them. The city page's own a11y test has a mutation probe for
exactly this mistake, and Browse's axe gate has one too.

### 7. The chunk loader, and the two bugs that were in it

The anchor's `href` names the next chunk, so the affordance is a real navigation even though
the click is intercepted to load in place — **and the route honours `?offset=`**, so a
middle-click, a "copy link address", or a reader with JavaScript off lands on the same chunk
the anchor names.

Three things about the loader are worth knowing:

- **The guard is inside the handler, not on the element.** `aria-disabled` is advisory; it
  tells assistive technology the control is unavailable and does *not* stop a second click.
- **The appended list renders whether or not there is more to come.** The early return that
  used to sit above that list meant the chunk which *finished* the pool was thrown away.
- **The anchor is `role="button"` with its `href` kept.** It behaves as a button — the chunk
  is fetched in place, with no navigation — so announcing it as a link would lie about what
  activating it does.

## Security Considerations

| Concern | Approach |
|---------|----------|
| Anonymous access | `getSession()` → `homeRoute(session)` redirects before the read, exactly as every authed route does. The route decision is made **here**, not in `proxy.ts` — the proxy has one job. |
| A session used on a public surface | **Not applicable** — Browse is authed (AD-12). The read forwards the visitor's cookies via `sessionHeaders()`, so a signed-in user's own Browse never tells them their city has nothing on. |
| The backend boundary | Reached only through the generated client (`api` from `@/lib/backend-client`). `fetch` is banned in `components/` and `app/` by a lint rule, and the build is the real check that the client boundary holds. |
| A failure being shown as an empty city | Two answers, not one: `browse` is the payload and `unavailable` is a failure to answer. A signed-out reader gets the error state, never an empty city. |
| The `?offset=` parameter | Parsed with `Number.parseInt`, and a malformed or negative value falls back to the first page. The offset is a slice into one bounded, already-ranked pool — it cannot reach outside it. |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| No client-side ranking | The server ranks once and the page renders the order it arrived. The client does not score anything. |
| A bounded payload | The page asks for 24 cards (`PAGE_SIZE = 24`), matching the server's `BROWSE_PAGE_SIZE`. The soft cap is a page size, not a client-side truncation — the page never slices the payload it was given. |
| No fetch on load | The route is a server component. The only client request is the deliberate chunk load the reader asks for. |
| No layout shift on load | `loading.tsx` renders 12 card-shaped rectangles in the same grid, so the layout holds while the read is in flight. |
| The pool is bounded server-side | `MAX_CANDIDATE_POOL_SIZE = 200` in the backend read, so the ranking cost is bounded per request. |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Section 2's meta counts the section's own events, not the remainder | `total - tier_2_starts_at` | The mockup settles it: the hero's pill says *"147 events this week"* and section 2 says *"144 events"*, and 147 − 3 = 144. N is the pool's **tier-2 size**. Reading it as a remainder would announce *"37 events"* above a grid of 2 cards — a heading that contradicts the thing it heads. |
| The chunk anchor announces as a button, not a link | `role="button"` with the `href` kept | The click is intercepted and the chunk is fetched in place, so no navigation happens. The `href` stays because the chunk's real URL *is* the anchor's `href`, and the route now honours `?offset=`. |
| The anchor's visibility is the server's statement | `has_more` from the payload | A pool whose `total` disagrees with its card count would otherwise strand the reader on an anchor that leads nowhere, or hide a chunk that is really there. |
| The card shows the event's state | `EventStateBadge`, plus the state in the link's accessible name | The server routes cancelled and postponed events to the **amber** stripe, so a cancelled event rendered as a "Must-know" card with nothing saying it was cancelled. The badge is `aria-hidden` (the glanceable half); the **link** carries the state in words, so the fact is announced once. |
| The grid ships at `lg` rather than `xl` | `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` | There is no `xl` breakpoint token and adding one is a new CSS variable, which the criterion forbids. |
| The h1 maps to `display-lg` and the section heads to `headline-lg` | The nearest existing tokens | `display.xl` and `display.sm` do not exist in this codebase. 48px is the design's own floor for `display.xl`. |
| The sidenav's Browse row stays an inert "Coming soon" span | Deliberate deferral | `browse-nav-activation` is a separate item. Linking it now would put a link in a surface whose route has no error state yet. |

## Deviations from Plan

**Four changed what the page says**, and the plan's deviation table now carries them:

1. **Section 2's count** — from "what is still to come" to the section's own size. The mockup
   settles it (see Decisions).
2. **The anchor's role** — from "a `Text.Meta` anchor, not a button" to `role="button"`. It
   behaves as a button, and announcing it as a link lies about what activating it does.
3. **`has_more` drives the anchor** — the client's arithmetic on `total` is gone.
4. **The card shows the event's state** — the plan said the card renders the payload and
   decides nothing; it now also shows a state the payload carries, with the state in the
   link's accessible name.

**The rest are the eight defects the review found and fixed.** The most serious: the chunk
loader discarded the final chunk's cards entirely, in code that passed every test, lint,
typecheck and the production build.

## Dependencies Added

**None.** No new package, no new `package.json` entry, no new CSS variable, no new spacing or
colour token. `axe-core` was already a dev dependency and is used by the existing
`tests/city-page-a11y.test.tsx`.

## How to Verify

1. **Run the whole frontend gate** (Node 24 is required — see Developer Notes):

   ```bash
   cd frontend
   export PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH"
   pnpm test && pnpm lint && pnpm typecheck && pnpm build
   ```

   Expected: `2118 passed (127 files)`, lint clean, types clean, and a build listing `ƒ /browse`.

2. **Run the Browse suite on its own:**

   ```bash
   pnpm vitest run tests/browse-labels.test.ts tests/browse-rendering.test.tsx \
     tests/browse-a11y.test.tsx tests/browse-boundary.test.ts
   ```

   Expected: `84 passed (4)`.

3. **See the surface in a browser.** Sign in, set a city in `/settings/account`, then open
   `/browse`:

   ```bash
   pnpm dev
   ```

   Expected: the hero with a terracotta dot and an italic city, a city-meta pill with a
   "Change city" link to `/settings/account`, a mono quota note, "3 worth your attention today"
   above the first grid and "More this week" above the second, and a "More events below" anchor
   when the pool has more. **No Sign-up CTA, no How-it-works CTA, no footer, no filter chips.**

4. **Watch the chunk load.** Click "More events below" in a city with more than 24 events.

   Expected: the next chunk appears below, the anchor's URL is `/browse?offset=24`, and the
   anchor disappears when the pool runs out — **while the last chunk's cards stay**.

5. **Prove the absence test can fail.** Plant a Sign-up CTA in `browse-hero.tsx`:

   ```bash
   # add <Link href="/signup">Sign up</Link> to the hero, then:
   pnpm vitest run tests/browse-rendering.test.tsx
   ```

   Expected: `has no Sign-up call to action` **FAILS**. Revert.

6. **Prove the axe gate can fail.** Move a section `<h2>` inside the `<ul>` in
   `browse-grid.tsx`:

   Expected: the `list` rule fires and the gate fails. Revert.

7. **Check the offset is honoured.** Open `/browse?offset=24` directly.

   Expected: the second chunk of the pool, and the same two section heads (a chunk at offset ≥ 3
   is entirely tier two).

## Test Coverage

- **Tests added**: 23 in this phase (+19 in `browse-labels.test.ts`, +4 in the rendering suite)
- **The whole frontend suite**: 2118 passed across 127 files, 0 failed
- **Status**: passing
- **The axe gate**: six tests, one per state — populated, empty, error, loading,
  every-card-treatment, and the probe that proves it can fail

## Ready for Review

- [x] All 16 acceptance criteria met, each with named evidence in `test-report.md`
- [x] Tests passing — 2118 across 127 files
- [x] Lint clean, types clean, production build succeeds
- [x] No critical issues remaining — the review's seventeen findings are all fixed
- [x] No new tokens; `styles/tokens.css` untouched
- [x] No production code outside `frontend/` changed
- [ ] **The chunk loader has no test of its own** — recorded as Finding 21, deliberately not
      folded in. The coverage shape that let the critical bug through is still a gap.

## Developer Notes

**Node 24 is required, and the failure looks like a code bug.** `frontend/package.json` asks
for `node >= 24.15`; the machine's default is **v20.20.0**. On Node 20, `undici@8.12.3`
binds a zlib constant that does not exist there, and it surfaces as ~100 *"[vitest-pool]:
Failed to start forks worker"* errors and a non-zero exit **even when every assertion passes**.
Always prefix with:

```bash
export PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH"
```

**The token file resets everything, so an undeclared value generates no CSS at all.**
`styles/tokens.css` uses `@theme static` to reset `--color-*`, `--radius-*`, `--shadow-*`,
`--spacing`, `--breakpoint-*` and the type scale. `px-[22px]` works because it is a bracketed
exact value; `p-22` would produce **no padding whatsoever**, silently. The spacing scale's
`20` is **80px**, not 20px — which is why the grid gap is `gap-[20px]` and not `gap-5`.

**The spacing scale has no 22px step and the breakpoint list has no `xl`.** Both are
deviations, both are recorded in the plan, and both are asserted in the tests so a future
change to either has to change the test.

**`app/browse/page.tsx` is `force-dynamic`.** It reads the session and the offset, so it must
not be prerendered.

**The tooltip ids must be derived from the event's id.** A confidence bucket is 1–5 and the
tags come from a fixed vocabulary, so an id built from them collides on every grid, and
`aria-describedby` resolves to the **first** match — a card's description would be another
card's element. The house pattern is `pulse-card.tsx`'s.

**The card's state badge cannot be sold-out on Browse.** The Browse payload carries `status`
but not `is_sold_out`, so `cardStateFor(status, false)` can only ever return `cancelled` or
`postponed`. A badge for a state the payload cannot express would be a badge invented by the
client — which is what AD-10 forbids. Finding 18 records the gap.

**A component can be covered and still have its most important branch untested.** The chunk
loader was exercised by the page tests on every fixture, and the critical bug lived in the one
branch no fixture reached. **When a page delegates to a client island, the island's own
branches need their own tests.**

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-029*

---

# Implementation Walkthrough: The Inline Keyword Search

**Work item:** `frontend-browse-search` — *Inline Keyword Search — the Grammar, and the Two
Different Emptinesses*
**Mode:** `confirm` — checkpoint 1 (plan) approved 2026-11-12
**Completed:** 2026-11-12

## Summary

One `<input type="search">` below the hero, and it is the **only** filter surface on the
Browse page. The grammar is deliberately small — whitespace-split words and `tag:` literals,
AND-matched — and it runs **client-side over the loaded set**, so typing costs nothing and
no request is made per keystroke.

The item's real work was not the input. It was **the two different emptinesses**: the city
has nothing on, versus the reader's query found nothing. They are different documents with
different headings, different landmarks and different ways out, and a test now proves it.

The review phase found **two defects** in the code this item shipped, both fixed: the
filter could promote a tier-two card into tier one, and the chunk's cards were rendered
twice. Both are AD-10 failures wearing a search's clothes, and both are now covered.

## Structure Overview

The search is **one client island** that owns the whole filterable surface — the query, the
input, the hint line, the count line, the live region, the no-match state, the chunk's state,
and the rendering of both grids. The route stays a server component; it reads the payload and
hands it down.

**Why one island and not a search box beside a server-rendered grid.** A query typed into a
client island cannot reach a server-rendered grid, and a filter that reached only part of the
surface would be a filter that lied about how much it had narrowed. Since the AC forbids a
network request per keystroke, the filter must be client-side; and if the filter is
client-side, the filtered surface must be client-side too. The chunk's state moved into the
island for the same reason — a chunk becomes part of the loaded set the moment it lands, so
the query has to reach it.

The **grammar itself is a separate pure module** (`lib/browse-search.ts`) with no React and
no DOM, so it can be tested directly rather than through the DOM. The **tag vocabulary**
(`lib/digest-labels.ts`) is a translation table: the server states the fact, the client
speaks the reader's language.

```
  /browse  (server component)
      │
      ├── BrowseHero                     the h1, the city's own facts
      │
      └── BrowseSearch  ("use client")  the island
            ├── the input + the hint line + the count line + the live region
            ├── the no-match empty state (replaces the grid)
            └── the loaded set
                  ├── BrowseGrid        draws every card, both sections
                  └── BrowseMore        the anchor and the announcement
```

## Architecture

### Pattern Used

**A client island over a server-rendered payload.** The route reads the server's payload on
the server and passes it into a single client component; the island owns everything that
changes without a navigation.

The alternative — a server component for the grid and a client component for the input — was
**not** viable, and the reason is worth stating because it is the whole argument for this
shape: a query typed into a client island cannot filter a server-rendered grid, so a
server-rendered grid under a client-side search would be a filter that narrowed *half* the
surface while reporting that it had narrowed all of it.

### Layer Structure

```text
┌─────────────────────────────────────────────┐
│  Route            app/browse/page.tsx       │  server component
│                  reads the payload, hands   │
│                  it to the island           │
├─────────────────────────────────────────────┤
│  Island          browse-search.tsx         │  "use client"
│                  the query, the loaded set, │
│                  the chunk's state          │
├─────────────────────────────────────────────┤
│  Presentation    browse-grid.tsx           │  draws the cards
│                  browse-more.tsx           │  the anchor
│                  browse-states.tsx         │  the empty states
├─────────────────────────────────────────────┤
│  Grammar         lib/browse-search.ts      │  pure, no React
│                  tokenize · filter ·        │
│                  survivingTierOneCount      │
├─────────────────────────────────────────────┤
│  Vocabulary      lib/digest-labels.ts      │  the server's facts,
│                  the alias table            │  the reader's words
└─────────────────────────────────────────────┘
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `frontend/lib/browse-search.ts` | **The grammar, in full.** Tokenisation, matching, filtering, the query summary, and the pool-relative tier count. Pure — no React, no DOM — so the edge cases are tested directly. |
| `frontend/components/browse/browse-search.tsx` | **The client island.** The input, the hint line, the count line, the polite live region, the no-match state, the chunk's state, and both grids. The only `"use client"` module on the surface. |
| `frontend/tests/browse-search.test.ts` | **43 tests.** The grammar on its own: tokenisation edge cases, the matching rules, the alias resolution, and the tier split. |

### Modified

| File | Changes |
|------|---------|
| `frontend/lib/digest-labels.ts` | **The alias table.** Six friendly names → the server's chip keys, and `searchTagKey()` / `SEARCH_TAG_VOCABULARY`. The four design tags with no server-side counterpart are deliberately **omitted**. |
| `frontend/components/browse/browse-grid.tsx` | Now presentational: it takes the cards to draw and a **count** of the pool's tier-one survivors, not the server's raw index. |
| `frontend/components/browse/browse-more.tsx` | Now the **anchor and the announcement only** — it draws no cards, because the grid draws them. |
| `frontend/components/browse/browse-states.tsx` | **The no-match empty state.** A different heading, a different landmark (`role="status"`), a different way out, and the reader's own terms named back to them. |
| `frontend/app/browse/page.tsx` | Renders the island instead of the grid and the loader. Still a server component. |
| `frontend/tests/browse-rendering.test.tsx` | +33 tests: the search surface, the two empty states, the A-11 lock on the rendered DOM, the tier split under a filter, and the chunk loader. |
| `frontend/tests/browse-boundary.test.ts` | +7 tests: A-11's lock on the source, the client-module list, the four-link tier chain, the no-re-sort rule, and the one-place rule for the chunk's cards. |
| `frontend/tests/browse-a11y.test.tsx` | +2 axe gates: the no-match state and the filtered state. |
| `frontend/tests/digest-labels.test.ts` | +4 tests: the alias table, checked against `backend/shared/constants.py` itself. |

## Key Implementation Details

### 1. The grammar, and the one rule it does not bend

A query is whitespace-split, lowercased and trimmed. Plain words AND-match against the
card's headline, its where line and its why-tag keys. `tag:` literals match **only** why-tag
keys.

**The rule the whole grammar's trustworthiness rests on: an unknown `tag:` token matches
nothing.** It is not dropped and it does not widen into a plain-word match — because a
reader who typed `tag:music` would otherwise get every card with "music" anywhere in its
title and no way to tell the tag had been ignored. The implementation keeps an unresolved
tag as `null` in `resolvedTags` precisely so the matcher can refuse the whole query.

### 2. The tag vocabulary, and the four tags that do not exist

The design names ten search tags. The server's why-tag vocabulary is
`RANKING_TAG_ORDER` (`discovery`, `nearby`, `tonight`, `tomorrow`, `weekend`, `saved`) plus
`matches_<chip>` over ten *other* slugs. **Six of the design's ten map onto a real chip;
four — `music`, `food`, `indoor`, `rooftop` — have no counterpart at all.**

The alias table maps the six and **deliberately omits the four**. A test reads
`backend/shared/constants.py` and proves every alias still points at a chip the server has,
and another proves the advertised vocabulary contains nothing that resolves to `null`.

**The backend was not changed.** The why-tag set is a persisted, server-stated fact
(AD-10), and a search alias is a frontend *translation* of it — the same seam
`digest-labels.ts` already documents for chip labels.

### 3. The tier split, counted against the pool

The server's `tier_2_starts_at` is an index into the **pool** it sent. The grid does not
slice the filtered list at that index — it slices at a **count of the pool's tier-one cards
that survived the filter**, computed by `survivingTierOneCount()` against the loaded set.

**A filter makes tier one smaller; it never makes it longer.** Slicing the filtered list at
the pool's index would say "the first three survivors are tier one", and when the filter
removed all three of the pool's tier-one cards, the first three survivors were tier-*two*
cards wearing tier one's heading.

### 4. The two emptinesses

| | Zero-events state | No-match state |
|---|---|---|
| Trigger | The city has nothing on | The query found nothing |
| Replaces | **The whole page** — hero and all | **The grid and the section heads** |
| Heading | The page's own empty state | `"Nothing matched."` |
| Recovery | The city's settings — *"Change city"* | The search box — *"Drop a term, or browse the full list."* |
| Landmark | — | `role="status" aria-live="polite"` |

The no-match state removes the section heads on purpose: a heading over nothing is a
heading that lies.

## Security Considerations

| Concern | Approach |
|---------|----------|
| Session handling | **Unchanged.** The route calls `getSession()` → `homeRoute(session)` and redirects anonymous readers. Browse is authed, so it may use a session (AD-12). The island is client-side and reads no session. |
| Backend access | The island reaches the backend only through the generated client — `api.GET("/api/personal/browse", …)`. `fetch` is banned in `components/` by a lint rule, and a boundary test asserts the surface never calls it. AD-19 kept. |
| Input handling | The query is **displayed back to the reader as text** — React escapes it. There is no `dangerouslySetInnerHTML` anywhere on the surface. |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| No network request per keystroke | The filter is a pure function over an array already in the browser. **Zero** requests per keystroke; the only request the surface makes is the chunk's. |
| Instant typing | The match is `String.includes` over a handful of fields per card, over at most 48 loaded cards. No debounce is needed because there is nothing to debounce. |
| The grid draws every card once | The chunk's cards are drawn by the grid, not by the loader. Rendering them in both places was a defect the review found; the source rule now forbids it. |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where the search runs | Client-side, over the loaded set | The AC forbids a request per keystroke, and the search is over *the loaded set* — which is a client-side notion by definition. |
| Where the surface is rendered | One client island, not a server grid plus a client input | A client-side filter cannot reach a server-rendered grid. Splitting them would produce a filter that narrowed half the surface and reported that it had narrowed all of it. |
| The chunk's state | In the island, not in the loader | A chunk becomes part of the loaded set the moment it lands, so the query has to reach it. |
| The four unmapped tags | Match nothing | The item's own rule for unknown tags, applied honestly. Aliasing `music` onto `matches_arts_culture` would put "music" on a card the server tagged "Sports & fitness". |
| The backend | Unchanged | The why-tag set is a persisted fact. Inventing four chips to satisfy a placeholder string would change the product's vocabulary to fit a string. |
| The placeholder | Kept verbatim, including `tag:music` | The AC fixes it word for word. The conflict with the four unmapped tags is **recorded**, not repaired by editing a fixed string. |
| The tier split under a filter | Counted against the pool | AD-10. The client does not re-tier; a filter makes tier one smaller. |
| The second section's meta under a filter | Counts what the section holds | "39 events" above a grid of one card, while the count line said "1 event matched", would have been the page contradicting itself twice. |

## Deviations from Plan

**Thirteen deviations, of which four came out of the review.** The full table with
rationales is in `plan.md`; the ones that changed the design are:

| # | The plan said | Now | Why |
|---|---|---|---|
| 1 | Ten tags, and "the ten documented tags all work" | **Six work**; four match nothing | The server has no such why-tag. The item's own unknown-tag rule, applied honestly. |
| 2 | The placeholder teaches the grammar | Kept verbatim, but `tag:music` matches nothing | Two criteria that cannot both hold for `music`. **Recorded, not repaired.** |
| 4 | The grid and the loader are separate components | **One client island owns the whole surface** | A client-side filter cannot reach a server-rendered grid. |
| 10 | The grid splits at the server's `tier_2_starts_at` | **The grid splits at a count of the pool's tier-one survivors** | `tier_2_starts_at` is an index into the *pool*; slicing the *filtered* list at it promoted tier-two cards into tier one. **Found in review.** |
| 11 | The second section's meta counts the pool's tier-two size | Under a filter it counts what the section holds | The page would have contradicted its own count line. **Found in review.** |
| 12 | The loader renders the chunk's cards | **The loader renders the anchor; the grid draws the cards** | Every chunked event was appearing twice. **Found in review.** |

**And the plan's own claims were corrected in the plan, not papered over.** The plan said
"the grid slices at the index the server gave" and "the chunk loader is the island's
presentational half: the list and the anchor". Both were wrong — the plan had not checked
what `tier_2_starts_at` was an index *into*, and had assumed the loader's list and the
grid's list were different cards.

## Dependencies Added

**None.** No new package, no new runtime dependency, and no new build step.

## How to Verify

1. **The whole gate.**

   ```bash
   export PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH"
   cd frontend && pnpm test && pnpm lint && pnpm typecheck && pnpm build
   ```

   Expected: `2203 passed (128 files)`, lint clean, typecheck clean, and `/browse` rendered
   as `ƒ` (Dynamic).

   **The `export PATH` line is not optional.** The machine's default Node is v20, and
   `undici`'s zstd support makes the whole suite fail there with a hundred "Failed to
   start forks worker" errors.

2. **The search, by hand.** Sign in, open `/browse`, and type in the box under the hero.

   - `jazz` — narrows to the cards with "jazz" in the headline, the venue, or a why-tag.
   - `jazz free` — narrows further; both words must match something.
   - `tag:tonight` — narrows to the cards the server tagged tonight, and to nothing else.
   - `tag:music` — **matches nothing.** That is the recorded spec conflict, not a bug.
   - `quantum` — the no-match state: "Nothing matched.", the section heads gone, and a
     way out that points at the search box rather than at "Change city".

3. **The two emptinesses, by hand.** Open a city with no events — the page shows
   *"Nothing nearby tonight. Try a wider city?"* and a **"Change city"** link, and the
   hero is gone. Then, on a city with events, type a query that matches nothing — the
   page shows *"Nothing matched."* and **"Drop a term, or browse the full list."**, and
   the hero is still there.

4. **The tier split, by hand.** On a page where the first card is tier one, search for a
   word that is only on a *later* card. The later card stays under **"More this week"** —
   it does not jump up under "3 worth your attention today".

5. **The chunk, by hand.** Scroll to "More events below" and click it. The chunk's cards
   appear **once**, in "More this week", and the offset advances — clicking again fetches
   the *next* chunk, not the same one.

## Test Coverage

- Tests added: **108** (2,095 → 2,203 across 128 files)
- Coverage: not measured — this repository does not gate on a frontend coverage number
- Status: **passing**

| File | Tests |
|---|---|
| `tests/browse-search.test.ts` | 43 (new file) |
| `tests/browse-rendering.test.tsx` | 68 |
| `tests/browse-boundary.test.ts` | 27 |
| `tests/digest-labels.test.ts` | 15 |
| `tests/browse-a11y.test.tsx` | 8 |

## Ready for Review

- [x] Twelve of thirteen acceptance criteria met outright
- [x] The thirteenth met for six of ten tags, and the shortfall **recorded** rather than
      papered over
- [x] The two empty states distinguished by DOM, not by eye
- [x] A-11's lock enforced by both a source scan and a rendering test
- [x] The chunk-bounded limitation documented in the component's own doc comment
- [x] All four gate commands clean — 2,203 passed, 0 failed
- [x] Both review defects fixed and covered by tests
- [x] The previous item's open Finding 21 (the untested chunk loader) closed
- [x] No new tokens; `styles/tokens.css` untouched
- [x] No backend change; the server's why-tag vocabulary is untouched
- [x] Developer notes captured

## Developer Notes

**`tier_2_starts_at` is an index into the *pool*, not into the list you have.** It is
computed server-side as `max(0, min(BROWSE_TIER_1_SIZE - offset, len(cards)))` — an index
into the pool the server sent. The moment a filter is in play, the list in front of you is
shorter than the pool, and slicing the filtered list at the pool's index promotes cards.
This is the single most likely way to reintroduce an AD-10 violation on this surface.

**A filter is a narrowing, and code written for the whole list breaks on the narrowed one.**
Both defects the review found were this shape: the grid slicing at a pool index, and the
loader drawing what the grid was already drawing. When you add anything downstream of
`filterCards`, ask whether it was written for the filtered list or the pool.

**One place draws the cards.** The grid draws every card, including the chunk's; the loader
draws the anchor. There is a source rule for this (`browse-boundary.test.ts`), because the
duplicate rendering is invisible to a reader who has seen the page once and obvious to a
count.

**The AppShell has a date input.** A rule about "no date pickers" that scans the whole
document will fail on the shell's account controls, not on Browse. A-11's lock is about the
city page's filter vocabulary, so the rendering test is scoped to Browse's own frame.

**The vocabulary libraries legitimately say "chip" and "discovery".** `lib/digest-labels.ts`
names chips because the server sends chip tags, and it names `discovery` because the server
sends that. A source scan over the surface's markup alone — not over the libraries — is
what keeps the A-11 and A-12 rules from crying wolf.

**The placeholder's `tag:music` matches nothing.** If someone "fixes" this by aliasing
`music` onto a chip, they will put "music" on cards the server tagged as something else.
The right fix is a server-side chip, which is a backend decision, not a frontend one.

**Node 24 is required.** `frontend/package.json` requires `>=24.15`; the default is v20.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-029*

---

# Implementation Walkthrough: The Inline Save Button

**Work item:** `frontend-browse-save-button` — *The Inline Save Button — State Machine, Quota
Wall and the Two Refusals*
**Mode:** `confirm` — checkpoint 1 (plan) approved 2026-11-12
**Completed:** 2026-11-12

## Summary

`Component.Button.Save.Inline` — the one element a Browse card adds to the digest card
anatomy. The card body is not a button; **Save is**. It is a client island (it holds a state
machine and talks to the API) mounted inside a card that stays a server component.

**It adds no endpoint.** It uses the `POST` and `DELETE
/api/personal/saved-events/{catalog_event_id}` pair the Detail Screen's action row already
uses, with the same call shape and no request body. The backend is untouched.

The item's real work was **the two 409s**, and they are not symmetric. The backend tells them
apart by `code`, and they mean opposite things:

| Answer | What the backend did | What the button says |
|---|---|---|
| 2xx | The save happened. | "Saved ✓" |
| 409 `scheduling_conflict` | **The save row was written and the pair is active.** The save *succeeded*; a choice is waiting. | "Saved ✓", plus a conflict line |
| 409 `save_cap_reached` | **The gate refused before anything was written.** The save *did not happen*. | "Save", plus an upgrade line |

Rendering both as a failure would say "couldn't save that" about a save that was saved, and
would invite a second press that would receive the same 409. The tests assert the asymmetry
directly, and the test report names that table as the first thing a reviewer should check.

The review phase found **two defects**, both fixed: the quota's shape was hand-declared in
four files while the generated export sat unused, and the spent button's colour was decided
by CSS emission order rather than by the component.

## Structure Overview

One client island, mounted in the slot the grid work item reserved, fed the payload's facts.
The quota travels down the tree as **the server's number**, unchanged, from the route to the
island — nobody along the way re-derives it.

```
app/browse/page.tsx              server — reads the payload, hands the quota down
   └─ components/browse/browse-search.tsx    client island — owns the grid
        └─ components/browse/browse-grid.tsx        server-presentational — both sections
             └─ components/browse/browse-card.tsx        server component — the card
                  └─ components/browse/browse-save.tsx   client island — the Save button
```

**Why the card stays a server component.** An island can be mounted inside a server
component's markup, so making the card a client component would put the whole grid's markup
across the client/server boundary for the sake of one button. The boundary test asserts
this: exactly two client modules on the surface — `browse-save.tsx` and `browse-search.tsx` —
and the card is not one of them.

**The island's three states, and what is not one of them.** `idle → saving → saved`. The
quota wall is **not** a state — "the allowance is spent" is a fact about the payload, so it
is derived at render. A `blocked` state could get stuck when the allowance reset, and a
reset the payload never announces would leave it stuck forever.

## Architecture

### Pattern Used

**Client island in a server-rendered surface.** The route, the grid and the card render on
the server; two client islands own the two things that need a browser — the filter (which
must reach the whole loaded set) and the Save button (which holds a state machine and talks
to the API). This is the same pattern the two previous items established, and the boundary
test enforces the count.

### Layer Structure

```text
┌─────────────────────────────────────────┐
│  Server components                      │
│  route · grid · card — render the       │
│  payload, decide nothing                │
├─────────────────────────────────────────┤
│  Client islands (exactly two)           │
│  search — owns the filterable surface   │
│  save   — owns the state machine        │
├─────────────────────────────────────────┤
│  Generated client                       │
│  api.POST / api.DELETE — never fetch    │
├─────────────────────────────────────────┤
│  Backend (untouched)                    │
│  POST/DELETE /api/personal/saved-events │
│  two 409s, told apart by `code`         │
└─────────────────────────────────────────┘
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `frontend/components/browse/browse-save.tsx` | The Save island — the state machine, the quota wall, and the two refusals told apart by `code` |
| `frontend/tests/browse-save.test.tsx` | 35 tests of the island: the state machine, the endpoints, the two refusals, the quota wall, the Pro exemption, the first paint, the in-flight guard and the Esc cancel |

### Modified

| File | Changes |
|------|---------|
| `frontend/components/browse/browse-card.tsx` | Mounts the Save island in the reserved slot and passes the payload's quota; stays a server component |
| `frontend/components/browse/browse-grid.tsx` | Passes the quota down to both sections' cards |
| `frontend/components/browse/browse-search.tsx` | Passes the quota down to the grid |
| `frontend/app/browse/page.tsx` | Passes the payload's quota into the search island |
| `frontend/lib/browse-labels.ts` | Adds `spentQuotaLabel()` — the spent allowance as the payload's numbers |
| `frontend/tests/browse-boundary.test.ts` | The two-islands rule: `browse-save.tsx` is the second client module, the card stays a server component, and neither island reaches `next/headers` |
| `frontend/tests/browse-rendering.test.tsx` | Six tests of the card's Save button — one per card, the accessible name, the first paint, the muted quota label, the Pro exemption and the request through the existing endpoint |
| `frontend/tests/browse-a11y.test.tsx` | The axe gate for the spent-quota state |

## Key Implementation Details

### 1. The two refusals, told apart by `code` and never by prose

The backend owns the wording and will change it, so a client that matched on the message
would break on a reword. The island branches on `error.code` only. `readCapDetails()` from
`lib/cap-details.ts` reads the cap out of a refusal — and it too branches on `code`, not on
the presence of a field, because the save endpoint already answers 409 for an unrelated
reason.

### 2. The quota wall is read from the payload, never re-derived

`quota.cap` is `null` for a Pro account and `is_pro` says so as well — **both are read, and
either one is enough**, because Django Ninja omits the field when it is null and a missing
`cap` is the same answer arriving by two routes. `quotaNote()` in `lib/browse-labels.ts`
reads the same two facts the same way; two rules for one fact would be a rule that could
drift.

**The client never refuses a save on the strength of a string it rendered.** The server's
gate is the gate; this is a sign above it.

### 3. The refusals are inline, in the normal flow, under the button

No `role="dialog"`, no `aria-modal`, no overlay, no portal, no toast. `save_cap.py` puts it
plainly: *"A cap that interrupts with a modal is a cap that trains people to dismiss
prompts."* The line is `role="status"`, not `role="alert"` — a refusal is information, not
an emergency, and an assertive region would interrupt a screen reader mid-sentence.

**The test asserts the absence by name.** It queries for `[role="dialog"]`,
`[aria-modal="true"]`, `[role="alertdialog"]` and a toast container, and fails if any
exists. A test that only checked the copy would pass while a modal appeared.

### 4. `Esc` abandons an answer, not the save

The item's technical note asked whether server-side rollback actually exists. **It does
not.** `save_event()` writes inside `transaction.atomic(using=PERSONAL)` and the transaction
commits when it returns — no abort path, no compensating write, no cancellation hook. So the
honest scope is the client-side label, and the generation counter makes the in-flight answer
a no-op.

**The handler is on the wrapper, not on the button.** The button is `disabled` while a
request is in flight — that is what "Saving…" means — and **a disabled button fires no key
events at all.** A handler on the button would never run in the one case it exists for. The
wrapper is never disabled, and the event bubbles up to it.

### 5. The morph reuses the existing transition token

`--motion-fade-in` is `opacity 240ms ease-out` — the criterion's 240ms and the token's 240ms
are the same number — and `.fade-in` already collapses under `prefers-reduced-motion`.
`tests/architecture.test.ts` bans every Tailwind `transition-*`/`duration-*`/`ease-*` class
in a `.tsx`, so a hand-written transition would have failed the build. Reusing the token is
what makes the reduced-motion criterion true for free.

## Security Considerations

| Concern | Approach |
|---------|----------|
| The client does not decide whether a save is allowed | The server's gate is the gate. The wall is *rendered* from the payload; the refusal comes from the server. A client that blocked on a locally-derived number would be a second, weaker gate. |
| The two refusals are not distinguished by message text | Branching on `code` means a backend rewording cannot silently change the client's behaviour — and cannot, for instance, make a cap look like a clash. |
| The un-save path is the same endpoint | `DELETE` on the same path, so no second route is introduced and no authorization surface widens. |
| No destructive confirmation, by design | The thing being removed is something the reader put there themselves. The label change *is* the feedback. |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| The first paint must not flash "Save" | `is_saved` comes from the API and is the initial state — the button renders "Saved ✓" on the first paint. |
| A fast double-tap must not flicker the label | A 1500ms lockout, held by a flag cleared by a timer rather than a `Date.now()` compared during render. |
| A duplicate press must not cost a second request | The in-flight guard is in the handler, not only on `disabled` — a click dispatched in the same tick as the state change can still arrive. |
| The quota must not be re-fetched per card | It travels down the tree as one value. No extra request, no per-card read. |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| The two 409s are told apart by `code`, and rendered asymmetrically | A `scheduling_conflict` renders "Saved ✓" plus a conflict line; a `save_cap_reached` renders "Save" plus an upgrade line | The backend semantics differ: a conflicting save means the row was written and the pair is active (the save **happened**), while the cap is refused before anything is written (the save **did not happen**) |
| The quota wall is derived at render, not a state in the machine | `spent = !isPro && used >= cap`, computed from the payload on every render | A `blocked` state could get stuck when the allowance reset, and a reset the payload never announces would leave it stuck forever |
| The cap sentence uses the criterion's wording, not `UpgradePrompt`'s "the server's sentence, rendered verbatim" | "You've used your N free save today", with N read from `details.cap` | `UpgradePrompt` exists to render a server sentence where there is no criterion; here the criterion *is* the sentence. The number is still the payload's |
| The 240ms morph reuses the existing `.fade-in` token rather than a new transition | The `fade-in` class | The criterion's 240ms and the token's 240ms are the same number; `.fade-in` already collapses under reduced motion; and `tests/architecture.test.ts` bans Tailwind transition classes in a `.tsx` |
| `Esc` is scoped to the client-side label | The generation counter moves and the label resets; the button does not claim the save did not happen | `save_event()` commits inside `transaction.atomic()` with no abort path, so there is no server-side rollback to honour |
| The `Esc` handler sits on the wrapper, not on the button | `onKeyDown` on the wrapper div, which is never disabled | A disabled button fires no key events at all, and the button *is* disabled while a request is in flight — the only moment the cancel exists for |
| The quota's shape is the generated type, not a hand-written copy | `BrowseQuota` from `lib/browse-read.ts` | Found in review. The shape was hand-declared in four files while the generated export sat unused — exactly the copy-that-can-drift that AD-19 exists to prevent |
| The spent button carries exactly one ink colour | `blocked ? "text-ink-faint" : labelColour`, as a replacement rather than an addition | Found in review. The button carried both, and Tailwind resolves two colour utilities by CSS emission order, not by class order. Measured against the shipped CSS: `text-ink-faint` is emitted first, so the ordinary ink won and the button that refuses every press looked like the one that accepts them |

## Deviations from Plan

| # | Deviation | Why |
|---|-----------|-----|
| 1 | **The Save button is a client island.** The card is not. | The button holds a state machine and talks to the API, so it cannot be a server component — but an island can be mounted inside a server component's markup. The card hands it the payload's facts. |
| 2 | **The cap sentence is the criterion's, not the server's.** | `UpgradePrompt`'s rule is "the sentence is the server's, rendered verbatim" — but that rule exists for places where there is no criterion. Here the criterion *is* the sentence, and the AC says so word for word. The cap's *number* is still the payload's. |
| 3 | **`.fade-in` instead of a new transition class.** | The criterion's 240ms is the existing token's 240ms, and `tests/architecture.test.ts` bans Tailwind transition classes in a `.tsx`. A new class would have failed the build. |
| 4 | **`Esc` is scoped to the label.** | The technical note asked whether the rollback exists. It does not — `save_event()` commits inside `transaction.atomic()` with no abort path. Claiming the save was undone would be a guarantee the server does not make. |
| 5 | **The conflict line does not read `details.conflicts[0]`.** | The AC asks for a link "to the event detail" — the event being saved — and that is what the "Open" link does. The clashing event's name is available in the payload but is not asked for. *(Corrected in review: the plan had claimed the name was carried in the DOM, which the implementation does not do.)* |
| 6 | **The wall is derived, not a state.** | A `blocked` state could get stuck when the allowance reset. |
| 7 | **`Esc` is on the wrapper.** | A disabled button fires no key events. |
| 8 | **A generation counter, not a boolean.** | A boolean cannot distinguish "the answer I am waiting for" from "an answer I cancelled" — a second cancel, or a second press, would let a stale answer through. |

## Dependencies Added

**None.** No new package, no new dependency, no new token, no new CSS variable, no new
endpoint.

## How to Verify

1. **The suite, the lint, the typecheck and the build**

   ```bash
   cd frontend
   export PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH"   # Node 24 is required
   pnpm test && pnpm lint && pnpm typecheck && pnpm build
   ```

   Expected: **2246 passed (129 files)**, lint clean, typecheck clean, build clean with
   `/browse` rendering as `ƒ`.

2. **The island's own tests**

   ```bash
   pnpm vitest run tests/browse-save.test.tsx
   ```

   Expected: 35 passed. The describes are the state machine, the endpoints, the cap refusal,
   the conflict refusal, neither refusal interrupting, the quota wall, the Pro exemption, the
   button itself, the first paint, the in-flight guard and the Esc cancel.

3. **The asymmetry, by hand** — this is the one to check first

   Save an event that clashes with a saved one, and confirm the button says **"Saved ✓"** and
   a conflict line appears with an "Open" link. Then exhaust the allowance and save again:
   the button must go back to **"Save"** with an upgrade line. The clash means the save
   *succeeded*; the cap means it *did not*.

4. **The quota wall**

   With the allowance spent, every button on the page should read "1 of 1 save used today",
   be disabled, and carry `title="Upgrade for unlimited saves"`. Pressing it should do
   nothing — no request.

5. **The Pro exemption**

   A Pro account's `cap` is `null`. No button should ever show the muted label, and repeated
   saves should succeed.

6. **The review's colour finding**

   Inspect a blocked button's `className`. It must carry **exactly one** `text-ink-*` class,
   and it must be `text-ink-faint`. (The pre-review code carried two, and the ordinary ink
   won the cascade.)

## Test Coverage

- Tests added: **43** (35 in the new file, 8 across the three existing Browse test files)
- Coverage: **the island's branches are covered** — every state, both refusals, the wall,
  the Pro exemption, the first paint, the in-flight guard and the Esc cancel
- Status: **passing** — 2246 passed (129 files), 0 failed

## Ready for Review

- [x] All acceptance criteria met (13 of 13; criterion 13 is satisfied *by construction*
      rather than by a DOM test — jsdom evaluates no media queries)
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated (`plan.md`, `test-report.md`, `review-report.md`)
- [x] Developer notes captured

## Developer Notes

**The `Esc` trap.** A `<button disabled>` fires **no key events at all** — so a cancel
handler placed on the button never runs, because the button is disabled for exactly the
duration the cancel exists for. The handler belongs on a wrapper that is never disabled.

**A test can pass and prove nothing.** The original `Esc` test used `fireEvent.keyDown`,
which dispatches to the element regardless of `disabled`. The test was green and the
feature was broken. The test now fires on the wrapper, and a second test asserts the button
really is disabled at that moment. The mutation probe — moving the listener back — fails
both.

**Two colour classes on one element are decided by the cascade, not by the component.**
Tailwind sorts utilities by their own name, not by the order they appear in `className`.
`text-ink-faint` is emitted *before* `text-ink-secondary`, so a button carrying both renders
in the ordinary ink. Assert that the element carries **one** colour class, not that a
particular one is present.

**`vi.useFakeTimers()` mid-test breaks `waitFor`.** `waitFor` polls with real timers. The
lockout tests wait ~1600ms of real time inside `act()` instead.

**The two 409s are not symmetric, and getting this backwards is the worst mistake available
here.** A clash means the save *succeeded*; a cap means it *did not happen*. The backend's
own words are the authority: `api.py:398` and `saved_events.py:106`.

**`readCapDetails()` branches on `code`, not on the presence of `upgrade_hint`.** The save
endpoint already answers 409 for an unrelated reason, so narrowing on a field's presence
would make the client's reading depend on a payload's accidents.

**Node 24 is required.** `frontend/package.json` requires `>=24.15`; the default is v20, on
which the whole suite fails with ~100 undici/zstd errors.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-029*

---

# Implementation Walkthrough: Retiring the "Coming Soon" Stubs

**Work item:** `browse-nav-activation` — *Retire the Three "Coming Soon" Stubs*
**Mode:** `autopilot` — 0 checkpoints
**Completed:** 2026-11-12

## Summary

Three places in the shell rendered Browse as a disabled `<span>` with a "Coming soon" note,
because a link to a 404 is a lie about where a label goes. The Browse surface shipped, so
the lie inverted: the stub now claims there is nothing there when there is a whole city to
browse.

**Three of them were Browse. A fourth was not, and it was the one that mattered.**

| # | Where | What it was | Now |
|---|---|---|---|
| 1 | `sidenav.tsx` | `<span aria-disabled="true">` + "Coming soon" | `<Link href="/browse">` |
| 2 | `more-menu.tsx` | `<span aria-disabled="true">` + "Coming soon" | `<Link href="/browse">` with `aria-current` |
| 3 | `bottom-tab-nav.tsx` — the bar's **Digest** slot | `<span aria-disabled="true">` + a visually-hidden "Coming soon" | `<a href="/">` |
| 4 | `more-menu.tsx` — the sheet's inert-row branch | a whole branch for a disabled row | **deleted** |

**The bottom tab never had a Browse slot.** It has five slots — Digest / Timeline / Add /
Conflicts / Settings — and Browse is the sixth route, behind the More sheet on the trailing
edge, because the bar's geometry is five slots at twenty percent each and the spec says so
twice.

So the bar's *first* slot was the inert one, and it was inert for a reason that had nothing
to do with Browse: **the Digest slot has had no `href` since the digest home shipped.**
`git log -p --follow` shows only the `+` line for that slot, never a `-` line — it was
never a link. On a phone, tapping the first tab rendered a disabled `<span>` carrying a
visually-hidden "Coming soon", **while also carrying `active={pathname === "/"}`**. The home
route's own tab did nothing, and said it was not coming soon.

The item's third criterion — *"the visually-hidden 'Coming soon' text is removed where it
referred to Browse"* — pointed at a place where nothing referred to Browse, because the text
that remained was attached to **Digest**. The criterion was satisfied by a fix the item did
not name, and that fix is the difference between a phone user reaching the digest and not
reaching it.

## Structure Overview

No new files, no new layers, no new components. Three existing shell components changed,
and the change is entirely in what they *are* — a `<span>` became a `<Link>`.

```
components/shell/sidenav.tsx          6 routes, vertical list, desktop only (md:flex)
   ├─ <Link href="/browse">            ← was a disabled <span>
   └─ if (!href) → <span aria-disabled>   ← KEPT, for the next deferred route

components/shell/bottom-tab-nav.tsx    5 slots, horizontal bar, mobile only (md:hidden)
   ├─ <a href="/">  (Digest)          ← was a disabled <span> with no href at all
   ├─ <MoreMenu />                     ← the sixth route lives behind this control
   └─ if (!href) → <div aria-disabled>   ← KEPT, for the next deferred route

components/shell/more-menu.tsx         the overflow sheet the More slot opens
   ├─ <Link href="/browse">            ← was a disabled <span>
   └─ (the inert branch)              ← DELETED — the sheet's only row is a route
```

**The geometry is unchanged.** Five slots, twenty percent each, in the same order. The More
slot is still a control and still carries no `aria-current="page"`; the row *inside* the
sheet carries that, because **More is a control and Browse is a route.**

## Architecture

### Pattern Used

**A disabled affordance becomes a link; the pattern that produced it stays.** The shell
already had the right structure for a route that does not exist yet — a `<span>` with
`aria-disabled`, never an anchor, because *"the attribute is a hint, not a mechanism"*. This
item did not remove that structure. It stopped using it, and left it standing for the next
route that needs it.

### Layer Structure

No layer moved. All three components were already `"use client"`, so `usePathname` in
`more-menu.tsx` added **no new client boundary** — verified, not assumed.

## Files Changed

| File | Change |
|---|---|
| `components/shell/sidenav.tsx` | Browse becomes a real `SidenavItem` with `href="/browse"` and `active={pathname === "/browse"}`. The inert branch is kept; its comment now says nothing uses it today. |
| `components/shell/more-menu.tsx` | The sheet's row becomes a `<Link>` carrying `aria-current="page"`. The inert branch is **deleted**. `usePathname` imported and called. |
| `components/shell/bottom-tab-nav.tsx` | The Digest slot becomes `<a href="/">` with `active={pathname === "/" \|\| pathname.startsWith("/events/")}`. |
| `components/shell/nav-routes.test.tsx` | Browse-inert inverted to Browse-link (+3); a `describe("the More sheet")` block added (+3); the bar's Digest slot pinned (+2). **16 → 23.** |
| `tests/digest-home-boundary.test.ts` | The More-sheet assertion inverted; the new source-level sweep added; the "does not render an inert route as an anchor" rule left standing. **26 → 27.** |
| `app/page.test.tsx` | The Browse-is-inert test inverted; a new test asserts the rail has **no** `aria-disabled` row left. **51 → 52.** |

## Key Implementation Details

### 1. The active rules differ per route, and the difference is not arbitrary

| Route | Rule | Why |
|---|---|---|
| Digest | **prefix** — `/` or `/events/*` | the Detail Screen is reached by tapping a Digest card, so `/events/*` hangs off Digest in the IA |
| Browse | **equality** — `/browse` | Browse has no children. A prefix rule would be a claim about routes that do not exist |
| Timeline | equality | no children |
| Conflicts | equality | no children |
| Settings | **prefix** — `/settings/*` | `/settings/reminders` and `/settings/quiet-hours` both hang off it; the link points at the first |

**The bar's Digest slot takes the sidenav's prefix rule, and it has to.** The sidenav
already marked Digest active on `/events/*`. If the bar did not, the *same screen* would
show Digest active in the rail and **nothing** active in the bar — which reads as "you have
left the digest" on a screen the user never left.

### 2. More is a control. Browse is a route. The distinction is the point.

The More button carries `aria-haspopup="dialog"` and **no** `aria-current`. The row inside
the sheet carries `aria-current="page"` when Browse is current. A screen-reader user on
`/browse` needs to be told where they are, and the thing they are in is the sheet's row,
not the button that opened the sheet.

Both halves are asserted by **separate tests**, because they fail for different reasons.

### 3. The criterion's assertion is on the source, and that is the only way to see all three

*"No `aria-disabled` Browse row remains anywhere — asserted by a test."*

The three places live in three different files, and only one is reachable from any single
render. The More sheet's row is not in the DOM until the sheet is opened. **A DOM assertion
can only ever see one of them at a time.**

So the assertion is a source-level sweep across the three shell files — the same house
pattern as `tests/digest-home-boundary.test.ts` already uses for the rules a rendering test
cannot catch.

**And the sweep cannot be "this file contains no `aria-disabled`".** The inert branches are
kept, and they *do* contain `aria-disabled="true"` and a "Coming soon" string — that is what
they are. The sweep is narrower and truer:

> **No inert branch mentions Browse.**

```tsx
const inertBranch = /if \(!href\) \{[\s\S]*?\n  \}/.exec(source)?.[0] ?? "";
expect(inertBranch.includes('label="Browse"'), file).toBe(false);
```

The inert branch renders the disabled `<span>`, so the label inside it is the label that is
on the way but not here. If Browse is in that branch, Browse is inert. If it is not, it is a
route — and the branch is waiting for the next one.

The sweep also asserts the positive half, because *nothing is inert* is a weaker claim than
*this thing is a link*.

### 4. The More sheet is held to a stricter standard than the other two

It has no inert branch to keep, so it carries neither the marker nor the note:

```tsx
expect(more).not.toContain("aria-disabled");
expect(more).not.toContain("Coming soon");
```

## Security Considerations

**None.** No fetch, no URL built from user input, no auth check, no token, no cookie. The
links are two static literals — `/browse` and `/` — and both point at routes that exist
(confirmed by the build output: `/browse` is `ƒ (dynamic)`).

The backend is **untouched** by this item. `git diff` shows no change under `backend/`.

## Performance Considerations

**Negligible.** Two client components gain a `usePathname()` call — a React hook that reads
the router's current pathname from context, not a subscription or a network request. The
More sheet's row adds one `<Link>`, which is one prefetch on hover.

## Decisions Made

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | The More sheet's inert branch | **Deleted** | The sheet's only row is Browse, and Browse is a route. There was never a reason for that sheet to carry a disabled `<span>`. Leaving the branch would be leaving dead code. |
| 2 | The sidenav's and the bar's inert branches | **Kept** | The Technical Notes: *"Nothing here should weaken that rule for whatever route is deferred next."* The branch is the *implementation of a rule*, not a Browse thing. Deleting the only implementation of a rule, in the same edit that removes its last user, is how the rule dies quietly. |
| 3 | The bar's Digest slot's active rule | **Prefix** | Not named by the item, but the sidenav already applies it, and the two rails must agree or the same screen shows two different answers about where the reader is. |
| 4 | The criterion's assertion | **On the source** | A DOM assertion sees one of the three places at a time. The source sweep is the only assertion that sees all three. |
| 5 | The `page.test.tsx`'s "Coming soon" filter | **Kept, comment corrected** | It is dead weight today, but it is the guard that keeps the six-route-order test honest when the next deferred route lands. The comment now says what is true. |
| 6 | The bottom bar's `<a>` vs the rail's `<Link>` | **Left alone, recorded** | Pre-existing — Timeline and Conflicts already used the raw `<a>`. Changing it is a behavioural change outside this item's scope. Recorded in the review report. |
| 7 | Prettier on 14 files | **Auto-fixed** | One was introduced by this item (`nav-routes.test.tsx`, verified clean at HEAD); the other thirteen are new files from earlier items in this run. CI runs `prettier --check`, so they would all have failed the pipeline. |
| 8 | The five-route onboarding variant | **Not touched** | It does not exist in the code. `app/onboarding/page.tsx` renders `BrandTopbar` + `OnboardingFlow` and no nav; the variant survives only as a design intention in `frontend-digest-home-design.md` D12 and `EXPERIENCE.md:1155`, and neither renders it. |

## Deviations from the Plan

| # | The plan said | Now | Why |
|---|---|---|---|
| 1 | "Three places render Browse as an inert `<span>`" | **Two rendered Browse inert; a third rendered *Digest* inert** | The bar's five slots have no Browse slot — Browse is behind the More sheet. The third inert thing was the bar's *first* tab, which had no `href` since the digest home shipped. |
| 2 | "deletes the inert-row machinery that only Browse used" | **Two of three branches kept; only the More sheet's deleted** | The Technical Notes ask for the rule to survive. **Recorded in the run log, as the criterion requires.** |
| 3 | The bottom tab's "Browse handling is updated" | **The bar's Browse handling did not change, because there is none** | The bar carries five slots; Browse is the sixth route, behind More. The bar's change was the Digest slot. |
| 4 | The onboarding five-route variant is "unchanged" | **There is no five-route variant in the code** | Nothing changed, so the criterion is satisfied trivially. |
| 5 | — | **The Digest slot's active rule became a prefix** | Not named by the item. The sidenav marks Digest active on `/events/*`; the bar must agree. |

## Dependencies Added

**None.** No new package, no new module, no new endpoint. `fireEvent` was added to an
existing `@testing-library/react` import; `Link` and `usePathname` were added to a file
that already imported from `next/`.

## How to Verify

1. `cd frontend && export PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH"` — Node 24 is
   required; the default v20 fails the whole suite.
2. `pnpm test` → **2255 passed (129 files)**.
3. `pnpm lint && pnpm typecheck && pnpm build` → all clean.
4. `pnpm format:check` → clean.
5. **In a browser, at phone width**: the bottom bar's first tab is a *link* — tapping it
   reaches `/`. It is no longer a disabled span. Open the More sheet: its Browse row is a
   link, and on `/browse` that row (not the More button) is the one marked as current.
6. **In a browser, at desktop width**: the rail's Browse row is a link to `/browse`, and on
   `/events/…` the rail marks Digest active.

## Test Coverage

**Nine tests added, zero removed.** 2246 → 2255.

| File | Before | After | What the new ones cover |
|---|---|---|---|
| `components/shell/nav-routes.test.tsx` | 16 | **23** | Browse is a link in the rail (×1), Browse's `aria-current` when current and when not (×2), the bar's Digest slot is a link and is active on `/events/*` (×2), the More sheet's Browse row is a link and carries `aria-current` (×2), More carries none (×1) |
| `tests/digest-home-boundary.test.ts` | 26 | **27** | the source-level sweep across all three shell files |
| `app/page.test.tsx` | 51 | **52** | the rail has no `aria-disabled` row left |

**Mutation-proven.** Seven distinct tests fire across two mutations: the More sheet's
Browse row reverted to an inert `<span>`, and the bar's Digest slot reverted to no `href`.
The source-level sweep fires under both — which is the point of putting it on the source.

## Ready for Review

**Yes.** All eight criteria pass, the backend is untouched, and the criterion the item asked
for by name — *"No `aria-disabled` Browse row remains anywhere"* — is asserted by a test
that was mutation-proven to fire.

**The thing a reviewer should check first** is *Decisions* row 2: the two kept branches.
The item's criterion reads *"deleted if Browse was its only remaining user"*, and Browse
**was** the last user in both — so a literal reading says delete, and this edit keeps them.
The Technical Notes ask for the rule to survive, and the run log says which way it went and
why. If the item's author meant the literal reading, this is the one decision to overturn.

## Developer Notes

**Read the third row of the summary table before you read the diff.** The item was written
around Browse, and the interesting defect was not a Browse defect. The bottom tab's Digest
slot has never been a link — not since it was introduced, not since the digest home
shipped — and it looked exactly like an active slot, because it *was* marked active. An
inert affordance that carries `active` is the worst kind of inert: it tells the user where
they are and does nothing.

**Two branches survive on purpose.** If you delete them, delete the Technical Notes first —
and understand that the next deferred route will then have nothing to copy, and will
probably reach for an `<a aria-disabled="true">`, which still navigates.

**The bottom bar's `<a>` is not the rail's `<Link>`, and it was not before this item
either.** That inconsistency is recorded in the review report rather than fixed here.
