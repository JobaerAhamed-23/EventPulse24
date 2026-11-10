"""The digest read: the user's persisted Pulse Digest, and nothing else (AD-10, FR-6).

**This is a read of persisted rows. It computes nothing.** That is the whole design, and
the design's value: AD-10 says an explanation is persisted at composition time and
**never recomputed at render**, and this is where that rule either holds or is quietly
broken. A read that scored, ranked or regenerated a tag would be a read that could
disagree with the card the user saw that morning — and the disagreement would be silent,
because the recomputed answer would look perfectly reasonable.

So this module resolves the user's local day, finds the digest written for it, joins the
persisted rows to the display facts, and hands over plain data.

**The three states are three different facts** (FR-8):

| State | What it means |
|---|---|
| `composed` | there is a digest, and it has cards |
| `empty` | there is a digest, and it has none — "we looked and there was nothing" |
| `not_composed` | there is **no** digest — the composition job has not run yet |

The last one is not the second one. A user who arrives before the worker has composed
would be shown "nothing on the pulse today" — a **lie**, because something might be on the
pulse and the system simply has not looked yet.

**Why this is a separate module and not a function in `digest_composition.py`.** That
module is a *command* module: it opens a transaction, takes an `Actor`, writes an audit
row, and is the only writer of these rows (AD-16). A read in it would be a second kind of
thing in a module whose whole identity is "the writer". `digest_candidates.py` set the
precedent for a separate read module: "These are reads, not commands. They write
nothing, audit nothing and log nothing (AD-13)."

**Why it is not `digest_candidates.py` either.** Those are *candidate* reads — the pools
the composition ranks from. This is the *composed* read: the digest and its rows, already
decided. "What might be ranked" and "what was ranked" answer different questions about the
same day.

**The wall (AD-3).** Nothing here joins the two schemas. The public events' display facts
come from `apps.ingestion.services.catalog_read`, which hands over plain frozen
dataclasses; the personal events' display facts come from the user's own agenda. The
join happens in Python, over plain data, exactly as the composition service does it.

**The query count is bounded, and the bound is asserted by a test.** At most four
queries: the preference, the digest, the compositions, and the display facts. Three cards
must not become three-plus queries per card — an N+1 that lands inside the <500ms p95
budget is how the budget gets missed.

Design: .specs-fire/intents/pulse-digest-and-trust/work-items/
digest-read-api-design.md (decisions D1-D15).
"""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from apps.ingestion.services.catalog_read import PublicEvent, get_public_events
from apps.personalization.models import (
    DIGEST_SLOT_ORDER,
    ConflictPair,
    DigestComposition,
    DigestPreference,
    PersonalEvent,
    PulseDigest,
    SavedEvent,
)
from apps.personalization.services.digest_candidates import list_conflict_pairs
from apps.personalization.services.digest_dates import local_date_for
from shared.constants import DEFAULT_DIGEST_TIMEZONE
from shared.db import PERSONAL


class DigestStatus:
    """The three states a digest read can report.

    A closed set of three, and they are **three different facts** — not two. A `Literal`
    in the wire schema carries them to the client; this class is the service's own name
    for the same three.
    """

    COMPOSED = "composed"
    EMPTY = "empty"
    NOT_COMPOSED = "not_composed"


@dataclass(frozen=True)
class DigestCard:
    """One Pulse Card, as the read hands it over.

    **The bucket, not the score.** FR-22's raw `relevance_score` is an internal number;
    the card shows 1-5 dots. Handing over the score would invite the frontend to
    re-bucket it — which is the "recomputed at render" failure wearing a different hat,
    and would break the no-flicker rule, since the bucket the user saw this morning is a
    **persisted fact about their day**.

    **The tags are the persisted keys, in the persisted order.** They are not recomputed
    and not re-sorted: the order is the priority order, and it is what the card and the
    Detail Screen must agree on.

    **The times are instants plus the IANA zone.** AD-6: "display-time conversion
    happens at the presentation edge, never in domain logic". The API does not send a
    pre-formatted local string.

    **The display facts are optional, and that is not a gap.** They live in the catalog
    (for a public event) or in the user's own agenda (for a personal one), and either
    place may have moved on since the composition. When they have, the card says so
    through `catalog_event_missing` — and the *explanation* (the bucket, the tags, the
    badge) is still there, because AD-10 says the composition is a fact about the day and
    its explanation must not change because a source moved.
    """

    event_id: UUID
    slot: str
    event_kind: str
    #: The event's name. `None` when the display facts are gone — there is no name to
    #: show, and the card does not invent one.
    title: str | None
    canonical_url: str | None
    start_time_utc: datetime | None
    end_time_utc: datetime | None
    start_time_tz: str | None
    venue_name: str | None
    venue_city: str | None
    #: A personal event's place is free text; a public event's is a venue. Exactly one of
    #: the two is set, and both fields exist so neither has to mean two things.
    location: str | None
    tags: tuple[str, ...]
    bucket: int
    #: The Source Badge *type*, or `None` for a personal event — a personal event has no
    #: source, so it has no badge. `None` here is not "unknown"; it is "there is no
    #: source".
    source_badge: str | None
    #: Whether the event's timezone is still under review — the time is approximated and
    #: the frontend marks it as such. A **live** fact about the event, read at request
    #: time, unlike the explanation above.
    tz_review_pending: bool
    #: Whether the event's display facts are gone. The card is still valid and still
    #: explained; the client marks it rather than hiding it.
    catalog_event_missing: bool
    #: Whether the event is in an open conflict pair (FR-58). A **live** condition of the
    #: user's own calendar, read from the persisted pairs and never computed here
    #: (AD-21) — so the indicator on a card and the one on the Timeline cannot disagree.
    conflict: bool
    #: The event's **public page slug**, or `None`.
    #:
    #: **This is the shareability fact, and the server states it (FR-28).** The client
    #: does not infer it: `get_public_events` returns published, non-superseded events
    #: and *"an id that is not public is simply absent from the result"*, so a slug here
    #: means the public page exists and a `None` means it does not.
    #:
    #: **`None` has three honest reasons,** and they are all facts rather than gaps:
    #: the card is a **personal** event (the user's own agenda row — there is no public
    #: page for a personal event, and none should ever be); the catalog does not
    #: currently hold the event publicly (unpublished, `in_review` or superseded); or
    #: the event has no slug at all.
    #:
    #: **Why it matters.** A share control needs a public URL. Without this field the
    #: card could only build `/events/{event_id}` — the *personal* URL — and a friend
    #: who opened it would meet a sign-in wall instead of the event.
    public_slug: str | None
    #: The event's **lifecycle status** — `scheduled`, `postponed` or `cancelled` — or
    #: `None` when there is no catalog status to report.
    #:
    #: **A live fact, read at request time** (FR-53), exactly like `tz_review_pending`
    #: and `conflict` above. It is deliberately *not* on the composition: the composition
    #: is append-only (`append_only_mutable = frozenset()`) and AD-10 says it explains
    #: *why* the event was chosen, not *what* the event currently is. A status stored
    #: there would be frozen at composition time, and an event cancelled at noon would
    #: keep showing as live until tomorrow's digest.
    #:
    #: **`None` has two honest reasons**, and neither is a gap. The card is a
    #: **personal** event — the user's own agenda row, which no source can cancel — or
    #: the catalog no longer holds the event (unpublished or superseded), in which case
    #: the card already carries `catalog_event_missing=True`. "Not applicable" and
    #: "scheduled" are different facts, so a personal card is not defaulted to
    #: `"scheduled"`: that would claim the catalog had an opinion about a row it has
    #: never seen.
    status: str | None
    #: Whether the event is **sold out** (FR-53), or `None` when there is no catalog to
    #: have an opinion — the same two reasons `status` has.
    #:
    #: **Separate from the status, not part of it.** An event can be `scheduled` and
    #: sold out at the same time, and collapsing the two into one "state" enum would
    #: make the card unable to say both. The backend's existing vocabulary is kept
    #: unchanged: `Event.Status` for the lifecycle, a separate flag for the tickets.
    is_sold_out: bool | None


@dataclass(frozen=True)
class DigestRead:
    """The user's digest for their local day, as the read hands it over.

    `status` says which of the three states this is, and `cards` is empty for two of
    them. The two empties are different facts, and the status is what tells them apart.
    """

    status: str
    local_date: date
    timezone: str
    city: str | None
    city_source: str | None
    cards: tuple[DigestCard, ...]


def _read_preference(user_id: UUID) -> DigestPreference | None:
    """The user's digest preference, if they have one.

    **The same read the composition service makes.** The preference holds the zone the
    local day is computed in and the city the digest is about, and the read needs both.
    """
    return DigestPreference.objects.using(PERSONAL).filter(user_id=user_id).order_by("id").last()


def _find_digest(*, user_id: UUID, local_date: date) -> PulseDigest | None:
    """The user's digest for that local date, if it has one."""
    return (
        PulseDigest.objects.using(PERSONAL)
        .filter(user_id=user_id, local_date=local_date)
        .order_by("id")
        .last()
    )


def _composition_rows(*, digest_id: UUID) -> list[DigestComposition]:
    """The digest's compositions, in slot order.

    **The slot order is `DIGEST_SLOT_ORDER`, not the row order.** A `CHAR` index sorts
    alphabetically — which would put "nearby" before "must_know" — so the read sorts in
    Python against the tuple that is the single place the slot order lives. (The
    composition service does the same thing, for the same reason.)
    """
    rows = DigestComposition.objects.using(PERSONAL).filter(digest_id=digest_id).order_by("id")
    by_slot = {row.slot: row for row in rows}
    return [by_slot[slot] for slot in DIGEST_SLOT_ORDER if slot in by_slot]


def _conflicted_card_ids(
    rows: list[DigestComposition],
    *,
    user_id: UUID,
) -> set[UUID]:
    """The composition `event_id`s whose card carries the conflict indicator.

    **FR-58's indicator renders on a card whose event is in a `CONFLICT_PAIR`**, so the
    card has to know. The flag is read from the **persisted** `ConflictPair` rows and
    never computed here (AD-21: conflict detection happens "never at render") — an
    overlap computed at request time would produce a *different* answer from the
    persisted pair the moment the two disagreed.

    **A pair names two sides, and a card is one side.** The pair's sides are the
    `personal` rows — a `PersonalEvent`'s id and a `SavedEvent`'s id — while a card
    names a **catalog** event id. So the two are matched through the user's saves: one
    query for the saves of the public cards' event ids, and one for the pairs.

    **The two kinds are matched differently.** A personal card's `event_id` **is** the
    `PersonalEvent`'s id, so it matches a pair's `personal_event` side directly. A public
    card's `event_id` is the catalog event's, and a pair's `saved_event` side is the
    `SavedEvent`'s id, so the save is the bridge.

    **Only `ACTIVE` pairs count.** A `RESOLVED` pair is answered and a
    `CLEARED_BY_STATE_CHANGE` one is over; neither is an open conflict, and showing
    either would put a conflict prompt on a card for a conflict the user has settled.
    """
    personal_ids = {
        row.event_id for row in rows if row.event_kind == DigestComposition.EventKind.PERSONAL
    }
    public_ids = {
        row.event_id for row in rows if row.event_kind == DigestComposition.EventKind.PUBLIC
    }
    if not personal_ids and not public_ids:
        return set()

    pairs = list_conflict_pairs(user_id=user_id)
    if not pairs:
        return set()

    # The user's saves of the public cards' events: the bridge from a catalog event id
    # to a pair's `saved_event` side. The map goes the other way — from the saved row's
    # id to the catalog event id the card carries.
    saved_to_event: dict[UUID, UUID] = {}
    if public_ids:
        saved_to_event = {
            saved.id: saved.event_id
            for saved in SavedEvent.objects.using(PERSONAL)
            .filter(user_id=user_id)
            .filter(event_id__in=public_ids)
        }

    conflicted: set[UUID] = set()
    for pair in pairs:
        sides = (
            (pair.left_kind, pair.left_id),
            (pair.right_kind, pair.right_id),
        )
        for side_kind, side_id in sides:
            if side_kind == ConflictPair.SideKind.PERSONAL_EVENT:
                if side_id in personal_ids:
                    conflicted.add(side_id)
            elif side_kind == ConflictPair.SideKind.SAVED_EVENT:
                event_id = saved_to_event.get(side_id)
                if event_id is not None:
                    conflicted.add(event_id)
    return conflicted


def _public_display_facts(rows: list[DigestComposition]) -> dict[UUID, PublicEvent]:
    """The catalog's current facts for the public cards, in **one** query.

    `get_public_events` is a lookup, not a join: it runs against the `catalog` alias and
    returns plain data, so the wall holds (AD-3).

    **An id that is not public is simply absent.** The card still appears — with the
    facts the composition persisted — and carries `catalog_event_missing=True`.
    """
    event_ids = {
        row.event_id for row in rows if row.event_kind == DigestComposition.EventKind.PUBLIC
    }
    if not event_ids:
        return {}
    return get_public_events(event_ids=event_ids)


def _personal_display_facts(
    rows: list[DigestComposition],
    *,
    user_id: UUID,
) -> dict[UUID, PersonalEvent]:
    """The user's own agenda rows for the personal cards, in **one** query.

    **A personal event's facts are the user's own row.** There is no catalog event and
    there must not be one — the composition holds the personal event's id *by value*
    (OQ-8), and the personal event's own row is where its name, time and location live.

    The query is scoped to the user as well as to the ids: the read is already scoped by
    the session, and the scoping is repeated here because the second line of defence is
    the query itself.
    """
    personal_ids = [
        row.event_id for row in rows if row.event_kind == DigestComposition.EventKind.PERSONAL
    ]
    if not personal_ids:
        return {}
    return {
        event.id: event
        for event in PersonalEvent.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .filter(pk__in=personal_ids)
    }


def _card_for_public(
    row: DigestComposition,
    public: PublicEvent | None,
    *,
    conflict: bool,
) -> DigestCard:
    """One public card, joined to the catalog's current facts.

    **The card still exists when the catalog has moved on.** A public event that was
    superseded or unpublished after the composition still appears — with the facts the
    composition persisted, and `catalog_event_missing=True`. The reason is AD-10: the
    composition is a fact about the day, and the explanation on it must not change
    because a source moved.

    **The title and the venue come from the catalog when it has them.** The composition
    row does not hold a title, and it must not: a title is untrusted source content, and
    the composition is a durable account of *why* the event was chosen, not a copy of the
    event. So when the catalog has dropped the event there is no title to show — the card
    says the event is no longer in the catalog, and the explanation stays.
    """
    if public is None:
        return DigestCard(
            event_id=row.event_id,
            slot=row.slot,
            event_kind=row.event_kind,
            title=None,
            canonical_url=None,
            start_time_utc=None,
            end_time_utc=None,
            start_time_tz=None,
            venue_name=None,
            venue_city=None,
            location=None,
            tags=tuple(row.tags),
            bucket=row.bucket,
            source_badge=row.source_badge,
            tz_review_pending=False,
            catalog_event_missing=True,
            conflict=conflict,
            public_slug=None,
            # **No catalog, no opinion.** The event is gone from the catalog, so there
            # is no status and no sold-out flag to report. This is the same shape as
            # the missing title above: the card says what it can, and marks the rest.
            status=None,
            is_sold_out=None,
        )
    return DigestCard(
        event_id=row.event_id,
        slot=row.slot,
        event_kind=row.event_kind,
        title=public.title,
        canonical_url=public.canonical_url,
        start_time_utc=public.start_time_utc,
        end_time_utc=public.end_time_utc,
        start_time_tz=public.start_time_tz,
        venue_name=public.venue_name,
        venue_city=public.venue_city,
        location=None,
        tags=tuple(row.tags),
        bucket=row.bucket,
        source_badge=row.source_badge,
        tz_review_pending=public.tz_review_pending,
        catalog_event_missing=False,
        conflict=conflict,
        # **The public page's slug, because the event is public.** `public` came from
        # `get_public_events`, which returns published, non-superseded events only —
        # so reaching this branch at all means the public page exists.
        public_slug=public.slug,
        # **The catalog's current state, handed over as it stands.** `public` was
        # already joined to this card — the read did not go to the catalog for this,
        # it read one batched map and passed the row through. The status is a *live*
        # fact: an event cancelled after the composition still says `cancelled` here,
        # rather than showing as live until tomorrow's digest.
        #
        # **A cancelled card stays on the digest.** FR-55's removal happens at the
        # *candidate* stage — `digest_candidates` drops a save the catalog says is
        # cancelled, before it can become a candidate, so a newly cancelled event is
        # never composed at all. What is left here is a card composed *before* the
        # cancellation, and removing it here would be a second, different removal
        # than FR-55's — and would break AD-10's rule that digest rows are served as
        # stored. The card tells the truth; tomorrow's composition will not contain
        # the event at all.
        status=public.status,
        is_sold_out=public.is_sold_out,
    )


def _card_for_personal(
    row: DigestComposition,
    event: PersonalEvent | None,
    *,
    conflict: bool,
) -> DigestCard:
    """One personal card, joined to the user's own agenda row.

    **The place is the free-text `location`, verbatim.** It is not matched against a
    city and it is not turned into a venue — the codebase refuses guesses of that kind
    (the same call the composition service makes for the personal event's city band).

    **A personal event is never shareable, so its card carries no public slug.** A
    personal event is *the user's own agenda row* — their dinner, their anniversary,
    their location — and it has no catalog event and therefore no public page. A share
    control on one would produce a link to `/events/{personal_event_id}`, which the
    public page 404s; and if it did not, it would publish a stranger's private calendar.
    So `public_slug` is `None` on both personal branches, and the client renders no
    share control at all.
    """
    if event is None:
        return DigestCard(
            event_id=row.event_id,
            slot=row.slot,
            event_kind=row.event_kind,
            title=None,
            canonical_url=None,
            start_time_utc=None,
            end_time_utc=None,
            start_time_tz=None,
            venue_name=None,
            venue_city=None,
            location=None,
            tags=tuple(row.tags),
            bucket=row.bucket,
            source_badge=row.source_badge,
            tz_review_pending=False,
            catalog_event_missing=True,
            conflict=conflict,
            public_slug=None,
            # **A personal event has no lifecycle and no ticket state.** It is the
            # user's own agenda row; no source can postpone or sell it out.
            status=None,
            is_sold_out=None,
        )
    return DigestCard(
        event_id=row.event_id,
        slot=row.slot,
        event_kind=row.event_kind,
        title=event.name,
        canonical_url=None,
        start_time_utc=event.start_utc,
        end_time_utc=event.end_utc,
        start_time_tz=event.start_time_tz,
        venue_name=None,
        venue_city=None,
        location=event.location,
        tags=tuple(row.tags),
        bucket=row.bucket,
        source_badge=row.source_badge,
        tz_review_pending=False,
        catalog_event_missing=False,
        conflict=conflict,
        public_slug=None,
        # **Not applicable, not "fine".** A personal event is not cancelled and is not
        # sold out, but saying `status="scheduled"` would claim the catalog had an
        # opinion about a row it has never seen. `None` says "there is no lifecycle
        # here", and the client can tell that apart from a live event.
        status=None,
        is_sold_out=None,
    )


def read_digest(*, user_id: UUID, now: datetime) -> DigestRead:
    """The user's Pulse Digest for their local day.

    **The local date is resolved exactly as the composition resolved it** — through the
    same `local_date_for` helper, with the same preference and the same zone. If the read
    computed a different date, it would look for a digest that does not exist and report
    `not_composed` on a day that has three cards on it.

    **The zone comes from the *current* preference.** The digest row stores the zone it
    was composed in, but the read needs the zone *now* to know which day "now" is in. If
    the user moved, the zone changed, and the day may have changed with it — and the
    digest for the new day has not been composed. The response reports the digest's own
    stored zone, so a mismatch is visible rather than silent.

    **The city comes from the preference too, with its source.** FR-8's copy is "No
    qualifying events in **{city}**", and if the city is the server's fallback rather
    than the user's, the copy is misleading — so `city_source` travels alongside it.

    **Nothing is computed.** No scoring, no ranking, no tag generation. If no composition
    exists, this says so; it does not compose one (AD-11: composition is worker work, and
    a read that composes would be a write from a request path).
    """
    preference = _read_preference(user_id)
    zone_name = preference.timezone if preference else DEFAULT_DIGEST_TIMEZONE
    city = (preference.city or None) if preference else None
    city_source = (preference.city_source or None) if preference else None
    local_date = local_date_for(now=now, zone_name=zone_name)

    digest = _find_digest(user_id=user_id, local_date=local_date)
    if digest is None:
        return DigestRead(
            status=DigestStatus.NOT_COMPOSED,
            local_date=local_date,
            timezone=zone_name,
            city=city,
            city_source=city_source,
            cards=(),
        )

    rows = _composition_rows(digest_id=digest.id)
    public_by_id = _public_display_facts(rows)
    personal_by_id = _personal_display_facts(rows, user_id=user_id)
    conflicted = _conflicted_card_ids(rows, user_id=user_id)

    cards: list[DigestCard] = []
    for row in rows:
        conflict = row.event_id in conflicted
        if row.event_kind == DigestComposition.EventKind.PERSONAL:
            cards.append(
                _card_for_personal(row, personal_by_id.get(row.event_id), conflict=conflict)
            )
        else:
            cards.append(_card_for_public(row, public_by_id.get(row.event_id), conflict=conflict))

    return DigestRead(
        status=DigestStatus.EMPTY if not cards else DigestStatus.COMPOSED,
        local_date=digest.local_date,
        timezone=digest.timezone,
        city=city,
        city_source=city_source,
        cards=tuple(cards),
    )


__all__ = [
    "DigestCard",
    "DigestRead",
    "DigestStatus",
    "read_digest",
]
