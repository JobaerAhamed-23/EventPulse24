"""LLM port (AD-8): one gateway owns provider choice, fallback and cost accounting.

Starter shape; the extraction intent reshapes it (structured output, Pydantic schemas).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMRequest:
    task: str  # stable slug for cost accounting, e.g. "extract_event"
    instructions: str
    # AD-9: source content is untrusted. Kept apart so the adapter always delimits it.
    untrusted_content: str


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_micros: int  # integer micro-dollars, never a float


class LLMPort(ABC):
    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResult: ...
