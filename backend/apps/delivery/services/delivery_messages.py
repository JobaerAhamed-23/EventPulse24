"""The renderer seam: a `ScheduledSend` row becomes an `EmailMessage` (D8).

**This module is the boundary between the sweep's mechanism and the message's content.**
The sweep (`apps.delivery.services.delivery_sweep`) owns the claim, the key, the stream and
the mark. This module owns the words.

**Item 6 replaced the strings, and the seam held.** The renderers now build real bodies
through `email_templates` and carry real signed unsubscribe links through
`unsubscribe_tokens` — and the sweep's contract is unchanged. The renderer is still handed
exactly two arguments:

```python
renderer(row: ScheduledSend, address: str) -> EmailMessage
```

What they *are not* is still the point:

- **It is not given the stream.** The stream comes from the row (AD-20). A renderer that
  could choose one would be a second place for that decision to drift, and the drift would
  show up as a digest going out on the transactional stream — the exact failure AD-20 exists
  to prevent.
- **It is not given the send key.** The key comes from the row too (AD-7), and it is the
  provider's idempotency key. A renderer cannot mint one, so it cannot cause a duplicate.
- **It is not given a clock.** It renders what the row says, at the moment it is called.

---

## Two layers, and the split between them

| module | responsibility |
|---|---|
| `delivery_messages` (here) | **gathering** — which event, which cards, which facts |
| `email_templates` | **rendering** — facts in, a body out |

The split is what keeps the templates testable. `email_templates` takes frozen dataclasses
and reads nothing: no clock, no database, no request. So the bodies can be asserted
without a network or a fixture user, and the *gathering* stays where it has always been —
reading through published interfaces, never another app's models.

---

## The two renderers

`render_transactional` and `render_digest` are separate functions rather than one function
with a branch, because **the two streams have different obligations** and merging them
would make the bulk one's obligations optional:

| | transactional | bulk (digest) |
|---|---|---|
| stream | `Stream.TRANSACTIONAL` | `Stream.BULK` |
| unsubscribe URL | not required | **required** (RFC 8058) |
| subject | one event | one day |

`EmailPort.send` refuses a bulk message with no `unsubscribe_url` — a `ValueError` at the
port, which is the correct refusal: RFC 8058 is not optional on the bulk stream. So
`render_digest` must produce one, and it gets it from `unsubscribe_url_for`, which now mints
a **signed** token.

**The transactional renderer carries a per-event unsubscribe link in its body, and no
stream-level one.** FR-11: a reminder's link stops *that event's* reminders and does not
touch the Pulse Ping. The link is scoped to the event, signed, and lives in the body where
the user expects to find it — while `EmailMessage.unsubscribe_url` stays `None`, because the
transactional stream has no stream-level opt-out.

---

## Facts come from published interfaces, never from another app's models (AD-3, AD-16)

A reminder's body quotes the event's **name** and **time**. Those live in the `catalog`
schema (a public event) or in the user's own agenda (a personal event), and `delivery` may
read neither table directly:

- **A public event** is read through `apps.ingestion.services.catalog_read.get_public_event`
  — a lookup against the `catalog` alias that hands over plain data. It runs **outside** any
  `personal` transaction: AD-3 forbids one transaction spanning both schemas, and a sweep
  that held a `personal` row lock while reading `catalog` would serialise the batch behind
  the slowest catalog query.
- **A personal event** is read through `apps.personalization.services.personal_events
  .get_personal_event` — the published service, because `delivery` may not import
  `apps.personalization.models`.
- **The digest's cards** are read through `apps.personalization.services.digest_read
  .read_digest`, the same read the API serves.

**A missing fact is not an error.** The catalog may have dropped the event since it was
saved, the personal event may have been deleted, the digest may not have been composed.
The renderer then says so in the body rather than inventing a title — the same reasoning as
`digest_read`'s `catalog_event_missing`.

---

## No PII leaves this module (AD-13)

The renderer receives the recipient's address and puts it in `EmailMessage.to`. That is the
address's one legitimate destination. It is never logged, never put in an audit `details`
dict and never used to build a subject. The audit rows the sweep writes carry ids and
counts only.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.conf import settings

from apps.delivery.models import ScheduledSend
from apps.delivery.services.delivery_sweep import VanishedTargetError
from apps.delivery.services.email_templates import (
    DigestCardFacts,
    DigestFacts,
    ReminderFacts,
)
from apps.delivery.services.email_templates import (
    render_digest as _render_digest_body,
)
from apps.delivery.services.email_templates import (
    render_reminder as _render_reminder_body,
)
from apps.delivery.services.unsubscribe_tokens import (
    UNSUBSCRIBE_SCOPE_EVENT_REMINDERS,
    UNSUBSCRIBE_SCOPE_PING,
    mint_click_token,
    mint_unsubscribe_token,
)
from ports.email import EmailMessage, Stream
from shared.constants import CLICK_REDIRECT_PATH, UNSUBSCRIBE_PATH

#: The base URL the unsubscribe link is built from. A module constant rather than a
#: setting: the token builder, the renderer and the command all need to agree on it, and
#: a value that had to be threaded through every call would be one more thing to thread
#: through.
DEFAULT_UNSUBSCRIBE_BASE_URL = "https://eventpulse24.example/unsub"


class MissingTargetError(VanishedTargetError):
    """The row's target cannot be found, so there is no message to write.

    **Not a domain error and never mapped to HTTP.** This happens in the worker, against a
    row the user never asked about. The sweep catches it and **cancels** the row — sending a
    reminder about an event the user removed would be worse than not sending it, and
    cancelling keeps the record of what was supposed to happen (AD-7's `CANCELLED`).

    **It is a subclass of the sweep's `VanishedTargetError`, not a second error.** The
    sweep catches one exception type, and a renderer that raised something the sweep did
    not know about would be an *unhandled* failure — the row would be released and retried
    forever against a target that is never coming back. Subclassing makes the catch
    structural: any renderer that says "the target is gone" is caught, whoever raises it.
    """


def unsubscribe_url_for(*, user_id: UUID, scope: str, target_id: UUID | None = None) -> str:
    """The RFC 8058 one-click unsubscribe target for one user (AD-20).

    **The link is signed, and the scope is inside the signature.** The token names the
    user, the scope and — for the event scope — the target, and all three are covered by
    the signature. So a user who edits the URL cannot widen their own unsubscribe to
    "everything" or retarget it at somebody else's event: the signature stops verifying
    and the endpoint refuses.

    **The scope is not in the path.** It used to look natural to put it there
    (`/unsub/digest/<user_id>`), and that is exactly the version where the scope is
    editable by whoever holds the URL. Inside the payload, it cannot be.

    **The token does not expire.** A plain `Signer` is used rather than a timestamped one,
    because an unsubscribe link that quietly stops working is worse than one that keeps
    working: the user turns it off once and the mail keeps coming.
    """
    token = mint_unsubscribe_token(user_id=user_id, scope=scope, target_id=target_id)
    return f"{DEFAULT_UNSUBSCRIBE_BASE_URL}{UNSUBSCRIBE_PATH}?token={token}"


def click_url_for(*, user_id: UUID, destination: str) -> str:
    """A server-side tracked link to `destination` (SM-2).

    **A redirect, not a pixel.** SM-2 rejects open-pixel measurement: a hidden image
    request is unreliable, is blocked by most clients, and does not survive a text-only
    mail at all. So the link is a real link the user clicks, and the click passes through
    our server on the way to the destination.

    The destination is inside the signed token, so it cannot be edited into an open
    redirect.
    """
    token = mint_click_token(user_id=user_id, destination=destination)
    return f"{DEFAULT_UNSUBSCRIBE_BASE_URL}{CLICK_REDIRECT_PATH}?token={token}"


def _local_time_text(*, start_utc: datetime | None, zone: str | None) -> str | None:
    """The event's start as local wall-clock text, or `None` when it cannot be rendered.

    AD-6: display-time conversion happens at the presentation edge. This **is** the
    presentation edge — the body of the email. The conversion is done here and nowhere else.

    A zone that the platform does not know is not an error: the facts are still rendered
    without the time rather than not rendered at all.
    """
    if start_utc is None:
        return None
    if not zone:
        return None
    try:
        from zoneinfo import ZoneInfo

        return start_utc.astimezone(ZoneInfo(zone)).strftime("%A %-d %B, %H:%M")
    except Exception:
        return None


def _public_event_facts(*, target_id: UUID) -> ReminderFacts:
    """A saved public event's display facts, through the catalog's published read (AD-3).

    **`now` is not passed**, so the "has not started yet" bound is not applied: a reminder
    about an event that has already begun must still be able to name it. The catalog's own
    docstring says exactly this — "a record of something the user already saved has to stay
    readable after the event has started".

    **A missing event is not an error here.** The catalog may have unpublished or
    superseded the event since the user saved it. The reminder still goes out — the user
    asked to be reminded about something, and the honest body says the event is no longer
    listed rather than pretending otherwise. The catalog's read *raises* on a missing id,
    so the exception is caught here and turned into empty facts.

    **A personal event that is gone *is* an error**, and the two cases differ on purpose:
    a public event's disappearance is the catalog's business, while a personal event is
    the user's own row and its absence means the thing they asked about no longer exists.
    """
    from apps.ingestion.services.catalog_read import EventNotFoundError, get_public_event

    try:
        public = get_public_event(event_id=target_id)
    except EventNotFoundError:
        return ReminderFacts(title=None, local_time_text=None, location=None, slot=None)
    return ReminderFacts(
        title=public.title,
        local_time_text=_local_time_text(
            start_utc=public.start_time_utc,
            zone=public.start_time_tz,
        ),
        location=public.venue_name,
        slot=None,
    )


def _personal_event_facts(*, user_id: UUID, target_id: UUID) -> ReminderFacts:
    """A personal event's display facts, through `personalization`'s published service.

    A deleted personal event is **not** an error here: the row's target is gone, so the
    message cannot be written, and the sweep cancels the row instead.
    """
    from apps.personalization.services.personal_events import (
        PersonalEventNotFoundError,
        get_personal_event,
    )

    try:
        event = get_personal_event(user_id=user_id, event_id=target_id)
    except PersonalEventNotFoundError:
        raise MissingTargetError(f"personal event {target_id} is gone") from None
    return ReminderFacts(
        title=event.name,
        local_time_text=_local_time_text(start_utc=event.start_utc, zone=event.start_time_tz),
        location=event.location,
        slot=None,
    )


def _facts_for(row: ScheduledSend) -> ReminderFacts:
    """The facts for a row, whichever kind of target it names.

    **The dispatch is on `row.kind`, not `row.target_kind`** — and the two are different
    vocabularies, which is worth being explicit about:

    | column | vocabulary | values |
    |---|---|---|
    | `ScheduledSend.kind` | `ScheduledSend.Kind` | `event_reminder`, |
    | | | `personal_reminder`, `state_notice`, `digest` |
    | `ScheduledSend.target_kind` | `ReminderPlan.TargetKind` | `personal_event`, |
    | | | `saved_event` |

    `target_kind` says **which personal-side record the plan belongs to** — it is copied
    verbatim from the plan at minting time (`mint_for_plan` writes
    `target_kind=target.target_kind`, and that value is a `ReminderPlan.TargetKind`). It
    never says "personal reminder"; comparing it against `ScheduledSend.Kind` would compare
    two different enumerations and could never be true.

    `kind` is the one that says what the send is. The minting service decides it in
    `_kind_for`: a target with a `catalog_event_id` is an `event_reminder`, and one without
    is a `personal_reminder`. So the dispatch reads `kind`.

    The target kind is read from the row, never inferred: the row says whether it is about
    a personal event or a saved public event, and guessing from the ids would be a second
    place for that decision to drift.
    """
    if row.target_id is None:
        raise MissingTargetError(f"send {row.id} names no target")
    if row.kind == ScheduledSend.Kind.PERSONAL_REMINDER.value:
        return _personal_event_facts(user_id=row.user_id, target_id=row.target_id)
    return _public_event_facts(target_id=row.target_id)


def render_transactional(row: ScheduledSend, address: str) -> EmailMessage:
    """Render a reminder or a notice as a transactional message.

    **The transactional stream carries no unsubscribe URL.** It is not optional here, it
    is *absent*: RFC 8058 is a requirement of the bulk stream (AD-20), and adding one to a
    transactional message would tell the user they can stop mail they never subscribed to
    as a list.

    **The event's own link is in the body.** FR-11: a reminder's link stops *that event's*
    reminders and does not touch the Pulse Ping. It is scoped to the event and signed, so
    it cannot be edited into a wider unsubscribe.

    **A vanished target raises `MissingTargetError`** and the sweep cancels the row.
    """
    facts = _facts_for(row)
    unsubscribe_url = None
    if row.target_id is not None:
        unsubscribe_url = unsubscribe_url_for(
            user_id=row.user_id,
            scope=UNSUBSCRIBE_SCOPE_EVENT_REMINDERS,
            target_id=row.target_id,
        )
    return _render_reminder_body(
        ReminderFacts(
            title=facts.title,
            local_time_text=facts.local_time_text,
            location=facts.location,
            slot=row.slot,
            unsubscribe_url=unsubscribe_url,
        ),
        to=address,
    )


def render_digest(row: ScheduledSend, address: str) -> EmailMessage:
    """Render the day's Pulse Digest as a bulk message (AD-20, FR-10).

    **The unsubscribe URL is mandatory.** `EmailPort.send` refuses a bulk message without
    one, and this renderer always supplies one — so the refusal is a fact about the port,
    not a thing that happens to a digest row whose user has no id.

    **The cards come from the persisted digest**, read through `personalization`'s published
    `read_digest`. Nothing is composed here: AD-10 says the explanation is persisted at
    composition time and never recomputed at render, and a body that recomputed it would be
    the "recomputed at render" failure wearing a different hat.

    A day with no digest yet renders as an empty digest rather than an error. The row is
    about a day, and a day without a digest is a day with nothing on it.
    """
    from apps.personalization.services.digest_read import DigestStatus, read_digest

    digest = read_digest(user_id=row.user_id, now=row.due_at)

    # The bulk stream's unsubscribe link is mandatory, so it is built first and for
    # certain. A digest that fails to build its link must fail loudly here rather than
    # at the port, where the refusal would be about a row nobody can see.
    unsubscribe_url = unsubscribe_url_for(
        user_id=row.user_id,
        scope=UNSUBSCRIBE_SCOPE_PING,
    )
    cta_url = click_url_for(
        user_id=row.user_id,
        destination=f"{settings.FRONTEND_BASE_URL.rstrip('/')}/pulse",
    )

    if digest.status == DigestStatus.NOT_COMPOSED:
        # No cards, but still a bulk message with its link: the user may want to stop the
        # Ping before the first digest arrives.
        cards: tuple[DigestCardFacts, ...] = ()
    elif digest.status == DigestStatus.EMPTY:
        cards = ()
    else:
        cards = tuple(
            DigestCardFacts(
                title=card.title,
                local_time_text=_local_time_text(
                    start_utc=card.start_time_utc,
                    zone=card.start_time_tz,
                ),
                location=card.location or card.venue_name,
                bucket=card.bucket,
                tags=card.tags,
                url=card.canonical_url,
            )
            for card in digest.cards
        )

    return _render_digest_body(
        DigestFacts(
            local_date=digest.local_date,
            city=digest.city,
            cards=cards,
            unsubscribe_url=unsubscribe_url,
            cta_url=cta_url,
        ),
        to=address,
    )


def renderer_for(row: ScheduledSend, address: str) -> EmailMessage:
    """Render a row, choosing the renderer from the row's stream.

    **This is the callable the sweep is given.** Its shape is exactly the renderer's
    contract — `(row, address) -> EmailMessage` — so the worker passes `renderer_for`
    straight to `sweep_due_sends` and there is no wrapper to get wrong.

    **The choice is made from the row's stream, not from its kind.** The stream is what the
    provider will send it on and AD-20 makes it the thing that must not drift; the kind is
    a description of the content. So a digest row on the bulk stream gets the bulk
    renderer, and a row on any other stream gets the transactional one — and a row whose
    stream says bulk but whose kind says something else still gets the bulk renderer,
    because the stream is what the obligation follows.

    **An unknown stream raises.** The sweep's `_stream_for` refuses it first and names the
    row, so this branch is unreachable in the normal path; it raises rather than guessing,
    because guessing here would mean sending on a stream nobody chose.
    """
    try:
        stream = Stream(row.stream)
    except ValueError as exc:
        raise ValueError(f"send {row.id} carries an unknown stream") from exc
    if stream is Stream.BULK:
        return render_digest(row, address)
    return render_transactional(row, address)


__all__ = [
    "DEFAULT_UNSUBSCRIBE_BASE_URL",
    "MissingTargetError",
    "click_url_for",
    "render_digest",
    "render_transactional",
    "renderer_for",
    "unsubscribe_url_for",
]
