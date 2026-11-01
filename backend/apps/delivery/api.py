"""The Reminder Plan endpoints (FR-9, AD-7, AD-16, AD-19).

`GET /api/reminders/{target_kind}/{target_id}` reads one event's plan; `PUT` saves it.
Two endpoints on one router, mounted at `/api/reminders` in `config/api.py`.

**The auth is on the router**, as `personalization`'s is: `auth=current_user`. The user id
comes from the session and **never from a payload**, so the scoping cannot be talked out
of by a request body (AD-12's personal-surface rule).

**The layer is thin.** It resolves the user, resolves the target, calls the published
service, and projects the service's plain data onto the wire shape. It never imports
`apps.delivery.models` and never touches the ORM directly — `apps/*/api.py` are surface
files, and the architecture test `test_no_direct_writes.py` enforces that.

**The kind is in the path, not the body.** A `PUT` replaces the plan at a *resource*, and
the resource is `(kind, id)` — so the URL names it. The kind is `ReminderPlan.TargetKind`'s
vocabulary (`personal_event`, `saved_event`), which is **not** `ScheduledSend.Kind`'s: a
send's kind says whether the row is a digest or a reminder, while a plan's kind says which
side of the user's calendar the plan belongs to. `delivery_messages._facts_for` already
tabulates the two.

**A target that does not exist, is not the caller's, or is of the other kind is a 404.**
Not a 403: a 403 would confirm that the record exists, so the endpoint could be used to
probe for other users' event ids. The response uses the shared `{code, message}` envelope
`catalog` uses, so the client has one error shape across the whole API.
"""

from uuid import UUID

from django.utils import timezone
from ninja import Router

from apps.delivery.schemas import ReminderPlanIn, ReminderPlanOut
from apps.delivery.services.reminder_plan_read import (
    ReminderTargetNotFoundError,
    read_plan,
    read_plan_for,
    resolve_target,
)
from apps.delivery.services.reminder_plans import save_plan_slots
from apps.identity.api_auth import current_user
from domain.errors import NotFoundError
from shared.actor import Actor
from shared.errors import ErrorOut

router = Router(tags=["reminders"], auth=current_user)

#: The endpoint's own not-found error. The message says nothing about what exists — a 404
#: must not confirm that another user's event is there (no existence leak).
_NOT_FOUND_MESSAGE = "We couldn't find that event."


def _actor(request) -> Actor:
    """The acting user, for the audit row the command writes (AD-5).

    The user id comes from the session, never from the request — the same id the service
    scopes its queries by.
    """
    return Actor.user(request.user.pk)


def _not_found() -> NotFoundError:
    """The shared 404, with the `{code, message}` envelope the whole API uses."""
    return NotFoundError(_NOT_FOUND_MESSAGE)


@router.get(
    "/{target_kind}/{target_id}",
    response={200: ReminderPlanOut, 404: ErrorOut},
    summary="One event's Reminder Plan, with each slot's delivery time",
    description=(
        "The signed-in user's Reminder Plan for one event, and for each slot the instant "
        "its reminder will **actually** go out.\n\n"
        "**The delivery time is the server's answer, not the client's arithmetic.** It is "
        "the post-Quiet-Hours instant — already deferred, if the slot would have fallen "
        "inside the user's quiet window — so the picker can dim that chip and show "
        '*"Will deliver at 8:00 am Saturday"* without reimplementing the shift (where '
        "DST and midnight-crossing would be rediscovered and got wrong differently). "
        "`deferred` says whether the shift moved it, and `deferred_to` is the quiet "
        "window's end when it did.\n\n"
        "`target_kind` is `personal_event` or `saved_event`. A target that does not exist, "
        "is not yours, or is of the other kind is a **404** — never a 403, which would "
        "confirm that the record exists."
    ),
)
def get_plan(request, target_kind: str, target_id: UUID):
    """The signed-in user's plan for one event, with the computed delivery times."""
    try:
        view = read_plan(user_id=request.user.pk, target_kind=target_kind, target_id=target_id)
    except ReminderTargetNotFoundError:
        raise _not_found() from None
    return ReminderPlanOut.from_view(view)


@router.put(
    "/{target_kind}/{target_id}",
    response={200: ReminderPlanOut, 404: ErrorOut},
    summary="Save one event's Reminder Plan",
    description=(
        "Replaces the signed-in user's Reminder Plan for one event with the given slots, "
        "and **reschedules the event's pending reminders in the same transaction** — a "
        "plan saved without its sends changing is a plan that does nothing.\n\n"
        "**0 to 4 slots**, and at most one custom slot. **An empty list is a valid save** "
        "and not a delete: it means 'no reminders, but I still see this event in the "
        "digest'. The plan row survives, so 'the user chose no reminders' stays "
        "distinguishable from 'the user never configured a plan'.\n\n"
        "**A custom slot's id carries its offset**: `custom:90` is 90 minutes before the "
        "event. The bound is **15 minutes to 30 days** before the event — an offset "
        "outside that range is refused.\n\n"
        "The response is the saved plan, with each slot's computed delivery time, exactly "
        "as the `GET` returns it. A target that does not exist, is not yours, or is of the "
        "other kind is a **404** — never a 403, which would confirm that the record "
        "exists."
    ),
)
def put_plan(request, target_kind: str, target_id: UUID, body: ReminderPlanIn):
    """Save the plan, and reschedule its sends with it."""
    try:
        target = resolve_target(
            user_id=request.user.pk, target_kind=target_kind, target_id=target_id
        )
    except ReminderTargetNotFoundError:
        raise _not_found() from None

    save_plan_slots(
        user_id=request.user.pk,
        target_kind=target_kind,
        target_id=target_id,
        slots=tuple(body.slots),
        actor=_actor(request),
        now=timezone.now(),
        send_target=target,
    )

    # The saved plan is read back through the same published read the `GET` uses, so the
    # response carries the same delivery times the next `GET` would — and the write and
    # the read cannot disagree about what was saved. The **target is not resolved a second
    # time**: it was resolved above, and re-resolving it would re-read the event, the
    # preference and the zone for facts this request already has.
    view = read_plan_for(
        user_id=request.user.pk,
        target_kind=target_kind,
        target_id=target_id,
        target=target,
    )
    return ReminderPlanOut.from_view(view)
