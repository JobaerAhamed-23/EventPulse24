"""The published read port for the event embeddings (FR-25).

**What this test holds:** the port hands back plain tuples of numbers, an event with no
vector is *absent* rather than zero, and a vector of the wrong width is dropped.
"""

import pytest

from adapters.llm.fake import FakeEmbeddingAdapter
from apps.ingestion.services.embedding import embed_event
from apps.ingestion.services.event_embeddings import _usable_vector, read_event_embeddings
from shared.constants import FR25_EMBEDDING_DIMENSIONS
from shared.db import CATALOG

from .factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[CATALOG])


class TestReadEventEmbeddings:
    def test_it_returns_the_stored_vector(self):
        event = EventFactory(title="Rooftop jazz")
        embed_event(event_id=event.pk, adapter=FakeEmbeddingAdapter())

        found = read_event_embeddings(event_ids=[event.pk])

        assert event.pk in found
        assert len(found[event.pk]) == FR25_EMBEDDING_DIMENSIONS
        assert all(isinstance(value, float) for value in found[event.pk])

    def test_an_event_with_no_vector_is_absent_and_not_zero(self):
        """A missing vector is not a zero vector — a zero vector would count as "not
        similar" and would silently advance the cluster's counter."""
        event = EventFactory(title="Not embedded")

        found = read_event_embeddings(event_ids=[event.pk])

        assert event.pk not in found
        assert found == {}

    def test_an_empty_request_returns_nothing(self):
        assert read_event_embeddings(event_ids=[]) == {}

    def test_an_unknown_id_is_absent(self):
        from shared.ids import uuid7

        assert read_event_embeddings(event_ids=[uuid7()]) == {}

    def test_it_reads_several_events_at_once(self):
        first = EventFactory(title="One")
        second = EventFactory(title="Two")
        embed_event(event_id=first.pk, adapter=FakeEmbeddingAdapter())
        embed_event(event_id=second.pk, adapter=FakeEmbeddingAdapter())

        found = read_event_embeddings(event_ids=[first.pk, second.pk])

        assert set(found) == {first.pk, second.pk}


class TestTheUsableVector:
    def test_a_vector_of_the_wrong_width_is_dropped(self):
        """The cosine of two vectors of different lengths is not defined.

        **The column refuses a wrong-width vector itself** — `pgvector` raises on the
        write, at the column type, so a row with a bad width cannot exist. The check is
        defence in depth, and the cost of getting it wrong is a number that looks like a
        cosine and is not one.
        """
        wrong = tuple([0.1] * (FR25_EMBEDDING_DIMENSIONS + 1))

        assert _usable_vector(wrong) is None

    def test_a_vector_of_the_right_width_is_kept(self):
        right = tuple([0.1] * FR25_EMBEDDING_DIMENSIONS)

        assert _usable_vector(right) == right

    def test_no_vector_is_not_a_zero_vector(self):
        assert _usable_vector(None) is None
