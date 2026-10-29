"""`write_audit` (design D17): one append-only row, only inside a catalog transaction."""

import pytest
from django.db import transaction

from apps.ingestion.models import IngestionAuditEntry
from apps.ingestion.services.audit import AuditOutsideCatalogTransaction, write_audit
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7

TARGET = {"action": "register_source", "target_type": "source"}


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_write_audit_inside_catalog_transaction_stores_user_actor_without_label():
    user_id, target_id = uuid7(), uuid7()

    with transaction.atomic(using=CATALOG):
        entry = write_audit(
            actor=Actor.user(user_id), target_id=target_id, details={"cadence_h": 4}, **TARGET
        )

    stored = IngestionAuditEntry.objects.using(CATALOG).get(pk=entry.pk)
    assert (stored.actor_kind, stored.actor_id, stored.actor_label) == ("user", user_id, "")
    assert (stored.action, stored.target_type, stored.target_id) == (
        "register_source",
        "source",
        target_id,
    )
    assert stored.details == {"cadence_h": 4}


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_write_audit_stores_system_actor_label():
    with transaction.atomic(using=CATALOG):
        entry = write_audit(actor=Actor.system("ingest_pipeline"), target_id=uuid7(), **TARGET)

    assert (entry.actor_kind, entry.actor_id, entry.actor_label) == (
        "system",
        None,
        "ingest_pipeline",
    )


# transaction=True: pytest-django otherwise wraps every alias in an atomic block, and the
# "no transaction open" branch could never run.
@pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)
def test_write_audit_with_no_transaction_raises():
    with pytest.raises(AuditOutsideCatalogTransaction):
        write_audit(actor=Actor.system("ingest_pipeline"), target_id=uuid7(), **TARGET)

    assert not IngestionAuditEntry.objects.using(CATALOG).exists()


@pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)
def test_write_audit_inside_personal_transaction_only_raises():
    with transaction.atomic(using=PERSONAL), pytest.raises(AuditOutsideCatalogTransaction):
        write_audit(actor=Actor.system("ingest_pipeline"), target_id=uuid7(), **TARGET)


def test_write_audit_rejects_positional_arguments():
    with pytest.raises(TypeError):
        write_audit(Actor.system("ingest_pipeline"), "register_source", "source", uuid7())
