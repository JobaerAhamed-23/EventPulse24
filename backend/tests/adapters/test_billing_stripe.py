"""The real Stripe adapter (FR-48).

**No network and no Stripe account.** Signature verification runs for real — `stripe.Webhook`
computes an HMAC locally, so a correctly-signed payload can be built in the test and the SDK's
actual verification path is exercised, not a stand-in for it. The two outbound calls use an
injected client, following `HttpRevalidationAdapter`'s and `RedisThrottleAdapter`'s shape.

What these tests protect is the translation boundary: Stripe's vocabulary must stop here. A
status this adapter has never seen must not reach the app, and must not crash a live webhook.
"""

import hashlib
import hmac
import json
import time

import pytest

from adapters.billing.stripe import (
    STATUS_MAP,
    UNMAPPED_STATUS,
    USER_ID_METADATA_KEY,
    StripeBillingAdapter,
    mapped_status,
)
from ports.billing import (
    BillingCustomer,
    BillingEventKind,
    InvalidWebhookSignature,
    ProPlan,
)
from shared.ids import uuid7

SECRET = "whsec_test_secret_for_signing"


def _signed(body: dict) -> tuple[bytes, str]:
    """A payload and a header Stripe's own verifier accepts."""
    payload = json.dumps(body).encode()
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode() + payload
    signature = hmac.new(SECRET.encode(), signed_payload, hashlib.sha256).hexdigest()
    return payload, f"t={timestamp},v1={signature}"


def _adapter(client=None) -> StripeBillingAdapter:
    return StripeBillingAdapter(
        api_key="sk_test_not_a_real_key",
        webhook_secret=SECRET,
        price_ids={"monthly": "price_m", "yearly": "price_y"},
        client=client,
    )


def _subscription_event(event_type: str, *, status: str = "active", sub_id: str = "sub_1") -> dict:
    return {
        "id": "evt_1",
        "type": event_type,
        "created": 1_762_000_000,
        "data": {
            "object": {
                "id": sub_id,
                "customer": "cus_1",
                "status": status,
                "current_period_end": 1_765_000_000,
                "items": {"data": [{"price": {"recurring": {"interval": "month"}}}]},
            }
        },
    }


# ----------------------------------------------------------------- signature verification


def test_a_correctly_signed_payload_verifies():
    payload, signature = _signed(_subscription_event("customer.subscription.updated"))
    event = _adapter().parse_event(payload, signature=signature)
    assert event.kind is BillingEventKind.SUBSCRIPTION_CHANGED


def test_a_wrong_signature_is_refused():
    payload, _ = _signed(_subscription_event("customer.subscription.updated"))
    with pytest.raises(InvalidWebhookSignature):
        _adapter().parse_event(payload, signature="t=1,v1=deadbeef")


def test_a_tampered_payload_is_refused():
    """The signature covers the bytes. Changing one of them invalidates it."""
    payload, signature = _signed(_subscription_event("customer.subscription.updated"))
    tampered = payload.replace(b'"sub_1"', b'"sub_2"')
    assert tampered != payload
    with pytest.raises(InvalidWebhookSignature):
        _adapter().parse_event(tampered, signature=signature)


def test_reserialising_the_payload_breaks_verification():
    """Proof that the raw bytes matter: a semantically identical body with different
    whitespace does not verify. This is why the receiver must never parse before verifying."""
    body = _subscription_event("customer.subscription.updated")
    payload, signature = _signed(body)
    reserialised = json.dumps(body, indent=2).encode()
    assert json.loads(reserialised) == json.loads(payload)
    with pytest.raises(InvalidWebhookSignature):
        _adapter().parse_event(reserialised, signature=signature)


def test_a_malformed_payload_is_refused_as_an_invalid_signature():
    """A body that is not JSON is not a delivery we can trust, which is the same answer."""
    with pytest.raises(InvalidWebhookSignature):
        _adapter().parse_event(b"not json at all", signature="t=1,v1=x")


# ----------------------------------------------------------------- translation


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [
        ("checkout.session.completed", BillingEventKind.SUBSCRIPTION_STARTED),
        ("customer.subscription.updated", BillingEventKind.SUBSCRIPTION_CHANGED),
        ("customer.subscription.deleted", BillingEventKind.SUBSCRIPTION_ENDED),
        ("invoice.payment_failed", BillingEventKind.PAYMENT_FAILED),
        ("customer.created", BillingEventKind.IGNORED),
        ("some.type.invented.tomorrow", BillingEventKind.IGNORED),
    ],
)
def test_every_event_type_maps_to_one_kind(event_type, expected):
    payload, signature = _signed(_subscription_event(event_type))
    assert _adapter().parse_event(payload, signature=signature).kind is expected


@pytest.mark.parametrize(("raw", "expected"), sorted(STATUS_MAP.items()))
def test_every_known_stripe_status_maps(raw, expected):
    assert mapped_status(raw) == expected


def test_an_unknown_status_maps_conservatively_and_never_raises():
    """Stripe can add a status. A live webhook must not 500 because of it."""
    assert mapped_status("some_status_stripe_added_later") == UNMAPPED_STATUS
    assert mapped_status(None) == UNMAPPED_STATUS


def test_an_unknown_status_survives_a_whole_parse():
    payload, signature = _signed(
        _subscription_event("customer.subscription.updated", status="invented_by_stripe")
    )
    event = _adapter().parse_event(payload, signature=signature)
    assert event.status == UNMAPPED_STATUS
    # The original is carried through for the log line, and only for that.
    assert event.raw_status == "invented_by_stripe"


def test_the_mapped_status_and_the_raw_status_are_separate_fields():
    """They are two fields precisely so a provider string cannot be mistaken for ours."""
    payload, signature = _signed(
        _subscription_event("customer.subscription.updated", status="unpaid")
    )
    event = _adapter().parse_event(payload, signature=signature)
    assert (event.status, event.raw_status) == ("past_due", "unpaid")


def test_a_completed_checkout_carries_the_user_id_from_metadata():
    user_id = uuid7()
    body = {
        "id": "evt_2",
        "type": "checkout.session.completed",
        "created": 1_762_000_000,
        "data": {
            "object": {
                "customer": "cus_9",
                "subscription": "sub_9",
                "metadata": {USER_ID_METADATA_KEY: str(user_id)},
            }
        },
    }
    payload, signature = _signed(body)
    event = _adapter().parse_event(payload, signature=signature)
    assert event.user_id == user_id
    assert (event.customer_ref, event.subscription_ref) == ("cus_9", "sub_9")


def test_a_malformed_user_id_in_metadata_does_not_crash():
    """Metadata is free-form and a human can edit it in the dashboard."""
    body = {
        "id": "evt_3",
        "type": "checkout.session.completed",
        "created": 1_762_000_000,
        "data": {
            "object": {
                "customer": "c",
                "subscription": "s",
                "metadata": {USER_ID_METADATA_KEY: "not-a-uuid"},
            }
        },
    }
    payload, signature = _signed(body)
    assert _adapter().parse_event(payload, signature=signature).user_id is None


def test_the_plan_is_read_from_the_subscriptions_interval():
    payload, signature = _signed(_subscription_event("customer.subscription.updated"))
    assert _adapter().parse_event(payload, signature=signature).plan is ProPlan.MONTHLY


# ----------------------------------------------------------------- outbound calls


class _FakeSessions:
    def __init__(self, result):
        self.result = result
        self.params = None

    def create(self, params):
        self.params = params
        return self.result


class _FakeClient:
    def __init__(self, checkout_result=None, portal_result=None):
        self.checkout = type("C", (), {"sessions": _FakeSessions(checkout_result)})()
        self.billing_portal = type("B", (), {"sessions": _FakeSessions(portal_result)})()


def test_checkout_carries_the_user_id_as_metadata():
    """Without this, `checkout.session.completed` cannot name a user and a paying customer
    never becomes Pro. It is the cross-item contract with `checkout-and-portal-api`."""
    user_id = uuid7()
    result = type("S", (), {"id": "cs_1", "url": "https://checkout.example/cs_1"})()
    client = _FakeClient(checkout_result=result)

    session = _adapter(client).create_checkout(
        BillingCustomer(user_id=user_id, email="a@example.com"),
        ProPlan.YEARLY,
        success_url="https://app.example/ok",
        cancel_url="https://app.example/no",
    )

    params = client.checkout.sessions.params
    assert params["metadata"][USER_ID_METADATA_KEY] == str(user_id)
    assert params["line_items"][0]["price"] == "price_y"
    assert session.url == "https://checkout.example/cs_1"


def test_the_portal_uses_the_stored_customer_reference():
    result = type("S", (), {"url": "https://portal.example/x"})()
    client = _FakeClient(portal_result=result)

    portal = _adapter(client).create_portal_session("cus_7", return_url="https://app.example/s")

    assert client.billing_portal.sessions.params["customer"] == "cus_7"
    assert portal.url == "https://portal.example/x"


def test_the_adapter_is_constructible_with_no_arguments(settings):
    """`ports.registry.get_adapter` constructs every adapter with no arguments, so a
    required-argument constructor would be unreachable through the port."""
    adapter = StripeBillingAdapter()
    assert isinstance(adapter, StripeBillingAdapter)
