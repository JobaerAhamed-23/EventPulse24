"""Local stand-in for billing: hands back placeholder sessions, charges nothing.

`parse_event` is implemented here too, and it is what lets the webhook receiver be built and
tested with no SDK and no network. The fake's "signature" is a fixed sentinel rather than a
real HMAC: the point of a test at that level is the receiver's dispatch, its 200/400
discipline and its ordering behaviour, none of which depend on real cryptography. The real
signature check is the real adapter's job and is tested there.
"""

import json
from datetime import UTC, datetime
from urllib.parse import urlencode
from uuid import UUID

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
from shared.ids import uuid7

FAKE_BILLING_URL = "http://127.0.0.1:3000/dev/fake-billing"

#: The only "signature" the fake accepts. Anything else raises, so a test can exercise the
#: receiver's 400 path without a signing secret.
FAKE_SIGNATURE = "fake-signature"


class FakeBillingAdapter(BillingPort):
    def create_checkout(
        self, customer: BillingCustomer, plan: ProPlan, *, success_url: str, cancel_url: str
    ) -> CheckoutSession:
        session_id = f"fake_cs_{uuid7().hex}"
        query = urlencode({"session": session_id, "plan": plan.value, "next": success_url})
        return CheckoutSession(session_id=session_id, url=f"{FAKE_BILLING_URL}/checkout?{query}")

    def create_portal_session(self, customer_ref: str, *, return_url: str) -> PortalSession:
        query = urlencode({"next": return_url})
        return PortalSession(url=f"{FAKE_BILLING_URL}/portal?{query}")

    def parse_event(self, payload: bytes, *, signature: str) -> BillingEvent:
        """Accept `FAKE_SIGNATURE`, and read the event straight out of the JSON body.

        The body's shape is the fake's own, not Stripe's: a test writes what it means
        (`{"kind": "subscription_ended", ...}`) rather than reconstructing a provider
        envelope that this adapter would only throw away.
        """
        if signature != FAKE_SIGNATURE:
            raise InvalidWebhookSignature("fake adapter: signature mismatch")

        body = json.loads(payload.decode())
        kind = BillingEventKind(body.get("kind", BillingEventKind.IGNORED.value))
        plan = body.get("plan")
        user_id = body.get("user_id")
        period_end = body.get("current_period_end")
        return BillingEvent(
            kind=kind,
            event_id=body.get("event_id", "evt_fake"),
            occurred_at=datetime.fromtimestamp(body.get("occurred_at", 0), tz=UTC),
            customer_ref=body.get("customer_ref"),
            subscription_ref=body.get("subscription_ref"),
            user_id=UUID(user_id) if user_id else None,
            plan=ProPlan(plan) if plan else None,
            current_period_end=(datetime.fromtimestamp(period_end, tz=UTC) if period_end else None),
            status=body.get("status"),
            raw_status=body.get("raw_status"),
        )
