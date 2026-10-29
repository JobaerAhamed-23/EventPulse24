---
id: personalization-models
title: Personalization Models (PersonalEvent, SavedEvent, ConflictPair)
intent: personal-events-and-saved-catalog
complexity: high
mode: validate
status: completed
depends_on:
  - repo-hygiene-cleanup
created: 2026-10-29
run_id: run-eventpulse24-019
completed_at: 2026-10-29T03:03:09.953Z
---

# Work Item: Personalization Models (PersonalEvent, SavedEvent, ConflictPair)

## Description

Creates the three entities that AD-16 assigns to `personalization`, plus its audit table, in the `personal` schema:

- **`PERSONAL_EVENT`** — a user-created event (FR-18).
- **`SAVED_EVENT`** — a user's save of a public catalog event, holding a propagated time snapshot (AD-21).
- **`CONFLICT_PAIR`** — one persisted conflict between two of a user's events, with the user's resolution recorded on it (AD-21, FR-58).
- **`PERSONALIZATION_AUDIT_ENTRY`** — the concrete audit table for AD-5.

`apps/personalization/models.py` is currently empty. This work item makes `personal` a real schema and establishes the write-ownership contract that the Pulse Digest, Timeline and `/conflicts` will all build on.

The two decisions that need settling carefully are the **`SAVED_EVENT` snapshot semantics** (what exactly is stored, when it is refreshed, and what happens when `catalog` moves underneath it) and the **`CONFLICT_PAIR` lifecycle** (how a pair is created, how a resolution makes it immutable, and how a cleared pair differs from a resolved one).

**Mode: validate.** This work item gets a design doc and two checkpoints before implementation.

## Acceptance Criteria

- [ ] **A design doc exists** at `.specs-fire/intents/personal-events-and-saved-catalog/work-items/personalization-models-design.md`, covering at minimum: the `SAVED_EVENT` snapshot semantics and refresh triggers, the `CONFLICT_PAIR` state machine, the `PERSONAL_EVENT` timezone representation, the audit table shape, and the retention category per table.
- [ ] The design doc is **reviewed and approved** before implementation begins (Checkpoint 1).
- [ ] `PERSONAL_EVENT` stores: name, `start_utc` (UTC `timestamptz`), `end_utc` (nullable), `start_time_tz` (IANA zone name), location (nullable), notes (nullable), `source = user_created`, and a `version`/timestamp for optimistic ordering. The start time **requires** an explicit IANA timezone; a floating or ambiguous local time is refused at the model/service boundary.
- [ ] `SAVED_EVENT` holds `event_id` **by value** — a `UUIDField`, **not** a foreign key. It also holds the snapshot: `start_utc`, `end_utc` and `event_version`. There is **no** `ForeignKey` to `catalog` from any `personal` model, and no cross-schema join exists anywhere (AD-3).
- [ ] `SAVED_EVENT` is unique per `(user, event_id)`. Saving the same event twice is one row, not two.
- [ ] `CONFLICT_PAIR` links two sides, each of which is a reference to either a `PERSONAL_EVENT` or a `SAVED_EVENT`. It carries a status (`active` / `resolved` / `cleared_by_state_change`) and the `ConflictResolution` value.
- [ ] A **resolved** `CONFLICT_PAIR` is **immutable**: it is never re-prompted, and its resolution is never rewritten. A pair closed because a catalog state change removed the overlap is distinguishable from a pair the user resolved — AD-21 calls the former `cleared_by_state_change`, "which is not a user resolution".
- [ ] The `ConflictResolution` value object covers exactly the PRD's cases: `keep_both`, `edit_new`, `delete_new` for a time conflict, and `keep_both`, `update_existing`, `delete_new` for a duplicate. There is **no** `dismiss` value.
- [ ] Every model declares a retention category. `PERSONAL_EVENT`, `SAVED_EVENT` and `CONFLICT_PAIR` use `RetentionCategory.ACCOUNT_CONTENT` — that category already exists in `shared/retention.py` and its docstring names exactly these two record types. The audit table uses `RetentionCategory.AUDIT_LOG`.
- [ ] No `personal` model FKs to `User` or `ContentType` (spine OQ-8). The user is referenced by `UUID` value, matching the `ActorColumns` pattern. The catalog-side precedent is `apps/ingestion/models.py`.
- [ ] The audit table extends `shared.models.AuditEntry` (the same pattern `ingestion` uses), so the actor is stored by value via `ActorColumns` and `actor_check()` is applied.
- [ ] The `import-linter` contract `models-personalization` (already declared: only `apps.personalization` may import `apps.personalization.models`) keeps passing. `make lint-imports` is green.
- [ ] The `domain-pure` contract still passes; no model module imports `domain` in a way that would pull Django into the domain layer.
- [ ] Migrations apply cleanly on the local stack, and the tables land in the **`personal`** schema — verified by inspecting `information_schema`, not by assuming the router did the right thing.
- [ ] The `personal` schema tables carry the AD-3 separation: no foreign key constraint crosses from `personal` to `catalog`. This is asserted by a test, mirroring the existing cross-schema FK refusal test from `project-scaffold`.
- [ ] A model test asserts `SAVED_EVENT.event_id` is a plain `UUIDField` and that no `ForeignKey` exists on any of the three models. This is a **structural** test, so a future "helpful" FK breaks the build.

## Technical Notes

Follow the conventions `apps/ingestion/models.py` establishes — it is the reference implementation:

- `UUIDv7Model` as the base, so the id is minted in Python and known before `save()`.
- Explicit `using=PERSONAL` on every query. `shared/db.py` defines `PERSONAL = "default"` and `CATALOG = "catalog"`; the router handles the alias, but the codebase convention is to pass it explicitly rather than rely on `default`.
- `retention_category` as a field on every model (the scaffold's `manage.py check` fails when a model holding user data declares no retention category — AD-15).
- `related_name` set on every `ForeignKey` (Django's system check `models.W342` fires otherwise, and `manage.py check` runs in CI).

For `PERSONAL_EVENT.start_time_tz`, use the IANA zone name as a `CharField` and validate it against `zoneinfo.available_timezones()`. The `tzdata` package is pinned deliberately (`tzdata` 2026.5, IANA 2026e) and `config.apps.ConfigConfig.ready()` calls `zoneinfo.reset_tzpath(to=())`, so dev, CI and production always compute the same instants. Do not read the OS timezone database.

The `SAVED_EVENT` snapshot and AD-17 propagation are tightly coupled even though propagation itself is not in this intent. AD-17 says the propagation job calls `personalization`'s published service to update the `SAVED_EVENT` snapshot and re-evaluate `CONFLICT_PAIR`s, keyed `(state_change_id, user_id)`, and only when the change's `event_version` is greater than the version already stored. Design the model so that update path exists — a `version` field that only ever increases, and a lookup that can find every `SAVED_EVENT` for a given `event_id` — even though the propagation job that calls it lands later.

AD-21 also requires that "a save re-reads the Event's version after commit and requests re-propagation for that user if it moved meanwhile, so a save racing a postponement cannot keep a stale snapshot." The *model* must support this; the *save command* implementing it is the next work item.

## Dependencies

- repo-hygiene-cleanup
