"""Named collections: the table, the commands, the ordering and the one permitted delete.

**What is worth proving here is what a reading of the model cannot show:**

1. **The constraints are the database's**, not the command layer's. The name collision and
   the position collision are both asserted by reaching around the commands and writing
   rows directly — a check the application performs is a check a future code path can skip.
2. **Dense ordering survives the operations that disturb it** — create, delete and reorder —
   and two concurrent reorders do not interleave into an order nobody asked for.
3. **Deleting a collection deletes a grouping and no content.** The `SavedEvent` rows are
   still there afterwards, which is the brief's constraint in its most literal form.
"""

import threading
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.db import IntegrityError, connections, transaction

from apps.personalization.models import (
    PersonalizationAuditEntry,
    SavedCollection,
    SavedCollectionItem,
    SavedEvent,
)
from apps.personalization.services.saved_collections import (
    add_to_collection,
    create_collection,
    delete_collection,
    list_collection_saves,
    list_collections,
    remove_from_collection,
    rename_collection,
    reorder_collections,
)
from apps.personalization.services.saved_events import SavedEventNotFoundError
from domain.errors import (
    CollectionNameTaken,
    CollectionNotFoundError,
    InvalidCollectionOrderError,
)
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7
from shared.retention import RetentionCategory
from tests.personalization.factories import SavedCollectionFactory, SavedEventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def actor(user_id):
    return Actor.user(user_id)


def make_user():
    return uuid7()


def positions(user_id) -> list[int]:
    """This user's positions, in order. Dense means `[0, 1, 2, …]`."""
    return list(
        SavedCollection.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .order_by("position")
        .values_list("position", flat=True)
    )


def names_in_order(user_id) -> list[str]:
    return [view.name for view in list_collections(user_id=user_id)]


# ── The model's own integrity ──────────────────────────────────────────────────────


def test_both_models_declare_account_content_retention():
    """AD-15: the sweep, account deletion and export all read the registry, and a model
    without a category fails `eventpulse.E003`."""
    assert SavedCollection.retention_category is RetentionCategory.ACCOUNT_CONTENT
    assert SavedCollectionItem.retention_category is RetentionCategory.ACCOUNT_CONTENT


def test_one_user_cannot_have_two_collections_with_the_same_name():
    """**The database refuses it**, not the command. Written directly, around the service."""
    user_id = make_user()
    SavedCollectionFactory(user_id=user_id, name="Weekend", position=0)

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        SavedCollectionFactory(user_id=user_id, name="Weekend", position=1)


def test_the_name_constraint_folds_case():
    """ "Weekend" and "weekend" are one name for one user. A list showing both would read
    as a bug to whoever made them."""
    user_id = make_user()
    SavedCollectionFactory(user_id=user_id, name="Weekend", position=0)

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        SavedCollectionFactory(user_id=user_id, name="weekend", position=1)


def test_two_users_may_use_the_same_name():
    """The constraint is per user. Two people both having a "Weekend" is the normal case."""
    SavedCollectionFactory(user_id=make_user(), name="Weekend", position=0)
    SavedCollectionFactory(user_id=make_user(), name="Weekend", position=0)

    assert SavedCollection.objects.using(PERSONAL).filter(name="Weekend").count() == 2


def test_two_collections_at_one_position_are_allowed_until_the_check_runs():
    """**The deferral itself, in two assertions.**

    The insert that duplicates a position does *not* raise — that is what lets a reorder
    renumber a list through states where two rows briefly share a slot. The violation
    surfaces when the constraint is actually checked, which Postgres defers to commit.

    The check is forced here with `SET CONSTRAINTS ALL IMMEDIATE`, because Django wraps
    each test in a transaction that is rolled back rather than committed — so a test that
    simply expected an error at the end of a block would be asserting against a commit that
    never happens, which is exactly how the first version of this test failed.
    """
    user_id = make_user()
    SavedCollectionFactory(user_id=user_id, name="One", position=0)

    # Deferred: the write lands with no complaint.
    SavedCollectionFactory(user_id=user_id, name="Two", position=0)

    with pytest.raises(IntegrityError), connections[PERSONAL].cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_the_name_constraint_is_not_deferred():
    """**The contrast that gives the test above its meaning.** Only the position constraint
    is deferred; a duplicate name is refused at the insert, where the user can be told."""
    user_id = make_user()
    SavedCollectionFactory(user_id=user_id, name="One", position=0)

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        SavedCollectionFactory(user_id=user_id, name="One", position=1)


def test_a_blank_name_is_refused_by_the_database():
    user_id = make_user()

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        SavedCollectionFactory(user_id=user_id, name="", position=0)


def test_a_save_is_in_a_collection_at_most_once():
    user_id = make_user()
    collection = SavedCollectionFactory(user_id=user_id, position=0)
    saved = SavedEventFactory(user_id=user_id)
    SavedCollectionItem.objects.using(PERSONAL).create(collection=collection, saved_event=saved)

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        SavedCollectionItem.objects.using(PERSONAL).create(collection=collection, saved_event=saved)


# ── Creating, naming, renaming ─────────────────────────────────────────────────────


def test_a_new_collection_is_empty_and_lands_at_the_end():
    """**Empty is an ordinary state**, because membership is explicit — and the new one
    does not disturb the positions of the ones already there."""
    user_id = make_user()
    create_collection(user_id=user_id, name="Weekend", actor=actor(user_id), now=NOW)
    create_collection(user_id=user_id, name="Gigs", actor=actor(user_id), now=NOW)
    third = create_collection(user_id=user_id, name="Maybe", actor=actor(user_id), now=NOW)

    assert third.position == 2
    assert third.item_count == 0
    assert names_in_order(user_id) == ["Weekend", "Gigs", "Maybe"]


def test_the_name_is_stored_exactly_as_typed():
    """Only the comparison folds case. A user who writes "Weekend" sees "Weekend"."""
    user_id = make_user()
    view = create_collection(user_id=user_id, name="  Weekend  ", actor=actor(user_id), now=NOW)

    assert view.name == "Weekend"


def test_creating_a_name_this_user_already_has_is_refused_with_a_sentence():
    """The constraint would catch it too; the command turns it into something a person can
    read, rather than a 500 from an `IntegrityError`."""
    user_id = make_user()
    create_collection(user_id=user_id, name="Weekend", actor=actor(user_id), now=NOW)

    with pytest.raises(CollectionNameTaken):
        create_collection(user_id=user_id, name="WEEKEND", actor=actor(user_id), now=NOW)


def test_an_empty_name_is_refused_before_it_reaches_the_database():
    user_id = make_user()

    with pytest.raises(ValueError):
        create_collection(user_id=user_id, name="   ", actor=actor(user_id), now=NOW)


def test_renaming_a_collection_to_its_own_name_is_allowed():
    """**The no-op case.** A naive "does this name exist?" refuses this, because the name
    exists — on the very row being renamed."""
    user_id = make_user()
    view = create_collection(user_id=user_id, name="Weekend", actor=actor(user_id), now=NOW)

    renamed = rename_collection(
        user_id=user_id, collection_id=view.id, name="Weekend", actor=actor(user_id), now=NOW
    )

    assert renamed.name == "Weekend"


def test_renaming_onto_another_collections_name_is_refused():
    user_id = make_user()
    create_collection(user_id=user_id, name="Weekend", actor=actor(user_id), now=NOW)
    gigs = create_collection(user_id=user_id, name="Gigs", actor=actor(user_id), now=NOW)

    with pytest.raises(CollectionNameTaken):
        rename_collection(
            user_id=user_id, collection_id=gigs.id, name="weekend", actor=actor(user_id), now=NOW
        )


def test_another_users_collection_is_reported_as_absent():
    """Not "forbidden": saying it exists would confirm another user's collection, and a
    name is content they wrote."""
    mine = make_user()
    theirs = create_collection(
        user_id=make_user(), name="Theirs", actor=actor(make_user()), now=NOW
    )

    with pytest.raises(CollectionNotFoundError):
        rename_collection(
            user_id=mine, collection_id=theirs.id, name="Mine", actor=actor(mine), now=NOW
        )


# ── Membership ─────────────────────────────────────────────────────────────────────


def test_one_save_can_be_in_two_collections_at_once():
    """The whole reason membership is a table rather than a column on the save."""
    user_id = make_user()
    weekend = create_collection(user_id=user_id, name="Weekend", actor=actor(user_id), now=NOW)
    gigs = create_collection(user_id=user_id, name="Gigs", actor=actor(user_id), now=NOW)
    saved = SavedEventFactory(user_id=user_id)

    for collection in (weekend, gigs):
        add_to_collection(
            user_id=user_id,
            collection_id=collection.id,
            saved_event_id=saved.id,
            actor=actor(user_id),
            now=NOW,
        )

    assert list_collection_saves(user_id=user_id, collection_id=weekend.id) == [saved.id]
    assert list_collection_saves(user_id=user_id, collection_id=gigs.id) == [saved.id]


def test_adding_the_same_save_twice_is_one_row_and_one_audit_entry():
    """Idempotent: the second add changed nothing, so it records nothing."""
    user_id = make_user()
    collection = create_collection(user_id=user_id, name="Weekend", actor=actor(user_id), now=NOW)
    saved = SavedEventFactory(user_id=user_id)

    for _ in range(2):
        add_to_collection(
            user_id=user_id,
            collection_id=collection.id,
            saved_event_id=saved.id,
            actor=actor(user_id),
            now=NOW,
        )

    assert SavedCollectionItem.objects.using(PERSONAL).count() == 1
    assert (
        PersonalizationAuditEntry.objects.using(PERSONAL)
        .filter(action="saved_collection.item_added")
        .count()
        == 1
    )


def test_another_users_save_cannot_be_added():
    """**And it is reported as a missing save, not a missing collection.** The collection
    was found a line earlier; naming it in the error would send a client looking at the
    wrong thing."""
    user_id = make_user()
    collection = create_collection(user_id=user_id, name="Weekend", actor=actor(user_id), now=NOW)
    someone_elses = SavedEventFactory(user_id=make_user())

    with pytest.raises(SavedEventNotFoundError):
        add_to_collection(
            user_id=user_id,
            collection_id=collection.id,
            saved_event_id=someone_elses.id,
            actor=actor(user_id),
            now=NOW,
        )


def test_removing_a_save_from_a_collection_leaves_the_save_itself():
    user_id = make_user()
    collection = create_collection(user_id=user_id, name="Weekend", actor=actor(user_id), now=NOW)
    saved = SavedEventFactory(user_id=user_id)
    add_to_collection(
        user_id=user_id,
        collection_id=collection.id,
        saved_event_id=saved.id,
        actor=actor(user_id),
        now=NOW,
    )

    remove_from_collection(
        user_id=user_id,
        collection_id=collection.id,
        saved_event_id=saved.id,
        actor=actor(user_id),
        now=NOW,
    )

    assert list_collection_saves(user_id=user_id, collection_id=collection.id) == []
    assert SavedEvent.objects.using(PERSONAL).filter(id=saved.id).exists()


def test_a_collection_can_be_empty():
    user_id = make_user()
    collection = create_collection(user_id=user_id, name="Someday", actor=actor(user_id), now=NOW)

    assert list_collection_saves(user_id=user_id, collection_id=collection.id) == []
    assert list_collections(user_id=user_id)[0].item_count == 0


def test_unsaving_an_event_takes_its_memberships_with_it():
    """**The database does this, not a command.** `on_delete=CASCADE` is why no future code
    path can leave a membership row pointing at a save that is gone."""
    user_id = make_user()
    collection = create_collection(user_id=user_id, name="Weekend", actor=actor(user_id), now=NOW)
    saved = SavedEventFactory(user_id=user_id)
    add_to_collection(
        user_id=user_id,
        collection_id=collection.id,
        saved_event_id=saved.id,
        actor=actor(user_id),
        now=NOW,
    )

    saved.delete(using=PERSONAL)

    assert SavedCollectionItem.objects.using(PERSONAL).count() == 0
    assert SavedCollection.objects.using(PERSONAL).filter(id=collection.id).exists()


# ── Deleting a collection ──────────────────────────────────────────────────────────


def test_deleting_a_collection_leaves_every_save_inside_it_intact():
    """**The acceptance criterion, literally.** What is deleted is a grouping; the saves
    become uncollected and are otherwise untouched."""
    user_id = make_user()
    collection = create_collection(user_id=user_id, name="Weekend", actor=actor(user_id), now=NOW)
    saves = [SavedEventFactory(user_id=user_id) for _ in range(3)]
    for saved in saves:
        add_to_collection(
            user_id=user_id,
            collection_id=collection.id,
            saved_event_id=saved.id,
            actor=actor(user_id),
            now=NOW,
        )

    delete_collection(user_id=user_id, collection_id=collection.id, actor=actor(user_id), now=NOW)

    assert SavedCollection.objects.using(PERSONAL).filter(id=collection.id).count() == 0
    assert SavedCollectionItem.objects.using(PERSONAL).count() == 0
    for saved in saves:
        assert SavedEvent.objects.using(PERSONAL).filter(id=saved.id).exists()


def test_deleting_from_the_middle_closes_the_gap():
    """Positions stay dense, so a later reorder never has to reason about a hole."""
    user_id = make_user()
    for name in ("One", "Two", "Three", "Four"):
        create_collection(user_id=user_id, name=name, actor=actor(user_id), now=NOW)
    second = list_collections(user_id=user_id)[1]

    delete_collection(user_id=user_id, collection_id=second.id, actor=actor(user_id), now=NOW)

    assert positions(user_id) == [0, 1, 2]
    assert names_in_order(user_id) == ["One", "Three", "Four"]


def test_deleting_records_how_many_saves_it_released():
    user_id = make_user()
    collection = create_collection(user_id=user_id, name="Weekend", actor=actor(user_id), now=NOW)
    for _ in range(2):
        add_to_collection(
            user_id=user_id,
            collection_id=collection.id,
            saved_event_id=SavedEventFactory(user_id=user_id).id,
            actor=actor(user_id),
            now=NOW,
        )

    delete_collection(user_id=user_id, collection_id=collection.id, actor=actor(user_id), now=NOW)

    entry = (
        PersonalizationAuditEntry.objects.using(PERSONAL)
        .filter(action="saved_collection.deleted")
        .get()
    )
    assert entry.details["items_released"] == 2


# ── Reordering ─────────────────────────────────────────────────────────────────────


def test_a_reorder_rewrites_the_whole_list_densely():
    """**This is the test the deferred constraint exists for.** Reversing four collections
    walks through states where two rows briefly share a position."""
    user_id = make_user()
    created = [
        create_collection(user_id=user_id, name=name, actor=actor(user_id), now=NOW)
        for name in ("One", "Two", "Three", "Four")
    ]

    reorder_collections(
        user_id=user_id,
        ordered_ids=[view.id for view in reversed(created)],
        actor=actor(user_id),
        now=NOW,
    )

    assert names_in_order(user_id) == ["Four", "Three", "Two", "One"]
    assert positions(user_id) == [0, 1, 2, 3]


def test_a_reorder_must_name_every_collection():
    """A partial list would leave the unnamed ones somewhere nobody asked for.

    **`InvalidCollectionOrderError`, not `ValueError`** — `saved-collections-api` put this
    body on the wire, and a `ValueError` would have reached the caller as a 500 for a
    request the server understood perfectly and chose to refuse.
    """
    user_id = make_user()
    created = [
        create_collection(user_id=user_id, name=name, actor=actor(user_id), now=NOW)
        for name in ("One", "Two", "Three")
    ]

    with pytest.raises(InvalidCollectionOrderError):
        reorder_collections(
            user_id=user_id,
            ordered_ids=[created[0].id, created[1].id],
            actor=actor(user_id),
            now=NOW,
        )


def test_a_reorder_cannot_name_the_same_collection_twice():
    user_id = make_user()
    created = [
        create_collection(user_id=user_id, name=name, actor=actor(user_id), now=NOW)
        for name in ("One", "Two")
    ]

    with pytest.raises(InvalidCollectionOrderError):
        reorder_collections(
            user_id=user_id,
            ordered_ids=[created[0].id, created[0].id],
            actor=actor(user_id),
            now=NOW,
        )


def test_a_reorder_naming_another_users_collection_is_refused():
    user_id = make_user()
    mine = create_collection(user_id=user_id, name="Mine", actor=actor(user_id), now=NOW)
    theirs = SavedCollectionFactory(user_id=make_user(), position=0)

    with pytest.raises(CollectionNotFoundError):
        reorder_collections(
            user_id=user_id,
            ordered_ids=[mine.id, theirs.id],
            actor=actor(user_id),
            now=NOW,
        )


def test_a_refused_reorder_changes_nothing():
    """The raise unwinds the transaction, so a rejected order leaves the old one whole."""
    user_id = make_user()
    created = [
        create_collection(user_id=user_id, name=name, actor=actor(user_id), now=NOW)
        for name in ("One", "Two", "Three")
    ]

    with pytest.raises(InvalidCollectionOrderError):
        reorder_collections(
            user_id=user_id,
            ordered_ids=[created[2].id, created[1].id],
            actor=actor(user_id),
            now=NOW,
        )

    assert names_in_order(user_id) == ["One", "Two", "Three"]
    assert positions(user_id) == [0, 1, 2]


def test_two_concurrent_reorders_leave_one_whole_order_and_no_duplicate_position():
    """**The race the advisory lock exists for.**

    Two threads reorder the same user's list at the same time. Without the lock they
    interleave their renumberings and commit an order neither asked for — or collide on the
    deferred constraint at commit. With it, one waits, and the list that survives is one of
    the two orders, entire.
    """
    user_id = make_user()
    created = [
        create_collection(user_id=user_id, name=name, actor=actor(user_id), now=NOW)
        for name in ("One", "Two", "Three", "Four")
    ]
    forward = [view.id for view in created]
    backward = list(reversed(forward))
    start = threading.Barrier(2)
    errors: list[BaseException] = []

    def reorder(order):
        try:
            start.wait(timeout=5)
            reorder_collections(user_id=user_id, ordered_ids=order, actor=actor(user_id), now=NOW)
        except BaseException as exc:  # noqa: BLE001 - recorded and asserted below
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=reorder, args=(backward,)),
        threading.Thread(target=reorder, args=(forward,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert errors == []
    # Dense and unique, whichever order won.
    assert positions(user_id) == [0, 1, 2, 3]
    final = [view.id for view in list_collections(user_id=user_id)]
    assert final in (forward, backward)


# ── Reads and audit ────────────────────────────────────────────────────────────────


def test_a_reorder_counts_the_collections_in_one_query_not_one_each():
    """**The N+1 found in review.** `_view`'s fallback counts one collection, which is
    right for a command that touched one and wrong for a reorder, which returns the whole
    list. Twelve collections cost twelve extra COUNTs until this was pinned."""
    user_id = make_user()
    created = [
        create_collection(user_id=user_id, name=name, actor=actor(user_id), now=NOW)
        for name in ("One", "Two", "Three", "Four")
    ]

    with connections[PERSONAL].execute_wrapper(_counting_wrapper(queries := [])):
        reorder_collections(
            user_id=user_id,
            ordered_ids=[view.id for view in reversed(created)],
            actor=actor(user_id),
            now=NOW,
        )

    counting = [sql for sql in queries if "COUNT" in sql.upper()]
    assert len(counting) <= 1, f"a reorder ran {len(counting)} counting queries"


def test_the_list_read_counts_each_collection_without_a_query_per_row():
    user_id = make_user()
    weekend = create_collection(user_id=user_id, name="Weekend", actor=actor(user_id), now=NOW)
    create_collection(user_id=user_id, name="Empty", actor=actor(user_id), now=NOW)
    for _ in range(3):
        add_to_collection(
            user_id=user_id,
            collection_id=weekend.id,
            saved_event_id=SavedEventFactory(user_id=user_id).id,
            actor=actor(user_id),
            now=NOW,
        )

    with connections[PERSONAL].execute_wrapper(_counting_wrapper(queries := [])):
        views = list_collections(user_id=user_id)

    assert [view.item_count for view in views] == [3, 0]
    # Two: the collections, and one grouped read of the memberships.
    assert len(queries) == 2


def _counting_wrapper(sink: list):
    def wrapper(execute, sql, params, many, context):
        sink.append(sql)
        return execute(sql, params, many, context)

    return wrapper


def test_one_users_collections_are_not_another_users():
    mine = make_user()
    theirs = make_user()
    create_collection(user_id=mine, name="Mine", actor=actor(mine), now=NOW)
    create_collection(user_id=theirs, name="Theirs", actor=actor(theirs), now=NOW)

    assert names_in_order(mine) == ["Mine"]
    assert names_in_order(theirs) == ["Theirs"]


@pytest.mark.parametrize(
    "action",
    [
        "saved_collection.created",
        "saved_collection.renamed",
        "saved_collection.reordered",
        "saved_collection.item_added",
        "saved_collection.item_removed",
        "saved_collection.deleted",
    ],
)
def test_every_command_writes_its_audit_row(action):
    """AD-5: one row per mutation, in the mutation's own transaction."""
    user_id = make_user()
    first = create_collection(user_id=user_id, name="Weekend", actor=actor(user_id), now=NOW)
    create_collection(user_id=user_id, name="Gigs", actor=actor(user_id), now=NOW)
    rename_collection(
        user_id=user_id, collection_id=first.id, name="Weekends", actor=actor(user_id), now=NOW
    )
    saved = SavedEventFactory(user_id=user_id)
    add_to_collection(
        user_id=user_id,
        collection_id=first.id,
        saved_event_id=saved.id,
        actor=actor(user_id),
        now=NOW,
    )
    remove_from_collection(
        user_id=user_id,
        collection_id=first.id,
        saved_event_id=saved.id,
        actor=actor(user_id),
        now=NOW,
    )
    reorder_collections(
        user_id=user_id,
        ordered_ids=[view.id for view in reversed(list_collections(user_id=user_id))],
        actor=actor(user_id),
        now=NOW,
    )
    delete_collection(user_id=user_id, collection_id=first.id, actor=actor(user_id), now=NOW)

    assert PersonalizationAuditEntry.objects.using(PERSONAL).filter(action=action).exists(), (
        f"no audit row for {action}"
    )


def test_a_collection_id_that_does_not_exist_is_not_found():
    user_id = make_user()

    with pytest.raises(CollectionNotFoundError):
        list_collection_saves(user_id=user_id, collection_id=uuid4())
