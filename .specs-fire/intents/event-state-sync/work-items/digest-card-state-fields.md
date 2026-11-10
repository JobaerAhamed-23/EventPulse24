---
id: digest-card-state-fields
title: The card cannot say an event is cancelled because the API never tells it
  — the digest state fields
intent: event-state-sync
complexity: medium
mode: confirm
status: in_progress
depends_on: []
created: 2026-11-04
---

# Work Item: The card cannot say an event is cancelled because the API never tells it — the digest state fields

## Description

FR-53's testable consequence is that *"a sold-out event is marked with a 'Sold Out' tag on the Pulse Card and Detail Screen."* The Detail Screen half is already done — `EventDetailFactsOut` carries both `status` (`schemas.py:840`) and `is_sold_out` (`schemas.py:847`), and `frontend/app/events/[id]/page.tsx:402` renders it.

`DigestCardOut` (`schemas.py:585-614`) carries neither. The card could not show the state if it wanted to.

This item is the backend half of the Pulse Card's state treatment: the fields, and the composition path that fills them.

## Acceptance Criteria

- [ ] `DigestCardOut` carries the event's **lifecycle status** and **sold-out** flag, using the backend's existing vocabulary — `Event.Status` is `scheduled`/`postponed`/`cancelled`, and `is_sold_out` is separate from it. No new vocabulary, no derived "state" enum that collapses the two.
- [ ] The fields are filled **from the composition**, not from a per-card read at render time. AD-10's rule holds: digest rows are served as stored and never recomputed at render.
- [ ] A card for an event whose state changed **after** composition reflects the change — the composition is per-user per-day, and an event cancelled at noon must not keep showing as live until tomorrow's digest. The item states how, and whether propagation touches the composed row or the read resolves it.
- [ ] Whether a **cancelled** event remains in the digest at all is settled against FR-55's consequence *"event is removed from the digest"* and `saved-event-lifecycle-state`'s decision — the two must agree, and this item does not get to decide it alone.
- [ ] The schema change regenerates the OpenAPI contract and the frontend client (AD-19).
- [ ] Contract tests for a live card, a sold-out card, a postponed card, and a cancelled card.

## Technical Notes

`apps/personalization/services/digest_composition.py` composes, `digest_read.py` serves. The question of which one carries the state is the one real decision here, and it turns on AD-10: the composed row is the stored answer, so a state change arriving later is propagation's business, not the read's. That points at the composition path plus a propagation touch — but `digest_read.py:209` already has `_conflicted_card_ids` resolving a cross-cutting fact at read time, so there is precedent for the other shape. Worth reading both before choosing.

This item has no dependencies and can start immediately, in parallel with the validate-mode items.
