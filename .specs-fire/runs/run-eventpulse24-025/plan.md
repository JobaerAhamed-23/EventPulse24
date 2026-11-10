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

---

---
run: run-eventpulse24-025
work_item: digest-card-state-fields
intent: event-state-sync
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at: pending
---

# Implementation Plan: The digest state fields

## Approach

Give `DigestCardOut` the two facts the Pulse Card needs to say an event is not what it was:
the event's **lifecycle status** and its **sold-out** flag.

**The state is read at read time, not stored on the composition.** Three things in the code
already settle this, and all three point the same way:

1. **`DigestComposition` cannot hold it.** It is append-only with
   `append_only_mutable = frozenset()` — *"Nothing about a composition becomes known after it
   is written."* A status stored there would have to be written at composition time, and an
   event cancelled at noon would keep showing as live until tomorrow's digest.
2. **AD-10 says the composition explains *why*, not *what*.** The card's bucket, tags and
   badge are the persisted explanation — a fact about the user's day. The event's lifecycle
   status is not an explanation; it is a **live** fact about the event, and the card already
   carries two of those: `tz_review_pending` and `conflict`.
3. **The read already joins the catalog's current facts.** `_public_display_facts` calls
   `get_public_events` — one batched lookup — and `_card_for_public` already joins the card to
   that `PublicEvent`. The status is *already on the object*; the card simply does not hand it
   over.

So this is a plumbing change, not a new read and not a new store.

**`is_sold_out` is the one field that has to travel.** `PublicEvent` carries `status` but not
`is_sold_out`; `PublicEventDetail` carries both. Adding it to `PublicEvent` is the same
one-line change `PublicEventDetail` already made, in the same module, for the same reason.

### The one question this item does not get to decide alone

FR-55 says *"event is removed from the digest"*, and `saved-event-lifecycle-state` settled it
at the **candidate** stage: `digest_candidates.py:336` drops a save the catalog says is
cancelled, before it can become a candidate.

**So a cancelled event never enters a composition at all.** A *newly* cancelled event is
never a card. But a card composed *before* the cancellation is still on the digest — and that
is the case this item's third acceptance criterion is about. The card must then say
`status="cancelled"`, because the alternative — the card silently disappearing from a
composed digest — is a *different* removal than FR-55's, and it would break AD-10's rule that
the digest is served as stored.

**Both agree.** FR-55's removal happens at the door (a cancelled event is not a candidate);
this item's card marks what is already on the digest. A card that says "Cancelled" is the
truth about a composed row; the next day's composition will not contain the event at all.

### The vocabulary

The backend's own words, unchanged: `EventStatus` is `scheduled` / `postponed` / `cancelled`
/ `superseded`, and `is_sold_out` is **separate** from the status. No new "state" enum that
collapses the two — the acceptance criterion forbids it, and the Detail Screen's
`EventDetailFactsOut` already sets the precedent with the same two fields.

**A personal card has neither.** A personal event is the user's own agenda row: it is not
cancelled by a source and it is not sold out. Both fields are absent rather than
defaulted-to-something-false, so a client cannot mistake "no source, so no lifecycle" for
"a live event that happens to be fine".

## Files to Create

| File | Purpose |
|------|---------|
| (none) | — |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/ingestion/services/catalog_read.py` | `PublicEvent` gains `is_sold_out`; `_to_public_event` fills it |
| `backend/apps/personalization/services/digest_read.py` | `DigestCard` gains `status` and `is_sold_out`; `_card_for_public` fills them; `_card_for_personal` leaves them `None` |
| `backend/apps/personalization/schemas.py` | `DigestCardOut` gains `status` and `is_sold_out` |
| `backend/apps/personalization/api.py` | The endpoint passes the two through |
| `frontend/lib/api/openapi.json` | Regenerated |
| `frontend/lib/api/schema.ts` | Regenerated |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/personalization/test_digest_read.py` | A live card, a sold-out card, a postponed card, a cancelled card; a personal card carries neither |
| `backend/tests/personalization/test_digest_api.py` | The wire shape: the two fields are on the card |
| `backend/tests/ingestion/test_catalog_read.py` | `PublicEvent` carries `is_sold_out` |
| `backend/tests/api/test_contract.py` | The OpenAPI schema matches the committed client |

## Technical Details

### 1. `PublicEvent.is_sold_out`

```python
@dataclass(frozen=True)
class PublicEvent:
    ...
    status: str
    is_sold_out: bool
```

`PublicEventDetail` already carries it (`catalog_read.py:472`), set from `event.is_sold_out`.
The same field on `PublicEvent` is the same fact about the same event, and `PublicEventDetail`
is a *different* wire shape for a different surface — the docstring on
`PublicEventCandidate` says exactly this about widening a shape: *"Widening `PublicEvent`
would put digest-only fields on the public catalog's contract."* `is_sold_out` is **not**
digest-only — it is already on the public contract, via `PublicEventDetail` and
`apps/catalog/schemas.py`. So this is not widening; it is making the existing fact reachable
from the one read that lacked it.

**It is a required field, not a default.** `PublicEvent` has no defaults on any field today;
adding `= False` would let a new construction site forget it silently.

### 2. `DigestCard.status` and `DigestCard.is_sold_out`

Both `str | None` — `None` for a personal card, because "not applicable" and "scheduled" are
different facts and the client must be able to tell them apart. The alternative, defaulting
to `"scheduled"` for a personal card, would claim the catalog had an opinion about a row it
has never seen.

### 3. `_card_for_public` fills them; `_card_for_personal` does not

`_card_for_public` already receives the joined `PublicEvent`. It hands over `public.status`
and `public.is_sold_out`. When `public is None` — the event is gone from the catalog — both
are `None`, because there is no catalog to have an opinion. The card already says
`catalog_event_missing=True` in that case, and this does not contradict it.

### 4. The `superseded` case

`get_public_events` excludes superseded events (`_public_events`:
`.exclude(status=Event.Status.SUPERSEDED)`), so a superseded event is simply **absent** — the
card carries `catalog_event_missing=True` and `status=None`. That is the existing behaviour
and this item does not change it. A superseded event is not "cancelled"; it is gone, and the
card says so the way it already does.

### 5. What this item does **not** do

- **It does not remove a cancelled card from a composed digest.** FR-55's removal is at the
  candidate stage and already shipped. This item makes a card that is *already composed* tell
  the truth. Removing it at read time would contradict AD-10 ("digest rows are served as
  stored and never recomputed at render") and would make the digest flicker.
- **It does not touch the frontend.** The Pulse Card's *rendering* is
  `frontend-pulse-card-state`'s work. This item gives the API the facts.
- **It does not re-evaluate conflicts.** FR-55's conflict re-evaluation is propagation's, and
  propagation shipped in the previous item.

## Based on Design Doc

None. This is a `confirm`-mode item: no design doc, one checkpoint — this plan.

---
*Plan awaiting approval.*
