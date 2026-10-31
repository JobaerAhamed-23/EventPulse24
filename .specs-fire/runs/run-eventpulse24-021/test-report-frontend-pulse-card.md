# Test report: `frontend-pulse-card`

**Work item**: `frontend-pulse-card`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-31

---

## What was built

| File | Kind | What it is |
|---|---|---|
| `frontend/components/digest/pulse-card.tsx` | new | `Card.PulseDigest` — the card itself, plus `categoryFor`, `MAX_WHY_THIS_TAGS` and the `Explanation` union |
| `frontend/lib/digest-labels.ts` | new | the two label tables: the Why-this Tags and the Source Badge |
| `frontend/components/digest/pulse-card.test.tsx` | new | 71 tests — the card's behaviour, as a rendered DOM |
| `frontend/tests/digest-labels.test.ts` | new | 11 tests — the label tables against the backend's own constants |
| `frontend/tests/pulse-card-boundary.test.ts` | new | 13 tests — the card's structural rules, asserted against the source |

## The three test files, and why there are three

**A rendering test cannot see everything.** Some of this item's rules are visible in the
DOM and some are not:

- *Visible* — the stripe's colour, the tags being capped at three, the badge having a text
  label, the five dots, the `▸` appearing on hover.
- *Invisible* — that the card contains no literal hex value; that a hex value has not
  crept into a **second** file; that the tag separator is a DOM character rather than a CSS
  pseudo-element; that the terracotta has not been spread to a fifth place.

The visible half is `pulse-card.test.tsx`. The invisible half is
`pulse-card-boundary.test.ts`, which reads the **source** and asserts on it. And
`digest-labels.test.ts` exists because the frontend cannot import Python: the chip
labels are restated in `lib/digest-labels.ts`, and only a test that reads
`backend/shared/constants.py` can stop that restatement from going stale.

## `pulse-card.test.tsx` — 71 tests

| Group | What it pins |
|---|---|
| the anatomy | the article, the kicker, the headline, the tag row, the meta row; the link's `href` |
| the category stripe | the stripe is decorative (`aria-hidden`); the kicker repeats its meaning in words; `Personal` beats the slot; `must_know` → amber; `serendipity` → the 0.85 slate |
| the Why-this Tags | at most three; the persisted order; the labels; the comma separator; no row when there are no tags |
| the confidence indicator | five dots always; the count in the `aria-label` and **not** on the card; the indicator named in words; the `Explanation` union required |
| the Source Badge | every variant's label and tooltip; the terracotta only on `official_site`; the warning only on `crawled_html`; the italic only on `community`; the text label always present |
| the whole card is the tap target | one link; `absolute inset-0`; the terracotta focus ring; the accessible name reads the card; the `▸` is decorative and revealed on hover **and** focus; the tooltip triggers sit above the link |
| the trust signals never hide | the tags, the pulse and the badge are all present together; there is no density state and no compact variant |
| what the card does not do | it does not re-bucket, re-sort, re-label or recompute the date; it renders what it was given |
| a card whose facts have moved on | a changed title, a changed tag, a changed time — the card follows, it does not argue |

**Two of these tests drove real changes to the component**, not just to the test:

1. *"shows no visible numeric"* failed because the card's `textContent` contained
   "4 of 5" — from the **hidden tooltip**. The fix was a component change, not a test
   change: the indicator's name moved out of `sr-only` and became a **visible** label
   (`aria-hidden`, so it is not announced twice), and the tooltip's heading no longer
   restates the count. The dots are now never the only signal, and the count lives only
   in the accessible name.
2. *"keeps the tooltip triggers above the stretched link"* is the test for the stacking
   bug the code review found — see below.

## `pulse-card-boundary.test.ts` — 13 tests

The source is read, the **comments are stripped**, and what remains is asserted on. A
comment is not code: the card's docstrings quote the spec — they mention the middle dot,
the pseudo-element rule and the preview's vocabulary — and a source-text assertion that
read them would be asserting on prose.

| Rule | Assertion |
|---|---|
| no literal hex colour | `cardCode` matches no `#[0-9a-f]{3,8}` |
| no raw `rgb()`/`hsl()` | `cardCode` matches no colour function |
| every colour from a token utility | each `bg-`/`text-`/`border-`/`ring-`/`outline-` token is one `tokens.css` declares (`ring-1` is a width, not a colour, and is excluded) |
| no font family outside the type scale | each `[font:…]` utility names `--type-scale-` |
| no font family utility outside the three | `font-display`/`font-body`/`font-mono` only; the six weight utilities are excluded because they are weights |
| no motion class in the markup | no `animate-`, `transition`, `duration-`, `delay-` or `ease-` utility; `fade-in` **is** present |
| the separator is DOM text | no `::after`, no `::before`, no `content-[` |
| the separator is the comma | the separator expression contains `", "` |
| terracotta is rationed | every terracotta utility is `text-accent-terracotta` or `focus-visible:outline-accent-terracotta` |
| no stripe colour on an interactive element | `accent-slate`, `accent-amber` and `warm-personal` appear only as `bg-` utilities |
| the label tables have no hex | `labelsCode` matches no hex |
| the label tables are not the preview's | `labelsCode` contains no `preview-labels` |

## `digest-labels.test.ts` — 11 tests

This file reads `backend/shared/constants.py` — the chip table and the fixed
`RANKING_TAG_*` keys — and checks the frontend's restatement against it.

| Rule | Assertion |
|---|---|
| the chip labels match the backend's exactly | each `(slug, label)` pair is the frontend's `tagLabel("matches_<slug>")` |
| every chip has a real label | no chip renders as its raw slug |
| no chip of the frontend's own | an unknown slug falls back to its title-cased slug; the backend does not have it |
| every fixed tag has a label | each `RANKING_TAG_*` key has a human label |
| the two weekend vocabularies stay apart | `this_weekend` → "This Weekend"; `weekend` → "This weekend" — the backend's naming drift, recorded not papered over |
| an unknown tag is rendered, not dropped | `a_brand_new_tag` → "A Brand New Tag" |
| the five badge variants are complete | each has a label and a non-empty tooltip |
| the terracotta belongs to `official_site` alone | the other four are not official |
| an unknown source borrows nothing | "Listed", not official |
| the warning belongs to `crawled_html` alone | the other four are not warnings |
| the italic belongs to `community` alone | the other four are not italic |

## The acceptance criteria, one by one

| Criterion | How it is met | Test |
|---|---|---|
| the card renders `DigestCardOut` and decides nothing | the prop is the generated schema type; `categoryFor` reads the server's `slot`/`event_kind`; the tags are `slice`d, not re-sorted | `it renders what it was given`, `it does not re-sort the tags` |
| the explanation source is a **required** prop, and a union | `Explanation` has no default and no optional variant; `kind` is `"relevance"` or `"event_fit"` | `it requires the explanation` |
| the two indicators are told apart in words | the visible name is "Relevance" or "Event Fit"; the `aria-label` names it too | `it names the indicator in words` |
| the category stripe's meaning is never carried by colour alone | the stripe is `aria-hidden`; the kicker says the same thing | `it repeats the stripe's meaning in words` |
| the confidence indicator has five positions and no visible numeric | five dots; the count in the `aria-label` only | `it shows no visible numeric` |
| the conflict mark is 6px, amber, never red, and distinguishable | `h-1.5 w-1.5` (6px), `bg-warn-amber`, `ring-1 ring-ink-faint` | `it is amber and never red`, `it is distinct from the confidence dots` |
| the Source Badge is always inline, always with a text label | five variants, each with a visible label and a tooltip | `it gives every badge a visible text label` |
| the whole card is the tap target | one `<Link>`, `absolute inset-0` | `it covers the whole card` |
| the tooltips stay clickable above that link | the trust row is `relative z-10`; the tooltip is `absolute z-10` | `it keeps the tooltip triggers above the stretched link` |
| the accessible name reads the full card | one `accessibleName()` assembly | `it reads the full card content as its accessible name` |
| the tags are comma-separated DOM text | `", "` in the DOM, no pseudo-element | `it joins the tags with a comma`, and the boundary test's separator rules |
| at most three Why-this Tags | `MAX_WHY_THIS_TAGS = 3` | `it shows at most three tags` |
| the time is converted at the presentation edge | `utcInstantToLocal` in the component, never in a service | `it shows the time in the card's zone` |
| the trust signals never hide | no density state, no `compact` prop, no media query | `it shows the tags, the confidence pulse and the badge together` |
| every colour comes from a token | no hex, no `rgb()`, no `hsl()`; only token utilities | the boundary test's four colour rules |
| `motion.fadeIn` is the only motion | `fade-in` and nothing else | the boundary test's two motion rules |
| the UI system is "None" | a hand-rolled tooltip; no component kit, no tooltip library | the tooltip's own implementation |

## The gate

```
pnpm vitest run
→ Test Files 45 passed (45), Tests 524 passed (524)

pnpm typecheck
→ ✓ Types generated successfully   (no TypeScript errors)

pnpm lint
→ clean

pnpm format:check
→ All matched files use Prettier code style!
```

The pnpm engine warning (`wanted: node >=24.15, current: 24.14.1`) appears on every
script invocation. It is pre-existing, unrelated to this item, and does not fail the
gate.

## The ten failures, and what each one was for

The first run of the card's tests failed **10 times**, and **two** of those failures were
the tests doing their job — they caught a component that was wrong, not a test that was
wrong. The other eight were the tests being imprecise about what they were looking at.

| Failure | What it was | Fix |
|---|---|---|
| *"shows no visible numeric"* | **the component's fault** — the count leaked into the visible text through the tooltip | **component change**: the indicator's name became visible, and the tooltip stopped restating the count |
| *"keeps the tooltip triggers above the stretched link"* | **the component's fault** — the stretched `<Link>` painted over the tooltip buttons, making them unclickable | **component change**: the trust row is `relative z-10` |
| `getByText(/Nearby/)` matched two elements | the test was imprecise — the tag row and the tag's own `<span>` both contain "Nearby" | a `tagRow()` helper that finds the `<p>` by its type-scale class |
| the `▸` query matched the stripe | the test was imprecise — `span[aria-hidden]` matched the decorative stripe first | `.find()` on `textContent.includes("▸")` |
| `ring-1` failed the colour-utility rule | the test was wrong — `ring-1` is a **width**; the ring's colour is the separate `ring-ink-faint` | the width was excluded, with a comment saying why |
| `font-medium` failed the font-family rule | the test was wrong — `font-medium` is a **weight** | a `weights` set excluded the six weight utilities |
| `::after` found in the source | the test was wrong — it was found in a **comment** | `withoutComments()` strips comments before the source is asserted on |
| `::before` found in the source | the same | the same |
| `·` found in the source | the test was wrong — the **time row** legitimately uses a middle dot | the assertion narrowed to the separator expression itself |
| `preview-labels` found in the source | the test was wrong — it was found in a **comment** explaining why the file is *not* the preview's | the same |

The two component bugs are the reason the report exists. A rendering test could not have
found the stacking bug — jsdom computes no stacking order, and the buttons were
present, labelled and reachable by every accessibility query. The failure was that a
*sighted user on a desktop browser* could not press them.
