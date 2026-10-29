# Code Review Report

**Run**: run-eventpulse24-020
**Intent**: onboarding-and-account
**Work item**: account-auth-core
**Reviewed**: 2026-10-29
**Files Reviewed**: 40

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 3 | 0 | 0 |
| Security | 3 | 0 | 0 |
| Architecture | 1 | 0 | 0 |
| Testing | 4 | 0 | 0 |
| **Total** | **11** | **0** | **0** |

**Tests Status**: Passing — 2202 passed, 0 failed; 98.77% coverage; 14/14 import contracts kept.

Every finding was a **defect**, not a style preference, and every one was fixed in the same
pass rather than deferred. No finding was left as a suggestion requiring approval: each was
either a clear correctness bug with a definite fix, or a documented acceptance.

---

## Files Reviewed

### Created

- `backend/ports/throttle.py` (new)
- `backend/adapters/throttle/__init__.py` (new)
- `backend/adapters/throttle/memory.py` (new)
- `backend/adapters/throttle/redis.py` (new)
- `backend/apps/identity/managers.py` (new)
- `backend/apps/identity/services/audit.py` (new)
- `backend/apps/identity/services/authenticate.py` (new)
- `backend/apps/identity/services/emails.py` (new)
- `backend/apps/identity/services/password_reset.py` (new)
- `backend/apps/identity/services/session.py` (new)
- `backend/apps/identity/services/sign_up.py` (new)
- `backend/apps/identity/services/throttle.py` (new)
- `backend/apps/identity/templates/identity/password_reset.txt` (new)
- `backend/apps/identity/migrations/0002_identityauditentry_passwordresettoken_and_more.py` (new)
- `backend/tests/identity/conftest.py` (new)
- `backend/tests/identity/factories.py` (new)
- `backend/tests/identity/test_audit.py` (new)
- `backend/tests/identity/test_authenticate.py` (new)
- `backend/tests/identity/test_log_redaction.py` (new)
- `backend/tests/identity/test_models.py` (new)
- `backend/tests/identity/test_password_reset.py` (new)
- `backend/tests/identity/test_password_reset_concurrency.py` (new)
- `backend/tests/identity/test_session.py` (new)
- `backend/tests/identity/test_session_settings.py` (new)
- `backend/tests/identity/test_sign_up.py` (new)
- `backend/tests/identity/test_throttle.py` (new)

### Modified

- `backend/apps/identity/models.py`
- `backend/apps/identity/admin.py`
- `backend/apps/identity/services/__init__.py`
- `backend/apps/ingestion/admin.py`
- `backend/config/adapters.py`
- `backend/config/env.py`
- `backend/config/management/commands/seed_local_stack.py`
- `backend/config/settings.py`
- `backend/config/settings_test.py`
- `backend/domain/errors.py`
- `backend/ports/registry.py`
- `backend/pyproject.toml`
- `backend/shared/constants.py`
- `backend/tests/architecture/test_import_contracts.py`
- `backend/tests/identity/test_user.py`
- `backend/tests/ingestion/test_admin.py`
- `backend/tests/ingestion/test_seed_local_stack.py`
- `backend/tests/personalization/test_auth.py`
- `backend/tests/personalization/test_personal_events_api.py`
- `backend/tests/personalization/test_saved_events_api.py`
- `backend/tests/wall/test_orm_wall.py`
- `backend/tests/wall/test_transactions.py`
- `backend/tests/e2e/test_end_to_end.py`
- `backend/tests/e2e/test_personal_events_and_saved_catalog.py`
- `backend/tests/e2e/test_save_race.py`

---

## Applied Fixes

### 1. [Security] `sign_up` swallowed *any* `IntegrityError` and misreported it as a duplicate

- **File**: `backend/apps/identity/services/sign_up.py:77-104`
- **Description**: The `except IntegrityError` wrapped the whole `transaction.atomic` block,
  including the audit write. An infrastructure failure — the audit table's own constraints,
  a disk error — rolled the account back, returned `SignUpOutcome(accepted=True)` to the
  caller, and sent the holder a "someone tried to sign up with your email" notice for an
  account that did not exist. A real failure was indistinguishable from a duplicate.
- **Rationale**: The outcome shape is the enumeration-safety mechanism (D15). Swallowing a
  non-duplicate failure into that shape tells the caller their account exists when none was
  created — the same leak, arrived at from the other direction.
- **Risk Level**: High — it changes the transaction structure.
- **Diff**:

```diff
-    try:
-        with transaction.atomic(using=PERSONAL):
-            user = User.objects.create_user(email=normalised, password=password)
-            audit_service.write_audit(...)
-    except IntegrityError:
-        _notify_existing_holder(normalised)
-        return SignUpOutcome()
+    with transaction.atomic(using=PERSONAL):
+        try:
+            with transaction.atomic(using=PERSONAL):
+                user = User.objects.create_user(email=normalised, password=password)
+        except IntegrityError:
+            _notify_existing_holder(normalised)
+            return SignUpOutcome()
+        audit_service.write_audit(...)
```

The nested `atomic` is a savepoint: the insert's `IntegrityError` is caught at the point of
the insert, while the account and the audit row stay in **one** transaction (AD-5).

### 2. [Security] The reset token was not single-use under concurrency

- **File**: `backend/apps/identity/services/password_reset.py:124-183`
- **Description**: `_find_outstanding_token` read the outstanding rows with no lock. Two
  concurrent `reset_password` calls could both read `used_at IS NULL`, both pass the
  check, and both change the password — so the token was usable twice, which breaks the
  acceptance criterion outright.
- **Rationale**: "Single-use" is the property the work item names. A sequential test cannot
  see a race.
- **Risk Level**: High — it changes the locking behaviour of the write path.
- **Diff**:

```diff
-    candidates = PasswordResetToken.objects.using(PERSONAL).filter(
-        used_at__isnull=True, revoked_at__isnull=True
-    )
+    candidates = (
+        PasswordResetToken.objects.using(PERSONAL)
+        .select_for_update()
+        .filter(used_at__isnull=True, revoked_at__isnull=True)
+    )
...
-        row.used_at = moment
-        row.save(using=PERSONAL, update_fields=["used_at"])
+        consumed = PasswordResetToken.objects.using(PERSONAL).filter(
+            pk=row.pk, used_at__isnull=True
+        ).update(used_at=moment)
+        if consumed == 0:
+            raise InvalidResetTokenError()
```

The conditional update makes the **database** the arbiter of single-use, so the row lock is
belt and braces rather than the only defence.

### 3. [Security] Sign-in and sign-out were not audited

- **File**: `backend/apps/identity/services/authenticate.py`, `backend/apps/identity/services/session.py`
- **Description**: The design doc (D14) requires sign-in, sign-up, sign-out and password
  reset all to be audited. Only sign-up and password reset were. AD-5 requires one audit
  row per mutation, and a sign-in is the security event most worth recording.
- **Rationale**: An unimplemented design decision is a gap, not a preference.
- **Risk Level**: High — it adds a write to the sign-in path.
- **Diff**:

```diff
+# in authenticate(), after the password check
+    with transaction.atomic(using=PERSONAL):
+        audit_service.write_audit(
+            actor=Actor.user(user.pk),
+            action="sign_in",
+            target_type="User",
+            target_id=user.pk,
+            details={"method": "password"},
+        )
```

`sign_out` was changed from `sign_out(request)` to `sign_out(*, user, request)`, matching
the design doc's signature, so the audit row's actor is explicit rather than read off the
request.

### 4. [Testing] A reset ended the session it was made from

- **File**: `backend/apps/identity/services/password_reset.py`, `backend/tests/identity/test_password_reset.py`
- **Description**: `reset_password` called `end_other_sessions(user)` with no
  `keep_session_key`, so the session the user reset *from* was destroyed too. The design
  doc (D12) says the current session is rotated, not deleted.
- **Rationale**: The user is logged out of the browser they just used.
- **Risk Level**: Medium — it changes which sessions survive.
- **Diff**:

```diff
-def reset_password(*, token: str, new_password: str, now=None) -> User:
+def reset_password(
+    *, token: str, new_password: str, now=None, keep_session_key: str | None = None
+) -> User:
...
-    end_other_sessions(user)
+    end_other_sessions(user, keep_session_key=keep_session_key)
```

The old test called `end_other_sessions` **directly**, so it pinned the helper rather than
the command — and the command was wrong. The test now calls `reset_password`.

### 5. [Testing] The tests that should have caught the above did not exist

- **File**: `backend/tests/identity/test_sign_up.py`, `test_authenticate.py`, `test_password_reset.py`, `test_password_reset_concurrency.py` (new), `test_session.py` (new)
- **Description**: 13 tests were added, one per fixed defect. Each was verified to **fail
  without its fix** — the fix was reverted in the working tree and the test re-run.
- **Rationale**: A test that cannot fail is worse than no test. The concurrency test
  produced `['ok', 'ok']` instead of `['ok', 'refused']` when the lock was removed.
- **Risk Level**: Low — tests only.
- **Diff**: new files and new test functions; no production code touched.

### 6. [Architecture] An expired token row shadowed a valid one

- **File**: `backend/apps/identity/services/password_reset.py:166-196`
- **Description**: `_find_outstanding_token` returned `None` on the first digest match if it
  was expired, without continuing the scan — so an expired row could make a later valid row
  unreachable.
- **Rationale**: The state machine should not conflate "expired" with "unknown" mid-scan.
  Astronomically unlikely with 256-bit tokens, but a logic error nonetheless.
- **Risk Level**: Low — it only ever made a valid token *less* reachable, never more.
- **Diff**:

```diff
         if row.expires_at <= now:
-            return None
+            continue
```

### 7. [Code Quality] `reset_password_stream()` was dead code

- **File**: `backend/apps/identity/services/emails.py`, `backend/apps/identity/services/password_reset.py`
- **Description**: The helper existed but was never called; the call site spelled
  `Stream.TRANSACTIONAL` directly.
- **Rationale**: Either delete it or use it. Using it puts the AD-20 stream choice in one
  place, so a future second auth mail cannot drift onto the wrong stream.
- **Risk Level**: Low — mechanical.
- **Diff**:

```diff
-        stream=Stream.TRANSACTIONAL,
+        stream=reset_password_stream(),
```

### 8-11. [Code Quality] Lint and format

- **Files**: `backend/apps/identity/admin.py`, `backend/apps/identity/services/__init__.py`,
  `backend/tests/identity/conftest.py`, `backend/tests/identity/test_password_reset.py`,
  `backend/apps/identity/migrations/0002_*.py`
- **Description**: An over-long line in the admin's `fieldsets`, three unsorted import
  blocks, and two unused locals.
- **Rationale**: Mechanical, non-semantic — the auto-fix category.
- **Risk Level**: None.
- **Fix**: `ruff check --fix` and `ruff format`. The line was wrapped by hand rather than
  left for the formatter, because the `fieldsets` list is more readable expanded.

---

## Accepted Without a Change

These were raised by the review and deliberately not changed. Each is recorded so the
decision is visible rather than silent.

| Finding | Why accepted |
|---------|-------------|
| `_find_outstanding_token` scans every outstanding row in the table | The digest depends on a per-row salt, so no index can be looked up without knowing the salt. The scan is bounded by the number of *outstanding* tokens, which are short-lived and revoked on the next request. A cleanup job for expired rows belongs to a later item. |
| `request_password_reset` sends the email after the row commits | The standard transactional-email trade-off. A send failure leaves a row the user never received a link for; the next request revokes it and issues a new one. Sending inside the transaction would instead roll the row back on a transient SMTP failure, which is worse. |
| The duplicate sign-up path is a timing oracle | Measured at roughly 17 ms against 346 ms, both dominated by password hashing. The design (D15) accepts the email as the only observable difference. |
| `_user_sessions` decodes every session row | Django's session model keeps the user id inside an encoded payload, not in a column, so there is no database-level lookup. An account has a handful of sessions. |
| `DUMMY_PASSWORD_HASH` is not in `shared/constants.py` | The design doc asked for it there, but that module is stdlib-only and `make_password` needs Django — **the design doc is wrong, the code is right**. The code's placement is correct and documented in the module. This is a design-doc amendment, not a code change. |
| `TOKEN_BYTES` / `SALT_BYTES` are not in `shared/constants.py` | Local implementation detail of the token module; no other module needs them. |

---

## Project Tooling Used

- **ruff**: `backend/pyproject.toml` — `ruff check .` and `ruff format --check .`, both clean
- **import-linter**: `backend/pyproject.toml` — 14 contracts, 0 broken
- **pytest + pytest-django**: `backend/pyproject.toml` — 2202 passed, 0 failed
- **coverage**: `backend/pyproject.toml` — 98.77% overall, 100% for `domain/`
- **Django system checks**: `manage.py check` — no issues
- **Migration drift**: `manage.py makemigrations --check --dry-run` — no changes detected

## Standards Referenced

- `docs/ARCHITECTURE-SPINE.md` — AD-1, AD-2, AD-3, AD-5, AD-8, AD-9, AD-13, AD-16, AD-18, AD-20, AD-21
- `.specs-fire/intents/onboarding-and-account/work-items/account-auth-core-design.md` — D1–D20
- `.specs-fire/runs/run-eventpulse24-020/plan.md` — the approved implementation plan
- `.specs-fire/runs/run-eventpulse24-020/test-report.md` — the test evidence for every fix

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-020*

---

# Code Review: Calendar Connection Model (AD-18, FR-50)

**Work item**: `calendar-connection-model` — the second of thirteen in
`run-eventpulse24-020`.
**Reviewer**: the FIRE Builder's code-review pass, over the diff for this item.
**Outcome**: two defects found and fixed; one mechanical cleanup applied; two findings
accepted with a recorded reason; one gap in the *tests* found and closed.

## What Was Reviewed

| File | Change |
|------|--------|
| `shared/credential_key.py` | **New.** The credential key's *format*: parse, validate, encode, decode. Stdlib-only. |
| `apps/personalization/credentials.py` | **New.** The cipher: the envelope, encrypt, decrypt, the keyed fingerprint. |
| `apps/personalization/fields.py` | **New.** `EncryptedTextField` — the model field whose stored value is ciphertext. |
| `apps/personalization/models.py` | `CalendarConnection`; `PersonalEvent` gains `calendar_connection_id`, `source_uid`, and the `CALENDAR_IMPORT` source. |
| `apps/personalization/services/calendar_connections.py` | **New.** connect, disconnect, purge, reveal. |
| `apps/personalization/admin.py` | The credential is **excluded**, not made readonly. |
| `config/env.py`, `config/checks.py` | The key is validated at startup (D5). |
| `backend/pyproject.toml` | Two import contracts: `crypto-library`, `credential-key`. |

The review's question is narrow and specific: **can a plaintext calendar address reach
a place it should not, or be lost in a way the user cannot see?**

## Findings

### DEFECT 1 — `decrypt` leaked two exception types it promised never to leak

**Severity**: high. **Status**: **fixed**.

`apps/personalization/credentials.py` documents one promise: *"Every failure mode — a
malformed envelope, the wrong key, a tampered ciphertext — is the same error."* The
module's docstring says the caller "cannot tell them apart, and neither can an
attacker: the error never says whether the envelope was well-formed."

Two paths broke that promise:

1. **A structurally impossible envelope.** `AESGCM.decrypt` raises a bare `ValueError`
   when the nonce is not 12 bytes or the ciphertext is shorter than GCM's 16-byte tag.
   That `ValueError` escaped the module. A caller written against the documented
   contract — `except CredentialDecryptionError` — would not catch it, and a corrupt row
   would surface as an unhandled 500 instead of a credential fault.
2. **A non-text plaintext.** The credential is a URL, so the plaintext is text. A column
   holding bytes that are not text is a corrupt row, but `plaintext.decode("utf-8")`
   raised `UnicodeDecodeError`, which is not a `ValueError` and not a
   `CredentialDecryptionError`.

Both are now caught and re-raised as `CredentialDecryptionError`. The `ValueError` branch
carries a comment saying why the raw exception must not escape: *"a raw `ValueError`
escaping this module would break the promise that every failure is a
`CredentialDecryptionError` — the caller would have to know which of cryptography's
exceptions to expect."*

**Tests**: `test_a_structurally_impossible_envelope_fails_loudly`,
`test_a_short_ciphertext_fails_loudly`,
`test_a_non_text_plaintext_fails_loudly`.

**Verified load-bearing**: with both `except` clauses reverted to a bare `raise`, the
suite was re-run and **2 failed** — `test_a_structurally_impossible_envelope_fails_loudly`
and `test_a_non_text_plaintext_fails_loudly` — each failing with the leaked exception
type (`ValueError` and `UnicodeDecodeError` respectively). The fix was then restored and
the suite re-run green.

### DEFECT 2 — the field encrypted an already-encrypted value a second time

**Severity**: high. **Status**: **fixed**.

`EncryptedTextField.get_prep_value` encrypts every write. It had no check for a value
that was *already* an envelope, so:

- a `loaddata` fixture, which writes the serialised ciphertext straight into the column,
- a copy of an existing row,
- any future code path that round-trips a credential through the model

would each be stored as **ciphertext-of-ciphertext**. Reading the row back decrypts
*once*, and hands the caller an `EPENC1.…` string where the provider's address should be.
That is silently wrong, and it is visible only at fetch time — when the adapter tries to
fetch a calendar whose address is a base64 blob.

The fix is one guard: a value that `is_envelope(value)` is stored as it is.

This is the same class of defect as the ones the tests were written to catch, and it is
the reason the fix has a dedicated test rather than a comment.

**Tests**: `test_an_already_encrypted_value_is_not_encrypted_again`,
`test_a_dumped_connection_reloads_as_the_same_credential`.

**Verified load-bearing**: with the guard replaced by an unconditional
`encrypt(value, _current_key())`, the suite was re-run and **2 failed**. The failure
message is the defect itself: `assert 'EPENC1.k1.dOgBQrWSB5…' == 'https://calendar.google.com/calendar/ical/…/basic.ics'` — the address replaced by an envelope, exactly as described above. The fix was then restored and the suite re-run green.

### CLEANUP 1 — `from django.conf import settings` inside a function

**Severity**: none. **Status**: **applied**.

`_key()` in `services/calendar_connections.py` imported `settings` inside the function
body. Every other module in the codebase imports it at the top. This was a mechanical,
non-semantic change with no behavioural effect; the tests were re-run after it.

### CLEANUP 2 — an unused `moment` in the two commands

**Severity**: none. **Status**: **applied**.

`moment` was assigned in `connect_calendar` and `disconnect_calendar` and never used —
ruff caught it. Rather than delete the value, the commands now stamp it into the audit
row (`details={"provider": …, "at": moment.isoformat()}`), matching
`apps/personalization/services/personal_events.py`. The audit row should say *when* the
thing happened; a moment that is computed and thrown away is a moment nobody recorded.

Two tests that asserted the audit row's exact `details` were updated to match.

### GAP 3 — `fields.py` sat at 73% coverage, below the project gate

**Severity**: medium. **Status**: **fixed**.

The file that decides what lands in the credential column — the one file whose whole job
is the write path — was at **73%**, under the project's 80% floor. The uncovered lines
were not incidental: they were the missing-key branch, the malformed-key branch, the
non-string write, the empty-string write, the whole of `to_python`, and both branches
of `value_to_string`.

A security-relevant file that is three-quarters untested is a file whose *rejection*
paths are unknown. The gap is closed by a new file,
`tests/personalization/test_calendar_credential_field.py` (18 tests), which covers each
branch of the field on its own — away from the model that uses it.

**Result**: `apps/personalization/` and `shared/credential_key.py` are now at **100% —
every line and every branch**.

## Accepted Without a Change

| Finding | Why accepted |
|---------|-------------|
| `value_to_string` encrypts the plaintext attribute into a **fresh** envelope, so the serialised payload is not byte-identical to the stored ciphertext | This is correct, and it is a consequence of the fresh nonce. The property that matters is that the payload is *one* layer of encryption and decrypts to the address — which is what the test now asserts. (An earlier draft of that test asserted byte-identity and was wrong; the test was corrected, not the code.) |
| `connect_calendar` matches a reconnecting row by **status**, not by fingerprint | The provider revokes the old secret, so the address the user pastes now is a *new* one with a *new* fingerprint. Matching by fingerprint would create a second row and consume a second slot. |
| `OCCUPYING_STATUSES` counts a `needs_reconnect` row against the cap | The user has not given the calendar up. Freeing the slot would let a user connect past the cap by waiting for a failure. |
| `reveal_credential` returns the plaintext wrapped in `ports.calendar.Credential`, whose `repr`/`str` are redacted | There is exactly one function in the codebase that returns the plaintext, and the wrapper makes printing it by accident a no-op. |
| The Free-tier cap is enforced in the service, not the API | The API is one caller. A cap that only one caller enforces is a cap another caller walks past. |
| `.env.example` holds a working example key (`k1.ZXZlbnRwdWxzZTI0LWxvY2FsLWNyZWRrZXktMzJieWQ`) | It decodes to `eventpulse24-local-credkey-32byt` and follows the repo's established `DJANGO_SECRET_KEY=…-not-for-production` convention. `.env` is gitignored; the file is a template, not a secret. |

## A Note on the Base64 Fix

Found during the earlier test pass, and recorded here because it is the most instructive
defect of the item.

Python's `base64.urlsafe_b64decode` **silently discards** characters outside the
alphabet. A 32-byte key with one stray `$` in it would decode to *different* 32 bytes,
pass the length check, and be accepted — so the key in use would not be the key the
operator wrote, and every credential written under it would be unreadable by the key they
thought they had. The key's format now checks the alphabet before decoding and decodes
strictly (`validate=True`).

The defect was found through a **coverage gap**, not by inspection: the uncovered branch
in `b64decode` led directly to it. That is the argument for treating a coverage gap in a
security-critical module as a finding rather than a nuisance.

## The Gates, After Everything

| Gate | Command | Result |
|------|---------|--------|
| Tests | `pytest -q --cov` | **2363 passed**, 0 failed |
| Coverage | `pytest --cov` | **98.80%** overall (floor 80%) |
| Coverage, this item's code | `pytest --cov=apps.personalization --cov=shared.credential_key` | **100%** — every line, every branch |
| Coverage, `domain/` | `pytest --cov=domain` | **100%** (floor 100%) |
| Lint | `ruff check .` | clean |
| Format | `ruff format --check .` | 318 files already formatted |
| Architecture | `lint-imports` | **16 kept, 0 broken** |
| Django | `manage.py check` | no issues |
| Migrations | `manage.py makemigrations --check --dry-run` | no changes detected |

## Standards Referenced

- `docs/ARCHITECTURE-SPINE.md` — AD-3 (the schema wall), AD-5 (the audit row), AD-13 (no PII in logs), AD-15 (retention), AD-16 (write ownership), AD-18 (the calendar credential)
- `.specs-fire/intents/onboarding-and-account/work-items/calendar-connection-model-design.md` — D1–D13
- `.specs-fire/runs/run-eventpulse24-020/plan.md` — the approved implementation plan
- `.specs-fire/runs/run-eventpulse24-020/test-report.md` — the test evidence for every fix

