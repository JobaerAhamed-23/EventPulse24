"""Resolving a conflict (FR-58): the user's explicit choice on a conflict prompt.

FR-58's prompt has **exactly three buttons and no dismiss**. "There is no 'dismiss' resolution
— the user must make an explicit choice." So every prompt ends in a recorded resolution, and
this module is where that happens.

The three choices:

- **`keep_both`** — "Keep both — I'll manage." The pair closes as `resolved`, and the
  conflict indicator stays on both events permanently. No further prompting.
- **`edit_new`** — "Edit the new one." The resolution is recorded, and the caller opens the new
  event in edit mode; after the edit, detection re-runs.
- **`delete_new`** — "Delete the new one." The new event is removed, through
  `delete_personal_event` — one path to delete an event, one audit trail.

For a duplicate prompt, button 2 is relabelled "Update the existing one" and maps to
`update_existing`, which opens the *existing* event in edit mode.

**Every answered prompt records its resolution, whichever button was pressed.** The pair's
status is `resolved` in all three cases — including "delete the new one". The model's
`conflict_pair_status_ck` is what forces this: a `cleared_by_state_change` pair must carry a
NULL resolution, so a pair the user answered can never be a cleared one. `cleared_by_state_change`
is reserved for a pair that ended because a side went away *without* the user answering — an
unrelated delete, an unsave, or a propagation-driven close.

A closed pair is immutable (AD-21) and never re-prompted, so resolving one twice is refused
here rather than hitting the database's `guard_conflict_pair` trigger.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.personalization.models import ConflictPair
from apps.personalization.services.audit import write_audit
from apps.personalization.services.personal_events import delete_personal_event
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
    """The resolution is not one of the three this pair's kind offers (FR-58)."""

    code = "illegal_resolution"
    default_message = "That isn't one of the choices for this conflict."


#: Which resolutions each kind of conflict offers. FR-58's two prompts have different button
#: sets: a time conflict offers "Edit the new one", a duplicate offers "Update the existing
#: one". `keep_both` and `delete_new` are legal for both.
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


@dataclass(frozen=True)
class Resolution:
    """The outcome of resolving a conflict."""

    pair_id: UUID
    kind: str
    resolution: str
    status: str
    #: The side the prompt called "new", for `edit_new` and `delete_new`. The caller opens it
    #: in edit mode, or finds it already deleted.
    new_side_id: UUID | None = None
    new_side_kind: str | None = None
    #: For `update_existing`, the side the user should open instead.
    existing_side_id: UUID | None = None
    existing_side_kind: str | None = None


def _resolution_value(resolution: str) -> str:
    """The stored resolution, rejecting anything outside the four values."""
    try:
        return ConflictPair.Resolution(resolution).value
    except ValueError:
        raise IllegalResolutionError(details={"resolution": str(resolution)}) from None


def resolve_conflict(
    *,
    user_id: UUID,
    pair_id: UUID,
    resolution: str,
    new_side_kind: str,
    new_side_id: UUID,
    actor: Actor,
    now: datetime,
) -> Resolution:
    """Record the user's choice on a conflict prompt (FR-58).

    The resolution is recorded on the pair **before** the action it names, so the audit trail
    shows what the user chose even if the follow-up edit lands later. `delete_new` deletes the
    new event through `delete_personal_event` — one path to delete an event, one audit trail.

    The pair's status is `resolved` whatever the choice was: a pair the user answered carries
    their answer, and the model's `conflict_pair_status_ck` makes a cleared pair (a NULL
    resolution) the only other shape.

    The caller says which side is the "new" one, because the pair row itself is symmetric:
    it stores both sides sorted, so the prompt's asymmetry cannot live in the row.
    """
    value = _resolution_value(resolution)

    with transaction.atomic(using=PERSONAL):
        pair = ConflictPair.objects.using(PERSONAL).filter(user_id=user_id, pk=pair_id).first()
        if pair is None:
            raise ConflictPairNotFoundError(details={"pair_id": str(pair_id)})
        if pair.status != ConflictPair.Status.ACTIVE:
            raise ConflictAlreadyResolvedError(details={"pair_id": str(pair_id)})
        allowed = RESOLUTIONS_BY_KIND[pair.kind]
        if value not in allowed:
            raise IllegalResolutionError(details={"resolution": value, "kind": pair.kind})

        other_kind, other_id = _other_side(pair, new_side_kind, new_side_id)

        # The user's choice is recorded on the pair *first*, and it is recorded as a
        # `resolved` pair whatever the choice was — including "delete the new one" and "edit
        # the new one". The model's `conflict_pair_status_ck` is what forces this: a
        # `cleared_by_state_change` pair must carry a NULL resolution, so a pair the user
        # answered can never be a cleared one. `cleared_by_state_change` is for a pair that
        # ended because a side went away *without* the user answering it.
        pair.status = ConflictPair.Status.RESOLVED
        pair.resolution = value
        pair.resolved_at = now
        pair.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])

        if value == ConflictPair.Resolution.DELETE_NEW:
            # The action the button names. It goes through `delete_personal_event`, so there
            # is one path to delete an event and one audit trail for it.
            delete_personal_event(
                user_id=user_id,
                event_id=new_side_id,
                actor=actor,
                now=now,
            )

        write_audit(
            actor=actor,
            action="conflict.resolved",
            target_type="conflict_pair",
            target_id=pair.id,
            details={
                "resolution": value,
                "kind": pair.kind,
                "new_side_id": str(new_side_id),
                "deleted": value == ConflictPair.Resolution.DELETE_NEW,
            },
        )
        return Resolution(
            pair_id=pair.id,
            kind=pair.kind,
            resolution=value,
            status=ConflictPair.Status.RESOLVED,
            new_side_id=new_side_id,
            new_side_kind=new_side_kind,
            existing_side_id=other_id,
            existing_side_kind=other_kind,
        )


def _other_side(
    pair: ConflictPair, new_side_kind: str, new_side_id: UUID
) -> tuple[str | None, UUID | None]:
    """The side of the pair that is not the new one."""
    if pair.left_kind == new_side_kind and pair.left_id == new_side_id:
        return pair.right_kind, pair.right_id
    if pair.right_kind == new_side_kind and pair.right_id == new_side_id:
        return pair.left_kind, pair.left_id
    return None, None


__all__ = [
    "ConflictAlreadyResolvedError",
    "ConflictPairNotFoundError",
    "IllegalResolutionError",
    "RESOLUTIONS_BY_KIND",
    "Resolution",
    "resolve_conflict",
]
