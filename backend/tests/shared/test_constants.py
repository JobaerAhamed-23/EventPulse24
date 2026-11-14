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
    EVENT_REPORT_DAILY_LIMIT,
    EVENT_REPORT_WINDOW_SECONDS,
    EXTRACTION_CONFIDENCE_PUBLISH,
    EXTRACTION_CONFIDENCE_REJECT,
    FR25_CLUSTER_COSINE_THRESHOLD,
    FR25_CLUSTER_MIN_EVENTS,
    FR25_CLUSTER_WINDOW_HOURS,
    FR25_DECAY_EXPIRE_DAYS,
    FR25_DECAY_HALF_DAYS,
    FR25_EMBEDDING_DIMENSIONS,
    FR25_EMBEDDING_MODEL,
    FR25_MUTE_DURATIONS_DAYS,
    FR25_RAGE_GUARD_COUNT,
    FR25_RAGE_GUARD_SECONDS,
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
    RANKING_WEIGHT_RELIABILITY,
    RANKING_WEIGHT_SUM,
    RANKING_WEIGHTS_AMENDMENT,
    RELIABILITY_ESCALATION_SCORE,
    RELIABILITY_MIN_OBSERVATIONS,
    RELIABILITY_NEW_SOURCE_FLOOR,
    RELIABILITY_PRIOR_ALPHA,
    RELIABILITY_PRIOR_BETA,
    RELIABILITY_SPIKE_MULTIPLIER,
    REMINDER_SLOT_OFFSET,
    REPORT_CATEGORIES,
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
    """FR-22: a weight change is a PRD amendment, and the amendment is a document.

    The implemented formula (0.35 interest_overlap / 0.25 source_reliability / 0.20 recency /
    0.10 city_match / 0.10 confidence) is the published one with each component mapped to
    the term the product can compute — `source_reliability` at FR-22's published weight of
    0.25, unchanged. The mapping is recorded in the ADR named below.

    **If any weight moves, the PRD must be amended in the same commit** — and the
    amendment is not a string in this file. The next test reads the ADR itself.
    """
    assert RANKING_WEIGHT_INTEREST == Decimal("0.35")
    assert RANKING_WEIGHT_RECENCY == Decimal("0.20")
    assert RANKING_WEIGHT_CITY == Decimal("0.10")
    assert RANKING_WEIGHT_CONFIDENCE == Decimal("0.10")
    assert RANKING_WEIGHT_RELIABILITY == Decimal("0.25")
    assert RANKING_WEIGHT_SUM == Decimal("1.00")
    assert RANKING_WEIGHTS_AMENDMENT == "ADR-0025"


def test_the_ranking_weights_have_an_amendment_that_says_so():
    """The reference is not a string. It points at a document that has to agree.

    A constant that names an ADR is only an amendment if the ADR is there **and** says
    what the constant says. This test reads the ADR and checks that it lists every weight
    it claims to authorise — so "bump the weight and update the string" is not a way past
    the pin: the ADR's own table has to move too, and the ADR is a document a human reads
    and that is surfaced to users in Settings (FR-22).
    """
    adr = BACKEND_DIR.parent / "docs" / "adr" / f"{RANKING_WEIGHTS_AMENDMENT}.md"
    assert adr.exists(), (
        f"{RANKING_WEIGHTS_AMENDMENT} is named as the amendment for the ranking weights, "
        f"but there is no ADR at {adr}. A reference to a document that does not exist is "
        "not an amendment."
    )

    text = adr.read_text()

    for weight in (
        RANKING_WEIGHT_INTEREST,
        RANKING_WEIGHT_RECENCY,
        RANKING_WEIGHT_CITY,
        RANKING_WEIGHT_CONFIDENCE,
        RANKING_WEIGHT_RELIABILITY,
    ):
        assert f"{weight:.2f}" in text, (
            f"{RANKING_WEIGHTS_AMENDMENT} does not mention the weight {weight}. A weight "
            "that moved without the amendment saying so is exactly the failure FR-22 "
            "makes a CI-level failure."
        )


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


# ── FR-16: the Source Reliability Score ──────────────────────────────────────────────────


def test_the_reliability_prior_is_the_prd_beta_binomial():
    """FR-16: "a beta-binomial model with prior α=5, β=5"."""
    assert RELIABILITY_PRIOR_ALPHA == 5
    assert RELIABILITY_PRIOR_BETA == 5


def test_the_reliability_min_n_and_escalation_line_are_the_prd_numbers():
    """FR-16: "<0.3 AND >=30 observations is escalated to editorial review"."""
    assert RELIABILITY_MIN_OBSERVATIONS == 30
    assert RELIABILITY_ESCALATION_SCORE == Decimal("0.30")


def test_the_new_source_floor_is_the_prd_number():
    """FR-16: "a new source (under 30 observations) cannot have its score drop below 0.32"."""
    assert RELIABILITY_NEW_SOURCE_FLOOR == Decimal("0.32")


def test_the_new_source_floor_sits_above_the_escalation_line():
    """**Why the floor can never hide a Source that deserves review.**

    If the floor ever dropped below the escalation line, a clamped new Source could look
    escalatable while the clamp was the only thing holding its score up.
    """
    assert RELIABILITY_NEW_SOURCE_FLOOR > RELIABILITY_ESCALATION_SCORE


def test_the_new_source_floor_matches_the_posterior_after_five_or_six_failures():
    """**Where 0.32 comes from**, pinned so the derivation is not lost again.

    FR-16 calls it "the prior-posterior floor" without deriving it, and it is *not* the
    posterior at n=29 (0.13). It is the value between five straight failures (0.33) and six
    (0.31) — which is what makes "never judge a Source worse than about five strikes until
    there are 30 observations" the readable statement of the rule.
    """
    from domain.reliability import posterior_mean

    assert posterior_mean(0, 5) > RELIABILITY_NEW_SOURCE_FLOOR
    assert posterior_mean(0, 6) < RELIABILITY_NEW_SOURCE_FLOOR


def test_the_spike_multiplier_is_the_prd_number():
    """FR-16: "a 3x week-over-week drop". Measured on negative rates, not scores."""
    assert RELIABILITY_SPIKE_MULTIPLIER == Decimal("3")


# ── FR-59: the report categories ─────────────────────────────────────────────────────────


def test_the_four_report_categories_are_the_prd_four():
    """FR-59: "exactly four single-select categories", and no free text."""
    assert REPORT_CATEGORIES == (
        "wrong_date_time",
        "wrong_venue",
        "does_not_exist",
        "duplicate",
    )


def test_all_three_category_vocabularies_agree():
    """**Three enums must agree and none of them can import the others.**

    `ReviewItem.ReportCategory` is in `catalog`, `EventReport.Category` in `personal`, and
    `shared` is below `apps` so it can hold neither — the same bind `LIFECYCLE_SEND_BEHAVIOUR`
    is in, solved the same way: values in `shared`, parity asserted here. Add a category to
    one and this fails rather than a report silently landing in a tally that does not exist.
    """
    from apps.ingestion.models import ReviewItem
    from apps.personalization.models import EventReport

    assert tuple(ReviewItem.ReportCategory.values) == REPORT_CATEGORIES
    assert tuple(EventReport.Category.values) == REPORT_CATEGORIES


def test_every_category_has_a_tally_column():
    """A category with no column would be counted nowhere (review-queue-model D3)."""
    from apps.ingestion.models import ReviewItem

    assert set(ReviewItem.REPORT_FIELDS) == set(REPORT_CATEGORIES)


def test_the_daily_report_limit_is_the_prd_five():
    """FR-59: "capped at 5 per user per day"."""
    assert EVENT_REPORT_DAILY_LIMIT == 5
    assert EVENT_REPORT_WINDOW_SECONDS == 24 * 60 * 60


# ── FR-25: the "Less like this" cluster ─────────────────────────────────────────────────


def test_the_cluster_cosine_threshold_is_the_fr25_number():
    """FR-25: "embedding cosine ≥0.7".

    A cluster that fires at a different cosine is a different product — one that asks
    users to mute categories they did not mean to mute. So the number is pinned.
    """
    assert FR25_CLUSTER_COSINE_THRESHOLD == Decimal("0.70")


def test_the_cluster_needs_three_distinct_events():
    """FR-25: "3 distinct events dismissed".

    Two dismissals is what a user does when a card renders wrong; three is what a user
    does when they do not want a category.
    """
    assert FR25_CLUSTER_MIN_EVENTS == 3


def test_the_cluster_window_is_twenty_four_hours():
    """FR-25: the three dismissals must fall inside a 24-hour window."""
    assert FR25_CLUSTER_WINDOW_HOURS == 24


def test_the_rage_guard_is_three_swipes_in_five_seconds():
    """FR-25: the guard against a flick being read as a preference.

    The count and the window are separate constants because they are different kinds of
    number — one counts dismissals, the other measures time — and a bare "3" at the call
    site is exactly the kind of literal AD-8 exists to prevent.
    """
    assert FR25_RAGE_GUARD_COUNT == 3
    assert FR25_RAGE_GUARD_SECONDS == 5


def test_the_decay_is_a_sixty_day_half_life_and_a_one_hundred_eighty_day_cliff():
    """FR-25: the decay has two stages, and the cliff is what makes the half-life honest.

    A half-life alone never reaches zero, so a decade-old swipe would still count for a
    sliver — and a sliver that never dies is a preference the user cannot escape.
    """
    assert FR25_DECAY_HALF_DAYS == 60
    assert FR25_DECAY_EXPIRE_DAYS == 180
    assert FR25_DECAY_EXPIRE_DAYS > FR25_DECAY_HALF_DAYS


def test_the_mute_durations_are_the_mocks_three_finite_ones():
    """FR-25: 7, 30, 90 days — and the indefinite one is a `null` expiry, not a fourth number."""
    assert FR25_MUTE_DURATIONS_DAYS == (7, 30, 90)
    assert all(isinstance(days, int) and days > 0 for days in FR25_MUTE_DURATIONS_DAYS)


def test_the_embedding_dimensions_are_the_pinned_two_hundred_and_fifty_six():
    """The spine pins 256 or 512; this is the 256 choice, written down once."""
    assert FR25_EMBEDDING_DIMENSIONS == 256


def test_the_embedding_model_is_the_pinned_name():
    """**The name is a constant because the cost row carries it.**

    A cost row that records "some model" cannot answer "what did we spend on embeddings",
    and the AI Cost Dashboard reads exactly that.
    """
    assert FR25_EMBEDDING_MODEL == "voyage-4-lite"
