"""No transaction spans both schemas: the accepted cost of AD-3."""

import pytest
from django.contrib.auth import get_user_model
from django.db import connections, transaction

from shared.db import CATALOG, PERSONAL
from tests.wall.catalog_probe.models import Thing

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)


def test_catalog_rollback_does_not_undo_personal_write():
    User = get_user_model()

    with pytest.raises(RuntimeError), transaction.atomic(using=CATALOG):
        Thing.objects.create(name="discarded")
        User.objects.create(username="kept")  # default alias: outside the catalog transaction
        raise RuntimeError("abort the catalog transaction")

    assert User.objects.filter(username="kept").exists()
    assert not Thing.objects.exists()


def test_aliases_use_separate_backend_sessions():
    pids = {}
    for alias in (PERSONAL, CATALOG):
        with connections[alias].cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            pids[alias] = cursor.fetchone()[0]

    assert pids[PERSONAL] != pids[CATALOG]
