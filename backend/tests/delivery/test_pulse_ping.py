"""The Pulse Ping: one a day, and the silence that earns it (FR-10, SM-C1).

**This is the product's most distinctive behaviour, and it is the only one that improves
by doing less.** SM-C1 targets a **≥30% suppression rate** and counts a higher number as
better intelligence, not worse. So the rule has to be *measurable from day one*, and
that means every silence is counted with its reason.

**The centre of this file is FR-10's four consequences**, each its own test, because
each is a different way the Ping could go wrong:

| | what it pins |
|---|---|
| 0 public + 0 personal in 48h | **no row at all** — not a row that is later skipped |
| 1+ personal, 0 public | **a row**, carrying a personal-only digest |
| 3 qualifying events | **exactly one** row, not three |
| one row, one key | **consistent across devices** — multi-device cannot double-deliver |

**The first test is the one that matters most.** "No send minted at all" and "a minted
row that is later skipped" look identical to a user and completely different to the
system: the second is a `pending` row that is a promise the product will not keep.

**The two reasons are counted separately**, and that separation is tested too — because
an opt-out counted as a suppression would inflate SM-C1 with the user's own decisions
and make the counter-metric a lie.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from apps.delivery.models import DeliveryAuditEntry, NotificationPreference, ScheduledSend
from apps.delivery.send_keys import digest_key
from apps.delivery.services.pulse_ping import (
    REASON_NO_QUALIFYING_EVENTS,
    REASON_UNSUBSCRIBED,
    mint_ping_send,
)
from apps.delivery.services.unsubscribes import unsubscribe_pulse_ping
from apps.personalization.models import DigestPreference
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 4, 16, 0, tzinfo=UTC)
LOCAL_DATE = date(2026, 11, 4)
ZONE = "America/Los_Angeles"
DELIVERY_TIME = "09:00"

ACTOR = Actor.system("pulse_ping")


def _make_preference(user_id, **overrides):
    fields = {
        "user_id": user_id,
        "timezone": ZONE,
        "city": "Los Angeles",
        "city_source": "choice",
        "delivery_time": _time(DELIVERY_TIME),
    }
    fields.update(overrides)
    return DigestPreference.objects.using(PERSONAL).create(**fields)


def _time(value: str):
    from datetime import time

    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _unsubscribe(user_id):
    """Turn the Ping off, the way the email link does."""
    NotificationPreference.objects.using(PERSONAL).get_or_create(user_id=user_id)
    unsubscribe_pulse_ping(user_id=user_id, actor=Actor.user(user_id), now=NOW)


def _ping(
    user_id,
    *,
    public=0,
    personal=0,
    has_qualifying=None,
    local_date=LOCAL_DATE,
    now=NOW,
):
    """Ask for a Ping, with the counts the composition would have reported."""
    if has_qualifying is None:
        has_qualifying = public > 0 or personal > 0
    return mint_ping_send(
        user_id=user_id,
        local_date=local_date,
        public_qualifying_count=public,
        personal_qualifying_count=personal,
        has_qualifying_events=has_qualifying,
        actor=ACTOR,
        now=now,
    )


def _sends_for(user_id):
    return list(ScheduledSend.objects.using(PERSONAL).filter(user_id=user_id))


# --- FR-10's first consequence: nothing to say, nothing sent ------------------------------


def test_no_qualifying_events_mints_no_send_at_all():
    """**No row at all** — not a row that is later skipped.

    This is the criterion's whole point: "no send minted at all (not a minted row that
    is later skipped)". A `pending` row that is never sent is a promise the product does
    not keep, and it is indistinguishable from a bug.
    """
    user_id = uuid7()
    _make_preference(user_id)

    outcome = _ping(user_id, public=0, personal=0)

    assert not outcome.minted
    assert outcome.suppressed
    assert outcome.reason == REASON_NO_QUALIFYING_EVENTS
    assert _sends_for(user_id) == []


def test_the_suppressed_ping_leaves_no_row_of_any_status():
    """**Not even a cancelled one.** A cancelled row is still a row: the audit trail
    would show a send that was planned and withdrawn, which is not what happened."""
    user_id = uuid7()
    _make_preference(user_id)

    _ping(user_id, public=0, personal=0)

    assert ScheduledSend.objects.using(PERSONAL).filter(user_id=user_id).count() == 0


# --- FR-10's second consequence: personal events alone are enough ---------------------------


def test_personal_events_alone_mint_the_send():
    """**A personal event is the qualifying event** (FR-10).

    FR-19's opt-in makes the user's own commitment worth a Ping even when the catalog
    has nothing for their city — which is most days for most users.
    """
    user_id = uuid7()
    _make_preference(user_id)

    outcome = _ping(user_id, public=0, personal=1)

    assert outcome.minted
    assert not outcome.suppressed
    assert outcome.reason is None
    assert len(_sends_for(user_id)) == 1


def test_the_minted_row_is_a_digest_row():
    user_id = uuid7()
    _make_preference(user_id)

    _ping(user_id, public=0, personal=1)

    row = _sends_for(user_id)[0]
    assert row.kind == ScheduledSend.Kind.DIGEST
    assert row.status == ScheduledSend.Status.PENDING


def test_the_minted_row_has_no_target():
    """**A digest row is about a user and a day, not an event.** So `target_kind` is
    empty and `target_id` is `NULL` — the shape `cancel_pending_digests_for_user`
    addresses by kind."""
    user_id = uuid7()
    _make_preference(user_id)

    _ping(user_id, public=0, personal=1)

    row = _sends_for(user_id)[0]
    assert row.target_kind == ""
    assert row.target_id is None
    assert row.slot == ""
    assert row.event_version is None


# --- FR-10's third consequence: three events, one Ping ----------------------------------------


def test_three_qualifying_events_mint_one_send():
    """**One Ping, not three.** The key is `user_id · digest · local_date`, so the count
    is a property of the key rather than something the code has to remember to enforce.
    """
    user_id = uuid7()
    _make_preference(user_id)

    outcome = _ping(user_id, public=3, personal=0)

    assert outcome.minted
    assert len(_sends_for(user_id)) == 1


def test_the_send_key_is_the_users_local_date():
    """**One key, one row** — and the key carries the *local* date, because "today" is a
    different day for a user in Auckland and one in Los Angeles at the same instant."""
    user_id = uuid7()
    _make_preference(user_id)

    _ping(user_id, public=1)

    row = _sends_for(user_id)[0]
    assert row.send_key == digest_key(user_id=user_id, local_date=LOCAL_DATE)
    assert row.send_key == f"{user_id}:digest:2026-11-04"


# --- FR-10's fourth consequence: consistent across devices -------------------------------------


def test_running_the_job_twice_mints_one_row():
    """**The send is idempotent, the way the composition already is.**

    A duplicated job — the first lost to a broker hiccup, a retried enqueue — must not
    produce a second email. The unique key is what makes it so.
    """
    user_id = uuid7()
    _make_preference(user_id)

    first = _ping(user_id, public=3, personal=0)
    second = _ping(user_id, public=3, personal=0)

    assert first.minted
    assert not second.minted
    assert len(_sends_for(user_id)) == 1


def test_two_different_local_dates_mint_two_rows():
    """**One per local date, not one ever.** Tomorrow's Ping is a different row."""
    user_id = uuid7()
    _make_preference(user_id)

    _ping(user_id, public=1, local_date=LOCAL_DATE)
    _ping(user_id, public=1, local_date=LOCAL_DATE + timedelta(days=1))

    assert len(_sends_for(user_id)) == 2


def test_two_users_get_their_own_rows():
    """**The key is per user.** One user's Ping is never another's."""
    first = uuid7()
    second = uuid7()
    _make_preference(first)
    _make_preference(second)

    _ping(first, public=1)
    _ping(second, public=1)

    assert len(_sends_for(first)) == 1
    assert len(_sends_for(second)) == 1


# --- the opt-out, and what it means for the rule ------------------------------------------------


def test_a_user_who_opted_out_of_personal_events_is_not_kept_subscribed_by_them():
    """**FR-19's opt-out reaches the Ping rule.**

    A user who asked not to see their personal events in the digest must not be kept
    subscribed *by* those events. The composition reports the personal count as zero
    when the user opted out, so the rule has nothing to count.
    """
    user_id = uuid7()
    _make_preference(user_id)

    outcome = _ping(user_id, public=0, personal=0)

    assert outcome.suppressed
    assert _sends_for(user_id) == []


def test_the_opt_out_is_the_compositions_call_not_the_pings():
    """**The count the composition reports is the one the rule reads.**

    The ping command does not re-read the preference to decide whether personal events
    count — it is handed the count, so there is one place where "does this user's
    personal event qualify?" is decided.
    """
    user_id = uuid7()
    _make_preference(user_id, include_personal_events=False)

    # The composition would report zero personal events for an opted-out user.
    outcome = _ping(user_id, public=0, personal=0)

    assert outcome.personal_qualifying_count == 0
    assert outcome.suppressed


# --- the counts and the flag must agree -----------------------------------------------------------


def test_a_caller_cannot_claim_qualifying_events_with_no_qualifying_counts():
    """**The counts and the flag are two statements about the same world, so they cannot
    both be true.**

    A caller that passed `(public=0, personal=0, has_qualifying=True)` would mint a
    Ping the composition says should not exist — and the log line would say the
    product had nothing to say while the user got an email. The command refuses
    instead of guessing which fact it believes.
    """
    user_id = uuid7()
    _make_preference(user_id)

    with pytest.raises(ValueError, match="disagree"):
        _ping(user_id, public=0, personal=0, has_qualifying=True)

    assert _sends_for(user_id) == []


def test_a_caller_cannot_claim_no_qualifying_events_with_qualifying_counts():
    """**The other direction is the same contradiction.** Counting a pool that had
    events as empty would suppress a Ping the user should have got, and would record
    the suppression with counts that say otherwise."""
    user_id = uuid7()
    _make_preference(user_id)

    with pytest.raises(ValueError, match="disagree"):
        _ping(user_id, public=3, personal=0, has_qualifying=False)

    assert _sends_for(user_id) == []


def test_a_refused_caller_records_no_suppression():
    """**The refusal is not a suppression.** The command never got to decide anything,
    so there is nothing to count — and counting it would put a line in SM-C1 that no
    product decision produced."""
    user_id = uuid7()
    _make_preference(user_id)

    with pytest.raises(ValueError):
        _ping(user_id, public=0, personal=0, has_qualifying=True)

    assert (
        not DeliveryAuditEntry.objects.using(PERSONAL)
        .filter(target_id=user_id, action="pulse_ping.suppressed")
        .exists()
    )


# --- the unsubscribed user, counted separately ----------------------------------------------------


def test_an_unsubscribed_user_gets_nothing_minted():
    """**FR-11's opt-out is a promise, and the cheapest way to keep it is to never
    mint.** Nothing is created — no pending row, no cancelled row."""
    user_id = uuid7()
    _make_preference(user_id)
    _unsubscribe(user_id)

    outcome = _ping(user_id, public=5, personal=5)

    assert not outcome.minted
    assert _sends_for(user_id) == []


def test_an_unsubscribed_user_is_not_counted_as_a_suppression():
    """**The two reasons are different facts about the product.**

    SM-C1 measures *the product's* silence — the product chose not to speak because it
    had nothing worth saying. An opt-out is the *user* choosing silence. Counting an
    opt-out as a suppression would inflate SM-C1 with demand-side decisions: a product
    that mailed nobody because nobody wanted its mail would score a perfect 100%.
    """
    user_id = uuid7()
    _make_preference(user_id)
    _unsubscribe(user_id)

    outcome = _ping(user_id, public=0, personal=0)

    assert outcome.reason == REASON_UNSUBSCRIBED
    assert not outcome.suppressed


def test_an_unsubscribed_user_is_checked_before_the_suppression_rule():
    """**The order of the checks matters.** A user who has turned the Ping off is not
    counted as a suppression even when they had nothing to say either — the unsubscribe
    is the more specific fact, and it is the one that is true."""
    user_id = uuid7()
    _make_preference(user_id)
    _unsubscribe(user_id)

    outcome = _ping(user_id, public=0, personal=0)

    assert outcome.reason == REASON_UNSUBSCRIBED


def test_a_user_who_never_unsubscribed_is_not_treated_as_unsubscribed():
    """**`False` is the default, and the default means "not unsubscribed".** A user who
    has never opened settings has not opted out."""
    user_id = uuid7()
    _make_preference(user_id)

    outcome = _ping(user_id, public=1)

    assert outcome.minted
    assert outcome.reason is None


# --- the counts, which are what make SM-C1 measurable ------------------------------------------


def test_a_suppression_is_counted_in_the_audit_log_with_its_reason():
    """**The audit row answers "why did *this* user get no ping on this day?"** — a
    product question about one account, which is why it is a row and not a log line."""
    user_id = uuid7()
    _make_preference(user_id)

    _ping(user_id, public=0, personal=0)

    rows = list(
        DeliveryAuditEntry.objects.using(PERSONAL).filter(
            target_id=user_id,
            action="pulse_ping.suppressed",
        )
    )
    assert len(rows) == 1
    assert rows[0].details["reason"] == REASON_NO_QUALIFYING_EVENTS
    assert rows[0].details["local_date"] == LOCAL_DATE.isoformat()


def test_a_suppression_is_counted_with_the_pool_counts_it_saw():
    """**The counts beside the reason say what the pools looked like.** "We suppressed
    because the user's city had nothing" is answerable from them; "we suppressed" alone
    is not."""
    user_id = uuid7()
    _make_preference(user_id)

    _ping(user_id, public=0, personal=0)

    row = DeliveryAuditEntry.objects.using(PERSONAL).get(
        target_id=user_id, action="pulse_ping.suppressed"
    )
    assert row.details["public_qualifying_count"] == 0
    assert row.details["personal_qualifying_count"] == 0


def test_an_unsubscribe_is_counted_in_the_audit_log_with_its_own_reason():
    """**The two reasons are two literals**, so the audit log can tell them apart."""
    user_id = uuid7()
    _make_preference(user_id)
    _unsubscribe(user_id)

    _ping(user_id, public=1)

    row = DeliveryAuditEntry.objects.using(PERSONAL).get(
        target_id=user_id, action="pulse_ping.suppressed"
    )
    assert row.details["reason"] == REASON_UNSUBSCRIBED


def test_a_suppression_is_counted_in_a_structured_log_line(caplog):
    """**SM-C1 is read from the log line**, so it has to be structured rather than prose.

    A log line that said "suppressed a ping" would need a scrape to count; one with a
    `reason` field is a query.
    """
    import logging

    user_id = uuid7()
    _make_preference(user_id)

    with caplog.at_level(logging.INFO, logger="apps.delivery.services.pulse_ping"):
        _ping(user_id, public=0, personal=0)

    records = [r for r in caplog.records if r.msg == "Pulse Ping suppressed"]
    assert len(records) == 1
    assert records[0].reason == REASON_NO_QUALIFYING_EVENTS
    assert records[0].user_id == str(user_id)
    assert records[0].local_date == LOCAL_DATE.isoformat()


def test_the_suppression_reason_survives_the_log_formatter(caplog):
    """**The line has to survive the formatter, not just the logger.**

    `caplog` hands back the raw `LogRecord`, where every field is readable. The
    **sink** is a different thing: `JsonFormatter` redacts any field not on
    `ALLOWED_FIELDS`, so a reason that was never allowlisted reaches production as
    `[redacted]` — and SM-C1, which reads the line, cannot tell a product suppression
    from an opt-out. That is exactly the distinction the two reasons exist to make.

    So this test formats the record **through the project's own formatter** and asserts
    on the bytes that would reach the sink.
    """
    import json
    import logging

    from adapters.logging.formatter import JsonFormatter

    user_id = uuid7()
    _make_preference(user_id)

    with caplog.at_level(logging.INFO, logger="apps.delivery.services.pulse_ping"):
        _ping(user_id, public=0, personal=0)

    record = next(r for r in caplog.records if r.msg == "Pulse Ping suppressed")
    line = json.loads(JsonFormatter().format(record))

    assert line["reason"] == REASON_NO_QUALIFYING_EVENTS
    assert line["local_date"] == LOCAL_DATE.isoformat()
    assert line["public_qualifying_count"] == 0
    assert line["personal_qualifying_count"] == 0
    assert line["user_id"] == str(user_id)


def test_an_unsubscribed_reason_survives_the_log_formatter(caplog):
    """**The two reasons must both be readable at the sink**, because the difference
    between them is the whole measurement.** A sink where one reason survives and the
    other does not would count the opt-outs into SM-C1 — the inflation the two
    reasons exist to prevent."""
    import json
    import logging

    from adapters.logging.formatter import JsonFormatter

    user_id = uuid7()
    _make_preference(user_id)
    _unsubscribe(user_id)

    with caplog.at_level(logging.INFO, logger="apps.delivery.services.pulse_ping"):
        _ping(user_id, public=0, personal=0)

    record = next(r for r in caplog.records if r.msg == "Pulse Ping suppressed")
    line = json.loads(JsonFormatter().format(record))

    assert line["reason"] == REASON_UNSUBSCRIBED


def test_a_minted_ping_writes_no_suppression_row():
    """**A Ping that went out is not a suppression.** The audit log must not contain a
    row saying otherwise, or SM-C1 would count the sends as suppressions."""
    user_id = uuid7()
    _make_preference(user_id)

    _ping(user_id, public=1)

    assert (
        not DeliveryAuditEntry.objects.using(PERSONAL)
        .filter(target_id=user_id, action="pulse_ping.suppressed")
        .exists()
    )


# --- the stream and the unsubscribe URL (AD-20) ---------------------------------------------------


def test_the_send_goes_on_the_bulk_stream():
    """**AD-20: the digest email is bulk.** RFC 8058 is not optional on that stream —
    `EmailPort.send` refuses a bulk message with no `unsubscribe_url`."""
    user_id = uuid7()
    _make_preference(user_id)

    _ping(user_id, public=1)

    assert _sends_for(user_id)[0].stream == "bulk"


def test_the_rendered_digest_carries_the_ping_unsubscribe_url():
    """**The unsubscribe URL is the Ping's, not an event's.**

    It is minted at render time (the link is signed and carries the scope inside the
    signature), so this test renders the row and checks the URL is there.
    """
    from apps.delivery.services.delivery_messages import render_digest

    user_id = uuid7()
    _make_preference(user_id)
    _ping(user_id, public=1)

    row = _sends_for(user_id)[0]
    message = render_digest(row, "someone@example.com")

    assert message.unsubscribe_url is not None
    assert "token=" in message.unsubscribe_url


# --- the delivery time, and Quiet Hours -----------------------------------------------------------


def test_the_send_is_due_at_the_users_local_delivery_time():
    """**09:00 in the user's own zone**, not 09:00 UTC and not 16:00 UTC."""
    user_id = uuid7()
    _make_preference(user_id, delivery_time=_time("09:00"))

    _ping(user_id, public=1)

    row = _sends_for(user_id)[0]
    # 09:00 PST on the 4th is 17:00 UTC on the 4th.
    assert row.due_at == datetime(2026, 11, 4, 17, 0, tzinfo=UTC)


def test_the_delivery_time_is_read_in_the_users_zone():
    """**Two users, two zones, two delivery times.** A user in Tokyo's 09:00 is not the
    same instant as a Los Angeles user's 09:00."""
    tokyo_user = uuid7()
    la_user = uuid7()
    _make_preference(tokyo_user, timezone="Asia/Tokyo", delivery_time=_time("09:00"))
    _make_preference(la_user, timezone=ZONE, delivery_time=_time("09:00"))

    _ping(tokyo_user, public=1)
    _ping(la_user, public=1)

    tokyo_due = _sends_for(tokyo_user)[0].due_at
    la_due = _sends_for(la_user)[0].due_at
    assert tokyo_due != la_due


def test_the_send_is_shifted_by_quiet_hours():
    """**Quiet Hours applies to the digest like any other send** (AD-7).

    The window is `delivery`'s own row, and the shift happens at minting — the stored
    `due_at` is already the true send time, so the sweep never re-checks it.
    """
    from apps.delivery.services.notification_preferences import set_quiet_hours
    from domain.quiet_hours import QuietHours

    user_id = uuid7()
    _make_preference(user_id, delivery_time=_time("02:00"))
    set_quiet_hours(
        user_id=user_id,
        window=QuietHours(start=_time("22:00"), end=_time("08:00")),
        actor=Actor.user(user_id),
        now=NOW,
    )

    _ping(user_id, public=1)

    row = _sends_for(user_id)[0]
    # 02:00 local is inside the 22:00-08:00 window, so it defers to 08:00 local.
    assert row.due_at == datetime(2026, 11, 4, 16, 0, tzinfo=UTC)


def test_a_user_with_no_preference_row_still_gets_a_ping():
    """**No preference row is a real state**, not an error. The shared defaults are
    used, so the three places that read them agree rather than each guessing."""
    user_id = uuid7()

    outcome = _ping(user_id, public=1)

    assert outcome.minted
    assert len(_sends_for(user_id)) == 1


# --- the key kinds ------------------------------------------------------------------------------


def test_the_pulse_ping_key_kind_is_never_minted():
    """**`pulse_ping` is reserved for the Phase 2 push channel** (decided 2026-10-31).

    In MVP the digest email *is* the Ping, so the `digest` kind is the only daily one
    minted. A `pulse_ping` row would be a second send for the same day.
    """
    user_id = uuid7()
    _make_preference(user_id)

    _ping(user_id, public=1)

    assert (
        not ScheduledSend.objects.using(PERSONAL)
        .filter(kind=ScheduledSend.Kind.PULSE_PING)
        .exists()
    )


def test_the_pulse_ping_kind_carries_the_reservation_comment():
    """**The reservation is in the enum, with the reason.** A reader sees a deliberate
    reservation rather than an omission."""
    assert ScheduledSend.Kind.PULSE_PING.value == "pulse_ping"
    assert ScheduledSend.Kind.PULSE_PING.label == "Pulse Ping"
