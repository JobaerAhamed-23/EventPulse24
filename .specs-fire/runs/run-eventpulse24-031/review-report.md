---
run: run-eventpulse24-031
work_item: collection-assign-control
intent: unwired-surfaces
generated: 2026-11-13
---

# Code Review: collection-assign-control

Reviewed: `frontend/components/collections/collection-manager.tsx`,
`frontend/components/collections/collection-manager.test.tsx`.

## Applied

### 1. The picker's list was unnamed (a11y)

A bare `<ul>` of event titles sits directly below the collection's own contents list. To a
screen reader the two were indistinguishable — the second read as more of the collection.
Named the group with `aria-labelledby` pointing at the "Add a save" heading, and gave the
heading a per-collection id so two open collections cannot collide.

### 2. "Add a save" did not announce that it reveals a region

Added `aria-expanded={false}` — the button is replaced by the picker when pressed, so it is
never the `true` case, but a control that discloses must say it discloses.

Both fixes verified: 32 tests still pass, `tsc` and `eslint` clean.

## Considered and not changed

### `data-*` hooks rather than roles in the tests

The existing suite mixes `getByRole` with `document.querySelector("[data-…]")`, and the new
tests follow it. Switching to roles throughout is a change to the whole file's idiom and
belongs in its own pass, not smuggled into a feature item.

### The `busy` flag disables every assign button at once

Pressing one save disables all of them while the write is in flight. That is the existing
component-wide convention (`busy` already gates create, rename, delete, reorder and
unassign), and a per-row busy state would be a second convention for no behavioural gain —
the writes are fast and the list re-reads after each one.

### `readableWhen` is used for the picker's times

It is the component's own formatter, already used for collection contents. Using `cardTime`
(the detail/timeline formatter) here would put two time idioms on one screen.

## Findings reported, not fixed

1. **`unassign` closes the collection it just modified.** `await open(collectionId === opened?.id ? collectionId : collectionId)`
   — a ternary with identical branches, resolving to the toggle. Pre-existing, out of scope,
   recorded for the intent's follow-ups.
2. **`SavedEventsSection` is dead code with ten passing tests.** For
   `personal-events-list-surface` to decide.
3. **`GET /api/personal/saved-events` declares no error response**, so the generated
   client's `error` is `never` there.

## Verdict

**Approved.** No backend change, no migration, no new endpoint. The Pro gate is inherited
from the page rather than re-implemented, so there is no second gate to drift.
