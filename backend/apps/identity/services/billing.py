"""The paid path's outbound side: starting a checkout, and opening the customer portal.

**This module grants nothing.** It mints a session and hands back a URL. It writes no
`Subscription` row, no audit entry, and no entitlement. That is the whole point of the
seam item 2 built: returning from a successful checkout changes nothing by itself, and
only the provider's webhook moves `Subscription` state. A user who completes checkout and
whose webhook is delayed, lost or replayed stays Free until the webhook lands — which is
the correct behaviour, because the alternative is granting entitlement on a redirect the
client controls.

**The URLs are derived, never transmitted.** `success_url` and `cancel_url` are built here,
from `settings.FRONTEND_BASE_URL` plus a configured path. The caller supplies **only the
plan**. This is the classic open-redirect in a checkout flow: a crafted `success_url` sends
a paying user to an attacker's page, and the session id rides along in the query string. So
there is no field anywhere in the request that names a URL, and there is no code path that
reads one from the request.

**Two refusals, and they are refusals of the account's state rather than of the request.**
A user who already holds a live subscription cannot start a second checkout, and a user
with no subscription cannot open the portal. Both are 409s. Both are decided *before* the
provider is called, so neither can surface as a provider error: the portal endpoint in
particular would otherwise be handing a provider a `customer_ref` that does not exist.

**The provider's vocabulary stops at the port.** This module imports `ports.billing` and
nothing else — no provider SDK, no provider error strings. `create_checkout` and
`create_portal_session` are the only outbound calls, and they return plain values.
"""

from uuid import UUID

from django.conf import settings

from apps.identity.models import LIVE_SUBSCRIPTION_STATUSES, Subscription
from apps.identity.services.entitlement import is_pro
from domain.errors import AlreadySubscribedError, NoSubscriptionError
from ports import registry
from ports.billing import BillingCustomer, ProPlan
from shared.db import PERSONAL


def _live_subscription(user_id: UUID) -> Subscription | None:
    """This user's live subscription row, or `None`.

    The same row the entitlement read consults, found by the same status set — so "is this
    user Pro" and "does this user hold a subscription" cannot disagree about what counts
    as live. A cancelled or expired row is not a live subscription: the user can buy again,
    and the portal for a cancelled subscription is not something this product offers.
    """
    return (
        Subscription.objects.using(PERSONAL)
        .filter(user_id=user_id, status__in=LIVE_SUBSCRIPTION_STATUSES)
        .first()
    )


def checkout_urls() -> tuple[str, str]:
    """The success and cancel URLs, built from configuration.

    Both are `FRONTEND_BASE_URL` plus one of the configured paths. The client supplies no
    part of either — see the module docstring for why that is not a stylistic choice.
    """
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return (
        f"{base}{settings.BILLING_SUCCESS_PATH}",
        f"{base}{settings.BILLING_CANCEL_PATH}",
    )


def portal_return_url() -> str:
    """Where the provider sends the user back to after they manage their subscription."""
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}{settings.BILLING_PORTAL_RETURN_PATH}"


def start_checkout(*, user_id: UUID, email: str, plan: ProPlan) -> str:
    """Mint a checkout session for this user and return the URL to send them to.

    **Nothing is granted here.** The returned URL leads to the provider, and the provider's
    webhook is what moves the subscription. A caller who completes checkout and whose
    webhook never lands stays Free, which is the honest answer.

    Raises:
        AlreadySubscribedError: The user already holds a live subscription. A second
            checkout would create a second subscription they would have to notice and
            cancel.
    """
    if _live_subscription(user_id) is not None:
        raise AlreadySubscribedError(
            details={"portal_path": settings.BILLING_PORTAL_RETURN_PATH},
        )

    success_url, cancel_url = checkout_urls()
    session = registry.get_billing_port().create_checkout(
        BillingCustomer(user_id=user_id, email=email),
        plan,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session.url


def open_portal(*, user_id: UUID) -> str:
    """Open the customer portal for this user and return the URL to send them to.

    The provider is called with the **stored** customer reference. It is not asked to look
    the customer up by email, and no reference is taken from the request — a caller must
    not be able to open another account's portal by naming one.

    Raises:
        NoSubscriptionError: The user holds no live subscription, so there is no customer
            reference to open a portal against. The refusal is plain and happens before
            the provider is called.
    """
    subscription = _live_subscription(user_id)
    if subscription is None:
        raise NoSubscriptionError()

    session = registry.get_billing_port().create_portal_session(
        subscription.stripe_customer_ref,
        return_url=portal_return_url(),
    )
    return session.url


def read_entitlement(*, user_id: UUID) -> bool:
    """Is this user Pro? The read, over the one published entitlement function.

    **It calls `is_pro` and nothing else.** The mapping from a subscription's status to
    "is this person entitled" lives in exactly one place — `services/entitlement.py` — and
    this function does not re-derive it. A second mapping is how `past_due` becomes "not
    Pro" in one call site and "Pro" in another, and the pricing page and the save gate
    would then disagree about the same user.

    **It is a read, and it stays a read.** No provider is called, no session is minted and
    no row is written. That matters here because the two obvious ways to answer "is this
    user Pro?" without a read — attempting a checkout, or opening a portal — both have
    side effects, and a page that probed them on load would mint real provider sessions
    for anyone who merely looked at it.

    **`past_due` counts as Pro**, because `is_pro` says so. A payment that failed leaves
    the person entitled while they fix it, and the place to fix it is the portal.
    """
    return is_pro(user_id=user_id)


__all__ = [
    "checkout_urls",
    "open_portal",
    "portal_return_url",
    "read_entitlement",
    "start_checkout",
]
