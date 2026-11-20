---
run: run-eventpulse24-044
work_item: email-change-endpoints-and-contract
intent: account-profile-expansion
date: 2026-11-19
---

# Report: Request and Confirm

## A premise in the work item was wrong

The work item warned that *"`require_csrf` cannot apply to an anonymous confirm from a
fresh browser — say how that endpoint is protected instead."*

**It can, and the product already does it.** `password_reset_confirm` calls
`require_csrf(request)` *and* serves callers with no session, because `GET /api/auth/csrf`
issues the token and sets the cookie for exactly that case. So there was no special
protection to invent: the email-change confirm mirrors it, and both properties are pinned
— it answers a caller with **no session** (200) and refuses one with **no CSRF token**
(403).

## Tests

| Suite | Result |
|---|---|
| `tests/identity/test_email_change_api.py` | **15 passed** |
| `tests/api/test_contract.py` + `tests/architecture/` | **1057 passed** |
| `make client` | both `openapi.json` and `schema.ts` regenerated and committed (AD-19) |

Operation ids were **read out of the regenerated file**, not assumed:

```
POST /api/auth/profile/email          -> apps_identity_api_request_email_change_endpoint
POST /api/auth/profile/email/confirm  -> apps_identity_api_confirm_email_change_endpoint
CurrentUserOut: [email, id, name, onboarding, pending_email]
```

## Mutation probes

| Mutation | Result |
|---|---|
| The taken-address case answers differently (**the oracle**) | 1 failed |
| The warning mail is never sent | 2 failed |
| The confirm endpoint requires a session | 1 failed |
| `me` stops reporting the pending address | 1 failed |
| CSRF is not checked on the request endpoint | 1 failed |

## What the first test run exposed

Six tests failed with `'SmtpEmailAdapter' object has no attribute 'sent'`. The
`email_adapter` fixture patches `get_email_port` in a **named list of consumer modules**,
and it listed only the two services. **The email-change sends happen at the edge**, so
`apps.identity.api` is a third consumer — and without it a test would have been answered
by a real SMTP adapter rather than the in-memory one.

The fixture now lists it, with the reason recorded. **This is a seam worth knowing about**:
any future module that sends mail must be added there, or its tests will quietly talk to
SMTP.

## Two guards the wider suite fired, and why they are right

```
FAILED tests/identity/test_auth_api.py::test_me_returns_..._and_nothing_else
FAILED tests/identity/test_profile_api.py::test_me_still_carries_no_password_field
```

Both pin the **exact field set** `me` returns — one as a whole-dict equality, one as a
set. `CurrentUserOut`'s own docstring says it has *"no password field, no permission field
and no catch-all, so nothing internal can ride along"*, and these two tests are how that
sentence is enforced rather than merely asserted.

**Adding a field to `me` is meant to cost this edit.** It did, and both were updated
deliberately, with the reasoning for `pending_email` written into the first test's
docstring: the address rather than a boolean, and on `me` rather than behind its own
endpoint. A field that slipped in without this failure would be a field nobody decided to
add.

## A divergence from the house pattern, stated rather than hidden

`request_password_reset` **sends from inside the service**. `request_email_change` does
not: it returns the token and both addresses, and the endpoint sends.

That was decided in run-042 and kept here deliberately — the command stays testable with
no email port at all, and the two messages are the edge's concern. **It is still a
divergence**, and the cost is the fixture seam above. If you would rather the command
owned its sends, say so; it is a small move and it would make the two auth flows match.

## Acceptance criteria

| Criterion | State |
|---|---|
| `require_csrf` first on both | ✅ |
| Anonymous caller 401 on request; **no session needed** on confirm | ✅ |
| Free and taken **indistinguishable**, status and body | ✅ the oracle test |
| One refusal for every token failure | ✅ 422, no reason given |
| `me` reports the pending change, decision recorded | ✅ the address, not a boolean |
| Every status declared so `ErrorOut` reaches the client | ✅ |
| No handler touches the ORM for a write | ✅ `test_no_direct_writes` green |
| `make client` run, both artifacts committed | ✅ |
| No address or token in any error body | ✅ asserted on the 422 |
| Every test can fail | ✅ five probes |

## Not in this item

No UI. The screen — three pending states, resend, cancel, and the route the link lands on
— is `email-change-on-the-profile-screen`.
