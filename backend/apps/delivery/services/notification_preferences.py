"""The user's Quiet Hours window and their own default Reminder Plan (FR-12, FR-20).

Two stored preferences, both columns on `NotificationPreference`, which `delivery` owns
(AD-16). The model docstring carries the ownership reasoning; this module carries the
commands.

**Reading creates.** `get_preference` returns a row for every user, creating it with the
defaults on first call. That is what lets the minting service read one row and branch on
nothing — the same property `digest_preferences` wanted when it chose to *write* the default
on skip rather than assume it at read time.

**The lock is advisory, and the reason is worth repeating.** A row lock can only lock a row
that exists, and the interesting case is precisely a user who has never had a preference: two
concurrent first-writers both find nothing to lock, both insert, and the loser gets a raw
`IntegrityError` from the unique constraint, which reaches the caller as a 500.
`pg_advisory_xact_lock` is transaction-scoped, so a crashed worker cannot leave a user wedged.

**Its own lock key, not `personalization`'s.** `digest_preferences` and `onboarding` share a
key because they write the *same row*. This writes a different table in a different app;
sharing their key would serialise unrelated writes for no benefit.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import blake2b
from uuid import UUID

from django.db import connections, transaction

from apps.delivery.models import SLOTS_MAX, NotificationPreference
from apps.delivery.services.audit import write_audit
from apps.delivery.services.slots import validate_slots
from domain.errors import InvalidQuietHoursWindowError
from domain.quiet_hours import QuietHours
from shared.actor import Actor
from shared.constants import (
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_REMINDER_PLAN,
)
from shared.db import PERSONAL

#: The advisory-lock key space for this table. Deliberately **not** `digest_preferences`'
#: `b"eventpulse24-onb"`: a different row, in a different app, with no shared invariant.
_LOCK_PERSON = b"eventpulse24-ntf"


@dataclass(frozen=True)
class NotificationSettings:
    """One user's notification preferences, as plain data.

    A frozen dataclass and never a model instance, matching `catalog_read.PublicEvent`: a
    caller that received the model could write it, and `delivery` is the only writer (AD-16).

    `quiet_hours` is already the `domain.quiet_hours.QuietHours` value, assembled here, so no
    caller reassembles a window from two columns and gets the pairing wrong.
    """

    user_id: UUID
    quiet_hours: QuietHours | None
    default_reminder_slots: tuple[str, ...]


def _user_lock_key(user_id: UUID) -> int:
    """The advisory-lock key for one user's preference row.

    Stable across processes: `blake2b`, never the per-process-salted `hash()`.
    """
    digest = blake2b(str(user_id).encode(), digest_size=8, person=_LOCK_PERSON).digest()
    return int.from_bytes(digest, "big", signed=True)


def _lock_user(user_id: UUID) -> None:
    """Serialise this user's preference writes. See the module docstring."""
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_user_lock_key(user_id)])


def _to_settings(row: NotificationPreference) -> NotificationSettings:
    window = None
    if row.quiet_hours_start is not None and row.quiet_hours_end is not None:
        window = QuietHours(start=row.quiet_hours_start, end=row.quiet_hours_end)
    return NotificationSettings(
        user_id=row.user_id,
        quiet_hours=window,
        default_reminder_slots=tuple(row.default_reminder_slots),
    )


def _get_or_create_row(user_id: UUID) -> NotificationPreference:
    """This user's row, created with the defaults if it does not exist yet.

    The caller holds the lock and an open `PERSONAL` transaction.
    """
    row = NotificationPreference.objects.using(PERSONAL).filter(user_id=user_id).first()
    if row is not None:
        return row
    return NotificationPreference.objects.using(PERSONAL).create(
        user_id=user_id,
        quiet_hours_start=DEFAULT_QUIET_HOURS_START,
        quiet_hours_end=DEFAULT_QUIET_HOURS_END,
        default_reminder_slots=[slot.value for slot in DEFAULT_REMINDER_PLAN],
    )


def get_preference(*, user_id: UUID) -> NotificationSettings:
    """This user's notification settings, creating the defaults on first read.

    A new user gets the **22:00-08:00** window and the `DEFAULT_REMINDER_PLAN` slots, so the
    first reminder they ever receive already respects their night.
    """
    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        return _to_settings(_get_or_create_row(user_id))


def set_quiet_hours(
    *,
    user_id: UUID,
    window: QuietHours | None,
    actor: Actor,
    now: datetime,
) -> NotificationSettings:
    """Set or clear this user's Quiet Hours window.

    `None` turns quiet hours off, and is the **only** way to express that. A window whose
    start equals its end is the same statement spelled differently, so it is refused rather
    than stored — otherwise "off" would have two representations and a reader would have to
    handle both. `domain.quiet_hours` still treats `start == end` as disabled, because a pure
    shift must stay total; the refusal belongs here, at the write.

    Raises:
        InvalidQuietHoursWindowError: the window's start equals its end.
    """
    if window is not None and window.disabled:
        raise InvalidQuietHoursWindowError(
            details={"quiet_hours_start": str(window.start), "quiet_hours_end": str(window.end)}
        )

    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        row = _get_or_create_row(user_id)
        row.quiet_hours_start = window.start if window else None
        row.quiet_hours_end = window.end if window else None
        row.save(
            using=PERSONAL,
            # `updated_at` is auto_now, and Django only writes it when update_fields names
            # it — otherwise the timestamp silently never advances. Same as saved_events.
            update_fields=["quiet_hours_start", "quiet_hours_end", "updated_at"],
        )
        write_audit(
            actor=actor,
            action="notification_preference.quiet_hours_set",
            target_type="notification_preference",
            target_id=row.id,
            details={
                "quiet_hours_start": str(window.start) if window else None,
                "quiet_hours_end": str(window.end) if window else None,
                "at": now.isoformat(),
            },
        )
        return _to_settings(row)


def set_default_reminder_slots(
    *,
    user_id: UUID,
    slots: Sequence[str],
    actor: Actor,
    now: datetime,
) -> NotificationSettings:
    """Set what a newly attached Reminder Plan starts with (FR-20).

    **This changes future attachments only.** Existing per-event plans are untouched: a user
    who already chose 5d for one event keeps it. The opposite is a plausible misreading that
    would silently rewrite choices the user made deliberately, so it has its own test.

    An empty sequence is valid and means "new saves get no reminders" — the same reading as a
    0-slot plan (FR-9: "0 slots = no reminders (still in feed)").

    Raises:
        TooManySlotsError: more than `SLOTS_MAX` slots.
        UnknownSlotError: a slot that is neither a `ReminderSlot` nor a custom slot id.
    """
    chosen = tuple(slots)
    validate_slots(chosen)

    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        row = _get_or_create_row(user_id)
        row.default_reminder_slots = list(chosen)
        row.save(using=PERSONAL, update_fields=["default_reminder_slots", "updated_at"])
        write_audit(
            actor=actor,
            action="notification_preference.default_slots_set",
            target_type="notification_preference",
            target_id=row.id,
            details={"slots": list(chosen), "at": now.isoformat()},
        )
        return _to_settings(row)


def default_slots_for(*, user_id: UUID) -> tuple[str, ...]:
    """The slots a new plan for this user should start with (FR-20).

    The user's own default when they have set one, and `shared.constants`'
    `DEFAULT_REMINDER_PLAN` when they have not. **The constant stays the fallback and is never
    duplicated into this app** (AD-16) — FR-20's default survives as the answer for a user who
    has never opened `/settings/reminders`.

    An explicitly empty default is honoured, not treated as "unset": a user who chose "no
    reminders by default" means it. That distinction is why this reads the row rather than
    testing the list for truthiness.
    """
    row = NotificationPreference.objects.using(PERSONAL).filter(user_id=user_id).first()
    if row is None:
        return tuple(slot.value for slot in DEFAULT_REMINDER_PLAN)
    return tuple(row.default_reminder_slots)


__all__ = [
    "SLOTS_MAX",
    "NotificationSettings",
    "default_slots_for",
    "get_preference",
    "set_default_reminder_slots",
    "set_quiet_hours",
]
