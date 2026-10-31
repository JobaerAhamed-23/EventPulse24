"""The detail-open command: record that a user opened an event's Detail Screen (FR-24).

**This is a command, not a read.** It writes a row and an audit entry, in one
transaction (AD-5), and it is the only writer of `EventDetailOpen` (AD-16).

**It is a `POST`, and that is a privacy decision, not an API style choice.** The
neighbor count depends on this signal, so a signal anyone can forge inflates a number
that is supposed to mean "other people are interested in this". A `GET` that writes is
exactly the shape CSRF exists to stop — a third-party page can make a browser issue a
`GET` — and Django's own rule is that only **unsafe** methods need the CSRF token, so
`require_csrf` would return early on a `GET` and check nothing. A signal recorded from
an unprotected `GET` is forgeable.

So the detail screen's read (`GET /api/events/{id}`) writes **nothing at all**, and this
command is a separate request the frontend fires when the screen is actually shown.

**It is idempotent.** Opening the same event twice updates `opened_at` and does not
create a second row. The count counts distinct users, so a repeated open cannot inflate
it — and a user who opens a page five times has still opened it once.

**It stores no more than it needs.** One row per `(user, event)`, holding the most
recent open. No IP address, no user agent, no referrer, no duration, no view count. The
row answers exactly one question — "has this user opened this event in the last 30
days?" — and nothing that would be PII reaches a table (AD-13).

**The audit row carries the event id and nothing else.** AD-13 forbids PII and
untrusted content in logs, and the audit table is a log. The event id is an id, not
content: no title, no URL, no city.

Design: .specs-fire/intents/pulse-digest-and-trust/work-items/
event-detail-api-design.md (decisions D1, D5, D11).
"""

from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.personalization.models import EventDetailOpen
from apps.personalization.services.audit import write_audit
from shared.actor import Actor
from shared.db import PERSONAL


def record_detail_open(
    *,
    user_id: UUID,
    event_id: UUID,
    actor: Actor,
    now: datetime,
) -> EventDetailOpen:
    """Record that the user opened this event's Detail Screen.

    **The row is upserted, not inserted.** One row per `(user, event)`, holding the most
    recent open. The alternative — an append-only log of every open — would answer the
    same question with a query that counts rows, and would store the user's entire
    viewing history of the catalog. The count asks one question and the answer is a
    boolean per pair.

    **The write and the audit entry are in one transaction.** `write_audit` raises
    outside a `transaction.atomic(using=PERSONAL)` block, which is the guard that keeps
    an audit row from being committed apart from its mutation.
    """
    with transaction.atomic(using=PERSONAL):
        opened, created = EventDetailOpen.objects.using(PERSONAL).update_or_create(
            user_id=user_id,
            event_id=event_id,
            defaults={"opened_at": now},
        )
        write_audit(
            actor=actor,
            action="event_detail.opened",
            target_type="event_detail_open",
            target_id=opened.id,
            details={"event_id": str(event_id), "created": created},
        )
    return opened


__all__ = ["record_detail_open"]
