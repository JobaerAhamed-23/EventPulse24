---
id: digest-scheduling
title: Composition scheduling from the single tick
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: completed
depends_on: [digest-composition-service]
created: 2026-10-31
---

# Design: Composition scheduling from the single tick

## The problem

The composition service exists and is deterministic. Nothing **runs** it. A user who
finishes onboarding lands on an empty home, and the first digest they ever see is one
the scheduler happened to produce overnight — or, if the scheduler does not exist, never.

This item adds the schedule. It has to satisfy four things at once:

1. **AD-7 — one tick, no platform cron.** `config/celery.py` has exactly one
   `beat_schedule` entry and `tests/worker/test_tick.py` pins it. The digest's schedule
   hangs off that tick like every other periodic job.
2. **AD-11 — no long work in a request.** Composing a digest reads three candidate
   pools and scores them. It is worker work, and a request handler's job is to
   "validate, enqueue, and return".
3. **FR-1 — a new user's home is never empty.** The first digest is composed as soon as
   onboarding completes, not at tomorrow's delivery time.
4. **Per-user delivery time.** The user's digest is composed *at or before* their local
   delivery time, so it exists when they arrive.

---

## The decisions

### D1 — The dispatcher is a claiming dispatcher, exactly like `schedule_calendars`

The work item names the pattern, and the codebase already has two instances of it
(`schedule_sources`, `schedule_calendars`). The new one is the third:

```
tick → schedule_digests → claim due users → enqueue one compose job per claim
```

**Why the claim, and not a query-then-enqueue.** Two workers ticking at once must not
compose the same user's digest twice. The claim is taken under a **row lock**
(`SELECT … FOR UPDATE SKIP LOCKED`), so the two dispatchers are serialised: the second
one waits for the first to commit, and then re-reads the row and finds it already
claimed. This is AD-7's "single writer" rule applied to the digest.

**`SKIP LOCKED` is the liveness half, not the correctness half.** With the lock and
without `SKIP LOCKED`, the second dispatcher would *block* on the row the first is
holding — and would still find it claimed when it woke up. `SKIP LOCKED` is what stops
it blocking: the dispatcher moves on to the next user instead of waiting.

The concurrency test was checked against a broken implementation, and the distinction
is the honest one: removing the **row lock** makes it fail (the user is claimed
twice); removing only `SKIP LOCKED` makes it still pass.

**The claim needs a column.** The existing dispatchers claim a column on the row they
are scheduling (`Source.ingest_claimed_at`, `CalendarConnection.sync_claimed_at`).
`DigestPreference` has no such column, so one is added: `digest_claimed_at`.

**Why the preference row and not the digest row.** A digest is per `(user, local_date)`,
and the thing being scheduled is the *user's daily digest* — the local date is computed
from the preference's timezone, and the due time comes from the preference's delivery
time. The preference is the row that holds both. It is also one row per user, so
claiming it is claiming the user's daily composition.

**A user with no preference is never due.** A digest needs a local date, and the local
date needs a zone. Without a preference there is no zone, and the default zone would
mean composing in UTC for a user we know nothing about. The dispatcher therefore only
considers users who have a preference — which is every user who finished onboarding.

### D2 — "Due" is a local wall clock, and the composition happens at or before it

The user's `DigestPreference` holds a **local wall clock** (`delivery_time`, an
`HH:MM`) paired with an IANA `timezone`. "9am" means 9am in the user's own zone, and
it must stay 9am after a DST change — which is exactly why the pair is stored rather
than a UTC instant.

**So "due" is computed in the user's zone, not in UTC.** The dispatcher's rule is:

> a user is due when **the local wall clock in their zone has reached their delivery
> time**, and they have no digest for the local date yet.

The first half is a comparison in the user's zone. The second is the real guard: even
if the due-time rule said yes, a user who already has a digest for today is not due
again.

**The composition is at or before the delivery time, and it does not send anything.**
The digest *exists* before the user arrives, so the home screen has something to show.
The **send** is the delivery intent's job — this item composes, it does not deliver.

**The date comparison is the user's local date, and it is computed by the shared rule.**
`local_date_for(now, zone_name)` already exists and is shared with the composition
service and the read API. The dispatcher uses it too — three callers of one rule, so
"today" cannot mean three different days.

**The DST boundary is where a naive implementation breaks.** The due-time comparison is
a *local wall clock* comparison, so it is computed by **converting `now` into the
user's zone** and comparing the resulting local time-of-day against `delivery_time`.
That is DST-correct by construction: on the day the clocks go forward, 9am local is
still 9am local, and the instant it corresponds to moves.

**A user whose delivery time has already passed today is due immediately.** If it is
14:00 local and the user's delivery time is 9:00, they are due now — the dispatcher
must not wait until tomorrow.

**The comparison is between two *naive* wall clocks.** The conversion gives the local
time-of-day; the comparison is against the preference's `HH:MM`, which carries no
offset. So the converted time must be **naive** too — `timetz()` would return an
*aware* time, and comparing an aware time with a naive one does not raise in Python:
it orders them by their UTC equivalents, and the answer would be silently wrong. (This
is not a hypothetical — the first implementation used `timetz()`, and the test that
pinned the inclusive boundary caught it.)

### D3 — The dispatcher's selection is bounded and ordered

The dispatcher claims at most `DIGEST_DISPATCH_BATCH` users per run, ordered by the
user id (a UUIDv7, so the id **is** the creation time — the oldest preference is
claimed first, so a new user is never starved behind a backlog).

**The bound is a constant, not a literal** (AD-8), and it is **not** shared with
`SCHEDULE_BATCH` or `CALENDAR_SYNC_BATCH`: those pace ingestion and calendar fetches,
which are per-*source* and per-*connection*. This paces per-*user* digest composition,
which is a different unit of work and a different cost.

### D4 — The claim is released whatever happens

The existing pattern, exactly: the claim is released in a `finally`, so a job that
crashes, a job that is refused, and a job that cannot be enqueued all release it, and
the next tick retries.

**A claim older than the TTL is a lost job** (a worker died) and becomes claimable
again. The TTL is its own constant, sized to the composition: a composition reads three
candidate pools and scores them — minutes, not hours.

### D5 — The first digest is enqueued from the onboarding completion, not polled for

FR-1 promises an authenticated Pulse Digest within 30 seconds of sign-up. A user who
finishes onboarding must not land on an empty home waiting for tomorrow's tick.

**The job is enqueued from the onboarding-completion path.** There are three ways
onboarding completes — `advance_step` past the last step, `skip_step` on the last
step, and `skip_all` — and all three must enqueue it. A user who skipped everything
has still finished onboarding, and the default preference is written, so they have a
zone and a delivery time.

**Why enqueue and not compose.** AD-11: a request handler's job is to "validate,
enqueue, and return". Composing inside the request would do the work — three reads and
a scoring pass — in the request path.

**Why enqueue and not poll.** The alternative is a "users with no digest at all"
dispatcher, which would re-check every user forever and would compose a digest for a
user who has not finished onboarding. The enqueue is precise: it fires exactly when
the precondition appears.

**The enqueue happens *after* the transaction commits.** A job enqueued inside the
transaction would find no preference yet — the worker's transaction would not see it —
and would compose nothing. So the enqueue is after the command returns.

**The composition is idempotent anyway**, so a lost or duplicated enqueue is harmless:
the service returns the existing digest with `created=False` and writes nothing.

### D6 — The management command composes on demand

`manage.py compose_digest` — for one user (`--user-id <uuid>`), or for every user whose
delivery time has arrived (`--all`). It is **idempotent**, because the composition
service is: re-running it for a user who already has today's digest returns the
existing one and writes nothing.

**`--all` asks the scheduler's own rule.** The command calls `claim_due_digests`, so
"everyone who is due right now" means exactly what the dispatcher means by it, in the
user's own local wall clock. The command does not have a second, looser idea of "due" —
and it releases the claims it took, so it cannot leave a user claimed until the TTL
expires.

**`--user-id` composes whether or not the user is due.** A user named on the command
line is composed on demand: the point of the command is to answer *this* user's
request, not to test the schedule.

It exists for operating and for local development: "compose this user's digest now" is
the question an operator asks when a user says their digest is empty.

### D7 — Nothing in a request path calls the composition service

AD-11's rule is a *structural* one, and the work item asks for a test that asserts it.
The test checks the API modules and asserts the composition is absent: the API may
**enqueue** the composition, but it may not **call** it.

**The distinction is the point.** `compose_digest` is the service; `compose_digest_task`
is the worker job; the API calls neither — it hands the work to the worker.

**The check is on the *call*, not on the import — and it had to be.** The design
originally said "greps the API modules for the composition service". That would have
been the wrong check, for two reasons:

1. **It would be vacuous.** The worker legitimately imports the composition, so an
   import-based rule needs an exemption list — and a list of exemptions is a list of
   holes, one per new API module.
2. **The enqueue is reachable from a request handler by design.** The onboarding path
   calls `enqueue_digest_composition`, and that module's own name contains
   `digest_composition` as a substring. A text search would flag the seam for its own
   function name.

So the check is **AST-based and call-based**: it reports a module that *calls*
`compose_digest`, and it does not report a module that merely imports the enqueue.
The API module list is **discovered** — every `api.py` and `*_api.py` under `apps`,
plus `config/api.py` — so a new API module is covered the moment it exists.

**And the boundary is a direction, not an absence.** A rule that forbade the
composition *everywhere* would be satisfied by a tree where no digest was ever
composed — and the user's digest would simply never appear. So there is a second
test: the worker *must* still compose it. AD-11 moves the work out of the request
path, not out of the system.

### D8 — The audit row carries no PII

The claim's audit row says *that* a user was claimed, and the job's log line says
*which job* failed. Neither carries an email, a city, or a delivery time (AD-13). The
user id is already one indexed read away, and it is a UUID, not a name.

### D9 — The tick's docstring is extended, in the same spirit

The tick's docstring documents its own nesting carefully ("the two cadences nest —
every multiple of 15 is also a multiple of 5 … if the two are ever made independent,
the tick test that pins the enqueue order will say so"). The new dispatcher's cadence
**does not nest** — it runs on **every** tick, because "due" is a per-user local
comparison, not a minute-modulo rule — and the docstring says so, in the same spirit.

**And the tick's pinned enqueue table grows a row in every case.** The existing test
(`tests/worker/test_scheduling_tasks.py`) pins the tick's enqueue order minute by
minute, and the digest dispatcher now appears in **every** row of it. That is the
point: the two cadences that *do* nest — the reconciler's five minutes and the
refresh's fifteen — are the ones that vary, and the digest dispatcher is the one job
that is always there.

### D10 — The concurrency test is checked against a broken implementation

The acceptance criterion is explicit: "A test exercises the concurrent path rather
than assuming the constraint covers it." So two real dispatchers race in two real
threads over a real committed row (`transaction=True`, because without a commit the
second thread cannot see the first thread's rows and the test passes vacuously).

**The test was then checked against a broken implementation**, and the result is worth
recording: removing the **row lock** makes it fail — the user is claimed twice —
while removing only `SKIP LOCKED` leaves it passing. So the correctness mechanism is
the lock, and `SKIP LOCKED` is the liveness half.

That distinction is worth stating in the test itself, because a reader who assumed
`SKIP LOCKED` was the guarantee would be wrong about which line to keep if the code
were ever changed.

---

## The decision table

| # | Decision |
|---|---|
| D1 | The dispatcher is a claiming dispatcher, like `schedule_sources` and `schedule_calendars`: a row lock (`SELECT … FOR UPDATE SKIP LOCKED`) on a `digest_claimed_at` column on `DigestPreference`, and a TTL for a lost job |
| D2 | "Due" is the user's local wall clock reaching their delivery time, **and** no digest for the local date yet. The composition is at or before the delivery time and **sends nothing** |
| D3 | The dispatch is bounded by `DIGEST_DISPATCH_BATCH` and ordered by the user id, so the oldest preference is claimed first |
| D4 | The claim is released in a `finally`, whatever happens; a claim older than `DIGEST_CLAIM_TTL` is a lost job and becomes claimable again |
| D5 | The first digest is enqueued from all three onboarding-completion paths, after the transaction commits |
| D6 | A management command composes on demand, for one user or for all of them, idempotently |
| D7 | No request handler calls the composition service; a test asserts the API modules do not import it |
| D8 | The audit row and the log line carry no PII — the job name and the user id, nothing else |
| D9 | The tick's docstring is extended to document that the digest dispatcher's cadence does **not** nest, and the tick's pinned enqueue table grows a row in every case |
| D10 | The concurrency test races two real dispatchers in two real threads, and it was checked against a broken implementation — the **row lock** is the correctness mechanism, `SKIP LOCKED` is the liveness half |

---

## What the code review changed

### D2 — the local time must be **naive**, and the first implementation was not

The review found the one bug in this item that a passing test would not have caught on
its own: `_local_time` used `timetz()`, which returns an *aware* time carrying the
zone's offset.

**Python does not raise when an aware time is compared with a naive one.** It orders
them by their UTC equivalents and answers. So the comparison
`timetz() >= delivery_time` did not raise `TypeError` — it returned the **wrong
answer**, quietly, for every user in every zone whose offset is non-zero. A user in
Los Angeles asking for 09:00 was read as due only from 17:00 UTC, because the
offset-bearing "09:00 PST" was compared as if it were 17:00.

The fix is `.time()` instead of `.timetz()`: the conversion already accounts for the
offset, and carrying it into the comparison would apply it twice.

**The test that caught it** is the inclusive-boundary one — "a user is due exactly at
their delivery time" — and it caught it because the test's own `NOW` was chosen to be
09:00 *local*. A test that had used a fixed UTC hour would have agreed with the broken
implementation.

### D2 — the test's `NOW` was wrong, and the design's DST claim was checked against the calendar

The first `NOW` was 16:00 UTC, described as "09:00 in Los Angeles". It is not — PST is
UTC−8, so 09:00 Pacific is 17:00 UTC. The review checked the offsets rather than
trusting the comment.

**And the spring-forward date was wrong too.** The design said "2026-03-08 is the US
spring-forward" and then used 17:00 UTC as 09:00 PST on that date — but the transition
happens at 02:00 local *on* 2026-03-08, so that morning is already PDT. The two 9ams
are 2026-03-07 at 17:00 UTC and 2026-03-09 at 16:00 UTC, and the test now says so.

The review also added a test for the property that actually matters: **the two 9ams
are different instants** (`after - before == 2 days − 1 hour`). That is what a naive
implementation gets wrong, and pinning the two instants separately would not have said
it.

### D7 — the boundary check is on the *call*, not the import

The design said "the test greps the API modules for the composition service and
asserts it is absent". The implementation is AST-based and call-based, for the two
reasons set out above. The import-based version would have been vacuous (the worker
legitimately imports it, so the rule needs an exemption list) and would have flagged
the enqueue seam for its own name.

**And the boundary is a direction, not an absence** — a second test pins that the
worker *must* still compose the digest, so a tree that satisfied the first rule by
composing nothing would fail.

### D6 — the command's `--all` uses the scheduler's own rule, and releases its claims

The first implementation had `--all` iterate every preference itself. That would have
been a **second, looser idea of "due"** — the exact drift `local_date_for` was promoted
out to prevent. It now calls `claim_due_digests`, so "everyone due" means what the
dispatcher means by it.

It also releases the claims it takes, in a `finally` — a command that claimed a user
and crashed would leave them claimed until the TTL expired, delaying their digest by
a quarter of an hour for no reason.

### D5 — the enqueue is registered on the `personal` alias

`transaction.on_commit(..., using=PERSONAL)` rather than the default. The callback
belongs to the transaction that wrote the rows, and the rows live in the `personal`
schema. A test pins the alias.

### D9 — the tick test's expected job list grew a row

The tick's enqueue order is pinned minute by minute in
`tests/worker/test_scheduling_tasks.py`, and the digest dispatcher appears in **every**
row of that table. That is the point: the digest cadence does not nest, so it is the
one job that is always there.

**What the review checked and left alone**

- **The claim lives on `DigestPreference`, not on `PulseDigest`.** The reasoning holds:
  the local date and the delivery time are both on the preference row, and it is one
  row per user.
- **A user with no preference is never due.** The composition service *would* cope
  (it falls back to UTC and no city), but composing for a user who has told us nothing
  is not the dispatcher's job — the default zone would mean composing in UTC for
  someone we know nothing about.
- **The `DIGEST_CLAIM_TTL` is 15 minutes.** A composition reads three candidate pools
  and scores them — minutes, not hours — so the TTL is generous rather than tight.
- **The audit row carries the claim time and the user id, and nothing else.** No
  email, no city, no delivery time (AD-13).
