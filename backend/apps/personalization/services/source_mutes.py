"""The per-user source mute: how one person asked to see (or not see) one source.

`personalization` owns `SOURCE_MUTE` (AD-16). The source itself belongs to `ingestion` and
is held here **by value** — `source_id` is a UUID with no FK — because AD-3 forbids a
relation across the schema wall.

**There are two states, and `default` is the absence of a row.** The mockup's control has
three positions, but only two are stored. A third stored state saying "default" would be a
row that says nothing, and it would turn "Restore all defaults" from a bulk delete into a
three-way update. So setting `default` **deletes** the row, and `default` is what a source
with no row means.

**`mute` and `show_less` are different promises, and the two ends of the pipeline treat
them differently.** `mute` means "do not show me this source's events" — the events are
*absent* from the candidate set. `show_less` means "show me fewer" — the events are
*present* and score lower. A "show less" that hid events would be indistinguishable from a
mute on the wire, and would be a lie to the user who asked for fewer, not none.

**No existence check on the source.** The id names a row in `catalog`, which this module
may not read in a write transaction (AD-3), and a mute for a source that has since been
removed is harmless: it excludes nothing and is purged with the user's data. The same
reasoning `delivery.services.mutes` gives for not checking that the event exists.

**Every write is audited (AD-5), inside the personal transaction.** `write_audit` raises if
it is called outside one.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.personalization.models import SourceMute
from apps.personalization.services.audit import write_audit
from shared.actor import Actor
from shared.db import PERSONAL

#: The three states the screen's control offers. `default` is the absence of a row.
STATE_DEFAULT = "default"
STATE_SHOW_LESS = SourceMute.State.SHOW_LESS
STATE_MUTE = SourceMute.State.MUTE

#: Every state a caller may ask for, in the screen's order.
SOURCE_MUTE_STATES: tuple[str, ...] = (STATE_MUTE, STATE_SHOW_LESS, STATE_DEFAULT)


@dataclass(frozen=True)
class SourceMuteResult:
    """The outcome of setting one source's mute state.

    `changed` says whether this call did anything. The API needs it: setting the state a
    source is already in is a success, not an error, but a response that claimed a change
    when none happened would make the screen redraw something that did not move.
    """

    source_id: UUID
    state: str
    changed: bool


@dataclass(frozen=True)
class SourceVisibility:
    """What one user has asked about the sources, as the composition path reads it.

    **The two sets are read together, in one query.** The composition path asks both
    questions on every read, and a user with a mute for one source and a show-less for
    another is the normal case — so two queries would be two queries for one answer.
    """

    #: Sources whose events must not be shown at all.
    muted: frozenset[UUID]
    #: Sources whose events should be shown, but ordered lower.
    show_less: frozenset[UUID]


def set_source_mute(
    *,
    user_id: UUID,
    source_id: UUID,
    state: str,
    actor: Actor,
    now: datetime,
) -> SourceMuteResult:
    """Set one source's mute state for one user. Idempotent.

    **`default` deletes the row.** The row's absence *is* the default state, so setting
    `default` is not a write of "default" — it is the removal of the row that said
    something else.

    **The row is locked before it is read.** The state is read to decide whether anything
    moved, and then written — and without the lock two concurrent requests could both
    read the old state, both conclude they changed it, and both write an audit row
    claiming a change while only the second write survives. `select_for_update` takes the
    row's lock first, so the second request waits, reads the first request's state, and
    correctly reports that nothing moved. (The *create* path needs no such care: the
    unique constraint on `(user_id, source_id)` is what `get_or_create` leans on.)
    """
    if state not in SOURCE_MUTE_STATES:
        raise ValueError(f"unknown source mute state: {state!r}")

    if state == STATE_DEFAULT:
        return _restore_one(user_id=user_id, source_id=source_id, actor=actor, now=now)

    with transaction.atomic(using=PERSONAL):
        row, created = SourceMute.objects.using(PERSONAL).get_or_create(
            user_id=user_id,
            source_id=source_id,
            defaults={"state": state},
        )
        changed = created
        if not created:
            # **Re-read under the row's lock.** `get_or_create` fetched the row before
            # the lock was taken, so its `state` may already be stale.
            row = (
                SourceMute.objects.using(PERSONAL)
                .select_for_update()
                .get(user_id=user_id, source_id=source_id)
            )
            if row.state != state:
                row.state = state
                row.save(using=PERSONAL, update_fields=["state"])
                changed = True
        if changed:
            write_audit(
                actor=actor,
                action=f"source_mute.{state}",
                target_type="source",
                target_id=source_id,
                details={"at": now.isoformat()},
            )
    return SourceMuteResult(source_id=source_id, state=state, changed=changed)


def _restore_one(
    *,
    user_id: UUID,
    source_id: UUID,
    actor: Actor,
    now: datetime,
) -> SourceMuteResult:
    """Remove one source's mute row, restoring it to the default."""
    with transaction.atomic(using=PERSONAL):
        deleted, _ = (
            SourceMute.objects.using(PERSONAL).filter(user_id=user_id, source_id=source_id).delete()
        )
        if deleted:
            write_audit(
                actor=actor,
                action="source_mute.default",
                target_type="source",
                target_id=source_id,
                details={"at": now.isoformat()},
            )
    return SourceMuteResult(source_id=source_id, state=STATE_DEFAULT, changed=bool(deleted))


def restore_source_defaults(*, user_id: UUID, actor: Actor, now: datetime) -> int:
    """Clear every custom mute for one user. Idempotent.

    **This is the bulk reset behind "Restore all defaults".** It removes every row for the
    user — both the mutes and the show-less preferences — and returns how many it removed.
    Nothing else is touched: the sources themselves are the catalog's, and another user's
    preferences are theirs.

    **The confirmation is the client's job** (§10.4's bulk-action safeguard). The endpoint
    behind the button is a single idempotent delete, and the screen asks before it calls
    it. The safeguard is that the destructive action is confirmed *before it completes*, and
    a confirmation the server owns would have to be a state machine to survive a refresh.
    """
    with transaction.atomic(using=PERSONAL):
        deleted, _ = SourceMute.objects.using(PERSONAL).filter(user_id=user_id).delete()
        if deleted:
            write_audit(
                actor=actor,
                action="source_mute.restore_defaults",
                target_type="user",
                target_id=user_id,
                details={"at": now.isoformat(), "removed": deleted},
            )
    return deleted


def read_source_states(*, user_id: UUID) -> dict[UUID, str]:
    """This user's mute state for each source that has one.

    The settings screen's read needs the state per source, and it reads them all at once —
    a screen that rendered a mute control per row must not cost a query per row.

    **This is the one query.** The composition path needs the same facts, split into two
    sets, and it reads them from here rather than running a second, near-identical query:
    two reads of one table that differ only in how they fold the rows is two places to
    change when the states change.
    """
    return {
        source_id: state
        for source_id, state in SourceMute.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .values_list("source_id", "state")
    }


def read_source_visibility(*, user_id: UUID) -> SourceVisibility:
    """What this user has asked about the sources, in one query.

    **This is the read the composition path uses.** It is called on every digest composition
    and every Browse page, so it is one query — not one per state, and not one per source.

    **It reads the one query.** `read_source_states` is the single place that knows the
    table's shape; this folds that answer into the two sets the composition path asks
    about. A source whose state is neither `mute` nor `show_less` cannot exist — the row's
    absence *is* `default`, and only the two non-default states are ever written — but a
    state this function does not recognise is simply not in either set, so an unknown
    value would exclude nothing rather than exclude everything.
    """
    states = read_source_states(user_id=user_id)
    return SourceVisibility(
        muted=frozenset(source_id for source_id, state in states.items() if state == STATE_MUTE),
        show_less=frozenset(
            source_id for source_id, state in states.items() if state == STATE_SHOW_LESS
        ),
    )


__all__ = [
    "SOURCE_MUTE_STATES",
    "STATE_DEFAULT",
    "STATE_MUTE",
    "STATE_SHOW_LESS",
    "SourceMuteResult",
    "SourceVisibility",
    "read_source_states",
    "read_source_visibility",
    "restore_source_defaults",
    "set_source_mute",
]
