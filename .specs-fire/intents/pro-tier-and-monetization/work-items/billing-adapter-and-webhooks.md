---
id: billing-adapter-and-webhooks
title: Real Stripe, and the way subscription state gets back in
intent: pro-tier-and-monetization
complexity: high
mode: validate
status: completed
depends_on:
  - subscription-model-and-entitlement
created: 2026-11-11
run_id: run-eventpulse24-027
completed_at: 2026-11-11T08:44:27.984Z
---

# Work Item: Real Stripe, and the way subscription state gets back in

## Description

`ports/billing.py` declares exactly two methods, `create_checkout` and
`create_portal_session`. Both send the user **to** Stripe. Nothing in the port brings
subscription state back, and `grep -rn webhook backend/ --include='*.py'` returns nothing —
this codebase has no inbound webhook endpoint for any purpose.

So this item builds two things that are usually conflated and are not the same: the
**outbound adapter** (`adapters/billing/stripe.py`, implementing the existing port) and the
**inbound receiver** (an app-layer HTTP endpoint and handler, which is *not* a port method
because nothing calls out).

The receiver is the risk. Stripe retries, replays, and delivers out of order. A naive
handler lets a stale `customer.subscription.updated` overwrite a newer
`customer.subscription.deleted`, silently restoring entitlement to someone who cancelled.
That is why this item is `validate`.

## Acceptance Criteria

- [ ] `adapters/billing/stripe.py` implements `BillingPort` against the real API, and
      `billing` joins `REAL_ADAPTERS` in `config/adapters.py`.
- [ ] **`ADAPTER_MODE=real` still does not boot**, and a test asserts why: `llm`, `embedding`
      and `email` remain missing, so `_mode_paths` still raises `ImproperlyConfigured`. The
      existing assertion at `tests/config/test_adapters.py:30` is updated to name the three
      that remain, not the four that do now. This item must not appear to deliver go-live.
- [ ] The webhook receiver **verifies Stripe's signature** and rejects an unsigned or
      wrongly-signed payload before parsing it.
- [ ] It handles `checkout.session.completed`, `customer.subscription.updated`,
      `customer.subscription.deleted` and `invoice.payment_failed`, mapping each to exactly
      one named `identity` command from `subscription-model-and-entitlement`.
- [ ] **Idempotent:** the same event delivered twice changes state once. The second delivery
      is recorded as a no-op, not an error, and returns success so Stripe stops retrying.
- [ ] **Order-tolerant:** an event that is older than the state already stored is ignored.
      Follow the precedent in `SavedEvent`, whose `event_version` guard exists so that *"a
      retried, partial or out-of-order run can neither double-apply nor let an older
      postponement overwrite a newer one"*.
- [ ] An **unknown or unhandled event type** is acknowledged and ignored without error, so a
      Stripe dashboard change cannot break the endpoint.
- [ ] If a cache was specified by item 1's design, every handled event invalidates it, and a
      test proves entitlement reflects the change immediately after the webhook returns.
- [ ] Keys are read once at startup via pydantic-settings, per the constitution's *"config is
      validated once at startup"*. `.env.example` gains local-only placeholders in the style
      of `DJANGO_SECRET_KEY` and `REVALIDATION_SECRET`. **No credential enters source
      control.**
- [ ] Both adapter and receiver are proven **without a Stripe account and without a
      network**, and CI stays secret-free.

      *(Corrected 2026-11-11, during item 1.* An earlier version of this criterion named
      `tests/adapters/scripted_network.py` as a shared harness used by `test_crawl_http.py`,
      `test_revalidation_http.py` and `test_calendar_ics.py`. That was wrong on both counts:
      that module is bound to `HttpFetchAdapter` — it injects into `getaddrinfo` and the TCP
      connector *that adapter* supplies, and imports `FetchLimits` and `HttpFetchAdapter`
      directly — and **only** `test_crawl_http.py` uses it. `test_revalidation_http.py` uses a
      local stand-in for `httpx.Client`; `test_calendar_ics.py` uses
      `tests/adapters/calendar_fakes.ScriptedFetch`. The pattern to follow here is
      `test_revalidation_http.py`'s, or the Stripe SDK's own test constructs — the design doc
      decides. The conclusion is unchanged: no account, no network.)*
- [ ] Tests cover: signature rejection; a replayed event; an out-of-order event that must not
      regress state; each of the four event types reaching its command; an unknown type; and
      a cancellation closing entitlement.

## Technical Notes

High complexity, so this item gets a design doc. The design must decide:

- **Where the receiver lives.** It is an app-layer endpoint, but which app? It writes
  `identity` state, so `identity` is the obvious home; confirm it does not drag an HTTP
  concern somewhere the import contracts forbid — check
  `tests/architecture/test_import_contracts.py` before choosing.
- **How idempotency is recorded.** Storing Stripe's event id is the usual answer and makes
  replays cheap to detect, but it is another table with a retention category to declare.
- **What "older" means for ordering.** Stripe events carry a `created` timestamp, but two
  events in the same second are possible; the subscription object's own version or period
  fields may be the sounder comparator. Decide explicitly, and write the test that fails
  under the naive choice.
- **The failure mode when a webhook arrives for an unknown user.** Acknowledge and log, or
  reject? Acknowledging hides a real bug; rejecting invites infinite Stripe retries.

Note the port stays outbound-only. Resist adding `fetch_subscription()` here: a pull-based
reconcile was considered and rejected during capture because it leaves entitlement stale on
a hot path. If a reconciliation job is wanted later as a safety net against missed webhooks,
that is a separate item, not a quiet addition to this one.

## Dependencies

- subscription-model-and-entitlement
