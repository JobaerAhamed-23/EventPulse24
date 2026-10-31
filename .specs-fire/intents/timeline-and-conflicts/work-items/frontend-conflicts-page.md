---
id: frontend-conflicts-page
title: The Conflict Review screen
intent: timeline-and-conflicts
complexity: medium
mode: confirm
status: in_progress
depends_on:
  - conflict-list-api
  - saved-public-conflict-resolution
created: 2026-10-31
---

# Work Item: The Conflict Review screen

## Description

`/conflicts` (FR-33, Flow 6, `conflicts-desktop.html`): every clash the user has, in two sections — what still needs a decision, and what was decided — with the decision made right there. The Conflicts item in the sidenav and the bottom-tab becomes a real route.

## Acceptance Criteria

- [ ] Heading **"These days overlap."** (locked microcopy); sections **Active (n)** and **Resolved (n)**.
- [ ] An **active** pair shows both sides side by side (stripe + "Personal" / "Public event" label + name + local time) and the actions the API allows for it, worded per FR-33: "Move {personal event}", "Skip {public event}", "Keep both — I'll manage" (and the personal-vs-personal / duplicate wording that exists today).
- [ ] Choosing an action posts the resolution; **Move** opens the personal side in the edit sheet with the conflicting time highlighted; after any success the page re-reads and the pair appears under Resolved. A failed action says so calmly and leaves the pair active.
- [ ] A **resolved** pair is history: both sides, the resolution in words ("Skipped public · Poetry reading · Fri Sep 11"), and a `Text.Meta` timestamp. No edit affordance.
- [ ] **States**: "No overlaps." when there are none; skeleton rows while loading; "Couldn't analyze conflicts. Try again." on error. **No auto-refresh.**
- [ ] **Navigation**: Conflicts becomes a real link in the sidenav and the bottom-tab with the active-route pill; "Coming soon" goes.
- [ ] Accessibility: each action's accessible name says the action and its consequence (EXPERIENCE.md §4 `Sheet.ConflictResolution`); axe passes; ≥44px targets.
- [ ] Tests: both sections, each action wired to the right request, Move opening the edit sheet, empty/loading/error states, the nav link.

## Technical Notes

Reuse the conflict wording and action set from `components/sheets/conflict-resolution.tsx` rather than writing a second copy of the strings; if the inline layout needs them outside the sheet, extract them once.

## Dependencies

- conflict-list-api
- saved-public-conflict-resolution
