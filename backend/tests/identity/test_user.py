"""identity.User uses a UUIDv7 primary key, stored as uuid in the personal schema."""

import uuid

import pytest
from django.db import connections

from apps.identity.models import User
from shared.db import PERSONAL


def test_user_pk_is_uuid7_before_save():
    user = User(username="someone")

    assert isinstance(user.pk, uuid.UUID)
    assert user.pk.version == 7


@pytest.mark.django_db
def test_user_id_column_is_uuid_in_personal_schema():
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "SELECT table_schema, data_type FROM information_schema.columns "
            "WHERE table_name = 'identity_user' AND column_name = 'id'"
        )
        rows = cursor.fetchall()

    assert rows == [("personal", "uuid")]


@pytest.mark.django_db
def test_user_saved_keeps_its_uuid7():
    user = User.objects.using(PERSONAL).create(username="someone")

    assert User.objects.using(PERSONAL).get(pk=user.pk).pk.version == 7
