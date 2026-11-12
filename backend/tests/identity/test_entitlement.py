"""The one published read of entitlement (AD-2, FR-48).

`personalization` and `delivery` may not read `apps.identity.models` — the `models-identity`
contract fails the build if they try — so "is this user Pro?" is published as a function from
the app that owns the data, exactly as `get_recipient_address` is.

These tests pin the properties that make that safe to publish:

- **The mapping lives in one place.** A caller never sees a status, so `past_due` cannot
  quietly mean Pro in one call site and Free in another.
- **`past_due` grants Pro.** A failed charge starts Stripe's dunning; taking the product away
  at the first failure would run a second clock against Stripe's.
- **A missing row is Free, not an error.** Most users have no subscription.
- **It returns a bool, never a model.** A caller handed a `Subscription` could write to it.
"""

import pytest

from apps.identity.models import SubscriptionStatus
from apps.identity.services import is_pro
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.identity.factories import SubscriptionFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


def test_a_user_with_no_subscription_is_free():
    """The ordinary case. It is an answer, not an exception."""
    assert is_pro(user_id=uuid7()) is False


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (SubscriptionStatus.ACTIVE, True),
        (SubscriptionStatus.PAST_DUE, True),
        (SubscriptionStatus.CANCELED, False),
        (SubscriptionStatus.EXPIRED, False),
    ],
)
def test_each_status_maps_to_one_entitlement_answer(status, expected):
    """All four states, each pinned. `past_due` granting Pro is a decision, not an accident."""
    subscription = SubscriptionFactory(status=status)
    assert is_pro(user_id=subscription.user_id) is expected


def test_past_due_is_pro_so_a_failed_charge_does_not_cut_a_payer_off():
    """Named separately from the table above because it is the decision most likely to be
    reversed by someone who reads `past_due` as "not paying"."""
    subscription = SubscriptionFactory(status=SubscriptionStatus.PAST_DUE)
    assert is_pro(user_id=subscription.user_id) is True


def test_a_live_row_wins_over_the_users_own_cancelled_history():
    """A user who subscribed, cancelled and subscribed again is Pro.

    The terminal row stays — `BILLING_RECORDS` keeps it for seven years — so the read must
    not be fooled by its presence.
    """
    user_id = uuid7()
    SubscriptionFactory(user_id=user_id, status=SubscriptionStatus.CANCELED)
    SubscriptionFactory(user_id=user_id, status=SubscriptionStatus.ACTIVE)
    assert is_pro(user_id=user_id) is True


def test_only_cancelled_history_reads_as_free():
    """The mirror of the test above: history alone entitles nobody."""
    user_id = uuid7()
    SubscriptionFactory(user_id=user_id, status=SubscriptionStatus.CANCELED)
    SubscriptionFactory(user_id=user_id, status=SubscriptionStatus.EXPIRED)
    assert is_pro(user_id=user_id) is False


def test_one_users_subscription_does_not_entitle_another():
    SubscriptionFactory(status=SubscriptionStatus.ACTIVE)
    assert is_pro(user_id=uuid7()) is False


def test_the_read_returns_a_bool_and_never_a_model():
    """A refactor that leaked a `Subscription` would still be truthy, and every assertion
    above would still pass. This is the test that catches it."""
    subscription = SubscriptionFactory(status=SubscriptionStatus.ACTIVE)
    result = is_pro(user_id=subscription.user_id)
    assert type(result) is bool
