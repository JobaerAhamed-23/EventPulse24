"""The published read of one user's notification settings, as **one** answer (AD-2, AD-16).

**What this module exists for.** The settings the two `/settings/*` screens need are split
across two tables in two apps — the Quiet Hours window and the default Reminder Plan on
`delivery`'s `NotificationPreference`, the delivery time and the zone on `personalization`'s
`DigestPreference`. That split is deliberate (the 2026-10-31 ownership decision, recorded on
the model), and the client should never see it: **one call, one response**, with all four
facts in it.

**The read is assembled from two published services, and the seam is the point.** `delivery`
reads its own row directly — it owns the table, and this is the hot path of every `due_at`
computation (AD-16). `personalization`'s facts come through its published
`get_delivery_settings`, because `delivery` may not import another app's models (AD-3). The
import is **function-local**, the `_zone_for` pattern, because a module-level import closes a
cycle at import time.

**Nothing here writes.** The read is a read: it creates no rows, mints no sends and rewrites
no schedules. `get_preference` does create the preference row on a first read — that is the
documented behaviour of that command, and it is what lets the minting path read one row and
branch on nothing.

**The fallbacks are the shared constants, never a guess.** A user with no `DigestPreference`
row — an account that has not finished onboarding — has **no delivery time and no zone**,
which is a real state. The read answers with `DEFAULT_DIGEST_DELIVERY_TIME` and
`DEFAULT_DIGEST_TIMEZONE`, because a settings screen that renders "no delivery time" cannot
show the user what they will actually get, and a guessed zone would show the wrong hour.
"""

from dataclasses import dataclass
from datetime import time
from uuid import UUID

from apps.delivery.services.notification_preferences import get_preference
from domain.quiet_hours import QuietHours, WeeklyQuietHours
from shared.constants import DEFAULT_DIGEST_DELIVERY_TIME, DEFAULT_DIGEST_TIMEZONE


@dataclass(frozen=True)
class NotificationSettingsView:
    """One user's notification settings, as plain data.

    A frozen dataclass and never a model instance: `delivery` and `personalization` both own
    pieces of this, and a caller that received a model could write it (AD-16).

    `quiet_hours` is `None` when the user has turned quiet hours **off** — and only then.
    "Never set" is not a state this field can hold, because reading the preference creates
    the row with the defaults.

    `delivery_time` is a **local wall clock** and `timezone` is the zone it is a clock in.
    They are two fields rather than one because they are two facts, and a client that has
    only one of them cannot show the user the other.
    """

    user_id: UUID
    quiet_hours: QuietHours | None
    #: The per-weekday windows as **stored** — always readable, whatever the user's tier.
    quiet_hours_overrides: dict[int, QuietHours]
    #: What the delivery path will actually use. For a Free or lapsed account this is the
    #: base window on all seven days, whatever `quiet_hours_overrides` holds. Reporting
    #: only the stored overrides would show a lapsed user seven windows not in force.
    effective_quiet_hours: WeeklyQuietHours
    default_reminder_slots: tuple[str, ...]
    delivery_time: time
    timezone: str
    #: Whether the daily Pulse Ping is **on** (FR-10).
    #:
    #: **Stated as "on", not as the opt-out it is stored as.** The column is
    #: `pulse_ping_unsubscribed`, and the inversion happens here, once, at the edge of the
    #: read — so every caller above this line, the wire included, reads a field whose
    #: `True` means what a user would expect it to mean. A settings screen that had to
    #: remember it was rendering a double negative is a settings screen that will
    #: eventually render it the wrong way round.
    pulse_ping: bool


def _delivery_settings(user_id: UUID) -> tuple[time, str]:
    """The user's delivery time and zone, from `personalization`'s published read.

    Imported inside the function: `apps.personalization.services.personal_events` imports
    `apps.delivery.services.reminder_plans`, which reaches `delivery`'s services, so a
    module-level import here would close a loop at import time. The call itself is the
    ordinary published seam — `delivery` never touches `apps.personalization.models` (AD-3).

    **Both fall back to the shared constants.** A user with no preference row is a real
    state, not an error; the answer is what their digest *would* be scheduled at if it were
    minted now.
    """
    from apps.personalization.services.digest_preferences import get_delivery_settings

    settings = get_delivery_settings(user_id=user_id)
    if settings is None:
        return DEFAULT_DIGEST_DELIVERY_TIME, DEFAULT_DIGEST_TIMEZONE
    return settings.delivery_time, settings.timezone


def read_notification_settings(*, user_id: UUID) -> NotificationSettingsView:
    """The user's notification settings — the window, the default slots, the delivery time
    and the zone — as one answer.

    **One call, one response.** The four facts come from two tables in two apps, and the
    client should not have to know that. It asks once and renders one settings screen.

    **The window and the slots come from `delivery`'s own row**, read through
    `notification_preferences.get_preference` — the same published read the minting path
    uses, so the settings screen and the scheduler cannot disagree about the user's night.

    **The delivery time and the zone come from `personalization`'s published read**, because
    `personalization` owns `DigestPreference` and `delivery` may not import another app's
    models (AD-3, AD-16).
    """
    preference = get_preference(user_id=user_id)
    delivery_time, zone = _delivery_settings(user_id)
    return NotificationSettingsView(
        user_id=user_id,
        quiet_hours=preference.quiet_hours,
        quiet_hours_overrides=preference.quiet_hours_overrides,
        effective_quiet_hours=preference.effective_quiet_hours,
        default_reminder_slots=tuple(preference.default_reminder_slots),
        delivery_time=delivery_time,
        timezone=zone,
        pulse_ping=not preference.pulse_ping_unsubscribed,
    )


__all__ = [
    "NotificationSettingsView",
    "read_notification_settings",
]
