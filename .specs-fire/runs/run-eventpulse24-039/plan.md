---
run: run-eventpulse24-039
work_item: time-bomb-tests
intent: traceability-gap-closure
mode: confirm
checkpoint: plan
approved_at: 2026-11-17
---

# Implementation Plan: Six tests that pass only before a date that has now passed

## Approach

Anchor the expired fixtures to the **real clock** instead of to literals, and derive every
expected instant from that anchor rather than writing it out. No assertion gets weaker.

**The e2e file already states the intent this restores.** Its own comment at line 84 reads:
*"the services on this path all take `now` as an argument; the two that do not are read
through HTTP, and the HTTP journeys use an event **far enough ahead that the wall clock
cannot overtake it**."* The author saw the hazard and answered it by starting the event two
days after `NOW` — but `NOW` is a literal, so "far enough ahead" was only ever true for a
while. Making the anchor relative is not a new idea; it is the stated intent, implemented.

**The whole file has exactly two literal dates** (`NOW` at line 87, `START_UTC` at line 99)
and everything else derives from them, so the change is two lines plus their comments.

**The delivery pair needs a helper, not a constant**, because its arithmetic is about wall
clocks: an event at **23:30 local**, whose `1hr` slot at **22:30** falls inside the default
22:00–08:00 window and is therefore deferred to **08:00 the next morning**. Those three
local times are the test, so the fixture builds them as local times on a future day and the
expectations become expressions over the same anchor.

**Why not freeze the clock.** These tests mint through the real API on purpose — that is
what makes them worth having — and freezing time around an HTTP call is a heavier tool that
can hide a genuine clock dependency in the code under test. Relative fixtures keep the test
honest about what it proves.

## Files to Modify

| File | Changes |
|------|---------|
| `backend/tests/e2e/test_state_change_proof.py` | `NOW` → the real clock; `START_UTC` → 19:00 local, two days on |
| `backend/tests/delivery/test_preferences_api.py` | A `_future_local` helper; the two failing tests build and assert through it |

## Tests

No new test files. The six existing tests are the deliverable: they must pass **and still
prove what their docstrings claim**.

## Technical Details

**The expectations stay exact.** The delivery pair asserts precise instants because the
deferral arithmetic is the point — `slot_at` is the fact that makes a Quiet Hours write
work at all, and a row that only remembered its pushed-to time could not come back. Those
become `slot_local.astimezone(UTC)` and `(next morning at 08:00).astimezone(UTC)`, not
looser comparisons.

**DST is why the fixture builds local times and converts**, rather than doing UTC
arithmetic. 23:30, 22:30 and 08:00 all exist on every day of the year; a transition happens
at 02:00, so none of these three can land in a gap or a fold.

**`last_seen_at=NOW` must move with `START_UTC`.** The e2e fixture pins it deliberately —
FR-14's staleness bound measures from it, and an event built with the column's wall-clock
default would be dropped by the catalog read before the save ever saw it. It already reads
`NOW`, so a relative `NOW` carries it along; this is noted so a later edit does not split
the pair.

**A scan for the same pattern elsewhere** is part of the item: any other test pinning a
future literal that will expire gets listed, even if not fixed here.

## Verification

`make test-backend` must report **0 failed**. `make lint-backend`. Then the six are run
again on their own to confirm they fail for the right reason if the anchor is wrong — i.e.
that they still exercise the deferral rather than passing vacuously.

---
*Plan approved at checkpoint (the item was chosen with this approach stated in it).*
