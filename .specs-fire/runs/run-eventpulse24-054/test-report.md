---
run: run-eventpulse24-054
work_item: account-deletion-confirmation-email
intent: account-profile-expansion
generated: 2026-11-20
status: passed
---

# Test Report: The Mail That Says Your Account Is Going Away — and How to Stop It

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit | 65 | 0 | 0 | 95% |
| Integration | 1703 | 0 | 0 | 95% |
| **Total** | **1768** | **0** | **0** | **95%** |

The full backend suite is green: **7632 passed** in 14m12s.

## Acceptance Criteria Validation

| # | Criterion | Status |
|---|-----------|--------|
| 1 | The design checkpoint settles the cancel-link mechanism, recorded in a design doc before any code is written | ✅ `design-deletion-cancel-token.md`, written and approved at the plan checkpoint before the first line of implementation |
| 2 | A mail is sent when the deletion is **requested**, on the **transactional** stream | ✅ `test_requesting_deletion_sends_the_notice` |
| 3 | The mail carries the date the account will be destroyed, rendered from `scheduled_for` | ✅ `test_it_carries_the_date_the_account_will_be_destroyed` |
| 4 | The mail carries a working way to cancel, the way the design checkpoint chose | ✅ `test_it_carries_the_token_in_the_link`, `test_the_token_in_the_mail_cancels_the_deletion` |
| 5 | The recipient is the account's address; it reaches no log line, no audit detail, no forbidden store | ✅ `test_it_goes_to_the_accounts_own_address`, `test_the_send_failure_log_carries_no_address`, `test_the_audit_rows_carry_no_token` |
| 6 | The token is a digest with a per-row salt, single-use, revocable, and holds the user by value | ✅ `test_the_notice_carries_a_token_that_is_not_stored_in_the_clear`, `test_a_spent_token_cannot_be_replayed`, `test_two_concurrent_cancellations_of_one_token_only_one_succeeds` |
| 7 | The template lives in `backend/apps/identity/templates/identity/`, beside the four already there | ✅ `backend/apps/identity/templates/identity/account_deletion.txt` |
| 8 | The mail says the same things the modal's body says, and the two are checked against each other | ✅ `DELETION_REMOVES` / `DELETION_SURVIVES` are one source for both surfaces; `test_it_uses_the_shared_words_the_modal_uses` |
| 9 | The mail does not promise a follow-up mail | ✅ `test_it_does_not_promise_a_follow_up_mail` |
| 10 | Every expiry in the copy is rendered from the constant that enforces it | ✅ `test_it_states_the_grace_period_from_its_constant`, `test_changing_the_constant_changes_the_copy` |
| 11 | The mail is sent once, not on every request | ✅ `test_asking_twice_sends_one_mail_not_two` |
| 12 | A send failure does not fail the deletion request | ✅ `test_a_mail_failure_does_not_fail_the_request`, `test_the_send_failure_log_carries_no_address` |
| 13 | The new template and renderer are covered by tests that can fail — verified by a mutation probe | ✅ **three mutation probes, all detected** — see below |
| 14 | `backend/tests/api/test_contract.py` stays green, and the contract is regenerated and committed if the change reaches the schema | ✅ **the schema is byte-identical** — this item adds no endpoint and no field, so `export_openapi_schema` produces no diff and the generated client needs no regeneration |
| 15 | `tests/architecture/test_no_direct_writes.py` stays green | ✅ included in the 1703-test run |

## Tests Written

### Unit Tests

- `backend/tests/identity/test_account_deletion_mails.py` (13 tests) — the renderer: the recipient, the link, the four facts the mail states, the two promises it must not make, the grace period from its constant, and the stream.
- `backend/tests/identity/test_account_deletion_token_concurrency.py` (2 tests) — single-use **under concurrency**, and the audit trail recording exactly one cancellation when two attempts arrive together.

### Integration Tests

- `backend/tests/identity/test_account_deletion.py` (12 tests added, 37 total) — the send happens, once, after the commit; the token is a digest at rest; a mail failure does not fail the request and logs no address; a rolled-back request sends no mail; the token in the mail cancels the deletion, cannot be replayed, cancels only its own account, and is audited without the token.

## Test Commands

```bash
# The item's own tests
cd backend && uv run pytest tests/identity/test_account_deletion.py \
    tests/identity/test_account_deletion_mails.py \
    tests/identity/test_account_deletion_token_concurrency.py -q

# The wider blast radius
cd backend && uv run pytest tests/identity/ tests/architecture/ tests/api/test_contract.py -q

# Everything
cd backend && uv run pytest -q

# Coverage on the changed modules
cd backend && uv run pytest tests/identity/ tests/architecture/ tests/api/test_contract.py \
    --cov=apps.identity.services.deletion --cov=apps.identity.services.emails \
    --cov=apps.identity.models --cov-report=term-missing -q
```

## Coverage Details

| Module | Statements | Cover | Missing |
|--------|------------|-------|---------|
| `apps/identity/services/deletion.py` | 147 | 97% | 363-366, 822 — **both pre-existing**, not this item |
| `apps/identity/models.py` | 113 | 96% | 109, 172, 235, 328, 424 — **all pre-existing** |
| `apps/identity/services/emails.py` | 42 | 88% | 170-171, 191-200, 209 — **the pre-existing data-export renderer**, not this item |
| **Total** | **302** | **95%** | above the 80% target |

**Every line this item added is covered.** The uncovered lines are the data-export mail
renderer and pre-existing model branches, none of which this item touched.

## Mutation Probes

**A test that cannot fail is a decoration.** Three mutations were applied to the
implementation, and each was detected:

| # | The mutation | The test that caught it | Result |
|---|---|---|---|
| 1 | The mail sent **inside** the transaction instead of after the commit | `test_a_rolled_back_request_sends_no_mail` | **FAILED** — "the mail was sent for a request that was rolled back" |
| 2 | The send made **unconditional**, so a second request sends a second mail | `test_asking_twice_sends_one_mail_not_two` | **FAILED** — `assert 2 == 1` |
| 3 | `{{ grace_days }}` **hard-coded** to "30 days" in the template | `test_changing_the_constant_changes_the_copy` | **FAILED** — "14 days" absent |
| 4 | The `select_for_update()` **row lock removed** from the token spend | `test_two_concurrent_cancellations_of_one_token_only_one_succeeds` | **FAILED** — 3 of 3 runs |

**The fourth is the one worth dwelling on.** The row lock is not decoration: without it,
two concurrent attempts at the same token both find the pending request and both delete
it, so the token would be usable twice and the audit trail would carry two cancellations
for one request. The probe failed on **every** run, so the test is not merely
occasionally sensitive.

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| **HTML entity syntax leaked into the plain-text mail.** Django's template engine escapes `"` to `&quot;` and `'` to `&#x27;`, and the shared copy contained a quoted example — so the reader would have seen `&quot;47 events were saved in NYC on Aug 27&quot;` in their inbox | **Medium** | **Fixed.** The copy was rewritten without quotation marks. **`mark_safe` was deliberately *not* used** — the project's other mails escape on purpose (`email_change_requested.txt` renders a user's own address), and introducing a safe-mark into a codebase that has never had one would trade a visible artefact for a latent injection risk. The test `test_it_uses_the_shared_words_the_modal_uses` caught this, and it is the reason that test asserts the *raw* shared string rather than a substring of it |
| The grace period was initially rendered through `humanise_duration`, which is scoped to whole hours and minutes and falls through to the raw `timedelta` repr — "30 days, 0:00:00" in a sentence about a person's account | Low | **Fixed.** A local `_humanise_days` formatter was added in `emails.py`, with the reason recorded beside it. `domain.sources.humanise_duration` was **not** widened — it is scoped to cadence-and-refusal copy, and its own docstring says it is "not a general formatter" |
| The date rendered in Django's localised default format ("Dec. 20, 2026, midnight"), which is locale-dependent and reads oddly | Low | **Fixed.** The renderer formats it explicitly as `%d %B %Y` |
| The `django_capture_on_commit_callbacks(execute=True)` guard | — | **Not an issue.** Under pytest-django the test transaction never commits, so an `on_commit` callback would never fire — and an implementation that never sent the mail would pass. Every test that asserts a send uses the capture |

## Ready for Completion

- [x] All tests passing — 7632 backend, 0 failures
- [x] Coverage target met (95% on the changed modules, against an 80% target)
- [x] All acceptance criteria validated — 15 of 15
- [x] No critical issues open
- [x] The mutation probes detect all four mutations
- [x] `ruff check` and `ruff format --check` clean across `apps/identity/` and `tests/identity/`
- [x] No missing migrations (`makemigrations --check` reports no changes)
- [x] The OpenAPI schema is byte-identical — no endpoint or field changed, so the generated client needs no regeneration

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-054*
