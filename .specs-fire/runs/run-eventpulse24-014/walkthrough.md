---
run: run-eventpulse24-014
work_item: source-registry-commands-admin
intent: event-catalog-ingestion
generated: 2026-10-28
mode: confirm
---

# Implementation Walkthrough: Source Registry Commands & Admin

## Summary

The Source Registry (FR-13) now has its write path. Seven named commands in `apps/ingestion/services/` cover every Source, ToS-review and Venue write. Each one validates its input, runs in `atomic(using=CATALOG)`, and writes an audit row with the caller's `Actor`.

The FR-17 guard refuses crawl without an approved ToS review:
- when a source is registered
- when it is switched to crawl
- when a crawl source moves to a new host
- at ingest, through `ensure_can_ingest`, which item 6 calls

Django admin is routed at `/admin/` for the first time. It is a thin client of those commands: saves call them, nothing can be deleted, events, state changes and the audit log are read-only, and the audit list shows who did what and when.

There are no model changes and no migration.

## Structure Overview

```
 Django admin (apps/ingestion/admin.py)            later: pipeline, scheduler, seed command
   SourceForm / VenueForm / TosReviewForm.clean()      │
     └─ check_source_change / check_new_venue /        │
        clean_tos_review   (same rules, shown on form) │
   save_model ─ Actor.user(request.user.pk) ──┐        │
                                              ▼        ▼
            services/source_registry.py · services/venue_registry.py
              atomic(using=CATALOG): validate → lock row → write → write_audit()
                                              │
                         catalog: Source · TosReview · Venue · IngestionAuditEntry
```

## Architecture

### Pattern Used

The admin is a **command client**: the service layer is the only write path (AD-5), and the admin is a client of it, like any other (AD-14). The validation rules are written once, in the service module, and the forms call them from `clean()`, so a refusal is shown on the form instead of becoming a 500.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/services/source_registry.py` | `register_source`, `update_source`, `pause_source`, `resume_source`, `record_tos_review`, `ensure_can_ingest`; the checks `check_source_change`, `clean_source_input` and `clean_tos_review`; `TosReviewInput`; the errors |
| `backend/apps/ingestion/services/venue_registry.py` | `register_venue`, `set_venue_timezone`, `check_new_venue`, `clean_venue_tz`, errors |
| `backend/tests/ingestion/test_source_registry.py` | 68 tests, including the `tos_status` invariant sequence and the rollback tests |
| `backend/tests/ingestion/test_venue_registry.py` | 21 tests |
| `backend/tests/ingestion/test_admin.py` | 39 tests through Django's test client |
| `backend/tests/architecture/test_no_direct_writes.py` | 30 tests: an AST scan of every admin and API module, plus planted violations |

### Modified

| File | Changes |
|------|---------|
| `backend/apps/ingestion/admin.py` | `CommandAdmin`, `ReadOnlyAdmin`, and admins for Source (with a ToS-review inline), TosReview, Venue, Event, EventStateChange and IngestionAuditEntry |
| `backend/config/urls.py` | `path("admin/", admin.site.urls)` |
| `backend/config/settings.py` | Comment: admin is routed |
| `backend/shared/constants.py` | `DEFAULT_INGESTION_CADENCE`, `INGESTION_CADENCE_MIN` |
| `backend/tests/architecture/checkers.py` | `direct_write_calls`, `surface_files` |
| `backend/tests/ingestion/test_domain_parity.py` | The cadence map covers every `AcquisitionMethod` |
| `backend/tests/config/test_project.py` | `test_admin_not_routed_yet` replaced by `test_admin_routed_to_the_admin_site` |
| `.specs-fire/standards/coding-standards.md` | Source Registry rules, admin as a command client, the no-direct-writes scan, and the permission rule for cross-model form inputs |
| `brief.md`, `ingest-pipeline-and-lifecycle.md`, `real-feeds-and-e2e-proof.md` | Deferrals (see Deviations) |

## Domain Model

No entities changed. Two value objects are new:
- **`TosReviewInput(decision, evidence_url, notes)`**: a person's review of the source's *current* method. An approval needs an http(s) evidence URL.
- **`CheckedSourceChange(values, resets_tos, tos_review)`**: holds the cleaned values (on update, only the fields that really change), whether the cached review stops applying, and the cleaned review.

## Key Implementation Details

### 1. `tos_status` as a cache that can't drift

- Only `_write_review` (from `record_tos_review`, or inline from register/update) and the reset in `update_source` write `tos_status`, and always in the same transaction as the change that causes it.
- A **method change or a URL-host change** resets it to `not_reviewed`. A path-only change keeps it.
- The tested invariant (plan R3): `tos_status` = the latest review of the current method **since that method was set**, else `not_reviewed`.
- The scripted test covers rss → api → rss: an old RSS approval still exists, but it doesn't come back.

### 2. Crawl needs its review in the same command (plan R2)

A `TosReview` references a Source, so a new crawl source can't be reviewed before it exists. Switching to crawl resets the review as well. So `register_source` and `update_source` take an optional `tos_review`, and crawl requires an approved one, written right after the insert or switch. Without it, `CrawlNeedsTosReviewError` is raised and **nothing** is written; tests assert there is no Source, review or audit row.

### 3. Admin saves go through commands

- `save_model` calls the command with `Actor.user(request.user.pk)`. It then points the admin's unsaved instance at the stored row (`adopt`) so the redirect works.
- `CommandAdmin` turns off every other way to write:
  - delete permission is false
  - `delete_model` and `delete_queryset` raise
  - the base `save_model` raises
  - `save_related` does nothing
  - `LogEntry` writing and `construct_change_message` are turned off
- The tests prove the command ran from the audit row, because a plain `obj.save()` writes none.

### 4. Who, what, when

The audit changelist resolves usernames for the page's user actors in one query on `personal` (AD-3: composed for display, never stored in `catalog`). System actors show as `"<job> (system job)"`.

## Security Considerations

| Concern | Approach |
|---------|----------|
| Admin write access per model (AD-14) | Django's per-model permissions. The pause and resume actions need `change_source`. **Approving ToS from the Source form needs `add_tosreview`** (code-review fix): without it the fields are hidden and a forged POST is refused. |
| No personal data in `catalog` (OQ-8, D17) | The actor is stored by UUID with no label. Usernames are read from `personal` only for display. |
| A second, unauthoritative history | Admin `LogEntry` is off: it would commit in `personal` even if the catalog write rolled back. |
| Untrusted source strings (AD-9) | Shown through admin auto-escaping; nothing is marked safe. |
| URLs | Source and evidence URLs must be http(s) with a host and no userinfo, at most 2,048 characters. Fetch-time SSRF policy stays in the HTTP adapter. |
| Deletes | Impossible from admin, even for a superuser (403), plus `PROTECT` FKs. Sources are paused instead. |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| R1: admin placement | `apps/ingestion/admin.py` | Registering a model needs its class, which contract `models-ingestion` keeps inside `ingestion`. |
| R2: crawl review | Inline in the same command | It's the only order that satisfies both "review needs a Source" and "a switch resets the review". |
| R3: invariant | Latest review of the current method since it was set | Old approvals never revive. |
| R4: host change | Resets the review; crawl needs a new one | A ToS review covers one site. |
| R5: cadences | 4h for rss/ics/jsonld/api/partnership, 24h for crawl and email_ics, 15-minute floor | The AC fixes RSS at 4h; crawl is polled politely. |
| R6: duplicate feeds | Refused by `canonical_url`, no constraint | Two sources on one feed would double the binding work. |
| R7: venues | Plus `set_venue_timezone`; the identity fields are fixed | D14 needs tz backfill; renames go to the editorial intent. |
| R8: `LogEntry` | Off | One audit trail. |
| R9: ToS reviews | Need evidence (approvals) and a person | FR-17 requires a logged review, and it must be auditable. |
| R10: pause/resume repeats | No-op, no audit row | The audit log records changes, not attempts. |
| Review fix | ToS approval in the Source form needs `add_tosreview` | Probe-confirmed bypass of the per-model grant (AD-14). |

## Deviations from Plan

- **One extra admin rule (code-review fix):** the Source form's ToS fields need `add_tosreview`. The plan didn't cover this; the user approved it at review.
- **`construct_change_message` is overridden** to return `[]`. The plan only listed the `log_*` no-ops. Without it, `save_related`'s skipped formset save breaks Django's message building (an `AttributeError` on `formset.new_objects`).
- **Module names** follow the plan (`source_registry.py`, `venue_registry.py`), not `coding-standards`' "verb phrase" example. One registry concept per module.
- **One existing test was replaced:** `test_admin_not_routed_yet` pinned the scaffold placeholder that this item ends.
- **Deferrals, written into later items:**
  - `real-feeds-and-e2e-proof`: the `editorial` group with its exact per-model permissions; the operator uses it instead of superuser.
  - `ingest-pipeline-and-lifecycle`: call `ensure_can_ingest` on the **locked** row. A host change already re-triggers the ToS review.
  - `brief.md`, under "Still open": venue renames.

## Dependencies Added

None.

## How to Verify

1. **Run the new tests**
   ```bash
   cd backend && uv run pytest -q tests/ingestion/test_source_registry.py tests/ingestion/test_venue_registry.py tests/ingestion/test_admin.py tests/architecture/test_no_direct_writes.py
   ```
   Expected: 158 passed (68 + 21 + 39 + 30).

2. **Run all the gates**
   ```bash
   make lint-backend && make manage ARGS="check" && make manage ARGS="makemigrations --check --dry-run" && make coverage-backend
   ```
   Expected: 13 contracts kept, no issues, no changes, 1476 passed, 99.03% overall, 100% `domain/`.

3. **Use the admin by hand.** This is not done in this run: it was verified through Django's test client only, so as not to add a superuser to the dev database.
   ```bash
   make up && make migrate
   make manage ARGS="createsuperuser"
   make api        # then open http://127.0.0.1:8000/admin/
   ```
   - Add an RSS source with the cadence empty: it gets 4:00:00.
   - Change the method to crawl without the "Terms reviewed and approved" box: you get a form error. With the box and a terms URL, `tos_status` becomes approved.
   - Try "Delete": it is forbidden.
   - Open "Ingestion audit entries": your username shows for each change.

## Test Coverage

- **Tests added:** 161. That is 158 in the four new files, 1 parity test, and 2 alias-scan checks generated for the new modules. One existing test was replaced.
- **Totals:** the suite went from 1315 to 1476. Coverage is 99.03% overall, 100% for both service modules, 99% for `admin.py` (only the unreachable `log_deletions` no-op is uncovered), and 100% for `domain/`.
- **Mutation probes:** 13 planted bugs, each caught by at least one test (see `test-report.md`).
- **Status:** all passing.

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing, and each key test shown able to fail
- [x] Code-review finding fixed with your approval
- [x] Documentation updated: coding standards, later items' ACs, intent brief
- [x] Developer notes captured

## Developer Notes

- **The admin is not a back door.** To add a writable admin for a catalog model:
  - subclass `CommandAdmin` and call a command in `save_model`
  - run the command's own `check_*` function in the form's `clean()`
  - check every *other* model permission the form can trigger
- **`update_source` takes a `changes` mapping**, not the whole record. Values equal to the stored ones are dropped before anything is decided, so a resubmitted form never resets the review or writes an audit row.
- **Pass the locked row to `ensure_can_ingest`.** It trusts the instance it is given.
- **Audit `details` go through `DjangoJSONEncoder`:** cadences read back as ISO-8601 durations (`"P0DT04H00M00S"`), and UUIDs as strings.
- **`direct_write_calls` flags any `.update()`**, including `dict.update`. Use another spelling in admin and API modules.
- **`surface_files()` expects 13 modules** (six apps × admin/api, plus `config/api.py`). Adding an app means updating that count on purpose.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-014*
