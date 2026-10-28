# Code Review Report

**Run**: run-eventpulse24-014
**Intent**: event-catalog-ingestion
**Reviewed**: 2026-10-28
**Files Reviewed**: 19

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 2 | 0 | 0 |
| Security | 0 | 1 | 0 |
| Architecture | 0 | 1 | 0 |
| Testing | 0 | 0 | 0 |
| **Total** | **2** | **2** | **0** |

**Tests Status**: Passing. After the fixes: 1476 passed, 99.03% overall, 100% `domain/`, 13 import contracts kept, `check` and `makemigrations --check` clean.

---

## Files Reviewed

**Code:**
- `backend/apps/ingestion/services/source_registry.py` (created)
- `backend/apps/ingestion/services/venue_registry.py` (created)
- `backend/apps/ingestion/admin.py` (modified)
- `backend/config/urls.py` (modified)
- `backend/config/settings.py` (modified, comment only)
- `backend/shared/constants.py` (modified)

**Tests:**
- `backend/tests/architecture/checkers.py` (modified)
- `backend/tests/architecture/test_no_direct_writes.py` (created)
- `backend/tests/ingestion/test_source_registry.py` (created)
- `backend/tests/ingestion/test_venue_registry.py` (created)
- `backend/tests/ingestion/test_admin.py` (created)
- `backend/tests/ingestion/test_domain_parity.py` (modified)
- `backend/tests/config/test_project.py` (modified)

**Docs and plans:**
- `.specs-fire/standards/coding-standards.md` (modified)
- `.specs-fire/intents/event-catalog-ingestion/brief.md` (modified)
- `.specs-fire/intents/event-catalog-ingestion/work-items/ingest-pipeline-and-lifecycle.md` (modified)
- `.specs-fire/intents/event-catalog-ingestion/work-items/real-feeds-and-e2e-proof.md` (modified)
- `.specs-fire/runs/run-eventpulse24-014/plan.md`, `test-report.md` (created)

---

## Auto-Fixed Issues

### 1. [Code Quality] Line too long (E501)
- **File**: `backend/tests/ingestion/test_source_registry.py:80`
- **Fix**: split one assertion into two.

### 2. [Code Quality] Line too long (E501)
- **File**: `backend/apps/ingestion/admin.py` (`SourceAdmin.get_fieldsets`, added by suggestion 1)
- **Fix**: bound the hidden-field tuple to a local name.

Ruff format also reformatted the new files. There is no behaviour change in any of these.

---

## Applied Suggestions (approved by the user)

### 1. [Security / AD-14] Approving a ToS review from the Source form bypassed `add_tosreview`

- **Found by:** reading `SourceForm`. **Confirmed by a probe:**
  - A staff user holding only `view_source` and `change_source` POSTed the Source change form with `acquisition_method=crawl` and the "Terms reviewed and approved" box checked.
  - The result: 302, one `TosReview` written and `tos_status = approved`.
  - So a user without the per-model grant for ToS records could approve crawling. AD-14 requires admin write access to be "granted per-model".
- **Fix:** user's choice: "Require `add_tosreview`".
  - `SourceAdmin.get_form` sets `form.can_review_tos = request.user.has_perm("ingestion.add_tosreview")`.
  - Without it, `get_fieldsets` hides the ToS input fields.
  - `SourceForm.clean()` adds an error to a forged `tos_approved`, and `tos_review()` returns `None`.
- **Tests:**
  - `test_source_tos_approval_without_add_tosreview_permission_refused`: field hidden, error shown, source still rss/not_reviewed, no review written.
  - `test_source_tos_approval_with_add_tosreview_permission_allowed`.
  - **Mutation probe:** forcing `can_review_tos = True` fails the refusal test.
- **Standards:** `coding-standards.md` now says that a form recording something governed by another model's permission checks that permission itself.

### 2. [Architecture] `ensure_can_ingest` on a stale row

- `ensure_can_ingest(source)` trusts the instance it is given. If the pipeline checks a copy read before it takes its run lock, a pause or ToS rejection committed in between would be missed.
- **Fix:** documentation only, since the pipeline doesn't exist yet. The item-6 AC now says to call it on the row it has **locked** for the run.

---

## Checked and found fine (probed or read, no change)

| Concern | Result |
|---|---|
| A view-only staff user opening the Source change page, which has non-model form fields shown read-only | Probe: 200 on the change page and the changelist. |
| The audit changelist evaluating `result_list` early | The sliced queryset caches its rows; the template reuses them. The username test proves the decoration survives. |
| A Venue change POST carrying `name` | Ignored: name is read-only after registration, and a test asserts the name is unchanged. |
| A Source change where nothing changed but "approve" is checked | Records a review of the current method with no `update_source` row. This is intended, and needs `add_tosreview` after fix 1. |
| `LogEntry` and `construct_change_message` | Both are off; `construct_change_message` returns `[]` because `save_related` doesn't save the view-only formsets. Found during testing (an `AttributeError` on `formset.new_objects`) and fixed before the test report. |
| Logging | Only `pause_source` logs, with `source_id` (allowlisted). No source content is logged. |
| AD-9 | Every source string is rendered through admin auto-escaping; nothing is marked safe. |

## Known limitations (accepted in the plan)

- **Duplicate-feed check (R6):** it compares against every registered source, with no DB constraint, so a race between two identical registrations is possible.
- **`direct_write_calls`:** syntactic only. It misses `save(obj)` and dynamically built calls, the same as the existing alias scan.
