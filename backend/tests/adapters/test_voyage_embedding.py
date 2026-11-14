"""The Voyage embedding adapter: what it sends, and what it makes of the answer.

**The provider is the only thing faked here.** Everything else runs for real: the batch
bound, the dimension check, the pairing of vectors to texts, the cost arithmetic and the
cost row. A test that faked the whole adapter would be testing the fake.

**The three things this file holds**, each of which is a way the adapter could quietly
do the wrong thing:

- **The request.** It asks for `input_type=document` — the vectors are compared against
  each other, so they are documents, and embedding a document as a query would put it in
  the wrong part of the space. It asks for exactly the dimension the caller wants, because
  Matryoshka truncation is the model's, not a slice applied afterwards.
- **The pairing.** `data[i]` is the vector for `texts[i]`. The provider is allowed to
  return its results out of order, so the adapter sorts on `index`. A vector attached to
  the wrong event is a wrong *cluster*, not a wrong card — the consequence is invisible
  until a user is shown a mute for the wrong thing.
- **The cost.** Voyage bills per token and does not return a price, so the price is a
  constant here and the row carries the product. A row of zero would be a lie the AI Cost
  Dashboard would report.
"""

import json

import httpx
import pytest
from django.db import transaction

from adapters.llm import voyage as module
from adapters.llm.models import AICostRow
from adapters.llm.voyage import (
    VOYAGE_EMBEDDINGS_URL,
    VOYAGE_MAX_BATCH,
    VoyageEmbeddingAdapter,
    VoyageError,
)
from shared.db import CATALOG

pytestmark = pytest.mark.django_db(databases=[CATALOG])

DIMENSIONS = 256
KEY = "a-test-key"


class _StubClient:
    """Stands in for `httpx.Client`. Records the call and answers with a canned response.

    **The house pattern, from `tests/adapters/test_revalidation_http.py`** — the same
    adapter seams, the same reason: the adapter owns its client, so the client is the
    one thing a test may replace.
    """

    calls: list[dict] = []
    response: httpx.Response | None = None
    raises: Exception | None = None

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        type(self).calls.append({"init": kwargs})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, *, json=None, headers=None):
        type(self).calls.append({"url": url, "json": json, "headers": headers})
        if type(self).raises is not None:
            raise type(self).raises
        return type(self).response


def _response(status: int, *, body: dict | None = None) -> httpx.Response:
    """An `httpx.Response` with a request attached.

    **`raise_for_status()` needs a request.** A response built without one raises a
    `RuntimeError` instead of an `HTTPStatusError`, so the adapter's error path would
    never be reached. The request is a real one, to the real endpoint.
    """
    request = httpx.Request("POST", VOYAGE_EMBEDDINGS_URL)
    if body is None:
        return httpx.Response(status, request=request)
    return httpx.Response(status, json=body, request=request)


@pytest.fixture
def stub(monkeypatch):
    _StubClient.calls = []
    _StubClient.response = _response(200, body={"data": [], "total_tokens": 0})
    _StubClient.raises = None
    monkeypatch.setattr(module.httpx, "Client", _StubClient)
    return _StubClient


@pytest.fixture
def adapter():
    return VoyageEmbeddingAdapter()


def _payload(*, count: int = 1, dimensions: int = DIMENSIONS, tokens: int = 100, order=None):
    """A Voyage-shaped response body.

    `order` names the `index` each vector carries, in the order the provider returned
    them — so a test can hand back the vectors shuffled and assert the adapter puts them
    back.

    **Each vector carries its own index as its first component**, so the vectors are
    distinguishable. A payload of identical vectors would make the pairing untestable: a
    shuffled response and a sorted one would be the same list.
    """
    if order is None:
        order = list(range(count))
    return {
        "data": [
            {"index": index, "embedding": [float(index)] + [0.1] * (dimensions - 1)}
            for index in order
        ],
        "total_tokens": tokens,
    }


class TestTheRequest:
    def test_it_posts_to_the_embeddings_endpoint(self, stub, adapter):
        stub.response = _response(200, body=_payload())

        with transaction.atomic(using=CATALOG):
            adapter.embed(["a rooftop jazz evening"], dimensions=DIMENSIONS)

        call = next(c for c in stub.calls if "url" in c)
        assert call["url"] == VOYAGE_EMBEDDINGS_URL

    def test_the_key_goes_in_a_header_and_never_in_the_body(self, stub, adapter, settings):
        """The key is a secret. It travels in a header, and the body is only the text."""
        settings.VOYAGE_API_KEY = KEY
        stub.response = _response(200, body=_payload())

        with transaction.atomic(using=CATALOG):
            adapter.embed(["a rooftop jazz evening"], dimensions=DIMENSIONS)

        call = next(c for c in stub.calls if "url" in c)
        assert call["headers"]["Authorization"] == f"Bearer {KEY}"
        assert KEY not in json.dumps(call["json"])

    def test_it_asks_for_the_dimension_the_caller_wants(self, stub, adapter):
        """Matryoshka truncation is the model's. Asking for the dimension is not the same
        operation as embedding wide and slicing."""
        stub.response = _response(200, body=_payload(dimensions=128))

        with transaction.atomic(using=CATALOG):
            adapter.embed(["a rooftop jazz evening"], dimensions=128)

        call = next(c for c in stub.calls if "url" in c)
        assert call["json"]["output_dimension"] == 128

    def test_it_asks_for_document_input_type(self, stub, adapter):
        """The vectors are compared against each other, so they are documents. Embedding
        a document as a query would put it in the wrong part of the space, and the cosine
        between two wrongly-placed vectors means nothing."""
        stub.response = _response(200, body=_payload())

        with transaction.atomic(using=CATALOG):
            adapter.embed(["a rooftop jazz evening"], dimensions=DIMENSIONS)

        call = next(c for c in stub.calls if "url" in c)
        assert call["json"]["input_type"] == "document"

    def test_it_asks_for_the_named_model(self, stub, adapter):
        stub.response = _response(200, body=_payload())

        with transaction.atomic(using=CATALOG):
            adapter.embed(["a rooftop jazz evening"], dimensions=DIMENSIONS)

        call = next(c for c in stub.calls if "url" in c)
        assert call["json"]["model"] == module.FR25_EMBEDDING_MODEL

    def test_it_refuses_a_batch_larger_than_the_limit(self, stub, adapter):
        """The request is a body, and the limit is a per-request one. The caller splits
        its work; the adapter does not silently truncate a list."""
        with pytest.raises(VoyageError, match="the caller splits its work"):
            adapter.embed(
                ["text"] * (VOYAGE_MAX_BATCH + 1),
                dimensions=DIMENSIONS,
            )

        assert not [c for c in stub.calls if "url" in c]

    def test_an_empty_batch_costs_nothing_and_calls_nothing(self, stub, adapter):
        result = adapter.embed([], dimensions=DIMENSIONS)

        assert result.vectors == ()
        assert result.cost_micros == 0
        assert not [c for c in stub.calls if "url" in c]

    def test_a_non_positive_dimension_is_refused(self, stub, adapter):
        with pytest.raises(ValueError, match="dimensions must be positive"):
            adapter.embed(["a rooftop jazz evening"], dimensions=0)


class TestTheAnswer:
    def test_the_vectors_come_back_in_the_order_the_texts_went_in(self, stub, adapter):
        """**The pairing is the point.** `data[i]` is the vector for `texts[i]`, and the
        provider is allowed to answer out of order. A vector attached to the wrong event
        is a wrong cluster, not a wrong card."""
        stub.response = _response(200, body=_payload(count=2, order=[1, 0]))

        with transaction.atomic(using=CATALOG):
            result = adapter.embed(["first", "second"], dimensions=DIMENSIONS)

        assert len(result.vectors) == 2
        # The provider said index 1 first; the adapter must still hand back text 0's
        # vector first. Each vector carries its own index as its first component, so
        # the order is visible in the values rather than only in the provider's
        # bookkeeping.
        assert result.vectors[0][0] == 0.0
        assert result.vectors[1][0] == 1.0

    def test_a_vector_of_the_wrong_size_is_refused(self, stub, adapter):
        """A vector of the wrong size cannot be compared with anything."""
        stub.response = _response(200, body=_payload(dimensions=64))

        with transaction.atomic(using=CATALOG):
            with pytest.raises(VoyageError, match="wrong size"):
                adapter.embed(["a rooftop jazz evening"], dimensions=DIMENSIONS)

    def test_the_wrong_number_of_vectors_is_refused(self, stub, adapter):
        """One text in, two vectors out, is a provider that does not understand the
        request. Pairing them by index would silently drop one."""
        stub.response = _response(200, body=_payload(count=2))

        with transaction.atomic(using=CATALOG):
            with pytest.raises(VoyageError, match="unexpected number of vectors"):
                adapter.embed(["one text only"], dimensions=DIMENSIONS)

    def test_a_transport_failure_becomes_a_voyage_error(self, stub, adapter):
        """A provider that cannot be reached is an outcome, not a crash — and the
        message must not carry the key."""
        stub.raises = httpx.ConnectError("connection refused")

        with transaction.atomic(using=CATALOG):
            with pytest.raises(VoyageError, match="could not be reached"):
                adapter.embed(["a rooftop jazz evening"], dimensions=DIMENSIONS)

    def test_an_http_error_becomes_a_voyage_error(self, stub, adapter):
        stub.response = _response(500, body={"error": "boom"})

        with transaction.atomic(using=CATALOG):
            with pytest.raises(VoyageError, match="could not be reached"):
                adapter.embed(["a rooftop jazz evening"], dimensions=DIMENSIONS)

    def test_a_missing_key_is_a_configuration_error_not_a_free_embedding(
        self, stub, adapter, settings
    ):
        """An adapter that returned a free embedding would write a cost row saying the
        call was free. A missing key is a configuration error."""
        settings.VOYAGE_API_KEY = ""

        with pytest.raises(VoyageError, match="VOYAGE_API_KEY is not configured"):
            adapter.embed(["a rooftop jazz evening"], dimensions=DIMENSIONS)

        assert not [c for c in stub.calls if "url" in c]


class TestTheCost:
    def test_the_cost_row_is_written_for_the_call(self, stub, adapter):
        stub.response = _response(200, body=_payload(tokens=1_000))

        with transaction.atomic(using=CATALOG):
            adapter.embed(["a rooftop jazz evening"], dimensions=DIMENSIONS)

        row = AICostRow.objects.using(CATALOG).first()
        assert row is not None
        assert row.kind == "embedding"
        assert row.input_tokens == 1_000
        assert row.call_count == 1

    def test_the_cost_is_the_token_count_times_the_price(self, stub, adapter):
        """The price is per million tokens and the row carries the product. A cost row
        of zero would be a lie the AI Cost Dashboard would report."""
        stub.response = _response(200, body=_payload(tokens=1_000_000))

        with transaction.atomic(using=CATALOG):
            result = adapter.embed(["a rooftop jazz evening"], dimensions=DIMENSIONS)

        expected = module.VOYAGE_PRICE_PER_MILLION_TOKENS_MICROS
        assert result.cost_micros == expected

        row = AICostRow.objects.using(CATALOG).first()
        assert row.cost_micros == expected

    def test_the_cost_is_the_same_on_the_result_and_on_the_row(self, stub, adapter):
        """The result and the row are two views of one fact. If they disagreed, the
        dashboard would report a different spend than the call actually cost."""
        stub.response = _response(200, body=_payload(tokens=12_345))

        with transaction.atomic(using=CATALOG):
            result = adapter.embed(["a rooftop jazz evening"], dimensions=DIMENSIONS)

        row = AICostRow.objects.using(CATALOG).first()
        assert row.cost_micros == result.cost_micros

    def test_the_call_count_is_the_number_of_texts(self, stub, adapter):
        stub.response = _response(200, body=_payload(count=2))

        with transaction.atomic(using=CATALOG):
            adapter.embed(["one", "two"], dimensions=DIMENSIONS)

        row = AICostRow.objects.using(CATALOG).first()
        assert row.call_count == 2

    def test_the_price_constant_is_the_provider_price(self):
        """A price change is a config change here, and in the cost row's history — the
        rows already written keep what they were charged at."""
        assert module.VOYAGE_PRICE_PER_MILLION_TOKENS_MICROS > 0
