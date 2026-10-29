"""Confidence gates (AD-6, AD-8; design D6): exact two-decimal Decimals, inclusive lower bounds."""

from decimal import Decimal

import pytest

from domain.confidence import Gate, checked_confidence, combine_gates, extraction_gate, tz_gate


@pytest.mark.parametrize(
    ("confidence", "gate"),
    [
        ("0.00", Gate.IN_REVIEW),
        ("0.69", Gate.IN_REVIEW),
        ("0.70", Gate.PUBLISH_FLAGGED),
        ("0.89", Gate.PUBLISH_FLAGGED),
        ("0.90", Gate.PUBLISH),
        ("1.00", Gate.PUBLISH),
    ],
)
def test_tz_gate_boundaries(confidence, gate):
    assert tz_gate(Decimal(confidence)) is gate


@pytest.mark.parametrize(
    ("confidence", "gate"),
    [
        ("0.49", Gate.REJECT),
        ("0.50", Gate.IN_REVIEW),
        ("0.69", Gate.IN_REVIEW),
        ("0.70", Gate.PUBLISH),
        ("1.00", Gate.PUBLISH),
    ],
)
def test_extraction_gate_boundaries(confidence, gate):
    assert extraction_gate(Decimal(confidence)) is gate


@pytest.mark.parametrize("value", [0.7, 1, True, None, "0.70"], ids=repr)
def test_confidence_not_a_decimal_raises_type_error(value):
    with pytest.raises(TypeError):
        tz_gate(value)


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "0.705", "1.01", "-0.01"])
def test_confidence_not_a_two_decimal_unit_value_raises_value_error(value):
    with pytest.raises(ValueError):
        checked_confidence(Decimal(value))


def test_float_seventy_hundredths_would_have_landed_below_the_gate():
    # Why floats are refused: the float 0.7 is just under the 0.70 boundary.
    assert Decimal(0.7) < Decimal("0.70")


@pytest.mark.parametrize(
    ("gates", "strictest"),
    [
        ((Gate.PUBLISH,), Gate.PUBLISH),
        ((Gate.PUBLISH, Gate.PUBLISH_FLAGGED), Gate.PUBLISH_FLAGGED),
        ((Gate.PUBLISH_FLAGGED, Gate.IN_REVIEW, Gate.PUBLISH), Gate.IN_REVIEW),
        ((Gate.IN_REVIEW, Gate.REJECT), Gate.REJECT),
    ],
)
def test_combine_gates_strictest_wins(gates, strictest):
    assert combine_gates(*gates) is strictest


def test_combine_gates_with_nothing_raises():
    with pytest.raises(ValueError):
        combine_gates()
