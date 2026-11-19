---
run: run-eventpulse24-044
work_item: email-change-endpoints-and-contract
intent: account-profile-expansion
mode: confirm
checkpoint: plan
---

# Plan: Request and Confirm — Two Endpoints, and the Sends

## A premise in the work item is wrong, and the code says so

The work item says the confirm endpoint "may be anonymous", and warns that
*"`require_csrf` cannot apply to an anonymous confirm from a fresh browser — say how that
endpoint is protected instead."*

**It can, and the product already does it.** `password_reset_confirm` (`api.py:380`) calls
`require_csrf(request)` and serves callers with no session, because `GET /api/auth/csrf`
issues the token and sets the cookie for exactly this case. The frontend route fetches it
before posting.

So there is no special protection to invent. **The email-change confirm mirrors
`password_reset_confirm` exactly**, and that is the whole answer to the work item's open
question.

## The endpoints

### `POST /api/auth/profile/email` — signed in

Mirrors `password_reset_request`: `require_csrf` first, resolve the user (401 for an
anonymous caller), call `request_email_change`, **then send the two mails outside the
transaction** as `request_password_reset` does.

- **202, not 200**, matching `password_reset` — the work is accepted, not finished.
- `{202, 401, 403, 422, 429}` declared, so `ErrorOut` reaches the generated client.
- **The response is identical whether the address was free or taken.** The command returns
  `None` for taken; the handler sends nothing and answers the same 202. A test asserts
  both responses match status *and* body.
- 422 only for the two plain refusals (empty address, your own address) — neither echoes
  the address back.

### `POST /api/auth/profile/email/confirm` — session optional

Mirrors `password_reset_confirm`: `require_csrf` first, then `confirm_email_change`.

- `{200, 403, 422}`. One refusal for unknown/used/revoked/expired/race.
- **No throttle of its own**, which is `password_reset_confirm`'s existing choice — the
  token space is 32 random bytes and the request path is already limited. I follow it
  rather than invent a second policy; flagging it so you can overrule.

### The sends

`request_email_change` returns the token and both addresses; the handler sends the
confirmation to the new address and the warning to the old one, each with an idempotency
key built from the row id, as `request_password_reset` keys its send.

**Both sends happen after the command returns**, outside its transaction — the row is
committed before any mail claims it exists.

## `GET /api/auth/me` — reporting a pending change

`CurrentUserOut` gains `pending_email` — **the requested address, or `""`.**

**Decision, and the one I most want challenged.** Exposing the address puts it in every
page's payload. The alternative, a bare boolean, leaves the screen unable to say *"we sent
a link to m…@…"*, which is what a person who mistyped it needs to see. **The address is
the account holder's own data about their own pending change**, and they are the only one
who can read `me`. So: expose it, `""` when none.

## Tests

Both endpoints across every refusal; the two sends and their recipients; **free vs taken
answered identically, field for field and status for status**; `me` reporting and
clearing; anonymous confirm succeeding; missing CSRF 403; `test_no_direct_writes` green.

Then a mutation probe per test.

## The contract

`make client`, with **both** `openapi.json` and `schema.ts` committed (AD-19), and
`test_contract.py` plus `test_state_change_contract.py` green. **Operation ids read out of
the regenerated file, not assumed.**

## Files

| File | Action |
|---|---|
| `backend/apps/identity/schemas.py` | modify — two In schemas, two Out, `CurrentUserOut.pending_email` |
| `backend/apps/identity/api.py` | modify — two handlers, `me` extended |
| `frontend/lib/api/openapi.json`, `schema.ts` | regenerate and commit |
| `backend/tests/api/test_email_change_api.py` | create |

**No UI.** The screen is the next item.
