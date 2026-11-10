---
id: e2e-proof-and-contract-tests
title: Proof the whole path works — end-to-end and contract tests
intent: event-state-sync
complexity: medium
mode: confirm
status: completed
depends_on:
  - propagation-consumer
  - notice-composition-and-email
  - detail-overlap-notice
  - polling-cadence-floors
  - frontend-digest-strip-and-detail-banner
created: 2026-11-04
run_id: run-eventpulse24-025
completed_at: 2026-11-10T13:48:08.507Z
---

# Work Item: Proof the whole path works — end-to-end and contract tests

## Description

Every preceding item is tested in isolation. This one proves the path a user actually travels: a venue cancels an event, the pipeline notices, propagation reaches the user, their reminders stop, their conflict closes, their card changes, and they are told once.

The path crosses two schemas, three modules, a Celery task, an email, and two frontend surfaces. Nothing below this item tests it end to end.

## Acceptance Criteria

- [ ] **The cancellation journey**: a published event with a saved user and a pending reminder is cancelled upstream → re-ingest records an `EventStateChange` → propagation runs → pending sends are cancelled → the conflict pair closes → the card shows cancelled → one notice appears in the strip and one email is sent. Asserted end to end, not per step.
- [ ] **The postponement journey**: the same, but the snapshot moves, reminders are re-minted against the new version, and a newly-created overlap surfaces as the calm Detail notice — not the FR-58 forced prompt.
- [ ] **The sold-out journey**: badge on card and Detail, "Save Reminder" CTA removed, reminders **kept** (`LIFECYCLE_SEND_BEHAVIOUR` maps `sold_out → KEEP`), one notice.
- [ ] **The reinstatement journey**: a cancelled event comes back, reminders are re-minted from the surviving plan, the save returns to live, and the old spent send key does not block the new send.
- [ ] **The hold-and-release journey**: a send claimed by the sweep while its event is mid-change is held, not sent, and is released by propagation. This is the race AD-17 exists for and the one no unit test can prove alone.
- [ ] **The backlog drain**: unpropagated `EventStateChange` rows that predate this intent are propagated by the reconciler without manual intervention.
- [ ] **The mute journey**: a muted event's state change produces no notice and no email, while its reminders still fire.
- [ ] **Contract tests** for every endpoint added by this intent, generated-client-first per AD-19.
- [ ] **Architecture tests hold**: `ingestion` still never writes to `personal`; no cross-schema transaction exists; `import-linter` contracts pass.
- [ ] CI stays green with the coverage gates and the `axe-core` zero-serious-violations gate on every touched surface.

## Technical Notes

The existing `tests/architecture/` suite is the model for the invariant assertions, and each prior intent's own `e2e-proof-and-contract-tests` item is the model for the journey tests — `public-pages-and-seo`'s is the most recent and the closest in shape.

**The hold-and-release journey is the one to write first**, because it is the only one that can fail for a reason none of the unit tests would catch, and because getting a deterministic test around a claim-then-change race will shape how the other journeys are staged.

The email assertions should check the fake `EmailPort`'s recorded sends — subject, stream, and the absence of an unsubscribe URL on a transactional send — rather than rendering templates in isolation, which `notice-composition-and-email` already covers.
