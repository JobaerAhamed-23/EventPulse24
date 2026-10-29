---
work_item: personalization-models
intent: personal-events-and-saved-catalog
created: 2026-10-29
mode: validate
checkpoint_1: approved
---

# Design: Personalization Models (PersonalEvent, SavedEvent, ConflictPair)

## Summary

This item creates the `personalization`-owned tables in the `personal` schema — the three
entities AD-16 assigns to `personalization`, plus their audit table:

- `PersonalEvent` — a user's own event (FR-18).
- `SavedEvent` — a user's save of a public catalog event, holding the propagated time
  snapshot (AD-21).
- `ConflictPair` — one persisted conflict between two of a user's events (AD-21, FR-58).
- `PersonalizationAuditEntry` — the concrete audit table for AD-5.

`apps/personalization/models.py` is currently empty, so `personal` has no product tables of
its own yet. This item makes the schema real and establishes the write-ownership contract
that the Pulse Digest, the Timeline and `/conflicts` all build on.

The two decisions that need settling carefully are the **`SavedEvent` snapshot semantics**
(what exactly is stored, when it is refreshed, and what happens when `catalog` moves
underneath it) and the **`ConflictPair` lifecycle** (how a pair is created, how a resolution
makes it immutable, and how a cleared pair differs from a resolved one).

Everything here is structural. The schema makes the invariants the database can hold
constraints; what it can't — IANA zone validity, conflict arithmetic, the save-race
protocol — is left as an obvious seam for the command layer (work item ⑤).

## Scope

**In Scope:**
- Four concrete models in `apps/personalization/models.py`
- The `ConflictResolution` value object and its `ConflictKind`
- Migration `personalization/0001_initial` — tables, constraints, indexes, and the
  runtime-role grants for the audit table
- The `ConflictPair` state machine as database check constraints, plus the append-only
  guard on a resolved pair
- Model, constraint, structural and schema-placement tests
- New constants in `shared/constants.py` where a threshold or a window is needed

**Out of Scope:**
- Every command and query (`personalization-write-services`) — this item writes no service
- The API (`personal-events-api`, `saved-events-api`)
- The frontend surfaces (`frontend-personal-and-conflict-surfaces`)
- AD-17 propagation itself — the propagation job lands in a later intent; this item makes
  the *model* able to receive it
- `ReminderPlan` — `delivery` owns it (AD-16), and it is work item ④
- `CalendarConnection`, `PulseDigest`, `DigestComposition`, `EventReport`,
  `Interest`, `PreferenceGraph` — other `personalization` entities, not this item
- The audit *write path* (`write_audit` for `personalization`) — that is work item ⑤,
  because it needs the same-transaction rule the commands have

## Key Decisions

### Placement and identity

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D1. Home** | All four tables live in `apps/personalization/models.py`. `apps.personalization` is already routed to `PERSONAL` in `settings.DATABASE_ROUTING`, so no routing change is needed. | AD-16 gives `PERSONAL_EVENT`, `SAVED_EVENT` and `CONFLICT_PAIR` to `personalization`. The app is already in the `personal` set, so `eventpulse.E001` stays green with no settings edit. |
| **D2. The user is a value, never a relation** | Every model stores `user_id` as a plain `UUIDField`. There is **no** `ForeignKey` to `User` on any model, and no `GenericForeignKey`. | Spine OQ-8 and the work item's AC: personal models never relate to `User` or `ContentType`. `User` lives in the `personal` schema, so a FK would technically pass E002 — but the pattern is forbidden regardless, because `User` is `identity`-owned and `personalization` must not depend on it. `shared.models.ActorColumns` stores the actor the same way. |
| **D3. Base class** | `PersonalEvent`, `SavedEvent` and `ConflictPair` subclass `shared.models.UUIDv7Model`. `PersonalizationAuditEntry` subclasses `shared.models.AuditEntry` (which already subclasses `UUIDv7Model`). | `eventpulse.E005` requires `UUIDv7Model` on every project model. The audit table follows the `ingestion` precedent exactly (`IngestionAuditEntry(AuditEntry)`). |
| **D4. Retention** | `ACCOUNT_CONTENT` for `PersonalEvent`, `SavedEvent` and `ConflictPair`. `AUDIT_LOG` for `PersonalizationAuditEntry`. | `RetentionCategory.ACCOUNT_CONTENT`'s docstring names exactly "Personal events + saved events". `ConflictPair` is the same kind of record — it exists only to serve the user's own events, is purged with them, and holds no user-derived data beyond what they already hold. `AUDIT_LOG` is the category `ingestion` uses for its audit table. |

### `PersonalEvent` — the user's own event

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D5. Fields** | `name`, `start_utc` (NOT NULL, `timestamptz`), `end_utc` (NULL), `start_time_tz` (IANA name, NOT NULL), `location` (NULL), `notes` (NULL), `source` (`user_created`), `version` (positive int, default 1), `created_at`, `updated_at`. | FR-18 names exactly these: name, start time, location, optional end time, optional notes, optional Reminder Plan. AD-6 makes UTC the storage truth and requires the timezone to be explicit, so `start_utc` is the instant and `start_time_tz` is the zone the user meant. The Reminder Plan is **not** a field here — AD-16 gives `REMINDER_PLAN` to `delivery` (work item ④), and `personalization` attaches it by calling `delivery`'s published service. |
| **D6. `source`** | A `TextChoices` with one member, `USER_CREATED = "user_created"`, defaulting to it. Not a free `CharField`. | FR-18 states a Personal Event is saved "with `source = user_created`". AD-18's calendar import will later produce events from a `CALENDAR_CONNECTION` (FR-50), so the column must be extensible — but only to values this app defines. A `TextChoices` makes an accidental third value impossible without editing this file. |
| **D7. Timezone validation** | `start_time_tz` is a `CharField(max_length=64)` validated against `zoneinfo.available_timezones()` **in the command layer**, not by a database check. | A database check cannot see the tz database, so an IANA check there would be a lie. The work item's AC says the refusal happens "at the model/service boundary" — this item provides the seam (`domain.timezones.canonical_zone` already does exactly this check) and the command uses it in work item ⑤. `config/apps.py` calls `zoneinfo.reset_tzpath(to=())`, so the pinned `tzdata` package is the only source, in every environment. |
| **D8. Interval validity** | `CheckConstraint`: `end_utc IS NULL OR end_utc >= start_utc`, named `personal_event_end_after_start_ck`. | The catalog's `Event` carries the same check (`event_end_after_start_ck`). `domain.conflict._interval_end` raises `InvalidIntervalError` for the same condition, so the database and the domain agree. A NULL end is legal and means open-ended. |
| **D9. Version** | `version: PositiveIntegerField(default=1)`, with `CheckConstraint(version__gte=1)`. The application increments it on every mutation. | The work item's AC asks for "a `version`/timestamp for optimistic ordering". AD-17's send key uses `personal_event_revision`, so a monotonic per-event version is needed anyway. Unlike the catalog's `Event`, this item does **not** add a trigger enforcing the increment — the write path is work item ⑤, and a trigger that guesses the caller's intent is worse than none. The check keeps the value positive; monotonicity is the command's contract. |
| **D10. Lookup index** | `Index(fields=["user_id", "start_utc"])`, named `personal_event_user_start_idx`. | The Timeline (FR-32) reads "one week in the user's timezone", and the Pulse Digest (FR-19) reads "within the next 48 hours". Both are `user_id` + `start_utc` range scans. |
| **D11. Delete behaviour** | Plain `models.Model` — no `PROTECT`, no append-only guard. A user may delete a Personal Event (FR-18). | The catalog's `PROTECT` chain exists because Events are never deleted (only superseded). Personal Events are the user's own records and FR-18 explicitly says "A user can edit or delete a Personal Event". `ConflictPair` rows referencing a deleted event are handled by the command layer (item ⑤), not by a `PROTECT` that would block the deletion. |

### `SavedEvent` — the save and its snapshot

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D12. `event_id` by value** | `event_id = models.UUIDField()` — a **plain** `UUIDField`, not a `ForeignKey`. There is no relation to `catalog` on any model in this app. | AD-21: "It holds `event_id` by value (no FK)". The `models-personalization` import-linter contract and `eventpulse.E002` both make a cross-schema relation impossible to express; this makes it impossible to *want*. A structural test asserts the field's type so a future "helpful" FK breaks the build. |
| **D13. The snapshot** | `start_utc` (NOT NULL), `end_utc` (NULL), `event_version` (positive int, NOT NULL) — the values read from `catalog` at save time. Plus `saved_at`, `created_at`, `updated_at`. | AD-21 names exactly these three. The Timeline and conflict detection read the snapshot and never join `catalog` (D12). `event_version` is what makes propagation idempotent: AD-17 applies a change only if the incoming `event_version` is **greater** than the stored one. |
| **D14. Uniqueness** | `UniqueConstraint(fields=["user_id", "event_id"], name="saved_event_user_event_uq")`. | The work item's AC: "Saving the same event twice is one row, not two." The constraint is the whole guarantee; the command layer then upserts. |
| **D15. Propagation lookup** | `Index(fields=["event_id"])`, named `saved_event_event_idx`. | AD-17 propagation must find *every* `SAVED_EVENT` for a given `event_id` (across all users) to re-stamp the snapshot. Without this index that lookup is a sequential scan of the user's saves. |
| **D16. No FK to `PersonalEvent`** | A `SAVED_EVENT` and a `PERSONAL_EVENT` are **different kinds of thing** and are never linked to each other. | A saved public event and a user's own event are independent records. Linking them would imply an ownership relation that does not exist and would block deletion of a personal event that happens to share a time slot with a saved one. |

### `ConflictPair` — the persisted conflict

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D17. Two typed sides** | Each side is a pair of columns: `left_kind` / `left_id` and `right_kind` / `right_id`, where `kind ∈ {personal_event, saved_event}` and `id` is a `UUIDField`. **No foreign keys** — the ids refer to `PersonalEvent.id` or `SavedEvent.id` by value. | AD-21: "linking two sides (each a `SAVED_EVENT` or a `PERSONAL_EVENT`)". A polymorphic FK (`GenericForeignKey`) is forbidden by OQ-8 and would need a `ContentType` relation. Storing `(kind, id)` by value keeps the row self-contained and makes the side's type explicit. |
| **D18. Side kinds** | `ConflictSideKind(TextChoices)`: `PERSONAL_EVENT = "personal_event"`, `SAVED_EVENT = "saved_event"`. | A single `kind` column per side is enough; the `id` namespace is UUIDv7 in both tables and is not distinguishable by inspection, so the kind must be stored. |
| **D19. Status** | `status ∈ {active, resolved, cleared_by_state_change}`, stored as a `TextChoices` on the model. | AD-21 names these three exactly. `cleared_by_state_change` is "not a user resolution" — it is the case where propagation removed the overlap (a cancel, or a postpone past the partner). |
| **D20. The resolution** | `resolution` is a **nullable** `CharField` holding a `ConflictResolution` value, plus `resolved_at` (nullable `DateTimeField`). | The PRD's `ConflictResolution` is "a user decision on a conflict prompt". A pair closed by a state change has **no** user decision, so the column is NULL there — that is exactly what makes a cleared pair distinguishable from a resolved one. `resolved_at` is set only for a user resolution. |
| **D21. `ConflictResolution` — where it lives** | A `TextChoices` on `ConflictPair`, with the PRD's exact values: `KEEP_BOTH = "keep_both"`, `EDIT_NEW = "edit_new"`, `DELETE_NEW = "delete_new"`, `UPDATE_EXISTING = "update_existing"`. **There is no `dismiss` value.** | PRD §3: "recorded as one of: `keep_both`, `edit_new`, `delete_new` (Personal-vs-Personal time conflict); or `keep_both`, `update_existing`, `delete_new` (Personal-vs-Personal duplicate). There is no `dismiss` resolution — the user must make an explicit choice." All four values live in one `TextChoices` so the vocabulary cannot drift; the *pairing* rule (which three are legal for a given conflict kind) is enforced by the command layer in item ⑤. |
| **D22. Conflict kind** | A `kind` column, `ConflictKind(TextChoices)`: `TIME = "time"`, `DUPLICATE = "duplicate"`. | FR-58's two prompts are different: a time conflict offers "Edit the new one"; a duplicate offers "Update the existing one". The prompt's button set is derived from the kind, so the kind must be persisted with the pair. The kind is *not* derivable from the sides — a personal event can conflict with a saved event by time or be a duplicate of it by name. |
| **D23. Uniqueness** | `UniqueConstraint(fields=["user_id", "left_kind", "left_id", "right_kind", "right_id"], name="conflict_pair_pair_uq")`, with the sides **normalised** so `(A,B)` and `(B,A)` are the same row. | The same pair must not be detected twice. The ordering is normalised at write time by the command layer (lexicographic on `(kind, id)`), which is the only way to make a composite unique constraint symmetric. |
| **D24. Immutability of a resolved pair** | A database trigger raises when a row's `status` leaves `resolved` or `cleared_by_state_change`, or when a non-null `resolution`/`resolved_at` changes. A resolved pair is never re-prompted and its resolution is never rewritten. | AD-21: "A resolved pair is immutable and never re-prompted." The catalog's `guard_event_write` trigger is the precedent for putting this guarantee in the database rather than trusting every caller. A Python-level guard alone would not stop a raw SQL write. |
| **D25. Status consistency** | One `CheckConstraint` (`conflict_pair_status_ck`):<br>• `active`: `resolution IS NULL AND resolved_at IS NULL`<br>• `resolved`: `resolution IS NOT NULL AND resolved_at IS NOT NULL`<br>• `cleared_by_state_change`: `resolution IS NULL AND resolved_at IS NOT NULL` | The three states are mutually exclusive and collectively exhaustive. A pair can be closed by a state change *and* carry a resolution only if it was first resolved — and then it would be `resolved`, not cleared. The check makes "resolved but with no resolution value" impossible. |
| **D26. The sides differ** | `CheckConstraint`: the two sides may not be the same `(kind, id)`. | A conflict is between two distinct events. A pair whose sides are equal is a programming error, and the unique constraint would not catch it. |

### The audit table

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D27. Shape** | `PersonalizationAuditEntry(AuditEntry)` with `retention_category = RetentionCategory.AUDIT_LOG`. The abstract base gives it `at`, `action`, `target_type`, `target_id`, `details`, and the `actor_kind` / `actor_id` / `actor_label` columns, plus `actor_check()`. | The work item's AC: "The audit table extends `shared.models.AuditEntry` (the same pattern `ingestion` uses), so the actor is stored by value via `ActorColumns` and `actor_check()` is applied." The abstract base already carries the check constraint in its `Meta`. |
| **D28. Append-only** | The concrete table is append-only, exactly like `IngestionAuditEntry`: the migration adds the `forbid_history_mutation` trigger and the column-level grants. | AD-5: audit rows are never rewritten. `catalog.forbid_history_mutation` is a `catalog`-schema function; the `personal` schema needs its own, because the runtime role has no access to the `catalog` schema. The migration creates `personal.forbid_history_mutation` and the `personal.ep_personal` grants. |

## Data Models Affected

### Creates

- **`PersonalEvent`** — `user_id` (UUID, by value), `name` (varchar 200), `start_utc`
  (timestamptz, NOT NULL), `end_utc` (timestamptz, NULL), `start_time_tz` (varchar 64,
  IANA name), `location` (varchar 300, NULL), `notes` (text, NULL), `source`
  (`user_created`), `version` (positive int, default 1), `created_at`, `updated_at`.
  Check: `end_utc IS NULL OR end_utc >= start_utc`; `version >= 1`.
  Index: `(user_id, start_utc)`.
  Retention: `ACCOUNT_CONTENT`.

- **`SavedEvent`** — `user_id` (UUID, by value), `event_id` (**plain `UUIDField`** — the
  catalog event's id, no FK), `start_utc` (timestamptz, NOT NULL), `end_utc` (timestamptz,
  NULL), `event_version` (positive int, NOT NULL), `saved_at`, `created_at`, `updated_at`.
  Unique: `(user_id, event_id)`. Index: `(event_id)`.
  Retention: `ACCOUNT_CONTENT`.

- **`ConflictPair`** — `user_id` (UUID, by value), `kind` (`time` | `duplicate`), `left_kind`
  / `left_id` / `right_kind` / `right_id` (the two sides, by value), `status` (`active` |
  `resolved` | `cleared_by_state_change`), `resolution` (nullable, one of the four
  `ConflictResolution` values), `resolved_at` (nullable), `detected_at`, `created_at`,
  `updated_at`. Checks: status consistency, sides differ, resolution legal for the kind.
  Unique: `(user_id, left_kind, left_id, right_kind, right_id)` with normalised sides.
  Index: `(user_id, status)`.
  Retention: `ACCOUNT_CONTENT`.

- **`PersonalizationAuditEntry`** — the concrete audit table; `at`, `action`, `target_type`,
  `target_id`, `details`, `actor_kind`, `actor_id`, `actor_label`.
  Retention: `AUDIT_LOG`.

### Modifies

None. No existing model changes. `apps/personalization/models.py` goes from empty to four
models; `settings.DATABASE_ROUTING` already routes the app to `personal`.

## Technical Approach

### Architecture

```
                    catalog schema (AD-3 wall — no FK, no join)
                            │
                            │  AD-17 propagation (later intent):
                            │  reads event_version, stamps the snapshot
                            ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  personal schema                                             │
   │                                                              │
   │   PersonalizationAuditEntry   (append-only, AUDIT_LOG)       │
   │                                                              │
   │   PersonalEvent ──┐                                           │
   │      user_id      │                                           │
   │      start_utc    │                                           │
   │      end_utc      │                                           │
   │      start_time_tz│                                           │
   │      version      │                                           │
   │                  ├──► ConflictPair ──► (left_kind, left_id)  │
   │   SavedEvent ────┤      user_id          (right_kind,        │
   │      user_id     │      kind                 right_id)       │
   │      event_id ───┘      status                                │
   │      start_utc          resolution                           │
   │      end_utc            resolved_at                          │
   │      event_version                                          │
   └──────────────────────────────────────────────────────────────┘
              ▲                    ▲
              │                    │
     commands (item ⑤)    reads: Timeline (FR-32),
     AD-5 writes          Pulse Card, /conflicts (FR-33)
```

The two arrows into `ConflictPair` are **by-value id references**, not relations. The same
`ConflictPair` row type serves a personal-vs-personal pair, a personal-vs-saved pair, and a
saved-vs-saved pair — only the side kinds differ.

### Database Changes

```sql
-- personal schema (the app is already routed to PERSONAL; the migration runs on `default`)

CREATE TABLE personal.personalization_personalevent (
    id              uuid PRIMARY KEY,
    user_id         uuid NOT NULL,
    name            varchar(200) NOT NULL,
    start_utc       timestamptz NOT NULL,
    end_utc         timestamptz,
    start_time_tz   varchar(64) NOT NULL,
    location        varchar(300),
    notes           text,
    source          varchar(16) NOT NULL DEFAULT 'user_created',
    version         integer NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL,
    updated_at      timestamptz NOT NULL,
    CONSTRAINT personal_event_end_after_start_ck
        CHECK (end_utc IS NULL OR end_utc >= start_utc),
    CONSTRAINT personal_event_version_positive_ck CHECK (version >= 1)
);
CREATE INDEX personal_event_user_start_idx
    ON personal.personalization_personalevent (user_id, start_utc);

CREATE TABLE personal.personalization_savedevent (
    id              uuid PRIMARY KEY,
    user_id         uuid NOT NULL,
    event_id        uuid NOT NULL,          -- the catalog Event id, by value. No FK.
    start_utc       timestamptz NOT NULL,
    end_utc         timestamptz,
    event_version   integer NOT NULL,
    saved_at        timestamptz NOT NULL,
    created_at      timestamptz NOT NULL,
    updated_at      timestamptz NOT NULL,
    CONSTRAINT saved_event_user_event_uq UNIQUE (user_id, event_id),
    CONSTRAINT saved_event_version_positive_ck CHECK (event_version >= 1)
);
CREATE INDEX saved_event_event_idx
    ON personal.personalization_savedevent (event_id);

CREATE TABLE personal.personalization_conflictpair (
    id              uuid PRIMARY KEY,
    user_id         uuid NOT NULL,
    kind            varchar(16) NOT NULL,
    left_kind       varchar(16) NOT NULL,
    left_id         uuid NOT NULL,
    right_kind      varchar(16) NOT NULL,
    right_id        uuid NOT NULL,
    status          varchar(32) NOT NULL,
    resolution      varchar(32),
    resolved_at     timestamptz,
    detected_at     timestamptz NOT NULL,
    created_at      timestamptz NOT NULL,
    updated_at      timestamptz NOT NULL,
    CONSTRAINT conflict_pair_pair_uq
        UNIQUE (user_id, left_kind, left_id, right_kind, right_id),
    CONSTRAINT conflict_pair_sides_differ_ck
        CHECK (left_kind <> right_kind OR left_id <> right_id),
    CONSTRAINT conflict_pair_status_ck CHECK (
        (status = 'active'          AND resolution IS NULL     AND resolved_at IS NULL)
     OR (status = 'resolved'        AND resolution IS NOT NULL AND resolved_at IS NOT NULL)
     OR (status = 'cleared_by_state_change'
                           AND resolution IS NULL     AND resolved_at IS NOT NULL)
    ),
    CONSTRAINT conflict_pair_resolution_ck CHECK (
        resolution IS NULL
     OR resolution IN ('keep_both', 'edit_new', 'delete_new', 'update_existing')
    ),
    CONSTRAINT conflict_pair_resolution_kind_ck CHECK (
        (kind = 'time'      AND (resolution IS NULL
              OR resolution IN ('keep_both', 'edit_new', 'delete_new')))
     OR (kind = 'duplicate' AND (resolution IS NULL
              OR resolution IN ('keep_both', 'update_existing', 'delete_new')))
    )
);
CREATE INDEX conflict_pair_user_status_idx
    ON personal.personalization_conflictpair (user_id, status);

-- Immutability of a closed pair (D24): a resolved or cleared pair never changes again.
CREATE FUNCTION personal.guard_conflict_pair() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status IN ('resolved', 'cleared_by_state_change') THEN
    IF NEW.status IS DISTINCT FROM OLD.status
       OR NEW.resolution IS DISTINCT FROM OLD.resolution
       OR NEW.resolved_at IS DISTINCT FROM OLD.resolved_at THEN
      RAISE EXCEPTION 'a closed ConflictPair % is immutable', OLD.id
        USING ERRCODE = 'restrict_violation';
    END IF;
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER conflict_pair_guard_update
  BEFORE UPDATE ON personal.personalization_conflictpair
  FOR EACH ROW EXECUTE FUNCTION personal.guard_conflict_pair();

-- The audit table is append-only. The personal schema needs its own copy of the
-- catalog trigger: the runtime role has no access to the catalog schema.
CREATE FUNCTION personal.forbid_history_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF current_setting('eventpulse.retention_purge', true) = 'on' THEN
      RETURN OLD;
    END IF;
  END IF;
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
END
$$;

CREATE TRIGGER personalizationauditentry_append_only
  BEFORE UPDATE OR DELETE ON personal.personalization_personalizationauditentry
  FOR EACH ROW EXECUTE FUNCTION personal.forbid_history_mutation();

REVOKE UPDATE, DELETE ON personal.personalization_personalizationauditentry FROM ep_personal;
```

`ep_personal` has `USAGE` on `personal` only, and **no** `USAGE` on `catalog`. That is why
the `personal` schema needs its own `forbid_history_mutation` rather than calling
`catalog.forbid_history_mutation()`: a trigger function is resolved in the caller's
context, and `ep_personal` cannot see the `catalog` schema, so the shared function would
fail to resolve at the moment the trigger fires — for every write, not just a forbidden
one. The `personal` copy is also simpler: the audit table has no settable column, so it
needs no `TG_ARGV[0]` branch.

The `personal` schema's runtime role is `ep_personal` — the counterpart of `ep_catalog` in
`docker/postgres/init/01-schemas-and-roles.sh`. The grant block must assert that the
revoke actually applied, exactly as `ingestion/0001_initial` does, because a `REVOKE` by a
non-owner merely warns.

### The `resolution` / `kind` pairing (D22, D21)

FR-58 offers different buttons for a time conflict and a duplicate:

| Conflict kind | Prompt button 1 | Prompt button 2 | Prompt button 3 |
|---|---|---|---|
| `time` | "Keep both — I'll manage" | "Edit the new one" (`edit_new`) | "Delete the new one" (`delete_new`) |
| `duplicate` | "Keep both — I'll manage" | "Update the existing one" (`update_existing`) | "Delete the new one" (`delete_new`) |

`keep_both` and `delete_new` are legal for both kinds; `edit_new` is time-only and
`update_existing` is duplicate-only. The `conflict_pair_resolution_kind_ck` check enforces
this at the database level, so an illegal pairing cannot be written even by raw SQL.

There is **no `dismiss`** value, and the constraint above makes one unwritable. That is the
structural expression of PRD FR-58's "there is no dismiss-without-resolution option".

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/apps/personalization/models.py` | Modify | The four concrete models |
| `backend/apps/personalization/migrations/0001_initial.py` | Create | Tables, constraints, indexes, triggers, grants |
| `backend/tests/personalization/test_models.py` | Create | Model, constraint and lifecycle tests |
| `backend/tests/personalization/test_model_structure.py` | Create | The structural test: no FK anywhere, `event_id` is a plain `UUIDField` |
| `backend/tests/wall/test_schema_placement.py` | Modify | Assert the four tables land in `personal` |
| `backend/tests/wall/test_role_isolation.py` | Modify | Assert `ep_personal` cannot update or delete the audit table |
| `backend/shared/constants.py` | Modify | Only if a threshold is needed (see below) |

### Constants

The model layer needs **no new constants**. Every threshold that applies here already
exists in `shared/constants.py`:

- `CONFLICT_MIN_OVERLAP` (15 minutes) — the overlap threshold, used by `domain.conflict`.
- `TITLE_TOKEN_OVERLAP_MIN` (4/5) — the duplicate threshold, used by `domain.conflict`.
- `DUPLICATE_START_WINDOW` (24 hours) — the duplicate scan window.

The FR-58 "±30 minutes" candidate scan window is a **service-layer** concern (which events
to compare), not a model concern, so it lands in work item ⑤ as a constant there.

## Security Considerations

- **No personal data in a label.** `PersonalEvent.name`, `location` and `notes` are the
  user's own content and live in `personal`, which is the schema built for exactly that.
  They never cross into `catalog`. The audit table's `actor_label` holds only a system job
  name, enforced by `actor_check()` and by `shared.actor.Actor`'s own validation.
- **No relation to `User`.** The user is a UUID by value. There is no `GenericForeignKey`,
  so no `ContentType` table is consulted and no information about the account's
  permissions is reachable from a `personal` row.
- **No cross-schema reach.** `SavedEvent.event_id` is a UUID with no FK, so a `personal`
  row cannot cause a read of or a reference into `catalog`. The runtime role for `personal`
  has no `USAGE` on the `catalog` schema — `tests/wall/test_role_isolation.py` already
  proves that for the probe tables, and the new tables are covered by the same role.
- **Append-only audit.** The audit table cannot be rewritten or deleted by the runtime
  role; only the retention sweep, under `SET LOCAL eventpulse.retention_purge = 'on'`,
  may delete from it.

## Integration Points

| System | Type | Purpose |
|--------|------|---------|
| `catalog` (`ingestion`) | Read-only, via `ingestion`'s published interface | The save command reads the Event's `start_time_utc`, `end_time_utc` and `event_version` to stamp the `SavedEvent` snapshot. This is a read across the wall, never a join or a transaction. |
| AD-17 propagation | Write, later intent | Updates the `SavedEvent` snapshot (only when the incoming `event_version` is greater) and re-evaluates `ConflictPair`s. The model supports it: `event_version` only ever rises, and `saved_event_event_idx` finds every save of an event. |
| `delivery` | Call, later intent | `personalization` calls `delivery`'s published service to attach the default Reminder Plan when it creates a `PersonalEvent` (AD-16, FR-20). No `REMINDER_PLAN` column lives on `PersonalEvent`. |
| `domain.conflict` | Pure function | The overlap and duplicate rules, called by the command layer on write (item ⑤), never at render. |
| `shared.models` | Inheritance | `UUIDv7Model`, `AuditEntry`, `ActorColumns`, `actor_check()`. |
| `shared.retention` | Declaration | `ACCOUNT_CONTENT` and `AUDIT_LOG`. |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| The polymorphic conflict side (`kind` + `id` by value) can drift from the real rows: a pair may reference a `PersonalEvent.id` that was deleted. | Medium — the `/conflicts` surface would show a pair whose other side no longer exists. | The command layer (item ⑤) is the only writer and resolves a pair as part of any event deletion. The model also stores `detected_at` and the user can resolve a pair to `keep_both`, which is the explicit "both still happen" record. A dangling reference is a command-layer bug, and item ⑤'s tests cover delete-with-open-conflict. |
| `CONFLICT_PAIR` stores both sides by value, so a unique constraint on the unordered pair cannot be enforced by the database alone. | Medium — the same pair could be inserted twice with the sides swapped. | The command layer normalises the sides (lexicographic on `(kind, id)`) before writing, and a test pins that `(A,B)` and `(B,A)` are one row. The database constraint catches the normalised form; the normalisation is what makes it symmetric. |
| The append-only trigger and the `personal` schema's role grants are hand-written SQL and could silently not apply. | High — an audit row could be rewritten. | The migration's grant block **asserts** the revoke took effect and raises if it did not, exactly as `ingestion/0001_initial` does. The trigger is verified by a test that attempts the update and expects the refusal. |
| `PersonalEvent.version` is not enforced to increase by a database trigger. | Low — a stale write could lower the version, breaking AD-7's `personal_event_revision` send key. | The command layer owns the increment (item ⑤), and the model check keeps the value positive. A trigger cannot know which mutation is legitimate. |
| `start_time_tz` cannot be validated by a database check. | Medium — an invalid zone name would be stored. | The command layer validates via `domain.timezones.canonical_zone` before writing (item ⑤). The model stores the name; the *boundary* refuses the value, which is what the work item's AC asks for. |
| The `personal` schema's `forbid_history_mutation` duplicates the `catalog` function. | Low — two copies could drift. | The `personal` copy is deliberately simpler (no settable-column argument, because the audit table has none). A shared function is not an option: `ep_personal` has no `USAGE` on the `catalog` schema, so `catalog.forbid_history_mutation()` would fail to resolve for every write. The two bodies are each a handful of lines and each is covered by its own trigger test. |
| `SavedEvent.event_version` could be written lower than the current value, re-stamping a stale snapshot. | High — AD-17's ordering guarantee would break. | AD-17's rule is enforced at the propagation call site ("only if the change's `event_version` is greater than the version already stored"), which is work item ⑤ / the propagation job. This item adds the positive-version check and the lookup index the rule needs. |

## Implementation Checklist

1. `apps/personalization/models.py`: `PersonalEvent` with its `source` `TextChoices`,
   fields, checks and index (D5–D11).
2. `apps/personalization/models.py`: `SavedEvent` with `event_id` as a plain `UUIDField`,
   the snapshot fields, the unique constraint and the propagation index (D12–D16).
3. `apps/personalization/models.py`: `ConflictPair` with `ConflictSideKind`, `ConflictKind`,
   `ConflictResolution` and `Status` `TextChoices`, the four side columns, the checks and
   the unique constraint (D17–D23, D26).
4. `apps/personalization/models.py`: `PersonalizationAuditEntry(AuditEntry)` with
   `AUDIT_LOG` retention (D27).
5. `apps/personalization/migrations/0001_initial.py`: generate the tables, then hand-write
   the `guard_conflict_pair` trigger, the `personal.forbid_history_mutation` function, the
   audit trigger and the `ep_personal` grant/revoke block with its assertion (D24, D28).
6. `tests/personalization/test_models.py`: one test per constraint — end-before-start,
   positive version, the three status shapes, the illegal status/resolution combinations,
   sides differing, the unique constraint, and the resolution/kind pairing.
7. `tests/personalization/test_models.py`: the trigger test — a resolved pair refuses an
   update; the audit table refuses an update and a delete.
8. `tests/personalization/test_model_structure.py`: the structural test — for each of the
   three models, assert no field `is_relation`; assert `SavedEvent.event_id` is a
   `UUIDField` and not a `ForeignKey`; assert the `personal` models declare no relation to
   `User` (D12, D2).
9. `tests/wall/test_schema_placement.py`: assert the four tables are in `personal` and
   that `catalog` is unchanged (verified through `information_schema`, not assumed).
10. `tests/wall/test_role_isolation.py`: assert `ep_personal` cannot update or delete the
    audit table, and that the runtime role still cannot read `catalog`.
11. Run `manage.py check` (E001/E002/E003/E004/E005), `make lint-imports` (13 contracts),
    `ruff check`, `ruff format --check`, the full backend suite and the coverage gate.
12. Append the item's section to `test-report.md` and `review-report.md`.

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-10-29*
