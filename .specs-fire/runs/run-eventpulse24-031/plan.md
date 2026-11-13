---
run: run-eventpulse24-031
intent: unwired-surfaces
generated: 2026-11-13
---

# Implementation Plan — run-eventpulse24-031

## Work Item: collection-assign-control

Based on the approved design:
`.specs-fire/intents/unwired-surfaces/work-items/collection-assign-control-design.md`

### Approach

Add an "Add a save" picker inside the opened collection in `CollectionManager`, reaching
`PUT /api/personal/collections/{collection_id}/events/{saved_event_id}` — the endpoint that
has existed, tested, since the collections intent and has never had a caller.

**Two code reads since the design was approved sharpen the plan and confirm it.**

1. **The filter is a plain set difference.** `CollectionEventOut.id` is *"The personal
   save's id — its identity, and what membership points at"* (`schemas.py:1471`), and
   `SavedEventOut.id` is *"The personal row's id"* (`:520`). Same id space. Excluding saves
   already in the collection is `savedEvents.filter(s => !openedIds.has(s.id))` — no
   second read, no join, no id translation.

2. **The backend already told us where titles come from.** `CollectionEventOut` carries no
   title by design, because *"reading them here would put a `catalog` query behind a
   `personal` endpoint, and AD-3 forbids relating the two"* — and its docstring names the
   remedy: *"A surface that wants titles has `GET /api/personal/saved-events`, which is the
   endpoint that owns that join"* (`:1467`). The picker uses exactly that endpoint. The
   design's choice is the one the backend documented in advance.

### Implementation checklist

1. **Extend the `opened` state** to carry the saves available to assign, alongside the
   events it already holds. Keep one state object, not two — `opened` is already the
   single record of "which collection is open and what is in it".
2. **Read saves when the picker opens**, not when `open()` runs. A user who opens a
   collection to look at it does not pay for a saves read. The design's §4.1 rule.
3. **Filter with the set difference** from `opened.events` by `id`.
4. **`assign(collectionId, savedEventId)`** through the existing `run()` helper
   (`collection-manager.tsx:91`), which already centralises `setFailure` and the
   `saveFailureMessage` refusal/offline split. Reuse it — the 409 `upgrade_hint` path works
   for free, exactly as it does for create.
5. **Re-read the collection after a successful assign** via the existing `open()`, the same
   way `unassign` does (`:194`) — the server's list stays the source of truth after every
   write, which is this component's stated rule.
6. **Update the empty-collection copy** at `:396` to name where the control actually is.
7. **The four states** from design §4.3: no saves at all, everything already in, read
   failure, 409 refusal.

### Files to Modify

| File | Change |
|---|---|
| `frontend/components/collections/collection-manager.tsx` | picker, `assign`, extended `opened` state, copy at `:396` |
| `frontend/components/collections/collection-manager.test.tsx` | the nine tests below |

### Files to Create

None. No backend change, no migration, no schema change, no new route, no nav change.
`make client` must produce no diff.

### Tests

Nine tests in `collection-manager.test.tsx`, each with the mutation probe that must break
it. A test that cannot fail is the failure mode this whole intent exists to correct.

| # | Test | Probe |
|---|---|---|
| 1 | assign sends the collection id and the **save row's** id | send `event_id` |
| 2 | a save already in the collection is not offered | remove the filter |
| 3 | a save can go into a second collection | make assign drop it from the picker globally |
| 4 | unassign leaves the save itself intact | point it at the saved-event delete |
| 5 | unassign is not entitlement-gated | gate it |
| 6 | a 409 renders the server's `upgrade_hint` verbatim, no modal | hard-code the hint |
| 7 | refusal and offline produce different lines | collapse them |
| 8 | no saves → plain line, not the dashed empty state | swap in `emptystate.quiet` |
| 9 | saves are read on picker open, not on mount | move the read to mount |

Plus: the copy at `:396` is asserted against where the control actually is.

### Verification

- `npx vitest run components/collections/` — then the full suite
- Each probe applied and reverted, with the failing test named
- `npx eslint` on both changed files
- `npx tsc --noEmit` — no new errors against the known pre-existing baseline
- `pnpm build`

### Out of scope, recorded

- **`SavedEventsSection` is dead** — exported, ten passing tests, zero mounts. A finding for
  `personal-events-list-surface`, which already owns the tested-but-unmounted decision.
- **The picker is unpaginated** — `GET /api/personal/saved-events` offers no page size.
  Recorded rather than solved with an invented limit.
