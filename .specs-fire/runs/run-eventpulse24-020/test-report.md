---
run: run-eventpulse24-020
work_item: calendar-sync-and-polling
intent: onboarding-and-account
generated: 2026-10-29
status: passing
---

# Test Report: Calendar Sync & Polling (AD-7, AD-18, FR-20, FR-50, FR-58)

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Item-scoped | 107 | 0 | 0 | 100% (the item's modules) |
| **Total (whole backend)** | **2648** | **0** | **0** | **98.92%** |

The 107 item-scoped tests are a subset of the 2648-test backend suite. The whole backend
suite is **2648 passed, 0 failed** in 207.33s; coverage is **98.92%** across 5816
statements with **151 files at 100%**.

**Every module this item created or changed is at 100%** — `calendar_sync.py`,
`calendar_connections.py`, `conflicts.py`, `conflict_resolutions.py`,
`reminder_plans.py`, `personal_events.py` and `worker/tasks.py`. The 63 uncovered
statements are all pre-existing gaps elsewhere in the codebase (`adapters/throttle/redis.py`,
`config/asgi.py`, `apps/identity/*` and friends).

## Test Commands

```bash
# The item's own tests
cd backend && .venv/bin/python -m pytest \
    tests/personalization/test_calendar_sync.py \
    tests/personalization/test_calendar_polling.py \
    tests/personalization/test_calendar_disconnect_purge.py \
    tests/personalization/test_calendar_conflict_resolution.py \
    tests/worker/test_calendar_tasks.py \
    tests/delivery/test_reminder_plans.py -q

# The whole backend suite, with coverage
cd backend && .venv/bin/python -m pytest tests/ -q --cov --cov-report=term-missing

# The linter
cd backend && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .

# The import contracts
cd backend && .venv/bin/lint-imports

# The tick's own acceptance criterion
cd backend && .venv/bin/python -m pytest tests/worker/test_tick.py -q
```

## What Was Added

| File | Tests | Covers |
|------|-------|--------|
| `backend/tests/personalization/test_calendar_sync.py` | 39 | The reconcile: the three branches, idempotence, ownership, the failures, the conflicts, the audit and the logs |
| `backend/tests/personalization/test_calendar_polling.py` | 19 | The due-claim: atomicity, the TTL, the batch, the ordering, the due rule |
| `backend/tests/personalization/test_calendar_conflict_resolution.py` | 23 | The imported-event conflict rules (D3) and the reconnect command (D6, D9) |
| `backend/tests/personalization/test_calendar_disconnect_purge.py` | 9 | The disconnect purge: the scope, the pairs, the plans, the ordering (D13) |
| `backend/tests/worker/test_calendar_tasks.py` | 12 | The dispatcher and the sync job (D8) |
| `backend/tests/delivery/test_reminder_plans.py` | +4 | `remove_plans_for_targets` — the bulk delete and its audit rows |
| `backend/tests/personalization/test_calendar_connection_commands.py` | 3 | The purge's scope, now asserted against the command path |

## What Was Changed in the Existing Tests

Exactly one existing test file changed, and it changed because the tick's behaviour changed:

`backend/tests/worker/test_scheduling_tasks.py` — the tick's enqueued job list now includes
`worker.tasks.schedule_calendars`. The tick still enqueues `schedule_sources` and
`reconcile_outbox` exactly as before; it enqueues one more dispatcher.

**`backend/tests/worker/test_tick.py` is unchanged**, which is the acceptance criterion the
work item names. It asserts that `beat_schedule` is exactly one 60s tick, that the tick is
registered under its scheduled name, that it logs and returns nothing, and that it runs
through Celery — none of which the new dispatcher disturbs. It passes untouched.

## The Properties Pinned

### The reconcile is a three-way diff (D1)

| In the feed | In the database | Action |
|---|---|---|
| yes | no | create |
| yes | yes, identical | **nothing** |
| yes | yes, different | update (unless the user owns the row — D2) |
| no | yes | delete |

The **identical → nothing** branch is the one that matters most, and it is pinned from
both sides:

- `test_resyncing_an_unchanged_feed_changes_nothing` — the row's `version` and
  `updated_at` are unchanged after a second sync of the same feed.
- `test_an_unchanged_feed_sends_no_reminders_again` — the version did not move, so AD-7's
  send key did not move, so the reminder is not re-sent.

The reason is worth stating, because it is the whole reason the branch exists: `version`
feeds the send key, so a sync that rewrote every row on every poll would re-send every
reminder for every imported event, every hour, forever. A poll that changes nothing must
change *nothing downstream*.

The key is `(calendar_connection_id, source_uid)` — the unique constraint the model already
carries, created by the connection-model item for this purpose. The id is the one the
**adapter** produced (`domain.dedup.ics_item_id`), not one re-derived from the raw UID, so
an override of a recurring master's own instance lands on the master's row rather than
beside it.

### The user's edit wins (D2)

- `test_a_feed_change_overwrites_an_untouched_import` — the feed owns an untouched row, so
  a difference is applied.
- `test_a_feed_change_does_not_overwrite_a_user_edit` — the user owns an edited row, so
  the feed's difference is not applied and the row is not counted as updated.
- `test_a_user_edit_marks_the_row_user_modified` — the command sets the flag.
- `test_a_user_created_event_is_never_flagged_user_modified` — there is no feed to
  disagree with a user-created event, and the model's constraint says so.
- `test_a_user_created_event_is_never_touched_by_a_sync` — the diff's scope is the
  connection's imported rows, so a user-created event is out of reach by construction.
- `test_a_deleted_imported_event_returns_on_the_next_sync` — the decided behaviour: the
  mirror is the provider's agenda, and the provider still says the event exists.

The flag is stored, not inferred. "Did the user edit it?" could be inferred by comparing
the row with the feed, but that inference is exactly the case where the two disagree — and
its answer would flip depending on which side you looked from.

### Every write goes through the shared command paths (D11)

The import calls `create_personal_event`, `update_personal_event` and
`delete_personal_event` — the same commands the user's own edits use. The tests pin the
consequences rather than the implementation:

- `test_the_imported_event_gets_the_default_reminder_plan` — FR-20's 1d + 1hr, attached by
  the same call a user-created event makes.
- `test_an_update_does_not_replace_the_users_reminder_plan` — the default is a property of
  *creation*; re-attaching it on an update would wipe a customised plan.
- `test_an_imported_event_that_overlaps_records_a_conflict_pair` — the pair exists, and it
  can only exist if the import went through the command that creates pairs.
- `test_a_changed_uid_updates_its_row_and_bumps_the_version` — the version bump is the
  command's, and AD-7's send key depends on it.

### The failures (D6, D7, D15)

- `test_a_revoked_fetch_marks_the_connection_and_keeps_the_events` — the status becomes
  `needs_reconnect` and **the imported events stay**. The provider revoked the *address*,
  not the *events*.
- `test_a_transient_failure_leaves_the_status_alone` — a provider's bad afternoon never
  asks the user to reconnect a working calendar.
- `test_a_refused_fetch_is_never_a_revocation` — a refusal is *our* decision about the
  address, not the provider's word about the credential.
- `test_an_undecryptable_credential_is_recorded_but_is_not_a_revocation` — a wrong key is a
  fault on our side; the user cannot fix it by pasting the address again.
- `test_a_failed_fetch_writes_no_events` — no events, no plans, nothing.
- `test_the_next_poll_is_scheduled_after_a_failure` and
  `test_the_next_poll_is_scheduled_after_a_success` — the same schedule either way.

### The conflicts (D3, D4)

- `test_an_imported_event_that_overlaps_records_a_conflict_pair` — the time rule applies
  and the pair is `active`.
- `test_an_imported_event_that_is_a_duplicate_of_a_user_event_records_no_pair` — the
  duplicate rule does **not** apply between an import and a user-created event. The test
  places the two a day apart, so the time rule cannot fire and the duplicate rule is the
  only one that could.
- `test_an_imported_event_that_overlaps_a_user_event_records_a_time_pair` — the same name
  *and* the same hour still records a **time** pair: two things at once is a clash
  whichever way round it is.
- `test_two_imported_events_with_the_same_name_do_record_a_pair` — two imports *are*
  compared: the user saved the same meeting to two calendars.
- `test_a_resolved_conflict_is_not_re_prompted_on_the_next_sync` — AD-21: a closed pair
  is immutable and never re-prompted.
- `test_delete_new_is_refused_when_the_new_side_is_an_imported_event` and
  `test_the_refusal_leaves_the_pair_active_and_the_event_alone` — D3. "Delete the new one"
  would delete a row the *provider* owns, and the next poll would recreate it, so the
  button would be a lie. The refusal happens **before** the pair is marked resolved, so a
  refused attempt leaves the pair active and answerable with a choice that works.
- `test_keep_both_is_offered_for_an_imported_event` and
  `test_edit_new_is_offered_for_an_imported_event` — the two buttons that do work. The
  API that presents the prompt (`pulse-preview-api-and-geo`) must offer a two-button
  variant for an imported side; that dependency is recorded in the design doc.

### The disconnect (D13)

- `test_disconnecting_purges_exactly_that_connections_events` and
  `test_disconnecting_leaves_the_users_own_events` — the scope.
- `test_disconnecting_leaves_another_connections_events` — the two-connection test.
- `test_disconnecting_removes_the_reminder_plans` — `delivery` owns `REMINDER_PLAN`, and
  a disconnected calendar must not leave rows pointing at events that no longer exist.
- `test_disconnecting_closes_the_conflict_pairs` — the pairs close as
  `cleared_by_state_change`: nobody answered the prompt, the event went away.
- `test_disconnecting_destroys_the_credential_first` — the ordering.
- `test_a_disconnected_connection_is_not_polled_again` — the row leaves the due set.

### The polling (D8)

- `test_a_due_connection_is_claimed`, `test_a_connection_that_is_not_due_is_not_claimed`,
  `test_a_connection_that_has_never_been_polled_is_due`.
- `test_a_needs_reconnect_connection_is_not_claimed` — a revoked connection is not polled
  until the user pastes a new address.
- `test_a_disconnected_connection_is_not_claimed` — there is no credential to fetch with.
- `test_the_claim_takes_the_row_atomically` — `SKIP LOCKED`, proved the same way
  `ingestion`'s equivalent is: one thread holds two rows, the other claim takes the rest,
  and the two claims are **disjoint**.
- `test_an_expired_claim_becomes_claimable_again` — a lost job (a worker died).
- `test_a_live_claim_is_not_claimable_again` and
  `test_a_claimed_connection_is_not_claimed_again`.
- `test_the_claim_is_bounded` and `test_the_claim_batch_size_is_configurable`.
- `test_the_least_recently_polled_connection_is_claimed_first` — no connection starves.
- `test_the_claim_writes_an_audit_row` and `test_releasing_a_claim_writes_no_audit_row` —
  the claim is audited by the dispatcher; the release is not, because the sync's own audit
  row closes it.

### The worker (D8)

- `test_the_dispatcher_claims_the_due_connections_and_enqueues_one_job_each`.
- `test_a_failed_enqueue_releases_that_claim_and_continues` — a broker failure frees the
  claim so the next tick retries it, and the other connection is still enqueued.
- `test_the_sync_job_releases_the_claim_after_a_successful_sync`,
  `..._after_a_transient_failure` and `..._after_an_unexpected_error` — the claim is
  released in a `finally`, so an unexpected error does not leave the connection claimed
  until the TTL expires.

### The audit and the logs (D10, D17)

- `test_a_sync_writes_one_audit_row_with_counts` — **one** row per connection, not one per
  event: a user's calendar can hold hundreds of events, and a per-event row would write
  hundreds of rows per hour per connection.
- `test_the_sync_audit_row_holds_no_event_content` — the details hold no title, no UID
  and no URL.
- `test_a_polled_sync_uses_a_system_actor` — the actor is `calendar_sync`, with no user
  id: a poll at 3am has no user behind it.
- `test_no_event_content_reaches_any_log_line_over_a_full_sync` — the acceptance
  criterion, checked over a whole sync.
- `test_the_sync_never_logs_the_credential` — the port is handed a `Credential`, whose own
  `repr` is `Credential('[redacted]')`.

### The 304 path

- `test_a_not_modified_feed_changes_nothing` — a 304 is a success, and the caller keeps
  what it has.
- `test_the_successful_poll_stores_the_cache_validators` — the validator is stored and
  goes back on the next fetch, so an unchanged feed costs a 304 instead of a full
  download. A stale validator is cleared rather than kept: a stale `ETag` would make the
  provider answer 304 for a feed it has changed, and the user's events would silently
  stop updating.

## Coverage

```
TOTAL                                             5816     63    99%
151 files skipped due to complete coverage.
Required test coverage of 80.0% reached. Total coverage: 98.92%
```

Every file this item touched is in the "skipped due to complete coverage" set:

```
apps/personalization/services/calendar_sync.py            100%
apps/personalization/services/calendar_connections.py     100%
apps/personalization/services/conflicts.py                100%
apps/personalization/services/conflict_resolutions.py     100%
apps/personalization/services/personal_events.py          100%
apps/delivery/services/reminder_plans.py                  100%
worker/tasks.py                                           100%
```

## Lint and Contracts

```
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
```

The 17 import contracts are unchanged, and that matters here: `calendar_connections.py` now
calls `delivery`'s service and `personalization`'s own, and the `models-delivery` contract
is what keeps `personalization` from writing `REMINDER_PLAN` itself. The purge asks
`delivery` to delete the plans; it does not reach for the model.

```
AD-2 only apps.delivery imports apps.delivery.models (others call its services) KEPT
AD-2 only apps.personalization imports apps.personalization.models (others call its
services) KEPT
```

## The Defects the Suite Found and the Fixes

Six gaps were found and closed while building this item. Each is now regression-tested.

1. **The 304 path could never work.** `ports.calendar.CalendarFeed` carries `etag` and
   `last_modified`, and `CalendarResult` returns new ones — but `CalendarConnection` had
   nowhere to keep them, so the sync had nothing to send back and every poll was a full
   download. Fixed by adding the two columns (migration `0004`) and storing the
   validators on every successful poll; pinned by
   `test_the_successful_poll_stores_the_cache_validators`.

2. **`remove_plans_for_targets` had no target to name in its audit row.**
   `PersonalizationAuditEntry.target_id` is a non-null `UUIDField`, so the first
   implementation — one row for the whole batch — would have raised on write. Fixed by
   writing **one row per deleted plan**, each carrying its target's id. AD-5 wants one row
   per mutation, and a row that names no target cannot say what changed.

3. **The duplicate rule could not be switched off on the command path.** D4 requires the
   import to skip the duplicate rule, and the import reaches detection only through
   `create_personal_event` / `update_personal_event`. The first implementation put the
   rule behind a flag on `detect_conflicts` alone, which the import could not reach.
   Fixed by adding `include_duplicate_conflicts` to both commands, defaulting to `True`
   so every existing caller is unchanged.

4. **A stale cache validator would have frozen the user's calendar.** The first version of
   the validator storage kept the old value when the provider sent none. Fixed by clearing
   it — a stale `ETag` would make the provider answer 304 for a feed it has changed.

5. **The `_is_imported_personal_event` helper had two uncovered branches.** The kind check
   and the missing-row check were separate statements, and neither was reachable from the
   tests. Fixed by folding them into one expression and adding
   `test_delete_new_on_a_saved_event_side_is_not_the_imported_refusal`.

6. **The atomicity test could not see its own rows.** The first version of
   `test_the_claim_takes_the_row_atomically` ran inside the test's transaction, so the
   other thread's connection could not see the uncommitted rows and the assertion passed
   vacuously. Fixed with `transaction=True`, the same marker `ingestion`'s equivalent
   uses — and the test now genuinely proves the two claims are disjoint.

## The Defects the Review Found and the Fixes

The code review found **five** more, one of them a BLOCKER. All five are fixed and
regression-tested, and each fix was verified by **reverting it and watching the test
fail** — a regression test that passes against the broken code proves nothing.

7. **A user's edit could be overwritten, and their ownership destroyed, by a poll that
   raced them.** The reconcile decided ownership from a snapshot taken *before* the diff
   began, so a user edit landing in between was invisible to it — and the write then
   **cleared** the `user_modified` flag, because the import passed `False` and a boolean
   cannot say "leave it alone". The user's edit was destroyed, and the *next* poll would
   destroy it again, forever.

   Fixed in two halves: the command's `user_modified` parameter gained a third value
   (`None` — leave it as it stands), and the ownership decision is now made against
   **committed state**, under a row lock, in the same transaction as the write. Pinned by
   `test_a_user_edit_that_lands_mid_reconcile_is_not_overwritten`,
   `test_a_user_edit_that_lands_mid_reconcile_keeps_the_ownership_flag` and
   `test_an_event_deleted_mid_reconcile_is_not_resurrected`.

8. **A failed calendar was re-fetched every 60 seconds, forever.** The four handled
   failure modes each wrote the next poll time; an unhandled one skipped that, so the
   poll time stayed in the past and the connection was re-claimed on the very next tick,
   with nothing capping it. Each retry is a real HTTP fetch carrying the user's **secret
   calendar address** — 1,440 a day against their provider. Fixed by recording the
   unexpected failure on the connection, so it is retried at the poll cadence rather
   than the tick cadence. Pinned by `test_a_failed_calendar_is_not_re_claimed_on_the_next_tick`.

9. **A reconnected calendar was invisible to the dispatcher for up to 15 minutes.** Neither
   `connect_calendar` nor `reconnect_calendar` cleared `sync_claimed_at`, so a claim left
   behind by a dead worker kept the row out of the claim filter — and D9's promise of a
   sync "within 60 seconds" was broken. Fixed by clearing the claim in both commands.
   Pinned by `test_a_reconnected_calendar_is_claimed_on_the_next_tick`.

10. **The module promised a guarantee it did not make.** The module docstring and the
    `sync_calendar` docstring said the reconcile was "all-or-nothing", contradicting
    `_reconcile`'s own docstring. D15's actual requirement — *a failed fetch* writes
    nothing — does hold, and is tested; the reconcile is deliberately not atomic, and
    one transaction for the whole diff would be worse. The docstrings now say what is
    true.

11. **A public, exported function purged the events without closing the pairs or the
    plans.** `purge_connection_events` was a raw `DELETE` that closed no conflict pairs,
    removed no reminder plans and wrote no audit rows, and it was the one a caller would
    reach for by name. It is now **removed**; `disconnect_calendar` is the only way a
    connection's events are purged. The three legacy assertions were migrated onto the
    command path rather than deleted — the purge's scope is still pinned, against the
    purge that actually runs.

## Test Result

**Passing.** 2648 passed, 0 failed, 98.92% coverage, ruff clean, 17/17 import contracts
kept, no migration drift.
