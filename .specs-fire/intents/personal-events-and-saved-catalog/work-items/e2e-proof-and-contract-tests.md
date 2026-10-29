---
id: e2e-proof-and-contract-tests
title: End-to-End Proof & Contract Tests
intent: personal-events-and-saved-catalog
complexity: medium
mode: confirm
status: completed
depends_on:
  - personal-events-api
  - saved-events-api
  - frontend-personal-and-conflict-surfaces
created: 2026-10-29
---

# Work Item: End-to-End Proof & Contract Tests

## Description

The final work item proves the intent actually works end to end, and that the architectural invariants it touches still hold.

Every prior intent in this project ended with a proof item — `real-feeds-and-e2e-proof` for ingestion, `health-round-trip` for the scaffold. The pattern is established: a feature is not done until a recorded scenario exercises it against real data through the real API, and the architecture contracts are re-verified.

This item proves three things:

1. **The feature works end to end** — a user creates a personal event, gets a conflict, resolves it, saves a public event, and sees the right state.
2. **The boundary rules hold** — AD-3 (schema separation), AD-16 (write ownership), AD-21 (snapshot semantics) and AD-2 (import contracts) are all still true after this intent's code landed.
3. **The edge cases are pinned** — especially the conflict thresholds, which are the kind of thing that silently drifts.

## Acceptance Criteria

- [ ] A **recorded end-to-end scenario** runs against the local stack (Django + Next.js + Postgres + Redis) and passes:
  - Register a source, ingest a real event, so `catalog` has data.
  - As a user, **create a personal event** with an explicit timezone. It persists in `personal` and is returned by the list endpoint.
  - Create a **second personal event** overlapping the first by more than 15 minutes. The create returns the conflict payload with exactly three actions and does not complete silently.
  - Choose **"Keep both — I'll manage"**. The `CONFLICT_PAIR` is persisted with a `keep_both` resolution, and the pair is **never re-prompted**.
  - Re-create the same conflicting pair. **No prompt appears** — the resolved pair is immutable and is not prompted again.
  - **Save** a public event from the ingested catalog. The `SAVED_EVENT` row exists with a snapshot of the event's `start_utc`, `end_utc` and `event_version`.
  - Create a personal event overlapping the **saved public event** by more than 15 minutes. The conflict payload appears with the three actions.
  - Choose **"Delete the new one"** (with its confirmation). The new event is gone, the `ConflictResolution` is still **recorded** on the pair, and the pair's status reflects a resolved-not-cleared outcome.
- [ ] The **save-race** is proven, not just asserted: a catalog postponement landing between the save's initial version read and its commit does not leave a stale snapshot. The scenario forces the interleaving deterministically.
- [ ] The **"exactly 15 minutes is not a conflict"** boundary is pinned by a test. 15 minutes → no conflict. 15 minutes + 1 second → conflict.
- [ ] The **80% duplicate threshold** is pinned: at exactly 80% token overlap → duplicate flagged; just below → not flagged. The 24-hour duplicate window is pinned at its boundary too.
- [ ] A **resolved `CONFLICT_PAIR` is immutable**: attempting to change its resolution fails, and the pair is not re-prompted.
- [ ] A **`SAVED_EVENT` snapshot survives a catalog postponement unchanged** — until AD-17 propagation runs, which is a later intent. The test asserts the snapshot's `event_version` is behind the catalog's, which is the correct pre-propagation state.
- [ ] **AD-3 (schema separation)** is verified: a test asserts that no foreign key crosses from `personal` to `catalog`, and that the tables physically live in their own schemas. This mirrors the existing cross-schema FK refusal test from `project-scaffold`.
- [ ] **AD-16 (write ownership)** is verified: `personalization` writes `PERSONAL_EVENT`, `SAVED_EVENT` and `CONFLICT_PAIR`; `delivery` writes `REMINDER_PLAN`; neither writes the other's. Asserted by the import contracts and by a test that `personalization` reaches the plan through `delivery`'s service.
- [ ] **AD-21 (snapshot semantics)** is verified: the conflict indicator is symmetric by construction because the Pulse Card, the Timeline and the conflicts list read the same `CONFLICT_PAIR` rows. A test asserts both sides of a pair carry the indicator.
- [ ] `make lint-imports` passes, with the `models-personalization` and `models-delivery` contracts green.
- [ ] `manage.py check` passes, including the AD-15 retention check for every new model.
- [ ] **CI is green**: the full GitHub Actions pipeline passes, including the coverage gates.
- [ ] The backend and frontend test suites pass with no skipped or quarantined tests introduced by this intent.
- [ ] `beat_schedule` is still exactly one 60s tick. `backend/tests/worker/test_tick.py` passes untouched.
- [ ] A **test report** records: the end-to-end scenario and its result, the pinned boundary cases, the architecture-invariant checks, the coverage figure, and any behaviour that was deliberately left out (for example the free-tier save quota, which belongs to the Pro tier intent).

## Technical Notes

Look at `run-eventpulse24-018` (`real-feeds-and-e2e-proof`) as the precedent — it established the pattern for a proof item in this project, including how the real-feed scenario is driven and how the test report is written.

The architecture-invariant checks belong in `backend/tests/architecture/`, alongside the existing contract tests from `project-scaffold` (the cross-schema FK refusal test, the deliberate import-linter violation test, the retention-category check). They are structural assertions about the codebase, not scenario tests.

For the save-race, forcing the interleaving deterministically matters. A probabilistic race test is a flaky test, and a flaky test in CI is worse than no test. The clean approach is to make the race reproducible — for instance, by patching the catalog read so the first call returns version N and a later call returns version N+1 — rather than by racing real threads and hoping.

**The free-tier save quota.** FR-48 caps free-tier saves at 1 per 24 hours. That needs the `identity` subscription model, which does not exist yet, and it belongs to the Pro tier intent. The endpoint work item deliberately skips it. Record it explicitly in the test report as a known gap so the Pro tier intent picks it up — a silent omission here would read as "done" later.

**What this item must not do.** It is a proof item, not a feature item. If a test uncovers a bug, fix it in the work item that owns the code, not here — otherwise the ownership map stops describing reality. If the fix is genuinely out of scope for this intent's remaining work, record it in the test report as a known issue rather than expanding the intent's boundaries.

## Dependencies

- personal-events-api
- saved-events-api
- frontend-personal-and-conflict-surfaces
