---
id: time-bomb-tests
title: Six tests that pass only before a date that has now passed
intent: traceability-gap-closure
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-17
run_id: run-eventpulse24-039
completed_at: 2026-11-17T15:56:13.029Z
---

# Work Item: Six tests that pass only before a date that has now passed

## Description

Six tests fail on a clean checkout of `main`, and they are **time bombs**: each pins an
absolute date that the real clock has now moved past. They were green when written and
nothing in the product broke them — the calendar did.

| Test | Symptom |
|---|---|
| `tests/delivery/test_preferences_api.py::test_the_window_write_rewrites_the_pending_rows_due_at` | `ScheduledSend.DoesNotExist` |
| `tests/delivery/test_preferences_api.py::test_a_deferred_row_keeps_the_instant_it_was_for` | `ScheduledSend.DoesNotExist` |
| `tests/e2e/test_state_change_proof.py::TestTheStripAndTheBanner` (4 tests) | `KeyError: 'personal'` |

**The delivery pair.** The module pins `NOW = 2026-11-10` and builds a personal event
starting `2026-11-14 07:30 UTC`. But `save_plan` mints the reminder through the **real
API**, which uses `timezone.now()` — not the module's `NOW`. While the wall clock was
before the 14th the event was upcoming and a row was minted; today it is in the past, no
row is minted, and `pending_of(user).get()` raises.

**The e2e four.** Same shape, one layer further out. The fixture's own docstring says it
builds *"a published, **upcoming** catalog event"* and pins `last_seen_at=NOW` precisely so
FR-14's staleness bound measures against the test clock. The start times derive from
`NOW = 2026-11-10`, so the event is now in the past, the catalog's public read drops it,
`GET /api/events/{id}` answers **404** (visible as a `Not Found` warning in the captured
log), and `detail.json()["personal"]` raises `KeyError` on the error body.

**This is diagnosis, not yet a proven fix.** The evidence is strong — past-dated fixtures,
a 404 on the read, a fixture docstring that states the event must be upcoming — but the
repair should be confirmed by making the dates relative and watching all six go green,
not by assuming.

**Why it matters beyond six red tests.** A suite with permanently-red tests teaches
everyone to read "6 failed" as normal, and the next real regression hides in that number.
Two runs in this intent have now had to stash the tree and re-run on a clean checkout just
to prove their own changes innocent.

## Acceptance Criteria

- [ ] All six tests pass, and the full backend suite is **0 failed**.
- [ ] The fixtures no longer depend on the real date: either the clock is frozen for these tests, or the fixture dates are derived relative to a reference instant rather than written as literals.
- [ ] **The behaviour under test is unchanged.** The delivery pair must still prove what their docstrings say — that a deferred row returns to its own hour when the window stops covering it, and that the row remembers the instant it was *for* (`slot_at`), not merely the instant it was pushed to. A "fix" that stops exercising the deferral is a deletion wearing a repair's clothes.
- [ ] The e2e four still drive the real journey end to end; the event is upcoming **because the fixture makes it so**, not because the suite happens to run before a date.
- [ ] A comment at each changed fixture says why the date is relative, so the next person does not helpfully pin it again.
- [ ] A scan for the same pattern elsewhere: any other test pinning a future literal that will expire is listed, even if not fixed in this item.

## Technical Notes

**Prefer making the fixture's dates relative to freezing the world.** The delivery tests
deliberately exercise the *real* mint path through the API — that is what makes them worth
having — and freezing time around an API call is a heavier tool that can hide a genuine
clock dependency in the code under test. Deriving the fixture's instants from a reference
that moves with the suite keeps the test honest about what it is proving.

**Check `last_seen_at` when moving the e2e dates.** The fixture pins it to `NOW` on purpose:
FR-14's staleness bound measures from it, and an event built with the column's wall-clock
default would be dropped by the catalog read before the save ever saw it. Whatever reference
the start time moves to, that pin has to move with it or the tests fail for a second,
differently-confusing reason.

**Do not weaken the assertions to get green.** The delivery pair asserts exact instants
(`2026-11-14 16:00 UTC`, then `06:30 UTC`) because the deferral arithmetic is the point.
Those become expressions over the new reference, not looser comparisons.

## Dependencies

(none)
