---
id: e2e-proof-and-contract-tests
title: The end-to-end proof and the AD-10 contract tests
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: completed
depends_on: [frontend-digest-home, frontend-event-detail, digest-scheduling]
created: 2026-10-30
completed_at: 2026-10-31T12:00:00Z
---

# Work Item: The end-to-end proof and the AD-10 contract tests

## Description

Proves the intent end to end, and pins the architectural rules that this intent is the first to be able to break. The two previous intents each closed with an item of this shape; this one carries more weight, because AD-10's two-explanation rule has until now been enforceable only in one direction — `personalization` could not reach the Event Fit, but there was no Relevance Pulse for anything to be substituted *for*. Now there is.

## Acceptance Criteria

- [x] **The end-to-end proof**, as one runnable path: a user signs up, completes onboarding with interest chips and a city, has events ingested into their city, gets a digest composed by the worker, opens `/`, sees three cards in three slots with their trust signals, taps one, and reads a why-this breakdown built from the same persisted row the card rendered.
  → `backend/tests/e2e/test_digest_and_detail_proof.py`. The proof is the **backend half**: the scenario walks signup → onboarding → ingestion → the worker's composition → the two read paths, and asserts that the card's tags, bucket and badge **are** the breakdown's — two independent services, one persisted `DigestComposition` row. The *rendered* half was proved by the `frontend-digest-home` and `frontend-event-detail` items, and both read the same row. See the test report's *"The proof"* section for why the browser half is a named scope decision rather than a silent one.
- [x] **The skip-everything path is proved too**: a user who skips every onboarding step still reaches a digest. They have no interest chips, so the ranking must score them without dividing by zero and without silently treating "no preference" as "every preference".
  → Two scenarios: one with a preference row carrying **no city and no chips**, and one with **no preference row at all**. The first asserts the composition completes, that the persisted tags carry **no `matches_` tag**, and that the digest still has cards. The second asserts the composition falls back to the defaults without raising.
- [x] **The empty-state path is proved**: a user in a city with no qualifying events sees FR-8's card, with its copy and its city line, and not a "being prepared" state.
  → `test_a_city_with_nothing_in_it_is_empty_and_not_being_prepared`. The status is asserted to be `empty` and **not** `not_composed`, and the city line is asserted. The *copy* is the frontend's, and was proved by the `frontend-digest-home` item; both halves are asserted, neither is re-implemented.
- [x] **AD-10 contract tests**, each able to fail:
  - an authenticated surface **never** falls back to an Event Fit to fill a missing Relevance Pulse — asserted structurally, not by reading a rendered string;
    → `frontend/tests/ad10-separation.test.ts` — a **transitive import walk** from each authenticated route outward, plus a check that the Event Fit's vocabulary has exactly one importer and that the public preview still reaches it. Probed: planting a call to the Event Fit's read in the detail read is caught.
  - a public surface **never** reads `personal`;
    → `frontend/tests/personal-separation.test.ts` — a **brace-aware data-flow check**: every use of `.personal` must sit inside a branch guarded by a test of it. Probed: moving a use outside the guard is caught.
  - `personalization` still cannot import `apps.ingestion.event_fit` or anything inside it, with the existing package-level contract unrelaxed;
    → `make lint-imports` passes (**19 kept, 0 broken**); the contract still names the **package** with the `.*` wildcard in `pyproject.toml`; and the AST wall's own **re-export probe** still catches the two-line bypass.
  - **no explanation is ever generated at view time** — the detail path and the digest read path both assert that `domain/ranking.py` is not called and no composition row is written.
    → `backend/tests/architecture/test_ad10_explanation_persistence.py` — **AST call analysis** (a call, not an import) plus the **database row count** taken before and after the read, which is the half a source check cannot make. Probed: both the call and the write are caught.
- [x] **AD-3 contract test:** no query joins `catalog` and `personal`, and no model in either schema holds a foreign key into the other. The composition path is asserted to read the two sides separately.
  → `backend/tests/architecture/test_ad3_composition_separation.py` — the FK half already existed (`test_personal_events_invariants.py`, through `information_schema`); this adds the **query** half on the composition path: **every** candidate read must precede **every** transaction, and no chain names two aliases. Probed: moving a catalog read inside the transaction window is caught.
- [x] **FR-22 weight-lock test:** the formula's weights are read from `shared/constants.py` and pinned, so that changing one fails CI — FR-22's own consequence is that "a weight change without a PRD amendment is a CI-level test failure".
  → The pin already existed (`tests/shared/test_constants.py`). What this item adds is the **proof that the pin can fail**: probe 5 moves `RANKING_WEIGHT_INTEREST` from `0.45` to `0.50` and the suite must fail. **Caught.**
- [x] **Determinism test at the integration level:** composing a user's digest twice produces the identical persisted rows and the identical rendered page.
  → `test_composing_twice_produces_the_same_rows_and_the_same_digest`. The rows are compared **including `composed_at`** — a second composition that rewrote the rows would produce the same content with a new timestamp — and the rendered HTML is compared byte-for-byte, with any excluded region **named in the test**.
- [x] **The `beat_schedule` is still exactly one 60s tick**, with `tests/worker/test_tick.py` passing unchanged.
  → The file is **not edited**. It passes, and `git diff backend/tests/worker/test_tick.py` is **empty** — the diff is the evidence, because the criterion is about the file not having been touched.
- [x] **Contract tests for the generated client**: every new endpoint is in the OpenAPI schema, the TypeScript client is generated rather than hand-written, and a schema change that breaks the client fails the build (AD-19).
  → `frontend/tests/ad19-endpoint-coverage.test.ts` (16 tests) — the endpoints are in the committed schema, the operation ids are bound in the generated TypeScript (**both** the `operations` key and the `paths` reference), the client exports a typed `api`, and each caller imports it and does not define its own. `frontend/tests/ad19-client-break.mjs` proves the chain is load-bearing by **breaking** each of its five links in turn — **7/7 caught**.
- [x] **No PII in logs** across the new paths: no email address, no city, no event title, no secret of any kind reaches a log sink, asserted against the logger adapter's allowlist (AD-13).
  → `backend/tests/architecture/test_ad13_pii_sweep.py` — the **real** paths are exercised and the **real** output captured. The log sink is checked against `ALLOWED_FIELDS`; the audit sink has no allowlist, so its vocabulary is **stated** in the test. The sink **proves its own instrument** before the sweep begins, so the paths' silence cannot make the sweep vacuous. Probed: a title and a city in the audit sink are both caught.
- [ ] **Accessibility gates** hold on both new surfaces: `axe-core` zero serious/critical, Lighthouse ≥95. — **PARTIALLY MET**
  → ✅ `axe-core` zero serious/critical on both surfaces, in CI: the digest home's gate runs over four documents, the detail screen's over five. Both were **confirmed** here, not duplicated. ⚠️ **Lighthouse ≥95 is unverified** — Playwright is not installed and this run does not install it, the same scope decision the previous two intents' proofs made and recorded. **The substitute is a static WCAG computation** from the token file (`frontend/tests/contrast.test.ts`, 66 tests), because colour contrast is the one Lighthouse criterion the axe gate *cannot* cover — jsdom computes no layout, so axe has `color-contrast` disabled. **A static computation is not a Lighthouse score, and the run does not claim one.** The substitute found **two real, pre-existing product defects**: the light ambers at 2.96:1 used as error text in seven places, and the empty confidence dot at 1.77:1 (D1).
- [x] **CI is green**: coverage gates, `make lint-imports`, `manage.py check` on both database aliases, and the frontend test suite.
  → Backend **3920 passed**; frontend **785 passed** across 58 files; `make lint-imports` **19 kept, 0 broken**; `manage.py check` (PERSONAL) no issues; `manage.py check --database catalog` no issues; `pnpm typecheck`, `pnpm lint`, `pnpm format:check` all clean; `pnpm build` 9 routes, success.
- [x] **Every test in this item can fail.** No placeholder assertions, no `or`-fallbacks, no test that passes because a value is absent. Each one is verified to fail when the behavior it pins is deliberately broken, and the run log records that it was checked.
  → **27 of 27 probes caught**: 10 backend (`backend/tests/e2e/mutation_probe_contract_e2e.py`), 10 contrast (`frontend/tests/contrast-mutation.mjs`), 7 client-break (`frontend/tests/ad19-client-break.mjs`). The per-probe table is in the run log (`run.md`, *"The probe record"*). Five probes were **rewritten** because their first version proved nothing, and the client-break probe found **four real holes in the test written to catch it** — including a false green that read a docstring instead of the code.

## Recorded deviations

- **D1 — the empty confidence dot is below 3:1.** `color.ink.faint` is the design's designated value and the value is pre-existing; the **state** is legible (the filled dot is 10:1 against the empty one). Held open by a **tripwire** that asserts the empty dot is *still* below 3:1, so closing the deviation makes the test fail and forces this note to be updated.
- **D2 — the detail-open endpoint has no frontend caller.** `POST /api/events/{event_id}/opened` is in the schema and bound in the generated TypeScript, but nothing calls it. Calling it would be a **behaviour change** to the Detail Screen, and that decision belongs to the `frontend-event-detail` item. Held open by a **tripwire** that asserts the caller list is empty, so the day the frontend gains its caller the test fails.

## Technical Notes

**The substitution test is the hard one to write honestly.** Asserting that a page does not show an Event Fit by checking rendered text is weak — the two indicators look identical on screen, which is the entire premise of AD-10. The assertion must be structural: the import graph, the call graph, or the absence of any code path from the authenticated surface to the Event Fit read. `tests/architecture/test_event_fit_separation.py` already reasons about this well and records why a name-based wall was bypassable by a two-line re-export; extend it in the same spirit rather than adding a shallower test beside it.

**Run the frontend tests with Node 24.** A login shell may default to Node 20, where every Vitest file dies with `Cannot read properties of undefined (reading 'bind')` from undici.

The previous two intents' proof items are the model for scope and shape — read `.specs-fire/intents/onboarding-and-account/work-items/e2e-proof-and-contract-tests.md` and the run-020 artifacts before starting, so this one is recognizably the same kind of thing.

## Dependencies

- frontend-digest-home
- frontend-event-detail
- digest-scheduling
