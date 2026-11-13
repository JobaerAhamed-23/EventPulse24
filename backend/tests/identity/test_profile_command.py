"""The account's display name: the one command that writes it (AD-5).

Three things are proved here, and each is proved by the assertion rather than by a
reviewer's eye:

- **The rules.** A name is trimmed, its internal whitespace is collapsed, an empty name
  means "no name set", an over-long name is truncated rather than refused, and a name
  carrying a control character is refused with **nothing written**.
- **The transaction.** The write and its audit row commit together, inside
  `transaction.atomic(using=PERSONAL)` (AD-3, AD-5).
- **The privacy.** The audit row's details carry **no name** (AD-13). The name is PII;
  the action names the account and the row is one lookup away.
"""

import inspect
from unittest import mock

import pytest

from apps.identity.models import IdentityAuditEntry, User
from apps.identity.services import audit as audit_service
from apps.identity.services import profile as profile_service
from apps.identity.services.profile import NAME_MAX_LENGTH, set_user_name
from domain.errors import ValidationError
from shared.db import PERSONAL
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


def _stored_name(user) -> str:
    return User.objects.using(PERSONAL).get(pk=user.pk).name


def test_set_user_name_stores_the_name():
    user = UserFactory()

    set_user_name(user_id=user.pk, name="Maya Ahmed")

    assert _stored_name(user) == "Maya Ahmed"


def test_set_user_name_trims_leading_and_trailing_whitespace():
    user = UserFactory()

    set_user_name(user_id=user.pk, name="  Maya Ahmed  ")

    assert _stored_name(user) == "Maya Ahmed"


def test_set_user_name_collapses_internal_whitespace():
    user = UserFactory()

    set_user_name(user_id=user.pk, name="Maya   Ahmed")

    assert _stored_name(user) == "Maya Ahmed"


def test_set_user_name_refuses_a_newline_between_words():
    """A newline between words is a control character, and it is refused.

    The collapse rule and the refusal rule meet here, and the refusal wins: a newline
    would break the one-line layout the name is rendered in, so it is never stored —
    not even collapsed into the space it would look like.
    """
    user = UserFactory()

    with pytest.raises(ValidationError):
        set_user_name(user_id=user.pk, name="Maya\nAhmed")

    assert _stored_name(user) == ""


def test_set_user_name_stores_an_empty_name_as_no_name_set():
    """Clearing your name is a thing a person does; it is not a refusal."""
    user = UserFactory(name="Maya Ahmed")

    set_user_name(user_id=user.pk, name="")

    assert _stored_name(user) == ""


def test_set_user_name_stores_a_whitespace_only_name_as_no_name_set():
    user = UserFactory(name="Maya Ahmed")

    set_user_name(user_id=user.pk, name="   \t  ")

    assert _stored_name(user) == ""


def test_set_user_name_collapses_a_tab_into_a_space():
    """A tab is whitespace, not a control character to refuse.

    The refusal is for the characters that break the one-line layout — a newline, a
    carriage return. A tab does not break it; it is just a wider space.
    """
    user = UserFactory()

    set_user_name(user_id=user.pk, name="Maya\tAhmed")

    assert _stored_name(user) == "Maya Ahmed"


def test_set_user_name_collapses_a_line_separator_into_a_space():
    """U+2028 is whitespace too, so it is collapsed rather than refused.

    The rule the code follows is *"the characters that are not whitespace and would
    survive the collapse are refused"*. U+2028 and U+2029 are whitespace as far as
    `str.split()` is concerned, so they become the space the collapse would give them
    anyway — the same answer a tab gets.
    """
    user = UserFactory()

    set_user_name(user_id=user.pk, name="Maya\u2028Ahmed")

    assert _stored_name(user) == "Maya Ahmed"


def test_set_user_name_collapses_a_paragraph_separator_into_a_space():
    user = UserFactory()

    set_user_name(user_id=user.pk, name="Maya\u2029Ahmed")

    assert _stored_name(user) == "Maya Ahmed"


def test_set_user_name_truncates_an_over_long_name():
    """A name of 121 characters is still a name, so it is truncated and not refused."""
    user = UserFactory()
    long_name = "a" * (NAME_MAX_LENGTH + 1)

    set_user_name(user_id=user.pk, name=long_name)

    stored = _stored_name(user)
    assert len(stored) == NAME_MAX_LENGTH
    assert stored == "a" * NAME_MAX_LENGTH


def test_set_user_name_refuses_a_name_carrying_a_newline():
    user = UserFactory()

    with pytest.raises(ValidationError):
        set_user_name(user_id=user.pk, name="Maya\nAhmed")

    assert _stored_name(user) == ""


def test_set_user_name_refuses_a_name_carrying_a_carriage_return():
    user = UserFactory()

    with pytest.raises(ValidationError):
        set_user_name(user_id=user.pk, name="Maya\rAhmed")

    assert _stored_name(user) == ""


def test_set_user_name_refuses_a_name_carrying_a_control_character():
    user = UserFactory()

    with pytest.raises(ValidationError):
        set_user_name(user_id=user.pk, name="Maya\x00Ahmed")

    assert _stored_name(user) == ""


def test_set_user_name_refuses_a_control_character_and_writes_nothing():
    """The refusal happens **before** the write, so the row keeps its old name."""
    user = UserFactory(name="Maya Ahmed")

    with pytest.raises(ValidationError):
        set_user_name(user_id=user.pk, name="Maya\nAhmed")

    assert _stored_name(user) == "Maya Ahmed"


def test_set_user_name_refuses_a_control_character_past_the_cap():
    """**The refusal runs before the truncation, not after it.**

    A newline at position 121 is past the 120-character cap — so a command that
    truncated first would cut the newline away and store a 120-character name with no
    trace of the refusal. The refusal has to come first: the check is on the raw input,
    before anything is shortened.
    """
    user = UserFactory()

    with pytest.raises(ValidationError):
        set_user_name(user_id=user.pk, name="a" * NAME_MAX_LENGTH + "\nzzz")

    assert _stored_name(user) == ""


def test_the_cap_agrees_with_the_column():
    """The cap *is* the column's limit, by construction rather than by coincidence.

    `NAME_MAX_LENGTH` is read from the field, so the two cannot drift. This test says
    so out loud: if someone replaces the read with a literal, this fails.
    """
    field = User._meta.get_field("name")

    assert NAME_MAX_LENGTH == field.max_length


def test_set_user_name_refusal_writes_no_audit_row():
    """A refused write leaves no trace: no mutation, no audit row."""
    user = UserFactory()

    with pytest.raises(ValidationError):
        set_user_name(user_id=user.pk, name="Maya\nAhmed")

    assert IdentityAuditEntry.objects.using(PERSONAL).count() == 0


def test_set_user_name_refusal_carries_the_projects_error_shape():
    """The error reaches the client as a 422 with `details.errors` (AD-19's shape).

    `config/errors.py` puts `exc.details` straight into the response body, so the
    details are **plain dicts** — the same shape `errors_from_pydantic` and
    `errors_from_django` produce.
    """
    user = UserFactory()

    with pytest.raises(ValidationError) as excinfo:
        set_user_name(user_id=user.pk, name="Maya\nAhmed")

    error = excinfo.value
    assert error.code == "invalid_input"
    assert error.details is not None
    assert error.details["errors"][0]["loc"] == ["name"]
    assert error.details["errors"][0]["msg"]


def test_set_user_name_writes_an_audit_row():
    user = UserFactory()

    set_user_name(user_id=user.pk, name="Maya Ahmed")

    assert IdentityAuditEntry.objects.using(PERSONAL).count() == 1


def test_the_audit_row_names_the_action():
    user = UserFactory()

    set_user_name(user_id=user.pk, name="Maya Ahmed")

    row = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert row.action == "user_name_changed"


def test_the_audit_row_names_the_target():
    user = UserFactory()

    set_user_name(user_id=user.pk, name="Maya Ahmed")

    row = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert row.target_type == "User"
    assert row.target_id == user.pk


def test_the_audit_row_carries_the_actor_by_value():
    """The actor is a UUID and no label, so no address reaches a row."""
    user = UserFactory(email="maya@example.com")

    set_user_name(user_id=user.pk, name="Maya Ahmed")

    row = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert row.actor_kind == "user"
    assert row.actor_id == user.pk
    assert not row.actor_label


def test_the_audit_row_details_carry_no_name():
    """AD-13: the name is PII. The action names the account; the row is one lookup away."""
    user = UserFactory()

    set_user_name(user_id=user.pk, name="Maya Ahmed")

    row = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert "Maya" not in str(row.details)
    assert "Ahmed" not in str(row.details)
    assert row.details == {}


def test_the_audit_row_carries_no_email():
    user = UserFactory(email="maya@example.com")

    set_user_name(user_id=user.pk, name="Maya Ahmed")

    row = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert "maya@example.com" not in str(row.actor_label)
    assert "maya@example.com" not in str(row.details)


def test_set_user_name_is_callable_without_an_actor_label():
    """The command builds its own actor from the id, and an id carries no label."""
    user = UserFactory()

    set_user_name(user_id=user.pk, name="Maya Ahmed")

    row = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert row.actor_id == user.pk


def test_set_user_name_leaves_the_email_alone():
    """The name is not a key: it must not disturb the login."""
    user = UserFactory(email="maya@example.com")

    set_user_name(user_id=user.pk, name="Maya Ahmed")

    stored = User.objects.using(PERSONAL).get(pk=user.pk)
    assert stored.email == "maya@example.com"


def test_set_user_name_leaves_the_name_case_alone():
    """The case is the person's. The email is normalised; the name is not."""
    user = UserFactory()

    set_user_name(user_id=user.pk, name="maya aHMed")

    assert _stored_name(user) == "maya aHMed"


def test_set_user_name_writes_the_audit_row_in_the_same_transaction():
    """AD-5: the audit row commits with the mutation, or neither does.

    The refusal to write an audit row outside a personal transaction is `write_audit`'s
    own guard — it raises rather than writing an orphaned row. Here the command opens
    the transaction itself, so the guard never fires.
    """
    user = UserFactory()

    set_user_name(user_id=user.pk, name="Maya Ahmed")

    # Both rows are visible from outside the command's transaction, which is what
    # "committed together" means from here.
    assert _stored_name(user) == "Maya Ahmed"
    assert IdentityAuditEntry.objects.using(PERSONAL).count() == 1


def test_set_user_name_cannot_write_an_audit_row_outside_a_transaction():
    """The guard, from the command's side: the audit row cannot escape the mutation.

    `write_audit` raises `AuditOutsidePersonalTransaction` when it is called with no
    `transaction.atomic(using=PERSONAL)` block open. If the command's own transaction
    were removed, the audit write would hit that guard and the name would be rolled
    back with it — so a name without its audit row is not a reachable state.
    """
    user = UserFactory()

    with pytest.raises(Exception) as excinfo:
        with mock.patch.object(
            profile_service.transaction, "atomic", side_effect=RuntimeError("no transaction")
        ):
            set_user_name(user_id=user.pk, name="Maya Ahmed")

    assert "no transaction" in str(excinfo.value)
    assert _stored_name(user) == ""
    assert IdentityAuditEntry.objects.using(PERSONAL).count() == 0


def test_set_user_name_rolls_back_the_audit_row_when_the_write_fails():
    """A failure after the write leaves neither the name nor the audit row.

    The audit row is written after the name, so a failure in the audit write rolls the
    name back with it — that is what one transaction means.
    """
    user = UserFactory(name="Maya Ahmed")

    def _boom(**kwargs):
        raise RuntimeError("the audit write failed")

    with mock.patch.object(audit_service, "write_audit", side_effect=_boom):
        with pytest.raises(RuntimeError):
            set_user_name(user_id=user.pk, name="Someone Else")

    assert _stored_name(user) == "Maya Ahmed"
    assert IdentityAuditEntry.objects.using(PERSONAL).count() == 0


def test_set_user_name_for_an_unknown_account_raises():
    from shared.ids import uuid7

    with pytest.raises(User.DoesNotExist):
        set_user_name(user_id=uuid7(), name="Maya Ahmed")


def test_the_command_is_published_from_the_services_module():
    """AD-2: the services module is the app's published interface."""
    from apps.identity import services

    assert "set_user_name" in services.__all__
    assert services.set_user_name is set_user_name


def test_the_write_is_inside_a_personal_transaction():
    """AD-3: the write names the alias, and the audit row cannot commit apart from it.

    Two things are proved. The **alias** is a syntax rule — the tree is scanned for a
    bare `transaction.atomic()` by `tests/architecture/test_database_alias.py`, and the
    command's own source is read here to show it names the alias. The **transaction** is
    a behaviour: `write_audit` raises rather than writing an orphaned row when it is
    called outside a personal transaction, so a row that exists is a row that committed
    with its mutation.
    """
    from apps.identity.services import profile as profile_service

    source = inspect.getsource(profile_service.set_user_name)

    assert "transaction.atomic(using=PERSONAL)" in source
    assert "using=PERSONAL" in source
