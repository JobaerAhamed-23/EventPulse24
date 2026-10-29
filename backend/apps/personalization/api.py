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

from apps.identity.api_auth import current_user
from apps.ingestion.services.catalog_read import EventNotFoundError, get_public_event
from apps.personalization.schemas import (
    ConflictOut,
    ConflictResolutionIn,
    ConflictResolutionOut,
    DigestPreferenceIn,
    InterestChipOut,
    InterestChipsOut,
    InterestsIn,
    InterestsOut,
    OnboardingStateOut,
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
from apps.personalization.services.onboarding import (
    advance_step,
    get_onboarding_state,
    list_interest_chips,
    set_digest_preference,
    set_interests,
    skip_all,
    skip_step,
)
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


# ─────────────────────────────────────────────────────────────────────────────
# The onboarding flow (FR-1)
#
# Seven endpoints under `/api/personal/onboarding`. They share the router's
# `auth=current_user`, so every one is authed, and **none of them accepts a user id as
# input** — the scoping comes from the session and cannot be talked out of by a payload.
#
# `PUT` for the two setters, because they **replace** a resource — that is what `PUT`
# means, and `POST` would imply a create. `POST` for the three step movers, because they
# are transitions, not idempotent replacements of a body.
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/onboarding",
    response={200: OnboardingStateOut},
    summary="The signed-in user's onboarding state",
    description=(
        "Where the user is in the 3-step onboarding flow, their interest picks and their "
        "digest delivery preference. A user who left mid-step is resumed at the same step "
        "within 7 days; after that the flow restarts at step 1. A user who has finished "
        "onboarding is never sent back into it."
    ),
)
def read_onboarding(request):
    """The signed-in user's whole onboarding state."""
    state = get_onboarding_state(user_id=request.user.pk, now=timezone.now())
    return OnboardingStateOut.from_state(state)


@router.get(
    "/onboarding/interest-chips",
    response={200: InterestChipsOut},
    summary="The interest chips on offer",
    description=(
        "The ten interest chips, in the order the flow shows them. This list comes from "
        "the server, so the frontend holds no second copy of it. Each chip carries a "
        "stable `key` and a display `label` — send the key back, not the label."
    ),
)
def read_interest_chips(request):
    """The ten interest chips, from the server's constant."""
    return InterestChipsOut(
        items=[InterestChipOut(key=chip.key, label=chip.label) for chip in list_interest_chips()]
    )


@router.put(
    "/onboarding/interests",
    response={200: InterestsOut, 422: ErrorOut},
    summary="Set the user's interest picks",
    description=(
        "Replaces the user's interest picks with the given set. At most 3 chips may be "
        "picked, and every key must be one the chips endpoint offers. An empty list is "
        "valid — that is how the step is skipped, and it clears the set."
    ),
)
def put_interests(request, body: InterestsIn):
    """Replace the user's interest picks."""
    state = set_interests(
        user_id=request.user.pk,
        chip_keys=body.chip_keys,
        actor=_actor(request),
        now=timezone.now(),
    )
    return InterestsOut(chip_keys=list(state.interests))


@router.put(
    "/onboarding/digest-preference",
    response={200: OnboardingStateOut, 422: ErrorOut},
    summary="Set the digest delivery time and timezone",
    description=(
        "Sets when and where the Pulse Digest should arrive. The delivery time is a "
        "local wall clock, so it means nine in the morning where the user is. The "
        "timezone must be an IANA zone name."
    ),
)
def put_digest_preference(request, body: DigestPreferenceIn):
    """Set the digest delivery time and timezone."""
    state = set_digest_preference(
        user_id=request.user.pk,
        delivery_time=body.delivery_time,
        timezone_name=body.timezone,
        actor=_actor(request),
        now=timezone.now(),
    )
    return OnboardingStateOut.from_state(state)


@router.post(
    "/onboarding/step",
    response={200: OnboardingStateOut, 409: ErrorOut},
    summary="Advance to the next onboarding step",
    description=(
        "Moves the user to the next step. Advancing past the last step finishes the "
        "onboarding — there is no fourth step. A user who has already finished is not "
        "moved again."
    ),
)
def post_advance_step(request):
    """Advance to the next onboarding step."""
    state = advance_step(
        user_id=request.user.pk,
        actor=_actor(request),
        now=timezone.now(),
    )
    return OnboardingStateOut.from_state(state)


@router.post(
    "/onboarding/step/skip",
    response={200: OnboardingStateOut, 409: ErrorOut},
    summary="Skip the current onboarding step",
    description=(
        "Skips the current step. No step requires any input, so every one of them can be "
        "skipped. Skipping the interests step clears the picks; skipping the digest step "
        "writes the default delivery preference. Skipping the last step finishes the "
        "onboarding."
    ),
)
def post_skip_step(request):
    """Skip the current onboarding step."""
    state = skip_step(
        user_id=request.user.pk,
        actor=_actor(request),
        now=timezone.now(),
    )
    return OnboardingStateOut.from_state(state)


@router.post(
    "/onboarding/skip-all",
    response={200: OnboardingStateOut, 409: ErrorOut},
    summary="Skip the whole onboarding flow",
    description=(
        "Skips every step and finishes the onboarding. A user who skips everything has "
        "still finished onboarding — the default digest preference is written, so the "
        "digest has a delivery time to work with."
    ),
)
def post_skip_all(request):
    """Skip the whole onboarding flow."""
    state = skip_all(
        user_id=request.user.pk,
        actor=_actor(request),
        now=timezone.now(),
    )
    return OnboardingStateOut.from_state(state)


__all__ = ["router"]
