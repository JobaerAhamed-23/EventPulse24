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

---

# Code Review Report

**Run**: run-eventpulse24-027
**Intent**: pro-tier-and-monetization
**Work item**: `checkout-and-portal-api`
**Reviewed**: 2026-11-11
**Files Reviewed**: 15

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 2 | 0 | 0 |
| Security | 1 | 0 | 0 |
| Architecture | 0 | 0 | 0 |
| Testing | 1 | 0 | 0 |
| **Total** | **4** | **0** | **0** |

**Tests Status**: Passing — backend `16 failed, 6312 passed` (the pre-existing 16); frontend `1826 passed`.

---

## Files Reviewed

**Created**

- `backend/apps/identity/billing_api.py` (new) — the two endpoints
- `backend/apps/identity/services/billing.py` (new) — the service layer
- `backend/tests/identity/test_checkout_portal_api.py` (new) — 24 contract tests
- `frontend/app/dev/fake-billing/fake-billing-panel.tsx` (new) — the shared harness
- `frontend/app/dev/fake-billing/checkout/page.tsx` (new) — the fake checkout page
- `frontend/app/dev/fake-billing/checkout/page.test.tsx` (new) — 10 tests
- `frontend/app/dev/fake-billing/portal/page.tsx` (new) — the fake portal page
- `frontend/app/dev/fake-billing/portal/page.test.tsx` (new) — 6 tests

**Modified**

- `backend/apps/identity/schemas.py` — `CheckoutIn`, `CheckoutOut`, `PortalOut`
- `backend/apps/identity/services/__init__.py` — the two service exports
- `backend/config/api.py` — the `/billing` router mount
- `backend/config/env.py` — the three configured paths
- `backend/config/settings.py` — the three settings
- `backend/domain/errors.py` — `AlreadySubscribedError`, `NoSubscriptionError`
- `backend/tests/architecture/test_no_direct_writes.py` — the surface-file count
- `backend/tests/architecture/test_digest_composition_separation.py` — the request-module list
- `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` — regenerated

---

## Auto-Fixed Issues

### 1. [Code Quality] Import block was un-sorted

- **File**: `backend/apps/identity/services/billing.py:35`
- **Description**: `from ports import registry` sat after `from ports.billing import …`. Ruff's
  `I001` caught it; the fix is a reorder, which has no runtime effect.
- **Diff**:

```diff
 from domain.errors import AlreadySubscribedError, NoSubscriptionError
+from ports import registry
 from ports.billing import BillingCustomer, ProPlan
-from ports import registry
 from shared.db import PERSONAL
```

### 2. [Code Quality] An off-scale spacing utility

- **File**: `frontend/app/dev/fake-billing/fake-billing-panel.tsx:102,109,115`
- **Description**: `w-28` is not a step in the DESIGN.md spacing scale, and the scale test
  (`frontend/tests/spacing-scale.test.ts`) fails on it. An off-scale step generates no CSS at
  all — no warning, just a definition list whose labels have no width. `w-20` is on the
  scale and is the right weight for the label column.
- **Diff**:

```diff
-          <dt className="w-28 text-ink-muted …
+          <dt className="w-20 text-ink-muted …
```

### 3. [Security] The dev page honoured a `next` on any host — an open redirect

- **File**: `frontend/app/dev/fake-billing/fake-billing-panel.tsx` (the `localTarget` helper)
- **Description**: **This is the finding worth reading.** The page read `next` from the
  query string and used it as the `href` of the "Complete checkout" link. A query string is
  attacker-controllable by anyone who can hand a developer a link, so `?next=https://
  attacker.example` produced a link that sends the user off-site.

  This is the same open-redirect the backend refuses to allow — and the backend's refusal is
  one of this item's acceptance criteria. Leaving the dev page as the one place in the
  codebase where a redirect target *is* taken from a request would have been a hole in the
  rule the rest of the item is built on. The app's own posture agrees: every other redirect
  in this codebase is a hardcoded path, never a URL.

  The fix mirrors the backend's rule. A `next` that names a path on this origin is honoured;
  a same-origin absolute URL is reduced to its path (the backend's own success URL is
  absolute, and the point is *where it points*, not *how it is spelled*); anything else is
  refused outright and no link is rendered.

  The panel already had a "No return URL on this session" branch for an absent `next`, so a
  refused target reuses it — the page says plainly that there is nowhere to return to rather
  than rendering a link that goes somewhere unexpected.

- **Diff**:

```diff
+function localTarget(next: string | undefined): string | undefined {
+  if (!next) return undefined;
+  if (next.startsWith("/")) return next;
+  try {
+    const url = new URL(next);
+    const here = window.location.origin;
+    return url.origin === here ? `${url.pathname}${url.search}${url.hash}` : undefined;
+  } catch {
+    return undefined;
+  }
+}
+
 export function FakeCheckoutPanel({ session, plan, next }: FakeCheckoutParams) {
-  const success = next ?? "";
+  const success = localTarget(next) ?? "";
```

Three tests were added or changed with it: the portal's return-URL test now asserts the
*path* rather than the whole URL, the checkout page gained a test that a target on another
site renders **no link at all**, and another that the same-origin success URL keeps its query
string.

### 4. [Testing] Two docstrings promised something the code did not do

- **File**: `backend/domain/errors.py:283`, `backend/apps/identity/billing_api.py:31`
- **Description**: `NoSubscriptionError`'s docstring said *"The message points at the pricing
  page instead"*, and the API module's said the portal refusal was *"409, pointing at the
  pricing page"*. Neither pointed anywhere: the error carries no `details`, and the message
  is a fixed string. The work item only asks for *"a clear refusal, not a Stripe error"* —
  which is what the code does.

  The docstrings were corrected to describe the behaviour, rather than the behaviour being
  changed to match the docstrings. Adding a pricing path to the error would be a new
  decision about what the frontend does next, and that decision belongs to
  `frontend-account-and-billing-settings`, which builds the surface these errors point at.
- **Diff**:

```diff
-    state is what refuses it. The message points at the pricing page instead, because the
-    only sensible next step for someone with no subscription is to start one.
+    state is what refuses it. The message says plainly that there is no subscription to
+    manage, because the only sensible next step for someone with no subscription is to start
+    one — and the frontend decides where that step leads.
```

---

## Reviewed and found correct — no change

**The `CheckoutIn` schema carries exactly one field.** The generated `openapi.json` confirms
`properties: {plan}` and `required: ["plan"]` — no `success_url`, no `cancel_url`, no
`return_url`. The absence is the security property, and it is now structural rather than a
convention: a URL field could not be added without changing the published contract.

**The two refusals are decided before the provider is called.** `_live_subscription` is
consulted before `create_checkout` or `create_portal_session`, and the test that swaps the
billing port for one that raises on any call asserts the call list is empty. This also
keeps the portal refusal from leaking the account's state: a provider error about a
customer that does not exist would confirm more than a plain 409 does.

**The service imports no provider vocabulary.** `apps/identity/services/billing.py` imports
`ports.billing` and nothing else — no SDK, no provider error strings — and the
`stripe-sdk` import contract is kept. The `import-linter` run confirms all 19 contracts.

**The endpoint modules are under AD-5.** `apps/identity/billing_api.py` is a surface file
and makes no direct ORM write; the architecture suite covers it alongside every other
endpoint now that it is named in both lists.

**The dev pages are a harness, not a design surface.** They live under `/dev/`, are
`notFound()` in a production build, and carry a visible "Development stand-in" banner. They
are reached only through URLs the fake adapter mints, so a real Stripe deployment never
points a user at them.

**The service looks the billing port up at call time.** `registry.get_billing_port()` rather
than a module-level `from … import`. This is what makes the port boundary substitutable in
a test — and the test that substitutes it is what caught the mistake when the import was
bound at import time.

---

## Skipped

Nothing. Every finding was either mechanical (auto-fixed) or a security correctness fix
whose own tests were written with it.

---

## One note for the next item

`frontend/app/settings/billing` **does not exist yet.** The backend's success, cancel and
portal-return paths all point at it, and the 409's `portal_path` points at it too — that is
the route `frontend-account-and-billing-settings` will build, and it depends on this item.
Until it exists, the dev checkout's "Complete" link and its "Cancel" link both 404 locally.
That is a real gap in the *local* walkability of the paid path, so it is worth naming here
rather than discovering it mid-item.

---

# Code Review: The caps learn who is Pro — the save gate, and the provider cap that caps everyone

**Work item**: `free-tier-caps-read-entitlement`
**Intent**: `pro-tier-and-monetization`
**Date**: 2026-11-11

## Scope

| File | Action |
|---|---|
| `apps/personalization/services/save_cap.py` | created — the gate |
| `apps/personalization/services/saved_events.py` | modified — idempotence, then the gate, then the write |
| `apps/personalization/services/calendar_connections.py` | modified — `_provider_cap`, tier-chosen |
| `apps/personalization/schemas.py` | modified — `SaveCapOut`, `CalendarCapOut`, `SaveConflictOut` |
| `apps/personalization/api.py` | modified — the two 409 response maps |
| `domain/errors.py` | modified — `SaveCapReached` |
| `shared/constants.py` | modified — the save limit and window; the stale comment resolved |
| `adapters/throttle/memory.py` | modified — **the window rule, fixed** |
| `tests/personalization/test_save_cap.py` | created — 16 tests |
| `tests/personalization/test_calendar_provider_cap.py` | created — 13 tests |
| `tests/adapters/test_throttle.py` | created — 9 tests, **written by this review** |
| `frontend/components/detail/detail-actions.tsx` | modified — the narrowing |
| `frontend/lib/api/openapi.json`, `schema.ts` | regenerated |

## Findings

### 1. The in-memory throttle adapter contradicted its own port contract — FIXED

**Severity: latent defect, and it was live.** `ThrottlePort.check` states the rule in one
sentence: *"The window is fixed: the count resets `window_seconds` after the first attempt in
it."* The Redis adapter implements exactly that — `EXPIRE` is set only when `count == 1`, so
the window slides from the *first* attempt.

The in-memory adapter implemented a **sliding** window instead:

```python
cutoff = moment - window_seconds
attempts = [t for t in self._attempts.get(key, ()) if t > cutoff]
```

It dropped every attempt older than the window *on each call*, so the window effectively slid
from the **last** attempt. Two consequences:

- **A refusal extended the user's wait.** Under a sliding window, the refused attempt is
  itself a recent attempt, so it pushed the expiry out — a user who was refused kept being
  refused for longer each time they tried.
- **A client could hold a bucket open forever** by attempting just often enough to keep the
  count alive.

This is the exact defect class a test double must not have: the fake answered a
*differently-shaped question* than the real adapter, so a test written against the fake
would have pinned behaviour production does not have.

**Fix:** the adapter now anchors the window at the first attempt, exactly as the port says
and as the Redis adapter does.

### 2. Neither throttle adapter had a test of its own — FIXED

**Severity: test gap, and the reason the defect above survived.** `InMemoryThrottleAdapter`
was only ever reached indirectly, through app-level tests that stub the port out.
`RedisThrottleAdapter` — **the adapter production actually runs** — had no test at all.

So the port's one stated rule was implemented twice and pinned by neither.

**Fix:** `tests/adapters/test_throttle.py` was written by this review. It pins:

- the window rule on the in-memory adapter, at the boundary;
- **the parity** — the same calls against both adapters, asserting they answer identically.

The Redis adapter is exercised against an in-memory stand-in for Redis that **deletes expired
keys**, because that is what real Redis does and it is precisely the behaviour the window
rule depends on. A stand-in that kept an expired key would have made the parity test test
the stand-in rather than the adapter.

**The tests are load-bearing, and this was checked rather than assumed.** Reverting the
adapter to its old sliding implementation and re-running the file:

```
FAILED test_the_window_closes_on_the_first_attempt_plus_the_window
FAILED test_a_refused_attempt_does_not_move_the_anchor
FAILED test_the_window_does_not_slide_from_the_last_attempt
FAILED test_the_two_adapters_agree_about_every_call
FAILED test_the_two_adapters_agree_on_the_window_opening_again
5 failed, 4 passed
```

The adapter was then restored and the file passes 9/9.

### 3. The two adapters' parity was verified independently of the test — CONFIRMED

**Severity: verification.** The parity claim in finding 2 rests on the stand-in being
faithful, so it was checked by hand first, over a walk that crosses the window boundary:

```
     t |       mem |     redis | match
     0 |      True |      True | OK
    10 |     False |     False | OK
    50 |     False |     False | OK
    99 |     False |     False | OK
   100 |      True |      True | OK
   101 |     False |     False | OK
   150 |     False |     False | OK
   199 |     False |     False | OK
   200 |      True |      True | OK
   201 |     False |     False | OK

mismatches: 0
```

The two adapters agree on the decision at every point, **including the exact boundary**.

An earlier run of the same walk reported mismatches at t=100 and t=200. Those were an
artifact of the stand-in, not of the adapters: the first version of the stub kept expired
keys, so it believed a closed window was still open. Real Redis deletes the key. The stub
was corrected, and the parity re-verified. The mismatch was worth chasing rather than
writing off, because "the two adapters disagree" is exactly the failure this review exists
to prevent.

### 4. The frontend reached into `details` without narrowing — FIXED

**Severity: latent type error, caught by the contract change.** `detail-actions.tsx` read
`response.error?.details?.conflicts?.[0]` on any 409. With two refusal shapes behind one
status code, `details` is no longer one shape, and `tsc` rejected the access.

**Fix:** the client narrows on `code` — the field the server set — before reading
`details.conflicts`. This is the narrowing the discriminated union was designed for, and
the frontend's behaviour is unchanged: a save-cap refusal was never a clash, and it was
already on the failure path.

## Reviewed and found correct — no change

**The two refusal payloads have exactly two fields.** `SaveCapDetails` and
`CalendarCapDetails` are both `{cap, upgrade_hint}` and nothing else. The schemas make a
modal-shaped field **inexpressible** rather than merely absent from the prose, and the tests
pin the key set exactly — so a future edit that grows a `modal` fails the suite rather than
shipping.

**The discriminated union produces a real `oneOf` in the OpenAPI.** Verified directly against
the generated document, not assumed:

```json
"409": { "content": { "application/json": {
  "discriminator": { "mapping": { "save_cap_reached": "#/components/schemas/SaveCapOut",
                                  "scheduling_conflict": "#/components/schemas/SchedulingConflictOut" },
                     "propertyName": "code" },
  "oneOf": [ {"$ref": "#/components/schemas/SchedulingConflictOut"},
             {"$ref": "#/components/schemas/SaveCapOut"} ] } } }
```

The discriminator is the error's own `code`, which is exactly the field the frontend
branches on. A generated client reads `details.cap` on one branch and `details.conflicts` on
the other, without guessing.

**The gate sits after the idempotence lookup, and that position is forced.** An existing
test (`test_a_save_is_idempotent_and_one_row`) asserts 201 then 200 with one row. So the
order — idempotence, then gate, then write — is not a preference: a repeat save is the same
row returned again, and gating it would spend an allowance on a save that did not happen.

**The refusal writes nothing.** The gate raises inside the transaction, before any row
exists. The test pins both halves: no `SavedEvent` row, and no audit entry either — an
audit row saying "we refused to save" would be a record of a save that never happened.

**The throttle key namespaces are disjoint.** The four throttle users build four distinct
key shapes — `auth:` (identity), `preview:` (catalog), `event_report:` (personalization),
`save:` (personalization) — and the Redis adapter prefixes all of them with `throttle:`.
Two features cannot collide. The `save:` prefix was checked against the auth keys
specifically, because both live in the same Redis instance.

**Neither cap reimplements "is Pro".** Both call `is_pro(user_id=...)`, the single published
read from `subscription-model-and-entitlement`. The `_provider_cap` helper is one `if` on
that bool; the gate is another. There is no second mapping of status to tier anywhere, so
the two cannot disagree about what Pro means.

**The lapse is a transition, not a second row.** `Subscription` allows at most one live row
per user, so a lapse updates the existing row to `CANCELED`. Both test files do this the
same way, and both document why adding a `CANCELED` row beside the `ACTIVE` one would leave
the user still Pro.

**A Pro user spends no throttle slot at all.** The gate returns early rather than being
made with a limit of infinity, so a Pro user's saves leave no trace in the counter. The test
pins this by recording every `check()` call and asserting the list is empty.

**The downgrade does not delete anything.** The provider cap is enforced at the *connect*
step, so a lapse closes the door behind the user and leaves their existing connections
alone. The test asserts two connections survive a lapse. What happens to over-cap data on a
downgrade is an open question in the brief, and this item does not quietly answer it.

**The import contracts still hold.** `lint-imports`: **19 kept, 0 broken**. `apps.identity`
does not import `apps.personalization.models`; `save_cap.py` reaches entitlement through
`apps.identity.services`, the published seam.

## Skipped

Nothing. Every finding was either a correctness fix with its own tests, or a test gap
closed by tests written for it.

## Verification

| Check | Result |
|---|---|
| `pytest tests/adapters/test_throttle.py` | 9 passed |
| `pytest tests/personalization/ tests/adapters/ tests/identity/ tests/api/` | **2126 passed** |
| `pytest` (full backend) | 16 failed, **6358 passed** — the 16 are **identical to the verified baseline** |
| `ruff check` / `ruff format --check` | All checks passed / 9 files already formatted |
| `lint-imports` | 19 contracts kept, 0 broken |
| `pytest tests/api/test_contract.py` | 1 passed |
| `pnpm vitest run` | **1826 passed (109 files)** |
| `pnpm lint` / `pnpm typecheck` | clean |

The 16 backend failures are the pre-existing baseline failures, confirmed earlier in this
run by stashing every change and re-running the whole suite into a comparison file that
contained exactly those 16 names. **No existing test was broken by this item.**

## One note for the next item

**The inline upgrade prompt is still not rendered.** A save-cap refusal and a calendar-cap
refusal both reach the frontend as a 409 with `cap` and `upgrade_hint`, and the frontend
does the right thing with them today — a save-cap refusal falls through to the generic
failure path, and a calendar refusal likewise. But *rendering the calm inline prompt with
the quiet "Upgrade" link* is `frontend-upgrade-prompts`'s work, and that item is `pending`.

Until it lands, the product has a gate with no visible prompt behind it. The **backend** half
is complete and the contract is published; the frontend half is a separate item, and this
one should not grow into it.

---

# Item 5 — `frontend-pricing-page`: code review

**Scope:** the pricing screen, its route, the entitlement read it needs, and the sign-in
round trip it depends on. Reviewed after the tests passed, against the plan and against
FR-48.

**Verdict: approve with one real defect.** The defect was in the *plan*, not only in the
code, and it was found by checking an assumption rather than by reading the code carefully.
It has been fixed and the fix is tested.

## The HIGH finding: `next` was a dead end

> The pricing page's "Sign in to buy" link carries `/signin?next=%2Fpricing`, but
> `/signin` has no `searchParams` and `SigninForm` does `router.replace("/")`. The
> parameter is ignored at the destination.

**Why it is HIGH.** The criterion is *"a signed-out visitor … is routed to sign-in on
choosing a plan."* The page did route them to sign-in. But the sign-in page did not route
them **back** — so a visitor who chose a plan, was asked to sign in, signed in, and landed
on the home page had silently lost their intent. The link looked right and the code was
right; the *destination* was wrong, and the plan was what said otherwise.

**How it was found.** The plan's own file list said "the sign-in route takes a `next`
parameter — let me verify that." The verification was never done, and the implementation
inherited the assumption. This is the failure mode the plan's checklist exists to prevent,
and it is the reason the assumption was tested rather than accepted.

**The fix.** `frontend/lib/return-path.ts`:

```ts
export function returnPath(next: string | null | undefined): string {
  if (typeof next !== "string") return DEFAULT_RETURN_PATH;
  const candidate = next.trim();
  if (candidate === "") return DEFAULT_RETURN_PATH;
  if (!candidate.startsWith("/")) return DEFAULT_RETURN_PATH;
  if (candidate.startsWith("//")) return DEFAULT_RETURN_PATH;
  if (candidate.includes("\\")) return DEFAULT_RETURN_PATH;
  if (/^[a-z][a-z0-9+.-]*:/i.test(candidate)) return DEFAULT_RETURN_PATH;
  return candidate;
}
```

**A redirect target read from a query parameter is an open redirect**, so the guard is not
optional decoration — it is the reason the feature is safe. `/signin` now takes
`searchParams`, passes the *guarded* destination to `SigninForm`, and `SigninForm` replaces
to it after a successful sign-in. Nine tests pin the guard.

**A note in the review's favour and against it.** The `/signin` route's own test file
already contained "refuses to redirect to somewhere off this site" — and it had been
passing, against a route that could not redirect anywhere at all. **The test was passing for
the wrong reason.** It passes for the right reason now. That is worth recording: a green
test in an area nobody had built yet is not evidence.

## The MEDIUM findings, all fixed

**1. An unavailable session was folded into "signed out."** The route returned the
`signed-out` state for both `anonymous` and `unavailable`, so a signed-in visitor whose
session read failed was told "Sign in to buy" — which `lib/session.ts` calls "a lie about
who they are", in a button. Now `unavailable` renders the tiers with the checkout button
and **no** sign-in link; the checkout itself says what is true.

**2. The no-upsell test was a blacklist.** Eleven banned phrases is a tripwire, not the
rule. It is now an **allowlist**: the Pro card's prose is FR-48's sentence and nothing else.
The blacklist was kept alongside it, because a countdown or a scarcity badge arrives in a
string rather than a sentence. See the test report for the mutation that proves the
allowlist bites.

**3. No `<main>` landmark.** The route rendered its content into a `<div>`. Now it has a
`<main>`, as `/preview` does.

## The gaps the review found, now closed

**No axe gate.** Every public surface in this project carries one; the pricing page is a
new public surface and had none. `frontend/tests/pricing-a11y.test.tsx` audits all three
visitor states, over `document.body`, and includes a "can fail" mutation test.

**The state label was counted as marketing copy.** The first allowlist failed on
"You're on Free" — which is a *state*, not a sales pitch. Rather than widen the allowlist
to include any sentence that sounds like a label, the taglines are now marked
`data-tagline`, and the test says "every paragraph is either the tagline or a state
label". The rule stayed strict; the classification got precise.

## What the review did not find

**The entitlement read is correct and minimal.** It returns one bool, it is implemented
over the one published `is_pro`, and it is tested to call no provider, write no row and
write no audit entry. The page and the caps cannot disagree about what Pro means, because
there is only one definition.

**The two inference paths were rejected for the right reasons.** Showing a Pro user a buy
button that 409s, and minting a provider session as a side effect of reading the page, are
both worse than one extra endpoint.

**The copy discipline holds.** The mockup's Phase 2 features, "priority support from
Brooklyn" and share-links are all absent; the feature lists are FR-48's. "Save 18%" is
arithmetic, not persuasion: $49 against $4.99 × 12 is an 18.2% discount.

## Skipped

Nothing. Every finding was fixed, or was a test gap closed by a test written for it.

## Verification

| Check | Result |
|---|---|
| `pnpm vitest run` (full frontend) | **1885 passed** (114 files) — no failures |
| `pytest` (full backend) | 16 failed, **6369 passed** — the pre-existing 16 exactly |
| `pytest tests/identity/test_billing_subscription_api.py` | 11 passed |
| `pnpm typecheck` | clean |
| `pnpm lint` | clean |
| `pnpm format:check` | clean |
| `tests/spacing-scale.test.ts` | passes — `py-0.5` / `px-2.5` removed, `px-2` used |

The backend delta against item 4's baseline is **+11 passed, 0 failed**, and the 11 are
exactly the new subscription-read tests. The 16 failures are the same 16 — save-race,
timeline/conflict, reminder-plan, personal-events, url-feed — none of which touch billing.

## One note for the next item

**The pricing page and the account page will both need to read the entitlement.** This
item's read lives in `frontend/app/pricing/page.tsx`, inline, as a private `readTier`. When
`frontend-account-and-billing-settings` needs the same answer, that helper should move to
`frontend/lib/` — where this repo's other reads live (`lib/session.ts`, `lib/city-page-read.ts`,
`lib/url-feed-read.ts`) — rather than being written a second time. **This item does not do
that move**, because nothing else needs it yet, and a shared helper with one caller is not a
shared helper.

---

## Work Item: `frontend-upgrade-prompts`

All seven acceptance criteria met. Three things are worth a reader's attention: one copy
regression this item introduces and deliberately does not fix, one deliberate change to an
existing surface's behaviour, and one guard that was decorative until it was probed.

### 1. The calendar cap's sentence got worse, and the fix belongs in the backend

Acceptance criterion 4 is unambiguous: *"The prompt renders from the server's
`upgrade_hint` … It does not hard-code the sentence."* So it does. The consequence:

| Surface | Before this item | After |
|---|---|---|
| Save cap | *(no prompt existed)* | "You saved one event today. Save more with Pro." |
| Calendar cap | "You've connected the calendars your plan allows." | **"Save more with Pro."** |

The calendar prompt used to render the refusal's `message`, which states the fact. It now
renders `upgrade_hint`, which is `"Save more with Pro."` — a nudge with no stated cause.
After a failed connect, that reads as a non-sequitur.

**Not fixed here, on purpose.** Three ways to fix it were available and all three were
wrong for this item:

- *Render `message` + `upgrade_hint`.* Correct for the calendar, redundant for the save cap
  ("You've used your free save for today." followed by "You saved one event today…").
- *Branch on the code and pick the field.* The frontend would then be choosing the copy,
  which is the thing criterion 4 forbids.
- *Write a better sentence in the component.* Hard-coding, same criterion.

**The fix is one string in `backend/apps/personalization/services/calendar_connections.py:449`**,
making the calendar hint a complete sentence the way the save hint already is. It was not
made here because `EXPERIENCE.md` §3 has an approved sentence for the save-cap prompt and
**none for the calendar cap**, and inventing approved copy is not this item's call. Flagged
for the Planner as a one-line copy item.

This is a visible regression on a live surface and is reported as one, not buried.

### 2. The onboarding cap block changed from `role="alert"` to `role="status"`

`alert` is assertive — it interrupts a screen reader mid-sentence. Hitting a tier ceiling
is information, not an emergency, and this item's whole posture is that a cap must not
interrupt. Making it `alert` on one surface and `status` on the other would also mean two
spellings of a UI the acceptance criteria say must have one.

A deliberate change to shipped behaviour, pinned by a test that asserts `role="alert"` is
now absent.

### 3. `CAP_CODES` was decorative

Found by mutation, not by reading: deleting the code check broke **nothing** in 79 tests,
because the only non-cap 409 under test carried no cap-shaped fields and was rejected by
the field checks anyway. Written up in the test report; fixed by the test that makes it
load-bearing.

### What this item does not deliver, and why

- **The mockup's expanded panel** (`pro-upgrade-cta-desktop.html`) has `role="dialog"` and
  its own copy. The backend payload, FR-48's criterion and the work item all say inline.
  **The payload wins**; the mockup is the authority on feel, not on mechanism. Recorded as
  a deliberate divergence, with its "Not now" dismissal and muted-footer state.
- **Browse's disabled Save state** (`EXPERIENCE.md` §4) is a different surface's component
  and Browse is not in this intent. The prompt here is the *refusal* path.
- **`readApiError` was not widened.** It is used in nine places; `readCapDetails` is a
  sibling that reads the same body for a different question, so the other nine are
  untouched.

---

## Work Item: `per-day-quiet-hours-domain-and-model`

All seven acceptance criteria met. The two design decisions that changed during
implementation are both recorded in the plan's "Deviations" section; this is what a reviewer
should look at.

### 1. The design doc contradicted itself, and the resolution is the safer half

It said `NotificationSettings.quiet_hours` *becomes* the weekly value, and also listed
`schemas.py` among the files asserted unchanged. Those cannot both hold: `schemas.py` reads
`window.start` off that field.

Resolved by keeping `quiet_hours` exactly as it was — the base window, the thing the settings
API reports — and adding `effective_quiet_hours: WeeklyQuietHours` as what the delivery path
reads. All seven delivery call sites were moved to it.

**This is also the safer failure mode, which is why it was not just the cheaper fix.** Under
the design as approved, a consumer nobody updated raises `AttributeError`. Under this one it
keeps using the base window: wrong for a Pro user, but today's behaviour, and it cannot put
a send at 3am. For a change whose one serious failure mode is a notification at the wrong
hour, the variant that degrades to "the old correct answer" beats the one that degrades to a
crash on the delivery path.

### 2. A guard was designed, tested, and deleted before it shipped

`has_sendable_gap` protected against a week with no sendable moment. Seven day-anchored
windows **cannot** cover a week (the arithmetic is in the test report and in
`MAX_DEFERRALS`' docstring), so the function could only ever return `True`, and the command
refusal built on it could never fire or be tested.

Deleting it was the right call over shipping it "defensively": an untestable refusal is a
branch that will rot, and a reader who finds it will reasonably assume the state it guards
is reachable. The invariant is better recorded as a proof beside the bound it justifies.

### 3. `max(ends)` is an optimisation, not the mechanism

Found by mutation, and written up in the test report. The docstring was corrected; the
acceptance criterion is met by the fixpoint loop. Flagged here because a future reader
tempted to "simplify" the loop into a single pass would break the criterion while `max`
sits there looking like the thing that enforces it — the three-day-chain test is what stops
that, and it is named in the docstring.

### 4. What a lapsed Pro user gets, stated once and in one place

The criterion forbade leaving this implicit. It is decided in `_effective_week` and nowhere
else: **the override rows stay, and they stop being read.** The user falls back to their base
window, and a resubscribe restores all seven without them re-entering anything. Two tests
cover the lapse and the return.

**The consequence worth carrying to item 8:** a lapse silently moves a Pro user's delivery
times back to the base window. That is correct — they are not paying for seven windows any
more — but it is the only delivery-time change in this intent caused by a billing event.
`quiet-hours-pro-api` should report the **effective** schedule rather than the stored one, so
a lapsed user is never shown seven windows that are not in force.

### 5. The entitlement read landed on the delivery path, cheaply

`_effective_week` queries overrides first and asks `is_pro` only if it finds any. A user who
has never been Pro — every Free user, which is the batch's whole population — never reads
`Subscription` at all. Both halves are pinned by tests that assert on the **table a query
names**, not on a query count, because the count includes transaction bookkeeping that has
nothing to do with the claim.

`apps.delivery → apps.identity.services` is permitted: only `apps.identity.models` is
protected, and `save_cap.py` already does it. All 19 import contracts stay kept.

---

## Work Item: `quiet-hours-pro-api`

All six acceptance criteria met. Two things a reviewer should look at: the shape chosen
against the item's stated risk, and a second docstring that credited the wrong line.

### 1. One representation, not two — which is what the item asked for

The work item named the risk as **shape drift**: "two parallel spellings of quiet hours in
the API, one legacy and one weekly, that slowly disagree." So there is no second endpoint
and no weekly variant of `NotificationSettingsOut`. Three fields on the body that already
exists:

| Field | Direction | Meaning |
|---|---|---|
| `quiet_hours` | read + write | **Unchanged.** "This window, every day." |
| `quiet_hours_overrides` | read + write | `{weekday, start, end}`, at most seven. Pro to write. |
| `effective_quiet_hours` | **read only** | Seven entries: what the scheduler will apply. |

These cannot drift because the third is **derived from the other two and cannot be
written**. It is not a parallel spelling; it is the answer to a different question — "when
will I actually be quiet" — which nothing else on the response could answer.

### 2. `effective_quiet_hours` is the carried risk from item 7, closed

`per-day-quiet-hours-domain-and-model`'s review flagged that a lapse silently returns a Pro
user to their base window, and asked that this item report the effective schedule rather
than the stored one. It reports **both**, which is better than either: a lapsed account sees
its seven stored windows *and* sees that the effective week is the base window every day.
Reporting only the stored ones would show seven windows not in force; reporting only the
effective ones would look as though the lapse had deleted their data.

### 3. The paywall is at the API, and that is a deliberate split

`replace_quiet_hours_overrides` is tier-agnostic, as `set_quiet_hours_override` was. The
refusal lives in `preferences_api._refuse_weekday_windows_without_pro`. This is not two
answers to item 7's rule but the same one: **the rows are the user's data and the
subscription governs their effect, not their existence.** A command that refused on tier
would have to be re-run after an upgrade to restore what the user already said.

Two consequences worth stating because neither is obvious:

- **Clearing is never refused.** `[]` removes every override and returns the account to one
  window for the week — the Free shape. Refusing someone the ability to go back to what
  their plan includes would be absurd, and it is also exactly what a lapsed account needs
  to tidy up.
- **A lapsed account is refused a write and keeps its read**, which is what the acceptance
  criterion required.

### 4. A second docstring credited the wrong line

Mutation testing again. `replace_quiet_hours_overrides` validated the whole week before
opening the transaction, and said that was what kept the server from seeing a
partially-updated week. **It is not** — moving the validation inside the write loop keeps
every atomicity test green, because the raise unwinds `transaction.atomic`.

The validation still runs first, for a real but much smaller reason now stated in the
docstring: a request that will fail should not first take the user's advisory lock and
serialise their other settings writes behind it. This is the second time in two items that
a mutation found a comment claiming more than its line does, which is worth noting as a
pattern rather than twice as an incident.

### 5. The refusal reuses the prompt rather than growing a second one

`QuietHoursProRequired` carries `{cap, upgrade_hint}` and no modal-shaped field — the same
payload as `SaveCapReached` and `CalendarProviderCapReached`. The whole frontend change is
`quiet_hours_pro_required` joining `CAP_CODES`; the inline prompt built in
`frontend-upgrade-prompts` renders it with no new component and no new copy path. The
surface that shows it is item 9's.

### 6. Addendum — one guard test changed, and why that is not a weakening

Closing this item required touching a test belonging to `subscription-model-and-entitlement`:
`test_no_app_code_deletes_a_subscription`. It scanned each file under `apps/` for the words
`Subscription` and `.delete()` and flagged any file holding both.
`notification_preferences.py` holds both — it deletes `QuietHoursOverride` rows, and its
docstring explains that a lapse never deletes a subscription. The guard was reading an
explanation as a violation.

The scan now runs over the file's **code**, with docstrings and comments blanked out. What
was *not* changed is as important: it is still file-wide rather than following the call, so
`qs = Subscription.objects.all()` on one line and `qs.delete()` on the next is still caught.
A probe module asserting exactly that shape was run against the new guard; it fails, as it
must, and the clean tree passes.

**Three files were changed after the review above was written**, all of them cleanup rather
than behaviour: the unused `time` import in the new test file, the guard test, and Prettier
formatting of `lib/cap-details.ts`. No production code changed.

---

## Work Item: `frontend-pro-quiet-hours`

All nine acceptance criteria met, two of them on weaker evidence than they deserve (below).
One defect found and fixed in review; one deviation from DESIGN.md logged on purpose.

### 1. The deviation: `component.control.day-picker`'s Free state was not built

DESIGN.md's Amendment A-19 contains **both** of these:

> Free users see all 7 rows in a locked visual state — day-name in `{color.ink.muted}` …
> toggle replaced by a small `Lock` glyph …

> **Don't:** Render the per-day picker for Free users (Pro tier is the contract — Free
> stays single-window).

They cannot both be followed. The build takes the second, because three other sources agree
with it: the work item's acceptance criterion (*"A Free user's screen is unchanged"*), the
existing `page.test.tsx` guard, and `page.tsx`'s own standing note that *"a locked row for a
feature that does not exist on this tier would be a row the user can neither use nor
remove."* A Free user gets their single window plus **one** inline line — approved at the
plan checkpoint.

### 2. The toggle was relabelled, because the mockup's wording promises a state the API lacks

The mockup draws an On/Off toggle per day, default Off. In the data, a weekday with no
override row means **the base window applies that day** — not *no quiet hours that day*.
There is no way, anywhere in `quiet-hours-pro-api`, to say "quiet every night except
Thursday".

A row labelled "Off" would therefore tell a user they had switched Thursday's silence off
when they had not, and the only way they would find out is a 3am notification that never
came. The two states the control can actually distinguish are **"Same as usual"** and **a
window of its own**, and those are the two it shows.

### 3. The paywall is read server-side, not inferred

`readIsPro()` calls `GET /api/billing/subscription` — the published one-bool answer. The
tempting shortcut, inferring the tier from `quiet_hours_overrides` being non-empty, is wrong
in **both** directions: a Pro user who has set no weekday yet would be sold something they
already own, and a lapsed user would be handed an editor the API refuses. The page therefore
has **three** states rather than two, and the third — lapsed — is the one that needed saying
out loud.

### 4. Defect found in review: a dangling `aria-controls`

Each day's header button carried `aria-controls={panelId}` unconditionally, while the panel
itself only exists when the row is open. A collapsed row therefore pointed at an id that was
not in the document — an ARIA reference to nothing, on all seven rows at rest, which is the
state the page is in when it loads.

Fixed by setting the attribute only while the panel exists. Keeping the panel mounted and
hidden would have been the other fix, and was rejected: an always-mounted panel puts
fourteen time inputs in the DOM, which is the thing the accordion exists to avoid.

### 5. Mutation testing found an untested line, not an untrue comment

Deleting the `.sort()` from the payload left the whole suite green: the test that looked
like it pinned the order used a Monday-first fixture, so its assertion held whether anything
sorted or not. A shuffled fixture now pins it. The docstring's claim was already the modest
one — *"the server does not care, and a reader comparing a request to the UI does"* — so
nothing had to be retracted this time. Four of the other five probes were caught outright.

### 6. What is weakly evidenced, and should not be read as proven

**"Works at mobile width" and the accordion's accessibility are pinned in jsdom, not in a
browser.** `testing-standards.md` names Playwright + axe-core, but the repo has no
`playwright.config`, no `e2e/` directory and no axe dependency — the E2E stack is
aspirational. What is actually asserted is structural: one day's clocks in the DOM at a
time, `aria-expanded` on a real `button`, the week as a list. Nothing has rendered this at
375px or run an accessibility audit over it.

**The Free user's upgrade sentence is duplicated across the stack.** It is a string in
`page.tsx` and a constant in `shared/constants.py`, because a Free user is never refused and
so never receives the server's copy. A test asserts the exact string, so they cannot drift
silently — but a backend copy change turns that test red rather than updating the screen,
and that is the cost of the chosen option, accepted at the checkpoint.

---

## Work Item: `saved-collections-model`

All nine acceptance criteria met. Two defects found and fixed in review, one architecture
rule narrowed with approval, and one small Unicode caveat left standing deliberately.

### 1. Defect: an N+1 in `reorder_collections`

`_view()` falls back to counting one collection's memberships when the caller does not
supply a count. That is right for a command that touched one collection and wrong for a
reorder, which returns the **whole list** — so reordering twelve collections ran twelve
extra `COUNT` queries, one per returned view, on top of the renumbering.

Fixed by extracting `_item_counts(user_id)`, the single grouped read `list_collections` was
already doing, and using it in both places. `test_a_reorder_counts_the_collections_in_one_query_not_one_each`
pins it, and was probed by reinstating the N+1 — it fails, as it must.

### 2. Defect: a missing *save* reported as a missing *collection*

`add_to_collection` raised `CollectionNotFoundError` when the saved event could not be
found — having located the collection successfully one line earlier. A client acting on
that error would go looking at the wrong object, and the docstring I had written for it was
muddled in a way that should have been the clue.

It now raises `SavedEventNotFoundError`, the error that already exists for exactly this.
The privacy reasoning is unchanged: another user's save is reported as **absent**, never as
forbidden, because "it exists but is not yours" confirms the existence of someone else's
content.

### 3. The architecture rule, narrowed — what was traded

Two tests asserted that `personal`'s models hold **zero** relation fields. The membership
table's two foreign keys are intra-schema and intra-app, and the only trace either leaves on
`SavedEvent` is a reverse accessor — not a column, and not a constraint on `SavedEvent`'s
table.

Each of the three rules those tests cite has its own dedicated test, and **all three were
green the entire time**, including `test_no_foreign_key_crosses_from_personal_to_catalog`,
which reads the keys Postgres actually holds rather than the models' metadata. The blanket
assertion was a wider net than its own stated rationale.

Both now forbid a relation for **what it reaches** — a catalog app, `User`, `ContentType` —
rather than for existing, and were probed with a real `SavedEvent → ingestion.Event`
foreign key, which both reject.

**The honest cost:** a blanket rule is cheaper than a judgement, and this one is now a
judgement. Any future foreign key inside `personal` passes these two tests in silence. The
wall itself is unaffected — it is enforced against the database — but the early, mechanical
warning that *any* relation here deserves a second look is gone. That trade was put to the
user explicitly rather than taken quietly, which is the only reason it is acceptable.

### 4. Deferred constraints are new here, and the test says what they mean

`saved_collection_user_position_uq` is the codebase's first `DEFERRABLE INITIALLY DEFERRED`
constraint. It exists because dense positions must be renumbered, and a renumber is
transiently inconsistent by nature.

The first version of its test asserted the wrong thing — it expected an error at the end of
an `atomic` block, which in Django's test transaction never commits — and the deferral was
what made it fail. It now asserts both halves: the duplicate insert lands quietly, and
`SET CONSTRAINTS ALL IMMEDIATE` raises. A companion test pins that the *name* constraint is
**not** deferred, so the contrast is recorded rather than assumed.

### 5. Left standing: case folding is the database's, not Python's

`_name_taken` compares with Python's `str.lower()`; the constraint uses Postgres' `Lower()`.
For ASCII they agree. For a few Unicode cases they need not — Turkish dotted/dotless I being
the usual example — and a disagreement would mean the pre-check passes and the insert then
raises `IntegrityError`, surfacing as a 500 rather than as `CollectionNameTaken`.

Not fixed, because the fix (`.annotate(folded=Lower("name")).filter(folded=Lower(Value(name))))`,
pushing both sides into the database) buys a case no test can currently reach, and the
constraint is still the authority either way — the race between check and insert ends there
regardless. Recorded so the next person meets it as a known edge rather than a surprise.

---

## Work Item: `data-export`

All nine acceptance criteria met, one of them on weaker evidence than it asks for. Two
defects found in review, one security gap found by mutation testing, and one tradeoff
accepted knowingly.

### 1. The decision this item turned on was legal, not technical

FR-52 concedes its own tension — *"export is free for GDPR compliance but UX is in Pro
settings for non-EU users"* — and the PRD §11.5 table resolves it as *"Free in EU/UK/CA/BR/AU;
Pro-only elsewhere"*. **That resolution is not implementable here without doing something
worse than the problem.** The product stores no country and no geo consent, so the gate
would require collecting location data in order to decide a privacy right, and every wrong
guess denies a legal entitlement to the person it belongs to.

The export is therefore ungated. `test_a_free_account_may_request_an_export` exists so the
decision cannot be quietly reverted into a tier check by someone reading the pricing page.

**Follow-on, flagged and not fixed here:** `/pricing` still sells "JSON + ICS export" as a
Pro bullet. That copy is now inaccurate. It belongs to `frontend-pricing-page`.

### 2. Defect found in review: an export nested inside the next one

`DataExport` is `ACCOUNT_CONTENT`, so the registry exports it — rightly, since *when a user
asked for their data* is a fact about them. But the row carries `json_body` and `ics_body`,
which are **a copy of everything else in the export**. Left in, a second request would carry
the first's entire payload, a third would carry both, and each download would double while
telling the user nothing new.

The model now declares `export_redact_fields = ("json_body", "ics_body")` — one more
declaration beside `retention_category` and `export_user_path`, in the same place, read the
same way. The metadata still exports. Probed by ignoring the declaration: the test fails.

### 3. Security gap found by mutation testing, not by review

Disabling the credential redaction's **type** check left all 74 tests green. The only
`EncryptedTextField` in the tree is also *named* `credential`, so the name list caught it —
the belt held while the braces were cut, and the check that matters for a field added later
was pinned by nothing.

`_is_secret_field` now has three tests of its own: an encrypted field named `notes` is
redacted, a plain field named `password` is redacted, and an ordinary field is **not** — the
third because a redactor that redacted everything would pass the first two and hand the user
a file of nothing but `[redacted]`.

### 4. Two tests failed in ways that improved the design

**Seven models could not name their user.** `identity.User` was among them — the account
row itself would have been the one record missing from a user's own export. The audit tables
reach their user through `actor_id`; `User` through its own `id`. Only `sessions.Session`
genuinely cannot, and it is declared not portable with the reason recorded where it is
declared: a session key is a **live credential**.

**The export reached across the AD-3 wall.** Once the audit tables became reachable,
`ingestion.IngestionAuditEntry` — `AUDIT_LOG`, in `catalog` — joined the walk, and 24 tests
failed with *"Database queries to 'catalog' are not allowed"*. The fix filters on the alias;
the **first** version of that fix imported `config.db_router` from an app and was rejected
by `lint-imports` for breaking AD-2's inward-pointing layers. Two guards, in sequence, each
catching what the other would have missed.

### 5. Accepted knowingly: the token is in the URL

`GET /api/exports/{id}/{fmt}?token=…` carries a credential in a query string, which reaches
server access logs and proxy logs. The alternatives are worse for the actual use: a header
cannot be sent by a mail client following a link, and a POST form in an email is not a link.

Mitigated rather than solved — the token is single-purpose (one export, one user, one
format), expires with the row, and the response sets `Cache-Control: no-store, private` and
`Referrer-Policy: no-referrer` so it is neither cached by a shared proxy nor forwarded in a
`Referer`. **Access-log exposure remains**, and an operator rotating logs should know the
links in them were live for seven days.

### 6. The ICS criterion is met on weaker evidence than it asks for

*"Importable into Google Calendar / Apple Calendar / Outlook"* — none was run, and this repo
has no harness that could. The file round-trips through `formats/ics/parser.py`, the
`icalendar`-based parser this product already uses for subscribed feeds, with titles,
locations and instants intact; the structural rules those clients differ on are asserted
directly. That is real evidence of a real round trip and it is **not** three clients. Stated
here and in the test report rather than implied away.

---

## Work Item: `frontend-account-and-billing-settings`

All nine acceptance criteria met. One backend endpoint added inside a frontend item with the
design's explicit blessing, two defects found while testing, and one limitation recorded
rather than papered over.

### 1. A backend read in a frontend item, sanctioned in advance

`SubscriptionOut` stays one bool — its docstring is emphatic that *"a field here would be a
field two callers could disagree about"* — and `is_pro` is **true for `past_due`**. So the
existing endpoint cannot see the one state these criteria single out.

The same docstring named the remedy before this item existed: *"the fuller subscription
record belongs to the account-and-billing surface, **which needs a wider read and builds it
there**."* `GET /api/billing/account` is that read. The entitlement endpoint is untouched,
and a parametrized test pins that the two never disagree about entitlement — a failure that
would otherwise be silent, showing "you're on Pro" over features the server refuses.

### 2. The limitation this screen cannot fix, stated instead of hidden

Stripe cancels by setting `cancel_at_period_end`. **This product models it nowhere** — not
in `ports.billing`, not in either adapter, not on `Subscription`, not in the webhook
mapping. A subscription cancelled in the portal therefore reads `active` until its term runs
out, and nothing on this side can tell "renews on 3 March" from "ends on 3 March".

So the copy says **"Your plan runs until 3 March"**, which is true either way, and a test
asserts the word "renew" never appears. Guessing "renews" would be reassuring and wrong for
precisely the person most likely to be on this screen: somebody who cancelled five minutes
ago and came to confirm it worked.

**The real fix is a field**, and it reaches the port, both adapters, the model, a migration
and the webhook mapping — an already-closed item's territory, and more than this item should
quietly take on. Recorded here as the follow-on it is.

### 3. Defect: a refusal with no sentence rendered as no refusal at all

`saveFailureMessage` returns the API's own message whenever the body is the project's error
shape, **including when that message is empty**, and the component renders `{failure}` —
which an empty string makes falsy. A user would have clicked, seen nothing change, and had
no way to know whether anything happened.

Both call sites now fall back to their own line, each with a test. **The same hole exists in
`quiet-hours-window.tsx`, `digest-delivery-time.tsx` and `default-reminder-slots.tsx`**,
which call the helper the same way. They belong to a closed item and are not changed here,
but it is one class of bug across four files and deserves a sweep rather than four
rediscoveries.

### 4. A test of mine was passing for the wrong reason

The past-due case asserted that `"You're on the free plan"` was absent — and it was absent
whatever the component did, because the rendered sentence ends in a full stop. The *positive*
assertion in the Free case failed first and exposed both. Both now match the rendered text
exactly.

This is the second time in this run a negative assertion has been found passing vacuously
(the first was the `.sort()` fixture in `frontend-pro-quiet-hours`). Worth noting as a
pattern: a `queryBy*(...)` asserted null is only as strong as the string it looks for, and
nothing fails when the string is wrong.

### 5. What was deliberately not built

- **No local cancel flow.** It would be a second write path into subscription state for the
  webhook to reconcile against. The portal is the one door, and a test asserts no cancel
  control exists.
- **The sidenav account row was left alone.** Its own comment calls it "a control, not a
  route" because `/settings` would 404 — and this item adds `/settings/account`, which is
  plausibly the page it wanted. Repointing a shell component used on every authed screen is
  its own change, approved as out of scope at the checkpoint. **`/settings/account` is
  currently reachable only by typing the URL**, which is a real gap for a later item to
  close.
- **The export sits in its own top-level section**, not nested under the plan. That is
  load-bearing rather than cosmetic: the acceptance criterion forbids gating the export *by
  placement*, and a Pro-shaped block around it would be the same gate wearing a layout.

---

## Work Item: `saved-collections-api`

All seven acceptance criteria met. Two defects found by the tests, one decision made at the
checkpoint that the criteria left open, and one observation about the run's failing baseline.

### 1. The gate is at the API, and the commands stayed tier-agnostic

`services/saved_collections.py` was written in `saved-collections-model` with no notion of a
tier, deliberately, and this item did not change that. The gate is a single
`check_collections_allowed` call at two endpoints. That split is the same one
`quiet-hours-pro-api` made and for the same reason: **the rows are the user's data, and a
command that refused on tier would have to be re-run after an upgrade to restore what the
user already said.**

The payload is `{cap, upgrade_hint}` with no modal-shaped field, so the whole frontend
change is `collections_pro_required` joining `CAP_CODES` — the fourth code to reuse the one
inline prompt, with no new component and no new copy path.

### 2. The checkpoint decision, and why it is pinned in both directions

The criteria name read and unassign as surviving a lapse and create as blocked; rename,
reorder, delete and assign were unspecified. **Only the two operations that add are gated.**

The reasoning is recorded in `collection_cap.py` where someone changing it will see it:
gating rename would stop a lapsed user fixing a typo in a name they wrote; gating delete
would trap them with data they want gone, which is the inverse of what the never-delete
constraint is for; and *not* gating assign would leave the cap limiting how many
collections exist rather than how much they are used.

Two mutations pin it from both sides — the gate spreading to unassign, and the gate
retreating from assign — because a one-sided test would let the boundary drift in the
untested direction.

### 3. Defect: `/order` was unreachable, and the error said nothing useful

`PUT /collections/order` was matched by the `/{collection_id}` rename route, because
django-ninja matches in registration order and a literal segment loses to a path parameter
declared above it. The caller received `405 Method Not Allowed` listing PATCH and DELETE —
an answer about the wrong route entirely.

**This is a class of bug worth naming rather than just fixing**: it is invisible to review
(both routes read correctly in isolation), it only appears when the two are read together in
order, and the error it produces points away from the cause. The fix is a comment plus
ordering, and a mutation that moves it back fails five tests.

### 4. Defect: a client could make the server 500 by sending a short list

`reorder_collections` raised `ValueError` for a list that does not name every collection.
That is the right convention for programmer misuse and the wrong one for a request body —
and this item is precisely what turned that body into user input. A caller sending two ids
for a three-collection list got a 500.

It raises `InvalidCollectionOrderError(ValidationError)` → 422 now. **The underlying lesson
is about the model item, not this one**: a command written as internal-only acquires a new
contract the moment an endpoint exposes it, and its `ValueError`s need re-reading as
possible client input at that point. `create_collection` and `rename_collection` still raise
`ValueError` for an empty name — **unreachable here only because the schema's
`min_length=1` refuses it first**, which is a parser guarantee rather than a service one.
Worth knowing if either is ever called from somewhere without that schema in front of it.

### 5. The failing baseline is growing by itself

The run's pre-existing failures went from 16 to 17 between yesterday and today, with no code
change: `test_a_custom_slot_is_minted` has a fixture hard-coded to `2026-11-12 02:00 UTC`
and a 90-minute lead time that elapsed this morning.

**That is the whole family in miniature.** These tests are not flaky — they are stale by
calendar, they fail deterministically from a fixed date onward, and the count will keep
rising as the fixtures age. Nothing in this run caused them and nothing in this run has
fixed them; they are worth their own item before the number makes a genuinely broken suite
indistinguishable from the expected noise.

---

## Work Item: `frontend-collections`

All nine acceptance criteria met. **This surface was designed during the build**, which the
work item asked to be stated plainly, and the review is largely about what that means.

### 1. Designed during the build — what that actually cost

EXPERIENCE.md's coverage table claims `settings-desktop.html` covers FR-49. TRACEABILITY.md
checked and found *"the mockup contains zero 'collection' content"*. So there was no design
to follow and no design to deviate from.

What held the build to the product rather than to taste:

- **`component.emptystate.quiet`**, used as specified — dashed `border-strong`, centred,
  headline plus lede — so the empty state reads as intentional rather than failed.
- **`tests/spacing-scale.test.ts`**, which rejected four off-scale values. On a surface with
  a mockup this is a tidiness check; here it was **the only automated thing standing between
  "built from the design system" and "built from whatever looked right"**.
- **The existing controls' shapes** — the settings routes' inputs, the inline prompt, the
  `44px` minimum target — reused rather than re-invented.

No new component, no new token, no new visual idea. If this surface grows past a modest
management UI, the work item's stop condition applies and it should get a design pass before
it does.

### 2. The nav constraint shaped the route, and the route is still unreachable

DESIGN.md closes the nav to new routes, with Browse as its single named exception. So
`/settings/collections` was chosen because the sidenav's Settings item matches
`pathname.startsWith("/settings/")` and lights up with no nav change at all.

**But nothing links to it**, exactly as nothing links to `/settings/account` from item 12.
Two new surfaces in this run are reachable only by typing a URL. That is now a pattern
rather than an oversight, and it wants one item: either a `/settings` index that lists the
sub-routes, or the account-menu row repointed — the row whose own comment already calls
itself "a control, not a route" because `/settings` would 404.

### 3. The lapsed user gets a different component, not a disabled one

A lapsed Pro user is served a plain read-only list from the page rather than the manager
with its controls removed. That was deliberate: a manager rendered with every button
disabled tells the user the controls exist and are refused, which is a different and worse
message than *these are yours, and here is how to get the rest back*.

The cost is a second rendering of a collection row — small, and the duplication is three
lines of markup rather than a component that two tiers have to agree about.

### 4. What the mutation probe found worth keeping

Deleting the sentence *"Your saved events stay saved"* leaves the delete working, the
confirmation appearing and one test failing. That is the right ratio: the sentence carries
no behaviour and all of the reassurance, and it is exactly the kind of line a later edit
trims as redundant. It now has a test whose name says why it is there.

### 5. Carried forward from this item

- **Assignment has no surface.** A user can take a save *out* of a collection here, but
  putting one *in* happens through `PUT /collections/{id}/events/{save}`, which no screen
  calls — the saved-events surface that would own that control is `SavedEventsSection`, and
  it is **mounted on no page at all**. So collections can be created, named, ordered and
  emptied, and filled only by an API client. FR-49's "assign" is built and reachable; its
  affordance is not, and the empty-collection copy points at a surface that does not exist
  yet.
- **`SavedEventsSection` being unmounted** is the root of that, and predates this intent.

---

## Work Item: `e2e-proof-and-contract-tests`

All eight acceptance criteria met. **No defect was found in the product**, and the reasons
that is a finding rather than a blank are below.

### 1. Every failure was the test misunderstanding a rule

Six assertions failed before this file went green, and not one of them was the system
breaking a promise. Each was a real rule the proof had to learn: a lapsed account keeps its
unspent Free allowance; weekday windows apply only to Pro; a day's window owns the next
morning; a preference change re-times sends only through the API; `set_plan_slots` mints
nothing without a `send_target`; a send needs the user's zone.

**That is the strongest thing this item can report.** The intent's fourteen prior items each
proved their own piece against their own seam; this is the first time four gates, five
surfaces and the entitlement read ran together, and the loop closed. The place a defect was
most expected — the downgrade, where every item promised "never delete" in isolation — held.

### 2. The test was made to fail on purpose, three times

A proof that has never failed proves nothing about itself. The probes:

- A cancelled subscription still counting as Pro — **3 tests fail**.
- The collections gate never refusing — **2 tests fail**.
- **A cancellation deleting the user's collections** — **1 fails, 13 error**.

The third is the one worth keeping. Every earlier item asserted "never delete" against its
own table, so a downgrade path reaching across apps would have passed all of them; this file
is the first that notices.

### 3. The contract test enumerates routes, and that is deliberate

The repo already had four "the generated client is in sync" tests. **Every one of them would
stay green if a route were deleted** — the client would be regenerated without it and both
artefacts would agree about an API that had quietly lost a feature.

`INTENT_PATHS` names all thirteen paths and their verbs, in **both** directions: a missing
verb is a lost feature, and an extra one is a surface nobody designed. Two of those
assertions are about absences that matter — no `DELETE` on an export (a client that could
delete one could destroy a user's own copy of their data before they collected it) and no
write verb on either entitlement read (only the webhook grants Pro, and that is now a
property of the published contract rather than a convention).

### 4. Every instant is relative, and the reason is in this run's own data

The repository's failing baseline went from **16 to 17 during this run**, with no code
change: a fixture hard-coded to `2026-11-12 02:00 UTC` aged past its lead time overnight.

Nothing in this file can join them. Every instant derives from `timezone.now()`, and where
the save cap needed a deterministic window it is the *throttle's* clock that is pinned, not
a calendar date. **This is now the clearest statement in the tree of what those seventeen
tests should have done**, which is worth something when they are finally fixed.

### 5. What this item deliberately did not do

- **Nothing in `apps/`, `domain/` or `worker/` was modified.** A defect found by a proof is
  a finding, not a patch smuggled into the item meant to measure it.
- **No frontend journey test.** It would mock the API client, so it would prove the
  components agree with a fake rather than with the server this proof exercises. The
  contract test is what actually closes that gap, and the five surfaces have 2030 passing
  tests of their own.

### 6. Carried forward from this item

- **The seventeen stale fixtures** are the one thing in the repository that will keep
  getting worse on its own. They are deterministic, not flaky, and the count rises as dates
  pass. They need an item before the number makes a genuinely broken suite
  indistinguishable from expected noise.
- **Assignment still has no UI** (from `frontend-collections`): this proof exercises
  `PUT /collections/{id}/events/{save}` through the API because no screen calls it.
