"""The calendar sync service (AD-18, AD-7, FR-50, FR-58, FR-20).

A connected calendar is a **mirror of somebody else's agenda**. This module is what turns a
fetched feed into the user's `PERSONAL_EVENT` rows, and what decides which connection to
fetch next.

**The reconcile is a three-way diff (D1).** A feed is a snapshot, not a delta: it says "here
are my events", not "here is what changed". So every sync computes the difference between the
feed's entries and the connection's imported rows, keyed on `(calendar_connection_id,
source_uid)` — the unique constraint the model already carries. A new uid becomes a row, a
changed uid updates its row, a vanished uid is deleted, and an **identical** uid is left
alone. That last branch is what makes the poll idempotent in the sense that matters: a
rewrite-everything sync would bump `version` hourly for every event, and `version` feeds
AD-7's send key — so every reminder would be re-sent, every hour, forever.

**Every write goes through the shared command paths (D11).** The sync calls
`create_personal_event`, `update_personal_event` and `delete_personal_event` — the same
commands the user's own edits use. So an imported event gets the same conflict detection,
the same FR-20 reminder default, the same version bump and the same audit row. Writing
rows directly from here would give imports a *second* implementation of "create a personal
event", and the two would drift.

**The user's edit wins (D2).** An imported row carries a `user_modified` flag. When it is
False the feed owns the row and a difference is a real upstream change, so it is applied.
When it is True the user owns the row, and the feed's value is not applied — the user's
edit survives the feed disagreeing with it.

**A failed fetch writes nothing (D15).** When the *fetch* fails, no event row, no conflict
pair and no reminder plan is written — only the connection's own status and error fields.
A truncated feed must never delete half the user's imported events.

Design: .specs-fire/intents/onboarding-and-account/work-items/
calendar-sync-and-polling-design.md (decisions D1–D17).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.db.models import F, Q

from apps.personalization.models import CalendarConnection, PersonalEvent
from apps.personalization.services.audit import write_audit
from apps.personalization.services.calendar_connections import reveal_credential
from apps.personalization.services.personal_events import (
    create_personal_event,
    delete_personal_event,
    update_personal_event,
)
from domain.errors import CredentialDecryptionError
from ports.calendar import (
    CalendarEntry,
    CalendarFeed,
    CalendarPort,
    CalendarRefusedError,
    CalendarResult,
    CalendarRevokedError,
    CalendarTransientError,
)
from shared.actor import Actor
from shared.constants import (
    CALENDAR_CLAIM_TTL,
    CALENDAR_IMPORT_WINDOW,
    CALENDAR_POLL_INTERVAL,
    CALENDAR_SYNC_BATCH,
)
from shared.db import PERSONAL

logger = logging.getLogger(__name__)

#: The actor a polled sync acts as (D10). A poll at 3am has no user behind it, and putting
#: a user's id in an audit row for an action they did not take would be a lie. The label
#: matches `shared.actor.SYSTEM_LABEL`.
SYNC_ACTOR = Actor.system("calendar_sync")

#: The actor the dispatcher claims connections as (D8). Mirrors `ingestion`'s `SCHEDULER`.
SCHEDULER = Actor.system("calendar_scheduler")


class CalendarConnectionNotFoundError(Exception):
    """The connection does not exist, or is not the caller's.

    A plain exception rather than a `domain.errors` type: this is a service-level lookup
    failure for a background job, not a user-facing refusal.
    """


@dataclass(frozen=True)
class SyncCounts:
    """What one sync did, as counts (D10).

    Counts only — never a title, a uid, a location or a note. A count is an integer with no
    content in it; the values here go straight into the audit row and the log line.
    """

    created: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0

    def as_details(self) -> dict[str, int]:
        return {
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "unchanged": self.unchanged,
        }


@dataclass(frozen=True)
class SyncOutcome:
    """What a sync did, as plain data.

    `outcome` is "synced", "not_modified" (the provider answered 304 — nothing to do),
    "revoked" (the credential is no longer valid; the user must reconnect) or "failed"
    (a transient or refused fetch; the next poll is scheduled as usual).
    """

    connection_id: UUID
    outcome: str
    counts: SyncCounts = field(default_factory=SyncCounts)
    error_kind: str | None = None


@dataclass(frozen=True)
class _Entry:
    """A feed entry, with its identity already resolved.

    `uid` is the id the **adapter** produced (`domain.dedup.ics_item_id`), not the raw ICS
    UID: a recurring instance carries `uid#YYYYMMDDTHHMMSSZ`, and an override of a master's
    own instance carries the *same* id as that master. Re-deriving an id here would land
    the override beside the master it is supposed to replace (D1).
    """

    uid: str
    name: str
    start_utc: datetime
    end_utc: datetime | None
    start_time_tz: str
    location: str | None = None
    notes: str | None = None


def _to_entry(entry: CalendarEntry) -> _Entry:
    """The adapter's entry, in the shape the commands want."""
    return _Entry(
        uid=entry.uid,
        name=entry.title,
        start_utc=entry.starts_at,
        end_utc=entry.ends_at,
        start_time_tz=entry.tz,
    )


def _same_content(existing: PersonalEvent, entry: _Entry) -> bool:
    """Whether the row already says what the entry says.

    The comparison covers the fields that make an imported event what it is. The feed
    carries no location and no notes (`CalendarEntry` has neither), so those are not part
    of the comparison — a feed that has no location must not erase a location the user
    typed.
    """
    return (
        existing.name == entry.name
        and existing.start_utc == entry.start_utc
        and existing.end_utc == entry.end_utc
        and existing.start_time_tz == entry.start_time_tz
    )


def in_import_window(entry: CalendarEntry, *, now: datetime) -> bool:
    """Does `entry` overlap the import window `[now, now + CALENDAR_IMPORT_WINDOW]`?

    **Overlap, not "starts inside".** An event that began this morning and ends tonight is
    happening now; a rule that asked only where it *started* would drop it at the moment it
    matters most, and today's timeline would empty itself at lunchtime.

    The bounds are inclusive at both ends so a zero-length entry — which an all-day event
    can become once it is resolved to an instant — is not excluded by arithmetic alone.
    """
    return entry.ends_at >= now and entry.starts_at <= now + CALENDAR_IMPORT_WINDOW


def _entry_by_uid(entries: list[CalendarEntry]) -> dict[str, _Entry]:
    """The feed's entries, keyed by uid.

    A feed may repeat a uid (an override and the master it replaces arrive with the same
    id). The **last** one wins, because the adapter emits the override after the master —
    so the later entry is the one the provider means now.
    """
    return {entry.uid: _to_entry(entry) for entry in entries}


def _imported_rows(connection: CalendarConnection) -> dict[str, PersonalEvent]:
    """The connection's imported rows, keyed by uid.

    Scoped by `calendar_connection_id`, so a user-created event (which has no connection id
    at all) and another connection's events are both out of reach — the diff's scope *is*
    the rule (D2).
    """
    rows = (
        PersonalEvent.objects.using(PERSONAL)
        .filter(calendar_connection_id=connection.pk)
        .order_by("start_utc", "id")
    )
    return {row.source_uid: row for row in rows if row.source_uid}


def _fetch(
    *,
    connection: CalendarConnection,
    port: CalendarPort,
) -> CalendarResult:
    """Fetch the connection's feed through the port (AD-18).

    The credential is revealed here and nowhere else: it is wrapped in
    `ports.calendar.Credential`, whose `repr` and `str` are redacted, and it is handed
    straight to the port.

    ## The fetch is unconditional, and the import window is why

    The stored validators are deliberately **not** sent. Conditional fetching rests on an
    assumption — *"the feed has not changed, therefore neither has what we should store"* —
    and `CALENDAR_IMPORT_WINDOW` breaks it. What we import is a function of the feed **and
    of `now`**, so an unchanged feed still means a changed answer:

    - an event that has ended drops out of the window and should be deleted;
    - an event eight days out crosses into the window and should be imported.

    A 304 shows us neither. A calendar nobody edits for a fortnight — which is most
    calendars — would freeze its imported set on the day it last changed, and a meeting
    booked a month ahead would never arrive, because the feed carrying it never changes
    again. That failure is silent: the connection reads healthy and simply stops telling
    the truth.

    The cost of giving up the 304 is one full feed per poll: a few kilobytes an hour per
    connection (the first real local calendar measured 2,237 bytes). That is a small price
    for the window being correct, and it is the window — not bandwidth — that the product
    promised.

    `_store_validators` still records what the provider sent, so reinstating conditional
    fetching is a one-line change if the window ever goes away.
    """
    credential = reveal_credential(connection=connection)
    feed = CalendarFeed(url=credential)
    return port.fetch_entries(feed)


def _mark_failed(
    *,
    connection: CalendarConnection,
    error_kind: str,
    revoked: bool,
    now: datetime,
) -> None:
    """Record a failed poll on the connection, and schedule the next one (D6, D7).

    A revoked fetch sets the status to `needs_reconnect` and **keeps every imported
    event** — the provider revoked the *address*, not the *events*, and deleting a user's
    history over a 403 would be irreversible. A transient or refused fetch leaves the
    status alone and retries at the next due time (D7).

    The next poll is scheduled the same way in every case: `now + CALENDAR_POLL_INTERVAL`.
    A `needs_reconnect` connection is not polled again anyway — only an `active` connection
    is ever due — but the time is written so the row says what it means.
    """
    updates: dict[str, object] = {
        "last_error_kind": error_kind,
        "last_error_at": now,
        "next_poll_at": now + CALENDAR_POLL_INTERVAL,
    }
    if revoked:
        updates["status"] = CalendarConnection.Status.NEEDS_RECONNECT
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(**updates)


def _mark_synced(*, connection: CalendarConnection, now: datetime) -> None:
    """Record a successful poll: the time, the next due time, and no error (D7, D9)."""
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        last_polled_at=now,
        next_poll_at=now + CALENDAR_POLL_INTERVAL,
        last_error_kind=None,
        last_error_at=None,
    )


def _store_validators(*, connection: CalendarConnection, result: CalendarResult) -> None:
    """Store the provider's new cache validators, so the next fetch can be conditional.

    A validator the provider no longer sends is cleared rather than kept: a stale `ETag`
    would make the provider answer 304 for a feed it has changed, and the user's events
    would silently stop updating.
    """
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        etag=result.etag,
        last_modified=result.last_modified,
    )


def _apply_created(
    *,
    connection: CalendarConnection,
    entry: _Entry,
    now: datetime,
) -> None:
    """Create the imported event through the shared command path (D11).

    `create_personal_event` attaches the FR-20 default reminder plan (D5) and runs the
    conflict detection (D3). The import's detection skips the **duplicate** rule (D4): a
    user-created "Dinner" and a calendar "Dinner" are very often the same dinner, but the
    user typed theirs deliberately, so flagging them would be a prompt with no useful
    answer. The time rule still applies — two things at once is a clash either way.
    """
    create_personal_event(
        user_id=connection.user_id,
        name=entry.name,
        start_utc=entry.start_utc,
        end_utc=entry.end_utc,
        start_time_tz=entry.start_time_tz,
        source=PersonalEvent.Source.CALENDAR_IMPORT,
        calendar_connection_id=connection.pk,
        source_uid=entry.uid,
        # D4: an import is never a duplicate of a user-created event. The time rule still
        # applies, and the pair is recorded — the prompt is deferred to `/conflicts`.
        include_duplicate_conflicts=False,
        actor=SYNC_ACTOR,
        now=now,
    )


def _apply_updated(
    *,
    connection: CalendarConnection,
    existing: PersonalEvent,
    entry: _Entry,
    now: datetime,
) -> bool:
    """Apply a feed change to an imported row through the shared command path (D2, D11).

    Returns whether the change was applied. It is **not** applied when the user owns the
    row.

    **The ownership rule, and when it is decided.** The decision is made here, against
    committed state, under a row lock — not against the snapshot the diff started with.
    That matters: the snapshot was read before the diff began, so a user edit landing in
    the meantime would be invisible to it, and the feed's value would be written over the
    user's edit. Silently, and permanently, because the next poll would do it again.

    The lock is held across the write, so the check and the write are decided against the
    same committed state. A user's own request waits for the lock rather than racing it.

    `update_personal_event` takes a `user_modified` flag precisely because the import
    cannot use the user-editing default: applying the feed's value must not be mistaken
    for the user editing the row, or the next feed change would be ignored and the mirror
    would freeze after one update.

    The import passes **`None`** — "leave the ownership as it stands" — not `False`.
    The distinction is the whole point of D2: `False` would *reset* the flag, handing the
    row back to the feed, and a user's edit would then be overwritten on the next poll.
    The import is never entitled to decide who owns a row; it only knows what the feed
    says, and the feed does not say whose edit it is.

    The feed carries no location and no notes (`CalendarEntry` has neither), so the
    command keeps the row's existing ones — a feed that has no location must not erase a
    location the user typed.
    """
    with transaction.atomic(using=PERSONAL):
        row = (
            PersonalEvent.objects.using(PERSONAL).select_for_update().filter(pk=existing.pk).first()
        )
        if row is None:
            # The row is gone. There is nothing left to protect, and the delete that
            # follows is a no-op on a row that is already gone.
            return False
        if row.user_modified:
            # The user owns this row. The feed's difference is not applied (D2).
            return False
        update_personal_event(
            user_id=connection.user_id,
            event_id=row.pk,
            name=entry.name,
            start_utc=entry.start_utc,
            end_utc=entry.end_utc,
            start_time_tz=entry.start_time_tz,
            # D2: preserve the ownership. Never reset it.
            user_modified=None,
            # D4: the import path skips the duplicate rule, exactly as the create path does.
            include_duplicate_conflicts=False,
            actor=SYNC_ACTOR,
            now=now,
        )
    return True


def _apply_deleted(
    *,
    connection: CalendarConnection,
    existing: PersonalEvent,
    now: datetime,
) -> None:
    """Delete a vanished imported event through the shared command path (D11).

    The command closes the event's conflict pairs as `cleared_by_state_change` and writes
    the audit row. The reminder plan row is left behind — `delivery` owns `REMINDER_PLAN`
    and has no per-target delete — and the leftover row is inert.

    A user-*modified* row is still deleted when the entry vanishes from the feed: the
    provider removed the event, and the mirror's whole job is to mirror. The user's edit
    was to a row that no longer exists upstream.
    """
    delete_personal_event(
        user_id=connection.user_id,
        event_id=existing.pk,
        actor=SYNC_ACTOR,
        now=now,
    )


def sync_calendar(
    *,
    connection_id: UUID,
    port: CalendarPort,
    now: datetime,
) -> SyncOutcome:
    """Fetch one connection's feed and reconcile its imported events (D1–D17).

    **A failed fetch writes nothing (D15).** When the fetch fails, no event row, no
    conflict pair and no reminder plan is written — only the connection's own status and
    error fields, which are not part of the reconcile. A truncated feed must never delete
    half the user's imported events.

    The writes themselves go through `create_personal_event` / `update_personal_event` /
    `delete_personal_event` (D11), so an imported event is indistinguishable from a
    user-created one except for the `source` and the connection it names.

    The connection's row is **not** locked for the whole reconcile. The claim that keeps
    two ticks from syncing the same connection is the dispatcher's (`sync_claimed_at`), and
    holding a row lock across a network fetch would hold a database connection open for the
    length of the fetch.
    """
    connection = CalendarConnection.objects.using(PERSONAL).filter(pk=connection_id).first()
    if connection is None:
        raise CalendarConnectionNotFoundError(f"No calendar connection {connection_id}")

    try:
        result = _fetch(connection=connection, port=port)
    except CalendarRevokedError:
        # D6: the provider says the credential is no longer valid. The status changes; the
        # imported events stay.
        with transaction.atomic(using=PERSONAL):
            _mark_failed(
                connection=connection,
                error_kind="revoked",
                revoked=True,
                now=now,
            )
            write_audit(
                actor=SYNC_ACTOR,
                action="calendar.sync_failed",
                target_type="calendar_connection",
                target_id=connection.pk,
                details={"reason": "revoked", "at": now.isoformat()},
            )
        logger.info(
            "calendar sync revoked connection=%s provider=%s",
            connection.pk,
            connection.provider,
        )
        return SyncOutcome(connection_id=connection.pk, outcome="revoked", error_kind="revoked")
    except CalendarTransientError:
        return _record_failed(connection=connection, reason="transient", now=now)
    except CalendarRefusedError:
        # D6: a refusal is *our* decision about the address, not the provider's word about
        # the credential. It must never mark a connection revoked.
        return _record_failed(connection=connection, reason="refused", now=now)
    except CredentialDecryptionError:
        # The stored credential could not be read — a wrong key, or a key rotated under a
        # running process. That is a fault on our side, and the user cannot fix it by
        # pasting the address again, so it is recorded but never treated as a revocation.
        return _record_failed(connection=connection, reason="undecryptable", now=now)

    if result.not_modified:
        # A 304 is a success: the feed has not changed and the caller keeps what it has.
        #
        # **Defensive, not expected.** `_fetch` sends no validators, so a well-behaved
        # provider has nothing to answer 304 to. The branch stays because the port allows
        # the answer and because the safe response to "no entries" is to keep what we have:
        # reconciling against an empty feed would delete every imported event.
        with transaction.atomic(using=PERSONAL):
            _mark_synced(connection=connection, now=now)
            _store_validators(connection=connection, result=result)
        return SyncOutcome(connection_id=connection.pk, outcome="not_modified")

    counts = _reconcile(connection=connection, result=result, now=now)

    with transaction.atomic(using=PERSONAL):
        _mark_synced(connection=connection, now=now)
        _store_validators(connection=connection, result=result)
        write_audit(
            actor=SYNC_ACTOR,
            action="calendar.synced",
            target_type="calendar_connection",
            target_id=connection.pk,
            # Counts only. Never a title, a uid, a location, a note or a URL (AD-13).
            details={**counts.as_details(), "provider": connection.provider},
        )
    logger.info(
        "calendar sync connection=%s provider=%s created=%d updated=%d deleted=%d unchanged=%d",
        connection.pk,
        connection.provider,
        counts.created,
        counts.updated,
        counts.deleted,
        counts.unchanged,
    )
    return SyncOutcome(connection_id=connection.pk, outcome="synced", counts=counts)


def _record_failed(*, connection: CalendarConnection, reason: str, now: datetime) -> SyncOutcome:
    """Record a failed poll that does not revoke the connection (D6, D7, D15).

    Nothing is reconciled: no event row, no conflict pair, no reminder plan is written.
    """
    with transaction.atomic(using=PERSONAL):
        _mark_failed(connection=connection, error_kind=reason, revoked=False, now=now)
        write_audit(
            actor=SYNC_ACTOR,
            action="calendar.sync_failed",
            target_type="calendar_connection",
            target_id=connection.pk,
            details={"reason": reason, "at": now.isoformat()},
        )
    logger.info(
        "calendar sync failed connection=%s provider=%s reason=%s",
        connection.pk,
        connection.provider,
        reason,
    )
    return SyncOutcome(connection_id=connection.pk, outcome="failed", error_kind=reason)


def _reconcile(
    *,
    connection: CalendarConnection,
    result: CalendarResult,
    now: datetime,
) -> SyncCounts:
    """The three-way diff, applied through the shared command paths (D1, D11).

    | In the feed | In the database | Action |
    |---|---|---|
    | yes | no | create |
    | yes | yes, identical | nothing |
    | yes | yes, different | update (unless the user owns the row — D2) |
    | no | yes | delete |

    Each write is its own transaction, so a single failing event does not roll back the
    whole sync — the sync is the *reconcile*'s all-or-nothing property (D15), and a failed
    *fetch* is what D15 is about. The commands are individually atomic, which is their own
    guarantee.

    One transaction for the whole diff would hold a lock on every touched row for the
    length of the diff and would roll back a correct update because an unrelated event
    failed to write.
    """
    # **The window is applied here, to the feed, and that is what makes it self-cleaning.**
    # An entry outside it is simply not in the feed as far as the diff is concerned, so a
    # row that has aged out takes the ordinary "in the database, not in the feed" branch and
    # is deleted. No separate pruning pass, and no second rule about which rows may be
    # removed — there is one definition of "what this calendar currently means".
    entries = _entry_by_uid([entry for entry in result.entries if in_import_window(entry, now=now)])
    existing_rows = _imported_rows(connection)

    created = updated = deleted = unchanged = 0

    for uid, entry in entries.items():
        row = existing_rows.get(uid)
        if row is None:
            _apply_created(connection=connection, entry=entry, now=now)
            created += 1
            continue
        if _same_content(row, entry):
            # The "identical → nothing" branch. Bumping the version here would re-key
            # AD-7's send key and re-send every reminder, every hour, forever (D1).
            unchanged += 1
            continue
        # D2: the ownership decision is made against **committed** state, under a row
        # lock, and in the same transaction as the write — not against the snapshot this
        # loop started with. The snapshot was read before the diff began, so a user edit
        # that landed in between would be invisible to it, and the feed's value would be
        # written over the user's edit, silently and permanently.
        if _apply_updated(connection=connection, existing=row, entry=entry, now=now):
            updated += 1
        else:
            # The user owns this row. The feed's difference is not applied, and the row is
            # not counted as updated — nothing changed (D2).
            unchanged += 1

    for uid, row in existing_rows.items():
        if uid in entries:
            continue
        _apply_deleted(connection=connection, existing=row, now=now)
        deleted += 1

    return SyncCounts(created=created, updated=updated, deleted=deleted, unchanged=unchanged)


def claim_due_connections(
    *,
    now: datetime,
    limit: int = CALENDAR_SYNC_BATCH,
) -> list[UUID]:
    """Claim up to `limit` due connections, least recently polled first; returns their ids (D8).

    **Due** means: `active`, and (`next_poll_at` is null, or `next_poll_at <= now`). A
    `needs_reconnect` connection is never due — the user must paste a new address first
    (D6) — and a `disconnected` one has no credential to fetch with.

    The claim is taken with `FOR UPDATE SKIP LOCKED`, exactly as `claim_due_sources` does,
    so two overlapping ticks never claim the same connection: the second tick's `SKIP
    LOCKED` skips the row the first one is holding. A claim older than
    `CALENDAR_CLAIM_TTL` is a lost job (a worker died) and the connection becomes
    claimable again.
    """
    with transaction.atomic(using=PERSONAL):
        ids = list(
            CalendarConnection.objects.using(PERSONAL)
            .select_for_update(skip_locked=True)
            .filter(status=CalendarConnection.Status.ACTIVE)
            .filter(
                Q(sync_claimed_at__isnull=True) | Q(sync_claimed_at__lte=now - CALENDAR_CLAIM_TTL)
            )
            .filter(Q(next_poll_at__isnull=True) | Q(next_poll_at__lte=now))
            .order_by(F("last_polled_at").asc(nulls_first=True), "id")
            .values_list("id", flat=True)[:limit]
        )
        CalendarConnection.objects.using(PERSONAL).filter(pk__in=ids).update(sync_claimed_at=now)
        for connection_id in ids:
            write_audit(
                actor=SCHEDULER,
                action="claim_calendar_sync",
                target_type="calendar_connection",
                target_id=connection_id,
            )
    return ids


def release_claim(connection_id: UUID) -> None:
    """End a claim when its job ends, however it ended.

    Not audited: the sync's own audit row (or the job's log line) closes the claim. This
    mirrors `ingestion`'s `release_claim`.
    """
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection_id).update(sync_claimed_at=None)


def record_unexpected_failure(*, connection_id: UUID, error_kind: str, now: datetime) -> None:
    """Record a poll that failed in a way the sync does not handle (D7).

    **Why this exists.** `sync_calendar` handles four failure modes — revoked, transient,
    refused, undecryptable — and each of them writes the next poll time. An error the sync
    does *not* handle — a malformed feed entry, a constraint violation, a dropped database
    connection — skips all of that: the poll time is left where it was, in the past.

    The worker then releases the claim, and the connection is due again on the very next
    60-second tick. And on the tick after that. Forever, because nothing caps it: the
    calendar would be fetched 1,440 times a day against the user's provider, every fetch
    carrying their secret address, each one failing the same way.

    So the unexpected failure is recorded the same way a transient one is: the next poll
    is scheduled one interval out, so the connection is retried **at the poll cadence**
    rather than at the tick cadence, and the error is visible on the row instead of
    vanishing into a log line.

    The status is left alone. An unexpected error is a fault on our side, and it must never
    ask the user to reconnect a calendar that works (D6).
    """
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection_id).update(
        last_error_kind=error_kind,
        last_error_at=now,
        next_poll_at=now + CALENDAR_POLL_INTERVAL,
    )


__all__ = [
    "SCHEDULER",
    "SYNC_ACTOR",
    "CalendarConnectionNotFoundError",
    "SyncCounts",
    "SyncOutcome",
    "claim_due_connections",
    "record_unexpected_failure",
    "release_claim",
    "sync_calendar",
]
