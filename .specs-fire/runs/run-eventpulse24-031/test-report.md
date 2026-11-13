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

---

## Work Item: calendar-connection-controls

### Test Results

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| `calendar-connections.test.tsx` (new) | 13 | 0 | 0 |
| **Full frontend suite** | **2371** | **0** | **0** |

135 test files, up from 134. +13 tests over the previous item's 2358. No backend change.

### Acceptance Criteria Validation

- ✅ **Connections and their status are visible on a settings screen** — `/settings/calendars`.
- ✅ **Disconnect calls `DELETE /api/personal/calendars/{id}`** — *"disconnects the
  connection it was pressed on"* asserts the id, with two rows rendered so the id is what
  distinguishes them.
- ✅ **Confirmed before it completes, and the confirmation says what is lost** — *"says the
  imported events go, and that the user's own events stay"*.
- ✅ **Reconnect offered for `needs_reconnect`, not for a healthy connection** — two tests,
  one each way.
- ✅ **The list reflects a disconnect without a manual reload** — `run()` re-reads.
- ✅ **The onboarding promise resolves** — `/settings/quiet-hours` carries the one link.
- ✅ **No secret address is rendered or left behind** — see finding 1.
- ✅ **Honest empty state, not an error** — *"is honest rather than an error…"*.

### Mutation Probes

| Probe | Result |
|---|---|
| Disconnect fires on the first press | ✅ 5 failed |
| Keep the address in state after the request | ⚠️ **0 failed** — see finding 1 |
| Offer reconnect for every connection | ✅ 1 failed |
| Print the raw error slug | ✅ 2 failed |
| Clear the confirmation even when refused | ✅ 1 failed |
| Keep the address (re-run, after the test was fixed) | ✅ 1 failed |

### Findings

#### 1. A probe found a test that could not fail

*"leaves no trace of the address in the DOM afterwards"* passed against a build that never
cleared the address. The reason: after a successful reconnect, `run()` re-reads, and the
default mock answers with an **active** connection — so the form unmounted because the
connection had stopped needing a reconnect, not because the credential was cleared. The
assertion was true for the wrong reason.

Fixed by making the refresh return the connection **still revoked** in that test, so the
form would persist if the address were not cleared. Re-probed: it now fails.

This is the second probe in this run to catch a false green, after the two in
`collection-assign-control` that reported passing against an unmodified file. The tests
would all have shipped green.

#### 2. The calendars endpoint answers an envelope

`GET /api/personal/calendars` returns `{ items: [...] }`, while
`GET /api/personal/collections` returns the array itself. Caught by `tsc` on the first
write of the read helper. The two helpers now differ by one line and that line is commented.

#### 3. A failed reconnect costs the user a re-paste, deliberately

The address is cleared whether or not the request succeeded. Holding a credential in memory
to save a re-paste is the wrong trade; the connection is still `needs_reconnect`, so the
control is still there and the failure line says what happened.

---

## Work Item: detail-open-signal

### Test Results

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| `record-detail-open.test.tsx` (new) | 6 | 0 | 0 |
| `app/events/[id]/page.test.tsx` (+2) | 72 | 0 | 0 |
| `ad19-endpoint-coverage.test.ts` (reconciled) | — | 0 | 0 |
| **Full frontend suite** | **2381** | **0** | **0** |

136 files, up from 135. +10 tests over the previous item's 2371.

### Acceptance Criteria Validation

- ✅ **Opening the signed-in Detail Screen records the open** — asserted at the page level,
  naming the event id, with the island stubbed so the assertion is about *which branch
  mounts it*.
- ✅ **Fire-and-forget** — the promise is not awaited; the island renders `null`.
- ✅ **No write for an anonymous visitor** — `read.kind === "found"` gates the mount, and a
  page test asserts the marker is absent in the anonymous case.
- ✅ **No write on the public page** — a different branch entirely; it never reaches `content`.
- ✅ **Once per screen view** — see finding 1.
- ✅ **`ad19-endpoint-coverage.test.ts` reconciled** — see finding 2.

### Mutation Probes

| Probe | Result |
|---|---|
| Remove the once-guard | ⚠️ **0 failed** → test fixed → ✅ 1 failed |
| Fire for the anonymous branch too | ✅ 1 failed |
| Never fire at all | ✅ 1 failed |
| Drop the rejection handler | ⚠️ **0 failed** — not fixable here, see finding 3 |

### Findings

#### 1. The "fires once" test could not fail

The effect's dependency list is `[eventId]`, so re-rendering with the same id never re-runs
it — **with or without the ref guard**. The old test re-rendered twice and asserted one
call, which was true either way. Rewritten to render inside `<StrictMode>`, which mounts,
unmounts and remounts and so actually double-invokes the effect. Re-probed: it now fails.

A second test keeps the weaker re-render claim, which is worth holding separately.

#### 2. The AD-19 tripwire fired exactly as designed

`ad19-endpoint-coverage.test.ts` carried a **passing** test asserting the detail-open
endpoint had *no* caller, written as a deliberate tripwire: *"When the frontend gains its
caller, this test fails… and whoever closes it deletes the test and adds the 'reaches it
through the generated client' assertion alongside the others."*

It failed on the first run after the island was mounted. Followed its instruction exactly:
the endpoint moved into `NEW_ENDPOINTS` with `components/detail/record-detail-open.tsx` as
its caller, and the gap test, its constant and the now-orphaned `findCallers` helper were
deleted.

**That test is the best thing in this repo's test suite.** It is the only place where a
known gap was written as something that would fail when closed, rather than as a comment.
`endpoint-coverage-enforcement` should generalise this pattern, not replace it.

It also caught a formatting problem: the coverage check matches `api.POST(` on the
comment-stripped source, and the call site had been formatted as a fluent chain split
across lines (`api\n  .POST(`). Kept contiguous, with a comment saying why.

#### 3. The `.catch` is not covered by a failing test, and cannot be here

A probe deleting `.catch(() => {})` left the suite green. The failure mode is an
**unhandled promise rejection**, and Vitest installs its own `unhandledRejection` handler,
so a listener registered inside a test never fires — verified with a throwaway spec that
rejected a bare promise and observed nothing.

The test was rewritten to claim only what it can prove (a rejected write changes nothing on
screen), with the limit stated in the test's own docstring. The `.catch` matters in a
browser, where an unhandled rejection is a console error on every detail view — so it is
the **e2e work item's** to verify, and is recorded there.

---

## Work Item: personal-event-reminder-plan

### Test Results

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| `app/personal-events/[id]/reminders/page.test.tsx` (new) | 6 | 0 | 0 |
| `personal-event-form.test.tsx` (+3) | — | 0 | 0 |
| **Full frontend suite** | **2390** | **0** | **0** |

137 files, up from 136. +9 tests over the previous item's 2381.

### Acceptance Criteria Validation

- ✅ **A personal event's plan can be read and saved** — `/personal-events/:id/reminders`,
  sending `personal_event`, asserted directly.
- ✅ **Reachable from where a personal event is managed** — a link in the edit sheet, which
  is the one surface that opens a personal event. Three tests: absent on create, absent
  without an id, correct href on edit.
- ✅ **`ReminderPicker` reused, not reimplemented** — it already took `targetKind`.
- ✅ **A plan with no slots is the picker's empty state, not a 404** — confirmed in the
  backend before building: *"A plan that does not exist is an empty plan, not a 404"*
  (`reminder_plan_read.py:233`), so no special-casing was needed.
- ✅ **Saving a personal plan does not touch a saved-event plan** — different `target_kind`
  and `target_id` in the request; the backend owns the isolation and has its own tests.
- ✅ **A refused save is reported** — unchanged `ReminderPicker` behaviour.

### Mutation Probes

| Probe | Result |
|---|---|
| Read the plan as a `saved_event` | ✅ 1 failed |
| Give the picker the saved kind | ✅ 1 failed |
| Render the picker even when the plan is missing | ✅ 1 failed |

### Findings

#### 1. The house spacing scale caught four invented values

`tests/spacing-scale.test.ts` failed the suite on `w-40`, `w-60`, `h-11` and `w-24` in the
new loading skeleton — eleven violations across four lines. The skeleton now uses only
values its saved-event sibling already uses. This is the repo's structural rules working
exactly as the testing standards describe: *"Structural rules are enforced by tooling in
CI, not by review."*

#### 2. A second route, not a branch on the existing one

`/events/:id` serves catalog events and already carries two surfaces plus a documented
rendering-mode conflict; a personal event id does not resolve through `readEventDetail`.
A new route was the smaller change. Timeline is its active sidenav item, not Digest,
because `personal-event-reminders-desktop.html` says so and gives the reason.

#### 3. The event's name needed a new read

The plan payload carries slots and delivery times and no title. `lib/personal-event-read.ts`
is the counterpart of the saved-event route's use of `readEventDetail`, and keeps the same
three-way split (`found` / `missing` / `unavailable`). A name that cannot be read falls back
to "this event" rather than failing the screen — the plan is still the user's and still
editable.

---

## Work Item: personal-events-list-surface

### Decision: delete both dead surfaces

Verified at execution, not assumed: **six** mounts of `PersonalEventsPanel`, **all six**
passing `sheetsOnly`; **zero** mounts of `SavedEventsSection`.

Deleted rather than given routes, because **no requirement asks for either**. The Timeline
is the personal-events surface and works. Saves are reachable from Browse, the Detail
Screen, and now the collections assign picker; FR-49's design is `collections-desktop.html`
and there is no saved-events-list mockup anywhere in the corpus. Building two new screens
to justify untested-by-use code would have been scope invented to avoid a deletion.

### Test Results

| Category | Count |
|----------|-------|
| **Full frontend suite** | **2374 passed, 0 failed** |
| Test files | 136 (down from 137) |

**The test count fell by 16** — 2390 → 2374 — which is the direction the decision implies
and the work item's own criterion: *"deleting dead code should reduce it, and a test count
that does not change is a signal the dead code was not actually removed."*

Net diff: **94 insertions, 199 deletions.** `pnpm build` green.

### What was removed

- `PersonalEventsPanel`'s list branch, `PersonalEventRow`, and the `events`, `sheetsOnly`
  and `addButton` props — `sheetsOnly` was true at every call site, so the prop had one
  value and no meaning.
- Six tests covering that branch.
- `components/saved-events-section.tsx` and its ten tests.
- `openCreate` and the `cardTime` import, orphaned by the above and caught by eslint.
- The stale `PersonalEventsSection` comment naming a component that never existed.

### Findings

#### 1. Deleting the list broke four tests that drove the panel through it

The create and delete tests pressed the list's "Add event" and "Edit {name}" buttons —
controls no user could reach. They were rewired to drive the panel the way every real
caller does, through `createOpen` and `editingEventId`.

**That rewiring needed stateful harnesses.** The first attempt passed `() => {}` as the
change callbacks, and four tests failed because *the panel cannot close a sheet whose state
the caller owns*. A no-op callback would have let "the sheet stayed open" assert as a pass.
`CreateHarness` and `EditHarness` hold the state the sidenav, the digest header and the
Timeline each hold in the real app.

So the tests for delete — written three items ago in this same run — were themselves
exercising a surface the user could not reach. They now exercise the one they can.

#### 2. The warm-personal pairing assertions went with the list

Two tests asserted WCAG 1.4.1's colour-plus-label pairing on `PersonalEventRow`. The rule
is still proven, on the conflict sheet's cards and the Timeline's event blocks — surfaces
a user reaches. Recorded so the deletion is not read as dropping an accessibility check.
