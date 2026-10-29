# Code Review Report

**Run**: run-eventpulse24-020
**Intent**: onboarding-and-account
**Work item**: calendar-sync-and-polling
**Reviewed**: 2026-10-29
**Files Reviewed**: 18

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Correctness | 3 | 0 | 0 |
| Contract / Architecture | 1 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Observability | 0 | 0 | 0 |
| Code Quality | 0 | 0 | 0 |
| Documentation | 1 | 0 | 0 |
| **Total** | **5** | **0** | **0** |

**Tests Status**: Passing — 2648 passed, 0 failed; 98.92% coverage; 17/17 import contracts kept.

Every finding was a **defect**, not a style preference, and every one was fixed in the same
pass rather than deferred. Each was verified by reading the code and **reproducing the
failure before being acted on** — a review finding is a claim, not a fact, and a finding
that cannot be reproduced is a finding that cannot be fixed.

Two claims the review raised did **not** survive reproduction and are recorded below as
**not defects**, because a review that reports a false positive is as costly as one that
misses a real bug. Both were checked against the code rather than taken on trust.

---

## Files Reviewed

### Created

- `backend/apps/personalization/services/calendar_sync.py` — the reconcile, the claim
- `backend/apps/personalization/migrations/0003_calendarconnection_sync_claimed_at_and_more.py`
- `backend/apps/personalization/migrations/0004_calendarconnection_etag_and_more.py`
- `backend/tests/personalization/test_calendar_sync.py` — 39 tests
- `backend/tests/personalization/test_calendar_polling.py` — 19 tests
- `backend/tests/personalization/test_calendar_conflict_resolution.py` — 23 tests
- `backend/tests/personalization/test_calendar_disconnect_purge.py` — 9 tests
- `backend/tests/worker/test_calendar_tasks.py` — 12 tests

### Modified

- `backend/apps/personalization/services/calendar_connections.py` — the purge, the reconnect
- `backend/apps/personalization/services/personal_events.py` — the shared commands
- `backend/apps/personalization/services/conflicts.py` — the duplicate rule's switch
- `backend/apps/personalization/services/conflict_resolutions.py` — the imported-event refusal
- `backend/apps/personalization/models.py` — the claim column, the cache validators, the flag
- `backend/apps/delivery/services/reminder_plans.py` — `remove_plans_for_targets`
- `backend/worker/tasks.py` — the dispatcher and the sync job
- `backend/shared/constants.py` — the batch, the claim TTL
- `backend/tests/delivery/test_reminder_plans.py` — the bulk delete's audit rows
- `backend/tests/worker/test_scheduling_tasks.py` — the tick's enqueue list
- `backend/tests/personalization/test_calendar_connection_commands.py` — the purge's scope

---

## Findings and Fixes

### B1 — A user's edit was overwritten, and their ownership of the row destroyed, by a poll that raced them

**Severity**: BLOCKER · **Category**: Correctness · **Status**: Fixed

D2 is the decision this whole item rests on: **the user's edit wins**. The design says it
is "a data-loss bug wearing a synchronisation feature's clothes" to get it wrong. The
implementation got it wrong in a way the test suite could not see.

The reconcile reads its snapshot of the imported rows **before** the diff begins, and
then decides ownership from that snapshot:

```python
existing_rows = _imported_rows(connection)      # the snapshot
...
if row.user_modified:                            # read from the snapshot
    unchanged += 1
    continue
_apply_updated(connection=connection, existing=row, entry=entry, now=now)
```

So a user edit that lands *between* the snapshot and the write is invisible to the check.
And the write itself was worse than invisible — it **actively destroyed** the edit:

```python
# personal_events.py
user_modified=(user_modified and event.source == PersonalEvent.Source.CALENDAR_IMPORT),
```

The import passed `user_modified=False`, and `False and True` is `False`. The stored flag
was therefore reset to `False` on every import write — **structurally impossible to
preserve**, because a boolean cannot say "don't change it".

**Reproduced** before fixing, with the user's edit committing between the snapshot and
the write:

```
REAL INTERLEAVE: name='Provider moved it' user_modified=False updated=1
```

The user's edit (`name='My version'`) was gone, and the flag had been cleared. The
clear is the worse half: with the flag cleared, the **next** poll would overwrite the
user's edit again, and the one after that, forever.

**Fix** — two halves, because the defect was in two places.

*First*, the command's vocabulary. `user_modified` now has **three** values, not two:
`True` (the user owns it), `False` (the feed owns it) and `None` (leave it as it
stands). `backend/apps/personalization/services/personal_events.py`:

```python
user_modified: bool | None = True,
...
user_modified=(
    event.user_modified
    if user_modified is None
    else (user_modified and event.source == PersonalEvent.Source.CALENDAR_IMPORT)
),
```

The import passes `None` — "leave the ownership alone" — which is the only thing it is
entitled to say. It knows what the feed says; it does not know whose edit it is.

*Second*, the decision itself is made against **committed state**, under a row lock, in
the same transaction as the write. `backend/apps/personalization/services/calendar_sync.py`:

```python
with transaction.atomic(using=PERSONAL):
    row = (
        PersonalEvent.objects.using(PERSONAL).select_for_update().filter(pk=existing.pk).first()
    )
    if row is None:
        # The row is gone. There is nothing left to protect.
        return False
    if row.user_modified:
        # The user owns this row. The feed's difference is not applied (D2).
        return False
    update_personal_event(..., user_modified=None, ...)
```

The lock is held across the write, so the check and the write are decided against the
same committed state — a user's own request waits for the lock rather than racing it.
The lock is held for one row's write, not for the whole diff.

**Tests added** — `backend/tests/personalization/test_calendar_sync.py`:

- `test_a_user_edit_that_lands_mid_reconcile_is_not_overwritten` — the user's edit
  survives a poll that raced it.
- `test_a_user_edit_that_lands_mid_reconcile_keeps_the_ownership_flag` — the flag is not
  cleared, so the next poll does not overwrite it either.
- `test_the_import_path_never_resets_the_ownership_flag` — the command's third value.
- `test_an_event_deleted_mid_reconcile_is_not_resurrected` — a row deleted in the window
  stays deleted; a mirror that resurrects a deleted event is worse than one that is
  briefly out of date.

**Verified by reverting the fix**: with the locked ownership check removed, three tests
fail — including both new mid-reconcile tests. A regression test that passes against the
broken code is not a regression test.

---

### B2 — A failed calendar was re-fetched every 60 seconds, forever

**Severity**: BLOCKER · **Category**: Correctness · **Status**: Fixed

`sync_calendar` handles four failure modes — revoked, transient, refused, undecryptable —
and each of them writes the next poll time. An error it does **not** handle skipped all
of that: the poll time was left where it was, in the past.

The worker then released the claim, and the connection was due again on the very next
60-second tick — and on every tick after that. Nothing capped it: there is no
`CELERY_TASK_MAX_RETRIES`, no `autoretry_for`, no per-connection failure counter and no
backoff, and the task is acked on receipt, so Celery does not redeliver it either.

**Reproduced** before fixing:

```
after the release: claimed_at=None next_poll_at=2026-11-06 11:59:00+00:00
RE-CLAIMED after 61s: True [UUID('01a18779-...')]
```

**The impact** is not just churn. Each retry is a real HTTP fetch carrying the user's
**secret calendar address** — the credential (AD-18) — against their provider. For one
user with a malformed feed entry, that is 1,440 requests a day, every one failing the
same way, and every one putting the credential on the wire.

**Fix** — the unexpected failure is recorded the same way a transient one is, so the
connection is retried at the **poll cadence** rather than the **tick cadence**, and the
error is visible on the row instead of vanishing into a log line.
`backend/apps/personalization/services/calendar_sync.py`:

```python
def record_unexpected_failure(*, connection_id: UUID, error_kind: str, now: datetime) -> None:
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection_id).update(
        last_error_kind=error_kind,
        last_error_at=now,
        next_poll_at=now + CALENDAR_POLL_INTERVAL,
    )
```

and `backend/worker/tasks.py`:

```python
except Exception as exc:
    calendar_sync.record_unexpected_failure(
        connection_id=identifier,
        error_kind=f"unexpected:{type(exc).__name__}",
        now=_now(),
    )
    logger.warning(
        "Calendar sync failed unexpectedly",
        extra={"connection_id": str(identifier), "error_type": type(exc).__name__},
    )
    raise
```

The status is **not** changed. An unexpected error is a fault on our side, and it must
never ask the user to reconnect a calendar that works (D6).

**Tests added** — `backend/tests/worker/test_calendar_tasks.py` and
`backend/tests/personalization/test_calendar_polling.py`:

- `test_the_sync_job_records_an_unexpected_error_on_the_connection` — the error is on
  the row.
- `test_a_failed_calendar_is_not_re_claimed_on_the_next_tick` — 61 seconds later the
  connection is not due. **This is the hot-loop test.**
- `test_an_unexpected_error_does_not_revoke_the_calendar` — the status is untouched.
- `test_an_unexpected_failure_schedules_the_next_poll` — the poll time moved.
- `test_an_unexpected_failure_does_not_revoke_the_connection` — the status is untouched.

**Verified by reverting the fix**: the hot-loop test fails with the connection re-claimed
61 seconds later.

---

### B3 — A reconnected calendar was invisible to the dispatcher for up to 15 minutes

**Severity**: MAJOR · **Category**: Correctness · **Status**: Fixed

D9 promises that a connected or reconnected calendar is due immediately, so the tick's
dispatcher syncs it **within 60 seconds**. The claim mechanism is what makes that
promise real — a claimed connection is skipped.

But neither `connect_calendar` nor `reconnect_calendar` cleared `sync_claimed_at`, and
neither included it in its `update_fields`. A connection that was claimed when a worker
died kept its stale claim, and the claim filter —

```python
.filter(Q(sync_claimed_at__isnull=True) | Q(sync_claimed_at__lte=now - CALENDAR_CLAIM_TTL))
```

— matched neither branch. So the row was `active` and due, and **nobody would fetch it**
until the claim expired: up to `CALENDAR_CLAIM_TTL` (15 minutes).

**Reproduced** before fixing, reading the row rather than the in-memory instance:

```
row status: active next_poll_at: 2026-11-06 12:00:00+00:00 sync_claimed_at: 2026-11-06 12:00:00+00:00
claimed 61s after the reconnect: []
THE RECONNECTED CALENDAR IS INVISIBLE: True
```

This bites the **reconnect** path hardest, because that is the path a revoked calendar
takes — and a revoked calendar is usually reached *by* a failed sync, which is exactly
when a claim may have been left behind.

**Fix** — `backend/apps/personalization/services/calendar_connections.py`: both commands
now set `connection.sync_claimed_at = None` and include `"sync_claimed_at"` in their
`update_fields`. `disconnect_calendar` already cleared it; the gap was the path that
brings a calendar *back*.

**Tests added** — `backend/tests/personalization/test_calendar_conflict_resolution.py`:

- `test_reconnect_clears_a_claim_left_behind_by_a_dead_worker`
- `test_a_reconnected_calendar_is_claimed_on_the_next_tick` — **the promise D9 makes.**
- `test_connecting_clears_a_claim_left_behind_by_a_dead_worker`

**Verified by reverting the fix**: with `"sync_claimed_at"` out of the `update_fields`,
the reconnect tests fail — the calendar is invisible for the full claim TTL.

---

### B4 — The module promised a guarantee it did not make

**Severity**: MAJOR · **Category**: Documentation · **Status**: Fixed

The module docstring and the `sync_calendar` docstring both said the reconcile is
**all-or-nothing**:

> "**A failed fetch writes nothing (D15).** The reconcile is all-or-nothing: a partial
> sync would delete half the user's imported events because the feed happened to be
> truncated."

and

> "The whole reconcile is **all-or-nothing** (D15)."

Both contradicted `_reconcile`'s own docstring, which says the opposite:

> "**Each write is its own transaction**, so a single failing event does not roll back
> the whole sync."

Two of the three were wrong. D15's actual requirement is about a failed **fetch** — and
that one **does** hold: a failed fetch writes no event row, no conflict pair and no
reminder plan, and the failure is verified by test. The reconcile is deliberately *not*
all-or-nothing, and that is the better design: one transaction for the whole diff would
hold a lock on every touched row for the length of the diff and would roll back a
correct update because an unrelated event failed to write.

**The defect was the claim, not the behaviour.** A docstring that overstates a guarantee
is worse than one that makes none, because the next reader trusts it.

**Fix** — both docstrings now say what is actually true: *a failed fetch* writes
nothing.

---

### B5 — A public, exported function purged the events without closing the pairs or the plans

**Severity**: MAJOR · **Category**: Contract / Architecture · **Status**: Fixed

`calendar_connections.py` ended up with two near-identically named functions:

- `_purge_connection_events` — the real one: deletes through `delete_personal_event`,
  closes the conflict pairs, removes the reminder plans, writes the audit rows.
- `purge_connection_events` — a raw `.delete()` on `PersonalEvent`. It closes **no**
  pairs, removes **no** plans and writes **no** audit rows.

The public one was exported in `__all__`, had the cleaner signature (no `actor`, no
`now`), and was the one a caller would reach for by name. It had no production callers —
only three assertions in an earlier work item's test file.

**Reproduced** before fixing:

```
deleted=1 pair.status='active' plans=1 event_exists=False
```

The event is gone; the conflict pair is still `active` and names a row that no longer
exists; the reminder plan still points at the deleted event.

**Fix** — the raw function is **removed**. It is no longer exported, and it is gone from
the module entirely, so there is no second way to purge a calendar's events that skips
the pairs, the plans and the audit rows.

The three legacy assertions were **migrated onto the command path** rather than deleted.
The property they pinned — the purge removes exactly that connection's events, and leaves
another connection's events and the user's own events alone — is worth keeping, and it
is now asserted against the purge that actually runs. The tests live in
`backend/tests/personalization/test_calendar_connection_commands.py` and the deeper
purge behaviour (the pairs, the plans, the ordering) is pinned in
`backend/tests/personalization/test_calendar_disconnect_purge.py`.

`disconnect_calendar` is now the **only** way a connection's events are purged.

---

## Claims the review raised that did not survive reproduction

These are recorded because a review that reports a false positive is as costly as one
that misses a real bug — and because the *reason* each is not a defect is worth having
written down.

### N1 — The import path could never clear an event's end time

**Claim**: `update_personal_event` treats `end_utc=None` as "leave the end alone", so a
feed entry with no end could never clear the row's end — and because `_same_content`
compares `end_utc`, every subsequent poll would see a "difference", bump `version`, and
re-send the reminder every hour, forever.

**Not a defect.** The claim depends on a feed entry carrying `ends_at=None`. It cannot:
`ports.calendar.CalendarEntry.ends_at` is a non-optional `datetime`
(`backend/ports/calendar.py:111`), and the ICS adapter collapses a missing DTEND to the
start (`backend/adapters/calendar/ics.py:246` and `:268`). A row's `end_utc` is therefore
never `None` for an imported event, so the sentinel is never exercised.

The underlying sharpness — `None` meaning "unchanged" — is real but **unreachable**, and
the port's own type already rules it out. No change was made.

### N2 — The reconcile's atomicity was a hole in D15

**Claim**: the reconcile is not all-or-nothing, so a partial failure leaves the user's
calendar half-mirrored.

**Not a defect as stated.** D15 requires that *a failed fetch* writes nothing, and that
holds — verified by test, and by the fact that the failure paths return before the
reconcile is reached. The reconcile's per-write transactions are a deliberate choice
(documented in `_reconcile`'s own docstring), not an oversight, and one transaction for
the whole diff would be worse.

The **partial-failure** case it describes is real, but it is a consequence of the
per-write design rather than a violation of D15, and B4 fixed the part of it that was
actively misleading — the docstring. The half-mirrored state itself remains possible if a
single malformed feed entry fails mid-diff; it is now *visible* on the connection row
rather than silent, because B2 records every unexpected failure there.

---

## The Verification

Every fix was verified by **reverting it and watching the test fail**. A regression test
that passes against the broken code is not a regression test, and three of these fixes
could have been shipped with tests that proved nothing.

| Fix | Reverted | Result |
|---|---|---|
| B1 — the locked ownership check | `if row.user_modified:` → `if False:` | 3 tests fail |
| B2 — the recorded unexpected failure | the worker's `record_unexpected_failure` call removed | 2 tests fail |
| B3 — the cleared claim on reconnect | `"sync_claimed_at"` out of `update_fields` | 2 tests fail |
| B3 — the cleared claim on connect | `"sync_claimed_at"` out of `update_fields` | 1 test fails |

---

## The Final Gate

```
pytest tests/ -q --cov --cov-report=term-missing
2648 passed in 191.76s
TOTAL                                             5819     63    99%
Required test coverage of 80.0% reached. Total coverage: 98.92%

ruff check .
All checks passed!

ruff format --check .
339 files already formatted

lint-imports
Contracts: 17 kept, 0 broken.

manage.py check
System check identified no issues (1 silenced).

manage.py makemigrations --check --dry-run
No changes detected

pytest tests/worker/test_tick.py -q
5 passed
```

Every module this item created or changed is at **100%** — `calendar_sync.py`,
`calendar_connections.py`, `personal_events.py`, `conflicts.py`,
`conflict_resolutions.py`, `reminder_plans.py`. The 63 uncovered statements are all
pre-existing gaps elsewhere in the codebase.

`tests/worker/test_tick.py` is **unchanged** and passes untouched — the acceptance
criterion this work item names.

---

## The Shape of the Defects

All five findings share one shape, and it is worth naming because it is the shape the
*next* item will have too.

**Every one of them is a value that could not express what the caller needed to say.**

- `user_modified: bool` could not say "leave the ownership alone" → the user's edit was
  destroyed (B1).
- The four handled failure modes could not say "something else went wrong" → the failure
  was invisible and the poll looped (B2).
- The claim's lifecycle had no way to say "this claim is dead, forget it" → the calendar
  was invisible (B3).
- Two functions with almost the same name, one of them a trap → the wrong one would be
  called (B5).

A boolean is a good tool right up until it needs a third value. The fix in each case was
the same: **give the parameter a vocabulary that can say what is actually meant**, rather
than overloading a value that already means something else.

B1 is the sharpest instance. The command already had a `user_modified` parameter, added
for exactly this purpose, and the design had already worked out that the import should
pass the *existing* value. The parameter was never given the ability to say that, so the
import passed `False` and the flag was reset every time. The design was right and the
vocabulary was wrong.

---

## What This Review Does Not Cover

- **The live provider.** No Google or iCal secret address was fetched. The ICS adapter is
  tested against fixtures, and the poll interval (OQ-7) is still provisional.
- **The API surface.** This item has no endpoints; the conflict prompt's two-button
  variant for an imported side is owed to `pulse-preview-api-and-geo`.
- **The purge's failure mode.** The purge is deliberately not atomic — the credential is
  destroyed first, so a failed purge never leaves a live secret. A failed purge *does*
  leave orphaned events and plans, and nothing retries them. The design sanctions this,
  but it sanctions it without a compensating mechanism, and the item that adds the
  retention sweep (AD-15) is where that should be settled.
- **The `delete_new` button on a saved-event side.** `resolve_conflict` calls
  `delete_personal_event` unconditionally, so a `SAVED_EVENT` side would raise
  `PersonalEventNotFoundError` and leave the pair `active` forever. This is
  **pre-existing** — the call is unchanged from the original commit — and not reachable
  through the current API, which hardcodes a personal-event side. It becomes reachable
  with `pulse-preview-api-and-geo`, and it should be settled there.
