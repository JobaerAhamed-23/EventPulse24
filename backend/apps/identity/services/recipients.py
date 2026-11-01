"""The one published read of a user's address (AD-2, AD-13, AD-16).

**Why this module exists.** `delivery` sends mail, and mail needs a recipient. The address
lives on `identity`'s `User` — and `identity` owns `USER` (AD-16), so `delivery` may not read
that table directly. The `models-identity` import-linter contract is the machine that enforces
it: *"only `apps.identity` imports `apps.identity.models` (others call its services)"*.

So the read lives here, in the app that owns the data, and is published as a function. That is
the ordinary cross-module seam in this codebase — `personalization` reads `delivery`'s
preferences the same way, and `delivery` reads `personalization`'s zone the same way.

**It returns the address and nothing else.** Not the user, not the account's flags, not a
model instance. A caller that received the `User` could write to it, and `identity` is the only
writer of that table. The address is a string, and a string cannot be written back.

**`None` is a real answer.** The account may have been closed, or the id may name a user who
never existed. The caller treats `None` as "there is nobody to send to" and cancels the row —
which is the right outcome for a send whose target has vanished.

**An inactive account reads as `None` too, and that is the point.** Django's `is_active` is
documented on the model as *"Designates whether this user should be treated as active.
Unselect this instead of deleting accounts."* An account that has been deactivated is an
account that should not be mailed: the whole reason the flag exists is that the row stays
(readable to an admin, present for the audit trail) while the person stops being a
participant. **The sweep's response to `None` is to cancel the row**, so a deactivated
account's pending reminders are cancelled rather than sent — and the record of what was
supposed to happen stays.

**The address never reaches a log sink** (AD-13). It is the recipient, not a log field. The
allowlist in `adapters/logging/redaction.py` holds ids, counts, durations and slugs, and
nothing that could carry an address; a caller that logged one would have it redacted to
`[email]`, which is a safety net rather than a plan.
"""

from uuid import UUID

from django.contrib.auth import get_user_model

from shared.db import PERSONAL


def get_recipient_address(*, user_id: UUID) -> str | None:
    """The account holder's address, or `None` when there is no such account.

    A read, never a write: this module has no command in it, and the `User` table has exactly
    one writer (`identity`'s own commands).

    **An inactive account has no recipient.** See the module docstring: `is_active` is how
    this codebase says "stop treating this person as a participant without deleting the
    row", and mailing them anyway would ignore the flag.
    """
    User = get_user_model()
    return (
        User.objects.using(PERSONAL)
        .filter(pk=user_id)
        .filter(is_active=True)
        .values_list("email", flat=True)
        .first()
    )


__all__ = ["get_recipient_address"]
