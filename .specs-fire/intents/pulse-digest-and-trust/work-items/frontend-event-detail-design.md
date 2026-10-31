---
id: frontend-event-detail
title: The Detail Screen component
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: in_progress
depends_on: [frontend-pulse-card, event-detail-api]
created: 2026-10-31
---

# Design: The Detail Screen at `/events/:id`

## The problem

The Detail API exists and it answers two audiences correctly: a signed-in caller gets
the public facts, their own persisted why-this breakdown, their saved state and the
k-anonymous neighbor bucket; an anonymous caller gets the public facts and nothing
personal. Nothing renders either answer.

And the surface is not a page with a component in it. It is the surface where **AD-10's
durability rule becomes visible**, and the difference between a good implementation and a
plausible-looking one is entirely in what it refuses to show:

| Situation | A wrong screen shows | The right screen shows |
|---|---|---|
| The user was never shown this event | *some* explanation | **nothing** — no section at all |
| The user was shown it on another day | today's reasoning | **that day's** reasoning |
| Anonymous visitor | the Event Fit's tags | **nothing personal** |
| Fewer than 5 neighbors | "0 neighbors" | **silence** |

Every one of those four rows is a lie the API already prevents the server from making.
The screen's job is to not put the lie back.

The spec is unusually complete — `EXPERIENCE.md` §12 and PRD §14.3 agree on a locked
element order — and the mockups disagree with it in **nine** places. Each is resolved
below and each resolution is recorded, because a resolution nobody can find is a
resolution nobody can keep.

---

## The decisions

### D1 — The route is a **server** page, and the read is server-side

`app/events/[id]/page.tsx` is a server component. The read goes through
`lib/event-detail-read.ts`, which calls `GET /api/events/{event_id}` with
`sessionHeaders()` — the same reason `lib/digest-read.ts` does it: the Next.js server is
a separate HTTP client with no session of its own, so a server-side read without the
forwarded cookies is **anonymous**, and a signed-in user's own Detail Screen telling
them they have no explanation would be the exact failure this surface cannot have.

The page is `force-dynamic`. The Detail Screen shows a *per-user* payload, and neither
the payload nor the 404 can be baked into a build.

**The read has four answers, not two.**

```ts
type DetailRead =
  | { kind: "found"; detail: EventDetailOut }
  | { kind: "anonymous"; detail: EventDetailOut }   // same payload, personal === null
  | { kind: "removed" }                              // 404: not public, superseded, or started
  | { kind: "unavailable" };                         // a failure to answer
```

`anonymous` is **not** a separate data shape — it is the same payload with
`personal: null`, and the API says so. But the screen *behaves* differently for the two
(a signed-in user has a Save button; an anonymous visitor does not), so the read says
which one it was. The `found`/`anonymous` split is derived from `personal === null`, and
**never from the session** — the API is the authority on whether it found a personal
payload, and the screen must not decide that by looking at its own session cookie.

`removed` and `unavailable` are **different failures** and they render different copy:
an event that has started or been withdrawn is a fact about the world ("This event is no
longer available."), while an unreachable API is a fact about us ("Couldn't load this
event."). Folding them together would either lie about the event or lie about our
infrastructure. The API answers 404 for the first, and the read catches the rest.

### D2 — The element order is the locked order, and it is asserted, not eyeballed

`EXPERIENCE.md` §12 and PRD §14.3 agree:

> Source Badge → Confidence Pulse → event name → When · Where → **the same 3 Why-this
> Tags as the card** → Description (2–3 lines max) → Reminder Picker → Save · Share ·
> Dismiss → **Why-this breakdown (expandable)** → Similar events → Neighbor count.

The order is a **trust argument**, not a layout preference: the badge and the confidence
pulse come before the name because "where did this come from" is the first question a
sceptical user has, and the breakdown comes *after* the actions because it is the
elaboration of the tags that are already above it.

**The order is a test, not a comment.** A test collects the DOM's landmark-ish elements
in document order — the badge trigger, the confidence trigger, the `h1`, the meta line,
the tags, the description, the action row, the breakdown, the neighbor line — and
asserts the sequence matches. A test that only asserted "all of these exist" would pass
on a screen that put the breakdown above the title.

**The items that do not ship are *absent*, not empty** (D7). The order therefore has
gaps, and the gaps are the point: there is no Reviews row, no Similar Events row, no
"Report this event" link.

### D3 — The Why-this Tags are read from the same persisted composition, and the equality is asserted

FR-21's third testable consequence: *"Why-this Tags are consistent on the Pulse Card and
on the Detail Screen."* The word that matters is **consistent**, and the strongest form
of it is **equal**.

Both surfaces read the same `DigestComposition` row — the card through `DigestCardOut`,
the Detail Screen through `WhyThisOut` — and both render `tagLabel(key)` from
`lib/digest-labels.ts`. So the two surfaces render the *same words* for the *same
persisted keys*, because there is exactly one translation table.

**The test asserts equality, not similarity.** A test renders a `PulseCard` and the Detail
Screen with the **same** persisted tag keys and asserts the two rendered tag strings are
identical — same labels, same order. The order matters: the tags are a priority order
(`RANKING_TAG_ORDER`), and re-sorting them on one surface is a client-side decision
(AD-10) even when the *set* is the same.

**The Detail Screen's tags come from `why_this.tags`, and from nowhere else.** Not from
the card's payload (the Detail Screen is reachable for an event that is not in today's
digest), and not from a recomputation. When `why_this` is `null`, there are no tags —
and there is no breakdown, and no confidence pulse either (D4).

### D3b — The Source Badge is the **persisted** one, and its absence is the API's answer

`EventDetailFactsOut` carries **no `source_badge`**. The only badge anywhere in the
Detail Screen's payload is `why_this.source_badge` — the variant key the composition
persisted. The backend's own docstring says why:

> **The Source Badge is the variant key, or `None`.** A personal event has no source, so
> it has no badge; `None` here means "there is no source", not "unknown".

**So the badge appears when there is a composition, and not otherwise** — including for
an anonymous visitor, who has no composition and therefore no badge.

**This is a deviation from `EXPERIENCE.md` §12's locked order**, which puts the Source
Badge first for every reader, and it is recorded rather than papered over. The
alternative — resolving the badge fresh from the catalog's `Source.type` — is exactly
the recomputation AD-10 forbids: a badge computed at view time is a fact the client
invented, and the badge's whole meaning is *"we verified this source"*. FR-23's
trust signal is the **persisted** one, the same one the card showed.

**The gap is real and it is the API's to close, not this screen's.** The catalog's own
`PublicEvent` carries a resolved `source_badge` (`catalog_read.source_badge_for_type`),
so the backend *can* say it — `EventDetailFactsOut` simply does not ask for it. Widening
it is a one-field change to `PublicEventDetail` and `EventDetailFactsOut`, and it
belongs to the `event-detail-api` item rather than to this one. **Until it is widened,
the badge is absent for a reader with no composition, and this screen does not
substitute one.**

### D4 — **No composition, no breakdown, and no confidence pulse**

This is the work item's sharpest criterion:

> An event the user was never shown renders the public facts and **no explanation section
> at all** — not an empty one, not a placeholder, not an Event Fit standing in for it.

**The absence is a shape on the wire.** `DetailPersonalOut.why_this` is `null` when no
composition exists, and `null` means *"we have nothing for you on this event"* — which is
different from *"we looked and the answer was nothing"*. The API already distinguishes
them. The screen renders the distinction.

So:

| The screen shows | when |
|---|---|
| the breakdown section | `why_this !== null` |
| the Why-this Tags | `why_this !== null` |
| the Confidence Pulse | `why_this !== null` |
| the "Saved" state | `personal !== null` (it is the user's own save row, not a tag) |
| the neighbor line | `personal !== null && neighbor_bucket !== null` |

**The confidence pulse is part of the explanation, so it disappears with it.** The
pulse's value is `why_this.bucket` — the persisted Relevance Pulse bucket for that
composition. There is no other source for it on this screen: the Event Fit's bucket
belongs to the anonymous preview (AD-12), and substituting it here is exactly the
"company-ending" fallback the API's own design refuses. So an anonymous visitor, and a
signed-in user who was never shown this event, see **no five-dot indicator at all**.

**The test asserts the section's absence.** Not "the section is empty" — the section
element is **not in the DOM**. A test that checked `textContent === ""` would pass on a
screen that rendered an empty `<section aria-labelledby="why">` with a heading, which is
the placeholder the criterion forbids.

### D5 — The breakdown renders **one factor per line**, derived from the persisted tags

`EXPERIENCE.md` §12 gives the shape:

> "Surfaced because:
> - Comedy is in your top 3 categories.
> - 2 km from your work.
> - 12 of your neighbors saved this.
> - Source reliability 0.92."

Each factor on its own line, each may carry a tooltip, and the expansion uses
`motion.fadeIn` (240ms), disabled under reduced motion.

**The factors are derived from the persisted tags — and nothing else.** The tags are
the persisted *keys*; the breakdown is their human-readable form. This is the one place
in the screen where prose is generated, and it is generated from a **persisted fact**, not
from a fresh computation — which is what keeps AD-10 intact. A factor that required a
number we never computed would be a lie, and the work item names the mockup's exact
sin:

> *"Source reliability 0.91 (Bayesian-smoothed)"* and *"It's four blocks from your
> office"* — neither of which exists: FR-16 is unbuilt and there are no coordinates.

**So the factor vocabulary is closed, and it is the tag vocabulary.** Each persisted tag
key maps to one line of prose:

| Tag key | The line |
|---|---|
| `nearby` | It's in your city. |
| `tonight` | It starts tonight. |
| `tomorrow` | It starts tomorrow. |
| `weekend` | It starts this weekend. |
| `discovery` | It's outside your usual — a little discovery. |
| `saved` | You saved a similar event before. |
| `matches_<chip>` | It matches an interest you picked: *{chip label}*. |

And **nothing else is a factor**. No reliability score (FR-16 is unbuilt — `Source` has no
score field, and `shared/constants.py` says so in as many words). No distance (no
coordinates). No "12 of your neighbors" (the exact count never reaches the client — the
wire shape has a bucket key and no count field). No "Free" (there is no price field).

**The neighbor line is *not* a breakdown factor.** It is its own element at the bottom
of the screen (the locked order puts it last), and it is the **bucketed prose**, not a
number. Duplicating it inside the breakdown would put the same fact in two places and
give it two chances to drift.

**The tags are a closed set on the server, and the frontend's table mirrors it.** A tag
key the frontend does not know falls back to its slug, title-cased — the same rule
`lib/digest-labels.ts` already uses for the label. So a new server tag appears on the
card and in the breakdown without a frontend deploy, and the breakdown's fallback line
is the slug, not a fabricated reason. **A tag with no known prose renders the tag's own
label as its line** — the same fallback, so the breakdown never invents a reason.

### D6 — The neighbor count is bucketed prose, and the number is not in the DOM

FR-24: the count is bucketed, `≥5` is the threshold, below 5 is **silently suppressed**,
and **exact counts are never exposed**.

`EXPERIENCE.md` §12 gives the prose:

| Bucket key | The line |
|---|---|
| `few` | A few neighbors saved this. |
| `some` | Some neighbors saved this. |
| `many` | Many neighbors saved this. |
| `a_lot` | A lot of neighbors saved this. |
| `null` | *(nothing at all)* |

**The suppression is silence.** No row, no "0 neighbors", no "Not enough neighbors yet" —
and, critically, **no `neighbor_suppressed: true` field in the DOM**, because a field
that says "we computed a count and suppressed it" is itself a signal about how many
people are near this event. The API does not send one, and the client must not
manufacture one.

**The `👥` emoji prefix is dropped.** `EXPERIENCE.md` §12's `_RECONCILE_` note says so
explicitly ("Neighbor-count bucketing … was originally specified with `👥` emoji prefixes
per the prior draft. This was revised to prose-only `Text.Meta` labels to honor §3 Voice
and Tone ('Emoji as CTAs' ban)"). The PRD's `👥 5–9` is **drift** — it is the superseded
draft.

**The mockup's "12 neighbors tracking this in Brooklyn" is not reproduced.** It violates
FR-24's "exact counts are never exposed" outright, and it adds a city qualifier the
bucket has no data for.

**The test asserts the number is not in the DOM.** For every bucket, the rendered text
contains the prose and **no digits**. That is a stronger assertion than "the bucket key
is right": it fails if someone later adds `" (12)"` to the prose.

### D7 — What does not ship, and what "does not ship" means

Three things in the mockup and the PRD are absent from the payload. **Absent is a
different wire shape from empty**, and the difference is the point:

| Section | Why it is absent |
|---|---|
| **Similar events you've attended** | There is no attendance data anywhere in the codebase — no `Attendance` model, no past-visited tracking. A `similar_events: []` field would say "we looked and there are none", which is a lie for a user who has attended events the app does not know about. |
| **Reviews count** | ASSUM-6, deferred to Phase 3+ pending an engagement-trap design review. |
| **Community-corroboration count** | ASSUM-7, deferred, and "do not adopt without a Trust Review pass". |
| **"Report this event"** | FR-59's flow does not exist. There is no `EventReport` model, no endpoint, no rate limiter. A link to a flow that does not exist is a dead end. |

**So all four are absent from the DOM entirely** — not rendered as empty sections, not
rendered as "coming soon". The route's surface has no slot for them.

### D8 — The reminder picker is **display-only**, and the reason is named

FR-9's picker is a real feature with a real model (`ReminderPlan` exists), but **nothing
schedules sends** — the delivery intent has not built the scheduler, and FR-11's email
delivery is not wired. A chip that toggles and persists a plan would be a control that
appears to work and silently does nothing, which is worse than no control.

**So the picker is display-only and says so.** The four chips (5d / 2d / 1d / 1hr) render
as **non-interactive chips showing the default plan**, with the label:

> Reminders come by email the day before and the hour before.

which is FR-9's own default (1d + 1hr) and FR-9's own channel (email is the MVP channel;
ASSUM-3 says push is Phase 2).

**The chips are not `<button>`s.** They are `<span>`s, because a button that does nothing
is a broken control, and a screen reader announcing "5 days before, button" for
something unpressable is worse than silence. The test asserts the picker contains **no
button**.

**The selection is an ink inversion, never terracotta.** `EXPERIENCE.md` §4
`Input.ReminderSlot`: "no terracotta on this chip; selection is communicated by ink
inversion, not by accent".

### D9 — The Save / Share / Dismiss row is **three secondary buttons**, and two of them are honest

`EXPERIENCE.md` §12 item 8: "Save to Pulse · Share · Dismiss (3 buttons in
`Button.Secondary` weight)".

| Action | Ships? | Why |
|---|---|---|
| **Save to Pulse** | **yes** | `POST /api/personal/saved-events/{catalog_event_id}` exists and is idempotent. The Detail Screen already knows `personal.saved`, so the button's state is known before the user presses it. |
| **Share** | **yes, as a real share** | `navigator.share` when the browser has it, falling back to copying the canonical URL. The `canonical_url` is on the payload. A "Share" button that copies a link is a real feature. |
| **Dismiss** | **yes, but it does not signal "less like this"** | FR-25's dismissal is a *swipe* on the Pulse Card, and it "signals 'less like this' to the AI". There is **no dismissal endpoint** in the codebase. A Detail Screen button that claimed to dismiss would be a control with no backend. |

**So the third button is "Not for me", and it does something real and small: it
dismisses the event from *this user's digest*.** Hmm — there is no such endpoint either.

**The honest resolution: the third button does not ship either, and the row is two
buttons.** A row of two buttons with a gap is fine; the locked order says "three buttons"
because the mockup had three. **A dead button is not a button.** The row renders
**"Save to Pulse"** (primary, terracotta — one of the four sanctioned uses) and
**"Share"** (secondary). The dismissal gesture stays where FR-25 puts it: the **swipe on
the Pulse Card**, which the card already carries as a spec and which this item does not
implement.

**This is recorded as a deviation.** The alternative — shipping a "Dismiss" button that
POSTs to nothing — is the exact failure the work item warns about in D8's terms: "does
not ship a control that silently does nothing."

### D10 — Tooltips are one component, and they work on touch

`Tooltip.Source` and `Tooltip.Confidence` are specified:

- a `<button>` trigger with `aria-describedby` pointing at a **sibling**
  `role="tooltip"`;
- revealed on hover **and** `:focus-visible`;
- on touch below 768px, **opened on tap** and dismissed on outside-tap or `Esc`;
- **"No hover-only tooltips on touch."**

**The card already has the hover/focus behaviour**, and the detail screen reuses the
pattern rather than forking it — but the card's tooltip is **hover/focus only**, and
`:focus-within` on a touch device opens it on tap as a side effect of the tap focusing
the button. The Detail Screen's tooltips must also close on **outside-tap** and on
**`Esc`**, which the card's CSS-only tooltip cannot do.

So the Detail Screen gets a **small client component** — `components/detail/trigger-tip.tsx` —
that:

- renders the `<button>` trigger and the sibling `role="tooltip"`;
- opens on `mouseenter`/`focus` and on `click` (which is what a tap is);
- closes on `Esc` (a document-level keydown listener) and on an outside `pointerdown`;
- keeps the tooltip **in the DOM** at all times, so `aria-describedby` always resolves.

**"No hover-only tooltips on touch" is the test.** A test asserts that the tooltip's
content is present in the DOM regardless of hover state, and that the trigger is a
`<button>` with `aria-describedby` pointing at an element whose `role` is `tooltip` and
whose `id` matches. A test cannot simulate a real touch in jsdom, so the *mechanism*
is pinned: the trigger is a `<button>` (which is focusable and therefore reachable by
tap), and the tooltip is not `display: none` (which is what a CSS-hover-only tooltip
would have to be to be hidden).

**The card's tooltips are not changed.** The card's own tooltip is a CSS-only sibling and
it already satisfies §12's requirement for the card's context. Changing it here would
be a change to a completed work item, and the criterion is about *this* surface.

### D11 — Time is user-local, with venue-local beside it when they differ

Glossary §3 and AD-6: display-time conversion happens at the presentation edge.

The payload carries `start_time_utc` (an instant), `start_time_tz` (the event's IANA
zone) and `tz_review_pending`. So:

- **The primary time is the user's local time.** The user's zone comes from their
  `DigestPreference` — which the Detail Screen's payload does **not** carry. So the
  user's zone is read server-side from `GET /api/personal/digest-preference`… which is a
  second round trip on a screen that already has one.

**Better: the browser's own zone, on the client.** A Detail Screen is a *navigation*, so
it renders in a browser, and the browser knows the user's zone exactly —
`Intl.DateTimeFormat().resolvedOptions().timeZone`. No second round trip, and no
assumption that the user's saved preference matches the machine they are on.

**The format is exact and local-noon-based.** The time is read at a **local noon** of the
event's day in the target zone, so a UTC-offset difference can never move the displayed
*date* onto the neighbouring day. This is the same rule the Digest Header uses, and the
same reason.

**The venue's local time is shown when it differs.** The rule is a **comparison of the
two zones' wall-clock for the same instant** — not a comparison of the zone *names*.
`America/New_York` and `America/Toronto` are different zones that show the same clock
face, and a screen that said "6:30 PM EDT · 6:30 PM Toronto" would be noise. So the
venue time is shown when the **formatted wall-clock differs**, and the zone's short name
is shown beside it.

**The approximate marker.** When `tz_review_pending` is set, the time carries "Time
approximate" — the card's wording, reused, because a user who saw "6:30 PM" on the card
and "6:30 PM (approx.)" here has been told the same thing twice in two words.

### D12 — The sold-out state replaces the actions, and the error states are three

FR-53 and A-15: a sold-out event is marked "Sold Out" on the Detail Screen.
`EventDetailFactsOut.is_sold_out` carries it.

**Sold out replaces the Save and Reminder actions** with a single calm line:

> Sold out — tickets no longer available.

**A sold-out event is still saveable.** The work item's own text says "replaces the save
and reminder CTAs" — but FR-53's own rule is "a sold-out event is marked with a 'Sold
Out' tag", and a user who saved an event before it sold out still wants it on their
calendar. Hmm — but the criterion is explicit: *"Sold-out (A-15) replaces the save and
reminder CTAs with 'Sold out — tickets no longer available.'"*

**The criterion governs.** The save CTA is replaced. The state is calm, one line, and
the **neighbor count and the breakdown still render** — a sold-out event is still an
event the user was shown, and hiding its explanation would be a second, quieter lie.
The "Find similar events" link from the mockup is **absent**: there is no similar-events
data (D7).

**The three states.**

| State | The copy | The action |
|---|---|---|
| **removed** | "This event is no longer available." | a back link to the Pulse Digest |
| **error** | "Couldn't load this event. Back to Pulse Digest." | a single primary action home |
| **loading** | a header block, a meta row, three chip skeletons | none |

The error's copy is the work item's own and is followed exactly, including the second
sentence — the copy says where the action goes, so the action is "Back to Pulse Digest"
and it is **one primary button**.

**The loading skeleton is the Detail Screen's own shape**, not the digest's three
rectangles: "one full-width header block + one meta row + 3 chip skeletons. Same fade
animation." The **same fade** means `motion.fadeIn` — the product's single transition —
not the digest's `skeleton-pulse` keyframe. The digest's pulse is a *loading* animation
for a *waiting* state; a detail page's skeleton is a *shape* that fades in.

### D13 — The confidence pulse's tooltip carries the **persisted tags**, not an invented explanation

The card's confidence tooltip shows the persisted tags as "Surfaced because:". The Detail
Screen's `Tooltip.Confidence` has the same job and **the same source**.

The `EXPERIENCE.md` §4 `Indicator.Confidence` text ("Strong match on your top three
interests. Within 2 km. Source reliability 0.92.") is the **mockup's** prose and it is
**drift**: none of those three strings was persisted, and two of them are things the
codebase cannot compute at all (FR-16, coordinates). The card already established the
correct precedent — "the tags *are* the persisted contributing factors" — and this screen
follows it.

So the confidence tooltip shows the **same factor lines as the breakdown** (D5). The
breakdown is the elaboration of the tags; the tooltip is the short form. **One source of
prose, two places** — so the two cannot drift.

### D14 — The Detail Screen's shell is the authed shell, and the route is inert-safe

The page renders inside `AppShell` — the same sidenav, the same brand-only topbar, the
same bottom-tab bar — with **Digest** as the active route. The Detail Screen is a
destination *inside* the app, not a surface of its own.

**But the Detail Screen is also reachable by an anonymous visitor** (the IA: "Authed +
Anon (read-only)"). An anonymous visitor has no sidenav and no bottom-tab bar — they
have the public preview's chrome. So the page branches:

| Visitor | The chrome |
|---|---|
| signed in | `AppShell` with the name from the session |
| anonymous | the public shell — the brand topbar and the pre-auth footer, as `/preview` uses |

**The anonymous branch is read-only, and it looks read-only.** No Save button, no
Reminder picker, no Dismiss, no breakdown, no confidence pulse, no neighbor count, no
saved state. **The personal block is `null`**, so every one of those is absent from the
payload, and the screen renders only what the payload has.

**The route does not redirect an anonymous visitor to sign in.** The API serves the
public facts to anonymous callers on purpose, and the IA marks the route "Authed + Anon
(read-only)". A redirect would turn a *read-only* route into an authed one and would
break the share link — which is the whole reason the canonical URL is on the payload.

---

## The file plan

| File | Kind | What it is |
|---|---|---|
| `app/events/[id]/page.tsx` | new | the route, the read, and the four states |
| `lib/event-detail-read.ts` | new | the server-side read: `readEventDetail()` |
| `lib/detail-labels.ts` | new | the breakdown prose, the neighbor prose, and the tag→line mapping |
| `components/detail/detail-header.tsx` | new | the badge, the confidence pulse, the name, the when·where |
| `components/detail/detail-breakdown.tsx` | new | the expandable "Surfaced because:" section |
| `components/detail/detail-actions.tsx` | new | Save and Share |
| `components/detail/detail-reminder.tsx` | new | the display-only reminder chips |
| `components/detail/detail-neighbors.tsx` | new | the bucketed prose line |
| `components/detail/detail-states.tsx` | new | the loading skeleton, the removed state, the error state |
| `components/detail/trigger-tip.tsx` | new | the shared tooltip: keyboard, focus, outside-tap, `Esc` |

**The tooltip is extracted rather than copied.** The card's tooltip is a CSS-only
sibling inside `pulse-card.tsx`; this one needs `Esc` and outside-tap dismissal, which
CSS cannot do. Copying the card's shape and adding the two handlers would be two
tooltips that behave differently — so the *new* one is a component, and the card's is
left alone (D10).

---

## The test plan

**`app/events/[id]/page.test.tsx`** — the visible rules.

| Group | What it pins |
|---|---|
| the read | the four answers; the 404 and the failure are different; the read carries the session cookies; a 401 is not a crash |
| the order | the element sequence matches the locked order exactly (D2) |
| the tags | the rendered tags equal the card's, same labels, same order (D3) |
| the absence | **no** breakdown section, **no** tags, **no** confidence pulse when `why_this` is `null`; the section element is not in the DOM (D4) |
| the anonymous case | no breakdown, no confidence pulse, no neighbor line, no save button, no reminder picker; the public facts are all there |
| the breakdown | one factor per line; one line per persisted tag; **no line the composition does not support**; no reliability score; no distance |
| the neighbors | all four buckets; `null` renders **nothing**; the rendered text contains **no digits** (D6) |
| the states | the removed copy; the error copy and its single action; the skeleton's shape |
| the sold-out | the line; the Save and Reminder are gone; the breakdown is still there |
| the picker | the default plan is named; the chips are not buttons; no terracotta on a chip |
| the time | user-local; venue-local shown when the wall-clock differs; the approximate marker |

**`tests/event-detail-a11y.test.tsx`** — the axe gate, over **four** documents (found,
anonymous, removed, error), for the same reason the digest home's is over four: a page
can be accessible when it is full and inaccessible when it is empty.

**`tests/event-detail-boundary.test.ts`** — the source-level rules that no rendering
test can see:

- no literal hex, no raw `rgb()`/`hsl()`, every colour from a token utility;
- **no exact neighbor count anywhere** — the literal strings `"12"`, `"5–9"` and
  `"👥"` are absent from the source;
- **no emoji glyphs** in the detail components (`📍 ⭐ 🆓 ✅ 👥`) — the emoji-as-CTA ban,
  decided once and applied consistently (D6);
- **no reliability score** — the literals `"0.91"`, `"reliability"` and `"Bayesian"` are
  absent from the detail components;
- **no distance claim** — the literals `"km"`, `"blocks"` and `"office"` are absent;
- the picker contains no `<button`;
- no reviews, no ratings, no attendance, no "similar events", no "report this event";
- no motion class in the markup other than the one the product allows.

---

## The drift table

Nine places where the mockups, the PRD or the as-built assumptions disagree with the
spine. Each is resolved **in favour of the spine**, and the resolution is recorded.
Three further deviations were found during the review and are listed after them.

| # | The drift | The resolution |
|---|---|---|
| 1 | The mockup's breakdown shows "Source reliability 0.91 (Bayesian-smoothed)". | **Not reproduced.** FR-16 is unbuilt — `Source` has no score field. A factor line stating a number we never computed is worse than no line (D5). |
| 2 | The mockup's breakdown shows "It's four blocks from your office." | **Not reproduced.** There are no coordinates and no work address. "nearby" is a city band, and the band is what the tag says (D5). |
| 3 | The mockup's breakdown shows "You attended 2 similar events in the past 60 days". | **Not reproduced.** There is no attendance data anywhere in the codebase (D7). |
| 4 | The mockup's breakdown shows "Free, no ticket required." | **Not reproduced.** There is no price field on `Event`. |
| 5 | The mockup shows "12 neighbors tracking this in Brooklyn". | **Not reproduced.** FR-24: exact counts are never exposed. The bucketed prose replaces it, with no digits (D6). |
| 6 | The PRD's `👥 5–9` / `👥 10–24` rendering. | **Not reproduced.** `EXPERIENCE.md` §12's `_RECONCILE_` note revised this to prose-only under the emoji-as-CTA ban. The PRD's form is the superseded draft (D6). |
| 7 | The mockup's `📍 ⭐ 🆓 ✅` glyphs on the breakdown factors. | **Not reproduced.** Same ban, same reason. The factors are text lines (D5, D6). |
| 8 | The mockup has a "Map" section. | **Not reproduced.** There are no coordinates to put on a map, and a static map would be a different product decision. The venue name and city carry the location. |
| 9 | The mockup has "Save to my Pulse → / Share / Less like this" and a "+ Add custom slot". | **Save and Share ship** (both have real endpoints). **"Less like this" does not** — FR-25's dismissal is a card swipe, and there is no dismissal endpoint (D9). **The custom slot does not** — the picker is display-only (D8). |

**Three more deviations, in the spine's favour but against the PRD's literal text:**

| # | The deviation | Why |
|---|---|---|
| 10 | The action row is **two** buttons, not three. | A "Dismiss" button with no backend is a control that silently does nothing. The swipe stays on the card (D9). |
| 11 | The **Confidence Pulse is absent** when there is no composition. | The pulse's value is the persisted Relevance Pulse bucket. There is no other source for it, and the Event Fit's bucket belongs to the anonymous preview (D4, AD-10). |
| 12 | The **Source Badge is absent** when there is no composition — including for an anonymous visitor. | `EventDetailFactsOut` carries no `source_badge`; the only badge in the payload is the composition's persisted one. Resolving a badge fresh would be a recomputation at view time (D3b). The API's gap, not this screen's. |

---

## What this item does not decide

- **The `opened` signal is not fired by this item.** The API has
  `POST /api/events/{event_id}/opened`, and it is the *second* half of the neighbor
  count's qualifying rule. Firing it means a client-side `POST` on mount, with CSRF,
  that must not block the render and must not be fired for anonymous visitors. **That is
  a client-component concern** and it is deferred to the delivery intent, where the
  detail-open signal belongs. The read here does not send it, and the neighbor bucket
  therefore counts saves and opens recorded before this screen shipped — which is
  correct, because the count is *other people's* behaviour.
- **The share sheet.** `navigator.share` with a clipboard fallback is a browser API,
  not a design decision. It ships here because it is small and real; a custom share
  sheet belongs with the rest of the sheet work.
- **The reminder picker becoming interactive.** It ships display-only (D8). Making it
  real needs the delivery intent's scheduler, and the control's copy changes when it
  does.
