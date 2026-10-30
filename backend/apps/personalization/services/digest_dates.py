"""The user's local calendar day — one rule, shared by the writer and the reader.

**Why this is a module and not a private helper.** The composition service *writes* a
digest under a local date, and the read API *looks for* a digest under a local date. If
those two dates were computed by two copies of the same rule, the read could look for a
day the write never made — and the symptom would be a user with three cards on their
digest being told "nothing today". The boundary is exactly what the DST test pins, so it
is the last place for two rules to drift.

So there is one function, and both sides call it.

**By conversion, not by arithmetic.** `now.astimezone(zone).date()` is the user's day.
Adding 24 hours to a UTC date would be a different day for most of the world, and a DST
transition would break it twice a year.

**An unknown zone falls back to UTC rather than raising.** The zone is validated at
write time by the onboarding command, so an unknown name means hand-edited data — not
that the composition should fail. And the failure mode is deliberate: a composition that
raised would leave the user with **no digest at all**, which is worse than a digest whose
day is computed in the fallback zone. The failure mode is a wrong day, not a missing card.

Design: .specs-fire/intents/pulse-digest-and-trust/work-items/
digest-read-api-design.md (decision D4b).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.constants import DEFAULT_DIGEST_TIMEZONE


def local_date_for(*, now: datetime, zone_name: str) -> date:
    """The user's local calendar day for `now` in `zone_name`.

    **The zone is a string, not a preference.** The function is a pure function of the
    two things it needs — the instant and the zone — so it can be tested without a
    database, and it does not know what a `DigestPreference` is.

    **The zone is the user's, not the server's.** "Today" means different things in Tokyo
    and Los Angeles, and the digest must be able to say which day it meant (AD-6).
    """
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo(DEFAULT_DIGEST_TIMEZONE)
    return now.astimezone(zone).date()


__all__ = ["local_date_for"]
