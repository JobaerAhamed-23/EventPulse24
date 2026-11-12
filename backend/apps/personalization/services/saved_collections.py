"""The collection commands (FR-49): name a grouping of saves, order it, fill it, drop it.

`personalization` owns `SavedEvent`, so it owns the groupings over it (AD-16). Every write
here goes through a named command with a `PersonalizationAuditEntry` (AD-5), and every one
of them runs inside one `transaction.atomic(using=PERSONAL)`.

**No command checks the tier, and that is the design rather than an omission.** FR-49's cap
is the API's to enforce (`saved-collections-api`), because the brief forbids deleting a
lapsed subscriber's over-cap data: their collections must stay readable, and a command that
refused on tier would also refuse the reads and re-writes that keep them. The same split
`quiet-hours-pro-api` made, for the same reason — the paywall belongs where the user is.

**Ordering is dense — `0..n-1`, no gaps, no ties — and the lock is what makes that safe.**
Two concurrent reorders of one user's list would otherwise interleave their renumberings and
leave the positions neither order asked for. `pg_advisory_xact_lock` serialises them per
user, exactly as `delivery.notification_preferences` does for the settings row; it is
transaction-scoped, so a crashed worker cannot wedge anyone.

**The unique constraint on `(user_id, position)` is deferred, and the renumber depends on
it.** Rewriting a list of five positions touches rows one at a time, and the second write
collides with a position the fourth row has not vacated yet. Postgres checks a deferred
constraint at commit, when the list is whole; an immediate constraint would reject the
middle of a perfectly legal reorder. Nothing here renumbers "cleverly" to avoid collisions,
because the deferral is the mechanism and working around it would hide a broken constraint.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import blake2b
from uuid import UUID

from django.db import connections, transaction
from django.db.models.functions import Lower

from apps.personalization.models import SavedCollection, SavedCollectionItem, SavedEvent
from apps.personalization.services.audit import write_audit
from apps.personalization.services.saved_events import (
    SavedEventNotFoundError,
    SavedEventSnapshot,
)
from domain.errors import (
    CollectionNameTaken,
    CollectionNotFoundError,
    InvalidCollectionOrderError,
)
from shared.actor import Actor
from shared.db import PERSONAL

#: The advisory-lock key space for one user's collection list. Its own, not `delivery`'s:
#: a different table in a different app, with no shared invariant.
_LOCK_PERSON = b"eventpulse24-col"


@dataclass(frozen=True)
class CollectionView:
    """One collection as plain data, with the size of it.

    A frozen dataclass and never a model instance, matching `SavedEventSnapshot`: a caller
    holding the model could write it, and the commands here are the only writers.
    """

    id: UUID
    user_id: UUID
    name: str
    position: int
    item_count: int


def _user_lock_key(user_id: UUID) -> int:
    """The advisory-lock key for one user's collection list.

    Stable across processes: `blake2b`, never the per-process-salted `hash()`.
    """
    digest = blake2b(str(user_id).encode(), digest_size=8, person=_LOCK_PERSON).digest()
    return int.from_bytes(digest, "big", signed=True)


def _lock_user(user_id: UUID) -> None:
    """Serialise this user's collection writes. See the module docstring."""
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_user_lock_key(user_id)])


def _view(collection: SavedCollection, item_count: int | None = None) -> CollectionView:
    return CollectionView(
        id=collection.id,
        user_id=collection.user_id,
        name=collection.name,
        position=collection.position,
        item_count=(
            item_count
            if item_count is not None
            else SavedCollectionItem.objects.using(PERSONAL)
            .filter(collection_id=collection.id)
            .count()
        ),
    )


def _item_counts(user_id: UUID) -> dict[UUID, int]:
    """How many saves are in each of this user's collections, in one query.

    A `values_list` tallied in Python rather than an `annotate(Count(...))` join, so an
    empty collection is simply absent from the map and the caller defaults it to zero —
    which is the same answer with one fewer join to reason about.
    """
    counts: dict[UUID, int] = {}
    rows = (
        SavedCollectionItem.objects.using(PERSONAL)
        .filter(collection__user_id=user_id)
        .values_list("collection_id")
    )
    for (collection_id,) in rows:
        counts[collection_id] = counts.get(collection_id, 0) + 1
    return counts


def _get_owned(user_id: UUID, collection_id: UUID) -> SavedCollection:
    """This user's collection, or `CollectionNotFoundError`.

    **The user id is part of the lookup, not checked afterwards.** A read that fetched by id
    and then compared the owner would be one forgotten comparison away from handing over
    somebody else's collection.
    """
    collection = (
        SavedCollection.objects.using(PERSONAL).filter(id=collection_id, user_id=user_id).first()
    )
    if collection is None:
        raise CollectionNotFoundError(details={"collection_id": str(collection_id)})
    return collection


def _name_taken(user_id: UUID, name: str, *, excluding: UUID | None = None) -> bool:
    """Whether this user already has this name, compared case-insensitively.

    The database enforces this too (`saved_collection_user_name_uq`). This exists so the
    caller gets `CollectionNameTaken` — a sentence written for a person — rather than an
    `IntegrityError` surfacing as a 500. The constraint remains the authority; a race
    between the check and the insert ends at the constraint, which is the correct place for
    it to end.
    """
    rows = (
        SavedCollection.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .annotate(folded=Lower("name"))
        .filter(folded=name.lower())
    )
    if excluding is not None:
        rows = rows.exclude(id=excluding)
    return rows.exists()


def _next_position(user_id: UUID) -> int:
    """Where a new collection goes: the end.

    **Nothing already in the list moves.** Inserting at the top would rewrite every other
    row's position on every create, for no gain the user asked for, and would make a create
    race an in-flight reorder.
    """
    return SavedCollection.objects.using(PERSONAL).filter(user_id=user_id).count()


def create_collection(
    *,
    user_id: UUID,
    name: str,
    actor: Actor,
    now: datetime,
) -> CollectionView:
    """Create an empty collection at the end of this user's list (FR-49).

    **It is created empty, and that is a feature of the model.** Membership is explicit, so
    a collection with nothing in it is an ordinary state rather than a half-finished one.

    **The name is stored exactly as typed**, with surrounding whitespace stripped. The fold
    is only for comparison: a user who writes "Weekend" sees "Weekend".

    Raises:
        CollectionNameTaken: this user already has that name, ignoring case.
        ValueError: the name is empty once stripped.
    """
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("a collection name cannot be empty")

    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        if _name_taken(user_id, cleaned):
            raise CollectionNameTaken(details={"name": cleaned})

        collection = SavedCollection.objects.using(PERSONAL).create(
            user_id=user_id, name=cleaned, position=_next_position(user_id)
        )
        write_audit(
            actor=actor,
            action="saved_collection.created",
            target_type="saved_collection",
            target_id=collection.id,
            details={"name": cleaned, "position": collection.position, "at": now.isoformat()},
        )
        return _view(collection, item_count=0)


def rename_collection(
    *,
    user_id: UUID,
    collection_id: UUID,
    name: str,
    actor: Actor,
    now: datetime,
) -> CollectionView:
    """Rename one of this user's collections (FR-49).

    Renaming a collection to the name it already has is allowed and is not a collision with
    itself — the check excludes this row, which is the case a naive "does this name exist?"
    gets wrong by refusing a no-op.

    Raises:
        CollectionNotFoundError: no such collection, or not this user's.
        CollectionNameTaken: another of this user's collections has that name.
        ValueError: the name is empty once stripped.
    """
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("a collection name cannot be empty")

    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        collection = _get_owned(user_id, collection_id)
        if _name_taken(user_id, cleaned, excluding=collection.id):
            raise CollectionNameTaken(details={"name": cleaned})

        previous = collection.name
        collection.name = cleaned
        # `updated_at` is auto_now, and Django only writes it when update_fields names it.
        collection.save(using=PERSONAL, update_fields=["name", "updated_at"])
        write_audit(
            actor=actor,
            action="saved_collection.renamed",
            target_type="saved_collection",
            target_id=collection.id,
            details={"from": previous, "to": cleaned, "at": now.isoformat()},
        )
        return _view(collection)


def delete_collection(
    *,
    user_id: UUID,
    collection_id: UUID,
    actor: Actor,
    now: datetime,
) -> None:
    """Delete a collection, leaving every save inside it untouched (FR-49).

    **This is the one delete this intent permits, and what it deletes is a grouping.** The
    `SavedEvent` rows are the user's content and are never touched: the membership rows go
    with the collection by `CASCADE`, and the saves inside simply become uncollected. The
    brief's constraint — nothing of the user's is deleted on a downgrade — is about content,
    and a collection the user asked to delete is not that.

    **The list is closed up afterwards.** Positions stay dense, so deleting the second of
    five leaves `0..3` rather than a hole at 1 that a later reorder would have to reason
    about.
    """
    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        collection = _get_owned(user_id, collection_id)
        name, position = collection.name, collection.position
        item_count = (
            SavedCollectionItem.objects.using(PERSONAL).filter(collection_id=collection.id).count()
        )

        collection.delete(using=PERSONAL)
        _close_gap(user_id, removed_position=position)
        write_audit(
            actor=actor,
            action="saved_collection.deleted",
            target_type="saved_collection",
            target_id=collection_id,
            details={
                "name": name,
                "position": position,
                "items_released": item_count,
                "at": now.isoformat(),
            },
        )


def _close_gap(user_id: UUID, *, removed_position: int) -> None:
    """Pull everything after a removed position down by one, keeping the list dense.

    Walked in ascending order so each row moves into the slot the previous one just left.
    The deferred constraint means the order would not strictly matter, but a renumber that
    reads in the list's own order is one a person can follow.
    """
    following = (
        SavedCollection.objects.using(PERSONAL)
        .filter(user_id=user_id, position__gt=removed_position)
        .order_by("position")
    )
    for collection in following:
        collection.position -= 1
        collection.save(using=PERSONAL, update_fields=["position", "updated_at"])


def reorder_collections(
    *,
    user_id: UUID,
    ordered_ids: Sequence[UUID],
    actor: Actor,
    now: datetime,
) -> list[CollectionView]:
    """Set the order of this user's collections to exactly this list (FR-49).

    **The whole list is given, not a move instruction.** "Put this one third" has to be
    interpreted against a list that may have changed since the client read it; a complete
    order is unambiguous, and the result is the order the user saw themselves arrange.

    **The request must name every collection this user has, exactly once.** A partial list
    would leave the unnamed ones somewhere this function had to invent, and an order nobody
    asked for is worse than a refusal.

    **Positions are rewritten `0..n-1` inside one transaction**, which is transiently
    inconsistent and relies on the deferred unique constraint. See the module docstring.

    **The two refusals are `InvalidCollectionOrderError`, not `ValueError`.** This body
    comes off the wire, so a `ValueError` would reach the caller as a 500 — a server error
    for a request the server understood and chose to refuse.

    Raises:
        CollectionNotFoundError: an id in the list is not this user's.
        InvalidCollectionOrderError: the list repeats an id, or does not cover the user's
            collections.
    """
    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        existing = list(
            SavedCollection.objects.using(PERSONAL).filter(user_id=user_id).order_by("position")
        )
        by_id = {collection.id: collection for collection in existing}

        if len(set(ordered_ids)) != len(ordered_ids):
            raise InvalidCollectionOrderError(
                details={"reason": "a collection is named more than once"}
            )
        for collection_id in ordered_ids:
            if collection_id not in by_id:
                raise CollectionNotFoundError(details={"collection_id": str(collection_id)})
        if len(ordered_ids) != len(existing):
            raise InvalidCollectionOrderError(
                details={"expected": len(existing), "received": len(ordered_ids)}
            )

        for position, collection_id in enumerate(ordered_ids):
            collection = by_id[collection_id]
            if collection.position == position:
                continue
            collection.position = position
            collection.save(using=PERSONAL, update_fields=["position", "updated_at"])

        write_audit(
            actor=actor,
            action="saved_collection.reordered",
            target_type="saved_collection",
            target_id=user_id,
            details={"order": [str(cid) for cid in ordered_ids], "at": now.isoformat()},
        )
        # **One counting query, not one per collection.** `_view`'s own fallback counts a
        # single collection, which is right for a command that touched one and an N+1 for a
        # command that touched the whole list.
        counts = _item_counts(user_id)
        return [_view(by_id[cid], item_count=counts.get(cid, 0)) for cid in ordered_ids]


def add_to_collection(
    *,
    user_id: UUID,
    collection_id: UUID,
    saved_event_id: UUID,
    actor: Actor,
    now: datetime,
) -> None:
    """Put one of this user's saves into one of their collections (FR-49).

    **Idempotent.** Adding a save that is already there is the same statement twice, so it
    returns quietly and writes no audit row: nothing changed, so there is nothing to record.

    **A save can be in several collections at once**, which is the point of an explicit
    membership table.

    Raises:
        CollectionNotFoundError: no such collection, or not this user's.
        SavedEventNotFoundError: no such save, or not this user's.
    """
    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        collection = _get_owned(user_id, collection_id)
        saved = (
            SavedEvent.objects.using(PERSONAL).filter(id=saved_event_id, user_id=user_id).first()
        )
        if saved is None:
            # **The save's own error, not the collection's.** Reporting a missing save as
            # a missing *collection* would send a client looking at the wrong thing — and
            # the collection was found a line ago. The reasoning `_get_owned` uses still
            # applies: another user's save is reported as absent, never as forbidden.
            raise SavedEventNotFoundError(details={"saved_event_id": str(saved_event_id)})

        _item, created = SavedCollectionItem.objects.using(PERSONAL).get_or_create(
            collection=collection, saved_event=saved, defaults={"added_at": now}
        )
        if not created:
            return

        write_audit(
            actor=actor,
            action="saved_collection.item_added",
            target_type="saved_collection",
            target_id=collection.id,
            details={"saved_event_id": str(saved_event_id), "at": now.isoformat()},
        )


def remove_from_collection(
    *,
    user_id: UUID,
    collection_id: UUID,
    saved_event_id: UUID,
    actor: Actor,
    now: datetime,
) -> None:
    """Take one save out of one collection, leaving the save itself alone (FR-49).

    **This removes a membership, never a save.** The `SavedEvent` row is untouched; the
    event simply stops being in this collection.

    Removing something that is not there is a no-op and writes no audit row.
    """
    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        collection = _get_owned(user_id, collection_id)
        item = (
            SavedCollectionItem.objects.using(PERSONAL)
            .filter(collection_id=collection.id, saved_event_id=saved_event_id)
            .first()
        )
        if item is None:
            return

        item.delete(using=PERSONAL)
        write_audit(
            actor=actor,
            action="saved_collection.item_removed",
            target_type="saved_collection",
            target_id=collection.id,
            details={"saved_event_id": str(saved_event_id), "at": now.isoformat()},
        )


def list_collections(*, user_id: UUID) -> list[CollectionView]:
    """This user's collections, in their order, with the size of each.

    The counts come from one grouped query rather than one query per collection, because a
    user with twelve collections should cost two queries and not thirteen.
    """
    collections = list(
        SavedCollection.objects.using(PERSONAL).filter(user_id=user_id).order_by("position")
    )
    counts = _item_counts(user_id)
    return [
        _view(collection, item_count=counts.get(collection.id, 0)) for collection in collections
    ]


def list_collection_events(*, user_id: UUID, collection_id: UUID) -> list[SavedEventSnapshot]:
    """The saves in one of this user's collections, as snapshots, newest addition first.

    **The snapshot and nothing else.** The times are the user's own `SavedEvent` rows,
    which AD-17 propagation keeps correct; no `catalog` read happens here, because AD-3
    forbids relating the two schemas and the snapshot is what the Timeline and the conflict
    detector already use.

    **One query, not one per save.** The membership rows and the saves they point at are
    both in `personal` and both in this app, so the join is ordinary — and a per-save read
    would turn a twelve-event collection into thirteen round trips.

    Raises:
        CollectionNotFoundError: no such collection, or not this user's.
    """
    collection = _get_owned(user_id, collection_id)
    items = (
        SavedCollectionItem.objects.using(PERSONAL)
        .filter(collection_id=collection.id)
        .select_related("saved_event")
        .order_by("-added_at")
    )
    return [
        SavedEventSnapshot(
            id=item.saved_event.id,
            user_id=item.saved_event.user_id,
            event_id=item.saved_event.event_id,
            start_utc=item.saved_event.start_utc,
            end_utc=item.saved_event.end_utc,
            event_version=item.saved_event.event_version,
        )
        for item in items
    ]


def list_collection_saves(*, user_id: UUID, collection_id: UUID) -> list[UUID]:
    """The ids of the saves in one of this user's collections, newest addition first.

    Raises:
        CollectionNotFoundError: no such collection, or not this user's.
    """
    collection = _get_owned(user_id, collection_id)
    return list(
        SavedCollectionItem.objects.using(PERSONAL)
        .filter(collection_id=collection.id)
        .order_by("-added_at")
        .values_list("saved_event_id", flat=True)
    )


__all__ = [
    "CollectionView",
    "add_to_collection",
    "create_collection",
    "delete_collection",
    "list_collection_events",
    "list_collection_saves",
    "list_collections",
    "remove_from_collection",
    "rename_collection",
    "reorder_collections",
]
