---
id: subscription-model-and-entitlement
title: Something to be Pro with — the Subscription entity and the one entitlement read
intent: pro-tier-and-monetization
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-11-11
run_id: run-eventpulse24-027
completed_at: 2026-11-11T07:45:29.301Z
---

# Work Item: Something to be Pro with — the Subscription entity and the one entitlement read

## Description

`apps/identity/__init__.py` reads *"Accounts and billing state. Owns User and Subscription."*
`identity/models.py` defines `User`, `PasswordResetToken` and `IdentityAuditEntry`. The
`Subscription` has never been written, so no user can be anything but Free, and
`shared/constants.py:469` has been carrying the consequence in a comment: *"Every user is
Free in this intent (there is no SUBSCRIPTION entity yet)."*

This item builds the entity, the named commands that move it between states, and the single
entitlement read that every other item in this intent calls. Nothing else here can start
until it lands.

Its hard part is not the table. It is the **read path**: the save gate (item
`free-tier-caps-read-entitlement`) runs on every save, `personalization` and `delivery` may
not hold a foreign key into `identity` (AD-3), and a cached answer needs an invalidation
story that the Stripe webhook drives. That is why this item is `validate`.

## Acceptance Criteria

- [ ] `Subscription` lives in `apps/identity/models.py`, owned by `identity`, and is written
      only through `identity` commands.
- [ ] It declares `retention_category = RetentionCategory.BILLING_RECORDS` — already defined
      at `shared/retention.py:33` as *"Billing records (Pro subscribers): 7 years
      (tax/legal)"* and currently used by **no model**. System checks `eventpulse.E003/E004`
      enforce this.
- [ ] It carries the plan (`ProPlan.MONTHLY` / `ProPlan.YEARLY`, reusing the enum already in
      `ports/billing.py` rather than a second spelling), a status, the current period end,
      and the external customer and subscription references.
- [ ] **The status set is decided by the design doc and justified**, including whether
      `past_due` is distinct from `cancelled`. Whatever is chosen, every value maps to
      exactly one entitlement answer, and that mapping lives in one place.
- [ ] **At most one non-terminal subscription per user**, enforced by a partial unique
      constraint — not by application code alone.
- [ ] **Never delete.** A lapse or cancellation is a state transition. There is no delete
      path, matching the soft-reject and paused-not-deleted precedents elsewhere.
- [ ] Every transition is a **named command** with an `IdentityAuditEntry` (AD-5). No caller
      reaches `obj.save()`.
- [ ] **One entitlement read** answers "is this user Pro?" for every caller in the codebase.
      It crosses the schema wall **by value** (AD-3): `personalization` and `delivery` pass
      a user id and receive an answer, never a relation.
- [ ] The read is **total**: a user with no `Subscription` row is Free, not an error.
- [ ] Tests cover: the partial unique constraint refusing a second active subscription; each
      status mapping to the right entitlement answer; the absent-row case; audit entries
      written on every transition; and that no code path deletes a subscription.

## Technical Notes

High complexity, so this item gets a design doc. The design must decide:

- **The entitlement read path.** A direct `identity` service call per check is simplest and
  always correct, but it is on the hot save path. A denormalized or cached answer is faster
  but needs invalidation, and the only thing that can invalidate it correctly is the webhook
  from `billing-adapter-and-webhooks` — which is built *after* this item. The design must
  therefore either pick the direct read now and leave a documented seam for caching, or
  specify the cache and its invalidation contract up front so item 2 can honour it. Do not
  leave this to be discovered during item 4.
- **The status set**, and specifically whether `past_due` exists. This is the same question
  as "grace on `invoice.payment_failed`" from the brief, and answering it here rather than
  in item 2 keeps the state machine in one place.
- **Where the external references live.** The Stripe customer id is needed by
  `create_portal_session(customer_ref=...)`, so it must be readable without a Stripe call.

Follow `apps/identity/services/` for command and audit conventions, and the `ActorColumns`
mixin for attribution where a transition has a human actor (an admin comp, say) rather than
a webhook.

Resolve the comment at `shared/constants.py:469` only in item
`free-tier-caps-read-entitlement`, where the cap actually changes — not here.

## Dependencies

(none)
