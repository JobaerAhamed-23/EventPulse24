---
id: frontend-reminder-picker
title: The reminder picker — four chips, and the one that dims
intent: delivery-and-reminders
complexity: medium
mode: confirm
status: completed
depends_on:
  - reminder-plan-api
created: 2026-10-31
run_id: run-eventpulse24-023
completed_at: 2026-11-01T05:45:47.304Z
---

# Work Item: The reminder picker — four chips, and the one that dims

## Description

`/events/:id/reminders` — the per-event Reminder Plan editor, reached from "Edit reminders" on the Event Detail screen.

*Decided with the user 2026-10-31:* a **full route**, not a sheet, matching Amendment A-21's `reminder-picker-desktop.html` — the A-8 shell with the 240px sidenav, the brand-only topbar, and the crumb `Digest · {event} · Edit reminders`. The IA table's 14 routes gain a 15th; that gets an amendment note rather than being left as a silent divergence.

The detail worth the care is the **Quiet Hours chip state**, which EXPERIENCE.md specifies with four worked examples: a chip whose resulting delivery time would land inside the user's window **dims to 40% opacity** and shows "Will deliver at {end of quiet hours}." — and **stays selectable**. Selecting it queues the deferred send. It is the clearest place in the product where the system explains itself instead of silently doing something surprising.

## Acceptance Criteria

- [ ] Route `/events/:id/reminders` in the A-8 shell, with the crumb `Digest · {event name} · Edit reminders` and **Digest** as the active sidenav item (the picker hangs off Digest in the IA, as Detail does).
- [ ] "Edit reminders" on the Event Detail screen routes here.
- [ ] Four slot chips — **5d / 2d / 1d / 1hr** — labelled "Remind me:" (locked microcopy).
- [ ] **Selection is ink inversion, never terracotta** (`component.input.reminder.slot`): selected is `color.ink.primary` fill with `color.ink.inverse` label; unselected is `color.ink.primary` on `color.surface.subtle`. A test asserts no accent token on this chip.
- [ ] **The Quiet Hours chip state**, driven by the API's per-slot deferred flag — never recomputed in the browser: dims to **40% opacity**, shows a `color.ink.meta` tooltip "Will deliver at {end of quiet hours}.", and **remains selectable**.
- [ ] EXPERIENCE.md's four worked examples are the tests, verbatim — including *Friday 11:30pm event + 1hr slot → "Will deliver at 8:00 am Saturday."*
- [ ] **One custom slot** can be added, with its own interval; a second is not offered. The server's bound is surfaced as an inline message, not a silent clamp.
- [ ] **Empty state**: no chips selected reads "No reminders. You'll still see this event in Pulse Digest." Saving 0 slots is a normal save with a calm confirmation, not a warning.
- [ ] The action bar: **Reset to default** (ghost) and **Save reminder plan** (primary).
- [ ] States: skeleton while loading; "Couldn't save. We'll try again on your next change." on a failed save, with the chosen state kept rather than reverted.
- [ ] Success is quiet — "Saved.", no emoji, no celebration (EXPERIENCE.md §3).
- [ ] Accessibility: chips are real controls reachable by keyboard, `aria-pressed` reflects selection, the dimmed state is conveyed by text and not by opacity alone, the tooltip is reachable without hover, and the focus ring is the terracotta stroke. Reduced motion renders instantly.
- [ ] Spacing stays on the DESIGN.md scale — `tests/spacing-scale.test.ts` passes.
- [ ] Reaches the API only through the generated client (AD-19).
- [ ] Out of scope, and deliberately absent from the mockup's three aside panels: the **Pro per-event quiet hours** upsell (FR-51) and the **"less like this"** explainer (FR-25). Both belong to later intents.
- [ ] Tests: chip rendering and selection; the dimmed state and its tooltip from the API flag; all four worked examples; the custom slot; 0-slot save; every loading and error state; keyboard and screen-reader behaviour.

## Technical Notes

The dimming must come from the server's per-slot deferred flag. Computing it in the browser would mean a second implementation of the Quiet Hours shift in TypeScript, with DST and the midnight-crossing window rediscovered there — the exact duplication `reminder-plan-api` returns the computed times to prevent.

## Dependencies

- reminder-plan-api
