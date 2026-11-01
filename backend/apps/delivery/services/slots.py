"""The Reminder Plan slot rule (FR-9), in one place.

**Why this is its own module.** Two commands validate a slot list — `reminder_plans` for one
event's plan, and `notification_preferences` for the default that new plans start from (FR-20)
— and `reminder_plans` reads the stored default, so it depends on `notification_preferences`.
Leaving the rule in `reminder_plans` would make that dependency circular. One leaf module both
import gives a single direction:

    reminder_plans -> notification_preferences -> slots

AD-16's point exactly: one rule, one declaration. Two copies of "at most four slots" would be
free to drift, and the drift would be a plan the API accepts and the database then rejects.

The database enforces the same bound (`reminder_plan_slots_max_4_ck`,
`notification_preference_slots_max_4_ck`); this layer checks it too so the caller gets a
readable error rather than an `IntegrityError`.
"""

from collections.abc import Sequence

from domain.errors import ValidationError
from shared.constants import (
    CUSTOM_SLOT_MAX_MINUTES,
    CUSTOM_SLOT_MIN_MINUTES,
    CUSTOM_SLOT_PREFIX,
    REMINDER_PLAN_MAX_SLOTS,
    ReminderSlot,
)

# FR-9: "up to 4 reminder slots".
MAX_SLOTS = REMINDER_PLAN_MAX_SLOTS

# The four named tiers, by value. A custom slot is identified by its own id and is not a
# member of the enum, so it is looked up separately.
_NAMED_SLOTS = frozenset(slot.value for slot in ReminderSlot)


class TooManySlotsError(ValidationError):
    """More than FR-9's four slots were requested."""

    default_message = f"A reminder plan holds at most {MAX_SLOTS} reminders."


class UnknownSlotError(ValidationError):
    """A slot that is neither a named tier nor a custom slot id."""

    default_message = "That reminder time isn't one we recognise."


class InvalidCustomSlotError(ValidationError):
    """A custom slot whose offset is outside the UX spec's bounds, or is not an integer.

    The bound is the product's: EXPERIENCE.md — *"Min: 15 minutes before; max: 30 days
    before. Out-of-range snaps back."* A negative offset would be a reminder **after** the
    event, which is not a reminder at all, and the lower bound refuses it before the
    arithmetic could produce one.
    """

    default_message = "That reminder time is outside the range we can schedule."


class TooManyCustomSlotsError(ValidationError):
    """More than one custom slot in one plan."""

    default_message = "A reminder plan holds at most one custom reminder."


def custom_slot_minutes(slot: str) -> int | None:
    """The offset a custom slot carries, in minutes before the event — or None.

    `None` means **the id is not a well-formed custom slot**: either it is a named tier,
    or its suffix is not a plain integer. The caller decides what to do about that; this
    function never guesses, because a guess about an offset is a reminder at the wrong
    hour.

    The grammar is `custom:<minutes>` and the minutes are a plain integer — **no sign, no
    decimal point, no whitespace**. A signed value would let `custom:-30` through the
    parse and produce a reminder after the event; a decimal one would silently truncate
    to a different minute than the user chose.
    """
    if not slot.startswith(CUSTOM_SLOT_PREFIX):
        return None
    suffix = slot[len(CUSTOM_SLOT_PREFIX) :]
    if not suffix.isdigit():
        return None
    # `isdigit()` is True for some non-ASCII digits (e.g. "١٢"), which `int()` accepts and
    # which would put a non-ASCII character into a send key. The ASCII check keeps the id
    # and the key plain.
    if not suffix.isascii():
        return None
    return int(suffix)


def is_custom_slot(slot: str) -> bool:
    """Whether this id is a custom slot's — whatever its offset says."""
    return slot.startswith(CUSTOM_SLOT_PREFIX)


def validate_slots(slots: Sequence[str]) -> None:
    """Check a slot list against FR-9's rule.

    An **empty** list is valid: FR-9 says "0 slots = no reminders (still in feed)", and FR-20
    says "the user can remove all reminders". Emptiness is a deliberate state, not an error.

    Raises:
        TooManySlotsError: more than `MAX_SLOTS` slots.
        UnknownSlotError: a slot that is neither a named tier nor a custom slot id.
        InvalidCustomSlotError: a custom slot whose offset is not an integer in bounds.
        TooManyCustomSlotsError: more than one custom slot.
        ValidationError: the same slot appears twice.
    """
    if len(slots) > MAX_SLOTS:
        raise TooManySlotsError(details={"max_slots": MAX_SLOTS, "given": len(slots)})
    custom_count = 0
    for slot in slots:
        # A named tier, or a custom slot: the user's own id (AD-7's send key names the custom
        # slot by id). A custom slot is identified by a prefix, so it can never be mistaken
        # for one of the four named tiers.
        if slot in _NAMED_SLOTS:
            continue
        if not slot.startswith(CUSTOM_SLOT_PREFIX):
            raise UnknownSlotError(details={"slot": slot})
        custom_count += 1
        minutes = custom_slot_minutes(slot)
        if minutes is None:
            raise InvalidCustomSlotError(details={"slot": slot})
        if not CUSTOM_SLOT_MIN_MINUTES <= minutes <= CUSTOM_SLOT_MAX_MINUTES:
            raise InvalidCustomSlotError(
                details={
                    "slot": slot,
                    "minutes": minutes,
                    "min_minutes": CUSTOM_SLOT_MIN_MINUTES,
                    "max_minutes": CUSTOM_SLOT_MAX_MINUTES,
                }
            )
    if custom_count > 1:
        raise TooManyCustomSlotsError(details={"given": custom_count})
    if len(set(slots)) != len(slots):
        raise ValidationError("A reminder plan holds each slot once.")
