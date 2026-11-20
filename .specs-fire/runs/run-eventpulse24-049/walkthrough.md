---
run: run-eventpulse24-049
work_item: time-bomb-tests-remainder
intent: traceability-gap-closure
generated: 2026-11-19
mode: confirm
---

# Walkthrough: The time bombs run 039 did not reach

## What this run did

**Took the full backend suite from 3 failures to 0** — 7495 passed, nothing red — and in
the process found that the three red tests were the *smaller* half of the problem.

No production code changed. The defect was in the tests, not in the behaviour they guard.

## The three failures were never a regression

Four consecutive runs (041, 046, 047, 048) reported them as *"pre-existing, verified
unrelated, unowned"*. Accurate every time, and never diagnosed.

They are a **time bomb**. Eight call sites pinned an event to
`datetime(2026, 11, 20, 2, 0, tzinfo=UTC)` and then scheduled reminders **through the real
API**, which schedules against `timezone.now()` — not the module's pinned `NOW`. As the
real clock advanced, each slot fell into the past and stopped being minted:

| Slot | Falls at | On 2026-11-19 ~09:50 UTC |
|---|---|---|
| `1d` | 2026-11-19 02:00 UTC | **past** — nothing minted → `ScheduledSend.DoesNotExist` |
| `1hr` | 2026-11-20 01:00 UTC | future, for ~15 more hours |

## The part nobody was looking at

Three tests failed loudly. **Four kept passing while asserting less and less.**

| Test | Should mint | Minted today |
|---|---|---|
| `test_changing_the_default_plan_does_not_touch_the_existing_per_event_plans` | 2 | 1 |
| `test_the_keys_are_unchanged_across_ten_successive_changes` | 2 | 1 |
| `test_the_row_count_does_not_change_when_the_window_changes` | 2 | **1 (measured)** |
| `test_the_rewrite_reads_the_zone_once_not_once_per_row` | **4 vs 1** | **1 vs 0** |

The last one is the worst in the file. Its entire purpose is that query count does not grow
with a user's reminders — a four-row user against a one-row user. It was comparing a
**one-row user against a none-row user** and asserting the difference was ≤ 6. The N+1
property it exists to defend was not being exercised at all.

**And tonight it would have got quietly worse.** Once the clock passed 2026-11-20 01:00
UTC, the `1hr` slot goes past too and all four become `0 == 0` — green, asserting nothing.

## The root cause is a test shape, not a date

These tests compare a before-count to an after-count. **That shape is self-nulling**: when
the fixture stops producing rows, both sides reach zero together and the test passes.

Converting the dates fixes today. Fixing the shape is what stops it recurring, so each
affected test now asserts the row count it depends on *before* the behaviour under test
runs:

```python
count_before = pending_of(user).count()
# Counted, not assumed — see `future_local` on why a before/after test must.
assert count_before == 2, "the `1d` and `1hr` slots must both be pending"
```

The rationale is stated once, on `future_local` — the helper run 039 built for exactly this
failure:

> A test that cannot tell the difference between "nothing changed" and "there was nothing"
> is not a test.

## What changed

| Change | Detail |
|---|---|
| 8 date literals → `future_local` | 6 at `days_ahead=3`, 2 at `days_ahead=7` (that test's plan reaches `5d`) |
| 5 row-count assertions | `== 2` ×3, `== 4`, `== 1` |
| 1 docstring | the self-nulling lesson, stated once |

**`hour=18`, not `hour=2`** — and this is the detail that would have broken the fix
silently. `2026-11-20 02:00 UTC` is `18:00` in `America/Los_Angeles`. Writing `hour=2`
would have put every slot inside the default 22:00–08:00 quiet window, deferring them to
08:00 the next morning. The tests would still pass — while quietly having become deferral
tests instead of the thing they were written for.

**Two `datetime(2026, …)` literals were deliberately left.** `NOW` is the pinned instant
the module measures from, and one call invokes `mint_digest(..., now=NOW)` directly,
bypassing the real scheduler. Neither depends on the wall clock.

## The fix was proved against the clock, not just run today

A fix for a time bomb verified at a single instant is not verified.

| Probe | Result |
|---|---|
| `future_local`'s base clock **+400 days** | **32 passed** — fixtures move with the clock |
| `future_local`'s base clock **−400 days** (events in the past) | **9 failed** |
| Restored | 32 passed |

The second probe is the one that matters. Under the old code that same condition produced
three failures and four quiet passes. It now produces **nine failures** — the new
assertions catch exactly the tests that used to rot in green.

## Also fixed this session, outside the run

`ruff check .` was failing on `F401 pytest imported but unused` in
`tests/identity/test_email_change_mails.py`, introduced by commit `d181391` (run 043).
Since `make lint-backend` runs `ruff check .`, **the backend lint gate was red on committed
code**. One-line removal; `ruff check` and `ruff format --check` are now both clean.

## The lesson worth keeping

Run 039 (`time-bomb-tests`) diagnosed this class of bug correctly, built `future_local`,
wrote a docstring that describes the failure precisely — and applied it to **2 of 10** call
sites. The remaining eight went off on schedule.

Four later runs then reported the symptom accurately without diagnosing it. The diagnosis
took about fifteen minutes once started. **A failure nobody owns gets re-reported until it
becomes scenery** — and here, four green tests were decaying beside the three red ones the
whole time.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-049*
