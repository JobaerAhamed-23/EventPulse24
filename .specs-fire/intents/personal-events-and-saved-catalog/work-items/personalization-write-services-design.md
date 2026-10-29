---
work_item: personalization-write-services
intent: personal-events-and-saved-catalog
created: 2026-10-29
mode: validate
checkpoint_1: approved
---

# Design: Personalization Write Services

## Summary

This item implements the commands that write the `personal` schema. They are the only way
anything in `personal` changes, and they are where AD-5 (audit in the same transaction), AD-16
(write ownership) and AD-21 (conflict detection on write, snapshots not joins) actually take
effect.

The commands:

| Command | Requirement | What it writes |
|---|---|---|
| `create_personal_event` | FR-18, FR-20 | `PersonalEvent`, a default `ReminderPlan` (via `delivery`), and any detected `ConflictPair` |
| `update_personal_event` | FR-18 | the edited `PersonalEvent` (version +1) and any re-detected `ConflictPair` |
| `delete_personal_event` | FR-18 | the deleted event and the closure of its conflict pairs |
| `save_event` | AD-21 | a `SavedEvent` snapshot read from `catalog` |
| `unsave_event` | AD-21 | the removed save and the closure of its conflict pairs |
| `resolve_conflict` | FR-58 | the `ConflictResolution` on a `ConflictPair` |

Three things need settling carefully, and they are the reason this item is `validate`:

1. **The `personalization` ↔ `delivery` boundary.** `personalization` creates a personal
   event but must not write `REMINDER_PLAN`. The seam, the transaction scope, and the failure
   behaviour all need deciding.
2. **The save-race with a catalog postponement.** AD-21 requires the version to be re-read
   after commit and re-propagation requested if it moved. This is the subtlest requirement in
   the intent.
3. **The forced-choice state machine.** A conflict found on creation must *not* silently
   complete the creation, and every prompt must end in a recorded resolution.

Everything here is a command: a plain function taking an explicit `Actor` and plain data,
`now` passed explicitly, `transaction.atomic(using=PERSONAL)` around the write, and an audit
row inside it. No `request` object ever reaches a service.

## Scope

**In Scope:**

- Six commands in `apps/personalization/services/`
- The `personalization` audit writer (`apps/personalization/services/audit.py`)
- A published conflict-detection service that calls `domain/conflict.py` and normalises the
  pair sides
- The `personalization` → `delivery` call that attaches the default reminder plan (FR-20)
- The AD-21 save-race protocol in `save_event`, and the propagation-shaped entry points it
  implies
- The `ConflictPair` side normalisation the model's unique constraint depends on
- Tests for every behaviour the work item's AC names

**Out of Scope:**

- The API surfaces (`personal-events-api`, `saved-events-api`)
- The frontend conflict sheet (`frontend-personal-and-conflict-surfaces`)
- The `/conflicts` read query — that is a read, and it belongs to the API item
- AD-17's propagation *job*. This item publishes the services the job will call; the job
  itself lands in a later intent, as it does for `delivery`'s `SCHEDULED_SEND` rewrite
- The reminder-plan *picker* — `delivery` already published `set_plan_slots` (item ④)
- `CalendarConnection` and AD-18's calendar import
- Any LLM call (AD-8's gateway is not involved)

## Key Decisions

### The `personalization` ↔ `delivery` boundary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D1. The seam** | `personalization` calls `apps.delivery.services.reminder_plans.attach_default_plan`. It never imports `apps.delivery.models` and never touches the `REMINDER_PLAN` table. | AD-16's contested rule, settled: "`delivery` owns `REMINDER_PLAN`. `personalization` calls `delivery`'s published service to attach the default plan when it creates a `PERSONAL_EVENT` (FR-20)." Item ④ published exactly that service, with `attach_default_plan(user_id, target_kind, target_id, actor, now)`. The `models-delivery` import contract keeps the wall honest, and a test asserts the import never happens. |
| **D2. The transaction scope** | **One `personal` transaction.** `create_personal_event` opens `transaction.atomic(using=PERSONAL)`, writes the event, and calls `attach_default_plan` *inside* it. `delivery`'s service opens its own `transaction.atomic(using=PERSONAL)` — a nested `atomic` on the same alias is a savepoint, so both commit or roll back together. | Both tables live in the `personal` schema and are written by the same role, so there is no AD-3 wall between them — only a write-ownership boundary. One transaction means the event and its default plan are never out of step: there is no window in which a personal event exists with no plan, and no plan exists for an event that was rolled back. A second transaction would make "the event was created but the plan failed" a real state, and FR-20's "a new Personal Event has a Reminder Plan of 1d + 1hr by default" would be only eventually true. |
| **D3. Failure behaviour** | A failure inside `attach_default_plan` rolls back the whole creation. `create_personal_event` does **not** swallow it and does **not** create the event without a plan. | FR-20 says the default plan is part of what a created Personal Event *is*, not an optional extra. An event with no plan would silently fail FR-20 and would need a repair path that nothing else in the product has. The failure is loud, and the user retries. |
| **D4. The audit actor on the plan** | The plan's audit row is written by `delivery`'s own `write_audit`, with the **same actor** the caller passed to `attach_default_plan`. `personalization` writes no audit row for the plan. | The plan's audit row belongs to `delivery`'s table, and `delivery` owns it. Two apps writing one row would break AD-16 in the other direction. The actor is the *user's*, because the user created the event — not a system job — and `attach_default_plan` already takes an `Actor` for exactly this. |
| **D5. The default plan is attached once, at creation** | `create_personal_event` attaches the default plan. `update_personal_event` does **not** re-attach it. | FR-20's default is a property of *creation*. Re-attaching on every edit would silently reset a plan the user had customised (FR-9's picker) back to 1d + 1hr — the user edited the event's time and lost their reminders. The plan is edited through `delivery`'s `set_plan_slots`, which is item ④'s command. |

### The commands

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D6. The shape of a command** | Every command is a plain function: keyword-only arguments, an explicit `Actor`, an explicit `now`, plain data in and out. `transaction.atomic(using=PERSONAL)` around the write; the audit row inside it. | The `apps/ingestion/services/` convention, which the work item names as the reference. It is also what makes the commands testable at an exact second and what keeps `request` objects out of the service layer (AD-5's "services receive an explicit actor argument, never a `request`"). |
| **D7. The audit writer** | `apps/personalization/services/audit.py`, mirroring `apps/ingestion/services/audit.py`: `write_audit(actor=..., action=..., target_type=..., target_id=..., details=...)`, raising `AuditOutsidePersonalTransaction` when `connections[PERSONAL].in_atomic_block` is false. | The work item's AC: "the `personal` equivalent must raise rather than silently write an orphaned audit row." An orphaned audit row records a change that rolled back. |
| **D8. `now` is passed explicitly** | Every command takes `now: datetime` and uses it for `detected_at`, `resolved_at`, `saved_at` and the audit `at`. The models' `auto_now_add` / `auto_now` fields are left to the database. | The `ingestion` convention. It makes each boundary testable at the exact second, with no time-freezing library. |
| **D9. `update_personal_event` bumps `version`** | The command increments `version` by exactly one, using `F("version") + 1` in the same `UPDATE`. | AD-7's send key uses `personal_event_revision`, so the value must only ever go up. The model cannot know which write is legitimate (item ③'s D9), so the increment is the command's contract. `F()` makes it atomic against a concurrent write. |
| **D10. `update_personal_event` closes the pairs it invalidates** | When an edit changes the event's time, the pairs that referenced its *old* time are re-evaluated: a pair that no longer overlaps is closed as `cleared_by_state_change` (nobody answered it — the world moved); a pair that still overlaps stays `active`; a *new* overlap creates a new pair. | AD-21: the pair's existence is a claim about the two events' times. If the time moves and the pair stays `active`, the `/conflicts` list lies. And the pair's status must reflect the *current* times, not the times when it was detected. |
| **D11. `delete_personal_event` closes its pairs as `cleared_by_state_change`** | Every `active` pair naming the event is closed with `status = cleared_by_state_change`, `resolution = NULL`, `resolved_at = now`. | AD-21 names the status exactly, and says a cleared pair "is not a user resolution" — so `resolution` stays NULL. The model's `conflict_pair_status_ck` enforces that shape. Closing them at delete time is what keeps the `/conflicts` list from showing a pair whose other side no longer exists. |
| **D12. `unsave_event` closes its pairs the same way** | Same as D11. | AD-21's rule is about the *pair ending because a side went away*, which is true of an unsave exactly as it is of a delete. The two commands share one helper. |
| **D13. `delete_personal_event` does not delete the reminder plan** | The event row goes; the plan row stays. | The plan is `delivery`'s to write and to delete. `personalization` may not write `REMINDER_PLAN`, and deleting it would be a write. `delivery`'s published interface is where a "remove the plan" belongs; until it exists, a deleted event's plan row is inert. This is a **known gap**, recorded below. |
| **D14. Every command's audit action is named** | `personal_event.created`, `personal_event.updated`, `personal_event.deleted`, `saved_event.saved`, `saved_event.unsaved`, `conflict.resolved`. Plus `conflict.detected` for a pair created by detection. | AD-5: "every mutation is a named command with an audit-log write in the same transaction." The names are stable slugs, and `delivery` uses the same shape (`reminder_plan.attached_default`). |

### Conflict detection on write

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D15. Detection is a service, not a command** | `apps/personalization/services/conflicts.py` publishes `detect_conflicts(*, user_id, candidate, now) -> list[DetectedConflict]`. It is **pure with respect to the database**: it reads the user's events and returns the pairs it finds, and a separate step writes them. | AD-21's "one overlap function" is `domain/conflict.py`, and it is already pure. The service's job is to *gather candidates* and *call the domain function*; the command's job is to *write* the pairs. Splitting them means the same detection can run on create, on edit, on save and on propagation, and each of those sites decides what to do with the result. |
| **D16. Which candidates are compared** | A candidate event (personal or saved) is compared against the user's other **personal** events and their **saved** events. The candidate scan window is **±30 minutes** around the candidate's start, widened to **±24 hours** for the duplicate rule (which is already absolute in `domain.conflict.is_duplicate`). | FR-58: "the system scans for other Personal Events within ±30 minutes of the new event's start time", and the duplicate rule's own 24-hour window. The window is a *service*-layer concern (which events to compare), not a model or domain concern, so the constant lives in `shared/constants.py` as `CONFLICT_SCAN_WINDOW`. The overlap *threshold* (15 minutes) is `CONFLICT_MIN_OVERLAP` in the domain and is not re-declared. |
| **D17. The two rules produce two kinds** | A **time** conflict when `domain.conflict.conflicts` is true. A **duplicate** conflict when `domain.conflict.is_duplicate` is true. A pair that satisfies both is recorded as **one `duplicate` pair** (the duplicate prompt's buttons are a superset in usefulness: "Update the existing one" is the more specific instruction). | FR-58's two prompts are distinct, and `ConflictPair.kind` exists precisely because the pair's kind is not derivable from its sides (item ③'s D22). When both rules fire, one pair must be recorded — the unique constraint would reject the second anyway. `duplicate` is the stronger claim (it asserts "these are the same event"), and `update_existing` is the resolution that acts on it. |
| **D18. The pair sides are normalised** | The two sides are sorted lexicographically on `(kind, id)` before the pair is written: the `left_*` side is the smaller. | Item ③'s D23 and the model's own docstring: the unique constraint is symmetric only if the command layer normalises. `(A,B)` and `(B,A)` must be one row, or the same conflict is detected twice and the user is prompted twice. The normalisation is this layer's responsibility — the model says so explicitly. |
| **D19. The "new" side is tracked, not just the pair** | The pair row holds both sides symmetrically, but the *prompt* needs to know which side is the new one (the one the user just created). The detection result carries it; the pair row does not. | FR-58's buttons are asymmetric: "Delete the new one" must delete the new one, not whichever side sorts first. If the pair row alone held the sides, the resolution could not know which to delete. The `detect_conflicts` result therefore names `new_side` and `other_side`, and `resolve_conflict` is given the resolution plus the pair, and the *caller* (the API layer) knows which side is "new" from the flow it is in. |
| **D20. A pair is written once and updated, never duplicated** | Writing a pair uses `update_or_create` on the normalised sides. If the pair exists and is `active`, it is left alone. If it exists and is `resolved` or `cleared_by_state_change`, it is **not** re-opened: the resolution is immutable (item ③'s D24) and AD-21 says "a resolved pair is immutable and never re-prompted". | AD-21, plainly. Re-opening a resolved pair would rewrite a closed row — which the `guard_conflict_pair` trigger **refuses**, so the attempt would fail with a database error rather than a domain one. The command must not even try. |
| **D21. A conflict on create blocks the completion** | `create_personal_event` returns a **discriminated result**: either `Created(event=...)` or `ConflictFound(conflicts=[...])`. In the `ConflictFound` case the event row **is written** but the flow is **incomplete**: the result says the creation is awaiting the user's forced choice, and no completion is signalled. | The work item's Technical Notes settle this: "The cleanest expression is for `create_personal_event` to return a discriminated result — either the created event, or a pending-conflict payload — and for the API layer to turn the latter into the three-action prompt. The alternative (creating the row and then prompting) would leave a conflicted event in the database with no resolution recorded, which breaks the 'a `ConflictResolution` is recorded for every conflict prompt' rule." The row *is* written because the pair references it by id; but the **prompt** is what is pending, and the resolution is recorded when the user chooses. The pair row is `active` and *is* the pending prompt. |
| **D22. Every prompt ends in a recorded resolution** | `resolve_conflict` writes the resolution onto the pair and closes it as `status = resolved` — **whatever the choice was**, including `edit_new` and `delete_new`. The pair's status is `resolved` in all three cases; the *action* the choice names happens after the resolution is recorded. | The work item's AC: "The `ConflictResolution` value is recorded for **every** prompt, including those resolved by editing or deleting." The model's `conflict_pair_status_ck` is what forces this reading: a `cleared_by_state_change` pair must carry a **NULL** resolution, so a pair the user answered can never be a cleared one. `cleared_by_state_change` is reserved for a pair that ended because a side went away *without* the user answering — an unrelated delete, an unsave, or a propagation-driven close. The two statuses are therefore exactly "the user answered" and "nobody answered", which is what makes them distinguishable. |
| **D23. `resolve_conflict` validates the resolution against the kind** | `edit_new` is legal only for a `time` pair; `update_existing` only for a `duplicate` pair. An illegal pairing raises a domain `ValidationError` before anything is written. | The model's `conflict_pair_resolution_kind_ck` already makes an illegal pairing unwritable; the command checks first so the user gets a readable error rather than a database error. The pairing is FR-58's: the time prompt's button 2 is "Edit the new one", the duplicate prompt's is "Update the existing one". |
| **D24. `resolve_conflict` is immutable once applied** | A pair that is already `resolved` or `cleared_by_state_change` cannot be resolved again; the command raises `ConflictAlreadyResolvedError`. | AD-21: "A resolved pair is immutable and never re-prompted." The trigger enforces it in the database; the command enforces it in Python, so the user gets a domain error rather than a `RestrictViolation`. |
| **D25. `resolve_conflict` may act on the choice** | `resolve_conflict` with `delete_new` deletes the new side; with `edit_new` it returns the new side's id so the caller opens it in edit mode; with `keep_both` it only records the resolution. | FR-58's buttons are actions, not just labels. "Delete the new one — Removes the new event." The command that owns the deletion is `delete_personal_event`, so `resolve_conflict` calls it rather than writing the delete itself — one path to delete an event, one audit trail. |
| **D26. `keep_both` keeps the pair `resolved`, not `active`** | The pair's status becomes `resolved` with `resolution = keep_both`, and the indicator persists. | FR-58: "The conflict indicator remains on both Pulse Cards **permanently**. No further prompting for this conflict pair." The status `resolved` is what stops the prompt (D20, D24); the *indicator* is a read-time projection of a resolved pair with `keep_both`, which is the API item's concern. |

### The save-race protocol (AD-21)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D27. The shape** | `save_event` does, in order: (1) open a `personal` transaction and read the catalog event's `event_version` through `ingestion`'s published interface — the read happens *inside* the transaction, but on the `catalog` alias, so it is not part of that transaction; (2) write the `SavedEvent` snapshot with that version and the event's times; commit; (3) re-read the catalog event's version — a **non-transactional** read; (4) if it moved, request re-propagation for that user. | AD-21: "A save re-reads the Event's version after commit and requests re-propagation for that user if it moved meanwhile, so a save racing a postponement cannot keep a stale snapshot." The wall (AD-3) forbids a transaction spanning `catalog` and `personal`, so the protocol is: read, write, commit, read again. |
| **D28. The first read is inside the transaction** | The snapshot is written with the version read immediately before the write, inside the same transaction. | Reading the version *before* the transaction opened would widen the race window to the whole transaction rather than to the moment of the write — and would make the check after the commit meaningless, because the version being compared against could already be stale. The read is inside the transaction but on the `catalog` alias, so it is still not part of it: the wall is untouched. |
| **D29. The staleness check** | After the commit, the catalog event's version is re-read. If the re-read version is **greater** than the version stored in the snapshot, the snapshot is stale. | AD-17's rule, applied at the save site: "only if the change's `event_version` is greater than the version already stored". Greater, not different: a re-read of the *same* version means nothing moved. |
| **D30. What "request re-propagation" means** | `save_event` **records the request on the save row** and returns it, rather than sending a job. The API layer (item ⑥) or the propagation job (a later intent) acts on it. | The propagation job does not exist yet (`worker.tasks.propagate_state_change` is an explicit placeholder that "deliberately leaves `propagated_at` NULL"). `personalization` cannot enqueue a propagation job without reaching into `ingestion`'s outbox, which would be `personalization` writing `catalog`'s concern — an AD-16 violation. The seam is a plain value: the save's result says "this snapshot is stale, re-propagation is needed for this user and event". |
| **D31. The stale-save marker** | The staleness is expressed by the command's **return value** (`SaveResult(saved=..., stale=True, current_version=...)`) and recorded in the audit row's `details`. No extra column is added to `SavedEvent`. | The model is item ③'s, already shipped and migration-frozen. Adding a `stale` column would need a new migration for a value that is only meaningful between the commit and the next propagation. The audit row records the fact; the return value tells the caller. The *fix* — re-stamping the snapshot — is the propagation service's job (D35). |
| **D32. Saving twice is idempotent** | `save_event` upserts on `(user_id, event_id)`: one row, and a second save updates the snapshot rather than adding a row. | The work item's AC: "Saving the same event twice is idempotent — one row, not two." The model's `saved_event_user_event_uq` is the guarantee; the command upserts against it. A second save of an unchanged event is a no-op that still writes an audit row (AD-5: it *is* a mutation attempt, and the fact that nothing changed is worth recording). |
| **D33. `unsave_event` removes the row and closes its pairs** | The `SavedEvent` row is deleted; its `active` pairs are closed as `cleared_by_state_change`. | D12. A removed save must not leave a dangling side in a pair. |
| **D34. The propagation-shaped entry point** | `apps/personalization/services/saved_events.py` publishes `update_saved_event_snapshot(*, event_id, user_id, new_version, new_start_utc, new_end_utc, actor, now) -> bool`. It updates the snapshot **only if** `new_version` is greater than the stored `event_version`, and returns whether it applied. It re-evaluates the user's conflicts against the new time. | The work item's Technical Notes name this exact shape: "A public `update_saved_event_snapshot(event_id, user_id, new_version, new_start, new_end)` with the 'only if the new version is greater' rule is the shape AD-17 describes." The job lands later; the service it will call lands now, so the seam exists and is tested. |
| **D35. `save_event` reads through `ingestion`'s published interface** | It calls `apps.ingestion.services.catalog_read.get_public_event(event_id=...)`, which returns a `PublicEvent` frozen dataclass — plain data, not a model instance. `personalization` never imports `apps.ingestion.models`. | The work item's AC: "`save_event` reads the catalog event through `ingestion`'s published read interface ... never by importing `apps.ingestion.models` and never by a cross-schema join." The `models-ingestion` import contract keeps it honest. The dataclass means neither side knows the other's models. |
| **D36. A non-public event cannot be saved** | `get_public_event` raises `EventNotFoundError` for an event that is unpublished, `in_review` or superseded. `save_event` propagates it. | AD-6: only published, non-superseded, upcoming events are publicly visible, and the public catalog has one truth. A save of a hidden event would put a snapshot in `personal` that no public read could produce. |

### The command layer's remaining rules

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D37. The timezone is required and validated** | `create_personal_event` and `update_personal_event` require `start_time_tz`, and validate it with `domain.timezones.canonical_zone`. An invalid or missing zone raises `InvalidTimezoneError` (a `ValidationError`, so `config/errors.py` maps it to a 422 with the `{code, message, details?}` shape). A floating local time is **refused**, never guessed. | The work item's AC: "refuses a floating or ambiguous local time. An explicit IANA zone is required. The refusal is a domain error that maps to the standard `{code, message, details?}` shape via the single handler in `config/errors.py` — not a raw `ValueError` leaking as a 500." `canonical_zone` is the same check the models design named (item ③'s D7), and `InvalidTimezoneError` already exists in `domain/errors.py` with `code = "invalid_timezone"`. |
| **D38. The start is an instant plus a zone** | The command takes `start_utc` (an aware datetime) and `start_time_tz` (an IANA name). The wall-clock reading is the caller's job — the API layer parses the user's input into an instant and a zone. | AD-6: UTC is the storage truth and the zone is explicit. Storing a naive local time plus a zone would make the row ambiguous at DST boundaries and would put the DST-cap arithmetic (a `domain.timezones` concern) in the command. The command validates the pair: the zone is real, and `end_utc >= start_utc` (the model's `personal_event_end_after_start_ck`, and `domain.errors.InvalidIntervalError` when it is not). |
| **D39. Ownership is checked by `user_id` on every read** | Every command takes `user_id` and scopes every query by it. A row belonging to another user reads as absent, not as forbidden. | `domain.errors.PermissionDeniedError`'s own docstring: "For personal data the caller doesn't own, raise NotFoundError instead (no existence leak)." |
| **D40. `now` is the caller's** | Every command takes `now` explicitly; no command reads the clock. | The `ingestion` convention. |
| **D41. No long work in the request (AD-11)** | Conflict detection is an in-process pure computation over the user's own events, bounded by the ±30-minute / ±24-hour windows and indexed by `(user_id, start_utc)`. It stays in the request. | The work item's AC: "Conflict detection is an in-process pure computation over the user's own events, so it is bounded and fast; if the event count ever makes it unbounded, it moves to a worker task rather than growing inside the request." The indexes (`personal_event_user_start_idx`) make the scan a range query. |
| **D42. `beat_schedule` is untouched** | No change to `config/celery.py` or `worker/tasks.py`. | The work item's AC: "`beat_schedule` is **unchanged** — still exactly one 60s tick. `backend/tests/worker/test_tick.py` passes untouched." |
| **D43. No LLM call** | Nothing in this item imports `adapters.llm` or calls a model. | AD-8's gateway is not involved; the `llm-sdk` import contract keeps it true. |

### The model-layer gaps this item inherits

Two things item ③ deliberately left to the command layer, and this item settles them.

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D44. The `ConflictPair` status machine on `resolve_conflict`** | `resolve_conflict` sets `status = resolved`, `resolution = <value>`, `resolved_at = now` — all three, together. | The model's `conflict_pair_status_ck` requires exactly that shape for a `resolved` pair: resolution NOT NULL **and** resolved_at NOT NULL. Writing only the resolution would fail the check. |
| **D45. The `PersonalEvent.version` increment** | `update_personal_event` increments it; `create_personal_event` leaves it at the model's default of 1. | Item ③'s D9: the model holds a positive-value check; the increment is the command's contract. A new event is version 1, which is what AD-7's send key expects for a first mint. |
| **D46. A conflict whose sides have no id is not written** | `record_detected_conflicts` **skips** a conflict whose `new_side.id` or `other_side.id` is `None`, rather than writing a pair row it cannot fill. The candidate scan applies `.exclude(pk=...)` **only when the candidate has an id**. | A `Candidate` may be detected before its row exists, but a pair names both sides by id and the column is `NOT NULL` — so a conflict found against an unsaved candidate has nothing to point at. Two sub-cases: `pk=None` in an `.exclude()` excludes **nothing**, which would put the candidate's own row back into its own scan and compare it against itself; and the recorder would try to write `right_id = NULL`. The commands call the recorder *after* the row is written, so every recorded conflict has two real ids in practice — the skip is the safety net for a caller that breaks that order. |
| **D47. A moved side's pairs are re-judged by a shared helper** | `conflicts.py` publishes `reconcile_pairs_for_side(*, user_id, kind, side_id, side, now) -> int`: it re-judges the active pairs naming one side and closes the ones that no longer overlap, as `cleared_by_state_change` with a NULL resolution. | A pair is a claim about two events' *current* times, so when one of them moves the claim has to be re-judged — otherwise `/conflicts` would list a clash that is not there. Two call sites need it: a user's edit (`update_personal_event`) and a propagation-driven re-stamp (`update_saved_event_snapshot`). Sharing the helper keeps the two sites from drifting apart. |

## Data Models Affected

### Creates

None. This item writes no new tables.

### Modifies

None. `PersonalEvent`, `SavedEvent`, `ConflictPair` and `PersonalizationAuditEntry` are exactly as
item ③ shipped them. **No migration is needed for this item** — the commands write the rows
item ③ defined, and the `personalization` audit table already exists.

This is worth stating plainly because the item is `validate`: the complexity here is in the
*protocols*, not in the schema. The one schema-adjacent decision — D13, that deleting a personal
event leaves its reminder plan row — is a **gap**, recorded below, not a migration.

## Technical Approach

### Architecture

```
   catalog schema (AD-3 wall — no FK, no join, no shared transaction)
        ▲                                    │
        │ get_public_event()                 │ read the version again
        │ (published read interface,         │ (non-transactional)
        │  plain data: PublicEvent)          │
        │                                    ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  personal schema                                            │
   │                                                            │
   │  ┌────────────────────────────────────────────────────────┐  │
   │  │ transaction.atomic(using=PERSONAL)                     │  │
   │  │                                                        │  │
   │  │   create_personal_event                               │  │
   │  │     ├─ write PersonalEvent (version = 1)              │  │
   │  │     ├─ attach_default_plan(...)  ──► delivery         │  │
   │  │     │     (nested atomic on the same alias =          │  │
   │  │     │      a savepoint; both commit together)        │  │
   │  │     ├─ detect_conflicts(...)  ──► domain.conflict     │  │
   │  │     │     └─ write ConflictPair rows (normalised)    │  │
   │  │     └─ write_audit(...)        ──► Personalization   │  │
   │  │                                  AuditEntry          │  │
   │  │   update_personal_event                                 │  │
   │  │   delete_personal_event                                 │  │
   │  │   save_event / unsave_event                             │  │
   │  │   resolve_conflict                                      │  │
   │  └────────────────────────────────────────────────────────┘  │
   │                                                            │
   │   SavedEvent   ConflictPair   PersonalEvent                │
   └──────────────────────────────────────────────────────────────┘
```

### The six commands

```python
# --- the results, as plain data -------------------------------------------------------------

@dataclass(frozen=True)
class Created:
    """The event was created, with no conflict to answer."""

    event: PersonalEventSnapshot


@dataclass(frozen=True)
class ConflictFound:
    """The event was created, and a conflict prompt is awaiting the user's choice.

    The row exists — the pair references it by id — but the creation flow is *incomplete*
    until one of the three resolutions is recorded (FR-58).
    """

    event: PersonalEventSnapshot
    conflicts: tuple[DetectedConflict, ...]


@dataclass(frozen=True)
class DetectedConflict:
    """One conflict the user must answer."""

    kind: str                 # "time" | "duplicate"
    new_side: ConflictSide    # the event the user just created
    other_side: ConflictSide  # the event it clashes with
    pair_id: UUID             # the ConflictPair row


@dataclass(frozen=True)
class ConflictSide:
    kind: str                 # "personal_event" | "saved_event"
    id: UUID
    name: str
    start_utc: datetime
```

### The transaction boundaries, command by command

| Command | Reads | Writes | Transaction |
|---|---|---|---|
| `create_personal_event` | the user's other events (personal + saved) | `PersonalEvent`, `ReminderPlan` (via `delivery`), `ConflictPair`s, audit | one `personal` transaction (D2) |
| `update_personal_event` | the event, its pairs, the user's other events | `PersonalEvent` (version +1), `ConflictPair`s, audit | one `personal` transaction |
| `delete_personal_event` | the event, its pairs | `PersonalEvent` (deleted), `ConflictPair`s (closed), audit | one `personal` transaction |
| `save_event` | the catalog event (non-transactional), the user's events | `SavedEvent`, `ConflictPair`s, audit | one `personal` transaction around the write only (D27) |
| `unsave_event` | the save, its pairs | `SavedEvent` (deleted), `ConflictPair`s (closed), audit | one `personal` transaction |
| `resolve_conflict` | the pair, the new side | `ConflictPair` (resolution), the new side (deleted, for `delete_new`), audit | one `personal` transaction |

Every one of them opens `transaction.atomic(using=PERSONAL)` and writes its audit row **inside**
it.

### The save-race, in sequence

```
  t0   ┌─ transaction.atomic(using=PERSONAL) ────────────────┐
       │  read catalog_event.version   (inside the tx, but  │
       │    on the catalog alias — not part of it)         │
       │  write SavedEvent(start_utc, end_utc, version)    │
       │  write ConflictPair rows                          │
       │  write_audit                                      │
  t1   └─ commit ───────────────────────────────────────────┘
  t2   read catalog_event.version          ── non-transactional (D27 step 3)
  t3   if t2.version > t0.version:  → the snapshot is stale
       → return SaveResult(stale=True, current_version=t2.version)
       → the caller requests re-propagation for this user (D30)
```

A postponement that commits between **t0 and t1** is caught by the t2 re-read. A postponement
that commits *after* t2 is not this save's problem: the propagation job's own version check
(D34) handles it. The window the protocol closes is exactly the one AD-21 names.

### The forced-choice state machine

```
   create_personal_event
        │
        ├── no conflict ────────────────────────────────► Created
        │
        └── conflict found
                 │
                 │  the event row EXISTS
                 │  the pair is ACTIVE  (the pair *is* the pending prompt)
                 ▼
        ConflictFound
                 │
                 ├── resolve_conflict(keep_both)
                 │      → pair: status=resolved, resolution=keep_both, resolved_at=now
                 │      → the indicator persists; the pair is never re-prompted
                 │
                 ├── resolve_conflict(edit_new)
                 │      → the pair records status=resolved, resolution=edit_new
                 │      → the caller opens the new event in edit mode
                 │      → update_personal_event re-runs detection; the pair is already
                 │        closed, so it is never re-prompted (D20)
                 │
                 └── resolve_conflict(delete_new)
                        → the pair records status=resolved, resolution=delete_new
                        → the new event is deleted (through delete_personal_event)
```

`resolve_conflict` records the resolution on the pair **before** the action it names, so the
audit trail shows what the user chose even if the follow-up edit lands later. A pair that is
already closed cannot be resolved again (D24).

**Why a cleared pair is never the answer.** The model's `conflict_pair_status_ck` makes a
`cleared_by_state_change` pair carry a NULL resolution, so "the user answered" and "nobody
answered" are the only two shapes a closed pair can have. That is the whole point of the
status: a pair closed because the user deleted an unrelated event is *not* the same fact as a
pair the user answered with "keep both", and the database refuses to let one masquerade as
the other.

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/apps/personalization/services/audit.py` | Create | The `personal` audit writer, mirroring `ingestion`'s |
| `backend/apps/personalization/services/conflicts.py` | Create | Conflict detection: candidate gathering, the `domain.conflict` call, side normalisation |
| `backend/apps/personalization/services/personal_events.py` | Create | `create_personal_event`, `update_personal_event`, `delete_personal_event` |
| `backend/apps/personalization/services/saved_events.py` | Create | `save_event`, `unsave_event`, `update_saved_event_snapshot` |
| `backend/apps/personalization/services/conflict_resolutions.py` | Create | `resolve_conflict` and the forced-choice transitions |
| `backend/shared/constants.py` | Modify | `CONFLICT_SCAN_WINDOW` (±30 minutes), and the audit action slugs if they are wanted in one place |
| `backend/tests/personalization/factories.py` | Create | Factories for the three tables |
| `backend/tests/personalization/test_personal_events.py` | Create | The create / update / delete commands |
| `backend/tests/personalization/test_saved_events.py` | Create | The save / unsave commands and the race protocol |
| `backend/tests/personalization/test_conflicts.py` | Create | Detection, normalisation, the forced-choice machine |
| `backend/tests/personalization/test_audit.py` | Create | The audit writer's guard |
| `backend/tests/personalization/test_ownership.py` | Create | The AD-16 boundary: no import of `apps.delivery.models` or `apps.ingestion.models` |

### Constants

| Constant | Value | Where |
|---|---|---|
| `CONFLICT_SCAN_WINDOW` | `timedelta(minutes=30)` | `shared/constants.py` — the FR-58 ±30-minute candidate scan |
| `CONFLICT_MIN_OVERLAP` | `timedelta(minutes=15)` | already in `shared/constants.py` — the AD-21 overlap threshold, used by `domain.conflict` |
| `DUPLICATE_START_WINDOW` | `timedelta(hours=24)` | already in `shared/constants.py` — the FR-58 duplicate window |
| `TITLE_TOKEN_OVERLAP_MIN` | `Fraction(4, 5)` | already in `shared/constants.py` — the ≥80% token overlap |

The ±30-minute window is the only new constant. It is a *service*-layer concern (which events
to compare), which is why item ③'s design said it "lands in work item ⑤ as a constant there" —
and `shared/constants.py` is where it lands, beside the thresholds it works with.

## Security Considerations

- **No personal data crosses into `catalog`.** Every write this item performs is in `personal`.
  The only cross-schema movement is a *read* of a public catalog event through `ingestion`'s
  published interface, and only its time fields and version are copied — the user's own event
  names, locations and notes never travel outward.
- **The actor is stored by value.** `shared.actor.Actor` carries a UUID for a user and a job
  name for a system; the `actor_check()` constraint on the audit table enforces that a user
  actor has no label, so no username or email can reach an audit row.
- **Ownership is by `user_id` on every read.** A command scoped to one user cannot read or
  mutate another user's rows, and a row the caller does not own reads as absent — so the API
  cannot be used to probe for the existence of another user's event id.
- **The audit row is in the mutation's transaction.** `write_audit` raises rather than writing
  an orphaned row, so an audit trail can never claim a change that rolled back.
- **No LLM call, no model call.** The duplicate rule is a Jaccard overlap on normalised
  tokens — structural, not semantic. Nothing in this item reaches a model provider.
- **The `personal` role never touches `catalog`.** `ep_personal` has no `USAGE` on the
  `catalog` schema, so a cross-schema query would fail at the database, not merely be
  discouraged by convention.

## Integration Points

| System | Type | Purpose |
|--------|------|---------|
| `delivery` | Call | `attach_default_plan` attaches FR-20's default plan when a personal event is created (AD-16) |
| `ingestion` | Read | `catalog_read.get_public_event` supplies the snapshot for a save (AD-21) |
| `domain.conflict` | Pure call | `conflicts` and `is_duplicate` — the one overlap function, called on write only |
| `domain.timezones` | Pure call | `canonical_zone` validates the IANA zone the user meant |
| `domain.errors` | Raised | `InvalidTimezoneError`, `InvalidIntervalError`, `ValidationError` — all mapped by `config/errors.py` |
| `shared.actor` | Value | The explicit `Actor` every command takes |
| `shared.db` | Alias | `PERSONAL` — every query and every `transaction.atomic` |
| AD-17 propagation | Later intent | Calls `update_saved_event_snapshot` (D34) and re-runs detection |
| `apps/personalization.api` | Later intent | Turns the command results into the three-action prompt and the endpoints |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| The `personalization` → `delivery` call nests two `transaction.atomic(using=PERSONAL)` blocks. If the outer one is not on the same alias, the inner one opens a *second* connection and the "one transaction" claim is false. | High — a plan could commit apart from its event, so FR-20's default would be only eventually true, and the audit rows could disagree with the data. | Every command opens `transaction.atomic(using=PERSONAL)` and `delivery`'s service opens `transaction.atomic(using=PERSONAL)` — the same alias. Django's nested `atomic` on one alias is a savepoint, so the inner block cannot commit on its own. A test asserts that a failure inside `attach_default_plan` rolls the **event** back too, which is the observable proof. |
| A conflict is detected, the event row is written, and the user abandons the flow. The row exists with an `active` pair and no resolution. | Medium — the `/conflicts` list shows a pair the user never answered, and the event exists in the Timeline with no plan decision recorded. | This is D21's deliberate trade-off, and it is the one the PRD forces: the pair *is* the pending prompt, and `/conflicts` is the place a user reviews exactly these pairs ("Lists all conflict pairs the system has recorded (active + resolved)"). The alternative — writing no row — leaves a pair referencing an id that does not exist. A later sweep could clear abandoned pairs, but that is a product decision beyond this item. |
| The save-race window is widened by the transaction's duration. | Medium — a postponement committing during the transaction leaves a stale snapshot until propagation. | D28 reads the version *inside* the transaction, immediately before the write, narrowing the window to the write itself. D29 detects the residual case after the commit and reports it. The propagation job's own version check (D34) is the backstop. |
| The propagation job does not exist yet, so a stale snapshot is detected but never fixed. | Medium — a saved event could show a stale time on the Timeline until the job lands. | The staleness is *reported* (D31: the return value and the audit details) rather than silently accepted, so the gap is visible rather than invisible. The fixing service (`update_saved_event_snapshot`, D34) lands now and is tested, so the job is a thin caller when it arrives. |
| Conflict detection scans the user's events on every write. A user with many events could make the request slow. | Medium — AD-11 forbids long work in a request. | The scan is bounded by the ±30-minute / ±24-hour windows and reads through `personal_event_user_start_idx` (`user_id`, `start_utc`), so it is a range query, not a full scan. The work item's AC accepts this and names the escape hatch (a worker task) if the count ever makes it unbounded. |
| The candidate set includes the event being created, so an event conflicts with itself. | Low — a spurious pair with itself, or a self-conflict prompt. | The detection is always given an explicit `exclude_id` for the candidate, and the model's `conflict_pair_sides_differ_ck` would reject a self-pair at the database anyway. The command filters first so the user never sees it. |
| A resolved pair is re-opened by a later detection, hitting the `guard_conflict_pair` trigger's `RestrictViolation` as a raw database error. | Medium — a 500 instead of a calm response. | D20 checks the pair's status *before* writing and skips a closed pair. The command never attempts the write, so the trigger is a backstop rather than the primary guard. |
| A deletion leaves an orphan `ReminderPlan` row, because `personalization` may not delete it. | Low — an inert row in `delivery`'s table that no surface reads. | D13. `delivery` owns the plan and its deletion; adding a `remove_plan` command to `delivery` is `delivery`'s call, not this item's. The gap is recorded, and `delivery`'s `set_plan_slots(slots=())` already expresses "this event has no reminders" if the row's presence ever mattered. |
| The ±30-minute scan window is a second number next to the 15-minute overlap threshold, and the two could be confused. | Medium — a reader (or a later edit) could treat the window as the threshold. | They are different quantities and are named differently: `CONFLICT_SCAN_WINDOW` (which events to look at) and `CONFLICT_MIN_OVERLAP` (when two of them clash). The domain function owns the threshold and the service owns the window, and each has a comment saying so. |

## Implementation Checklist

1. `shared/constants.py`: add `CONFLICT_SCAN_WINDOW` with a comment distinguishing it from
   `CONFLICT_MIN_OVERLAP` (D16).
2. `apps/personalization/services/audit.py`: the `personal` audit writer, mirroring
   `apps/ingestion/services/audit.py` (D7).
3. `apps/personalization/services/conflicts.py`:
   - `ConflictSide` and `DetectedConflict` dataclasses (plain data)
   - the candidate query, bounded by the windows and the `(user_id, start_utc)` index
   - `detect_conflicts(*, user_id, candidate, exclude_id, now)` calling
     `domain.conflict.conflicts` and `domain.conflict.is_duplicate` (D15, D16, D17)
   - the side normalisation, lexicographic on `(kind, id)` (D18)
   - `record_detected_conflicts(...)`: `update_or_create` for `active` pairs, skip for closed
     ones (D20)
4. `apps/personalization/services/personal_events.py`:
   - `create_personal_event`: validate the zone (D37), validate the interval (D38), write the
     event, **call `delivery`'s `attach_default_plan` inside the same transaction** (D1, D2),
     detect conflicts, write the pairs, write the audit rows, return `Created` or
     `ConflictFound` (D21)
   - `update_personal_event`: validate, bump `version` with `F()` (D9), re-run detection,
     close pairs that no longer overlap (D10), write the audit row
   - `delete_personal_event`: delete the row, close the pairs as `cleared_by_state_change`
     (D11), write the audit row
5. `apps/personalization/services/saved_events.py`:
   - `save_event`: the AD-21 protocol exactly as in the sequence diagram (D27–D31), the
     idempotent upsert (D32), conflict detection on save, the audit row
   - `unsave_event`: remove the row, close the pairs (D33)
   - `update_saved_event_snapshot`: the "only if greater" rule, re-evaluate the conflicts
     (D34)
6. `apps/personalization/services/conflict_resolutions.py`:
   - `resolve_conflict`: validate the resolution against the kind (D23), refuse a closed pair
     (D24), record the resolution (D44), act on `delete_new` through
     `delete_personal_event` (D25), write the audit row
7. `tests/personalization/factories.py`: factories for the three tables.
8. `tests/personalization/test_personal_events.py`: create with an explicit zone; create
   refused without one (and the error's shape); create attaching the default plan through
   `delivery`'s service; create producing a conflict that blocks completion; each of the three
   resolutions; edit re-running detection; edit bumping the version; delete closing the pairs.
9. `tests/personalization/test_saved_events.py`: save writing a correct snapshot; save racing
   a postponement (the stale snapshot is reported); double-save idempotency; unsave closing the
   pairs; the propagation-shaped snapshot update refusing an older version.
10. `tests/personalization/test_conflicts.py`: detection of a time conflict; detection of a
    duplicate; the side normalisation (one row for `(A,B)` and `(B,A)`); a resolved pair is
    never re-prompted; an illegal resolution/kind pairing is refused.
11. `tests/personalization/test_audit.py`: the writer inside a transaction; the guard when none
    is open.
12. `tests/personalization/test_ownership.py`: the structural proof that
    `apps/personalization/services/` imports neither `apps.delivery.models` nor
    `apps.ingestion.models`, and that the import contracts still hold.
13. Run `manage.py check` (E001–E005), `make lint-imports` (13 contracts), `ruff check`,
    `ruff format --check`, the full backend suite and the coverage gate (`domain/` 100%,
    overall ≥80%).
14. Append the item's section to `plan.md`, `test-report.md` and `review-report.md`.

## Known Gaps

These are deliberate, and each is named here rather than left to be discovered.

- **A deleted personal event leaves its reminder plan row behind.** `personalization` may not
  write `REMINDER_PLAN` (D13), and `delivery` has no "remove the plan" command yet. The row is
  inert. Adding `delivery`'s command is the fix, and it belongs to `delivery`.
- **The propagation job does not exist.** `worker.tasks.propagate_state_change` is an explicit
  placeholder. This item publishes the services the job will call (`update_saved_event_snapshot`)
  and reports staleness; it does not fix a stale snapshot, because fixing it is the job's job.
- **No API, no frontend.** The three-action prompt is returned as data (`ConflictFound`); the
  sheet that renders it is item ⑧, and the endpoints are items ⑥ and ⑦.
- **The `/conflicts` read query does not exist.** It is a read, and it belongs to item ⑥.
- **`update_existing` does not edit the existing event.** The resolution is *recorded*; opening
  the existing event in edit mode is the API layer's action, exactly as `edit_new` returns the
  event to edit rather than editing it.
- **Public-vs-public conflicts are out of scope** (FR-33: "Public-event vs. public-event
  conflicts (Phase 3)"), so detection never compares two saved events with each other.

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-10-29*
