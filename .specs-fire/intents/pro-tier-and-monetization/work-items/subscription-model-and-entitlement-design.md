---
work_item: subscription-model-and-entitlement
intent: pro-tier-and-monetization
created: 2026-11-11
mode: validate
checkpoint_1: approved
---

# Design: Something to be Pro with — the Subscription entity and the one entitlement read

## Summary

`Subscription` is the row that makes "Pro" a fact rather than an aspiration. It lives in
`apps/identity`, which already declares ownership of it, and in the `PERSONAL` alias. It
carries the plan, a status, the current period end, the Stripe references, and the timestamp
of the last external event applied to it.

Entitlement is published as **one function in one module** — `is_pro(user_id) -> bool` in
`apps/identity/services/entitlement.py` — modelled directly on the existing
`services/recipients.py`, which solves the identical problem for a user's email address.
It returns a primitive, never a model; a user with no row is Free, not an error.

Three idempotent, order-tolerant commands move the row, each writing an `IdentityAuditEntry`.
The ordering guard lives here, on the model, so that `billing-adapter-and-webhooks` inherits
it rather than inventing one.

**A correction to the work item and the intent brief.** Both say the entitlement read
"crosses the schema wall by value (AD-3)". **It does not.** `settings.DATABASE_ROUTING`
(`config/settings.py:75`) places `identity`, `personalization` and `delivery` all in
`PERSONAL`, and `shared/db.py` explains why: *"`default` is the personal schema because
Django requires a `default` alias and the user table must share an alias with the personal
data that references it."* AD-3's wall runs between `catalog` and `personal`, and this read
never approaches it. The contract that actually governs here is **AD-2's `models-identity`**:
*"only `apps.identity` imports `apps.identity.models` (others call its services)."* The
conclusion is unchanged — callers get a function, not a model — but for a different and
stricter reason, and the ACs should be read accordingly.

## Scope

**In Scope:**
- The `Subscription` model, its constraints and its retention category
- The status set, and the single mapping from status to entitlement
- `is_pro(user_id)` as the one published read
- Three named commands with audit entries, idempotent and order-tolerant
- The ordering guard column the webhook receiver will rely on

**Out of Scope:**
- The Stripe adapter and the webhook receiver (`billing-adapter-and-webhooks`)
- Checkout and portal endpoints (`checkout-and-portal-api`)
- Any cap, gate or Pro feature reading entitlement (items 4 onward)
- Trials, proration, refunds, coupons, and multiple concurrent plans
- A reconciliation job against Stripe as a safety net for missed webhooks

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Read path | **Direct service read, no cache** | `identity` shares the `PERSONAL` alias with its callers, so this is one indexed lookup in the same database — not a cross-schema or cross-service hop. `recipients.py` already does exactly this on the delivery path with no cache and no complaint. A cache here would add an invalidation contract for item 2 to honour, in exchange for savings nobody has measured. |
| Caching seam | **Documented, not built** | `is_pro` is one function with one caller signature, so a cache can be added behind it later without touching a single call site. Building it now would be speculative. |
| Governing contract | **AD-2 `models-identity`**, not AD-3 | See the correction above. Callers import `apps.identity.services.entitlement`, never `apps.identity.models`. The import-linter contract fails the build if they do. |
| Status set | `active`, `past_due`, `canceled`, `expired` | Four states, each mapping to exactly one entitlement answer. `past_due` is distinct because `frontend-account-and-billing-settings` must show a failed payment honestly rather than rendering the user as plain "Free". |
| Grace on payment failure | **Pro during `past_due`; Stripe owns the timing** | Entitlement persists through dunning and drops when Stripe moves the subscription to `canceled`. We do not implement a grace timer: a second clock racing Stripe's is a bug generator, and cutting a paying customer off mid-dunning is exactly the un-calm behaviour this product avoids. |
| `is_active` / deactivated users | **Not consulted** | `recipients.py` filters on `is_active` because mailing a closed account is wrong. Entitlement is only ever asked about a user making a request, and a deactivated user has no session to make one with. Consulting it here would imply a gate that authentication already closed. Documented in the module docstring so the asymmetry with `recipients.py` is deliberate and visible. |
| Ordering guard | **`last_event_at` on the model**, commands refuse older | The guard belongs with the state machine, not in the webhook handler, so every writer inherits it — including an admin action or a future reconciliation job. Mirrors `SavedEvent.event_version`, whose docstring gives the same reasoning for AD-17 propagation. |
| One subscription per user | **Partial unique constraint** on non-terminal statuses | Enforced by the database, not by application code. A user may hold a history of `canceled` rows but only ever one live one. |
| Plan enum | **Reuse `ports.billing.ProPlan`** | It already exists with `MONTHLY` and `YEARLY`. A second spelling in `apps/identity` would be free to drift from the one the adapter uses. |
| Deletion | **None** | A lapse is a transition to `canceled`. Consistent with soft reject, paused-not-deleted sources, and the `BILLING_RECORDS` 7-year retention, which would be meaningless against deletable rows. |

## Data Models Affected

### Creates

- **`Subscription`** (`apps/identity`, alias `PERSONAL`, `retention_category = BILLING_RECORDS`)
  - `user_id` — the account. One live subscription per user, by partial unique constraint.
  - `plan` — `ProPlan.MONTHLY` / `ProPlan.YEARLY`, from `ports.billing`.
  - `status` — `active` | `past_due` | `canceled` | `expired`.
  - `current_period_end` — for display and for the renewal date in settings.
  - `stripe_customer_ref` — needed by `create_portal_session(customer_ref=...)` **without a
    Stripe round-trip**, which is why it is stored rather than looked up.
  - `stripe_subscription_ref` — the external subscription, for correlation and support.
  - `last_event_at` — the external event timestamp last applied. The ordering guard.
  - `created_at`, `updated_at`.

### Modifies

- **None.** `User` is untouched. No flag is denormalized onto it — that would be a second
  source of truth for entitlement and the thing a cache decision would force later.

## Technical Approach

### Architecture

```
  billing-adapter-and-webhooks (item 2)
            │  record_subscription_{started,changed,ended}
            ▼
  apps/identity/services/subscriptions.py   ── writes ──▶  Subscription  (PERSONAL)
            │                                                    │
            │  IdentityAuditEntry (AD-5)                          │
            ▼                                                     │
  apps/identity/models.py (protected: models-identity)            │
                                                                  │
  apps/identity/services/entitlement.py  ──── reads ──────────────┘
            ▲         is_pro(user_id) -> bool
            │
     ┌──────┴───────────────────────────────┬──────────────────┐
  personalization                        delivery           config.api
  (save gate, collections)          (quiet hours)        (checkout, settings)
```

Callers import the service module. The `models-identity` contract makes the alternative a
build failure rather than a code-review note.

### Database Changes

```sql
-- in the PERSONAL alias, alongside identity's existing tables
CREATE TABLE identity_subscription (
    id                      uuid PRIMARY KEY,          -- UUIDv7Model
    user_id                 uuid NOT NULL,
    plan                    text NOT NULL,             -- ProPlan
    status                  text NOT NULL,             -- active|past_due|canceled|expired
    current_period_end      timestamptz NULL,
    stripe_customer_ref     text NOT NULL,
    stripe_subscription_ref text NULL,
    last_event_at           timestamptz NULL,
    created_at              timestamptz NOT NULL,
    updated_at              timestamptz NOT NULL
);

-- at most one live subscription per user; history of canceled rows is allowed
CREATE UNIQUE INDEX subscription_one_live_per_user_uq
    ON identity_subscription (user_id)
    WHERE status IN ('active', 'past_due');

CREATE INDEX subscription_user_idx ON identity_subscription (user_id);
```

The partial unique index is the pattern already used elsewhere in this codebase for
"at most one open row per key"; follow the existing constraint-naming convention.

## Dependencies

- None. This is the first item of the intent.

## Affected Files

| File | Action | Purpose |
|---|---|---|
| `backend/apps/identity/models.py` | modify | Add `Subscription` |
| `backend/apps/identity/migrations/` | create | The table, the partial unique index |
| `backend/apps/identity/services/entitlement.py` | create | `is_pro(user_id)` — the one published read |
| `backend/apps/identity/services/subscriptions.py` | create | The three commands, audit, ordering guard |
| `backend/shared/constants.py` | modify | Any threshold this item introduces |
| `backend/tests/apps/identity/` | create | Model, constraint, command and entitlement tests |
| `backend/tests/architecture/test_import_contracts.py` | modify | Plant a `personalization → identity.models` import and prove `models-identity` catches it |

## Security Considerations

- **No Stripe credential appears here.** This item stores external *references* only. Keys
  arrive with the adapter in item 2, via pydantic-settings, per the constitution's
  *"config is validated once at startup"* and *"no credentials, API keys, or tokens in
  source control."*
- **Entitlement is server-side only.** `is_pro` is never trusted from a client claim, and no
  endpoint accepts a tier as input.
- **The references are not secrets but are identifying.** `stripe_customer_ref` must not
  reach a log sink. Confirm against the allowlist in `adapters/logging/redaction.py`, which
  AD-13 makes the single sink — the same reasoning `recipients.py` applies to the address.
- **A caller cannot write through the read.** `is_pro` returns a `bool`. A caller handed a
  `Subscription` could save it, and `identity` is the only writer of that table.

## Integration Points

| System | Type | Purpose |
|---|---|---|
| `billing-adapter-and-webhooks` (item 2) | inbound | The only routine writer: Stripe events become the three commands |
| `free-tier-caps-read-entitlement` (item 4) | outbound | First hot-path reader — the save gate |
| `saved-collections-api`, `quiet-hours-pro-api`, `data-export` | outbound | Feature gates |
| `checkout-and-portal-api` (item 3) | both | Reads to refuse a second checkout; reads `stripe_customer_ref` for the portal |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| The direct read proves too slow on the save path | Latency on every save | `is_pro` is one function with one signature, so a cache goes behind it without touching callers. Item 4's ACs require measuring rather than assuming. |
| A second entitlement check grows elsewhere | Two answers that drift | One published function; a test greps for `status ==` comparisons outside `entitlement.py` and fails on a second mapping. |
| An out-of-order webhook restores a cancelled subscription | A cancelled user stays Pro | `last_event_at` guard in the commands, tested here with an explicitly stale event — not left for item 2. |
| `past_due` treated as Free by a caller that maps status itself | A paying customer cut off mid-dunning | Callers never see `status`. They see `is_pro`. |
| Two webhooks race and create two live rows | Double entitlement, ambiguous state | Partial unique index refuses it at the database, tested under concurrency. |
| The AD-3 correction is missed and someone adds a by-value id crossing | Needless indirection, or a real wall crossing later | Stated at the top of this doc and in the module docstring, with the `DATABASE_ROUTING` citation. |

## Implementation Checklist

- [ ] `Subscription` in `apps/identity/models.py` with `retention_category = BILLING_RECORDS`
- [ ] Migration: table, partial unique index on `(user_id) WHERE status IN ('active','past_due')`, user index
- [ ] `ProPlan` reused from `ports.billing`; no second plan enum
- [ ] `services/entitlement.py`: `is_pro(user_id) -> bool`, total, returns a primitive, docstring explaining the `is_active` asymmetry with `recipients.py` and the `DATABASE_ROUTING` correction
- [ ] `services/subscriptions.py`: `record_subscription_started` / `_changed` / `_ended`, each idempotent, each writing `IdentityAuditEntry`
- [ ] Every command refuses an event older than `last_event_at`, and records the refusal as a no-op rather than an error
- [ ] No delete path anywhere; a test asserts none exists
- [ ] Tests: absent row reads Free; each status maps to the right answer; `past_due` is Pro; stale event refused; replayed command applies once; concurrent writes yield one live row; audit entry per transition
- [ ] Import-contract test plants `from apps.identity.models import Subscription` in `personalization` and proves `models-identity` fails
- [ ] `make lint check test` green; no existing test modified except the adapter-mode assertion left for item 2

---
*FIRE Flow — Checkpoint 1 pending approval*
