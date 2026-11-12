"""Billing port (FR-48..52): Pro checkout, the customer portal, and inbound events.

Two directions, and the second is the one worth explaining.

**Outbound** (`create_checkout`, `create_portal_session`) sends the user to the provider.

**Inbound** is `parse_event`, and it lives on the port for a reason that is structural rather
than stylistic. Subscription state arrives as a signed webhook, and verifying that signature
needs the provider's own SDK. The `stripe-sdk` import contract lists `apps` as a forbidden
source, so an app-layer endpoint *cannot* verify a signature: it may not import the SDK. So
the endpoint hands this port raw bytes and a signature header, and receives a `BillingEvent`
expressed in **our** vocabulary — no provider event names, no provider status strings, no SDK
object. The provider's vocabulary stops here, exactly as it already does for `ProPlan` and
`CheckoutSession`.

That seam has a second payoff: the receiver can be built and tested against the fake adapter
with no SDK involved at all.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ProPlan(StrEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


@dataclass(frozen=True)
class BillingCustomer:
    user_id: UUID
    email: str


@dataclass(frozen=True)
class CheckoutSession:
    session_id: str
    url: str


@dataclass(frozen=True)
class PortalSession:
    url: str


class BillingEventKind(StrEnum):
    """What an inbound billing event means to this product.

    Deliberately our vocabulary, not the provider's. Stripe sends
    `customer.subscription.deleted`; the receiver matches on `SUBSCRIPTION_ENDED`. Swapping
    providers, or Stripe renaming an event, is then an adapter change and not a change to
    every `match` arm in the app.

    `PAYMENT_FAILED` is its own kind rather than a `SUBSCRIPTION_CHANGED` carrying a status,
    because `invoice.payment_failed` does **not** say what the subscription's status became —
    Stripe sends a separate subscription-updated event for that. Collapsing the two would have
    the receiver inventing a status the provider never reported.

    `IGNORED` is an event type we deliberately do not handle. It is a real answer, not a
    failure: the receiver acknowledges it so the provider stops retrying.
    """

    SUBSCRIPTION_STARTED = "subscription_started"
    SUBSCRIPTION_CHANGED = "subscription_changed"
    SUBSCRIPTION_ENDED = "subscription_ended"
    PAYMENT_FAILED = "payment_failed"
    IGNORED = "ignored"


@dataclass(frozen=True)
class BillingEvent:
    """One verified inbound event, in this product's terms.

    `occurred_at` is the provider's own timestamp for the event, and it becomes the
    `event_at` that the subscription commands compare against their stored `last_event_at`.
    It is therefore the thing that makes an out-of-order delivery safe, which is why it is
    required rather than optional.

    `user_id` is present only on the event that starts a subscription, and only because the
    checkout session was created carrying it as metadata. Every later event names the
    subscription and not the user, which is why the change and end commands look a
    subscription up by reference.
    """

    kind: BillingEventKind
    event_id: str
    occurred_at: datetime
    customer_ref: str | None = None
    subscription_ref: str | None = None
    user_id: UUID | None = None
    plan: ProPlan | None = None
    current_period_end: datetime | None = None
    #: The subscription status **in this product's vocabulary**, already mapped by the
    #: adapter. This is what the receiver acts on.
    status: str | None = None
    #: The provider's own status string, kept only so a log line can name what arrived when
    #: the mapping did not recognise it. **Never interpreted by the app** — the two fields
    #: are separate precisely so that a raw provider string cannot be mistaken for ours.
    raw_status: str | None = None


class InvalidWebhookSignature(Exception):
    """The payload did not verify against the signing secret.

    The one inbound case that is an error rather than an outcome: an unverified payload is
    not a provider delivery at all, it is someone posting to the endpoint. The receiver
    answers 400 and changes nothing.
    """


class BillingPort(ABC):
    @abstractmethod
    def create_checkout(
        self, customer: BillingCustomer, plan: ProPlan, *, success_url: str, cancel_url: str
    ) -> CheckoutSession: ...

    @abstractmethod
    def create_portal_session(self, customer_ref: str, *, return_url: str) -> PortalSession: ...

    @abstractmethod
    def parse_event(self, payload: bytes, *, signature: str) -> BillingEvent:
        """Verify `payload` against the signing secret and translate it.

        `payload` is the **raw request body**, not a parsed and re-serialised object:
        verification is over the exact bytes, and normalising them first both breaks
        verification and invites a bypass.

        Raises `InvalidWebhookSignature` when the payload does not verify. An event type this
        product does not handle is **not** an error — it comes back as
        `BillingEventKind.IGNORED`.
        """
