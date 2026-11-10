"""FR-54's state-change notice: one calm correction, raised once, capped at one a day.

`delivery` owns `STATE_CHANGE_NOTICE` (AD-16). AD-17's propagation calls `raise_state_notice`
once per affected user, inside that user's own `personal` transaction.

**The notice is the record and the email is one of its two deliveries.** The other is the
screen — the dismissible digest strip and the Detail banner — and both read this row, so the
two surfaces cannot drift. See `StateChangeNotice`'s own docstring for why this is not just
a `SCHEDULED_SEND`.

**Three rules live here, and FR-54 states them as if they were one.**

1. **Never repeats** — one notice per `(user, state change)`. Held by the unique constraint,
   not by this module remembering to look. This is the repeat FR-54 forbids: a propagation
   retried after a partial run.
2. **At most one per event per day** — a *different* rule, about different changes rather
   than the same one. Enforced here, against `(user, event, local date)`, and resolved with
   `domain.lifecycle.PRECEDENCE`.
3. **Muted events are silent** — except terminally; see below.

**Why the cap cannot be the send key.** AD-7 fixes the key as
`user_id · state_notice · state_change_id`. Re-keying it on `(event, local_date)` looks
tempting and loses data: a cancellation at 14:00 would collide with a sold-out minted at
09:00 and be dropped as a duplicate — silently discarding the one message FR-54 most
requires. The key stays AD-7's, and the cap is a decision taken before minting.

**And the cap is the common case, not an edge.** `ingestion.event_writes` appends **one
`EVENT_STATE_CHANGE` per kind** within a single poll, versions `v+1..v+k`, ordered by
`PRECEDENCE`. A source update that moves an event's time *and* marks it sold out already
produces two notices seconds apart. Without the cap, FR-54's "no notification spam" fails on
the first ordinary multi-field change.

**The terminal exception.** A `cancelled` or `superseded` change is raised even when the cap
or a mute would suppress it. Every other notice is a convenience — a venue moved, tickets
ran out. A cancellation is the one where silence costs the user the evening, and FR-55 has
*already* removed the event from their digest, so there is no second channel that would have
told them. A mute means "stop telling me about tweaks to this event"; reading it as "do not
tell me it is off" turns a preference into a trap.

That exception is also what bounds the cap honestly: **at most two emails per event per
day**, because nothing outranks a terminal change.
"""

from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction

from apps.delivery.models import StateChangeNotice
from apps.delivery.services.audit import write_audit
from apps.delivery.services.mutes import is_muted
from apps.delivery.services.scheduled_sends import (
    cancel_state_notice_sends,
    mint_state_notice,
    zone_for,
)
from domain.lifecycle import PRECEDENCE, ChangeKind
from domain.notices import is_notified
from domain.timezones import to_instant
from shared.actor import Actor
from shared.db import PERSONAL

#: The kinds that override both the daily cap and a mute. See the module docstring.
#:
#: Deliberately **not** "anything that cancels sends": `postponed` also stops a reminder
#: going out, and a postponement is exactly the calm, deferrable news the cap exists for.
#: These two are the kinds after which there is no event left to tell the user about.
TERMINAL_KINDS = frozenset({ChangeKind.CANCELLED, ChangeKind.SUPERSEDED})

#: Rank by importance, most important first (`domain.lifecycle.PRECEDENCE`). Reused, never
#: re-declared: `classify_change` already orders a poll's changes by it, and a second
#: ordering here would be free to disagree with the one that does the deciding.
_RANK = {kind: position for position, kind in enumerate(PRECEDENCE)}


def _as_kind(change_kind: str) -> ChangeKind | None:
    """The `ChangeKind`, or None for a value this module has not been taught.

    None rather than an exception. A kind `domain.lifecycle` gained without this module
    being updated should degrade to "ordinary, outranks nothing" — not crash propagation for
    every user of one event.
    """
    try:
        return ChangeKind(change_kind)
    except ValueError:
        return None


def _rank(change_kind: str) -> int:
    """How important a change is. Lower is more important; an unknown kind sorts last."""
    kind = _as_kind(change_kind)
    return len(PRECEDENCE) if kind is None else _RANK[kind]


def _local_date(instant: datetime, zone: str) -> date:
    """The user's local date at `instant`.

    The same conversion `shift_to_sendable` makes, for the same reason: "today" is a
    different day for a user in Auckland and one in Los Angeles at the same moment, and the
    cap is about the user's day.
    """
    return to_instant(instant).astimezone(ZoneInfo(zone)).date()


def raise_state_notice(
    *,
    user_id: UUID,
    event_id: UUID,
    state_change_id: UUID,
    change_kind: str,
    event_version: int,
    event_start_utc: datetime | None,
    actor: Actor,
    now: datetime,
    before: dict | None = None,
    after: dict | None = None,
) -> bool:
    """Raise one FR-54 notice for one user and one catalog state change. True if it did.

    **Called by `worker.propagation`**, the AD-17 consumer: the notice is raised last, after
    the snapshot and the sends have both been made true, because it describes a state both
    halves have made real.

    Returns `False` for every suppression — already raised, muted, capped, an older
    version, or a change with nothing worth saying — so the caller can count what it
    actually did without inferring it.

    The order of the guards is load-bearing:

    0. **Whether there is a notice at all.** A `detail_changed` that did not move the
       venue is not notified — see below. **This comes first**, because a notice that
       should never have been raised must not be able to cancel a newer one on its way
       to being refused, and must not consume the day's cap slot.
    1. **The AD-17 version gate first.** An out-of-order change must not be able to cancel a
       newer notice on its way to being refused. This also absorbs the retry case: a
       re-delivered change carries the version its notice already stored, so it is refused
       here rather than needing a guard of its own.
    2. **Then the mute**, which the user asked for.
    3. **Then the cap**, which is the only guard that can *replace* rather than refuse.

    "Never repeats" itself is the database's, not this function's — see the comment on the
    insert. A check above it would look like a retry guard and prevent nothing, because two
    concurrent propagations of one change both pass it.

    Runs in one `personal` transaction. AD-3 forbids one spanning `catalog`, so
    `event_start_utc` is passed in by value: the caller has already read the event. The
    change's `before`/`after` come the same way — **by value, from the caller's read**,
    so no transaction here spans the two schemas.

    **The `detail_changed` rule, and why it is here rather than in the renderer.**
    `domain.lifecycle.classify_change` files a venue move under `detail_changed`, because
    `venue_fingerprint` is one of its detail facts — so the PRD's "moved to [new location]"
    subject has no kind of its own. **Silencing `detail_changed` wholesale would silence
    the PRD's own third subject.** So the rule is about the *change*, not the kind: a
    `detail_changed` whose venue fingerprints differ is notified; one that fixed a title, a
    description, a URL or a timezone label is not.

    **And a notice that was never raised is better than one that says nothing.** FR-53: not
    every change deserves a notification — "would be engagement-trap". A title edit has no
    reminder consequence (`LIFECYCLE_SEND_BEHAVIOUR` maps `detail_changed` to `KEEP`), so
    FR-54's body requirement — "what changed and what it means for the user's reminders" —
    has no answer for it. **Silencing at the source is the only place this can be decided
    once**: a notice the renderer refuses to render would still have been raised, would
    still have consumed the day's cap slot, and would still be sitting in the user's
    in-app strip saying nothing.
    """
    kind_rank = _rank(change_kind)
    terminal = _as_kind(change_kind) in TERMINAL_KINDS

    # 0. Is there a notice to raise at all? See the docstring.
    if not is_notified(change_kind, before=before or {}, after=after or {}):
        return False

    try:
        raised = _raise(
            user_id=user_id,
            event_id=event_id,
            state_change_id=state_change_id,
            change_kind=change_kind,
            event_version=event_version,
            kind_rank=kind_rank,
            terminal=terminal,
            actor=actor,
            now=now,
        )
    except IntegrityError:
        # **The unique constraint is what makes "never repeats" true, and it has to be.**
        # A `SELECT … .exists()` above the insert would read like a retry guard and prevent
        # nothing: two workers propagating the same state change for the same user both
        # pass it, because neither has committed yet. Only the constraint is atomic.
        #
        # **Caught outside the transaction, deliberately.** A savepoint around the insert
        # alone would let the block commit — leaving the day's earlier notices deleted and
        # their emails cancelled by the cap, for a notice that was never raised. The whole
        # block rolls back together or not at all.
        return False
    if not raised:
        return False

    # Minting opens its own transaction, and that is deliberate: it reads the user's
    # preferences and zone, which are reads this transaction should not be held open for.
    # A notice whose email fails to mint is still a notice — the in-app surfaces have it —
    # so the two are not all-or-nothing.
    mint_state_notice(
        user_id=user_id,
        event_id=event_id,
        state_change_id=state_change_id,
        event_start_utc=event_start_utc,
        actor=actor,
        now=now,
    )
    return True


def _raise(
    *,
    user_id: UUID,
    event_id: UUID,
    state_change_id: UUID,
    change_kind: str,
    event_version: int,
    kind_rank: int,
    terminal: bool,
    actor: Actor,
    now: datetime,
) -> bool:
    """The guards and the write, in one `personal` transaction. True if a notice was made.

    Separate from `raise_state_notice` only so the `IntegrityError` can be caught *outside*
    the transaction — see the comment there.
    """
    with transaction.atomic(using=PERSONAL):
        # 1. AD-17's gate. A notice already raised for this event at a version at or above
        #    this one means this change is older or a duplicate; it changes nothing.
        newer_exists = (
            StateChangeNotice.objects.using(PERSONAL)
            .filter(user_id=user_id, event_id=event_id, event_version__gte=event_version)
            .exists()
        )
        if newer_exists:
            return False

        # 2. The user asked for silence — unless there is nothing left to be silent about.
        if not terminal and is_muted(user_id=user_id, event_id=event_id):
            return False

        local_date = _local_date(now, zone_for(user_id))

        # 3. The cap. One notice per event per day, resolved by importance.
        if not terminal:
            existing = (
                StateChangeNotice.objects.using(PERSONAL)
                .select_for_update()
                .filter(user_id=user_id, event_id=event_id, local_date=local_date)
                .order_by("created_at")
            )
            for notice in existing:
                if _rank(notice.change_kind) <= kind_rank:
                    # Something at least as important already went out today. This is the
                    # spam FR-54 is guarding against.
                    return False
            # Everything today is less important than this change, so it is replaced
            # rather than added to: FR-54 asks for *a single, calm* notification, not a
            # stack of them. The superseded notices' sends are cancelled; their keys stay
            # spent, which AD-7 names as the intended pattern.
            _supersede(notices=list(existing), actor=actor, now=now)

        # No guard above this insert: the unique constraint is the guarantee, and
        # `raise_state_notice` handles its refusal. See the comment there.
        StateChangeNotice.objects.using(PERSONAL).create(
            user_id=user_id,
            event_id=event_id,
            state_change_id=state_change_id,
            change_kind=change_kind,
            event_version=event_version,
            local_date=local_date,
        )
        write_audit(
            actor=actor,
            action="state_change_notice.raised",
            target_type="event",
            target_id=event_id,
            details={
                "change_kind": change_kind,
                "event_version": event_version,
                "state_change_id": str(state_change_id),
                "local_date": local_date.isoformat(),
                "terminal": terminal,
            },
        )
        return True


def _supersede(*, notices: list[StateChangeNotice], actor: Actor, now: datetime) -> None:
    """Retire today's less important notices and cancel their pending emails."""
    if not notices:
        return
    change_ids = [notice.state_change_id for notice in notices]
    # **The schedule is not written here.** This module owns `STATE_CHANGE_NOTICE` and
    # decides which notices lose to a more important change; AD-7 gives `scheduled_sends`
    # sole ownership of what is due, so the cancellation goes through its published command.
    # Two writers would be two rule sets — one that mints and one that cancels.
    cancel_state_notice_sends(
        state_change_ids=change_ids,
        user_id=notices[0].user_id,
        actor=actor,
        now=now,
    )
    StateChangeNotice.objects.using(PERSONAL).filter(
        pk__in=[notice.pk for notice in notices]
    ).delete()
    write_audit(
        actor=actor,
        action="state_change_notice.superseded",
        target_type="event",
        target_id=notices[0].event_id,
        details={"count": len(notices), "state_change_ids": [str(i) for i in change_ids]},
    )


def list_undismissed_notices(*, user_id: UUID, limit: int) -> list[StateChangeNotice]:
    """This user's open notices, newest first — the digest strip's read.

    **Scoped by `dismissed_at`, not by `seen_at`.** The strip is a queue, and closing an
    item should empty it; being *shown* something is not the same as acting on it.

    **`limit` is required, and it is not a default.** A default would leave the unbounded
    read reachable, and "somebody forgot to pass a limit" is exactly the failure the bound
    exists to prevent. The strip shows a few notices, not a history — so the bound lives
    here, where the query is, rather than only at the surface that happens to call it.

    **The bound is applied by the database**, through the slice on the ordered queryset,
    so a busy day costs one query and one index range — not a fetch of every open notice
    to throw most of them away.

    **The order has a tiebreaker, and it is the same one the banner uses.**
    `order_by("-created_at", "-id")` — see `services.notice_state`, which owns the
    "newest notice" rule. `created_at` is `auto_now_add` with microsecond resolution, and
    a single ingestion poll can raise several notices at once, so two rows can share a
    `created_at`. Without the tiebreaker the strip and the banner would each be free to
    pick a different row for the same tie — two rules for one question.
    """
    return list(
        StateChangeNotice.objects.using(PERSONAL)
        .filter(user_id=user_id, dismissed_at__isnull=True)
        .order_by("-created_at", "-id")[:limit]
    )


def mark_seen(*, user_id: UUID, notice_ids: list[UUID], now: datetime) -> int:
    """Record that these notices were put in front of the user. Returns how many moved.

    **Only the first time.** `seen_at` is when it was first shown, not most recently — a
    column that moved on every render would answer "when did we last draw this" rather than
    "has this user had their chance to read it".

    No audit row: being shown something is not a mutation the user made, and AD-5's log is
    for commands. The column is the record.
    """
    if not notice_ids:
        return 0
    return (
        StateChangeNotice.objects.using(PERSONAL)
        .filter(user_id=user_id, pk__in=notice_ids, seen_at__isnull=True)
        .update(seen_at=now, updated_at=now)
    )


def dismiss_notice(*, user_id: UUID, notice_id: UUID, actor: Actor, now: datetime) -> bool:
    """Close one notice's strip entry. True if this call closed it.

    Idempotent: dismissing an already-dismissed notice changes nothing and says so, rather
    than reporting a change the screen would redraw.
    """
    with transaction.atomic(using=PERSONAL):
        changed = (
            StateChangeNotice.objects.using(PERSONAL)
            .filter(user_id=user_id, pk=notice_id, dismissed_at__isnull=True)
            .update(dismissed_at=now, seen_at=now, updated_at=now)
        )
        if changed:
            write_audit(
                actor=actor,
                action="state_change_notice.dismissed",
                target_type="state_change_notice",
                target_id=notice_id,
                details={"at": now.isoformat()},
            )
    return bool(changed)


def notice_belongs_to_user(*, user_id: UUID, notice_id: UUID) -> bool:
    """Whether a notice with this id exists and is the caller's — dismissed or not.

    **The answer the dismiss endpoint needs, and the only safe one.** `dismiss_notice`
    returns whether *this call* closed the notice, and it cannot say why it did not:
    "not yours", "there is no such notice" and "already dismissed" all come back as
    `False`. The endpoint has to tell the third from the first two — an already-dismissed
    notice is a success, not an error — while the first two must be the *same* answer,
    because a 403 for one and a 404 for the other would turn the endpoint into an
    existence oracle over notice ids (no existence leak).

    **So it asks about the caller's own notices, including the dismissed ones.** A
    dismissed notice still belongs to the user who dismissed it — which is exactly why
    this can answer "it was already closed" without answering "it exists but is not
    yours".
    """
    return StateChangeNotice.objects.using(PERSONAL).filter(user_id=user_id, pk=notice_id).exists()


__all__ = [
    "TERMINAL_KINDS",
    "dismiss_notice",
    "list_undismissed_notices",
    "mark_seen",
    "notice_belongs_to_user",
    "raise_state_notice",
]
