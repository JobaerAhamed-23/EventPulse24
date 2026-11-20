---
run: run-eventpulse24-042
work_item: pending-email-model-and-commands
intent: account-profile-expansion
date: 2026-11-19
---

# Report: Moving the Login

## The gate the plan set, and whether it held

**It held.** The outstanding-token scan was extracted into
`apps/identity/services/tokens.py` **before** the email-change flow was written, and the
password-reset suite passed **23/23 unedited** — `git diff --stat tests/` was empty at
that point. No reset test was touched to accommodate the extraction, which was the
condition for the extraction being correct rather than convenient.

## Tests

| Suite | Result |
|---|---|
| `tests/identity/test_email_change.py` | **20 passed** |
| `tests/architecture/` | 165 write-ownership tests passed, **after declaring the new table's owner** |
| `tests/identity/test_password_reset.py` | 23 passed, **unedited** |
| `ruff check` / `format` | clean |
| `lint-imports` | 20 contracts kept, 0 broken |
| `manage.py check` | no issues (3 silenced) |

## The mutation probes, including the one that found a hole

Six probes were run against the commands. **Five failed the right tests. One did not, and
that was the finding of this run.**

| Mutation | Result |
|---|---|
| A taken address is refused loudly instead of silently | 2 failed |
| The login moves at request time | 5 failed |
| The race is "handled" by something other than the constraint | 2 failed |
| **The conditional-update guard is removed** | **20 passed — no test noticed** |
| Sessions ARE ended (the decision, reversed) | 1 failed |
| The address leaks into the audit details | 1 failed |

### What the fourth probe exposed

`test_a_token_works_once` **passes without the single-use guard.** The scan already
filters `used_at__isnull=True`, so a *sequential* second attempt finds no row and is
refused for an entirely different reason. The guard — the conditional
`UPDATE ... WHERE used_at IS NULL`, which makes the **database** the arbiter rather than
the row lock — exists for two confirmations in flight at once, and no sequential test can
reach it.

So `test_the_database_is_the_arbiter_when_two_confirmations_race` was added. It consumes
the row *after* the scan returns it and *before* the update — the exact interleaving the
guard is for, and the only way to reach it deterministically. **Re-running the fourth
probe now fails 1 test**, where before it failed none.

**This is worth recording as a process point, not just a test.** The suite was 19/19 green
and the gap was invisible until a mutation probe asked the question. A test that cannot
fail is not evidence.

## What the wider suite caught that the item's own tests did not

`tests/architecture/test_write_ownership.py` failed twice on the new table:

```
tables with no owner in TABLE_OWNERS: ['identity_pendingemailchange'].
Every table needs an owner; an unowned table is one nobody is responsible for.
```

**A new table is not finished when it has a migration.** AD-16 requires it to be claimed
in the ownership map, and the map is enforced from two directions — the declared tables
must exist, and every table the tree writes must be claimed. `identity_pendingemailchange`
is `identity`'s, for the same reason the reset token is: it is an unproven claim about the
account's own login, written only by identity's commands, and the app that owns the
credential owns the claim on it.

This is a good failure. It is the kind of omission that is invisible in the item's own
tests, because the item's own tests are about the behaviour and this is about who is
responsible for it.

## Acceptance criteria

| Criterion | State |
|---|---|
| Digest + per-row salt, no token at rest | ✅ asserted |
| Normalised address, like-for-like compare | ✅ |
| Same-address refused | ✅ |
| Taken address refused **without revealing it exists** | ✅ silence, and **no mail owed** |
| New request revokes the outstanding one | ✅ |
| Confirm moves the login in one transaction | ✅ |
| Expired / revoked / used / unknown all refused | ✅ |
| **Race lost at `user_email_uq`, not a pre-check** | ✅ run for real |
| Rate limiting with a test that trips it | ✅ |
| Session consequence implemented and recorded | ✅ **not ended**, with the reasoning in the module docstring |
| Audit rows in the same transaction, no address in details | ✅ |
| `test_no_direct_writes` green | ✅ |
| Every test can fail | ✅ **after the fourth probe forced one more test** |

## Not in this item

No API layer, no mails, no UI. `request_email_change` returns `EmailChangeRequest` — the
raw token and **both** addresses — and sends nothing; `email-change-mails` owns the two
messages, including the warning to the old address that this design leans on as its real
defence against a session-holding attacker.
