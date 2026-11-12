---
id: saved-collections-api
title: Collections over the wire — CRUD, reorder, and the Pro gate
intent: pro-tier-and-monetization
complexity: medium
mode: confirm
status: completed
depends_on:
  - saved-collections-model
  - free-tier-caps-read-entitlement
created: 2026-11-11
run_id: run-eventpulse24-027
completed_at: 2026-11-12T01:11:30.261Z
---

# Work Item: Collections over the wire — CRUD, reorder, and the Pro gate

## Description

The API surface FR-49 needs: *"A Pro user can create, rename, delete, and reorder saved
collections."* This item exposes `SavedCollection` to the frontend and decides what a Free
user sees.

## Acceptance Criteria

- [ ] Authenticated endpoints create, rename, delete and **reorder** collections, and assign
      or unassign a `SavedEvent` to one.
- [ ] **Collections are Pro-gated for writes.** A Free user attempting to create one is
      refused with the same calm inline `upgrade_hint` shape used by the caps in
      `free-tier-caps-read-entitlement` — not a modal, not a 403 with no explanation.
- [ ] **A lapsed Pro user can still read and still unassign.** Their collections do not
      vanish and are not deleted; they simply cannot create more. A test covers this
      explicitly, because it is the behaviour most likely to be got wrong.
- [ ] Reorder accepts the whole ordering in one request, not a sequence of pairwise swaps, so
      the server never observes a partially reordered list.
- [ ] A user can only ever see or modify their **own** collections. A test proves a
      cross-user id is refused as not-found rather than forbidden, so the API does not
      confirm another user's collection exists.
- [ ] Listing a collection's events returns the `SavedEvent` snapshot fields already
      maintained by AD-17 propagation. It does **not** join `catalog` (AD-3).
- [ ] Contract tests cover every endpoint, and `frontend/lib/api/schema.ts` is regenerated.

## Technical Notes

Medium complexity. The one judgement call is the Free-user read/write split, and it follows
from the brief's "never delete" constraint plus the open downgrade question: writes gate,
reads do not.

Refusing a cross-user id as **not-found** rather than **forbidden** matters — a forbidden
response confirms the row exists. Check how the existing personalization endpoints answer
this and match them rather than inventing a second convention.

Follow the django-ninja conventions in `apps/personalization/api.py` and its schemas.

## Dependencies

- saved-collections-model
- free-tier-caps-read-entitlement
