---
run: run-eventpulse24-023
work_item: reminder-plan-api
intent: delivery-and-reminders
mode: confirm
checkpoint: plan
approved_at:
---

# Implementation Plan: The Reminder Plan API — filling an empty router

## Approach

**The gap this item closes.** `apps/delivery/api.py` is three lines — `router = Router()` and
nothing else — and it is not mounted in `config/api.py`. The service layer beneath it has been
complete since run 019: `ReminderPlan` exists with its 0–4 bound, `set_plan_slots` exists and
is audited, `resync_plan` exists and cancels-and-mints inside the plan's transaction,
`shift_to_sendable` exists and is pure. **A user can save a plan and nothing will read it, and
nothing turns a plan into a send.** This item is the surface that makes both true.

**The shape of the work.** Two endpoints on one router, and the router is mounted under
`/api/reminders` with `auth=current_user` — the same seam `personalization` uses, so the user id
comes from the session and never from a payload (AD-12's personal-data rule).

- `GET /api/reminders/{target_kind}/{target_id}` — the plan, the target kind, and **for each slot
  the computed delivery time**: the post-Quiet-Hours instant, whether it was deferred, and the
  window end it was deferred to.
- `PUT /api/reminders/{target_kind}/{target_id}` — replace the plan's slots, 0–4 of them, with the
  pending sends minted, rewritten or cancelled **in the same transaction** as the plan.

**The work item's Technical Note is the spine of the design.** *"Returning the computed delivery
time per slot is what keeps the Quiet Hours rule in one place. The alternative — shipping the
window to the browser and computing there — would put a second implementation of the shift in
TypeScript, where DST and midnight-crossing would be rediscovered and got wrong differently. The
server already knows; let it say."*

So the API **computes the shift server-side** and returns the result. It never returns the quiet
window's times for the client to apply. The client's job is to *render* a dimmed chip and a
tooltip, which is what the UX spec's worked examples describe:

> Event Friday 11:30 pm, slot 1hr → would deliver at 10:30 pm Friday (inside Quiet Hours). Chip
> dims to 40%, tooltip reads "Will deliver at 8:00 am Saturday."

The tooltip's text is the **window end**, and that is exactly the instant the shift returns when it
defers — so the server returns it and the client renders it.

### Five decisions I am making explicit

**D1 — The custom slot's offset rides in the slot id: `custom:<minutes>`.**

The UX spec pins the bounds precisely: *"Custom slot: Long-press a chip → opens a time picker
(relative to the event start). **Min: 15 minutes before; max: 30 days before.** Out-of-range
snaps back."*

There is nowhere to put that offset today. `ReminderPlan.slots` is a JSON array of strings, and
`shared.constants.CUSTOM_SLOT_PREFIX = "custom:"` marks a slot as custom — but `validate_slots`
only checks the **prefix**, so the suffix carries no meaning and `_slot_due_at` returns `None`
for any custom slot (it has no offset to look up). A custom slot today is a slot with no due
time: it is stored, it is listed, and it is **never minted**.

The choice is between a new column and an encoded id:

| | new column | encoded id (`custom:90`) |
|---|---|---|
| storage | `ReminderPlan.custom_slot_offsets` (JSON) | the slot id itself |
| migration | yes | no |
| AD-7's key | the key names the slot **id** — unchanged either way | the key names the slot id — unchanged |
| the id's meaning | opaque | **self-describing** |
| a slot's offset travels with it | in two places, which can disagree | in one place, always |

The encoded id wins, and not only because it avoids a migration. AD-7 says the send key names
"the custom slot's id" — so the id is already a first-class part of the key, and a slot whose id
*is* its offset cannot disagree with itself. A second column would be a second place for the same
fact, and the failure mode is a reminder that fires at the wrong hour.

So `custom:<minutes-before-the-event>` where `<minutes>` is an integer in
`[CUSTOM_SLOT_MIN_MINUTES, CUSTOM_SLOT_MAX_MINUTES]` = `[15, 43200]` (30 days). The bound is
**stated in the endpoint's description**, as the acceptance criteria require, and it is enforced
in `shared/constants.py` — one place, read by the validator.

This changes the slot-id grammar from `custom:<uuid>` to `custom:<minutes>`. `apps/delivery/
send_keys.py`'s `SEND_KEY_MAX_LENGTH` comment already anticipates a `custom:<uuid>` suffix at 43
characters; the new suffix is at most 11 characters (`custom:43200`), so the key gets *shorter*
and the 255-column headroom grows. The comment's arithmetic is updated to match.

**D2 — A new published read module, `apps/delivery/services/reminder_plan_read.py`.**

The per-slot delivery time needs three facts: the event's start instant, the user's zone, and the
user's quiet window. All three are `delivery`'s to read, and the shift is `delivery`'s arithmetic
(`shift_to_sendable`). But `_slot_due_at` — the function that already combines them — is
**private** to `scheduled_sends.py`, and `apps/delivery/api.py` may not import a private name
without making it public.

So the read is a new module, and `scheduled_sends._slot_due_at` is **promoted to a published
function** rather than duplicated. The rule stays in one place; the new module is the surface the
API reads.

The read returns, per slot:

| field | what it is |
|---|---|
| `slot` | the slot id, exactly as stored |
| `delivery_at` | the **post-Quiet-Hours** instant — the true send time |
| `deferred` | whether the shift moved it |
| `deferred_to` | the window end it was deferred to, or `None` |

**`deferred_to` is `delivery_at` when deferred, and `None` otherwise** — and this is not a
convenience, it is what `shift_to_sendable` already guarantees. The shift returns *the window's
end* when it defers, and the window's end is the instant the send goes out. So there is one
instant, not two, and no second computation of "which day does this window end on" (which
`shift_to_sendable` owns and would have to be duplicated to compute separately).

**D3 — A published read for a saved event, by catalog event id.**

The plan's `target_id` for a `SAVED_EVENT` is the **catalog event id**, not the `SavedEvent`
row's own id. That is the tree's existing convention and I verified it in two places:
`delivery_messages._public_event_facts` reads `target_id` through `get_public_event`, and
`apps/delivery/send_keys.event_reminder_key` puts `target.catalog_event_id` in the key.

But the API needs the *snapshot's* start time and version — the `SavedEvent` row's
`start_utc` and `event_version`, which is what the send key is minted from — and
`personalization.services.saved_events` has **no published read for one save**. It has
`list_saved_events` (a list, filtered by time bounds) and `unsave_event` (which finds by
`event_id` internally).

So `personalization` gains `get_saved_event(*, user_id, event_id) -> SavedEventSnapshot`,
raising `SavedEventNotFoundError` when the save is not the caller's. That is AD-3's shape:
`delivery` reads the snapshot through `personalization`'s published service and never touches
`apps.personalization.models`.

**And it is what makes "a saved event the user has since un-saved" a 404.** The AC asks for the
shared error shape when the target does not exist *or* the user has un-saved it — and those are
the same fact, because the plan's target for a saved event is the save. Without a published read
there is no way to tell "never saved" from "un-saved", and the API would have to guess.

**D4 — A saved event has no plan, so `PUT` attaches one.**

`personal_events.create_personal_event` calls `attach_default_plan` (FR-20: a new personal event
inherits 1d + 1hr). **`save_event` does not.** So a saved public event has no `ReminderPlan` row
at all, and `set_plan_slots` — which raises `ReminderPlanNotFoundError` when the row is missing —
would 404 for every saved event. The picker would be dead on arrival for the surface the UX mockup
(`/events/:id/reminders`) actually shows.

So `PUT` **attaches the plan when it is missing** and **replaces its slots when it is there**.
The attach and the slot-set are the same command path: `attach_default_plan` writes the default
slots, and then `set_plan_slots` replaces them — but that is two transactions, and the AC wants
one.

Better: the API calls a **new single command** in `reminder_plans` that does both inside one
`transaction.atomic(using=PERSONAL)`:

```python
def save_plan_slots(*, user_id, target_kind, target_id, slots, actor, now, send_target) -> PlanSlots
```

which is `set_plan_slots` with the "plan missing → create it" branch folded in. `set_plan_slots`
itself stays exactly as it is (other callers depend on its 404). The new command is the API's
entry point, and it is the one that guarantees *"the plan and its sends move together or not at
all"*.

**D5 — The plan's target id is validated against the target's kind before anything is written.**

A caller can name `(target_kind="saved_event", target_id=<a personal event's id>)`. The plan row
is unique on `(user_id, target_kind, target_id)`, so that would be a well-formed row about a
nonsense target, and its sends would be minted with the wrong kind's key.

So the API resolves the target **first** — through the published reads — and a target that is
missing, un-saved, or of the other kind is a **404** with the shared `{code, message}` shape. The
resolution is what produces the `SendTarget` (start instant, version, catalog event id) that the
minting service needs anyway, so the validation is free.

### The three layers, and where each fact comes from

| fact | source | why there |
|---|---|---|
| the user's id | `request.user.pk` (the session) | AD-12: the personal surface is session-scoped; no endpoint takes a user id as input |
| the target's start + version | `personalization.services.personal_events.get_personal_event` / the new `saved_events.get_saved_event` | AD-3: `delivery` reads the other side's models through its published service |
| the user's zone | `personalization.services.digest_preferences.get_delivery_settings` (falling back to `DEFAULT_DIGEST_TIMEZONE`) | the same read `_zone_for` already uses |
| the user's quiet window | `delivery.services.notification_preferences.get_preference` | the window is `delivery`'s own row, on the hot path (the decision recorded on 2026-10-31) |
| the shift | `domain.quiet_hours.shift_to_sendable` | one implementation, pure, no Django |
| the plan and its sends | `delivery.services.reminder_plans` + `delivery.services.scheduled_sends` | AD-16: `delivery` owns both tables; AD-7: `scheduled_sends` is the only writer of `SCHEDULED_SEND` |

### The one transaction, and how the rollback is proved

`set_plan_slots` already wraps the plan write, the `resync_plan` and the audit in one
`transaction.atomic(using=PERSONAL)`. The new `save_plan_slots` inherits that. So the AC — *"A
plan change that fails to reschedule rolls back the plan too — tested by forcing the second half to
fail"* — is proved the way the tree already proves it: monkeypatch `resync_plan` to raise, and
assert the plan's slots are **unchanged**.

### The route shape

```
GET  /api/reminders/{target_kind}/{target_id}
PUT  /api/reminders/{target_kind}/{target_id}
```

`target_kind` is `personal_event` or `saved_event` — the two values of
`ReminderPlan.TargetKind`, which is already the tree's vocabulary for "which kind of personal-side
record this is about". Using it in the path means the client names the kind it is acting on and
the server cannot mix it up with the send kind (`ScheduledSend.Kind`), which is a *different*
enumeration — a distinction `delivery_messages._facts_for` already has a table for.

The kind is in the path rather than the body because a `PUT` replaces the plan at a **resource**,
and the resource is `(kind, id)`. A body-only kind would make the URL ambiguous.

### The 0-slot case, stated plainly

FR-9: *"A user can save a Reminder Plan with 0 to 4 slots. 0 slots = no reminders (still in
feed)."* The UX spec's empty state reads *"No reminders. You'll still see this event in Pulse
Digest."*

So **`PUT` with `slots: []` is a valid save.** It is not a delete and not an error. The plan row
**survives**, holding no slots, so "the user chose no reminders" stays distinguishable from "the
user never configured a plan" — which is exactly why `remove_all_reminders` empties the row rather
than deleting it, and the API must not quietly delete it either.

### The query-count bound

The AC asks that the query count be *"bounded and independent of slot count."* The design gives
that for free: the read is one query for the plan, one for the preference, one for the zone, and
one for the target — and the per-slot delivery times are computed **in Python** over those facts,
not with one query per slot. Four slots cost the same four queries as one slot.

The test asserts this with `django_assert_num_queries` (or the project's equivalent) at one slot
and at four, and asserts the counts are equal.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/delivery/services/reminder_plan_read.py` | The published read: the plan plus, for each slot, the post-Quiet-Hours delivery time, the deferred flag and the window end. Owns the target resolution (which produces the `SendTarget`) and the shift. |
| `backend/apps/delivery/schemas.py` | The Pydantic shapes. **The file exists and is empty** — this fills it, rather than creating a new one. |
| `backend/tests/delivery/test_reminder_plan_api.py` | The API contract tests: both target kinds, 0/1/4 slots, 5 rejected, the custom slot, ownership in both directions, the deferred flag, the rollback, the query count, the OpenAPI schema, and the AD-3 import check. |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/delivery/api.py` | The two endpoints. `Router(tags=["reminders"], auth=current_user)` — the auth is on the **router**, as `personalization`'s is. Thin: resolve, call the service, project the plain data. **No ORM writes** (the architecture test `test_no_direct_writes.py` treats `apps/*/api.py` as a surface file). |
| `backend/config/api.py` | `api.add_router("/reminders", reminders_router)`. The auth is **not** an `add_router` kwarg — it lives on the `Router`, matching `personalization`. |
| `backend/apps/delivery/services/reminder_plans.py` | Adds `save_plan_slots` — `set_plan_slots` plus the "plan missing → create it" branch, in one transaction. `set_plan_slots` itself is **unchanged** (other callers depend on its 404). |
| `backend/apps/delivery/services/scheduled_sends.py` | `_slot_due_at` is **promoted to published** (`slot_due_at`), so the API's read and the minting path share one implementation of the shift. Its signature gains the custom-slot offset. |
| `backend/apps/delivery/services/slots.py` | The custom-slot grammar: parse `custom:<minutes>`, enforce the UX spec's bounds (15 minutes – 30 days), and refuse more than one custom slot. `validate_slots` gains the bound check. |
| `backend/shared/constants.py` | `CUSTOM_SLOT_MIN_MINUTES = 15`, `CUSTOM_SLOT_MAX_MINUTES = 43200` (30 days), and the custom slot id's format — **one place**, read by the validator (AD-8). |
| `backend/apps/personalization/services/saved_events.py` | Adds `get_saved_event(*, user_id, event_id) -> SavedEventSnapshot`, raising `SavedEventNotFoundError`. The published read `delivery` needs (D3). |
| `backend/apps/delivery/send_keys.py` | The `SEND_KEY_MAX_LENGTH` comment's arithmetic — the custom slot's suffix is now minutes, not a uuid, so the key is shorter. |

## Files NOT Modified (and why)

- **`apps/delivery/models.py`** — no new column. The custom slot's offset rides in its id (D1),
  so no migration is needed. `makemigrations --check --dry-run` stays clean.
- **`apps/delivery/services/notification_preferences.py`** — the quiet window is already read
  through `get_preference`, and it is already `delivery`'s own row.
- **`domain/quiet_hours.py`** — the shift is already there, already pure, already tested. **A
  second shift implementation in TypeScript is exactly what this item exists to prevent.**
- **`apps/personalization/api.py`** — the picker is `delivery`'s surface (AD-16: `delivery` owns
  `REMINDER_PLAN`), and the work item says "`delivery`'s own router".
- **`apps/ingestion/services/catalog_read.py`** — `get_public_event` already exists and is the
  published read for a catalog event.

## Tests

**`backend/tests/delivery/test_reminder_plan_api.py`** — the API contract tests:

- both target kinds (a personal event, a saved public event);
- 0 slots, 1 slot, 4 slots — each its own save;
- 5 slots rejected, with the shared `{code, message}` shape;
- the custom slot, and its offset refused when out of the UX spec's bounds;
- **ownership in both directions** — another user's target is a **404**, not a 403, and their plan
  is unchanged;
- an anonymous request is a **401** with `not_authenticated`;
- the **deferred flag**: a slot that lands inside Quiet Hours answers `deferred: true` and a
  `deferred_to` equal to the window end; a slot outside it answers `deferred: false`;
- the **rollback**: `resync_plan` forced to fail leaves the plan's slots unchanged;
- the **query count** is the same at one slot and at four;
- the endpoints are in the OpenAPI schema;
- the AD-3 check — `apps/delivery/api.py` does not import `apps.ingestion.models`.

**`backend/tests/delivery/test_reminder_plan_read.py`** (or the same file) — the read's own
behaviour: the shift is applied, a deferred slot reports the window end, a custom slot's offset
is honoured, and a target of the wrong kind is refused.

**`backend/tests/delivery/test_slots.py`** — the custom-slot grammar: the bounds, the
"at most one custom slot" rule, and that a named slot is never mistaken for a custom one.

**`backend/tests/personalization/test_saved_events.py`** — `get_saved_event` finds the caller's
own save, refuses another user's, and raises when there is none.

### Gates

`ruff check .` · `ruff format --check .` · `lint-imports` (19 contracts) · `manage.py check` ·
`makemigrations --check --dry-run` · the new tests · then the full backend suite · then
`make client` and `git diff --exit-code frontend/lib/api/` (AD-19).

## Dependencies

None beyond what the run has already completed:

- `send-minting-and-rescheduling` — `scheduled_sends.py` as the schedule's writer, `resync_plan`,
  `mint_for_plan`, and the Quiet Hours arithmetic at compute time;
- `quiet-hours-domain` — `QuietHours` and `shift_to_sendable`;
- `notification-preferences` — `NotificationPreference` and `get_preference`;
- `email-templates-and-unsubscribe` — the reminder renderer's target facts, which pin the
  `target_id` convention this item follows.

## A note on the AD-19 client

The AC asks for *"Pydantic schemas and the regenerated client via `make client`; no hand-written
types (AD-19); CI's diff check passes."* `make client` regenerates
`frontend/lib/api/openapi.json` and `frontend/lib/api/schema.ts`. The generated files are
**committed** — CI's contract job runs `make client` and then `git diff --exit-code`, so a schema
that is not regenerated fails CI.

This item adds endpoints but **no frontend work** — the picker is the next work item
(`frontend-reminder-picker`). The generated client is regenerated here because the contract
changed; the frontend does not call the new endpoints until its own item.

---

# Implementation Plan: The preferences API — one settings surface over two modules

## The problem, in one paragraph

The window and the default plan live on `delivery`'s `NotificationPreference`. The delivery time
and the zone live on `personalization`'s `DigestPreference`. That split is deliberate — the
2026-10-31 ownership decision, recorded on the model — and the API's job is to **hide it from
the client**. One `GET` that returns all four facts; one `PUT` that writes any subset of them
and rewrites the user's pending sends in the same breath.

The trap is the rewrite. AD-7 says a preference change *"rewrites `due_at` on `pending` rows
only and never touches the key"*. There is a helper for that — `reschedule_pending_for_user` —
and it has **zero production callers**: it was built in `send-minting-and-rescheduling` and
nothing has ever called it. This is the item that calls it, and the helper has **two gaps** it
must close first.

## The two gaps in `reschedule_pending_for_user`

**Gap 1 — it skips digest rows.** The loop's guard is
`if not row.slot or row.event_version is None: continue`, with the comment *"A digest row's
due time is the user's delivery time, not a slot offset. It is recomputed by the digest
scheduler, which owns that arithmetic."*

That comment was true when it was written and it is now **wrong in the way that matters**. The
digest scheduler recomputes a digest's due time when it *composes* it, for a digest that does
not exist yet. It does not revisit a digest row that **already exists and is pending** — that
row was minted yesterday for today's local date, and it is the row the sweep will pick up. So a
user who changes their delivery time at 07:00 and already has today's digest row pending still
receives it at the **old** hour. That is exactly the bug the AC's Technical Note names:

> *"A test should change the delivery time and assert tomorrow's digest row moved with it and
> kept its `user_id · digest · local_date` key."*

So the rewrite must reach the digest rows, and it must compute their due time the way
`mint_digest` does — the user's delivery time, on the row's **local date**, shifted by Quiet
Hours.

**Gap 2 — the local date is not on the row.** `mint_digest` is called with a `local_date`, and
the key is `user_id · digest · local_date`, but the row stores **no date column**: `slot` is
`""`, `target_kind` is `""`, `target_id` is `NULL`, `event_version` is `NULL`. The date lives
**only inside the key**.

So the rewrite has to recover the local date from the key. That is a parse of a value this
module minted, and the parser belongs next to the builder — in `apps/delivery/send_keys.py` —
not inline in the rewrite loop. A key shape parsed in two places is a key shape that will be
parsed wrongly in one of them.

**Gap 3 — the zone is not the only thing a digest's due time needs.** `mint_digest` takes
`delivery_time` and `zone` as arguments, and the caller (`pulse_ping.mint_ping_send`) reads
them from `personalization`'s published `get_delivery_settings`. The rewrite is inside
`delivery`, so it needs the same two facts, read the same way, **once** (design D4: the zone
is read once, not once per row).

## The decisions

### D1 — the surface lives in `delivery`, and `delivery` reads `personalization` through its
published interface

`delivery` owns the window and the default plan. `personalization` owns the delivery time and
the zone. The API assembles both, so the API must live somewhere that can see both — and the
only app that can be the *owner* of the surface is `delivery`, because the two settings the
user thinks of as "notifications" are `delivery`'s, and because `delivery` is the app that
already reaches `personalization` through a published service.

`delivery` reads `personalization` through `get_delivery_settings` — **a function-local
import**, the `_zone_for` pattern, because a module-level import closes a cycle
(`personalization.services.personal_events` → `delivery.services.reminder_plans` →
`delivery.services.scheduled_sends`).

`personalization` never imports `delivery` in this item. The delivery-time write goes
**through `personalization`'s own published command** — `onboarding.set_digest_preference` —
which is what the AC asks for (*"through `personalization`'s published command"*) and what
keeps `DigestPreference`'s write ownership where it already is (AD-16). Onboarding's existing
endpoint keeps working unchanged, because it calls the same command.

### D2 — one facade service, one command service

Two new modules in `delivery`:

- **`apps/delivery/services/preferences_read.py`** — the `GET` facade. It reads
  `delivery`'s own preference row and `personalization`'s published delivery settings, and
  returns one frozen dataclass carrying all four facts. It is a *read*: it writes nothing.
- **`apps/delivery/services/preferences.py`** — the write commands: one per setting, each
  calling the owning module's command and then the rewrite.

The API layer stays thin: it resolves the user, calls the service, projects the plain data
onto the wire. It never imports a model.

### D3 — the shape of the write, and the atomicity

The AC says *"Partial writes are atomic — a request that sets the window and the default plan
either applies both or neither."*

So the `PUT` body is a **partial patch**: each field is optional, and an omitted field means
*"leave it alone"*. A field that is present is written. `quiet_hours` is present-and-`null`
meaning *"no quiet hours"* — which is different from omitted, because `None` is a real
value the user can choose.

**The atomicity mechanism.** Both modules write to the `personal` schema, so their
`transaction.atomic(using=PERSONAL)` blocks **nest** — Django's savepoint-based nesting means
an outer atomic makes the inner ones part of one transaction. So the outer
`transaction.atomic(using=PERSONAL)` in the API layer (or in the service) makes a
window-write and a default-plan-write **one transaction**: either both land or neither does.

**Where the outer atomic lives: the service, not the API.** The API is a surface; a
transaction that the service owns is a transaction a non-HTTP caller gets too. The service
opens one `transaction.atomic(using=PERSONAL)` around the whole request's writes.

**The delivery-time write is the awkward one**, because `personalization`'s command opens its
own atomic block and takes **its own advisory lock** (`b"eventpulse24-onb"`), while
`delivery`'s preference commands take **a different one** (`b"eventpulse24-ntf"`). Two locks
on two rows, taken in one outer transaction, in a fixed order (`onb` then `ntf`? or `ntf` then
`onb`?) — the order must be **fixed**, or two concurrent requests that write both settings
could deadlock.

The fixed order: **`delivery`'s lock first, then `personalization`'s**. Rationale: the delivery
surface is `delivery`'s, and a request that writes only `delivery`'s settings takes only
`delivery`'s lock — so the "one lock" path never waits on the "two locks" path. A request that
writes both takes `ntf` then `onb`; a request that writes only the delivery time takes `onb`
only, and never waits for `ntf`. No cycle.

### D4 — the rewrite: one command, called by every write

**Every one of those writes rewrites `due_at` on the user's `pending` rows** (AC). So the
rewrite is not optional per-setting — it is what each write *does* after the setting lands.

But the rewrite is not the same for each setting:

- **quiet hours changed** → the pending rows' `due_at` may move (the shift moved).
- **default plan changed** → **nothing moves**. The default plan applies to *future*
  attachments; existing per-event plans are untouched. The rewrite still *runs* (a user might
  have also changed the window in the same request) but it recomputes the same values, because
  the default plan is not part of any row's `due_at`.
- **delivery time or zone changed** → the digest rows move, and the reminder rows move too
  (the zone is part of every `due_at` computation).

**So the rewrite is one command, and the setting decides whether it changes anything.** The
command recomputes every pending row's due time from the *current* facts — the window, the
zone, the delivery time. A row whose recomputed time equals its stored time is left alone
(`due_at == base → continue`), so a no-op write touches nothing.

**This is what makes the default plan's non-retroactivity true *by construction*, not by a
special case.** The default plan is not an input to any `due_at` computation, so a rewrite
cannot move a per-event plan's row. The test asserts the row count and the keys are unchanged.

### D5 — the digest row's rewrite, and the key

A digest row's due time is: **the user's delivery time, on the row's local date, in the user's
zone, shifted by Quiet Hours** — exactly what `mint_digest` computes.

So the rewrite for a digest row is:

```python
local_date = digest_local_date_from_key(row.send_key)   # parsed from the key
due_at = shift_to_sendable(
    _local_delivery_instant(local_date=local_date, delivery_time=delivery_time, zone=zone),
    window=preference.quiet_hours,
    zone=zone,
)
```

`_local_delivery_instant` and `shift_to_sendable` are **already** the functions `mint_digest`
uses. Reusing them is what makes the rewritten time equal the time a freshly minted row would
carry — the same "by construction, not by two implementations agreeing" argument the reminder
path makes.

**The key does not move.** The rewrite writes `due_at` only. The key stays
`user_id · digest · local_date`, which is the AC's explicit demand and AD-7's rule. The
Technical Note's *"kept its `user_id · digest · local_date` key"* is exactly this.

**The parser.** `apps/delivery/send_keys.py` gains
`digest_local_date_from_key(send_key: str) -> date | None` — the inverse of `digest_key`. It
returns `None` for a key that is not a digest key, and the caller **skips rather than
guesses** (the same rule `slot_offset` follows).

### D6 — the local date and the zone, read once

Design D4: *"the zone is read once, not once per row."*

The rewrite needs:
- the **window** — `get_preference(user_id)`. **Once.**
- the **zone** — `get_delivery_settings(user_id)`. **Once.**
- the **delivery time** — the same read as the zone. **Once.**

So one call to `get_delivery_settings` yields both the zone and the delivery time, and it is
read once per rewrite, not once per row.

**One wrinkle:** `get_preference` **creates** the row on first call. So the steady state is one
SELECT, and the first call for a user is a SELECT + INSERT. A query-count test must measure
in the steady state — the same note that applies to the reminder-plan item.

### D7 — the `GET` response, and the shape of "no delivery settings"

The `GET` returns the four facts: the window, the default slots, the delivery time, the zone.

**The delivery time and the zone have a fallback.** `get_delivery_settings` returns `None` for a
user with no `DigestPreference` row — a real state (an account that has not finished
onboarding). The read falls back to `shared.constants`' `DEFAULT_DIGEST_DELIVERY_TIME` and
`DEFAULT_DIGEST_TIMEZONE`, **not** to a guess, and not to `None` on the wire — because a
settings screen that renders "no delivery time" cannot show the user what they will get. The
same fallback `delivery`'s `_zone_for` already applies.

**The window's fallback is different, and deliberately so.** `get_preference` **creates** the
row with the defaults on first read, so the window is always a real value — `None` only if the
user has explicitly turned quiet hours off. There is no "no preference yet" state for the
window, because the read creates it.

### D8 — the endpoint's surface and its schemas

New router, `apps/delivery/preferences_api.py`, mounted at `/api/settings` in `config/api.py`,
with `auth=current_user` **on the router** — the same rule as `personalization`'s and
`delivery`'s other routers: the user id comes from the session and **never from a payload**
(AD-12's personal-surface rule).

Two endpoints:

- `GET /api/settings/notifications` — the four facts, one response.
- `PUT /api/settings/notifications` — the partial patch.

**Why `/api/settings` and not `/api/reminders/notifications`?** The work item says *"the two
`/settings/*` routes"* — the frontend item is `frontend-settings-reminders-and-quiet-hours`,
and the two settings screens are *reminders* and *quiet hours*, both of which this endpoint
carries. `/api/settings` is the parent both live under, and one endpoint serving both screens
is why the AC says *"one call, one response"* — the client fetches the settings page once and
renders both halves from it.

### D9 — the wire shapes

Pydantic schemas in `apps/delivery/schemas.py` (the file the reminder-plan item created and
owns):

- **`NotificationSettingsOut`** — `quiet_hours: QuietHoursOut | None`,
  `default_reminder_slots: list[str]`, `delivery_time: time`, `timezone: str`.
- **`QuietHoursOut`** — `start: time`, `end: time`.
- **`NotificationSettingsIn`** — `quiet_hours: QuietHoursIn | None = None`,
  `default_reminder_slots: list[str] | None = None`,
  `delivery_time: time | None = None`, `timezone: str | None = None`.

**Three states, and the wire must tell them apart.** An omitted field means *"leave it alone"*.
A present-and-`null` `quiet_hours` means *"no quiet hours"*. Pydantic's `None` default cannot
express "omitted" — but **`None` as the default plus a sentinel for "explicitly off"** can, and
the sentinel is the honest one.

The cleanest shape: `quiet_hours: QuietHoursIn | None` where the **default is a sentinel
meaning "unset"**. Two candidates:

1. A module-level `_UNSET` sentinel object, and the field typed `QuietHoursIn | None | _Unset`.
   Pydantic can handle a sentinel default if the type allows it, but the generated OpenAPI
   becomes awkward.
2. **Make the whole request a set of *optional sub-objects* whose presence is what matters**,
   and give the *explicitly-off* case its own spelling.

Option 2, concretely: the body carries
`quiet_hours: QuietHoursIn | None = None` and the **rule is stated in the schema**: `null`
means "no quiet hours" — but then an **omitted** `quiet_hours` would also be `null`, and
omitting it would clear the user's window. That is wrong.

So: **`quiet_hours` is `QuietHoursIn | None`, and the endpoint distinguishes "not mentioned"
from "explicitly null" by the field's presence in the raw payload.**

Django Ninja gives a Pydantic model its parsed body; Pydantic v2 records which fields were
set via `model_fields_set`. So the API can read `body.model_fields_set` and ask
*"was `quiet_hours` mentioned?"* — a first-class answer, not a sentinel.

**That is the decision: presence is read from `model_fields_set`.** It is exactly the
distinction the semantics need, it needs no sentinel, and it keeps the generated schema
honest (`quiet_hours` is nullable — "null" is a legal value; "omitted" is a different thing,
and the description says so).

The other three fields follow the same rule, and for them `null` is never a legal value:
omitting `default_reminder_slots` leaves the default alone; sending `[]` sets it to empty.
So `default_reminder_slots: list[str] | None = None` — `None` means "leave it alone", and
`[]` means "no reminders by default". **An empty list is not null**, and the two are
different states that the wire distinguishes without a sentinel.

`delivery_time` and `timezone` are a **pair**: the delivery time is meaningless without the
zone it is a wall clock in, and the zone without a time. So they are one nested object:
**`digest: DigestScheduleIn | None`** — `{"delivery_time": "09:00", "timezone": "America/New_York"}`.

That also gives the write a natural atomicity: the pair is one field, so it cannot be
half-applied. And it matches how the value is stored (`DigestPreference.delivery_time` +
`.timezone` are written by `_write_digest` together).

**So the request body is four optional fields:**

| Field | Omitted | Present |
|---|---|---|
| `quiet_hours` | leave the window alone | `null` = no quiet hours; `{start, end}` = that window |
| `default_reminder_slots` | leave the default alone | `[]` = no reminders by default; else the slots |
| `digest` | leave the delivery time and zone alone | `{delivery_time, timezone}` |

**A full-day window is rejected** — `start == end` is `QuietHours.disabled`, and
`set_quiet_hours` already refuses it with `InvalidQuietHoursWindowError` (a 422 with a
readable message). The API does **not** add a second check; it lets the command refuse it.
That is the *"reusing one validator rather than a second copy"* discipline applied to the
window as well as to the slots.

### D10 — the slots validator is reused, not copied

`set_default_reminder_slots` **already calls `validate_slots`**. So the API does not validate
slots at all — it passes them through, and the command refuses a bad list. One validator,
one place (`apps/delivery/services/slots.py`), already the leaf both commands depend on.

### D11 — ownership

The router's `auth=current_user` means the user id comes from the session. There is **no
user id in the path and none in the body** — so there is nothing to tamper with. Another
user's settings are unreachable by construction, not by a check.

Anonymous → **401** (`current_user` raises `HttpError(401, ...)`). No endpoint accepts a user
id, so there is no "ownership" branch to get wrong.

### D12 — what is NOT changed

- **`onboarding.set_digest_preference` keeps its shape.** The API calls it; onboarding's
  endpoint calls it; nothing about it changes. **But** — and this is the one thing that must
  be checked — onboarding's endpoint does **not** rewrite pending sends today. If the new
  endpoint rewrites and onboarding's does not, then the same write has two behaviours
  depending on which door it came through.

  **The decision: the rewrite lives in the API's service, not inside
  `personalization`'s command.** `personalization` does not know about `SCHEDULED_SEND`
  (AD-16: `delivery` owns that table), so it cannot rewrite the rows — and the AC says the
  delivery-time write goes *"through `personalization`'s published command"*, which is about
  **who writes `DigestPreference`**, not about who rewrites the sends.

  So: the API's service calls `personalization`'s command (which writes the row), then calls
  `delivery`'s rewrite (which re-times the sends). Onboarding's endpoint calls the same
  command and does not rewrite — **which is correct**: onboarding happens before the user has
  any pending sends to rewrite. The two doors differ in what they rewrite because the
  situations differ, and the difference is not visible to the user (a user in onboarding has
  no pending sends).

  This is recorded because it is exactly the kind of difference a later reader would trip
  over.

- **`reschedule_pending_for_user`'s name and signature.** It stays. Its *body* gains the
  digest branch — a widening, not a change of contract.

- **The `NotificationPreference` model.** Untouched. No new columns.

- **The `DigestPreference` model.** Untouched.

### D13 — a fourth gap, found by the tests: a deferred row cannot be re-timed

The three gaps above are all about **digest** rows. Writing the tests turned up a **fourth**
gap, and this one is about **reminder** rows — the rows the Quiet Hours write exists for.

**The bug.** `reschedule_pending_for_user` recomputed a reminder's due time from
`row.due_at + offset`, deriving the event's start from the stored time. That is an
*approximation*: `due_at` is the **post-Quiet-Hours** instant, so for a row that was
**deferred** the derivation compounds. A 22:30 reminder pushed to 08:00 reads as one that
was for 09:00, and re-shifting that lands on the wrong hour again — and, worse, lands on the
*same* wrong answer, so the row never moves.

**Why it matters here and not before.** The existing suite never rescheduled a *deferred*
row: its one rewrite test minted a row that the default window did not cover, so the
approximation was exact. This work item's first test mints a row that **is** covered —
because moving a deferred row is the whole point of a Quiet Hours write — and the
approximation fell over.

**The two candidate fixes, and why the second loses.**

| | read the event's start from its owner | keep the pre-shift instant on the row |
|---|---|---|
| how | `delivery` asks `personalization` for the start of each target | a new `slot_at` column on `SCHEDULED_SEND` |
| queries | **two** (one per kind), batched | **zero** |
| correctness | correct | correct |
| the codebase's convention | **breaks it** — the tree holds cross-module ids *by value*; a plan needs **no** backing event to exist | keeps it — the row holds the id and the time together |
| the existing suite | **breaks** — `test_rescheduling_rewrites_due_at_without_changing_keys` mints against a synthetic target with no save behind it | passes unchanged |
| cross-module surface | adds two published reads to `personalization` for `delivery`'s benefit | none |

The first option was implemented, and it was **wrong for this codebase**: the tree's
convention is explicit — *"the plan holds the reference by value, like every other
cross-module id here"* — and making a rewrite depend on a backing record existing makes a
pending row's fate depend on a row it does not own.

**The decision: `ScheduledSend.slot_at` — the instant the slot names, before Quiet Hours
moved it.**

The row then carries two instants, and they are the same kind of pair as `event_version`'s:
one frozen at minting (in the key) and one re-stamped by propagation (in the column).

- `slot_at` — **the instant this send was for.** A reminder's is its slot
  (`event_start - offset`); a digest's is its local delivery instant.
- `due_at` — **the instant this send goes out**, already shifted.

And the rewrite becomes one arithmetic: `due_at = shift_to_sendable(slot_at, window, zone)`.
**The shift is the only difference between the two columns**, so re-timing is exactly one
function call — and it is *correct* for a deferred row, because the pre-shift instant was
kept rather than reconstructed.

**This is also the cheaper design.** The AC asks for *"one pass over the user's pending
rows, not one query per row, and the zone read once"*. The column meets that with room to
spare: the zone is read once, the rows are read once, and **the user's calendar is not read
at all**. The alternative needed two more queries and two more published reads in another
app.

**The digest branch is the one thing that does not use `slot_at`.** A digest is about a
*time of day*, so a delivery-time change has to move it — and `slot_at` holds the old
delivery instant. The digest's local date is immutable and lives in its key, so the digest's
pre-shift instant is rebuilt from **the key's date and the current delivery time**, which is
exactly what `mint_digest` does. The key parser stays, beside the builder.

**What this costs.** One migration (`0005_scheduledsend_slot_at`), one nullable column, and
the `ScheduledSend` factory sets `slot_at` so factory rows are re-timeable rather than
skipped.

## Files to create

| File | What it holds |
|---|---|
| `backend/apps/delivery/services/preferences_read.py` | The `GET` facade — one read across the two modules, one dataclass. |
| `backend/apps/delivery/services/preferences.py` | The write commands — one per setting, each calling the owner's command and then the rewrite. |
| `backend/apps/delivery/preferences_api.py` | The router: two endpoints, `auth=current_user`, the partial-patch semantics. |
| `backend/tests/delivery/test_preferences_api.py` | The API tests — the AC's list, one test per claim. |
| `backend/tests/delivery/test_preferences.py` | The service tests — the rewrite's digest branch, the atomicity, the query bound. |

## Files to modify

| File | What changes |
|---|---|
| `backend/apps/delivery/services/scheduled_sends.py` | `reschedule_pending_for_user` gains the digest branch; `_local_delivery_instant` is reused; the delivery time is read once. **And, per D13: the reminder branch is re-timed from the row's `slot_at` instead of the `due_at + offset` approximation, and both minting paths write `slot_at`.** |
| `backend/apps/delivery/models.py` | **The `slot_at` column** (D13) — the instant the slot names, before Quiet Hours. |
| `backend/apps/delivery/migrations/0005_scheduledsend_slot_at.py` | **The migration for that column** (D13). |
| `backend/apps/delivery/send_keys.py` | `digest_local_date_from_key` — the inverse of `digest_key`. |
| `backend/apps/delivery/schemas.py` | The three wire shapes: `QuietHoursOut`, `NotificationSettingsOut`, and the patch body. |
| `backend/config/api.py` | The `/api/settings` mount. |
| `backend/tests/delivery/factories.py` | **`ScheduledSendFactory` sets `slot_at`** (D13) — a factory row is not deferred, so the two instants coincide, and the row stays re-timeable. |
| `backend/tests/delivery/test_scheduled_sends.py` | The digest-rewrite tests and the key parser's tests. |

## Tests

Every claim the AC makes, one named test:

**The `GET`**
- `test_the_get_returns_the_window_the_default_slots_the_delivery_time_and_the_zone` — all four in one response.
- `test_the_get_assembles_the_response_across_the_two_modules` — the response is built from `delivery`'s row and `personalization`'s published read, and neither module's models are imported by the API module (an `ast` check, like the reminder-plan item's AD-3 test).
- `test_the_get_falls_back_to_the_shared_defaults_when_there_is_no_digest_preference` — a user with no `DigestPreference` row gets the constants, not `None` and not a guess.
- `test_the_get_reports_no_quiet_hours_when_the_user_turned_them_off` — `null` on the wire.

**The quiet-hours write**
- `test_putting_the_window_writes_it`
- `test_putting_a_null_window_turns_quiet_hours_off`
- `test_omitting_the_window_leaves_it_alone`
- `test_a_full_day_window_is_refused_with_a_readable_message` — `start == end` → 422, and the message says what is wrong.
- `test_the_window_write_rewrites_the_pending_rows_due_at`
- `test_a_deferred_row_keeps_the_instant_it_was_for` — **D13.** The row carries both instants, and the round trip works: quiet hours off brings the reminder back to its own hour, on pushes it out again to the same hour.
- `test_the_rewrite_does_not_read_the_calendar` — **D13.** The rewrite reads the rows and the zone and nothing else — no event, no save, no per-row query.

**The default-plan write**
- `test_putting_the_default_slots_writes_them`
- `test_putting_an_empty_default_is_valid`
- `test_the_default_slots_use_the_same_validator_as_the_per_event_plan` — a 5-slot list and a bad slot are refused **with the same error** the per-event plan gives, because it is the same validator.
- `test_changing_the_default_plan_does_not_touch_the_existing_per_event_plans` — the AC's explicit non-retroactivity: the plan rows are unchanged and their pending sends' keys and count are unchanged.

**The delivery-time write**
- `test_putting_the_delivery_time_writes_it_through_the_published_command`
- `test_putting_the_delivery_time_moves_tomorrows_digest_row_and_keeps_its_key` — **the Technical Note's test.** The digest row's `due_at` moves and its `send_key` is still `user_id · digest · local_date`.
- `test_putting_the_delivery_time_moves_the_pending_reminder_rows_too`
- `test_a_bad_timezone_is_refused`

**The rewrite's invariants**
- `test_the_keys_are_unchanged_across_ten_successive_changes` — ten writes, ten reads, the key set is identical.
- `test_a_sent_row_is_never_touched`
- `test_a_cancelled_row_is_never_touched`
- `test_the_row_count_does_not_change_when_the_window_changes` — the rewrite never mints.
- `test_the_rewrite_reads_the_zone_once_not_once_per_row` — design D4, by query count.
- `test_the_rewrite_is_one_pass_over_the_pending_rows` — the query count does not grow with the number of rows.

**Atomicity**
- `test_a_request_that_sets_the_window_and_the_default_plan_applies_both`
- `test_a_request_that_sets_the_window_and_the_default_plan_applies_neither_when_one_fails` — a forced failure in the second write leaves the first unapplied.

**Ownership**
- `test_anonymous_gets_401`
- `test_anonymous_put_gets_401`
- `test_a_caller_cannot_read_another_users_settings` — the endpoint takes no user id, so this is structurally true; the test asserts the second user's settings are invisible to the first.

**The command layer**
- `test_onboardings_digest_preference_endpoint_still_works` — the existing endpoint is untouched.

## Gates

`ruff check .` · `ruff format --check .` · `lint-imports` (19 contracts) · `manage.py check` ·
`makemigrations --check --dry-run` · the new tests · then the full backend suite · then
`make client` and `git diff --exit-code frontend/lib/api/` (AD-19).

## Dependencies

- `notification-preferences` — `NotificationPreference`, `get_preference`, `set_quiet_hours`,
  `set_default_reminder_slots`, `default_slots_for`, and the `validate_slots` call inside
  `set_default_reminder_slots`.
- `send-minting-and-rescheduling` — `scheduled_sends.py` as the schedule's single writer,
  `reschedule_pending_for_user` (the helper this item finally calls), `mint_digest`'s
  due-time arithmetic, and the Quiet Hours shift at compute time.
- `reminder-plan-api` — the router/schema conventions this endpoint follows, and the
  `read_plan_for` pattern (resolve once, read back once) applied to the settings read.

## A note on AD-19

The client is regenerated because the contract changed. The generated files are **committed** —
CI's contract job runs `make client` and then `git diff --exit-code`. This item adds the
settings endpoints; the frontend that calls them is the next item
(`frontend-settings-reminders-and-quiet-hours`).

---

# Implementation Plan: The reminder picker — four chips, and the one that dims

**Work item**: `frontend-reminder-picker` (the 10th)
**Route**: `/events/:id/reminders`
**Mode**: `confirm`

## The problem, in one paragraph

`reminder-plan-api` built the endpoint; nothing calls it. The Detail Screen's reminder
section is still `components/detail/detail-reminder.tsx` — a set of `<span>`s, deliberately
display-only, because when it was written "nothing scheduled sends". **That is no longer
true**: `ScheduledSend` rows are minted, the sweep sends them, and the plan API returns
each slot's computed delivery time. So the display-only span is now a **control that
cannot be operated**, which is the failure its own docstring says is worse than silence.

The picker's one real piece of work is the **Quiet Hours chip state**: a chip whose
delivery time would land inside the user's window dims to 40% opacity and says *"Will
deliver at 8:00 am Saturday."* — and **stays selectable**. That state comes from the
server's per-slot `deferred` flag, and it must not be recomputed in the browser.

## The one conflict in the source documents, and how it is settled

**Three documents describe the selected chip, and two of them disagree.**

| Source | What it says the selected chip looks like |
|---|---|
| `DESIGN.md` §Components → `component.input.reminder.slot` | *"Selected state fills with `rgba(255,106,71,0.10)` and shifts the label to `color.accent.terracotta`."* |
| `EXPERIENCE.md` §4 → `Input.ReminderSlot` | *"no terracotta on this chip; selection is communicated by ink inversion, not by accent"* — selected is `color.ink.primary` fill with `color.ink.inverse` label. |
| **The work item's AC** | *"**Selection is ink inversion, never terracotta** … selected is `color.ink.primary` fill with `color.ink.inverse` label; unselected is `color.ink.primary` on `color.surface.subtle`. **A test asserts no accent token on this chip.**"* |

**The AC decides it, and the AC is not arbitrary.** It cites `component.input.reminder.slot`
as the token name and then contradicts that token's *colour* — so it is deliberately
overriding DESIGN.md's colour line, not misremembering it. The reason is in DESIGN.md
itself: `ASSUM-6` generalises the terracotta tint as *"the canonical small-control
selection treatment across the system"* — and a control used **many times per day** (the
sidenav's active-route pill says the same thing) burns the accent. The reminder chip is
one of those.

**So the chip is ink inversion**, and the test that proves it is a **source check**: the
chip's class string must contain **no accent token at all**. A terracotta tint would be
invisible to a visual review and obvious to that check.

**The DESIGN.md line is not deleted.** It stays in the design file as a record of the
older decision; this plan records that the AC overrode it for *this* chip, and why.

## The decisions

### 1. The route is a **full page**, not a sheet

**Decided with the user 2026-10-31** (the work item's own first line). The route is
`/events/:id/reminders`, in the A-8 shell: the 240px sidenav, the brand-only topbar, and
the crumb `Digest · {event name} · Edit reminders`.

**The crumb's shape comes from Amendment A-21**, the mockup migration: *"The prior '←
Free tech meetup' back link becomes a crumb segment (`Digest · Free tech meetup —
'Designing for Calm' · Edit reminders`)."* The mockup's crumb has **three** segments —
the digest, the event, and the page — and the work item's AC says the crumb is
`Digest · {event name} · Edit reminders`, which is the mockup's **three** segments with
the mockup's *digest* slot filled by the event's own context. The AC's spelling wins: the
crumb is `Digest · {event name} · Edit reminders`, and the event's name is the
**title** the API returns, not the mockup's two-part "collection — title" string.

**The IA's 14 routes gain a 15th.** The work item says so: *"that gets an amendment note
rather than being left as a silent divergence."* The note goes in this plan and in the
test report.

### 2. The crumb's event name comes from the **Detail Screen's own read**

The picker needs the event's title for the crumb, and the title is not on the plan
payload — the plan payload carries `target_kind`, `target_id`, `slots` and `deliveries`.

**The picker reads the event's detail for the title**, through the same published read
the Detail Screen uses (`lib/event-detail-read.ts`). It is one extra request, and it is
the right one: the event's title is the **catalog's** fact, the catalog is behind AD-3's
wall, and the plan API deliberately does not carry it. A picker that guessed a title, or
that showed an empty crumb, would be worse.

**The target kind is a decision the picker makes once**, and it is decided from what the
picker is: a **saved public event** (`saved_event`). The Detail Screen's "Edit reminders"
link is on a catalog event, and the plan API's target vocabulary is `personal_event` /
`saved_event` — a public event the user has saved is a `saved_event`. A **personal**
event's reminders are edited on the personal-event sheet, which is where that plan lives.

### 3. The dimmed state is the server's flag, read — never recomputed

`ReminderSlotDeliveryOut` carries `deferred: boolean` and `deferred_to: datetime | null`.
The chip dims **iff** `deferred` is true, and the tooltip reads *"Will deliver at {…}"*
built from `deferred_to`.

**There is no Quiet Hours arithmetic in the frontend.** The AC's Technical Note says why:
*"Computing it in the browser would mean a second implementation of the Quiet Hours shift
in TypeScript, with DST and the midnight-crossing window rediscovered there — the exact
duplication `reminder-plan-api` returns the computed times to prevent."*

**The dimmed state is conveyed by text as well as opacity.** The AC says so: *"the dimmed
state is conveyed by text and not by opacity alone"*. So the chip carries the tooltip
**as visible text** in its accessible description — and the tooltip is **reachable
without hover**, so it is not a `title` attribute and not a hover-only popover.

### 4. The four chips are **buttons with `aria-pressed`**, not switches

The AC says: *"chips are real controls reachable by keyboard, `aria-pressed` reflects
selection"*.

**`aria-pressed`, not `role="switch"`.** The mockup's chip row uses `role="switch"`
toggles. A switch is for a setting that is **on or off independently**; these four chips
are a **multiple choice** — turning one on and another off is one act. `aria-pressed` is
the toggle-button semantic, and it is what the AC names. The mockup's markup is a
mockup; the AC is the contract.

**The chips are `<button type="button">` inside a `<fieldset>`** with a `<legend>`. The
legend is the locked microcopy: **"Remind me:"**. A fieldset is what makes a group of
toggles announce as a group to a screen reader, and it is the correct element for a set
of controls that together form one answer.

### 5. The custom slot is a **number input**, and the server's bound is **surfaced**

The AC: *"One custom slot can be added, with its own interval; a second is not offered.
The server's bound is surfaced as an inline message, not a silent clamp."*

**The custom slot's id is `custom:<minutes>`** — the grammar the API's `ReminderPlanIn`
documents and the backend's validator enforces (`custom_slot_minutes`). So the picker
offers **minutes before the event**, and sends `custom:${minutes}`.

**The bound is 15 minutes to 30 days** (43200 minutes). The picker offers that bound in
the input's own affordances — a `min`/`max` and a stated range — and when the value is
outside it, **the server's refusal is surfaced inline**.

**Why the server's message and not a client-side one.** The AC says *"the server's bound
is surfaced as an inline message, not a silent clamp"* — the bound belongs to the server,
so the message belongs to the server. The client does **not** clamp: it sends what the
user typed, and shows what came back. A client-side clamp would be a second copy of the
bound, free to drift, and it would silently change what the user chose.

**A second custom slot is not offered** because the API refuses one (`TooManyCustomSlotsError`).
The picker removes the custom-slot control when one is already in the plan, rather than
offering a control that cannot be used.

### 6. **Reset to default** restores the user's default plan — and the default is **not** re-derived in the browser

The action bar is **Reset to default** (ghost) and **Save reminder plan** (primary).

**What "default" means.** The user's own default plan — `NotificationPreference.
default_reminder_slots` — is what a **newly attached** plan starts as (FR-20). The
backend's `default_slots_for(user_id)` is the published read of it.

**But the picker cannot read it** — there is no endpoint that exposes the user's default
plan over the personal API. The settings endpoint (the 9th item) does expose it:
`GET /api/settings/notifications` returns `default_reminder_slots`.

**So "Reset to default" reads the settings endpoint.** That is one extra call, and it is
the right one: the default plan is a real fact about the user, it is owned by `delivery`,
and the settings endpoint is its published read.

**What it does when clicked.** It **restores the chips to the default** — it does not
save. The save is still an explicit act, because a plan that is saved is a plan whose
sends have been minted, and a button that saved without saying so would be the opposite
of "Success is quiet".

**The default's chips have no delivery times.** The settings endpoint returns the slot
ids, not the per-slot delivery times. So after a reset, the chips are **selected but not
yet timed**: the chip shows its label and no "Will deliver at" line, because the server
has not computed one for a plan that is not saved. **The dimmed state is therefore
absent on a freshly reset chip** — and that is honest: the server has not said the chip
is deferred.

**The dimmed state is re-read after the save.** The `PUT` returns the saved plan with
its computed deliveries, so the chips get their real times — and their real dimmed
states — **from the save's own response**, not from a second read.

### 7. The picker is a **client component**, and the page is a **server component**

The picker is interactive — chips toggle, a custom slot is added, a save happens — so it
is `"use client"`, exactly like `components/detail/detail-actions.tsx`.

**The page is a server component** and does the reads, exactly like
`app/events/[id]/page.tsx`: it reads the event detail and the plan on the server and
hands plain data to the island. The crumb, the heading and the event's own times are
server-rendered.

**The save happens in the browser**, through the generated client, because a save that
navigates would lose the "Saved." confirmation and the "Couldn't save" message — both of
which the AC requires, and neither of which survives a navigation.

### 8. The **target kind** is a prop, and it is the one thing the route does not carry

`/events/:id/reminders` has one id, and the API has two target kinds. The picker takes
`targetKind` as a prop, and the route passes `saved_event`.

**Why not infer it.** The API resolves the target by kind, and a target of the wrong kind
is a **404**. The route is for the **saved public event** — the Detail Screen's
"Edit reminders" is the only entry point — so the kind is a fact about the route, not a
guess.

### 9. The loading state is a **skeleton**, and the AC's "chips render immediately" is
**not** honoured

EXPERIENCE.md's `Input.ReminderSlot` says: *"**Loading:** Chips render immediately (no
loading state — local save)."*

**That line is about a different architecture** — it describes a local, optimistic save
with no server round-trip. This picker reads the plan from the server, so it cannot
render the chips "immediately": the chips' **delivery times and dimmed states** are the
server's answer, and before the read there is no answer.

**The work item's AC overrides it**: *"States: skeleton while loading; 'Couldn't save.
We'll try again on your next change.' on a failed save, with the chosen state kept
rather than reverted."* The AC names a skeleton, so there is a skeleton.

**The skeleton is the Detail Screen's own shape** — the same treatment
`app/events/[id]/loading.tsx` gets, and the same `DetailSkeleton` vocabulary. A route
that shows a spinner where its sibling shows a shaped block is a route that reads as
broken.

### 10. The **empty state** is a line, not a warning

*"No reminders. You'll still see this event in Pulse Digest."* — the AC's wording, and
EXPERIENCE.md's, **verbatim**.

**A 0-slot save is a normal save.** The AC says so: *"Saving 0 slots is a normal save
with a calm confirmation, not a warning."* So the empty state is **the same line**, and
the save confirmation is the same **"Saved."** — no special case, no warning colour, no
"are you sure".

### 11. Success is **"Saved."** — and it is a **live region**

*"Success is quiet — 'Saved.', no emoji, no celebration."* The word is exactly `Saved.`,
in a `role="status"` region, so a screen reader hears it too.

**The success message replaces itself.** It is shown after a successful save and then
goes away — a status region that keeps saying "Saved." forever is noise. The timer is
**not** an animation: no transition, no fade — the codebase's motion rule is that motion
goes through `.fade-in` only, and a status message that fades is a message that is
half-gone when it is read.

### 12. A failed save **keeps the chosen state**

*"Couldn't save. We'll try again on your next change."* — **verbatim**, and **the chips
stay as the user left them**.

**This is the important part.** The AC says: *"with the chosen state kept rather than
reverted."* A failed save that snapped the chips back would take away the user's choice
and make them re-do it — and the message says the system will try again, so the state
must be there to try again **with**.

**The message is inline, below the chip row**, one line, in `color.warn.amber` — the
EXPERIENCE.md spec.

### 13. The route's **"Edit reminders"** link on the Detail Screen

The Detail Screen's reminder section becomes a **link to the picker**, and the
display-only `<span>` chips go away.

**The Detail Screen's section is replaced, not decorated.** The old component's whole
reason for existing — *"nothing schedules sends"* — is false. A display-only summary
next to a link to the editor would show the user the same information twice.

**The link's label is "Edit reminders"** — the AC's wording, and the phrase the crumb
and the mockup both use.

**The Detail Screen's section keeps its heading and its one-line explanation**, so the
screen still says what reminders are, and the link is the way to change them.

## Files to create

| File | What it holds |
|---|---|
| `frontend/app/events/[id]/reminders/page.tsx` | The route — a server component: the reads, the crumb, the heading, the shell. |
| `frontend/app/events/[id]/reminders/loading.tsx` | The skeleton, in the Detail Screen's own shape. |
| `frontend/components/reminders/reminder-picker.tsx` | The island: the chips, the custom slot, the action bar, the states. |
| `frontend/components/reminders/reminder-chip.tsx` | One chip — the ink inversion, the dimmed state, the `aria-pressed`. |
| `frontend/components/reminders/reminder-picker.test.tsx` | The island's tests: the chips, the dimmed state, the custom slot, the states. |
| `frontend/lib/reminder-plan-read.ts` | The plan read, on the server, through the generated client. |
| `frontend/tests/reminder-picker-a11y.test.tsx` | The axe-core gate over every state. |

## Files to modify

| File | What changes |
|---|---|
| `frontend/app/events/[id]/page.tsx` | The reminder section becomes a link to the picker; the display-only component is dropped. |
| `frontend/components/detail/detail-reminder.tsx` | **Deleted** — its premise (nothing schedules sends) is false, and the picker replaces it. |
| `frontend/tests/ad19-endpoint-coverage.test.ts` | The reminders endpoint is added to `NEW_ENDPOINTS`, with its caller. |
| `frontend/tests/architecture.test.ts` | **Unchanged** — the new files are kebab-case and use no motion class. |

## Files NOT modified (and why)

| File | Why not |
|---|---|
| `frontend/components/shell/sidenav.tsx` | The picker's active sidenav item is **Digest**. The sidenav marks `pathname === "/"` as active, so the picker path would not mark it — **so the sidenav needs one change**, and it is listed below. |
| `frontend/lib/api/schema.ts` | **Generated.** The endpoint is already in the contract from `reminder-plan-api`; nothing is added to it. |
| `frontend/styles/tokens.css` | No new token. The chip uses `bg-ink-primary` / `text-ink-inverse` / `bg-surface-subtle` / `text-ink-primary` — all four already exist. |

### The sidenav's active item

The AC: *"**Digest** as the active sidenav item (the picker hangs off Digest in the IA,
as Detail does)."*

The sidenav's rule is `pathname === "/"` for Digest. **The Detail Screen has the same
problem and solved it** — let me check how. The sidenav's Digest item must also be active
for `/events/[id]`, because Detail hangs off Digest in the IA too. **If the Detail Screen
already marks Digest active on its own path, the picker inherits the rule for free.** If
it does not, the sidenav's rule becomes "the Digest item is active on `/` and on every
path under `/events/`".

## Tests

Every claim the AC makes, one named test.

**The route**
- `test_the_route_renders_the_crumb` — `Digest · {event name} · Edit reminders`.
- `test_the_route_renders_in_the_app_shell` — the sidenav is there, and Digest is the active item.
- `test_the_route_is_a_server_component_that_reads_the_plan_on_the_server`.

**The chips**
- `test_the_four_chips_are_rendered` — 5d / 2d / 1d / 1hr, labelled "Remind me:".
- `test_a_chip_toggles` — clicking a chip toggles it, and `aria-pressed` follows.
- `test_the_selected_chip_is_an_ink_inversion_and_never_terracotta` — **the source check**: the chip's class string contains **no accent token**.
- `test_the_chips_are_reachable_by_keyboard` — they are `<button>`s, in a `<fieldset>` with a `<legend>`.

**The dimmed state**
- `test_a_deferred_chip_dims_and_says_when_it_will_deliver` — the flag drives the dim, and the tooltip is the text.
- `test_a_deferred_chip_is_still_selectable`.
- `test_a_chip_that_is_not_deferred_does_not_dim`.
- `test_the_four_worked_examples` — **EXPERIENCE.md's four, verbatim**, as four cases over the same component.

**The custom slot**
- `test_a_custom_slot_can_be_added`.
- `test_a_second_custom_slot_is_not_offered`.
- `test_an_out_of_range_custom_slot_shows_the_servers_message` — **not a clamp**: the value the user typed is what was sent, and the server's refusal is what is shown.

**The empty state**
- `test_no_chips_selected_reads_the_empty_line` — *"No reminders. You'll still see this event in Pulse Digest."*
- `test_saving_zero_slots_is_a_normal_save` — the request carries `slots: []`, the answer is *"Saved."*, and there is no warning.

**The action bar**
- `test_reset_to_default_restores_the_users_default_plan` — the default comes from the settings endpoint.
- `test_reset_to_default_does_not_save` — no `PUT` is sent.
- `test_save_sends_the_chosen_slots` — through the generated client.

**The states**
- `test_the_loading_state_is_a_skeleton`.
- `test_a_failed_save_shows_the_message_and_keeps_the_chosen_state` — the chips are still the user's choice.
- `test_a_successful_save_reads_saved` — exactly `Saved.`, and no emoji.
- `test_the_saved_response_refreshes_the_delivery_times` — the `PUT`'s own response carries the new times.

**Accessibility**
- `test_the_dimmed_state_is_conveyed_by_text_not_opacity_alone`.
- `test_the_tooltip_is_reachable_without_hover`.
- `test_the_focus_ring_is_the_terracotta_stroke`.
- `test_reduced_motion_renders_instantly`.

**The Detail Screen**
- `test_edit_reminders_links_to_the_picker`.

## Gates

`pnpm lint` · `pnpm typecheck` · `pnpm format:check` · `pnpm test` (the frontend suite) ·
`make lint-web` · the **backend** suite (the Detail Screen's test asserts the link) ·
`make client` and `git diff --exit-code frontend/lib/api/` (AD-19 — the contract did not
change, so the regenerated client must be **byte-identical**).

## Dependencies

- `reminder-plan-api` — the `GET`/`PUT /api/reminders/{target_kind}/{target_id}`
  endpoints, `ReminderSlotDeliveryOut.deferred` / `.deferred_to`, the `custom:<minutes>`
  grammar, and the 0-to-4 rule.
- `notification-preferences-api` — `GET /api/settings/notifications`, whose
  `default_reminder_slots` is what **Reset to default** restores.

## A note on the IA

The IA table's 14 routes gain a 15th: `/events/:id/reminders`. **That is a divergence
from the IA, and it is recorded here rather than left silent** — the work item asks for
an amendment note, and this is it. The route hangs off Digest in the IA's own logic (the
Detail Screen does too), so it does not introduce a new top-level destination; it is a
second level under an event, like the Detail Screen itself.

## A note on what is deliberately absent

**The mockup's three aside panels are not built**: this reminder plan summary, the Pro
per-event quiet hours upsell (FR-51), and the "less like this" explainer (FR-25). The AC
says so explicitly: *"Out of scope, and deliberately absent from the mockup's three aside
panels."* Both FR-51 and FR-25 belong to later intents.

**The drag-to-add timeline is not built.** EXPERIENCE.md's `Input.ReminderSlot` describes
*"Drag-to-add: The user can drag a chip along a horizontal timeline"*, and the mockup has
no timeline (it has a chip list). The AC describes **four slot chips** and a custom slot,
and its test list says *"chip rendering and selection"* — selection, not dragging. Drag is
a second input method for the same answer, and the AC does not ask for it.

**A drag-to-add would also need a decision the AC does not make**: what a drag *means* on
a touch device, and how it coexists with a chip that is a button. The AC's chip list is
the contract, and it is met in full.

---

# Implementation Plan: The first settings routes — defaults, and a window that means something

**Work item**: `frontend-settings-reminders-and-quiet-hours` (the 11th)
**Routes**: `/settings/reminders` and `/settings/quiet-hours`
**Mode**: `confirm`

## The problem, in one paragraph

`notification-preferences-api` built `GET`/`PUT /api/settings/notifications` — one call
that returns the quiet window, the default reminder slots and the digest schedule
together. **Nothing calls it for its own sake.** The only caller today is the per-event
picker's *"Reset to default"*, and it keeps only the slot ids and throws the rest away.
So the user has a **server-side default they cannot see and cannot change**, and the
sidenav's Settings entry is an inert `<span>` that says *"Coming soon"* — on a product
whose own onboarding copy says *"You can change these later in Settings."*

These are the product's **first `/settings/*` routes**, and building them is what makes
that copy true.

## The three conflicts in the source documents, and how they are settled

### 1. "Inline save **with a spinner**" vs. "No spinners, anywhere"

**The work item's AC says** *"Inline save on change, with a spinner on the control being
saved — not a page-level Save button (EXPERIENCE.md §2 state table)."*

**`EXPERIENCE.md:80-81`** — the state table the AC cites — does say *"Inline save spinner
on chip change"* and *"Inline save spinner"* for these two routes.

**But `EXPERIENCE.md:546` says**, in a section headed for the whole product:

> **No spinners, anywhere.** PRD §13.1 and §13.2: "No urgency badges." A spinner is a
> visual urgency badge.

**And the architecture test enforces it.** `frontend/tests/architecture.test.ts` plants
`animate-spin` as a **must-fail** fixture: the scanner matches
`animate-[\w-]+|transition|duration|delay|ease` across every `.tsx` under `app/`,
`components/`, `lib/`, `styles/` and `tests/`. An animated spinner in a settings
component is a **red build**.

**The house pattern already resolves this.** `components/auth/submit-button.tsx` says it
outright:

> *"**There is no spinner.** The mockups draw one, and `EXPERIENCE.md` overrules them in
> the same breath… So the in-flight state is the form the spec itself specifies for
> reduced motion: a **static dot** beside the label."*

The implementation is `<span aria-hidden="true" className="h-2 w-2 rounded-full bg-current" />`
— a **static 8×8px dot**, plus `disabled` and `aria-busy` on the control, plus a label
that says what is happening.

**So the in-flight affordance is a static dot, not a spinner.** This satisfies the AC's
real requirement — *the control being saved shows that it is being saved* — without
breaking the architecture gate. The AC's word "spinner" and the spec's word "spinner"
both lose to the spec's later, stronger, product-wide rule and to the test that enforces
it. **The static dot is what "reduced motion renders instantly" already asks for**, so
the AC's own accessibility criterion is satisfied by the same choice.

### 2. The sidenav's Settings entry — **there are two rails**

The AC says *"the sidenav's Settings entry becomes a **real link** rather than an inert
label."* The sidenav is the **desktop** rail. There is also
`components/shell/bottom-tab-nav.tsx`, the **mobile** rail, and **its** Settings entry is
inert in exactly the same way — `<span aria-disabled="true">` plus an `sr-only` *"Coming
soon"*.

**Both become links.** Leaving the mobile one inert would mean that on a phone the
product says *"You can change these later in Settings"* and then Settings is a row that
does nothing. The work item is about the product's *first* settings routes; a route that
only exists on desktop is not a route.

### 3. "Reuse the onboarding time-preset control" — it is not a component yet

`components/onboarding/digest-step.tsx` holds the delivery-time control the AC names. It
is **not** an exported sub-component: the file is one flat `<div>` containing the time
input, the preset row **and** an unrelated timezone `<select>`, with the label *"Pulse
Digest delivery time"* hardcoded.

**So it is extracted.** A new `components/onboarding/digest-time-control.tsx` carries the
time input and the preset row, with `id` and `label` as props; `DigestStep` consumes it,
so the onboarding flow keeps working unchanged and the settings route gets **the same
control**, not a second copy of it.

**The timezone `<select>` stays out of the extraction.** It is a separate concern, the
digest zone is already set by the onboarding step, and the AC does not ask for it. The
settings route sends the zone it read back unchanged — the digest schedule's two fields
travel together, and the server refuses to half-apply them.

## The decisions

### 4. Two routes, no index page

`/settings/reminders` and `/settings/quiet-hours` are separate routes. There is **no
`/settings` index** — the work item says so, and `tests/digest-home-boundary.test.ts`
scans every shell file for the literal `href="/settings"` and forbids it.

**The sidenav's Settings link points at `/settings/reminders`**, and Settings is
**active on both routes** via a prefix rule, exactly as the Digest row is active on
every path under `/events/`. The prefix rule is the precedent, not an invention: the
Digest rule was widened the same way in the picker item.

**There is no in-page section nav.** The mockup's `settings-desktop.html` has a
single-page `.section-nav` with eight anchors. Eight anchors over a page that now has
two routes would be a lie about where the sections are; the sidenav is the nav, and the
two routes are reached through it.

### 5. The mockup's stale quiet window loses to the server's

The mockup draws the window as **10:00 PM – 7:00 AM** (`22:00`/`07:00`). The server's
default is `DEFAULT_QUIET_HOURS_START = time(22, 0)` and
`DEFAULT_QUIET_HOURS_END = time(8, 0)` — **22:00–08:00** — and the AC locks the label
**"10pm–8am. Nothing during this window."**

**The server and the AC win.** The mockup's `07:00` is stale, and a client that showed
`07:00` would show a window the server does not have.

### 6. The mockup's AM/PM button pair loses to `digest-step.tsx`

The mockup's `.time-row` draws an hour box, a minute box and an **AM/PM button**. The
onboarding control **explicitly rejected** that:

> *"The mockup draws an hour box, a minute box and an AM/PM pair. A native `type="time"`
> is one value, one control, and it is what a screen reader and a keyboard already know
> how to drive; three controls for one value is three chances to disagree with each
> other."*

**The extracted control keeps the native `<input type="time">` and the preset row.**
The AC's *"the time inputs are usable without a mouse"* is exactly what a native time
input gives, and what three spinners do not.

### 7. The default-plan chips **reuse `ReminderChip`**, with no deferred state

The AC says *"the same ink-inversion treatment as the per-event picker, **reusing that
component** rather than a second copy."* `ReminderChip` takes eight props and **no
context** — no target, no API — so it is reusable as it stands.

On `/settings/reminders` there is **no target event** and therefore **no deliveries**:
the settings payload carries `default_reminder_slots: string[]` and nothing per-slot. So
the chips are rendered with `deferred={false}` and `note={null}`.

**The four named tiers only.** The custom slot is a **per-event** feature — the AC names
four chips, and the mockup's default plan has no custom chip. The settings route does
**not** build the custom-slot input.

### 8. The non-retroactivity sentence is on the page, in plain words

The AC: *"It says plainly that it sets the default for **newly saved events** and does
not change plans already set — because the opposite is the natural assumption and getting
it wrong silently rewrites the user's choices."*

The server does not rewrite existing plans (`notification-preferences-api` proves it),
but **the user has to be told**, or the setting looks like it does something it does not.
The sentence is on the page, above the chips.

### 9. Inline save, one control at a time

The AC: *"Inline save on change, with a spinner on the control being saved — **not a
page-level Save button**."*

**So there is no Save button.** The chips save when the selection changes; the quiet
window saves when both times are valid; the delivery time saves when it changes.

**The save sends only the field that changed.** `NotificationSettingsIn` is a **patch**
and every field is optional: *"an omitted field is left alone"*. So a chip change sends
`{ default_reminder_slots: [...] }` and **not** the quiet window, and a window change
sends `{ quiet_hours: {...} }` and **not** the slots. This matters: the patch's
`quiet_hours` field is the one where `null` is a value (off) — so a payload that
re-sent the window on every chip change could **turn quiet hours off** by accident. The
server is right; the client must send the narrow patch.

**The chosen state is kept on failure.** Both routes keep the user's choice and show the
failure line — verbatim, and different for each route, as the AC specifies.

### 10. The per-day-of-week windows are **out of the markup entirely**

The AC: *"Per-day-of-week windows are Pro (FR-51) and out of scope. If a locked-row
affordance is shown at all it is a calm, non-nagging one; no upsell carousel, no
interstitial."*

**No locked rows at all.** The page says what the tier has — one window — and stops. A
locked row for a feature that does not exist on this tier would be a row the user can
neither use nor remove.

### 11. The Privacy section is not in the markup at all

The mockup's `settings-desktop.html` carries the entire Privacy section — the A-14 geo
toggle and the A-13 ranking amendment timeline, both belonging to a later intent. The
work item's technical note is explicit: *"leave those sections out of the markup
entirely rather than hiding them with `display:none` — the same rule Amendment A-12
locked for pre-auth CTA leakage."*

**Nothing from Privacy, Calendar sync, Account, Plan or Danger zone is rendered.** These
two routes carry only the two surfaces the work item names.

### 12. The authed-route guard follows `/conflicts`, not the picker

`/events/:id/reminders` renders an empty shell for an anonymous visitor, because the
Detail Screen is reachable without a session. **Settings are not.** `app/conflicts/page.tsx`
uses `homeRoute(session)` and `redirect()` — an anonymous visitor goes to `/preview`, a
half-onboarded one to `/onboarding` — and falls back to an error page for an unreadable
session.

**The settings routes use the same guard.** A settings surface that renders for someone
who is not signed in would offer to change a plan that is not theirs.

## The files

**New**

| File | What |
|------|------|
| `frontend/app/settings/reminders/page.tsx` | The default-plan route |
| `frontend/app/settings/reminders/loading.tsx` | Its skeleton |
| `frontend/app/settings/quiet-hours/page.tsx` | The window route |
| `frontend/app/settings/quiet-hours/loading.tsx` | Its skeleton |
| `frontend/components/settings/default-reminder-slots.tsx` | The chips island — inline save |
| `frontend/components/settings/quiet-hours-window.tsx` | The window island — inline save |
| `frontend/components/settings/digest-delivery-time.tsx` | The delivery-time island — inline save |
| `frontend/components/settings/settings-states.tsx` | The unreadable-settings state |
| `frontend/components/onboarding/digest-time-control.tsx` | **Extracted** from `digest-step.tsx` |
| `frontend/lib/notification-settings-read.ts` | The server-side read |
| `frontend/app/settings/reminders/page.test.tsx` | The route's tests |
| `frontend/app/settings/quiet-hours/page.test.tsx` | The route's tests |
| `frontend/tests/settings-a11y.test.tsx` | axe over every state |

**Modified**

| File | What changes |
|------|--------------|
| `frontend/components/shell/sidenav.tsx` | Settings becomes a link; active on `/settings/*` |
| `frontend/components/shell/bottom-tab-nav.tsx` | The mobile Settings slot becomes a link |
| `frontend/components/onboarding/digest-step.tsx` | Consumes the extracted control |
| `frontend/components/shell/nav-routes.test.tsx` | Settings is no longer inert |
| `frontend/app/page.test.tsx` | The same |
| `frontend/tests/ad19-endpoint-coverage.test.ts` | The `PUT /api/settings/notifications` endpoint |

**The four tests that will break, and what they become**

| Test | Becomes |
|------|---------|
| `nav-routes.test.tsx` — *"leaves the routes that do not exist inert"* | Browse stays inert; Settings leaves the list |
| `nav-routes.test.tsx` — *"keeps the routes that do not exist inert"* | The mobile Settings slot becomes a link |
| `app/page.test.tsx` — *"does not let an inert route navigate"* | Browse only |
| `digest-home-boundary.test.ts` — *"links nowhere that does not exist"* | Still passes: `href="/settings/reminders"` is not `href="/settings"` |

## The gates

Every gate the picker item ran, plus the spacing scale on the new files, plus
`axe-core` over **every** state of both routes.

---

# Implementation Plan: The proof — a quiet hour, a deferred reminder, a real send

## The problem, in one paragraph

Eleven items of the `delivery-and-reminders` intent were built and each was tested in
isolation. Every one of them passes. **And none of them has ever run the whole path.**
A quiet window that shifts a due time is tested by a domain test; a send key that stays
stable is tested by a key test; a suppression rule is tested by a rule test. The
**seams** — where the shift meets the mint, where the mint meets the sweep, where the
sweep meets the port, where the key meets the reschedule — are untested, and the seams
are where the failures live.

This item is the proof: **one scenario, run end to end, against the fake adapters,
asserting on what actually left the system.** The claim is narrow and checkable: *a user
sets a quiet window, saves an event whose reminder would land inside it, and the mail
arrives at the window's end — once, on the right stream, under the right key.*

## What this item is, and what it is not

**It is not a new feature.** Every behaviour it proves already exists. It is the
**evidence** that the behaviour exists, that it works *in composition*, and that the
tests pinning it can actually fail.

**The distinction matters because a proof that only re-runs the unit tests proves
nothing.** If the proof asserted the same facts the unit tests assert, in the same
units, it would pass exactly when the unit tests pass and add no information. So the
proof asserts on **the seam**: it walks the real path and checks the *end state* — what
the adapter received, what the database holds, what the user sees.

## The scenario, in the order it happens

```
1.  A user signs up, with a timezone and a city.
2.  They set a quiet window: 22:00 → 08:00, in their own zone.
3.  They save an event at Friday 23:30, with a 1-hour slot.
4.  The slot's instant is Friday 22:30 — inside the window.
5.  The mint shifts it. The row's due_at is Saturday 08:00.
6.  The sweep runs. It sends that row — and only that row.
7.  The adapter received exactly one message:
      - on the TRANSACTIONAL stream
      - under the event's send key
      - at Saturday 08:00 in the user's zone
```

**Step 5 is the claim.** Everything else is scaffolding. AD-7 says Quiet Hours are applied
"when `due_at` is **computed or recomputed**, deferring to the window end — never as a
skip at send time." The proof asserts the *stored* `due_at` is the window's end, and that
the sweep — which never consults the window — sends it at that time.

## The decisions

### The clock is frozen, never slept

The work item's Technical Note says it: *"Freeze the clock for the proof rather than
sleeping; the sweep takes `now` as an argument everywhere else in this project."*

**Every service in this path takes `now` explicitly.** `mint_for_plan(now=…)`,
`mint_ping_send(now=…)`, `sweep_due_sends(now=…)`, `apply_lifecycle_change(now=…)`. The
proof passes its own instant and never reads the wall clock. **A proof that sleeps is a
proof that is slow, flaky, and wrong on a loaded machine** — and it is also the proof
whose result depends on the hour it ran, which is the exact defect item 11 found in the
backend's own digest tests.

**The frozen instant is chosen, not arbitrary.** Friday 2026-11-06 23:30 in
`America/Los_Angeles` is a slot instant *inside* the window, and the expected send is
Saturday 2026-11-07 08:00 local. **Both sides of midnight are in the scenario on purpose:**
a window that crosses midnight is the default window, and testing it at 23:30 proves the
"evening side defers to tomorrow" branch rather than the trivial one.

### The assertion surface is the memory adapter — and it already records everything

The work item's Technical Note anticipated this: *"The memory email adapter is the
assertion surface. If it does not yet record stream and idempotency key per message,
extending it belongs to `delivery-sweep-and-send`, not here."*

**It already records everything.** `InMemoryEmailAdapter.sent` is a list of `SentEmail`
— `message`, `stream`, `idempotency_key`. **No adapter change is needed**, and making
one would be a brownfield change outside this item's scope.

### The proof calls the services, not HTTP — with one exception

The HTTP stack is proved by **run 022's** timeline/conflict proof, which drives the real
router. This proof is about the **delivery path**, and the delivery path's boundary is
the service layer: the sweep, the mint, the shift.

**But the unsubscribe proof goes through HTTP**, because the AC says *"one-click
unsubscribe"* and one-click unsubscribe is an HTTP contract — RFC 8058's `List-Unsubscribe`
one-click is a `POST` with a form body, and that is not a thing a service call proves.

### The AD-17 propagation proof calls the service, and records the deviation

`worker.tasks.propagate_state_change` is a **placeholder** — it does nothing, and the
delivery half (`scheduled_sends.apply_lifecycle_change`) is **not wired to it**. The
task was built that way on purpose (the worker does not yet own the propagation loop).

**So the propagation proof calls `apply_lifecycle_change` directly**, and the deviation is
recorded in the test report. **A proof that calls a placeholder proves nothing** — the
placeholder would pass every assertion.

### The frontend half is a contract test, not a browser test

The AC says: *"set quiet hours in `/settings/quiet-hours`, open `/events/:id/reminders`,
and see the affected chip rendered dim with its 'Will deliver at …' tooltip — proving the
server-computed flag reaches the UI."*

**There is no browser in this stack** — the frontend's e2e proof in run 020 drove the HTTP
API from Python. So the frontend half is proved where the flag actually lives:

- the **server** computes the flag (`reminder_plan_read.compute_deliveries` → `SlotDelivery.deferred`),
- the **client** renders it (`reminder-chip.tsx` → the dimmed treatment and the tooltip).

**The seam between them is the API's JSON.** So the proof asserts that the server's
`deferred` flag arrives in the response body, and that the client component renders the
dimmed chip and the tooltip when that flag is `true`. **Both halves are asserted; neither
is asserted by the other.** A flag that the server computes but the client ignores would
pass both halves, so the client half is a **component test** driven by the flag, and the
server half is an **API test** driven by a real quiet window.

## The eight proofs, and what each one is really asking

| The proof | The claim | The seam it crosses |
|-----------|----------|----------------------|
| **Deferral** | The mail arrives at the window's end, once, transactional, under the right key | quiet hours → mint → sweep → port |
| **Pulse Ping** | One BULK message with an unsubscribe URL and the key `user · digest · local_date` | composition → ping → mint_digest → sweep → port |
| **Suppression** | Zero qualifying events → **no row minted**, no message, and the suppression is recorded | composition → pulse_ping's decision |
| **Personal-only** | One personal event → the Ping **does** go out | the `OR` in FR-10's rule |
| **Reschedule** | Changing the window moves `due_at`, the key is **byte-identical**, and **no second row** exists — ten times over | preference → reschedule → the key |
| **Propagation** | Old pending rows cancelled, new ones minted with a bumped version, a `sent` row for the old date does not block the new one | AD-17's lifecycle change |
| **Unsubscribe** | One-click unsubscribe cancels that event's reminders and **leaves the Ping alone** | the token, the two scopes |
| **Idempotency** | The sweep run twice over one due row → the provider saw **one** send | the send key at the boundary |

**The one that matters most is the reschedule proof, and the reason is the key.**
Four ordinary user actions rewrite `due_at` on pending rows — quiet hours, timezone,
delivery time, a plan edit. **If the key moved with the time, each would mint a second
send.** The proof changes the window **ten times** and asserts **one row** with a
**byte-identical** key every time. Ten, not one, because the first change is the easy
case and the tenth is where an accumulating off-by-one would show.

## The probe harness: each proof is proven able to fail

The AC demands: *"Probe tests: as run 021 did with its 27 probes, each major assertion is
proven able to fail — break the quiet-hours shift, the key stability and the suppression
rule in turn, and show the matching test goes red."*

**The harness is `tests/e2e/mutation_probe_contract_e2e.py`'s, reused in the same shape:**
a `Probe` dataclass, literal-text edits, a per-probe suite, and a `finally` that restores
the file unconditionally.

**Three rules run-021 learned, and this item inherits them:**

1. **Plant a CALL, not an import.** An imported-but-uncalled function computes nothing.
2. **The mutation must still parse and run.** A `SyntaxError` is a *false green* — the
   suite "caught" it because it could not be collected.
3. **Never plant a bug in dead code.** A probe that mutates a branch the scenario never
   runs proves nothing — run-021's probe 10 hit exactly that and had to be rewritten.

**The three the AC names, and the mutation for each:**

| The rule | The mutation | The suite that must go red |
|---------|--------------|-----------------------------|
| The quiet-hours shift | `shift_to_sendable` returns the instant unchanged | the deferral proof |
| The key's stability | `reschedule_pending_for_user` re-mints instead of rewriting | the reschedule proof |
| The suppression rule | `mint_ping_send` mints even with nothing qualifying | the suppression proof |

**And two more this item adds, because the AC says *each major assertion*:**

| The rule | The mutation | The suite that must go red |
|---------|--------------|-----------------------------|
| The sweep sends once | the send key stops deduping at the boundary | the idempotency proof |
| The unsubscribe's scope | the event unsubscribe also cancels the Ping | the unsubscribe proof |

**The probe file is not a test** — it is a script that runs other suites, and it is
excluded from the normal pytest run the way run-021's was. It is run explicitly, and its
output is recorded in the run log.

## The contract tests

### The import contracts still hold, including `models-delivery`

`models-delivery` already exists and already covers `ScheduledSend` — it is a
**package-level** contract (`apps.delivery.models`), so every model in it is covered
automatically.

**But the contract's *breaking* is not proven.** `test_import_contracts.py` has a
`VIOLATIONS` dict of planted violations and their expected broken-contract sets, and
**`models-delivery` has no entry.** So the contract exists and is enforced, but nothing
shows it *can* break. **The AC asks for the extended `models-delivery` for
`ScheduledSend`** — and the way to satisfy that is to plant a violation that breaks it and
assert the exact set of contracts that break.

**The planted violation is `delivery` reaching another app's models** — which the AC
names explicitly: *"`delivery` never imports `apps.ingestion.models` or
`apps.personalization.models`."*

### `make client` is the contract

The generated client is regenerated for every new endpoint, and CI's diff check passes.
**This item adds no endpoint**, so the check is a *gate*, not a change: `make client` must
produce no diff.

## Files to create

| File | What it is |
|------|-----------|
| `backend/tests/e2e/test_delivery_proof.py` | The eight backend proofs — one scenario, one user, one database |
| `backend/tests/e2e/test_delivery_contract.py` | The contract proofs — the import contracts, the `models-delivery` violation, the client diff |
| `backend/tests/e2e/mutation_probe_delivery_e2e.py` | The probe harness — five probes, each proven able to fail |

## Files to modify

| File | What changes |
|------|--------------|
| `backend/tests/architecture/test_import_contracts.py` | The `models-delivery` entry in the `VIOLATIONS` map |
| `frontend/components/reminders/reminder-chip.test.tsx` (new) | The frontend half — the dimmed chip and the tooltip, driven by the flag |

## The gates

| Gate | Why |
|------|-----|
| `uv run pytest` | The whole backend suite, including the eight proofs |
| `uv run ruff check .` / `uv run ruff format --check .` | The probe file is Python and must lint |
| `coverage report --include='domain/*' --fail-under=100` | The domain's rules are exercised, and the proof must not lower it |
| `make lint-backend` | The import contracts still hold |
| `pnpm test` | The frontend half |
| `pnpm lint` / `pnpm typecheck` / `pnpm format:check` | The frontend gates |
| `pnpm build` | The build is a different gate from the test suite, and item 11 proved it |
| `make client` + a clean diff | The generated client is the contract |

## What this item deliberately does not do

- **It does not wire `propagate_state_change` to the delivery half.** That is the
  worker's job and belongs to a work item about the worker. The deviation is recorded.
- **It does not add an endpoint.** The proof reuses the API that item 9 built.
- **It does not add a browser.** There is no browser in this stack, and adding one would
  be a different kind of work.
- **It does not change the memory adapter.** It already records what the proof asserts.
