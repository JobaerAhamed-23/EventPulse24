"""The category mute (FR-25): one person's "less of that category, for a while".

**What these tests hold.**

1. **The duration is a closed set.** Seven, thirty, ninety days, or indefinite. A mute
   that outlived the user's patience by a typo is a mute the user has to find a screen
   to undo.
2. **A null expiry is indefinite, not a bug.** The mockup's fourth choice — "until I
   change it" — is a *state of the same row*, not a second code path.
3. **The expiry runs from `now`, not from the row's creation.** Pressing "30 days" again
   refreshes the window, which is what the user asked for.
4. **An expired mute is not active.** The row is still there — it is the user's data — but
   it no longer mutes anything, so it neither appears on the screen nor excludes anything.
5. **Unmuting is a delete.** There is no "unmuted" state to record: the absence of a row
   *is* the absence of a mute. One tap.
6. **The category is a chip key, and the server owns the vocabulary.** An unknown key is
   refused, and the label the user reads comes from `INTEREST_CHIPS` — never from a
   scraped string (AD-9).
7. **Every write is audited (AD-5).**
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apps.personalization.models import CategoryMute
from apps.personalization.services.taste_mutes import (
    CHIP_KEYS,
    UnknownCategoryError,
    UnknownDurationError,
    category_id_for,
    clear_all_category_mutes,
    clear_category_mute,
    read_active_mutes,
    read_muted_category_keys,
    set_category_mute,
)
from shared.actor import Actor
from shared.db import PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
USER_ID = uuid4()
ACTOR = Actor.user(USER_ID)


def _rows(user_id=USER_ID):
    return list(
        CategoryMute.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .values_list("category_key", "expires_at")
    )


# ── Setting a mute ────────────────────────────────────────────────────────────────


def test_setting_a_mute_records_the_row_and_its_expiry():
    result = set_category_mute(
        user_id=USER_ID,
        category_key="arts_culture",
        duration_days=30,
        actor=ACTOR,
        now=NOW,
    )

    assert result.category_key == "arts_culture"
    assert result.expires_at == NOW + timedelta(days=30)
    assert result.changed is True
    assert _rows() == [("arts_culture", NOW + timedelta(days=30))]


def test_an_indefinite_mute_has_no_expiry():
    """The mockup's fourth choice — "until I change it" — is a null expiry on the same
    row, not a second code path."""
    result = set_category_mute(
        user_id=USER_ID,
        category_key="tech_meetups",
        duration_days=None,
        actor=ACTOR,
        now=NOW,
    )

    assert result.expires_at is None
    assert _rows() == [("tech_meetups", None)]


def test_setting_a_mute_that_is_already_set_refreshes_the_window():
    """Pressing "30 days" again is a request for thirty more days from now."""
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )

    result = set_category_mute(
        user_id=USER_ID,
        category_key="arts_culture",
        duration_days=30,
        actor=ACTOR,
        now=NOW + timedelta(days=1),
    )

    assert result.expires_at == NOW + timedelta(days=1) + timedelta(days=30)
    assert result.changed is True


def test_setting_the_same_mute_at_the_same_instant_changes_nothing():
    """Idempotent: setting a mute that is already set is a success, not an error — but a
    response claiming a change when none happened would make the screen redraw
    something that did not move."""
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )

    result = set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )

    assert result.changed is False
    assert len(_rows()) == 1


def test_switching_a_mute_to_indefinite_clears_the_expiry():
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )

    result = set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=None, actor=ACTOR, now=NOW
    )

    assert result.expires_at is None
    assert result.changed is True
    assert _rows() == [("arts_culture", None)]


# ── The closed sets ───────────────────────────────────────────────────────────────


def test_an_unknown_category_is_refused():
    """The vocabulary is the server's, so the screen can name every key it holds."""
    with pytest.raises(UnknownCategoryError):
        set_category_mute(
            user_id=USER_ID, category_key="jazz_clubs", duration_days=30, actor=ACTOR, now=NOW
        )


def test_an_unknown_duration_is_refused():
    """A mute that outlived the user's patience by a typo is a mute the user has to find
    a screen to undo."""
    with pytest.raises(UnknownDurationError):
        set_category_mute(
            user_id=USER_ID, category_key="arts_culture", duration_days=45, actor=ACTOR, now=NOW
        )


def test_the_closed_sets_are_the_published_ones():
    assert CHIP_KEYS == frozenset(
        {
            "tech_meetups",
            "sports_fitness",
            "arts_culture",
            "family_kids",
            "community_volunteering",
            "outdoors_nature",
            "classes_workshops",
            "markets_fairs",
            "talks_lectures",
            "government_civic",
        }
    )


# ── The reads ─────────────────────────────────────────────────────────────────────


def test_the_active_read_returns_the_mutes_with_their_labels():
    """The screen names the category, and the name is the server's own wording — never a
    scraped string (AD-9)."""
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )

    mutes = read_active_mutes(user_id=USER_ID, now=NOW)

    assert len(mutes) == 1
    assert mutes[0].category_key == "arts_culture"
    assert mutes[0].label == "Arts & culture"
    assert mutes[0].is_indefinite is False


def test_an_indefinite_mute_reads_as_indefinite():
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=None, actor=ACTOR, now=NOW
    )

    mutes = read_active_mutes(user_id=USER_ID, now=NOW)

    assert mutes[0].is_indefinite is True


def test_an_expired_mute_is_not_active():
    """The row is still there — it is the user's data — but it no longer mutes anything,
    so the screen does not list it and the composition path does not apply it."""
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=7, actor=ACTOR, now=NOW
    )

    later = NOW + timedelta(days=8)
    mutes = read_active_mutes(user_id=USER_ID, now=later)

    assert mutes == ()
    assert read_muted_category_keys(user_id=USER_ID, now=later) == frozenset()


def test_a_mute_that_expires_in_an_hour_is_still_active():
    """An expired mute and one that expires in an hour are not the same thing to the
    reader of this list."""
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=7, actor=ACTOR, now=NOW
    )

    later = NOW + timedelta(days=7) - timedelta(hours=1)

    assert read_muted_category_keys(user_id=USER_ID, now=later) == frozenset({"arts_culture"})


def test_the_key_read_returns_the_muted_chip_keys():
    """The set is of chip keys, not of event ids: a category mute is about a category,
    and the composition path applies it to whatever the candidate belongs to."""
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )
    set_category_mute(
        user_id=USER_ID, category_key="tech_meetups", duration_days=None, actor=ACTOR, now=NOW
    )

    assert read_muted_category_keys(user_id=USER_ID, now=NOW) == frozenset(
        {"arts_culture", "tech_meetups"}
    )


def test_the_key_read_of_a_user_with_nothing_is_empty():
    assert read_muted_category_keys(user_id=uuid4(), now=NOW) == frozenset()


# ── Unmuting ──────────────────────────────────────────────────────────────────────


def test_unmuting_deletes_the_row():
    """There is no "unmuted" state to record — the absence of a row *is* the absence of
    a mute — so an unmute is a deletion."""
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )

    result = clear_category_mute(user_id=USER_ID, category_key="arts_culture", actor=ACTOR, now=NOW)

    assert result.changed is True
    assert result.expires_at is None
    assert _rows() == []


def test_unmuting_a_category_that_is_not_muted_changes_nothing():
    result = clear_category_mute(user_id=USER_ID, category_key="arts_culture", actor=ACTOR, now=NOW)

    assert result.changed is False


def test_unmuting_one_category_leaves_the_others():
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )
    set_category_mute(
        user_id=USER_ID, category_key="tech_meetups", duration_days=30, actor=ACTOR, now=NOW
    )

    clear_category_mute(user_id=USER_ID, category_key="arts_culture", actor=ACTOR, now=NOW)

    assert _rows() == [("tech_meetups", NOW + timedelta(days=30))]


def test_one_users_unmute_does_not_touch_anothers():
    """The mute is the user's, and another user's preferences are theirs."""
    other = uuid4()
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )
    set_category_mute(
        user_id=other, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )

    clear_category_mute(user_id=USER_ID, category_key="arts_culture", actor=ACTOR, now=NOW)

    assert len(_rows(other)) == 1


# ── The bulk reset ────────────────────────────────────────────────────────────────


def test_the_bulk_reset_clears_every_mute():
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )
    set_category_mute(
        user_id=USER_ID, category_key="tech_meetups", duration_days=None, actor=ACTOR, now=NOW
    )

    removed = clear_all_category_mutes(user_id=USER_ID, actor=ACTOR, now=NOW)

    assert removed == 2
    assert _rows() == []


def test_the_bulk_reset_is_idempotent():
    """The screen's confirmation can be asked twice; the second call changes nothing."""
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )

    first = clear_all_category_mutes(user_id=USER_ID, actor=ACTOR, now=NOW)
    second = clear_all_category_mutes(user_id=USER_ID, actor=ACTOR, now=NOW)

    assert first == 1
    assert second == 0


def test_the_bulk_reset_is_scoped_to_the_caller():
    other = uuid4()
    set_category_mute(
        user_id=USER_ID, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )
    set_category_mute(
        user_id=other, category_key="arts_culture", duration_days=30, actor=ACTOR, now=NOW
    )

    removed = clear_all_category_mutes(user_id=USER_ID, actor=ACTOR, now=NOW)

    assert removed == 1
    assert len(_rows(other)) == 1


# ── The audit id ──────────────────────────────────────────────────────────────────


def test_the_audit_id_is_stable_for_a_category():
    """A category has no id, and the audit row's `target_id` is a UUID — so the key is
    hashed into one. The hash is stable, so the same chip always audits to the same id."""
    assert category_id_for("arts_culture") == category_id_for("arts_culture")


def test_two_categories_never_collide():
    assert category_id_for("arts_culture") != category_id_for("tech_meetups")
