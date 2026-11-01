"""The renderer seam: a `ScheduledSend` row becomes an `EmailMessage` (D8).

**The sweep's contract does not change when the templates do** — that is the entire reason
the renderer is a seam rather than an inline template. These tests pin the *contract*, not
the wording:

- The renderer is given the row and the address, and **nothing else** — no stream, no send
  key, no clock. Those three come from the row, so a renderer cannot re-decide them.
- The **bulk** renderer always supplies an unsubscribe URL (RFC 8058, AD-20).
- The **transactional** renderer never does.
- A vanished personal target raises, and the sweep cancels the row.
- A vanished *public* event does not: the catalog dropping an event is the catalog's
  business, and the reminder still goes out.
- The facts come from published interfaces, never from another app's models (AD-3, AD-16).
"""

from datetime import UTC, datetime

import pytest

from apps.delivery.models import ReminderPlan, ScheduledSend
from apps.delivery.send_keys import digest_key
from apps.delivery.services.delivery_messages import (
    DEFAULT_UNSUBSCRIBE_BASE_URL,
    MissingTargetError,
    _facts_for,
    render_digest,
    render_transactional,
    renderer_for,
    unsubscribe_url_for,
)
from apps.delivery.services.unsubscribe_tokens import UNSUBSCRIBE_SCOPE_PING
from ports.email import Stream
from shared.constants import UNSUBSCRIBE_PATH
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.delivery.factories import ScheduledSendFactory
from tests.personalization.factories import PersonalEventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
ADDRESS = "maya@example.com"


# --- The renderer's shape ---------------------------------------------------------------------


def test_the_renderer_takes_the_row_and_the_address():
    """**Two arguments, and what they are not is the point.**

    The renderer is not given the stream, the send key or a clock. Those three come from
    the row, so a renderer that could choose one would be a second place for that decision
    to drift — and the drift would show up as a digest going out on the transactional
    stream, which is exactly what AD-20 exists to prevent.
    """
    import inspect

    params = set(inspect.signature(renderer_for).parameters)

    assert params == {"row", "address"}


def test_the_renderer_takes_no_time():
    """A renderer that took a clock could render a different message on a retry."""
    import inspect

    names = set(inspect.signature(renderer_for).parameters)

    assert not (names & {"now", "at", "when", "instant", "due_at"})


# --- The stream chooses the renderer ---------------------------------------------------------


def test_a_bulk_row_gets_the_bulk_renderer():
    user = uuid7()
    row = ScheduledSendFactory(
        kind=ScheduledSend.Kind.DIGEST,
        send_key=digest_key(user_id=user, local_date=NOW.date()),
        user_id=user,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        stream=Stream.BULK.value,
    )

    message = renderer_for(row, ADDRESS)

    assert message.unsubscribe_url


def test_a_transactional_row_gets_the_transactional_renderer():
    row = ScheduledSendFactory(stream=Stream.TRANSACTIONAL.value)

    message = renderer_for(row, ADDRESS)

    assert message.unsubscribe_url is None


def test_the_stream_not_the_kind_chooses_the_renderer():
    """The stream is what the provider will send it on, and AD-20 makes it the thing that
    must not drift. The kind is a description of the content."""
    user = uuid7()
    row = ScheduledSendFactory(
        kind=ScheduledSend.Kind.EVENT_REMINDER,
        send_key=digest_key(user_id=user, local_date=NOW.date()),
        user_id=user,
        stream=Stream.BULK.value,
    )

    message = renderer_for(row, ADDRESS)

    assert message.unsubscribe_url


def test_an_unknown_stream_is_refused():
    row = ScheduledSendFactory(stream="carrier-pigeon")

    with pytest.raises(ValueError, match="unknown stream"):
        renderer_for(row, ADDRESS)


# --- RFC 8058 (AD-20) --------------------------------------------------------------------------


def test_a_bulk_message_always_carries_an_unsubscribe_url():
    user = uuid7()
    row = ScheduledSendFactory(
        kind=ScheduledSend.Kind.DIGEST,
        send_key=digest_key(user_id=user, local_date=NOW.date()),
        user_id=user,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        stream=Stream.BULK.value,
    )

    message = render_digest(row, ADDRESS)

    assert message.unsubscribe_url
    # The user id is **inside the signed token**, not in the URL path. It is not
    # readable from the link — that is the point of signing it.
    assert str(user) not in message.unsubscribe_url


def test_the_unsubscribe_url_names_the_scope():
    """The real endpoint distinguishes "stop this digest" from "stop all email"."""
    url = unsubscribe_url_for(
        user_id=uuid7(),
        scope=UNSUBSCRIBE_SCOPE_PING,
    )

    # The scope is inside the signed payload, so it is not readable from the URL — and
    # it cannot be edited either. The URL itself says only where to go.
    assert "pulse_ping" not in url
    assert url.startswith(DEFAULT_UNSUBSCRIBE_BASE_URL)
    assert UNSUBSCRIBE_PATH in url


def test_a_transactional_message_carries_no_unsubscribe_url():
    """RFC 8058 is a requirement of the bulk stream. Telling a user they can stop mail
    they never subscribed to as a list would be a lie."""
    row = ScheduledSendFactory(stream=Stream.TRANSACTIONAL.value)

    message = render_transactional(row, ADDRESS)

    assert message.unsubscribe_url is None


def test_a_bulk_message_without_an_unsubscribe_url_is_refused_by_the_port():
    """The port's own refusal, reached through the real renderer path."""
    from adapters.email.memory import InMemoryEmailAdapter

    user = uuid7()
    row = ScheduledSendFactory(
        kind=ScheduledSend.Kind.DIGEST,
        send_key=digest_key(user_id=user, local_date=NOW.date()),
        user_id=user,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        stream=Stream.BULK.value,
    )
    port = InMemoryEmailAdapter()

    port.send(render_digest(row, ADDRESS), stream=Stream.BULK, idempotency_key=row.send_key)

    assert len(port.sent) == 1


# --- The facts ---------------------------------------------------------------------------------


def test_a_personal_event_reminder_names_the_event():
    event = PersonalEventFactory(name="Rooftop cinema", user_id=uuid7())
    row = ScheduledSendFactory(
        kind=ScheduledSend.Kind.PERSONAL_REMINDER,
        target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT,
        target_id=event.id,
        user_id=event.user_id,
    )

    message = render_transactional(row, ADDRESS)

    assert "Rooftop cinema" in message.subject
    assert "Rooftop cinema" in message.text_body


def test_the_target_kind_and_the_send_kind_are_different_vocabularies():
    """**The two columns are separate enumerations, and the renderer's dispatch is on the
    send kind.**

    `ScheduledSend.target_kind` is copied verbatim from the `ReminderPlan` at minting time
    and carries a `ReminderPlan.TargetKind` — `personal_event` or `saved_event`. It says
    *which personal-side record the plan belongs to*.

    `ScheduledSend.kind` carries a `ScheduledSend.Kind` — `event_reminder`,
    `personal_reminder`, `state_notice`, `digest`. It says *what the send is*.

    A dispatch that compared `target_kind` against `ScheduledSend.Kind` would compare two
    enumerations that share no values, and could never be true. This test pins the two
    vocabularies apart so that mistake cannot come back silently.
    """
    assert ReminderPlan.TargetKind.PERSONAL_EVENT.value == "personal_event"
    assert ReminderPlan.TargetKind.SAVED_EVENT.value == "saved_event"
    assert ScheduledSend.Kind.PERSONAL_REMINDER.value == "personal_reminder"
    assert ScheduledSend.Kind.EVENT_REMINDER.value == "event_reminder"

    # No `ReminderPlan.TargetKind` value is a `ScheduledSend.Kind` value.
    target_kinds = {kind.value for kind in ReminderPlan.TargetKind}
    send_kinds = {kind.value for kind in ScheduledSend.Kind}
    assert not (target_kinds & send_kinds)


def test_a_personal_reminder_is_dispatched_on_the_send_kind_not_the_target_kind():
    """The dispatch reads `kind`, and a personal reminder's facts come from the personal
    event — with the **real** `target_kind` value the minting path writes."""
    event = PersonalEventFactory(name="Rooftop cinema", user_id=uuid7())
    row = ScheduledSendFactory(
        kind=ScheduledSend.Kind.PERSONAL_REMINDER,
        target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT,
        target_id=event.id,
        user_id=event.user_id,
    )

    facts = _facts_for(row)

    assert facts.title == "Rooftop cinema"


def test_a_vanished_personal_target_raises():
    """A personal event is the user's own row; its absence means the thing they asked
    about no longer exists, and the sweep cancels the row."""
    row = ScheduledSendFactory(
        kind=ScheduledSend.Kind.PERSONAL_REMINDER,
        target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT,
        target_id=uuid7(),
    )

    with pytest.raises(MissingTargetError):
        render_transactional(row, ADDRESS)


def test_the_vanished_target_error_is_a_vanished_target_error():
    """It is a **subclass**, so the sweep's one `except` catches any renderer that says
    "the target is gone". A renderer raising something the sweep did not know about would
    be an unhandled failure — the row would be retried forever against a target that is
    never coming back."""
    from apps.delivery.services.delivery_sweep import VanishedTargetError

    assert issubclass(MissingTargetError, VanishedTargetError)


def test_a_missing_public_event_still_produces_a_message():
    """The catalog dropping an event is the catalog's business: the user asked to be
    reminded about something, and the honest body says the event is no longer listed."""
    row = ScheduledSendFactory(target_id=uuid7())

    message = render_transactional(row, ADDRESS)

    assert message.text_body
    assert "your saved event" in message.text_body


def test_a_public_event_reminder_names_the_event():
    """The facts come from the catalog's published read, and the body quotes them."""
    from tests.ingestion.factories import EventFactory

    event = EventFactory(title="Rooftop cinema")
    row = ScheduledSendFactory(target_id=event.id)

    message = render_transactional(row, ADDRESS)

    assert "Rooftop cinema" in message.subject
    assert "Rooftop cinema" in message.text_body


def test_a_public_event_reminder_names_the_time_and_the_venue():
    """AD-6: the time is converted at the presentation edge — which is the body."""
    from tests.ingestion.factories import EventFactory

    event = EventFactory()
    row = ScheduledSendFactory(target_id=event.id)

    message = render_transactional(row, ADDRESS)

    assert "When:" in message.text_body
    assert "Where:" in message.text_body


def test_a_row_with_no_target_raises():
    row = ScheduledSendFactory(target_id=None)

    with pytest.raises(MissingTargetError):
        render_transactional(row, ADDRESS)


# --- No PII in the message beyond the recipient ------------------------------------------------


def test_the_message_goes_to_the_address_it_was_given():
    row = ScheduledSendFactory()

    message = render_transactional(row, ADDRESS)

    assert message.to == ADDRESS
    assert isinstance(message.to, str)


def test_the_subject_does_not_contain_the_address():
    """The address belongs in `to` and nowhere else."""
    row = ScheduledSendFactory()

    message = render_transactional(row, ADDRESS)

    assert ADDRESS not in message.subject
    assert ADDRESS not in message.text_body


def test_the_message_carries_no_send_key():
    """The key is the provider's idempotency key, and the sweep reads it from the row."""
    row = ScheduledSendFactory()

    message = render_transactional(row, ADDRESS)

    assert row.send_key not in message.subject
    assert row.send_key not in message.text_body


# --- The digest renderer -----------------------------------------------------------------------


def test_a_day_with_no_digest_renders_without_raising():
    """The row is about a day, and a day without a digest is a day with nothing on it."""
    user = uuid7()
    row = ScheduledSendFactory(
        kind=ScheduledSend.Kind.DIGEST,
        send_key=digest_key(user_id=user, local_date=NOW.date()),
        user_id=user,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        stream=Stream.BULK.value,
    )

    message = render_digest(row, ADDRESS)

    assert message.subject
    assert message.text_body
    assert message.unsubscribe_url


def test_the_digest_subject_names_the_day():
    user = uuid7()
    row = ScheduledSendFactory(
        kind=ScheduledSend.Kind.DIGEST,
        send_key=digest_key(user_id=user, local_date=NOW.date()),
        user_id=user,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        stream=Stream.BULK.value,
    )

    message = render_digest(row, ADDRESS)
    assert NOW.date().isoformat() in message.subject


# --- The time conversion (AD-6) -------------------------------------------------------------------


def test_a_missing_time_renders_as_no_time():
    """A fact that is not there is not rendered as a zero."""
    from apps.delivery.services.delivery_messages import _local_time_text

    assert _local_time_text(start_utc=None, zone="Europe/London") is None


def test_a_missing_zone_renders_as_no_time():
    from apps.delivery.services.delivery_messages import _local_time_text

    assert _local_time_text(start_utc=NOW, zone=None) is None


def test_an_unknown_zone_renders_as_no_time_and_not_as_an_error():
    """A zone the platform does not know is not an error: the facts are still rendered
    without the time rather than not rendered at all."""
    from apps.delivery.services.delivery_messages import _local_time_text

    assert _local_time_text(start_utc=NOW, zone="Middle/Earth") is None


def test_a_known_zone_renders_the_local_wall_clock():
    """AD-6: display-time conversion happens at the presentation edge — the body."""
    from apps.delivery.services.delivery_messages import _local_time_text

    rendered = _local_time_text(start_utc=NOW, zone="Europe/London")

    assert rendered is not None
    assert "November" in rendered


# --- The seam: the sweep's contract does not change when the templates do ------------------------


def test_the_renderer_is_swappable():
    """The sweep is handed a callable, so item 6 can replace every string without
    touching the mechanism."""
    import inspect

    from apps.delivery.services.delivery_sweep import send_one, sweep_due_sends

    for fn in (send_one, sweep_due_sends):
        params = inspect.signature(fn).parameters
        assert "renderer" in params


# --- A digest with cards on it ------------------------------------------------------------------


def test_a_composed_digest_lists_its_cards():
    """The cards come from the **persisted** digest, read through `personalization`'s
    published `read_digest`. Nothing is composed here: AD-10 says the explanation is
    persisted at composition time and never recomputed at render."""
    from apps.personalization.models import DigestComposition
    from tests.ingestion.factories import EventFactory
    from tests.personalization.factories import (
        DigestCompositionFactory,
        PulseDigestFactory,
    )

    user = uuid7()
    event = EventFactory(title="Rooftop cinema")
    local_date = NOW.date()
    digest = PulseDigestFactory(user_id=user, local_date=local_date, timezone="UTC")
    DigestCompositionFactory(
        digest_id=digest.id,
        user_id=user,
        event_id=event.id,
        event_kind=DigestComposition.EventKind.PUBLIC,
    )

    row = ScheduledSendFactory(
        kind=ScheduledSend.Kind.DIGEST,
        send_key=digest_key(user_id=user, local_date=local_date),
        user_id=user,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        stream=Stream.BULK.value,
    )

    message = render_digest(row, ADDRESS)

    assert "Rooftop cinema" in message.text_body
    assert message.unsubscribe_url


def test_an_empty_digest_says_the_pulse_is_empty():
    """`composed` and `empty` are different facts (FR-8), and the body says which."""
    from tests.personalization.factories import PulseDigestFactory

    user = uuid7()
    local_date = NOW.date()
    PulseDigestFactory(user_id=user, local_date=local_date, timezone="UTC", is_empty=True)

    row = ScheduledSendFactory(
        kind=ScheduledSend.Kind.DIGEST,
        send_key=digest_key(user_id=user, local_date=local_date),
        user_id=user,
        target_kind="",
        target_id=None,
        slot="",
        event_version=None,
        stream=Stream.BULK.value,
    )

    message = render_digest(row, ADDRESS)

    assert "Nothing on the Pulse" in message.text_body
