---
run: run-eventpulse24-054
work_item: account-danger-zone
intent: account-profile-expansion
mode: autopilot
tested_at: 2026-11-20
---

# Test Report: The Danger Zone — a Place to Put What Cannot Be Undone

## What Was Tested

| File | Tests | Covers |
|------|-------|--------|
| `frontend/components/settings/danger-zone.test.tsx` | 9 | The section itself — the labelled region, the delete row, the terracotta treatment, the subtitle's truth, the absence of the export row, the one-state rule, axe-core |
| `frontend/tests/privacy-danger-zone.test.tsx` | 6 | The **screen** — that the section is mounted on `/settings/privacy` in *both* branches, and that the nav row's description and the page's subheading agree |

**Fifteen tests, and they run on both sides of the page.** The component file proves the
section is *correct*; the page file proves the section is *reached*. **Those are two
different claims, and only the second one is a claim about the product** — a danger zone
that is built and never mounted is a component, and a danger zone that is mounted on a
route nobody visits is a line of code.

## Results

| Suite | Result |
|-------|--------|
| `danger-zone.test.tsx` | 9 passed |
| `privacy-danger-zone.test.tsx` | 6 passed |
| `tests/settings-routes.test.ts` | 13 passed — the Privacy row must still resolve to a real route |
| **Full frontend suite** | **2774 passed, 0 failed** (172 files) |
| `pnpm tsc --noEmit` | clean |
| `pnpm eslint` on the changed files | clean |

**The repository-wide `pnpm lint` has three pre-existing errors** — in
`components/settings/email-change.tsx` (two `react-hooks/purity` findings on `Date.now()`
during render) and `e2e/digest-opt-out.spec.ts` (an unused binding). **None of them is in
a file this item touched**, and `git status` confirms those files are unmodified. The
repository-wide `pnpm format:check` likewise reports 36 files, all of them pre-existing
except this item's, and this item's files are formatted.

## Mutation Probes — five, all detected

**A test that cannot fail is not a test.** Every claim the danger zone makes was
contradicted deliberately, and the suite was asked to notice.

| # | Mutation | Detected by | Result |
|---|----------|-------------|--------|
| 1 | Terracotta moved from the control to the heading | `does not put terracotta on the heading` | **Detected** |
| 2 | The subtitle changed to the mockup's *"Permanent. Cannot be undone."* | `does not claim the deletion cannot be undone` + `says the grace period…` | **Detected (2 tests)** |
| 3 | The section removed from the `unavailable` branch | `renders the danger zone when the ranking read failed` + the terracotta-on-both-branches test | **Detected (2 tests)** |
| 4 | The section removed from the normal branch | `renders the danger zone when the ranking formula loads` | **Detected** |
| 5 | The page's subheading reverted to naming only the ranking formula | `agrees with the page's own subheading, because they are the same sentence` | **Detected** |

**Probe 3 is the one this item exists for.** The plan's requirement that the section
renders "including in the `unavailable` branch, so a failed ranking read does not
silently remove it" had **no test behind it** — the component file cannot see the page.
The first mutation probe was run *before* the page-level test existed, and **it passed**:
the mutation was undetectable. That gap is why `tests/privacy-danger-zone.test.tsx`
exists, and it is now closed.

**Probe 5 caught a real drift during the review.** The nav row's description had been
updated to name the danger zone, but the page's own subheading had not — so the two
places that `lib/settings-sections.ts` says must hold the same sentence did not. The
subheading was corrected and the probe is what proved the correction is held.

## The axe-core gate

`danger-zone.test.tsx` runs axe over the rendered section and asserts **zero serious or
critical violations**. `color-contrast` is disabled — jsdom computes no layout, so axe
cannot measure contrast and would report every coloured thing as a violation. The
project's other gates (`tests/contrast.test.ts`) measure contrast against the tokens
separately.

## What Is Not Yet Testable, and Why

**The pending-deletion state is not built, so it is not tested.** `CurrentUserOut`
carries no pending-deletion field, and the item that adds it
(`account-deletion-cancel-surface`) *depends on this one*. So:

- There is no "Keep my account" button to render, and
- `never renders both states of the danger zone at once` asserts the *negative* — the
  contradictory second state is absent.

**When the pending state lands, that assertion must be inverted and the page file must
grow the pending branch.** The mutual exclusion becomes load-bearing at that moment, and
until then only one state exists to be exclusive about. This is recorded in the section's
own docstring so the next reader knows it is a deferral and not an oversight.

## Notes on the Fixtures

**The ranking fixture is deliberately partial.** It carries two terms and five buckets —
the buckets' dot counts have to match the bucket count, or `RankingFormula` renders a
negative repeat count and throws. **The fixture is not the product's real weights**; the
ranking formula's own test file already holds the assertion that matters there (that no
weight literal appears in the component), and duplicating it here would add nothing.

**The page test mocks at the read boundary, not the component boundary.** `readRankingTransparency`
and `getSession` are the two reads the page makes; both are replaced at the port, the
same way `tests/profile-a11y.test.tsx` does it for the profile screen.

---
*Test report for `account-danger-zone`. The item is ready for review.*
