---
run: run-eventpulse24-049
work_item: time-bomb-tests-remainder
intent: traceability-gap-closure
generated: 2026-11-19
status: passed
---

# Test Report: The time bombs run 039 did not reach

## Summary

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| Backend (full suite) | **7495** | **0** | 7 |
| `tests/delivery/test_preferences_api.py` | 32 | 0 | 0 |

**The whole backend suite is green.** It was 7492 passed / 3 failed at the start of this
run, and those three failures had been reported as "pre-existing and unowned" by four
consecutive runs (041, 046, 047, 048).

## What was wrong

Not a regression — a **time bomb**, and a partially-exploded one.

Eight call sites pinned an event to `datetime(2026, 11, 20, 2, 0, tzinfo=UTC)` and then
scheduled reminders **through the real API**, which schedules against `timezone.now()`
rather than the module's pinned `NOW`. As the real clock advanced past each slot, the slot
stopped being minted.

| Test | Plan | Should mint | Minted today | Was |
|---|---|---|---|---|
| `test_putting_the_delivery_time_moves_the_pending_reminder_rows_too` | `["1d"]` | 1 | 0 | **failing** |
| `test_a_sent_row_is_never_touched` | `["1d"]` | 1 | 0 | **failing** |
| `test_a_cancelled_row_is_never_touched` | `["1d"]` | 1 | 0 | **failing** |
| `test_changing_the_default_plan_does_not_touch_the_existing_per_event_plans` | `["1d","1hr"]` | 2 | 1 | passing, half-proving |
| `test_the_keys_are_unchanged_across_ten_successive_changes` | `["1d","1hr"]` | 2 | 1 | passing, half-proving |
| `test_the_row_count_does_not_change_when_the_window_changes` | `["1d","1hr"]` | 2 | **1 (measured)** | passing, half-proving |
| `test_the_rewrite_reads_the_zone_once_not_once_per_row` | `["1d","2d","5d","1hr"]` vs `["1d"]` | 4 vs 1 | **1 vs 0** | passing, proving nothing |

**The silent failures were the more serious half.** Three red tests get looked at. Four
green ones that quietly stopped asserting do not — and the last of them exists specifically
to defend an N+1 property, which it was not exercising at all.

## Acceptance Criteria Validation

- ✅ **All eight call sites use `future_local`** — six at `days_ahead=3`, two at `days_ahead=7` (the zone test's furthest slot is `5d`). Both events in the zone test use the same offset, so the four-row and one-row users are compared on equal footing.
- ✅ **The original local wall clock is preserved** — `2026-11-20 02:00 UTC` is `2026-11-19 18:00` in `America/Los_Angeles` (PST), so the replacement is `hour=18`, not `hour=2`. Every slot stays outside the default 22:00–08:00 quiet window exactly as before; none of these tests silently became a deferral test.
- ✅ **The three failing tests pass.**
- ✅ **The degraded tests now assert on the rows they claim** — explicit `== 2`, `== 4` and `== 1` counts before the behaviour under test runs.
- ✅ **No hard-coded future date remains** — the two surviving `datetime(2026, ...)` literals are `NOW` (the pinned instant) and a `mint_digest(..., now=NOW)` call that bypasses the real scheduler and is deterministic by construction. Both correctly left alone.
- ✅ **No non-test file changed.**

## The fix was probed against the clock, not just run today

A fix for a time bomb that is only verified at one instant is not verified.

| Probe | Result |
|---|---|
| `future_local`'s base clock advanced **+400 days** | **32 passed** — the fixtures move with the clock |
| `future_local`'s base clock moved **−400 days** (the time-bomb condition: events in the past) | **9 failed** |
| Restored | 32 passed |

The second probe is the important one. Under the old code that condition produced **three**
failures and four quiet passes. It now produces **nine** failures — the new row-count
assertions catch precisely the tests that used to rot in green.

## Tests Changed

`backend/tests/delivery/test_preferences_api.py` — 8 call sites converted, 5 assertions
added:

```python
count_before = pending_of(user).count()
# **Not a formality.** The comparison below is satisfied by `0 == 0`, so a fixture
# that stopped minting would leave this test green and asserting nothing. …
assert count_before == 2, "the `1d` and `1hr` slots must both be pending"
```

That shape — comparing a before-count to an after-count — is **self-nulling**: when the
fixture stops producing rows, both sides reach zero together and the test passes. The
assertion is what makes the comparison mean something, and it is what would have caught
this in October rather than today.

## Verification performed

| Check | Result |
|---|---|
| Full backend suite | **7495 passed, 0 failed**, 7 skipped |
| `tests/delivery/test_preferences_api.py` | 32 passed |
| Clock probe +400d / −400d | 32 passed / 9 failed, as designed |
| `grep "datetime(2026"` | 2 legitimate literals, 0 time bombs |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 691 files already formatted |
| `lint-imports` | 20 contracts kept, 0 broken |
| Non-test files changed | **none** |

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| `test_the_rewrite_reads_the_zone_once_not_once_per_row` was comparing a 1-row user to a 0-row user | **High** | **Fixed.** Its purpose is that query count does not grow with reminders; it was asserting a difference of ≤6 between one row and none. Now asserts 4 and 1 explicitly before measuring. |
| Four tests used a self-nulling before/after comparison | **High** | **Fixed** with explicit counts. This shape is the root cause of the silent half of the failure, not the literal date. |
| 8 of 10 call sites were left behind by run 039 | Medium | **Fixed.** Run 039 built `future_local` and converted two. |

## Ready for Completion

- [x] All tests passing — **the full backend suite is green, 0 failures**
- [x] Coverage target met — every converted test probed against a moved clock
- [x] All acceptance criteria validated (6 of 6)
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-049*
