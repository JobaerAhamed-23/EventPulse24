---
id: personal-events-list-surface
title: The List That Renders Nowhere — A Decision, Not a Cleanup
intent: unwired-surfaces
complexity: low
mode: confirm
status: pending
depends_on: []
created: 2026-11-13
---

# Work Item: The List That Renders Nowhere — A Decision, Not a Cleanup

## Description

`PersonalEventsPanel` has two branches. The `sheetsOnly` branch renders the sheets and a
screen-reader live region. The other branch renders a heading ("Your personal events"), an
"Add event" button, a visible message line, an empty state ("You haven't added any personal
events yet.") and a list of `PersonalEventRow`s, each with an **Edit** button.

**Nothing in the application renders the second branch.** All six mounts pass `sheetsOnly`:

| Mount | Line |
|---|---|
| `add-event-button.tsx` | 91 |
| `detail/detail-actions.tsx` | 407 |
| `shell/sidenav.tsx` | 152 |
| `shell/bottom-tab-nav.tsx` | 123 |
| `conflicts/conflicts-panel.tsx` | 134 |
| `timeline/timeline-panel.tsx` | 73 |

The `events` prop — the list's only data source — is passed by `personal-events-panel.test.tsx`
and by nothing else. A comment at `personal-events-panel.tsx:200` refers to a server
component called `PersonalEventsSection` that **does not exist** anywhere in the repo.

The list is alive in the test suite and dead in the product, which is exactly why it went
unnoticed: its tests pass, so it looks maintained.

**This item decides which it is**, and the decision is the deliverable. Both answers are
defensible:

- **Delete it.** The timeline is the personal-event surface, and a second list is a second
  place to keep in sync.
- **Give it a route.** A plain list of personal events with edit and delete is a reasonable
  thing to want, and the code is written, tested and working.

What is not acceptable is leaving a tested component that no user can reach, because the
next reader will assume it ships.

## Acceptance Criteria

- [ ] The decision is made explicitly and recorded with its reason
- [ ] **If deleted**: the branch, `PersonalEventRow`, the `events` prop and the tests that
      only exist to cover them are removed together, and the stale `PersonalEventsSection`
      comment at `personal-events-panel.tsx:200` goes with them
- [ ] **If kept**: it is mounted somewhere a user can reach without knowing a URL, it reads
      real data from `GET /api/personal/events`, and the `PersonalEventsSection` comment
      describes something that exists
- [ ] Either way, the full frontend suite passes and the test count moves in the direction
      the decision implies — deleting dead code should *reduce* it, and a test count that
      does not change is a signal the dead code was not actually removed
- [ ] No other mount's behaviour changes — the six `sheetsOnly` call sites are untouched

## Technical Notes

- **Check for a seventh mount before deleting.** The audit found six; a mount added after
  2026-11-13 would not be in that table. Re-run the grep rather than trusting this list.
- **The delete control built on 2026-11-13 (commit `2ba0073`) lives in the sheet, not the
  list**, so deleting the list does not remove delete from the product. Its three real entry
  points are the timeline's personal blocks, the conflicts panel and the detail screen's
  move flow.
- **`events` defaults to `[]`** (`personal-events-panel.tsx:178`), which is why no mount
  breaks today and why nothing ever failed.
- **If the decision is "delete", resist widening it.** The `message` state is shared with the
  `sheetsOnly` branch's live region — it stays.

## Dependencies

- (none)
