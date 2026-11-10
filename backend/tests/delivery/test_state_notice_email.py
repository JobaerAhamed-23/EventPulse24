"""FR-54's state-change email: the four subjects the PRD wrote, and the body that earns them.

**What this file proves.** FR-54 fixes the copy *verbatim*, which is unusual and makes the
subjects a contract rather than a preference. So:

- **one test per kind, asserting the literal subject string** — a well-meaning rewrite
  fails rather than ships;
- **the body says what changed and what it means for the user's reminders**, because the
  reminder consequence is the reason the email is correctness-critical rather than
  informational;
- **the title is rendered safely** — an ingested string cannot inject into the subject line
  and cannot escape into the HTML body;
- **a missing name degrades** to something legible rather than `EventPulse24: was
  cancelled.`;
- **a muted event produces no send at all.**

**Why the subject tests are here and not in `domain/notices.py`'s own tests.** The
vocabulary — which kind says what — lives in `domain.notices`, because the renderer, the
service that decides whether there is a notice at all, and the tests all need the same
answers, and a subject written twice is a subject that drifts. These tests are the
*contract*: they assert the PRD's literal strings against the whole rendering path, so
"the vocabulary is right" and "the mail that goes out says it" cannot come apart.

---

## The subjects, and whose they are

| subject | for | whose |
|---|---|---|
| `EventPulse24: [event name] was cancelled.` | a cancellation | PRD verbatim |
| `EventPulse24: [event name] was moved to [new date].` | a postponement or a time move | PRD |
| `EventPulse24: [event name] moved to [new location].` | **a venue move** | PRD verbatim |
| `EventPulse24: [event name] is sold out.` | a sell-out | PRD verbatim |
| `EventPulse24: [event name] was replaced by a new event.` | a supersede | ours |
| `EventPulse24: [event name] is back on.` | a reinstatement | ours |

**The PRD's third subject has no kind of its own.** `domain.lifecycle.classify_change` files
a venue move under `detail_changed`, because `venue_fingerprint` is one of its detail facts.
So "moved to [new location]" is a `detail_changed` — and a `detail_changed` that fixed a
typo is not notified at all. **The rule is about the change, not the kind.**
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from apps.delivery.models import ScheduledSend
from apps.delivery.send_keys import state_notice_key
from apps.delivery.services.delivery_messages import renderer_for
from apps.delivery.services.email_templates import (
    StateNoticeFacts,
    render_state_notice,
)
from apps.delivery.services.mutes import mute_event_notices
from apps.delivery.services.state_notices import raise_state_notice
from domain.lifecycle import ChangeKind
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

ADDRESS = "maya@example.com"
NOW = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)


# --- One test per kind, asserting the literal subject ----------------------------------------


def test_a_cancellation_says_the_prds_subject():
    """FR-54: `EventPulse24: [event name] was cancelled.`"""
    message = render_state_notice(
        StateNoticeFacts(title="Rooftop cinema", change_kind=ChangeKind.CANCELLED.value),
        to=ADDRESS,
    )

    assert message.subject == "EventPulse24: Rooftop cinema was cancelled."


def test_a_postponement_says_the_prds_subject():
    """FR-54: `EventPulse24: [event name] was moved to [new date].`"""
    message = render_state_notice(
        StateNoticeFacts(
            title="Rooftop cinema",
            change_kind=ChangeKind.POSTPONED.value,
            new_time_text="Friday 21 November, 19:30",
        ),
        to=ADDRESS,
    )

    assert message.subject == "EventPulse24: Rooftop cinema was moved to Friday 21 November, 19:30."


def test_a_time_move_says_the_prds_subject():
    """FR-54: `EventPulse24: [event name] was moved to [new date].`

    **The same subject as a postponement**, because the PRD gives them the same one — a
    postponement *is* a time move, recorded under its own kind so the send machinery can
    tell the two apart.
    """
    message = render_state_notice(
        StateNoticeFacts(
            title="Rooftop cinema",
            change_kind=ChangeKind.TIME_MOVED.value,
            new_time_text="Friday 21 November, 19:30",
        ),
        to=ADDRESS,
    )

    assert message.subject == "EventPulse24: Rooftop cinema was moved to Friday 21 November, 19:30."


def test_a_sell_out_says_the_prds_subject():
    """FR-54: `EventPulse24: [event name] is sold out.`"""
    message = render_state_notice(
        StateNoticeFacts(title="Rooftop cinema", change_kind=ChangeKind.SOLD_OUT.value),
        to=ADDRESS,
    )

    assert message.subject == "EventPulse24: Rooftop cinema is sold out."


def test_a_venue_move_says_the_prds_subject():
    """FR-54: `EventPulse24: [event name] moved to [new location].`

    **This is the PRD's third subject, and it belongs to a `detail_changed`** — because
    `venue_fingerprint` is one of that kind's facts. The subject is built from the kind, so
    a `detail_changed` gets it; what decides whether it is *sent* is whether the change
    actually moved the venue.
    """
    message = render_state_notice(
        StateNoticeFacts(
            title="Rooftop cinema",
            change_kind=ChangeKind.DETAIL_CHANGED.value,
            venue_name="Tate Modern",
        ),
        to=ADDRESS,
    )

    assert message.subject == "EventPulse24: Rooftop cinema moved to Tate Modern."


def test_a_supersede_says_our_subject():
    """The PRD names no subject for a supersede. This one is ours, in the PRD's register.

    **A supersede is not a move.** The event was replaced by a *different* one, so the
    subject says so rather than naming a time that is not the user's any more.
    """
    message = render_state_notice(
        StateNoticeFacts(title="Rooftop cinema", change_kind=ChangeKind.SUPERSEDED.value),
        to=ADDRESS,
    )

    assert message.subject == "EventPulse24: Rooftop cinema was replaced by a new event."


def test_a_reinstatement_says_our_subject():
    """The PRD names no subject for a reinstatement. This one is ours.

    **"is back on", not "was moved to"** — a reinstatement is the event being back at the
    time it was already at, and "was moved to" would name a move that did not happen.
    """
    message = render_state_notice(
        StateNoticeFacts(title="Rooftop cinema", change_kind=ChangeKind.REINSTATED.value),
        to=ADDRESS,
    )

    assert message.subject == "EventPulse24: Rooftop cinema is back on."


def test_every_kind_has_a_subject():
    """**A kind with no subject is a programming error, not a generic subject.**

    A notice reading "your saved event was cancelled" about an event that was not
    cancelled is worse than a notice that did not go out, because the user reads it.
    """
    from domain.notices import NOTICE_SUBJECTS

    assert set(NOTICE_SUBJECTS) == {kind.value for kind in ChangeKind}


def test_an_unknown_kind_raises_rather_than_producing_a_generic_subject():
    """A kind `domain.lifecycle` gained without the vocabulary learning it."""
    with pytest.raises(KeyError):
        render_state_notice(
            StateNoticeFacts(title="Rooftop cinema", change_kind="invented_kind"),
            to=ADDRESS,
        )


# --- The body: what changed, and what it means ------------------------------------------------


def test_the_body_says_what_changed_and_what_it_means_for_the_reminders():
    """FR-54's body requirement, in one assertion.

    **The reminder consequence is derived, not written out.** The body's line about the
    user's reminders must be the same promise the send machinery kept — if the body said
    "your reminders have been cancelled" while the reminders still fired, that would be
    exactly the bug class this whole intent exists to prevent.
    """
    from domain.notices import reminder_consequence

    message = render_state_notice(
        StateNoticeFacts(
            title="Rooftop cinema",
            change_kind=ChangeKind.TIME_MOVED.value,
            new_time_text="Friday 21 November, 19:30",
            previous_time_text="Friday 14 November, 19:30",
            reminder_consequence=reminder_consequence(ChangeKind.TIME_MOVED.value),
        ),
        to=ADDRESS,
    )

    assert "Friday 21 November, 19:30" in message.text_body
    assert "Friday 14 November, 19:30" in message.text_body
    assert "Your reminders have been rescheduled to the new time." in message.text_body


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (ChangeKind.CANCELLED, "Your reminders for this event have been cancelled."),
        (ChangeKind.SUPERSEDED, "Your reminders for this event have been cancelled."),
        (ChangeKind.POSTPONED, "Your reminders have been rescheduled to the new time."),
        (ChangeKind.TIME_MOVED, "Your reminders have been rescheduled to the new time."),
        (ChangeKind.REINSTATED, "Your reminders are back on."),
        (ChangeKind.SOLD_OUT, "Your reminders are unchanged."),
        (ChangeKind.DETAIL_CHANGED, "Your reminders are unchanged."),
    ],
)
def test_the_reminder_consequence_agrees_with_the_send_behaviour(kind, expected):
    """**The body cannot promise something the send machinery did not do.**

    `LIFECYCLE_SEND_BEHAVIOUR` is the table the sends already follow: `CANCEL` cancels the
    reminders, `REMINT` re-mints them, `KEEP` leaves them. The body's line is derived from
    it, so the two cannot drift.

    **`reinstated` overrides the derivation, and says so.** It is `REMINT` — the reminders
    are re-minted — but "rescheduled to the new time" is a sentence about a *new time*, and
    a reinstatement is not a new time: the event is back at the time it was already at. So
    it says the reminders are back on.
    """
    from domain.notices import reminder_consequence

    assert reminder_consequence(kind.value) == expected


def test_a_cancellation_body_says_the_reminders_are_cancelled():
    message = render_state_notice(
        StateNoticeFacts(
            title="Rooftop cinema",
            change_kind=ChangeKind.CANCELLED.value,
            reminder_consequence="Your reminders for this event have been cancelled.",
        ),
        to=ADDRESS,
    )

    assert "Your reminders for this event have been cancelled." in message.text_body
    assert "Your reminders for this event have been cancelled." in message.html_body


def test_a_sold_out_body_says_the_reminders_are_unchanged():
    """**Worth saying.** A user who bought a ticket needs to know the reminder is still
    coming — a sell-out cancels nothing."""
    message = render_state_notice(
        StateNoticeFacts(
            title="Rooftop cinema",
            change_kind=ChangeKind.SOLD_OUT.value,
            reminder_consequence="Your reminders are unchanged.",
        ),
        to=ADDRESS,
    )

    assert "Your reminders are unchanged." in message.text_body


def test_the_body_links_to_the_detail_screen():
    """**A link to the event's Detail screen, where the banner and the mute live.**

    The mute is the opt-out for FR-54's notices, and it is on the Detail Screen — so the
    body is where the user is sent to find it.
    """
    message = render_state_notice(
        StateNoticeFacts(
            title="Rooftop cinema",
            change_kind=ChangeKind.CANCELLED.value,
            detail_url="https://eventpulse24.example/events/abc",
        ),
        to=ADDRESS,
    )

    assert "https://eventpulse24.example/events/abc" in message.text_body
    assert "https://eventpulse24.example/events/abc" in message.html_body


def test_the_notice_carries_no_unsubscribe_url():
    """**No unsubscribe URL on a transactional send, and no footer implying one exists.**

    RFC 8058 is a requirement of the *bulk* stream (AD-20). A state notice is a one-time
    correction about a record the user created themselves — not a broadcast — so it
    carries none.
    """
    message = render_state_notice(
        StateNoticeFacts(title="Rooftop cinema", change_kind=ChangeKind.CANCELLED.value),
        to=ADDRESS,
    )

    assert message.unsubscribe_url is None
    assert "unsubscribe" not in message.text_body.lower()
    assert "unsubscribe" not in message.html_body.lower()


def test_the_notice_offers_no_reminder_opt_out_link():
    """**The reminder body's "stop reminders for this event" link does not belong here.**

    It would be a lie twice over: the mail is not a reminder, and the change it reports may
    have cancelled the reminders already. The mute lives on the Detail Screen, and the body
    points there.
    """
    message = render_state_notice(
        StateNoticeFacts(
            title="Rooftop cinema",
            change_kind=ChangeKind.CANCELLED.value,
            detail_url="https://eventpulse24.example/events/abc",
        ),
        to=ADDRESS,
    )

    assert "Stop reminders for this event" not in message.text_body


# --- The name: folded, escaped, and never empty -------------------------------------------------


def test_a_name_with_a_newline_cannot_inject_a_header():
    """**SMTP header injection.** A `\\n` in the subject would end the `Subject:` header
    and let the rest of the name become headers of its own."""
    from domain.notices import fold_title

    folded = fold_title("Rooftop cinema\nBcc: somebody@example.com")

    assert "\n" not in folded
    assert "\r" not in folded


def test_a_name_with_a_newline_produces_a_single_line_subject():
    """**The end-to-end version: through the renderer, not just the fold.**

    A fold that lived only in the vocabulary would leave the renderer free to quote the
    raw name — so the assertion is on the subject that goes on the wire.
    """
    from domain.notices import fold_title

    message = render_state_notice(
        StateNoticeFacts(
            title=fold_title("Rooftop cinema\nBcc: somebody@example.com"),
            change_kind=ChangeKind.CANCELLED.value,
        ),
        to=ADDRESS,
    )

    assert "\n" not in message.subject
    assert message.subject == (
        "EventPulse24: Rooftop cinema Bcc: somebody@example.com was cancelled."
    )


def test_a_name_with_markup_is_escaped_in_the_html_body():
    """**Untrusted source text may be served, never injected.**

    The title is whatever the source said, and Django escapes it in the template because
    the template never marks it safe.
    """
    message = render_state_notice(
        StateNoticeFacts(
            title="<script>alert(1)</script>",
            change_kind=ChangeKind.CANCELLED.value,
        ),
        to=ADDRESS,
    )

    assert "<script>alert(1)</script>" not in message.html_body
    assert "&lt;script&gt;" in message.html_body


def test_a_missing_name_degrades_to_something_legible():
    """**Not `EventPulse24: was cancelled.`** — a sentence about nothing, which the user
    cannot tell apart from any other notice."""
    message = render_state_notice(
        StateNoticeFacts(title=None, change_kind=ChangeKind.CANCELLED.value),
        to=ADDRESS,
    )

    assert message.subject == "EventPulse24: your saved event was cancelled."
    assert "your saved event" in message.text_body


def test_a_whitespace_only_name_degrades_to_something_legible():
    """**The fold runs first, and the fallback after it.** A name of three spaces folds
    to nothing, and "nothing" is not a name."""
    from domain.notices import fold_title

    assert fold_title("   ") is None

    message = render_state_notice(
        StateNoticeFacts(title=fold_title("   "), change_kind=ChangeKind.CANCELLED.value),
        to=ADDRESS,
    )

    assert message.subject == "EventPulse24: your saved event was cancelled."


def test_the_subject_and_the_body_quote_the_same_name():
    """**One name, folded once.** If the subject folded and the body did not, the mail
    would say one thing in its subject line and another in its body."""
    from domain.notices import fold_title

    message = render_state_notice(
        StateNoticeFacts(
            title=fold_title("Rooftop\ncinema"),
            change_kind=ChangeKind.CANCELLED.value,
        ),
        to=ADDRESS,
    )

    assert message.subject == "EventPulse24: Rooftop cinema was cancelled."
    assert "Rooftop cinema" in message.text_body


# --- The mute: no send at all ------------------------------------------------------------------


def test_a_muted_event_produces_no_send():
    """**The mute is the opt-out, and it stops the whole notice.**

    Not just the email — the notice row itself, because the in-app strip is the notice's
    other half and a strip entry with no email behind it is a claim the product cannot
    keep.
    """
    from apps.delivery.models import StateChangeNotice

    user_id = uuid7()
    event_id = uuid7()
    mute_event_notices(user_id=user_id, event_id=event_id, actor=Actor.user(user_id), now=NOW)

    raised = raise_state_notice(
        user_id=user_id,
        event_id=event_id,
        state_change_id=uuid7(),
        change_kind=ChangeKind.SOLD_OUT.value,
        event_version=2,
        event_start_utc=datetime(2026, 11, 20, 3, 0, tzinfo=UTC),
        actor=Actor.system("propagation"),
        now=NOW,
    )

    assert raised is False
    assert StateChangeNotice.objects.using(PERSONAL).filter(user_id=user_id).count() == 0
    assert (
        ScheduledSend.objects.using(PERSONAL)
        .filter(user_id=user_id, kind=ScheduledSend.Kind.STATE_NOTICE)
        .count()
        == 0
    )


def test_a_muted_event_still_gets_a_cancellation():
    """**The terminal exception.** A mute means "stop telling me about tweaks to this
    event" — not "do not tell me it is off". FR-55 has already removed the event from the
    digest, so silence here is the one failure with no second channel to catch it."""
    from apps.delivery.models import StateChangeNotice

    user_id = uuid7()
    event_id = uuid7()
    mute_event_notices(user_id=user_id, event_id=event_id, actor=Actor.user(user_id), now=NOW)

    raised = raise_state_notice(
        user_id=user_id,
        event_id=event_id,
        state_change_id=uuid7(),
        change_kind=ChangeKind.CANCELLED.value,
        event_version=2,
        event_start_utc=datetime(2026, 11, 20, 3, 0, tzinfo=UTC),
        actor=Actor.system("propagation"),
        now=NOW,
    )

    assert raised is True
    assert StateChangeNotice.objects.using(PERSONAL).filter(user_id=user_id).count() == 1


# --- The whole path: a row becomes a mail ---------------------------------------------------------


def test_a_state_notice_row_renders_the_prds_subject():
    """**The whole path, not just the renderer.** A row on the wire, through the dispatch,
    with the change's own facts — so "the vocabulary is right" and "the mail that goes out
    says it" cannot come apart."""
    from apps.ingestion.models import EventStateChange
    from tests.ingestion.factories import EventFactory, EventStateChangeFactory

    event = EventFactory(title="Rooftop cinema")
    change = EventStateChangeFactory(
        event=event,
        kind=EventStateChange.Kind.CANCELLED,
        event_version=2,
        before={"status": "scheduled"},
        after={"status": "cancelled"},
    )
    user_id = uuid7()
    row = _notice_row(user_id=user_id, event_id=event.id, state_change_id=change.id)

    message = renderer_for(row, ADDRESS)

    assert message.subject == "EventPulse24: Rooftop cinema was cancelled."


def test_a_state_notice_row_is_not_rendered_as_a_reminder():
    """**A notice is not a reminder, and it must not wear a reminder's clothes.**

    The transactional renderer would give it "Reminder: Rooftop cinema" and a per-event
    unsubscribe link — the second one worse than wrong, because it would offer to stop
    reminders for an event whose reminders the change already cancelled.
    """
    from apps.ingestion.models import EventStateChange
    from tests.ingestion.factories import EventFactory, EventStateChangeFactory

    event = EventFactory(title="Rooftop cinema")
    change = EventStateChangeFactory(
        event=event,
        kind=EventStateChange.Kind.CANCELLED,
        event_version=2,
        before={"status": "scheduled"},
        after={"status": "cancelled"},
    )
    row = _notice_row(user_id=uuid7(), event_id=event.id, state_change_id=change.id)

    message = renderer_for(row, ADDRESS)

    assert not message.subject.startswith("Reminder:")
    assert message.unsubscribe_url is None
    assert "Stop reminders for this event" not in message.text_body


def test_a_venue_move_row_renders_the_prds_third_subject():
    """**The PRD's third subject, end to end.**

    The change moved the venue — the fingerprints differ — so the notice is raised, and
    the subject names the **new** place. The old place is not nameable: a fingerprint is a
    hash, and a hash cannot be reversed to a name.
    """
    from apps.ingestion.models import EventStateChange
    from tests.ingestion.factories import EventFactory, EventStateChangeFactory

    event = EventFactory(title="Rooftop cinema")
    change = EventStateChangeFactory(
        event=event,
        kind=EventStateChange.Kind.DETAIL_CHANGED,
        event_version=2,
        before={"venue_fingerprint": "sha256:old"},
        after={"venue_fingerprint": "sha256:new"},
    )
    row = _notice_row(user_id=uuid7(), event_id=event.id, state_change_id=change.id)

    message = renderer_for(row, ADDRESS)

    assert message.subject.startswith("EventPulse24: Rooftop cinema moved to ")


def test_a_time_move_row_says_the_new_time_in_the_subject():
    """**The new date is in the subject, in the user's local wall clock.**

    AD-6: the conversion happens at the presentation edge, and the subject line is one.
    """
    from apps.ingestion.models import EventStateChange
    from tests.ingestion.factories import EventFactory, EventStateChangeFactory

    event = EventFactory(title="Rooftop cinema", start_time_tz="Europe/London")
    change = EventStateChangeFactory(
        event=event,
        kind=EventStateChange.Kind.TIME_MOVED,
        event_version=2,
        before={"start_utc": "2026-11-14T19:00:00+00:00", "start_time_tz": "Europe/London"},
        after={"start_utc": "2026-11-21T19:00:00+00:00", "start_time_tz": "Europe/London"},
    )
    row = _notice_row(user_id=uuid7(), event_id=event.id, state_change_id=change.id)

    message = renderer_for(row, ADDRESS)

    assert message.subject.startswith("EventPulse24: Rooftop cinema was moved to ")
    assert "21 November" in message.subject


def test_the_catalog_is_read_once_per_notice(monkeypatch):
    """**One read of the event, not two.**

    The renderer needs the event's name, its venue and its zone. Reading it once and
    passing it down is not only cheaper — a second read is a second *answer*, and a row
    that changed between the two reads could give the notice a name from one moment and
    a zone from another.

    This is the same lesson `propagation-consumer` learned: a catalog read on the path
    that scales with the saver count is worth hoisting, and hoisting it means there is
    exactly one of it.
    """
    from apps.ingestion.models import EventStateChange
    from apps.ingestion.services import catalog_read
    from tests.ingestion.factories import EventFactory, EventStateChangeFactory

    calls: list[UUID] = []
    real = catalog_read.get_public_event

    def counting(*, event_id):
        calls.append(event_id)
        return real(event_id=event_id)

    monkeypatch.setattr(catalog_read, "get_public_event", counting)

    event = EventFactory(title="Rooftop cinema", start_time_tz="Europe/London")
    change = EventStateChangeFactory(
        event=event,
        kind=EventStateChange.Kind.CANCELLED,
        event_version=2,
        before={"status": "scheduled"},
        after={"status": "cancelled"},
    )
    row = _notice_row(user_id=uuid7(), event_id=event.id, state_change_id=change.id)

    renderer_for(row, ADDRESS)

    assert calls == [event.id]


def _notice_row(*, user_id, event_id, state_change_id):
    """A pending `state_notice` row, keyed the way AD-7 keys it."""
    from tests.delivery.factories import ScheduledSendFactory

    return ScheduledSendFactory(
        kind=ScheduledSend.Kind.STATE_NOTICE,
        target_kind="saved_event",
        target_id=event_id,
        slot="",
        event_version=None,
        user_id=user_id,
        send_key=state_notice_key(user_id=user_id, state_change_id=state_change_id),
    )
