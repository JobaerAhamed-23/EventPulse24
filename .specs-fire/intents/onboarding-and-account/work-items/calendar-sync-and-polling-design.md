# Design: Calendar Sync Services & Polling

**Work item**: `calendar-sync-and-polling`
**Intent**: `onboarding-and-account`
**Mode**: validate (Checkpoint 1 of 2 — this document)
**Date**: 2026-10-29

---

## 1. What this item delivers

The **write side** of calendar import: the commands that turn a fetched feed into the user's
`PERSONAL_EVENT` rows, and the scheduler that decides when a feed is fetched.

Four commands live in `apps/personalization/services/`:

| Command | What it does |
|---|---|
| `connect_calendar` | Validates the address, enforces the Free cap, stores the connection, **requests** a first sync. Does not fetch (AD-11). |
| `sync_calendar` | Fetches through `CalendarPort`, then reconciles the connection's imported events. |
| `reconnect_calendar` | Replaces the encrypted credential, returns the status to `active`. |
| `disconnect_calendar` | Destroys the credential, then purges **exactly that connection's** events. |

Plus the **polling** dispatcher, which claims due connections atomically and enqueues one
sync per claim.

**In scope**: the four commands, the reconcile logic, the due-claim, the worker tasks, the
audit rows, and the tests that pin every behaviour above.

**Out of scope** (separate items): the HTTP endpoints (`calendar-connect-api`), the
onboarding step-1 UI (`frontend-onboarding-flow`), the pending-conflicts read
(`pulse-preview-api-and-geo`), and two-way sync (out of scope in the brief entirely).

**A note on the previous item.** `connect_calendar` and `disconnect_calendar` already exist
(`calendar-connection-model`, D13). This item **extends** them rather than rewriting them:
`connect_calendar` gains "request a first sync", `disconnect_calendar` gains "purge the
events". The extension must preserve every behaviour the earlier item's tests pin — the cap
ordering, the `needs_reconnect` row reuse, the fingerprint uniqueness, the credential
destroyed first.

---

## 2. The problem, stated precisely

A connected calendar is a **mirror of somebody else's agenda** that we re-fetch on a
schedule and write into the user's own event list. Three things make that harder than it
looks:

1. **A feed is a snapshot, not a delta.** It says "here are my events", not "here is what
   changed". So every sync must *reconcile* — create what is new, update what changed,
   delete what disappeared. A sync that only appends will accumulate duplicates forever; a
   sync that only upserts will accumulate ghosts forever.

2. **The user can edit an imported event.** The imported event is in `PERSONAL_EVENT` and
   the user can rename it, move it, or delete it. On the next sync the feed still says the
   old thing. If the sync overwrites the user, the user's edit is lost; if the sync never
   overwrites, the mirror stops being a mirror. FR-50 says a disconnect "purges exactly
   that connection's events", so the imported rows are ours to manage — but *whose* edit
   wins is a product question with no obvious answer.

3. **A background sync has no user to prompt.** FR-58's conflict prompt assumes the user is
   right there, mid-creation, choosing between three buttons. A poll happens at 3am, to
   nobody. Something has to be decided about what a background import does when it finds a
   conflict, and about what "Delete the new one" means when the "new" event is one the
   provider owns and will re-send next hour.

---

## 3. Decisions

### D1 — The reconcile is a three-way diff, keyed on `(connection, uid)`

**Decision.** A sync computes the diff between the feed's entries and the connection's
imported rows, keyed on `(calendar_connection_id, source_uid)` — the unique constraint the
model already carries.

| In the feed | In the database | Action |
|---|---|---|
| yes | no | **Create** the imported event |
| yes | yes, identical | **Nothing.** The sync is a no-op for this entry. |
| yes | yes, different | **Update** the row, and bump `version` |
| no | yes | **Delete** the row |

**Why the unique constraint is the right key.** `personal_event_connection_uid_uq` already
exists on `(calendar_connection_id, source_uid)` — it was created by the connection-model
item *for this purpose*, and its model docstring says so: "Together with the connection id
it makes a re-sync an upsert rather than a duplicate." Using it here means the database
already refuses the one thing that would corrupt the data (two rows for one provider
event), so the code does not have to be clever.

**Why the id is the *entry* id and not the raw UID.** The adapter (`ics-calendar-adapter`)
already applies `domain.dedup.ics_item_id`, so a recurring instance carries
`uid#YYYYMMDDTHHMMSSZ` and an override of a master's own instance carries the *same* id as
that master. This is what makes the override replace the master instead of duplicating it.
The sync must use the id the adapter produced — it must **not** re-derive one from the raw
UID, or the override would land beside the master it replaces.

**Why "identical → nothing" is explicit.** A sync that rewrites every row on every poll
would bump `version` hourly for every event, and `version` feeds AD-7's send key — so every
reminder for every imported event would be re-sent, every hour, forever. Comparing the
fields that matter and leaving an unchanged row alone is what makes the poll idempotent in
the sense that matters: not just "the data is the same" but "nothing downstream fires".

**The comparison.** The fields that make an imported event what it is: `name`,
`start_utc`, `end_utc`, `start_time_tz`, `location`, `notes`. The `version` column is
bumped only when one of those actually differs.

---

### D2 — The user's edit wins over the feed, on the fields the user can change

**Decision.** On a difference, the **user's** value of a user-editable field wins, and the
feed's value wins only for fields the user cannot edit.

| Field | Who wins on a difference |
|---|---|
| `name` | **The user** |
| `start_utc`, `end_utc`, `start_time_tz` | **The user** |
| `location`, `notes` | **The user** |
| `source_uid`, `calendar_connection_id`, `source` | The feed (structural — never user-editable) |

**The mechanism.** The import distinguishes an imported row the user has **never touched**
from one the user has **edited**, by a flag on the row: `user_modified` (Boolean, default
`False`).

- `user_modified = False` → the feed owns the row. A difference is a real change upstream,
  so the sync **applies** it: the row is updated and `version` is bumped.
- `user_modified = True` → the user owns the row. A difference is either a feed change the
  user has overridden, or a genuine conflict. The sync **does not** apply it, and the row is
  left exactly as the user left it.

**Why this is the right answer.** The alternative — the feed always wins — makes the user's
edit to their own event a temporary state that evaporates within an hour, with no warning
and no undo. That is a data-loss bug wearing a synchronisation feature's clothes. The other
alternative — the user always wins — means a meeting moved at the provider's end never
updates, and the mirror is quietly wrong. Splitting the fields by who *owns* them gives each
party what it owns and neither can destroy the other's work.

**Why the flag, and not a heuristic.** "Did the user edit it?" can be inferred ("the row
differs from what the feed says"), but that inference is exactly the case where the feed and
the row disagree — and the answer would flip depending on which side you looked from. A
stored flag is unambiguous, it survives a feed change, and it is one boolean column.

**The flag is set by the update command.** `update_personal_event` sets
`user_modified = True` on a user-created event and on an imported event the user edits. That
is the **same command path** the user's own edit takes (the work item's requirement: "Every
create, update and delete goes through the same command paths as user-created events"), so
the flag cannot be set by a path that bypasses the command layer.

**A user-created event is never touched by a sync at all.** It has no `source_uid` and no
`calendar_connection_id`, so the diff — which is scoped to *this connection's imported rows*
— cannot reach it. This is not a rule the code enforces by checking; it is a consequence of
the diff's scope.

**A user-*deleted* imported event comes back.** If the user deletes an imported event, the
next sync sees the entry in the feed with no row in the database, and recreates it. **This
is decided, not an oversight**: the mirror is the provider's agenda, and the provider still
says the event exists. The alternative — a tombstone — would need a persistent "the user
hid this" set, and the provider could reintroduce the event under a new UID anyway, so the
tombstone would be a half-measure that leaks imported events into the user's list forever.
The user's recourse is to delete it again, or to disconnect the calendar, which purges
everything. **This is recorded as a known product behaviour and it is what the UI's
"delete" affordance on an imported event will have to explain** (`frontend-onboarding-flow`
and the Timeline's read-only surface are the surfaces that would carry it).

---

### D3 — A background import records a conflict; it never forces a prompt

**Decision.** An imported event that conflicts with the user's own events creates an
**`active` `CONFLICT_PAIR`** — the same row, through the same `detect_conflicts` /
`record_detected_conflicts` path, with the same `domain/conflict.py` rules. The pair is
recorded; the three-way prompt is **not** presented at import time.

**Why.** FR-58's prompt is a *forced choice* ("there is no dismiss") and it is presented in
a creation flow the user is in. A poll at 3am has no such flow. Three options were
considered:

| Option | What happens | Why not |
|---|---|---|
| **A** | Record the pair as `active`; show the amber indicator; present the three-way prompt the next time the user opens the app, through a pending-conflicts read. | Preserves FR-58's "no dismiss" and the amber indicator. Needs a pending-conflicts read. |
| **B** | Record the pair; show only the indicator; never prompt, because the user did not create the event here. | Simplest. But leaves the user with a permanent indicator and no way to resolve it. |
| **C** | Suppress conflict detection entirely for imported events. | **Rejected.** The work item and the brief both say "Imported events … go through the existing FR-58 conflict detection". Suppressing it would contradict the brief outright. |

**Option A is chosen.** It is the only one that satisfies both halves of the requirement:
the conflict *is* detected, by the one function in `domain/conflict.py`, and the prompt is
still a forced choice — just deferred to a moment when the user is present. The amber
indicator is on both events from the moment the pair is recorded (AD-21: detection runs on
write, never at render, and the indicator reads the pair rows), so the user is not left
unaware; they are simply not interrupted at 3am.

**The pending-conflicts read is a later item.** `pulse-preview-api-and-geo` owns the
authenticated home and the `/conflicts` route (EXPERIENCE.md's route map, route 11). This
item delivers the *pairs* — the durable, user-visible fact — and the later item delivers the
read that presents them. The design records the dependency so the later item knows what it
is inheriting: **an `active` `CONFLICT_PAIR` naming an imported event is the prompt's
pending state.**

**What "Delete the new one" means for an imported event.** The work item asks this
explicitly. On an imported event, the button would delete the row — and the next sync would
recreate it. So the button is **meaningless for an imported event**, and offering it would
be a lie: the user picks "Delete", and the event comes back an hour later.

**Decision:** for a conflict where the *new* side is an imported event, the resolution
"delete the new one" is **not offered**; the pair is instead closed as
`cleared_by_state_change` with a `keep_both`-equivalent outcome? No — that would erase the
conflict without the user's choice.

**Revised decision, and the final one:** for a conflict whose new side is an **imported**
event, the pair is recorded but **the three-way prompt is not presented at all**, and the
pair is closed with `status = cleared_by_state_change` the moment the user *views* the
conflict list and takes no action? No — that invents a viewing rule nobody asked for.

Let me state it plainly, because the design must not wobble:

**The pair is recorded as `active`. The user resolves it from `/conflicts`, where the
prompt's three buttons are shown. "Delete the new one" on an imported event does not
delete the row — it **hides the UID** for that connection.** The sync then skips that UID
on every future poll, so the event does not come back.

**This needs a storage decision.** A "hidden UID" is per `(connection, uid)`. A row in a
dedicated table is the honest model: `CalendarEventSuppression` — `(connection_id, uid)`,
created when the user hides an imported event. The sync skips suppressed UIDs. The
suppression is per connection, so disconnecting the calendar removes the suppressions with
it, and the user who reconnects gets their calendar back as the provider has it.

**But this is a schema addition, and the work item's acceptance criteria do not mention
suppression.** So this is a decision for **Checkpoint 1**, and the options are:

- **(a) Add a suppression table now.** One new model + migration + a skip in the sync.
  Costs a migration and a new model in the `personal` schema.
- **(b) Do not delete imported events at all.** The UI simply does not offer "Delete the new
  one" for an imported event — it offers "Keep both" and "Edit the new one" only. FR-58's
  three buttons are for *creation flows*; an imported event is not a creation flow. The
  conflict stays visible as an amber indicator until the provider stops sending the event.

**Recommended: (b).** It needs no schema change, it does not break FR-58 (which governs
creation-time prompts, not import-time ones), and it is honest: the imported event is the
provider's, and the user cannot delete it from their calendar — only the provider can. The
suppression table (a) becomes the right answer the moment the user *asks* for a "hide this
from my timeline" affordance, which is a different feature (a **timeline filter**, not a
conflict resolution) and belongs to a later item.

**The "Edit the new one" button on an imported event** opens the imported event in edit
mode; the user edits it; `update_personal_event` sets `user_modified = True`; and from then
on the sync leaves it alone (D2). That is a coherent, useful resolution — and it is the one
that makes the conflict *resolvable* rather than merely visible.

**Consequence:** the three-button prompt for an imported conflict has **two** usable
buttons, not three. The API that presents it (`pulse-preview-api-and-geo`) must therefore
offer a two-button variant for imported sides, and the design records that so the later
item does not offer a button that cannot work.

**Resolved plan:** Option (b). The pair is recorded as `active`; the prompt (presented from
`/conflicts` by a later item) offers **"Keep both"** and **"Edit the new one"** for an
imported side; **"Delete the new one" is not offered** for an imported side; no suppression
table is added; the resolution code for an imported side is restricted accordingly. This is
pinned by a test in this item.

---

### D4 — Duplicate detection does **not** apply between an imported event and a user-created one

**Decision.** FR-58's duplicate rule (≥80% token overlap, starts within 24 hours) applies
**between two personal events**, including two imported ones. It does **not** apply between
an imported event and a **user-created** one.

**Why.** The rule's purpose is to catch the user typing "Dinner" twice. A user-created
"Dinner" and a calendar "Dinner" at 7pm are very often the *same real-world dinner* — but
the user typed theirs deliberately, and the provider's is the source of truth for the same
occasion. Flagging them as duplicates would:

- present a prompt the user cannot meaningfully resolve ("Delete the new one" would delete
  the user's own event, and "keep both" would keep the same dinner twice);
- be wrong in the common case where the user's event is *about* the calendar one ("take the
  dog to the vet" at 7pm, and a "Vet appointment" at 7pm — not duplicates at all, just two
  things at the same hour).

**But the time conflict still applies.** Two intervals overlapping by more than 15 minutes
is a double-booking regardless of who owns them, and the amber indicator is the right
response: it says "you have two things at once", which is true, without claiming they are
the same event.

**How the difference is expressed in code, without a second detector.** The *time* rule and
the *duplicate* rule are both in `domain/conflict.py` and both are applied by
`detect_conflicts`. The distinction is *which* pairs the duplicate rule is applied to. So
the sync's detection path differs from a user creation's in exactly one way:

- `create_personal_event` → `detect_conflicts` (time + duplicate), unchanged.
- The import → `detect_conflicts` for the **time** rule only, against the user's personal
  and saved events.

The cleanest expression is a parameter on the service, not a new function:

```python
detect_conflicts(user_id=..., candidate=..., include_duplicates=False)
```

The flag is on the *service*, not on the domain: `domain/conflict.py` keeps both rules and
one implementation of each; the service decides which rules to apply to which comparison.
That keeps the domain pure and keeps the policy — "an imported event is not a duplicate of
a user-created one" — in the layer that owns the policy.

**Two imported events from two different connections** *are* compared for duplication
against each other (both are imported, both are personal events). A duplicate between two
imports is a real duplicate: the user saved the same meeting to two calendars.

---

### D5 — The reminder default: imported events get the FR-20 default, and that is the answer

**Decision.** An imported event gets the **FR-20 default plan** — 1d + 1hr — exactly like a
user-created one. It is attached by calling `delivery`'s published `attach_default_plan`,
the same call `create_personal_event` makes.

**Why.** FR-20 says "A Personal Event created with a default Reminder Plan inherits 1d + 1hr"
— it says *Personal Event*, not *user-created Personal Event*. An imported event is a
`PERSONAL_EVENT` row, and the user asked for their calendar to be in their timeline; the
whole point of a reminder is to tell them about it. Not reminding them about their own
meetings would make the import less useful than useless.

**The alternative, and why it loses.** "Imported events get no reminders" would avoid
double-notifying a user who also saves the same event from the catalog — the imported one
and the saved one would both remind. But that double-notification is already possible
today (a user-created event and a saved public event for the same concert both carry the
default), and FR-58's conflict system is what surfaces the overlap, not the reminder plan.
Suppressing reminders on imports would silently break the feature for every user whose
calendar is their main agenda, and it would make the import's behaviour inconsistent with
every other personal event.

**The user can remove them** (FR-9's picker, `remove_all_reminders`), and the plan is a
row the user owns — so the default is a default, not a commitment.

**One consequence the design must own.** An import that *updates* an existing row does
**not** re-attach the plan: `attach_default_plan` **replaces** any existing plan with the
default, so calling it on an update would wipe a plan the user had customised. So the
default is attached **only on create** — the same rule `update_personal_event` already
follows ("The reminder plan is **not** touched. FR-20's default is a property of creation").

---

### D6 — A revoked fetch marks the connection `needs_reconnect` and **keeps the imported events**

**Decision.** A `CalendarRevokedError` from the port sets the connection's status to
`needs_reconnect`, records `last_error_kind = "revoked"`, and **leaves every imported event
in place**. A `CalendarTransientError` leaves the status alone and records
`last_error_kind = "transient"`. A `CalendarRefusedError` records
`last_error_kind = "refused"` and leaves the status alone — a refusal is *our* decision
about the address, not the provider's word about the credential, and it must never mark a
connection revoked.

**Why the events stay.** The work item says it and it is right: the provider revoked the
*address*, not the *events*. The events were real, they are the user's, and they are the
only record the user has of what they had planned. Deleting a user's history because a
provider issued a 403 would be destructive and irreversible, and the user might fix the
credential in a minute. "Never silently deletes them" is the requirement.

**What the status does.** `needs_reconnect` means "the user must paste a new address". The
connection stops being due (the due-scan only claims `active` connections — the model's
partial index says so), so a revoked connection is not polled again until the user
reconnects. The imported events remain visible in the timeline, and the UI can show a calm
"reconnect to keep it up to date" note. **Deleting them is the user's explicit choice**,
through disconnect.

**The status transition is legal.** `active → needs_reconnect` is in the connection-model
design's transition table (D7). The reverse — `needs_reconnect → active` — is the reconnect
command.

---

### D7 — A transient failure leaves the schedule alone and retries at the next due time

**Decision.** A transient failure records `last_error_kind` and `last_error_at`, and sets
`next_poll_at = now + CALENDAR_POLL_INTERVAL` — the same schedule as a success. The
connection stays `active` and is polled again an hour later.

**Why not a backoff?** A backoff would need a second set of constants (the interval, a
multiplier, a cap) and would make the "when is the next poll" question harder to answer.
The interval is one hour and the provider's failure is not ours to predict. A provider
that is down for an hour costs one failed poll per connection per hour — bounded, small,
and honest. **A backoff is recorded as a possible later refinement**, when there is
evidence it is needed (OQ-7 is still open, and its answer may be about how often we may
poll at all).

**A transient failure does not reconcile.** Nothing is written, nothing is deleted. The
previous state is kept exactly as it was.

---

### D8 — Polling: the tick enqueues a dispatcher; the dispatcher claims atomically

**Decision.** The polling path mirrors `ingestion`'s scheduling exactly:

```
beat (60s) → tick → enqueue(schedule_calendars)
                        ↓
              schedule_calendars:
                flag?  no — calendar connections have no staleness flag
                claim_due_connections(now)   # FOR UPDATE SKIP LOCKED, batched
                for each claim: enqueue(sync_calendar, connection_id)
```

**The tick never touches the database** (AD-11): it enqueues, and the dispatcher does the
work. `beat_schedule` stays exactly one 60s tick — `backend/tests/worker/test_tick.py`
passes unchanged.

**The claim is atomic and has a TTL.** `claim_due_connections` takes its rows with
`select_for_update(skip_locked=True)` and stamps a claim timestamp, exactly as
`claim_due_sources` does. Two overlapping ticks therefore never claim the same connection:
the second tick's `SKIP LOCKED` skips the row the first one is holding. A claim older than
the TTL is a lost job (a worker died) and the connection becomes claimable again.

**A claim column is needed.** `CalendarConnection` has no claim field today. The model
gains `sync_claimed_at` (nullable DateTime), mirroring `Source.ingest_claimed_at`.

**The TTL is a new named constant.** `shared.constants.CALENDAR_CLAIM_TTL`, alongside
`INGEST_CLAIM_TTL`. It is **not** the ingestion TTL reused by name — they are different
jobs with different durations (a calendar fetch can take up to 30 s, plus a large body;
an ingestion run can take much longer). **Decision: 15 minutes** — comfortably longer than
a fetch's worst case (30 s total timeout) and comfortably shorter than the 1-hour poll
interval, so a lost claim is recovered well before the next scheduled poll.

**The batch size** is `CALENDAR_SYNC_BATCH = 100`, mirroring `SCHEDULE_BATCH`.

**The due rule.** A connection is due when it is `active` and `next_poll_at <= now`. A
connection that has never been polled has `next_poll_at = NULL` — it is due immediately
(the connect command sets it, D9, so it is never NULL in practice; but the NULL case is
treated as due, so a row written by any other path is still picked up).

**Ordering:** least-recently-polled first, so no connection starves.

---

### D9 — The connect command **requests** a sync; it does not fetch

**Decision.** `connect_calendar` sets `next_poll_at = now` (due immediately) and writes an
audit row. It does **not** fetch, and it does not enqueue anything itself — the tick's
dispatcher will pick it up within 60 seconds.

**Why.** AD-11: no request does long work. A fetch can take 30 seconds and download
megabytes. The connect command must return in milliseconds so the user sees their calendar
appear in the onboarding flow immediately.

**Why "set `next_poll_at`" rather than "enqueue a job".** The connect command is a
*service* command; it must not depend on Celery. Setting the due time is the durable
expression of "please sync this soon", and the dispatcher — which already exists for the
polling path — picks it up. One mechanism, not two. **This is the same pattern `ingestion`
uses**: `register_source` sets a cadence and the tick's dispatcher does the work.

**The first-sync timing.** The user's first sync happens within 60 seconds of connecting
(the tick interval), plus the fetch time. The onboarding step-1 UI therefore needs a
**pollable sync status** — the work item says so explicitly. That read is
`calendar-connect-api`'s (the endpoint) and `frontend-onboarding-flow`'s (the UI). This item
delivers the *state* the read needs: the connection's `status`, `last_polled_at`,
`next_poll_at` and `last_error_kind` are all on the row and all updated by the sync.

**What "a first sync was requested" means in the audit row.** `calendar.connected` carries
the provider and the moment — never the address, never the fingerprint (AD-13). The
*request* to sync is not a separate audit row; the sync itself writes one.

---

### D10 — The sync writes one audit row, by a system actor, with no event content

**Decision.** Every sync writes **one** audit row per connection — not one per event.

- The actor is a **system actor**: `Actor.system("calendar_sync")`. A polled sync has no
  user behind it; inventing one would put a user's id in an audit row for an action they
  did not take.
- The action is `calendar.synced`.
- The details carry **counts only**: `created`, `updated`, `deleted`, `unchanged`, and the
  provider. **Never a title, a location, a note, a UID, or a URL** (AD-13).

**Why one row per sync rather than one per event.** A user's calendar can hold hundreds of
events. A per-event audit row would write hundreds of rows per hour per connection, and
each row would be about an event the user did not create — noise in a log whose purpose is
"what changed in this account". The counts answer the question an audit row exists to
answer ("did the sync happen, and what did it do") without naming a single event.

**Why the counts are safe and the content is not.** A count is an integer with no content
in it. A title is user content. The distinction is the same one the logger's allowlist
draws, and it is why the counts are in the audit row and the titles are not.

**The reconciling writes themselves.** The create/update/delete of an imported event go
through the *same command paths* as user-created events (the work item's requirement), so
those paths write their own audit rows — `personal_event.created` and friends. **This is
the tension in the requirement, and it is resolved like this:** the *event-level* audit rows
are written by the shared command paths (so there is one audit trail for one kind of
mutation, whichever way it was triggered), and they are written with the **system actor**,
because a polled sync has no user actor. The additional `calendar.synced` row is the
connection-level record: "this connection was synced, and here is what changed".

So a sync of 50 new events writes 50 `personal_event.created` rows (system actor) and one
`calendar.synced` row (system actor). The counts are in the latter, so the former do not
need to.

---

### D11 — Every create, update and delete goes through the existing command paths

**Decision.** The sync does **not** write `PersonalEvent` rows directly. It calls:

- `create_personal_event` for a new entry,
- `update_personal_event` for a changed entry,
- `delete_personal_event` for a vanished entry.

**Why.** The work item requires it and it is the right call: those commands are where
conflict detection, the reminder default, the audit rows and the version bump live. Writing
rows directly from the sync would give imports a *second* implementation of "create a
personal event" — and the two would drift, which is exactly how an imported event ends up
with no conflict detection.

**What has to change in those commands to make them usable by an import.** Three things,
and they are the reason this item touches `personal_events.py` at all:

1. **`source`, `calendar_connection_id` and `source_uid`** must be settable. Today
   `create_personal_event` hardcodes the user-created default. The commands gain optional
   parameters for them.
2. **`user_modified`** must be set by `update_personal_event` (D2), and **not** set by the
   import's own update path — the import's update path calls `update_personal_event`, which
   would set it. **This is a real conflict, and it is resolved below.**
3. The conflict detection on the import path must skip the duplicate rule (D4).

**Resolving (2).** The import calls `update_personal_event` to apply a feed change, but
`update_personal_event` sets `user_modified = True` because a *user* edit means the user
owns the row. If the import used it, every feed change would mark the row user-owned, and
the next feed change would be ignored — the mirror would freeze after one update.

**Decision:** the commands gain an explicit flag for who is making the change:

```python
update_personal_event(..., user_modified: bool = True)
create_personal_event(..., user_modified: bool = False)
```

The import passes `user_modified=False` for a create, and for an update it passes
`user_modified=True` only when the row was **already** user-modified (preserving the
user's ownership), and `False` otherwise (the feed owns it).

**This is explicit and a little awkward, and that is the honest shape of the thing.** The
alternative — a separate `apply_imported_event` command that writes rows directly — would
duplicate the conflict detection, the reminder attachment and the audit. The flag keeps one
command path and states the policy at the call site. The awkwardness is the *policy*: "who
owns this row" is a real question, and a parameter that names it is clearer than a
convention hidden in a branch.

**What "the same command paths" means for the version bump.** `update_personal_event`
bumps `version` by one with `F("version") + 1`. The import's update does the same, because
it goes through the same command. AD-7's send key uses the version, so a changed imported
event's reminders are re-keyed — which is correct: the time moved, so the reminder times
move.

---

### D12 — Reconcile on a time change: the conflict pairs and the reminders follow the row

**Decision.** An imported event whose time changes is an **edit**, and it goes through
`update_personal_event` — so:

- its **conflict pairs are re-judged**: a pair that no longer overlaps closes as
  `cleared_by_state_change`, one that still overlaps stays `active`, and a new overlap
  creates a new pair. That is `_reconcile_pairs`, which the command already calls.
- its **reminder plan is not re-attached** (D5) — but the plan's slots are *relative*
  offsets before the event start, so when the start moves the **computed send times move
  with it**. `delivery`'s `slot_offsets` derives the absolute times from the start, and the
  send key includes the event's version (AD-7), so the changed event's reminders are
  re-scheduled rather than left pointing at the old time.

**This is why the import must go through `update_personal_event`** and not write the row
directly: the pair reconciliation and the version bump are already there, and re-implementing
them in the sync would be a second implementation of the same rules.

---

### D13 — The disconnect purges exactly that connection's events, and their conflicts and plans

**Decision.** `disconnect_calendar` gains a purge step, in this order:

1. **Destroy the credential** — `status = disconnected`, `credential = NULL`. Already
   implemented.
2. **Close the conflict pairs** naming the connection's imported events, as
   `cleared_by_state_change`.
3. **Delete the imported `PersonalEvent` rows.**
4. **Delete the reminder plans** for those events.

Each step goes through **its owner's interface** (the work item's requirement):

| Step | Owner | How |
|---|---|---|
| 2. Close the pairs | `personalization` | `close_pairs_for_side` — the same call `delete_personal_event` makes. |
| 3. Delete the events | `personalization` | `delete_personal_event` — the same command, so the audit row and the pair closure happen. |
| 4. Delete the plans | **`delivery`** | `delivery` owns `REMINDER_PLAN`. `personalization` may not write it — the `models-delivery` import contract forbids importing `apps.delivery.models`. |

**Step 4 needs a new command in `delivery`.** `delivery` currently has
`attach_default_plan`, `set_plan_slots`, `remove_all_reminders` and `get_plan` — none
removes a plan for a deleted event. The reason is visible in
`delete_personal_event`'s docstring: "The reminder plan row stays behind. `delivery` owns
`REMINDER_PLAN`, and `personalization` may not write it — deleting the plan is `delivery`'s
call, and it has no such command yet. The leftover row is inert."

**Decision: `delivery` gains `remove_plans_for_targets(*, user_id, target_kind, target_ids)`**
— a command that deletes the plans for a set of targets. `personalization` calls it, which
keeps the ownership boundary: `personalization` never writes `REMINDER_PLAN`; it asks
`delivery` to.

**Why this matters for the disconnect specifically.** FR-50: "disconnecting purges exactly
that connection's imported events". If the plans stayed behind, a disconnected calendar
would leave reminder rows pointing at events that no longer exist — and if the user later
connected a *different* calendar whose events got new ids, the old plans would not match
anything either. Inert rows are tolerable for a single deleted event; for a whole
calendar's worth, they are a growing pile of dead rows. **The disconnect is the one place
where the plans must go**, and it is why this item touches `delivery`.

**Ordering.** The credential is destroyed **first** (already the case). Then the events are
deleted (which closes their pairs). Then the plans. If the purge fails part-way, the
credential is already gone — the user's revocation does not depend on the purge succeeding
(the connection-model design's D7 reasoning, unchanged).

**What is untouched.** Another connection's events, and the user's own events. The purge is
scoped by `calendar_connection_id = connection.pk` — exact by construction, since the id is
held by value (the connection-model design's D8). **A test with two connections proves
this**, and it is in the acceptance criteria.

---

### D14 — The imported event's zone is the entry's own zone

**Decision.** The imported event's `start_time_tz` is the `CalendarEntry.tz` — the IANA zone
the entry was authored in (AD-6: UTC is the storage truth, and the zone says which wall
clock the user meant). For an entry with no zone (an all-day event read at UTC midnight),
the zone is `UTC`.

**Why.** A personal calendar has no venue registry to resolve a zone later — the catalog's
venue registry is for *public* events. The adapter already resolved the entry against its
own zone (`ics-calendar-adapter`), and the result carries the zone. The sync uses it as-is.

**Why "UTC" for a zoneless all-day event.** `CalendarEntry.tz` is a required field on the
port's entry. An all-day event has no zone; the adapter reads it at UTC midnight, and the
zone it reports is `UTC`. So the sync stores `UTC` — and the instant is right, which is what
the timeline draws.

---

### D15 — What a sync does when the fetch fails: nothing is written

**Decision.** A failed fetch writes **no** event rows, no conflict pairs and no reminder
plans. It writes the connection's status/error fields and one audit row recording the
failure — and the audit row's details hold a **slug** (`revoked`, `transient`, `refused`,
`undecryptable`) and a count of nothing. Never a URL, never a message, never a title.

**Why.** A partial sync would be worse than no sync: half the user's imported events would
be deleted because the feed happened to be truncated, and the missing ones would be
recreated on the next poll. The reconcile is therefore **all-or-nothing**: the fetch
succeeds and produces a complete entry list, or nothing is reconciled.

**The one exception:** the connection's own status may change (D6) — that is not part of
the reconcile.

---

### D16 — Where the code lives

| Module | Contents |
|---|---|
| `apps/personalization/services/calendar_sync.py` | **New.** `sync_calendar`, the reconcile diff, `claim_due_connections`, `release_claim`. |
| `apps/personalization/services/calendar_connections.py` | **Extended.** `connect_calendar` sets `next_poll_at`; `disconnect_calendar` purges; `reconnect_calendar` is added. |
| `apps/personalization/services/personal_events.py` | **Extended.** `create_personal_event` / `update_personal_event` gain the import parameters. |
| `apps/personalization/services/conflicts.py` | **Extended.** `detect_conflicts` gains `include_duplicates`. |
| `apps/delivery/services/reminder_plans.py` | **Extended.** `remove_plans_for_targets`. |
| `apps/personalization/models.py` | **Extended.** `PersonalEvent.user_modified`; `CalendarConnection.sync_claimed_at`. |
| `worker/tasks.py` | **Extended.** `schedule_calendars` and `sync_calendar` tasks. |
| `shared/constants.py` | **Extended.** `CALENDAR_SYNC_BATCH`, `CALENDAR_CLAIM_TTL`. |

**Why the sync is a service, not a task.** The task is the *trigger*; the service is the
*work*. The same rule the other services follow: no `request`, an explicit `now`, an
explicit `actor`, one `transaction.atomic(using=PERSONAL)`, the audit row inside it. It is
also what makes the sync testable without Celery — the test calls the service; the task is a
thin wrapper, like `ingest_source` is a thin wrapper around `ingest_source`.

**Why `calendar_sync.py` is a separate module rather than more of `calendar_connections.py`.**
`calendar_connections.py` is about *the connection* (its credential, its status, its
lifecycle). The sync is about *the user's events* — it reconciles them, detects conflicts
on them and drives the reminder plans. Two different concerns, two modules, and the second
one is the one that will grow when the UI needs to know how a sync is going.

---

### D17 — The sync's own log line carries counts only

**Decision.** The sync logs one line per connection with the same counts the audit row
carries: `created`, `updated`, `deleted`, `unchanged`, and a slug when it failed. **No
title, no UID, no URL, no location, no note** (AD-13).

**Why the UID is not logged.** The UID is the provider's identifier for the event. It is
opaque, but it is *per-event content* — and it is the key the reconcile uses. A log line
full of UIDs is a log line full of the user's agenda, in a form that names every event in
their calendar. The counts say what happened without naming any of it.

---

## 4. Files

### Created

| File | Purpose |
|---|---|
| `backend/apps/personalization/services/calendar_sync.py` | `sync_calendar`, the reconcile diff, the due-claim and its release. |
| `backend/apps/personalization/migrations/0003_…` | `PersonalEvent.user_modified`, `CalendarConnection.sync_claimed_at`. |
| `backend/tests/personalization/test_calendar_sync.py` | The sync: the three reconcile branches, idempotence, revoked/transient, the conflict behaviour, the audit rows. |
| `backend/tests/personalization/test_calendar_polling.py` | The due-claim: atomicity, the TTL, the batch, the ordering. |
| `backend/tests/worker/test_calendar_tasks.py` | The tick's dispatcher and the sync task. |

### Modified

| File | Change |
|---|---|
| `backend/apps/personalization/models.py` | `PersonalEvent.user_modified`; `CalendarConnection.sync_claimed_at`; the constraints. |
| `backend/apps/personalization/services/calendar_connections.py` | `connect_calendar` sets `next_poll_at`; `disconnect_calendar` purges; `reconnect_calendar` is added. |
| `backend/apps/personalization/services/personal_events.py` | The import parameters on create and update; `user_modified` on update. |
| `backend/apps/personalization/services/conflicts.py` | `detect_conflicts(..., include_duplicates=False)`. |
| `backend/apps/delivery/services/reminder_plans.py` | `remove_plans_for_targets`. |
| `backend/worker/tasks.py` | `schedule_calendars`, `sync_calendar`. |
| `backend/shared/constants.py` | `CALENDAR_SYNC_BATCH`, `CALENDAR_CLAIM_TTL`. |
| `backend/apps/personalization/admin.py` | The new columns, if the admin lists them. |
| `backend/tests/worker/test_tick.py` | Unchanged — the acceptance criterion says it must pass unchanged. |

---

## 5. Test plan

Every test below must be able to **fail** — the fix reverted in the working tree, the test
re-run, and the failure observed.

### Connect

| Test | Pins |
|---|---|
| `test_connecting_requests_a_sync_without_fetching` | `next_poll_at` is set; the port is never called. |
| `test_connecting_still_refuses_a_duplicate` | The earlier item's behaviour, preserved. |
| `test_connecting_still_enforces_the_free_cap` | The earlier item's behaviour, preserved. |

### The reconcile

| Test | Pins |
|---|---|
| `test_a_new_uid_becomes_a_personal_event` | The create branch. |
| `test_a_changed_uid_updates_its_row_and_bumps_the_version` | The update branch. |
| `test_a_uid_that_disappeared_is_removed` | The delete branch. |
| `test_resyncing_an_unchanged_feed_changes_nothing` | The idempotence branch: same rows, same versions. |
| `test_an_unchanged_feed_sends_no_reminders_again` | The version did not move, so the send key did not move. |
| `test_the_imported_event_carries_its_connection_and_uid` | The row is marked as an import. |
| `test_the_imported_event_gets_the_default_reminder_plan` | D5. |
| `test_an_update_does_not_replace_the_users_reminder_plan` | D5's consequence. |

### Ownership (D2)

| Test | Pins |
|---|---|
| `test_a_feed_change_overwrites_an_untouched_import` | The feed owns an untouched row. |
| `test_a_feed_change_does_not_overwrite_a_user_edit` | The user owns an edited row. |
| `test_a_user_edit_marks_the_row_user_modified` | The command sets the flag. |
| `test_a_user_created_event_is_never_touched_by_a_sync` | The diff's scope. |
| `test_a_deleted_imported_event_returns_on_the_next_sync` | The decided behaviour. |

### The failures (D6, D7, D15)

| Test | Pins |
|---|---|
| `test_a_revoked_fetch_marks_the_connection_and_keeps_the_events` | D6. |
| `test_a_transient_failure_leaves_the_status_alone` | D7. |
| `test_a_refused_fetch_is_never_a_revocation` | D6. |
| `test_a_failed_fetch_writes_no_events` | D15. |
| `test_the_next_poll_is_scheduled_after_a_failure` | D7. |
| `test_the_next_poll_is_scheduled_after_a_success` | D9. |

### The conflicts (D3, D4)

| Test | Pins |
|---|---|
| `test_an_imported_event_that_overlaps_records_a_conflict_pair` | D3: the pair exists. |
| `test_an_imported_event_that_is_a_duplicate_of_a_user_event_records_no_pair` | D4. |
| `test_two_imported_events_with_the_same_name_do_record_a_pair` | D4's exception. |
| `test_a_resolved_conflict_is_not_re_prompted_on_the_next_sync` | AD-21. |

### The disconnect (D13)

| Test | Pins |
|---|---|
| `test_disconnecting_purges_exactly_that_connections_events` | The scope. |
| `test_disconnecting_leaves_another_connections_events` | The two-connection test. |
| `test_disconnecting_leaves_the_users_own_events` | The scope. |
| `test_disconnecting_removes_the_reminder_plans` | D13's step 4. |
| `test_disconnecting_closes_the_conflict_pairs` | D13's step 2. |
| `test_disconnecting_destroys_the_credential_first` | The ordering. |

### The polling (D8)

| Test | Pins |
|---|---|
| `test_a_due_connection_is_claimed` | |
| `test_a_connection_that_is_not_due_is_not_claimed` | |
| `test_a_claim_takes_the_row_atomically` | `SKIP LOCKED` — two claims, one row. |
| `test_an_expired_claim_becomes_claimable_again` | The TTL. |
| `test_the_claim_is_bounded` | The batch size. |
| `test_a_needs_reconnect_connection_is_not_claimed` | D6: a revoked connection is not polled. |
| `test_the_tick_stays_one_60s_tick` | The acceptance criterion. |

### The audit and the logs (D10, D17)

| Test | Pins |
|---|---|
| `test_a_sync_writes_one_audit_row_with_counts` | D10. |
| `test_the_sync_audit_row_holds_no_event_content` | D10: no title, no uid, no url. |
| `test_a_polled_sync_uses_a_system_actor` | D10. |
| `test_no_event_content_reaches_any_log_line_over_a_full_sync` | The acceptance criterion (AD-13). |

---

## 6. Acceptance criteria → where each is met

| Acceptance criterion | Where |
|---|---|
| Connect validates, refuses duplicates, enforces the cap, stores, does not fetch | D9; `calendar_connections.py` |
| Connect **enqueues** the first sync | D9 — `next_poll_at = now`, claimed by the dispatcher |
| New UIDs become rows; changed UIDs update and bump `version`; disappeared UIDs are removed | D1 |
| Re-running a sync with an unchanged feed changes nothing | D1 — the "identical → nothing" branch |
| Every create/update/delete goes through the same command paths | D11 |
| A revoked outcome sets `needs_reconnect` and **keeps** the events | D6 |
| A transient failure leaves the status alone and retries at the next due time | D7 |
| Reconnect replaces the credential, sets `active`, requests a sync | D9 |
| Disconnect deletes **exactly** that connection's events, their pairs and their plans | D13 |
| Another connection's events and user-created events are untouched | D13; the two-connection test |
| The tick enqueues a dispatcher; the dispatcher claims due connections in bounded batches | D8 |
| Two overlapping ticks never sync the same connection twice; the claim is atomic with a TTL | D8 |
| `beat_schedule` stays exactly one 60s tick; `test_tick.py` passes unchanged | D8 |
| Conflicts detected by `domain/conflict.py` (strictly more than 15 minutes) | D3, D4 |
| The background-import conflict behaviour is decided and pinned by tests | D3 |
| A conflict resolved with "Keep both" is not re-prompted | D3 (AD-21's immutability) |
| Sync/connect/disconnect write audit entries by actor, with no event content and no URL | D10 |
| No event content and no URL reaches any log (AD-13) | D17 |
| The listed test coverage | §5 |

---

## 7. Open questions carried forward

1. **OQ-7 — the poll interval.** `CALENDAR_POLL_INTERVAL` is **1 hour, provisional**. It is
   not validated against a live Google secret address, and this item does not change it.
   The number lives in exactly one place (`shared/constants.py`), and the *only* thing this
   item changes is that the constant is now actually used — by the dispatcher that computes
   the next due time. **When OQ-7 closes, one line changes.**
2. **The pending-conflicts read.** The pairs are durable and the `active` state is the
   prompt's pending state; presenting them is `pulse-preview-api-and-geo`'s job. This item
   records the dependency, and the two-button variant for an imported side (D3) with it.
3. **"Delete the new one" on an imported event.** Decided as *not offered* (D3). If the
   product later wants a "hide this event" affordance, it is a **timeline filter**, not a
   conflict resolution — a new table, a later item, and a different name.
4. **A backoff on transient failures.** Not implemented (D7). If the poll interval turns
   out to be too aggressive, a backoff is the first thing to add — and it belongs next to
   `CALENDAR_POLL_INTERVAL`, not scattered.
5. **A user-created event that duplicates an imported one.** The import wins the *time*
   conflict and loses the *duplicate* one (D4). If a user finds that confusing, the
   duplicate rule's scope is the thing to revisit — not the detector.

---

## 8. Standards referenced

- `docs/ARCHITECTURE-SPINE.md` — AD-3 (the wall), AD-5 (the audit), AD-6 (UTC + IANA zone),
  AD-7 (the tick, the send key), AD-8 (one home for constants), AD-11 (no long work in a
  request), AD-13 (no PII in logs), AD-15 (retention), AD-16 (write ownership), AD-18 (the
  calendar is a port), AD-21 (conflict pairs).
- `PRD §4.11 FR-50`, `§4.11 FR-58`, `§4.11 FR-20` — the connect, the conflict prompt, the
  reminder default.
- `EXPERIENCE.md` `Sheet.ConflictResolution` — the three-button prompt, "no dismiss", the
  permanence of the indicator after "Keep both".
- `.specs-fire/intents/onboarding-and-account/brief.md` — the import goes through FR-58's
  conflict detection; the poll interval is provisional (OQ-7); `beat_schedule` stays one
  60s tick.
- `calendar-connection-model-design.md` (D6, D7, D8, D13) — the fingerprint, the status
  machine, the model, and the service layer this item extends.
- `ics-calendar-adapter-design.md` — the port's three outcomes, the entry's identity rule,
  and the zone the adapter resolved.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-020*
