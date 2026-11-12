"""The commands that move a `Subscription` (AD-5, FR-48).

Three named commands, one per thing that can happen to a subscription: it starts, it changes,
it ends. Each runs inside `transaction.atomic(using=PERSONAL)` and writes exactly one
`IdentityAuditEntry` in that transaction, which is what `audit_service.write_audit` enforces.

**Every command is order-tolerant, and that is the point of this module.** Stripe retries on
any non-2xx, replays on request, and does not promise ordering. The failure that matters is
specific: a stale `customer.subscription.updated` arriving after a cancellation, restoring
entitlement to someone who cancelled. So each command compares the incoming `event_at`
against the row's `last_event_at` and declines to apply anything older.

**A declined event returns `None`. It is not an exception.** An out-of-order delivery is
routine, and the webhook receiver must answer Stripe with success so it stops retrying.
Raising here would push a normal outcome through exception handling and invite a handler to
return 500 for something that is working correctly.

**Equal timestamps are not automatically a replay.** Stripe can emit two events in the same
second, so refusing on `event_at <= last_event_at` would drop a real status change. An equal
timestamp is declined only when it would change nothing; when the status differs, it is
applied. A strictly older event is always declined.

**The actor is passed in, never assumed.** Routine transitions carry a system actor —
`Actor(kind=ActorKind.SYSTEM, label="stripe_webhook")` — because no human is behind a webhook.
An admin granting a comp would pass a user actor. `shared/actor.py` requires a system actor to
carry a lowercase label and no id, which is why the label is spelled that way.

**No email, and no customer reference, reaches an audit row** (AD-13). `details` carries the
plan, the status and the subscription reference. The Stripe *customer* reference is left out:
audit rows live for seven years under `AUDIT_LOG`, and the reference identifies a paying
person without ever being needed to read the log.
"""

from datetime import datetime
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.identity.models import Subscription, SubscriptionStatus
from apps.identity.services import audit as audit_service
from ports.billing import ProPlan
from shared.actor import Actor
from shared.db import PERSONAL

#: The audit `target_type` for every row this module writes.
TARGET_TYPE = "subscription"

#: The system actor label for a webhook-driven transition. Lowercase with underscores, as
#: `shared.actor.SYSTEM_LABEL` requires.
STRIPE_WEBHOOK_ACTOR_LABEL = "stripe_webhook"


def _live_subscription_for(user_id: UUID) -> Subscription | None:
    """This user's live subscription, locked for the rest of the transaction, or `None`.

    `select_for_update` locks the rows it *returns*, so when the answer is `None` it has
    locked nothing and two concurrent commands can both reach the insert. That is by design:
    the partial unique constraint is what resolves the race, and the lock only matters for
    the case where a row already exists and must not change underneath the caller.

    A module-level function rather than an inline query so a test can make the check blind
    and exercise the losing side of the race deterministically, without threads.
    """
    return (
        Subscription.objects.using(PERSONAL)
        .select_for_update()
        .filter(
            user_id=user_id,
            status__in=(SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE),
        )
        .first()
    )


def _is_stale(subscription: Subscription, *, event_at: datetime, status_changes: bool) -> bool:
    """Should this event be declined as older than what the row already holds?

    Strictly older is always stale. Equal is stale only when applying it would change
    nothing — see the module docstring on same-second deliveries.
    """
    if subscription.last_event_at is None:
        return False
    if event_at > subscription.last_event_at:
        return False
    if event_at < subscription.last_event_at:
        return True
    return not status_changes


def record_subscription_started(
    *,
    actor: Actor,
    user_id: UUID,
    plan: ProPlan,
    customer_ref: str,
    subscription_ref: str | None,
    current_period_end: datetime | None,
    event_at: datetime,
) -> Subscription | None:
    """A checkout completed: this user now has a live subscription.

    Returns `None` when the user already holds a live subscription — the ordinary outcome of
    a replayed `checkout.session.completed`, and of two deliveries racing each other. The
    partial unique constraint is what makes the race safe; this catches its `IntegrityError`
    the way `sign_up` catches the email one.
    """
    with transaction.atomic(using=PERSONAL):
        if _live_subscription_for(user_id) is not None:
            return None
        try:
            # The insert gets its own nested `atomic` block — a savepoint — so its
            # `IntegrityError` can be caught here while the outer block stays usable.
            # Without the savepoint the connection is marked for rollback and the next
            # query in this transaction raises `TransactionManagementError`, which is
            # survivable only while nothing follows the catch. `sign_up` takes the same
            # precaution for the same reason, and says so.
            with transaction.atomic(using=PERSONAL):
                subscription = Subscription.objects.using(PERSONAL).create(
                    user_id=user_id,
                    plan=plan.value,
                    status=SubscriptionStatus.ACTIVE,
                    current_period_end=current_period_end,
                    stripe_customer_ref=customer_ref,
                    stripe_subscription_ref=subscription_ref,
                    last_event_at=event_at,
                )
        except IntegrityError:
            # The other side of the race won: its row committed between this command's
            # check and its insert, and the partial unique constraint refused ours. One
            # live subscription exists, which is the outcome this command wanted, so
            # there is nothing to add and nothing to record.
            return None
        audit_service.write_audit(
            actor=actor,
            action="subscription.started",
            target_type=TARGET_TYPE,
            target_id=subscription.id,
            details={
                "plan": plan.value,
                "status": SubscriptionStatus.ACTIVE.value,
                "subscription_ref": subscription_ref,
            },
        )
        return subscription


def record_subscription_changed(
    *,
    actor: Actor,
    subscription_ref: str,
    status: SubscriptionStatus,
    plan: ProPlan | None = None,
    current_period_end: datetime | None = None,
    event_at: datetime,
) -> Subscription | None:
    """A subscription's status, plan or period moved.

    Returns `None` when there is no such subscription, or when the event is older than what
    the row already holds. **This is the command the ordering guard exists for**: a stale
    `active` arriving after a cancellation must not restore entitlement.
    """
    with transaction.atomic(using=PERSONAL):
        subscription = (
            Subscription.objects.using(PERSONAL)
            .select_for_update()
            .filter(stripe_subscription_ref=subscription_ref)
            .first()
        )
        if subscription is None:
            return None
        if _is_stale(subscription, event_at=event_at, status_changes=subscription.status != status):
            return None

        subscription.status = status
        if plan is not None:
            subscription.plan = plan.value
        if current_period_end is not None:
            subscription.current_period_end = current_period_end
        subscription.last_event_at = event_at
        subscription.save(
            using=PERSONAL,
            update_fields=[
                "status",
                "plan",
                "current_period_end",
                "last_event_at",
                "updated_at",
            ],
        )
        audit_service.write_audit(
            actor=actor,
            action="subscription.changed",
            target_type=TARGET_TYPE,
            target_id=subscription.id,
            details={
                "plan": subscription.plan,
                "status": status.value,
                "subscription_ref": subscription_ref,
            },
        )
        return subscription


def record_subscription_ended(
    *,
    actor: Actor,
    subscription_ref: str,
    event_at: datetime,
) -> Subscription | None:
    """The subscription is over: entitlement stops.

    A transition to `CANCELED`, never a delete — see `Subscription`'s docstring. Returns
    `None` when there is no such subscription or the event is stale.
    """
    with transaction.atomic(using=PERSONAL):
        subscription = (
            Subscription.objects.using(PERSONAL)
            .select_for_update()
            .filter(stripe_subscription_ref=subscription_ref)
            .first()
        )
        if subscription is None:
            return None
        if _is_stale(
            subscription,
            event_at=event_at,
            status_changes=subscription.status != SubscriptionStatus.CANCELED,
        ):
            return None

        subscription.status = SubscriptionStatus.CANCELED
        subscription.last_event_at = event_at
        subscription.save(using=PERSONAL, update_fields=["status", "last_event_at", "updated_at"])
        audit_service.write_audit(
            actor=actor,
            action="subscription.ended",
            target_type=TARGET_TYPE,
            target_id=subscription.id,
            details={
                "plan": subscription.plan,
                "status": SubscriptionStatus.CANCELED.value,
                "subscription_ref": subscription_ref,
            },
        )
        return subscription


__all__ = [
    "STRIPE_WEBHOOK_ACTOR_LABEL",
    "TARGET_TYPE",
    "record_subscription_changed",
    "record_subscription_ended",
    "record_subscription_started",
]
