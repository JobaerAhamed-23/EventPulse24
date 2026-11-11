---
id: e2e-proof-and-contract-tests
title: Prove the paid path closes — and that cancelling closes every gate
intent: pro-tier-and-monetization
complexity: medium
mode: confirm
status: pending
depends_on: [frontend-pricing-page, frontend-upgrade-prompts, frontend-collections, frontend-pro-quiet-hours, frontend-account-and-billing-settings]
created: 2026-11-11
---

# Work Item: Prove the paid path closes — and that cancelling closes every gate

## Description

Every other item in this intent proves its own piece. This one proves the loop: that a Free
user can hit a wall, pay, and find all four Pro capabilities actually unlocked — and, the
half that is easier to get wrong, that **cancelling closes every gate again**.

It follows the pattern of `trust-loop`'s own proof, which walked report → queue → reject →
digest → score → ranking in one test rather than trusting six green unit suites to compose.

## Acceptance Criteria

- [ ] **The paid path, end to end**: a Free user saves one event, is refused on the second
      with the inline prompt, reaches `/pricing`, starts checkout, the webhook lands,
      entitlement flips, and the second save succeeds.
- [ ] **All four Pro capabilities are then exercised in the same test**: a second and third
      calendar provider connect (FR-50), a collection is created and an event assigned
      (FR-49), a weekday-specific quiet-hours window defers a send to the right instant
      (FR-51), and an export is requested (FR-52).
- [ ] **Cancellation closes every gate**: after `customer.subscription.deleted`, the save cap
      refuses again, a fourth provider is refused, new collections are refused — and
      **nothing the user created is deleted**. Existing collections, connections, saves and
      seven stored windows all survive, per the intent's never-delete constraint.
- [ ] **Entitlement is never granted without a webhook.** A test returns from a successful
      checkout with no webhook delivered and proves the user is still Free.
- [ ] **A replayed and an out-of-order webhook** are exercised at the e2e level, not only in
      item 2's unit tests: a replayed `checkout.session.completed` grants nothing twice, and a
      stale `customer.subscription.updated` arriving after a cancellation does not restore
      entitlement.
- [ ] Contract tests cover every endpoint added by this intent, and `frontend/lib/api/schema.ts`
      is regenerated and committed in a state matching the backend.
- [ ] The whole suite runs with **no Stripe account, no network and no secrets**, via
      `scripted_network.py` and `FakeBillingAdapter`, so CI runs it unchanged.
- [ ] **Every test can fail.** No placeholder assertions, no `or`-fallbacks. Any behaviour
      found to be broken during this item is pinned by a test that asserts the defect and
      will fail when it is fixed, with a note carried into the walkthrough — as
      `TestTheStrandedEventGetsOut` did in `trust-loop`.

## Technical Notes

Medium complexity, but it is the item most likely to surface real defects, because it is the
first time the entitlement read, the webhook, four gates and five surfaces run together.

Expect the downgrade path to be where problems appear. Every item in this intent was written
with "never delete" as a constraint, but each proved it in isolation; this is the first test
that downgrades a user who has accumulated data under all four capabilities at once.

Follow `backend/tests/e2e/test_trust_loop_proof.py` for structure and naming. Do not weaken an
assertion to make the suite green — record the defect as a new work item for the Planner, as
the trust-loop proof did.

Node 24 is required for the frontend half of the suite (`.nvmrc`).

## Dependencies

- frontend-pricing-page
- frontend-upgrade-prompts
- frontend-collections
- frontend-pro-quiet-hours
- frontend-account-and-billing-settings
