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

---

## Work Item: saved-event-lifecycle-state

### Test Results

| Suite | Result |
|---|---|
| `tests/personalization/test_saved_events.py` | **55 passed** (25 pre-existing + 30 new) |
| `tests/personalization/test_digest_candidates.py` | **36 passed** (32 pre-existing + 4 new) |
| `tests/personalization/test_timeline.py` | **50 passed** (44 pre-existing + 6 new) |
| `tests/personalization/test_conflict_list.py` | **22 passed** (21 pre-existing + 1 new) |
| `tests/personalization/test_saved_events_api.py` | **30 passed** (17 were failing before this item — see below) |
| `lint-imports` | **19 contracts kept, 0 broken** |
| `ruff check` / `ruff format` | clean |
| `manage.py check` | no issues |
| `makemigrations --check` | **no changes detected** — the design's central claim, held |
| OpenAPI + TS client | regenerated; `state` is additive and optional |
| Frontend (`lint-web`, `test-web`) | **1577 passed**, eslint / tsc / prettier clean |
| **Full backend suite** | **5329 passed, 8 failed** — all 8 pre-existing e2e |

**41 tests added.**

### Tests proven able to fail

Thirteen mutations, each applied to the source, run, and reverted. **All thirteen caught.**

| Mutation | Caught by |
|---|---|
| M1 cancel gate `<` instead of `<=` | `test_cancelling_a_save_refuses_the_version_it_already_has` |
| M2 digest keeps cancelled candidates | `test_a_saved_event_the_catalog_says_is_cancelled_is_not_a_candidate` |
| M3 digest drops anything not `scheduled` | `test_a_postponed_save_is_still_a_candidate` |
| M4 timeline calls an absent event `scheduled` | `test_a_save_whose_catalog_event_disappeared_has_an_unknown_state` |
| M5 reverse read ignores the keyset cursor | `test_list_savers_for_event_pages_by_keyset` |
| M6 reverse read not scoped to the event | `test_list_savers_for_event_is_scoped_to_the_event` |
| M7 unsave leaves the Reminder Plan behind | `test_unsaving_removes_the_reminder_plan` |
| M8 cancellation does not close the pairs | `test_cancelling_a_save_closes_its_pairs_as_cleared_by_state_change` |
| M9a reinstate does not bump the version | `test_reinstating_applies_a_newer_version` |
| M9b reinstate gate accepts an equal version | `test_cancel_reinstate_cancel_is_idempotent_at_every_step` |
| M9c reinstate claims success on a missing save | `test_reinstating_an_event_nobody_saved_does_nothing` |
| M10 cancel does not bump the version | `test_cancelling_a_save_applies_a_newer_version` |
| M11 reinstate reopens the closed pair | `test_reinstating_cannot_reopen_a_pair_cancellation_closed` |

Three of these only pass because of corrections the mutations forced. See below.

### Acceptance Criteria Validation

| Criterion | Status | Note |
|---|---|---|
| `SavedEvent` can represent a dead event without crossing the wall | **met by removal** | No column. Every reader already receives a `PublicEvent` carrying `status`; the gap was that none of them looked (D1) |
| Published cancellation service, version-gated like `update_saved_event_snapshot` | met | `cancel_saved_event`, same gate, same audit shape, same single `personal` transaction |
| Published reverse read, batched and bounded | met | `list_savers_for_event`, keyset-paged on UUIDv7 `id` over `saved_event_event_idx` |
| Covers both FR-54 populations | **met, as one population** | Probed: a plan cannot be born without a live save, and `unsave_event` now removes the plan, so plan-holders ⊆ savers always (D5) |
| A cancelled public event never auto-cancels a personal event | met | `test_cancelling_a_save_leaves_the_personal_event_untouched` asserts times, version and `updated_at` |
| `superseded` behaves as a cancellation; no plan migrated | met | Same service; nothing follows `superseded_by` |
| **`reinstated` reverses it, pairs re-evaluated rather than left closed** | **NOT MET — unachievable** | See below |
| Three surfaces each state and test their behaviour for a dead save | met | Timeline shows and marks; digest drops; `/conflicts` needs no rule of its own, pinned by an end-to-end test rather than assumed |
| Version gate at the boundary; out-of-order no-op; cancel→reinstate→cancel idempotent; personal event untouched | met | |

### The one AC that cannot be built

**`reinstated` can never restore the conflict the cancellation closed.** Two invariants meet
and leave no room, both probed directly rather than inferred:

```
reopen:    IntegrityError: a closed ConflictPair ... is immutable   (guard_conflict_pair)
duplicate: IntegrityError: duplicate key violates "conflict_pair_pair_uq"
```

AD-17 requires a cancellation to *close conflicts*; AD-21's D24 makes a closed pair immutable
and the unique constraint on `(user, left, right)` forbids a replacement row. A saved event
that clashed, was cancelled, then reinstated clashes again — and `/conflicts` will not say so.

Pinned by `test_reinstating_cannot_reopen_a_pair_cancellation_closed` so it is documented
behaviour, not a silent hole, and raised as an amendment on the intent brief with two exits,
both spine edits: AD-17 stops closing conflicts and the readers filter on the catalog's
`status` (which is D1 again), or D24 gains a narrow exception for a state-change clear that
later reverses.

### Corrections made during execution

**1. The work item's central premise was wrong, and the design dropped it.** It claimed the
personal side "cannot ask `catalog` whether it is dead: AD-3 forbids the join." AD-21 forbids a
SQL *join* so conflict arithmetic cannot depend on catalog availability — the snapshot owns the
*times*. All three reading surfaces already do a batched published read on every call and
already receive `status`. A grep for `.status` across them returned one hit, `pair.status`.
**No column, no migration.**

**2. D5 settled by probe, and it pulled in a fix.** `unsave_event` left the `ReminderPlan` and
both pending sends alive (`plans_after=1 sends_after=['pending','pending']`), so reminders kept
going out for an event the user removed. Taken into this item rather than filed, because
without it FR-54's population is undecidable *and* item 1's hold becomes a permanent alarm: an
orphan's owner is not a saver, so propagation never reaches `apply_lifecycle_change`'s `KEEP`
branch and `held_at` is never cleared.

**3. `reinstate_saved_event`'s conflict detection was dead code, and a mutation proved it.**
M9 survived. The probe showed why: `after_save=0 after_cancel=0 after_personal_event=1` — the
pair is created by `create_personal_event`, before any reinstatement. Every path that can bring
an overlap into existence already detects it, and a `SavedEvent` carries no cancelled flag
(D1), so an overlap acquired while the save is dead is recorded the moment it is acquired.
`update_saved_event_snapshot` needs its detection because the save *moved*; a reinstatement
moves nothing. **The call was removed** rather than kept as code that claims to restore
conflicts while provably restoring none.

**4. A test that could not fail.** The first reinstate test asserted `exists()` after the call —
true whether or not `reinstate` did anything. Replaced with one asserting the count **before**
and after, plus one asserting the full `(id, status, resolution)` set is unchanged.

**5. A test that hung instead of failing.** `test_list_savers_for_event_pages_by_keyset` drove
the cursor with `while True`; M5 made it re-serve page one forever, hanging the suite for 30
minutes and holding the test database open. Now bounded by an explicit page budget with a
`for…else` that raises "the cursor is not advancing". A test that hangs is not a test that can
fail.

**6. A coverage gap, not a design finding.** M9c (`return True` for a user with no save)
survived. `cancel_saved_event` had that guard tested; reinstate did not. The return value is
what AD-17's consumer reads to decide who was affected, so a `True` would queue an FR-54 notice
to a non-saver. Two tests added and M9c re-run alone to confirm it now fails.

### Fixed in passing: 17 tests that expired overnight

`tests/personalization/test_saved_events_api.py` pinned `START = datetime(2026, 11, 6, 3, 30)`
under a docstring reading *"a fixed instant **far enough ahead** that a test's events are always
upcoming"*. The endpoints call `timezone.now()` themselves and only an unstarted event is
saveable, so at 03:30Z on 2026-11-06 every save in the file became a 404 — seventeen tests that
had never run against a started event suddenly did. Verified pre-existing by stashing.

Anchored to the run clock (`timezone.now() + 30 days`, fixed time of day so the ordering
assertions stay stable) rather than bumped, which would only reset the timer. Taken because
this file is what covers the `unsave_event` change this item makes.

### Still pre-existing and unfixed

`tests/e2e/test_timeline_and_conflict_proof.py` — **8 failures**, same defect class, same
one-line fix. Left alone per the approved plan; it belongs to `timeline-and-conflicts` and
still blocks CI on any branch.
