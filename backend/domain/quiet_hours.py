"""Quiet Hours: when a due send should actually happen (FR-12, AD-7). Stdlib only.

AD-7's rule, in full: *"Quiet Hours are applied when `due_at` is **computed or recomputed**,
deferring to the window end — never as a skip at send time. A deferred send is silently moved,
never dropped and never re-delivered next day."*

That sentence decides this module's whole shape. `shift_to_sendable` returns **the time to
send**, and the caller stores it. The sweep then reads a `due_at` that is already true and must
never consult this module again — a send-time check would re-defer a send that was already
moved, and a send deferred twice is a send that never leaves.

Three things make this harder than comparing two clocks, and each has tests that pin it:

**The window is wall-clock, the due time is an instant.** They can only be compared after the
instant is read in the user's zone, and the answer has to be converted back. Nothing here reads
a clock or a preference: the caller supplies the window and the zone, exactly as
`domain.conflict` makes the caller supply the intervals.

**The default window crosses midnight.** 22:00-08:00 is not a range, and testing it as one is
the bug this docstring exists to prevent — it would misfire for the default every user has.
"Inside" is a disjunction (`t >= start or t < end`), and which *day* the window ends on depends
on which side of midnight the due time sits: an evening send defers to tomorrow morning, a
small-hours send defers to this morning.

**The window's end is a wall clock, so some days it does not exist.** On a spring-forward day it
can fall in a DST gap; on a fall-back day it occurs twice. `domain.timezones.read_wall_clock`
already resolves exactly this — gap and fold detected by round-tripping through UTC, resolved
deterministically at `fold=0` — so it is reused rather than re-derived (AD-16). Its second
return value is an extraction confidence cap, which means nothing here and is discarded.

Two boundary decisions, both load-bearing:

- **The start is inclusive, the end is exclusive.** This is what makes the shift idempotent: the
  returned instant sits exactly at the window end, which is therefore *outside* the window, so
  shifting it again returns it unchanged. A closed end would make the function shift forever on
  its own output.
- **`start == end` means disabled, not "defer forever."** See `InvalidQuietHoursWindowError`:
  the shift stays total and returns the instant unchanged; the command layer refuses to store
  such a window, so "no quiet hours" has one spelling — a null window.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from domain.timezones import read_wall_clock, to_instant


@dataclass(frozen=True)
class QuietHours:
    """A user's quiet window, as a pair of **local wall clocks** (FR-12).

    Deliberately not instants and deliberately not zone-aware: "10pm" means 10pm wherever
    the user is, and survives both travel and DST because it is re-read against the zone
    every time a due time is computed. The zone is passed separately to
    `shift_to_sendable`, because the user has exactly one zone and a second copy here
    would be free to drift from it.
    """

    start: time
    end: time

    @property
    def disabled(self) -> bool:
        """A window of zero length. See the module docstring: unchanged, never deferred."""
        return self.start == self.end

    @property
    def crosses_midnight(self) -> bool:
        """True for the default 22:00-08:00 window, and for every window like it."""
        return self.start > self.end

    def covers(self, local: time) -> bool:
        """Is this local wall-clock time inside the window? Start inclusive, end exclusive."""
        if self.disabled:
            return False
        if self.crosses_midnight:
            return local >= self.start or local < self.end
        return self.start <= local < self.end


def shift_to_sendable(instant: datetime, *, window: QuietHours | None, zone: str) -> datetime:
    """The instant this send should actually go out (AD-7).

    Returns `instant` **unchanged** when it falls outside the window, when there is no
    window, or when the window is disabled. Otherwise returns the window's end, in `zone`,
    on the day the window the instant fell into actually ends.

    Idempotent: the result sits at the window's end, which is outside the window (the end is
    exclusive), so shifting it again is a no-op. The one assumption is that a DST gap is
    shorter than the gap between the window's end and its next start — true of every real
    zone, where a gap is an hour or less and the awake part of a day is many.

    Never moves a send **backwards**: the window's end is always later than a due time that
    fell inside it, on every branch. A send moved backwards would fire on the next sweep.

    Args:
        instant: an aware datetime — the due time before Quiet Hours.
        window: the user's window, or None for "no quiet hours".
        zone: the user's IANA zone, which the window's wall clocks are read in.

    Raises:
        TypeError: `instant` is naive (inherited from `to_instant`; AD-6 forbids naive).
    """
    if window is None or window.disabled:
        # Returned as given, not re-zoned: an unaffected send must be bit-for-bit untouched.
        return instant

    local = to_instant(instant).astimezone(ZoneInfo(zone))
    local_clock = local.time()
    if not window.covers(local_clock):
        return instant

    # Which day does this window end on? For an ordinary window, today. For one that crosses
    # midnight, it depends which side of midnight we are on: a 23:30 send is on the *evening*
    # side and defers to tomorrow's 08:00, while a 02:00 send is on the *morning* side of a
    # window that began yesterday, and defers to today's 08:00.
    end_date = local.date()
    if window.crosses_midnight and local_clock >= window.start:
        end_date += timedelta(days=1)

    # The window's end as a naive wall clock, then read in the zone. `read_wall_clock` resolves
    # a DST gap or fold deterministically; its confidence cap is an extraction concern and is
    # not ours, so it is discarded by name rather than silently.
    sendable, _dst_cap = read_wall_clock(datetime.combine(end_date, window.end), zone)
    return sendable
