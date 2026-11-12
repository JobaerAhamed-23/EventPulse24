"""The collections endpoints (FR-49): create, rename, reorder, delete, assign, unassign.

**The gate is here and not in the commands, deliberately.** `services/saved_collections.py`
is tier-agnostic by design — the rows are the user's data, and a command that refused on
tier would have to be re-run after an upgrade to restore what the user already said. The
API is where the *user* is, so it is where "you are not paying for this" belongs. The same
split `quiet-hours-pro-api` made.

**Only the two operations that add are gated**: creating a collection, and assigning a save
into one. Reading, unassigning, renaming, reordering and deleting are open on every tier, so
a lapsed Pro user keeps using what they have at its current size. `services/collection_cap.py`
records why each of those falls on the side it does.

**A collection that is not yours is 404, never 403**, on every endpoint. A "forbidden"
answer confirms the row exists, and a collection's name is content somebody wrote. The
services already answer this way; this layer does not second-guess them.

**The layer is thin.** It resolves the user from the session — never from a payload (AD-12)
— calls the published commands, and projects their plain data onto the wire. It never
imports models and never touches the ORM, which `test_no_direct_writes.py` enforces.
"""

from uuid import UUID

from django.utils import timezone
from ninja import Router, Status

from apps.identity.api_auth import current_user
from apps.personalization.schemas import (
    CollectionEventOut,
    CollectionIn,
    CollectionOrderIn,
    CollectionOut,
)
from apps.personalization.services.collection_cap import check_collections_allowed
from apps.personalization.services.saved_collections import (
    add_to_collection,
    create_collection,
    delete_collection,
    list_collection_events,
    list_collections,
    remove_from_collection,
    rename_collection,
    reorder_collections,
)
from shared.actor import Actor
from shared.errors import ErrorOut

router = Router(tags=["collections"], auth=current_user)


def _actor(request) -> Actor:
    """The acting user, for the audit rows the commands write (AD-5).

    The id comes from the session, never from the request — the same id the services scope
    their queries by.
    """
    return Actor.user(request.user.pk)


def _out(view) -> CollectionOut:
    return CollectionOut(
        id=view.id, name=view.name, position=view.position, item_count=view.item_count
    )


@router.post(
    "",
    response={201: CollectionOut, 409: ErrorOut, 422: ErrorOut},
    summary="Create a collection",
    description=(
        "Creates an empty collection at the end of this user's list.\n\n"
        "**Pro only.** A Free account is refused with 409 and a `{cap, upgrade_hint}` "
        "payload — the same inline-prompt shape the save cap and the calendar cap use, "
        "with no modal-shaped field.\n\n"
        "**It is created empty**, which is an ordinary state rather than a half-finished "
        "one: membership is explicit, so nothing is ever filed into a collection the user "
        "did not put it in.\n\n"
        "**The name is unique per user, case-insensitively** — 'Weekend' and 'weekend' are "
        "one name — and is stored exactly as typed."
    ),
)
def post_collection(request, body: CollectionIn):
    """Create a collection, if this account may have one."""
    check_collections_allowed(user_id=request.user.pk)
    view = create_collection(
        user_id=request.user.pk,
        name=body.name,
        actor=_actor(request),
        now=timezone.now(),
    )
    return Status(201, _out(view))


@router.get(
    "",
    response={200: list[CollectionOut]},
    summary="List your collections",
    description=(
        "This user's collections in the order they arranged, each with how many saves it "
        "holds.\n\n"
        "**Open on every tier.** A lapsed Pro user's collections do not vanish — the brief "
        "forbids deleting a downgraded account's data, and a list that hid them would be "
        "that deletion as far as the user could tell."
    ),
)
def get_collections(request):
    """This user's collections, in their order."""
    return [_out(view) for view in list_collections(user_id=request.user.pk)]


# ── `/order` is declared BEFORE the `/{collection_id}` routes, and must stay there ──
#
# **A literal segment loses to a path parameter when the parameter is registered first.**
# Django-ninja matches in registration order, so with `/{collection_id}` above it, a PUT to
# `/order` is matched by the rename route, `"order"` fails to parse as a UUID, and the
# caller gets a 405 naming PATCH and DELETE — an error that says nothing about the real
# problem. The tests caught exactly that, five times over.
@router.put(
    "/order",
    response={200: list[CollectionOut], 404: ErrorOut, 422: ErrorOut},
    summary="Set the order of your collections",
    description=(
        "Takes the **whole ordering in one request**, so the server never observes a "
        "partially reordered list.\n\n"
        "**The complete list, never a move instruction.** 'Put this one third' has to be "
        "interpreted against a list that may have changed since the client read it; a "
        "complete order is unambiguous. A list that does not name every collection "
        "exactly once is refused, because the unnamed ones would otherwise land "
        "somewhere nobody asked for.\n\n"
        "**Open on every tier.**"
    ),
)
def put_collection_order(request, body: CollectionOrderIn):
    """Set this user's collection order to exactly this list."""
    views = reorder_collections(
        user_id=request.user.pk,
        ordered_ids=body.collection_ids,
        actor=_actor(request),
        now=timezone.now(),
    )
    return [_out(view) for view in views]


@router.patch(
    "/{collection_id}",
    response={200: CollectionOut, 404: ErrorOut, 409: ErrorOut, 422: ErrorOut},
    summary="Rename a collection",
    description=(
        "Renames one of this user's collections.\n\n"
        "**Open on every tier.** Gating a rename would mean a lapsed user cannot fix a "
        "typo in a name they wrote themselves, which is punishment for lapsing rather "
        "than a tier boundary.\n\n"
        "**Renaming to the name it already has is allowed** and is not a collision with "
        "itself. Another collection's name is refused with 409."
    ),
)
def patch_collection(request, collection_id: UUID, body: CollectionIn):
    """Rename a collection."""
    view = rename_collection(
        user_id=request.user.pk,
        collection_id=collection_id,
        name=body.name,
        actor=_actor(request),
        now=timezone.now(),
    )
    return _out(view)


@router.delete(
    "/{collection_id}",
    response={204: None, 404: ErrorOut},
    summary="Delete a collection",
    description=(
        "Deletes a collection and **leaves every save inside it untouched** — they simply "
        "become uncollected.\n\n"
        "**Open on every tier.** This is the one delete the intent permits, and what it "
        "deletes is a grouping rather than user content. Gating it would trap a lapsed "
        "user with data they want gone, which is the inverse of what the "
        "never-delete constraint is for.\n\n"
        "The remaining collections close up, so positions stay dense."
    ),
)
def delete_collection_endpoint(request, collection_id: UUID):
    """Delete a collection, keeping its saves."""
    delete_collection(
        user_id=request.user.pk,
        collection_id=collection_id,
        actor=_actor(request),
        now=timezone.now(),
    )
    return Status(204, None)


@router.get(
    "/{collection_id}/events",
    response={200: list[CollectionEventOut], 404: ErrorOut},
    summary="List the saves in a collection",
    description=(
        "The saves in one collection, newest addition first.\n\n"
        "**The snapshot, and only the snapshot.** The times come from the user's own "
        "`SavedEvent` rows, which AD-17 propagation keeps correct — there is no `catalog` "
        "read here, because AD-3 forbids relating the two schemas and the snapshot is "
        "what the Timeline and the conflict detector already use.\n\n"
        "A surface that wants titles and venues uses `GET /api/personal/saved-events`, "
        "which is the endpoint that owns that join."
    ),
)
def get_collection_events(request, collection_id: UUID):
    """The saves in one collection, as snapshots."""
    snapshots = list_collection_events(user_id=request.user.pk, collection_id=collection_id)
    return [
        CollectionEventOut(
            id=snapshot.id,
            event_id=snapshot.event_id,
            start_time_utc=snapshot.start_utc,
            end_time_utc=snapshot.end_utc,
            event_version=snapshot.event_version,
        )
        for snapshot in snapshots
    ]


@router.put(
    "/{collection_id}/events/{saved_event_id}",
    response={204: None, 404: ErrorOut, 409: ErrorOut},
    summary="Put a save into a collection",
    description=(
        "Assigns one of this user's saves to one of their collections.\n\n"
        "**Pro only**, and refused with the same `{cap, upgrade_hint}` payload as a "
        "create. Without this gate the cap would limit how many collections exist and not "
        "how much they are used.\n\n"
        "**Idempotent**: a save already in the collection is the same statement twice, so "
        "it answers 204 and writes no audit row.\n\n"
        "**A save can be in several collections at once** — membership is a table, not a "
        "column."
    ),
)
def put_collection_event(request, collection_id: UUID, saved_event_id: UUID):
    """Assign a save to a collection."""
    check_collections_allowed(user_id=request.user.pk)
    add_to_collection(
        user_id=request.user.pk,
        collection_id=collection_id,
        saved_event_id=saved_event_id,
        actor=_actor(request),
        now=timezone.now(),
    )
    return Status(204, None)


@router.delete(
    "/{collection_id}/events/{saved_event_id}",
    response={204: None, 404: ErrorOut},
    summary="Take a save out of a collection",
    description=(
        "Removes a membership. **The save itself is untouched** — it simply stops being "
        "in this collection.\n\n"
        "**Open on every tier**, and deliberately so: this is how a lapsed Pro user tidies "
        "up, and refusing it would trap them with an arrangement they cannot change.\n\n"
        "Removing something that is not there is a no-op."
    ),
)
def delete_collection_event(request, collection_id: UUID, saved_event_id: UUID):
    """Take a save out of a collection."""
    remove_from_collection(
        user_id=request.user.pk,
        collection_id=collection_id,
        saved_event_id=saved_event_id,
        actor=_actor(request),
        now=timezone.now(),
    )
    return Status(204, None)


__all__ = ["router"]
