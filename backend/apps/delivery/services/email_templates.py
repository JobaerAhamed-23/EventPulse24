"""The three mail bodies: reminder, digest, state-change notice (FR-11, FR-10, AD-20).

**These renderers are pure.** They take frozen dataclasses in and return an `EmailMessage`
out. No clock, no database, no request, no model instance. That is not a style preference —
it is what makes the bodies testable at all: the work item asks for rendering that is
"snapshot-tested: no clock, no database reads inside the renderer, so bodies are asserted
without a network or a fixture user."

**The facts come in, already gathered.** Which event, which cards, which time — all of that
is somebody else's job, read through published interfaces (AD-3, AD-16). The existing
`delivery_messages._facts_for` does that gathering, and it keeps doing it. This module only
turns facts into words.

---

## The three bodies

| body | stream | unsubscribe | minted in MVP |
|---|---|---|---|
| reminder | transactional | **that event's reminders** | yes |
| digest | **bulk** | **the Pulse Ping** | yes |
| state notice | transactional | — | yes — `scheduled_sends.mint_state_notice` |

**The state-change notice is rendered *and* minted.** `scheduled_sends.mint_state_notice`
mints it and `state_notices.raise_state_notice` raises it, which is what
`worker.propagation` calls — the AD-17 consumer. **Its subject is FR-54's, verbatim**,
and the vocabulary that decides which subject a kind gets lives in `domain.notices` — one
place, read by this renderer and by the tests that assert the PRD's literal strings.

---

## Both bodies, always

`EmailMessage.html_body` is `str | None`, so a text-only message is representable. **It must
not happen here.** The work item is explicit: each renderer returns *both* a `text_body` and
an `html_body`, "because a text-only client is not an error state" — a mail client that
cannot render HTML should get a readable text body, not an empty half.

---

## The voice

EXPERIENCE.md §3: calm, no exclamation marks, no emoji, no urgency. The subjects are plain
and say what the mail is — "Reminder: Rooftop cinema", "Your Pulse for 2026-11-14" — not
"🎉 Your event is coming up!!". A mail that hypes is a mail the user learns to distrust,
and a daily sender that hypes is a daily sender that gets filtered.

**A missing fact is stated, not hidden.** If the catalog has dropped the event, the body says
"the event you saved" rather than inventing a title, and a blank line where a title should be
looks like a bug in the product rather than in the catalog.

**An untrusted name is folded before it is quoted.** The event's title comes from an
ingested source record, so it is whatever the source said — and a `\n` in it would end
the `Subject:` header and turn the rest of the title into headers of its own. The fold
is `domain.notices.fold_title`, and it is applied **before** the facts reach this
module, so the subject and the body quote the same name and cannot disagree about it.

---

## Colour is never the sole carrier of meaning

The digest's cards carry a bucket (1–5 dots) and tags. On the web the colour and the label
travel together, and the rule is that colour never carries meaning alone. **The same rule
holds in email** — and email is where it matters more, because a mail client may render the
HTML with a different palette, or a client may strip styles entirely.

So every card in the HTML body carries its bucket and its tags **in text**, next to the
stripe. A reader who sees nothing but the text still knows the same thing a reader who sees
the colours does.

---

## No address leaves this module (AD-13)

The renderer is given the recipient's address and puts it in `EmailMessage.to`. That is the
address's one legitimate destination. It is never logged, never put in an audit `details`
dict, and never used to build a subject — a subject that quoted the address would put it in
the mail client's notification bar, in a lock screen, and in a list of every subject the
client has ever shown.
"""

from dataclasses import dataclass
from datetime import date

from django.template.loader import render_to_string

from domain.notices import MISSING_TITLE, notice_subject
from ports.email import EmailMessage

#: The templates' directory, relative to the app's `templates/` root.
_TEMPLATE_DIR = "delivery"


@dataclass(frozen=True)
class ReminderFacts:
    """What a reminder body quotes.

    Plain data, never a model instance — the same discipline as `catalog_read.PublicEvent`
    and `notification_preferences.NotificationSettings`. A caller that received the model
    could write it, and `delivery` is not the writer of the tables these facts come from
    (AD-16).
    """

    #: The event's name. `None` when the catalog has dropped it.
    title: str | None
    #: The start, already rendered as local wall-clock text (AD-6: the conversion happens
    #: at the presentation edge, and this **is** the presentation edge).
    local_time_text: str | None
    location: str | None
    #: The reminder slot, in the plan's own vocabulary (`1d`, `1hr`).
    slot: str | None
    #: The link that stops **this event's** reminders. `None` for a message that is not
    #: about one event.
    unsubscribe_url: str | None = None


@dataclass(frozen=True)
class DigestCardFacts:
    """One Pulse Card, as the digest body renders it."""

    title: str | None
    local_time_text: str | None
    location: str | None
    #: The relevance bucket, 1–5. It is carried as **words** beside the stripe, so the
    #: colour is never the only thing carrying it.
    bucket: int
    #: The persisted tags, in their persisted order (AD-10: never recomputed, never
    #: re-sorted — the order is the priority order).
    tags: tuple[str, ...]
    #: Where the card goes when clicked. `None` for a card with no link.
    url: str | None = None


@dataclass(frozen=True)
class DigestFacts:
    """What the digest body quotes."""

    local_date: date
    city: str | None
    cards: tuple[DigestCardFacts, ...]
    #: The link that stops **the Pulse Ping**. Always present on a bulk message — the port
    #: refuses a bulk send without one (AD-20, RFC 8058).
    unsubscribe_url: str
    #: The digest's call to action. A server-side tracked link, because SM-2 measures the
    #: click and rejects open-pixel measurement as unreliable.
    cta_url: str


@dataclass(frozen=True)
class StateNoticeFacts:
    """What a state-change notice quotes.

    Minted by `scheduled_sends.mint_state_notice` and raised by
    `state_notices.raise_state_notice` (FR-54).

    **The facts are the change's, not the live event's.** A poll appends one
    `EVENT_STATE_CHANGE` per kind, so the live event already holds the *last* kind's
    facts; pairing a change's version with those times would state a move that never
    happened. So `new_time_text` and `previous_time_text` come from the change's own
    `after`/`before`, and `venue_name` comes from the catalog *now* — a venue move has no
    name in the change row, because a fingerprint cannot be reversed to a name.

    **The title is already folded.** `domain.notices.fold_title` did it, and it did it
    before the value reached this dataclass, so the subject and the body quote the same
    name — a body that escaped the fold and a subject that did not would make the mail
    say two different things.
    """

    #: The event's name, folded. `None` when the catalog has no name to give — the
    #: renderer then says `domain.notices.MISSING_TITLE`.
    title: str | None
    #: The change's kind, in `domain.lifecycle.ChangeKind`'s vocabulary. The subject is
    #: built from it, so a kind this module has not been taught raises rather than
    #: producing a generic subject.
    change_kind: str
    #: The new start, already in local wall-clock text. `None` when the change carried no
    #: new time — a cancellation, a sell-out.
    new_time_text: str | None = None
    #: The old start, so the notice can say what it was before. `None` when there was
    #: none.
    previous_time_text: str | None = None
    #: The venue's name, resolved from the catalog at render time. `None` when the
    #: catalog holds no venue, or the change did not move one.
    venue_name: str | None = None
    #: The link to the event's Detail Screen, where the banner and the mute live.
    detail_url: str | None = None
    #: What the change means for the user's reminders. Derived from
    #: `LIFECYCLE_SEND_BEHAVIOUR` by `domain.notices.reminder_consequence`, so the body
    #: cannot promise something the send machinery did not do.
    reminder_consequence: str | None = None


def _render(template: str, context: dict) -> str:
    """Render one template and strip the trailing newline.

    The `.strip()` matters: Django's template loader keeps the file's final newline, and a
    body ending in `\n\n` is a body that differs from the one a snapshot was taken of for
    no reason a reader could see.
    """
    return render_to_string(f"{_TEMPLATE_DIR}/{template}", context).strip()


def _render_both(template: str, context: dict) -> tuple[str, str]:
    """Render a template's text and HTML forms.

    **Both, always.** The work item is explicit that neither is optional: "a text-only
    client is not an error state". So the pair is rendered together and neither can be
    forgotten.
    """
    return _render(f"{template}.txt", context), _render(f"{template}.html", context)


def render_reminder(facts: ReminderFacts, *, to: str) -> EmailMessage:
    """Render a reminder.

    **A transactional message, with this event's own unsubscribe link.** FR-11: the link
    stops "that event's reminders" and explicitly *does not* unsubscribe from the Pulse
    Ping. So the link it carries is the event scope, and never the Ping's.

    The subject is plain and says what the mail is. It does not carry the address, the
    send key, or an exclamation mark.
    """
    title = facts.title or "your saved event"
    subject = f"Reminder: {title}"
    text_body, html_body = _render_both(
        "reminder",
        {
            "title": facts.title,
            "display_title": title,
            "local_time_text": facts.local_time_text,
            "location": facts.location,
            "slot": facts.slot,
            "unsubscribe_url": facts.unsubscribe_url,
        },
    )
    return EmailMessage(
        to=to,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        # The transactional stream does not carry a stream-level unsubscribe URL. RFC 8058
        # is a requirement of the *bulk* stream; the reminder's own link is in the body,
        # scoped to this event.
        unsubscribe_url=None,
    )


def render_digest(facts: DigestFacts, *, to: str) -> EmailMessage:
    """Render the day's Pulse Digest.

    **A bulk message, and the unsubscribe URL is always populated.** `EmailPort.send`
    refuses a bulk send with no unsubscribe URL, and that refusal is a fact about the port
    rather than a thing that happens to a digest whose user has no id.

    The cards come from the persisted digest — nothing is composed here. AD-10 says the
    explanation is persisted at composition time and never recomputed at render, and a body
    that recomputed it would be the "recomputed at render" failure wearing a different hat.
    """
    subject = f"Your Pulse for {facts.local_date.isoformat()}"
    context = {
        "local_date": facts.local_date,
        "city": facts.city,
        "cards": facts.cards,
        "unsubscribe_url": facts.unsubscribe_url,
        "cta_url": facts.cta_url,
    }
    text_body, html_body = _render_both("digest", context)
    return EmailMessage(
        to=to,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        unsubscribe_url=facts.unsubscribe_url,
    )


def render_state_notice(facts: StateNoticeFacts, *, to: str) -> EmailMessage:
    """Render a state-change notice.

    **The subject is FR-54's, verbatim.** Four of them are fixed by the PRD:

    - `EventPulse24: [event name] was cancelled.`
    - `EventPulse24: [event name] was moved to [new date].`
    - `EventPulse24: [event name] moved to [new location].`
    - `EventPulse24: [event name] is sold out.`

    **The subject is built by `domain.notices.notice_subject`, not here.** The vocabulary
    — which kind says what, and which of those lines are the PRD's and which are ours —
    is a contract, and a contract belongs in one place that every caller reads. Two
    copies of "EventPulse24: " would drift, and the second copy would be the one a test
    asserted against.

    **A kind with no subject raises.** `domain.notices.subject_template` raises
    `KeyError` for a kind it has not been taught, and that error is *not* caught here.
    A notice reading "your saved event was cancelled" about an event that was not
    cancelled is worse than a notice that did not go out, because the user reads it.

    **No unsubscribe URL.** A transactional message carries none (AD-20), and a state
    notice is not a thing a user subscribes to. **The mute is the opt-out, and it lives
    on the Detail Screen** — which is why the body links there.
    """
    title = facts.title or MISSING_TITLE
    subject = notice_subject(
        facts.change_kind,
        title=title,
        when=facts.new_time_text,
        where=facts.venue_name,
    )
    text_body, html_body = _render_both(
        "state_notice",
        {
            "title": facts.title,
            "display_title": title,
            "change_kind": facts.change_kind,
            "new_time_text": facts.new_time_text,
            "previous_time_text": facts.previous_time_text,
            "venue_name": facts.venue_name,
            "detail_url": facts.detail_url,
            "reminder_consequence": facts.reminder_consequence,
        },
    )
    return EmailMessage(
        to=to,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        unsubscribe_url=None,
    )


__all__ = [
    "DigestCardFacts",
    "DigestFacts",
    "ReminderFacts",
    "StateNoticeFacts",
    "render_digest",
    "render_reminder",
    "render_state_notice",
]
