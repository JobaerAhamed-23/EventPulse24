"""The billing read: `GET /api/billing/subscription` (FR-48).

This endpoint exists because the other two on the billing surface are **actions**. One
mints a checkout session, the other mints a portal session, so neither can answer "may
this person buy a plan?" without doing something to them — attempting a charge, or
creating a provider session every time somebody looked at a page. The read is therefore
a read.

**The property these tests exist to protect is that it stays a read.** It calls the one
published entitlement function and returns a bool. It mints nothing, calls no provider
and writes no row. That is asserted here rather than assumed, because "it happens to be
read-only today" is how a read quietly grows a side effect.

**The second property is that it is the *same* read.** The endpoint calls `is_pro`, the
function the save gate and the provider cap call. If the endpoint re-derived "is Pro"
from a status instead, a second mapping would exist, and `past_due` would become "not
Pro" in one call site and "Pro" in another — and the pricing page would then disagree
with the caps about the same person.

**The third is that it says nothing about anybody else.** There is no user id in the
request, and none in the response: the user comes from the session.
"""

import pytest
from django.test import Client

from apps.identity.models import Subscription, SubscriptionStatus
from apps.identity.services import is_pro
from shared.db import PERSONAL
from tests.identity.factories import SubscriptionFactory, UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

SUBSCRIPTION_URL = "/api/billing/subscription"


def signed_in_client(user=None) -> Client:
    """A client carrying a real session for `user` — Django's own, via `force_login`."""
    client = Client()
    client.force_login(user or UserFactory())
    return client


# ----------------------------------------------------------------------- the read


def test_a_free_user_reads_as_not_pro():
    """The ordinary case. Most users have no subscription, and that is not an error."""
    client = signed_in_client()

    response = client.get(SUBSCRIPTION_URL)

    assert response.status_code == 200
    assert response.json() == {"is_pro": False}


def test_a_pro_user_reads_as_pro():
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.ACTIVE)
    client = signed_in_client(user)

    response = client.get(SUBSCRIPTION_URL)

    assert response.status_code == 200
    assert response.json() == {"is_pro": True}


def test_a_past_due_user_reads_as_pro():
    """A payment that failed leaves the person entitled while they fix it.

    The place to fix it is the portal, so the pricing page should not offer them a
    second plan. This is `is_pro`'s mapping, and the endpoint inherits it rather than
    re-deriving it.
    """
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.PAST_DUE)
    client = signed_in_client(user)

    response = client.get(SUBSCRIPTION_URL)

    assert response.json() == {"is_pro": True}
    assert is_pro(user_id=user.pk) is True


def test_a_cancelled_subscription_reads_as_not_pro():
    """A cancelled row is history. The person may buy again, so the page must offer."""
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.CANCELED)
    client = signed_in_client(user)

    response = client.get(SUBSCRIPTION_URL)

    assert response.json() == {"is_pro": False}


def test_the_read_agrees_with_the_published_entitlement_read():
    """One mapping, not two.

    If the endpoint derived "is Pro" from a status of its own, this test would fail the
    moment the two mappings drifted — and the drift would be invisible, because both
    would still look right in isolation.
    """
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.ACTIVE)
    client = signed_in_client(user)

    response = client.get(SUBSCRIPTION_URL)

    assert response.json()["is_pro"] is is_pro(user_id=user.pk)


# ----------------------------------------------------------------------- the session


def test_an_anonymous_read_is_refused():
    """The read is about the *caller*, so there has to be a caller."""
    response = Client().get(SUBSCRIPTION_URL)

    assert response.status_code == 401


def test_a_read_answers_only_for_the_signed_in_user():
    """Two users, two answers — each sees their own.

    There is no user id in the request and none in the response, so there is no way to
    ask about somebody else.
    """
    pro = UserFactory()
    SubscriptionFactory(user_id=pro.pk, status=SubscriptionStatus.ACTIVE)
    free = UserFactory()

    pro_response = signed_in_client(pro).get(SUBSCRIPTION_URL)
    free_response = signed_in_client(free).get(SUBSCRIPTION_URL)

    assert pro_response.json() == {"is_pro": True}
    assert free_response.json() == {"is_pro": False}


# ----------------------------------------------------------------------- it stays a read


def test_the_read_calls_no_provider(monkeypatch):
    """The property that makes it a read.

    A read that minted a provider session would create real sessions for anyone who
    merely looked at the pricing page. So the provider is not called at all — the test
    fails loudly if it ever is.
    """
    import ports.registry

    class ExplodingBilling:
        def create_checkout(self, *args, **kwargs):
            raise AssertionError("the provider must not be called")

        def create_portal_session(self, *args, **kwargs):
            raise AssertionError("the provider must not be called")

    monkeypatch.setattr(ports.registry, "get_billing_port", lambda: ExplodingBilling())

    client = signed_in_client()

    response = client.get(SUBSCRIPTION_URL)

    assert response.status_code == 200


def test_the_read_writes_no_row():
    """Reading about a subscription does not write one."""
    user = UserFactory()
    client = signed_in_client(user)

    client.get(SUBSCRIPTION_URL)

    assert Subscription.objects.using(PERSONAL).filter(user_id=user.pk).count() == 0


def test_the_read_writes_no_audit_entry():
    """A read is not a state transition, so it is not an audit row (AD-5)."""
    from apps.identity.models import IdentityAuditEntry

    client = signed_in_client()

    client.get(SUBSCRIPTION_URL)

    assert (
        IdentityAuditEntry.objects.using(PERSONAL).filter(action__startswith="subscription").count()
        == 0
    )


# ----------------------------------------------------------------------- the shape


def test_the_response_carries_only_is_pro():
    """No plan, no renewal date, no status.

    The endpoint answers one question — *may this person buy a plan?* — and the fuller
    subscription record belongs to the account-and-billing surface. A field here would be
    a field two callers could disagree about.
    """
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.ACTIVE)
    client = signed_in_client(user)

    payload = client.get(SUBSCRIPTION_URL).json()

    assert set(payload) == {"is_pro"}
