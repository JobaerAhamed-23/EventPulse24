---
work_item: propagation-consumer
run: run-eventpulse24-025
intent: event-state-sync
checkpoint: 1 (design)
created: 2026-11-10
---

# Design: AD-17's propagation consumer

## Summary

The caller between two finished halves. Three decisions carry it, and one hard constraint rules out the obvious answer to the work item's "central design question".

**The constraint:** `EventStateChange` is append-only with exactly one mutable column.

```python
append_only_mutable = frozenset({"propagated_at"})
```

Python-guarded in `AppendOnlyQuerySet` and trigger-enforced for every role. So there can be **no claim column, no attempts counter, no per-user cursor on that row** — which removes the mechanism three of the work item's four open questions would naturally reach for.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | **No per-user marker, anywhere.** The version gate already is one | Every published service is version-gated *and* stores the version it applied, on the row it applied it to |
| D2 | `personalization` first, `delivery` second, the notice last | Only one of the two orderings leaves a survivable inconsistency, and item 1's hold is what makes it safe |
| D3 | Per-kind dispatch; `personalization` is **not** called for `sold_out` / `detail_changed` | Those kinds change nothing the snapshot stores, and calling it would re-run conflict detection for a time that did not move |
| D4 | One task per state change, paging savers internally | A task per user multiplies the broker traffic by the saver count for no idempotency gain |
| D5 | A poisoned user leaves `propagated_at` NULL and raises an **alarm**, not a timeout | The alternative is marking a change propagated while a user genuinely is not |
| D6 | The orchestrator lives in `worker/`, not in an app | AD-17 exists partly to stop `ingestion` reaching across the wall; putting the reach inside `ingestion` would read as exactly that |

---

### D1 — the version gate is the marker, and it is already durable

The work item calls this "the central design question of this item": `(state_change_id, user_id)` needs a durable marker for *this user is done*, or a partial run cannot resume without re-applying.

It does not need one, because **every service the consumer calls is both version-gated and version-storing**:

| Service | Gate | Where the version lands |
|---|---|---|
| `update_saved_event_snapshot` | `new_version <= saved.event_version → False` | `SavedEvent.event_version` |
| `cancel_saved_event` / `reinstate_saved_event` | same | `SavedEvent.event_version` |
| `apply_lifecycle_change` | `event_version__gte=target.version → no-op` | `ScheduledSend.event_version` |
| `raise_state_notice` | `event_version__gte → False` | `StateChangeNotice.event_version` |

A marker table would record "user 7 is done with change X". The `SavedEvent` row *already* records it, as the version it holds — and it is the same fact, written in the same transaction as the work it describes. A separate marker could disagree with the work; this cannot.

So a partial run retried re-walks every saver, and the ones already applied cost one indexed read each and change nothing. That is the whole resumption story.

**Re-applying is not merely harmless, it is the mechanism.** This is also why the consumer must not add a gate of its own: a second gate in the caller could refuse work the service would have accepted, and then nothing would ever repair it.

**The one case worth naming:** a user who saves the event *during* propagation stamps their snapshot with the catalog's current version, which is at or above the change's — so the gate refuses, correctly, since they never had the old state. AD-21's save-race protocol already re-requests propagation for them if the version moved mid-save.

### D2 — personalization first, and the hold is what makes the window safe

A crash between the two halves is not hypothetical; AD-3 forbids a transaction spanning them, so the gap is permanent and the only question is which inconsistency survives it.

**Sends first, snapshot second** leaves a user whose reminders are re-minted for the new time while their Timeline still shows the old one — a reminder that contradicts the calendar it came from, with nothing on screen to explain it.

**Snapshot first, sends second** leaves a user whose Timeline is correct and whose sends still carry the old version. And that state is already defended: item 1's sweep guard holds any send whose `event_version` is below the catalog's, so **nothing wrong goes out during the window**. The next tick re-runs, the snapshot no-ops, and the sends are rewritten or cancelled.

So the order is forced, and it is the one that item 1 already built the safety net for. The notice goes **last**, because it describes a state that both halves have made true; a notice sent before the sends were fixed would tell the user about a correction that had not happened yet.

### D3 — per-kind dispatch, and two kinds skip `personalization` entirely

`LIFECYCLE_SEND_BEHAVIOUR` maps all seven kinds for `delivery`. The personal side needs its own mapping, and it is **not** the same shape:

| Kind | `delivery` | `personalization` |
|---|---|---|
| `time_moved`, `postponed` | REMINT | `update_saved_event_snapshot` |
| `reinstated` | REMINT | `reinstate_saved_event` |
| `cancelled`, `superseded` | CANCEL | `cancel_saved_event` |
| `sold_out`, `detail_changed` | KEEP | **nothing** |

`SavedEvent` stores a time and a version. A sold-out or venue-detail change moves neither — `event_writes._kind_facts` does not even record a time for those kinds. Calling `update_saved_event_snapshot` with the unchanged times would bump the version and then re-run `reconcile_pairs_for_side` and `detect_conflicts` for an overlap that cannot have changed.

**Letting the snapshot's version lag is safe**, because every gate is `>` and not `==`: a snapshot at v1 that skips a `sold_out` at v2 still accepts a `time_moved` at v3. And `delivery`'s own version is re-stamped by `apply_lifecycle_change`'s KEEP branch, which is what releases item 1's hold — so the hold's exit does not depend on the personal side at all.

**The times come from the change, not from the current event.** `after` carries `start_utc` / `end_utc` for the kinds that moved them. Reading the live `Event` instead would pair *this* change's version with *the latest* times, which is wrong whenever several changes are in flight — the exact case `event_writes` creates by appending k changes per poll.

### D4 — one task per state change

A task per user turns one popular event into thousands of broker messages, and buys nothing: the idempotency is in the services (D1), not in the task boundary.

So one task pages `list_savers_for_event` (item 2's keyset read, `SAVERS_PAGE` at a time) and applies each user in their own `personal` transaction. The per-user transaction is what AD-17 asks for; the task is just the loop around it.

**The reconciler can overlap a long run, and that is tolerable rather than prevented.** `OUTBOX_RECONCILE_AFTER` re-offers a change still unpropagated after five minutes, so a very popular event can have two workers walking the same saver list. Without a claim column — which append-only forbids — this cannot be excluded, and it does not need to be: both workers call the same idempotent services, and the loser's writes no-op. The cost is duplicated reads, bounded by `OUTBOX_RECONCILE_BATCH`.

Recorded rather than hidden: if that duplication ever matters, the fix is a claim table in `catalog`, not a column on an append-only row.

### D5 — a poisoned user is surfaced, not timed out

The work item asks for a bound: `propagated_at` must not be held NULL forever by one bad user, and must not be set while a user is genuinely unpropagated.

Those two cannot both be satisfied by a counter, and the append-only row has nowhere to keep one anyway. So the bound is on **silence**, not on retries — the same answer item 1 reached for its held sends:

> The hold itself is correct and has no timeout … what needs a bound is nobody *releasing* it … That failure is quieter than the one being fixed, so it gets an alarm rather than a timeout.

A user whose apply raises is logged with the state change and the user id (AD-13: ids, never PII), the loop **continues to the next user**, and `mark_propagated` is not called. The reconciler re-offers the change; the healthy users no-op; the broken one is retried. A change still unpropagated beyond `PROPAGATION_ALARM_AFTER` is reported by a worker task, exactly as `report_held_sends` reports a stuck hold.

`propagated_at` stays NULL because setting it would be a lie, and the lie is worse: the reconciler would stop offering, and the user would be silently left on the old state forever.

### D6 — the orchestrator lives in `worker/`

AD-17's "Prevents" clause names it: *"Also prevents `ingestion` reaching across the wall to fix it directly."* Putting the loop inside `apps/ingestion` would satisfy the import contracts — `apps` is one layer — and read as precisely the thing the decision exists to stop.

It is also nobody's flow. `personalization` owns saves, `delivery` owns sends, `ingestion` owns the catalog; the propagation is the *job* that joins them, and the job is `worker`.

So: `worker/propagation.py` holds the logic as plain functions, and `tasks.py` keeps a thin `@shared_task` — the shape `revalidate_public_pages` already uses, and testable without Celery. `ingestion` gains one published read, `outbox.get_state_change`, returning a frozen dataclass rather than the model, so the AD-2 contract holds.

## Data Models Affected

**None.** No new table, no migration — D1 is the reason, and it is the design's main claim.

## Affected Files

| File | Action | Purpose |
|---|---|---|
| `backend/apps/ingestion/services/outbox.py` | Modify | `StateChangeFacts` + `get_state_change`, published as plain data |
| `backend/worker/propagation.py` | Create | The per-user loop, the per-kind dispatch |
| `backend/worker/tasks.py` | Modify | Replace the stub; add `report_stuck_propagation` to the tick |
| `backend/shared/constants.py` | Modify | `PROPAGATION_ALARM_AFTER`, `LIFECYCLE_PERSONAL_BEHAVIOUR` |
| `backend/tests/worker/test_propagation.py` | Create | |
| `backend/tests/worker/test_propagation_tasks.py` | Create | |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| A change with many savers outruns the reconciler window | Two workers walk one list | D4: safe by idempotency, bounded by the reconcile batch, recorded as a known cost |
| The personal and delivery halves disagree between steps | A user sees a new time with old reminders | D2: the only survivable order, and item 1's hold means nothing wrong *sends* during the gap |
| A permanently failing user blocks the whole change | `propagated_at` NULL forever | D5: the loop continues past it, and an alarm surfaces it within minutes |
| A new `ChangeKind` ships unmapped on the personal side | A change silently does nothing to saves | `LIFECYCLE_PERSONAL_BEHAVIOUR` is total and tested, mirroring `test_every_lifecycle_kind_is_mapped` |

## Implementation Checklist

- [ ] `outbox.get_state_change` — published, plain data
- [ ] `LIFECYCLE_PERSONAL_BEHAVIOUR` — total over all seven kinds, with a test that it stays total
- [ ] `worker/propagation.py` — page savers, apply per user in one `personal` transaction, dispatch per kind, continue past a failure
- [ ] `mark_propagated` only when every user applied without raising
- [ ] The stub replaced; `report_stuck_propagation` on the tick
- [ ] AD-17's accepted residual window test, **deferred here from `held-for-propagation-status`** and not deferred again
- [ ] Tests: full re-run is a no-op; partial run completes; older change after newer is a no-op; two changes racing leave the newer; no savers marks propagated; the backlog drains through the reconciler; a held send is released by each of the three behaviours
- [ ] Full suite, `import-linter`, `ruff`, `makemigrations --check`

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: pending*
