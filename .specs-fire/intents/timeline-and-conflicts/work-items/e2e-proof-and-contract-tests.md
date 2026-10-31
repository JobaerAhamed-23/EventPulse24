---
id: e2e-proof-and-contract-tests
title: The end-to-end proof for the Timeline and the conflicts
intent: timeline-and-conflicts
complexity: medium
mode: confirm
status: completed
depends_on:
  - frontend-timeline
  - frontend-conflicts-page
  - detail-screen-conflict-prompt
  - home-back-to-digest
created: 2026-10-31
run_id: run-eventpulse24-022
completed_at: 2026-10-31T10:27:58.265Z
---

# Work Item: The end-to-end proof for the Timeline and the conflicts

## Description

Prove the intent the way the earlier ones were proved (`backend/tests/e2e/`): real requests through the real stack with the fake adapters, and tests that can be shown to fail.

## Acceptance Criteria

- [x] **The week**: a user creates a personal event and saves an overlapping public event; the Timeline read for that week returns both, on the right local day, both flagged `conflict`.
- [x] **The review**: `/conflicts`' read lists the pair as active with its allowed actions; resolving it with each action (skip / keep both / move) moves it to resolved with the right wording, and the Timeline flag follows FR-58 (keep both keeps it; skip and move clear it).
- [x] **The detail path**: a clashing save answers 409 with a pair the resolve endpoint can close.
- [x] **Isolation**: a second user sees none of the first user's pairs or blocks.
- [x] **Contract**: `make client` leaves `frontend/lib/api/` unchanged; the frontend contract tests cover the new endpoints.
- [x] **Mutation probes** for the key rules (e.g. the cross-midnight indicator, ownership, keep-both keeping the flag), each shown to fail when the rule is broken, in the style of `mutation_probe_contract_e2e.py`.
- [x] The whole CI sequence passes locally: `make lint-backend`, Django checks, `make coverage-backend` (100% on `domain/`), `make client` diff, `make lint-web`, `make test-web`, the production build.

## Technical Notes

(none)

## Dependencies

- frontend-timeline
- frontend-conflicts-page
- detail-screen-conflict-prompt
- home-back-to-digest
