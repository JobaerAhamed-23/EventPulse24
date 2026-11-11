"""The editorial app's own reading of the FR-57 review queue (AD-14).

**This module owns no table and writes nothing.** AD-14 says the `editorial` app *"reads
`catalog` and writes through `ingestion` services like any other client; it gets no
privileged write path"*, and this is that client: it reads the queue through `ingestion`'s
published read service, and it decides **who may work it**.

---

## Why the `ModelAdmin` is not in `apps/editorial/`

Django's `admin.site.register` needs the model class, and the `models-ingestion`
import-linter contract says only `apps.ingestion` may import `apps.ingestion.models`. A
`ModelAdmin` for `ReviewItem` written here would break AD-2 on import.

So the split is by **who owns the row**, not by who works it:

- **`apps/ingestion/admin.py`** holds the `ReviewItemAdmin`. `ingestion` owns
  `REVIEW_ITEM` (AD-16), and the admin that renders a table lives with its owner — the
  rule the coding standard states: *"An app's admin lives in that app."*
- **This module** holds the *editorial reading* of the queue: the facts an editor needs,
  and the rule about who may work it.

The consequence, stated rather than hidden: Django groups its index by
`model._meta.app_label`, so the queue appears under **Ingestion** in the admin index. A
second `AdminSite` for the editorial group would give it its own index — and its own
login, its own permission namespace and its own `LogEntry`, which is a *second privileged
surface*. AD-14 exists to prevent exactly that, so there is one admin site, one
permission model and one audit log, and the group is a group of permissions within it.

---

## What this module adds

**The reviewer's reading of the queue.** `queue_view` gathers, at one instant, the ordered
queue and the three FR-57 metrics — so the page's ordering and its numbers can never
disagree about which instant they describe.

**Who may work it.** `may_review` is the access rule, and it is stated here rather than
left to Django's defaults, because "a member of the editorial group" is a requirement and
Django's model-permission check does not know about groups.

**The editor's own name.** The verdict is attributed to a person, and the person's name is
read from `personal` *for display only* — the actor id is what is stored, and it crosses
into `catalog` by value (AD-3, OQ-8).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ingestion.services import review_queue_read
from shared.db import PERSONAL

#: The group whose members work the FR-57 queue (AD-14).
#:
#: **The group is a bundle of permissions, and the permissions are the rule.** A member
#: gets `change_reviewitem` and `view_reviewitem` from the group's grant; a reviewer who
#: was granted the permission directly works the queue too, and that is right — Django's
#: permission model is per-permission, and a group is only one way to hold one. What is
#: *not* allowed is a staff user with neither, and Django's own model-permission check
#: refuses that before this module is reached.
#:
#: **Superuser is not required.** A group member with no superuser flag works the queue
#: exactly as a superuser would. The group's grant is wider than this queue — it also
#: carries the source and venue permissions the editorial role needs — but the two
#: permissions below are the ones this queue is gated on, and nothing else grants access
#: to it.
EDITORIAL_GROUP = "editorial"

#: The permissions a reviewer needs, as Django codenames.
#:
#: `change` is what lets the admin's verdicts be *saved*; `view` is what lets the queue be
#: *read*. There is deliberately no `add` and no `delete`: a review item is raised by the
#: commands that own the queue, and a resolved item is history.
#:
#: **The two are separate on purpose, and the code below keeps them separate.** A single
#: "may review" predicate that accepted either permission would hand a read-only auditor
#: the power to publish quarantined events and rewrite event facts. Reading the queue and
#: deciding its fate are different acts, and Django models them as different permissions
#: for exactly that reason.
REVIEW_PERMISSIONS = ("ingestion.change_reviewitem", "ingestion.view_reviewitem")

#: The permission that lets an editor *work* the queue — the verdicts and the edit.
REVIEW_CHANGE_PERMISSION = "ingestion.change_reviewitem"

#: The permission that lets an editor *read* the queue.
REVIEW_VIEW_PERMISSION = "ingestion.view_reviewitem"


@dataclass(frozen=True)
class QueueView:
    """The queue and its metrics, at one instant.

    **One instant for both.** The ordering of the rows and the numbers at the top of the
    page describe the same moment, so a reviewer cannot see a queue of four with a summary
    that says five.
    """

    #: The ordered queue. Open items first, then priority, then the deadline.
    items: tuple[review_queue_read.ReviewItemRow, ...]
    #: The three FR-57 numbers.
    summary: review_queue_read.QueueSummary
    #: The instant everything above was read at.
    now: datetime


def queue_view(*, now: datetime | None = None) -> QueueView:
    """The whole queue and its summary, at one instant.

    `now` is a parameter, like every other read in this codebase: no time-freezing
    library, and each boundary is testable at the exact second.
    """
    moment = now or timezone.now()
    return QueueView(
        items=tuple(review_queue_read.list_review_items(now=moment)),
        summary=review_queue_read.queue_summary(now=moment),
        now=moment,
    )


def _is_staff_reviewer(user) -> bool:
    """The two conditions that are common to reading and working the queue.

    1. **The user is signed in.** Django's admin already refuses an anonymous user before
       this is called; the check is here so the rule is stated once.
    2. **The user is staff.** The admin index is a staff surface. A signed-in customer
       account is not a reviewer, however many permissions it holds.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_staff", False))


def may_review(user) -> bool:
    """Whether this user may **work** the queue — the verdicts and the edit.

    **Three conditions, and the last one is the one that matters.**

    1. **The user is signed in.**
    2. **The user is staff.**
    3. **The user holds `change_reviewitem`.** This is what the editorial group grants,
       and what a directly-granted permission also satisfies.

    **The permission is `change`, not "either review permission".** Reading the queue is a
    different act from deciding its fate, and Django models them as different permissions
    for exactly that reason. A user who holds only `view_reviewitem` may read the queue and
    may not touch it — see `may_view`.

    **Superuser is neither required nor special.** A superuser is staff and holds every
    permission, so a superuser passes — but so does a group member with no superuser flag
    at all, which is the case the AC names and the test pins.
    """
    if not _is_staff_reviewer(user):
        return False
    return user.has_perm(REVIEW_CHANGE_PERMISSION)


def may_view(user) -> bool:
    """Whether this user may **read** the queue.

    **`view_reviewitem` is enough, and `change_reviewitem` implies it.** A reviewer who
    can work the queue can certainly look at it, so the check is "either of the two" —
    which is the opposite of `may_review`, and deliberately so.

    The asymmetry is the point: reading is a weaker permission than changing, and each
    gate asks for exactly the permission it needs. A single predicate for both would let
    the weaker permission open the stronger gate.
    """
    if not _is_staff_reviewer(user):
        return False
    return any(user.has_perm(codename) for codename in REVIEW_PERMISSIONS)


def editor_name(user_id: UUID | None) -> str | None:
    """A user's name, for display only.

    **AD-3: the actor is stored by id only.** The name is read from `personal` here, at
    display time, and never travels into `catalog` — an audit row is not a place for a
    username.

    Returns None for an unknown id, rather than a placeholder that looks like a name.
    """
    if user_id is None:
        return None
    user_model = get_user_model()
    row = user_model.objects.using(PERSONAL).filter(pk=user_id).first()
    if row is None:
        return None
    return row.get_username()


__all__ = [
    "EDITORIAL_GROUP",
    "REVIEW_CHANGE_PERMISSION",
    "REVIEW_PERMISSIONS",
    "REVIEW_VIEW_PERMISSION",
    "QueueView",
    "editor_name",
    "may_review",
    "may_view",
    "queue_view",
]
