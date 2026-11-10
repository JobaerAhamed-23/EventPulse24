---
id: propagation-consumer
title: The job that was always a stub — AD-17's propagation consumer
intent: event-state-sync
complexity: high
mode: validate
status: completed
depends_on:
  - saved-event-lifecycle-state
  - held-for-propagation-status
  - state-change-notice-model
created: 2026-11-04
run_id: run-eventpulse24-025
completed_at: 2026-11-10T06:26:57.512Z
---

# Work Item: The job that was always a stub — AD-17's propagation consumer

## Description

This is the item the intent exists for. `worker/tasks.py:159-167`:

```python
@shared_task(name="worker.tasks.propagate_state_change")
def propagate_state_change(state_change_id: str) -> None:
    """AD-17 placeholder consumer: no propagation into `personal` exists yet (FR-53-55).

    It deliberately leaves `propagated_at` NULL: marking the row would claim a propagation that
    never happened, and the real consumer would then skip it. The reconciler keeps re-offering
    it until that consumer arrives.
    """
```

Everything around it is finished. `ingestion` appends a versioned `EventStateChange` in the same transaction as the change (`event_writes.py:165`), the outbox enqueues on commit and the reconciler re-offers every five minutes (`OUTBOX_RECONCILE_AFTER`, `shared/constants.py:79`). `delivery.apply_lifecycle_change` is built and tested, and `LIFECYCLE_SEND_BEHAVIOUR` (`shared/constants.py:903-911`) maps all seven kinds. `personalization.update_saved_event_snapshot` (`saved_events.py:243`) is built and tested, version gate and conflict re-evaluation included — its docstring reads *"This is the service AD-17's propagation job calls."*

Two finished halves with no caller between them. This item is that caller.

**This item needs a design doc (Checkpoint 1) before any code.** It orchestrates two modules across a boundary AD-3 forbids a transaction from spanning, and its correctness is entirely in its ordering and its idempotency.

## Acceptance Criteria

- [ ] `propagate_state_change` reads the `EventStateChange`, resolves the affected users through the reverse read, and applies the change **per user, in one `personal` transaction each**, keyed `(state_change_id, user_id)`.
- [ ] The change applies **only if** its `event_version` exceeds the version stored on that user's `SavedEvent` — the gate already inside both published services, which the consumer must not duplicate or second-guess.
- [ ] It **writes nothing itself.** Every mutation goes through a published service: `delivery.apply_lifecycle_change`, `personalization`'s snapshot and cancellation services, and the notice service. AD-16 ownership holds; `import-linter` stays green.
- [ ] **No transaction spans `catalog` and `personal`** (AD-3). The sequence is ordered and idempotent instead, and the design states the order and what a crash between steps leaves behind.
- [ ] `mark_propagated` is called **only once every affected user is done**, so a partial run is re-offered by the reconciler rather than silently lost.
- [ ] All seven kinds are handled per `LIFECYCLE_SEND_BEHAVIOUR`: `time_moved`/`postponed`/`reinstated` re-mint, `cancelled`/`superseded` cancel and close pairs, `sold_out`/`detail_changed` re-stamp and keep.
- [ ] **Held rows are released.** A send held by the sweep guard is rewritten, re-minted or cancelled by this job — the hold's only exit.
- [ ] It **queues one FR-54 notice per affected user**, respecting the mute and the one-per-day cap.
- [ ] **Idempotent under every failure shape**, each with its own test: a full re-run is a no-op; a partial run retried completes; an older change arriving after a newer one changes nothing; two changes racing on one event leave the newer one's effect.
- [ ] A state change affecting **no users** marks propagated and does nothing else — the common case for an unsaved event, and it must not be an error or a slow path.
- [ ] **The backlog drains.** A test fixture of unpropagated rows from before this item is propagated by the reconciler without manual intervention.

## Technical Notes

**Design-doc decisions (Checkpoint 1):**

- **The order of the two modules.** Snapshot first or sends first. A crash between them must not leave a user with a correct snapshot and reminders for the old time, or vice versa — the design names which inconsistency is the survivable one, and the next tick's behaviour that repairs it.
- **Per-user keying and where it is recorded.** `(state_change_id, user_id)` needs a durable marker for "this user is done" or a partial run cannot resume without re-applying. Whether that is a table, a counter, or re-derivable from the version gate alone is the central design question of this item.
- **Fan-out bound.** A state change on a popular event may affect many users. One task per user, batched tasks, or one long task — weighed against the five-minute reconciler window, which will re-enqueue anything still unfinished and must not stampede.
- **What "every affected user is done" means when one user's apply permanently fails.** `propagated_at` must not be held NULL forever by a single poisoned row, and must not be set while a user is genuinely unpropagated. The design states the bound and what it surfaces.

**Existing patterns to follow:** `worker/tasks.py` already runs a 60s tick with an established `_enqueue` helper (`tasks.py:42`) and a sibling consumer worth reading first — `revalidate_public_pages` (`tasks.py:243`) and `reconcile_revalidation` (`tasks.py:298`) solve the same outbox-consumer shape for a different consumer, and `apps/ingestion/services/revalidation.py:16-18` explains exactly how the two outboxes differ.
