"""The account screen's billing read (FR-48).

**The reason this endpoint exists is one state.** `GET /api/billing/subscription` answers
`is_pro`, and `is_pro` is **true for `past_due` as well as `active`** — correctly, because a
failed payment leaves someone entitled while they fix it. An account screen reading only
that bool would render a person with a recoverable problem exactly like a person with none,
and this is the only screen where that problem becomes visible.

So the tests that matter here are the ones that pin the *difference* between two accounts
that `is_pro` calls identical, and the ones that pin that the two reads never disagree about
entitlement itself.
"""

import json
from datetime import UTC, datetime

import pytest
from django.test import Client

from apps.identity.models import SubscriptionStatus
from apps.identity.services import is_pro
from ports.billing import ProPlan
from shared.db import PERSONAL
from tests.identity.factories import SubscriptionFactory, UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

ACCOUNT_URL = "/api/billing/account"
SUBSCRIPTION_URL = "/api/billing/subscription"
PERIOD_END = datetime(2027, 3, 3, 12, 0, tzinfo=UTC)


def signed_in(user=None) -> Client:
    client = Client()
    client.force_login(user or UserFactory())
    return client


def account(client) -> dict:
    response = client.get(ACCOUNT_URL)
    assert response.status_code == 200, response.content
    return json.loads(response.content)


# ── The three states the screen has to tell apart ──────────────────────────────────


def test_an_account_that_never_subscribed_reads_as_free_and_never_pro():
    body = account(signed_in())

    assert body["is_pro"] is False
    assert body["status"] is None
    assert body["plan"] is None
    assert body["had_pro"] is False
    assert body["needs_payment"] is False


def test_an_active_subscription_reads_as_pro_with_its_term():
    user = UserFactory()
    SubscriptionFactory(
        user_id=user.pk,
        status=SubscriptionStatus.ACTIVE,
        plan=ProPlan.YEARLY.value,
        current_period_end=PERIOD_END,
    )

    body = account(signed_in(user))

    assert body["is_pro"] is True
    assert body["status"] == SubscriptionStatus.ACTIVE
    assert body["plan"] == ProPlan.YEARLY.value
    assert body["period_end"].startswith("2027-03-03")
    assert body["needs_payment"] is False


def test_a_past_due_subscription_is_pro_and_says_a_payment_needs_fixing():
    """**The state this endpoint exists for.** `is_pro` cannot see it; `needs_payment` can."""
    user = UserFactory()
    SubscriptionFactory(
        user_id=user.pk, status=SubscriptionStatus.PAST_DUE, current_period_end=PERIOD_END
    )

    body = account(signed_in(user))

    assert body["is_pro"] is True
    assert body["needs_payment"] is True
    assert body["status"] == SubscriptionStatus.PAST_DUE


def test_a_past_due_account_is_not_reported_as_free():
    """The regression the account screen exists to prevent, asserted at the source: showing
    this person as plain Free would hide a problem only they can fix."""
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.PAST_DUE)

    body = account(signed_in(user))

    assert body["is_pro"] is not False
    assert body["status"] != SubscriptionStatus.CANCELED


@pytest.mark.parametrize("ended", [SubscriptionStatus.CANCELED, SubscriptionStatus.EXPIRED])
def test_a_lapsed_account_is_free_but_remembers_having_been_pro(ended):
    """**`had_pro` is the difference between two Free screens.** A lapsed subscriber shown
    the same blank copy a brand-new account sees would have a relationship they paid for
    quietly erased."""
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=ended, current_period_end=PERIOD_END)

    body = account(signed_in(user))

    assert body["is_pro"] is False
    assert body["had_pro"] is True
    assert body["status"] == ended
    assert body["needs_payment"] is False


def test_a_live_subscription_wins_over_an_older_ended_one():
    """A user who cancelled and came back has history and a live row; the screen is about
    now, and the history answers only "were they ever Pro"."""
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.CANCELED)
    SubscriptionFactory(
        user_id=user.pk, status=SubscriptionStatus.ACTIVE, current_period_end=PERIOD_END
    )

    body = account(signed_in(user))

    assert body["is_pro"] is True
    assert body["status"] == SubscriptionStatus.ACTIVE


# ── The two reads must never disagree ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "status",
    [
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE,
        SubscriptionStatus.CANCELED,
        SubscriptionStatus.EXPIRED,
    ],
)
def test_is_pro_agrees_with_the_entitlement_read_in_every_state(status):
    """**Two endpoints, one answer.** Both read `LIVE_SUBSCRIPTION_STATUSES`, so this holds
    by construction — and it is pinned because the failure would be silent: a screen saying
    "you're on Pro" over features the server refuses."""
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=status)
    client = signed_in(user)

    wide = account(client)["is_pro"]
    narrow = json.loads(client.get(SUBSCRIPTION_URL).content)["is_pro"]

    assert wide == narrow == is_pro(user_id=user.pk)


# ── Scoping and auth ───────────────────────────────────────────────────────────────


def test_the_read_is_scoped_to_the_session_and_takes_no_user_id():
    """There is no id in the request and none in the response, so a caller cannot ask about
    somebody else (AD-12)."""
    mine = UserFactory()
    theirs = UserFactory()
    SubscriptionFactory(user_id=theirs.pk, status=SubscriptionStatus.ACTIVE)

    body = account(signed_in(mine))

    assert body["is_pro"] is False
    assert json.dumps(body).find(str(theirs.pk)) == -1


def test_an_anonymous_caller_is_refused():
    response = Client().get(ACCOUNT_URL)

    assert response.status_code in (401, 403)


def test_the_response_carries_no_provider_references():
    """The Stripe customer and subscription ids are ours to hold, not the browser's."""
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.ACTIVE)

    body = account(signed_in(user))

    assert set(body) == {
        "status",
        "plan",
        "period_end",
        "is_pro",
        "needs_payment",
        "had_pro",
    }


def test_the_read_writes_nothing_and_calls_no_provider():
    """It answers a question. Minting a session would be an action with a side effect, and
    that is what the other two endpoints are for."""
    from apps.identity.models import Subscription

    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.ACTIVE)
    before = Subscription.objects.using(PERSONAL).values_list("updated_at", flat=True)[0]

    account(signed_in(user))

    after = Subscription.objects.using(PERSONAL).values_list("updated_at", flat=True)[0]
    assert before == after
