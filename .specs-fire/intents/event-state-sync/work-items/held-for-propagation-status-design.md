---
work_item: held-for-propagation-status
intent: event-state-sync
created: 2026-11-04
mode: validate
checkpoint_1: approved
---

# Design: The sweep will send a reminder for an event that already moved — the propagation hold

## Summary

AD-17 specifies a guard the codebase never built: after claiming a send, the sweep must compare the row's `event_version` against the catalog's current one and **hold** the row instead of sending if the catalog has moved ahead. `apps/delivery/services/delivery_sweep.py` has no version check — the only match for "propagat" in all 493 lines is a comment quoting a different AD-17 rule.

The bug is live now and does not depend on propagation existing: an event cancelled at noon still has its 1-hour reminder delivered at 18:00.

This design covers the hold, its release, and one decision the work item left open — **whether the hold is a new status or a nullable timestamp**. The investigation changed the answer, and the recommendation below is not the one the work item's acceptance criteria assume.

## Scope

**In Scope:**
- A representation for "claimed, not sent, waiting for propagation"
- A batched catalog version read after the claim, before the send
- Holding stale event-bound rows; sending the rest
- Keeping every existing `delivery` writer able to see and act on a held row
- An alarm for held rows nothing releases
- Tests, including the accepted residual race AD-17 concedes

**Out of Scope:**
- The propagation consumer that releases held rows (`propagation-consumer`, item 4)
- Any change to how sends are minted or keyed (AD-7 is untouched)
- The FR-54 notice (`state-change-notice-model`, item 3)
- Personal-event reminders and the digest, which have no catalog version

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| D1 — How a hold is represented | **Nullable `held_at` column; status stays `pending`** | A new status blinds 8 existing `status=PENDING` filters. See below. |
| D2 — Where the version check runs | After the claim commits, in `sweep_due_sends` | AD-17: *"After claiming a row… a separate, non-transactional read."* Keeps the cross-schema read out of the claim's row lock. |
| D3 — Which rows are guarded | Any row with `event_version IS NOT NULL` | Catches event reminders now and state notices later without revisiting, since only event-bound rows carry the column. |
| D4 — Batched or per-row read | Batched, via `catalog_read.get_public_events` | One `IN` query per sweep batch. A per-row read would put a cross-module call on the hottest path in the system. |
| D5 — An event absent from the catalog read | **Hold, do not cancel** | Cancelling is propagation's decision (AD-17 owns "what each change does"). The sweep's job is to not send. |
| D6 — Attempts on a hold | Not incremented; `claimed_at` cleared | A hold is not a delivery attempt. Counting it would exhaust the attempt bound and mark a live reminder `failed`. |
| D7 — Alarm for unreleased holds | Age bound surfaced on the tick | A hold that nobody releases stops mail silently — a quieter, worse failure than the one being fixed. |

### D1 — the hold is a column, not a status, and this reverses the work item

The work item's first acceptance criterion asks for *"a new non-terminal `held_for_propagation` status"*, and AD-17's own wording is *"the row goes to `held_for_propagation`"*. Reading the code changed my mind, and the reason is concrete.

`apps/delivery/services/scheduled_sends.py` filters on `status=ScheduledSend.Status.PENDING` in **eight** places (lines 303, 395, 461, 562, 612, 676, 691, 771). These are the module AD-17 calls *"the sole rewriter of `SCHEDULED_SEND`"* — minting, cancelling, re-timing, and `apply_lifecycle_change` itself.

If a held row's status is no longer `pending`, **every one of those eight goes blind to it**, including:

- `apply_lifecycle_change` — the function whose entire job is to cancel or re-mint the row. The release path would skip exactly the rows it exists to release.
- `reschedule_pending_for_user` — a quiet-hours or timezone change would silently not re-time a held row.
- The staleness gate at `scheduled_sends.py:676`, which asks whether a newer version is already pending. A held row would be invisible to it, and propagation would mint a **duplicate**.

Fixing that means auditing and widening all eight to `status__in=[PENDING, HELD]`, in the most correctness-critical module in the project, where the module's own docstring warns that collapsing behaviours into one flag is how *"the caller who gets it wrong gets duplicate sends with no error."* Missing one is a stranded row or a double send, and neither raises.

A nullable `held_at` instead keeps the row `pending`. Every existing writer continues to see it and behave correctly **with no change at all**. The blast radius drops from eight call sites to one: the claim query gains `held_at IS NULL`.

It is also the idiom this codebase already uses twice for exactly this shape — `claimed_at` on this same model, and `sync_claimed_at` on `CalendarConnection` — with `release_claim` setting it back to `NULL`.

**On the Spine.** The constitution says AD deviation requires amending the spine first. I read this as representation, not deviation: AD-17 mandates that the row *is not sent* and that *propagation releases, rewrites or cancels it*, and both hold exactly. `held_for_propagation` names a state, and `held_at IS NOT NULL` **is** that state. If you read it as a deviation, the honest path is to amend AD-17's sentence to describe the state rather than the column — and that is a one-line amendment I would rather make than widen eight filters.

**Cost, stated plainly.** The sweep's partial index is `WHERE status = 'pending'`, so a held row stays in it. The index stays slightly larger than a status would make it, and the claim query carries one more predicate. Against a permanently small pending set, that is cheap; against eight silent correctness hazards, it is not close.

### D5 — an absent event is a hold, not a cancel

`get_public_events` returns a map that **omits** any event that is unpublished, `in_review`, or `superseded`. For a pending reminder that means "the catalog no longer publishes this", which is exactly the condition under which a reminder must not go out.

The tempting move is to cancel. The design does not, for two reasons. AD-17 owns the table of what each change does to a send, and "cancelled" is its answer for a cancellation — reached through `apply_lifecycle_change`, with an audit row and a version gate. A sweep that cancels on its own authority is a second, unversioned writer of that decision, and an event briefly absent for an unrelated reason (an editorial hold, a mid-publish window) would have its reminders destroyed rather than delayed.

Holding is recoverable; cancelling is not.

## Data Models Affected

### Modifies

- **`ScheduledSend`** — adds `held_at = DateTimeField(null=True, blank=True)`. Null means not held. Set when the sweep declines to send a stale row; cleared by propagation on release. No change to `Status`, `TERMINAL_STATUSES`, or the `sent_at` CHECK constraint.

The `models.py:287` docstring — *"`pending` is a promise; the other three are terminal and never reopened"* — **stays true** under this design and needs no rewrite. That the work item expected to rewrite it is itself evidence for the column.

## Technical Approach

### Architecture

```
sweep_due_sends(now)
  │
  ├─ claim_due_sends()                  [personal tx; commits]
  │     status='pending' AND due_at<=now
  │     AND (claimed_at IS NULL OR expired)
  │     AND held_at IS NULL              ← new predicate
  │
  ├─ _hold_stale(claimed_ids, now)      ← NEW, after the claim, no tx held
  │     1. load claimed rows; partition on event_version IS NOT NULL
  │     2. catalog_read.get_public_events({event ids})   [one query, catalog]
  │     3. for each event-bound row:
  │          absent from map            → hold   (D5)
  │          catalog.event_version > row.event_version → hold
  │          otherwise                  → send
  │     4. held rows: held_at=now, claimed_at=NULL, attempts untouched
  │     returns the ids still safe to send
  │
  └─ for send_id in safe_ids: send_one(...)      [unchanged]
```

The guard sits between the claim and the send, which is precisely where AD-17 puts it, and it holds no transaction across the catalog read.

### The release path

Propagation (item 4) releases by calling `delivery`'s published service. Because the row never left `pending`, `apply_lifecycle_change` already finds it and already does the right thing per `LIFECYCLE_SEND_BEHAVIOUR`:

- `REMINT` → cancels the stale row, mints a new one at the new version
- `CANCEL` → cancels it
- `KEEP` → re-stamps `event_version`

This design adds one requirement to item 4: **clear `held_at` wherever it re-stamps or re-times a row it leaves pending** (the `KEEP` path). Cancel and re-mint need nothing, because the held row becomes terminal and the new row is born unheld. That is one line in item 4, recorded here so it is not discovered late.

**A held row also needs its `due_at` recomputed on release**, not merely unheld: the row was due in the past, so clearing `held_at` alone would send it immediately at the old time. `REMINT` and `CANCEL` handle this naturally. The `KEEP` path must re-time. This is the subtlest consequence of the design and gets its own test.

### Database Changes

```sql
ALTER TABLE personal.delivery_scheduledsend
  ADD COLUMN held_at timestamptz NULL;
```

Additive, nullable, no default, no backfill, no rewrite — safe against a table the sweep is actively claiming from. Forward-only, one migration, per the constitution.

## Affected Files

| File | Action | Purpose |
|---|---|---|
| `backend/apps/delivery/models.py` | Modify | Add `held_at`; document the hold beside `claimed_at` |
| `backend/apps/delivery/migrations/00NN_scheduledsend_held_at.py` | Create | Additive nullable column |
| `backend/apps/delivery/services/delivery_sweep.py` | Modify | `held_at IS NULL` in the claim; new `_hold_stale`; wire into `sweep_due_sends` |
| `backend/apps/delivery/services/scheduled_sends.py` | Modify | Clear `held_at` on the `KEEP` re-stamp path; re-time on release |
| `backend/shared/constants.py` | Modify | `HELD_SEND_ALARM_AFTER` |
| `backend/worker/tasks.py` | Modify | Surface the held-row alarm on the tick |
| `backend/tests/delivery/test_delivery_sweep.py` | Modify | The guard's tests |
| `backend/tests/delivery/test_scheduled_sends.py` | Modify | Release-path tests |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Held rows accumulate because item 4 does not exist yet | Reminders for changed events stop going out silently | Expected and correct — not sending beats sending wrong. `HELD_SEND_ALARM_AFTER` surfaces the count on the tick; item 4 drains it |
| The `KEEP` path leaves `held_at` set | Row never sends again | Explicit AC and test in this item; one-line requirement recorded for item 4 |
| Release without re-timing | Reminder fires immediately at its old `due_at` | Dedicated test on the `KEEP` path |
| Catalog read fails mid-sweep | Whole batch stalls | Treat a failed read as "hold nothing, send nothing this tick" — release the claims and retry next tick. Never send unverified |
| Cross-schema read inside the claim lock | Lock held across a network call | Guard runs after the claim transaction commits (D2), asserted by a test |
| One more predicate on the sweep's hot query | Throughput | `held_at IS NULL` is a null check on a column that is null for nearly every row; the partial index still serves it |

## Implementation Checklist

- [ ] Add `held_at` to `ScheduledSend` with the docstring explaining the hold and why it is not a status
- [ ] Forward-only migration, additive and nullable
- [ ] Add `held_at IS NULL` to `claim_due_sends`
- [ ] Implement `_hold_stale`: partition, batched `get_public_events`, hold on absent-or-newer
- [ ] Hold sets `held_at`, clears `claimed_at`, leaves `attempts` and `last_attempt_at` untouched
- [ ] Wire `_hold_stale` into `sweep_due_sends` between claim and send
- [ ] Audit row for each hold, following the `claim_scheduled_send` pattern
- [ ] Clear `held_at` and re-time on the `KEEP` path in `apply_lifecycle_change`
- [ ] `HELD_SEND_ALARM_AFTER` constant and tick surfacing
- [ ] Tests: a moved event is held not sent; an absent event is held not cancelled; a current event sends; a personal reminder and a digest are never held; attempts unchanged by a hold; the claim query skips held rows; the catalog read happens after the claim commits; a failed catalog read sends nothing; `KEEP` release clears `held_at` and re-times; no held row is stranded
- [ ] Test documenting AD-17's accepted residual window (a change committing between the version read and the provider call) and asserting the FR-54 notice is what corrects it
- [ ] Full `delivery` suite green; `import-linter` contracts green; `manage.py check` clean

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-11-04*
