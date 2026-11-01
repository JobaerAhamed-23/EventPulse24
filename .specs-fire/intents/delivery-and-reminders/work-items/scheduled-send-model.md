---
id: scheduled-send-model
title: SCHEDULED_SEND — the table AD-7 was written around
intent: delivery-and-reminders
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-10-31
run_id: run-eventpulse24-023
completed_at: 2026-10-31T13:43:03.075Z
---

# Work Item: SCHEDULED_SEND — the table AD-7 was written around

## Description

The `SCHEDULED_SEND` model: one row per intended send, carrying its due time, its status, and the idempotency key that makes at-least-once delivery safe.

AD-7 is built entirely around this table — the due-index sweep, the five key shapes, the `SKIP LOCKED` transition, "the schedule is never in the broker" — and **the table has never existed**. It appears in the repository only inside docstrings: `apps/delivery/__init__.py` and `services/reminder_plans.py` both name it as though it were there. Every other piece of the delivery story was built around a hole.

This is `validate` mode because the key is the whole design and it is **not recoverable after the fact**. A key derived from `due_at` looks correct until the first reschedule, at which point the recompute mints a second row and the user gets two of the same reminder. AD-7 states the rule — minted once at creation, stored under a unique constraint, never derived from `due_at` — and the design doc is where the five shapes, the status machine and the index are settled before any of it is written.

## Acceptance Criteria

- [ ] `ScheduledSend` in `apps/delivery/models.py`, in the `personal` schema, `retention_category` set, user held by value (`user_id`).
- [ ] **The send key is minted once at row creation**, stored in its own column under a **unique constraint**, and **never derived from `due_at`**. A test rewrites `due_at` and asserts the key is byte-identical.
- [ ] The key shapes follow AD-7's table exactly:
  - saved public event reminder — `user_id · event_reminder · event_id · slot · event_version`
  - personal event reminder — `user_id · personal_reminder · personal_event_id · slot · personal_event_revision`
  - state-change notice (FR-54) — `user_id · state_notice · state_change_id`
  - Pulse Digest email — `user_id · digest · local_date`
- [ ] **The `pulse_ping` shape is defined but never minted in MVP**, per the 2026-10-31 decision that the digest email *is* the Pulse Ping. The kind exists in the enum with a comment saying it is reserved for the Phase 2 push channel, so a later reader does not think it was forgotten.
- [ ] `event_version` and `personal_event_revision` in the key are the values **at minting**. A separate working `event_version` column may be re-stamped by AD-17 propagation; the key never is. Both are present and the distinction is tested.
- [ ] A **`(due_at, status)` index** that the sweep's query actually uses — proven by a test asserting the query plan, not by inspection.
- [ ] A status machine — at least `pending`, `sent`, `cancelled` — with the legal transitions named in one place. A `sent` row is terminal and is never rekeyed, re-timed or resurrected.
- [ ] The row records enough to send without a second lookup round trip per row: the kind, the target by value (`target_kind` + `target_id`, the `ReminderPlan` convention), the slot where one applies, and the stream.
- [ ] **`delivery` owns this table** (AD-16). No other app writes it; `apps.delivery.models` is imported only from `apps.delivery`, and the import-linter contract is extended to say so, as `models-delivery` already does for `ReminderPlan`.
- [ ] Migration applies cleanly against the existing `personal` schema and its grants.
- [ ] Tests: the unique constraint rejects a duplicate key; `due_at` rewrite preserves the key; every legal and illegal status transition; the index is used; two rows differing only by `event_version` both exist (the old key stays spent).

## Technical Notes

The reason the key must not come from `due_at` is worth stating in the model docstring in the house style, because it is the invariant everything else rests on: Quiet Hours, a timezone change, a delivery-time change and a plan edit **all rewrite `due_at` on `pending` rows**. If the key moved with it, each of those would mint a second send, and the user would get a duplicate for every preference change they ever made.

A lifecycle change is the opposite case and the asymmetry is deliberate: a moved event **bumps `event_version`, cancels the pending rows and mints new ones**, so the old key stays spent — which is exactly what lets a `1d` reminder already sent for the old date not block the `1d` reminder for the new one.

## Dependencies

(none)
