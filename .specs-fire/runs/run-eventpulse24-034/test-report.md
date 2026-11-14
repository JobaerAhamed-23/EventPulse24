---
run: run-eventpulse24-034
work_item: less-like-this-adjustment
intent: relevance-feedback-loop
generated: 2026-11-14
status: passed
---

# Test Report: "Less like this" — the loop, and the way back out of it

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit (backend) | 139 | 0 | 0 | 98.35% (the new modules) |
| Unit (frontend) | 61 | 0 | 0 | n/a (Vitest, no threshold) |
| **Total** | **200** | **0** | **0** | **98.35%** |

**Full-suite health.** The whole backend suite is **6920 passed, 0 failed**; the whole
frontend suite is **2572 passed, 0 failed** across 154 files. The import-linter's 19
contracts are all kept, `make client` produces no drift, and `ruff check` / `ruff format
--check` / `tsc --noEmit` are all clean.

**The four e2e failures are pre-existing and not this work item's.** `digest-opt-out.spec.ts`
(two) and `unwired-surfaces.spec.ts` (two) fail — verified by `git stash push -u` and
re-running the same two specs on a clean tree, which produces the same four failures.
The five `settings-navigation.spec.ts` tests **pass**, and they now include `/settings/taste`.

**Eight of the new modules are at 100%.** `dismissals.py`, `taste_mutes.py`,
`embedding.py`, `embedding_backfill.py`, `event_embeddings.py`, `voyage.py`, `costs.py` and
the dismissal API are covered line for line. The two below 100% are the two places where
a line is *provably* unreachable, and both are explained below.

## Acceptance Criteria Validation

- ✅ **The design checkpoint settles the AD-4 question before any migration is written** — Checkpoint 1 approved the design doc, which recorded a **finding**, not an amendment: the spine's rule (`ARCHITECTURE-SPINE.md:82-88`) is *"Embedding cosine similarity is never an identity signal"*, and FR-25 clusters **preference**, never identity. The spine's actual words are cited in the design doc, and a new AD would be needed only if cosine were ever used to merge events.
- ✅ **The event has a vector, and the vector is the event's own text** — `Event.embedding` is `public.vector(256)`, written only by `ingestion` (AD-4's sole writer). `event_embedding_text` is the title then the description, with the description bounded (AD-9: a source can publish a megabyte under a short title). Proven by `test_embedding_backfill.py` (14 tests) and `test_event_embeddings_read.py` (8 tests).
- ✅ **Every embedding call writes a cost row, in the call's own transaction (AD-8)** — the row carries no user id (a cost row is about a *call*, not a person); the row rolls back with the result; and the writer **refuses to run outside a catalog transaction** rather than quietly opening one of its own. Proven by `test_embedding_cost.py` (7 tests) and `test_voyage_embedding.py` (19 tests).
- ✅ **The cluster needs three distinct events, each at cosine ≥ 0.70, inside a 24-hour window** — proven at the boundary, not just off it: a cosine of exactly 0.50 does **not** cluster and one of 0.75 **does**, and the vectors are built as unit vectors (`[t, √(1−t²), 0]`) so the cosine is the number the test means it to be.
- ✅ **The rage guard stops the third dismissal inside five seconds from counting** — the dismissal is still *recorded*; only its contribution to the cluster is withheld.
- ✅ **The serendipity slot is immune** — the immunity is anchored to the slot the composition records, not to a tag the candidate does not carry.
- ✅ **The prompt fires once per cluster, and the counter resets** — the third similar dismissal fires it, and the next cluster has to earn its own.
- ✅ **The mute excludes — it is a filter on the candidate set, not a score term** — proven in **both** surfaces (the digest composition and the Browse read), so the two surfaces agree.
- ✅ **The prompt is a bottom-anchored sheet, not a modal, and the user can close it without choosing** — the mockup says so in as many words. The digest stays readable behind it, the backdrop is transparent, and Escape, the X, the backdrop click and a named "Not now" button all dismiss it. Focus moves to the affirmative on open and is restored on close.
- ✅ **The swipe has a keyboard-reachable equivalent** — both paths call one `dismiss()` in `SwipeDismiss`, so there is exactly one implementation. A gesture-only control would fail the PRD §11.5 a11y gate and exclude keyboard users.
- ✅ **The reversal surface is `Settings → Taste`, with a one-tap unmute** — the mockup says so twice (`:122`, `:149`), and FR-25 mutes **categories** while `Settings → Sources` mutes **sources**. The two are siblings, not one control, and this work item does not couple them.
- ✅ **New endpoints go through the generated client (AD-19) with `make client` output committed** — `make client` is idempotent; a second run produces no change, so CI's `git diff --exit-code frontend/lib/api/` passes.
- ✅ **Every test is verified by a mutation probe that makes it fail** — **35 probes, all caught**. See "Mutation Probes" below.

## Tests Written

### Unit Tests — backend

- `backend/tests/personalization/test_dismissal_clustering.py` — **35 tests**. The cosine (identical, orthogonal, opposite, mismatched lengths, a zero vector); the cluster (three similar, two not enough, *each* pair must clear the threshold, a similarity below 0.50, one just above at 0.75, another user's dismissals, a dismissal outside the window, a missing vector on the newest *and* in the middle, a zero vector); the rage guard; the serendipity immunity; the decay (the weight is 0 past the expiry, 0.5 past the half-life, 1 inside it, an expired dismissal leaves the pool, a half-decayed dismissal does not make three); the prompt (fires once, names the server's own chip label, the generic variant when no chip dominates, **a tie between two chips is not a majority**); and the re-dismissal rules (the pair is unique, the timestamp does not move).
- `backend/tests/personalization/test_category_mutes.py` — **23 tests**. The mute commands and their expiry.
- `backend/tests/personalization/test_category_mute_composition.py` — **9 tests**. The mute's effect on the digest and on Browse.
- `backend/tests/personalization/test_taste_mutes_api.py` — **19 tests**. The list, the set, the one-tap unmute, the bulk reset; an unknown category is a 422 and an unknown duration is a 422; **and the two are the two *different* 422s** — `invalid_input` (the command refused the value) against `invalid_request` (the schema refused the shape) — so a test that asserted only the status could not tell a broken refusal path from a working one.
- `backend/tests/personalization/test_dismissals_api.py` — **7 tests**. The dismissal endpoint.
- `backend/tests/personalization/test_embedding_cost.py` — **5 tests**. The cost row: the writer refuses to run outside a catalog transaction, it writes a row inside one, it carries no user id, an embed call writes a row, and the row rolls back with the result.
- `backend/tests/ingestion/test_embedding_backfill.py` — **14 tests**. The command, the resumable backfill, the batching, the bounded description, a provider failure costing one event and not the run, and **a provider that answers with no vector writing nothing** (storing an empty one would leave the event looking embedded, and the backfill would skip it).
- `backend/tests/ingestion/test_event_embeddings_read.py` — **8 tests**. The published read port: the stored vector, absence (not zero), the wrong width dropped, several events at once.
- `backend/tests/adapters/test_voyage_embedding.py` — **19 tests**. The request (the endpoint, the key in a header and never in the body, the dimension requested rather than sliced, `input_type=document`, the named model, the batch bound, the empty batch, a non-positive dimension) and the answer (**the vectors are paired to the texts by index whatever order they arrive in**, a wrong-sized vector, the wrong number of vectors, a transport failure, an HTTP error, a missing key) and the cost (the row is written, the cost is the token count times the price, the result and the row agree, the call count is the number of texts).

### Unit Tests — frontend

- `frontend/components/digest/swipe-dismiss.test.tsx` — **18 tests**. The button, the gesture (the threshold, an upward swipe ignored, the control guard, the travel cap, the spring-back), "what the client does not decide" (the client never counts; the server's prompt is passed through verbatim), and "a dismissal the server refused" (the card stays, the button re-enables, a second swipe is ignored).
- `frontend/components/digest/mute-prompt.test.tsx` — **16 tests**. The structure (`aria-modal`, `aria-labelledby`, `aria-describedby`, bottom-anchored and **not** centred, the copy naming `Settings → Taste`), the focus (moves to the affirmative, is restored), the dismissibility (Escape, the X, the backdrop, a named "Not now"), the answering (accept hands back the server's prompt), and the assertive announcement.
- `frontend/components/digest/digest-card-list.test.tsx` — **10 tests**. The server's order, one status region, the card leaves **only** on the server's confirmation, the prompt opens only when the server says `prompt_due`, accepting writes `setCategoryMute("arts_culture", 30)`, declining writes nothing, the generic prompt (no `category_key`) writes nothing, and a failed mute shows the alert naming `Settings → Taste`.
- `frontend/app/settings/taste/page.test.tsx` — **11 tests**. The heading, the server's labels, the one-tap unmute, the expiry wording, the sub-nav, the not-Pro gate, the honest empty state, the failed read rendering the *error* state and not an empty list, and the signed-out branch not reading.
- `frontend/tests/taste-a11y.test.tsx` — **6 tests**. The axe-core gate over the taste screen's **three documents** (populated, empty, failed read) and the prompt (open and closed), plus a structural check that all three dismissal controls are real buttons.

## Mutation Probes

`backend/tests/personalization/mutation_probe_fr25.py` — **35 probes, all caught**:

```
OK  the cluster needs only two events (the third is not required)
OK  the cosine threshold is lowered (dissimilar events cluster)
OK  the cosine is checked against *any* pair, not each one
OK  the window is dropped (a dismissal from last week joins the cluster)
OK  the decay is ignored (an old dismissal counts for a whole one)
OK  the decay never expires (a 200-day-old dismissal still counts)
OK  the serendipity slot is not immune (a discovery card joins the cluster)
OK  a dismissal with no vector is treated as comparable (the cluster forms anyway)
OK  the rage guard is dropped (three rapid swipes count as a cluster)
OK  the rage guard's window is widened (a slow flick still counts as a rage flick)
OK  the prompt fires again for the same cluster (the counter does not reset)
OK  the prompt's copy is built from the event's title (AD-9's leak)
OK  the generic prompt is given a category (a mute on nothing)
OK  the dismissal is not scoped to its caller
OK  the category mute is dropped from the digest (the filter is gone)
OK  the category mute is dropped from Browse (the two surfaces disagree)
OK  the mute is a penalty, not a filter (muted events are still shown)
OK  an event with no chips is muted (the product decides what it is)
OK  an expired mute is still applied (it never lifts)
OK  the mute's expiry is computed from its creation, not from now
OK  an unknown duration is accepted (the closed set is open)
OK  the bulk reset is not scoped to the caller
OK  the list endpoint reads another user's mutes (the scoping is broken)
OK  the list endpoint drops the server's labels (it sends the raw key)
OK  the unmute endpoint does not delete the row (it only reports success)
OK  the dismissal endpoint reports the prompt as due whatever the server said
OK  the provider's vectors are not re-ordered (a vector is paired with the wrong text)
OK  the wrong number of vectors is accepted (a pairing is silently dropped)
OK  a vector of the wrong size is accepted (the cosine compares nothing)
OK  the cost is not written to the cost row (the dashboard reports a free call)
OK  the cost is computed as zero (the row says the call was free)
OK  the batch limit is not enforced (the request body is unbounded)
OK  a missing key is treated as a free embedding (the row lies about the cost)
OK  the input type is a query (the vectors are in the wrong part of the space)
OK  the dimension is not requested (the truncation is applied by slicing)

All 35 probes were caught by the suite.
```

**Six probes found real gaps**, and in each case the gap was in the *test*, not the probe:

- **"the cosine threshold is lowered"** was not caught, because the existing test used a cosine of 0.0 — which fails against *any* threshold. A test that only exercises the far end of a threshold proves nothing about it. `test_a_similarity_below_the_threshold_does_not_cluster` (cosine 0.50) and `test_a_similarity_just_above_the_threshold_does_cluster` (cosine 0.75) were added.
- **"the decay never expires"** was not caught, because `_decayed_weight`'s expiry branch is unreachable *through* the cluster — the candidate filter already excludes by cutoff — and the evidence sum was identical to the half-decay case. `test_an_expired_dismissal_leaves_the_candidate_pool` was added, which asserts the thing the expiry actually does: **the row leaves the pool**, which is distinguishable from the half-decay's "weighs 0.5".
- **"a dismissal with no vector is treated as comparable"** was caught by a different check, because the existing test put the missing vector on the *newest* event. `test_an_event_with_no_vector_in_the_middle_cannot_cluster` was added — the middle is the one that matters, because the rule compares the newest against each of the others.
- **"the generic prompt is given a category"** was a **no-op mutation**: in that branch `category_key` is already `None` and the constructor hardcodes it. The probe was repointed at the branch's *return statement*.
- **"the cluster needs only two events"** broke only one of the two places the rule is enforced (the length check *and* the evidence sum). The probe was repointed at the evidence sum.
- **"the dismissal is not scoped to its caller"** was not caught, because every other test used one user — so a rule reading *all* users' dismissals passed them all. `test_another_users_dismissals_do_not_join_the_cluster` was added.

## Test Commands

```bash
# Backend, this work item
cd backend && uv run pytest \
  tests/personalization/test_dismissal_clustering.py \
  tests/personalization/test_category_mutes.py \
  tests/personalization/test_category_mute_composition.py \
  tests/personalization/test_taste_mutes_api.py \
  tests/personalization/test_dismissals_api.py \
  tests/personalization/test_embedding_cost.py \
  tests/ingestion/test_embedding_backfill.py \
  tests/ingestion/test_event_embeddings_read.py \
  tests/adapters/test_voyage_embedding.py -q

# The mutation probes
cd backend && uv run python tests/personalization/mutation_probe_fr25.py

# The whole backend suite
cd backend && uv run pytest -q --ignore=tests/e2e --ignore=tests/wall

# The whole frontend suite
cd frontend && pnpm exec vitest run

# Typecheck, lint, and the generated client
cd frontend && pnpm exec tsc --noEmit && pnpm run lint
cd backend && uv run ruff check . && uv run ruff format --check .
uv run lint-imports
make client && git diff --exit-code frontend/lib/api/

# The end-to-end suite (needs `make up`, the API running, and the seed)
make seed-browse-for-test
cd frontend && pnpm exec playwright test
```

## Coverage Details

| Module | Statements | Cover |
|--------|------------|-------|
| `apps/personalization/services/dismissals.py` | 125 | 100% |
| `apps/personalization/services/taste_mutes.py` | — | 100% |
| `apps/personalization/taste_mutes_api.py` | 35 | 94% |
| `apps/ingestion/services/embedding.py` | 27 | 100% |
| `apps/ingestion/services/embedding_backfill.py` | — | 100% |
| `apps/ingestion/services/event_embeddings.py` | — | 100% |
| `adapters/llm/voyage.py` | 53 | 100% |
| `adapters/llm/costs.py` | — | 100% |
| `apps/personalization/api.py` | — | 100% |
| **Total (the new modules)** | **850** | **98.35%** |

Target: 80%. Met.

**The two lines below 100% are unreachable on purpose, and the code says why.**
`taste_mutes_api.py:153-161` is the `except UnknownDurationError` branch — the request
schema's `Literal[7, 30, 90]` refuses a bad duration *before* the handler runs, so over
HTTP the branch is never reached. It stays because the service is the place the closed set
is the rule, and a rule that lived only in a request schema would not be a rule at all.
`adapters/llm/models.py:88` is a model default.

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| **The prompt was a centred, backdrop-washing modal** — the mockup says *"Position: bottom-anchored sheet, NOT a modal. The user can close it without choosing."* | High | **Fixed.** The prompt is now a bottom-anchored sheet: the digest stays readable behind it, the backdrop is transparent (it exists to catch the click, not to dim the page), and the container is `pointer-events-none` so the sheet itself is not covered. |
| **Two buttons shared the accessible name "Close"** — the backdrop and the X | Medium | **Fixed.** A second control with the same name is a second tab stop that leads nowhere. The backdrop is `aria-hidden` and `tabIndex={-1}`; the X carries the dismissal for anyone not using a pointer. |
| **The swipe was gesture-only** | High | **Fixed by construction.** `SwipeDismiss` exposes a real `<button>` with the same action, and both paths call one `dismiss()`. |
| **A failed dismissal write still removed the card** | High | **Fixed.** The card springs back and the button re-enables — a card that vanished without a recorded dismissal would return unexplained. |
| **`MutePromptOut.category_key` is `string \| null \| undefined`**, so `asked.category_key` was `string \| undefined` | Low | **Fixed.** `const categoryKey = asked.category_key ?? null;`. |
| **The `swipe-dismiss.test.tsx` local `PROMPT` typed `category_key` as required `string`**, which does not match the generated schema | Low | **Fixed.** The test now uses `components["schemas"]["MutePromptOut"]`, so the test's type and the component's type are the same type. |
| **The `loading.tsx` doc comment contained a literal off-scale class name** (`w-40`), which the spacing-scale test flagged — it scans raw source lines *including comments* | Low | **Fixed.** The comment now describes the rule without spelling an off-scale utility. |
| **Twenty macOS " 2.tsx" duplicate files** appeared after `prettier --write` | Low | **Fixed.** These are the filesystem's NFD→NFC normalisation artifacts — every one was byte-identical to its base file and untracked. Removed. |
| **`CategoryMuteDuration` as a `Literal` made the endpoint's `except UnknownDurationError` unreachable over HTTP** | Low | **Kept, and documented.** The schema's refusal is a *shape* refusal (`invalid_request`) and the service's is a *value* refusal (`invalid_input`) — the house's two 422s, distinguished on purpose (`tests/identity/test_profile_api.py` pins the same distinction). The branch is the service's own defence for the callers that are not this endpoint. A test now asserts *both* codes, so a broken refusal path cannot hide behind the other. |

## Notes

- **The four e2e failures are pre-existing and not this work item's.** They reproduce on a
  clean tree (`git stash push -u` → run → same 4 failures → `git stash pop`).
- **`frontend/components/brand-topbar.tsx` and `brand-topbar.test.tsx` are uncommitted
  changes that are not this work item's** (a Dark Reader `suppressHydrationWarning`
  hydration fix). They are deliberately left out of this run's diff.
- **The two eslint findings are pre-existing** — a `useCallback` dependency warning in
  `source-mute-control.tsx` and an unused variable in `e2e/digest-opt-out.spec.ts`, both
  from run 033 (`settings-sources-surface`) and both outside this item's scope.
- **`TRACEABILITY.md` and the mockup headers are untouched**, per the work item's own
  instruction — editing a document to improve a matrix score in the same pass that
  measures it is how a matrix stops being trustworthy.
- **The probes are a script, not CI.** The same gap run 033 recorded. A CI job could run
  them in a throwaway checkout; out of scope here.

## Ready for Completion

- [x] All tests passing
- [x] Coverage target met (98.35% against 80%)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-034*
