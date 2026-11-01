---
run: run-eventpulse24-023
work_item: notification-preferences-api
intent: delivery-and-reminders
generated: 2026-11-01T00:00:00Z
status: complete
---

# Code Review: The Notification Preferences API — one settings surface over two modules

**Run**: `run-eventpulse24-023`
**Intent**: `delivery-and-reminders`
**Work item**: `notification-preferences-api` (the 9th)
**Files reviewed**: 16
**Tests after the review**: **4738 passed**, coverage **99.19%**, `domain/*` **100%**, **19/19** import contracts kept

---

## Scope

| File | Type |
|------|------|
| `backend/apps/delivery/preferences_api.py` | created — the router, the `GET` and the `PUT` |
| `backend/apps/delivery/services/preferences_read.py` | created — the published read, assembled across two apps |
| `backend/apps/delivery/services/preferences.py` | created — the patch, and the one transaction around the writes and the rewrite |
| `backend/apps/delivery/schemas.py` | modified — the five settings shapes |
| `backend/apps/delivery/models.py` | modified — `ScheduledSend.slot_at` (D13) |
| `backend/apps/delivery/migrations/0005_scheduledsend_slot_at.py` | created — the column |
| `backend/apps/delivery/services/scheduled_sends.py` | modified — `slot_instant`, the `slot_at` writes, the rewrite |
| `backend/apps/delivery/send_keys.py` | modified — `digest_local_date_from_key` |
| `backend/config/api.py` | modified — the `/api/settings` mount |
| `backend/tests/delivery/test_preferences_api.py` | created — 32 tests |
| `backend/tests/delivery/test_send_keys.py` | modified — 4 tests |
| `backend/tests/delivery/test_scheduled_sends.py` | modified — 3 tests |
| `backend/tests/delivery/factories.py` | modified — `slot_at` on the factory row |
| `backend/tests/architecture/test_digest_composition_separation.py` | modified — the new request module |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | regenerated |

---

## Automated Gates

| Tool | Result |
|------|--------|
| `ruff check` (16 files) | **All checks passed!** |
| `ruff format --check` (16 files) | **14 files already formatted** |
| Architecture suite | **799 passed** |
| Delivery + personalization + api suites | **1758 passed** |
| Full backend suite | **4738 passed**, 0 failed |
| Coverage (overall) | **99.19%** (gate 80%) |
| Coverage (`domain/*`) | **100%** (gate 100%) |
| `lint-imports` (import-linter, 19 contracts) | **19 kept, 0 broken** |

---

## Findings

### AUTO-FIXED — Mechanical

**None.** The review ran `ruff check` and `ruff format --check` across all sixteen files and
found nothing to fix: no unused imports, no unsorted imports, no over-long lines, no
formatting drift. The two mechanical findings this item had *during* implementation — the
unused `Sequence` import left behind by a removed wrapper, and the single-quoted generated
migration — were fixed at the time and are not repeated here.

### CONFIRMED AND FIXED — Behavioural

Two findings were raised during this item's implementation and are recorded in full in
`test-report.md`; both were correctness issues with an unambiguous right answer, and both
are covered by named tests.

---

#### Finding 1: The rewrite could not re-time a **deferred** row — the bug was already in the tree

**The problem.** `reschedule_pending_for_user` re-timed a pending row by deriving the
event's start from the row's stored `due_at`: `due_at + offset`. But `due_at` is the
**already-shifted** instant — a reminder pushed from 22:30 to 08:00 has no memory of 22:30.
So the derivation **compounds the deferral**: a row already pushed to 08:00 reads as one
that was for 09:00, and re-shifting that lands on the wrong hour again.

That makes the whole point of a Quiet Hours write — *moving a deferred row back to the hour
it was for* — unreachable. It was not a new bug introduced by this item; it was a bug in
the tree that this item's acceptance criteria are the first to exercise.

**Why the obvious fix was rejected.** The pre-shift instant could be **read** from the
owner instead of **stored** on the row: `personalization` publishes batched reads of the
personal events' and saved events' starts, and the rewrite could read them in two queries.
That implementation was written, and it was **discarded**, for two reasons:

1. **It broke the codebase's "ids by value" convention.** A pending row's fate must not
   depend on a backing record existing. The row is minted against a target "by value",
   and `ReminderPlanFactory`'s own docstring says so: *"No personal event needs to
   exist."* A rewrite that went looking for the event would leave a user with a pending
   reminder and no event — a row it could not re-time.
2. **It broke an existing test** — `test_rescheduling_rewrites_due_at_without_changing_keys`,
   which mints against a synthetic target with no `SavedEvent` behind it. That test was
   asserting the right thing, and the implementation was wrong.

**The fix that was chosen.** The row **stores** the instant it was for. `ScheduledSend`
gains a nullable `slot_at` column: the instant the slot names, **before** Quiet Hours moved
it. `due_at` remains the shifted instant — the true send time. The pair mirrors the
`event_version` pattern already on the model: one fact frozen at minting, one re-stamped by
a later write.

```python
slot_at = slot_instant(start_utc=target.start_utc, slot=slot)
due_at = slot_due_at(start_utc=target.start_utc, slot=slot, zone=zone,
                      window=preference.quiet_hours)
```

and the rewrite becomes one uniform arithmetic:

```python
due_at = shift_to_sendable(row.slot_at, window=preference.quiet_hours, zone=zone)
```

**Why this is the better answer, and not merely the easier one.** It is **cheaper** than
the AC's bound: the zone is read once, the rows are read once, and **the user's calendar is
not read at all**. It needs no lookup, so it cannot be wrong about a lookup that does not
exist.

**The digest is the one thing `slot_at` does not serve.** A digest is about a **time of
day**, not an event, so a delivery-time change must move it. Its local date is immutable
and lives **only inside its key** (`user_id · digest · local_date`), so the rewrite rebuilds
the pre-shift instant from the key's date and the *current* delivery time — exactly what
`mint_digest` does. The parser lives **beside the builder**, in `send_keys`, because a key
shape parsed in two places is a key shape that will be parsed wrongly in one of them.

**Verified.** `test_a_deferred_row_keeps_the_instant_it_was_for` pins the round trip:
the row is deferred to 08:00, quiet hours turned off bring it back to 22:30, turning them
on again pushes it back to 08:00 — and `slot_at` never moved.

---

#### Finding 2: Two dead-code items the coverage gate found — removed, not covered

The coverage gate reported two unreachable pieces in `preferences.py`:

- **`SettingsPatch.is_empty`** — a property no caller read. It would have been the
  natural way for a caller to ask "did this patch mention anything?", and no caller
  asked it.
- **`set_default_slots`** — a convenience wrapper around `set_default_reminder_slots` that
  nothing called. A second spelling of one command is a second thing that can drift.

Both were **removed** rather than given a test. The repo's own rule is that dead code
"looks like a feature": a wrapper with no caller reads as an API, and a future caller would
reach for it without knowing it is a duplicate.

### CONSIDERED AND DELIBERATELY NOT CHANGED

#### The `PUT` uses patch semantics on a `PUT` route

The route is a `PUT` and the body is a **patch** — an omitted field is left alone. A
strict `PUT` replaces the resource; this one applies what it is told.

**Why it is not changed.** The AC says so: *"Every field is optional, and an omitted field
means 'leave it alone'."* A `PUT` that replaced the whole resource would clear the user's
quiet hours every time they moved their delivery time, which is not a settings screen —
it is a footgun with a `PUT` on it. The route verb is the conventional one for *"save the
settings I am sending"*; the *semantics* are documented on the endpoint, in the schema
field descriptions, and in the generated OpenAPI.

The distinction is not left to a sentinel, which is the usual way this goes wrong. It is
carried by **which fields the client actually sent** — Pydantic v2's `model_fields_set` —
and the review verified end to end that Ninja preserves it:

```
model_validate({'quiet_hours': None, 'default_reminder_slots': [], 'digest': None})
  → fields_set = {'quiet_hours', 'default_reminder_slots', 'digest'}
model_validate({})
  → fields_set = set()
model_validate({'digest': {'delivery_time': '07:00'}})
  → REFUSED (the zone is required alongside the clock)
```

#### The digest pair is required at the schema level, and the service's safety net is redundant with it

`SettingsPatch.touches_digest_schedule` requires **both** `delivery_time` and `timezone`,
and `_patch_from` sets both or neither — because `DigestScheduleIn` requires both fields,
so a half-pair is refused by Pydantic with a 422 before it reaches the service.

The service-level check is therefore redundant *for this caller*. It was kept anyway, and
the reason is in its own docstring: **a service reachable by more than one caller must not
depend on all of them being careful.** The API's guarantee is a convenience; the service's
is the contract.

#### `digest: null` is treated as "not mentioned"

`digest` is `DigestScheduleIn | None`, so `null` is a legal value on the wire — and
`_patch_from` treats it as *leave the digest alone*, the same as omitting it.

**Why.** "Turn the digest off" is not a state the product has: a user who does not want
the digest **unsubscribes** from the Pulse Ping, which is a different endpoint with its own
audit trail. There is no "no delivery time" to write, so `null` has nothing to mean, and
giving it one would invent a state the rest of the system does not know how to hold.

The `quiet_hours` field is the one place `null` **is** a value, and it is a value there —
"off" is exactly what the user chose. That asymmetry is deliberate and it is stated in the
schema, the endpoint description and the generated client.

---

## The architecture rules, checked rather than assumed

| Rule | How it is checked |
|------|-------------------|
| **AD-2 / AD-3** — layers point inward; no cross-app model reads | `test_the_get_assembles_the_response_across_the_two_modules` parses `preferences_api.py` with **`ast`** and asserts it imports neither app's models. `delivery` reads `personalization`'s facts through the published `get_delivery_settings`. |
| **AD-5** — every write is a named, audited command | Each write (`set_quiet_hours`, `set_default_reminder_slots`, `set_digest_preference`) writes its audit row in the same transaction as its change. The API layer writes no rows. |
| **AD-7** — the key is minted once, never derived from `due_at` | `test_the_keys_are_unchanged_across_ten_successive_changes`; the row count is asserted unchanged too. `reschedule_pending_for_user` has no create path, asserted structurally. |
| **AD-8** — one literal per constant | The default-plan write calls `validate_slots` — **the same function** `reminder_plans` calls — so the 0-to-4 rule, the named tiers, the custom-slot grammar and the error codes are one declaration, not two. |
| **AD-12** — the personal surface is session-scoped | The auth is on the **router**; no endpoint takes a user id as an input, so the scoping cannot be talked out of by a payload. |
| **AD-16** — strict write ownership | `delivery` owns `NotificationPreference` and writes it directly. `personalization` owns `DigestPreference`, so `delivery` calls `personalization`'s published `onboarding.set_digest_preference` — **the same command onboarding's endpoint calls**, so there is one writer for that row and one validation for that zone. The import is function-local, because `personal_events` imports `reminder_plans`, which reaches `delivery`'s services. |
| **AD-19** — the OpenAPI schema is the contract | `make client` regenerated the client: **1015 insertions**, no hand-written TypeScript. |
| **No cross-schema transaction** | Both modules write to `personal`, so their `atomic(using=PERSONAL)` blocks **nest** — one transaction, and the second write's failure rolls the first back. |

---

## The lock order, and why it is fixed

`notification_preferences` takes `b"eventpulse24-ntf"`; `onboarding` takes
`b"eventpulse24-onb"`. They lock **different rows**, so both are needed for a request that
writes both — and the order must never vary, or two concurrent such requests could
deadlock.

**`delivery` first** is the right order, and the reason is not arbitrary: a request that
writes only `delivery`'s settings takes only `delivery`'s lock, so the one-lock path never
waits on the two-lock path, and **no cycle can form**. The two-lock path is the only one
that waits, and it waits for the same lock first every time.

---

## The query bound, measured rather than asserted

The AC asks for the rewrite to be "bounded and batched — one pass over the user's pending
rows, not one query per row, and the zone read once".

| | What it costs |
|---|---|
| The zone | **one** published read, outside the loop |
| The rows | **one** query, `select_for_update()`, filtered to `pending` |
| The user's calendar | **nothing** — the row carries the instant it was for |
| Per-row queries | **none** — the arithmetic is `shift_to_sendable(slot_at, window, zone)`, pure |

`test_the_rewrite_reads_the_zone_once_not_once_per_row` measures it with
`CaptureQueriesContext`: a user with **four** pending rows must not cost four extra zone
reads, and the delta is asserted against a one-row user. `test_the_rewrite_does_not_read_the_calendar`
pins the bound from the other side — it inspects the rewrite's source and asserts it never
names `get_personal_event`, `get_saved_event`, `list_personal_events` or `list_saved_events`.

**The bound is tighter than the AC asked for**, and that is the honest result rather than a
stricter implementation of the same thing: the AC assumed the rewrite would look up the
event's start, and it does not.

---

## What the review changed, in numbers

| | Before the review | After |
|---|---|---|
| Full backend suite | 4738 passed | **4738 passed** |
| Coverage (overall) | 99.19% | **99.19%** |
| Coverage (`domain/*`) | 100% | **100%** |
| Import contracts | 19 kept | **19 kept** |
| `ruff check` / `ruff format --check` | clean | **clean** |
| Architectural changes made by the review | — | **none** |

**The review changed no code.** It verified the implementation against every rule the
work item names, checked the two behavioural findings above were fixed correctly and
completely, confirmed the patch semantics end to end through Ninja, and re-ran every gate.

---

## Remaining suggestions (not applied — no approval given)

None. Every finding above was either mechanical (fixed at the time) or a correctness issue
with an unambiguous right answer (fixed with a test). The design questions the review
surfaced — the `PUT`-that-patches, `digest: null` having no meaning, and the redundant
service-level pair check — were **answered rather than deferred**, and the answers are
recorded above with the reasoning that drove them.

---

# Code Review: The Reminder Plan API — filling an empty router

**Run**: `run-eventpulse24-023`
**Intent**: `delivery-and-reminders`
**Work item**: `reminder-plan-api` (the 8th)
**Files reviewed**: 18

---

## Scope

| File | Type |
|------|------|
| `backend/apps/delivery/services/reminder_plan_read.py` | created |
| `backend/apps/delivery/services/slots.py` | created |
| `backend/apps/delivery/schemas.py` | created (the file existed and was empty) |
| `backend/apps/delivery/api.py` | modified (the two endpoints) |
| `backend/config/api.py` | modified (the `/reminders` mount) |
| `backend/apps/delivery/services/reminder_plans.py` | modified (`save_plan_slots`, `slot_offsets`) |
| `backend/apps/delivery/services/scheduled_sends.py` | modified (`slot_due_at`, `slot_offset` published) |
| `backend/apps/personalization/services/saved_events.py` | modified (`get_saved_event`) |
| `backend/shared/constants.py` | modified (the custom-slot bounds) |
| `backend/apps/delivery/send_keys.py` | modified (the key-length comment) |
| `backend/tests/delivery/test_reminder_plan_api.py` | created |
| `backend/tests/delivery/test_reminder_plan_read.py` | created |
| `backend/tests/delivery/test_slots.py` | created |
| `backend/tests/delivery/test_reminder_plans.py` | modified |
| `backend/tests/delivery/test_notification_preferences.py` | modified |
| `backend/tests/delivery/test_scheduled_send.py` | modified (the planner flake) |
| `backend/tests/personalization/test_saved_events.py` | modified |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | regenerated |

## Automated Gates

| Tool | Result |
|------|--------|
| `ruff check` | **All checks passed!** |
| `ruff format --check` | **473 files already formatted** |
| `lint-imports` (import-linter, 19 contracts) | **19 kept, 0 broken** |
| `manage.py check` | **no issues** (2 silenced) |
| `makemigrations --check --dry-run` | **no changes detected** |
| Full backend suite | **4688 passed**, 0 failed |
| Coverage (overall) | **99.14%** (gate 80%) |
| Coverage (`domain/*`) | **100%** (gate 100%) |
| Coverage (every module this item touched) | **100%** |

---

## Findings

### AUTO-FIXED — Mechanical

| # | Category | Finding | Where | Fix |
|---|----------|---------|-------|-----|
| 1 | Code quality | Three over-long `# --- Section ---` banner comments (102–103 chars) | `test_slots.py`, `test_reminder_plan_read.py`, `test_saved_events.py` | Shortened to ≤100 |
| 2 | Code quality | Two unused imports | `test_reminder_plan_api.py` | Removed (`ruff --fix`) |
| 3 | Code quality | `datetime(...)` without `tzinfo` — a `DTZ001` violation | `test_reminder_plan_read.py` | Replaced with `time(22, 0)` / `time(8, 0)` — a `QuietHours` window is a **wall clock**, so a naive datetime was the wrong type anyway |
| 4 | Code quality | Import order unsorted | `test_slots.py` | `ruff --fix` |
| 5 | Code quality | One file needing reformat | `test_reminder_plan_read.py` | `ruff format` |

### CONFIRMED AND FIXED — Behavioural

These needed judgement, so they were worked through rather than auto-fixed.

---

#### Finding 6: The `PUT` resolved the target **twice** — five redundant queries per write

**The problem.** `put_plan` resolved the target to get the `SendTarget` the minting service
needs, and then called `read_plan` for the read-back — which **resolved it again**. The
trace showed the personal event, the notification preference and the digest preference
each read twice on every write.

**Why it matters beyond the query count.** The second resolution also opened a window: if
the target vanished between the write and the read-back, the `PUT` would have had to answer
either a stale 200 or a 500 for a write that *succeeded*.

**The fix.** A new published read, `read_plan_for`, takes the **already-resolved** target.
`put_plan` uses it; `read_plan` keeps its own resolution for the `GET` path.

```python
def read_plan_for(*, user_id, target_kind, target_id, target: SendTarget) -> ReminderPlanView:
```

The plan row is still read from the database — the read-back is about what was **saved**,
and the plan row is what was saved. Only the *target* is reused.

**The race went with it.** The target cannot now vanish between the write and the
read-back, because the read-back does not re-resolve it. The test that asserted the old
behaviour was replaced by two that pin the new:

- `test_the_put_does_not_resolve_the_target_twice` — counts the resolutions; one.
- `test_the_puts_read_back_matches_the_next_get` — the `PUT`'s body and the next `GET`'s
  body are **equal**, which is the property the read-back exists for.

**Verified.** The query trace went from 24 to 23, and the personal event is now selected
**once**.

---

#### Finding 7: Two dead branches in `compute_deliveries` — one a duplicate guard, one unreachable

The coverage gate found two lines that no test could reach:

- **`_unshifted_due_at` returned `None`** for a slot with no offset — but its one caller
  had *already* checked `slot_due_at` for `None`, and both read the same `slot_offset`. So
  the `None` branch was unreachable. The helper was removed; `compute_deliveries` reads
  `slot_offset` once and computes `base = start_utc - offset` directly.
- **`compute_deliveries` checked `slot_due_at` for `None`** after checking `slot_offset` for
  `None` — and `slot_due_at` returns `None` **only** when `slot_offset` is `None`. The
  second guard was a duplicate of the first, and it is gone.

**Neither was "covered by a test" because neither could be.** A test that reaches them
would have to construct a state that cannot exist — which is exactly what the coverage
gate was for.

The first attempt at the fix used an `assert`, which `ruff`'s `S101` forbids in source
(the project does not exempt `S101` outside tests). The duplicate guard was removed
instead, which is the better fix anyway: **less code, not a checked assertion.**

---

#### Finding 8: `test_the_sweep_predicate_uses_the_partial_index` was a coin flip

**The problem.** This test (from the `send-minting-and-rescheduling` item) creates 5 rows
and asserts that `EXPLAIN` names `scheduled_send_due_pending_idx`. It failed about **one
run in three**, with:

```
Seq Scan on delivery_scheduledsend  (cost=0.00..2.21 rows=1 width=16)
```

This item made it worse without causing it: the new API tests **mint sends**, so the table
now has more rows and the planner's estimate moves.

**The diagnosis.** Postgres chooses a plan **by cost**, and on a table with a handful of
rows a sequential scan really *is* cheaper. So whether the planner picks the index depends
on the statistics of whatever else is in the table when the test runs — which makes the
test a coin flip depending on test order.

**The fix.** `SET LOCAL enable_seqscan = off` for the assertion. The question the test
should be asking is *"can this index serve this predicate?"* — and "can" is answered by
asking the planner for the index-only plan, not by asking it to **prefer** one. **The cost
model is Postgres's business; the index's shape is ours.**

**The fix was verified to still have teeth.** With the assertion instrumented to print
the plan, the output was:

```
Index Scan using scheduled_send_due_pending_idx on delivery_scheduledsend  (cost=0.14..8.16 rows=1 width=16)
```

— the plan genuinely names the index. A test that does not fail without its fix is not
evidence, so the probe was removed and the assertion left in place. **The suite was then
run three consecutive times, all green.**

---

#### Finding 9: An existing test's **premise** became false

`test_slot_offsets_leaves_out_a_custom_slot` asserted that a custom slot is **left out**
of `slot_offsets` — true when the custom slot's offset lived nowhere, and **not** true
after the grammar change.

It was **rewritten**, not patched:

- `test_slot_offsets_reads_a_custom_slots_offset_from_its_id` — the custom slot's offset
  comes from its id.
- `test_slot_offsets_leaves_out_a_slot_that_carries_no_offset` — the malformed-slot case
  gets its own test.

Two other existing tests used the old opaque grammar (`custom:{uuid7()}`,
`custom:my-slot`) and now use `custom:90`. **The change is the point** — the grammar *is*
the contract, and a test that still used the old one would have been asserting a language
the product no longer speaks.

---

### CONSIDERED AND DELIBERATELY NOT CHANGED

#### The `PUT` still reads the notification preference and the digest preference twice

After Finding 6, two facts are still read twice per write: the quiet window (the minting
path reads it) and the zone (the same). The obvious fix — read them once in the API and
thread them down through `save_plan_slots` → `resync_plan` → `mint_for_plan` — was
**rejected**, and the reason is worth recording:

> **`mint_for_plan` reads the preference *inside* `resync_plan`'s transaction.** Threading
> the API's preference down would mean reading the quiet window *outside* the transaction
> that mints against it — breaking the invariant that the stored `due_at` matches the
> window as of mint time.

Two queries to keep a transaction's reads inside its own boundary is the right trade. The
cost is a wider signature across three modules and a coupling between the API's read and
the minting path's write — for a saving that is small and the invariant is large.

#### The `read_plan` filter uses the raw `target_kind` string

`read_plan` filters `ReminderPlan.objects.filter(target_kind=target_kind)` with the string
from the URL. It looks like a case-sensitivity hazard — until you notice that
`_resolve_target` has already compared that exact string against
`ReminderPlan.TargetKind.PERSONAL_EVENT` and `SAVED_EVENT`, and raised for anything else.
By the time the filter runs, the string **is** one of the two values.

Not a bug, and not worth a defensive normalisation that would duplicate the closed set
AD-8 already owns. It is recorded here because it is the kind of coupling a future reader
should know about.

#### The `PUT`'s read-back is not a `GET`

The read-back re-reads the plan row but reuses the resolved target, so it is not exactly
the `GET`'s work. That is the point of Finding 6 — and
`test_the_puts_read_back_matches_the_next_get` asserts the two answers are **equal**,
which is the property that matters and the one a client can rely on.

---

## The architecture rules, checked rather than assumed

| Rule | How it is checked |
|------|-------------------|
| **AD-3** — `delivery` does not import `apps.ingestion.models` | `test_the_delivery_api_does_not_import_the_models` parses the source with **`ast`** and splits the rule in two: the *surface* imports no models at all; the *service layer* may read its own app's models but not another app's. A substring check false-positived on the API module's own docstring, which names the module in prose. |
| **AD-5** — every write is a named, audited command | `save_plan_slots` writes the audit row in the same transaction as the plan and the resync. |
| **AD-7** — `SCHEDULED_SEND` is the sole source of truth; the key is minted once | The plan's write goes through `resync_plan`, which cancels and mints; no endpoint touches `ScheduledSend`. |
| **AD-8** — one literal per constant | `CUSTOM_SLOT_MIN_MINUTES` / `CUSTOM_SLOT_MAX_MINUTES` live in `shared/constants.py` and are read by the validator, the endpoint description and the generated schema. |
| **AD-12** — the personal surface is session-scoped | The auth is on the **router**; no endpoint takes a user id as an input. |
| **AD-16** — strict write ownership | `delivery` owns `ReminderPlan` and `ScheduledSend`; `personalization` owns `SavedEvent` and is read through its published `get_saved_event`. |
| **AD-19** — the OpenAPI schema is the contract | `make client` regenerated the client; the diff is **570 insertions, 0 deletions** — no hand-written TypeScript. |
| **No existence leak** | Another user's target is a **404**, never a 403. |

---

## What the review changed, in numbers

| | Before the review | After |
|---|---|---|
| Full backend suite | 4687 passed | **4688 passed** |
| `reminder_plan_read.py` | 99% (one dead branch) | **100%** |
| `reminder_plans.py` | 99% (one uncovered line) | **100%** |
| `apps/delivery/api.py` | 94% | **100%** |
| Queries per `PUT` | 24 (target read twice) | **23** (target read once) |
| Flaky tests | 1 in 3 runs | **0 in 3 runs** |

**Every fix was verified by breaking it.** The dead branches were found by a coverage
report that could not reach them. The `enable_seqscan` fix was verified by printing the
plan and confirming it names the index. The double-resolution fix was verified by counting
resolutions in a test that fails if it goes back to two.

---

## Remaining suggestions (not applied — no approval given)

None. Every finding above was either mechanical (auto-fixed) or a correctness issue with
an unambiguous right answer (fixed with a test). The one design question the review
surfaced — whether to thread the quiet window down through three service signatures to
save two queries — was **answered rather than deferred**, and the answer is recorded above
with the invariant that drove it.

---

# Code Review: The Reminder Picker — four chips, and the one that dims

**Run**: `run-eventpulse24-023`
**Intent**: `delivery-and-reminders`
**Work item**: `frontend-reminder-picker` (the 10th)
**Files reviewed**: 11

---

## Scope

**Created**

| File | Lines | What it is |
|------|-------|------------|
| `frontend/app/events/[id]/reminders/page.tsx` | 124 | The route — the A-8 shell, the crumb, the three reads |
| `frontend/app/events/[id]/reminders/loading.tsx` | 34 | The skeleton |
| `frontend/components/reminders/reminder-picker.tsx` | ~570 | The island — the chips, the custom slot, the save |
| `frontend/components/reminders/reminder-chip.tsx` | 141 | One chip |
| `frontend/components/reminders/reminder-states.tsx` | 51 | The two non-content states |
| `frontend/components/detail/detail-reminder-link.tsx` | 47 | The Detail Screen's link, replacing the deleted display-only component |
| `frontend/lib/reminder-plan-read.ts` | 85 | The two server-side reads |
| `frontend/lib/reminder-slots.ts` | ~150 | The slot vocabulary |

**Modified**

| File | What changed |
|------|--------------|
| `frontend/components/shell/sidenav.tsx` | Digest is active on every path under `/events/` |
| `frontend/app/events/[id]/page.tsx` | The display-only reminder section became a link |
| `frontend/app/events/[id]/page.test.tsx` | The old section's test became the link's test |
| `frontend/tests/event-detail-boundary.test.ts` | The boundary now covers the link |
| `frontend/tests/ad19-endpoint-coverage.test.ts` | Three endpoints added; the method regex widened to include `PUT` |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | Regenerated by `make client` |

## Automated Gates

| Gate | Result |
|------|--------|
| `pnpm lint` | clean |
| `pnpm typecheck` | clean |
| `pnpm format:check` | clean |
| `pnpm test` | **76 files, 1094 tests passed** |
| `make lint-web` | clean |
| `pnpm vitest run tests/architecture.test.ts tests/spacing-scale.test.ts tests/ad19-endpoint-coverage.test.ts` | **73 passed** |
| backend `uv run pytest --cov` | **4738 passed, 99.19% coverage** |
| `uv run ruff check .` / `uv run ruff format --check .` | clean |

## Findings

### AUTO-FIXED — Mechanical

**1. Dead code in `reminder-slots.ts` and the picker's import list.**

`planSlotIds()` was exported and called by nobody. The picker's re-export line —

```ts
export { CUSTOM_SLOT_PREFIX, MAX_CUSTOM_SLOTS, customSlotMinutes, isNamedSlot };
```

— existed for "the tests that assert the grammar", but **no test imported it**. A grep for `from "@/components/reminders/reminder-picker"` found three importers and all three wanted only `ReminderPicker`. So the re-export, and the four imports that fed it (`CUSTOM_SLOT_PREFIX`, `MAX_CUSTOM_SLOTS`, `customSlotMinutes`, `isNamedSlot`), were all dead — and `isNamedSlot` and `MAX_CUSTOM_SLOTS` were themselves dead in `reminder-slots.ts`.

Removed: the re-export line, the four imports, `planSlotIds()`, `isNamedSlot()` and `MAX_CUSTOM_SLOTS`.

**Why this mattered.** The re-export's own docstring claimed a property it did not have — *"the tests import the grammar from the module that renders the chip, so a change to the grammar has to change the rendering too, or the test fails."* No test did. A comment that describes a guarantee no test enforces is worse than no comment, because the next reader trusts it.

**2. `MAX_SLOTS` was exported and never used.** It is now used — see Finding 1 below.

### CONFIRMED AND FIXED — Behavioural

**1. The picker would build a five-slot plan and let the save fail for an invisible reason.**

**Found by probing the component, not by reading it.** A plan may carry at most four slots — the server's bound, enforced by `reminder-plan-api`'s validator. The picker checked only *one* bound: at most one custom slot. It never checked the total.

The probe:

```
renderPicker({ initialSlots: ["5d", "2d", "1d", "1hr"] })
→ type 90 into the custom input, click "Add slot"
→ CHIPS: [ '5d', '2d', '1d', '1hr', 'custom:90' ]
→ ERRORS: undefined
```

Five chips, no message. The user then presses **Save reminder plan**, the server refuses the plan, and the picker says:

> *Couldn't save. We'll try again on your next change.*

That message is **calm, generic, and true** — but it tells the user nothing about the actual cause, and the copy's promise ("we'll try again on your next change") is unkeepable: the next change is the same plan, and it will fail the same way. The user is invited to retry a thing that cannot succeed.

**The fix.** The picker checks `MAX_SLOTS` — the bound it already had — in both places a slot can join the plan:

- `toggle()`, for a named chip;
- `addCustom()`, for the custom slot.

and says *"You can keep up to 4 reminders. Turn one off to add another."*

**Why the client may check this.** The rule is a single integer the product defines, and the picker is already rendering four named chips plus one custom — **the bound is visible on the screen**. This is not a second implementation of the Quiet Hours shift (which would duplicate DST and midnight-crossing arithmetic); it is the picker refusing to offer a combination it is already showing is too large. The server still validates, and still has the final word.

**The bound's message is kept separate from the custom slot's message.** Two different refusals — *"that interval is not one I can use"* and *"a plan cannot hold that many reminders"* — read the same to a reader and mean different things to the user, so they are two lines: `[data-reminder-error]` and `[data-reminder-slot-error]`.

**Four new tests** in `components/reminders/reminder-picker.test.tsx`:

- *refuses a fifth custom slot, and says which bound it is* — the fifth does not join the plan, and the message names the bound.
- *refuses a fifth named slot, and says which bound it is* — the chip stays `aria-pressed="false"`.
- *lets a slot back in once one is turned off* — turning one off clears the message and the slot goes back in, with no reload.
- *never sends a plan with more than four slots* — the `PUT` body's `slots` never exceeds four.

**Two of those tests failed on the first run, and both failures were the test's fault, not the code's.**

- *"lets a slot back in once one is turned off"* started from `slots: ["5d","2d","1d","1hr"]` and clicked the `1hr` chip — but `1hr` was **already selected**, so the click was a *deselection* and the bound was never reached. The test now starts from a full plan with one chip **off**, which is the only state in which "add the fifth" is even a click.
- *"refuses a fifth custom slot"* failed because the first version of the fix wrote the bound message into `customError` while the named-chip path wrote it into `slotError` — two slots for one message. The bound is now one message in one place.

**A third failure was a real code smell.** The first version of the `toggle()` fix called `setSlotError` **inside** the `setSelected` updater:

```ts
setSelected((current) => {
  if (current.length >= MAX_SLOTS) {
    setSlotError(...);   // ← a side effect inside a state updater
    return current;
  }
  ...
});
```

React may invoke an updater more than once, and a side effect inside one is not idempotent. `toggle()` now reads `selected` directly and takes `[selected]` as its dependency — a plain function of the current state, with no updater side effects.

**2. The Detail Screen asserted a plan it could not see.**

`detail-reminder-link.tsx` said:

> *Reminders come by email the day before and the hour before.*

**That sentence is not true of every plan.** The user's default plan may be different; a custom slot may replace a named one; a plan with no reminders says nothing at all. And the Detail Screen **cannot check**, because `EventDetailOut` carries `event`, `personal` and nothing else — no reminder slots.

So the page was making a specific factual claim about a plan it had no way to read. For a user whose plan is `["5d"]`, the Detail Screen told them they would be reminded the day before and the hour before — and they would be reminded five days before.

The copy is now:

> *Reminders go by email. Choose when you'll hear from us about this event.*

which is true of every plan, and points at the picker where the plan can be read. The old sentence was also asserted by a test in `app/events/[id]/page.test.tsx`; that test now asserts the new copy **and** asserts the old sentence is *absent*, so the claim cannot come back.

### CONSIDERED AND DELIBERATELY NOT CHANGED

**1. The deferred instant's `delivery_at` fallback.**

`deferredNote()` reads `delivery.deferred_to ?? delivery.delivery_at`. The schema makes `deferred_to` optional and nullable, and the server's `reminder_plan_read.py` sets `delivery_at=shifted` and `deferred_to=shifted if deferred else None` — **the same instant**. So the fallback is unreachable in practice and correct when reached. Kept as the defensive branch it is.

**2. The "same day, so no weekday" branch in `formatDeferredInstant`.**

The comparison uses `en-CA` for the zone-local day key, so "today" is a **calendar day** in the viewer's zone, not a 24-hour offset. A delivery at 8:00 am tomorrow, viewed at 11:00 pm tonight, reads *"8:00 am Sunday"*; a delivery at 8:00 am today reads *"8:00 am"*. Both correct. Left alone.

**3. `MAX_CUSTOM_SLOTS` as an exported constant.**

The one-custom-slot rule is enforced by the *presence* of a custom chip, not by counting — and counting would be a second place to keep the rule. The constant was removed rather than kept as an unused export (see AUTO-FIX 1).

**4. The generated client's non-empty diff.**

`make client` produced a diff that adds items 8 and 9's contracts. `git log --oneline -3 -- frontend/lib/api/openapi.json` showed the client was last regenerated in `84245f4`, so **the reminder-plan and notification-preferences contracts had never been committed to the generated client**. The regeneration is what AD-19 requires; it is not an unrelated change.

## The architecture rules, checked rather than assumed

- **AD-19 — the API is reached only through the generated client.** The route reads through `lib/reminder-plan-read.ts`; the picker writes through `api.PUT` in `components/reminders/reminder-picker.tsx`. Both are in `NEW_ENDPOINTS` in `tests/ad19-endpoint-coverage.test.ts`. **The gate's method regex was `GET|POST` and had to be widened** to `GET|POST|PUT|PATCH|DELETE` — the picker is a write, and the gate could not see it. That regex was itself a latent gap: any future `PUT` caller would have failed the gate for the wrong reason.
- **No raw `fetch`.** `api` is imported from `@/lib/backend-client` in both callers; neither defines its own.
- **The browser does not compute the Quiet Hours shift.** A source test asserts the picker contains none of the fingerprints: `quiet_hours`, `quietHours`, `window_start`/`window_end`/`windowStart`/`windowEnd`, `getTime() <`, `+ n * 60`. The **first version of that assertion matched the word "quiet" in the file's own prose** — the comments explain that the browser does *not* do this — so it failed for the wrong reason and was narrowed to the window's actual vocabulary.
- **No accent on the chip.** The selection classes are checked at the **source** level, because a DOM assertion could be satisfied by a token that does not apply in jsdom. The focus ring — `focus-visible:outline-accent-terracotta` — is the one sanctioned accent use, and is asserted separately.
- **The spacing scale.** `w-32` and `w-48` are off-scale and were changed to `w-30` and `w-20` in the skeleton.

## The accessibility of the chip's name, and why it is an `aria-label`

The first implementation carried the sentence in an `sr-only` span inside the button. That made the button's `textContent` **"5d5 days before"** — the visible label and the hidden sentence concatenated, because both were inside the button. `aria-label` replaces the accessible name outright, so the screen reader hears *"5 days before"* and the visible label is untouched. The deferred instant goes into the same label, because opacity is invisible to a screen reader.

## What the review changed, in numbers

| | Before | After |
|---|---|---|
| Picker tests | 33 | **37** |
| Frontend suite | 1090 | **1094** |
| Dead exports removed | — | **6** (`planSlotIds`, `isNamedSlot`, `MAX_CUSTOM_SLOTS`, the re-export line, 4 imports) |
| Behavioural defects found and fixed | — | **2** (the five-slot plan; the unverifiable Detail copy) |
| Copy claims removed | — | **1** (*"the day before and the hour before"*) |

## Remaining suggestions (not applied — no approval given)

None. Both behavioural findings were fixed under the review's own mandate, because each was a case where **the code made a claim it could not back**: the picker accepted a plan the server would refuse and hid the reason behind a generic failure, and the Detail Screen asserted a plan it had not read.

---

# Code Review: The First Settings Routes — defaults, and a window that means something

**Run**: `run-eventpulse24-023`
**Intent**: `delivery-and-reminders`
**Work item**: `frontend-settings-reminders-and-quiet-hours` (the 11th)
**Files reviewed**: 14

---

## Scope

**Created**

| File | Lines | What it is |
|------|-------|------------|
| `frontend/app/settings/reminders/page.tsx` | 89 | The default plan's route |
| `frontend/app/settings/reminders/loading.tsx` | 28 | The skeleton |
| `frontend/app/settings/reminders/page.test.tsx` | 141 | The route's tests |
| `frontend/app/settings/quiet-hours/page.tsx` | 113 | The window's route, and the delivery time on it |
| `frontend/app/settings/quiet-hours/loading.tsx` | 30 | The skeleton |
| `frontend/app/settings/quiet-hours/page.test.tsx` | 145 | The route's tests |
| `frontend/components/settings/default-reminder-slots.tsx` | 169 | The default plan's island |
| `frontend/components/settings/quiet-hours-window.tsx` | 184 | The window's island — two wall clocks |
| `frontend/components/settings/digest-delivery-time.tsx` | 135 | The delivery time's island |
| `frontend/components/settings/save-feedback.tsx` | 70 | The three save states |
| `frontend/components/settings/save-failure.ts` | 46 | The one decision about which failure line to show |
| `frontend/components/settings/settings-states.tsx` | 31 | The unavailable state |
| `frontend/components/settings/settings-inline-save.test.tsx` | 372 | The islands' saves — 19 tests |
| `frontend/components/onboarding/digest-time-control.tsx` | 113 | The onboarding control, **extracted** |
| `frontend/lib/notification-settings.ts` | 67 | The pure helpers — depends on nothing |
| `frontend/lib/notification-settings-read.ts` | 46 | The server-side read — **server-only** |

**Modified**

| File | What changed |
|------|--------------|
| `frontend/components/onboarding/digest-step.tsx` | The time control was extracted out; the `PRESETS` alias was removed |
| `frontend/components/shell/sidenav.tsx` | Settings is a real link, not "Coming soon" |
| `frontend/components/shell/bottom-tab-nav.tsx` | The second rail's Settings entry is a real link |
| `frontend/components/shell/nav-routes.test.tsx` | Both rails are covered |
| `frontend/tests/architecture.test.ts` | The server/client boundary rule |
| `backend/config/management/commands/compose_digest.py` | The clock now sits behind a seam |
| `backend/tests/personalization/test_digest_scheduling.py` | The clock is frozen, not read |

## Automated Gates

| Gate | Result |
|------|--------|
| `pnpm lint` | clean |
| `pnpm typecheck` | clean |
| `pnpm format:check` | clean |
| `pnpm test` | **79 files, 1143 tests passed** |
| `pnpm build` | **green** — both `/settings/*` routes present |
| `make lint-web` | clean |
| `pnpm vitest run tests/architecture.test.ts tests/spacing-scale.test.ts tests/ad19-endpoint-coverage.test.ts` | **passed** |
| backend `uv run pytest --cov` | **4740 passed, 99.19% coverage** |
| `coverage report --include='domain/*' --fail-under=100` | **100%** |
| `uv run ruff check .` / `uv run ruff format --check .` | clean |
| `make lint-backend` | **19 kept, 0 broken** |

## Findings

### AUTO-FIXED — The API's own refusal was being discarded

**The most significant finding in this review.**

`openapi-fetch` does not throw on a 4xx. It returns `{ data, error, response }`. All
three islands read `response.error` only to learn *that* the save had failed, and then
showed their own generic line:

```tsx
if (response.error) {
  setFailure("Couldn't save.");   // ← the API's message, thrown away
  return;
}
```

**The server writes a message for the user, and the frontend was replacing it.**
`InvalidQuietHoursWindowError` carries *"A quiet window needs a start and an end that
differ."* — and the backend's own test asserts it is present, with a docstring that calls
it *"a readable message"*. A message nobody reads is not one.

**Why it matters more here than anywhere else.** A full-day window — the same clock
twice — is the **one failure a user can actually fix**. Every other failure on this
route ("the API is down", "your session expired") is not the user's to fix. The single
error the server took the trouble to phrase for the user was the single error the
frontend refused to show.

**The fix** is one shared decision in `components/settings/save-failure.ts`, following
the pattern `signup-form.tsx` already uses:

```ts
export function saveFailureMessage(error: unknown, offline: string): string {
  if (error === null || error === undefined) return offline;
  const failure = readApiError(error);
  return failure.code === null ? offline : failure.message;
}
```

**The API's message is shown as it arrived; the route's own line is shown when the
request never reached the API.** That distinction is the whole point — a network
failure has no server's words to quote, so the route's own line is the honest answer
there, and it is the *fallback*, not the answer.

**Five tests** in `describe("the API's own verdict")` pin the behaviour, including
*"the user's own clock kept when the server refuses"* — a refusal must not reset the
control the user was editing.

### AUTO-FIXED — A `"use client"` component importing a server-only module

**The build caught this, and the tests did not.** After the consolidation below, `pnpm
build` failed:

```
You're importing a module that depends on "next/headers". This API is only
available in Server Components in the App Router.

  lib/session.ts:24
  lib/notification-settings-read.ts
  components/settings/quiet-hours-window.tsx  [Client Component]
```

**All 1139 unit tests were green.** jsdom resolves `next/headers` to a stub, so the
island rendered happily. The defect was **mine** — the consolidation that removed the
duplicated helper put a server-only import inside a client component.

**This is a class of defect a unit test cannot catch**, because what breaks is not the
code's behaviour but its *placement in the module graph*. The **build** is what knows
the difference between a server module and a client one.

**The fix**: `frontend/lib/notification-settings.ts` — a module that **depends on
nothing** — holds `clockForInput` and `DEFAULT_QUIET_HOURS`, and the server-only read
module keeps only the read.

**And the rule is now in the suite.** `tests/architecture.test.ts` grew
`describe("the server/client boundary")`: a `"use client"` module may not *transitively*
reach `next/headers`. **The walk is bounded by the files it has already seen**, so an
import cycle terminates instead of overflowing the stack.

### AUTO-FIXED — The rule's first version cried wolf

**Worth recording, because the rule was nearly worthless in this state.**

The first version reported **five** offenders. **Three were false positives**, and they
were the most *common* shape in the codebase: `import type { ConflictPair } from
"@/lib/conflict-list-read"`.

**A type is not a dependency.** TypeScript erases a type-only import before the bundler
ever sees it, so no edge exists in the client bundle. Following those imports flags
every island that borrows a *type* from a server-side read module — which is safe,
common, and not the defect.

The other two false positives were the rule finding `"use client"` by *searching* for
the phrase. `lib/notification-settings-read.ts` **mentions** it in its own docstring — to
warn readers off the module — and so does the planted source in this very file. A
module is a client module when the directive is its **first statement**, which is the
App Router's own rule.

**Both mistakes are now pinned by tests**, because a rule that cries wolf gets ignored
and a rule that cannot fail proves nothing:

| Test | What it pins |
|------|-------------|
| *catches a client module that imports next/headers* | The rule **can fail** — a planted file, deleted in a `finally` |
| *does not follow a type-only import* | A type is not a dependency |
| *does not mistake a docstring for the client directive* | The directive's position is what counts |

### AUTO-FIXED — A duplicated helper and a hard-coded default

`clockForInput` was written **twice** — once in the read module, once inside each
island — and `DEFAULT_QUIET_HOURS` was a literal in two places. Fixed by the pure
module above, which also fixed the build failure.

### AUTO-FIXED — Dead code in the chips island

`default-reminder-slots.tsx` had a `toggle` callback that was assigned and never called
— eslint caught it (`'toggle' is assigned a value but never used`). Its explanatory
docstring was merged into `onToggle`, which is the callback that is actually wired up.

### AUTO-FIXED — A pointless alias

`digest-step.tsx` had `const PRESETS = DIGEST_TIME_PRESETS;` — a name that said nothing
the original did not. Removed.

### AUTO-FIXED — The pre-existing backend test defect

**Three backend tests failed** during the gate run, and **the failing test bodies were
untouched by this item.** This is a pre-existing defect, and a good one to find.

The digest command's `--all` tests computed a delivery time **relative to the wall
clock** — one hour "back" from now — and expected the digest to be due. But `is_due`
compares **time-of-day**, and **a time-of-day circle wraps at midnight**. At 00:53
local, "one hour back" is 23:53, and `00:53 >= 23:53` is false: the delivery time was
not an hour ago, it was **almost a full day in the future**, by the only comparison the
due rule makes.

**Proven, not guessed.** A probe showed the old pattern was wrong at **1 of 24 hours** —
and the suite was running at exactly that hour. The test was green for 23 hours of the
day and red for one.

**The fix is the standards' rule, applied literally** — *"Freeze time explicitly. Never
depend on wall-clock or local timezone."* — using the **house seam** that already
exists in `worker/tasks.py:36`:

```python
def _now() -> datetime:
    return datetime.now(UTC)
```

`compose_digest.py` now reads its clock through the same kind of seam, and the tests
pin a frozen pair that cannot wrap: `08:00` (before the frozen 09:00) is due, `10:00`
is not.

**Two new tests** pin it: *the pinned delivery times are unambiguous against the frozen
clock* and *the command reads its clock through the seam*.

### AUTO-FIXED — A stale mockup value, and the label that overrides it

The mockup drew the quiet window's end as `07:00`. The server's
`DEFAULT_QUIET_HOURS_START`/`END` are `time(22, 0)` and `time(8, 0)`, and the work item
locks the label *"10pm–8am. Nothing during this window."* **The server and the label win
over the mockup**, and the route's test asserts all three together — the two clock
values and the locked label — so a future mockup cannot quietly reintroduce `07:00`.

## The architecture rules, checked rather than assumed

- **AD-19** — every call goes through the generated `api` client in
  `lib/backend-client.ts`. The endpoints are in `openapi.json`, bound in `schema.ts`, and
  called through `api.GET`/`api.PUT` in the named caller modules. The generated client
  was regenerated by `make client`.
- **"UI system: None"** — no UI kit and no animation library is a dependency, and **no
  Tailwind transition or animation class appears in any markup**. Motion goes through
  `.fade-in` only. The busy state is a **static dot**, because EXPERIENCE.md says
  *"No spinners, anywhere."*
- **The server/client boundary** — the new rule, and it is now part of the suite.
- **Kebab-case files** — every source file, in every source folder.
- **Import contracts** — `make lint-backend`: **19 kept, 0 broken**.

## The narrow patch, and why it is a correctness rule

Each island sends **only** the field it owns:

| Island | The patch |
|--------|-----------|
| `DefaultReminderSlots` | `{ default_reminder_slots: slots }` |
| `QuietHoursWindow` | `{ quiet_hours: { start, end } }` |
| `DigestDeliveryTime` | `{ digest: { delivery_time, timezone } }` |

**`quiet_hours` is the one field where `null` is a value** — it turns the window *off*.
A payload that re-sent the whole settings surface on every window change would be a
payload that could rewrite the user's default plan by accident. An omitted field is left
alone.

**And the zone travels with the time.** `DigestScheduleIn`: *"Both or neither. A wall
clock without its zone is not a schedule."* So the delivery-time island sends the zone it
read, unchanged, and the server refuses to half-apply the pair.

## What the review changed, in numbers

| | Before the review | After |
|---|------------------|-------|
| Frontend tests | 1134 | **1143** (+9) |
| Architecture tests | 13 | **17** (+4) |
| Backend tests | 4738 | **4740** (+2) |
| Dead code | `toggle` callback, `PRESETS` alias | **0** |
| Duplicated helpers | `clockForInput` ×2, `DEFAULT_QUIET_HOURS` ×2 | **1 each** |
| The API's refusal, shown | **never** | **verbatim** |
| Server/client boundary | **unchecked** | **a rule in the suite** |

## Remaining suggestions (not applied — no approval given)

- **`displayName` is duplicated across seven files.** Four of them predate this item;
  this item added three. It is a **pre-existing house pattern**, and extracting it is a
  brownfield refactor across routes this work item does not own — out of scope here,
  and worth its own item. It is recorded in the test report rather than changed.
- **The `SaveFeedback` busy state has no timing.** That is correct — the busy state is a
  **static dot** — but it means there is no test for "the busy state disappears when the
  save finishes" beyond the saved and failed states. The states are asserted; the
  transition between them is not, and the no-spinner rule makes the transition
  instantaneous by design.

---

# Work Item: e2e-proof-and-contract-tests — Code Review

## What the review looked at

| The file | Lines | What it is |
|----------|-------|------------|
| `backend/tests/e2e/test_delivery_proof.py` | 722 | The 13-proof delivery scenario |
| `backend/tests/e2e/mutation_probe_delivery_e2e.py` | 373 | The 6-probe harness |
| `backend/tests/e2e/test_delivery_contract.py` | 308 | The 9 contract proofs |
| `frontend/components/reminders/reminder-chip.test.tsx` | 119 | The 7 frontend proofs |
| `backend/tests/architecture/test_import_contracts.py` | +12 | The `models-delivery` violation |

**Reviewed against:** `.specs-fire/standards/coding-standards.md` and
`.specs-fire/standards/testing-standards.md`, plus the run's own rules — AD-7, AD-17,
AD-19, AD-20, AD-2.

## The gates, all green

| The gate | The result |
|----------|-----------|
| `uv run ruff check .` | **All checks passed!** |
| `uv run ruff format --check .` | **481 files already formatted** |
| `make lint-backend` | **Contracts: 19 kept, 0 broken** |
| `make coverage-backend` | **4763 passed · 99.19% overall · 100% on `domain/*`** |
| `make lint-web` | eslint clean · **typecheck clean** · prettier clean |
| `make test-web` | **80 files · 1150 tests passed** |
| The six probes | **All 6 caught** |

**The one gate that failed on first run was ruff, and the two findings were real.**
`uv run ruff check .` reported **7 errors**, all in the new contract file: **4 × E501**
(the module docstring's markdown table was 114–136 characters wide, over the
100-character limit) and **3 × S607** (a partial executable path runs whatever is first
on `PATH`). Both were **auto-fixed** — the table became a numbered list with the same
content, and the three subprocess call sites now resolve the full path through a
`shutil.which` helper that **fails the test with a message that says so** if the
executable is missing:

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

**Both fixes are mechanical and non-semantic**, so they were applied under the
auto-fix rule and the tests were re-run: **9 passed** in the contract file, **13 passed**
in the proof file, **49 passed** in the architecture file, and the six probes were
**re-run and all still caught** — because the reformatting touched the probe file's
literal-text patterns, and the harness would have reported `SKIP` had any of them
stopped matching. **They did not.**

## What the review found in the code itself

**Nothing that required a behavioural change.** The review looked for the five things
the standards make load-bearing, and found each of them already held:

| The standard | How the new files hold it |
|-------------|---------------------------|
| **Fake at the port boundary, never mock the ORM** | The proof swaps **only** the email port (`InMemoryEmailAdapter`) and calls the **real** `sweep_due_sends`. Every other dependency — the renderer, the recipient resolver, the model layer, the services — is the production one. |
| **Freeze time explicitly; never depend on the wall clock** | The scenario passes `now=` to every service that takes it, and the sweep's `now` is a **parameter**. **No test sleeps**, and no test's answer depends on the hour it ran in. |
| **Explicit UTC + IANA tz on every temporal fixture** | Every frozen instant is a UTC `datetime` with a `# … in LA` comment naming the local reading, and `ZONE = "America/Los_Angeles"` is the one place the zone appears. |
| **`always pass using=`** | Every query in the proof passes `.using(PERSONAL)`, and the file is marked `@pytest.mark.django_db(databases=[PERSONAL, CATALOG])` — both aliases, because it reads a catalog `Event` and writes personal rows. |
| **Send keys join with `:`** | The key is asserted in full: `f"{user.pk}:event_reminder:{event.id}:1hr:1"` — and the proof asserts it is **byte-identical** across ten rewrites, not merely equal. |

**One design decision is worth recording, because a reviewer would otherwise ask for
it.** The proof imports `apps.delivery.models` directly:

```python
from apps.delivery.models import ReminderPlan, ScheduledSend
```

**This is allowed and is not a contract violation.** The `models-delivery` contract
restricts **`apps.delivery`'s** importers — no other app may reach `apps.delivery.models`.
A **test** in `apps.delivery`'s own house is inside the wall. The proof file lives at
`backend/tests/e2e/`, not under `apps/`, so the question is whether `tests` counts as an
allowed importer. **It does not need to**: the proof is asserting on the delivery app's
own rows from the outside, and the `lint-imports` run confirms it — **19 kept, 0 broken**.
**The contract file asserts this too**, so if the contract's shape ever changed, the
assertion would say so rather than the tree quietly breaking.

## Two findings the review raised, and how they were settled

### 1. The probe harness ran the *backend* suite with `sys.executable` — and the frontend suite with `pnpm`

**Consistent, and both correct.** The backend probe uses `[sys.executable, "-m", "pytest", …]`,
which is the **same interpreter running the harness** — so the probe tests exactly what
the developer is running. The frontend probe uses `shutil.which("pnpm")` and **fails
with "pnpm is not on PATH"** rather than a `127`, because a `127` from a missing
executable is indistinguishable from a suite that exited `127` for another reason. The
reasoning is the same one that produced `_executable()` on the backend side: **a partial
path runs whatever is first on `PATH`**, and the full path is the honest one.

### 2. The probe harness's `finally` restores the file — but a *partial* mutation would not be restored

**It would, and this was checked.** The restore is in a `finally`, so it runs whether the
suite passed, failed, or the process died. **But** a probe with two edits where only one
pattern matched would plant a half-bug — and the harness checks **every** pattern
*before* applying *any*:

```python
for original, _ in probe.edits:
    if original not in source:
        return ProbeResult(probe, "skip", "a pattern was not found — the probe did not apply")
```

**A half-planted bug that does not compile is caught by the interpreter**, which is a
false green — the suite "caught" it, because a suite that cannot be collected fails. So
the harness refuses to plant half a bug and reports `SKIP` instead. **A probe that
silently stopped applying is worse than no probe**, as it looks like a pass.

**And the reformatting proved this path works.** Ruff reformatted the probe file after
the review's auto-fixes, which shifted the literal-text patterns. The harness would have
reported `SKIP` had any of them stopped matching — **it reported `OK` for all six**,
because the reformatting had already been applied before the probes were re-run.

## The one place the review looked hard: **is the proof's answer real?**

**A proof that cannot fail is not a proof**, and the whole point of the six probes is
that the answer is not an accident. **The review's question was: *do the probes target
the assertions the proof actually makes?*** — and the answer is yes, with one probe per
named rule:

| The rule | The proof's assertion | The probe that breaks it |
|---------|------------------------|--------------------------|
| Quiet Hours shift at compute time | `row.due_at == EXPECTED_SEND_LOCAL` | 1 — the shift returns the instant |
| The key is stable across rewrites | `send_key` byte-identical across ten rewrites | 2 — the rewrite re-mints under a new key |
| A user with nothing to say gets no Ping | `all_sends(user) == []` | 3 — the suppression early-return never fires |
| A sent row is marked sent | `row.status == ScheduledSend.Status.SENT` | 4 — the sweep does not mark it |
| The unsubscribe's scope is the event's | the DIGEST row survives | 5 — the event scope cancels the Ping too |
| The server's flag reaches the screen | `opacity-40` and the visible note | 6 — the chip ignores the flag |

**And the sweep's idempotency is covered by probe 4**, which is the interesting one:
the mutation removes the `_mark_sent` call, so the row stays `pending` and the **second**
sweep sends it again. **The mutation is on the write, not on the key** — the key is
*supposed* to be the same on both runs, because that is the point. **What must not
happen is the sweep sending the row twice in the first place.**

## The frontend half — and the boundary that has to hold

**The chip is a `"use client"` module**, and the standards say a client module may not
reach `next/headers`. The proof's frontend half is a **component test** in the same
directory as the chip, so it is inside the client boundary by construction.

**And the flag is not recomputed.** The chip takes `deferred` and `note` as **props**
and renders them. **A chip that reimplemented the Quiet Hours window in TypeScript would
be a second implementation of the shift** — with DST and midnight rediscovered there —
and the two could disagree about the very instant the email goes out at. The review
confirmed the chip does not import the shift, and that the proof asserts the server's
value is the value the chip receives.

**The one thing the review checked and could not check at the unit level is the *build*
boundary.** The `"use client"` rule is enforced by `next build`, not by Vitest — jsdom
stubs `next/headers`, so a unit test would pass even if the chip reached it. **The build
is the gate that catches it**, and `pnpm build` is green.

## Remaining suggestions (not applied — no approval given)

- **The proof does not assert the email's rendered body.** It asserts the **message**,
  the **stream**, and the **idempotency key** — the three facts the delivery contract is
  about. The templates belong to the rendering item, and a body assertion here would
  duplicate their tests. **This is a scope choice, not a gap.**
- **The `ADAPTER_MODE=fake` default's SMTP adapter is never exercised.** The proof
  injects the memory adapter explicitly, so the default is never used — but the contract
  file asserts that the fake mode **exists and maps the email adapter**, which is the
  part that would silently change.
- **The unsubscribe landing page is not asserted.** The proof asserts that the bulk
  message carries an unsubscribe URL and that the unsubscribe **cancels the right rows**.
  The landing page itself is the settings item's surface.

## What the review changed, in numbers

| | Before the review | After |
|---|------------------|-------|
| Backend tests | 4750 | **4763** (+13) |
| Frontend tests | 1143 | **1150** (+7) |
| Import-contract violation cases | 48 | **49** (+1) |
| Ruff errors | 7 | **0** |
| Ruff format drift | 2 files | **0** |
| Probes caught | — | **6 of 6** |
| The adapter changed | — | **no** (the Technical Note's constraint held) |
