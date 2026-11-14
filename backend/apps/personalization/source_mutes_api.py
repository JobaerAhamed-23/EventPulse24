"""The source-visibility endpoints (FR-13, FR-16): the screen behind `Settings → Sources`.

`GET /api/settings/sources` lists the registry, grouped and with each source's trust and
the caller's mute state. `PUT /api/settings/sources/{source_id}` sets one source's state.
`POST /api/settings/sources/restore-defaults` clears every one of them.

**The auth is on the router**, as `personalization`'s other routers' is: `auth=current_user`.
The user id comes from the session and **never from a payload**, so the scoping cannot be
talked out of by a request body (AD-12's personal-surface rule).

**The layer is thin.** It resolves the user, calls the published services, and projects
the services' plain data onto the wire shape. It never imports `apps.personalization.models`
and never touches the ORM directly — `apps/*_api.py` are surface files, and the
architecture test `test_no_direct_writes.py` enforces that.

**The registry comes from `ingestion` and the user's state comes from `personalization`,
and the client never learns that.** The source list is the catalog's — `ingestion` owns
`Source` and publishes the read — while the mute is the user's. This endpoint joins them
into one response, which is what the screen needs and what the client should have to
make one call.

**"Restore all defaults" is confirmed by the client, not here.** The endpoint is a single
idempotent bulk delete. §10.4's bulk-action safeguard is that the destructive action is
confirmed *before it completes*, and the screen asks before it calls this. A confirmation
the server owned would have to survive a page refresh, which is a state machine to buy a
dialog.

**A mute for a source that is not in the registry is accepted, not a 404.** The id in the
path names a `catalog` row, and this layer may not read `catalog` in a write transaction
(AD-3) — so the endpoint cannot check, and the service deliberately does not either: a
mute for a source that has since been removed excludes nothing and is purged with the
user's data. So the answer is a 200 with the state recorded, and the declared `404` is
gone rather than left as a promise the code does not keep. A contract that says 404 and
answers 200 is worse than one that says 200, because the first teaches the client to
expect a failure that never comes.

**`restore-defaults` is declared before `{source_id}`, and the order is load-bearing.**
Django resolves the URL patterns in registration order, and the first pattern to match the
*path* wins — then the method is checked against it. So a `PUT /sources/{source_id}`
registered first would swallow `POST /sources/restore-defaults` as a `PUT` against a
`source_id` of `"restore-defaults"`, and the answer would be a **405**, not a 404. The
literal path has to come first. (`tests/personalization/test_source_mutes_api.py` asserts
both endpoints answer, which is what catches this.)
"""

from uuid import UUID

from django.utils import timezone
from ninja import Router

from apps.identity.api_auth import current_user
from apps.ingestion.services.source_registry_read import read_source_registry
from apps.personalization.schemas import (
    SourceGroupOut,
    SourceListOut,
    SourceMuteResultOut,
    SourceMuteSetIn,
    SourceOut,
    SourceRestoreDefaultsOut,
    SourceTrustOut,
)
from apps.personalization.services.source_mutes import (
    STATE_DEFAULT,
    read_source_states,
    restore_source_defaults,
    set_source_mute,
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
    "/sources",
    response={200: SourceListOut, 401: ErrorOut},
    summary="The source registry, grouped, with the caller's visibility settings",
    description=(
        "Every source in the registry, grouped by how its facts were obtained — "
        "Official, Community, Aggregator, Crawled — with each source's trust and the "
        "caller's mute state.\n\n"
        "**The groups are the Source Badge types.** The server names the type; the "
        "client owns the label and the glyph.\n\n"
        "**A muted source is still listed.** The screen's job is transparency — the user "
        "is told what is informing their timeline *and* what they have turned off. A "
        "muted source that disappeared would be a preference they could not see or undo."
    ),
)
def list_sources(request) -> SourceListOut:
    """The registry and the caller's state on it, in one response."""
    user_id = request.user.pk
    states = read_source_states(user_id=user_id)

    groups: list[SourceGroupOut] = []
    for group in read_source_registry():
        groups.append(
            SourceGroupOut(
                badge=group.badge,
                label=group.label,
                sources=[
                    SourceOut(
                        id=source.id,
                        name=source.name,
                        source_badge=source.source_badge,
                        city=source.city,
                        trust=SourceTrustOut(band=source.trust_band, score=source.reliability),
                        mute_state=states.get(source.id, STATE_DEFAULT),
                        is_paused=source.is_paused,
                    )
                    for source in group.sources
                ],
            )
        )
    return SourceListOut(groups=groups)


@router.post(
    "/sources/restore-defaults",
    response={200: SourceRestoreDefaultsOut, 401: ErrorOut, 403: ErrorOut},
    summary="Clear every custom visibility setting",
    description=(
        "Reset every source to its default visibility, clearing both the mutes and the "
        '"show less" preferences in one action.\n\n'
        "**The screen asks before it calls this.** The endpoint is a single idempotent "
        "delete; the confirmation belongs to the client, because the safeguard is that "
        "the destructive action is confirmed before it completes."
    ),
)
def restore_defaults(request) -> SourceRestoreDefaultsOut:
    """Clear every custom visibility setting for the signed-in user."""
    removed = restore_source_defaults(
        user_id=request.user.pk,
        actor=_actor(request),
        now=timezone.now(),
    )
    return SourceRestoreDefaultsOut(removed=removed)


@router.put(
    "/sources/{source_id}",
    response={
        200: SourceMuteResultOut,
        401: ErrorOut,
        403: ErrorOut,
        422: ErrorOut,
    },
    summary="Set one source's visibility",
    description=(
        "Set one source's state to `mute`, `show_less` or `default`.\n\n"
        "**`mute` excludes the source's events** — they are not shown at all. "
        "**`show_less` deprioritises them** — they are still shown, but ordered lower. "
        "**`default` restores the source** to how it was before any preference.\n\n"
        "The state is idempotent: setting a source to the state it already has is a "
        "success, and `changed` says whether anything actually moved.\n\n"
        "**There is no 404.** The endpoint does not read the catalog (AD-3), so a source "
        "that is not in the registry is accepted like any other: the preference excludes "
        "nothing and is purged with the user's data."
    ),
)
def set_source_mute_state(
    request,
    source_id: UUID,
    payload: SourceMuteSetIn,
) -> SourceMuteResultOut:
    """Set one source's visibility state for the signed-in user."""
    result = set_source_mute(
        user_id=request.user.pk,
        source_id=source_id,
        state=payload.state,
        actor=_actor(request),
        now=timezone.now(),
    )
    return SourceMuteResultOut(
        source_id=result.source_id,
        state=result.state,
        changed=result.changed,
    )
