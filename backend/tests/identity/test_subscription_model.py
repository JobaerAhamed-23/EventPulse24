"""The `Subscription` table's own integrity (AD-15, FR-48).

What the database holds is a constraint; what it cannot hold belongs to the commands. These
tests cover the first half: one live subscription per user, history allowed, a declared
retention category, and no way to delete a row.
"""

import pytest
from django.db import IntegrityError, transaction

from apps.identity.models import (
    LIVE_SUBSCRIPTION_STATUSES,
    Subscription,
    SubscriptionStatus,
)
from shared.db import PERSONAL
from shared.ids import uuid7
from shared.retention import RetentionCategory
from tests.identity.factories import SubscriptionFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


def test_the_retention_category_is_billing_records():
    """Seven years, for tax and legal reasons (PRD §10.2). The system checks
    `eventpulse.E003/E004` fail on any concrete model without a valid category, so this is
    enforced as well as asserted."""
    assert Subscription.retention_category is RetentionCategory.BILLING_RECORDS


@pytest.mark.parametrize("second_status", list(LIVE_SUBSCRIPTION_STATUSES))
def test_a_user_cannot_hold_two_live_subscriptions(second_status):
    """The partial unique index, in both of its live spellings.

    This is what makes two racing `checkout.session.completed` deliveries safe: the loser
    gets an `IntegrityError` rather than a second entitlement.
    """
    user_id = uuid7()
    SubscriptionFactory(user_id=user_id, status=SubscriptionStatus.ACTIVE)
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        SubscriptionFactory(user_id=user_id, status=second_status)


def test_a_cancelled_row_does_not_occupy_the_live_slot():
    """History is allowed. A user who cancels and resubscribes holds one live row and any
    number of terminal ones — which is the whole point of retaining them."""
    user_id = uuid7()
    SubscriptionFactory(user_id=user_id, status=SubscriptionStatus.CANCELED)
    SubscriptionFactory(user_id=user_id, status=SubscriptionStatus.EXPIRED)
    live = SubscriptionFactory(user_id=user_id, status=SubscriptionStatus.ACTIVE)

    assert Subscription.objects.using(PERSONAL).filter(user_id=user_id).count() == 3
    assert live.status == SubscriptionStatus.ACTIVE


def test_two_users_each_hold_their_own_live_subscription():
    """The constraint is per user, not global."""
    SubscriptionFactory(user_id=uuid7(), status=SubscriptionStatus.ACTIVE)
    SubscriptionFactory(user_id=uuid7(), status=SubscriptionStatus.ACTIVE)
    assert Subscription.objects.using(PERSONAL).count() == 2


def test_the_live_statuses_are_exactly_active_and_past_due():
    """Pinning the set, because `PRO_STATUSES` is defined as equal to it. If a fifth status
    is added, this test is where the author is asked whether it occupies the live slot."""
    assert LIVE_SUBSCRIPTION_STATUSES == (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE)


def test_no_app_code_deletes_a_subscription():
    """A lapse is a transition, never a delete: `BILLING_RECORDS` retention would be
    meaningless against a table anything could empty.

    This greps rather than exercises, because the absence of a delete path cannot be
    demonstrated by calling something.
    """
    import pathlib

    apps_root = pathlib.Path(__file__).resolve().parents[2] / "apps"
    offenders = [
        path
        for path in apps_root.rglob("*.py")
        if "Subscription" in (text := path.read_text())
        and (".delete()" in text or "bulk_delete" in text)
    ]
    assert offenders == [], f"a delete path reached Subscription in {offenders}"
