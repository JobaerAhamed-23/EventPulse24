---
id: frontend-pro-quiet-hours
title: Per-weekday quiet hours in settings
intent: pro-tier-and-monetization
complexity: medium
mode: confirm
status: pending
depends_on: [quiet-hours-pro-api]
created: 2026-11-11
---

# Work Item: Per-weekday quiet hours in settings

## Description

`frontend/app/settings/quiet-hours/page.tsx` and
`frontend/components/settings/quiet-hours-window.tsx` already exist and edit one window. The
Pro variant is designed — `settings-quiet-hours-pro-desktop.html`, which DESIGN.md backs with
an explicit `component.control.day-picker`. This item extends the existing surface to seven
windows for Pro users without disturbing the Free one.

## Acceptance Criteria

- [ ] A Pro user sets **seven distinct windows, one per weekday**, from the existing settings
      route, following `settings-quiet-hours-pro-desktop.html` and reusing
      `component.control.day-picker`.
- [ ] A **Free user's screen is unchanged** — one window, same controls, same behaviour. A
      test asserts this, because an unnoticed regression here changes when real reminders
      arrive.
- [ ] The whole week saves in one request, matching `quiet-hours-pro-api`, so a partial week
      is never persisted.
- [ ] Turning quiet hours **off** remains possible and remains unambiguous — there is still
      one spelling of "off", and the UI cannot produce the `start == end` form the backend
      refuses with `InvalidQuietHoursWindowError`.
- [ ] A window **crossing midnight** is shown as such, so a user setting Friday 22:00–08:00
      can see it reaches into Saturday.
- [ ] A **Free user** is offered the Pro variant through the inline prompt from
      `frontend-upgrade-prompts`.
- [ ] A **lapsed Pro user** sees their seven stored windows, presented consistently with
      whatever `quiet-hours-pro-api` permits them to do.
- [ ] Existing tests for the single-window surface still pass unmodified wherever the
      behaviour has not deliberately changed.
- [ ] Works at mobile width, where seven windows are the real layout challenge.

## Technical Notes

Medium complexity. Extend `quiet-hours-window.tsx` rather than forking it — two components
that both render a window will drift, and the Free path is the one that already ships to
users.

Read `app/settings/quiet-hours/page.test.tsx` before changing anything; the existing tests
encode the current behaviour, and keeping them passing is the cheapest proof that Free users
are unaffected.

Mobile is the real constraint: seven start/end pairs do not fit the desktop layout at phone
width. The mockup is desktop-only, so the mobile treatment is a judgement call to raise at the
checkpoint.

Node 24 is required for the frontend test suite (`.nvmrc`); under Node 20 every Vitest file
fails in undici.

## Dependencies

- quiet-hours-pro-api
