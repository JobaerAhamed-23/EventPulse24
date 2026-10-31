# Test report: `frontend-event-detail`

**Work item**: `frontend-event-detail`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-31

---

## What was built

| File | Kind | What it is |
|---|---|---|
| `frontend/app/events/[id]/page.tsx` | new | the route — one server read, four answers, the locked order |
| `frontend/app/events/[id]/loading.tsx` | new | the Detail Screen's own skeleton |
| `frontend/lib/event-detail-read.ts` | new | the server-side read, typed as `found` / `anonymous` / `removed` / `unavailable` |
| `frontend/lib/detail-time.ts` | new | the time arithmetic: instant → the reader's wall-clock, and the venue's |
| `frontend/lib/detail-labels.ts` | new | the two vocabularies: the factor lines and the neighbour prose |
| `frontend/components/detail/detail-header.tsx` | new | the trust row (badge → pulse), the name, when · where |
| `frontend/components/detail/detail-breakdown.tsx` | new | the Why-this Tags row and the why-this breakdown |
| `frontend/components/detail/detail-actions.tsx` | new | Save to Pulse and Share |
| `frontend/components/detail/detail-reminder.tsx` | new | the display-only reminder picker |
| `frontend/components/detail/detail-neighbors.tsx` | new | the neighbour line, or nothing |
| `frontend/components/detail/detail-states.tsx` | new | the skeleton, the removed state, the error state |
| `frontend/components/detail/trigger-tip.tsx` | new | the shared tooltip: `<button>` + `aria-describedby` + `role="tooltip"` |
| `frontend/app/events/[id]/page.test.tsx` | new | 44 tests — the screen, as a rendered DOM |
| `frontend/tests/event-detail-a11y.test.tsx` | new | 6 tests — the axe-core gate over five documents |
| `frontend/tests/event-detail-boundary.test.ts` | new | 24 tests — the structural rules, asserted against the source |
| `frontend/lib/detail-labels.test.ts` | new | 13 tests — the two vocabularies |
| `frontend/lib/detail-time.test.ts` | new | 9 tests — the time arithmetic |
| `frontend/components/detail/detail-actions.test.tsx` | new | 6 tests — the action row's behaviour |

**102 new tests** across six files.

## The six test files, and why there are six

The screen has three kinds of rule, and no single kind of test can see all of them:

- *Visible in the DOM* — the order, the tags, the absence of a breakdown, the neighbour
  prose, the states. That is `page.test.tsx`.
- *Visible only in the source* — that no hex value has crept in, that the confidence
  tooltip does not restate the mockup's prose, that the picker has no `<button>`. That
  is `event-detail-boundary.test.ts`, which reads the **source** with the comments
  stripped.
- *Arithmetic* — the factor lines and the time conversion are pure functions and are
  pinned directly, rather than only through a render. That is `detail-labels.test.ts` and
  `detail-time.test.ts`.

And two more, for two specific reasons:

- `event-detail-a11y.test.ts` runs axe over **five** documents, not one. A page can be
  accessible when it is full and inaccessible when it is empty.
- `detail-actions.test.tsx` exists because `page.test.tsx` **mocks the action row out** —
  the page's tests are about the page's composition, and the row's own behaviour (the
  POST shape, the saved state, the refused save) would have been untested otherwise.

## `page.test.tsx` — 44 tests

| Group | What it pins |
|---|---|
| the read | the four answers; `removed` and `unavailable` are different documents; a 404 is not an error |
| the locked order | the badge before the pulse; the name before the time; the tags before the description; the action row before the breakdown |
| the tags | the same three tags as the card, in the persisted order, comma-separated; no row when there are none |
| no composition | no breakdown section in the DOM; no confidence pulse; no badge; no Event Fit value anywhere |
| the anonymous case | public chrome, no sidenav, no breakdown, no pulse, no neighbour count, no saved state, no picker, no action row |
| the breakdown | one factor per line; the persisted order; an unknown tag falls back to its own label |
| the neighbour count | all four buckets; silence below the threshold; no digits in the DOM; no emoji |
| the action row and the picker | Save and Share only; the picker is display-only; both are behind the signed-in guard |
| the sold-out state | the line replaces the save and the picker; the breakdown still renders |
| the time | the local time; the venue's time; the weekday and the date in step |
| what does not ship | no reviews, no similar events, no "report this event", no "less like this" |

**The order test asserts on the document, not on the component tree.** The locked order
is a claim about what a reader sees first, so the test indexes each marker's **parent**
within `article.children` and asserts those indices are increasing. A component-tree
assertion would not have been evidence of it.

## `event-detail-boundary.test.ts` — 24 tests

Twelve source files are read, the **comments are stripped**, and what the compiler sees is
asserted on. A comment is not code: these files' docstrings quote the spec, and a
source-text assertion that read them would be asserting on prose.

| Rule | Assertion |
|---|---|
| no literal hex colour | no `#[0-9a-f]{3,8}` |
| no raw `rgb()`/`hsl()` | no colour function |
| every colour from a token utility | each token utility is one `tokens.css` declares |
| no font outside the type scale | each `[font:…]` names `--type-scale-` |
| no motion class | no `animate-`, `transition`, `duration-`, `delay-` or `ease-` utility |
| not the digest's pulse | no `skeleton-pulse` — the Detail Screen has its own shape |
| no exact neighbour count | no `5–9`, `10–24`, `25–99`, `100+` |
| no "neighbors N" | no such phrase |
| no emoji | no `👥` |
| no reliability claim | no `reliability`, no `bayesian`, no `0.\d+` |
| no distance claim | no "N km", no "blocks from" |
| no attendance claim | no "attended", no "no ticket required" |
| no emoji glyphs | no `📍 ⭐ 🆓 ✅ 📌 🔥` |
| no CSS pseudo-element for visible text | no `::after`, no `::before`, no `content-[` |
| no sections that do not ship | no "reviews", no "similar events", no "report this event" |
| no dismissal control | no "less like this", no `>Dismiss<` |
| the picker is display-only | no `<button` in the picker; no terracotta in it |
| the tooltip is a real tooltip | `<button` + `aria-describedby` + `role="tooltip"` + `Escape` + `pointerdown` + `hidden={!open}` |
| the read is honest about the session | `personal === null` + `sessionHeaders`; **not** `getSession` |

**That last rule is the one that would have caught the anonymous picker.** The read
derives `found` from `personal === null` — never from the session — so an anonymous
visitor's absence of personal data is a fact about the payload, not a guess about who is
looking.

## `event-detail-a11y.test.tsx` — 6 tests

axe-core over **five** documents: found, anonymous, removed, error, sold-out. The gate
fails on serious and critical only; `color-contrast` is disabled explicitly, because
jsdom computes no layout and the rule reports false positives rather than findings. One
further test asserts the landmark structure.

## `detail-labels.test.ts` — 13 tests

The factor lines and the neighbour prose, pinned directly:

| Rule | Assertion |
|---|---|
| each known tag has its own line | "It's in your city." / "It starts tonight." / … |
| a chip tag names the interest | "It matches an interest you picked: Arts & culture." |
| an unknown tag falls back to its own label | "Brand New Tag" — a new server tag appears, plainly |
| no line states a reliability, a distance, a price or an attendance | no `reliability`, no `bayesian`, no digit, no `km`, no `free`, no `attended` |
| six tags give six different lines | the set has six members |
| four buckets give four different lines | the `it.each` over `few`/`some`/`many`/`a_lot` |
| a suppressed count renders nothing | `null`, `undefined` and `""` all give `null` |
| an unknown bucket renders nothing | `a_great_many` gives `null` — the client does not invent prose |
| no bucket states a number | no digit in any line |
| no bucket carries an emoji prefix | no `👥` |

**The "no digits" rule is the strongest of these.** The neighbour line is prose — "A few
neighbors saved this." — and the count that would make it a number is not in the payload
at all (`NeighborCount` has no count field). The test asserts the *absence* of a digit so
that a future change cannot quietly reintroduce one.

## `detail-time.test.ts` — 9 tests

The rule this file exists to pin: **a timezone offset must never move the displayed date
onto a different day.**

| Rule | Assertion |
|---|---|
| the instant is read in the reader's zone | 23:00Z in New York is 6:00 PM, Saturday Nov 7 |
| the day moves when the zone crosses midnight | 23:00Z is 12:00 PM on **Sunday** Nov 8 in Auckland |
| midnight and noon | 5:00 AM is not 12 AM; 12:00Z is 12 PM |
| the venue's time shows when the reader is elsewhere | 11:00 PM in London, 6:00 PM in the venue |
| the venue's time is withheld when the clocks agree | New York and Toronto show the same hour — one time, not two |
| the reader's zone falls back to the venue's | a `null` reader zone still shows the event's time |
| no time means no time | `null`, `undefined` and `"not a date"` all give `null` |
| the weekday and the date stay in step | "Sunday" and "Nov 8" are the same wall-clock |

**The weekday is derived from the same wall-clock as the date**, by
`new Date(Date.UTC(y, m - 1, d)).getUTCDay()` — not by formatting the instant again.
Two independent `Intl` calls could disagree across a DST boundary; one wall-clock
cannot.

## `detail-actions.test.tsx` — 6 tests

The action row, which `page.test.tsx` mocks away:

| Rule | Assertion |
|---|---|
| the row offers Save and Share | both buttons |
| the saved state is known before the press | `saved` renders "Saved to your Pulse", and the unsaved label is **gone entirely** |
| the save posts with the event's id | `POST("/api/personal/saved-events/{catalog_event_id}", { params: { path: { catalog_event_id: "event-1" } } })` |
| the saved state appears once the save succeeds | the button becomes "Saved to your Pulse" |
| a refused save is shown calmly | a 409 gives "Couldn't save that", and the button still says "Save to Pulse" |
| an already-saved event does not post | the button is disabled, and no request is made |

## The acceptance criteria, one by one

| Criterion | How it is met | Test |
|---|---|---|
| the locked element order | asserted as **document** order | *the locked order* (2 tests) |
| the tags are byte-identical to the card's | the same persisted keys, the same `tagLabel`, the same order | *the tags* (3 tests) |
| one factor per line, in prose | the closed factor vocabulary, one `<li>` per tag | *the breakdown* (4 tests) |
| no composition, no breakdown | the section element is **not in the DOM** | *no composition* (4 tests) |
| anonymous visitors see nothing personal | the whole personal half is behind the guard | *the anonymous case* (5 tests) |
| the neighbour count is bucketed prose, silent below 5 | four buckets; `null` renders nothing | *the neighbour count* (7 tests) |
| no reviews, no ratings, no corroboration count | absent from the DOM entirely | *what does not ship* |
| no "similar events you've attended" | absent from the DOM entirely | *what does not ship* |
| the reminder picker is display-only or absent | **display-only**: `<span>` chips, no `<button>` | *the action row and the picker*; the boundary test's picker rule |
| "Report this event" is absent rather than dead | no FR-59 flow exists, so nothing is rendered | the boundary test's "no sections that do not ship" rule |
| the three states | the skeleton's three shapes; the removed copy; the error copy and its single action | *the removed state*, *the error state*, the boundary test's `skeleton-pulse` rule |
| the tooltips are real tooltips | `<button>` + `aria-describedby` + `role="tooltip"`; `Esc`; outside-tap | the boundary test's tooltip rule |
| the time is user-local, with the venue's beside it | the reader's wall-clock, and the venue's when the two differ | `detail-time.test.ts` (9 tests) |
| axe-core, zero serious/critical | five documents | `event-detail-a11y.test.tsx` (6 tests) |
| the tests cover the listed ground | order, tag equality, the breakdown, no-composition, anonymous, every bucket, the states, the tooltip, the cross-timezone display | the six files above |

## The gate

```
pnpm vitest run
→ Test Files 54 passed (54), Tests 687 passed (687)

pnpm typecheck
→ ✓ Types generated successfully   (no TypeScript errors)

pnpm lint
→ clean

pnpm format:check
→ All matched files use Prettier code style!

pnpm build
→ ✓ Compiled successfully
  Route (app)  ƒ /  ·  ƒ /events/[id]  ·  ƒ /onboarding  ·  ○ /preview …
```

The pnpm engine warning (`wanted: node >=24.15, current: 24.14.1`) appears on every
script invocation. It is pre-existing, unrelated to this item, and does not fail the
gate.

## The failures, and what each one was for

The screen's tests failed **10 times** on their first run. **One** of them was the tests
doing their job — they caught a component that was wrong. The other nine were the tests
being imprecise about what they were looking at.

| Failure | What it was | Fix |
|---|---|---|
| the reminder picker rendered for an anonymous visitor | **the component's fault** — the picker sat outside the `personal` guard | **component change**: the picker and the action row are both behind the guard |
| `getByText(/Nearby, Tonight…/)` found nothing | the text is split across `<span>`s, so no single element holds it | a `textOf()` helper that reads an element's `textContent` |
| "found multiple elements with the role banner" | the shell's topbar and the detail header are both `<header>` | scoped to `article header` |
| "found multiple elements with the role list" | the shell has lists of its own | scoped to `[data-detail-breakdown] ul` |
| the error state had two links home | `PreAuthFooter` has links of its own | scoped to `[data-detail-error]` |
| "shows the event's date and time" | **the test machine is not in New York**, so the local time is the test's, not the fixture's | rewritten as a shape assertion, and the arithmetic moved into `detail-time.test.ts` where the zone is a parameter |
| the order test's `tags` index was `-1` | the marker was nested deeper than the test assumed | each marker's **parent** is indexed within `article.children` instead |
| `getByRole` threw on an absent button | `getByRole` throws when the element is missing — a negative assertion needs `queryByRole` | the negative assertion now uses `queryByRole` |

**The picker bug is the reason this report exists.** It was invisible to the page's own
tests in one direction and visible in the other: the anonymous document was *supposed*
to have no personal controls, and it had one. A control that cannot be persisted for an
anonymous visitor is the same failure as a control that does nothing — and the screen is
supposed to be careful about exactly that.

## What could not be verified here

Three of the work item's criteria are claims about a **real browser**, and jsdom is not
one:

- **Lighthouse accessibility ≥95** and **LCP <1.5s at 3G-fast** — a Lighthouse run
  measures a rendered page under a throttled network. Neither number is asserted by this
  suite, and neither can be.
- **Contrast** — `color-contrast` is disabled in the axe gate, because jsdom computes no
  layout and the rule reports false positives. The colours are token-driven and the
  token file is the source of truth, but the *rendered* contrast is unmeasured.
- **The touch behaviour** — the tooltip's `Esc` and outside-tap dismissal are asserted
  on the source and on the DOM, and the *keyboard* path is unit-testable, but the
  "no hover-only tooltips on touch" claim is about a finger on glass.

These belong to `e2e-proof-and-contract-tests`, which is the run's last item and the one
that puts the product in front of a real browser.
