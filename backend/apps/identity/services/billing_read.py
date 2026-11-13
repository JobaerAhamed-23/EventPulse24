"""The account screen's view of a subscription (FR-48).

**Why this exists next to `entitlement.is_pro` rather than inside it.** `is_pro` answers one
bit — *may this person use Pro features* — and `SubscriptionOut`'s docstring is emphatic
that it stays one bit, because *"a field here would be a field two callers could disagree
about"*. The account screen asks a different question: *what is the state of this person's
plan, and what can they do about it*. The same docstring already said where that lives:
*"the fuller subscription record belongs to the account-and-billing surface, which needs a
wider read and builds it there."* This is there.

**The difference is `past_due`, and it is the whole reason for a second read.** `is_pro` is
true for `ACTIVE` and `PAST_DUE` alike — correctly, because a person whose card failed is
still entitled while they fix it. But an account screen that could only see the bit would
render those two people identically, and one of them has a recoverable problem they can only
discover here. `SubscriptionStatus`' own docstring says so: *"`PAST_DUE` is distinct from
`CANCELED` because a user must be able to see it."*

**It reads; it never writes and never calls the provider.** Opening the portal is an action
with a side effect and lives in `billing.open_portal`. This answers a question.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.identity.models import LIVE_SUBSCRIPTION_STATUSES, Subscription, SubscriptionStatus
from shared.db import PERSONAL


@dataclass(frozen=True)
class BillingAccount:
    """One account's plan, as the settings screen needs it.

    A frozen dataclass and never a model instance: a caller holding the row could write it,
    and the webhook-driven commands are the only writers.

    **`period_end` is deliberately not called `renews_at`.** This product does not model
    `cancel_at_period_end` — not in `ports.billing`, not in either adapter, not on the row —
    so a subscription the user cancelled in the provider's portal still reads `ACTIVE` until
    its term runs out, and nothing here can tell the two apart. The field is named for what
    it is: when the current term ends. Calling it a renewal would make every reader who
    trusted the name state something false to the one person most likely to be reading the
    screen — somebody who just cancelled and came to check it worked.
    """

    #: `None` when the account has never subscribed.
    status: str | None
    #: `None` when the account has never subscribed.
    plan: str | None
    #: The end of the current term, when one is known.
    period_end: datetime | None
    #: Whether Pro features are available right now. Matches `entitlement.is_pro` by
    #: construction — both read `LIVE_SUBSCRIPTION_STATUSES` — so the two cannot disagree.
    is_pro: bool
    #: Whether a payment failed and is waiting to be fixed. The state this read exists for.
    needs_payment: bool
    #: Whether this account once had Pro and no longer does.
    had_pro: bool


def read_billing_account(*, user_id: UUID) -> BillingAccount:
    """This user's plan state for the account screen.

    **The live row wins; history is only consulted when there is none.** A user accumulates
    `CANCELED` and `EXPIRED` rows — seven years of them, by `BILLING_RECORDS` — and the
    screen is about now. So the live subscription is read first, and the history answers
    exactly one further question: *was this person ever Pro*, which decides whether the Free
    state reads as "you're on the free plan" or as "your Pro plan ended".

    **`had_pro` is the gentler of two possible lies.** Showing a lapsed subscriber the same
    blank "free plan" copy a brand-new account sees would quietly erase a relationship they
    paid for; showing a never-subscriber a past-tense message would be wrong about a plan
    they never had.
    """
    live = (
        Subscription.objects.using(PERSONAL)
        .filter(user_id=user_id, status__in=LIVE_SUBSCRIPTION_STATUSES)
        .order_by("-created_at")
        .first()
    )
    if live is not None:
        return BillingAccount(
            status=live.status,
            plan=live.plan,
            period_end=live.current_period_end,
            is_pro=True,
            needs_payment=live.status == SubscriptionStatus.PAST_DUE,
            had_pro=True,
        )

    ended = (
        Subscription.objects.using(PERSONAL).filter(user_id=user_id).order_by("-created_at").first()
    )
    if ended is None:
        return BillingAccount(
            status=None,
            plan=None,
            period_end=None,
            is_pro=False,
            needs_payment=False,
            had_pro=False,
        )

    return BillingAccount(
        status=ended.status,
        plan=ended.plan,
        period_end=ended.current_period_end,
        is_pro=False,
        needs_payment=False,
        had_pro=True,
    )


@dataclass(frozen=True)
class LiveSubscriptionRefs:
    """The provider's references for a user's live subscription.

    **Why these are readable at all.** A cancellation arrives as a provider event that
    names the *subscription*, not the user — `BillingEvent`'s docstring says so: *"Every
    later event names the subscription and not the user, which is why the change and end
    commands look a subscription up by reference."* So anything that has to cancel a
    subscription needs its reference, and a reference nobody can read is a reference only
    the webhook can use.

    **The live row, not the newest row.** `record_subscription_ended` looks a subscription
    up by reference alone, so the reference has to name the *live* one. A user who has
    subscribed, cancelled and subscribed again holds a cancelled row and a live one; the
    cancelled row's reference would cancel nothing and leave the user Pro.

    **`None` when there is no live subscription.** That is the ordinary case, and it is
    what a caller needs to know: there is nothing to cancel.
    """

    #: The provider's customer reference.
    customer_ref: str
    #: The provider's subscription reference. `None` when the row carries none.
    subscription_ref: str | None


def read_live_subscription_refs(*, user_id: UUID) -> LiveSubscriptionRefs | None:
    """This user's live subscription's provider references, or `None` if there is none.

    **It returns the live row's refs and nothing else.** No status, no plan, no dates: the
    only question it answers is "which subscription reference names the subscription this
    user currently holds", and a caller handed more could start mapping states it has no
    business mapping.

    **It reads the live row first**, by the same `LIVE_SUBSCRIPTION_STATUSES` the
    entitlement read uses — so "live" means one thing across the app. Ordered by
    `created_at` descending, so a user with more than one live row (which the partial
    unique constraint should prevent, but a restored backup might not) gets the newest.
    """
    live = (
        Subscription.objects.using(PERSONAL)
        .filter(user_id=user_id, status__in=LIVE_SUBSCRIPTION_STATUSES)
        .order_by("-created_at")
        .first()
    )
    if live is None:
        return None
    return LiveSubscriptionRefs(
        customer_ref=live.stripe_customer_ref,
        subscription_ref=live.stripe_subscription_ref,
    )


__all__ = [
    "BillingAccount",
    "LiveSubscriptionRefs",
    "read_billing_account",
    "read_live_subscription_refs",
]
