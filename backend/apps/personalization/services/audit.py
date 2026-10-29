"""The `personalization` audit log writer (AD-5): one row per mutation, in the mutation's
transaction.

The `personal` counterpart of `apps/ingestion/services/audit.py`. The guard is the same: a
`write_audit` outside a `transaction.atomic(using=PERSONAL)` block raises instead of writing
an orphaned row, because an audit row committed apart from its mutation could record a change
that rolled back.

`personalization` writes only its own audit table. `delivery`'s reminder plan has its own audit
table, written by `delivery` (AD-16) — this module never writes it.
"""

from collections.abc import Mapping
from uuid import UUID

from django.db import connections

from apps.personalization.models import PersonalizationAuditEntry
from shared.actor import Actor
from shared.db import PERSONAL


class AuditOutsidePersonalTransaction(RuntimeError):
    """`write_audit` was called with no `transaction.atomic(using=PERSONAL)` block open.

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
) -> PersonalizationAuditEntry:
    """Append one audit row. Call it from inside the command's personal transaction."""
    if not connections[PERSONAL].in_atomic_block:
        raise AuditOutsidePersonalTransaction(
            "write_audit must run inside transaction.atomic(using=PERSONAL)."
        )
    return PersonalizationAuditEntry.objects.using(PERSONAL).create(
        actor_kind=actor.kind,
        actor_id=actor.id,
        actor_label=actor.label,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=dict(details or {}),
    )


__all__ = ["AuditOutsidePersonalTransaction", "write_audit"]
