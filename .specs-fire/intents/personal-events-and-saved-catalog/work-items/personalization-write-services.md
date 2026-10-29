---
id: personalization-write-services
title: Personalization Write Services
intent: personal-events-and-saved-catalog
complexity: high
mode: validate
status: pending
depends_on: [conflict-domain-and-constants, personalization-models, delivery-reminder-plan-owner]
created: 2026-10-29
---

# Work Item: Personalization Write Services

## Description

Implements the commands that write `personal`. These are the only way anything in the `personal` schema changes, and they are where AD-5, AD-16 and AD-21 actually take effect.

The commands:

- **`create_personal_event`** — FR-18. Validates the explicit timezone, writes the event, attaches the default reminder plan via `delivery`'s published service, runs conflict detection, and (if a conflict is found) leaves the flow **incomplete pending the user's forced choice**.
- **`update_personal_event`** — FR-18. Re-runs conflict detection after the edit, per the UX spine: "Edit the new one — opens the new event in edit mode with the conflicting time pre-highlighted. After editing, conflict detection re-runs."
- **`delete_personal_event`** — FR-18. Closes any conflict pairs involving the event.
- **`save_event`** — AD-21. Writes the `SAVED_EVENT` row with a snapshot read from `catalog` through `ingestion`'s published read interface, re-reads the event's version after commit, and requests re-propagation if it moved meanwhile.
- **`unsave_event`** — removes the save and closes any conflict pairs it participated in.
- **`resolve_conflict`** — FR-58. Records the `ConflictResolution` on the pair.

Two architectural decisions need settling here:

1. **The write-ownership boundary between `personalization` and `delivery`.** `personalization` creates a personal event but must not write `REMINDER_PLAN`. The seam, the transaction scope (one `personal` transaction that calls into `delivery`'s service, or two), and the failure behaviour when the plan attachment fails all need deciding.
2. **The save-race with a catalog postponement.** AD-21 requires the version to be re-read after commit and re-propagation requested if it moved. This is the subtlest requirement in the intent.

**Mode: validate.** A design doc and two checkpoints precede implementation.

## Acceptance Criteria

- [ ] **A design doc exists** at `.specs-fire/intents/personal-events-and-saved-catalog/work-items/personalization-write-services-design.md`, covering the `personalization` ↔ `delivery` boundary and transaction scope, the save-race protocol, the conflict-detection-on-write flow, and the forced-choice state machine.
- [ ] The design doc is **reviewed and approved** before implementation begins (Checkpoint 1).
- [ ] Every command takes an explicit `Actor` (from `shared.actor`), never a `request` object. The actor is stored by value on the audit row via `ActorColumns`.
- [ ] Every mutation writes an audit row **in the same transaction** as the mutation, using the `personalization` audit table. The ingestion precedent is `apps/ingestion/services/audit.py`, which raises `AuditOutsideCatalogTransaction` when called outside a transaction — the `personal` equivalent must raise rather than silently write an orphaned audit row.
- [ ] Every command passes `using=PERSONAL` explicitly to its queries and its `transaction.atomic` block.
- [ ] Conflict detection runs **on write** — on create, on edit, and on save — and **never at render time**. The commands call the single function from `domain/conflict.py`.
- [ ] A conflict detected on personal event creation **does not silently complete the creation**. The command returns a conflict result that leaves the flow awaiting one of the three explicit choices. There is no code path that completes a conflicted creation without a recorded `ConflictResolution`.
- [ ] **`resolve_conflict` records the resolution on the pair** and makes it immutable. A resolved pair is never re-prompted. The `ConflictResolution` value is recorded for **every** prompt, including those resolved by editing or deleting.
- [ ] `create_personal_event` attaches the default reminder plan by **calling `delivery`'s published service**. It does not import `apps.delivery.models` and does not write the `REMINDER_PLAN` table. This is asserted by the import contract and by a test.
- [ ] `create_personal_event` refuses a floating or ambiguous local time. An explicit IANA zone is required. The refusal is a domain error that maps to the standard `{code, message, details?}` shape via the single handler in `config/errors.py` — not a raw `ValueError` leaking as a 500.
- [ ] **`save_event` reads the catalog event through `ingestion`'s published read interface** (`apps/ingestion/services/catalog_read.py`), never by importing `apps.ingestion.models` and never by a cross-schema join. The `models-ingestion` import contract keeps passing.
- [ ] **`save_event` implements the AD-21 race protocol:** read the event's `event_version` → write the `SAVED_EVENT` snapshot → commit → re-read the event's version → if it moved, request re-propagation for that user. A test simulates a postponement landing between the first read and the commit and asserts the snapshot is not left stale.
- [ ] Saving the same event twice is idempotent — one row, not two.
- [ ] `unsave_event` and `delete_personal_event` close the conflict pairs they participated in, marking them `cleared_by_state_change` where the pair ends because one side went away (which AD-21 says is "not a user resolution").
- [ ] No command runs long work inside a request (AD-11). Conflict detection is an in-process pure computation over the user's own events, so it is bounded and fast; if the event count ever makes it unbounded, it moves to a worker task rather than growing inside the request.
- [ ] `beat_schedule` is **unchanged** — still exactly one 60s tick. `backend/tests/worker/test_tick.py` passes untouched.
- [ ] No LLM call anywhere (AD-8's gateway is not involved; this intent makes no model calls).
- [ ] Tests cover: create with an explicit timezone; create refused without one; create producing a conflict that blocks completion; each of the three resolutions; edit re-running detection; delete closing pairs; save writing a correct snapshot; save racing a postponement; double-save idempotency; unsave closing pairs; and a default plan attached via `delivery`'s service.

## Technical Notes

Read `apps/ingestion/services/event_writes.py` and `apps/ingestion/services/ingest_source.py` first. They are the reference for what a command in this codebase looks like: a plain function taking an explicit `Actor` and plain data, `now` passed explicitly, `transaction.atomic(using=CATALOG)` around the write, and an audit row inside it.

The same pattern applies here with `using=PERSONAL`.

The AD-3 wall means a `personal` transaction and a `catalog` transaction **cannot** span each other. So `save_event` necessarily does: a non-transactional read of `catalog` → a `personal`-only transaction for the `SAVED_EVENT` write → a non-transactional re-read of `catalog`. The save-race protocol is what closes the gap the wall leaves open. This is the same shape AD-17 uses for the sweep: "the claim transaction is **`personal`-only**. Every event-bound `SCHEDULED_SEND` carries the `event_version` it was scheduled against. After claiming a row, the sweep reads the Event's current `event_version` through `ingestion`'s read interface — a separate, non-transactional read."

`ingestion`'s published read interface hands over **plain data** — a frozen dataclass, not a model instance — so the calling app never holds a reference to `apps.ingestion.models` and the wall holds without either side knowing the other's models. `save_event` consumes that dataclass and writes it into the `personal` snapshot.

On the forced choice: the PRD requires "exactly three buttons" and "**no dismiss or X button**", and that the creation flow "cannot complete" without one. The cleanest expression is for `create_personal_event` to return a discriminated result — either the created event, or a pending-conflict payload — and for the API layer to turn the latter into the three-action prompt. The alternative (creating the row and then prompting) would leave a conflicted event in the database with no resolution recorded, which breaks the "a `ConflictResolution` is recorded for every conflict prompt" rule.

AD-21 also notes the re-evaluation path for AD-17 propagation: "the propagation job calls each owner's published service — ... `personalization` updates the `SAVED_EVENT` snapshot and re-evaluates `CONFLICT_PAIR`s (AD-21)." Design the service functions so that path exists even though the propagation job lands later. A public `update_saved_event_snapshot(event_id, user_id, new_version, new_start, new_end)` with the "only if the new version is greater" rule is the shape AD-17 describes.

## Dependencies

- conflict-domain-and-constants
- personalization-models
- delivery-reminder-plan-owner
