"""The notification settings endpoints — quiet hours, the default plan, and the delivery time.

`GET /api/settings/notifications` reads the signed-in user's settings in one response;
`PUT` saves the ones the request mentions. One router, mounted at `/api/settings` in
`config/api.py`.

**The auth is on the router**, as `personalization`'s and `delivery`'s other routers' is:
`auth=current_user`. The user id comes from the session and **never from a payload**, so
the scoping cannot be talked out of by a request body (AD-12's personal-surface rule).

**The surface spans two modules, and the API hides it.** The Quiet Hours window and the
default Reminder Plan are `delivery`'s; the digest delivery time and the zone are
`personalization`'s. That split is the accepted cost of the 2026-10-31 ownership decision,
and the client makes one call and gets one response — it never learns that the settings
live in two places.

**The write is a patch, and "mentioned" is read from the request itself.** Every field of
the body is optional, and an omitted field means *"leave it alone"*. `quiet_hours` is the
one field where `null` is a value: an omitted `quiet_hours` leaves the window alone and a
`null` one turns quiet hours **off**. The two are told apart by which fields the client
actually sent — Pydantic's `model_fields_set` — and not by a sentinel, so the wire shape
stays honest: `quiet_hours` is nullable because "off" is a legal value.

**Every write re-times the user's pending sends.** AD-7: a preference change *"rewrites
`due_at` on `pending` rows only and never touches the key"*. That is why a user can change
their quiet hours ten times and still receive one reminder. The service does the rewrite;
this layer never touches the ORM.

**The layer is thin.** It resolves the user, calls the published services, and projects the
services' plain data onto the wire shape. It never imports `apps.delivery.models` and never
touches the ORM directly — `apps/*/api.py` are surface files, and the architecture test
`test_no_direct_writes.py` enforces that.
"""

from django.utils import timezone
from ninja import Router

from apps.delivery.schemas import NotificationSettingsIn, NotificationSettingsOut
from apps.delivery.services.preferences import SettingsPatch, apply_settings_patch
from apps.delivery.services.preferences_read import read_notification_settings
from apps.identity.api_auth import current_user
from domain.quiet_hours import QuietHours
from shared.actor import Actor
from shared.errors import ErrorOut

router = Router(tags=["settings"], auth=current_user)


def _actor(request) -> Actor:
    """The acting user, for the audit rows the commands write (AD-5).

    The user id comes from the session, never from the request — the same id the service
    scopes its queries by.
    """
    return Actor.user(request.user.pk)


@router.get(
    "/notifications",
    response={200: NotificationSettingsOut},
    summary="The signed-in user's notification settings",
    description=(
        "The Quiet Hours window, the default Reminder Plan, and the digest delivery time "
        "and zone — **in one response**.\n\n"
        "**The settings live in two places, and you do not have to care.** The window and "
        "the default plan are stored with the delivery service; the delivery time and the "
        "zone are stored with the digest service. This endpoint assembles them so the "
        "settings screen is one call.\n\n"
        "`quiet_hours` is **two local wall clocks** in your own timezone, not instants — "
        "`22:00` to `08:00` is the night wherever you are. It is `null` when you have "
        "turned quiet hours off, and that is the only way to say so.\n\n"
        "`digest.delivery_time` is likewise a **local wall clock** — `09:00` means nine in "
        "the morning where you are — and `digest.timezone` is the IANA zone it is a clock "
        "in."
    ),
)
def get_notification_settings(request):
    """The signed-in user's notification settings, in one response."""
    view = read_notification_settings(user_id=request.user.pk)
    return NotificationSettingsOut.from_view(view)


@router.put(
    "/notifications",
    response={200: NotificationSettingsOut, 422: ErrorOut},
    summary="Save the signed-in user's notification settings",
    description=(
        "Saves the settings the request mentions, and **re-times the pending reminders "
        "and digests in the same transaction** — a setting that does not change what is "
        "already scheduled is a setting that does nothing.\n\n"
        "**This is a patch.** Every field is optional, and an **omitted field is left "
        "alone**: changing your quiet hours does not clear your default plan, and moving "
        "your delivery time does not reset your window. The one field where `null` means "
        "something is `quiet_hours` — **omit it to leave the window alone, send `null` to "
        "turn quiet hours off.**\n\n"
        "**The quiet-hours window is two local wall clocks.** A window that covers the "
        "whole day (the same clock twice) is refused, because that is the absence of a "
        'window rather than a window, and "off" already has one spelling.\n\n'
        "**The default Reminder Plan is 0 to 4 slots**, validated by exactly the same rule "
        "as a per-event plan — the same named reminders, the same custom-reminder "
        'grammar, the same errors. An empty list is valid and means "new reminders start '
        'with none". **Changing it does not change plans that already exist**: it applies '
        "to events saved from now on.\n\n"
        "**The delivery time and the zone are one setting.** A wall clock without its "
        "zone is not a schedule, so they are sent together and are applied together."
    ),
)
def put_notification_settings(request, body: NotificationSettingsIn):
    """Save the settings the request mentions, and re-time what is already scheduled."""
    patch = _patch_from(body)
    apply_settings_patch(
        user_id=request.user.pk,
        patch=patch,
        actor=_actor(request),
        now=timezone.now(),
    )
    view = read_notification_settings(user_id=request.user.pk)
    return NotificationSettingsOut.from_view(view)


def _patch_from(body: NotificationSettingsIn) -> SettingsPatch:
    """The request body as a patch — **reading which fields the client actually sent**.

    **Presence is the whole distinction.** `model_fields_set` is the set of fields the
    request mentioned, so:

    - `quiet_hours` **not mentioned** → leave the window alone;
    - `quiet_hours` mentioned and `null` → turn quiet hours **off**;
    - `quiet_hours` mentioned with a window → set that window.

    The alternative — a sentinel for "unset" — would put a fake value in the schema and a
    fake branch in the OpenAPI contract, and a client generated from it would have to know
    about a value that does not exist in the product.

    **`default_reminder_slots` is a list, and an empty list is not `None`.** An omitted
    field leaves the default alone; an empty list sets it to "no reminders by default".
    Those are different states, and the wire distinguishes them without a sentinel.
    """
    mentioned = body.model_fields_set

    quiet_hours: QuietHours | None = None
    clear_quiet_hours = False
    if "quiet_hours" in mentioned:
        window = body.quiet_hours
        if window is None:
            clear_quiet_hours = True
        else:
            quiet_hours = QuietHours(start=window.start, end=window.end)

    default_slots = body.default_reminder_slots if "default_reminder_slots" in mentioned else None

    delivery_time = None
    timezone_name = None
    if body.digest is not None:
        delivery_time = body.digest.delivery_time
        timezone_name = body.digest.timezone

    return SettingsPatch(
        quiet_hours=quiet_hours,
        clear_quiet_hours=clear_quiet_hours,
        default_reminder_slots=None if default_slots is None else tuple(default_slots),
        delivery_time=delivery_time,
        timezone=timezone_name,
    )


__all__ = ["router"]
