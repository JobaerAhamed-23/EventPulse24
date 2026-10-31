# Review report: `frontend-digest-home`

**Work item**: `frontend-digest-home`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-31

---

## The verdict

**Approved, after four fixes.** The page renders what it was given and decides nothing,
which is the whole point of the item. The review found **four substantive defects** —
two of them silent, and one of them a test that was asserting the opposite of what its
name said.

The most serious finding is worth stating plainly: **the "Refresh page." label could
never appear.** The error state's rule is stateful — the second *consecutive* failure
gets a different label — and the implementation had a function that computed the count
and a page that hardcoded `attempt={0}`. The two were never connected. The label was
therefore always "Try again", and the acceptance criterion was unmet.

It survived because **the test for it asserted the wrong thing.** The test was named
*"says 'Refresh page.' on the second consecutive failure"* and its body asserted
`getByRole("link", { name: "Try again" })`. The name and the body said different things,
and the body was what ran. A test that does not check what it says it checks is worse
than no test: it is a green tick that means nothing.

---

## What the review checked

| Property | How | Result |
|---|---|---|
| the page decides nothing | the data flow read line by line: no re-bucketing, no re-sorting, no re-derivation | green |
| `not_composed` is distinct from `empty` | the two states are separate components with separate copy | green |
| the empty state has no CTA | one `<Link>`, no `<button>`, no terracotta in the article | green |
| the retry label changes on the second failure | the cookie-backed count, read and written by the server | **red → fixed** |
| the retry *does* something different from the reload | the first carries a nonce; the second reloads | **red → fixed** |
| the More slot is a working control | the slot opens a sheet; the sheet's Browse row is inert | **red → fixed** |
| the content is constrained at `xl` | the `<main>`'s max-width | **red → fixed** |
| the inert routes cannot navigate | `<span aria-disabled>`, no `<a>` | green |
| the active route is an ink pill | the class string | green |
| the topbar is brand-only | no `<Link>`, no `<button>`, no `<nav>` | green |
| the live region announces once, with a comma | `role="status"`, `aria-atomic` | green |
| the pulse is the only animation | the boundary test's motion rule; `styles/motion.test.ts` | green |
| terracotta is rationed | the boundary test's terracotta rule | green |
| no serious or critical axe violations | the axe gate over all four documents | green |
| the page is still `force-dynamic` | `export const dynamic` | green |

---

## The four changes the review made

### 1. The "Refresh page." label could never appear (the dead count)

**The bug.** `digest-error.tsx` exported `attemptFromCookie()` and `ATTEMPT_COOKIE` —
and **nothing called either of them**. The page rendered:

```tsx
<DigestError attempt={0} />
```

`attempt={0}` is hardcoded. `DigestError`'s rule is `attempt >= 1`, so the label was
always "Try again". The helper functions were dead code that *looked* like the feature
was implemented: the file contained the cookie's name, the cookie's parsing, and a
comment explaining that "a query parameter is the wrong place for this" — but the count
never came from anywhere.

**Why it survived.** The test for it was this:

```tsx
it("says 'Refresh page.' on the second consecutive failure", async () => {
  render(await HomePage());
  expect(screen.getByRole("link", { name: "Try again" })).toBeInTheDocument();
});
```

The body asserts **"Try again"**. The name asserts **"Refresh page."**. The body is what
ran, so it passed, and it passed while proving the feature was *absent*.

**The fix.** The count moved to a module that owns it, `lib/digest-attempt.ts`:

- the count lives in a **cookie**, because the retry is a navigation and a client-side
  counter cannot survive one;
- the cookie is written **only on a failure**, and cleared on a success, because the
  rule says *consecutive* — one good read breaks the run;
- `recordFailure()` returns the number of **prior** failures, not the new total. This is
  the distinction the label turns on: the first failure has zero prior failures, so the
  error state says "Try again". Returning the new total would make the *first* failure
  say "Refresh page.".

**The regression tests.** Three now, and they assert on the cookie's actual value
rather than on a method call:

- the second consecutive failure renders "Refresh page." and not "Try again";
- the count is "2" after two failures, is cleared by a success, and the next failure
  starts again at "Try again";
- the retry carries `/?retry=1`, so the server renders again rather than serving the
  failure it already rendered.

**The general lesson, recorded for the next item.** A test whose *name* and *body*
assert different things is a silent failure. The name is what a reviewer reads and the
body is what the runner checks, and when they disagree only the body is evidence. This
one was not caught by any gate because the gate ran the body.

### 2. The More slot was a dead control

**The bug.** The bottom-tab's trailing slot was documented as opening the overflow
sheet:

> **The More slot is a control, not a route.** It opens the overflow sheet, and it
> carries no `aria-current="page"` — the row *inside* the sheet carries that when the
> overflow route is the current one.

What it actually rendered was:

```tsx
<TabSlot label="More" glyph={<MoreGlyph />} />
```

and `TabSlot`'s inert branch — a `<div aria-disabled="true">` that does nothing. **There
was no overflow sheet.** The component's docstring described a surface that did not
exist, and the slot it described was inert. A user tapping More would get nothing.

**The fix.** `components/shell/more-menu.tsx` is the sheet: a `<button>` that opens it,
and the `Sheet` primitive — the same `<dialog>` base the create sheet uses, so the
overflow sheet sits in the top layer above the bottom bar.

**The sheet's one row is Browse, and Browse is inert.** A `<span aria-disabled="true">`
with a "Coming soon" note, exactly like the sidenav's Browse row. **A control that
opens a sheet is not the same as a route that exists**, and the two must not be
confused: the sheet is a real, working surface whose contents happen to be one row
that says honestly that its destination is not built yet.

### 3. The content was not constrained at `xl`

**The bug.** The design's layout table says:

> `xl` | ≥1180px | content constrained to **1180px**, whitespace expands outward, **no reflow**

The `<main>` had **no max-width at all**. The digest cards would stretch to the full
width of the content column — which on a 2560px display is roughly 2300px of card, on a
surface whose reading width is 720px. §10's rule is "Desktop adds whitespace and hover
affordances — **never features, screens, actions or copy**", and a card stretched to
2300px is a different screen from a card at 720px. The whitespace was supposed to go
*outside* the content; it was going *inside* the card.

**The fix.** `max-w-(--layout-container-max) mx-auto` on the `<main>`. The constraint is
the whole of the desktop's contribution to the layout.

**A note on why this was missed.** The design's *decision* (D18) was about the two-column
layout, and the review checked that. The *width* was a separate row of the same table,
and a table has many rows. The regression test now asserts the class on the `<main>`,
and the boundary test asserts the source.

### 4. The shell's docstring described a client component that was not one

`app-shell.tsx` began:

> **The shell is a client component's shell.** … This wrapper is a client component so
> those children may be

It has no `"use client"`, and it does not need one. The sidenav and the bottom-tab are
client components in their own right — they need `usePathname`, and they open panels —
but the wrapper needs none of that, and the content it wraps is a server component's
children.

This one is small, and it is included because **a docstring that lies about the
architecture is worse than no docstring**: the next reader would add `"use client"` to
"fix" it, and that would pull the entire page's content across the client boundary —
including the digest, which is read on the server. The docstring now says what the
component is.

---

## Decisions the review confirmed

These were recorded in the design's drift table and the review checked each one against
the spines.

| The question | The spines disagree? | The decision | Why |
|---|---|---|---|
| the h1's wording | the mobile mockup inverts it | **"Today, three things matter."** | §3's contract gives the exact string |
| the empty state's copy | the mockup says "No pulse today." | **§5's copy exactly** | §5 is marked canonical and is stricter than the mockup |
| the empty state's affordances | the mockup ships a terracotta primary + a ghost button + a sources panel | **one `Text.Meta` link** | §5: "No CTA. No carousel. No upsell at all." |
| the live region's punctuation | the mockup says "ready." | **"ready,"** | it changes the sentence boundary a screen reader hears |
| the skeleton period | the preview's skeleton has no pulse | **1800ms** | §5's Loading Patterns |
| the skeleton's shape | the preview's is a card-shaped frame | **three plain rectangles** | §5's own vocabulary for this surface |
| the two-column layout | §10 says two columns at `lg+` | **one column** | the side rail's contents cannot ship; an empty column is a layout with a hole in it |
| the Pro card | the mockup has one | **does not ship** | there is no `SUBSCRIPTION`; every user is Free |
| "Saved this week" | the mockup has one | **deferred** | it needs a new read, and the criterion required no new backend work |
| the card count | ASSUM-5 is OPEN | **three, with no affordance hinting at more** | shipping the promise of an undecided feature is shipping the feature |
| the retry semantics | §5 gives the labels, not the behaviour | **retry the read; reload the document** | the second failure is probably not in the one request |
| the `not_composed` copy | §5 has no such state | **the page writes it** | and it claims nothing about the world |

**The `not_composed` state is the one that would have been easy to collapse.** Both
statuses are "no cards", both answer 200, and collapsing them is a one-line change that
every test would have kept green — because the empty state's own tests assert the empty
state's copy, and a collapsed page would have rendered that copy for both. The
distinction is that "No qualifying events in {city}." is a **claim about the world**, and
before the digest is composed the world has not been asked. There is now a test that
renders each status separately and asserts the other one's copy is *absent*.

---

## Things the review looked for and did not find

- **No second animation.** The pulse is one named keyframe, it lands only on the
  skeleton, and it collapses under `prefers-reduced-motion`. `styles/motion.test.ts` was
  updated rather than deleted, and it still fails on any *other* animation.
- **No terracotta outside the sanctioned uses.** The today dot, the error state's
  primary retry, the brand mark, the focus ring — and the bottom tab's 2px active
  underline, which the spec names explicitly.
- **No literal colour.** No hex, no `rgb()`, no `hsl()` anywhere on the surface.
- **No pseudo-element for visible text.** Every separator is DOM text.
- **No client-side derivation of the digest's facts.** The cards are mapped in the
  server's order; the bucket is rendered, never recomputed; the date is read in the
  digest's own zone, never from the browser clock.
- **No pull-to-refresh, no auto-poll, no service worker.** Recorded, not half-built.
- **No inert route that navigates.** Four of the six sidenav routes are `<span
  aria-disabled>` elements, and the boundary test asserts the branch contains no anchor.

---

## One thing the review could not verify

**The page has never been in a browser.** The gate is jsdom, which has no layout
engine, no stacking order, no hit-testing and no contrast. Three things are therefore
asserted in the source rather than observed:

- that the terracotta reads as terracotta against the warm and cool surfaces;
- that the skeleton reads as three paper rectangles at a glance, and that its pulse is
  perceptible rather than distracting;
- that the 1180px constraint *looks* right — that the whitespace reads as breathing room
  rather than as an accidental narrow column.

`e2e-proof-and-contract-tests` is the item that puts the product in front of a real
browser, and these three are what it should look at first.

**What the review would check next time**, and records here so the next item inherits it:

1. **A test's name and its body must assert the same thing.** When they disagree, the
   body is evidence and the name is decoration — but a reader trusts the name. This is
   the second time in this run that a docstring or a test name has described behaviour
   the code did not have (the pulse card's stacking comment, this test's name).
2. **A design's tables have many rows, and a decision is usually about one of them.**
   D18 covered the *columns*; the *width* was a different row, and it was missed.
3. **A control that is documented as opening a surface must actually open one.** A
   docstring describing a sheet is not a sheet.
