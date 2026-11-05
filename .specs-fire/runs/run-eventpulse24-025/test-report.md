---
run: run-eventpulse24-025
work_item: held-for-propagation-status
intent: event-state-sync
created: 2026-11-05
---

# Test Report: run-eventpulse24-025

## Work Item: held-for-propagation-status

### Test Results

| Suite | Result |
|---|---|
| `tests/delivery/test_delivery_sweep.py` | **58 passed** (45 pre-existing + 13 new) |
| `tests/delivery/test_scheduled_sends.py` | **52 passed** (46 pre-existing + 6 new) |
| `tests/worker/test_sweep_tasks.py` | **17 passed** (12 pre-existing + 5 new) |
| `tests/delivery/test_delivery_sweep_concurrency.py` | **5 passed** |
| `tests/worker/test_scheduling_tasks.py` | **18 passed** |
| `lint-imports` | **19 contracts kept, 0 broken** |
| `ruff check` / `ruff format` | clean |
| `manage.py check` | no issues |
| `makemigrations --check` | no changes detected — model and migration agree |
| **Full backend suite** | **5288 passed, 8 failed** — all 8 pre-existing (see below) |

**24 tests added.** Two more were added during code review, pinning the two findings it
surfaced (see `review-report.md`).

### Tests proven able to fail

Each mutation was applied to the source, the suite run, and the source restored.

| Mutation | Caught by |
|---|---|
| Guard never holds (`if False`) | 4 tests |
| Guard drops a vanished row | `test_a_row_deleted_between_the_claim_and_the_guard_stays_in_the_batch` |
| Discriminator uses `event_version` instead of `target_kind` | `test_only_saved_event_rows_are_looked_up_in_the_catalog` |
| A hold increments `attempts` | `test_a_hold_is_not_a_delivery_attempt` |
| `KEEP` does not clear `held_at` | 3 tests, incl. the parametrized all-seven-kinds guard |

The discriminator mutation initially **survived**, which exposed a weak test and an overstated
justification. See "Corrections" below.

### Acceptance Criteria Validation

| Criterion | Status | Note |
|---|---|---|
| New non-terminal held state | **Changed by design** | A nullable `held_at`, not a `Status` member. Approved at Checkpoint 1 (D1) |
| `TERMINAL_STATUSES` unchanged; `models.py:287` docstring rewritten | **Partly superseded** | The frozenset is unchanged, and the docstring needed *no* rewrite — it stays true under the column. That the AC expected a rewrite is itself evidence for D1 |
| Version read after claim, separate and non-transactional | met | `hold_stale_sends` takes ids, runs after the claim commits |
| Catalog newer → held, not sent, not re-claimed | met | `test_a_send_whose_event_moved_is_held_not_sent`, `test_a_held_row_is_not_claimed_again` |
| A held row is never stranded | met | Parametrized across all seven `LIFECYCLE_SEND_BEHAVIOUR` kinds |
| Guard applies only to event-bound rows | met | `target_kind == saved_event`; personal reminders and digests pass through |
| Send key not consumed by a hold | met | A hold never calls the port; `REMINT` re-mints against a fresh key |
| Accepted residual window tested | **not met — see below** | |
| No per-row catalog query | met | One batched `get_public_events` per sweep batch |

### Corrections made during execution

**1. D5 reversed — an absent event is sent, not held.** The design said hold. That was wrong:
the release path is propagation, and propagation only runs from an `EVENT_STATE_CHANGE` row, so
an event absent for any reason that is not a lifecycle change would be held **permanently** with
the alarm firing forever over something propagation cannot fix. The tree had already settled
this deliberately (`delivery_messages._public_event_facts`: *"a missing event is not an error
here… the reminder still goes out"*). AD-17 names exactly one condition — *"if the catalog
version is newer"* — and the guard now holds on that alone. Caught by 19 failing tests.

**2. The `KEEP` re-timing requirement was dropped.** The design said the `KEEP` path must
re-time `due_at`. Only `sold_out` and `detail_changed` map to `KEEP`, and a time change is
always its own `time_moved` state change (one per kind), which is `REMINT` — so a `KEEP` change
never moved the event and re-timing would move a reminder that nothing moved.

**3. A test was testing the harness.** `assert not ...in_atomic_block` can never fail under
`pytest.mark.django_db`. Replaced with a falsifiable property: the claim must be **persisted**
in `claimed_at` before the guard runs — AD-17's *"recorded, not merely locked"*.

**4. An overstated justification, corrected in the code.** The `target_kind` discriminator was
justified as preventing "every personal reminder held forever". True only under the original
D5; once absence means *send*, the wrong discriminator is benign. Mutation testing proved it.
The discriminator still earns its place (it avoids a pointless catalog lookup per personal
reminder) and now has a test that actually fails without it, with the honest reason recorded.

**5. AD-2 contract break.** `worker.tasks` imported `apps.delivery.models` directly. Moved
behind a published `count_stuck_holds` service — which is what that contract exists to force.

### Known gaps

- **AD-17's accepted residual window is not tested.** The AC asked for a test documenting the
  race where a change commits between the version read and the provider call. It is genuinely
  hard to make deterministic without a seam the sweep does not have, and a test that cannot
  reliably reproduce it would be theatre. **Deferred to `propagation-consumer`**, where the
  FR-54 notice that corrects the window is built and the seam exists. Recorded, not dropped.

### Pre-existing failures (not caused by this work item)

`tests/e2e/test_timeline_and_conflict_proof.py` — **8 failures**, reproduced on stashed code.

`START_UTC = datetime(2026, 11, 5, 3, 0)` and `CATALOG_START_UTC` an hour later; the save
endpoint treats an event that has already started as not found, so the test gets 404 where it
expects 409. **The fixture expired at 04:00 UTC on 2026-11-05.** It passed when run-024 closed
on 2026-11-04 and has failed since the date rolled over. It belongs to `timeline-and-conflicts`
and blocks CI on any branch until fixed.
