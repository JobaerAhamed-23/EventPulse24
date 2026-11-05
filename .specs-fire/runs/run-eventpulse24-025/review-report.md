---
run: run-eventpulse24-025
work_item: held-for-propagation-status
intent: event-state-sync
created: 2026-11-05
---

# Code Review: run-eventpulse24-025

## Scope

| File | Action |
|---|---|
| `backend/apps/delivery/models.py` | modified — `held_at` |
| `backend/apps/delivery/migrations/0006_scheduledsend_held_at.py` | created |
| `backend/apps/delivery/services/delivery_sweep.py` | modified — claim filter, `_event_ids_to_check`, `hold_stale_sends`, `count_stuck_holds`, wiring |
| `backend/apps/delivery/services/scheduled_sends.py` | modified — `KEEP` release |
| `backend/shared/constants.py` | modified — `HELD_SEND_ALARM_AFTER` |
| `backend/worker/tasks.py` | modified — `report_held_sends`, tick |
| 4 test files | modified |

## Linters

`ruff check` clean · `ruff format` clean · `lint-imports` 19 kept / 0 broken · `manage.py check` no issues.

## Findings requiring a change — fixed

### 1. The guard silently shrank the sweep's counts (correctness)

`hold_stale_sends` built its result by iterating the rows it loaded. A row deleted between the
claim and the guard simply vanished from the batch.

Before this guard existed, **every** claimed id reached `send_one`, which reads the row, finds
it gone and counts it `cancelled`. Dropping it instead meant a send that disappeared stopped
being reported at all — smaller counts, nothing to say why.

Fixed by iterating `send_ids` and passing an unknown id straight through to `send_one`, which
already handles it. This also made the trailing re-sort unnecessary: iterating `send_ids`
preserves the claim's `due_at` ordering by construction.

Pinned by `test_a_row_deleted_between_the_claim_and_the_guard_stays_in_the_batch`, verified to
fail when the row is dropped instead.

### 2. The hold and its audit rows could diverge (robustness)

The bulk `update(held_at=...)` ran outside a transaction, with the audit rows written after. A
crash between them would leave rows held with no audit entry — a send that stopped with no
record of why, which is the hardest version of this failure to diagnose.

`claim_due_sends` already pairs its claim with its audit inside `transaction.atomic(using=PERSONAL)`.
The hold now does the same, matching the established pattern rather than inventing a weaker one.

Pinned by `test_a_hold_and_its_audit_row_commit_together`.

## Considered and deliberately not changed

| Observation | Why it stands |
|---|---|
| `write_audit` called in a loop (N inserts for N held rows) | `claim_due_sends` does exactly this for N claimed rows. Matching the existing pattern beats optimising one of a pair |
| Function-local import of `catalog_read` | Matches `delivery_messages._public_event_facts`, which imports it the same way to avoid an import cycle |
| No bound on the `IN` clause | The batch is already capped at `SEND_SWEEP_BATCH` (100) |
| Broad `except Exception` around the guard | Deliberate: the sweep must never send unverified, so any guard failure stops the tick. `exc_info=True` was added so a programming error is distinguishable from a catalog outage rather than silently looking like one |

## Security (AD-13)

- The hold path logs nothing. `report_held_sends` logs a **count** only — no user id, no address.
- `test_the_report_logs_a_count_and_never_a_user_or_address` asserts the user id does not appear
  in any record's fields and that no `@` reaches the message.
- No new external input, no new endpoint, no new credential.

## Architecture

- **AD-2 violation found and fixed during execution.** `worker.tasks` imported
  `apps.delivery.models` directly. Moved behind a published `count_stuck_holds` service — what
  that contract exists to force.
- **AD-3 holds.** The catalog read runs after the claim transaction commits; no transaction and
  no row lock spans the two schemas.
- **AD-16 holds.** `delivery` owns every write made here.
- **AD-7 untouched.** No send key is minted, derived or consumed by a hold.

## Outcome

2 findings, both fixed, both pinned by tests verified to fail without the fix. No findings
left pending.
