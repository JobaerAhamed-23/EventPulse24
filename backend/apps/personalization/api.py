"""The personal-events endpoints (FR-18, FR-58, AD-19).

`POST /api/personal/events` creates one, `GET` lists and fetches, `PATCH` edits, `DELETE`
removes, and `POST /api/personal/events/conflicts/{pair_id}/resolve` answers a conflict
prompt.

**This surface is session-based and user-scoped.** AD-12's session-free rule applies to the
*public* catalog only. Every request here resolves exactly one user, from the session
(`apps.personalization.auth`), and no endpoint accepts a user id as input — so the scoping
cannot be talked out of by a payload.

The layer is thin: it resolves the user, parses the body, calls the published service, and
projects the service's plain data back onto the wire shape. It never imports
`apps.personalization.models` (import contract `models-personalization`) and never touches
the ORM directly.

**The conflict round trip is the interesting part.** A create that clashes does not
complete: the service writes the event and leaves the pair `active`, and the endpoint
answers **409** with the conflicting event and the three actions. The client then posts one
of them to the resolve endpoint. There is no dismiss — FR-58 says the user must choose — and
the action list comes from the service, so the schema cannot offer one either.
"""

from uuid import UUID

from django.utils import timezone
from ninja import Query, Router, Status

from apps.ingestion.services.catalog_read import EventNotFoundError, get_public_event
from apps.personalization.auth import current_user
from apps.personalization.schemas import (
    ConflictOut,
    ConflictResolutionIn,
    ConflictResolutionOut,
    PersonalEventCreateIn,
    PersonalEventListOut,
    PersonalEventListQuery,
    PersonalEventOut,
    PersonalEventPatchIn,
    SavedEventListOut,
    SavedEventListQuery,
    SavedEventOut,
    SchedulingConflictOut,
)
from apps.personalization.services.conflict_resolutions import resolve_conflict
from apps.personalization.services.conflicts import PERSONAL_EVENT_SIDE
from apps.personalization.services.personal_events import (
    ConflictFound,
    create_personal_event,
    delete_personal_event,
    get_personal_event,
    list_personal_events,
    update_personal_event,
)
from apps.personalization.services.saved_events import (
    list_saved_events,
    save_event,
    unsave_event,
)
from domain.errors import SchedulingConflictError
from shared.actor import Actor
from shared.errors import ErrorOut

router = Router(tags=["personal"], auth=current_user)

# A module-level singleton, so the query-parameter model is declared once. `Query(...)` is
# what makes the schema a set of query parameters: without it a schema-typed argument
# becomes a request *body*, and the query string would be ignored (B008).
EVENT_LIST_QUERY = Query(...)


def _actor(request) -> Actor:
    """The acting user, for the audit row the command writes (AD-5).

    The user id comes from the session, never from the request — the same id the service
    scopes its queries by.
    """
    return Actor.user(request.user.pk)


def _conflict_response(result: ConflictFound) -> SchedulingConflictError:
    """The 409 that carries the conflict and the three actions.

    `details` is plain data because `domain` is pure stdlib: the payload is built here,
    from the schema, and handed to the error as a dict.
    """
    return SchedulingConflictError(
        details={
            "event_id": str(result.event.id),
            "conflicts": [
                ConflictOut.from_detected(conflict).model_dump(mode="json")
                for conflict in result.conflicts
            ],
        }
    )


@router.post(
    "/events",
    response={201: PersonalEventOut, 409: SchedulingConflictOut},
    summary="Create a personal event",
    description=(
        "Creates a personal event. The IANA timezone is required — a floating local time is "
        "refused rather than guessed. If the new event clashes with one already on the "
        "calendar, the response is 409 carrying the conflict and the three actions; the "
        "client then posts one of them to the resolve endpoint."
    ),
)
def create_event(request, body: PersonalEventCreateIn):
    """Create a personal event, with its default reminder plan."""
    result = create_personal_event(
        user_id=request.user.pk,
        name=body.name,
        start_utc=body.start_time_utc,
        end_utc=body.end_time_utc,
        start_time_tz=body.start_time_tz,
        location=body.location,
        notes=body.notes,
        actor=_actor(request),
        now=timezone.now(),
    )
    if isinstance(result, ConflictFound):
        raise _conflict_response(result)
    return Status(201, PersonalEventOut.from_snapshot(result.event))


@router.get(
    "/events",
    response={200: PersonalEventListOut},
    summary="List the signed-in user's personal events",
    description="The user's own personal events, soonest first. No one else's are listed.",
)
def list_events(request, filters: PersonalEventListQuery = EVENT_LIST_QUERY):
    """The signed-in user's personal events."""
    return PersonalEventListOut(
        items=[
            PersonalEventOut.from_snapshot(event)
            for event in list_personal_events(
                user_id=request.user.pk,
                starts_after=filters.starts_after,
                starts_before=filters.starts_before,
            )
        ]
    )


@router.get(
    "/events/{event_id}",
    response={200: PersonalEventOut, 404: ErrorOut},
    summary="Get one personal event",
    description=(
        "One of the signed-in user's personal events. An event that is not theirs reads as "
        "not found."
    ),
)
def get_event(request, event_id: UUID):
    """One of the user's own personal events."""
    return PersonalEventOut.from_snapshot(
        get_personal_event(user_id=request.user.pk, event_id=event_id)
    )


@router.patch(
    "/events/{event_id}",
    response={200: PersonalEventOut, 404: ErrorOut, 409: SchedulingConflictOut},
    summary="Edit a personal event",
    description=(
        "Edits a personal event and re-runs conflict detection. A conflicting edit returns "
        "the same 409 payload a conflicting create does."
    ),
)
def edit_event(request, event_id: UUID, body: PersonalEventPatchIn):
    """Edit one of the user's own personal events."""
    result = update_personal_event(
        user_id=request.user.pk,
        event_id=event_id,
        name=body.name,
        start_utc=body.start_time_utc,
        end_utc=body.end_time_utc,
        start_time_tz=body.start_time_tz,
        location=body.location,
        notes=body.notes,
        actor=_actor(request),
        now=timezone.now(),
    )
    if isinstance(result, ConflictFound):
        raise _conflict_response(result)
    return PersonalEventOut.from_snapshot(result.event)


@router.delete(
    "/events/{event_id}",
    response={204: None, 404: ErrorOut},
    summary="Delete a personal event",
    description="Removes one of the signed-in user's personal events.",
)
def remove_event(request, event_id: UUID):
    """Delete one of the user's own personal events."""
    delete_personal_event(
        user_id=request.user.pk,
        event_id=event_id,
        actor=_actor(request),
        now=timezone.now(),
    )
    return Status(204, None)


@router.post(
    "/events/conflicts/{pair_id}/resolve",
    response={200: ConflictResolutionOut, 404: ErrorOut, 422: ErrorOut},
    summary="Answer a conflict prompt",
    description=(
        "Records the user's choice on a conflict prompt. Exactly one of the three actions "
        "the prompt offered is accepted; there is no dismiss. A resolution that is illegal "
        "for this conflict's kind is refused, and the prompt stays open."
    ),
)
def resolve_event_conflict(request, pair_id: UUID, body: ConflictResolutionIn):
    """Record the user's choice on a conflict prompt."""
    resolution = resolve_conflict(
        user_id=request.user.pk,
        pair_id=pair_id,
        resolution=body.resolution,
        new_side_kind=PERSONAL_EVENT_SIDE,
        new_side_id=body.new_side_id,
        actor=_actor(request),
        now=timezone.now(),
    )
    return ConflictResolutionOut(
        pair_id=resolution.pair_id,
        kind=resolution.kind,
        resolution=resolution.resolution,
        status=resolution.status,
        new_side_id=resolution.new_side_id,
        existing_side_id=resolution.existing_side_id,
    )


@router.post(
    "/saved-events/{catalog_event_id}",
    response={200: SavedEventOut, 201: SavedEventOut, 409: SchedulingConflictOut},
    summary="Save a public event",
    description=(
        "Saves a public catalog event onto the signed-in user's own calendar. The save is "
        "idempotent: saving an event that is already saved returns the existing record. The "
        "times in the response are the snapshot taken at save time; `stale` says whether the "
        "catalog has moved past it, in which case re-propagation has been requested. If the "
        "save clashes with a personal event, the response is 409 carrying the conflict and "
        "the three actions."
    ),
)
def save_public_event(request, catalog_event_id: UUID):
    """Save a public catalog event for the signed-in user."""
    result = save_event(
        user_id=request.user.pk,
        event_id=catalog_event_id,
        actor=_actor(request),
        now=timezone.now(),
    )
    if result.conflicts:
        # A conflicting save is a `ConflictFound` in the same shape as a conflicting create:
        # the save row exists, the pair is active, and the flow is waiting for a choice.
        raise SchedulingConflictError(
            details={
                "event_id": str(result.saved.id),
                "conflicts": [
                    ConflictOut.from_detected(conflict).model_dump(mode="json")
                    for conflict in result.conflicts
                ],
            }
        )
    # The display fields come from the catalog; the times come from the snapshot. The read
    # is not bounded by "not started yet": the save already succeeded, and the user's own
    # calendar does not un-save an event because it began.
    public = get_public_event(event_id=catalog_event_id)
    body = SavedEventOut.from_snapshot(
        result.saved,
        public,
        stale=result.stale,
        current_version=result.current_version if result.stale else None,
    )
    # A first save is a creation (201); a repeat is the same record returned again (200).
    return Status(201 if result.created else 200, body)


@router.delete(
    "/saved-events/{catalog_event_id}",
    response={204: None, 404: ErrorOut},
    summary="Unsave a public event",
    description=(
        "Removes one of the signed-in user's saves. The conflict pairs it took part in close "
        "as `cleared_by_state_change` — the pair ended because a side went away, which is "
        "not a user resolution."
    ),
)
def unsave_public_event(request, catalog_event_id: UUID):
    """Remove one of the user's own saves."""
    unsave_event(
        user_id=request.user.pk,
        event_id=catalog_event_id,
        actor=_actor(request),
        now=timezone.now(),
    )
    return Status(204, None)


@router.get(
    "/saved-events",
    response={200: SavedEventListOut},
    summary="List the signed-in user's saved events",
    description=(
        "The user's own saved events, soonest first. The times are the snapshots — what the "
        "user saw when they saved — and the titles and venues are the catalog's current "
        "values. `omitted` counts the saves whose catalog event has since disappeared; they "
        "are not listed, but they are not hidden either."
    ),
)
def list_saved(request, filters: SavedEventListQuery = EVENT_LIST_QUERY):
    """The signed-in user's saved events."""
    items = []
    omitted = 0
    for saved in list_saved_events(
        user_id=request.user.pk,
        starts_after=filters.starts_after,
        starts_before=filters.starts_before,
    ):
        try:
            public = get_public_event(event_id=saved.event_id)
        except EventNotFoundError:
            # The catalog event is gone — superseded or unpublished. There is no title to
            # show, so the save is left out; the count tells the client how many.
            omitted += 1
            continue
        items.append(SavedEventOut.from_snapshot(saved, public))
    return SavedEventListOut(items=items, omitted=omitted)


__all__ = ["router"]
