"""`write_audit` (AD-5): one append-only row, only inside a personal transaction."""

import pytest
from django.db import transaction

from apps.delivery.models import DeliveryAuditEntry
from apps.delivery.services.audit import AuditOutsidePersonalTransaction, write_audit
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7

TARGET = {"action": "reminder_plan.attached_default", "target_type": "personal_event"}


@pytest.mark.django_db(databases=[PERSONAL])
def test_write_audit_inside_personal_transaction_stores_user_actor_without_label():
    user_id, target_id = uuid7(), uuid7()

    with transaction.atomic(using=PERSONAL):
        entry = write_audit(
            actor=Actor.user(user_id), target_id=target_id, details={"slots": ["1d"]}, **TARGET
        )

    stored = DeliveryAuditEntry.objects.using(PERSONAL).get(pk=entry.pk)
    assert (stored.actor_kind, stored.actor_id, stored.actor_label) == ("user", user_id, "")
    assert (stored.action, stored.target_type, stored.target_id) == (
        "reminder_plan.attached_default",
        "personal_event",
        target_id,
    )
    assert stored.details == {"slots": ["1d"]}


@pytest.mark.django_db(databases=[PERSONAL])
def test_write_audit_stores_system_actor_label():
    with transaction.atomic(using=PERSONAL):
        entry = write_audit(actor=Actor.system("delivery_worker"), target_id=uuid7(), **TARGET)

    assert (entry.actor_kind, entry.actor_id, entry.actor_label) == (
        "system",
        None,
        "delivery_worker",
    )


# transaction=True: pytest-django otherwise wraps every alias in an atomic block, and the
# "no transaction open" branch could never run.
@pytest.mark.django_db(databases=[PERSONAL], transaction=True)
def test_write_audit_with_no_transaction_raises():
    with pytest.raises(AuditOutsidePersonalTransaction):
        write_audit(actor=Actor.system("delivery_worker"), target_id=uuid7(), **TARGET)

    assert not DeliveryAuditEntry.objects.using(PERSONAL).exists()


def test_write_audit_rejects_positional_arguments():
    with pytest.raises(TypeError):
        write_audit(Actor.system("delivery_worker"), "reminder_plan.attached_default", "x", uuid7())
