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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import blake2b
from uuid import UUID

from django.db import connections, transaction

from apps.delivery.models import SLOTS_MAX, NotificationPreference, QuietHoursOverride
from apps.delivery.services.audit import write_audit
from apps.delivery.services.slots import validate_slots
from apps.identity.services import is_pro
from domain.errors import InvalidQuietHoursWindowError
from domain.quiet_hours import DAYS_IN_WEEK, QuietHours, WeeklyQuietHours
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

    **Two windows, and the difference matters.**

    - `quiet_hours` is the **base** window: the one pair on the row, meaning "this window,
      every day". It is what the settings API reports and what the user set. Its type and
      meaning are exactly what they were before FR-51.
    - `effective_quiet_hours` is **what the delivery path must actually use**: the base
      window on every weekday, with a Pro user's per-weekday overrides applied. It is always
      a `WeeklyQuietHours`, never `None`, so a caller cannot forget the weekly case by
      falling into a null check.

    A caller that wants to know "when is this user quiet" wants the second. The first exists
    because the settings surface reports what the user *set*, and FR-51's seven windows get
    their own surface in `quiet-hours-pro-api`.
    """

    user_id: UUID
    quiet_hours: QuietHours | None
    #: The per-weekday windows as **stored**, whatever the user's tier. A lapsed Pro user's
    #: windows are their own data and are always readable; what a lapse removes is their
    #: effect, which is `effective_quiet_hours`' business.
    quiet_hours_overrides: dict[int, QuietHours]
    effective_quiet_hours: WeeklyQuietHours
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


def _stored_overrides(user_id: UUID) -> dict[int, QuietHours]:
    """This user's per-weekday windows as stored, by weekday. One query."""
    return {
        row.weekday: QuietHours(start=row.start, end=row.end)
        for row in QuietHoursOverride.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .order_by("weekday")
    }


def _effective_week(
    user_id: UUID, base: QuietHours | None, overrides: dict[int, QuietHours]
) -> WeeklyQuietHours:
    """The base window on every weekday, with a Pro user's overrides laid over it (FR-51).

    **The entitlement read only happens if there are overrides to apply.** A user who has
    never been Pro has none, so this never touches `Subscription` at all — which is the
    common case and the one the delivery batch runs on.

    **A lapsed Pro user keeps their rows and loses their effect.** The brief forbids
    deleting them, so the rows stay exactly where they were and this read simply stops
    applying them: the user falls back to their base window, and everything is where they
    left it if they resubscribe. That is the explicit answer the acceptance criterion asked
    for, and it is here rather than in a docstring somewhere because this is the only place
    that decides it.
    """
    if not overrides or not is_pro(user_id=user_id):
        return WeeklyQuietHours.every_day(base)

    windows: list[QuietHours | None] = [base] * DAYS_IN_WEEK
    for weekday, window in overrides.items():
        windows[weekday] = window
    return WeeklyQuietHours(windows=tuple(windows))


def _to_settings(row: NotificationPreference) -> NotificationSettings:
    window = None
    if row.quiet_hours_start is not None and row.quiet_hours_end is not None:
        window = QuietHours(start=row.quiet_hours_start, end=row.quiet_hours_end)
    overrides = _stored_overrides(row.user_id)
    return NotificationSettings(
        user_id=row.user_id,
        quiet_hours=window,
        quiet_hours_overrides=overrides,
        effective_quiet_hours=_effective_week(row.user_id, window, overrides),
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


def set_quiet_hours_override(
    *,
    user_id: UUID,
    weekday: int,
    window: QuietHours,
    actor: Actor,
    now: datetime,
) -> NotificationSettings:
    """Set one weekday's quiet-hours window for a Pro user (FR-51).

    **This writes the row whatever the user's tier is, and the *read* decides whether it
    counts.** Entitlement is checked where the window is used (`_effective_week`), not here,
    for the same reason a lapsed Pro user's rows are not deleted: the data is the user's,
    and the subscription governs its effect rather than its existence. A command that
    refused on tier would also have to be re-run after an upgrade to restore what the user
    already said.

    **`start == end` is refused**, exactly as for the base window. "No quiet hours" has one
    spelling — a null base pair — and a zero-length override would be a second. "No quiet
    hours *on this day*" is the absence of a row, which is what `clear_quiet_hours_override`
    leaves behind. The database refuses it too (`quiet_hours_override_not_empty_ck`).

    Raises:
        InvalidQuietHoursWindowError: the window's start equals its end.
        ValueError: `weekday` is not 0..6.
    """
    if not 0 <= weekday < DAYS_IN_WEEK:
        raise ValueError(f"weekday must be 0..{DAYS_IN_WEEK - 1}, got {weekday}")
    if window.disabled:
        raise InvalidQuietHoursWindowError(
            details={"quiet_hours_start": str(window.start), "quiet_hours_end": str(window.end)}
        )

    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        row = _get_or_create_row(user_id)
        override, _created = QuietHoursOverride.objects.using(PERSONAL).update_or_create(
            user_id=user_id,
            weekday=weekday,
            defaults={"start": window.start, "end": window.end},
        )
        write_audit(
            actor=actor,
            action="notification_preference.quiet_hours_override_set",
            target_type="quiet_hours_override",
            target_id=override.id,
            details={
                "weekday": weekday,
                "quiet_hours_start": str(window.start),
                "quiet_hours_end": str(window.end),
                "at": now.isoformat(),
            },
        )
        return _to_settings(row)


def replace_quiet_hours_overrides(
    *,
    user_id: UUID,
    overrides: Mapping[int, QuietHours],
    actor: Actor,
    now: datetime,
) -> NotificationSettings:
    """Replace this user's whole set of per-weekday windows in one go (FR-51).

    **The week is applied atomically, and the transaction is what guarantees that.** A list
    whose seventh window is `start == end` must leave the first six unwritten, not applied;
    the raise unwinds the surrounding `transaction.atomic`, so nothing lands. Mutation
    testing confirms this is the transaction's doing: moving the validation *inside* the
    write loop keeps every atomicity test green.

    The validation still runs first, for a smaller reason that is worth stating so nobody
    "simplifies" it back: a request that is going to fail should not first take this user's
    advisory lock and serialise their other settings writes behind it.

    **It is a replace, not a merge.** A weekday absent from `overrides` has its row removed,
    because that is how a day says "the base window applies here". A merge would make it
    impossible to go back to six overrides without a second call, and "set my week" is the
    operation the settings screen actually performs.

    **It does not check entitlement**, deliberately — the same choice
    `set_quiet_hours_override` made and for the same reason. The rows are the user's data;
    the subscription governs their *effect*, which `_effective_week` decides, and their
    writability, which the API decides where the user is. A command that refused on tier
    would have to be re-run after an upgrade to restore what the user already said.

    Raises:
        InvalidQuietHoursWindowError: any window's start equals its end.
        ValueError: any weekday is not 0..6.
    """
    for weekday, window in overrides.items():
        if not 0 <= weekday < DAYS_IN_WEEK:
            raise ValueError(f"weekday must be 0..{DAYS_IN_WEEK - 1}, got {weekday}")
        if window.disabled:
            raise InvalidQuietHoursWindowError(
                details={
                    "weekday": weekday,
                    "quiet_hours_start": str(window.start),
                    "quiet_hours_end": str(window.end),
                }
            )

    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        row = _get_or_create_row(user_id)
        QuietHoursOverride.objects.using(PERSONAL).filter(user_id=user_id).exclude(
            weekday__in=list(overrides)
        ).delete()
        for weekday, window in sorted(overrides.items()):
            QuietHoursOverride.objects.using(PERSONAL).update_or_create(
                user_id=user_id,
                weekday=weekday,
                defaults={"start": window.start, "end": window.end},
            )
        write_audit(
            actor=actor,
            action="notification_preference.quiet_hours_overrides_replaced",
            target_type="notification_preference",
            target_id=row.id,
            details={
                "weekdays": sorted(overrides),
                "windows": {
                    str(weekday): [str(window.start), str(window.end)]
                    for weekday, window in sorted(overrides.items())
                },
                "at": now.isoformat(),
            },
        )
        return _to_settings(row)


def clear_quiet_hours_override(
    *,
    user_id: UUID,
    weekday: int,
    actor: Actor,
    now: datetime,
) -> NotificationSettings:
    """Remove one weekday's override, returning that day to the base window (FR-51).

    **The absence of a row is how a day says "the base window applies here".** This is the
    one deletion in the quiet-hours story, and it deletes a user's own explicit statement at
    the user's own request — not a lapsed subscription's data, which the brief protects.

    Clearing a weekday that has no override is a no-op and writes no audit row: nothing
    changed, so there is nothing to record.
    """
    if not 0 <= weekday < DAYS_IN_WEEK:
        raise ValueError(f"weekday must be 0..{DAYS_IN_WEEK - 1}, got {weekday}")

    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        row = _get_or_create_row(user_id)
        override = (
            QuietHoursOverride.objects.using(PERSONAL)
            .filter(user_id=user_id, weekday=weekday)
            .first()
        )
        if override is None:
            return _to_settings(row)

        override_id = override.id
        override.delete(using=PERSONAL)
        write_audit(
            actor=actor,
            action="notification_preference.quiet_hours_override_cleared",
            target_type="quiet_hours_override",
            target_id=override_id,
            details={"weekday": weekday, "at": now.isoformat()},
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
    "clear_quiet_hours_override",
    "replace_quiet_hours_overrides",
    "set_quiet_hours",
    "set_quiet_hours_override",
]
