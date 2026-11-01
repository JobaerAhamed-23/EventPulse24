---
id: e2e-proof-and-contract-tests
title: The proof — a quiet hour, a deferred reminder, a real send
intent: delivery-and-reminders
complexity: medium
mode: confirm
status: completed
depends_on:
  - delivery-sweep-and-send
  - pulse-ping-and-suppression
  - frontend-reminder-picker
  - frontend-settings-reminders-and-quiet-hours
created: 2026-10-31
run_id: run-eventpulse24-023
completed_at: 2026-11-01T08:46:47.705Z
---

# Work Item: The proof — a quiet hour, a deferred reminder, a real send

## Description

The end-to-end proof and the contract tests, in the style of the five intents before this one: a single run through the whole path, against the fake adapters, asserting on what actually left the system.

The claim this intent has to prove is narrow and checkable: **a user sets a quiet window, saves an event whose reminder would land inside it, and the mail arrives at the window's end — once, on the right stream, under the right key.** Every piece of AD-7 is exercised by that one sentence.

## Acceptance Criteria

- [ ] **The deferral proof**: sign up, set quiet hours to 22:00–08:00, save an event at Friday 23:30 with a 1hr slot, run the sweep, and assert the memory adapter received **exactly one** message, on the **TRANSACTIONAL** stream, with the expected send key, at **Saturday 08:00** in the user's zone. This is EXPERIENCE.md's own worked example, executed.
- [ ] **The Pulse Ping proof**: compose a digest for a user with qualifying events, run the sweep, assert **one** message on the **BULK** stream with an unsubscribe URL and the key `user_id · digest · local_date`.
- [ ] **The suppression proof**: a user with zero qualifying public events and zero personal events in the next 48 hours gets **no row minted and no message sent**; the suppression is recorded.
- [ ] **The personal-only proof**: the same user with one personal event **does** get the Ping, with a personal-only digest.
- [ ] **The reschedule proof**: change the quiet-hours window, assert pending `due_at` moved, keys are **byte-identical**, and no second row exists. Repeat ten times; still one row.
- [ ] **The propagation proof**: move the event's start through the AD-17 path, assert the old pending rows are cancelled, new ones minted with a bumped `event_version`, and a reminder already `sent` for the old date does not block the new one.
- [ ] **The unsubscribe proof**: one-click unsubscribe from a reminder cancels that event's pending reminders and leaves the Pulse Ping subscription **untouched** — FR-11's explicit requirement.
- [ ] **The idempotency proof**: run the sweep twice over the same due row and assert the provider saw one send, deduped at the boundary by the send key.
- [ ] **Contract tests**: the import-linter contracts still hold, including the extended `models-delivery` for `ScheduledSend`; `delivery` never imports `apps.ingestion.models` or `apps.personalization.models`.
- [ ] **`make client` is the contract**: the generated client is regenerated for every new endpoint and CI's diff check passes.
- [ ] The whole proof runs **fully offline** with `ADAPTER_MODE=fake` and no network.
- [ ] **Probe tests**: as run 021 did with its 27 probes, each major assertion is proven able to fail — break the quiet-hours shift, the key stability and the suppression rule in turn, and show the matching test goes red.
- [ ] Frontend end-to-end: set quiet hours in `/settings/quiet-hours`, open `/events/:id/reminders`, and see the affected chip rendered dim with its "Will deliver at …" tooltip — proving the server-computed flag reaches the UI.

## Technical Notes

Freeze the clock for the proof rather than sleeping; the sweep takes `now` as an argument everywhere else in this project (`_now()` in `worker/tasks.py`), and this is why.

The memory email adapter is the assertion surface. If it does not yet record stream and idempotency key per message, extending it belongs to `delivery-sweep-and-send`, not here — this item should be able to assert without changing the adapter.

## Dependencies

- delivery-sweep-and-send
- pulse-ping-and-suppression
- frontend-reminder-picker
- frontend-settings-reminders-and-quiet-hours
