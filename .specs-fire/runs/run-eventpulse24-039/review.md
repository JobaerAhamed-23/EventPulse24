---
run: run-eventpulse24-039
work_item: time-bomb-tests
intent: traceability-gap-closure
date: 2026-11-17
---

# Code Review: Six tests that pass only before a date that has now passed

## The diagnosis held, and the file said so itself

The e2e file's own comment claimed the HTTP journeys *"use an event far enough ahead that
the wall clock cannot overtake it"*, and `START_UTC`'s comment claimed it was *"two days
past the wall clock, so the Detail endpoint's `now`-bounded read still finds the event
however long after the suite was written it is run"*. Both sentences described the right
intent; both were false, because the anchor was a literal. **The repair makes the comments
true rather than rewriting them** — they are kept, with a note recording what went wrong on
2026-11-17 so the next reader does not have to re-derive it.

## Decisions taken

**1. Relative fixtures, not a frozen clock.** These tests mint through the real API on
purpose; freezing time around an HTTP call is a heavier tool that can hide a genuine clock
dependency in the code under test.

**2. `NOW` steps back a day when the suite runs before 08:00 local.** 08:00 is deliberate —
it sits outside the default 22:00–08:00 Quiet Hours window, so a reminder minted at `NOW`
is not deferred and the journeys measure what they mean to. Without the step-back, a suite
run at 06:00 would put `NOW` two hours *ahead* of the real clock, and a notice written
"later than now" can be filtered out of a `now`-bounded read.

**3. Local wall clocks, converted — never UTC arithmetic.** The deferral is about local
times (22:30 inside the window, pushed to 08:00). A UTC offset computed once drifts by an
hour across a DST boundary. 22:30, 23:30 and 08:00 exist on every day of the year, because
transitions happen at 02:00.

**4. My own new file was repaired too.** `test_pulse_ping_control.py`, written earlier in
this same intent, pinned `datetime(2026, 11, 17, 12, 0)` and drove HTTP. Shipping a new
time bomb inside the work item opened to remove time bombs would have been absurd.

## Verdict

**Approved.** The repair is proved non-vacuous by mutation rather than by assertion, and
the remaining exposure is listed rather than implied.
