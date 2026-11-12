---
run: run-eventpulse24-027
work_item: subscription-model-and-entitlement
intent: pro-tier-and-monetization
date: 2026-11-11
---

# Test Report: Something to be Pro with — the Subscription entity and the one entitlement read

## Result

| Suite | Result |
|---|---|
| New tests for this item | **34 passed** (31 identity + 2 planted violations + 1 allowed import) |
| `tests/identity/` (whole app) | **208 passed** |
| `tests/architecture/` | **919 passed** |
| Full backend suite | **6230 passed, 16 failed** — all 16 pre-existing, see below |
| `ruff check` + `ruff format --check` | clean |
| `import-linter` | **19 contracts kept, 0 broken** |
| `manage.py check` | no issues (3 silenced) |

## Acceptance Criteria

| AC | Status | Evidence |
|---|---|---|
| `Subscription` in `apps/identity`, written only through `identity` commands | met | `TABLE_OWNERS["identity_subscription"] = "identity"`; `test_write_ownership` passes |
| `retention_category = BILLING_RECORDS` | met | `test_the_retention_category_is_billing_records`; `eventpulse.E003/E004` pass |
| Plan, status, period end, customer and subscription refs | met | Model fields; migration `0003_subscription` |
| Status set decided and justified; each maps to one entitlement answer | met | Four statuses, parametrised in `test_each_status_maps_to_one_entitlement_answer` |
| At most one non-terminal subscription per user, DB-enforced | met | Partial unique index; `test_a_user_cannot_hold_two_live_subscriptions` (both live spellings) |
| Never delete | met | `test_no_app_code_deletes_a_subscription` |
| Every transition a named command with `IdentityAuditEntry` | met | `test_starting_a_subscription_grants_pro_and_writes_one_audit_row`, and the action list asserted per command |
| One entitlement read, by value, no relation | met | `is_pro(user_id) -> bool`; two planted-violation tests prove `models-identity` blocks the alternative |
| The read is total (absent row = Free) | met | `test_a_user_with_no_subscription_is_free` |
| Tests cover constraint, mappings, absent row, audit, no-delete | met | 31 tests across three modules |

## Can these tests fail?

Green tests prove nothing until they are shown to fail for the right reason. Two checks were
run deliberately.

**1. The ordering guard was mutation-tested.** `_is_stale` was short-circuited to
`return False` and the suite re-run. Exactly four tests failed, and they are the right four:

```
FAILED test_a_stale_update_after_a_cancellation_does_not_restore_entitlement
FAILED test_a_declined_stale_event_writes_no_audit_row
FAILED test_an_equal_timestamp_with_no_status_change_is_treated_as_a_replay
FAILED test_an_existing_row_untouched_by_a_declined_event_keeps_its_last_event_at
```

The first is the bug the guard exists for — a stale `customer.subscription.updated` restoring
entitlement to someone who cancelled. The guard was restored and the suite re-verified.

**2. One test was wrong and was replaced, not patched.**
`test_write_audit_refuses_to_run_outside_a_personal_transaction` asserted a raise that cannot
happen: `pytest.mark.django_db` already wraps each test in a transaction, so
`connections[PERSONAL].in_atomic_block` is `True` and the guard never fires. It also
duplicated `test_audit.py::test_write_audit_outside_a_transaction_raises`, which does it
correctly with `transaction=True`.

It was replaced by `test_the_commands_open_their_own_personal_transaction`, which uses
`transaction=True`, asserts no atomic block is open *before* the call, then runs the command.
Deleting `transaction.atomic(using=PERSONAL)` from `record_subscription_started` makes it
fail — which is what the original test was supposed to prove and did not.

## The architecture tests caught a real omission

The first full run failed `test_write_ownership.py` twice:

```
AssertionError: tables with no owner in TABLE_OWNERS: ['identity_subscription'].
Every table needs an owner; an unowned table is one nobody is responsible for.
```

A new table had been added without an owner. Registered to `identity`, with the reason
recorded in the map. This was a genuine defect in the implementation, found by the suite
rather than by review.

## Log redaction: checked, no change needed

The plan called for verifying that `stripe_customer_ref` cannot reach a log sink.
`adapters/logging/redaction.py` holds an **allowlist** (`ALLOWED_FIELDS`), so any field not
named in it is redacted — and `stripe_customer_ref` is not named. The value is therefore
redacted by default, with no edit required. Adding it to the allowlist would have been
exactly the wrong move.

Worth noting for item 2: the value scrubber already carries `sk_live`, `sk_test` and `whsec`
patterns, so Stripe's secret-key and webhook-secret shapes are caught in free text too.

## Pre-existing failures on `main` — NOT caused by this work item

The full suite reports 16 failures. **All 16 fail identically on a clean tree.** This was
verified, not assumed: the work was stashed with `git stash push -u`, the same tests re-run,
and the same 16 failed with none of this item's code present. `tests/architecture/test_write_ownership.py`
**passed** on that clean tree, which is how the two genuine failures above were isolated.

| File | Failures |
|---|---|
| `tests/e2e/test_timeline_and_conflict_proof.py` | 9 |
| `tests/e2e/test_save_race.py` | 4 |
| `tests/ingestion/test_url_feed_read.py` | 1 |
| `tests/delivery/test_reminder_plan_api.py` | 1 |
| `tests/e2e/test_personal_events_and_saved_catalog.py` | 1 |

`test_url_feed_read.py::test_a_city_lastmod_is_the_latest_of_its_events` looks
time-dependent — it expects a fixed `2026-11-06T10:00Z` and receives the current instant. The
other fifteen cluster tightly around saves, conflicts and AD-17 propagation, which suggests
one underlying cause rather than five.

**This matters beyond bookkeeping: `main` is not green, and the failures are concentrated in
the e2e proofs** — the tests whose whole purpose is to show the MVP holds together. Run 026
closed with these presumably passing, so something regressed between then and now.

**Recommended: a defect work item for the Planner**, following the `trust-loop` precedent
where a defect found during a proof became a work item rather than a patch inside the run.
It is deliberately not fixed here: it is outside this item's scope, and the diagnosis
(one cause or five) is itself the work.

## Deviations

1. **Equal-timestamp handling**, as flagged at the plan checkpoint. A strictly older event is
   always declined; an *equal* timestamp is declined only when the status is unchanged.
   Pinned by `test_an_equal_timestamp_with_no_status_change_is_treated_as_a_replay` and
   `test_an_equal_timestamp_with_a_different_status_is_applied`.
2. **`shared/constants.py` untouched**, as predicted in the plan. This item introduced no
   threshold or duration; grace timing belongs to Stripe.
3. **`tests/architecture/test_write_ownership.py` modified**, which the plan did not list.
   Required by the new table, and the omission is what the first full run caught.

---

# Test Report: Real Stripe, and the way subscription state gets back in

*(work item: `billing-adapter-and-webhooks`)*

## Result

| Suite | Result |
|---|---|
| `tests/adapters/test_billing_stripe.py` | **28 passed in 0.19s** — no network, no account |
| `tests/identity/test_billing_webhooks.py` | **14 passed** — through the fake, no SDK |
| `tests/adapters/test_fakes.py` additions | **3 passed** |
| `tests/architecture/` | **925 passed** |
| `ruff` + `import-linter` | clean · **19 contracts kept, 0 broken** |

## The seam that made the receiver testable

Signature verification had to move into the adapter, because the `stripe-sdk` contract lists
`apps` as a forbidden source and `stripe.Webhook.construct_event` is therefore unreachable
from an endpoint. That constraint turned out to be a gift: `FakeBillingAdapter` implements
`parse_event` too, so **every receiver test runs with no SDK, no signing secret and no
network** — dispatch, the 200/400 discipline, ordering and attribution all exercised against
a body shape the test writes in plain terms.

The real signature path is still tested for real: `stripe.Webhook` computes an HMAC locally,
so `test_billing_stripe.py` builds a correctly-signed payload and exercises the SDK's actual
verification, not a stand-in for it. That is why a tampered payload and a re-serialised
payload both fail verification in tests rather than in theory.

## Tests that pin a specific mistake

| Test | The mistake it prevents |
|---|---|
| `test_reserialising_the_payload_breaks_verification` | Parsing the body before verifying it. Semantically identical JSON with different whitespace does **not** verify — which is why the receiver passes raw bytes through. |
| `test_the_receiver_reads_the_mapped_status_not_the_providers_own` | Acting on `raw_status`. The body carries a provider string that is not one of ours; reading the wrong field would fall back instead of cancelling. |
| `test_an_unknown_status_survives_a_whole_parse` | A 500 on every delivery because Stripe added a status. |
| `test_a_stale_change_after_a_cancellation_does_not_restore_entitlement` | The out-of-order bug, asserted **end-to-end through the endpoint**, not only at the command level where item 1 pinned it. |
| `test_a_completed_checkout_with_no_user_is_not_silently_discarded` | A user charged and never made Pro, with nothing in the log to say so. |
| `test_checkout_carries_the_user_id_as_metadata` | The cross-item contract with `checkout-and-portal-api`, pinned here so item 3 cannot quietly drop it. |
| `test_the_adapter_is_constructible_with_no_arguments` | A constructor the port's own registry cannot call. |
| `test_the_refusal_explains_nothing` | A 400 body that tells a prober signature verification is what failed. |

## Defects found during the build

**1. The adapter was unreachable through its own port.** `ports.registry.get_adapter`
constructs every adapter with **no arguments**; `StripeBillingAdapter.__init__` required three.
Rewritten to `HttpRevalidationAdapter`'s shape — all optional, resolved from settings lazily,
SDK client built on first use so importing the module does not require a key.

**2. The status mapping was written and never called.** The adapter set `raw_status` to
Stripe's unmapped string while the receiver treated it as already mapped; `mapped_status()`
existed and no code path reached it. `BillingEvent` now carries both fields with distinct
jobs — `status` is ours and is acted on, `raw_status` is the provider's and is for logging
only — and a test pins which one the receiver reads.

**3. A bespoke error body disclosed more than the house one.** The first version returned
`{"code": "invalid_signature"}`. `config/errors.py` maps 400 to a fixed *"That request
couldn't be read."* under a comment reading *"their own text is not shown"*. Switching to
`HttpError(400)` means the response does not reveal that signature verification failed at
all, and `raise ... from None` keeps the provider's verification message out of any
traceback. Strictly less disclosure than what was written first.

**4. Two architecture guards caught the new surface.** `test_no_direct_writes` and
`test_digest_composition_separation` each maintain an explicit list of request modules, and
the first says plainly that *"a surface file that is missing from this list is exempt from
AD-5, and nothing else would catch it."* `apps/identity/webhooks_api.py` is registered in
both. A payment provider being the caller changes nothing about who may write.

## A pre-existing CI defect, found and fixed

`ci.yml`'s env block describes itself as *"Test-only configuration for `config.env`"*, but
was **two settings short of what `config.env` requires**. Verified empirically rather than by
reading: reconstructing CI's exact environment with no `.env` file reported

```
MISSING REQUIRED: ['calendar_credential_key', 'revalidation_secret',
                   'stripe_api_key', 'stripe_webhook_secret']
```

Two were this item's; `calendar_credential_key` and `revalidation_secret` predate it, meaning
**Django could not boot in CI at all**. All four are now in the env block, and the check was
re-run against the real `ci.yml`: it boots clean.

The same gap existed in `tests/config/test_env.py` (`REQUIRED`) and
`tests/config/test_databases.py` (`make_env`), both of which build settings from a minimal
explicit set. Both extended.

## This item does not deliver go-live, and a test says so

`billing` joins `REAL_ADAPTERS`, but `ADAPTER_MODE=real` still refuses to boot: `llm`,
`embedding` and `email` remain without real adapters. The assertion in
`tests/config/test_adapters.py` now reads *"no real adapter for email, embedding, llm."* —
one name shorter than before, and still a refusal. The comment in `config/adapters.py` was
updated to say the Stripe and ICS adapters have landed and the LLM gateway and email provider
have not.

## A regression this item caused, and nearly shipped

The first full-suite run after implementation returned **21 failed**, not the pre-existing 16.
All five extras were this item's: API contract tests failing with *"the generated client is in
sync with the document"*. Adding `/webhooks/billing` changed the OpenAPI document, and
`frontend/lib/api/schema.ts` had not been regenerated against it — **the exact acceptance
criterion written for this item**, and skipped.

It is worth recording *how* it nearly slipped through. `tests/api/test_contract.py`
**passes in isolation** and fails only alongside the other contract tests. Spot-checking that
one file — the obvious thing to do after touching the API — would have shown green and the
item would have been committed with a broken client contract.

Fixed with `make client` under Node 24 (`.nvmrc`; a login shell defaulting to Node 20 kills
every Vitest file in undici). The document gained exactly the new endpoint and its response
schema and nothing else: `openapi.json` +47 lines, `schema.ts` +60.

**Final full suite: 16 failed, 6282 passed** — the pre-existing 16 exactly, no contract
failures.

**Carried to every remaining item that adds an endpoint:** run `make client` in the same run,
and trust only the full suite to confirm it. Items 3, 6, 8 and 9 all add endpoints.

## Deviations

1. **No idempotency table**, as the design decided. Item 1's row guards cover replay and
   ordering, and both are now asserted through the endpoint as well as at the command level.
2. **`PAYMENT_FAILED` is its own event kind**, not a change carrying a status. Stripe does not
   say what the subscription became, so the receiver does not guess — it records `past_due`,
   which keeps a paying user entitled while dunning runs.
3. **`.env` was modified** (not only `.env.example`), because the required settings must be
   present for a local run. The values are placeholders of the right shape and are not
   credentials.
4. **`frontend/lib/api/openapi.json` and `schema.ts` regenerated**, which the plan's file list
   did not name. Required by the new endpoint; the omission is what the regression above was.

---

# Test Report: Checkout and portal endpoints

*(work item: `checkout-and-portal-api`)*

## Result

| Suite | Result |
|---|---|
| `tests/identity/test_checkout_portal_api.py` | **24 passed** — through `FakeBillingAdapter`, no provider, no network |
| `app/dev/fake-billing/**` (Vitest) | **13 passed** across 2 files |
| `tests/architecture/` | **933 passed** |
| Full backend suite | **16 failed, 6312 passed** — the pre-existing 16 exactly |
| Full frontend suite | **1823 passed** (109 files) |
| `ruff` + `import-linter` | clean · **19 contracts kept, 0 broken** |
| `eslint` + `tsc` + `prettier` | clean |

## The property these tests exist to protect: the endpoints grant nothing

**A checkout that completes changes nothing by itself.** The endpoint mints a session and
returns a URL. It writes no `Subscription`, no audit row, no entitlement — and the user is
still Free afterwards. Only the provider's webhook moves the subscription.

This is the criterion most easily lost to a well-meaning convenience. An endpoint that
"helpfully" marked the user Pro on the redirect would pass every obvious test and break the
product in production, where the redirect is under the client's control. So the tests pin it
from both sides: the endpoint itself
(`test_a_checkout_grants_nothing`), and the browser's side of it
(`test_returning_from_a_successful_checkout_leaves_the_user_free`).

**A cancelled row is history, not a live subscription.** `test_a_cancelled_subscription_does_not_block_a_new_checkout`
pins that a user who cancelled may buy again — otherwise the refusal in the next paragraph
would quietly become a one-way door.

## The refusals are about the account's state, not the request's shape

Both are 409s, and both are decided **before** the provider is called:

| Account state | Endpoint | Answer |
|---|---|---|
| Already holds a live subscription | `/api/billing/checkout` | 409 `already_subscribed`, pointing at `portal_path` |
| Holds no subscription | `/api/billing/portal` | 409 `no_subscription` |

`test_the_portal_refusal_happens_before_the_provider_is_called` swaps the billing port for
one that raises on any call and asserts the call list is empty. This matters beyond
correctness: a provider error about a customer that does not exist would be *leaky* — it
would confirm the account's state to whoever asked.

`test_a_user_who_is_already_pro_is_still_pro_after_the_refusal` pins that a refusal does not
disturb the entitlement that already exists.

## The redirect URLs cannot be supplied by the client

The request body carries **only** `plan`. There is no `success_url`, no `cancel_url`, no
`return_url` field anywhere in the schema — and that absence is the security property rather
than an oversight.

Two tests hold it down from different directions:

- `test_both_urls_are_handed_to_the_port` — the success *and* the cancel URL are both
  derived from configuration. The fake adapter puts only the success URL in the returned
  link, so the cancel URL is observable only at the port boundary, which is where the rule
  lives. This is the test that would fail if either URL were taken from the request.
- `test_a_client_supplied_success_url_is_ignored` — a crafted `success_url` in the body is
  ignored, and the attacker host appears nowhere in the returned URL.

The generated schema confirms it structurally: `CheckoutIn` has exactly one property,
`plan`, and `required` is `["plan"]`. A URL field could not be added without changing the
published contract.

## The dev stand-in

`frontend/app/dev/fake-billing/` holds two pages and one shared panel. The tests pin the
contract with `FakeBillingAdapter` — the query parameters `session`, `plan` and `next` — because
a rename on either side silently breaks the local paid path: the page would still render,
just with an empty session and an unknown plan.

- It is obviously a stand-in: every page carries a visible "Development stand-in" banner,
  and the pages `notFound()` in a production build.
- It can simulate **both** outcomes, so the local paid path and the local abandoned-checkout
  path are both walkable. The portal offers a cancellation too, because the local path that
  exercises item 2's `subscription_ended` webhook starts there.
- It says that completing does not grant Pro, and points at the webhook that does. A page
  that said otherwise would teach the wrong thing about how the product works.

## Two defects the tests found

**`RawPostDataException` — a 500 that was my own fault, twice over.** The first run of the
contract tests returned 500 on every POST. The cause was the *test client's* defaults, not
the endpoint: setting `client.defaults["CONTENT_TYPE"] = "application/json"` changes how
Django encodes the body, so Django's CSRF middleware reads the request stream that Ninja
later wants to read again. The established pattern in
`tests/personalization/test_personal_events_api.py` passes `content_type` **per request** and
never in `defaults`; the helper now does the same, and the docstring says why, so the next
person does not rediscover it.

**A monkeypatch that patched the wrong name.** The port-recording test asserted
`seen["customer_ref"] == "cus_stored"` and failed with `KeyError`. The service did
`from ports.registry import get_billing_port`, binding the function into the service
module's namespace at import time — so patching `ports.registry.get_billing_port` rebound
the registry's attribute and left the service calling the original. The service now imports
the *module* and looks the port up at call time (`registry.get_billing_port()`), which is
both patchable and honest about when the lookup happens.

**The third failure was a test's own blind spot.** `test_the_success_and_cancel_urls_come_from_configuration`
asserted `"settings/billing" in url`, but the fake adapter percent-encodes the query string,
so the path appears as `settings%2Fbilling`. The behaviour was correct and the assertion was
not; the assertion now matches the encoding.

## The architecture tests caught the new surface file — twice

Adding `apps/identity/billing_api.py` broke two architecture tests, and **both were right**:

- `test_no_direct_writes.py` asserts the number of surface files, because a surface file
  missing from that list is **exempt from AD-5** and nothing else would catch it. The count
  went 20 → 21 and the new module is named explicitly.
- `test_digest_composition_separation.py` keeps a hand-written list of request modules so
  the discovery can be checked against it. `apps/identity/billing_api.py` was added.

Neither was noise. The new module *is* a request handler, and it now sits inside both guards
alongside every other endpoint.

## The client was regenerated in the same run

Item 2's report recorded a regression this item could have repeated: adding an endpoint
changes the OpenAPI document, and `frontend/lib/api/schema.ts` must be regenerated against
it or the contract test fails. `make client` was run under Node 24 (`.nvmrc`) — the login
shell defaults to Node 20, which kills every Vitest file in undici.

The document gained exactly the two endpoints and three schemas and nothing else:
`openapi.json` +175 lines, `schema.ts` +203.

## Pre-existing failures — NOT caused by this work item

**16 failed, 6312 passed.** The same 16 the previous item reported, verified by stashing this
work and re-running the affected files on a clean tree — an identical 16:

- `tests/delivery/test_reminder_plan_api.py` (1)
- `tests/e2e/test_personal_events_and_saved_catalog.py` (1)
- `tests/e2e/test_save_race.py` (4)
- `tests/e2e/test_timeline_and_conflict_proof.py` (9)
- `tests/ingestion/test_url_feed_read.py` (1)

None of them touch billing, identity entitlements or the API surface this item changed. They
predate it and remain open.

## Deviations

1. **`frontend/lib/api/openapi.json` and `schema.ts` regenerated**, which the plan's file
   list did not name. Required by the two new endpoints — and, as item 2's report records,
   the exact omission that caused a regression there.
2. **Two architecture tests modified** (`test_no_direct_writes.py`,
   `test_digest_composition_separation.py`), which the plan did not list. Both assert on the
   set of surface files, and the new module changes that set. Neither modification weakened a
   guard: both now name the new file explicitly.
3. **The service looks the billing port up at call time** (`registry.get_billing_port()`)
   rather than binding the function at import time. This was not a stylistic choice — it is
   what makes the port boundary substitutable in a test, and the test that substitutes it
   caught the mistake.
4. **A test file asserts against the percent-encoded URL** (`settings%2Fbilling`). The
   encoding is the adapter's, and asserting on the decoded form would have made the test
   depend on a decoding step the endpoint does not perform.

## The review found a hole in the dev page's own rule

The code review caught something the contract tests could not: **the dev page honoured a
`next` on any host.** The page read `next` from the query string and used it as the `href`
of the "Complete checkout" link, and a query string is attacker-controllable by anyone who
can hand a developer a link. `?next=https://attacker.example` produced a link that sends
the user off-site.

This is the same open-redirect the backend refuses to allow — and the backend's refusal is
one of this item's acceptance criteria. Leaving the dev page as the one place in the
codebase where a redirect target *is* taken from a request would have put a hole in the
rule the rest of the item is built on. The app's own posture agrees: every other redirect
in this codebase is a hardcoded path, never a URL.

The fix mirrors the backend's rule — a `next` naming a path on this origin is honoured, a
same-origin absolute URL is reduced to its path, and anything else is refused outright with
no link rendered. Three tests went with it: a target on another site renders **no link at
all**, the same-origin success URL keeps its query string, and the portal's return-URL
test now asserts the path rather than the whole URL.

**The frontend suite grew from 1823 to 1826 tests, and every one still passes.**

---

# Test Report: Free-tier caps and the entitlement read

*(work item: `free-tier-caps-read-entitlement`)*

## Result

| Suite | Result |
|---|---|
| `tests/personalization/test_save_cap.py` | **16 passed** |
| `tests/personalization/test_calendar_provider_cap.py` | **13 passed** |
| `tests/adapters/test_throttle.py` | **9 passed** — added by the code review |
| `tests/personalization/ tests/adapters/ tests/identity/ tests/api/` | **2126 passed** |
| Full backend suite | **16 failed, 6358 passed** — the pre-existing 16 exactly |
| Full frontend suite | **1826 passed** (109 files) |
| `ruff` + `import-linter` | clean · **19 contracts kept, 0 broken** |
| `eslint` + `tsc` + `prettier` | clean |

This item added **38 tests** (16 + 13 + 9). The failure count is **unchanged at 16** — the
same sixteen test names as the baseline, verified by stashing the work and re-running the
whole suite into a comparison file and diffing the two name lists. No existing test was
broken.

## The gate is the port's, and the port says the window is fixed

The acceptance criterion is that the cap is declared through `ThrottlePort.check(key,
limit, window_seconds)`, exactly as `EventReport` declares its own — not hand-rolled, and
not a count of rows. Two tests pin that: one records the call and asserts the key is
`save:{user_id}` and the limit and window are the constants from `shared/constants.py`; the
other asserts that **unsaving an event does not hand the allowance back**, which a row
count would have done.

That second test is the one that matters. A row count would make the cap depend on data
the user can delete: unsave, save again, and the allowance would never run out. The
throttle port counts the *attempt*, so the refusal stands even though the row is gone.

**Writing it turned up a real defect in the test double.** The port's contract is
explicit — *"The window is fixed: the count resets `window_seconds` after the first
attempt in it"* — and the Redis adapter implements exactly that (`EXPIRE` is set only when
the count is 1). But the in-memory adapter was **sliding**: it dropped any attempt older
than `window_seconds` before each decision, so the window slid from the *last* attempt.

Two consequences, and the second is the serious one. A refusal could extend the user's
wait, which is the opposite of what the criterion requires. And a client could keep a
bucket alive for ever by attempting just often enough — a limit that can be held open
indefinitely is not a limit. The adapter's own docstring already said "fixed window"; the
code did not do it.

**The in-memory adapter now implements the port's contract**: the window is anchored at the
first attempt, and every attempt made since it counts, refused ones included. The
consequence is the property the criterion asks for — a refused save costs the user no
time, because a refusal does not move the anchor.

**No existing test broke.** The four suites that use the adapter — the auth throttle, the
event reports, the preview API, and the trust-loop proof — were re-run and all pass
unchanged, because their existing boundary test advances the clock past the window from the
first attempt, which both window shapes answer the same way.

## The adapters now have a test of their own — `tests/adapters/test_throttle.py`

The defect above survived because **neither throttle adapter had a test of its own.** The
in-memory one was only reached indirectly, through app-level tests that stub the port out;
the Redis one — the adapter production actually runs — had no test at all. So the port's one
stated rule was implemented twice and pinned by neither.

The new file has **9 tests**, in two halves.

**The rule, on the in-memory adapter, at the boundary.** The window opens with the *first*
attempt, so it closes at `first + window_seconds` — not at `2 × window_seconds`, which is
what an anchor at the *last* attempt would give. A refused attempt does not move the anchor.
And the window does not slide: a client that keeps attempting holds its bucket open under a
sliding window, and the test walks exactly that case.

**The parity, between the two adapters.** The same calls go to both, and the decisions must
match. The Redis adapter runs against an in-memory stand-in that **deletes expired keys**,
because that is what real Redis does and it is the behaviour the window rule depends on — a
stand-in that kept an expired key would have made the parity test test the stand-in rather
than the adapter.

**The parity was verified by hand before the test was written**, over a walk that crosses the
boundary: `t = 0, 10, 50, 99, 100, 101, 150, 199, 200, 201` — **0 mismatches**, including
at the exact boundary.

An earlier run of that walk reported mismatches at t=100 and t=200. Those were the stub's
fault, not the adapters': the first version kept expired keys and so believed a closed
window was still open. The stub was corrected and the parity re-verified. It was worth
chasing rather than writing off, because "the two adapters disagree about the same call" is
precisely the failure the fake exists to prevent.

**The tests are load-bearing, and that was checked rather than assumed.** Reverting the
adapter to its old sliding implementation and re-running the file:

```
5 failed, 4 passed
```

The three rule tests and both parity tests fail against the old behaviour; the adapter was
then restored and the file passes 9/9. A test that cannot fail is not a test.

## A refused save changes nothing

The criterion is that a refusal leaves no partial `SavedEvent` and consumes no throttle on
a save that did not happen. Two tests pin it: the row count is unchanged after a refused
save, and **the audit log carries no row for it**. The audit assertion is the stricter one
— an audit row saying "we refused to save" would be a record of a save that never
happened, and the gate refuses inside the transaction before any write, so there is no
command to audit.

## Pro has no cap, and the gate is skipped rather than made infinite

FR-49's own testable consequence is that **a Pro user saves 10+ events in one day with no
soft wall**; the test saves twelve and asserts every one is a 201.

The stronger test is that **a Pro user's saves spend no throttle slot at all**. The gate
is skipped entirely rather than being made with a limit of infinity, so a Pro user's saves
leave no trace in the counter. The test replaces the throttle with a recorder and asserts
the recorder was never called — which is a stronger statement than "the limit was high
enough", and one a limit-of-infinity implementation would fail.

## The tiering follows the tier, read at the moment of the act

Four tests walk the same user through the tiers:

- a **Pro user who lapses back to Free** is refused again;
- a **Free user who becomes Pro** is allowed again — the cap follows the tier, not the
  account, which is the whole point of the gate;
- the **provider cap's payload names the tier's own cap** — `1` for Free, `3` for Pro — so
  the frontend can say what the account *would* allow rather than a number that never
  changes;
- a **Pro user connects a second and a third provider** and is refused a fourth.

One of these tests had to be written twice, and the first version was wrong about the
product. It asserted that a lapsed Pro user's *next* save is refused. It is not, and
should not be: **a Pro user's save never reached the gate**, so no slot was spent on it,
and the lapsed user's first *gated* save is their first. The test now says that, and
asserts the second one is refused — which is what "refused again" means.

## The reuse path, at both caps

The criterion is that the reuse path — a `needs_reconnect` row flipped back to `active` —
still behaves correctly under the raised cap. Three tests cover it: it reuses the row
rather than duplicating it, under the Free cap and under the Pro cap; and **it does not
get a free pass**, so a Free user who already holds an active calendar and has a revoked
one is still at the cap and is refused.

That last one is the subtle case, and it is the one the criterion is really about. The
reuse row is already counted, so it does not add a slot — but skipping the check on this
path would let a user end up with two active calendars on a one-calendar plan.

## The refusal payload is the same shape for both caps

The criterion pins the payload to the shipped `CalendarProviderCapReached` shape: an
`upgrade_hint` sentence and **no modal-shaped field**. The key set is asserted exactly —
`{"cap", "upgrade_hint"}` — so a future edit that grows a `modal`, `title`, `actions` or
`dismissable` field fails the test rather than shipping.

Both caps now speak one language to the frontend: a number and a sentence. The two
schemas are separate types with the same shape, so the frontend renders one prompt
component for both.

## The contract carries both 409s, and the frontend narrows on the code

The save endpoint answers 409 for two different reasons — a clash (FR-58) and the cap
(FR-49) — with different `details`. A route may declare only one schema per status code,
so the two shapes are joined in a **discriminated union on `code`**:

```
"409": { "oneOf": [ {"$ref": ".../SchedulingConflictOut"}, {"$ref": ".../SaveCapOut"} ],
          "discriminator": { "propertyName": "code",
                             "mapping": { "save_cap_reached": ".../SaveCapOut",
                                          "scheduling_conflict": ".../SchedulingConflictOut" } } }
```

The discriminator is the field the frontend already branches on, so a client generated from
the document can read `details.cap` and `details.upgrade_hint` on one branch and
`details.conflicts` on the other, without guessing. The calendar connect endpoint's 409
is the only one on its route, so it needs no union and is narrowed to `CalendarCapOut`
directly — which also means a generated client can read its `cap` field, where before it
was an untyped dictionary.

**The typecheck caught the one place the frontend reads that 409.** `detail-actions.tsx`
read `response.error?.details?.conflicts?.[0]`, which the union correctly refuses: `details`
may be the save-cap shape. The fix is the narrowing the contract was designed for — the
client checks `error.code === "scheduling_conflict"` before reading `details.conflicts`.
The frontend's behaviour is unchanged, because a save-cap refusal was never a clash and was
already handled by the failure branch.

## Deviations

1. **`backend/apps/personalization/schemas.py` and `backend/apps/personalization/api.py`**
   gained the two cap schemas and the union, which the plan's file list named only as
   "the save endpoint's response map gains the new refusal". The narrowing of the
   *calendar* endpoint's 409 is a step further than the plan described, and it is what lets
   a generated client read `details.cap` at all.
2. **`backend/adapters/throttle/memory.py` was changed** — it now implements the port's
   stated fixed-window contract instead of a sliding one. This was not in the plan, and it
   is a shared piece of infrastructure; the four suites that use it were re-run and none
   broke. It is recorded here because it changes behaviour for every throttle caller.
3. **`frontend/components/detail/detail-actions.tsx` was changed** — the narrowing on
   `code`, required by the typecheck. The plan noted that `frontend-upgrade-prompts` owns
   the *rendering* of a save-cap refusal; this change is not that rendering. It is the
   narrowing the new contract forces on a client that reads the 409, and it leaves the
   save-cap refusal on the existing failure path — which is what the plan said the
   frontend should do for now.
4. **`frontend/lib/api/openapi.json` and `schema.ts` regenerated**, which the plan's file
   list did not name — and which is the exact omission that caused a regression in item 2.
5. **`backend/tests/adapters/test_throttle.py` was created by the code review**, not by the
   plan. It is a test file, so it adds no behaviour — but it is the first test either
   throttle adapter has had, and it is what pins the window rule that finding 2 of the
   review turned up. It was written after the implementation and after the suites had
   already passed, so it changed no result above; it changed only what a future edit to the
   adapters could get away with.

## What this item does not deliver

**The save-cap refusal renders as a generic failure on the Detail Screen.** The payload is
here, the contract is here, and the frontend today shows "Couldn't save that" — which is
true, and is what `frontend-upgrade-prompts` (still `pending`) exists to replace with the
inline prompt the copy was written for.

**`frontend/app/settings/billing` does not exist yet.** The backend's success, cancel and
portal-return paths and the 409's `portal_path` all point at it.
`frontend-account-and-billing-settings` — also `pending`, and a dependency of this item —
builds it.


---

# Item 5 — `frontend-pricing-page`: the pricing screen, one screen, no upsell

**FR-48:** *"Pricing page is a single screen; no upsell copy beyond 'fewer interruptions, more
control.'"* The design exists as `pricing-page-desktop.html`; there was no `/pricing` route in
`frontend/app/`. This item builds the screen, the route, and the one HTTP read it needs.

## The test files

| File | Tests | What it pins |
| --- | --- | --- |
| `frontend/tests/pricing-a11y.test.tsx` | **6** | The axe-core gate, over all three visitor states |
| `frontend/components/pricing/pricing-page.test.tsx` | **24** | The prices, the copy, the three states, the layout |
| `frontend/components/pricing/choose-plan-button.test.tsx` | **8** | The buy button's four outcomes |
| `frontend/app/pricing/page.test.tsx` | **8** | The route's session rules |
| `frontend/lib/return-path.test.ts` | **10** | The open-redirect guard |
| `backend/tests/identity/test_billing_subscription_api.py` | **11** | The entitlement read |
| **Total new** | **67** | |

The pre-existing suites, re-run after every change:

| Suite | Result |
| --- | --- |
| Full frontend suite | **1885 passed** (114 files) — no failures |
| Full backend suite | **16 failed, 6369 passed** — the pre-existing 16 exactly |
| `pnpm typecheck` | clean |
| `pnpm lint` | clean |
| `pnpm format:check` | clean |

**The backend delta is +11 passed, 0 failed.** The baseline recorded by item 4 was
*16 failed, 6358 passed*; this item is *16 failed, 6369 passed*. The difference is exactly the
eleven new subscription-read tests, and the sixteen failures are the same sixteen —
`test_save_race.py`, `test_timeline_and_conflict_proof.py`, `test_reminder_plan_api.py`,
`test_personal_events_and_saved_catalog.py`, `test_url_feed_read.py` — none of which touch
billing. They were failing before this item and are failing after it.

## The no-upsell rule is asserted as an allowlist, not a blacklist

The criterion is *"no upsell copy beyond 'fewer interruptions, more control.'"* The first
version of the test was a **banned-word list** — eleven phrases that would count as
pressure. That is a tripwire, not the rule: any upsell phrase outside those eleven words
slips past it, and a second tagline written well would pass.

So the test asserts the **allowlist** instead. The Pro card's prose is FR-48's sentence and
the feature list, and nothing else:

```tsx
const prose = [...card.querySelectorAll("[data-tagline]")]
  .map((node) => node.textContent?.trim() ?? "")
  .filter((text) => text !== "");

expect(prose).toEqual(["Fewer interruptions, more control."]);
```

**`data-tagline` marks the marketing copy.** The cards also carry *state labels* — "You're
on Free", "Free, without Pro" — which are facts about the visitor rather than salesmanship,
so they are not taglines. A second `<p>` of marketing prose in either card fails the test.

**The guard was proved by mutation, not by assertion.** A paragraph reading "The best choice
for busy people." was added to the Pro card; the test failed with `expected [ …(3) ] to
include 'The best choice for busy people.'`; the mutation was reverted. A test that cannot
fail is a test that has been switched off, and this one is the only thing standing between
the page and a second tagline.

The banned-word list was **kept**, alongside the allowlist, because it names the specific
ways this page could go wrong that an allowlist would not: a countdown, a scarcity badge, a
"limited time" — the sort of copy that arrives in a string rather than a sentence. The
trust strip's own promise ("No 'limited time!' copy.") is excluded before the scan, because
the promise names the phrase in order to disown it.

## Three visitor states, and the three are three documents

The criterion asks for tests over signed out, Free and Pro. They are audited separately,
because they are separately different documents:

- **Signed out** — a link to sign-in, and **no request is made**. A visitor with no session
  cannot buy, and the answer is the sign-in route rather than a failed call.
- **Free** — the buy button, the monthly/annual radio group.
- **Pro** — the portal button, and **no buy button at all**. A second buy button for
  somebody who already pays is a control that cannot work.

The Pro state is also the reason the page needs a read the checkout did not have. A Pro user
whose page was rendered before their plan landed would be shown a buy button, and the
server refusing that click is the only thing that catches it — so a 409 swaps the page to
its Pro state rather than showing a failure.

## The one entitlement read

There was no way to ask "is this user Pro?" over HTTP. The two actions both have side
effects: the checkout refuses with 409 for a Pro user (so they are shown a buy button that
cannot work), and the portal 409 mints a real provider session (so opening the page would
create billing sessions as a side effect of reading it). Neither can be used as a read.

So the backend gained **`GET /api/billing/subscription`**, returning `{is_pro}` and nothing
else — no user id in the request and none in the response, because the user comes from the
session, so a caller cannot ask about somebody else. It is implemented over the one
published entitlement function, `is_pro`, so the page and the caps cannot disagree: a
`past_due` subscriber reads as Pro, exactly as `is_pro` says, and a missing row reads as
Free.

**The read is tested for what it must not do.** Beyond the three entitlement states, the
eleven tests assert that the read **calls no provider** (against a billing adapter that
explodes if touched), **writes no row**, and **writes no audit entry**. A read that
recorded something would make the page load a write, and "the page loaded" would become a
thing that can fail a user's account.

## The read that failed to be read: `next` was a dead end

**This was the code review's one HIGH finding, and it was a real defect.**

The plan asserted that "the sign-in route takes a `next` parameter" and the implementation
inherited the assumption without checking. It did not: `/signin` took no `searchParams`, and
`SigninForm` did `router.replace("/")`. So the pricing page's "Sign in to buy" link carried
`/signin?next=%2Fpricing` — a parameter the destination ignored. A visitor who chose a
plan, was asked to sign in, signed in, and landed on the home page had lost their intent,
and nothing said so.

The fix was a **guarded** `next`, because a redirect target read from a query parameter is
an open redirect:

```
frontend/lib/return-path.ts
  returnPath(next)  →  "/pricing", or "/" for anything that is not a plain local path
  signInUrl(path)   →  "/signin?next=%2Fpricing"
```

`returnPath` rejects an absolute URL, a protocol-relative `//` URL, a backslash, a scheme
(`javascript:`, `data:`), a relative path, and a non-string. Nine tests pin those, and the
`/signin` page and `SigninForm` were changed to honour what survives the guard. **The
`/signin` route's own existing test already had the open-redirect case** — "refuses to
redirect to somewhere off this site" — and it had been passing against a route that could
not redirect anywhere at all. It passes for the right reason now.

## The page is public, and an unavailable session is not "signed out"

`lib/session.ts` is explicit that "sending a signed-in user to the anonymous preview because
the API blinked would be a lie about who they are." The route has three session kinds and
they do not collapse:

- **anonymous** → the `signed-out` state: the tiers, and "Sign in to buy". **The entitlement
  read is skipped entirely** — there is nobody to read it for, the endpoint would answer
  401, and asking would be a pointless request.
- **unavailable** → the page still renders, with the checkout button, and **no** "Sign in to
  buy". The visitor's identity is unknown, so the page does not claim they are signed out.
- **signed-in** → the entitlement read decides Free or Pro.

When the entitlement read itself fails, the page shows the **Free** state — "the honest
direction to be wrong in". If the visitor is in fact Pro, the checkout refuses with 409 and
the page swaps itself. A page that failed to render because the API blinked would be a worse
answer than a page that is briefly one state behind.

## The axe gate

The pricing page is a new public surface, and every public surface in this project carries
an axe gate. `frontend/tests/pricing-a11y.test.tsx` audits **all three visitor states** plus
the annual option, over `document.body` rather than the screen alone — auditing the screen
alone would miss the shell's landmarks. `color-contrast` is disabled explicitly (jsdom
computes no layout, so the rule reports false positives rather than findings; the contrast
requirement belongs to `tests/contrast.test.ts`, which checks the tokens).

**The gate can fail.** A `<ul>` whose `<li>`s were replaced by `<div>`s is the mutation this
page is most likely to develop — a layout edit that silently breaks the feature list's
semantics. The `list` rule is serious, so the gate's own filter catches it, which is
exactly what the "can fail" test asserts.

## The spacing scale and the design tokens

The first run of the repo's own `tests/spacing-scale.test.ts` failed on three classes this
item introduced: `py-0.5`, `px-2.5` and `px-2.5`. The spacing scale is exactly
`0 1 2 3 4 6 8 12 16 20 30`, so `0.5` and `2.5` are not on it. They became `px-2` and no
vertical padding, and the suite passes.

## Deviations

1. **`backend/apps/identity/billing_api.py`, `schemas.py` and `services/billing.py` gained
   the entitlement read**, which the plan's file list did not name — the plan assumed the
   frontend could already learn a visitor's tier. It could not, and the review confirmed the
   read was the right shape: a new `GET /api/billing/subscription` returning `{is_pro}`,
   implemented over the existing `is_pro` so there is still exactly one definition of "Pro".
2. **`frontend/lib/return-path.ts` was created by the code review**, not by the plan. It is
   the open-redirect guard the `next` parameter needs, and it was missing from the plan
   because the plan did not check whether `next` was honoured at all.
3. **`frontend/app/signin/page.tsx` and `frontend/components/auth/signin-form.tsx` were
   changed** to honour a guarded `next`. Neither is named in the plan's file list; both had
   to change for the pricing page's sign-in link to mean anything.
4. **`frontend/components/shell/account-menu.tsx` and
   `frontend/components/pre-auth/pre-auth-footer.tsx` gained a Pricing link**, for the
   "reachable from navigation" criterion. The sidenav's six routes are locked, so the link
   is a quiet one in the account panel and a real one in the pre-auth footer.
5. **`frontend/lib/api/openapi.json` and `schema.ts` regenerated** — `make client`, for the
   new endpoint. The same omission as in item 2, and the reason the frontend's read could
   not have been written without it.
6. **`frontend/tests/pricing-a11y.test.tsx` was created by the code review**, which found
   that this new public surface had no axe gate while every other one did.

## What this item does not deliver

**The page does not know the visitor's tier until the server reads it.** The tier is read
per request — `export const dynamic = "force-dynamic"` — because a prerendered page would
bake one visitor's tier into a page whose whole job is to tell them apart.

**`frontend/app/settings/billing` still does not exist.** The backend's success, cancel and
portal-return paths and the 409's `portal_path` all point at it.
`frontend-account-and-billing-settings` — still `pending` — builds it.

**The upgrade prompts are not here.** A Free visitor who hits a cap is told the cap, not
offered the upgrade; `frontend-upgrade-prompts` — still `pending` — is what writes that
copy.

---

## Work Item: `frontend-upgrade-prompts`

**28 new tests. Frontend 1913 passed / 116 files, from a 1885 / 114 baseline. No backend
change, so no backend run and no `make client`: this item adds no endpoint and touches no
schema.**

| File | Tests | What it pins |
|---|---|---|
| `frontend/lib/cap-details.test.ts` | 11 | Both cap payloads; the six not-a-cap shapes; the hint read verbatim; no modal-shaped field is ever read |
| `frontend/components/upgrade/upgrade-prompt.test.tsx` | 9 | The sentence verbatim; `/pricing`; no dialog/overlay/focus theft; `role="status"` not `alert`; no dismissal; no tier prop |
| `frontend/components/detail/detail-actions.test.tsx` | +7 | The save cap renders the prompt; **not retried**; not a failure; not a modal; a Pro user sees nothing; the scheduling conflict still opens the sheet |
| `frontend/components/onboarding/calendar-step.test.tsx` | +2 | The calendar cap renders the **same** component from the server's `upgrade_hint` |

### Mutation testing: four guards probed, one found untested

Every assertion in this item is about an *absence* — no modal, no retry, no dismissal — and
an absence is the easiest kind of test to write green and useless. So each guard was broken
on purpose to see whether anything noticed.

| Mutation | Result |
|---|---|
| `role="status"` → `role="alert"` | **3 failed** — caught |
| `UPGRADE_HREF` `/pricing` → `/` | **3 failed** — caught |
| `readCapDetails` accepts any `code` | **79 passed** — **not caught** |
| The Detail Screen's cap branch removed | **5 failed** — caught |

**The third is the finding.** `CAP_CODES` exists so the client narrows on the fact the
server stated rather than on which fields a payload happens to carry. But the only non-cap
409 in the tests was `scheduling_conflict`, whose `details` has no `cap` and no
`upgrade_hint` — so the field checks below already rejected it, and deleting the code check
changed nothing anywhere in the suite. The guard was decorative.

Fixed by adding the case that makes it load-bearing: a `scheduling_conflict` payload that
*does* carry `{cap, upgrade_hint}`. Re-run with the mutation: **1 failed**. Restored: green.

### A test-authoring trap worth recording

`await screen.findByRole("status")` on the onboarding surface **resolves on the wrong
element**. The `connecting` phase replaces the whole step with `SyncState`, which is itself
a `role="status"`, so the query matched that and returned before the refusal had been
handled — the assertion then failed against the text "Connecting…". `findBy*` waits for the
*query* to match, not for the assertion to pass.

Both calendar-step assertions now wait on the hint's **text** and check its enclosing role,
which waits for the right thing. Any later test of a transient status region on this surface
has the same trap.

---

## Work Item: `per-day-quiet-hours-domain-and-model`

**42 new tests. Backend 6411 passed / 16 failed — exactly the pre-existing 16, unchanged
since item 1. No endpoint, so no `make client` and no frontend run.**

| File | Tests | What it pins |
|---|---|---|
| `tests/domain/test_weekly_quiet_hours.py` | 18 | The weekly type and the midnight rule |
| `tests/delivery/test_quiet_hours_overrides.py` | 24 | The table, the commands, the lapse, the Free user, the migration |
| `tests/domain/test_quiet_hours.py` | **0 — and that is the result** | 24 existing single-window tests pass **unmodified** |

That last row is the one that matters most. *"A Free user keeps exactly one window, with
today's behaviour unchanged"* is not asserted by a new test claiming it; it is asserted by
the 24 old tests never being touched, plus
`test_one_window_every_day_is_the_same_answer_as_the_bare_window`, which compares the two
shapes hour by hour across a whole week.

### Mutation testing: five guards probed, one claim retracted

Everything here is arithmetic that fails silently — a wrong answer is a plausible-looking
timestamp, not an exception — so every branch was broken on purpose.

| Mutation | Result |
|---|---|
| The previous day's window is never consulted | **3 failed** — caught |
| Today's window uses `covers()` instead of its start side | **5 failed** — caught |
| The **earlier** end wins (`max` → `min`) | **63 passed** — **not caught** |
| A single pass instead of the fixpoint loop | **1 failed** — caught |
| Entitlement ignored; overrides always apply | **3 failed** — caught |

The second is the dangerous one, and it is caught five times over: it is the "ask the
instant's own weekday" rule, which would let a Saturday-night setting govern Saturday
*morning*.

**The third is a claim I had to retract.** The acceptance criterion says a send must
*"defer to the later end, not the earlier one"*, and I wrote `max(ends)` and a docstring
saying the later end wins. Mutation testing says otherwise: `min` produces the identical
answer. The reason is that coverage is a union of intervals and the loop steps forward
inside it until nothing covers the instant, so **it exits at the right-hand end of the run
of overlapping windows whichever end it steps to first**. `max` only gets there in fewer
passes.

So the criterion is met — `test_two_windows_covering_one_instant_defer_to_the_later_end`
asserts the right instant and passes — but **the loop is what makes it true, and `max` is an
optimisation**. The docstring now says that, including the mutation result, rather than
crediting the wrong line.

### A test that found something before the code existed

`has_sendable_gap` was in the approved design: a pure check so the command could refuse a
week with no sendable moment. Writing its tests first made the fixture impossible to
construct, and the arithmetic says why:

> A window spans `(end − start) mod 1440` minutes, at most **1439** — a span of 0 is
> `disabled`, not 24 hours. Closing every seam around the week needs the seven spans to sum
> to 10080; seven windows sum to at most 7 × 1439 = **10073**. Every schedule leaves at
> least **seven minutes** open.

The function was deleted rather than shipped. `test_every_schedule_leaves_a_sendable_moment`
replaces it, walking the worst case the arithmetic allows — seven maximal windows at every
alignment of their starts, 10080 minutes each — and the proof lives in `MAX_DEFERRALS`'
docstring, where it explains why a bound exists that can never be reached.

---

## Work Item: `quiet-hours-pro-api`

**21 new backend tests, 1 new frontend test. Backend 6432 passed / 16 failed — the same
pre-existing 16 as every item since item 1. Frontend 1913 passed / 1 failed, and that one
fails only on this machine (see below). `make client` regenerated and produced no diff, so
the committed client was already in sync.**

| File | Tests | What it pins |
|---|---|---|
| `tests/delivery/test_quiet_hours_pro_api.py` | 21 | Both shapes, the refusal, atomicity, the lapse, scoping |
| `frontend/lib/cap-details.test.ts` | 1 | `quiet_hours_pro_required` is a third cap with the same shape |

### Acceptance criteria

| Criterion | Pinned by |
|---|---|
| Pro writes seven windows in **one request** | `test_a_pro_account_sets_seven_windows_in_one_request` |
| Free reads/writes one window, shape unchanged | `test_the_free_shape_is_unchanged` |
| Free setting seven is refused with `upgrade_hint` | `test_a_free_account_setting_weekday_windows_is_refused_with_an_upgrade_hint`, `test_the_refusal_carries_no_modal_shaped_field` |
| A lapsed Pro user can still **read** seven windows | `test_a_lapsed_account_still_reads_its_seven_windows`, `test_a_lapsed_accounts_effective_week_is_its_base_window_not_its_stored_windows` |
| `start == end` refused on **every** window | `test_a_week_whose_last_window_is_empty_writes_none_of_them` |
| Contract tests cover both shapes; `schema.ts` regenerated | `tests/api/test_contract.py` in the full suite; `make client` → no diff |

The lapse pair is the one worth reading together. The first says the seven stored windows
come back; the second says `effective_quiet_hours` is the base window every day. Either
alone would be a half-truth — the first would show a user seven windows that are not in
force, the second would look as though the lapse had deleted their data.

### Mutation testing: three probes, three caught

| Mutation | Result |
|---|---|
| Clearing no longer short-circuits the paywall (`[]` refused for a Free user) | **1 failed** — caught |
| The tier check always says Pro | **4 failed** — caught |
| `replace_quiet_hours_overrides` merges instead of replacing | **1 failed** — caught |

### A probe that caught the test author rather than the code

`test_no_app_code_deletes_a_subscription` greps `apps/` for a file containing both
`Subscription` and `.delete()`. This item made it fail for a false reason:
`notification_preferences.py` deletes `QuietHoursOverride` rows — that is how a weekday
returns to the base window — and separately *mentions* `Subscription` in a docstring
explaining that a lapse never deletes one. The guard was reading prose as a delete path.

The fix strips docstrings and comments before the same scan, keeping the guard file-wide so
it still catches a queryset parked in a variable and deleted two lines later.

**The first version of that fix was wrong, and a probe is what said so.** It rebuilt the
source by joining the surviving tokens with newlines, which splits `qs.delete()` across four
lines — so the scan found nothing and the guard passed against a module that really did
delete the table. The helper now blanks prose **in place**, preserving every other
character's line and column. Re-probed both ways: clean tree passes, probe module fails.

### The 16 pre-existing failures, and one that is local-only

Verified against `73ba016` (the commit before this item) in a scratch worktree: the same 16
fail there. They are date-dependent fixtures — `test_reminder_plan_api` mints only the `1hr`
send because the fixture event is now inside five days, and the e2e save tests 404 on a
fixture event that has aged out. **Not this item's, and not fixed here**, but they are
stale-by-calendar rather than flaky and will not recover on their own.

`frontend/lib/site-url.test.ts` fails on this machine only: the test asserts that an
unconfigured `PUBLIC_SITE_URL` yields `undefined` in production, and the repo `.env` sets
that variable. Unset it and the file passes 4/4. The test file is unchanged since `ccfadca`.

### Lint and coverage

| Check | Result |
|---|---|
| `ruff check` / `ruff format` | Clean for this item (one unused import removed) |
| ESLint, `tsc --noEmit` | Clean |
| Prettier | Clean for this item (`lib/cap-details.ts` formatted) |
| Backend coverage | 98.69% overall — the 80% gate passes |

Two gates are red for reasons this item did not create and did not fix, both from item 7:

1. **`ruff` reports 2 `DTZ001` errors** in `tests/domain/test_weekly_quiet_hours.py:210,265`
   — naive `datetime()` calls. Present at `73ba016`, so `make lint-backend` was already
   failing when that item closed.
2. **The `domain/` 100% coverage gate reports 99%** — `domain/quiet_hours.py` lines 79, 145
   and 255 are uncovered. Line 255 is the **deliberately unreachable** return that item 7's
   own report proved can never be hit (seven maximal windows leave at least seven minutes
   open), so it cannot be covered by a test and needs a `# pragma: no cover` or an explicit
   gate exemption. `make coverage-backend` fails its second gate until then.

---

## Work Item: `frontend-pro-quiet-hours`

**35 new frontend tests. Frontend 1948 passed / 1 failed — the one being the same
machine-local `site-url` failure as the previous item, unrelated to this work. ESLint and
`tsc --noEmit` clean. No backend change, so no `make client` and no backend run.**

| File | Tests | What it pins |
|---|---|---|
| `components/settings/weekday-quiet-hours.test.tsx` | 18 | The picker: one request, the refusals, midnight, the lapse |
| `lib/notification-settings.test.ts` | 11 | The weekday numbering and the clock labels |
| `app/settings/quiet-hours/page.test.tsx` (new `the tiers` block) | 6 | Free, Pro and lapsed are three states, not two |

### Acceptance criteria

| Criterion | Pinned by |
|---|---|
| Pro sets seven windows from the existing route | `gives a Pro user the seven-row picker` + the picker's own 18 |
| **A Free user's screen is unchanged** | The 9 existing `the route` tests pass **unmodified**, plus `leaves a Free user's single window exactly where it was` |
| The whole week saves in one request | `sends the whole week in one request when one day changes` |
| "Off" stays possible and unambiguous | `does not send a window whose clocks are the same`; the base window's own tests are untouched |
| A window crossing midnight is shown as such | `says which morning it reaches into`, `wraps from Sunday to Monday` |
| A Free user is offered the Pro variant inline | `offers a Free user the Pro variant, inline and once` |
| A lapsed Pro user sees their seven windows | `shows a lapsed Pro user their seven stored windows`, `does not let a lapsed Pro user edit the week` |
| Existing single-window tests still pass | 9 of 9, with one **renamed and scoped**, not weakened — see below |
| Works at mobile width | `never renders more than one day's clocks, which is what makes a phone work` |

**The one existing test that changed.** `does not offer per-day-of-week windows` became
`…to a Free user`. Its assertions are unchanged and one was **added** (`queryByRole("region",
{ name: "Per-day quiet hours" })` is null). It was the right assertion for a Free user and
the wrong one for a Pro user; deleting it would have dropped the only guard on the Free
screen, so it was scoped to the tier it describes.

### Mutation testing: five probes, one test added because of them

| Mutation | Result |
|---|---|
| Only the changed day is sent, not the week | **1 failed** — caught |
| A full-day window is sent instead of withheld | **1 failed** — caught |
| The midnight line runs off the end of the week (Sunday) | **1 failed** — caught |
| A lapsed user's rows become editable | **2 failed** — caught |
| The week is not sorted before sending | **32 passed — NOT caught** |

**The fifth is the useful one.** `sends the whole week in one request` asserts the payload's
weekdays are `[0,1,2,3,4,5,6]`, which looks like a test of the sort and is not: its fixture
is already Monday-first, so the assertion holds whether anything sorts or not. Deleting the
sort left the suite green.

A test with a **shuffled** fixture now pins it, and the probe fails as it should. The sort
itself is unchanged and the docstring's claim about it was already the modest one — *"the
server does not care, and a reader comparing a request to the UI does"* — so what the
mutation found was an untested line, not an untrue comment. Third item running in which a
probe has corrected either a claim or a test.

### Two things this item did not verify, and should be said plainly

1. **No real browser ran.** `testing-standards.md` names Playwright + axe-core for E2E and
   a11y, but this repo has **no `playwright.config`, no `e2e/` directory and no axe
   dependency** — the stack is aspirational, not installed. So "works at mobile width" and
   the a11y of the accordion are pinned by jsdom assertions about structure (one day's
   clocks in the DOM at a time, `aria-expanded` on a real `button`, rows as a list) and by
   construction, **not** by a 375px viewport or an axe run. That is weaker evidence than
   the criterion deserves, and installing the E2E stack would be its own work item.
2. **The Free user's upgrade sentence is duplicated.** It is spelled in `page.tsx` as
   `PRO_QUIET_HOURS_HINT` and in `shared/constants.py` as `QUIET_HOURS_PRO_UPGRADE_HINT`,
   because a Free user is never refused and so never receives the server's copy. The test
   `offers a Free user the Pro variant, inline and once` asserts the exact string, so the
   two cannot drift silently — but nothing *automatically* ties the TypeScript literal to
   the Python one, and a backend copy change will turn that assertion red rather than
   updating the screen.

---

## Work Item: `saved-collections-model`

**39 new backend tests. Backend 6479 passed / 16 failed — the same pre-existing 16. All 19
import contracts kept. `ruff` adds nothing new. No frontend change.**

FR-49 was the only MVP requirement with no work item on disk; this is its storage.

| File | Tests | What it pins |
|---|---|---|
| `tests/personalization/test_saved_collections.py` | 39 | The constraints, the ordering, the race, the one permitted delete |

### Acceptance criteria

| Criterion | Pinned by |
|---|---|
| `SavedCollection` in `personalization`, `personal`, owned | `TABLE_OWNERS` entries + `test_the_tables_this_intent_added_have_an_owner` |
| `ACCOUNT_CONTENT` retention on both models | `test_both_models_declare_account_content_retention` |
| Membership explicit; a save in two collections; empty collections | `test_one_save_can_be_in_two_collections_at_once`, `test_a_collection_can_be_empty` |
| **AD-3 holds** | `test_no_foreign_key_crosses_from_personal_to_catalog` (reads the live database) — untouched and green |
| Ordering persisted, explicit, stable, total, gapless | `test_a_reorder_rewrites_the_whole_list_densely`, `test_deleting_from_the_middle_closes_the_gap` |
| Name unique per user, **by constraint not code** | `test_one_user_cannot_have_two_collections_with_the_same_name` — writes around the service |
| Deleting a collection keeps its saves | `test_deleting_a_collection_leaves_every_save_inside_it_intact` |
| Named commands with audit rows (AD-5) | `test_every_command_writes_its_audit_row`, parametrized over all six actions |
| Concurrent reorder | `test_two_concurrent_reorders_leave_one_whole_order_and_no_duplicate_position` |

### The test that failed first, and what it taught

`test_one_user_cannot_have_two_collections_at_one_position` asserted that a duplicate
position raises inside a `transaction.atomic` block. It did not — and the reason is the
feature: the constraint is `DEFERRABLE INITIALLY DEFERRED`, so Postgres checks it **at
commit**, and Django wraps each test in a transaction it rolls back rather than commits. The
error escaped into teardown instead.

Rewritten as two assertions that say what deferral actually means: the duplicate insert
lands with no complaint, and `SET CONSTRAINTS ALL IMMEDIATE` then raises. A second test
(`test_the_name_constraint_is_not_deferred`) pins the contrast — only the position
constraint is deferred, and a duplicate name is still refused at the insert, where the user
can be told about it.

### Mutation testing: five probes, five caught

| Mutation | Result |
|---|---|
| The reorder takes no advisory lock | **1 failed** — caught by the concurrency test |
| Rename does not exclude itself from the name check | **1 failed** — caught |
| Deleting leaves a gap in the positions | **1 failed** — caught |
| A new collection claims position 0 instead of the end | **4 failed, 9 errors** — caught |
| Ownership is not part of the collection lookup | **1 failed** — caught |

The first is the one the advisory lock exists for, and it is worth noting that the mutated
run failed in **under a second** against 41 seconds for the real suite: without the lock the
two threads collide immediately rather than queueing.

### An architecture rule was narrowed, with approval

Two tests asserted that `personal`'s models declare **zero** relation fields. The collection
membership table has two foreign keys — both inside `personal`, neither crossing anything —
and its only mark on `SavedEvent` is a *reverse accessor*, which is not even a column.

The three rules those tests cite each have their own dedicated test, and **all three stayed
green throughout**: AD-3's `test_no_foreign_key_crosses_from_personal_to_catalog` (which
reads the foreign keys Postgres actually holds, not the metadata), OQ-8's
`test_no_personal_model_relates_to_user_or_content_type`, and AD-21's
`test_saved_event_event_id_is_a_plain_uuid_field`. The blanket assertion was a wider net
than any of them.

Both tests now forbid a relation **for what it reaches** — a catalog app, `User` or
`ContentType` — rather than for existing. Probed by adding a `ForeignKey` from `SavedEvent`
to `ingestion.Event` and confirming both fail; reverted immediately, and they pass again.

**What was given up, stated plainly:** the blanket version made *any* foreign key in
`personal` a build break, which is a cheaper and blunter signal than a judgement about what
a key points at. A future intra-`personal` foreign key will now pass these two tests
silently. The wall itself is still enforced by a test that reads the database.

---

## Work Item: `data-export`

**75 new backend tests. Backend 6589 passed / 16 failed — the same pre-existing 16. All 19
import contracts kept, `make client` run and the client regenerated. Frontend 1948 passed,
unchanged by this item.**

| File | Tests | What it pins |
|---|---|---|
| `tests/identity/test_data_export.py` | 44 | Registry enumeration, redaction, the link as a credential |
| `tests/identity/test_export_api.py` | 16 | The two auth models, and what a token cannot be aimed at |
| `tests/identity/test_export_ics_roundtrip.py` | 15 | The ICS through this project's own parser |
| `tests/worker/test_data_export_tasks.py` | 12 | The dispatcher, the build-and-send job, the expiry |

### Acceptance criteria

| Criterion | Pinned by |
|---|---|
| Enumerates from `retention_registry()`, no second list | `test_the_export_names_no_models_of_its_own`, `test_a_user_data_model_registered_later_is_exported_without_touching_export_code` |
| Excluded **by category**, not by name | `test_the_categories_that_are_not_user_data_are_excluded_by_category` (parametrized) |
| All user-created records in the JSON | `test_every_exported_model_can_name_its_user` — 29 models reached |
| Personal-event locations redacted on opt-out | Both branches, plus `test_a_user_with_no_preference_row_shares_by_default` |
| Saved collections included | `test_a_user_data_model_registered_later_is_exported_without_touching_export_code` |
| ICS imports cleanly | `test_export_ics_roundtrip.py` — **weaker than the criterion, see below** |
| Async, email within 24h | `test_the_job_builds_the_export_and_mails_the_links`, `DATA_EXPORT_SLA` |
| Links expire; no cross-user fetch | `test_a_link_past_the_window_is_refused`, `test_another_users_token_does_not_open_this_export` |
| Requesting twice queues one job | `test_requesting_twice_in_quick_succession_does_not_queue_two_jobs` + a partial unique constraint |

### The test that found the design hole before the download did

`test_every_exported_model_can_name_its_user` failed on its first run, naming **seven**
models the export would have silently skipped:

| Model | Why it had no `user_id` | Answer |
|---|---|---|
| `identity.User` | The account row **is** the user | `export_user_path = "id"` |
| Four `*AuditEntry` tables | The user is whoever acted | `export_user_path = "actor_id"` on `ActorColumns` |
| `tests.wall.personal_probe.Note` | Owns through a FK | `export_user_path = "owner_id"` |
| `sessions.Session` | **Genuinely has none** — the account is inside the encoded blob | Declared not portable |

Without that test, a user's own account record would have been the one thing missing from
their export, and nobody would have noticed until somebody read a download.

`sessions.Session` is the only entry in `FRAMEWORK_EXPORT_PATHS` mapped to `None`, and the
reason is stated where it is declared: a session key is a **live credential**, and mailing
one to whoever reads the mailbox is the opposite of what a privacy feature should do. It
mirrors `FRAMEWORK_RETENTION`, which exists for the same reason — a Django model cannot
declare an attribute we invented.

### A second failure that was the wall working

With the audit tables newly reachable through `actor_id`, 24 tests began failing with
*"Database queries to 'catalog' are not allowed in this test"*. `ingestion.IngestionAuditEntry`
is `AUDIT_LOG` like our other audit tables and sits on the **far side of the AD-3 wall**, so
one export query would have spanned both schemas.

`exported_models()` now filters on the alias, asked of Django's own `router.db_for_read` —
not of `settings.DATABASE_ROUTING` and not of `config.db_router`, because an app importing
`config` breaks AD-2's inward-pointing layers. That was the *first* fix, and `lint-imports`
rejected it, which is the second guard doing its job.

### Mutation testing: six probes, and one that corrected the tests

| Mutation | Result |
|---|---|
| Not-user-data categories join the export | **2 failed** — caught |
| The alias filter is dropped | **35 failed** — caught |
| The location opt-out is ignored | **1 failed** — caught |
| The download token omits the user | **10 failed** — caught |
| The expiry check is dropped | **1 failed** — caught |
| **Credential redaction by field *type* disabled** | **74 passed — NOT caught** |

**The last one is the important one.** Disabling the type check changed nothing, because
the only `EncryptedTextField` in the tree is *also* named `credential` — so the name list
caught it. The belt was holding while the braces were cut, and the type check, which is the
guard that matters for a field added later, was pinned by nothing.

Three focused tests now pin `_is_secret_field` directly: an encrypted field called `notes`
is redacted, a plain field called `password` is redacted, and an ordinary field is **not**
— the third because a redactor that redacted everything would satisfy the first two and
hand the user a download full of `[redacted]`. Re-probed: the mutation now fails.

### What the ICS test does and does not prove

The criterion says the export *"is importable into Google Calendar / Apple Calendar /
Outlook"*. **None of those was run.** There is no Playwright, no calendar client and no
integration harness in this repo.

What was proved is a real round trip: the file is parsed by `formats/ics/parser.py`, the
`icalendar`-based parser this project already uses to read users' subscribed feeds, and the
events come back with their titles, locations and **instants** intact. The structural rules
those three clients actually differ on are asserted directly — `UID` and `DTSTAMP` on every
event, CRLF endings, `VERSION`/`PRODID`, no line over 75 octets, escaped commas and
semicolons, and no invented `DTEND`.

That is good evidence and it is not the criterion. Importing into the three clients remains
unverified.

---

## Work Item: `frontend-account-and-billing-settings`

**60 new tests — 15 backend, 45 frontend. Backend 6608 passed / 16 failed (the same
pre-existing 16); frontend 1993 passed / 1 failed (the same machine-local `site-url`).
All 19 import contracts kept, `make client` run.**

| File | Tests | What it pins |
|---|---|---|
| `tests/identity/test_billing_account_api.py` | 15 | The four states, and that the two reads never disagree |
| `frontend/app/settings/account/page.test.tsx` | 17 | The route: free, lapsed, active, past-due, failures |
| `frontend/components/settings/plan-summary.test.tsx` | 17 | The plan block and the portal action |
| `frontend/components/settings/download-my-data.test.tsx` | 11 | The export request, the repeat, the failures |

### Acceptance criteria

| Criterion | Pinned by |
|---|---|
| Plan read from `Subscription`, never inferred | `GET /api/billing/account` + `test_the_read_writes_nothing_and_calls_no_provider` |
| Pro gets **Manage subscription** → portal | `mints a session and follows the URL it returns` |
| No local cancel flow | `offers Manage subscription and no local cancel` |
| Free gets a quiet link to `/pricing` | `says so and links to pricing` |
| Export says "by email within 24 hours" | `posts once and says it will arrive by email within 24 hours` |
| Asking twice handled gracefully | `is not reported as a failure`, `cannot be double-submitted while the first is in flight` |
| **Past-due shown honestly** | Six tests across both layers — see below |
| Export not gated, **and not gated by placement** | `still gets Download my data` on a Free account |
| Mobile, settings conventions | 44px controls, the same block layout as the other `/settings/*` routes |

### The state this screen exists for

`is_pro` is **true for `past_due`**, which is correct — a failed payment leaves someone
entitled while they fix it — and it is exactly why this screen could not be built on the
existing endpoint. A `past_due` account and an `active` one are indistinguishable through
that bool, and this is the only place in the product where a failed payment is visible at
all.

`GET /api/billing/account` carries `needs_payment` beside `is_pro`, and
`test_is_pro_agrees_with_the_entitlement_read_in_every_state` — parametrized over all four
statuses — pins that the two endpoints can never disagree about entitlement itself. That
failure would be silent in the worst way: a screen saying "you're on Pro" over features the
server refuses.

### Mutation testing: three probes, three caught

| Mutation | Result |
|---|---|
| `past_due` no longer sets `needs_payment` | **1 failed** — caught |
| A lapsed account forgets it ever had Pro | **2 failed** — caught |
| A past-due account renders the ordinary term line | **4 failed** — caught |

### Two defects found while writing the tests

1. **A refusal with no sentence rendered as no refusal at all.** `saveFailureMessage`
   returns the API's own message whenever the body is the project's error shape —
   *including when that message is empty* — and the component renders `{failure}`, so an
   empty string produced no line. A user would have clicked, watched nothing happen, and
   had no way to tell whether it worked. Both call sites now fall back to their own line,
   and both have a test for it.

   **The same hole exists in `quiet-hours-window.tsx` and the other settings islands**,
   which use the helper the same way. Not fixed here — they belong to a closed item — but
   it is the same class of bug and worth a sweep.

2. **A test of mine was passing vacuously.** `queryByText("You're on the free plan")` was
   asserted to be null in the past-due case — and it was null for the wrong reason, since
   the component renders the sentence *with a full stop*. The positive assertion in the
   Free case failed first and exposed both; both now match the rendered text exactly.

### Verified by construction, not by a browser

Mobile layout follows the other `/settings/*` routes — stacked blocks inside
`max-w-(--layout-container-reading)`, controls at `min-h-[44px]`. As with the previous two
frontend items, **no 375px viewport and no axe run**: this repo still has no Playwright and
no axe dependency. The accessibility assertions here are structural — the two sections are
named regions, the confirmation is a `role="status"` live region that is always present,
the failures are `role="alert"`, and the busy controls carry `aria-busy`.

---

## Work Item: `saved-collections-api`

**35 new backend tests. Backend 6654 passed / 17 failed; frontend 1993 passed / 1 failed.
All 19 import contracts kept, `make client` run. The backend baseline moved from 16 to 17
overnight — see below.**

| File | Tests | What it pins |
|---|---|---|
| `tests/personalization/test_collections_api.py` | 35 | Eight endpoints, the gate, the lapse, scoping |

### Acceptance criteria

| Criterion | Pinned by |
|---|---|
| Create, rename, delete, reorder, assign, unassign | One test each, over HTTP |
| **Writes Pro-gated** with the inline `{cap, upgrade_hint}` shape | `test_a_free_user_creating_a_collection_is_refused_with_an_upgrade_hint`, `test_the_refusal_carries_no_modal_shaped_field` |
| **A lapsed user reads and unassigns** | Seven tests under *the lapse*, built from a fixture that subscribes, creates, then cancels |
| Reorder takes the whole ordering in one request | `test_reorder_takes_the_whole_list_in_one_request`, and a partial list refused |
| Own collections only, **404 not 403** | Parametrized across five endpoints |
| Events read returns the snapshot, no `catalog` join | `test_the_events_read_returns_the_snapshot_and_no_catalog_fields`, run without the catalog database granted |
| Contract tests; `schema.ts` regenerated | Full suite + `make client` |

### The lapse, which is seven tests rather than one

The acceptance criterion names read and unassign and names create as blocked. The checkpoint
settled the rest: **only the two operations that add are gated**. So each half is pinned —
a lapsed user may still read, unassign, rename, reorder and delete, and may not create or
assign. The fixture subscribes a user, has them build a collection with a save in it, and
*then* cancels the subscription, so every one of those tests runs against data that
genuinely predates the lapse.

### Two defects the tests found before a client would have

**1. `/order` was unreachable.** Five tests failed with `405 Method Not Allowed` naming
PATCH and DELETE. `PUT /collections/order` was being matched by the `/{collection_id}`
rename route — django-ninja matches in registration order, so a literal segment loses to a
path parameter declared above it. `"order"` then failed to parse as a UUID and the caller
got a 405 that said nothing about the real problem.

Fixed by declaring `/order` above the parameterised routes, with a comment saying why it
must stay there. Re-probed by moving it back: five tests fail again.

**2. A partial reorder answered 500.** The command raised `ValueError` for a list that does
not name every collection — the right convention for programmer misuse, and the wrong one
for a request body. A client can send that list, so it reached the caller as a server error
for a request the server had understood perfectly and chosen to refuse.

It now raises `InvalidCollectionOrderError(ValidationError)` → 422 with a sentence. Two of
`saved-collections-model`'s tests expected `ValueError` and were updated with the reason.

### Mutation testing: four probes, four caught

| Mutation | Result |
|---|---|
| The gate never refuses | **5 failed** — caught |
| Unassign is gated too (a lapsed user trapped) | **1 failed** — caught |
| Assign is no longer gated | **1 failed** — caught |
| `/order` declared after `/{collection_id}` again | **5 failed** — caught |

The second and third are the pair that pins the checkpoint decision in both directions: the
gate must not spread to tidying, and must not retreat from adding.

### The baseline moved overnight, and it is not this item

`tests/delivery/test_reminder_plan_api.py::test_a_custom_slot_is_minted` joined the
pre-existing failures between yesterday's run and today's. Its fixture is hard-coded to
`AFTERNOON_START = 2026-11-12 02:00 UTC`, and a `custom:90` slot is due 90 minutes before
that — a moment that passed this morning, so no send is minted.

**It is the same stale-by-calendar family as the other 16**, in the same file as one of
them, and it touches nothing this item changed (collections live in `personalization` and
`identity`; this is `delivery`). It will not recover on its own, and more of these will
arrive as the fixture dates age: the set grew from 16 to 17 purely by the date changing.

---

## Work Item: `frontend-collections`

**37 new frontend tests. Frontend 2030 passed / 1 failed — the same machine-local
`site-url`. ESLint, `tsc` and Prettier clean. No backend change, so no `make client` and no
backend run.**

FR-49 now has a screen. TRACEABILITY.md's *"no screen shows creating, viewing, or managing a
collection"* is closed.

| File | Tests | What it pins |
|---|---|---|
| `components/collections/collection-manager.test.tsx` | 22 | The four verbs, membership, both empty states, failures |
| `app/settings/collections/page.test.tsx` | 15 | Pro, Free and lapsed; the unavailable read |

### Acceptance criteria

| Criterion | Pinned by |
|---|---|
| Create, rename, delete, reorder + membership | One test each, through the mocked client |
| Reorder sends the whole ordering | `sends the whole resulting order, not a swap` |
| Delete says the saves survive | `asks first, and says the saved events survive` |
| Both empty states render deliberately | `renders the quiet empty state…`, `says an opened collection is empty without borrowing the failure treatment` |
| Free sees it offered inline, not hidden | Five tests under *a Free user* |
| Lapsed still sees and reads theirs | Four tests under *a lapsed Pro user* |
| Events render from the `SavedEvent` snapshot | `reads the collection's events and renders the snapshot time` |
| Mobile; design-system tokens | One column; **`tests/spacing-scale.test.ts` enforces the tokens** — see below |

### The two pairs that look alike and are not

**Free and lapsed are both "not Pro".** One has nothing and is being offered something; the
other has collections that are still theirs. Rendering the second like the first would be
the deletion the brief forbids, as far as the user could tell. Four tests pin the lapsed
case, including that they are *not* shown the "no collections yet" copy.

**An unavailable read and an empty list are both "nothing on screen".** A Pro user with
three collections whose read blinked would otherwise see "you have none", which reads as
data loss. `shows the unavailable state when the read fails` pins the difference.

### The design system caught what no reviewer would have

`tests/spacing-scale.test.ts` failed on four values — `h-14` three times in the skeleton and
`py-10` in the empty state. The scale is `0 1 2 3 4 6 8 12 16 20 30`, and none of those four
is on it.

**That guard matters more here than anywhere else in this run**, because this is the one
surface with no mockup to check against: there was no design to deviate from, so the token
scale was the only thing standing between "built from the design system" and "built from
whatever looked right". Fixed to `h-12` and `py-12`.

### Mutation testing: four probes, four caught

| Mutation | Result |
|---|---|
| Reorder sends only the moved collection | **2 failed** — caught |
| Delete fires without confirming | **3 failed** — caught |
| The confirmation stops saying the saves survive | **1 failed** — caught |
| A lapsed user's collections are hidden | **2 failed** — caught |

The third is the one worth having: the delete would still work, the confirmation would still
appear, and only the sentence that stops a user fearing for their saves would be gone.

### Verified by construction, not by a browser

As with every frontend item in this run: **no 375px viewport and no axe run**, because this
repo has no Playwright and no axe dependency. The accessibility work here is structural and
asserted — the list is a real `<ul>`, the reorder controls are `<button>`s with
`aria-label`s naming the collection they move, the ends are `disabled` rather than inert so
the boundary is announced, the expander carries `aria-expanded`, and the delete confirmation
is inline with no focus trap. None of that is a substitute for an audit.

---

## Work Item: `e2e-proof-and-contract-tests`

**67 new backend tests — 21 journey, 46 contract. Backend 6721 passed / 17 failed (the same
pre-existing 17). All 19 import contracts kept. No Stripe, no network, no secrets.**

| File | Tests | What it proves |
|---|---|---|
| `tests/e2e/test_pro_tier_proof.py` | 21 | The paid path, all four capabilities, and the downgrade |
| `tests/e2e/test_pro_tier_contract.py` | 46 | Every endpoint this intent added, by name |

### Acceptance criteria

| Criterion | Pinned by |
|---|---|
| The paid path end to end | `test_the_whole_paid_path` — save, refuse, checkout, webhook, save again |
| All four capabilities in the same test | Steps 7–10 of that test: calendars, collection + assign, seven windows, export |
| **Cancellation closes every gate** | Five refusal tests under `TestCancellationClosesEveryGate` |
| **Nothing is deleted** | Five survival tests on the same fixture |
| Entitlement never granted without a webhook | `TestTheWebhookIsTheOnlyGrant`, two tests |
| Replay and out-of-order webhooks | `TestTheReplayAndTheRace`, two tests |
| Contract covers every endpoint; client in sync | 46 tests, enumerated by path and verb |
| No Stripe, no network, no secrets | `FakeBillingAdapter` + `InMemoryThrottleAdapter` |
| Every test can fail | Three mutation probes below; no `or`-fallbacks anywhere |

### Four product rules this test learned the hard way

Every one of these was a failing assertion first, and each is a real rule rather than a
defect. They are recorded in the test where the next reader meets them.

**1. A lapsed account keeps the Free allowance it never spent.** The first version asserted
that the next save after cancelling is refused. It is not: `save_cap.py` says a Pro user
*"is never refused and never spends a slot"*, so a lapsing user has an untouched daily
allowance. Asserting otherwise would have demanded that lapsing confiscate a day the user
never used. The test now saves once, then asserts the refusal.

**2. Weekday windows apply only to a Pro account.** Writing seven overrides for a Free user
changes no send — `_effective_week` reads entitlement and falls back to the base window.
That is the lapse promise observed from the other side, and it made the first Pro assertion
read 07:00 instead of 09:00.

**3. A day's window begins on that day.** A 23:00–09:00 window set for Friday owns
*Saturday's* small hours, so the window governing a 03:30 send is the **previous** night's.
The test now sets all seven days, asserting that the override takes effect rather than
which night owns the instant — the selection itself is pinned by `test_weekly_quiet_hours.py`.

**4. A preference change re-times pending sends only through the API.** `apply_settings_patch`
wraps the write and `reschedule_pending_for_user` in one transaction (AD-7); calling
`replace_quiet_hours_overrides` directly writes windows and re-times nothing. The send kept
its old instant until the test went through `PUT /api/settings/notifications` — which is
what this file's own method required anyway.

### Two more the test had to be driven through the real surface to see

- **`set_plan_slots` mints nothing without a `send_target`.** `delivery` may not read
  `apps.personalization.models` (AD-3), so only a caller holding the event can supply the
  start time the keys are minted from. Called directly it updated the plan and left an empty
  `ScheduledSend` table.
- **A send's `due_at` needs the user's zone.** A user with no digest preference has no
  timezone, so no send is minted at all — the shift is of a *local* wall clock.

### Mutation testing: three probes, three caught

| Mutation | Result |
|---|---|
| A cancelled subscription still counts as Pro | **3 failed** — caught |
| The collections gate never refuses | **2 failed** — caught |
| **A cancellation deletes the user's collections** | **1 failed, 13 errored** — caught |

The third is the one this item exists for. Every previous item proved "never delete" against
its own table; this is the first test that would notice a downgrade path reaching across
apps to destroy something.

### No defect was found in the product

Every failing assertion in this item turned out to be the test misunderstanding a rule, not
the system breaking one. **That is a result, not an absence of one**: four gates, five
surfaces and the entitlement read ran together for the first time and the loop closed.

Nothing in `apps/`, `domain/` or `worker/` was modified by this item.
