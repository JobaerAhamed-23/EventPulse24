---
run: run-eventpulse24-029
work_item: test-clock-seam
intent: browse-surface
generated: 2026-11-12
status: passed
---

# Code Review: A Clock Seam for the Tests

## Scope

```
backend/domain/quiet_hours.py                          |  8 +-   (1 pragma comment)
backend/pyproject.toml                                 |  1 +
backend/uv.lock                                        | 14 +
backend/tests/delivery/test_reminder_plan_api.py       | 33 +-
backend/tests/domain/test_quiet_hours.py               | 14 +
backend/tests/domain/test_weekly_quiet_hours.py        | 28 +-
backend/tests/e2e/test_personal_events_and_saved_catalog.py | 20 +
backend/tests/e2e/test_save_race.py                    | 22 +
backend/tests/e2e/test_timeline_and_conflict_proof.py  | 19 +
backend/tests/ingestion/test_url_feed_read.py          | 27 +-
```

283 insertions, 7 deletions. Nine of the ten files are tests or packaging. The tenth is a
comment.

## Standards compliance

`.specs-fire/standards/testing-standards.md`, "Mock Strategy", line 97:

> **"Freeze time explicitly. Never depend on wall-clock or local timezone."**

**The 17 failures were a standing violation of a rule this project had already written down.**
This item did not invent a convention; it enforced one that existed and was unenforced. That
is the strongest argument that the approach is right, and it is worth recording because it
reframes the work: not "a clever fix for flaky dates" but "the standard, finally applied".

The same section's neighbouring rules are also satisfied:

| Rule | Status |
|---|---|
| Fake at the **port** boundary; never mock the ORM or the database | **kept** — no ORM or DB mocking was added; `freeze_time` patches the clock, not persistence |
| Use a real Postgres for app and worker tests | **kept** — unchanged |
| No `time.sleep` in tests | **kept** — none added |
| Explicit UTC + IANA tz on every temporal fixture | **kept** — every frozen instant is tz-aware; the two deliberate naive values are wall clocks passed to a function documented to take them, each carrying a `noqa` and a reason |
| Include DST-boundary cases for any time logic | **kept** — `FAR_AFTERNOON_START` was chosen specifically so both it and `AFTERNOON_START` sit in PST (US DST ended 2026-11-01), preserving the quiet-hours property under test |

Architecture contracts: **19 kept, 0 broken** (`make lint-imports`). `domain/` gained no import
— it is still pure stdlib and importable with Django absent, which its own module docstring
requires.

## Findings

### Auto-fixed (mechanical, non-semantic)

| # | Finding | Fix |
|---|---|---|
| 1 | `I001` import block unsorted in `test_reminder_plan_api.py` after adding `freezegun` | `ruff check --select I --fix` |
| 2 | Blank-line formatting in `test_timeline_and_conflict_proof.py` after inserting the fixture | `ruff format` |

Both re-verified: `make lint-backend` → "All checks passed!".

### Confirmed with the user before acting

| # | Finding | Why it needed confirmation | Outcome |
|---|---|---|---|
| 3 | `domain/` coverage gate at 99%, needing a production-file edit to close | The work item explicitly promised no production code changes; a `pragma` is still an edit to a production file | Approved; closed with 2 tests + 1 pragma |

### Reviewed and accepted

| # | Observation | Judgement |
|---|---|---|
| 4 | `tick=True` on all five freezes | **Correct and necessary.** UUIDv7 keys order by timestamp prefix and four of these modules assert on identity or ordering. A hard freeze would have traded a dated bug for a flaky one. |
| 5 | Two tests changed their *fixtures*, not just their clock (`FAR_AFTERNOON_START`, events created a day back) | **Justified, and the production code was right in both cases.** Each is documented in `test-report.md` Issue 1 with the reasoning inline in the test. Both were mutation-checked afterwards. |
| 6 | `# noqa: DTZ001` used twice rather than adding `tzinfo` | **Correct.** `_ends_covering` takes a wall clock and its docstring calls the values naive. A `tzinfo` would assert an instant the value does not mean — the lint rule would be satisfied and the code would be less true. |
| 7 | `pragma: no cover` carries 6 lines of justification | **Deliberate.** The risk with an unreachable line under a hard 100% gate is that someone eventually lowers the gate. The comment names the test that pins the unreachability. |
| 8 | `freezegun==1.5.5` exact-pinned | **Matches house convention** — every other dev dep is exact-pinned. `uv.lock` diff shows freezegun only; no other version moved, ruff included (verified 0.17.3 before and after). |

### Open — recorded, not fixed

| # | Finding | Severity | Why not fixed here |
|---|---|---|---|
| 9 | `test_a_custom_slot_is_minted` asserts the send exists but never its **due time** — the "90 minutes" in `custom:90` is unverified | low | Outside this item's acceptance criteria. Found by accident when a mutation to `slot_offsets` left the test passing. Silently widening scope is the habit this run is meant to break. |
| 10 | Backend suite takes **12m14s**; `pytest-xdist` not installed | low | Raised at checkpoint 1 and explicitly declined for this item. |

## The thing worth saying plainly

This item was scoped as "fix 17 failing tests". It found **three** red gates, all pre-existing,
all masked by the first:

1. `make test-backend` — 17 failures
2. `make lint-backend` — 2 `DTZ001` errors, red since run 027 (`54ecf50`)
3. `make coverage-backend` — `domain/` at 99%, and **never evaluated**, because `make` aborts
   at the failing pytest step before reaching the gate

Runs 027 and 028 both closed while 2 and 3 were red. That is not a criticism of those runs so
much as a property of the setup: **a gate behind a failing gate is not a gate.** If one thing
survives this item beyond the fix itself, it should be that `coverage-backend` runs its second
command even when the first fails, or that CI reports each gate independently.

All three are green as of this review.

---

# Code Review: The Browse Read API

## Scope

```
backend/apps/ingestion/services/catalog_read.py       |  11 +   (one additive parameter)
backend/apps/personalization/api.py                     |  97 ++
backend/apps/personalization/schemas.py                 |  95 ++
backend/apps/personalization/services/browse_read.py    | 377 ++  (new)
backend/apps/personalization/services/save_cap.py       |  63 ++
backend/ports/throttle.py                               |  37 ++
backend/adapters/throttle/memory.py                     |  19 +
backend/adapters/throttle/redis.py                      |  31 +
backend/tests/adapters/test_throttle.py                 | 114 ++
backend/tests/personalization/test_browse_read.py       | 521 ++  (new)
backend/tests/personalization/test_browse_api.py        | 238 ++  (new)
frontend/lib/api/openapi.json                           | 255 ++  (generated)
frontend/lib/api/schema.ts                              | 207 ++  (generated)
```

Nine backend files and two generated frontend files. **No production code outside
`personalization`, `catalog_read` and the throttle port was touched**, and no model was
added or migrated — Browse is a read.

## Standards compliance

| Rule | Status |
|---|---|
| AD-3 — two aliases, no cross-schema join, always `using=` | **kept.** `browse_read.py` reads the catalog through `catalog_read`'s published interface and the personal side through `using(PERSONAL)`. No transaction spans the two; the join is in Python. |
| AD-10 — never substitute the Event Fit for the Relevance Pulse | **kept.** `browse_read.py` imports `domain.ranking`, not `apps.ingestion.event_fit`. The import-linter's two contracts pass (52 tests, 0 broken). |
| AD-10 — "never recomputed at render" | **deviation, recorded below as Finding 1.** |
| AD-19 — `frontend/lib/api/` is generated, never hand-edited | **kept.** `make client` is idempotent: regenerating twice changes nothing, verified by copy-and-diff rather than by `git diff --exit-code` (which reports the *new* types as drift, not instability). |
| Domain purity — `domain/` is stdlib-only | **kept.** `domain/` was not touched by this item. |
| No direct ORM writes outside commands | **kept.** The architecture scan (979 tests) passes. |
| `ruff` — `E,F,I,B,UP,S,DTZ,G,LOG`, line length 100 | **clean.** `ruff check`: all passed. `ruff format --check`: 626 files already formatted. |

## Findings

### Auto-fixed (mechanical, non-semantic)

None. The diff went into the gate already lint-clean, and the review found nothing that a
formatter or import-sorter would have caught.

### Reviewed and accepted

| # | Observation | Judgement |
|---|---|---|
| 1 | `ThrottlePort.peek` is a **new abstract method** on a shared port | **Correct and additive.** `check` is untouched, so the gate's behaviour is byte-identical — the property the whole gate rests on. Both implementations (memory, Redis) were updated, and there are exactly two: a grep for `ThrottlePort` across `backend/` finds no third. The Redis adapter's `peek` uses `GET` + `TTL` and never `INCR`, so it cannot spend an allowance. |
| 2 | `RedisThrottleAdapter.peek` treats a non-numeric key as `used=0` | **Correct.** Reporting zero shows a full allowance rather than refusing a save the gate would have allowed — and the gate still decides every actual save, so nothing is let through. The alternative (raising) would turn a corrupt counter into a 500 on a read. |
| 3 | `RedisThrottleAdapter.peek` clamps a missing TTL to `window_seconds` | **Correct.** Redis returns `-1` for "no expiry" and `-2` for "no key"; the clamp prevents a nonsense countdown reaching the user. The `ttl if isinstance(ttl, int) and ttl > 0 else window_seconds` form also survives `redis-py`'s integer return. |
| 4 | `InMemoryThrottleAdapter.peek` **does not evict** the closed window it finds | **Correct, and deliberately so.** `check` does the eviction on the next attempt. A read that mutated the store would change the answer a later `check` gives — so a surface polling `peek` on every page load would be deciding when a user's window resets, which is the gate's job. Pinned by `test_peek_does_not_evict_the_closed_window_it_finds`. |
| 5 | `read_save_quota` **never peeks a Pro user** | **Correct.** A Pro account has no cap and spends no throttle slots, so there is no window to read. It returns `cap=None` rather than a large number, which is what `FR-48`'s "no soft wall" means. |
| 6 | `starts_before` on `list_public_candidates` is **additive and defaults to `None`** | **Correct.** The Digest never passes it, so the Digest's pool is byte-identical to what it was — pinned by `test_omitting_starts_before_leaves_the_candidate_pool_unchanged`. The bound is **exclusive**, so two windows asked back to back neither overlap nor leave a gap — pinned by `test_starts_before_is_exclusive_at_the_boundary`. |
| 7 | `total` is the **size of the ranked pool**, not a `COUNT(*)` | **Approved at checkpoint 2.** The reason is mechanical: FR-14's staleness bound is applied in Python after the SQL narrows the set (it is per-source, and a database cannot compare a column against another column times a multiplier). A SQL count would count rows the Python filter then drops, so the section head would advertise a number no amount of scrolling reaches. The pool size is exactly what the user can page to. |
| 8 | `MAX_CANDIDATE_POOL_SIZE = 200` is a **real limit**, documented in the module docstring | **Correct to state rather than bury.** A city with more than 200 eligible events in its seven-day window reports 200 and pages to 200. The design's own mockup shows 147 in a week, so there is room — but if it ever binds, the answer is a decision about what Browse is for, not a bigger constant. |
| 9 | The stripe cap is **server-side** | **Correct.** A client-side cap is per page: two pages would each show "their one" and the surface as a whole would flood. Pinned by `test_at_most_one_card_a_page_carries_the_must_know_stripe`. |
| 10 | `tier_2_starts_at` is computed as `max(0, min(BROWSE_TIER_1_SIZE - offset, len(cards)))` | **Correct.** Tier 1 is the top three of the *pool*, so it exists only on the first page; a later page is all "More this week" and its boundary is zero. The formula yields `0` past the first page and clamps to the number of cards actually returned, so a pool smaller than a tier never claims cards it does not have. |
| 11 | The ranking's total order is `(score desc, start_time asc, id asc)` | **Correct, and load-bearing.** Without the id the order is only partial, and two events with the same score and start could swap between pages — showing one twice and losing the other. Pinned by `test_two_passes_over_the_window_show_every_event_exactly_once`. |
| 12 | `apply_hysteresis(previous_bucket=None, previous_score=None, …)` is called with no previous | **Correct, and stated.** Browse has no yesterday to compare against, and `apply_hysteresis` with nothing to compare *is* `score_bucket`. The same call the Digest makes, for the same stated reason. |
| 13 | The service takes `now` as a parameter rather than reading the clock | **Correct.** The seam the whole `test-clock-seam` item exists to establish. `timezone.now()` is called once, in the view layer, and handed down. |
| 14 | `_read_preference` reads `order_by("id").last()` | **Correct.** `DigestPreference` is a `UUIDv7Model`, so the id *is* the creation time and `last` is the newest row — the same read `digest_composition.py` makes. |
| 15 | The quota read is **one `IN` query** over the pool's ids, not one lookup per card | **Correct, and measured.** Pinned by `test_the_saved_state_costs_one_query_however_many_cards_the_page_holds`, which asserts the count rather than inferring it, and which fails loudly (printing all the queries) if the join is rewritten into a per-card lookup. The mutation probe confirmed it is a real assertion. |
| 16 | The catalog pool is **one query**, and the personal side does not grow with the pool | **Correct.** Pinned by `test_scoring_a_full_pool_costs_a_query_and_a_bounded_amount_of_python`: 1 catalog query, ≤4 personal. |
| 17 | The timing bound in the cost test is **loose** (`elapsed < 1.0` for 60 candidates) | **Correct.** A tight wall-clock assertion is a flaky test on a loaded CI box, and a flaky test is worse than no test. The bound catches a *regression of kind* — the score starting to hit the database, or the pool growing without bound — rather than policing microseconds. The measured value (20–27 ms) is printed so the report carries the real number. |

### Open — recorded, not fixed

| # | Finding | Severity | Why not fixed here |
|---|---|---|---|
| 18 | **Browse computes the Why-this Tags at request time; AD-10 says explanations are persisted, never regenerated.** `browse_read.py:333` calls `why_this_tags(...)` in the read path. The Digest does the opposite: `digest_composition.py` calls it once and **persists** the result on `DigestComposition`, and `digest_read.py` reads that row back without ever calling `why_this_tags`. The standards doc lists "Recomputing explanations at render" as an anti-pattern (AD-10), and `system-architecture.md` states AD-10 as *"Persisted Event Fit + Relevance Pulse — Never recomputed at render."* | **medium** | Persisting Browse's explanation is a **schema + composition-job change** — a new persisted row per `(user, event, window)`, a writer that runs before the read, and a read that falls back to the unpersisted path when the row is missing. That is a work item of its own, not a reviewer's fix, and it would change the endpoint's contract. The design document did not address persistence at all, so this is a **gap in the approved design**, not a deviation from it. **Recommended as its own work item under the `browse-surface` intent.** |
| 19 | The consequence of #18, stated plainly: **a Browse card's tags can change between two identical requests** — for instance when the user saves an event, since `why_this_tags` takes `is_saved` and Browse computes it from the live `SavedEvent` join. The Digest's tags cannot, because they were persisted at composition. The window this actually matters is narrow (the tag set differs only when `is_saved` flips, or when the clock crosses a time-tag boundary), and the surface re-reads on navigation rather than caching, so it is a **consistency** difference rather than a wrong answer. But it is a real difference from the Digest, and the design's own D2 goal — that the two surfaces "explain the same event the same way" — holds only while the inputs hold. | low | Same as #18. The test `test_the_ranking_inputs_match_the_digests_for_the_same_candidate` pins that the *inputs* agree; it cannot pin that the *outputs* agree across time, because on the Digest they are frozen and on Browse they are not. |
| 20 | `RedisThrottleAdapter.peek` is exercised only against `StubRedis`, never against a live Redis | low | The stub **deletes expired keys**, which is the one behaviour the window rule depends on, and the parity test runs the same walk against both adapters. A live-Redis test would need a Redis instance in CI; the parity test is the stronger guarantee anyway, because it pins that the fake and the real adapter answer the same question the same way. |
| 21 | `read_save_quota` calls `is_pro()` on every Browse page load, and `is_pro` is an entitlement read | low | Already the case for the gate. The read is one extra call per request, and `is_pro` is documented as the single published entitlement read in the project. Not worth a cache until the profile says otherwise. |
| 22 | `browse_endpoint` clamps `limit` inside the service but the **OpenAPI schema does not declare the bounds** — a client can ask for `limit=1000` and receives 24 | low | The service clamps it (`limit = max(1, min(limit, BROWSE_PAGE_SIZE))`), so the response is bounded either way; the parameter is simply not self-describing. Tightening this would change the generated client types, which is a contract change for a small gain. Worth noting for the frontend work item. |
| 23 | **In `ADAPTER_MODE=fake`, the throttle's state does not survive between requests, so the quota reads `used: 0` after a save.** `ports.registry.get_adapter` calls `adapter()`, constructing a **new** adapter instance on every call — so the in-memory adapter forgets its counters between two requests. Browse is the **first surface to display** the counter, so it is the first place the gap is visible: in a local run, a user saves an event, reloads Browse, and the quota still says `used: 0`. The save itself worked (`is_saved` flips to `true`), and the real Redis adapter *is* shared and does persist, so **production is correct**. | low | Pre-existing behaviour, not introduced by this item — the gate only ever needed the counter within one request. The fix would be to make the fake a **singleton** rather than a fresh instance per call, which touches the registry and every adapter, and is outside this item's scope. **Recorded because the frontend work item will consume this endpoint and a developer testing locally will read it as a bug.** The repo's existing convention for working around it in a test is to patch the port, as `tests/e2e/test_pro_tier_proof.py` does. |

## The thing worth saying plainly

**AD-10 has two halves, and only one of them is enforced.**

The half that *is* enforced is the substitution rule: two explanations that look identical must
never be silently swapped. Two import-linter contracts guard it, and they are good — the Event
Fit is a **package** specifically so a new module inside it is inside the wall by default rather
than outside it until somebody notices. Browse passes both.

The half that is *not* enforced is the persistence rule: *"Relevance Pulse and Event Fit are
persisted, never regenerated."* Nothing in the import linter, the architecture tests, or the
schema can catch a read that recomputes an explanation at render time — and Browse does
compute one.

This is not a Browse-specific lapse; it is a gap in the enforcement mechanism, and Browse is
simply the first read in this codebase that renders an explanation it did not persist. The
Digest persists, the Detail Screen reads the persisted row (`WhyThisOut` says so in its own
docstring), and Browse is the odd one out.

Two consequences worth carrying forward:

1. **The rule and the linter disagree about where the risk lives.** The linter watches for the
   *wrong kind* of explanation. Nothing watches for the *right kind, computed at the wrong
   time*. A "persisted explanations" contract — say, a test that asserts no read module
   imports `why_this_tags` — would close the gap, and the Digest's own structure shows it is
   cheap: `digest_read.py` never calls it.
2. **Browse is not wrong today.** Its tags come from the same `RankingInputs` the score used,
   from the same `domain.ranking` functions the Digest uses, and the design's D2 goal is
   pinned by a test. What is missing is *persistence*, not *correctness*.

I am recording this as **Finding 18 (medium)** and recommending it as its own work item under
the `browse-surface` intent, rather than folding it in here. Widening a work item's scope
without approval is the habit this run exists to break — and the honest statement is that
**the approved design did not mention persistence at all**, so this is a gap in the design,
not a departure from it.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-029*

---

# Code Review: The Browse Shell and Grid

## Scope

```
frontend/app/browse/page.tsx                        | 149 ++  (the route)
frontend/app/browse/loading.tsx                     |   6 +  (the skeletons)
frontend/components/browse/browse-hero.tsx           | 123 ++ (the hero)
frontend/components/browse/browse-card.tsx           | 377 ++ (one card)
frontend/components/browse/browse-grid.tsx           | 125 ++ (the two sections)
frontend/components/browse/browse-more.tsx           | 165 ++ (the chunk loader)
frontend/components/browse/browse-states.tsx         | 131 ++ (empty / error / loading)
frontend/lib/browse-labels.ts                       | 154 ++ (the words)
frontend/lib/browse-read.ts                         |  68 ++ (the server read)
frontend/tests/browse-rendering.test.tsx            | 525 ++ (the rendered document)
frontend/tests/browse-a11y.test.tsx                  | 231 ++ (the axe gate)
frontend/tests/browse-boundary.test.ts               | 214 ++ (the source scan)
frontend/tests/browse-labels.test.ts                 | 169 ++ (the pure functions)
```

Fourteen files, twelve of them new. **No change to `styles/tokens.css`, no change to the
shared shell, and no new colour, spacing or CSS variable** — which the acceptance criteria
required and which the token reset would have turned into silently-missing CSS had they
been tried.

## Standards compliance

| Rule | Status |
|---|---|
| AD-10 — the page renders the payload and decides nothing | **kept, and made testable.** The page does not rank, sort, re-tier or re-bucket. The one thing the review found here was the section-2 count, which was the *client's* arithmetic on `total` rather than the server's statement — see Finding 5. |
| AD-10 — never substitute the Event Fit for the Relevance Pulse | **kept.** The card's visible label is "Relevance" and its accessible name is "Relevance N of 5". The review found the accessible name said "Confidence" — see Finding 7. |
| AD-12 — a public surface never uses a session; Browse is authed | **kept.** `getSession()` → `homeRoute(session)` decides the redirect, and a signed-out reader is redirected rather than shown an empty city. |
| AD-19 — `frontend/lib/api/` is generated; the backend is reached only through `api` | **kept.** The chunk loader uses `api.GET("/api/personal/browse", …)`. `fetch` is banned in `components/` by a lint rule, and the build is the real check that the client boundary holds. |
| The product has exactly one animation and one transition | **kept.** `.skeleton-pulse` is the only animation; the card's hover is a colour swap with **no** transition class, because `tests/architecture.test.ts` scans every `.tsx` for `transition-*`/`duration-*`/`ease-*`. |
| No new colour, CSS or spacing tokens | **kept.** Every off-scale size is a bracketed exact value — the codebase's own idiom. `tests/spacing-scale.test.ts` explicitly leaves bracketed values alone. |
| Colour is never the sole carrier (WCAG 1.4.1) | **kept, and strengthened.** The stripe's meaning is in words, the event's state is in a badge *and* in the link's accessible name, and the indicator's number lives in the accessible name. |

## Findings

The review was run by a read-only agent against the executed code and then **every finding
was confirmed by hand before it was acted on**. Eight defects were found; all eight are
fixed. Three of them are worth stating plainly, because the test suite that was supposed to
catch them did not.

### 1. [Architecture] The chunk loader threw away the final chunk — **critical**

`browse-more.tsx` began with:

```tsx
if (remaining === 0) return null;
```

That early return sat **above** the appended list, so when the pool ran out the component
returned nothing at all — and with it, every card the last chunk had just delivered. The
last screen of events never appeared, and the page stopped short of the count the hero had
promised.

**The fix** moves the guard down to wrap only the anchor, and the appended list renders
whenever it has cards. The anchor's visibility is a separate decision from the list's
existence — they were the same decision and should not have been.

**Why the suite missed it:** no test covered `BrowseMore` at all. The component was written
after the test file, and the file tested the page, which renders `BrowseMore` with
`remaining > 0` on every fixture. The defect lived entirely in the branch the fixture never
reached.

### 2. [Architecture] A double-click issued two requests for the same offset

`aria-disabled` is advisory. It tells assistive technology the control is unavailable; it
does **not** stop a second click from firing. Two responses for the same offset both
appended, so the page showed the same events twice — under duplicate React keys — and the
next request skipped a chunk of the pool entirely.

**The fix** is a re-entrancy guard *inside* the handler (`if (busy) return;`), not on the
element. The element's `aria-disabled` stays, because it is still the right thing to tell a
screen reader; it simply was never the thing stopping the second click.

### 3. [Architecture] The anchor's `href` pointed at the chunk the reader was already looking at

`nextOffset` was `offset + appended.length`, which is `0` on first render — so the anchor
named `/browse?offset=0` while sitting under a page of 24 cards. The `href` is not decoration:
the route honours `?offset=`, so a middle-click, a "copy link address", or a reader with
JavaScript off would land on the *first* page.

**The fix** is `offset + cards.length + appended.length` — the next chunk starts where this
page's cards end. **And the route was changed to honour `?offset=`** (Finding 4), so the
link is now true in both directions.

### 4. [Architecture] The route ignored the offset it was given

`app/browse/page.tsx` never read `searchParams`, so the anchor's `href` was a link to a URL
the page ignored — the finding above was half a symptom of this.

**The fix** adds a `searchParams` prop, a `requestedOffset()` helper, and a malformed offset
falls back to the first page. The route is `force-dynamic`, so this costs nothing.

### 5. [Testing] The section-2 count was the client's arithmetic

The plan said section 2's meta counts *"what is still to come"*. The review flagged this as a
client-side inference, and **the mockup settles it**: the hero's pill says *"147 events this
week"* and section 2's meta says *"144 events"* — and 147 − 3 (the first section's cards) is
144.

So N is the pool's **tier-2 size**, not the remainder. Reading it as a remainder would
announce *"37 events"* above a grid of 2 cards — a heading that contradicts the thing it
heads. The code now computes `total − tier_2_starts_at`, and the test asserts the mockup's
own arithmetic.

### 6. [Testing] The tooltip ids collided on every card on the page

`browse-badge-Official` was the same string on every official card on the grid. A DOM `id`
must be unique, and `aria-describedby` resolves to the **first** match — so a card's
description was another card's element.

**The fix** derives the ids from the event's own id (`browse-confidence-{event_id}`), which
is what `pulse-card.tsx` already does. The house pattern was right; this file had not
followed it.

### 7. [Accessibility] The accessible name said "Confidence" where the card said "Relevance"

Two indicators on this product look identical on screen — the Relevance Pulse and the Event
Fit — and AD-10 forbids substituting one for the other. The words are the only thing keeping
them apart, and the card's own accessible name called its indicator *"Confidence 4 of 5. …"*
while the visible label said "Relevance". **"Confidence" appears nowhere on the visible
card.** It also used the unclamped value, so the button could say "1 of 5" while the card's
name said "0 of 5".

**The fix** is one clamp, three consumers: the dots, the button's accessible name and the
card's accessible name all read the same clamped value, and all three say "Relevance".

### 8. [Accessibility] A cancelled event said nothing about being cancelled

The server routes cancelled and postponed events to the **amber** stripe, so a cancelled
event rendered as a "Must-know" card with nothing on it saying it was cancelled. For a
sighted reader the state was invisible, and only the link's accessible name carried it.

**The fix** adds the event-state badge — `component.card.pulse.digest`'s anatomy, which
Browse borrows. The badge is `aria-hidden` and the **link** carries the state in words, so
the fact is announced once and legible at a glance. The Browse payload carries `status` but
not `is_sold_out`, so the sold-out branch cannot fire here — and a badge for a state the
payload cannot express would be a badge invented by the client.

### Also fixed, smaller

| # | Finding | Fix |
|---|---|---|
| 9 | `windowDateLabel` threw a `RangeError` on a timezone the runtime does not know | The `Intl` call is wrapped; the fallback is the date in UTC. The zone is a string the server wrote — a typo would have taken the whole page down over a label. |
| 10 | `resetPhrase` rounded a duration **up**, over-promising the time left (90 minutes → "2h") | `Math.round` → `Math.floor` in the minutes, hours and days branches. |
| 11 | `resetPhrase(86400)` returned "1d" — the phrase for *every* user, hiding the number the payload carries | The hour branch now owns `<= 24`, so a day reads "24h". |
| 12 | The empty state's heading was an `<h2>` on a page with **no `<h1>`** | The empty state *replaces* the hero, so its heading is the page's `<h1>`. An `<h2>` with no `<h1>` before it breaks the heading order the way a skipped level does. |
| 13 | `badge.warn` lost its warning colour — the ⚠ rendered in plain ink | `text-signal-warn`, which is `PulseCard`'s `BadgeGlyph` rule. A `crawled_html` source is "Unverified", and without this it lost the one signal separating it from a merely-official source. |
| 14 | The card showed up to every tag the server sent | `MAX_WHY_THIS_TAGS` — `PulseCard`'s own cap. |
| 15 | The chunk loader's success was silent | A polite live region says how many events arrived. The cards appear *below* the reader, outside the focus, and nothing had changed where they were. |
| 16 | The anchor announced as a link but behaved as a button | `role="button"`, with the `href` kept. The click is intercepted and the chunk is fetched in place — no navigation happens — so announcing it as a link lies about what activating it does. The `href` stays because the chunk's real URL is the anchor's `href`. |
| 17 | `has_more` was on the payload and the client was doing arithmetic on `total` instead | The anchor's visibility is now the server's statement. A pool whose `total` disagrees with its card count would otherwise strand the reader on an anchor that leads nowhere, or hide a chunk that is really there. |

### Open — recorded, not fixed

| # | Finding | Severity | Why not fixed here |
|---|---|---|---|
| 18 | **The card renders the server's `status` but the Browse payload has no `is_sold_out`.** A sold-out event cannot carry a sold-out badge on Browse, though it can on the Digest. | low | **The payload does not carry the field.** Adding it is a backend schema change to an endpoint whose contract this item's own backend sibling just set. A badge for a state the payload cannot express would be a badge invented by the client — which is exactly what AD-10 forbids. |
| 19 | The **card has no Save affordance** — the `data-browse-save-slot` is an empty element. | low | **Deliberate, and in the plan.** The Save affordance is its own work item; this one leaves the slot for it rather than shipping a control that does nothing. The slot is marked so the next editor knows the absence is planned. |
| 20 | The **sidenav's Browse row** is still an inert "Coming soon" span. | low | `browse-nav-activation` is a separate item with its own scope. Linking it now would put a link in a surface whose route has no error state yet. |
| 21 | The **chunk loader has no test of its own.** | low | The findings above say what a test would have caught, and two of them (Findings 1 and 2) are exactly what a `BrowseMore` test would have caught. The component is now correct, but **the coverage gap that let Finding 1 through is still a gap**, and the next person to touch this file inherits it. The axe gate does cover the appended list's *markup*; it does not cover the *load*. Recorded rather than folded in, because writing the interaction test is a work item rather than a reviewer's fix. |

## The thing worth saying plainly

**The gate was green and the page was still broken.**

The review found a critical defect — the final chunk of every pool silently discarded — in
code that passed every test, lint, typecheck and the production build. The reason is a
coverage shape that is easy to mistake for coverage: `BrowseMore` was exercised by the page
tests, but only on the branch where the pool has more in it. **A component can be covered
and still have its most important branch untested.**

Two of the seventeen findings (1 and 2) live in that gap, and a third (4, the route ignoring
`?offset=`) is the reason the anchor's `href` was never checked. So the honest count is that
**three of the seventeen defects were reachable only by a test that did not exist.**

That is the lesson worth carrying forward, and it is more useful than any individual fix:
*when a page delegates to a client island, the island's own branches need their own
tests — rendering the island on a happy-path fixture does not test the island.* The
appended-list markup is audited by the axe gate; the *load* is not tested at all, and
Finding 21 records that as still open rather than pretending the file is finished.

## Verification

The full gate, re-run after every fix:

```
pnpm test        2118 passed (127 files)   0 failed
pnpm lint        clean
pnpm typecheck   clean
pnpm build       clean — /browse renders as ƒ (Dynamic, server-rendered on demand)
```

**Node 24 is required.** `frontend/package.json` asks for `node >= 24.15`; the machine's
default is v20, on which undici's zstd binding throws and vitest's forks worker fails to
start ~100 times. The failures are environmental, not the change's. Every command above was
run with `PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH"`.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-029*

---

# Code Review: The Inline Keyword Search

## Scope

```
frontend/lib/browse-search.ts                      | 240 ++ (the grammar, pure)
frontend/lib/digest-labels.ts                      |  47 + (the alias table)
frontend/components/browse/browse-search.tsx       | 380 ++ (the client island)
frontend/components/browse/browse-grid.tsx         |  29 + (presentational now)
frontend/components/browse/browse-more.tsx         |  90 + (the anchor only)
frontend/components/browse/browse-states.tsx       |  52 + (the no-match state)
frontend/app/browse/page.tsx                       |  14 + (the island, not the grid)
frontend/tests/browse-search.test.ts                | 105 ++ (the grammar)
frontend/tests/browse-rendering.test.tsx           | 200 ++ (the rendered document)
frontend/tests/browse-boundary.test.ts             |  60 ++ (the source scan)
frontend/tests/browse-a11y.test.tsx                |  50 ++ (two more axe gates)
frontend/tests/digest-labels.test.ts               |  60 ++ (the alias table)
```

Twelve files. **No change to `styles/tokens.css`, no change to the shared shell, and no
backend change at all** — the server's why-tag vocabulary is untouched, because it is a
persisted, server-stated fact (AD-10) and a search alias is a frontend *translation* of it.

## Standards compliance

| Rule | Status |
|---|---|
| AD-10 — the page renders the payload and decides nothing | **kept, and the review found two ways the filter broke it.** The filter could promote a tier-two card into tier one, and the chunk's cards were rendered twice. Both are fixed — see Findings 1 and 2. |
| AD-10 — never substitute the Event Fit for the Relevance Pulse | **kept.** The two vocabularies are translated separately; `this_weekend` and `weekend` stay two keys for two ideas, and the client's alias table does not merge them. |
| AD-12 — a public surface never uses a session; Browse is authed | **kept, unchanged.** |
| AD-19 — `frontend/lib/api/` is generated; the backend is reached only through `api` | **kept.** The island's chunk load uses `api.GET("/api/personal/browse", …)`. `fetch` is banned in `components/` by a lint rule, and the boundary test asserts the surface never calls it. |
| The product has exactly one animation and one transition | **kept.** The input has a focus ring, not a transition class — `tests/architecture.test.ts` scans every `.tsx` for `transition-*`/`duration-*`/`ease-*`. |
| No new colour, CSS or spacing tokens | **kept.** Every off-scale size is a bracketed exact value. `tests/spacing-scale.test.ts` caught one (`mt-7`) during the build; it is `mt-8` now. |
| Colour is never the sole carrier (WCAG 1.4.1) | **kept.** The count line is words; the clear button is a labelled control; the no-match state is a heading and a sentence. |
| A lock needs enforcement | **kept, and strengthened.** A-11's lock is asserted by both a source scan *and* a rendering test, and the rendering test is scoped to Browse's own frame — the shell has a date input of its own, and a rule that scanned the whole document would be a rule about the shell. |

## Findings

The review was run by reading the executed code and then **confirming every finding by
hand before acting on it**. Two defects were found; both are fixed. Both are worth stating
plainly, because **the test suite that was supposed to catch them did not** — and the
second one is the more interesting of the two.

### 1. [Architecture] The filter could promote a tier-two card into tier one — **high**

`browse-grid.tsx` computed its split as:

```ts
const split = Math.max(0, Math.min(tierTwoStartsAt, cards.length));
```

**`tierTwoStartsAt` is an index into the *pool* the server sent** — `browse_read.py:363`
computes it as `max(0, min(BROWSE_TIER_1_SIZE - offset, len(cards)))` — but `cards` here
was the **filtered** list. Slicing the filtered list at the pool's index says "the first
three survivors are tier one", and when the filter removed all three of the pool's tier-one
cards, the first three survivors were tier-*two* cards.

**The reproduction.** A pool of four — three tier-one cards and one tier-two — with
`tier_2_starts_at: 3`. A search matching only the tier-two card produced:

```
SECTIONS AFTER FILTER: [ 'tier-1', 'tier-2' ]
  items: 1  heading: 3 worth your attention today
  items: 0  heading: More this week
```

**"3 worth your attention today" was heading a card the server had explicitly put in tier
two.** That is AD-10's exact failure — a client-side re-tiering — wearing a search's
clothes, and it is the one thing this codebase spends the most words forbidding.

**The fix** changes the grid's contract. It no longer slices at the server's index; it
slices at a **count of the pool's tier-one cards that survived the filter**, computed by
`survivingTierOneCount()` in `lib/browse-search.ts` against the *loaded set* rather than
the filtered one. A filter makes tier one **smaller**; it never makes it longer.

**Why the suite missed it:** every existing fixture had `tier_2_starts_at: 1` and no
filtering, and the grid was tested only unfiltered. The defect needed *both* a filter and a
pool whose tier-one prefix the filter removed — a combination no test constructed.

**The fix also changed the second section's count.** It read `total - split`, and `split`
was the server's index; under a filter that would have made it count the pool rather than
the section, so the meta would have read "39 events" above a grid of one card while the
count line above it said "1 event matched". The page would have contradicted itself twice
over. Under a filter the meta now counts what the section holds.

### 2. [Architecture] The chunk's cards were rendered twice — **high**

Moving the chunk's state into the search island made the island hand the **whole loaded
set** to the grid. But `browse-more.tsx` still rendered the appended list itself, in a
`<ul data-browse-appended>` of its own below the grid.

**The reproduction.** A page with one card and a chunk of one:

```
CARDS: 3
TITLES: [ 'One card', 'Chunked gallery', 'Chunked gallery' ]
```

**Every chunked event appeared twice on the page.** The card count was wrong, the page
had two `<li>`s with the same React key in two different lists, and a reader saw the same
event twice.

**The fix** gives the chunk's cards to the grid, which is where they belong: the server's
tier formula puts every card past the first section in tier two, so the chunk belongs in
the grid's second section. `BrowseMore` is now the anchor and the announcement, and draws
no cards at all.

**Why the suite missed it:** the previous item's review left the chunk loader untested —
Finding 21 of that review recorded it as "still open", and this item moved the loader's
state without closing the gap. Nothing rendered a chunk, so nothing could see it twice.

### Also fixed, smaller

| Finding | Category | Fix |
|---|---|---|
| `BrowseSearchEmpty` did `terms.map((term) => term).filter(Boolean)` | Code quality | `terms.filter(Boolean)` — a `.map()` that maps a value to itself. |
| `browse-more.tsx` imported `BrowseCardOut` after the loader stopped drawing cards | Code quality | The unused import is gone. `pnpm lint` caught it. |

### Reviewed and accepted

These were looked at closely and left as they are.

| What | Why it stays |
|---|---|
| The island serialises the first page's cards as client props rather than server-rendering them | The AC forbids a network request per keystroke and a query typed into a client island cannot reach a server-rendered grid. The cost is the AC's own trade. Recorded as deviation #5. |
| The placeholder says `tag:music`, and `tag:music` matches nothing | The placeholder is fixed word for word by the AC, and `music` has no server-side counterpart. The conflict is recorded as deviation #2 rather than repaired by editing a fixed string or by aliasing `music` onto a chip that means something else. |
| The hint line advertises twelve tags, not the design's ten | Four of the design's ten have no server-side fact. A grammar line that teaches four dead tags teaches the reader to distrust the grammar. `digest-labels.test.ts` asserts every advertised token resolves to something. |
| The double-click guard uses `busy` state rather than a ref | **Probed, and the state guard holds.** A pending request plus two clicks produced **one** request — React flushes `setBusy(true)` between the two discrete click events. The guard is now asserted by a test rather than by prose. |
| `aria-labelledby="browse-tier-1"` / `"browse-tier-2"` are static IDs | One grid per page. The IDs are stable strings on a single-instance surface, and the axe gate confirms the `region` rule is satisfied. |

### Open — recorded, not fixed

| # | Finding | Severity | Why it is not fixed here |
|---|---|---|---|
| 1 | The four design tags with no server-side counterpart (`music`, `food`, `indoor`, `rooftop`) match nothing | Medium | Fixing it means inventing four server-side chips, which changes the product's vocabulary to fit a placeholder string. The why-tag set is a persisted fact. Recorded as deviation #1 and as a spec conflict in deviation #2. |
| 2 | The search is chunk-bounded: a match past the loaded chunk does not appear until that chunk loads | Low, by design | The AC requires this to be *stated*, not fixed. It is stated in the component's own doc comment, and the count line makes the gap visible ("N events matched · M of M events total"). |
| 3 | The chunk loader's *request* was untested until this review | — | **Closed by this review.** Six tests now cover the offset, the advancing offset, the append, the double-click guard, the failure path, and the query reaching the chunk. |

## The thing worth saying plainly

**Both defects were found by reading the code, not by running the suite.** 2,186 tests were
green — every one of them passing — while the page was promoting tier-two cards into tier
one and showing every chunked event twice.

The shape of both failures is the same: **a filter is a narrowing, and the code that
consumed the filtered list was written for the whole list.** The grid sliced the filtered
list at an index that belonged to the pool. The loader drew the chunk that the grid was
already drawing. Neither is exotic, and neither would have been caught by a test that
asserted "the search filters" — because the search *did* filter; it was what happened
*downstream* of the filtering that broke.

**The lesson is about coverage shape, not coverage volume.** The previous item's review
left the chunk loader untested and said so, explicitly, in Finding 21. This item moved the
loader's state into the island and did not close that gap — so the gap was inherited, and
the defect that lived in it was inherited too. The gap is closed now: the loader has six
tests of its own, and the grid's split is asserted against the pool rather than against
the filtered list.

**The probes were the point.** Both defects were found by *running* the code with a
deliberately awkward input — a filter that removed the whole tier-one prefix, and a chunk
that arrived — and reading what the page said. A test that only ever filters and checks
"the right cards are on screen" cannot see either failure, because both are about *where*
the surviving cards are and *how many times*.

## Verification

```
pnpm test        2203 passed (128 files)   0 failed
pnpm lint        clean
pnpm typecheck   clean
pnpm build       clean — /browse renders as ƒ (Dynamic, server-rendered on demand)
```

Up from 2,095 tests in 127 files at the start of the previous item: **+108 tests**.

| File | Before | After | Delta |
|---|---|---|---|
| `tests/browse-search.test.ts` | — | **43** | +43 (new file) |
| `tests/browse-rendering.test.tsx` | 35 | **68** | +33 |
| `tests/browse-boundary.test.ts` | 20 | **27** | +7 |
| `tests/browse-a11y.test.tsx` | 6 | **8** | +2 |
| `tests/digest-labels.test.ts` | 11 | **15** | +4 |
| **Total** | 2,095 | **2,203** | **+108** |

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-029*

---

# Code Review: The Inline Save Button

## Scope

```
frontend/components/browse/browse-save.tsx           | 439 ++ (the island — new)
frontend/components/browse/browse-card.tsx           | 409 ++ (mounts the island)
frontend/components/browse/browse-grid.tsx           | 192 ++ (passes the quota down)
frontend/components/browse/browse-search.tsx         | 395 ++ (passes the quota down)
frontend/app/browse/page.tsx                         | 159 ++ (passes the quota down)
frontend/lib/browse-labels.ts                        | 192 ++ (the spent-quota label)
frontend/tests/browse-save.test.tsx                  | 736 ++ (new — 35 tests)
frontend/tests/browse-boundary.test.ts               | 404 ++ (the two-islands rule)
frontend/tests/browse-rendering.test.tsx             | 1147 ++ (the card's Save button)
frontend/tests/browse-a11y.test.tsx                  | 289 ++ (the spent-quota axe gate)
```

(The whole Browse surface is new in this run, so the column is total line count rather
than a diff against a committed baseline.)

**No backend change, no new endpoint, no token, no CSS.** The item's whole shape is that the
two 409s the backend already distinguishes are told apart by `code` and rendered as two
quiet lines under a button. `POST` and `DELETE /api/personal/saved-events/{catalog_event_id}`
are the endpoints the Detail Screen's action row already uses, and they are the endpoints
this uses.

## Standards compliance

| Rule | Status |
|---|---|
| AD-10 — the page renders the payload and decides nothing | **kept, and the review found the one place it nearly broke.** The two refusals are told apart by `code` and never by a string match of the message — the backend owns the wording and will change it, and a client that matched on prose would break on a reword. The quota wall is *derived* from the payload's `cap` and `used`, never re-derived from a sentence the client rendered. |
| AD-19 — `frontend/lib/api/` is generated; the backend is reached only through `api` | **kept.** The island calls `api.POST` / `api.DELETE` against the generated paths. `fetch` is banned in `components/` by a lint rule, and the boundary test asserts the surface never calls it. |
| A hand-written copy of the contract is the thing AD-19 exists to prevent | **broken on arrival, and fixed by this review.** The quota's shape was hand-declared in four files while `lib/browse-read.ts` already exported the generated `BrowseQuota` — an export that was itself unused. See Finding 1. |
| The product has exactly one animation and one transition | **kept.** The morph uses the existing `.fade-in`, whose token is `--motion-fade-in: opacity 240ms ease-out` — the criterion's 240ms and the token's 240ms are the same number. `tests/architecture.test.ts` bans every Tailwind `transition-*`/`duration-*`/`ease-*` class in a `.tsx`, so a hand-written transition would have failed the build. |
| Under `prefers-reduced-motion: reduce`, the 240ms morph collapses | **kept by construction.** `styles/globals.css` sets `.fade-in { transition: none; }` inside the reduced-motion block. Reusing the token is what makes this true for free — the criterion asked for a property, and the token already had it. |
| Neither refusal may interrupt — no modal, no toast | **kept, and asserted by a test that checks the *absence* by name.** It queries for `[role="dialog"]`, `[aria-modal="true"]`, `[role="alertdialog"]` and a toast container. A test that only checked the copy would pass while a modal appeared. |
| Colour is never the sole carrier (WCAG 1.4.1) | **kept, and strengthened by Finding 2.** The spent allowance's *appearance* was decided by CSS emission order rather than by the component — so the label and the appearance could disagree. |

## Findings

The review was run by reading the executed code and then **confirming every finding by
measurement before it was acted on**. Two defects were found; both are fixed. One of them
is the more interesting of the two, because it was invisible to every gate the project has.

### 1. [Architecture] The quota's shape was hand-written in four files — **medium**

`browse-save.tsx`, `browse-card.tsx`, `browse-grid.tsx` and `browse-search.tsx` each
declared the quota inline:

```ts
quota: {
  used: number;
  cap?: number | null;
  is_pro: boolean;
  resets_in_seconds: number;
};
```

**And `lib/browse-read.ts` already exported the generated one** — `export type BrowseQuota =
components["schemas"]["BrowseQuotaOut"];` — which nothing imported. The generated export sat
there unused while four hand-written copies of the same shape were threaded down the tree.

**Why this is not a style nit.** A hand-written copy of the contract is precisely what AD-19
exists to prevent: it is a copy that can drift. The day the server adds a field to
`BrowseQuotaOut`, the hand-written copies would keep the old shape and the typecheck would
keep passing — the drift would be invisible until a field was read. The generated export was
already written, already correct, and already unused.

**The fix** is four import changes and four type substitutions. Each of the four now names
`BrowseQuota`, and the shape is stated once, by the generator.

### 2. [Visual behaviour] The spent button's colour was decided by CSS emission order — **medium**

The blocked button carried **two** ink colour classes at once:

```tsx
labelColour,                       // "text-ink-secondary" when the state is idle
blocked ? "text-ink-faint" : "",
```

**The reader saw the wrong colour.** Tailwind sorts utilities by their own name, *not* by
the order they appear in `className`. The review measured this against the project's own
CSS rather than reasoning about it, and the shipped stylesheet settles it:

```
$ grep -o "\.text-ink-faint{...}\|\.text-ink-secondary{...}" .next/static/chunks/*.css
.text-ink-faint{color:var(--color-ink-faint)}
.text-ink-secondary{color:var(--color-ink-secondary)}

text-ink-faint     at byte 29895
text-ink-secondary at byte 30083     <- later, so it wins
```

**`text-ink-secondary` wins.** So the spent button rendered in the *ordinary* ink, not the
muted one — the button that refuses every press looked exactly like the button that accepts
them. The only difference the reader could see was the label text and the grey cursor.
Every gate was green: the tests passed (the class *was* present), lint passed, typecheck
passed, and the build passed.

**The fix** makes the muted colour a *replacement* rather than an addition — one colour
class reaches the DOM, chosen by the component — and the assertion now counts the ink
classes rather than checking that one of them is present:

```tsx
blocked ? "text-ink-faint" : labelColour,
```

```ts
const inks = (button().className.match(/text-ink-\w+/g) ?? []);
expect(inks).toEqual(["text-ink-faint"]);
```

**Why the count and not a check.** "Which of these two classes wins" is a question about
Tailwind's internals and about the order the design tokens happen to be declared in; it
would be a brittle assertion that could break on a Tailwind upgrade without the component
being wrong. "How many colour classes are on this button" is a question about *this
component*, and it is the one that can be enforced here.

**The mutation probe confirms the test is real.** Reverting the fix to the additive form
and re-running:

```
× carries exactly one ink colour, so the muted one is the one that applies
  AssertionError: expected [ 'text-ink-secondary', …(1) ] to deeply equal [ 'text-ink-faint' ]
  Tests  1 failed | 34 passed
```

The test fails on exactly the defect it was written for, and nothing else moved.

### Also fixed, smaller

| # | Finding | Fix |
|---|---|---|
| 3 | The plan's deviation #5 claimed the server's clashing event name was "carried in the DOM from `details.conflicts[0]`". **The implementation never reads `details.conflicts`.** | **The plan was corrected, not the code.** The AC asks for a link "to the event detail" — the event being saved — and that is what the "Open" link does. The plan's claim was an over-reach, and a plan that over-claims is worse than one that admits a limit. Both the paragraph and the deviation table now say so, and the correction is marked as such rather than silently rewritten. |

### Reviewed and accepted

These were looked at closely and left as they are.

| What | Why it stays |
|---|---|
| **The two 409s are treated asymmetrically** — a clash renders "Saved ✓", a cap renders "Save" | **Correct, and it is the item's whole point.** The backend's own words differ: `api.py:398` says a conflicting save means *"the save row exists, the pair is active, and the flow is waiting for a choice"* — the save **happened**; `saved_events.py:106` says the cap is *"refused before anything is written: no partial `SavedEvent`, no audit row, no conflict pair"* — the save **did not happen**. Rendering both as a failure would say "couldn't save that" about a save that was saved, and would invite a second press that would receive the same answer. |
| The wall is **derived at render** from `cap` and `used`, not a fourth state in the machine | **Correct.** A `blocked` state could get stuck when the allowance reset, and a reset the payload never announces would leave it stuck forever. The comment says so. |
| The lockout is a **flag cleared by a timer**, not a `Date.now()` compared during render | **Correct, and necessary.** The component does not re-render when the clock passes a deadline, so a timestamp read in render would leave the button disabled forever. |
| The in-flight guard is in the **handler**, not only on `disabled` | **Correct.** A `<button disabled>` is not a guarantee — a click dispatched in the same tick as the state change can still arrive. The save is idempotent server-side, so a duplicate is safe but wasteful; the guard costs one line. |
| The `Esc` handler is on the **wrapper**, not on the button | **Correct, and it was the item's subtlest trap.** A disabled button fires no key events at all, and the button *is* disabled while a request is in flight — the only moment the cancel exists for. A handler on the button would never run. The build's own test caught this: the original test passed because `fireEvent.keyDown` dispatches regardless of `disabled`, so it was proving something a browser would not do. |
| `Esc` resets the label and **does not claim the save did not happen** | **Correct, and it answers the item's technical note.** `save_event()` writes inside `transaction.atomic(using=PERSONAL)` and commits on return — **there is no server-side rollback**, no abort path, no compensating write, no cancellation hook. The honest scope is the client-side label, and the generation counter makes the in-flight answer a no-op. |
| The refusals are `role="status"`, not `role="alert"` | **Correct.** A refusal is information, not an emergency; an assertive region would interrupt a screen reader mid-sentence. |
| The cap sentence uses the **criterion's wording**, not `UpgradePrompt`'s "the server's sentence, rendered verbatim" | **Deliberate, and recorded as deviation #2.** `UpgradePrompt` exists to render a server's sentence where there is no criterion; here the criterion *is* the sentence, and the AC says so word for word. The cap's *number* is still the payload's — it reads `details.cap`. |
| The wrapper `<div>` carries an event handler and no `role` | **Correct.** It is a layout container, not a control, and it has no focusable content of its own. The axe gate is green on the spent-quota fixture. |

### Open — recorded, not fixed

| # | Finding | Severity | Why it is not fixed here |
|---|---|---|---|
| 1 | **Criterion 13 cannot be asserted by a DOM test.** "Under `prefers-reduced-motion: reduce`, the 240ms morph collapses to an instant label swap." jsdom evaluates no media queries, so no test can observe the reduced-motion branch. | low | **Satisfied by construction rather than by assertion.** The morph reuses `.fade-in`, and `styles/globals.css` already sets `.fade-in { transition: none; }` inside `@media (prefers-reduced-motion: reduce)`. The property is the token's, not the component's, so it is true by the existing rule rather than by anything this item wrote. A test that pretended to check it would be a test that could not fail. Recorded in the test report as the one thing the criterion cannot be tested for. |
| 2 | The `Esc` cancel **abandons the answer but not the request** — the request is still in flight and will still save server-side. | low | **The server does not offer a rollback**, so there is nothing to cancel to. The item's technical note asks for exactly this check, and the answer is that the honest scope is the label. The alternative — hiding the fact that the save happened — would be a guarantee the server does not make. |
| 3 | The spent allowance's **countdown is not shown on the card** — the payload carries `resets_in_seconds` and the button does not use it. | low | Outside the criteria. The quota note in the hero already states the reset, and a second statement of it under every button would be a wall of numbers. Recorded rather than folded in. |

## The thing worth saying plainly

**The button that refuses every press was painted in the colour of the buttons that accept
them.**

Every gate was green. 2,244 tests passed, lint was clean, typecheck was clean, the
production build succeeded. The class `text-ink-faint` was *in the DOM* — a test asserted
`expect(button().className).toContain("text-ink-faint")` and passed — and the button still
rendered in the wrong colour, because a second colour class was also on it and CSS
resolved the pair by emission order rather than by the component's intent.

**This is the same lesson the previous two reviews in this run kept arriving at, from a new
direction.** The shell-and-grid review found a critical defect in code that passed every
gate: the final chunk of every pool was silently discarded. The search review found two
high-severity defects in code that passed every gate: a filter promoted tier-two cards
into tier one, and every chunked event appeared twice. Both were found by *running* the
code, not by running the suite.

This one was found by **measuring the artefact**. The question was not "is the class
there?" — it was "which of the two classes on this element actually applies?" — and the
answer was in the shipped CSS, at a byte offset. A component can pass every assertion
about itself and still render wrongly, because rendering is decided downstream of the
component, by a tool whose rules the component does not state.

**The generalisable form: a test that asserts a class is *present* cannot detect that a
class is *inert*.** The fix is not a better assertion about Tailwind's internals — it is a
component that puts one colour on the element, so there is nothing for the cascade to
resolve. The count-based test then pins the invariant that keeps it that way.

## Verification

The full gate, re-run after every fix:

```
pnpm test        2246 passed (129 files)   0 failed
pnpm lint        clean
pnpm typecheck   clean
pnpm build       clean — /browse renders as ƒ (Dynamic, server-rendered on demand)
```

**Node 24 is required.** `frontend/package.json` asks for `node >= 24.15`; the machine's
default is v20, on which undici's zstd binding throws and vitest's forks worker fails to
start ~100 times. Every command above was run with
`PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH"`.

Up from 2,244 tests at the start of this review: **+2** — the two colour-class assertions.
The suite grew by 43 tests across the item itself.

| File | Before | After | Delta |
|---|---|---|---|
| `tests/browse-save.test.tsx` | — | **35** | +35 (new file) |
| `tests/browse-rendering.test.tsx` | 68 | **74** | +6 |
| `tests/browse-boundary.test.ts` | 27 | **28** | +1 |
| `tests/browse-a11y.test.tsx` | 8 | **9** | +1 |
| **Total (this item)** | 2,203 | **2,246** | **+43** |

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-029*

---

# Code Review: Retiring the "Coming Soon" Stubs

**Work item**: `browse-nav-activation` · **Mode**: autopilot · **Phase**: review

## Scope

Six files, three of them components and three of them tests. The line counts are measured,
not estimated.

| File | Kind | Lines before → after |
|---|---|---|
| `components/shell/sidenav.tsx` | component | 224 → 255 |
| `components/shell/more-menu.tsx` | component | 82 → 91 |
| `components/shell/bottom-tab-nav.tsx` | component | 185 → 214 |
| `components/shell/nav-routes.test.tsx` | test | 231 → 333 |
| `tests/digest-home-boundary.test.ts` | test | 389 → 441 |
| `app/page.test.tsx` | test | 701 → 713 |

**The "before" column is `HEAD`, not the state at the start of this item.** The Browse
surface landed earlier in this same run and is still uncommitted, so `HEAD` understates
what this item changed. The *item's* own delta is best read from the test counts: **nine
tests added, zero removed**, and the three components changed as described above.

**A note on the honesty of these numbers.** The per-item `+`/`−` diff is not quoted here,
because the tree this item inherited (the previous item's uncommitted work) is not
recoverable from the repository — it was never committed. Quoting a `git diff` against
`HEAD` would have attributed the Browse surface's lines to this item, and estimating the
split by hand would have been a guess dressed as a measurement. The line counts above are
real; the item's own delta is the test count and the prose.

## Standards compliance

| Rule | Status |
|---|---|
| Frontend imports from `frontend/lib/api/` only for backend access (AD-19) | **N/A** — no API call in this item |
| Tailwind classes outside the tokens | **Clean** — the only new class strings are `hover:bg-surface-subtle` and `hover:text-ink-primary`, both existing surface/ink tokens |
| Motion other than `.fade-in` | **Clean** — no `transition-*` / `duration-*` / `ease-*` / `delay-*` / `animate-*` class was added anywhere |
| No literal hex, no `rgb()`/`hsl()` | **Clean** — the boundary test enforces this over all three shell files, and it passes |
| Frontend file names kebab-case | **Clean** — no file was added |
| ESLint (`next/core-web-vitals` + strict) | **Clean** — `pnpm lint` passes |
| Prettier | **One violation found, auto-fixed** — see below |
| TypeScript strict | **Clean** — `pnpm typecheck` passes |
| Tests assert behaviour, not implementation | **Clean** — the DOM assertions query by role and label; the one source-level assertion is justified below |

## Findings

### 1. The bottom bar renders a raw `<a>`, the rail renders `<Link>` — **pre-existing, recorded not fixed**

`TabSlot` in `bottom-tab-nav.tsx` emits a plain `<a href={href}>`. `SidenavItem` in
`sidenav.tsx` emits Next's `<Link href={href}>`. The two rails therefore do not share a
navigation implementation: the rail gets client-side navigation and prefetching; the bar
gets a full document load.

**This is not something this item introduced.** `git show HEAD:frontend/components/shell/bottom-tab-nav.tsx`
shows the `<a>` at line 173 — Timeline and Conflicts already used it before this item, and
this item's Digest slot followed the file's own convention rather than introducing a new
inconsistency inside it.

**Why it was not fixed here.** Swapping `<a>` for `<Link>` in `TabSlot` is a behavioural
change to a component outside this item's scope, touching three existing slots, and it
would need its own check: `<Link>` inside a `<nav>` that is `position: fixed` and
`md:hidden` behaves the same, but the change is not mechanical and the item did not ask
for it. It is recorded here so a reviewer can decide.

**Severity**: low. The bar is mobile-only, the destinations are three, and a full load is
not a correctness problem.

### 2. Prettier: `nav-routes.test.tsx` drifted — **auto-fixed**

`pnpm format:check` flagged `components/shell/nav-routes.test.tsx` (and thirteen other
files, all of them new in this run). The nav-routes drift was **introduced by this item** —
the file was clean at `HEAD` (verified by stashing the six files and re-running
`prettier --check`, which reported "All matched files use Prettier code style!").

**Auto-fixed.** This is a mechanical, whitespace-only change: no token was added, removed,
or reordered in a way that changes behaviour. All fourteen files were formatted, and the
full suite was re-run afterwards — **2255 passed (129 files)**, unchanged.

**Severity**: low, but it would have failed CI's `prettier --check` gate.

### 3. The "Coming soon" filter in `page.test.tsx` is now vestigial — **comment corrected, filter kept**

`app/page.test.tsx`'s six-route-order test filters out spans whose text is `"Coming soon"`
before reading the route name. No route carries that text any more, so the filter is dead
weight — but it is also the guard that keeps the test honest if the next deferred route
lands and brings its note back.

**The filter was kept and its comment was corrected** to say what is now true: it is there
for the next deferred route, not because any current row carries the note.

**Severity**: informational.

### 4. The source-level sweep's regex is the load-bearing part — **reviewed, kept**

`tests/digest-home-boundary.test.ts`'s new assertion extracts the inert branch with
`/if \(!href\) \{[\s\S]*?\n  \}/` and asserts it does not mention Browse. That regex is
**brittle in the way the existing boundary test's regexes already are** — it depends on the
branch's indentation (two spaces before the closing brace) and on the branch being the
first `if (!href) {` in the file.

This is a deliberate consistency with the file's existing pattern: the `does not render an
inert route as an anchor` test above it already uses
`/if \(!href\) \{[\s\S]*?\n  \}/` on the same source. **A new style of assertion in a file
that has one established style would be the inconsistent choice**, and if the indentation
ever changes, both assertions break together and point at the same edit.

**Severity**: informational. The mutation probes in `test-report.md` prove the assertion
fires when the code changes.

## Reviewed and accepted

| # | What | Why it is right |
|---|---|---|
| 1 | **The More sheet's inert branch was deleted, not kept.** | The sheet has exactly one row, Browse, and Browse is a route. There was never a reason for that sheet to carry a disabled `<span>`, so leaving the branch behind would be leaving dead code. The branch is gone from the file entirely — `more-menu.tsx` now contains no `aria-disabled` and no "Coming soon". |
| 2 | **The sidenav's and the bar's inert branches were kept.** | The Technical Notes: *"Nothing here should weaken that rule for whatever route is deferred next."* The branch is the *implementation of a rule the product still states*. Deleting the only implementation of a rule, in the same edit that removes its last user, is how the rule dies quietly. Recorded in the run log as the criterion requires. |
| 3 | **The More sheet's row carries `aria-current="page"`; the More button carries none.** | More is a control, not a route. A screen-reader user on `/browse` needs to be told where they are, and the thing they are in is the sheet's row, not the button that opened the sheet. Both halves are asserted by separate tests. |
| 4 | **Browse's active rule is an equality in both rails.** | Browse has no children — there is no `/browse/*` screen — so a prefix rule would be a claim about routes that do not exist. Timeline and Conflicts take the same rule; Digest and Settings take prefixes because they *do* have children. |
| 5 | **The bar's Digest slot takes the sidenav's prefix rule.** | The Detail Screen is reached by tapping a Digest card, so `/events/*` hangs off Digest in the IA. The sidenav already applied this rule; if the bar did not, the same screen would show Digest active in the rail and nothing active in the bar. |
| 6 | **`usePathname` in `more-menu.tsx` adds no new client boundary.** | All three shell components already carry `"use client"`. Verified, not assumed. |
| 7 | **The `fireEvent` import in `nav-routes.test.tsx` is the only new dependency.** | `fireEvent` is from `@testing-library/react`, already imported on the same line. No new package, no new mock. |
| 8 | **The More-sheet tests open the sheet before asserting.** | The sheet is a `<dialog>` with `open={false}` until the user taps More, so its rows are not in the DOM until then. Asserting without opening would assert on nothing — which is exactly how a test can pass while asserting nothing. |
| 9 | **No security surface was touched.** | No fetch, no URL construction from user input, no auth check, no token. The links are two static literals — `/browse` and `/` — both pointing at routes that exist and are confirmed by the build output. |
| 10 | **The backend is untouched.** | `git diff --stat` shows no change under `backend/` from this item. The change is purely presentational in the frontend shell. |

## Open — recorded, not fixed

| # | Finding | Severity | Why not fixed |
|---|---|---|---|
| 1 | The bottom bar's `<a>` vs the rail's `<Link>` | low | Pre-existing; a behavioural change outside this item's scope. Decided by a reviewer, not by the builder. |
| 2 | The source-level sweep's regex depends on indentation | informational | Deliberate consistency with the file's existing pattern; both regexes break together. |

## The thing worth saying plainly

**The bottom tab's first slot was never a link, and no one noticed, because an inert slot
looks exactly like an active one.**

`git log -p --follow` on `bottom-tab-nav.tsx` shows only the `+` line for the Digest slot,
never a `-` line — it has had no `href` since the digest home shipped. On a phone, the
*first* tab rendered a disabled `<span>` carrying a visually-hidden "Coming soon" — **while
also carrying `active={pathname === "/"}`**. So the bar's own code said "you are on the
Digest" and the same tab said "there is no Digest, yet", on the same screen, at the same
time.

The item this run was given was *"retire the three Browse stubs"*. The Browse stubs were
real and are gone. But the third inert thing in the product was not a Browse stub, and the
item's own criterion — *"the visually-hidden 'Coming soon' text is removed where it referred
to Browse"* — pointed at a place where nothing referred to Browse, because the text that
remained was attached to **Digest**.

**That is the defect worth having found**, and it was found by reading the criterion rather
than by satisfying it literally.

## Verification

```
pnpm test          # 2255 passed (129 files)   — after the Prettier auto-fix
pnpm lint          # clean
pnpm typecheck     # clean
pnpm build         # clean — /browse is ƒ (dynamic)
pnpm format:check  # clean (was 14 files; auto-fixed)
```

**Mutation probes** (in `test-report.md`): seven distinct tests fire across two mutations —
the More sheet's Browse row reverted to an inert `<span>`, and the bar's Digest slot
reverted to no `href`. The source-level sweep fires under both.
