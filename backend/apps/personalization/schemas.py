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

from datetime import datetime, time
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.ingestion.services.catalog_read import PublicEvent
from apps.personalization.services.conflict_resolutions import RESOLUTIONS_BY_KIND
from apps.personalization.services.conflicts import DetectedConflict
from apps.personalization.services.personal_events import PersonalEventSnapshot
from apps.personalization.services.saved_events import SavedEventSnapshot
from shared.errors import ErrorOut

#: The three choices a conflict prompt offers, as a closed set. `keep_both` and
#: `delete_new` are legal for both prompts; the middle one differs — a time conflict offers
#: `edit_new`, a duplicate offers `update_existing`.
ConflictAction = Literal["keep_both", "edit_new", "update_existing", "delete_new"]

#: The actions a request may ask for. The service refuses a pairing that is illegal for the
#: pair's kind, so the union is accepted here and narrowed there.
ConflictResolutionValue = Literal["keep_both", "edit_new", "update_existing", "delete_new"]


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
    """

    id: UUID
    name: str
    start_time_utc: datetime
    end_time_utc: datetime | None = None


class ConflictOut(Schema):
    """One conflict the user must answer.

    `actions` is the closed set of three choices for this conflict's kind. `dismiss` is not
    among them and cannot be expressed.
    """

    pair_id: UUID
    kind: str
    other: ConflictSideOut
    actions: list[str]

    @classmethod
    def from_detected(cls, conflict: DetectedConflict) -> "ConflictOut":
        """Project the detector's plain data onto the wire shape."""
        return cls(
            pair_id=conflict.pair_id,
            kind=conflict.kind,
            other=ConflictSideOut(
                id=conflict.other_side.id,
                name=conflict.other_side.name,
                start_time_utc=conflict.other_side.start_utc,
                end_time_utc=conflict.other_side.end_utc,
            ),
            actions=sorted(RESOLUTIONS_BY_KIND[conflict.kind]),
        )


class ConflictResolutionIn(Schema):
    """The body of a resolution: which of the three, and which event is the new one.

    `new_side_id` is required because the pair row is **symmetric** — it stores both sides
    sorted, so the row cannot say which side the user just created. The prompt's asymmetry
    lives in the client (it knows which event it just made) and comes back here.

    The body carries the id only, not the kind: this endpoint resolves conflicts *on
    personal events*, so the new side is a personal event by definition. That keeps the
    shape narrow — a client cannot name a saved event's id and have it deleted.
    """

    resolution: ConflictResolutionValue
    new_side_id: UUID


class ConflictResolutionOut(Schema):
    """The outcome of a resolution.

    `new_side_id` is the event the prompt called "new" — the client opens it in edit mode
    for `edit_new`, or finds it already deleted for `delete_new`.
    """

    pair_id: UUID
    kind: str
    resolution: str
    status: str
    new_side_id: UUID | None = None
    existing_side_id: UUID | None = None


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


__all__ = [
    "CalendarConnectIn",
    "CalendarConnectionListOut",
    "CalendarConnectionOut",
    "CalendarReconnectIn",
    "ConflictAction",
    "ConflictOut",
    "ConflictResolutionIn",
    "ConflictResolutionOut",
    "ConflictResolutionValue",
    "ConflictSideOut",
    "DigestPreferenceIn",
    "DigestPreferenceOut",
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
]
