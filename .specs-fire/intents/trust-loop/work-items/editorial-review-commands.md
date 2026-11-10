---
id: editorial-review-commands
title: Approve, edit, reject — the editor's three verbs as ingestion commands
intent: trust-loop
complexity: medium
mode: confirm
status: pending
depends_on:
  - review-queue-model
  - event-rejection-state
created: 2026-11-10
---

# Work Item: Approve, edit, reject — the editor's three verbs as ingestion commands

## Description

AD-14 says the `editorial` app "writes **through `ingestion` services** like any other client; it gets no privileged write path". This item builds those services: the only way a `ReviewItem` gets resolved, and the only way an editor changes an event. The admin in `editorial-admin-queue` is a thin caller of them.

## Acceptance Criteria

- [ ] **`approve_review_item`:** publishes an `in_review` event (`publication_status` becomes `published`), or confirms a reported event as correct. It closes the item as `approved`.
- [ ] **`edit_and_publish`:** corrects a bounded set of editable event fields (title, start and end with their timezone, and venue, as the plan lists them), then publishes. A lifecycle-field change bumps `event_version` and appends an `EventStateChange` exactly like an ingestion-driven change, so AD-17 carries it to saved users. The item closes as `edited`.
- [ ] **`reject_review_item`:** applies the representation `event-rejection-state` chose, and closes the item as `rejected`.
- [ ] **`dismiss_source_item`:** closes a `source_reliability` item without changing the source. A low score never pauses a source (FR-16).
- [ ] Every command:
  - requires an editor `Actor` and refuses a system or anonymous actor
  - is attributed (`ActorColumns`)
  - writes an `IngestionAuditEntry`
  - runs in one catalog transaction
- [ ] **Stale-safe:** resolving an item that is already closed is refused with a domain error, and so is resolving one whose event has changed version since the editor opened it. An editor never overwrites an ingestion update they didn't see.
- [ ] **An FR-16 observation is recorded for each resolution**, attributed to the event's owning source. A reject is negative and an approve is positive. An edit is recorded the way `reliability-recompute-and-escalation` will consume it, and this item leaves it as a stored fact, not a computed score. The observation shape is agreed with that item's design before this one closes. If that design isn't settled yet, the shape is recorded here as a deferral in its ACs.
- [ ] An editorial edit is not undone by the next ingestion poll. The plan states the editorial-lock rule the brief deferred ("editorial vs. automatic re-gating"), and a test pins it.
- [ ] Tests cover:
  - each command's happy path
  - each refusal (closed item, stale version, non-editor actor)
  - the version bump and the `EventStateChange` row on a time edit
  - the observation row
  - an ingestion poll after an edit

## Technical Notes

`apps/ingestion/services/event_writes.py` has `apply_lifecycle_change` (:224) and `_record_change` (:156). An editorial time edit should go through the same functions, not a parallel path. `services/audit.py:write_audit` refuses to run outside a catalog transaction. Keep that.

## Dependencies

- review-queue-model
- event-rejection-state
