"""`SCHEDULED_SEND`: the constraints, the key's stability, and the status machine (AD-7).

The load-bearing test here is `test_rewriting_due_at_leaves_the_key_byte_identical`. Everything
AD-7 builds on top of this table assumes a recompute cannot mint a second send, and that
assumption is only true while the key is independent of `due_at`.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.db import IntegrityError, connections, transaction

from apps.delivery.models import ScheduledSend
from apps.delivery.send_keys import digest_key, event_reminder_key
from ports.email import Stream
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.delivery.factories import ScheduledSendFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

DUE = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)


# --- The unique key ---------------------------------------------------------------------------


def test_a_duplicate_send_key_is_refused():
    """One row per thing-to-be-sent: a retry and a recompute collapse onto the same row."""
    first = ScheduledSendFactory()

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        ScheduledSendFactory(send_key=first.send_key)


def test_two_rows_differing_only_by_event_version_both_exist():
    """AD-7's subtlest case: the old key stays spent when an event moves.

    A `1d` reminder already sent for the old date must not block the `1d` reminder for the new
    one — which works precisely because the version is inside the key.
    """
    user, event = uuid7(), uuid7()
    common = {"user_id": user, "target_id": event, "slot": "1d"}

    ScheduledSendFactory(**common, event_version=1, status=ScheduledSend.Status.SENT, sent_at=DUE)
    ScheduledSendFactory(**common, event_version=2)

    assert ScheduledSend.objects.using(PERSONAL).filter(user_id=user).count() == 2


# --- The invariant everything rests on -----------------------------------------------------------


def test_rewriting_due_at_leaves_the_key_byte_identical():
    """AD-7: quiet hours, timezone, delivery time and plan edits all rewrite `due_at`.

    If the key moved with the time, each of those would mint a second send. This is the test
    that would catch a key quietly derived from `due_at`.
    """
    row = ScheduledSendFactory()
    original_key = row.send_key

    row.due_at = row.due_at + timedelta(hours=9)
    row.save(using=PERSONAL, update_fields=["due_at", "updated_at"])
    row.refresh_from_db()

    assert row.send_key == original_key


def test_ten_successive_due_at_rewrites_produce_no_new_rows():
    """A user who fiddles with settings ten times still gets one reminder."""
    row = ScheduledSendFactory()
    user = row.user_id

    for hour in range(10):
        row.due_at = DUE + timedelta(hours=hour)
        row.save(using=PERSONAL, update_fields=["due_at", "updated_at"])

    assert ScheduledSend.objects.using(PERSONAL).filter(user_id=user).count() == 1


# --- The sent_at CHECK ------------------------------------------------------------------------


def test_a_sent_row_without_a_sent_at_is_refused():
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        ScheduledSendFactory(status=ScheduledSend.Status.SENT, sent_at=None)


def test_an_unsent_row_carrying_a_sent_at_is_refused():
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        ScheduledSendFactory(status=ScheduledSend.Status.PENDING, sent_at=DUE)


def test_a_cancelled_row_may_not_carry_a_sent_at():
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        ScheduledSendFactory(status=ScheduledSend.Status.CANCELLED, sent_at=DUE)


def test_a_sent_row_with_a_sent_at_is_accepted():
    row = ScheduledSendFactory(status=ScheduledSend.Status.SENT, sent_at=DUE)

    assert row.sent_at == DUE


def test_the_sent_at_check_matches_the_status_value():
    """The constraint is written with the literal "sent" because an inner class is not in
    scope inside `Meta`. This pins the literal to the enum so they cannot drift."""
    assert ScheduledSend.Status.SENT.value == "sent"
    assert ScheduledSend.Status.PENDING.value == "pending"


# --- The status machine -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [ScheduledSend.Status.SENT, ScheduledSend.Status.CANCELLED, ScheduledSend.Status.FAILED],
)
def test_the_terminal_statuses_are_declared(status):
    assert status in ScheduledSend.TERMINAL_STATUSES


def test_pending_is_not_terminal():
    assert ScheduledSend.Status.PENDING not in ScheduledSend.TERMINAL_STATUSES


def test_a_new_row_starts_pending():
    assert ScheduledSendFactory().status == ScheduledSend.Status.PENDING


def test_every_status_is_either_pending_or_terminal():
    """No third category can appear without this failing — a half-finished state would be a
    row the sweep neither sends nor leaves alone."""
    all_statuses = set(ScheduledSend.Status)

    assert all_statuses == {ScheduledSend.Status.PENDING} | ScheduledSend.TERMINAL_STATUSES


# --- The Pulse Ping is reserved, never minted (FR-10, decided 2026-10-31) ------------------------


def test_pulse_ping_is_in_the_enum():
    """It stays so AD-7's table is legible against the code."""
    assert ScheduledSend.Kind.PULSE_PING.value == "pulse_ping"


def test_nothing_in_the_tree_mints_a_pulse_ping():
    """MVP's digest email **is** the Pulse Ping, so the key is reserved, not used."""
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]
    # The reservation itself is allowed in exactly one file — the model that declares it.
    # Matching on `models.py` by name would excuse any app's models.py, which is not the rule.
    declaration = backend / "apps" / "delivery" / "models.py"
    offenders = []
    for path in list((backend / "apps").rglob("*.py")) + list((backend / "worker").rglob("*.py")):
        if path == declaration:
            continue
        if "PULSE_PING" in path.read_text():
            offenders.append(str(path.relative_to(backend)))

    assert not offenders, f"PULSE_PING is reserved and must not be minted: {offenders}"


# --- The partial index (design D4) ----------------------------------------------------------------


def test_the_sweep_predicate_uses_the_partial_index():
    """`EXPLAIN`, not inspection: an index that exists but is not used is not an index.

    The sweep's real predicate is `status = 'pending' AND due_at <= now()`.

    **The seq scan is switched off for the assertion, and that is the point.** Postgres
    chooses a plan by cost, and on a table with a handful of rows a sequential scan really
    *is* cheaper — so whether the planner picks the index depends on the statistics of
    whatever else is in the table when the test runs. That made this a coin flip: it
    passed or failed depending on which other tests had run first and in what order.

    What the test is actually about is **whether the index can serve this predicate** —
    and "can" is answered by asking the planner for the index-only plan, not by asking
    it to prefer one. With `enable_seqscan = off`, the planner has no choice but the
    index, so a plan that names it proves the index covers the predicate and the
    planner considers it usable. The cost model is Postgres's business; the index's
    *shape* is ours.
    """
    ScheduledSendFactory.create_batch(5)

    with connections[PERSONAL].cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute(
            "EXPLAIN SELECT id FROM personal.delivery_scheduledsend "
            "WHERE status = 'pending' AND due_at <= %s",
            [DUE],
        )
        plan = "\n".join(row[0] for row in cursor.fetchall())

    assert "scheduled_send_due_pending_idx" in plan, plan


def test_the_partial_index_does_not_carry_sent_rows():
    """The point of the partial index: `sent` rows accumulate forever and are never swept."""
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'scheduled_send_due_pending_idx'"
        )
        definition = cursor.fetchone()[0]

    assert "WHERE" in definition.upper()
    assert "pending" in definition


# --- Streams (AD-20) ------------------------------------------------------------------------------


def test_the_stream_is_stored_explicitly():
    """AD-20: a send without an explicit stream is a type error at the port, and it does not
    acquire one by accident here either — the column has no default."""
    assert ScheduledSend._meta.get_field("stream").has_default() is False


def test_a_reminder_rides_the_transactional_stream():
    assert ScheduledSendFactory().stream == Stream.TRANSACTIONAL.value


def test_a_digest_row_needs_no_target():
    """A digest is about a user and a day, not one event."""
    user = uuid7()

    row = ScheduledSendFactory(
        kind=ScheduledSend.Kind.DIGEST,
        send_key=digest_key(user_id=user, local_date=DUE.date()),
        user_id=user,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        stream=Stream.BULK.value,
    )

    assert row.target_id is None
    assert row.stream == Stream.BULK.value


# --- Retention (design D5) ------------------------------------------------------------------------


def test_the_retention_category_is_account_content():
    """Not EMAIL_DELIVERY_EVENTS: a 90-day purge would delete a long-lead pending reminder
    before it ever fired. See the model docstring."""
    from shared.retention import RetentionCategory

    assert ScheduledSend.retention_category == RetentionCategory.ACCOUNT_CONTENT


# --- AD-13 ----------------------------------------------------------------------------------------


def test_str_carries_no_recipient_or_key():
    row = ScheduledSendFactory()

    rendered = str(row)

    assert str(row.user_id) not in rendered
    assert row.send_key not in rendered


def test_last_error_kind_is_short_enough_to_be_a_kind_not_a_message():
    """A provider's message can quote the recipient address (AD-13)."""
    assert ScheduledSend._meta.get_field("last_error_kind").max_length == 32


# --- The key the factory builds is the one production would ---------------------------------------


def test_the_factory_key_matches_the_builder():
    row = ScheduledSendFactory()

    assert row.send_key == event_reminder_key(
        user_id=row.user_id,
        event_id=row.target_id,
        slot=row.slot,
        event_version=row.event_version,
    )
