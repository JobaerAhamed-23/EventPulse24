"""The `identity` audit log (AD-5): one row per mutation, inside the mutation's
transaction, and never written by anything else.

The guard is the important part: an audit row committed apart from its mutation could
record a change that rolled back, so `write_audit` outside a personal transaction raises
instead of writing an orphaned row.
"""

import pytest
from django.db import IntegrityError, connections, transaction

from apps.identity.models import IdentityAuditEntry
from apps.identity.services import audit as audit_service
from apps.identity.services.audit import AuditOutsidePersonalTransaction, write_audit
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7
from shared.models import AppendOnlyViolation
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


@pytest.mark.django_db(databases=[PERSONAL], transaction=True)
def test_write_audit_outside_a_transaction_raises():
    """The guard: an audit row committed apart from its mutation could record a change
    that rolled back.

    `transaction=True` gives the test its own autocommit connection, so
    `in_atomic_block` is False — the state a caller is in when it forgets the
    `transaction.atomic(using=PERSONAL)` wrapper.
    """
    from django.db import connections

    actor = Actor.user(uuid7())

    assert connections[PERSONAL].in_atomic_block is False

    with pytest.raises(AuditOutsidePersonalTransaction):
        write_audit(actor=actor, action="sign_up", target_type="User", target_id=uuid7())


def test_write_audit_inside_a_personal_transaction_writes_one_row():
    actor = Actor.user(uuid7())
    target = uuid7()

    with transaction.atomic(using=PERSONAL):
        write_audit(actor=actor, action="sign_up", target_type="User", target_id=target)

    assert IdentityAuditEntry.objects.using(PERSONAL).count() == 1


def test_the_audit_row_carries_the_actor_by_value():
    actor = Actor.user(uuid7())

    with transaction.atomic(using=PERSONAL):
        row = write_audit(actor=actor, action="sign_up", target_type="User", target_id=uuid7())

    assert row.actor_id == actor.id
    assert row.actor_kind == "user"


def test_the_audit_row_holds_no_email():
    """The actor is a UUID and no label, so no address reaches a row."""
    user = UserFactory(email="maya@example.com")

    with transaction.atomic(using=PERSONAL):
        row = write_audit(
            actor=Actor.user(user.pk),
            action="sign_up",
            target_type="User",
            target_id=user.pk,
        )

    assert "maya@example.com" not in str(row.actor_label)
    assert "maya@example.com" not in str(row.details)


def test_the_audit_table_is_append_only():
    """The database refuses an update and a delete.

    Two layers, tested separately. The Python guard (`AppendOnlyModel.save`) refuses the
    update before any SQL is sent, so the ORM path raises `AppendOnlyViolation`. The
    database trigger is the real guarantee — it binds every role and raw SQL — and is
    tested below, with raw SQL so the Python guard is never in the path.
    """
    with transaction.atomic(using=PERSONAL):
        row = write_audit(
            actor=Actor.user(uuid7()), action="sign_up", target_type="User", target_id=uuid7()
        )

    row.action = "changed"
    with pytest.raises(AppendOnlyViolation):
        row.save(using=PERSONAL)


def test_the_audit_table_trigger_refuses_an_update():
    """The trigger itself, below the ORM: raw SQL, so the Python guard is not in the path."""
    with transaction.atomic(using=PERSONAL):
        row = write_audit(
            actor=Actor.user(uuid7()), action="sign_up", target_type="User", target_id=uuid7()
        )

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic(using=PERSONAL):
        with connections[PERSONAL].cursor() as cursor:
            cursor.execute(
                "UPDATE personal.identity_identityauditentry SET action = 'changed' WHERE id = %s",
                [row.pk],
            )

    assert "append-only" in str(excinfo.value.__cause__)


def test_the_audit_table_trigger_refuses_a_delete():
    with transaction.atomic(using=PERSONAL):
        row = write_audit(
            actor=Actor.user(uuid7()), action="sign_up", target_type="User", target_id=uuid7()
        )

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic(using=PERSONAL):
        with connections[PERSONAL].cursor() as cursor:
            cursor.execute(
                "DELETE FROM personal.identity_identityauditentry WHERE id = %s",
                [row.pk],
            )

    assert "append-only" in str(excinfo.value.__cause__)


def test_the_audit_table_is_in_the_personal_schema():
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "SELECT table_schema FROM information_schema.tables "
            "WHERE table_name = 'identity_identityauditentry'"
        )
        rows = cursor.fetchall()

    assert rows == [("personal",)]


def test_the_audit_service_exposes_only_the_writer():
    """`identity` writes its own audit table and nobody else's."""
    assert audit_service.__all__ == ["AuditOutsidePersonalTransaction", "write_audit"]
