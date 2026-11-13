"""The Source Registry read, and the trust band it renders (FR-13, FR-16).

**What these tests hold.**

1. **The four groups are FR-23's Source Badge types, in the mockup's order**, and all four
   are always present — even when the registry is empty. A group that appeared and
   disappeared as the data changed would make the screen's shape depend on the data.
2. **The trust band is the server's number, banded on inclusive lower bounds.** 0.50 — the
   prior a never-scored source sits at — is band 3, and an exact boundary lands in the
   higher band. This is `domain.reliability.source_trust_band`, which is *not*
   `domain.ranking.score_bucket`: a source's trust and an event's confidence are different
   questions.
3. **Nothing is fabricated and nothing is hidden.** A paused source is still in the
   registry (FR-16 says escalation "never pauses, hides or removes" — but an operator may
   pause one, and the screen's job is transparency). A source with no city shows no city
   rather than an empty-looking row.
"""

from decimal import Decimal

import pytest

from apps.ingestion.models import AcquisitionMethod, Source
from apps.ingestion.services.source_badges import (
    SOURCE_BADGE_AGGREGATOR,
    SOURCE_BADGE_COMMUNITY,
    SOURCE_BADGE_CRAWLED,
    SOURCE_BADGE_OFFICIAL,
)
from apps.ingestion.services.source_registry_read import (
    SOURCE_GROUP_ORDER,
    read_source_registry,
)
from domain.reliability import reliability_score, source_trust_band
from shared.db import CATALOG
from tests.ingestion.factories import SourceFactory

pytestmark = pytest.mark.django_db(databases=[CATALOG])


# ── The trust band ────────────────────────────────────────────────────────────────


def test_the_prior_is_band_three():
    """A source nobody has observed anything about is neither trusted nor distrusted.

    Banding it at 1 would call every un-scored source a bad one on the strength of no
    evidence at all, which is the exact thing the prior exists to prevent.
    """
    assert source_trust_band(reliability_score(0, 0)) == 3
    assert source_trust_band(Decimal("0.50")) == 3


def test_an_exact_boundary_lands_in_the_higher_band():
    """`0.80` is a 5, not a 4. `0.50` is a 3, not a 2.

    The score is a `Decimal`, so `Decimal("0.80")` is *exactly* the boundary and there is
    no float rounding to argue about. The bands are inclusive lower bounds, so the
    comparison is `>=`.
    """
    assert source_trust_band(Decimal("0.80")) == 5
    assert source_trust_band(Decimal("0.65")) == 4
    assert source_trust_band(Decimal("0.35")) == 2


@pytest.mark.parametrize(
    ("score", "band"),
    [
        (Decimal("0.00"), 1),
        (Decimal("0.32"), 1),
        (Decimal("0.34"), 1),
        (Decimal("0.35"), 2),
        (Decimal("0.49"), 2),
        (Decimal("0.50"), 3),
        (Decimal("0.64"), 3),
        (Decimal("0.65"), 4),
        (Decimal("0.79"), 4),
        (Decimal("0.80"), 5),
        (Decimal("1.00"), 5),
    ],
)
def test_the_bands_are_inclusive_lower_bounds(score, band):
    assert source_trust_band(score) == band


def test_a_score_outside_the_unit_interval_is_refused():
    """A caller passing something else has a bug, and a band for it would be a
    plausible-looking wrong answer."""
    with pytest.raises(ValueError):
        source_trust_band(Decimal("1.01"))
    with pytest.raises(ValueError):
        source_trust_band(Decimal("-0.01"))


# ── The registry read ─────────────────────────────────────────────────────────────


def test_the_four_groups_are_the_source_badge_types_in_order():
    assert SOURCE_GROUP_ORDER == (
        SOURCE_BADGE_OFFICIAL,
        SOURCE_BADGE_COMMUNITY,
        SOURCE_BADGE_AGGREGATOR,
        SOURCE_BADGE_CRAWLED,
    )


def test_an_empty_registry_still_has_four_groups():
    """The screen's shape must not depend on which groups happen to have sources.

    A group that vanished when its last source went would make the layout jump.
    """
    groups = read_source_registry()

    assert [group.badge for group in groups] == list(SOURCE_GROUP_ORDER)
    assert all(group.sources == () for group in groups)


def test_a_source_lands_in_the_group_its_badge_names():
    source = SourceFactory(
        source_type=Source.SourceType.VENUE,
        acquisition_method=AcquisitionMethod.RSS,
    )

    groups = {group.badge: group for group in read_source_registry()}

    assert [s.id for s in groups[SOURCE_BADGE_OFFICIAL].sources] == [source.id]


def test_a_crawled_source_is_a_crawled_group():
    """The badge is a function of the source type *and* how the facts were obtained."""
    source = SourceFactory(
        source_type=Source.SourceType.VENUE,
        acquisition_method=AcquisitionMethod.CRAWL,
    )

    groups = {group.badge: group for group in read_source_registry()}

    assert [s.id for s in groups[SOURCE_BADGE_CRAWLED].sources] == [source.id]


def test_sources_are_ordered_by_name_within_a_group():
    SourceFactory(name="Zebra Hall")
    SourceFactory(name="Alpha Hall")
    SourceFactory(name="Middling Hall")

    groups = read_source_registry()
    official = next(g for g in groups if g.badge == SOURCE_BADGE_OFFICIAL)

    assert [s.name for s in official.sources] == ["Alpha Hall", "Middling Hall", "Zebra Hall"]


def test_a_paused_source_is_still_in_the_registry():
    """**Transparency is the screen's whole job.**

    FR-16 says escalation "never pauses, hides or removes" a source — but an operator can
    pause one. A paused source is still a source the user has seen events from, so hiding
    it would hide the very thing the screen exists to reveal.
    """
    source = SourceFactory(status=Source.Status.PAUSED)

    groups = {group.badge: group for group in read_source_registry()}
    official = groups[SOURCE_BADGE_OFFICIAL]

    assert source.id in [s.id for s in official.sources]
    assert next(s for s in official.sources if s.id == source.id).is_paused is True


def test_an_active_source_is_not_marked_paused():
    source = SourceFactory(status=Source.Status.ACTIVE)

    groups = {group.badge: group for group in read_source_registry()}
    official = groups[SOURCE_BADGE_OFFICIAL]

    assert next(s for s in official.sources if s.id == source.id).is_paused is False


def test_a_never_scored_source_reads_at_the_prior():
    """A source with no `reliability_score` is not zero — it is the prior."""
    source = SourceFactory(reliability_score=None)

    groups = {group.badge: group for group in read_source_registry()}
    official = groups[SOURCE_BADGE_OFFICIAL]
    row = next(s for s in official.sources if s.id == source.id)

    assert row.reliability == Decimal("0.50")
    assert row.trust_band == 3


def test_a_source_with_no_city_reports_no_city():
    """A blank city is a real state, not an empty string to render."""
    source = SourceFactory(city="")

    groups = {group.badge: group for group in read_source_registry()}
    official = groups[SOURCE_BADGE_OFFICIAL]

    assert next(s for s in official.sources if s.id == source.id).city == ""


def test_a_source_with_a_city_reports_it():
    source = SourceFactory(city="Lisbon")

    groups = {group.badge: group for group in read_source_registry()}
    official = groups[SOURCE_BADGE_OFFICIAL]

    assert next(s for s in official.sources if s.id == source.id).city == "Lisbon"
