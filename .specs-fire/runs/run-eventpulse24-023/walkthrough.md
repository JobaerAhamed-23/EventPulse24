---
run: run-eventpulse24-023
scope: wide
work_items:
  - quiet-hours-domain
  - notification-preferences
  - scheduled-send-model
  - send-minting-and-rescheduling
  - delivery-sweep-and-send
  - email-templates-and-unsubscribe
  - pulse-ping-and-suppression
  - reminder-plan-api
  - notification-preferences-api
  - frontend-reminder-picker
  - frontend-settings-reminders-and-quiet-hours
  - e2e-proof-and-contract-tests
intent: delivery-and-reminders
generated: 2026-11-01T08:46:50Z
mode: wide (confirm and validate per item)
---

# Implementation Walkthrough: Delivery and Reminders — the whole path, from a quiet window to the mail

## Summary

This run built **the delivery and reminders path end to end** — twelve work items that
between them turn "the user set a quiet window and saved an event" into "the mail
arrives at the window's end, once, on the right stream, under a stable key."

**Before this run the tree could not send anything.** It had every shape a send needs
and no one to put them together: a quiet-hours domain, a notification-preference model,
a `ScheduledSend` row, a digest that could be composed into the void. **Nothing minted
a reminder. Nothing swept one. Nothing sent one.**

**Now it does, and the path is proved.** A deferred slot lands at the window's **end**,
not at its own instant and not tomorrow. The idempotency key carries **no instant
anywhere**, so changing the window cannot move it and cannot mint a second row. The
sweep marks a row sent and does not consult the window at all. The daily Pulse Ping is
minted **only** when there is something to say, and its silence is counted with its
reason. The frontend renders the server's `deferred` flag and **does not recompute it**.

**The proof is the point.** The run's last item is one frozen scenario — a user in Los
Angeles, a 22:00–08:00 window, an event at Friday 23:30 — walked end to end against
the **real services**, plus **six mutation probes** proving each major assertion is
**able to fail**, plus nine contract proofs for the things that would let the path work
*by accident*.

**The totals:** backend **4763 tests passing** at **99.19%** coverage (**100%** on
`domain/*`), frontend **80 files / 1150 tests**, import contracts **19 kept / 0
broken**, **6 of 6** probes caught.

## Structure Overview

**The run is a vertical slice, not a layer.** Each work item took one *capability* from
the user's sentence and carried it all the way down — the model, the service, the API,
the screen, the proof — so that at the end of the run there is a **path** rather than
twelve components.

```text
        the user's sentence
  "set a quiet window, save an event,
   and the mail arrives at the window's end"
                            │
  ┌─────────────────────────┴──────────────────────────┐
  │                                                      │
  ▼                                                      ▼
  DOMAIN (pure, stdlib only)                    PREFERENCES (the app's rows)
  domain/quiet_hours.py                         apps/delivery/models.py
  domain/horizon.py                             · NotificationPreference
  · shift_to_sendable()                           · ReminderPlan
  · covers()                                    · ScheduledSend
  · the window's edges                          · the one row that is a promise
  · the 48-hour horizon
                                                    │
                                                    ▼
                              SERVICES (apps/delivery/services)
                              · notification_preferences  — the window, written
                              · scheduled_sends           — the key, minted once
                              · slots / reminder_plan_read — what will be sent, and when
                              · delivery_messages         — the rendered message
                              · delivery_sweep            — the claim, the send, the mark
                              · pulse_ping                — the daily Ping, and the silence
                              · unsubscribes              — the scope of "stop"
                              · email_templates           — the bodies
                                                    │
                             ┌──────────────────────┴──────────────────────┐
                             ▼                                             ▼
                        ADAPTERS (ports)                              API (apps/delivery/api.py)
                        · email memory / smtp                         · preferences in/out
                        · the assertion surface                       · reminder plans
                                                                  · unsubscribe
                             │                                             │
                             └──────────────────────┬──────────────────────┘
                                                    ▼
                                          FRONTEND (Next.js)
                                          · /events/:id/reminders — the picker
                                          · /settings/reminders — the slots
                                          · /settings/quiet-hours — the window
                                          · ReminderChip — the server's flag
```

**The two rules that shaped everything.**

**AD-7 — Quiet Hours are applied when `due_at` is computed, never at send time.** The
shift lives in `domain/quiet_hours.py` and is called by the *minting* path. **The sweep
never imports it.** A send deferred twice is a send that never leaves; a send skipped at
send time is a send the user never gets. So the window moves the **promise**, and the
sweeper only ever asks *"is this row due?"*

**AD-7 — the key carries no instant.** `user_id · kind · target · slot · version`,
joined with `:`. **Not the due time.** This is what makes a quiet-hours change, a
timezone change, a delivery-time change, or a plan edit *safe*: they rewrite `due_at`
and **never** the key. A key that moved with the time would mint a second send for every
settings change, and a user who adjusted their settings three times would get four
copies of one reminder.

## Architecture

### Pattern Used

**Service Layer over a pure domain, with ports at the boundary.** This is the
project's existing spine (AD-1/AD-2), not a new pattern introduced here:

- **`domain/` is pure.** `quiet_hours.py` and `horizon.py` import the stdlib and
  `shared.constants` — nothing else. **No Django, no database, no models.** The
  shift's rules are the kind that get *rediscovered* in each place they are needed, and
  DST is the classic way to rediscover them wrongly. So they live once.
- **`apps/` owns the writes.** Every row is minted by a named command in
  `apps/delivery/services/`, and every command takes an explicit `Actor`.
- **`ports/` is the boundary.** The email port is an ABC over frozen dataclasses, and
  `InMemoryEmailAdapter` is the assertion surface. **Tests fake at the port and never
  mock the ORM.**
- **`config` wires, `worker` drives.** The Celery task calls the same
  `sweep_due_sends` the proof calls.

### Layer Structure

```text
┌──────────────────────────────────────────────────────────────┐
│  PRESENTATION — apps/delivery/api.py · Next.js routes        │
│  validate, enqueue, return — never write                     │
├──────────────────────────────────────────────────────────────┤
│  APPLICATION — apps/delivery/services/ · apps/personalization│
│  named commands, explicit actors, both schemas                │
├──────────────────────────────────────────────────────────────┤
│  DOMAIN — domain/quiet_hours.py · domain/horizon.py         │
│  stdlib only · no Django · no models · 100% covered          │
├──────────────────────────────────────────────────────────────┤
│  PORTS — ports/email.py · ports/registry.py                  │
│  ABCs over frozen dataclasses · the fakeable boundary        │
├──────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE — adapters/email/ · adapters/logging/        │
│  memory · smtp · the redaction allowlist                      │
└──────────────────────────────────────────────────────────────┘
```

### The sweep, in one paragraph

`sweep_due_sends` claims the due rows (`FOR UPDATE SKIP LOCKED`), renders each through
`renderer_for`, resolves the recipient, and calls `port.send(message, stream=…,
idempotency_key=…)`. **It then marks the row sent, in the same transaction.** It never
consults the quiet window — a deferred row is *already* deferred, because the shift
happened when the row was minted. It never mints. It never skips. **Its whole job is
"is this row due, and did it go?"**

## Files Changed

### Created — Backend

| File | Purpose |
|------|---------|
| `backend/domain/quiet_hours.py` | **The window.** `covers()`, `shift_to_sendable()` — the shift to the window's end, across midnight, in the user's own zone |
| `backend/domain/horizon.py` | The 48-hour qualifying horizon, shared by the Ping and the picker |
| `backend/apps/delivery/send_keys.py` | **The key.** One place that joins `user · kind · target · slot · version` with `:` — and nothing else |
| `backend/apps/delivery/services/notification_preferences.py` | Writing the window and the settings — one command, one actor |
| `backend/apps/delivery/services/preferences.py` | Reading the preferences for a user |
| `backend/apps/delivery/services/preferences_read.py` | The read model behind the settings screen |
| `backend/apps/delivery/services/slots.py` | The slot vocabulary — `5d`, `2d`, `1d`, `1hr`, `custom:<minutes>` |
| `backend/apps/delivery/services/scheduled_sends.py` | **The minting.** `mint_for_plan`, `reschedule_pending_for_user`, `apply_lifecycle_change` — and the rule that a rewrite never touches the key |
| `backend/apps/delivery/services/reminder_plan_read.py` | `compute_deliveries` — what will be sent, when, and **whether it is deferred**. The server's half of the frontend's flag |
| `backend/apps/delivery/services/delivery_messages.py` | The rendered message and the renderer lookup |
| `backend/apps/delivery/services/delivery_sweep.py` | **The sweep.** Claim, send, mark. Never consults the window; never mints |
| `backend/apps/delivery/services/pulse_ping.py` | **The Ping, and the silence.** FR-10's check, one row per local date, and a counted reason for every suppression |
| `backend/apps/delivery/services/email_templates.py` | The bodies, per kind |
| `backend/apps/delivery/services/unsubscribes.py` | **The scope.** One event's reminders — and *not* the Ping |
| `backend/apps/delivery/services/unsubscribe_tokens.py` | The signed, single-purpose unsubscribe token |
| `backend/apps/delivery/email_api.py` | The unsubscribe endpoint |
| `backend/apps/delivery/preferences_api.py` | The preferences endpoints |
| `backend/apps/delivery/templates/` | The email templates |
| `backend/apps/identity/services/recipients.py` | Resolving a user id to a recipient address |

### Created — Backend migrations

| File | Purpose |
|------|---------|
| `backend/apps/delivery/migrations/0002_notificationpreference.py` | The user's window and delivery settings |
| `backend/apps/delivery/migrations/0003_scheduledsend.py` | The promise |
| `backend/apps/delivery/migrations/0004_notificationpreference_ping_unsubscribed.py` | The Ping's own opt-out |
| `backend/apps/delivery/migrations/0005_scheduledsend_slot_at.py` | The slot's own instant, distinct from `due_at` |

### Created — Frontend

| File | Purpose |
|------|---------|
| `frontend/lib/reminder-slots.ts` | The slot vocabulary, read from the server's shapes |
| `frontend/lib/reminder-plan-read.ts` | Reading the plan and the deliveries |
| `frontend/lib/notification-settings.ts` | The settings write path — **islands, not a whole surface** |
| `frontend/lib/notification-settings-read.ts` | The settings read path |
| `frontend/components/reminders/reminder-chip.tsx` | **The chip.** The server's flag, applied. Never recomputed |
| `frontend/components/reminders/reminder-picker.tsx` | The picker |
| `frontend/components/reminders/reminder-states.tsx` | The picker's empty and error states |
| `frontend/components/reminders/reminder-chip.test.tsx` | The frontend half of the deferred-flag proof |
| `frontend/components/reminders/reminder-picker.test.tsx` | The picker's tests |
| `frontend/components/detail/detail-reminder-link.tsx` | The link into the picker |
| `frontend/components/onboarding/digest-time-control.tsx` | The extracted time control — **shared, not copied** |
| `frontend/components/settings/default-reminder-slots.tsx` | The slots island |
| `frontend/components/settings/digest-delivery-time.tsx` | The delivery-time island |
| `frontend/components/settings/quiet-hours-window.tsx` | The window island |
| `frontend/components/settings/save-feedback.tsx` | The save state |
| `frontend/components/settings/save-failure.ts` | The failure copy |
| `frontend/components/settings/settings-states.tsx` | The settings' empty and error states |
| `frontend/components/settings/settings-inline-save.test.tsx` | The island save's tests |
| `frontend/app/events/[id]/reminders/page.tsx` | `/events/:id/reminders` |
| `frontend/app/events/[id]/reminders/page.test.tsx` | Its tests |
| `frontend/app/events/[id]/reminders/loading.tsx` | Its loading state |
| `frontend/app/settings/reminders/` | `/settings/reminders` |
| `frontend/app/settings/quiet-hours/` | `/settings/quiet-hours` |
| `frontend/tests/reminder-picker-a11y.test.tsx` | The axe-core gate on the picker |

### Created — Tests

| File | Purpose |
|------|---------|
| `backend/tests/domain/test_quiet_hours.py` | The window, in isolation — no Django |
| `backend/tests/domain/test_horizon.py` | The horizon, in isolation |
| `backend/tests/delivery/test_*.py` (17 files) | Each service's own contract |
| `backend/tests/identity/test_recipients.py` | The recipient resolution |
| `backend/tests/worker/test_sweep_tasks.py` | The Celery task |
| `backend/tests/architecture/test_schedule_writes.py` | No surface writes directly |
| `backend/tests/e2e/test_delivery_proof.py` | **The proof** — one frozen scenario, 13 assertions |
| `backend/tests/e2e/test_delivery_contract.py` | **The contracts** — 9 proofs |
| `backend/tests/e2e/mutation_probe_delivery_e2e.py` | **The six probes** — each major assertion, proven able to fail |

### Modified

| File | Changes |
|------|---------|
| `backend/apps/delivery/models.py` | `NotificationPreference`, `ReminderPlan`, `ScheduledSend` |
| `backend/apps/delivery/schemas.py` | The API's shapes |
| `backend/apps/delivery/api.py` | The routes |
| `backend/apps/delivery/services/__init__.py` | The published interface |
| `backend/apps/delivery/services/reminder_plans.py` | The plan writes |
| `backend/apps/identity/services/__init__.py` | The published interface |
| `backend/apps/personalization/services/digest_preferences.py` | The preferences moved to `delivery`'s ownership |
| `backend/apps/personalization/services/digest_candidates.py` | The qualifying horizon |
| `backend/apps/personalization/services/digest_composition.py` | The composition |
| `backend/apps/personalization/services/saved_events.py` | The save |
| `backend/config/api.py` | The routers |
| `backend/config/management/commands/compose_digest.py` | The command |
| `backend/worker/tasks.py` | The sweep task and the house clock seam |
| `backend/domain/errors.py` | The new domain errors |
| `backend/shared/constants.py` | The defaults — the window's edges, the slots |
| `backend/adapters/logging/redaction.py` | The allowlist |
| `backend/tests/architecture/test_import_contracts.py` | **The `models-delivery` violation case** — proving the contract can break |
| `backend/tests/architecture/test_write_ownership.py` | The ownership rules |
| `backend/tests/architecture/test_ad13_pii_sweep.py` | The PII sweep |
| `backend/tests/architecture/test_digest_composition_separation.py` | The separation |
| `backend/tests/delivery/factories.py` | The factories |
| `backend/tests/delivery/test_reminder_plans.py` | The plan tests |
| `backend/tests/personalization/test_*.py` (3 files) | The moved preferences |
| `backend/tests/worker/test_digest_tasks.py` | The digest task |
| `backend/tests/worker/test_scheduling_tasks.py` | The scheduling task |
| `frontend/app/page.tsx` · `frontend/app/page.test.tsx` | The home surface |
| `frontend/app/events/[id]/page.tsx` · `page.test.tsx` | The event page |
| `frontend/components/detail/detail-reminder.tsx` | **Deleted** — replaced by `detail-reminder-link.tsx` |
| `frontend/components/onboarding/digest-step.tsx` | Now uses the extracted time control |
| `frontend/components/shell/bottom-tab-nav.tsx` · `sidenav.tsx` · `nav-routes.test.tsx` | The Settings entry in both rails |
| `frontend/lib/api/openapi.json` · `schema.ts` | **Generated** — never hand-edited |
| `frontend/tests/ad19-endpoint-coverage.test.ts` | The endpoint coverage |
| `frontend/tests/architecture.test.ts` | **The server/client boundary rule** — added, with four tests |
| `frontend/lib/api/` | The generated client |

## Domain Model

### Entities

| Entity | Properties | Business Rules |
|--------|------------|----------------|
| **`NotificationPreference`** | `user_id`, `timezone`, `quiet_hours` (start/end), `digest_delivery_time`, `default_reminder_slots`, `ping_unsubscribed`, `city`, `city_source` | The window's edges are local to the user's zone. **`city_source` is required** — a city without saying how it was found is a row nobody can interpret. The Ping's opt-out is its own column, so unsubscribing from one event's reminders cannot turn off the Ping |
| **`ReminderPlan`** | `user_id`, `target_kind`, `target_id`, `slots`, `event_version` | **One plan per (user, target).** The slots are the user's choices, and `slots == []` is a real state — "this event has no reminders" — which is what the event-scoped unsubscribe writes |
| **`ScheduledSend`** | `user_id`, `kind`, `target_kind`, `target_id`, `slot`, `event_version`, `stream`, `slot_at`, `due_at`, `send_key`, `status` | **`send_key` is minted once and never rewritten.** `slot_at` is the instant the slot *names*; `due_at` is the instant it will *go* — and Quiet Hours is the difference between them. A row's `status` is a **fact** once it is `sent`, not a schedule. `due_at` is the only thing a settings change rewrites |

### Value Objects

| Value Object | Properties | Constraints |
|--------------|------------|--------------|
| **`QuietHours`** | `start: time`, `end: time` | **May wrap midnight** — the default 22:00→08:00 does. `covers()` must be true on **both** sides of midnight. `start == end` means the window is off, not "always" |
| **`SendTarget`** | `target_kind`, `target_id`, `start_utc`, `version`, `catalog_event_id` | The thing being reminded about, and **the version** it was at — because a moved event is a *different* send |
| **`SendKey`** | the joined parts | Joined with `shared.constants.SEND_KEY_SEPARATOR` (`:`) — **never `-` or `_`**, so each UUID stays a 36-character run and the key survives log scrubbing. **Contains no instant** |
| **`Stream`** | `TRANSACTIONAL` \| `BULK` | `stream` is **keyword-only with no default** on `EmailPort.send`. **Bulk requires an `unsubscribe_url`** (RFC 8058). A send without a stream is refused at the port |

## Key Implementation Details

### 1. The shift, and the fact that the sweep never applies it

**The window is a pure function of an instant and the user's zone.**

```text
shift_to_sendable(instant, window, zone)
    → if the local clock is inside the window: the window's end, on the next occurrence
    → otherwise: the instant, unchanged
```

**The two things that make it right.** The window's end is computed **in the user's
zone** and then converted to UTC — never by adding eight hours to a UTC timestamp,
which is the bug that DST produces. And the end is the **next occurrence** of that
clock time: an instant at Friday 22:30 shifts to **Saturday** 08:00, not to Friday
08:00, which is in the past.

**And it is called in exactly one place: the minting path.** `delivery_sweep.py` does
**not** import `domain.quiet_hours` — and the contract test asserts that by reading the
module's **import lines**, because the module's own docstring names the module precisely
to record that the import is *absent*, and a search for the word would match the very
sentence that explains the rule.

**An import cannot lie.** If the module does not import the shift, it cannot consult the
window, whatever else it does.

### 2. The key, and why it has no instant in it

**The key identifies the thing being sent, not when it goes.**

```text
user_id : kind : target_id : slot : version
```

**Every part of that is a fact about the *thing*.** `due_at` is not a fact about the
thing — it is a fact about *the schedule*, and the schedule changes. **A key that
carried the due time would be a new key every time the user touched their settings.**

**So the rewrite is one operation:** change `due_at`, leave `send_key` alone. The proof
makes **ten** window changes and asserts that there is still **one** row and that its
key is **byte-identical** — not merely equal, because "equal" would hide a key that was
rebuilt from the same parts in a different order.

**And the mutation probe is the one that matters.** It plants the real bug: the
rewrite *also* mints a second row, under a key with `:rescheduled` appended. **The user
gets two reminders for one event**, and the second one is under a key the provider has
never seen.

### 3. The sweep, and what it is allowed to do

**The sweep has exactly three jobs:** find the due rows, send them, mark them sent.
**It does not mint. It does not skip. It does not consult the window.**

**The marking is the load-bearing part.** A row that says `pending` after a successful
send is a promise the sweep did not keep, and the next sweep would try again — the
provider would see two messages under the same key, and only the provider's own dedup
would stand between the user and a duplicate email.

**So probe 4 removes the `_mark_sent` call**, and the proof catches it. **The mutation
is on the write, not on the key** — the key is *supposed* to be the same on both runs,
because that is the point. What must not happen is the sweep sending the row twice in
the first place.

**And the concurrency is real.** `test_delivery_sweep_concurrency.py` runs two workers
over the same row; the claim is `FOR UPDATE SKIP LOCKED`, so one of them gets it.

### 4. The Ping, and the silence that earns it

**FR-10's rule:** *"3 qualifying events → exactly 1 Pulse Ping, not 3."* The key
`user_id : digest : local_date` makes that true **by construction** rather than by a
count — the key is a **calendar day**, not an instant, so the second qualifying event
mints nothing new.

**And when there is nothing to say, there is no row.** Not a row that is later skipped.
**A `pending` row that is never sent is indistinguishable from a bug**, and AD-7's whole
premise is that a `pending` row is a promise. **The silence has to be *the absence of
the row*.**

**Every silence is counted with its reason** — in a structured log line and in an
audit row — so SM-C1's "≥30% suppression rate" target is measurable from day one. **A
product that cannot say *why* it stayed quiet cannot tell its own intelligence apart
from a broken pipe.**

### 5. The unsubscribe's scope

**FR-11's explicit requirement:** unsubscribing from **one event's** reminders leaves
the daily Ping alone. **The distinction is the whole point**, and it is the one thing
that is easy to get backwards — a single unsubscribe that turned off the daily digest
would be a surprise the user cannot undo.

**So the event scope cancels the event's pending rows and clears the plan's slots, and
touches nothing else.** The Ping is a different `kind` on a different target.

**Probe 5 plants the real bug** — the event scope also cancels the user's pending
digests — and the proof catches it because the DIGEST row is asserted to survive.

### 6. The server's flag, and why the client does not recompute it

**The picker needs to know which slots will be deferred.** The server computes it —
`compute_deliveries` returns each delivery with `deferred` and `deferred_to` — because
**the window is a server-side fact**, expressed in the user's zone, and reimplementing
it in TypeScript would be a **second implementation of the shift**, with DST and
midnight rediscovered there. **The two could disagree about the very instant the email
goes out at.**

**So the chip takes `deferred` and `note` as props and renders them.** It does not
import the window; it does not know what a window is.

**And the flag's journey has two halves, and neither half proves the other.** The
server's half is the backend proof; the client's half is the component test. A flag
the server computes but the client ignores would pass both halves on their own, and a
chip that dims on a flag nobody sends would too.

**Which is why probe 6 exists.** It is the **only** probe that could catch a client
that ignores the flag — every backend probe and every server-side assertion would stay
green. **It is a frontend mutation, caught by a frontend test**, because running the
backend suite against a frontend mutation would prove nothing.

### 7. The proof itself, and the two instants

**The scenario is one test, one user, one database, and one transaction's worth of
shared state** — because the failures that matter live in the *seams*. A chain of
independent tests proves each step and not the whole: a due time shifted in one test
and swept in another is not the same send.

**The clock is frozen, never slept.** Every service on the path takes `now` as an
argument, and the sweep's `now` is a parameter. **No test sleeps**, and **no test's
answer depends on the hour it ran in** — the defect item 11 found in the backend's own
digest tests.

**And the two rows are due at different instants.** The reminder's send time is the
quiet window's **end** — 08:00 — because its slot was *inside* the window and was
moved. The Ping's send time is the user's **delivery time** — 09:00 — because 09:00
was outside the window and **nothing moved it**.

**That difference is the whole reason the constants are separate.** A proof that swept
at one instant would have found the other row not yet due, and would have read that as
a bug. **The difference between them is the difference between *a slot that moved* and
*a digest that never moved*.**

## Security Considerations

| Concern | Approach |
|---------|----------|
| **A bulk send without an unsubscribe path** | **Refused at the port.** `EmailPort.send` requires `unsubscribe_url` on `Stream.BULK` (RFC 8058) and takes `stream` as **keyword-only with no default** — so a send without an explicit stream is refused, not defaulted |
| **An unsubscribe that reaches another user's rows** | The token is **signed and single-purpose** — it carries the target, not a query parameter a user can edit |
| **Email addresses in the logs** | The allowlist (`adapters/logging/redaction.py`) keeps ids, counts, durations and slugs. **Email addresses, names, titles, tokens and ICS URLs are never allowed**, and `test_ad13_pii_sweep.py` scans for them |
| **The delivery path reaching the network** | **Only `adapters.crawl` may import an HTTP client** — the `http-client` import contract. And the contract test scans the six delivery-path modules for `httpx`/`requests`/`urllib`/`http.client` **by source**, because a module that imported one and never called it would still be a path that *could* reach the network |
| **The quiet window being a way to be notified *later* than the user expects** | The window's edges are **visible on the screen** and in the chip's accessible name — the user is told, not surprised |
| **The proof leaking real data** | **No real user data, no PII.** The user is `maya@example.test` on a reserved domain, and the "recipient" is a synthetic address |
| **A signed token leaking into a log** | The allowlist does not permit free text, so a token in a log field is redacted rather than written |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| **The sweep must not send the same row twice under concurrency** | `FOR UPDATE SKIP LOCKED` on the claim — a second worker skips the locked row rather than waiting for it. `test_delivery_sweep_concurrency.py` runs two workers over one row |
| **The sweep must not scan the whole table** | The claim is over the **due** rows only, and `due_at` is the indexed column the sweep orders by |
| **Changing a user's settings must not rewrite the world** | The rewrite is scoped to the user's **pending** rows — a sent row is a fact, not a schedule, and is never touched |
| **The Ping must be one row per day, not one per event** | The key is `user : digest : local_date` — the row is **mint-once per day** by construction, so the count of qualifying events does not affect the number of rows |
| **The picker must not need the whole plan** | `compute_deliveries` takes the slots and the window and returns the deliveries — **no per-slot round trip** |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Where the shift lives** | `domain/quiet_hours.py`, pure | The window's rules are the kind that get rediscovered in each place they are needed, and DST is the classic way to rediscover them wrongly. **One implementation, 100% covered, no Django** |
| **When the shift is applied** | At minting and at rewriting — **never at send time** | AD-7's own words. A send skipped at send time is a send the user never gets |
| **What the key contains** | `user · kind · target · slot · version` — **no instant** | A key carrying the due time is a new key per settings change, and the user gets a copy per change |
| **What the sweep is allowed to know** | The due rows and nothing about the window | The sweep's `import` list is the enforcement, and the contract test reads the import lines |
| **The assertion surface** | The **memory email adapter**, injected by name | It already records `message`, `stream` and `idempotency_key` — so **the adapter was not changed**, exactly as the work item's Technical Note required |
| **The proof's layer** | The **services**, not the HTTP surface | The rules live in the services, and an HTTP surface would add a transport failure mode without adding a rule |
| **The proof's two instants** | The reminder at **08:00**, the Ping at **09:00** | The reminder was deferred to the window's end; the Ping was not moved and is due at the user's delivery time |
| **The client-sync check** | **Regenerate, compare, restore** | `schema.ts` is uncommitted work from an earlier item, so a `git diff` compares against the last commit, not against what the generator produces. **The test is a measurement, not a rewrite** |
| **The settings write path** | **Islands, not a whole surface** | `quiet_hours` is the one field where `null` is a value — it turns the window *off*. A payload that re-sent the whole settings surface on every window change would rewrite the user's default plan by accident |
| **The AD-17 seam** | Call `apply_lifecycle_change` **directly** | `propagate_state_change` is a deliberate placeholder. The proof asserts the rule at the layer that currently implements it, and becomes the thing that **must keep passing** when AD-17 lands |
| **The `displayName` duplication** | **Not extracted** | A pre-existing house pattern across seven files, four of which predate this run. A brownfield refactor across routes this run does not own — **recorded, not changed** |
| **The probe's suite** | **One file, named exactly** | A probe that ran the whole backend suite could pass for the wrong reason — some unrelated test would go red and the probe would look like it proved the rule when it proved nothing about *this* rule |

## Deviations from Plan

**Four, all recorded at the time they were made.**

**1. The Pulse Ping's due time was reasoned from the domain, not adjusted until green.**
The first version of the Ping tests swept at the window's end (08:00) and found **zero
sends**. The cause was not a bug: **the Ping is due at the user's delivery time (09:00)**,
because nothing moved it. The fix was to add `EXPECTED_PING_SEND_LOCAL` and sweep the
Ping tests there — **not** to loosen an assertion. **The reminder and the Ping are
different facts, and the proof now says so in two named constants.**

**2. The `models-delivery` violation was planted in the wrong direction.** The first
attempt planted `apps/delivery/_planted.py` importing `apps.ingestion.models`, which
broke **`models-ingestion`** — because that contract protects *ingestion's* models. The
two contracts are **mirror images**, and the error was only visible because the test
asserts the **exact** broken set. The violation moved to `apps/ingestion/_planted.py`
importing `apps.delivery.models`.

**3. The client-sync check was rewritten from a `git diff` to a regeneration.** The
first version failed with a **498-line diff** — because `schema.ts` is *uncommitted
work*, and a `git diff` compares against the last commit, not against what the
generator produces. The question the contract actually asks is narrower: **does
regenerating change anything?** So the test now regenerates, compares, and restores.

**4. The proof calls `apply_lifecycle_change` directly rather than
`propagate_state_change`.** `propagate_state_change` is a **deliberate placeholder** —
a seam reserved for the fan-out AD-17's state machine will own — and it does not yet
mint the row the proof needs. **This is the item's one recorded deviation**, and the
relationship it creates is the right one: **the placeholder does not get to change the
answer.**

**Two smaller corrections**, both of which were *the fixture being wrong*, not the
assertion: a `1d` slot on a 23:30 event lands at 23:30 **the day before**, which is
**still inside** the window — so the "not deferred" test uses an 18:00 start; and
`DigestPreferenceFactory` needs `city_source="choice"`, because the database refuses a
city without saying where it came from.

## Dependencies Added

**None.** No new package was added to `backend/pyproject.toml`, `frontend/package.json`,
or any lockfile.

**The frontend's testing-library surface was already there** — `@testing-library/react`
only, **without `user-event`** — and the new component test uses `.click()` rather than
introducing a dependency. **The generation tooling (`openapi-typescript`, `pnpm exec`)
was already in the toolchain**, and the contract test invokes it rather than adding it.

## How to Verify

**1. Run the delivery proof — the scenario, end to end**

   ```bash
   cd backend && uv run pytest tests/e2e/test_delivery_proof.py -v
   ```

   Expected: **13 passed**. The proof is offline: it injects the memory email adapter
   and reaches no network.

**2. Run the contract proofs**

   ```bash
   cd backend && uv run pytest tests/e2e/test_delivery_contract.py -v
   ```

   Expected: **9 passed**. This regenerates the OpenAPI document and the TypeScript
   client and asserts both come back **byte-identical**.

**3. Run the six mutation probes — the proof is able to fail**

   ```bash
   cd backend && uv run python tests/e2e/mutation_probe_delivery_e2e.py
   ```

   Expected: **six `OK` lines** and `All 6 delivery probes were caught by the suite.`
   **A probe that reports `FAIL` means the test does not prove that rule.** The harness
   restores every file it mutates, whether the suite passed, failed, or the process died.

**4. Run the frontend half, and the seam**

   ```bash
   cd frontend && pnpm vitest run components/reminders/reminder-chip.test.tsx
   ```

   Expected: **7 passed**.

**5. Run the whole backend suite, with coverage**

   ```bash
   make coverage-backend
   ```

   Expected: **4763 passed**, **99.19%** overall, **100%** on `domain/*`.

**6. Run the import contracts**

   ```bash
   make lint-backend
   ```

   Expected: **`Contracts: 19 kept, 0 broken.`** — including *"AD-2 only
   `apps.delivery` imports `apps.delivery.models` (others call its services) KEPT"*.

**7. Run the frontend gates**

   ```bash
   make lint-web && make test-web && cd frontend && pnpm build
   ```

   Expected: eslint clean, **typecheck clean**, prettier clean, **80 files / 1150
   tests**, and the build green. **The build is a different gate from the test suite** —
   it is what catches a `"use client"` module reaching `next/headers`, which jsdom
   stubs.

**8. Manually walk the user's sentence**

   1. Open `/settings/quiet-hours`, set the window to `22:00 → 08:00`, save.
   2. Open an event starting at **23:30 local** and open `/events/:id/reminders`.
   3. **The `1hr` chip is dimmed** and reads *"Will deliver at 8:00 am Saturday."* —
      visible text, not a hover-only tooltip.
   4. The chip is **still selectable** — it says what will happen; it does not forbid it.
   5. Check the chip's accessible name in a screen reader: **"1 hour before. Will deliver
      at 8:00 am Saturday."** — the fact reaches the ear as well as the eye.

## Test Coverage

- **Backend tests added by this run:** **+1,631** (3,132 → 4,763)
- **Frontend tests added by this run:** **+221** (929 → 1,150)
- **Backend coverage:** **99.19%** overall — **100%** on `domain/*`
- **Import contracts:** **19 kept, 0 broken**
- **Mutation probes:** **6 of 6 caught**
- **Status:** **passing** — every gate green

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated — `plan.md`, `test-report.md` and `review-report.md` all carry a section per work item
- [x] Developer notes captured
- [x] **Every major assertion proven able to fail** — six probes, all caught
- [x] **The path proved offline**, with no delivery-path module importing a network client

## Developer Notes

**The quiet window's end is the window's end, and the day it lands on matters.** An
instant at Friday 22:30 shifts to **Saturday** 08:00. Adding eight hours to a UTC
timestamp gets the wrong answer twice — once for the zone, once for the day.

**Never add a due time to a send key.** The key is the *thing*; `due_at` is the
*schedule*. The moment the key moves, every settings change becomes a second email.

**The sweep has no opinion about quiet hours.** If you find yourself importing
`domain.quiet_hours` into `delivery_sweep.py`, you are about to skip a send at send
time — which is not a deferral, it is a cancellation.

**Two rows, two due times.** The deferred reminder is due at the window's **end**; the
Ping is due at the user's **delivery time**. They are usually an hour apart. **A test
that sweeps at one instant will find the other row "not due", and that is not a bug.**

**`city_source` is not optional.** The database refuses a city without saying where it
came from. If a factory raises `IntegrityError` on
`digest_preference_city_source_ck`, pass `city_source="choice"`.

**`apply_lifecycle_change` takes `revision` for personal events and `version` for
catalog ones** — and `kind="rescheduled"` is **not** a valid kind. The valid kinds are
`time_moved`, `postponed`, `reinstated`, `cancelled`, `superseded`, `sold_out`,
`detail_changed`. **A reschedule is `time_moved`.**

**The probe harness reports `SKIP` when a pattern does not match — and that is a
failure, not a pass.** It means the implementation moved and the probe stopped
applying. **A probe that silently stopped applying is worse than no probe**, because it
looks like a pass.

**The client's sync test is a measurement, not a rewrite.** It regenerates, compares,
and restores the file in a `finally`. **Do not "fix" it into a `git diff`** — the
schema is uncommitted work, and a `git diff` would fail for a reason that has nothing
to do with the contract.

**The frontend's testing-library surface is `@testing-library/react` only —
`user-event` is not installed.** Use `.click()` and `fireEvent`; do not reach for
`userEvent` and add a dependency.

**The build catches what the unit tests cannot.** A `"use client"` module that reaches
`next/headers` passes every Vitest test — jsdom stubs it — and fails `pnpm build`.
**Run the build.**

**`displayName` is duplicated across seven frontend files.** Four predate this run;
this run added three. It is a pre-existing house pattern, recorded rather than changed.
**Extracting it is a brownfield refactor worth its own item.**

---

## Appendix: the Pulse Ping's own walkthrough

**The walkthrough generated when item 7 (`pulse-ping-and-suppression`) completed is
preserved below verbatim.** It documents that one capability in depth — the FR-10 rule,
the suppression's counted reason, the key's shape — and the run-wide document above
covers the whole path. Together they are the two views a reviewer wants: **one item
closely, and the run as a whole.**

---

---
run: run-eventpulse24-023
work_item: pulse-ping-and-suppression
intent: delivery-and-reminders
generated: 2026-11-01T00:00:00Z
mode: confirm
---

# Implementation Walkthrough: The Pulse Ping — one a day, and the silence that earns it

## Summary

This work item made the Pulse Ping a real thing in the schedule. Until now the tree
could *compose* a digest and had every shape a send needs — a `digest` kind, a
`digest_key`, a cancelled-rows helper, a renderer — but **nothing anywhere minted one**.
A user could have been composing into the void for the whole MVP.

Three things now happen, in order, in one place. The **unsubscribe check** comes first
and mints nothing. The **FR-10 check** comes second: zero qualifying public events and
zero qualifying personal events in the user's next 48 hours means **no row is minted at
all** — not a row that is later skipped — because a `pending` row is a promise (AD-7).
Otherwise **exactly one** `digest`-kind `ScheduledSend` is minted, keyed
`user_id · digest · local_date`, for the user's local delivery time, shifted by Quiet
Hours like any other send.

And every silence is **counted with its reason** — in a structured log line and in an
audit row — so SM-C1's "≥30% suppression rate" target is measurable from day one. A
product that cannot say *why* it stayed quiet cannot tell its own intelligence apart
from a broken pipe.

## Structure Overview

The item is a seam, not a feature: it connects the composition (which lives in
`personalization` and knows *what there is to say*) to the schedule (which lives in
`delivery` and owns *when it is said*). Three modules carry that seam, and each keeps
its own responsibility.

`apps/personalization/services/digest_composition.py` remains the **single owner of
the word "qualifying"**. It already reads the public and personal candidate pools; it
now *reports* them — two counts and a boolean property derived from them — instead of
leaving the composition's knowledge to be re-derived by a caller. Nothing else in the
tree re-implements the rule.

`apps/delivery/services/pulse_ping.py` is the **decision**. It takes the composition's
counts, asks the three questions in order — is the user still subscribed, is there
anything worth saying, and if so mint one — and records the outcome. It does not write
the schedule; it asks `scheduled_sends` to.

`apps/delivery/services/scheduled_sends.py` remains the **only writer** of
`SCHEDULED_SEND` (AD-16). It gained one create path, `mint_digest`, which is where the
due time is computed — the local delivery time, shifted out of Quiet Hours — because
that arithmetic is `delivery`'s and the quiet window is `delivery`'s row.

Underneath those three sits a small new piece of domain arithmetic,
`domain/horizon.py`: the user's **local 48-hour horizon**. It advances the *wall clock*,
not the instant, and resolves the result through the project's existing
`read_wall_clock`, so a DST boundary is handled by one piece of code that already knows
how.

Two callers drive the seam: the worker task (`worker/tasks.py`) and the operator
command (`config/management/commands/compose_digest.py`). Both do the same two steps in
the same order — compose, then mint — because the command's `--all` mode stands in for
the dispatcher, and a dispatcher that composed without minting would leave the same
gap.

## Architecture

### Pattern Used

**Service layer with strict write ownership, and a decision that lives in one place.**

Three rules carry the design, and each is enforced by something other than convention:

- **The decision lives in one place.** `DigestCompositionResult.has_qualifying_events`
  is the *only* definition of "qualifying" in the tree. The Ping service reads it; it
  never re-derives it from the counts.
- **The write lives in one place.** `scheduled_sends.py` is the sole owner of
  `SCHEDULED_SEND`. `pulse_ping.py` asks; it does not write. The architecture test
  AST-scans every `apps/` module and fails if any module outside the owner writes the
  table — so the rule is structural, not a convention that can drift.
- **The explanation lives with the fact.** The suppression reason is *persisted* at the
  moment the suppression happens (AD-10), not recomputed later at render time. A row
  that is read to explain what the product did must not depend on the state of the
  world at the time it is read.

### Layer Structure

```text
┌───────────────────────────────────────────────────────────┐
│  Callers                                                  │
│  worker/tasks.py  ·  config/management/commands/…         │
└───────────────────────┬───────────────────────────────────┘
                        │  compose → decide → mint
┌───────────────────────▼───────────────────────────────────┐
│  Delivery — apps/delivery/services/pulse_ping.py          │
│  the DECISION: subscribe? · anything to say? · mint one   │
└───────────────────────┬───────────────────────────────────┘
                        │  mint_ping_send(…)
┌───────────────────────▼───────────────────────────────────┐
│  Delivery — apps/delivery/services/scheduled_sends.py     │
│  the WRITE: get_or_create on the unique send_key          │
│  local delivery time → shift_to_sendable (Quiet Hours)    │
└───────────────────────┬───────────────────────────────────┘
                        │
┌───────────────────────▼───────────────────────────────────┐
│  Domain — domain/horizon.py                               │
│  the ARITHMETIC: now → +48h on the user's wall clock      │
│  resolved through read_wall_clock (gap vs fold)           │
└───────────────────────────────────────────────────────────┘

  Facts in, from personalization:
  apps/personalization/services/digest_composition.py
  DigestCompositionResult{public_qualifying_count,
                           personal_qualifying_count,
                           has_qualifying_events}
        ▲
        │  reads (never writes)
        └──── apps/personalization/services/digest_candidates.py
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/apps/delivery/services/pulse_ping.py` | The decision: the unsubscribe check, the FR-10 check, the mint request, and the counting of both silences. Writes nothing to `SCHEDULED_SEND` — it asks `scheduled_sends` to. |
| `backend/domain/horizon.py` | The user's local 48-hour horizon. Advances the wall clock rather than the instant and resolves the result through `read_wall_clock`, so DST is handled once, in one place. |
| `backend/tests/delivery/test_pulse_ping.py` | The behaviour tests: FR-10's four consequences, the zone boundary, the opt-out, the unsubscribed user, the double-run, the stream and the unsubscribe URL, the counts, and the two formatter-survival tests. |
| `backend/tests/domain/test_horizon.py` | The horizon's arithmetic, including both 2026 DST transitions and the gap/fold resolutions. |

### Modified

| File | Changes |
|------|---------|
| `backend/apps/delivery/services/scheduled_sends.py` | Added `mint_digest(...)` — the digest row's creating path, and the only new create in the module. Computes the due time itself (local delivery time → Quiet Hours shift) and writes its audit inside the same atomic as the `get_or_create`. Also gained `_local_delivery_instant`, the delivery-time arithmetic that belongs in `delivery`. |
| `backend/apps/personalization/services/digest_composition.py` | `DigestCompositionResult` now carries `public_qualifying_count`, `personal_qualifying_count` and the derived `has_qualifying_events` property. The composition computes the local horizon **before** the reads and reports the counts it already had in hand. |
| `backend/apps/personalization/services/digest_candidates.py` | `list_personal_candidates` takes an optional `window_end` and uses `max(default_end, window_end)` — a **widen-only** bound, so a caller can ask for more rows but never fewer. |
| `backend/worker/tasks.py` | `compose_digest_task` now mints the Ping after composing, in the same order the command does, and logs the outcome (`ping_minted`, `ping_suppressed`, `ping_reason`). |
| `backend/config/management/commands/compose_digest.py` | The command now composes **and** mints. Its `--all` mode takes the scheduler's own claim, so it stands in for the dispatcher — and a dispatcher that composed without minting would leave users with no email and no counted silence. |
| `backend/adapters/logging/redaction.py` | Added `reason`, `local_date`, `public_qualifying_count`, `personal_qualifying_count`, `ping_minted`, `ping_suppressed`, `ping_reason` to `ALLOWED_FIELDS`. Without them the suppression line reached the sink with every field redacted, and SM-C1 was unmeasurable. |
| `backend/tests/personalization/test_digest_composition.py` | The pool-count exposure, the opt-out, and two DST tests — one per transition, in both directions. |
| `backend/tests/personalization/test_digest_scheduling.py` | The command now mints alongside the digest; four new tests, and the composition stub was widened to carry the four attributes the decision needs. |
| `backend/tests/worker/test_digest_tasks.py` | A shared `FakeResult` carrying the decision's four attributes, and three new tests: the double-run, the nothing-to-say case, and the outcome line. |
| `backend/tests/architecture/test_ad13_pii_sweep.py` | The audit sink has no allowlist, so its vocabulary is *stated* in the test file. The three new detail keys are now listed, with the reason they are safe. |

## Domain Model

No new entities and no new models. Two **value objects** were introduced, both in
`domain/` and both pure.

| Value Object | Properties | Constraints |
|--------------|------------|-------------|
| `QuietHours` (from the previous item) | `start`, `end` (local wall-clock times), `zone` | Start inclusive, end exclusive; shifting is idempotent — a window that already contains the instant is returned unchanged. |
| `local_horizon(...)` result | a single UTC instant | The wall clock is advanced, not the instant: 48 hours on the user's clock is 47 elapsed hours on a spring-forward day and 49 on a fall-back day. A reading that lands in a gap resolves deterministically; one that lands in a fold resolves to the first occurrence — matching the rest of the codebase. |

Two **enumerations** carry the work item's vocabulary.

| Enumeration | Values | Constraint |
|-------------|--------|-------------|
| `ScheduledSend.Kind` | `DIGEST`, `PULSE_PING`, … | `PULSE_PING` **exists and is never minted**. It is the Phase 2 push reservation; `send_keys` has no builder for it, and a test asserts nothing in the tree mints it. |
| Suppression reason | `unsubscribed`, `no_qualifying_events` | A **closed set of two literals**, two call sites, no stringly-typed escape hatch. `_record_suppression` is private and only called with those two constants. |

The reason set is the important one: `unsubscribed` is *not* a suppression. SM-C1
measures *the product choosing silence*; an opt-out is *the user choosing silence*.
Mixing them would inflate the counter-metric with opt-outs and make SM-C1 a lie.

## Key Implementation Details

### 1. The three checks, in one order, in one place

`mint_ping_send` runs exactly three steps, and the order is not incidental:

```
1. do the counts and the flag agree?   → refuse loudly (ValueError)
2. has the user unsubscribed?          → mint nothing; count `unsubscribed`; STOP
3. is there anything qualifying?       → mint nothing; count `no_qualifying_events`; STOP
4. otherwise                           → mint exactly one row
```

Step 1 exists because the function takes both the counts *and* the boolean. The
boolean decides; the counts are recorded. A caller passing
`(public=0, personal=0, has_qualifying=True)` would mint a Ping the composition says
should not exist — and the log line would read "suppressed because nothing qualified"
while the user got an email. That is a contradiction in a row that exists to explain
what the product did, so it is refused rather than silently sent.

Step 2 comes first because there is no point counting a suppression for a user who
has opted out of the thing entirely. The opt-out is a fact about the user's choice, not
about the product's intelligence.

### 2. One definition of "qualifying"

The work item's technical note is explicit: *do not write a second definition of what
counts as a qualifying event.* The composition's cards cannot answer FR-10's question
— a user with 40 qualifying public events still gets three cards, and "3 qualifying
events → exactly one send" is about *sends*, not cards. So the composition **exposes
the pool counts**:

- `public_qualifying_count` — the public pool's size, within the horizon;
- `personal_qualifying_count` — the personal pool's size, within the horizon, and
  **zero** when the user has opted out of personal events;
- `has_qualifying_events` — a **property** derived from the two counts, not a separate
  field, so the two can never disagree by construction.

`pulse_ping.py` reads the boolean. It never re-derives it from the counts, and it never
re-queries the pools.

### 3. The 48-hour horizon is drawn on the user's wall clock

The distinction is not academic. A 48-hour *duration* is zone-independent in length, but
the *horizon* — the instant the window closes — is a wall-clock reading:

| | local horizon | elapsed (`now + 48h`) | delta |
|---|---|---|---|
| spring-forward (2026-03-10) | `07:00Z` | `08:00Z` | **−1h** |
| fall-back (2026-11-03) | `08:00Z` | `07:00Z` | **+1h** |
| ordinary (2026-11-06) | `16:00Z` | `16:00Z` | 0 |

The horizon therefore advances the wall clock and resolves through `read_wall_clock`,
which detects a gap from a fold by round-tripping through UTC and resolves both
deterministically.

### 4. The personal pool read is widened, never narrowed

The composition counts against the **local** horizon, but the personal candidate read
filtered its own pool with **elapsed** arithmetic (`now + 48h`). The two disagreed by
an hour on each DST day, and on a **fall-back** day the local horizon was an hour
*later* than the read's bound — so a personal event inside that band was in the user's
next 48 local hours, was never read at all, and the user was suppressed for having it.

The fix is deliberately **widening**: `list_personal_candidates` takes an optional
`window_end` and uses `max(default_end, window_end)`, so a caller can only ever ask for
*more* rows. It is impossible for the caller's bound to silently drop an event the
caller wanted to see.

Widening rather than narrowing is what keeps the two decisions separate. The Slot 1
window governs which *cards* a digest holds; narrowing the read to the local horizon
would change that for every user on two days a year. Widening it changes nothing about
the cards, because the caller's own comparison still applies the Slot 1 window.

### 5. One row per user per local date, by construction

Three independent layers:

1. the composition is idempotent — one `PulseDigest` per `(user, local_date)`, a second
   run returns `created=False`;
2. the send key is `{user_id}:digest:{local_date}`, and `send_key` carries a
   `UniqueConstraint`;
3. `mint_digest` uses `get_or_create`, which catches `IntegrityError` inside a
   savepoint and re-fetches — so two concurrent workers cannot create two rows.

"Exactly one row per user per local date" is therefore a property of the schema and
the writer, not of a count someone remembered to write. The acceptance criterion says
*"tested by running the job twice"* — that test exists, and it asserts one row.

### 6. The suppression is counted where it can be read

The module's contract is that the log line is where SM-C1 is read from. But
`JsonFormatter` redacts any `extra` field not on `ALLOWED_FIELDS`, and the fields that
carry the metric were not on it. Every suppression line reached the sink as:

```json
{"message": "Pulse Ping suppressed", "job": "pulse_ping", "user_id": "abc",
 "local_date": "[redacted]", "reason": "[redacted]",
 "public_qualifying_count": "[redacted]", "personal_qualifying_count": "[redacted]"}
```

So SM-C1 could not tell a product suppression from an opt-out — precisely the
distinction this work item exists to make. The log sink was safe (no PII leaked) but
useless. **A metric that cannot be read is not a metric.**

The seven fields were added to `ALLOWED_FIELDS`, following the precedent the previous
item set with the sweep's outcome counts. They are safe because they are a **closed
vocabulary**: `reason` is one of our own slugs, `local_date` is an ISO date, the counts
are integers, and the three `ping_*` fields are booleans and a slug. The architecture
check `test_the_allowlist_itself_holds_no_free_text` passes on all of them (lowercase,
no spaces, snake_case).

### 7. The unsubscribed user is a separate count, not a suppression

`_record_suppression` is called with one of two reasons, and the two are counted
separately in the audit trail. An unsubscribed user has **nothing minted** — no row at
all — and the count says `unsubscribed`, so the product's intelligence and the user's
choice never blur together.

## Security Considerations

| Concern | Approach |
|---------|----------|
| **AD-13 — no PII in logs or audit** | The audit `details` carries only the reason, the ISO date, two integers and a timestamp. The log line carries a user id, a job name, a date and counts. No email address, event title, city or free text reaches either sink. |
| **The reason is a closed vocabulary** | Exactly two literals, two call sites, no stringly-typed escape hatch. `reason` is a slug (`unsubscribed`, `no_qualifying_events`), never a sentence. The allowlist's own architecture test rejects free text on the fields it permits. |
| **Actor labels cannot carry PII** | `Actor.system("pulse_ping")` is validated against a slug pattern, so PII is structurally impossible in the actor label rather than merely absent today. |
| **Audit writes are transactional** | Every `write_audit` call sits inside `transaction.atomic(using=PERSONAL)`. `_record_suppression` opens its own, precisely so the refusal path cannot be reached by a forgotten call site. |
| **A refused caller records nothing** | A caller whose counts and flag disagree raises before any decision is made, so no suppression is counted. Counting it would put a line in SM-C1 that no product decision produced. |
| **RFC 8058 unsubscribe** | The row is `Stream.BULK`, and `render_digest` always builds a `pulse_ping`-scoped `unsubscribe_url`, which `EmailPort.send` requires for bulk (AD-20). The unsubscribe is a POST, so a GET cannot unsubscribe. |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| **No second query for the decision** | The suppression decision reads the counts the composition already had in hand. No pool is re-queried; the Technical Note's demand ("read that rather than re-querying") is met literally, not just in spirit. |
| **The counts are computed over lists already in memory** | `public_qualifying_count` and `personal_qualifying_count` are `sum(1 for c in pool if ...)` over pools the composition already materialised — O(n) over an existing list, no database round trip. |
| **The pool read is not made larger than it needs to be** | The widened bound is `max(default_end, window_end)` — on the two DST days a year it is one hour wider; on every other day it is exactly the same as before. The public pool is untouched. |
| **The mint is a single `get_or_create`** | One query on the unique key, with the `IntegrityError` race handled inside a savepoint. The retry path costs a re-fetch, not a second insert. |
| **The horizon is computed once** | `local_horizon` is called once per composition and its result is passed to both the count and the pool read. |
| **The suppression write is one row** | A suppression is a single audit row inside a single atomic block. It is not a fan-out. |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D1 — the 48-hour window's scope** | Scoped to the **suppression path**, not to the composition's Slot 1 window | FR-10's rule is about *whether to send*, not *what to put in the digest*. Changing `list_personal_candidates`'s default bound would change *which cards a digest holds* — the composition's product surface — for every user, with no test in this item's scope. The review later showed the pools still had to agree, and the fix was a **widen-only** bound rather than a change of default. |
| **D2 — where "qualifying" is defined** | In the composition's `DigestCompositionResult`, as two counts and a derived boolean | The cards cannot answer FR-10's question (40 events → 3 cards), so the composition had to expose the pool counts. Making the boolean a *property* rather than a field means the two can never disagree by construction. |
| **D3 — the reason vocabulary** | A closed set of two: `unsubscribed`, `no_qualifying_events` | SM-C1 measures *the product choosing silence*. An opt-out is *the user choosing silence*. Counting them together would inflate the metric and make SM-C1 a lie. |
| **D4 — where the count lives** | Both a structured log line *and* an audit row | They answer different questions: "how many Pings did we suppress today, and why?" (SM-C1) versus "why did *this* user get no Ping on this day?" (a product question about one account). |
| **D5 — where the seam lives** | A new module `apps/delivery/services/pulse_ping.py` | It is the seam between the composition (`personalization`) and the schedule (`delivery`). The decision is `delivery`'s; the write is `scheduled_sends`'s; the composition's knowledge is `personalization`'s. Neither service reaches across to the other. |
| **D6 — the horizon's arithmetic** | Advance the **wall clock**, resolve through `read_wall_clock` | The horizon is a local reading, not a duration. `read_wall_clock` already knows how to tell a gap from a fold and resolves both deterministically, matching the rest of the codebase. |
| **D7 — the command's role** | `compose_digest` **composes and mints** | The command's `--all` mode takes the scheduler's own claim through `claim_due_digests`, so it stands in for the dispatcher. Leaving the send unminted there produced digests with no emails — and no counted suppression either, so the day's silence was invisible to SM-C1. |
| **D8 — the command's docstring** | Rewritten to say why it changed | It said *"It composes; it does not send… this command has no opinion about it"* — correct when there was no send to mint, and now it says what changed and why. |
| **D9 — the composition's pool read** | Widened via `max(default_end, window_end)` | The composition counts against the local horizon while the read filtered in elapsed arithmetic — a one-hour band on each DST day. Widening is the only safe direction: it cannot drop an event the caller wanted, and it leaves the Slot 1 card window untouched. |
| **D10 — the counts/flag consistency check** | A loud `ValueError`, not a silent correction | The rule lives in the composition; the check only insists that the two facts the caller passes describe the same world. Correcting silently would hide the caller's bug; sending anyway would put a lie in the audit trail. |

## Deviations from Plan

Four changes, all made during the code review, each in the direction the work item's own
acceptance criteria demanded.

**1. `ALLOWED_FIELDS` in `adapters/logging/redaction.py` was not in the plan.**
The plan assumed the suppression's log line was readable. It was not — `JsonFormatter`
redacted every field on it, so SM-C1 could not tell a product suppression from an
opt-out. The plan's own D3 says "a structured log line" and the criterion says the
suppression must be *counted with the reason*; a redacted reason is not counted with the
reason. Seven fields were added, each with a comment saying why it is safe.

**2. `list_personal_candidates` was modified, against the plan's explicit "Not modified".**
The plan's D1 reasoned from the *default* bound, but the review measured the actual
divergence: the pool was filtered in elapsed arithmetic while the count was filtered in
the local zone, and on a fall-back day a personal event in that band was never read at
all — so a user with a real event was suppressed for having it. The plan's reasoning
about blast radius was right, and the fix honours it: the read is **widened**, never
narrowed, and the Slot 1 window is untouched.

**3. `config/management/commands/compose_digest.py` was modified, and it was not in
the plan's file list at all.**
The plan only changed the worker task. But the command's `--all` mode takes the
dispatcher's own claim, so it stands in for the dispatcher — and composing without
minting left a user with no email *and* no counted silence. The command now does what
the worker does, in the same order.

**4. `pulse_ping.py` gained the counts/flag consistency guard.**
Not in the plan, and not an acceptance criterion — but a contradiction between the two
facts a caller passes would put a lie in a row that exists to explain what the product
did. The guard refuses loudly and records nothing.

The plan's "Not modified" list also holds for `list_public_candidates` and
`render_digest` — both were left alone, and the review confirmed the public pool's
gates and the Ping-scoped unsubscribe URL were already correct.

## Dependencies Added

**None.** No new packages, no new services, no new infrastructure. The item depends only
on work already completed in this run:

- `send-minting-and-rescheduling` — `scheduled_sends.py` as the schedule's writer and
  the Quiet Hours arithmetic (`shift_to_sendable`);
- `email-templates-and-unsubscribe` — the Ping-scoped unsubscribe URL and the
  `pulse_ping_unsubscribed` read;
- `quiet-hours-domain` — `QuietHours` and `shift_to_sendable`;
- `notification-preferences` — `DigestPreference` and `get_delivery_settings`.

## How to Verify

1. **Run the whole gate suite.**

   ```bash
   cd backend
   ruff check .
   ruff format --check .
   lint-imports
   python manage.py check
   python manage.py makemigrations --check --dry-run
   pytest --cov --cov-report=term
   ```

   Expected: `All checks passed!` · `469 files already formatted` · `Contracts: 19 kept,
   0 broken` · `System check identified no issues` · `No changes detected` ·
   **4599 passed**, overall coverage **99.10%**, `domain/` **100%**.

2. **Run this item's tests alone.**

   ```bash
   cd backend
   pytest tests/delivery/test_pulse_ping.py tests/domain/test_horizon.py \
          tests/personalization/test_digest_composition.py \
          tests/personalization/test_digest_scheduling.py \
          tests/worker/test_digest_tasks.py
   ```

   Expected: **164 passed** (34 / 19 / 59 / 35 / 17).

3. **See the suppression count reach the sink, unredacted.**

   ```bash
   cd backend
   pytest tests/delivery/test_pulse_ping.py -k survives_the_log_formatter -v
   ```

   Expected: the test formats the record through the project's own `JsonFormatter` and
   asserts `line["reason"] == "no_qualifying_events"`. Reverting the `ALLOWED_FIELDS`
   change makes it fail with `"reason": "[redacted]"` — that is the proof that the test
   is reading the bytes that reach production, not the raw `LogRecord`.

4. **Exercise the operator command end to end.**

   ```bash
   cd backend
   python manage.py compose_digest --user-id <uuid>
   ```

   Expected: `Composed the digest for <uuid> (<local date>).` followed by either
   `Minted the Pulse Ping.` or `Suppressed the Pulse Ping (no_qualifying_events).`
   Running it twice writes **one** `ScheduledSend` row and reports `Already had…` the
   second time.

5. **Confirm the write ownership is structural, not conventional.**

   ```bash
   cd backend
   pytest tests/architecture/test_schedule_writes.py -v
   ```

   Expected: passes. It AST-scans every `apps/` module and fails if any module outside
   `scheduled_sends.py` / `delivery_sweep.py` writes `SCHEDULED_SEND`.

6. **Confirm the DST boundary by hand.**

   ```bash
   cd backend
   python -c "
   from datetime import datetime, UTC, timedelta
   from domain.horizon import local_horizon
   for n in ('2026-03-10', '2026-11-03'):
       now = datetime.fromisoformat(n + 'T12:00:00+00:00').replace(tzinfo=UTC)
       h = local_horizon(now=now, zone_name='America/New_York', window=timedelta(hours=48))
       print(n, h, (h - now))
   "
   ```

   Expected: the spring-forward horizon is 47 elapsed hours out and the fall-back
   horizon is 49 — the wall clock advanced 48 hours in both cases.

## Test Coverage

- **Tests added: 76** (34 `test_pulse_ping.py`, 19 `test_horizon.py`, and 23 added to
  the three existing files)
- **Suite: 4599 passed**, 0 failed (up from 4588 — **+11** after the review fixes)
- **Coverage: 99.10%** overall (gate 80%); **`domain/` 100%** (gate 100%)
- **This item's modules: 100%** each — `pulse_ping.py`, `horizon.py`,
  `digest_composition.py`, `digest_candidates.py`, `compose_digest.py`,
  `worker/tasks.py`. `scheduled_sends.py` is at 96%, and the 7 uncovered lines are all
  in *other* commands, not in `mint_digest`.
- **Status: passing.** Every fix was verified by **reverting it and watching the test
  fail** — a test that does not fail without its fix is not evidence.

## Ready for Review

- [x] All nine acceptance criteria met, each with its own test
- [x] Tests passing — 4599 passed, 0 failed
- [x] No critical issues — the code review found one critical defect (the redacted
      metric) and three further problems; **all four are fixed**, each with a test that
      fails without the fix
- [x] Architecture contracts intact — 19 kept, 0 broken
- [x] Documentation updated — the module docstrings, the command's docstring and the
      `ALLOWED_FIELDS` comments all state the *current* behaviour and why it changed
- [x] Developer notes captured
- [ ] **Concurrent mint test** — the unique constraint makes concurrent minting
      correct, and the sequential double-run is tested, but there is no *concurrent*
      test. The project has a `race()` harness in
      `tests/personalization/test_digest_scheduling_concurrency.py` that would cover
      it. Deliberately left for the end-to-end proof item rather than added here.

## Developer Notes

**Gotchas that will save debugging time.**

- **`JsonFormatter` redacts anything not on `ALLOWED_FIELDS`.** A log field that is
  not allowlisted reaches production as `"[redacted]"` — and it does so *quietly*. The
  existing tests asserted on the raw `LogRecord`, where every field is readable, so
  they passed while the sink was useless. When a metric has to be *read*, assert on the
  bytes: format through `adapters.logging.formatter.JsonFormatter` and parse the
  result. That gap is now closed for the two fields that carry the metric.
- **`pytest --cov=<module>` breaks the database.** Narrowing the coverage source set
  changes the plugin's import ordering, and 212 tests failed with `OperationalError:
  the connection is closed`. The project's own `pytest --cov --cov-report=term` is
  unaffected. Get per-module figures from `coverage report --include=...` afterwards.
- **`.replace(tzinfo=None)` keeps `fold`.** It strips the offset but preserves the
  `fold` flag, so a `fold=1` reading can reach code that ignores it. `domain/horizon.py`
  uses an explicit `.replace(tzinfo=None, fold=0)` to state the intent.
- **`DigestCompositionResult` is frozen, and `has_qualifying_events` is a property,
  not a field.** `dataclasses.replace(result, has_qualifying_events=...)` raises
  `TypeError`; replace the two *counts* instead and the flag follows.
- **The DST divergence is one hour in opposite directions on the two transitions** —
  the local horizon is *earlier* on spring-forward and *later* on fall-back. The
  fall-back case is the one that silently loses events, because the read's bound stops
  an hour before the count's horizon.
- **`ruff` on a scoped path misses errors elsewhere.** An earlier scoped `ruff check`
  passed while a full `ruff check .` found 12 errors (3 × E501, 9 × DTZ001). The `tests/`
  config exempts `S101`, `S105`, `S106`, `S603`, `S608` and `TID251` — **but not
  `DTZ`**. A naive wall-clock reading in a test needs an explicit `# noqa: DTZ001`
  with a comment saying why it is deliberate.

**For the next item.**

- The `pulse_ping` kind still exists in the enum and is still never minted — that is
  the Phase 2 push reservation, and the comment says so. Do not add a `send_keys`
  builder for it; a builder for a key nothing mints is dead code that looks like a
  feature.
- The composition now exposes the pool counts. The reminder-plan API will need the
  same treatment: **read the composition's knowledge, do not re-query it**, or the
  second definition of "qualifying" that this item took pains to avoid will reappear.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-023*
