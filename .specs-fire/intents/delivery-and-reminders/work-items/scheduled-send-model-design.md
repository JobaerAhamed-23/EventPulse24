---
id: scheduled-send-model
title: SCHEDULED_SEND — design
intent: delivery-and-reminders
mode: validate
created: 2026-10-31
checkpoint_1: approved
checkpoint_1_at: 2026-10-31T13:25:00Z
---

# Design: `ScheduledSend`

One model in `apps/delivery/models.py`, in the `personal` schema, written only by `delivery`
(AD-16). One row per intended send: what it is, who it is for, when it is due, and the key
that makes at-least-once delivery safe.

**The table AD-7 was written around, and which has never existed.** It appears in this
repository only inside docstrings — `apps/delivery/__init__.py` and
`services/reminder_plans.py` both name it as though it were there. Every other piece of the
delivery story was built against a hole.

## The spine's own words

AD-7: *"Reminders and Pulse Pings dispatch from a worker sweeping a `(due_at, status)` index
at **≤60s intervals**... Every send carries a stable idempotency key... delivery is
at-least-once with dedupe at the send boundary."*

AD-7: *"The key is minted **once**, when the `SCHEDULED_SEND` row is created, stored under a
unique constraint, and **never derived from `due_at`**."*

AD-7: *"Quiet Hours, timezone, digest-time and tier changes **rewrite `due_at` on `pending`
rows only and never touch the key**, so a recompute can never produce a second send."*

AD-7: *"`SCHEDULED_SEND` rows in Postgres are the sole source of truth for what is due...
a total Redis loss costs in-flight pipeline jobs, never a user's reminder."*

---

## Decisions

### D1 — The key is one stored column, and the reason it is not derived is the whole design

`send_key`, a `CharField` under a `UniqueConstraint`, built once at row creation by joining
parts with `shared.constants.SEND_KEY_SEPARATOR` (`:`), per the coding standard that already
exists for it: *"never `-` or `_`. That keeps each UUID a 36-character run, so keys survive
log scrubbing."*

The shapes are AD-7's table, unchanged:

| Kind | Key |
|---|---|
| `event_reminder` | `user_id : event_reminder : event_id : slot : event_version` |
| `personal_reminder` | `user_id : personal_reminder : personal_event_id : slot : personal_event_revision` |
| `state_notice` | `user_id : state_notice : state_change_id` |
| `digest` | `user_id : digest : local_date` |
| `pulse_ping` | *(reserved, never minted — see D2)* |

**Why it must not come from `due_at`.** Four ordinary user actions rewrite `due_at` on pending
rows: changing quiet hours, changing timezone, changing the digest delivery time, and editing a
plan. If the key moved with the time, **each of those would mint a second send**, and a user
who adjusted their settings three times would get four copies of the same reminder. The key is
the identity of *the thing being sent*, not of *when*.

**Length.** The longest shape is a personal reminder with a custom slot:
36 + 1 + 17 + 1 + 36 + 1 + 43 + 1 + 10 ≈ 146 characters. `max_length=255`, with the arithmetic
in a comment so a future slot format has visible headroom.

### D2 — `pulse_ping` exists in the enum and is never minted

Decided with the user on 2026-10-31: **in MVP the digest email *is* the Pulse Ping.** FR-9's
Out of Scope is explicit that MVP is "email digest only", and PRD SM-2 measures the two as one
thing.

So MVP mints the `digest` key and not `pulse_ping`. The member stays in the enum with a comment
saying it is reserved for the Phase 2 push channel — **so a later reader sees a deliberate
reservation rather than an omission**, and so AD-7's table is still legible against the code.

A test asserts nothing in the tree mints it.

### D3 — Status machine: four states, and the database holds the parts it can

```
                 ┌──────────┐
                 │ pending  │  ← the only state the sweep looks at
                 └────┬─────┘
          ┌───────────┼───────────┐
          ▼           ▼           ▼
      ┌──────┐   ┌──────────┐  ┌────────┐
      │ sent │   │cancelled │  │ failed │
      └──────┘   └──────────┘  └────────┘
         all three terminal — never reopened, never rekeyed
```

- **`pending`** — a promise. AD-7's premise is that a pending row *will* be sent.
- **`sent`** — terminal. Never rekeyed, never re-timed, never resurrected.
- **`cancelled`** — the event moved, was cancelled, was un-saved, or the user unsubscribed.
- **`failed`** — the provider refused past the attempt bound. Terminal and **recorded**, because `delivery-sweep-and-send` requires that a row exhausting its attempts "is recorded, not retried forever and not silently dropped".

**The transitions are enforced in the service, not by a trigger.** `delivery` is the single
writer (AD-16) and the sweep is the only mutator of status, so a trigger would add a plpgsql
function and a migration to re-state a rule one module already owns. This repo reserves
triggers for *append-only* tables, where the guarantee has to survive any writer. Pinned by
tests instead, and the model docstring says which layer holds the rule.

**What the database does hold** is the pairing that a status alone cannot express:

```sql
CHECK ((status = 'sent') = (sent_at IS NOT NULL))
```

A `sent` row with no `sent_at`, or an unsent row carrying one, is a lie about whether a user
received an email. That is worth a constraint.

### D4 — The index: a partial index on pending rows ✅ **decided 2026-10-31**

AD-7 says "sweeping a `(due_at, status)` index". The sweep's actual query is:

```sql
WHERE status = 'pending' AND due_at <= now()
```

Three candidates:

| Option | Shape | Trade-off |
|---|---|---|
| **A** | `Index(fields=["due_at", "status"])` — AD-7's literal wording | Range column first, so the equality on `status` cannot be used to seek; Postgres scans a `due_at` range and filters. Works, grows forever. |
| **B** | `Index(fields=["status", "due_at"])` | Equality first, then range — the textbook order. Still indexes every `sent` row ever written. |
| **C** | `Index(fields=["due_at"], condition=Q(status="pending"))` — **recommended** | Indexes only the pending set, which is naturally tiny and roughly constant, while `sent` rows accumulate forever. The index stays small permanently and never indexes a row the sweep will not look at. |

**Why this needs your decision rather than mine.** The constitution says ADs "are invariants,
not suggestions; deviating requires amending the spine first." Option C is, I'd argue, *within*
AD-7's intent — the AD's point is "the sweep reads a due index rather than scanning the table",
and C satisfies that better than A does. But it is not AD-7's literal words, and I would rather
you decide that than have me quietly reinterpret a spine rule.

There is also no partial-index precedent anywhere in this codebase yet, so C would be the first.

**Decided with the user: option C.** The partial index is read as serving AD-7's intent —
"the sweep reads a due index rather than scanning the table" — which C satisfies more completely
than A does, since it never indexes a row the sweep will not look at. This is the codebase's
first partial index; the migration comment records that and why, so the next one has a
precedent to point at rather than rediscovering the argument.

No spine amendment is raised: AD-7's subject is *where the schedule lives and how it is swept*,
not the btree column order. If a reviewer disagrees, the index can be changed by a migration
alone — it touches no row and no key.

### D5 — The retention category ✅ **decided 2026-10-31**

The table holds two different kinds of fact and `shared/retention.py`'s categories do not have
one that covers both:

- a **pending** row is a *future intention* — it must survive until it fires;
- a **sent** row is a *delivery event* — PRD §10.2 gives those 90 days, then aggregates.

`EMAIL_DELIVERY_EVENTS` is the obvious name, and **it is dangerous here**: a 5-day reminder for
an event eight months out sits `pending` for eight months, and a 90-day purge measured from
creation would **delete the reminder before it ever fired**. Silently. The user would simply
never be reminded, and nothing would look broken.

| Option | Effect |
|---|---|
| **A — `ACCOUNT_CONTENT`** (recommended) | Matches `ReminderPlan`, which this table is derived from. Nothing is ever purged early. Cost: `sent` rows outlive the 90-day email-events policy, so this is a privacy-policy drift to be closed later. |
| **B — `EMAIL_DELIVERY_EVENTS`** | Policy-accurate for sent rows, **and will silently drop long-lead pending reminders**. I do not recommend this. |
| **C — `ACCOUNT_CONTENT` + a status-aware prune** | Correct on both halves: retained as account content, with the retention sweep pruning `sent` rows at 90 days. Costs a sweep change that belongs to this item rather than a later one. |

**Decided with the user: option A, with C recorded as a known follow-up.**
`ACCOUNT_CONTENT`, matching `ReminderPlan`, which this table is derived from. It is the only
option with no path to losing a user's reminder.

The cost is accepted and must not be forgotten: **`sent` rows will outlive PRD §10.2's 90-day
email-delivery-events policy.** That is a documented retention drift, not a silent one. It is
written into the model docstring, carried into the intent brief's follow-ups, and belongs to
whichever later item touches the retention sweep. A reader who finds `ACCOUNT_CONTENT` here and
wonders why it is not `EMAIL_DELIVERY_EVENTS` will find the answer in the docstring.

### D6 — `event_version` appears twice, deliberately

AD-7: *"`event_version` and `personal_event_revision` are the values **at minting**;
propagation may re-stamp a row's working `event_version` column (AD-17) but never its key."*

So the row carries:

- the version **inside `send_key`** — frozen at minting, part of the identity;
- a **working `event_version` column** — which AD-17 propagation re-stamps.

They are allowed to differ, and the difference is meaningful: it says "this row was minted
against version N, and the event has since moved to version M". A test asserts a re-stamp
changes the column and leaves the key byte-identical.

This is the mechanism behind AD-7's subtlest sentence: a moved event cancels the old pending
rows and mints new ones, so *"the old key stays spent, so a `1d` reminder already sent for the
old date does not block the `1d` reminder for the new one."*

### D7 — The row carries routing, not a rendered body

The row holds what the sweep needs to *route* a send — kind, user, target by value
(`target_kind` + `target_id`, the `ReminderPlan` convention), slot, stream, due time. It does
**not** hold a rendered subject and body.

**Why not denormalise the body.** A stored body is a copy of facts that live elsewhere, and
every copy can go stale; a venue correction that does not bump `event_version` would leave a
pending reminder carrying the old address with nothing to detect it.

**How "no second round trip per row" is still met:** the sender batch-loads the bodies for a
whole sweep batch, not per row — the same move `conflict-list-api` already uses
(`get_public_events(event_ids=…)`, one catalog query for many ids). The requirement is a bound
on queries *per row*, and batching meets it while keeping bodies current.

### D8 — The claim is a column, because the lock cannot span the provider call

The sweep claims with `SELECT … FOR UPDATE SKIP LOCKED`, but **must not hold the row lock
across the network call** to the email provider — that would hold a transaction open for the
provider's latency and cap throughput at the connection pool.

So the claim is also recorded as `claimed_at`, exactly as `DigestPreference.digest_claimed_at`
and `CalendarConnection.sync_claimed_at` already do, with the same reading: null means
unclaimed, and a claim older than a TTL is a dead worker's row and becomes claimable again. The
existing precedent is followed rather than re-invented.

Attempt accounting rides alongside — `attempts`, `last_attempt_at`, `last_error_kind` —
mirroring `CalendarConnection`'s error columns. `last_error_kind` is a **kind**, never the
provider's message, which can contain a recipient address (AD-13).

---

## Data Model

```python
class ScheduledSend(UUIDv7Model):
    retention_category = RetentionCategory.ACCOUNT_CONTENT      # D5

    class Kind(models.TextChoices):
        EVENT_REMINDER = "event_reminder"
        PERSONAL_REMINDER = "personal_reminder"
        STATE_NOTICE = "state_notice"
        DIGEST = "digest"
        PULSE_PING = "pulse_ping"       # reserved, never minted in MVP (D2)

    class Status(models.TextChoices):
        PENDING = "pending"
        SENT = "sent"
        CANCELLED = "cancelled"
        FAILED = "failed"

    user_id = models.UUIDField()                      # by value (OQ-8)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    send_key = models.CharField(max_length=255)       # minted once, unique (D1)

    target_kind = models.CharField(max_length=16, blank=True, default="")
    target_id = models.UUIDField(null=True, blank=True)
    slot = models.CharField(max_length=64, blank=True, default="")
    event_version = models.PositiveIntegerField(null=True, blank=True)   # working (D6)

    stream = models.CharField(max_length=16)          # AD-20, no default
    due_at = models.DateTimeField()                   # post-Quiet-Hours (AD-7)
    status = models.CharField(max_length=16, default=Status.PENDING)
    sent_at = models.DateTimeField(null=True, blank=True)

    claimed_at = models.DateTimeField(null=True, blank=True)             # D8
    attempts = models.PositiveSmallIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error_kind = models.CharField(max_length=32, blank=True, default="")

    created_at / updated_at
```

### Constraints and indexes

```sql
UNIQUE (send_key)                                  -- D1: the whole point
CHECK  ((status = 'sent') = (sent_at IS NOT NULL)) -- D3
INDEX  (due_at) WHERE status = 'pending'           -- D4, pending your call
INDEX  (user_id)                                   -- rewrite-all-of-a-user's-pending-rows
INDEX  (user_id, kind, status)                     -- "does this user have a digest today?"
```

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/apps/delivery/models.py` | modify | Add `ScheduledSend` |
| `backend/apps/delivery/migrations/0003_scheduledsend.py` | create | Table, constraints, indexes |
| `backend/shared/constants.py` | modify | Send-kind strings if shared; claim TTL |
| `backend/tests/delivery/test_scheduled_send.py` | create | Constraints, key stability, status machine |
| `backend/tests/delivery/factories.py` | modify | `ScheduledSendFactory` |
| `backend/tests/architecture/test_write_ownership.py` | modify | Claim `delivery_scheduledsend` for `delivery` |
| `backend/.importlinter` | check | `models-delivery` already covers the new model |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| A key derived from `due_at` slips in later | Duplicate sends on every preference change | A test rewrites `due_at` and asserts the key is byte-identical; the model docstring states the rule where a reader will hit it |
| Retention purges a long-lead pending reminder | **A user silently never gets reminded** | D5 — `ACCOUNT_CONTENT`, never the 90-day category; called out at checkpoint 1 rather than chosen quietly |
| The status machine drifts because it lives in the service | A resurrected `sent` row double-sends | Single-writer discipline (AD-16) + transition tests + the `sent_at` CHECK |
| `last_error_kind` grows into a message | Recipient address in a log (AD-13) | It is a `kind`, capped at 32 chars; a test asserts no address reaches the column or the logs |
| The ownership map is forgotten | Full-suite failure | Already known from item 2 — `test_write_ownership.py` is updated in the same commit |

## Implementation Checklist

- [ ] `ScheduledSend` model with the fields, constraints and indexes above
- [ ] `Kind` and `Status` as `TextChoices`; `PULSE_PING` present with its reservation comment
- [ ] Send-key builder, one function, joining on `SEND_KEY_SEPARATOR`, with all four MVP shapes
- [ ] Migration, including the `sent_at` CHECK and the chosen index shape
- [ ] `ScheduledSendFactory`
- [ ] Register `delivery_scheduledsend` in `TABLE_OWNERS`
- [ ] Tests: unique key rejects a duplicate; `due_at` rewrite preserves the key; every legal and illegal status transition; the `sent_at` CHECK; two rows differing only by `event_version` both exist; the index is used by the sweep's predicate; `pulse_ping` is never minted
- [ ] `manage.py check`, `makemigrations --check`, `lint-imports`, full suite

---
*Checkpoint 1 — awaiting approval.*
