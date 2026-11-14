"""The category-mute endpoints (FR-25): the list, the set, the one-tap unmute, the reset.

**What these tests hold.**

1. **The category key and its label are the server's.** The response carries the chip
   label the user reads, so the client never owns a category list and can never show a
   category the server does not recognise.
2. **The state comes from the session, never from the payload** (AD-12). The write
   endpoints take no user id, so a request cannot talk the scoping out of.
3. **An unknown key is a 422, and an unknown duration is a 422.** The vocabulary and the
   duration set are both closed, and the contract says so rather than quietly accepting
   a mute that excludes nothing.
4. **`restore-defaults` is declared before `{category_key}`.** The order is load-bearing:
   a `DELETE /mutes/{category_key}` registered first would swallow
   `POST /mutes/restore-defaults` as a `DELETE` against a key of `"restore-defaults"`, and
   the answer would be a **405**, not a 404.
5. **The bulk reset is scoped to the caller.**
"""

import json
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.identity.models import User
from apps.personalization.models import CategoryMute
from shared.db import PERSONAL
from tests.csrf import CsrfClient

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

TASTE = "/api/settings/taste"
MUTES = "/api/settings/taste/mutes"


def make_user(email=None):
    """A fresh user. The email is unique per call, so a test can make two."""
    return User.objects.create_user(
        email=email or f"sam-{uuid4().hex[:8]}@example.test", password="pw"
    )


def signed_in(user=None):
    """A client whose session identifies a user, and that user's id.

    The id is returned alongside because `force_login` does not leave the user on the
    client, and these tests need to assert on rows scoped to the caller.
    """
    account = user or make_user()
    client = CsrfClient()
    client.force_login(account)
    client.user_id = account.pk
    return client


def body_of(response):
    return json.loads(response.content)


def put_mute(client, category_key="arts_culture", duration_days=30):
    return client.put(
        MUTES,
        {"category_key": category_key, "duration_days": duration_days},
        content_type="application/json",
    )


# ── The list ──────────────────────────────────────────────────────────────────────


def test_the_list_is_empty_for_a_user_with_no_mutes():
    response = signed_in().get(TASTE)

    assert response.status_code == 200, response.content
    assert body_of(response)["mutes"] == []


def test_the_list_carries_the_mutes_with_the_servers_own_label():
    """**The label is the server's wording**, so the client never owns a category list
    and can never show a category the server does not recognise."""
    client = signed_in()
    put_mute(client, "arts_culture")

    response = client.get(TASTE)

    mutes = body_of(response)["mutes"]
    assert len(mutes) == 1
    assert mutes[0]["category_key"] == "arts_culture"
    assert mutes[0]["label"] == "Arts & culture"
    assert mutes[0]["is_indefinite"] is False


def test_an_indefinite_mute_reads_as_indefinite():
    """The mockup's fourth choice — "until I change it" — is a null expiry, not a
    second code path."""
    client = signed_in()
    put_mute(client, "arts_culture", duration_days=None)

    response = client.get(TASTE)

    mute = body_of(response)["mutes"][0]
    assert mute["expires_at"] is None
    assert mute["is_indefinite"] is True


def test_an_expired_mute_is_not_listed():
    """The row is still there — it is the user's data — but it no longer mutes anything,
    so the screen does not list it.

    **The row is written directly, already expired.** The endpoint computes the expiry
    from *now*, so a mute it creates cannot be expired when the read follows it a moment
    later — the only way to reach this state is a mute whose time has passed, and the
    only way to set that up without waiting seven days is to write the row.
    """
    client = signed_in()
    CategoryMute.objects.create(
        user_id=client.user_id,
        category_key="arts_culture",
        expires_at=timezone.now() - timedelta(hours=1),
    )

    response = client.get(TASTE)

    assert body_of(response)["mutes"] == []
    assert CategoryMute.objects.filter(user_id=client.user_id).count() == 1


def test_an_anonymous_caller_is_refused():
    response = CsrfClient().get(TASTE)

    assert response.status_code == 401


# ── Setting a mute ───────────────────────────────────────────────────────────────


def test_setting_a_mute_records_the_row():
    client = signed_in()

    response = put_mute(client, "arts_culture", 30)

    assert response.status_code == 200, response.content
    payload = body_of(response)
    assert payload["category_key"] == "arts_culture"
    assert payload["changed"] is True
    assert payload["expires_at"] is not None
    assert (
        CategoryMute.objects.filter(user_id=client.user_id, category_key="arts_culture").count()
        == 1
    )


def test_an_indefinite_mute_has_no_expiry():
    client = signed_in()

    response = put_mute(client, "arts_culture", None)

    assert response.status_code == 200, response.content
    assert body_of(response)["expires_at"] is None


def test_an_unknown_category_is_refused():
    """**The vocabulary is the server's.** A mute on a key the server does not recognise
    would exclude nothing, silently, while the screen showed a row the user could not
    make sense of."""
    client = signed_in()

    response = put_mute(client, "jazz_clubs", 30)

    assert response.status_code == 422, response.content
    assert CategoryMute.objects.filter(user_id=client.user_id).count() == 0


def test_an_unknown_duration_is_refused():
    """**The duration set is closed.** A mute that outlived the user's patience by a typo
    is a mute the user has to find a screen to undo."""
    client = signed_in()

    response = put_mute(client, "arts_culture", 45)

    assert response.status_code == 422, response.content
    assert CategoryMute.objects.filter(user_id=client.user_id).count() == 0


def test_the_two_refusals_are_the_two_different_422s():
    """**The house's two 422s, and this endpoint uses both.**

    `invalid_request` is Ninja refusing the *shape* of the body before the handler
    runs; `invalid_input` is the command refusing the *value*. The frontend branches on
    the code, so the two are deliberately distinguishable — see
    `tests/identity/test_profile_api.py`, which pins the same distinction for the
    profile write.

    **Here the split falls where the rule falls.** The duration set is a `Literal` in
    the request schema, so a bad duration is refused as a shape — `invalid_request`.
    The category vocabulary is the server's and is open in the schema (`str`), so a
    bad category reaches the command and is refused as a value — `invalid_input`.

    **A test that asserted only the status would pass even if one of the two refusal
    paths were entirely broken**, because the other would satisfy it. So both codes are
    asserted.
    """
    client = signed_in()

    bad_category = put_mute(client, "jazz_clubs", 30)
    bad_duration = put_mute(client, "arts_culture", 45)

    assert bad_category.status_code == 422, bad_category.content
    assert bad_duration.status_code == 422, bad_duration.content
    assert body_of(bad_category)["code"] == "invalid_input"
    assert body_of(bad_duration)["code"] == "invalid_request"


def test_setting_the_same_mute_again_refreshes_the_window():
    """**The expiry runs from `now`, not from the mute's creation.** Asking for 30 days
    again is a request for thirty more days from now, so the expiry moves — and
    `changed` says so.

    The service-level test holds the *exact* idempotence case (same `now`, same expiry,
    `changed` false); at the API layer the two calls are milliseconds apart, so the
    expiry genuinely does move.
    """
    client = signed_in()
    first = put_mute(client, "arts_culture", 30)
    second = put_mute(client, "arts_culture", 30)

    assert second.status_code == 200, second.content
    assert body_of(second)["changed"] is True
    assert body_of(second)["expires_at"] >= body_of(first)["expires_at"]
    assert CategoryMute.objects.filter(user_id=client.user_id).count() == 1


def test_one_users_mute_does_not_touch_anothers():
    """The mute is the user's, and scoping is by the session."""
    mine = signed_in()
    theirs = signed_in()
    put_mute(theirs, "arts_culture", 30)

    response = mine.get(TASTE)

    assert body_of(response)["mutes"] == []


# ── The one-tap unmute ────────────────────────────────────────────────────────────


def test_unmuting_removes_the_row():
    """**One tap.** The row's absence *is* the absence of a mute, so an unmute is a
    deletion."""
    client = signed_in()
    put_mute(client, "arts_culture", 30)

    response = client.delete(f"{MUTES}/arts_culture")

    assert response.status_code == 200, response.content
    assert body_of(response)["changed"] is True
    assert CategoryMute.objects.filter(user_id=client.user_id).count() == 0


def test_unmuting_a_category_that_is_not_muted_reports_no_change():
    client = signed_in()

    response = client.delete(f"{MUTES}/arts_culture")

    assert response.status_code == 200, response.content
    assert body_of(response)["changed"] is False


def test_unmuting_an_unknown_category_is_refused():
    client = signed_in()

    response = client.delete(f"{MUTES}/jazz_clubs")

    assert response.status_code == 422, response.content


# ── The bulk reset ────────────────────────────────────────────────────────────────


def test_the_bulk_reset_clears_every_mute():
    client = signed_in()
    put_mute(client, "arts_culture", 30)
    put_mute(client, "tech_meetups", None)

    response = client.post(f"{MUTES}/restore-defaults")

    assert response.status_code == 200, response.content
    assert body_of(response)["removed"] == 2
    assert CategoryMute.objects.filter(user_id=client.user_id).count() == 0


def test_the_bulk_reset_is_not_swallowed_by_the_category_key_route():
    """**`restore-defaults` is declared before `{category_key}`, and the order is
    load-bearing.**

    Django resolves the URL patterns in registration order, and the first pattern to match
    the *path* wins — then the method is checked against it. So a
    `DELETE /mutes/{category_key}` registered first would swallow this as a `DELETE`
    against a key of `"restore-defaults"`, and the answer would be a **405**, not a 404.
    """
    client = signed_in()

    response = client.post(f"{MUTES}/restore-defaults")

    assert response.status_code != 405, response.content
    assert response.status_code == 200, response.content


def test_the_bulk_reset_is_scoped_to_the_caller():
    mine = signed_in()
    theirs = signed_in()
    put_mute(theirs, "arts_culture", 30)
    put_mute(mine, "arts_culture", 30)

    response = mine.post(f"{MUTES}/restore-defaults")

    assert body_of(response)["removed"] == 1
    assert CategoryMute.objects.filter(user_id=theirs.user_id).count() == 1


def test_the_bulk_reset_is_idempotent():
    """The screen's confirmation can be asked twice; the second call changes nothing."""
    client = signed_in()
    put_mute(client, "arts_culture", 30)

    first = client.post(f"{MUTES}/restore-defaults")
    second = client.post(f"{MUTES}/restore-defaults")

    assert body_of(first)["removed"] == 1
    assert body_of(second)["removed"] == 0
