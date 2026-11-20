"""The one published read of a pending account deletion.

**Why this is a separate module from `deletion.py`.** That file holds *three commands*,
and its docstring says so: *"Three commands, and the difference between them is the whole
design."* A read is not a fourth command, and putting it in that file would blur the
central claim the file makes. **This answers a question; `deletion.py` changes the world.**
The same split `billing_read.py` records, for the same reason.

**What it returns, and what it does not.** Two moments — when the request was made, and
when the account will be destroyed — and nothing else. In particular:

- **Not the row.** A frozen dataclass and never a model instance: a caller holding the row
  could write it, and `identity`'s own commands are the only writers. `BillingAccount`
  says the same thing for the same reason.
- **Not the cancel token.** `DeletionRequest` carries `token_hash` and `token_salt`, and a
  read that handed the API layer the row would hand it the digest of a bearer credential
  that cancels the account's destruction. **The token cannot reach the wire because this
  read cannot carry it** — the dataclass has exactly two fields, and both are dates.

**`None` is a real answer.** Most accounts will never delete themselves, and "there is
nothing pending" is the answer for them. It is not a failure and not an empty row.

**It reads; it never writes.** There is no command in this module, and `DeletionRequest`
has exactly one writer (`identity`'s own deletion commands).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.identity.models import DeletionRequest
from shared.db import PERSONAL


@dataclass(frozen=True)
class PendingDeletion:
    """One account's outstanding request to be deleted, as the surface needs it.

    **Two moments, and no boolean.** The surface has to say *when* the account dies — a
    person deciding whether to cancel needs a date, not a bit. `"pending": true` cannot
    answer that, and neither can a duration: the grace period is computed once, at
    request time, and a duration typed into a frontend is the mistake the mail templates
    already made — *"a number that keeps saying '30 minutes' after the constant says
    otherwise."*

    **The two differ by exactly the grace period**, and that difference is computed once.
    A later request returns the original row rather than moving the deadline, so
    `scheduled_for` here is the promise the product made, carried verbatim.
    """

    #: When the request was recorded.
    requested_at: datetime
    #: When the account will be destroyed, if the request is not cancelled first.
    scheduled_for: datetime


def read_pending_deletion(*, user_id: UUID) -> PendingDeletion | None:
    """This account's outstanding deletion request, or `None` when there is none.

    **At most one row per account.** `request_account_deletion` returns the existing row
    rather than writing another, so there is never more than one pending destruction for
    the worker to find — and this read has no need to choose between them.

    **The newest wins, and there is only one to win.** The `order_by` is there for the
    pathological case — a row written before this read existed — not because two rows are
    a normal state.
    """
    row = (
        DeletionRequest.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .order_by("-requested_at")
        .first()
    )
    if row is None:
        return None
    return PendingDeletion(requested_at=row.requested_at, scheduled_for=row.scheduled_for)


__all__ = ["PendingDeletion", "read_pending_deletion"]
