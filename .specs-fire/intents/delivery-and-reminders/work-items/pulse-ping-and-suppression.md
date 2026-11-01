---
id: pulse-ping-and-suppression
title: The Pulse Ping — one a day, and the silence that earns it
intent: delivery-and-reminders
complexity: medium
mode: confirm
status: completed
depends_on:
  - send-minting-and-rescheduling
  - email-templates-and-unsubscribe
created: 2026-10-31
run_id: run-eventpulse24-023
completed_at: 2026-11-01T02:59:41.421Z
---

# Work Item: The Pulse Ping — one a day, and the silence that earns it

## Description

Mint the daily digest send after composition, and enforce FR-10's suppression rule — the product's single most distinctive behaviour.

**The digest email is the Pulse Ping.** *Decided with the user 2026-10-31:* MVP is web-first and email-only (FR-9's Out of Scope: "Push notifications to mobile in MVP (email digest only)"), so one send per user per day carries the digest and is the Ping. AD-7's separate `pulse_ping` key stays reserved for the Phase 2 push channel and is not minted here. PRD SM-2 already measures the two as one thing.

`compose_digest_task` currently composes and stops — its docstring says the send belongs to this intent. This item is the other half: compose, then decide whether to send at all, then mint the `digest` row for the user's local delivery time.

The suppression rule is not a filter, it is the pitch. SM-C1 targets a suppression rate **≥30%** and counts a higher number as *better intelligence, not worse* — the only metric in the PRD that improves when the product does less. It has to be measurable, so suppression is recorded rather than merely happening.

## Acceptance Criteria

- [ ] After composition, a `digest`-kind `ScheduledSend` is minted for the user's **local delivery time**, keyed `user_id · digest · local_date` and **shifted by Quiet Hours** like any other send.
- [ ] **Exactly one row per user per local date.** The unique key makes a duplicated or retried composition job mint nothing the second time — the composition is already idempotent and the send must match it. Tested by running the job twice.
- [ ] **FR-10's four consequences, each its own test:**
  - 0 qualifying public events **and** 0 personal events in the next 48 hours → **no send minted at all** (not a minted row that is later skipped).
  - 1+ personal events with 0 public events → **send minted**, carrying a personal-only digest.
  - 3 qualifying events → **exactly one** send, not three.
  - The content is consistent for the user — one row, one key, so multi-device cannot double-deliver.
- [ ] The 48-hour window is evaluated in the **user's own zone**, not UTC, and the boundary is pinned by a test.
- [ ] The personal-events half of the rule honours `DigestPreference.include_personal_events` — a user who opted out of personal events in their digest is not kept subscribed by events they asked not to see.
- [ ] **Suppression is counted**, with the reason, so SM-C1's ≥30% target is measurable from day one. A structured log line at minimum; the shape is stated in the plan.
- [ ] The send goes on the **BULK** stream with the Pulse Ping unsubscribe URL (AD-20).
- [ ] A user who has unsubscribed from the Ping has **nothing minted**, and that is counted separately from a suppression — they are different facts about the product.
- [ ] The `pulse_ping` key kind exists in the enum, is **never minted**, and carries a comment saying it is reserved for Phase 2 push.
- [ ] Tests: all four consequences; the zone boundary; the opt-out; the unsubscribed user; double composition minting one row; the stream and unsubscribe URL.

## Technical Notes

"Qualifying" must mean the same thing here as it does to the composition service — do not write a second definition of what counts as a qualifying event. If the composition already knows its own card count and sources, read that rather than re-querying, and if it does not expose it, exposing it is part of this item.

Suppression deciding *not to mint* (rather than minting and skipping at send time) is deliberate and worth a docstring line: a row that exists but is never sent is indistinguishable from a bug, and AD-7's whole premise is that a `pending` row is a promise.

## Dependencies

- send-minting-and-rescheduling
- email-templates-and-unsubscribe
