---
run: run-eventpulse24-042
work_item: pending-email-model-and-commands
intent: account-profile-expansion
date: 2026-11-19
---

# Review: Moving the Login

## Findings raised and fixed during the run

| # | Finding | Resolution |
|---|---|---|
| 1 | **`test_a_token_works_once` did not test the single-use guard.** Removing the conditional `UPDATE ... WHERE used_at IS NULL` left all 19 tests green — the scan's `used_at__isnull=True` filter refuses a sequential retry for a different reason entirely. | Added `test_the_database_is_the_arbiter_when_two_confirmations_race`, which consumes the row between the scan and the update. The probe now fails 1 test. |
| 2 | **The new table had no owner.** `tests/architecture/test_write_ownership.py` failed twice: AD-16 enforces that every table the tree writes is claimed in `TABLE_OWNERS`. | Claimed for `identity`, with the reason recorded: the app that owns the credential owns the unproven claim on it. |
| 3 | **`ErrorItem` was constructed with the wrong fields** (`field=` / `message=` rather than `loc=` / `msg=`), which would have failed at runtime on the two validation paths. | Corrected against `sign_up.py`'s usage; the two messages are named constants so neither echoes the address back (AD-13). |
| 4 | **`EmailChangeRequest` was a hand-rolled `__slots__` class** where the codebase uses frozen dataclasses for value objects. | Converted; `row_id`'s purpose (the send's idempotency key, as `request_password_reset` does it) is now stated rather than implied. |
| 5 | **What losing the race leaves behind was undocumented.** The raise rolls the transaction back, so the row stays unconsumed. | Documented with its reasoning, and pinned by an assertion. Marking a token used by a change that did not happen would record an untruth; the link is useless but harmless. |

## Deliberate decisions a reviewer should push on

- **Sessions are not ended.** Argued in the module docstring from Django's session auth
  hash being an HMAC over the *password* field. If you disagree, it is two lines plus a
  warning on the screen.
- **24-hour token lifetime**, against the reset flow's 30 minutes. A longer window on a
  mailbox, traded against expiring most honest attempts.
- **The taken-address path is not constant-time.** It skips a row write.
  `request_password_reset` accepts the same exposure; it is now stated in the docstring
  rather than left unmentioned.

## Suite

**7422 passed, 3 failed.** The three are `tests/delivery/test_preferences_api.py`,
**verified pre-existing** on the unmodified base commit `b8c6b21` in a separate worktree
with its own dependency set. Untouched by this work.

The 28 `test_digest_api.py` failures seen in an earlier run **did not recur** with the dev
stack stopped, confirming they were interference through the Redis this stack shares by
design rather than a defect.
