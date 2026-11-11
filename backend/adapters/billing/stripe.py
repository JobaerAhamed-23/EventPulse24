"""The real billing adapter: Stripe checkout, the customer portal, and webhook verification.

**This is the only module in the project allowed to import the Stripe SDK.** The `stripe-sdk`
import contract names every other package as a forbidden source, and it was written before
this module existed — the architecture reserved the seam and this fills it.

That contract is also why `parse_event` lives behind a port rather than in the webhook
endpoint. Verifying a signature means calling `stripe.Webhook.construct_event`, and `apps` may
not import `stripe`. So the endpoint hands this adapter raw bytes and gets back a
`BillingEvent` in the product's own vocabulary. Stripe's event names and status strings stop
here.

**The SDK, not an HTTP client.** `adapters.billing` appears in the `http-client` contract's
forbidden list for `httpx`, `httpcore`, `requests` and `urllib3`, so calling Stripe's REST API
by hand is not an available option. The SDK brings `requests` transitively, which the contract
permits because it allows indirect imports — verified, not assumed.

**Stripe's nine statuses map onto four of ours, and the mapping is total.** An unrecognised
status does not crash a live webhook: it maps conservatively and carries the original string
through as `raw_status` so a log line can name it. Being wrong in the generous direction for
one webhook is recoverable; a 500 on every delivery is not.
"""

from datetime import UTC, datetime
from functools import cached_property
from uuid import UUID

import stripe
from django.conf import settings

from ports.billing import (
    BillingCustomer,
    BillingEvent,
    BillingEventKind,
    BillingPort,
    CheckoutSession,
    InvalidWebhookSignature,
    PortalSession,
    ProPlan,
)

#: Stripe's subscription statuses, mapped onto ours. `incomplete` and `trialing` are deliberate
#: entries rather than oversights: this product sells no trial, and a checkout that never
#: completed is not a subscription here, so both read as "not yet entitled".
STATUS_MAP = {
    "active": "active",
    "past_due": "past_due",
    "unpaid": "past_due",
    "canceled": "canceled",
    "incomplete": "expired",
    "incomplete_expired": "expired",
    "trialing": "active",
    "paused": "expired",
}

#: What an unmapped Stripe status becomes. `past_due` rather than `canceled` or `active`: it
#: keeps a paying user entitled while the situation is understood, and it is the one value that
#: is visible to the user on the account screen, so an unknown state cannot hide silently.
UNMAPPED_STATUS = "past_due"

#: Stripe event types this product acts on. Everything else is `IGNORED` — acknowledged, so
#: Stripe stops retrying, and never an error.
EVENT_KINDS = {
    "checkout.session.completed": BillingEventKind.SUBSCRIPTION_STARTED,
    "customer.subscription.updated": BillingEventKind.SUBSCRIPTION_CHANGED,
    "customer.subscription.deleted": BillingEventKind.SUBSCRIPTION_ENDED,
    "invoice.payment_failed": BillingEventKind.PAYMENT_FAILED,
}

#: The metadata key the checkout session must carry so the completed event can name a user.
#: `checkout-and-portal-api` sets it; without it a paid checkout can never be attributed.
USER_ID_METADATA_KEY = "user_id"

_PLAN_BY_VALUE = {plan.value: plan for plan in ProPlan}


class StripeBillingAdapter(BillingPort):
    def __init__(
        self,
        api_key: str | None = None,
        webhook_secret: str | None = None,
        price_ids: dict[str, str] | None = None,
        client=None,
    ) -> None:
        """Every argument optional and resolved from settings lazily.

        `ports.registry.get_adapter` constructs every adapter with **no arguments**, so a
        required-argument constructor would be unreachable through the port. The optional
        shape is the same one `HttpRevalidationAdapter` and `RedisThrottleAdapter` use, and
        it is what lets a test inject a stand-in without touching settings.

        The SDK client is built lazily rather than here: importing this module must not
        require a key, or collecting the test suite would need one.
        """
        self._api_key = api_key
        self._webhook_secret = webhook_secret
        self._price_ids = price_ids
        self._injected_client = client

    @cached_property
    def _client(self):
        return self._injected_client or stripe.StripeClient(
            self._api_key or settings.STRIPE_API_KEY
        )

    @property
    def _secret(self) -> str:
        return self._webhook_secret or settings.STRIPE_WEBHOOK_SECRET

    @property
    def _prices(self) -> dict[str, str]:
        return self._price_ids if self._price_ids is not None else settings.STRIPE_PRICE_IDS

    def create_checkout(
        self, customer: BillingCustomer, plan: ProPlan, *, success_url: str, cancel_url: str
    ) -> CheckoutSession:
        """Mint a checkout session, carrying the user id as metadata.

        The metadata is not decoration: `checkout.session.completed` is the only event that can
        attribute a payment to an account, and it can do so only because of this.
        """
        session = self._client.checkout.sessions.create(
            params={
                "mode": "subscription",
                "line_items": [{"price": self._prices[plan.value], "quantity": 1}],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "customer_email": customer.email,
                "client_reference_id": str(customer.user_id),
                "metadata": {USER_ID_METADATA_KEY: str(customer.user_id)},
                "subscription_data": {"metadata": {USER_ID_METADATA_KEY: str(customer.user_id)}},
            }
        )
        return CheckoutSession(session_id=session.id, url=session.url or "")

    def create_portal_session(self, customer_ref: str, *, return_url: str) -> PortalSession:
        session = self._client.billing_portal.sessions.create(
            params={"customer": customer_ref, "return_url": return_url}
        )
        return PortalSession(url=session.url)

    def parse_event(self, payload: bytes, *, signature: str) -> BillingEvent:
        try:
            event = stripe.Webhook.construct_event(payload, signature, self._secret)
        except (stripe.SignatureVerificationError, ValueError) as exc:
            # A `ValueError` here is a malformed payload, which is the same thing from the
            # caller's point of view: not a delivery we can trust.
            raise InvalidWebhookSignature(str(exc)) from exc

        kind = EVENT_KINDS.get(event["type"], BillingEventKind.IGNORED)
        obj = event["data"]["object"]
        occurred_at = datetime.fromtimestamp(event["created"], tz=UTC)

        if kind is BillingEventKind.IGNORED:
            return BillingEvent(kind=kind, event_id=event["id"], occurred_at=occurred_at)
        if kind is BillingEventKind.SUBSCRIPTION_STARTED:
            return self._started(event, obj, occurred_at)
        if kind is BillingEventKind.PAYMENT_FAILED:
            return BillingEvent(
                kind=kind,
                event_id=event["id"],
                occurred_at=occurred_at,
                customer_ref=obj.get("customer"),
                subscription_ref=obj.get("subscription"),
            )
        return self._subscription(kind, event, obj, occurred_at)

    # ---------------------------------------------------------------- translation helpers

    def _started(self, event, obj, occurred_at: datetime) -> BillingEvent:
        raw_user = (obj.get("metadata") or {}).get(USER_ID_METADATA_KEY) or obj.get(
            "client_reference_id"
        )
        return BillingEvent(
            kind=BillingEventKind.SUBSCRIPTION_STARTED,
            event_id=event["id"],
            occurred_at=occurred_at,
            customer_ref=obj.get("customer"),
            subscription_ref=obj.get("subscription"),
            user_id=_as_uuid(raw_user),
            # A checkout session does not carry the price, so the plan is resolved from the
            # session's own metadata if present and otherwise left to the caller's default.
            plan=_PLAN_BY_VALUE.get((obj.get("metadata") or {}).get("plan", "")),
        )

    def _subscription(self, kind, event, obj, occurred_at: datetime) -> BillingEvent:
        raw_status = obj.get("status")
        period_end = obj.get("current_period_end")
        return BillingEvent(
            kind=kind,
            event_id=event["id"],
            occurred_at=occurred_at,
            customer_ref=obj.get("customer"),
            subscription_ref=obj.get("id"),
            plan=_plan_from_subscription(obj),
            current_period_end=(datetime.fromtimestamp(period_end, tz=UTC) if period_end else None),
            status=mapped_status(raw_status),
            raw_status=raw_status,
        )


def mapped_status(raw_status: str | None) -> str:
    """Stripe's status as one of ours. Total: an unknown status never raises."""
    return STATUS_MAP.get(raw_status or "", UNMAPPED_STATUS)


def _as_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        # Metadata is free-form and a human can edit it in the dashboard. A malformed id is
        # "we cannot attribute this", not a crash on a live webhook.
        return None


def _plan_from_subscription(obj) -> ProPlan | None:
    """The plan, read from the subscription's interval. `None` when Stripe did not say."""
    items = (obj.get("items") or {}).get("data") or []
    if not items:
        return None
    interval = ((items[0].get("price") or {}).get("recurring") or {}).get("interval")
    if interval == "month":
        return ProPlan.MONTHLY
    if interval == "year":
        return ProPlan.YEARLY
    return None


__all__ = [
    "EVENT_KINDS",
    "STATUS_MAP",
    "UNMAPPED_STATUS",
    "USER_ID_METADATA_KEY",
    "StripeBillingAdapter",
    "mapped_status",
]
