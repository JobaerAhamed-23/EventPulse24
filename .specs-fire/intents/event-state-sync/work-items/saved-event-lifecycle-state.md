---
id: saved-event-lifecycle-state
title: A cancelled event still looks alive on the personal side — the save's
  lifecycle state
intent: event-state-sync
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-11-04
run_id: run-eventpulse24-025
completed_at: 2026-11-06T07:56:29.500Z
---

# Work Item: A cancelled event still looks alive on the personal side — the save's lifecycle state

## Description

`SavedEvent` records a time snapshot and nothing else. `apps/personalization/models.py:286-298` is the whole of it: `user_id`, `event_id`, `start_utc`, `end_utc`, `event_version`, `saved_at`. There is no column that can say *this event is not happening*.

That is fine while every saved event is live, and it becomes wrong the moment propagation exists. AD-17 says a cancellation "cancels `pending` sends, closes conflicts, queues a notice" — and then the save row itself is still sitting in the Timeline and the digest, holding a start time, indistinguishable from an event that is going ahead. The personal side cannot ask `catalog` whether it is dead: AD-3 forbids the join, and AD-21 is explicit that "the Timeline and conflict detection read the snapshot; they never join `catalog`."

This item gives the snapshot somewhere to put that fact, builds the cancellation path that writes it, and adds the reverse lookup the propagation consumer needs.

**The reverse lookup is the quiet blocker.** Every function in `saved_events.py` takes `user_id` **and** `event_id` — `save_event`, `unsave_event`, `update_saved_event_snapshot`, `get_saved_event`. A state change arrives naming only an event. There is no published read that answers *who saved this?*, so the consumer has nobody to iterate.

**This item needs a design doc (Checkpoint 1) before any code.** It adds a column to a model AD-17 describes by name and does not describe this field for, and it settles how a dead event behaves in three shipped surfaces.

## Acceptance Criteria

- [ ] `SavedEvent` can represent a **cancelled or superseded** event without any read crossing the schema wall. The `import-linter` contracts and `tests/architecture/` stay green.
- [ ] A published **cancellation/supersede service** in `personalization` that: marks the save, closes its `CONFLICT_PAIR`s via the existing `close_pairs_for_side` (`conflicts.py:285`), writes an audit row, and is **version-gated exactly as `update_saved_event_snapshot` is** — applying only when the change's `event_version` exceeds the stored one.
- [ ] A published **reverse read** naming every user affected by one event's state change, **batched and bounded** — it runs for every state change on a popular event and must not degrade into a per-user query storm.
- [ ] The reverse read covers **both populations FR-54 names**: users who saved the event, and users who have a `ReminderPlan` for it. The design doc states whether those sets can differ and what the consumer does if they do.
- [ ] A **cancelled public event never auto-cancels a personal event** (FR-55). The personal event is untouched; only the save and its pairs change.
- [ ] A **superseded** event (AD-4, beyond ±30 days) behaves as a cancellation on the personal side. AD-17: *"users are notified and re-save; plans are never silently migrated."* No plan is migrated to the new Event.
- [ ] **`reinstated` reverses it.** A save marked dead by a cancellation returns to live when the event is reinstated, and its conflict pairs are re-evaluated rather than left closed.
- [ ] The three shipped surfaces that read the snapshot — Timeline, `/conflicts`, and digest candidate selection — each state their behaviour for a dead save, and each is tested.
- [ ] Tests: the version gate at the exact boundary; an out-of-order cancellation after a newer change is a no-op; cancel → reinstate → cancel is idempotent at each step; a personal event conflicting with a cancelled save survives unmodified.

## Technical Notes

**Design-doc decisions (Checkpoint 1):**

- **Where the lifecycle fact lives.** A status column on `SavedEvent`, or a separate row, or a nullable `cancelled_at`. The Spine's `SAVED_EVENT` description names three snapshot fields and not a fourth; whichever is chosen is an amendment to that description and should be written as one.
- **Whether the personal side mirrors `Event.Status` or carries its own vocabulary.** `public-event-page.tsx:279-280` already establishes the rule that "the vocabulary is the backend's" — `scheduled`/`postponed`/`cancelled`. A second, divergent vocabulary on the personal side would be a new translation layer. But `sold_out` is not a `status` (it is `is_sold_out`), and `superseded` is a catalog concept the personal side may not need.
- **What the Timeline and digest do with a dead save.** Hide it, show it struck through, or keep it until the user dismisses it. FR-55's consequence is only *"event is removed from the digest"* — it says nothing about the Timeline, and silently vanishing from a calendar the user curated is its own kind of wrong.
- **The reverse read's shape and bound.** Whether it returns user ids for the consumer to page, or the consumer claims in batches. A state change on a popular event must not hold a long transaction.

**What already exists and must be reused, not reimplemented:** `close_pairs_for_side` and `reconcile_pairs_for_side` (`conflicts.py:285, 334`), `detect_conflicts` / `record_detected_conflicts` (`conflicts.py:160, 229`), and the version-gate-plus-audit shape of `update_saved_event_snapshot` (`saved_events.py:243`), which is the template this service should follow closely enough that a reader sees them as a pair.
