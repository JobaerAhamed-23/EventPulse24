---
run: run-eventpulse24-054
work_item: account-danger-zone
intent: account-profile-expansion
reviewed_at: 2026-11-20
status: complete
---

# Code Review: The Danger Zone — a Place to Put What Cannot Be Undone

## Files Reviewed

| File | Status |
|---|---|
| `frontend/components/settings/danger-zone.tsx` | created |
| `frontend/components/settings/danger-zone.test.tsx` | created |
| `frontend/tests/privacy-danger-zone.test.tsx` | created |
| `frontend/app/settings/privacy/page.tsx` | modified |
| `frontend/lib/settings-sections.ts` | modified |

## Summary

| Category | Auto-fixed | Suggested | Skipped |
|----------|-----------|-----------|---------|
| Code quality | 2 | 0 | 0 |
| Accessibility | 0 | 0 | 0 |
| Architecture | 0 | 0 | 0 |
| Testing | 1 | 0 | 0 |
| **Total** | **3** | **0** | **0** |

**No finding required confirmation.** Every change was a correction of this item's own
work, and the suite was re-run after each batch.

## Auto-Fixed

| # | Finding | File | Change |
|---|---|---|---|
| 1 | The nav row's description had been updated to name the danger zone, but the **page's own subheading had not** — so the two places `lib/settings-sections.ts` states must hold the same sentence did not | `app/settings/privacy/page.tsx` | The subheading now names the danger zone and the thirty-day window. A test was added to hold the two in agreement, and a mutation probe confirmed it can fail |
| 2 | The module docstring still said *"Appearance and Danger zone are not here, because they are not built"* — **true of Appearance, false of the danger zone**, which is built and lives on this route | `lib/settings-sections.ts` | Corrected, and a new paragraph records that the danger zone is not a nav row but the Privacy row's description |
| 3 | The plan's requirement that the section renders "including in the `unavailable` branch" **had no test behind it** — the component file cannot see the page, and the first mutation probe confirmed the mutation was undetectable | `tests/privacy-danger-zone.test.tsx` | Created. The page is now tested in both branches, and the probe is detected |

**Tests re-run after the auto-fixes:** 2774 passed (172 files), `tsc --noEmit` clean,
`eslint` clean on every changed file.

## Findings Reviewed and Accepted as Correct

These were found by reading the diff and are **not** defects — they are recorded because
a reviewer who did not know the reasoning would reasonably ask about them.

### 1. The section renders only the request state, and the "one state at a time" rule is only half-exercised

`DangerZone` has no pending-deletion state, because `CurrentUserOut` carries no
pending-deletion field and the item that adds it (`account-deletion-cancel-surface`)
**depends on this one**. So the "exactly one state" rule is currently enforced by there
being only one state.

**The mutual exclusion becomes load-bearing when the pending state lands**, and the
section's own docstring says so, so the next reader does not mistake the absence for an
oversight. The page test asserts the *negative* today — the contradictory "Keep my
account" button is absent — and it must be inverted when the read lands. Not changed.

### 2. The delete button has no handler

`data-open-delete-modal` marks the control and nothing else does with it yet. The modal
is `account-delete-confirmation-surface`'s work, and it depends on this item. **The row
renders as a real `<button>` rather than a `<div>`,** so the control is keyboard-reachable
and has an accessible name today, and the sibling item gives it a handler rather than
making it interactive first. Not changed.

### 3. The danger zone is not a nav row

A-16 puts the danger zone *at* `/settings/privacy`, and that route is already in
`SETTINGS_SECTIONS`. **Adding a nav row for it would be a row pointing at a route that
does not exist** — the 404 link the whole file exists to prevent. What changed instead is
the Privacy row's description, because the file's own rule is that the description is the
destination page's own subheading. Not changed.

### 4. The subtitle says "30-day" and the constant says thirty

The row's description is written out as *"after a 30-day grace period"*. The backend's
`DELETION_GRACE_PERIOD` is thirty days, and the mail renders its copy from the constant
rather than from a literal.

**This is not the same defect the mail had.** The mail's copy is rendered from the
constant on the server, where a change to the constant propagates. This is a
**frontend string with no constant to render from**, and the backend's grace period is
not exposed to the frontend yet. Changing it means changing this string.

**It is a real coupling and it is recorded, not hidden.** When
`account-deletion-cancel-surface` adds the pending-deletion fields to `CurrentUserOut`,
it will be able to render the *server's* date rather than a duration — **and this string
should go with it.** Not changed in this item, because that item owns the field.

### 5. The axe gate disables `color-contrast`

jsdom computes no layout, so axe cannot measure contrast and reports every coloured
thing as a violation. `tests/contrast.test.ts` measures contrast against the tokens
separately, and every other gate in the project disables it for the same reason. Not
changed.

## Accessibility Review

| Check | Result |
|---|---|
| The section is a **labelled region** | ✅ `<section aria-labelledby="danger-zone-heading">` — a screen reader can reach it by the name "Danger zone" |
| One `h1` per screen | ✅ The danger zone's heading is an `h2`, under the page's `h1` |
| The control has an accessible name | ✅ "Delete account →" is the button's text |
| The colour is not the only signal | ✅ The word "Delete" and the arrow carry the meaning; terracotta is reinforcement, not information |
| The destructive colour is on the control, not the heading | ✅ Asserted, and mutation-probed |
| Serious/critical axe violations | ✅ Zero |
| `color-contrast` | ⚠️ Disabled in the axe gate — measured separately by `tests/contrast.test.ts` |

## Architecture Review

| Check | Result |
|---|---|
| **AD-16 — write ownership** | ✅ The frontend writes nothing. The button has no handler, and the API surface that will back it belongs to the two sibling items |
| **AD-19 — OpenAPI is the contract** | ✅ **No endpoint, no field, no schema change.** The generated client is untouched and needs no regeneration |
| **One settings nav list** | ✅ `SETTINGS_SECTIONS` remains the single source; no hand-written `href="/settings…"` link was added, and `tests/settings-routes.test.ts` is green |
| **The `SettingRow` primitive is reused** | ✅ The row is a `SettingRow`, the same primitive `/settings/account` uses for its own rows |
| **The page's own subheading and the nav description agree** | ✅ Asserted by test, mutation-probed |
| **No new component owns its own layout** | ✅ The section renders a heading and one row; it does not restyle the shell |

## Testing Review

| Check | Result |
|---|---|
| Tests can fail | ✅ **Five mutation probes, all detected** |
| Naming convention `test_<unit>_<condition>_<expected>` | ✅ The frontend's own convention (`it("…")` in a `describe` naming the unit) |
| Fakes at the port boundary | ✅ `getSession` and `readRankingTransparency` are the two reads the page makes, and both are replaced at the port — the same way `tests/profile-a11y.test.tsx` does it |
| Coverage of the changed files | ✅ `danger-zone.tsx` — every line covered. `privacy/page.tsx` — both branches covered |
| The section's own axe gate | ✅ Zero serious or critical |
| Edge cases | ✅ Ranking read succeeded; ranking read failed; one state at a time; terracotta on the control in both branches; subheading/nav agreement |

## A Note on the Pre-Existing Lint Failures

`pnpm lint` across the repository reports **three errors** — two `react-hooks/purity`
findings on `Date.now()` in `components/settings/email-change.tsx`, and an unused binding
in `e2e/digest-opt-out.spec.ts`. **None of them is in a file this item touched**, and
`git status` confirms those files are unmodified by this run. They are left alone:
fixing another work item's file inside this one is how two items end up conflicting in a
merge.

## Conclusion

**No changes require confirmation.** The three auto-fixes were corrections of this item's
own work, and the suite is green after them.

The item is ready for completion.
