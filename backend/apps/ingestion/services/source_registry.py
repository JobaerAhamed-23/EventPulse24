"""Source Registry commands (FR-13) and the acquisition-hierarchy guard (FR-17).

Every Source and ToS-review write goes through here, inside `atomic(using=CATALOG)`, with an
audit row (AD-5). `Source.tos_status` caches the latest review of the *current* method since that
method was set: a method or host change resets it to `not_reviewed` (design D13, plan R3/R4).
A source is never deleted, only paused.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import UUID

from django.db import transaction

from apps.ingestion.models import AcquisitionMethod, Source, TosReview
from apps.ingestion.services.audit import write_audit
from domain.dedup import canonical_url
from domain.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from shared.actor import Actor, ActorKind
from shared.constants import DEFAULT_INGESTION_CADENCE, INGESTION_CADENCE_MIN
from shared.db import CATALOG

logger = logging.getLogger(__name__)

# What update_source may change. status moves only through pause/resume, tos_status only
# through reviews and resets, and the fetch state belongs to the pipeline and the scheduler.
EDITABLE_SOURCE_FIELDS = (
    "name",
    "source_type",
    "url",
    "city",
    "acquisition_method",
    "ingestion_cadence",
    "freshness_ttl_hours",
    "tz_coverage",
)
URL_MAX = 2048
FRESHNESS_TTL_HOURS_MAX = 32767  # PositiveSmallIntegerField


class SourceNotFoundError(NotFoundError):
    default_message = "We couldn't find that source."


class CrawlNeedsTosReviewError(PermissionDeniedError):
    """FR-17: crawling is the last resort and needs an approved ToS review of this method."""

    code = "crawl_needs_tos_review"
    default_message = "Crawling this source needs an approved terms-of-service review first."


class SourcePausedError(ConflictError):
    code = "source_paused"
    default_message = "This source is paused."


class SourceAlreadyRegisteredError(ConflictError):
    code = "source_already_registered"
    default_message = "That source is already registered."


@dataclass(frozen=True)
class TosReviewInput:
    """A ToS review of the source's current method, as entered by a person."""

    decision: str  # TosReview.Decision
    evidence_url: str = ""  # the terms page; required for an approval (plan R9)
    notes: str = ""


@dataclass(frozen=True)
class CheckedSourceChange:
    values: dict[str, object]  # cleaned, and on update only the fields that really change
    resets_tos: bool  # the method or the URL host changes, so the cached review no longer applies
    tos_review: TosReviewInput | None  # cleaned


class _FieldError(Exception):
    pass


def _text(value: object, max_length: int, *, required: bool) -> str:
    if not isinstance(value, str):
        raise _FieldError("Enter text here.")
    value = value.strip()
    if required and not value:
        raise _FieldError("This can't be empty.")
    if len(value) > max_length:
        raise _FieldError(f"Keep this to {max_length} characters.")
    return value


def _choice(choices: list[str]):
    def clean(value: object) -> str:
        if value not in choices:
            raise _FieldError("Choose one of the listed options.")
        return str(value)

    return clean


def _http_url(value: object) -> str:
    value = _text(value, URL_MAX, required=True)
    try:
        parts = urlsplit(value)
        _ = parts.port  # raises on a malformed port
    except ValueError:
        raise _FieldError("That URL can't be read.") from None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise _FieldError("Use a full http or https URL.")
    if parts.username is not None or parts.password is not None:
        raise _FieldError("Leave sign-in details out of the URL.")
    return value


def _cadence(value: object) -> timedelta:
    if not isinstance(value, timedelta):
        raise _FieldError("Enter a duration.")
    if value < INGESTION_CADENCE_MIN:
        raise _FieldError("Sources are checked at most every 15 minutes.")
    return value


def _freshness_ttl_hours(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _FieldError("Enter a whole number of hours.")
    if not 1 <= value <= FRESHNESS_TTL_HOURS_MAX:
        raise _FieldError(f"Use between 1 and {FRESHNESS_TTL_HOURS_MAX} hours.")
    return value


_CLEANERS = {
    "name": lambda v: _text(v, 200, required=True),
    "source_type": _choice(Source.SourceType.values),
    "url": _http_url,
    "city": lambda v: _text(v, 100, required=False),
    "acquisition_method": _choice(AcquisitionMethod.values),
    "ingestion_cadence": _cadence,
    "freshness_ttl_hours": _freshness_ttl_hours,
    "tz_coverage": _choice(Source.TzCoverage.values),
}


def clean_source_input(values: Mapping[str, object]) -> dict[str, object]:
    """Validate and normalize the Source fields given; raises ValidationError naming each bad
    field. Only the fields present are checked, so an update passes just its changes.
    """
    cleaned, errors = {}, []
    for field, value in values.items():
        try:
            if field not in _CLEANERS:
                raise _FieldError("This field can't be changed here.")
            cleaned[field] = _CLEANERS[field](value)
        except _FieldError as exc:
            errors.append({"loc": [field], "msg": str(exc)})
    if errors:
        raise ValidationError(details={"errors": errors})
    return cleaned


def clean_tos_review(review: TosReviewInput) -> TosReviewInput:
    """Validate a ToS review; an approval needs the terms page as evidence (plan R9)."""
    errors = []
    if review.decision not in TosReview.Decision.values:
        errors.append({"loc": ["tos_review", "decision"], "msg": "Choose approved or rejected."})
    evidence_url = ""
    try:
        if review.evidence_url:
            evidence_url = _http_url(review.evidence_url)
        elif review.decision == TosReview.Decision.APPROVED:
            raise _FieldError("Link the terms page you reviewed.")
    except _FieldError as exc:
        errors.append({"loc": ["tos_review", "evidence_url"], "msg": str(exc)})
    if not isinstance(review.notes, str):
        errors.append({"loc": ["tos_review", "notes"], "msg": "Enter text here."})
    if errors:
        raise ValidationError(details={"errors": errors})
    return replace(review, evidence_url=evidence_url, notes=review.notes.strip())


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def _check_not_registered(url: str, exclude_id: UUID | None) -> None:
    # No unique column backs this (plan R6): registration is a rare admin act, so a race
    # between two identical registrations is accepted. The registry is small (hundreds of rows)
    # and a host prefilter would miss punycode vs Unicode spellings, so every URL is compared.
    target = canonical_url(url)
    others = Source.objects.using(CATALOG).all()
    if exclude_id is not None:
        others = others.exclude(pk=exclude_id)
    for other_id, other_url in others.values_list("id", "url"):
        if canonical_url(other_url) == target:
            raise SourceAlreadyRegisteredError(details={"source_id": str(other_id)})


def check_source_change(
    *,
    values: Mapping[str, object],
    current: Source | None,
    tos_review: TosReviewInput | None,
) -> CheckedSourceChange:
    """Every rule `register_source` (current=None) and `update_source` apply before writing:
    field validation, the duplicate-feed check and the FR-17 crawl guard. Admin forms call it
    from `clean()` so a refusal shows on the form.
    """
    cleaned = clean_source_input(values)
    if current is not None:
        cleaned = {f: v for f, v in cleaned.items() if getattr(current, f) != v}
    if tos_review is not None:
        tos_review = clean_tos_review(tos_review)
    if "url" in cleaned:
        _check_not_registered(cleaned["url"], current.id if current else None)

    if current is None:
        resets_tos = True
    else:
        method_changed = "acquisition_method" in cleaned
        host_changed = "url" in cleaned and _host(cleaned["url"]) != _host(current.url)
        resets_tos = method_changed or host_changed
    method = cleaned.get("acquisition_method", current.acquisition_method if current else None)
    approved = tos_review is not None and tos_review.decision == TosReview.Decision.APPROVED
    if method == AcquisitionMethod.CRAWL and resets_tos and not approved:
        raise CrawlNeedsTosReviewError()
    return CheckedSourceChange(cleaned, resets_tos, tos_review)


def _require_person(actor: Actor) -> None:
    if actor.kind != ActorKind.USER:
        raise PermissionDeniedError("A terms-of-service review is recorded by a person.")


def _locked_source(source_id: UUID) -> Source:
    try:
        return Source.objects.using(CATALOG).select_for_update().get(pk=source_id)
    except Source.DoesNotExist:
        raise SourceNotFoundError(details={"source_id": str(source_id)}) from None


def _write_review(actor: Actor, source: Source, review: TosReviewInput) -> TosReview:
    tos = TosReview.objects.using(CATALOG).create(
        source=source,
        decision=review.decision,
        acquisition_method=source.acquisition_method,
        reviewed_by_id=actor.id,
        evidence_url=review.evidence_url,
        notes=review.notes,
    )
    source.tos_status = review.decision  # Decision values are TosStatus values
    source.save(using=CATALOG, update_fields=["tos_status", "updated_at"])
    write_audit(
        actor=actor,
        action="record_tos_review",
        target_type="source",
        target_id=source.id,
        details={
            "tos_review_id": tos.id,
            "decision": tos.decision,
            "acquisition_method": tos.acquisition_method,
        },
    )
    return tos


def register_source(
    *,
    actor: Actor,
    name: str,
    source_type: str,
    url: str,
    acquisition_method: str,
    tz_coverage: str,
    city: str = "",
    ingestion_cadence: timedelta | None = None,
    freshness_ttl_hours: int = 24,
    tos_review: TosReviewInput | None = None,
) -> Source:
    """Add a source to the registry. Crawl needs an approved `tos_review` (FR-17, plan R2).

    With no cadence, the method's default applies (`DEFAULT_INGESTION_CADENCE`, design D16).
    """
    if tos_review is not None:
        _require_person(actor)
    values = {
        "name": name,
        "source_type": source_type,
        "url": url,
        "city": city,
        "acquisition_method": acquisition_method,
        "freshness_ttl_hours": freshness_ttl_hours,
        "tz_coverage": tz_coverage,
    }
    if ingestion_cadence is not None:
        values["ingestion_cadence"] = ingestion_cadence
    with transaction.atomic(using=CATALOG):
        change = check_source_change(values=values, current=None, tos_review=tos_review)
        fields = change.values
        fields.setdefault(
            "ingestion_cadence", DEFAULT_INGESTION_CADENCE[fields["acquisition_method"]]
        )
        source = Source.objects.using(CATALOG).create(**fields)
        write_audit(
            actor=actor,
            action="register_source",
            target_type="source",
            target_id=source.id,
            details={"fields": fields},
        )
        if change.tos_review is not None:
            _write_review(actor, source, change.tos_review)
    return source


def update_source(
    *,
    actor: Actor,
    source_id: UUID,
    changes: Mapping[str, object],
    tos_review: TosReviewInput | None = None,
) -> Source:
    """Change a source's registry fields (`EDITABLE_SOURCE_FIELDS`).

    A method or host change resets `tos_status` to `not_reviewed` in the same transaction
    (D13); switching to crawl, or moving a crawl source to a new host, needs an approved
    `tos_review` (FR-17). Changes equal to the stored values are dropped, and nothing changed
    means nothing written.
    """
    if tos_review is not None:
        _require_person(actor)
    with transaction.atomic(using=CATALOG):
        source = _locked_source(source_id)
        change = check_source_change(values=changes, current=source, tos_review=tos_review)
        if change.values:
            diff = {f: {"from": getattr(source, f), "to": v} for f, v in change.values.items()}
            for field, value in change.values.items():
                setattr(source, field, value)
            if change.resets_tos:
                source.tos_status = Source.TosStatus.NOT_REVIEWED
            source.save(using=CATALOG, update_fields=[*change.values, "tos_status", "updated_at"])
            write_audit(
                actor=actor,
                action="update_source",
                target_type="source",
                target_id=source.id,
                details={"changes": diff, "tos_status_reset": change.resets_tos},
            )
        if change.tos_review is not None:
            _write_review(actor, source, change.tos_review)
    return source


def _set_status(actor: Actor, source_id: UUID, status: str, action: str) -> Source:
    with transaction.atomic(using=CATALOG):
        source = _locked_source(source_id)
        if source.status == status:
            return source  # no change, no audit row (plan R10)
        previous, source.status = source.status, status
        source.save(using=CATALOG, update_fields=["status", "updated_at"])
        write_audit(
            actor=actor,
            action=action,
            target_type="source",
            target_id=source.id,
            details={"from": previous, "to": status},
        )
    if status == Source.Status.PAUSED:
        logger.warning("Source paused", extra={"source_id": source.id})
    return source


def pause_source(*, actor: Actor, source_id: UUID) -> Source:
    """Stop ingesting a source. Sources are paused, never deleted (FR-13 auditability)."""
    return _set_status(actor, source_id, Source.Status.PAUSED, "pause_source")


def resume_source(*, actor: Actor, source_id: UUID) -> Source:
    return _set_status(actor, source_id, Source.Status.ACTIVE, "resume_source")


def record_tos_review(*, actor: Actor, source_id: UUID, review: TosReviewInput) -> TosReview:
    """Log a person's ToS review of the source's current method and refresh the
    `tos_status` cache (FR-17, D13).
    """
    _require_person(actor)
    review = clean_tos_review(review)
    with transaction.atomic(using=CATALOG):
        return _write_review(actor, _locked_source(source_id), review)


def ensure_can_ingest(source: Source) -> None:
    """The FR-13/FR-17 ingest guard: a paused source, or a crawl source without an approved
    review, is refused. The pipeline calls it before fetching.
    """
    if source.status == Source.Status.PAUSED:
        raise SourcePausedError(details={"source_id": str(source.id)})
    if (
        source.acquisition_method == AcquisitionMethod.CRAWL
        and source.tos_status != Source.TosStatus.APPROVED
    ):
        raise CrawlNeedsTosReviewError(details={"source_id": str(source.id)})
