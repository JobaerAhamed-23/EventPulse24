# Review report: `digest-scheduling`

**Work item**: `digest-scheduling`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-31

---

## The verdict

**Approved.** The schedule does what the item asked, and it does it as worker work: the
request path enqueues and returns, and the composition happens on the tick.

The review changed **six** substantive things. One of them was a **silent correctness
bug** that a passing test would not have caught on its own — the aware/naive time
comparison — and one of them was a **design that had to be rewritten**, because the
boundary test it asked for would have been vacuous.

The review also added a **concurrency test** and then **checked it against a broken
implementation**, which turned up a distinction the design had wrong: the **row lock**
is the correctness mechanism, and `SKIP LOCKED` is the liveness half.

The design's central claim survived contact with the implementation: **the digest is
composed because the user's own wall clock reached their delivery time**, and the test
that proves it is one that pins two 9ams a year apart and shows they are different
instants.

---

## What the review checked

| Property | How | Result |
|---|---|---|
| the schedule hangs off the single tick | the beat schedule is asserted to be exactly one 60-second entry, and the tick's enqueue list is pinned minute by minute | green |
| the digest dispatcher's cadence does **not** nest | five ticks produce five dispatcher enqueues | green |
| "due" is the user's local wall clock | one UTC instant, two zones, two answers | green |
| the comparison is inclusive | 09:00:00 is due | green |
| the comparison is DST-correct | the two 9ams are different instants, `after − before == 2 days − 1 hour` | green |
| the dispatcher is bounded | `DIGEST_DISPATCH_BATCH` | green |
| the dispatcher is fair | ordered by the user id — a UUIDv7, so the id is the creation time | green |
| two dispatchers never claim the same user | two real threads over a committed row; the test was checked against a broken implementation | green |
| a lost job becomes claimable again | a claim older than the TTL | green |
| a broker outage frees the claim | the dispatcher releases it, and the next tick retries | green |
| a crash frees the claim | the release is in a `finally` | green |
| a failure reaches Celery | the job re-raises | green |
| the enqueue happens after the commit | the callback is *registered*, not performed | green |
| a broker outage does not fail the onboarding | `robust=True`, and the command's return value is unaffected | green |
| the enqueue carries only the user id | one argument, a UUID | green |
| no request handler composes | an AST, call-based check over the nine discovered API modules | green |
| the worker still composes | the boundary is a direction, not an absence | green |
| the log lines carry no PII | the job name and the error type; the user id is a UUID | green |
| the audit row carries no PII | the actor is `system` / `digest_scheduler` | green |
| the API surface is unchanged | the OpenAPI contract regenerates with no diff | green |

---

## The six changes the review made

### 1. The local time must be **naive**, and the first implementation was not *(D2)*

**This is the one that mattered.** `_local_time` used `timetz()`, which returns an
**aware** time carrying the zone's offset. The preference's `delivery_time` is a
**naive** `HH:MM` wall clock.

**Python does not raise when an aware time is compared with a naive one.** It orders
them by their UTC equivalents and answers. So `timetz() >= delivery_time` returned the
**wrong answer** — quietly, for every user in every zone with a non-zero offset. A Los
Angeles user asking for 09:00 read as due only from 17:00 UTC, because the
offset-bearing "09:00 PST" was compared as if it were 17:00.

The fix is `.time()` instead of `.timetz()`: the conversion already accounts for the
offset, and carrying it into the comparison applies it twice.

**What made it catchable** is worth recording. The test that caught it —
`test_a_user_is_due_exactly_at_their_delivery_time` — pins the *inclusive boundary*,
and it caught the bug because the test's `NOW` is chosen to be 09:00 **local**. A test
that had used a fixed UTC hour would have agreed with the broken implementation. The
lesson is that a wall-clock rule needs a wall-clock fixture.

### 2. The design's DST example was wrong in two ways *(D2)*

The design said "2026-03-08 is the US spring-forward" and then used 17:00 UTC as 09:00
**PST** on that date. Both halves were wrong:

- 09:00 Pacific is **17:00 UTC** in PST (UTC−8) — the design's example `NOW` of 16:00
  UTC was an hour off, and so was the test that copied it;
- the transition happens at 02:00 local **on** 2026-03-08, so that morning is already
  **PDT**. The two 9ams are 2026-03-07 at 17:00 UTC and 2026-03-09 at 16:00 UTC.

The review checked the offsets against the zone database rather than trusting the
comment — and added a test for the property that actually matters:

> **the two 9ams are different instants** — `after − before == 2 days − 1 hour`.

That is what a naive implementation gets wrong, and pinning the two instants
separately would not have said it.

### 3. The boundary test had to be rewritten, because the designed one was vacuous *(D7)*

The design said: "the test greps the API modules for the composition service and
asserts it is absent".

**That check would have been vacuous**, for two reasons:

1. The worker legitimately imports the composition, so an import-based rule needs an
   exemption list — and a list of exemptions is a list of holes, one per new API
   module.
2. The enqueue is reachable from a request handler **by design**, and the enqueue
   module's own name contains `digest_composition` as a substring. A text search would
   have flagged the seam for its own function name.

So the check is **AST-based and call-based**: it reports a module that *calls*
`compose_digest`, and it does not report a module that merely imports the enqueue. The
API module list is **discovered** — every `api.py` and `*_api.py` under `apps`, plus
`config/api.py` — so a new API module is covered the moment it exists.

**And the review added the other half**: a test that the worker *must* still compose.
A rule that forbade the composition everywhere would be satisfied by a tree where no
digest was ever composed — and the user's digest would simply never appear. AD-11 moves
the work out of the request path, not out of the system.

### 4. The command's `--all` now asks the scheduler's own rule, and releases its claims *(D6)*

The first implementation had `--all` iterate every preference itself. That would have
been a **second, looser idea of "due"** — the exact drift `local_date_for` was promoted
out to prevent, and the design's own D2 argument against a second rule applied to its
own command.

It now calls `claim_due_digests`, so "everyone who is due right now" means exactly what
the dispatcher means by it, in the user's own local wall clock.

It also **releases the claims it takes**, in a `finally`. A command that claimed a user
and crashed would have left them claimed until the TTL expired — delaying their digest
by a quarter of an hour, for no reason.

### 5. The command's flag is `--user-id`, not `--user` *(D6)*

The design named `--user-id`; the implementation said `--user`. The design was right —
`--user` reads as "the user's name", and the value is a UUID. Aligned to the design.

### 6. The enqueue is registered on the `personal` alias *(D5)*

`transaction.on_commit(..., using=PERSONAL)` rather than the default. The callback
belongs to the transaction that wrote the rows, and the rows live in the `personal`
schema. A test pins the alias.

---

## The seventh change: the concurrency test, and what it found *(D1, D10)*

The acceptance criterion is explicit: "A test exercises the concurrent path rather
than assuming the constraint covers it." So the review added one — two real dispatchers
in two real threads, over a real **committed** row (`transaction=True`, because
without a commit the second thread cannot see the first thread's rows and the test
would pass vacuously).

**Then the review checked the test against a broken implementation**, which is the
part worth recording:

| What was broken | What happened |
|---|---|
| the **row lock** removed | the test **failed** — the user was claimed twice |
| only `SKIP LOCKED` removed | the test **still passed** |
| only the candidate-read's claim filter removed | the test **still passed** |
| only the re-read's claim filter removed | the test **still passed** |

**So the design had it wrong.** It said the guarantee was "`SKIP LOCKED`, so the second
dispatcher skips the row the first one is holding". `SKIP LOCKED` is the **liveness**
half — it stops the second dispatcher *blocking* on the row the first is holding. The
**correctness** half is the row lock itself: the second dispatcher waits, and when it
wakes up it re-reads the row and finds it already claimed.

That distinction matters for whoever changes this code next. A reader who believed
`SKIP LOCKED` was the guarantee would have no reason to keep the `select_for_update`
call — and removing it silently breaks the one-claim rule. The test's assertion message
and the design now both say which line is the guarantee.

---

## What the review checked and left alone

- **The claim lives on `DigestPreference`, not on `PulseDigest`.** The reasoning holds:
  the local date and the delivery time are both on the preference row, and it is one
  row per user, so claiming it claims the user's daily composition.
- **A user with no preference is never due.** The composition service *would* cope — it
  falls back to UTC and no city — but composing for a user who has told us nothing is
  not the dispatcher's job. The default zone would mean composing in UTC for someone we
  know nothing about.
- **The `DIGEST_CLAIM_TTL` is 15 minutes.** A composition reads three candidate pools
  and scores them — minutes, not hours — so the TTL is generous rather than tight. And
  the TTL is *its own* constant, not `INGEST_CLAIM_TTL` or `CALENDAR_CLAIM_TTL` reused
  by name (AD-8): those pace per-source and per-connection work; this paces per-user
  composition, which is a different unit and a different cost.
- **The dispatcher reads a bounded candidate set** (`limit * 4`) before applying the
  Python rule. The rule cannot be expressed in SQL — "has 9am arrived in
  `America/Los_Angeles`?" depends on the row's own IANA zone and compares against a
  per-row time-of-day — so the rule lives in one testable function and the read is
  bounded.
- **The candidate read is *not* ordered by due-ness.** It is ordered by the user id,
  which is the creation time. A user who has just finished onboarding is therefore
  never starved behind a backlog of established users.
- **The audit row carries the claim time and the user id, and nothing else** — no
  email, no city, no delivery time (AD-13).
- **The composition is idempotent, so the enqueue is a fast path rather than the only
  path.** The scheduler is the backstop: it finds users whose delivery time has
  arrived and who have no digest for the local date, so a lost enqueue costs a minute,
  not a digest.
- **`robust=True` is the right choice for the enqueue.** The user has finished
  onboarding either way; what they have not got is a digest, and the backstop will
  produce one.

---

## The neighbours this item touches

- **`digest-composition-service`** — the composition this item schedules. The
  idempotence guard (`created=False`, the unique constraint) is what makes both the
  dispatcher and the command safe to re-run.
- **`digest-user-preferences`** — the `DigestPreference` row this item claims on, and
  the delivery-time wall clock this item reads.
- **`digest-read-api`** — the read side of the same local-date rule. Both sides call
  `local_date_for`, so "today" cannot mean two different days.
- **`worker/tasks.py`'s tick** — the existing tick-order test was **extended**, not
  replaced. The digest dispatcher appears in every row of the pinned table, because
  its cadence does not nest.

---

## The contradictions the review found and resolved

1. **The design's DST example contradicted the zone database.** Resolved: the design
   was wrong, and the test now pins the two real 9ams.
2. **The design's D7 asked for a check that would not have worked.** Resolved: the
   design now describes the call-based check and says why the import-based one was
   wrong.
3. **The design's D6 named a flag the implementation did not use.** Resolved: aligned
   to the design.
4. **The design's D2 did not say whether the converted time carries an offset.** That
   omission is what produced the bug. Resolved: the design now says the comparison is
   between two *naive* wall clocks, and says why.
