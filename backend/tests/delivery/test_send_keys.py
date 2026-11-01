"""AD-7 send keys: the shapes, and the rule that no key is a function of time.

No Django, no database — these are pure string builders, and keeping the tests that way means
the key's shape can be asserted without a fixture.
"""

import inspect
from datetime import date
from uuid import UUID

import pytest

from apps.delivery import send_keys
from apps.delivery.send_keys import (
    SEND_KEY_MAX_LENGTH,
    digest_key,
    digest_local_date_from_key,
    event_reminder_key,
    personal_reminder_key,
    state_notice_key,
)
from shared.constants import CUSTOM_SLOT_PREFIX, SEND_KEY_SEPARATOR

USER = UUID("0192f3a0-0000-7000-8000-000000000001")
EVENT = UUID("0192f3a0-0000-7000-8000-000000000002")
CHANGE = UUID("0192f3a0-0000-7000-8000-000000000003")

ALL_BUILDERS = (event_reminder_key, personal_reminder_key, state_notice_key, digest_key)


# --- The four MVP shapes, exactly as AD-7's table writes them ------------------------------------


def test_event_reminder_key_matches_the_spine_shape():
    key = event_reminder_key(user_id=USER, event_id=EVENT, slot="1d", event_version=3)

    assert key == f"{USER}:event_reminder:{EVENT}:1d:3"


def test_personal_reminder_key_matches_the_spine_shape():
    key = personal_reminder_key(
        user_id=USER, personal_event_id=EVENT, slot="1hr", personal_event_revision=7
    )

    assert key == f"{USER}:personal_reminder:{EVENT}:1hr:7"


def test_state_notice_key_matches_the_spine_shape():
    assert state_notice_key(user_id=USER, state_change_id=CHANGE) == (
        f"{USER}:state_notice:{CHANGE}"
    )


def test_digest_key_matches_the_spine_shape():
    assert digest_key(user_id=USER, local_date=date(2026, 11, 14)) == (f"{USER}:digest:2026-11-14")


# --- The rule this module exists for --------------------------------------------------------------


@pytest.mark.parametrize("builder", ALL_BUILDERS, ids=lambda b: b.__name__)
def test_no_key_builder_accepts_a_time(builder):
    """AD-7: the key is "never derived from `due_at`".

    Checked mechanically rather than remembered. A builder that grew a `due_at`, `now`,
    `when` or `instant` parameter would make every preference change mint a duplicate send,
    and the failure would be invisible until a user complained about four copies of one
    reminder.

    `local_date` is deliberately allowed: AD-7's own table keys the digest by the user's local
    date. It identifies *which day's digest*, not *when the send goes* — the digest's `due_at`
    is the user's delivery time, which is a different value entirely and is not here.
    """
    forbidden = {"due_at", "now", "when", "instant", "send_at", "at", "timestamp"}

    params = set(inspect.signature(builder).parameters)

    assert not (params & forbidden), f"{builder.__name__} takes a time: {params & forbidden}"


@pytest.mark.parametrize("builder", ALL_BUILDERS, ids=lambda b: b.__name__)
def test_every_builder_is_keyword_only(builder):
    """Positional args would make two UUIDs interchangeable at a call site."""
    kinds = {p.kind for p in inspect.signature(builder).parameters.values()}

    assert kinds == {inspect.Parameter.KEYWORD_ONLY}


def test_the_same_inputs_always_produce_the_same_key():
    first = event_reminder_key(user_id=USER, event_id=EVENT, slot="1d", event_version=3)
    second = event_reminder_key(user_id=USER, event_id=EVENT, slot="1d", event_version=3)

    assert first == second


def test_a_different_event_version_is_a_different_key():
    """AD-7: a moved event mints new rows, and the old key stays spent."""
    old = event_reminder_key(user_id=USER, event_id=EVENT, slot="1d", event_version=3)
    new = event_reminder_key(user_id=USER, event_id=EVENT, slot="1d", event_version=4)

    assert old != new


def test_a_different_slot_is_a_different_key():
    one_day = event_reminder_key(user_id=USER, event_id=EVENT, slot="1d", event_version=1)
    one_hour = event_reminder_key(user_id=USER, event_id=EVENT, slot="1hr", event_version=1)

    assert one_day != one_hour


# --- The separator, and why it is ":" (AD-13) -----------------------------------------------------


def test_the_separator_keeps_each_uuid_a_thirty_six_character_run():
    """Coding standard: ":" "keeps each UUID a 36-character run, so keys survive log scrubbing".

    A "-" separator would break a UUID's own hyphenation into an ambiguous run and defeat a
    scrubber looking for UUID-shaped text.
    """
    key = event_reminder_key(user_id=USER, event_id=EVENT, slot="1d", event_version=1)

    assert SEND_KEY_SEPARATOR == ":"
    assert str(USER) in key
    assert str(EVENT) in key
    for part in key.split(SEND_KEY_SEPARATOR):
        assert len(part) == 36 or "-" not in part


def test_a_custom_slot_fits_in_a_key():
    custom = f"{CUSTOM_SLOT_PREFIX}{EVENT}"

    key = personal_reminder_key(
        user_id=USER, personal_event_id=EVENT, slot=custom, personal_event_revision=12
    )

    assert custom in key
    assert len(key) <= SEND_KEY_MAX_LENGTH


def test_the_longest_realistic_key_fits_the_column():
    """The arithmetic in `send_keys`' header, checked rather than trusted."""
    longest = personal_reminder_key(
        user_id=USER,
        personal_event_id=EVENT,
        slot=f"{CUSTOM_SLOT_PREFIX}{EVENT}",
        personal_event_revision=9999999999,
    )

    assert len(longest) <= SEND_KEY_MAX_LENGTH


# --- The Pulse Ping is reserved, not built --------------------------------------------------------


def test_there_is_no_pulse_ping_key_builder():
    """MVP's digest email **is** the Pulse Ping (decided 2026-10-31).

    A builder for a key nothing mints would be dead code that looks like a feature.
    """
    assert not [name for name in dir(send_keys) if "pulse_ping" in name]


# --- The digest key's inverse: the local date, read back out --------------------------------------


def test_the_digest_local_date_round_trips_through_its_key():
    """The builder and its inverse are one piece of knowledge about one string."""
    day = date(2026, 11, 11)

    key = digest_key(user_id=USER, local_date=day)

    assert digest_local_date_from_key(key) == day


def test_the_digest_local_date_is_none_for_a_key_that_is_not_a_digest():
    """`None` means "this is not a digest key" — and the caller skips rather than guesses."""
    key = event_reminder_key(user_id=USER, event_id=EVENT, slot="1d", event_version=3)

    assert digest_local_date_from_key(key) is None


def test_the_digest_local_date_is_none_when_the_key_has_the_wrong_number_of_parts():
    """The parse is strict: exactly three parts, or it is not a digest key."""
    assert digest_local_date_from_key(f"{USER}:digest") is None
    assert digest_local_date_from_key(f"{USER}:digest:2026-11-11:extra") is None


def test_the_digest_local_date_is_none_when_the_date_is_not_a_date():
    """A date that cannot be read is never approximated.

    A digest shifted to the wrong day is a digest that goes out at the wrong hour on the
    wrong day, so a malformed date reads as "no date" rather than as a guess.
    """
    assert digest_local_date_from_key(f"{USER}:digest:not-a-date") is None
    assert digest_local_date_from_key(f"{USER}:digest:2026-13-45") is None
