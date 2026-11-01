---
id: delivery-sweep-and-send
title: The sweep — due rows out, mail sent, exactly once
intent: delivery-and-reminders
complexity: high
mode: validate
status: completed
depends_on:
  - scheduled-send-model
  - send-minting-and-rescheduling
created: 2026-10-31
run_id: run-eventpulse24-023
completed_at: 2026-10-31T14:50:36.892Z
---

# Work Item: The sweep — due rows out, mail sent, exactly once

## Description

The worker job that reads due `SCHEDULED_SEND` rows off the `(due_at, status)` index, claims each under `SELECT … FOR UPDATE SKIP LOCKED`, sends it through the existing `EmailPort`, and marks it `sent`.

**This is the first code in the project's history to send an email.** `ports/email.py` and `adapters/email/{smtp,memory}.py` have existed since the scaffold with no caller anywhere.

It hangs off the **existing** tick. `config/celery.py` sets `TICK_SECONDS = 60.0`, which already satisfies AD-7's "≤60s intervals" — there is no new beat entry, and `tick()` keeps its property of enqueueing without touching the database. The sweep is the enqueued job, mirroring `schedule_sources`, `schedule_calendars` and `schedule_digests` exactly.

`validate` mode because double-sending is the failure this whole architecture exists to prevent, and because "at-least-once with dedupe at the send boundary" has to be designed rather than hoped for.

## Acceptance Criteria

- [ ] A `sweep_due_sends` task enqueued by the existing `tick()`. **No new `beat_schedule` entry** — `tests/worker/test_tick.py` pins `TICK_SECONDS == 60.0` and the enqueue order, and both still pass.
- [ ] `tick()` still **touches no database**, so a slow sweep cannot delay the next tick.
- [ ] The sweep selects on the `(due_at, status)` index with a bounded batch size, claims with `SELECT … FOR UPDATE SKIP LOCKED`, and never holds a lock across the network call to the email provider.
- [ ] **Two concurrent workers never send the same row** — tested with real concurrency against the database, not by reasoning. The second worker's `SKIP LOCKED` skips what the first is holding.
- [ ] A worker that dies mid-send leaves a row that becomes **claimable again** after a TTL, the way `digest_claimed_at` and `sync_claimed_at` already work. The retry is safe because the send key is the provider's idempotency key.
- [ ] **The send key is passed to the provider as its idempotency key** (AD-7), so an at-least-once retry dedupes at the boundary. A `sent` row is never rekeyed.
- [ ] **Streams are correct and never shared** (AD-20): reminders and state notices go `TRANSACTIONAL`, the digest goes `BULK` with an unsubscribe URL. `EmailPort.send` already raises without one; a test asserts the bulk path supplies it.
- [ ] **The sweep never imports `domain.quiet_hours`.** A stored `due_at` is already the true send time (AD-7); re-checking at send time is the bug the rule exists to prevent. A test asserts the import is absent.
- [ ] A provider failure leaves the row `pending` for the next sweep, with a bounded attempt count; a row that exhausts its attempts is recorded, not retried forever and not silently dropped.
- [ ] A row whose target has since vanished is **cancelled, not sent**, and does not crash the batch. One bad row never stops the others.
- [ ] Structured logs carry `user_id`, the send key and the stream, and **never the recipient address** (AD-13). A test greps the log output for the address.
- [ ] Works fully offline with `ADAPTER_MODE=fake` against the memory adapter, which is the test seam for every assertion above.
- [ ] Tests: concurrency; crash-and-reclaim; provider failure and retry; idempotency at the boundary; both streams; the vanished target; the log redaction; the index actually used.

## Technical Notes

Do not hold the row lock across the provider call. The lock protects the claim, not the network. Claim-then-send-then-mark is the shape; the key is what makes the window between send and mark safe.

The memory adapter should record every send with its key and stream so the end-to-end proof can assert on them without a network. If it does not already, extending it is part of this item.

## Dependencies

- scheduled-send-model
- send-minting-and-rescheduling
