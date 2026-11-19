---
run: run-eventpulse24-044
work_item: email-change-endpoints-and-contract
intent: account-profile-expansion
date: 2026-11-19
---

# Review: Request and Confirm

## Findings

| # | Finding | Resolution |
|---|---|---|
| 1 | **The work item's premise was wrong.** It said `require_csrf` could not apply to an anonymous confirm and asked for alternative protection. `password_reset_confirm` does exactly that already. | Mirrored it. Both properties pinned: no session needed (200), no CSRF token refused (403). |
| 2 | **The `email_adapter` fixture patches a named list of modules**, and listed only the two services. The edge sends, so six tests were being answered by a **real SMTP adapter**. | `apps.identity.api` added, with the reason recorded. Any future sender must be added or its tests will quietly talk to SMTP. |
| 3 | **Two guards on `me`'s exact field set fired.** | Updated deliberately; the rationale for `pending_email` now lives in the test's docstring. |

## Decisions a reviewer should push on

- **`me` exposes the pending address, not a boolean.** It is the caller's own data about
  their own change, and a boolean leaves the screen unable to say which address a link
  went to. The cost is the address in every page's payload.
- **The confirm endpoint has no throttle of its own**, following
  `password_reset_confirm`. The token is 32 random bytes and the request path is limited.
- **The sends live at the edge, not in the command**, unlike `request_password_reset`.
  Deliberate — the command stays testable with no email port — but it is a divergence
  between two flows that otherwise mirror each other, and finding #2 is its cost.

## Suite

Re-run after the two guards were updated; the standing three `test_preferences_api`
failures are pre-existing and untouched.
