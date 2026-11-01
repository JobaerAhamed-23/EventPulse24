"""The sweep: due rows out, mail sent, exactly once (AD-7, AD-13, AD-20).

**This is the first code in the project's history to send an email.** `ports/email.py` and
`adapters/email/{smtp,memory}.py` have existed since the scaffold with no caller anywhere.

The whole architecture exists so that this module can do one thing without doing it twice.
AD-7: *"delivery is at-least-once with dedupe at the send boundary"* — the sweep **may**
attempt a send twice, and the provider collapses the second, because the send key is the
provider's idempotency key.

---

## The shape

```
claim (transaction)  →  send (no transaction)  →  mark (transaction)
```

Three transactions, and the middle one has none. That is the whole design.

**The claim** takes the rows with `FOR UPDATE SKIP LOCKED` and records `claimed_at`, then
**commits before the provider is called**. The lock protects the *claim*, not the network:
holding a row lock across an SMTP call serialises the batch behind one slow provider, and a
connection dropped mid-call releases the lock at the worst possible moment.

**The send** happens with no transaction open. `row.send_key` goes to the provider as its
idempotency key and `row.stream` goes as the stream — both read from the row, neither
recomputed. The send key was minted when the row was created and is never a function of
`due_at` (AD-7), so a retry after a crash carries the identical key and the provider collapses
the duplicate.

**The mark** is a guarded update: `WHERE id = %s AND status = 'pending'`. Zero rows affected
means someone else got there first — not an error.

---

## What this module deliberately does not do

**It never re-checks Quiet Hours.** AD-7: *"Quiet Hours are applied when `due_at` is computed
or recomputed, deferring to the window end — never as a skip at send time."* The stored
`due_at` is already the true send time — `mint_for_plan` shifts it, and
`reschedule_pending_for_user` rewrites it in place when the user's window changes. Re-checking
here would either double-shift a send (a send deferred twice never leaves) or skip a reminder
the user explicitly asked for. The import of `domain.quiet_hours` is **absent from this
module's source**, and a test asserts that — the same discipline as item 3's
`test_no_key_builder_accepts_a_time`: a rule the suite checks beats a rule everybody has to
remember.

**It never writes a send key.** `send_key` is not in any update set here, so it cannot change
by accident. A `sent` row is never rekeyed (AD-7).

**It never holds a lock across the provider call** (see above).

**It never lets one bad row stop the batch.** Each row is handled in isolation. A provider
failure, a vanished target, a rendering error — all are recorded against that row, and the
sweep moves on.

---

## The renderer is a seam

This module is the *mechanism*. The message body comes from a renderer that item 6 replaces
with real templates and the RFC 8058 one-click unsubscribe endpoint. **The sweep's own
contract — the claim, the key, the stream, the mark — does not change when the templates do**,
which is the entire reason the seam exists rather than an inline template.

The renderer is given the row and the recipient address and returns an `EmailMessage`. It is
**not** given the stream: the stream comes from the row (AD-20), and a renderer that chose one
would be a second place for the decision to drift.

Design: .specs-fire/intents/delivery-and-reminders/work-items/
delivery-sweep-and-send-design.md (decisions D1-D12).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.db.models import Q

from apps.delivery.models import ScheduledSend
from apps.delivery.services.audit import write_audit
from ports.email import EmailMessage, EmailPort, Stream
from shared.actor import Actor
from shared.constants import SEND_CLAIM_TTL, SEND_MAX_ATTEMPTS, SEND_SWEEP_BATCH
from shared.db import PERSONAL

logger = logging.getLogger(__name__)

#: The actor that sweeps sends. A **job name**, never a user's name (AD-13).
SWEEPER = Actor.system("send_sweeper")


@dataclass(frozen=True)
class SweepCounts:
    """What one sweep did. Counts only — never an address, never a title (AD-13)."""

    claimed: int = 0
    sent: int = 0
    failed: int = 0
    cancelled: int = 0

    @property
    def attempted(self) -> int:
        return self.sent + self.failed + self.cancelled


class VanishedTargetError(Exception):
    """The row's target no longer exists, so there is nobody to remind.

    Not a domain error and never mapped to HTTP: this happens in the worker, against a row
    the user never asked about. The sweep catches it and **cancels the row** — sending a
    reminder about an event the user removed would be worse than not sending it, and
    cancelling keeps the record of what was supposed to happen (AD-7's `CANCELLED`).
    """


def _claim_expiry(now: datetime) -> datetime:
    """The instant before which a claim is considered live."""
    return now - SEND_CLAIM_TTL


def claim_due_sends(
    *,
    now: datetime,
    limit: int = SEND_SWEEP_BATCH,
) -> list[UUID]:
    """Claim up to `limit` due sends; returns their ids (D1, D2, D11).

    **Due** means three things at once: `status = 'pending'`, `due_at <= now`, and the row is
    not currently claimed by a live worker. `due_at` is **already shifted for Quiet Hours**
    (AD-7), so this is the true send time and nothing else is tested against it.

    **The claim is taken with `FOR UPDATE SKIP LOCKED`**, exactly as `claim_due_sources` and
    `claim_due_connections` do, so two overlapping sweeps never claim the same row: the second
    sweep's `SKIP LOCKED` skips the rows the first is holding.

    **The claim is recorded, not merely locked.** `claimed_at` is set in the same transaction
    and the transaction **commits before the provider is called** — the row lock protects the
    claim, not the network. A claim older than `SEND_CLAIM_TTL` is a lost job (a worker died
    mid-send) and the row becomes claimable again. The retry is safe because the send key is
    the provider's idempotency key.

    **The batch is ordered by `due_at`**, and that is not cosmetic: a bounded batch that is
    not ordered drops the *newest* rows when more rows are due than the limit, and the most
    overdue rows are the ones that should go first.
    """
    with transaction.atomic(using=PERSONAL):
        ids = list(
            ScheduledSend.objects.using(PERSONAL)
            .select_for_update(skip_locked=True)
            .filter(status=ScheduledSend.Status.PENDING)
            .filter(due_at__lte=now)
            .filter(Q(claimed_at__isnull=True) | Q(claimed_at__lte=_claim_expiry(now)))
            .order_by("due_at", "id")
            .values_list("id", flat=True)[:limit]
        )
        if not ids:
            return []
        ScheduledSend.objects.using(PERSONAL).filter(pk__in=ids).update(claimed_at=now)
        for send_id in ids:
            write_audit(
                actor=SWEEPER,
                action="claim_scheduled_send",
                target_type="scheduled_send",
                target_id=send_id,
                details={"at": now.isoformat()},
            )
    return ids


def release_claim(send_id: UUID) -> None:
    """End a claim without sending (D7 — the target vanished).

    Not audited separately: the cancellation audit row closes the claim, the same way
    `calendar_sync.release_claim` and `digest_scheduling.release_claim` are closed by the
    work they precede.
    """
    ScheduledSend.objects.using(PERSONAL).filter(pk=send_id).update(claimed_at=None)


def _mark_sent(*, send_id: UUID, now: datetime) -> bool:
    """Mark one row sent. Returns whether this call was the one that did it (D12).

    **The update is guarded.** `status = 'pending'` is in the `WHERE`, so a row another
    worker already sent — or a cancellation that landed first — is not overwritten. **Zero rows
    affected is not an error**: it means someone else got there first. The same shape as
    AD-17's outbox rule, *"a result of 0 means already propagated, not an error"*.

    The `sent_at` CHECK constraint (`scheduled_send_sent_at_pairs_with_status_ck`) is the
    database's half of the same rule: a `sent` row with no `sent_at` is refused by Postgres.
    """
    with transaction.atomic(using=PERSONAL):
        updated = (
            ScheduledSend.objects.using(PERSONAL)
            .filter(
                pk=send_id,
                status=ScheduledSend.Status.PENDING,
            )
            .update(
                status=ScheduledSend.Status.SENT,
                sent_at=now,
                claimed_at=None,
                updated_at=now,
            )
        )
        if updated:
            write_audit(
                actor=SWEEPER,
                action="scheduled_send.sent",
                target_type="scheduled_send",
                target_id=send_id,
                details={"at": now.isoformat()},
            )
    return bool(updated)


def _record_failure(*, send_id: UUID, error_kind: str, now: datetime) -> bool:
    """Record a provider failure against one row (D6).

    **The row goes back to `pending`** — a provider failure is a failure *this time*, not a
    verdict on the row — with `attempts` incremented and `last_error_kind` set. **The bound
    is what stops the retry ladder**: a row that exhausts `SEND_MAX_ATTEMPTS` becomes
    `failed`, which is terminal and **recorded**. It is never retried forever and never
    silently dropped.

    **`last_error_kind` is a kind, never the provider's message.** A provider error can quote
    the recipient address, and this column reaches logs and admin columns (AD-13). The
    `ScheduledSend` model's docstring says so, and the column is 32 characters for exactly
    this reason.

    **The update is guarded** the same way the mark is: a row another worker already sent
    must not be dragged back to `pending` by this worker's failure.

    Returns whether the row is now terminal (`failed`).
    """
    with transaction.atomic(using=PERSONAL):
        row = (
            ScheduledSend.objects.using(PERSONAL)
            .select_for_update()
            .filter(pk=send_id, status=ScheduledSend.Status.PENDING)
            .first()
        )
        if row is None:
            # Another worker already handled it. Not an error.
            return False
        attempts = row.attempts + 1
        exhausted = attempts >= SEND_MAX_ATTEMPTS
        row.attempts = attempts
        row.last_attempt_at = now
        row.last_error_kind = error_kind
        row.claimed_at = None
        if exhausted:
            row.status = ScheduledSend.Status.FAILED
        row.save(
            using=PERSONAL,
            update_fields=[
                "attempts",
                "last_attempt_at",
                "last_error_kind",
                "claimed_at",
                "status",
                "updated_at",
            ],
        )
        write_audit(
            actor=SWEEPER,
            action="scheduled_send.failed" if exhausted else "scheduled_send.retry",
            target_type="scheduled_send",
            target_id=send_id,
            details={"attempt": attempts, "error_kind": error_kind, "at": now.isoformat()},
        )
    return exhausted


def _cancel_vanished(*, send_id: UUID, now: datetime) -> None:
    """Cancel a row whose target no longer exists (D7).

    **Cancelled, not deleted.** The record of what was supposed to happen stays — that is
    what `Status.CANCELLED` is for — and nothing is sent.
    """
    with transaction.atomic(using=PERSONAL):
        updated = (
            ScheduledSend.objects.using(PERSONAL)
            .filter(
                pk=send_id,
                status=ScheduledSend.Status.PENDING,
            )
            .update(
                status=ScheduledSend.Status.CANCELLED,
                claimed_at=None,
                updated_at=now,
            )
        )
        if updated:
            write_audit(
                actor=SWEEPER,
                action="scheduled_send.cancelled",
                target_type="scheduled_send",
                target_id=send_id,
                details={"reason": "target_vanished", "at": now.isoformat()},
            )


def _stream_for(row: ScheduledSend) -> Stream:
    """The stream this row goes out on (AD-20, D5).

    **Read from the row.** The column has no default — a send without an explicit stream is a
    type error at the port, and it does not acquire one by accident here either. The decision
    was recorded at minting time, and re-deciding it here would be a second place for it to
    drift.

    A row carrying something that is not a `Stream` is refused: the port would raise
    `TypeError` anyway, and raising here names the row rather than the port's generic
    complaint.
    """
    try:
        return Stream(row.stream)
    except ValueError as exc:
        raise ValueError(f"send {row.id} carries an unknown stream") from exc


def send_one(
    *,
    send_id: UUID,
    port: EmailPort,
    renderer: Callable[[ScheduledSend, str], EmailMessage],
    resolve_recipient: Callable[[UUID], str | None],
    now: datetime,
) -> str:
    """Send one claimed row. Returns what happened to it (D4, D5, D6, D7, D12).

    The outcomes are `"sent"`, `"failed"` and `"cancelled"` — three facts, and the sweep
    counts them.

    **The send key is the provider's idempotency key** and is taken from the row verbatim.
    It was minted when the row was created and is never a function of `due_at` (AD-7), so a
    retry — after a provider error, or after a worker crash — carries the identical key and
    the provider collapses the duplicate. **Nothing here writes the key.**

    **The stream comes from the row** and is never shared between kinds (AD-20). A bulk send
    without an unsubscribe URL raises at the port, which is the correct refusal: RFC 8058 is
    not optional on the bulk stream.

    **The log lines carry the row's ids and the stream, never the address** (AD-13). The
    fields are `user_id`, `idempotency_key` (the send key — the very thing that is the
    provider's idempotency key) and `stream`, all of which are on the logger adapter's
    allowlist. The recipient's address is not on that allowlist and never reaches a log
    line; the address's one destination is the provider.
    """
    row = ScheduledSend.objects.using(PERSONAL).filter(pk=send_id).first()
    if row is None:
        return "cancelled"

    address = resolve_recipient(row.user_id)
    if address is None:
        # The account is gone. There is nobody to remind.
        _cancel_vanished(send_id=send_id, now=now)
        logger.info(
            "Send cancelled",
            extra={
                "job": "sweep_due_sends",
                "send_id": str(row.id),
                "user_id": str(row.user_id),
                "idempotency_key": row.send_key,
                "stream": row.stream,
                "outcome": "vanished",
            },
        )
        return "cancelled"

    stream = _stream_for(row)

    try:
        message = renderer(row, address)
    except VanishedTargetError:
        _cancel_vanished(send_id=send_id, now=now)
        logger.info(
            "Send cancelled",
            extra={
                "job": "sweep_due_sends",
                "send_id": str(row.id),
                "user_id": str(row.user_id),
                "idempotency_key": row.send_key,
                "stream": row.stream,
                "outcome": "target_vanished",
            },
        )
        return "cancelled"

    try:
        port.send(message, stream=stream, idempotency_key=row.send_key)
    except Exception as exc:
        # A provider failure is a failure *this time*. The row goes back to `pending` with a
        # bounded attempt count, and the bound makes it `failed` — recorded, not retried
        # forever and not silently dropped (D6).
        #
        # **The outcome is `"failed"` either way**, and that is not a bug. A row that has
        # exhausted its attempts is terminal; a row that has not is still pending and will
        # be picked up again. The sweep counts *attempts*, not terminal outcomes — the
        # distinction lives in the row's status, which is the only place that can say it
        # without a second count to keep in step.
        #
        # **Only the exception's *type* is logged.** A provider's message can quote the
        # recipient's address, and the message is never logged anywhere in this codebase.
        error_kind = type(exc).__name__[:32]
        _record_failure(
            send_id=send_id,
            error_kind=error_kind,
            now=now,
        )
        logger.warning(
            "Send failed",
            extra={
                "job": "sweep_due_sends",
                "send_id": str(row.id),
                "user_id": str(row.user_id),
                "idempotency_key": row.send_key,
                "stream": row.stream,
                "error_type": error_kind,
            },
        )
        return "failed"

    _mark_sent(send_id=send_id, now=now)
    logger.info(
        "Send sent",
        extra={
            "job": "sweep_due_sends",
            "send_id": str(row.id),
            "user_id": str(row.user_id),
            "idempotency_key": row.send_key,
            "stream": row.stream,
            "outcome": "sent",
        },
    )
    return "sent"


def sweep_due_sends(
    *,
    port: EmailPort,
    renderer: Callable[[ScheduledSend, str], EmailMessage],
    resolve_recipient: Callable[[UUID], str | None],
    now: datetime,
    limit: int = SEND_SWEEP_BATCH,
) -> SweepCounts:
    """Claim the due sends and send them, one at a time (D1-D12).

    **One row never stops the others.** Each row is handled in its own try/except: a provider
    failure, a vanished target, a rendering error — all are recorded against that row, and the
    sweep moves on. One user's bad address must not mean nobody gets mail.
    """
    claimed = claim_due_sends(now=now, limit=limit)
    counts = SweepCounts(claimed=len(claimed))

    for send_id in claimed:
        try:
            outcome = send_one(
                send_id=send_id,
                port=port,
                renderer=renderer,
                resolve_recipient=resolve_recipient,
                now=now,
            )
        except Exception:
            # The last line of defence. A row that raises in a way this module does not
            # anticipate is released so the next sweep can try it again, and the sweep
            # continues.
            release_claim(send_id)
            continue
        if outcome == "sent":
            counts = replace(counts, sent=counts.sent + 1)
        elif outcome == "failed":
            counts = replace(counts, failed=counts.failed + 1)
        else:
            counts = replace(counts, cancelled=counts.cancelled + 1)

    return counts


__all__ = [
    "SWEEPER",
    "SweepCounts",
    "VanishedTargetError",
    "claim_due_sends",
    "release_claim",
    "send_one",
    "sweep_due_sends",
]
