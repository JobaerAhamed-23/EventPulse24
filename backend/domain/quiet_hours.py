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
from datetime import date, datetime, time, timedelta
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


DAYS_IN_WEEK = 7

#: How many times the shift may defer before giving up.
#:
#: **Seven day-anchored windows can never cover a whole week**, so a sendable moment always
#: exists and this bound is never reached. The proof: a window spans `(end - start) mod
#: 1440` minutes, which is at most 1439 — a span of 0 is `disabled`, not 24 hours. Closing
#: every seam around the week needs the spans to sum to the week's 10080 minutes, and seven
#: windows can sum to at most 7 x 1439 = 10073. Every schedule leaves at least seven
#: minutes open.
#:
#: The bound is therefore a termination guarantee, not a policy: it makes the loop provably
#: finite for a reader who has not done that arithmetic, and
#: `test_every_schedule_leaves_a_sendable_moment` does the arithmetic by brute force.
MAX_DEFERRALS = 8


@dataclass(frozen=True)
class WeeklyQuietHours:
    """Seven windows, one per weekday — a Pro user's quiet hours (FR-51).

    Indexed by `date.weekday()`: Monday 0 … Sunday 6. A `None` slot is a day with no quiet
    hours at all.

    **A day's window begins on that day.** A Friday 22:00-08:00 window is *Friday night*: it
    opens Friday at 22:00 and owns Saturday's small hours right through to 08:00. Saturday's
    own window does not begin until Saturday's start.

    The alternative — asking each local instant's own weekday for a window and calling
    `covers()` — is wrong in the dangerous direction. Saturday's 23:00-09:00 window would
    "cover" Saturday 02:00 through its morning side, so the user's Saturday setting would
    quietly govern Saturday *morning* instead of Saturday *night*. That is not what anyone
    setting a window per weekday means by it, and it is how a send ends up at 3am.

    Like `QuietHours`, these are **local wall clocks and nothing else**: no instants, no
    zone. The zone is passed to `shift_to_sendable` separately, because the user has exactly
    one and a copy here would be free to drift from it.
    """

    windows: tuple[QuietHours | None, ...]

    def __post_init__(self) -> None:
        if len(self.windows) != DAYS_IN_WEEK:
            raise ValueError(f"a week has {DAYS_IN_WEEK} days, got {len(self.windows)} windows")

    @classmethod
    def every_day(cls, window: QuietHours | None) -> "WeeklyQuietHours":
        """The same window on all seven days — what a Free user's single window means."""
        return cls(windows=(window,) * DAYS_IN_WEEK)

    def for_weekday(self, weekday: int) -> QuietHours | None:
        """The window that *begins* on this weekday, or None."""
        return self.windows[weekday]


def _window_beginning_on(window: "Window | None", day: date) -> QuietHours | None:
    """The window that opens on `day`, for either shape of schedule.

    A bare `QuietHours` is "this window, every day" — which is exactly what a Free user's
    single stored window is, so a Free user's send travels the same arithmetic it always
    has.
    """
    if window is None:
        return None
    if isinstance(window, WeeklyQuietHours):
        return window.for_weekday(day.weekday())
    return window


def _ends_covering(window: "Window | None", local: datetime) -> list[datetime]:
    """The naive local ends of every window covering `local`. Empty means "send now".

    Only two windows can reach a given instant: the one that opens on its own date, and the
    previous day's if that one crosses midnight. Each contributes the wall clock it ends on.
    """
    local_date = local.date()
    local_clock = local.time()
    ends: list[datetime] = []

    today = _window_beginning_on(window, local_date)
    if today is not None and not today.disabled:
        if today.crosses_midnight:
            # Opened today at `start` and runs into tomorrow. The morning side of today is
            # *yesterday's* window's business, handled below.
            if local_clock >= today.start:
                ends.append(datetime.combine(local_date + timedelta(days=1), today.end))
        elif today.start <= local_clock < today.end:
            ends.append(datetime.combine(local_date, today.end))

    yesterday_date = local_date - timedelta(days=1)
    yesterday = _window_beginning_on(window, yesterday_date)
    if (
        yesterday is not None
        and not yesterday.disabled
        and yesterday.crosses_midnight
        and local_clock < yesterday.end
    ):
        ends.append(datetime.combine(local_date, yesterday.end))

    return ends


#: Either shape of schedule: one window for every day, or one per weekday.
Window = QuietHours | WeeklyQuietHours


def shift_to_sendable(instant: datetime, *, window: Window | None, zone: str) -> datetime:
    """The instant this send should actually go out (AD-7).

    Returns `instant` **unchanged** when it falls outside every window, when there is no
    window, or when the window is disabled. Otherwise returns the end of the window the
    instant fell into, in `zone`, on the day that window actually ends.

    `window` is either one `QuietHours` — the same window every day, which is what a Free
    user has — or a `WeeklyQuietHours` of seven. The single-window case is the same
    arithmetic it has always been; `tests/domain/test_quiet_hours.py` pins that it has not
    moved.

    **Two windows can cover one instant.** A Friday window running to 10:00 and a Saturday
    window from 09:00 both cover Saturday 09:30. Releasing the send at 10:00 would drop it
    into the middle of Saturday's window, so the answer is 11:00.

    **What guarantees that is the loop, not the `max`.** The end of one window can sit
    inside another's — a Monday window ending Tuesday 00:30 lands inside a Tuesday window
    that opens at 00:00 — so the shift repeats until the instant is covered by nothing.
    Coverage is a union of intervals and each pass steps forward inside it, so the loop
    exits at the right-hand end of whichever run of overlapping windows the instant fell in.
    Taking `max(ends)` rather than any other covering end only gets there in fewer passes:
    **it is an optimisation, and mutation testing confirms `min` reaches the same answer.**
    The loop is what makes the answer right.

    **It stays total.** Seven windows cannot cover a whole week (see `MAX_DEFERRALS`), so
    the loop always finds a sendable moment. If the bound were somehow exhausted it returns
    the last end it computed rather than the unshifted instant: a send that is late can be
    recovered, and a send at 3am cannot.

    Idempotent: the result sits at a window's end, which is outside that window (the end is
    exclusive), and the loop has already checked it is outside every other one. The one
    assumption is that a DST gap is shorter than the gap between a window's end and the next
    start — true of every real zone, where a gap is an hour or less and the awake part of a
    day is many.

    Never moves a send **backwards**: every end is later than a due time that fell inside its
    window, on every branch. A send moved backwards would fire on the next sweep.

    Args:
        instant: an aware datetime — the due time before Quiet Hours.
        window: the user's schedule, or None for "no quiet hours".
        zone: the user's IANA zone, which the wall clocks are read in.

    Raises:
        TypeError: `instant` is naive (inherited from `to_instant`; AD-6 forbids naive).
    """
    if window is None:
        # Returned as given, not re-zoned: an unaffected send must be bit-for-bit untouched.
        return instant

    zoneinfo = ZoneInfo(zone)
    local = to_instant(instant).astimezone(zoneinfo)

    sendable = instant
    for _pass in range(MAX_DEFERRALS):
        ends = _ends_covering(window, local)
        if not ends:
            return sendable
        # `read_wall_clock` resolves a DST gap or fold deterministically; its second return
        # value is an extraction confidence cap, which means nothing here and is discarded
        # by name rather than silently.
        sendable, _dst_cap = read_wall_clock(max(ends), zone)
        local = sendable.astimezone(zoneinfo)

    # Unreachable: see `MAX_DEFERRALS`. Returning the last end keeps the function total
    # without ever handing back an instant known to be inside a window.
    return sendable
