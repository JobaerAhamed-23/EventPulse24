"""The FR-57 review queue's intake: raise an item, or bump the open one (design:
review-queue-model D2, D4, D8, D10).

`raise_review_item` is the only writer of a new `ReviewItem` and of an open item's tallies.
Resolution (approve, edit, reject, dismiss, withdraw) belongs to the editorial commands; the
`catalog.guard_review_item` trigger keeps a resolved row out of this module's reach (D7).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.ingestion.models import Event, ReviewItem, Source
from apps.ingestion.services.audit import write_audit
from domain.errors import ValidationError
from shared.actor import Actor, ActorKind
from shared.constants import REVIEW_SLA_USER_REPORTED
from shared.db import CATALOG

_EVENT_REASONS = frozenset({ReviewItem.Reason.USER_REPORTED, ReviewItem.Reason.IN_REVIEW})
_OPEN_UNIQUE = frozenset({"review_item_open_event_reason_uq", "review_item_open_source_reason_uq"})


@dataclass(frozen=True)
class RaiseResult:
    item: ReviewItem
    created: bool


def raise_review_item(
    *,
    actor: Actor,
    reason: ReviewItem.Reason | str,
    event: Event | None = None,
    source: Source | None = None,
    category: ReviewItem.ReportCategory | str | None = None,
    now: datetime | None = None,
) -> RaiseResult:
    """Open a review item for this (target, reason), or bump the one already open.

    **One open item per (target, reason) (D2).** A second raise increments the open item's
    tally for `category` (user reports) and moves `last_raised_at`; it never moves `due_at`,
    so a stream of reports cannot push the 24h SLA back (D8).

    **Concurrent raises both count (D10).** The insert runs in a savepoint; if another writer
    opened the item first, the open-unique constraint refuses ours, and we lock and bump
    theirs with `F() + 1`. If that item was resolved between the refusal and the lock, it is
    history (D7): the insert is tried once more and opens a fresh item.

    **A report is raised as a system actor (D4)**: the caller passes
    `Actor.system("event_report")`, never the reporter, because the audit row lives in
    `catalog` where every editor can read it.

    Runs in its own `transaction.atomic(using=CATALOG)`, which nests as a savepoint inside a
    caller's catalog transaction, so the item commits or rolls back with the change that
    raised it.
    """
    reason = ReviewItem.Reason(reason)
    if reason == ReviewItem.Reason.USER_REPORTED and actor.kind != ActorKind.SYSTEM:
        # D4, enforced rather than trusted: a user actor here would put the reporter's id in a
        # catalog audit row every editor can read. A programming error, never a user's input.
        raise ValueError("A report is raised as a system actor, never as the reporter (D4).")
    category = _checked(reason=reason, event=event, source=source, category=category)
    moment = now or timezone.now()

    with transaction.atomic(using=CATALOG):
        for _attempt in range(2):
            item = _insert(reason=reason, event=event, source=source, category=category, now=moment)
            if item is not None:
                _audit(actor, "review_item_raised", item, category)
                return RaiseResult(item=item, created=True)
            item = _bump(reason=reason, event=event, source=source, category=category, now=moment)
            if item is not None:
                _audit(actor, "review_item_bumped", item, category)
                return RaiseResult(item=item, created=False)
        # Two collisions with two items that each closed under us. Vanishingly unlikely;
        # refusing is safer than looping, and the caller's transaction rolls back cleanly.
        raise RuntimeError(  # pragma: no cover
            "raise_review_item lost the race to an open item twice"
        )


def _checked(*, reason, event, source, category) -> ReviewItem.ReportCategory | None:
    errors = []
    if reason in _EVENT_REASONS:
        if event is None or source is not None:
            errors.append({"loc": ["event"], "msg": f"A {reason} item is about one event."})
    elif source is None or event is not None:
        errors.append({"loc": ["source"], "msg": f"A {reason} item is about one source."})

    if reason == ReviewItem.Reason.USER_REPORTED:
        if category is None:
            errors.append({"loc": ["category"], "msg": "A report needs a category."})
        else:
            try:
                category = ReviewItem.ReportCategory(category)
            except ValueError:
                errors.append({"loc": ["category"], "msg": "That isn't a report category."})
    elif category is not None:
        errors.append({"loc": ["category"], "msg": "Only a report carries a category."})

    if errors:
        raise ValidationError(details={"errors": errors})
    return category


def _insert(*, reason, event, source, category, now) -> ReviewItem | None:
    """Insert a new open item, or return None if one is already open (in a savepoint)."""
    item = ReviewItem(
        reason=reason,
        event=event,
        source=source,
        raised_at=now,
        last_raised_at=now,
        due_at=now + REVIEW_SLA_USER_REPORTED
        if reason == ReviewItem.Reason.USER_REPORTED
        else None,
    )
    if category is not None:
        setattr(item, ReviewItem.REPORT_FIELDS[category], 1)
    try:
        with transaction.atomic(using=CATALOG):
            item.save(using=CATALOG, force_insert=True)
    except IntegrityError as exc:
        if _constraint(exc) not in _OPEN_UNIQUE:
            raise
        return None
    return item


def _bump(*, reason, event, source, category, now) -> ReviewItem | None:
    """Lock the open item and bump it, or return None if it closed before we got the lock."""
    item = _reread_open(reason=reason, event=event, source=source)
    if item is None:
        return None
    changes = {"last_raised_at": now, "updated_at": now}
    if category is not None:
        column = ReviewItem.REPORT_FIELDS[category]
        changes[column] = F(column) + 1
    updated = (
        ReviewItem.objects.using(CATALOG)
        .filter(pk=item.pk, status=ReviewItem.Status.OPEN)
        .update(**changes)
    )
    if not updated:  # pragma: no cover - the lock held, so the row cannot close under us
        return None
    item.refresh_from_db(using=CATALOG)
    return item


def _reread_open(*, reason, event, source) -> ReviewItem | None:
    """The open item for this (target, reason), locked; None if there is none any more.

    A separate function so a test can resolve the item between the refused insert and this
    read — the one interleaving a two-thread test cannot hit on demand (D10).
    """
    return (
        ReviewItem.objects.using(CATALOG)
        .select_for_update()
        .filter(reason=reason, event=event, source=source, status=ReviewItem.Status.OPEN)
        .first()
    )


def _audit(actor: Actor, action: str, item: ReviewItem, category) -> None:
    details = {"reason": item.reason}
    if item.event_id is not None:
        details["event_id"] = str(item.event_id)
    if item.source_id is not None:
        details["source_id"] = str(item.source_id)
    if category is not None:
        details["category"] = str(category)
    write_audit(
        actor=actor, action=action, target_type="review_item", target_id=item.id, details=details
    )


def _constraint(exc: IntegrityError) -> str | None:
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None)


def raise_user_report(
    *,
    event_id: UUID,
    category: ReviewItem.ReportCategory | str,
    now: datetime | None = None,
) -> RaiseResult | None:
    """Raise or bump the `user_reported` item for one Event, by id. `None` if it is gone.

    **The published entry point for `personalization`, and the reason it exists is the wall.**
    `raise_review_item` takes an `Event` **instance**, and the `models-ingestion` contract
    lets only `apps.ingestion` import `apps.ingestion.models` — so no other app can call it.
    Resolving the id here keeps that contract intact and keeps the caller free of catalog
    models.

    **The actor is fixed here, not passed in** (D4). A report is raised as
    `Actor.system("event_report")` and never as the reporter: the audit row lives in `catalog`
    and the editorial group can read it, so attributing the raise to the user would let any
    editor read who reported what — the leak AD-3's ER note exists to prevent. Making it a
    parameter would make that leak a one-line mistake.

    Returns `None` when the Event no longer exists. The caller has already refused unknown and
    non-public events at the edge; this is the narrow race where it was deleted in between,
    and it is not an error — there is simply nothing left to review.
    """
    event = Event.objects.using(CATALOG).filter(pk=event_id).first()
    if event is None:
        return None
    return raise_review_item(
        event=event,
        reason=ReviewItem.Reason.USER_REPORTED,
        category=category,
        actor=Actor.system("event_report"),
        now=now,
    )
