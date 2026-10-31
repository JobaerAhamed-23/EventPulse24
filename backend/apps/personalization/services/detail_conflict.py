"""The Detail Screen's conflict: the caller's **active** pair for one saved event.

**One question, one answer.** The Detail Screen shows a public event. The signed-in
caller may have saved it, and that save may clash with one of their own personal events.
When it does, the pair is **active** — it is waiting for a choice — and the screen must
say so, because the choice is the whole point of the surface.

**Why this is its own module.** The conflict *list* (`conflict_list`) reads every pair
the user has. The Detail Screen needs something much narrower: **the pair for this one
saved event**, and only while it is active. Reading the whole list to find one pair would
cost a query count that grows with the user's history, for a screen that shows one event.

**The id the pair stores is the save row's, not the catalog event's.** A `ConflictPair`
names a `SavedEvent` by that row's id, while the Detail Screen is keyed by the **catalog**
event id. So the read resolves the caller's save row first — the same row
`detail_read._is_saved` looks for — and then finds the pair by that row's id. The pair
never names a catalog event, and nothing here guesses.

**Only an active pair is reported.** A **resolved** pair is history: the user answered
it, and the screen has nothing to ask. A **cleared** pair ended because a side went away
without an answer, and it is nobody's decision. Only `active` means "there is a choice
waiting", so only `active` produces an indicator.

**The actions are the saved side's, not the pair's.** The Detail Screen acts on the
**saved** side — "skip this event" releases the save — so the choices are
`resolutions_for_side(kind, SAVED_EVENT)`: `keep_both`, `edit_new` and `skip_public` for
a time clash. The **union** across the pair would also offer `delete_new`, and deleting
the user's personal event is not a choice this surface should present: the user came here
to look at a public event, and the personal event is the thing in the way.

**The other side is named.** The screen knows which event it is showing, so it does not
need a symmetric pair — it needs to say what the save clashes *with*. The other side's
name comes from the catalog's title for a saved side, or from the personal event's own
name, read through the same published interface the list uses (AD-2 / AD-3).

**The read never crosses the schema wall.** The saved side's title is read through
`catalog_read`, and nothing here imports `apps.ingestion.models`.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from apps.ingestion.services.catalog_read import get_public_events
from apps.personalization.models import ConflictPair, PersonalEvent, SavedEvent
from apps.personalization.services.conflict_resolutions import resolutions_for_side
from shared.db import PERSONAL


@dataclass(frozen=True)
class DetailConflictSide:
    """The side the saved event clashes with.

    `name` is None when the other side's record is gone — the client renders "event no
    longer available" rather than a blank title, the same rule the conflict list follows.
    """

    kind: str
    id: UUID
    name: str | None
    start_time_utc: datetime
    end_time_utc: datetime | None


@dataclass(frozen=True)
class DetailConflict:
    """The caller's active pair for this event, as the Detail Screen reads it.

    **`other_side` is the personal event** in the ordinary case — the user's own event
    is what clashes with the save. It is a personal side because the save is the side the
    user just took, and the pair's other side is theirs.

    **`saved_side_id` is the save row's id**, the id the pair itself stores. It is not
    the catalog event's id — the Detail Screen is keyed by the catalog event, but the
    pair names a `SavedEvent` — and it is the id a `skip_public` resolution has to name,
    because releasing a save is releasing that row. The client cannot derive it, so the
    payload carries it.
    """

    pair_id: UUID
    kind: str
    saved_side_id: UUID
    other_side: DetailConflictSide
    actions: tuple[str, ...]


def _personal_side(event: PersonalEvent) -> DetailConflictSide:
    return DetailConflictSide(
        kind=ConflictPair.SideKind.PERSONAL_EVENT,
        id=event.id,
        name=event.name,
        start_time_utc=event.start_utc,
        end_time_utc=event.end_utc,
    )


def _missing_side(kind: str, side_id: UUID) -> DetailConflictSide:
    """A side whose record is gone.

    The pair is still real — it names two records, and one of them is no longer there.
    The side is named with no title, so the client says "event no longer available"
    rather than showing a blank.
    """
    return DetailConflictSide(
        kind=kind,
        id=side_id,
        name=None,
        start_time_utc=datetime.min.replace(tzinfo=UTC),
        end_time_utc=None,
    )


def read_detail_conflict(
    *,
    user_id: UUID,
    saved: SavedEvent,
    public_event_ids: set[UUID],
) -> DetailConflict | None:
    """The caller's active pair for this saved event, or `None`.

    **`saved` is the caller's own save row** for this event, already read. The pair names
    that row by its id, so the lookup is by the row's id and not by the catalog event's.

    **`public_event_ids`** carries the catalog ids of the saved sides the pairs name, so
    the titles can be read in **one** batched catalog read. It is empty when the pair's
    other side is a personal event, which is the ordinary case — and then no catalog
    read happens at all.
    """
    pair = (
        ConflictPair.objects.using(PERSONAL)
        .filter(
            user_id=user_id,
            status=ConflictPair.Status.ACTIVE,
            left_kind=ConflictPair.SideKind.SAVED_EVENT,
            left_id=saved.id,
        )
        .first()
    )
    if pair is None:
        pair = (
            ConflictPair.objects.using(PERSONAL)
            .filter(
                user_id=user_id,
                status=ConflictPair.Status.ACTIVE,
                right_kind=ConflictPair.SideKind.SAVED_EVENT,
                right_id=saved.id,
            )
            .first()
        )
    if pair is None:
        return None

    other_kind = (
        pair.right_kind
        if pair.left_kind == ConflictPair.SideKind.SAVED_EVENT
        else pair.left_kind
    )
    other_id = pair.right_id if pair.left_kind == ConflictPair.SideKind.SAVED_EVENT else pair.left_id

    if other_kind == ConflictPair.SideKind.PERSONAL_EVENT:
        # The user's own event. Scoped to the caller as well as to the id: the pair is
        # the caller's row, so its sides are the caller's rows too.
        event = (
            PersonalEvent.objects.using(PERSONAL)
            .filter(user_id=user_id, pk=other_id)
            .first()
        )
        other = (
            _personal_side(event)
            if event is not None
            else _missing_side(other_kind, other_id)
        )
    else:
        # The other side is a save. Its title lives in the catalog, read through the
        # published interface — never by a cross-schema query (AD-2 / AD-3).
        other_saved = (
            SavedEvent.objects.using(PERSONAL).filter(user_id=user_id, pk=other_id).first()
        )
        if other_saved is None:
            other = _missing_side(other_kind, other_id)
        else:
            public = get_public_events(event_ids=public_event_ids).get(other_saved.event_id)
            other = DetailConflictSide(
                kind=other_kind,
                id=other_id,
                name=public.title if public is not None else None,
                start_time_utc=other_saved.start_utc,
                end_time_utc=other_saved.end_utc,
            )

    return DetailConflict(
        pair_id=pair.id,
        kind=pair.kind,
        saved_side_id=saved.id,
        other_side=other,
        actions=tuple(
            sorted(
                resolutions_for_side(
                    kind=pair.kind,
                    side_kind=ConflictPair.SideKind.SAVED_EVENT,
                )
            )
        ),
    )


__all__ = [
    "DetailConflict",
    "DetailConflictSide",
    "read_detail_conflict",
]
