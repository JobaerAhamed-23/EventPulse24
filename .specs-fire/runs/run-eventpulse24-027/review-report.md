---
run: run-eventpulse24-027
work_item: subscription-model-and-entitlement
intent: pro-tier-and-monetization
date: 2026-11-11
---

# Code Review: Something to be Pro with — the Subscription entity and the one entitlement read

## Scope

| File | Action |
|---|---|
| `apps/identity/models.py` | modified — `SubscriptionStatus`, `LIVE_SUBSCRIPTION_STATUSES`, `Subscription` |
| `apps/identity/services/entitlement.py` | created |
| `apps/identity/services/subscriptions.py` | created |
| `apps/identity/services/__init__.py` | modified — published the four new names |
| `apps/identity/migrations/0003_subscription.py` | created |
| `tests/identity/factories.py` | modified — `SubscriptionFactory` |
| `tests/identity/test_entitlement.py` | created |
| `tests/identity/test_subscription_model.py` | created |
| `tests/identity/test_subscription_commands.py` | created |
| `tests/architecture/test_import_contracts.py` | modified — 2 planted violations, 1 allowed import |
| `tests/architecture/test_write_ownership.py` | modified — registered the table's owner |

## Findings

### 1. Caught `IntegrityError` inside `atomic` with no savepoint — FIXED

**Severity: latent defect.** `record_subscription_started` caught `IntegrityError` directly
inside its only `transaction.atomic(using=PERSONAL)` block. Django marks the connection for
rollback when a database error fires inside an atomic block, and every subsequent query in
that transaction raises `TransactionManagementError`.

**Probed before reporting**, rather than asserted from memory. A throwaway test reproduced
the exact shape — catch the error, then run one more query:

```
django.db.transaction.TransactionManagementError: An error occurred in the current
transaction. You can't execute queries until the end of the 'atomic' block.
```

The code did **not** crash in practice, because it returns immediately after the catch and
Django rolls the outer block back cleanly on exit. But it was one added line from breaking,
and it contradicted the pattern this codebase already documents at `sign_up.py:95`:

> *"The insert gets its own nested `atomic` block — a savepoint — so its `IntegrityError`
> can be caught here, at the point of the insert, while the outer block still holds the
> account and the audit row in one transaction."*

**Fix:** the insert is wrapped in a nested `atomic` (a savepoint), matching `sign_up`.

### 2. The race path had no test at all — FIXED

The `except IntegrityError` branch was unreachable by every test written for it. The sequential
replay test (`test_a_replayed_checkout_does_not_create_a_second_subscription`) returns at the
earlier `existing is not None` check and never reaches the insert, so the branch that actually
resolves a concurrent race was never executed.

**Fix:** the pre-check was extracted to a module-level `_live_subscription_for(user_id)`, so a
test can make it blind — which is precisely what the losing transaction observes, its SELECT
having run before the winner's INSERT committed. `test_the_losing_side_of_a_concurrent_checkout_is_a_clean_no_op`
now covers it, deterministically and without threads.

**Verified it can fail:** changing `except IntegrityError` to `except ValueError` fails the
test with the raw `IntegrityError`.

### 3. The new race test does not pin the savepoint — DOCUMENTED, not papered over

Mutation-testing the fix showed the new test passes **with and without** the savepoint,
because the command returns immediately after the catch so nothing follows to trip on the
broken transaction.

The honest conclusion is that the savepoint is **defensive hardening, not currently
load-bearing**, and the test docstring now says exactly that instead of implying coverage it
does not provide. An earlier draft of that docstring claimed the test exercised the savepoint;
that claim was wrong and was removed.

### 4. `select_for_update()` returning `None` locks nothing — DOCUMENTED

`_live_subscription_for` uses `select_for_update()`, which locks the rows it *returns*. When
there is no live subscription it returns `None` and has locked nothing, so two concurrent
commands can both reach the insert. That is correct — the partial unique constraint is what
resolves the race — but the call reads as though it prevents the race, which it does not.

Not a defect; the function's docstring now states what the lock does and does not do, so the
next reader is not misled into deleting the `IntegrityError` catch as redundant.

### 5. Unregistered table — FIXED (found by the suite, not by review)

`identity_subscription` was added without an entry in `TABLE_OWNERS`, failing two
`test_write_ownership` tests. Registered to `identity`. Recorded in the test report.

## Checked and found clean

- **No secret or identifying reference reaches a log sink.** `ALLOWED_FIELDS` in
  `adapters/logging/redaction.py` is deny-by-default and does not name `stripe_customer_ref`,
  so it is redacted without an edit. Adding it to the allowlist would have been the wrong fix.
- **No customer reference in audit `details`** — asserted by
  `test_no_customer_reference_reaches_an_audit_row`. Audit rows live seven years.
- **No email anywhere in a subscription or audit row** (AD-13).
- **The status→entitlement mapping has exactly one home.** No caller sees a status.
- **No delete path**, asserted by a test rather than by inspection.
- **`update_fields` includes `updated_at`**, so `auto_now` still fires on partial saves.
- **19/19 import contracts kept**, including the two new planted violations proving
  `models-identity` blocks the alternative seam.
- **Commands take an explicit `Actor`**, never a `request`, per the spine.

## Not changed, and why

- **No cache behind `is_pro`.** The design decided against one; nothing measured here
  contradicts that. Item 4 (`free-tier-caps-read-entitlement`) carries the AC to measure on
  the hot save path.
- **The 16 pre-existing suite failures.** Out of scope for this item, verified not caused by
  it, and recommended to the Planner as a defect work item. See the test report.

## Result

**5 findings: 3 fixed, 2 documented.** Suite green for everything this item touches —
`tests/identity/` and `tests/architecture/` together: **1128 passed**.
