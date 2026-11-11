"""The one published read of what a user is entitled to (AD-2, FR-48).

**Why this module exists.** Four features and two caps need to know whether a user is Pro,
and they live in `personalization` and `delivery`. Those apps may not read
`apps.identity.models`: the `models-identity` import-linter contract says *"only
`apps.identity` imports `apps.identity.models` (others call its services)"*, and it fails the
build rather than a review. So the read lives here, in the app that owns the data, published
as a function — the same seam `services/recipients.py` opens for a user's address.

**This is not an AD-3 wall crossing, and it is worth saying so.** `settings.DATABASE_ROUTING`
places `identity`, `personalization` and `delivery` all in the `PERSONAL` alias, and
`shared/db.py` explains why: *"`default` is the personal schema because Django requires a
`default` alias and the user table must share an alias with the personal data that references
it."* AD-3's wall runs between `catalog` and `personal`. A caller here is one indexed lookup
away in the same database, which is why this read is direct and uncached — exactly as
`get_recipient_address` is, on a path that sends real mail.

**It returns a bool and nothing else.** Not the subscription, not the status, not a model. A
caller handed a `Subscription` could write to it, and `identity` is the only writer of that
table. More importantly, a caller handed the *status* would start mapping it — and a second
mapping is how `past_due` quietly becomes "not Pro" in one call site and "Pro" in another.
The mapping lives here, once.

**`past_due` is Pro.** A failed payment starts Stripe's dunning, and the subscription stays
`past_due` until Stripe gives up and cancels it. Cutting entitlement at the first failed
charge would mean running a second clock against Stripe's, and taking a product people pay
for away from someone whose card expired — which is neither calm nor correct. The account
screen shows them the problem; the gates stay open while they fix it.

**A missing row is Free, never an error.** Most users have no subscription. "No row" is the
ordinary case, not an exceptional one, so this function is total.

**`is_active` is deliberately not consulted, unlike `recipients.py`.** That module filters
deactivated accounts because mailing a closed account is wrong — the send is aimed *at* the
person. Entitlement is only ever asked about a user who is making a request, and a
deactivated account has no session to make one with: authentication has already closed that
door. Checking it here would imply a gate that does not exist, and would leave the reader
wondering which of the two modules is wrong.
"""

from uuid import UUID

from apps.identity.models import LIVE_SUBSCRIPTION_STATUSES, Subscription
from shared.db import PERSONAL

#: The statuses that grant Pro. Kept beside the read that uses it so the mapping has exactly
#: one home; `LIVE_SUBSCRIPTION_STATUSES` is the same set because the two questions — "does
#: this row occupy the user's live slot?" and "does this row grant Pro?" — have the same
#: answer today. They are named separately because they are different questions: a future
#: state that occupies the slot without granting Pro (a paused subscription, say) would split
#: them, and a single shared constant would hide that.
PRO_STATUSES = LIVE_SUBSCRIPTION_STATUSES


def is_pro(*, user_id: UUID) -> bool:
    """Is this user entitled to Pro features? `False` when there is no subscription at all.

    A read, never a write. See the module docstring for why `past_due` counts as Pro and why
    `is_active` is not consulted.
    """
    return (
        Subscription.objects.using(PERSONAL)
        .filter(user_id=user_id, status__in=PRO_STATUSES)
        .exists()
    )


__all__ = ["PRO_STATUSES", "is_pro"]
