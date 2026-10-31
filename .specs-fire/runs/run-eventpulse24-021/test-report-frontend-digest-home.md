# Test report: `frontend-digest-home`

**Work item**: `frontend-digest-home`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-31

---

## What was built

| File | Kind | What it is |
|---|---|---|
| `frontend/app/page.tsx` | rewritten | `/` — the route decision, the digest read, and the four states |
| `frontend/lib/digest-read.ts` | new | the server-side read: `readDigest()` returns `composed` / `empty` / `not_composed` / `unavailable` |
| `frontend/components/shell/app-shell.tsx` | new | the sidenav + the brand-only topbar + `<main>` + the bottom-tab bar |
| `frontend/components/shell/sidenav.tsx` | new | `Component.Sidenav.App` — the six-route rail |
| `frontend/components/shell/bottom-tab-nav.tsx` | new | `Component.BottomTab` — the five-slot bar and the More affordance |
| `frontend/components/shell/nav-glyphs.tsx` | new | eight hand-drawn 16×16 stroke-only glyphs |
| `frontend/components/digest/digest-header.tsx` | new | the `Indicator.Today` dot, the h1, the lede, the date line |
| `frontend/components/digest/digest-empty.tsx` | new | FR-8's empty state, one low-weight link |
| `frontend/components/digest/digest-preparing.tsx` | new | the not-yet-composed state |
| `frontend/components/digest/digest-error.tsx` | new | "Couldn't reach Pulse." and both retry labels |
| `frontend/components/digest/digest-skeleton.tsx` | new | the three paper rectangles, `skeleton-pulse` |
| `frontend/components/shell/more-menu.tsx` | new | the bottom tab's overflow sheet, where Browse lives |
| `frontend/lib/digest-attempt.ts` | new | the server-owned count of consecutive digest failures |
| `frontend/components/add-event-button.tsx` | modified | `compact`, `withoutPanel` and `onOpen`, so the nav can own the Add glyph |
| `frontend/styles/globals.css` | modified | the `skeleton-pulse` keyframes and the reduced-motion collapse |
| `frontend/styles/motion.test.ts` | modified | now allows **exactly one** animation, and still fails on any other |
| `frontend/tests/cookie-store.ts` | new | a real cookie store for the tests that render a page which reads a cookie |

## The three test files, and why there are three

The same split the pulse-card item used, for the same reason: **some of this item's rules
are visible in the DOM and some are not.**

- *Visible* — the four states, the card order, the live region's words, the six route
  labels, the ink pill on the active route. These are `app/page.test.tsx`.
- *Invisible to a DOM query but catchable* — a serious or critical accessibility
  violation in any one of the four documents. These are `tests/digest-home-a11y.test.tsx`.
- *Invisible to any rendering test* — that a literal hex has crept into a **second**
  file; that a motion class has been added to the markup; that terracotta has been
  spread to a fifth place; that an inert route has become an anchor. These are
  `tests/digest-home-boundary.test.ts`, which reads the **source**.

## `app/page.test.tsx` — 31 tests

| Group | What it pins |
|---|---|
| the routing decision | anonymous → `/preview`; onboarding unfinished → `/onboarding`; onboarded → here; **the API unreachable is not a redirect**; the digest is not read for a non-signed-in visitor |
| the digest | the cards render in the **server's** order; no more cards than the server sent; the header's date line comes from the server's date and city, in the digest's own zone; the live region announces once, with the count, with a comma; the page is `force-dynamic` |
| the empty state | FR-8's exact heading; the city line; **one link and no button**; no terracotta in the empty state's own article; and it is *not* the not-composed state |
| the not-yet-composed state | "Your Pulse is being prepared."; it claims nothing about the world; it is not the empty state |
| the error state | "Couldn't reach Pulse"; the retry link; the **second consecutive** failure's label; the count is consecutive and a success breaks the run; the retry re-runs the read rather than reloading the document; it is not the session error (one `h2`, no `h1`) |
| the shell | the six routes **in the locked order**; the active route is an ink pill, never a terracotta fill; the four inert routes cannot navigate; the topbar is brand-only; the content is constrained to the reading width; the footer carries Search and the account row |

**Two of these tests drove real changes to the code**, not just to the test:

1. *"carries the six routes, in the locked order"* failed because the create sheet's
   **"Name" field was inside the `<li>`** — `AddEventButton` rendered both the button
   and the panel, so a form was nested in a navigation list. The fix was a structural
   one: `AddEventButton` gained `withoutPanel` and `onOpen`, and both nav components
   now mount `<PersonalEventsPanel>` **outside** their route list.
2. The same test then failed because the Add row rendered the glyph and the control but
   **no route label**. The `control` branch of `SidenavItem` gained its `<span>`.

**And one test was asserting the opposite of what its name said.** The test named
*"says 'Refresh page.' on the second consecutive failure"* asserted
`getByRole("link", { name: "Try again" })`. The body is what ran, so it passed, and it
passed while the feature was **absent** — the page hardcoded `attempt={0}`, so the label
could never change. The test is now written properly, and two more were added beside it
for the count itself. See the review report.

## `lib/digest-attempt.test.ts` — 11 tests

The server-owned count of consecutive digest failures — the thing §5's stateful error
rule turns on.

| Rule | Assertion |
|---|---|
| a missing cookie is no failures | `attemptFromCookie(undefined)` is 0 |
| a well-formed cookie is read | `"3"` → 3 |
| a malformed cookie is no failures, not a crash | `"not a number"`, `"-1"`, `"0"`, `""`, `"Infinity"` → 0 — the cookie is user-writable, so its contents are untrusted input |
| a fractional count is floored | `"2.7"` → 2 |
| recording returns the number of **prior** failures | the first failure returns 0 and writes "1"; the second returns 1 and writes "2" |
| the count goes up | four failures → "4" |
| the count is read back | two failures → `readAttempt()` is 2; nothing recorded → 0 |
| a success clears the count | two failures, then `clearAttempt()` → 0 and the cookie is gone |
| clearing is safe when there is nothing to clear | it resolves |

**The store is a real store, not a spy.** `tests/cookie-store.ts` is a `Map` behind
`get`/`set`/`delete`, so the tests assert on the cookie's *value* — "the count went up to
2" — rather than on the fact that a method was called. A spy would only prove the call
happened; the store proves the cookie ended up right.

## `tests/digest-home-a11y.test.tsx` — 5 tests

The work item's criterion is *"axe-core reports zero serious or critical violations on
this surface."* `axe-core` was added as a devDependency for it.

| State audited | Assertion |
|---|---|
| composed | zero serious or critical violations |
| empty | zero serious or critical violations |
| not-composed | zero serious or critical violations |
| error | zero serious or critical violations |
| the landmarks are real | `main`, the `complementary` rail and the rail's own `nav` are in the document — so the gate cannot pass by auditing nothing |

**The gate runs over all four documents, not just the happy one.** A page can be
accessible when it is full and inaccessible when it is empty: an empty state with no
heading hierarchy, an error state whose retry is an unnamed control — each is a different
document and a different set of rules.

**Serious and critical only.** `minor` and `moderate` findings are advisory, and a gate
that fails on a moderate finding is a gate that gets disabled. `color-contrast` is
disabled explicitly: jsdom computes no layout, so axe has no boxes to compare and the
rule reports false positives rather than findings.

## `tests/digest-home-boundary.test.ts` — 22 tests

The source is read, the **comments are stripped**, and what remains is asserted on.

| Rule | Assertion |
|---|---|
| no literal hex colour | no `#[0-9a-f]{3,8}` in any of the ten files |
| no raw `rgb()`/`hsl()` | no colour function in any of the ten files |
| every colour from a token utility | each colour utility is one `tokens.css` declares — with `ring-1`, `border-t-2`, `border-b` excluded as **widths**, and the `text-left`-style alignment utilities excluded as **alignments** |
| no font family outside the type scale | each `[font:…]` utility names `--type-scale-` |
| no motion class in the markup | no `animate-`, `transition`, `duration-`, `delay-` or `ease-` utility anywhere |
| the pulse lands only on the skeleton | `skeleton-pulse` appears in exactly one file — the loading skeleton |
| terracotta is rationed | every terracotta utility is one of the sanctioned forms |
| the active sidenav route is an ink pill | the active branch carries `bg-surface-subtle` and no terracotta |
| the active bottom-tab slot is an ink inversion | the active branch carries `bg-ink-primary` and no terracotta |
| no nav row carries a terracotta fill | no `bg-…terracotta` in either nav component |
| no CSS pseudo-element for visible helper text | no `::after`, no `::before`, no `content-[` |
| the six routes, in order | the sidenav's `<SidenavItem label="…">` sequence is Digest / Timeline / Add / Browse / Conflicts / Settings |
| an inert route is not an anchor | the `!href` branch contains `aria-disabled="true"` and no `<Link` and no `<a` |
| the topbar is brand-only | the `<header>` contains no `<Link`, no `<button` and no `<nav` |
| the create sheet is outside the route list | neither nav's `<ul>` contains `PersonalEventsPanel`, and both files do |
| the Add glyph is drawn once | the compact button renders **no** literal `+`; each nav draws `AddGlyph` exactly once |
| the More slot is a working control | the bottom tab renders `<MoreMenu />`; the menu renders a `<Sheet` and an `onClick`; and its Browse row is inert, with no `<Link` |
| the content is constrained | the `<main>` carries `max-w-(--layout-container-max)` |
| the not-composed state is distinct | the empty state says "No qualifying events in"; the preparing state says neither it nor "Nothing on the pulse" |
| the empty state is one link and no button | exactly one `<Link`, no `<button` |
| both error labels exist | "Couldn&apos;t reach Pulse", "Try again", "Refresh page." |

## The acceptance criteria, one by one

| Criterion | How it is met | Test |
|---|---|---|
| the route decision is preserved unchanged | `homeRoute(session)` is still the decision; the unreachable case still returns a page rather than redirecting | `app/page.test.tsx` — the routing decision group, all 5 |
| the header: today dot, date line, h1, lede | `DigestHeader`; the h1 is "Today, three things matter."; the weekday is read in the digest's **own** zone via a local noon | `it shows the header's date line from the server's date and city` |
| three cards in slot order, no scoring, no sorting | `digest.cards.map(...)` in the server's order; the bucket is rendered, never re-derived | `it renders the cards in the server's order`, `it renders no more cards than the server sent` |
| the 3-card discipline holds | there is no pagination, no carousel, no "show more" — the page renders the array and stops | `it renders no more cards than the server sent`; the boundary test's motion rule |
| the empty state: FR-8's copy, the city line, one link | `DigestEmpty`; §5's copy exactly; one `Text.Meta` link; **no** CTA pair, no upsell | the empty state's five tests |
| not-yet-composed is distinct from empty | a separate `DigestPreparing` state; it claims nothing about the world | the not-composed group's two tests |
| loading: three paper rectangles, 1800ms, no spinner | `DigestSkeleton`; `skeleton-pulse 1800ms`; no spinner anywhere in the product | the boundary test's pulse rule; `styles/motion.test.ts` |
| error: both labels | `DigestError`; "Try again" first, "Refresh page." on the second consecutive failure; the count is a server-owned cookie | the error group's four tests, plus `lib/digest-attempt.test.ts` (11) |
| shell: six routes, ink pill, footer, brand-only topbar, inert routes | `Sidenav`; the ink pill; the footer pinned with `margin-top: auto`; the topbar carries only the wordmark; inert routes are `<span aria-disabled>` | the shell group's six tests, plus the boundary test's six route rules |
| the live region | `role="status" aria-live="polite" aria-atomic="true"` with the count | `it announces the digest once, in a live region, with the card count` |
| responsive | **one column at every width**, constrained to 1180px — a deliberate deviation, recorded below | `it constrains the content to the reading width`; the boundary test's constraint rule; the deviation is in the design doc's drift table row 8 |
| accessibility: zero serious or critical axe violations | the axe gate over all four documents | `tests/digest-home-a11y.test.tsx` — all five |
| the Pro upsell does not ship; "Saved this week" only if it is free | **neither ships** — there is no `SUBSCRIPTION` model, and the saved rail needs a backend read this item does not do | the design doc's D19; no rail markup exists |
| tests cover the listed cases | 31 + 5 + 22 + 11 = 69 tests across four files | — |

## The gate

```
pnpm vitest run
→ Test Files 48 passed (48), Tests 585 passed (585)

pnpm typecheck
→ ✓ Types generated successfully   (no TypeScript errors)

pnpm lint
→ clean

pnpm format:check
→ All matched files use Prettier code style!

pnpm build
→ ✓ Compiled successfully
→ Route (app)  ƒ /      ← dynamic, as it must be
```

The pnpm engine warning (`wanted: node >=24.15, current: 24.14.1`) appears on every
script invocation. It is pre-existing, unrelated to this item, and does not fail the
gate.

## The failures, and what each one was for

The first run of the page's tests failed **once** — and it was **the test doing its
job**: the create sheet was rendering inside the navigation list, so the route list
carried a form field called "Name" and the route label was missing.

| Failure | What it was | Fix |
|---|---|---|
| *"carries the six routes, in the locked order"* — expected `["Digest", "Timeline", …]` to equal `["Digest", "Timeline", "Add", "Browse", "Conflicts", "Settings"]` | **the code's fault** — the Add row rendered no label, and the create sheet was mounted **inside** the `<li>` | **code change**: `AddEventButton` gained `withoutPanel`/`onOpen`; `SidenavItem`'s `control` branch gained its label span; both navs mount the panel outside the list |

The boundary test's own first run failed **four times**, and **none** of them was the
code's fault — all four were the test asserting on the wrong thing:

| Failure | What it was | Fix |
|---|---|---|
| `border-b` failed the colour rule | the test was wrong — `border-b` is a **width**, not a colour | the width utilities were excluded, with a comment saying why |
| `aria-disabled` matched the `<Link` | the test was wrong — the `<Link>` import sits **above** the inert branch in the file, so the regex spanned the wrong region | the assertion was narrowed to the `!href` branch's own body |
| `compact ? null` not found | the test was wrong — `add-event-button.tsx` was **not in the file list** | it was added |
| "Couldn't reach Pulse" not found | the test was wrong — the source writes `Couldn&apos;t` | the assertion was corrected to the escaped form |

The fourth one is worth naming: **the boundary test found nothing wrong with the
product, and that is what a boundary test is for.** Its job is to be uneventful.

Then the review's fixes broke the tests again — the new `cookies()` call needs a request
scope, so `next/headers` is mocked — and **three of the error state's tests failed**,
which turned out to be the code's fault and not the test's:

| Failure | What it was | Fix |
|---|---|---|
| *"says so, and offers one retry"* found no "Try again" link | **the code's fault** — `recordFailure()` returned the *new* total, so the first failure already counted as one and rendered "Refresh page." | **code change**: `recordFailure()` returns the number of *prior* failures; the cookie holds the total |
| *"counts consecutive failures"* — the count was not 2 | the same | the same |
| *"retries the read rather than reloading the document"* — the href was wrong | the same, plus the href is now the fixed `/?retry=1` | the same |

That first one is the interesting one. **The new code was wrong in the direction the old
code was wrong in**: the count was one too high, so the *first* failure rendered the
*second* failure's label. The tests caught it because they were written to assert the
specific label for the specific failure — which is exactly what the original test was
not doing.

## One thing the tests could not verify

**The page has never been in a browser.** jsdom computes no layout, no stacking order
and no contrast, so three things are asserted in the source rather than observed:

- that the two-column rail's absence is a *choice* and not a *breakage* — the layout is
  one column at every width, deliberately;
- that the terracotta reads as terracotta against the warm and cool surfaces;
- that the skeleton actually reads as three paper rectangles at a glance, and that the
  1180px constraint reads as breathing room rather than as a narrow column.

The first is a decision, recorded in the design doc's drift table. The second and third
are visual, and a browser is where they get checked.
