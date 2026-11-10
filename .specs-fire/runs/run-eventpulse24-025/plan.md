---
run: run-eventpulse24-025
work_item: held-for-propagation-status
intent: event-state-sync
mode: validate
checkpoint: plan (Checkpoint 2 of 2)
approved_at: 2026-11-05
---

# Implementation Plan: The propagation hold

## Approach

Add a nullable `held_at` to `ScheduledSend`. Between the claim and the send, batch-read the catalog's current `event_version` for every event-bound row in the batch and hold the ones the catalog has moved past. The claim query gains `held_at IS NULL`; everything else in `delivery` keeps working untouched, because a held row is still `pending`.

Seven steps, smallest-blast-radius first: the column and its migration, then the guard, then the release, then the alarm.

## One correction to the approved design

The design doc says *"The `KEEP` path must re-time."* **That is wrong and the plan does not do it.**

`LIFECYCLE_SEND_BEHAVIOUR` maps only `sold_out` and `detail_changed` to `KEEP`, and `event_writes.py:5` records that a change of k kinds is k separate statements, each with its own `EventStateChange`. A time change is therefore always its own `time_moved` row, which is `REMINT`. **A `KEEP` change never moves the event**, so `due_at` is still correct and re-timing it would move a reminder that nothing moved.

Releasing a held `KEEP` row therefore just clears `held_at`. The row is past due, so the next sweep sends it slightly late — which is the right outcome for a reminder we paused for a few seconds to verify.

The design's risk row *"Release without re-timing → fires immediately at its old `due_at`"* described correct behaviour as a bug. Corrected here.

**The real risk in that neighbourhood is different**: a row held for hours because propagation was broken, then released, sends a "1 hour before" reminder after the event has already started. That is out of scope for this item — it is the alarm's job to prevent the long hold, and item 4's job to decide whether a release checks staleness against the event start. Recorded for item 4, not silently dropped.

## Files to Create

| File | Purpose |
|---|---|
| `backend/apps/delivery/migrations/0010_scheduledsend_held_at.py` | Additive nullable column (number confirmed against the directory at execution) |

## Files to Modify

| File | Changes |
|---|---|
| `backend/apps/delivery/models.py` | Add `held_at`, documented beside `claimed_at`, stating why the hold is not a status |
| `backend/apps/delivery/services/delivery_sweep.py` | `held_at IS NULL` in `claim_due_sends`; new `_hold_stale`; wire into `sweep_due_sends` between claim and send |
| `backend/apps/delivery/services/scheduled_sends.py` | `KEEP` branch clears `held_at` alongside the version re-stamp |
| `backend/shared/constants.py` | `HELD_SEND_ALARM_AFTER` |
| `backend/worker/tasks.py` | Surface the stuck-hold count on the existing tick |

## Tests

| Test File | Coverage |
|---|---|
| `backend/tests/delivery/test_delivery_sweep.py` | The guard: held vs sent, absent event, unguarded kinds, attempts, claim skip, read-after-commit, failed catalog read |
| `backend/tests/delivery/test_scheduled_sends.py` | Release on all three behaviours; no stranded row; `KEEP` leaves `due_at` alone |
| `backend/tests/delivery/test_models.py` *(or nearest existing)* | `TERMINAL_STATUSES` and the `sent_at` CHECK unchanged by the new column |

## Technical Details

### 1. The column

```python
held_at = models.DateTimeField(null=True, blank=True)
```

Null means not held. Documented beside `claimed_at`, which is the same idiom: a nullable timestamp that gates the claim and is cleared to release. The docstring records why this is not a `Status` member — the eight `status=PENDING` filters in `scheduled_sends.py` — so the next reader does not "fix" it.

`Status`, `TERMINAL_STATUSES` and the `sent_at` CHECK constraint are **unchanged**, and `models.py:287`'s docstring stays true as written.

### 2. The claim

One predicate in `claim_due_sends`:

```python
.filter(held_at__isnull=True)
```

The partial index (`WHERE status = 'pending'`) still serves the query; `held_at` is null for nearly every row.

### 3. The guard — `_hold_stale(send_ids, now) -> list[UUID]`

Runs in `sweep_due_sends` **after `claim_due_sends` returns** (its transaction already committed), so no row lock is held across the catalog read. Per AD-17: *"After claiming a row… a separate, non-transactional read."*

1. Load the claimed rows.
2. Partition on `event_version IS NOT NULL` — rows without it (personal reminders, digests) are never guarded and pass straight through.
3. One batched read: `catalog_read.get_public_events(event_ids={...})`, imported function-locally, matching `delivery_messages.py:226`.
4. Per guarded row:
   - **absent from the map** → hold (unpublished / `in_review` / superseded; cancelling is propagation's call, not the sweep's)
   - `catalog.event_version > row.event_version` → hold
   - otherwise → send
5. Holding sets `held_at = now` and clears `claimed_at`; `attempts` and `last_attempt_at` are **untouched**, because a hold is not a delivery attempt and must not count toward the bound that marks a row `failed`.
6. One audit row per hold, following the existing `claim_scheduled_send` shape.
7. Returns the ids still safe to send.

**`target_id` is the event id for an event-bound row** — confirmed at execution against `mint_for_plan`'s `SendTarget`; if it turns out not to be, the plan takes the event id from wherever that row stores it rather than inventing a column.

**A failed catalog read holds nothing and sends nothing.** The claims are released and the next tick retries. Sending unverified is the one outcome this item exists to prevent, so the degraded path degrades toward silence, not toward mail.

### 4. The release

`apply_lifecycle_change` already finds held rows, because they are still `pending` — that is the whole point of D1. Each behaviour then needs:

| Behaviour | Action | Change needed |
|---|---|---|
| `REMINT` | Cancels the stale row, mints a new one | **None** — the new row is born with `held_at = NULL` |
| `CANCEL` | Cancels the row | **None** — terminal; `held_at` is left as a forensic record |
| `KEEP` | Re-stamps `event_version` | **Clear `held_at`** (one line, `scheduled_sends.py:696-701`) |

That one line is the whole release path. It is small because D1 made it small.

### 5. The alarm

`HELD_SEND_ALARM_AFTER` in `shared/constants.py`, beside the other cadences and with the comment the file's conventions require. The existing 60s tick counts rows where `held_at < now - HELD_SEND_ALARM_AFTER` and logs a warning with the count — a count, never a user id or address (AD-13).

Until item 4 lands this count only grows, and that is correct and expected: not sending beats sending wrong. The alarm is what stops it being *silent*.

## Based on Design Doc

Reference: `.specs-fire/intents/event-state-sync/work-items/held-for-propagation-status-design.md` (Checkpoint 1 approved 2026-11-04), with the `KEEP` re-timing correction recorded above.

---
*Plan approved at checkpoint. Execution follows.*

---

---
run: run-eventpulse24-025
work_item: propagation-consumer
intent: event-state-sync
mode: validate
checkpoint: plan (Checkpoint 2 of 2)
approved_at: 2026-11-10
---

# Implementation Plan: AD-17's propagation consumer

## Approach

Build the caller between two finished halves. `ingestion` appends a versioned
`EventStateChange`; `personalization` and `delivery` each publish a version-gated service
that applies it. Nothing joined them until now.

**The consumer adds no state of its own.** Every service it calls is both version-gated and
version-storing, so the version on the row it applied to *is* the "this user is done" marker
AD-17 asks for — written in the same transaction as the work it describes, so it cannot
disagree with it. A retried partial run re-walks every saver; the ones already applied cost
one indexed read each and change nothing.

**The order is forced.** AD-3 forbids a transaction spanning `catalog` and `personal`, so the
gap between the halves is permanent and the only question is which inconsistency survives it.
Snapshot first: sends then carry an old version, and the sweep's AD-17 guard *holds* those rows
rather than sending them. The reverse order would leave a user whose reminders were re-minted
for the new time while their Timeline still showed the old one. The notice goes last, because
it describes a state both halves have made true.

**The personal side is not the same shape as the delivery side.** `SAVED_EVENT` stores a time
and a version; `SCHEDULED_SEND` stores a due time computed from them. So `sold_out` and
`detail_changed` change nothing the snapshot holds, and calling the snapshot updater for them
would re-run conflict detection for an overlap that cannot have moved. They still reach the
delivery side, because a held send needs its version re-stamped to be released.

**One task per state change, paging savers internally.** A task per user multiplies the
broker traffic by the saver count and buys nothing: the idempotency is in the services, not
the task boundary.

**A poisoned user is surfaced, not timed out.** `EventStateChange` is append-only with one
mutable column, so there is nowhere to keep an attempts counter. The loop continues past a
failing user, `propagated_at` stays NULL, and an alarm bounds the *silence*.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/worker/propagation.py` | The per-user loop, the per-kind dispatch, the alarm's count |
| `backend/tests/worker/test_propagation.py` | The orchestration: ordering, idempotency, paging, failure |
| `backend/tests/worker/test_propagation_tasks.py` | The task seam and the alarm |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/ingestion/services/outbox.py` | `StateChangeFacts` + `get_state_change` + `count_unpropagated_since`, published as plain data |
| `backend/worker/tasks.py` | Replace the stub; add `report_stuck_propagation` to the tick |
| `backend/shared/constants.py` | `PROPAGATION_ALARM_AFTER`, `LIFECYCLE_PERSONAL_BEHAVIOUR` |
| `backend/tests/ingestion/test_outbox.py` | The consumer's cases, replacing the placeholder's |
| `backend/tests/worker/test_scheduling_tasks.py` | The tick enqueues the new alarm |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/worker/test_propagation.py` | No savers; missing change; already propagated; per-kind dispatch; the times come from the change; ordering; idempotency; paging; a failing user; the backlog drains; the residual window; a stalled cursor |
| `backend/tests/worker/test_propagation_tasks.py` | The task's reporting; the alarm; both behaviour maps cover every kind |
| `backend/tests/ingestion/test_outbox.py` | The consumer marks a change nobody saved; a missing change is not an error |

## Technical Details

### No new table, no migration

D1 is the design's central claim and it removes the migration entirely. The `EventStateChange`
row gains nothing: no claim column, no attempts counter, no per-user cursor. `propagated_at`
was already there.

### The loop

`worker/propagation.py` holds plain functions; `tasks.py` keeps a thin `@shared_task` — the
shape `revalidate_public_pages` already uses, and testable without Celery.

One page of savers at a time (`SAVERS_PAGE`), keyset-paged on the UUIDv7 `id`. **Not offset**:
propagation runs while people are saving and unsaving the same event, and an offset page skips
a row whenever an earlier one is deleted between pages — a user silently missed by a change
that reached everyone else.

Each user is applied in one `personal` transaction, inside the service that owns it. They are
deliberately *not* wrapped in one transaction here: each service already makes its own write
atomic, and wrapping them would put a `personal` transaction around the catalog read
`delivery` needs — the shape AD-3 exists to forbid.

**A failing user's failure is logged and the loop continues.** The change stays unpropagated,
which is what surfaces it; the reconciler re-offers it, the healthy users no-op, and the broken
one is retried. `propagated_at` stays NULL because setting it would be a lie, and the lie is
worse: the reconciler would stop offering, and the user would be silently left on the old
state forever.

### The version comes from the change, not from the live event

`after` carries `start_utc` / `end_utc` for the kinds that moved them. Reading the live
`Event` instead would pair *this* change's version with *the latest* times, which is wrong
whenever several changes are in flight — the exact case `event_writes` creates by appending
one change per kind per poll.

### The hold's only exit

Every kind reaches the delivery side, including the two the personal side skips. A `sold_out`
or `detail_changed` moves nothing the snapshot stores, but it still bumps the catalog's
version — so the sweep's guard has already *held* this user's pending sends, and
`apply_lifecycle_change`'s `KEEP` branch clearing `held_at` is what releases them.

**The version handed to `apply_lifecycle_change` is the change's, not the target's.**
`resolve_target` reads it off the `SavedEvent` snapshot, and for those two kinds the snapshot
deliberately never moves — so the target would carry the *old* version, the lifecycle would
find nothing stale, and `held_at` would never be cleared. The hold's only exit would silently
stop working for exactly the two kinds that most often cause one.

### The alarm

`PROPAGATION_ALARM_AFTER` sits in `shared/constants.py` beside the other cadences, comfortably
longer than `OUTBOX_RECONCILE_AFTER` (5 minutes): a change outliving 30 minutes is failing
rather than merely waiting. `report_stuck_propagation` counts and reports — **counts only,
never a user id or an event title** (AD-13).

### The residual window, deferred here

`held-for-propagation-status` deferred AD-17's accepted residual window to this item, "where
the FR-54 notice that corrects the window is built and the seam exists". The seam exists now:
a send claimed before the change commits can still go out, and the notice is what tells the
user their reminder was for the old time.

## Based on Design Doc

Reference: `.specs-fire/intents/event-state-sync/work-items/propagation-consumer-design.md`
(Checkpoint 1 approved), with D1's "no per-user marker" proven rather than assumed — every
service called here is version-gated *and* version-storing.

---
*Plan approved at checkpoint. Execution follows.*
