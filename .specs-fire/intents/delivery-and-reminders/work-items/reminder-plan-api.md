---
id: reminder-plan-api
title: The Reminder Plan API — filling an empty router
intent: delivery-and-reminders
complexity: medium
mode: confirm
status: completed
depends_on:
  - send-minting-and-rescheduling
created: 2026-10-31
run_id: run-eventpulse24-023
completed_at: 2026-11-01T04:17:53.625Z
---

# Work Item: The Reminder Plan API — filling an empty router

## Description

`delivery`'s first endpoints. `apps/delivery/api.py` is three lines — `router = Router()` and nothing else — and it is not mounted in `config/api.py`. The service layer beneath it has been complete since run 019.

Read and write one event's Reminder Plan, for both target kinds, with the plan's **pending sends minted, rewritten or cancelled in the same transaction** as the plan itself. A plan saved without its sends changing is a plan that does nothing, which is the state the product has been in.

## Acceptance Criteria

- [ ] `router` mounted in `config/api.py` under `/api/reminders`, authenticated with `current_user` like `personalization`'s router.
- [ ] `GET` one event's plan: the slots, the target kind, and **for each slot the computed delivery time** — because the picker has to dim a chip whose delivery falls inside Quiet Hours and cannot compute that itself.
- [ ] Each slot's returned delivery time is the **post-Quiet-Hours** instant, with a flag saying whether it was deferred and the window end it was deferred to, so the UI can render "Will deliver at {end of quiet hours}." without reimplementing the shift.
- [ ] `PUT` the plan: 0–4 slots, validated against `ReminderSlot` plus at most one custom slot. **0 slots is a valid save**, not a delete and not an error.
- [ ] The write goes through `services/reminder_plans.set_plan_slots` and the minting service **in one transaction**. A plan change that fails to reschedule rolls back the plan too — tested by forcing the second half to fail.
- [ ] **Ownership is enforced**: a caller can only read or write their own plan, another user's target is a 404 not a 403 (no existence leak), and an anonymous caller gets 401.
- [ ] A target that does not exist, or a saved event the user has since un-saved, returns the shared `{code, message}` error shape — the same envelope `catalog` uses.
- [ ] A custom slot's offset is validated as a sane interval and cannot be negative (a reminder after the event) — the bound is stated in the endpoint description.
- [ ] **AD-3 holds**: `delivery` does not import `apps.ingestion.models` to name the event. A catalog title comes through the published read service, as `conflict-list-api` already does.
- [ ] Pydantic schemas and the regenerated client via `make client`; no hand-written types (AD-19); CI's diff check passes.
- [ ] Tests: both target kinds; 0, 1 and 4 slots; 5 slots rejected; the custom slot; ownership in both directions; the deferred-slot flag; the rollback; the query count bounded and independent of slot count.

## Technical Notes

Returning the computed delivery time per slot is what keeps the Quiet Hours rule in one place. The alternative — shipping the window to the browser and computing there — would put a second implementation of the shift in TypeScript, where DST and midnight-crossing would be rediscovered and got wrong differently. The server already knows; let it say.

## Dependencies

- send-minting-and-rescheduling
