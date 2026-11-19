---
id: time-bomb-tests-remainder
title: The time bombs run 039 did not reach — eight hard-coded dates in the
  preferences suite
intent: traceability-gap-closure
complexity: low
mode: confirm
status: completed
depends_on:
  - time-bomb-tests
created: 2026-11-19
run_id: run-eventpulse24-049
completed_at: 2026-11-19T16:01:32.325Z
---

# Work Item: The time bombs run 039 did not reach

## Description

**Found on 2026-11-19 while diagnosing three failures that had been reported as
"pre-existing, unowned" by four consecutive runs (041, 046, 047, 048).** They are not a
regression and never were: they are a time bomb that went off.

`tests/delivery/test_preferences_api.py` builds events at a hard-coded
`datetime(2026, 11, 20, 2, 0, tzinfo=UTC)` and then schedules reminders **through the real
API**, which schedules against `timezone.now()` — not against the module's pinned `NOW`.
As the real clock advances, the slots fall into the past one by one and stop being minted.

| Slot | Falls at | State on 2026-11-19 ~09:50 UTC |
|---|---|---|
| `1d` | 2026-11-19 02:00 UTC | **past** — no row minted |
| `1hr` | 2026-11-20 01:00 UTC | future, for about 15 more hours |

### Three tests fail, and two rot silently — which is worse

**Failing** with `ScheduledSend.DoesNotExist`, because they call `pending_of(user).get()`
on a `["1d"]` plan that mints nothing:

- `test_putting_the_delivery_time_moves_the_pending_reminder_rows_too`
- `test_a_sent_row_is_never_touched`
- `test_a_cancelled_row_is_never_touched`

**Passing while proving less than they claim**, because they compare a before-count to an
after-count and both shrink together:

- `test_the_keys_are_unchanged_across_ten_successive_changes`
- `test_the_row_count_does_not_change_when_the_window_changes`

**Measured, not inferred:** `test_the_row_count_does_not_change_when_the_window_changes`
saves a plan with **two** slots (`["1d", "1hr"]`) and sees **one** pending row today. It
passes. Once the clock passes 2026-11-20 01:00 UTC it will see **zero**, and `0 == 0`
passes just as well — so a test whose stated purpose is *"the rewrite never mints"* will be
asserting nothing at all, in green.

### The fix already exists in the file

`future_local()` (line 56) was written by `time-bomb-tests` (run 039) and its docstring
describes this exact failure:

> They used to build an event on a fixed date; once the wall clock passed it the event was
> in the past, no reminder was minted at all, and both failed on
> `ScheduledSend.DoesNotExist` — a time bomb, not a regression.

Run 039 converted **two** call sites (lines 289 and 327). **Eight hard-coded dates across
five tests were left behind**, at lines 434, 525, 552, 573, 594, 616, 731 and 743.

**This item is the remainder of that work**, and the reason it is a separate item rather
than a silent extension is that four runs reported these failures as "pre-existing and
unowned" without diagnosing them. A failure nobody owns gets re-reported until it becomes
scenery.

## Acceptance Criteria

- [ ] All eight hard-coded `datetime(2026, 11, 20, ...)` call sites use `future_local`, so no test in this file depends on the real clock not having passed a literal date
- [ ] **The original local wall clock is preserved**: `2026-11-20 02:00 UTC` is `2026-11-19 18:00` in `America/Los_Angeles`, so the replacement is an 18:00 local start, not an 02:00 one. A reminder's relationship to the default 22:00–08:00 quiet window must not change
- [ ] The three failing tests pass
- [ ] **The two silently-degraded tests are shown to be asserting on the rows they claim** — a `["1d", "1hr"]` plan yields **two** pending rows, asserted explicitly rather than compared to a count that could be zero
- [ ] `grep` finds no remaining hard-coded future date in this file
- [ ] No change to any non-test file: this is a defect in the tests, not in the behaviour they guard

## Technical Notes

**Do not simply bump the literal to a later date.** That re-arms the bomb with a longer
fuse and is the change that created this item. `future_local` exists precisely so the date
is computed from `timezone.now()`.

**`days_ahead=3` is the established choice** in this file's two converted tests — far
enough ahead that neither a `1d` nor a `1hr` slot can be in the past.

**Watch the quiet-hours interaction.** The default window is 22:00–08:00 local. An 18:00
local start puts the `1d` slot at 18:00 two days earlier and the `1hr` slot at 17:00 —
both outside the window, so neither is deferred. That is the behaviour the current literal
produces, and the replacement must keep it, or these tests start proving something else.

**Consider whether a guard is possible.** These tests were green for weeks, then red, and
two will be green-but-empty tonight. A test asserting a non-zero row count before the
behaviour under test runs is the cheap version of that guard, and the acceptance criteria
ask for it.

## Dependencies

- time-bomb-tests (run 039 — this is the remainder of that work)
