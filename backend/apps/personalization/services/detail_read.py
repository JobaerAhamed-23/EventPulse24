"""The Detail Screen's read: the public facts, and the signed-in user's own state (FR-24).

**This is a read of persisted rows, and it computes no explanation.** AD-10's rule for
this surface is exact:

> the Detail Screen "is reachable for an Event that is not in today's digest; it reads the
> **most recent composition** for that `(user, event)` pair, and **renders no explanation
> rather than recomputing one if none exists**. An explanation is never generated at
> view time."

So the why-this breakdown here is the **persisted** `DigestComposition` row — whatever
day it was composed — and when there is no such row the answer is an **explicit absence**.
Not an empty breakdown. Not a zero bucket. Not a freshly-computed one. A breakdown that
was recomputed at render time could disagree with the card the user saw that morning,
and the disagreement would be silent, because the recomputed answer would look
perfectly reasonable.

**The absence is a shape, not a null field with a magic value.** `why_this` is `None`
when there is no composition — and `None` means "we have nothing for you on this event",
which is different from "we looked and the answer was nothing".

**The wall (AD-3).** The public facts come from `apps.ingestion.services.catalog_read`,
which hands over plain frozen dataclasses; the personal facts come from the `personal`
schema. Nothing here joins the two schemas, and nothing here imports
`apps.ingestion.models` (import contract `models-ingestion`).

**The Event Fit is not reached from here (AD-10).** This is the surface where the
substitution would be most tempting: an anonymous visitor sees an event with **no**
personal explanation, and the Event Fit is the one explanation an anonymous visitor is
allowed to see. Reaching for it would be exactly the substitution AD-10 calls
"company-ending" — an authenticated surface falling back to the Event Fit to fill a
missing Relevance Pulse. So the breakdown is absent, and it is honestly absent.

**The anonymous path never touches `personal` at all.** Not "does not return personal
data" — **does not query it**. A test asserts that the personal alias was never queried
on an anonymous request, which is the same technique the public catalog read's test uses.
The strongest statement about a leak is that the query never happened.

Design: .specs-fire/intents/pulse-digest-and-trust/work-items/
event-detail-api-design.md (decisions D2, D3, D8, D9, D10).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.ingestion.services.catalog_read import PublicEventDetail, get_public_event_detail
from apps.personalization.models import DigestComposition, SavedEvent
from apps.personalization.services.detail_conflict import DetailConflict, read_detail_conflict
from apps.personalization.services.neighbor_count import NeighborCount, count_neighbors
from shared.db import PERSONAL


@dataclass(frozen=True)
class WhyThis:
    """The persisted why-this breakdown, as the read hands it over.

    **This is a persisted fact, not a computation.** The tags, the bucket and the badge
    are the `DigestComposition` row's own values, read back. AD-10 says a Pulse Card is
    "a projection of it, never a stored entity" — this is that projection, on a second
    surface.

    **The bucket, not the score.** FR-22's raw `relevance_score` is an internal number;
    the screen shows 1–5 dots. Handing over the score would invite the frontend to
    re-bucket it — the "recomputed at render" failure wearing a different hat.

    **The tags are the persisted keys, in the persisted order.** They are not recomputed
    and not re-sorted: the order is the priority order, and it is what the card and the
    Detail Screen must agree on.

    **The Source Badge is a type, not a label and not an icon.** The server names the
    type; the frontend owns the label and the glyph.
    """

    tags: tuple[str, ...]
    bucket: int
    source_badge: str | None
    #: When the explanation was composed. The row's own `composed_at` — the screen can
    #: say "why you saw this on Tuesday".
    composed_at: datetime
    #: The slot the event occupied in that composition: `must_know`, `nearby` or
    #: `serendipity`. It is part of the explanation, and it is persisted.
    slot: str


@dataclass(frozen=True)
class DetailPersonal:
    """The signed-in user's own state for this event.

    **Three independent facts, and none of them implies another.** "There is no
    explanation" and "you have not saved this" are different, and a client that cannot
    tell them apart renders the wrong thing.

    `why_this` is `None` when no composition exists for this `(user, event)` pair.
    `saved` is the user's *current* save state — read from the save row, not from a tag
    on the composition, because a save may have happened since the composition was made.
    `neighbor_bucket` is the k-anonymous neighbor count, already bucketed; `None` means
    the count is below the threshold and is suppressed (D4).

    **`conflict` is a fourth independent fact**, and it is `None` when there is no
    **active** pair for this event. A resolved pair is history and a cleared one is
    nobody's decision, so neither is an indicator — only a pair waiting for an answer is.
    """

    why_this: WhyThis | None
    saved: bool
    neighbors: NeighborCount
    conflict: DetailConflict | None = None


@dataclass(frozen=True)
class EventDetail:
    """One event's Detail Screen, as the read hands it over.

    `personal` is `None` for an anonymous caller — and it is `None` rather than an empty
    `DetailPersonal` because "you are not signed in, so we looked up nothing" and "you
    are signed in and have nothing here" are different claims.
    """

    event: PublicEventDetail
    personal: DetailPersonal | None


def _most_recent_composition(*, user_id: UUID, event_id: UUID) -> DigestComposition | None:
    """The user's most recent composition for this event, whatever day it was composed.

    **The index does the work.** `DigestComposition` carries
    `digest_comp_user_event_idx` on `(user_id, event_id, -composed_at)` — the model
    docstring says it exists for exactly this lookup, and the descending `composed_at`
    means the newest row is the first the index yields.

    **A composition for an event that is not in today's digest still counts.** That is
    the point of the rule: the Detail Screen is reachable for any event the user has
    seen, and the explanation is the one they were given at the time.
    """
    return (
        DigestComposition.objects.using(PERSONAL)
        .filter(user_id=user_id, event_id=event_id)
        .order_by("-composed_at", "-id")
        .first()
    )


def _why_this(row: DigestComposition | None) -> WhyThis | None:
    """The persisted breakdown, or `None` when there is no composition."""
    if row is None:
        return None
    return WhyThis(
        tags=tuple(row.tags),
        bucket=row.bucket,
        source_badge=row.source_badge,
        composed_at=row.composed_at,
        slot=row.slot,
    )


def _saved_row(*, user_id: UUID, event_id: UUID) -> SavedEvent | None:
    """The user's own save row for this event, or `None`.

    **The user's own row**, read by the unique constraint on `(user_id, event_id)`. The
    scoping is repeated in the query as well as coming from the session, because the
    second line of defence is the query itself.

    **The row, not a boolean**, because the conflict pair names the save **row's** id —
    the Detail Screen is keyed by the catalog event's id, and the pair is not.
    """
    return (
        SavedEvent.objects.using(PERSONAL).filter(user_id=user_id, event_id=event_id).first()
    )


def read_event_detail(
    *,
    event_id: UUID,
    user_id: UUID | None,
    now: datetime,
) -> EventDetail:
    """One event's Detail Screen.

    **`user_id` is `None` for an anonymous caller**, and that is the whole of the
    difference between the two audiences. The anonymous path issues **one** query — the
    catalog's — and never touches the `personal` schema.

    **The public facts are the catalog's, through its published interface.**
    `get_public_event_detail` raises `EventNotFoundError` for an event that is not
    public, and the endpoint turns that into a 404. The Detail Screen must not show an
    event the public catalog does not list, because a link to a detail page for a hidden
    event would leak that it exists.

    **`now` bounds the event's visibility.** An event that has already started is not
    found — the same set the public catalog's list shows.

    **Nothing is computed.** No scoring, no ranking, no tag generation, no Event Fit
    fallback. If no composition exists, this says so; it does not make one.
    """
    event = get_public_event_detail(event_id=event_id, now=now)

    if user_id is None:
        # The anonymous path. **No personal query is issued** — not one, not even one
        # whose result is discarded.
        return EventDetail(event=event, personal=None)

    composition = _most_recent_composition(user_id=user_id, event_id=event_id)
    saved_row = _saved_row(user_id=user_id, event_id=event_id)
    neighbors = count_neighbors(event_id=event_id, now=now)

    # **The conflict is read only when the user has saved the event.** A pair names a
    # saved side, so without the save row there is nothing for a pair to name — and the
    # query is skipped rather than run and discarded.
    conflict = None
    if saved_row is not None:
        conflict = read_detail_conflict(
            user_id=user_id,
            saved=saved_row,
            public_event_ids={event_id},
        )

    return EventDetail(
        event=event,
        personal=DetailPersonal(
            why_this=_why_this(composition),
            saved=saved_row is not None,
            neighbors=neighbors,
            conflict=conflict,
        ),
    )


__all__ = [
    "DetailPersonal",
    "EventDetail",
    "WhyThis",
    "read_event_detail",
]
