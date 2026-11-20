"""The published read of a pending account deletion.

**What these tests hold.**

1. **The two moments come back, and they are the server's.** The read reports when the
   request was made and when the account will be destroyed — the values the command
   computed, not something recomputed here.
2. **`None` is a real answer.** Most accounts will never delete themselves, and "nothing
   is pending" is the answer for them — not a failure, and not an empty row.
3. **The cancel token never reaches the wire.** `DeletionRequest` carries the digest of a
   bearer credential that cancels the account's destruction, and the read exists to be
   handed to the API layer. **A read that leaked the digest would leak a credential.**
4. **The read does not write.** There is no command in the module, and `DeletionRequest`
   has exactly one writer.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.identity.models import DeletionRequest, IdentityAuditEntry, User
from apps.identity.services.deletion import request_account_deletion
from apps.identity.services.deletion_read import read_pending_deletion
from shared.constants import DELETION_GRACE_PERIOD
from shared.db import PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


def make_user() -> User:
    return User.objects.create_user(
        email=f"sam-{timezone.now().timestamp()}@example.test", password="pw"
    )


def test_the_read_carries_both_moments():
    """**The two moments, and they are the ones the command computed.**

    The screen has to say when the account dies, so the read carries the date the
    destruction is scheduled for — and the date the request was made, so the surface can
    say "you asked on the 3rd" without recomputing anything."""
    user = make_user()

    request_account_deletion(user_id=user.pk)
    pending = read_pending_deletion(user_id=user.pk)

    assert pending is not None
    row = DeletionRequest.objects.get(user_id=user.pk)
    assert pending.requested_at == row.requested_at
    assert pending.scheduled_for == row.scheduled_for


def test_the_read_carries_no_pending_deletion_when_nothing_is_pending():
    """**`None` is a real answer.**

    Most accounts will never delete themselves. "Nothing is pending" is the answer for
    them — not a failure, and not a row of empty dates."""
    user = make_user()

    assert read_pending_deletion(user_id=user.pk) is None


def test_the_read_reports_another_accounts_deletion_as_absent():
    """**One account's pending deletion is not another's.**

    The read is keyed by the account, and the frontend only ever asks about the signed-in
    one."""
    user = make_user()
    other = make_user()

    request_account_deletion(user_id=other.pk)

    assert read_pending_deletion(user_id=user.pk) is None
    assert read_pending_deletion(user_id=other.pk) is not None


def test_the_read_carries_no_cancel_token():
    """**The token cannot reach the wire, because the read cannot carry it.**

    `DeletionRequest` holds the salted digest of a bearer credential that cancels the
    account's destruction. The read is what the API layer is handed, so a read that
    carried the digest would carry a credential with it.

    **This is the assertion that holds the dataclass to two fields.** The token is on
    the row; the read is not."""
    user = make_user()

    request_account_deletion(user_id=user.pk)
    pending = read_pending_deletion(user_id=user.pk)

    assert pending is not None
    assert not hasattr(pending, "token_hash")
    assert not hasattr(pending, "token_salt")
    # **And the values themselves carry no trace of it.**
    assert "token" not in repr(pending).lower()
    assert set(vars(pending)) == {"requested_at", "scheduled_for"}


def test_the_read_writes_nothing():
    """**A read is a read.** `DeletionRequest` has exactly one writer — `identity`'s own
    deletion commands — and this is not it."""
    user = make_user()

    request_account_deletion(user_id=user.pk)
    before_rows = DeletionRequest.objects.count()
    before_audits = IdentityAuditEntry.objects.count()

    read_pending_deletion(user_id=user.pk)

    assert DeletionRequest.objects.count() == before_rows
    assert IdentityAuditEntry.objects.count() == before_audits


def test_a_cancelled_deletion_is_no_longer_pending():
    """**Cancelling is what makes the read empty again.**

    The surface shows the way back because of this read, and the way back has to close
    when it is taken — otherwise the page would keep offering a cancel for a deletion
    that no longer exists."""
    user = make_user()

    request_account_deletion(user_id=user.pk)
    assert read_pending_deletion(user_id=user.pk) is not None

    from apps.identity.services.deletion import cancel_account_deletion

    cancel_account_deletion(user_id=user.pk)

    assert read_pending_deletion(user_id=user.pk) is None


def test_the_read_does_not_move_the_schedule():
    """**Asking again does not move the date.**

    The schedule is computed once, when the request is first made. A read that recomputed
    it — or a second request that moved it — would break the promise the product made to
    the person who asked."""
    user = make_user()

    request_account_deletion(user_id=user.pk)
    first = read_pending_deletion(user_id=user.pk)

    request_account_deletion(user_id=user.pk)
    second = read_pending_deletion(user_id=user.pk)

    assert first is not None
    assert second is not None
    assert second.scheduled_for == first.scheduled_for
    assert second.requested_at == first.requested_at


def test_the_schedule_is_the_grace_period_from_the_request():
    """**The gap between the two moments is the grace period.**

    This is the arithmetic the surface relies on, and it is the server's arithmetic — the
    constant, not a number typed into a template."""
    user = make_user()

    request_account_deletion(user_id=user.pk)
    pending = read_pending_deletion(user_id=user.pk)

    assert pending is not None
    assert pending.scheduled_for - pending.requested_at == DELETION_GRACE_PERIOD


def test_the_read_survives_a_schedule_that_has_already_passed():
    """**A row whose date has passed is still a pending row, until the worker takes it.**

    The read reports what the row says, and the worker is what removes it. A read that
    filtered on "not yet due" would make the row invisible in the window between the
    deadline passing and the worker running — and the surface would offer a cancel for an
    account that is already gone."""
    user = make_user()

    request_account_deletion(user_id=user.pk)
    DeletionRequest.objects.filter(user_id=user.pk).update(
        scheduled_for=timezone.now() - timedelta(days=1)
    )

    pending = read_pending_deletion(user_id=user.pk)

    assert pending is not None
