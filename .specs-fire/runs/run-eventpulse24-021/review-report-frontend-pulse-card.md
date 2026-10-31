# Review report: `frontend-pulse-card`

**Work item**: `frontend-pulse-card`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-31

---

## The verdict

**Approved.** The card renders what it was given and decides nothing, which is the whole
point of the item. The review found and fixed **two substantive bugs** — one of them
serious — and made **one design correction** (the indicator's name became visible).

The serious bug is worth stating plainly, because it is the kind that survives every
test: **the tooltip triggers were unclickable.** The stretched `<Link>` that makes the
whole card the tap target is `absolute inset-0 z-0` and comes *later* in the DOM, so it
painted over the confidence and badge `<button>`s. Every automated test passed — the
buttons were present, labelled, focusable and reachable by every accessibility query.
Only a real browser would have shown the failure. The component's own comment asserted
the opposite of what the CSS did.

---

## What the review checked

| Property | How | Result |
|---|---|---|
| the card decides nothing | the component's data flow read line by line: no re-bucketing, no re-sorting, no recomputed date | green |
| the explanation is required and is a union | `Explanation` has no default; `PulseCardProps.explanation` is not optional | green |
| the two indicators are distinguishable | the visible name and the `aria-label` both say "Relevance" or "Event Fit" | green |
| the whole card is the tap target | one `<Link>`, `absolute inset-0` | green — but see the stacking bug below |
| the tooltips are reachable | the stacking order of the trust row against the link | **red → fixed** |
| the trust signals never hide | no density state, no `compact` prop, no media-query branch | green |
| no visible numeric on the confidence indicator | the card's visible text | **red → fixed** |
| every colour comes from a token | the boundary test's four colour rules | green |
| terracotta is rationed | the boundary test's terracotta rule | green |
| the separator is DOM text | the boundary test's pseudo-element rule | green |
| the motion is one fade | the boundary test's motion rules | green |
| the label tables match the backend's | `digest-labels.test.ts` reads `constants.py` | green |
| the accessible name reads the card | one `accessibleName()` assembly | green |
| the time conversion is at the presentation edge | `utcInstantToLocal` in the component | green |

---

## The three changes the review made

### 1. The tooltip triggers sit above the stretched link (the stacking bug)

**The bug.** The card's whole tap target is a stretched link:

```tsx
<Link className="absolute inset-0 z-0 rounded-card …" />
```

It is absolutely positioned and it comes **last** in the DOM. The tooltip triggers are in
the normal flow with no `z-index`:

```tsx
<div className="flex items-center gap-2">      {/* ← no z-index */}
  <ConfidencePulse … />                          {/* ← the button */
  <SourceBadgeBadge … />                        {/* ← the button */
</div>
```

Both are positioned elements, both have `z-index: auto`, and the link comes later in the
document — so the link paints **over** both buttons. They were covered by an invisible
`<a>` that spans the entire card. Clicking the confidence dots navigated to the event
instead of opening the tooltip; the badge's tooltip was equally unreachable.

**The fix.** The trust row is raised above the link:

```tsx
<div className="relative z-10 flex items-center gap-2">
```

`relative` puts the row into the positioned-elements painting group and `z-10` puts it
above the link's `z-0`. The tooltips are `absolute z-10` inside that row, so they are
above the link too.

**Why no test could have caught it.** jsdom computes no stacking order and has no
layout engine. Every accessibility query found the buttons; every DOM assertion found
them; `userEvent.click` on the button would have dispatched the event, because jsdom does
not do hit-testing. The only way to see this bug is to read the CSS stacking rules
against the DOM order — which is exactly what the code review is for.

**The regression test.** A rendering test cannot compute stacking, so the test asserts
the *classes* that produce it: the link carries `z-0`, the trust row carries `relative`
and `z-10`, and the tooltip carries `absolute` and `z-10`. It will fail if anyone
removes the raise, and the comment says why the classes are load-bearing.

### 2. The confidence indicator's name is visible (a design correction)

**The design had it as `sr-only`.** The review changed it to a **visible** label.

The reasoning: the five dots are the *same shape* for the Relevance Pulse and the Event
Fit. A screen-reader user gets the `aria-label` — "Relevance 4 of 5" — and is fine. A
**sighted** user sees five identical dots and five identical unfilled dots and has no
way to tell which indicator they are looking at. The words are the only thing keeping
the two apart (AD-10), and the design had put them where only one of the two audiences
could see them.

The visible label is `aria-hidden="true"`, so it is not announced a second time — the
`aria-label` remains the single accessible name for the button.

**The visible numeric stays invisible.** `DESIGN.md:308` renders the count beside the
dots; `EXPERIENCE.md:210` says "Dots only. No numeric label visible." The review kept
the no-numeric rule, because a visible number is what makes the Relevance Pulse legible
as a *score* — and the same number on an Event Fit card would be the two indicators
wearing each other's clothes. The count lives in the `aria-label`, where it belongs.

### 3. The tooltip's contributing factors are the persisted tags

**The design did not specify what the confidence tooltip said.** The implementation had
to answer, and the answer is constrained by AD-10: "an explanation is never generated at
view time."

The card cannot compute "Strong match on your top three interests" — that text was never
persisted, and computing it at render would be exactly the failure AD-10 exists to
prevent. But the **persisted Why-this Tags** *are* the persisted contributing factors: the
server chose them and stored them.

So the tooltip says **"Surfaced because:"** followed by the tags. It restates persisted
facts and generates nothing. The full prose breakdown is the Detail Screen's job, not
the card's.

**A side effect worth noting:** the tooltip no longer restates the count, which is what
the visible-numeric test was tripping over. Both changes point the same way — the count
is in the `aria-label`, and nowhere else.

---

## Decisions the review confirmed

These were recorded in the design's drift table and the review checked each one against
the spines.

| The question | The spines disagree? | The decision | Why |
|---|---|---|---|
| the conflict mark's size | `DESIGN.md` says 8px; ASSUM-13 locks 6px | **6px** | ASSUM-13 is an explicit lock |
| a visible confidence numeric | `DESIGN.md` says yes; `EXPERIENCE.md` says no | **no** | a visible number makes the indicator legible as a score, which is the AD-10 confusion |
| the headline's role | — | `<h3>` | the card sits under the page's `<h1>`/`<h2>` |
| the card's fill and border | — | `bg-surface-elevated`, `border-border-subtle` | `DESIGN.md` `component.surface.card` |
| the tooltip's surface | — | `bg-surface-elevated` + `shadow-floating` | the tooltip must be *above* the card's fill, so it cannot use it |
| the hover fill | — | `bg-surface-subtle` | a swap, not a shadow — `DESIGN.md` says no shadow is ever added |
| the tag separator | `DESIGN.md` middle dot; `EXPERIENCE.md` comma | **comma** | `EXPERIENCE.md:736` says the tags are announced as comma-separated text; a middle dot would announce "nearby dot tonight" |
| `official_site`'s tooltip copy | — | "Verified venue or organizer." | `EXPERIENCE.md` §4 |
| the discovery stripe's label | — | "Public event" | the slot is `serendipity` but the *category* is public; the PRD's `discovery` is the tag |
| which slot gets which slate | `nearby` → full, `serendipity` → 0.85 | as decided | `DESIGN.md` names slate as the "serendipity / discovery" stripe |

**The conflict mark needed a shape, not just a colour.** The conflict dot and the
confidence dots are both 6px circles. A 6px amber circle next to five 6px circles is
not distinguishable. The design's options were all bad: enlarging breaks ASSUM-13,
reshaping breaks "filled circle", and colouring it amber is what it already was. The
review accepted a **`ring-1 ring-ink-faint`** — the ring makes it distinct in shape, and
`color.ink.faint` is the dimmest ink, not a chromatic one, so no colour reservation is
broken.

**The 44×44 target with a 6px dot.** The visible dot stays 6px; the *trigger* gets
`min-h-11 min-w-11` (44px). The dot is what the user sees; the hit area is what the
finger needs.

**The personal check comes before the slot.** A personal event fills Slot 1
(`must_know`) when eligible — the backend's own rule — so a slot-first mapping would
give every personal event the must-know amber stripe and the label "Must-know". The
warm-personal tone is the tone of the *kind*, not the slot (FR-19).

---

## Things the review looked for and did not find

- **No second transition.** `motion.fadeIn` is the only one; the boundary test asserts no
  Tailwind motion class appears in the markup, and the hover is a swap rather than a
  transition.
- **No shadow on the card.** The only shadow is `shadow-floating` on the tooltip.
- **No literal colour.** No hex, no `rgb()`, no `hsl()` — and no token utility outside
  what `tokens.css` declares.
- **No icon-only badge.** Every variant has a visible text label (WCAG 1.1.1).
- **No hover-only affordance.** The `▸` reveals on `group-focus-within` as well as
  `group-hover`, and the tooltips reveal on `group-focus-within` as well.
- **No density state.** There is no `compact` prop and no media-query branch that drops
  a signal.
- **No client-side derivation of the card's facts.** The tags are `slice`d (the cap is
  specified by `EXPERIENCE.md`) but not re-sorted; the bucket is rendered, never
  recomputed; the date is converted, never recomputed.

---

## One thing the review could not verify

**The card has never been seen in a browser.** The gate is jsdom, and jsdom has no
layout engine, no stacking order and no hit-testing. The stacking bug was found by
reading CSS rules against DOM order — and it was found *late*, after the tests were
already green. That is the class of bug this suite structurally cannot catch.

The next work item (`frontend-digest-home`) renders this card in a list, and
`e2e-proof-and-contract-tests` is the item that puts the product in front of a real
browser. The stacking fix should be confirmed there.

**What the review would check next time**, and records here so the next item inherits it:

1. Any element that is `absolute` and covers its container must be checked against
   **every** interactive element inside that container, for the stacking order.
2. A test that asserts on classes is weaker than a test that asserts on behaviour — but
   where the browser is the only oracle, the class assertion is the honest substitute,
   provided the comment says what is load-bearing and why.
