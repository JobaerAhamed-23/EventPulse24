"""The paid path's HTTP surface (FR-48): start a checkout, open the customer portal.

Two endpoints hand back a URL and nothing else, and a third reads the caller's tier.

- `POST /api/billing/checkout` — mint a checkout session for the signed-in user.
- `POST /api/billing/portal` — open the customer portal for the signed-in user.
- `GET /api/billing/subscription` — read whether the signed-in user is Pro.

**The third endpoint exists because the first two cannot answer the question.** Both are
actions with side effects: one mints a checkout session, the other mints a portal session.
So neither can be used to find out whether a user is Pro without doing something to them
— attempting a charge, or creating a provider session every time somebody looked at a
page. The read is therefore a read: it calls the one published entitlement function and
returns a bool.

**The auth is on the router**, as `personalization`'s and `delivery`'s are
(`auth=current_user`). The user id therefore comes from the session and **never from a
payload** — there is no field on either request body that names a user, so the scoping
cannot be talked out of.

**Neither endpoint grants entitlement.** This is the property worth stating plainly, and
it is easy to lose: a checkout that completes changes nothing here. The `Subscription` row
is written by the webhook receiver, from the provider's signed event. So a user who pays
and whose webhook is delayed, lost or replayed stays Free until the webhook lands — and
that is correct, because the alternative is granting entitlement on a redirect the client
controls. Neither endpoint writes a row, and neither writes an audit entry.

**The redirect URLs are derived from configuration and cannot be supplied by the client.**
The request body carries only the plan. `success_url` and `cancel_url` are built from
`settings.FRONTEND_BASE_URL` plus a configured path, so a client that asks for a checkout
with a `success_url` of its own simply gets a session whose URLs point at this host.
Taking the redirect target from the request is the classic open-redirect in a checkout
flow: it sends a paying user — and the session id in the query string — to somebody else's
site.

**Two refusals, and both are about the account's state rather than the request's shape.**
A user who already holds a live subscription cannot start a second checkout (409, pointing
at the portal), and a user with no subscription cannot open the portal (409, saying so in
plain words). Both are decided before the provider is called, so neither can surface
as a provider error — a portal request for a customer that does not exist would otherwise
be the provider's error to explain, and it is ours to explain instead.
"""

from ninja import Router

from apps.identity.api_auth import current_user
from apps.identity.schemas import CheckoutIn, CheckoutOut, PortalOut, SubscriptionOut
from apps.identity.services import open_portal, read_entitlement, start_checkout
from shared.errors import ErrorOut

router = Router(tags=["billing"], auth=current_user)


@router.post(
    "/checkout",
    response={200: CheckoutOut, 401: ErrorOut, 403: ErrorOut, 409: ErrorOut, 422: ErrorOut},
    summary="Start a Pro checkout",
    description=(
        "Mints a checkout session for the chosen plan and returns the URL to send the "
        "user to.\n\n"
        "**The body carries the plan and nothing else.** The success and cancel URLs are "
        "built from this deployment's configuration, so a client cannot name them.\n\n"
        "**Paying does not make you Pro yet.** The provider's webhook is what records the "
        "subscription; this endpoint writes nothing. If the webhook has not landed, the "
        "user is still on the free tier — which is why the response carries no "
        "entitlement field.\n\n"
        "**A user who already has a live subscription is refused** with 409, and the "
        "response points at the portal: that is where an existing subscription is "
        "managed. Starting a second checkout would create a second subscription to notice "
        "and cancel."
    ),
)
def post_checkout(request, body: CheckoutIn):
    """Mint a checkout session. Grants nothing."""
    url = start_checkout(
        user_id=request.user.pk,
        email=request.user.email,
        plan=body.plan,
    )
    return CheckoutOut(url=url)


@router.post(
    "/portal",
    response={200: PortalOut, 401: ErrorOut, 403: ErrorOut, 409: ErrorOut},
    summary="Open the customer portal",
    description=(
        "Opens the provider's customer portal for the signed-in user, where they manage "
        "their plan, their card and their cancellation, and returns the URL to send them "
        "to.\n\n"
        "**The provider is called with the stored customer reference.** No reference is "
        "taken from the request, so a caller cannot open another account's portal by "
        "naming one.\n\n"
        "**A user with no subscription is refused** with 409 — there is no customer to "
        "open a portal against, and the answer says so plainly rather than letting the "
        "provider explain a customer that does not exist."
    ),
)
def post_portal(request):
    """Open the customer portal for the signed-in user."""
    url = open_portal(user_id=request.user.pk)
    return PortalOut(url=url)


@router.get(
    "/subscription",
    response={200: SubscriptionOut, 401: ErrorOut, 403: ErrorOut},
    summary="Read the caller's entitlement",
    description=(
        "Reads whether the signed-in user is entitled to Pro, and returns a single "
        "boolean.\n\n"
        "**This is the only read on the billing surface.** The other two endpoints are "
        "actions — they mint a checkout session and they mint a portal session — so "
        "neither can answer 'may this person buy a plan?' without a side effect. This one "
        "is read-only: no provider is called, no session is minted and nothing is "
        "written.\n\n"
        "**The user comes from the session.** There is no id in the request and none in "
        "the response, so a caller cannot ask about somebody else's subscription.\n\n"
        "**It carries a bool and nothing else.** No plan, no renewal date, no status: the "
        "answer to this question is one bit, and the fuller record belongs to the "
        "account-and-billing surface.\n\n"
        "**`past_due` reads as Pro.** A payment that failed leaves the person entitled "
        "while they fix it, and the portal is where they fix it."
    ),
)
def get_subscription(request):
    """Read the caller's entitlement. Reads nothing else, writes nothing."""
    return SubscriptionOut(is_pro=read_entitlement(user_id=request.user.pk))


__all__ = ["router"]
