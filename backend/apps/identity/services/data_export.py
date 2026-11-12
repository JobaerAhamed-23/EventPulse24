"""The export commands (FR-52, GDPR Art. 20): ask for your data, build it, fetch it.

**It is not gated on tier, and that was a decision, not an omission.** FR-52's own text
concedes the tension — *"export is free for GDPR compliance but UX is in Pro settings for
non-EU users"* — and the PRD's §11.5 table resolves it by jurisdiction: free in EU/UK/CA/BR/AU,
Pro elsewhere. That resolution needs each user's country, which this product deliberately
does not store, so implementing it would mean **collecting location data in order to decide
a privacy right** and denying the right whenever the guess was wrong. Article 20 is a right;
a right behind $4.99/month is a right the product is failing for the people it is owed to.
So any signed-in user may ask, and no tier is read anywhere in this module.

**A second request joins the first rather than queueing a second job.** The partial unique
constraint `data_export_one_in_flight_per_user_uq` makes that a database fact, so the
"requesting twice" case is not a race the command layer has to win — it is a row that
already exists. The claim column is the same idiom `DigestPreference.digest_claimed_at` and
`Source.reliability_claimed_at` use.

**A download link is a signed token *and* a row that is still alive.** Either alone is not
enough: a signature with a `max_age` cannot be revoked, and a row with no signature could be
fetched by anyone who guessed a UUID. Both are checked, and the row is checked second
because it is the one an account deletion will later set.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.core import signing
from django.db import IntegrityError, transaction

from apps.identity.models import DataExport, DataExportStatus
from apps.identity.services.audit import write_audit
from apps.identity.services.export_serializer import build_ics, build_json
from domain.errors import NotFoundError
from shared.actor import Actor
from shared.constants import DATA_EXPORT_LINK_LIFETIME, DATA_EXPORT_SLA
from shared.db import PERSONAL

#: The signing salt for a download link. Its own, never shared with the unsubscribe or
#: click tokens: a token minted for one purpose must not be replayable as another.
_LINK_SALT = "eventpulse24.data-export.download"


class DataExportNotFoundError(NotFoundError):
    """No such export, or not the caller's, or no longer downloadable.

    **One error for all three, deliberately.** Telling a caller "this export exists but is
    not yours" confirms that another account requested one, and "it existed but expired"
    confirms the same thing a day later. The same reasoning `SavedEventNotFoundError` uses.
    """

    code = "data_export_not_found"
    default_message = "We couldn't find that export."


@dataclass(frozen=True)
class DataExportView:
    """One export request as plain data."""

    id: UUID
    user_id: UUID
    status: str
    requested_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None
    #: When the user should have it by — `requested_at` plus the SLA.
    due_by: datetime


def _view(row: DataExport) -> DataExportView:
    return DataExportView(
        id=row.id,
        user_id=row.user_id,
        status=row.status,
        requested_at=row.requested_at,
        completed_at=row.completed_at,
        expires_at=row.expires_at,
        due_by=row.requested_at + DATA_EXPORT_SLA,
    )


def request_export(*, user_id: UUID, actor: Actor, now: datetime) -> DataExportView:
    """Ask for an export, or join the one already in flight (FR-52).

    **Idempotent while one is in flight**, which is what "requesting twice does not queue
    two jobs" means in practice. The second caller gets the first request's row back — not
    an error, because they asked a reasonable question and the answer is "it is coming".

    A *completed* export does not block a new one: a user who exported last month and has
    since changed their data is asking for something different.
    """
    with transaction.atomic(using=PERSONAL):
        existing = (
            DataExport.objects.using(PERSONAL)
            .filter(
                user_id=user_id,
                status__in=[DataExportStatus.PENDING, DataExportStatus.BUILDING],
            )
            .first()
        )
        if existing is not None:
            return _view(existing)

        try:
            with transaction.atomic(using=PERSONAL):
                row = DataExport.objects.using(PERSONAL).create(user_id=user_id, requested_at=now)
        except IntegrityError:
            # Lost the race to the constraint. The other writer's row is the answer, which
            # is the same answer this call would have produced.
            row = (
                DataExport.objects.using(PERSONAL)
                .filter(
                    user_id=user_id,
                    status__in=[DataExportStatus.PENDING, DataExportStatus.BUILDING],
                )
                .get()
            )
            return _view(row)

        write_audit(
            actor=actor,
            action="data_export.requested",
            target_type="data_export",
            target_id=row.id,
            details={"at": now.isoformat(), "due_by": (now + DATA_EXPORT_SLA).isoformat()},
        )
        return _view(row)


def claim_next_export(*, now: datetime) -> UUID | None:
    """Take the oldest unclaimed request, or `None`.

    `SKIP LOCKED` so two workers never build the same export, the same claim the delivery
    sweep uses (AD-7). The claim and the status move together: a row that is `BUILDING`
    with no `claimed_at` would be a row nobody could tell was stuck.
    """
    with transaction.atomic(using=PERSONAL):
        row = (
            DataExport.objects.using(PERSONAL)
            .select_for_update(skip_locked=True)
            .filter(status=DataExportStatus.PENDING, claimed_at__isnull=True)
            .order_by("requested_at")
            .first()
        )
        if row is None:
            return None

        row.status = DataExportStatus.BUILDING
        row.claimed_at = now
        row.save(using=PERSONAL, update_fields=["status", "claimed_at"])
        return row.id


def build_export(*, export_id: UUID, now: datetime) -> DataExportView:
    """Serialise the user's data onto the row and mark it ready (FR-52).

    **The location opt-out is read here, not passed in**, so there is one place that decides
    it and no caller can forget to.

    Raises:
        DataExportNotFoundError: no such export.
    """
    from apps.personalization.services.export_source import (
        dated_records_for,
        shares_precise_location,
    )

    row = DataExport.objects.using(PERSONAL).filter(id=export_id).first()
    if row is None:
        raise DataExportNotFoundError(details={"export_id": str(export_id)})

    redact = not shares_precise_location(user_id=row.user_id)
    json_body = build_json(user_id=row.user_id, redact_location=redact, generated_at=now)
    ics_body = build_ics(
        events=dated_records_for(user_id=row.user_id, redact_location=redact),
        generated_at=now,
    )

    with transaction.atomic(using=PERSONAL):
        row.json_body = json_body
        row.ics_body = ics_body
        row.status = DataExportStatus.READY
        row.completed_at = now
        row.expires_at = now + DATA_EXPORT_LINK_LIFETIME
        row.save(
            using=PERSONAL,
            update_fields=[
                "json_body",
                "ics_body",
                "status",
                "completed_at",
                "expires_at",
            ],
        )
        write_audit(
            actor=Actor.system("data_export"),
            action="data_export.built",
            target_type="data_export",
            target_id=row.id,
            details={
                "at": now.isoformat(),
                "locations_redacted": redact,
                "expires_at": row.expires_at.isoformat(),
            },
        )
    return _view(row)


def download_token(*, export_id: UUID, user_id: UUID, fmt: str) -> str:
    """A signed link token for one export, one user and one format.

    **All three are inside the signature.** A token that named only the export would let
    the format be swapped in the URL, and a token that omitted the user could be handed to
    another account — the whole payload is what the signature covers, so editing any part
    of it invalidates the link.
    """
    return signing.dumps(
        {"export": str(export_id), "user": str(user_id), "fmt": fmt},
        salt=_LINK_SALT,
    )


def read_export(*, token: str, export_id: UUID, fmt: str, now: datetime) -> str:
    """The export's body for a valid, unexpired, matching token.

    **The token is checked against the URL, not trusted instead of it.** A valid token for
    export A presented at export B's URL is refused: otherwise one legitimate link would
    unlock every export whose id the holder could guess.

    Raises:
        DataExportNotFoundError: bad signature, expired link, wrong export, wrong format,
            or a row that is no longer downloadable.
    """
    try:
        payload = signing.loads(
            token,
            salt=_LINK_SALT,
            max_age=int(DATA_EXPORT_LINK_LIFETIME.total_seconds()),
        )
    except signing.BadSignature as exc:
        raise DataExportNotFoundError(details={"export_id": str(export_id)}) from exc

    if payload.get("export") != str(export_id) or payload.get("fmt") != fmt:
        raise DataExportNotFoundError(details={"export_id": str(export_id)})

    row = (
        DataExport.objects.using(PERSONAL)
        .filter(id=export_id, user_id=payload.get("user"), status=DataExportStatus.READY)
        .first()
    )
    if row is None:
        raise DataExportNotFoundError(details={"export_id": str(export_id)})
    # **The row has the last word.** The signature's own age check cannot be revoked; this
    # is what an account deletion will later set to stop a download mid-window.
    if row.expires_at is not None and now >= row.expires_at:
        raise DataExportNotFoundError(details={"export_id": str(export_id)})

    return row.json_body if fmt == "json" else row.ics_body


def get_export(*, user_id: UUID, export_id: UUID) -> DataExportView:
    """One of this user's exports.

    Raises:
        DataExportNotFoundError: no such export, or not this user's.
    """
    row = DataExport.objects.using(PERSONAL).filter(id=export_id, user_id=user_id).first()
    if row is None:
        raise DataExportNotFoundError(details={"export_id": str(export_id)})
    return _view(row)


def expire_due_exports(*, now: datetime) -> int:
    """Mark ready exports whose window has closed, and drop their payloads.

    **The bodies are cleared, not just the status.** An expired export that still held the
    user's records would be a copy of their data living past the lifetime they were told
    about — the privacy cost of a snapshot outliving its reason.
    """
    rows = list(
        DataExport.objects.using(PERSONAL).filter(
            status=DataExportStatus.READY, expires_at__lte=now
        )
    )
    for row in rows:
        with transaction.atomic(using=PERSONAL):
            row.status = DataExportStatus.EXPIRED
            row.json_body = ""
            row.ics_body = ""
            row.save(using=PERSONAL, update_fields=["status", "json_body", "ics_body"])
            write_audit(
                actor=Actor.system("data_export"),
                action="data_export.expired",
                target_type="data_export",
                target_id=row.id,
                details={"at": now.isoformat()},
            )
    return len(rows)


def sla_window() -> timedelta:
    """How long a user should have to wait at most. One place, for the email to quote."""
    return DATA_EXPORT_SLA


__all__ = [
    "DataExportNotFoundError",
    "DataExportView",
    "build_export",
    "claim_next_export",
    "download_token",
    "expire_due_exports",
    "get_export",
    "read_export",
    "request_export",
    "sla_window",
]
