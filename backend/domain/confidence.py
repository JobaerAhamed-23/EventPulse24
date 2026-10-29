"""Publication gates for confidence scores (AD-6, AD-8; design D6).

Scores are two-decimal `Decimal`s in [0, 1] (spine: `numeric(3,2)`). Floats are refused: a float
0.7 is slightly below Decimal 0.70 and would land an event in the wrong band. Thresholds live in
`shared.constants`; each lower bound is inclusive.
"""

from decimal import Decimal
from enum import StrEnum

from shared.constants import (
    EXTRACTION_CONFIDENCE_PUBLISH,
    EXTRACTION_CONFIDENCE_REJECT,
    TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH,
    TZ_INFERENCE_CONFIDENCE_DIGEST,
)

_HUNDREDTHS = Decimal("0.01")


class Gate(StrEnum):
    """What may happen to an Event, from least to most strict."""

    PUBLISH = "publish"
    PUBLISH_FLAGGED = "publish_flagged"  # published, digest-eligible, `tz_review_pending`
    IN_REVIEW = "in_review"  # stored, never in a digest until editorial review
    REJECT = "reject"  # never becomes an Event


_STRICTNESS = {gate: rank for rank, gate in enumerate(Gate)}


def checked_confidence(value: Decimal) -> Decimal:
    """Return `value` if it's a finite two-decimal Decimal in [0, 1]; raise otherwise."""
    if type(value) is not Decimal:
        raise TypeError(f"confidence must be a Decimal, not {type(value).__name__}")
    if not value.is_finite() or value.quantize(_HUNDREDTHS) != value or not 0 <= value <= 1:
        raise ValueError(f"confidence must be a two-decimal value in [0, 1], not {value}")
    return value


def tz_gate(confidence: Decimal) -> Gate:
    """FR-60 / AD-6: >= 0.90 publish, >= 0.70 publish flagged, below that in review."""
    confidence = checked_confidence(confidence)
    if confidence >= TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH:
        return Gate.PUBLISH
    if confidence >= TZ_INFERENCE_CONFIDENCE_DIGEST:
        return Gate.PUBLISH_FLAGGED
    return Gate.IN_REVIEW


def extraction_gate(confidence: Decimal) -> Gate:
    """AD-8: below 0.50 reject, below 0.70 in review, otherwise publish."""
    confidence = checked_confidence(confidence)
    if confidence < EXTRACTION_CONFIDENCE_REJECT:
        return Gate.REJECT
    if confidence < EXTRACTION_CONFIDENCE_PUBLISH:
        return Gate.IN_REVIEW
    return Gate.PUBLISH


def combine_gates(*gates: Gate) -> Gate:
    """The strictest gate wins (reject > in review > publish flagged > publish)."""
    if not gates:
        raise ValueError("combine_gates needs at least one gate")
    return max(gates, key=_STRICTNESS.__getitem__)
