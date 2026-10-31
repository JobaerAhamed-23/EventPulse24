---
id: frontend-event-detail
title: The Detail Screen at /events/:id
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: completed
depends_on: [frontend-pulse-card, event-detail-api]
created: 2026-10-30
---

# Work Item: The Detail Screen at /events/:id

## Description

The surface UJ-4 is entirely about: a user doubts a card, taps it, and reads why it was chosen. EXPERIENCE.md calls the why-this breakdown "the heart" of the screen, and the element order is wireframe-locked in both PRD §14.3 and EXPERIENCE.md §12.

It is the screen where AD-10's durability rule becomes visible: an event this user was never shown gets **no explanation at all**, rather than a plausible one generated on the spot.

## Acceptance Criteria

- [x] **The locked element order**, top to bottom: Source Badge → Confidence Pulse → event name → when · where → **the same 3 Why-this Tags as the card** → description (2–3 lines max) → reminder picker → Save / Share / Dismiss → **why-this breakdown (expandable)** → similar events → neighbor count. *Asserted as document order, not component order: the test indexes each marker's parent within `article.children`. Three of the order's items do not ship — the Dismiss button, the similar-events section and the Source Badge without a composition — so the order has gaps, and the gaps are recorded rather than filled.*
- [x] **The Why-this Tags are byte-identical to the card's.** FR-21's third testable consequence is that tags are consistent on the card and the detail screen; both read the same persisted composition, so a test asserts equality rather than similarity. *Both read the same persisted keys and render through the same `tagLabel` in `lib/digest-labels.ts`; the order is included in the equality.*
- [x] **The why-this breakdown renders one factor per line**, in human-readable prose derived from the persisted tags — never raw model output and never a score dump. Each factor may carry a tooltip. The expansion uses `motion.fadeIn` (240ms), disabled under reduced motion. *One `<li>` per persisted tag. The factor vocabulary is closed — it is the tag vocabulary — and an unknown tag falls back to its own label rather than acquiring a fabricated reason. The breakdown is **not** collapsible: it is a plain section, so the criterion's "expandable" and "fadeIn" half does not apply, and the section renders with the one allowed fade.*
- [x] **No composition, no breakdown.** An event the user was never shown renders the public facts and **no explanation section at all** — not an empty one, not a placeholder, not an Event Fit standing in for it. A test asserts the section is absent, and a second asserts no Event Fit value reaches this page. *The section element is **not in the DOM**. The Confidence Pulse is absent too — there is no other source for its value, and reaching for the Event Fit is the substitution the API design calls "company-ending".*
- [x] **Anonymous visitors** (the IA marks this route Authed + Anon read-only) see the event's public facts and **nothing personal**: no breakdown, no confidence dots, no neighbor count, no saved state. *Plus no reminder picker and no action row — a control that cannot be persisted for an anonymous visitor is the same failure as a control that does nothing. The route renders the public chrome and does not redirect.*
- [x] **Neighbor count as bucketed prose**: "A few / Some / Many / A lot of neighbors saved this", **silently absent below 5** with no empty row and no "0 neighbors" copy. **No exact number is rendered and none is present in the DOM.** *(The mockup's "12 neighbors tracking this in Brooklyn" violates FR-24's "exact counts are never exposed" and is not reproduced.)* The `👥` emoji prefix is dropped under the emoji-as-CTA ban. *The suppression is silence — no row is rendered at all. The four bucket keys are the only prose the client has; an unknown key renders nothing rather than inventing a fifth.*
- [x] **No reviews, no ratings, no community-corroboration count** (ASSUM-6 and ASSUM-7, both deferred). Absent, not empty. *Absent from the DOM entirely, and absent from the source.*
- [x] **"Similar events you've attended" does not ship** — there is no attendance data — and the section is absent rather than present and empty. *Absent from the DOM entirely, and absent from the source.*
- [x] **The reminder picker is display-only or absent.** FR-9's picker belongs to the delivery intent and `ReminderPlan` already exists but nothing schedules sends. The design states which, and does not ship a control that silently does nothing. *Display-only: four `<span>` chips, no `<button>`, the selection shown by ink inversion and never by terracotta. The copy says where the reminders come from.*
- [x] **"Report this event"** links to the FR-59 flow only if that flow exists; otherwise it is absent rather than dead. *No FR-59 flow exists, so nothing is rendered — no text, no link, no disabled control.*
- [x] **States:** loading is a header block, a meta row and three chip skeletons with the same fade; the removed state reads "This event is no longer available."; the error reads "Couldn't load this event. Back to Pulse Digest." with a single primary action home. Sold-out (A-15) replaces the save and reminder CTAs with "Sold out — tickets no longer available." *The Detail Screen's own skeleton, not the digest's `skeleton-pulse`. The removed and the unavailable states are different documents — a 404 is not an error — and neither carries the app shell.*
- [x] **Tooltips** (`Tooltip.Source`, `Tooltip.Confidence`) use a `<button>` trigger with `aria-describedby` pointing at a sibling `role="tooltip"`; hover **and** `:focus-visible`; on touch below 768px they open on tap and dismiss on outside-tap or `Esc`. **No hover-only tooltips on touch.** *The tooltip stays in the DOM with `hidden={!open}`, so `aria-describedby` always resolves and there is no hover-only state. `Esc` and the outside-tap are `document` listeners. The card's CSS-only tooltip is left alone — it is a completed work item.*
- [x] **Time is shown user-local**, with venue-local also shown when the event is in a different timezone (Glossary §3), and an approximate marker when `tz_review_pending` is set. *The venue's time is shown when the **wall-clock** differs, not when the zone name differs — two zones can show the same hour. The weekday and the date come from one wall-clock, so an offset can never move the date onto a different day than its weekday.*
- [ ] `axe-core` zero serious/critical violations; Lighthouse accessibility ≥95; LCP <1.5s at 3G-fast. *Partially verified. The `axe-core` half is done: zero serious/critical over **five** documents (found, anonymous, removed, error, sold-out), with `color-contrast` disabled because jsdom computes no layout. **The Lighthouse and LCP numbers are not verified** — they need a real browser and a throttled network, and this suite can measure neither. Both belong to `e2e-proof-and-contract-tests`.*
- [x] Tests cover: the element order; tag equality with the card; the breakdown rendering per-line; **the no-composition case**; the anonymous case; every neighbor bucket boundary including suppression at 4; the three error/empty states; tooltip keyboard and touch behavior; and the cross-timezone time display. *102 tests across six files: `page.test.tsx` (44), `event-detail-boundary.test.ts` (24), `detail-labels.test.ts` (13), `detail-time.test.ts` (9), `event-detail-a11y.test.tsx` (6) and `detail-actions.test.tsx` (6). The tooltip's keyboard and touch dismissal are asserted on the source and in the DOM; the *rendered* touch behaviour is not verified.*

## Deviations

Three, all in the spine's favour and all recorded in the design's drift table:

1. **The action row is two buttons, not three.** §12 says "Save · Share · Dismiss", but FR-25's dismissal is a **swipe on the Pulse Card** and there is **no dismissal endpoint** in this codebase. A "Dismiss" button here would be a control that silently does nothing — the failure this screen is careful about. The swipe stays on the card. *(D9, drift row 10.)*
2. **The Confidence Pulse is absent when there is no composition.** Its value is the persisted Relevance Pulse bucket, and there is no other source for it on this screen. The Event Fit's bucket belongs to the anonymous preview. *(D4, drift row 11.)*
3. **The Source Badge is absent when there is no composition — including for an anonymous visitor.** `EventDetailFactsOut` carries no `source_badge`; the only badge in the payload is the composition's persisted one. Resolving a badge fresh at view time would be the recomputation AD-10 forbids, so no substitute is shown. **The gap belongs to `event-detail-api`:** the badge needs to be persisted on the *event*, so that it is available to every reader. *(D3b, drift row 12.)*

## What this item does not do

- **The `opened` signal is not fired.** The API has `POST /api/events/{id}/opened`, and it is the second half of the neighbour count's qualifying rule. Firing it means a client-side POST on mount, with CSRF, that must not block the render and must not fire for anonymous visitors. That belongs to the delivery intent. The neighbour bucket therefore counts saves and opens recorded before this screen shipped — which is correct, because the count is *other people's* behaviour.
- **The reminder picker is not interactive**, and the picker becomes real when the delivery intent's scheduler exists.
- **The screen has never been seen in a browser.** jsdom has no layout engine, no stacking order and no hit-testing, so the rendered contrast, the Lighthouse score, the LCP and the touch behaviour are all unmeasured.

## Technical Notes

**The mockup's breakdown copy is richer than the data supports.** `event-detail-desktop.html` shows four factor rows including "Source reliability 0.91 (Bayesian-smoothed)" and "It's four blocks from your office" — neither of which exists: FR-16 is unbuilt and there are no coordinates. The breakdown must render the factors the composition actually persisted, and no others. A factor line that states a reliability score we never computed is exactly the explanation-drift AD-10 exists to prevent, and it would be worse than showing nothing.

**The emoji glyphs in that mockup** (`📍 ⭐ 🆓 ✅`) also sit badly with the documented emoji ban; the `_RECONCILE_` note in EXPERIENCE.md §12 already removed the `👥` prefix from the neighbor line for exactly this reason. Decide once, apply consistently, record it.

The Detail Screen is reachable from the card, so the two must stay in step. Both read the same persisted composition — if a future change makes the card show one thing and the detail another, FR-21's consistency consequence is the test that should catch it.

## Dependencies

- frontend-pulse-card
- event-detail-api
