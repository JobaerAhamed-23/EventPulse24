---
run: run-eventpulse24-027
work_item: subscription-model-and-entitlement
intent: pro-tier-and-monetization
mode: validate
checkpoint: plan (checkpoint 2)
approved_at: 2026-11-11
---

# Implementation Plan: Something to be Pro with — the Subscription entity and the one entitlement read

## Approach

Four pieces, in dependency order, each landing green before the next starts.

1. **`Subscription` on the model layer**, in `apps/identity/models.py`, alias `PERSONAL`,
   `retention_category = BILLING_RECORDS`. One migration carries the table, the partial
   unique index and the user index.

2. **`services/entitlement.py`** — the one published read. Written as a near-sibling of the
   existing `services/recipients.py`: a module whose docstring argues for its own shape, a
   single function returning a primitive, and `__all__` naming just that function.

3. **`services/subscriptions.py`** — three commands, each inside
   `transaction.atomic(using=PERSONAL)`, each calling `audit_service.write_audit`, each
   refusing an event older than `last_event_at`.

4. **Tests**, including an import-contract test that plants the forbidden import and proves
   `models-identity` catches it.

The actor on every webhook-driven transition is a **system actor** — `Actor(kind=SYSTEM,
label="stripe_webhook")` — because `shared/actor.py` requires a system actor to carry a
lowercase label and no id, and the mutation has no human behind it. An admin-initiated
transition would carry a user actor, which is why the commands take `Actor` rather than
assuming one.

## Files to Create

| File | Purpose |
|---|---|
| `backend/apps/identity/services/entitlement.py` | `is_pro(user_id) -> bool` — the single published read |
| `backend/apps/identity/services/subscriptions.py` | `record_subscription_started` / `_changed` / `_ended`, the ordering guard, audit |
| `backend/apps/identity/migrations/000X_subscription.py` | Table, partial unique index, user index |
| `backend/tests/apps/identity/test_subscription_model.py` | Constraints, retention category, no-delete |
| `backend/tests/apps/identity/test_subscription_commands.py` | Idempotency, ordering guard, audit rows |
| `backend/tests/apps/identity/test_entitlement.py` | The status→entitlement mapping, absent row, `past_due` |

## Files to Modify

| File | Change |
|---|---|
| `backend/apps/identity/models.py` | Add `Subscription` and its `SubscriptionStatus` enum |
| `backend/tests/architecture/test_import_contracts.py` | Plant `personalization → apps.identity.models`, assert `models-identity` fails |

`backend/shared/constants.py` is listed in the work item but is **expected to go untouched**:
this item introduces no threshold or duration. Grace timing belongs to Stripe (design
decision), so there is no window constant to name. If that turns out to be wrong during
implementation it will be recorded as a deviation rather than slipped in.

## The interface

```python
# apps/identity/services/entitlement.py
def is_pro(*, user_id: UUID) -> bool: ...

# apps/identity/services/subscriptions.py
def record_subscription_started(
    *, actor: Actor, user_id: UUID, plan: ProPlan,
    customer_ref: str, subscription_ref: str | None,
    current_period_end: datetime | None, event_at: datetime,
) -> Subscription | None: ...

def record_subscription_changed(
    *, actor: Actor, subscription_ref: str, status: SubscriptionStatus,
    plan: ProPlan | None = None, current_period_end: datetime | None = None,
    event_at: datetime,
) -> Subscription | None: ...

def record_subscription_ended(
    *, actor: Actor, subscription_ref: str, event_at: datetime,
) -> Subscription | None: ...
```

Every command is keyword-only, takes an explicit `Actor` and never a `request` — matching the
spine's *"Auth resolved at the API edge"* and the convention `sign_up` already follows.

**`None` is the return for a refused stale event**, not an exception. An out-of-order webhook
is an expected, routine occurrence, not an error condition — item 2's receiver must return
success to Stripe so it stops retrying, and raising here would push that decision into
exception handling.

## Tests

Every test below can fail; none asserts a tautology.

**Model**
- The partial unique index refuses a second `active` row for one user
- It *permits* a second row when the first is `canceled` — history is allowed
- `past_due` also occupies the live slot (it is in the index predicate)
- `retention_category` is `BILLING_RECORDS`, and the `eventpulse.E003/E004` checks pass
- No delete path: a grep-style test asserts no `.delete()` on `Subscription` in `apps/`

**Entitlement**
- Absent row → `False` (total, not an exception)
- `active` → `True`; `past_due` → **`True`**; `canceled` → `False`; `expired` → `False`
- A user with a `canceled` row *and* an `active` row reads `True` (the live row wins)
- `is_pro` returns a `bool`, never a model — asserted by type, so a refactor that leaks a
  `Subscription` fails

**Commands**
- Each writes exactly one `IdentityAuditEntry` with the right `action` and `target_id`
- A replayed command (same `event_at`) applies once; the second returns `None` and writes
  no second audit row
- A **stale** `event_at`, older than the stored one, is refused and leaves the row unchanged
  — including the case that matters most: a stale `_changed(active)` arriving *after*
  `_ended`, which must not restore entitlement
- Concurrent `record_subscription_started` for one user yields one live row, the loser
  catching `IntegrityError` as `sign_up` does
- `write_audit` outside a transaction raises `AuditOutsidePersonalTransaction` — i.e. the
  commands really do open `transaction.atomic(using=PERSONAL)`

**Architecture**
- Planting `from apps.identity.models import Subscription` in `apps/personalization` makes
  the `models-identity` contract fail, and only that contract

## Technical Details

- **`SubscriptionStatus`** is a `StrEnum` on the model module, four members. The
  status→entitlement mapping lives **only** in `entitlement.py`; no caller compares status.
- **The partial unique index** uses `condition=Q(status__in=[ACTIVE, PAST_DUE])` on a
  `UniqueConstraint`, named `subscription_one_live_per_user_uq`, following the existing
  naming convention (`saved_event_user_event_uq`, `notification_preference_quiet_hours_pair_ck`).
- **The ordering guard** compares `event_at` against the stored `last_event_at` with
  `>`, so an equal timestamp is treated as a replay and refused. Stripe can deliver two
  events in one second; the design flagged this, and the `_changed` command therefore also
  compares the incoming status against the stored one so an equal-timestamp *different*
  status is not silently dropped. **This is the one place the plan goes beyond the design
  doc** — see Deviations.
- **No email in any audit row** (AD-13): `details` carries the plan value, the status and the
  subscription reference. The `stripe_customer_ref` is deliberately excluded from `details`,
  since audit rows are long-lived under `AUDIT_LOG` retention.
- **`stripe_customer_ref` must not reach a log sink.** Check it against the allowlist in
  `adapters/logging/redaction.py` during implementation and extend the redaction test if the
  allowlist's shape permits the value through.

## Deviations from the Design

1. **Equal-timestamp handling is specified more tightly than the design doc.** The design
   says commands "refuse an event older than `last_event_at`". Strictly applied, two Stripe
   events in the same second would see the second refused, which could drop a real status
   change. The plan therefore refuses an equal timestamp **only when the status is
   unchanged**, and applies it otherwise. The design's risk table anticipated this
   ("Stripe can deliver two events in the same second"), but its checklist did not. If you
   prefer the stricter literal reading, say so and the test for it changes accordingly.

2. **`shared/constants.py` is expected to be untouched**, where the work item's affected-files
   list named it. Stated above, with the reason.

## Based on Design Doc

`.specs-fire/intents/pro-tier-and-monetization/work-items/subscription-model-and-entitlement-design.md`
(checkpoint 1 approved 2026-11-11), including its correction that this is an **AD-2
`models-identity`** concern, not an AD-3 wall crossing.
