---
id: frontend-pulse-card
title: The Pulse Card component
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: completed
depends_on: [digest-read-api]
created: 2026-10-31
---

# Design: The Pulse Card component

## The problem

The digest API exists and it returns three cards, each a `DIGEST_COMPOSITION` row read
back. Nothing renders them. The signature component of the product — the thing the mockups
are mostly pictures of — has no code.

And it is not one component with one shape. `Card.PulseDigest` is used by **three**
surfaces: the signed-in home (`/`), Browse (`/browse`), and — structurally identically —
the Pulse Preview, which renders the *session-free* Event Fit rather than the per-user
Relevance Pulse. AD-10 is explicit that those two indicators must never be substituted for
one another, because they look identical on screen and mean different things. So the
component has to make the caller **say which explanation it is carrying**, and label it
accordingly.

The spec is unusually complete, and where the mockups disagree with it, **the spines
win**. Nine drift points were found in the sources during this design; each is resolved
below and each resolution is recorded, because a resolution nobody can find is a
resolution nobody can keep.

---

## The decisions

### D1 — The card is a projection, and it decides nothing

Everything the card shows was decided by the composition service and persisted (AD-10).
The card reads `DigestCardOut` and renders it. It does not re-bucket the score, re-sort
the tags, recompute the local date, or decide the category.

That constraint has teeth in three places, and each has a test:

- **The confidence is the persisted `bucket`, not the score.** `DigestCardOut.bucket` is
  1–5. The server sends the bucket precisely so the client cannot re-bucket it. The card
  clamps it — a bad value draws five dots, not six — but never re-derives it.
- **The tags are the persisted keys in the persisted order.** The card renders them in
  the order they arrive. It does not sort them.
- **The category comes from the server's `slot` and `event_kind`.** The card maps those
  to a stripe and a label (D3) — but the mapping is a **presentation** mapping, not a
  decision.

### D2 — The explanation source is a required prop, and it names itself

`Card.PulseDigest` takes an `explanation` prop with two variants:

```ts
type Explanation =
  | { kind: "relevance"; value: number }   // the per-user Relevance Pulse (AD-10)
  | { kind: "event_fit"; value: number };  // the session-free Event Fit (AD-12)
```

The component renders the same five dots for both, but the **visible label and the
`aria-label` name the source**: "Relevance" vs "Event Fit". AD-10's rule is that the two
indicators look identical on screen, so *the words* are what keep them apart. A caller
that passes nothing cannot render the card at all — the prop is required, not optional
with a default. A default would be exactly how one indicator quietly becomes the other.

**This is why the preview's existing card is not reused.** `components/preview/preview-card.tsx`
already solved the anonymous case, and its own docstring says it is "deliberately the
smallest card the preview needs, so the Pulse Digest intent can extend it rather than fork
it." So the new component is **built here** and the preview's card is *migrated onto it* —
which is the `frontend-digest-home` item's job, not this one's. This item builds the
component and proves it renders both explanation kinds.

**The existing `EventFitDots` and `Tooltip` in the preview card are the pattern this
component follows**, not code it copies: the preview's dots are `h-1.5 w-1.5` (6px) with
`gap-1` (4px) — exactly the spec — and its hand-rolled tooltip is the `DESIGN.md:124`
pattern. The preview card keeps its own implementation for now; the digest home item
consolidates.

### D3 — The category is a mapping from the server's slot and kind, and the mapping is recorded

The spines name **categories** (`public`, `mustknow`, `personal`, `discovery`), not the
backend's slots (`must_know`, `nearby`, `serendipity`). Nothing in either spine maps one
to the other. The mapping is a presentation decision, and it is:

| Backend | Visible label | Stripe | Source |
|---|---|---|---|
| `slot = "must_know"` | **"Must-know"** | `color.accent.amber` | `DESIGN.md:295`, `DESIGN.md:385` |
| `event_kind = "personal"` | **"Personal"** | `color.warm.personal` | `DESIGN.md:296`, `DESIGN.md:61` |
| `slot = "nearby"` | **"Public event"** | `color.accent.slate` | `DESIGN.md:294`, `DESIGN.md:385` |
| `slot = "serendipity"` | **"Public event"** + a `discovery` micro-tag | `color.accent.slate` at **0.85 opacity** | `DESIGN.md:297`, `DESIGN.md:65`, `prd.md:203` |

**Three things about that table need saying out loud.**

**Personal beats slot.** A personal event fills Slot 1 (`must_know`) when it is eligible —
the backend's own rule ("Slot 1, 'must-know' … is the user's own personal event"). So
`event_kind = "personal"` must be checked **before** the slot, or every personal event
would render with the must-know amber stripe and the label "Must-know". The warm-personal
tone is what FR-19 asks for, and it is the tone of the *kind*, not of the slot.

**`nearby` → the full-opacity public stripe; `serendipity` → the 0.85 discovery stripe.**
The spine has two slate treatments and the backend has two public slots, and nothing
joins them. The reading above is the one every spine line supports: `DESIGN.md:65` names
`color.accent.slate` as "the **serendipity / discovery** card category stripe", and
`prd.md:203` says Slot 3's tag reads `discovery`. So Slot 3 is the discovery treatment,
and `nearby` is the plain public one. **Recorded because the spines do not resolve it.**

**Discovery has no stripe label of its own — the `discovery` micro-tag is its label.**
`DESIGN.md:107` requires every stripe to be paired with "a visible text label on the card
itself", and `DESIGN.md:297` gives discovery only a micro-tag in the micro-tag row. So the
card renders **"Public event"** in the kicker for a discovery card *and* the `discovery`
micro-tag in the tag row. The stripe is never alone: there is a kicker label on every
card, and the discovery card carries a second, tag-shaped one.

**The must-know cap is not the card's job.** `DESIGN.md:295` says the must-know stripe
"should appear on fewer than ~10% of cards in any given view" — a property of the *view*,
not of the card. The card renders the stripe the server's slot asks for; the cap belongs
to the composition service (which decides the slots), not here.

### D4 — Every stripe is paired with a visible text label, and the label is in the kicker

`DESIGN.md:107` requires the pairing for **every** stripe, and `DESIGN.md:385` names the
three labels: "Public event", "Must-know", "Personal". The kicker — the
`type.scale.meta.sm` line in `color.ink.muted` at the top of the anatomy — is where the
label lives. That is the natural home: `EXPERIENCE.md:723` says the warm/cool tone is
"accompanied by text label 'Personal' / 'Public event' in `Text.Meta`", and the anatomy
puts a `meta.sm` kicker right above the headline.

So the card's top row is: **the category kicker on the left, the trust row on the right**
(conflict indicator, confidence pulse, source badge). That matches `EXPERIENCE.md:1029-1030`:
"Source Badge — top-right of card", "Confidence Pulse — top-right of card, immediately
left of Source Badge".

**The stripe colours never appear on an interactive surface.** `DESIGN.md:105-106` reserves
slate and amber for category stripes and `DESIGN.md:241` reserves warm-personal for the
Personal tone. The mockup's amber-tinted "Why this?" button and its violet `#B59CE8`
save button are both violations — the violet is in no token table at all — and neither is
reproduced.

### D5 — The confidence indicator: five positions, always, and no visible numeric

`DESIGN.md:308` and `EXPERIENCE.md:206-216` agree on the shape: five 6px dots, 4px apart,
filled in `color.ink.primary` and empty in `color.ink.faint`, `radius.full`. Five
positions **always** — a one-dot indicator is a different component, not a smaller one.

**The visible numeric is omitted, and the disagreement is recorded.** `DESIGN.md:308` says
"The numeric count is rendered in `{type.scale.numeric}` next to the dots";
`EXPERIENCE.md:210` says "Dots only. **No numeric label visible.**" The work item rules
for EXPERIENCE ("Default shows **dots only with no visible numeric**"), and the reason is
principled rather than arbitrary: the numeric is what makes the *Relevance* Pulse legible
as a score, and the same numeric on an Event Fit card would be the two indicators wearing
each other's clothes — exactly what AD-10 forbids. **The number is in the `aria-label`,
where it belongs: `"Relevance 4 of 5"` / `"Event Fit 4 of 5"`.**

**The tooltip's contributing factors come from the persisted tags, not from a
recomputation.** This is the AD-10 rule in its most specific form: "an explanation is never
generated at view time." The card cannot compute "Strong match on your top three interests
and within 2 km" — that text was never persisted, and inventing it would be a client-side
explanation of a server-side decision. So the tooltip lists **the persisted Why-this tag
labels**, one per line. The tags *are* the persisted contributing factors; `prd.md:203`
calls them "category descriptors" and the Detail Screen's full breakdown is the prose
version of the same fact.

That is why the tooltip's lines are the tags and not the mockup's prose. The mockup's
copy is not wrong — it is a *different* surface (the Detail Screen's "Surfaced because"
expansion), and this item is not that surface.

### D6 — The source badge: five variants, each with a visible inline label

`DESIGN.md:301-307` and `EXPERIENCE.md:218-226` agree: five variants, each with a
**visible inline text label** (never icon-only, WCAG 1.1.1), always inline in the card's
top-right trust row, never behind a tap.

| Variant | Label | Glyph | Label colour |
|---|---|---|---|
| `official_site` | **Official** | terracotta checkmark | `color.accent.terracotta` |
| `community` | **Community** | ink-bordered checkmark | `color.ink.primary` (italic) |
| `aggregator` | **Listing site** | ink-bordered chain | `color.ink.secondary` |
| `user_imported` | **Forwarded** | ink-bordered inbox | `color.ink.secondary` |
| `crawled_html` | **Unverified** | amber warning triangle | `color.signal.warn` |

**`official_site` is terracotta — one of the four sanctioned uses.** `DESIGN.md:64` names
them: the `Indicator.Today` dot, the `Button.Primary` fill, the `Badge.Source.verified`
fill, and the focus ring. `DESIGN.md:302` confirms the badge case explicitly ("One of the
four sanctioned terracotta uses. The only one that appears on a card body besides the
`Indicator.Today` dot"). The mockup renders it green with a "✅ Verified" label; that is a
direct violation of the rationing rule and is not reproduced.

**A personal event has no badge.** `DigestCardOut.source_badge` is `None` for a personal
event, and `None` means "there is no source", not "unknown" (the backend's own docstring).
So the card renders **no badge** — it does not render a "Listed" fallback for a `None`
that means "no source". A personal event's provenance *is* the Personal label.

**The `crawled_html` one-time tooltip.** `DESIGN.md:200` requires a one-time "Why does
this show ⚠?" tooltip, once per user per event. **That is a per-user, per-event, persisted
fact — so it cannot be a client-side `localStorage` flag.** The backend owns it; the client
has no endpoint for it in this item's contract. So the card renders the `crawled_html`
variant with its **persistent** tooltip ("Read from a public page. We could not confirm it
with the organizer.") — the same tooltip the other variants have — and the *one-time*
variant is recorded as **not implementable without a backend endpoint**, which is out of
this item's scope. The alternative — shipping a `localStorage` flag — would make the
one-time behaviour depend on the browser rather than on the user, which is the wrong
subject for a per-user fact.

**The tooltip copy conflict is resolved to §4.** `EXPERIENCE.md:116` gives the
`official_site` tooltip as "Official site. Verified venue." while `EXPERIENCE.md:221`
gives it as "Verified venue or organizer." Both are in the same document.
`EXPERIENCE.md:1197` (ASSUM-9) locks the tooltip text to **§4**, so §4's wording wins:
"Verified venue or organizer." The existing `lib/preview-labels.ts` already uses §4's
wording, so this is also the choice that keeps one copy in the codebase.

### D7 — The conflict indicator: 6px, amber, never red, and it never collapses

`DESIGN.md:310` and ASSUM-13 (`EXPERIENCE.md:1209-1210`, RESOLVED) both say **6px**;
`DESIGN.md:293`'s "8px" is stale, and the mockup's 10px is drift. `color.warn.amber`,
`aria-label="Schedule conflict"`, top-right.

**It is a separate element from the confidence dots, and its shape says so.** The
confidence dots are 6px circles too — so the conflict mark is **not** a circle of the same
size, or it would be invisible against a five-dot row. `DESIGN.md:310` says "Distinct in
shape and position from the Source Badge and Confidence Pulse dots", and `EXPERIENCE.md:721`
says "Shape distinct from Source Badge and Confidence Pulse dots."

**So the conflict mark is a 6px filled circle with a 1px ink-faint ring around it** — the
ring is what distinguishes it from an unfilled confidence dot at a glance, and the ring is
not a colour signal (it is `color.ink.faint`, the dimmest ink, not a chromatic one), so it
does not break any reservation. The alternative — making it larger — would break the
locked 6px size. The alternative — making it a different shape — would break "filled
circle". So the ring is the answer, and it is recorded.

**Never red.** `DESIGN.md:63`: "On dark, never red." `color.signal.error` is reserved for
destructive actions.

### D8 — The whole card is the tap target, and it is one Tab stop

`EXPERIENCE.md:180-185`: the whole card opens `/events/:id`, the `▸` is `aria-hidden` and
decorative, focus shows a 2px terracotta ring, and `aria-label` reads the full card
content.

**The implementation is a `<Link>` wrapping the card's content.** Not a `<div>` with an
`onClick` — a div is not focusable, is not in the tab order, and cannot carry a real
`href`, so all three of the spec's requirements (focusable, one Tab stop, opens a route)
would fail. A `<Link>` gives all three for free, and it is what the preview card already
does.

**But the tooltips are inside the card, and a `<Link>` cannot contain a `<button>`.**
HTML forbids interactive content inside an `<a>`. The confidence pulse and the source badge
both need a `<button>` trigger (`DESIGN.md:124`: "a `<button>` trigger with
`aria-describedby`"). So they **cannot** live inside the `<Link>`.

**The resolution: the `<Link>` is the card's *title*, and the whole card is the tap
target via a stretched overlay.** No — a stretched overlay is a hack that breaks the
focus ring and the button semantics.

**The resolution actually used: the card is a `<div>` with the `<Link>` covering the
title, and the card's own `onClick` navigates.** No — that makes the keyboard path
different from the pointer path, which is the classic accessibility failure.

**The resolution: the card is an `<article>` containing an `<a>` that is the *whole*
card, and the two tooltip triggers are the exception.** HTML5 permits an `<a>` to contain
flow content as long as there is no *interactive content* descendant. A `<button>` is
interactive content. So the tooltip triggers cannot be buttons inside the link.

**Therefore: the card's `<Link>` covers the card's *content* by absolute positioning, and
the two tooltip triggers sit above it in the stacking order.** This is the standard
"stretched link" pattern: the link is `absolute inset-0` (so its hit area is the whole
card), and the tooltip buttons are `relative z-10` (so they sit above it and remain
clickable). The focus ring is drawn on the card's wrapper when the link inside it has
focus, using `focus-within`.

That gives: one Tab stop for the card (the link), the tooltips reachable by their own
buttons (two more Tab stops — **but they are not inside the link**, so the link's
accessible name is the card's full content, not the buttons' labels), and a whole-card hit
area.

**"Reachable in a single Tab cycle" means the *card* is one Tab stop** — not that the
card contains zero other focusable elements. The confidence and badge triggers are
focusable by design (`DESIGN.md:124`: a `<button>` trigger). So the reading is: the card's
*content* is announced in one stop, and the tooltips are additional stops after it. This is
recorded because the phrase is not literal in either spine.

**The `▸` is `aria-hidden="true"`** and is not a click target — it is inside the link, so
it cannot be anything else.

**Tap targets are ≥44×44 CSS px** (`EXPERIENCE.md:704-708`). The link covers the card,
so the card's height satisfies it. The tooltip triggers are 6px dots — **and they are not
44×44**. This is a genuine tension: a 6px dot cannot be a 44px tap target. The
resolution: each trigger gets a **44×44 transparent hit area** with the 6px dot drawn
inside it, centred. The visible dot stays 6px; the target is 44×44. The badge's text
label is already inline, so its target is the label's line box plus the padding.

### D9 — The tag separator: the comma, rendered as a comma

The sources disagree: `DESIGN.md:293`, `:152`, `:263` and `:382` all show the middle dot
(`nearby · tonight · music`); `EXPERIENCE.md:1031` and `:736` say comma-separated. The
brief records the disagreement as undecided and the work item says "pick one, apply it
everywhere, and record the choice".

**The comma wins, and the reason is the screen reader.** `EXPERIENCE.md:736` says the tags
are "Announced as comma-separated text: 'nearby, tonight, music.'" A screen reader
announces the DOM's text. If the separator the client renders is a middle dot, the
announcement is "nearby dot tonight dot music" — the accessible reading and the visible
reading diverge, which is the one outcome the rule exists to prevent. So the **rendered
separator is a comma**, and the announcement is comma-separated text.

**The comma is real text, not a CSS pseudo-element.** `EXPERIENCE.md:738` is explicit:
"Visible helper text is in the DOM, not in pseudo-elements… Screen readers do not announce
`::after` content by default; visible-to-sighted, invisible-to-screen-reader is an
accessibility regression."

The mockups use the middle dot, so the mockups are the thing that changes — which the
work item's own rule licenses ("where the mockups disagree with it, **the spines win**").

**The `discovery` micro-tag joins the row.** `DESIGN.md:297` puts the `discovery` tag "in
the micro-tag row", so it is rendered as another tag, separated the same way.

**The cap is 3, and the card enforces it.** `EXPERIENCE.md:177` says "up to 3 Why-this
Tags". The server already caps them (`RANKING_MAX_TAGS`), but the client enforces it too —
a card that shows four tags is wrong regardless of what the server sent, and the cap is a
property of the component's contract.

**The italic is the token, and only the token.** `DESIGN.md:174`: "Italic is reserved for
the `type.scale.microtag` token… Bold italic is not used." So the tag row is
`type.scale.microtag` — 13px, 400, **italic** — and nothing in it is bold.

### D10 — The container is the token, and hover adds nothing but a shift

`DESIGN.md:253`: `{color.surface.elevated}` fill, 1px `{color.border.subtle}` stroke,
`{radius.card}` (12px), `{spacing.6}` (24px) padding on desktop and `{spacing.4}` (16px)
on mobile. **"No shadow is ever added."**

**The padding is responsive: `p-4 md:p-6`.** The tokens give both steps and the rule is
per-breakpoint, so both classes are on the element.

**Hover shifts the fill to `color.surface.subtle` and transitions the border to
`color.border.strong`** (`DESIGN.md:253`). The transition is a **border-colour transition
with no duration class** — the frontend's architecture test bans every Tailwind
transition/animation/duration class, and `motion.fadeIn` is the product's only transition.
So the hover is an **instant** fill swap with no fade. `DESIGN.md:386` allows exactly
this: "Communicate hover on dark via `color.surface.subtle` fill swap or 1px border
transition." The word "transition" there is descriptive, not a motion token.

**The container's default fill is `surface.elevated`, not `surface.paper`.** `EXPERIENCE.md:179`
says `color.surface.paper` with a `color.ink.faint` hairline; `DESIGN.md:253` says
`surface.elevated` + `border.subtle`. `DESIGN.md` owns the visual layer and the work item
picks the tokens. Recorded, because the drift is real.

### D11 — The headline: 22px, at most 8 words, and the cap is enforced

`type.scale.headline.md` (22px / 1.25 / 600 / display) in `color.ink.primary`, **max 8
words** (`DESIGN.md:293`, `:384`).

**The card does not truncate a long headline.** Truncating to eight words would cut a
sentence in half, and `DESIGN.md:384`'s Don't is "Wrap a long sentence as a card
headline; that is body copy, not a headline" — a truncated headline is body copy wearing a
headline's clothes. So the card renders the headline it was given, and the **8-word rule
is the server's** (it composes the headline). The card's part of the rule is to render it
at `headline.md` and not at `headline.sm` — a Browse card uses a different size, and the
same component must be able to do both.

**But a card with a 9-word headline is a server bug, and the card says so.** No — the
card does not render a warning. The honest implementation is: the card renders the
headline, and a **test** asserts the card does not truncate, plus a **test on the server**
is out of scope here. The client-side half that *is* in scope: the headline is rendered
whole, and the 8-word rule is recorded as a server-side obligation.

**`EXPERIENCE.md:179`'s "Text.Display.sm" is `DESIGN.md`'s own role vocabulary, not a
different size.** `DESIGN.md` owns the visual type scale, and the work item picks
`headline.md`. Recorded.

### D12 — The card shows nothing it was not given

The anatomy is: stripe, kicker, headline, tag row, source-and-time row, trust row. The
card does not invent:

- **A missing title.** `DigestCardOut.title` is `None` when the display facts are gone
  ("there is no name to show, and the card does not invent one"). So the card renders a
  placeholder — "Event details unavailable" — rather than an empty `<h3>`. And when
  `catalog_event_missing` is true, the card says so, because a card whose title is a
  placeholder should not look like a card whose title is a real name.
- **A missing time.** `start_time_utc` is `None` for a personal event with no time. The
  source-and-time row shows the source (or "Your event") and omits the time.
- **A price.** The catalog has no price field. The preview card's test already asserts the
  word "free" never appears; the same holds here.
- **A description, an image, a map, an attendee count, a share button.** `EXPERIENCE.md:544`
  is the mobile default's complete list, and the card is that list.

### D13 — Motion is `.fade-in`, and nothing else

`DESIGN.md:123`: `motion.fadeIn` is "a 240ms CSS `opacity` transition (no transform, no
translate)… Under `@media (prefers-reduced-motion: reduce)`, the class becomes
`transition: none`. There is no JS animation library."

The frontend's `styles/motion.test.ts` already asserts that `.fade-in` is the **only**
transition in any stylesheet and that no stylesheet contains an `animation` or `@keyframes`.
So the card's fade is the `fade-in` class and nothing else animates.

**The card carries the `fade-in` class.** A digest of three cards that arrives at once
should arrive as one fade, not three staggered ones — the product has exactly one motion
and staggering would be a second.

**The reduced-motion behaviour is inherited, not reimplemented.** `globals.css` already
collapses `.fade-in` to `transition: none` under the media query. The card does not add
its own reduced-motion branch — that would be a second copy of a rule that already exists.

### D14 — The trust signals never hide, at any density

`EXPERIENCE.md:1109-1115` is a locked anti-pattern: "Adaptive density must not hide the
trust signals (Why-this Tags, Confidence Pulse, Source Badge) at any density mode. The
mobile default exposes all three; hover/focus/long-press *add* detail but never *remove*
the trust signals."

So the card has **no density state at all**. There is no `dense` prop, no `compact`
variant, no media-query branch that drops a signal. Hover and focus *add* — the tooltips
appear, the `▸` appears — and nothing is removed.

**The `▸` appears on hover and on focus.** `EXPERIENCE.md:180` requires it on hover
(desktop) and on mobile in any focused or long-pressed state, "so the desktop hover cue
has a mobile equivalent and §6 'No hover-only affordances on `sm` viewports' is honored".
So it is revealed by `group-hover` **and** `group-focus-within`.

**The conflict indicator is exempt from density entirely** — `EXPERIENCE.md:1115`: "the
indicator itself never collapses below 6×6 px (the locked size)".

### D15 — The card is one component, three surfaces, and it lives in `components/`

The file is `frontend/components/digest/pulse-card.tsx` — kebab-case (the architecture
test enforces it), in a `digest/` folder because it will be joined by the digest home
section and the digest list. The preview card lives in `components/preview/`; the shared
card cannot live in either, because it is used by both.

**The props are shaped by the *digest* contract, not the preview's.** The card takes a
`DigestCardOut`-shaped card. The preview card's `PreviewCardOut` has a `slug`, a `venue`,
a `score` and a `tags` array; the digest card has an `event_id`, a `slot`, an
`event_kind`, a `bucket`, an optional `title` and optional times. They are different
shapes for the same *idea*, and this component is built for the digest's shape — because
the digest is the signed-in product and the preview is the anonymous one, and the preview
card is explicitly "deliberately the smallest card the preview needs".

**The component is a client component** (`"use client"`) because the tooltips are
interactive.

### D16 — The tag and badge labels are the client's business, and they live in `lib/`

The backend sends tag *keys* and badge *types* and says so: "The labels are the
frontend's." So the labels are a translation, and the translation is a **module** — not
inline in the component, and not a copy of `lib/preview-labels.ts`.

**`lib/digest-labels.ts` holds the Relevance Pulse's tag vocabulary** — which is a
*different* vocabulary from the Event Fit's. The preview's tags are `tonight`,
`tomorrow`, `this_weekend`, `in_<city>`; the Relevance Pulse's are `discovery`, `nearby`,
`tonight`, `tomorrow`, `weekend`, `saved`, and `matches_<chip_key>`.

The overlap is real and confusing: **`tonight` and `tomorrow` are in both vocabularies,
and they mean the same thing** — but `this_weekend` (Event Fit) and `weekend` (Relevance
Pulse) are two keys for one idea. That is a **backend** naming drift, not a frontend
one; the frontend translates each vocabulary on its own terms and the record notes it.

**The chip labels come from the server's chip table.** `shared/constants.INTEREST_CHIPS`
holds `("arts_culture", "Arts & culture")` — the slug and its label. The tag key is
`matches_arts_culture`, and the label is "Arts & culture" — so the frontend needs the
chip table too. **The client cannot import the backend's `shared/constants.py`.** So the
chip label table is **a small, explicit map in `lib/digest-labels.ts`**, and a test
asserts that every chip key the backend can send has a label — by reading the backend's
constants file. The frontend's `tests/` already read files outside `frontend/` (the
`tokens.test.ts` reads `DESIGN.md`), so this is the established pattern for a
cross-boundary fact.

### D17 — The times are converted at the presentation edge, in the event's own zone

AD-6: "display-time conversion happens at the presentation edge, never in domain logic."
The API sends an instant plus an IANA zone. `lib/timezones.ts` already has
`utcInstantToLocal(instant, zone)` — the same helper the preview card uses — so the card
uses it too.

**The zone shown is the event's, named.** The preview card renders the zone in parentheses
(`2026-11-07 · 18:00 (America/New_York)`). The digest card does the same, because a time
without its zone is ambiguous and the card is read at a glance.

**`tz_review_pending` is stated.** The backend sends "Whether the event's timezone is still
under review — the time is approximated and the client marks it as such." So the card
marks it — a "Time approximate" note next to the time.

### D18 — The card's accessible name is the whole card

`EXPERIENCE.md:185`: "`aria-label` reads the full card content." So the link's
`aria-label` is assembled from the card's facts: the title, the time, the place, the
category, and the trust signals. It is built by one function, so the visible card and the
announced card cannot drift.

**It is not a re-computation of the explanation.** It restates the persisted facts in
prose — it does not compute a score or a ranking.

---

## The decision table

| # | Decision |
|---|---|
| D1 | The card renders `DigestCardOut` and decides nothing: the bucket is the bucket, the tag order is the tag order |
| D2 | The explanation source is a **required** prop (`relevance` or `event_fit`) and the card names it visibly and in the `aria-label` |
| D3 | The category mapping is recorded: personal beats slot; `nearby` → public stripe; `serendipity` → the 0.85 discovery stripe |
| D4 | Every stripe is paired with a visible kicker label — "Public event", "Must-know", "Personal" — and the stripe colours appear on no interactive surface |
| D5 | The confidence is five 6px dots, 4px apart, always five, with **no visible numeric**; the tooltip's factors are the **persisted tags** |
| D6 | Five badge variants, each with a visible inline label; `official_site` is terracotta; `None` means "no source" and renders no badge; the one-time `crawled_html` tooltip needs a backend endpoint and is recorded as out of scope |
| D7 | The conflict mark is a 6px `color.warn.amber` filled circle with an `color.ink.faint` ring, so it is distinct in shape from the 6px confidence dots |
| D8 | The card is a `<Link>`; the tooltip triggers are 44×44 hit areas with `focus-within` for the ring; the `▸` is `aria-hidden` |
| D9 | The tag separator is a **comma**, as real DOM text, so the announcement matches the visible reading; the cap is 3, enforced by the card |
| D10 | The container is `surface.elevated` + `border.subtle` + 12px radius, `p-4 md:p-6`; hover swaps the fill to `surface.subtle` and adds **no shadow** and **no transition** |
| D11 | The headline is `headline.md`, rendered whole; the 8-word cap is the server's obligation |
| D12 | The card invents nothing: a missing title, a missing time and a missing badge each have a stated behaviour |
| D13 | The only motion is the `fade-in` class; the reduced-motion collapse is inherited from `globals.css` |
| D14 | The card has **no density state**: the trust signals are always present, and hover and focus only add |
| D15 | The card lives in `components/digest/pulse-card.tsx` and is shaped by the digest's contract |
| D16 | The tag and badge labels live in `lib/digest-labels.ts`, with the chip table checked against the backend's |
| D17 | The times are converted at the presentation edge, in the event's own zone, with the zone named and `tz_review_pending` marked |
| D18 | The link's `aria-label` is assembled from the card's facts by one function, so the visible card and the announced card cannot drift |

---

## The drift the sources contain, and how it is resolved

| # | Drift | Sources | Resolution |
|---|---|---|---|
| 1 | Conflict indicator size: 8px vs 6px | `DESIGN.md:293` (8px), `DESIGN.md:310` (6px), ASSUM-13 (6px, RESOLVED) | **6px** — ASSUM-13 is locked |
| 2 | A visible confidence numeric | `DESIGN.md:308` (numeric beside the dots), `EXPERIENCE.md:210` (dots only) | **No visible numeric** — it is in the `aria-label` |
| 3 | Headline type role | `DESIGN.md:293` (`headline.md`), `EXPERIENCE.md:179` (`Text.Display.sm`) | **`type.scale.headline.md`** — DESIGN.md owns the type scale |
| 4 | The card's fill and border | `EXPERIENCE.md:179` (paper + ink.faint), `DESIGN.md:253` (elevated + border.subtle) | **elevated + border.subtle** |
| 5 | The confidence tooltip's surface | `EXPERIENCE.md:211` (paper.darker), `DESIGN.md:124` (elevated + shadow) | **elevated** — `DESIGN.md:111` forbids `paper.darker` as a static surface |
| 6 | The card's hover fill | `DESIGN.md:253` (`surface.subtle`), `EXPERIENCE.md:180` (paper.darker) | **`surface.subtle`** — the token layer; either satisfies "shift only" |
| 7 | The tag separator | `DESIGN.md:293` (middle dot), `EXPERIENCE.md:736` (comma) | **Comma**, so the announcement matches the visible reading |
| 8 | The `official_site` tooltip copy | `EXPERIENCE.md:116`, `EXPERIENCE.md:221` | **§4's** wording — ASSUM-9 locks the copy to §4 |
| 9 | The discovery stripe's label | `DESIGN.md:107` (every stripe needs a label), `DESIGN.md:297` (only a micro-tag) | The kicker says "Public event" **and** the `discovery` micro-tag is rendered |
| 10 | Which slot gets which slate | Two slate treatments, three slots, no mapping | `nearby` → public slate; `serendipity` → the 0.85 discovery slate |

---

## What the code review is expected to check

- **Does the card decide anything?** Any re-bucketing, re-sorting or re-computation is a
  D1 violation.
- **Is the explanation prop required, and does the card name it?** A defaulted prop is a
  D2 violation.
- **Does every stripe have a visible label?** A stripe alone is a WCAG 1.4.1 failure and a
  D4 violation.
- **Does the confidence tooltip recompute a factor?** It must not (D5).
- **Does any interactive element carry a stripe colour?** (D4)
- **Is there exactly one transition in the card's markup?** The architecture test fails
  on any Tailwind transition class (D13).
- **Is the tag separator real text, and is it a comma?** (D9)
- **Does the card hide a trust signal in any state?** (D14)
- **Is the 8-word headline rule enforced on the server, and is the client's half honest
  about it?** (D11)

---

## What the code review changed

The review approved the design and changed **two substantive things** and **confirmed one
that the implementation had to decide for itself**.

### 1. The tooltip triggers sit above the stretched link — a real bug, found by review

The design specified the stretched-link pattern and said, in the component's comment, that
"the tooltip triggers sit above it in the stacking order and stay clickable." **That was
not true of the implementation.** The link is `absolute inset-0 z-0` and comes *last* in
the DOM; the trust row's buttons were in the normal flow with no `z-index`. Both are
positioned elements with `z-index: auto`, so the later link painted **over** both
buttons — they were covered by an invisible `<a>` spanning the whole card, and clicking
the confidence dots navigated to the event instead of opening the tooltip.

**The fix**: the trust row is `relative z-10`, which puts it above the link's `z-0`; the
tooltips are `absolute z-10` inside that row. A test asserts the classes that produce
the stacking order, because jsdom computes no stacking and no layout.

**Why it survived the green suite**: the buttons were present, labelled, focusable and
reachable by every accessibility query, and jsdom does no hit-testing. Only a browser
would have shown it.

### 2. The indicator's name is visible, not screen-reader-only

The design had the Relevance / Event Fit name in an `sr-only` span. The review made it a
**visible** label with `aria-hidden="true"`.

The reasoning: the five dots are identical for both indicators, so the words are the only
thing keeping them apart (AD-10). An `sr-only` name means only a screen-reader user
learns which indicator they are looking at — and the whole risk AD-10 guards against is a
*sighted* user reading an Event Fit as a Relevance. The `aria-hidden` keeps the
`aria-label` as the single accessible name.

### 3. The confidence tooltip's content — decided at implementation, confirmed by review

The design did not specify what the confidence tooltip said, and the implementation had to
answer under AD-10's rule that an explanation is never generated at view time.

It says **"Surfaced because:"** followed by the **persisted Why-this Tags**. The card
cannot compute "Strong match on your top three interests" — that text was never persisted,
and generating it at render is exactly what AD-10 forbids. The tags *are* the persisted
contributing factors: the server chose them and stored them.

A side effect: the tooltip no longer restates the count, so the count appears in the
`aria-label` and nowhere else.

### 4. Confirmed, not changed

- **The conflict mark's shape.** The conflict dot and the confidence dots are both 6px
  circles, so a 6px amber circle among five 6px circles is not distinguishable. The
  design's alternatives were all worse: enlarging breaks ASSUM-13, reshaping breaks
  "filled circle", and amber was already its colour. `ring-1 ring-ink-faint` makes it
  distinct in shape, and `color.ink.faint` is the dimmest ink — not a chromatic one — so
  no colour reservation is broken.
- **The 44×44 hit area.** The visible dot stays 6px; the trigger is `min-h-11 min-w-11`.
  The dot is what the user sees; the hit area is what the finger needs.
- **Personal before slot.** A personal event fills Slot 1 when eligible, so a slot-first
  mapping would give every personal event the amber must-know stripe and the label
  "Must-know". The warm-personal tone is the tone of the *kind* (FR-19).
- **The comma separator** (drift #7) and the **no visible numeric** (drift #2) both
  stand as designed.

### The check the review could not make

The card has never been seen in a browser. The gate is jsdom, which has no layout, no
stacking order and no hit-testing. The stacking bug was found by reading CSS rules
against DOM order, and it was found *after* the tests were green — which is the class of
bug this suite structurally cannot catch. The `e2e-proof-and-contract-tests` item is
where the card should be confirmed in a real browser.
