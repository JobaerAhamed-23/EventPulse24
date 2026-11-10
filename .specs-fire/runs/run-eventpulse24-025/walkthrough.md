---
run: run-eventpulse24-025
work_item: propagation-consumer
intent: event-state-sync
generated: 2026-11-10
mode: validate
---

# Implementation Walkthrough: The job that was always a stub

## Summary

AD-17's propagation consumer now exists. `ingestion` appends a versioned `EventStateChange`
when a source moves an event; this job applies that change to every user who saved the
event — rewriting their snapshot, their reminders, and raising one calm correction notice.

The design's central claim is what it does **not** add: no table, no migration, no per-user
"done" marker. Every service it calls is version-gated *and* version-storing, so the version
already written on the row is the marker — written in the same transaction as the work it
describes, so it cannot disagree with it.

## Structure Overview

The job sits in `worker/`, deliberately not in an app. `ingestion` owns the catalog,
`personalization` owns saves, `delivery` owns sends, and the propagation is the *job* that
joins them. Putting the loop inside `apps/ingestion` would satisfy every import contract
while reading as exactly the thing AD-17 exists to prevent.

It reads a change, pages the event's savers, and applies each one in three steps — snapshot,
then sends, then the notice. The order is forced, not chosen: AD-3 forbids a transaction
spanning `catalog` and `personal`, so the crash gap is permanent, and only one order leaves a
survivable inconsistency.

## Architecture

### Pattern Used

Service Layer with published commands. The consumer holds no business logic of its own — it
is an orchestrator that calls each module's published service and owns only the *ordering* and
the *failure policy*.

### Layer Structure

```text
┌──────────────────────────────────────────────┐
│  ingestion (catalog)                          │
│  appends EventStateChange, enqueues on commit │
└───────────────────┬──────────────────────────┘
                    │ outbox (plain data, no model)
┌───────────────────▼──────────────────────────┐
│  worker.propagation   ← the orchestrator      │
│  pages savers, dispatches per kind           │
└──────┬───────────────────────┬───────────────┘
       │                       │
┌──────▼─────────────┐ ┌───────▼────────────────┐
│ personalization    │ │ delivery                │
│ snapshot / cancel  │ │ lifecycle / notices     │
│ reinstate          │ │                         │
└────────────────────┘ └────────────────────────┘
```

### Data flow

1. A poll moves an event. `ingestion` appends one `EventStateChange` **per kind** and
   enqueues `worker.tasks.propagate_state_change` on commit.
2. The reconciler re-offers anything still unpropagated after five minutes.
3. The consumer reads the change as plain data, pages the savers by keyset, and applies each
   one: snapshot → sends → notice.
4. `propagated_at` is set only when every saver applied without raising.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/worker/propagation.py` | The per-user loop, the per-kind dispatch, the alarm's count |
| `backend/tests/worker/test_propagation.py` | The orchestration: ordering, idempotency, paging, failure |
| `backend/tests/worker/test_propagation_tasks.py` | The task seam and the alarm |

### Modified

| File | Changes |
|------|---------|
| `backend/apps/ingestion/services/outbox.py` | `StateChangeFacts`, `get_state_change`, `count_unpropagated_since` — published as plain data |
| `backend/worker/tasks.py` | The stub replaced; `report_stuck_propagation` added to the tick |
| `backend/shared/constants.py` | `PROPAGATION_ALARM_AFTER`, `LIFECYCLE_PERSONAL_BEHAVIOUR` |
| `backend/apps/delivery/services/state_notices.py` | Docstring: the notice is now raised |
| `backend/apps/delivery/services/scheduled_sends.py` | Docstring: the module is now the delivery half of AD-17 |
| `backend/apps/delivery/services/email_templates.py` | Docstring: the notice is now minted, not merely rendered |
| `backend/tests/ingestion/test_outbox.py` | The consumer's cases, replacing the placeholder's |
| `backend/tests/worker/test_scheduling_tasks.py` | The tick enqueues the new alarm |

## Domain Model

No new entities. **That is the design's claim**, and `makemigrations --check` confirms it.

| Entity | Change | Business Rules |
|--------|--------|----------------|
| `EventStateChange` | none | Append-only. `propagated_at` is its one mutable column, so there is nowhere to keep an attempts counter |
| `SavedEvent` | none | Its `event_version` *is* the "this user is done" marker |
| `ScheduledSend` | none | Its `event_version` is the marker for the delivery half; `held_at` came from item 1 |

## Key Implementation Details

### 1. No per-user marker, and the suite proves it

Every service called here is version-gated *and* version-storing:

| Service | Gate | Where the version lands |
|---|---|---|
| `update_saved_event_snapshot` | `new_version <= saved.event_version → False` | `SavedEvent.event_version` |
| `cancel_saved_event` / `reinstate_saved_event` | same | `SavedEvent.event_version` |
| `apply_lifecycle_change` | `event_version__gte=target.version → no-op` | `ScheduledSend.event_version` |
| `raise_state_notice` | `event_version__gte → False` | `StateChangeNotice.event_version` |

So a retried partial run re-walks every saver, and the ones already applied cost one indexed
read each and change nothing.

**The proof is a mutation, not an argument:** adding a gate of its own to the consumer breaks
**18** tests. That is what "sufficient" looks like when it is proven rather than asserted.

### 2. The order is forced, and the hold is the safety net

A crash between the two halves is permanent — AD-3 forbids the transaction that would make it
atomic. Only one order is survivable:

- **Sends first** → a user whose reminders were re-minted for the new time while their
  Timeline still shows the old one. A reminder contradicting the calendar it came from.
- **Snapshot first** → sends carrying the old version. And that state is already defended:
  item 1's sweep guard *holds* any send below the catalog's version, so nothing wrong goes out
  during the window. The next tick rewrites them.

The notice goes last, because it describes a state both halves have made true.

### 3. The personal side is not the same shape as the delivery side

`SAVED_EVENT` stores a time and a version; `SCHEDULED_SEND` stores a due time computed from
them. So `sold_out` and `detail_changed` change **nothing** the snapshot holds — calling the
snapshot updater for them would re-run conflict detection for an overlap that cannot have
moved. They still reach the delivery side, because a held send needs its version re-stamped
to be released.

Letting the snapshot's version lag is safe: every gate in this tree is `>` and not `==`.

### 4. The version handed to the lifecycle is the change's

`resolve_target` reads the version off the `SavedEvent` snapshot — and for a `sold_out` the
snapshot deliberately never moves. So the target would carry the *old* version,
`apply_lifecycle_change` would find nothing stale, and `held_at` would never be cleared. The
hold's only exit would silently stop working for exactly the two kinds that most often cause
one.

The version is replaced with the change's before the call.

### 5. A poisoned user is surfaced, not timed out

`EventStateChange` is append-only, so there is no counter to retire a poisoned change with,
and marking it propagated to stop the churn would claim a propagation that never happened and
strand that user on the old state forever. The loop continues past a failing user,
`propagated_at` stays NULL, and `report_stuck_propagation` bounds the **silence**.

## Security Considerations

| Concern | Approach |
|---|---|
| PII in logs | Ids only — `state_change_id`, `event_id`, `user_id`, `kind`. No title, no address, no name (AD-13) |
| The alarm's output | A count only, never a user id or an event title |
| Model exposure across the wall | `get_state_change` returns a frozen dataclass, not the model — a caller holding the model could write it (AD-2/AD-4) |
| New attack surface | None. No new endpoint, no new credential, no new external input, no new query parameter |
| Transaction boundaries | No transaction spans `catalog` and `personal` (AD-3) |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| One catalog read per change, not per saver | `_current_start` is hoisted into `propagate` and threaded through as a value. `get_public_events` is a batch read; asking it per saver would turn one read into one-per-saver on the only path that scales with the saver count |
| Bounded fan-out | Savers are paged `SAVERS_PAGE` at a time, keyset-paged on UUIDv7 `id` |
| A stalled cursor cannot spin forever | `PropagationCursorStalled` is raised when the cursor does not advance. A worker looping on page one makes no progress and raises nothing — that looks exactly like a slow job |
| No per-row catalog query in the sweep | Item 1's guard already batches; unchanged |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Per-user marker | **None** | Every service called is version-gated *and* version-storing. A marker could disagree with the work it describes; the version on the row cannot |
| Order of the halves | Snapshot → sends → notice | The only survivable one. Sends-first leaves a reminder contradicting the calendar; snapshot-first leaves sends the sweep already holds |
| Fan-out shape | One task per state change, paging savers internally | A task per user multiplies broker traffic by the saver count and buys no idempotency |
| The personal map | A separate `LIFECYCLE_PERSONAL_BEHAVIOUR`, total, no default | The two sides store different things, so the same shape would be wrong for two kinds. No default means a new kind fails a test rather than silently doing nothing |
| Where the job lives | `worker/`, not an app | AD-17's "Prevents" clause names `ingestion` reaching across the wall. It is also nobody's flow — the propagation is the job that joins the others |
| The bound on a poisoned change | An alarm, not a timeout | Append-only forbids a counter; setting `propagated_at` to stop the churn would be a lie that strands the user |
| The catalog read's placement | Once per change, outside every transaction | AD-3, and it is the same fact for every saver |

## Deviations from Plan

**None in substance.** One thing the design's checklist listed as owed — AD-17's accepted
residual-window test, deferred from `held-for-propagation-status` — was delivered here, as the
design promised, because the seam exists now: the notice is what corrects the window.

Two things were found during execution and code review and are recorded in the test report
rather than hidden: the catalog read was an N+1 against a batch API (fixed, and pinned), and
two acceptance criteria were not actually pinned by any test (three tests added, each verified
to fail under a mutation).

## Dependencies Added

None. No new package, no new library, no new service.

## How to Verify

1. **The consumer's own suite**

   ```bash
   cd backend && uv run pytest tests/worker/test_propagation.py tests/worker/test_propagation_tasks.py -q
   ```

   Expected: `40 passed`.

2. **The whole backend suite**

   ```bash
   cd backend && uv run pytest tests/ -q
   ```

   Expected: `5429 passed, 16 failed` — the 16 are pre-existing date-expired fixtures,
   reproduced identically on stashed code (`git stash` + re-run). They belong to
   `timeline-and-conflicts` and block CI on any branch.

3. **The architecture contracts**

   ```bash
   cd backend && uv run lint-imports && uv run ruff check . && uv run ruff format --check .
   ```

   Expected: `19 kept, 0 broken` · `All checks passed!` · `524 files already formatted`.

4. **No migration was needed**

   ```bash
   cd backend && uv run python manage.py makemigrations --check --dry-run
   ```

   Expected: `No changes detected` — the design's central claim, held.

5. **The design's proof, by hand**

   Add a gate to the consumer and watch the suite break:

   ```python
   # backend/worker/propagation.py, in _apply_to_user
   if change.event_version <= change.event_version:
       return
   ```

   Expected: `18 failed`. This is the evidence for D1 — the version gate inside the services is
   sufficient, and a second gate would refuse work the services would have accepted.

6. **The alarm, by hand**

   A state change that nobody can propagate stays NULL and is counted by
   `report_stuck_propagation` once it is older than `PROPAGATION_ALARM_AFTER` (30 minutes).
   The log line carries a **count** and no user id, no address.

## Test Coverage

- Tests added: **43** (29 in `test_propagation.py`, 11 in `test_propagation_tasks.py`, 3 in `test_outbox.py`)
- Mutations proven able to fail: **4**, each applied, run, and reverted
- Status: **passing**

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated (three stale docstrings corrected)
- [x] Developer notes captured

## Developer Notes

- **The version gate is the marker.** Do not add a "have I done this user?" check here. It
  would refuse work the services would have accepted, and nothing would come back to repair it.
  The proof is the mutation above: 18 tests break.
- **`EventStateChange` is append-only** — `append_only_mutable = frozenset({"propagated_at"})`,
  Python-guarded and trigger-enforced for every role. No claim column, no attempts counter, no
  per-user cursor. If a future change needs one, it needs a table in `catalog`.
- **The times come from the change's `after`, never from the live `Event`.** A poll appends one
  change per kind, so the live event already holds the *last* kind's facts. Pairing this
  change's version with those times stamps a snapshot that never existed.
- **`sold_out` and `detail_changed` skip the personal side but not the delivery side.** The
  snapshot deliberately never moves for them, so the version handed to
  `apply_lifecycle_change` must be the change's, not the target's — otherwise `held_at` is
  never cleared and the hold's only exit silently stops working.
- **A `CANCEL` must cancel the held rows, not release them.** A held row left `pending` is
  picked up by the next sweep and sent — a reminder for an event that is not happening. The
  mutation that got this wrong broke four tests.
- **`_current_start` is called once per change.** If it moves back into the per-user path, a
  popular event costs one catalog round-trip per saver.
- **The pre-existing 16 failures are date-expired fixtures**, not regressions. They grew from
  8 to 16 as the calendar rolled over. Fix them by anchoring to `timezone.now()`, not by
  bumping a pinned constant.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-025*
