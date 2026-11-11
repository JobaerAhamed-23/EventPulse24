---
id: checkout-and-portal-api
title: A way to actually pay — checkout, portal, and the fake-billing dead end
intent: pro-tier-and-monetization
complexity: medium
mode: confirm
status: pending
depends_on: [billing-adapter-and-webhooks]
created: 2026-11-11
---

# Work Item: A way to actually pay — checkout, portal, and the fake-billing dead end

## Description

`BillingPort` can mint a checkout session and a portal session. Nothing calls either. This
item puts an authenticated API in front of both, so the frontend has something to send a
user to.

It also fixes a dead end that ships today: `adapters/billing/fake.py` sets
`FAKE_BILLING_URL = "http://127.0.0.1:3000/dev/fake-billing"` and builds checkout and portal
URLs under it, but the only route beneath `frontend/app/dev/` is `health`. In local and CI
mode the fake checkout redirects to a 404, so the paid path cannot be walked end to end
without this page existing.

## Acceptance Criteria

- [ ] An authenticated endpoint starts checkout for a chosen `ProPlan`, returning the
      session URL from `create_checkout`. It passes success and cancel URLs derived from
      configuration, never from client input.
- [ ] **A user who is already Pro cannot start a second checkout.** The endpoint refuses and
      points at the portal instead.
- [ ] An authenticated endpoint returns a portal session URL from `create_portal_session`,
      using the stored customer reference. A user with no subscription gets a clear refusal,
      not a Stripe error.
- [ ] **Entitlement is never granted by these endpoints.** Returning from a successful
      checkout changes nothing by itself; only the webhook from
      `billing-adapter-and-webhooks` moves `Subscription` state. A test proves that hitting
      the success URL without a webhook leaves the user Free.
- [ ] `frontend/app/dev/fake-billing/` exists with checkout and portal pages matching the
      query parameters `FakeBillingAdapter` emits (`session`, `plan`, `next`). It is
      obviously a development stand-in, and it is reachable only when the fake adapter is in
      use.
- [ ] The dev page can simulate both outcomes — completing and cancelling — so the local
      paid path and the local abandoned-checkout path are both walkable.
- [ ] Contract tests cover the new endpoints, and `frontend/lib/api/schema.ts` is
      regenerated.

## Technical Notes

Medium complexity: the endpoints are thin, and the decisions that matter were taken in items
1 and 2.

Success and cancel URLs come from configuration. Taking them from the request is the classic
open-redirect in a checkout flow, and the constitution's posture on validated-once config
points the same way.

The dev fake-billing page is deliberately in this item rather than a frontend item: it is
part of making the seam testable, and `e2e-proof-and-contract-tests` depends on it existing.
Keep it plain — it is a harness, not a design surface, and it must not be mistaken for
`pricing-page-desktop.html`, which is item `frontend-pricing-page`.

Follow the existing django-ninja API conventions in `apps/*/api.py` and the auth seam in
`apps/identity/api_auth.py`.

## Dependencies

- billing-adapter-and-webhooks
