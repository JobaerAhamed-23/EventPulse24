"""The three mail bodies: reminder, digest, state-change notice (FR-11, AD-20).

**These tests need no fixture user, no network and no database.** That is the point of
the split: `email_templates` takes frozen dataclasses and reads nothing, so the bodies
can be asserted directly. A test that needed a database to check a body's wording would
be a test that could fail for the wrong reason.

The properties under test:

- Each renderer returns **both** a text body and an HTML body. Neither is optional.
- The **voice** is calm: no exclamation marks, no emoji, no urgency.
- The digest carries its cards, with the bucket and tags **in text** beside the stripe —
  colour is never the sole carrier of meaning.
- The digest's `unsubscribe_url` is always populated; the port refuses a bulk send
  without one.
- **No address reaches the body** (AD-13).
"""

from datetime import date

import pytest

from apps.delivery.services.email_templates import (
    DigestCardFacts,
    DigestFacts,
    ReminderFacts,
    StateNoticeFacts,
    render_digest,
    render_reminder,
    render_state_notice,
)
from ports.email import Stream

ADDRESS = "maya@example.com"


# --- Both bodies, always -------------------------------------------------------------------------


def test_the_reminder_has_both_bodies():
    message = render_reminder(
        ReminderFacts(
            title="Rooftop cinema",
            local_time_text="Friday 14 November, 19:30",
            location="The Barbican",
            slot="1d",
        ),
        to=ADDRESS,
    )

    assert message.text_body
    assert message.html_body


def test_the_digest_has_both_bodies():
    message = render_digest(
        DigestFacts(
            local_date=date(2026, 11, 14),
            city="London",
            cards=(),
            unsubscribe_url="https://eventpulse24.example/unsub?token=x",
            cta_url="https://eventpulse24.example/click?token=y",
        ),
        to=ADDRESS,
    )

    assert message.text_body
    assert message.html_body


def test_the_state_notice_has_both_bodies():
    message = render_state_notice(
        StateNoticeFacts(
            title="Rooftop cinema",
            change_kind="moved to a new time",
            local_time_text="Friday 14 November, 19:30",
        ),
        to=ADDRESS,
    )

    assert message.text_body
    assert message.html_body


# --- The voice -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "render",
    [
        lambda: render_reminder(
            ReminderFacts(
                title="Rooftop cinema",
                local_time_text="Friday 14 November, 19:30",
                location="The Barbican",
                slot="1d",
                unsubscribe_url="https://eventpulse24.example/unsub?token=x",
            ),
            to=ADDRESS,
        ),
        lambda: render_digest(
            DigestFacts(
                local_date=date(2026, 11, 14),
                city="London",
                cards=(
                    DigestCardFacts(
                        title="Rooftop cinema",
                        local_time_text="Friday 14 November, 19:30",
                        location="The Barbican",
                        bucket=4,
                        tags=("music", "outdoors"),
                        url="https://eventpulse24.example/events/1",
                    ),
                ),
                unsubscribe_url="https://eventpulse24.example/unsub?token=x",
                cta_url="https://eventpulse24.example/click?token=y",
            ),
            to=ADDRESS,
        ),
        lambda: render_state_notice(
            StateNoticeFacts(
                title="Rooftop cinema",
                change_kind="moved to a new time",
                local_time_text="Friday 14 November, 19:30",
            ),
            to=ADDRESS,
        ),
    ],
    ids=["reminder", "digest", "state_notice"],
)
def test_the_bodies_are_calm(render):
    """EXPERIENCE.md §3: calm, no exclamation marks, no emoji, no urgency.

    A mail that hypes is a mail the user learns to distrust, and a daily sender that hypes
    is a daily sender that gets filtered.

    **The HTML is checked with its markup stripped**, because `<!doctype html>` and a CSS
    declaration are not prose and an exclamation mark in a tag is not enthusiasm.
    """
    import re

    message = render()

    bodies = [message.subject, message.text_body]
    for html in (message.html_body,):
        # Strip tags, comments and doctype declarations; what is left is what a reader
        # actually sees.
        stripped = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
        stripped = re.sub(r"<[^>]+>", " ", stripped)
        bodies.append(stripped)

    for body in bodies:
        assert "!" not in body
        assert "🎉" not in body
        assert "urgent" not in body.lower()
        assert "hurry" not in body.lower()


def test_the_reminder_subject_says_what_the_mail_is():
    message = render_reminder(
        ReminderFacts(
            title="Rooftop cinema",
            local_time_text=None,
            location=None,
            slot="1d",
        ),
        to=ADDRESS,
    )

    assert message.subject == "Reminder: Rooftop cinema"


def test_the_digest_subject_says_what_the_mail_is():
    message = render_digest(
        DigestFacts(
            local_date=date(2026, 11, 14),
            city="London",
            cards=(),
            unsubscribe_url="https://eventpulse24.example/unsub?token=x",
            cta_url="https://eventpulse24.example/click?token=y",
        ),
        to=ADDRESS,
    )

    assert message.subject == "Your Pulse for 2026-11-14"


# --- A missing fact is stated, not hidden ---------------------------------------------------------


def test_a_reminder_without_a_title_says_the_event_was_saved():
    message = render_reminder(
        ReminderFacts(title=None, local_time_text=None, location=None, slot="1d"),
        to=ADDRESS,
    )

    assert "your saved event" in message.subject
    assert "your saved event" in message.text_body


def test_a_reminder_without_a_time_omits_the_time():
    message = render_reminder(
        ReminderFacts(
            title="Rooftop cinema",
            local_time_text=None,
            location=None,
            slot="1d",
        ),
        to=ADDRESS,
    )

    assert "When:" not in message.text_body
    assert "Rooftop cinema" in message.text_body


def test_a_card_without_a_title_says_an_event_was_saved():
    message = render_digest(
        DigestFacts(
            local_date=date(2026, 11, 14),
            city="London",
            cards=(
                DigestCardFacts(
                    title=None,
                    local_time_text=None,
                    location=None,
                    bucket=3,
                    tags=(),
                ),
            ),
            unsubscribe_url="https://eventpulse24.example/unsub?token=x",
            cta_url="https://eventpulse24.example/click?token=y",
        ),
        to=ADDRESS,
    )

    assert "an event you saved" in message.text_body


# --- The digest's cards --------------------------------------------------------------------------


def test_the_digest_carries_its_cards():
    message = render_digest(
        DigestFacts(
            local_date=date(2026, 11, 14),
            city="London",
            cards=(
                DigestCardFacts(
                    title="Rooftop cinema",
                    local_time_text="Friday 14 November, 19:30",
                    location="The Barbican",
                    bucket=4,
                    tags=("music", "outdoors"),
                    url="https://eventpulse24.example/events/1",
                ),
                DigestCardFacts(
                    title="Late night gallery",
                    local_time_text="Friday 14 November, 21:00",
                    location="Tate Modern",
                    bucket=2,
                    tags=("art",),
                    url="https://eventpulse24.example/events/2",
                ),
                DigestCardFacts(
                    title="Morning run",
                    local_time_text="Saturday 15 November, 08:00",
                    location="Parliament Hill",
                    bucket=5,
                    tags=("sport",),
                    url="https://eventpulse24.example/events/3",
                ),
            ),
            unsubscribe_url="https://eventpulse24.example/unsub?token=x",
            cta_url="https://eventpulse24.example/click?token=y",
        ),
        to=ADDRESS,
    )

    assert "Rooftop cinema" in message.text_body
    assert "Late night gallery" in message.text_body
    assert "Morning run" in message.text_body
    for title in ("Rooftop cinema", "Late night gallery", "Morning run"):
        assert title in message.html_body


def test_the_cards_carry_their_bucket_in_text():
    """**Colour is never the sole carrier of meaning.**

    The HTML card has a stripe; the bucket is also written out, so a reader whose client
    stripped the styles knows exactly what a reader who saw the colours knows.
    """
    message = render_digest(
        DigestFacts(
            local_date=date(2026, 11, 14),
            city="London",
            cards=(
                DigestCardFacts(
                    title="Rooftop cinema",
                    local_time_text=None,
                    location=None,
                    bucket=4,
                    tags=("music",),
                ),
            ),
            unsubscribe_url="https://eventpulse24.example/unsub?token=x",
            cta_url="https://eventpulse24.example/click?token=y",
        ),
        to=ADDRESS,
    )

    assert "Fit: 4 of 5" in message.text_body
    assert "4 of 5" in message.html_body


def test_the_cards_carry_their_tags_in_text():
    message = render_digest(
        DigestFacts(
            local_date=date(2026, 11, 14),
            city="London",
            cards=(
                DigestCardFacts(
                    title="Rooftop cinema",
                    local_time_text=None,
                    location=None,
                    bucket=4,
                    tags=("music", "outdoors"),
                ),
            ),
            unsubscribe_url="https://eventpulse24.example/unsub?token=x",
            cta_url="https://eventpulse24.example/click?token=y",
        ),
        to=ADDRESS,
    )

    assert "music" in message.text_body
    assert "outdoors" in message.text_body
    assert "music" in message.html_body


def test_an_empty_digest_says_the_pulse_is_empty():
    message = render_digest(
        DigestFacts(
            local_date=date(2026, 11, 14),
            city="London",
            cards=(),
            unsubscribe_url="https://eventpulse24.example/unsub?token=x",
            cta_url="https://eventpulse24.example/click?token=y",
        ),
        to=ADDRESS,
    )

    assert "Nothing on the Pulse" in message.text_body
    assert "Nothing on the Pulse" in message.html_body


# --- RFC 8058 ------------------------------------------------------------------------------------


def test_the_digest_always_carries_an_unsubscribe_url():
    """**The bulk path never raises at the port.** `EmailPort.send` refuses a bulk send
    with no unsubscribe URL, so the renderer always supplies one."""
    from adapters.email.memory import InMemoryEmailAdapter

    message = render_digest(
        DigestFacts(
            local_date=date(2026, 11, 14),
            city=None,
            cards=(),
            unsubscribe_url="https://eventpulse24.example/unsub?token=x",
            cta_url="https://eventpulse24.example/click?token=y",
        ),
        to=ADDRESS,
    )
    port = InMemoryEmailAdapter()

    port.send(message, stream=Stream.BULK, idempotency_key="digest:2026-11-14")

    assert len(port.sent) == 1


def test_the_reminder_carries_no_stream_level_unsubscribe_url():
    """RFC 8058 is a requirement of the **bulk** stream. Telling a user they can stop
    mail they never subscribed to as a list would be a lie."""
    message = render_reminder(
        ReminderFacts(
            title="Rooftop cinema",
            local_time_text=None,
            location=None,
            slot="1d",
            unsubscribe_url="https://eventpulse24.example/unsub?token=x",
        ),
        to=ADDRESS,
    )

    assert message.unsubscribe_url is None
    # The event's own link is in the **body**, where the user expects to find it.
    assert "https://eventpulse24.example/unsub?token=x" in message.text_body


def test_the_state_notice_carries_no_unsubscribe_url():
    message = render_state_notice(
        StateNoticeFacts(
            title="Rooftop cinema",
            change_kind="moved to a new time",
            local_time_text="Friday 14 November, 19:30",
        ),
        to=ADDRESS,
    )

    assert message.unsubscribe_url is None


# --- No PII (AD-13) ------------------------------------------------------------------------------


def test_the_address_reaches_only_the_recipient_field():
    """AD-13: the address is in `to` and nowhere else. A subject that quoted the address
    would put it in the mail client's notification bar, in a lock screen, and in a list of
    every subject the client has ever shown."""
    message = render_reminder(
        ReminderFacts(
            title="Rooftop cinema",
            local_time_text=None,
            location=None,
            slot="1d",
        ),
        to=ADDRESS,
    )

    assert message.to == ADDRESS
    assert ADDRESS not in message.subject
    assert ADDRESS not in message.text_body
    assert ADDRESS not in message.html_body


# --- The state notice is rendered but not minted -------------------------------------------------


def test_the_state_notice_says_what_changed_and_what_it_was():
    message = render_state_notice(
        StateNoticeFacts(
            title="Rooftop cinema",
            change_kind="moved to a new time",
            local_time_text="Friday 14 November, 19:30",
            previous_time_text="Friday 14 November, 18:00",
            location="The Barbican",
        ),
        to=ADDRESS,
    )

    assert message.subject == "Update: Rooftop cinema"
    assert "moved to a new time" in message.text_body
    assert "Friday 14 November, 19:30" in message.text_body
    assert "Friday 14 November, 18:00" in message.text_body


def test_the_state_notice_is_not_minted_by_the_delivery_app():
    """**Rendered but not minted** — FR-53/54 is the next intent's work.

    The body exists so that intent is an API and a trigger rather than a fresh template
    pass, and this test says so: nothing outside the model that declares the kind may
    mint a `state_notice` send yet.
    """
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]
    # The declaration itself is allowed in exactly one file — the model that declares it.
    declaration = backend / "apps" / "delivery" / "models.py"
    offenders = [
        str(path.relative_to(backend))
        for path in (backend / "apps").rglob("*.py")
        if path != declaration and "STATE_NOTICE" in path.read_text()
    ]

    assert offenders == [], f"A state notice must not be minted yet: {offenders}"
