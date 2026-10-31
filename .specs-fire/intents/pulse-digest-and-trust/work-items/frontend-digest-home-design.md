---
id: frontend-digest-home
title: The Pulse Digest home at /
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: completed
depends_on: [frontend-pulse-card, digest-read-api]
created: 2026-10-31
---

# Design: The Pulse Digest home at `/`

## The problem

`app/page.tsx` says "Your Pulse is being prepared." It has to become the Pulse Digest:
the page that shows the user the three things that matter today.

**The route decision is already correct and is not this item's work.** `lib/session.ts`
holds the rule as a pure function, and the page calls it. Anonymous → `/preview`;
onboarding unfinished → `/onboarding`; signed in and onboarded → here. And the **fourth
case is deliberately not a redirect**: when the API cannot be reached, the page says so.
Sending a signed-in user to the anonymous preview because one request failed would tell
them they are logged out when they are not. That structure is preserved exactly.

**The shell does not exist yet.** There is no sidenav, no bottom-tab nav and no authed
topbar in the codebase — only `BrandTopbar`, which is the *pre-auth* topbar. This item
builds the shell, because the digest home is the first authed surface and the shell is
what makes it an app rather than a page.

**The page performs no decisions.** Every fact it shows was decided by the composition
service and persisted. The page reads `GET /api/personal/digest` and renders what came
back: the cards in the server's order, the city the server resolved, the status the
server chose. It does not score, sort, re-bucket or compose.

---

## The two states the API distinguishes, and why the page cannot collapse them

`DigestOut.status` is one of three, and **all three answer 200**:

| `status` | What it means | What the page shows |
|---|---|---|
| `composed` | there are cards | the cards |
| `empty` | the digest was composed and there was nothing qualifying | §5's empty state — "Nothing on the pulse today." |
| `not_composed` | the digest has not been composed yet | a calm "being prepared" state |

**`not_composed` is not `empty`, and the difference is the whole point.** The empty
state's copy — "No qualifying events in {city}." — is a **claim about the world**: it
says there is nothing for you. If the digest has not been composed, the page does not
know that; it knows only that it has not been asked yet. Showing "your week is quiet"
before the question has been answered would be a lie, and a lie the user cannot detect.

So the not-composed state says what is true: the digest is being prepared.

---

## The header

The mockup (`pulse-digest-desktop.html`) draws it, and §3's microcopy contract locks the
words:

```
Thursday · Aug 27, 2026 · Brooklyn, NY     ← the Indicator.Today dot, then weekday · date · city
Today, three things matter.                 ← the h1
Your morning brief, kept short on purpose.  ← the lede
Open one, save one, or close the app and let it go.
```

**The mobile mockup's inverted "Three things matter today." is drift** and does not
govern — §3's contract gives the exact string, and the desktop mockup agrees with it.

**The `Indicator.Today` dot** is the first sanctioned terracotta use: a single 6px
`radius.full` dot in `color.accent.terracotta` with the sanctioned glow
(`--glow-today`, `box-shadow: 0 0 12px rgba(255,106,71,0.55)`), placed inline next to
today's date label. Not a background fill, not a bar.

**The date line is the server's.** `DigestOut.local_date` is the user's local day and
`DigestOut.timezone` is the zone the digest row was composed in. The eyebrow reads the
**weekday and date from `local_date`**, in that zone, and the **city from `city`**. The
page does not compute "today" from the browser clock — the server already decided which
day this is, and a browser in another zone computing its own "today" would disagree
with the digest it is about to render.

**The h1 says "three"**, and the digest has three cards. That is a contract the page
keeps by not padding: the 3-card discipline (below).

---

## The cards, in the server's order

The page renders `digest.cards` **in the array's order**, one `PulseCard` each, with
`explanation={{ kind: "relevance", value: card.bucket }}`.

**`card.bucket` is the persisted bucket, not a score.** The API sends the bucket on
purpose — FR-22's raw `relevance_score` is an internal number, and sending it would
invite the frontend to re-bucket it, which is the "recomputed at render" failure wearing
a different hat. The page maps the bucket straight onto the card's five-dot indicator
and re-buckets nothing.

**The digest card is always a Relevance Pulse.** `/` is the signed-in home, and the
per-user digest is the Relevance Pulse (AD-10). The Event Fit belongs to the
session-free preview. The page therefore always says `kind: "relevance"` — and the card
names itself "Relevance" on screen, which is the words keeping the two indicators apart.

**The tags are the server's tags, in the server's order.** The card caps them at three
(`MAX_WHY_THIS_TAGS`) — that cap is `EXPERIENCE.md`'s, and it is a *display* rule, not a
reordering. The page does not re-sort.

### The 3-card discipline

The digest shows **three** cards. No infinite scroll, no carousel, no "show more", no
reordering by engagement.

**ASSUM-5 (adaptive expansion to 5 or 7) is OPEN** — "Decision deadline: before
adaptive-expansion ships." Adaptive expansion is therefore **out of scope**, and
critically: **no affordance may hint at it.** A "Show all 5" link, a scroll sentinel or a
carousel control would ship a Phase 3 feature's promise while the feature is
undecided. The page renders exactly what the API returned and nothing that suggests
there could be more.

---

## The empty state

`EXPERIENCE.md` §5 marks this canonical, and it is stricter than both `DESIGN.md` and
the as-built mockup.

**Copy:** "Nothing on the pulse today. The calendar is yours."

**Visual:** a **single `Card.PulseDigest` variant** (no second card), whose body shows
the headline in `Text.Display.sm`. Below the card, a single `Text.Meta` line reading
**"No qualifying events in {city}."** — the city is the server's `city`, and the API
carries `city_source` precisely so the client does not have to guess whether it is the
user's city or the server's fallback.

**One low-weight "Suggest an event" link** in `Text.Meta`, present but not prominent.

**No CTA. No carousel. No upsell of any kind.** The mockup
(`pulse-digest-empty-state-desktop.html`) ships a **terracotta primary "Suggest an
event" button, a ghost "Browse all sources" button, and a "Suggested sources for you"
panel**. All three are violations:

| The mockup | The spine | Why |
|---|---|---|
| terracotta primary "Suggest an event" | a `Text.Meta` link | §5: "A small 'Suggest an event' link in `Text.Meta` ink color, low visual weight"; and terracotta is rationed to four uses, none of which is this |
| ghost "Browse all sources" button | nothing | §5: "No CTA. No carousel. No 'Explore trending events' upsell. No upsell at all." |
| "Suggested sources for you" panel | nothing | it is an upsell, and the mockup's own copy calls it "a way to add a source" — a CTA in disguise |
| "No pulse today." / "Your week is quiet. We don't pad it." / "Nothing qualifying today." | "Nothing on the pulse today. The calendar is yours." | §5 locks the copy |

**"The calendar is yours" is the strongest sentence in the product.** A user opening
Pulse to nothing should feel the absence of the product's noise, not be marketed at. A
terracotta button in that moment would be the marketing.

**The "Suggest an event" link points at `/suggest`** (PRD FR-8). That route does not
exist yet. It is a **real link with `href="/suggest"`**, not a disabled button — a
disabled link would be a promise the product cannot keep, and a `<button>` that does
nothing would be worse. The link is honest about where it goes; the route's absence is
a separate work item.

---

## The loading state

**Three paper skeleton rectangles. No text inside them. No spinner anywhere** — "a
spinner is a visual urgency badge" (PRD §13.1).

**The pulse.** §5's Loading Patterns: "3 paper rectangles rendered in
`color.surface.paper`, fading 1px toward `color.ink.faint` at 60% opacity, then back.
Pulse period: 1800ms."

**This is a real conflict with an existing locked test, and it is resolved here.**

`styles/motion.test.ts` asserts that **no stylesheet contains any `animation` or
`@keyframes`**, because `motion.fadeIn` — a 240ms opacity *transition* — is the product's
only motion. The pulse the spec describes is an **animation**, not a transition: a
repeating 1800ms cycle cannot be expressed as a transition.

The resolution is **not** to weaken the test, and **not** to drop the pulse:

- The pulse is a **loading affordance**, and it is **exactly one** animation in the
  product — the same thing `motion.fadeIn` is. DESIGN.md's token contract names
  `motion.fadeIn` as *the* motion, and the reduced-motion rule ("All entrance
  animations collapse to instant render") requires the pulse to collapse too.
- So the pulse is added as a **named, declared, single animation** in `globals.css`:
  one `@keyframes`, one `animation:` declaration, and it collapses to `none` under
  `prefers-reduced-motion`.
- `styles/motion.test.ts` is **updated to allow exactly that one animation** and to
  fail on any *other*. The test's intent — "the product has one transition and no
  animation" — becomes "the product has one transition and one loading pulse, and
  nothing else". The test still does its job: a second animation still fails the build.

**Why the skeleton is `color.surface.paper` and not `surface.elevated`.** §5 says paper.
The existing preview skeleton uses `bg-surface-elevated` with `bg-surface-inset` bars —
that is a *different* vocabulary (a card-shaped placeholder with internal structure),
and this item's spec says three plain paper rectangles. The digest skeleton's shapes
come from §5, not from the preview's.

---

## The error state

**Copy:** "Couldn't reach Pulse. Try again."

**One retry button**, a `Button.Primary` (terracotta fill, `color.surface.paper` text).
The retry button uses `Button.Primary` because it is a *decision moment* — the user is
being asked to do something about a failure — and terracotta's second sanctioned use is
exactly that.

**On the second consecutive failure the label becomes "Refresh page."** This is §5's
"Generic error" pattern verbatim. It is a **stateful** rule, so it needs state: the page
tracks how many consecutive failures it has seen, and the second one changes the label.

The first failure's button **retries the digest read** — the same request, without
changing the URL. The second failure's "Refresh page." **reloads the document**, because
by then the failure is probably not in the one request.

**The error state is not a redirect.** The existing `HomeUnavailable` — the
*session* being unreadable — keeps its own calm copy ("Your events are safe. This is on
our side.") and its "Try again →" link. The digest *read* failing is a different
failure: the session is fine, the digest request did not come back. The two are
separate states and the page distinguishes them.

**No stack trace. No emoji.**

---

## The live region

`role="status" aria-live="polite" aria-atomic="true"`, announcing **"Pulse Digest
ready, 3 events for today."** when the three cards finish loading and render (§7 Live
Regions).

The mockup has "Pulse Digest ready. 3 events for today." — **a full stop instead of a
comma**. The spec's §7 string uses a comma; the work item quotes the comma form. The
comma is used, and the difference is recorded because the live region is *spoken* and a
full stop changes the sentence boundary a screen reader hears.

The live region is **visually hidden** and lives with the cards. It announces once, when
the cards are in the DOM — not on the server, where it would be read before the cards
exist, and not repeatedly.

**ASSUM-8 (live-region queueing and debounce) is OPEN.** It concerns rapid-fire
save/dismiss sequences, which this page does not have. The one announcement this page
makes is a single discrete event, so the queue does not apply. Recorded, not implemented.

---

## The shell

### The sidenav (desktop `md+`)

`Component.Sidenav.App`, in its **locked six-route order**: **Digest / Timeline / Add /
Browse / Conflicts / Settings**. Six, not five — the six-route variant is canonical
"going forward" on every authed surface, and the five-route variant survives only in
the onboarding batch.

**The active item is `color.ink.primary` on a `color.surface.subtle` pill with a 1px
`color.border.subtle` stroke — never a terracotta fill.** The spec is explicit and
repeats itself in both documents: "Never terracotta fill on the active route", and
"terracotta on a small-control toggle burns the accent on a control used many times per
day." The pill mirrors the `Control.Segmented` ink-inversion pattern in miniature.

**The topbar is brand-only** (ASSUM-11, the topbar-quiet rule): the brand mark and
optionally the tagline, nothing else. The sidenav is the nav; the topbar is identity.

**The footer is pinned bottom** (`margin-top: auto`) and carries two affordances:
**Search** (a button, `aria-label="Search events"`) and the **account row** (the user's
name + "Account" subtitle, routing to `/settings`).

**The link reset is already in place.** `styles/globals.css` carries
`a { color: inherit; text-decoration: none; }` — the 2026-09-06 migration bug the spec
warns about. The audit is done and recorded here rather than assumed.

### The inert routes

**Four of the six routes do not exist yet**: `/timeline`, `/add`, `/browse`,
`/conflicts`, `/settings` — only `/` exists. The spec does not say what an inert route
should do, so this design decides and records it:

**An inert route renders as a non-interactive row, not a link.** It is a `<span>` with
`aria-disabled="true"` and the label **"Coming soon"** in `Text.Meta` `color.ink.muted`,
rather than an `<a>` that navigates to a 404.

The reasons:

1. **A link to a 404 is a lie.** The sidenav would be promising a destination that does
   not exist, and the user would find out by hitting an error page.
2. **`aria-disabled` on an `<a>` does not disable it.** An anchor with
   `aria-disabled="true"` is still focusable and still navigates — the attribute is a
   hint, not a mechanism. Using a `<span>` is the honest mechanism: there is nothing to
   activate.
3. **The route list must not shrink.** The six-route order is locked; a sidenav with
   two items would be a different component.

The **Digest** item is the only live route, and it carries `aria-current="page"`. The
**Add** item is special: the spec says the Add slot opens the creation surface in
place rather than routing. The `AddEventButton` component already exists and already
mounts that panel — so the sidenav's Add item mounts it too, rather than becoming an
inert row.

### The bottom-tab nav (mobile `sm`)

**Five slots: Digest / Timeline / Add / Conflicts / Settings.** Browse is the sixth
route and lives behind the **"More"** overflow affordance on the trailing edge, per
`Component.BottomTab.MoreMenu`.

**The active slot is ink-inverted** (`color.ink.primary` fill + `color.ink.inverse`
label) with a **2px terracotta underline bar** above it — never a full-bar terracotta
fill.

### The glyphs

The spec wants **16×16 stroke-only SVGs, never filled chromatic**. There is no icon
library in this codebase and the stack is "UI system: None", so the glyphs are
**hand-drawn inline SVG paths** — five stroke paths for the sidenav/bottom-tab, one
compass for Browse, one magnifier for Search. Each is `stroke="currentColor"`,
`fill="none"`, `stroke-width="1.6"`.

**The Add glyph is a `+`** and the Browse glyph is a **compass**, both named by the
spec. The rest are not named, so the design picks and records them: Digest = a pulse
wave, Timeline = a week grid, Conflicts = two overlapping arcs, Settings = a slider.

---

## The layout

| Breakpoint | Width | This page |
|---|---|---|
| `sm` | ≤767px | **single column**, bottom-tab nav, `spacing.4` card spacing |
| `md` | 768–1023px | sidenav (220px), single column, two-column on landscape |
| `lg` | 1024–1179px | sidenav (240px), **two columns**: the digest left, the side rail right |
| `xl` | ≥1180px | content constrained to **1180px**, whitespace expands outward, **no reflow** |

**Desktop adds whitespace and hover affordances — never features, screens, actions or
copy** (§10). The desktop layout is the mobile layout with more room, not a different
page.

**The side rail.** At `lg+` there is a right-hand rail. The mockup's carries "Saved this
week" and a **Pro upsell card**.

- **The Pro card does not ship.** There is no `SUBSCRIPTION` model, every user is Free,
  and the upsell would be an upsell of a product that does not exist.
- **"Saved this week" ships only if it reads already-built saved-event data without new
  backend work.** There *is* a saved-events surface in the codebase
  (`components/saved-events-section.tsx`), and the work item's condition is that it
  reads data that already exists. **This item does not build the rail.** The saved
  events live on the digest's own page (the placeholder hosts them today), and
  assembling a "this week" rail is a *new read* — a different endpoint, a different
  time window, a different query. The work item's condition ("without new backend
  work") is therefore **not met**, and the rail is deferred rather than half-built.

So at `lg+` the two-column grid has the digest on the left and an **empty right rail
slot** — which is worse than no rail. **The design instead renders the digest in a
single column at every width**, constrained to `--layout-container-max` (1180px) at
`xl`. The two-column layout arrives with the rail that earns it.

**This is a deliberate deviation from §10's "two-column digest: today's pulse on the
left, 'this week' preview on the right"**, and it is recorded as one: the spec's
two-column layout is defined *in terms of the side rail*, and the side rail's contents
are (a) a Pro card that cannot ship and (b) a saved-events rail that needs a backend
read this item does not do. A two-column layout with an empty column is not the spec's
layout; it is a layout with a hole in it.

---

## The data seam

The page reads the digest **on the server**, through the generated client
(`@/lib/backend-client`) — AD-19: the frontend reaches the backend only through the
generated `api` client. The read carries `sessionHeaders()`, because a server-side read
without the visitor's cookies is anonymous, and a signed-in user's home showing them no
digest would be exactly the bug `lib/session.ts` documents.

**The read is a server component's read.** The page is `force-dynamic` (it already is),
and the digest is fetched during the render. That is right for a *personal* page: it
cannot be cached at the edge, and it must not be baked into a build.

**Three outcomes, and the page renders a different thing for each:**

| Outcome | What the page shows |
|---|---|
| the read throws or returns a non-2xx | the **error** state (§5's generic error) |
| the read returns `not_composed` | the **being prepared** state |
| the read returns `empty` | the **empty** state |
| the read returns `composed` | the **cards** |

**The read is a separate module**, `lib/digest-read.ts`, so the page's decision logic is
a pure function over the result and can be tested directly — the same pattern
`lib/session.ts` uses for the route rule.

---

## The file layout

| File | What it is |
|---|---|
| `app/page.tsx` | the page: the route decision, the read, and the four states |
| `lib/digest-read.ts` | the server-side read of `GET /api/personal/digest`, typed |
| `components/digest/digest-header.tsx` | the eyebrow, the h1 and the lede |
| `components/digest/digest-empty.tsx` | §5's empty state |
| `components/digest/digest-preparing.tsx` | the not-composed state |
| `components/digest/digest-skeleton.tsx` | the three paper skeletons and the pulse |
| `components/digest/digest-error.tsx` | the error state and the retry button |
| `components/shell/app-shell.tsx` | the sidenav + topbar + main frame |
| `components/shell/sidenav.tsx` | the six-route rail and its footer |
| `components/shell/bottom-tab-nav.tsx` | the five-slot bar and the More affordance |
| `components/shell/more-menu.tsx` | the overflow sheet, where Browse lives |
| `components/shell/nav-glyphs.tsx` | the hand-drawn stroke-only SVGs |
| `lib/digest-attempt.ts` | the server-owned count of consecutive digest failures |

---

## The decisions

| # | Decision | Why |
|---|---|---|
| D1 | The route decision in `lib/session.ts` is **not touched** | it is already a pure function and already correct; the fourth case's "not a redirect" is load-bearing |
| D2 | The page reads the digest **on the server**, through the generated client, with `sessionHeaders()` | AD-19; and a server read without the cookies is anonymous |
| D3 | The read lives in `lib/digest-read.ts`, not in the page | the page's decision becomes a pure function over a typed result, testable directly |
| D4 | `not_composed` gets **its own state**, not the empty state | the empty state claims "no qualifying events"; that claim is not yet true |
| D5 | The empty state is **§5's copy exactly**, with one `Text.Meta` link and nothing else | §5 is canonical and stricter than the mockup; the terracotta primary and the sources panel are violations |
| D6 | "Suggest an event" is a **real link to `/suggest`**, not a disabled button | a disabled control promises a destination that does not exist; the route is a separate item |
| D7 | The skeleton is **three plain paper rectangles**, not the preview's card-shaped one | §5's Loading Patterns is the digest's own vocabulary |
| D8 | The pulse is added as **one named animation**, and `styles/motion.test.ts` is updated to allow exactly it | the spec requires the pulse; the test's intent ("one motion") survives as "one transition and one loading pulse" |
| D9 | The error's retry **retries the read**; "Refresh page." **reloads the document** | §5's generic error; the second failure is probably not in the one request |
| D10 | The error state is **separate** from `HomeUnavailable` | the session being unreadable and the digest read failing are different failures |
| D11 | The live region is **visually hidden** and announces once, with the comma form | §7; it must not be read before the cards exist |
| D12 | The sidenav is the **six-route** variant | canonical on every authed surface; the five-route variant is onboarding-only |
| D13 | The active sidenav item is an **ink pill**, never terracotta | both documents say so, twice |
| D14 | An **inert route is a `<span aria-disabled>`, not an `<a>`** | an anchor with `aria-disabled` still navigates; a link to a 404 is a lie |
| D15 | The sidenav's **Add** item mounts the existing `AddEventButton` | the spec says Add opens the creation surface in place rather than routing |
| D16 | The bottom-tab is **five slots + a More affordance** for Browse | §4 `Component.BottomTab.MoreMenu` |
| D17 | The glyphs are **hand-drawn inline SVGs** | "UI system: None"; no icon library exists and none is being added |
| D18 | The layout is **one column at every width** until the side rail has content to justify it | the spec's two-column layout is defined in terms of the side rail, and the rail cannot ship |
| D19 | **The Pro card does not ship**, and the saved rail is deferred | no `SUBSCRIPTION` exists; and the saved rail needs a backend read this item does not do |
| D20 | **Pull-to-refresh is not implemented** | it is a browser-native behaviour that needs no work, and "if it ships, it must not auto-poll" — nothing here polls |
| D21 | **Offline is out of scope** | there is no service worker in this codebase, and building one is a different item; the spec's offline path is a whole surface, not a banner |

---

## The drift the sources contain, and how it is resolved

| # | Drift | Sources | Resolution |
|---|---|---|---|
| 1 | The h1's wording | the mobile mockup inverts it ("Three things matter today."); §3 and the desktop mockup agree | **"Today, three things matter."** |
| 2 | The empty state's copy | the mockup says "No pulse today." / "Nothing qualifying today."; §5 says "Nothing on the pulse today. The calendar is yours." | **§5** — it is marked canonical |
| 3 | The empty state's affordances | the mockup ships a terracotta primary + a ghost button + a sources panel; §5 says no CTA, no upsell | **§5** — one `Text.Meta` link |
| 4 | The live region's punctuation | the mockup says "ready."; §7 and the work item say "ready," | **the comma** — it changes what a screen reader hears |
| 5 | The skeleton period | §5 says 1800ms; the existing preview skeleton has no pulse at all | **1800ms**, as a declared animation |
| 6 | The skeleton's shape | §5 says "3 paper rectangles"; the preview's is a card-shaped frame with bars | **§5** — three plain rectangles |
| 7 | The confidence's visible numeric | `DESIGN.md:308` renders the count; `EXPERIENCE.md:210` says dots only | **no visible numeric** — the card item already settled this |
| 8 | The two-column layout | §10 says two columns at `lg+`; the side rail's contents cannot ship | **one column**, recorded |
| 9 | The side rail's contents | the mockup has a Pro card and "Saved this week" | **neither ships** — no `SUBSCRIPTION`, and the saved rail needs a new read |
| 10 | The card count | ASSUM-5 is OPEN (5 at MVP, 7 later); §4's adaptive expansion | **three**, and no affordance hints at more |
| 11 | The error's retry semantics | §5 says the label changes; it does not say what the first button does | **retry the read**; the second reloads the document |
| 12 | The `not_composed` copy | §5 has no "being prepared" state for the digest; the API's `status` demands one | **the page writes it** — and it claims nothing about the world |

---

## What the code review is expected to check

- **Does the page decide anything?** Any sorting, scoring, re-bucketing or filtering of
  the cards is a D-something violation. The page must render `digest.cards` as they
  came.
- **Is `not_composed` distinguishable from `empty`?** Both are "no cards", and a
  collapsed pair would be a lie about the world.
- **Does the empty state contain any CTA?** A button, a link that is not "Suggest an
  event", or a panel is a violation. The terracotta primary is the specific violation
  the mockup makes.
- **Does the skeleton's pulse respect `prefers-reduced-motion`?** And is it the *only*
  animation in the product?
- **Is the retry label "Refresh page." on the second consecutive failure?**
- **Does the live region announce exactly once, with the comma form?**
- **Does the sidenav have exactly six items in the locked order?** Is the active item an
  ink pill rather than terracotta?
- **Do the inert routes navigate?** An `<a>` with `aria-disabled="true"` still
  navigates, and that is the bug to look for.
- **Does the shell add a terracotta fill anywhere?** The active route, the active
  bottom-tab slot and the More affordance are the three places it could creep in.
- **Is the topbar brand-only?** Any nav link or action button in it is an inversion.
- **Is the page still `force-dynamic`?** A build-time read of a personal page is a leak.

---

## What the code review changed

The review found **four defects**, and each one is recorded here because the design is
the thing the next item inherits.

### 1. The "Refresh page." label could never appear

**The design said** "the page tracks how many consecutive failures it has seen, and the
second one changes the label" — but it did not say *where* that count lives, and the
implementation put the parsing in `digest-error.tsx` and never connected it to anything.
The page hardcoded `attempt={0}`.

**The count now lives in `lib/digest-attempt.ts`**, in a cookie the server owns, because
the retry is a navigation and a client-side counter cannot survive one. The cookie is
written only on a failure and cleared on a success, because the rule says *consecutive*.

**The subtlety, and the reason it is written down.** `recordFailure()` returns the
number of **prior** failures, not the new total. The component's rule is `attempt >= 1`,
so the first failure must pass 0 and the second 1. Returning the new total would make
the *first* failure render the *second* failure's label — which is what the first
version of the fix did, and what the new tests caught.

### 2. The More slot was a dead control

**The design said** the More slot "opens the overflow sheet", and the bottom-tab's
docstring said the same. **No sheet existed** — the slot rendered the inert
`TabSlot` branch, a `<div>` that does nothing.

**`components/shell/more-menu.tsx` is the sheet now.** It uses the same `Sheet` primitive
as the create sheet, so it sits in the top layer above the bottom bar.

**The sheet's one row is Browse, and Browse is inert** — a `<span aria-disabled>` with a
"Coming soon" note. A control that opens a sheet is not the same as a route that
exists, and the distinction is the point: the sheet works, and it says honestly that its
destination is not built.

### 3. The content was not constrained at `xl`

**The design's layout table** says `xl` is "content constrained to **1180px**, whitespace
expands outward, **no reflow**". **The `<main>` had no max-width at all**, so the cards
would stretch to the width of the content column on a wide display.

**`max-w-(--layout-container-max) mx-auto` on the `<main>`.** §10's rule is "Desktop
adds whitespace — never features, screens, actions or copy", and a card stretched to
2300px is a different screen from a card at 720px.

**This one was missed because D18 was about the *columns*.** A design's tables have many
rows, and a decision is usually about one of them.

### 4. The shell's docstring described a client component that was not one

`app-shell.tsx` said "This wrapper is a client component so those children may be". It
has no `"use client"` and needs none — the sidenav and the bottom-tab are client
components in their own right, and the content the shell wraps is a server component's
children.

**A docstring that lies about the architecture is worse than no docstring**: the next
reader would add `"use client"` to "fix" it, which would pull the whole page across the
client boundary — including the digest, which is read on the server.

### A fifth, smaller correction

**The create sheet was mounted inside the route list.** `AddEventButton` renders both
the button and the panel, so the sidenav's `<li>` contained a form — and the panel's
"Name" field was a descendant of the navigation list. `AddEventButton` gained
`withoutPanel` and `onOpen`, and both nav components now mount `<PersonalEventsPanel>`
outside their list.

**And the compact button's mark.** The sidenav and the bottom-tab draw the 16×16
stroke-only `+` themselves; a compact button that also rendered a literal `+` put two
plus signs in one row. The compact button now renders no ink of its own.

### What the review added to the file list

| File | Why |
|---|---|
| `components/shell/more-menu.tsx` | the overflow sheet (defect 2) |
| `lib/digest-attempt.ts` | the consecutive-failure count (defect 1) |
| `frontend/tests/cookie-store.ts` | a real cookie store, so the tests assert on the cookie's value rather than on a method call |
