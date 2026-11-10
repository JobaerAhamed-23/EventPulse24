"""The state-change notice endpoints (FR-54, FR-55, AD-16, AD-19).

`GET /api/notices` reads the signed-in user's open notices — the digest strip's data.
`POST /api/notices/{notice_id}/dismiss` closes one. `PUT`/`DELETE
/api/notices/events/{event_id}/mute` set and clear FR-55's per-event mute.

**The auth is on the router**, as `apps/delivery/api.py`'s is: `auth=current_user`. The user
id comes from the session and **never from a payload**, so the scoping cannot be talked out
of by a request body (AD-12's personal-surface rule).

**The layer is thin.** It resolves the user, calls the published service, and projects the
service's plain data onto the wire shape. It never imports `apps.delivery.models` and never
touches the ORM directly — `apps/*/api.py` are surface files, and the architecture test
`test_no_direct_writes.py` enforces that.

**Why a router of its own, and not a third handler on `/api/reminders`.** The mount path is
public contract: `frontend/lib/api/openapi.json` and `frontend/lib/api/schema.ts` are
generated from it and committed, and `tests/api/test_contract.py` fails on any drift. So a
path has to name the thing it serves. `/api/reminders` names **Reminder Plans** — a plan has
slots, and its path shape is `/{target_kind}/{target_id}`. A state-change notice is not a
plan, and an FR-55 mute is not a plan either; hanging them off that router would make
`/api/reminders/<uuid>` mean two different things depending on which handler matched.
`delivery` already has three routers (`api.py`, `preferences_api.py`, `email_api.py`), and a
fourth follows that pattern exactly.

**The mute is a state, so it is `PUT` and `DELETE`.** Setting a state is `PUT`; clearing it
is `DELETE`; there is no request body at all, so the client cannot encode "clear this" as a
field that could be confused with "leave it alone". `apps/personalization/api.py`'s
`DELETE /api/personal/events/{id}` is the same idiom.

**The dismiss is a `POST`, not a `DELETE`.** The notice row is **not** deleted — FR-54's
"never repeats" and the daily cap both depend on the row surviving — and `dismiss_notice`
sets `dismissed_at` rather than deleting. A `DELETE` that does not delete is a lie in the
method, so the path names the act.

**A notice that is not the caller's is a 404.** Not a 403: a 403 would confirm that the
record exists, so the endpoint could be used to probe for other users' notice ids. The same
404 answers "there is no such notice", so the two are indistinguishable (no existence leak).

**This router declares `401` and `403`, and the sibling routers do not.** `401` is the
anonymous refusal and `403` is the CSRF refusal (`csrf_failed`), and both are reachable on
every endpoint here — `identity`'s `current_user` resolver answers the first with a 401 and
raises the second. `apps/identity/api.py` declares `403: ErrorOut` on its own endpoints for
exactly this reason. The other app routers (`/api/reminders`, `apps/personalization/api.py`)
declare neither, which means a generated client cannot type a response the server actually
gives. **Declaring them here is deliberate**: the frontend needs to branch on "sign in"
(a 401) against "fetch a fresh token and retry" (a `csrf_failed` 403), and it can only do
that if the contract says both are possible.

**Dismissing an already-dismissed notice is a success**, not an error — and the response says
`changed: false`, because nothing changed. See `NoticeDismissOut`.
"""

from uuid import UUID

from django.utils import timezone
from ninja import Router

from apps.delivery.schemas import (
    EventMuteOut,
    NoticeDismissOut,
    NoticeListOut,
    NoticeOut,
)
from apps.delivery.services.mutes import mute_event_notices, unmute_event_notices
from apps.delivery.services.notice_state import summarize_notice
from apps.delivery.services.state_notices import (
    dismiss_notice,
    list_undismissed_notices,
    notice_belongs_to_user,
)
from apps.identity.api_auth import current_user
from domain.errors import NotFoundError
from shared.actor import Actor
from shared.constants import NOTICE_STRIP_LIMIT
from shared.errors import ErrorOut

router = Router(tags=["notices"], auth=current_user)

#: The endpoint's own not-found error. The message says nothing about what exists — a 404
#: must not confirm that another user's notice is there (no existence leak).
_NOT_FOUND_MESSAGE = "We couldn't find that notice."


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
    "",
    response={200: NoticeListOut, 401: ErrorOut, 403: ErrorOut},
    summary="The signed-in user's open state-change notices",
    description=(
        "The notices the user has not dismissed, newest first — the data behind the "
        "digest home's strip.\n\n"
        "**A few, not a history.** The list is bounded by the server: FR-54 promises one "
        "calm correction, not a notification centre, and there is no inbox to page "
        "through. An empty list is the common case — most users, most days, have nothing "
        "to correct.\n\n"
        "**A notice is here until it is dismissed.** Being shown a notice is not the same "
        "as acting on it, so the strip is a queue: it empties when the user closes an item, "
        "not when it renders.\n\n"
        "**This says nothing about the event.** A notice names the change and the event it "
        "is about; it does not say the event is cancelled, moved, or off. The client "
        "renders the correction; the event's own page carries its facts."
    ),
)
def get_notices(request):
    """The signed-in user's open notices, newest first."""
    rows = list_undismissed_notices(user_id=request.user.pk, limit=NOTICE_STRIP_LIMIT)
    return NoticeListOut(items=[NoticeOut.from_summary(summarize_notice(row)) for row in rows])


@router.post(
    "/{notice_id}/dismiss",
    response={200: NoticeDismissOut, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut},
    summary="Dismiss one state-change notice",
    description=(
        "Closes one notice: it leaves the strip, and it never comes back. This is a real "
        "write, not client state — dismissal is what makes FR-54's \"one-time, never "
        'repeats" true.\n\n'
        "**The notice row survives.** It is closed, not deleted, so the daily cap and the "
        "never-repeat rule still hold against it.\n\n"
        "**Dismissing an already-dismissed notice is a success**, and the response says "
        "`changed: false` — nothing moved, and the client need not redraw.\n\n"
        "**A notice that is not yours, or that does not exist, is a 404** — the same 404 "
        "for both, so the endpoint cannot be used to find out whether a given id exists."
    ),
)
def post_dismiss_notice(request, notice_id: UUID):
    """Close one notice's strip entry. Idempotent."""
    changed = dismiss_notice(
        user_id=request.user.pk,
        notice_id=notice_id,
        actor=_actor(request),
        now=timezone.now(),
    )
    if not changed and not notice_belongs_to_user(user_id=request.user.pk, notice_id=notice_id):
        # Not the caller's, or no such notice — **the same answer for both**, so this
        # endpoint is not an existence oracle over notice ids.
        raise _not_found() from None
    return NoticeDismissOut(id=notice_id, dismissed=True, changed=changed)


@router.put(
    "/events/{event_id}/mute",
    response={200: EventMuteOut, 401: ErrorOut, 403: ErrorOut},
    summary="Silence the state-change notices for one event",
    description=(
        'Mutes FR-54\'s notices for one event: the "this changed" message stops.\n\n'
        "**A mute silences the correction, not the event.** Reminders still fire on the "
        "user's Reminder Plan and the event still places in the Pulse Digest. There is no "
        "global off switch — a per-event mute is a judgement about the one event the user "
        "is looking at.\n\n"
        "**A cancellation is still raised.** A cancelled or superseded event is announced "
        "even when muted, because the mute has already removed it from the digest and "
        "silence about it would have no second channel to catch it.\n\n"
        "**Muting an already-muted event is a success**, and the response says "
        "`changed: false` — nothing moved.\n\n"
        "**No existence check on the event.** A mute for an event that has since gone is "
        "harmless, and refusing it would make the mute fail in exactly the case a user most "
        "wants it."
    ),
)
def put_event_mute(request, event_id: UUID):
    """Mute one event's notices. Idempotent."""
    result = mute_event_notices(
        user_id=request.user.pk,
        event_id=event_id,
        actor=_actor(request),
        now=timezone.now(),
    )
    return EventMuteOut(event_id=result.event_id, muted=result.muted, changed=result.changed)


@router.delete(
    "/events/{event_id}/mute",
    response={200: EventMuteOut, 401: ErrorOut, 403: ErrorOut},
    summary="Let one event's state-change notices through again",
    description=(
        'Clears the mute on one event, so its "this changed" messages come back.\n\n'
        "**Unmuting does not replay what was silenced.** The notices suppressed while the "
        "mute was on are gone, and raising them now would deliver a correction about a "
        "change the user has had days to notice. The event's current state is on its Detail "
        "screen, which is where a user who just unmuted is standing.\n\n"
        "**Unmuting an event that is not muted is a success**, and the response says "
        "`changed: false`."
    ),
)
def delete_event_mute(request, event_id: UUID):
    """Unmute one event's notices. Idempotent."""
    result = unmute_event_notices(
        user_id=request.user.pk,
        event_id=event_id,
        actor=_actor(request),
        now=timezone.now(),
    )
    return EventMuteOut(event_id=result.event_id, muted=result.muted, changed=result.changed)
