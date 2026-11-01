"""The Pulse Ping: decide whether to send one, and say why when we do not (FR-10, SM-C1).

**This is the product's most distinctive behaviour, and it is the only one that improves
by doing less.** SM-C1 targets a **≥30% suppression rate** and counts a higher number as
*better intelligence, not worse* — the one metric in the PRD that gets better when the
product does less. A ping that fires every day regardless is a ping nobody reads, and the
user who unsubscribes is the failure the counter-metric exists to prevent.

**So the rule is a decision, and the decision is recorded.** A ping is minted only when
there is something worth saying, and every "we said nothing" is counted with its reason.
A product that silently does less is indistinguishable from a product that is broken.

**The decision is made here, and the row is made elsewhere.** This module asks the
question and writes nothing to `SCHEDULED_SEND`; `scheduled_sends.mint_digest` owns the
create, because that module is the single writer of the table (AD-16). The shape is the
same as everywhere else in this codebase: the decision is one place, the write is one
place, and neither reaches across to the other.

---

## The order of the checks, and why it is this order

```
1. has the user turned the Ping off?   → nothing minted; counted as `unsubscribed`; STOP
2. is there anything worth saying?     → nothing minted; counted as a suppression; STOP
3. otherwise                            → mint exactly one digest row
```

**The unsubscribe check comes first** because a user who has opted out is not a fact
about the product's intelligence — it is a fact about the user's choice — and because
there is no point counting a suppression for a user who is not listening. FR-11's opt-out
is a promise, and the cheapest way to keep it is to never mint.

**The suppression check comes second** because it is FR-10's rule: a user with no
qualifying public events **and** no personal events in the next 48 hours does not get a
Ping. **Not a minted row that is later skipped** — a `pending` row that is never sent is
indistinguishable from a bug, and AD-7's whole premise is that a `pending` row is a
promise. The silence has to be *the absence of the row*.

---

## The two reasons, and why they are counted separately

| reason | meaning | is it a suppression? |
|---|---|---|
| `unsubscribed` | the user turned the Ping off | **no** |
| `no_qualifying_events` | nothing worth saying in the next 48 hours | **yes** |

**They are different facts about the product.** SM-C1 measures *the product's* silence —
the product chose not to speak because it had nothing worth saying. An opt-out is the
*user* choosing silence. Counting an opt-out as a suppression would inflate SM-C1 with
demand-side decisions and make the counter-metric a lie: a product that mails nobody
because nobody wants its mail would score a perfect 100%, and the target says nothing
about whether the product is any good.

**The reasons are a closed set.** Two reasons, two literals, in this module. A reason
that is spelled differently in two places is two reasons, and the count splits.

---

## Where the counts go, and why both

| | answers |
|---|---|
| **structured log line** | "how many pings did we suppress today?" — SM-C1 |
| **audit row** | "why did *this* user get no ping on this day?" |

The log line is `logger.info("Pulse Ping suppressed", extra={...})` and the audit row is
`write_audit(action="pulse_ping.suppressed", ...)`.

Both carry the reason, and **neither carries anything but a user id and a date** (AD-13).
The audit row's `target_type` is `user` and its `target_id` is the user's id; the reason
is a vocabulary word, not a description of the user's day.

**The log line is where SM-C1 is read from.** It is structured, so the rate is a query
rather than a scrape.

---

## What "qualifying" means, and why it is not re-derived here

**FR-10's rule is about the candidate *pool*, not the three composed cards.** A user with
forty eligible events still gets three cards, and "3 qualifying events → exactly 1
Ping" is a statement about sends, not cards. So the composition reports the pool counts
it already computed — `public_qualifying_count` and `personal_qualifying_count`, counted
within the 48-hour horizon in the user's own zone — and this module reads them.

**The rule is not written a second time.** `DigestCompositionResult.has_qualifying_events`
is the `AND` from FR-10, in one place, next to the counts it is about. This module asks
that property rather than re-deriving it from the counts, so the two cannot disagree.

**A personal event only counts if the user has not opted out of them.** FR-19's opt-out
means those events are not in the user's digest, so they cannot be the reason the user
keeps receiving a Ping either. The composition reports the personal count as zero when
the user opted out, and this module does not second-guess it.

---

## The user's own zone, twice over

The **48-hour horizon** is drawn in the user's zone, not UTC — `domain.horizon`
owns that arithmetic, and the composition applied it before counting.

The **delivery time** is a wall clock in the user's zone, and `mint_digest` reads it
there and shifts it by Quiet Hours. Both are the same idea: the user said "tomorrow
morning" and "the next 48 hours" in *their* frame of reference, not the server's.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from uuid import UUID

from django.db import transaction

from apps.delivery.services.audit import write_audit
from apps.delivery.services.scheduled_sends import mint_digest
from apps.delivery.services.unsubscribes import pulse_ping_unsubscribed
from apps.personalization.services.digest_preferences import get_delivery_settings
from shared.actor import Actor
from shared.constants import DEFAULT_DIGEST_DELIVERY_TIME, DEFAULT_DIGEST_TIMEZONE
from shared.db import PERSONAL

logger = logging.getLogger(__name__)

#: The reason a user received no Ping because they turned it off.
#:
#: **Not a suppression.** See the module docstring: SM-C1 measures the product's silence,
#: and an opt-out is the user's silence. Counting it here would inflate the counter-metric
#: with a demand-side decision.
REASON_UNSUBSCRIBED = "unsubscribed"

#: The reason a user received no Ping because nothing was worth saying (FR-10).
REASON_NO_QUALIFYING_EVENTS = "no_qualifying_events"

#: The actor recorded on the audit rows this module writes.
#:
#: A **job name**, never a user's name (AD-13).
PING_ACTOR = Actor.system("pulse_ping")


@dataclass(frozen=True)
class PingOutcome:
    """What the Ping decision was, and what it did.

    **`minted` is the fact that matters.** It is `True` when a row was created, `False`
    when the row already existed — the two are different facts about the world, and a
    caller that logs "minted" for a duplicate would report a second send that never
    happened.

    **`reason` is `None` when a row was minted**, and one of the two reason literals
    otherwise. It is never both and never neither.
    """

    user_id: UUID
    local_date: date
    minted: bool
    suppressed: bool
    reason: str | None
    public_qualifying_count: int
    personal_qualifying_count: int


def mint_ping_send(
    *,
    user_id: UUID,
    local_date: date,
    public_qualifying_count: int,
    personal_qualifying_count: int,
    has_qualifying_events: bool,
    actor: Actor = PING_ACTOR,
    now: datetime,
) -> PingOutcome:
    """Decide whether this user's Pulse Ping goes out, and mint it if it does.

    **`has_qualifying_events` is passed in, not re-derived.** The composition already
    counted the pools and owns the `AND`; this module reads the answer rather than
    re-implementing the rule against the same two numbers (the work item's Technical
    Note: *"do not write a second definition of what counts as a qualifying event"*).

    **Nothing is minted when the rule suppresses**, and the suppression is counted with
    its reason.

    **The unsubscribed check comes first**, and its count is *not* a suppression — the
    two are different facts about the product, and SM-C1 must not be inflated with
    opt-outs.

    **The user's delivery time and zone come from `personalization`'s published
    interface**, because the zone lives on `DigestPreference` and `delivery` may not
    import another app's models (AD-3, AD-16). A user with no preference row falls back
    to the shared defaults rather than being guessed at.
    """
    # **The counts and the boolean must agree.** The boolean decides; the counts are
    # recorded. A caller that passed `(public=0, personal=0, has_qualifying=True)`
    # would mint a Ping the composition says should not exist, and the log line would
    # say "suppressed because nothing qualified" while the user got an email — a
    # contradiction in a row that is read to explain what the product did.
    #
    # This is not a second definition of the rule: the rule lives in the composition's
    # property, and this check only insists that the two facts the caller passes are
    # consistent with each other. It fails loudly rather than silently sending.
    _assert_counts_agree(
        public_qualifying_count=public_qualifying_count,
        personal_qualifying_count=personal_qualifying_count,
        has_qualifying_events=has_qualifying_events,
    )

    if pulse_ping_unsubscribed(user_id=user_id):
        _record_suppression(
            user_id=user_id,
            local_date=local_date,
            reason=REASON_UNSUBSCRIBED,
            public_qualifying_count=public_qualifying_count,
            personal_qualifying_count=personal_qualifying_count,
            actor=actor,
            now=now,
        )
        return PingOutcome(
            user_id=user_id,
            local_date=local_date,
            minted=False,
            suppressed=False,
            reason=REASON_UNSUBSCRIBED,
            public_qualifying_count=public_qualifying_count,
            personal_qualifying_count=personal_qualifying_count,
        )

    if not has_qualifying_events:
        _record_suppression(
            user_id=user_id,
            local_date=local_date,
            reason=REASON_NO_QUALIFYING_EVENTS,
            public_qualifying_count=public_qualifying_count,
            personal_qualifying_count=personal_qualifying_count,
            actor=actor,
            now=now,
        )
        return PingOutcome(
            user_id=user_id,
            local_date=local_date,
            minted=False,
            suppressed=True,
            reason=REASON_NO_QUALIFYING_EVENTS,
            public_qualifying_count=public_qualifying_count,
            personal_qualifying_count=personal_qualifying_count,
        )

    settings = get_delivery_settings(user_id=user_id)
    delivery_time, zone = _delivery_time_and_zone(settings)

    created = mint_digest(
        user_id=user_id,
        local_date=local_date,
        delivery_time=delivery_time,
        zone=zone,
        actor=actor,
        now=now,
    )

    return PingOutcome(
        user_id=user_id,
        local_date=local_date,
        minted=created,
        suppressed=False,
        reason=None,
        public_qualifying_count=public_qualifying_count,
        personal_qualifying_count=personal_qualifying_count,
    )


def _assert_counts_agree(
    *,
    public_qualifying_count: int,
    personal_qualifying_count: int,
    has_qualifying_events: bool,
) -> None:
    """Refuse a caller whose counts and boolean disagree.

    **A contradiction here would be a lie in the audit trail.** The suppression row
    records the counts beside the reason, and the mint path records the decision — so a
    `(0, 0, True)` caller would write "the product had nothing to say" into a log line
    and then email the user anyway. The two facts cannot both be true, and the product
    must not guess which one it believes.

    **This is a consistency check, not a second rule.** The definition of "qualifying"
    lives in `DigestCompositionResult.has_qualifying_events`; this only asks whether
    the two values the caller passed describe the same world.
    """
    counted = public_qualifying_count > 0 or personal_qualifying_count > 0
    if counted != has_qualifying_events:
        raise ValueError(
            "the qualifying counts and the qualifying flag disagree: "
            f"public={public_qualifying_count}, personal={personal_qualifying_count}, "
            f"has_qualifying_events={has_qualifying_events}"
        )


def _delivery_time_and_zone(settings) -> tuple[time, str]:
    """The user's delivery time and zone, or the shared defaults.

    **A user with no preference row is a real state** — an account that predates the
    preference, or one that has not finished onboarding. The defaults are the same ones
    the composition and the scheduler use, so the three agree rather than each guessing
    a different hour (AD-8).
    """
    if settings is None:
        return DEFAULT_DIGEST_DELIVERY_TIME, DEFAULT_DIGEST_TIMEZONE
    return settings.delivery_time, settings.timezone


def _record_suppression(
    *,
    user_id: UUID,
    local_date: date,
    reason: str,
    public_qualifying_count: int,
    personal_qualifying_count: int,
    actor: Actor,
    now: datetime,
) -> None:
    """Count a "no Ping today", with the reason, in a log line and an audit row.

    **The log line is where SM-C1 is read from.** It is structured, so the suppression
    rate is a query rather than a scrape of prose.

    **The counts are on the line too.** "How many pings did we suppress?" is answered by
    the total; "were we suppressing because the user's city had nothing, or because
    everyone had opted out?" is answered by the reason, and the two counts beside it say
    what the pools looked like at the time.
    """
    logger.info(
        "Pulse Ping suppressed",
        extra={
            "job": "pulse_ping",
            "user_id": str(user_id),
            "local_date": local_date.isoformat(),
            "reason": reason,
            "public_qualifying_count": public_qualifying_count,
            "personal_qualifying_count": personal_qualifying_count,
        },
    )

    # **The audit row is written inside its own transaction**, because a suppression
    # writes nothing else — there is no mutation for it to be atomic with. `write_audit`
    # refuses to run outside a `personal` transaction (AD-5), and the transaction is
    # opened here rather than by the caller so that the refusal cannot be reached by
    # forgetting it at a call site.
    with transaction.atomic(using=PERSONAL):
        write_audit(
            actor=actor,
            action="pulse_ping.suppressed",
            target_type="user",
            target_id=user_id,
            details={
                "reason": reason,
                "local_date": local_date.isoformat(),
                "public_qualifying_count": public_qualifying_count,
                "personal_qualifying_count": personal_qualifying_count,
                "at": now.isoformat(),
            },
        )


__all__ = [
    "PING_ACTOR",
    "REASON_NO_QUALIFYING_EVENTS",
    "REASON_UNSUBSCRIBED",
    "PingOutcome",
    "mint_ping_send",
]
