"""Abstract model bases shared by every app."""

from typing import ClassVar

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

from shared.actor import ActorKind
from shared.ids import uuid7


class UUIDv7Model(models.Model):
    """UUIDv7 primary key, minted in Python so a command has the id before `save()`.

    Postgres 18's `uuidv7()` is not used: audit rows and AD-7 send keys need the id at
    creation time.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    class Meta:
        abstract = True


class AppendOnlyViolation(RuntimeError):
    """Code tried to change or delete a row of an append-only table (a programming error)."""


class AppendOnlyQuerySet(models.QuerySet):
    """Blocks bulk paths that rewrite or remove rows, except the model's `append_only_mutable`.

    The database triggers are the real guarantee (they bind every role and raw SQL); this fails
    fast in Python with a readable error.
    """

    def update(self, **kwargs):
        mutable = self.model.append_only_mutable
        if not kwargs or not kwargs.keys() <= mutable:
            raise AppendOnlyViolation(
                f"{self.model._meta.label} is append-only; only {sorted(mutable)} may be set."
            )
        if any(value is None for value in kwargs.values()):
            raise AppendOnlyViolation(f"{self.model._meta.label}: a set field is never cleared.")
        return super().update(**kwargs)

    update.alters_data = True

    def bulk_update(self, objs, fields, batch_size=None):
        if not set(fields) or not set(fields) <= self.model.append_only_mutable:
            raise AppendOnlyViolation(f"{self.model._meta.label} is append-only.")
        return super().bulk_update(objs, fields, batch_size=batch_size)

    bulk_update.alters_data = True

    def bulk_create(self, objs, *args, update_conflicts=False, **kwargs):
        if update_conflicts:
            raise AppendOnlyViolation(f"{self.model._meta.label} is append-only; no upserts.")
        return super().bulk_create(objs, *args, update_conflicts=update_conflicts, **kwargs)

    bulk_create.alters_data = True

    def delete(self):
        raise AppendOnlyViolation(f"{self.model._meta.label} is append-only.")

    delete.alters_data = True
    delete.queryset_only = True


class AppendOnlyModel(models.Model):
    """Rows are inserted, never rewritten or deleted, except `append_only_mutable` fields, which
    may go from empty to set exactly once (for example an outbox's `propagated_at`).

    Concrete tables also get the `forbid_history_mutation` trigger and runtime-role grants in
    their migration; set `Meta.base_manager_name = "objects"` so related-object paths use the
    guarded QuerySet too.
    """

    append_only_mutable: ClassVar[frozenset[str]] = frozenset()

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, update_fields=None, **kwargs):
        # force_update on a freshly built instance takes the UPDATE path too.
        if not self._state.adding or kwargs.get("force_update"):
            fields = set(update_fields or ())
            if not fields or not fields <= self.append_only_mutable:
                raise AppendOnlyViolation(f"{self._meta.label} is append-only.")
            if any(getattr(self, name) is None for name in fields):
                raise AppendOnlyViolation(f"{self._meta.label}: a set field is never cleared.")
        super().save(*args, update_fields=update_fields, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyViolation(f"{self._meta.label} is append-only.")


def actor_check(name: str = "%(app_label)s_%(class)s_actor_ck") -> models.CheckConstraint:
    """The `shared.actor.Actor` rules as a database check, for any table storing an actor.

    A user actor has an id and no label; a system actor has a label and no id. The `%(class)s`
    default keeps the name unique per concrete table when used on an abstract base.
    """
    return models.CheckConstraint(
        condition=(
            models.Q(actor_kind=ActorKind.USER.value, actor_id__isnull=False, actor_label="")
            | (
                models.Q(actor_kind=ActorKind.SYSTEM.value, actor_id__isnull=True)
                & ~models.Q(actor_label="")
            )
        ),
        name=name,
    )


class ActorColumns(models.Model):
    """Who made a change, stored by value (`shared.actor.Actor`); pair with `actor_check()`.

    No relation to `User`: these columns live on catalog tables too (AD-3, spine OQ-8).
    """

    #: An audit row's "user" is whoever acted (FR-52 export). A system actor has no
    #: `actor_id`, so those rows belong to nobody and appear in no export — which is
    #: correct: a propagation job acting on the catalog is not a fact about a person.
    export_user_path = "actor_id"

    actor_kind = models.CharField(max_length=16, choices=[(k.value, k.value) for k in ActorKind])
    actor_id = models.UUIDField(null=True, blank=True)
    # System job name only (shared.actor.SYSTEM_LABEL), never a username or email.
    actor_label = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        abstract = True


class AuditEntry(AppendOnlyModel, ActorColumns, UUIDv7Model):
    """One audit-log row (AD-5), written in the same transaction as the mutation it records.

    Each owning app has its own concrete table, so the row sits in that app's schema and the app
    is its only writer (AD-16; spine OQ-8). The actor is stored by value, never as a relation to
    `User`: catalog tables may not relate across the AD-3 wall. Concrete tables are append-only.
    """

    at = models.DateTimeField(default=timezone.now, editable=False)
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=64)
    target_id = models.UUIDField()
    details = models.JSONField(default=dict, encoder=DjangoJSONEncoder, blank=True)

    class Meta:
        abstract = True
        base_manager_name = "objects"
        constraints = [actor_check()]
