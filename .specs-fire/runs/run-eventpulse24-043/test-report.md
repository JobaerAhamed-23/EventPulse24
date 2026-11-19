---
run: run-eventpulse24-043
work_item: email-change-mails
intent: account-profile-expansion
date: 2026-11-19
---

# Report: Two Letters — One to Prove It, One to Warn About It

## The finding that stopped the item

The warning mail's first draft told the reader: *"change your password now. That ends the
other sessions on your account, which stops the change from being confirmed."*

**That was false, and it was about to ship as security advice.**

Probed rather than assumed:

- `confirm_email_change` takes **a token and nothing else** — no session, no password.
- `reset_password` had **zero references** to `PendingEmailChange`.

So an attacker who already held the confirmation link kept it through a password change,
and the login moved anyway. Ending sessions does not help either: the link is in their
mailbox, not in their session.

**This is a gap in the design shipped in run-042, not a wording slip.** That design leans
on the warning as its defence against a session-holding attacker — and as built, there was
no action the victim could take that stopped the confirmation.

**Closed by making the remedy real** (user's decision): `reset_password` now revokes the
account's outstanding email changes in the same transaction, and
`test_password_reset_revokes_a_pending_email_change` proves the link stops working.

## Tests

| Suite | Result |
|---|---|
| `tests/identity/test_email_change_mails.py` | **13 passed** |
| `tests/identity/test_email_change.py` | **21 passed** (one added for the remedy) |
| `tests/identity/test_password_reset.py` | **23 passed** |
| `ruff` / `lint-imports` | clean; 20 contracts kept |

## Mutation probes

| Mutation | Result |
|---|---|
| The warning carries the confirmation link | 2 failed |
| The confirmation is sent to the old address | 3 failed |
| The expiry is typed back into the reset copy | 3 failed |
| **The reset stops revoking pending changes** (the remedy becomes a lie) | 1 failed |

**A probe's restore step failed, and that is worth recording**: `git checkout` cannot
restore an untracked new template, and on a *tracked* one it restored the **committed**
version — silently undoing this item's own fix to `password_reset.txt`. The suite caught
it immediately (`test_changing_the_constant_changes_the_copy`), which is the test earning
its place: it fails against hard-coded text that merely happens to match.

## The finding fixed on the way past

`password_reset.txt` stated *"valid for 30 minutes"* as literal text, so changing
`AUTH_RESET_TOKEN_LIFETIME` left the mail misstating its own rule — exactly what this
item's acceptance criterion forbids. Both new templates and the reset template now render
the expiry from the constant via `domain.sources.humanise_duration`, **reused rather than
reimplemented**.

## Acceptance criteria

| Criterion | State |
|---|---|
| Link builder + renderer following the reset pattern | ✅ |
| Renderer for the warning to the old address | ✅ |
| Warning carries **no token and no link that performs the change** | ✅ asserted twice |
| Neither mail logged with its token; allowlist untouched | ✅ |
| Stream chosen explicitly | ✅ `email_change_stream()` |
| Expiry from the **named constant**, not retyped | ✅ and the old violation fixed |
| Confirmation → new address only; warning → old address only, swap fails | ✅ |
| Preview never really sends | ✅ existing seam untouched |
| Every test can fail | ✅ four probes |

## Decision recorded rather than implemented

**Send failure is not retried here.** The row is written, the mails go after the
transaction as `request_password_reset` does, and a failed send leaves an outstanding
request with no link. The row expires, and the screen's resend control (a later item) is
the remedy. Retrying inside the request path would turn a mail provider's outage into a
failed API call for the user.
