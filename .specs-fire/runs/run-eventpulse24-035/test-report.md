---
run: run-eventpulse24-035
work_item: ai-cost-dashboard
intent: traceability-gap-closure
date: 2026-11-17
---

# Test Report: Make the AI cost rows readable — FR-29

## New tests

`backend/tests/adapters/test_llm_admin.py` — **12 tests, all passing.**

| Group | Holds |
|---|---|
| `TestTheDashboardIsReachable` | `AICostRow` is in `admin.site._registry`; a staff user gets `200` on the changelist. The superuser is in `personal` and the rows are in `catalog`, so the pair also proves the two aliases render on one page |
| `TestItIsReadOnly` | add / change / delete permissions all return `False`; `delete_model` and `delete_queryset` both raise `PermissionDenied`; the rendered changelist reports `has_add_permission is False`, so no add link is offered |
| `TestTheTotals` | the total sums cost **and** calls; **the total follows the filter** (`kind__exact=embedding` sums only that kind); an empty table totals `0` rather than `None`; the page title carries the spend |

**Why the filter test is the important one.** A sum over the unfiltered table printed under
a filtered heading would be worse than no total at all — it would answer a question nobody
asked, in a place that looks like it answers the one they did.

## Suite result

```
7287 passed, 6 failed in 291.12s
```

**The 6 failures are pre-existing and unrelated to this work.** Verified, not assumed: the
tree was stashed (`git stash -u`) and the same six were run against a clean checkout, where
they fail identically.

| Failing test | |
|---|---|
| `tests/delivery/test_preferences_api.py::test_the_window_write_rewrites_the_pending_rows_due_at` | pre-existing |
| `tests/delivery/test_preferences_api.py::test_a_deferred_row_keeps_the_instant_it_was_for` | pre-existing |
| `tests/e2e/test_state_change_proof.py::TestTheStripAndTheBanner` (4 tests) | pre-existing — `KeyError: 'personal'` |

They are **not** fixed here: this run's work item is FR-29, and silently repairing unrelated
failing tests inside it would make the run's diff describe something other than what it did.
They should be their own item. Note that `pulse-ping-control`, the next item in this intent,
touches `tests/delivery/test_preferences_api.py` — so the first two are worth looking at then.

## Gates

| Gate | Result |
|---|---|
| `pytest tests/adapters/test_llm_admin.py` | **12 passed** |
| `pytest` (full backend suite) | 7287 passed, 6 pre-existing failures |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 674 files already formatted |
| `lint-imports` | **19 contracts kept, 0 broken** |
| `manage.py check` | No issues (3 silenced) |

**`lint-imports` is the load-bearing gate for this change.** The plan recorded that
`adapters.llm` may not import `apps.ingestion.admin.ReadOnlyAdmin`, because the `layers`
contract makes `apps | adapters` independent siblings. The local read-only base is what keeps
all 19 contracts green; had the import been taken, this gate is the one that would have
failed.

## Not covered

- **No browser check of the rendered page.** Docker infra and the API are down, so the admin
  was exercised through Django's test client rather than looked at. The totals are asserted in
  `context_data`; the template renders them through the standard changelist, which is
  unmodified.
