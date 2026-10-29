---
run: run-eventpulse24-020
work_item: calendar-sync-and-polling
intent: onboarding-and-account
generated: 2026-10-29
mode: validate
---

# Implementation Walkthrough: Calendar Sync & Polling (AD-7, AD-18, FR-20, FR-50, FR-58)

## Summary

One module that turns a connected calendar's feed into the user's own events, and one
dispatcher that decides which connection to fetch next.

The item's central problem is that **a feed is a snapshot, not a delta**. It says "here
are my events", not "here is what changed". So every poll has to compute the difference
between the feed and what is already stored — and the difference has four possible
shapes, not two:

| In the feed | In the database | Action |
|---|---|---|
| yes | no | create |
| yes | yes, identical | **nothing** |
| yes | yes, different | update (unless the user owns the row) |
| no | yes | delete |

The third row of that table is the one that matters most, and it is the one this
implementation got wrong the first time. A row the user has edited is **the user's**,
not the feed's; a poll that overwrites it is a data-loss bug wearing a synchronisation
feature's clothes. The review found that the implementation did exactly that, in a
window the test suite could not see, and it is now fixed and pinned.

---

## Structure Overview

```
backend/
├── apps/personalization/
│   ├── models.py                     ← the claim column, the cache validators, the flag
│   ├── migrations/
│   │   ├── 0003_calendarconnection_sync_claimed_at_and_more.py
│   │   └── 0004_calendarconnection_etag_and_more.py
│   └── services/
│       ├── calendar_sync.py          ← NEW: the reconcile, the claim, the dispatcher API
│       ├── calendar_connections.py   ← connect, reconnect, disconnect, purge
│       ├── personal_events.py        ← the shared commands (create/update/delete)
│       ├── conflicts.py              ← detection, with the duplicate rule switchable
│       └── conflict_resolutions.py   ← the three buttons, and the imported-event refusal
│
├── apps/delivery/services/
│   └── reminder_plans.py             ← `remove_plans_for_targets` (delivery owns the plans)
│
├── shared/constants.py               ← the batch size, the claim TTL
└── worker/tasks.py                   ← the tick, the dispatcher, the sync job
```

The layer rule is unchanged: `worker` → `apps` → `ports` → `domain` → `shared`. The
17 import contracts are intact.

---

## The Three Decisions That Carry the Item

### 1. The reconcile is a three-way diff, and "identical" means nothing happens

`sync_calendar` reads the connection's imported rows, reads the feed's entries, and
diffs them on `(calendar_connection_id, source_uid)` — the unique constraint the model
already carries.

The **identical → nothing** branch is the one the whole design turns on. `version` feeds
AD-7's send key. A poll that rewrote every row on every pass would bump every version,
re-key every send, and **re-send every reminder for every imported event, every hour,
forever**. So the branch is pinned from both sides:

- the row's `version` and `updated_at` are unchanged after a second sync of the same feed;
- and the reminder is not re-sent.

The id is the one the **adapter** produced (`domain.dedup.ics_item_id`), not one
re-derived from the raw ICS UID. That matters for recurring events: an override of a
master's own instance carries the same id as that master, and re-deriving would land the
override *beside* the master it is supposed to replace.

### 2. The user's edit wins — and the flag is stored, not inferred

"Who owns this row?" could be inferred by comparing the row with the feed. **That
inference is exactly the case where the two disagree**, and its answer flips depending
on which side you look from. So the flag is stored:

`PersonalEvent.user_modified` — `True` means the user owns the row, `False` means the
feed owns it. A model constraint refuses `True` on a user-created event, because there
is no feed to disagree with one.

The first implementation had this **almost** right, and the gap was the interesting
part. The command's parameter was `user_modified: bool`, and the import passed `False`.
But `False` cannot mean "leave it alone" — it means "the feed owns this row". So every
import write **reset** the flag, and a user's edit could be overwritten on the next
poll.

The fix gave the parameter a **third value**:

```python
user_modified: bool | None = True,
```

`True` (the user owns it), `False` (the feed owns it), `None` (leave it as it stands).
The import passes `None` — the only thing it is entitled to say, because it knows what
the feed says but not whose edit it is.

And the decision itself is made against **committed state**, under a row lock, in the
same transaction as the write — not against the snapshot the diff started with. A user's
edit that lands mid-reconcile is now protected.

### 3. "Delete the new one" is not offered for an imported event

An imported event is the **provider's**. Deleting the row would make the event vanish
for an hour and then come back at the next poll — so the button would be a lie.

The refusal happens **before** the pair is marked resolved, so a refused attempt leaves
the pair `active` and still answerable with a choice that works ("keep both", "edit the
new one").

---

## The Polling

The dispatcher mirrors `ingestion`'s scheduling exactly.

```
tick (every 60s)  →  schedule_calendars  →  claim_due_connections  →  one job per claim
                                                                    →  sync_calendar
```

The claim is taken with `FOR UPDATE SKIP LOCKED`, so two overlapping ticks never claim
the same connection. A claim older than `CALENDAR_CLAIM_TTL` (15 minutes) is a lost job
— a worker that died — and the connection becomes claimable again.

**The tick itself is unchanged.** `tests/worker/test_tick.py` still passes untouched;
that was this item's named acceptance criterion. The tick now enqueues one more
dispatcher, and `tests/worker/test_scheduling_tasks.py` was updated to say so.

### The failure taxonomy

Four outcomes, and only one of them asks the user to do anything:

| Outcome | Status | Events | Next poll |
|---|---|---|---|
| revoked (401/403/404/410) | `needs_reconnect` | **kept** | scheduled |
| transient (5xx, timeout) | unchanged | kept | scheduled |
| refused (our decision) | unchanged | kept | scheduled |
| undecryptable credential | unchanged | kept | scheduled |

A provider revoked the **address**, not the events — deleting a user's history over a
403 would be irreversible. And a refusal is *our* decision about the address, not the
provider's word about the credential, so it must never mark a connection revoked.

### The 304 path

A `304 Not Modified` is a success: the feed has not changed and the caller keeps what it
has. The provider's cache validators (`ETag`, `Last-Modified`) are stored on the
connection and sent back on the next fetch, so an unchanged feed costs one `304`
instead of a full download.

A validator the provider no longer sends is **cleared** rather than kept. A stale
`ETag` would make the provider answer `304` for a feed it has changed, and the user's
events would silently stop updating.

---

## The Audit and the Logs

One audit row per sync, holding **counts only**:

```json
{"created": 3, "updated": 1, "deleted": 0, "unchanged": 42, "provider": "google"}
```

One row per connection, not one per event: a user's calendar can hold hundreds of
events, and a per-event row would write hundreds of rows per hour per connection.

The log line carries the same counts and no event content. A test asserts that **no
event content reaches any log line over a whole sync** — no title, no uid, no location,
no URL. The credential is handed to the port wrapped in `ports.calendar.Credential`,
whose own `repr` is `Credential('[redacted]')`.

The polled sync acts as the system actor `calendar_sync`, with no user id: a poll at 3am
has no user behind it, and putting a user's id in an audit row for an action they did
not take would be a lie.

---

## The Purge

FR-50: "disconnecting purges exactly that connection's events". The order is the safe
one — **the credential is destroyed first**, in its own transaction, so the user's
revocation never depends on a purge succeeding. If the purge fails, the secret is
already gone.

The purge then walks three tables, each through **its owner's interface**:

| Step | Owner | How |
|---|---|---|
| the conflict pairs | `personalization` | `delete_personal_event` closes them |
| the events | `personalization` | `delete_personal_event` |
| the reminder plans | **`delivery`** | `remove_plans_for_targets` (AD-16) |

`delivery` owns `REMINDER_PLAN`, and `personalization` may not write it. The purge asks
`delivery` to delete the plans; it does not reach for the model. The
`models-delivery` import contract is what keeps that true.

The purge is scoped by `calendar_connection_id`, which is exact by construction: another
connection's events and the user's own events are untouched.

---

## The Conflicts

The import reaches detection only through `create_personal_event` and
`update_personal_event` — the same commands the user's own edits use. That is D11, and
it is why an imported event gets the same reminder default (FR-20's 1d + 1hr), the same
version bump, the same audit row and the same conflict detection.

Two rules apply, and they do not apply to the same pairs:

- the **time** rule applies everywhere — two things at once is a clash whichever way
  round it is;
- the **duplicate** rule does **not** apply between an import and a user-created event.
  A user-created "Dinner" and a calendar "Dinner" at 7pm are very often the same dinner,
  and the user typed theirs deliberately, so flagging them would be a prompt with no
  useful answer. Two *imports* are still compared — the user saved the same meeting to
  two calendars.

So the duplicate rule had to become switchable on the command path, not only on
`detect_conflicts`: the import reaches detection only through the commands. That was
one of the six gaps the test suite found while building this item.

---

## Where the Money Is Spent

The poll interval is **1 hour**, and it is **provisional** (OQ-7). The number lives in
exactly one place (`shared/constants.py`), and the only thing this item changes is that
the constant is now actually used — by the dispatcher that computes the next due time.

**When OQ-7 closes, one line changes.**

---

## What the Tests Prove

94 item-scoped tests, 2648 in the whole backend, all passing. Every module this item
created or changed is at **100%** coverage.

The properties pinned, by decision:

- **D1** — the three-way diff: create, update, delete, and the identical branch that
  changes nothing.
- **D2** — the user's edit wins, including when the edit lands *mid-reconcile*, and the
  ownership flag is never reset by an import.
- **D3/D4** — the imported-event refusal; the duplicate rule's scope; the time rule's
  scope; a resolved pair is never re-prompted.
- **D5/FR-20** — the default plan is attached on creation only, so an update never
  wipes a customised plan.
- **D6/D7** — revoked keeps the events; transient leaves the status alone; refused is
  never a revocation; a failed fetch writes nothing.
- **D8** — the claim: atomicity under real contention, the TTL, the batch, the
  ordering, the release.
- **D9** — connect and reconnect request a sync **without fetching**; the reconnected
  calendar is claimed on the next tick.
- **D10/D17** — one audit row with counts; no event content in any audit row or log
  line.
- **D13** — the purge's scope, the pairs, the plans, and the ordering.
- **D15** — a failed fetch writes no events, no pairs, no plans.

The review's fixes added their own regression tests, and each was verified by **reverting
the fix and watching the test fail** — a regression test that passes against the broken
code proves nothing.

---

## What Comes Next

- **`calendar-connect-api`** — the HTTP surface for connect, reconnect and disconnect.
  The conflict prompt's two-button variant for an imported side is owed to
  **`pulse-preview-api-and-geo`**: the service refuses "delete the new one" for an
  imported side, but the client has to be told which buttons to offer.
- **`pulse-preview-api-and-geo`** — the conflicts endpoint. Note that
  `resolve_conflict`'s "delete the new one" calls `delete_personal_event`
  unconditionally, so a `SAVED_EVENT` side would raise `PersonalEventNotFoundError` and
  leave the pair `active` forever. That is pre-existing and unreachable through today's
  API, but it becomes reachable with the conflicts endpoint, and should be settled
  there.
- **AD-15, the retention sweep** — a failed purge leaves orphaned events and plans, and
  nothing retries them. The design sanctions that (the credential is destroyed first),
  but it sanctions it without a compensating mechanism, and the retention sweep is where
  that should be settled.

---

## Result

**Passing.** 2648 passed, 0 failed; 98.92% coverage with 151 files at 100%; ruff clean;
17/17 import contracts kept; no migration drift; `tests/worker/test_tick.py` unchanged
and passing.

The item's own test suite found **six** gaps while building it (the 304 path could never
work; the bulk delete had no target to name in its audit row; the duplicate rule was not
switchable on the command path; a stale cache validator would have frozen a calendar;
two uncovered branches in the imported-event helper; an atomicity test that could not see
its own rows). The code review found **five** more, one of them a BLOCKER — a user's
edit could be overwritten and their ownership destroyed by a poll that raced them. All
eleven are fixed and regression-tested.
