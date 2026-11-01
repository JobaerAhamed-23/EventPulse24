"""The custom slot's grammar: `custom:<minutes>` (FR-9, AD-8, AD-16).

**The id *is* the offset.** `custom:90` is 90 minutes before the event. The choice
between an encoded id and a new column was made for a reason worth keeping visible: AD-7's
send key already names the custom slot **by its id**, so the id is already a first-class
part of the key. A slot whose id *is* its offset cannot disagree with itself; a second
column would be a second place for the same fact, and the failure mode would be a
reminder that fires at the wrong hour.

So the grammar is the whole contract, and these tests pin it:

- the bounds are the UX spec's — **15 minutes to 30 days** (EXPERIENCE.md);
- a negative offset is refused, because a reminder *after* the event is not a reminder;
- a named tier is never mistaken for a custom one, and a custom one is never mistaken for
  a named tier;
- at most one custom slot per plan (FR-9).
"""

import pytest

from apps.delivery.services.slots import (
    InvalidCustomSlotError,
    TooManyCustomSlotsError,
    TooManySlotsError,
    UnknownSlotError,
    custom_slot_minutes,
    is_custom_slot,
    validate_slots,
)
from domain.errors import ValidationError
from shared.constants import (
    CUSTOM_SLOT_MAX_MINUTES,
    CUSTOM_SLOT_MIN_MINUTES,
    CUSTOM_SLOT_PREFIX,
)

# --- The grammar -------------------------------------------------------------------------------


def test_a_custom_slots_id_carries_its_offset():
    assert custom_slot_minutes(f"{CUSTOM_SLOT_PREFIX}90") == 90


def test_the_minimum_offset_is_accepted():
    assert custom_slot_minutes(f"{CUSTOM_SLOT_PREFIX}{CUSTOM_SLOT_MIN_MINUTES}") == 15


def test_the_maximum_offset_is_accepted():
    assert custom_slot_minutes(f"{CUSTOM_SLOT_PREFIX}{CUSTOM_SLOT_MAX_MINUTES}") == 43200


def test_a_named_slot_has_no_offset():
    assert custom_slot_minutes("1d") is None
    assert custom_slot_minutes("1hr") is None


def test_a_named_slot_is_not_a_custom_slot():
    assert is_custom_slot("1d") is False
    assert is_custom_slot("5d") is False


def test_a_custom_slot_is_recognised_by_its_prefix():
    assert is_custom_slot(f"{CUSTOM_SLOT_PREFIX}90") is True


def test_a_malformed_suffix_has_no_offset():
    """Not a number, so no offset — and never a guessed one."""
    assert custom_slot_minutes(f"{CUSTOM_SLOT_PREFIX}my-slot") is None
    assert custom_slot_minutes(f"{CUSTOM_SLOT_PREFIX}") is None
    assert custom_slot_minutes(f"{CUSTOM_SLOT_PREFIX}90.5") is None
    assert custom_slot_minutes(f"{CUSTOM_SLOT_PREFIX} 90") is None


def test_a_non_ascii_digit_has_no_offset():
    """`"١٢".isdigit()` is True and `int("١٢")` is 12 — but the id must stay plain ASCII.

    A non-ASCII character in a send key is a key that survives log scrubbing by accident
    rather than by design, and AD-13's scrubbing patterns are tuned for ASCII runs.
    """
    assert custom_slot_minutes(f"{CUSTOM_SLOT_PREFIX}١٢") is None


# --- The validator -----------------------------------------------------------------------------


def test_a_named_slot_is_accepted():
    validate_slots(["5d", "2d", "1d", "1hr"])


def test_an_empty_list_is_valid():
    """FR-9: "0 slots = no reminders (still in feed)." A deliberate state, not an error."""
    validate_slots([])


def test_five_slots_are_refused():
    with pytest.raises(TooManySlotsError):
        validate_slots(["5d", "2d", "1d", "1hr", f"{CUSTOM_SLOT_PREFIX}90"])


def test_an_unknown_slot_is_refused():
    with pytest.raises(UnknownSlotError):
        validate_slots(["3d"])


def test_a_duplicate_slot_is_refused():
    with pytest.raises(ValidationError):
        validate_slots(["1d", "1d"])


def test_a_custom_slot_is_accepted():
    validate_slots([f"{CUSTOM_SLOT_PREFIX}90"])


def test_a_custom_slot_below_the_minimum_is_refused():
    with pytest.raises(InvalidCustomSlotError):
        validate_slots([f"{CUSTOM_SLOT_PREFIX}{CUSTOM_SLOT_MIN_MINUTES - 1}"])


def test_a_custom_slot_above_the_maximum_is_refused():
    with pytest.raises(InvalidCustomSlotError):
        validate_slots([f"{CUSTOM_SLOT_PREFIX}{CUSTOM_SLOT_MAX_MINUTES + 1}"])


def test_a_negative_custom_slot_is_refused():
    """A reminder *after* the event is not a reminder."""
    with pytest.raises(InvalidCustomSlotError):
        validate_slots([f"{CUSTOM_SLOT_PREFIX}-30"])


def test_a_malformed_custom_slot_is_refused():
    with pytest.raises(InvalidCustomSlotError):
        validate_slots([f"{CUSTOM_SLOT_PREFIX}soon"])


def test_two_custom_slots_are_refused():
    """FR-9: at most one custom slot alongside the named tiers."""
    with pytest.raises(TooManyCustomSlotsError):
        validate_slots([f"{CUSTOM_SLOT_PREFIX}90", f"{CUSTOM_SLOT_PREFIX}120"])


def test_one_custom_slot_alongside_the_named_tiers_is_accepted():
    validate_slots(["5d", "2d", "1d", f"{CUSTOM_SLOT_PREFIX}90"])


def test_the_bounds_are_the_ux_specs():
    """EXPERIENCE.md: "Min: 15 minutes before; max: 30 days before."

    The numbers are the product's, and they live in `shared/constants.py` (AD-8) so the
    validator and the endpoint's description cannot drift apart.
    """
    assert CUSTOM_SLOT_MIN_MINUTES == 15
    assert CUSTOM_SLOT_MAX_MINUTES == 30 * 24 * 60
