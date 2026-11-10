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

---

# Code Review: digest-card-state-fields

**Scope:** 4 source files, 2 test files, 2 generated contract files. Reviewed against
AD-2/AD-3/AD-6/AD-10/AD-13/AD-16/AD-19, FR-53, FR-55.

### Files reviewed

| File | Change |
|---|---|
| `backend/apps/ingestion/services/catalog_read.py` | `PublicEvent` gains `is_sold_out`; `_to_public_event` fills it |
| `backend/apps/personalization/services/digest_read.py` | `DigestCard` gains `status` and `is_sold_out`; four construction sites fill them |
| `backend/apps/personalization/schemas.py` | `DigestCardOut` gains the same two |
| `backend/apps/personalization/api.py` | The endpoint passes them through; the OpenAPI description was updated |
| `backend/tests/personalization/test_digest_api.py` | 9 tests |
| `backend/tests/api/test_catalog_read_service.py` | 3 tests |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | Regenerated |

### Findings — fixed

**1. The endpoint's OpenAPI description had become incomplete.**
The description enumerated what a card carries ("the event's name, time and place, up to three
Why-this Tag keys, the Confidence Pulse bucket (1-5) and the Source Badge variant") and was
silent about the two new fields. A client author reading the contract — not the source — would
not learn that a card can say an event is cancelled or sold out, nor that both fields are
`null` for a personal event. That is the one document the frontend is actually generated
from, so an omission there is an omission in the contract. The description now states both
fields, that they are read at request time rather than stored on the composition, and the two
reasons they are `null`.

**2. `is_sold_out` on `PublicEvent` was made a required field rather than defaulted.**
`PublicEvent` has no defaults on any field, and adding `= False` would let a future
construction site forget the flag and get a silently wrong `False` — a live event that
happens to look not-sold-out. There is exactly one construction site, so the cost is zero
today and the trap is removed tomorrow.

### Considered, and deliberately not changed

| Consideration | Decision |
|---|---|
| **Should the status be stored on `DigestComposition`?** | No. The composition is append-only with `append_only_mutable = frozenset()` and AD-10 says it explains *why* the event was chosen, not *what* the event currently is. Storing it would freeze the status at composition time — the exact failure the item exists to prevent. `makemigrations --check` reports no changes, which is the design's claim, held |
| **Should a cancelled card be removed from the digest?** | No, and this was the item's one real decision. FR-55's removal already happens at the **candidate** stage (`digest_candidates.py:336`), so a newly cancelled event is never composed. A card composed *before* the cancellation is a different case, and removing it here would be a second removal with a different trigger — and would break AD-10's rule that digest rows are served as stored, and make the digest flicker. The card says `cancelled`; tomorrow's composition will not contain the event at all |
| **Should a personal card carry `status="scheduled"`?** | No. `None` says "there is no lifecycle here"; `"scheduled"` would claim the catalog had an opinion about a row it has never seen, and the client could not tell the two apart. Pinned by mutation 3 |
| **Should a superseded event show `status="superseded"`?** | No, and this is unchanged behaviour rather than a choice. `get_public_events` excludes superseded events, so a superseded event is simply absent — the card already carries `catalog_event_missing=True` and `status=None`. A superseded event is not "cancelled"; it is gone, and the card says so the way it already does |
| **Should `status` be a `Literal` rather than `str`?** | No. `Event.Status` includes `superseded`, which the read cannot produce, so a `Literal` over the three producible values would be a narrower claim than the data model supports, and widening it later is a breaking change to the contract. The existing `DigestCardOut` fields (`slot`, `event_kind`, `source_badge`) are all `str` for the same reason — the client owns the vocabulary. `EventDetailFactsOut.status` is also `str` |
| **Should the two fields be collapsed into one "state" enum?** | No — the acceptance criterion forbids it, and it would be wrong anyway: an event can be `scheduled` *and* sold out, and a collapsed enum could not say both. The backend's existing vocabulary is unchanged |

### Architecture

| Decision | How it holds |
|---|---|
| **AD-3 (no transaction spans `catalog` and `personal`)** | The read crosses the wall through `get_public_events`, the published interface that returns plain data. No model crosses it. `lint-imports`: 19 kept, 0 broken |
| **AD-2 (only `apps.<X>` imports `apps.<X>.models`)** | `personalization` imports no catalog model. The two facts arrive as plain data on `PublicEvent` |
| **AD-10 (no recomputation at render)** | Nothing is recomputed. The read joins the catalog's *current* facts through the batch it already made — **no new query**. The existing query-count tests pass unchanged, including `test_the_query_count_does_not_grow_with_the_number_of_cards`. AD-10's own architecture test still passes |
| **AD-16 (write ownership)** | Nothing is written. `makemigrations --check`: no changes detected |
| **AD-19 (OpenAPI is the contract)** | `make client` run; the schema and the TS client regenerated; `test_contract.py` passes |

### Security

| Concern | Assessment |
|---|---|
| **PII in logs or payloads** | None. Two booleans and a status word. No title, no address, no name |
| **New attack surface** | None. No new endpoint, no new parameter, no new query, no new credential |
| **New input** | None. Both fields are read from the catalog and copied. No user input reaches them |
| **The `status` value on the wire** | It is the catalog's own `Event.Status` — one of four fixed strings chosen by the server. A client that receives an unknown value is no worse off than one that receives `null` |

### One thing worth saying plainly

**The status is not persisted, and that is the whole design.** The obvious implementation —
store `status` on `DigestComposition` — would have passed every acceptance criterion's letter
and failed its third one. A card composed at 09:00 and read at 12:00, for an event cancelled
at 10:00, would have said `scheduled` for the rest of the day. `test_a_state_change_after_the_composition_is_reflected`
writes the composition *before* the cancellation and reads it *after*, and mutation 1 — which
hardcodes `status="scheduled"` — fails it, along with three others. The test that would have
caught the wrong design exists and is proven able to fail.

### Verdict

Approved. No critical issues. No architecture contract broken. No migration. The one
documentation gap found was the OpenAPI description, and it is fixed.

---

# Code Review: polling-cadence-floors

### Files reviewed

| File | What was checked |
|---|---|
| `backend/shared/constants.py` | The two ceilings and the high-priority method set |
| `backend/domain/sources.py` | The derivation, and that it is stdlib-only |
| `backend/apps/ingestion/models.py` | The check constraint, and that its "else" branch matches the derivation |
| `backend/apps/ingestion/migrations/0007_source_cadence_ceiling.py` | The clamp, the operation order, and the reverse |
| `backend/apps/ingestion/services/source_registry.py` | The cleaner, the effective-method resolution, the method-change re-check |
| `backend/apps/ingestion/services/scheduling.py` | The floor check, and that it is not a duplicate of the stale flag |
| `backend/worker/tasks.py` | The tick's use of the count, and the log line |
| `backend/apps/ingestion/admin.py` | The form's help text and the inheritance of the check |
| `backend/tests/e2e/test_state_detection_window.py` | The consequence test, and whether it proves what it claims |
| `backend/tests/ingestion/test_migrations.py` | The backfill, and whether it can be tested at all |

### Findings, and what was done about them

**1. The method's default cadence was never checked against the ceiling — FIXED.**

`register_source` applied `DEFAULT_INGESTION_CADENCE[method]` *after* `check_source_change`
had run, so the default was the one cadence value that skipped the cleaner entirely. Every
default is currently inside its tier's ceiling, so nothing was broken — but nothing
*enforced* it either. A future default above its ceiling would have produced an
`IntegrityError` from the database constraint, at registration, in production, rather than a
refusal with a message.

The default now goes through the same cleaner as a given cadence, and the refusal is raised
in the shape the caller already handles (`_checked_cadence` turns `_FieldError` into a
`ValidationError` naming `ingestion_cadence`, because the default path has no collection loop
around it).

Three tests were added: one asserting every shipped default is inside its own ceiling (the
invariant, so a future default cannot drift silently), one proving a default above the
ceiling is *refused* rather than written, and one proving the default is measured against
**its own** tier — a 12-hour default is illegal for `api` and legal for `rss`, so a check
against the wrong tier is caught in one direction or the other.

**2. The floor check's boundary was inclusive, and the first test asserted the opposite —
CORRECTED.**

`report_cadence_floor_breaches` uses `__lte`, so a source last ingested exactly its ceiling
ago is a breach. The implementation was **kept**: it matches `flag_stale_sources`'s own
convention ("exactly 2x is stale") and it is the right reading of "detected *within* 4
hours" — at the instant the window closes, the promise has expired. The test was corrected,
and the boundary is now stated in the docstring so the next reader does not re-derive it.

**3. The consequence test could not drive both halves at once — SPLIT, AND SAID SO.**

No high-priority method has a parser: `api` and `partnership` have no adapter in this
codebase, and `PARSERS` holds `jsonld`, `rss`, `ics` and `email_ics`. A high-priority source
therefore cannot be ingested today, so a single test driving the scheduler *and* the
detection would have had to fake the parser — and **faking the parser would make the test
prove a fiction**.

The file is split instead: the scheduler half is proved on a high-priority source, the
detection half on a source whose method has a parser, and the file's docstring says exactly
why. This is a limitation of the codebase, not a gap in the work, and it is stated rather
than papered over.

### Considered, and deliberately not changed

| Consideration | Decision |
|---|---|
| **Should the tier be a stored field?** | No. FR-17's own order is the codebase's statement of which sources matter more, and `AcquisitionMethod`'s docstring says "FR-17 priority order, highest first". A second priority column would be a second opinion about a question the codebase has already answered, and the two could disagree — and a priority that disagrees with the method is a guarantee nobody can check. `HIGH_PRIORITY_METHODS` derives it in one place (`domain/sources.py`), and mutation 13 inverts the derivation and fails 14 tests |
| **Should `jsonld`, `rss` and `ics` be in the high tier?** | No. FR-53's parenthetical is "official sites", and the official sources are the API and partnership ones. Their 4-hour *defaults* are unchanged — a default is a starting point, and a source may poll more often than its tier requires. What the item adds is the 24-hour *ceiling* underneath, which forbids only what the guarantee cannot support |
| **Should the constraint be `DEFERRABLE`?** | No. The check is on one row's own columns, so it is evaluated immediately and correctly, and the constraint it sits beside (`source_cadence_positive_ck`) is not deferrable. Following the local convention |
| **Should the constraint's "else" branch be a whitelist of lower methods?** | No — it is `~Q(acquisition_method__in=HIGH_PRIORITY_METHODS)`, exactly the Python derivation. A whitelist would make every row with a method added later illegal until the constraint was updated, and would disagree with `source_priority`, which puts anything outside the high set in the lower tier. The two layers must be the same rule |
| **Should the constraint be added *before* the clamp?** | No — `AddConstraint` validates existing rows, so the constraint would fail on exactly the rows the migration exists to fix. The order is stated in the migration's docstring, and mutation 9 catches a clamp that does nothing |
| **Should the migration restore the clamped values on reverse?** | It cannot: it does not know them, and guessing would be worse than leaving them. The reverse drops the constraint and says what it does, in the function's docstring |
| **Should the floor check be about `last_attempted_at`?** | No. The guarantee is about *detection*, and a failed poll detects nothing. `flag_stale_sources` is about the data's freshness at 2× the row's own cadence; the floor check is about the promise at 1× the tier's ceiling. Mutation 5 swaps the two columns and 5 tests fail, including the one that pins the case where they differ |
| **Should the floor check return a list rather than a count?** | No. A count is enough to say the guarantee is at risk, and the codebase's convention is ids and counts in logs (AD-13). Who it is belongs in the registry, not in a log line |
| **Should a breach of zero be logged as a warning?** | No. A warning that fires on every tick for a healthy registry is noise, and a signal that always fires is a signal nobody reads. Mutation 12 makes it fire on a zero count and one test fails |
| **Should the floor check live in `scheduling.py`?** | Yes — it is the scheduler's question, it uses the same `_schedulable()` filter as the other two commands, and it is called by the same tick |
| **Should the rule live in `apps/ingestion/services/source_registry.py`?** | No — `domain/sources.py`. Three modules need it (the registry's cleaner, the scheduler's floor check, and the migration), and a pure function that three modules need does not belong to any one of them. `domain` is stdlib-only, so putting it there costs the layering nothing, and `lint-imports` confirms the contract still holds |
| **Should the migration import `domain.sources.cadence_ceiling`?** | No. A migration that imports live application code is a migration whose behaviour depends on the day it is run. The migration restates the rule against `shared.constants`, and a test asserts the two agree |

### Architecture

| Decision | How it holds |
|---|---|
| **AD-2 (only `apps.<X>` imports `apps.<X>.models`)** | Unchanged. `domain/sources.py` imports no model at all — it is a pure function of a method string |
| **AD-2 (`domain` is pure)** | `domain/sources.py` imports only `datetime.timedelta` and `shared.constants`, which the import-linter's contract explicitly permits ("stdlib, plus shared.constants and shared.ids"). `lint-imports`: 19 kept, 0 broken |
| **AD-3 (no transaction spans `catalog` and `personal`)** | Nothing crosses the wall. Every write is `atomic(using=CATALOG)` |
| **AD-5 (every write goes through a command)** | The registry's two write paths (`register_source`, `update_source`) are the only ones, and both reach the cleaner. The admin's `save_model` calls one of them and never `obj.save()` |
| **AD-7 / AD-13 (logs carry ids and counts)** | The new log line carries a count and a job name. No source id, no source name |
| **AD-16 (write ownership)** | `models.py` declares the constraint; no module writes the table outside the registry. `makemigrations --check`: no changes detected |
| **The constraint has two guards, each with its own catcher** | The **migration** builds the schema the tests run against (mutation 4 attacks it, 29 tests fail). The **model** is held to the migration by `makemigrations --check` (mutation 15 attacks it, exit 1) |

### Security

| Concern | Assessment |
|---|---|
| **PII in logs or payloads** | None. A count. No source id, no source name, no URL |
| **New attack surface** | None. No new endpoint, no new parameter, no new credential, no new external call |
| **New input** | The cadence, which was already an input. The ceiling only *narrows* what is accepted — it cannot widen any attack surface |
| **The migration rewrites data** | Yes — it clamps cadences down to the ceiling. It cannot raise one, and it prints the count of what it changed. The clamped value is a legal cadence under the tier it is in, so no row becomes invalid |
| **Denial of service via the constraint** | The check is on one row's own columns and costs one comparison. No lock, no table scan, no contention |

### One thing worth saying plainly

**The guarantee is now enforceable, but it is not yet keepable, and that is a statement about
the codebase rather than about this work.** FR-53 promises that a cancellation on an official
source is detected within four hours. This item makes that promise *checkable* — the cadence
cannot exceed the window, the scheduler honours it, and a source that has not successfully
ingested inside the window is counted and warned about. But no high-priority method has a
parser: `api` and `partnership` have no adapter, so a high-priority source cannot be
ingested at all today, and there is nothing for the window to protect.

That is not a reason to soften the ceiling — the ceiling is right, and it is enforced by the
database — but it is a reason not to call FR-53 satisfied. The consequence test says so at
the top of the file rather than arranging the tests to look complete: the scheduler half is
proved on an `api` source, the detection half on an `ics` source, and the gap between them
is named. When the first API adapter lands, the second half moves to the first source and
the gap closes. Until then, the promise is enforced and unexercised, which is the honest
state of it.

### Verdict

Approved. Two findings, both fixed. No critical issues. No architecture contract broken. One
migration, correctly ordered, with a reverse that says what it cannot do.

---

## Work Item: notice-composition-and-email

**Mode:** confirm · **Files changed:** 9 · **Tests added:** 38

### What was reviewed

FR-54's four verbatim subjects and the body that says what changed *and* what it means for
the user's reminders; the rule that a `detail_changed` which did not move the venue is
silenced; the escaping of an untrusted ingested title; and the dispatch that routes a
`STATE_NOTICE` row to the notice renderer rather than the reminder one.

### Findings

**Two found, both fixed.** Both were found by reading the diff against the intent's own
acceptance criteria rather than against the tests, which is the point of a review that
runs after the suite is green.

#### Finding 1 — a redundant catalog read, and a second *answer*

`_state_notice_facts` read the event for its name and its venue. `_change_zone` then read
**the same event again** to find the zone, because it was written to take the change alone.

Two problems, and the second is the one that matters:

1. **A second round trip** on the path that renders a notice for every saver of an event.
   `propagation-consumer` had just learned this lesson — `_current_start` was hoisted out of
   the per-user loop for exactly this reason — and the same mistake was reintroduced one
   layer down.
2. **A second *answer*.** `get_public_event` reads the live row. Two reads of a live row
   are two answers, and a row that changed between them could give the notice a name from
   one moment and a zone from another. A notice whose whole purpose is to be right about
   the user's evening should not be assembled from two moments.

**Fixed** by passing the already-read event into `_change_zone`. Pinned by
`test_the_catalog_is_read_once_per_notice`.

**The test's first version did not bite, and that is worth recording.** It was written
against a `time_moved` change, whose `after` carries `start_time_tz` — so `_change_zone`
returned the change's own zone and **never reached the branch that re-reads the event**.
The mutation survived. The test was then rewritten against a **cancellation**, which
records no zone and so exercises the fallback — and the mutation was caught
(`Left contains one more item`). A test that passes against the defect it was written for
is worse than no test, because it is counted.

#### Finding 2 — a self-contradictory docstring

`domain.notices.notice_subject` said: *"The title is the caller's to fold. This module does
not sanitise."* — in a module that now **contains** the fold. The sentence was written when
the fold lived elsewhere, and it was left behind when the fold moved in. A reader would
have had to decide which half of it was true, and the wrong half is the one that invites
a second folding rule.

**Fixed** by rewriting the paragraph to say what is true: the caller folds, the fold is
`fold_title`, and `fold_title` is right here so the subject and the body cannot disagree.

### What was checked and found correct

| Concern | Assessment |
|---|---|
| **The subject is FR-54's, verbatim** | Seven literal assertions in `test_state_notice_email.py`, one per kind, asserted through the **whole rendering path** — not against the vocabulary alone. A well-meaning rewrite of the template fails the test rather than ships |
| **The four PRD subjects vs. our three** | `domain.notices.PRD_SUBJECT_KINDS` records which is which, so the file's table is a fact rather than a claim. The PRD names no subject for `postponed`, `reinstated` or `superseded`; the three we wrote are in the PRD's register and marked ours |
| **The body's reminder line cannot lie** | The consequence is **derived** from `LIFECYCLE_SEND_BEHAVIOUR` — the table the sends already follow — with `reinstated`'s override written out explicitly. A body saying "your reminders have been cancelled" while the reminders still fired is exactly the bug class this intent exists to prevent, and the derivation makes it unwriteable |
| **An untrusted title cannot inject a header** | The title is folded *before* the facts reach the renderer, so the subject and the body quote the same name. `EmailMessage.subject` is a plain `str`, so a `\n` would be SMTP header injection. The HTML body escapes by Django's default (no `|safe`) |
| **A missing name degrades legibly** | `EventPulse24: your saved event was cancelled.` — the same phrase the reminder body already uses, so two mails from one product do not say it two ways. A whitespace-only title folds to `None` and takes the same path |
| **No RFC 8058 unsubscribe URL, and no footer implying one** | `unsubscribe_url=None`; transactional stream. The body's only link is the Detail Screen |
| **The mute is the opt-out, not an unsubscribe link** | The body carries **no** "Stop reminders for this event" link. A link there would be a lie twice over: the mail is not a reminder, and the change it reports may have cancelled the reminders already |
| **One minting path (AD-7)** | `test_the_state_notice_is_minted_in_exactly_one_place`, **rewritten** from a substring scan to an AST check of assignments. The old scan fired a false positive on `delivery_messages.py`, which *reads* the kind to dispatch on it — a reader is not a second writer |
| **AD-3 (no transaction spans the two schemas)** | The change's `before`/`after` are passed **by value** into `raise_state_notice`, and the renderer's reads are separate published reads. No transaction crosses the wall |
| **AD-13 (no PII in logs)** | Nothing new is logged. The failure log in `propagation.py` still carries ids only |
| **AD-2 (layering)** | `lint-imports`: **19 kept, 0 broken**. `domain/notices.py` imports only `domain.lifecycle` and `shared.constants` |
| **No migration, no new column** | `makemigrations --check`: no changes detected. `ScheduledSend` has no `state_change_id` — AD-7 put it in the key, and `send_keys.state_change_id_from_key` reads it back out, beside the builder that writes it |

### Design decisions

| Decision | Reasoning |
|---|---|
| **Should `detail_changed` be silenced wholesale?** | No — and this is the decision the whole item turns on. The PRD's third subject is "moved to [new location]", and a venue move is filed under `detail_changed` because `venue_fingerprint` is one of its detail facts. Silencing the kind silences the PRD's own subject. The rule is about the **change**, not the kind: a `detail_changed` whose venue fingerprints differ is notified; one that fixed a title is not. FR-53 asks for this ("would be engagement-trap"), and the body's own requirement — "what changed and what it means for the user's reminders" — has no answer for a title edit, because `detail_changed` maps to `KEEP` and `NONE` |
| **Should the silence happen in the renderer instead?** | No. A notice the renderer refuses to render would still have been **raised** — consuming the day's one-notice cap slot, cancelling a less important notice on its way to being refused, and leaving an entry in the user's in-app strip saying nothing. Silencing at the source (`raise_state_notice`, guard 0) is the only place it can be decided once. `test_a_silenced_detail_change_does_not_consume_the_days_cap` pins the half that is easiest to get wrong |
| **Should the venue be named in the subject?** | Only the **new** one. A venue is identified by a fingerprint — a hash — so the old venue's name is not recoverable. The subject names the new place, read from the catalog at render time. This is a deliberate narrowing of what the PRD's subject can say, and it is recorded rather than papered over |
| **Should the change's times come from the live event?** | No. A poll appends **one change per kind**, so the live event already holds the *last* kind's facts. Pairing this change's version with those times would state a move that never happened. The change's own `after`/`before` carry the times; the catalog carries the *name*, which a hash cannot |
| **Should a superseded event link to its own Detail Screen?** | No — that page is a 404, and `catalog_read.get_public_event_by_slug` refuses it. The notice links to the **replacement's** Detail Screen, whose id is on the change row (`after["superseded_by"]`) |
| **Should the renderer read the change, or should the row carry it?** | The row does not, and adding a column would be a migration. AD-7 put the change's id in the send key, so the renderer reads it back out — and the parser lives beside the builder, following `digest_local_date_from_key`'s precedent. A key shape parsed in two places is a key shape that will be parsed wrongly in one of them |
| **Should the body carry a "stop reminders" link?** | No. FR-54 asks for none, and the transactional stream carries no stream-level opt-out. The mute is the per-event opt-out and it lives on the Detail Screen — which is where the body points |
| **Should the notice be on the bulk stream?** | No. It is a one-time correction about a record the user created themselves. The bulk stream's obligation is an RFC 8058 unsubscribe URL, and a state notice is not a list |
| **Should a kind with no subject fall back to a generic one?** | No — it raises. FR-54 fixes the copy, and a notice reading "your saved event was cancelled" about an event that was not cancelled is worse than no mail, because the user reads it |

### One thing worth saying plainly

**The old venue is never named, and that is a limitation of the data rather than of the
copy.** The PRD's subject — "moved to [new location]" — reads as though both places were
nameable. A venue is identified in this codebase by `venue_fingerprint`, a hash, so the
old place has no name to print. The subject names the new one and the body says the venue
moved. If the PRD wants "moved from The Barbican to The Barbican Annexe", the catalog would
have to keep the old name — which is a change to the catalog's facts, not to the notice,
and is recorded here as a follow-up rather than smuggled in.

### Verdict

Approved. Two findings, both fixed, both now pinned by a test that was **proven** to fail
against the defect — including the first version of the read-count test, which passed
against the very defect it was written for and had to be rewritten. No critical issues. No
architecture contract broken. No migration, and none needed.

---

## Work Item: notice-and-mute-api

**Mode:** confirm · **Reviewed by:** a code-review agent against the real import graph and
the real SQL · **Findings:** 8 (3 real defects, 5 coverage/drift) · **All 8 fixed**

### What the review actually did

It did not read the plan and agree with it. It:

- rebuilt the **whole backend import graph** from AST (264 files) and checked the claimed
  import cycle against it;
- **instrumented the real SQL** of a live request, rather than trusting the query-count
  assertions;
- **mutated the code** — adding the exact edge the plan said would break a cycle — and
  re-ran `lint-imports`;
- built a **clean worktree at `HEAD`** and ran the whole suite there, to separate this
  change's failures from the ones that were already there.

### The three real defects

#### 1. HIGH — the stated reason for the module's shape was **factually wrong**

`notice_state.py`'s docstring justified reading the two models directly by claiming a
`personalization → notice_state → state_notices → scheduled_sends → personalization` cycle.

**That chain does not close.** `scheduled_sends` imports only
`apps.personalization.services.digest_preferences`, and that module reaches none of
`detail_read`, `personalization.schemas`, `detail_conflict` or `neighbor_count`. The review
proved it two ways: adding the edge `notice_state → state_notices` leaves `lint-imports` at
**19 kept, 0 broken**, and `import apps.personalization.services.detail_read` still
succeeds with that edge present.

**Fixed.** The rationale now names the reason that actually holds — **the model must not
cross the app boundary** (AD-2/AD-16), which is real and enforced — and says plainly that
there is no cycle to avoid. A false rationale is worse than a missing one: it makes a real
constraint look inviolable when it is not, and it is the reason a future maintainer would
cite to reject a legitimate refactor.

#### 2. MEDIUM — a dead function, and the query it used, duplicated verbatim

`state_notices.latest_notice_for_event` had **zero production callers** once this read
arrived — only tests and docstrings — while `notice_state.read_event_notice_state`
re-implemented its query **byte for byte**.

Two places defining "the newest notice for an event" is exactly the drift the
`NoticeSummary` projection was introduced to prevent: the projection was applied to the
*shape* but not to the *query*.

**Fixed.** `latest_notice_for_event` is **deleted**; the rule now lives in
`services.notice_state`, which owns it, and the strip's read in
`state_notices.list_undismissed_notices` uses the **same ordering**. The three tests that
covered the dead function moved to `test_notice_state.py` with it.

**And the ordering got a tiebreaker.** `order_by("-created_at")` had no secondary key, and
`created_at` is `auto_now_add` with microsecond resolution — while
`ingestion.event_writes` appends *one `EVENT_STATE_CHANGE` per kind within a single poll*,
so several notices genuinely can share a `created_at`. Without a tiebreaker the database is
free to return either row from an unordered tie, and it is free to choose differently each
time: **the strip and the banner could disagree about which notice was newest.**

Both reads now order by `("-created_at", "-id")`. **`-id` is the natural tiebreak** because
the primary key is a UUIDv7, which is time-ordered by construction. Two new tests pin it:
one asserts a stable winner, the other asserts **the strip and the banner agree**.

#### 3. MEDIUM — the query bound was **wrong on the path nobody tested**

The Detail read's query count was widened `4 → 6` to absorb the two new reads. But the
conflict read is **gated on the caller having saved the event**, so a *saved* user costs
**8** queries, not 6 — and **none of the three `<= 6` assertions set up a save**, so all
three ran the 6-query path.

The review instrumented a signed-in user who *has* a `SavedEvent` row: **8** personal
queries, two of them `personalization_conflictpair` reads.

**Fixed.** The bounds are now **named constants** — `UNSAVED_READ_QUERIES = 6`,
`CONFLICT_READ_QUERIES = 2`, `SAVED_READ_QUERIES = 8` — and a new test asserts the
difference **relatively**:

```python
assert saved == unsaved + CONFLICT_READ_QUERIES
```

That form survives the next read anyone adds to the surface, while still catching the
regression the test is for (a per-save or per-conflict loop). **The saved path is the path
most users are on** — a user who saved the event is the one reading the Detail Screen at
all.

### The five coverage and drift findings

| # | Finding | Fix |
|---|---|---|
| 4 | **No CSRF test on any of the four endpoints.** The whole file uses `CsrfClient`, which always sends a token — so the CSRF path was never exercised, and a regression that dropped `require_csrf` would leave the suite green | Three tests added: the dismiss, the mute and the unmute, each with a plain `Client`, each asserting **403 / `csrf_failed`** *and* that the row did not change |
| 5 | **`mark_seen` has no production caller.** `dismiss_notice` is the only production writer of `seen_at`, so it is either `None` or a duplicate of `dismissed_at` — while the schema docstrings described a state the system cannot produce | **Decided, not removed.** The strip's read deliberately does *not* mark notices seen — a `GET` that writes is the shape CSRF exists to stop. The docstrings now say so plainly: "Today a dismissal sets both", with the reason |
| 6 | **The work item's acceptance criteria still said "unseen"** and "marks a notice seen", and "an undismissed notice" for the Detail — contradicting what was built | The two criteria **amended in place**, with the amendment and its reason recorded in the work item rather than left for a reader to discover |
| 7 | **The router's declared response codes diverged from every sibling.** `401` was declared (no sibling declares it) and **`403` was not** — though `csrf_failed` genuinely fires on all four endpoints. A generated client could not type a response the server actually gives | `403: ErrorOut` added to all four, and the divergence is now **documented as a decision** in the module docstring: the frontend must branch on "sign in" (401) against "fetch a fresh token" (`csrf_failed` 403) |
| 8 | **`config/health.py` was outside the discovery.** It defines its own `Router` and is mounted at `/health`, but it is not named `api.py`, so the shape rule missed it — and a request handler outside the list is one nothing checks | Added by name to both `api_modules()` and `surface_files()`. The count goes **18 → 19**, and `REQUEST_MODULES` in the AD-11 guard grows to match |

### What the review confirmed as sound

- **The dismiss write is airtight.** `dismiss_notice`'s `UPDATE` is scoped
  `filter(user_id=..., pk=..., dismissed_at__isnull=True)`, so **another user's notice can
  never be dismissed** — the write itself is user-scoped, not the check after it. The four
  cases (yours/open, yours/dismissed, not yours, no such notice) map to 200/200/404/404, and
  the two 404s are byte-identical.
- **The anonymous leak floor is intact.** `read_event_notice_state` is called at
  `detail_read.py:241`, strictly after the `user_id is None` early return. An anonymous
  `GET` issues **0** personal queries.
- **The two-query claim is exact** — instrumented SQL is one `EXISTS` on the mute and one
  `LIMIT 1` on the notice — and **constant** across 0, 1, 50 notices and 150 neighbours.
- **The `limit` bound cannot be bypassed.** `limit` is keyword-only, **required, no
  default**; the only production caller passes `NOTICE_STRIP_LIMIT`. The unbounded call is
  inexpressible.
- **AD-2 holds.** `apps.personalization` never imports `apps.delivery.models` — directly or
  transitively. The `models-delivery` contract breaks on a direct import, so it is enforced
  rather than vacuous.
- **The count of 18 (now 19) is right**, and the four previously-unchecked surface files
  genuinely write no ORM.

### Design decisions

| Decision | Reasoning |
|---|---|
| **Should `notice_state` go through `state_notices`?** | It would have been fine — the review proved the cycle was never real. But it would have handed `personalization` a `StateChangeNotice` **model instance**, which is the AD-2/AD-16 leak. Reading the models directly is **right**, for the reason the docstring now gives: the projection happens inside the owning app, and the caller receives plain data |
| **Should the "newest notice" rule stay in `state_notices`?** | No. It had no production caller once the combined read arrived, and its query was duplicated verbatim. A dead function and a live copy of its query is the shape drift takes. The rule moved to the module that actually reads it |
| **What should break a `created_at` tie?** | `-id`. The primary key is a UUIDv7, which is time-ordered by construction, so of two notices raised in the same instant the later one has the larger id. The alternative — a `NULLS LAST` on a nullable column, or a second timestamp — would need a column, and a column is a migration |
| **Should the query bound be one absolute number or two?** | Two, and **named**. The conflict read is gated on the save, so the two paths differ by exactly two. One absolute number is right for half the readers; the relative form (`saved == unsaved + 2`) is right for all of them and survives the next change |
| **Should `mark_seen` be called by the strip's read?** | No. It would make the strip's `GET` a write, and the strip's read is asserted to be **one query**. The Detail Screen already refuses a `GET` that writes. `seen_at` stays as a separate column and a separate wire field, ready for the moment something marks a notice seen on render |
| **Should the router declare `401` and `403` when no sibling does?** | Yes — deliberately, and now documented. `identity`'s own router declares `403: ErrorOut` for the same reason. The other app routers declare neither, which means their generated clients cannot type a response the server actually gives |

### One thing worth saying plainly

**The plan's own premise was the source of two of the three defects.** The plan said the
module "must" be a leaf to avoid an import cycle. That premise was false, and it was the
reason a dead function was left behind with a duplicated query — the plan made the shape
feel forced, so nobody asked whether the function was still needed. And the plan widened the
query bound from `4` to `6` by adding two to the number it had, without asking which path
that number described.

**Both were caught by a review that checked the claims rather than the code.** The cycle
claim fell to a single mutation experiment — add the edge, run the linter. The query bound
fell to instrumenting a saved user.

### Verdict

Approved after fixes. **All eight findings fixed**, each pinned by a test — the three
defects by new tests that were **proven** to fail against the defect, and the five
coverage findings by new tests that exercise paths nothing had exercised before. No
critical issues. No architecture contract broken. **19 import contracts kept, 0 broken.**
No migration, and none needed. The full suite is at **5637 passed, 16 failed** — the same
sixteen that fail on a clean worktree at `HEAD`.

## Work Item: frontend-pulse-card-state

### Scope

| File | Action |
|---|---|
| `frontend/lib/event-state.ts` | created — the shared table |
| `frontend/components/state/event-state-badge.tsx` | created — the badge |
| `frontend/components/digest/pulse-card.tsx` | modified — the badge block, the accessible name, the share comment |
| `frontend/components/public-event/public-event-page.tsx` | modified — the local table removed |
| `frontend/components/city-page/city-event-card.tsx` | modified — the shared sentence |
| `frontend/app/events/[id]/page.tsx` | modified — the shared sentence, and the lifecycle line |
| `frontend/components/digest/pulse-card-state.test.tsx` | created — 31 tests |
| `frontend/tests/event-state.test.ts` | created — 31 tests |
| `frontend/tests/event-state-badge-boundary.test.ts` | created — 18 tests |
| `frontend/tests/digest-home-a11y.test.tsx` | modified — two axe-core cases |
| `frontend/app/events/[id]/page.test.tsx` | modified — four new cases |
| `…/ux-designs/…/DESIGN.md` | modified — Amendment A-22 |
| `…/ux-designs/…/EXPERIENCE.md` | modified — the badge's four bullets |

### Linters

`npx tsc --noEmit` clean · `npx eslint .` clean · `npx vitest run` **102 files / 1663 tests,
0 failed**.

### Findings requiring a change — fixed

#### 1. The card documented a backend behaviour that is false (blocker)

`pulse-card.tsx` claimed: *"A **cancelled** event has no public page: the catalog's public
read excludes it, so `public_slug` is `null` and the share control is already gone."*

**The backend does the opposite.** `backend/apps/ingestion/services/catalog_read.py:432-437`
filters `publication_status=PUBLISHED` and excludes **only** `Event.Status.SUPERSEDED`, and
`backend/apps/personalization/services/digest_read.py:416` sends `public_slug=public.slug`.
A cancelled event therefore **keeps** its share control — and the comment described a
change that had never been made.

**Fixed** by replacing the claim with the truth: the cancelled card keeps its share,
because a reader who wants to tell a friend that an event was cancelled needs a link to
the page that says so. The control is rendered from `public_slug` and **never** from the
state, so the card never guesses the server's publishing policy (AD-10). The test that
"covered" this had been passing `public_slug: null` by hand — asserting the rendering rule
and never the server contract — so it was split into two cases that do.

#### 2. The badge's docstring described markup it did not have (blocker)

`event-state-badge.tsx` claimed *"**`label` and `aria-label` are the same word.** … the
visible label and the accessible name are the same string"*, and `EXPERIENCE.md` required
`aria-label="Sold out"`. **There was no `aria-label` in the rendered markup.**

**Fixed** by resolving this together with finding 3, below.

#### 3. The badge was announced twice in one card (should-fix)

The badge's visible text was in the accessibility tree, and the card's link `aria-label`
also carried the state — so a browse-mode reader reached the badge, heard "Cancelled",
then reached the link and heard "Cancelled" again.

**Fixed** by making the badge **`aria-hidden`** and letting the link carry the fact. The
link is the tap target and the only focusable thing in the card; the **visible** label
stays, because it is what makes the state legible at a glance and what satisfies WCAG
1.4.1. Hiding a badge from the accessibility tree hides it from nobody — it only stops
the announcement happening twice. **This is a change of the design, not of the
implementation**, and it is recorded as Amendment A-22 in `DESIGN.md` and in
`EXPERIENCE.md`.

#### 4. The typography did not match the design it cited (should-fix)

The badge's docstring quoted `DESIGN.md`'s anatomy but omitted the weight and the
tracking it did not implement: `--type-scale-meta-sm` is `500 12px/1.45`, so the label
rendered at weight 500, and the tracking was `0.08em` where the design says `0.06em`.
`DESIGN.md` and the mockup disagreed with each other on the tracking, and the build had
silently picked the mockup's.

**Fixed** by implementing the design's values — `font-semibold`, `tracking-[0.06em]` —
and by recording in A-22 that **the mockup's mono family and `0.08em` are the mockup's own
styling and are not adopted**, because `DESIGN.md` and the mockup already disagreed and
the design wins. The badge's boundary test now pins the weight and the tracking.

#### 5. `DESIGN.md`'s Do's-and-Dont's row named a status the backend cannot send (should-fix)

The row read *"Lifecycle: appears when `event.status = sold_out` per FR-53"*. **`sold_out`
is not a member of `Event.Status`** — the choices are `scheduled | postponed | cancelled |
superseded`, and sold-out is the separate boolean field `event.is_sold_out`. A reader of
the row would wire `status === "sold_out"` and get a badge that never appears.

**Fixed** by amending the row to `event.is_sold_out is true` **or**
`event.status ∈ {cancelled, postponed}`, and by recording the correction in A-22.

#### 6. The "no duplicated sentences" guard covered four files and not the badge (should-fix)

`tests/event-state.test.ts` listed four consumers. **The badge was not among them** — and
the badge is the most likely place for a copy to reappear, because it renders a state's
*label*. The Detail screen was listed but imported only `SOLD_OUT_LINE`, so it rendered
no cancelled or postponed state at all while the public page did — an undocumented
asymmetry.

**Fixed** by adding the badge to the list, by adding a check for literal *labels* as well
as literal sentences, and by making the Detail screen render the lifecycle line — so both
surfaces now ask the shared table the same question.

#### 7. The cancelled test was vacuous with respect to cancellation (should-fix)

The test asserted that a cancelled card has no share control, but it **passed
`public_slug: null` itself** — so it asserted the rendering of a null slug and nothing
about cancellation.

**Fixed** by splitting it: one case renders a cancelled card with the slug the server
actually sends and asserts the share is **there**, and one renders it with a null slug and
asserts the share is **gone**.

#### 8. The "tells the two apart by position" test asserted a class name (nit)

It asserted `conflict.closest(".relative.z-10")` — the current DOM structure, not the
behaviour.

**Fixed** by asserting what a reader perceives: the two are not the same element, they
are in the same card, and they are not in the same parent.

#### 9. The "is never red" guard was a bare substring match (nit)

`expect(badgeCode).not.toContain("red")` passes only because no word in the badge happens
to contain those three letters, and it says nothing about *which* token would be red.

**Fixed** by scoping it to the colour utilities — `not.toMatch(/\b(?:bg|text|border|…)-
(?:signal-)?(?:error|red|destructive)\b/)` — and by adding positive assertions that the
badge renders the shared label and is `aria-hidden`.

#### 10. The badge's position did not match the design's wording (nit)

`DESIGN.md` said "top-right of the title row"; the build put the badge in **its own row**
above the title row, because the trust row is at capacity.

**Fixed** by amending the design's text and A-22 to say "in its own row immediately above
the title row", so the spine matches the build.

#### 11. Two names for one type (nit)

`event-state-badge.tsx` re-exported `CardState` as `EventState` — a second vocabulary for
one concept, which is the thing the shared table exists to prevent.

**Fixed** by keeping `EventState` as a documented alias of `CardState` — the badge *is* the
card's badge — and by saying so in the type's own docstring rather than leaving it as an
unexplained re-export.

### Found by the mutation pass — fixed

#### 12. The lifecycle precedence was documentation and nothing else (blocker)

**The item's own reasoning says the lifecycle state must win over the sold-out flag** — "a
badge reading 'Sold out' on a cancelled event would invite a reader to wait for tickets
for an event that is not happening" — and **no test covered it.** The card was never
rendered with both facts at once, so the rule was a comment and nothing else.

**Fixed** by adding a `describe` block for a card that is *both* sold out and cancelled,
and four direct `cardStateFor` cases. The rule is now pinned by six tests instead of
asserted in prose, and the mutation (inverting the precedence) is caught by four of them.

### Things that are genuinely fine — no action

- **The `⊘` glyph is a justified deviation from `DESIGN.md`, and the reason is sound.**
  `styles/tokens.css` confirms `--color-warn-amber` and `--color-signal-warn` are the
  same hex in both themes, and `conflict-indicator.tsx` renders a `size-[6px]
  rounded-full bg-warn-amber` — a filled circle. A `●` in the badge would be the same
  shape, colour and scale in the same card. The `⊘`/`✕`/`↦` set resolves it, and the
  `↦`-not-clock rationale (a postponed event has no new time yet) is correct against
  `POSTPONED = "postponed"  # date to be announced`.
- **The shared table is a genuine single source.** The only occurrences of "tickets no
  longer available" and "this event is not happening" outside `lib/event-state.ts` are in
  test files. The local `STATUS_LINES` really did move out of `public-event-page.tsx`.
- **`cardStateFor`'s precedence matches the backend.** `Event.Status` never contains
  `sold_out`, so a cancelled or postponed event that is also sold out shows the lifecycle
  state, and no branch is unreachable.
- **The badge-as-a-`<span>` decision is right.** It is a fact, not a control, and
  `EXPERIENCE.md` supports it.
- **The `aria-hidden` glyph is correct** and matches the Source Badge and conflict
  indicator convention.
- **Test placement and style match the repo** — the colocated
  `pulse-card-state.test.tsx`, `tests/event-state.test.ts` mirroring
  `tests/digest-labels.test.ts`'s backend-parsing pattern, and
  `tests/event-state-badge-boundary.test.ts` mirroring `tests/pulse-card-boundary.test.ts`.
- **`withoutComments` is sound here.** The `//`-truncation does not hide a duplicate
  sentence; a copy injected as code and as a comment is caught either way.
- **The vocabulary-drift test is genuinely valuable.** `backendStatuses()` correctly scopes
  to `class Event` and not `Source.Status` — there are **two** `class Status` choices
  classes in `backend/apps/ingestion/models.py`, and a regex that took the first match
  would have compared the registry's vocabulary against the event's.
- **The a11y additions correctly audit a different document** — a cancelled card has one
  fewer control — and `audit()` filters to serious and critical, as the gate requires.
- **The `superseded` case is safe.** Superseded events are excluded from
  `get_public_events`, so the card gets `status=null, catalog_event_missing=true` and
  shows no badge.

---

# Code Review: frontend-digest-strip-and-detail-banner

### Files reviewed

| File | What was checked |
|---|---|
| `frontend/lib/notice-copy.ts` | The restated backend vocabulary, and the terminal-kind rule |
| `frontend/lib/notice-read.ts` | The read, and that it reads only what the server said |
| `frontend/components/state/notice-strip.tsx` | The strip's anatomy, its live region, its dismiss write |
| `frontend/components/state/detail-notice-banner.tsx` | The banner, the mute's reach, the dismissed-notice line |
| `frontend/components/state/detail-mute-control.tsx` | The mute's write, its failure line, its accessible name |
| `frontend/app/page.tsx` | The strip's placement, and that the two reads are concurrent |
| `frontend/app/events/[id]/page.tsx` | The banner's placement, and the one-status-region rule |
| `frontend/tests/contrast.test.ts` | The new surfaces' colour pairs |
| `frontend/components/state/notice-strip.test.tsx` | 20 tests |
| `frontend/components/state/detail-notice-banner.test.tsx` | 26 tests |
| `frontend/tests/notice-copy.test.ts` | The drift guard against the backend's tables |
| `frontend/tests/notice-surfaces-a11y.test.tsx` | 9 audits through the pages, not the islands |

**Linters**: `tsc --noEmit` clean; `eslint .` clean; `prettier --check` clean on every file
this item touched. (`frontend/lib/event-state.ts` and `frontend/tests/event-state.test.ts`
were already failing `prettier --check` at `41e2313` and were not touched.)

**No backend change.** `DetailPersonalOut.muted` and `.notice`, and `GET /api/notices`,
already exist — this item is the frontend's half of a contract that was already signed.
`tests/api/test_contract.py` and the 861 architecture tests pass unchanged.

### Findings, and what was done about them

**1. The mute hid the terminal notices the backend raises *despite* a mute — FIXED.**
This was the item's one real bug. `detail-notice-banner.tsx` gated the banner on
`isMuted` alone, so a **cancelled** or **superseded** notice was hidden on a muted event
— and the backend raises those two kinds *on purpose*.
`backend/apps/delivery/services/state_notices.py:69` defines
`TERMINAL_KINDS = frozenset({ChangeKind.CANCELLED, ChangeKind.SUPERSEDED})`, and line 245
skips the mute check for exactly those two; `services/mutes.py` says why: *"FR-55 has
already pulled a cancelled event out of the digest, so silence about it is the one
failure with no second channel to catch it."* `services/notice_state.py` says the same
from the other side: *"A caller that read one and assumed the other would get one of
those two cases wrong."*

**A frontend that hid it was undoing the server's deliberate decision (AD-10).** The fix
is `muteSilencesNotice(changeKind)` in `lib/notice-copy.ts`: the mute silences the
non-terminal corrections, and leaves the terminal ones alone. Pinned by two tests — *"still
shows a terminal change, because the backend raised it despite the mute"* and *"still shows
a supersede"*.

**2. The banner and the strip invented a sentence for a kind they could not name —
FIXED.** Both fell back to *"This event has changed."* / *"An event you saved has
changed."* **That is a claim about the world made by a client that was told *what*
changed and could not understand it.** The backend does the opposite: `domain/notices.py`'s
`subject_template` raises `KeyError` for a kind it has no subject for, and the renderer
turns that into a cancelled send — *"a kind `domain.lifecycle` gained without this module
learning it must not produce a generic subject — FR-54 fixes the copy, and a wrong subject
is worse than no email."*

**So both now render nothing at all** (ASSUMPTION-9). The strip renders the entries it
*can* put into words and leaves the rest out; one unknown kind does not take the whole
strip down.

**3. The mute control was a second `role="status"` on the Detail Screen — FIXED.** The
Detail Screen's action row already owns that page's one status region (the
conflict-resolution failure line, `components/detail/detail-actions.tsx:443`), and two
status regions on a page make *"which one is the page talking?"* a question the DOM
cannot answer. The mute control's failure line is now a bare `aria-live="polite"`, always
in the DOM. Pinned by *"does not turn the mute control's failure line into a second status
region"*.

**4. The mute control was unreachable on an event with no notice — FIXED.** The banner
component returned `null` before reaching the control, so a user could not mute an event
*before* a change arrived — which is the only time muting is useful. The banner is now
gated on the notice, and the control is not.

**5. The optimistic mute hid the banner before the server confirmed it — FIXED.** The
control called `onMuteChange` *before* the write, so the banner vanished on a click and
came back if the write failed. **The banner's disappearance is a claim about the world**
— *"you will not be told about changes to this event"* — and a claim the server has not
agreed to is the client deciding the server's fact (AD-10).

**So the button's label still flips at once** (so the control feels responsive) **but the
banner moves only after the server confirms.** Pinned by *"keeps the banner while the mute
is still in flight"*.

**6. `aria-pressed` on a button whose accessible name changed with its state — FIXED.**
The control's accessible name was *"Mute updates about this event"* when unmuted and
*"Updates about this event are muted"* when muted. **A toggle button whose accessible name
changes with its state is a contradiction** — `aria-pressed="true"` on a button called
"Mute updates about this event" says both *"this is on"* and *"press me to turn it on"*,
and *"Updates about this event are muted"* is a status with nothing to press.

**So the accessible name is stable** (it names the action the control performs) **and
`aria-pressed` carries the state** (WCAG 4.1.2). The *visible* text still changes, so a
sighted reader sees the state too, and an explicit `aria-label` keeps the two apart.
Pinned by *"keeps the accessible name stable while the state changes"*.

**7. The strip's live region left the DOM with the strip — FIXED.** A live region added to
the page together with its text is not announced reliably; a region that is *already
there* and then changes is. **The moment that matters most is the dismissal of the last
notice** — which is exactly when a strip that returned `null` took its own live region
with it. The region is now always in the DOM and always `sr-only`, so the "no layout
shift" claim still holds. Pinned by *"keeps the live region in the DOM when the strip
empties"*.

**8. Two identical changes produced two identically-named dismiss buttons — FIXED.** Two
events cancelled on the same day gave two buttons both called *"Dismiss: This event was
cancelled."*, and the strip **cannot name the event** — the payload carries no title
(AD-13). So the name carries the position as well: *"Dismiss: This event was cancelled.
(1 of 2)"*. The position is counted over the entries that *render*, so an unknown kind
does not make the numbers skip. The visible text stays "Dismiss" — the position is a
screen-reader affordance, not something to print on the page.

**9. The announcement counted notices the strip did not show — FIXED.** It said *"Two
changes"* over a screen showing one, when one of the two was a kind the table had no word
for. It now counts the entries that render.

**10. The two home-page reads were serial, and the comment claimed otherwise — FIXED.**
`app/page.tsx` said the reads were concurrent and awaited them one after the other. Now
`Promise.all`.

**11. The strip's link was below the 44px tap-target floor — FIXED.** Every other tap
target on the site has it; the strip's link — its primary tap target, and the way to the
event — did not.

**12. The new surfaces' colour pairs were not named in the contrast gate — FIXED.**
`tests/contrast.test.ts` computes WCAG ratios statically from `styles/tokens.css` (the
axe gate cannot: jsdom computes no layout, which is why `color-contrast` is disabled in
every axe gate in this repo). The strip's and the banner's own pairs are now named in
`TEXT_PAIRS` — `ink-secondary` and `ink-muted` on `surface-elevated`, which is the surface
both surfaces actually sit on.

### Considered, and deliberately not changed

| Consideration | Decision |
|---|---|
| **Should the banner's dismissal line be a `role="status"`?** | No. The Detail Screen already has one, and two make *"which one is the page talking?"* unanswerable. A bare `aria-live="polite"`, always in the DOM — the same rule `components/share/share-control.tsx` and `components/add-event-button.tsx` already follow |
| **Should the mute control's label be a stable "Mute updates" with a separate state chip?** | No. A second element would need its own contrast pair and its own accessible-name rules, for no gain the `aria-pressed` attribute does not already give. The visible text carries the state, the name carries the action, and the attribute carries it to assistive technology — three carriers for one fact, each in the medium it belongs to |
| **Should the strip count undismissed notices server-side instead of rendering "N of M" positions?** | No. The count is not a badge, and a count in the payload would be a number a client renders — the exact "client re-decides a fact the server stated" that AD-10 forbids. The position is a *disambiguation aid*, not a claim about how many notices exist |
| **Should the strip's link name the event?** | It cannot. The notice payload carries no title (AD-13), and the change's before/after values are source payload and stay off the wire. The link's text is the change, and the event's own card is in the digest right below |
| **Should the banner disappear for a muted event at all?** | Only for the kinds the backend would have suppressed anyway. The backend raises a terminal notice *despite* the mute, so hiding it would undo the server's decision — finding 1 |
| **Should the strip render a fallback line for an unknown kind?** | No. The backend raises `KeyError` rather than produce a generic subject — *"a wrong subject is worse than no email"* — and ASSUMPTION-9 says a kind this system has never heard of shows nothing |
| **Should the banner offer a dismissal?** | No. The banner is persistent; the strip is dismissible. The user came to the Detail Screen on purpose, and the page's job there is to say what happened to the event they were planning around |

### Mutations

Each of the item's claims is proved by a mutation that breaks a test. The five added for
this review pass:

| # | Mutation | Caught by | Tests failing |
|---|---|---|---|
| A | The banner moves optimistically, before the server confirms | *"keeps the banner while the mute is still in flight"*, *"keeps the banner when the mute fails"* | 2 |
| B | The accessible name changes with the mute state | *"keeps the accessible name stable while the state changes"* + 3 | 4 |
| C | The live region leaves the DOM when the strip empties | *"keeps the live region in the DOM when the strip empties"* + 1 | 2 |
| D | The dismiss position is dropped from the accessible name | *"gives two identical changes distinguishable dismiss buttons"* + 2 | 3 |
| E | The announcement counts notices the strip does not render | *"counts only the changes it can put into words"* | 1 |

The four from the test phase (the terminal-notice rule, the unknown-kind silence, the
single status region, and the concurrent reads) were proved in the test phase and are
unchanged.

### Outcome

**13 findings, all fixed.** 106 files / 1765 frontend tests pass; 861 backend contract and
architecture tests pass. `tsc`, `eslint` and `prettier` are clean on every file this item
touched. No backend change, no migration, no contract regeneration.

---

## Work Item: e2e-proof-and-contract-tests

**Mode:** confirm · **Reviewed:** the proof, the contract tests, the domain tests and the
six mutation probes.

### Scope

| File | Action |
|---|---|
| `backend/tests/e2e/test_state_change_proof.py` | created — 30 tests, seven journeys |
| `backend/tests/e2e/test_state_change_contract.py` | created — 13 tests |
| `backend/tests/domain/test_notices_and_sources.py` | created — 11 tests |
| `backend/tests/e2e/mutation_probe_state_change_e2e.py` | created — 6 probes |
| `frontend/lib/event-state.ts` | modified — whitespace only (prettier) |
| `frontend/tests/event-state.test.ts` | modified — whitespace only (prettier) |

**No production code changed.** The review's most useful finding was that the proof
*found* the implementation to be correct in three places where the first draft of the
test was wrong — recorded below rather than papered over.

### Linters

`ruff check` clean · `ruff format` clean · `lint-imports` 19 kept / 0 broken ·
`tsc --noEmit` clean · `eslint .` clean · `prettier --check` clean ·
`axe-core` zero serious violations on both touched surfaces.

### Findings requiring a change — fixed

#### 1. A contract test asserted a rule the tree does not state (correctness)

`test_ingestion_never_writes_to_the_personal_schema` scanned every module in
`apps/ingestion/` for the string `PERSONAL` — and **failed on `apps/ingestion/admin.py`**,
which *reads* the user model from `personal` to show an actor's name in the admin's list
column.

**A read across the wall is legal.** AD-3 is about a *write* and about a transaction
spanning both schemas. The scan would have flagged a legitimate pre-existing read as a
breach — and a contract test that fails on correct code is worse than no contract test,
because it teaches the reader to ignore it.

Fixed by delegating to the tree's own rules: `test_no_app_writes_a_table_it_does_not_own`
over `_source_files()`, plus the import half (`ingestion` may not reach
`personalization`'s services). **One rule, one discovery, and the two lists can never
disagree.**

#### 2. Two tests carried a `self` they did not use (correctness)

`test_the_proof_runs_fully_offline` and
`test_the_state_change_path_does_not_import_a_network_client` were written with a `self`
parameter in a module with no class. **Pytest then treated them as test *methods* and
asked for a `self` fixture**, so both errored at setup rather than running. A contract
test that never runs is a contract test that proves nothing.

Fixed by dropping the parameter.

#### 3. The `domain/` coverage gate was red, and this intent's own module was half of it

`make coverage-backend` requires **100% for `domain/`**. At `HEAD` it was at **99%** —
nine lines across two files:

| Module | Missing | Whose gap |
| --- | --- | --- |
| `domain/notices.py` | 258, 355–358 | **this intent's** — the notice copy |
| `domain/sources.py` | 107–110 | an earlier intent's — `humanise_duration` |

Every one of the nine is a branch a user can reach, and each changes what the user is
told — a missing title that folds to nothing, a kind the behaviour map does not carry, a
cadence of 30 minutes that must not read "0 hours".

**The gate is on the whole directory, so an older gap keeps this intent's build red** —
and a red gate is a gate nobody reads. Fixed by `tests/domain/test_notices_and_sources.py`
(11 tests), which asserts the *words* rather than the calls.

#### 4. Two committed files failed `prettier --check` (CI)

`frontend/lib/event-state.ts` and `frontend/tests/event-state.test.ts` were committed
unformatted at `41e2313`. **CI runs `make lint-web`**, so the gate was red on files this
run did not touch — and "CI stays green" is this item's own criterion. Fixed by
`prettier --write`: a trailing blank line and a line join. **Whitespace only.**

### Findings about the *implementation* — deliberately not changed

These are the review's most valuable output, and in all three cases **the implementation
was right and the test was wrong.** The fix was to the test, with the reasoning
recorded in the test so a later reader does not "fix" it back.

#### 1. The `CANCEL` branch leaves a held row's `held_at` marker on it — and that is inert

`apply_lifecycle_change`'s `CANCEL` branch cancels the stale row and does **not** clear
`held_at`. The first draft of the proof asserted the marker was cleared, and it failed.

**The investigation:** `claim_due_sends` filters on `status = PENDING` **and**
`held_at IS NULL`; `count_stuck_holds` filters on `status = PENDING`. **So the marker is
inert on a terminal row** — a cancelled row is not claimable either way, and the stuck-hold
alarm does not see it. Clearing the marker would change no observable behaviour and would
cost a write.

The test now asserts the marker **stays**, that `claim_due_sends` returns `[]`, and says
why in a comment. **Changing the implementation to satisfy a test here would have been a
regression dressed as a fix.**

#### 2. A reinstatement raises one notice, not two — and that is the daily cap

FR-54 caps notices at one per event per local day, resolved by
`domain.lifecycle.PRECEDENCE`, which puts `cancelled` above `reinstated`. So a
cancellation followed by a reinstatement on the same day raises **one** notice.

The first draft treated this as a defect. It is not — it is the cap working. The
reinstatement was moved to `NOW + 1 day`, **and the cap is now proved deliberately** by
`test_the_daily_cap_keeps_the_second_notice_of_one_day_out`. **A test that proves the
rule beats a test that works around it.**

#### 3. The `CANCEL` branch does not re-stamp the row's version — and that is right

A cancelled send keeps the version it was minted at. The first draft asserted it moved.
The `CANCEL` branch cancels the row and stops; a cancelled row is terminal, so its
working version is nobody's business. The test now asserts the row keeps the version it
was minted at.

### Considered and deliberately not changed

| Observation | Why it stands |
|---|---|
| The proof asserts on `idempotency_key` membership rather than on a mail count | A total would also be a claim about the *notice* — a different journey's business. The first draft asserted `counts.sent == 1` and found **two** mails: the reminder and the notice |
| The contract test shells out to `lint-imports` | It is the check CI runs, and the contract count is pinned at 19 — a contract deleted from `pyproject.toml` would otherwise pass with one fewer wall |
| The contract test regenerates `schema.ts` and compares | The question is "does regenerating change anything?", and the file is restored in a `finally` — so the test is a *measurement*, not a rewrite |
| The proof drives `apply_lifecycle_change` rather than writing rows | The `catalog.guard_event_write` trigger refuses a status change without a version bump, so this is the *only* way a cancellation happens. The proof drives the real path |
| The `domain/` test patches `LIFECYCLE_SEND_BEHAVIOUR` with a synthetic kind | Nothing is stubbed — only the table the function reads is extended, which is exactly what a new kind in `ingestion` would do. The function takes its ordinary path |
| The proof's `NOW` is a fixed instant, not "now" | Two reads are bounded by the wall clock (`get_public_event` and the Detail endpoint), so a proof whose answer depended on the hour it ran would be flaky. The event starts two days past the wall clock, so the Detail read finds it whenever the suite runs |
| The frontend suite needs Node 24 | `package.json` requires `>=24.15` and CI pins Node 24 via `.nvmrc`. Under Node 20 the forks pool crashes and 83 files report as **errors** — the suite looks broken rather than skipped |

### A note on the pre-existing failures

**16 backend tests fail, and all 16 are pre-existing.** Confirmed against a clean
worktree at `HEAD`: the *same 16 test names* fail there, with the same date-expired
fixtures. **The baseline at `HEAD` is 17** — this item **fixed** one
(`test_the_generated_client_is_in_sync_with_the_document`, because the committed client
now matches the document). **The delta is −1, not 0.**

They are not this item's to fix: they are the `timeline-and-conflicts` item's
date-expired fixtures, and fixing them would mean editing another work item's tests
without its review.
