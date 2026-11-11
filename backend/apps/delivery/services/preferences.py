"""The write commands for the notification settings, and the rewrite they carry with them.

**What a settings write does, in two parts.** It changes the setting, and it **re-times the
user's pending sends** so the change is real rather than promised. AD-7: a preference change
*"rewrites `due_at` on `pending` rows only and never touches the key, so a recompute can never
produce a second send."* That is why a user can change their quiet hours ten times and still
receive one reminder.

**The rewrite is not optional, and it is not per-setting.** Every write here calls
`reschedule_pending_for_user` — the command that owns the re-timing. A row whose recomputed
time equals its stored time is left alone, so a write that changes nothing moves nothing.

**The default Reminder Plan is the exception that proves the rule.** Changing the default does
*not* touch existing per-event plans (FR-20): the default applies to future attachments only.
That is true **by construction, not by a special case** — the default is not an input to any
`due_at` computation, so a rewrite cannot move a per-event plan's row even in principle. The
rewrite still runs after a default-plan write, and finds nothing to move.

**The settings are owned by two apps, and each write goes through its owner's command.**
`delivery` owns the window and the default plan, and calls its own published commands.
`personalization` owns the delivery time and the zone, and the write goes through
`personalization`'s published `onboarding.set_digest_preference` — the same command the
onboarding endpoint calls, so there is one writer for that row and one validation for that
zone (AD-16). The import is function-local: `apps.personalization.services.personal_events`
imports `apps.delivery.services.reminder_plans`, so a module-level import here could close a
loop at import time.

**A partial write is one transaction.** The work item asks for *"a request that sets the
window and the default plan either applies both or neither"*. Both modules write to the
`personal` schema, so their `transaction.atomic(using=PERSONAL)` blocks **nest** — an outer
atomic makes the inner ones part of one transaction, and a failure in the second write rolls
the first back with it.

**The lock order is fixed, and it is `delivery` first.** The two modules take different
advisory locks (`notification_preferences` takes `eventpulse24-ntf`, `onboarding` takes
`eventpulse24-onb`) because they lock different rows. A request that writes both takes both,
and **the order must never vary** or two concurrent such requests could deadlock. `delivery`
first is the right order because a request that writes only `delivery`'s settings takes only
`delivery`'s lock — so the one-lock path never waits on the two-lock path, and no cycle can
form.

**What this module does NOT do: it does not touch `personalization`'s other preferences.** The
home city and the personal-events opt-out are `DigestPreference` columns too, but they are
the *digest's content*, not its schedule, and they are not what this endpoint is for.
`set_digest_preference` leaves both alone when they are not passed, and this module does not
pass them.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time
from uuid import UUID

from django.db import transaction

from apps.delivery.services.notification_preferences import (
    replace_quiet_hours_overrides,
    set_default_reminder_slots,
    set_quiet_hours,
)
from apps.delivery.services.scheduled_sends import reschedule_pending_for_user
from domain.quiet_hours import QuietHours
from shared.actor import Actor
from shared.db import PERSONAL


@dataclass(frozen=True)
class SettingsPatch:
    """What the caller wants changed — **only what they mentioned**.

    **`None` means "leave it alone"** for every field except `quiet_hours`, where `None`
    means "no quiet hours". The caller distinguishes the two before it gets here: the API
    layer reads the request's *field presence*, so "mentioned and null" arrives as a
    `clear_quiet_hours` flag rather than as an ambiguous `None`.

    That is why the dataclass has a flag rather than a nullable field. A field that can be
    "unset" and "set to nothing" at once is a field whose meaning depends on how it was
    sent, and the meaning has to survive the trip from the wire.
    """

    quiet_hours: QuietHours | None = None
    clear_quiet_hours: bool = False
    #: The per-weekday windows to store, or `None` to leave them alone. An **empty mapping
    #: is not `None`**: it means "remove every override", which is how a user goes back to
    #: one window for the whole week. The API tells the two apart by field presence, as it
    #: does for `quiet_hours`.
    quiet_hours_overrides: Mapping[int, QuietHours] | None = None
    default_reminder_slots: tuple[str, ...] | None = None
    delivery_time: time | None = None
    timezone: str | None = None

    @property
    def touches_quiet_hours(self) -> bool:
        """Whether this patch mentions the window at all."""
        return self.clear_quiet_hours or self.quiet_hours is not None

    @property
    def touches_quiet_hours_overrides(self) -> bool:
        """Whether this patch mentions the per-weekday windows at all."""
        return self.quiet_hours_overrides is not None

    @property
    def touches_digest_schedule(self) -> bool:
        """Whether this patch mentions the delivery time and zone.

        **They are one field, because they are one fact.** A wall clock without its zone is
        not a schedule, so they cannot be changed separately and cannot be half-applied.

        **Both or neither.** A patch that carried only one of them would leave the other
        stale — a delivery time in the old zone — which is a schedule nobody chose. The
        API refuses such a request before it gets here; this property is the safety net
        underneath it, so a caller that reaches the service with half a pair changes
        nothing rather than half-changing.
        """
        return self.delivery_time is not None and self.timezone is not None


@dataclass(frozen=True)
class SettingsWriteResult:
    """What one settings write did.

    `rewritten` is how many pending rows were re-timed. It is **not** how many were minted —
    the rewrite cannot mint, and that is asserted structurally in the test suite.
    """

    rewritten: int


def apply_settings_patch(
    *,
    user_id: UUID,
    patch: SettingsPatch,
    actor: Actor,
    now: datetime,
) -> SettingsWriteResult:
    """Apply the patch, and re-time the user's pending sends with it.

    **One transaction around the whole thing.** The settings writes and the rewrite are in
    it together, so a user whose window was written but whose sends were not re-timed never
    exists — the reminder would go out at the old hour, and the settings screen would say
    otherwise.

    **The order is `delivery` first, then `personalization`, then the rewrite.** The first
    two are the settings themselves; the rewrite goes last because it must recompute from the
    **new** values. A rewrite that ran before the write would compute the old times and
    change nothing.
    """
    with transaction.atomic(using=PERSONAL):
        if patch.touches_quiet_hours:
            set_quiet_hours(
                user_id=user_id,
                window=None if patch.clear_quiet_hours else patch.quiet_hours,
                actor=actor,
                now=now,
            )

        if patch.touches_quiet_hours_overrides:
            # Inside the same transaction as the base window and the rewrite below, so a
            # week is never half-applied and the pending sends are re-timed from the
            # windows the user just set.
            replace_quiet_hours_overrides(
                user_id=user_id,
                overrides=patch.quiet_hours_overrides,
                actor=actor,
                now=now,
            )

        if patch.default_reminder_slots is not None:
            set_default_reminder_slots(
                user_id=user_id,
                slots=patch.default_reminder_slots,
                actor=actor,
                now=now,
            )

        if patch.touches_digest_schedule:
            _set_digest_schedule(
                user_id=user_id,
                delivery_time=patch.delivery_time,
                timezone_name=patch.timezone,
                actor=actor,
                now=now,
            )

        rewritten = reschedule_pending_for_user(user_id=user_id, actor=actor, now=now)

    return SettingsWriteResult(rewritten=rewritten)


def _set_digest_schedule(
    *,
    user_id: UUID,
    delivery_time: time,
    timezone_name: str,
    actor: Actor,
    now: datetime,
) -> None:
    """The delivery time and the zone, through `personalization`'s published command.

    **This is the command onboarding uses**, and it is the only writer of that pair of
    columns. Calling it here — rather than writing `DigestPreference` from `delivery` — is
    what keeps AD-16's strict write ownership intact: `personalization` owns the row, so
    `personalization` writes it.

    **The zone and the wall clock are validated there**, by `domain.timezones.canonical_zone`
    and the plain-wall-clock check — the same checks the onboarding endpoint gets, so
    "Etc/UTC" is stored as "UTC" and an offset-bearing time is refused, wherever it came
    from.

    **The city and the opt-out are not passed**, and that is deliberate: they are the
    digest's *content* preferences rather than its schedule, and `set_digest_preference`
    leaves both alone when they are not given. A request that only moves the delivery time
    must not reset the user's home city.

    The import is function-local: `apps.personalization.services.personal_events` imports
    `apps.delivery.services.reminder_plans`, so a module-level import here could close a
    loop at import time.
    """
    from apps.personalization.services.onboarding import set_digest_preference

    set_digest_preference(
        user_id=user_id,
        delivery_time=delivery_time,
        timezone_name=timezone_name,
        actor=actor,
        now=now,
    )


__all__ = [
    "SettingsPatch",
    "SettingsWriteResult",
    "apply_settings_patch",
]
