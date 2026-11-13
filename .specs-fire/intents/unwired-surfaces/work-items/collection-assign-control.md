---
id: collection-assign-control
title: The Assign Control — Making a Collection Fillable
intent: unwired-surfaces
complexity: high
mode: validate
status: pending
depends_on: []
created: 2026-11-13
---

# Work Item: The Assign Control — Making a Collection Fillable

## Description

`PUT /api/personal/collections/{collection_id}/events/{saved_event_id}` is built, tested and
documented — *"A save can be in several collections at once — membership is a table, not a
column"* (`collections_api.py:235`). It has never been called.

The consequence is a Pro feature that cannot work. `collection-manager.tsx` calls `GET`,
`POST`, `PATCH`, `DELETE`, `PUT …/order` and `DELETE …/events/{saved_event_id}` — every
collection operation **except** the one that puts something in. Its own empty state
(`collection-manager.tsx:396`) says *"Nothing in here yet. Add saves to it from your saved
events"*, and `SavedEventRow` (`saved-events-section.tsx:86`) renders a stripe, a label, a
title and a time — and no control at all.

So a Pro subscriber can create a collection, rename it, reorder it, delete it and remove
things from it, and can never put anything in it.

**The tier gate is already decided**: `collections-desktop.html:34` — *"THE TIER GATE IS ON
`create` AND `assign` ONLY. Rename, reorder, delete, unassign and [everything else] stay
open."* Confirm the backend agrees before building the UI gate; do not invent a second gate.

## Acceptance Criteria

- [ ] A saved event can be assigned to a collection from the UI, through
      `PUT /api/personal/collections/{collection_id}/events/{saved_event_id}`
- [ ] A saved event can be assigned to **several** collections — the UI does not model
      membership as a single choice, because the backend does not
- [ ] Unassigning works from the same surface, through the existing `DELETE`, and **the save
      survives** — unassign is not delete, and a test proves the `SavedEvent` row is still there
- [ ] The control is gated on the Pro entitlement for **assign only**, matching the backend's
      own gate; a free user sees the upgrade path the product already uses, not a dead button
- [ ] A free user's unassign is **not** gated
- [ ] The empty-collection copy is true after this item — if the assign control lives
      somewhere other than the saved-events list, `collection-manager.tsx:396` is updated to
      point at where it actually is
- [ ] The surface reports a refused assign distinctly from a network failure, via the
      existing `saveFailureMessage` split
- [ ] Tests cover: assign, assign-to-second-collection, unassign leaving the save intact,
      the tier gate on assign, the absence of a gate on unassign, and a refused assign
- [ ] Every test is verified by a mutation probe that makes it fail

## Technical Notes

- **Read the backend's gate first.** `collections_api.py` is the source of truth for which
  operations are Pro. The mockup states the intent; the code states the fact. If they
  disagree, that disagreement is a finding to report, not a thing to paper over.
- **Where the control goes is the design decision.** Two candidates: a per-row control on
  `SavedEventRow`, or a picker inside the opened collection in `collection-manager.tsx`.
  The mockup's empty-state copy points at the first. The second puts assign next to the
  collection it affects. Decide at the design checkpoint and state why.
- **`saved_event_id` is the save's id, not the catalog event's id.** `browse-save.tsx`
  deals in `catalog_event_id`; this endpoint takes the `SavedEvent` row's id. Confirm which
  id `GET /api/personal/saved-events` returns before wiring anything.
- **`PUT` is idempotent here** — assigning twice is not an error. The UI must not report one.
- **`saved-events-section.tsx` is currently a server component with no island.** Adding a
  control makes part of it interactive; follow the `browse-save.tsx` pattern (a client
  island around the control, not around the list).

## Dependencies

- (none)
