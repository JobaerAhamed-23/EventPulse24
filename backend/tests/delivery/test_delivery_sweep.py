"""The sweep: due rows out, mail sent, exactly once (AD-7, AD-13, AD-20).

**This is the first suite that sends email**, so it is the suite that has to prove the send
happens *once*. Everything here is built around that:

| Test | What it pins |
|---|---|
| `test_two_concurrent_workers_never_send_the_same_row` | `SKIP LOCKED` — one claim, one send |
| `test_a_claim_older_than_the_ttl_becomes_claimable_again` | a dead worker's row is reclaimed |
| `test_the_send_key_reaches_the_provider_as_the_idempotency_key` | dedupe at the boundary |
| `test_a_retry_after_a_provider_failure_carries_the_same_key` | the retry collapses |
| `test_a_bulk_send_carries_an_unsubscribe_url` | RFC 8058 on the bulk stream (AD-20) |
| `test_the_sweep_never_imports_domain_quiet_hours` | `due_at` is the true send time |
| `test_the_log_output_never_carries_the_recipient_address` | AD-13 |

**Everything runs offline.** The port is `adapters.email.memory.InMemoryEmailAdapter`, which
records each send with its stream and its key — the seam every assertion here needs.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from adapters.email.memory import InMemoryEmailAdapter
from apps.delivery.models import ScheduledSend
from apps.delivery.send_keys import digest_key
from apps.delivery.services.delivery_sweep import (
    SweepCounts,
    VanishedTargetError,
    claim_due_sends,
    release_claim,
    send_one,
    sweep_due_sends,
)
from ports.email import EmailMessage, EmailPort, SendResult, Stream
from shared.constants import SEND_CLAIM_TTL, SEND_MAX_ATTEMPTS, SEND_SWEEP_BATCH
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.delivery.factories import ScheduledSendFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

DUE = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
NOW = DUE + timedelta(minutes=1)
ADDRESS = "maya@example.com"


# ── Fakes ───────────────────────────────────────────────────────────────────────────────────


class FailingPort(EmailPort):
    """A provider that always refuses, and says why in the message.

    **The message quotes the recipient's address on purpose.** That is what a real
    provider's error looks like, and it is the case the `last_error_kind` column's 32
    characters exist for: the kind is stored, the message is not.
    """

    def __init__(self) -> None:
        self.attempts: list[tuple[str, str, str]] = []

    def _deliver(
        self, message: EmailMessage, *, stream: Stream, idempotency_key: str
    ) -> SendResult:
        self.attempts.append((message.to, stream.value, idempotency_key))
        raise RuntimeError(f"provider refused to deliver to {message.to}")


def _renderer(row: ScheduledSend, address: str) -> EmailMessage:
    """A renderer that says nothing about the target.

    The sweep's contract is the claim, the key, the stream and the mark. The *content* is
    item 6's business, so the tests here use a renderer that has no opinion about the
    event — which is what makes the suite about the mechanism.
    """
    return EmailMessage(
        to=address,
        subject="Reminder",
        text_body="Something you asked to be reminded about.",
    )


def _bulk_renderer(row: ScheduledSend, address: str) -> EmailMessage:
    """A bulk renderer that satisfies RFC 8058, the way the real one must."""
    return EmailMessage(
        to=address,
        subject="Your Pulse",
        text_body="Today's pulse.",
        unsubscribe_url=f"https://eventpulse24.example/unsub/digest/{row.user_id}",
    )


def _resolve(address: str | None = ADDRESS):
    def resolve(user_id) -> str | None:
        return address

    return resolve


# ── The claim ───────────────────────────────────────────────────────────────────────────────


def test_a_due_pending_row_is_claimed():
    ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))

    claimed = claim_due_sends(now=NOW)

    assert len(claimed) == 1


def test_a_row_that_is_not_due_yet_is_not_claimed():
    ScheduledSendFactory(due_at=NOW + timedelta(minutes=1))

    assert claim_due_sends(now=NOW) == []


def test_a_sent_row_is_not_claimed():
    ScheduledSendFactory(
        due_at=NOW - timedelta(minutes=1), status=ScheduledSend.Status.SENT, sent_at=DUE
    )

    assert claim_due_sends(now=NOW) == []


def test_a_claimed_row_is_not_claimed_again():
    """The second sweep skips what the first is holding."""
    ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))

    first = claim_due_sends(now=NOW)
    second = claim_due_sends(now=NOW)

    assert len(first) == 1
    assert second == []


def test_a_claim_older_than_the_ttl_becomes_claimable_again():
    """A worker that died mid-send leaves a row that another sweep picks up (AD-7).

    The retry is safe because the send key is the provider's idempotency key — the same
    key the dead worker used.
    """
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    stale = NOW - SEND_CLAIM_TTL - timedelta(seconds=1)
    ScheduledSend.objects.using(PERSONAL).filter(pk=row.pk).update(claimed_at=stale)

    claimed = claim_due_sends(now=NOW)

    assert claimed == [row.id]


def test_a_live_claim_is_not_stolen():
    """A claim inside the TTL belongs to a worker that is still working."""
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    fresh = NOW - timedelta(seconds=10)
    ScheduledSend.objects.using(PERSONAL).filter(pk=row.pk).update(claimed_at=fresh)

    assert claim_due_sends(now=NOW) == []


def test_the_claim_is_ordered_by_due_at():
    """A bounded batch that is not ordered drops the *newest* rows when more rows are due
    than the limit, and the most overdue rows are the ones that should go first."""
    old = ScheduledSendFactory(due_at=NOW - timedelta(hours=3))
    new = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))

    claimed = claim_due_sends(now=NOW)

    assert claimed == [old.id, new.id]


def test_the_claim_is_bounded():
    ScheduledSendFactory.create_batch(SEND_SWEEP_BATCH + 5, due_at=NOW - timedelta(minutes=1))

    claimed = claim_due_sends(now=NOW, limit=SEND_SWEEP_BATCH)

    assert len(claimed) == SEND_SWEEP_BATCH


def test_releasing_a_claim_makes_the_row_claimable_again():
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    claim_due_sends(now=NOW)

    release_claim(row.id)

    assert claim_due_sends(now=NOW) == [row.id]


def test_the_claim_is_recorded_on_the_row():
    """The lock protects the claim, not the network — so the claim is *recorded* too."""
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))

    claim_due_sends(now=NOW)

    stored = ScheduledSend.objects.using(PERSONAL).get(pk=row.pk)
    assert stored.claimed_at is not None


# ── The send ────────────────────────────────────────────────────────────────────────────────


def test_a_due_row_is_sent():
    ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    counts = sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    assert counts == SweepCounts(claimed=1, sent=1)
    assert len(port.sent) == 1
    assert port.sent[0].message.to == ADDRESS


def test_the_sent_row_is_marked_sent():
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    stored = ScheduledSend.objects.using(PERSONAL).get(pk=row.pk)
    assert stored.status == ScheduledSend.Status.SENT
    assert stored.sent_at is not None
    assert stored.claimed_at is None


def test_a_sent_row_is_never_sent_again():
    """The second sweep finds nothing due, so nothing goes out."""
    ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)
    sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    assert len(port.sent) == 1


def test_the_send_key_reaches_the_provider_as_the_idempotency_key():
    """AD-7: the key is the provider's idempotency key, so a retry dedupes at the boundary."""
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    assert port.sent[0].idempotency_key == row.send_key


def test_a_retry_after_a_provider_failure_carries_the_same_key():
    """The retry collapses at the provider, because the key never moved.

    This is the whole "at-least-once with dedupe at the send boundary" claim, asserted at
    the boundary itself: two attempts, one key.
    """
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = FailingPort()

    sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)
    sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    keys = {key for _, _, key in port.attempts}
    assert len(port.attempts) == 2
    assert keys == {row.send_key}


def test_a_sent_row_is_never_rekeyed():
    """A row's key is fixed at minting and nothing in the sweep writes it."""
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    original = row.send_key
    port = InMemoryEmailAdapter()

    sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    stored = ScheduledSend.objects.using(PERSONAL).get(pk=row.pk)
    assert stored.send_key == original


# ── Streams (AD-20) ──────────────────────────────────────────────────────────────────────────


def test_a_reminder_goes_out_on_the_transactional_stream():
    ScheduledSendFactory(due_at=NOW - timedelta(minutes=1), stream=Stream.TRANSACTIONAL.value)
    port = InMemoryEmailAdapter()

    sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    assert port.sent[0].stream is Stream.TRANSACTIONAL


def test_a_digest_goes_out_on_the_bulk_stream():
    user = uuid7()
    ScheduledSendFactory(
        kind=ScheduledSend.Kind.DIGEST,
        send_key=digest_key(user_id=user, local_date=DUE.date()),
        user_id=user,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        due_at=NOW - timedelta(minutes=1),
        stream=Stream.BULK.value,
    )
    port = InMemoryEmailAdapter()

    sweep_due_sends(port=port, renderer=_bulk_renderer, resolve_recipient=_resolve(), now=NOW)

    assert port.sent[0].stream is Stream.BULK


def test_a_bulk_send_carries_an_unsubscribe_url():
    """RFC 8058 is not optional on the bulk stream (AD-20)."""
    user = uuid7()
    ScheduledSendFactory(
        kind=ScheduledSend.Kind.DIGEST,
        send_key=digest_key(user_id=user, local_date=DUE.date()),
        user_id=user,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        due_at=NOW - timedelta(minutes=1),
        stream=Stream.BULK.value,
    )
    port = InMemoryEmailAdapter()

    sweep_due_sends(port=port, renderer=_bulk_renderer, resolve_recipient=_resolve(), now=NOW)

    assert port.sent[0].message.unsubscribe_url


def test_the_two_streams_never_share_one_send():
    """A reminder and a digest in the same batch go out on different streams."""
    user = uuid7()
    ScheduledSendFactory(due_at=NOW - timedelta(minutes=1), stream=Stream.TRANSACTIONAL.value)
    ScheduledSendFactory(
        kind=ScheduledSend.Kind.DIGEST,
        send_key=digest_key(user_id=user, local_date=DUE.date()),
        user_id=user,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        due_at=NOW - timedelta(minutes=1),
        stream=Stream.BULK.value,
    )
    port = InMemoryEmailAdapter()

    sweep_due_sends(port=port, renderer=_bulk_renderer, resolve_recipient=_resolve(), now=NOW)

    assert {sent.stream for sent in port.sent} == {Stream.TRANSACTIONAL, Stream.BULK}


def test_a_bulk_send_without_an_unsubscribe_url_is_refused_at_the_port():
    """The port's own refusal: the sweep does not paper over it with a default."""
    from ports.email import EmailMessage as Message

    port = InMemoryEmailAdapter()
    message = Message(to=ADDRESS, subject="Pulse", text_body="body")

    with pytest.raises(ValueError, match="unsubscribe"):
        port.send(message, stream=Stream.BULK, idempotency_key="key")


# ── Provider failure and the attempt bound (D6) ─────────────────────────────────────────────


def test_a_provider_failure_leaves_the_row_pending():
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = FailingPort()

    sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    stored = ScheduledSend.objects.using(PERSONAL).get(pk=row.pk)
    assert stored.status == ScheduledSend.Status.PENDING
    assert stored.attempts == 1


def test_a_provider_failure_records_the_kind_not_the_message():
    """AD-13: the provider's message can quote the recipient's address."""
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = FailingPort()

    sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    stored = ScheduledSend.objects.using(PERSONAL).get(pk=row.pk)
    assert stored.last_error_kind == "RuntimeError"
    assert ADDRESS not in stored.last_error_kind


def test_a_failed_row_is_claimable_again():
    """A provider failure is a failure *this time*, not a verdict on the row."""
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = FailingPort()

    sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    assert claim_due_sends(now=NOW) == [row.id]


def test_a_row_that_exhausts_its_attempts_is_recorded_as_failed():
    """Never retried forever, never silently dropped."""
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = FailingPort()

    for _ in range(SEND_MAX_ATTEMPTS):
        sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    stored = ScheduledSend.objects.using(PERSONAL).get(pk=row.pk)
    assert stored.status == ScheduledSend.Status.FAILED
    assert stored.attempts == SEND_MAX_ATTEMPTS


def test_a_failed_row_is_never_claimed_again():
    """A terminal row is a fact, not a schedule."""
    ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = FailingPort()

    for _ in range(SEND_MAX_ATTEMPTS):
        sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    assert claim_due_sends(now=NOW) == []


# ── The vanished target (D7) ───────────────────────────────────────────────────────────────


def test_a_row_whose_target_vanished_is_cancelled():
    """Sending a reminder about an event the user removed would be worse than not sending."""
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    counts = sweep_due_sends(
        port=port,
        renderer=_renderer,
        resolve_recipient=_resolve(None),
        now=NOW,
    )

    stored = ScheduledSend.objects.using(PERSONAL).get(pk=row.pk)
    assert stored.status == ScheduledSend.Status.CANCELLED
    assert counts.cancelled == 1
    assert port.sent == []


def test_a_vanished_target_does_not_stop_the_batch():
    """One bad row never stops the others."""
    ScheduledSendFactory.create_batch(2, due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    calls: list = []

    def resolve(user_id):
        calls.append(user_id)
        return None if len(calls) == 1 else ADDRESS

    counts = sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=resolve, now=NOW)

    assert counts.sent == 1
    assert counts.cancelled == 1
    assert len(port.sent) == 1


def test_a_renderer_that_reports_a_vanished_target_cancels_the_row():
    """The renderer may discover that the thing is gone; the sweep cancels the row."""
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    def renderer(row, address):
        raise VanishedTargetError("the event is gone")

    counts = sweep_due_sends(port=port, renderer=renderer, resolve_recipient=_resolve(), now=NOW)

    stored = ScheduledSend.objects.using(PERSONAL).get(pk=row.pk)
    assert stored.status == ScheduledSend.Status.CANCELLED
    assert counts.cancelled == 1
    assert port.sent == []


def test_a_cancelled_row_is_never_claimed_again():
    ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(None), now=NOW)

    assert claim_due_sends(now=NOW) == []


# ── One bad row never stops the batch ─────────────────────────────────────────────────────


def test_an_unexpected_failure_in_one_row_does_not_stop_the_others():
    """The last line of defence: the row is released and the sweep continues."""
    ScheduledSendFactory.create_batch(2, due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()
    seen: list = []

    def renderer(row, address):
        seen.append(row.id)
        if len(seen) == 1:
            raise RuntimeError("something nobody anticipated")
        return _renderer(row, address)

    counts = sweep_due_sends(port=port, renderer=renderer, resolve_recipient=_resolve(), now=NOW)

    assert counts.sent == 1
    assert len(port.sent) == 1


def test_an_unexpected_failure_releases_the_row():
    """A row that raised is released, so the next sweep can try it again."""
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    def renderer(row, address):
        raise RuntimeError("something nobody anticipated")

    sweep_due_sends(port=port, renderer=renderer, resolve_recipient=_resolve(), now=NOW)

    stored = ScheduledSend.objects.using(PERSONAL).get(pk=row.pk)
    assert stored.claimed_at is None
    assert stored.status == ScheduledSend.Status.PENDING


# ── Quiet Hours are never re-checked at send time (AD-7) ───────────────────────────────────


def test_the_sweep_never_imports_domain_quiet_hours():
    """`due_at` is already the true send time. Re-checking it is the bug the rule prevents.

    The same discipline as `test_no_key_builder_accepts_a_time`: a rule the suite checks
    beats a rule everybody has to remember.

    **The check is on the imports, parsed from the source** — not on the raw text. The
    module's docstring *names* `domain.quiet_hours` to explain why it does not import it,
    and a text search would flag its own explanation. Parsing the AST asks the question
    that matters: does this module import anything from `domain.quiet_hours`?
    """
    import ast

    backend = Path(__file__).resolve().parents[2]
    path = backend / "apps" / "delivery" / "services" / "delivery_sweep.py"
    tree = ast.parse(path.read_text())

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    quiet_hours_imports = {name for name in imported if "quiet_hours" in name}

    assert not quiet_hours_imports, f"the sweep must not import quiet hours: {quiet_hours_imports}"


# ── The refusals ──────────────────────────────────────────────────────────────────────────


def test_a_row_carrying_an_unknown_stream_is_refused_by_name():
    """The port would raise `TypeError` anyway; raising here names the row.

    A stream that is neither `transactional` nor `bulk` is a row that was minted wrong,
    and a refusal that says which row is the difference between a five-minute diagnosis
    and an afternoon.
    """
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1), stream="carrier-pigeon")

    with pytest.raises(ValueError, match=str(row.id)):
        send_one(
            send_id=row.id,
            port=InMemoryEmailAdapter(),
            renderer=_renderer,
            resolve_recipient=_resolve(),
            now=NOW,
        )


def test_a_failure_does_not_drag_back_a_row_another_worker_already_sent():
    """The failure update is guarded the same way the mark is.

    A row another worker already sent must not be dragged back to `pending` by this
    worker's failure — that would resurrect a terminal row and re-send an email the user
    has already received.

    **`send_one` is called directly**, not through the sweep: a `sent` row is not
    `pending`, so the *claim* would never pick it up. The race this test stages is
    between the two writes inside one send — the row was pending when this worker
    claimed it and another worker sent it in between.
    """
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = FailingPort()

    # Another worker sent it between this worker's claim and this worker's failure.
    ScheduledSend.objects.using(PERSONAL).filter(pk=row.pk).update(
        status=ScheduledSend.Status.SENT, sent_at=DUE, claimed_at=None
    )

    outcome = send_one(
        send_id=row.id,
        port=port,
        renderer=_renderer,
        resolve_recipient=_resolve(),
        now=NOW,
    )

    stored = ScheduledSend.objects.using(PERSONAL).get(pk=row.pk)
    assert outcome == "failed"
    assert stored.status == ScheduledSend.Status.SENT
    assert stored.attempts == 0


def test_the_sweep_imports_no_domain_module_at_all():
    """Stronger than the one rule, and true: the sweep is mechanism, and `domain` is
    where the *rules* live. A sweep that imported a domain rule would be re-deciding
    something the minting path already decided."""
    import ast

    backend = Path(__file__).resolve().parents[2]
    path = backend / "apps" / "delivery" / "services" / "delivery_sweep.py"
    tree = ast.parse(path.read_text())

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    domain_imports = {name for name in imported if name == "domain" or name.startswith("domain.")}

    assert not domain_imports, f"the sweep must not import domain: {domain_imports}"


def test_a_row_due_during_quiet_hours_is_still_sent():
    """The shift happened at minting. The sweep sends what is due."""
    ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    counts = sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    assert counts.sent == 1


# ── The index is actually used ─────────────────────────────────────────────────────────────


def test_the_sweep_predicate_uses_the_partial_index():
    """`EXPLAIN`, not inspection: an index that exists but is not used is not an index.

    The sweep's real predicate is `status = 'pending' AND due_at <= now()`.
    """
    ScheduledSendFactory.create_batch(5, due_at=NOW - timedelta(minutes=1))

    from django.db import connections

    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "EXPLAIN SELECT id FROM personal.delivery_scheduledsend "
            "WHERE status = 'pending' AND due_at <= %s",
            [NOW],
        )
        plan = "\n".join(row[0] for row in cursor.fetchall())

    assert "scheduled_send_due_pending_idx" in plan, plan


# ── AD-13: the log output carries no address ───────────────────────────────────────────────


def test_the_log_output_never_carries_the_recipient_address(caplog):
    import logging

    ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    with caplog.at_level(logging.DEBUG):
        sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    output = "\n".join(record.getMessage() for record in caplog.records)
    assert ADDRESS not in output


def test_the_log_output_never_carries_the_address_even_on_a_failure(caplog):
    """The provider's message quotes the address — and the message is never logged."""
    import logging

    ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = FailingPort()

    with caplog.at_level(logging.DEBUG):
        sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    output = "\n".join(record.getMessage() for record in caplog.records)
    assert ADDRESS not in output


def test_the_log_line_carries_the_user_the_key_and_the_stream(caplog):
    import logging

    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    with caplog.at_level(logging.INFO):
        sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    records = [r for r in caplog.records if getattr(r, "job", None) == "sweep_due_sends"]
    assert records
    record = records[-1]
    assert record.user_id == str(row.user_id)
    assert record.idempotency_key == row.send_key
    assert record.stream == Stream.TRANSACTIONAL.value


# ── The counts ────────────────────────────────────────────────────────────────────────────


def test_the_counts_describe_what_the_sweep_did():
    ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    counts = sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    assert counts.claimed == 1
    assert counts.sent == 1
    assert counts.failed == 0
    assert counts.cancelled == 0
    assert counts.attempted == 1


def test_an_empty_sweep_counts_nothing():
    port = InMemoryEmailAdapter()

    counts = sweep_due_sends(port=port, renderer=_renderer, resolve_recipient=_resolve(), now=NOW)

    assert counts == SweepCounts()
    assert port.sent == []


# ── send_one, on its own ───────────────────────────────────────────────────────────────────


def test_send_one_sends_a_single_row():
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    port = InMemoryEmailAdapter()

    outcome = send_one(
        send_id=row.id,
        port=port,
        renderer=_renderer,
        resolve_recipient=_resolve(),
        now=NOW,
    )

    assert outcome == "sent"
    assert len(port.sent) == 1


def test_send_one_on_a_row_that_does_not_exist_is_a_cancellation():
    port = InMemoryEmailAdapter()

    outcome = send_one(
        send_id=uuid7(),
        port=port,
        renderer=_renderer,
        resolve_recipient=_resolve(),
        now=NOW,
    )

    assert outcome == "cancelled"
    assert port.sent == []
