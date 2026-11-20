---
run: run-eventpulse24-054
work_item: account-deletion-confirmation-email
intent: account-profile-expansion
reviewed_at: 2026-11-20
status: complete
---

# Code Review: The Mail That Says Your Account Is Going Away — and How to Stop It

## Files Reviewed

| File | Status |
|---|---|
| `backend/apps/identity/models.py` | modified |
| `backend/apps/identity/services/deletion.py` | modified |
| `backend/apps/identity/services/emails.py` | modified |
| `backend/apps/identity/migrations/0009_deletionrequest_cancel_token.py` | created |
| `backend/apps/identity/templates/identity/account_deletion.txt` | created |
| `backend/tests/identity/conftest.py` | modified |
| `backend/tests/identity/test_account_deletion.py` | modified |
| `backend/tests/identity/test_account_deletion_mails.py` | created |
| `backend/tests/identity/test_account_deletion_token_concurrency.py` | created |

## Summary

| Category | Auto-fixed | Suggested | Skipped |
|----------|-----------|-----------|---------|
| Code quality | 3 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 0 | 0 |
| Testing | 1 | 0 | 0 |
| **Total** | **4** | **0** | **0** |

**No finding required confirmation.** Every change was mechanical, and the tests were
re-run after each batch.

## Auto-Fixed

| # | Finding | File | Change |
|---|---|---|---|
| 1 | `datetime.timezone.utc` should be the `datetime.UTC` alias (ruff `UP017`) | `tests/identity/test_account_deletion_mails.py:31` | `tzinfo=UTC`, and the import updated |
| 2 | Three import-order and unused-import findings (ruff `I`, `F401`) | `tests/identity/`, `apps/identity/services/` | Re-sorted; the unused imports dropped |
| 3 | Django generates migrations with single quotes; every other migration in the repo is ruff-formatted with double quotes | `migrations/0009_…py` | Reformatted, so the file matches its nine siblings rather than being the odd one out |
| 4 | Two function signatures wrapped where ruff would keep them on one line | `tests/identity/test_account_deletion.py` | Reformatted |

**Tests re-run after the auto-fixes:** 1703 passed (identity + architecture + contract),
and the full suite at 7632 passed.

## Findings Reviewed and Accepted as Correct

These were found by reading the diff and are **not** defects — they are recorded because
a reviewer who did not know the reasoning would reasonably ask about them.

### 1. The candidate scan in the token spend is O(n) over pending deletions

`cancel_account_deletion_with_token` walks every pending `DeletionRequest` and compares
the digest against each row's own salt.

**This is the same shape as the shared `token_service.find_outstanding`**, which does
exactly this for reset and email-change tokens. The digest depends on the row's own
salt, so there is no index that can answer "which row is this token?" without either
storing the raw token (which AD-18 forbids) or giving every row a common salt (which
would make the digests attackable with precomputed digests of the token space).

**The pending set is small** — one row per account that has asked to be deleted — and
the shared scan already established the pattern. Not changed.

### 2. `select_for_update()` locks rows that do not match the token

The lock is taken over every candidate row, not just the matching one, because the
matching row is not known until the digests have been compared.

**The worker does not contend with this.** `due_deletion_requests` is a plain MVCC
read with no `select_for_update()`, so it does not block on these locks and does not
block them. Not changed.

**The lock is load-bearing, and the mutation probe proves it.** Removing it makes two
concurrent attempts at the same token both succeed — see the probe in the test report.

### 3. The token's lifetime is longer than any other token in the project

A reset token lives 30 minutes; this one lives the whole grace period.

**This is the decision the work item's checkpoint asked to settle**, and the reasoning
is recorded in `design-deletion-cancel-token.md` and in
`models.DeletionRequest`'s docstring. The short version: **a token that can only
prevent destruction is a categorically weaker bearer than one that grants access.** A
reset token spends into full account access; this one spends into "the account was not
destroyed". Its worst outcome is that the account survives.

### 4. The address is not captured onto the row

`DeletionRequest` holds no email address, so the "your account has been destroyed" mail
(message B) still cannot be sent.

**That is deliberate and is out of this item's scope** — the work item's own scope note
records it. The model's docstring says so, so a later reader does not mistake the
absence for an oversight. Not changed.

### 5. The API layer was not given a token-consuming endpoint

`cancel_account_deletion_with_token` is a command with no HTTP surface yet.

**That surface belongs to `account-deletion-cancel-surface`**, the sibling work item
that owns the read and the action. This item ships the command that makes the mail's
promise true, and the route the link names (`/cancel-account-deletion?token=…`) is
recorded in the design doc so the next item can be written against it. Not changed.

## Security Review

| Check | Result |
|---|---|
| Raw token at rest | **No** — the row holds `sha256(salt + token)` and the salt. The raw token is in the mail body and nowhere else |
| Token in a log line | **No** — the failure path logs the exception type only. `test_the_send_failure_log_carries_no_address` asserts it |
| Token in an audit detail | **No** — the audit details are `{}`. `test_the_audit_rows_carry_no_token` asserts it |
| Address in a log line | **No** — same test |
| Address in an audit detail | **No** — pre-existing test `test_the_audit_rows_carry_no_personal_data` still passes |
| Address in the idempotency key | **No** — the key is `account_deletion:<row pk>`. Asserted |
| Logger allowlist widened | **No** — `logger.exception` on the module's own logger, which is already allowed |
| Constant-time comparison | **Yes** — `secrets.compare_digest`, the same primitive `find_outstanding` uses |
| Token replayable | **No** — spending the token deletes the row the token lived on. Asserted sequentially *and* under concurrency |
| Timing side-channel on "no such token" | **No** — an unknown token and a wrong token take the same path and return the same answer |
| Direct writes in the API layer | **No** — the send is in the command. `tests/architecture/test_no_direct_writes.py` is green |
| Transaction boundary | **Correct** — `transaction.atomic(using=PERSONAL)` (AD-3), and the mail is sent after the commit |
| Idempotency | **Yes** — the key is derived from the request row, and a second request sends nothing (AD-7) |
| Stream | **Transactional** — one-time answer to something the user did, no unsubscribe URL needed (AD-20) |

## Architecture Review

| Check | Result |
|---|---|
| AD-2 — app ownership | ✅ The model, the command and the mail are all in `identity`, which owns the account |
| AD-3 — schema and `using=PERSONAL` | ✅ Every query and every `atomic` block names `PERSONAL` explicitly |
| AD-5 — named command owns the write | ✅ The token is minted and the row written in `request_account_deletion`; the API layer calls it and writes nothing |
| AD-13 — no PII in logs or audit | ✅ See the security review |
| AD-15 — retention category | ✅ `DeletionRequest` already declares `RetentionCategory.ACCOUNT_IDENTITY`; no new model was added |
| AD-18 — credentials encrypted at rest | ✅ The token is a salted digest |
| AD-19 — OpenAPI is the contract | ✅ The schema is byte-identical — this item changed no endpoint and no field |
| AD-20 — explicit stream | ✅ `account_deletion_stream()` returns `Stream.TRANSACTIONAL`; `EmailPort.send` has no default |
| OQ-8 — user held by value | ✅ The token lives on the account's own `DeletionRequest` row; there is no relation to `User` |

## Testing Review

| Check | Result |
|---|---|
| Tests can fail | ✅ **Four mutation probes, all detected** — see the test report |
| Naming convention `test_<unit>_<condition>_<expected>` | ✅ |
| Fakes at the port boundary | ✅ The `InMemoryEmailAdapter` is a port fake; no ORM is mocked |
| No new model without a retention category | ✅ No new model |
| Coverage | ✅ 95% on the changed modules; every line this item added is covered |
| Concurrency covered | ✅ The single-use property is asserted **under concurrency**, not only in sequence |
| Edge cases | ✅ Wrong token, spent token, unknown token, second request, rolled-back request, mail failure, one token one account |

## Conclusion

**No changes require confirmation.** The four auto-fixes were mechanical, and the tests
were re-run after them and are green.

The item is ready for completion.
