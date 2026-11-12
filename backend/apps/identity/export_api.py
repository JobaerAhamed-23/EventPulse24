"""The data-export endpoints (FR-52, GDPR Art. 20): ask for it, then fetch the file.

**Two endpoints with two different auth models, on purpose.**

`POST /api/exports` is a signed-in action: the user id comes from the session and never
from a payload, like every other personal surface (AD-12).

`GET /api/exports/{id}/{fmt}` is **not** session-authed, and that is not an oversight. The
link arrives in an email and is followed from a mail client that carries no session —
possibly on a different device, possibly days later. The signed token is the credential,
and it names the export, the user and the format together so none of the three can be
swapped in the URL. Requiring a session here would mean a user who is signed out cannot
collect data they are legally owed, which is the failure this whole item exists to avoid.

**No tier is read anywhere in this file.** See `services/data_export.py` for the reasoning:
Article 20 is a right, and the jurisdiction split the PRD describes would require collecting
location data in order to decide a privacy right.

**The layer is thin.** It resolves the user, calls the published services and projects their
plain data onto the wire — it never imports models and never touches the ORM, which
`test_no_direct_writes.py` enforces.
"""

from uuid import UUID

from django.http import HttpResponse
from django.utils import timezone
from ninja import Router, Schema, Status

from apps.identity.api_auth import current_user
from apps.identity.services.data_export import (
    DataExportNotFoundError,
    get_export,
    request_export,
)
from apps.identity.services.data_export import read_export as read_export_body
from shared.actor import Actor
from shared.errors import ErrorOut

router = Router(tags=["exports"], auth=current_user)

#: The one place the two formats are spelled. A third would need a serializer, not a branch.
FORMATS = ("json", "ics")


class DataExportOut(Schema):
    """One export request, as the settings screen sees it.

    **It carries no download links.** The links live in the email, which is what FR-52
    promises and what keeps a session-authed response from becoming a second way to reach
    a file that is supposed to require the token.
    """

    id: UUID
    status: str
    requested_at: str
    completed_at: str | None
    expires_at: str | None
    due_by: str


def _out(view) -> DataExportOut:
    return DataExportOut(
        id=view.id,
        status=view.status,
        requested_at=view.requested_at.isoformat(),
        completed_at=view.completed_at.isoformat() if view.completed_at else None,
        expires_at=view.expires_at.isoformat() if view.expires_at else None,
        due_by=view.due_by.isoformat(),
    )


@router.post(
    "",
    response={202: DataExportOut},
    summary="Request an export of everything we hold about you",
    description=(
        "Starts building a JSON and an ICS export of this account's data. The links "
        "arrive by email within 24 hours.\n\n"
        "**Available to every signed-in account**, on any tier: data portability is a "
        "right under GDPR Article 20, not a paid feature.\n\n"
        "**Asking twice while one is already building returns the request in flight** "
        "rather than starting a second one, so a double-click costs nothing."
    ),
)
def post_export(request):
    """Request an export, or join the one already running."""
    view = request_export(
        user_id=request.user.pk,
        actor=Actor.user(request.user.pk),
        now=timezone.now(),
    )
    return Status(202, _out(view))


@router.get(
    "/{export_id}",
    response={200: DataExportOut, 404: ErrorOut},
    summary="Check on one of your export requests",
)
def get_export_status(request, export_id: UUID):
    """How far along one of this user's exports is."""
    return _out(get_export(user_id=request.user.pk, export_id=export_id))


@router.get(
    "/{export_id}/{fmt}",
    auth=None,
    response={404: ErrorOut},
    summary="Download an export with its emailed link",
    description=(
        "Returns the export file itself. **Authenticated by the signed token in the "
        "link, not by a session** — the link is followed from a mail client, which has "
        "none.\n\n"
        "The token names the export, the account and the format together, so none of the "
        "three can be changed in the URL. A link is refused once the export expires, "
        "whatever its signature says."
    ),
)
def download_export(request, export_id: UUID, fmt: str, token: str = ""):
    """Stream one export's body to whoever holds a valid link for it."""
    if fmt not in FORMATS:
        raise DataExportNotFoundError(details={"export_id": str(export_id)})

    body = read_export_body(token=token, export_id=export_id, fmt=fmt, now=timezone.now())

    content_type = "application/json" if fmt == "json" else "text/calendar; charset=utf-8"
    response = HttpResponse(body, content_type=content_type)
    # `attachment` so a browser saves the file rather than rendering it: an ICS shown as
    # text is not what the user asked for, and a JSON page is not a download.
    response["Content-Disposition"] = f'attachment; filename="eventpulse24-export.{fmt}"'
    # The link is a credential in a URL. Nothing about this response should be cached by a
    # shared proxy, and nothing should carry the token onward in a Referer.
    response["Cache-Control"] = "no-store, private"
    response["Referrer-Policy"] = "no-referrer"
    return response
