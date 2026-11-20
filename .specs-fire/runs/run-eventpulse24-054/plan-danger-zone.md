---
run: run-eventpulse24-054
work_item: account-danger-zone
intent: account-profile-expansion
mode: autopilot
checkpoint: none
approved_at:
---

# Implementation Plan: The Danger Zone — a Place to Put What Cannot Be Undone

## Approach

**The container the other two account-deletion surfaces hang on.** This item builds the
section, the row, and the nav row that names it. It starts no deletion and cancels none.

**Three decisions are worth stating before the code.**

1. **The nav row is the Privacy row's description, not a new row.** The danger zone
   lives *at* `/settings/privacy`, and that route is already in `SETTINGS_SECTIONS`. So
   there is no new nav entry — there is the Privacy row's description, which currently
   says *"How your Pulse is ranked."* and must now describe what is actually behind it:
   the ranking formula **and** the danger zone. **A nav row promising "your data" over a
   page that explains ranking is the exact failure that page's docstring records**, and
   the description is the only thing that changes.

2. **The section renders the request state, and the section renders unconditionally.**
   The two states are driven by whether a deletion is pending, and **the frontend cannot
   know that yet** — `CurrentUserOut` carries no pending-deletion field, and the item
   that adds it (`account-deletion-cancel-surface`) depends on *this* item. So the
   pending state is not built here.

   **That does not weaken the "exactly one state" rule, and this is why.** The rule is
   *"never both at once"* — a section showing a "Delete account →" row *and* a "Keep my
   account" button is offering two contradictory instructions. A section that has only
   one state available shows that one. When the read lands, the section gains the second
   state and the mutual exclusion becomes load-bearing — **which is exactly why the
   pending state is the sibling item's work and not this one.**

   **The section renders even when a read fails.** A danger zone that vanishes is the
   opposite of what a danger zone is for. So the section is not conditional on any read
   succeeding; when the read lands and fails, the section shows the state it can prove —
   which is the request row, because *"no pending deletion I can see"* and *"no pending
   deletion"* are different, and only the first is provable.

3. **The row's subtitle does not say "Permanent. Cannot be undone."** That is the A-16
   mockup's wording, and it is **false** of the shipped engine: there is a thirty-day
   grace period, and the mockup predates it. The subtitle says what is true.

**The "Export your data" row stays where it is** — on `/settings/account`, where
`DownloadMyData` already lives. This item moves nothing.

## Files to Create

| File | Purpose |
|------|---------|
| `frontend/components/settings/danger-zone.tsx` | The section, its heading, and the "Delete account →" row |
| `frontend/components/settings/danger-zone.test.tsx` | The two states, the terracotta treatment, the subtitle, the unconditional render, and axe-core |

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/app/settings/privacy/page.tsx` | Render the danger zone below the ranking formula — **including in the `unavailable` branch**, so a failed ranking read does not silently remove it |
| `frontend/lib/settings-sections.ts` | The Privacy row's description now names the danger zone as well as the ranking formula |
| `frontend/tests/settings-routes.test.ts` | No change expected — it must stay green, and the Privacy row must still be accurate |

## Tests

| Test File | Coverage |
|-----------|----------|
| `frontend/components/settings/danger-zone.test.tsx` | The section renders; the delete row carries the terracotta treatment; the subtitle is **not** "cannot be undone"; the export row is **not** here (it stays on `/settings/account`); `axe-core` passes |

## Technical Details

### The section is a server component

Its state comes from a read the page makes; the modal that opens from it is a client
component — and that modal is `account-delete-confirmation-surface`'s work, not this
one. **So the row renders as a real `<button>` with no handler yet**, and the sibling
item gives it one.

### The terracotta treatment

The mockup's `.danger` class is `color: var(--accent-terracotta)`, on the row's control.
The project's own rule is that terracotta is reserved for destructive actions, and the
personal-event delete row already uses exactly this treatment —
`text-accent-terracotta underline-offset-[3px] hover:underline` on
`components/sheets/personal-event-form.tsx:475`. **This row reuses that treatment
rather than inventing a second one**, because the mockup's `.danger` button is the same
control.

### The subtitle that must be true

The mockup says *"Permanent. Cannot be undone."* The engine says otherwise: the grace
period is thirty days and the account survives it. The subtitle says what is actually
true — **that the account is destroyed on a date, and that the grace period is the
chance to change your mind.**

### The page renders it in both branches

`/settings/privacy` currently renders `readRankingTransparency()` and can render an
`unavailable` state. **The danger zone must be reachable in that branch too**, or a
failed ranking read silently removes the section — which would make the danger zone
disappear precisely when the page is unhealthy. That is the same reasoning the page's own
docstring records about a blank ranking table.

### The nav row's description

`SETTINGS_SECTIONS`'s Privacy entry currently reads *"How your Pulse is ranked."* — an
accurate description of a page that only held the ranking formula. **It becomes
inaccurate the moment the danger zone lands**, and the file's own docstring says the
description is *"the same sentence as the destination page's own subheading"* and that
the index is *"a table of contents, not a second description of the product"*.

**So the description changes to match the page's new subheading**, and the page's
subheading changes to match too. One sentence, two places that must agree.

---
*Plan approved at checkpoint. Execution follows.*
