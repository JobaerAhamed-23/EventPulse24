"""The dismissal cluster (FR-25): the rule that decides when to ask the user.

**What this test holds:** three distinct events inside a window, each at least 0.70 from
the newest; the rage-dismiss guard; the decay; the serendipity immunity; the prompt
firing once; and the copy being the server's own.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.personalization.models import DigestComposition, EventDismissal
from apps.personalization.services.dismissals import (
    SERENDIPITY_SLOT,
    cosine,
    record_dismissal,
)
from shared.actor import Actor
from shared.constants import (
    FR25_CLUSTER_COSINE_THRESHOLD,
    FR25_DECAY_EXPIRE_DAYS,
    FR25_DECAY_HALF_DAYS,
    FR25_EMBEDDING_DIMENSIONS,
    FR25_RAGE_GUARD_SECONDS,
)
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory
from tests.personalization.factories import DigestCompositionFactory, PulseDigestFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 6, 18, 0, tzinfo=UTC)
USER_ID = uuid4()
ACTOR = Actor.user(USER_ID)


def _unit(values: list[float]) -> list[float]:
    """A vector from a list, for the test to seed a row with.

    **The vector is padded to the stored dimension.** The column is `vector(256)`, and
    `pgvector` refuses a vector of any other width — so a test that wants to control the
    *direction* of a vector has to supply the full width, and the direction lives in the
    first few components.
    """
    padded = list(values) + [0.0] * (FR25_EMBEDDING_DIMENSIONS - len(values))
    norm = sum(value**2 for value in padded) ** 0.5
    return [value / norm for value in padded]


def _event_with_embedding(*, title: str, description: str = "", embed: bool = True) -> tuple:
    """A catalog event with a known vector, and its id.

    **The vector is written directly**, not through the embedding adapter: the rule
    under test is the cosine, and the fake adapter's hash-based vectors would make the
    similarity between two events a function of their titles rather than of the rule.

    **`embed=False` leaves the event with no vector at all** — the state the backfill
    has not reached yet.
    """
    from apps.ingestion.models import Event
    from apps.ingestion.services.embedding import event_embedding_text

    event = EventFactory(title=title, description=description)
    if embed:
        vector = _unit([1.0, 0.0, 0.0])
        Event.objects.using(CATALOG).filter(pk=event.pk).update(embedding=vector)
    return event.pk, event_embedding_text(title=title, description=description)


def _embed(event_id, values: list[float]) -> None:
    from apps.ingestion.models import Event

    Event.objects.using(CATALOG).filter(pk=event_id).update(embedding=_unit(values))


class TestCosine:
    def test_identical_vectors_are_one(self):
        vector = _unit([1.0, 2.0, 3.0])

        assert cosine(tuple(vector), tuple(vector)) == Decimal("1.000000")

    def test_orthogonal_vectors_are_zero(self):
        assert cosine((1.0, 0.0), (0.0, 1.0)) == Decimal("0.000000")

    def test_opposite_vectors_are_minus_one(self):
        assert cosine((1.0, 0.0), (-1.0, 0.0)) == Decimal("-1.000000")

    def test_mismatched_lengths_raise(self):
        """A dot product of two different lengths is not a cosine."""
        with pytest.raises(ValueError):
            cosine((1.0, 0.0), (1.0, 0.0, 0.0))

    def test_a_zero_vector_raises(self):
        """A zero vector has no direction, so its cosine is undefined."""
        with pytest.raises(ValueError):
            cosine((0.0, 0.0), (1.0, 0.0))


class TestTheCluster:
    def test_three_similar_dismissals_raise_the_prompt(self):
        first, _ = _event_with_embedding(title="Jazz one")
        second, _ = _event_with_embedding(title="Jazz two")
        third, _ = _event_with_embedding(title="Jazz three")
        for event_id in (first, second, third):
            _embed(event_id, [1.0, 0.1, 0.0])

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )
        result = record_dismissal(
            user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )

        assert result.prompt_due is True
        assert result.prompt is not None

    def test_two_dismissals_do_not_raise_the_prompt(self):
        first, _ = _event_with_embedding(title="Jazz one")
        second, _ = _event_with_embedding(title="Jazz two")

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        result = record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )

        assert result.prompt_due is False
        assert result.prompt is None

    def test_each_must_clear_the_threshold_not_just_any_pair(self):
        """Two close and one distant is not a cluster."""
        first, _ = _event_with_embedding(title="Jazz one")
        second, _ = _event_with_embedding(title="Jazz two")
        third, _ = _event_with_embedding(title="Something else")
        _embed(first, [1.0, 0.0, 0.0])
        _embed(second, [1.0, 0.05, 0.0])
        _embed(third, [0.0, 1.0, 0.0])

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )
        result = record_dismissal(
            user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )

        assert result.prompt_due is False

    def test_dismissals_outside_the_window_do_not_cluster(self):
        first, _ = _event_with_embedding(title="Jazz one")
        second, _ = _event_with_embedding(title="Jazz two")
        third, _ = _event_with_embedding(title="Jazz three")
        for event_id in (first, second, third):
            _embed(event_id, [1.0, 0.0, 0.0])

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(hours=2)
        )
        result = record_dismissal(
            user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW + timedelta(hours=25)
        )

        assert result.prompt_due is False

    def test_an_event_with_no_vector_cannot_cluster(self):
        """A missing vector is not a zero vector, so it is not comparable."""
        first, _ = _event_with_embedding(title="Jazz one")
        second, _ = _event_with_embedding(title="Jazz two")
        third, _ = _event_with_embedding(title="Jazz three", embed=False)
        _embed(first, [1.0, 0.0, 0.0])
        _embed(second, [1.0, 0.0, 0.0])

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )
        result = record_dismissal(
            user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )

        assert result.prompt_due is False


class TestTheRageDismissGuard:
    def test_three_fast_dismissals_do_not_all_advance(self):
        first, _ = _event_with_embedding(title="One")
        second, _ = _event_with_embedding(title="Two")
        third, _ = _event_with_embedding(title="Three")

        results = [
            record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW),
            record_dismissal(
                user_id=USER_ID,
                event_id=second,
                actor=ACTOR,
                now=NOW + timedelta(seconds=1),
            ),
            record_dismissal(
                user_id=USER_ID,
                event_id=third,
                actor=ACTOR,
                now=NOW + timedelta(seconds=2),
            ),
        ]

        assert [result.cluster_advanced for result in results] == [True, True, False]

    def test_the_guard_does_not_stop_the_dismissal_being_recorded(self):
        """The user really did dismiss it; the product just does not count it."""
        first, _ = _event_with_embedding(title="One")
        second, _ = _event_with_embedding(title="Two")
        third, _ = _event_with_embedding(title="Three")

        for index, event_id in enumerate((first, second, third)):
            record_dismissal(
                user_id=USER_ID,
                event_id=event_id,
                actor=ACTOR,
                now=NOW + timedelta(seconds=index),
            )

        assert EventDismissal.objects.using(PERSONAL).filter(user_id=USER_ID).count() == 3

    def test_dismissals_outside_the_rage_window_all_advance(self):
        first, _ = _event_with_embedding(title="One")
        second, _ = _event_with_embedding(title="Two")
        third, _ = _event_with_embedding(title="Three")

        results = [
            record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW),
            record_dismissal(
                user_id=USER_ID,
                event_id=second,
                actor=ACTOR,
                now=NOW + timedelta(seconds=FR25_RAGE_GUARD_SECONDS + 1),
            ),
            record_dismissal(
                user_id=USER_ID,
                event_id=third,
                actor=ACTOR,
                now=NOW + timedelta(seconds=2 * (FR25_RAGE_GUARD_SECONDS + 1)),
            ),
        ]

        assert all(result.cluster_advanced for result in results)


class TestTheSerendipityImmunity:
    def test_a_serendipity_dismissal_is_not_a_clustering_candidate(self):
        """The product put that card there deliberately; dismissing it is not a verdict."""
        digest = PulseDigestFactory(user_id=USER_ID)
        first, _ = _event_with_embedding(title="One")
        second, _ = _event_with_embedding(title="Two")
        third, _ = _event_with_embedding(title="Three")
        for event_id in (first, second, third):
            _embed(event_id, [1.0, 0.0, 0.0])

        # The third card was the serendipity card.
        for index, event_id in enumerate((first, second, third)):
            DigestCompositionFactory(
                digest_id=digest.id,
                user_id=USER_ID,
                event_id=event_id,
                slot=(SERENDIPITY_SLOT if index == 2 else DigestComposition.Slot.MUST_KNOW),
            )

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )
        result = record_dismissal(
            user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )

        assert result.prompt_due is False

    def test_the_serendipity_dismissal_is_still_recorded(self):
        digest = PulseDigestFactory(user_id=USER_ID)
        event_id, _ = _event_with_embedding(title="One")
        DigestCompositionFactory(
            digest_id=digest.id,
            user_id=USER_ID,
            event_id=event_id,
            slot=SERENDIPITY_SLOT,
        )

        record_dismissal(user_id=USER_ID, event_id=event_id, actor=ACTOR, now=NOW)

        row = EventDismissal.objects.using(PERSONAL).get(user_id=USER_ID, event_id=event_id)
        assert row.slot == SERENDIPITY_SLOT


class TestTheDecay:
    def test_a_dismissal_older_than_the_expiry_is_ignored(self):
        first, _ = _event_with_embedding(title="One")
        second, _ = _event_with_embedding(title="Two")
        third, _ = _event_with_embedding(title="Three")
        for event_id in (first, second, third):
            _embed(event_id, [1.0, 0.0, 0.0])

        old = NOW - timedelta(days=FR25_DECAY_EXPIRE_DAYS + 1)
        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=old)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW - timedelta(minutes=1)
        )
        result = record_dismissal(user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW)

        assert result.prompt_due is False

    def test_a_half_decayed_dismissal_does_not_make_three(self):
        """The decay is a half-life, not a cliff — and a half is not a whole.

        Two fresh dismissals plus one from two months ago is 2.5 dismissals' worth of
        evidence, and the rule asks for three.
        """
        first, _ = _event_with_embedding(title="One")
        second, _ = _event_with_embedding(title="Two")
        third, _ = _event_with_embedding(title="Three")
        for event_id in (first, second, third):
            _embed(event_id, [1.0, 0.0, 0.0])

        record_dismissal(
            user_id=USER_ID,
            event_id=first,
            actor=ACTOR,
            now=NOW - timedelta(days=FR25_DECAY_HALF_DAYS + 1),
        )
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW - timedelta(minutes=1)
        )
        result = record_dismissal(user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW)

        assert result.prompt_due is False

    def test_a_fresh_dismissal_after_a_decayed_one_still_clusters(self):
        """Three fresh dismissals are three, whatever came before them."""
        stale, _ = _event_with_embedding(title="Stale")
        first, _ = _event_with_embedding(title="One")
        second, _ = _event_with_embedding(title="Two")
        third, _ = _event_with_embedding(title="Three")
        for event_id in (stale, first, second, third):
            _embed(event_id, [1.0, 0.0, 0.0])

        record_dismissal(
            user_id=USER_ID,
            event_id=stale,
            actor=ACTOR,
            now=NOW - timedelta(days=FR25_DECAY_HALF_DAYS + 1),
        )
        record_dismissal(
            user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW - timedelta(minutes=3)
        )
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW - timedelta(minutes=2)
        )
        result = record_dismissal(user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW)

        assert result.prompt_due is True


class TestThePrompt:
    def test_it_fires_once_per_cluster(self):
        """The counter resets when it fires, so the same cluster cannot nag."""
        first, _ = _event_with_embedding(title="Jazz one")
        second, _ = _event_with_embedding(title="Jazz two")
        third, _ = _event_with_embedding(title="Jazz three")
        fourth, _ = _event_with_embedding(title="Jazz four")
        for event_id in (first, second, third, fourth):
            _embed(event_id, [1.0, 0.0, 0.0])

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )
        fired = record_dismissal(
            user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )
        again = record_dismissal(
            user_id=USER_ID, event_id=fourth, actor=ACTOR, now=NOW + timedelta(minutes=3)
        )

        assert fired.prompt_due is True
        assert again.prompt_due is False

    def test_the_copy_names_the_servers_own_chip_label(self):
        """A scraped title can never reach the user's screen."""
        gallery, _ = _event_with_embedding(title="Gallery night", description="An art exhibition")
        museum, _ = _event_with_embedding(title="Museum tour", description="An art exhibition")
        opening, _ = _event_with_embedding(title="Gallery opening", description="An art exhibition")
        for event_id in (gallery, museum, opening):
            _embed(event_id, [1.0, 0.0, 0.0])

        record_dismissal(user_id=USER_ID, event_id=gallery, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=museum, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )
        result = record_dismissal(
            user_id=USER_ID, event_id=opening, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )

        assert result.prompt is not None
        assert result.prompt.category_key == "arts_culture"
        assert "Arts & culture" in result.prompt.title
        assert "3 similar events" in result.prompt.description

    def test_the_generic_variant_when_no_chip_dominates(self):
        first, _ = _event_with_embedding(title="Zzz one")
        second, _ = _event_with_embedding(title="Zzz two")
        third, _ = _event_with_embedding(title="Zzz three")
        for event_id in (first, second, third):
            _embed(event_id, [1.0, 0.0, 0.0])

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )
        result = record_dismissal(
            user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )

        assert result.prompt is not None
        assert result.prompt.category_key is None
        assert result.prompt.title == "Less events like these in your next digest?"


class TestTheThreshold:
    def test_the_threshold_is_the_published_constant(self):
        assert FR25_CLUSTER_COSINE_THRESHOLD == Decimal("0.70")
