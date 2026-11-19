---
id: email-change-endpoints-and-contract
title: Request and Confirm — Two Endpoints, One of Them Unauthenticated
intent: account-profile-expansion
complexity: medium
mode: confirm
status: completed
depends_on:
  - email-change-mails
created: 2026-11-19
run_id: run-eventpulse24-044
completed_at: 2026-11-19T11:15:48.309Z
---

# Work Item: Request and Confirm — Two Endpoints, One of Them Unauthenticated

## Description

Two endpoints on `/api/auth`, plus what `me` must say about a change in flight.

- `POST /api/auth/profile/email` — **signed in, CSRF-checked.** Takes the new address,
  calls `request_email_change`, sends both mails. **It answers the same way whether or
  not the address is already held by another account** — the refusal that does not
  disclose, carried from the command into the wire shape, exactly as
  `request_password_reset`'s endpoint already does.
- `POST /api/auth/profile/email/confirm` — **takes a token, and the caller may be
  anonymous.** The person confirming is reading mail, possibly in another browser, and
  requiring a session would make the link work only where it was requested. This is the
  one endpoint in the intent that is **not** behind a session, which is precisely why
  its rate limiting and its refusals matter more than anywhere else.
- `GET /api/auth/me` — reports **whether a change is pending**, so the screen can say
  so. **It reports that one is pending; whether it also reports the requested address
  is a decision** — showing it helps the person who typo'd, and it also puts the
  address on every page's payload.

## Acceptance Criteria

- [ ] `POST /api/auth/profile/email` calls `require_csrf(request)` **first**, resolves
      the user, and calls the named command
- [ ] An anonymous caller gets **401**; no CSRF token gets **403**
- [ ] The response is **indistinguishable** between "address free" and "address taken" —
      asserted by a test comparing both responses field for field **and** status for
      status
- [ ] `POST /api/auth/profile/email/confirm` works **without a session**, and its
      anonymous reachability is deliberate and documented
- [ ] The confirm endpoint refuses an expired, revoked, used or unknown token with the
      **same** response — a distinguishing message is an oracle for guessing tokens
- [ ] The confirm endpoint is rate limited
- [ ] `CurrentUserOut` reports a pending change, and the decision about exposing the
      requested address is recorded with its rationale
- [ ] Every response status is **declared** so `ErrorOut` reaches the generated client
- [ ] No handler touches the ORM — `tests/architecture/test_no_direct_writes.py` green
- [ ] `make client` run; `openapi.json` **and** `schema.ts` committed and modified
      (AD-19); `test_contract.py` and `test_state_change_contract.py` green
- [ ] Operation ids read out of the regenerated `openapi.json`, not assumed
- [ ] No address and no token appears in any error `details` (AD-13)
- [ ] Tests cover both endpoints across every refusal, each with a mutation probe

## Technical Notes

- **The confirm endpoint is a `POST`, not a `GET`, even though a link opens it.** A
  `GET` that moves a login is performed by every mail scanner and link prefetcher that
  touches the message. The link lands on a **frontend page** which then posts — that
  page is the next item's job, and this item's contract must make it possible.
- **`require_csrf` cannot apply to an anonymous confirm from a fresh browser** — say how
  that endpoint is protected instead, and do not leave it as an omission.
- **`ErrorOut` is `shared.errors.ErrorOut`.**

## Dependencies

- `email-change-mails` — the request endpoint sends what that item renders.
