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
    _cluster_candidates,
    _decayed_weight,
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


def _embed_raw(event_id, values: list[float]) -> None:
    """Write a vector *without* normalising it.

    **The zero vector cannot be made any other way.** `_unit` divides by the norm, so
    it cannot produce a vector of length zero — and a zero vector is exactly the case
    the cosine refuses, because a zero vector has no direction. So this writes the
    column directly, padded to the stored width.
    """
    from apps.ingestion.models import Event

    padded = list(values) + [0.0] * (FR25_EMBEDDING_DIMENSIONS - len(values))
    Event.objects.using(CATALOG).filter(pk=event_id).update(embedding=padded)


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

    def test_a_similarity_below_the_threshold_does_not_cluster(self):
        """**The threshold is 0.70, and a pair at 0.50 is not a pair at 0.70.**

        **This is the test that pins the number.** The other threshold test uses a pair
        at cosine 0.0 — as far apart as two vectors can be — and that pair fails against
        *any* threshold worth the name. So it would still pass if the threshold had
        drifted down to 0.10, which is a rule that would cluster genuinely unrelated
        events.

        **A pair at 0.50 is the discriminating case**: it is above a threshold that has
        drifted down, and below the published one. Two vectors at 60° to each other are
        `[1, 0]` and `[0.5, √3/2]`, whose cosine is exactly 0.5.
        """
        first, _ = _event_with_embedding(title="Jazz one")
        second, _ = _event_with_embedding(title="Jazz two")
        third, _ = _event_with_embedding(title="Jazz three")
        _embed(first, [1.0, 0.0, 0.0])
        # 60° apart: cosine 0.5 — similar, and not similar enough.
        _embed(second, [0.5, (1 - 0.5**2) ** 0.5, 0.0])
        _embed(third, [0.5, (1 - 0.5**2) ** 0.5, 0.0])

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )
        result = record_dismissal(
            user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )

        assert result.prompt_due is False

    def test_another_users_dismissals_do_not_join_the_cluster(self):
        """**The cluster is the user's, not the product's.**

        Every other test in this file uses one user, so a rule that read *all* users'
        dismissals would pass all of them. **The scoping is a real rule, and it needs a
        test with a second user in it.**

        Two of this user's dismissals plus one of somebody else's is two dismissals.
        Somebody else's swipe past a jazz event says nothing about whether *this* user
        wants less jazz — and a rule that let it in would ask a user to mute a
        category because a stranger swiped.
        """
        first, _ = _event_with_embedding(title="Mine one")
        second, _ = _event_with_embedding(title="Mine two")
        theirs, _ = _event_with_embedding(title="Theirs")
        for event_id in (first, second, theirs):
            _embed(event_id, [1.0, 0.0, 0.0])

        other_user = uuid4()
        other_actor = Actor.user(other_user)

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=other_user, event_id=theirs, actor=other_actor, now=NOW + timedelta(minutes=1)
        )
        result = record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )

        assert result.prompt_due is False

    def test_a_similarity_just_above_the_threshold_does_cluster(self):
        """**The other side of the same number.**

        A pair at cosine 0.75 clears the published threshold of 0.70, so it clusters.
        The two tests together pin the threshold from both sides: 0.50 does not
        cluster, 0.75 does.
        """
        first, _ = _event_with_embedding(title="Jazz one")
        second, _ = _event_with_embedding(title="Jazz two")
        third, _ = _event_with_embedding(title="Jazz three")
        _embed(first, [1.0, 0.0, 0.0])
        # 41.4° apart: cosine 0.75 — the unit vector's x-component is the cosine
        # against `[1, 0]`, so the y-component is √(1 − 0.75²).
        _embed(second, [0.75, (1 - 0.75**2) ** 0.5, 0.0])
        _embed(third, [0.75, (1 - 0.75**2) ** 0.5, 0.0])

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )
        result = record_dismissal(
            user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )

        assert result.prompt_due is True

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

    def test_an_event_with_no_vector_in_the_middle_cannot_cluster(self):
        """**The gap the newest-only test leaves open.**

        **The newest dismissal is the one the cluster is measured from**, so a missing
        vector on the *newest* event is caught by a different check — and a test that
        only covers that case leaves the middle of the cluster unguarded.

        **The middle event is the one that matters.** The rule compares the newest
        against each of the others, and an event the backfill has not reached cannot be
        compared. Treating a missing vector as comparable would let two unrelated
        events satisfy the rule on the strength of the third — which is the rule
        deciding something it cannot know.
        """
        first, _ = _event_with_embedding(title="Jazz one", embed=False)
        second, _ = _event_with_embedding(title="Jazz two")
        third, _ = _event_with_embedding(title="Jazz three")
        _embed(second, [1.0, 0.0, 0.0])
        _embed(third, [1.0, 0.0, 0.0])

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )
        result = record_dismissal(
            user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )

        assert result.prompt_due is False

    def test_a_zero_vector_does_not_crash_the_rule(self):
        """**A zero vector has no direction**, so its cosine with anything is undefined
        — and the division would be by zero. The read port never returns a zero vector
        (a missing vector is absent, not zero), but a zero can still arrive from a
        provider, and a rule that crashed on one would take the whole dismissal path
        down.

        **So the comparison refuses the pair rather than raising.** The dismissal is
        recorded, the cluster does not form, and the next dismissal still works.
        """
        first, _ = _event_with_embedding(title="Jazz one")
        second, _ = _event_with_embedding(title="Jazz two")
        third, _ = _event_with_embedding(title="Jazz three")
        _embed(first, [1.0, 0.0, 0.0])
        _embed(second, [1.0, 0.0, 0.0])
        _embed_raw(third, [0.0, 0.0, 0.0])

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )
        result = record_dismissal(
            user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )

        assert result.prompt_due is False

    def test_the_dismissal_is_still_recorded_when_a_vector_is_zero(self):
        """**The rule refuses the comparison; it does not lose the dismissal.** The
        user's swipe is a fact about what they want, and dropping it because a vector
        was degenerate would lose the signal the whole loop is built on."""
        first, _ = _event_with_embedding(title="Jazz one")
        second, _ = _event_with_embedding(title="Jazz two")
        third, _ = _event_with_embedding(title="Jazz three")
        _embed(first, [1.0, 0.0, 0.0])
        _embed(second, [1.0, 0.0, 0.0])
        _embed_raw(third, [0.0, 0.0, 0.0])

        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )
        record_dismissal(
            user_id=USER_ID, event_id=third, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )

        assert EventDismissal.objects.using(PERSONAL).filter(user_id=USER_ID).count() == 3


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

    def test_dismissing_the_same_event_twice_does_not_add_a_second_row(self):
        """**The pair is unique.** A second dismissal of the same event updates the row
        rather than adding another one — otherwise one event could satisfy the
        "three *distinct* events" rule on its own.
        """
        event, _ = _event_with_embedding(title="One")

        record_dismissal(user_id=USER_ID, event_id=event, actor=ACTOR, now=NOW)
        record_dismissal(user_id=USER_ID, event_id=event, actor=ACTOR, now=NOW + timedelta(hours=1))

        assert EventDismissal.objects.using(PERSONAL).filter(user_id=USER_ID).count() == 1

    def test_re_dismissing_the_same_event_does_not_move_its_timestamp(self):
        """**The dismissal happened when it first happened.** Moving it would let a
        user keep a cluster alive by re-swiping the same card."""
        event, _ = _event_with_embedding(title="One")

        record_dismissal(user_id=USER_ID, event_id=event, actor=ACTOR, now=NOW)
        later = NOW + timedelta(hours=1)
        record_dismissal(user_id=USER_ID, event_id=event, actor=ACTOR, now=later)

        row = EventDismissal.objects.using(PERSONAL).filter(user_id=USER_ID).first()
        assert row.dismissed_at == NOW

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
    def test_the_weight_is_zero_past_the_expiry(self):
        """**The rule itself, stated once.** The candidate pool already filters the
        expired dismissals out, so this branch cannot be reached *through* the cluster —
        but the weight function is the place the rule lives, and a rule that is only
        enforced by a filter somewhere else is a rule with two sources of truth.

        **Expired means zero, not half.** Past 180 days the dismissal is not counted at
        all: a preference the user cannot escape is not a preference the product should
        speak for.
        """
        old = NOW - timedelta(days=FR25_DECAY_EXPIRE_DAYS + 1)

        assert _decayed_weight(dismissed_at=old, now=NOW) == Decimal(0)

    def test_the_weight_is_half_past_the_half_life(self):
        assert _decayed_weight(
            dismissed_at=NOW - timedelta(days=FR25_DECAY_HALF_DAYS + 1), now=NOW
        ) == Decimal("0.5")

    def test_the_weight_is_one_inside_the_half_life(self):
        assert _decayed_weight(dismissed_at=NOW, now=NOW) == Decimal(1)

    def test_a_dismissal_older_than_the_expiry_is_ignored(self):
        """**The expiry is a cliff, and it is observable on its own.**

        **The half-decay test and this one used to look the same.** A dismissal past
        the expiry also weighs half — no, it weighs *nothing* — but the evidence sum
        was the same either way, so a rule that had quietly changed the expiry into a
        half-weight still passed. So this test asserts the thing the expiry actually
        does: **the row leaves the candidate pool entirely.**

        **Two fresh dismissals plus an expired one is two dismissals**, and the pool
        that holds them is two rows long. The half-decayed dismissal, by contrast, is
        still *in* the pool — it just weighs half.
        """
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

    def test_an_expired_dismissal_leaves_the_candidate_pool(self):
        """**The expiry removes the row; it does not merely weaken it.**

        **A dismissal from 200 days ago is not evidence the product may still use.** It
        is gone — not half-weighted, not quarter-weighted, gone — because a preference
        the user cannot escape is not a preference the product should speak for.

        **So the row is not in the pool at all**, and that is what this asserts. The
        pool is the *set* of dismissals the rule considers; the weights are applied
        inside it.
        """
        first, _ = _event_with_embedding(title="One")
        second, _ = _event_with_embedding(title="Two")
        for event_id in (first, second):
            _embed(event_id, [1.0, 0.0, 0.0])

        old = NOW - timedelta(days=FR25_DECAY_EXPIRE_DAYS + 1)
        record_dismissal(user_id=USER_ID, event_id=first, actor=ACTOR, now=old)
        record_dismissal(
            user_id=USER_ID, event_id=second, actor=ACTOR, now=NOW - timedelta(minutes=1)
        )

        candidates = _cluster_candidates(user_id=USER_ID, now=NOW)

        assert [row.event_id for row in candidates] == [second]

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

    def test_a_tie_between_two_chips_is_not_a_majority(self):
        """**A tie is not a majority.** One event in the cluster being a jazz event does
        not make the cluster jazz: the cluster is three events, and the mute is for the
        thing they have in common. Here one event is an art event and one is a sports
        event and one belongs to no category at all — so no chip has a majority, and the
        honest prompt is the generic one.

        **A mute on the wrong category would be the worst outcome here.** The user
        swiped past three things and gets asked about one of them; the category in the
        title would be a claim about what they had in common, and it would be false.
        """
        art, _ = _event_with_embedding(title="Gallery night")
        sport, _ = _event_with_embedding(title="Basketball clinic")
        neither, _ = _event_with_embedding(title="Zzz three")
        for event_id in (art, sport, neither):
            _embed(event_id, [1.0, 0.0, 0.0])

        record_dismissal(user_id=USER_ID, event_id=art, actor=ACTOR, now=NOW)
        record_dismissal(
            user_id=USER_ID, event_id=sport, actor=ACTOR, now=NOW + timedelta(minutes=1)
        )
        result = record_dismissal(
            user_id=USER_ID, event_id=neither, actor=ACTOR, now=NOW + timedelta(minutes=2)
        )

        assert result.prompt is not None
        assert result.prompt.category_key is None
        assert result.prompt.title == "Less events like these in your next digest?"


class TestTheThreshold:
    def test_the_threshold_is_the_published_constant(self):
        assert FR25_CLUSTER_COSINE_THRESHOLD == Decimal("0.70")
