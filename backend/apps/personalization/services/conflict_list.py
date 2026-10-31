"""Listing the user's conflict pairs, with both sides named (FR-33, AD-2, AD-3).

`ConflictPair`'s own docstring says the Pulse Card indicator, the Timeline indicator and
`/conflicts` all read these rows — but until now nothing listed them. This module is that
list.

**The pair row is symmetric; the list is not.** The row stores `left`/`right` sorted by
`(kind, id)`, so "which side is mine to move" is not in it. This list presents **both
sides symmetrically** — the pair, its kind, its status, and each side as
`{kind, id, name, start_time_utc, end_time_utc, start_time_tz}`. The asymmetry is decided
in the resolve flow (`conflict_resolutions`), where the caller names the side the action
is about.

**The saved side has no name of its own.** A `SavedEvent` holds the catalog Event's id by
value and a snapshot of its time; the title lives in `catalog` and is never copied into
`personal` (`conflicts._saved_side` names it `saved {event_id}` for that reason). So the
title is read through the catalog's published interface and joined here, in the application
layer — never by a cross-schema query (AD-2 / AD-3).

**The join is one batch.** `get_public_events(event_ids=…)` reads many ids in **one**
query against the `catalog` alias and hands back plain data. A user with five saved events
costs one round-trip, not five — and the whole list costs the same whether the user has
one pair or a hundred. The query count is a constant, and a test pins it.

**An absent catalog event is a state, not a crash.** `get_public_events` omits an id that
is no longer public, so a save whose catalog event has disappeared is found by **absence**.
The side reads as `available=False` with no name — "event no longer available" — rather
than a blank or an exception. The same is true of a personal side whose row is gone.

**`cleared_by_state_change` pairs are excluded.** A cleared pair ended because a side went
away *without* the user answering — an unrelated delete, an unsave, a propagation-driven
close. It is not a user's choice, so it is not presented as one: the `Resolved` section is
history the user created, and a cleared pair would sit there with a NULL resolution and
claim a decision the user never made. The endpoint's description says so.

**This is a read.** It opens no transaction, writes no audit row and touches no model
attribute. Every query is scoped to the caller's user id, so another user's pairs are
never readable.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from apps.ingestion.services.catalog_read import get_public_events
from apps.personalization.models import ConflictPair, PersonalEvent, SavedEvent
from apps.personalization.services.conflict_resolutions import resolutions_for_pair
from shared.db import PERSONAL


@dataclass(frozen=True)
class ConflictSideView:
    """One side of a pair, as the list hands it over.

    `name` is None when the side's record is gone — `available` says so, and the client
    renders "event no longer available" instead of an empty name.

    `start_time_tz` is the side's **display** zone: the personal event's own zone, or the
    catalog event's zone for a saved side. It is None when the record is gone, because the
    snapshot is UTC and the display zone is then genuinely unknown.
    """

    kind: str
    id: UUID
    name: str | None
    start_time_utc: datetime
    end_time_utc: datetime | None
    start_time_tz: str | None
    available: bool


@dataclass(frozen=True)
class ConflictPairView:
    """One pair, with both sides and the choices it offers.

    `actions` is the allowed set for an **active** pair, read from the one map the
    resolve endpoint enforces — so there is one source and not a second list. A
    **resolved** pair carries no actions — there is nothing left to choose — and instead
    carries `resolution` and `resolved_at`.

    **A pair with a saved side offers four actions.** The list presents both sides
    symmetrically and does not know which one the user will act on, so it offers the
    union across the pair's sides: `delete_new` against the personal side, `skip_public`
    against the saved one, and the two shared choices. A personal-vs-personal pair is
    unaffected — its union is exactly the three it has always offered.
    """

    pair_id: UUID
    kind: str
    status: str
    left: ConflictSideView
    right: ConflictSideView
    actions: tuple[str, ...] = ()
    resolution: str | None = None
    resolved_at: datetime | None = None


@dataclass(frozen=True)
class ConflictList:
    """The user's conflict pairs, split into what needs a decision and what is history."""

    active: tuple[ConflictPairView, ...]
    resolved: tuple[ConflictPairView, ...]


def _personal_side(event: PersonalEvent) -> ConflictSideView:
    return ConflictSideView(
        kind=ConflictPair.SideKind.PERSONAL_EVENT,
        id=event.id,
        name=event.name,
        start_time_utc=event.start_utc,
        end_time_utc=event.end_utc,
        start_time_tz=event.start_time_tz,
        available=True,
    )


def _saved_side(
    saved: SavedEvent,
    *,
    title: str | None,
    start_time_tz: str | None,
    available: bool,
) -> ConflictSideView:
    """A saved side, named by its catalog title.

    A save has no title of its own: the title lives in `catalog`. `available=False` means
    the catalog no longer holds the event, so there is no title to show.
    """
    return ConflictSideView(
        kind=ConflictPair.SideKind.SAVED_EVENT,
        id=saved.id,
        name=title,
        start_time_utc=saved.start_utc,
        end_time_utc=saved.end_utc,
        start_time_tz=start_time_tz,
        available=available,
    )


def _missing_side(kind: str, side_id: UUID) -> ConflictSideView:
    """A side whose record is gone.

    The pair is still real — it names two records, and one of them is no longer there.
    The side is listed with no name, so the client renders "event no longer available"
    rather than an empty title.

    The start time is the epoch rather than "no time": the field is a datetime, and a
    missing side must not sort as if it were the oldest event on the calendar. The
    ordering reads `available` to skip these sides entirely, so the value is only ever a
    placeholder.
    """
    return ConflictSideView(
        kind=kind,
        id=side_id,
        name=None,
        start_time_utc=datetime.min.replace(tzinfo=UTC),
        end_time_utc=None,
        start_time_tz=None,
        available=False,
    )


def _earliest_start(view: ConflictPairView) -> datetime:
    """The earlier of the pair's two start times.

    Only the **available** sides take part. A side whose record is gone has no start time
    to compare, so it cannot decide the order; a pair whose sides are both gone sorts
    last, by the epoch placeholder.

    The AC says "active pairs by the earlier side's start time" — the *earlier* side, not
    the left one. The pair row stores the sides sorted on `(kind, id)`, so the left side
    is the personal one, not the earlier one, and reading `left` would order the list by
    side kind rather than by time.
    """
    starts = [side.start_time_utc for side in (view.left, view.right) if side.available]
    return min(starts) if starts else datetime.min.replace(tzinfo=UTC)


def list_conflict_pairs(*, user_id: UUID) -> ConflictList:
    """The signed-in user's conflict pairs: active first, then resolved.

    **The query count is constant**, independent of how many pairs the user has:

    1. the pairs, scoped to `user_id`;
    2. the personal sides, in one `IN` query;
    3. the saved sides, in one `IN` query;
    4. the catalog titles, in one batched read.

    **Ordering.** Active pairs by the **earlier** side's start time, soonest first.
    Resolved pairs by **resolution time**, newest first. Both are total orders — the pair
    id breaks a tie — so the list is deterministic when two pairs share a start time.

    **`cleared_by_state_change` pairs are excluded**: nobody answered them, so they are
    not the user's history to read.
    """
    pairs = list(
        ConflictPair.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .exclude(status=ConflictPair.Status.CLEARED_BY_STATE_CHANGE)
    )

    personal_ids = {
        side_id
        for pair in pairs
        for side_kind, side_id in (
            (pair.left_kind, pair.left_id),
            (pair.right_kind, pair.right_id),
        )
        if side_kind == ConflictPair.SideKind.PERSONAL_EVENT
    }
    saved_ids = {
        side_id
        for pair in pairs
        for side_kind, side_id in (
            (pair.left_kind, pair.left_id),
            (pair.right_kind, pair.right_id),
        )
        if side_kind == ConflictPair.SideKind.SAVED_EVENT
    }

    # The side lookups are scoped to the caller **as well as** to the ids. A pair is the
    # caller's own row, so its sides are the caller's rows too — but the pair stores its
    # sides by id, and a row is only the caller's if the user id matches. Looking the ids
    # up without the user id would read another user's event and hand its name over.
    personal_events = {
        event.id: event
        for event in PersonalEvent.objects.using(PERSONAL).filter(
            user_id=user_id, pk__in=personal_ids
        )
    }
    saved_events = {
        saved.id: saved
        for saved in SavedEvent.objects.using(PERSONAL).filter(user_id=user_id, pk__in=saved_ids)
    }

    # One batched read for every saved side in the list. The ids are the catalog's; the
    # query runs against the `catalog` alias and the result is plain data, so the wall
    # holds exactly as it does for `get_public_event`.
    catalog_event_ids = {saved.event_id for saved in saved_events.values()}
    public_events = get_public_events(event_ids=catalog_event_ids)

    def side_view(kind: str, side_id: UUID) -> ConflictSideView:
        if kind == ConflictPair.SideKind.PERSONAL_EVENT:
            event = personal_events.get(side_id)
            if event is None:
                return _missing_side(kind, side_id)
            return _personal_side(event)
        saved = saved_events.get(side_id)
        if saved is None:
            return _missing_side(kind, side_id)
        public = public_events.get(saved.event_id)
        if public is None:
            # The catalog no longer holds the event: superseded, unpublished or in review.
            # The save is still here, so the side is still listed — with no title.
            return _saved_side(saved, title=None, start_time_tz=None, available=False)
        return _saved_side(
            saved,
            title=public.title,
            start_time_tz=public.start_time_tz,
            available=True,
        )

    views = [
        ConflictPairView(
            pair_id=pair.id,
            kind=pair.kind,
            status=pair.status,
            left=side_view(pair.left_kind, pair.left_id),
            right=side_view(pair.right_kind, pair.right_id),
            actions=(
                tuple(
                    sorted(
                        resolutions_for_pair(
                            kind=pair.kind,
                            side_kinds=frozenset({pair.left_kind, pair.right_kind}),
                        )
                    )
                )
                if pair.status == ConflictPair.Status.ACTIVE
                else ()
            ),
            resolution=pair.resolution,
            resolved_at=pair.resolved_at,
        )
        for pair in pairs
    ]

    active = tuple(
        sorted(
            (view for view in views if view.status == ConflictPair.Status.ACTIVE),
            key=lambda view: (_earliest_start(view), str(view.pair_id)),
        )
    )
    resolved = tuple(
        sorted(
            (view for view in views if view.status == ConflictPair.Status.RESOLVED),
            key=lambda view: (-view.resolved_at.timestamp(), str(view.pair_id)),
        )
    )
    return ConflictList(active=active, resolved=resolved)


__all__ = [
    "ConflictList",
    "ConflictPairView",
    "ConflictSideView",
    "list_conflict_pairs",
]
