---
run: run-eventpulse24-025
work_item: held-for-propagation-status
intent: event-state-sync
created: 2026-11-05
---

# Code Review: run-eventpulse24-025

## Scope

| File | Action |
|---|---|
| `backend/apps/delivery/models.py` | modified — `held_at` |
| `backend/apps/delivery/migrations/0006_scheduledsend_held_at.py` | created |
| `backend/apps/delivery/services/delivery_sweep.py` | modified — claim filter, `_event_ids_to_check`, `hold_stale_sends`, `count_stuck_holds`, wiring |
| `backend/apps/delivery/services/scheduled_sends.py` | modified — `KEEP` release |
| `backend/shared/constants.py` | modified — `HELD_SEND_ALARM_AFTER` |
| `backend/worker/tasks.py` | modified — `report_held_sends`, tick |
| 4 test files | modified |

## Linters

`ruff check` clean · `ruff format` clean · `lint-imports` 19 kept / 0 broken · `manage.py check` no issues.

## Findings requiring a change — fixed

### 1. The guard silently shrank the sweep's counts (correctness)

`hold_stale_sends` built its result by iterating the rows it loaded. A row deleted between the
claim and the guard simply vanished from the batch.

Before this guard existed, **every** claimed id reached `send_one`, which reads the row, finds
it gone and counts it `cancelled`. Dropping it instead meant a send that disappeared stopped
being reported at all — smaller counts, nothing to say why.

Fixed by iterating `send_ids` and passing an unknown id straight through to `send_one`, which
already handles it. This also made the trailing re-sort unnecessary: iterating `send_ids`
preserves the claim's `due_at` ordering by construction.

Pinned by `test_a_row_deleted_between_the_claim_and_the_guard_stays_in_the_batch`, verified to
fail when the row is dropped instead.

### 2. The hold and its audit rows could diverge (robustness)

The bulk `update(held_at=...)` ran outside a transaction, with the audit rows written after. A
crash between them would leave rows held with no audit entry — a send that stopped with no
record of why, which is the hardest version of this failure to diagnose.

`claim_due_sends` already pairs its claim with its audit inside `transaction.atomic(using=PERSONAL)`.
The hold now does the same, matching the established pattern rather than inventing a weaker one.

Pinned by `test_a_hold_and_its_audit_row_commit_together`.

## Considered and deliberately not changed

| Observation | Why it stands |
|---|---|
| `write_audit` called in a loop (N inserts for N held rows) | `claim_due_sends` does exactly this for N claimed rows. Matching the existing pattern beats optimising one of a pair |
| Function-local import of `catalog_read` | Matches `delivery_messages._public_event_facts`, which imports it the same way to avoid an import cycle |
| No bound on the `IN` clause | The batch is already capped at `SEND_SWEEP_BATCH` (100) |
| Broad `except Exception` around the guard | Deliberate: the sweep must never send unverified, so any guard failure stops the tick. `exc_info=True` was added so a programming error is distinguishable from a catalog outage rather than silently looking like one |

## Security (AD-13)

- The hold path logs nothing. `report_held_sends` logs a **count** only — no user id, no address.
- `test_the_report_logs_a_count_and_never_a_user_or_address` asserts the user id does not appear
  in any record's fields and that no `@` reaches the message.
- No new external input, no new endpoint, no new credential.

## Architecture

- **AD-2 violation found and fixed during execution.** `worker.tasks` imported
  `apps.delivery.models` directly. Moved behind a published `count_stuck_holds` service — what
  that contract exists to force.
- **AD-3 holds.** The catalog read runs after the claim transaction commits; no transaction and
  no row lock spans the two schemas.
- **AD-16 holds.** `delivery` owns every write made here.
- **AD-7 untouched.** No send key is minted, derived or consumed by a hold.

## Outcome

2 findings, both fixed, both pinned by tests verified to fail without the fix. No findings
left pending.

---

---
run: run-eventpulse24-025
work_item: propagation-consumer
intent: event-state-sync
reviewed: 2026-11-10
---

# Code Review: propagation-consumer

## Scope

| File | Action |
|---|---|
| `backend/worker/propagation.py` | created — the per-user loop, the per-kind dispatch, the alarm's count |
| `backend/worker/tasks.py` | modified — the stub replaced; `report_stuck_propagation` on the tick |
| `backend/apps/ingestion/services/outbox.py` | modified — `StateChangeFacts`, `get_state_change`, `count_unpropagated_since` |
| `backend/shared/constants.py` | modified — `PROPAGATION_ALARM_AFTER`, `LIFECYCLE_PERSONAL_BEHAVIOUR` |
| `backend/apps/delivery/services/state_notices.py` | modified — docstring |
| `backend/apps/delivery/services/scheduled_sends.py` | modified — docstring |
| `backend/apps/delivery/services/email_templates.py` | modified — docstring |
| `backend/tests/worker/test_propagation.py` | created (29 tests) |
| `backend/tests/worker/test_propagation_tasks.py` | created (11 tests) |
| `backend/tests/ingestion/test_outbox.py` | modified — the consumer's cases |
| `backend/tests/worker/test_scheduling_tasks.py` | modified — the tick |

## Linters

`ruff check` clean · `ruff format` clean · `lint-imports` 19 kept / 0 broken ·
`manage.py check` no issues · `makemigrations --check` no changes detected ·
`tests/architecture/` 840 passed.

## Findings requiring a change — fixed

### 1. An N+1 against a batch API, on the path that scales (performance, correctness of scale)

`_apply_to_user` called `_current_start(change.event_id)` to get the event's current start
for the notice's Quiet-Hours lead margin — and `_current_start` calls
`get_public_events(event_ids={event_id})`.

`get_public_events` is a **batch** read. Its own docstring says why: *"A user's saved events
are resolved one by one, and a user with five saves would cost five round-trips to the
catalog… The batch is the same query with an `IN` clause instead of five queries with an `=`."*

Every saver of one event is notified about **the same event**, so the answer is the same fact
for all of them. Calling it once per saver turned one read into one-per-saver — on the one
path in this job that scales with the saver count. A popular event with 1000 savers cost 1000
identical catalog round-trips.

Fixed by hoisting the read to `propagate`, once per change, and threading the value through
`_apply_to_savers` → `_apply_to_user` → `raise_state_notice`. This also keeps the catalog read
out of the per-user path entirely, which is where AD-3 wants it.

Pinned by `test_the_catalog_is_read_once_for_the_whole_change`, verified to fail with the
mutation (4 reads where 1 is expected).

### 2. Two acceptance criteria were not pinned (testing)

The work item asks for two things the suite did not actually assert:

- **"Held rows are released… by this job — the hold's only exit."** The suite had the `KEEP`
  case only. `REMINT` and `CANCEL` had no coverage of the hold.
- **"Two changes racing on one event leave the newer one's effect."** The suite had the
  *sequential* out-of-order case, which is a different property.

Three tests added: `test_a_time_move_releases_the_held_rows_it_replaces` (REMINT),
`test_a_cancellation_releases_the_held_rows_it_cancels` (CANCEL), and
`test_two_changes_racing_on_one_event_leave_the_newer_effect`.

The `CANCEL` mutation — release the held rows instead of cancelling them — caught **four**
tests, two of them pre-existing. That is the finding that matters: a held row left `pending`
is picked up by the next sweep and sent. The user would get a reminder for an event that is
not happening.

### 3. Three stale docstrings, all asserting the consumer did not exist (correctness of prose)

| File | Claim |
|---|---|
| `state_notices.raise_state_notice` | "**Not wired to `propagate_state_change` yet** — that consumer is the next work item" |
| `scheduled_sends` (module) | "**`propagate_state_change` is deliberately not wired to this module yet.**" |
| `email_templates` (module) | "**The state-change notice is rendered but never minted, and that is deliberate.**" |

All three were true when written and are false now. The first two mattered most: they told
the next reader that a published service was deliberately uncalled, which is exactly the
sentence that stops someone wiring it up.

The `email_templates` one also carried a stale instruction — "the next implementer should not
'clean it up'" — which would have preserved dead code as if it were live.

All three now say what is true. The `email_templates` replacement also carries the note
forward that `render_state_notice` still produces `Update: {title}` and that FR-54's four
verbatim subjects belong to item 7.

## Considered and deliberately not changed

| Observation | Why it stands |
|---|---|
| `except Exception` around one user's apply | Deliberate: one user's failure is not the job's. The loop must continue, and the failure is surfaced by `propagated_at` staying NULL plus the alarm. `logger.exception` keeps the traceback |
| `resolve_target` and `get_plan` called per user | These read *that user's* snapshot and plan, which differ per user. Only the *event's* facts are shared, and only those were hoisted |
| No per-user marker table (D1) | The design's central claim, and the suite is the proof: a mutation adding a gate of its own breaks **18** tests |
| Two workers may walk one saver list | D4: append-only forbids a claim column, both workers call the same idempotent services, and the loser's writes no-op. Recorded as a known cost, not hidden |
| The catalog read is outside the per-user transaction | Required by AD-3 — a `personal` transaction must not span the catalog read |
| `PropagationCursorStalled` escapes the per-user handler | It is a programming error, not one user's failure. A worker looping on page one forever makes no progress and raises nothing — that looks exactly like a slow job |

## Security (AD-13)

- The per-user failure log carries **ids only** — `state_change_id`, `event_id`, `user_id`,
  `kind`. No title, no address, no name.
- `report_stuck_propagation` logs a **count** only.
- `report_held_sends` (item 1) unchanged.
- No new external input, no new endpoint, no new credential, no new query parameter.

## Architecture

- **AD-2 holds.** `worker.propagation` imports no app's models — it calls published services
  only. `outbox.get_state_change` returns a frozen dataclass, not the model, for exactly this
  reason: a caller holding the model could write it.
- **AD-3 holds.** No transaction spans `catalog` and `personal`. The catalog read is once per
  change, outside every transaction.
- **AD-16 holds.** Every mutation goes through the owning module's published command.
- **AD-7 holds.** No send key is minted, derived or consumed here.
- **AD-13 holds.** Ids and counts only.
- **AD-1 holds.** `worker` imports no API surface — `lint-imports` confirms.

## Outcome

3 findings, all fixed, each pinned by a test verified to fail without the fix. No findings
left pending.
