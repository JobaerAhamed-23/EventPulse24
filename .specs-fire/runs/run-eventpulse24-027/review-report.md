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

---

# Code Review: Real Stripe, and the way subscription state gets back in

*(work item: `billing-adapter-and-webhooks`)*

## Scope

| File | Action |
|---|---|
| `backend/pyproject.toml` / `uv.lock` | modified — `stripe==13.1.0` pinned |
| `ports/billing.py` | modified — `BillingEventKind`, `BillingEvent`, `InvalidWebhookSignature`, `parse_event` |
| `adapters/billing/stripe.py` | created |
| `adapters/billing/fake.py` | modified — `parse_event`, `FAKE_SIGNATURE` |
| `apps/identity/webhooks_api.py` | created |
| `config/{adapters,api,env,settings}.py` | modified |
| `.env`, `.env.example`, `.github/workflows/ci.yml` | modified |
| `tests/adapters/test_billing_stripe.py`, `tests/identity/test_billing_webhooks.py` | created |
| `tests/adapters/test_fakes.py`, `tests/config/test_env.py`, `tests/config/test_databases.py`, `tests/architecture/test_no_direct_writes.py`, `tests/architecture/test_digest_composition_separation.py` | modified |

## Findings

### 1. The adapter could not be built by its own registry — FIXED

**Severity: would have failed at first use.** `StripeBillingAdapter.__init__` took three
required keyword arguments. `ports.registry.get_adapter` ends with `return cast(P, adapter())`
— **no arguments**. Every call through `get_billing_port()` would have raised `TypeError`.

Found by reading the registry before wiring, not by a test — the unit tests constructed the
adapter directly and would have passed indefinitely. `test_the_adapter_is_constructible_with_no_arguments`
now closes that hole.

**Fix:** all arguments optional, resolved from `settings` lazily, matching
`HttpRevalidationAdapter` and `RedisThrottleAdapter`. The SDK client is a `cached_property`
so importing the module does not require a key — otherwise collecting the test suite would.

### 2. A mapping function that nothing called — FIXED

`mapped_status()` translated Stripe's nine statuses onto this product's four. No code path
reached it: `_subscription` set `raw_status` to Stripe's own string, and the receiver read
that field as though it had already been mapped. A `customer.subscription.updated` carrying
`unpaid` would have hit the receiver's `except ValueError` fallback instead of mapping to
`past_due` — right answer, wrong road, and silently wrong for any status where the fallback
and the mapping disagree.

**Fix:** `BillingEvent` carries two fields with distinct jobs — `status` (ours, acted on) and
`raw_status` (the provider's, logged only). Both docstrings say which is which, because the
confusion is the whole reason the pair exists.
`test_the_receiver_reads_the_mapped_status_not_the_providers_own` fails if they are swapped.

### 3. My error body disclosed more than the project's — FIXED

The first version returned `{"code": "invalid_signature", "message": "Invalid signature."}`,
which tells anyone probing the endpoint exactly which check rejected them.

`config/errors.py` already had a better answer, under a comment that states the policy:
*"Framework HttpErrors get a stable code and a calm message; their own text is not shown."*
A 400 becomes `bad_request` / *"That request couldn't be read."*

**Fix:** `raise HttpError(400, ...) from None`. The response no longer reveals that signature
verification is what failed, the `from None` keeps the provider's message out of any
traceback or error reporter, and the deprecated tuple-return warnings (21 of them, which no
other endpoint in the codebase produces) are gone.

### 4. Two AD-5 guards did not know about the new surface — FIXED

`test_no_direct_writes` and `test_digest_composition_separation` each hold an explicit list of
request modules. The former is blunt about the stakes: *"a surface file that is missing from
this list is **exempt from AD-5**, and nothing else would catch it."*

`apps/identity/webhooks_api.py` is registered in both, with a note that the caller being a
payment provider changes nothing about who may write.

### 5. Pre-existing: CI could not boot Django — FIXED, after being verified

`ci.yml`'s env block was two settings short of what `config.env` requires
(`calendar_credential_key`, `revalidation_secret`), independent of this work. Verified by
reconstructing CI's exact environment rather than by reading the file. All four required
settings are now present and the check was re-run against the real `ci.yml`.

Fixed at the user's explicit instruction, having first been reported rather than folded in.

## Checked and found clean

- **No SDK import anywhere outside `adapters.billing`.** The `stripe-sdk` contract enforces
  it; `lint-imports` reports 19 kept. Verified that `adapters.billing → stripe → requests`
  does not break `http-client`, whose `allow_indirect_imports = true` permits the chain —
  probed with a planted import, not assumed.
- **No provider vocabulary in `apps`.** The receiver matches on `BillingEventKind`. The
  strings `customer.subscription.deleted` and friends appear only in `adapters/billing/stripe.py`.
- **Raw bytes reach verification unparsed**, pinned by a test where re-serialised JSON fails.
- **No Stripe object is logged.** The endpoint logs a kind slug, an outcome slug and nothing
  else — a Stripe object can carry an email, a name and a card's last four digits.
- **No secret in source control.** Both keys are required settings with no default;
  `.env.example` and `ci.yml` carry placeholders of the right shape. The redaction allowlist
  is deny-by-default and its scrubber already matches `sk_test`, `sk_live` and `whsec`.
- **The webhook grants nothing by itself that the commands would not.** All three dispatch
  paths go through item 1's audited commands; there is no direct write to `Subscription` in
  this item.
- **`makemigrations --check --dry-run`**: no changes detected — the new code adds no model.

## Not changed, and why

- **No idempotency table.** The design rejected it and nothing built here changed that:
  replay and ordering are both covered by item 1's row guards, now asserted through the
  endpoint too.
- **No reconciliation job.** A safety net for webhooks Stripe never delivers is a real
  concern and a separate item; inventing it here would be scope the design explicitly
  excluded.
- **`ADAPTER_MODE=real` still does not boot.** Deliberate, asserted, and documented in
  `config/adapters.py`.

## Result

**5 findings: all 5 fixed.** One of them (the registry constructor) would have failed the
first time anything used the adapter through its port, and no test written for this item
would have caught it.
