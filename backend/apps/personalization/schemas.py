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
from decimal import Decimal
from typing import Annotated, Literal
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

    **`code` is a literal, not a bare string**, so this shape can sit in a discriminated
    union with the save-cap refusal the same endpoint can answer. See `SaveConflictOut`.
    """

    code: Literal["scheduling_conflict"]
    details: SchedulingConflictDetails | None = None


class CalendarCapDetails(Schema):
    """The `details` of a calendar-cap refusal: the cap, and one upgrade sentence.

    **Exactly two fields, and nothing else** — the same shape as `SaveCapDetails`, and
    for the same reason. No `modal`, no `title`, no `actions`, no `dismissable`: the
    refusal is an *inline* prompt with a quiet "Upgrade" link, not a modal
    (EXPERIENCE.md §3, the Free-tier cap prompt). A cap that interrupts with a modal is a
    cap that trains people to dismiss prompts.

    The two tier caps — one on connected calendars, one on saves — therefore speak **one**
    language to the frontend: a number and a sentence. The frontend renders one prompt
    component for both.
    """

    cap: int
    upgrade_hint: str


class CalendarCapOut(ErrorOut):
    """The 409 a refused calendar connection answers with (FR-50).

    **A conflict, not a bad request.** The address the user pasted is perfectly good — it
    is the *state of the account* that refuses it, because the account already holds as
    many calendars as its plan allows. The request was well-formed and conflicts with the
    account, which is what a 409 means.

    This is the only 409 the connect route can answer, so it needs no union — unlike the
    save route, which refuses for two different reasons.
    """

    code: Literal["calendar_cap_reached"]
    details: CalendarCapDetails | None = None


class SaveCapDetails(Schema):
    """The `details` of a save-cap refusal: the cap, and one upgrade sentence.

    **Exactly two fields, and nothing else.** No `modal`, no `title`, no `actions`, no
    `dismissable` — the refusal is an *inline* prompt with a quiet "Upgrade" link, not a
    modal (EXPERIENCE.md §3, the Free-tier cap prompt). A cap that interrupts with a modal
    is a cap that trains people to dismiss prompts. The schema makes the modal-shaped
    field inexpressible rather than merely absent from the prose.

    This is the same shape `CalendarProviderCapReached` carries (`calendar_connections.py`),
    so the two tier caps speak one language to the frontend.
    """

    cap: int
    upgrade_hint: str


class SaveCapOut(ErrorOut):
    """The 409 a refused save answers with (FR-49).

    **A conflict, not a rate limit.** The request was well-formed and the event is
    perfectly saveable; the *state of the account* refuses it, because the account has
    already spent its allowance. The remedy is not to wait — it is to upgrade — so this is
    a 409 and not a 429.

    **`code` is a literal, not a bare string**, so this shape can sit in a discriminated
    union with the scheduling conflict the same endpoint can answer. See `SaveConflictOut`.
    """

    code: Literal["save_cap_reached"]
    details: SaveCapDetails | None = None


#: The 409 of the save endpoint, as a **discriminated union on `code`**.
#:
#: One endpoint, two refusals, two payloads: a clashing save answers with the conflict
#: and its three actions (FR-58), and a capped save answers with the cap and one upgrade
#: sentence (FR-49). A route may declare only one schema per status code, so the two
#: shapes are joined here rather than by widening either of them into a mush.
#:
#: The discriminator is the error's own `code` — `scheduling_conflict` or
#: `save_cap_reached` — which is exactly the field the frontend branches on. A client
#: generated from this document can read `details.cap` and `details.upgrade_hint` on the
#: one branch, and `details.conflicts` on the other, without guessing.
SaveConflictOut = Annotated[
    SchedulingConflictOut | SaveCapOut,
    Field(discriminator="code"),
]


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
    #: The event's **lifecycle status** — `scheduled`, `postponed` or `cancelled` — or
    #: `None` (FR-53).
    #:
    #: **A live fact, read at request time**, exactly like `tz_review_pending` and
    #: `conflict` above — not a snapshot of the composition. An event cancelled after
    #: the composition says `cancelled` here, rather than showing as live until
    #: tomorrow's digest.
    #:
    #: **`None` covers two honest facts,** and neither is a gap: the card is a
    #: **personal** event (the user's own agenda row — no source can cancel it), or the
    #: catalog no longer holds the event publicly (unpublished or superseded), in which
    #: case `catalog_event_missing` is already `True`. A personal card is not defaulted
    #: to `"scheduled"`: that would claim the catalog had an opinion about a row it has
    #: never seen.
    status: str | None = None
    #: Whether the event is **sold out** (FR-53), or `None` for the same two reasons
    #: `status` has.
    #:
    #: **Separate from the status, not part of it.** An event can be `scheduled` and sold
    #: out at the same time, so the two are not collapsed into one "state" enum. The
    #: backend's existing vocabulary is unchanged — `Event.Status` for the lifecycle, a
    #: separate flag for the tickets — and the Detail Screen's own facts already carry
    #: both in this shape.
    is_sold_out: bool | None = None


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


class DetailNoticeOut(Schema):
    """The newest state-change notice for this event, as the Detail banner shows it.

    **It is the newest notice for this event, regardless of dismissal.** That is the
    deliberate rule of `delivery.services.notice_state`: the banner is about *this* event,
    which the user has navigated to on purpose, so dismissing the strip on the digest home
    must not hide "this event was cancelled" from the event's own page.

    **`dismissed_at` says whether the user has already closed it.** The banner renders
    that state rather than pretending the correction never happened — the notice is still
    the truth about this event, and the user may still want to read it.

    **`seen_at` is when it was first put in front of them** — not an act by them, and
    not the same thing as the dismissal. The two are separate columns on the row and
    they are separate fields here. (Today a dismissal sets both; the strip's read
    deliberately does not mark notices seen, because a `GET` that writes is the shape
    CSRF exists to stop.)

    **No `event_id`.** The Detail read is already scoped to one event and the response's
    enclosing `event` object names it. A redundant field could disagree with its own
    parent.
    """

    #: The notice's own id. The dismiss endpoint names it.
    id: UUID
    #: `domain.lifecycle.ChangeKind`'s vocabulary, carried through unchanged.
    change_kind: str
    #: The event version the change carried.
    event_version: int
    #: The user's local date when the notice was raised.
    local_date: date
    #: When the notice was first put in front of the user, or `None`.
    seen_at: datetime | None = None
    #: When the user closed it, or `None` while it is still open.
    dismissed_at: datetime | None = None
    #: When the notice was raised.
    created_at: datetime

    @classmethod
    def from_summary(cls, summary) -> "DetailNoticeOut":
        """Project `delivery`'s plain data onto the wire shape."""
        return cls(
            id=summary.id,
            change_kind=summary.change_kind,
            event_version=summary.event_version,
            local_date=summary.local_date,
            seen_at=summary.seen_at,
            dismissed_at=summary.dismissed_at,
            created_at=summary.created_at,
        )


class DetailPersonalOut(Schema):
    """The signed-in user's own state for an event (FR-24, FR-54, FR-55).

    **Five independent facts, and none of them implies another.** "There is no
    explanation" and "you have not saved this" are different, and a client that cannot
    tell them apart renders the wrong thing. The same is true of the two newest ones:
    **a notice and a mute are different facts**, and a client must not read "muted" as
    "there is nothing to say".

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
    #: FR-55: whether this user has silenced state-change notices for this event.
    #:
    #: **`False` means "not muted"**, and `True` means "notices for this event are
    #: silenced". It says nothing about the event: reminders still fire and the event
    #: still places in the digest (FR-55). A client that read this as "the event is
    #: off" would hide an event the user still sees.
    muted: bool = False
    #: FR-54: the newest state-change notice for this event, or `None`.
    #:
    #: **`None` is an explicit absence**: there is no notice for this event — not "the
    #: notice is empty". The notice read deliberately ignores
    #: `dismissed_at`, so a notice the user has already closed is **still reported
    #: here**: the banner is about this event, and dismissing the strip on the digest
    #: home must not hide "this event was cancelled" from the event's own page.
    #:
    #: The strip's list and this field are the **same fact read two ways** — the strip
    #: lists the open ones, the banner names the newest one for the event you are
    #: looking at — and they are read from the same table through the same service,
    #: so they cannot disagree.
    notice: DetailNoticeOut | None = None


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

    **`place` is one already-chosen string**, not the three fields it was chosen from:
    the venue's name, or the city when the venue has none, or a personal event's own
    location. It is null when there is nothing to state. The screen reveals it on hover
    and focus (EXPERIENCE.md §13) and never picks between candidates — the precedence is
    the server's, so this surface and the Pulse Card cannot disagree about where one
    event is.
    """

    kind: TimelineBlockKind
    id: UUID
    name: str | None = None
    start_time_utc: datetime
    end_time_utc: datetime | None = None
    start_time_tz: str
    conflict: bool = False
    state: str | None = None
    place: str | None = None

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
            place=block.place,
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
    "DetailNoticeOut",
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
    "CollectionEventOut",
    "CollectionIn",
    "CollectionOrderIn",
    "CollectionOut",
    "TimelineBlockKind",
    "TimelineBlockOut",
    "TimelineDayOut",
    "TimelineOut",
    "TimelineQuery",
    "WhyThisOut",
]


#: FR-59's four report categories on the wire. A `Literal` rather than a free string, so the
#: OpenAPI schema enumerates them and an invalid value is refused by the parser as a 422
#: before any service sees it — the same way the conflict actions are typed.
EventReportCategory = Literal["wrong_date_time", "wrong_venue", "does_not_exist", "duplicate"]


class EventReportIn(Schema):
    """The body of a report: which event, and which of the four things is wrong (FR-59).

    **There is no free-text field, and that is a product decision rather than a gap.** FR-57
    and FR-59 both put free text in Phase 2. Four fixed categories mean there is nothing for
    a user to type into, so there is nothing to moderate, nothing to leak into an editor's
    screen, and nothing that needs its own retention rule.
    """

    event_id: UUID
    category: EventReportCategory


class EventReportOut(Schema):
    """What the client needs for the toast, and deliberately nothing else.

    **No report id, no tally, no queue state.** A client that could read the tally could
    count other people's reports on an event, which is a fact about other users and not
    about this one. FR-59 asks only that the user sees "Thanks — we'll review this."

    `category` is echoed so an optimistic UI can confirm what it sent without keeping it.
    """

    reported: bool = True
    category: EventReportCategory


class CollectionIn(Schema):
    """The body of a create or a rename: a name, and nothing else (FR-49).

    **No position.** Where a new collection lands is the server's rule — the end — and a
    client that could choose would be a second writer of an ordering the reorder endpoint
    already owns. Moving one is what `PUT /collections/order` is for.
    """

    name: str = Field(min_length=1, max_length=80)


class CollectionOut(Schema):
    """One collection as the client sees it.

    `item_count` is here because every surface that lists collections wants it, and a
    client counting for itself would need the membership of each one — turning one list
    into N requests.
    """

    id: UUID
    name: str
    #: `0..n-1` within this user, dense. The order the user arranged.
    position: int
    item_count: int


class CollectionOrderIn(Schema):
    """A whole ordering, in one request (FR-49).

    **The complete list, never a move instruction.** "Put this one third" has to be
    interpreted against a list that may have changed since the client read it; a complete
    order is unambiguous, and the result is the order the user saw themselves arrange. The
    command refuses a list that does not name every collection exactly once, so the server
    never observes a partially reordered list.
    """

    collection_ids: list[UUID]


class CollectionEventOut(Schema):
    """One saved event inside a collection — **the snapshot, and only the snapshot**.

    **This deliberately carries no title, venue or URL**, which is what makes it different
    from `SavedEventOut`. Those fields are the catalog's current values, read at request
    time; reading them here would put a `catalog` query behind a `personal` endpoint, and
    AD-3 forbids relating the two. The snapshot is what AD-17 propagation keeps correct and
    what the Timeline and the conflict detector already use, so it is what this returns.

    A surface that wants titles has `GET /api/personal/saved-events`, which is the endpoint
    that owns that join.
    """

    #: The personal save's id — its identity, and what membership points at.
    id: UUID
    #: The catalog event's id, by value. No foreign key (AD-3).
    event_id: UUID
    start_time_utc: datetime
    end_time_utc: datetime | None
    #: The snapshot's version of the catalog event (AD-17).
    event_version: int


class BrowseQuotaOut(Schema):
    """What the user's save allowance stands at — for showing, never for deciding.

    **This is read without spending it.** The gate (`check_save_allowed`) counts an
    attempt by contract, so asking *it* what the allowance is would charge a user a save
    for loading a page. The read goes through `ThrottlePort.peek`, which counts nothing.

    **A Pro account has `cap: null`,** not a very large number. FR-48's consequence is
    that a Pro user has no soft wall at all, and a cap of "infinity" is a number a client
    would eventually render into the hero.
    """

    #: Saves spent in the current window. Always `0` for Pro, which spends no slots.
    used: int
    #: The daily limit, or `None` for a Pro account with no cap.
    cap: int | None = None
    #: Seconds until the window frees up. `0` when nothing is spent.
    resets_in_seconds: int = 0
    is_pro: bool = False


class BrowseCardOut(Schema):
    """One Browse card (FR-26): public facts, the personal explanation, and save state.

    **`tags` are Why-this Tags — the Relevance Pulse, not the Event Fit.** AD-10 forbids
    substituting one explanation for the other, and this surface is authed: its first
    section head says "3 worth your attention today". The tags and the confidence come
    from the same `RankingInputs` the ranking used, so the explanation cannot drift from
    the decision.

    **`is_saved` is on the card, not in an envelope-level set.** The Save button's initial
    state is a property of the card, and an already-saved event must render "Saved ✓" on
    first paint rather than flashing "Save" — which a client-side join invites.

    **`stripe` is capped server-side.** At most one card per response carries `must_know`.
    A client-side cap would be per page, so two pages would each show "their one" and the
    surface as a whole would flood.
    """

    event_id: UUID
    slug: str
    title: str
    canonical_url: str
    start_time_utc: datetime
    start_time_tz: str
    end_time_utc: datetime | None = None
    venue_name: str | None = None
    venue_city: str | None = None
    #: `scheduled`, `cancelled` or `postponed`. The card marks the last two.
    status: str
    source_badge: str
    #: FR-14/AD-6: the time is published but still under review, so the client marks it.
    tz_review_pending: bool = False
    #: The Why-this Tag keys, in priority order. The client owns the labels.
    tags: list[str] = []
    #: The Confidence Pulse bucket (FR-22) — a bucket, never the raw score.
    confidence: int = 0
    #: `public` or `must_know`.
    stripe: str = "public"
    is_saved: bool = False


class BrowseOut(Schema):
    """The Browse surface for the signed-in user (FR-26, FR-48).

    **Every state answers 200.** A user with no city, a city with nothing on this week,
    and an offset past the end are all answers rather than errors — the client tells them
    apart by `city_missing` and `total`, and tells all three from a failure by the fact
    that a failure is not a 200 at all. That distinction is the whole reason the surface
    can say "Nothing matched." and "Nothing nearby tonight." and mean different things.

    **`total` is the size of the ranked pool, not a `COUNT(*)`.** It is what the user can
    actually page to. A count taken in SQL would include events that FR-14's staleness
    bound — applied in Python, because it is per source — then drops, so the section head
    would advertise a number no amount of scrolling reaches.

    **`tier_2_starts_at` is the server's.** The two section heads are "3 worth your
    attention today" and "More this week", and the rule that splits them lives here so it
    cannot drift from the Digest's idea of what is worth attention.
    """

    city: str
    timezone: str
    window_from: datetime
    window_to: datetime
    total: int
    tier_2_starts_at: int
    quota: BrowseQuotaOut
    cards: list[BrowseCardOut] = []
    has_more: bool = False
    #: True when the user has never set a city. The surface shows the quiet empty state
    #: with "Change city" rather than guessing one the user did not choose.
    city_missing: bool = False


#: The three states the source-mute control offers, as a closed set.
#:
#: **`default` is in the set even though no row ever holds it.** The control has three
#: positions, and the third one is what the wire shape says when the user puts a source
#: back the way they found it. The service turns it into a row *deletion* — the absence
#: of a row is the default state — but the vocabulary the client sends is the three
#: positions the user sees.
SourceMuteState = Literal["mute", "show_less", "default"]


class SourceTrustOut(Schema):
    """One source's trust, as the screen renders it.

    **`band` is the 1–5 count the dots draw**, and it is the server's number. The client
    draws `band` filled dots and `5 - band` empty ones; it does not compute the band from
    `score`, because the boundaries are the server's rule and a client that recomputed
    them would be a second opinion about what a score means.

    **`score` is the raw FR-16 posterior**, in [0, 1]. It is here for the client's own
    tooltips and for a future "why is this source low?" — not for the dots.

    **`band` is never a delta.** A week-over-week drop is provably impossible
    (`domain/reliability.py`), so there is no "down" state to render.
    """

    band: int
    score: Decimal


class SourceOut(Schema):
    """One source in the registry, as the screen shows it.

    **`id` is the catalog Source's id, by value.** The mute is keyed on it, and the
    client sends it back on the write — so the id the screen shows and the id the mute
    uses are the same one.

    **`mute_state` is this user's state for this source**, and it is `"default"` for a
    source the user has never touched. It is not `None`: the control has three
    positions, and "no preference" is one of them.
    """

    id: UUID
    name: str
    #: The Source Badge type — the group this source belongs to.
    source_badge: str
    #: The source's city, when it has one.
    city: str = ""
    #: The source's trust.
    trust: SourceTrustOut
    #: This user's mute state for this source.
    mute_state: SourceMuteState = "default"
    #: Whether the source is paused. A paused source is still in the registry.
    is_paused: bool = False


class SourceGroupOut(Schema):
    """One group of sources — Official, Community, Aggregator or Crawled.

    **The four groups are always present, even when empty.** The screen renders a heading
    per group, and a group that appeared and disappeared as the registry changed would
    make the screen's shape depend on the data.
    """

    #: The Source Badge type — the group key.
    badge: str
    #: The heading the screen shows.
    label: str
    sources: list[SourceOut] = []


class SourceListOut(Schema):
    """Every source in the registry, grouped.

    **`groups` is the whole registry**, in the order the screen shows it. A registry with
    no sources answers with four empty groups rather than an error — an empty registry is
    an answer, and the screen has a quiet empty state for it.
    """

    groups: list[SourceGroupOut] = []


class SourceMuteSetIn(Schema):
    """The request body for setting one source's mute state."""

    #: The state to set. `default` restores the source to the default visibility.
    state: SourceMuteState


class SourceMuteResultOut(Schema):
    """The outcome of setting one source's mute state.

    **`changed` says whether the call did anything.** Setting the state a source was
    already in is a success, not an error — but a response claiming a change when none
    happened would make the screen redraw something that did not move.
    """

    source_id: UUID
    state: SourceMuteState
    changed: bool


class SourceRestoreDefaultsOut(Schema):
    """The outcome of the bulk reset.

    **`removed` is how many preferences were cleared**, so the screen can say what
    happened rather than just that it happened.
    """

    removed: int


# ── FR-25: the dismissal and the category mute ───────────────────────────────────

#: The chip keys a mute may name.
#:
#: **The vocabulary is the server's.** The category label the user reads comes from
#: `shared.constants.INTEREST_CHIPS`, so an unknown key would have no label — and a mute
#: on a key the server does not recognise would exclude nothing, silently, while the
#: screen showed a row the user could not make sense of.
CategoryKey = str

#: The durations a mute may last, in days. `None` means indefinite.
#:
#: **The set is closed.** Seven, thirty, ninety, or "until I change it". A mute that
#: outlived the user's patience by a typo is a mute the user has to find a screen to undo.
#:
#: **The `Literal` is the published contract, and it is why a bad duration is a
#: *shape* refusal.** The request schema refuses a duration outside the set before the
#: handler runs, so the endpoint never sees it — and a refusal that happens before the
#: command is `invalid_request`, where a refusal by the command is `invalid_input`.
#: (`tests/identity/test_profile_api.py` pins the same distinction for the profile
#: write.) The service refuses the same set in its own right, for the callers that are
#: not this endpoint.
#:
#: **The category key is open here on purpose** — it is `str`, not a `Literal` — because
#: the vocabulary is the server's and the schema should not be a second copy of it. So
#: a bad category reaches the command and is refused as a value.
CategoryMuteDuration = Literal[7, 30, 90] | None


class DismissalIn(Schema):
    """The request body for recording one dismissal.

    **Only the event id is needed.** The slot is *read*, not sent: the service resolves
    it from the user's own composition, so a client cannot claim a dismissal came from a
    slot it did not come from — and cannot put a serendipity card into the cluster by
    asserting it did.
    """

    #: The catalog event the user dismissed.
    event_id: UUID


class MutePromptOut(Schema):
    """The "less of this" prompt, when the product should show it.

    **The copy is the server's own.** The title names the category the cluster agreed on
    and the label comes from `INTEREST_CHIPS` — never from the event's title, which is
    untrusted scraped text (AD-9).

    **`category_key` is `None` for the generic variant**, when no single chip dominates
    the cluster. The client renders the generic copy in that case, and the mute it
    creates is a general one rather than a category-specific one.
    """

    title: str
    description: str
    category_key: CategoryKey | None = None


class DismissalOut(Schema):
    """What one dismissal did.

    **`cluster_advanced` says whether this dismissal counted**, and `prompt_due` says
    whether the product should now ask. Both are separate facts: a dismissal that
    advanced the counter may still not have completed a cluster, and a dismissal that did
    not advance can never complete one.
    """

    event_id: UUID
    cluster_advanced: bool
    prompt_due: bool
    #: The prompt, when one is due. `None` otherwise.
    prompt: MutePromptOut | None = None


class CategoryMuteIn(Schema):
    """The request body for setting one category mute."""

    #: The chip key to mute.
    category_key: CategoryKey
    #: How long the mute lasts. `null` means "until I change it".
    duration_days: CategoryMuteDuration = None


class CategoryMuteOut(Schema):
    """One active category mute, as the settings screen reads it."""

    #: The chip key.
    category_key: CategoryKey
    #: The server's label for the chip — the wording the user reads.
    label: str
    #: When the mute ends. `null` means it is indefinite.
    expires_at: datetime | None = None
    #: Whether the mute has no end date.
    is_indefinite: bool = False


class CategoryMuteListOut(Schema):
    """Every active category mute for the signed-in user.

    **An expired mute is not in the list.** The row is still there — it is the user's
    data — but it no longer mutes anything, so the screen does not list it.
    """

    mutes: list[CategoryMuteOut] = []


class CategoryMuteResultOut(Schema):
    """The outcome of setting or clearing one category mute.

    **`changed` says whether the call did anything.** Setting a mute that is already set
    is a success, not an error — but a response claiming a change when none happened
    would make the screen redraw something that did not move.
    """

    category_key: CategoryKey
    expires_at: datetime | None = None
    changed: bool


class CategoryMuteRestoreDefaultsOut(Schema):
    """The outcome of the bulk reset.

    **`removed` is how many mutes were cleared**, so the screen can say what happened
    rather than just that it happened.
    """

    removed: int


class RankingTermOut(Schema):
    """One weighted term of the published Relevance Pulse formula (FR-22).

    **`weight` is a string, not a number.** FR-22's bucket boundaries are exact and the
    whole of `domain/ranking.py` turns on `Decimal("0.85")` not being the float `0.85`. A
    JSON number would be parsed into a double by the browser, on the one page that exists
    to let a reader check the arithmetic — so the decimal crosses the wire as the text it
    is, and the client renders it without doing sums on it.

    **`label` is the server's, not the client's.** The same rule the interest chips and
    the category keys already follow: the client never owns a list of formula terms, so it
    cannot render a term the server does not recognise, and the wording of the explanation
    cannot drift from the thing being explained.
    """

    key: str
    label: str
    weight: str


class RankingBucketOut(Schema):
    """One step of the 1-5 dot Confidence Pulse scale (FR-22).

    `min_score` is the **inclusive** lower bound for this many dots, as a decimal string
    for the same reason `RankingTermOut.weight` is.
    """

    dots: int
    min_score: str


class RankingAmendmentOut(Schema):
    """Which amendment published the current weights, and when it last moved.

    FR-22 requires the surface to show "the current weights and the last-amendment date".
    `id` is the **PRD** amendment (what FR-22 promises a reader can look up), `record` is
    the ADR that authorises the constants, and `date` is when the published amendment last
    moved — not when the weights last changed, which may be earlier.
    """

    id: str
    record: str
    date: date


class RankingTransparencyOut(Schema):
    """The published formula, its scale, and its amendment — FR-22 made visible.

    **Every value here is projected from `shared.constants`.** The surface holds no copy
    of a weight or a boundary; a second copy on the page whose purpose is that there is
    one source of truth would be the exact drift FR-22 exists to prevent.

    `boundary_rule` is `"lower"` and says which way an exact boundary falls: a score of
    exactly 0.85 shows **4** dots, not 5. It is published because a reader checking the
    arithmetic at a boundary gets the wrong answer without it.
    """

    terms: list[RankingTermOut]
    total: str
    buckets: list[RankingBucketOut]
    boundary_rule: str
    amendment: RankingAmendmentOut
