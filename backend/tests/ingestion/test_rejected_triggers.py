"""The `0009` guard rule: entering or leaving `rejected` needs `event_version + 1` (design D2).

Raw SQL on the catalog connection, so the Python command guards are never in the path — a
pass here proves the trigger itself, which is what makes the rule true for *any* writer and
not only for `editorial_state`.
"""

from contextlib import contextmanager

import psycopg
import pytest
from django.db import IntegrityError, connections, transaction

from apps.ingestion.models import Event
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

EVENT = "catalog.ingestion_event"
NEEDS_BUMP = "entering or leaving rejected needs event_version + 1"


def execute(sql: str, params=()) -> int:
    with connections[CATALOG].cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.rowcount


@contextmanager
def restricted(message: str):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic(using=CATALOG):
        yield
    assert isinstance(excinfo.value.__cause__, psycopg.errors.RestrictViolation)
    assert message in str(excinfo.value.__cause__)


def move(event, to: str, *, bump: bool) -> int:
    version = event.event_version + 1 if bump else event.event_version
    return execute(
        f"UPDATE {EVENT} SET publication_status = %s, event_version = %s WHERE id = %s",
        [to, version, event.id],
    )


# --- The four legal transitions, each with its bump ----------------------------------------


def test_published_to_rejected_with_a_version_bump_is_allowed():
    event = EventFactory()

    assert move(event, "rejected", bump=True) == 1


def test_in_review_to_rejected_with_a_version_bump_is_allowed():
    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)

    assert move(event, "rejected", bump=True) == 1


def test_rejected_to_published_with_a_version_bump_is_allowed():
    """A reject is reversible: `rejected` is a state, not a terminal one like `superseded`."""
    event = EventFactory()
    move(event, "rejected", bump=True)
    event.refresh_from_db(using=CATALOG)

    assert move(event, "published", bump=True) == 1


def test_rejected_to_in_review_with_a_version_bump_is_allowed():
    event = EventFactory()
    move(event, "rejected", bump=True)
    event.refresh_from_db(using=CATALOG)

    assert move(event, "in_review", bump=True) == 1


# --- The same four, refused without the bump -----------------------------------------------


def test_published_to_rejected_without_a_version_bump_rejected():
    event = EventFactory()

    with restricted(NEEDS_BUMP):
        move(event, "rejected", bump=False)


def test_in_review_to_rejected_without_a_version_bump_rejected():
    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)

    with restricted(NEEDS_BUMP):
        move(event, "rejected", bump=False)


def test_rejected_to_published_without_a_version_bump_rejected():
    """The half that matters most: this is the transition ingestion would make silently.

    Without the rule, a re-poll could write `published` back over an editor's verdict and
    no version would move, so no saver would ever learn the event was back either.
    """
    event = EventFactory()
    move(event, "rejected", bump=True)
    event.refresh_from_db(using=CATALOG)

    with restricted(NEEDS_BUMP):
        move(event, "published", bump=False)


def test_rejected_to_in_review_without_a_version_bump_rejected():
    event = EventFactory()
    move(event, "rejected", bump=True)
    event.refresh_from_db(using=CATALOG)

    with restricted(NEEDS_BUMP):
        move(event, "in_review", bump=False)


# --- The rule is a boundary, not a lifecycle column (D2) -----------------------------------


def test_in_review_to_published_without_a_version_bump_still_allowed():
    """**The regression this design is most exposed to.**

    Adding `publication_status` to `LIFECYCLE_FIELDS` would have been the tidier-looking
    change and would have broken this: ingestion moves events out of timezone review
    silently on every re-resolution (`IncomingEvent.gating()`), and that path does not bump
    the version. The rule fires only on the `rejected` boundary precisely so it does not
    reach here.
    """
    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)

    assert move(event, "published", bump=False) == 1


def test_a_rejected_event_is_not_terminal_the_way_superseded_is():
    """`superseded` refuses *every* update. `rejected` refuses only an unbumped one."""
    event = EventFactory()
    move(event, "rejected", bump=True)

    assert execute(f"UPDATE {EVENT} SET title = %s WHERE id = %s", ["edited", event.id]) == 1
