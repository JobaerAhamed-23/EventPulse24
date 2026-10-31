"""Resolving a conflict that involves a **saved public event** (FR-58, FR-33).

A pair can name a saved public event on one side — the user saved a public event and it
clashed with one of their own. Until now nothing could close that pair: the resolve
endpoint only accepted a personal event as the side to act on, and `skip_public` did not
exist.

**The action determines which side it acts on.** `skip_public` *is* "the saved side";
`edit_new` and `delete_new` *are* "the personal side"; `keep_both` is about neither. So:

- `skip_public` releases the save, through the existing saved-events command, with its
  audit entry — one path to remove a save, one audit trail.
- `delete_new` refuses a saved side, and `skip_public` refuses a personal side. A client
  cannot delete a personal event by naming a saved side, and it cannot release somebody
  else's save by naming a personal one.

**"Skip public" is answered, not abandoned.** The pair ends `resolved` with a resolution,
not `cleared_by_state_change` — because the user chose, and a cleared pair is "nobody
answered". That is what `unsave_event(..., keep_pair=…)` is for: the unsave must not
close the pair the user just answered.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from apps.personalization.models import (
    ConflictPair,
    PersonalEvent,
    PersonalizationAuditEntry,
    SavedEvent,
)
from apps.personalization.services.conflict_resolutions import (
    RESOLUTIONS_BY_KIND,
    RESOLUTIONS_BY_KIND_SAVED,
    ConflictPairNotFoundError,
    IllegalResolutionError,
    SideNotInPairError,
    resolve_conflict,
)
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)
END = START + timedelta(hours=2)
TZ = "America/Los_Angeles"

USER = uuid7()
OTHER = uuid7()


def _personal(user_id: UUID = USER, name: str = "Coffee with Sam") -> PersonalEvent:
    return PersonalEvent.objects.using(PERSONAL).create(
        user_id=user_id,
        name=name,
        start_utc=START,
        end_utc=END,
        start_time_tz=TZ,
    )


def _saved(user_id: UUID = USER, event_id=None) -> SavedEvent:
    return SavedEvent.objects.using(PERSONAL).create(
        user_id=user_id,
        event_id=event_id or uuid7(),
        start_utc=START,
        end_utc=END,
        event_version=1,
    )


def _pair(
    user_id: UUID = USER,
    *,
    kind: str = ConflictPair.Kind.TIME,
    left_kind: str = ConflictPair.SideKind.PERSONAL_EVENT,
    left_id: UUID | None = None,
    right_kind: str = ConflictPair.SideKind.SAVED_EVENT,
    right_id: UUID | None = None,
) -> ConflictPair:
    return ConflictPair.objects.using(PERSONAL).create(
        user_id=user_id,
        kind=kind,
        left_kind=left_kind,
        left_id=left_id or uuid7(),
        right_kind=right_kind,
        right_id=right_id or uuid7(),
        status=ConflictPair.Status.ACTIVE,
        detected_at=NOW,
    )


def _mixed_pair(user_id: UUID = USER, *, kind: str = ConflictPair.Kind.TIME):
    """A personal event and a saved public event, and the pair between them."""
    personal = _personal(user_id)
    saved = _saved(user_id)
    pair = ConflictPair.objects.using(PERSONAL).create(
        user_id=user_id,
        kind=kind,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=personal.pk,
        right_kind=ConflictPair.SideKind.SAVED_EVENT,
        right_id=saved.pk,
        status=ConflictPair.Status.ACTIVE,
        detected_at=NOW,
    )
    return personal, saved, pair


# --- The action sets ------------------------------------------------------------------------


def test_a_saved_side_offers_skip_public_instead_of_delete_new():
    # The destructive choice against a save is to *release* it, not to delete it.
    assert RESOLUTIONS_BY_KIND_SAVED[ConflictPair.Kind.TIME] == frozenset(
        {"keep_both", "edit_new", "skip_public"}
    )


def test_a_duplicate_pair_with_a_saved_side_offers_the_same_three():
    # The *kind* decides the middle action's name; the *side's kind* decides the
    # destructive one. A duplicate's middle action is "update the existing one".
    assert RESOLUTIONS_BY_KIND_SAVED[ConflictPair.Kind.DUPLICATE] == frozenset(
        {"keep_both", "update_existing", "skip_public"}
    )


def test_the_personal_side_offers_are_unchanged():
    # The existing personal-vs-personal behaviour is exactly as before.
    assert RESOLUTIONS_BY_KIND[ConflictPair.Kind.TIME] == frozenset(
        {"keep_both", "edit_new", "delete_new"}
    )
    assert RESOLUTIONS_BY_KIND[ConflictPair.Kind.DUPLICATE] == frozenset(
        {"keep_both", "update_existing", "delete_new"}
    )


# --- Skip public ----------------------------------------------------------------------------


def test_skipping_public_releases_the_save_and_records_the_resolution():
    personal, saved, pair = _mixed_pair()

    result = resolve_conflict(
        user_id=USER,
        pair_id=pair.pk,
        resolution="skip_public",
        side_kind=ConflictPair.SideKind.SAVED_EVENT,
        side_id=saved.pk,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert result.resolution == "skip_public"
    # The save is gone.
    assert not SavedEvent.objects.using(PERSONAL).filter(pk=saved.pk).exists()
    # The personal event is untouched — only the save was released.
    assert PersonalEvent.objects.using(PERSONAL).filter(pk=personal.pk).exists()


def test_skipping_public_records_the_resolution_on_the_pair():
    _, saved, pair = _mixed_pair()

    resolve_conflict(
        user_id=USER,
        pair_id=pair.pk,
        resolution="skip_public",
        side_kind=ConflictPair.SideKind.SAVED_EVENT,
        side_id=saved.pk,
        actor=Actor.user(USER),
        now=NOW,
    )

    pair.refresh_from_db()
    # **Resolved, not cleared.** The user answered, so this is their history — not the
    # NULL-resolution `cleared_by_state_change` shape, which means "nobody answered".
    assert pair.status == ConflictPair.Status.RESOLVED
    assert pair.resolution == "skip_public"
    assert pair.resolved_at == NOW


def test_skipping_public_writes_both_audit_rows():
    _, saved, pair = _mixed_pair()

    resolve_conflict(
        user_id=USER,
        pair_id=pair.pk,
        resolution="skip_public",
        side_kind=ConflictPair.SideKind.SAVED_EVENT,
        side_id=saved.pk,
        actor=Actor.user(USER),
        now=NOW,
    )

    # One audit trail per fact: the pair was answered, and the save was released.
    resolved = PersonalizationAuditEntry.objects.using(PERSONAL).get(
        target_id=pair.pk, action="conflict.resolved"
    )
    assert resolved.details["resolution"] == "skip_public"
    assert resolved.details["skipped"] is True
    assert resolved.details["deleted"] is False
    assert (
        PersonalizationAuditEntry.objects.using(PERSONAL)
        .filter(target_id=saved.pk, action="saved_event.unsaved")
        .exists()
    )


def test_skipping_public_leaves_the_indicator_on_the_other_side():
    # "Keep both" keeps the indicator; "skip" clears it by removing the side it was on.
    personal, saved, pair = _mixed_pair()

    resolve_conflict(
        user_id=USER,
        pair_id=pair.pk,
        resolution="skip_public",
        side_kind=ConflictPair.SideKind.SAVED_EVENT,
        side_id=saved.pk,
        actor=Actor.user(USER),
        now=NOW,
    )

    # The save is gone, so there is nothing on the saved side to remind about. The
    # personal side is untouched.
    assert not SavedEvent.objects.using(PERSONAL).filter(pk=saved.pk).exists()
    assert PersonalEvent.objects.using(PERSONAL).filter(pk=personal.pk).exists()


def test_keeping_both_leaves_both_sides_in_place():
    personal, saved, pair = _mixed_pair()

    resolve_conflict(
        user_id=USER,
        pair_id=pair.pk,
        resolution="keep_both",
        side_kind=ConflictPair.SideKind.SAVED_EVENT,
        side_id=saved.pk,
        actor=Actor.user(USER),
        now=NOW,
    )

    # FR-58: "the conflict indicator remains on both Pulse Cards permanently."
    assert SavedEvent.objects.using(PERSONAL).filter(pk=saved.pk).exists()
    assert PersonalEvent.objects.using(PERSONAL).filter(pk=personal.pk).exists()
    pair.refresh_from_db()
    assert pair.status == ConflictPair.Status.RESOLVED
    assert pair.resolution == "keep_both"


def test_a_saved_side_can_also_be_answered_with_keep_both():
    _, saved, pair = _mixed_pair()

    result = resolve_conflict(
        user_id=USER,
        pair_id=pair.pk,
        resolution="keep_both",
        side_kind=ConflictPair.SideKind.SAVED_EVENT,
        side_id=saved.pk,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert result.resolution == "keep_both"


# --- The refusals ---------------------------------------------------------------------------


def test_skip_public_is_refused_against_a_personal_side():
    # There is no save to release, so the action does not apply.
    personal, saved, pair = _mixed_pair()

    with pytest.raises(IllegalResolutionError):
        resolve_conflict(
            user_id=USER,
            pair_id=pair.pk,
            resolution="skip_public",
            side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
            side_id=personal.pk,
            actor=Actor.user(USER),
            now=NOW,
        )

    pair.refresh_from_db()
    assert pair.status == ConflictPair.Status.ACTIVE
    assert pair.resolution is None


def test_delete_new_is_refused_against_a_saved_side():
    # A save cannot be deleted — it can be released.
    personal, saved, pair = _mixed_pair()

    with pytest.raises(IllegalResolutionError):
        resolve_conflict(
            user_id=USER,
            pair_id=pair.pk,
            resolution="delete_new",
            side_kind=ConflictPair.SideKind.SAVED_EVENT,
            side_id=saved.pk,
            actor=Actor.user(USER),
            now=NOW,
        )

    # The save is untouched.
    assert SavedEvent.objects.using(PERSONAL).filter(pk=saved.pk).exists()
    pair.refresh_from_db()
    assert pair.status == ConflictPair.Status.ACTIVE


def test_delete_new_against_the_personal_side_still_works():
    personal, saved, pair = _mixed_pair()

    result = resolve_conflict(
        user_id=USER,
        pair_id=pair.pk,
        resolution="delete_new",
        side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        side_id=personal.pk,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert result.resolution == "delete_new"
    assert not PersonalEvent.objects.using(PERSONAL).filter(pk=personal.pk).exists()
    # The save is untouched — deleting the personal event does not release the save.
    assert SavedEvent.objects.using(PERSONAL).filter(pk=saved.pk).exists()


def test_a_side_that_is_not_in_the_pair_is_refused():
    # The request names a record that has nothing to do with this conflict.
    _, saved, pair = _mixed_pair()

    with pytest.raises(SideNotInPairError):
        resolve_conflict(
            user_id=USER,
            pair_id=pair.pk,
            resolution="skip_public",
            side_kind=ConflictPair.SideKind.SAVED_EVENT,
            side_id=uuid7(),
            actor=Actor.user(USER),
            now=NOW,
        )

    pair.refresh_from_db()
    assert pair.status == ConflictPair.Status.ACTIVE


def test_another_users_pair_is_not_found():
    _, saved, pair = _mixed_pair(OTHER)

    with pytest.raises(ConflictPairNotFoundError):
        resolve_conflict(
            user_id=USER,
            pair_id=pair.pk,
            resolution="skip_public",
            side_kind=ConflictPair.SideKind.SAVED_EVENT,
            side_id=saved.pk,
            actor=Actor.user(USER),
            now=NOW,
        )


def test_a_side_belonging_to_another_user_is_not_reachable():
    # The pair is the caller's, but the side it names is somebody else's save. The
    # lookup is scoped to the caller, so the save is not found and the resolution is
    # refused — no leak, and no un-save of another user's row.
    own_saved = _saved(USER)
    theirs = _saved(OTHER)
    pair = _pair(
        USER,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=_personal(USER).pk,
        right_kind=ConflictPair.SideKind.SAVED_EVENT,
        right_id=theirs.pk,
    )

    with pytest.raises(ConflictPairNotFoundError):
        resolve_conflict(
            user_id=USER,
            pair_id=pair.pk,
            resolution="skip_public",
            side_kind=ConflictPair.SideKind.SAVED_EVENT,
            side_id=theirs.pk,
            actor=Actor.user(USER),
            now=NOW,
        )

    # Their save is untouched, and so is the caller's own save.
    assert SavedEvent.objects.using(PERSONAL).filter(pk=theirs.pk).exists()
    assert SavedEvent.objects.using(PERSONAL).filter(pk=own_saved.pk).exists()


def test_answering_twice_is_refused():
    from apps.personalization.services.conflict_resolutions import ConflictAlreadyResolvedError

    _, saved, pair = _mixed_pair()
    resolve_conflict(
        user_id=USER,
        pair_id=pair.pk,
        resolution="keep_both",
        side_kind=ConflictPair.SideKind.SAVED_EVENT,
        side_id=saved.pk,
        actor=Actor.user(USER),
        now=NOW,
    )

    with pytest.raises(ConflictAlreadyResolvedError):
        resolve_conflict(
            user_id=USER,
            pair_id=pair.pk,
            resolution="skip_public",
            side_kind=ConflictPair.SideKind.SAVED_EVENT,
            side_id=saved.pk,
            actor=Actor.user(USER),
            now=NOW,
        )


# --- The duplicate kind ----------------------------------------------------------------------


def test_a_duplicate_pair_with_a_saved_side_can_be_skipped():
    _, saved, pair = _mixed_pair(kind=ConflictPair.Kind.DUPLICATE)

    result = resolve_conflict(
        user_id=USER,
        pair_id=pair.pk,
        resolution="skip_public",
        side_kind=ConflictPair.SideKind.SAVED_EVENT,
        side_id=saved.pk,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert result.resolution == "skip_public"
    assert not SavedEvent.objects.using(PERSONAL).filter(pk=saved.pk).exists()


def test_a_duplicate_pair_with_a_saved_side_refuses_update_existing_on_the_saved_side():
    # "Update the existing one" targets the **personal** side — it opens an event in the
    # edit sheet. A save has no edit sheet, so the action does not apply to it.
    _, saved, pair = _mixed_pair(kind=ConflictPair.Kind.DUPLICATE)

    with pytest.raises(IllegalResolutionError):
        resolve_conflict(
            user_id=USER,
            pair_id=pair.pk,
            resolution="update_existing",
            side_kind=ConflictPair.SideKind.SAVED_EVENT,
            side_id=saved.pk,
            actor=Actor.user(USER),
            now=NOW,
        )


# --- The migration ---------------------------------------------------------------------------


def test_the_resolution_constraint_accepts_skip_public_for_both_kinds():
    """The constraint is a **kind** rule; the side rule lives in the service.

    `skip_public` is legal for both kinds, because the kind decides the *name* of the
    middle action while the side's kind decides the destructive one.
    """
    for kind in (ConflictPair.Kind.TIME, ConflictPair.Kind.DUPLICATE):
        pair = _pair(kind=kind)
        pair.status = ConflictPair.Status.RESOLVED
        pair.resolution = "skip_public"
        pair.resolved_at = NOW
        pair.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])

        pair.refresh_from_db()
        assert pair.resolution == "skip_public"


def test_the_resolution_constraint_still_refuses_an_unknown_resolution():
    from django.db import IntegrityError, transaction

    pair = _pair()
    pair.status = ConflictPair.Status.RESOLVED
    pair.resolution = "dismiss"
    pair.resolved_at = NOW
    with pytest.raises(IntegrityError):
        with transaction.atomic(using=PERSONAL):
            pair.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])


def test_the_resolution_constraint_still_refuses_a_dismiss():
    from django.db import IntegrityError, transaction

    pair = _pair()
    with pytest.raises(IntegrityError):
        with transaction.atomic(using=PERSONAL):
            pair.resolution = "dismiss"
            pair.save(update_fields=["resolution"])


def test_an_existing_resolved_pair_still_satisfies_the_constraint():
    """The migration is forwards-only: it changes a CHECK, not a column.

    A row written under the old constraint — one of the four original resolutions — must
    still satisfy the new one, because the new set is a superset for each kind.
    """
    for kind, resolution in (
        (ConflictPair.Kind.TIME, "keep_both"),
        (ConflictPair.Kind.TIME, "edit_new"),
        (ConflictPair.Kind.TIME, "delete_new"),
        (ConflictPair.Kind.DUPLICATE, "keep_both"),
        (ConflictPair.Kind.DUPLICATE, "update_existing"),
        (ConflictPair.Kind.DUPLICATE, "delete_new"),
    ):
        pair = _pair(kind=kind)
        pair.status = ConflictPair.Status.RESOLVED
        pair.resolution = resolution
        pair.resolved_at = NOW
        pair.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])

        pair.refresh_from_db()
        assert pair.resolution == resolution


def test_a_cleared_pair_still_carries_a_null_resolution():
    """`cleared_by_state_change` is unchanged by the new value: it still means "nobody
    answered", and the status constraint still requires a NULL resolution for it."""
    pair = _pair()
    pair.status = ConflictPair.Status.CLEARED_BY_STATE_CHANGE
    pair.resolution = None
    pair.resolved_at = NOW
    pair.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])

    pair.refresh_from_db()
    assert pair.resolution is None
    assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE


# --- The endpoint ----------------------------------------------------------------------------


def test_the_save_to_409_to_resolve_round_trip_works_on_the_api():
    """The whole point: a save that clashes can be answered, end to end, over HTTP."""
    from tests.personalization.test_personal_events_api import make_user, signed_in

    user = make_user()
    personal = _personal(user.pk, name="Coffee with Sam")
    saved = _saved(user.pk)
    pair = ConflictPair.objects.using(PERSONAL).create(
        user_id=user.pk,
        kind=ConflictPair.Kind.TIME,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=personal.pk,
        right_kind=ConflictPair.SideKind.SAVED_EVENT,
        right_id=saved.pk,
        status=ConflictPair.Status.ACTIVE,
        detected_at=NOW,
    )

    client = signed_in(user)
    response = client.post(
        f"/api/personal/events/conflicts/{pair.pk}/resolve",
        {
            "resolution": "skip_public",
            "side": {"kind": "saved_event", "id": str(saved.pk)},
        },
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["resolution"] == "skip_public"
    assert payload["status"] == "resolved"
    assert payload["action_side"]["kind"] == "saved_event"
    assert payload["action_side"]["id"] == str(saved.pk)
    assert payload["other_side"]["kind"] == "personal_event"
    assert payload["other_side"]["id"] == str(personal.pk)
    assert not SavedEvent.objects.using(PERSONAL).filter(pk=saved.pk).exists()
