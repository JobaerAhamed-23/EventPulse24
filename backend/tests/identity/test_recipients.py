"""The published read of a user's address (AD-2, AD-13, AD-16).

**Why this module exists** is the interesting part: `delivery` sends mail and needs a
recipient, the address lives on `identity`'s `User`, and `delivery` may not read that table
directly — the `models-identity` import contract enforces it at build time. So the read
lives in the app that owns the data and is published as a function.

These tests pin the three properties that make it safe to publish:

- **It returns the address and nothing else.** A caller that received the `User` could
  write to it, and `identity` is the only writer of that table. The address is a string,
  and a string cannot be written back.
- **`None` is a real answer.** The account may have been closed, or the id may name a
  user who never existed.
- **The address never reaches a log sink** (AD-13).
"""

from uuid import UUID

import pytest

from apps.identity.services import get_recipient_address
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


def test_the_address_is_returned_for_an_existing_account():
    user = UserFactory(email="maya@example.com")

    assert get_recipient_address(user_id=user.pk) == "maya@example.com"


def test_a_nonexistent_user_reads_as_none():
    """`None` is a real answer: the caller treats it as "there is nobody to send to"."""
    assert get_recipient_address(user_id=uuid7()) is None


def test_a_closed_account_reads_as_none():
    """A closed account is not a recipient."""
    user = UserFactory(email="gone@example.com", is_active=False)

    assert get_recipient_address(user_id=user.pk) is None


def test_the_read_returns_a_string_and_not_a_model():
    """A caller that received the model could write to it; `identity` is the only writer."""
    user = UserFactory(email="maya@example.com")

    address = get_recipient_address(user_id=user.pk)

    assert isinstance(address, str)
    assert not isinstance(address, UUID)


def test_two_users_read_their_own_addresses():
    first = UserFactory(email="first@example.com")
    second = UserFactory(email="second@example.com")

    assert get_recipient_address(user_id=first.pk) == "first@example.com"
    assert get_recipient_address(user_id=second.pk) == "second@example.com"


def test_the_address_is_not_written_anywhere():
    """The module is a read. It has no command in it, and `User` has exactly one writer."""
    from apps.identity.services import recipients

    source = recipients.__file__ or ""
    assert source
    body = open(source).read()

    for forbidden in (".save(", ".update(", ".delete(", ".create("):
        assert forbidden not in body, f"the recipients module must not write: {forbidden}"
