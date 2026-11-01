---
id: send-minting-and-rescheduling
title: Minting, rewriting and cancelling sends — design
intent: delivery-and-reminders
mode: validate
created: 2026-10-31
checkpoint_1: approved
checkpoint_1_at: 2026-10-31T13:50:00Z
---

# Design: the single writer of `SCHEDULED_SEND`

One service in `apps/delivery/services/`, the **only** writer of the table item 3 built. It
turns Reminder Plans and preferences into pending rows, and keeps those rows true as the world
changes.

## The shape of the problem

Three kinds of change reach this service. They all read as "recompute the time", and they must
behave differently. Conflating any two of them either **duplicates a user's reminders** or
**silently drops them** — and both failures look like nothing at all until a user complains.

| | Trigger | Key | Rows |
|---|---|---|---|
| **1. Preference change** | quiet hours, timezone, delivery time, plan edit | **unchanged** | `due_at` rewritten in place on `pending` rows |
| **2. Lifecycle change** (AD-17) | the source moved / cancelled / superseded the event | **new** (version bumps) | old `pending` cancelled, new minted |
| **3. Disappearance** | un-saved, personal event deleted, unsubscribed, account closed | — | `pending` cancelled, nothing minted |

The distinction between 1 and 2 is exactly why AD-7 insists the key is not derived from
`due_at`, and item 3 made that structurally true. This item is where the distinction is spent.

---

## Decisions

### D1 — Three entry points, named so they cannot be confused, with no shared boolean

```python
reschedule_pending_for_user(user_id, *, actor, now)        # 1 — never mints, never cancels
apply_lifecycle_change(state_change_id, user_id, *, ...)   # 2 — cancels and re-mints
cancel_sends_for_targets(user_id, targets, *, actor, now)  # 3 — only cancels
mint_for_plan(user_id, target, slots, *, actor, now)       # the plan-edit half of 1
```

**No `recompute(..., remint: bool)`.** A boolean parameter is how these three collapse into
one function that behaves differently depending on a flag a caller has to get right, and the
caller who gets it wrong gets duplicate sends with no error. Four names, four behaviours, each
testable in isolation.

`reschedule_pending_for_user` **cannot mint** — it has no code path that creates a row, so the
"preference change duplicated my reminders" bug is not a discipline, it is unreachable.

### D2 — The version guard makes a re-run a no-op, and it must be written carefully

AD-17: propagation is *"per-user, versioned, idempotent ... applied in one `personal`
transaction, keyed `(state_change_id, user_id)`, and **only if** the change's `event_version`
is greater than the version already stored on that user's `SAVED_EVENT`."*

The hazard, which is easy to write and hard to see: a careless "cancel the pending rows and
mint new ones" re-run **cancels the rows it just minted**. The second run would cancel the v5
rows, then try to mint v5 rows again, hit the unique constraint on the spent keys, and leave
the user with nothing pending. A reminder silently deleted by a retry.

The guard that prevents it:

- Cancel only rows whose **working `event_version` is less than** the change's version.
- Mint only if no row already carries the change's version (the unique key makes this cheap).
- Both inside the `(state_change_id, user_id)` transaction.

So a second run finds nothing below the version and nothing to mint, and does nothing. An
**older** change arriving after a newer one is also a no-op, which is AD-17's out-of-order
requirement. Three tests: run twice, run out of order, run partially then retry.

### D3 — What each lifecycle kind does

`EventStateChange.Kind` has seven members. AD-17 names the behaviour; mapping all seven
explicitly means a new kind cannot silently fall into a default.

| Kind | Sends |
|---|---|
| `TIME_MOVED`, `POSTPONED` | cancel pending, bump version, **re-mint** |
| `CANCELLED`, `SUPERSEDED` | **cancel** pending, mint nothing |
| `SOLD_OUT`, `DETAIL_CHANGED` | **keep** sends, re-stamp the working version only |
| `REINSTATED` | re-mint from the plan (the event is live again) |

The map is a module-level dict, and a test asserts **every** `Kind` member is a key — so adding
a kind to `ingestion` fails this test rather than quietly doing nothing.

`SOLD_OUT` is the one worth a second look: AD-17 says "keep sends, queue a notice". A sold-out
event still happens, and a user who saved it still wants their reminder. Cancelling would be a
plausible, wrong reading, so it gets its own test.

### D4 — The zone is read once per batch, which is the whole point of D5-in-item-2

The Quiet Hours shift needs the user's IANA zone, which lives on `personalization`'s
`DigestPreference`. Reading it **per row** would undo the reasoning that put the quiet-hours
window in `delivery` in the first place.

One read per command, through `personalization`'s published service — never
`apps.personalization.models` (AD-3, the `models-personalization` contract). For
`reschedule_pending_for_user` that is one read for all of a user's rows.

A test asserts the query count is **independent of the number of pending rows**, the way
`conflict-list-api` pins its own bound.

### D5 — A past due time is not minted

A 5-day slot on an event three days away produces **no row**, rather than a row with a due time
in the past that the next sweep fires immediately. The user would get a "5 days until…" email
about an event in three days.

The boundary is `due_at <= now` at minting time. A test covers the 5d slot on a 3-day-out event
and asserts three slots exist, not four.

**Deliberately not symmetrical:** an *existing* pending row whose rewritten `due_at` lands in
the past is **still sent**, not dropped. It means the user changed their quiet hours such that
a reminder that was waiting is now overdue — and the honest thing is to send it late rather
than silently bin a reminder they asked for.

### D6 — Status transitions are enforced here, closing item 3's stated gap

Item 3 built the states and tested their shape; it deliberately left enforcement untested
because nothing implemented it yet. This service is that implementation.

One private guard every status write passes through, rejecting any transition out of a terminal
state. A `sent` row is never re-timed, rekeyed, cancelled or resurrected. Tests cover each legal
transition and each illegal one — the item-3 test report's "Known gap" closes here.

### D7 — Every write is audited, and never carries an address

`write_audit` in the same `PERSONAL` transaction (AD-5), recording the send key, the user id and
the kind of change. **Never a recipient address** (AD-13) — the table does not store one, and
the audit row must not reintroduce it.

### D8 — Wiring `propagate_state_change` ✅ **decided 2026-10-31**

**What I found while designing this.** `worker/tasks.py:137` is still a placeholder:

> *"AD-17 placeholder consumer: no propagation into `personal` exists yet (FR-53-55). It
> deliberately leaves `propagated_at` NULL: marking the row would claim a propagation that
> never happened, and the real consumer would then skip it."*

AD-17 says propagation calls **each owner's** published service — `delivery` rewrites sends,
**and `personalization` updates the `SAVED_EVENT` snapshot and re-evaluates `CONFLICT_PAIR`s** —
and sets `propagated_at` *"once every affected user is done"*.

This work item's acceptance criteria say to wire the `delivery` half. But **the
`personalization` half does not exist**, and that is FR-53/54 — which the intent brief
explicitly puts in the *next* intent. That leaves a fork I should not pick silently:

| | What happens | Cost |
|---|---|---|
| **A — build the service, don't wire the task** (recommended) | The delivery half exists, is tested directly, and is wired when FR-53/54 builds the other half. The placeholder and its comment stay. | The acceptance criterion "wired to `propagate_state_change`" moves to the next intent. Honest, and nothing is half-done. |
| **B — wire the delivery half, still don't mark propagated** | Sends are cancelled and re-minted correctly on a real state change. | `reconcile_outbox` re-offers every unpropagated change forever (every 5 minutes, oldest first). Today that costs nothing because the consumer is a no-op; wired, **every re-offer does real database work, forever**. Safe only because D2's guard makes it a no-op — which is a lot of weight on one guard. |
| **C — wire both halves and mark propagated** | AD-17 completed. | Pulls FR-53/54's `personalization` work — snapshot update and conflict re-evaluation — into this item, roughly doubling it and taking scope the brief assigned elsewhere. |

**Decided with the user: option A.** Marking `propagated_at` after only half a propagation
would make the `personalization` consumer permanently skip those changes — a silent data bug,
and exactly what the existing placeholder comment warns about. The only *safe* wirings are
"both halves" or "neither", and "both" is the next intent's job.

**Consequences, recorded so nothing is lost:**

1. `apply_lifecycle_change` is built, published and fully tested **against its own callers in
   tests**, not against the worker. It is ready for the FR-53/54 intent to call.
2. `worker/tasks.py`'s placeholder is **unchanged**, including its comment — which is already
   correct and now also explains why the delivery half it could call is not called yet. One
   line is added naming `apps.delivery.services.scheduled_sends.apply_lifecycle_change` as the
   half that already exists, so the next implementer does not go looking.
3. The work item's acceptance criterion "`propagate_state_change` ... is wired to this service"
   is **moved to the FR-53/54 intent** and struck from this item, with this decision cited. An
   acceptance criterion quietly left unmet is worse than one explicitly moved.

---

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/apps/delivery/services/scheduled_sends.py` | create | The four commands; the sole writer |
| `backend/tests/delivery/test_scheduled_sends.py` | create | All three change kinds, the guard, the bounds |
| `backend/shared/constants.py` | modify | The lifecycle→behaviour map, if shared |
| `backend/worker/tasks.py` | **depends on D8** | Wire `propagate_state_change` (option B/C only) |
| `backend/apps/delivery/services/reminder_plans.py` | modify | `set_plan_slots` / `remove_all_reminders` mint and cancel in the same transaction |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| A re-run cancels the rows it just minted | **A reminder silently deleted by a retry** | D2's version guard; three idempotency tests including a partial-then-retry |
| Preference path grows a mint | Duplicate reminders on every settings change | D1 — `reschedule_pending_for_user` has no create path at all |
| `SOLD_OUT` read as "cancel the reminders" | A user misses an event they saved | D3's explicit map + its own test |
| Zone read per row | Query count grows with a user's reminders | D4 + a query-count test |
| A terminal row is resurrected | Double send | D6's guard + transition tests |
| Wiring half of AD-17 | Outbox churn, or a silently skipped propagation | D8 — raised rather than chosen |

## Implementation Checklist

- [ ] `scheduled_sends.py` with the four commands of D1
- [ ] The lifecycle map of D3, with a test asserting it covers every `Kind`
- [ ] D2's version guard; idempotent, out-of-order safe, partial-retry safe
- [ ] D5's past-due rule, and its deliberate asymmetry
- [ ] D6's transition guard — closes item 3's stated gap
- [ ] Plan edits mint/rewrite/cancel in the **same transaction** as the plan write
- [ ] Audit rows, no addresses (D7)
- [ ] Query-count test, independent of row count (D4)
- [ ] D8's decision applied
- [ ] `manage.py check`, `makemigrations --check`, `lint-imports`, full suite

---
*Checkpoint 1 — awaiting approval.*
