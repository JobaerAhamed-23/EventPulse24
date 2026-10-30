---
id: e2e-proof-and-contract-tests
title: The end-to-end proof and the AD-10 contract tests
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: pending
depends_on: [frontend-digest-home, frontend-event-detail, digest-scheduling]
created: 2026-10-30
---

# Work Item: The end-to-end proof and the AD-10 contract tests

## Description

Proves the intent end to end, and pins the architectural rules that this intent is the first to be able to break. The two previous intents each closed with an item of this shape; this one carries more weight, because AD-10's two-explanation rule has until now been enforceable only in one direction — `personalization` could not reach the Event Fit, but there was no Relevance Pulse for anything to be substituted *for*. Now there is.

## Acceptance Criteria

- [ ] **The end-to-end proof**, as one runnable path: a user signs up, completes onboarding with interest chips and a city, has events ingested into their city, gets a digest composed by the worker, opens `/`, sees three cards in three slots with their trust signals, taps one, and reads a why-this breakdown built from the same persisted row the card rendered.
- [ ] **The skip-everything path is proved too**: a user who skips every onboarding step still reaches a digest. They have no interest chips, so the ranking must score them without dividing by zero and without silently treating "no preference" as "every preference".
- [ ] **The empty-state path is proved**: a user in a city with no qualifying events sees FR-8's card, with its copy and its city line, and not a "being prepared" state.
- [ ] **AD-10 contract tests**, each able to fail:
  - an authenticated surface **never** falls back to an Event Fit to fill a missing Relevance Pulse — asserted structurally, not by reading a rendered string;
  - a public surface **never** reads `personal`;
  - `personalization` still cannot import `apps.ingestion.event_fit` or anything inside it, with the existing package-level contract unrelaxed;
  - **no explanation is ever generated at view time** — the detail path and the digest read path both assert that `domain/ranking.py` is not called and no composition row is written.
- [ ] **AD-3 contract test:** no query joins `catalog` and `personal`, and no model in either schema holds a foreign key into the other. The composition path is asserted to read the two sides separately.
- [ ] **FR-22 weight-lock test:** the formula's weights are read from `shared/constants.py` and pinned, so that changing one fails CI — FR-22's own consequence is that "a weight change without a PRD amendment is a CI-level test failure".
- [ ] **Determinism test at the integration level:** composing a user's digest twice produces the identical persisted rows and the identical rendered page.
- [ ] **The `beat_schedule` is still exactly one 60s tick**, with `tests/worker/test_tick.py` passing unchanged.
- [ ] **Contract tests for the generated client**: every new endpoint is in the OpenAPI schema, the TypeScript client is generated rather than hand-written, and a schema change that breaks the client fails the build (AD-19).
- [ ] **No PII in logs** across the new paths: no email address, no city, no event title, no secret of any kind reaches a log sink, asserted against the logger adapter's allowlist (AD-13).
- [ ] **Accessibility gates** hold on both new surfaces: `axe-core` zero serious/critical, Lighthouse ≥95.
- [ ] **CI is green**: coverage gates, `make lint-imports`, `manage.py check` on both database aliases, and the frontend test suite.
- [ ] **Every test in this item can fail.** No placeholder assertions, no `or`-fallbacks, no test that passes because a value is absent. Each one is verified to fail when the behavior it pins is deliberately broken, and the run log records that it was checked.

## Technical Notes

**The substitution test is the hard one to write honestly.** Asserting that a page does not show an Event Fit by checking rendered text is weak — the two indicators look identical on screen, which is the entire premise of AD-10. The assertion must be structural: the import graph, the call graph, or the absence of any code path from the authenticated surface to the Event Fit read. `tests/architecture/test_event_fit_separation.py` already reasons about this well and records why a name-based wall was bypassable by a two-line re-export; extend it in the same spirit rather than adding a shallower test beside it.

**Run the frontend tests with Node 24.** A login shell may default to Node 20, where every Vitest file dies with `Cannot read properties of undefined (reading 'bind')` from undici.

The previous two intents' proof items are the model for scope and shape — read `.specs-fire/intents/onboarding-and-account/work-items/e2e-proof-and-contract-tests.md` and the run-020 artifacts before starting, so this one is recognizably the same kind of thing.

## Dependencies

- frontend-digest-home
- frontend-event-detail
- digest-scheduling
