"""The digest's personal-side candidate reads: the user's events, saves and conflicts.

**These are reads, not commands.** They write nothing, audit nothing and log nothing
(AD-13): reading a candidate list is not a decision, and the audit table records
decisions. They take an explicit `now` and open no transaction — the reads are separate
queries against the `personal` alias, and the composition service owns the order.

**Why they are here and not in `personal_events.py` / `saved_events.py`.** Those two
modules are *command* modules: they create, update and delete, and they carry their own
audit writes, transaction boundaries and error types. A read for composition is a
different kind of thing, and putting it in either module would either mix reads into a
command module or scatter composition's reads across three files.

**The wall (AD-3).** Nothing here joins `catalog`. The public candidates come from
`apps.ingestion.services.catalog_read`, which hands over plain frozen dataclasses, and
the saved events resolve their display facts through the same published interface — one
lookup per saved event, never a cross-alias join. `apps.ingestion` may not import
`apps.personalization` either, so the join happens in the composition service.

**The conflict state comes from the persisted rows.** AD-21: conflict detection happens
"never at render", and `domain/conflict.py` is the one overlap function. Computing an
overlap here would produce a *different* answer from the persisted pair whenever the two
disagreed — and they disagree the moment an event moves without the propagation running.
The Pulse Card indicator, the Timeline block indicator and `/conflicts` all read the same
rows; this read joins them.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.ingestion.services.catalog_read import PublicEvent, get_public_events
from apps.personalization.models import ConflictPair, PersonalEvent, SavedEvent
from shared.constants import RANKING_PERSONAL_EVENT_WINDOW
from shared.db import PERSONAL

#: How many saved events a user's candidate pool may hold.
#:
#: The same shape as the public pool's bound: a digest has three slots, and a user with
#: thousands of saves must not cost a thousands-of-rows read on a job that runs once per
#: day. The bound is on the *saves*, and the catalog's facts are fetched in one batched
#: query regardless of how many there are.
MAX_SAVED_CANDIDATES = 60


@dataclass(frozen=True)
class PersonalEventCandidate:
    """One of the user's own events, as a digest candidate.

    Plain data — the caller never holds a model instance, so the wall holds without
    either side knowing the other's models.
    """

    id: UUID
    user_id: UUID
    name: str
    start_utc: datetime
    end_utc: datetime | None
    start_time_tz: str
    location: str | None
    #: `user_created` or `calendar_import`. Both are the user's own agenda; the source
    #: says how the row got here, not whether it counts.
    source: str
    #: The calendar connection that imported it, or `None` for one the user entered.
    #: The connection's **id**, never its credential (AD-18).
    calendar_connection_id: UUID | None
    #: The persisted conflict pairs this event is a side of. Empty when it has none —
    #: "no conflict" and "we did not look" must not be the same value.
    conflict_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class SavedEventCandidate:
    """One of the user's saved public events, as a digest candidate.

    **The snapshot is the truth for the time.** AD-21: the Timeline and conflict
    detection read the snapshot and never join `catalog`. The snapshot is what the user's
    own calendar shows; the catalog's current time may have moved, and AD-17's
    propagation is what reconciles them. A digest that showed the catalog's current time
    for a saved event would show a time the user's own calendar does not show — the two
    surfaces would disagree about the same event.

    `public` is `None` when the catalog no longer holds the event. The save is still
    real — the user made it — so it is still a candidate; dropping it would make a user's
    save vanish from their digest because a source dropped the event, with no way for
    the user to know why.
    """

    id: UUID
    user_id: UUID
    event_id: UUID
    start_utc: datetime
    end_utc: datetime | None
    event_version: int
    #: The catalog's current public facts, or `None` if the event is gone from the
    #: catalog.
    public: PublicEvent | None
    conflict_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class ConflictPairSnapshot:
    """One of the user's open conflict pairs.

    The sides are held by value — a `(kind, id)` pair — because the pair row is symmetric
    and cannot say which side the user is looking at.
    """

    id: UUID
    user_id: UUID
    kind: str
    left_kind: str
    left_id: UUID
    right_kind: str
    right_id: UUID
    detected_at: datetime


def _personal_candidate(
    event: PersonalEvent,
    conflict_ids: tuple[UUID, ...],
) -> PersonalEventCandidate:
    return PersonalEventCandidate(
        id=event.id,
        user_id=event.user_id,
        name=event.name,
        start_utc=event.start_utc,
        end_utc=event.end_utc,
        start_time_tz=event.start_time_tz,
        location=event.location,
        source=event.source,
        calendar_connection_id=event.calendar_connection_id,
        conflict_ids=conflict_ids,
    )


def _saved_candidate(
    saved: SavedEvent,
    public: PublicEvent | None,
    conflict_ids: tuple[UUID, ...],
) -> SavedEventCandidate:
    return SavedEventCandidate(
        id=saved.id,
        user_id=saved.user_id,
        event_id=saved.event_id,
        start_utc=saved.start_utc,
        end_utc=saved.end_utc,
        event_version=saved.event_version,
        public=public,
        conflict_ids=conflict_ids,
    )


def _open_conflict_pairs(*, user_id: UUID) -> list[ConflictPair]:
    """The user's open conflict pairs, oldest first.

    **Only `ACTIVE`.** A `RESOLVED` pair is answered; a `CLEARED_BY_STATE_CHANGE` pair is
    over because a side went away. Neither is an open conflict, and showing either would
    put a conflict prompt on a card for a conflict the user has already settled.
    """
    return list(
        ConflictPair.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .filter(status=ConflictPair.Status.ACTIVE)
        .order_by("detected_at", "id")
    )


def _conflicts_by_side(
    pairs: list[ConflictPair],
    *,
    kind: str,
    ids: set[UUID],
) -> dict[UUID, tuple[UUID, ...]]:
    """Map each of `ids` to the ids of the conflict pairs it is a side of.

    A pair names two sides, and a candidate is one side — so the pairs are read once for
    the user and attached to the candidates here. One extra query per user per day.
    """
    by_side: dict[UUID, list[UUID]] = {}
    for pair in pairs:
        sides = ((pair.left_kind, pair.left_id), (pair.right_kind, pair.right_id))
        for side_kind, side_id in sides:
            if side_kind != kind or side_id not in ids:
                continue
            by_side.setdefault(side_id, []).append(pair.id)
    return {side_id: tuple(pair_ids) for side_id, pair_ids in by_side.items()}


def list_personal_candidates(
    *,
    user_id: UUID,
    now: datetime,
    window_end: datetime | None = None,
) -> list[PersonalEventCandidate]:
    """The user's own events starting within the next 48 hours, soonest first.

    **The window is `RANKING_PERSONAL_EVENT_WINDOW`** — FR-5's Slot 1 window, already
    named for the ranking. A second 48-hour constant for the same window would be two
    constants that could disagree about a window FR-5 and FR-19 both name (AD-8).

    **Both ends are inclusive.** An event starting exactly 48 hours from now is
    eligible: FR-5's "within the next 48 hours" includes the boundary, and the ranking
    boost it carries (`RANKING_PERSONAL_EVENT_BOOST`) applies at exactly the same
    boundary — so the candidate set and the boost cannot disagree about which events
    are "soon". An event that has already started is *not* a candidate: the window is
    "starting within the next 48 hours", not "running".

    **Imported calendar events are included.** `PersonalEvent.source` is `user_created`
    or `calendar_import`, and both are the user's own agenda — Slot 1 is about the user's
    events, not about who typed the row. `user_modified` does not affect eligibility
    either: it decides who owns the row during a re-sync, which is a sync concern.

    The conflict pairs come from the persisted rows, never from an overlap computed here
    (AD-21).

    ---
    **`window_end` widens the read; it never narrows it.**

    The default upper bound is `now + 48h` — **elapsed** arithmetic, and therefore a UTC
    horizon. FR-10's suppression rule asks a different question ("events in the next 48
    hours", in the **user's own zone**), and the local horizon is a *wall clock* — on a
    spring-forward day it is an hour **earlier** than the elapsed arithmetic, and on a
    fall-back day an hour later.

    So when the caller knows the local horizon, it passes it in, and the read is widened
    to cover it. The pool is then a **superset** of the horizon-filtered set, and the
    caller narrows it by comparing against the horizon itself.

    **Why widen rather than narrow.** The Slot 1 window is a deliberate, separate
    decision — it governs which *cards* a digest holds, and it is not this function's
    business to change it. Narrowing the read to the local horizon would change which
    cards a digest holds for every user on the two DST days a year. Widening it changes
    nothing about the cards, because the caller's own comparison still applies the
    Slot 1 window.

    **The bound is a maximum, not a replacement.** `max` of the two, so a caller can
    only ever ask for *more* rows, never fewer — the function cannot silently drop an
    event the caller wanted to see.
    """
    default_end = now + RANKING_PERSONAL_EVENT_WINDOW
    upper_bound = default_end if window_end is None else max(default_end, window_end)
    events = list(
        PersonalEvent.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .filter(start_utc__gte=now)
        .filter(start_utc__lte=upper_bound)
        .order_by("start_utc", "id")
    )
    pairs = _open_conflict_pairs(user_id=user_id)
    by_side = _conflicts_by_side(
        pairs,
        kind=ConflictPair.SideKind.PERSONAL_EVENT,
        ids={event.id for event in events},
    )
    return [_personal_candidate(event, by_side.get(event.id, ())) for event in events]


def list_saved_candidates(
    *,
    user_id: UUID,
    now: datetime,
    limit: int = MAX_SAVED_CANDIDATES,
) -> list[SavedEventCandidate]:
    """The user's saved public events that have not started yet, soonest first.

    The list is scoped to `user_id` and to nothing else — a save belongs to exactly one
    user, so there is no visibility rule to apply beyond ownership.

    **The bound is "has not started yet", on the snapshot's start time.** A digest's slots
    hold upcoming events, so a save whose event has already begun is not a candidate for
    one. The bound is applied to the **snapshot**, not to the catalog's current time,
    because the snapshot is the user's own calendar (AD-21) and the two may disagree
    until AD-17's propagation reconciles them.

    **The 48-hour window does not apply here.** `RANKING_PERSONAL_EVENT_WINDOW` is FR-5's
    *Slot 1* window — the window in which the user's own agenda is the must-know card. A
    save is not the user's agenda; it is a record of a public event they took an interest
    in, and a save three weeks out is still a save three weeks out. Applying the agenda
    window to saves would drop a user's saves of long-planned events, and the digest's own
    slots have no reason to.

    **A save is not gated by the catalog's confidence thresholds.** Those gate what the
    *catalog* may rank; a save is the user's own record, made when the event was public,
    and the user did not ask for a confidence score. The gates belong to the public
    candidate read.

    **The display facts come from the catalog, in one batched lookup.**
    `get_public_events` is a lookup, not a join: one query against the `catalog` alias,
    returning plain data, with no queryset spanning the two schemas. It is batched rather
    than one call per save because this read runs once per user per day — five saves
    would otherwise cost five round-trips to the catalog, times every user.

    **A save the catalog no longer holds is still a candidate.** The save is real; the
    user made it. Dropping it would make a user's save vanish from their digest because a
    source dropped the event, with no way for the user to know why.
    """
    if limit <= 0:
        return []
    limit = min(limit, MAX_SAVED_CANDIDATES)

    saved_events = list(
        SavedEvent.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .filter(start_utc__gte=now)
        .order_by("start_utc", "id")[:limit]
    )
    pairs = _open_conflict_pairs(user_id=user_id)
    by_side = _conflicts_by_side(
        pairs,
        kind=ConflictPair.SideKind.SAVED_EVENT,
        ids={saved.id for saved in saved_events},
    )

    public_by_id = get_public_events(event_ids={saved.event_id for saved in saved_events})
    return [
        _saved_candidate(saved, public_by_id.get(saved.event_id), by_side.get(saved.id, ()))
        for saved in saved_events
    ]


def list_conflict_pairs(*, user_id: UUID) -> list[ConflictPairSnapshot]:
    """The user's open conflict pairs, oldest first.

    Only `ACTIVE` pairs — see `_open_conflict_pairs`. A resolved pair is answered and a
    cleared one is over; neither is an open conflict.
    """
    return [
        ConflictPairSnapshot(
            id=pair.id,
            user_id=pair.user_id,
            kind=pair.kind,
            left_kind=pair.left_kind,
            left_id=pair.left_id,
            right_kind=pair.right_kind,
            right_id=pair.right_id,
            detected_at=pair.detected_at,
        )
        for pair in _open_conflict_pairs(user_id=user_id)
    ]


__all__ = [
    "ConflictPairSnapshot",
    "PersonalEventCandidate",
    "SavedEventCandidate",
    "list_conflict_pairs",
    "list_personal_candidates",
    "list_saved_candidates",
]
