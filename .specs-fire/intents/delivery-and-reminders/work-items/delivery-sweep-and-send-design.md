---
id: delivery-sweep-and-send
title: The sweep — due rows out, mail sent, exactly once
intent: delivery-and-reminders
mode: validate
created: 2026-10-31
checkpoint_1: approved
checkpoint_1_at: 2026-10-31T15:10:00Z
---

# Design: the sweep — due rows out, mail sent, exactly once

This is the **first code in the project's history to send an email**. `ports/email.py` and
`adapters/email/{smtp,memory}.py` have existed since the scaffold with no caller anywhere. The
`SCHEDULED_SEND` table exists (item 3) and is written by exactly one service (item 4), and
nothing has ever read it.

The worker job that reads due rows off the `(due_at, status)` index, claims each under
`SELECT … FOR UPDATE SKIP LOCKED`, sends it through the existing `EmailPort`, and marks it
`sent`.

---

## The shape of the problem

Four failure modes, and they pull in opposite directions:

| Failure | What the user sees | The tempting fix | Why the fix is wrong |
|---|---|---|---|
| **Double send** | Two of the same reminder | Hold the row lock across the provider call | The lock is held for the length of a network call; the batch stalls and a slow provider backs up the whole sweep |
| **Lost send** | No reminder at all | Mark `sent` before calling the provider | The row says sent and nobody received anything; the fact is now a lie |
| **Duplicate rows** | Two different reminders | Re-mint on every retry | A retry is not a new intent; a second key means a second email (AD-7) |
| **One bad row stops the batch** | One user's provider error means nobody gets mail | Let the exception propagate | A single bad address becomes every user's lost reminder |

AD-7 resolves the first three by making delivery **at-least-once with dedupe at the send
boundary**: the send key is the provider's idempotency key. That means the sweep may attempt a
send twice, and the provider collapses the second. It does **not** mean the sweep may attempt a
send twice *and hope* — the key has to actually reach the provider, on every attempt, including
the retry after a crash.

The fourth is ordinary error isolation: one row never stops the others.

---

## Decisions

### D1 — Claim-then-send-then-mark, with the lock released before the provider call

The lock protects the **claim**, not the network.

```
BEGIN
  SELECT ... FOR UPDATE SKIP LOCKED      -- claim
  UPDATE claimed_at = now                -- record the claim
COMMIT                                   -- <-- lock released here
                                         -- provider call happens OUTSIDE the transaction
BEGIN
  UPDATE status = 'sent', sent_at = now -- mark
COMMIT
```

Holding the lock across the provider call is the obvious implementation and it is wrong twice
over. It serialises the batch behind one slow SMTP server, and — worse — it makes the
"two workers never send the same row" guarantee depend on a transaction staying open across
the network, which is exactly the kind of lock that gets released by a connection drop at the
worst moment.

So the claim is **recorded**, not merely locked: `claimed_at` is set in the same transaction as
the `SKIP LOCKED` claim, and the transaction commits before the provider is called. The
`claimed_at` column already exists on `ScheduledSend` with exactly this docstring:

> *"Null means unclaimed. The sweep claims with `FOR UPDATE SKIP LOCKED` but **must not hold the
> row lock across the provider call**, so the claim is also recorded here — the same reading as
> `DigestPreference.digest_claimed_at` and `CalendarConnection.sync_claimed_at`. A claim older
> than `SEND_CLAIM_TTL` is a dead worker's row and becomes claimable again."*

The model was written with this design in mind. The sweep is that design's implementation.

### D2 — The claim predicate is `(due_at <= now) AND (unclaimed OR claim expired)`

Two conditions, and they are both needed.

`due_at <= now` is the due-ness test. `due_at` is **already shifted for Quiet Hours** (AD-7),
so this is the true send time and no other test applies. **The sweep never re-checks Quiet
Hours** — see D3.

`claimed_at IS NULL OR claimed_at <= now - SEND_CLAIM_TTL` is the liveness test. A worker that
died mid-send leaves a `claimed_at` that never expires on its own, so the row would be claimed
once and never again — a reminder that silently disappears. `SEND_CLAIM_TTL` is 5 minutes, and
the constant's own docstring says why it is shorter than the digest's 15:

> *"A reminder has the ±5-minute delivery budget of AD-7, so a dead worker's row has to come
> back quickly or the reminder is late. Re-sending is safe: the send key is the provider's
> idempotency key."*

**The retry is safe because the key is the same on both attempts.** The key lives in the row,
was minted at creation, and is never recomputed — so a reclaimed row sends with the identical
idempotency key and the provider collapses the duplicate.

### D3 — The sweep never imports `domain.quiet_hours`

AD-7: *"Quiet Hours are applied when `due_at` is **computed or recomputed**, deferring to the
window end — never as a skip at send time. A deferred send is silently moved, never dropped and
never re-delivered next day."*

Re-checking the window at send time is the bug the rule exists to prevent, and it is a
plausible one: "the user changed their quiet hours at 7am, this reminder is now inside the
window, don't send it." But `due_at` was **rewritten** when the quiet hours changed —
`reschedule_pending_for_user` does exactly that, in place, on `pending` rows, without touching
the key. So the stored `due_at` is already the answer. Re-checking would either double-shift
(a send deferred twice is a send that never leaves) or skip a send the user asked for.

A test asserts the import is **absent from the sweep module's source**, the same discipline as
`test_no_key_builder_accepts_a_time` in item 3: a rule the suite checks beats a rule everybody
has to remember.

### D4 — The send key is the provider's idempotency key, unchanged on every attempt

`EmailPort.send(message, *, stream, idempotency_key)` already takes the key. The sweep passes
`row.send_key` — the same string on the first attempt, on the retry after a provider error, and
on the retry after a worker crash.

**A `sent` row is never rekeyed** (AD-7). Nothing in the sweep writes `send_key`; it is not
even in the update set of the mark-sent statement, so the column cannot change by accident.

### D5 — Streams are read from the row, and the two kinds never share one

AD-20: *"Every send through the email port carries an explicit **stream**. Transactional mail
(reminders, state-change notices, auth) and bulk mail (the Pulse Digest) use **separate sending
streams and separate reputations**. A send with no stream is a type error, not a default."*

`ScheduledSend.stream` already carries the stream, and it has **no default** — the model
docstring says so, and `test_the_stream_is_stored_explicitly` pins it. The sweep reads it and
passes it through. It does not decide the stream from the kind, because the row is where the
decision was recorded at minting time.

The two kinds map as:

| Kind | Stream | Unsubscribe |
|---|---|---|
| `event_reminder`, `personal_reminder`, `state_notice` | `TRANSACTIONAL` | none |
| `digest` | `BULK` | **required** (RFC 8058) |

`EmailPort.send` already raises `ValueError` when a bulk send carries no unsubscribe URL. The
sweep supplies one for the bulk path — the URL comes from the **template layer** (item 6),
behind a seam this item defines and item 6 fills. The test asserts the bulk path supplies it,
which is the acceptance criterion; it does not assert a particular URL shape, because the shape
belongs to item 6.

**The two never share a stream**, and that is enforced at the port, not by convention: a
transactional send with a bulk unsubscribe URL is not a thing the port permits, and a bulk send
without one raises.

### D6 — A provider failure leaves the row `pending`, with a bounded attempt count

A provider failure is not a terminal state. It is a provider failure *this time*. The row goes
back to `pending`, `attempts` goes up, `last_error_kind` records **a kind, never the
provider's message** (a provider error can quote the recipient address — AD-13), and the next
sweep tries again.

The bound: `attempts` is compared against a limit, and a row that exhausts it becomes
`failed` — **recorded, not retried forever and not silently dropped**. `ScheduledSend.Status`
already has `FAILED` for this, and its docstring says exactly that:

> *"The provider refused past the attempt bound. Terminal and **recorded**: a row that exhausts
> its attempts is never retried forever and never silently dropped."*

The limit is a shared constant (`SEND_MAX_ATTEMPTS`), not a literal in the sweep, because the
retry policy is a product decision and AD-8 puts thresholds in `shared/constants.py`.

### D7 — A vanished target is cancelled, not sent, and never stops the batch

The row names a target by value (`target_kind`, `target_id`) — a personal event or a saved
public event. The target can disappear between minting and sending: the user un-saved the
event, deleted the personal event, or the event was cancelled and AD-17's propagation has not
run yet.

**The row is cancelled, not sent.** Sending a reminder about an event the user no longer has is
worse than not sending it. And **the row is cancelled, not deleted** — the record of what was
supposed to happen stays, which is what `Status.CANCELLED` is for.

**One bad row never stops the others.** Each row is sent in its own try/except. A provider
failure, a vanished target, a rendering error — all of them are recorded against that row and
the sweep moves on. The sweep's own summary log line reports the counts.

### D8 — The sweep renders a minimal, honest message; the template layer is item 6

This item is the **mechanism**. It proves the row goes out, exactly once, on the right stream,
with the right key.

The message body is therefore a seam, not a design: `apps/delivery/services/delivery_sweep.py`
asks a renderer for the message, and the renderer is the thing item 6 replaces with real
templates and the one-click unsubscribe endpoint. **The sweep's own contract — the claim, the
key, the stream, the mark — does not change when the templates do.**

The renderer needs three things: the recipient address, the subject and the body. The subject
and body come from the renderer; the **recipient address comes from `identity`**, through a
published read, because `delivery` may not import `apps.identity.models` (the `models-identity`
import-linter contract).

### D9 — The recipient address is read through `identity`'s published interface

AD-2's `models-identity` contract: *"only `apps.identity` imports `apps.identity.models` (others
call its services)"*. So the sweep cannot read `User.email` directly.

`identity` publishes `get_recipient_address(user_id)` — a read that returns the address or
`None`, and never anything else about the account. `None` means the account is gone, which is
the vanished-target case of D7.

**The address never reaches a log sink.** AD-13's allowlist (`adapters/logging/redaction.py`)
contains `user_id`, `idempotency_key`, `stream`, `send_id`, `slot`, `attempt` and `job` — and
nothing that could carry an address. The sweep's log lines use exactly those.

### D10 — The sweep is a `tick()` enqueue, and `tick()` still touches no database

`config/celery.py` sets `TICK_SECONDS = 60.0`, which already satisfies AD-7's *"≤60s
intervals"*. **There is no new `beat_schedule` entry.** The sweep is the enqueued job,
mirroring `schedule_sources`, `schedule_calendars` and `schedule_digests` exactly.

`tests/worker/test_tick.py` pins the beat schedule, `TICK_SECONDS` and the enqueue order, and
those tests still pass — the sweep is added to the enqueue list, and the pinned assertions are
about the schedule and the *relative* order of the existing jobs, so adding one more preserves
them.

**`tick()` still touches no database.** The sweep is enqueued, not run, from the tick. A slow
sweep cannot delay the next tick, because the tick's only work is `_enqueue` — which is a Redis
publish.

The sweep is **one task that sweeps a batch**, not one task per send. AD-7: *"A reminder is
**never** enqueued as a per-reminder Celery task at its due time."* The schedule lives in
Postgres; the broker carries the tick and the sweep.

### D11 — The batch is bounded and ordered by `due_at`

The query is bounded by a limit and ordered by `due_at`, then by id. The ordering matters
because a bounded batch that is not ordered drops the *newest* rows when there are more due
rows than the limit — the oldest due rows would wait for the next sweep, and they are the most
overdue. Ordering by `due_at` ascending sends the most overdue first.

The limit is a shared constant (`SEND_SWEEP_BATCH`), for the same reason `SCHEDULE_BATCH` and
`CALENDAR_SYNC_BATCH` are separate constants rather than one shared number: *"Two schedulers
pacing different work must not share a number, or a change to one silently changes the other."*

### D12 — The mark-sent statement is a guarded update, not a blind write

The final update is:

```
UPDATE ... SET status='sent', sent_at=now, claimed_at=NULL
WHERE id = <row> AND status = 'pending'
```

The `status = 'pending'` guard means the update affects zero rows if something else moved the
row in the meantime — and **zero rows affected is not an error**. It means another worker
already handled it, or a cancellation landed first. The sweep must not then write `sent` over a
`cancelled` row.

This is the same shape as AD-17's outbox rule: *"`propagated_at` only with
`EventStateChange.objects...filter(pk=…, propagated_at__isnull=True).update(...)`. A result of 0
means already propagated, not an error."*

The `sent_at` CHECK constraint (`scheduled_send_sent_at_pairs_with_status_ck`) is the
database's half of the same rule: a `sent` row with no `sent_at` is refused by Postgres.

---

## The send boundary, end to end

```
tick()                                   -- no database, 60s
  └─ _enqueue(sweep_due_sends)

sweep_due_sends                          -- one task, one batch
  ├─ claim_due_sends(now, limit)         -- SKIP LOCKED + claimed_at, commit
  └─ for each claimed row:
       ├─ resolve the recipient          -- identity's published read
       ├─ vanished?  → cancel the row    -- D7
       ├─ render the message              -- the seam item 6 replaces
       ├─ port.send(msg, stream=…, idempotency_key=row.send_key)   -- D4, D5
       ├─ provider raised?
       │    ├─ attempts < limit → back to pending, record the kind   -- D6
       │    └─ attempts == limit → failed, recorded                  -- D6
       └─ mark sent (guarded)                                        -- D12
```

---

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/apps/delivery/services/delivery_sweep.py` | create | The claim, the send, the mark; the sweep's whole mechanism |
| `backend/apps/identity/services/recipients.py` | create | The published read of a user's address (D9) |
| `backend/worker/tasks.py` | modify | The `sweep_due_sends` task and the tick's enqueue of it (D10) |
| `backend/shared/constants.py` | modify | `SEND_SWEEP_BATCH`, `SEND_MAX_ATTEMPTS` (D6, D11) |
| `backend/adapters/email/memory.py` | modify | Record the stream and key — it already does (no change needed) |
| `backend/tests/delivery/test_delivery_sweep.py` | create | The whole proof |
| `backend/tests/identity/test_recipients.py` | create | The published read |

**`adapters/email/memory.py` needs no change.** It already records `SentEmail(message, stream,
idempotency_key)` — every send with its key and its stream, which is exactly the test seam the
work item describes. The work item says *"If it does not already, extending it is part of this
item"* — it does already.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| The lock is held across the provider call | The batch serialises behind one slow provider; a dropped connection releases the lock mid-send | D1 — the lock is released before the network call; `claimed_at` carries the claim |
| Quiet Hours re-checked at send time | A send deferred twice never leaves; or a reminder the user asked for is skipped | D3 — the import is absent, and a test asserts it |
| The key is recomputed on retry | A second key means a second email | D4 — the key comes from the row and is never written by the sweep |
| The claim never expires | A worker crash silently deletes a reminder forever | D2 — the TTL, and a reclaim test |
| A provider error stops the batch | One user's bad address means nobody gets mail | D7 — per-row isolation |
| The attempt count is unbounded | A permanently-refused address is retried forever | D6 — the bound, and a `failed` row that is recorded |
| A vanished target is sent | A reminder about an event the user removed | D7 — cancelled, not sent |
| An address reaches a log | AD-13 violation | D9 — the allowlist; a test greps the log output for the address |
| The tick grows a database read | A slow sweep delays the next tick | D10 — the tick enqueues and returns |

---

## Implementation Checklist

- [ ] `delivery_sweep.py` — the claim (D1, D2), the send (D4, D5), the mark (D12)
- [ ] The sweep never imports `domain.quiet_hours` (D3), and a test asserts it
- [ ] The send key is the provider's idempotency key, unchanged on every attempt (D4)
- [ ] The stream comes from the row; the bulk path supplies an unsubscribe URL (D5)
- [ ] A provider failure returns the row to `pending`; the bound makes it `failed` (D6)
- [ ] A vanished target is cancelled; one bad row never stops the batch (D7)
- [ ] The message body is a seam the template item replaces (D8)
- [ ] The recipient is read through `identity`'s published interface (D9)
- [ ] `sweep_due_sends` is enqueued by the existing `tick()`; no new beat entry (D10)
- [ ] The batch is bounded and ordered by `due_at` (D11)
- [ ] The mark is a guarded update; zero rows affected is not an error (D12)
- [ ] Concurrency test: two workers, one send, against real Postgres
- [ ] Crash-and-reclaim test: a dead worker's row becomes claimable again
- [ ] Provider-failure test, idempotency-at-the-boundary test, both-streams test
- [ ] Vanished-target test, log-redaction test, index-used test
- [ ] `manage.py check`, `makemigrations --check`, `lint-imports`, full suite

---

*Checkpoint 1 — approved 2026-10-31.*
