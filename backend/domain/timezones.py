"""Timezone tiers for extracted event times (FR-60, AD-6). Stdlib only.

`resolve_tz` turns a start time as a source wrote it, plus whatever zone information exists,
into a UTC instant, an IANA zone name and a `tz_inference_confidence`, or a rejection. The
cases (rows A1-C2) and their scores are in run-eventpulse24-011/plan.md; the scores and DST caps
live in `shared.constants`.

Rules that hold everywhere:
- Instants are truncated to whole seconds.
- A UTC instant (`Z` / `+00:00`) is absolute: it is never compared with a zone's offset.
- When two explicit claims disagree, the more specific one (an IANA zone over an offset) sets
  the instant and the event goes to review.
- DST caps apply only when a naive wall-clock time is read in a zone: a time that occurs twice
  (fold) takes its first occurrence; a time that doesn't exist (gap) keeps zoneinfo's `fold=0`
  reading. Both lower the confidence.
- `start_time_local` is derived from the UTC instant and the zone, so it always converts back.
- A naive time with no explicit zone falls back through what we *hold* about the place, in
  descending order of how specific the evidence is: the venue's registered zone (C1), then
  the source's city zone (C1b). Both are read with `read_wall_clock`, so both carry the DST
  caps; the city zone scores lower because a city is a weaker claim than an address.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from domain.confidence import Gate, tz_gate
from domain.errors import InvalidTimezoneError
from shared.constants import (
    TZ_CAP_DST_FOLD,
    TZ_CAP_DST_GAP,
    TZ_SCORE_CITY_ZONE,
    TZ_SCORE_CONFLICT,
    TZ_SCORE_EXPLICIT,
    TZ_SCORE_FIXED_ZONE,
    TZ_SCORE_VENUE_REGISTRY,
)

UTC_ZONE = "UTC"
LOCAL_FORMAT = "%Y-%m-%dT%H:%M:%S"

# IANA geographic areas. Names outside them (EST, localtime, Factory, posixrules, ...) load in
# zoneinfo but aren't zones an event can happen in.
PRIMARY_AREAS = frozenset(
    {
        "Africa",
        "America",
        "Antarctica",
        "Arctic",
        "Asia",
        "Atlantic",
        "Australia",
        "Europe",
        "Indian",
        "Pacific",
    }
)
UTC_ALIASES = frozenset(
    {"UTC", "Etc/UTC", "Etc/UCT", "Etc/Universal", "Etc/Zulu", "Etc/GMT", "Etc/GMT0"}
    | {"Etc/GMT+0", "Etc/GMT-0", "Etc/Greenwich"}
)
# Legacy North American links (tzdata `backward`) mapped to their targets. Other legacy links
# inside a primary area (e.g. Asia/Calcutta) are kept as given: identity compares instants.
LEGACY_ALIASES = {
    "US/Alaska": "America/Anchorage",
    "US/Aleutian": "America/Adak",
    "US/Arizona": "America/Phoenix",
    "US/Central": "America/Chicago",
    "US/East-Indiana": "America/Indiana/Indianapolis",
    "US/Eastern": "America/New_York",
    "US/Hawaii": "Pacific/Honolulu",
    "US/Indiana-Starke": "America/Indiana/Knox",
    "US/Michigan": "America/Detroit",
    "US/Mountain": "America/Denver",
    "US/Pacific": "America/Los_Angeles",
    "US/Samoa": "Pacific/Pago_Pago",
    "Canada/Atlantic": "America/Halifax",
    "Canada/Central": "America/Winnipeg",
    "Canada/Eastern": "America/Toronto",
    "Canada/Mountain": "America/Edmonton",
    "Canada/Newfoundland": "America/St_Johns",
    "Canada/Pacific": "America/Vancouver",
    "Canada/Saskatchewan": "America/Regina",
    "Canada/Yukon": "America/Whitehorse",
}
# Etc/GMT±N carries an inverted sign: Etc/GMT+5 is UTC-5. Valid offsets are UTC-12 .. UTC+14.
_ETC_GMT = re.compile(r"Etc/GMT([+-])(\d{1,2})")
MIN_OFFSET_HOURS, MAX_OFFSET_HOURS = -12, 14


class Tier(StrEnum):
    FULL = "full"  # the source supplied a zone or an exact instant
    PARTIAL = "partial"  # naive time, zone from the venue registry
    NONE = "none"  # nothing to resolve a zone from


class RejectReason(StrEnum):
    TZ_UNRESOLVABLE = "tz_unresolvable"
    OFFSET_WITHOUT_IANA_ZONE = "offset_without_iana_zone"


@dataclass(frozen=True)
class TzResolution:
    tier: Tier
    zone: str  # canonical IANA name, or "UTC"
    start_utc: datetime
    end_utc: datetime | None
    start_time_local: str  # start_utc read in `zone`, no offset, no microseconds
    confidence: Decimal
    reason: str  # which table row produced it, for audit and review

    @property
    def gate(self) -> Gate:
        return tz_gate(self.confidence)


@dataclass(frozen=True)
class TzRejection:
    reason: RejectReason


def canonical_zone(name: str | None) -> str | None:
    """The canonical IANA zone for `name`, "UTC" for UTC aliases, or None if it isn't valid."""
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    if name in UTC_ALIASES:
        return UTC_ZONE
    name = LEGACY_ALIASES.get(name, name)
    etc = _ETC_GMT.fullmatch(name)
    if etc:
        hours = -int(etc[2]) if etc[1] == "+" else int(etc[2])
        if not MIN_OFFSET_HOURS <= hours <= MAX_OFFSET_HOURS:
            return None
    elif name.split("/", 1)[0] not in PRIMARY_AREAS or "/" not in name:
        return None
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None
    return name


def offset_zone(offset: timedelta) -> str | None:
    """The IANA fixed zone for a whole-hour offset in range ("UTC" for zero), else None."""
    seconds = offset.total_seconds()
    if seconds % 3600:
        return None
    hours = int(seconds // 3600)
    if not MIN_OFFSET_HOURS <= hours <= MAX_OFFSET_HOURS:
        return None
    if hours == 0:
        return UTC_ZONE
    return f"Etc/GMT{'-' if hours > 0 else '+'}{abs(hours)}"


def to_instant(value: datetime) -> datetime:
    """An aware datetime as UTC, truncated to whole seconds."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise TypeError("expected an aware datetime")
    return value.astimezone(UTC).replace(microsecond=0)


def read_wall_clock(local: datetime, zone: str) -> tuple[datetime, Decimal | None]:
    """Read a naive wall-clock time in `zone`: the UTC instant plus a DST cap, if any.

    Detection: if `fold=0` and `fold=1` give different offsets the time is at a transition; a
    round trip through UTC that comes back different means a gap, otherwise it's a fold.
    """
    tz = ZoneInfo(zone)
    early = local.replace(tzinfo=tz, fold=0)
    late = local.replace(tzinfo=tz, fold=1)
    instant = to_instant(early)
    if early.utcoffset() == late.utcoffset():
        return instant, None
    back = instant.astimezone(tz).replace(tzinfo=None)
    return instant, TZ_CAP_DST_GAP if back != local.replace(microsecond=0) else TZ_CAP_DST_FOLD


def _offset_at(zone: str, instant: datetime) -> timedelta:
    return instant.astimezone(ZoneInfo(zone)).utcoffset()


def _capped(score: Decimal, *caps: Decimal | None) -> Decimal:
    return min([score, *(cap for cap in caps if cap is not None)])


def resolve_tz(
    start: datetime,
    *,
    source_zone: str | None = None,
    venue_tz: str | None = None,
    city_tz: str | None = None,
    end: datetime | None = None,
) -> TzResolution | TzRejection:
    """Resolve an event's start (and end) per the FR-60 table.

    `start` / `end` are naive (a wall-clock time) or aware with a fixed offset, exactly as the
    source gave them. An invalid `source_zone` is ignored; an invalid `venue_tz` raises, because
    the venue registry validates its zones on write.

    **An invalid `city_tz` is ignored rather than raised, unlike `venue_tz`.** The registry
    guarantees a venue's zone, so a bad one there is a broken invariant worth stopping for. A
    source's `city_tz` is set by provisioning, and a bad one should cost that one city its
    date-only events — a state the product already shows honestly — not raise inside the
    ingest loop and take every other candidate in the run down with it.
    """
    venue = None
    if venue_tz is not None:
        venue = canonical_zone(venue_tz)
        if venue is None:
            raise InvalidTimezoneError(details={"venue_tz": venue_tz})
    city = canonical_zone(city_tz)
    source = canonical_zone(source_zone)
    offset = start.utcoffset() if start.tzinfo is not None else None
    wall = start.replace(tzinfo=None)

    read_from_wall = False  # was the instant computed by reading a wall-clock time in `zone`?
    cap = None
    if source is not None:
        zone, tier = source, Tier.FULL
        if offset is None or (offset and _offset_at(source, to_instant(start)) != offset):
            instant, cap = read_wall_clock(wall, source)
            read_from_wall = True
            score, reason = (
                (TZ_SCORE_EXPLICIT, "A1") if offset is None else (TZ_SCORE_CONFLICT, "A2")
            )
        else:  # UTC instant, or an offset the zone agrees with: exact
            instant, score, reason = to_instant(start), TZ_SCORE_EXPLICIT, "A1"
        if venue is not None and _offset_at(venue, instant) != _offset_at(source, instant):
            score, reason = min(score, TZ_SCORE_CONFLICT), "A3"
    elif offset is not None:
        tier = Tier.FULL
        if not offset:  # a UTC instant
            instant = to_instant(start)
            zone, score, reason = (
                (venue, TZ_SCORE_EXPLICIT, "U1")
                if venue is not None
                else (UTC_ZONE, TZ_SCORE_FIXED_ZONE, "U2")
            )
        elif venue is not None:
            if _offset_at(venue, to_instant(start)) == offset:
                zone, instant, score, reason = venue, to_instant(start), TZ_SCORE_EXPLICIT, "B1"
            else:
                zone, score, reason = venue, TZ_SCORE_CONFLICT, "B2"
                instant, cap = read_wall_clock(wall, venue)
                read_from_wall = True
        else:
            zone = offset_zone(offset)
            if zone is None:
                return TzRejection(RejectReason.OFFSET_WITHOUT_IANA_ZONE)
            instant, score, reason = to_instant(start), TZ_SCORE_FIXED_ZONE, "B3"
    elif venue is not None:
        zone, tier, score, reason = venue, Tier.PARTIAL, TZ_SCORE_VENUE_REGISTRY, "C1"
        instant, cap = read_wall_clock(wall, venue)
        read_from_wall = True
    elif city is not None:
        # Only reachable with no source zone, no offset and no venue — the precedence is the
        # shape of this chain, not a rule someone has to remember to apply.
        zone, tier, score, reason = city, Tier.PARTIAL, TZ_SCORE_CITY_ZONE, "C1b"
        instant, cap = read_wall_clock(wall, city)
        read_from_wall = True
    else:
        return TzRejection(RejectReason.TZ_UNRESOLVABLE)

    end_utc, end_cap = None, None
    if end is not None:
        if end.tzinfo is None or read_from_wall:
            end_utc, end_cap = read_wall_clock(end.replace(tzinfo=None), zone)
        else:
            end_utc = to_instant(end)

    return TzResolution(
        tier=tier,
        zone=zone,
        start_utc=instant,
        end_utc=end_utc,
        start_time_local=instant.astimezone(ZoneInfo(zone)).strftime(LOCAL_FORMAT),
        confidence=_capped(score, cap, end_cap),
        reason=reason,
    )
