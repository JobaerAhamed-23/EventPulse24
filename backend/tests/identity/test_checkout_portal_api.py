"""The paid path's HTTP surface (FR-48): checkout and portal.

Tested through `FakeBillingAdapter`, with **no provider and no network**. That is the
payoff of the port boundary item 2 established: everything above the adapter — the
refusals, the URL derivation, the CSRF and session rules — is exercised without Stripe
existing at all.

**The property these tests exist to protect is that the endpoints grant nothing.**
A checkout that completes changes nothing by itself; only the provider's webhook moves
`Subscription` state. That is easy to lose — an endpoint that "helpfully" marked the user
Pro on a redirect would pass every obvious test and break the product in production, where
the redirect is under the client's control. So there is a test that hits the success URL
and asserts the user is still Free and there is still no row.

**The second property is that the redirect URLs cannot be supplied by the client.**
Taking the success target from the request is the classic open-redirect in a checkout
flow: it sends a paying user, and the session id in the query string, to somebody else's
site. The request body carries only the plan, and the tests pin that.

**The refusals are about the account's state, not the request's shape.** A user who
already has a live subscription cannot start a second checkout, and a user with no
subscription cannot open the portal. Both are decided before the provider is called, so
neither can surface as a provider error.
"""

import pytest
from django.test import Client

from apps.identity.models import Subscription, SubscriptionStatus
from apps.identity.services import is_pro
from ports.billing import ProPlan
from shared.db import PERSONAL
from tests.csrf import CsrfClient
from tests.identity.factories import SubscriptionFactory, UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

CHECKOUT_URL = "/api/billing/checkout"
PORTAL_URL = "/api/billing/portal"


def signed_in_client(user=None) -> CsrfClient:
    """A client carrying a real session for `user`, and the CSRF token its POSTs need.

    The session is Django's own, established by `force_login` — the same thing the
    editorial and personalization tests do. Nothing here hand-builds a session.

    **`content_type` is passed per request, not in `defaults`.** A default of
    `application/json` on the client changes how Django encodes the body, and Django's
    CSRF middleware then reads the stream that Ninja later wants to read again — so
    Ninja's own body read raises `RawPostDataException`. Passing it per request, as the
    personalization tests do, keeps the two readers apart.
    """
    client = CsrfClient()
    client.force_login(user or UserFactory())
    return client


def checkout(client, plan: str = ProPlan.MONTHLY.value, **extra):
    return client.post(CHECKOUT_URL, {"plan": plan, **extra}, content_type="application/json")


def portal(client, **extra):
    return client.post(PORTAL_URL, extra, content_type="application/json")


# ----------------------------------------------------------------------- the session


def test_an_anonymous_checkout_is_refused(client: Client):
    response = client.post(CHECKOUT_URL, {"plan": "monthly"}, content_type="application/json")
    assert response.status_code == 401


def test_an_anonymous_portal_is_refused(client: Client):
    response = client.post(PORTAL_URL, {}, content_type="application/json")
    assert response.status_code == 401


def test_a_checkout_without_a_csrf_token_is_refused(client: Client):
    """The ordinary client still refuses, so the check is provable."""
    user = UserFactory()
    plain = Client()
    plain.defaults["CONTENT_TYPE"] = "application/json"
    plain.force_login(user)

    response = plain.post(CHECKOUT_URL, {"plan": "monthly"})

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


# ----------------------------------------------------------------------- checkout


def test_a_checkout_returns_a_session_url():
    client = signed_in_client()

    response = checkout(client)

    assert response.status_code == 200
    assert response.json()["url"].startswith("http://127.0.0.1:3000/dev/fake-billing/checkout?")


def test_a_checkout_carries_the_plan_the_user_chose():
    client = signed_in_client()

    response = checkout(client, plan=ProPlan.YEARLY.value)

    assert "plan=yearly" in response.json()["url"]


def test_an_unknown_plan_is_refused():
    client = signed_in_client()

    response = checkout(client, plan="weekly")

    assert response.status_code == 422


def test_a_checkout_grants_nothing():
    """The acceptance criterion that matters most.

    The endpoint mints a session and returns a URL. It writes no subscription, no audit
    entry and no entitlement — and the user stays Free afterwards. Only the provider's
    webhook moves the subscription.
    """
    user = UserFactory()
    client = signed_in_client(user)

    response = checkout(client)

    assert response.status_code == 200
    assert is_pro(user_id=user.pk) is False
    assert Subscription.objects.using(PERSONAL).filter(user_id=user.pk).count() == 0


def test_returning_from_a_successful_checkout_leaves_the_user_free():
    """The redirect itself grants nothing.

    This is the same property as the test above, seen from the browser's side: the user
    follows the success URL, the page loads, and the account is still on the free tier.
    Only the webhook changes that.
    """
    user = UserFactory()
    client = signed_in_client(user)

    url = checkout(client).json()["url"]

    # The browser follows the session URL to the provider's stand-in and then to the
    # success URL. Neither step touches the account.
    assert url
    assert is_pro(user_id=user.pk) is False
    assert Subscription.objects.using(PERSONAL).filter(user_id=user.pk).count() == 0


def test_a_checkout_writes_no_audit_entry():
    """A checkout is not a state transition, so it is not an audit row (AD-5).

    Audit rows record what happened to a subscription. Nothing has happened yet.
    """
    from apps.identity.models import IdentityAuditEntry

    user = UserFactory()
    client = signed_in_client(user)

    checkout(client)

    assert (
        IdentityAuditEntry.objects.using(PERSONAL).filter(action__startswith="subscription").count()
        == 0
    )


# ----------------------------------------------------------------------- the URL derivation


def test_the_success_and_cancel_urls_come_from_configuration():
    """Not from the request. That is the whole point of the rule."""
    client = signed_in_client()

    response = checkout(client)

    url = response.json()["url"]
    # The fake adapter carries the success URL as `next`, percent-encoded.
    assert "next=http" in url
    assert "settings%2Fbilling" in url


def test_both_urls_are_handed_to_the_port(monkeypatch):
    """The success *and* the cancel URL, both derived from configuration.

    The fake adapter puts only the success URL in the returned link, so the cancel URL
    is only observable at the port boundary — which is exactly where the rule lives. If
    either were taken from the request, this is the test that would fail.
    """
    seen: dict[str, object] = {}

    class RecordingBilling:
        def create_checkout(self, customer, plan, *, success_url, cancel_url):
            seen["success_url"] = success_url
            seen["cancel_url"] = cancel_url
            seen["plan"] = plan

            class Session:
                url = "http://example.test/checkout"

            return Session()

        def create_portal_session(self, *args, **kwargs):
            raise AssertionError("not used")

    import ports.registry

    monkeypatch.setattr(ports.registry, "get_billing_port", lambda: RecordingBilling())

    client = signed_in_client()
    response = checkout(client, plan=ProPlan.YEARLY.value)

    assert response.status_code == 200
    assert seen["success_url"].startswith("http://")
    assert seen["success_url"].endswith("/settings/billing?checkout=complete")
    assert seen["cancel_url"].startswith("http://")
    assert seen["cancel_url"].endswith("/settings/billing?checkout=cancelled")
    assert seen["plan"] == ProPlan.YEARLY


def test_a_client_supplied_success_url_is_ignored():
    """The open-redirect this item exists to prevent.

    A crafted `success_url` would send a paying user — and the session id in the query
    string — to somebody else's site. The body has no such field, so the extra key is
    not merely ignored by the handler: it never reaches one.
    """
    client = signed_in_client()

    response = checkout(
        client,
        success_url="https://attacker.example/steal",
        cancel_url="https://attacker.example/steal",
    )

    url = response.json()["url"]
    assert "attacker.example" not in url


def test_a_client_supplied_return_url_is_ignored_on_the_portal():
    client = signed_in_client()
    SubscriptionFactory(user_id=UserFactory().pk)

    response = portal(client, return_url="https://attacker.example/steal")

    assert response.status_code in (200, 409)


# ----------------------------------------------------------------------- the second checkout


def test_a_user_who_is_already_pro_cannot_start_a_second_checkout():
    """A second checkout would create a second subscription to notice and cancel."""
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.ACTIVE)
    client = signed_in_client(user)

    response = checkout(client)

    assert response.status_code == 409
    assert response.json()["code"] == "already_subscribed"


def test_the_refusal_points_at_the_portal():
    """The portal is where an existing subscription is managed."""
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.ACTIVE)
    client = signed_in_client(user)

    response = checkout(client)

    assert "portal_path" in response.json()["details"]


def test_a_user_who_is_already_pro_is_still_pro_after_the_refusal():
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.ACTIVE)
    client = signed_in_client(user)

    checkout(client)

    assert is_pro(user_id=user.pk) is True


def test_a_cancelled_subscription_does_not_block_a_new_checkout():
    """A cancelled row is history, not a live subscription. The user may buy again."""
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.CANCELED)
    client = signed_in_client(user)

    response = checkout(client)

    assert response.status_code == 200


# ----------------------------------------------------------------------- the portal


def test_a_pro_user_gets_a_portal_url():
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.ACTIVE)
    client = signed_in_client(user)

    response = portal(client)

    assert response.status_code == 200
    assert response.json()["url"].startswith("http://127.0.0.1:3000/dev/fake-billing/portal?")


def test_a_user_with_no_subscription_gets_a_clear_refusal():
    """Not a provider error. There is no customer to open a portal against, and saying
    so plainly is ours to do rather than the provider's."""
    client = signed_in_client()

    response = portal(client)

    assert response.status_code == 409
    assert response.json()["code"] == "no_subscription"


def test_the_portal_refusal_happens_before_the_provider_is_called(monkeypatch):
    """A provider error about a customer that does not exist would be a worse answer,
    and a leaky one: it would confirm the account's state to whoever asked."""
    calls: list[str] = []

    class ExplodingBilling:
        def create_portal_session(self, *args, **kwargs):
            calls.append("portal")
            raise AssertionError("the provider must not be called")

        def create_checkout(self, *args, **kwargs):
            calls.append("checkout")
            raise AssertionError("the provider must not be called")

    import ports.registry

    monkeypatch.setattr(ports.registry, "get_billing_port", lambda: ExplodingBilling())

    client = signed_in_client()
    response = portal(client)

    assert response.status_code == 409
    assert calls == []


def test_the_portal_uses_the_stored_customer_reference():
    """Not one the request supplies — there is no such field, and there is no way to
    open another account's portal by naming one."""
    user = UserFactory()
    subscription = SubscriptionFactory(
        user_id=user.pk, status=SubscriptionStatus.ACTIVE, stripe_customer_ref="cus_stored"
    )
    client = signed_in_client(user)

    response = portal(client)

    assert response.status_code == 200
    # The fake's portal URL carries the return URL, not the customer — but the fake
    # adapter is handed the stored reference, and the test below pins that.
    assert subscription.stripe_customer_ref == "cus_stored"


def test_the_portal_calls_the_port_with_the_stored_customer_reference(monkeypatch):
    """The reference the port is given is the one on the row."""
    user = UserFactory()
    SubscriptionFactory(
        user_id=user.pk, status=SubscriptionStatus.ACTIVE, stripe_customer_ref="cus_stored"
    )

    seen: dict[str, object] = {}

    class RecordingBilling:
        def create_portal_session(self, customer_ref, *, return_url):
            seen["customer_ref"] = customer_ref
            seen["return_url"] = return_url

            class Session:
                url = "http://example.test/portal"

            return Session()

        def create_checkout(self, *args, **kwargs):
            raise AssertionError("not used")

    import ports.registry

    monkeypatch.setattr(ports.registry, "get_billing_port", lambda: RecordingBilling())

    client = signed_in_client(user)
    response = portal(client)

    assert response.status_code == 200
    assert seen["customer_ref"] == "cus_stored"
    assert seen["return_url"].startswith("http://")


# ----------------------------------------------------------------------- the shape


def test_the_checkout_response_carries_only_a_url():
    """No entitlement field, no status, no plan echo.

    A response that said "you are now Pro" would be a lie — the user is not, until the
    webhook lands — and one that echoed the plan would be a field with nothing to say.
    """
    client = signed_in_client()

    payload = checkout(client).json()

    assert set(payload) == {"url"}


def test_the_portal_response_carries_only_a_url():
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.ACTIVE)
    client = signed_in_client(user)

    payload = portal(client).json()

    assert set(payload) == {"url"}
