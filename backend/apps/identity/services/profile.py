"""The account's display name: the one command that writes it (AD-5).

**A name is the only thing about an account a person can change.** The email is the
login and the key, and it is not changeable from here; the password is changed by the
reset flow, which ends the account's other sessions. So this module holds exactly one
command, `set_user_name`, and it is the door every caller goes through.

**Why the name is stored blank rather than null.** `""` is the single "no name set"
state. The product shows an email-derived name when there is no stored name, and that is
a **display** rule the frontend owns — the backend does not know how a human renders
their own name from an address, and must not guess. A null would make "cleared" and
"never set" two states with the same meaning.

**Why an empty name is not a refusal.** Clearing your name is a thing a person does.
`set_user_name(user_id=…, name="")` stores `""`, and the frontend falls back to the
address. A whitespace-only name is the same request.

**Why the name is trimmed, collapsed and truncated.** It is stored as it will be
rendered: on one line, in the rail, in the bottom bar and in the account sheet. Leading
and trailing whitespace is an artefact of a paste, and a run of internal whitespace is
not a name either — "Maya   Ahmed" is the same name as "Maya Ahmed". The cap is the
column's own limit: a name of 121 characters is still a name, so it is truncated rather
than refused. Truncating rather than refusing is a decision, recorded here rather than
left to chance.

**Why a control character is refused.** A newline in the name would break the one-line
layout the name is rendered in, and it is not a name. The refusal is a
`domain.errors.ValidationError`, which `config/errors.py` maps to a 422 — and it happens
**before** the write, so nothing is stored. **A tab is not refused**: it is whitespace,
and a name typed with a tab in it is a name with a space in it.

**Why the audit row carries no name (AD-13).** The name is PII. `write_audit`'s own
docstring says *"details must carry counts and slugs, never free text"*, and
`ensure_account` sets the precedent — it writes `details={"method": "password", "at": …}`
and **not** the address. The action names the account and the row is one lookup away.

**Why the command takes a `user_id` and not a `User`.** A command that took a model
instance would invite a caller to pass an unsaved one. The row is looked up inside the
transaction, and the command owns what it writes.

**Why the actor is the account itself.** `sign_up` and `reset_password` do the same: a
person changing their own account is the actor. `Actor.user(user.pk)` carries a UUID and
no label, so no address reaches a row (AD-13).
"""

from uuid import UUID

from django.db import transaction

from apps.identity.models import User
from apps.identity.services import audit as audit_service
from domain.errors import ValidationError
from shared.actor import Actor
from shared.db import PERSONAL

#: The column's own limit. A longer name is truncated to it, not refused.
#:
#: **It is read from the field, not written out here.** Two literals would be two
#: numbers that could drift: widen the column to 200 and the command would still
#: truncate at 120, with no error raised and no test failing. Reading the field means
#: the cap *is* the column's limit, by construction.
NAME_MAX_LENGTH = User._meta.get_field("name").max_length

#: The characters that cannot appear in a name: the C0 control range **minus** the
#: whitespace ones, plus DEL.
#:
#: Tab is deliberately absent: it is whitespace, and a name typed with a tab in it is a
#: name with a space in it. Newline and carriage return are not — they would break the
#: one-line layout the name is rendered in, and they are refused rather than collapsed.
#:
#: **The line separators U+2028 and U+2029 are collapsed, not refused.** They are
#: whitespace as far as `str.split()` is concerned, so they become the space the
#: collapse rule would give them anyway. That is deliberate: a name typed with a line
#: separator in it is a name with a space in it, exactly as a name typed with a tab is.
#: The characters refused here are the ones that are **not** whitespace and would
#: therefore survive the collapse into the stored name.
_CONTROL_CHARACTERS = frozenset(chr(code) for code in range(0x20) if code not in (0x09,)) | {
    chr(0x7F)
}

_NAME_ERROR_MESSAGE = "A name can't contain line breaks or control characters."


def _clean_name(name: str) -> str:
    """The name as it will be stored: trimmed, collapsed, capped.

    Raises:
        ValidationError: The name carries a control character. Nothing is written.
    """
    if any(character in _CONTROL_CHARACTERS for character in name):
        raise ValidationError(
            _NAME_ERROR_MESSAGE,
            details={"errors": [{"loc": ["name"], "msg": _NAME_ERROR_MESSAGE}]},
        )

    collapsed = " ".join(name.split())
    return collapsed[:NAME_MAX_LENGTH]


def set_user_name(*, user_id: UUID, name: str) -> str:
    """Set this account's name, and record the change in the audit log (AD-5).

    Args:
        user_id: The account to change. The row is looked up inside the transaction.
        name: The name as the person typed it. Trimmed and collapsed; capped at
            `NAME_MAX_LENGTH`. An empty (or whitespace-only) name means "no name set".

    Returns:
        The name as it was **stored** — trimmed, collapsed and capped. This is not the
        same string as the one that came in: the caller asked for `"  Maya   Ahmed  "`
        and the account now holds `"Maya Ahmed"`. Returning the stored value means a
        caller can report what the account actually holds without re-reading the row,
        which is the same shape `ensure_account` and `authenticate` already have.

    Raises:
        ValidationError: The name carries a control character or a line break. Nothing
            is written.
        User.DoesNotExist: No account carries that id.
    """
    cleaned = _clean_name(name)

    with transaction.atomic(using=PERSONAL):
        user = User.objects.using(PERSONAL).get(pk=user_id)
        user.name = cleaned
        user.save(using=PERSONAL, update_fields=["name"])

        # The actor is the account itself, by id and with no label — so no address
        # reaches the row (AD-13). The details carry no name either: the action names
        # the account, and the row is one lookup away.
        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="user_name_changed",
            target_type="User",
            target_id=user.pk,
            details={},
        )

    return cleaned


__all__ = ["NAME_MAX_LENGTH", "set_user_name"]
