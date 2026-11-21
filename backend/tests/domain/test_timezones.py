"""Timezone tiers (FR-60, AD-6): every row of the plan's table, DST, zone validity."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from domain.confidence import Gate
from domain.errors import InvalidTimezoneError
from domain.timezones import (
    LEGACY_ALIASES,
    RejectReason,
    Tier,
    TzRejection,
    canonical_zone,
    offset_zone,
    read_wall_clock,
    resolve_tz,
    to_instant,
)
from shared.constants import TZ_SCORE_CITY_ZONE

NY, LA = "America/New_York", "America/Los_Angeles"


def wall(text: str) -> datetime:
    """A naive wall-clock time, as a source without a zone writes it."""
    return datetime.fromisoformat(text)


WALL = wall("2026-11-05T19:30")  # a Thursday evening, after the 2026-11-01 DST end
NY_INSTANT = datetime(2026, 11, 6, 0, 30, tzinfo=UTC)  # 19:30 EST
LA_INSTANT = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)  # 19:30 PST


def offset(hours: float) -> timezone:
    return timezone(timedelta(hours=hours))


def at(value: datetime, hours: float) -> datetime:
    return value.replace(tzinfo=offset(hours))


# --- The table ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "source_zone", "venue_tz", "row", "zone", "instant", "confidence", "gate"),
    [
        (WALL, NY, None, "A1", NY, NY_INSTANT, "1.00", Gate.PUBLISH),
        (at(WALL, -5), NY, None, "A1", NY, NY_INSTANT, "1.00", Gate.PUBLISH),
        (NY_INSTANT, NY, None, "A1", NY, NY_INSTANT, "1.00", Gate.PUBLISH),
        (WALL, NY, NY, "A1", NY, NY_INSTANT, "1.00", Gate.PUBLISH),
        (at(WALL, -4), NY, None, "A2", NY, NY_INSTANT, "0.60", Gate.IN_REVIEW),
        (WALL, LA, NY, "A3", LA, LA_INSTANT, "0.60", Gate.IN_REVIEW),
        (NY_INSTANT, None, NY, "U1", NY, NY_INSTANT, "1.00", Gate.PUBLISH),
        (NY_INSTANT, None, None, "U2", "UTC", NY_INSTANT, "0.85", Gate.PUBLISH_FLAGGED),
        (at(WALL, -5), None, NY, "B1", NY, NY_INSTANT, "1.00", Gate.PUBLISH),
        (at(WALL, -8), None, NY, "B2", NY, NY_INSTANT, "0.60", Gate.IN_REVIEW),
        (at(WALL, -8), None, None, "B3", "Etc/GMT+8", LA_INSTANT, "0.85", Gate.PUBLISH_FLAGGED),
        (WALL, None, NY, "C1", NY, NY_INSTANT, "0.95", Gate.PUBLISH),
    ],
)
def test_resolve_tz_table_row(start, source_zone, venue_tz, row, zone, instant, confidence, gate):
    result = resolve_tz(start, source_zone=source_zone, venue_tz=venue_tz)

    assert (result.reason, result.zone, result.start_utc) == (row, zone, instant)
    assert result.confidence == Decimal(confidence)
    assert result.gate is gate


@pytest.mark.parametrize(
    ("row", "source_zone", "venue_tz", "tier"),
    [("A1", NY, None, Tier.FULL), ("U2", None, None, Tier.FULL), ("C1", None, NY, Tier.PARTIAL)],
)
def test_resolve_tz_tier(row, source_zone, venue_tz, tier):
    start = NY_INSTANT if row == "U2" else WALL
    assert resolve_tz(start, source_zone=source_zone, venue_tz=venue_tz).tier is tier


@pytest.mark.parametrize(
    ("start", "reason"),
    [
        (at(WALL, 5.5), RejectReason.OFFSET_WITHOUT_IANA_ZONE),  # B4: not a whole hour
        (at(WALL, -13), RejectReason.OFFSET_WITHOUT_IANA_ZONE),  # B4: out of range
        (WALL, RejectReason.TZ_UNRESOLVABLE),  # C2
    ],
    ids=["B4-half-hour", "B4-out-of-range", "C2"],
)
def test_resolve_tz_rejections(start, reason):
    assert resolve_tz(start) == TzRejection(reason)


def test_resolve_tz_utc_instant_with_source_zone_is_not_a_conflict():
    # A UTC instant is absolute: never compared with the zone's (non-zero) offset.
    result = resolve_tz(NY_INSTANT, source_zone="US/Eastern")

    assert (result.reason, result.zone, result.confidence) == ("A1", NY, Decimal("1.00"))
    assert result.start_time_local == "2026-11-05T19:30:00"


def test_resolve_tz_invalid_source_zone_is_ignored():
    result = resolve_tz(WALL, source_zone="Mars/Olympus_Mons", venue_tz=NY)

    assert result.reason == "C1"


def test_resolve_tz_invalid_venue_tz_raises():
    with pytest.raises(InvalidTimezoneError) as excinfo:
        resolve_tz(WALL, venue_tz="EST")

    assert excinfo.value.code == "invalid_timezone"


def test_resolve_tz_truncates_to_whole_seconds():
    result = resolve_tz(NY_INSTANT.replace(microsecond=999_999), venue_tz=NY)

    assert result.start_utc == NY_INSTANT


@pytest.mark.parametrize(
    ("start", "source_zone", "venue_tz"),
    [
        (WALL, NY, None),
        (at(WALL, -4), NY, None),
        (WALL, LA, NY),
        (at(WALL, -8), None, NY),
        (at(WALL, -8), None, None),
        (NY_INSTANT, None, None),
        (wall("2026-03-08T02:30"), None, NY),
    ],
)
def test_start_time_local_round_trips_to_start_utc(start, source_zone, venue_tz):
    result = resolve_tz(start, source_zone=source_zone, venue_tz=venue_tz)
    local = datetime.fromisoformat(result.start_time_local)

    assert local.replace(tzinfo=ZoneInfo(result.zone)).astimezone(UTC) == result.start_utc


# --- DST (America/New_York, 2026) -------------------------------------------------------------

GAP = wall("2026-03-08T02:30")  # doesn't exist: clocks jump 02:00 -> 03:00
FOLD = wall("2026-11-01T01:30")  # occurs twice: 01:30 EDT, then 01:30 EST


def test_read_wall_clock_gap_caps_into_review():
    instant, cap = read_wall_clock(GAP, NY)

    assert cap == Decimal("0.65")
    assert instant == datetime(2026, 3, 8, 7, 30, tzinfo=UTC)  # fold=0: read with EST


def test_read_wall_clock_fold_takes_first_occurrence_and_flags():
    instant, cap = read_wall_clock(FOLD, NY)

    assert cap == Decimal("0.80")
    assert instant == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)  # 01:30 EDT


def test_read_wall_clock_ordinary_time_has_no_cap():
    assert read_wall_clock(WALL, NY) == (NY_INSTANT, None)


@pytest.mark.parametrize(
    ("start", "confidence", "gate"),
    [(GAP, "0.65", Gate.IN_REVIEW), (FOLD, "0.80", Gate.PUBLISH_FLAGGED)],
    ids=["gap", "fold"],
)
def test_resolve_tz_naive_dst_time_is_capped(start, confidence, gate):
    result = resolve_tz(start, venue_tz=NY)

    assert (result.confidence, result.gate) == (Decimal(confidence), gate)


def test_resolve_tz_offset_in_a_fold_is_exact_and_uncapped():
    # The offset disambiguates the fold, so no cap: caps apply only to naive times.
    second_occurrence = at(FOLD, -5)  # 01:30 EST

    result = resolve_tz(second_occurrence, venue_tz=NY)

    assert (result.reason, result.confidence) == ("B1", Decimal("1.00"))
    assert result.start_utc == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)


# --- End time ---------------------------------------------------------------------------------


def test_resolve_tz_naive_end_read_in_same_zone():
    result = resolve_tz(WALL, venue_tz=NY, end=WALL + timedelta(hours=3))

    assert result.end_utc == NY_INSTANT + timedelta(hours=3)


def test_resolve_tz_end_in_dst_gap_lowers_confidence():
    result = resolve_tz(wall("2026-03-07T22:00"), venue_tz=NY, end=GAP)

    assert result.confidence == Decimal("0.65")


def test_resolve_tz_aware_end_is_exact_when_start_was():
    end = at(WALL + timedelta(hours=2), -5)

    result = resolve_tz(at(WALL, -5), venue_tz=NY, end=end)

    assert result.end_utc == NY_INSTANT + timedelta(hours=2)


def test_resolve_tz_conflicting_start_reads_end_in_the_chosen_zone_too():
    # B2: the venue tz wins for the start, so the end's wall clock is read in it as well.
    result = resolve_tz(at(WALL, -8), venue_tz=NY, end=at(WALL + timedelta(hours=2), -8))

    assert result.end_utc == NY_INSTANT + timedelta(hours=2)


# --- Zone validity ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "EST",
        "EST5EDT",
        "localtime",
        "Factory",
        "posixrules",
        "Nope/Zone",
        "America/",
        "Etc/GMT+13",
        "Etc/GMT-15",
        "Etc/Unknown",
        "",
        "   ",
        None,
        "../etc/passwd",
    ],
)
def test_canonical_zone_rejects(name):
    assert canonical_zone(name) is None


@pytest.mark.parametrize(
    ("name", "canonical"),
    [
        ("America/New_York", NY),
        (" Europe/Paris ", "Europe/Paris"),
        ("US/Eastern", NY),
        ("Canada/Newfoundland", "America/St_Johns"),
        ("Asia/Calcutta", "Asia/Calcutta"),  # in-area legacy link: kept as given
        ("UTC", "UTC"),
        ("Etc/UTC", "UTC"),
        ("Etc/Zulu", "UTC"),
        ("Etc/GMT+0", "UTC"),
        ("Etc/GMT+12", "Etc/GMT+12"),
        ("Etc/GMT-14", "Etc/GMT-14"),
    ],
)
def test_canonical_zone_accepts(name, canonical):
    assert canonical_zone(name) == canonical


@pytest.mark.parametrize(("alias", "target"), sorted(LEGACY_ALIASES.items()))
def test_legacy_alias_targets_keep_the_same_offsets(alias, target):
    instants = [datetime(2026, month, 15, 12, tzinfo=UTC) for month in (1, 4, 7, 10)]

    assert [i.astimezone(ZoneInfo(alias)).utcoffset() for i in instants] == [
        i.astimezone(ZoneInfo(target)).utcoffset() for i in instants
    ]


@pytest.mark.parametrize(
    ("hours", "zone"),
    [(-8, "Etc/GMT+8"), (5, "Etc/GMT-5"), (0, "UTC"), (-12, "Etc/GMT+12"), (14, "Etc/GMT-14")],
)
def test_offset_zone_inverts_the_sign(hours, zone):
    assert offset_zone(timedelta(hours=hours)) == zone
    assert datetime(2026, 1, 1, tzinfo=ZoneInfo(zone)).utcoffset() == timedelta(hours=hours)


@pytest.mark.parametrize("hours", [5.5, 9.75, -13, 15])
def test_offset_zone_none_without_an_iana_fixed_zone(hours):
    assert offset_zone(timedelta(hours=hours)) is None


def test_to_instant_rejects_naive():
    with pytest.raises(TypeError):
        to_instant(WALL)


# --- C1b: the source's city zone, the last link in the chain --------------------------------
#
# `ingest_item._venue_for` never creates a venue (D5), so a city with no registered venue
# resolves `venue=None` for every candidate. Without this row a freshly provisioned city
# fetches cleanly, parses cleanly and publishes nothing, forever.


def test_resolve_tz_city_zone_reads_a_naive_time_and_publishes():
    result = resolve_tz(WALL, city_tz=NY)

    assert (result.reason, result.zone, result.start_utc) == ("C1b", NY, NY_INSTANT)
    assert result.tier is Tier.PARTIAL
    assert result.confidence == TZ_SCORE_CITY_ZONE == Decimal("0.90")
    assert result.gate is Gate.PUBLISH  # publishes clean: no blanket tz_review_pending


def test_resolve_tz_city_zone_scores_below_the_venue_registry():
    # The whole justification for a separate row: a city is weaker evidence than an address.
    city = resolve_tz(WALL, city_tz=NY)
    venue = resolve_tz(WALL, venue_tz=NY)

    assert city.confidence < venue.confidence


@pytest.mark.parametrize(
    ("kwargs", "row"),
    [
        ({"source_zone": LA}, "A1"),  # an explicit zone wins
        ({"venue_tz": LA}, "C1"),  # a registered venue wins
    ],
    ids=["source-zone-beats-city", "venue-beats-city"],
)
def test_resolve_tz_city_zone_yields_to_more_specific_evidence(kwargs, row):
    result = resolve_tz(WALL, city_tz=NY, **kwargs)

    assert result.reason == row
    assert result.zone == LA  # the city zone did not decide the zone either


@pytest.mark.parametrize(
    ("start", "row"),
    [(NY_INSTANT, "U2"), (at(WALL, -8), "B3")],
    ids=["utc-instant", "fixed-offset"],
)
def test_resolve_tz_an_instant_or_an_offset_ignores_the_city_zone(start, row):
    # A time that already carries its own claim never falls through to what we hold.
    result = resolve_tz(start, city_tz=NY)

    assert result.reason == row
    assert result.zone != NY


@pytest.mark.parametrize(
    ("start", "confidence", "gate"),
    [(GAP, "0.65", Gate.IN_REVIEW), (FOLD, "0.80", Gate.PUBLISH_FLAGGED)],
    ids=["gap", "fold"],
)
def test_resolve_tz_city_zone_carries_the_dst_caps(start, confidence, gate):
    # The caps are what keeps 0.90 honest: a reading that genuinely needs a human still gets
    # one, without flagging every event in every newly provisioned city.
    result = resolve_tz(start, city_tz=NY)

    assert result.reason == "C1b"
    assert result.confidence == Decimal(confidence)
    assert result.gate is gate


def test_resolve_tz_city_zone_reads_the_end_in_the_same_zone():
    result = resolve_tz(WALL, city_tz=NY, end=wall("2026-11-05T22:00"))

    assert result.end_utc == datetime(2026, 11, 6, 3, 0, tzinfo=UTC)


def test_resolve_tz_invalid_city_tz_is_ignored_not_raised():
    # Unlike venue_tz: a bad city zone costs that city its date-only events rather than
    # raising inside the ingest loop and taking the rest of the run's candidates with it.
    assert resolve_tz(WALL, city_tz="Mars/Olympus_Mons") == TzRejection(
        RejectReason.TZ_UNRESOLVABLE
    )
    assert resolve_tz(WALL, city_tz="EST") == TzRejection(RejectReason.TZ_UNRESOLVABLE)


def test_resolve_tz_city_tz_is_canonicalized_like_every_other_zone():
    assert resolve_tz(WALL, city_tz="US/Eastern").zone == NY


@pytest.mark.parametrize("city_tz", [None, ""])
def test_resolve_tz_without_a_city_zone_is_exactly_todays_behaviour(city_tz):
    # The additive guarantee, asserted rather than assumed: every source that predates this
    # field carries no city_tz, and nothing about its resolution moves.
    assert resolve_tz(WALL, city_tz=city_tz) == TzRejection(RejectReason.TZ_UNRESOLVABLE)
    assert resolve_tz(WALL, venue_tz=NY, city_tz=city_tz) == resolve_tz(WALL, venue_tz=NY)
    assert resolve_tz(WALL, source_zone=LA, city_tz=city_tz) == resolve_tz(WALL, source_zone=LA)
