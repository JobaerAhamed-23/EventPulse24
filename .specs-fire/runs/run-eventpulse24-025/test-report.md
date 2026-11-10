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

---

## Work Item: state-change-notice-model

### Test Results

| Suite | Result |
|---|---|
| `tests/delivery/test_state_notices.py` | **44 passed** (new file) |
| `tests/delivery/test_notice_mutes.py` | **14 passed** (new file) |
| `lint-imports` | **19 contracts kept, 0 broken** |
| `ruff check` / `ruff format` | clean |
| `manage.py check` | no issues |
| `makemigrations --check` | no changes detected — model and migration agree |
| `tests/architecture/` | **839 passed** |
| **Full backend suite** | **5395 passed, 8 failed** — all 8 pre-existing e2e |

**58 tests added**, plus one rewritten (see below).

### Tests proven able to fail

Twenty-two mutations, each applied, run, and reverted. **All twenty-two caught** — nineteen
on the first pass, the other three after the correction N9 forced.

| Mutation | Caught by |
|---|---|
| N1 cap uses `<` instead of `<=` | `test_an_equally_important_change_the_same_day_raises_nothing` |
| N2 cap never suppresses | `test_a_less_important_change_the_same_day_raises_nothing` |
| N3 version gate `>` instead of `>=` | `test_the_same_version_again_raises_nothing` |
| N4 mute ignored entirely | `test_a_muted_event_raises_nothing` |
| N5 mute also silences terminal changes | `test_a_terminal_change_reaches_a_muted_event` |
| N6 terminal changes capped like any other | `test_a_terminal_change_overrides_the_days_cap` |
| N7 `postponed` counts as terminal | `test_postponed_is_not_terminal` |
| N8 superseded notice's email left pending | `test_replacing_cancels_the_superseded_email` |
| N9a a duplicate crashes instead of answering | `test_the_callers_transaction_survives_a_refused_duplicate` |
| N9b catch moved inside the transaction | `test_a_refused_duplicate_does_not_leave_the_caps_deletions_behind` |
| N10 local date read in UTC | `test_the_day_is_the_users_day_not_the_servers` |
| N11 unknown kind ranks most important | `test_an_unknown_change_kind_outranks_nothing_and_does_not_raise` |
| N12 email on the bulk stream | `test_the_email_is_transactional_with_no_unsubscribe_url` |
| N13 Quiet Hours not applied | `test_quiet_hours_defer_the_notice` |
| N14 lead margin removed | `test_a_notice_is_not_deferred_past_the_point_of_being_useful` |
| N15 unmute reports a change it did not make | `test_unmuting_something_never_muted_reports_no_change` |
| N16 `muted_event_ids` ignores the user | `test_muted_event_ids_is_scoped_to_the_user` |
| N17 dismiss ignores the user | `test_dismissing_another_users_notice_does_nothing` |
| N18 `mark_seen` overwrites an earlier sighting | `test_seen_records_the_first_sighting_not_the_last` |
| N19 the strip ignores dismissal | `test_dismissing_removes_it_from_the_strip` |
| N20 the banner respects dismissal | `test_a_dismissed_notice_still_shows_on_its_own_event` |

### Acceptance Criteria Validation

| Criterion | Status | Note |
|---|---|---|
| A notice entity in `personal`, `delivery`-owned, recording event, user, kind, version, seen | met | `StateChangeNotice`; "seen" is **two** columns — see corrections |
| One notice per event per user, never repeated; design states what a *different* kind does | met | Uniqueness is per **state change** (D2), held by `state_notice_change_uq`; a different kind is the cap's business, not this rule's |
| At most one notice per event per day, enforced in the write path and tested at the boundary | met | `PRECEDENCE`-resolved; `<=` boundary tested in both directions |
| The email is on the transactional stream, explicitly | met | `ScheduledSend.stream` has no default (AD-20); asserted, and N12 proves the assertion bites |
| No RFC 8058 unsubscribe URL, and none implied | met | `mint_state_notice` sets none; `render_state_notice` already returns `unsubscribe_url=None` |
| Quiet Hours apply with one exception; both branches tested, including an event starting inside the window | met | Margin is `REMINDER_SLOT_OFFSET["1hr"]`, reused not invented (D5) |
| A per-event mute, settable and clearable; reminders and digest untouched | met | `EventNoticeMute`; `test_a_mute_does_not_touch_the_events_reminders` |
| No global off switch, recorded as a decision | met | Recorded in `EventNoticeMute`'s docstring and `mutes.py`'s |
| Raised by propagation, not by the sweep | met by construction | `raise_state_notice` is published and uncalled until `propagation-consumer` |
| Tests: cap boundary; muted event whose reminders still fire; both sides of the Quiet-Hours exception; a repeated propagation raising exactly one | met | |

**One AC is met differently than written**: "a muted event raises no notice and sends no
email" holds for every change *except* a terminal one (D7), which was approved at Checkpoint 1
and is tested from both sides.

### Corrections made during execution

**1. A guard that could never run.** `raise_state_notice` had a second step checking whether a
notice for this `state_change_id` already existed. Mutation N9 survived, which exposed it as
unreachable: step 1 refuses anything whose `event_version` is at or above the stored one, and
a notice records the version of the change it came from — so a retry is always caught earlier.

It was also pretending to a job it could not do. Two workers propagating one change for one
user both pass a `SELECT`, because neither has committed. Only the unique constraint is
atomic. The guard was removed; the insert now meets the constraint and its refusal is the
answer.

**2. A bug in that fix, caught by the follow-up mutation.** The `IntegrityError` was first
caught by a savepoint around the insert alone. N9b showed what that costs: the cap runs
*before* the insert and **deletes** the day's less important notices, cancelling their emails.
With a savepoint around only the insert, the surrounding block still commits — so a refused
duplicate would leave the user having lost a notice that was already raised and already due
to send, in exchange for one that was never created. The catch moved outside the transaction
so the whole block rolls back together.

**3. A hand-built send key, caught while writing it.** `_supersede` originally filtered on
`f"{user_id}:state_notice:{change_id}"` — a second spelling of AD-7's key. It would have
cancelled nothing the day `send_keys` changed, silently, because a filter matching no rows
raises nothing. It calls `state_notice_key` now.

**4. `_zone_for` published rather than copied.** The cap needs the user's zone to date a
notice. Two private copies of that fallback already existed (`scheduled_sends`,
`reminder_plan_read`); a third would have been a third place for it to drift. Renamed to
`zone_for` and exported; two call sites.

**5. Two Quiet-Hours comments corrected (D5a).** `models.py` and `scheduled_sends.py` both
said a `state_notice` has *"no slot and no Quiet-Hours arithmetic"*. The first half is right
and the second is not — `shift_to_sendable` takes any aware instant, and nothing in it is
slot-specific. This is the sentence that made the capture decision look like a contradiction
with the shipped code. Both now say what is actually true: no *slot*, and the rewrite skips
the row because the unshifted instant is the change itself, which is in the past and never
moves.

### Four failures the targeted runs could not have caught

The per-file runs were green; the full suite was not. All four were in
`tests/architecture/` or were tree-wide guards, which is exactly the class a targeted run
cannot see.

**1. AD-7 broken, and the rule was right.** `state_notices._supersede` wrote `SCHEDULED_SEND`
directly. The detector is deliberately coarse — importing the model attributes *every* write
in the module to it, on the reasoning that "a module that does not import the model cannot be
writing it". The fix is what AD-7 wants anyway: the cancellation moved to the schedule's owner
as `scheduled_sends.cancel_state_notice_sends`, and `state_notices` no longer imports
`ScheduledSend` at all. One module decides which notices lose to a more important change;
another owns what is due.

**2. Two unowned tables.** `TABLE_OWNERS` did not claim `delivery_statechangenotice` or
`delivery_eventnoticemute`. Both registered, with the reasoning recorded: the mute is set from
`personalization`'s Detail screen, but the preference is about a *delivery*, so it lives beside
the notice it silences.

**3. A guard that had done its job.** `test_the_state_notice_is_not_minted_by_the_delivery_app`
existed because the template was written an intent ahead of its trigger. This item fills that
gap, so the test was rewritten as its inverse —
`test_the_state_notice_is_minted_in_exactly_one_place` — keeping the invariant that actually
mattered (one minting path, AD-7) now that the feature exists. Deleting it would have dropped
a real guard along with the obsolete one.

**4. Two stale docstrings.** `email_templates` claimed "Rendered but not minted — FR-53/54 is
the next intent's work" in two places and in its module table. Corrected, and
`render_state_notice` now records that its subject is still `Update: {title}` rather than
FR-54's four verbatim ones — so item 7 inherits a note instead of a surprise.

### Investigations that settled the two open questions

**Quiet Hours — the decision was right, the docstring was wrong.** See correction 5. No
behaviour was in conflict; one comment overreached.

**FR-54's cap cannot live in the send key, and it is not an edge case.**
`ingestion/services/event_writes.py:245` appends **one `EVENT_STATE_CHANGE` per kind** inside
a single poll, versions `v+1..v+k`. A source update that moves an event's time *and* marks it
sold out already produces two notices seconds apart — so the cap is the common case for any
multi-field change, not a rare burst. Re-keying on `(event, local_date)` would make a
cancellation collide with a sold-out minted earlier the same day and be dropped as a
duplicate. The key stays AD-7's; the cap is a mint-time rule resolved by `PRECEDENCE`.

### Amendments raised

- **PRD (FR-54):** "The notification is one-time per event; never repeats" contradicts its own
  testable bullet "at most one per event per day", which presumes repeats, and its four
  consequence bullets, which expect distinct notices. Should read "one-time per state change".
- **PRD (FR-54), D7:** a terminal change overriding the cap and the mute exceeds the literal
  wording. Deliberate, bounded at two emails per event per day, approved at Checkpoint 1.

### Carried forward

- **FR-54's four subjects are verbatim and `EventPulse24: `-prefixed**; `render_state_notice`
  currently produces `Update: {title}`. Item 7 (`notice-composition-and-email`) is an edit,
  not a fresh template pass.
- **FR-54 names no subject for `postponed`, `reinstated` or `superseded`**, which `ChangeKind`
  has. Item 7 needs three more written, or three kinds mapped onto the existing four.

---

## Work Item: propagation-consumer

### Test Results

| Suite | Result |
|---|---|
| `tests/worker/test_propagation.py` | **29 passed** (new file) |
| `tests/worker/test_propagation_tasks.py` | **11 passed** (new file) |
| `tests/ingestion/test_outbox.py` | **8 passed** (5 pre-existing + 3 new) |
| `tests/worker/test_scheduling_tasks.py` | **18 passed** (17 pre-existing + 1 new) |
| `lint-imports` | **19 contracts kept, 0 broken** |
| `ruff check` / `ruff format` | clean |
| `manage.py check` | no issues |
| `makemigrations --check` | no changes detected — the design's central claim, held |
| `tests/architecture/` | **840 passed** |
| **Full backend suite** | **5429 passed, 16 failed** — all 16 pre-existing (see below) |

**43 tests added.** Four were added during code review, pinning what it surfaced.

### Tests proven able to fail

Each mutation was applied to the source, the suite run, and the source restored.

| Mutation | Caught by |
|---|---|
| The consumer adds a gate of its own | 18 tests, incl. `test_two_changes_racing_on_one_event_leave_the_newer_effect` |
| The version handed to the lifecycle is the target's, not the change's | `test_a_sold_out_change_still_restamps_and_releases_the_sends` |
| `CANCEL` releases the held rows instead of cancelling them | 4 tests, incl. `test_a_cancellation_releases_the_held_rows_it_cancels` |
| The catalog is read once per user instead of once per change | `test_the_catalog_is_read_once_for_the_whole_change` (4 reads vs 1) |

The first mutation is the one that matters most: **18 tests caught a gate the design says
must not exist.** That is the evidence for D1 — the design's central claim is that the version
gate inside the services is sufficient, and a suite that breaks when a second gate is added is
what "sufficient" looks like when it is proven rather than asserted.

### Acceptance Criteria Validation

| Criterion | Status | Note |
|---|---|---|
| Reads the change, resolves the users through the reverse read, applies per user in one `personal` transaction each | met | `propagate` → `_apply_to_savers` → `_apply_to_user`; each service owns its own transaction |
| Applies only if `event_version` exceeds the version on the `SavedEvent` — the gate inside the services, not duplicated | met | The consumer adds no gate; a mutation adding one breaks 18 tests |
| Writes nothing itself; every mutation through a published service | met | AD-16; the module imports no app's models |
| No transaction spans `catalog` and `personal` (AD-3) | met | The order is documented and the crash window is survivable by construction |
| `mark_propagated` only once every affected user is done | met | `test_a_failing_user_leaves_the_change_unpropagated` |
| All seven kinds handled per `LIFECYCLE_SEND_BEHAVIOUR` | met | `test_the_two_behaviour_maps_cover_the_same_kinds`; the personal side's map is total and has no default |
| **Held rows are released** | met | `test_a_sold_out_change_still_restamps_and_releases_the_sends` (KEEP), `test_a_time_move_releases_the_held_rows_it_replaces` (REMINT), `test_a_cancellation_releases_the_held_rows_it_cancels` (CANCEL) |
| Queues one FR-54 notice per affected user, respecting mute and the one-per-day cap | met | The mute and the cap live inside `raise_state_notice`; this item calls it |
| Idempotent under every failure shape | met | Full re-run; partial run retried; older after newer; two changes racing |
| A change affecting no users marks propagated and does nothing else | met | `test_a_change_nobody_saved_marks_propagated_and_touches_nothing` |
| The backlog drains through the reconciler | met | `test_the_backlog_drains_through_the_reconciler` |

### Corrections made during execution

**1. The design's checklist said the residual-window test was "not deferred again".** It was
still owed from `held-for-propagation-status`, and it is here now:
`test_a_send_claimed_before_the_change_commits_can_still_go_out`. The seam the earlier item
lacked exists because the notice does.

**2. Two acceptance criteria were not pinned, and code review found them.** The work item asks
for held rows released by the three behaviours, and for two changes racing. The suite had the
`KEEP` case and the *sequential* out-of-order case — the parallel one and the `REMINT`/`CANCEL`
cases were missing. All three added, and each was verified to fail under a mutation. The
`CANCEL` mutation (release instead of cancel) caught **four** tests, two of them pre-existing:
a held row that stayed `pending` would be picked up by the next sweep and sent — a reminder
for an event that is not happening.

**3. An N+1 against a batch API, on the one path that scales with the saver count.**
`_current_start` called `get_public_events` — a read that exists precisely to batch — once per
user, so a change to an event with 1000 savers cost 1000 identical catalog reads. Hoisted to
one read per change and threaded through as a value, which also keeps it out of the per-user
transaction. Pinned by `test_the_catalog_is_read_once_for_the_whole_change`.

**4. Three stale docstrings, all saying the consumer did not exist.** `state_notices`'s
`raise_state_notice` said it was "not wired to `propagate_state_change` yet";
`scheduled_sends`'s module docstring said the same; `email_templates` said the notice was
"rendered but never minted". All three were true when written and are false now. Corrected to
say what is true instead — which is the only reason a docstring is worth maintaining.

### Pre-existing failures (not caused by this work item)

**16 failures, reproduced identically on stashed code** (the baseline run, same commit, same
fixtures). They are date-expired fixtures, the same defect class the earlier items recorded:

| Suite | Failures | Cause |
|---|---|---|
| `tests/e2e/test_timeline_and_conflict_proof.py` | 8 | Fixtures pinned to `2026-11-05`/`2026-11-06` instants that have since passed |
| `tests/e2e/test_save_race.py` | 4 | Same class |
| `tests/e2e/test_personal_events_and_saved_catalog.py` | 1 | Same class |
| `tests/delivery/test_reminder_plan_api.py` | 1 | Same class — the `5d`/`2d` slots are now in the past |
| `tests/ingestion/test_url_feed_read.py` | 1 | Same class — a `last_modified` pinned to `2026-11-06` |

**The count grew from 8 to 16 between the previous item's report and now**, and it grew
entirely by the date rolling over, not by this work: the baseline run on stashed code fails
the same 16. They belong to `timeline-and-conflicts` and block CI on any branch until fixed.
Recorded here rather than silently absorbed, because "the suite is green except for the ones
that were already red" is only true if the red ones are enumerated.

### Carried forward

- **FR-54's four subjects are verbatim and `EventPulse24: `-prefixed**; `render_state_notice`
  still produces `Update: {title}`. Item 7 (`notice-composition-and-email`) is an edit, not a
  fresh template pass. Unchanged by this item, which raises notices but does not compose them.
- **FR-54 names no subject for `postponed`, `reinstated` or `superseded`**, which `ChangeKind`
  has. Item 7 needs three more written, or three kinds mapped onto the existing four.

---

## Work Item: digest-card-state-fields

**Mode:** confirm · **Tests added:** 11 · **Mutations proven able to fail:** 5

### The change

Two fields, read live and joined in:

- `PublicEvent` gains `is_sold_out` (`catalog_read.py`) — the same fact `PublicEventDetail`
  already carried, on the one read the digest already joins.
- `DigestCard` gains `status: str | None` and `is_sold_out: bool | None` (`digest_read.py`).
- `DigestCardOut` gains the same two (`schemas.py`), and the endpoint passes them through
  (`api.py`).
- The OpenAPI schema and the TypeScript client are regenerated.

**Nothing was stored.** `DigestComposition` is untouched, and `makemigrations --check` reports
no changes detected — which is the point. A status written at composition time would be frozen
there, and an event cancelled at noon would keep showing as live until tomorrow's digest.

### Results

| Suite | Result |
|---|---|
| `tests/personalization/test_digest_api.py` | **42 passed** (33 pre-existing + 9 new) |
| `tests/api/test_catalog_read_service.py` | **25 passed** (22 pre-existing + 3 new) |
| `tests/api/test_contract.py` + `test_openapi.py` | **3 passed** |
| `tests/architecture/` | **840 passed** |
| `tests/personalization/` + `tests/ingestion/` + `tests/api/` | **2188 passed**, 1 pre-existing failure |
| Full backend suite | **5440 passed, 16 failed** — all 16 pre-existing |
| `lint-imports` | **19 kept, 0 broken** |
| `ruff check` / `ruff format --check` | **All checks passed!** / **524 files already formatted** |
| `makemigrations --check --dry-run` | **No changes detected** |
| `tsc --noEmit` (frontend) | **exit 0** |

### Mutations

Each was applied, run, and reverted.

| # | Mutation | Caught by |
|---|---|---|
| 1 | `_card_for_public` hardcodes `status="scheduled"` — the frozen-status failure | **4 tests** |
| 2 | `_card_for_public` hardcodes `is_sold_out=False` | **1 test** |
| 3 | The personal branch defaults to `status="scheduled", is_sold_out=False` | **1 test** |
| 4 | The "catalog event gone" branch defaults to `status="scheduled", is_sold_out=False` | **1 test** |
| 5 | `_to_public_event` hardcodes `is_sold_out=False` — the flag never travels | **3 tests** |

Mutation 1 is the important one: it is exactly the defect the item exists to prevent, and four
tests fail on it — including `test_a_state_change_after_the_composition_is_reflected`, which
writes the composition *before* the cancellation and reads it *after*. That test is the item's
third acceptance criterion, made executable.

Mutations 3 and 4 are the two `None` branches. They are worth pinning because "not applicable"
and "fine" are different facts, and a client that cannot tell them apart will draw a sold-out
badge on the user's own dentist appointment.

### Acceptance criteria

| Criterion | Evidence |
|---|---|
| `DigestCardOut` carries the lifecycle status and the sold-out flag, in the backend's existing vocabulary | `schemas.py`; `Event.Status` unchanged; `is_sold_out` separate from the status. Pinned by `test_the_status_and_the_sold_out_flag_are_separate_facts` |
| Filled from the composition path, not from a per-card read at render time | The read already batched `get_public_events` into one map and joined the `PublicEvent` into the card. **No new query** — the query-count tests still pass unchanged (`test_the_query_count_does_not_grow_with_the_number_of_cards`) |
| A card for an event whose state changed after composition reflects the change | `test_a_state_change_after_the_composition_is_reflected`. Mutation 1 fails it |
| Whether a cancelled event remains in the digest is settled against FR-55 | Settled elsewhere and consistent: `digest_candidates.py:336` drops a cancelled save at the **candidate** stage, so a newly cancelled event is never composed. A card composed *before* the cancellation stays and says `cancelled` — pinned by `test_a_cancelled_card_says_cancelled_and_stays_on_the_digest`, which also asserts the explanation (bucket, tags) is untouched |
| The schema change regenerates the OpenAPI contract and the frontend client (AD-19) | `make client` run; `frontend/lib/api/openapi.json` and `frontend/lib/api/schema.ts` regenerated; `test_contract.py` passes |
| Contract tests for a live card, a sold-out card, a postponed card, and a cancelled card | Four tests, one per state, plus a personal card and a gone-event card |

### Corrections made during the work

**1. The "state change after composition" test needed a version bump.** The catalog's
`guard_event_write` trigger refuses a lifecycle change without one, so the test's
`event.status = "cancelled"; event.save()` was refused. The test now bumps `event_version`
first — the way production does. Worth recording because the *naive* version of this test would
have looked like it worked while silently changing nothing.

**2. The frontend's vitest cannot start in this environment.** `Failed to start forks worker` —
an `undici` module error, before any test runs. Reproduced identically on stashed code, so it
is not caused by this change. The meaningful check for a type-only change is `tsc --noEmit`,
which exits 0.

### Pre-existing failures (not caused by this work item)

**16 failures, reproduced identically on stashed code.** The same date-expired fixtures the
previous item recorded:

| Suite | Failures |
|---|---|
| `tests/e2e/test_timeline_and_conflict_proof.py` | 9 |
| `tests/e2e/test_save_race.py` | 4 |
| `tests/e2e/test_personal_events_and_saved_catalog.py` | 1 |
| `tests/delivery/test_reminder_plan_api.py` | 1 |
| `tests/ingestion/test_url_feed_read.py` | 1 |

Verified by stashing the change and re-running exactly those five files: **the same 16 fail.**
The count is up one from the previous item's report (15 → 16) because the calendar rolled over
and one more fixture expired. Not caused by this work; it belongs to `timeline-and-conflicts`
and blocks CI on any branch.

### Carried forward

- **The Pulse Card does not yet render either field.** `frontend-pulse-card-state` is the item
  that does it, and it depends on this one. The API now carries the facts; nothing displays
  them yet.
- **FR-54's four verbatim subjects** and the `postponed`/`reinstated`/`superseded` gap are
  unchanged — they belong to `notice-composition-and-email`.

---

## Work Item: polling-cadence-floors

**Mode:** confirm · **Tests added:** 55 · **Mutations proven able to fail:** 17

### The change

FR-53's guarantee, enforced in three places and checked in a fourth:

- **`shared/constants.py`** — `HIGH_PRIORITY_METHODS = ("api", "partnership")`,
  `HIGH_PRIORITY_CADENCE_MAX = 4h`, `LOW_PRIORITY_CADENCE_MAX = 24h`.
- **`domain/sources.py`** (new) — the derivation, in one place: `source_priority(method)`,
  `cadence_ceiling(method)`, `humanise_duration(duration)`.
- **`apps/ingestion/models.py`** — `source_cadence_within_priority_ceiling_ck`, a check
  constraint on the table itself.
- **`apps/ingestion/migrations/0007_source_cadence_ceiling.py`** (new) — clamps the rows that
  break the rule, *then* adds the constraint (the order matters: `AddConstraint` validates
  existing rows).
- **`apps/ingestion/services/source_registry.py`** — the ceiling in the cadence cleaner, and
  the method-change re-check.
- **`apps/ingestion/services/scheduling.py`** — `report_cadence_floor_breaches(now)`.
- **`worker/tasks.py`** — the tick asks for the count and logs a warning when it is non-zero.
- **`apps/ingestion/admin.py`** — the form's help text explains the ceiling.

### Results

| Suite | Result |
|---|---|
| `tests/ingestion/test_source_registry.py` | **98 passed** (69 pre-existing + 29 new) |
| `tests/ingestion/test_scheduling.py` | **41 passed** (24 pre-existing + 17 new) |
| `tests/ingestion/test_models.py` | **58 passed** (52 pre-existing + 6 new) |
| `tests/ingestion/test_migrations.py` (new) | **12 passed** |
| `tests/e2e/test_state_detection_window.py` (new) | **7 passed** |
| `tests/worker/test_scheduling_tasks.py` | **20 passed** (18 pre-existing + 2 new) |
| `lint-imports` | **19 kept, 0 broken** |
| `ruff check` / `ruff format --check` | **All checks passed!** / **528 files already formatted** |
| `makemigrations --check --dry-run` | **No changes detected** |
| Full backend suite | **5519 passed, 16 failed** — all 16 pre-existing |

### Mutations

Each was applied to the source, the suite run, and the source restored.

| # | Mutation | Caught by |
|---|---|---|
| 1 | The ceiling is not enforced in the cleaner (`if False:`) | **4 tests** |
| 2 | Every method uses the daily ceiling | **4 tests** |
| 3 | A method change does not re-check the stored cadence | **3 tests** |
| 4 | The migration's constraint never refuses anything | **29 tests** |
| 5 | The floor check counts the last **attempt**, not the last success | **5 tests** |
| 6 | The floor check never fires | **6 tests** |
| 7 | The lower tier is measured against the four-hour window | **4 tests** |
| 8 | The scheduler's cadence filter slips (2× the cadence) | **9 tests** |
| 9 | The migration clamps nothing | **8 tests** |
| 10 | The migration clamps the wrong tier | **9 tests** |
| 11 | The worker stops asking for the breach count | **2 tests** |
| 12 | The warning fires even on a zero count | **1 test** |
| 13 | The tier derivation is inverted | **14 tests** |
| 14 | The cleaner measures the cadence against the **stored** method | **4 tests** |
| 15 | The model's constraint drifts from the migration's | **`makemigrations --check`** (exit 1) |
| 16 | The method's default cadence skips the ceiling check | **2 tests** |
| 17 | The default is checked against the wrong tier | **1 test** |

**Mutation 8 is the one that matters most.** It breaks the *scheduler's* cadence filter — the
exact defect FR-53 exists to prevent — and nine tests fail, three of them the consequence
test's own boundary assertions. A scheduler that polled every eight hours would still pass a
test that only asserted "the constant is four hours".

**Mutation 5 is the one that proves the floor check is not a duplicate of the stale flag.** It
swaps `last_ingested_at` for `last_attempted_at` — the exact confusion the item's design
discussed — and five tests fail, including
`test_the_floor_counts_the_failure_case_the_stale_flag_is_too_late_for`, which is the case the
two signals differ on: a high-priority source polled every four hours that keeps failing. The
stale flag has not fired (it waits for 2× the cadence); the floor check has, because the
guarantee is about detection.

**Mutation 15 is caught by a different tool, and that is worth recording.** The test database
is built from the **migration**, not from the model, so mutating the *model's* constraint
survives the suite. What catches it is `makemigrations --check`, which reports the drift and
exits 1:

```
Migrations for 'ingestion':
  apps/ingestion/migrations/0008_remove_source_..._and_more.py
    - Remove constraint source_cadence_within_priority_ceiling_ck from model source
    + Create constraint source_cadence_within_priority_ceiling_ck on model source
```

**So the constraint has two independent guards, each with its own catcher**: the migration
(which builds the schema the tests run against) and the model (which `makemigrations --check`
holds to the migration). Mutation 4 attacks the first and is caught by 29 tests; mutation 15
attacks the second and is caught by the check.

### Acceptance criteria

| Criterion | Evidence |
|---|---|
| A cadence above the tier's ceiling is **rejected where it is written**, not discovered later | `source_registry.py`'s `_cadence` — the one place every write path reaches. Pinned by `test_register_high_priority_source_over_its_ceiling_refused` and its lower-tier twin; the refusal is a `ValidationError` naming `ingestion_cadence`, and `_nothing_written()` asserts the row was not created |
| The tier is **derived**, not stored — no second source of truth | `domain/sources.py`'s `source_priority(method)`; the derivation is from `acquisition_method`, FR-17's own order. Mutation 13 inverts it and 14 tests fail |
| A method change that would leave the row over the new tier's ceiling is refused | `_check_stored_cadence_against_new_tier` — the case the cleaner cannot see, because a method-only change carries no cadence. Pinned by `test_update_source_to_a_higher_tier_without_a_cadence_refused` (and refused), `..._with_a_legal_cadence_accepted` (and accepted) |
| Existing rows are brought within the rule by a **migration**, not by hand | `0007_source_cadence_ceiling.py` clamps, then adds the constraint. `tests/ingestion/test_migrations.py` asserts the clamp, the untouched legal row, the report line, and that the migration and the application agree on the ceiling |
| The scheduler honours the cadence | Already true; now asserted by `test_a_high_priority_source_is_polled_inside_its_four_hour_window` and the boundary pair. Mutation 8 breaks it and nine tests fail |
| A cadence guarantee nobody is checking is worse than no guarantee | `report_cadence_floor_breaches` + the worker's warning. Mutation 6 (never fires) and mutation 11 (the worker stops asking) each fail tests |
| **A test that can fail on the FR-53 consequence itself** — not a test that the constant equals four | `tests/e2e/test_state_detection_window.py`. It drives the real `claim_due_sources` and the real `ingest_source`, and asserts the boundary from **both** sides: not due at `cadence - 1s`, due at `cadence` |

### Corrections made during the work

**1. `ingestion_cadence` was dropped from `_CLEANERS`, and the cleaner then refused every
cadence.** The ceiling needs the effective method, and a flat field → cleaner map has nowhere
to carry it, so `ingestion_cadence` was moved out of `_CLEANERS` into a branch of
`clean_source_input`. But the branch was written *after* the `field not in _CLEANERS` guard,
so every cadence was rejected as "This field can't be changed here." Fifteen tests failed at
once. The branch now comes first. Worth recording because the failure looked like a policy
refusal rather than a control-flow mistake.

**2. The boundary is inclusive, and the first test asserted the opposite.** `report_cadence_floor_breaches`
uses `__lte`, so a source last ingested exactly its ceiling ago **is** a breach — the same
convention `flag_stale_sources` uses ("exactly 2x is stale"), and the same reading of "detected
*within* 4 hours": at the instant the window closes, the promise has expired. The first test
asserted the opposite and failed. The implementation was kept and the test corrected, and the
boundary is now stated in the docstring so the next reader does not have to re-derive it.

**3. A `crawl` source moved to `api` now needs its cadence brought along.** `crawl`'s default
cadence is 24 hours and `api`'s ceiling is 4, so the method change alone would leave the row
illegal. `test_update_source_crawl_to_api_needs_no_review` asserted the old behaviour and now
brings a 4-hour cadence with the change. **This is a real behaviour change to an existing
test, and it is the item working as designed** — the row must be legal after the write,
whichever field changed.

**4. The consequence test is split into two halves, and the reason is real.** No
high-priority method has a parser — `api` and `partnership` have no adapter in this codebase
(`PARSERS` holds `jsonld`, `rss`, `ics`, `email_ics`) — so a high-priority source cannot be
ingested today. A single test driving both halves at once would have had to fake the parser,
and **faking the parser would make the test prove a fiction.** So the scheduler half is proved
on a high-priority source (`api`), the detection half is proved on a source whose method has a
parser (`ics`), and the file says so at the top.

### Review findings, and what they cost

The code review found two things the tests had not caught, and both are now fixed and
mutation-covered:

| Finding | Fix | New tests | New mutations |
|---|---|---|---|
| The method's **default** cadence skipped the cleaner entirely — it was applied after `check_source_change` had run | The default now goes through the same cleaner, and the refusal is raised in the shape the caller handles (`_checked_cadence`) | 3 | 2, both caught |
| The floor check's boundary was inclusive and the first test asserted the opposite | The implementation was kept (it matches `flag_stale_sources`'s convention and the right reading of "within 4 hours"); the test was corrected and the boundary documented | 2 (one split into two) | — |

**The default-cadence finding is the one worth naming.** Every default is currently inside its
tier's ceiling, so nothing was broken — but nothing enforced it either. A future default
above its ceiling would have produced an `IntegrityError` at registration, in production,
instead of a refusal with a message. Three tests now hold that: one asserts every shipped
default is inside its own ceiling, one proves an over-ceiling default is *refused* rather
than written, and one proves the default is measured against **its own** tier (a 12-hour
default is illegal for `api` and legal for `rss` — so a check against the wrong tier is
caught in one direction or the other).

### Pre-existing failures (not caused by this work item)

**16 failures, reproduced identically on stashed code.** The same date-expired fixtures the
previous two items recorded:

| Suite | Failures |
|---|---|
| `tests/e2e/test_timeline_and_conflict_proof.py` | 9 |
| `tests/e2e/test_save_race.py` | 4 |
| `tests/e2e/test_personal_events_and_saved_catalog.py` | 1 |
| `tests/delivery/test_reminder_plan_api.py` | 1 |
| `tests/ingestion/test_url_feed_read.py` | 1 |

Verified by stashing the change and re-running `tests/ingestion/test_url_feed_read.py`: **the
same failure, identically.** Not caused by this work; it belongs to `timeline-and-conflicts`
and blocks CI on any branch.

### Carried forward

- **No high-priority source can be ingested today.** `api` and `partnership` have no adapter
  and no parser. The high tier's 4-hour window is enforced and tested, but the *detection* it
  promises cannot happen until an adapter exists. The consequence test says this at the top
  rather than papering over it.
- **The floor check is a count, and a count is not a fix.** A breach says the promise is at
  risk; nothing yet says which source, to whom, or what to do. The registry's admin surface
  (`list_display`, `is_stale`) is where that would land.
- **FR-53's webhook half is untouched.** Polling is the fallback; the near-real-time path
  needs an adapter that does not exist. Out of scope for this intent, and recorded at capture.

---

## Work Item: notice-composition-and-email

**Mode:** confirm · **Tests added:** 38 · **Mutations proven able to fail:** 9

### The change

FR-54's four PRD-verbatim subjects, the body that says what changed *and* what it means for
the user's reminders, and the rule that a `detail_changed` which did not move the venue is
not worth an email.

- **`domain/notices.py`** — `MISSING_TITLE` ("your saved event"), and `fold_title`, which
  collapses a whitespace run so a folded name is quoted identically by the subject and the
  body.
- **`domain/notices.py`** — `notice_subject(kind, title, when, where)` builds the subject
  from the vocabulary; an unknown kind raises rather than producing a generic subject.
- **`apps/delivery/services/email_templates.py`** — `StateNoticeFacts` grows
  `previous_time_text`, `venue_name`, `detail_url` and `reminder_consequence`;
  `render_state_notice` builds the subject through `notice_subject`.
- **`apps/delivery/templates/delivery/state_notice.{txt,html}`** — rewritten. The body says
  what changed (new time, previous time, new venue) and what it means for the reminders
  (the consequence sentence).
- **`apps/delivery/send_keys.py`** — `state_change_id_from_key`, the parser beside the
  builder. `ScheduledSend` has no `state_change_id` column; AD-7 put it in the key.
- **`apps/delivery/services/delivery_messages.py`** — `renderer_for` dispatches a
  `STATE_NOTICE` row to `render_state_notice`; `_state_notice_facts` assembles the facts from
  the change row, the catalog event and the parsed send key.
- **`apps/delivery/services/state_notices.py`** — `raise_state_notice` takes the change's
  `before`/`after` facts and refuses a `detail_changed` that did not move the venue.
- **`worker/propagation.py`** — passes `before=change.before, after=change.after` through.

**No migration and no new column.** `makemigrations --check` reports no changes detected.

### Results

| Suite | Result |
|---|---|
| `tests/delivery/test_state_notice_email.py` (new) | **34 passed** |
| `tests/delivery/test_state_notices.py` | **48 passed** (44 pre-existing + 4 new) |
| `tests/delivery/test_email_templates.py` | **21 passed** (17 pre-existing + 4 rewritten) |
| `tests/delivery/` + `tests/architecture/` + `tests/worker/` | **1589 passed**, 1 pre-existing failure |
| `lint-imports` | **19 kept, 0 broken** |
| `ruff check` / `ruff format --check` | **All checks passed!** / **530 files already formatted** |
| `makemigrations --check --dry-run` | **No changes detected** |
| Full backend suite | **5559 passed, 16 failed** — all 16 pre-existing |

### Mutations

Each was applied to the source, the suite run, and the source restored.

| # | Mutation | Caught by |
|---|---|---|
| 1 | `fold_title` returns the raw title (no whitespace collapse) | `test_a_name_with_a_newline_in_it_cannot_inject_a_header` |
| 2 | The subject falls back to a generic string for an unknown kind | `test_an_unknown_kind_raises_rather_than_producing_a_generic_subject` |
| 3 | `MISSING_TITLE` is dropped from the subject | `test_a_missing_name_says_your_saved_event` |
| 4 | The body omits the previous time | `test_the_state_notice_says_what_changed_and_what_it_was` |
| 5 | The body omits the reminder consequence | `test_the_body_says_what_it_means_for_the_reminders` (parametrized over all 7 kinds) |
| 6 | `notice_subject` is given the old time instead of the new one | `test_a_time_move_row_says_the_new_time_in_the_subject` |
| 7 | A `detail_changed` that moved the venue is silenced | `test_a_detail_change_that_moved_the_venue_is_notified` |
| 8 | Every `detail_changed` is notified | `test_a_detail_change_that_did_not_touch_the_venue_is_not_notified` |
| 9 | A silenced `detail_changed` still consumes the day's cap slot | `test_a_silenced_detail_change_does_not_consume_the_days_cap` |

**Mutation 8 is the one that matters most**, because it is the *tempting* implementation. The
PRD's third subject is "moved to [new location]", and the only kind that carries a venue is
`detail_changed` — so the easy reading is "notify on `detail_changed`". Mutation 8 proves
that reading is wrong in the direction that matters: a title typo fix is not an email, and
a suite that breaks when it is notified is what FR-53 ("not every change deserves a
notification") looks like when it is proven rather than asserted.

**Mutation 9 is the one that proves the silence happens at the right place.** Silencing at
the *source* — in `raise_state_notice`, before the row is written — means a silenced change
consumes neither the day's one-notice cap nor a strip entry saying nothing. Silencing later,
in the renderer, would have left the user's notice strip carrying an entry with no mail
behind it.

### Acceptance criteria

| Criterion | Evidence |
|---|---|
| The four PRD subjects, verbatim, prefixed `EventPulse24: ` | `domain.notices.NOTICE_SUBJECTS`; seven literal assertions in `test_state_notice_email.py`, one per kind, and `test_every_kind_has_a_subject` |
| The PRD names no subject for `postponed`, `reinstated` or `superseded` | Three further subjects written — "was moved to [new date]", "was replaced by a new event", "is back on" — and each pinned by its own test. The PRD's three that *are* named are used verbatim and the three that are not are marked ours in the file's table |
| The body says what changed | New time, previous time, new venue; a missing fact is omitted rather than shown as empty |
| The body says what it means for the reminders | The consequence is **derived** from `LIFECYCLE_SEND_BEHAVIOUR`, so the body cannot promise something the send machinery did not do. Parametrized over all seven kinds, with `reinstated`'s override written out |
| A name is never injected into a header | `fold_title` collapses whitespace runs before the facts reach the renderer; the subject and the body quote the same folded name |
| A missing name says "your saved event" | The same phrase the reminder body already uses, so two mails from one product do not say it two ways |
| The notice carries no RFC 8058 unsubscribe URL | `unsubscribe_url=None`; the transactional stream |
| The mute is the opt-out, not an unsubscribe link | The body carries **no** "Stop reminders for this event" link — the Detail Screen it links to is where the mute lives |
| A `detail_changed` that did not move the venue is not notified | `is_notified` decides on the *change*, not the kind; a venue move is a `detail_changed` and is notified, a title edit is not |
| A superseded event links to its replacement | `after["superseded_by"]` — the superseded event's own Detail Screen is a 404 |
| One minting path | `test_the_state_notice_is_minted_in_exactly_one_place`, rewritten from a substring scan to an **AST-based** check of assignments, so a module that merely *reads* the kind to dispatch on it is not caught |

### Corrections made during the work

**1. A test that was testing the string, not the invariant.** The one-minting-path guard
scanned `apps/` for the text `STATE_NOTICE`. When `delivery_messages.py` began naming the
kind to dispatch a row on the right renderer, the guard fired — a **false positive**, because
a *reader* is not a second writer. Rewritten as an AST check that finds only *assignments* of
the kind (a `kind=` keyword, a `"kind":` dict key, or the enum's own declaration). The
invariant is unchanged and now provably narrower than the thing it was standing in for.

**2. Three tests were passing vacuously.** `test_a_less_important_change_the_same_day_raises_nothing`
and `test_a_more_important_change_replaces_the_days_notice` used `DETAIL_CHANGED` as a
convenient "the least important kind" — which, after correction 3 below, raises nothing at
all. They were asserting the cap on a notice that was never raised. Given venue-move facts
so they test the cap again. Two further tests that used the same convenience kind were
given venue facts too.

**3. The rule is about the change, not the kind.** The first implementation silenced
`detail_changed` wholesale. That is wrong in the direction the PRD names: "moved to [new
location]" **is** a `detail_changed` (`venue_fingerprint` is one of its detail facts), so
silencing the kind silences the PRD's third subject. `is_notified` now compares the
venue fingerprint in `before` and `after`, and decides on the *change*.

**4. The old venue cannot be named, only the new one.** A venue is identified by a
fingerprint — a hash — so "moved from [old location]" has no old location to print. The
subject names the **new** venue, read from the catalog at render time. Recorded here because
it is a deliberate narrowing of what the PRD's subject can say, not an oversight.

**5. A superseded event's Detail Screen is a 404.** The notice links to the **replacement**'s
Detail Screen (`after["superseded_by"]`). The body would otherwise send a user to a page
that cannot load.

### The subject table, and whose each subject is

`domain.notices.NOTICE_SUBJECTS` is the vocabulary, and `test_state_notice_email.py` pins
every entry against the whole rendering path — so "the vocabulary is right" and "the mail
that goes out says it" cannot come apart.

| subject | for | whose |
|---|---|---|
| `EventPulse24: [event name] was cancelled.` | a cancellation | PRD verbatim |
| `EventPulse24: [event name] was moved to [new date].` | a postponement or a time move | PRD verbatim |
| `EventPulse24: [event name] moved to [new location].` | **a venue move** | PRD verbatim |
| `EventPulse24: [event name] is sold out.` | a sell-out | PRD verbatim |
| `EventPulse24: [event name] was replaced by a new event.` | a supersede | ours |
| `EventPulse24: [event name] is back on.` | a reinstatement | ours |

The last three are ours because the PRD does not name them — a gap this item's predecessor
recorded and carried forward. The PRD's third subject has **no kind of its own**, which is
the fact correction 3 turns on.

### Pre-existing failures (not caused by this work item)

**16 failures, reproduced identically against a clean `git worktree` at `HEAD`.** The same
date-expired fixtures the previous three items recorded:

| Suite | Failures |
|---|---|
| `tests/e2e/test_timeline_and_conflict_proof.py` | 9 |
| `tests/e2e/test_save_race.py` | 4 |
| `tests/e2e/test_personal_events_and_saved_catalog.py` | 1 |
| `tests/delivery/test_reminder_plan_api.py` | 1 |
| `tests/ingestion/test_url_feed_read.py` | 1 |

Verified by building a worktree at `8d4fe74` (the same commit, the same fixtures) and
running `test_reminder_plan_api.py::test_a_saved_plan_and_its_sends_move_together` there:
**the identical failure**. Not caused by this work; it belongs to `timeline-and-conflicts`
and blocks CI on any branch.

### Carried forward

- **The notice strip and the Detail Screen banner do not exist yet.** This item composes
  and sends the mail; `frontend-digest-strip-and-detail-banner` renders it.
- **The mute is not reachable from the mail.** The body links to the Detail Screen, and the
  Detail Screen's mute is `notice-and-mute-api`'s job.
- **The old venue is never named** — a fingerprint is a hash. A subject naming both venues
  would need the catalog to keep the old name, which it does not.

---

## Work Item: notice-and-mute-api

**Mode:** confirm · **Tests added:** 67 · **Mutations proven able to fail:** 8

### The change

The in-app half of FR-54: the digest strip's read, the dismiss, FR-55's per-event mute, and
the Detail Screen's two new fields — so the banner and the mute control render from **one**
round trip.

- **`backend/apps/delivery/services/notice_state.py`** (new) — a **leaf** read module.
  `NoticeSummary`, `EventNoticeState`, `read_event_notice_state`, and the public
  `summarize_notice` projection. It reads the two models **directly** rather than through
  `state_notices` / `mutes`, so it cannot close the import cycle
  `personalization.detail_read → notice_state → state_notices → scheduled_sends →
  personalization`, and so the model never leaves `delivery`.
- **`backend/apps/delivery/notices_api.py`** (new) — the router, `auth=current_user`.
  Four handlers: `GET ""`, `POST /{notice_id}/dismiss`, `PUT` and `DELETE`
  `/events/{event_id}/mute`.
- **`backend/apps/delivery/services/state_notices.py`** — `list_undismissed_notices` gains a
  **required keyword-only `limit`**; new `notice_belongs_to_user`.
- **`backend/apps/delivery/schemas.py`** — `NoticeOut`, `NoticeListOut`, `NoticeDismissOut`,
  `EventMuteOut`.
- **`backend/apps/personalization/schemas.py`** — `DetailNoticeOut`; `DetailPersonalOut`
  gains `muted` and `notice`.
- **`backend/apps/personalization/services/detail_read.py`** — the two facts, read **after**
  the anonymous early return.
- **`backend/apps/personalization/detail_api.py`** — the two fields projected.
- **`backend/shared/constants.py`** — `NOTICE_STRIP_LIMIT = 5`.
- **`backend/config/api.py`** — the router mounted at `/api/notices`.

**No migration.** `makemigrations --check` reports no changes detected.

### Results

| Suite | Result |
|---|---|
| `tests/delivery/test_notices_api.py` (new) | **38 passed** |
| `tests/delivery/test_notice_state.py` (new) | **13 passed** |
| `tests/delivery/test_state_notices.py` | **48 passed** (44 pre-existing + 4 new) |
| `tests/personalization/test_event_detail_api.py` | **65 passed** (53 pre-existing + 12 new) |
| `tests/architecture/` | **858 passed** |
| `tests/api/` + `tests/e2e/test_delivery_contract.py` | **10 passed** |
| `lint-imports` | **19 kept, 0 broken** |
| `ruff check` / `ruff format --check` | **All checks passed!** / clean |
| `makemigrations --check --dry-run` | **No changes detected** |
| Full backend suite | **5637 passed, 16 failed** — all 16 pre-existing |

**67 tests added.** The baseline at `HEAD` (`8d4fe74`) is **5438 passed, 16 failed** on a
clean worktree — the same sixteen. **Zero new failures**, and 199 net new passing tests.

### Mutations

Each was applied to the source, the suite run, and the source restored.

| # | Mutation | Caught by |
|---|---|---|
| 1 | The route is `"/"` instead of `""` | Every strip test — a trailing-slash 301 |
| 2 | `limit` is dropped from the slice | `test_the_strip_is_bounded` |
| 3 | The slice keeps the **oldest** notices | `test_the_strip_keeps_the_newest_when_it_is_bounded` |
| 4 | `notice_belongs_to_user` is not user-scoped | `test_dismissing_another_users_notice_is_a_404` |
| 5 | The dismiss 404 is raised for an already-dismissed notice | `test_dismissing_an_already_dismissed_notice_is_a_success` |
| 6 | `read_event_notice_state` is hoisted above the anonymous early return | `test_the_anonymous_path_still_never_queries_the_personal_schema` |
| 7 | The read loops over the notices | `test_the_read_is_two_queries` |
| 8 | The Detail reports only an **undismissed** notice | `test_the_detail_reports_a_dismissed_notice_too` |

**Mutation 6 is the one that matters most.** `read_event_notice_state` is one line above the
place it belongs, and moving it one line up would be invisible to every other test — the
notice would still be reported, the mute would still be reported, and the response would be
identical for a signed-in user. The **only** thing that would change is that an anonymous
caller's request would touch the `personal` schema, which is the leak AD-12 forbids and the
existing `test_the_anonymous_path_never_queries_the_personal_schema` already guarded. The new
test restates that guard under this change's name so the property cannot be lost with it.

**Mutation 8 is the one the AC's wording would have got wrong.** Criterion 4 says "whether it
has an undismissed notice"; the service's own rule says the opposite — the banner is about
*this* event, and the user navigated here on purpose, so dismissing the strip on the digest
home must not hide *"this event was cancelled"* from the event's own page. The test pins the
service's rule, and `dismissed_at` is on the wire so the client can render the state.

### Acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| A read of the signed-in user's notices, newest first, bounded | met | `GET /api/notices` → `NOTICE_STRIP_LIMIT` items, newest first; one query; no `total`, no cursor |
| A dismiss write that makes "one-time, never repeats" true | met | `POST /api/notices/{id}/dismiss` sets `dismissed_at`; the row survives, so the daily cap and the never-repeat rule still hold |
| A mute set/clear write, per event (FR-55) | met | `PUT` / `DELETE /api/notices/events/{event_id}/mute`; no request body at all |
| The Detail read reports the mute and the notice in one round trip | met | `personal.muted` and `personal.notice`; both facts, one response, **two queries total** |
| Every endpoint is session-scoped | met | `auth=current_user` on the router, **and** four authorization tests — the scoping is tested, not assumed |
| Idempotent dismiss and mute answer success | met | `changed: false` on the no-op; `dismissed_at` unchanged; **one** row, not two |
| A notice for an un-saved event still reads and dismisses | met | The read never crosses to `catalog`; a mute for an unknown event is allowed on purpose |
| The OpenAPI schema regenerates and the client is rebuilt | met | `make openapi && make client`; `frontend/lib/api/openapi.json` and `frontend/lib/api/schema.ts` committed; `tests/api/test_contract.py` green |
| Contract tests cover each shape, the empty case, and the authorization case | met | `tests/delivery/test_notices_api.py` — 5 groups, 35 tests |

### Two ambiguities the AC left open, and how they were settled

**1. "Unseen" in criterion 1 — the strip is keyed on `dismissed_at`, not `seen_at`.**
The service's own rule is explicit (*"the strip is a queue, and closing an item should empty
it"*), and criterion 2's own wording says dismissal is what makes "one-time, never repeats"
true. A `GET` that writes `seen_at` is exactly the shape `detail_api.py` refuses (*"a `GET`
that writes is the shape CSRF exists to stop"*), so **`mark_seen` is not called by this API
at all.** `seen_at` is on the wire — it is a fact about the row — but it does not gate the
strip.

**2. "Undismissed notice" in criterion 4 — the banner reports the newest notice whatever
its dismissal state.** See mutation 8 above. `latest_notice_for_event` ignores `dismissed_at`
on purpose, and `dismissed_at` rides along so the client can tell the two apart.

### The dismiss 404-vs-idempotence resolution

`dismiss_notice` returns a `bool` that collapses three cases: not yours, does not exist,
already dismissed. Criterion 6 wants the third to answer success; criterion 5 wants the first
two refused. The resolution:

- `changed == True` → **200** `{id, dismissed: true, changed: true}` — **zero** extra queries.
- `changed == False` → one extra **user-scoped** existence check:
  - yours, already dismissed → **200** `{id, dismissed: true, changed: false}`
  - not yours, or no such id → **404**, and **the same 404 for both**.

A 403 would confirm that the record exists, so the endpoint could be used to probe for other
users' notice ids. The extra query is scoped by `user_id`, so it can only ever answer about
the caller's own notices — and it runs **only** on the `changed == False` path, so the common
case costs nothing.

### Corrections made during the work

**1. The route was `"/"`, and Django redirected.** `@router.get("/")` registers
`/api/notices/`; Django's `APPEND_SLASH` then answers `GET /api/notices` with a **301** to
the slashed path, which broke every strip test at once. Changed to `@router.get("")`, which
registers `/api/notices` exactly — confirmed in the regenerated `openapi.json`.

**2. A helper that returned the wrong thing.** The bounded-strip test read `raise_notice(...)`
as though it returned the notice row; it returns a `bool`. The test was reading the newest
row directly instead.

**3. `created_at` is `auto_now_add`, so the insert could not set it.** The ordering tests and
the wire-format assertion both needed a *stated* timestamp. The helper inserts, then
`.update(created_at=...)`, then `refresh_from_db()`.

**4. A pre-existing hole in an architecture guard, closed here.** `checkers.surface_files()`
globbed `apps/*/api.py`, which matches only files named exactly `api.py` — so
`apps/catalog/preview_api.py`, `apps/delivery/email_api.py`,
`apps/delivery/preferences_api.py` and `apps/personalization/detail_api.py` were **exempt
from AD-5**: nothing would have caught any of them writing through the ORM. The discovery is
now **by shape** (`admin.py`, `api.py`, `*_api.py`), the same rule
`test_digest_composition_separation.py` already used. The count goes **13 → 18**
(6 admins + 6 `api.py` + 5 `*_api.py` + `config/api.py`), and the four previously-unchecked
files were **checked for the first time** — all four pass.

**5. The AD-11 guard and the AD-5 guard needed different lists.** The first widening made
`surface_files()` include the admins, which broke
`test_the_request_modules_are_the_ones_we_think` — the AD-11 list is *routers*, not admins.
Split into two discoveries in `checkers.py`: `api_modules()` (routers only, used by AD-11)
and `surface_files()` (admins + routers, used by AD-5). **One rule, one discovery** — the two
guards can no longer disagree about what a request handler is.

**6. One projection instead of two.** `notices_api.py` first carried its own `_summary()`
helper, duplicating the strip card and the Detail banner's fields. Refactored so
`summarize_notice()` is public in `notice_state.py` and both surfaces use it — the strip card
and the banner carry the same fields **by construction**.

### Pre-existing failures (not caused by this work item)

**16 failures, reproduced identically against a clean `git worktree` at `HEAD`.** Verified by
building a worktree at `8d4fe74` and running the whole suite there: **5438 passed, 16 failed**
— the same sixteen, in the same files:

| Suite | Failures |
|---|---|
| `tests/e2e/test_timeline_and_conflict_proof.py` | 9 |
| `tests/e2e/test_save_race.py` | 4 |
| `tests/e2e/test_personal_events_and_saved_catalog.py` | 1 |
| `tests/delivery/test_reminder_plan_api.py` | 1 |
| `tests/ingestion/test_url_feed_read.py` | 1 |

(The baseline worktree also failed `tests/e2e/test_delivery_contract.py` — because it has no
`node_modules`. In the real tree that test passes: **10 passed** across `tests/api/` and
`tests/e2e/test_delivery_contract.py`.)

The same date-expired fixtures the previous five items recorded. It belongs to
`timeline-and-conflicts` and blocks CI on any branch.

### The corrections code review forced

The review found **three real defects and five coverage gaps**, all fixed — see
`review-report.md` for the full account. Three of them changed what this report counts,
so they are recorded here:

1. **A dead function and a duplicated query.** `state_notices.latest_notice_for_event` had
   no production caller once the combined read arrived, while `notice_state` re-implemented
   its query verbatim. It is **deleted**, the rule moved to `notice_state`, and the strip's
   read now uses the **same ordering** — so the strip card and the Detail banner cannot
   disagree about which notice is newest.

2. **A tiebreaker, and the test that pins it.** `order_by("-created_at")` had no secondary
   key, and a single ingestion poll can raise several notices at once — so two rows can
   share a `created_at`, and the database is free to return either. Both reads now order by
   `("-created_at", "-id")`; `-id` is the natural tiebreak because the primary key is a
   UUIDv7. Two new tests: one asserts a stable winner, the other asserts **the strip and
   the banner agree**.

3. **The query bound was wrong on the path nobody tested.** The conflict read is gated on
   the caller having saved the event, so a **saved** user costs **8** queries, not 6 — and
   all three `<= 6` assertions ran the unsaved path. The bounds are now named constants
   (`UNSAVED_READ_QUERIES = 6`, `CONFLICT_READ_QUERIES = 2`, `SAVED_READ_QUERIES = 8`),
   and a new test asserts the difference **relatively**: `saved == unsaved + 2`.

**Three more tests are the CSRF cases** — the dismiss, the mute and the unmute, each with a
plain client, each asserting 403 / `csrf_failed` *and* that the row did not change. The
whole file used a client that always sends a token, so the CSRF path had never been
exercised.

### Carried forward

- **The strip and the banner are not rendered yet.** This item builds the API they read;
  `frontend-digest-strip-and-detail-banner` renders them.
- **The Pulse Card's state fields are read from the catalog, not from a notice.** A notice
  is about a *change*, a card field is about the event's *current* state — two different
  facts, and `detail-overlap-notice` has to say which one the Detail Screen shows when both
  exist.
- **The mute is still not reachable from the mail.** The notice body links to the Detail
  Screen; the mute lives there, and this item gives the Detail Screen the button's write.
