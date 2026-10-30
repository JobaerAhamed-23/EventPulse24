---
id: frontend-digest-home
title: The Pulse Digest home at /
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: pending
depends_on: [frontend-pulse-card, digest-read-api]
created: 2026-10-30
---

# Work Item: The Pulse Digest home at /

## Description

Replaces the placeholder. `frontend/app/page.tsx` currently says "Your Pulse is being prepared" and its own docstring names this intent as the one that ends it: "In the route map `/` is the **Pulse Digest**. That is the Pulse Digest intent's work, so until then this is the calm placeholder the onboarding intent promised."

The three-way route decision it already makes — anonymous → `/preview`, onboarding unfinished → `/onboarding`, signed in and onboarded → here — stays exactly as it is. Only the page's body changes.

## Acceptance Criteria

- [ ] **The existing route decision is preserved unchanged**, including the fourth case that is deliberately not a redirect: when the API cannot be reached, the page says so rather than sending a signed-in user to the anonymous preview and telling them they are logged out when they are not.
- [ ] **Header:** the `Indicator.Today` terracotta dot inline with `{weekday} · {date} · {city}`, the h1 **"Today, three things matter."**, and the lede "Your morning brief, kept short on purpose. Open one, save one, or close the app and let it go." *(The mobile mockup's inverted "Three things matter today." is drift and does not govern.)*
- [ ] **Three cards in slot order**, rendered from the API's persisted compositions — the page performs **no scoring, no sorting and no re-bucketing**. A test asserts the rendered order is the server's order.
- [ ] **The 3-card discipline holds.** No infinite scroll, no carousel, no "show more", and no reordering by engagement. Adaptive expansion to 5 or 7 cards is out of scope (ASSUM-5 is open) and no affordance hints at it.
- [ ] **Empty state (FR-8):** a single `Card.PulseDigest` variant reading **"Nothing on the pulse today. The calendar is yours."** with a `Text.Meta` line **"No qualifying events in {city}."** below it, and **one low-weight `Text.Meta` "Suggest an event" link** — **no CTA pair, no carousel, no upsell of any kind**. *(EXPERIENCE.md §5 is marked canonical and is stricter than both DESIGN.md and the as-built mockup, which ships a terracotta primary plus a ghost "Browse all sources" button. The spine governs; record the deviation from the mockup.)*
- [ ] **Not-yet-composed is distinct from empty.** A user whose digest has not been composed sees a calm "being prepared" state, not FR-8's "your week is quiet" — the second is a claim about the world and would be a lie.
- [ ] **Loading:** three paper skeleton rectangles, **1800ms pulse period**, no text inside them, and **no spinner anywhere** ("a spinner is a visual urgency badge").
- [ ] **Error:** "Couldn't reach Pulse. Try again." with a single retry primary button whose label becomes **"Refresh page."** on the second consecutive failure.
- [ ] **Shell:** `Component.Sidenav.App` in its locked 6-route order — **Digest / Timeline / Add / Browse / Conflicts / Settings** — with the active item as an ink-primary label on a `color.surface.subtle` pill and **never a terracotta fill**; the sidenav footer pinned bottom with Search and the account row; the topbar **brand-only** (the topbar-quiet rule). Routes that do not exist yet are present but inert, and the design states how an inert route behaves rather than 404ing silently. The global `a { color: inherit; text-decoration: none; }` reset must be in place before the sidenav is applied — a documented bug from the 2026-09-06 migration.
- [ ] **Live region:** `role="status" aria-live="polite" aria-atomic="true"` announcing "Pulse Digest ready, 3 events for today."
- [ ] **Responsive:** single-column at ≤767px with the bottom-tab nav; two-column at ≥1024px with the digest left and the side rail right; content constrained to 1180px at `xl` with **no reflow**. **Desktop adds whitespace and hover affordances — never features, screens, actions or copy.**
- [ ] **Accessibility:** `axe-core` reports **zero serious or critical violations** on this surface, Lighthouse accessibility **≥95**, every card reachable in a single Tab cycle, and contrast ≥4.5:1 text / 3:1 UI on both the warm and cool card variants.
- [ ] **The Pro upsell card does not ship** (no `SUBSCRIPTION` exists; everyone is Free), and the "Saved this week" rail ships only if it reads already-built saved-event data without new backend work.
- [ ] Tests cover: the three route decisions and the unreachable-API case; three cards in server order; the empty state's exact copy including the city line and the single link; the not-yet-composed state; the loading skeleton; both error labels; the live-region text; and the axe-core gate.

## Technical Notes

**Pull-to-refresh is enabled here and nowhere else** — `/` is the one surface where swipe-down refreshes. Whether that ships in this item or waits for a mobile pass is a design decision; if it ships, it must not auto-poll. EXPERIENCE.md forbids passive auto-refresh explicitly on `/conflicts` and the same calm rule applies here: "Auto-refresh would be a passive pressure element."

**Offline is specified but is not obviously this intent's.** EXPERIENCE.md describes a service worker caching the last digest with a 24h TTL and an "Offline — showing last sync." banner. There is no service worker in this codebase. Treat it as out of scope unless the design doc argues otherwise, and say so rather than half-building it.

The placeholder page is a good model for what to keep: it is honest about what does not exist yet, it makes the route decision in a pure function (`lib/session.ts`), and it explains in its docstring why the decision lives on the page rather than in `proxy.ts`. Preserve that structure.

## Dependencies

- frontend-pulse-card
- digest-read-api
