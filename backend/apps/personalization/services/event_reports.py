"""FR-59: a user reports an event, and an editor gets told — across the schema wall.

**Two writes in two databases, which AD-3 forbids sharing a transaction.** The hop between
them is the whole design of this module:

```
1. personal   write EventReport (raised_at = NULL)   <- the user's fact, committed first
2. catalog    raise_user_report(event_id, category)  <- outside the transaction
3. personal   stamp raised_at                        <- only once the ticket exists
   on failure: leave NULL, log, and still answer the user normally
```

**Report first, ticket second, and the order is load-bearing.** Reversed, a failure would
leave an editor holding a ticket with a tally raised by a report that was never stored, and
FR-16's "upheld report" accounting reads the stored report. A lost *ticket* is recoverable
from the report — that is what `reconcile_unraised_reports` does. A lost *report* is not
recoverable from the ticket, because the ticket deliberately knows nothing about who
reported it.

**The user is told "thanks" either way, and that is not a lie.** Their report is stored and
will reach the queue; what failed is an internal hop with a reconciler behind it. Failing the
request would ask them to retry a write that already half-succeeded, and the retry would then
look like a duplicate.

**Nothing here changes what anyone can see.** A report never hides an event — only an editor
can (`editorial_state`). One person, or a troll with five accounts, cannot pull a listing.
"""

import logging
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.ingestion.services.review_queue import raise_user_report
from apps.personalization.models import EventReport
from domain.errors import ThrottledError
from ports.registry import get_throttle_port
from shared.constants import EVENT_REPORT_DAILY_LIMIT, EVENT_REPORT_WINDOW_SECONDS
from shared.db import PERSONAL

logger = logging.getLogger(__name__)


def throttle_key(user_id: UUID) -> str:
    """The throttle key for one user's reports.

    Keyed by **user**, not by IP: FR-59's limit is "5 per user per day", and the endpoint is
    session-scoped so there is always exactly one user. A user id is already an opaque
    identifier, so unlike the auth keys it needs no digest (AD-13 is about addresses).
    """
    return f"event_report:{user_id}"


def report_event(
    *, user_id: UUID, event_id: UUID, category: str, now: datetime | None = None
) -> EventReport:
    """Record one report and raise its review item. Idempotent per (user, event, category).

    The throttle is checked **before** the idempotence shortcut, deliberately: a client
    hammering the same report is still spending attempts, and a limit that a repeat could
    slip past is not a limit.
    """
    moment = now or timezone.now()

    decision = get_throttle_port().check(
        throttle_key(user_id),
        limit=EVENT_REPORT_DAILY_LIMIT,
        window_seconds=EVENT_REPORT_WINDOW_SECONDS,
    )
    if not decision.allowed:
        # **The shared `ThrottledError`, not a bespoke one.** `config/errors.py` already maps
        # it to 429 with the `{code, message}` body every other endpoint answers with, so a
        # new exception type here would mean a second mapping that could drift from the first.
        raise ThrottledError(
            "You have reported enough events for today. Please try again tomorrow.",
            details={"retry_after_seconds": decision.retry_after_seconds},
        )

    report, created = EventReport.objects.using(PERSONAL).get_or_create(
        user_id=user_id,
        event_id=event_id,
        category=category,
        defaults={"created_at": moment},
    )
    if not created:
        # The same person saying the same thing twice. Their row stands and the tally is not
        # bumped: it counts people, not clicks.
        return report

    _raise_and_stamp(report, now=moment)
    return report


def reconcile_unraised_reports(*, now: datetime | None = None, limit: int = 100) -> int:
    """Re-offer the reports whose review item was never raised. Returns how many landed.

    The outbox's second half, on the tick's existing 5-minute cadence. Idempotent twice over:
    the query filters on `raised_at IS NULL`, and `raise_review_item` refuses to stack a
    second open item for the same (target, reason).
    """
    moment = now or timezone.now()
    pending = list(
        EventReport.objects.using(PERSONAL)
        .filter(raised_at__isnull=True)
        .order_by("created_at")[:limit]
    )
    return sum(1 for report in pending if _raise_and_stamp(report, now=moment))


def _raise_and_stamp(report: EventReport, *, now: datetime) -> bool:
    """Raise the item, then stamp the report. True if the item exists afterwards.

    **The stamp happens only after the catalog write returned**, so a crash between them
    leaves the report unraised and re-offered rather than silently marked done.

    A failure is logged and swallowed: the caller's job is the user's request, and the
    reconciler owns the recovery. Ids only in the log line, never a title (AD-13).
    """
    try:
        result = raise_user_report(event_id=report.event_id, category=report.category, now=now)
    except Exception:
        logger.exception(
            "Report raised no review item",
            extra={
                "job": "event_report",
                "report_id": str(report.id),
                "event_id": str(report.event_id),
            },
        )
        return False

    if result is None:
        # The event is gone. There is nothing to review and nothing to retry, so the report
        # is stamped to take it out of the reconciler's queue forever.
        logger.info(
            "Report has no event to review",
            extra={"job": "event_report", "event_id": str(report.event_id)},
        )

    with transaction.atomic(using=PERSONAL):
        EventReport.objects.using(PERSONAL).filter(pk=report.pk, raised_at__isnull=True).update(
            raised_at=now
        )
    report.raised_at = now
    return True


__all__ = [
    "EVENT_REPORT_DAILY_LIMIT",
    "reconcile_unraised_reports",
    "report_event",
    "throttle_key",
]
