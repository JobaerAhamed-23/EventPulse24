"""The AI cost row (AD-8): one row per call, in the call's own transaction.

**What this test holds:** every embedding call writes a cost row; the row is written
inside the caller's transaction and rolls back with it; and the row carries no user id.
"""

import pytest
from django.db import transaction

from adapters.llm.costs import CostRowOutsideCatalogTransaction, write_cost_row
from adapters.llm.fake import FakeEmbeddingAdapter
from adapters.llm.models import AICostRow
from apps.ingestion.services.embedding import embed_event
from shared.db import CATALOG
from tests.ingestion.factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[CATALOG])


class TestTheCostRow:
    # transaction=True: pytest-django otherwise wraps every alias in an atomic block, and
    # the "no transaction open" branch could never run. Same shape as
    # tests/ingestion/test_audit.py.
    @pytest.mark.django_db(databases=[CATALOG], transaction=True)
    def test_the_writer_refuses_to_run_outside_a_catalog_transaction(self):
        """A cost row committed apart from the result it bills records a call that may
        never have happened."""
        with pytest.raises(CostRowOutsideCatalogTransaction):
            write_cost_row(
                kind="embedding",
                model="fake",
                input_tokens=10,
                output_tokens=0,
                cost_micros=0,
                call_count=1,
            )

        assert not AICostRow.objects.using(CATALOG).exists()

    def test_it_writes_a_row_inside_a_catalog_transaction(self):
        with transaction.atomic(using=CATALOG):
            row = write_cost_row(
                kind="embedding",
                model="fake",
                input_tokens=10,
                output_tokens=0,
                cost_micros=0,
                call_count=1,
            )

        assert row.pk is not None
        assert AICostRow.objects.using(CATALOG).count() == 1

    def test_the_row_carries_no_user_id(self):
        """A cost row is about a call, not about a person."""
        with transaction.atomic(using=CATALOG):
            write_cost_row(
                kind="embedding",
                model="fake",
                input_tokens=10,
                output_tokens=0,
                cost_micros=0,
                call_count=1,
            )

        row = AICostRow.objects.using(CATALOG).first()
        assert "user_id" not in {field.name for field in row._meta.get_fields()}


class TestTheEmbedCommandIsCosted:
    def test_an_embed_call_writes_a_cost_row(self):
        event = EventFactory(title="Rooftop jazz")

        embed_event(event_id=event.pk, adapter=FakeEmbeddingAdapter())

        row = AICostRow.objects.using(CATALOG).get()
        assert row.kind == AICostRow.Kind.EMBEDDING
        assert row.call_count == 1
        assert row.output_tokens == 0

    def test_the_cost_row_rolls_back_with_the_result(self):
        """The rule is "a per-call cost row in the same transaction as the result"."""
        event = EventFactory(title="Rooftop jazz")

        with pytest.raises(RuntimeError):
            with transaction.atomic(using=CATALOG):
                embed_event(event_id=event.pk, adapter=FakeEmbeddingAdapter())
                raise RuntimeError("the command failed after the call")

        assert AICostRow.objects.using(CATALOG).count() == 0
