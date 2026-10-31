---
id: home-back-to-digest
title: The home page returns to the digest alone
intent: timeline-and-conflicts
complexity: low
mode: autopilot
status: in_progress
depends_on:
  - frontend-timeline
created: 2026-10-31
---

# Work Item: The home page returns to the digest alone

## Description

Remove the stopgap "Your personal events" list added under the digest on 2026-10-31 (commit `662a30e`), now that the Timeline is where personal events live. `/` goes back to the 3-card brief the spec describes. So that adding an event from home never again looks like nothing happened, the header's "+ Add personal event" confirms the add inline and points to the Timeline.

## Acceptance Criteria

- [ ] `/` no longer reads or renders the personal events list; the page's personal-events read is removed with it.
- [ ] After a successful add from the header quick-add, one calm `Text.Meta`-weight line near the button says the event was added, with a "See it on your Timeline" link to the week containing it. Inline, not a toast (EXPERIENCE.md: "inline notice only").
- [ ] Tests that asserted the stopgap list are removed or replaced; the empty-digest test returns to asserting no buttons in the whole digest region.
- [ ] Spacing and terracotta rules hold.

## Technical Notes

`PersonalEventsSection` / `readPersonalEvents` may then have no caller; delete what nothing uses rather than leaving it for the Timeline to maybe adopt.

## Dependencies

- frontend-timeline
