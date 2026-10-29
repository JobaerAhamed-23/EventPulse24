---
run: run-eventpulse24-020
work_item: account-auth-core
intent: onboarding-and-account
generated: 2026-10-29
mode: validate
---

# Implementation Walkthrough: Account & Auth Core (identity services)

## Summary

The `identity` app's account core, implemented as **services only** — no HTTP endpoints.
Sign-up, sign-in, password-reset request, password-reset consumption, sign-out and
session invalidation, each with the security property the work item names pinned by a
test that fails when the property is broken: enumeration safety in result *and* timing,
a single-use short-lived reset token stored only as a salted digest, per-IP and
per-account throttling, an append-only audit log with no PII in it, and a password
change that ends the account's other sessions.

The next item, `auth-api-and-session-seam`, puts the HTTP endpoints over these services.

## Structure Overview

The `identity` app owns three tables in the `personal` schema: the account, its
outstanding reset tokens, and its audit log. Everything the account *does* is a service
function that takes explicit arguments and returns a value — no service receives a
`request`, because authentication is resolved at the API edge.

Four properties shape the whole design:

**Enumeration safety.** Three public operations can be used to probe whether an account
exists. Each handles that the same way: the result shape does not depend on whether the
address is taken; the outcome is identical for a known and an unknown address; and where
timing could leak, it is equalised by doing the same work on both paths.

**The reset token is a stored row, not a signed value.** Django's
`PasswordResetTokenGenerator` was probed against the pinned Django 6.1.2 before choosing:
it is *not* single-use — two consecutive `check_token` calls with no state change both
succeed, and it only becomes single-use because the password changes. It is replayable
between issuance and use, and it cannot be revoked or listed. A stored row gives all
three properties, and holds only a salted digest, so a database dump yields no usable
reset link.

**The throttle is a port with an injectable clock.** The limit has to be testable
deterministically, so the counting store is an ABC with an in-memory fake that owns its
own clock. A test calls the operation N times and asserts the N+1-th is refused — no
sleeping, no Redis, no timing flake. The Redis adapter is a separate small file behind
the same interface.

**Audit rows live in the mutation's transaction.** `write_audit` outside a personal
transaction raises rather than writing an orphaned row, so an audit row can never record
a change that rolled back.

## Architecture

### Pattern Used

**Service layer over a ports-and-adapters boundary**, with the domain rules held in the
services and the volatile technology (Redis, SMTP) held behind ABCs. The app never imports
an adapter — it reaches one through a port — which is what the `apps | adapters` import
contract enforces.

The layering points inward: `config | worker` → `apps | adapters` → `ports` → `domain` →
`shared`. `domain/` stays pure stdlib, which is why the constants it needs live in
`shared/constants.py` and nothing Django-dependent does.

### Layer Structure

```text
┌──────────────────────────────────────────┐
│  config  (Django settings, adapters)     │  ← the API edge lands here next item
├──────────────────────────────────────────┤
│  apps.identity.services                  │  ← the commands and queries
│    sign_up · authenticate                 │
│    request_password_reset · reset_password│
│    sign_out · end_other_sessions          │
├──────────────────────────────────────────┤
│  ports.throttle · ports.email             │  ← ABCs over frozen dataclasses
├──────────────────────────────────────────┤
│  adapters.throttle.{memory,redis}        │  ← the volatile technology
├──────────────────────────────────────────┤
│  shared  (constants, db aliases, actor)  │  ← stdlib only
└──────────────────────────────────────────┘
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/ports/throttle.py` | The `ThrottlePort` ABC and `ThrottleDecision` — the counting store the app talks to |
| `backend/adapters/throttle/__init__.py` | Package marker |
| `backend/adapters/throttle/memory.py` | The in-memory fake with an injectable clock — the tested path |
| `backend/adapters/throttle/redis.py` | The Redis adapter (`INCR` + `EXPIRE`) |
| `backend/apps/identity/managers.py` | `UserManager` keyed on email: `create_user`, `create_superuser`, `get_by_natural_key`, `normalise_email` |
| `backend/apps/identity/services/audit.py` | The `identity` audit writer, with the same-transaction guard |
| `backend/apps/identity/services/throttle.py` | The two keys (per-IP, per-account) and the limit table |
| `backend/apps/identity/services/emails.py` | The reset mail: the link, the body, the stream |
| `backend/apps/identity/services/sign_up.py` | `sign_up` — enumeration-safe account creation |
| `backend/apps/identity/services/authenticate.py` | `authenticate` — timing-equalised sign-in |
| `backend/apps/identity/services/password_reset.py` | `request_password_reset` and `reset_password` |
| `backend/apps/identity/services/session.py` | `sign_out` and `end_other_sessions` |
| `backend/apps/identity/templates/identity/password_reset.txt` | The reset mail body |
| `backend/apps/identity/migrations/0002_*.py` | The reset-token and audit tables, the email backfill, the append-only trigger |
| `backend/tests/identity/conftest.py` | The `email_adapter` and `throttle_adapter` fixtures, and `patch_module_attribute` |
| `backend/tests/identity/factories.py` | The `User`, `PasswordResetToken` and `IdentityAuditEntry` factories |
| `backend/tests/identity/test_*.py` (10 files) | 109 tests, one file per rule |

### Modified

| File | Changes |
|------|---------|
| `backend/apps/identity/models.py` | `User` drops `username` and gains `email` as `USERNAME_FIELD`; adds `PasswordResetToken` and `IdentityAuditEntry` |
| `backend/apps/identity/admin.py` | Registers `User` by email; read-only for the audit table |
| `backend/apps/identity/services/__init__.py` | Publishes the service functions as the module's interface |
| `backend/apps/ingestion/admin.py` | `_usernames` → `_actor_names` after the column drop |
| `backend/config/adapters.py` | The `throttle` entry in the fake and real adapter tables |
| `backend/config/env.py` | `csrf_trusted_origins`, `frontend_base_url` |
| `backend/config/settings.py` | The session cookie flags and lifetime; `CSRF_TRUSTED_ORIGINS` |
| `backend/config/settings_test.py` | Pins `DEBUG = False` for the test environment |
| `backend/config/management/commands/seed_local_stack.py` | The operator is keyed on `email` |
| `backend/domain/errors.py` | `AuthenticationFailedError`, `InvalidResetTokenError`, `ThrottledError` |
| `backend/ports/registry.py` | `ThrottlePort` in `PORT_KEYS`; `get_throttle_port()` |
| `backend/pyproject.toml` | `adapters.throttle` added to three SDK contracts; the new `redis-sdk` contract |
| `backend/shared/constants.py` | The session lifetime, the token lifetime, the throttle window and the six limits |
| `backend/tests/architecture/test_import_contracts.py` | The Redis contract test |
| 11 test files across `ingestion`, `personalization`, `wall` and `e2e` | Rewired from `username=` to `email=` |

## Domain Model

### Entities

| Entity | Properties | Business Rules |
|--------|------------|----------------|
| `User` | `email` (unique, case-insensitive), `password` (hash), `is_active`, `is_staff`, `is_superuser`, `date_joined` | The email **is** the login; there is no `username`. The email is normalised (trimmed, lowercased) before it is stored, so a unique index on it *is* a case-insensitive unique index. `save()` normalises as a backstop, so even a write that bypasses the services cannot store a mixed-case value and slip past the constraint. |
| `PasswordResetToken` | `user_id` (by value, not a relation), `token_hash`, `token_salt`, `expires_at`, `used_at`, `revoked_at` | Only the **digest** is stored. A token is used or revoked, never both. `token_hash` is unique. The token is single-use, short-lived and revocable — properties Django's stateless generator does not have. |
| `IdentityAuditEntry` | `actor_kind`, `actor_id`, `actor_label`, `action`, `target_type`, `target_id`, `details`, `at` | Append-only, enforced twice: a Python guard and a database trigger. The actor is stored by value as a UUID — **no email ever reaches a row**. One row per mutation, written in the mutation's transaction. |

### Value Objects

| Value Object | Properties | Constraints |
|--------------|------------|-------------|
| `SignUpOutcome` | `accepted` (defaulted) | Deliberately has **no** field that distinguishes "created" from "already existed". The same value is returned either way. |
| `ThrottleDecision` | `allowed`, `retry_after_seconds` | Frozen. `retry_after_seconds` is zero when the attempt is allowed. |
| `Actor` (`shared`) | `kind`, `id`, `label` | A user actor has an id and no label; a system actor has a label and no id. The database enforces the same rule as a check constraint. |

## Key Implementation Details

### 1. The email uniqueness is a database constraint, not an application check

The address is normalised before it is written, so a plain unique index on the normalised
column *is* the case-insensitive unique index. The `IntegrityError` the constraint raises
is what makes the race between two concurrent sign-ups for the same address safe: the
loser gets the same outcome as the signer-up of a brand-new address.

### 2. The unknown-email sign-in path still performs a hash

`DUMMY_PASSWORD_HASH` is computed once at import time from a random password nobody
knows, and is checked against on the unknown-address path. Without it, an unknown address
would answer far faster than a wrong password — the difference is an account-existence
oracle. A test monkeypatches the hasher with a recorder and asserts it was called on the
unknown-address path, so removing the equalisation fails the suite.

### 3. The reset token's digest is compared per-row, in constant time

The digest depends on the row's own salt, so it cannot be computed without knowing the
salt — and the salt is not known until the row is found. The lookup therefore walks the
outstanding rows and compares each one's digest with `secrets.compare_digest`. The rows
are read with `select_for_update()`, and the consumption is a **conditional** update, so
the database — not just the lock — is the arbiter of single-use.

### 4. The audit row and the mutation commit together

`write_audit` raises `AuditOutsidePersonalTransaction` if it is called outside a personal
transaction, so an audit row can never be committed apart from the change it records. The
sign-up path narrows its `IntegrityError` catch to the **insert alone** using a nested
savepoint, so a failure anywhere else is a real failure and propagates — it is never
reported to the caller as "that address is taken".

### 5. The session that a reset was made from survives

A password reset ends every *other* session of the account, so a stolen session does not
survive a password change. The session the reset was made from is kept — it is rotated by
the caller, not deleted — so the person who just reset their password is not signed out of
the browser they did it in.

## Security Considerations

| Concern | Approach |
|---------|----------|
| Account enumeration (sign-up) | The same outcome value is returned whether or not the address is taken. The existing holder is notified by email — the only channel that reaches them, not the caller. |
| Account enumeration (sign-in) | One error and one message for both a wrong password and an unknown address. The unknown-address path performs a real hash check against a dummy hash, so the timing is equalised too. |
| Account enumeration (reset request) | An unknown address sends nothing and returns exactly what a known one returns. |
| Throttle as an oracle | The throttle runs **before** the account lookup, so a 429 cannot reveal whether the account exists. |
| Reset token at rest | Only `sha256(salt + token)` is stored, with a per-row salt. A database dump yields no usable reset link. The raw token appears in the email and nowhere else. |
| Reset token reuse | Single-use, enforced by the database (`used_at IS NULL` in the update's predicate) as well as the row lock. Short-lived, with the boundary pinned exactly. |
| Password storage | Django's `set_password` only. The column holds a salted `pbkdf2_` hash, never the plain text. |
| Session theft | A password change ends the account's other sessions. A stolen session does not survive. |
| PII in logs | No email, password or token reaches a log line. The assertion is on the **serialised** output, so a formatter that redacted the wrong field would fail the test. |
| PII in the throttle store | The per-account key is a SHA-256 digest, never the address — a Redis key would put it in `KEYS` output and in any monitoring dashboard. |
| PII in audit rows | The actor is a UUID. No email in the actor, the label or the details. |
| CSRF | `CSRF_TRUSTED_ORIGINS` is the explicit allowlist. `USE_X_FORWARDED_HOST` stays off — it would make Django trust the attacker-controlled `Host` header. |
| Cookies | `HttpOnly`, `Secure` outside local, `SameSite=Lax`, and a 7-day lifetime that is set at login and not slid on every request. |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| Deterministic throttle tests | The in-memory adapter owns an injectable clock. The window boundary is pinned with no sleeping and no flake. |
| Short-lived tokens | `expires_at` comes from a named constant, so outstanding rows — and the scan that looks for a matching digest — stay small. |
| Index the lookups the app actually makes | `PasswordResetToken` is indexed on `user_id`, which is what "revoke the outstanding ones" and "list a user's resets" need. |
| Digest comparison | `secrets.compare_digest`, so the comparison is constant time and cannot be made slower by a partial match. |
| Session lookup | Django keeps the user id inside an encoded payload rather than a column, so the sessions of one account are found by reading and filtering in Python. An account has a handful of sessions. |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Reset token storage | A stored row with a salted digest | Django's stateless generator is not single-use — it was probed and two consecutive checks both succeeded. A stored row is single-use, revocable, listable, and stores no usable token. |
| Where the dummy hash lives | `apps/identity/services/authenticate.py` | `shared/constants.py` is stdlib-only because `domain` imports it and the `domain-pure` contract forbids Django there. `make_password` needs Django, so the hash cannot live there. **The design doc asked for it there; the code is right and the doc is wrong.** |
| Sign-up outcome shape | A frozen dataclass with no distinguishing field | A field named `created` would be the leak. There is no field to leak. |
| Throttle key for the account | `sha256(normalised_email)` | AD-13 forbids the address in a key the store holds or logs. |
| Throttle normalisation | Inside `account_key`, not at the call site | The caller is what an attacker controls; a caller that varies the casing must not get a fresh bucket. |
| Email uniqueness | A named unique constraint on the normalised column | The database is the arbiter, which is what makes the concurrent sign-up race safe. |
| Audit actor | A UUID, stored by value | AD-3 forbids a cross-schema relation, and AD-13 forbids the address. A UUID satisfies both. |
| Append-only enforcement | Both a Python guard and a database trigger | The trigger binds every role and raw SQL; the guard fails fast with a readable message before any SQL is sent. The two are tested separately, so neither can be removed silently. |
| `SESSION_COOKIE_AGE` | An integer number of seconds | Django's session backend passes the value straight to `timedelta(seconds=...)`. The design doc had it as a `timedelta`, which raised a `TypeError` on every session write. |
| Sign-out signature | `sign_out(*, user, request)` | Matches the design doc, and the audit row's actor must be explicit rather than read off the request. |

## Deviations from Plan

| Deviation | Why |
|-----------|-----|
| `SESSION_COOKIE_AGE` is `int(AUTH_SESSION_LIFETIME.total_seconds())`, not the `timedelta` the plan specified | Django's session backend does `timedelta(seconds=expiry)`. A `timedelta` raised a `TypeError` on every session write — 35 test errors. The plan was wrong; the code is right. |
| The reset token is consumed with a conditional update, not a plain `save()` | The plan's `save()` was single-use only in sequence. Under concurrency, two attempts could both consume the token. The database now arbitrates. |
| The token lookup uses `select_for_update()` | The plan had no lock. This was found by the code review, not by the plan. |
| `reset_password` takes `keep_session_key` | The plan's signature ended *every* session, including the one the reset was made from. The design doc (D12) says the current session is rotated, not deleted. |
| `sign_out` takes the user explicitly | The plan's `sign_out(request)` could not produce an audit row with a known actor. The design doc's signature was `sign_out(*, user)`. |
| Sign-in writes an audit row | The plan's test table did not include it, but the design doc (D14) requires it. The plan was incomplete. |
| `DUMMY_PASSWORD_HASH` is not in `shared/constants.py` | The plan followed the design doc here; both were wrong. `shared/constants.py` is stdlib-only. |
| The migration is named `0002_identityauditentry_passwordresettoken_and_more.py` | Django's generated name. The plan suggested `0002_email_login_reset_token.py`. |
| `adapters.throttle` was added to three existing SDK contracts | It was outside every contract's source list, so its Redis import was unconstrained. A new `redis-sdk` contract was added too. |
| The `username` column drop required rewiring 11 test files | The plan anticipated the column's removal but not the blast radius on existing tests: 76 failures and 56 errors before the rewire. |

## Dependencies Added

**None.** No new package was added to `pyproject.toml`, `package.json` or the lockfiles.
The throttle uses the Redis client already in the stack; the in-memory fake needs nothing.

## How to Verify

1. **The identity suite**

   ```bash
   cd backend && .venv/bin/python -m pytest tests/identity/ -q
   ```

   Expected: **109 passed**.

2. **The whole backend suite, with the coverage gate**

   ```bash
   cd backend && .venv/bin/python -m pytest --cov --cov-report=term -q
   cd backend && .venv/bin/python -m coverage report --include='domain/*' --fail-under=100
   ```

   Expected: **2202 passed, 0 failed**; total coverage **98.77%** (gate 80%); `domain/` at
   **100%**.

3. **The architecture contracts**

   ```bash
   make lint-imports
   ```

   Expected: **14 kept, 0 broken** — including "Only adapters.throttle and config.health
   talk to Redis".

4. **Lint, format and Django's own checks**

   ```bash
   cd backend && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
   cd backend && .venv/bin/python manage.py check
   cd backend && .venv/bin/python manage.py makemigrations --check --dry-run
   ```

   Expected: all checks pass; **no changes detected** for the migration check.

5. **That the security properties are genuinely enforced**

   The point of the test suite is that it *cannot* pass while a property is broken. To see
   this, revert one fix in the working tree and re-run its test:

   ```bash
   # Remove the row lock from apps/identity/services/password_reset.py and re-run:
   cd backend && .venv/bin/python -m pytest tests/identity/test_password_reset_concurrency.py -q
   ```

   Expected: **FAIL** with `expected exactly one success, got ['ok', 'ok']` — without the
   lock, the token is usable twice. Restore the file and the test passes.

   The same holds for the sign-in audit row, the narrowed sign-up `IntegrityError` catch,
   and the kept session.

## Test Coverage

- Tests added: **109** in `tests/identity/` (plus 1 in `tests/architecture/`), on top of the
  2093 that already existed
- Coverage: **98.77%** overall; **100%** for `domain/`
- Status: **passing** — 2202 passed, 0 failed

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated — the design-doc amendment (`DUMMY_PASSWORD_HASH`'s location) is
      recorded in the review report
- [x] Developer notes captured

## Developer Notes

**`apps.identity.services.sign_up` as a package attribute is the *function*, not the
module.** The package's `__init__` imports the function under the same name, so
`apps.identity.services.sign_up` resolves to the function. Only `sys.modules` holds the
module object. The `patch_module_attribute` helper in `tests/identity/conftest.py` exists
for exactly this.

**`password` is the model's own column, so it cannot be a factory kwarg.** factory_boy
would treat it as a field value and write the raw text to the column. The public spelling
is `plain_password=`, and the factory writes the hash through `create_user`. Also note
factory_boy 3.3.3 has no `factory.Exclude`.

**`Manager.db` is read-only.** Calling `.using()` on a manager raises `AttributeError:
property 'db' of 'UserManager' object has no setter`. Drop the `.using()` and let the
router pick the alias.

**`pytest-django` forces `DEBUG = False` during tests**, whatever the developer's `.env`
says. Any setting computed from `not DEBUG` at import time is then stale — which is why
`config/settings_test.py` pins `DEBUG = False` and recomputes `SESSION_COOKIE_SECURE`
rather than the assertion being weakened.

**pytest-django wraps tests in a transaction**, so `connections[PERSONAL].in_atomic_block`
is `True` and the `write_audit` guard cannot be tested. Use
`@pytest.mark.django_db(databases=[PERSONAL], transaction=True)` for that.

**The ORM append-only guard fires before the database trigger.** `AppendOnlyModel.save`
raises `AppendOnlyViolation` before any SQL is sent, so the ORM path never produces an
`IntegrityError`. Test the two layers separately, with raw SQL for the trigger — the
pattern is in `tests/ingestion/test_triggers.py`.

**`SessionStore()` mints its own session key.** A test that creates a `Session` row and
then signs out through a separate store addresses two different sessions.

**A Django `Meta.base_manager_name` matters.** `Meta.base_manager_name = "objects"` makes
related-object paths use the guarded `QuerySet`, so the append-only rules apply there too.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-020*

---

# Walkthrough: Calendar Connection Model (AD-18, FR-50)

*Work item 2 of 13 in `run-eventpulse24-020`.*

## The Problem

A calendar subscription address **is** a credential. Google classifies its secret ICS
address as a secret and offers a reset for it. Anyone who can read the `personal` schema
can therefore impersonate the user against their provider until the address is reset.

So the address cannot be stored in the clear, cannot be logged, cannot appear in an audit
row, cannot reach the admin, and cannot be dumped by `dumpdata`. And when the user
disconnects, it has to be *destroyed* — not merely forgotten.

## The Shape of the Solution

Three modules, each with one job, in strict dependency order:

```
shared/credential_key.py      the key's FORMAT   (stdlib only — no cipher)
        ↓
apps/personalization/credentials.py   the CIPHER      (AES-256-GCM, keyed HMAC)
        ↓
apps/personalization/fields.py        the FIELD       (encrypt on write, decrypt on read)
```

The split is the whole design. `config` must validate the key at startup (D5), but the
settings layer must not be able to read a credential. So the key's *shape* lives in a
stdlib-only module, and the *cipher* lives in the app that owns the data.

### The envelope

```
EPENC1.<key_id>.<nonce>.<ciphertext>
```

- **`EPENC1`** — the format version. A different format gets a different prefix, so
  rotation is a data operation rather than a schema change.
- **`<key_id>`** — which key wrote this row. A row encrypted with a retired key is
  identifiable *without decrypting it*.
- **`<nonce>`** — 12 bytes from the OS CSPRNG, never derived from the message. A reused
  nonce under one key leaks the XOR of two plaintexts.
- **`<ciphertext>`** — base64url, including GCM's 16-byte tag, so a tampered envelope
  fails to decrypt rather than decrypting to something else.

The **key id** is what makes rotation possible. The **nonce** is what stops two
identical addresses from producing identical ciphertext.

### The fingerprint

The uniqueness constraint ("one calendar per user") needs a column that identifies the
calendar. It cannot be the address — the address is encrypted, and an encrypted column
cannot be indexed for equality. So there is a **keyed fingerprint**: HMAC-SHA256 of the
normalised address, under the application key.

*Keyed*, not a plain hash. A plain SHA-256 is deterministic, so an attacker holding the
database could confirm a guessed address by comparing digests. With an HMAC, nobody
without the key can compute the expected digest for any candidate — the column reveals
nothing beyond how many calendars are connected.

*Normalised*, but only partly: the scheme and host are lowercased, while the **path is
left exactly as typed**. A provider's secret path segment is case-sensitive, and
lowercasing it would name a *different* address — so two different calendars would
collide on one fingerprint.

### The field, and why it is a field

`EncryptedTextField` is a `TextField` whose **stored** value is ciphertext. Every write
path encrypts (`get_prep_value`), every read path decrypts (`from_db_value`), and
`value_to_string` serialises the ciphertext.

A field rather than explicit `encrypt()` calls in the service layer, because with a
field, encryption is enforced at **one** place. A service, an admin, a management
command, a test factory and a future script are all covered by construction. With
explicit calls, encryption is a convention that a new code path can forget — and the
failure mode is a plaintext credential in a database column.

Three details that are easy to get wrong:

- **`NULL` is the cleared state**, not `''`. A disconnect sets the column to `NULL`,
  which is unambiguous in a way an empty string is not.
- **An already-encrypted value is stored as it is.** Without this, a `loaddata` fixture
  or a copied row becomes ciphertext-of-ciphertext, and reading it back decrypts *once*
  and hands the caller an `EPENC1.…` string where the address should be: silently wrong,
  and visible only at fetch time.
- **The admin *excludes* the credential, not makes it readonly.** A readonly field is
  still rendered into the page, which would put the ciphertext in the operator's browser.
  Excluded means it never leaves the server.

### The commands

`connect`, `disconnect`, `purge`, `reveal` — the only things that change a connection
(AD-16). Each takes an explicit `Actor` and an explicit `now`, opens one
`transaction.atomic(using=PERSONAL)`, and writes its audit row **inside** it.

**`connect` orders its three refusals by specificity**, and the order is the point:

1. **Already connected?** → "already connected". The cap counts *distinct* calendars,
   and this one is already counted, so reporting a plan limit sends the user to the
   wrong screen.
2. **Waiting to reconnect?** → reuse that row. It is matched by **status**, not by
   fingerprint: the provider revoked the old secret, so the address the user pastes now
   is a *new* one, and the row waiting for it is the one to reuse. Matching by
   fingerprint would create a second row and consume a second slot.
3. **Only now**, the cap — and a `needs_reconnect` row still occupies its slot, because
   the user has not given it up.

**`disconnect` destroys the credential first**, in the same transaction, and purges the
events after. The order matters and it is the safe one: the user's revocation never
depends on a purge job succeeding. If the purge fails, the secret is already gone. The
row is **not** deleted — it becomes `disconnected` with a `NULL` credential, and the
retention sweep removes it later (AD-15).

**`reveal` is the only function that returns the plaintext**, and it returns it wrapped
in `ports.calendar.Credential`, whose `repr` and `str` are `Credential('[redacted]')`.
A cleared credential is refused, and so is one that cannot be decrypted — a wrong key is
a *fault*, not an absence, and the two must not look alike.

## The Defects the Tests Found

Every one of these was found by a test, not by inspection, and each was verified
load-bearing by reverting it and watching the suite go red.

| Defect | What would have happened |
|--------|--------------------------|
| **The cap was checked before the duplicate** | Connecting a calendar the user already had said "plan limit" — pointing at the wrong screen. |
| **Python's base64 silently discards stray characters** | A key with one `$` in it decoded to *different* bytes, passed the length check, and was accepted. The key in use would not be the key the operator wrote. |
| **`decrypt` leaked `ValueError` and `UnicodeDecodeError`** | A corrupt row surfaced as an unhandled 500 instead of a credential fault, breaking the module's one-error promise. |
| **`get_prep_value` double-encrypted an envelope** | A `loaddata` fixture read back as an `EPENC1.…` string instead of the address — silently wrong, visible only at fetch time. |

## The Two-Schema Wall

`CalendarConnection` has **no relation fields at all**. The user is held by value
(`user_id`, a plain column), and the connection crosses no schema (AD-3). The import
contracts enforce it: a planted import of the credential module from `shared` or from
another app breaks the `credential-key` contract.

## Where to Look

| What | Where |
|------|-------|
| The key's format | `backend/shared/credential_key.py` |
| The cipher and the fingerprint | `backend/apps/personalization/credentials.py` |
| The encrypted field | `backend/apps/personalization/fields.py` |
| The commands | `backend/apps/personalization/services/calendar_connections.py` |
| The model and its constraints | `backend/apps/personalization/models.py` |
| The cipher's tests | `backend/tests/personalization/test_calendar_credentials.py` |
| The field's tests | `backend/tests/personalization/test_calendar_credential_field.py` |
| The model's tests | `backend/tests/personalization/test_calendar_connection_model.py` |
| The commands' tests | `backend/tests/personalization/test_calendar_connection_commands.py` |

## Carried to the Next Item

- The `ics-calendar-adapter` item needs the fetch path: it will call `reveal_credential`
  and get a `Credential`, then `reveal()` it. That is the **only** place the plaintext
  is allowed to exist outside the model.
- `calendar-sync-and-polling` needs `purge_connection_events`, and the `needs_reconnect`
  status that `connect_calendar` reuses.
- The `calendar-connect-api` item needs the three refusals, in this order:
  `InvalidCalendarCredentialError` (already connected), `CalendarProviderCapReached`
  (plan limit), and the four accepted schemes.

