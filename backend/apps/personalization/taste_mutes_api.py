"""The category-mute endpoints (FR-25): the screen behind `Settings → Taste`.

`GET /api/settings/taste` lists the caller's active category mutes.
`PUT /api/settings/taste/mutes` sets one. `DELETE /api/settings/taste/mutes/{category_key}`
unmutes it — one tap. `POST /api/settings/taste/mutes/restore-defaults` clears them all.

**The auth is on the router**, as `personalization`'s other routers' is: `auth=current_user`.
The user id comes from the session and **never from a payload**, so the scoping cannot be
talked out of by a request body (AD-12's personal-surface rule).

**The layer is thin.** It resolves the user, calls the published services, and projects
the services' plain data onto the wire shape. It never imports `apps.personalization.models`
and never touches the ORM directly — `apps/*_api.py` are surface files, and the
architecture test `test_no_direct_writes.py` enforces that.

**The category key is the server's vocabulary.** The label the user reads comes from
`shared.constants.INTEREST_CHIPS` and is published in the response, so the client never
has to own a category list and can never show a category the server does not recognise.
An unknown key is a **422** — the service raises `UnknownCategoryError`, and this layer
maps it to the wire.

**The mockup's reversal surface is `Settings → Taste`, not `Settings → Sources`.** The
two screens are siblings under one settings nav, not one control: the sources screen
mutes *sources*, and this one mutes *categories*. Coupling them would build a control
that cannot express the other.

**`restore-defaults` is declared before `{category_key}`, and the order is load-bearing.**
Django resolves the URL patterns in registration order, and the first pattern to match the
*path* wins — then the method is checked against it. So a `DELETE /mutes/{category_key}`
registered first would swallow `POST /mutes/restore-defaults` as a `DELETE` against a
`category_key` of `"restore-defaults"`, and the answer would be a **405**, not a 404. The
literal path has to come first. (`tests/personalization/test_taste_mutes_api.py` asserts
both endpoints answer, which is what catches this.)
"""

from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from apps.identity.api_auth import current_user
from apps.personalization.schemas import (
    CategoryMuteIn,
    CategoryMuteListOut,
    CategoryMuteOut,
    CategoryMuteRestoreDefaultsOut,
    CategoryMuteResultOut,
)
from apps.personalization.services.taste_mutes import (
    UnknownCategoryError,
    UnknownDurationError,
    clear_all_category_mutes,
    clear_category_mute,
    read_active_mutes,
    set_category_mute,
)
from shared.actor import Actor
from shared.errors import ErrorOut

router = Router(tags=["settings"], auth=current_user)


def _actor(request) -> Actor:
    """The acting user, for the audit rows the commands write (AD-5).

    The id comes from the session, never from the request — the same id the services
    scope their queries by.
    """
    return Actor.user(request.user.pk)


@router.get(
    "/taste",
    response={200: CategoryMuteListOut, 401: ErrorOut},
    summary="The caller's muted categories",
    description=(
        "Every category the caller has muted, with the server's label for each and when "
        "the mute ends.\n\n"
        "**A null `expires_at` means the mute is indefinite** — the mockup's \"until I "
        'change it".\n\n'
        "**An expired mute is not in the list.** The row is still there — it is the "
        "caller's data — but it no longer mutes anything."
    ),
)
def list_category_mutes(request) -> CategoryMuteListOut:
    """The signed-in user's active category mutes."""
    mutes = read_active_mutes(user_id=request.user.pk, now=timezone.now())
    return CategoryMuteListOut(
        mutes=[
            CategoryMuteOut(
                category_key=mute.category_key,
                label=mute.label,
                expires_at=mute.expires_at,
                is_indefinite=mute.is_indefinite,
            )
            for mute in mutes
        ]
    )


@router.post(
    "/taste/mutes/restore-defaults",
    response={200: CategoryMuteRestoreDefaultsOut, 401: ErrorOut, 403: ErrorOut},
    summary="Clear every muted category",
    description=(
        "Clear every category mute in one action.\n\n"
        "**The screen asks before it calls this.** The endpoint is a single idempotent "
        "delete; the confirmation belongs to the client, because the safeguard is that "
        "the destructive action is confirmed before it completes."
    ),
)
def restore_defaults(request) -> CategoryMuteRestoreDefaultsOut:
    """Clear every category mute for the signed-in user."""
    removed = clear_all_category_mutes(
        user_id=request.user.pk,
        actor=_actor(request),
        now=timezone.now(),
    )
    return CategoryMuteRestoreDefaultsOut(removed=removed)


@router.put(
    "/taste/mutes",
    response={
        200: CategoryMuteResultOut,
        401: ErrorOut,
        403: ErrorOut,
        422: ErrorOut,
    },
    summary="Mute one category",
    description=(
        "Mute one category for the caller, for 7, 30 or 90 days — or indefinitely, by "
        "sending a null `duration_days`.\n\n"
        "**The duration set is closed.** A mute that outlived the caller's patience by a "
        "typo is a mute they have to find a screen to undo, so anything else is a 422.\n\n"
        "**The mute is idempotent.** Setting a mute that is already set is a success, and "
        "`changed` says whether the expiry actually moved.\n\n"
        "**The expiry runs from now, not from the mute's creation.** Asking for 30 days "
        "again refreshes the window, which is what pressing the button again means."
    ),
)
def put_category_mute(request, payload: CategoryMuteIn) -> CategoryMuteResultOut:
    """Set one category mute for the signed-in user."""
    try:
        result = set_category_mute(
            user_id=request.user.pk,
            category_key=payload.category_key,
            duration_days=payload.duration_days,
            actor=_actor(request),
            now=timezone.now(),
        )
    except UnknownCategoryError as error:
        raise HttpError(422, str(error)) from error
    except UnknownDurationError as error:
        raise HttpError(422, str(error)) from error
    return CategoryMuteResultOut(
        category_key=result.category_key,
        expires_at=result.expires_at,
        changed=result.changed,
    )


@router.delete(
    "/taste/mutes/{category_key}",
    response={200: CategoryMuteResultOut, 401: ErrorOut, 403: ErrorOut, 422: ErrorOut},
    summary="Unmute one category",
    description=(
        "Unmute one category. One tap, and the row is gone.\n\n"
        "**Unmuting does not resurrect the muted events.** The events that were excluded "
        "from a digest are excluded from the digests they were excluded from; the next "
        "digest is composed from the current candidate pool. A caller who unmutes is "
        "asking for the category back *from now on*."
    ),
)
def delete_category_mute(request, category_key: str) -> CategoryMuteResultOut:
    """Remove one category mute for the signed-in user."""
    try:
        result = clear_category_mute(
            user_id=request.user.pk,
            category_key=category_key,
            actor=_actor(request),
            now=timezone.now(),
        )
    except UnknownCategoryError as error:
        raise HttpError(422, str(error)) from error
    return CategoryMuteResultOut(
        category_key=result.category_key,
        expires_at=result.expires_at,
        changed=result.changed,
    )
