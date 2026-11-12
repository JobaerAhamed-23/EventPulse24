"""The commands that move a `Subscription` (AD-5, FR-48).

Stripe retries, replays and reorders. The failure these tests exist for is specific: a stale
`customer.subscription.updated` arriving after a cancellation, restoring entitlement to
someone who cancelled. The guard lives on the row, so every writer inherits it.

They also pin the quieter contracts: a declined event is `None` and not an exception, one
audit row per applied transition, no email or customer reference in a row, and a racing
create resolving to one live subscription.
"""

from datetime import UTC, datetime

import pytest

from apps.identity.models import IdentityAuditEntry, Subscription, SubscriptionStatus
from apps.identity.services import (
    is_pro,
    record_subscription_changed,
    record_subscription_ended,
    record_subscription_started,
)
from apps.identity.services.subscriptions import STRIPE_WEBHOOK_ACTOR_LABEL
from ports.billing import ProPlan
from shared.actor import Actor, ActorKind
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.identity.factories import SubscriptionFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 11, 11, 12, 5, tzinfo=UTC)
T2 = datetime(2026, 11, 11, 12, 10, tzinfo=UTC)

WEBHOOK = Actor(kind=ActorKind.SYSTEM, label=STRIPE_WEBHOOK_ACTOR_LABEL)


def _start(user_id=None, *, ref="sub_1", event_at=T0):
    return record_subscription_started(
        actor=WEBHOOK,
        user_id=user_id or uuid7(),
        plan=ProPlan.MONTHLY,
        customer_ref="cus_1",
        subscription_ref=ref,
        current_period_end=None,
        event_at=event_at,
    )


def _audit_actions(target_id):
    return list(
        IdentityAuditEntry.objects.using(PERSONAL)
        .filter(target_id=target_id)
        .order_by("at")
        .values_list("action", flat=True)
    )


# --------------------------------------------------------------------------- started


def test_starting_a_subscription_grants_pro_and_writes_one_audit_row():
    subscription = _start()
    assert subscription is not None
    assert is_pro(user_id=subscription.user_id) is True
    assert _audit_actions(subscription.id) == ["subscription.started"]


def test_a_replayed_checkout_does_not_create_a_second_subscription():
    """Stripe replays. The second delivery is a no-op, not an error — the receiver must
    still answer it with success so Stripe stops retrying."""
    first = _start()
    second = _start(first.user_id, ref="sub_1", event_at=T1)

    assert second is None
    assert Subscription.objects.using(PERSONAL).filter(user_id=first.user_id).count() == 1
    assert _audit_actions(first.id) == ["subscription.started"]


def test_the_actor_is_recorded_as_the_system_and_carries_no_id():
    """`shared.actor` requires a system actor to carry a lowercase label and no id, which is
    what keeps a human identity out of a webhook-driven row."""
    subscription = _start()
    entry = IdentityAuditEntry.objects.using(PERSONAL).get(target_id=subscription.id)
    assert entry.actor_kind == ActorKind.SYSTEM
    assert entry.actor_id is None
    assert entry.actor_label == STRIPE_WEBHOOK_ACTOR_LABEL


def test_no_customer_reference_reaches_an_audit_row():
    """Audit rows live seven years under `AUDIT_LOG`. The customer reference identifies a
    paying person and is never needed to read the log (AD-13)."""
    subscription = _start()
    entry = IdentityAuditEntry.objects.using(PERSONAL).get(target_id=subscription.id)
    assert "cus_1" not in str(entry.details)
    assert entry.details["subscription_ref"] == "sub_1"


# --------------------------------------------------------------------------- changed / ended


def test_a_cancellation_ends_entitlement_without_deleting_the_row():
    subscription = _start()
    ended = record_subscription_ended(actor=WEBHOOK, subscription_ref="sub_1", event_at=T1)

    assert ended is not None
    assert ended.status == SubscriptionStatus.CANCELED
    assert is_pro(user_id=subscription.user_id) is False
    assert Subscription.objects.using(PERSONAL).filter(pk=subscription.id).exists()


def test_a_payment_failure_moves_to_past_due_and_keeps_pro():
    subscription = _start()
    record_subscription_changed(
        actor=WEBHOOK,
        subscription_ref="sub_1",
        status=SubscriptionStatus.PAST_DUE,
        event_at=T1,
    )
    assert is_pro(user_id=subscription.user_id) is True


def test_a_stale_update_after_a_cancellation_does_not_restore_entitlement():
    """**The bug this whole module exists to prevent.**

    Stripe delivers `customer.subscription.deleted` at T2 and a `customer.subscription.updated`
    stamped T1 arrives afterwards. Applied naively, the cancelled user is Pro again.
    """
    subscription = _start(event_at=T0)
    record_subscription_ended(actor=WEBHOOK, subscription_ref="sub_1", event_at=T2)

    late = record_subscription_changed(
        actor=WEBHOOK,
        subscription_ref="sub_1",
        status=SubscriptionStatus.ACTIVE,
        event_at=T1,
    )

    assert late is None
    assert is_pro(user_id=subscription.user_id) is False
    subscription.refresh_from_db()
    assert subscription.status == SubscriptionStatus.CANCELED


def test_a_declined_stale_event_writes_no_audit_row():
    """A declined event changed nothing, so it must not leave a trace suggesting it did."""
    subscription = _start(event_at=T2)
    record_subscription_changed(
        actor=WEBHOOK, subscription_ref="sub_1", status=SubscriptionStatus.PAST_DUE, event_at=T0
    )
    assert _audit_actions(subscription.id) == ["subscription.started"]


def test_an_equal_timestamp_with_no_status_change_is_treated_as_a_replay():
    subscription = _start(event_at=T0)
    record_subscription_changed(
        actor=WEBHOOK, subscription_ref="sub_1", status=SubscriptionStatus.PAST_DUE, event_at=T1
    )
    repeat = record_subscription_changed(
        actor=WEBHOOK, subscription_ref="sub_1", status=SubscriptionStatus.PAST_DUE, event_at=T1
    )
    assert repeat is None
    assert _audit_actions(subscription.id) == ["subscription.started", "subscription.changed"]


def test_an_equal_timestamp_with_a_different_status_is_applied():
    """Stripe can emit two events in one second. Refusing on `<=` would drop a real change —
    this is the deviation from the design doc recorded in the plan."""
    subscription = _start(event_at=T0)
    record_subscription_changed(
        actor=WEBHOOK, subscription_ref="sub_1", status=SubscriptionStatus.PAST_DUE, event_at=T1
    )
    applied = record_subscription_changed(
        actor=WEBHOOK, subscription_ref="sub_1", status=SubscriptionStatus.ACTIVE, event_at=T1
    )
    assert applied is not None
    assert applied.status == SubscriptionStatus.ACTIVE
    assert is_pro(user_id=subscription.user_id) is True


def test_an_event_for_an_unknown_subscription_is_declined_not_raised():
    """The receiver must answer Stripe with success, so this cannot be an exception."""
    assert (
        record_subscription_changed(
            actor=WEBHOOK,
            subscription_ref="sub_does_not_exist",
            status=SubscriptionStatus.ACTIVE,
            event_at=T0,
        )
        is None
    )
    assert (
        record_subscription_ended(actor=WEBHOOK, subscription_ref="sub_does_not_exist", event_at=T0)
        is None
    )


def test_a_cancelled_user_can_subscribe_again():
    """The live slot is freed by the transition, and the history stays."""
    subscription = _start(event_at=T0)
    record_subscription_ended(actor=WEBHOOK, subscription_ref="sub_1", event_at=T1)

    again = _start(subscription.user_id, ref="sub_2", event_at=T2)

    assert again is not None
    assert is_pro(user_id=subscription.user_id) is True
    assert Subscription.objects.using(PERSONAL).filter(user_id=subscription.user_id).count() == 2


# --------------------------------------------------------------------------- audit guard


@pytest.mark.django_db(databases=[PERSONAL], transaction=True)
def test_the_commands_open_their_own_personal_transaction():
    """`write_audit` raises `AuditOutsidePersonalTransaction` unless an atomic block is open,
    so a command that forgot to open one could not write its audit row.

    The ordinary `django_db` mark wraps each test in a transaction, which would hide the
    omission — hence `transaction=True`, and the assertion that no block is open before the
    call. Deleting `transaction.atomic(using=PERSONAL)` from `record_subscription_started`
    makes this fail.
    """
    from django.db import connections

    assert connections[PERSONAL].in_atomic_block is False

    subscription = _start()

    assert subscription is not None
    assert _audit_actions(subscription.id) == ["subscription.started"]


def test_an_existing_row_untouched_by_a_declined_event_keeps_its_last_event_at():
    subscription = SubscriptionFactory(status=SubscriptionStatus.ACTIVE, last_event_at=T2)
    record_subscription_changed(
        actor=WEBHOOK,
        subscription_ref=subscription.stripe_subscription_ref,
        status=SubscriptionStatus.CANCELED,
        event_at=T0,
    )
    subscription.refresh_from_db()
    assert subscription.last_event_at == T2
    assert subscription.status == SubscriptionStatus.ACTIVE


def test_the_losing_side_of_a_concurrent_checkout_is_a_clean_no_op(monkeypatch):
    """Two deliveries race: each one's check runs before the other's insert commits.

    Simulated by making the check blind, which is exactly what the losing transaction sees.
    Removing the `except IntegrityError` makes this fail.

    **It does not pin the savepoint** around the insert, and it is worth saying so rather
    than implying otherwise: the command returns immediately after the catch, so no query
    follows it and the missing savepoint cannot bite. The savepoint is there because the
    first line added after that `return` would turn a caught `IntegrityError` into
    `TransactionManagementError`, and because `sign_up` takes the same precaution. It is
    defensive, not currently load-bearing.
    """
    from apps.identity.services import subscriptions as module

    user_id = uuid7()
    winner = _start(user_id, ref="sub_winner", event_at=T0)
    assert winner is not None

    monkeypatch.setattr(module, "_live_subscription_for", lambda _user_id: None)

    loser = _start(user_id, ref="sub_loser", event_at=T1)

    assert loser is None
    assert Subscription.objects.using(PERSONAL).filter(user_id=user_id).count() == 1
    assert is_pro(user_id=user_id) is True
    # The losing attempt recorded nothing: it created nothing.
    assert _audit_actions(winner.id) == ["subscription.started"]
