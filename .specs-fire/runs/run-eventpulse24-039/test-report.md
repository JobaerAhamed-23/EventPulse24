---
run: run-eventpulse24-039
work_item: time-bomb-tests
intent: traceability-gap-closure
date: 2026-11-17
---

# Test Report: Six tests that pass only before a date that has now passed

## Result

**The backend suite is 0 failed for the first time in this intent.**

```
7314 passed in 295.01s
```

Previously 7308 passed / 6 failed. No test was deleted, skipped or weakened — the six were
repaired and the count rose by the six now passing.

## What changed

| File | Change |
|---|---|
| `tests/e2e/test_state_change_proof.py` | `NOW` and `START_UTC` anchored to the real calendar instead of literals — **the only two literal dates in the file**, everything else derived from them |
| `tests/delivery/test_preferences_api.py` | A `future_local` helper; the two failing tests build their fixture and their expectations through it |
| `tests/delivery/test_pulse_ping_control.py` | **My own file from earlier today**, carrying the same defect — `NOW` now taken from the real clock |

## The assertions were not weakened — proved, not asserted

The work item warned that a "fix" which stops exercising the deferral is a deletion wearing
a repair's clothes. So the repair was checked by **mutation**: changing the expected
deferral hour from 08:00 to 09:00 made the test fail at the right line, and reverting it
made it pass again. The test still proves what its docstring claims — that a row deferred
into Quiet Hours comes back to its own hour when the window stops covering it, and that
`slot_at` is what makes that possible.

The expectations are still exact instants. They are now expressions over the anchor
(`slot_local.astimezone(UTC)`) rather than literals, not looser comparisons.

## The scan the work item asked for

**20 test files combine a pinned `datetime(202x, …)` with a real-clock HTTP path.** All
currently pass — their dates are far enough ahead, or the path does not care — so none is
failing today, and none was changed here beyond the three above.

```
tests/personalization/: test_calendar_manual_sync, test_calendar_connect_api, test_browse_api,
  test_timeline, test_dismissals_api, test_digest_opt_out_seam, test_conflict_list,
  test_personal_events_api, test_saved_public_conflict_resolution
tests/editorial/: test_admin_queue, test_access
tests/identity/: test_export_api, test_billing_webhooks, test_billing_account_api
tests/delivery/: test_reminder_plan_api, test_quiet_hours_pro_api, test_notices_api
tests/e2e/: test_save_race
```

**This is a list, not a verdict.** A pinned date is only a bomb when the fixture has to be
in the future *and* something on the path reads the real clock. Confirming which of these
twenty qualify is its own piece of work, and worth doing before one of them fails on a
morning when nobody has the context this run built.

## Gates

| Gate | Result |
|---|---|
| `pytest` | **7314 passed, 0 failed** |
| `ruff check` | All checks passed (1 import-sort error found and fixed) |
| `ruff format` | clean |
| `lint-imports` | 19 kept, 0 broken |

## Not covered

- **The other 18 candidate files were listed, not audited.** See above.
- **No guard against the pattern returning.** Nothing stops the next person writing a
  literal future date against an HTTP path. A lint rule or a fixture convention would, and
  is the obvious follow-up.
