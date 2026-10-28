"""The `ingestion` audit log writer (AD-5): one row per mutation, in the mutation's transaction."""

from collections.abc import Mapping
from uuid import UUID

from django.db import connections

from apps.ingestion.models import IngestionAuditEntry
from shared.actor import Actor
from shared.db import CATALOG


class AuditOutsideCatalogTransaction(RuntimeError):
    """`write_audit` was called with no `transaction.atomic(using=CATALOG)` block open.

    A programming error, never mapped to HTTP: an audit row committed apart from its mutation
    could record a change that rolled back.
    """


def write_audit(
    *,
    actor: Actor,
    action: str,
    target_type: str,
    target_id: UUID,
    details: Mapping | None = None,
) -> IngestionAuditEntry:
    """Append one audit row. Call it from inside the command's catalog transaction."""
    if not connections[CATALOG].in_atomic_block:
        raise AuditOutsideCatalogTransaction(
            "write_audit must run inside transaction.atomic(using=CATALOG)."
        )
    return IngestionAuditEntry.objects.using(CATALOG).create(
        actor_kind=actor.kind,
        actor_id=actor.id,
        actor_label=actor.label,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=dict(details or {}),
    )
