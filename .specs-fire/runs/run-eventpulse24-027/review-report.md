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
