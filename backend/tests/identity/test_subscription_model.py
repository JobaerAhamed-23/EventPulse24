"""The `Subscription` table's own integrity (AD-15, FR-48).

What the database holds is a constraint; what it cannot hold belongs to the commands. These
tests cover the first half: one live subscription per user, history allowed, a declared
retention category, and no way to delete a row.
"""

import pathlib
import tokenize
from io import StringIO

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


def _code_only(text: str) -> str:
    """One module's source with its docstrings and comments removed.

    **The guard below is about what the code does, not what it says.** A file that deletes
    its own unrelated rows and separately *explains* in prose that a lapse never deletes a
    subscription is the opposite of an offender, and the scan must not read it as one —
    which it did, for `delivery`'s quiet-hours overrides.

    Dropping every `STRING` token, not just docstrings, is deliberate: a string literal is
    data, and the one way it could name this table in earnest — a `getattr` by name — is
    not a delete path either.

    **The prose is blanked in place rather than removed**, so every other character keeps
    its line and column. Joining the surviving tokens instead would split `qs.delete()`
    across four lines and the scan below would find neither `Subscription` nor `.delete()`
    adjacent to anything — a guard that passes against a file that really does delete the
    table. That is not hypothetical: it is what the first version of this helper did, and a
    probe module was what caught it.
    """
    lines = text.splitlines(keepends=True)
    for token in tokenize.generate_tokens(StringIO(text).readline):
        if token.type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        (start_row, start_col), (end_row, end_col) = token.start, token.end
        for row in range(start_row, end_row + 1):
            line = lines[row - 1]
            begin = start_col if row == start_row else 0
            finish = end_col if row == end_row else len(line.rstrip("\n"))
            lines[row - 1] = line[:begin] + " " * (finish - begin) + line[finish:]
    return "".join(lines)


def test_no_app_code_deletes_a_subscription():
    """A lapse is a transition, never a delete: `BILLING_RECORDS` retention would be
    meaningless against a table anything could empty.

    This greps rather than exercises, because the absence of a delete path cannot be
    demonstrated by calling something. It greps the **code** (see `_code_only`), and stays
    file-wide rather than following the call: a queryset parked in a variable and deleted
    two lines later is exactly the shape this is here to catch.
    """
    apps_root = pathlib.Path(__file__).resolve().parents[2] / "apps"
    offenders = [
        path
        for path in apps_root.rglob("*.py")
        if "Subscription" in (code := _code_only(path.read_text()))
        and (".delete()" in code or "bulk_delete" in code)
    ]
    assert offenders == [], f"a delete path reached Subscription in {offenders}"
