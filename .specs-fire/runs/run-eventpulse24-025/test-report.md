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
