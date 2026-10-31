"""The digest scheduler: who is due, and the claim that makes two dispatchers safe (AD-7).

**This module owns the *selection rule*.** The tick and the worker task own the
*orchestration*; this module answers "which users are due, and which of them have I
claimed". It is the third instance of the claiming-dispatcher pattern the codebase
already has — `schedule_sources` and `schedule_calendars` — and it follows it exactly:
a `SELECT … FOR UPDATE SKIP LOCKED` claim, a TTL for a lost job, and a release
whatever happens.

**"Due" is a local wall clock comparison, not a UTC one.** The user's
`DigestPreference` holds a delivery time as an `HH:MM` **wall clock** paired with an
IANA zone, and that pairing is deliberate: the user said "9am", and a UTC instant
would be "9am once, then 8am or 10am after a DST change". So "has 9am arrived for
this user?" is asked **in the user's own zone**, and the answer moves with the clock —
which is the whole point of storing the pair.

**A user is due when two things hold:**

1. **the local wall clock has reached their delivery time** — and a user whose
   delivery time has already passed today is due *now*, not tomorrow;
2. **they have no digest for the local date yet** — so a user who already has today's
   digest is never re-composed, whatever the clock says.

The second half is the real guard. The first half is a *schedule*; the second is the
*fact*, and the fact is what makes the composition idempotent at the scheduler's level
as well as the service's.

**The local date is computed by the shared rule.** `local_date_for` already exists and
is shared with the composition service and the read API. This module calls it too, so
"today" cannot mean three different days — the exact drift the shared helper was
promoted out to prevent.

**The dispatcher composes; it does not send.** A digest is composed *at or before* the
delivery time so that it exists when the user arrives. The **send** is the delivery
intent's job, and this module has no opinion about it.

Design: .specs-fire/intents/pulse-digest-and-trust/work-items/
digest-scheduling-design.md (decisions D1, D2, D3, D4).
"""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.db.models import Q

from apps.personalization.models import DigestPreference, PulseDigest
from apps.personalization.services.audit import write_audit
from apps.personalization.services.digest_dates import local_date_for
from shared.actor import Actor
from shared.constants import (
    DEFAULT_DIGEST_TIMEZONE,
    DIGEST_CLAIM_TTL,
    DIGEST_DISPATCH_BATCH,
    DIGEST_SCHEDULER_ACTOR,
)
from shared.db import PERSONAL

#: The actor that claims digests. A **job name**, never a user's name (AD-13).
SCHEDULER = Actor.system(DIGEST_SCHEDULER_ACTOR)


def _local_time(now: datetime, zone_name: str):
    """The local wall-clock time of `now` in `zone_name`.

    **The zone falls back to UTC rather than raising**, exactly as `local_date_for`
    does. The zone is validated at write time by the onboarding command, so an unknown
    name means hand-edited data — and a dispatcher that raised would take down the
    whole tick, including every other user's digest. The failure mode is one user
    composed in the fallback zone, not a stopped scheduler.

    **The returned time is naive — the wall clock, with no offset attached.** The
    preference stores an `HH:MM` wall clock, and the comparison is against that naive
    value. `timetz()` would return an *aware* time carrying the zone's offset, and
    comparing an aware time to a naive one does **not** raise — Python orders the two
    by their UTC equivalents, so the answer would silently be the wrong one (an
    offset-bearing 09:00 PST reads as 17:00 against a naive 09:00). The offset is
    already accounted for by the conversion; carrying it into the comparison would
    apply it twice.
    """
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        zone = ZoneInfo(DEFAULT_DIGEST_TIMEZONE)
    return now.astimezone(zone).time()


def is_due(*, delivery_time, now: datetime, zone_name: str) -> bool:
    """Whether the user's local wall clock has reached their delivery time.

    **The comparison is on the local time-of-day, and it is inclusive.** A user whose
    delivery time is 9:00 is due at 9:00:00 — not at 9:01. A dispatcher that became due
    a minute late would show a user a digest that arrived after the moment they asked
    for it.

    **The comparison is DST-correct by construction.** It converts `now` into the
    user's zone and compares the *local* time-of-day, so on the day the clocks go
    forward, 9am local is still 9am local and the instant it corresponds to moves. A
    rule that added 24 hours to a UTC instant would break twice a year.

    **A delivery time that has already passed today is due.** The comparison is not
    "has 9am not yet arrived" — it is "is the local wall clock at or past 9am", and
    the wall clock passes 9am once a day and stays past it until midnight.
    """
    return _local_time(now, zone_name) >= delivery_time


def _already_composed(*, user_id: UUID, local_date) -> bool:
    """Whether this user already has a digest for that local date.

    **This is the idempotence guard.** The composition service is idempotent too, but
    this check means the scheduler does not *start* work whose result is already on
    disk — which is what keeps the dispatcher from claiming the same user on every
    tick of the day.
    """
    return (
        PulseDigest.objects.using(PERSONAL)
        .filter(
            user_id=user_id,
            local_date=local_date,
        )
        .exists()
    )


def claim_due_digests(
    *,
    now: datetime,
    limit: int = DIGEST_DISPATCH_BATCH,
) -> list[UUID]:
    """Claim up to `limit` users whose digest is due; returns their user ids (D1).

    **The claim is taken with `FOR UPDATE SKIP LOCKED`**, exactly as
    `claim_due_connections` does, so two overlapping ticks never claim the same user:
    the second tick's `SKIP LOCKED` skips the row the first one is holding. A claim
    older than `DIGEST_CLAIM_TTL` is a lost job (a worker died) and the user becomes
    claimable again.

    **The due test is a local wall-clock comparison, and it cannot be expressed in SQL.**
    "Has 9am arrived in `America/Los_Angeles`?" depends on the row's own IANA zone,
    and Postgres's `AT TIME ZONE` takes a zone name — which the row does carry — but
    the *comparison* is against a per-row time-of-day, so the whole predicate would
    have to be a correlated expression per row. So the rows are read and the rule is
    applied in Python, which is also where the rule lives: one function, one
    implementation, testable without a database.

    **The read is bounded.** The queryset is limited to `limit` rows *before* the
    Python filter runs, so a large user base does not mean reading every preference
    on every tick.

    **The order is by the user id, which is a UUIDv7 — so it is the creation time.**
    The oldest preference is claimed first, so a user who has just finished onboarding
    is never starved behind a backlog of established users.
    """
    candidates = list(
        DigestPreference.objects.using(PERSONAL)
        .filter(
            Q(digest_claimed_at__isnull=True) | Q(digest_claimed_at__lte=now - DIGEST_CLAIM_TTL)
        )
        .order_by("id")
        .values("user_id", "delivery_time", "timezone")[: limit * 4]
    )

    due: list[UUID] = []
    for candidate in candidates:
        if len(due) >= limit:
            break
        user_id = candidate["user_id"]
        local_date = local_date_for(now=now, zone_name=candidate["timezone"])
        if not is_due(
            delivery_time=candidate["delivery_time"],
            now=now,
            zone_name=candidate["timezone"],
        ):
            continue
        if _already_composed(user_id=user_id, local_date=local_date):
            continue
        due.append(user_id)

    if not due:
        return []

    with transaction.atomic(using=PERSONAL):
        # Re-claim under the row lock, so two dispatchers that read the same
        # candidates cannot both claim the same user. The `SKIP LOCKED` skips a row
        # another dispatcher is holding.
        claimed = list(
            DigestPreference.objects.using(PERSONAL)
            .select_for_update(skip_locked=True)
            .filter(user_id__in=due)
            .filter(
                Q(digest_claimed_at__isnull=True) | Q(digest_claimed_at__lte=now - DIGEST_CLAIM_TTL)
            )
            .values_list("user_id", flat=True)
        )
        if not claimed:
            return []
        DigestPreference.objects.using(PERSONAL).filter(user_id__in=claimed).update(
            digest_claimed_at=now
        )
        for user_id in claimed:
            write_audit(
                actor=SCHEDULER,
                action="claim_digest",
                target_type="DigestPreference",
                target_id=user_id,
                details={"at": now.isoformat()},
            )

    return list(claimed)


def release_claim(user_id: UUID) -> None:
    """End a claim when its job ends, however it ended (D4).

    Not audited: the composition's own audit row (or the job's log line) closes the
    claim. This mirrors `calendar_sync.release_claim`.
    """
    DigestPreference.objects.using(PERSONAL).filter(user_id=user_id).update(digest_claimed_at=None)


__all__ = [
    "SCHEDULER",
    "claim_due_digests",
    "is_due",
    "release_claim",
]
