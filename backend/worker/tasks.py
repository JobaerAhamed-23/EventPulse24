"""Worker tasks. Beat and the Celery app find these by dotted string (`config/celery.py`).

Each task wraps one `ingestion` command and returns None (Celery would otherwise log the return
value). Jobs are sent through `_enqueue`, the single seam tests replace.
"""

import logging
from datetime import datetime
from uuid import UUID

from celery import shared_task
from django.utils import timezone

from apps.delivery.services.pulse_ping import mint_ping_send
from apps.ingestion.event_fit.writes import refresh_stale_event_fits
from apps.ingestion.services import outbox, revalidation, scheduling
from apps.ingestion.services.ingest_source import ingest_source as run_ingest
from apps.ingestion.services.reliability import recompute_due
from apps.ingestion.services.source_registry import (
    CrawlNeedsTosReviewError,
    SourceNotFoundError,
    SourcePausedError,
)
from apps.personalization.services import calendar_sync, digest_scheduling
from apps.personalization.services.digest_composition import compose_digest
from apps.personalization.services.event_reports import reconcile_unraised_reports
from ports.registry import get_calendar_port, get_email_port, get_revalidation_port
from ports.revalidation import RevalidationOutcome, RevalidationRequest
from shared.actor import Actor
from shared.constants import (
    EVENT_FIT_REFRESH_BATCH_SIZE,
    EVENT_FIT_REFRESH_EVERY_MINUTES,
    OUTBOX_RECONCILE_EVERY_MINUTES,
    REVALIDATION_RECONCILE_EVERY_MINUTES,
)
from worker import propagation

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return timezone.now()


def _enqueue(task, *args) -> None:
    task.delay(*args)


@shared_task(name="worker.tasks.tick")
def tick() -> None:
    """The periodic tick (AD-7): the only beat entry. It enqueues and never touches the
    database, so a slow query can't delay the next tick.

    Every tick: `schedule_sources`, `schedule_calendars`, `schedule_digests` and
    `sweep_due_sends`. When the UTC minute is a multiple of 5: `reconcile_outbox` (the
    tick keeps no state, so the 5-minute cadence is approximate; both jobs are idempotent),
    `reconcile_revalidation`, the revalidation outbox's own reconciler (FR-27), and
    `report_held_sends` and `report_stuck_propagation`, the two halves of AD-17's
    propagation alarm. When
    the minute is a multiple of 15: `refresh_event_fits`, which recomputes the Event
    Fit rows so that "tonight" does not go stale (AD-10).

    The two cadences nest — every multiple of 15 is also a multiple of 5 — so the refresh
    always lands on a reconciler minute. That is a consequence of the numbers, not a
    design: the refresh's cadence is a divisor of the reconciler's, and if the two are
    ever made independent, the tick test that pins the enqueue order will say so.

    **The digest dispatcher's cadence does NOT nest, and it is not a minute-modulo
    rule.** `schedule_digests` runs on every tick because "due" is a *per-user local
    wall clock* comparison — a user whose delivery time is 9:00 becomes due at 9:00 in
    their own zone, and a minute-modulo rule would compose everyone at the same instant
    regardless of the hour they asked for. The dispatcher itself does the per-user
    comparison; the tick only asks it to look.

    **The sweep runs on every tick, for the same reason the digest dispatcher does.** A
    send's `due_at` is a point in time, not a minute-of-day, so a minute-modulo rule
    would be arbitrary. The sweep claims whatever is due; an empty batch is a no-op.

    **The sweep is enqueued, not run here.** It talks to a provider, and a provider call
    in the tick would put a network round-trip on the path of every 60-second tick — the
    exact coupling the tick's docstring says it exists to avoid.

    **FR-16's reliability recompute runs on every tick too, for the same reason, and the
    reason is sharper: a weekly cadence is not a minute-modulo rule.** There is no
    `minute % 10080`. The period is the ISO week, so "due" is a per-source comparison
    ("does this source have a row for this week?"), and the job makes it — the tick only
    asks it to look, exactly as `schedule_digests` does. An empty batch is a no-op, and the
    job's own claim is `FOR UPDATE SKIP LOCKED`, so two overlapping ticks cannot recompute
    the same source at once.
    """
    _enqueue(schedule_sources)
    _enqueue(schedule_calendars)
    _enqueue(schedule_digests)
    _enqueue(sweep_due_sends)
    _enqueue(recompute_reliability)
    if _now().minute % OUTBOX_RECONCILE_EVERY_MINUTES == 0:
        _enqueue(reconcile_outbox)
        # Same cadence as the outbox reconciler, and for the same reason: propagation is what
        # releases a held send (AD-17), so a hold that outlives the reconciler's own recovery
        # window is evidence the consumer is failing rather than merely slow.
        _enqueue(report_held_sends)
        # Same cadence again: a held send and a stuck change are two views of one failure,
        # and reading them together is what tells a responder which half is broken.
        _enqueue(report_stuck_propagation)
        # FR-59's report outbox. Same cadence and the same shape as the two above: a report
        # is written in `personal` and its ReviewItem raised in `catalog`, which AD-3 forbids
        # doing in one transaction — so the second half needs a second attempt, not a retry
        # loop. No new beat entry: the tick is the only one (AD-7).
        _enqueue(reconcile_event_reports)
    if _now().minute % REVALIDATION_RECONCILE_EVERY_MINUTES == 0:
        _enqueue(reconcile_revalidation)
    if _now().minute % EVENT_FIT_REFRESH_EVERY_MINUTES == 0:
        _enqueue(refresh_event_fits)
    logger.info("Tick", extra={"job": "tick"})


@shared_task(name="worker.tasks.refresh_event_fits")
def refresh_event_fits() -> None:
    """Recompute every published event's Event Fit row (AD-10, FR-26).

    **This is the staleness refresh.** "Tonight" is a statement about *now*, so a
    persisted tag goes stale as the clock moves — not only when the event changes. The
    refresh is a **writer**: it recomputes the rows and persists them, so the read path
    serves them as they stand and computes nothing (AD-10: "never recomputed at render").

    It runs on a cadence, so a tag can be up to one interval out of date. That is the
    trade-off, and it is stated in the plan rather than hidden: the alternative —
    computing at read — is what AD-10 forbids.

    The work is bounded: one pass over the published events, in batches, each batch in its
    own transaction.
    """
    written = refresh_stale_event_fits(
        now=_now(),
        actor=Actor.system("event_fit_refresh"),
        batch_size=EVENT_FIT_REFRESH_BATCH_SIZE,
    )
    logger.info("Event fits refreshed", extra={"job": "refresh_event_fits", "count": written})


@shared_task(name="worker.tasks.recompute_reliability")
def recompute_reliability() -> None:
    """Recompute the FR-16 Source Reliability Score for every source that is due (FR-16).

    **A weekly job, dispatched on every tick.** The period is the ISO week, so "due" is a
    per-source comparison and the job makes it — a weekly cadence is not expressible as a
    minute-modulo rule, so the tick asks and the job answers. An empty batch is a no-op, and
    the tick costs one enqueue either way.

    **The job is idempotent within a period.** A re-run in the same week refreshes the
    period's row rather than writing a second one, and the unique constraint on
    `(source, period_start)` is what enforces that — not this code's good manners.

    **It escalates and never removes.** A source whose score is below 0.30 with enough
    observations, or whose negative rate has spiked, gets a `source_reliability` review item
    raised — and nothing else. FR-16 is explicit that there is no auto-removal, and the
    service writes no other column of a source.

    **A failure on one source does not lose the others.** Each source is recomputed in its
    own transaction, and the batch catches per source — so one bad row cannot roll back the
    whole batch, and cannot silently skip the sources after it either.
    """
    results = recompute_due(now=_now())
    escalated = sum(1 for result in results if result.escalated)
    logger.info(
        "Reliability recomputed",
        extra={
            "job": "recompute_reliability",
            "count": len(results),
            "escalated": escalated,
        },
    )


@shared_task(name="worker.tasks.schedule_sources")
def schedule_sources() -> None:
    """Flag stale sources, claim the due ones and enqueue one ingest job per claim (FR-13)."""
    now = _now()
    stale = scheduling.flag_stale_sources(now=now)
    breaches = scheduling.report_cadence_floor_breaches(now=now)
    claimed = scheduling.claim_due_sources(now=now)
    enqueued = 0
    for source_id in claimed:
        try:
            _enqueue(ingest_source, str(source_id))
            enqueued += 1
        except Exception as exc:  # broker down: free the claim so the next tick retries
            scheduling.release_claim(source_id)
            logger.warning(
                "Ingest not enqueued",
                extra={"source_id": source_id, "error_type": type(exc).__name__},
            )
    logger.info("Sources scheduled", extra={"job": "schedule_sources", "count": enqueued})
    if stale:
        logger.warning("Sources stale", extra={"job": "schedule_sources", "count": stale})
    if breaches:
        # **FR-53's promise, broken.** A source that has not successfully ingested inside its
        # tier's ceiling cannot have a cancellation detected inside its window — so the
        # product is about to promise something it cannot keep.
        #
        # **A count, never a source id or a name** (AD-13). The count is enough to say the
        # guarantee is at risk; who it is belongs in the registry, not in a log line.
        logger.warning(
            "Source cadence floors breached",
            extra={"job": "schedule_sources", "count": breaches},
        )


@shared_task(name="worker.tasks.ingest_source")
def ingest_source(source_id: str) -> None:
    """Run one source's ingest and release its claim, whatever happens (run-016 plan S7).

    A source refused since it was claimed (paused, crawl without approval, removed) is
    skipped quietly; any other error reaches Celery.
    """
    try:
        run_ingest(UUID(source_id))
    except (SourcePausedError, CrawlNeedsTosReviewError, SourceNotFoundError) as exc:
        logger.info("Ingest skipped", extra={"source_id": source_id, "error_code": exc.code})
    finally:
        scheduling.release_claim(UUID(source_id))


@shared_task(name="worker.tasks.propagate_state_change")
def propagate_state_change(state_change_id: str) -> None:
    """AD-17's consumer: apply one catalog state change to every user it touches (FR-53-55).

    **Thin on purpose.** The loop, the per-kind dispatch and the ordering live in
    `worker.propagation`, which is plain Python and testable without Celery — the shape
    `revalidate_public_pages` already uses.

    **`propagated_at` is set only when every affected user is done.** A user whose apply
    raises is logged and skipped, the change stays unpropagated, and `reconcile_outbox`
    re-offers it; the users already applied no-op on the retry because every service this
    calls is version-gated. Marking it to stop the churn would claim a propagation that never
    happened and strand that user on the old state forever — which is why the bound on a
    poisoned change is `report_stuck_propagation`, not a timeout.
    """
    result = propagation.propagate(state_change_id=UUID(state_change_id), now=_now())
    if result.missing:
        return
    if result.failed:
        logger.warning(
            "State change propagated to some users",
            extra={
                "job": "propagate_state_change",
                "state_change_id": state_change_id,
                "users": result.users,
                "applied": result.applied,
                "failed": result.failed,
            },
        )
        return
    logger.info(
        "State change propagated",
        extra={
            "job": "propagate_state_change",
            "state_change_id": state_change_id,
            "users": result.users,
        },
    )


@shared_task(name="worker.tasks.schedule_calendars")
def schedule_calendars() -> None:
    """Claim the due calendar connections and enqueue one sync job per claim (D8).

    This mirrors `schedule_sources` exactly: the tick enqueues the dispatcher, the
    dispatcher claims what is due, and each claim becomes one job. The claim is atomic
    (`FOR UPDATE SKIP LOCKED`), so two overlapping ticks never sync the same connection
    twice, and a claim older than `CALENDAR_CLAIM_TTL` is a lost job and becomes claimable
    again.

    A connection that could not be enqueued has its claim released, so the next tick
    retries it rather than leaving it claimed until the TTL expires.
    """
    now = _now()
    claimed = calendar_sync.claim_due_connections(now=now)
    enqueued = 0
    for connection_id in claimed:
        try:
            _enqueue(sync_calendar, str(connection_id))
            enqueued += 1
        except Exception as exc:  # broker down: free the claim so the next tick retries
            calendar_sync.release_claim(connection_id)
            logger.warning(
                "Calendar sync not enqueued",
                extra={"connection_id": str(connection_id), "error_type": type(exc).__name__},
            )
    logger.info("Calendars scheduled", extra={"job": "schedule_calendars", "count": enqueued})


@shared_task(name="worker.tasks.sync_calendar")
def sync_calendar(connection_id: str) -> None:
    """Sync one connected calendar and release its claim, whatever happens (D8).

    The sync's own failures are recorded on the connection — a revoked credential marks the
    connection `needs_reconnect` and keeps the imported events (D6) — so they do not reach
    Celery as a retry. A revoked credential will not become valid by trying again.

    **An unexpected failure is recorded too.** The four failures the sync handles each
    write the next poll time. An error it does not handle would skip that, and the
    connection would be due again on the very next 60-second tick — and on every tick
    after that, forever, fetching the user's calendar 1,440 times a day. So the error is
    recorded on the row before the claim is released, and the connection is retried at the
    poll cadence rather than the tick cadence.
    """
    identifier = UUID(connection_id)
    try:
        calendar_sync.sync_calendar(
            connection_id=identifier,
            port=get_calendar_port(),
            now=_now(),
        )
    except Exception as exc:
        calendar_sync.record_unexpected_failure(
            connection_id=identifier,
            error_kind=f"unexpected:{type(exc).__name__}",
            now=_now(),
        )
        logger.warning(
            "Calendar sync failed unexpectedly",
            extra={"connection_id": str(identifier), "error_type": type(exc).__name__},
        )
        raise
    finally:
        calendar_sync.release_claim(identifier)


@shared_task(name="worker.tasks.reconcile_outbox")
def reconcile_outbox() -> None:
    """Re-enqueue state changes left unpropagated (AD-17). Scheduled by ingestion-scheduling."""
    count = outbox.reconcile_outbox()
    logger.info("Outbox reconciled", extra={"job": "reconcile_outbox", "count": count})


@shared_task(name="worker.tasks.revalidate_public_pages")
def revalidate_public_pages(request_id: str) -> None:
    """Deliver one revalidation signal to the frontend (FR-26, FR-27).

    **The delivery is a network call, so it happens here and not in the write path.** AD-11
    says a request handler's job is to validate, enqueue and return: a frontend that is down
    must never fail a user's saved write. The write path records the *intent*; this task
    carries it out.

    **Every failure is recorded on the row, and none of them is an exception.** The house
    pattern is "record it on the row, retry at the next cadence" — there is no Celery retry
    anywhere in this codebase. A 5xx or a timeout leaves the request **open**, so the
    reconciler offers it again; a 401 leaves it **failed**, because retrying with the same
    wrong secret forever is noise; and a request that has failed too many times is
    **exhausted** — kept and surfaced, not retried forever.

    **A double delivery is harmless.** The row is closed conditionally, so the second
    attempt finds nothing open and does nothing.
    """
    identifier = UUID(request_id)
    request = revalidation.open_request(identifier)
    if request is None:
        # Already delivered, exhausted or failed. Nothing to do — and doing something would
        # be the bug.
        logger.debug("Revalidation request not open", extra={"request_id": request_id})
        return

    result = get_revalidation_port().revalidate(
        RevalidationRequest(paths=tuple(request.paths), event_version=request.event_version)
    )
    if result.outcome is RevalidationOutcome.DELIVERED:
        revalidation.mark_delivered(identifier, now=_now())
        logger.info(
            "Revalidation delivered",
            extra={"job": "revalidate_public_pages", "request_id": request_id},
        )
        return

    revalidation.mark_failed(
        identifier,
        reason=result.outcome.reason,
        permanent=not result.outcome.is_retryable,
        now=_now(),
    )
    logger.warning(
        "Revalidation not delivered",
        extra={
            "job": "revalidate_public_pages",
            "request_id": request_id,
            "outcome": result.outcome.value,
            "status": result.status,
        },
    )


@shared_task(name="worker.tasks.reconcile_revalidation")
def reconcile_revalidation() -> None:
    """Re-offer the revalidation requests nobody delivered (FR-27).

    **This is the "never lost" half.** The reconciler re-offers the open requests that have
    been waiting longer than `REVALIDATION_RECONCILE_AFTER`, oldest first. A broker outage
    at enqueue time, or a crash between the commit and the enqueue, loses the *message* — never
    the *row*, so nothing is silently dropped.
    """
    count = revalidation.reconcile_revalidation()
    logger.info("Revalidation reconciled", extra={"job": "reconcile_revalidation", "count": count})


@shared_task(name="worker.tasks.schedule_digests")
def schedule_digests() -> None:
    """Claim the users whose digest is due and enqueue one composition job per claim (D1).

    This mirrors `schedule_calendars` exactly: the tick enqueues the dispatcher, the
    dispatcher claims what is due, and each claim becomes one job. The claim is atomic
    (`FOR UPDATE SKIP LOCKED`), so two overlapping ticks never compose the same user's
    digest twice, and a claim older than `DIGEST_CLAIM_TTL` is a lost job and becomes
    claimable again.

    **"Due" is the user's own local wall clock reaching their delivery time**, and the
    dispatcher composes *at or before* that time so the digest exists when the user
    arrives. **It sends nothing itself** — the job it enqueues composes *and* mints the
    Pulse Ping (FR-10), and the sweep sends what that minted.

    A user that could not be enqueued has its claim released, so the next tick retries
    it rather than leaving it claimed until the TTL expires.
    """
    now = _now()
    claimed = digest_scheduling.claim_due_digests(now=now)
    enqueued = 0
    for user_id in claimed:
        try:
            _enqueue(compose_digest_task, str(user_id))
            enqueued += 1
        except Exception as exc:  # broker down: free the claim so the next tick retries
            digest_scheduling.release_claim(user_id)
            logger.warning(
                "Digest not enqueued",
                extra={"user_id": str(user_id), "error_type": type(exc).__name__},
            )
    logger.info("Digests scheduled", extra={"job": "schedule_digests", "count": enqueued})


@shared_task(name="worker.tasks.compose_digest")
def compose_digest_task(user_id: str) -> None:
    """Compose one user's digest, mint its Pulse Ping, and release the claim (D4, FR-10).

    **The composition is idempotent.** A digest already exists for this `(user,
    local_date)`, so the service returns it with `created=False` and writes nothing. A
    duplicated job — the first one lost to a broker hiccup, a retried enqueue — is
    therefore harmless, and does not need a de-duplication of its own.

    **The send is minted after the composition, from the composition's own counts.** The
    digest email *is* the Pulse Ping (FR-10), so the two decisions happen in one job and
    in this order: compose, then decide whether to send, then mint. The counts the
    decision needs are the composition's — the pools it already read — so nothing is
    re-queried and there is no second definition of "qualifying" (the work item's
    Technical Note).

    **The decision is `delivery`'s, not this task's.** `pulse_ping.mint_ping_send` asks
    whether there is anything worth sending and calls `scheduled_sends.mint_digest` to
    create the row. This task is the orchestrator: it composes (personalization) and
    then mints (delivery), and it does not decide anything itself.

    **The claim is released in a `finally`**, so a crash cannot leave a user claimed
    until the TTL expires. An unexpected error is re-raised so Celery sees it and the
    job is retried; the log line names the job and the error's type, and **no PII**
    (AD-13) — a user id is a UUID, and it is already one indexed read away.
    """
    identifier = UUID(user_id)
    try:
        result = compose_digest(
            user_id=identifier,
            actor=Actor.system("digest_composer"),
            now=_now(),
        )
        outcome = mint_ping_send(
            user_id=identifier,
            local_date=result.local_date,
            public_qualifying_count=result.public_qualifying_count,
            personal_qualifying_count=result.personal_qualifying_count,
            has_qualifying_events=result.has_qualifying_events,
            now=_now(),
        )
        logger.info(
            "Digest composed",
            extra={
                "job": "compose_digest",
                "user_id": str(identifier),
                # Not `created`: `LogRecord` already has a field by that name, and
                # `extra` may not shadow one.
                "digest_created": result.created,
                "is_empty": result.is_empty,
                # The Ping's own outcome: minted, suppressed, or not (the user
                # unsubscribed). `reason` is the reason literal, and it is `None`
                # when a row was minted.
                "ping_minted": outcome.minted,
                "ping_suppressed": outcome.suppressed,
                "ping_reason": outcome.reason,
            },
        )
    except Exception as exc:
        logger.warning(
            "Digest composition failed",
            extra={
                "job": "compose_digest",
                "user_id": str(identifier),
                "error_type": type(exc).__name__,
            },
        )
        raise
    finally:
        digest_scheduling.release_claim(identifier)


@shared_task(name="worker.tasks.report_held_sends")
def report_held_sends() -> None:
    """Report sends held for propagation longer than `HELD_SEND_ALARM_AFTER` (AD-17).

    **It reports; it never releases and never sends.** Releasing a held row is
    `apply_lifecycle_change`'s decision, taken against a version. A job that released on a
    timer would send exactly the mail the hold exists to prevent, and it would do it only
    when the system was already known to be broken.

    **Why an alarm at all.** A held row is correct — the catalog moved past it and it must
    not go out. What is not correct is nobody releasing it: the user's reminders then stop
    with no error raised anywhere, which is quieter and worse than the stale send this guard
    replaced. Until the propagation consumer exists this count only grows, and that is the
    expected reading rather than a surprise.

    **Counts only, never a user id or an address** (AD-13).
    """
    from apps.delivery.services.delivery_sweep import count_stuck_holds

    stuck = count_stuck_holds(now=_now())
    if stuck:
        logger.warning(
            "Sends held for propagation past the alarm window",
            extra={"job": "report_held_sends", "stuck": stuck},
        )
    else:
        logger.info("No sends stuck behind propagation", extra={"job": "report_held_sends"})


@shared_task(name="worker.tasks.report_stuck_propagation")
def report_stuck_propagation() -> None:
    """Report state changes unpropagated past `PROPAGATION_ALARM_AFTER` (AD-17).

    **The other half of `report_held_sends`.** That one counts sends waiting for propagation;
    this counts the propagations themselves. A held send with no stuck change is a `delivery`
    problem; a stuck change explains every hold behind it at once.

    **It reports and never repairs.** `EventStateChange` is append-only — `propagated_at` is
    its one mutable column — so there is no attempts counter to retire a poisoned change with,
    and setting `propagated_at` to stop the churn would claim a propagation that never
    happened. What is bounded here is how long the failure stays quiet.

    **Counts only, never a user id or an event title** (AD-13).
    """
    stuck = propagation.count_stuck_propagations(now=_now())
    if stuck:
        logger.warning(
            "State changes unpropagated past the alarm window",
            extra={"job": "report_stuck_propagation", "stuck": stuck},
        )
    else:
        logger.info("No state changes stuck", extra={"job": "report_stuck_propagation"})


@shared_task(name="worker.tasks.sweep_due_sends")
def sweep_due_sends() -> None:
    """Claim the due sends and send them (AD-7, AD-20).

    **This is the task that actually sends email.** It is the first code in the project's
    history to call a provider, and it is deliberately shaped so that the mechanism lives
    in `apps.delivery.services.delivery_sweep` and only the wiring lives here.

    **The renderer is chosen by the row's stream** (`delivery_messages.renderer_for`), and
    the stream is read from the row — never re-decided here (AD-20). A digest that went out
    on the transactional stream would be the failure AD-20 exists to prevent, and a place
    that chose the stream would be a second place for that to happen.

    **The recipient is resolved through `identity`'s published read**, not by reading the
    `User` table: `delivery` may not import `apps.identity.models` (the `models-identity`
    import contract enforces it), and the address is the one thing the sweep needs that
    `delivery` does not own.

    **Nothing here logs an address** (AD-13). The log line carries counts and the job name.

    **A failure in the sweep does not reach Celery as a retry.** The sweep handles every
    row in isolation and records each outcome against its row — a provider failure is
    recorded as a bounded retry on that row, not as a job failure. A job-level exception
    would re-run the whole batch, and the batch's rows are protected by the claim, so the
    re-run would find them claimed and do nothing — a retry that cannot help. The
    exception is logged and swallowed; the rows own the outcome.
    """
    from apps.delivery.services.delivery_messages import renderer_for
    from apps.delivery.services.delivery_sweep import sweep_due_sends as run_sweep
    from apps.identity.services.recipients import get_recipient_address

    try:
        counts = run_sweep(
            port=get_email_port(),
            renderer=renderer_for,
            resolve_recipient=lambda user_id: get_recipient_address(user_id=user_id),
            now=_now(),
        )
    except Exception as exc:
        logger.warning(
            "Send sweep failed",
            extra={"job": "sweep_due_sends", "error_type": type(exc).__name__},
        )
        return
    logger.info(
        "Sends swept",
        extra={
            "job": "sweep_due_sends",
            "claimed": counts.claimed,
            "sent": counts.sent,
            "failed": counts.failed,
            "cancelled": counts.cancelled,
        },
    )


@shared_task(name="worker.tasks.reconcile_event_reports")
def reconcile_event_reports() -> None:
    """Re-offer the FR-59 reports whose ReviewItem was never raised.

    **The second half of the report outbox.** `report_event` writes the report in `personal`,
    then raises the item in `catalog` outside that transaction, because AD-3 forbids one
    spanning both. If the catalog write fails the report keeps `raised_at IS NULL`, the user
    is still told "thanks" — truthfully, because this job is what makes it true — and the
    editor gets the item on the next sweep.

    Idempotent twice over: the query filters on `raised_at IS NULL`, and `raise_review_item`
    refuses to stack a second open item for the same (target, reason).
    """
    raised = reconcile_unraised_reports(now=_now())
    if raised:
        logger.info(
            "Event reports reconciled",
            extra={"job": "reconcile_event_reports", "count": raised},
        )
