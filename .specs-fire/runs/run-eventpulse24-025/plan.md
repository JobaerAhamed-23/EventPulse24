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
