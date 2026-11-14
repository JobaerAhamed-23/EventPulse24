"""Local stand-ins for the LLM gateway and embeddings: deterministic, free, no network (AD-8)."""

import hashlib
import math
import struct
from collections.abc import Sequence

from adapters.llm.costs import write_cost_row
from ports.embedding import EmbeddingPort, EmbeddingResult
from ports.llm import LLMPort, LLMRequest, LLMResult

FAKE_MODEL = "fake"


def _word_count(text: str) -> int:
    return len(text.split())


class FakeLLMAdapter(LLMPort):
    def complete(self, request: LLMRequest) -> LLMResult:
        digest = hashlib.sha256(
            f"{request.task}\0{request.instructions}\0{request.untrusted_content}".encode()
        ).hexdigest()[:12]
        return LLMResult(
            text=f"fake {request.task} result {digest}",
            model=FAKE_MODEL,
            input_tokens=_word_count(request.instructions) + _word_count(request.untrusted_content),
            output_tokens=4,
            cost_micros=0,
        )


def _unit_vector(text: str, dimensions: int) -> tuple[float, ...]:
    # Expand a hash of the text into `dimensions` floats in [-1, 1], then normalise.
    raw: list[float] = []
    block = 0
    while len(raw) < dimensions:
        chunk = hashlib.sha256(f"{block}\0{text}".encode()).digest()
        raw.extend(value / 2**31 for value in struct.unpack(">8i", chunk))
        block += 1
    values = raw[:dimensions]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return tuple(v / norm for v in values)


class FakeEmbeddingAdapter(EmbeddingPort):
    """The free, deterministic, offline stand-in.

    **It writes a cost row too, and the row says zero.** AD-8 requires a cost row per
    call, and a fake that skipped it would mean the cost path was never exercised by a
    local run — the row would appear for the first time in production. A row of zero is
    honest: the fake really is free.

    The row needs a `catalog` transaction open, exactly as the real adapter's does — the
    fake is a stand-in for the *behaviour*, and the behaviour includes the cost row.
    """

    def embed(self, texts: Sequence[str], *, dimensions: int) -> EmbeddingResult:
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        input_tokens = sum(_word_count(text) for text in texts)
        write_cost_row(
            kind="embedding",
            model=FAKE_MODEL,
            input_tokens=input_tokens,
            output_tokens=0,
            cost_micros=0,
            call_count=len(texts),
        )
        return EmbeddingResult(
            vectors=tuple(_unit_vector(text, dimensions) for text in texts),
            model=FAKE_MODEL,
            input_tokens=input_tokens,
            cost_micros=0,
        )
