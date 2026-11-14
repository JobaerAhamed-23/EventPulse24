# Code Review Report

**Run**: run-eventpulse24-034
**Intent**: relevance-feedback-loop
**Reviewed**: 2026-11-14
**Files Reviewed**: 53 (backend 46, frontend 7) + 12 created in this pass

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 6 | 3 | 0 |
| Security | 0 | 2 | 0 |
| Architecture | 0 | 4 | 0 |
| Testing | 0 | 4 | 0 |
| **Total** | **6** | **13** | **0** |

**Tests Status**: Passing — 6920 backend, 2572 frontend, 35 mutation probes all caught.

**The count is 19 findings, all fixed.** The split between "auto-fixed" and "applied" is
a split between *mechanical* and *semantic*, the same split run 033 used. A mechanical fix
(an unused variable, a formatter's opinion, a doc comment quoting an off-scale class) needs
no judgment. A semantic fix (a contract that lied, a prompt that was a modal, a card that
vanished without a recorded dismissal) is a behavioural change and gets a finding, a
rationale, and a test.

---

## Files Reviewed

### Created — backend

- `backend/adapters/llm/voyage.py` (adapter) — the real embedding adapter: the REST call, the dimension request, the pairing, the cost
- `backend/adapters/llm/costs.py` (adapter) — the AD-8 cost-row writer, and the refusal to write outside a catalog transaction
- `backend/adapters/llm/models.py` (model) — `AICostRow`, routed to the `catalog` schema
- `backend/adapters/llm/fake.py` (adapter) — the fake embedding adapter (the test double at the port boundary)
- `backend/apps/ingestion/services/embedding.py` (service) — the embed command
- `backend/apps/ingestion/services/embedding_backfill.py` (service) — the resumable backfill
- `backend/apps/ingestion/services/event_embeddings.py` (service) — the published read port for the vectors
- `backend/apps/personalization/services/dismissals.py` (service) — the dismissal, the guard, the cluster, the decay, the prompt
- `backend/apps/personalization/services/taste_mutes.py` (service) — the category-mute commands
- `backend/apps/personalization/taste_mutes_api.py` (api) — the three `/api/settings/taste` endpoints
- `backend/config/management/commands/backfill_embeddings.py` (command) — the resumable backfill's entry point
- `backend/apps/ingestion/migrations/0013_event_embedding.py` (migration) — `Event.embedding`, `public.vector(256)`
- `backend/apps/personalization/migrations/0017_dismissal_mute_cost.py` (migration) — `EventDismissal`, `CategoryMute`
- `backend/tests/adapters/test_voyage_embedding.py` (test) — 19 tests
- `backend/tests/personalization/mutation_probe_fr25.py` (test) — 35 probes, one per rule

### Created — frontend

- `frontend/components/digest/swipe-dismiss.tsx` (component) — the gesture and the keyboard-reachable button, one `dismiss()` between them
- `frontend/components/digest/mute-prompt.tsx` (component) — the bottom-anchored sheet
- `frontend/components/digest/digest-card-list.tsx` (component) — the client state the loop needs
- `frontend/components/settings/taste-mute-list.tsx` (component) — the reversal surface's list
- `frontend/app/settings/taste/page.tsx` (page) — `/settings/taste`
- `frontend/app/settings/taste/loading.tsx` (page) — the sibling loading skeleton
- `frontend/lib/dismissal-write.ts` (lib) — the one client write path for a dismissal
- `frontend/lib/taste-mute-write.ts` (lib) — the client write paths for a category mute
- `frontend/lib/taste-mutes-read.ts` (lib) — the server read for the reversal surface

### Modified

- `backend/shared/constants.py` (constants) — the FR-25 thresholds (AD-8)
- `backend/apps/ingestion/models.py` (model) — `Event.embedding`
- `backend/apps/personalization/models.py` (model) — `EventDismissal`, `CategoryMute`
- `backend/apps/personalization/schemas.py` (schema) — the wire shapes, and the `Literal` that is the published duration contract
- `backend/apps/personalization/api.py` (api) — `POST /api/personal/dismissals`
- `backend/apps/personalization/services/digest_composition.py` (service) — the category filter
- `backend/apps/personalization/services/browse_read.py` (service) — the same filter, so the two surfaces agree
- `backend/apps/ingestion/services/catalog_read.py` (service) — the chip keys the mute filters on
- `backend/config/api.py` (config) — the router mounts
- `backend/config/adapters.py` (config) — the embedding adapter registered; the `:49-51` comment corrected
- `backend/config/settings.py`, `backend/config/env.py`, `.env.example` (config) — the Voyage settings
- `backend/pyproject.toml` (deps) — the `pgvector` dependency
- `frontend/components/digest/pulse-card.tsx` (component) — the swipe wrapper and the button
- `frontend/app/page.tsx` (page) — the digest delegates to `DigestCardList`
- `frontend/lib/settings-sections.ts` (lib) — the "Taste" row
- `frontend/e2e/settings-navigation.spec.ts` (e2e) — the "Taste" row, and the missing "Sources" row
- `frontend/lib/api/` (generated) — the OpenAPI client (AD-19)

---

## Findings

### Code Quality

**1. [auto-fixed] The `loading.tsx` doc comment contained a literal off-scale class name.**
`tests/spacing-scale.test.ts` scans raw source lines — **including comments** — so the
comment's own prose (`w-40`) was flagged exactly like a class in a `className`. The
comment now describes the rule without spelling an off-scale utility.

**2. [auto-fixed] Twenty macOS " 2.tsx" files appeared after `prettier --write`.**
These are the filesystem's NFD→NFC filename normalisation: `prettier` writes the NFC name
while the filesystem held the NFD form, and macOS materialises a copy. Every one was
verified **byte-identical** to its base file and **untracked** before removal, and the
backend's two stale copies were confirmed to be the *older* revisions. The
`tests/architecture.test.ts` "kebab-case in every source folder" check caught them.

**3. [auto-fixed] `MutePromptOut.category_key` is `string | null | undefined`.**
The generated schema makes the field optional, so `asked.category_key` was
`string | undefined` and would not narrow. Fixed with `?? null` — and with the same
pattern the generic prompt's "no category, write nothing" branch depends on.

**4. [auto-fixed] The `swipe-dismiss.test.tsx` local `PROMPT` typed `category_key` as a
required `string`.** That does not match the component's prop type, so `tsc` rejected the
mock. The test now uses `components["schemas"]["MutePromptOut"]` — **the test's type and
the component's type are the same type**, which is the point of a generated schema.

**5. [auto-fixed] Two buttons shared the accessible name "Close".**
The backdrop and the X. A second control with the same name is a second tab stop that
leads nowhere. The backdrop is now `aria-hidden` and `tabIndex={-1}`; the X carries the
dismissal for anyone not using a pointer.

**6. [auto-fixed] `ruff format` and `ruff check` disagreed over line length in the probe
file.** Five long string literals exceeded the 100-column limit. They are now split with
implicit concatenation — **which keeps the probed byte sequences identical**, so the
probes still apply. Re-verified: all 35 are still caught.

**7. [applied] The prompt was a centred, backdrop-washing modal.**
The mockup says, in as many words: *"Position: bottom-anchored sheet, NOT a modal. The
user can close it without choosing."* The inherited implementation did the opposite — it
blacked out the digest and centred the panel. It is now a bottom-anchored sheet: the
container is `pointer-events-none` so the sheet stays clickable, the backdrop is
transparent (it exists to catch the click, not to dim the page), and the digest stays
readable behind it. **The accessibility line in the mockup is honoured too** —
`role="dialog"`, `aria-labelledby`, `aria-describedby`, focus to the affirmative on open,
focus restored on close. The prompt is *not* the house `Sheet`, because a native
`<dialog>` has no `aria-describedby` slot and the description here is a separate element
from the title.

### Security

**8. [applied] The prompt's copy could have been built from an event's title.**
A scraped title is untrusted source content (AD-9) and must never reach a user's screen.
The title and description arrive on the dismissal response, computed by the server, and
the client renders them **verbatim**. The mutation probe "the prompt's copy is built from
the event's title (AD-9's leak)" pins it.

**9. [applied] The embedding key must never reach a log line or a request body.**
httpx logs request URLs at INFO and this URL carries no secret — the key is a header, and
httpx does not log headers. The test asserts the key is in the `Authorization` header and
**nowhere in the JSON body**, and the adapter's error message never carries it.

### Architecture

**10. [applied] The cost row must be written inside the caller's transaction (AD-8).**
The coding standard says "the calling command opens `atomic(using=CATALOG)`, and the
gateway writes the row inside it". So the adapter does **not** open a transaction of its
own — it would commit the cost row on its own, which is exactly the failure the rule
exists to prevent: **a cost row describing a result that later rolled back**. The writer
*raises* if there is no catalog transaction open, rather than quietly opening one. The
row carries no user id: a cost row is about a *call*, not a person.

**11. [applied] The category mute must exclude, and it must do so in both surfaces.**
A mute is a filter on the candidate set, not a score term — a "show less" that hid
events entirely would be a lie to the user. The filter is applied in `compose_digest`
**and** in `browse_read`, and two mutation probes attack each, because a filter present
in one surface and absent in the other is the quietest bug in this feature.

**12. [applied] The AD-4 question is a finding, not an amendment.**
The spine's rule (`ARCHITECTURE-SPINE.md:82-88`) is *"Embedding cosine similarity is
never an identity signal."* FR-25 clusters **preference**, never identity — a different
decision, on the other side of the wall. The design doc records the finding with the
spine's verbatim words; a new AD would be needed only if cosine were ever used to merge
events.

**13. [applied] Slot-3 immunity is enforced at the dismissal, not at the candidate.**
The candidate carries no slot — the `discovery` tag is derived at scoring time from a
flag the candidate does not have. So the immunity reads the user's own composition to
find the slot the card came from, and a discovery card is never a clustering candidate.

### Testing

**14. [applied] Six mutation probes found real gaps in the tests.**
Each is listed under "Mutation Probes" in `test-report.md`. The pattern: a probe that
*passes* the suite is not a bad probe — it is a test that does not prove the rule it
claims to. The sharpest was "the cluster needs only two events", which was **not caught**
because the rule is enforced in two places (the length check *and* the evidence sum) and
the probe broke only one.

**15. [applied] The Voyage adapter had no test at all.**
It was 36% covered — the whole network path, the vector pairing, the cost arithmetic and
every error branch were unexercised. The adapter is where a wrong vector would be
attached to the wrong event, and **a wrong vector is a wrong cluster, not a wrong card** —
the consequence is invisible until a user is shown a mute for the wrong thing. Nineteen
tests now cover it, at 100%.

**16. [applied] A test asserting only the status could not tell a broken refusal path
from a working one.** The endpoint refuses an unknown category (`invalid_input` — the
command refused the value) and the schema refuses an unknown duration
(`invalid_request` — the shape was refused before the command ran). Those are the
house's two 422s, distinguished on purpose, and the test now asserts **both codes**.

**17. [applied] The tie case had no test.** One event in the cluster being a jazz event
does not make the cluster jazz. A tie is not a majority, and a tie produces the generic
prompt. A mute on the wrong category would be the worst outcome here — the title would be
a claim about what the three had in common, and it would be false.

---

## Verification

| Gate | Result |
|------|--------|
| `pytest` (backend, whole suite) | **6920 passed, 0 failed** |
| `vitest run` (frontend, whole suite) | **2572 passed, 0 failed** across 154 files |
| `uv run python tests/personalization/mutation_probe_fr25.py` | **35 probes, all caught** |
| `uv run lint-imports` | **19 contracts kept, 0 broken** |
| `uv run ruff check .` | clean |
| `uv run ruff format --check .` | clean |
| `npx tsc --noEmit` | clean |
| `npx eslint .` | 2 findings, both pre-existing (run 033) |
| `npx prettier --check .` | 28 findings, all pre-existing (repo baseline) |
| `make client` + `git diff --exit-code frontend/lib/api/` | **no drift** |
| `npx playwright test e2e/settings-navigation.spec.ts` | **5 passed** (includes `/settings/taste`) |
| `npx playwright test` (whole suite) | 22 passed, 4 failed — all 4 pre-existing, verified on a clean tree |

## Notes

- **`TRACEABILITY.md` and the mockup headers are untouched.** Editing a document to
  improve a matrix score in the same pass that measures it is how a matrix stops being
  trustworthy.
- **`frontend/components/brand-topbar.tsx` and `brand-topbar.test.tsx` are excluded from
  this run's diff** — they are a pre-existing uncommitted Dark Reader hydration fix, not
  this work item's work.
- **The probes are a script, not CI.** The same gap run 033 recorded. A CI job could run
  them in a throwaway checkout; out of scope here.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-034*
