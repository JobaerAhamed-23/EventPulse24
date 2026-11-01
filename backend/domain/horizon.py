"""The user's local horizon: how far ahead "the next 48 hours" reaches, in their own zone.

**One rule, and it is not arithmetic.** FR-10 asks whether a user has "events in the next
48 hours", and the acceptance criteria pin that window to the **user's own zone**, not
UTC. A naive `now + timedelta(hours=48)` is a UTC horizon, and it is wrong in two ways
that only show up twice a year:

| | on a spring-forward day | on a fall-back day |
|---|---|---|
| UTC horizon (`now + 48h`) | **47** local hours | **49** local hours |
| local-zone horizon (this module) | **48** local hours | **48** local hours |

The user said "the next 48 hours", and a day that is 23 hours long does not make "48
hours" mean something else. So the horizon is drawn as a **local wall clock** — the
clock reading 48 hours on, resolved in the user's zone — and the duration is kept honest
across the transition.

**How the local wall clock is read.** The user's local reading of "48 hours from now" is
`now` in their zone, plus 48 hours of *wall clock* — so the naive local datetime is
computed first, and only then resolved to an instant. `domain.timezones.read_wall_clock`
already resolves a wall clock in a zone: it detects a DST gap (the time does not exist)
and a fold (the time occurs twice) by round-tripping through UTC, and resolves both
deterministically at `fold=0`. So it is reused rather than re-derived (AD-16). Its second
return value is an extraction-confidence cap, which means nothing here and is discarded by
name.

**The boundary is inclusive.** An event starting *exactly* at the horizon qualifies. FR-5's
"within the next 48 hours" includes the boundary, and the ranking boost it carries
(`RANKING_PERSONAL_EVENT_BOOST`) applies at exactly the same boundary — so the candidate
set and the boost cannot disagree about which events are "soon". The rule is therefore
`start <= horizon`, and the caller compares against this instant.

**An unknown zone falls back to UTC rather than raising.** The zone is validated at write
time by the onboarding command, so an unknown name means hand-edited data. A horizon that
raised would take down the digest composition for that user, which is a worse failure than
a horizon computed in the fallback zone. The same choice `digest_dates.local_date_for`
makes, for the same reason.

**The window is a parameter, not a constant.** The function takes the duration so the
one 48-hour constant in the codebase (`shared.constants.RANKING_PERSONAL_EVENT_WINDOW`) stays
the single source of it (AD-8) — this module never hard-codes "48".
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from domain.timezones import read_wall_clock
from shared.constants import DEFAULT_DIGEST_TIMEZONE


def _zone_for(zone_name: str) -> ZoneInfo:
    """The zone, falling back to UTC when the name is not one the platform knows.

    **A bad zone must not take the user's digest down.** The zone is validated at write
    time; an unknown name is hand-edited data, and the failure mode is one horizon
    computed in UTC rather than a 500 for the whole composition.
    """
    try:
        return ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo(DEFAULT_DIGEST_TIMEZONE)


def local_horizon(*, now: datetime, zone_name: str, window: timedelta) -> datetime:
    """The instant `window` ahead of `now`, drawn in the user's own zone.

    **The wall clock is advanced, not the instant.** `now` is read in the user's zone, the
    naive local reading is advanced by `window`, and the result is resolved back to an
    instant in that same zone. Advancing the *instant* instead would give a UTC horizon,
    which is 47 local hours on a spring-forward day and 49 on a fall-back day.

    **A DST gap resolves forward, and a fold resolves to the first occurrence.**
    `read_wall_clock` decides both, and this module does not second-guess it: a horizon is
    a bound on "soon", and the exact instant of a 48-hour-later wall clock is not worth a
    rule of its own. The `fold=0` reading is the one the rest of the codebase uses.

    **The result is an aware instant**, truncated to whole seconds by `read_wall_clock`,
    so it compares cleanly against an event's `start_time_utc`.
    """
    zone = _zone_for(zone_name)
    # `fold=0` is explicit because the wall clock being advanced is a *reading*, not an
    # instant: a `fold=1` reading would name the second of two ambiguous local times,
    # and `read_wall_clock` resolves folds at `fold=0` anyway.
    local_now = now.astimezone(zone).replace(tzinfo=None, fold=0)
    horizon_local = local_now + window
    instant, _dst_cap = read_wall_clock(horizon_local, str(zone))
    return instant


__all__ = ["local_horizon"]
