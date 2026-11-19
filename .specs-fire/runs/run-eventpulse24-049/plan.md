---
run: run-eventpulse24-049
work_item: time-bomb-tests-remainder
intent: traceability-gap-closure
mode: confirm
checkpoint: plan
approved_at: pending
---

# Implementation Plan: The time bombs run 039 did not reach

## Approach

**Test-only.** Eight hard-coded `datetime(2026, 11, 20, 2, 0, tzinfo=UTC)` call sites in
`tests/delivery/test_preferences_api.py` become `future_local(...)` — the helper this file
already has, written by run 039 for exactly this failure, and applied then to only two of
its ten call sites.

No production code changes. This is a defect in the tests, not in the behaviour they guard.

## The damage, surveyed

Today is 2026-11-19 ~09:50 UTC. The event is pinned at 2026-11-20 02:00 UTC, so a `1d` slot
falls at 2026-11-19 02:00 UTC (**past**) and `1hr` at 2026-11-20 01:00 UTC (future for
~15 more hours). Every slot further out — `2d`, `5d` — is long past.

| Test | Plan | Rows it expects | Rows it gets today | State |
|---|---|---|---|---|
| `test_putting_the_delivery_time_moves_the_pending_reminder_rows_too` | `["1d"]` | 1 | 0 | **fails** |
| `test_a_sent_row_is_never_touched` | `["1d"]` | 1 | 0 | **fails** |
| `test_a_cancelled_row_is_never_touched` | `["1d"]` | 1 | 0 | **fails** |
| `test_changing_the_default_plan_does_not_touch_the_existing_per_event_plans` | `["1d","1hr"]` | 2 | 1 | passes, proves half |
| `test_the_keys_are_unchanged_across_ten_successive_changes` | `["1d","1hr"]` | 2 | 1 | passes, proves half |
| `test_the_row_count_does_not_change_when_the_window_changes` | `["1d","1hr"]` | 2 | **1 (measured)** | passes, proves half |
| `test_the_rewrite_reads_the_zone_once_not_once_per_row` | `["1d","2d","5d","1hr"]` vs `["1d"]` | 4 vs 1 | **1 vs 0** | passes, proves nothing |

**The last one is the worst.** Its entire purpose is that the query count does not grow with
a user's reminders — a four-row user against a one-row user. It is currently comparing a
**one-row** user against a **zero-row** user, and asserting the difference is ≤ 6. The N+1
property it exists to defend is not being exercised at all.

**And tonight it gets worse quietly.** Once the clock passes 2026-11-20 01:00 UTC, the
`1hr` slot goes past too. The four "passes, proves half" tests become `0 == 0` — green,
and asserting nothing.

## Files to Create

| File | Purpose |
|------|---------|
| (none) | |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/tests/delivery/test_preferences_api.py` | 8 call sites → `future_local`; add explicit row-count assertions to the four tests that currently compare a count to itself |
| `.specs-fire/.../work-items/time-bomb-tests-remainder.md` | frontmatter → completed |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/delivery/test_preferences_api.py` | The same 32 tests, now actually exercising the rows they name. Four gain an assertion that the expected number of pending rows exists **before** the behaviour under test runs. |

## Technical Details

### The replacement preserves the local wall clock exactly

`2026-11-20 02:00 UTC` is **`2026-11-19 18:00` in `America/Los_Angeles`** (PST, UTC-8).
So the replacement is an **18:00 local** start, not an 02:00 one:

```python
start_utc=future_local(days_ahead=N, hour=18).astimezone(UTC)
```

**This matters because of quiet hours.** The default window is 22:00–08:00 local. An 18:00
local start puts the `1d` slot at 18:00 two days earlier and `1hr` at 17:00 — both outside
the window, so neither is deferred. That is what the current literal produces. Writing
`hour=2` instead would put slots inside the window, they would defer to 08:00, and these
tests would quietly start proving something else.

### `days_ahead` per test, chosen so every slot is future

| Tests | Furthest slot | `days_ahead` |
|---|---|---|
| The six using `["1d"]` or `["1d","1hr"]` | 1 day | **3** (the value run 039 chose) |
| `test_the_rewrite_reads_the_zone_once_not_once_per_row` | `5d` | **7** |

Both events in the zone test use the same `days_ahead`, so the four-row and one-row users
are compared on equal footing — which is the whole point of that test.

### The guard that stops this recurring

Four of these tests compare a before-count to an after-count. That shape is **self-nulling**:
when the fixture stops minting, both sides go to zero together and the test passes. So each
gains an explicit assertion that the rows exist first:

```python
count_before = pending_of(user).count()
# **Not a formality.** This assertion is what keeps the comparison below meaningful:
# `before == after` is satisfied by `0 == 0`, so a fixture that stopped minting would
# leave this test green and empty — which is how these tests came to be rewritten.
assert count_before == 2
```

That is the cheap version of the guard the work item asks for, and it is the assertion that
would have caught this in October instead of today.

### Verification

1. The three failing tests pass.
2. The zone test compares **four** rows against **one**, asserted explicitly.
3. `grep -n "datetime(2026" tests/delivery/test_preferences_api.py` returns nothing.
4. Full backend suite green but for nothing new.
5. `ruff check` / `ruff format --check` / `lint-imports` clean.
6. **A clock probe:** re-run the suite with the system date advanced past the old literal
   to prove the fix is time-independent rather than merely currently-passing.

## Based on Work Item

Reference: `.specs-fire/intents/traceability-gap-closure/work-items/time-bomb-tests-remainder.md`

---
*Plan approved at checkpoint. Execution follows.*
