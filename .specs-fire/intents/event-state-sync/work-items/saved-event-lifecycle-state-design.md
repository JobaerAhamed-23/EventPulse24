---
work_item: saved-event-lifecycle-state
intent: event-state-sync
created: 2026-11-05
mode: validate
checkpoint_1: pending
---

# Design: Who saved this, and what a cancellation does to their save

## Summary

**The work item's central premise is wrong, and this design drops it.**

The item asks for a lifecycle column on `SavedEvent`, on the grounds that *"the personal side cannot ask `catalog` whether it is dead: AD-3 forbids the join."* Reading the three surfaces that consume a save shows they already ask, on every read, through the published interface — and that this is allowed, because AD-21 forbids a **SQL join**, not a published read.

What is genuinely missing is smaller and more specific: **a reverse lookup** (who saved this event?) and **a cancellation path** that closes conflict pairs under AD-17's version gate. Both of the hard parts they depend on already exist.

## Scope

**In Scope:**
- `list_savers_for_event` — the published reverse read AD-17's consumer needs
- A version-gated cancellation service closing the save's conflict pairs
- Making the three reading surfaces honour the catalog's `status` they already hold
- `reinstated` reversing a cancellation

**Out of Scope:**
- **A lifecycle column on `SavedEvent`** — see D1
- Any migration (nothing new is stored)
- The propagation consumer that calls these services (item 4)
- The FR-54 notice (item 3)

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| D1 — Lifecycle state on `SavedEvent` | **No column** | The catalog already tells every reader, on every read. A column would be a second source of truth that can drift |
| D2 — How a reader knows an event is dead | `PublicEvent.status`, already in hand | All three readers already call `get_public_events` and already receive `status`; none currently looks at it |
| D3 — Reverse lookup shape | `list_savers_for_event(event_id, after=None, limit=N)` | Paged, because a popular event's savers must not become one unbounded transaction |
| D4 — Closing conflicts on cancellation | Reuse `close_pairs_for_side` | It already closes as `CLEARED_BY_STATE_CHANGE` — AD-21's name for exactly this |
| D5 — FR-54's two populations | **One set: savers.** `unsave_event` now removes the plan too, so a plan cannot outlive its save | Probed: today a plan does outlive its save, and the orphan both muddies the population and permanently holds item 1's sends |

### D1 — there is no lifecycle column, and that is the whole design

The work item's reasoning was that AD-21's *"the Timeline and conflict detection read the snapshot; they never join `catalog`"* leaves the personal side unable to learn an event was cancelled. That reads "join" too broadly. The rule exists so that **conflict arithmetic** does not depend on catalog availability — the snapshot owns the *times*. It was never a rule that the personal side may not read the catalog at all.

And in fact every surface already does:

| Surface | Call | Already handles absence |
|---|---|---|
| Timeline | `timeline.py:376` `get_public_events` | `:112` — *"`name` is None when the catalog no longer holds a saved event"* |
| `/conflicts` | `conflict_list.py:241` `get_public_events` | `available=False`, title `None` |
| Digest candidates | `digest_candidates.py:315` `get_public_events` | `public` is `None`; the candidate is **kept** on purpose |

Each already receives a `PublicEvent`, and `PublicEvent` already carries **`status`** — `scheduled`, `postponed`, `cancelled`. `_public_events()` filters to `PUBLISHED` and excludes `SUPERSEDED`, so a **cancelled event is still in the map, with `status='cancelled'`**; a superseded or unpublished one is absent.

So the two facts a reader needs are already distinguishable today:

- **absent from the map** → superseded, unpublished, or in review
- **present with `status='cancelled'`** → cancelled

A grep for `.status` across those three modules returns exactly one hit, and it is `pair.status`. **Nobody looks.** The gap is not storage; it is that three readers ignore a field they are already holding.

Adding a column would denormalize a fact the catalog owns into a table that only AD-17 propagation updates — so between a cancellation and its propagation, the column and the catalog would disagree, and a reader consulting the column would be *more* stale than one consulting the catalog it already read. It would also need a migration, a backfill, a second vocabulary, and a new way to be wrong.

**The cheapest correct change is to read the field we already fetch.**

### D3 — the reverse lookup, which is the real gap

Every function in `saved_events.py` takes `user_id` **and** `event_id`. A state change names only an event, so nothing can answer *who saved this?*

The index for it already exists — `saved_event_event_idx`, whose comment reads *"AD-17 propagation finds every save of one event, across all users."* Built in anticipation, never used.

```python
def list_savers_for_event(*, event_id, after=None, limit=SAVERS_PAGE) -> list[SaverRef]
```

Keyset-paged on `(id,)`, not offset: propagation runs while users save and unsave, and an offset page would skip or repeat rows under that churn. The consumer pages until exhausted, applying each user in their own transaction — which is what AD-17's per-user keying already requires.

### D5 — savers and plan-holders are not the same set

FR-54: *"an event the user has **saved or set a Reminder Plan for**."*

**Settled by probe, 2026-11-06.** A throwaway test saved an event, PUT a two-slot plan, then unsaved:

```
plans_before=1 plans_after=1 sends_before=['pending','pending'] sends_after=['pending','pending']
```

So today a plan **does** outlive its save, with its pending sends intact.

Three facts bound what that means:

1. **A plan cannot be born without a live save.** Both the read (`reminder_plan_read.py:177`) and the write (`api.py:119`) resolve the target through the one `resolve_target`, which raises `ReminderTargetNotFoundError` when `get_saved_event` 404s. So plan-holders ⊆ savers *at creation*.
2. **An orphan plan is already declared dead by the tree's own test.** `test_a_saved_event_the_user_has_unsaved_is_a_404` — *"Un-saved and never-saved are the same fact: the save is the target."* The row reads as 404 while still holding live `ScheduledSend` rows that nothing re-resolves before sending.
3. **The owner's own cleanup already exists.** `remove_plans_for_targets` deletes the plans *and* cancels their pending sends in one transaction, and `personalization` already calls it from `calendar_connections.py:759` — exactly this shape, for exactly this reason (*"the target itself is gone, so a row holding no slots would be a plan for an event that no longer exists"*).

**D5 decision: `unsave_event` calls `remove_plans_for_targets`, and the notice population is savers — one set, one read.**

This is not scope creep into item 2; without it item 2's own output is wrong in two ways:

- **FR-54's population becomes undecidable.** A union read would notify people who unsaved — strictly worse than the status quo, since unsaving *is* the request to stop hearing about it. A savers-only read over today's data silently drops nothing, but only by accident.
- **It turns item 1's hold into a permanent alarm.** An orphan's pending send carries the old `event_version`. The sweep's `hold_stale_sends` holds it when the catalog moves ahead. The only release is `apply_lifecycle_change`'s `KEEP` branch, reached from propagation, which item 2's reverse lookup drives **off savers** — and the orphan's owner is not a saver. `held_at` is never cleared, and `count_stuck_holds` trips `report_held_sends` forever.

The import is **function-local**. `delivery` imports `personalization` inside functions throughout (`reminder_plan_read.py:107,129,146`; `scheduled_sends.py:143`) precisely to break this cycle; a module-level import in `saved_events.py` would close it from the other side.

## Data Models Affected

**None.** No model changes, no migration. This is the design's main claim.

## Technical Approach

### Architecture

```
AD-17 consumer (item 4)
  │
  ├─ personalization.list_savers_for_event(event_id, after=…)   ← NEW, paged
  │
  └─ per user, in one `personal` transaction:
        ├─ time moved  → update_saved_event_snapshot(...)        ← EXISTS, version-gated
        └─ cancelled   → cancel_saved_event(...)                 ← NEW, version-gated
        │                  └─ close_pairs_for_side(...)          ← EXISTS
        └─ reinstated  → reinstate_saved_event(...)              ← NEW
                           └─ detect_conflicts + record_detected ← EXISTS

Readers (no propagation involved — they just stop ignoring a field):
  timeline / conflict_list / digest_candidates
    └─ public.status == "cancelled"  → surface it; FR-55: drop from the digest
       public is None                → already handled today (available=False)
```

### What `cancel_saved_event` does

Mirrors `update_saved_event_snapshot` closely enough that a reader sees them as a pair: the same version gate, the same audit shape, the same single `personal` transaction.

1. Version gate — apply only if the change's `event_version` exceeds the stored one. Returns `False` otherwise, exactly as the snapshot updater does.
2. Bump `event_version` to the change's version, so a later out-of-order change is still correctly gated.
3. `close_pairs_for_side(...)` → the pairs close as `CLEARED_BY_STATE_CHANGE`, AD-21's own name for "a side went away, and the user did not choose this".
4. Audit row.

**The save row itself is not deleted and not flagged.** The user made that save; it stays. The catalog is what says the event is not happening, and every reader already asks.

**A cancelled public event never touches a personal event** (FR-55). Only the save's own pairs close.

### What the readers change

| Reader | Change |
|---|---|
| `digest_candidates` | A candidate whose `public.status == "cancelled"` is **dropped** — FR-55: *"event is removed from the digest"*. An absent `public` is still kept, as today: the save is real and vanishing silently is worse |
| `timeline` | A cancelled block is **shown, marked**, not hidden — it is on the user's calendar and silently removing it from a calendar they curated is its own failure |
| `conflict_list` | A pair whose saved side is cancelled is already closed by propagation, so it simply stops being listed |

The digest/timeline asymmetry is deliberate and worth stating: the digest is *"what is worth your attention today"*, and a cancelled event is not; the Timeline is *"what is on your calendar"*, and a cancelled event still is, until the user removes it.

## Affected Files

| File | Action | Purpose |
|---|---|---|
| `backend/apps/personalization/services/saved_events.py` | Modify | `list_savers_for_event`, `cancel_saved_event`, `reinstate_saved_event` |
| `backend/apps/personalization/services/digest_candidates.py` | Modify | Drop cancelled candidates (FR-55) |
| `backend/apps/personalization/services/timeline.py` | Modify | Surface cancelled state on the block |
| `backend/shared/constants.py` | Modify | `SAVERS_PAGE` |
| `backend/tests/personalization/test_saved_events.py` | Modify | Version gate, paging, cancel/reinstate |
| `backend/tests/personalization/test_digest_candidates.py` | Modify | Cancelled dropped, absent kept |
| `backend/tests/personalization/test_timeline.py` | Modify | Cancelled block shown and marked |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Reading `status` at read time is "less stable" than a snapshot | A digest could change between composes | Correct and intended: AD-10 stores the composition, and FR-53's whole promise is that a cancellation reaches the user within 4h. The *times* stay snapshotted, which is what AD-21 protects |
| Keyset paging skips a saver who saves mid-propagation | They miss that change's effects | A save re-reads the event's version after commit and requests re-propagation if it moved (AD-21's own rule) — the existing mechanism already covers this |
| Plan-holders without saves are missed | A user with reminders but no save gets no notice | D5: probed in code before the read is written, not assumed |
| Dropping cancelled from the digest hides it entirely | A user never learns their saved event died | The FR-54 notice (item 3) is what tells them; the Timeline still shows it. Recorded as a dependency, not a gap |

## Implementation Checklist

- [x] Probe whether `unsave_event` cancels the `ReminderPlan`; record the finding and let it decide D5 — **it does not**; `unsave_event` now calls `remove_plans_for_targets`
- [x] `list_savers_for_event` — keyset-paged, bounded by `SAVERS_PAGE`
- [x] `cancel_saved_event` — version-gated, closes pairs via `close_pairs_for_side`, audits
- [x] `reinstate_saved_event` — version-gated, re-runs `detect_conflicts` / `record_detected_conflicts`
- [x] `digest_candidates` drops a cancelled candidate; still keeps an absent one
- [x] `timeline` surfaces the catalog's lifecycle word on the block, and `TimelineBlockOut` carries it to the wire
- [x] Tests: version gate at the exact boundary; out-of-order cancel after a newer change is a no-op; cancel → reinstate → cancel idempotent at each step; a personal event conflicting with a cancelled save is untouched; paging across a page boundary with a row deleted mid-page; cancelled dropped from digest but kept on timeline
- [x] Full suite, `import-linter`, `ruff`, OpenAPI + client regenerated

## Amendment Raised During Implementation

**A reinstated event's conflict can never come back, and no code change can fix it.**

AD-17 requires a cancellation to *close conflicts*. AD-21's D24 makes a closed pair immutable — enforced by the `guard_conflict_pair` trigger, probed directly: `IntegrityError: a closed ConflictPair ... is immutable` — and `conflict_pair_pair_uq` refuses a replacement row for the same two sides.

So the work item's AC — *"its conflict pairs are re-evaluated rather than left closed"* — is **unachievable without a spine edit**. A saved event that clashed, was cancelled, and is then reinstated clashes again, and `/conflicts` will not say so.

What `reinstate_saved_event` *does* restore is every overlap not already recorded — the events the user added while the save was dead. That is the maximum the invariants permit, and `test_reinstating_cannot_reopen_a_pair_cancellation_closed` pins the limit.

Two ways out, both spine edits, recorded on the intent brief:

1. **AD-17 stops closing conflicts on a cancellation**, and the readers filter on the catalog's `status` — consistent with D1, where liveness is read rather than mirrored.
2. **AD-21's D24 gains a narrow exception** for a pair cleared by a state change that later reverses.

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-11-06*
