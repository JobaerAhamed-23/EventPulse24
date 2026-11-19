---
run: run-eventpulse24-043
work_item: email-change-mails
intent: account-profile-expansion
date: 2026-11-19
---

# Review: Two Letters

## The one finding that mattered

**The warning mail's advice was false**, and it was a design gap rather than a wording
slip. Recorded in full in `test-report.md`. Closed by making `reset_password` revoke
outstanding email changes, so *"change your password"* actually stops the takeover.

**What this says about run-042's design.** It claimed the warning to the old address was
the real defence against a session-holding attacker. That claim was only true if the
warning could offer an action — and it could not. The design reasoned correctly about
*who* to reach and never checked *what to tell them*. The defence is real now; it was not
when the previous item was called complete.

## Smaller findings

| # | Finding | Resolution |
|---|---|---|
| 1 | `password_reset.txt` typed its expiry into the copy, so the constant and the mail could disagree | All three templates render it from the constant |
| 2 | A duration formatter was about to be written for the copy | `domain.sources.humanise_duration` already existed; reused |
| 3 | `git checkout` as a mutation-probe restore silently reverted this item's own fix to a tracked file, and cannot restore untracked ones | Caught by the suite; probes now restore from a scratch copy |

## Decision recorded rather than implemented

**A failed send is not retried.** The row expires and the screen's resend control is the
remedy. Retrying in the request path would turn a provider outage into a failed API call.

## Suite

**7436 passed, 3 failed** — the three being `test_preferences_api`, verified pre-existing
on base commit `b8c6b21` and untouched by this work.
