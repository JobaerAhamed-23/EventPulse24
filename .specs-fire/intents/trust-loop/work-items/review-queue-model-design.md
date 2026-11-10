---
work_item: review-queue-model
intent: trust-loop
created: 2026-11-10
mode: validate
checkpoint_1: approved
---

# Design: Something to queue onto — the ReviewItem and the editorial group

## Summary

`ReviewItem` is FR-57's queue row. It lives in schema `catalog` and is owned and written only by `ingestion` (AD-4, AD-16). An item is raised against **an Event** (reasons `user_reported` and `in_review`) or **a Source** (reason `source_reliability`). There is **at most one open item per (target, reason)**: a second raise bumps the open row and never stacks a duplicate. One command, `raise_review_item`, raises and bumps. Resolution commands belong to `editorial-review-commands`. This item builds the columns, constraints and trigger those commands need, and nothing that decides a verdict.

The editorial role gains `view` and `change` on `ReviewItem` by extending the existing, idempotent `seed_local_stack` grant table. It does **not** use a data migration, which the work item's AC asked for (see D9).

## Scope

**In Scope:**
- The `ReviewItem` model, the migration `ingestion/0008_reviewitem` with its guard trigger, and the constants
- `apps/ingestion/services/review_queue.py::raise_review_item`, the only writer in this item
- Adding `reviewitem: (change, view)` to `EDITORIAL_GRANTS`
- Model, constraint, trigger, command and grant tests

**Out of Scope:**
- Approve, Edit, Reject and Dismiss, and the closing of items (`editorial-review-commands`). This item fixes the resolution columns those commands will set, and the trigger that freezes a closed row.
- Who calls `raise_review_item`: ingestion intake and backfill (`review-intake-and-backfill`), reports (`event-report-api`) and escalation (`reliability-recompute-and-escalation`)
- The admin (`editorial-admin-queue`) and the queue metrics read
- Any FR-16 observation row

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D1. One table, two targets** | Nullable `event` FK and nullable `source` FK (both `PROTECT`, both in `catalog`, so an FK is legal under AD-3). A `CheckConstraint` ties the target to the reason: `user_reported`/`in_review` require `event` and no `source`; `source_reliability` requires `source` and no `event`. | A single queue is what the editor works. A generic `(target_type, target_id)` pair would lose referential integrity, and a `GenericForeignKey` is banned on catalog models (ContentType lives in `personal`). Two FKs plus one check is the smallest shape the database can fully hold. |
| **D2. Uniqueness per (target, reason), not per target** | Two partial unique constraints: `(event, reason) WHERE status='open'` and `(source, reason) WHERE status='open'`. NULLs are distinct, so each constraint only bites its own target kind. | This keeps the approved AC. An event that is both quarantined **and** reported has two open items. `editorial-review-commands` must therefore close **every open item on the event** when it records one verdict, so the editor decides once. That rule is pinned here as an integration requirement (see Integration Points). |
| **D3. Category tallies are four integer columns** | `reports_wrong_date_time`, `reports_wrong_venue`, `reports_does_not_exist`, `reports_duplicate`: `PositiveIntegerField(default=0)`. A check enforces that they are all zero unless `reason='user_reported'`. `report_count` is a Python property (the sum), not a column. | Columns are queryable, checkable, and bumpable atomically with `F() + 1`. JSON would be none of those. A stored total could drift from its parts. The category vocabulary is `ReviewItem.ReportCategory`, which `EventReport` will reuse through a published re-export so the four values exist once. |
| **D4. No reporter identity, including in the audit row** | `raise_review_item` from a report runs as `Actor.system("event_report")`, never `Actor.user(reporter)`. | AD-3 keeps the item free of user identity, but the **audit row is in `catalog` too**, and the editorial group holds `view_ingestionauditentry`. Raising as the reporter would let any editor read who reported what from the audit list, which is the leak AD-3's ER note exists to prevent. The reporter is recorded once, in `personal.EventReport`. |
| **D5. Status, resolution, resolver** | `status ∈ {open, resolved}`. `resolution ∈ {approved, edited, rejected, dismissed, withdrawn}`, empty while open. `resolved_at`. The resolver is stored as `resolved_by_kind`, `resolved_by_id` and `resolved_by_label` with the `Actor` rules. | `ActorColumns` cannot be used directly, because its `actor_kind` is non-null and an open item has no resolver. The raiser is already in the audit log, so no raiser columns are needed. **`withdrawn`** is added now for a system close, when the target leaves review by another route (for example, superseded). `review-intake-and-backfill` needs it and should not have to migrate this table again. |
| **D6. Resolution consistency is a check, not a convention** | (a) `open` ⇔ resolution empty, `resolved_at` null, all resolver columns empty. (b) `resolved` ⇔ all four set, and the resolver passes the actor rule. (c) `approved`/`edited`/`rejected` only on event items; `dismissed` only on source items; `withdrawn` on either. (d) `withdrawn` requires a system resolver; every other resolution requires a user resolver. | This follows the `ExtractedRecord` D21 "resolution consistency" precedent. Rule (d) is AD-14's "every editorial action is attributed" held at the database level: a verdict cannot be recorded by a job. |
| **D7. Closed rows are immutable: a trigger** | `catalog.guard_review_item()` runs `BEFORE UPDATE`. It refuses any change to a row whose `OLD.status='resolved'`. On any row, it refuses changes to `reason`, `event_id`, `source_id` and `raised_at`. It runs `BEFORE DELETE` too, and allows delete only under `SET LOCAL eventpulse.retention_purge='on'`. | This is the `guard_conflict_pair` and `forbid_history_mutation` pattern already used in both schemas. A closed verdict is history. Re-opening would make the FR-16 observations (which count resolutions) silently wrong. A new raise against a closed target opens a **new** row, so history is kept, not rewritten. |
| **D8. SLA is a `due_at` column, set only for `user_reported`** | `due_at = raised_at + REVIEW_SLA_USER_REPORTED` (24h) on the **first** raise. A bump never moves it. `in_review` and `source_reliability` items have `due_at = NULL` and are ordered by `raised_at`. A check enforces that `due_at` is non-null iff `reason='user_reported'`. | The PRD gives an SLA only for user reports. "Reviewed at least daily" is a cadence for the team, not a per-item deadline, and inventing one would put false breaches on the dashboard. Keeping `due_at` on the first report means a stream of reports cannot keep pushing the deadline back. |
| **D9. The editorial group: extend `EDITORIAL_GRANTS`, not a migration** *(deviation from AC)* | Add `"reviewitem": ("change", "view")` to `config/management/commands/seed_local_stack.py`'s table, and update its docstring from "twelve" to "fourteen". Its `permissions.set()` already removes stale grants. | Groups and permissions live in `personal` (`auth`), while `ingestion` migrations run only on `catalog` (`db_router.allow_migrate`), so an ingestion data migration cannot write them. Permissions are created in `post_migrate`, so a migration in a `personal` app could run before `ingestion.reviewitem`'s permissions exist. The group is already owned by this idempotent command, so a second owner would make two sources of truth. **No `delete_reviewitem`, no `add_reviewitem`:** items are raised by commands, never typed in by hand. |
| **D10. `raise_review_item` contract** | `raise_review_item(*, actor, reason, event=None, source=None, category=None, now) -> RaiseResult(item, created: bool)`. It opens `atomic(using=CATALOG)` itself, which nests safely inside a caller's transaction. It inserts inside a savepoint. On `IntegrityError` from the open-unique constraint, it re-reads the open row `select_for_update()` and bumps it. The bump uses `F()` increments and sets `last_raised_at`. It writes one audit row per call: `review_item_raised` or `review_item_bumped`. | This mirrors `request_revalidation`'s insert-then-recover race handling, but bumps with `F()` so two concurrent reports both count. `select_for_update` serialises against a resolve committing at the same moment: if the row closed between the failed insert and the re-read, the call retries the insert once. A closed row is never bumped (D7). Validation: `category` is required iff `reason=user_reported`, and the target must match the reason. Both raise `ValidationError`. |
| **D11. Retention** | `SOURCE_REGISTRY`. | The row holds no user-derived data (D4) and describes catalog content. It ages out with the Event and Source it is about. |
| **D12. Ordering index** | A partial index on `(due_at, raised_at) WHERE status='open'`. | This is the admin changelist's access path. Open items are a tiny fraction once the queue is worked, and closed items are never scanned by the queue. |

## Data Models Affected

### Creates
- **ReviewItem** (`catalog.ingestion_reviewitem`). It subclasses `UUIDv7Model` and has:
  - `reason`
  - `event` (FK, null) and `source` (FK, null)
  - `status`, `resolution`
  - `reports_wrong_date_time`, `reports_wrong_venue`, `reports_does_not_exist`, `reports_duplicate`
  - `raised_at`, `last_raised_at`, `due_at` (null)
  - `resolved_at` (null), `resolved_by_kind`, `resolved_by_id` (null), `resolved_by_label`
  - `created_at`, `updated_at`

  It is the FR-57 queue row.

### Modifies
- **`shared/constants.py`**: adds `REVIEW_SLA_USER_REPORTED = timedelta(hours=24)`.
- **`seed_local_stack.EDITORIAL_GRANTS`**: adds `reviewitem: (change, view)` (D9).

## Technical Approach

### Architecture

```
 ingest_item (in_review)      EventReport API (personal)      reliability job
   [review-intake]              [event-report-api]              [recompute]
        │ Actor.system(          │ Actor.system("event_report")    │ Actor.system(
        │  "ingest_pipeline")    │ (never the reporter, D4)        │  "reliability_job")
        └──────────────┬─────────┴──────────────┬──────────────────┘
                       ▼                        ▼
          apps.ingestion.services.review_queue.raise_review_item
             atomic(CATALOG) ─ savepoint insert ─┬─ ok → audit "review_item_raised"
                                                 └─ IntegrityError → select_for_update
                                                    open row → F()+1 bump → audit "…_bumped"
                       ▼
          catalog.ingestion_reviewitem  ◄── catalog.guard_review_item() trigger (D7)
                       ▲
          [editorial-review-commands] closes items (resolution + resolver)
          [editorial-admin-queue]     reads through an ingestion read service
                                      (editorial may not import ingestion.models)
```

### Database Changes

```sql
-- the model fields come from Django's CreateModel; these are hand-written in RunSQL:
CREATE FUNCTION catalog.guard_review_item() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF current_setting('eventpulse.retention_purge', true) = 'on' THEN RETURN OLD; END IF;
    RAISE EXCEPTION 'a ReviewItem is never deleted' USING ERRCODE = 'restrict_violation';
  END IF;
  IF OLD.status = 'resolved' THEN
    RAISE EXCEPTION 'a resolved ReviewItem % is immutable', OLD.id USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.reason IS DISTINCT FROM OLD.reason OR NEW.event_id IS DISTINCT FROM OLD.event_id
     OR NEW.source_id IS DISTINCT FROM OLD.source_id OR NEW.raised_at IS DISTINCT FROM OLD.raised_at THEN
    RAISE EXCEPTION 'a ReviewItem''s target and reason are fixed' USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER review_item_guard BEFORE UPDATE OR DELETE ON catalog.ingestion_reviewitem
  FOR EACH ROW EXECUTE FUNCTION catalog.guard_review_item();
-- plus reverse SQL that drops both.
```

Constraints, as Django `Meta.constraints`:
- `review_item_target_ck` (D1)
- `review_item_open_event_reason_uq` and `review_item_open_source_reason_uq` (D2)
- `review_item_tallies_ck` (D3)
- `review_item_resolution_ck` (D6 a–d)
- `review_item_due_ck` (D8)

Index: `review_item_open_idx` (D12).

## Dependencies

- None among the trust-loop items. It relies on existing `Event`, `Source`, `write_audit`, `Actor` and `UUIDv7Model`.

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/apps/ingestion/models.py` | Modify | `ReviewItem` with its choices and constraints |
| `backend/apps/ingestion/migrations/0008_reviewitem.py` | Create | The model and the guard trigger (forward-only, with reverse SQL) |
| `backend/apps/ingestion/services/review_queue.py` | Create | `raise_review_item`, `RaiseResult` |
| `backend/shared/constants.py` | Modify | `REVIEW_SLA_USER_REPORTED` |
| `backend/config/management/commands/seed_local_stack.py` | Modify | `reviewitem` grants and docstring count (D9) |
| `backend/tests/ingestion/test_review_item_model.py` | Create | Constraints and trigger |
| `backend/tests/ingestion/test_review_queue.py` | Create | Raise, bump, validation, concurrency, audit |
| existing seed or e2e test that pins the group's grant set | Modify | The expected set gains two codenames, and still asserts no delete |

## Security Considerations

- **Reporter anonymity in the editorial surface (D4):** neither the item nor its audit row carries a reporter id. A test asserts that the audit row from a report-raised item has `actor_kind='system'` and `actor_id IS NULL`.
- **Least privilege (AD-14):** the group gets `change` and `view` only. There is no `add` or `delete`, and the group never makes a member a superuser. The existing seed test's "no delete" assertion covers the new model.

## Integration Points

| System | Type | Purpose |
|--------|------|---------|
| `editorial-review-commands` | Requirement placed on it | It sets the resolution columns. A verdict on an event closes **every** open item for that event (D2). It never touches a resolved row (D7). |
| `review-intake-and-backfill` | Caller | Raises `in_review`, and uses `withdrawn` for system closes (D5). |
| `event-report-api` | Caller, cross-wall by id | Raises `user_reported` as `Actor.system("event_report")` (D4), and reuses `ReviewItem.ReportCategory` through a published re-export. |
| `reliability-recompute-and-escalation` | Caller | Raises `source_reliability` on a Source. |
| `editorial-admin-queue` | Reader | Its admin must be registered where `ingestion.models` is importable, or built over an `ingestion` read service. The `models-ingestion` import contract forbids `apps.editorial` from importing the model. That item's design decides which. |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Two open items on one event (D2) lead to two verdicts, or to one item left open forever | Medium | An integration requirement on `editorial-review-commands` (close all open items on the event), plus a test there. The admin can show sibling items. |
| A concurrent bump and resolve: a report counted on an item that was just closed | Medium | `select_for_update` on the re-read, plus D7's trigger. If the row closed, the raise opens a fresh item, so the report is never lost and never lands on history. A concurrency test drives both orders. |
| The trigger and the Python model drift (a new immutable column added without updating the trigger) | Low | A test enumerates the trigger's fixed columns against a constant tuple on the model, as the existing `LIFECYCLE_FIELDS` and `guard_event_write` test does. |
| Production has no group, because D9 relies on a "local" seed command | Medium | It is recorded as a known gap. The PRD's operations runbook needs a line saying deploy runs the grant sync. Splitting `_editorial_group` into its own `sync_editorial_group` command is a small follow-up, offered rather than built here. |

## Implementation Checklist

- [ ] `shared/constants.py`: `REVIEW_SLA_USER_REPORTED`
- [ ] `ReviewItem` model: choices `Reason`, `Status`, `Resolution`, `ReportCategory`; fields; the six constraints; the partial index; `retention_category`; the `report_count` property; a `FIXED_FIELDS` tuple
- [ ] Migration `0008_reviewitem`: `CreateModel`, plus `RunSQL` for the guard trigger and its reverse
- [ ] Constraint tests: each illegal target shape, each illegal resolution shape (D6 a–d), the tallies on a non-report item, `due_at` on a non-report item, and duplicate open items refused while a closed duplicate is allowed
- [ ] Trigger tests: a resolved row refuses update; a fixed column refuses change on an open row; delete is refused, and allowed under the purge setting; the `FIXED_FIELDS` and trigger parity test
- [ ] `review_queue.raise_review_item` with savepoint insert, locked re-read, `F()` bump, a single retry on a closed race, validation, and the audit row
- [ ] Command tests: raise; bump (the tallies increment, `due_at` is unchanged, `last_raised_at` moves); a raise after a close opens a new row; the reason/target mismatch and missing-category errors; the audit action and actor (the D4 system actor); two-thread concurrent raises yield one row with count 2
- [ ] `EDITORIAL_GRANTS` plus docstring, and the existing grant-set test updated (and shown failing before the update)
- [ ] `manage.py check` (E001–E005), `makemigrations --check`, import-linter, ruff, and the full backend suite

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-11-10*
