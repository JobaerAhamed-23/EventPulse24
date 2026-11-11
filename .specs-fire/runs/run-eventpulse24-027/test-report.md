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
