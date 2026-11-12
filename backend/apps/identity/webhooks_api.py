"""The inbound billing webhook (FR-48): where subscription state gets back in.

**This endpoint has no `auth=` and no CSRF, and that is deliberate.** The caller is a payment
provider, not a browser: it carries no session cookie and no CSRF token, and a signature
header is what proves the request is genuine. Django Ninja already exempts the views it builds
from Django's CSRF middleware, so nothing has to be added back — but the absence is recorded
here so it reads as a decision rather than an omission.

**It contains no provider vocabulary and imports no SDK.** The `stripe-sdk` contract lists
`apps` as a forbidden source, so this module *could not* verify a signature even if it wanted
to. It hands the raw body to the billing port and matches on `BillingEventKind`, which is this
product's own enum. Swapping providers would not touch this file.

**The raw body is passed through unparsed.** Verification is over the exact bytes a provider
signed; letting a JSON parser normalise them first would break verification and invite a
bypass.

**Almost everything answers 200.** An unhandled event type, an event for a subscription we
have never seen, and a replayed or out-of-order delivery are all *routine* and all change
nothing. Answering anything else would make the provider retry forever for something working
as designed. A payload that does not verify is the single exception: it is not a delivery at
all, and it is answered 400 with a body that explains nothing.
"""

import logging

from django.http import HttpRequest
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.identity.models import SubscriptionStatus
from apps.identity.services import (
    record_subscription_changed,
    record_subscription_ended,
    record_subscription_started,
)
from apps.identity.services.subscriptions import STRIPE_WEBHOOK_ACTOR_LABEL
from ports.billing import BillingEvent, BillingEventKind, InvalidWebhookSignature, ProPlan
from ports.registry import get_billing_port
from shared.actor import Actor, ActorKind
from shared.errors import ErrorOut

logger = logging.getLogger(__name__)

router = Router(tags=["billing-webhooks"])


class WebhookAck(Schema):
    """What the provider gets back. A slug naming the outcome, and nothing else.

    No subscription id, no user id, no plan: a webhook response is read by a provider and by
    whoever can replay a delivery, and it has no reason to carry anything about the account.
    """

    status: str


#: The header a provider signs its payload with.
SIGNATURE_HEADER = "HTTP_STRIPE_SIGNATURE"

#: Every transition this endpoint causes is attributed to the webhook, not to a person.
WEBHOOK_ACTOR = Actor(kind=ActorKind.SYSTEM, label=STRIPE_WEBHOOK_ACTOR_LABEL)

#: The plan assumed when a provider's completed-checkout event does not name one. Monthly is
#: the conservative choice: it is the shorter commitment, so an attribution error cannot
#: silently grant a year.
DEFAULT_PLAN = ProPlan.MONTHLY


@router.post(
    "",
    auth=None,
    url_name="billing_webhook",
    response={200: WebhookAck, 400: ErrorOut},
)
def receive_billing_event(request: HttpRequest):
    """Verify, translate and apply one inbound billing event."""
    signature = request.META.get(SIGNATURE_HEADER, "")
    try:
        event = get_billing_port().parse_event(request.body, signature=signature)
    except InvalidWebhookSignature:
        # No detail in the response: a caller that cannot sign does not get told why.
        logger.warning("billing webhook rejected", extra={"outcome": "signature_invalid"})
        # `HttpError`'s own text is deliberately not shown: `config/errors.py` maps 400
        # to a fixed, calm "That request couldn't be read." So the response does not
        # reveal that *signature verification* is what failed — one fewer thing a prober
        # learns than a bespoke `invalid_signature` code would have told them.
        # `from None`: the provider's own verification message is deliberately dropped
        # rather than chained, so nothing about why the check failed can reach a traceback
        # or an error reporter.
        raise HttpError(400, "signature did not verify") from None

    outcome = _apply(event)
    logger.info(
        "billing webhook handled",
        extra={"outcome": outcome, "kind": event.kind.value},
    )
    return WebhookAck(status=outcome)


def _apply(event: BillingEvent) -> str:
    """Dispatch one verified event. Returns a slug naming what happened, for the log line."""
    if event.kind is BillingEventKind.IGNORED:
        return "ignored"

    if event.kind is BillingEventKind.SUBSCRIPTION_STARTED:
        if event.user_id is None or event.customer_ref is None:
            # A paid checkout that cannot be attributed. Loud, because it means the session
            # was created without the metadata `checkout-and-portal-api` must set — and the
            # user has been charged without becoming Pro.
            logger.error(
                "billing webhook could not attribute a completed checkout",
                extra={"outcome": "unattributable", "kind": event.kind.value},
            )
            return "unattributable"
        started = record_subscription_started(
            actor=WEBHOOK_ACTOR,
            user_id=event.user_id,
            plan=event.plan or DEFAULT_PLAN,
            customer_ref=event.customer_ref,
            subscription_ref=event.subscription_ref,
            current_period_end=event.current_period_end,
            event_at=event.occurred_at,
        )
        return "started" if started is not None else "no_change"

    if event.subscription_ref is None:
        # An event about a subscription that does not name one. Nothing to look up.
        return "no_change"

    if event.kind is BillingEventKind.SUBSCRIPTION_ENDED:
        ended = record_subscription_ended(
            actor=WEBHOOK_ACTOR,
            subscription_ref=event.subscription_ref,
            event_at=event.occurred_at,
        )
        return "ended" if ended is not None else "no_change"

    if event.kind is BillingEventKind.PAYMENT_FAILED:
        # `invoice.payment_failed` does not say what the subscription became, so this does
        # not guess one. It is recorded as past due, which keeps the user entitled while
        # the provider's dunning runs and makes the problem visible on the account screen.
        changed = record_subscription_changed(
            actor=WEBHOOK_ACTOR,
            subscription_ref=event.subscription_ref,
            status=SubscriptionStatus.PAST_DUE,
            event_at=event.occurred_at,
        )
        return "payment_failed" if changed is not None else "no_change"

    changed = record_subscription_changed(
        actor=WEBHOOK_ACTOR,
        subscription_ref=event.subscription_ref,
        status=_status_for(event),
        plan=event.plan,
        current_period_end=event.current_period_end,
        event_at=event.occurred_at,
    )
    return "changed" if changed is not None else "no_change"


def _status_for(event: BillingEvent) -> SubscriptionStatus:
    """The subscription status this change event reports.

    Reads `event.status`, which the adapter has **already mapped** into this product's
    vocabulary — never `raw_status`, which is the provider's own string and is carried only
    so a log line can name it. Confusing the two is the mistake this pair of fields exists to
    prevent.

    The adapter's mapping is total, so an unrecognised value should not arrive. The fallback
    is `past_due` anyway, and for the same reason the adapter uses it: it keeps a paying user
    entitled and makes the state visible on the account screen rather than hiding it.
    """
    try:
        return SubscriptionStatus(event.status or "")
    except ValueError:
        return SubscriptionStatus.PAST_DUE


__all__ = ["DEFAULT_PLAN", "SIGNATURE_HEADER", "receive_billing_event", "router"]
