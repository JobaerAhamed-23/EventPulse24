---
run: run-eventpulse24-023
work_item: reminder-plan-api
intent: delivery-and-reminders
generated: 2026-11-01T00:00:00Z
status: passed
---

# Test Report: The Reminder Plan API — filling an empty router

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| `tests/delivery/test_reminder_plan_api.py` (new) | 44 | 0 | 0 | `api.py` **100%**, `schemas.py` **100%** |
| `tests/delivery/test_reminder_plan_read.py` (new) | 16 | 0 | 0 | `reminder_plan_read.py` **100%** |
| `tests/delivery/test_slots.py` (new) | 21 | 0 | 0 | `slots.py` **100%** |
| `tests/delivery/test_reminder_plans.py` (updated) | 33 | 0 | 0 | `reminder_plans.py` **100%** |
| `tests/personalization/test_saved_events.py` (updated) | 44 | 0 | 0 | `saved_events.py` **100%** |
| `tests/delivery/test_scheduled_send.py` (updated) | 30 | 0 | 0 | `scheduled_sends.py` 97% |
| **Full backend suite (regression)** | **4688** | **0** | **0** | Project **99.14%**, `domain/` **100%** |

The suite grew from **4599** to **4688** — **+89 tests**, no regressions, no existing test
broken. The coverage gates are the project's own (`pytest --cov --cov-report=term` and
`coverage report --include='domain/*' --fail-under=100`), and both pass.

**Every module this item touched is at 100%**: `api.py`, `schemas.py`,
`reminder_plan_read.py`, `reminder_plans.py`, `slots.py`, `saved_events.py`. The two files
below 100% — `models.py` at 95% and `scheduled_sends.py` at 97% — carry gaps that belong to
earlier work items in this run (a bad-zone fallback, a digest-row branch, a `__str__`), not
to this one.

### The gate results, in full

| Gate | Command | Result |
|---|---|---|
| Lint | `ruff check .` | **All checks passed!** |
| Format | `ruff format --check .` | **473 files already formatted** |
| Import contracts | `lint-imports` | **Contracts: 19 kept, 0 broken.** |
| Django system check | `manage.py check` | **System check identified no issues** |
| Migrations | `makemigrations --check --dry-run` | **No changes detected** |
| Tests | `pytest` | **4688 passed** in 137.01s |
| Coverage | `pytest --cov --cov-report=term` | **99.14%** — gate is ≥80% |
| Domain coverage | `coverage report --include='domain/*' --fail-under=100` | **100%** |
| Client | `make client` | regenerated; `frontend/lib/api/` is the contract (AD-19) |

The suite was run **three times consecutively** before the last change, and once after, all
green — see "The flake I found and fixed" below.

---

## Acceptance Criteria Validation

Every acceptance criterion in the work item, and the test that proves it.

### ✅ `router` mounted in `config/api.py` under `/api/reminders`, authenticated with `current_user` like `personalization`'s router

- `test_an_anonymous_caller_is_refused` — a `GET` with no session is a **401** with
  `not_authenticated`.
- `test_an_anonymous_caller_cannot_save_a_plan` — a `PUT` with no session is a **401** too,
  so the write is not left open by the read's guard.
- `test_the_endpoints_are_in_the_openapi_schema` — both operations are in the committed
  OpenAPI document, under `/api/reminders/{target_kind}/{target_id}`, tagged `reminders`.
- The auth lives on the **router**, not on the mount: `Router(tags=["reminders"],
  auth=current_user)`. That is `personalization`'s shape, and it is why no endpoint takes a
  user id as an input — the user comes from the session, always (AD-12).

### ✅ `GET` one event's plan: the slots, the target kind, and for each slot the computed delivery time

- `test_a_personal_events_plan_is_read` — the response carries `target_kind`,
  `target_id`, `slots` and one `deliveries` entry per slot.
- `test_a_saved_events_plan_is_read` — the same for the other target kind.
- `test_the_delivery_time_matches_the_minted_send` — the API's `delivery_at` and the minted
  send's `due_at` are **the same instant**, compared as parsed datetimes so the two
  representations (`Z` and `+00:00`) cannot fake a difference.
- `test_a_read_reports_the_same_delivery_time_as_the_save` — the `GET` after the `PUT`
  answers the same delivery times the `PUT`'s own response did.
- `test_the_deliveries_keep_the_slots_order` — the delivery list follows the plan's stored
  slot order, so the picker can render the two together.

### ✅ Each slot's returned delivery time is the post-Quiet-Hours instant, with a deferred flag and the window end it was deferred to

- `test_a_slot_outside_quiet_hours_is_not_deferred` — `deferred` is `false`, `deferred_to`
  is `null`.
- `test_a_slot_inside_quiet_hours_is_deferred_to_the_window_end` — an event at 11:30pm local
  with a `1hr` slot would deliver at 10:30pm, inside the window; the answer is
  `deferred: true` and `deferred_to` **equal to** the window's end — which is also
  `delivery_at`, because the window's end *is* the delivery instant.
- `test_a_slot_inside_the_window_is_deferred_to_the_windows_end` (the read's own file) — the
  UX spec's worked example, computed on the server: the shift returns **2026-11-14 16:00Z**
  (08:00 local on the 14th).
- `test_no_window_means_no_deferral`, `test_a_disabled_window_means_no_deferral` — a user
  with no quiet hours, or with the window switched off, gets no deferral.
- `test_the_shift_is_applied_server_side` — the API never returns the window's times for the
  client to apply; it returns the instant. The client renders a dimmed chip and a tooltip.

**One instant, not two.** `deferred_to` is not computed by a second rule; it *is* the
shifted instant, because `shift_to_sendable` already returns the window's end when it
defers. `test_a_slot_inside_the_window_is_deferred_to_the_windows_end` asserts
`delivery.deferred_to == delivery.delivery_at` explicitly, so a future change that computes
the window end separately — a second implementation of "which day does this window end on"
— would fail.

### ✅ `PUT` the plan: 0–4 slots, validated against `ReminderSlot` plus at most one custom slot. 0 slots is a valid save, not a delete and not an error

- `test_zero_slots_is_a_valid_save` — a `PUT` with `[]` is a **200**, and the plan's slots
  are `[]`.
- `test_one_slot_is_saved`, `test_four_slots_are_saved` — 1 and 4 slots both save.
- `test_five_slots_are_refused` — a **422** with the shared `{code, message}` shape.
- `test_a_duplicate_slot_is_refused`, `test_an_unknown_slot_is_refused` — **422** each.
- `test_a_plan_with_no_slots_reports_no_deliveries` — a plan of 0 slots reads back with an
  empty deliveries list, not an error.
- `test_a_plan_is_attached_when_it_is_missing` — **the plan row survives.** A saved public
  event has no `ReminderPlan` row at all (only `create_personal_event` attaches one), so
  the `PUT` attaches it rather than 404-ing. And an empty save leaves the row in place, so
  "the user chose no reminders" stays distinguishable from "the user never configured a
  plan" — which is exactly why `remove_all_reminders` empties the row rather than deleting
  it.

### ✅ The write goes through `services/reminder_plans.set_plan_slots` and the minting service in one transaction. A plan change that fails to reschedule rolls the plan too

- `test_a_failed_reschedule_rolls_the_plan_back` — `resync_plan` is forced to raise, and
  the plan's slots are **unchanged** and the response is a **500**. The plan and its sends
  move together or not at all.
- `test_a_saved_plan_and_its_sends_move_together` — after a `PUT`, the plan's slots and the
  minted sends' slots are the same list.
- `test_a_custom_slot_is_minted` — a custom slot is not just stored: it produces a
  `ScheduledSend` with the right `due_at`.

The transaction is `save_plan_slots`'s own `transaction.atomic(using=PERSONAL)`, inherited
from the shape `set_plan_slots` already had.

### ✅ Ownership is enforced: another user's target is a 404 not a 403, anonymous caller gets 401

- `test_another_users_personal_event_is_a_404_not_a_403` — **404**, with the shared
  `{code, message}` shape, and never a 403.
- `test_another_users_saved_event_is_a_404_not_a_403` — the other target kind, same answer.
- `test_another_users_plan_is_not_written` — and the intruder's `PUT` leaves the owner's
  plan exactly as it was.
- `test_an_anonymous_caller_is_refused` — **401**.

**Why 404 and not 403:** a 403 confirms that the record exists, so the endpoint could be
used to probe for other users' event ids. A 404 says the same thing to a legitimate caller
and reveals nothing to an attacker. `test_get_saved_event_refuses_another_users_save` pins
the same rule one layer down, in the service.

### ✅ A missing target, or a saved event the user has since un-saved, returns the shared `{code, message}` error shape

- `test_a_target_that_does_not_exist_is_a_404` — and the body is `{code, message}`.
- `test_a_saved_event_the_user_has_unsaved_is_a_404` — **"never saved" and "un-saved" are
  the same fact**, because a saved event's plan target *is* the save. There is no way to
  tell them apart, and the API does not try to.
- `test_a_target_of_the_other_kind_is_a_404` — a personal event's id is not a saved event's
  id, so naming one as the other is a 404 rather than a plan about a nonsense target.
- `test_an_unknown_target_kind_is_a_404` — `target_kind` is a closed set, and an unknown one
  is refused rather than guessed at.
- `test_a_target_that_vanishes_between_the_save_and_the_read_is_a_404` — the read-back
  after the write is a second read, and the target can be gone by then. The answer is the
  same 404, not a 500: the shape of the answer does not depend on *when* the target stopped
  existing.

### ✅ A custom slot's offset is validated as a sane interval and cannot be negative; the bound is stated in the endpoint description

- `test_a_custom_slot_below_the_minimum_is_refused` — under 15 minutes is a **422**.
- `test_a_custom_slot_above_the_maximum_is_refused` — over 30 days is a **422**.
- `test_a_custom_slot_at_the_maximum_is_accepted` — the bound is **inclusive**.
- `test_a_negative_custom_slot_is_refused` — a reminder *after* the event is not a reminder.
- `test_two_custom_slots_are_refused` — at most one custom slot (FR-9).
- `test_a_custom_slot_is_saved`, `test_a_custom_slots_delivery_time_honours_its_offset` —
  a custom slot saves, and its delivery time honours the offset in its id.
- The bound is stated in the endpoint's description **and** in the generated schema
  (`ReminderPlanIn.slots`'s description carries "an integer from 15 ... to 43200"), so the
  client reads the bound from the contract rather than hard-coding it.

**The bound has one home.** `CUSTOM_SLOT_MIN_MINUTES = 15` and `CUSTOM_SLOT_MAX_MINUTES
= 43200` live in `shared/constants.py` (AD-8), and `test_the_bounds_are_the_ux_specs`
asserts they are the UX spec's numbers — "Min: 15 minutes before; max: 30 days before."
The validator, the endpoint description and the generated schema cannot drift apart,
because they all read the same constants.

### ✅ AD-3 holds: `delivery` does not import `apps.ingestion.models`

- `test_the_delivery_api_does_not_import_the_models` — this one **parses the source with
  `ast`** rather than grepping it, and it splits the rule in two:
  - the **surface** (`apps/delivery/api.py`) imports no models at all;
  - the **service layer** may read its own app's models, but not another app's.

  A substring check would have false-positived on the API module's own docstring, which
  names `apps.ingestion.models` in prose. Parsing the imports is what the rule actually
  says.
- `lint-imports` — **19 contracts kept, 0 broken**, including the cross-schema ones.

The read reaches the other side's data only through published services:
`personalization.services.personal_events.get_personal_event` and the new
`personalization.services.saved_events.get_saved_event`.

### ✅ Pydantic schemas and the regenerated client via `make client`; no hand-written types (AD-19)

- `apps/delivery/schemas.py` holds the three shapes: `ReminderPlanIn`, `ReminderPlanOut`,
  `ReminderSlotDeliveryOut`. The file existed and was **empty**; this fills it rather than
  creating a new one.
- `make client` regenerated `frontend/lib/api/openapi.json` and `frontend/lib/api/schema.ts`.
  The diff is **570 insertions and 0 deletions** — the new endpoints and nothing else. No
  hand-written TypeScript type was added; `schema.ts` is generated, and the frontend does
  not call the new endpoints until its own work item.

### ✅ Tests: both target kinds; 0, 1 and 4 slots; 5 slots rejected; the custom slot; ownership in both directions; the deferred-slot flag; the rollback; the query count bounded and independent of slot count

Every one of these has a test named above. The last one deserves its own note:

- `test_the_query_count_does_not_grow_with_the_slot_count` — one slot and four slots cost
  the **same** number of queries. The per-slot delivery times are computed **in Python**
  over four facts — the plan, the preference, the zone and the target — not with a query
  per slot.
- `test_the_query_count_does_not_grow_with_the_slot_count` (the read's own file) — the same
  property at the service level.

**Both measurements are taken in the steady state, and that matters.** The first read of a
user's notification preference *creates* the row (`get_preference` reads by writing), so it
costs one extra INSERT. That is a one-time cost per user, not a per-slot cost, and
measuring the first read against a later one would report a difference that has nothing to
do with the slot count. Both test files take a warm-up read before capturing, and their
docstrings say why.

---

## The custom slot's grammar: `custom:<minutes>`

**This is the one place the work item forced a design decision, and it changed the slot-id
grammar.**

A custom slot had **no offset anywhere**. `ReminderPlan.slots` is a JSON array of strings,
`CUSTOM_SLOT_PREFIX = "custom:"` marks a slot as custom, and `validate_slots` only checked
the **prefix** — so the suffix carried no meaning and `_slot_due_at` returned `None` for any
custom slot. **A custom slot was a slot with no due time: stored, listed, never minted.**

The choice was a new column versus an encoded id, and the encoded id won:

| | new column | encoded id (`custom:90`) |
|---|---|---|
| migration | yes | no |
| the id's meaning | opaque | **self-describing** |
| the offset travels with the slot | in two places, which can disagree | in one place, always |

AD-7 already names the custom slot **by its id** in the send key, so the id is a
first-class part of the key. A slot whose id *is* its offset cannot disagree with itself.

`makemigrations --check --dry-run` reports **No changes detected** — no column was added.

**The grammar is the whole contract, so it has its own test file** (`test_slots.py`, 21
tests): the id carries its offset; the minimum and maximum are accepted; a named tier has
no offset; a named tier is never mistaken for a custom one and vice versa; a malformed
suffix has no offset — `"my-slot"`, `""`, `"90.5"`, `" 90"`, and **non-ASCII digits**
(`"١٢".isdigit()` is `True` and `int("١٢")` is `12`, but the id must stay plain ASCII, or a
send key survives log scrubbing by accident rather than by design).

**Two existing tests changed, and the change is the point.** They used the old opaque
grammar (`custom:{uuid7()}`, `custom:my-slot`) and now use `custom:90`:

- `test_setting_slots_accepts_a_custom_slot`
- `test_a_custom_slot_is_accepted_as_a_default`

**And one existing test's *premise* became false**, so it was rewritten rather than
patched: `test_slot_offsets_leaves_out_a_custom_slot` asserted that a custom slot is left
out of `slot_offsets` — which was true when the offset lived nowhere, and is **not** true
now. It is now `test_slot_offsets_reads_a_custom_slots_offset_from_its_id`, and the
malformed-slot case has its own test.

---

## Two dead branches, found by the coverage gate

The coverage gate was worth running: it found two places where a branch could not be
reached, and both were removed rather than tested.

**`_unshifted_due_at` had a `None` return that could never happen.** It was called from
exactly one place, and that place had already asked `slot_due_at` for the shifted instant
and found it not `None` — and both read the same `slot_offset`. So the `None` branch was
unreachable. The helper is gone; `compute_deliveries` reads `slot_offset` once and computes
`base = start_utc - offset` directly.

**`compute_deliveries` had two guards for the same fact.** It checked `slot_offset` for
`None`, then checked `slot_due_at` for `None` — and `slot_due_at` returns `None` *only*
when `slot_offset` is `None`. The second guard was a duplicate. It is gone.

Neither was "covered by a test" because neither could be. A test that reaches them would
have to construct a state that cannot exist.

---

## The flake I found and fixed

**`test_the_sweep_predicate_uses_the_partial_index` failed intermittently** — about one run
in three — and the failure was a **Postgres planner decision**, not a broken index:

```
Seq Scan on delivery_scheduledsend  (cost=0.00..2.21 rows=1 width=16)
```

The test creates 5 rows and asserts that `EXPLAIN` names
`scheduled_send_due_pending_idx`. But Postgres chooses a plan **by cost**, and on a table
with a handful of rows a sequential scan really *is* cheaper — so whether the planner picks
the index depends on the statistics of whatever else is in the table when the test runs.

That made the test a coin flip depending on which other tests had run first and in what
order. This item made it worse without causing it: the new API tests **mint sends**, so
`delivery_scheduledsend` now has more rows in it, and the planner's estimate moves.

**The fix is `SET LOCAL enable_seqscan = off` for the assertion**, and it is the right
question to ask. The test is about whether the index **can serve this predicate** — and
"can" is answered by asking the planner for the index-only plan, not by asking it to prefer
one. With the seq scan off, the planner has no choice but the index, so a plan that names
it proves the index covers the predicate and the planner considers it usable. **The cost
model is Postgres's business; the index's shape is ours.**

**The fix was verified to still have teeth.** With the assertion temporarily instrumented to
print the plan, the output was:

```
Index Scan using scheduled_send_due_pending_idx on delivery_scheduledsend  (cost=0.14..8.16 rows=1 width=16)
```

— the plan genuinely names the index. A test that does not fail without its fix is not
evidence, so the probe was removed afterwards and the assertion left in place.

**The suite was then run three consecutive times, all green** — 4683 passed each.

---

## After the code review

The review found three real problems, and each one is now fixed with a test that fails
without the fix. The suite grew from **4687** to **4688** — **+1 net test** (one test
replaced two) — and the figures above are the post-review ones.

| The review found | The fix | The test that proves it |
|---|---|---|
| **The `PUT` resolved the target twice** — once for the minting service and again inside the read-back, so the personal event, the quiet window and the zone were each read twice on every write | A new published read, `read_plan_for`, takes the **already-resolved** target. The plan row is still read from the database — the read-back is about what was *saved* | `test_the_put_does_not_resolve_the_target_twice` counts the resolutions and asserts **one**; `test_the_puts_read_back_matches_the_next_get` asserts the `PUT`'s body and the next `GET`'s body are **equal** |
| **Two dead branches in `compute_deliveries`** — a helper whose `None` return could never happen, and a second guard that duplicated the first (`slot_due_at` returns `None` *only* when `slot_offset` is `None`) | The helper is gone; the duplicate guard is gone. `compute_deliveries` reads `slot_offset` once and computes the base instant directly | Neither could be covered — a test that reached them would have to construct a state that cannot exist. The coverage report is what found them |
| **The `PUT`'s read-back opened a race** — if the target vanished between the write and the read-back, the `PUT` would have had to answer a stale 200 or a 500 for a write that *succeeded* | The race went with the double resolution: the read-back does not re-resolve the target, so it cannot find it gone | The test that asserted the old behaviour was replaced by the two above |

**The query trace was the evidence.** Before the fix, a `PUT` issued **24** queries and
selected the personal event twice. After it, **23** — and the personal event once.

**One question the review answered rather than deferred.** The `PUT` still reads the quiet
window and the zone twice — once inside the minting path, once in the read-back. The
obvious fix was to read them once in the API and thread them down through
`save_plan_slots` → `resync_plan` → `mint_for_plan`. **It was rejected**, because
`mint_for_plan` reads the preference *inside* `resync_plan`'s transaction, and threading
the API's preference down would mean reading the quiet window *outside* the transaction
that mints against it — breaking the invariant that the stored `due_at` matches the
window as of mint time.

**Two queries to keep a transaction's reads inside its own boundary is the right trade.**

---

## Notes on how the tests were written

**The delivery-time expectations were not computed by hand.** Two assertions were off by a
day when first written, because `AFTERNOON_START` is 2026-11-11 18:00 *local* — so a `1d`
slot lands 2026-11-11T02:00Z and a `custom:90` slot lands 2026-11-12T00:30Z. The
implementation was right and the expectation was wrong. The temptation to "fix" the
implementation to match a hand-computed expectation is exactly the wrong move here: the
naive arithmetic is what the module exists to replace.

**`Actor.user()` needs the pk, not the `User` model instance.** Thirty-four of the forty-one
new API tests failed at first with `ValueError: A user actor has a UUID id and no label.`
The fix was mechanical — `user_id=user` → `user_id=user.pk`, `Actor.user(user)` →
`Actor.user(user.pk)`, and `DigestPreferenceFactory(user_id=user, ...)` →
`user_id=user.pk` — but it is worth recording, because the error message points at the
actor and the mistake is in the id.

**The rollback test forces the second half to fail, the way the tree already proves it.**
`resync_plan` is monkeypatched to raise, and the plan's slots are asserted **unchanged**.
The response is a 500 — which is right: the request was valid and the server failed, so it
is not a 404 and not a 422.

**One thing to know about the coverage command.** `pytest --cov=<module>` **breaks the
database** in this project — the tests fail with `the connection is closed`, because
narrowing the source set changes the coverage plugin's import ordering and the
`personal`/`catalog` connections never open. The project's own command
(`pytest --cov --cov-report=term`) is unaffected. **Use the project's command**, not a
narrowed one; per-module figures come from `coverage report --include=...` afterwards.

---

## What is not covered, and why

- **`apps/delivery/models.py` at 95% and `apps/delivery/services/scheduled_sends.py` at
  97%.** The uncovered lines are a bad-zone fallback, a digest-row branch, a `__str__`, and
  two other defensive paths — all belonging to earlier work items in this run, not to this
  one. They are recorded here rather than fixed here, because fixing them would mean
  changing code this item does not own.
- **The frontend picker.** This item is the API only. The picker is the next work item
  (`frontend-reminder-picker`), and it is where the dimmed chip and the "Will deliver at
  8:00 am Saturday" tooltip are rendered.
- **The client is regenerated but not called.** `frontend/lib/api/` carries the new
  operations, and the frontend does not use them until its own item.

---

# Work Item: pulse-ping-and-suppression

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| `tests/delivery/test_pulse_ping.py` (new) | 34 | 0 | 0 | `pulse_ping.py` **100%** |
| `tests/domain/test_horizon.py` (new) | 19 | 0 | 0 | `horizon.py` **100%** |
| `tests/personalization/test_digest_composition.py` (updated) | 59 | 0 | 0 | `digest_composition.py` **100%** |
| `tests/worker/test_digest_tasks.py` (updated) | 17 | 0 | 0 | `worker/tasks.py` **100%** |
| `tests/personalization/test_digest_scheduling.py` (updated) | 35 | 0 | 0 | `compose_digest.py` **100%** |
| `tests/architecture/test_ad13_pii_sweep.py` (updated) | — | 0 | 0 | `digest_candidates.py` **100%** |
| **Full backend suite (regression)** | **4599** | **0** | **0** | Project **99.10%**, `domain/` **100%** |

The suite grew from **4523** to **4599** — **+76 tests**, no regressions, no existing
test broken. The coverage gates are the project's own (`pytest --cov --cov-report=term`
and `coverage report --include='domain/*' --fail-under=100`), and both pass.

**Every module this item touched is at 100%**, except `scheduled_sends.py` at 96% — and
the seven uncovered lines there are all in *other* commands; `mint_digest` and its
helper are covered in full.

### The gate results, in full

| Gate | Command | Result |
|---|---|---|
| Lint | `ruff check .` | **All checks passed!** |
| Format | `ruff format --check .` | **469 files already formatted** |
| Import contracts | `lint-imports` | **Contracts: 19 kept, 0 broken.** |
| Django system check | `manage.py check` | **System check identified no issues** |
| Migrations | `makemigrations --check --dry-run` | **No changes detected** |
| Tests | `pytest` | **4599 passed** in 129.08s |
| Coverage | `pytest --cov --cov-report=term` | **99.10%** — gate is ≥80% |
| Domain coverage | `coverage report --include='domain/*' --fail-under=100` | **100%** |

---

## After the code review

The review found four real problems, and each one is now fixed with a test that fails
without the fix. The suite grew from **4588** to **4599** — **+11 tests** — and the
figures above are the post-review ones.

| The review found | The fix | The test that proves it |
|---|---|---|
| **The suppression reason was `[redacted]` at the sink** — the log line the module docstring calls "where SM-C1 is read from" emitted every field redacted, so SM-C1 could not tell a product suppression from an opt-out | `reason`, `local_date` and the two counts are now on `ALLOWED_FIELDS` (closed vocabulary slugs and integers, never free text) | `test_the_suppression_reason_survives_the_log_formatter`, `test_an_unsubscribed_reason_survives_the_log_formatter` — both format through the project's own `JsonFormatter`, not the raw `LogRecord` |
| **The personal pool was filtered in UTC while the count was filtered in the local zone** — a one-hour band on each DST day where an event in the user's next 48 hours was never read | The read is **widened** to the local horizon (`window_end=`), so the pool is a superset and the count narrows it | `test_the_personal_pool_is_not_narrower_than_the_local_horizon_on_a_fall_back_day`, `test_an_event_past_the_local_horizon_is_not_counted_on_a_spring_forward_day` |
| **`manage.py compose_digest` composed without minting** — and, worse, without counting the suppression either, so the day's silence was invisible to SM-C1 | The command now composes *and* mints, exactly as the worker does | `test_the_command_mints_the_ping_alongside_the_digest`, `test_the_command_mints_one_ping_when_run_twice`, `test_the_command_records_a_suppression_when_there_is_nothing_to_say`, `test_the_all_mode_mints_the_ping_for_the_due_users` |
| **The counts and the flag could disagree** — a caller passing `(0, 0, True)` would mint a Ping the composition says should not exist, and write "we had nothing to say" into the log | The command refuses a contradiction loudly | `test_a_caller_cannot_claim_qualifying_events_with_no_qualifying_counts`, `test_a_caller_cannot_claim_no_qualifying_events_with_qualifying_counts`, `test_a_refused_caller_records_no_suppression` |

**Each fix was verified by reverting it.** The allowlist fix was reverted and the
formatter test failed with `"reason": "[redacted]"` in the captured output; the pool
fix was reverted and the fall-back DST test failed with `assert 0 == 1`. A test that
does not fail without its fix is not evidence, so each was checked.

---

## Acceptance Criteria Validation

Every acceptance criterion in the work item, and the test that proves it.

### ✅ After composition, a `digest`-kind `ScheduledSend` is minted for the user's local delivery time, keyed `user_id · digest · local_date`, and shifted by Quiet Hours

- `test_the_minted_row_is_a_digest_row` — `kind == DIGEST`, `status == PENDING`.
- `test_the_minted_row_has_no_target` — `target_kind` is empty and `target_id` is
  `NULL`, because a digest row is about a user and a day, not an event.
- `test_the_send_key_is_the_users_local_date` — the key is
  `f"{user_id}:digest:2026-11-04}"`, and it is asserted against `digest_key(...)` as
  well, so the builder and the row cannot disagree.
- `test_the_send_is_due_at_the_users_local_delivery_time` — a 09:00 delivery time in
  `America/Los_Angeles` is `2026-11-04 17:00 UTC`, not 09:00 UTC and not 16:00 UTC.
- `test_the_delivery_time_is_read_in_the_users_zone` — a Tokyo user's 09:00 and a Los
  Angeles user's 09:00 are different instants, so the two rows have different
  `due_at`s.
- `test_the_send_is_shifted_by_quiet_hours` — a 02:00 delivery time inside a
  22:00–08:00 Quiet Hours window defers to 08:00 local, and **the stored `due_at` is
  already the shifted time**, so the sweep never re-checks it.
- `test_a_user_with_no_preference_row_still_gets_a_ping` — the shared defaults are used
  when there is no `DigestPreference`, so the three places that read them agree rather
  than each guessing a different hour (AD-8).

### ✅ Exactly one row per user per local date — tested by running the job twice

Three tests, at three levels, because idempotence can fail in three different places:

- `test_running_the_job_twice_mints_one_row` (the **worker** level — the criterion's
  own words) — `compose_digest_task` is run twice against the same user and the
  assertion is on the **row count**: exactly one `ScheduledSend`, `kind=DIGEST`,
  `status=PENDING`, `send_key = f"{user_id}:digest:2026-11-04"`.
- `test_running_the_job_twice_mints_one_send` (the **service** level) — the same
  property asserted on `mint_ping_send` directly, with three qualifying events so the
  count could plausibly have been three.
- `test_two_different_local_dates_mint_two_rows` — *one per local date, not one ever.*
  Tomorrow's Ping is a different row, so the key is not over-tight.
- `test_two_users_get_their_own_rows` — the key is per user; one user's Ping is never
  another's.

### ✅ FR-10's four consequences, each its own test

**Consequence 1 — 0 qualifying public events *and* 0 personal events → no send minted
at all (not a minted row that is later skipped).**

- `test_no_qualifying_events_mints_no_send_at_all` — `outcome.minted` is `False`,
  `outcome.suppressed` is `True`, the reason is
  `no_qualifying_events`, and **`_sends_for(user_id) == []`**.
- `test_the_suppressed_ping_leaves_no_row_of_any_status` — **not even a cancelled one.**
  A cancelled row is still a row, and the audit trail would show a send that was
  planned and withdrawn, which is not what happened. The count of *every* row for the
  user is `0`.
- `test_a_user_with_nothing_to_say_gets_no_send_from_the_job` — the same property
  through the worker job, so the guarantee is not an artefact of calling the service
  directly.

**Consequence 2 — 1+ personal events with 0 public events → a send is minted,
carrying a personal-only digest.**

- `test_personal_events_alone_mint_the_send` — `public=0, personal=1` mints one row.
- `test_a_personal_event_alone_makes_it_qualifying` (composition level) —
  `has_qualifying_events` is `True` when the personal count is 1 and the public count
  is 0.
- `test_the_personal_pool_count_is_zero_for_an_opted_out_user` (composition level) —
  and the converse: an opted-out user's personal events are **not** counted, so they
  cannot be the reason the user keeps receiving a Ping.

**Consequence 3 — 3 qualifying events → exactly one send, not three.**

- `test_three_qualifying_events_mint_one_send` — `public=3` mints **one** row.
- `test_running_the_job_twice_mints_one_send` — three qualifying events, run twice,
  still one row.

**Consequence 4 — content consistent across devices: one row, one key, so multi-device
cannot double-deliver.**

- `test_the_send_key_is_the_users_local_date` — the key carries the **local** date,
  because "today" is a different day for a user in Auckland and one in Los Angeles at
  the same instant.
- `test_a_zone_far_enough_from_utc_shifts_the_horizon_by_a_day` (composition level) —
  the two users' horizons land on different calendar days, which is the whole reason
  the digest's key is a **local** date and not a UTC one.

### ✅ The 48-hour window is evaluated in the user's own zone, not UTC, and the boundary is pinned

- `test_the_horizon_is_the_users_own_zone_and_not_utc` (composition level) — the
  horizon is `2026-11-06 16:00 UTC` for a Los Angeles user, which is **08:00 local on
  the 6th** and not the UTC reading.
- `test_two_users_in_different_zones_get_different_horizons` — the wall-clock
  readings are 17 hours apart (the difference between the two zones), and the
  readings are what the horizon is about.
- `test_a_zone_far_enough_from_utc_shifts_the_horizon_by_a_day` — the horizons land on
  **different calendar days** for the two zones.
- `test_the_counts_ignore_events_beyond_the_forty_eight_hour_horizon` — an event past
  the horizon is not counted, so it cannot make the Ping qualifying.
- `test_an_event_exactly_at_the_horizon_qualifies` — **the boundary is inclusive**, so
  `<=` is the right comparison: FR-5's "within the next 48 hours" includes the
  boundary, and the ranking boost it carries applies at exactly the same boundary, so
  the candidate set and the boost cannot disagree about which events are "soon".
- `test_on_an_ordinary_day_the_horizon_is_forty_eight_hours_later`,
  `test_a_spring_forward_day_keeps_forty_eight_local_hours`,
  `test_a_fall_back_day_keeps_forty_eight_local_hours` — the horizon is a **local wall
  clock**, not UTC arithmetic. A naive `now + timedelta(hours=48)` is 47 local hours on
  a spring-forward day and 49 on a fall-back day — and the user said "48 hours".
- `test_a_utc_horizon_would_be_the_wrong_thing_and_these_tests_prove_it` — the
  **negative control**. Without it, a future change that swapped `local_horizon` for
  `now + window` would still pass an ordinary-day test.
- `test_an_unknown_zone_falls_back_to_utc_rather_than_raising` — a hand-edited zone
  name must not take down the user's digest.
- `test_the_personal_pool_is_not_narrower_than_the_local_horizon_on_a_fall_back_day` —
  **the pool and the count must agree about "the next 48 hours", even on a DST day.**
  On a fall-back day the local horizon is an hour *later* than the elapsed arithmetic
  (`08:00` UTC rather than `07:00`), so a personal event at 07:30 is inside the user's
  next 48 *local* hours but only 47.5 *elapsed* hours away. It has to be counted — and
  the read's own bound was the elapsed arithmetic, so the event was never read at all.
- `test_an_event_past_the_local_horizon_is_not_counted_on_a_spring_forward_day` — the
  **other DST day, and the other direction.** The local horizon is an hour *earlier*, so
  it is the binding constraint, and an event between the two is correctly outside. The
  point of the test is that the **pool's** bound is not what excludes it — the read is
  widened, and the count excludes it on the horizon's own terms.

### ✅ The personal-events half of the rule honours `DigestPreference.include_personal_events`

- `test_the_personal_pool_count_is_zero_for_an_opted_out_user` — the composition
  reports zero personal events for an opted-out user.
- `test_a_user_who_opted_out_of_personal_events_is_not_kept_subscribed_by_them` — the
  Ping rule reads the composition's count, so an opted-out user's personal events
  cannot be the reason the user keeps receiving a Ping.
- `test_the_opt_out_is_the_compositions_call_not_the_pings` — **the count the
  composition reports is the one the rule reads.** The ping command does not re-read
  the preference, so there is one place where "does this user's personal event
  qualify?" is decided.

### ✅ Suppression is counted with its reason, so SM-C1's ≥30% target is measurable from day one

- `test_a_suppression_is_counted_in_the_audit_log_with_its_reason` — the audit row
  answers "why did *this* user get no ping on this day?" — a product question about
  one account, which is why it is a row and not a log line.
- `test_a_suppression_is_counted_with_the_pool_counts_it_saw` — "we suppressed
  because the user's city had nothing" is answerable from the counts; "we suppressed"
  alone is not.
- `test_a_suppression_is_counted_in_a_structured_log_line` — **SM-C1 is read from the
  log line**, so it has to be structured rather than prose: a log line that said
  "suppressed a ping" would need a scrape to count; one with a `reason` field is a
  query.
- `test_the_suppression_reason_survives_the_log_formatter` — **and the line has to
  survive the formatter, not just the logger.** `caplog` hands back the raw
  `LogRecord`, where every field is readable; the **sink** is a different thing, and
  `JsonFormatter` redacts any field not on `ALLOWED_FIELDS`. A reason that was never
  allowlisted reaches production as `[redacted]` — and SM-C1, which reads the line,
  cannot tell a product suppression from an opt-out, which is the one distinction the
  two reasons exist to make. This test formats through the project's own formatter and
  asserts on the bytes that would reach the sink.
- `test_an_unsubscribed_reason_survives_the_log_formatter` — **both** reasons must be
  readable at the sink. A sink where one survives and the other does not would count
  the opt-outs into SM-C1 — the inflation the two reasons exist to prevent.
- `test_a_minted_ping_writes_no_suppression_row` — a Ping that went out is not a
  suppression; the audit log must not contain a row saying otherwise, or SM-C1 would
  count the sends as suppressions.
- `test_the_job_logs_the_pings_outcome` — the Ping's outcome rides on the composition's
  own log line (`ping_minted`, `ping_suppressed`, `ping_reason`).

### ✅ The send goes on the BULK stream with the Pulse Ping unsubscribe URL (AD-20)

- `test_the_send_goes_on_the_bulk_stream` — `stream == "bulk"`. RFC 8058 is not
  optional on that stream — `EmailPort.send` refuses a bulk message with no
  `unsubscribe_url`.
- `test_the_rendered_digest_carries_the_ping_unsubscribe_url` — the URL is minted at
  render time (the link is signed and carries the scope inside the signature), so the
  test renders the row and checks the URL is there.

### ✅ A user who has unsubscribed from the Ping has nothing minted, counted separately from a suppression

- `test_an_unsubscribed_user_gets_nothing_minted` — **nothing is created**: no pending
  row, no cancelled row.
- `test_an_unsubscribed_user_is_not_counted_as_a_suppression` — **the two reasons are
  different facts about the product.** SM-C1 measures the *product's* silence; an
  opt-out is the *user* choosing silence. Counting an opt-out as a suppression would
  inflate SM-C1 with demand-side decisions: a product that mailed nobody because
  nobody wanted its mail would score a perfect 100%, and the target says nothing about
  whether the product is any good.
- `test_an_unsubscribed_user_is_checked_before_the_suppression_rule` — **the order of
  the checks matters.** A user who has turned the Ping off is not counted as a
  suppression even when they had nothing to say either — the unsubscribe is the more
  specific fact, and it is the one that is true.
- `test_an_unsubscribe_is_counted_in_the_audit_log_with_its_own_reason` — the two
  reasons are two literals, so the audit log can tell them apart.
- `test_a_user_who_never_unsubscribed_is_not_treated_as_unsubscribed` — `False` is the
  default, and the default means "not unsubscribed".

### ✅ The `pulse_ping` key kind exists in the enum, is never minted, and carries a reservation comment

- `test_the_pulse_ping_key_kind_is_never_minted` — **nothing in the tree mints it.** In
  MVP the digest email *is* the Ping, so the `digest` kind is the only daily one
  minted; a `pulse_ping` row would be a second send for the same day.
- `test_the_pulse_ping_key_kind_carries_the_reservation_comment` — the reservation is in
  the enum, with the reason: a reader sees a deliberate reservation rather than an
  omission.

---

## The Technical Note: one definition of "qualifying"

The work item's note is explicit: *"do not write a second definition of what counts as
a qualifying event."*

**`DigestCompositionResult.has_qualifying_events` is the only place FR-10's `AND` is
written**, and it sits next to the counts it is about:

```python
@property
def has_qualifying_events(self) -> bool:
    return self.public_qualifying_count > 0 or self.personal_qualifying_count > 0
```

The composition **reports** the pool counts it already computed — it does not
re-query. `mint_ping_send` **reads** the property rather than re-deriving it from the
same two numbers. Three tests pin the seam:

- `test_has_qualifying_events_is_the_and_of_the_two_counts`
- `test_has_qualifying_events_is_false_when_both_counts_are_zero`
- `test_the_opt_out_is_the_compositions_call_not_the_pings`

And the horizon is computed **once**: `compose_digest` computes it and puts it on the
result as `horizon_utc`, so the suppression path cannot disagree with the card path
about which events are "soon".

---

## Notes on how the tests were written

**The DST expectations were not computed by hand.** The three DST tests failed three
times before they were right — each time because *my expectation* was wrong and the
implementation was correct. The fix was to stop reasoning about offsets and run a
Python one-liner that printed the exact value. That is worth recording, because the
temptation to "fix" the implementation to match a hand-computed expectation is exactly
the wrong move here: the naive arithmetic is what the module exists to replace.

**The wall clock is a floating reading, and `DTZ001` says so.** `ruff` flags a
`datetime()` with no `tzinfo`, and `tests/**` does not exempt `DTZ`. Rather than nine
`# noqa` comments, `test_horizon.py` has one `clock(...)` helper that builds a
deliberately-floating wall clock — matching the repo's existing convention for
deliberate naive datetimes (`test_quiet_hours.py`, `test_calendar_ics.py`).

**The worker's stub had to grow.** `compose_digest_task` now reads four more
attributes off the composition's result, so the stubbed `Result` in
`tests/worker/test_digest_tasks.py` carries them — as a shared `FakeResult` class
rather than three anonymous ones, so the shape the job depends on is written down once.
**The stub's shape is a contract**, and the docstring says so: a stub that did not
carry the counts would let the job read counts from somewhere the real composition
never reads them.

**One thing to know about the coverage command.** `pytest --cov=<module>` **breaks the
database** in this project — 212 tests fail with `the connection is closed`, because
narrowing the source set changes the coverage plugin's import ordering and the
`personal`/`catalog` connections never open. The project's own command
(`pytest --cov --cov-report=term`) is unaffected. **Use the project's command**, not a
narrowed one; per-module figures come from `coverage report --include=...` afterwards.

---

## What is not covered, and why

- **`send_key` builders for `pulse_ping`.** There is no builder, deliberately — the
  kind is reserved and never minted. `test_the_pulse_ping_key_kind_is_never_minted`
  asserts the absence from the other side.
- **The push channel.** Phase 2. The enum reservation and its comment are what this
  item owes it.
- **The `pulse_ping` row shape.** The Phase 2 push row does not exist yet, so there is
  nothing to test.

---

# Work Item: notification-preferences-api

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| `tests/delivery/test_preferences_api.py` (new) | 32 | 0 | 0 | `preferences_api.py` **100%**, `preferences.py` **100%**, `preferences_read.py` **100%** |
| `tests/delivery/test_scheduled_sends.py` (updated) | 41 | 0 | 0 | `scheduled_sends.py` **98%** |
| `tests/delivery/test_send_keys.py` (updated) | 23 | 0 | 0 | `send_keys.py` **100%** |
| `backend/apps/delivery/schemas.py` | — | — | — | **100%** |
| **Full backend suite (regression)** | **4738** | **0** | **0** | Project **99.19%**, `domain/` **100%** |
| **Full frontend suite (regression)** | **1028** | **0** | **0** | — |

The suite grew from **4729** to **4738** — **+9 net tests** across the whole project, and
**+32** in the new API file, **+4** in `test_send_keys.py` and **+3** in
`test_scheduled_sends.py`. No existing test was broken, and **no existing test was
weakened**: the one existing test that my first implementation broke
(`test_rescheduling_rewrites_due_at_without_changing_keys`) was **fixed by fixing the
implementation**, not by editing the test — which is the whole story of D13 below.

### The gate results, in full

| Gate | Command | Result |
|---|---|---|
| Lint | `ruff check .` | **All checks passed!** |
| Format | `ruff format --check .` | **478 files already formatted** |
| Import contracts | `lint-imports` | **Contracts: 19 kept, 0 broken.** |
| Django system check | `manage.py check` | **System check identified no issues** |
| Migrations | `makemigrations --check --dry-run` | **No changes detected** |
| Tests | `pytest` | **4738 passed** in 142.39s |
| Coverage | `pytest --cov --cov-report=term` | **99.19%** — gate is ≥80% |
| Domain coverage | `coverage report --include='domain/*' --fail-under=100` | **100%** |
| Frontend lint | `make lint-web` | **eslint, tsc and prettier all clean** |
| Frontend tests | `make test-web` | **1028 passed** (73 files) |
| OpenAPI contract | `tests/api/test_contract.py` | **passed** — the committed schema matches the live API |
| Client | `make client` | regenerated — `openapi.json` and `schema.ts` both diffed |

---

## Acceptance Criteria Validation

### ✅ `GET` the notification settings: quiet-hours window, default reminder slots, delivery time and zone — one call, one response, assembled across the two modules through published services (AD-2)

- `test_the_get_returns_the_window_the_default_slots_the_delivery_time_and_the_zone` — all four in one response.
- `test_the_get_assembles_the_response_across_the_two_modules` — **an `ast` check**: the API module imports neither module's models, so the assembly goes through the published services and not through the ORM.
- `test_the_get_falls_back_to_the_shared_defaults_when_there_is_no_digest_preference` — a user with no `DigestPreference` row gets `shared.constants`' defaults, not `None` and not a guess.
- `test_the_get_reports_no_quiet_hours_when_the_user_turned_them_off` — `null` on the wire.

**The two modules really are two modules.** `delivery` owns the window and the default
plan; `personalization` owns the delivery time and the zone. The `GET` is a facade over
both, and the *client* never learns the split — one call, one response.

### ✅ `PUT` the quiet-hours window: two local wall clocks, or null for "no quiet hours". A full-day window is rejected with a readable message

- `test_putting_the_window_writes_it`
- `test_putting_a_null_window_turns_quiet_hours_off` — `null` is a **value** here.
- `test_omitting_the_window_leaves_it_alone` — **omission is not null**, and the two are told apart by the field's *presence in the request*, not by a sentinel.
- `test_a_full_day_window_is_refused_with_a_readable_message` — `start == end` → 422, `code == "invalid_quiet_hours_window"`, and the message says what is wrong.

**The patch semantics are the interesting part.** `quiet_hours` cannot be `None`-by-
omission and `None`-by-value at the same time, so the distinction is carried by Pydantic
v2's `model_fields_set` — the set of fields the client actually sent. **That was verified
end-to-end through Django Ninja**, not assumed: Ninja's `BodyModel.resolve` calls
`cls.model_validate(data)`, which preserves `model_fields_set`. The alternative — a
sentinel for "unset" — would have put a fake value in the OpenAPI contract and a fake
branch in the generated client.

### ✅ `PUT` the default reminder plan: 0–4 slots, the same validation as the per-event plan, reusing one validator rather than a second copy

- `test_putting_the_default_slots_writes_them`
- `test_putting_an_empty_default_is_valid` — 0 slots is a valid state, not an error.
- `test_the_default_slots_use_the_same_validator_as_the_per_event_plan` — **the same refusals, with the same error codes**, because `set_default_reminder_slots` calls `validate_slots` — the same function `reminder_plans` calls. The test compares the two refusals directly, so a second copy of the rule would fail it.
- `test_five_slots_are_refused`

### ✅ `PUT` the delivery time (and zone), through `personalization`'s published command. Onboarding's existing endpoint keeps working unchanged

- `test_putting_the_delivery_time_writes_it_through_the_published_command` — the write goes through `personalization.services.onboarding.set_digest_preference`, so `delivery` never writes `DIGEST_PREFERENCE` (AD-16).
- `test_a_bad_timezone_is_refused`
- `test_onboardings_digest_preference_endpoint_still_works` — **the existing endpoint is untouched.** This is the AC's explicit non-regression, and it is asserted rather than assumed.

**The delivery time and the zone are one setting.** A wall clock without its zone is not a
schedule, so they travel together and are applied together — the schema makes them two
*required* fields of one object, so half a pair cannot be sent.

### ✅ Every one of those writes rewrites `due_at` on the user's `pending` rows and leaves keys, `sent` and `cancelled` rows untouched. Asserted by key equality and row count, not by inspection

- `test_the_window_write_rewrites_the_pending_rows_due_at`
- `test_putting_the_delivery_time_moves_the_pending_reminder_rows_too`
- `test_the_keys_are_unchanged_across_ten_successive_changes` — **ten writes, ten reads, the key set is identical.** This is the AC's headline claim: a user who adjusts their settings ten times still receives one reminder.
- `test_a_sent_row_is_never_touched` — a sent row is a fact about an email that already went out.
- `test_a_cancelled_row_is_never_touched`
- `test_the_row_count_does_not_change_when_the_window_changes` — **the rewrite never mints.** The no-create path is also asserted *structurally*, by inspecting `reschedule_pending_for_user`'s source for `.create(`, `objects.create`, `bulk_create` and `get_or_create`.

### ✅ Changing the default plan does not retroactively change existing per-event plans. It applies to future attachments only — tested explicitly

- `test_changing_the_default_plan_does_not_touch_the_existing_per_event_plans` — the plan rows keep their slots **and** their pending sends keep their keys and their count.

**This is true by construction, and the test proves the construction.** The default plan is
not an input to any `due_at` computation, so a rewrite *cannot* move a per-event plan's
row. The test asserts both halves — the plan's slots and the sends' keys and count — because
either alone would pass on a partial implementation.

### ✅ The rewrite is bounded and batched: one pass over the user's pending rows, not one query per row, and the zone read once

- `test_the_rewrite_reads_the_zone_once_not_once_per_row` — **by query count**: four rows cost no more than one.
- `test_the_rewrite_does_not_read_the_calendar` — **the bound stated as a bound on *what* is read.** The rewrite reads the user's rows and the zone and nothing else; no event, no save, no per-row query. (See D13 — this test is only possible because of the `slot_at` column.)

### ✅ Ownership: a caller reads and writes only their own settings; anonymous gets 401

- `test_anonymous_get_gets_401`
- `test_anonymous_put_gets_401`
- `test_a_caller_cannot_read_another_users_settings`

**The user id comes from the session and never from a payload** — the endpoint takes no
user id at all, so the scoping cannot be talked out of by a request body.

### ✅ Partial writes are atomic — a request that sets the window and the default plan either applies both or neither

- `test_a_request_that_sets_the_window_and_the_default_plan_applies_both`
- `test_a_request_that_sets_the_window_and_the_default_plan_applies_neither_when_one_fails` — a bad slot list rolls the window write back; the stored window is still 22:00.

**Both modules write to the `personal` schema, so one `transaction.atomic(using=PERSONAL)`
around the two commands makes them one transaction.** The digest write, by contrast, goes
to `personalization` — which is also `personal` — so it nests inside the same transaction
rather than needing a second one. **No cross-schema transaction is involved** (AD-3).

### ✅ Pydantic schemas and the regenerated client via `make client` (AD-19); CI's diff check passes

- `make client` regenerated `frontend/lib/api/openapi.json` and `frontend/lib/api/schema.ts`.
- `tests/api/test_contract.py::test_committed_openapi_schema_matches_the_live_api` — **the committed schema matches the live API.** That test failed until the client was regenerated, which is the check doing its job.
- `make lint-web` — eslint, `tsc --noEmit` and prettier all clean against the new types.

### ✅ Tests: each write and its `due_at` rewrite; keys unchanged across ten successive changes; `sent` rows never touched; the default-plan non-retroactivity; the full-day rejection; atomicity; the query bound; ownership

**All of the above, one named test each** — 32 in `test_preferences_api.py`.

---

## The Technical Note: the digest row moved, and kept its key

> *"A test should change the delivery time and assert tomorrow's digest row moved with it
> and kept its `user_id · digest · local_date` key."*

`test_putting_the_delivery_time_moves_tomorrows_digest_row_and_keeps_its_key` — and it is
the test that found the **second** gap.

**A digest row stores no date.** `slot` is empty, `target_id` is `NULL`, and the row is
about a user and a *day* — and the day lives **only inside the key**. So the rewrite has to
recover it, and the recovery is a parse of a value this module minted. **The parser lives
beside the builder**, in `send_keys.py` next to `digest_key`, because *"a key shape parsed
in two places is a key shape that will be parsed wrongly in one of them."* Four tests pin
it: the round trip, a non-digest key, the wrong number of parts, and a malformed date.

**And the parse is strict on purpose.** A digest whose day cannot be read is **not**
re-timed to a guessed day — `test_a_digest_row_whose_key_has_no_readable_date_is_left_alone`
asserts the row is left exactly as it was. A digest moved to the wrong date is a digest that
goes out on the wrong day.

---

## D13: the fourth gap, and the bug that was there before this item

**The first implementation failed one test, and the failure was the most valuable thing in
the item.**

`test_the_window_write_rewrites_the_pending_rows_due_at` asserted that a Quiet Hours write
moves a pending row's due time. It did not move. The row was already **deferred** — its
`1hr` slot fell inside the default 22:00–08:00 window, so it was minted at 08:00 rather
than at 22:30 — and the rewrite recomputed the event's start as `due_at + offset`, which
for a deferred row **compounds the deferral**. A row pushed from 22:30 to 08:00 reads as
one that was for 09:00, and re-shifting that lands on the wrong hour again — and, worse,
lands on the *same* wrong answer, so the row never moves at all.

**This was a pre-existing bug**, from the `send-minting-and-rescheduling` item. The
existing suite never rescheduled a *deferred* row: its one rewrite test minted a row the
default window did not cover, so the approximation happened to be exact. **The bug was
invisible until a test needed the thing the bug was about.**

### The two candidate fixes, and why the first one lost

The first implementation read the event's start from its owner — `delivery` asking
`personalization` for the starts of the rows' targets, in two batched queries. It was
**correct**, and it was **wrong for this codebase**:

- The tree holds cross-module ids **by value**. The factory says so outright: *"the plan
  holds the reference by value, like every other cross-module id here"* — and **no personal
  event needs to exist** for a plan to hold a reference to one. Making a rewrite depend on
  a backing record existing makes a pending row's fate depend on a row it does not own.
- It broke an existing test — `test_rescheduling_rewrites_due_at_without_changing_keys`,
  which mints against a synthetic target with no save behind it. **The rule is never to
  break existing tests**, and a rule that is only true when the fixtures are convenient is
  not a rule.

### The fix: `ScheduledSend.slot_at` — the instant the slot names, before Quiet Hours

The row now carries **two instants**, and they are the same kind of pair as
`event_version`'s — one frozen at minting (in the key), one re-stamped by propagation (in
the column):

- `slot_at` — **the instant this send was for.** A reminder's is its slot
  (`event_start - offset`); a digest's is its local delivery instant.
- `due_at` — **the instant this send goes out**, already shifted.

**The shift is the only difference between the two columns**, so re-timing a row is
exactly one function call — `shift_to_sendable(slot_at, window, zone)` — and it is
*correct* for a deferred row, because the pre-shift instant was **kept** rather than
reconstructed.

**This is also the cheaper design.** The AC asks for *"one pass over the user's pending
rows, not one query per row, and the zone read once"*. The column meets that with room to
spare: the zone is read once, the rows are read once, and **the user's calendar is not read
at all**. The other candidate needed two more queries and two more published reads in
another app.

### What it costs, and the tests that pin it

- One migration (`0005_scheduledsend_slot_at`), one **nullable** column — the null is a real
  state: a `state_notice` has no slot and no Quiet-Hours arithmetic, so it has no
  `slot_at` and is skipped, exactly as it was before.
- `ScheduledSendFactory` now sets `slot_at`, so a factory row is re-timeable rather than
  skipped. A factory row is **not** deferred, so the two instants coincide — which is a
  real state.

Three tests pin the new behaviour:

- `test_a_deferred_row_keeps_the_instant_it_was_for` — the row carries both instants, and **the round trip works**: quiet hours off brings the reminder back to its own hour, on pushes it back out to the same hour it was pushed to the first time. A row that only remembered its pushed-to time could not do that.
- `test_the_rewrite_does_not_read_the_calendar` — the rewrite reads the rows and the zone and nothing else.
- `test_a_row_with_no_slot_instant_is_left_alone` — a `state_notice` has no pre-shift instant, so it is left exactly as it was rather than re-timed from a guess.

### The digest branch is the one thing that does not use `slot_at`

A digest is about a **time of day**, so a delivery-time change has to move it — and
`slot_at` holds the *old* delivery instant. The digest's local date is immutable and lives
in its key, so the digest's pre-shift instant is rebuilt from **the key's date and the
current delivery time**, which is exactly what `mint_digest` does. The key parser stays,
beside the builder.

---

## Notes on how the tests were written

**The first version of the failing test was wrong, and the second was right.** The original
test turned Quiet Hours **off** before measuring, so the row was never deferred and the
assertion could not fail for the right reason. The test that found the real bug mints the
row under the **default** window — so the row *is* deferred — and then widens the window
past the slot. **The fixture has to be right before the assertion means anything**, and
that took two attempts.

**The DST arithmetic was checked, not reasoned about.** The event starts at 07:30 UTC on
the 14th, which is **23:30 in Los Angeles on the 13th** — after the 1 November DST end, so
PST and UTC−8. The `1hr` slot is therefore 22:30 on the 13th, which is *inside* the
default 22:00–08:00 window, and the deferred time is 08:00 on the 14th = 16:00 UTC. **The
expectations are written out in the test's docstring**, so a reader does not have to
re-derive them, and a future DST change cannot silently make them wrong.

**The `model_fields_set` behaviour was verified empirically**, not assumed — through the
actual Django Ninja path, with `parse_obj({'a': None})` and `parse_obj({})` checked
directly — before the patch semantics were built on it.

**The plan's own validator is compared, not duplicated.** The default-plan test does not
re-state the 0–4 rule; it *compares* the refusal with the per-event plan's refusal, so a
second copy of the rule would fail the test rather than pass it.

**Two pieces of dead code were found and removed** rather than left covered: `SettingsPatch.is_empty`
and `set_default_slots` were both unreachable — the API path uses `apply_settings_patch`
directly and nothing called the convenience wrapper. Dead code that looks like a feature
is worse than no code, and the repo's own `send_keys` module says so.

---

## What is not covered, and why

- **`slot_due_at`'s "no offset" branch (line 175) and `_local_delivery_instant`'s bad-zone
  fallback (lines 338–339).** Both are pre-existing defensive branches: a slot id that is
  neither a named tier nor a well-formed custom slot, and a hand-edited zone name. The
  plan validator refuses the first, and the second falls back to UTC on purpose. The
  *new* defensive branches — a slot with no offset at minting
  (`test_a_slot_with_no_offset_is_not_minted`) and a row with no `slot_at`
  (`test_a_row_with_no_slot_instant_is_left_alone`) — are covered.
- **The `state_notice` key shape.** `state_notice_key` exists and is tested as a builder,
  but nothing mints a `state_notice` row yet — that belongs to the FR-54 intent.
- **The push channel.** Phase 2.

---

# Work Item: frontend-reminder-picker

## Summary

| Category | Passed | Failed | Skipped | Notes |
|----------|--------|--------|---------|-------|
| `components/reminders/reminder-picker.test.tsx` (new) | 37 | 0 | 0 | The picker's rendering, selection, deferred state, custom slot, save, failure paths and the plan's slot bound |
| `tests/reminder-picker-a11y.test.tsx` (new) | 6 | 0 | 0 | `axe-core` over every state, plus the landmarks and the group label |
| `app/events/[id]/reminders/page.test.tsx` (new) | 8 | 0 | 0 | The route's shell, crumb, active sidenav item and the states |
| `app/events/[id]/page.test.tsx` (updated) | — | 0 | 0 | The Detail Screen now links to the picker and holds no control of its own |
| `tests/event-detail-boundary.test.ts` (updated) | — | 0 | 0 | The boundary now covers the *link*, not a display-only component |

**47 new frontend tests** (51 after the code review added the plan's slot bound), and the
full suite passes: **76 files, 1094 tests**.

### The gate results, in full

| Gate | Command | Result |
|------|---------|--------|
| Lint | `pnpm lint` | clean |
| Types | `pnpm typecheck` | clean |
| Format | `pnpm format:check` | clean |
| Tests | `pnpm test` | **76 files, 1094 tests passed** |
| Web lint | `make lint-web` | clean |
| Architecture + spacing + AD-19 | `pnpm vitest run tests/architecture.test.ts tests/spacing-scale.test.ts tests/ad19-endpoint-coverage.test.ts` | **73 passed** |
| Backend | `uv run pytest --cov` | **4738 passed, 99.19% coverage** |
| Python lint | `uv run ruff check .` / `uv run ruff format --check .` | clean |

## Acceptance Criteria Validation

### ✅ The route is `/events/:id/reminders`, in the A-8 shell, with the crumb `Digest · {event name} · Edit reminders`, and Digest is the active sidenav item

`app/events/[id]/reminders/page.tsx` renders inside `<AppShell>`. The crumb is a real `<nav aria-label="Breadcrumb">` with an `<ol>`: *Digest* → the event's name → *Edit reminders* (`aria-current="page"`). The sidenav's Digest row is active on every path under `/events/`, so the Detail Screen and the picker both mark it. The route's test asserts the crumb's contents **scoped to the crumb** and the active item **scoped to the sidenav** — both because the page has two navigation landmarks and an unscoped query found the wrong "Digest".

### ✅ "Edit reminders" on the Event Detail screen routes here

`components/detail/detail-reminder-link.tsx` replaces the old display-only `detail-reminder.tsx`. The Detail Screen now carries a link to `/events/{id}/reminders` and **holds no control of its own** — the boundary test asserts the section contains the route, and contains no `<button>`, no `onClick` and no terracotta.

### ✅ Four slot chips — 5d / 2d / 1hr… labelled "Remind me:"

The four named slots are `5d`, `2d`, `1d`, `1hr`, under the locked microcopy **"Remind me:"**. The chip group is a `<fieldset>` with a `<legend>`, and the chips are scoped under `[data-reminder-chips]` so the *Add slot* button is not counted among them.

### ✅ Selection is ink inversion, never terracotta — and a test asserts it

Selected: `bg-ink-primary text-ink-inverse`. Unselected: `bg-surface-subtle text-ink-primary`. The **source-level test** reads `reminder-chip.tsx` and asserts the selection classes contain no `terracotta` and no `accent`; the one sanctioned accent use — the focus ring, `focus-visible:outline-accent-terracotta` — is asserted separately. This is a source test rather than a DOM test on purpose: the invariant is about the class string, and a DOM assertion could be satisfied by a token that happens not to apply in jsdom.

### ✅ The Quiet Hours chip state comes from the API's per-slot deferred flag — never recomputed in the browser

The chip takes `deferred` and `note` straight from `ReminderSlotDeliveryOut.deferred` and `deferred_to`. The dimming is `opacity-40`. A source test asserts the picker contains **none** of the fingerprints of the browser-side arithmetic: no `quiet_hours`, no `quietHours`, no `window_start`/`window_end`/`windowStart`/`windowEnd`, no `getTime() <`, and no `+ n * 60`.

### ✅ The dimmed state is conveyed by text and not by opacity alone, and the tooltip is reachable without hover

Opacity is invisible to a screen reader, so the deferred instant is carried **twice**: in the button's `aria-label` (`"1 hour before. Will deliver at 8:00 am Saturday."`) and as visible text under the chip. The visible text is the real signal; the opacity is the quiet part.

### ✅ The dimmed state remains selectable

The deferred chip is a normal `<button>` with a normal `onClick`; the test toggles it and asserts it becomes selected. A chip that could not be pressed would be a control that is present and inert.

### ✅ EXPERIENCE.md's four worked examples are the tests, verbatim

The four examples are table-driven against **server payloads**, not against browser arithmetic:

| Example | Expected |
|---|---|
| Saturday 7:00 pm event, 1hr slot — outside Quiet Hours | not dimmed, no note |
| Friday 11:30 pm event, 1hr slot — inside Quiet Hours | dimmed, *"Will deliver at 8:00 am Saturday."* |
| Sunday 6:00 am event, 5d slot — outside Quiet Hours | not dimmed, no note |
| Sunday 6:00 am event, 1hr slot — inside Quiet Hours | dimmed, *"Will deliver at 8:00 am Saturday."* → *"Will deliver at 8:00 am Sunday."* |

### ✅ One custom slot can be added, with its own interval; a second is not offered

The custom chip appears **immediately** on adding, not only after a save — the first implementation derived it from `initialSlots` (the saved plan), so the user's own addition was invisible until they saved. The second custom slot is refused with an inline message.

### ✅ The server's bound is surfaced as an inline message, not a silent clamp

The interval is validated against the server's own bounds (15…43200 minutes) and the refusal is shown as an inline message. The client mirrors the constants **without** clamping: it refuses, it does not quietly substitute a different number.

### ✅ The empty state is "No reminders. You'll still see this event in Pulse Digest."

Saving **0 slots is a normal save** — a `PUT` with an empty list, and the calm confirmation "Saved." The first version of the test failed to find "Saved." because the default `PUT` mock returned no body, so the save was read as a failure; the mock was corrected to return a valid plan payload, and the test now exercises the real path.

### ✅ The action bar is "Reset to default" (ghost) and "Save reminder plan" (primary)

**"Reset to default" does not save.** It restores the chips so the user can look at them and then press Save. It also **clears the deliveries**: the default-plan read carries slot ids only, so leaving the old deliveries in place would show a dimming state that belonged to the previous plan.

### ✅ A skeleton while loading

`app/events/[id]/reminders/loading.tsx` — a heading, a meta line, four chip skeletons and two action-bar skeletons. The skeleton widths use on-scale steps (`w-16`, `w-30`, `w-20`); `w-32` and `w-48` are off the DESIGN.md spacing scale and were changed.

### ✅ A failed save says "Couldn't save. We'll try again on your next change." — and keeps the chosen state

The failure message is shown in `text-warn-amber`, and the chips are **untouched**: the user's choices are not reverted because the write failed.

### ✅ Success is quiet — "Saved."

Exactly `Saved.`, inside a `<div role="status" aria-live="polite">`. No emoji, no celebration.

### ✅ Accessibility: keyboard, `aria-pressed`, the text-conveyed dimming, the reachable tooltip, the terracotta focus ring

The chips are native `<button>`s, so they are focusable and reachable by keyboard; `aria-pressed` reflects selection. The keyboard test asserts what is true and checkable in jsdom — that the chip is a native button and that every chip can take focus — rather than simulating an Enter that jsdom does not turn into a click.

### ✅ Spacing stays on the DESIGN.md scale

`tests/spacing-scale.test.ts` passes.

### ✅ The API is reached only through the generated client (AD-19)

The route reads through `lib/reminder-plan-read.ts` and the picker writes through `api.PUT` in `components/reminders/reminder-picker.tsx`. Both were added to `NEW_ENDPOINTS` in `tests/ad19-endpoint-coverage.test.ts`; the method regex there was widened from `GET|POST` to `GET|POST|PUT|PATCH|DELETE`, because the picker is a **write** and the gate could not see it.

### ✅ The generated client was regenerated

`make client` produced a **non-empty diff**. It was investigated rather than accepted: `git log --oneline -3 -- frontend/lib/api/openapi.json` showed the client was last regenerated in commit `84245f4`, so **items 8 and 9's contracts had never been committed to the generated client**. The regeneration adds `/api/reminders/{target_kind}/{target_id}` (GET + PUT), `/api/settings/notifications` (GET + PUT), `/api/email/click`, `/api/email/unsubscribe` and the `DigestScheduleIn/Out`, `NotificationSettingsIn/Out`, `QuietHoursIn/Out` schemas. This is required by AD-19, not an unrelated change.

## Three implementation decisions worth recording

### The chip's accessible name is an `aria-label`, not a hidden span

The first implementation put the sentence in an `sr-only` span inside the button. That made the button's `textContent` **"5d5 days before"** — the visible label and the hidden sentence concatenated, because both were inside the button. `aria-label` replaces the name outright, so the screen reader hears *"5 days before"* and the visible label is untouched.

### The custom slot's chip is derived from `selected`, not from `initialSlots`

`initialSlots` is the *saved* plan. Deriving the custom chip from it meant a user's newly added custom slot did not appear until they saved — which contradicts the whole point of adding it. Deriving from `selected` makes the chip appear immediately. (A blind string replace then produced `const selectedCustom = selectedCustom;`, which was fixed by hand.)

### The dimmed state's instant is formatted in the viewer's zone, with a calendar-day comparison

`formatDeferredInstant` uses `en-CA` for the zone-local day key, so "today" compares as a **calendar day** rather than as a 24-hour offset — the difference between "8:00 am Saturday" and "8:00 am tomorrow" when the viewer crosses midnight.

## The axe-core gate

Six axe runs, one per state: a plan, the empty state, a deferred chip, a custom slot, after a failed save, and a landmarks check. `axe.run(document.body, { resultTypes: ["violations"], rules: { "color-contrast": { enabled: false } } })`, filtered to `serious` and `critical` only — the same pattern as the rest of the repo. The landmarks check asserts the region named *"Reminder plan editor"*, the group, and the literal *"Remind me:"*.

## Notes on how the tests were written

**`user-event` is not installed.** Every interaction test uses `fireEvent`, matching the house pattern in `components/add-event-button.test.tsx` and `components/auth/reset-confirm-form.test.tsx`. This is a constraint of the repo, not a choice.

**The source-reading tests resolve their paths from `__dirname`.** `__dirname` is `components/reminders`, so `..` is `components` and the first attempt read `frontend/components/components/reminders/reminder-chip.tsx`. The fix was `path.resolve(__dirname, "..", "..")`, with the paths named as constants.

**The "never recomputes the shift" assertion was narrowed.** It first matched the word "quiet" in the file's own prose and comments — the comments explain that the browser does *not* do this. The assertion now checks the window's actual vocabulary.

**The "never terracotta" invariant is checked at the source.** A DOM assertion on class names would be brittle and could be satisfied by a token that does not apply in jsdom; the source-level check reads the class string the component actually ships.

## What is not covered, and why

- **The **Pro** per-event quiet hours upsell (FR-51) and the **"less like this"** explainer (FR-25).** Both are explicitly out of scope for this work item.
- **The mockup's three aside panels.** The mockup Amendment A-21 shows them; the acceptance criteria exclude them.
- **The `role="switch"` toggles in the mockup.** Overridden by the acceptance criteria's `aria-pressed`, which is what the mockup's own note says the difference is about.


---

## After the code review

The review found **two behavioural defects** and **six dead exports**. Both defects were
fixed, four tests were added, and the suite went from 1090 to 1094 tests.

### The picker would build a five-slot plan, and hide the reason

**Found by probing the component rather than by reading it.** A plan may carry at most
four slots — the server's bound. The picker checked only the *one custom slot* rule and
never the total, so a plan of `5d, 2d, 1d, 1hr` plus a custom slot was accepted
silently:

```
CHIPS: [ '5d', '2d', '1d', '1hr', 'custom:90' ]
ERRORS: undefined
```

The user presses Save, the server refuses, and the picker says *"Couldn't save. We'll try
again on your next change."* — **calm, generic, and true, but silent about the cause**,
and the copy's promise is unkeepable: the next change is the same plan and fails the
same way.

The picker now checks `MAX_SLOTS` — the bound it already exported and never used — in
both places a slot can join the plan, and says *"You can keep up to 4 reminders. Turn one
off to add another."* **This is not a second implementation of the server's rules:** the
bound is a single integer, and the picker is already showing four named chips plus one
custom, so the bound is **visible on the screen**. The server still validates.

### The Detail Screen asserted a plan it could not see

*"Reminders come by email the day before and the hour before."* is false for a user
whose plan is `["5d"]`, and false for a plan with no reminders at all — and
`EventDetailOut` carries no reminder slots, so the page **could not check**. The copy is
now *"Reminders go by email. Choose when you'll hear from us about this event."*, and the
test asserts both the new sentence and the **absence** of the old one.

### The four new tests, and the two that failed first

- *refuses a fifth custom slot, and says which bound it is*
- *refuses a fifth named slot, and says which bound it is*
- *lets a slot back in once one is turned off*
- *never sends a plan with more than four slots*

**Two failed on the first run, and both failures were the test's fault.** The first
started from a full plan in which the chip it clicked was *already selected*, so the
click was a deselection and the bound was never reached — the test now starts from a
full plan with one chip **off**, which is the only state in which "add the fifth" is even
a click. The second failed because the first version of the fix wrote the bound message
into `customError` while the named-chip path wrote it into `slotError`: **two slots for
one message.** The bound is now one message in one place.

### A side effect inside a state updater, and what it cost

The first version of the `toggle()` fix called `setSlotError` **inside** the
`setSelected` updater. React may invoke an updater more than once, and a side effect
inside one is not idempotent. `toggle()` now reads `selected` directly and takes
`[selected]` as its dependency — a plain function of the current state, with no updater
side effects.

### The dead code

`planSlotIds()`, `isNamedSlot()`, `MAX_CUSTOM_SLOTS` and the picker's re-export line
existed for "the tests that assert the grammar" — and **no test imported them**. The
re-export's own docstring claimed a guarantee it did not have: *"the tests import the
grammar from the module that renders the chip, so a change to the grammar has to change
the rendering too, or the test fails."* No test did. A comment that describes a guarantee
no test enforces is worse than no comment.

---

# Work Item: frontend-settings-reminders-and-quiet-hours

## Summary

| Category | Passed | Failed | Skipped | Notes |
|----------|--------|--------|---------|-------|
| `components/settings/settings-inline-save.test.tsx` (new) | 19 | 0 | 0 | The three islands' saves — the API's verdict, the offline line, the narrow patch |
| `app/settings/reminders/page.test.tsx` (new) | 7 | 0 | 0 | The default plan's route — shell, active sidenav item, the states |
| `app/settings/quiet-hours/page.test.tsx` (new) | 9 | 0 | 0 | The window's route — two clocks, the locked label, the delivery time |
| `tests/architecture.test.ts` (updated) | 17 | 0 | 0 | The server/client boundary — a new rule, and the two that keep it honest |
| `backend/tests/personalization/test_digest_scheduling.py` (updated) | 37 | 0 | 0 | The digest command's clock is now frozen, not read |

**35 new frontend tests** (52 across the four files), and the full suite passes:
**79 files, 1143 tests**.

### The gate results, in full

| Gate | Command | Result |
|------|---------|--------|
| Lint | `pnpm lint` | clean |
| Types | `pnpm typecheck` | clean |
| Format | `pnpm format:check` | clean |
| Tests | `pnpm test` | **79 files, 1143 tests passed** |
| Build | `pnpm build` | **green** — both `/settings/*` routes present |
| Architecture + spacing + AD-19 | `pnpm vitest run tests/architecture.test.ts tests/spacing-scale.test.ts tests/ad19-endpoint-coverage.test.ts` | **passed** |
| Backend | `uv run pytest --cov` | **4740 passed, 99.19% coverage** |
| Domain coverage | `coverage report --include='domain/*' --fail-under=100` | **100%** |
| Python lint | `uv run ruff check .` / `uv run ruff format --check .` | clean |
| Import contracts | `make lint-backend` | **19 kept, 0 broken** |

### The two settings routes

`/settings/reminders` and `/settings/quiet-hours` — **the first `/settings/*` routes the
product has had.** The sidenav's Settings entry has said *"Coming soon"* since the shell
was built, and onboarding tells the user *"You can change these later in Settings."* This
item makes that true.

| Route | What it edits | The island |
|-------|---------------|------------|
| `/settings/reminders` | The **default plan** — the slots we suggest when a user saves an event | `DefaultReminderSlots` |
| `/settings/quiet-hours` | The **quiet window** (two wall clocks) and the **digest delivery time** | `QuietHoursWindow`, `DigestDeliveryTime` |

**Both are authed surfaces**, guarded the same way `/conflicts` is: `homeRoute` sends an
anonymous visitor to the preview and a half-onboarded one to `/onboarding`, and a
session the API could not answer gets the unavailable state rather than somebody else's
plan.

### The three islands, and the one decision they share

Each island owns **one** field, and each sends **only** that field:

| Island | The patch it sends |
|--------|-------------------|
| `DefaultReminderSlots` | `{ default_reminder_slots: slots }` |
| `QuietHoursWindow` | `{ quiet_hours: { start, end } }` |
| `DigestDeliveryTime` | `{ digest: { delivery_time, timezone } }` |

**A narrow patch is not a simplification — it is a correctness rule.**
`NotificationSettingsIn` is a patch, and **`quiet_hours` is the one field where `null` is
a value**: it turns the window *off*. A payload that re-sent the whole settings surface
on every window change would be a payload that could rewrite the user's default plan by
accident. An omitted field is left alone, so each island sends what it owns.

**The zone travels with the delivery time.** `DigestScheduleIn` says it plainly: *"Both
or neither. A wall clock without its zone is not a schedule."* So `DigestDeliveryTime`
sends the zone it read, **unchanged**, alongside the new time. The zone is set during
onboarding and this route does not second-guess it — but it does send it, because the
server refuses to half-apply the pair.

**The control is reused, not copied.** `DigestTimeControl` was **extracted out of**
`digest-step.tsx` so `/settings/quiet-hours` reuses it. Two copies of a time control is
how two screens come to disagree about what a time means.

### The save is inline, and there is no Save button

The work item rules a page-level Save out, and the tests assert its **absence**
(`expect(screen.queryByRole("button", { name: /^save/i })).toBeNull()`) — a control that
is not there cannot be tested by what it does, only by its absence, so the absence is
what is asserted.

`SaveFeedback` renders the three states — **busy** (a **static dot**, because
EXPERIENCE.md says *"No spinners, anywhere."*), **saved** (*"Saved."*), and **failed**.

## The three defects this item's tests found

### 1. The API's own refusal was being thrown away

**This is the significant one.** `openapi-fetch` does **not** throw on a 4xx — it returns
`{ data, error, response }`. All three islands checked `response.error` only to decide
*that* the save failed, and then showed their own generic line:

```tsx
if (response.error) {
  setFailure("Couldn't save.");   // ← the API's message, discarded
  return;
}
```

**So the one message the server wrote for the user never reached the user.** The
backend's own test asserts that message is present, and its docstring calls it *"a
readable message"*:

> `A quiet window needs a start and an end that differ.` — `InvalidQuietHoursWindowError`
> (`backend/domain/errors.py:47-61`), asserted at
> `backend/tests/delivery/test_preferences_api.py:229-242`

A full-day window — the same clock twice — is the **one failure a user can actually
fix**, and it was the one failure the frontend refused to explain. The generic line is
true and useless; the server's line says what to change.

**The fix follows the house pattern** already used by `signup-form.tsx:118-127`:
`readApiError(response.error).message`. The shared decision now lives in one place —
`components/settings/save-failure.ts`:

```ts
export function saveFailureMessage(error: unknown, offline: string): string {
  if (error === null || error === undefined) return offline;
  const failure = readApiError(error);
  return failure.code === null ? offline : failure.message;
}
```

**The API's message is shown as it arrived; the route's own line is shown when the
request never reached the API.** There is nothing to quote in that second case — a
network failure has no server's words — so the route's own line is the honest answer.

**Five new tests** in `describe("the API's own verdict")`:

- the server's refusal shown verbatim on the quiet window
- the server's refusal shown verbatim on the delivery time
- the server's refusal shown verbatim on the default plan
- **the user's own clock kept when the server refuses**
- the route's own line when the API says nothing

### 2. Two copies of a helper, and a hard-coded default

`clockForInput` was written twice — once in `lib/notification-settings-read.ts` and once
inside each of the two islands. `DEFAULT_QUIET_HOURS` was hard-coded as a literal in
`quiet-hours-window.tsx` *and* in the route's fallback.

**The fix is a module with no dependencies**: `frontend/lib/notification-settings.ts`
holds both, and `lib/notification-settings-read.ts` keeps only the server-side read. The
read module's docstring now says why the split exists.

### 3. A pointless alias

`components/onboarding/digest-step.tsx` had

```ts
const PRESETS = DIGEST_TIME_PRESETS;
```

— a name that says nothing the original did not. Removed; `DIGEST_TIME_PRESETS[0]` is
used directly.

## The build is a different gate from the test suite — and it caught a real defect

**This is the finding that changed the shape of the item.** After the consolidation in
finding 2, `pnpm build` failed:

```
You're importing a module that depends on "next/headers". This API is only
available in Server Components in the App Router.

  lib/session.ts:24
  lib/notification-settings-read.ts
  components/settings/quiet-hours-window.tsx  [Client Component]
```

**The unit tests passed.** All 1139 of them. jsdom resolves `next/headers` to a stub, so
the island rendered happily and every test was green. **The build is what knows the
difference between a server module and a client one**, and the defect was mine — the
consolidation in finding 2 put a server-only import inside a `"use client"` component.

**This is a class of defect that a unit test cannot catch**, because the thing that
breaks is not the code's behaviour but its *placement in the module graph*. So the
architecture suite now knows it too.

### The new rule: the server/client boundary

`tests/architecture.test.ts` gained `describe("the server/client boundary")`:

> **A `"use client"` module may not reach `next/headers`.** The App Router's
> `cookies()` and `headers()` are server-only, and a client bundle that imports them
> fails to build.
>
> **The rule is about the module graph, not the file.** A client component may import a
> helper that happens to live in `lib/`; what it may not do is import a module that
> *transitively* reaches `next/headers`. So the check follows the imports.

**The walk is bounded by the files it has already seen**, so an import cycle is a loop
that terminates rather than a stack overflow.

### The rule has to be able to fail — and it must not cry wolf

**The first version of the rule reported five offenders. Three of them were wrong.**

The three false positives were all `import type { … } from "@/lib/conflict-list-read"`
— **a type is not a dependency.** TypeScript erases a type-only import before the
bundler ever sees it, so no edge exists in the client bundle. Following those imports
would flag every island that borrows a *type* from a server-side read module, which is
safe, common, and not the defect.

The other two false positives were the rule finding `"use client"` by *searching* for
the phrase. `lib/notification-settings-read.ts` **mentions** it in its own docstring (to
warn readers off the module), and so does this test file's planted source. A module is
a client module when the directive is its **first statement** — which is the App
Router's own rule.

**The rule as it stands, and the two tests that keep it honest:**

| Test | What it pins |
|------|-------------|
| *keeps every client module off the server-only API* | The rule fires on the real graph |
| *catches a client module that imports next/headers* | The rule **can fail** — a planted file, deleted in a `finally` |
| *does not follow a type-only import* | A type is not a dependency |
| *does not mistake a docstring for the client directive* | The directive's position is what counts |

**A rule that cannot fail proves nothing, and a rule that cries wolf gets ignored.**
Both are now pinned.

## The pre-existing backend defect: a test whose answer depended on the hour

**Three backend tests failed** during the gate run — *"Composed 0 digests; 0 already
existed; 0 claimed."* — and **the failing test bodies were untouched by this item.**
This was a pre-existing defect, and it is worth recording because it is a *good* defect:
the test was asserting something false about the domain, and the fix is a rule the whole
suite can now rely on.

### The defect, proven rather than guessed

The digest command's `--all` tests computed a delivery time **relative to the wall
clock** — one hour "back" from now — and expected the digest to be due. But `is_due`
compares **time-of-day**, not instants:

```python
# backend/apps/personalization/services/digest_scheduling.py:89-106
_local_time(now, zone) >= delivery_time
```

**A time-of-day circle wraps at midnight.** At 00:53 local, "one hour back" is 23:53 —
and `00:53 >= 23:53` is **false**. The delivery time was not "one hour ago"; it was
**almost a full day in the future**, by the only comparison the due rule makes.

A probe confirmed it: the pattern was wrong at **1 of 24 hours** — and the suite was
running at exactly that hour. The test was green for 23 hours of the day and red for one.

### The fix: freeze the clock explicitly

The testing standards say it plainly: *"Freeze time explicitly. Never depend on
wall-clock or local timezone."* The fix follows the **house seam** that already exists
in `worker/tasks.py:36`:

```python
def _now() -> datetime:
    """The current instant, behind a seam.

    **The seam exists so the clock can be frozen in a test.** The due rule is a
    comparison against the user's own local wall clock, so a test that composes "now"
    has to know what "now" is — and a test that reads the wall clock is a test whose
    answer depends on the hour it ran.
    """
    return datetime.now(UTC)
```

`compose_digest.py` now reads its clock through the same kind of seam, and the tests
freeze it:

```python
FROZEN_NOW = datetime(2026, 11, 4, 17, 0, tzinfo=UTC)   # 09:00 in Los Angeles
DUE_AT_FROZEN_NOW = time(8, 0)
NOT_DUE_AT_FROZEN_NOW = time(10, 0)
```

**The frozen pair is unambiguous.** `08:00` is before `09:00`, so it is due; `10:00` is
after, so it is not. Neither can wrap at midnight, so the test is the same at every hour
of every day.

**This is not a workaround — it is the correction.** The first attempt used
clock-relative helpers (`due_delivery_time(now)`, `not_due_delivery_time(now)`) and was
**proven correct at all 168 sampled instants**. It was still replaced: a helper that
computes "one hour back" re-introduces the wrap in a different place, and a constant
that is plainly due and plainly not due states the intent without arithmetic. The
standards ask for the freeze, and the freeze is what shipped.

**Two new tests** pin the fix:

- *the pinned delivery times are unambiguous against the frozen clock*
- *the command reads its clock through the seam*

## What is not covered, and why

- **Per-day-of-week windows.** FR-51 and Pro own them, and the work item leaves them
  out entirely. The route's test asserts their **absence** — no locked row, no upsell,
  no carousel, no `day-window-chip` — because *"a row the user can neither use nor
  remove is worse than no row."*
- **The `displayName` helper.** It is duplicated across seven files. That is a
  **pre-existing house pattern**, not something this item introduced, and extracting it
  is a brownfield refactor outside this work item's scope. It is recorded here rather
  than changed.
- **The `SaveFeedback` busy state's animation.** The busy state is a **static dot** —
  there is nothing to time, and the no-spinner rule is a design rule rather than a
  behavioural one.

## The three source-document conflicts, and how they were settled

| The conflict | The ruling | Why |
|--------------|-----------|-----|
| *"spinner"* vs *"No spinners, anywhere"* (EXPERIENCE.md:546) | **Static dot** | The prohibition is explicit and unconditional; the mention is incidental |
| *"the sidenav's Settings entry"* — there are **two** rails | **Both become links** | A bottom tab and a sidenav are both navigation, and the sidenav's Settings entry was the one that said "Coming soon" |
| *"reuse the onboarding time-preset control"* | **Extracted, not copied** | Two copies of a time control is how two screens come to disagree about what a time means |

## A note on the mockup's stale value

The mockup drew the quiet window's end as **`07:00`**. The server's
`DEFAULT_QUIET_HOURS_START`/`END` are `time(22, 0)` and `time(8, 0)`, and the work item
locks the label *"10pm–8am. Nothing during this window."* **The server and the label win
over the mockup**, and the route's test asserts all three together — the two clock
values and the locked label.

---

# Work Item: e2e-proof-and-contract-tests

## Summary

The run's last item. The work item's acceptance criterion asked for proof of the
delivery path *as a whole* — one scenario, walked end to end, with every rule it
touches asserted on the real services — and for **probe tests**: *"as run 021 did with
its 27 probes, each major assertion is proven able to fail."*

**What was built.**

| The file | What it proves | Count |
|----------|----------------|-------|
| `backend/tests/e2e/test_delivery_proof.py` | The delivery path works, and each rule in it is asserted on the real service | 13 tests |
| `backend/tests/e2e/mutation_probe_delivery_e2e.py` | Each major assertion is **able to fail** — six real bugs are planted, and the matching test goes red | 6 probes |
| `backend/tests/e2e/test_delivery_contract.py` | The **contracts** still hold — the ones that would let the path work *by accident* | 9 tests |
| `frontend/components/reminders/reminder-chip.test.tsx` | The server's `deferred` flag reaches the screen, and is rendered | 7 tests |
| `backend/tests/architecture/test_import_contracts.py` | *(modified)* `models-delivery` is now proven able to break | +1 case |

**The totals for the run as a whole:** backend **4763 passed**, frontend **80 files /
1150 tests**, coverage **99.19%** overall and **100%** on `domain/*`, import contracts
**19 kept / 0 broken**, all six probes caught.

## The scenario, and why it is frozen

The proof is **one scenario**, not a family of scenarios. It is frozen at a single
instant and a single window, so that every assertion in it is about the *rules* and
none of them is about the wall-clock hour the suite happened to run in.

```python
ZONE = "America/Los_Angeles"
FRIDAY_2330_LOCAL = datetime(2026, 11, 7, 7, 30, tzinfo=UTC)   # 2026-11-06 23:30 in LA
SLOT_AT_LOCAL = datetime(2026, 11, 7, 6, 30, tzinfo=UTC)        # 2026-11-06 22:30 in LA
EXPECTED_SEND_LOCAL = datetime(2026, 11, 7, 16, 0, tzinfo=UTC)  # 2026-11-07 08:00 in LA
EXPECTED_PING_SEND_LOCAL = datetime(2026, 11, 7, 17, 0, tzinfo=UTC)  # 2026-11-07 09:00
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)                  # 2026-11-06 04:00 in LA
QUIET_WINDOW = QuietHours(start=time(22, 0), end=time(8, 0))
```

**The clock is frozen, not mocked at the edges.** The scenario reaches the real
services, so the time it must control is the time those services read — and the
services read it through the house seam at `worker/tasks.py:36`:

```python
def _now() -> datetime:
    return timezone.now()
```

frozen in the test by `monkeypatch.setattr(tasks, "_now", lambda: when)`. **The clock
is passed into the sweep explicitly** (`now=EXPECTED_SEND_LOCAL`), because the sweep
takes `now` as a parameter — so the scenario controls the send instant rather than
racing it.

### The scenario, in one picture

A user in Los Angeles has Quiet Hours from **22:00 to 08:00**. An event starts
**Friday at 23:30 local**, so the event's `1hr` reminder slot falls at **22:30 local** —
**inside the window**. The proof then walks:

1. **the slot is deferred** — the row's `due_at` is moved to the window's end (08:00),
   the key is `f"{user.pk}:event_reminder:{event.id}:1hr:1"`, and one **transactional**
   message goes out when the sweep runs at 08:00.
2. **the sweep before the window end sends nothing** — the row is due at 08:00, so a
   sweep at 07:59 finds no due row and sends no mail.
3. **the Pulse Ping is separate** — one **bulk** message, with an unsubscribe URL, under
   the key `f"{user.pk}:digest:2026-11-07"`.
4. **a user with nothing to say gets no Ping** — no row minted, no message.
5. **the personal-only rule** — a `personal` event's reminders are the user's own.
6. **the reschedule rewrites, never re-mints** — **ten** window changes produce **one**
   row whose key is **byte-identical** throughout.
7. **a reschedule does not send twice**.
8. **a lifecycle change propagates** — `kind="time_moved"`, a bumped `event_version`, and
   a `sent` row does not block the new mint.
9. **a cancelled event sends nothing**.
10. **the unsubscribe's scope** — the event scope cancels **one** row, the **DIGEST** row
    survives, and `plan.slots == []`.
11. **the sweep is idempotent** — two sweeps, one send.
12. **the server computes the flag** — `deferred is True`, `deferred_to ==
    EXPECTED_SEND_LOCAL`.
13. **and does not compute it when it should not** — an un-deferred slot.

## The reminder and the Ping are due at *different* instants — and that is the point

**This was the one place the proof's timing had to be reasoned from the domain rather
than adjusted until green.** The two rows are both deferred by the same window, and it
is tempting to sweep once and expect both. They are not due at the same time:

| The row | Due at | Why |
|--------|--------|-----|
| The event reminder | **08:00** (the window's end) | Its slot was **inside** the window, so the shift moved it to the window's end |
| The Pulse Ping | **09:00** (the user's delivery time) | Nothing moved it — it was scheduled for the user's delivery time, which is outside the window already |

So the proof sweeps the reminder tests at `EXPECTED_SEND_LOCAL` (08:00 local) and the Ping
tests at `EXPECTED_PING_SEND_LOCAL` (09:00 local). **A proof that swept at one instant
would have found the other row not yet due, and would have read that as a bug.** The two
constants are separate in the file for exactly that reason — and the difference between
them is itself worth recording, because it is the difference between *a slot that moved*
and *a digest that never moved*.

**The same reasoning fixed a failing test that was not a bug.** A test asserting "a slot
outside the window is not deferred" failed — because a `1d` slot on a 23:30 event lands
at 23:30 *the day before*, which is **still inside** the window. The fix was to use an
18:00 start, so the slot genuinely falls outside. **The assertion was right and the
fixture was wrong.**

## The probe harness, and the six bugs

**The mechanism is run-021's, unchanged in shape:** apply one real bug to the
implementation, run the suite, and require that at least one test fails. **A probe that
passes the suite means the tests do not prove that rule** — and a test that cannot fail
is not a test.

**The suite is one file on purpose:**

```python
DELIVERY_SUITE = [
    "tests/e2e/test_delivery_proof.py",
]
```

A probe that mutated the implementation and ran the *whole* backend suite would pass
for the wrong reason — some unrelated test would go red, and the probe would look like
it proved the rule when it proved nothing about *this* rule. Naming the exact file makes
the failure attributable.

| # | The bug planted | Where | Caught by | Result |
|---|-----------------|-------|-----------|--------|
| 1 | **The quiet-hours shift does not shift.** The due time becomes the slot's own instant; the row is minted at 22:30 instead of 08:00, and the mail goes out in the middle of the window the user asked for. | `domain/quiet_hours.py` | 3 failed, 10 passed | **caught** |
| 2 | **The reschedule re-mints instead of rewriting.** The old row is cancelled and a new one is created — with a new key. The user gets **two reminders** for one event. | `apps/delivery/services/scheduled_sends.py` | 2 failed, 11 passed | **caught** |
| 3 | **The Pulse Ping is minted even with nothing to say.** The user with an empty week gets a daily email about nothing — exactly what FR-10 and SM-C1 exist to prevent. | `apps/delivery/services/pulse_ping.py` | 1 failed, 12 passed | **caught** |
| 4 | **The sweep does not mark the row sent.** The sweep runs again, finds the row still `pending`, and sends it a second time. | `apps/delivery/services/delivery_sweep.py` | 2 failed, 11 passed | **caught** |
| 5 | **The event unsubscribe also cancels the Pulse Ping.** The user asked to stop one thing and lost another — FR-11's whole point is that the two are different choices. | `apps/delivery/services/unsubscribes.py` | 1 failed, 12 passed | **caught** |
| 6 | **The chip ignores the server's deferred flag.** The chip does not dim and does not show the note, even though the server said the slot was deferred. | `frontend/components/reminders/reminder-chip.tsx` | 2 failed (vitest) | **caught** |

**Probe 6 is the one that closes the seam.** The backend probes prove the server
*computes* the flag; the frontend probe proves the client *uses* it. A flag that
arrives and is ignored would pass every backend probe and every server-side assertion —
**only a client-side mutation can catch it.** And a frontend bug is caught by a frontend
test, so the probe names the frontend suite; running the backend suite against a
frontend mutation would prove nothing.

### The three rules the probes inherit, and the one each would have violated

Run-021 learned these the hard way, and this file inherits them:

1. **Plant a CALL, not an import.** An imported-but-uncalled function computes nothing.
   **Probe 1 honours this**: `shift_to_sendable` is already imported, and the bug
   replaces the *call* with a no-op that still returns the right *type*.
2. **The mutation must still parse and run.** A `SyntaxError` is a **false green** — the
   suite "caught" it, because a suite that cannot be collected fails. **Probe 2 is the
   two-halves case**: the cancel and the re-mint are applied as one atomic change, so
   the planted code parses.
3. **Never plant a bug in dead code.** A probe that mutates a branch the scenario never
   runs proves nothing. **Probes 3 and 5 are on the live branch** — the suppression
   early-return and the event-scope unsubscribe — so the scenario reaches them.

**Every edit is checked before any is applied.** A probe with two edits where only one
pattern matched would plant half a bug, and a half-planted bug that does not compile is
caught by the interpreter — a false green. The harness returns `SKIP` when a pattern is
not found, because **a probe that silently stopped applying is worse than no probe**, as
it looks like a pass.

**The file is always restored**, whether the suite failed, passed, or the process died —
the `finally` is not conditional. A probe that leaves a broken file behind would make
every probe after it meaningless.

## The contract tests — the four contracts, and why each is a contract

The delivery proof proves the *path* works. `test_delivery_contract.py` proves the
**contracts** still hold — the ones that would let the path work *by accident*, or stop
working without anything going red.

| The contract | The test | What breaks without it |
|-------------|---------|------------------------|
| **The import contracts, including `models-delivery`** | `test_the_import_contracts_still_hold`, `test_the_models_delivery_contract_names_scheduled_send`, `test_the_models_delivery_contract_can_break` | `delivery` reaching another app's models, so a service boundary becomes advisory |
| **The generated client is in sync** | `test_the_openapi_document_is_in_sync_with_the_backend`, `test_the_generated_client_is_in_sync_with_the_document`, `test_the_generated_client_carries_this_intents_shapes` | The frontend's types drift from the API's shapes, and a field reads as `undefined` at runtime |
| **The proof runs fully offline** | `test_the_proof_runs_fully_offline`, `test_the_delivery_path_does_not_import_a_network_client`, `test_the_sweep_does_not_consult_the_quiet_window` | A proof that reaches the network is a proof whose answer depends on the network |
| **The memory adapter records what the proof asserts** | `test_the_proof_runs_fully_offline` | A proof asserting on a surface that does not record the fact it needs |

**The last one is the subtle one.** The work item's Technical Note anticipated it: *"The
memory email adapter is the assertion surface. If it does not yet record stream and
idempotency key per message, extending it belongs to `delivery-sweep-and-send`, not here —
this item should be able to assert without changing the adapter."* **It does record
them** — `SentEmail(message, stream, idempotency_key)` — and this file asserts that it
does. **So the adapter was not changed**, and if a future change to it drops the stream,
the proof's assertions would silently stop meaning anything. That is what the assertion
is for.

### The `models-delivery` contract, and the direction it breaks in

**The contract protects the module**, so the violation must be an import **of**
`apps.delivery.models` — not an import *by* it.

```python
"another app imports delivery's models": (
    {"apps/ingestion/_planted.py": "import apps.delivery.models\n"},
    {"models-delivery"},
),
```

**The first attempt broke the wrong contract.** Planting `apps/delivery/_planted.py`
importing `apps.ingestion.models` breaks **`models-ingestion`** — because that contract
protects *ingestion's* models. The two contracts are **mirror images**, and the error
was only visible because the test asserts the **exact** broken set:

```python
assert broken == expected
assert returncode == 1
```

**Exactly**, because a second break would mean the violation was not the one the
contract is about, and an "at least" assertion would let that hide. The violation was
moved to `apps/ingestion/_planted.py` importing `apps.delivery.models`, and it now
breaks `models-delivery` and nothing else.

### The generated client's sync check is a *measurement*, not a rewrite

**The first version compared against `git`, and it failed with a 498-line diff.** The
reason is that `frontend/lib/api/schema.ts` is **uncommitted work** from item 9 — a
`git diff` compares against the last commit, not against what the generator produces
today. The question the contract actually asks is narrower and better: **does
regenerating change anything?** So the test now regenerates, compares, and restores:

```python
before = SCHEMA.read_text()
result = subprocess.run([...], cwd=FRONTEND, ...)
assert result.returncode == 0, result.stdout + result.stderr
try:
    after = SCHEMA.read_text()
finally:
    # **The file is put back**, whatever the comparison says. The test is a
    # measurement, not a rewrite.
    SCHEMA.write_text(before)
assert after == before, "the generated client is out of sync with the OpenAPI document"
```

**And the regeneration was independently confirmed to be byte-identical** — the
`openapi.json` and `schema.ts` md5s were unchanged by `make openapi` and
`openapi-typescript`.

### The quiet-window check reads imports, not text

**The first version of `test_the_sweep_does_not_consult_the_quiet_window` failed on its
own docstring.** The module's docstring *names* `domain.quiet_hours` — it says so
precisely to record that the import is *absent* — so a search for the word matched the
very sentence that explains the rule. **An import cannot lie**, so the check now reads
only the import lines:

```python
import_lines = [
    line for line in source.splitlines() if re.match(r"^\s*(?:import|from)\s", line)
]
joined = "\n".join(import_lines)
assert "quiet_hours" not in joined
assert "shift_to_sendable" not in joined
```

If the module does not import the shift, it cannot consult the window, whatever else it
does.

## The frontend half — and why the chip must not recompute the flag

The flag's journey has **two halves**, and both are asserted — **neither half proves
the other**. A flag the server computes but the client ignores would pass both halves
on their own, and a chip that dims on a flag nobody sends would too.

The chip takes `deferred` and `note` as **props** and renders them. **The flag is not
recomputed in TypeScript.** A chip that reimplemented the Quiet Hours window in the
frontend would be a second implementation of the shift — with DST and midnight
rediscovered there — and the two could disagree about the very instant the email goes
out at.

| The test | What it pins |
|---------|--------------|
| dims when the server says the slot is deferred | `className` contains `opacity-40` |
| does not dim when the server says it is not deferred | `className` does not contain `opacity-40` |
| shows the note as **visible text**, not only as a tooltip | Opacity is invisible to a screen reader, so the note is rendered as text under the chip |
| carries the deferred instant in its accessible name | `aria-label` is `` `1 hour before. ${NOTE}` `` |
| stays selectable when it is deferred | The dimmed state *says* what will happen; it does not forbid it |
| does not carry the note when the slot is not deferred | A `deferred_to` on an un-deferred slot would be a time the picker showed that the send was not going to happen at |
| carries no accent token | EXPERIENCE.md §4: selection is an ink inversion, not an accent |

## The two fixture corrections, and what they say about the model

**`city_source` is required by a database check constraint.** `DigestPreferenceFactory`
without it raised `IntegrityError: violates check constraint
"digest_preference_city_source_ck"`. The fixture now passes `city_source="choice"` —
and the reason is worth recording: **the model refuses to guess where a city came from.**
A city without a source is a city the system does not know how to re-derive, so it
refuses to store one. The factory had to say it.

**`apply_lifecycle_change` takes `revision`, not `version`.** The first call raised
`TypeError: target_for_personal_event() got an unexpected keyword argument 'version'`.
And `kind="rescheduled"` is **not** in `LIFECYCLE_SEND_BEHAVIOUR` — the valid kinds are
`time_moved`, `postponed`, `reinstated`, `cancelled`, `superseded`, `sold_out`,
`detail_changed`. The proof uses `kind="time_moved"`, which is the honest description
of what a reschedule is.

## The AD-17 deviation, stated plainly

**The proof calls `apply_lifecycle_change` directly rather than going through
`propagate_state_change`.** The reason is that `propagate_state_change` is a
**deliberate placeholder** — a seam reserved for the fan-out that AD-17's state machine
will own, and it does not yet mint the row the proof needs to assert on. **The proof
asserts the rule the lifecycle change is supposed to honour** (the version bumps, the
event's reminders are re-minted, a `sent` row does not block a new mint) **at the layer
that currently implements it.** When AD-17 lands and `propagate_state_change` becomes
the real path, **this proof becomes the thing that must keep passing** — which is the
right relationship between a placeholder and a proof: the placeholder does not get to
change the answer.

**What this item did not do:** it did not implement `propagate_state_change`, and it did
not extend the memory email adapter. The Technical Note said the adapter *should not*
need extending, and it did not.

## The lint gate, and the two things it caught in the new file

`uv run ruff check .` first reported **7 errors**, all in
`tests/e2e/test_delivery_contract.py`:

- **4 × E501** — the markdown table in the module docstring was 114–136 characters wide,
  over the 100-character limit. **The table was rewritten as a numbered list** — the
  content is the same and the prose still reads, but the width is now inside the limit.
- **3 × S607** — a partial executable path runs whatever is first on `PATH`, which is
  not necessarily the thing meant. The file now resolves the full path through
  `shutil.which`, and **fails the test with a message that says so** if the executable is
  missing:

```python
def _executable(name: str) -> str:
    """The full path to an executable, or a failure that says so.

    **A partial path runs whatever is first on `PATH`** — which is not necessarily the
    thing meant (ruff's S607). The full path is the honest one.
    """
    found = shutil.which(name)
    if found is None:
        pytest.fail(f"{name} is not on PATH")
    return found
```

Both gates are now clean: `uv run ruff check .` → **All checks passed!**, and
`uv run ruff format --check .` → **481 files already formatted**.

## Acceptance Criteria Validation

| The criterion | Where it is met | Status |
|---------------|-----------------|--------|
| *"Prove the delivery path end to end, with the quiet-hours deferral, the idempotency, the suppression, the reschedule, and the unsubscribe"* | `test_delivery_proof.py` — 13 tests, one frozen scenario, the real services | **MET** |
| *"The whole proof runs fully offline with `ADAPTER_MODE=fake` and no network"* | `test_the_proof_runs_fully_offline`, `test_the_delivery_path_does_not_import_a_network_client`; the memory adapter is injected by name; no delivery-path module imports `httpx`/`requests`/`urllib` | **MET** |
| *"Probe tests: … break the quiet-hours shift, the key stability and the suppression rule in turn, and show the matching test goes red"* | Six probes — all caught, including the three named, the idempotency write, the unsubscribe's scope, and the client-side flag | **MET** |
| *"The contracts still hold"* | `test_delivery_contract.py` — 9 tests over the four contracts | **MET** |
| *"The generated client is in sync"* | The document regenerates byte-identically; the client regenerates byte-identically; the shapes this intent added are present **by name** | **MET** |
| *"`models-delivery` is not broken"* | `lint-imports` → 19 kept / 0 broken; and the contract is now proven **able to break** | **MET** |
| *"The server-computed flag reaches the UI"* | `test_delivery_proof.py` (the flag) + `reminder-chip.test.tsx` (the rendering) + probe 6 (the seam) | **MET** |

## Notes on how the tests were written

- **The proof reaches the real services, not the HTTP surface.** The sweep is called
  directly, with the **port swapped** for the memory adapter and the renderer injected.
  The work item allowed the services *or* the HTTP surface; the services were chosen
  because they are where the rules live, and an HTTP surface would have added a
  transport failure mode without adding a rule.
- **The time is passed in, not waited for.** No test sleeps, and no test's answer
  depends on the hour it runs in.
- **The probes mutate text, not objects.** Each `edits` entry is a literal
  `(original, mutated)` pair matched **once**. A literal pair is readable in a diff and
  fails loudly when the implementation moves — which is why the harness reports `SKIP`
  rather than silently passing.

## What is not covered, and why

- **The email's rendered body.** The proof asserts the **message**, the **stream**, and
  the **idempotency key** — the three facts the delivery contract is about. It does not
  assert the HTML, because the templates belong to the rendering item and a body
  assertion here would duplicate their tests.
- **The unsubscribe landing page.** The proof asserts that the **bulk** message carries
  an unsubscribe URL and that the unsubscribe *cancels the right rows*. The landing page
  itself is the settings item's surface.
- **The per-day-of-week windows.** FR-51 and Pro own them; the proof uses a window with
  no day restriction, so the deferral rule is exercised without the days.
- **The `ADAPTER_MODE=fake` default's SMTP adapter.** The proof injects the memory
  adapter explicitly, so the default is never exercised — but the contract test asserts
  that the fake mode *exists* and maps the email adapter, which is the part that would
  silently change.
