"""Local stand-ins for the LLM gateway and embeddings: deterministic, free, no network (AD-8)."""

import hashlib
import math
import struct
from collections.abc import Sequence

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
    def embed(self, texts: Sequence[str], *, dimensions: int) -> EmbeddingResult:
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        return EmbeddingResult(
            vectors=tuple(_unit_vector(text, dimensions) for text in texts),
            model=FAKE_MODEL,
            input_tokens=sum(_word_count(text) for text in texts),
            cost_micros=0,
        )
