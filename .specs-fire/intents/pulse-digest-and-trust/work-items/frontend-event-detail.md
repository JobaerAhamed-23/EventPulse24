---
id: frontend-event-detail
title: The Detail Screen at /events/:id
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: pending
depends_on: [frontend-pulse-card, event-detail-api]
created: 2026-10-30
---

# Work Item: The Detail Screen at /events/:id

## Description

The surface UJ-4 is entirely about: a user doubts a card, taps it, and reads why it was chosen. EXPERIENCE.md calls the why-this breakdown "the heart" of the screen, and the element order is wireframe-locked in both PRD §14.3 and EXPERIENCE.md §12.

It is the screen where AD-10's durability rule becomes visible: an event this user was never shown gets **no explanation at all**, rather than a plausible one generated on the spot.

## Acceptance Criteria

- [ ] **The locked element order**, top to bottom: Source Badge → Confidence Pulse → event name → when · where → **the same 3 Why-this Tags as the card** → description (2–3 lines max) → reminder picker → Save / Share / Dismiss → **why-this breakdown (expandable)** → similar events → neighbor count.
- [ ] **The Why-this Tags are byte-identical to the card's.** FR-21's third testable consequence is that tags are consistent on the card and the detail screen; both read the same persisted composition, so a test asserts equality rather than similarity.
- [ ] **The why-this breakdown renders one factor per line**, in human-readable prose derived from the persisted tags — never raw model output and never a score dump. Each factor may carry a tooltip. The expansion uses `motion.fadeIn` (240ms), disabled under reduced motion.
- [ ] **No composition, no breakdown.** An event the user was never shown renders the public facts and **no explanation section at all** — not an empty one, not a placeholder, not an Event Fit standing in for it. A test asserts the section is absent, and a second asserts no Event Fit value reaches this page.
- [ ] **Anonymous visitors** (the IA marks this route Authed + Anon read-only) see the event's public facts and **nothing personal**: no breakdown, no confidence dots, no neighbor count, no saved state.
- [ ] **Neighbor count as bucketed prose**: "A few / Some / Many / A lot of neighbors saved this", **silently absent below 5** with no empty row and no "0 neighbors" copy. **No exact number is rendered and none is present in the DOM.** *(The mockup's "12 neighbors tracking this in Brooklyn" violates FR-24's "exact counts are never exposed" and is not reproduced.)* The `👥` emoji prefix is dropped under the emoji-as-CTA ban.
- [ ] **No reviews, no ratings, no community-corroboration count** (ASSUM-6 and ASSUM-7, both deferred). Absent, not empty.
- [ ] **"Similar events you've attended" does not ship** — there is no attendance data — and the section is absent rather than present and empty.
- [ ] **The reminder picker is display-only or absent.** FR-9's picker belongs to the delivery intent and `ReminderPlan` already exists but nothing schedules sends. The design states which, and does not ship a control that silently does nothing.
- [ ] **"Report this event"** links to the FR-59 flow only if that flow exists; otherwise it is absent rather than dead.
- [ ] **States:** loading is a header block, a meta row and three chip skeletons with the same fade; the removed state reads "This event is no longer available."; the error reads "Couldn't load this event. Back to Pulse Digest." with a single primary action home. Sold-out (A-15) replaces the save and reminder CTAs with "Sold out — tickets no longer available."
- [ ] **Tooltips** (`Tooltip.Source`, `Tooltip.Confidence`) use a `<button>` trigger with `aria-describedby` pointing at a sibling `role="tooltip"`; hover **and** `:focus-visible`; on touch below 768px they open on tap and dismiss on outside-tap or `Esc`. **No hover-only tooltips on touch.**
- [ ] **Time is shown user-local**, with venue-local also shown when the event is in a different timezone (Glossary §3), and an approximate marker when `tz_review_pending` is set.
- [ ] `axe-core` zero serious/critical violations; Lighthouse accessibility ≥95; LCP <1.5s at 3G-fast.
- [ ] Tests cover: the element order; tag equality with the card; the breakdown rendering per-line; **the no-composition case**; the anonymous case; every neighbor bucket boundary including suppression at 4; the three error/empty states; tooltip keyboard and touch behavior; and the cross-timezone time display.

## Technical Notes

**The mockup's breakdown copy is richer than the data supports.** `event-detail-desktop.html` shows four factor rows including "Source reliability 0.91 (Bayesian-smoothed)" and "It's four blocks from your office" — neither of which exists: FR-16 is unbuilt and there are no coordinates. The breakdown must render the factors the composition actually persisted, and no others. A factor line that states a reliability score we never computed is exactly the explanation-drift AD-10 exists to prevent, and it would be worse than showing nothing.

**The emoji glyphs in that mockup** (`📍 ⭐ 🆓 ✅`) also sit badly with the documented emoji ban; the `_RECONCILE_` note in EXPERIENCE.md §12 already removed the `👥` prefix from the neighbor line for exactly this reason. Decide once, apply consistently, record it.

The Detail Screen is reachable from the card, so the two must stay in step. Both read the same persisted composition — if a future change makes the card show one thing and the detail another, FR-21's consistency consequence is the test that should catch it.

## Dependencies

- frontend-pulse-card
- event-detail-api
