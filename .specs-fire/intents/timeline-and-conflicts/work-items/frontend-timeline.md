---
id: frontend-timeline
title: The Timeline screen — week on desktop, day on mobile
intent: timeline-and-conflicts
complexity: medium
mode: confirm
status: completed
depends_on:
  - timeline-week-api
created: 2026-10-31
run_id: run-eventpulse24-022
completed_at: 2026-10-31T08:52:55.146Z
---

# Work Item: The Timeline screen — week on desktop, day on mobile

## Description

`/timeline` (FR-32, `Surface.Timeline`, Flow 5): a read-only view of the week the `timeline-week-api` returns, in the app shell, matching `timeline-mobile.html` and the `Surface.Timeline` spec. The Timeline item in the sidenav and the bottom-tab becomes a real route.

## Acceptance Criteria

- [ ] **Desktop (`md+`)**: a 7-column grid (`layout.timeline.grid`), Mon–Sun, header row of weekday + date in `Text.Meta`, today's column marked with `Indicator.Today`; week navigator `←` / `Today` / `→` above it. The visible week lives in the URL (`?week=`), so reload, back and share keep it.
- [ ] **Mobile (`sm`)**: one day at a time with a centred `← {date} →` navigator and a "Today" pill; the day also lives in the URL.
- [ ] **Event-blocks**: 2px left stripe (`warm.personal` / `cool.public`) **and** a visible "Personal" / "Public event" label; name and local time; `Indicator.Conflict` (6px amber, `aria-label="Schedule conflict"`) when the API says so. Hover swaps to `surface.subtle`; no chevron.
- [ ] **Read-only routing**: a public block links to `/events/:id`; a personal block opens the existing **Edit personal event** sheet, and a saved edit refreshes the Timeline. Tapping an empty day does nothing.
- [ ] **States**: empty day "Quiet day." (`Text.Meta`, muted, centred); empty week "Your week is quiet. Pulse Digest is the place to discover." + one `Text.Meta` "Open Pulse Digest" link; week-row skeletons while loading; "Couldn't reach Timeline. Try again." with a retry on error.
- [ ] **Accessibility**: each block's accessible name is name + time + "Personal" / "Public event"; the terracotta focus ring; ≥44px targets; reduced motion renders instantly; axe passes.
- [ ] **Navigation**: Timeline becomes a real link in the sidenav and the bottom-tab, with the active-route ink pill and `aria-current="page"`; its "Coming soon" goes.
- [ ] Spacing on the DESIGN.md scale (the spacing test passes); terracotta only on sanctioned uses.
- [ ] Tests for both layouts, stripe-plus-label pairing, the indicator, routing per kind, every state, and the nav link.

## Technical Notes

The page is a server component reading through the generated client with the session headers, like `/`; the edit sheet is the existing `PersonalEventsPanel` island in `sheetsOnly` mode. Browser-zone vs event-zone display follows the card rule (`cardTime`): render deterministic text on the server.

## Dependencies

- timeline-week-api
