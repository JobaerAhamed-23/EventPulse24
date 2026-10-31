# Review report: `frontend-event-detail`

**Work item**: `frontend-event-detail`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-31

---

## The verdict

**Approved with one recorded deviation.** The screen renders what it was given and
generates no explanation, which is the whole point of AD-10. The review found and fixed
**one real defect** — the reminder picker rendered for anonymous visitors — and
**recorded one product-level gap** that belongs to the API, not to this screen: the
Source Badge has no source to read when there is no composition.

The defect is worth stating plainly, because it is the kind that survives a naive test
suite: **an anonymous visitor was shown a reminder picker whose four chips could not be
persisted for anyone.** The page's own tests mocked the personal half away and the
anonymous case asserted on the *absence* of the breakdown, the pulse, the neighbour count
and the saved state — but never on the absence of the picker. A control that cannot be
saved is the same failure as a control that does nothing, and this screen is careful
about exactly that.

---

## What the review checked

| Property | How | Result |
|---|---|---|
| the screen generates no explanation | every fact traced to a persisted field; no score computed, no reason generated | green |
| no composition ⇒ nothing personal | the section elements are **absent from the DOM**, not empty | green |
| an Event Fit never stands in for a missing Relevance Pulse | the pulse's value is `why_this.bucket`; there is no other source | green |
| the read derives anonymity from the payload | `personal === null`, never from the session | green |
| the personal half is behind the signed-in guard | the picker and the action row | **red → fixed** |
| the locked order is the document's order | asserted on `article.children` | green |
| the tags are the card's tags | the same persisted keys, the same `tagLabel` | green |
| the factor vocabulary is closed | an unknown tag falls back to its own label | green |
| no factor states an uncomputed fact | no reliability, no distance, no price, no attendance | green |
| the neighbour line has no digits and no emoji | asserted on the rendered text | green |
| a suppressed count is silence | `null` renders nothing at all | green |
| the time cannot move the date across midnight | the weekday and the date come from one wall-clock | green |
| the tooltip is a real tooltip | `<button>` + `aria-describedby` + `role="tooltip"` + `Esc` + outside-tap | green |
| every colour comes from a token | the boundary test's four colour rules | green |
| the motion is one fade | the boundary test's motion rules | green |
| the action row has two buttons, not three | no dismissal endpoint exists | green — deviation recorded (D9) |
| the axe gate covers every document | five documents, not one | green |

---

## The one change the review made

### The reminder picker rendered for an anonymous visitor

**The bug.** The page rendered the picker and the action row **outside** the `personal`
guard:

```tsx
{event.is_sold_out ? (
  <p>Sold out — tickets no longer available.</p>
) : (
  <>
    <div className="mt-8"><DetailReminder /></div>
    <div className="mt-8"><DetailActions … /></div>
  </>
)}
```

The `personal` check was only applied to the neighbour count. An anonymous visitor
arrived at `/events/:id` and was shown four reminder chips — "5 days before", "2 days
before", "1 day before", "1 hour before" — and a Save button, neither of which could be
persisted for them.

**Why it matters.** The screen's whole posture is "no control that silently does
nothing" — which is why the Dismiss button was dropped (D9) and why the picker is
display-only (D8). An anonymous reader who taps "1 hour before" gets no reminder, no
confirmation, and no error. The screen promised a control it could not honour.

**The fix.** Both the picker and the action row are now behind the guard:

```tsx
{personal ? (
  <>
    <div className="mt-8"><DetailReminder /></div>
    <div className="mt-8"><DetailActions eventId={event.id} saved={personal.saved} /></div>
  </>
) : null}
```

**The regression test.** The anonymous case now asserts that neither the picker's chips
nor the action row's buttons are in the document. The boundary test's picker rule
(`no <button` in the picker) was already there; the *absence* rule was the missing half.

---

## The gap the review recorded rather than closed

### The Source Badge has no source to read without a composition

**What the locked order asks for.** `EXPERIENCE.md` §12 puts the Source Badge **first**,
for every reader:

```
Source Badge → Confidence Pulse → event name → …
```

**What the payload can give.** `EventDetailFactsOut` carries the event's public facts —
title, description, times, venue, `canonical_url`, `source_name`, `is_sold_out`,
`tz_review_pending`. It carries **no `source_badge`**. The only badge in the whole
payload is `why_this.source_badge` — the **persisted** one, which exists only when a
composition does.

So for an anonymous visitor, and for a signed-in user who was never shown this event,
**the badge is absent**. The locked order's first element is missing for those readers.

**The two alternatives, and why neither was taken.**

1. **Widen the API's `EventDetailFactsOut`** to carry a badge. That is a change to a
   completed work item (`event-detail-api`), and — more importantly — it means the
   backend resolving a badge *at read time* for a payload that has no persisted
   composition. The badge is a **persisted** fact about how the event was acquired, and
   the catalog's `Source.type` is one input to it, not the whole of it: the backend's own
   `source_badges` service maps a source's type **and** its acquisition method. Reading
   it fresh on every view is the recomputation-at-view-time that AD-10 exists to prevent.
2. **Substitute the card's badge** when there is a card. That is the same substitution
   by another route, and it would show a badge for an event the user was never shown —
   which is precisely the explanation AD-10 forbids.

**The decision.** Neither. The screen renders the badge it has and shows nothing when it
has none. This is recorded as **D3b** in the design and as **drift row 12**, and the gap
is named as **`event-detail-api`'s** to close: the badge needs to be persisted on the
**event**, not only on the composition, so that it is available to every reader.

**Why this is the right call even though it leaves the order short.** The order says the
badge comes first *when there is a badge*. The order does not license inventing one. A
sceptical reader who sees no badge learns "we don't know where this came from"; a
sceptical reader who sees a *fabricated* badge learns something false. The first is
truthful and the second is the thing the whole trust surface exists to prevent.

---

## Decisions the review confirmed

| The question | The spines disagree? | The decision | Why |
|---|---|---|---|
| the badge's position in the trust row | the card renders pulse-then-badge; §12 locks badge-then-pulse | **badge first** | §12 is the locked order for this screen; the card's order is the card's |
| does the Event Fit stand in for a missing pulse | — | **no** | the API design calls that substitution "company-ending" |
| the picker's form | — | **`<span>` chips, not `<button>`s** | nothing schedules sends; a button would be a control that does nothing |
| the picker's selection | — | **ink inversion**, never terracotta | terracotta is for one primary action per surface, and Save is it |
| the third action button | §12 says "Save · Share · Dismiss" | **two buttons** | FR-25's dismissal is a card swipe and there is no dismissal endpoint |
| the breakdown's factor set | the mockup has four rich factors | **the persisted tag keys only** | four of the mockup's factors state facts this codebase cannot compute |
| an unknown tag | — | **its own label, plainly** | a new server tag appears rather than vanishing or acquiring a fabricated reason |
| the neighbour line's threshold | — | **silence below 5** | "0 neighbors" is a signal about how many people are near the event |
| the venue's time | — | shown when the **wall-clock** differs | two zones can show the same hour; showing both is noise |
| the anonymous chrome | — | the public shell, **no redirect** | the IA marks the route "Authed + Anon (read-only)" |
| the skeleton's shape | — | header block + meta row + three chips | the digest's `skeleton-pulse` is the digest's own vocabulary |
| the `opened` signal | — | **not fired here** | it is a client-component concern and belongs to the delivery intent |

---

## Things the review looked for and did not find

- **No second round trip for the user's timezone.** The zone comes from
  `Intl.DateTimeFormat().resolvedOptions().timeZone` in the browser. The payload carries
  the instant and the venue's IANA zone (AD-6), and the conversion happens at the
  presentation edge.
- **No date that disagrees with its weekday.** The weekday is derived from the *same*
  wall-clock as the date, via `Date.UTC(y, m-1, d).getUTCDay()`. Two independent `Intl`
  calls could straddle a DST boundary; one wall-clock cannot.
- **No digits in the neighbour line.** The bucket key is prose and `NeighborCount` has no
  count field, so there is nothing to leak even if a future change tried.
- **No client-side derivation of any fact.** The tags are read, not re-sorted; the bucket
  is rendered, not recomputed; the date is converted, not recomputed; the saved state
  comes from `personal.saved` — the user's own save row — not from a tag on a
  composition that may have been composed days ago.
- **No session read on the anonymous path.** `getSession()` is called only on the
  `found` branch. The anonymous branch never reads the session, so the read cannot fail
  because of it.
- **No CSS pseudo-element carrying visible text.** The breakdown's bullets are a real
  `<ul>`/`<li>`, not `before:content-['—']`.
- **No emoji.** The badge glyphs are `✓ ⚭ ⌸ ⚠` — text marks, not pictographs.

---

## What the review could not verify

**The screen has never been seen in a browser.** The gate is jsdom, which has no layout
engine, no stacking order and no hit-testing. Three of the work item's criteria are
claims about a real browser and are **not** asserted by this suite:

- **Lighthouse accessibility ≥95** and **LCP <1.5s at 3G-fast** — neither is measurable
  in jsdom.
- **Rendered contrast** — `color-contrast` is disabled in the axe gate, because jsdom
  computes no layout and the rule reports false positives rather than findings. The
  colours are token-driven, but the rendered pairings are unmeasured.
- **The touch behaviour** — the tooltip's `Esc` and outside-tap dismissal are asserted on
  the source and in the DOM, and the keyboard path is unit-testable, but "no hover-only
  tooltips on touch" is a claim about a finger on glass.

`e2e-proof-and-contract-tests` is the run's last item and the one that puts the product
in front of a real browser. These three belong there.

**One thing the next item inherits.** The Detail Screen's route is `ƒ /events/[id]` — a
dynamic server-rendered route with `force-dynamic`. An end-to-end proof needs a route
that exists and returns the right document for a known event id, and it needs the signed-in
and anonymous variants to be distinguishable. The read's four answers
(`found` / `anonymous` / `removed` / `unavailable`) are the seams that e2e will drive.
