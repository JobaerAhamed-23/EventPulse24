---
id: user-name-model-and-command
title: The Name on the Account — the Field and the Command That Writes It
intent: account-profile-name
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-13
run_id: run-eventpulse24-032
completed_at: 2026-11-13T10:11:34.588Z
---

# Work Item: The Name on the Account — the Field and the Command That Writes It

## Description

**The product has no name.** `User` (`backend/apps/identity/models.py:23`) carries
`email`, `is_staff`, `is_active` and `date_joined` — nothing else. `CurrentUserOut`
(`backend/apps/identity/schemas.py:84`) carries `id`, `email` and `onboarding`. The
frontend derives a display name from the email's local part and that rule is
**copy-pasted into 12 pages**.

This work item adds the field and the one command that writes it. **No endpoint and no
UI** — those are the next two items. The item is the seam: after it lands, the backend
can hold a name and can be asked to change one, and nothing else has moved.

### The field

```python
name = models.CharField(max_length=120, blank=True, default="")
```

on `User`, after `email` (line 45).

**Blank, not null.** `""` means "no name set". The email-derived fallback is a
*display* concern, not a stored one — the backend does not know how a human renders
their own name from an address, and must not guess. A `null` would make "cleared" and
"never set" two states with the same meaning.

**The migration is `0005_user_name.py`.** `backend/apps/identity/migrations/` currently
ends at `0004_dataexport.py`.

**Retention is already declared.** `User.retention_category = ACCOUNT_IDENTITY`
(`models.py:41`), so the new column inherits the account-identity category. No new
retention declaration is needed, and `manage.py check` stays green (AD-15).

**The export picks it up for free.** `apps/identity/services/export_serializer.py`
serialises model fields generically from the retention registry, and `User.export_user_path
= "id"` (`models.py:39`). A user's own export therefore includes their name without any
change to the exporter (FR-52).

### The command

`backend/apps/identity/services/profile.py` (new):

```python
def set_user_name(*, user_id: UUID, name: str) -> None:
```

Published from `apps/identity/services/__init__.py` — imports and `__all__` — because
the services module **is** the app's published interface (AD-2, and the `models-identity`
import-linter contract).

- **Trim, then collapse internal whitespace.** `"  Maya   Ahmed "` is `"Maya Ahmed"`.
- **Cap at 120 characters**, matching the column.
- **Empty is legal.** A whitespace-only name stores as `""` — "no name set", which the
  frontend renders as the email-derived fallback. This is not a refusal; clearing your
  name is a thing a person does.
- **Refuse control characters and newlines.** The name is rendered on one line in the
  rail, the bottom bar and the account sheet; a newline in it would break that layout
  and is not a name.
- The write happens inside `with transaction.atomic(using=PERSONAL):` (AD-3).
- The audit row is written **in the same transaction**, via
  `audit_service.write_audit(actor=Actor.user(user_id), action="user_name_changed",
  target_type="User", target_id=user_id, details={})`.

**The audit `details` carries no name.** `write_audit`'s own docstring says *"`details`
must carry counts and slugs, never free text"* (`services/audit.py:39`), and the name is
PII (AD-13). `ensure_account` sets the precedent — it writes
`details={"method": "password", "at": ...}` and **not** the address
(`services/accounts.py:117`). The action names the account and the row is one lookup
away.

**The command takes an `Actor`, never a `request`** — the coding standards' named-command
pattern. `Actor.user(user_id)` carries an id and no label, so no email reaches a row.

## Acceptance Criteria

- [ ] `User.name` exists as `CharField(max_length=120, blank=True, default="")`, and
      `0005_user_name.py` is the migration that adds it
- [ ] `manage.py makemigrations --check --dry-run` reports no missing migration, and
      `manage.py check` is green
- [ ] `set_user_name` trims leading/trailing whitespace and collapses internal runs of
      whitespace to one space
- [ ] A whitespace-only name is stored as `""` — **not** refused, **not** `null`
- [ ] A name longer than 120 characters is stored truncated to 120, not refused
- [ ] A name containing a newline or a control character is **refused** with a
      `domain.errors.ValidationError` (a 422 via `config/errors.py`), and **nothing is
      written**
- [ ] The write lands inside `transaction.atomic(using=PERSONAL)` — the command never
      writes outside a personal transaction
- [ ] The audit row is written **in the same transaction** as the name change
- [ ] The audit row's `action` is `user_name_changed`, its `target_type` is `"User"` and
      its `target_id` is the user's id
- [ ] The audit row's `details` **contain no name** — asserted by a test, not by review
- [ ] `set_user_name` is exported from `apps/identity/services/__init__.py` and appears
      in its `__all__`
- [ ] The command is callable **without** an actor label or an email — no PII reaches
      the audit row (AD-13)
- [ ] `tests/identity/test_profile_api.py` — or a sibling named for the command — proves
      each of the above, and every test is verified by a mutation probe that makes it
      fail
- [ ] `lint-imports` is green: `models-identity` still holds, and no other app imports
      `apps.identity.models`

## Technical Notes

- **Follow `ensure_account` (`services/accounts.py`) as the shape.** It is the closest
  thing in the codebase to this command: one write, one audit row in the same
  transaction, an actor by value, and **no PII in the details**.
- **The command takes `user_id`, not a `User`.** A command that took a model instance
  would invite a caller to pass an unsaved one. Take the id, look the row up inside the
  transaction.
- **`write_audit` raises if it is not inside an atomic PERSONAL transaction**
  (`services/audit.py:44`). The transaction is not optional plumbing here — it is what
  keeps the audit row from being committed apart from the mutation.
- **Validation belongs in the command, not in the API layer.** The API layer must not
  touch the ORM (`tests/architecture/test_no_direct_writes.py`), and the domain-error
  mapping happens once in `config/errors.py`. A refusal raised in the command reaches
  the client as a 422 with the project's error shape.
- **Truncation vs. refusal for an over-long name.** Truncating is the choice here
  because a name that is 121 characters is a name, and the column is the limit the
  product set. If the product would rather refuse, that is a decision to make
  explicitly — not a silence.
- **`User.save()` normalises the email** (`models.py:74-78`). The name needs no
  equivalent: it is not a key, not unique, and case is the person's.

## Dependencies

- (none)
