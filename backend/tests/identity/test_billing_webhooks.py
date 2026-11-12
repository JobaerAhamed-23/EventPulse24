"""The inbound billing webhook (FR-48).

Tested entirely through `FakeBillingAdapter`, with **no SDK and no network**. That is the
payoff of putting signature verification behind the port: everything above the adapter —
dispatch, the 200/400 discipline, ordering, attribution — is exercised without Stripe
existing at all. The real signature check belongs to the real adapter and is tested there.

The property these tests exist to protect is narrow and easy to lose: **almost everything
answers 200**. An unhandled type, an unknown subscription and a replayed or out-of-order
delivery are all routine and all change nothing. Answering anything else makes the provider
retry forever for something working as designed.
"""

import json
from datetime import UTC, datetime

import pytest

from adapters.billing.fake import FAKE_SIGNATURE
from apps.identity.models import Subscription, SubscriptionStatus
from apps.identity.services import is_pro
from ports.billing import BillingEventKind, ProPlan
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.identity.factories import SubscriptionFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

URL = "/api/webhooks/billing"
T0 = int(datetime(2026, 11, 11, 12, 0, tzinfo=UTC).timestamp())
T1 = int(datetime(2026, 11, 11, 12, 5, tzinfo=UTC).timestamp())
T2 = int(datetime(2026, 11, 11, 12, 10, tzinfo=UTC).timestamp())


def _post(client, body: dict, *, signature: str = FAKE_SIGNATURE):
    return client.post(
        URL,
        data=json.dumps(body),
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=signature,
    )


def _started(user_id, *, ref="sub_1", at=T0):
    return {
        "kind": BillingEventKind.SUBSCRIPTION_STARTED.value,
        "event_id": "evt_1",
        "occurred_at": at,
        "customer_ref": "cus_1",
        "subscription_ref": ref,
        "user_id": str(user_id),
        "plan": ProPlan.MONTHLY.value,
    }


# ----------------------------------------------------------------------- signature


def test_an_unverifiable_payload_is_refused_and_changes_nothing(client):
    user_id = uuid7()
    response = _post(client, _started(user_id), signature="not-the-signature")

    assert response.status_code == 400
    assert is_pro(user_id=user_id) is False
    assert Subscription.objects.using(PERSONAL).count() == 0


def test_the_refusal_explains_nothing(client):
    """A caller that cannot sign is told that it failed, never which check or why."""
    response = _post(client, _started(uuid7()), signature="wrong")
    body = response.json()
    # The fixed 400 body from `config/errors.py`. It does not say that a *signature* failed:
    # `HTTP_ERRORS` exists precisely so a framework error's own text is never shown.
    assert body["code"] == "bad_request"
    assert "signature" not in str(body).lower()


def test_a_missing_signature_header_is_refused(client):
    user_id = uuid7()
    response = client.post(URL, data=json.dumps(_started(user_id)), content_type="application/json")
    assert response.status_code == 400
    assert is_pro(user_id=user_id) is False


# ----------------------------------------------------------------------- the four kinds


def test_a_completed_checkout_grants_pro(client):
    user_id = uuid7()
    response = _post(client, _started(user_id))

    assert response.status_code == 200
    assert response.json()["status"] == "started"
    assert is_pro(user_id=user_id) is True


def test_a_cancellation_ends_entitlement(client):
    user_id = uuid7()
    _post(client, _started(user_id))

    response = _post(
        client,
        {
            "kind": BillingEventKind.SUBSCRIPTION_ENDED.value,
            "event_id": "evt_2",
            "occurred_at": T1,
            "subscription_ref": "sub_1",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ended"
    assert is_pro(user_id=user_id) is False


def test_a_payment_failure_records_past_due_and_keeps_pro(client):
    """Stripe's dunning is still running. The user keeps what they paid for, and the account
    screen is where they find out."""
    user_id = uuid7()
    _post(client, _started(user_id))

    response = _post(
        client,
        {
            "kind": BillingEventKind.PAYMENT_FAILED.value,
            "event_id": "evt_3",
            "occurred_at": T1,
            "subscription_ref": "sub_1",
        },
    )

    assert response.json()["status"] == "payment_failed"
    assert is_pro(user_id=user_id) is True
    assert (
        Subscription.objects.using(PERSONAL).get(stripe_subscription_ref="sub_1").status
        == SubscriptionStatus.PAST_DUE
    )


def test_a_change_event_applies_the_mapped_status(client):
    user_id = uuid7()
    _post(client, _started(user_id))

    _post(
        client,
        {
            "kind": BillingEventKind.SUBSCRIPTION_CHANGED.value,
            "event_id": "evt_4",
            "occurred_at": T1,
            "subscription_ref": "sub_1",
            "status": SubscriptionStatus.CANCELED.value,
            "raw_status": "canceled",
        },
    )

    assert is_pro(user_id=user_id) is False


def test_the_receiver_reads_the_mapped_status_not_the_providers_own(client):
    """`status` is ours; `raw_status` is the provider's and is for logging only. A receiver
    that read the wrong field would act on an uninterpreted provider string."""
    user_id = uuid7()
    _post(client, _started(user_id))

    _post(
        client,
        {
            "kind": BillingEventKind.SUBSCRIPTION_CHANGED.value,
            "event_id": "evt_5",
            "occurred_at": T1,
            "subscription_ref": "sub_1",
            "status": SubscriptionStatus.CANCELED.value,
            # A provider string that is not one of ours. Reading this field would raise or
            # fall back; reading `status` cancels correctly.
            "raw_status": "unpaid",
        },
    )

    assert is_pro(user_id=user_id) is False


# ----------------------------------------------------------------------- routine non-events


def test_an_unhandled_event_type_is_acknowledged(client):
    response = _post(
        client,
        {"kind": BillingEventKind.IGNORED.value, "event_id": "evt_x", "occurred_at": T0},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_an_event_for_an_unknown_subscription_is_acknowledged(client):
    response = _post(
        client,
        {
            "kind": BillingEventKind.SUBSCRIPTION_ENDED.value,
            "event_id": "evt_y",
            "occurred_at": T0,
            "subscription_ref": "sub_never_seen",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "no_change"


def test_a_replayed_checkout_is_acknowledged_and_grants_once(client):
    user_id = uuid7()
    first = _post(client, _started(user_id))
    second = _post(client, _started(user_id, ref="sub_1", at=T1))

    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json()["status"] == "no_change"
    assert Subscription.objects.using(PERSONAL).filter(user_id=user_id).count() == 1


def test_a_stale_change_after_a_cancellation_does_not_restore_entitlement(client):
    """The ordering guard, asserted end-to-end rather than only at the command level."""
    user_id = uuid7()
    _post(client, _started(user_id, at=T0))
    _post(
        client,
        {
            "kind": BillingEventKind.SUBSCRIPTION_ENDED.value,
            "event_id": "evt_end",
            "occurred_at": T2,
            "subscription_ref": "sub_1",
        },
    )

    late = _post(
        client,
        {
            "kind": BillingEventKind.SUBSCRIPTION_CHANGED.value,
            "event_id": "evt_late",
            "occurred_at": T1,
            "subscription_ref": "sub_1",
            "status": SubscriptionStatus.ACTIVE.value,
        },
    )

    assert late.status_code == 200
    assert late.json()["status"] == "no_change"
    assert is_pro(user_id=user_id) is False


# ----------------------------------------------------------------------- attribution


def test_a_completed_checkout_with_no_user_is_not_silently_discarded(client):
    """The session was created without the metadata `checkout-and-portal-api` must set, so a
    user has been charged and cannot be made Pro. It answers 200 — retrying will not add the
    metadata — but names the outcome so the log says what happened."""
    body = _started(uuid7())
    del body["user_id"]

    response = _post(client, body)

    assert response.status_code == 200
    assert response.json()["status"] == "unattributable"
    assert Subscription.objects.using(PERSONAL).count() == 0


def test_a_webhook_cannot_make_another_users_subscription(client):
    """Entitlement follows the id in the verified payload and nothing else."""
    other = SubscriptionFactory(status=SubscriptionStatus.ACTIVE)
    user_id = uuid7()
    _post(client, _started(user_id, ref="sub_other"))

    assert is_pro(user_id=user_id) is True
    assert Subscription.objects.using(PERSONAL).filter(user_id=other.user_id).count() == 1
