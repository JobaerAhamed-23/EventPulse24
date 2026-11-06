"""The personal-events wire shapes (AD-19).

Request and response shapes are Pydantic schemas, never ad-hoc dicts. These live in the
`personalization` app because the surface owns the contract; the data comes from
`apps.personalization.services`, which owns the queries and hands over plain data.

Times are UTC plus an explicit IANA timezone — the same shape `EventOut` uses. Display
conversion is the frontend's job (AD-6).

**The conflict payload names exactly three actions.** FR-58: "There is no 'dismiss' or 'X'
button. The user must choose one." The action list comes from the service's
`RESOLUTIONS_BY_KIND`, so a dismiss is not merely absent from the response — it is
inexpressible in the schema, and a client generated from this OpenAPI document cannot offer
one.

A conflict payload carries **no internal field**: no reminder-plan state, no catalog row, and
no field the client has no use for.
"""

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.ingestion.services.catalog_read import PublicEvent
from apps.personalization.services.conflict_list import (
    ConflictList,
    ConflictPairView,
    ConflictSideView,
)
from apps.personalization.services.conflict_resolutions import resolutions_for_side
from apps.personalization.services.conflicts import DetectedConflict
from apps.personalization.services.personal_events import PersonalEventSnapshot
from apps.personalization.services.saved_events import SavedEventSnapshot
from apps.personalization.services.timeline import TimelineBlock, TimelineDay, TimelineWeek
from shared.errors import ErrorOut

#: The choices a conflict prompt offers, as a closed set. `keep_both` and `delete_new` are
#: legal for both prompts against a personal side; the middle one differs — a time conflict
#: offers `edit_new`, a duplicate offers `update_existing`.
#:
#: `skip_public` is the third choice against a **saved** side: it releases the user's save
#: of a public event, rather than deleting a record. It is a value of its own rather than a
#: second meaning for `delete_new`, because a stored word has to mean one thing.
ConflictAction = Literal["keep_both", "edit_new", "update_existing", "delete_new", "skip_public"]

#: The actions a request may ask for. The service refuses a pairing that is illegal for the
#: pair's kind **and** the side named, so the union is accepted here and narrowed there.
ConflictResolutionValue = Literal[
    "keep_both", "edit_new", "update_existing", "delete_new", "skip_public"
]

#: The two kinds of record a conflict side can name.
ConflictSideKind = Literal["personal_event", "saved_event"]

#: The two prompts a pair can come from. Not derivable from the sides: a personal event
#: can clash with a saved event by time, or be a duplicate of it by name.
ConflictPairKind = Literal["time", "duplicate"]

#: The three states a pair can be in (AD-21 names these exactly).
ConflictPairStatus = Literal["active", "resolved", "cleared_by_state_change"]

#: The three states a digest read can report, as a closed set.
#:
#: **They are three different facts, not two.** `composed` means there is a digest and it
#: has cards; `empty` means there is a digest and it has none ("we looked and there was
#: nothing"); `not_composed` means there is **no** digest — the composition job has not
#: run yet. The last one is not the second one: a user who arrives before the worker has
#: composed would be shown "nothing on the pulse today", which is a **lie**, because
#: something might be on the pulse and the system simply has not looked yet.
#:
#: A `Literal` rather than a plain string, because the client has to tell the three apart
#: and a generated type is worth more than the convenience of a `str`.
DigestStatus = Literal["composed", "empty", "not_composed"]


class PersonalEventOut(Schema):
    """One personal event.

    `version` rises by one on every edit (AD-7's send key uses it, so it may only go up).

    `calendar_connection_id` says where the event came from: a connection's id for a row a
    calendar imported, `None` for one the user entered. It is the **id** and nothing else
    — the secret address never appears in any response shape (AD-18), and this field does
    not change that. Onboarding step 1 needs it to show what a calendar just brought in,
    and Settings → Sources will need it to say what a connection owns before it is
    disconnected.
    """

    id: UUID
    name: str
    start_time_utc: datetime
    end_time_utc: datetime | None = None
    start_time_tz: str
    location: str | None = None
    notes: str | None = None
    version: int
    calendar_connection_id: UUID | None = None

    @classmethod
    def from_snapshot(cls, event: PersonalEventSnapshot) -> "PersonalEventOut":
        """Project the command layer's plain data onto the wire shape."""
        return cls(
            id=event.id,
            name=event.name,
            start_time_utc=event.start_utc,
            end_time_utc=event.end_utc,
            start_time_tz=event.start_time_tz,
            location=event.location,
            notes=event.notes,
            version=event.version,
            calendar_connection_id=event.calendar_connection_id,
        )


class PersonalEventListOut(Schema):
    """The user's own personal events, soonest first."""

    items: list[PersonalEventOut]


class PersonalEventListQuery(Schema):
    """The query parameters of the list endpoint.

    This is a **separate** schema from `PersonalEventListOut`, and it has to be. A
    schema-typed argument is a request *body* unless it is wrapped in `Query(...)`; and the
    response schema has no bounds on it, so using it as the query model would silently
    accept `?starts_after=…` and then ignore it.

    The bounds are inclusive and apply to the start time. Both are optional: with neither,
    the list is every event the user has.
    """

    starts_after: datetime | None = None
    starts_before: datetime | None = None


class PersonalEventCreateIn(Schema):
    """The body of a create.

    The IANA timezone is **required**: a floating local time is refused rather than guessed,
    because the user's wall clock and the event's zone are not the same thing.
    """

    name: str = Field(min_length=1)
    start_time_utc: datetime
    start_time_tz: str
    end_time_utc: datetime | None = None
    location: str | None = None
    notes: str | None = None


class PersonalEventPatchIn(Schema):
    """The body of an edit. Every field is optional — an edit changes only what it names.

    A field left out is unchanged. There is no way to *clear* `location` or `notes` through
    this shape, because `None` and "not mentioned" are the same value here; that is a
    deliberate limitation of a first-cut edit endpoint, not an oversight.
    """

    name: str | None = Field(default=None, min_length=1)
    start_time_utc: datetime | None = None
    start_time_tz: str | None = None
    end_time_utc: datetime | None = None
    location: str | None = None
    notes: str | None = None


class ConflictSideOut(Schema):
    """One side of a conflict: the event that clashes.

    The times are UTC instants. The side does not carry a timezone of its own — the sides
    are two records that may live in two different zones, and a conflict is about the
    instants they occupy, not about how either is displayed.

    `kind` says which kind of record this side names: a personal event the user owns, or
    a save of a public event. The client needs it to post a resolution — the resolution
    names the side, and the side is a `(kind, id)` pair.
    """

    kind: ConflictSideKind
    id: UUID
    name: str
    start_time_utc: datetime
    end_time_utc: datetime | None = None


class ConflictOut(Schema):
    """One conflict the user must answer.

    `actions` is the closed set of three choices for this conflict's kind **and the side
    the user just acted on**. `dismiss` is not among them and cannot be expressed.

    **Both sides are named.** The 409 is the client's route to a resolution, and a
    resolution names a side — so the client needs the side it just created or saved, and
    the side it clashes with, each with its kind. `new_side` is the one the user just
    touched; `other_side` is the one it clashes with.
    """

    pair_id: UUID
    kind: ConflictPairKind
    new_side: ConflictSideOut
    other_side: ConflictSideOut
    actions: list[ConflictAction]

    @classmethod
    def from_detected(cls, conflict: DetectedConflict) -> "ConflictOut":
        """Project the detector's plain data onto the wire shape."""
        return cls(
            pair_id=conflict.pair_id,
            kind=conflict.kind,
            new_side=ConflictSideOut(
                kind=conflict.new_side.kind,
                id=conflict.new_side.id,
                name=conflict.new_side.name,
                start_time_utc=conflict.new_side.start_utc,
                end_time_utc=conflict.new_side.end_utc,
            ),
            other_side=ConflictSideOut(
                kind=conflict.other_side.kind,
                id=conflict.other_side.id,
                name=conflict.other_side.name,
                start_time_utc=conflict.other_side.start_utc,
                end_time_utc=conflict.other_side.end_utc,
            ),
            actions=sorted(
                resolutions_for_side(kind=conflict.kind, side_kind=conflict.new_side.kind)
            ),
        )


class ConflictListSideOut(Schema):
    """One side of a pair, as the conflict list hands it over.

    **`name` is nullable, and `available` says why.** A side whose record cannot be read
    has no title to show. The client renders "event no longer available" rather than a
    blank name, so the state is explicit instead of looking like an event with no title.

    A side is unavailable when its own row is gone, or — for a saved side — when the
    catalog no longer **publishes** the event. The catalog's published interface is the
    only view across the schema wall (AD-2 / AD-3), and an event that is unpublished, in
    review or superseded is simply not in it. This is the same rule `GET
    /api/personal/saved-events` follows.

    `start_time_tz` is the side's **display** zone: the personal event's own zone, or the
    catalog event's zone for a saved side. It is None for an unavailable side, because the
    snapshot is UTC and the display zone is then genuinely unknown.
    """

    id: UUID
    #: `personal_event` or `saved_event`.
    kind: ConflictSideKind
    name: str | None = None
    start_time_utc: datetime
    end_time_utc: datetime | None = None
    start_time_tz: str | None = None
    available: bool = True

    @classmethod
    def from_view(cls, side: ConflictSideView) -> "ConflictListSideOut":
        """Project the service's plain data onto the wire shape."""
        return cls(
            id=side.id,
            kind=side.kind,
            name=side.name,
            start_time_utc=side.start_time_utc,
            end_time_utc=side.end_time_utc,
            start_time_tz=side.start_time_tz,
            available=side.available,
        )


class ConflictPairOut(Schema):
    """One pair, with both sides and the choices it offers.

    **Both sides are present, symmetrically.** The pair row stores them sorted, so the row
    cannot say which side the user should move — the resolve flow decides that, by the
    action the user picks.

    `actions` is the allowed set for an **active** pair, and it comes from the service's
    maps — the same ones the resolve endpoint enforces, so there is one source and not a
    second list. A **resolved** pair carries no actions (there is nothing left to choose)
    and instead carries `resolution` and `resolved_at`.

    **A pair with a saved side offers four actions.** The list presents both sides
    symmetrically and does not know which one the user will act on, so it offers the
    union across the pair's sides: `delete_new` for the personal side, `skip_public` for
    the saved one, and the two shared choices. A personal-vs-personal pair is unaffected —
    its union is exactly the three it has always offered.
    """

    pair_id: UUID
    #: `time` or `duplicate`.
    kind: ConflictPairKind
    status: ConflictPairStatus
    left: ConflictListSideOut
    right: ConflictListSideOut
    actions: list[ConflictAction] = []
    resolution: ConflictResolutionValue | None = None
    resolved_at: datetime | None = None

    @classmethod
    def from_view(cls, pair: ConflictPairView) -> "ConflictPairOut":
        """Project the service's plain data onto the wire shape."""
        return cls(
            pair_id=pair.pair_id,
            kind=pair.kind,
            status=pair.status,
            left=ConflictListSideOut.from_view(pair.left),
            right=ConflictListSideOut.from_view(pair.right),
            actions=list(pair.actions),
            resolution=pair.resolution,
            resolved_at=pair.resolved_at,
        )


class ConflictListOut(Schema):
    """The user's conflict pairs, split into what needs a decision and what is history.

    `resolved` holds exactly the pairs **the user answered**. A pair that was closed
    because a side went away — `cleared_by_state_change` — is neither list's business:
    nobody chose it, so it is not the user's history to read.
    """

    active: list[ConflictPairOut] = []
    resolved: list[ConflictPairOut] = []

    @classmethod
    def from_view(cls, conflicts: ConflictList) -> "ConflictListOut":
        """Project the service's plain data onto the wire shape."""
        return cls(
            active=[ConflictPairOut.from_view(pair) for pair in conflicts.active],
            resolved=[ConflictPairOut.from_view(pair) for pair in conflicts.resolved],
        )


class ConflictSideRef(Schema):
    """The side a resolution acts on: its kind and its id.

    The pair row stores its two sides **by value** as `(kind, id)` — the kind beside the
    id, because the id is a UUID and a UUID does not say what it points at. This is that
    same shape, so the server can check the request against the row without a
    translation.
    """

    kind: ConflictSideKind
    id: UUID


class ConflictResolutionIn(Schema):
    """The body of a resolution: which action, and which side it is about.

    **`side` names the side the action applies to**, and it carries the kind as well as
    the id. The pair row is **symmetric** — it stores both sides sorted — so the row
    cannot say which side the user is acting on, and the request has to.

    The field is called `side` rather than `new_side` because "new" is only true of the
    prompt: for a pair reviewed later on `/conflicts` there is no new side, there are two
    sides and the user picks one.

    **The kind is what makes the request safe.** The action decides what it may act on:
    `delete_new` deletes a personal event and refuses a saved side; `skip_public`
    releases a save and refuses a personal side. So a client cannot delete a personal
    event by naming a saved side, and it cannot release somebody else's save by naming a
    personal one. The rule is per-action, which is what it has to be now that both kinds
    of side are answerable.
    """

    resolution: ConflictResolutionValue
    side: ConflictSideRef


class ConflictResolutionOut(Schema):
    """The outcome of a resolution.

    `action_side` is the side the action was about — the client opens it in edit mode for
    `edit_new`, or finds it already deleted for `delete_new`, or finds the save gone for
    `skip_public`. `other_side` is the pair's other side.

    Both carry their kind, which the old shape did not: the old `new_side_id` was always
    a personal event, so the kind was implied.
    """

    pair_id: UUID
    kind: ConflictPairKind
    resolution: ConflictResolutionValue
    status: ConflictPairStatus
    action_side: ConflictSideRef | None = None
    other_side: ConflictSideRef | None = None


class SchedulingConflictDetails(Schema):
    """The `details` of a 409: which event was written, and what it clashes with."""

    event_id: UUID
    conflicts: list[ConflictOut]


class SchedulingConflictOut(ErrorOut):
    """The 409 a conflicting create or edit answers with.

    It is an `ErrorOut` — `{code, message, details?}` — with the `details` field
    **narrowed** to the conflict payload. That narrowing is the point: the client has to
    render the three actions (FR-58), so the shape of the conflict has to be in the
    generated contract, not just in the prose of the description. With the plain `ErrorOut`
    the `details` would be an untyped dictionary, and a client generated from the OpenAPI
    document could not read a single field of it.

    The message and code come from `domain.errors.SchedulingConflictError`; the API layer
    builds the body, so the two stay in step through this schema.
    """

    details: SchedulingConflictDetails | None = None


class SavedEventOut(Schema):
    """One saved public event.

    **The times come from the snapshot; the display fields come from the catalog.** They
    are two different places, and keeping them straight is the point (AD-21):

    - `start_time_utc` and `end_time_utc` are the **snapshot** — what the user saw when
      they saved, updated only by AD-17 propagation.
    - `title`, `venue_name` and `canonical_url` are the **catalog's current** values, read
      at request time. An editorial correction shows up immediately.

    `event_version` is the snapshot's version of the catalog event. It is what lets the
    system detect that the snapshot is behind, and it is what `stale` is measured against.
    """

    #: The personal row's id. The save is a personal record; this is its identity.
    id: UUID
    #: The catalog event's id, by value.
    event_id: UUID
    title: str
    canonical_url: str
    venue_name: str | None = None
    venue_city: str | None = None
    #: The snapshot's times.
    start_time_utc: datetime
    end_time_utc: datetime | None = None
    #: The catalog's IANA zone, for display. The snapshot itself is UTC.
    start_time_tz: str
    #: The snapshot's version of the catalog event.
    event_version: int
    #: True when the snapshot may already be behind the catalog (AD-21's save race).
    stale: bool = False
    #: The catalog's version now, when it differs from the snapshot's.
    current_version: int | None = None

    @classmethod
    def from_snapshot(
        cls,
        saved: SavedEventSnapshot,
        public: PublicEvent,
        *,
        stale: bool = False,
        current_version: int | None = None,
    ) -> "SavedEventOut":
        """Project the personal row and the catalog event onto the wire shape."""
        return cls(
            id=saved.id,
            event_id=saved.event_id,
            title=public.title,
            canonical_url=public.canonical_url,
            venue_name=public.venue_name,
            venue_city=public.venue_city,
            start_time_utc=saved.start_utc,
            end_time_utc=saved.end_utc,
            start_time_tz=public.start_time_tz,
            event_version=saved.event_version,
            stale=stale,
            current_version=current_version,
        )


class SavedEventListQuery(Schema):
    """The query parameters of the saved-events list endpoint.

    The bounds are inclusive and apply to the **snapshot's** start time — the same value the
    list returns — so a filtered item and its own timestamp never disagree (AD-21).
    """

    starts_after: datetime | None = None
    starts_before: datetime | None = None


class SavedEventListOut(Schema):
    """The user's saved events, and how many were left out.

    `omitted` counts the saves whose catalog event has since disappeared — superseded or
    unpublished. They are not listed, because they have no title to show, but they are not
    hidden either: the count lets the client tell the user that something they saved is no
    longer available, rather than silently dropping it.
    """

    items: list[SavedEventOut]
    omitted: int = 0


class InterestChipOut(Schema):
    """One interest chip: its stable key and its display label.

    The **key** is what the API accepts and what is stored; the **label** is what the UI
    shows. They are separate because a renamed label must not invalidate a stored pick.
    """

    key: str
    label: str


class InterestChipsOut(Schema):
    """The ten interest chips, in the order the flow shows them."""

    items: list[InterestChipOut]


class InterestsIn(Schema):
    """The user's interest picks.

    The list **replaces** the user's set: it is the whole set, not a delta. An empty list
    is valid — that is how the step is skipped, and it clears the set.

    The keys are what is sent, never the labels: a label may be renamed, a key may not.
    """

    chip_keys: list[str] = []


class InterestsOut(Schema):
    """The user's stored interest picks."""

    chip_keys: list[str]


class DigestPreferenceIn(Schema):
    """The digest delivery time and timezone, and the two content preferences.

    The delivery time is a **local wall clock** — "09:00" means nine in the morning where
    the user is, not nine in the morning UTC. The zone says where that is.

    **The two new fields are optional, and omission means "leave it alone".** The city
    and the opt-out are separate settings, and a client that only wants to change the
    delivery time must not silently clear the city or silently re-include personal
    events.

    **`city` is the user's home city, in the catalog's spelling.** A city the catalog
    does not cover is stored as the fallback with `city_source` `fallback`, so the digest
    can say "we don't have your city yet" rather than passing the fallback off as the
    user's city.

    **A `null` city is not a clearing, and this endpoint cannot clear.** A `null` and an
    omitted field are the same value here, so "leave it alone" and "clear it" cannot be
    told apart — and a shape that cannot say which one it means must not guess. Guessing
    "clear" would wipe the city of every client that sends the field as `null`, and
    guessing "leave alone" would make the value unreachable. So a `null` city is
    **left alone**, and clearing is not offered here at all: the service can clear the
    city (`set_home_city(city=None)`), and a future settings endpoint may expose it
    through a shape that *can* distinguish the two. Until then, "no city" is reached by
    the sign-up path or by the backfill, not by this request.
    """

    delivery_time: time
    timezone: str
    city: str | None = None
    include_personal_events: bool | None = None


class DigestPreferenceOut(Schema):
    """The stored digest delivery time and timezone, and the two content preferences.

    `city_source` says how the city was arrived at — `geo`, `choice`, `fallback` or
    `backfill`. A client can show "we don't have your city yet" for a fallback rather
    than implying New York City is the user's city.
    """

    delivery_time: time | None = None
    timezone: str | None = None
    city: str | None = None
    city_source: str | None = None
    include_personal_events: bool = True


class DigestCardOut(Schema):
    """One Pulse Card on the digest (FR-6).

    **The bucket, not the score.** FR-22's raw `relevance_score` is an internal number;
    the card shows 1-5 dots. Sending the score would invite the frontend to re-bucket it
    — which is the "recomputed at render" failure wearing a different hat, and would break
    the no-flicker rule, since the bucket the user saw this morning is a **persisted fact
    about their day**. The Detail Screen's own read carries the score; the card's
    contract is the card's.

    **The tags are the persisted keys, in the persisted order.** They are not recomputed
    and not re-sorted — the order is the priority order, and it is what the card and the
    Detail Screen must agree on (AD-10). The client owns the labels.

    **The times are instants plus the IANA zone.** AD-6: "display-time conversion happens
    at the presentation edge, never in domain logic". The API does not send a
    pre-formatted local string.

    **The display facts are optional.** They live in the catalog (for a public event) or
    in the user's own agenda (for a personal one), and either place may have moved on
    since the composition. When they have, `catalog_event_missing` says so and the
    *explanation* is still there — the composition is a fact about the day, and its
    explanation must not change because a source moved.

    **`source_badge` is the variant key, or `None`.** A personal event has no source, so
    it has no badge; `None` here means "there is no source", not "unknown". The client
    owns the label and the glyph.
    """

    event_id: UUID
    #: Which slot the event fills — `must_know`, `nearby` or `serendipity`.
    slot: str
    #: `public` or `personal`. FR-19 requires the "Personal" label, so the client needs
    #: to know which kind it is looking at.
    event_kind: str
    #: The event's name. `None` when the display facts are gone — there is no name to
    #: show, and the card does not invent one.
    title: str | None = None
    canonical_url: str | None = None
    start_time_utc: datetime | None = None
    end_time_utc: datetime | None = None
    start_time_tz: str | None = None
    #: A public event's place is a venue.
    venue_name: str | None = None
    venue_city: str | None = None
    #: A personal event's place is free text ("2 Example Street"). It is **not** matched
    #: against a city and it is **not** turned into a venue.
    location: str | None = None
    #: The persisted Why-this Tag keys, in the persisted order.
    tags: list[str] = []
    #: FR-22's Confidence Pulse: 1 to 5.
    bucket: int
    #: The Source Badge variant key, or `None` for a personal event.
    source_badge: str | None = None
    #: Whether the event's timezone is still under review — the time is approximated and
    #: the client marks it as such.
    tz_review_pending: bool = False
    #: Whether the event's display facts are gone. The card is still valid and still
    #: explained; the client marks it rather than hiding it.
    catalog_event_missing: bool = False
    #: Whether the event is in an open conflict pair (FR-58). A **live** condition of the
    #: user's own calendar, read from the persisted pairs — so the indicator on a card
    #: and the one on the Timeline cannot disagree.
    conflict: bool = False
    #: The event's **public page slug**, or `None` (FR-28).
    #:
    #: **This is the shareability fact, and the server states it.** The client does not
    #: infer it: the public catalog's read returns published, non-superseded events and
    #: an event that is not public is *absent from the result*, so a slug here means the
    #: public page exists and a `None` means it does not.
    #:
    #: **`None` covers three honest facts,** and none of them is a gap: the card is a
    #: **personal** event (there is no public page for the user's own agenda row); the
    #: catalog does not currently hold the event publicly (`in_review`, unpublished or
    #: superseded); or the event has no slug.
    #:
    #: **Why it is on the wire.** Without it the card could only build
    #: `/events/{event_id}` — the *personal* URL — and a friend who opened it would meet
    #: a sign-in wall instead of the event.
    public_slug: str | None = None


class DigestOut(Schema):
    """The signed-in user's Pulse Digest for their local day (FR-5, FR-8, FR-6).

    **`status` says which of the three states this is**, and all three answer **200**.
    A 404 would mean "there is no such digest", which is true of `not_composed` and false
    of `empty` — and the client would have to map a status code onto "nothing happening"
    versus "not ready", which is exactly the interpretation the API is supposed to
    remove.

    **The city carries its `city_source`,** because the fallback city is not the user's
    city: FR-8's copy is "No qualifying events in **{city}**", and if the city is the
    server's fallback rather than the user's, the copy is misleading.

    **`timezone` is on the response.** The digest row stores the zone it was composed in,
    and the client needs it to render the local date it was given. Without it, a client
    showing "Wednesday" has no way to know which Wednesday.
    """

    status: DigestStatus
    local_date: date
    timezone: str
    city: str | None = None
    city_source: str | None = None
    #: The three slots, in slot order. Empty for the `empty` and `not_composed` states.
    cards: list[DigestCardOut] = []


class WhyThisOut(Schema):
    """The persisted why-this breakdown (FR-24, AD-10).

    **This is a persisted fact, not a computation.** The tags, the bucket and the badge
    are the `DigestComposition` row's own values, read back from the most recent
    composition for that `(user, event)` pair. AD-10 says an explanation "is never
    generated at view time", and this is where that either holds or is quietly broken.

    **The bucket, not the score.** FR-22's raw `relevance_score` is an internal number;
    the screen shows 1–5 dots. Sending the score would invite the frontend to re-bucket
    it — the "recomputed at render" failure wearing a different hat.

    **The tags are the persisted keys, in the persisted order.** The client owns the
    labels; the server states the facts.

    **The Source Badge is the variant key, or `None`.** A personal event has no source,
    so it has no badge; `None` here means "there is no source", not "unknown".
    """

    #: The persisted Why-this Tag keys, in the persisted order.
    tags: list[str] = []
    #: FR-22's Confidence Pulse: 1 to 5.
    bucket: int
    #: The Source Badge variant key, or `None` for a personal event.
    source_badge: str | None = None
    #: When the explanation was composed.
    composed_at: datetime
    #: The slot the event occupied in that composition.
    slot: str


class DetailConflictSideOut(Schema):
    """The side a saved event clashes with, as the Detail Screen reads it.

    **`name` is nullable**, for the same reason the conflict list's side is: a side
    whose record has gone has no title to show, and the client renders "event no longer
    available" rather than a blank. `ConflictSideOut` — the 409's shape — requires a
    name, because the 409 names a side the user just touched, and that one is always
    there.

    **No timezone of its own.** The side is a record that may live in a different zone
    from the event on screen, and a conflict is about the instants they occupy.
    """

    kind: ConflictSideKind
    id: UUID
    name: str | None = None
    start_time_utc: datetime
    end_time_utc: datetime | None = None


class DetailConflictOut(Schema):
    """The caller's **active** conflict pair for this event (FR-33, FR-58).

    **The screen knows which event it is showing**, so this is not a symmetric pair —
    it is the pair's *other* side, the one the save clashes with. The client does not
    have to work out which of two sides is "mine".

    **Both sides are named, because a resolution names a side.** The request body
    (`ConflictResolutionIn.side`) carries a `(kind, id)` pair, and the server checks it
    against the pair's own two sides — so the client has to be able to name the side it
    is acting on. `saved_side` is the **save row's** id, which is *not* the catalog
    event's id: the pair stores a `SavedEvent` by that row's id, and `skip_public`
    releases the save by the same id. `other_side` is the personal event's id. Without
    both, the client would have to guess an id, and a guessed id is refused by the server.

    **`actions` is the saved side's set**, not the pair's union. The Detail Screen acts
    on the save — "skip this event" releases it — so the choices are `keep_both`,
    `edit_new` and `skip_public`. The union would also offer `delete_new`, and deleting
    the user's personal event is not a choice this surface should present.

    **Only an active pair is here.** A resolved pair is history and a cleared one is
    nobody's decision; neither means "there is a choice waiting".
    """

    pair_id: UUID
    #: `time` or `duplicate`.
    kind: ConflictPairKind
    #: The side the save clashes with — the user's own personal event.
    other_side: DetailConflictSideOut
    #: The save row's own id, as the pair stores it. This is the id a `skip_public`
    #: resolution names, and it is **not** the catalog event's id.
    saved_side_id: UUID
    #: The choices, from the server's own map — the same one the resolve endpoint
    #: enforces.
    actions: list[ConflictAction] = []


class DetailPersonalOut(Schema):
    """The signed-in user's own state for an event (FR-24).

    **Three independent facts, and none of them implies another.** "There is no
    explanation" and "you have not saved this" are different, and a client that cannot
    tell them apart renders the wrong thing.

    **`why_this` is `None` when no composition exists** for this `(user, event)` pair.
    That is an **explicit absence**: not an empty breakdown, not a zero bucket, and not
    a recomputed one. AD-10 says the screen "renders no explanation rather than
    recomputing one if none exists".
    """

    #: The persisted breakdown, or `None` when there is no composition for this event.
    why_this: WhyThisOut | None = None
    #: Whether the signed-in user has saved this event.
    saved: bool = False
    #: FR-24's neighbor count, **already bucketed** and never exact.
    #:
    #: The keys are `few` (5–9), `some` (10–24), `many` (25–99) and `a_lot` (100+).
    #: `None` means the count is **below the k-anonymity threshold and suppressed** —
    #: there is no key for "suppressed", because a key would tell the client the count
    #: was computed and discarded, which is itself a signal.
    #:
    #: **There is no count field, and there is no number anywhere in this contract.**
    #: FR-24: "Exact counts are never exposed." The count is bucketed inside the
    #: service, before it becomes a number the response-building code could log or
    #: leak.
    neighbor_bucket: str | None = None
    #: The caller's **active** conflict pair for this event, or `None`. A `None` means
    #: there is nothing to decide — not that the screen failed to look.
    conflict: DetailConflictOut | None = None


class EventDetailFactsOut(Schema):
    """The event's public facts, as the Detail Screen shows them.

    **These are the catalog's own fields**, read through the published read interface.
    The description is the *stripped* field — `formats.text.plain_text` removed the
    markup, decoded the entities and truncated it before it was stored — so it is
    display content, not raw source payload (AD-9).

    **The times are instants plus the IANA zone.** AD-6: "display-time conversion happens
    at the presentation edge, never in domain logic".
    """

    id: UUID
    slug: str
    title: str
    #: The stripped description. Empty when the source had none.
    description: str = ""
    canonical_url: str
    start_time_utc: datetime
    start_time_tz: str
    end_time_utc: datetime | None = None
    venue_name: str | None = None
    venue_city: str | None = None
    venue_country_code: str | None = None
    status: str
    event_version: int
    source_name: str
    #: Whether the event's timezone is still under review — the time is approximated and
    #: the client marks it as such.
    tz_review_pending: bool = False
    #: A-15 / FR-53: the event is sold out.
    is_sold_out: bool = False


class EventDetailOut(Schema):
    """One event's Detail Screen (FR-24).

    **The public facts are the catalog's,** read through `catalog_read`'s published
    interface — never from `apps.ingestion.models` directly, and never through the
    Event Fit.

    **`personal` is `None` for an anonymous caller.** It is `None` rather than an empty
    `DetailPersonalOut` because "you are not signed in, so we looked up nothing" and
    "you are signed in and have nothing here" are different claims — and the anonymous
    path never queries the `personal` schema at all.

    **Reviews and similar-events are absent from this contract**, not present and empty.
    Reviews are ASSUM-6, deferred to Phase 3+. Similar-events needs attendance data that
    does not exist — there is no attendance record anywhere in the codebase. An empty
    `similar_events: []` would say "we looked and there are none", which is a lie for a
    user who *has* attended events the app does not know about.

    **"Same area" is city equality, and the deviation is named.** FR-24 defines it as
    "haversine distance ≤ 2 km OR same city-zip-cluster", and neither is computable:
    `Venue` has no coordinates and there is no zip data. The count is the qualifying
    users of *this* event, whose area is the event's own city. FR-24's country rule is
    not applied either: the user's home country is not recorded.
    """

    #: The event's public facts.
    event: EventDetailFactsOut
    #: The signed-in user's own state, or `None` for an anonymous caller.
    personal: DetailPersonalOut | None = None


class OnboardingStatusOut(Schema):
    """How far through the onboarding the user is.

    This is what `GET /api/auth/me` carries. It says **only** whether the onboarding is
    finished and which step the user is on — enough for the frontend to choose between the
    onboarding flow and the home. It carries no interests and no digest preference: `me`
    is about *who* the user is, and a settings blob there would grow without bound.
    """

    completed: bool
    current_step: int | None = None


class OnboardingStateOut(Schema):
    """The whole onboarding state: the progress, the interests and the digest preference.

    The interests and the digest preference are the **stored** values, so a skipped step
    shows what the skip wrote (an empty set, the default preference) rather than nothing.
    """

    completed: bool
    current_step: int | None = None
    step_name: str | None = None
    interests: list[str] = []
    digest: DigestPreferenceOut = DigestPreferenceOut()
    last_advanced_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_state(cls, state) -> "OnboardingStateOut":
        """Project the service's plain data onto the wire shape."""
        return cls(
            completed=state.completed,
            current_step=state.current_step,
            step_name=state.step_name,
            interests=list(state.interests),
            digest=DigestPreferenceOut(
                delivery_time=state.digest_delivery_time,
                timezone=state.digest_timezone,
                city=state.digest_city,
                city_source=state.digest_city_source,
                include_personal_events=state.digest_include_personal_events,
            ),
            last_advanced_at=state.last_advanced_at,
            completed_at=state.completed_at,
        )


# ─────────────────────────────────────────────────────────────────────────────
# The calendar connections (FR-50)
#
# **The address never appears in an output shape.** The secret ICS/webcal address *is*
# the credential (AD-18): Google classifies it as a secret and offers a reset for it. So
# `CalendarConnectionOut` has no field for it — not in full, not masked, not as a
# fragment. The guarantee is structural rather than careful: the shape cannot carry the
# address, so no endpoint can leak it by accident.
# ─────────────────────────────────────────────────────────────────────────────


class CalendarConnectIn(Schema):
    """A provider and the secret address to connect.

    The `address` is the secret ICS/webcal address. It is **write-only**: it goes in
    and it is never handed back, in whole or in part, in any response.
    """

    provider: str
    address: str
    #: The user's own name for the calendar ("Work", "Family") — not the URL, and not a
    #: secret. It is how two calendars are told apart in the UI.
    display_label: str = ""


class CalendarReconnectIn(Schema):
    """A new address for a connection the provider revoked.

    The provider revoked the old secret, so the address the user pastes now is a *new*
    one. The connection's row is reused rather than a second row being created.
    """

    address: str
    display_label: str = ""


class CalendarConnectionOut(Schema):
    """One calendar connection, as it is shown to the user.

    There is no `address` field and no `fingerprint` field. The fingerprint is a keyed
    HMAC and so is not a secret, but it is not the user's business either, and a digest
    in a response body is one more thing to leak in a screenshot.

    `last_error_kind` is a **slug** (`revoked`, `transient`, …), never a message and
    never a URL: an `httpx` exception message contains the full request URL, which *is*
    the credential (AD-13).
    """

    id: UUID
    provider: str
    status: str
    display_label: str = ""
    #: When the last poll finished. Null if it never has.
    last_synced_at: datetime | None = None
    #: When the next poll is due. Null if the connection is not going to be polled.
    next_sync_at: datetime | None = None
    #: Whether a worker holds the claim right now. A stale claim is a lost job, not a
    #: sync in progress.
    sync_in_progress: bool = False
    last_error_kind: str | None = None

    @classmethod
    def from_view(cls, view) -> "CalendarConnectionOut":
        """Project the service's plain data onto the wire shape."""
        return cls(
            id=view.id,
            provider=view.provider,
            status=view.status,
            display_label=view.display_label,
            last_synced_at=view.last_synced_at,
            next_sync_at=view.next_sync_at,
            sync_in_progress=view.sync_in_progress,
            last_error_kind=view.last_error_kind,
        )


class CalendarConnectionListOut(Schema):
    """The user's calendar connections."""

    items: list[CalendarConnectionOut] = []


#: The two kinds of block the Timeline draws: a personal event, or a saved public event.
#:
#: **This is not `ConflictSideKind`.** A conflict side names *a side of a pair* —
#: `personal_event` / `saved_event` — and says which table its id points at. A block names
#: *what the screen is drawing*, and a block made from a save is a **public** block: it
#: carries the catalog event's id, because that is the id the screen routes to. The two
#: vocabularies answer different questions, so they stay apart.
TimelineBlockKind = Literal["personal", "public"]


class TimelineBlockOut(Schema):
    """One block on one day of the Timeline.

    **`id` is the id the screen acts on.** For a personal block it is the personal event's
    id; for a public block it is the **catalog** event's id, so the screen routes to
    `/events/:id` without knowing which table it came from.

    **`name` is nullable, and that is a state rather than a hole.** A save whose catalog
    event has disappeared has no title to show — the save is still the user's own record
    and its snapshot still has a time, so the block is still drawn, and the client says
    "event no longer available" rather than showing a blank.

    **`start_time_tz` is the event's own zone**, not the zone the week is cut in. A public
    event in Berlin, shown to a user in Los Angeles, is on a different Los Angeles day than
    its own clock suggests — so the block carries its own zone, and the response carries
    the user's zone separately.

    **`conflict` is already decided.** The server projects the pairs onto the blocks, so
    the screen does not have to know what a conflict pair is, and the two surfaces — the
    Pulse Card and the Timeline — cannot disagree about which block is flagged.

    **`state` is the catalog's lifecycle word**, carried through unchanged — the same
    `str` the event detail and the public page already carry, because the vocabulary is
    the backend's and a second one here would be a translation layer with nothing to
    translate. It is null for a personal block, which has no lifecycle, and for a public
    block whose catalog event has disappeared, where the state is unknown rather than
    normal — the same distinction `name` already draws.

    A `cancelled` block is still returned. FR-55 removes a cancelled event from the
    *digest*; the Timeline is the user's calendar, and a cancelled event is still on it
    until they take it off.
    """

    kind: TimelineBlockKind
    id: UUID
    name: str | None = None
    start_time_utc: datetime
    end_time_utc: datetime | None = None
    start_time_tz: str
    conflict: bool = False
    state: str | None = None

    @classmethod
    def from_block(cls, block: TimelineBlock) -> "TimelineBlockOut":
        """Project the service's plain data onto the wire shape."""
        return cls(
            kind=block.kind,
            id=block.id,
            name=block.name,
            start_time_utc=block.start_time_utc,
            end_time_utc=block.end_time_utc,
            start_time_tz=block.start_time_tz,
            conflict=block.conflict,
            state=block.state,
        )


class TimelineDayOut(Schema):
    """One local day, with its blocks in time order.

    **A multi-day event appears on every day it covers.** An event running from Friday
    22:00 to Saturday 02:00 is a Friday block *and* a Saturday block, and the indicator
    fires on whichever day-cell the overlap falls in.
    """

    date: date
    blocks: list[TimelineBlockOut] = []

    @classmethod
    def from_day(cls, day: TimelineDay) -> "TimelineDayOut":
        """Project the service's plain data onto the wire shape."""
        return cls(
            date=day.date,
            blocks=[TimelineBlockOut.from_block(block) for block in day.blocks],
        )


class TimelineQuery(Schema):
    """The query parameters of the Timeline endpoint.

    **`week` is any date in the wanted week.** The response names that week's Monday and
    Sunday, so the client does not have to know which day of the week it asked for. With
    no `week`, the current week in the user's own zone is returned — the user's zone, not
    the server's, because a week is cut at local midnight.

    A malformed value is a 422: the parameter is typed as a date, so Django Ninja's own
    validation answers it, on the same path every other malformed query in this codebase
    takes.
    """

    week: date | None = None


class TimelineOut(Schema):
    """One Mon–Sun week, in the user's timezone.

    **Seven days, always.** An empty week still has seven day cells, each with an empty
    `blocks` list — the screen draws seven columns, and it should not have to know whether
    the week has anything in it.

    `timezone` is the zone the days were cut in, so the client can label the week without
    guessing.
    """

    #: The local Monday.
    week_start: date
    #: The local Sunday.
    week_end: date
    #: The zone the days were cut in.
    timezone: str
    days: list[TimelineDayOut] = []

    @classmethod
    def from_week(cls, week: TimelineWeek) -> "TimelineOut":
        """Project the service's plain data onto the wire shape."""
        return cls(
            week_start=week.week_start,
            week_end=week.week_end,
            timezone=week.timezone,
            days=[TimelineDayOut.from_day(day) for day in week.days],
        )


__all__ = [
    "CalendarConnectIn",
    "CalendarConnectionListOut",
    "CalendarConnectionOut",
    "CalendarReconnectIn",
    "ConflictAction",
    "ConflictListOut",
    "ConflictListSideOut",
    "ConflictOut",
    "ConflictPairKind",
    "ConflictPairOut",
    "ConflictPairStatus",
    "ConflictResolutionIn",
    "ConflictResolutionOut",
    "ConflictResolutionValue",
    "ConflictSideKind",
    "ConflictSideOut",
    "ConflictSideRef",
    "DetailPersonalOut",
    "DigestCardOut",
    "DigestOut",
    "DigestPreferenceIn",
    "DigestPreferenceOut",
    "DigestStatus",
    "EventDetailFactsOut",
    "EventDetailOut",
    "InterestChipOut",
    "InterestChipsOut",
    "InterestsIn",
    "InterestsOut",
    "OnboardingStateOut",
    "OnboardingStatusOut",
    "PersonalEventCreateIn",
    "PersonalEventListOut",
    "PersonalEventListQuery",
    "PersonalEventOut",
    "PersonalEventPatchIn",
    "SavedEventListOut",
    "SavedEventListQuery",
    "SavedEventOut",
    "SchedulingConflictDetails",
    "SchedulingConflictOut",
    "TimelineBlockKind",
    "TimelineBlockOut",
    "TimelineDayOut",
    "TimelineOut",
    "TimelineQuery",
    "WhyThisOut",
]
