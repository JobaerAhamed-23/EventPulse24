---
id: frontend-digest-strip-and-detail-banner
title: Told once, calmly, where they already are — the strip and the banner
intent: event-state-sync
complexity: medium
mode: confirm
status: pending
depends_on:
  - notice-and-mute-api
  - frontend-pulse-card-state
created: 2026-11-04
---

# Work Item: Told once, calmly, where they already are — the strip and the banner

## Description

FR-54 asks for an "in-app banner". FR-10's design removed the topbar Notifications button and said why: `onboarding-skip-all-state-desktop.html`'s header states the button "is removed entirely… per PRD FR-10 there is no in-app notifications inbox."

Decided during capture (2026-11-04): honour both. A **dismissible strip** at the top of the digest home listing unseen state changes, and a **persistent banner** on the affected Event Detail screen. No inbox, no bell, no badge count.

This is the in-app half of the notice, plus FR-55's mute control and FR-54's sold-out CTA removal.

## Acceptance Criteria

- [ ] A **dismissible strip** on the digest home showing unseen notices, in the calm register — `component.emptystate.quiet`'s weight, not an alert banner's. Dismissing calls the API; it is not client-only state.
- [ ] A **persistent banner** on the Detail screen of an affected event, stating the change and what happened to the user's reminders.
- [ ] A **mute control** on the Detail screen (FR-55), with a legible off state so a user can tell they have muted it.
- [ ] When an event is **sold out**, the Detail screen **removes the "Save Reminder" CTA** — FR-54 names this consequence explicitly.
- [ ] The strip is **not an inbox**: no history, no paging, no count badge, nothing persisting after dismissal.
- [ ] The strip **does not displace the digest** or push the first Pulse Card below the fold on a phone — the digest is the screen's purpose and the strip is an aside.
- [ ] With **no unseen notices** — the ordinary case — the home screen renders exactly as it does today, with no layout shift and no extra request on the critical path if the digest response can carry the flag.
- [ ] `axe-core` **zero serious violations** on both surfaces; the strip is announced to assistive technology without stealing focus.
- [ ] Mobile layouts hold.
- [ ] Tests: strip renders and dismisses; dismissal survives reload; banner renders per kind; mute hides the banner and suppresses the strip entry; sold-out removes the CTA; the empty case.

## Technical Notes

The shell and topbar are `frontend/components/shell/` and `brand-topbar.tsx` — the topbar is where a bell would go and deliberately does not have one; this item must not add it.

`digest-header.tsx` is the likely attachment point for the strip. The Detail screen's existing sold-out block (`frontend/app/events/[id]/page.tsx:402-407`) is where the banner and the CTA removal belong, and `detail-actions.tsx` already receives `soldOut` (`page.tsx:463`), so the CTA logic has a home already.

**Register matters more than usual here.** Everything the user is being told is bad news about plans they made, delivered by a product whose positioning is calm. EXPERIENCE.md §5 is canonical and stricter than both DESIGN.md and the mockups — the empty-state precedent, where a terracotta primary button in the mockup was ruled a mockup bug, is the standard to read this against.
