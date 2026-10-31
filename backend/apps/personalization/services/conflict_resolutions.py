"""Resolving a conflict (FR-58): the user's explicit choice on a conflict prompt.

FR-58's prompt has **exactly three buttons and no dismiss**. "There is no 'dismiss' resolution
— the user must make an explicit choice." So every prompt ends in a recorded resolution, and
this module is where that happens.

The three choices, against a **personal** side:

- **`keep_both`** — "Keep both — I'll manage." The pair closes as `resolved`, and the
  conflict indicator stays on both events permanently. No further prompting.
- **`edit_new`** — "Edit the new one." The resolution is recorded, and the caller opens the new
  event in edit mode; after the edit, detection re-runs.
- **`delete_new`** — "Delete the new one." The new event is removed, through
  `delete_personal_event` — one path to delete an event, one audit trail.

For a duplicate prompt, button 2 is relabelled "Update the existing one" and maps to
`update_existing`, which opens the *existing* event in edit mode.

**A saved side has its own third button.** A pair can name a **saved public event** on one
side — the user saved a public event and it clashed with one of their own. The destructive
action there is not "delete" but **"skip"**: the save is released, through the existing
saved-events command. That is `skip_public`, and it is a resolution value of its own rather
than a second meaning for `delete_new` — a stored word has to mean one thing, or the
Resolved list and the audit trail both have to disambiguate by the side's kind before they
can say what the user did.

**The action determines which side it acts on.** `skip_public` *is* "the saved side";
`edit_new` and `delete_new` *are* "the personal side"; `keep_both` is about neither. The
request names the side the action is about, and the server checks that the side named is
the one the action targets. So a client cannot delete a personal event by naming a saved
side — `delete_new` does not accept a saved side — and it cannot release a save by naming
a personal one. The safety property is per-action rather than per-endpoint, which is what
it has to be now that both kinds of side are answerable.

**The kind decides the middle action's name; the side's kind decides the destructive one.**
A time pair offers `edit_new` and a duplicate offers `update_existing` — that is the
`RESOLUTIONS_BY_KIND` map. A pair with a saved side replaces `delete_new` with
`skip_public` — that is `RESOLUTIONS_BY_KIND_SAVED`. Two maps, one per side kind, and the
**prompt** offers the set for the side the user just acted on, while the **list** offers
the union across the pair's sides (a pair with a saved side can be answered on either
side, so both destructive actions are real choices).

**Every answered prompt records its resolution, whichever button was pressed.** The pair's
status is `resolved` in all four cases — including "delete the new one" and "skip public".
The model's `conflict_pair_status_ck` is what forces this: a `cleared_by_state_change` pair
must carry a NULL resolution, so a pair the user answered can never be a cleared one.
`cleared_by_state_change` is reserved for a pair that ended because a side went away
*without* the user answering — an unrelated delete, an unsave, or a propagation-driven
close.

**"Skip public" is answered, not abandoned.** The resolution is recorded on the pair
*before* the save is released, and the release is told to leave that one pair alone
(`unsave_event(..., keep_pair=…)`). Without that, the unsave would close the pair as
`cleared_by_state_change` — NULLing the answer the user just gave and turning their
choice into "nobody answered", which would drop it out of the Resolved list entirely.

A closed pair is immutable (AD-21) and never re-prompted, so resolving one twice is refused
here rather than hitting the database's `guard_conflict_pair` trigger.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.personalization.models import ConflictPair, PersonalEvent, SavedEvent
from apps.personalization.services.audit import write_audit
from apps.personalization.services.personal_events import delete_personal_event
from apps.personalization.services.saved_events import unsave_event
from domain.errors import NotFoundError, ValidationError
from shared.actor import Actor
from shared.db import PERSONAL


class ConflictPairNotFoundError(NotFoundError):
    """The pair doesn't exist, or isn't the caller's."""

    default_message = "We couldn't find that conflict."


class ConflictAlreadyResolvedError(ValidationError):
    """The pair was already closed. A closed pair is never re-prompted (AD-21)."""

    code = "conflict_already_resolved"
    default_message = "That conflict has already been answered."


class IllegalResolutionError(ValidationError):
    """The resolution is not one of the actions this pair's kind and side offer (FR-58)."""

    code = "illegal_resolution"
    default_message = "That isn't one of the choices for this conflict."


class SideNotInPairError(ValidationError):
    """The request named a side that is not one of the pair's two sides.

    The pair row is symmetric — it stores both sides sorted — so the request has to say
    which side the action is about. A request naming anything else is asking the server
    to act on a record that is not part of this conflict, and it is refused rather than
    quietly answered with a resolution that has no other side.
    """

    code = "side_not_in_pair"
    default_message = "That isn't one of the two things this conflict is about."


class ImportedEventNotDeletableError(ValidationError):
    """The side to delete is an imported event, and imported events cannot be deleted (D3).

    Deleting an imported event would delete a row the **provider** owns: the next poll
    would see the entry still in the feed and recreate it. So the user picks "Delete", the
    event disappears for an hour, and then it comes back — which is a lie the button tells.

    So the button is not offered for an imported side, and the service refuses it if a
    caller asks for it anyway. The imported event's user is the provider; only the
    provider can remove it.
    """

    code = "imported_event_not_deletable"
    default_message = "That event comes from your calendar, so we can't delete it here."


#: Which resolutions each kind of conflict offers **against a personal-event side**.
#:
#: FR-58's two prompts have different button sets: a time conflict offers "Edit the new
#: one", a duplicate offers "Update the existing one". `keep_both` and `delete_new` are
#: legal for both.
RESOLUTIONS_BY_KIND: dict[str, frozenset[str]] = {
    ConflictPair.Kind.TIME: frozenset(
        {
            ConflictPair.Resolution.KEEP_BOTH,
            ConflictPair.Resolution.EDIT_NEW,
            ConflictPair.Resolution.DELETE_NEW,
        }
    ),
    ConflictPair.Kind.DUPLICATE: frozenset(
        {
            ConflictPair.Resolution.KEEP_BOTH,
            ConflictPair.Resolution.UPDATE_EXISTING,
            ConflictPair.Resolution.DELETE_NEW,
        }
    ),
}

#: Which resolutions each kind of conflict offers when the pair has a **saved** side.
#:
#: The destructive action is `skip_public` rather than `delete_new`: a save is *released*,
#: not deleted — the public event belongs to the catalog and the user's own save of it is
#: what goes away. The middle action keeps the kind's name (`edit_new` for a time
#: conflict, `update_existing` for a duplicate).
#:
#: **This map is the set the client may choose from, not the set legal against a saved
#: side.** Each action names its own target: `edit_new` and `update_existing` open the
#: **personal** side in the edit sheet, `delete_new` deletes the **personal** side, and
#: `skip_public` releases the **saved** side. So a saved side can only ever be released,
#: never deleted or edited — and the refusal of `delete_new` against a saved side comes
#: from the action's own target, not from this set.
RESOLUTIONS_BY_KIND_SAVED: dict[str, frozenset[str]] = {
    ConflictPair.Kind.TIME: frozenset(
        {
            ConflictPair.Resolution.KEEP_BOTH,
            ConflictPair.Resolution.EDIT_NEW,
            ConflictPair.Resolution.SKIP_PUBLIC,
        }
    ),
    ConflictPair.Kind.DUPLICATE: frozenset(
        {
            ConflictPair.Resolution.KEEP_BOTH,
            ConflictPair.Resolution.UPDATE_EXISTING,
            ConflictPair.Resolution.SKIP_PUBLIC,
        }
    ),
}


def _target_side_kind(resolution: str) -> str:
    """The kind of side an action acts on.

    Every action names its own target, and that is what makes the request safe:

    - `keep_both` acts on neither side;
    - `edit_new`, `update_existing` and `delete_new` act on a **personal** side;
    - `skip_public` acts on a **saved** side.

    So a client cannot delete a personal event by naming a saved side (`delete_new`
    demands a personal side), and it cannot release a save by naming a personal one
    (`skip_public` demands a saved side).
    """
    if resolution == ConflictPair.Resolution.SKIP_PUBLIC:
        return ConflictPair.SideKind.SAVED_EVENT
    return ConflictPair.SideKind.PERSONAL_EVENT


def resolutions_for_side(*, kind: str, side_kind: str) -> frozenset[str]:
    """The actions legal for a pair of this kind, against a side of this kind.

    The **kind** decides the middle action's name; the **side's kind** decides the
    destructive one. A saved side cannot be deleted, and a personal side cannot be
    skipped — there is no save to release and no personal event to un-save.
    """
    if side_kind == ConflictPair.SideKind.SAVED_EVENT:
        return RESOLUTIONS_BY_KIND_SAVED[kind]
    return RESOLUTIONS_BY_KIND[kind]


def resolutions_for_pair(*, kind: str, side_kinds: frozenset[str]) -> frozenset[str]:
    """The actions a pair offers, across **its own two sides**.

    The conflict *list* uses this: it presents both sides symmetrically and does not know
    which one the user will act on, so it offers every action legal against either side.
    A personal-vs-personal pair therefore offers exactly `RESOLUTIONS_BY_KIND[kind]` —
    three actions, as it always has — while a pair with a saved side offers the
    personal side's `delete_new` **and** the saved side's `skip_public`, because both
    are real choices the user can make about that pair.
    """
    actions: frozenset[str] = frozenset()
    for side_kind in side_kinds:
        actions |= resolutions_for_side(kind=kind, side_kind=side_kind)
    return actions


@dataclass(frozen=True)
class Resolution:
    """The outcome of resolving a conflict."""

    pair_id: UUID
    kind: str
    resolution: str
    status: str
    #: The side the action was about, for `edit_new`, `delete_new` and `skip_public`. The
    #: caller opens it in edit mode, or finds it already deleted, or finds the save gone.
    action_side_id: UUID | None = None
    action_side_kind: str | None = None
    #: The pair's other side.
    other_side_id: UUID | None = None
    other_side_kind: str | None = None


def _resolution_value(resolution: str) -> str:
    """The stored resolution, rejecting anything outside the five values."""
    try:
        return ConflictPair.Resolution(resolution).value
    except ValueError:
        raise IllegalResolutionError(details={"resolution": str(resolution)}) from None


def resolve_conflict(
    *,
    user_id: UUID,
    pair_id: UUID,
    resolution: str,
    side_kind: str,
    side_id: UUID,
    actor: Actor,
    now: datetime,
) -> Resolution:
    """Record the user's choice on a conflict prompt (FR-58).

    The resolution is recorded on the pair **before** the action it names, so the audit trail
    shows what the user chose even if the follow-up edit lands later. `delete_new` deletes the
    personal event through `delete_personal_event` — one path to delete an event, one audit
    trail — and `skip_public` releases the save through `unsave_event`, for the same reason.

    The pair's status is `resolved` whatever the choice was: a pair the user answered carries
    their answer, and the model's `conflict_pair_status_ck` makes a cleared pair (a NULL
    resolution) the only other shape.

    The caller says which side the action is about, because the pair row itself is
    symmetric: it stores both sides sorted, so the prompt's asymmetry cannot live in the
    row. The service checks that the side named is one of the pair's two sides, and that
    the action is legal against a side of that kind.
    """
    value = _resolution_value(resolution)

    with transaction.atomic(using=PERSONAL):
        pair = ConflictPair.objects.using(PERSONAL).filter(user_id=user_id, pk=pair_id).first()
        if pair is None:
            raise ConflictPairNotFoundError(details={"pair_id": str(pair_id)})
        if pair.status != ConflictPair.Status.ACTIVE:
            raise ConflictAlreadyResolvedError(details={"pair_id": str(pair_id)})

        other_kind, other_id = _other_side(pair, side_kind, side_id)
        if other_id is None:
            # The request named a side that is not one of the pair's two. Answering it
            # would act on a record that has nothing to do with this conflict.
            raise SideNotInPairError(details={"side_kind": str(side_kind), "side_id": str(side_id)})

        # The action names its own target, and the named side has to be that target.
        # `keep_both` is about neither side, so either of the pair's sides may be named;
        # every other action acts on exactly one kind of side, and a request naming the
        # other kind is refused.
        allowed = resolutions_for_side(kind=pair.kind, side_kind=side_kind)
        if value not in allowed:
            raise IllegalResolutionError(
                details={"resolution": value, "kind": pair.kind, "side_kind": str(side_kind)}
            )
        if value != ConflictPair.Resolution.KEEP_BOTH and side_kind != _target_side_kind(value):
            raise IllegalResolutionError(
                details={"resolution": value, "kind": pair.kind, "side_kind": str(side_kind)}
            )

        # D3: an imported event cannot be deleted by the user — the provider owns it, and
        # the next poll would recreate the row anyway. The refusal happens **before** the
        # pair is marked resolved, so a refused attempt leaves the pair active and still
        # answerable with a choice that works.
        if value == ConflictPair.Resolution.DELETE_NEW and _is_imported_personal_event(
            kind=side_kind, event_id=side_id
        ):
            raise ImportedEventNotDeletableError(details={"side_id": str(side_id)})

        # The user's choice is recorded on the pair *first*, and it is recorded as a
        # `resolved` pair whatever the choice was — including "delete the new one", "skip
        # public" and "edit the new one". The model's `conflict_pair_status_ck` is what
        # forces this: a `cleared_by_state_change` pair must carry a NULL resolution, so a
        # pair the user answered can never be a cleared one. `cleared_by_state_change` is
        # for a pair that ended because a side went away *without* the user answering it.
        pair.status = ConflictPair.Status.RESOLVED
        pair.resolution = value
        pair.resolved_at = now
        pair.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])

        if value == ConflictPair.Resolution.DELETE_NEW:
            # The action the button names. It goes through `delete_personal_event`, so there
            # is one path to delete an event and one audit trail for it.
            delete_personal_event(
                user_id=user_id,
                event_id=side_id,
                actor=actor,
                now=now,
            )
        elif value == ConflictPair.Resolution.SKIP_PUBLIC:
            # The save is released, through the existing saved-events command — one path to
            # remove a save, one audit trail. `keep_pair` leaves **this** pair alone: it is
            # being answered, not abandoned, and closing it here would NULL the answer the
            # user just gave.
            unsave_event(
                user_id=user_id,
                event_id=_catalog_event_id_for_save(user_id=user_id, saved_id=side_id),
                actor=actor,
                now=now,
                keep_pair=pair.id,
            )

        write_audit(
            actor=actor,
            action="conflict.resolved",
            target_type="conflict_pair",
            target_id=pair.id,
            details={
                "resolution": value,
                "kind": pair.kind,
                "side_kind": str(side_kind),
                "side_id": str(side_id),
                "deleted": value == ConflictPair.Resolution.DELETE_NEW,
                "skipped": value == ConflictPair.Resolution.SKIP_PUBLIC,
            },
        )
        return Resolution(
            pair_id=pair.id,
            kind=pair.kind,
            resolution=value,
            status=ConflictPair.Status.RESOLVED,
            action_side_id=side_id,
            action_side_kind=side_kind,
            other_side_id=other_id,
            other_side_kind=other_kind,
        )


def _catalog_event_id_for_save(*, user_id: UUID, saved_id: UUID) -> UUID:
    """The catalog event id of one of the caller's saves.

    `unsave_event` takes the **catalog** event id, because that is how a save is
    identified from the outside — `DELETE /api/personal/saved-events/{catalog_event_id}`.
    The pair, though, names the save by its own id, so the lookup is needed to get from
    one to the other.

    The read is scoped to the caller: a save id that is not the caller's is not found, and
    the resolution is refused rather than reaching for somebody else's save.
    """
    saved = SavedEvent.objects.using(PERSONAL).filter(user_id=user_id, pk=saved_id).first()
    if saved is None:
        raise ConflictPairNotFoundError(details={"side_id": str(saved_id)})
    return saved.event_id


def _other_side(
    pair: ConflictPair, side_kind: str, side_id: UUID
) -> tuple[str | None, UUID | None]:
    """The side of the pair that is not the named one, or `(None, None)` if there is none.

    The pair stores its two sides sorted on `(kind, id)`, and it holds them by value — so
    there is no query to run and no join to make: which side is which is a comparison
    against the row.
    """
    if pair.left_kind == side_kind and pair.left_id == side_id:
        return pair.right_kind, pair.right_id
    if pair.right_kind == side_kind and pair.right_id == side_id:
        return pair.left_kind, pair.left_id
    return None, None


def _is_imported_personal_event(*, kind: str, event_id: UUID) -> bool:
    """Whether this side is a personal event that came from a connected calendar (D3).

    Only a personal event can be imported — a saved event is the user's own save of a
    public event — so the kind check comes first and the lookup is a single indexed read.

    A side that is gone counts as **not** imported: there is nothing left to delete, and
    the caller's delete would be a no-op either way.
    """
    if kind != ConflictPair.SideKind.PERSONAL_EVENT:
        return False
    event = PersonalEvent.objects.using(PERSONAL).filter(pk=event_id).first()
    return event is not None and event.source == PersonalEvent.Source.CALENDAR_IMPORT


__all__ = [
    "RESOLUTIONS_BY_KIND",
    "RESOLUTIONS_BY_KIND_SAVED",
    "ConflictAlreadyResolvedError",
    "ConflictPairNotFoundError",
    "IllegalResolutionError",
    "ImportedEventNotDeletableError",
    "Resolution",
    "SideNotInPairError",
    "resolve_conflict",
    "resolutions_for_pair",
    "resolutions_for_side",
]
