"""The ORM cannot express a cross-schema join (AD-3)."""

import pytest
from django.contrib.auth import get_user_model
from django.db import ProgrammingError, transaction

from shared.db import CATALOG, PERSONAL
from tests.wall.catalog_probe.models import Thing
from tests.wall.personal_probe.models import Note

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])


def test_subquery_inner_query_using_other_alias_raises_value_error():
    inner = Thing.objects.using(CATALOG).values("id")

    with pytest.raises(ValueError, match="Subqueries aren't allowed across different databases"):
        list(Note.objects.filter(id__in=inner))


def test_subquery_inner_query_without_using_fails_relation_missing():
    # Without .using(), the inner query compiles on the outer alias (personal), where the
    # catalog table isn't on the search path. raises() sits outside atomic() so the savepoint
    # is rolled back rather than released on the failed transaction.
    with (
        pytest.raises(ProgrammingError, match="does not exist"),
        transaction.atomic(using=PERSONAL),
    ):
        list(Note.objects.filter(id__in=Thing.objects.values("id")))


def test_foreign_key_within_same_alias_saves():
    user = get_user_model().objects.create(email="owner@example.test")

    Note.objects.create(text="hello", owner=user)

    assert Note.objects.get().owner == user
