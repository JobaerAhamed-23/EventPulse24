"""The real embedding adapter: Voyage AI's `/v1/embeddings` (FR-25, D16).

**This is the third module in the project allowed to import `httpx`** — the first is
`adapters/crawl/http.py` (which fetches third-party sources, AD-9) and the second is
`adapters/revalidation/http.py` (which POSTs to our own frontend, FR-26, FR-27). This one
calls a third-party AI provider. All three are adapters, and the `http-client` import
contract names them: a new HTTP-capable adapter cannot appear without that contract
being amended in the same commit, so the widening is forced to be a deliberate, visible
edit.

**Why not the `voyageai` SDK.** The SDK is named in the `llm-sdk` contract as a provider
SDK that only `adapters.llm` may import, so it *may* be used here. It was not, because
it pulls in a very large dependency tree for a single REST call — langchain, an async
HTTP stack and a model hub client — and the embeddings endpoint is a plain JSON POST
with one header. The SDK's value is its type wrappers, which this adapter does not need.

**Matryoshka truncation is the point of `dimensions`.** `voyage-4-lite` is a Matryoshka
model: it can be truncated to a smaller dimension at essentially no loss in similarity.
The adapter asks for exactly the dimension the caller wants (`output_dimension`), rather
than embedding at the model's full size and slicing afterwards — the truncation is part
of the model, and slicing a full vector is not the same operation.

**The cost row is written here, and that is AD-5's one named exception.** The coding
standard says "an adapter writing rows is AD-5's one named exception, by AD-8's explicit
rule", and AD-8 says the gateway writes "a per-call cost row in the same transaction as
the result". So `embed()` opens the catalog transaction and writes the row inside it.

**The cost row's model lives in `adapters/llm/models.py`, not in an app.** Under `apps
| adapters` the gateway cannot import an app's models, so the standard puts the table
here, with `adapters.llm` registered as a Django app and routed to the `catalog` schema.
The row carries no user id: a cost row is a fact about a *call*, not about a person.

**The key never reaches a log line.** httpx logs request URLs at INFO, and this URL
carries no secret — the key is a header, and httpx does not log headers.
"""

import logging
from collections.abc import Sequence

import httpx
from django.conf import settings

from adapters.llm.costs import write_cost_row
from ports.embedding import EmbeddingPort, EmbeddingResult
from shared.constants import FR25_EMBEDDING_MODEL

logger = logging.getLogger(__name__)

#: Voyage's embeddings endpoint.
VOYAGE_EMBEDDINGS_URL = "https://api.voyageai.com/v1/embeddings"

#: The `input_type` Voyage asks for.
#:
#: **`document` for the event's own text.** The vector is the event's, and it is compared
#: against other events' vectors — so the query and the document are the same kind of
#: thing. (`query` would be for a search string; `classification` for labels.) Embedding
#: a document as a query would put it in the wrong part of the space, and the cosine
#: between two wrongly-placed vectors means nothing.
VOYAGE_INPUT_TYPE = "document"

#: The largest batch the adapter sends in one call.
#:
#: **A bound, because the request is a body.** An unbounded batch is a request whose size
#: nobody chose, and Voyage's own limit is a per-request one. The caller splits its work
#: at this boundary rather than the adapter silently truncating a list.
VOYAGE_MAX_BATCH = 128


class VoyageError(RuntimeError):
    """Voyage could not produce the vectors. Never mapped to HTTP by the adapter itself."""


class VoyageEmbeddingAdapter(EmbeddingPort):
    """Embeds text with Voyage, and writes the cost row for the call."""

    def embed(self, texts: Sequence[str], *, dimensions: int) -> EmbeddingResult:
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        if not texts:
            return EmbeddingResult(
                vectors=(),
                model=FR25_EMBEDDING_MODEL,
                input_tokens=0,
                cost_micros=0,
            )
        if len(texts) > VOYAGE_MAX_BATCH:
            raise VoyageError(
                f"a batch of {len(texts)} exceeds the {VOYAGE_MAX_BATCH}-text limit; "
                "the caller splits its work."
            )

        api_key = settings.VOYAGE_API_KEY
        if not api_key:
            # A missing key is a configuration error, not a zero cost. An adapter that
            # returned a free embedding would write a cost row saying the call was free.
            raise VoyageError("VOYAGE_API_KEY is not configured.")

        vectors, input_tokens, cost_micros = self._call(
            api_key=api_key, texts=texts, dimensions=dimensions
        )

        # The cost row, in the same transaction as the result (AD-8). The adapter is the
        # one place allowed to write it (AD-5's named exception).
        #
        # **The transaction is the caller's, not this method's.** The coding standard says
        # "the calling command opens `atomic(using=CATALOG)`, and the gateway writes the
        # row inside it" — so the row commits with the result it bills. A transaction
        # opened here would commit the cost row on its own, which is the exact failure
        # the rule exists to prevent: a cost row describing a result that later rolled
        # back.
        #
        # **So the caller must have opened one.** If it has not, `write_cost_row` raises
        # rather than quietly opening a transaction of its own.
        write_cost_row(
            kind="embedding",
            model=FR25_EMBEDDING_MODEL,
            input_tokens=input_tokens,
            output_tokens=0,
            cost_micros=cost_micros,
            call_count=len(texts),
        )

        return EmbeddingResult(
            vectors=tuple(vectors),
            model=FR25_EMBEDDING_MODEL,
            input_tokens=input_tokens,
            cost_micros=cost_micros,
        )

    def _call(
        self, *, api_key: str, texts: Sequence[str], dimensions: int
    ) -> tuple[list[tuple[float, ...]], int, int]:
        """One call to Voyage. Returns the vectors, the input tokens and the cost.

        **The cost is computed here, in micro-dollars, from the token count.** Voyage
        bills per token and does not return a price; so the price per million tokens is a
        constant of this adapter, and the row's `cost_micros` is the product. A float
        would make the dashboard's sum drift, so the multiplication is done in integers.
        """
        try:
            with httpx.Client(timeout=settings.VOYAGE_TIMEOUT_SECONDS) as client:
                response = client.post(
                    VOYAGE_EMBEDDINGS_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "input": list(texts),
                        "model": FR25_EMBEDDING_MODEL,
                        "input_type": VOYAGE_INPUT_TYPE,
                        "output_dimension": dimensions,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            # The message names the status where there is one, and never the key.
            logger.warning("voyage embedding call failed: %s", exc)
            raise VoyageError("the embedding provider could not be reached.") from exc

        vectors = payload.get("data")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise VoyageError("the embedding provider returned an unexpected number of vectors.")

        # The order matters: `data[i]` is the vector for `texts[i]`, and the caller pairs
        # them by index. A reordering here would silently attach the wrong vector to the
        # wrong event — and a wrong vector is a wrong cluster, not a wrong card.
        pairs = sorted(vectors, key=lambda item: item.get("index", 0))
        out: list[tuple[float, ...]] = []
        for pair in pairs:
            embedding = pair.get("embedding")
            if not isinstance(embedding, list) or len(embedding) != dimensions:
                raise VoyageError("the embedding provider returned a vector of the wrong size.")
            out.append(tuple(float(value) for value in embedding))

        total_tokens = payload.get("total_tokens") or 0
        return out, int(total_tokens), self._cost_micros(int(total_tokens))

    @staticmethod
    def _cost_micros(input_tokens: int) -> int:
        """The cost of `input_tokens` embedded, in micro-dollars.

        **The price is per million tokens**, and it is a constant of this adapter because
        it is the provider's price, not a product decision. A price change is a config
        change here and in the cost row's history — the rows themselves keep what was
        charged at the time.
        """
        price_per_million_micros = VOYAGE_PRICE_PER_MILLION_TOKENS_MICROS
        return (input_tokens * price_per_million_micros) // 1_000_000


#: Voyage's price for `voyage-4-lite`, in micro-dollars per million tokens.
#:
#: **This is the provider's price at the time of writing, and it is here because the cost
#: row has to carry a real number.** A cost row of zero would be a lie the AI Cost
#: Dashboard would report. When the price changes, this constant changes with it — and
#: the rows already written keep the price they were charged at, which is exactly what a
#: cost history is for.
VOYAGE_PRICE_PER_MILLION_TOKENS_MICROS = 20_000


__all__ = [
    "VOYAGE_EMBEDDINGS_URL",
    "VOYAGE_MAX_BATCH",
    "VoyageEmbeddingAdapter",
    "VoyageError",
]
