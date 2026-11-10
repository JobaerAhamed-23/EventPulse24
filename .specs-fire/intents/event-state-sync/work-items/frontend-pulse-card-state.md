---
id: frontend-pulse-card-state
title: Sold out, cancelled, moved — the Pulse Card's state treatment
intent: event-state-sync
complexity: medium
mode: confirm
status: completed
depends_on:
  - digest-card-state-fields
created: 2026-11-04
run_id: run-eventpulse24-025
completed_at: 2026-11-10T11:13:26.617Z
---

# Work Item: Sold out, cancelled, moved — the Pulse Card's state treatment

## Description

`frontend/components/digest/pulse-card.tsx` reads neither `is_sold_out` nor the event's status — a grep for either across `components/digest/` returns nothing but unrelated `role="status"` attributes on the skeleton. The card renders a cancelled event exactly as it renders a live one.

The public page and the Detail screen already solved this, and their solution is the one to copy rather than re-derive: `public-event-page.tsx:279-280` states the rule plainly — *"the vocabulary is the backend's — `Event.Status` is `scheduled`, `postponed` or `cancelled`"* — and `:293-294` holds the copy: *"Postponed — this event is not happening at the time shown."*, *"Cancelled — this event is not happening."*

## Acceptance Criteria

- [ ] The Pulse Card renders **sold out**, **cancelled** and **postponed** states, matching `sold-out-card-state-desktop.html` (self-tagged `FR-53 FR-54`).
- [ ] It uses the **backend's vocabulary and the existing copy strings**, shared with the public page rather than duplicated — one more copy of "Cancelled — this event is not happening." is one more place for it to drift.
- [ ] **Colour is never the sole carrier of meaning** (WCAG 1.4.1). Every state carries a text label, as the `color.warm.personal` tone does for personal events.
- [ ] The state treatment is **distinct from the conflict indicator** — the 8–10px amber circle at the card's top-right already means "schedule conflict", and a second signal in the same place would be unreadable.
- [ ] A cancelled card's affordances match its state: whatever the card offers for a live event that makes no sense for a dead one is removed, not merely greyed.
- [ ] Mobile layout holds at the breakpoints the existing card already supports.
- [ ] `axe-core` reports **zero serious violations** on the digest surface, as the existing gate requires.
- [ ] Tests per state, including a card that is both sold out **and** conflicted, which is the case where two indicators must coexist legibly.

## Technical Notes

`pulse-card.test.tsx` is the existing test file and establishes the patterns. The DESIGN.md token for the sold-out badge is `component.badge.soldout`, already used by the public page — the card should consume the same component where the layout allows rather than styling a second badge.

Depends on `digest-card-state-fields` only for the data; the visual work can be built against a fixture in parallel if the run is wide.
