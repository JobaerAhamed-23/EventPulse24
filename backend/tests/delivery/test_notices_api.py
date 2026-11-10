"""The notice API: the strip's read, the dismiss, and the per-event mute (FR-54, FR-55).

**What these tests pin is the shape of the contract**, not the services' behaviour
(which `test_state_notices.py` and `test_notice_mutes.py` own):

- every endpoint is **authed** — an anonymous request is refused;
- every endpoint is **scoped to the session user** — another user's notice is invisible,
  and no endpoint accepts a user id as an input;
- **another user's notice is a 404, not a 403** — a 403 would confirm that the record
  exists, so the endpoint could be used to probe for other users' notice ids (no
  existence leak);
- **the dismiss and the mute are idempotent** — a second call answers success and says
  `changed: false`, because nothing moved;
- **the strip is bounded and newest-first**, and the bound is the server's;
- **the empty case answers 200 with an empty list** — most users, most days, have nothing
  to correct;
- **the query counts are bounded** — the strip read is one query, and the bound does not
  grow with the number of notices;
- **the writes refuse a request without a CSRF token** — because the rest of this file
  uses a client that always sends one.

The client is a `CsrfClient`, because the endpoints resolve their user through
`identity`'s resolver and the resolver checks CSRF on every unsafe method (D13).
"""

import ast
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client
from django.test.utils import CaptureQueriesContext

from apps.delivery.models import DeliveryAuditEntry, EventNoticeMute, StateChangeNotice
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.csrf import CsrfClient
from tests.ingestion.factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: The instant every test measures from. Pinned so a notice's timestamp is a fact, not a
#: function of when the suite happened to run.
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def make_user(email="sam@example.test"):
    """A real user with a real pk — the session resolves to this one."""
    return User.objects.create_user(email=email, password="pw")


def signed_in(user=None):
    """A client whose session identifies `user`."""
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


def make_notice(
    user,
    *,
    event_id=None,
    kind="sold_out",
    version=2,
    created_at=NOW,
    dismissed_at=None,
    seen_at=None,
):
    """One notice row, written directly.

    **The row is written directly rather than raised through the service**, because these
    tests are about the *surface* — and raising one needs a zone, a change and a
    propagation. The row is the same row either way; `test_state_notices.py` owns how it
    comes to exist.

    **`created_at` is set after the insert**, because the column is `auto_now_add` — the
    database stamps it, and the ordering these tests pin is the ordering by that column.
    """
    notice = StateChangeNotice.objects.using(PERSONAL).create(
        user_id=user.pk,
        event_id=event_id or uuid7(),
        state_change_id=uuid7(),
        change_kind=kind,
        event_version=version,
        local_date=created_at.date(),
        seen_at=seen_at,
        dismissed_at=dismissed_at,
    )
    StateChangeNotice.objects.using(PERSONAL).filter(pk=notice.pk).update(created_at=created_at)
    notice.refresh_from_db()
    return notice


def notices(user):
    return StateChangeNotice.objects.using(PERSONAL).filter(user_id=user.pk)


def dismiss_path(notice_id):
    return f"/api/notices/{notice_id}/dismiss"


def mute_path(event_id):
    return f"/api/notices/events/{event_id}/mute"


def strip_path():
    return "/api/notices"


# --- The strip's read (FR-54) ---------------------------------------------------------------------


def test_the_strip_reads_the_users_open_notices():
    user = make_user()
    notice = make_notice(user, kind="sold_out", version=3)
    client = signed_in(user)

    response = client.get(strip_path())

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["id"] == str(notice.id)
    assert item["event_id"] == str(notice.event_id)
    assert item["change_kind"] == "sold_out"
    assert item["event_version"] == 3
    assert item["local_date"] == str(NOW.date())
    assert item["created_at"] == NOW.isoformat().replace("+00:00", "Z")


def test_the_strip_is_newest_first():
    user = make_user()
    oldest = make_notice(user, created_at=NOW - timedelta(hours=3))
    newest = make_notice(user, created_at=NOW - timedelta(hours=1))
    middle = make_notice(user, created_at=NOW - timedelta(hours=2))
    client = signed_in(user)

    response = client.get(strip_path())

    assert [item["id"] for item in response.json()["items"]] == [
        str(newest.id),
        str(middle.id),
        str(oldest.id),
    ]


def test_a_dismissed_notice_is_not_in_the_strip():
    """The strip is a **queue**: closing an item empties it.

    Being *shown* something is not the same as acting on it, so the read is scoped by
    `dismissed_at` and not by `seen_at`.
    """
    user = make_user()
    make_notice(user, dismissed_at=NOW)
    make_notice(user)
    client = signed_in(user)

    response = client.get(strip_path())

    assert len(response.json()["items"]) == 1


def test_the_strip_is_empty_when_there_is_nothing():
    """The common case: most users, most days, have no open notices.

    **200 with an empty list** — not a 404, and not a `null`. There is no inbox, so
    "nothing" is a state the strip renders, not a missing resource.
    """
    user = make_user()
    client = signed_in(user)

    response = client.get(strip_path())

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_the_strip_is_bounded():
    """**A few, not a history.** The bound is the server's, and the newest are the ones
    kept — a busy day must not turn the strip into a list."""
    from shared.constants import NOTICE_STRIP_LIMIT

    user = make_user()
    made = [make_notice(user, created_at=NOW - timedelta(minutes=i)) for i in range(8)]
    client = signed_in(user)

    response = client.get(strip_path())

    items = response.json()["items"]
    assert len(items) == NOTICE_STRIP_LIMIT
    # The newest are the ones kept: `made[0]` is the newest.
    assert [item["id"] for item in items] == [str(n.id) for n in made[:NOTICE_STRIP_LIMIT]]


def test_the_strip_read_is_one_query():
    """The bound is cheap rather than merely capped: one query, whatever the day looks
    like. The session and identity reads are the request's, not the strip's."""
    user = make_user()
    for _ in range(5):
        make_notice(user)
    client = signed_in(user)

    with CaptureQueriesContext(connections[PERSONAL]) as captured:
        client.get(strip_path())

    reads = [
        str(query["sql"])
        for query in captured
        if "django_session" not in str(query["sql"]) and "identity_user" not in str(query["sql"])
    ]
    assert len(reads) == 1, "; ".join(reads)


def test_the_strip_carries_no_pii():
    """AD-13: no title, no venue, no address reaches the response.

    The change's before/after values are source payload, and they are where a title or a
    venue name would leak.
    """
    user = make_user()
    make_notice(user)
    client = signed_in(user)

    body = client.get(strip_path()).json()

    text = str(body).lower()
    for word in ("title", "venue", "email", "name", "address", "city"):
        assert word not in text, f"the strip payload carries {word!r}: {body}"


def test_the_strip_does_not_carry_the_state_change_id():
    """It is the notice's internal uniqueness key. No client acts on it."""
    user = make_user()
    notice = make_notice(user)
    client = signed_in(user)

    body = client.get(strip_path()).json()

    assert str(notice.state_change_id) not in str(body)


# --- The dismiss write (FR-54) -------------------------------------------------------------------


def test_dismissing_a_notice_closes_it():
    user = make_user()
    notice = make_notice(user)
    client = signed_in(user)

    response = client.post(dismiss_path(notice.id))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(notice.id)
    assert body["dismissed"] is True
    assert body["changed"] is True
    notice.refresh_from_db()
    assert notice.dismissed_at is not None


def test_dismissing_an_already_dismissed_notice_is_idempotent():
    """A success, not an error — and it must not claim to have changed anything.

    `changed: false` is the honest answer, and it is what lets the client skip the
    redraw.
    """
    user = make_user()
    notice = make_notice(user)
    client = signed_in(user)
    client.post(dismiss_path(notice.id))
    notice.refresh_from_db()
    first_dismissed_at = notice.dismissed_at

    response = client.post(dismiss_path(notice.id))

    assert response.status_code == 200
    body = response.json()
    assert body["dismissed"] is True
    assert body["changed"] is False
    notice.refresh_from_db()
    assert notice.dismissed_at == first_dismissed_at


def test_a_dismissal_records_the_first_sighting_too():
    """The dismissal sets `seen_at` as well — a user who closed it has certainly seen it,
    and the two columns are separate so the banner can tell them apart."""
    user = make_user()
    notice = make_notice(user)
    client = signed_in(user)

    client.post(dismiss_path(notice.id))

    notice.refresh_from_db()
    assert notice.seen_at is not None


def test_a_dismissal_writes_an_audit_row():
    user = make_user()
    notice = make_notice(user)
    client = signed_in(user)

    client.post(dismiss_path(notice.id))

    entry = DeliveryAuditEntry.objects.using(PERSONAL).get(
        action="state_change_notice.dismissed", target_id=notice.id
    )
    assert entry.actor_id == user.pk


def test_a_second_dismissal_writes_no_second_audit_row():
    """AD-5: one row per mutation. The second dismissal mutates nothing."""
    user = make_user()
    notice = make_notice(user)
    client = signed_in(user)
    client.post(dismiss_path(notice.id))

    client.post(dismiss_path(notice.id))

    assert (
        DeliveryAuditEntry.objects.using(PERSONAL)
        .filter(action="state_change_notice.dismissed", target_id=notice.id)
        .count()
        == 1
    )


def test_a_notice_for_an_unsaved_event_still_dismisses():
    """**Criterion 7.** The notice row names the catalog event by value, with no FK, so it
    survives the user un-saving the event — and the dismiss never resolves the event at
    all."""
    user = make_user()
    event = EventFactory()
    notice = make_notice(user, event_id=event.id)
    client = signed_in(user)

    response = client.post(dismiss_path(notice.id))

    assert response.status_code == 200
    notice.refresh_from_db()
    assert notice.dismissed_at is not None


def test_a_notice_for_an_event_that_no_longer_exists_still_dismisses():
    """The stronger half of criterion 7: the `event_id` names a UUID no catalog row
    carries, and the dismissal still succeeds."""
    user = make_user()
    notice = make_notice(user, event_id=uuid4())
    client = signed_in(user)

    response = client.post(dismiss_path(notice.id))

    assert response.status_code == 200
    notice.refresh_from_db()
    assert notice.dismissed_at is not None


# --- The mute write (FR-55) ----------------------------------------------------------------------


def test_muting_an_event_silences_its_notices():
    user = make_user()
    event_id = uuid7()
    client = signed_in(user)

    response = client.put(mute_path(event_id))

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == str(event_id)
    assert body["muted"] is True
    assert body["changed"] is True
    assert (
        EventNoticeMute.objects.using(PERSONAL).filter(user_id=user.pk, event_id=event_id).exists()
    )


def test_unmuting_an_event_lets_its_notices_through():
    user = make_user()
    event_id = uuid7()
    client = signed_in(user)
    client.put(mute_path(event_id))

    response = client.delete(mute_path(event_id))

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == str(event_id)
    assert body["muted"] is False
    assert body["changed"] is True
    assert (
        not EventNoticeMute.objects.using(PERSONAL)
        .filter(user_id=user.pk, event_id=event_id)
        .exists()
    )


def test_muting_an_already_muted_event_is_idempotent():
    """A success, not an error — and **one** row, not two."""
    user = make_user()
    event_id = uuid7()
    client = signed_in(user)
    client.put(mute_path(event_id))

    response = client.put(mute_path(event_id))

    assert response.status_code == 200
    body = response.json()
    assert body["muted"] is True
    assert body["changed"] is False
    assert (
        EventNoticeMute.objects.using(PERSONAL).filter(user_id=user.pk, event_id=event_id).count()
        == 1
    )


def test_unmuting_an_already_unmuted_event_is_idempotent():
    user = make_user()
    event_id = uuid7()
    client = signed_in(user)

    response = client.delete(mute_path(event_id))

    assert response.status_code == 200
    body = response.json()
    assert body["muted"] is False
    assert body["changed"] is False


def test_a_mute_writes_an_audit_row():
    user = make_user()
    event_id = uuid7()
    client = signed_in(user)

    client.put(mute_path(event_id))

    entry = DeliveryAuditEntry.objects.using(PERSONAL).get(
        action="event_notice_mute.muted", target_id=event_id
    )
    assert entry.actor_id == user.pk


def test_an_unmute_writes_an_audit_row():
    user = make_user()
    event_id = uuid7()
    client = signed_in(user)
    client.put(mute_path(event_id))

    client.delete(mute_path(event_id))

    entry = DeliveryAuditEntry.objects.using(PERSONAL).get(
        action="event_notice_mute.unmuted", target_id=event_id
    )
    assert entry.actor_id == user.pk


def test_a_no_op_mute_writes_no_audit_row():
    """AD-5: one row per mutation. The second mute mutates nothing."""
    user = make_user()
    event_id = uuid7()
    client = signed_in(user)
    client.put(mute_path(event_id))

    client.put(mute_path(event_id))

    assert (
        DeliveryAuditEntry.objects.using(PERSONAL)
        .filter(action="event_notice_mute.muted", target_id=event_id)
        .count()
        == 1
    )


def test_a_mute_is_allowed_for_an_event_the_catalog_does_not_hold():
    """AD-3: no existence check, on purpose.

    The id names a row in `catalog`, which the write may not read in its transaction, and
    a mute for an event that has since gone is harmless.
    """
    user = make_user()
    client = signed_in(user)

    response = client.put(mute_path(uuid4()))

    assert response.status_code == 200
    assert response.json()["muted"] is True


def test_the_mute_write_takes_no_user_id():
    """The scoping cannot be talked out of by a payload (AD-12)."""
    user = make_user()
    other = make_user(email="other@example.test")
    event_id = uuid7()
    client = signed_in(user)

    client.put(f"{mute_path(event_id)}?user_id={other.pk}")

    assert (
        EventNoticeMute.objects.using(PERSONAL).filter(user_id=user.pk, event_id=event_id).exists()
    )
    assert (
        not EventNoticeMute.objects.using(PERSONAL)
        .filter(user_id=other.pk, event_id=event_id)
        .exists()
    )


# --- The authorization cases (FR-54, FR-55) -----------------------------------------------------


def test_an_anonymous_caller_cannot_read_the_strip():
    client = CsrfClient()

    response = client.get(strip_path())

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_an_anonymous_caller_cannot_dismiss_a_notice():
    user = make_user()
    notice = make_notice(user)
    client = CsrfClient()

    response = client.post(dismiss_path(notice.id))

    assert response.status_code == 401
    notice.refresh_from_db()
    assert notice.dismissed_at is None


def test_an_anonymous_caller_cannot_mute_an_event():
    user = make_user()
    event_id = uuid7()
    client = CsrfClient()

    response = client.put(mute_path(event_id))

    assert response.status_code == 401
    assert (
        not EventNoticeMute.objects.using(PERSONAL)
        .filter(user_id=user.pk, event_id=event_id)
        .exists()
    )


def test_dismissing_without_a_csrf_token_is_refused():
    """D13: the check is explicit, and it applies to the unsafe methods.

    **The whole file uses a `CsrfClient`, which always sends a token** — so the CSRF path
    is never exercised by any other test here. A regression that dropped `require_csrf`
    from the router would leave this suite green.
    """
    user = make_user()
    notice = make_notice(user)
    client = Client()
    client.force_login(user)

    response = client.post(dismiss_path(notice.id))

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    notice.refresh_from_db()
    assert notice.dismissed_at is None


def test_muting_without_a_csrf_token_is_refused():
    """The same for the mute — and the mute row must not exist afterwards."""
    user = make_user()
    event_id = uuid7()
    client = Client()
    client.force_login(user)

    response = client.put(mute_path(event_id))

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    assert (
        not EventNoticeMute.objects.using(PERSONAL)
        .filter(user_id=user.pk, event_id=event_id)
        .exists()
    )


def test_unmuting_without_a_csrf_token_is_refused():
    """And for the clear, which is a write too."""
    user = make_user()
    event_id = uuid7()
    EventNoticeMute.objects.using(PERSONAL).create(user_id=user.pk, event_id=event_id)
    client = Client()
    client.force_login(user)

    response = client.delete(mute_path(event_id))

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    assert (
        EventNoticeMute.objects.using(PERSONAL).filter(user_id=user.pk, event_id=event_id).exists()
    )


def test_another_users_notice_is_not_in_the_strip():
    """The strongest form of the claim: the strip is the caller's only."""
    user = make_user()
    other = make_user(email="other@example.test")
    make_notice(other)
    mine = make_notice(user)
    client = signed_in(user)

    body = client.get(strip_path()).json()

    assert [item["id"] for item in body["items"]] == [str(mine.id)]


def test_dismissing_another_users_notice_is_a_404_not_a_403():
    """**No existence leak.** A 403 would confirm that the record exists, so the endpoint
    could be used to probe for other users' notice ids."""
    user = make_user()
    other = make_user(email="other@example.test")
    notice = make_notice(other)
    client = signed_in(user)

    response = client.post(dismiss_path(notice.id))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    notice.refresh_from_db()
    assert notice.dismissed_at is None


def test_a_notice_that_does_not_exist_is_a_404():
    """**The same 404**, with the same code — so the two cases are indistinguishable."""
    user = make_user()
    client = signed_in(user)

    response = client.post(dismiss_path(uuid4()))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_the_two_404s_are_indistinguishable():
    """Not another user's notice, and no such notice: the same status, the same code, and
    the same message. A client cannot tell them apart."""
    user = make_user()
    other = make_user(email="other@example.test")
    notice = make_notice(other)
    client = signed_in(user)

    not_yours = client.post(dismiss_path(notice.id))
    no_such_notice = client.post(dismiss_path(uuid4()))

    assert not_yours.status_code == no_such_notice.status_code == 404
    assert not_yours.json() == no_such_notice.json()


def test_muting_does_not_touch_another_users_mute():
    """A mute is keyed by `(user, event)`, so there is no cross-user leak possible — and
    the test says so rather than assuming it."""
    user = make_user()
    other = make_user(email="other@example.test")
    event_id = uuid7()
    other_client = signed_in(other)
    other_client.put(mute_path(event_id))

    client = signed_in(user)
    client.put(mute_path(event_id))

    assert (
        EventNoticeMute.objects.using(PERSONAL).filter(user_id=other.pk, event_id=event_id).exists()
    )
    assert (
        EventNoticeMute.objects.using(PERSONAL).filter(user_id=user.pk, event_id=event_id).exists()
    )


def test_the_strip_read_takes_no_user_id():
    user = make_user()
    other = make_user(email="other@example.test")
    make_notice(other)
    mine = make_notice(user)
    client = signed_in(user)

    body = client.get(f"{strip_path()}?user_id={other.pk}").json()

    assert [item["id"] for item in body["items"]] == [str(mine.id)]


# --- The contract (AD-19) ------------------------------------------------------------------------


def test_the_endpoints_are_in_the_openapi_schema():
    from config.api import api

    schema = api.get_openapi_schema()
    paths = schema["paths"]

    assert "/api/notices" in paths
    assert "get" in paths["/api/notices"]
    assert "/api/notices/{notice_id}/dismiss" in paths
    assert "post" in paths["/api/notices/{notice_id}/dismiss"]
    assert "/api/notices/events/{event_id}/mute" in paths
    assert "put" in paths["/api/notices/events/{event_id}/mute"]
    assert "delete" in paths["/api/notices/events/{event_id}/mute"]


def test_the_notices_api_does_not_import_the_models():
    """AD-5 / AD-16: a surface module reads through published services, never the ORM.

    The check is on the **import**, not on the text: a module that imported the models
    under an alias would still be holding them.
    """
    from tests.architecture.checkers import BACKEND_DIR

    path = BACKEND_DIR / "apps/delivery/notices_api.py"
    imported = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")

    assert not any(name.endswith(".models") for name in imported), imported
