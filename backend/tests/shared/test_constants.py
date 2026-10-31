"""Shared constants match the spine and load without Django."""

import os
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from domain.confidence import Gate, tz_gate
from shared.constants import (
    CONFLICT_MIN_OVERLAP,
    DEFAULT_REMINDER_PLAN,
    DUPLICATE_START_WINDOW,
    EXTRACTION_CONFIDENCE_PUBLISH,
    EXTRACTION_CONFIDENCE_REJECT,
    POSTPONEMENT_WINDOW,
    RANKING_BUCKET_2,
    RANKING_BUCKET_3,
    RANKING_BUCKET_4,
    RANKING_BUCKET_5,
    RANKING_HYSTERESIS_DELTA,
    RANKING_MAX_TAGS,
    RANKING_WEIGHT_CITY,
    RANKING_WEIGHT_CONFIDENCE,
    RANKING_WEIGHT_INTEREST,
    RANKING_WEIGHT_RECENCY,
    RANKING_WEIGHT_SUM,
    REMINDER_SLOT_OFFSET,
    SEND_KEY_SEPARATOR,
    SERIES_ID_NAMESPACE,
    TITLE_TOKEN_OVERLAP_MIN,
    TZ_CAP_DST_FOLD,
    TZ_CAP_DST_GAP,
    TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH,
    TZ_INFERENCE_CONFIDENCE_DIGEST,
    TZ_SCORE_CONFLICT,
    TZ_SCORE_EXPLICIT,
    TZ_SCORE_FIXED_ZONE,
    TZ_SCORE_VENUE_REGISTRY,
    ReminderSlot,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_confidence_gates_match_spine():
    assert EXTRACTION_CONFIDENCE_REJECT == Decimal("0.5")
    assert EXTRACTION_CONFIDENCE_PUBLISH == Decimal("0.7")
    assert TZ_INFERENCE_CONFIDENCE_DIGEST == Decimal("0.7")
    assert TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH == Decimal("0.9")


def test_series_id_namespace_is_pinned():
    assert str(SERIES_ID_NAMESPACE) == "cbd88e48-d511-4f1b-a595-2f31c0067ad4"


def test_default_reminder_plan_is_one_day_plus_one_hour():
    assert DEFAULT_REMINDER_PLAN == (ReminderSlot.ONE_DAY, ReminderSlot.ONE_HOUR)
    assert [str(slot) for slot in DEFAULT_REMINDER_PLAN] == ["1d", "1hr"]


def test_every_slot_has_an_offset():
    assert REMINDER_SLOT_OFFSET == {
        ReminderSlot.FIVE_DAYS: timedelta(days=5),
        ReminderSlot.TWO_DAYS: timedelta(days=2),
        ReminderSlot.ONE_DAY: timedelta(days=1),
        ReminderSlot.ONE_HOUR: timedelta(hours=1),
    }


def test_conflict_overlap_and_send_key_separator():
    assert CONFLICT_MIN_OVERLAP == timedelta(minutes=15)
    assert SEND_KEY_SEPARATOR == ":"


def test_duplicate_start_window_is_twenty_four_hours():
    assert DUPLICATE_START_WINDOW == timedelta(hours=24)


def test_constants_and_ids_import_without_django():
    code = (
        "import sys, shared.constants, shared.ids\n"
        "leaked = [m for m in sys.modules if m == 'django' or m.startswith('django.')]\n"
        "sys.exit('loaded Django: ' + ', '.join(leaked[:5]) if leaked else 0)\n"
    )
    env = {key: value for key, value in os.environ.items() if key != "DJANGO_SETTINGS_MODULE"}

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_identity_thresholds_match_the_prd():
    assert TITLE_TOKEN_OVERLAP_MIN == Fraction(4, 5)
    assert POSTPONEMENT_WINDOW == timedelta(days=30)


@pytest.mark.parametrize(
    ("score", "gate"),
    [
        (TZ_SCORE_EXPLICIT, Gate.PUBLISH),
        (TZ_SCORE_VENUE_REGISTRY, Gate.PUBLISH),
        (TZ_SCORE_FIXED_ZONE, Gate.PUBLISH_FLAGGED),
        (TZ_CAP_DST_FOLD, Gate.PUBLISH_FLAGGED),
        (TZ_CAP_DST_GAP, Gate.IN_REVIEW),
        (TZ_SCORE_CONFLICT, Gate.IN_REVIEW),
    ],
)
def test_each_tz_score_and_cap_lands_in_its_intended_gate(score, gate):
    assert type(score) is Decimal
    assert tz_gate(score) is gate


def test_ranking_weights_are_pinned():
    """FR-22 says a weight change without a PRD amendment is a CI-level failure.

    The published formula (0.40 preference_graph / 0.25 source_reliability /
    0.20 recency / 0.15 novelty) has two terms with no computable input in this
    codebase, so the surviving four are redistributed to still sum to 1.0. If
    any weight moves, the PRD must be amended in the same commit.
    """
    assert RANKING_WEIGHT_INTEREST == Decimal("0.45")
    assert RANKING_WEIGHT_RECENCY == Decimal("0.25")
    assert RANKING_WEIGHT_CITY == Decimal("0.20")
    assert RANKING_WEIGHT_CONFIDENCE == Decimal("0.10")
    assert RANKING_WEIGHT_SUM == Decimal("1.00")


def test_ranking_bucket_boundaries_are_pinned():
    """FR-22's boundaries, verbatim. An exact boundary takes the lower bucket."""
    assert RANKING_BUCKET_5 == Decimal("0.85")
    assert RANKING_BUCKET_4 == Decimal("0.65")
    assert RANKING_BUCKET_3 == Decimal("0.45")
    assert RANKING_BUCKET_2 == Decimal("0.25")


def test_ranking_hysteresis_delta_is_pinned():
    """EXPERIENCE.md: the bucket holds unless the raw score moves by at least 0.10."""
    assert RANKING_HYSTERESIS_DELTA == Decimal("0.10")


def test_ranking_tag_cap_is_pinned():
    assert RANKING_MAX_TAGS == 3
