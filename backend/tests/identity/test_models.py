"""The `identity` models: the email uniqueness constraint, the reset token's shape, and
the audit table's append-only guard.
"""

import uuid

import pytest
from django.db import IntegrityError, connections, transaction
from django.utils import timezone

from apps.identity.models import IdentityAuditEntry, User
from shared.db import PERSONAL
from shared.models import AppendOnlyViolation, AuditEntry
from tests.identity.factories import (
    IdentityAuditEntryFactory,
    PasswordResetTokenFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


def test_user_pk_is_uuid7():
    user = UserFactory()

    assert isinstance(user.pk, uuid.UUID)
    assert user.pk.version == 7


def test_user_email_is_lowercased_on_save():
    user = UserFactory(email="Maya@Example.com")

    assert user.email == "maya@example.com"
    assert User.objects.using(PERSONAL).get(pk=user.pk).email == "maya@example.com"


def test_user_email_is_unique_case_insensitively():
    UserFactory(email="maya@example.com")

    with pytest.raises(IntegrityError):
        with transaction.atomic(using=PERSONAL):
            User.objects.using(PERSONAL).create(
                email="Maya@Example.com",
                password="irrelevant-because-the-constraint-fires-first",
            )


def test_user_has_no_username_column():
    """AD-18: the email is the login; a `username` column would be a second identity."""
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'personal' AND table_name = 'identity_user'"
        )
        columns = {row[0] for row in cursor.fetchall()}

    assert "username" not in columns
    assert "email" in columns


def test_user_email_is_not_nullable():
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'personal' AND table_name = 'identity_user' "
            "AND column_name = 'email'"
        )
        rows = cursor.fetchall()

    assert rows == [("NO",)]


def test_reset_token_stores_only_a_digest():
    """The raw token is never stored: a database dump yields no usable reset link."""
    token = PasswordResetTokenFactory()

    assert token.token_hash != "the-raw-token"
    assert len(token.token_hash) == 64
    assert token.token_hash not in token.token_salt


def test_reset_token_is_not_used_and_revoked_at_once():
    """The database refuses a row that is both used and revoked."""
    token = PasswordResetTokenFactory()

    token.used_at = timezone.now()
    token.revoked_at = timezone.now()

    with pytest.raises(IntegrityError):
        with transaction.atomic(using=PERSONAL):
            token.save(using=PERSONAL)


def test_reset_token_hash_is_unique():
    PasswordResetTokenFactory(token_hash="a" * 64)

    with pytest.raises(IntegrityError):
        with transaction.atomic(using=PERSONAL):
            PasswordResetTokenFactory(token_hash="a" * 64)


def test_identity_audit_entry_is_append_only():
    """AD-5: an audit row is written once and never updated.

    The Python guard fires first — `AppendOnlyModel.save` refuses the update before any
    SQL is sent — so the ORM path raises `AppendOnlyViolation`, not `IntegrityError`.
    The database trigger behind it is tested separately in `test_audit.py`.
    """
    entry = IdentityAuditEntryFactory()

    entry.action = "changed"
    with pytest.raises(AppendOnlyViolation):
        entry.save(using=PERSONAL)

    with pytest.raises(AppendOnlyViolation):
        entry.delete(using=PERSONAL)


def test_identity_audit_entry_is_in_the_personal_schema():
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "SELECT table_schema FROM information_schema.tables "
            "WHERE table_name = 'identity_identityauditentry'"
        )
        rows = cursor.fetchall()

    assert rows == [("personal",)]


def test_identity_audit_entry_is_an_audit_entry():
    assert issubclass(IdentityAuditEntry, AuditEntry)
