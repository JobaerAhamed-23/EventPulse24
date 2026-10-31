---
id: detail-screen-conflict-prompt
title: The conflict prompt on the Detail Screen
intent: timeline-and-conflicts
complexity: medium
mode: confirm
status: pending
depends_on: [saved-public-conflict-resolution]
created: 2026-10-31
---

# Work Item: The conflict prompt on the Detail Screen

## Description

On `/events/:id`, a clash is answered where it is found (FR-33: "tapping the indicator opens a detail panel surfacing the three actions"). Today a clashing Save shows "Saved to your Pulse" and the line "It overlaps "{name}" on your calendar.", because nothing could resolve a saved-public pair; after `saved-public-conflict-resolution` something can.

## Acceptance Criteria

- [ ] A **Save that returns 409** shows the event as saved and opens the three-action prompt for the pair the 409 names: Move {personal event} / Skip {this event} / Keep both — I'll manage.
- [ ] An event that is **already in an active pair** shows `Indicator.Conflict` in its header; tapping it opens the same prompt. This needs the Detail API to say so — the signed-in payload gains the caller's active pair for this event (pair id, the other side, allowed actions), and nothing for an anonymous caller (AD-12).
- [ ] **Skip** un-saves the event and the Save button returns to "Save to Pulse"; **Keep both** keeps the indicator; **Move** opens the personal event in the edit sheet with the conflicting time highlighted.
- [ ] The prompt follows `Sheet.ConflictResolution`'s rules: an explicit choice is required (no dismiss-without-resolution), focus moves to its heading, the live region announces "Schedule conflict. Three choices."
- [ ] The "It overlaps …" stopgap line is removed.
- [ ] Tests: the 409 path, the indicator path, each action's effect on the Save state, the anonymous payload having no pair, and the regenerated client.

## Technical Notes

Reuse `ConflictResolution` (the sheet the personal-events panel already uses) rather than a second prompt.

## Dependencies

- saved-public-conflict-resolution
