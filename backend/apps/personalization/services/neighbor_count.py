"""The Detail Screen's neighbor count, under k-anonymity (FR-24, AD-13).

**This module exists to hold one thing: the count must never become a number that reaches
the response-building code.**

FR-24 is explicit — "Exact counts are never exposed" — and the work item names the trap
by name: "computing the bucket and then suppressing it in the serializer means the exact
count existed in the response-building code and could be logged, cached or leaked by a
later change."

So the shape of this module is the shape of the answer. The function below returns a
**bucket key or `None`**, and the count never leaves it. There is no `neighbor_count`
field on the dataclass, there is none on the schema, and there is nothing for a later
change to leak — because there is nothing to leak.

**The threshold is ≥5, and the PRD's glossary says 1.** FR-24's body says "≥5 qualifying
users"; the PRD's Glossary says "Revealed only when at least 1 qualifying user exists".
The stricter rule governs, and the reason is not deference to the body text: k-anonymity
at k=1 is not anonymity. A count of exactly one is the identity of one person, and the
whole point of the signal is that it says "other people near you are interested in this"
rather than "one specific person is".

**The buckets are slugs, not prose.** The server states facts; the client speaks the
user's language. "A few" can be re-worded without a backend deploy.

**"Same area" is city equality (D6), and the event's city is the only city.** FR-24
defines "same area" as "haversine distance ≤ 2 km OR same city-zip-cluster", and neither
is computable: `Venue` has no coordinates and there is no zip data anywhere in the
schema. The clause filters on the **event side** — a user qualifies for *this* event by
saving *this* event or opening *this* event, and the event's own city is the area. So
there is no per-user city to compare against.

The event's city is still read, for one reason: **an event with no venue has no area, and
therefore no neighbors.** "People near you" is meaningless for an event that is nowhere.

**The count is tier-agnostic (FR-24's privacy floor).** Pro and Free users count
identically, so no density difference can leak. There is no subscription entity in this
codebase yet, so this holds trivially — and the queries below have no tier filter,
which is a statement about the shape of the query rather than about a filter that does
not exist.

**The count is two queries, not one aggregate.** The two signals live in two tables with
two shapes, and the honest way to combine them is a union of user ids — not a join that
would multiply a user who both saved and opened. A user qualifies **once**, whichever
signals they have.

Design: .specs-fire/intents/pulse-digest-and-trust/work-items/
event-detail-api-design.md (decisions D4, D6, D9).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from apps.personalization.models import EventDetailOpen, SavedEvent
from shared.db import PERSONAL

#: FR-24: "the count aggregates Pro and Free tier users identically" and "Buckets `<5`
#: are suppressed (k-anonymity)".
#:
#: **The threshold is a constant, not a literal in the query.** AD-8: a threshold lives in
#: one shared module. It is here — in the module that owns the rule — rather than in
#: `shared/constants.py`, because it is this feature's threshold and not a product-wide
#: number; the shared module holds the ones two features agree on.
NEIGHBOR_COUNT_MIN = 5

#: FR-24's qualifying window: a save or an open "in the last 30 days".
#:
#: The window is **inclusive** at the bound: an open exactly 30 days ago still counts.
#: "In the last 30 days" is a closed interval, and a user who opened the event on the
#: first day of the window has not stopped qualifying on the last one.
NEIGHBOR_QUALIFYING_WINDOW = timedelta(days=30)

#: The bucket keys, from the smallest to the largest.
#:
#: These are the **only** values the count can take. There is deliberately no key for
#: "below the threshold": the suppression is silence, not a fourth bucket (D4).
NEIGHBOR_BUCKET_FEW = "few"
NEIGHBOR_BUCKET_SOME = "some"
NEIGHBOR_BUCKET_MANY = "many"
NEIGHBOR_BUCKET_A_LOT = "a_lot"

#: The bucket boundaries, as the **inclusive upper bound** of each bucket.
#:
#: A count of 9 is "few"; a count of 10 is "some". The bound is inclusive, so the
#: boundary is a fact about the number and not about which side of the line the
#: implementation put it.
NEIGHBOR_BUCKET_FEW_MAX = 9
NEIGHBOR_BUCKET_SOME_MAX = 24
NEIGHBOR_BUCKET_MANY_MAX = 99


class NeighborBucket:
    """The four bucket keys, and only those four.

    A closed set. There is no "suppressed" key: the suppression is the **absence** of a
    bucket, and a key for it would tell the client that the count was computed and
    discarded — which is itself a signal about how many people are near this event.
    """

    FEW = NEIGHBOR_BUCKET_FEW
    SOME = NEIGHBOR_BUCKET_SOME
    MANY = NEIGHBOR_BUCKET_MANY
    A_LOT = NEIGHBOR_BUCKET_A_LOT


@dataclass(frozen=True)
class NeighborCount:
    """The neighbor count, already bucketed.

    **`count` is deliberately not a field.** This dataclass holds a bucket key and
    nothing else, so the exact number cannot be read off it, logged from it, or
    serialized from it by a later change. The count existed, briefly, inside the
    function that built this — and it died there.
    """

    #: The bucket key, or `None` when the count is below the k-anonymity threshold.
    bucket: str | None


def bucket_for(count: int) -> str | None:
    """The bucket key for a count, or `None` when the count is below the threshold.

    **This is the only place the count becomes a bucket.** It is a pure function of an
    integer, and the integer does not survive it.

    The thresholds are inclusive upper bounds, so 9 is "few" and 10 is "some" — a
    boundary test is a statement about the number rather than about the code.
    """
    if count < NEIGHBOR_COUNT_MIN:
        return None
    if count <= NEIGHBOR_BUCKET_FEW_MAX:
        return NeighborBucket.FEW
    if count <= NEIGHBOR_BUCKET_SOME_MAX:
        return NeighborBucket.SOME
    if count <= NEIGHBOR_BUCKET_MANY_MAX:
        return NeighborBucket.MANY
    return NeighborBucket.A_LOT


def _qualifying_user_ids(
    *,
    event_id: UUID,
    since: datetime,
) -> set[UUID]:
    """The users whose signal for this event qualifies, within the window.

    **The window is applied to each signal's own timestamp.** A save qualifies on
    `saved_at` and an open qualifies on `opened_at`, each within 30 days of `now`. A
    user qualifies if **either** holds — FR-24 says "saved **or** opened".

    **The two signals are gathered into a set**, so a user who both saved and opened
    counts **once**. A join would multiply that user; a union of ids cannot.
    """
    qualifying: set[UUID] = set()

    qualifying.update(
        SavedEvent.objects.using(PERSONAL)
        .filter(event_id=event_id)
        .filter(saved_at__gte=since)
        .values_list("user_id", flat=True)
    )

    qualifying.update(
        EventDetailOpen.objects.using(PERSONAL)
        .filter(event_id=event_id)
        .filter(opened_at__gte=since)
        .values_list("user_id", flat=True)
    )

    return qualifying


def count_neighbors(
    *,
    event_id: UUID,
    now: datetime,
) -> NeighborCount:
    """The neighbor count for an event, already bucketed.

    **The count is never returned.** This function returns a `NeighborCount`, which holds
    a bucket key or `None` — and the exact number does not survive this call.

    **A user who both saved and opened counts once.** The two signals are gathered into
    a set of user ids, and the set's size is the count.

    **"Now" bounds the window.** The 30-day window is measured back from `now`, and
    `now` is a parameter, so the boundary is testable at the exact instant.
    """
    since = now - NEIGHBOR_QUALIFYING_WINDOW
    qualifying = _qualifying_user_ids(event_id=event_id, since=since)
    return NeighborCount(bucket=bucket_for(len(qualifying)))


__all__ = [
    "NEIGHBOR_BUCKET_A_LOT",
    "NEIGHBOR_BUCKET_FEW",
    "NEIGHBOR_BUCKET_FEW_MAX",
    "NEIGHBOR_BUCKET_MANY",
    "NEIGHBOR_BUCKET_MANY_MAX",
    "NEIGHBOR_BUCKET_SOME",
    "NEIGHBOR_BUCKET_SOME_MAX",
    "NEIGHBOR_COUNT_MIN",
    "NEIGHBOR_QUALIFYING_WINDOW",
    "NeighborBucket",
    "NeighborCount",
    "bucket_for",
    "count_neighbors",
]
