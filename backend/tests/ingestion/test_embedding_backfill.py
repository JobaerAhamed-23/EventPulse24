"""The embed command and the resumable backfill (FR-25).

**What these tests hold:** the command embeds the event's text and stores the vector; it
writes nothing for an event with no text; the backfill is resumable, batched and
costed; and a provider failure costs one event, not the run.
"""

import pytest

from adapters.llm.fake import FakeEmbeddingAdapter
from apps.ingestion.models import Event
from apps.ingestion.services.embedding import embed_event, event_embedding_text
from apps.ingestion.services.embedding_backfill import (
    BackfillReport,
    backfill_embeddings,
    count_events_without_an_embedding,
)
from shared.constants import FR25_EMBEDDING_DIMENSIONS
from shared.db import CATALOG

from .factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[CATALOG])


class TestTheEmbedCommand:
    def test_it_stores_a_vector_on_the_event(self):
        event = EventFactory(title="Rooftop jazz night")

        assert embed_event(event_id=event.pk, adapter=FakeEmbeddingAdapter()) is True

        stored = Event.objects.using(CATALOG).get(pk=event.pk).embedding
        assert stored is not None
        assert len(stored) == FR25_EMBEDDING_DIMENSIONS

    def test_it_writes_nothing_for_an_event_with_no_text(self):
        event = EventFactory(title="", description="")

        assert embed_event(event_id=event.pk, adapter=FakeEmbeddingAdapter()) is False

        assert Event.objects.using(CATALOG).get(pk=event.pk).embedding is None

    def test_it_writes_nothing_for_an_event_that_does_not_exist(self):
        from shared.ids import uuid7

        assert embed_event(event_id=uuid7(), adapter=FakeEmbeddingAdapter()) is False

    def test_it_writes_nothing_when_the_provider_returns_no_vector(self):
        """**A provider that answers with nothing is not a vector.** Storing an empty
        one would leave the event looking embedded — the backfill would skip it, and
        the cluster would compare it against nothing.

        **So the event keeps no vector, and the command says it did nothing.**
        """

        class _EmptyAdapter:
            def embed(self, texts, *, dimensions):
                from ports.embedding import EmbeddingResult

                return EmbeddingResult(vectors=(), model="fake", input_tokens=0, cost_micros=0)

        event = EventFactory(title="Rooftop jazz night")

        assert embed_event(event_id=event.pk, adapter=_EmptyAdapter()) is False

        assert Event.objects.using(CATALOG).get(pk=event.pk).embedding is None

    def test_the_text_is_the_title_then_the_description(self):
        text = event_embedding_text(title="Jazz night", description="Live at eight.")

        assert text == "Jazz night\n\nLive at eight."

    def test_the_description_is_bounded(self):
        """A source can publish a megabyte under a 500-character title (AD-9)."""
        text = event_embedding_text(title="Jazz night", description="x" * 5000)

        assert len(text) < 5000


class TestTheBackfill:
    def test_it_embeds_the_events_that_have_no_vector(self):
        EventFactory(title="One")
        EventFactory(title="Two")

        report = backfill_embeddings(adapter=FakeEmbeddingAdapter())

        assert report.embedded == 2
        assert report.skipped == 0
        assert report.failed == 0

    def test_it_is_resumable(self):
        """A second run finds nothing to do and writes nothing."""
        EventFactory(title="One")

        backfill_embeddings(adapter=FakeEmbeddingAdapter())
        second = backfill_embeddings(adapter=FakeEmbeddingAdapter())

        assert second.embedded == 0
        assert count_events_without_an_embedding() == 0

    def test_it_never_re_embeds_an_event_that_already_has_a_vector(self):
        event = EventFactory(title="One")
        embed_event(event_id=event.pk, adapter=FakeEmbeddingAdapter())
        before = list(Event.objects.using(CATALOG).get(pk=event.pk).embedding)

        backfill_embeddings(adapter=FakeEmbeddingAdapter())

        assert list(Event.objects.using(CATALOG).get(pk=event.pk).embedding) == before

    def test_it_skips_an_event_with_no_text(self):
        EventFactory(title="", description="")

        report = backfill_embeddings(adapter=FakeEmbeddingAdapter())

        assert report.skipped == 1
        assert report.embedded == 0

    def test_a_provider_failure_costs_one_event_and_not_the_run(self):
        EventFactory(title="One")
        EventFactory(title="Two")
        EventFactory(title="Three")

        class FailingAdapter(FakeEmbeddingAdapter):
            calls = 0

            def embed(self, texts, *, dimensions):
                FailingAdapter.calls += 1
                if FailingAdapter.calls == 2:
                    raise RuntimeError("the provider is down")
                return super().embed(texts, dimensions=dimensions)

        report = backfill_embeddings(adapter=FailingAdapter())

        assert report.failed == 1
        assert report.embedded == 2

    def test_it_batches(self):
        """Each batch is its own transaction, so a partial run is a valid state."""
        EventFactory(title="One")
        EventFactory(title="Two")
        EventFactory(title="Three")

        report = backfill_embeddings(adapter=FakeEmbeddingAdapter(), batch_size=1)

        assert report.embedded == 3

    def test_the_report_adds(self):
        assert BackfillReport(embedded=1) + BackfillReport(skipped=2) == BackfillReport(
            embedded=1, skipped=2
        )

    def test_the_count_is_the_pending_count(self):
        EventFactory(title="One")

        assert count_events_without_an_embedding() == 1
