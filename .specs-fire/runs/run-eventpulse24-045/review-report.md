---
run: run-eventpulse24-045
work_item: email-change-on-the-profile-screen
intent: account-profile-expansion
date: 2026-11-19
---

# Review: Asking to Move Your Address

## Findings

| # | Finding | Resolution |
|---|---|---|
| 1 | **The resend half of the "gap" was not a gap.** The token is never stored, so a resend must mint a new link, and the request command already revokes the outstanding row. | No endpoint. Resend posts the same address again, and the old link stops working — pinned at both layers. |
| 2 | **The taken-address test was vacuous.** A mutation making the island say *"already in use"* passed all 12 tests. | Rewritten to hold the layer to what it can be held to: the success line is a template with the address substituted, no branch, no reading of the answer. The mutation now fails. |
| 3 | **A missed acceptance criterion: the expiry.** Built address/resend/cancel; the work item asks for four. The first draft of the test report ticked it off from the code rather than the criterion. | Server now sends the moment; the island formats it, with three branches tested. |
| 4 | `mt-10` is **off the spacing scale**, and off-scale classes generate no CSS at all. | `mt-12`. |
| 5 | An unescaped apostrophe in JSX copy. | Escaped. |
| 6 | `ruff --fix` had removed an import my later test needed. | Restored. Second time this session an automated fix undid something needed — the first was `git checkout` reverting a template fix in run-043. |

## Decisions a reviewer should push on

- **No "you'll be signed out elsewhere" warning**, because the design ends no sessions.
  Asserted negatively, so the day that changes, the test fails.
- **The expiry is sent as a moment, formatted by the client.** The alternative — a
  server-rendered sentence — would put copy in the API.
- **Cancel revokes rather than deletes**, keeping the history an account holder
  investigating a takeover would want.

## Suite

Backend **7463 passed, 3 failed** (the standing pre-existing `test_preferences_api`
failures). Frontend **2690 passed**. `tsc` clean; `make lint-web` back to the two
pre-existing findings.
