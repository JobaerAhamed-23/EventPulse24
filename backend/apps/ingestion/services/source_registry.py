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

from apps.ingestion.models import AcquisitionMethod, City, Source, TosReview
from apps.ingestion.services.audit import write_audit
from domain.dedup import canonical_url
from domain.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from domain.sources import cadence_ceiling, humanise_duration
from domain.timezones import canonical_zone
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
    "city_tz",
    "acquisition_method",
    "ingestion_cadence",
    "freshness_ttl_hours",
    "tz_coverage",
)
URL_MAX = 2048
FRESHNESS_TTL_HOURS_MAX = 32767  # PositiveSmallIntegerField


class SourceNotFoundError(NotFoundError):
    default_message = "We couldn't find that source."


# ── FR-53: the tier and its ceiling ─────────────────────────────────────────────────
#
# **Derived, not stored.** FR-17's order is the codebase's own statement of which sources
# matter more — `AcquisitionMethod`'s docstring says "FR-17 priority order, highest first" —
# and the method is already on the row. A second priority field would be a second opinion
# about a question the codebase has already answered, and the two could disagree. A priority
# that disagrees with the method is a guarantee nobody can check.
#
# **The rule lives in `domain/sources.py`**, not here. Three modules need it — this
# registry's cleaner, the scheduler's floor check and the migration — and a pure function
# that three modules need does not belong to any one of them. `domain` is stdlib-only, so
# putting it there costs the layering nothing.


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


def _city_tz(value: object) -> str:
    """An IANA zone for the source's city, or "" to clear it.

    Canonicalized on the way in — `canonical_zone` folds the legacy links (US/Pacific ->
    America/Los_Angeles) and the UTC aliases — so the column holds one spelling per zone and
    `resolve_tz` reads back exactly what was validated. Refusing here is what lets
    `resolve_tz` ignore an invalid value instead of raising at ingest time.
    """
    value = _text(value, 64, required=False)
    if not value:
        return ""
    zone = canonical_zone(value)
    if zone is None:
        raise _FieldError("Enter an IANA zone name, like Asia/Dhaka.")
    return zone


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


def _cadence(value: object, *, method: str) -> timedelta:
    """Clean a cadence against **both** bounds: the floor, and the tier's ceiling.

    The floor is `INGESTION_CADENCE_MIN` — respect the feeds. The ceiling is FR-53's: a
    source's method decides how long it may go unpolled and still honour the detection
    window the product promises.

    **`method` is the *effective* method** — the one being set, or the stored one — because
    the cadence must be legal after the write, whichever field changed. A source at a 24-hour
    cadence moved to `api` is over the high tier's 4-hour ceiling, and is refused unless the
    cadence comes with the change.
    """
    if not isinstance(value, timedelta):
        raise _FieldError("Enter a duration.")
    if value < INGESTION_CADENCE_MIN:
        raise _FieldError("Sources are checked at most every 15 minutes.")
    ceiling = cadence_ceiling(method)
    if value > ceiling:
        raise _FieldError(
            f"This source is checked at least every {humanise_duration(ceiling)}, so its "
            f"cadence cannot be longer."
        )
    return value


def _checked_cadence(value: object, *, method: str) -> timedelta:
    """`_cadence`, but refusing the way the other fields refuse.

    `_cadence` raises the private `_FieldError`, which `clean_source_input` collects into a
    `ValidationError` naming the field. This is the path for a cadence that was **not** given
    by the caller — the method's default — and there is no collection loop around it, so the
    refusal is raised here in the same shape the caller already handles.
    """
    try:
        return _cadence(value, method=method)
    except _FieldError as exc:
        raise ValidationError(
            details={"errors": [{"loc": ["ingestion_cadence"], "msg": str(exc)}]}
        ) from None


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
    "city_tz": _city_tz,
    "acquisition_method": _choice(AcquisitionMethod.values),
    "freshness_ttl_hours": _freshness_ttl_hours,
    "tz_coverage": _choice(Source.TzCoverage.values),
}


def clean_source_input(
    values: Mapping[str, object], *, method: str | None = None
) -> dict[str, object]:
    """Validate and normalize the Source fields given; raises ValidationError naming each bad
    field. Only the fields present are checked, so an update passes just its changes.

    **`method` is the effective acquisition method** — the one being set, or the stored one.
    It is what the cadence is measured against, and it is needed because the ceiling is
    per-tier (FR-53). When it is not given, the cadence is checked against the lower
    tier's ceiling, which is the safe direction: it can only refuse more, never less.

    **Errors are collected, not raised one at a time.** So a change with both a bad method
    and an over-ceiling cadence reports both — the caller sees everything that is wrong with
    the change, not just the first thing.
    """
    cleaned, errors = {}, []
    for field, value in values.items():
        try:
            if field == "ingestion_cadence":
                # Not in `_CLEANERS`: the cadence's cleaner needs the effective method, which
                # `_CLEANERS` — a flat field → cleaner map — has nowhere to carry.
                cleaned[field] = _cadence(value, method=method or "")
            elif field not in _CLEANERS:
                raise _FieldError("This field can't be changed here.")
            else:
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


def find_source_by_url(url: str) -> Source | None:
    """The registered source with this URL, or None. The URL is canonicalized first, so a
    caller that must not create a duplicate can look the source up before registering it.
    """
    target = canonical_url(url)
    if not target:
        return None
    for source_id, source_url in Source.objects.using(CATALOG).values_list("id", "url"):
        if canonical_url(source_url) == target:
            return Source.objects.using(CATALOG).get(pk=source_id)
    return None


def check_source_change(
    *,
    values: Mapping[str, object],
    current: Source | None,
    tos_review: TosReviewInput | None,
) -> CheckedSourceChange:
    """Every rule `register_source` (current=None) and `update_source` apply before writing:
    field validation, the duplicate-feed check, the FR-17 crawl guard and FR-53's cadence
    ceiling. Admin forms call it from `clean()` so a refusal shows on the form.

    **The effective method is computed *before* the fields are cleaned.** The cadence's
    ceiling depends on the method, and the method is one of the fields being changed — so
    the cadence must be measured against the method the source will *have* after the write,
    not the one it has now. A 24-hour source moved to `api` is over the high tier's ceiling
    the moment the method changes, and the change is refused unless the cadence comes with
    it.

    **The method is read from the raw input, not the cleaned input.** A caller passing an
    invalid method gets *both* errors — the bad method and the cadence checked against the
    stored method's ceiling — because `clean_source_input` collects errors rather than
    raising on the first. The method's own error is the one that matters, and it is
    reported alongside the others rather than hiding them.
    """
    effective_method = values.get(
        "acquisition_method", current.acquisition_method if current is not None else ""
    )
    cleaned = clean_source_input(values, method=str(effective_method))
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
    _check_stored_cadence_against_new_tier(cleaned=cleaned, current=current)
    return CheckedSourceChange(cleaned, resets_tos, tos_review)


def _check_stored_cadence_against_new_tier(
    *, cleaned: Mapping[str, object], current: Source | None
) -> None:
    """Refuse a method change that would leave the source's cadence above its new ceiling.

    **This is the case the cadence cleaner cannot see.** The cleaner only runs on a cadence
    that was *given*. A method-only change carries no cadence, so nothing was measured — but
    the source's stored cadence is about to be measured against a tier it was never
    classified for.

    **The row must be legal after the write, whichever field changed.** A lower-tier source
    at a 24-hour cadence moved to `api` is over the high tier's 4-hour ceiling the moment
    the method changes. The change is refused, and the refusal names the cadence field, so
    the caller knows to bring the cadence with it — which is then accepted, because the
    cleaner measures it against the new method.

    **A cadence that came with the change is not checked here.** It was already measured
    against the effective (new) method by the cleaner, and measuring it again would apply
    the ceiling twice.
    """
    if current is None or "ingestion_cadence" in cleaned:
        return
    if "acquisition_method" not in cleaned:
        return  # the tier did not change, so the stored cadence is still legal
    ceiling = cadence_ceiling(cleaned["acquisition_method"])
    if current.ingestion_cadence > ceiling:
        raise ValidationError(
            details={
                "errors": [
                    {
                        "loc": ["ingestion_cadence"],
                        "msg": (
                            f"This source is checked at least every "
                            f"{humanise_duration(ceiling)} now, "
                            f"so its cadence cannot be longer. Change the cadence with the "
                            f"method."
                        ),
                    }
                ]
            }
        )


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
    city_tz: str = "",
    city_ref: City | None = None,
    ingestion_cadence: timedelta | None = None,
    freshness_ttl_hours: int = 24,
    tos_review: TosReviewInput | None = None,
) -> Source:
    """Add a source to the registry. Crawl needs an approved `tos_review` (FR-17, plan R2).

    With no cadence, the method's default applies (`DEFAULT_INGESTION_CADENCE`, design D16).

    **`city_ref` is the resolved city, and it bypasses the cleaner.** `city` above is a
    string — a source's city is written as free text, because a venue names a city the way
    it is written. `city_ref` is the *link* to the `City` row the provisioning service
    already resolved from the curated catalog.

    **The registry does not resolve it.** It cannot: resolving a city *name* is
    `resolve_city`'s job, and the provisioning service owns that write. Letting the
    registry resolve the name again would be a second source of truth about which city a
    source belongs to — and a disagreement would mint a second `City` for the same place.
    So the caller hands over the row it already holds, and the registry stores it.

    **It is not in the audit row.** The audit's `details` stay exactly `{"fields": fields}`,
    so every `register_source` audit row has the same shape; the link lives on the row.
    """
    if tos_review is not None:
        _require_person(actor)
    if city_ref is not None and not isinstance(city_ref, City):
        raise TypeError("city_ref must be a City instance, not a name or an id.")
    values = {
        "name": name,
        "source_type": source_type,
        "url": url,
        "city": city,
        "city_tz": city_tz,
        "acquisition_method": acquisition_method,
        "freshness_ttl_hours": freshness_ttl_hours,
        "tz_coverage": tz_coverage,
    }
    if ingestion_cadence is not None:
        values["ingestion_cadence"] = ingestion_cadence
    with transaction.atomic(using=CATALOG):
        change = check_source_change(values=values, current=None, tos_review=tos_review)
        fields = change.values
        if "ingestion_cadence" not in fields:
            # **The default is checked by the same cleaner as a given cadence.** A default is
            # a value this code chooses, so it is a value this code must be able to defend:
            # if a method's default were ever above its tier's ceiling (FR-53), the row
            # would be refused here with the same message — not created and then refused by
            # the database constraint as an `IntegrityError`.
            fields["ingestion_cadence"] = _checked_cadence(
                DEFAULT_INGESTION_CADENCE[fields["acquisition_method"]],
                method=fields["acquisition_method"],
            )
        # **The link is added after the cleaner, and kept out of the audit details.**
        create_kwargs = dict(fields)
        if city_ref is not None:
            create_kwargs["city_ref"] = city_ref
        source = Source.objects.using(CATALOG).create(**create_kwargs)
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


def _set_status(
    actor: Actor,
    source_id: UUID,
    status: str,
    action: str,
    reason: str = "",
) -> Source:
    with transaction.atomic(using=CATALOG):
        source = _locked_source(source_id)
        if source.status == status:
            return source  # no change, no audit row (plan R10)
        previous, source.status = source.status, status
        changed = ["status", "updated_at"]
        if status == Source.Status.PAUSED:
            # **The reason lives on the row, not in the audit details.** The audit's
            # `details` stay exactly `{"from", "to"}` — FR-13's contract, and the shape
            # every other status change has. The row says *why*.
            source.paused_reason = reason
            changed.append("paused_reason")
        else:
            # **A resumed source is a source with no reason to be paused.** The reason
            # and the zero-yield counter are cleared together: a resumed source starts
            # its probation afresh, or the next run would instantly re-pause it.
            source.paused_reason = ""
            source.consecutive_zero_yield_runs = 0
            changed += ["paused_reason", "consecutive_zero_yield_runs"]
        source.save(using=CATALOG, update_fields=changed)
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


def pause_source(*, actor: Actor, source_id: UUID, reason: str = "") -> Source:
    """Stop ingesting a source. Sources are paused, never deleted (FR-13 auditability).

    **`reason` records *why*, on the row.** `Source.PausedReason.MANUAL` when an editor
    pauses it, `Source.PausedReason.ZERO_YIELD` when the probation does. The city reads
    the reason to tell the two apart — a hand-paused city says `paused`, a city paused
    for zero yield says `yielded_nothing`, and the surface says different things for
    each.

    **An empty reason means "we do not know".** A source paused before this column
    existed has no reason, and the city treats it as a hand-pause — the conservative
    reading, because "somebody paused this" is a stronger claim than "the probation
    paused this", and only the probation's pauses should produce `yielded_nothing`.
    """
    source = _set_status(actor, source_id, Source.Status.PAUSED, "pause_source", reason=reason)
    _reprobate_city(source, actor=actor)
    return source


def resume_source(*, actor: Actor, source_id: UUID) -> Source:
    """Start ingesting a source again.

    **The zero-yield counter is cleared.** A source that resumes after being paused for
    zero yield starts its probation afresh — otherwise the next run would immediately
    re-pause it, and the resume would be a no-op in everything but name.
    """
    source = _set_status(actor, source_id, Source.Status.ACTIVE, "resume_source")
    _reprobate_city(source, actor=actor)
    return source


def _reprobate_city(source: Source, *, actor: Actor) -> None:
    """Re-decide the city's status after a source's status changed.

    **Every path that can change a source's status goes through this module**, so every
    path that can change a city's status is covered — without a scheduler.

    **The lazy import is deliberate.** `city_probation` imports this module at module
    level, so a module-level import back would be a cycle. The repo's established
    pattern is a lazy import inside the function (see `digest_preferences.set_home_city`).

    **A failure here does not undo the pause.** The pause has already committed and the
    registry's audit row says so; a probation that could not re-decide the city leaves
    the city one step behind, which the next run repairs.

    **The log carries no city name.** AD-13: a city is weak location data about a real
    person, and the log sink is exactly the place it must not reach.
    """
    if source.city_ref_id is None:
        return
    from apps.ingestion.services.city_probation import _probate_city_status

    try:
        _probate_city_status(city_id=source.city_ref_id, actor=actor)
    except Exception:
        logger.warning("City probation failed after a source status change")


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
