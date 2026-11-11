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
