"""Local stand-in for billing: hands back placeholder sessions, charges nothing."""

from urllib.parse import urlencode

from ports.billing import BillingCustomer, BillingPort, CheckoutSession, PortalSession, ProPlan
from shared.ids import uuid7

FAKE_BILLING_URL = "http://127.0.0.1:3000/dev/fake-billing"


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
