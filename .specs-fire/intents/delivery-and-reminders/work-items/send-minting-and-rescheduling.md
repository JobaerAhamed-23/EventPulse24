---
id: send-minting-and-rescheduling
title: Minting, rewriting and cancelling sends — the one writer
intent: delivery-and-reminders
complexity: high
mode: validate
status: completed
depends_on:
  - quiet-hours-domain
  - notification-preferences
  - scheduled-send-model
created: 2026-10-31
run_id: run-eventpulse24-023
completed_at: 2026-10-31T14:06:31.964Z
---

# Work Item: Minting, rewriting and cancelling sends — the one writer

## Description

The service that turns plans and preferences into `SCHEDULED_SEND` rows, and keeps them true as the world changes. It is the **only** writer of that table, and it is where AD-7's hardest rule is enforced: **Quiet Hours is applied when `due_at` is computed or recomputed — never as a skip at send time.**

Three kinds of change reach it, and they must behave differently:

1. **A plan or preference change** — the user edits slots, moves their quiet hours, changes zone or delivery time. This **rewrites `due_at` on `pending` rows in place**. No cancel, no re-mint, no new key. A user who fiddles with settings five times still gets one reminder.
2. **A lifecycle change** (AD-17) — the source moved, cancelled or superseded the event. This **cancels the pending rows, bumps `event_version` and mints new ones.** The old key stays spent.
3. **A disappearance** — the event is un-saved, the personal event deleted, the account closed. This **cancels** and mints nothing.

`validate` mode because the three paths look alike and are not, and because this is the seam `propagate_state_change` has been calling into since AD-17 shipped with nothing on the other side.

## Acceptance Criteria

- [ ] A published service in `apps/delivery/services/` that is the **sole writer** of `ScheduledSend`. Nothing else writes the table; a test asserts it.
- [ ] **Minting** from a Reminder Plan: each slot becomes one pending row at `event_start - REMINDER_SLOT_OFFSET[slot]`, shifted by `domain.quiet_hours`, keyed per AD-7. The offsets come from `shared.constants`, reused never redeclared (AD-16).
- [ ] **A plan of 0 slots mints nothing and is not an error.** A plan edited from 4 slots to 0 cancels four pending rows.
- [ ] **Quiet Hours is applied at compute time**, so a stored `due_at` is already the true send time. The sweep never re-checks it, and a test asserts the sweep does not import `domain.quiet_hours`.
- [ ] **A preference change rewrites `due_at` on `pending` rows only** and leaves keys, `sent` rows and `cancelled` rows untouched. Changing quiet hours twice produces no new rows — asserted by row count, not by inspection.
- [ ] **A lifecycle change cancels and re-mints**, bumping `event_version` so the new rows carry new keys. A `1d` reminder already `sent` for the old date **does not block** the `1d` reminder for the new date — the explicit AD-7 case, as its own test.
- [ ] Propagation is **per-user, versioned and idempotent** (AD-17): applied in one `personal` transaction keyed `(state_change_id, user_id)`, and **only if** the change's `event_version` exceeds the version already stored. A retried, partial or out-of-order run can neither double-apply nor let an older postponement overwrite a newer cancellation. Each is a test.
- [ ] A **past due time is not minted** — a 5d slot on an event three days away produces no row for that slot, rather than a row that fires immediately on the next sweep.
- [x] ~~`propagate_state_change` in `worker/tasks.py` is wired to this service~~ — **moved to the FR-53/54 intent** (design doc D8, decided with the user 2026-10-31). AD-17 marks `propagated_at` only once *every* owner has applied a change, and the `personalization` half (SAVED_EVENT snapshot + conflict re-evaluation) does not exist yet; wiring half of it would either churn the outbox forever or make the future consumer silently skip those changes. The behaviour table itself is still implemented and tested here — time moved → cancel + re-mint; cancelled/superseded → cancel; sold-out or detail changed → **keep sends**, re-stamp the version only — as a published service the next intent calls.
- [ ] Un-saving an event and deleting a personal event cancel their pending sends, through `remove_plans_for_targets`' existing path.
- [ ] Every write audits via `write_audit`, carrying the send key and `user_id` and **never an email address** (AD-13).
- [ ] Tests for all three paths, the idempotency key, the version guard in both directions, the 0-slot case, the past-due case, and the sold-out case that must *not* re-mint.

## Technical Notes

The thing most likely to go wrong is treating a preference change as a lifecycle change because both "recompute the time". They differ in exactly one respect — whether the key changes — and that difference is the whole reason AD-7 insists the key is not derived from `due_at`. Write the two entry points with names that cannot be confused, and do not give them a shared "recompute" helper that takes a boolean.

The zone needed for the Quiet Hours shift lives on `personalization`'s `DigestPreference`, read through its published interface. Read it **once per batch**, not once per row: this is the rare path by design (AD-16's reasoning for where the window lives), and a per-row read would undo that.

## Dependencies

- quiet-hours-domain
- notification-preferences
- scheduled-send-model
