---
run: run-eventpulse24-014
work_item: source-registry-commands-admin
intent: event-catalog-ingestion
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at: 2026-10-28T10:59:26Z
---

# Implementation Plan: Source Registry Commands & Admin

## Approach

> **Needs your call:** decisions **R1–R10** below.

Two service modules hold every Source, ToS-review and Venue write as a named command. Each command validates its input, runs in `transaction.atomic(using=CATALOG)`, and calls `write_audit` with the caller's `Actor`. The Django admin is a thin form layer: its `save_model` calls a command, every delete path is disabled, and the event, state-change and audit lists are read-only. `/admin/` is routed for the first time.

**Commands** (`apps/ingestion/services/`):

```python
# source_registry.py
@dataclass(frozen=True)
class TosReviewInput:
    decision: TosReview.Decision           # approved | rejected
    evidence_url: str = ""                 # required when approved (R9)
    notes: str = ""

register_source(*, actor, name, source_type, url, acquisition_method, tz_coverage,
                city="", ingestion_cadence=None, freshness_ttl_hours=24,
                tos_review: TosReviewInput | None = None) -> Source
update_source(*, actor, source_id, changes: Mapping[str, object],
              tos_review: TosReviewInput | None = None) -> Source
pause_source(*, actor, source_id) -> Source
resume_source(*, actor, source_id) -> Source
record_tos_review(*, actor, source_id, review: TosReviewInput) -> TosReview
ensure_can_ingest(source) -> None            # FR-17 guard; the pipeline (item 6) calls it

# venue_registry.py
register_venue(*, actor, name, city, country_code, tz=None) -> Venue
set_venue_timezone(*, actor, venue_id, tz) -> Venue          # R7
```

- **Validation:** each command raises `domain.errors.ValidationError` with field errors (`details = {"errors": [{"loc": [field], "msg": …}]}`). Its pure checks are exposed as `clean_source_input(...)` and `clean_venue_input(...)`, so the admin forms run the same rules in `clean()` and show the errors on the form instead of a 500.
- **Locking:** `update_source`, `pause_source`, `resume_source`, `record_tos_review` and `set_venue_timezone` load the row with `select_for_update()` inside the transaction.
- **`update_source`** accepts only `name, source_type, url, city, acquisition_method, ingestion_cadence, freshness_ttl_hours, tz_coverage`. `status` changes only through pause and resume. `tos_status` changes only through reviews and resets. The operational fields (`etag`, `last_*`, `consecutive_failures`, `stale_since`) belong to the pipeline and the scheduler. An unknown key is a `ValidationError`. If nothing changes, nothing is written and no audit row is added.
- **Audit rows:** `target_type` is `source` or `venue`. A ToS review is audited against its **source**, with `tos_review_id`, `decision` and `acquisition_method` in `details`, so one source's history reads as one trail. `update_source` stores `{"changes": {field: {"from": …, "to": …}}, "tos_status_reset": bool}`.
- **New errors** (in `source_registry.py` and `venue_registry.py`, following the `EventNotFoundError` example in `coding-standards.md`):
  - `SourceNotFoundError` and `VenueNotFoundError` (`NotFoundError`)
  - `CrawlNeedsTosReviewError` (`PermissionDeniedError`, code `crawl_needs_tos_review`)
  - `SourcePausedError` (`ConflictError`, code `source_paused`)
  - `SourceAlreadyRegisteredError` and `VenueAlreadyRegisteredError` (`ConflictError`, with the existing row's ID in `details`)

**Admin** (`apps/ingestion/admin.py`, R1). The base class `CommandAdmin` gives every class these rules:

| Model | Add | Change | Delete | Notes |
|---|---|---|---|---|
| Source | `register_source` | `update_source` | **disabled** | List: name, method, status, `tos_status`, `tz_coverage`, `last_ingested_at`, stale flag (`stale_since` set). Search: name, URL, city. Filters: method, status, `tos_status`, `tz_coverage`. Actions: pause and resume (change permission). `status`, `tos_status` and the operational fields are read-only. The form adds `tos_approved`, `tos_evidence_url` and `tos_notes` (R2). There is a read-only inline of ToS reviews. |
| TosReview | `record_tos_review` | read-only | disabled | Fields: source, decision, evidence URL, notes. The method is taken from the source. |
| Venue | `register_venue` | only `tz`, via `set_venue_timezone` | disabled | Name, city and country are read-only after registration because they define the fingerprint (R7). |
| Event, EventStateChange | none | read-only | disabled | List and search only. |
| IngestionAuditEntry | none | read-only | disabled | The "who, what, when" list. Who is the username for a user actor, looked up in bulk from `personal` per page through `get_user_model()`, or the job label for a system actor. Filters: action, target type. Dated by `at`. |

- `save_model` builds `Actor.user(request.user.id)`. It never calls `obj.save()` or `super().save_model()`. After the command it points `obj` at the stored row with `obj.pk = row.pk` and `obj.refresh_from_db()`, so the admin's redirect works.
- `delete_model` and `delete_queryset` raise as a second guard. `has_delete_permission` returns `False`, so the delete view returns 403 even for a superuser, and `delete_selected` disappears from the actions.
- `save_related` does nothing: these models have no M2M, and the inlines are view-only.
- `log_addition`, `log_change` and `log_deletions` do nothing (R8).

### Decisions that need your call

| # | Question | Proposed choice | Why |
|---|---|---|---|
| **R1** | Where the admin classes live | **`apps/ingestion/admin.py`**, not `apps/editorial/admin.py` | `admin.site.register(Source, …)` needs the model class. From `editorial` that would mean importing `apps.ingestion.models`, which breaks contract `models-ingestion`. The workarounds are worse: services re-exporting model classes, or `apps.get_model()`, both of which hide the dependency from the linter. With the classes in `ingestion`, the owner registers its own models and every write still goes through its commands, so AD-5 and AD-14 hold. AD-14 is about *what* editorial does (it acts through commands), not which module the ModelAdmin is in. `editorial` stays empty until the review queue. |
| **R2** | How to register or switch to `crawl` when a ToS review needs an existing Source | `register_source` and `update_source` take an optional `tos_review`. For `crawl`, an **approved** review is required, and it is written as a `TosReview` row in the same transaction, after the Source insert or method change. Without one, or with a rejected one, the command raises `CrawlNeedsTosReviewError` and writes nothing. In admin, the form's `tos_approved` checkbox plus evidence URL supplies it. | A review references a Source (FK), so "review first, then register" is impossible for a new source. "Register as RSS, review, then switch" fails as well, because the switch resets the review (D13). Approving in the same transaction is the only path that keeps both rules. |
| **R3** | What "`tos_status` always equals the latest `TosReview` for the current method" means exactly | `record_tos_review` always reviews the source's **current** method; there is no method parameter. A method change resets the cache to `not_reviewed` (D13, as the AC says). The tested invariant is: **`tos_status` equals the decision of the latest review for the current method recorded since that method was last set, or `not_reviewed` if there is none.** | The AC's wording breaks on rss → api → rss: an old RSS approval still exists, but D13 says the reset invalidates it. Reusing old approvals would let a years-old crawl approval silently revive. The test walks a scripted sequence that includes this case, with the expected value written out at each step. |
| **R4** | Changing a source's URL host | The cache is also reset when the URL's **host** changes. For a `crawl` source, a host change needs an approved `tos_review` in the same command, the same as R2. A path-only change keeps the review. | A ToS review covers a site's terms, and a new host is a different site. This matches the item-6 AC that a cross-host redirect "re-triggers the FR-17 ToS review". The comparison is between `urlsplit(url).hostname` values, lowercased, with `www.` stripped. |
| **R5** | Per-method cadence defaults and a floor | In `shared/constants.py`, `DEFAULT_INGESTION_CADENCE`: **rss, ics, jsonld, api and partnership 4h; crawl 24h; email_ics 24h**. `INGESTION_CADENCE_MIN = 15 minutes`; anything shorter is a `ValidationError`. A parity test checks that the map has exactly the `AcquisitionMethod` values. | The AC fixes only RSS at 4h. The PRD asks for 4h on high-priority sources and daily at worst. Crawl is the last resort, so it is polled politely. `email_ics` is pushed by a mailbox, and its cadence is only a fallback poll. The floor follows "no aggressive polling" (item 9). |
| **R6** | Registering the same feed twice | Refused with `SourceAlreadyRegisteredError` when an existing source has the same `domain.dedup.canonical_url`. The check also runs on a URL change. There is no DB constraint: it would need a new column and migration, and registration is a low-concurrency admin act, so the race is accepted and named. | Two sources on one feed would each bind every item (rule a), which doubles ingest work and pushes cross-source dedup onto rules b and c. |
| **R7** | Editing venues | Add the command **`set_venue_timezone`**, so editorial can fill in a venue's `tz` later (D14: "unknown until editorial adds it"). Name, city and country are fixed after registration. Renames are **deferred** to the editorial intent, because a rename has to decide whether the fingerprint changes. | Without it, the admin change page for a venue would have no command to call, and a venue registered without a tz could never rescue a partial-tier event. |
| **R8** | Django's `LogEntry` (admin "recent actions") | Turned off for the ingestion admin. `IngestionAuditEntry` is the only audit trail. | Admin writes `LogEntry` to `personal` in autocommit, *inside* the catalog transaction, so it would survive a catalog rollback. It would also be a second, unauthoritative history, holding source names as `object_repr`. |
| **R9** | ToS-review evidence and reviewer | An `approved` review needs a non-empty `evidence_url` (http(s), the ToS page). `record_tos_review` requires `Actor.user`; a system actor gets `PermissionDeniedError`. | FR-17 requires a *logged* review; the evidence is what makes it auditable. `TosReview.reviewed_by_id` is NOT NULL and must be a person. |
| **R10** | Pausing a paused source, resuming an active one | A no-op: it returns the source and writes **no** audit row. | Admin bulk actions over a mixed selection shouldn't fail, and the audit log records changes, not attempts. |

**Other validation (no decision needed):**
- `name` must be non-empty, at most 200 characters, and is stripped.
- `url` must be http(s) with a host, have no userinfo, and be at most 2,048 characters.
- `source_type`, `acquisition_method` and `tz_coverage` must be in their choices.
- `freshness_ttl_hours` must be at least 1.
- For venues, `country_code` must match `^[A-Za-z]{2}$` and is stored upper-case.
- A venue name with no tokens has an empty fingerprint, so it is refused.
- A venue `tz` goes through `domain.timezones.canonical_zone()`, and the canonical name is stored (`US/Pacific` is stored as `America/Los_Angeles`). An invalid one raises `InvalidTimezoneError` with `loc: ["tz"]`. This is the AC handed on from run-011.

### Deferrals (written into later items, not dropped)

- **`real-feeds-and-e2e-proof`:** an idempotent management command creates an `editorial` group with per-model permissions (AD-14), and the local operator logs in with it, not as superuser. This item uses Django's per-model permissions but seeds no groups.
- **`ingest-pipeline-and-lifecycle`:** the item-6 AC "refuses paused sources and crawl sources without approved ToS" gets the note "by calling `ensure_can_ingest(source)` (run-014)". Its cross-host-redirect AC is also connected to R4.
- **Intent brief, under "Still open":** venue rename and its effect on the fingerprint (R7) is for the editorial intent.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/services/source_registry.py` | `register_source`, `update_source`, `pause_source`, `resume_source`, `record_tos_review`, `ensure_can_ingest`, `clean_source_input`, `TosReviewInput`, errors |
| `backend/apps/ingestion/services/venue_registry.py` | `register_venue`, `set_venue_timezone`, `clean_venue_input`, errors |
| `backend/tests/ingestion/test_source_registry.py` | Source and ToS commands, the FR-17 guard, the `tos_status` invariant sequence, rollback |
| `backend/tests/ingestion/test_venue_registry.py` | Venue commands |
| `backend/tests/ingestion/test_admin.py` | The admin through the test client |
| `backend/tests/architecture/test_no_direct_writes.py` | A scan of `apps/*/admin.py` and `apps/*/api.py`, plus planted violations |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/ingestion/admin.py` | `CommandAdmin` base and the six ModelAdmins described above |
| `backend/config/urls.py` | `path("admin/", admin.site.urls)` |
| `backend/config/settings.py` | Comment only: `/admin/` is now routed |
| `backend/shared/constants.py` | `DEFAULT_INGESTION_CADENCE`, `INGESTION_CADENCE_MIN` (stdlib only) |
| `backend/tests/architecture/checkers.py` | `direct_write_calls(source)` |
| `.specs-fire/standards/coding-standards.md` | Source registry commands, admin through commands, no admin `LogEntry`, the no-direct-writes scan |
| `.specs-fire/intents/event-catalog-ingestion/work-items/ingest-pipeline-and-lifecycle.md`, `real-feeds-and-e2e-proof.md`, `brief.md` | The deferrals above |

There are no model changes and **no migration**. Admin ordering is set on the ModelAdmin, not on `Meta`, so `makemigrations --check` stays clean.

## Tests

| Test File | Coverage |
|-----------|----------|
| `tests/ingestion/test_source_registry.py` | **register:** happy path, with the audit row's actor, action, target and details checked. Cadence default for every method, with RSS = 4h asserted by value, not read from the constant. An explicit cadence is kept, and one below the floor is refused. Bad URL, userinfo, bad choice and duplicate canonical URL are refused.<br>**crawl:** without a review it is refused, and the test asserts no Source, TosReview or audit row exists. A rejected inline review is refused too. An approved one gives `tos_status = approved`, one TosReview for `crawl` and two audit rows.<br>**update:** field changes and audit details. A no-op writes no audit row. A non-editable or unknown key is refused. A method change resets `tos_status`. Switching to crawl is refused without a review and allowed with one; crawl → api is always allowed. A host change on a crawl source is refused without a review, while a path-only change keeps `approved`.<br>**pause/resume:** status and audit row; the second call is a no-op with no new row.<br>**record_tos_review:** the current method is used, the cache is updated, a system actor is refused, and an approval without evidence is refused.<br>**Invariant:** the scripted R3 sequence (rss approve → api → rss → reject → approve → crawl with review → rss).<br>**`ensure_can_ingest`:** paused, crawl not reviewed and crawl rejected are refused; crawl approved and rss not reviewed are allowed.<br>**Same transaction** (`transaction=True`): with `write_audit` patched to raise, `register_source` leaves no Source row, and `update_source` leaves the old values. |
| `tests/ingestion/test_venue_registry.py` | Happy path, the audit row and the fingerprint (equal to `domain.dedup.venue_fingerprint`). `US/Pacific` is stored as `America/Los_Angeles`. `Mars/Olympus` raises `InvalidTimezoneError` with `loc ["tz"]` and leaves no row. A duplicate fingerprint ("The Fillmore" vs "Fillmore") is refused. An empty name and a bad country code are refused. `set_venue_timezone` sets the tz and writes an audit row, and refuses a bad tz. |
| `tests/ingestion/test_admin.py` | Uses Django's test `Client` with a staff superuser in `personal`:<br>• An add POST creates the Source, and an audit row with `actor_id == user.id` and `actor_label == ""` proves the command ran (a plain `obj.save()` writes no audit row).<br>• A change POST gives an `update_source` row with `changes`.<br>• A crawl add without `tos_approved` re-renders with a form error and creates nothing; with it, the TosReview exists.<br>• The delete view returns 403, the row survives and `delete_selected` is not offered.<br>• The pause action works.<br>• Venue add with a bad tz shows a form error.<br>• TosReview add calls `record_tos_review`.<br>• The Event, EventStateChange and audit add pages return 403, and their change pages have no save button.<br>• The audit changelist shows the username.<br>• The `LogEntry` count is unchanged after a save (R8).<br>• The changelists for all six admins render (200). |
| `tests/architecture/test_no_direct_writes.py` | Every `apps/*/admin.py` and `apps/*/api.py` makes no `.save()`, `.create()`, `.update()`, `.delete()`, `bulk_*`, `get_or_create()` or `update_or_create()` call. Planted sources prove each form is caught, and that `refresh_from_db()` and `admin.site.register()` are not flagged. |
| `tests/shared/…` (existing file, or new `test_constants.py`) | `DEFAULT_INGESTION_CADENCE` has exactly the `AcquisitionMethod` values, and each is at least `INGESTION_CADENCE_MIN`. |

## Technical Details

- **Gates:**
  - `make lint-backend`
  - `make manage ARGS="check"`
  - `make manage ARGS="makemigrations --check --dry-run"`
  - `make coverage-backend` (≥ 80% overall, 100% `domain/`; `domain/` is untouched)
- **Import contracts:** `apps.ingestion.admin` imports `apps.ingestion.models` and `apps.ingestion.services` (same app) and `get_user_model()`, with no `identity.models` import. `shared.constants` stays stdlib-only, using string keys rather than the model enum.
- **AD-3:** the admin's username lookup is a read on `personal`, composed in the application layer. Nothing about the user is stored in `catalog`.
- **AD-9:** every source string is shown through admin auto-escaping. Nothing is marked safe.
- **Logging:** `pause_source` logs `WARNING "Source paused"` with `source_id`, which is already allowlisted. No other command logs, because the audit row is the record.

---
*Plan approved at Checkpoint 1. Execution follows.*
