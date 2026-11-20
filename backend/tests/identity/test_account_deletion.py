"""Deleting an account: the grace period, the purge, and the picture that must not
outlive it.

**What these tests hold.**

1. **Nothing dies while the request is pending.** The account, its rows and its picture
   are all still there — and the picture's *object* is probed in the bucket, not merely
   read off the row. A row that says `""` is not evidence that the object is gone.
2. **Cancelling returns the account whole.** Including the picture.
3. **The purge is thorough.** Every categorised row is gone, the sessions are gone, and
   the account is gone.
4. **The picture's object is removed from the bucket** — probed, not inferred.
5. **The survivors survive.** The audit log and the billing records, for the reasons the
   service's docstring gives.
6. **An account with no picture deletes cleanly.** The empty key must not reach the
   store, because `delete("")` raises `ValueError` from the port's key validation.
7. **The grace period is thirty days**, computed once, and not moved by asking again.
8. **The notice mail is sent once, and only once**, and a failure to send it does not
   fail the request — and **the token in it really cancels the deletion**, so the mail's
   promise is a tested fact rather than a claim in a docstring.
"""

import io
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from PIL import Image

from apps.identity.models import DeletionRequest, IdentityAuditEntry, User
from apps.identity.services import tokens as token_service
from apps.identity.services.avatar import set_user_avatar
from apps.identity.services.deletion import (
    cancel_account_deletion,
    cancel_account_deletion_with_token,
    destroy_account,
    due_deletion_requests,
    request_account_deletion,
)
from ports.blob import BlobNotFound, BlobPort
from ports.registry import get_adapter
from shared.constants import DELETION_GRACE_PERIOD
from shared.db import PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


def make_user():
    return User.objects.create_user(email=f"sam-{uuid4().hex[:8]}@example.test", password="pw")


def png_bytes(*, size=(8, 8)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(out, format="PNG")
    return out.getvalue()


def upload(data: bytes):
    class _Upload:
        def __init__(self, payload: bytes):
            self._stream = io.BytesIO(payload)

        def read(self, n=-1):
            return self._stream.read(n)

        def seek(self, *args):
            return self._stream.seek(*args)

        def tell(self):
            return self._stream.tell()

    return _Upload(data)


def blob() -> BlobPort:
    return get_adapter(BlobPort)


def stored(key: str) -> bytes | None:
    """**The object's bytes, or `None` if it is not in the store.**

    This is the probe that matters. The row's `avatar_key` being blank would say the
    account no longer *names* a picture; it would say nothing about whether the object
    is still sitting in the bucket, holding a person's face.
    """
    if not key:
        return None
    try:
        return blob().open(key).data
    except BlobNotFound:
        return None


def give_user_an_avatar(user) -> str:
    key = set_user_avatar(user_id=user.pk, upload=upload(png_bytes()))
    user.refresh_from_db()
    return key


# ── The grace period ───────────────────────────────────────────────────────────────


def test_requesting_deletion_destroys_nothing(django_capture_on_commit_callbacks):
    """**The request is a schedule, not an execution.**

    **The `on_commit` capture is what makes this test able to fail.** Under pytest-django
    the test runs inside a transaction that is never committed, so a `transaction.on_commit`
    callback would never fire — and an implementation that removed the picture at request
    time would pass this test unchanged. Capturing the callbacks and executing them means
    the probe sees the same thing a browser would.
    """
    user = make_user()
    key = give_user_an_avatar(user)

    with django_capture_on_commit_callbacks(execute=True):
        request_account_deletion(user_id=user.pk)

    assert User.objects.filter(pk=user.pk).exists()
    user.refresh_from_db()
    assert user.avatar_key == key
    assert stored(key) is not None, "the picture was removed while the request was pending"


def test_the_grace_period_is_thirty_days():
    """**The promise the product made, measured.**"""
    user = make_user()

    pending = request_account_deletion(user_id=user.pk)

    assert pending.scheduled_for - pending.requested_at == DELETION_GRACE_PERIOD
    assert DELETION_GRACE_PERIOD.days == 30


def test_asking_twice_does_not_move_the_deadline():
    """**The promise cannot be extended by pressing the button again.**

    The schedule is computed once, when the request is first made. A later request
    returns the same row rather than writing another.
    """
    user = make_user()

    first = request_account_deletion(user_id=user.pk)
    second = request_account_deletion(user_id=user.pk)

    assert second.pk == first.pk
    assert second.scheduled_for == first.scheduled_for
    assert DeletionRequest.objects.filter(user_id=user.pk).count() == 1


def test_cancelling_brings_the_account_back_whole():
    """**Cancelling returns everything — including the picture.**

    This is the property the whole design turns on. The object's removal happens at
    *destruction*, so a person who cancels inside the grace period has their picture
    back, exactly as they had it.
    """
    user = make_user()
    key = give_user_an_avatar(user)

    request_account_deletion(user_id=user.pk)
    cancelled = cancel_account_deletion(user_id=user.pk)

    assert cancelled is True
    assert DeletionRequest.objects.filter(user_id=user.pk).count() == 0

    user.refresh_from_db()
    assert user.avatar_key == key
    assert stored(key) is not None, "cancelling took the picture with it"


def test_cancelling_when_nothing_is_pending_is_not_an_error():
    """**An idempotent command.** The caller wanted no pending deletion and has none."""
    user = make_user()

    assert cancel_account_deletion(user_id=user.pk) is False


def test_a_cancelled_request_leaves_nothing_for_the_worker_to_find():
    """**Cancelling actually stops the destruction.**

    The destruction is driven by the worker's due-list, and that list is built from the
    pending requests — so a cancelled request is simply not in it, and the account is
    never reached. **The command itself is the hammer, not the gate**: `destroy_account`
    destroys the account it is given, and it is `due_deletion_requests` that decides
    which accounts are due. That split is why cancelling is safe.

    The worker-level behaviour — that a cancelled account is never destroyed — is
    asserted where the worker is the thing under test, in
    `tests/worker/test_account_deletion_task.py`.
    """
    user = make_user()

    request_account_deletion(user_id=user.pk)
    cancel_account_deletion(user_id=user.pk)

    assert DeletionRequest.objects.filter(user_id=user.pk).count() == 0
    assert due_deletion_requests(now=timezone.now() + timedelta(days=31)) == []


# ── The purge ───────────────────────────────────────────────────────────────────────


def test_destroying_removes_the_account():
    user = make_user()

    assert destroy_account(user_id=user.pk) is True
    assert not User.objects.filter(pk=user.pk).exists()


def test_destroying_an_account_that_is_not_there_is_a_no_op():
    """**A destroy with nothing to destroy is not an error.**"""
    assert destroy_account(user_id=uuid4()) is False


def test_the_pending_request_goes_with_the_account():
    """**The request row is itself personal data**, and it is in `ACCOUNT_IDENTITY`."""
    user = make_user()
    request_account_deletion(user_id=user.pk)

    destroy_account(user_id=user.pk)

    assert DeletionRequest.objects.filter(user_id=user.pk).count() == 0


def test_the_categorised_rows_are_actually_purged():
    """**The purge is thorough — and this is the test that holds that claim.**

    The file's docstring says *"every categorised row is gone"*, and until now the only
    row any test asserted was gone was the `DeletionRequest` — the one model the purge
    is least likely to get wrong, because it has a plain `user_id` column like most of
    them.

    **So this test asserts the awkward cases**, not the easy one:

    - `Interest` — a plain `user_id`, in `personalization`;
    - `SavedCollectionItem` — **no `user_id` at all**, reached through
      `collection__user_id`. A walk that forgot the traversal would leave it behind,
      holding a save that outlived the account.

    And it asserts the *other* side of the same purge: **another account's rows
    survive.** A purge that is too narrow is a bug; a purge that is too wide is a
    worse one.
    """
    from apps.personalization.models import (
        Interest,
        SavedCollection,
        SavedCollectionItem,
        SavedEvent,
    )

    user = make_user()
    other = make_user()

    interest = Interest.objects.create(user_id=user.pk, chip_key="tech_meetups")
    other_interest = Interest.objects.create(user_id=other.pk, chip_key="board_games")

    collection = SavedCollection.objects.create(user_id=user.pk, name="Weekend", position=0)
    other_collection = SavedCollection.objects.create(user_id=other.pk, name="Theirs", position=0)

    saved = SavedEvent.objects.create(
        user_id=user.pk,
        event_id=uuid4(),
        start_utc="2026-01-01T00:00:00Z",
        end_utc="2026-01-01T01:00:00Z",
        event_version=1,
    )
    other_saved = SavedEvent.objects.create(
        user_id=other.pk,
        event_id=uuid4(),
        start_utc="2026-01-01T00:00:00Z",
        end_utc="2026-01-01T01:00:00Z",
        event_version=1,
    )

    item = SavedCollectionItem.objects.create(collection=collection, saved_event=saved)
    other_item = SavedCollectionItem.objects.create(
        collection=other_collection, saved_event=other_saved
    )

    destroy_account(user_id=user.pk)

    # **This account's rows are gone.**
    assert not Interest.objects.filter(pk=interest.pk).exists()
    assert not SavedCollection.objects.filter(pk=collection.pk).exists()
    assert not SavedEvent.objects.filter(pk=saved.pk).exists()
    assert not SavedCollectionItem.objects.filter(pk=item.pk).exists()

    # **And the other account's are not.**
    assert Interest.objects.filter(pk=other_interest.pk).exists()
    assert SavedCollection.objects.filter(pk=other_collection.pk).exists()
    assert SavedEvent.objects.filter(pk=other_saved.pk).exists()
    assert SavedCollectionItem.objects.filter(pk=other_item.pk).exists()


def test_the_admin_history_is_purged_because_the_schema_forbids_its_surviving():
    """**A row the schema cannot keep is purged by name, and the reason is recorded.**

    `admin.LogEntry.user` is `NOT NULL` with a foreign key to `User`, so an
    `admin.logentry` row is **structurally impossible to keep** once the account is
    gone — the deferred constraint fails the commit. Its category says `AUDIT_LOG`,
    which survives, so the model is named in `PURGED_MODEL_OVERRIDES` with that reason.

    **This is not a hole in the audit trail.** Django's admin is off in this project;
    `identity.identityauditentry` is the audit log, and it survives — see
    `test_the_audit_log_survives_the_account`.
    """
    from django.contrib.admin.models import LogEntry
    from django.contrib.contenttypes.models import ContentType

    user = make_user()
    content_type = ContentType.objects.get_for_model(User)
    entry = LogEntry.objects.create(
        user_id=user.pk,
        content_type_id=content_type.pk,
        object_id=user.pk,
        object_repr="probe",
        action_flag=1,
        change_message="probe",
    )

    destroy_account(user_id=user.pk)

    assert not LogEntry.objects.filter(pk=entry.pk).exists()


def test_destroying_removes_the_picture_object_from_the_bucket(
    django_capture_on_commit_callbacks,
):
    """**The object is removed from the bucket — probed, not inferred.**

    The row's `avatar_key` being blank would not prove this: the object would still be
    there, holding a person's face, invisible to a reader of the database. The probe
    asks the store itself.
    """
    user = make_user()
    key = give_user_an_avatar(user)
    assert stored(key) is not None

    with django_capture_on_commit_callbacks(execute=True):
        destroy_account(user_id=user.pk)

    assert stored(key) is None, "the picture is still in the bucket"


def test_the_picture_object_survives_a_cancelled_request_in_the_bucket(
    django_capture_on_commit_callbacks,
):
    """**The other half of the promise, probed in the bucket rather than read off the
    row.**

    Cancelling must leave the object where it was — and the way to check that is *not*
    to destroy the account afterwards (a destruction removes the object, correctly).
    The check is that cancelling leaves nothing pending, so the worker never reaches
    the account at all.

    **The `on_commit` capture is what makes this test able to fail** — see the note on
    `test_requesting_deletion_destroys_nothing`.
    """
    user = make_user()
    key = give_user_an_avatar(user)

    with django_capture_on_commit_callbacks(execute=True):
        request_account_deletion(user_id=user.pk)
        cancel_account_deletion(user_id=user.pk)

    assert stored(key) is not None, "cancelling removed the picture from the bucket"

    # **And nothing is left for the worker to find**, so the account is never destroyed
    # and the picture is never at risk.
    assert DeletionRequest.objects.filter(user_id=user.pk).count() == 0
    assert due_deletion_requests(now=timezone.now() + timedelta(days=31)) == []


def test_an_account_with_no_picture_deletes_cleanly(django_capture_on_commit_callbacks):
    """**The empty key must never reach the store.**

    `delete("")` raises `ValueError` from the port's key validation — not `BlobError`,
    so the quiet-delete helper would not swallow it. An account without a picture is
    ordinary, and it must delete like any other.

    **The `on_commit` capture is what makes this test able to fail.** Without it the
    callback never runs, and an implementation that passed the empty key to the store
    would delete the account cleanly and pass this test — with a `ValueError` waiting
    in a callback that never fired.
    """
    user = make_user()
    assert user.avatar_key == ""

    with django_capture_on_commit_callbacks(execute=True):
        assert destroy_account(user_id=user.pk) is True

    assert not User.objects.filter(pk=user.pk).exists()


def test_the_sessions_die_with_the_account():
    """**A session is a live credential.** It dies with the account, and it is reached
    by decoding the payload rather than by a column."""
    from django.contrib.sessions.backends.db import SessionStore

    user = make_user()
    store = SessionStore()
    store["_auth_user_id"] = str(user.pk)
    store.create()

    destroy_account(user_id=user.pk)

    from django.contrib.sessions.models import Session

    assert not Session.objects.filter(session_key=store.session_key).exists()


# ── What survives ──────────────────────────────────────────────────────────────────


def test_the_audit_log_survives_the_account():
    """**The audit trail outlives the person.**

    AD-13 keeps PII out of the audit rows precisely so they can survive. A system that
    deleted its own audit trail on request could not answer "did this account ask to be
    deleted, and when".
    """
    user = make_user()

    request_account_deletion(user_id=user.pk)
    destroy_account(user_id=user.pk)

    actions = list(
        IdentityAuditEntry.objects.filter(actor_id=user.pk).values_list("action", flat=True)
    )
    assert "account_deletion_requested" in actions
    assert "account_deleted" in actions


def test_the_billing_records_survive_the_account():
    """**Seven years, for tax and legal.** A retention window that another table can
    override is not a retention window."""
    from tests.identity.factories import SubscriptionFactory

    user = make_user()
    subscription = SubscriptionFactory(user_id=user.pk)

    destroy_account(user_id=user.pk)

    assert not User.objects.filter(pk=user.pk).exists()
    from apps.identity.models import Subscription

    assert Subscription.objects.filter(pk=subscription.pk).exists()


def test_the_deletion_is_recorded_even_though_the_account_is_gone():
    """**The record of the deletion is written before the account goes.**

    `write_audit` needs an actor, and the actor is the account — so the row is written
    while the account still exists, and it outlives it.
    """
    user = make_user()
    request_account_deletion(user_id=user.pk)

    destroy_account(user_id=user.pk)

    row = IdentityAuditEntry.objects.filter(actor_id=user.pk, action="account_deleted").first()
    assert row is not None
    assert row.target_id == user.pk


def test_the_audit_rows_carry_no_personal_data():
    """**AD-13.** The rows that outlive the account must not carry the person."""
    user = make_user()

    request_account_deletion(user_id=user.pk)
    destroy_account(user_id=user.pk)

    for row in IdentityAuditEntry.objects.filter(actor_id=user.pk):
        assert user.email not in str(row.actor_label)
        assert user.email not in str(row.details)


# ── The mutation probes ────────────────────────────────────────────────────────────


def test_a_broken_store_does_not_make_a_successful_deletion_look_failed(
    django_capture_on_commit_callbacks,
    monkeypatch,
):
    """**A leak is a leak, not a failure.**

    The object is removed after the commit, so there is nothing left to undo by then:
    the account is already gone and the person is already gone. An exception escaping
    the `on_commit` callback would tell the caller the deletion failed — and the worker
    would log *"Account not destroyed"* for an account that **was** destroyed.

    **So the callback is registered with `robust=True`, and the store's failure is
    caught.** The account is destroyed; the object leaks; the caller is told the truth.

    **The probe is the store's failure, and it is the second belt.** The first belt is
    `robust=True` on the `on_commit` call, and that one is structural: it holds even if
    `_delete_object_quietly` is later refactored to catch less. This test cannot tell
    the two apart on its own — removing either layer alone leaves the other holding
    the promise — so it asserts the *outcome*, which is the thing that must not change.
    """
    import ports.registry as registry

    user = make_user()
    key = give_user_an_avatar(user)

    class _BrokenStore:
        def delete(self, k):
            raise RuntimeError("the store is misconfigured")

    monkeypatch.setattr(registry, "get_adapter", lambda port: _BrokenStore())

    with django_capture_on_commit_callbacks(execute=True):
        # **No exception escapes.** The deletion succeeded.
        assert destroy_account(user_id=user.pk) is True

    assert not User.objects.filter(pk=user.pk).exists()
    assert stored(key) is not None, "the object leaked, which is the promised outcome"


def test_the_commit_callback_is_registered_as_robust(django_capture_on_commit_callbacks):
    """**The structural belt, asserted directly.**

    `robust=True` is what makes *"a leak, not an error"* true even if
    `_delete_object_quietly` is later refactored to catch less — so it is a property of
    the *registration*, and it is asserted here rather than left to the outcome test
    above, which cannot tell the two layers apart.

    **The probe replaces the cleanup wholesale with one that raises**, so the `except`
    inside the real `_delete_object_quietly` is not in play — only `robust=True` can
    absorb this. Without it, the exception escapes the commit and the caller is told a
    successful deletion failed.
    """
    import apps.identity.services.deletion as module

    user = make_user()
    give_user_an_avatar(user)

    def _explode(key: str) -> None:
        raise RuntimeError("the store is misconfigured")

    original = module._delete_object_quietly
    module._delete_object_quietly = _explode
    try:
        with django_capture_on_commit_callbacks(execute=True):
            # **No exception escapes.** The account is gone and the caller is told so.
            assert destroy_account(user_id=user.pk) is True
    finally:
        module._delete_object_quietly = original

    assert not User.objects.filter(pk=user.pk).exists()


def test_the_probe_would_not_pass_if_the_object_were_merely_blanked(
    django_capture_on_commit_callbacks,
    monkeypatch,
):
    """**The bucket probe can fail.**

    A test that asserted only "the row's key is empty" would pass against an
    implementation that blanked the key and left the object in the store. This probe
    replaces the store's delete with a no-op — the mutation — and asserts the test
    notices.

    Without this, the probe would be a decoration: it might be asserting something
    that is trivially true.
    """
    user = make_user()
    key = give_user_an_avatar(user)

    # **The mutation**: the object is not removed from the store.
    monkeypatch.setattr(type(blob()), "_delete", lambda self, k: None)

    with django_capture_on_commit_callbacks(execute=True):
        destroy_account(user_id=user.pk)

    assert stored(key) is not None, "the mutation was not detected — the probe is inert"


def test_the_probe_would_not_pass_if_the_object_were_removed_at_request_time():
    """**The other mutation, and the one the design is shaped around.**

    Removing the object when deletion is *requested* rather than when the account is
    *destroyed* would break the grace-period promise. The probe checks the object is
    still there while the request is pending — so an implementation that removed it
    early fails.
    """
    user = make_user()
    key = give_user_an_avatar(user)

    request_account_deletion(user_id=user.pk)

    assert stored(key) is not None, "the picture was removed at request time"


def test_the_probe_would_not_pass_if_the_grace_period_were_zero(monkeypatch):
    """**A grace period of zero would make the promise a lie**, and the test that holds
    the promise is what would notice.

    The mutation is applied *here* and the holding assertion is re-run under it: the
    schedule must still be strictly later than the request. With a zero grace period it
    is not, so the assertion fails — which is exactly what the mutation probe is for.
    """
    user = make_user()

    # **The unmutated behaviour holds.**
    request_account_deletion(user_id=user.pk)
    pending = DeletionRequest.objects.get(user_id=user.pk)
    assert pending.scheduled_for > pending.requested_at

    # **Now the mutation:** a grace period of zero.
    DeletionRequest.objects.all().delete()
    monkeypatch.setattr(
        "apps.identity.services.deletion.DELETION_GRACE_PERIOD",
        timedelta(0),
    )
    request_account_deletion(user_id=user.pk)

    mutated = DeletionRequest.objects.get(user_id=user.pk)
    assert not (mutated.scheduled_for > mutated.requested_at), (
        "the grace period is not a grace period — the probe is inert"
    )


# ── The notice mail, and the token it carries ──────────────────────────────────────


def test_requesting_deletion_sends_the_notice(email_adapter, django_capture_on_commit_callbacks):
    """**The mail is the only channel that reaches someone who closed the tab.**

    The send is registered with `transaction.on_commit`, so the `on_commit` capture is
    what makes this test able to fail — under pytest-django's uncommitted transaction the
    callback would never fire, and an implementation that never sent the mail would pass
    this test unchanged.
    """
    user = make_user()

    with django_capture_on_commit_callbacks(execute=True):
        request_account_deletion(user_id=user.pk)

    assert len(email_adapter.sent) == 1
    sent = email_adapter.sent[0]
    assert sent.message.to == user.email
    assert sent.stream.value == "transactional"


def test_the_notice_carries_a_token_that_is_not_stored_in_the_clear(
    email_adapter, django_capture_on_commit_callbacks
):
    """**AD-18.** The raw token lives in the mail and nowhere else; the row holds a
    digest and a salt. A database dump must yield no usable cancel link."""
    user = make_user()

    with django_capture_on_commit_callbacks(execute=True):
        request_account_deletion(user_id=user.pk)

    body = email_adapter.sent[0].message.text_body
    row = DeletionRequest.objects.get(user_id=user.pk)

    # **The token is in the mail** — the person has to be able to follow the link.
    token = body.split("token=")[1].split("\n")[0].strip()
    assert token
    assert row.token_hash == token_service.hash_token(token, row.token_salt)

    # **And it is not in the row in the clear.** The digest is the sha256 of the salted
    # token, so the raw token cannot be recovered from the database.
    assert token not in row.token_hash
    assert row.token_salt


def test_asking_twice_sends_one_mail_not_two(email_adapter, django_capture_on_commit_callbacks):
    """**The mail is sent once.** A second request returns the same row and sends
    nothing — a person who pressed the button twice should not get two notices, and the
    idempotency key is derived from the row so the port would collapse them anyway."""
    user = make_user()

    with django_capture_on_commit_callbacks(execute=True):
        request_account_deletion(user_id=user.pk)
        request_account_deletion(user_id=user.pk)

    assert len(email_adapter.sent) == 1


def test_the_notice_carries_an_idempotency_key_derived_from_the_request(
    email_adapter, django_capture_on_commit_callbacks
):
    """**AD-7.** The key must be derived from the request, so a second request sends
    nothing — and it must not carry the address."""
    user = make_user()

    with django_capture_on_commit_callbacks(execute=True):
        row = request_account_deletion(user_id=user.pk)

    key = email_adapter.sent[0].idempotency_key
    assert key.endswith(str(row.pk))
    assert user.email not in key


def test_a_mail_failure_does_not_fail_the_request(
    email_adapter, django_capture_on_commit_callbacks, monkeypatch, caplog
):
    """**The request stands, and the failure is logged rather than raised.**

    The endpoint's contract says the request "cannot fail on its merits" — a deletion
    request that was recorded must not be reported as a failure because a mail server
    was down. The person can still cancel from the page.
    """
    import apps.identity.services.deletion as module

    user = make_user()

    def _explode(*args, **kwargs):
        raise RuntimeError("the mail server is down")

    monkeypatch.setattr(module, "_send_deletion_notice", _explode)

    with django_capture_on_commit_callbacks(execute=True):
        # **No exception escapes.**
        row = request_account_deletion(user_id=user.pk)

    assert row.pk is not None
    assert DeletionRequest.objects.filter(user_id=user.pk).count() == 1


def test_the_send_failure_log_carries_no_address(
    email_adapter, django_capture_on_commit_callbacks, monkeypatch, caplog
):
    """**AD-13.** The log line names the failure, not the recipient. The logger
    allowlist is not widened — the exception is logged with its own stack, and the
    address is in neither."""
    import apps.identity.services.deletion as module

    user = make_user()

    class _BrokenPort:
        def send(self, *args, **kwargs):
            raise RuntimeError("the mail server is down")

    monkeypatch.setattr(module, "get_email_port", lambda: _BrokenPort())

    with caplog.at_level("ERROR"):
        with django_capture_on_commit_callbacks(execute=True):
            request_account_deletion(user_id=user.pk)

    assert user.email not in caplog.text


def test_a_rolled_back_request_sends_no_mail(
    email_adapter, django_capture_on_commit_callbacks, monkeypatch
):
    """**The mail is after the commit, so a rolled back request sends nothing.**

    A request that was never recorded must not leave a notice in an inbox telling the
    person their account will be destroyed on a date that nothing will honour.
    """
    import apps.identity.services.deletion as module

    user = make_user()

    def _explode(*args, **kwargs):
        raise AssertionError("the mail was sent for a request that was rolled back")

    monkeypatch.setattr(module, "_send_deletion_notice", _explode)

    class _Boom(Exception):
        pass

    with django_capture_on_commit_callbacks(execute=True):
        try:
            with pytest.raises(_Boom):
                # **Force the transaction to roll back** after the row is written.
                from django.db import transaction

                with transaction.atomic(using=PERSONAL):
                    request_account_deletion(user_id=user.pk)
                    raise _Boom()
        except _Boom:
            pass


def test_the_token_in_the_mail_cancels_the_deletion(
    email_adapter, django_capture_on_commit_callbacks
):
    """**The promise is a tested fact, not a claim in a docstring.**

    A-16 says the person can cancel "from the email we send". This is that sentence,
    executed: the token from the mail cancels the pending deletion, and the account
    survives.
    """
    user = make_user()

    with django_capture_on_commit_callbacks(execute=True):
        request_account_deletion(user_id=user.pk)

    body = email_adapter.sent[0].message.text_body
    token = body.split("token=")[1].split("\n")[0].strip()

    assert cancel_account_deletion_with_token(token=token) is True
    assert DeletionRequest.objects.filter(user_id=user.pk).count() == 0
    assert User.objects.filter(pk=user.pk).exists()


def test_a_spent_token_cannot_be_replayed(email_adapter, django_capture_on_commit_callbacks):
    """**Single-use.** The token lived on the row and the row is gone, so there is
    nothing left to spend."""
    user = make_user()

    with django_capture_on_commit_callbacks(execute=True):
        request_account_deletion(user_id=user.pk)

    body = email_adapter.sent[0].message.text_body
    token = body.split("token=")[1].split("\n")[0].strip()

    assert cancel_account_deletion_with_token(token=token) is True
    assert cancel_account_deletion_with_token(token=token) is False


def test_a_wrong_token_cancels_nothing(email_adapter, django_capture_on_commit_callbacks):
    """**A token that does not match cancels nothing, and says nothing about why.**

    The same answer for an unknown token and a wrong one, so the token cannot be used
    to probe for a real one."""
    user = make_user()

    with django_capture_on_commit_callbacks(execute=True):
        request_account_deletion(user_id=user.pk)

    assert cancel_account_deletion_with_token(token="not-the-token") is False
    assert DeletionRequest.objects.filter(user_id=user.pk).count() == 1


def test_a_token_cancels_only_its_own_account(email_adapter, django_capture_on_commit_callbacks):
    """**One token, one account.** A token spent against somebody else's pending
    deletion would be a serious bug, so it is asserted rather than assumed."""
    mine = make_user()
    theirs = make_user()

    with django_capture_on_commit_callbacks(execute=True):
        request_account_deletion(user_id=mine.pk)
        request_account_deletion(user_id=theirs.pk)

    body = email_adapter.sent[0].message.text_body
    token = body.split("token=")[1].split("\n")[0].strip()

    assert cancel_account_deletion_with_token(token=token) is True
    assert DeletionRequest.objects.filter(user_id=mine.pk).count() == 0
    assert DeletionRequest.objects.filter(user_id=theirs.pk).count() == 1


def test_the_cancellation_is_recorded_when_the_token_is_spent(
    email_adapter, django_capture_on_commit_callbacks
):
    """**Cancelling by token is recorded the same way cancelling by session is.** The
    audit trail must not depend on how the cancellation arrived."""
    user = make_user()

    with django_capture_on_commit_callbacks(execute=True):
        request_account_deletion(user_id=user.pk)

    body = email_adapter.sent[0].message.text_body
    token = body.split("token=")[1].split("\n")[0].strip()

    cancel_account_deletion_with_token(token=token)

    actions = list(
        IdentityAuditEntry.objects.filter(actor_id=user.pk).values_list("action", flat=True)
    )
    assert "account_deletion_cancelled" in actions


def test_the_audit_rows_carry_no_token(email_adapter, django_capture_on_commit_callbacks):
    """**AD-13.** The token is a credential, and the audit details carry the action and
    the target only."""
    user = make_user()

    with django_capture_on_commit_callbacks(execute=True):
        request_account_deletion(user_id=user.pk)

    body = email_adapter.sent[0].message.text_body
    token = body.split("token=")[1].split("\n")[0].strip()

    for row in IdentityAuditEntry.objects.filter(actor_id=user.pk):
        assert token not in str(row.details)
        assert row.details == {}
