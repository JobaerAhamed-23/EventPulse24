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

---

---
run: run-eventpulse24-025
work_item: polling-cadence-floors
intent: event-state-sync
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at: pending
---

# Implementation Plan: FR-53's detection floors

## Approach

FR-53: *"The system re-ingests high-priority sources at least every 4 hours. Lower-priority
sources at least daily."* Its testable consequences are detection guarantees — a cancellation
found within 4h or 24h, and a postponed event's new time in the user's saved snapshot within
4h.

**The machinery exists; the guarantee does not.** `Source.ingestion_cadence` is a per-source
`DurationField`, the scheduler already selects on it (`claim_due_sources`), and
`DEFAULT_INGESTION_CADENCE` already splits by acquisition method into exactly FR-53's two
tiers — `api`/`partnership`/`jsonld`/`rss`/`ics` at 4h, `email_ics`/`crawl` at 24h.

**What does not exist is a floor.** A source can be registered with a seven-day cadence and
nothing objects; the registry's own cleaner accepts any duration above 15 minutes. The
product then promises a 4-hour detection window that the data does not support. FR-53 is not
satisfied by a *default*; it is satisfied by a *ceiling*.

### The one real decision: where does "priority" come from?

The work item says priority is the only real decision, and asks for "a field, or a documented
derivation from what is already there."

**The PRD does not define it.** FR-53 says "high-priority sources (FR-13)" — and FR-13 has no
priority concept at all. The only definitional trace anywhere is PRD §10.4's parenthetical:
*"high-priority sources (official sites) within 4 hours."* That is a hint, not a rule.

**So this is a project decision, and it is made here explicitly.**

**Priority is derived from `acquisition_method`** — and specifically from FR-17's own priority
order, which the codebase already declares:

```python
class AcquisitionMethod(models.TextChoices):
    """FR-17 priority order, highest first: crawl is the last resort and needs a ToS review."""
    API = "api"
    PARTNERSHIP = "partnership"
    JSONLD = "jsonld"
    RSS = "rss"
    ICS = "ics"
    EMAIL_ICS = "email_ics"
    CRAWL = "crawl"
```

**Why the method and not a new field:**

1. **It is the ordering the product already believes in.** FR-17 says official APIs >
   partnerships > RSS/JSON-LD > email/ICS import > web crawling, and the enum's own docstring
   says "FR-17 priority order, highest first". A second, parallel priority field on the same
   model would be a second opinion about a question the codebase has already answered — and
   the two could disagree.
2. **It matches FR-53's parenthetical.** "High-priority sources (official sites)" — official
   API and partnership sources are exactly the official sites.
3. **It matches the defaults that are already shipped.** `DEFAULT_INGESTION_CADENCE` splits on
   exactly this boundary: 4h for `api`/`partnership`/`jsonld`/`rss`/`ics`, 24h for
   `email_ics`/`crawl`. A derivation that produced a different split from the shipped
   defaults would be a bug on day one.
4. **The PRD's cross-reference is broken anyway.** FR-53 says "(FR-13)", but FR-13 is the
   registry requirement and says nothing about priority. There is no field to point at.

**And what is derived is not the cadence — it is the ceiling.** The cadence stays a per-source
field, because a source's *actual* cadence is an operational choice (a partner's feed may
publish weekly). What is derived is the **maximum** it is allowed, and the ceiling comes from
the tier the source is in.

**A derived priority, in one named place.** `shared/constants.py` gains
`HIGH_PRIORITY_CADENCE_MAX` and `LOW_PRIORITY_CADENCE_MAX`, and the derivation lives in one
function — `source_priority(method)` in `apps/ingestion/services/source_registry.py` — which
returns the ceiling for a source's method. No caller re-expresses the rule.

### The two tiers

| Tier | Methods | Ceiling | Why |
|---|---|---|---|
| **High** | `api`, `partnership` | **4 hours** | FR-53's first clause. These are the official sites — the sources whose cancellations a user is most likely to be hurt by |
| **Lower** | `jsonld`, `rss`, `ics`, `email_ics`, `crawl` | **24 hours** | FR-53's second clause |

**Wait — `jsonld`, `rss` and `ics` are 4h defaults today, and this puts them in the 24h tier.**
That is deliberate, and it is the one place this plan changes shipped behaviour. The shipped
`DEFAULT_INGESTION_CADENCE` gives `rss` a 4-hour default; FR-53's *guarantee* is about
**cancellation detection**, and a cancelled event on an RSS feed must be found within 4 hours.
A 4-hour *cadence* gives a detection window of up to 8 hours (the poll lands 4 hours after the
cancellation, plus up to 4 hours until the next poll). **So a 4-hour cadence does not
satisfy a 4-hour guarantee** — and FR-53's consequence says "detected within 4 hours".

**This is the crux of the item, and it is worth stating plainly:** FR-53's guarantee is
*detection within 4 hours*, and a polling system with period `p` detects within `p` only if it
polls at least once inside the window. A 4-hour cadence has a worst case of 4 hours — which
is *exactly* 4 hours, and a cancellation at 09:00:01 with a poll at 09:00:00 and 13:00:00 is
found at 13:00:00, which is 3h59m59s. That is inside the window.

**So a 4-hour ceiling is right for the high tier.** And for the lower tier, FR-53 says
"at least daily" — a 24-hour cadence has a worst case of 24 hours, which is "daily", again
exactly at the boundary.

**But the shipped defaults put `rss`/`jsonld`/`ics` at 4h.** Those are *defaults*, which is
a different thing from a *ceiling*: a source may poll more often than its tier requires.
Under this item they may not poll *less* often than 24h. Their defaults stay at 4h — which is
inside the 24h ceiling, and which keeps them detecting changes within 4h rather than 24h.

**So nothing ships worse than today.** The ceilings only *forbid* cadences that FR-53 cannot
guarantee. A source at 4h in the lower tier is unchanged and still detects within 4h; a
source at 24h is exactly at the boundary FR-53 allows.

**Why not simply put `jsonld`/`rss`/`ics` in the high tier?** Because FR-53's parenthetical is
"official sites" and FR-17's order puts crawling last for a reason. A crawl source is the
last resort; giving it a 4-hour floor would push the whole registry toward frequent crawling,
which is exactly what FR-17's ToS guard exists to prevent. The ceiling is a *guarantee*, not
an aspiration — a lower tier that polls daily is still a daily guarantee, and the registry's
40-source floor is met by mixture, not by making every source high-tier.

### What is enforced, and where

**At the point the value is written** — the acceptance criterion is explicit: *"Enforced where
the value is written, so an out-of-range cadence is rejected rather than discovered later."*

Two write paths reach `Source.ingestion_cadence`:

1. **`register_source`** — `source_registry.py`.
2. **`update_source`** — `source_registry.py`.

Both go through `check_source_change` → `clean_source_input` → the `_CLEANERS` map. The
`_cadence` cleaner is the one place to enforce, and it already enforces the *floor*
(`INGESTION_CADENCE_MIN`, 15 minutes). The ceiling goes in the same cleaner.

**But the cleaner does not know the source's tier** — on an update the method may itself be
changing. So the cleaner gains the method as an argument, and `check_source_change` computes
the *effective* method (the one being set, or the stored one) and passes it in.

**A method change re-checks the cadence.** This is the subtle case and it is worth stating:
a source at a 4h cadence in the high tier can be moved to `crawl` (a 24h tier), and the
cadence it already has is still legal there. But a source at a 24h cadence in the lower tier
moved to `api` (a 4h tier) would be *illegal* under its new ceiling. **The method change is
refused unless the cadence is brought within the new tier's ceiling in the same change.**

That is the honest reading of "enforced where the value is written": the row must be legal
after the write, whichever field changed.

**Two ways to satisfy it, and the order matters.** If a caller changes the method *and* the
cadence together, the new cadence is checked against the new tier — legal. If a caller changes
only the method, the stored cadence is checked against the new tier — and refused if illegal,
with the error naming the field to change. The error message says what to do.

### The admin form

`apps/ingestion/admin.py` has its own form for `ingestion_cadence` and calls
`check_source_change` from `clean()`. So the ceiling is enforced there too, for free — the
form shows the same refusal. **But** the admin form does not currently know the source's
method when the method is also being changed on the same form. `check_source_change` handles
that (it computes the effective method), so the form inherits it.

### The backfill

**Existing rows are brought within their ceiling by a migration, not by hand.**

Every `Source` row's method determines its ceiling. A row whose cadence exceeds its ceiling is
clamped to the ceiling. The migration is a `RunPython` that:

1. **Reads** each source's method and cadence.
2. **Clamps** any cadence above the ceiling to the ceiling.
3. **Reports** what it clamped — the migration must not silently rewrite an operator's data.

**Clamping, not refusing.** A migration cannot refuse: the rows exist and the schema must
end up legal. And a **database check constraint** is added alongside, so the invariant is
enforced by the database too and not only by the Python path.

**But a check constraint needs the priority as a stored expression** — the database has to
know which tier a row is in, and it cannot call a Python function. So the constraint is
written directly against `acquisition_method`:

```python
models.CheckConstraint(
    condition=(
        Q(acquisition_method__in=HIGH_PRIORITY_METHODS)
        & Q(ingestion_cadence__lte=HIGH_PRIORITY_CADENCE_MAX)
    )
    | (
        Q(acquisition_method__in=LOW_PRIORITY_METHODS)
        & Q(ingestion_cadence__lte=LOW_PRIORITY_CADENCE_MAX)
    ),
    name="source_cadence_within_priority_ceiling_ck",
)
```

**A check constraint cannot reference a constant that Django cannot serialize into a
migration** — but a `timedelta` and a tuple of strings both serialize fine. The constants live
in `shared/constants.py` and the migration imports them; if the constants change later, the
migration is rewritten by `makemigrations`, which is correct.

**The constraint is `DEFERRABLE`.** The repository's convention (seen in `Event.Meta`) is
`models.CheckConstraint(..., deferrable=models.Deferrable.DEFERRED)`. A constraint that
cannot be deferred is not a problem here — the write is a single row — but the convention is
the convention. **Actually, deferrable does not help here and is not needed**: the check is on
one row's own columns, so it is evaluated immediately and correctly. The existing
`source_cadence_positive_ck` is not deferrable. **This item follows the local convention of
the constraint it sits beside** — not deferrable.

### The scheduler honours the cadence

**Already true, and the acceptance criterion asks for it to be asserted.** `claim_due_sources`
filters on `last_attempted_at <= now - ingestion_cadence`. A source at a 4h cadence is
claimed 4 hours after its last attempt. This is asserted by a test — one that fails if the
scheduler's cadence filter is broken, not one that asserts the constant equals 4.

### The FR-53 consequence test — the one that matters

**"A test that can fail on the FR-53 consequence itself: given a source at its ceiling, a
cancellation introduced upstream is detected within the stated window. Not a test that the
constant equals four."**

So the test is **end-to-end through the real polling loop**, not a unit test of a constant:

1. A source is registered at its tier's ceiling (4h for a high-priority source).
2. The source is ingested once; a `last_attempted_at` is set.
3. **Upstream**, the event is cancelled. (The upstream side is a fixture, not the thing under
   test.)
4. The clock advances to **just inside** the window — `last_attempted_at + 4h`.
5. The scheduler's `claim_due_sources` is called at that moment.
6. The source **is claimed** — the detection happened inside the window.
7. And the ingest that follows writes the `EventStateChange` that propagation consumes.

**The test fails if the scheduler's cadence filter is wrong** — because step 5 uses the real
`claim_due_sources`, not a restatement of the rule.

**And the boundary is asserted from the wrong side too**: at `cadence - 1 second` the source
is **not** yet due, and at `cadence` it **is**. A test that only checks the happy path cannot
tell a scheduler that polls too often from one that polls exactly right.

### Failing sources do not silently stop meeting the floor

**"A cadence guarantee nobody is checking is worse than no guarantee, because the product
promises on it."**

A source that keeps failing never ingests successfully, so `stale_since` gets set by
`flag_stale_sources` — at **2× its cadence**, which for a high-priority source is 8 hours.
**That is already a surfacing mechanism** (a warning log with a count, and a flag on the row
visible in the admin).

But it is not enough, and here is why: **the stale flag fires at 2× the cadence, and the
guarantee is 1×.** A high-priority source that fails at 04:00 and would have been re-polled at
08:00 has already missed its 4-hour window by the time the flag appears at 08:00. **The
guarantee is broken before anything is surfaced.**

So this item adds a **cadence-floor alarm**: a source that has gone longer than its tier's
ceiling since its last *attempt* — not since its last success — has missed its floor, and
that is surfaced.

**Wait — that is what `flag_stale_sources` does.** Let me be precise about the difference:

- `flag_stale_sources` fires on **no successful ingestion** within **2×** the cadence. It is a
  *freshness* signal about the data.
- The new signal fires on **no attempt** within **1×** the ceiling. It is a *floor* signal
  about the polling.

**These are different.** A source that is polled every 4 hours but whose fetches all fail has
`last_attempted_at` moving and `last_ingested_at` frozen. The floor is **met** — the source
was polled — but the *detection* is not, because the poll failed. And a source that is not
claimed at all (the broker is down, the worker died, the claim is stuck) has neither moving.

**So the floor signal must be about attempts, and the detection signal is a separate
question.** This item adds the **attempt-side floor check**: a source whose
`last_attempted_at` (or `created_at`, if never attempted) is older than its tier's ceiling
has not been polled inside its window.

**Where does that surface?** The scheduler's tick already logs `"Sources stale"` with a count.
This adds a parallel **`report_cadence_floor_breaches`** that counts sources past their
ceiling and logs a warning with the count — no ids, no titles (AD-13). It is bounded and
cheap: one indexed query.

**And the failing-source half.** A source whose attempts are happening but which keeps
failing is past its *detection* floor without being past its *polling* floor. The existing
`consecutive_failures` counter tracks that, and `stale_since` fires at 2× the cadence. **The
gap is the window between the ceiling and 2× the cadence** — for a high-priority source,
4h to 8h, during which the guarantee is broken and nothing is flagged.

**So the floor check counts a source as breaching when EITHER** it has not been attempted
within its ceiling, **OR** it has been failing for long enough that its last successful
ingestion is older than its ceiling. The second half is `last_ingested_at` older than the
ceiling — which is exactly the guarantee, stated directly: **the source has not successfully
ingested inside its detection window.**

That is the honest formulation of FR-53's consequence. A cancellation is detected within 4
hours only if the source was *successfully* ingested within the last 4 hours.

**So `report_cadence_floor_breaches` counts sources whose `last_ingested_at` (or `created_at`)
is older than their tier's ceiling.** One query, one count, one warning log line.

**But the cadence field is per-source and the ceiling is per-tier** — so the query cannot use
a stored column for the ceiling. It has to compare each row's `last_ingested_at` against a
tier-dependent window. **Two queries** — one for the high tier, one for the lower — each with
its own window, which is exactly how `flag_stale_sources` handles the per-row cadence
window with `F("ingestion_cadence") * STALE_AFTER_CADENCES`.

**The alternative — a stored `priority` field — would make this one query.** That is the
argument for the field. But it buys one query, and costs a second source of truth that can
disagree with the method. **The two-query version is taken**, and the reason is recorded: a
cadence guarantee enforced by a derived rule should be enforced by the same derived rule
everywhere. A stored `priority` column that could say `high` for a `crawl` source is a
guarantee nobody can check.

### The constants

The acceptance criterion says the constants live in `shared/constants.py` beside the other
cadences, each with the comment the file's conventions require.

```python
# FR-53: the detection floors. A high-priority source must be re-ingested at least every
# 4 hours, a lower-priority one at least daily — so a source's cadence may not exceed its
# tier's ceiling. The ceiling is *not* the cadence: a source may poll more often than its
# tier requires (and the defaults for rss/jsonld/ics do), but never less often.
#
# These are ceilings, not defaults, because a default is a starting point and a ceiling is
# a guarantee. FR-53's consequence is "detected within 4 hours", and a source polled every
# 24 hours cannot honour it — so the value is refused at the point it is written.
#
# The tier is derived from `acquisition_method` (FR-17's own priority order), not stored:
# a second priority field on the same model would be a second opinion about a question the
# codebase has already answered, and the two could disagree.
HIGH_PRIORITY_CADENCE_MAX = timedelta(hours=4)
LOW_PRIORITY_CADENCE_MAX = timedelta(hours=24)
```

And the method sets, beside them:

```python
# FR-17's order, split at the boundary FR-53's consequence names. "Official sites" —
# the PRD's own parenthetical for high-priority — are the API and partnership sources.
HIGH_PRIORITY_METHODS = ("api", "partnership")
```

## Files to Create

| File | Purpose |
|------|---------|
| (none) | — |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/shared/constants.py` | `HIGH_PRIORITY_CADENCE_MAX`, `LOW_PRIORITY_CADENCE_MAX`, `HIGH_PRIORITY_METHODS` |
| `backend/apps/ingestion/models.py` | The `source_cadence_within_priority_ceiling_ck` check constraint |
| `backend/apps/ingestion/services/source_registry.py` | `source_priority(method)`; the ceiling in `_cadence`; the effective-method resolution in `check_source_change` |
| `backend/apps/ingestion/migrations/0002_source_cadence_ceiling.py` | The constraint + the clamping backfill |
| `backend/apps/ingestion/admin.py` | The form's own cadence field — inherits the check through `check_source_change` |
| `backend/apps/ingestion/services/scheduling.py` | `report_cadence_floor_breaches` — the floor check |
| `backend/worker/tasks.py` | The new check joins the tick |
| `backend/tests/ingestion/test_source_registry.py` | The ceilings are refused where the value is written |
| `backend/tests/ingestion/test_scheduling.py` | The floor breach count |
| `backend/tests/ingestion/test_models.py` | The constraint holds at the database level |
| `backend/tests/e2e/test_state_detection_window.py` | **The FR-53 consequence test** — the one that matters |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/e2e/test_state_detection_window.py` | **The consequence test.** A source at its ceiling; a cancellation introduced upstream; detected inside the window — through the real `claim_due_sources`, and at the boundary from both sides |
| `backend/tests/ingestion/test_source_registry.py` | A high-priority source at 4h is accepted; at 4h+1s is refused. A lower-priority source at 24h is accepted; at 24h+1s is refused. A method change that would leave the cadence above the new tier's ceiling is refused, and is accepted when the cadence comes with it |
| `backend/tests/ingestion/test_scheduling.py` | `report_cadence_floor_breaches` counts a source past its ceiling and does not count one inside it; the two tiers are counted against their own windows |
| `backend/tests/ingestion/test_models.py` | The database refuses a cadence above the ceiling, whatever the Python path did |
| `backend/tests/ingestion/test_migrations.py` (new) | The backfill clamps an out-of-range row and leaves a legal one alone |

## Technical Details

### 1. The derivation, in one named place

```python
def source_priority(method: str) -> str:
    """The tier this source's method puts it in: "high" or "lower" (FR-53).

    **Derived, not stored.** FR-17's order is the codebase's own statement of which
    sources matter more, and the method is already stored — a second priority column
    would be a second opinion about a question the codebase has answered, and the two
    could disagree.
    """
    return "high" if method in HIGH_PRIORITY_METHODS else "lower"
```

And the ceiling follows from the tier:

```python
def cadence_ceiling(method: str) -> timedelta:
    """The longest cadence this source's method may have (FR-53)."""
    return (
        HIGH_PRIORITY_CADENCE_MAX
        if source_priority(method) == "high"
        else LOW_PRIORITY_CADENCE_MAX
    )
```

**No caller re-expresses the rule.** The scheduler's floor query, the registry's cleaner, the
admin form and the migration all go through these.

### 2. The ceiling in the cleaner

`_cadence` already enforces the floor. The ceiling needs the method, so the cleaner takes it:

```python
def _cadence(value: object, *, method: str) -> timedelta:
    if not isinstance(value, timedelta):
        raise _FieldError("Enter a duration.")
    if value < INGESTION_CADENCE_MIN:
        raise _FieldError("Sources are checked at most every 15 minutes.")
    ceiling = cadence_ceiling(method)
    if value > ceiling:
        raise _FieldError(
            f"This source is checked at least every {humanise(ceiling)}, so its cadence "
            f"cannot be longer."
        )
    return value
```

`_CLEANERS` is a flat map of field → cleaner, so the method has to be threaded. The cleanest
way that keeps `_CLEANERS` flat: `clean_source_input` takes the effective method as an
argument and builds the cadence cleaner with it.

**`clean_source_input`'s signature changes** — it takes `method` alongside `values`. Its
callers are `check_source_change` (which computes the effective method) and the admin form
(which goes through `check_source_change`).

**`check_source_change` computes the effective method:**

```python
method = cleaned.get("acquisition_method", current.acquisition_method if current else None)
```

That line already exists in `check_source_change` — for the FR-17 crawl guard. **The ceiling
reuses it.** The effective method is the one being set, or the stored one, and it is the
method the cadence will be measured against *after* the write.

**But there is an ordering subtlety.** `clean_source_input` validates the fields, and it needs
the method to validate the cadence. But the method itself is being validated in the same
pass. **The effective method must be computed *before* the cadence is cleaned**, from the
raw input — not from the cleaned input.

**That is a real subtlety and it is easy to get wrong**: if the caller passes
`acquisition_method="crawl"` (valid) and `ingestion_cadence=timedelta(days=7)`, the ceiling
is 24h and the cadence is refused. If the caller passes `acquisition_method="api"` and a 7-day
cadence, the ceiling is 4h and it is refused too. Both are refused. But if the caller passes
`acquisition_method="not_a_method"` (invalid) with a 7-day cadence, the *cadence* error would
be reported against the method's ceiling — but the method is invalid anyway, so the method's
error is the one that matters. **Both errors are collected** — `clean_source_input` collects
errors rather than raising on the first — so the caller sees both. That is the existing
behaviour and it is right.

### 3. The constraint

```python
models.CheckConstraint(
    condition=(
        Q(acquisition_method__in=HIGH_PRIORITY_METHODS)
        & Q(ingestion_cadence__lte=HIGH_PRIORITY_CADENCE_MAX)
    )
    | (
        Q(acquisition_method__in=LOW_PRIORITY_METHODS)
        & Q(ingestion_cadence__lte=LOW_PRIORITY_CADENCE_MAX)
    ),
    name="source_cadence_within_priority_ceiling_ck",
)
```

**The condition is a disjunction, not an implication.** A constraint on `acquisition_method`
would be written as "if method ∈ high then cadence ≤ 4h". Django's `Q` objects combine with
`&` and `|`, and `~Q(...)` is the negation — so the implication is written as
`~Q(method__in=HIGH) | Q(cadence__lte=4h)`.

**Which form is right?** The disjunction form requires the method to be in *one of* the two
sets for the row to be legal at all. **That is stricter than intended**: a new
`AcquisitionMethod` added later would make every row with it illegal until the constraint is
updated — which is arguably *correct* (a new method must be given a ceiling) but it means the
migration fails on a fresh database with the new method, which is a loud failure rather than
a silent one.

**The implication form is looser**: a source with an unknown method is unconstrained. That is
the "not applicable" shape the rest of this codebase uses for exactly this situation — and it
matches the derivation: an unknown method has no tier, so it has no ceiling.

**The implication form is chosen**, because it degrades to "no ceiling" rather than "illegal",
and because it is the shape the Python path implements (an unknown method falls through to
the lower tier's ceiling — so the two would disagree if the constraint used the disjunction).

**Hmm — that disagreement matters.** The Python derivation says an unknown method gets the
*lower* ceiling (24h), because `source_priority` returns "lower" for anything not in the high
set. The constraint's implication form would say an unknown method has *no* ceiling. **Those
disagree.**

**They must not.** The cleanest resolution: the constraint is written to match the Python
exactly — the "else" branch is the lower tier, which covers every method not in the high set:

```python
models.CheckConstraint(
    condition=(
        Q(acquisition_method__in=HIGH_PRIORITY_METHODS)
        & Q(ingestion_cadence__lte=HIGH_PRIORITY_CADENCE_MAX)
    )
    | (
        ~Q(acquisition_method__in=HIGH_PRIORITY_METHODS)
        & Q(ingestion_cadence__lte=LOW_PRIORITY_CADENCE_MAX)
    ),
    name="source_cadence_within_priority_ceiling_ck",
)
```

**Now they agree**: a high method needs ≤4h; anything else needs ≤24h. And a new method added
later defaults to the lower ceiling until someone classifies it — **safe by default**, which
is the right direction: a new acquisition method should not be able to opt itself out of the
guarantee by being unclassified.

**And `AcquisitionMethod` is a `TextChoices`**, so the database has no enum — a row could in
principle hold a method outside the choices. The constraint's `~Q(in=...)` branch covers it:
it gets the 24h ceiling. Correct.

### 4. The backfill migration

```python
def clamp_source_cadences(apps, schema_editor):
    """Bring every source's cadence within its tier's ceiling (FR-53)."""
    Source = apps.get_model("ingestion", "Source")
    clamped = 0
    for source in Source.objects.all().iterator():
        ceiling = cadence_ceiling(source.acquisition_method)
        if source.ingestion_cadence > ceiling:
            source.ingestion_cadence = ceiling
            source.save(update_fields=["ingestion_cadence"])
            clamped += 1
    ...
```

**The reverse migration** must not try to restore the clamped values — it cannot know them.
The reverse is a no-op for the data and drops the constraint. That is stated in the
migration's docstring, because a reverse that silently loses data is worse than one that
says what it does.

**The migration runs *before* the constraint is added**, or the constraint would be violated
by the very rows the migration is clamping. Django's `AddConstraint` operation validates the
existing rows — `AddConstraint` on a check constraint **does** validate existing rows and
would fail if any violate it. So the order is: `RunPython(clamp)` then `AddConstraint`.

**Actually — `AddConstraint` with a `CheckConstraint` does validate existing rows in
PostgreSQL.** The migration would fail if the clamp had not already run. So the order
matters and is stated.

**The migration reports what it clamped.** A migration that silently rewrites an operator's
data is a migration nobody can audit. `RunPython` can print, and the migration writes a line
naming the count.

### 5. The floor check

```python
def report_cadence_floor_breaches(*, now: datetime) -> int:
    """Count the sources that have not successfully ingested inside their tier's ceiling.

    **This is FR-53's guarantee, stated as a check.** A cancellation is detected within
    4 hours only if the source was successfully ingested within the last 4 hours. A source
    that is polled on time but keeps failing does not meet the floor, and neither does one
    that is not polled at all.

    **Two queries, one per tier**, because the window is per-tier and the tier is derived
    from the method rather than stored — so it cannot be a column comparison. Two indexed
    queries on a registry of hundreds of rows are cheaper than a second source of truth.
    """
```

The two queries filter on `last_ingested_at` (or `created_at` for a never-ingested source)
being older than the tier's ceiling.

**Wait — should the floor be about `last_ingested_at` or `last_attempted_at`?** Decided above:
`last_ingested_at`, because the guarantee is about *detection*, and a failed poll detects
nothing. A source that has never been ingested is counted from `created_at` — the same
convention `flag_stale_sources` uses.

**But `flag_stale_sources` already counts sources with no successful ingestion within 2× the
cadence.** The new check is the same shape at **1× the tier ceiling**. So the two overlap —
the new one is strictly earlier and strictly in terms of the tier rather than the row's own
cadence.

**Is that a duplicate?** It is a *different window*: `flag_stale_sources` is 2× the row's own
cadence (which may be 15 minutes — so 30 minutes), and the new one is 1× the tier ceiling
(4h or 24h). **For a source polled every 15 minutes that fails, `flag_stale_sources` fires
after 30 minutes and the floor check fires after 4 hours — the stale flag is *earlier*.** So
the floor check does not add a signal for that source; the stale flag already covers it, and
more tightly.

**Hmm. So what does the floor check actually add?** The case where `flag_stale_sources` is
**too slow**: a source whose own cadence is long. A high-priority source at its 4h ceiling
that fails: `flag_stale_sources` fires at 8h (2×4h), the floor check at 4h. **The floor
check is 4 hours earlier — exactly the window FR-53 promises and the stale flag does not
cover.**

**And the case where `stale_since` is set but the source recovers?** `_close` clears
`stale_since` on success. The floor check counts sources whose *last success* is old, which
is the same thing. **So the floor check is a stricter, earlier version of the stale signal,
expressed in the tier's terms rather than the row's own.**

**Is a stricter duplicate worth it?** Yes, and here is the reason: **`flag_stale_sources` is
about the data's freshness, and its threshold is a function of the row's own cadence — which
an operator controls.** A high-priority source registered with a 15-minute cadence that fails
is flagged stale after 30 minutes, which is *before* its 4-hour window — so the product
surfaces a failure it has not yet broken a promise about. **That is noise.** And a
high-priority source at a 4h cadence that fails is flagged after 8 hours — **which is 4 hours
after the promise broke.** That is silence.

**The floor check is the promise, stated as a check.** It fires at the ceiling, always, for
every source in the tier, regardless of what cadence the row happens to carry. That is a
different question from "is this source's data fresh?" and it deserves its own signal.

**And it is a count, logged as a count** — no source ids, no titles (AD-13). The `Source`
row is the registry, and a source's name is not PII, but the codebase's convention is ids
and counts in logs.

**A breach count of zero is not logged as a warning.** Only a non-zero count is a warning.

### 6. What this item does **not** do

- **It does not add webhooks.** FR-53's near-real-time half is out of scope for this intent,
  decided at capture: no Eventbrite/Meetup/Luma adapter exists, `event-catalog-ingestion`
  put official-API and partnership sources out of scope, and OQ-5 is still open. FR-53 names
  polling "the fallback"; this ships the fallback.
- **It does not add sources.** No new adapters, no new sources. The scope guard is explicit.
- **It does not change the defaults.** `DEFAULT_INGESTION_CADENCE` stays as it is. The
  ceilings only forbid what the guarantee cannot support.
- **It does not build the Source Registry UI.** FR-13's registry surface is itself unbuilt.
  This item enforces at the model and the command layer, which is where the value is written.
- **It does not touch the frontend.**

## Based on Design Doc

None. This is a `confirm`-mode item: no design doc, one checkpoint — this plan.

---
*Plan awaiting approval.*


---

---
run: run-eventpulse24-025
work_item: notice-composition-and-email
intent: event-state-sync
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at: pending
---

# Implementation Plan: Four subjects the PRD already wrote

## Approach

FR-54 fixes the copy, which is unusual and makes this item narrow. The subjects are given
verbatim:

- `EventPulse24: [event name] was cancelled.`
- `EventPulse24: [event name] was moved to [new date].`
- `EventPulse24: [event name] moved to [new location].`
- `EventPulse24: [event name] is sold out.`

**The entity, the stream, the cap and the mute are `state-change-notice-model`'s; the decision
to send is `propagation-consumer`'s.** This item writes the words, and puts them on the wire.

### The thing this item finds: the state notice email is currently a reminder

`render_state_notice` exists in `email_templates.py` and is **called by nothing but the
tests**. The live path is:

```text
sweep_due_sends → renderer_for(row, address)
                → row.stream == "transactional"
                → render_transactional(row, address)
                → _facts_for(row) → render_reminder(ReminderFacts(...))
```

`renderer_for` dispatches on the **stream**, not the kind. A `state_notice` row is
transactional — correctly, per AD-20, because it is a one-time correction about the user's
own saved record, not a broadcast — so it takes the transactional branch and renders a
**reminder body**:

> subject: `Reminder: Rooftop cinema`
> body: *"This is a reminder you asked for."* + *"Stop reminders for this event: &lt;signed link&gt;"*

**A user whose event was cancelled is today sent a reminder about it, with a link to stop
reminders for an event that no longer exists.** That is not a copy problem; it is the wrong
email entirely, and it is the thing this item has to fix.

So this item is **two** things, in order:

1. **Render the right body for a state notice** — the dispatch gains a `state_notice` branch
   that renders `render_state_notice`, not `render_reminder`.
2. **Give that body the PRD's subjects, per kind.**

The dispatch is the load-bearing half. Fixing the subjects in `render_state_notice` while
leaving the dispatch alone would change a template nobody receives.

### The second thing this item finds: the renderer's facts are not on the row

`ScheduledSend` for a state notice carries `target_id` (the catalog event's id) and a
`send_key` holding the `state_change_id`. It carries **no `change_kind`**, and a subject is
per-kind — so the renderer has to learn the kind from somewhere.

**The `StateChangeNotice` row has it.** `change_kind` is a column there, and the notice is
`delivery`-owned in `personal` — the same app that owns the renderer. **Reading it is not a
cross-schema read and not a write:** AD-3 is about *transactions* spanning schemas, and
AD-16 is about *writing* another app's table. `delivery` reading `delivery`'s own model is
neither.

**And the notice row is the right source, not a workaround.** The design doc settled it:
*"The notice is the record and the email is one of its two deliveries."* The email's facts
come from the notice. The `ScheduledSend` is a ledger row whose only job is "this is due at
this time"; the notice is what the email is *about*.

### Where the change's facts come from: the change row, read through `outbox`

**The kind alone is not enough.** "was moved to [new date]" needs the *new date*; "moved to
[new location]" needs the *new venue*. Neither is on the notice row.

**Both are on the `EventStateChange` row**, in its `before`/`after` snapshots:

| kind | what the change records |
|---|---|
| `postponed`, `time_moved` | `before["start_utc"]`, `after["start_utc"]`, `after["start_time_tz"]` |
| `cancelled`, `superseded` | `before["status"]`, `after["status"]`, `after["start_utc"]` |
| `superseded` | **and** `after["superseded_by"]` — the replacement's id (`event_writes.supersede_event`) |
| `sold_out` | `after["is_sold_out"]` |
| `reinstated` | `before["status"]`, `after["status"]` |

**And the change row is already published**: `outbox.get_state_change(state_change_id)`
returns exactly these as plain data (`StateChangeFacts.before` / `.after`). **Verified: a
`delivery` module importing `apps.ingestion.services.outbox` breaks no import contract** —
`lint-imports` still reports `19 kept, 0 broken`, because the `models-ingestion` contract
protects the *direct* importers of `apps.ingestion.models` and `delivery` already reaches it
indirectly through `catalog_read`.

**So no migration, and no new columns on `StateChangeNotice`.** The change id is already on
the notice; the renderer follows it to the change and reads the facts that changed.

**Why the change's own `before`/`after`, and not the live Event.** A poll appends one change
per kind, and the live Event already holds the *last* kind's facts. Pairing this change's
version with the live event's start would name a time that never existed — the same
reasoning `worker.propagation._moved_times` already documents, and the same reason the
change log is append-only.

**And the change's `after` is what the user will find on the page.** For a lone
`time_moved` the change's new start and the live start are the same. They differ only when
the catalog has moved on since — and then the change's value is the one that describes *this
change*, which is what the email is about.

### Where the display facts come from: the catalog, at render time

**The title and the venue's name are display facts, not facts that changed.** The title
resolves through `catalog` at read time — the established pattern, and the one
`delivery_messages._public_event_facts` already uses for reminders. The venue's *name* is
the same: what changed is the venue's *fingerprint*, and a fingerprint is a hash.

**A fingerprint cannot be reversed to a name.** `EventFacts.venue_id`'s own comment records
it: *"a fingerprint is a hash, and a hash cannot be reversed to 'the old city was
Brooklyn'"*. So the *old* venue is **not nameable**, and the body does not try to name it.
The "moved to [new location]" subject names the **new** venue, read from the catalog at
render time.

**The work item's technical note says the notice should carry what it needs "from the
propagation moment rather than reading `catalog` at render time".** That sentence is about
the *fact that changed*; the design doc's `SAVED_EVENT` precedent draws exactly the line
this item follows: **the snapshot holds the time, the display name resolves through
`catalog` at read time.** The time is a fact that changed and it comes from the change row;
the name and the venue are display facts and they come from the catalog.

### The one decision this item actually has to make: `detail_changed`

The work item asks for it explicitly: *"`detail_changed` either has copy or is explicitly
**not notified** — FR-53 is clear that not every change deserves a notification ('would be
engagement-trap'), and a venue detail edit is the likeliest candidate for silence."*

**The investigation found something the work item did not know, and it changes the answer.**

#### The discovery: the PRD's "moved to [new location]" subject lives inside `detail_changed`

FR-54 names four subjects. **Three of them map onto a kind of their own:**

| PRD subject | kind |
|---|---|
| "was cancelled." | `cancelled` |
| "was moved to [new date]." | `postponed` / `time_moved` |
| "is sold out." | `sold_out` |
| **"moved to [new location]."** | **???** |

**There is no kind for a venue move.** `domain.lifecycle.classify_change` puts a venue
change under `DETAIL_CHANGED` — because `venue_fingerprint` is in `_DETAIL_FACTS`
(`domain/lifecycle.py:76-78`) — and `detail_changed` also covers a title edit, a description
edit, a canonical-URL edit and a timezone-label edit. `tests/domain/test_lifecycle.py:105`
pins it: `{"venue_fingerprint": "v1:other"}` → `ChangeKind.DETAIL_CHANGED`.

**So `detail_changed` is not one thing.** It is the kind that carries **both** the PRD's
"moved to [new location]" subject **and** the noise the PRD says not to send. **Silencing it
wholesale would silence the PRD's own third subject** — which the work item asks for, and
which the PRD fixes verbatim.

#### The distinction is available, in the change row

**`_kind_facts` intersects the changed fields with the kind's facts**, so a change row
records **only what actually changed**:

| what changed | the `detail_changed` row carries |
|---|---|
| the venue | `before["venue_fingerprint"]`, `after["venue_fingerprint"]` |
| the title | `before["title"]`, `after["title"]` |
| the description | `before["description"]`, `after["description"]` |

**So the row says whether the venue moved.** A venue move and a title edit are the same
*kind* and different *facts*, and the facts are on the row.

**And the new venue's name resolves through `catalog` at render time** — the same read that
gives the title. The old venue is not nameable (a fingerprint is a hash), which is the
limitation `EventFacts.venue_id`'s own comment records, and the reason the subject names
only the **new** place.

#### The decision: `detail_changed` notifies only when the venue moved

**The subject is decided by what changed, not by the kind.**

| the change carries | notified? | subject |
|---|---|---|
| a venue move | **yes** | `EventPulse24: {title} moved to {where}.` — **the PRD's, verbatim** |
| anything else (title, description, URL, timezone label) | **no** | — |

**Why the rest is silent**, in the work item's own terms:

1. **FR-53 says not every change deserves a notification.** Its out-of-scope line: *"Real-time
   push notification on every state change (would be engagement-trap; only meaningful changes
   trigger user-facing notification per FR-54)."*
2. **A title or description edit has no reminder consequence.**
   `LIFECYCLE_SEND_BEHAVIOUR` maps `detail_changed` to `KEEP` and
   `LIFECYCLE_PERSONAL_BEHAVIOUR` maps it to `NONE`. **FR-54's body requirement is "what
   changed and what it means for the user's reminders" — and a title edit has no such
   meaning.** A notice with no consequence is exactly the notification FR-54 is trying not
   to send.
3. **It cannot say what changed.** The kind carries no detail, so a notice about a title
   edit could only say "the details changed" — which is not information.
4. **The user can see it for themselves.** A typo fix in a description is on the Detail
   Screen, which is where a description belongs.

**The silence is at the source** — `services.state_notices` refuses to raise the notice — and
so it covers **both** deliveries: no email and no in-app banner. FR-54 asks for "in-app +
email" as a pair, and splitting them would leave a banner with no email, which is a worse
experience than neither.

**So the rule is not "the kind is silent" but "the *change* is silent unless the venue
moved."** That is a fact about the change row, and it is a decision the *raise* path makes —
which means the raise path needs the change's `before`/`after`, not just its kind. **That is
the one signature change in this item**, and it is a real one: `raise_state_notice` currently
takes `change_kind` and nothing else, and it will now take the change's facts.

**The counter-argument, and why it loses.** A title change is arguably meaningful — a venue
renaming "Rooftop Cinema" to "Rooftop Cinema: Late Night" is the kind of thing a user
should know about. **But the change row does distinguish it** — `after["title"]` is present.
**So the argument is not that the distinction is unavailable; it is that a title change is
not worth an email.** It is a rename on a page the user can open, and FR-53 calls
notification-on-every-change an engagement-trap. **If a title change should notify, that is
a `title_changed` kind** — with its own precedence position, its own subject and its own
ingestion rule. **That is a follow-up, and it is recorded as one.**

**`superseded` is the other kind the PRD does not name, and unlike `detail_changed` it is
not silenced.** A supersede means the event moved beyond the ±30-day window and a
*different* event replaced it. The user's saved event is cancelled
(`LIFECYCLE_SEND_BEHAVIOUR` maps it to `CANCEL`), so they lose the event entirely —
**silence would leave them with reminders that never fire and a Timeline entry for an event
that no longer exists.** It gets a subject, in the same register as `cancelled`.

### The subject table

| the change | subject | whose |
|---|---|---|
| `cancelled` | `EventPulse24: {name} was cancelled.` | PRD verbatim |
| `postponed`, `time_moved` | `EventPulse24: {name} was moved to {new date}.` | PRD verbatim |
| `sold_out` | `EventPulse24: {name} is sold out.` | PRD verbatim |
| **a venue move** (`detail_changed` whose facts name a venue) | `EventPulse24: {name} moved to {new location}.` | **PRD verbatim** |
| `superseded` | `EventPulse24: {name} was replaced by a new event.` | **ours** |
| `reinstated` | `EventPulse24: {name} is back on.` | **ours** |
| **a title, description, URL or timezone edit** (`detail_changed` otherwise) | *(no notice — silenced at the source)* | **our decision** |

**So the PRD's four subjects are all there, and the three kinds it does not name are
answered.** `detail_changed` is the one kind that appears twice — once with the PRD's
subject, once with no subject at all — and the *change's facts* say which.

**`postponed` and `time_moved` share the PRD's "was moved to [new date]" subject.** FR-54's
second consequence bullet names "a saved event that is postponed"; `time_moved` is a
postponement the catalog recorded without a status change. **The user's world is the same
in both cases: the event is at a new time.** They are not told which internal kind produced
it — the PRD's four bullets are written for the user's world, not the schema's.

**`reinstated` is ours, and the work item says so.** *"It is the seventh kind, it re-mints
reminders, and the PRD names no subject for it. This item writes one in the same register
and records that it is ours, not the PRD's."*

### The link: one rule, not two

**The AC says "A link to the event's Detail screen, where the banner and the mute control
live."** The Detail Screen is the frontend route `/events/{event_id}` — the personalized
one, where the banner and the mute live.

**Six of the seven kinds link to the saved event's own Detail Screen.** For a `superseded`
event that page is gone: `get_public_event_detail` raises for a superseded event (the
public catalog excludes superseded rows), and the personalized Detail Screen 404s with it.

**So for `superseded` the link points at the replacement's Detail Screen** — and the
replacement's id is `after["superseded_by"]` on the change row. **One rule: the link is the
page where the change is visible.** For six kinds that is the event's own page; for a
supersede that is the event that replaced it.

**The link is a tracked CTA**, like the digest's. `click_url_for` signs the destination, so
it cannot be edited into an open redirect, and SM-2 measures the click. The notice's link is
the thing the user does next: go and see the change, and mute it.

**And the Detail Screen is where the mute lives** — which is why the notice needs no
unsubscribe link of its own, and why the body must not imply one exists.

### The body: what changed and what it means

The work item's AC: *"The body states **what changed and what it means for the user's
reminders** — 'your reminders have been rescheduled' / 'your reminders have been cancelled'
— because the reminder consequence is the reason the email is correctness-critical rather
than informational."*

**This is where the body earns its place.** A subject saying "was cancelled" tells the user
the fact; the body tells them their evening's plan has been handled for them.

| kind | the body's reminder line |
|---|---|
| `cancelled` | *"Your reminders for this event have been cancelled."* |
| `superseded` | *"Your reminders for this event have been cancelled."* + the replacement's link |
| `postponed`, `time_moved` | *"Your reminders have been rescheduled to the new time."* |
| `reinstated` | *"Your reminders are back on."* |
| `sold_out` | *"Your reminders are unchanged."* + *"Tickets are no longer available."* |

**The reminder line is derived from `LIFECYCLE_SEND_BEHAVIOUR`, not from a second table.**
That table is what the *sends* already follow — `CANCEL` → cancelled, `REMINT` →
rescheduled, `KEEP` → unchanged. **Reusing it is the point:** the body's promise about the
reminders must be the same promise the send machinery kept. Two tables would let the email
say "your reminders have been cancelled" while the reminders still fire — **and that is
exactly the bug class this whole intent exists to prevent.**

**`sold_out`'s reminder consequence is "unchanged"** — `KEEP`, so the reminders still fire
for a sold-out event. Saying "unchanged" is honest and worth saying: a user who bought a
ticket needs to know the reminder is still coming.

**`reinstated`'s is "back on"** — `REMINT`, so the reminders are re-minted and fire again.

**The work item's subject line for `sold_out` mentions the CTA:** *"The Detail Screen shows
the 'Sold Out' badge and removes the 'Save Reminder' CTA."* That is the frontend's half —
`frontend-pulse-card-state` and `notice-and-mute-api`. **The email does not try to be the
badge.** It says the event is sold out and links to the page that shows it.

### The escaping

The work item: *"The event name is rendered safely for an untrusted ingested string — no
injection into the subject line, no unescaped HTML in the body."*

**The title is an ingested string.** It comes from a third-party feed and this codebase does
not control it. Three places it could hurt:

1. **The subject line.** A title containing `\n` is a header-injection vector — a title of
   `"Jazz\nBcc: attacker@example.com"` would, in a naive implementation, add a header.
2. **The HTML body.** A title of `"<script>alert(1)</script>"` is XSS in every HTML mail
   client that renders it. **Django's template engine autoescapes by default** — `{{ title }}`
   is escaped, `{{ title|safe }}` is not. The existing templates use `{{ display_title }}`
   with no filter, so **the HTML body is already escaped** and stays that way.
3. **The text body.** Plain text is not interpreted, so there is no injection — but a title
   with a newline in it would break the body's line structure.

**The subject is the real work.** `EmailMessage.subject` is a plain `str` handed to the
provider, and a newline in it is a header injection. So the title is folded to one line:

```python
def _one_line(title: str) -> str:
    """One line, no newlines, no control characters."""
    return " ".join(title.split())
```

**`" ".join(title.split())` collapses every whitespace run — newlines, tabs, non-breaking
spaces — to a single space.** It is the standard fold, it is one line, and it cannot leave a
newline behind. It also collapses a title's *legitimate* internal newlines, which is the
right trade: a subject is one line.

**The fold happens once, in the facts-gathering layer**, so the subject, the text body and
the HTML body cannot disagree about what the title is.

**The AC's "a missing or empty event name degrades to something legible rather than
`EventPulse24: was cancelled.`"** — the existing `email_templates` convention already
answers this: `facts.title or "your saved event"`. So a missing name gives
`EventPulse24: your saved event was cancelled.` — legible, and it invents no title. **The
existing convention is reused rather than a second one invented**;
`test_a_reminder_without_a_title_says_the_event_was_saved` is the precedent.

**An empty string is not `None`.** `facts.title or "your saved event"` handles both — an
empty string is falsy. And a whitespace-only title folds to `""`, which is also falsy, so
**the fold happens first and the fallback is applied to the folded value.**

**The HTML body escapes the folded title too.** A title of `<b>bold</b>` must show as
literal text in the HTML, not as bold — and the template's `{{ display_title }}` with no
filter does exactly that.

### The unsubscribe

The work item: *"**No unsubscribe URL** on a transactional send, and no footer implying one
exists."*

`render_state_notice` already sets `unsubscribe_url=None`, and the state notice is
transactional, so `EmailPort.send` does not demand one. **Two things must hold:**

1. **`EmailMessage.unsubscribe_url is None`** — the port-level fact.
2. **No footer implies one exists.** The reminder body says *"Stop reminders for this
   event"* — a *reminder* opt-out, not a list unsubscribe. **The state notice body must not
   carry that link**, because the notice is not a reminder: the reminders for a cancelled
   event have been *cancelled*, and a "stop reminders for this event" link on a cancellation
   email is offering to stop something that has already stopped.

**The mute is the opt-out, and it lives on the Detail Screen** — which the body links to.
**No footer, no link, no hint.** The AC is met by what is absent, and a test asserts the
absence.

### The dispatch: two questions, asked in order

**The dispatch is on `row.kind` *and* the stream — not instead of the stream.**

The stream is the *obligation* (AD-20: the bulk stream owes an unsubscribe URL). The kind
is the *content*. **Both matter, and they are different questions.** A state notice is
transactional *and* a state notice; the stream says what the provider owes, the kind says
what the body says.

```python
if row.kind == ScheduledSend.Kind.STATE_NOTICE.value:
    return render_state_notice_row(row, address)   # ← the new branch
if stream is Stream.BULK:
    return render_digest(row, address)
return render_transactional(row, address)
```

**Why the kind check comes first.** A state notice is transactional, so it would otherwise
reach the transactional branch — which renders a reminder. Putting the kind check first is
what makes the branch reachable at all. And it is honest about the ordering: **the content
decides the body; the stream decides the obligations.** A bulk row that were somehow a state
notice still gets the bulk renderer, because AD-20's obligation follows the stream.

### A missing notice cancels the send

**The renderer needs the notice row for the kind. What if it is gone?**

A notice row can be deleted by the cap's supersede path — which cancels the send, so the
row is not `pending` and is never claimed. It can also be purged by retention.

**A missing notice means there is no kind, and a generic subject is the one thing FR-54
forbids.** So the renderer raises `MissingTargetError` — the sweep's existing, tested
mechanism for "the thing this row is about is not there any more" — and the sweep cancels
the row. **The same treatment a vanished reminder target gets.**

### What this item does not do

- **It does not add the in-app surfaces.** The digest strip and the Detail banner are
  `notice-and-mute-api`'s and `frontend-digest-strip-and-detail-banner`'s.
- **It does not add the mute's API.** `notice-and-mute-api`.
- **It does not touch the frontend.** `frontend-pulse-card-state` and
  `frontend-digest-strip-and-detail-banner`.
- **It does not add a `title_changed` kind.** The reasoning above names it as the right
  follow-up; adding it here would mean a new `ChangeKind`, a new precedence position, a new
  subject and a new ingestion rule — a different item.
- **It does not add push.** FR-54 defers it to Phase 2+.
- **It does not change the cap, the mute or the stream.** Those are
  `state-change-notice-model`'s.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/domain/notices.py` | The pure vocabulary: the subject per kind, the reminder consequence per kind, the silent kinds |
| `backend/tests/delivery/test_state_notice_email.py` | The subjects per kind, the escaping, the empty name, the dispatch, the muted case |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/delivery/services/email_templates.py` | `StateNoticeFacts` gains the new fields; `render_state_notice` builds the subject from the kind and folds the title |
| `backend/apps/delivery/templates/delivery/state_notice.txt` | The body says what changed *and* what it means, with the Detail link and no unsubscribe |
| `backend/apps/delivery/templates/delivery/state_notice.html` | The same, in HTML, with the title escaped by Django as it is today |
| `backend/apps/delivery/services/delivery_messages.py` | The `state_notice` dispatch branch; the gathering for a notice's facts |
| `backend/apps/delivery/services/state_notices.py` | `raise_state_notice` takes the change's facts and raises nothing for a `detail_changed` that is not a venue move |
| `backend/tests/delivery/test_email_templates.py` | The existing `Update: {title}` assertion becomes the PRD's subjects; the fold |
| `backend/tests/delivery/test_delivery_messages.py` | The dispatch: a state notice row renders a notice, not a reminder |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/delivery/test_state_notice_email.py` | One subject per change (the literal strings), the escaping case, the empty-name case, the reminder-consequence line, no unsubscribe, the Detail link, a muted event producing no send, a title edit producing no notice, a venue move producing the PRD's |
| `backend/tests/delivery/test_email_templates.py` | The subject is the PRD's, not `Update: {title}`; the fold; the voice; both bodies always |
| `backend/tests/delivery/test_delivery_messages.py` | A `state_notice` row renders a notice, not a reminder; a missing notice cancels the send; a superseded notice links to the replacement |

## Technical Details

### The pure vocabulary, in `domain/`

`domain` is stdlib-only plus `shared.constants` and `shared.ids` (AD-2), and
`LIFECYCLE_SEND_BEHAVIOUR` is in `shared.constants` — so the reminder consequence is
derivable in `domain` without reaching into an app.

```python
# domain/notices.py
NOTICE_SUBJECTS: dict[str, str]        # kind → subject template
PRD_SUBJECT_KINDS: frozenset[str]      # which of them the PRD fixes, and which are ours
REMINDER_CONSEQUENCE: dict[str, str]   # kind → what the body says about the reminders
```

**`REMINDER_CONSEQUENCE` is derived from `LIFECYCLE_SEND_BEHAVIOUR`**, not written out —
so the body and the send machinery cannot disagree:

| `LIFECYCLE_SEND_BEHAVIOUR` | the body's line |
|---|---|
| `CANCEL` | cancelled |
| `REMINT` | rescheduled |
| `KEEP` | unchanged |

**`reinstated` is `REMINT`, so it would say "rescheduled" — but the PRD's world says the
event is *back*.** A reinstatement is not a new time: the event is back at the time it was
already at, so "your reminders have been rescheduled to the new time" would be a sentence
about a time that did not change. **So `reinstated` has its own line**, written out
explicitly rather than emerging from a branch — so a reader can see which kind says
something other than its behaviour implies.

**`PRD_SUBJECT_KINDS` records whose each subject is.** Four are the PRD's, verbatim; three
are this project's. **A test asserts the PRD's four literal strings**, so a well-meaning
rewrite fails rather than ships.

### The subject is built, not formatted

**The subject is assembled from the kind and the folded title, never from a `str.format`
over a dict of templates.** A template with a placeholder and a `.format()` call is a
`KeyError` waiting for a kind nobody tested — and `detail_changed` has *two* subjects, so
the subject cannot be a function of the kind alone.

**So the subject is chosen by the *change*, not the kind.** The subject template is picked
by a function that takes the kind *and* the change's facts:

```python
def notice_subject(change_kind, *, title, when=None, where=None) -> str
```

- `detail_changed` whose facts name a venue → the PRD's *"moved to {where}."*
- `detail_changed` otherwise → **not notified at all** (the raise path refuses it).
- every other kind → its own template.

**The generic-subject question has an answer: there isn't one.** If `domain.lifecycle` gains
a kind and `domain.notices` does not learn it, the renderer **must fail loudly** — a
notice with a wrong subject is worse than a notice that did not go out, because the user
reads "EventPulse24: your saved event was cancelled" about an event that was not
cancelled. **The exception is caught by the sweep, which cancels the row** — so the failure
is a cancelled send, not a wrong email. That is the right failure.

### The title's fold, and where it happens

**The fold is in the facts-gathering layer** (`delivery_messages`), not in the template and
not in `email_templates`. `email_templates` is the pure renderer: facts in, a body out, no
logic. **A fold is logic.** So `email_templates` receives an already-folded title, and its
own job is to choose the subject and render the body.

**But the fallback lives in `email_templates`,** because the fallback is a *presentation*
decision ("your saved event") and it already lives there for the reminder and the digest.
**So the facts carry the raw title, the fold happens in the gathering, and the fallback
happens in the renderer.** Two steps, two places, each with one reason.

### The gatherer

```python
def _state_notice_facts(row: ScheduledSend) -> StateNoticeFacts:
    """Everything a state notice's body quotes, gathered once."""
```

1. **The notice row** — `StateChangeNotice` by `(user_id, state_change_id)`. The
   `state_change_id` is inside `row.send_key`, and `send_keys` owns the key's shape, so
   **the parser lives beside the builder** — the same rule
   `digest_local_date_from_key` already follows. **A missing notice raises
   `MissingTargetError`.**
2. **The change row** — `outbox.get_state_change(state_change_id)`. **Its `before`/`after`
   carry the times, the venue facts and the replacement's id.** A missing change raises
   `MissingTargetError` too — the same reasoning: the notice is about a change that no
   longer exists.
3. **The event** — `get_public_event(event_id=row.target_id)`. **The title and the venue's
   name.** A missing event is **not** an error: the catalog may have dropped it, and the
   body then says "your saved event" — the same treatment `_public_event_facts` gives a
   reminder.

**A missing venue degrades the subject, and the degradation is ours.** The PRD's third
subject is *"moved to [new location]."* — the place named. **When the catalog cannot name
the place, the subject says *"moved to a new location."*** That is a fourth form of the
PRD's subject, it is ours, and it is recorded as such — the same way the four PRD forms
are. **It is better than a subject that names a place nobody can verify**, and better than
a `KeyError` that cancels the one notice FR-54 most wants for a venue move.

### The raise path needs the change's facts

**`raise_state_notice` currently takes `change_kind` and nothing else.** It now also takes
the change's `before`/`after`, because *"is this change worth a notice?"* is a question
about the **change**, not the kind — a `detail_changed` that moved the venue and a
`detail_changed` that fixed a typo are the same kind and different answers.

**The change's facts arrive as plain data** (`dict[str, Any]`), by value — the same shape
`outbox.StateChangeFacts` carries them in. **So the raise path takes a small, explicit
value rather than a whole change row:** the venue's fingerprint before and after, and
whether they differ. **That is the only new fact the raise path needs**, and it is the
smallest thing that answers the question.

### The renderer's public shape

```python
def render_state_notice_row(row: ScheduledSend, address: str) -> EmailMessage:
    """Render a state-change notice's email."""
```

**It is a separate function, not a branch inside `render_transactional`.** The two have
different obligations (the notice has no reminder link), different facts (a notice needs a
kind), and different failure modes (a missing notice cancels the row). **Merging them
would make the notice's obligations optional**, which is the reason
`render_transactional` and `render_digest` are already two functions.

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

---

---
run: run-eventpulse24-025
work_item: polling-cadence-floors
intent: event-state-sync
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at: pending
---

# Implementation Plan: FR-53's detection floors

## Approach

FR-53: *"The system re-ingests high-priority sources at least every 4 hours. Lower-priority
sources at least daily."* Its testable consequences are detection guarantees — a cancellation
found within 4h or 24h, and a postponed event's new time in the user's saved snapshot within
4h.

**The machinery exists; the guarantee does not.** `Source.ingestion_cadence` is a per-source
`DurationField`, the scheduler already selects on it (`claim_due_sources`), and
`DEFAULT_INGESTION_CADENCE` already splits by acquisition method into exactly FR-53's two
tiers — `api`/`partnership`/`jsonld`/`rss`/`ics` at 4h, `email_ics`/`crawl` at 24h.

**What does not exist is a floor.** A source can be registered with a seven-day cadence and
nothing objects; the registry's own cleaner accepts any duration above 15 minutes. The
product then promises a 4-hour detection window that the data does not support. FR-53 is not
satisfied by a *default*; it is satisfied by a *ceiling*.

### The one real decision: where does "priority" come from?

The work item says priority is the only real decision, and asks for "a field, or a documented
derivation from what is already there."

**The PRD does not define it.** FR-53 says "high-priority sources (FR-13)" — and FR-13 has no
priority concept at all. The only definitional trace anywhere is PRD §10.4's parenthetical:
*"high-priority sources (official sites) within 4 hours."* That is a hint, not a rule.

**So this is a project decision, and it is made here explicitly.**

**Priority is derived from `acquisition_method`** — and specifically from FR-17's own priority
order, which the codebase already declares:

```python
class AcquisitionMethod(models.TextChoices):
    """FR-17 priority order, highest first: crawl is the last resort and needs a ToS review."""
    API = "api"
    PARTNERSHIP = "partnership"
    JSONLD = "jsonld"
    RSS = "rss"
    ICS = "ics"
    EMAIL_ICS = "email_ics"
    CRAWL = "crawl"
```

**Why the method and not a new field:**

1. **It is the ordering the product already believes in.** FR-17 says official APIs >
   partnerships > RSS/JSON-LD > email/ICS import > web crawling, and the enum's own docstring
   says "FR-17 priority order, highest first". A second, parallel priority field on the same
   model would be a second opinion about a question the codebase has already answered — and
   the two could disagree.
2. **It matches FR-53's parenthetical.** "High-priority sources (official sites)" — official
   API and partnership sources are exactly the official sites.
3. **It matches the defaults that are already shipped.** `DEFAULT_INGESTION_CADENCE` splits on
   exactly this boundary: 4h for `api`/`partnership`/`jsonld`/`rss`/`ics`, 24h for
   `email_ics`/`crawl`. A derivation that produced a different split from the shipped
   defaults would be a bug on day one.
4. **The PRD's cross-reference is broken anyway.** FR-53 says "(FR-13)", but FR-13 is the
   registry requirement and says nothing about priority. There is no field to point at.

**And what is derived is not the cadence — it is the ceiling.** The cadence stays a per-source
field, because a source's *actual* cadence is an operational choice (a partner's feed may
publish weekly). What is derived is the **maximum** it is allowed, and the ceiling comes from
the tier the source is in.

**A derived priority, in one named place.** `shared/constants.py` gains
`HIGH_PRIORITY_CADENCE_MAX` and `LOW_PRIORITY_CADENCE_MAX`, and the derivation lives in one
function — `source_priority(method)` in `apps/ingestion/services/source_registry.py` — which
returns the ceiling for a source's method. No caller re-expresses the rule.

### The two tiers

| Tier | Methods | Ceiling | Why |
|---|---|---|---|
| **High** | `api`, `partnership` | **4 hours** | FR-53's first clause. These are the official sites — the sources whose cancellations a user is most likely to be hurt by |
| **Lower** | `jsonld`, `rss`, `ics`, `email_ics`, `crawl` | **24 hours** | FR-53's second clause |

**Wait — `jsonld`, `rss` and `ics` are 4h defaults today, and this puts them in the 24h tier.**
That is deliberate, and it is the one place this plan changes shipped behaviour. The shipped
`DEFAULT_INGESTION_CADENCE` gives `rss` a 4-hour default; FR-53's *guarantee* is about
**cancellation detection**, and a cancelled event on an RSS feed must be found within 4 hours.
A 4-hour *cadence* gives a detection window of up to 8 hours (the poll lands 4 hours after the
cancellation, plus up to 4 hours until the next poll). **So a 4-hour cadence does not
satisfy a 4-hour guarantee** — and FR-53's consequence says "detected within 4 hours".

**This is the crux of the item, and it is worth stating plainly:** FR-53's guarantee is
*detection within 4 hours*, and a polling system with period `p` detects within `p` only if it
polls at least once inside the window. A 4-hour cadence has a worst case of 4 hours — which
is *exactly* 4 hours, and a cancellation at 09:00:01 with a poll at 09:00:00 and 13:00:00 is
found at 13:00:00, which is 3h59m59s. That is inside the window.

**So a 4-hour ceiling is right for the high tier.** And for the lower tier, FR-53 says
"at least daily" — a 24-hour cadence has a worst case of 24 hours, which is "daily", again
exactly at the boundary.

**But the shipped defaults put `rss`/`jsonld`/`ics` at 4h.** Those are *defaults*, which is
a different thing from a *ceiling*: a source may poll more often than its tier requires.
Under this item they may not poll *less* often than 24h. Their defaults stay at 4h — which is
inside the 24h ceiling, and which keeps them detecting changes within 4h rather than 24h.

**So nothing ships worse than today.** The ceilings only *forbid* cadences that FR-53 cannot
guarantee. A source at 4h in the lower tier is unchanged and still detects within 4h; a
source at 24h is exactly at the boundary FR-53 allows.

**Why not simply put `jsonld`/`rss`/`ics` in the high tier?** Because FR-53's parenthetical is
"official sites" and FR-17's order puts crawling last for a reason. A crawl source is the
last resort; giving it a 4-hour floor would push the whole registry toward frequent crawling,
which is exactly what FR-17's ToS guard exists to prevent. The ceiling is a *guarantee*, not
an aspiration — a lower tier that polls daily is still a daily guarantee, and the registry's
40-source floor is met by mixture, not by making every source high-tier.

### What is enforced, and where

**At the point the value is written** — the acceptance criterion is explicit: *"Enforced where
the value is written, so an out-of-range cadence is rejected rather than discovered later."*

Two write paths reach `Source.ingestion_cadence`:

1. **`register_source`** — `source_registry.py`.
2. **`update_source`** — `source_registry.py`.

Both go through `check_source_change` → `clean_source_input` → the `_CLEANERS` map. The
`_cadence` cleaner is the one place to enforce, and it already enforces the *floor*
(`INGESTION_CADENCE_MIN`, 15 minutes). The ceiling goes in the same cleaner.

**But the cleaner does not know the source's tier** — on an update the method may itself be
changing. So the cleaner gains the method as an argument, and `check_source_change` computes
the *effective* method (the one being set, or the stored one) and passes it in.

**A method change re-checks the cadence.** This is the subtle case and it is worth stating:
a source at a 4h cadence in the high tier can be moved to `crawl` (a 24h tier), and the
cadence it already has is still legal there. But a source at a 24h cadence in the lower tier
moved to `api` (a 4h tier) would be *illegal* under its new ceiling. **The method change is
refused unless the cadence is brought within the new tier's ceiling in the same change.**

That is the honest reading of "enforced where the value is written": the row must be legal
after the write, whichever field changed.

**Two ways to satisfy it, and the order matters.** If a caller changes the method *and* the
cadence together, the new cadence is checked against the new tier — legal. If a caller changes
only the method, the stored cadence is checked against the new tier — and refused if illegal,
with the error naming the field to change. The error message says what to do.

### The admin form

`apps/ingestion/admin.py` has its own form for `ingestion_cadence` and calls
`check_source_change` from `clean()`. So the ceiling is enforced there too, for free — the
form shows the same refusal. **But** the admin form does not currently know the source's
method when the method is also being changed on the same form. `check_source_change` handles
that (it computes the effective method), so the form inherits it.

### The backfill

**Existing rows are brought within their ceiling by a migration, not by hand.**

Every `Source` row's method determines its ceiling. A row whose cadence exceeds its ceiling is
clamped to the ceiling. The migration is a `RunPython` that:

1. **Reads** each source's method and cadence.
2. **Clamps** any cadence above the ceiling to the ceiling.
3. **Reports** what it clamped — the migration must not silently rewrite an operator's data.

**Clamping, not refusing.** A migration cannot refuse: the rows exist and the schema must
end up legal. And a **database check constraint** is added alongside, so the invariant is
enforced by the database too and not only by the Python path.

**But a check constraint needs the priority as a stored expression** — the database has to
know which tier a row is in, and it cannot call a Python function. So the constraint is
written directly against `acquisition_method`:

```python
models.CheckConstraint(
    condition=(
        Q(acquisition_method__in=HIGH_PRIORITY_METHODS)
        & Q(ingestion_cadence__lte=HIGH_PRIORITY_CADENCE_MAX)
    )
    | (
        Q(acquisition_method__in=LOW_PRIORITY_METHODS)
        & Q(ingestion_cadence__lte=LOW_PRIORITY_CADENCE_MAX)
    ),
    name="source_cadence_within_priority_ceiling_ck",
)
```

**A check constraint cannot reference a constant that Django cannot serialize into a
migration** — but a `timedelta` and a tuple of strings both serialize fine. The constants live
in `shared/constants.py` and the migration imports them; if the constants change later, the
migration is rewritten by `makemigrations`, which is correct.

**The constraint is `DEFERRABLE`.** The repository's convention (seen in `Event.Meta`) is
`models.CheckConstraint(..., deferrable=models.Deferrable.DEFERRED)`. A constraint that
cannot be deferred is not a problem here — the write is a single row — but the convention is
the convention. **Actually, deferrable does not help here and is not needed**: the check is on
one row's own columns, so it is evaluated immediately and correctly. The existing
`source_cadence_positive_ck` is not deferrable. **This item follows the local convention of
the constraint it sits beside** — not deferrable.

### The scheduler honours the cadence

**Already true, and the acceptance criterion asks for it to be asserted.** `claim_due_sources`
filters on `last_attempted_at <= now - ingestion_cadence`. A source at a 4h cadence is
claimed 4 hours after its last attempt. This is asserted by a test — one that fails if the
scheduler's cadence filter is broken, not one that asserts the constant equals 4.

### The FR-53 consequence test — the one that matters

**"A test that can fail on the FR-53 consequence itself: given a source at its ceiling, a
cancellation introduced upstream is detected within the stated window. Not a test that the
constant equals four."**

So the test is **end-to-end through the real polling loop**, not a unit test of a constant:

1. A source is registered at its tier's ceiling (4h for a high-priority source).
2. The source is ingested once; a `last_attempted_at` is set.
3. **Upstream**, the event is cancelled. (The upstream side is a fixture, not the thing under
   test.)
4. The clock advances to **just inside** the window — `last_attempted_at + 4h`.
5. The scheduler's `claim_due_sources` is called at that moment.
6. The source **is claimed** — the detection happened inside the window.
7. And the ingest that follows writes the `EventStateChange` that propagation consumes.

**The test fails if the scheduler's cadence filter is wrong** — because step 5 uses the real
`claim_due_sources`, not a restatement of the rule.

**And the boundary is asserted from the wrong side too**: at `cadence - 1 second` the source
is **not** yet due, and at `cadence` it **is**. A test that only checks the happy path cannot
tell a scheduler that polls too often from one that polls exactly right.

### Failing sources do not silently stop meeting the floor

**"A cadence guarantee nobody is checking is worse than no guarantee, because the product
promises on it."**

A source that keeps failing never ingests successfully, so `stale_since` gets set by
`flag_stale_sources` — at **2× its cadence**, which for a high-priority source is 8 hours.
**That is already a surfacing mechanism** (a warning log with a count, and a flag on the row
visible in the admin).

But it is not enough, and here is why: **the stale flag fires at 2× the cadence, and the
guarantee is 1×.** A high-priority source that fails at 04:00 and would have been re-polled at
08:00 has already missed its 4-hour window by the time the flag appears at 08:00. **The
guarantee is broken before anything is surfaced.**

So this item adds a **cadence-floor alarm**: a source that has gone longer than its tier's
ceiling since its last *attempt* — not since its last success — has missed its floor, and
that is surfaced.

**Wait — that is what `flag_stale_sources` does.** Let me be precise about the difference:

- `flag_stale_sources` fires on **no successful ingestion** within **2×** the cadence. It is a
  *freshness* signal about the data.
- The new signal fires on **no attempt** within **1×** the ceiling. It is a *floor* signal
  about the polling.

**These are different.** A source that is polled every 4 hours but whose fetches all fail has
`last_attempted_at` moving and `last_ingested_at` frozen. The floor is **met** — the source
was polled — but the *detection* is not, because the poll failed. And a source that is not
claimed at all (the broker is down, the worker died, the claim is stuck) has neither moving.

**So the floor signal must be about attempts, and the detection signal is a separate
question.** This item adds the **attempt-side floor check**: a source whose
`last_attempted_at` (or `created_at`, if never attempted) is older than its tier's ceiling
has not been polled inside its window.

**Where does that surface?** The scheduler's tick already logs `"Sources stale"` with a count.
This adds a parallel **`report_cadence_floor_breaches`** that counts sources past their
ceiling and logs a warning with the count — no ids, no titles (AD-13). It is bounded and
cheap: one indexed query.

**And the failing-source half.** A source whose attempts are happening but which keeps
failing is past its *detection* floor without being past its *polling* floor. The existing
`consecutive_failures` counter tracks that, and `stale_since` fires at 2× the cadence. **The
gap is the window between the ceiling and 2× the cadence** — for a high-priority source,
4h to 8h, during which the guarantee is broken and nothing is flagged.

**So the floor check counts a source as breaching when EITHER** it has not been attempted
within its ceiling, **OR** it has been failing for long enough that its last successful
ingestion is older than its ceiling. The second half is `last_ingested_at` older than the
ceiling — which is exactly the guarantee, stated directly: **the source has not successfully
ingested inside its detection window.**

That is the honest formulation of FR-53's consequence. A cancellation is detected within 4
hours only if the source was *successfully* ingested within the last 4 hours.

**So `report_cadence_floor_breaches` counts sources whose `last_ingested_at` (or `created_at`)
is older than their tier's ceiling.** One query, one count, one warning log line.

**But the cadence field is per-source and the ceiling is per-tier** — so the query cannot use
a stored column for the ceiling. It has to compare each row's `last_ingested_at` against a
tier-dependent window. **Two queries** — one for the high tier, one for the lower — each with
its own window, which is exactly how `flag_stale_sources` handles the per-row cadence
window with `F("ingestion_cadence") * STALE_AFTER_CADENCES`.

**The alternative — a stored `priority` field — would make this one query.** That is the
argument for the field. But it buys one query, and costs a second source of truth that can
disagree with the method. **The two-query version is taken**, and the reason is recorded: a
cadence guarantee enforced by a derived rule should be enforced by the same derived rule
everywhere. A stored `priority` column that could say `high` for a `crawl` source is a
guarantee nobody can check.

### The constants

The acceptance criterion says the constants live in `shared/constants.py` beside the other
cadences, each with the comment the file's conventions require.

```python
# FR-53: the detection floors. A high-priority source must be re-ingested at least every
# 4 hours, a lower-priority one at least daily — so a source's cadence may not exceed its
# tier's ceiling. The ceiling is *not* the cadence: a source may poll more often than its
# tier requires (and the defaults for rss/jsonld/ics do), but never less often.
#
# These are ceilings, not defaults, because a default is a starting point and a ceiling is
# a guarantee. FR-53's consequence is "detected within 4 hours", and a source polled every
# 24 hours cannot honour it — so the value is refused at the point it is written.
#
# The tier is derived from `acquisition_method` (FR-17's own priority order), not stored:
# a second priority field on the same model would be a second opinion about a question the
# codebase has already answered, and the two could disagree.
HIGH_PRIORITY_CADENCE_MAX = timedelta(hours=4)
LOW_PRIORITY_CADENCE_MAX = timedelta(hours=24)
```

And the method sets, beside them:

```python
# FR-17's order, split at the boundary FR-53's consequence names. "Official sites" —
# the PRD's own parenthetical for high-priority — are the API and partnership sources.
HIGH_PRIORITY_METHODS = ("api", "partnership")
```

## Files to Create

| File | Purpose |
|------|---------|
| (none) | — |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/shared/constants.py` | `HIGH_PRIORITY_CADENCE_MAX`, `LOW_PRIORITY_CADENCE_MAX`, `HIGH_PRIORITY_METHODS` |
| `backend/apps/ingestion/models.py` | The `source_cadence_within_priority_ceiling_ck` check constraint |
| `backend/apps/ingestion/services/source_registry.py` | `source_priority(method)`; the ceiling in `_cadence`; the effective-method resolution in `check_source_change` |
| `backend/apps/ingestion/migrations/0002_source_cadence_ceiling.py` | The constraint + the clamping backfill |
| `backend/apps/ingestion/admin.py` | The form's own cadence field — inherits the check through `check_source_change` |
| `backend/apps/ingestion/services/scheduling.py` | `report_cadence_floor_breaches` — the floor check |
| `backend/worker/tasks.py` | The new check joins the tick |
| `backend/tests/ingestion/test_source_registry.py` | The ceilings are refused where the value is written |
| `backend/tests/ingestion/test_scheduling.py` | The floor breach count |
| `backend/tests/ingestion/test_models.py` | The constraint holds at the database level |
| `backend/tests/e2e/test_state_detection_window.py` | **The FR-53 consequence test** — the one that matters |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/e2e/test_state_detection_window.py` | **The consequence test.** A source at its ceiling; a cancellation introduced upstream; detected inside the window — through the real `claim_due_sources`, and at the boundary from both sides |
| `backend/tests/ingestion/test_source_registry.py` | A high-priority source at 4h is accepted; at 4h+1s is refused. A lower-priority source at 24h is accepted; at 24h+1s is refused. A method change that would leave the cadence above the new tier's ceiling is refused, and is accepted when the cadence comes with it |
| `backend/tests/ingestion/test_scheduling.py` | `report_cadence_floor_breaches` counts a source past its ceiling and does not count one inside it; the two tiers are counted against their own windows |
| `backend/tests/ingestion/test_models.py` | The database refuses a cadence above the ceiling, whatever the Python path did |
| `backend/tests/ingestion/test_migrations.py` (new) | The backfill clamps an out-of-range row and leaves a legal one alone |

## Technical Details

### 1. The derivation, in one named place

```python
def source_priority(method: str) -> str:
    """The tier this source's method puts it in: "high" or "lower" (FR-53).

    **Derived, not stored.** FR-17's order is the codebase's own statement of which
    sources matter more, and the method is already stored — a second priority column
    would be a second opinion about a question the codebase has answered, and the two
    could disagree.
    """
    return "high" if method in HIGH_PRIORITY_METHODS else "lower"
```

And the ceiling follows from the tier:

```python
def cadence_ceiling(method: str) -> timedelta:
    """The longest cadence this source's method may have (FR-53)."""
    return (
        HIGH_PRIORITY_CADENCE_MAX
        if source_priority(method) == "high"
        else LOW_PRIORITY_CADENCE_MAX
    )
```

**No caller re-expresses the rule.** The scheduler's floor query, the registry's cleaner, the
admin form and the migration all go through these.

### 2. The ceiling in the cleaner

`_cadence` already enforces the floor. The ceiling needs the method, so the cleaner takes it:

```python
def _cadence(value: object, *, method: str) -> timedelta:
    if not isinstance(value, timedelta):
        raise _FieldError("Enter a duration.")
    if value < INGESTION_CADENCE_MIN:
        raise _FieldError("Sources are checked at most every 15 minutes.")
    ceiling = cadence_ceiling(method)
    if value > ceiling:
        raise _FieldError(
            f"This source is checked at least every {humanise(ceiling)}, so its cadence "
            f"cannot be longer."
        )
    return value
```

`_CLEANERS` is a flat map of field → cleaner, so the method has to be threaded. The cleanest
way that keeps `_CLEANERS` flat: `clean_source_input` takes the effective method as an
argument and builds the cadence cleaner with it.

**`clean_source_input`'s signature changes** — it takes `method` alongside `values`. Its
callers are `check_source_change` (which computes the effective method) and the admin form
(which goes through `check_source_change`).

**`check_source_change` computes the effective method:**

```python
method = cleaned.get("acquisition_method", current.acquisition_method if current else None)
```

That line already exists in `check_source_change` — for the FR-17 crawl guard. **The ceiling
reuses it.** The effective method is the one being set, or the stored one, and it is the
method the cadence will be measured against *after* the write.

**But there is an ordering subtlety.** `clean_source_input` validates the fields, and it needs
the method to validate the cadence. But the method itself is being validated in the same
pass. **The effective method must be computed *before* the cadence is cleaned**, from the
raw input — not from the cleaned input.

**That is a real subtlety and it is easy to get wrong**: if the caller passes
`acquisition_method="crawl"` (valid) and `ingestion_cadence=timedelta(days=7)`, the ceiling
is 24h and the cadence is refused. If the caller passes `acquisition_method="api"` and a 7-day
cadence, the ceiling is 4h and it is refused too. Both are refused. But if the caller passes
`acquisition_method="not_a_method"` (invalid) with a 7-day cadence, the *cadence* error would
be reported against the method's ceiling — but the method is invalid anyway, so the method's
error is the one that matters. **Both errors are collected** — `clean_source_input` collects
errors rather than raising on the first — so the caller sees both. That is the existing
behaviour and it is right.

### 3. The constraint

```python
models.CheckConstraint(
    condition=(
        Q(acquisition_method__in=HIGH_PRIORITY_METHODS)
        & Q(ingestion_cadence__lte=HIGH_PRIORITY_CADENCE_MAX)
    )
    | (
        Q(acquisition_method__in=LOW_PRIORITY_METHODS)
        & Q(ingestion_cadence__lte=LOW_PRIORITY_CADENCE_MAX)
    ),
    name="source_cadence_within_priority_ceiling_ck",
)
```

**The condition is a disjunction, not an implication.** A constraint on `acquisition_method`
would be written as "if method ∈ high then cadence ≤ 4h". Django's `Q` objects combine with
`&` and `|`, and `~Q(...)` is the negation — so the implication is written as
`~Q(method__in=HIGH) | Q(cadence__lte=4h)`.

**Which form is right?** The disjunction form requires the method to be in *one of* the two
sets for the row to be legal at all. **That is stricter than intended**: a new
`AcquisitionMethod` added later would make every row with it illegal until the constraint is
updated — which is arguably *correct* (a new method must be given a ceiling) but it means the
migration fails on a fresh database with the new method, which is a loud failure rather than
a silent one.

**The implication form is looser**: a source with an unknown method is unconstrained. That is
the "not applicable" shape the rest of this codebase uses for exactly this situation — and it
matches the derivation: an unknown method has no tier, so it has no ceiling.

**The implication form is chosen**, because it degrades to "no ceiling" rather than "illegal",
and because it is the shape the Python path implements (an unknown method falls through to
the lower tier's ceiling — so the two would disagree if the constraint used the disjunction).

**Hmm — that disagreement matters.** The Python derivation says an unknown method gets the
*lower* ceiling (24h), because `source_priority` returns "lower" for anything not in the high
set. The constraint's implication form would say an unknown method has *no* ceiling. **Those
disagree.**

**They must not.** The cleanest resolution: the constraint is written to match the Python
exactly — the "else" branch is the lower tier, which covers every method not in the high set:

```python
models.CheckConstraint(
    condition=(
        Q(acquisition_method__in=HIGH_PRIORITY_METHODS)
        & Q(ingestion_cadence__lte=HIGH_PRIORITY_CADENCE_MAX)
    )
    | (
        ~Q(acquisition_method__in=HIGH_PRIORITY_METHODS)
        & Q(ingestion_cadence__lte=LOW_PRIORITY_CADENCE_MAX)
    ),
    name="source_cadence_within_priority_ceiling_ck",
)
```

**Now they agree**: a high method needs ≤4h; anything else needs ≤24h. And a new method added
later defaults to the lower ceiling until someone classifies it — **safe by default**, which
is the right direction: a new acquisition method should not be able to opt itself out of the
guarantee by being unclassified.

**And `AcquisitionMethod` is a `TextChoices`**, so the database has no enum — a row could in
principle hold a method outside the choices. The constraint's `~Q(in=...)` branch covers it:
it gets the 24h ceiling. Correct.

### 4. The backfill migration

```python
def clamp_source_cadences(apps, schema_editor):
    """Bring every source's cadence within its tier's ceiling (FR-53)."""
    Source = apps.get_model("ingestion", "Source")
    clamped = 0
    for source in Source.objects.all().iterator():
        ceiling = cadence_ceiling(source.acquisition_method)
        if source.ingestion_cadence > ceiling:
            source.ingestion_cadence = ceiling
            source.save(update_fields=["ingestion_cadence"])
            clamped += 1
    ...
```

**The reverse migration** must not try to restore the clamped values — it cannot know them.
The reverse is a no-op for the data and drops the constraint. That is stated in the
migration's docstring, because a reverse that silently loses data is worse than one that
says what it does.

**The migration runs *before* the constraint is added**, or the constraint would be violated
by the very rows the migration is clamping. Django's `AddConstraint` operation validates the
existing rows — `AddConstraint` on a check constraint **does** validate existing rows and
would fail if any violate it. So the order is: `RunPython(clamp)` then `AddConstraint`.

**Actually — `AddConstraint` with a `CheckConstraint` does validate existing rows in
PostgreSQL.** The migration would fail if the clamp had not already run. So the order
matters and is stated.

**The migration reports what it clamped.** A migration that silently rewrites an operator's
data is a migration nobody can audit. `RunPython` can print, and the migration writes a line
naming the count.

### 5. The floor check

```python
def report_cadence_floor_breaches(*, now: datetime) -> int:
    """Count the sources that have not successfully ingested inside their tier's ceiling.

    **This is FR-53's guarantee, stated as a check.** A cancellation is detected within
    4 hours only if the source was successfully ingested within the last 4 hours. A source
    that is polled on time but keeps failing does not meet the floor, and neither does one
    that is not polled at all.

    **Two queries, one per tier**, because the window is per-tier and the tier is derived
    from the method rather than stored — so it cannot be a column comparison. Two indexed
    queries on a registry of hundreds of rows are cheaper than a second source of truth.
    """
```

The two queries filter on `last_ingested_at` (or `created_at` for a never-ingested source)
being older than the tier's ceiling.

**Wait — should the floor be about `last_ingested_at` or `last_attempted_at`?** Decided above:
`last_ingested_at`, because the guarantee is about *detection*, and a failed poll detects
nothing. A source that has never been ingested is counted from `created_at` — the same
convention `flag_stale_sources` uses.

**But `flag_stale_sources` already counts sources with no successful ingestion within 2× the
cadence.** The new check is the same shape at **1× the tier ceiling**. So the two overlap —
the new one is strictly earlier and strictly in terms of the tier rather than the row's own
cadence.

**Is that a duplicate?** It is a *different window*: `flag_stale_sources` is 2× the row's own
cadence (which may be 15 minutes — so 30 minutes), and the new one is 1× the tier ceiling
(4h or 24h). **For a source polled every 15 minutes that fails, `flag_stale_sources` fires
after 30 minutes and the floor check fires after 4 hours — the stale flag is *earlier*.** So
the floor check does not add a signal for that source; the stale flag already covers it, and
more tightly.

**Hmm. So what does the floor check actually add?** The case where `flag_stale_sources` is
**too slow**: a source whose own cadence is long. A high-priority source at its 4h ceiling
that fails: `flag_stale_sources` fires at 8h (2×4h), the floor check at 4h. **The floor
check is 4 hours earlier — exactly the window FR-53 promises and the stale flag does not
cover.**

**And the case where `stale_since` is set but the source recovers?** `_close` clears
`stale_since` on success. The floor check counts sources whose *last success* is old, which
is the same thing. **So the floor check is a stricter, earlier version of the stale signal,
expressed in the tier's terms rather than the row's own.**

**Is a stricter duplicate worth it?** Yes, and here is the reason: **`flag_stale_sources` is
about the data's freshness, and its threshold is a function of the row's own cadence — which
an operator controls.** A high-priority source registered with a 15-minute cadence that fails
is flagged stale after 30 minutes, which is *before* its 4-hour window — so the product
surfaces a failure it has not yet broken a promise about. **That is noise.** And a
high-priority source at a 4h cadence that fails is flagged after 8 hours — **which is 4 hours
after the promise broke.** That is silence.

**The floor check is the promise, stated as a check.** It fires at the ceiling, always, for
every source in the tier, regardless of what cadence the row happens to carry. That is a
different question from "is this source's data fresh?" and it deserves its own signal.

**And it is a count, logged as a count** — no source ids, no titles (AD-13). The `Source`
row is the registry, and a source's name is not PII, but the codebase's convention is ids
and counts in logs.

**A breach count of zero is not logged as a warning.** Only a non-zero count is a warning.

### 6. What this item does **not** do

- **It does not add webhooks.** FR-53's near-real-time half is out of scope for this intent,
  decided at capture: no Eventbrite/Meetup/Luma adapter exists, `event-catalog-ingestion`
  put official-API and partnership sources out of scope, and OQ-5 is still open. FR-53 names
  polling "the fallback"; this ships the fallback.
- **It does not add sources.** No new adapters, no new sources. The scope guard is explicit.
- **It does not change the defaults.** `DEFAULT_INGESTION_CADENCE` stays as it is. The
  ceilings only forbid what the guarantee cannot support.
- **It does not build the Source Registry UI.** FR-13's registry surface is itself unbuilt.
  This item enforces at the model and the command layer, which is where the value is written.
- **It does not touch the frontend.**

## Based on Design Doc

None. This is a `confirm`-mode item: no design doc, one checkpoint — this plan.

---
*Plan awaiting approval.*


---

---
run: run-eventpulse24-025
work_item: notice-composition-and-email
intent: event-state-sync
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at: pending
---

# Implementation Plan: Four subjects the PRD already wrote

## Approach

FR-54 fixes the copy, which is unusual and makes this item narrow. The subjects are given
verbatim:

- `EventPulse24: [event name] was cancelled.`
- `EventPulse24: [event name] was moved to [new date].`
- `EventPulse24: [event name] moved to [new location].`
- `EventPulse24: [event name] is sold out.`

**The entity, the stream, the cap and the mute are `state-change-notice-model`'s; the decision
to send is `propagation-consumer`'s.** This item writes the words, and puts them on the wire.

### The thing this item finds: the state notice email is currently a reminder

`render_state_notice` exists in `email_templates.py` and is **called by nothing but the
tests**. The live path is:

```text
sweep_due_sends → renderer_for(row, address)
                → row.stream == "transactional"
                → render_transactional(row, address)
                → _facts_for(row) → render_reminder(ReminderFacts(...))
```

`renderer_for` dispatches on the **stream**, not the kind. A `state_notice` row is
transactional — correctly, per AD-20, because it is a one-time correction about the user's
own saved record, not a broadcast — so it takes the transactional branch and renders a
**reminder body**:

> subject: `Reminder: Rooftop cinema`
> body: *"This is a reminder you asked for."* + *"Stop reminders for this event: &lt;signed link&gt;"*

**A user whose event was cancelled is today sent a reminder about it, with a link to stop
reminders for an event that no longer exists.** That is not a copy problem; it is the wrong
email entirely, and it is the thing this item has to fix.

So this item is **two** things, in order:

1. **Render the right body for a state notice** — the dispatch gains a `state_notice` branch
   that renders `render_state_notice`, not `render_reminder`.
2. **Give that body the PRD's subjects, per kind.**

The dispatch is the load-bearing half. Fixing the subjects in `render_state_notice` while
leaving the dispatch alone would change a template nobody receives.

### The second thing this item finds: the renderer's facts are not on the row

`ScheduledSend` for a state notice carries `target_id` (the catalog event's id) and a
`send_key` holding the `state_change_id`. It carries **no `change_kind`**, and a subject is
per-kind — so the renderer has to learn the kind from somewhere.

**The `StateChangeNotice` row has it.** `change_kind` is a column there, and the notice is
`delivery`-owned in `personal` — the same app that owns the renderer. **Reading it is not a
cross-schema read and not a write:** AD-3 is about *transactions* spanning schemas, and
AD-16 is about *writing* another app's table. `delivery` reading `delivery`'s own model is
neither.

**And the notice row is the right source, not a workaround.** The design doc settled it:
*"The notice is the record and the email is one of its two deliveries."* The email's facts
come from the notice. The `ScheduledSend` is a ledger row whose only job is "this is due at
this time"; the notice is what the email is *about*.

### Where the change's facts come from: the change row, read through `outbox`

**The kind alone is not enough.** "was moved to [new date]" needs the *new date*; "moved to
[new location]" needs the *new venue*. Neither is on the notice row.

**Both are on the `EventStateChange` row**, in its `before`/`after` snapshots:

| kind | what the change records |
|---|---|
| `postponed`, `time_moved` | `before["start_utc"]`, `after["start_utc"]`, `after["start_time_tz"]` |
| `cancelled`, `superseded` | `before["status"]`, `after["status"]`, `after["start_utc"]` |
| `superseded` | **and** `after["superseded_by"]` — the replacement's id (`event_writes.supersede_event`) |
| `sold_out` | `after["is_sold_out"]` |
| `reinstated` | `before["status"]`, `after["status"]` |

**And the change row is already published**: `outbox.get_state_change(state_change_id)`
returns exactly these as plain data (`StateChangeFacts.before` / `.after`). **Verified: a
`delivery` module importing `apps.ingestion.services.outbox` breaks no import contract** —
`lint-imports` still reports `19 kept, 0 broken`, because the `models-ingestion` contract
protects the *direct* importers of `apps.ingestion.models` and `delivery` already reaches it
indirectly through `catalog_read`.

**So no migration, and no new columns on `StateChangeNotice`.** The change id is already on
the notice; the renderer follows it to the change and reads the facts that changed.

**Why the change's own `before`/`after`, and not the live Event.** A poll appends one change
per kind, and the live Event already holds the *last* kind's facts. Pairing this change's
version with the live event's start would name a time that never existed — the same
reasoning `worker.propagation._moved_times` already documents, and the same reason the
change log is append-only.

**And the change's `after` is what the user will find on the page.** For a lone
`time_moved` the change's new start and the live start are the same. They differ only when
the catalog has moved on since — and then the change's value is the one that describes *this
change*, which is what the email is about.

### Where the display facts come from: the catalog, at render time

**The title and the venue's name are display facts, not facts that changed.** The title
resolves through `catalog` at read time — the established pattern, and the one
`delivery_messages._public_event_facts` already uses for reminders. The venue's *name* is
the same: what changed is the venue's *fingerprint*, and a fingerprint is a hash.

**A fingerprint cannot be reversed to a name.** `EventFacts.venue_id`'s own comment records
it: *"a fingerprint is a hash, and a hash cannot be reversed to 'the old city was
Brooklyn'"*. So the *old* venue is **not nameable**, and the body does not try to name it.
The "moved to [new location]" subject names the **new** venue, read from the catalog at
render time.

**The work item's technical note says the notice should carry what it needs "from the
propagation moment rather than reading `catalog` at render time".** That sentence is about
the *fact that changed*; the design doc's `SAVED_EVENT` precedent draws exactly the line
this item follows: **the snapshot holds the time, the display name resolves through
`catalog` at read time.** The time is a fact that changed and it comes from the change row;
the name and the venue are display facts and they come from the catalog.

### The one decision this item actually has to make: `detail_changed`

The work item asks for it explicitly: *"`detail_changed` either has copy or is explicitly
**not notified** — FR-53 is clear that not every change deserves a notification ('would be
engagement-trap'), and a venue detail edit is the likeliest candidate for silence."*

**The investigation found something the work item did not know, and it changes the answer.**

#### The discovery: the PRD's "moved to [new location]" subject lives inside `detail_changed`

FR-54 names four subjects. **Three of them map onto a kind of their own:**

| PRD subject | kind |
|---|---|
| "was cancelled." | `cancelled` |
| "was moved to [new date]." | `postponed` / `time_moved` |
| "is sold out." | `sold_out` |
| **"moved to [new location]."** | **???** |

**There is no kind for a venue move.** `domain.lifecycle.classify_change` puts a venue
change under `DETAIL_CHANGED` — because `venue_fingerprint` is in `_DETAIL_FACTS`
(`domain/lifecycle.py:76-78`) — and `detail_changed` also covers a title edit, a description
edit, a canonical-URL edit and a timezone-label edit. `tests/domain/test_lifecycle.py:105`
pins it: `{"venue_fingerprint": "v1:other"}` → `ChangeKind.DETAIL_CHANGED`.

**So `detail_changed` is not one thing.** It is the kind that carries **both** the PRD's
"moved to [new location]" subject **and** the noise the PRD says not to send. **Silencing it
wholesale would silence the PRD's own third subject** — which the work item asks for, and
which the PRD fixes verbatim.

#### The distinction is available, in the change row

**`_kind_facts` intersects the changed fields with the kind's facts**, so a change row
records **only what actually changed**:

| what changed | the `detail_changed` row carries |
|---|---|
| the venue | `before["venue_fingerprint"]`, `after["venue_fingerprint"]` |
| the title | `before["title"]`, `after["title"]` |
| the description | `before["description"]`, `after["description"]` |

**So the row says whether the venue moved.** A venue move and a title edit are the same
*kind* and different *facts*, and the facts are on the row.

**And the new venue's name resolves through `catalog` at render time** — the same read that
gives the title. The old venue is not nameable (a fingerprint is a hash), which is the
limitation `EventFacts.venue_id`'s own comment records, and the reason the subject names
only the **new** place.

#### The decision: `detail_changed` notifies only when the venue moved

**The subject is decided by what changed, not by the kind.**

| the change carries | notified? | subject |
|---|---|---|
| a venue move | **yes** | `EventPulse24: {title} moved to {where}.` — **the PRD's, verbatim** |
| anything else (title, description, URL, timezone label) | **no** | — |

**Why the rest is silent**, in the work item's own terms:

1. **FR-53 says not every change deserves a notification.** Its out-of-scope line: *"Real-time
   push notification on every state change (would be engagement-trap; only meaningful changes
   trigger user-facing notification per FR-54)."*
2. **A title or description edit has no reminder consequence.**
   `LIFECYCLE_SEND_BEHAVIOUR` maps `detail_changed` to `KEEP` and
   `LIFECYCLE_PERSONAL_BEHAVIOUR` maps it to `NONE`. **FR-54's body requirement is "what
   changed and what it means for the user's reminders" — and a title edit has no such
   meaning.** A notice with no consequence is exactly the notification FR-54 is trying not
   to send.
3. **It cannot say what changed.** The kind carries no detail, so a notice about a title
   edit could only say "the details changed" — which is not information.
4. **The user can see it for themselves.** A typo fix in a description is on the Detail
   Screen, which is where a description belongs.

**The silence is at the source** — `services.state_notices` refuses to raise the notice — and
so it covers **both** deliveries: no email and no in-app banner. FR-54 asks for "in-app +
email" as a pair, and splitting them would leave a banner with no email, which is a worse
experience than neither.

**So the rule is not "the kind is silent" but "the *change* is silent unless the venue
moved."** That is a fact about the change row, and it is a decision the *raise* path makes —
which means the raise path needs the change's `before`/`after`, not just its kind. **That is
the one signature change in this item**, and it is a real one: `raise_state_notice` currently
takes `change_kind` and nothing else, and it will now take the change's facts.

**The counter-argument, and why it loses.** A title change is arguably meaningful — a venue
renaming "Rooftop Cinema" to "Rooftop Cinema: Late Night" is the kind of thing a user
should know about. **But the change row does distinguish it** — `after["title"]` is present.
**So the argument is not that the distinction is unavailable; it is that a title change is
not worth an email.** It is a rename on a page the user can open, and FR-53 calls
notification-on-every-change an engagement-trap. **If a title change should notify, that is
a `title_changed` kind** — with its own precedence position, its own subject and its own
ingestion rule. **That is a follow-up, and it is recorded as one.**

**`superseded` is the other kind the PRD does not name, and unlike `detail_changed` it is
not silenced.** A supersede means the event moved beyond the ±30-day window and a
*different* event replaced it. The user's saved event is cancelled
(`LIFECYCLE_SEND_BEHAVIOUR` maps it to `CANCEL`), so they lose the event entirely —
**silence would leave them with reminders that never fire and a Timeline entry for an event
that no longer exists.** It gets a subject, in the same register as `cancelled`.

### The subject table

| the change | subject | whose |
|---|---|---|
| `cancelled` | `EventPulse24: {name} was cancelled.` | PRD verbatim |
| `postponed`, `time_moved` | `EventPulse24: {name} was moved to {new date}.` | PRD verbatim |
| `sold_out` | `EventPulse24: {name} is sold out.` | PRD verbatim |
| **a venue move** (`detail_changed` whose facts name a venue) | `EventPulse24: {name} moved to {new location}.` | **PRD verbatim** |
| `superseded` | `EventPulse24: {name} was replaced by a new event.` | **ours** |
| `reinstated` | `EventPulse24: {name} is back on.` | **ours** |
| **a title, description, URL or timezone edit** (`detail_changed` otherwise) | *(no notice — silenced at the source)* | **our decision** |

**So the PRD's four subjects are all there, and the three kinds it does not name are
answered.** `detail_changed` is the one kind that appears twice — once with the PRD's
subject, once with no subject at all — and the *change's facts* say which.

**`postponed` and `time_moved` share the PRD's "was moved to [new date]" subject.** FR-54's
second consequence bullet names "a saved event that is postponed"; `time_moved` is a
postponement the catalog recorded without a status change. **The user's world is the same
in both cases: the event is at a new time.** They are not told which internal kind produced
it — the PRD's four bullets are written for the user's world, not the schema's.

**`reinstated` is ours, and the work item says so.** *"It is the seventh kind, it re-mints
reminders, and the PRD names no subject for it. This item writes one in the same register
and records that it is ours, not the PRD's."*

### The link: one rule, not two

**The AC says "A link to the event's Detail screen, where the banner and the mute control
live."** The Detail Screen is the frontend route `/events/{event_id}` — the personalized
one, where the banner and the mute live.

**Six of the seven kinds link to the saved event's own Detail Screen.** For a `superseded`
event that page is gone: `get_public_event_detail` raises for a superseded event (the
public catalog excludes superseded rows), and the personalized Detail Screen 404s with it.

**So for `superseded` the link points at the replacement's Detail Screen** — and the
replacement's id is `after["superseded_by"]` on the change row. **One rule: the link is the
page where the change is visible.** For six kinds that is the event's own page; for a
supersede that is the event that replaced it.

**The link is a tracked CTA**, like the digest's. `click_url_for` signs the destination, so
it cannot be edited into an open redirect, and SM-2 measures the click. The notice's link is
the thing the user does next: go and see the change, and mute it.

**And the Detail Screen is where the mute lives** — which is why the notice needs no
unsubscribe link of its own, and why the body must not imply one exists.

### The body: what changed and what it means

The work item's AC: *"The body states **what changed and what it means for the user's
reminders** — 'your reminders have been rescheduled' / 'your reminders have been cancelled'
— because the reminder consequence is the reason the email is correctness-critical rather
than informational."*

**This is where the body earns its place.** A subject saying "was cancelled" tells the user
the fact; the body tells them their evening's plan has been handled for them.

| kind | the body's reminder line |
|---|---|
| `cancelled` | *"Your reminders for this event have been cancelled."* |
| `superseded` | *"Your reminders for this event have been cancelled."* + the replacement's link |
| `postponed`, `time_moved` | *"Your reminders have been rescheduled to the new time."* |
| `reinstated` | *"Your reminders are back on."* |
| `sold_out` | *"Your reminders are unchanged."* + *"Tickets are no longer available."* |

**The reminder line is derived from `LIFECYCLE_SEND_BEHAVIOUR`, not from a second table.**
That table is what the *sends* already follow — `CANCEL` → cancelled, `REMINT` →
rescheduled, `KEEP` → unchanged. **Reusing it is the point:** the body's promise about the
reminders must be the same promise the send machinery kept. Two tables would let the email
say "your reminders have been cancelled" while the reminders still fire — **and that is
exactly the bug class this whole intent exists to prevent.**

**`sold_out`'s reminder consequence is "unchanged"** — `KEEP`, so the reminders still fire
for a sold-out event. Saying "unchanged" is honest and worth saying: a user who bought a
ticket needs to know the reminder is still coming.

**`reinstated`'s is "back on"** — `REMINT`, so the reminders are re-minted and fire again.

**The work item's subject line for `sold_out` mentions the CTA:** *"The Detail Screen shows
the 'Sold Out' badge and removes the 'Save Reminder' CTA."* That is the frontend's half —
`frontend-pulse-card-state` and `notice-and-mute-api`. **The email does not try to be the
badge.** It says the event is sold out and links to the page that shows it.

### The escaping

The work item: *"The event name is rendered safely for an untrusted ingested string — no
injection into the subject line, no unescaped HTML in the body."*

**The title is an ingested string.** It comes from a third-party feed and this codebase does
not control it. Three places it could hurt:

1. **The subject line.** A title containing `\n` is a header-injection vector — a title of
   `"Jazz\nBcc: attacker@example.com"` would, in a naive implementation, add a header.
2. **The HTML body.** A title of `"<script>alert(1)</script>"` is XSS in every HTML mail
   client that renders it. **Django's template engine autoescapes by default** — `{{ title }}`
   is escaped, `{{ title|safe }}` is not. The existing templates use `{{ display_title }}`
   with no filter, so **the HTML body is already escaped** and stays that way.
3. **The text body.** Plain text is not interpreted, so there is no injection — but a title
   with a newline in it would break the body's line structure.

**The subject is the real work.** `EmailMessage.subject` is a plain `str` handed to the
provider, and a newline in it is a header injection. So the title is folded to one line:

```python
def _one_line(title: str) -> str:
    """One line, no newlines, no control characters."""
    return " ".join(title.split())
```

**`" ".join(title.split())` collapses every whitespace run — newlines, tabs, non-breaking
spaces — to a single space.** It is the standard fold, it is one line, and it cannot leave a
newline behind. It also collapses a title's *legitimate* internal newlines, which is the
right trade: a subject is one line.

**The fold happens once, in the facts-gathering layer**, so the subject, the text body and
the HTML body cannot disagree about what the title is.

**The AC's "a missing or empty event name degrades to something legible rather than
`EventPulse24: was cancelled.`"** — the existing `email_templates` convention already
answers this: `facts.title or "your saved event"`. So a missing name gives
`EventPulse24: your saved event was cancelled.` — legible, and it invents no title. **The
existing convention is reused rather than a second one invented**;
`test_a_reminder_without_a_title_says_the_event_was_saved` is the precedent.

**An empty string is not `None`.** `facts.title or "your saved event"` handles both — an
empty string is falsy. And a whitespace-only title folds to `""`, which is also falsy, so
**the fold happens first and the fallback is applied to the folded value.**

**The HTML body escapes the folded title too.** A title of `<b>bold</b>` must show as
literal text in the HTML, not as bold — and the template's `{{ display_title }}` with no
filter does exactly that.

### The unsubscribe

The work item: *"**No unsubscribe URL** on a transactional send, and no footer implying one
exists."*

`render_state_notice` already sets `unsubscribe_url=None`, and the state notice is
transactional, so `EmailPort.send` does not demand one. **Two things must hold:**

1. **`EmailMessage.unsubscribe_url is None`** — the port-level fact.
2. **No footer implies one exists.** The reminder body says *"Stop reminders for this
   event"* — a *reminder* opt-out, not a list unsubscribe. **The state notice body must not
   carry that link**, because the notice is not a reminder: the reminders for a cancelled
   event have been *cancelled*, and a "stop reminders for this event" link on a cancellation
   email is offering to stop something that has already stopped.

**The mute is the opt-out, and it lives on the Detail Screen** — which the body links to.
**No footer, no link, no hint.** The AC is met by what is absent, and a test asserts the
absence.

### The dispatch: two questions, asked in order

**The dispatch is on `row.kind` *and* the stream — not instead of the stream.**

The stream is the *obligation* (AD-20: the bulk stream owes an unsubscribe URL). The kind
is the *content*. **Both matter, and they are different questions.** A state notice is
transactional *and* a state notice; the stream says what the provider owes, the kind says
what the body says.

```python
if row.kind == ScheduledSend.Kind.STATE_NOTICE.value:
    return render_state_notice_row(row, address)   # ← the new branch
if stream is Stream.BULK:
    return render_digest(row, address)
return render_transactional(row, address)
```

**Why the kind check comes first.** A state notice is transactional, so it would otherwise
reach the transactional branch — which renders a reminder. Putting the kind check first is
what makes the branch reachable at all. And it is honest about the ordering: **the content
decides the body; the stream decides the obligations.** A bulk row that were somehow a state
notice still gets the bulk renderer, because AD-20's obligation follows the stream.

### A missing notice cancels the send

**The renderer needs the notice row for the kind. What if it is gone?**

A notice row can be deleted by the cap's supersede path — which cancels the send, so the
row is not `pending` and is never claimed. It can also be purged by retention.

**A missing notice means there is no kind, and a generic subject is the one thing FR-54
forbids.** So the renderer raises `MissingTargetError` — the sweep's existing, tested
mechanism for "the thing this row is about is not there any more" — and the sweep cancels
the row. **The same treatment a vanished reminder target gets.**

### What this item does not do

- **It does not add the in-app surfaces.** The digest strip and the Detail banner are
  `notice-and-mute-api`'s and `frontend-digest-strip-and-detail-banner`'s.
- **It does not add the mute's API.** `notice-and-mute-api`.
- **It does not touch the frontend.** `frontend-pulse-card-state` and
  `frontend-digest-strip-and-detail-banner`.
- **It does not add a `title_changed` kind.** The reasoning above names it as the right
  follow-up; adding it here would mean a new `ChangeKind`, a new precedence position, a new
  subject and a new ingestion rule — a different item.
- **It does not add push.** FR-54 defers it to Phase 2+.
- **It does not change the cap, the mute or the stream.** Those are
  `state-change-notice-model`'s.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/domain/notices.py` | The pure vocabulary: the subject per kind, the reminder consequence per kind, the silent kinds |
| `backend/tests/delivery/test_state_notice_email.py` | The subjects per kind, the escaping, the empty name, the dispatch, the muted case |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/delivery/services/email_templates.py` | `StateNoticeFacts` gains the new fields; `render_state_notice` builds the subject from the kind and folds the title |
| `backend/apps/delivery/templates/delivery/state_notice.txt` | The body says what changed *and* what it means, with the Detail link and no unsubscribe |
| `backend/apps/delivery/templates/delivery/state_notice.html` | The same, in HTML, with the title escaped by Django as it is today |
| `backend/apps/delivery/services/delivery_messages.py` | The `state_notice` dispatch branch; the gathering for a notice's facts |
| `backend/apps/delivery/services/state_notices.py` | `raise_state_notice` takes the change's facts and raises nothing for a `detail_changed` that is not a venue move |
| `backend/tests/delivery/test_email_templates.py` | The existing `Update: {title}` assertion becomes the PRD's subjects; the fold |
| `backend/tests/delivery/test_delivery_messages.py` | The dispatch: a state notice row renders a notice, not a reminder |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/delivery/test_state_notice_email.py` | One subject per change (the literal strings), the escaping case, the empty-name case, the reminder-consequence line, no unsubscribe, the Detail link, a muted event producing no send, a title edit producing no notice, a venue move producing the PRD's |
| `backend/tests/delivery/test_email_templates.py` | The subject is the PRD's, not `Update: {title}`; the fold; the voice; both bodies always |
| `backend/tests/delivery/test_delivery_messages.py` | A `state_notice` row renders a notice, not a reminder; a missing notice cancels the send; a superseded notice links to the replacement |

## Technical Details

### The pure vocabulary, in `domain/`

`domain` is stdlib-only plus `shared.constants` and `shared.ids` (AD-2), and
`LIFECYCLE_SEND_BEHAVIOUR` is in `shared.constants` — so the reminder consequence is
derivable in `domain` without reaching into an app.

```python
# domain/notices.py
NOTICE_SUBJECTS: dict[str, str]        # kind → subject template
REMINDER_CONSEQUENCE: dict[str, str]   # kind → what the body says about the reminders
SILENT_KINDS: frozenset[str]           # the kinds that raise no notice
```

**`REMINDER_CONSEQUENCE` is derived from `LIFECYCLE_SEND_BEHAVIOUR` at import time**, not
written out — so the body and the send machinery cannot disagree:

| `LIFECYCLE_SEND_BEHAVIOUR` | the body's line |
|---|---|
| `CANCEL` | cancelled |
| `REMINT` | rescheduled |
| `KEEP` | unchanged |

**`reinstated` is `REMINT`, so it says "rescheduled" — but the PRD's world says the event is
*back*.** The subject says "is back on" and the body's reminder line says the reminders are
back on. **So `reinstated` needs its own line, not the `REMINT` one.** The table therefore
has a per-kind entry, and the derivation is a *default* the table can override — with the
override explicit rather than implicit, so a reader can see which kind says something other
than its behaviour implies.

**`SILENT_KINDS = {ChangeKind.DETAIL_CHANGED}`** — and `domain/notices.py` states the
reasoning in its own docstring, so the decision is not only in this plan.

### The subject, built in one place

**The subject is assembled from the kind and the folded title, never from a template
string with a `{}` inside a dict of formats.** A template with a placeholder and a
`.format()` call is a `KeyError` waiting for a kind nobody tested. **A function per kind,
or a mapping of kind → a small builder, with a fallback that raises** — a kind with no
subject is a programming error, not something to paper over with a generic subject.

**The generic-subject question has an answer: there isn't one.** If `domain.lifecycle` gains
a kind and `domain.notices` does not learn it, the renderer **must fail loudly** — a
notice with a wrong subject is worse than a notice that did not go out, because the user
reads "EventPulse24: your saved event was cancelled" about an event that was not
cancelled. **The exception is caught by the sweep, which cancels the row** — so the failure
is a cancelled send, not a wrong email. That is the right failure.

### The title's fold, and where it happens

**The fold is in the facts-gathering layer** (`delivery_messages`), not in the template and
not in `email_templates`. `email_templates` is the pure renderer: facts in, a body out, no
logic. **A fold is logic.** So `email_templates` receives an already-folded title, and its
own job is to choose the subject and render the body.

**But the fallback lives in `email_templates`,** because the fallback is a *presentation*
decision ("your saved event") and it already lives there for the reminder and the digest.
**So the facts carry the raw title, the fold happens in the gathering, and the fallback
happens in the renderer.** Two steps, two places, each with one reason.

### The gatherer

```python
def _state_notice_facts(row: ScheduledSend) -> StateNoticeFacts:
    """Everything a state notice's body quotes, gathered once."""
```

1. **The notice row** — `StateChangeNotice` by `(user_id, state_change_id)`. The
   `state_change_id` is inside `row.send_key`, and `send_keys` owns the key's shape, so
   **the parser lives beside the builder** — the same rule
   `digest_local_date_from_key` already follows. **A missing notice raises
   `MissingTargetError`.**
2. **The change row** — `outbox.get_state_change(state_change_id)`. **Its `before`/`after`
   carry the times and the replacement's id.** A missing change raises `MissingTargetError`
   too — the same reasoning: the notice is about a change that no longer exists.
3. **The event** — `get_public_event(event_id=row.target_id)`. **The title and the venue's
   name.** A missing event is **not** an error: the catalog may have dropped it, and the
   body then says "your saved event" — the same treatment `_public_event_facts` gives a
   reminder. **But the venue's name for a `moved to [new location]` subject is then
   missing**, and the subject degrades to `EventPulse24: {name} moved location.` — hmm.

Let me settle that: **the location subject's placeholder is the venue's name, and if the
venue is unknown the subject cannot be built.** The honest form is `EventPulse24: {name}
moved to a new location.` — which says what happened without naming a place the catalog
cannot name. **That is a third form of the PRD's subject, and it is ours** (a degradation of
the PRD's), and it is recorded as such.

### The renderer's public shape

```python
def render_state_notice_row(row: ScheduledSend, address: str) -> EmailMessage:
    """Render a state-change notice's email."""
```

**It is a separate function, not a branch inside `render_transactional`.** The two have
different obligations (the notice has no reminder link), different facts (a notice needs a
kind), and different failure modes (a missing notice cancels the row). **Merging them
would make the notice's obligations optional**, which is the reason
`render_transactional` and `render_digest` are already two functions.

## Based on Design Doc

None. This is a `confirm`-mode item: no design doc, one checkpoint — this plan. The
`state-change-notice-model` design doc is followed where it settles something (the notice
is the record and the email is one of its deliveries; `SAVED_EVENT`'s split between a
held time and a catalog-resolved display name), and this plan records where it left
something open (`superseded`'s subject, `reinstated`'s subject, and which `detail_changed`
changes are worth a notice).

---
*Plan awaiting approval.*

---

---
run: run-eventpulse24-025
work_item: notice-and-mute-api
intent: event-state-sync
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at: 2026-11-10
---

# Implementation Plan: The strip needs something to read and the mute needs somewhere to write

## Approach

FR-54's in-app half is a dismissible strip on the digest home and a banner on the Detail
Screen. FR-55's per-event mute needs a write from the Detail Screen. Both need a **read**,
and the Detail Screen needs **both facts in one round trip** so the banner and the mute
control cannot disagree.

The previous work item built the notice row and the email but deliberately stopped at the
surface boundary: `list_undismissed_notices` was **unbounded**, `dismiss_notice` and
`mute_event_notices` existed but nothing called them over HTTP, and the Detail read knew
nothing about notices or mutes.

### The endpoints

A **new router file** `backend/apps/delivery/notices_api.py`, mounted at **`/api/notices`**.

| Method | Path | Handler | Response |
|---|---|---|---|
| `GET` | `/api/notices` | `get_notices` | `200: NoticeListOut`, `401`, `403` |
| `POST` | `/api/notices/{notice_id}/dismiss` | `post_dismiss_notice` | `200: NoticeDismissOut`, `401`, `403`, `404` |
| `PUT` | `/api/notices/events/{event_id}/mute` | `put_event_mute` | `200: EventMuteOut`, `401`, `403` |
| `DELETE` | `/api/notices/events/{event_id}/mute` | `delete_event_mute` | `200: EventMuteOut`, `401`, `403` |

**Why a new file and not `apps/delivery/api.py`.** The mount path is public contract (AD-19).
`/api/reminders` names **Reminder Plans**; a state-change notice is not one, and the router's
path shape (`/{target_kind}/{target_id}`) would become ambiguous with a notice id. `delivery`
already has three routers; a fourth follows the established pattern.

**Why `PUT`/`DELETE` for the mute rather than one `POST` with a body flag.** A mute is a
*state* with two values; setting a state is `PUT`, clearing it is `DELETE`. **No request body
at all**, so the client cannot encode "clear this" as a field that could be confused with
"leave it alone".

**Why `POST …/dismiss` rather than `DELETE /api/notices/{id}`.** The row is **not** deleted —
FR-54's "never repeats" and the daily cap depend on the row surviving. A `DELETE` that does
not delete is a lie in the method.

### The service layer

`backend/apps/delivery/services/notice_state.py` — a **leaf** read module:
`NoticeSummary`, `EventNoticeState`, `read_event_notice_state`, `summarize_notice`.

**Two queries, both scoped by `user_id`** — the mute is an `EXISTS` and the notice is the
newest row for the pair. They are not merged: a cross-table join would answer "is there a
notice" only for events that also have a mute row.

**It reads the two models directly**, and the reason is the **model boundary**: `state_notices`
publishes reads that return model instances, and handing one to `personalization` would put a
reference to `apps.delivery.models` in another app's hands. The projection happens **inside
the owning app**.

### The two ambiguities the AC left open

**1. "Unseen" in criterion 1 — the strip is keyed on `dismissed_at`, not `seen_at`.** The
service's own rule is explicit (*"the strip is a queue, and closing an item should empty
it"*), and criterion 2's own wording says dismissal is what makes "one-time, never repeats"
true. A `GET` that writes `seen_at` is exactly the shape `detail_api.py` refuses (*"a `GET`
that writes is the shape CSRF exists to stop"*), so **`mark_seen` is not called by this API
at all.**

**2. "Undismissed notice" in criterion 4 — the banner reports the newest notice whatever its
dismissal state.** Dismissing the strip on the digest home must not hide *"this event was
cancelled"* from the event's own page. `dismissed_at` rides on the wire so the client can
tell the two states apart.

### The dismiss 404-vs-idempotence resolution

`dismiss_notice` returns a `bool` collapsing three cases: not yours, does not exist,
already dismissed. Criterion 6 wants the third to answer success; criterion 5 wants the first
two refused.

- `changed == True` → **200** `{id, dismissed: true, changed: true}` — **zero** extra queries.
- `changed == False` → one extra **user-scoped** existence check:
  - yours, already dismissed → **200** `{id, dismissed: true, changed: false}`
  - not yours, or no such id → **404**, and **the same 404 for both**.

A 403 would confirm that the record exists, so the endpoint could be used to probe for other
users' notice ids. The extra query runs **only** on the `changed == False` path, so the
common case costs nothing.

### The bound

`list_undismissed_notices` gains a **required keyword-only `limit: int`** — not optional with
a default, because a default leaves the unbounded call reachable. The API takes **no
`?limit=` query parameter**: the bound is a product decision (FR-54's "one calm correction"),
so it belongs in the server.

`NOTICE_STRIP_LIMIT = 5` — "a few, not a history". Unlike `SAVERS_PAGE` (a page, because
propagation must reach *every* saver), dropping the tail here loses nothing.

### The architecture guards

`checkers.py::surface_files()` — the current glob is `apps/*/api.py`, which matches only files
named exactly `api.py`. It therefore **misses** `apps/catalog/preview_api.py`,
`apps/delivery/email_api.py`, `apps/delivery/preferences_api.py` and
`apps/personalization/detail_api.py` — four surface files that are **exempt from AD-5
today**. **Fix: discover by shape**, the same rule the AD-11 guard already uses.

**One discovery, two rules.** `api_modules()` (routers only, used by AD-11) and
`surface_files()` (admins + routers, used by AD-5) — two copies of one rule would be free to
disagree about what a request handler is, and the disagreement would be invisible.

## Files

### New

| File | Contents |
|---|---|
| `backend/apps/delivery/notices_api.py` | The router and the four handlers. |
| `backend/apps/delivery/services/notice_state.py` | The leaf read module. |
| `backend/tests/delivery/test_notices_api.py` | The endpoint contract tests. |
| `backend/tests/delivery/test_notice_state.py` | The combined-read service tests. |

### Modified

| File | Change |
|---|---|
| `backend/shared/constants.py` | **New:** `NOTICE_STRIP_LIMIT = 5`. |
| `backend/apps/delivery/services/state_notices.py` | `limit` on `list_undismissed_notices`; **new** `notice_belongs_to_user`. |
| `backend/apps/delivery/schemas.py` | **New:** `NoticeOut`, `NoticeListOut`, `NoticeDismissOut`, `EventMuteOut`. |
| `backend/apps/personalization/schemas.py` | **New:** `DetailNoticeOut`; `DetailPersonalOut` gains `muted` and `notice`. |
| `backend/apps/personalization/services/detail_read.py` | The two facts, read **after** the anonymous early return. |
| `backend/apps/personalization/detail_api.py` | The two new fields projected. |
| `backend/config/api.py` | The router mounted at `/api/notices`. |
| `backend/tests/architecture/checkers.py` | `surface_files()` widened; `api_modules()` split out. |
| `backend/tests/architecture/test_no_direct_writes.py` | The count assertion → 18. |
| `backend/tests/architecture/test_digest_composition_separation.py` | `REQUEST_MODULES` gains the notices router. |
| `backend/tests/delivery/test_state_notices.py` | The three `list_undismissed_notices` calls gain `limit=`; a bound-at-the-service test. |
| `backend/tests/personalization/test_event_detail_api.py` | The new Detail tests; the pinned shape widened; the query-count bound widened. |
| `frontend/lib/api/openapi.json` | **Regenerated.** |
| `frontend/lib/api/schema.ts` | **Regenerated.** |

### Deliberately unchanged

- `backend/apps/delivery/models.py` — both models exist and need nothing.
- `backend/apps/delivery/services/mutes.py` — `is_muted`, `mute_event_notices`,
  `unmute_event_notices`, `MuteResult` are complete as-is.
- `backend/tests/architecture/test_write_ownership.py` — `TABLE_OWNERS` **already** maps both
  notice tables to `delivery`. No new entry.

## Implementation order

1. `shared/constants.py` — `NOTICE_STRIP_LIMIT = 5`.
2. `apps/delivery/services/state_notices.py` — `limit`; `notice_belongs_to_user`.
3. `apps/delivery/services/notice_state.py` — the leaf read module.
4. `apps/delivery/schemas.py` — the four new shapes.
5. `apps/delivery/notices_api.py` — the router and the four handlers.
6. `config/api.py` — mount at `/api/notices`.
7. `apps/personalization/` — the two new Detail fields.
8. Architecture guards — the discovery, the counts, `REQUEST_MODULES`.
9. Tests — the three test files.
10. `make openapi && make client`; commit the two generated artefacts.
11. The full suite, ruff, and `lint-imports`.

**The services come before the API so the surface is a projection of a finished read; the
guards come before the tests so the new surface file is covered from the moment it exists;
the contract is regenerated last so the committed artefacts match the final API.**

## Verification

**Static checks** — `ruff check .`, `ruff format --check .`, `lint-imports` (19 contracts kept,
0 broken).

**The new and changed tests** — the three test files, `tests/architecture/`, and
`tests/api/test_contract.py`.

**The whole backend suite** — `make test-backend`. The **16 pre-existing failures** from the
`timeline-and-conflicts` item (date-expired fixtures) are expected and unrelated; the
baseline is **{0} new failures**, confirmed against a clean `git worktree` at `HEAD`.

**The contract** — `make openapi && make client` must leave `frontend/lib/api/openapi.json`
and `frontend/lib/api/schema.ts` **clean in git**.

**Manual check of the four guards that change** — `surface_files()` finds 18 files including
the four previously-unchecked ones, and none of them writes through the ORM; the count is
18; `REQUEST_MODULES` and the discovery agree; the Detail read's personal-query bound is
**constant**.

**The end-to-end path** — sign in → `GET /api/notices` → `POST /api/notices/{id}/dismiss` →
the notice leaves the strip → `PUT /api/notices/events/{id}/mute` → `GET /api/events/{id}`
reports `personal.muted is true` and `personal.notice` still names the event's newest
notice.

---

---
run: run-eventpulse24-025
work_item: frontend-pulse-card-state
intent: event-state-sync
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at: 2026-11-10
---

# Implementation Plan: The Pulse Card has to be able to say what happened to the event

## Approach

FR-53's detection has been in the backend since `digest-card-state-fields`; FR-54's notice
has been composed and sent since `notice-composition-and-email`. **Neither one reaches the
reader.** The Pulse Card reads neither `status` nor `is_sold_out`, so a card whose event
was cancelled — or sold out, or postponed — renders exactly as a live one does, and a
reader is told nothing.

**This item is the card's state treatment.** Three pieces, in dependency order:

1. **One shared table of the words** (`frontend/lib/event-state.ts`) — the sentances and the
   labels the card, the public page, the city card and the Detail screen all read.
2. **The badge** (`frontend/components/state/event-state-badge.tsx`) — one pill, three
   states, distinguished by **glyph and label**, never by a new colour.
3. **The card renders it** (`frontend/components/digest/pulse-card.tsx`) — the badge in the
   right-side zone, and the state named in the card's accessible name.

### The decisions this item actually turns on

**1. The design system has a sold-out badge and no cancelled or postponed one.** That is a
real gap in `DESIGN.md` §`component.badge.soldout` and in the mockup, which covers only
sold out. So the item **extends the sold-out anatomy** rather than inventing a second
pill: the same `{color.surface.subtle}` fill, the same 1px `{color.border.strong}` stroke,
the same `{radius.subtle}`, the same ink label. **The three states differ by their glyph
and their label, and by nothing else** — no new colour token, no new spacing token, no new
CSS variable. A second pill for cancellation would have been a second visual language for
one kind of fact.

**2. The sold-out glyph cannot be the design's `●`.** This is a collision *inside the
design document*, and it is the reason the item needs an amendment at all.
`component.indicator.conflict` is "a 6px **filled circle** in `{color.warn.amber}`", and
`{color.signal.warn}` and `{color.warn.amber}` are **the same hex** in both themes — so a
`●` in the badge and the conflict indicator would be the same shape in the same colour at
the same scale, **in the same card**. `DESIGN.md` already requires the conflict indicator
to be "distinct in shape and position from the Source Badge and Confidence Pulse", and the
badge is a third signal on that card. So the sold-out glyph is **hollow** (`⊘`) where the
conflict dot is solid. Cancelled is `✕` (a strike); postponed is `↦` (a deferral) —
deliberately **not** a clock, because a postponed event has no new time yet
(`POSTPONED = "postponed"  # date to be announced`).

**3. The lifecycle state wins over the sold-out flag.** `DigestCardOut`'s own docstring
says "An event can be `scheduled` and sold out at the same time, so the two are not
collapsed into one 'state' enum" — so the frontend keeps **both** fields, and only the
*badge* picks one. It picks the lifecycle state: a badge reading "Sold out" on a
cancelled event would invite a reader to wait for tickets for an event that is not
happening.

**4. An unknown status shows nothing.** The vocabulary is the backend's, and `status` is
`string | null` in the generated schema. `scheduled`, `null` and a status the frontend has
never heard of all mean "no state" (ASSUMPTION-9). A card rendering "unknown" would be
inventing a claim about the world.

### The badge does not go in the trust row

The trust row already holds the conflict indicator, the five-dot confidence pulse and the
source badge, and it is a `flex items-center gap-2` that **does not wrap**. A fourth
element with a visible label would overflow a 360px viewport. So the badge gets **its own
row, immediately above the title row**, right-aligned — which is the right-side zone
`DESIGN.md` names, and a *different place* from the conflict mark as well as a different
shape.

## Files to Create

| File | Contents |
|---|---|
| `frontend/lib/event-state.ts` | The shared table: `STATUS_LINES`, `statusLineFor`, `SOLD_OUT_LINE`, `SOLD_OUT_LABEL`, `CardState`, `cardStateFor`, `STATE_LABELS`. |
| `frontend/components/state/event-state-badge.tsx` | `EventStateBadge` — one pill, three glyphs, one colour. |
| `frontend/components/digest/pulse-card-state.test.tsx` | The rendering tests, per state. |
| `frontend/tests/event-state.test.ts` | The vocabulary-drift guard, read against the backend's `Event.Status`. |
| `frontend/tests/event-state-badge-boundary.test.ts` | The badge's structural rules, asserted against the source. |

## Files to Modify

| File | Change |
|---|---|
| `frontend/components/digest/pulse-card.tsx` | The badge block; the state in `accessibleName`. |
| `frontend/components/public-event/public-event-page.tsx` | The local `STATUS_LINES` table removed; the shared one imported. |
| `frontend/components/city-page/city-event-card.tsx` | The sold-out sentence now comes from the shared table. |
| `frontend/app/events/[id]/page.tsx` | The sold-out sentence now comes from the shared table. |
| `frontend/tests/digest-home-a11y.test.tsx` | Two axe-core cases: the three states together, and sold-out-and-conflicted. |
| `…/ux-designs/…/DESIGN.md` | Amendment **A-22**: the three-state badge, the `⊘` glyph, the corrected lifecycle trigger. |
| `…/ux-designs/…/EXPERIENCE.md` | The badge's anatomy, placement, CTA pairing and accessibility, extended to the three states. |

## Tests

- **`components/digest/pulse-card-state.test.tsx`** — per state: the label, the accessible
  name, the affordances, the coexistence with the conflict indicator, the unknown-status
  case, the glyph shapes, and that the badge is not a control.
- **`tests/event-state.test.ts`** — the backend's `Event.Status` is parsed out of
  `backend/apps/ingestion/models.py` and compared against the frontend's vocabulary; the
  five consuming surfaces are checked for literal copies of the sentences *and* of the
  labels.
- **`tests/event-state-badge-boundary.test.ts`** — the rules a rendering test cannot see:
  no literal hex, no raw `rgb()`/`hsl()`, every colour from a token, no motion class, the
  label in ink rather than the signal colour, three different glyphs, and none of them the
  conflict indicator's filled circle.
- **`tests/digest-home-a11y.test.tsx`** — two new axe-core audits.

## Verification

**Static checks** — `npx tsc --noEmit` clean, `npx eslint .` clean.

**The new and changed tests** — the four files above.

**The whole frontend suite** — `npx vitest run`. The baseline at `HEAD` is **99 files /
1577 tests**; this item must land with **zero new failures**.

**Node 24 is required.** `package.json`'s `engines` says `>=24.15`; under Node 20 every
component test file is silently skipped and the suite reports a false pass.

## Based on Design Doc

`DESIGN.md` §`component.badge.soldout` (amended by A-22), §`component.indicator.conflict`;
`EXPERIENCE.md` §`Component.Badge.SoldOut`. PRD FR-53, FR-54.

---

## Work Item: frontend-digest-strip-and-detail-banner

### Approach

The in-app half of FR-54, plus FR-55's per-event mute. Two surfaces, one API.

**The API is already built** (`notice-and-mute-api`, completed): `GET /api/notices`,
`POST /api/notices/{notice_id}/dismiss`, and `PUT`/`DELETE /api/notices/events/{event_id}/mute`.
The generated contract carries `NoticeOut`, `NoticeListOut`, `NoticeDismissOut`,
`EventMuteOut`, and — on the **existing** Detail read — `DetailPersonalOut.muted` and
`DetailPersonalOut.notice`. **So the banner and the mute need no new read at all**: the
Detail screen already fetches both facts.

**What needs building is three surfaces and one shared vocabulary.**

1. **`frontend/lib/notice-copy.ts`** — the wording table. The banner must "state the change
   and what happened to the user's reminders", and the backend already owns that wording:
   `domain/notices.py`'s `NOTICE_SUBJECTS` (what changed) and `REMINDER_CONSEQUENCE` (what
   it means for your reminders). The frontend **restates** that table — it cannot import
   Python — and a test parses the backend's table out of `backend/domain/notices.py` and
   fails on drift, exactly as `frontend/tests/event-state.test.ts` already does for
   `Event.Status`. **One vocabulary, two languages, one test holding them together.**

2. **`frontend/components/state/notice-strip.tsx`** — the dismissible strip on the digest
   home. It is a **client island** (it dismisses, which is a write), mounted between
   `<DigestHeader>` and the digest's cards. It renders **nothing** when there are no
   notices.

3. **`frontend/components/state/detail-notice-banner.tsx`** — the persistent banner on the
   Detail screen, plus **`frontend/components/state/detail-mute-control.tsx`** — FR-55's
   per-event mute.

**The four decisions this item makes that its wording leaves open**, resolved below and
stated in the code's own docstrings:

- **The strip renders nothing at all when there are no notices.** Not an empty container, not
  a collapsed one, not a `hidden` one — **no element in the DOM**. The AC says "with no
  unseen notices … the home screen renders exactly as it does today, with no layout shift".
  An empty `<section>` is a layout shift waiting for a stylesheet; no element is not.
- **The strip's own read is a separate request from the digest's.** `DigestOut` carries no
  notices field, and the AC's "no extra request on the critical path if the digest response
  can carry the flag" is a conditional the API does not satisfy — so the strip makes its own
  `GET /api/notices`. It is **not** on the critical path: the strip is a client island that
  fetches after mount, so the digest's cards render without waiting for it.
- **The strip announces through a bare `aria-live="polite"`, not a second `role="status"`.**
  The digest home already carries exactly one `role="status"` — "Pulse Digest ready, N
  events for today." (`app/page.tsx:133`) — and `EXPERIENCE.md` §`Live Regions` says the
  digest's ready line is a live region. Two status regions would make "which one is the
  page talking?" a question the DOM cannot answer. **And the strip does not steal focus**:
  it is not `role="alert"`, it moves no focus, and it renders no focusable element until
  the user tabs into it.
- **The banner shows the notice whether or not it has been dismissed**, with the dismissal
  stated. That is the backend's deliberate rule (`delivery.services.notice_state`: the
  banner is about *this* event, which the user navigated to on purpose, so dismissing the
  strip on the digest home must not hide "this event was cancelled" from the event's own
  page). The banner's copy says so — "You've already dismissed this" — rather than
  pretending the correction never happened.

### The register, and why it is `component.emptystate.quiet`'s

The work item is emphatic: *"Register matters more than usual here. Everything the user is
being told is bad news about plans they made, delivered by a product whose positioning is
calm."* `EXPERIENCE.md` §5 is canonical and stricter than both `DESIGN.md` and the mockups
— the empty-state precedent, where a terracotta primary button in the mockup was ruled a
mockup bug.

**So: no terracotta, no `role="alert"`, no red, no exclamation marks, no "Urgent".** The
strip's vocabulary is the empty state's — a quiet card with a border and a subtle fill, one
line of plain ink, an underlined text control, no fill. The banner is the same weight.

**And the copy is the product's voice, not a notification service's.** `EXPERIENCE.md` §3's
microcopy contract has a row for the state-change email: *"EventPulse24: {event name} was
moved to {new date}"* — **not** *"⚠️ Important update about your event!"*. The strip and
the banner say the same thing in the same register.

### The banner's two sentences

The AC: *"stating the change and what happened to the user's reminders."* Two sentences, two
tables:

- **What changed** — the change kind's subject, without the email's `EventPulse24: ` prefix
  and with the event's name **not** in it (the notice carries no title; the Detail screen
  already has the title, and AD-13 keeps titles off the wire).
- **What it means for your reminders** — the backend's own `REMINDER_CONSEQUENCE` line,
  restated verbatim: *"Your reminders for this event have been cancelled."*

**The second sentence is the reason the banner exists.** A user whose event moved needs to
know whether their 1-day-before reminder still fires and at what time — "your reminders have
been rescheduled to the new time" is the sentence that answers it. The backend derives it
from `LIFECYCLE_SEND_BEHAVIOUR`, so **it cannot promise something the send machinery did not
do**, and the frontend restating it keeps that guarantee.

### The mute control's off state

FR-55 asks for "a legible off state so a user can tell they have muted it". So the control
is **not** a bare toggle whose meaning is in its position — it carries its state in its
**label**: unmuted reads "Mute updates about this event", muted reads "Updates about this
event are muted", and the muted state is **stated in words** (WCAG 1.4.1 again) and marked
with `aria-pressed`.

**The mute hides the banner.** The AC says "mute hides the banner and suppresses the strip
entry". **A mute hides the banner's *content*, not the banner's row** — no: a muted event
has nothing to correct the user about, so the banner **does not render at all** when the
event is muted. That is the whole point of the mute, and a banner that kept showing a
muted event's cancellation would make the mute a lie.

**But the mute control stays.** The user needs a way *back* — FR-55's mute is per-event and
reversible, and a control that could be set but never unset would be a trap.

### Files to Create

| File | Contents |
|---|---|
| `frontend/lib/notice-copy.ts` | The shared wording table: `NOTICE_CHANGE_LINES`, `noticeChangeLineFor`, `NOTICE_REMINDER_LINES`, `noticeReminderLineFor`. |
| `frontend/lib/notice-read.ts` | The server-side read: `readNotices()` → `NoticeRead`. |
| `frontend/components/state/notice-strip.tsx` | The dismissible strip — a client island. |
| `frontend/components/state/detail-notice-banner.tsx` | The Detail screen's persistent banner. |
| `frontend/components/state/detail-mute-control.tsx` | FR-55's per-event mute control. |
| `frontend/components/state/notice-strip.test.tsx` | The strip's rendering and dismissal. |
| `frontend/components/state/detail-notice-banner.test.tsx` | The banner, per kind, and the mute's effect on it. |
| `frontend/tests/notice-copy.test.ts` | The drift guard: the backend's `NOTICE_SUBJECTS` and `REMINDER_CONSEQUENCE`, parsed, compared. |

### Files to Modify

| File | Change |
|---|---|
| `frontend/app/page.tsx` | The strip mounted between `<DigestHeader>` and the digest's cards. |
| `frontend/app/events/[id]/page.tsx` | The banner and the mute control; `personal.muted` and `personal.notice` handed down. |
| `frontend/components/digest/digest-header.tsx` | **Unchanged** — the strip is a sibling of the header, not a child. |

### Deliberately unchanged

- **`frontend/lib/api/schema.ts` and `openapi.json`** — the API is already built and the
  contract already carries every field this item reads. **No regeneration.**
- **The backend.** `notice-and-mute-api` shipped the endpoints; this item consumes them.
- **`detail-actions.tsx`** — the sold-out CTA removal is **already implemented**
  (`page.tsx:472` drops `DetailReminderLink`, `detail-actions.tsx:407` drops the Save
  button, `page.test.tsx:695` asserts it). The work item's technical note carries
  out-of-date line numbers; **AC 4 is already done and already tested.**

### Tests

- **`components/state/notice-strip.test.tsx`** — the strip renders the notice's sentence and
  the event's link; **dismissing calls the API** and removes the entry; a **failed**
  dismissal restores the entry; the strip renders **nothing** for an empty list; the strip
  has **no count badge**, no "view all", no history.
- **`components/state/detail-notice-banner.test.tsx`** — the banner renders per kind; the
  banner says what happened to the reminders; a **dismissed** notice still renders, and says
  so; a **muted** event renders **no banner**; the mute control's two labels; the mute
  control's off state is legible in words.
- **`tests/notice-copy.test.ts`** — the backend's `NOTICE_SUBJECTS` and
  `REMINDER_CONSEQUENCE` are parsed out of `backend/domain/notices.py` and compared against
  the frontend's table; an unknown change kind has **no** line (ASSUMPTION-9); the
  consuming surfaces hold **no literal copy** of the sentences.
- **`app/page.test.tsx`** — the home renders exactly as before with no notices (no layout
  shift).
- **`app/events/[id]/page.test.tsx`** — the banner and the mute, end to end through the
  page.

### Verification

**Static checks** — `npx tsc --noEmit` clean, `npx eslint .` clean.

**The new and changed tests** — the five files above.

**The whole frontend suite** — `npx vitest run`. The baseline at `HEAD` is **99 files /
1577 tests** plus whatever the previous item added; this item must land with **zero new
failures**.

**Node 24 is required.** `package.json`'s `engines` says `>=24.15`; under Node 20 every
component test file is silently skipped and the suite reports a false pass.

### The design documents

`EXPERIENCE.md` §5 (the canonical register), §3 (the microcopy contract), §7 (the
accessibility floor — live regions, non-colour signals); `DESIGN.md`
§`component.emptystate.quiet` (the strip's weight). PRD FR-10, FR-53, FR-54, FR-55.


---

# Implementation Plan: Proof the whole path works — end-to-end and contract tests

**Work item**: `e2e-proof-and-contract-tests` · **Intent**: `event-state-sync` ·
**Mode**: confirm

## Approach

**This item writes tests, not features.** Every preceding item of the intent is
implemented and unit-tested in isolation. What none of them can prove is that the seams
compose — that a cancellation upstream actually reaches a saved user's reminders, their
conflict, their card, and their inbox, *in that order*, *exactly once*.

So the work is **one file of journeys**, plus **one file of contracts**, plus the
**mutation probes** that prove the journeys would fail if the seams broke.

### The composition, and why the seams are the point

```
ingest (catalog)          EventStateChange row, appended, version-gated
   ↓  propagation         worker.propagation.propagate(state_change_id=…, now=…)
personalization           cancel_saved_event → close_pairs_for_side   (AD-3 wall)
delivery                 apply_lifecycle_change → CANCEL / REMINT / KEEP
   ↓
notices                  raise_state_notice → one notice row, or none if muted
   ↓
sends                    state_notice send → Stream.TRANSACTIONAL, no unsubscribe URL
```

**Each arrow is a seam, and each seam is where a unit test stops.** The propagation
consumer was tested with a fake `EventStateChange`; the delivery behaviour was tested
with a fake change kind; the notice was tested with a fake user. **None of them tested
the fact that `propagation` reads the change row and hands the *same* version to all
three consumers** — and that is the failure mode a user would experience.

**The version is the spine.** `EventStateChange` carries `event_version`, and all three
consumers are version-gated against it. A journey that asserts a *version* — the send's
`send_key`, the notice's `event_version`, the saved event's `event_version` — proves the
spine holds across the wall. A journey that only asserts "a notice exists" does not.

### The journeys, and what each one proves that no unit test does

| Journey | The seam it proves | What no unit test could catch |
|---|---|---|
| **Cancellation** | catalog → propagation → personal → delivery → notice → email | That the *same* change reaches all three consumers, and that the notice and the email are about the *same* event at the *same* version |
| **Postponement** | the REMINT branch | That the new send is minted at the **new** version and the stale one is cancelled — a unit test of `apply_lifecycle_change` never sees the propagation's version hand-off |
| **Sold-out** | the KEEP branch | That the reminders **still fire** after the change — the branch where nothing is cancelled and everything is merely re-stamped, which is the branch most likely to be broken by an over-eager cancellation |
| **Reinstatement** | the REINSTATE branch, and the **spent send key** | That the old spent send key does not block the new send — a key collision that only shows up when the *same* event is cancelled and then revived |
| **Hold-and-release** | the claim-then-change race | That a send claimed by the sweep *while its event is mid-change* is **held, not sent**, and is released by propagation. **This is the race AD-17 exists for** |
| **Backlog drain** | the reconciler | That unpropagated rows **predating** this intent are propagated without manual intervention — the migration's other half |
| **Mute** | the mute in the real path | That a muted event's change produces **no notice and no email**, while its reminders **still fire** — the mute's scope, end to end |

**The hold-and-release journey is written first**, as the work item's Technical Note says.
It is the only one that can fail for a reason none of the unit tests would catch, and
staging a deterministic claim-then-change race shapes how the others are staged.

### The mute journey is the one that proves the *scope*

**FR-55's mute is narrow, and the narrowness is the whole point.** The mute silences
*the correction* — the notice and the email — and **not the reminders**. So the mute
journey must assert **two** things at once: no notice row, no email, **and** the pending
send still fires. **A test that only asserts the silence would pass against a mute that
also killed the user's reminders** — which is the failure a user would be most upset by.
And the *terminal* exception must be proved in the same journey: a **cancelled** event
raises its notice **despite** the mute, because silence about a cancelled event is the
one failure with no second channel to catch it.

### The clock is frozen, and every service takes `now`

Every service on this path takes `now` as an argument. **The proof passes its own
instant and never reads the wall clock** — a proof that sleeps is slow, flaky, and its
answer can depend on the hour it ran. `EventFactory(..., last_seen_at=NOW)` is pinned
too, or the event is stale against the frozen `NOW` and is dropped before composition.

### The database wall is respected, not worked around

`pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])` gives the test both
schemas, and **no transaction spans them** (AD-3). Each service opens its own
`transaction.atomic(using=…)`. The proof **does not use `transaction=True`** — it needs
no committed rows for another thread, and using it would let a bug hide behind a
committed intermediate state.

### The frontend half is *not* re-proved here, and that is a decision

**The rendered half was proved by the two frontend items**, and proved better than a
browser could: the digest home's own tests assert the rendered cards, the Detail
screen's assert the rendered breakdown, and *this* file asserts the **same persisted
row** that those screens read — the `DigestComposition`, the `StateChangeNotice`, the
`ScheduledSend`. The two halves meet on a row, which is the seam that matters.

**What this item adds on the frontend side is the contract**: that the endpoints this
intent added are in the committed OpenAPI document, that the generated client is in
sync, and that the frontend's notice vocabulary has not drifted from the backend's —
the last of which `frontend/tests/notice-copy.test.ts` already proves by reading the
backend's tables out of the source.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/tests/e2e/test_state_change_proof.py` | The seven journeys, each one scenario with one user, one database, and one transaction's worth of shared state |
| `backend/tests/e2e/test_state_change_contract.py` | The contracts: the OpenAPI paths this intent added, the generated client in sync, the import contracts, and the proof running offline |
| `backend/tests/e2e/mutation_probe_state_change_e2e.py` | The mutation probes — one real bug per seam, each of which must break a journey |

## Files to Modify

| File | Changes |
|------|---------|
| (none) | — |

**Nothing is modified.** This item is **tests only**, and that is deliberate: it is the
proof of the items that came before it, and a proof that changes the thing it proves is
not a proof. **If a journey fails, the fix is to the implementation** — and that fix
belongs to the item that owns the implementation, in its own commit.

## Tests

| File | What it holds |
|------|---------------|
| `backend/tests/e2e/test_state_change_proof.py` | The seven journeys |
| `backend/tests/e2e/test_state_change_contract.py` | The contracts |
| `backend/tests/e2e/mutation_probe_state_change_e2e.py` | The mutation probes (not a pytest file — a script, like the existing probes) |

### The journeys, one by one

1. **The cancellation journey** — a published event, a saved user, a pending reminder.
   The event is cancelled upstream; an `EventStateChange` is recorded; propagation runs;
   the pending send is **cancelled**; the conflict pair **closes**; the card shows
   **cancelled**; **one** notice appears in the strip; **one** email is sent, on
   `Stream.TRANSACTIONAL`, with **no unsubscribe URL**, subject
   *"EventPulse24: <name> was cancelled."*
2. **The postponement journey** — the same, but the snapshot **moves**, the reminders are
   **re-minted against the new version**, the stale send is cancelled, and a newly-created
   overlap surfaces as the **calm Detail notice** — not the FR-58 forced prompt.
3. **The sold-out journey** — the badge on the card and the Detail, the "Save Reminder"
   CTA **removed**, the reminders **kept** (`LIFECYCLE_SEND_BEHAVIOUR` maps
   `sold_out → KEEP`), and **one** notice.
4. **The reinstatement journey** — a cancelled event comes back; the reminders are
   re-minted **from the surviving plan**; the save returns to live; the **old spent send
   key does not block the new send**.
5. **The hold-and-release journey** — a send claimed by the sweep while its event is
   mid-change is **held, not sent**, and is **released by propagation**.
6. **The backlog drain** — unpropagated `EventStateChange` rows that predate this intent
   are propagated by the reconciler **without manual intervention**.
7. **The mute journey** — a muted event's change produces **no notice and no email**,
   while its reminders **still fire**; and a **cancelled** event raises its notice
   **despite** the mute.

### The mutation probes — one real bug per seam

Each probe applies **one real bug** to the implementation, runs the journey suite, and
checks that **at least one test fails**. A probe that passes means the journeys do not
prove that rule, and either the implementation or the journey has to change.

| # | The bug | The seam it breaks |
|---|---|---|
| 1 | propagation does not mark the change propagated | The backlog drain |
| 2 | the CANCEL branch cancels nothing | The cancellation journey |
| 3 | the KEEP branch cancels the sends anyway | The sold-out journey |
| 4 | the mute is not consulted | The mute journey |
| 5 | the hold does not exclude the send from the claim | The hold-and-release journey |
| 6 | the notice is raised for every kind, terminal or not | The mute journey's terminal half |

### Verification

**Static checks**

```
cd backend
uv run ruff check .
uv run ruff format --check .
uv run lint-imports            # 19 contracts kept, 0 broken
```

**The new tests**

```
uv run pytest tests/e2e/test_state_change_proof.py tests/e2e/test_state_change_contract.py -q
```

**The mutation probes** — each one must break the suite, and each must leave the tree
unchanged afterwards:

```
uv run python tests/e2e/mutation_probe_state_change_e2e.py
```

**The whole backend suite** — `make test-backend`. The **16 pre-existing failures** from
the `timeline-and-conflicts` item (date-expired fixtures) are expected and unrelated;
the baseline is **{0} new failures**.

**The frontend suite** — unchanged by this item, but it must still pass, because the
contract file asserts the generated client is in sync with the committed OpenAPI
document. `npx vitest run` (Node 24), `npx tsc --noEmit`, `npx eslint .`.

**The end-to-end path** (manual, against a running server): cancel an event upstream →
re-ingest → the digest card shows cancelled → the reminders stop → the conflict closes →
the strip carries one notice → one email arrives.
