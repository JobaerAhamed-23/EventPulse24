---
id: quiet-hours-pro-api
title: Seven windows over the wire
intent: pro-tier-and-monetization
complexity: medium
mode: confirm
status: pending
depends_on: [per-day-quiet-hours-domain-and-model]
created: 2026-11-11
---

# Work Item: Seven windows over the wire

## Description

The notification-preferences API currently reads and writes one quiet-hours window, because
that is all `NotificationPreference` held. With the weekly shape landed by
`per-day-quiet-hours-domain-and-model`, this item extends the API so a Pro user can set all
seven, and a Free user still sets one.

## Acceptance Criteria

- [ ] A Pro user can read and write seven windows in **one request**, so the server never
      observes a partially-updated week.
- [ ] A Free user reads and writes exactly one window, with the request and response shape
      for that case unchanged from today — existing clients keep working.
- [ ] A Free user attempting to set seven windows is refused with the calm inline
      `upgrade_hint` shape used elsewhere in this intent, not a bare validation error.
- [ ] **A lapsed Pro user can still read their seven stored windows.** Whether they may still
      write them follows the rule the design doc fixed in
      `per-day-quiet-hours-domain-and-model`, and the API matches it rather than inventing a
      second answer.
- [ ] `InvalidQuietHoursWindowError` still refuses `start == end` on every window, not just
      the first.
- [ ] Contract tests cover both shapes, and `frontend/lib/api/schema.ts` is regenerated.

## Technical Notes

Medium complexity. The risk here is not the endpoint; it is **shape drift** — ending up with
two parallel spellings of quiet hours in the API, one legacy and one weekly, that slowly
disagree. Prefer one representation that degenerates cleanly to the single-window case over
two endpoints or two schemas.

Follow the existing notification-preferences API built in the `delivery-and-reminders`
intent, and match its refusal conventions.

## Dependencies

- per-day-quiet-hours-domain-and-model
