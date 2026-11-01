---
id: frontend-settings-reminders-and-quiet-hours
title: The first settings routes — defaults, and a window that means something
intent: delivery-and-reminders
complexity: medium
mode: confirm
status: completed
depends_on:
  - notification-preferences-api
created: 2026-10-31
run_id: run-eventpulse24-023
completed_at: 2026-11-01T08:24:19.664Z
---

# Work Item: The first settings routes — defaults, and a window that means something

## Description

`/settings/reminders` and `/settings/quiet-hours` — **the first `/settings/*` routes the product has ever had.** The frontend's ten routes include nothing under `/settings`, and the sidenav's Settings entry has had nowhere to go.

*Decided with the user 2026-10-31:* only these two. `/settings/sources` (FR-13/16) and `/settings/privacy` (FR-22/52) stay with the intents that own their backends, and no `/settings` index page is built in this intent.

`/settings/reminders` is the **Default Reminder Plan editor** — the surface that finishes FR-20 by turning a module constant into the user's own choice. `/settings/quiet-hours` is the window editor, Free tier's single window, defaulting to 10pm–8am.

## Acceptance Criteria

- [ ] Both routes render in the A-8 authed shell with **Settings** as the active sidenav item, and the sidenav's Settings entry becomes a **real link** rather than an inert label.
- [ ] The **topbar-quiet rule** holds (ASSUM-11): brand mark and tagline only. No action affordances in the topbar on either route. Inversions are bugs.
- [ ] **`/settings/reminders`**: the four default slot chips (5d / 2d / 1d / 1hr) with the same **ink-inversion** treatment as the per-event picker, reusing that component rather than a second copy.
- [ ] It says plainly that it sets the default for **newly saved events** and does not change plans already set — because the opposite is the natural assumption and getting it wrong silently rewrites the user's choices.
- [ ] **`/settings/quiet-hours`**: a window editor defaulting to **22:00–08:00**, with the locked label "10pm–8am. Nothing during this window."
- [ ] **Per-day-of-week windows are Pro (FR-51) and out of scope.** If a locked-row affordance is shown at all it is a calm, non-nagging one; no upsell carousel, no interstitial.
- [ ] The **delivery time** is editable here too — the gap where it was writable only during onboarding. It reuses the onboarding time-preset control rather than a new one.
- [ ] **Inline save** on change, with a spinner on the control being saved — not a page-level Save button (EXPERIENCE.md §2 state table).
- [ ] Failure microcopy is verbatim: `/settings/reminders` → "Couldn't save. We'll try again on your next change."; `/settings/quiet-hours` → "Couldn't save." The user's chosen state is kept, not reverted.
- [ ] Success is quiet — "Saved.", no celebration.
- [ ] A changed window or delivery time **visibly affects the per-event picker's dimmed chips** on the next visit, because the server recomputed. Covered by the end-to-end proof.
- [ ] Accessibility: real form controls, labelled, keyboard-reachable, with the terracotta focus ring; the time inputs are usable without a mouse; reduced motion renders instantly.
- [ ] Spacing stays on the DESIGN.md scale — `tests/spacing-scale.test.ts` passes.
- [ ] Reaches the API only through the generated client (AD-19).
- [ ] Tests: both routes' default, loading and error states; inline save success and failure including the kept-state behaviour; the non-retroactivity copy; the sidenav active state; keyboard navigation.

## Technical Notes

`settings-desktop.html` is the visual reference, but it was drawn carrying the Privacy section's amendment timeline and geo toggle (Amendments A-13/A-14) which belong to a later intent. Take the shell and the form vocabulary; leave those sections out of the markup entirely rather than hiding them with `display:none` — the same rule Amendment A-12 locked for pre-auth CTA leakage.

## Dependencies

- notification-preferences-api
