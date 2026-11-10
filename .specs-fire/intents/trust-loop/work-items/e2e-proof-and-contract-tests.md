---
id: e2e-proof-and-contract-tests
title: The proof — a report, a verdict, a score, a ranking
intent: trust-loop
complexity: medium
mode: confirm
status: pending
depends_on:
  - review-intake-and-backfill
  - editorial-admin-queue
  - ranking-consumes-reliability
  - frontend-report-control
created: 2026-11-10
---

# Work Item: The proof — a report, a verdict, a score, a ranking

## Description

The intent's claim is that the three requirements form one loop. This item proves the loop end to end against the real local stack, the way each earlier intent closed with an e2e and contract item.

## Acceptance Criteria

- [ ] **The chain:**
  1. A signed-in user reports a published event.
  2. A `user_reported` `ReviewItem` appears, with no user identity on it.
  3. The event is still in the digest.
  4. An editor (a group member, not a superuser) rejects it through the admin.
  5. The event leaves the digest, the public Event URL and the sitemap.
  6. Saved users are handled as `event-rejection-state` decided.
  7. The source's observation count rises.
- [ ] **The score moves the ranking:** drive enough rejects past the minimum N to cross the escalation line. A `source_reliability` item appears, the source is **not** paused, and that source's next event ranks below an otherwise-identical event from a healthy source.
- [ ] **The stranded-event path:** a low-timezone-confidence event lands in `in_review`, gets a queue item, is approved by an editor, and appears in the digest.
- [ ] **The negative paths:** a non-editor is refused by the admin, a sixth report in a day is refused, and a stale-version resolve is refused.
- [ ] Contract tests cover every new endpoint against the regenerated `schema.ts`, and the intent's known gaps are listed (dismissals, the LLM path, free-text reports, the FR-29 dashboard, merging duplicates, and the PRD amendments owed).
- [ ] Each e2e assertion is shown to be able to fail, either by a recorded mutation probe in the style of `tests/e2e/mutation_probe_contract_e2e.py` or by an explicit negative control.

## Technical Notes

The local stack may need starting (`systemctl --user start docker-desktop`, then `make up`).

## Dependencies

- review-intake-and-backfill
- editorial-admin-queue
- ranking-consumes-reliability
- frontend-report-control
