"""AD-7 send keys: the stable idempotency key every send carries.

The key is **minted once, when the `SCHEDULED_SEND` row is created**, stored under a unique
constraint, and **never derived from `due_at`**. That last clause is the one this module exists
to make structurally true, so it is worth saying plainly what goes wrong without it.

Four ordinary user actions rewrite `due_at` on pending rows — changing quiet hours, changing
timezone, changing the digest delivery time, editing a Reminder Plan. If the key moved with the
time, **each of those would mint a second send**, and a user who adjusted their settings three
times would receive four copies of one reminder. The key identifies *the thing being sent*, not
*when it goes*.

**No function here takes an instant of any kind**, and `tests/delivery/test_send_keys.py`
asserts that by inspecting the signatures — a rule the test suite checks rather than one
everybody has to remember. A `time` or `datetime` would be a clock, and a clock in a key is
`due_at` by another name. The one time-shaped value a key may carry is the digest's
**local date** — a calendar day, not an instant — and it is the same value the digest is
*about*, so it names the send rather than timing it.

The separator is `shared.constants.SEND_KEY_SEPARATOR` (`:`), per the coding standard: "never
`-` or `_`. That keeps each UUID a 36-character run, so keys survive log scrubbing" (AD-13).

The shapes are AD-7's table, unchanged. `pulse_ping` has no builder: in MVP the digest email
*is* the Pulse Ping (decided 2026-10-31), so the `digest` key is the only daily one minted. A
builder for a key nothing mints would be dead code that looks like a feature.
"""

from datetime import date
from uuid import UUID

from shared.constants import SEND_KEY_SEPARATOR

# The longest shape is a personal reminder carrying a custom slot:
#   36 (user) + 1 + 17 (kind) + 1 + 36 (event) + 1 + 12 (custom:43200) + 1 + 10 (revision)
# ≈ 115 characters. The column is 255, so a longer slot format has visible headroom.
#
# The custom slot's suffix used to be budgeted as a 43-character `custom:<uuid>`. It is now
# the slot's **offset in minutes** (`custom:90`), so the longest suffix is 12 characters
# (`custom:43200` — thirty days) and the key got *shorter*. See
# `shared.constants.CUSTOM_SLOT_MIN_MINUTES`.
SEND_KEY_MAX_LENGTH = 255


def _join(*parts: object) -> str:
    return SEND_KEY_SEPARATOR.join(str(part) for part in parts)


def event_reminder_key(*, user_id: UUID, event_id: UUID, slot: str, event_version: int) -> str:
    """A reminder for a saved public event.

    `event_version` is the version **at minting** and is frozen here. AD-17 propagation may
    re-stamp the row's working `event_version` column, but never this key — which is what lets
    a moved event cancel its old pending rows and mint new ones while the old key stays spent.
    """
    return _join(user_id, "event_reminder", event_id, slot, event_version)


def personal_reminder_key(
    *, user_id: UUID, personal_event_id: UUID, slot: str, personal_event_revision: int
) -> str:
    """A reminder for a personal event. `personal_event_revision` is the value at minting."""
    return _join(user_id, "personal_reminder", personal_event_id, slot, personal_event_revision)


def state_notice_key(*, user_id: UUID, state_change_id: UUID) -> str:
    """A state-change notice (FR-54).

    One notice per user per state change: the change's id is what makes it unique, so a
    propagation retried after a partial run cannot queue a second notice.
    """
    return _join(user_id, "state_notice", state_change_id)


def state_change_id_from_key(send_key: str) -> UUID | None:
    """The state change a state-notice key names — the inverse of `state_notice_key`.

    **The renderer needs the change, and the row does not carry it.** `ScheduledSend`
    has no `state_change_id` column: it has a `target_id` (the event) and a `send_key`,
    and the key is where AD-7 put the change's id. So the renderer reads the key back
    out to find the change whose facts it needs — the new time, the venue fingerprints,
    the replacement event.

    **The parser lives beside the builder**, for the same reason `digest_local_date_from_key`
    does: a key shape parsed in two places is a key shape that will be parsed wrongly in
    one of them.

    **`None` means "this is not a state-notice key"**, and the caller treats it as a
    vanished target rather than guessing — a key that cannot be read is a row that
    cannot be rendered, and a mail about the wrong event is worse than no mail.

    The parse is strict: exactly three `:`-separated parts — the user id, the literal
    `"state_notice"`, and a real UUID.
    """
    parts = send_key.split(SEND_KEY_SEPARATOR)
    if len(parts) != 3 or parts[1] != "state_notice":
        return None
    try:
        return UUID(parts[2])
    except ValueError:
        return None


def digest_key(*, user_id: UUID, local_date: date) -> str:
    """The daily Pulse Digest email — which in MVP **is** the Pulse Ping (FR-10).

    Keyed by the user's **local** date, not a UTC one: "today" is a different day for a user in
    Auckland and one in Los Angeles at the same instant, and the key has to mean "this user's
    day". The caller supplies the local date; this module reads no clock.

    One key per user per local date is what makes FR-10's "a user with 3 qualifying events
    receives exactly 1 Pulse Ping, not 3" true by construction rather than by a count.
    """
    return _join(user_id, "digest", local_date.isoformat())


def digest_local_date_from_key(send_key: str) -> date | None:
    """The local date a digest key names — the inverse of `digest_key`.

    **A digest row stores no date.** `ScheduledSend` has no date column for it: `slot` is
    empty, `target_id` is `NULL`, and the local date lives **only inside the key**. So when a
    preference change rewrites a pending digest's `due_at`, the date has to come from
    somewhere — and it comes from here, the one place that knows the key's shape.

    **The parser lives beside the builder, not beside the reader.** A key shape parsed in two
    places is a key shape that will be parsed wrongly in one of them; the builder and its
    inverse are one piece of knowledge about one string.

    **`None` means "this is not a digest key"**, and the caller skips rather than guesses —
    the same rule `slots.slot_offset` follows. A date that cannot be read is never
    approximated: a digest shifted to the wrong day is a digest that goes out at the wrong
    hour on the wrong day.

    The parse is strict: exactly three `:`-separated parts — the user id, the literal
    `"digest"`, and a real ISO date. Anything else is `None`.
    """
    parts = send_key.split(SEND_KEY_SEPARATOR)
    if len(parts) != 3 or parts[1] != "digest":
        return None
    try:
        return date.fromisoformat(parts[2])
    except ValueError:
        return None


__all__ = [
    "SEND_KEY_MAX_LENGTH",
    "digest_key",
    "digest_local_date_from_key",
    "event_reminder_key",
    "personal_reminder_key",
    "state_change_id_from_key",
    "state_notice_key",
]
