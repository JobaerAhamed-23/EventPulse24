---
id: notification-preferences-api
title: The preferences API — quiet hours, the default plan, and a delivery time
  that can change
intent: delivery-and-reminders
complexity: medium
mode: confirm
status: completed
depends_on:
  - notification-preferences
  - send-minting-and-rescheduling
created: 2026-10-31
run_id: run-eventpulse24-023
completed_at: 2026-11-01T05:18:39.557Z
---

# Work Item: The preferences API — quiet hours, the default plan, and a delivery time that can change

## Description

Read and write the settings the two `/settings/*` routes need: the Quiet Hours window, the default Reminder Plan, and — the one that has quietly been broken — the **digest delivery time**.

Delivery time is set once at onboarding step 3 through `PUT /api/personal/onboarding/digest-preference` and **can never be changed again**. There is no non-onboarding endpoint for it. A user who moves cities or decides 8am was wrong has no recourse.

Every write here **rewrites `due_at` on pending rows and never mints or re-keys** (AD-7). That is the whole reason the key is not derived from `due_at`, and this is the endpoint that proves it: a user can change their quiet hours ten times and still receive one reminder.

The surface spans two modules — the window and the default plan are `delivery`'s, the delivery time and zone are `personalization`'s. That is the accepted cost of the 2026-10-31 ownership decision, and the API hides it from the client rather than passing it on.

## Acceptance Criteria

- [ ] `GET` the notification settings: quiet-hours window, default reminder slots, delivery time and zone — **one call, one response**, assembled across the two modules through published services (AD-2).
- [ ] `PUT` the **quiet-hours window**: two local wall clocks, or null for "no quiet hours". A full-day window is rejected with a readable message.
- [ ] `PUT` the **default reminder plan**: 0–4 slots, the same validation as the per-event plan, reusing one validator rather than a second copy.
- [ ] `PUT` the **delivery time** (and zone), through `personalization`'s published command — closing the gap where it was writable only during onboarding. Onboarding's existing endpoint keeps working unchanged.
- [ ] **Every one of those writes rewrites `due_at` on the user's `pending` rows** and leaves keys, `sent` and `cancelled` rows untouched. Asserted by key equality and row count, not by inspection.
- [ ] Changing the **default plan does not retroactively change existing per-event plans.** It applies to future attachments only — tested explicitly, because the opposite is a plausible misreading that would silently rewrite a user's choices.
- [ ] The rewrite is **bounded and batched**: one pass over the user's pending rows, not one query per row, and the zone read once (AD-16's rare-path reasoning).
- [ ] Ownership: a caller reads and writes only their own settings; anonymous gets 401.
- [ ] Partial writes are atomic — a request that sets the window and the default plan either applies both or neither.
- [ ] Pydantic schemas and the regenerated client via `make client` (AD-19); CI's diff check passes.
- [ ] Tests: each write and its `due_at` rewrite; keys unchanged across ten successive changes; `sent` rows never touched; the default-plan non-retroactivity; the full-day rejection; atomicity; the query bound; ownership.

## Technical Notes

The delivery-time write is the one with a trap: it changes when **every future digest** is due, so the rewrite touches the `digest` rows as well as the reminders. A test should change the delivery time and assert tomorrow's digest row moved with it and kept its `user_id · digest · local_date` key.

## Dependencies

- notification-preferences
- send-minting-and-rescheduling
