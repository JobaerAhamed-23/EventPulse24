---
id: frontend-collections
title: Collections, on screen for the first time
intent: pro-tier-and-monetization
complexity: medium
mode: confirm
status: completed
depends_on:
  - saved-collections-api
created: 2026-11-11
run_id: run-eventpulse24-027
completed_at: 2026-11-12T01:20:23.829Z
---

# Work Item: Collections, on screen for the first time

## Description

TRACEABILITY.md:59 is blunt about where this starts: *"no screen shows creating, viewing, or
managing a collection."* FR-49 is the only MVP requirement with no design and no work item,
so this surface is being designed as it is built — there is no mockup to follow, unlike every
other frontend item in this intent.

The PRD's examples set the tone: *"Music this month," "For the kids."* Collections are a
quiet organisational convenience over saved events, not a new primary surface.

## Acceptance Criteria

- [ ] A Pro user can **create, rename, delete and reorder** collections, and assign or
      unassign a saved event — FR-49's four verbs plus membership.
- [ ] Reorder sends the whole ordering in one request, matching `saved-collections-api`.
- [ ] Deleting a collection makes clear that **the saved events survive** — the user is
      removing a grouping, not their saves. The confirmation says so.
- [ ] An **empty collection** and a user with **no collections** both render deliberately,
      following the `component.emptystate.quiet` pattern the design system already defines
      for the empty digest.
- [ ] A **Free user** sees collections presented as a Pro capability via the inline prompt
      from `frontend-upgrade-prompts` — not a hidden feature, and not a modal.
- [ ] A **lapsed Pro user still sees and can read their collections**, consistent with
      `saved-collections-api`. They are never shown as deleted.
- [ ] Events listed inside a collection render from the `SavedEvent` snapshot, so a
      propagated time change (AD-17) is reflected without a catalog read.
- [ ] Works at mobile width; follows existing design-system tokens.
- [ ] Tests cover the four verbs, both empty states, the Free user, and the lapsed Pro user.

## Technical Notes

Medium complexity, with one caveat worth stating plainly: **this is the one surface in the
intent with no approved design.** EXPERIENCE.md's coverage table claims `settings-desktop.html`
covers FR-49, and TRACEABILITY.md checked and found *"the mockup contains zero 'collection'
content"* — so that claim cannot be leaned on.

Build from the existing saved-events surface and the design system rather than inventing a
new visual language, and expect the walkthrough to carry a note that this surface was
designed during the build. If it grows beyond a modest management UI, that is a signal to
stop and get a design pass rather than to keep going.

Drag-to-reorder is the obvious interaction and the most expensive; a simple move-up/move-down
affordance satisfies FR-49's "reorder" and is accessible by default. Prefer it unless the
checkpoint says otherwise.

## Dependencies

- saved-collections-api
