"""Embedding port (AD-8): behind the same gateway as the LLM, with the same cost accounting.

Under AD-4 embeddings only route editorial review candidates; they never decide identity.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]  # one per input text, in order
    model: str
    input_tokens: int
    cost_micros: int


class EmbeddingPort(ABC):
    @abstractmethod
    def embed(self, texts: Sequence[str], *, dimensions: int) -> EmbeddingResult:
        """`dimensions` is the Matryoshka truncation; the spine leaves 512 vs 256 open."""
