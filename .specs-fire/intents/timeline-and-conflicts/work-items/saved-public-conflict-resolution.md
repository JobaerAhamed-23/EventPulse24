---
id: saved-public-conflict-resolution
title: Resolving a conflict that involves a saved public event
intent: timeline-and-conflicts
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-10-31
run_id: run-eventpulse24-022
completed_at: 2026-10-31T07:41:28.775Z
---

# Work Item: Resolving a conflict that involves a saved public event

## Description

Make FR-33's three-action pattern work for a pair whose sides are a **personal event** and a **saved public event**: **Move {personal event}**, **Skip {public event}**, **Keep both — I'll manage**.

Today the resolve endpoint (`POST /api/personal/events/conflicts/{pair_id}/resolve`) only accepts a personal event as the new side (`ConflictResolutionIn`: "a client cannot name a saved event's id and have it deleted"), and `ConflictPair.Resolution` has no value for skipping a public event. So `POST /api/personal/saved-events/{id}` can answer 409 with a pending pair that nothing can close.

This is **high** complexity: it changes a stored enum (a migration and its check constraint), it relaxes a deliberate safety rule, and the "skip" action deletes a user's save — so it gets a design doc and Checkpoint 1 before code.

## Acceptance Criteria

- [ ] A pair with a saved side can be resolved with **skip public** (un-saves the caller's own saved event through the existing saved-events command, with its audit entry), **keep both**, or **move personal** (records the choice; the client then opens the personal side in the edit sheet with the conflicting time highlighted).
- [ ] The resolve request identifies **which side** the action is about in a way that cannot be abused: a client can only ever affect **its own** rows, a skip can only ever un-save, never delete a personal event, and an action not allowed for the pair's shape is refused (`IllegalResolutionError`).
- [ ] `ConflictPair.Resolution` and `RESOLUTIONS_BY_KIND` gain what the new actions need; the migration updates the `conflict_pair_status_ck` (and any resolution check) consistently, and existing personal-vs-personal resolutions behave exactly as before.
- [ ] **Keep both keeps the indicator** (FR-58: "a calm permanent reminder") and is never re-prompted; skip and move clear it.
- [ ] The **save → 409 → resolve** round trip works end to end on the API: the 409's `details` carry everything the client needs to post the resolution.
- [ ] Imported (calendar) personal events stay non-deletable, as today.
- [ ] Tests cover every action against both pair shapes, refusal of illegal actions, ownership (another user's pair is a 404), the already-resolved case, and the migration (forwards on a database with existing resolved pairs).

## Technical Notes

Open decisions for the design doc:

- **New values vs reuse.** Is "skip public" a new `Resolution` (`skip_public`), or `delete_new` interpreted per side kind? A new value is clearer in history ("Skipped public · Poetry reading") and in `/conflicts`' Resolved list; reuse avoids a migration but makes the stored word mean two things.
- **"New side" vs "side".** The current API names the side the user *just created*. For a pair reviewed later on `/conflicts`, there is no "new" side — the request should name the side the action applies to.
- **Duplicate-kind pairs** with a saved side: which actions are offered?
- Follow the audit wording `conflict_resolutions.py` already uses when adding the new actions; keep one audit trail per action.

## Dependencies

(none)
