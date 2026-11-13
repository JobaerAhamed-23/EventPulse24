---
id: collection-assign-control-design
work_item: collection-assign-control
intent: unwired-surfaces
run_id: run-eventpulse24-031
status: awaiting_approval
created: 2026-11-13
---

# Design: The Assign Control — Making a Collection Fillable

## 1. The three open questions, answered from the code

The work item left three things to settle at this checkpoint. All three are now answered by
reading the source, not by assumption.

### Q1 — Which id does the endpoint want?

**Answered: the list already returns it.** `SavedEventOut` (`schemas.py:505-523`) carries
both, and says which is which in its own field comments:

| Field | Meaning |
|---|---|
| `id` | *"The personal row's id. The save is a personal record; this is its identity."* |
| `event_id` | *"The catalog event's id, by value."* |

`PUT /collections/{collection_id}/events/{saved_event_id}` wants the **personal row's id** —
`SavedEventOut.id`. `browse-save.tsx` deals in `catalog_event_id`, which is `event_id`. They
are different values and the schema already distinguishes them, so **no new endpoint and no
schema change is needed** to get the id this control requires.

### Q2 — Does the backend's gate match the mockup's claim?

**Answered: yes, exactly.** `collections-desktop.html:34` claims *"THE TIER GATE IS ON
`create` AND `assign` ONLY."* The code agrees, and says so in its own module docstring
(`collections_api.py:9`): *"Only the two operations that add are gated: creating a
collection, and assigning a save."*

| Operation | Gate |
|---|---|
| `POST /collections` (create) | `check_collections_allowed` — **Pro** |
| `PUT /{id}/events/{saved_event_id}` (assign) | `check_collections_allowed` — **Pro** (`:239`) |
| `DELETE /{id}/events/{saved_event_id}` (unassign) | **none** — *"Open on every tier… this is how a lapsed Pro user tidies up"* (`:259`) |
| rename / reorder / delete collection | **none** |

No disagreement to report. The UI gate mirrors the server's, and the server stays the
authority — the client never decides entitlement on its own.

### Q3 — Where does the control live?

**This is the decision this checkpoint exists to make, and the investigation changed it.**
See §2.

## 2. The finding that changes the answer

The work item assumed the assign control would go on the saved-events list, because the
mockup's empty-collection line says so: *"Nothing in here yet. Add saves to it from your
saved events."*

**That surface does not render anywhere.** `SavedEventsSection`
(`saved-events-section.tsx:25`) is exported, has **ten passing tests**, and is imported by
nothing but its own test file. A repo-wide grep returns twelve hits: eleven in
`saved-events-section.test.tsx`, one at the definition.

This is the **same failure mode** as `personal-events-list-surface` — a tested component
with no mount — found independently inside a different work item. Two instances is a
pattern, not a coincidence: a component whose tests pass looks maintained, and nothing in
CI asks whether anything renders it.

So the mockup's instruction points at a screen that was never wired, and "put the control
on the saved-events list" would mean **building that screen first**: a route, a nav
discoverability problem (the sidenav has six rows — `/`, `/timeline`, Add, `/browse`,
`/conflicts`, `/settings/reminders` — and `DESIGN.md` forbids adding one), its own empty
state and its own unavailable state. That is a second work item wearing this one's name.

## 3. Decision

**The assign control goes inside the opened collection**, in `CollectionManager`, as an
"Add a save" picker. The mockup's empty-collection sentence is updated to match, which the
work item's acceptance criteria already anticipate: *"if the assign control lives somewhere
other than the saved-events list, `collection-manager.tsx:396` is updated to point at where
it actually is."*

**Why this and not the saved-events list:**

- It is **one surface**, already built and already mounted at `/settings/collections`, which
  already opens a collection, lists its events through
  `GET /collections/{id}/events`, and removes them through the `DELETE`. Assign is the
  missing third verb next to two that already work.
- It needs **no new route and no nav row**, so it does not collide with the `DESIGN.md`
  rule or need the discoverability workaround the digest-settings route needed.
- It puts the control **next to the thing it affects**. A user opening "For the kids" to
  fill it does not have to leave, find the saved list, and work backwards.
- It does not depend on first resurrecting a dead component — which would couple this item
  to `personal-events-list-surface`'s decision and double its scope.

**The cost, stated plainly:** this deviates from the mockup's stated flow. The mockup is the
authority on the *language and the treatment*, and the empty-collection line is explicitly
about where the control is, not what it looks like. Changing a sentence that describes a
screen that does not exist is cheaper and more honest than building that screen to keep the
sentence true.

**`SavedEventsSection` is not resurrected or deleted here.** It is recorded as a finding for
`personal-events-list-surface`, which is already the item that decides what to do with a
tested component nothing mounts. Folding a second component into that decision is right;
making this item decide it is not.

## 4. The design

### 4.1 Data

`CollectionManager` already holds `initial: CollectionOut[]` and reads a collection's events
on expand. The picker needs one more read: the user's saves, from
`GET /api/personal/saved-events` — **already called** by the dead `SavedEventsSection`, so
the call shape and its `{items, omitted}` envelope are known-good and the generated client
already has the binding.

**Read when the picker opens, not when the manager mounts.** A user who never opens a
collection never pays for the read, and the saves list is unbounded for a Pro account.

### 4.2 The control

Inside an expanded collection, below its event list:

- A button, **"Add a save"**, which reveals the picker rather than navigating.
- The picker lists the user's saves that are **not already in this collection**, newest
  first, each row a button that assigns on press.
- A save already in the collection is **not offered**. The endpoint is idempotent and
  answers 204 (`collections_api.py:233`) — but offering an action that does nothing visible
  is the control-that-silently-does-nothing failure this intent exists to close.
- The picker shows the save's title and its local time, the same two facts
  `SavedEventRow` shows, read through `cardTime` as every other surface does.

### 4.3 States

| State | Treatment |
|---|---|
| User has no saves at all | A plain line — "Nothing saved yet." — **not** the dashed `component.emptystate.quiet`. Same reasoning the mockup gives for the empty collection: a container made on purpose is not a found absence |
| Every save already in this collection | A plain line — "Everything you've saved is already in here." |
| Read fails | The existing `saveFailureMessage` split: the server's refusal when there is one, a retry invitation when the request never arrived |
| Assign refused with 409 | The server's `upgrade_hint` rendered **as it arrived**, inline, never a modal |

### 4.4 The tier gate

A Free user does not get the control at all, which is what
`app/settings/collections/page.tsx` already does for create: *"A Free user is never refused
here, because they are never given a control that could be refused, so no 409 ever arrives"*
(`page.tsx:41`). `CollectionManager` is rendered only when `isPro` is true, so **the picker
inherits the gate for free** — a Free user never reaches the manager.

Unassign must stay reachable for a lapsed Pro user, per `collections_api.py:259`. That is
**already true today** and this item must not break it: the existing `DELETE` call is
untouched. A test pins it.

### 4.5 What is deliberately not built

- **No multi-select.** One press, one assign. The endpoint is per-save and a batch UI would
  need a batch endpoint that does not exist.
- **No "assign to several collections at once."** The backend supports a save in several
  collections (`collections_api.py:235`) and the picker reaches that by being opened from
  each collection — which is the same capability without a second interaction model.
- **No reordering inside a collection.** Out of scope; `PUT /collections/order` orders
  collections, not their contents.

## 5. Test plan

Every test below must be able to fail, verified by a mutation probe — not by inspection.
This intent exists because green tests coexisted with unreachable features.

| # | Test | Probe that must break it |
|---|---|---|
| 1 | Assign calls `PUT` with the collection id and the **save row's** id | Pass `event_id` instead of `id` |
| 2 | A save already in the collection is not offered | Remove the filter |
| 3 | Assigning to a second collection works — membership is not exclusive | Make the first assign remove the save from the picker globally |
| 4 | Unassign still works and the **save survives** | Point unassign at the saved-event delete endpoint |
| 5 | Unassign is offered with no entitlement check | Gate it |
| 6 | A 409 renders the server's `upgrade_hint` verbatim, with no modal | Hard-code a hint string |
| 7 | A refused assign is distinguished from a network failure | Collapse both to one message |
| 8 | No saves → the plain line, not the dashed empty state | Swap in `component.emptystate.quiet` |
| 9 | The picker reads saves on open, not on mount | Move the read to mount |

Plus: `collection-manager.tsx:396`'s copy is asserted to name where the control actually is.

## 6. Risks

- **The saves list is unbounded for a Pro account.** `GET /api/personal/saved-events` takes
  `starts_after`/`starts_before` but no page size. A user with hundreds of saves gets a long
  picker. **Decision: ship it unpaginated**, and record the pagination question rather than
  inventing a limit the API does not offer. Filtering by date is available if it proves
  necessary.
- **`omitted` is in the envelope and means something.** Saves whose catalog event has
  disappeared are counted, not listed (`api.py:461`). The picker inherits that: it cannot
  offer what the API does not return. Not surfaced in the picker — a count of invisible
  things inside an add-control is noise.
- **This design deviates from the mockup's flow**, §3 states why. If that is the wrong call,
  it is the cheapest possible thing to reverse — the picker is one component and the
  alternative is strictly larger.

## 7. Files

| File | Change |
|---|---|
| `frontend/components/collections/collection-manager.tsx` | the picker, its states, the assign call |
| `frontend/components/collections/collection-manager.test.tsx` | tests 1–9 |
| `frontend/lib/` | a saves read helper, if the manager's existing read pattern does not already fit |

No backend change. No migration. No schema change. `make client` produces no diff.
