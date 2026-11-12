---
work_item: billing-adapter-and-webhooks
intent: pro-tier-and-monetization
created: 2026-11-11
mode: validate
checkpoint_1: approved
---

# Design: Real Stripe, and the way subscription state gets back in

## Summary

Two pieces that are usually conflated and are not the same: the **outbound adapter**
(`adapters/billing/stripe.py`, implementing the existing `BillingPort`) and the **inbound
receiver** (an app-layer endpoint that turns Stripe's webhooks into the three commands item 1
built).

The architecture has already decided more of this than it first appears, and two decisions
that looked open are closed by contracts that already exist:

1. **The Stripe SDK, not `httpx`.** The `http-client` contract names `adapters.billing` in its
   *forbidden* source list for `httpx`, `httpcore`, `requests` and `urllib3`. The `stripe-sdk`
   contract exists solely to permit `adapters.billing` — and nothing else — to import
   `stripe`. Calling Stripe's REST API by hand is not an option that was left open; it is one
   the contracts already closed.

2. **Signature verification cannot live in the app layer.** `stripe-sdk` lists `apps` as a
   forbidden source, so `apps/*` may not import `stripe` and therefore cannot call
   `stripe.Webhook.construct_event`. Verification belongs to the adapter. **This drives the
   whole design**: `BillingPort` gains a parse-and-verify method, the endpoint hands it raw
   bytes and a signature header, and what comes back is a typed value the app understands with
   no Stripe vocabulary in it.

That is a better seam than the obvious one anyway. The receiver becomes testable through
`FakeBillingAdapter` with no SDK involved, and Stripe's event vocabulary stops at the adapter
boundary instead of leaking into `apps`.

**There is no idempotency table.** Item 1's row-level guards already provide it; adding one
would be a second mechanism for a problem that is solved. See Key Decisions.

## Scope

**In Scope:**
- `adapters/billing/stripe.py` implementing `BillingPort`, and `stripe` as a dependency
- A new port method for parse-and-verify, plus its fake implementation
- The app-layer webhook endpoint and its dispatch to item 1's three commands
- Mapping Stripe's status vocabulary onto `SubscriptionStatus`
- `billing` joining `REAL_ADAPTERS`, and the adapter-mode assertion updated to name what
  still remains missing

**Out of Scope:**
- Checkout and portal **endpoints** (`checkout-and-portal-api`) — this item builds the
  adapter methods they call, not the HTTP surface
- Any feature gate reading entitlement
- A reconciliation job as a safety net for missed webhooks
- Trials, proration, refunds, coupons, dunning emails
- Making `ADAPTER_MODE=real` boot. It still will not: `llm`, `embedding` and `email` remain
  without real adapters. This item must not look like it delivered go-live.

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| HTTP client | **Stripe SDK** | Forced by two existing contracts, not chosen: `http-client` forbids `adapters.billing` from importing any HTTP client, and `stripe-sdk` permits only `adapters.billing` to import `stripe`. |
| Where signatures are verified | **In the adapter, behind a new port method** | `apps` may not import `stripe` (`stripe-sdk` contract). Verification needs `stripe.Webhook.construct_event`, so it cannot live in the endpoint. |
| What the port returns | **A typed value with no Stripe vocabulary** | The app dispatches on our own enum, not on the string `"customer.subscription.deleted"`. Stripe's vocabulary stops at the adapter, as `ProPlan` and `CheckoutSession` already do. |
| Unverifiable payload | **The port raises; the endpoint answers 400** | A bad signature is not a routine outcome — it is someone posting to the endpoint. It is the one case that is an error rather than a `None`. |
| Idempotency store | **None. Reuse item 1's row guards** | A replayed `checkout.session.completed` hits the existing-live-row check; a replayed change or cancellation hits `last_event_at`. Both return `None` today, tested. A table of processed event ids would be a second mechanism for a solved problem, plus a retention category to justify. If a future event type needs id-level idempotency, add the table then, with the case that forced it. |
| Unknown event type | **Acknowledged, ignored, logged by slug** | A dashboard change must not break the endpoint. Returning non-2xx would make Stripe retry forever for something we deliberately do not handle. |
| Webhook for an unknown subscription | **Acknowledged, no state change** | Item 1's commands already return `None` for an unknown reference. Rejecting would invite infinite retries; this is logged so a real misconfiguration is still visible. |
| Endpoint auth | **Signature only. No session, no CSRF** | Stripe is not a browser and carries no cookie. The signature *is* the authentication. Django Ninja already exempts its views from Django's CSRF middleware (noted in `apps/identity/api.py`), so nothing must be added back. |
| Status mapping | **In the adapter, total, with an explicit fallback** | Stripe has nine statuses; `SubscriptionStatus` has four. Mapping lives with the vocabulary it translates. An unrecognised Stripe status maps to a conservative value rather than crashing. |
| Keys | **pydantic-settings, required, no default** | Follows `revalidation_secret` and `calendar_credential_key` at `config/env.py:58,99`: *"Required, with no default and no fallback."* |

## Technical Approach

### Architecture

```
   Stripe ──POST /webhooks/billing──▶ apps/identity/webhooks_api.py
                                            │  raw bytes + Stripe-Signature header
                                            ▼
                                   get_billing_port().parse_event(...)
                                            │
                     ┌──────────────────────┴───────────────────────┐
            adapters/billing/stripe.py                   adapters/billing/fake.py
         stripe.Webhook.construct_event                  (deterministic, no SDK)
                     └──────────────────────┬───────────────────────┘
                                            │  BillingEvent  (our vocabulary)
                                            ▼
                         record_subscription_started / _changed / _ended
                                            │
                                            ▼
                                   Subscription  (PERSONAL)
```

The endpoint contains no Stripe vocabulary and no SDK import. It reads bytes, calls the port,
matches on our own enum, and calls one command.

### Port Changes

`ports/billing.py` gains a parse-and-verify method and the value it returns. The port stays
the only thing `apps` imports; the SDK stays inside `adapters.billing`.

```python
class BillingEventKind(StrEnum):
    SUBSCRIPTION_STARTED = "subscription_started"
    SUBSCRIPTION_CHANGED = "subscription_changed"
    SUBSCRIPTION_ENDED   = "subscription_ended"
    PAYMENT_FAILED       = "payment_failed"
    IGNORED              = "ignored"        # a type we deliberately do not handle

@dataclass(frozen=True)
class BillingEvent:
    kind: BillingEventKind
    event_id: str
    occurred_at: datetime          # becomes `event_at`, item 1's ordering guard
    customer_ref: str | None
    subscription_ref: str | None
    user_id: UUID | None           # from checkout session metadata
    plan: ProPlan | None
    current_period_end: datetime | None

class InvalidWebhookSignature(Exception): ...

class BillingPort(ABC):
    @abstractmethod
    def parse_event(self, payload: bytes, *, signature: str) -> BillingEvent: ...
```

`PAYMENT_FAILED` is its own kind rather than a `CHANGED` carrying `past_due`, because
`invoice.payment_failed` does not itself say what the subscription's status became — Stripe
sends a separate `customer.subscription.updated` for that. Collapsing them would have the
receiver inventing a status Stripe did not report.

### How the user is identified

`checkout.session.completed` is the only event that can name a user, and it does so only if
checkout was created with metadata. **The adapter reads `user_id` from the session's
metadata**, which `checkout-and-portal-api` must therefore set when it creates the session.
That is a cross-item contract and is recorded in this design so item 3 inherits it rather
than discovering it.

Later events carry only Stripe references, which is why item 1's `_changed` and `_ended`
commands look a subscription up by `stripe_subscription_ref` rather than by user.

### API Changes

- `POST /webhooks/billing` — unauthenticated by session, authenticated by signature.
  Returns 200 for handled, ignored and unknown-subscription cases; 400 only for a payload
  that does not verify.

### Dependencies

- `stripe` added to `backend/pyproject.toml` `dependencies`, pinned exactly, as every other
  dependency there is.
- `subscription-model-and-entitlement` (item 1) — the commands this dispatches to.

## Affected Files

| File | Action | Purpose |
|---|---|---|
| `backend/pyproject.toml` | modify | Add pinned `stripe`; no contract edit needed — `stripe-sdk` already exists |
| `backend/ports/billing.py` | modify | `BillingEvent`, `BillingEventKind`, `InvalidWebhookSignature`, `parse_event` |
| `backend/adapters/billing/stripe.py` | create | The real adapter: checkout, portal, parse-and-verify, status mapping |
| `backend/adapters/billing/fake.py` | modify | Implement `parse_event` deterministically, no SDK |
| `backend/apps/identity/webhooks_api.py` | create | The receiver; dispatch to the three commands |
| `backend/config/api.py` | modify | Mount the webhook router |
| `backend/config/adapters.py` | modify | `billing` joins `REAL_ADAPTERS` |
| `backend/config/env.py` | modify | `stripe_api_key`, `stripe_webhook_secret` — required, no default |
| `.env.example` | modify | Local-only placeholders |
| `backend/tests/config/test_adapters.py` | modify | Assertion now names `email, embedding, llm` |
| `backend/tests/adapters/test_billing_stripe.py` | create | Adapter tests, no network |
| `backend/tests/identity/test_billing_webhooks.py` | create | Receiver tests via the fake |

## Security Considerations

- **The signature is the authentication.** No session, no CSRF, no bearer. A request that does
  not verify changes nothing and is answered 400.
- **Raw bytes, not a parsed body.** Signature verification is over the exact payload; letting
  a JSON parser normalise it first breaks verification and invites a bypass. The endpoint must
  read the raw request body.
- **No secret in source control.** `stripe_api_key` and `stripe_webhook_secret` are required
  settings with no defaults, validated at startup, per the constitution.
- **Secrets cannot reach a log sink even by accident.** `adapters/logging/redaction.py` is
  deny-by-default, and its value scrubber already carries `sk_live`, `sk_test` and `whsec`
  patterns — verified during item 1.
- **The response body says nothing.** A 400 does not explain *why* verification failed.
- **No Stripe object is logged.** It can carry an email, a name and the last four digits of a
  card. The endpoint logs a kind slug, an event id and an outcome.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Framework parses the body before verification | Signatures fail, or a bypass | Read raw bytes explicitly; a test posts a payload whose byte form differs from its re-serialised form |
| An out-of-order event regresses state | A cancelled user becomes Pro again | Item 1's `last_event_at` guard, already tested there; re-asserted end-to-end here |
| A replay double-applies | Double entitlement | Item 1's existing-live-row check and the guard; tested |
| Stripe adds or renames a status | Crash on a live webhook | Total mapping with a conservative fallback, tested with a status the mapping has never seen |
| Checkout created without `user_id` metadata | A paid user never becomes Pro | Stated as a cross-item contract for item 3; the receiver logs loudly and returns 200 rather than silently discarding |
| This item appears to deliver go-live | Someone sets `ADAPTER_MODE=real` and it fails at boot | The adapter-mode assertion is updated to name the three that remain, and it is an AC |
| SDK version drift | Verification behaviour changes | Pinned exactly, like every dependency in `pyproject.toml` |

## Implementation Checklist

- [ ] `stripe` pinned in `pyproject.toml`; `lint-imports` still reports 19 contracts kept
- [ ] `ports/billing.py`: `BillingEventKind`, `BillingEvent`, `InvalidWebhookSignature`, `parse_event`
- [ ] `adapters/billing/stripe.py`: checkout, portal, parse-and-verify, total status mapping
- [ ] `adapters/billing/fake.py`: `parse_event` implemented deterministically, no SDK import
- [ ] `apps/identity/webhooks_api.py`: raw-body read, dispatch, 200/400 discipline, no Stripe vocabulary
- [ ] Router mounted in `config/api.py` with a comment saying why it has no `auth=`
- [ ] `billing` in `REAL_ADAPTERS`; `tests/config/test_adapters.py` names the remaining three
- [ ] `config/env.py` + `.env.example`: two required settings, local-only placeholders
- [ ] Tests: bad signature → 400 and no state change; replay; out-of-order; each of the four
      kinds; an unknown type; an unknown subscription; an unmapped Stripe status; a payload
      whose re-serialised bytes differ
- [ ] Every new test shown to fail for the right reason before it is counted
- [ ] `make lint-backend`, `make test-backend`: no new failures beyond the 16 pre-existing

---
*FIRE Flow — Checkpoint 1 pending approval*
