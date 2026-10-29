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

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.personalization.services.conflict_resolutions import RESOLUTIONS_BY_KIND
from apps.personalization.services.conflicts import DetectedConflict
from apps.personalization.services.personal_events import PersonalEventSnapshot
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
    """

    id: UUID
    name: str
    start_time_utc: datetime
    end_time_utc: datetime | None = None
    start_time_tz: str
    location: str | None = None
    notes: str | None = None
    version: int

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


__all__ = [
    "ConflictAction",
    "ConflictOut",
    "ConflictResolutionIn",
    "ConflictResolutionOut",
    "ConflictResolutionValue",
    "ConflictSideOut",
    "PersonalEventCreateIn",
    "PersonalEventListOut",
    "PersonalEventListQuery",
    "PersonalEventOut",
    "PersonalEventPatchIn",
    "SchedulingConflictDetails",
    "SchedulingConflictOut",
]
