"""The `personalization` audit writer (AD-5): one append-only row, only inside a personal
transaction.

The `personal` counterpart of `tests/ingestion/test_audit.py`. The guard is the same: a
`write_audit` outside a `transaction.atomic(using=PERSONAL)` block raises instead of writing
an orphaned row, because an audit row committed apart from its mutation could record a change
that rolled back.
"""

import pytest
from django.db import transaction

from apps.personalization.models import PersonalizationAuditEntry
from apps.personalization.services.audit import (
    AuditOutsidePersonalTransaction,
    write_audit,
)
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7

TARGET = {"action": "personal_event.created", "target_type": "personal_event"}


@pytest.mark.django_db(databases=[PERSONAL])
def test_write_audit_inside_personal_transaction_stores_user_actor_without_label():
    user_id, target_id = uuid7(), uuid7()

    with transaction.atomic(using=PERSONAL):
        entry = write_audit(
            actor=Actor.user(user_id), target_id=target_id, details={"name": "Coffee"}, **TARGET
        )

    stored = PersonalizationAuditEntry.objects.get(pk=entry.pk)
    assert (stored.actor_kind, stored.actor_id, stored.actor_label) == ("user", user_id, "")
    assert (stored.action, stored.target_type, stored.target_id) == (
        "personal_event.created",
        "personal_event",
        target_id,
    )
    assert stored.details == {"name": "Coffee"}


@pytest.mark.django_db(databases=[PERSONAL])
def test_write_audit_stores_system_actor_label():
    with transaction.atomic(using=PERSONAL):
        entry = write_audit(actor=Actor.system("propagation"), target_id=uuid7(), **TARGET)

    assert (entry.actor_kind, entry.actor_id, entry.actor_label) == (
        "system",
        None,
        "propagation",
    )


@pytest.mark.django_db(databases=[PERSONAL])
def test_write_audit_defaults_the_details_to_an_empty_mapping():
    with transaction.atomic(using=PERSONAL):
        entry = write_audit(actor=Actor.system("propagation"), target_id=uuid7(), **TARGET)

    assert PersonalizationAuditEntry.objects.get(pk=entry.pk).details == {}


# transaction=True: pytest-django otherwise wraps every alias in an atomic block, and the
# "no transaction open" branch could never run.
@pytest.mark.django_db(databases=[PERSONAL], transaction=True)
def test_write_audit_with_no_transaction_raises():
    with pytest.raises(AuditOutsidePersonalTransaction):
        write_audit(actor=Actor.system("propagation"), target_id=uuid7(), **TARGET)

    assert not PersonalizationAuditEntry.objects.exists()


@pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)
def test_write_audit_outside_a_personal_transaction_raises():
    # The guard is about *this* alias: an atomic block on another alias does not make the
    # personal write transactional with anything.
    with transaction.atomic(using=CATALOG), pytest.raises(AuditOutsidePersonalTransaction):
        write_audit(actor=Actor.system("propagation"), target_id=uuid7(), **TARGET)


@pytest.mark.django_db(databases=[PERSONAL])
def test_a_row_written_in_a_rolled_back_transaction_does_not_survive():
    # The point of the guard: an audit row that commits apart from its mutation would record a
    # change that never happened. Here the whole transaction rolls back, and the row goes with
    # it.
    with pytest.raises(RuntimeError):
        with transaction.atomic(using=PERSONAL):
            write_audit(actor=Actor.system("propagation"), target_id=uuid7(), **TARGET)
            raise RuntimeError("the mutation failed")

    assert not PersonalizationAuditEntry.objects.exists()


def test_write_audit_rejects_positional_arguments():
    with pytest.raises(TypeError):
        write_audit(
            Actor.system("propagation"), "personal_event.created", "personal_event", uuid7()
        )
