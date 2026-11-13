"""The source-visibility endpoints (FR-13, FR-16): the list, the set, and the bulk reset.

**What these tests hold.**

1. **The list joins the catalog's registry with the caller's own state.** The registry is
   `ingestion`'s and the mute is `personalization`'s; the client makes one call and learns
   both. A muted source is **still listed** — the screen's job is transparency, and a
   muted source that disappeared would be a preference the user could not see or undo.
2. **The state comes from the session, never from the payload** (AD-12). The write
   endpoints take no user id, so a request cannot talk the scoping out of.
3. **The bulk reset is scoped to the caller.** One user's reset clears that user's rows
   and nobody else's.
4. **The write endpoints touch only the personal schema** (AD-3). The write path reads
   and writes `personal` and never `catalog` — and the *grant* half of that is proved in
   `tests/personalization/test_grants.py`, which asserts the runtime role's privileges
   on the new `personalization_sourcemute` table.
5. **A source that is not in the registry is accepted, not a 404.** The endpoint may not
   read `catalog` in a write transaction, and the service deliberately does not check:
   a mute for a source that has since been removed excludes nothing and is purged with
   the user's data. The declared contract says so, rather than promising a 404 the code
   does not deliver.
"""

import json
from uuid import uuid4

import pytest

from apps.identity.models import User
from apps.personalization.models import PersonalizationAuditEntry, SourceMute
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.ingestion.factories import SourceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

SOURCES = "/api/settings/sources"


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


def set_state(client, source_id, state):
    return client.put(
        f"{SOURCES}/{source_id}",
        {"state": state},
        content_type="application/json",
    )


# ── The list ──────────────────────────────────────────────────────────────────────


def test_the_list_has_four_groups_in_order():
    client = signed_in()

    response = client.get(SOURCES)

    assert response.status_code == 200, response.content
    groups = body_of(response)["groups"]
    assert [group["badge"] for group in groups] == [
        "official_site",
        "community",
        "aggregator",
        "crawled_html",
    ]


def test_the_list_carries_each_source_with_its_trust():
    source = SourceFactory(name="Barbican Centre")

    response = signed_in().get(SOURCES)

    groups = body_of(response)["groups"]
    official = next(g for g in groups if g["badge"] == "official_site")
    row = next(s for s in official["sources"] if s["id"] == str(source.id))
    assert row["name"] == "Barbican Centre"
    # A never-scored source sits at the prior, which is band 3.
    assert row["trust"]["band"] == 3
    assert row["mute_state"] == "default"


def test_a_muted_source_is_still_listed_with_its_state():
    """**The screen's job is transparency.** The user is told what is informing their
    timeline *and* what they have turned off. A muted source that disappeared would be a
    preference they could not see or undo."""
    source = SourceFactory()
    client = signed_in()
    set_state(client, source.id, "mute")

    response = client.get(SOURCES)

    groups = body_of(response)["groups"]
    official = next(g for g in groups if g["badge"] == "official_site")
    row = next(s for s in official["sources"] if s["id"] == str(source.id))
    assert row["mute_state"] == "mute"


def test_an_empty_registry_lists_four_empty_groups():
    """Nothing is fabricated to fill the screen, and the shape does not depend on the
    data."""
    response = signed_in().get(SOURCES)

    groups = body_of(response)["groups"]
    assert len(groups) == 4
    assert all(group["sources"] == [] for group in groups)


def test_an_anonymous_caller_is_refused():
    response = CsrfClient().get(SOURCES)

    assert response.status_code == 401


# ── Setting a state ───────────────────────────────────────────────────────────────


def test_setting_a_mute_records_the_state():
    source = SourceFactory()
    client = signed_in()

    response = set_state(client, source.id, "mute")

    assert response.status_code == 200, response.content
    payload = body_of(response)
    assert payload["source_id"] == str(source.id)
    assert payload["state"] == "mute"
    assert payload["changed"] is True
    assert SourceMute.objects.filter(user_id=client.user_id, source_id=source.id).count() == 1


def test_a_source_that_is_not_in_the_registry_is_accepted():
    """**Not a 404 — and the contract says so.**

    The endpoint may not read `catalog` in a write transaction (AD-3), and the service
    deliberately does not check the source exists: a mute for a source that has since
    been removed excludes nothing, and the row is purged with the user's data. So the
    answer is a 200 with the state recorded.

    The test is here because the *contract* matters more than the behaviour: a declared
    404 that never arrives teaches the client to expect a failure that never comes, and
    a client that handles a 404 it will never see is a client handling the wrong thing.
    """
    client = signed_in()
    unknown = uuid4()

    response = set_state(client, unknown, "mute")

    assert response.status_code == 200, response.content
    payload = body_of(response)
    assert payload["source_id"] == str(unknown)
    assert payload["state"] == "mute"
    assert SourceMute.objects.filter(user_id=client.user_id, source_id=unknown).count() == 1


def test_setting_the_state_a_source_is_already_in_reports_no_change():
    """The screen moves only when the server confirms, and `changed` says whether
    anything actually moved."""
    source = SourceFactory()
    client = signed_in()
    set_state(client, source.id, "mute")

    response = set_state(client, source.id, "mute")

    assert response.status_code == 200
    assert body_of(response)["changed"] is False


def test_setting_default_removes_the_row():
    source = SourceFactory()
    client = signed_in()
    set_state(client, source.id, "mute")

    response = set_state(client, source.id, "default")

    assert response.status_code == 200
    assert body_of(response)["state"] == "default"
    assert SourceMute.objects.filter(user_id=client.user_id).count() == 0


def test_an_unknown_state_is_refused_by_the_parser():
    source = SourceFactory()
    client = signed_in()

    response = set_state(client, source.id, "silenced")

    assert response.status_code == 422


def test_a_write_without_a_csrf_token_is_refused():
    """D13: every state-changing request carries the token, and the check is the
    server's."""
    from django.test import Client

    source = SourceFactory()
    client = Client()
    client.force_login(make_user())

    response = client.put(
        f"{SOURCES}/{source.id}",
        {"state": "mute"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert body_of(response)["code"] == "csrf_failed"


def test_a_write_writes_an_audit_row():
    """AD-5: every state change is audited."""
    source = SourceFactory()
    client = signed_in()

    set_state(client, source.id, "mute")

    entry = PersonalizationAuditEntry.objects.get(target_id=source.id, action="source_mute.mute")
    assert entry.actor_id == client.user_id


def test_one_users_write_does_not_touch_anothers():
    source = SourceFactory()
    first, second = signed_in(), signed_in()

    set_state(first, source.id, "mute")

    assert SourceMute.objects.filter(user_id=second.user_id).count() == 0


# ── The bulk reset ────────────────────────────────────────────────────────────────


def test_the_bulk_reset_clears_the_callers_rows_and_says_how_many():
    source = SourceFactory()
    client = signed_in()
    set_state(client, source.id, "mute")
    set_state(client, source.id, "show_less")

    response = client.post(f"{SOURCES}/restore-defaults")

    assert response.status_code == 200, response.content
    assert body_of(response)["removed"] == 1
    assert SourceMute.objects.filter(user_id=client.user_id).count() == 0


def test_the_bulk_reset_leaves_another_users_rows_alone():
    source = SourceFactory()
    first, second = signed_in(), signed_in()
    set_state(first, source.id, "mute")
    set_state(second, source.id, "mute")

    client = first
    response = client.post(f"{SOURCES}/restore-defaults")

    assert response.status_code == 200
    assert SourceMute.objects.filter(user_id=second.user_id).count() == 1


def test_the_bulk_reset_of_a_user_with_nothing_removes_nothing():
    response = signed_in().post(f"{SOURCES}/restore-defaults")

    assert response.status_code == 200
    assert body_of(response)["removed"] == 0


def test_the_bulk_reset_is_idempotent():
    """The confirmation can be asked twice; the second call changes nothing."""
    source = SourceFactory()
    client = signed_in()
    set_state(client, source.id, "mute")

    first = client.post(f"{SOURCES}/restore-defaults")
    second = client.post(f"{SOURCES}/restore-defaults")

    assert body_of(first)["removed"] == 1
    assert body_of(second)["removed"] == 0


def test_the_bulk_reset_writes_an_audit_row():
    source = SourceFactory()
    client = signed_in()
    set_state(client, source.id, "mute")

    client.post(f"{SOURCES}/restore-defaults")

    entry = PersonalizationAuditEntry.objects.get(action="source_mute.restore_defaults")
    assert entry.actor_id == client.user_id


def test_an_anonymous_caller_cannot_reset():
    response = CsrfClient().post(f"{SOURCES}/restore-defaults")

    assert response.status_code == 401
