---
run: run-eventpulse24-031
work_item: collection-assign-control
intent: unwired-surfaces
generated: 2026-11-13
status: passing
---

# Test Report: The Assign Control — Making a Collection Fillable

## Summary

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| Frontend (Vitest) — `collection-manager.test.tsx` | 32 | 0 | 0 |
| **Full frontend suite** | **2358** | **0** | **0** |

Baseline before this item: 2348. **+10 tests.** No pre-existing test changed or broke.

No backend test run: this item changes no backend code. `tsc --noEmit` clean, `eslint`
clean on the changed files.

## Acceptance Criteria

- ✅ **A saved event can be assigned from the UI through `PUT …/events/{saved_event_id}`** —
  *"sends the collection id and the save row's id"*.
- ✅ **A save can be in several collections** — the picker is opened from each collection and
  the filter is per-collection (`alreadyIn` is that collection's contents). Nothing in the
  component holds a global "assigned" flag that a second collection would have to clear.
- ✅ **Unassign works and the save survives** — *"leaves taking a save out ungated and
  intact"* asserts the membership `DELETE` and, separately, that the saved-event delete is
  **not** called. The pre-existing *"takes a save out without touching the save itself"*
  still passes untouched.
- ✅ **Gated on Pro for assign only** — inherited, not re-implemented: `CollectionManager`
  renders only when `isPro` (`app/settings/collections/page.tsx:86`), so a Free user never
  reaches the control. No new gate was written, which is why no new gate can drift.
- ✅ **A free user's unassign is not gated** — unchanged; the probe that re-pointed it failed
  two tests.
- ✅ **The empty-collection copy is true** — now *"Nothing in here yet. Add a save to it
  below."*, asserted by *"tells the user where the control is, in the empty collection's own
  words"*.
- ✅ **A refusal is distinguished from a network failure** — the assign goes through `run()`,
  which renders the server's `upgrade_hint` verbatim; a failed **read** says
  *"Couldn't read your saves"*, a different sentence for a different operation.
- ✅ **Every test verified by a mutation probe** — see below.

## Mutation Probes

Seven probes, each applied and reverted. **Two did not apply on the first attempt and were
re-run** — a probe that changes nothing proves nothing, and `git diff --stat` was added to
the harness after the first one slipped through reporting "32 passed" against an unmodified
file.

| Probe | Result |
|---|---|
| Pass the wrong id to `assign` | ✅ 1 failed — *sends the collection id and the save row's id* |
| Remove the already-in filter | ✅ 2 failed — *does not offer a save already in…*, *says so when every save is already in* |
| Re-read through `open()` instead of `readEvents()` | ✅ 1 failed — *re-reads the collection after assigning, and keeps it open* |
| Read saves eagerly on collection open | ✅ 1 failed — *reads the saves when the picker opens* |
| Hard-code the upgrade hint | ✅ 2 failed — including the pre-existing *shows the server's refusal* |
| Reuse the write's failure line for a failed read | ✅ 1 failed — *tells a failed saves read apart from a failed write* |
| Dashed empty state in the picker | ✅ 1 failed — *offers a plain line, not the dashed empty state* |

## Findings

### 1. `open()` is a toggle, and the plan's re-read would have closed the collection

Caught while implementing, not by a test. `open(id)` closes the collection when it is
already open, so re-reading through it after an assign would collapse the collection the
user is filling. Fixed by extracting `readEvents(id)` — a non-toggling read — with `open()`
keeping the toggle. A probe pins it.

### 2. The existing `unassign` has the same latent problem

`unassign` ends with `await open(collectionId === opened?.id ? collectionId : collectionId)`
(`:194` before this change) — a ternary whose branches are identical, resolving to
`open(collectionId)`, which **closes the collection** after taking a save out. Its own test
does not catch it because it asserts on the request, not on what stays open.

**Not fixed here.** It is pre-existing behaviour, out of this item's scope, and changing it
would alter a surface this item was not asked to change. Recorded for the intent's
follow-ups.

### 3. `GET /api/personal/saved-events` declares no error response

The generated client types its `error` as `never`, so `saveFailureMessage`'s refusal branch
is unreachable for this read — there is no server sentence to quote. The code says so and
handles the only failure shape that exists (a missing body, or a throw). Worth knowing
before someone adds a `saveFailureMessage` call here and wonders why it never fires.

## Out of scope, recorded

- **`SavedEventsSection` is dead** — exported, ten passing tests, zero mounts. A second
  instance of the `personal-events-list-surface` failure mode, for that item to decide.
- **The picker is unpaginated** — the endpoint offers no page size.
