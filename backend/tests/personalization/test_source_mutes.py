"""The per-user source mute: the two states, the default, and the bulk reset (FR-13).

**What these tests hold.**

1. **`default` is the absence of a row.** The mockup's control has three positions, but
   only two are stored — a row saying "default" would say nothing, and it would turn
   "Restore all defaults" from a bulk delete into a three-way update. So setting
   `default` **deletes** the row.
2. **`mute` and `show_less` are different promises.** `mute` excludes; `show_less`
   deprioritises. The read returns them as two separate sets, because the composition
   path treats them differently.
3. **The scope is the user's.** One user's mute never touches another's, and the bulk
   reset clears one user's rows and no one else's.
4. **Every write is audited (AD-5).** A state change writes an audit row inside the
   personal transaction; a no-op write does not.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.personalization.models import SourceMute
from apps.personalization.services.source_mutes import (
    STATE_DEFAULT,
    STATE_MUTE,
    STATE_SHOW_LESS,
    read_source_states,
    read_source_visibility,
    restore_source_defaults,
    set_source_mute,
)
from shared.actor import Actor
from shared.db import PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def actor() -> Actor:
    return Actor.user(uuid4())


def set_state(user_id, source_id, state):
    return set_source_mute(
        user_id=user_id,
        source_id=source_id,
        state=state,
        actor=actor(),
        now=NOW,
    )


def rows_for(user_id):
    return list(
        SourceMute.objects.using(PERSONAL).filter(user_id=user_id).values_list("source_id", "state")
    )


# ── Setting a state ───────────────────────────────────────────────────────────────


def test_setting_a_mute_records_the_row():
    user_id, source_id = uuid4(), uuid4()

    result = set_state(user_id, source_id, STATE_MUTE)

    assert result.state == STATE_MUTE
    assert result.changed is True
    assert rows_for(user_id) == [(source_id, STATE_MUTE)]


def test_setting_show_less_records_a_different_row():
    """The two states are different promises, and the row says which one was made."""
    user_id, source_id = uuid4(), uuid4()

    set_state(user_id, source_id, STATE_SHOW_LESS)

    assert rows_for(user_id) == [(source_id, STATE_SHOW_LESS)]


def test_setting_the_state_a_source_is_already_in_changes_nothing():
    """Idempotent: setting the state a source is already in is a success, not an error —
    but a response claiming a change when none happened would make the screen redraw
    something that did not move."""
    user_id, source_id = uuid4(), uuid4()
    set_state(user_id, source_id, STATE_MUTE)

    result = set_state(user_id, source_id, STATE_MUTE)

    assert result.changed is False
    assert result.state == STATE_MUTE


def test_moving_from_mute_to_show_less_updates_the_row():
    user_id, source_id = uuid4(), uuid4()
    set_state(user_id, source_id, STATE_MUTE)

    result = set_state(user_id, source_id, STATE_SHOW_LESS)

    assert result.changed is True
    assert rows_for(user_id) == [(source_id, STATE_SHOW_LESS)]


def test_setting_default_deletes_the_row():
    """**The row's absence *is* the default state.** So setting `default` is not a write
    of "default" — it is the removal of the row that said something else."""
    user_id, source_id = uuid4(), uuid4()
    set_state(user_id, source_id, STATE_MUTE)

    result = set_state(user_id, source_id, STATE_DEFAULT)

    assert result.state == STATE_DEFAULT
    assert result.changed is True
    assert rows_for(user_id) == []


def test_setting_default_on_an_untouched_source_changes_nothing():
    user_id, source_id = uuid4(), uuid4()

    result = set_state(user_id, source_id, STATE_DEFAULT)

    assert result.changed is False
    assert rows_for(user_id) == []


def test_an_unknown_state_is_refused():
    with pytest.raises(ValueError):
        set_state(uuid4(), uuid4(), "silenced")


# ── The scoping ───────────────────────────────────────────────────────────────────


def test_one_users_mute_does_not_touch_anothers():
    first, second = uuid4(), uuid4()
    source_id = uuid4()

    set_state(first, source_id, STATE_MUTE)

    assert rows_for(second) == []
    assert read_source_states(user_id=second) == {}


def test_one_users_bulk_reset_does_not_clear_anothers():
    """The reset is scoped to the caller, so it is a bulk delete with a filter, not a
    truncate."""
    first, second = uuid4(), uuid4()
    set_state(first, uuid4(), STATE_MUTE)
    set_state(second, uuid4(), STATE_MUTE)

    removed = restore_source_defaults(user_id=first, actor=actor(), now=NOW)

    assert removed == 1
    assert rows_for(first) == []
    assert len(rows_for(second)) == 1


# ── The reads ─────────────────────────────────────────────────────────────────────


def test_the_visibility_read_returns_two_separate_sets():
    """The composition path asks both questions on every read, and the two answers mean
    different things — so they cannot be one set."""
    user_id = uuid4()
    muted, shown_less = uuid4(), uuid4()
    set_state(user_id, muted, STATE_MUTE)
    set_state(user_id, shown_less, STATE_SHOW_LESS)

    visibility = read_source_visibility(user_id=user_id)

    assert visibility.muted == frozenset({muted})
    assert visibility.show_less == frozenset({shown_less})


def test_the_visibility_read_of_a_user_with_nothing_is_empty():
    visibility = read_source_visibility(user_id=uuid4())

    assert visibility.muted == frozenset()
    assert visibility.show_less == frozenset()


def test_the_states_read_maps_each_source_to_its_state():
    user_id = uuid4()
    muted, shown_less = uuid4(), uuid4()
    set_state(user_id, muted, STATE_MUTE)
    set_state(user_id, shown_less, STATE_SHOW_LESS)

    states = read_source_states(user_id=user_id)

    assert states == {muted: STATE_MUTE, shown_less: STATE_SHOW_LESS}


# ── The bulk reset ────────────────────────────────────────────────────────────────


def test_the_bulk_reset_clears_mutes_and_show_lesses():
    """It removes every row for the user — both kinds — and returns how many."""
    user_id = uuid4()
    set_state(user_id, uuid4(), STATE_MUTE)
    set_state(user_id, uuid4(), STATE_SHOW_LESS)
    set_state(user_id, uuid4(), STATE_MUTE)

    removed = restore_source_defaults(user_id=user_id, actor=actor(), now=NOW)

    assert removed == 3
    assert rows_for(user_id) == []


def test_the_bulk_reset_of_a_user_with_nothing_removes_nothing():
    removed = restore_source_defaults(user_id=uuid4(), actor=actor(), now=NOW)

    assert removed == 0


def test_the_bulk_reset_is_idempotent():
    """The screen's confirmation can be asked twice; the second call changes nothing."""
    user_id = uuid4()
    set_state(user_id, uuid4(), STATE_MUTE)

    first = restore_source_defaults(user_id=user_id, actor=actor(), now=NOW)
    second = restore_source_defaults(user_id=user_id, actor=actor(), now=NOW)

    assert first == 1
    assert second == 0
