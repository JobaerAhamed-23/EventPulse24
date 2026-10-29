---
run: run-eventpulse24-020
work_item: auth-api-and-session-seam
intent: onboarding-and-account
generated: 2026-10-29
mode: confirm
---

# Implementation Walkthrough: Auth API & Session Seam Replacement (FR-4, AD-5, AD-18, AD-19, D13)

## Summary

Seven auth endpoints, one published session resolver, and a CSRF check that actually
matches Django's own rules.

The item's central problem is that **a session is a security boundary, and the boundary
has to be in exactly one place**. "Who is making this request?" is asked by every
authed endpoint in the project, and if each one answers it differently — or if the answer
comes from the request body — then scoping can be forged. So `identity` publishes the
resolver, every other app asks through it, and no endpoint accepts a user id.

The review found that the first implementation got the *enumeration* safety right in the
body and wrong in the headers, trusted a header the caller controls, skipped one of
Django's two CSRF branches, and kept a session it then silently destroyed. All four are
fixed and pinned.

---

## Structure Overview

```
backend/
├── apps/identity/
│   ├── api.py               ← the seven endpoints: csrf, signup, signin, signout, me, reset, reset/confirm
│   ├── api_auth.py          ← THE SEAM: current_user, require_csrf, issue_csrf_token
│   ├── schemas.py           ← the request and response shapes
│   └── services/            ← the named commands (AD-5): sign_up, authenticate, password_reset, session, throttle
├── apps/personalization/
│   └── auth.py              ← a delegation to identity's resolver — not a second implementation
├── config/
│   ├── errors.py            ← the one exception→HTTP mapping
│   ├── env.py               ← TRUST_FORWARDED_FOR
│   └── settings.py
└── tests/identity/          ← 61 tests for this item
```

The flow of a request is deliberately short:

```
browser
  │
  ▼
POST /api/auth/signin   ──▶ require_csrf()      ──▶ Django's own CSRF rules
                            authenticate()       ──▶ the service, which throttles and checks
                            django_login()       ──▶ the session is created
  │
  ▼
GET /api/personal/events
  │
  ▼
current_user(request)    ──▶ Django's session      ──▶ the user id, or a 401
```

`current_user` is the only place a request's identity is established. The personal
module's `auth.current_user` is the *same object* — not a copy — so the two cannot
drift.

---

## Architecture

### Pattern Used

**Service layer with a published interface.** The services own the writes and the
business rules; the endpoints own the HTTP projection. The endpoint layer never imports
`apps.identity.models` — the `models-identity` import contract enforces that — so other
apps reach `identity` through a named, published interface rather than through its
tables.

### Layer Structure

```text
┌─────────────────────────────────────────────┐
│  HTTP edge — apps/identity/api.py           │
│  CSRF, body parsing, wire shape             │
│  (no writes, no model imports)              │
├─────────────────────────────────────────────┤
│  Published interface — api_auth.py          │
│  current_user, require_csrf, issue_csrf_token│
├─────────────────────────────────────────────┤
│  Services — apps/identity/services/         │
│  sign_up, authenticate, password_reset,     │
│  session, throttle                          │
├─────────────────────────────────────────────┤
│  Models — apps/identity/models.py           │
│  (private to identity; the contract guards) │
└─────────────────────────────────────────────┘
```

---

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/apps/identity/api.py` | The seven endpoints. CSRF, body parsing, the wire shape — and no writes of its own |
| `backend/apps/identity/api_auth.py` | The published resolver, the CSRF check, the token issuer. This is the seam |
| `backend/apps/identity/schemas.py` | The request and response shapes |
| `backend/apps/personalization/auth.py` | A delegation to `identity`'s resolver — not a second implementation |
| `backend/tests/identity/test_auth_api.py` | 50 tests: the endpoints, the enumeration safety, the CSRF rules, the throttle, the session lifecycle |
| `backend/tests/identity/test_session_seam.py` | 11 tests: the seam is in one place, and a real session works on the personal endpoints |
| `backend/tests/csrf.py` | The shared CSRF client helper — the token, the `Origin`, the refusal |

### Modified

| File | Changes |
|------|---------|
| `backend/apps/identity/services/sign_up.py` | No session, and no sign-in throttle charge. The service says nothing about whether it created the account |
| `backend/apps/identity/services/authenticate.py` | The sign-in throttle, keyed on the IP and on the account |
| `backend/apps/identity/services/session.py` | The docstring on the kept session: the row survives, but the edge must re-stamp the hash |
| `backend/apps/identity/services/password_reset.py` | The docstring on `keep_session_key` |
| `backend/apps/identity/services/throttle.py` | The bucket limits and the two key derivations |
| `backend/config/env.py` | `trust_forwarded_for`, off by default |
| `backend/config/settings.py` | `TRUST_FORWARDED_FOR` |
| `backend/config/errors.py` | A wrong comment about the status of `AuthenticationFailedError` |
| `backend/tests/identity/conftest.py` | The module patching became order-independent |
| `frontend/lib/api/openapi.json` | Regenerated by `make client` |
| `frontend/lib/api/schema.ts` | Regenerated by `make client` |

---

## Key Implementation Details

### 1. The session resolver is published, and there is exactly one of them

`apps/identity/api_auth.py` exports `current_user`. It reads the user id from Django's
session — **never from the request body** — and returns `None` for an anonymous request.

`apps/personalization/auth.py` re-exports it:

```python
from apps.identity.api_auth import current_user
```

The two names are the *same object*. A copy would let them drift, which is the exact
failure the one-place rule exists to prevent, so a test asserts the identity of the two
objects and another asserts that the personal module has no `def current_user` of its
own.

`test_no_endpoint_takes_a_user_id_as_input` walks the generated OpenAPI schema and
fails if any endpoint under `/api/auth` or `/api/personal` accepts a `user_id` or `user`
field. There is nowhere for a forged id to come from.

### 2. Enumeration safety is enforced on the response, headers included

AD-18 wants a known address and an unknown address answered identically. The bodies
always were. The headers **were not**, because sign-up established a session — so a
taken address answered with a `Set-Cookie: sessionid` and a `Vary: Cookie`, and a free
one answered with neither.

The fix is to remove the session from sign-up entirely. The cookie's presence *is* the
oracle, so there is no way to keep the sign-up session and make the headers identical at
the same time. `signin` is now the one place a session is created.

The test compares the **whole header set**, the **cookie set** and the `Vary` value, not
just the body:

| Request | Body | Headers |
|---------|------|---------|
| New address, any password | `201 {"status":"accepted"}` | no `sessionid` |
| Taken address, wrong password | `201 {"status":"accepted"}` | no `sessionid` |
| Taken address, right password | `201 {"status":"accepted"}` | no `sessionid` |

### 3. The CSRF check mirrors Django's own two branches

Django Ninja sets `csrf_exempt = True` on every view it builds, and Ninja's own
cookie-CSRF check only runs for routers with a cookie-based `auth=` — which this router
does not have. So the check is made explicitly, through Django's own middleware.

Django's `process_view` has two branches, and **both** are reproduced:

| Request | Django's branch | What the check does |
|---------|------------------|---------------------|
| Has an `Origin` | origin check | compare against `CSRF_TRUSTED_ORIGINS` |
| No `Origin`, over HTTPS | referer check | the MITM fallback: compare the `Referer` |
| No `Origin`, not HTTPS | neither | the token check alone |

The referer fallback is the branch that is easy to miss, and it is the one that exists
for the network attacker: an active MITM can suppress `Origin` on a request it forwards
to us, and the CSRF secret is a cookie rather than a session secret, so a MITM that can
plant the cookie has both halves of the token.

The check calls Django's own `_origin_verified`, `_check_referer` and `_check_token`
rather than re-implementing them. Django's test-client escape hatch
(`request._dont_enforce_csrf_checks`) is **not** consulted — otherwise the protection
would silently vanish under the default test client and the tests would pass without the
check ever running.

### 4. The throttle buckets are one operation each

| Bucket | Charged by | Per-IP | Per-account |
|--------|-----------|--------|-------------|
| `sign_up` | `POST /api/auth/signup` | ✓ | ✓ |
| `sign_in` | `POST /api/auth/signin` | ✓ | ✓ |
| `reset` | `POST /api/auth/password-reset` | ✓ | ✓ |

Sign-up originally charged **two** buckets — its own, plus the sign-in bucket for the
authentication attempt that followed. So an attacker naming a victim's address could
spend the victim's own sign-in allowance and lock the real owner out. Removing the
sign-up session removed the second charge with it.

The account key is a SHA-256 digest of the normalised email, so the address itself
never becomes a key.

### 5. The caller's IP comes from `REMOTE_ADDR` unless a trusted edge says otherwise

`X-Forwarded-For` is attacker-controlled: Next's rewrite forwards the browser's headers
as they arrived. Reading it unconditionally let any caller mint a fresh throttle bucket
per request, which defeated the per-IP limit completely — the review reproduced it with
twenty spoofed IPs and twenty different buckets and zero 429s.

The header is read only when `settings.TRUST_FORWARDED_FOR` is on, which is **off by
default**. The value must also parse as an IP address before it is used, so it cannot be
padded with arbitrary text. It is never logged and never stored (AD-13); it only ever
becomes part of a throttle key.

### 6. The reset keeps the session it was made from — and says so in the code

The reset service keeps the session row and ends the account's other sessions. The
*edge* then has to re-stamp the session with the new password hash, because Django
compares `user.get_session_auth_hash()` against the session's stored hash on every
request and **flushes the session** on a mismatch.

Django's `update_session_auth_hash` cannot do this here. It stamps only when
`request.user == user`, and by the time the endpoint body runs, `AuthenticationMiddleware`
has already compared the stale hash, flushed the session and left `request.user`
anonymous — so the guard is false and the helper writes nothing, silently.

So the hash is written directly:

```python
session[HASH_SESSION_KEY] = user.get_session_auth_hash()
session.cycle_key()
```

The session key is cycled too, so a key that was on the wire before the reset cannot be
reused afterwards.

---

## Security Considerations

| Concern | Approach |
|---------|----------|
| Account enumeration | Byte-identical **and** header-identical responses for a known and an unknown address. Sign-up establishes no session, so there is no `Set-Cookie` to distinguish them |
| Forged user scoping | The user id comes from the session only. No endpoint accepts a user id; a schema-walking test enforces it |
| CSRF | Django's own rules, both branches, applied explicitly because Ninja exempts every view it builds |
| Brute force | Three throttle buckets, each with a per-IP and a per-account limit, keyed on a digest of the normalised email |
| Rate-limit bypass | `X-Forwarded-For` is trusted only when a deployment says a proxy overwrites it (`TRUST_FORWARDED_FOR`, off by default) |
| Session fixation | The session key is cycled on a password reset; Django's `login()` rotates the token on sign-in |
| Stale session after a password change | The kept session is re-stamped with the new hash, so it keeps working — and only that one session does |
| Password storage | Django's hashers, via `UserFactory` / `create_user`. The plain password is never stored, logged or returned |
| Secret leakage | The IP is never logged or stored. The email is never logged. The password hash never appears in a response |

---

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| The resolver must be cheap | It reads Django's session — one cached lookup per request — and nothing else. It touches no table of its own |
| Throttle lookups must not be a hot path | The throttle adapter is behind a port; the in-memory adapter is a dict lookup, Redis is one `GET`/`INCR` pair |
| The account key must not leak the address | SHA-256 of the normalised email, so the key is fixed-length and the address is not recoverable from it |
| `me` must not cost a query when the session is anonymous | The anonymous path returns before any user lookup |

---

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where the session resolver lives | `apps/identity/api_auth.py`, published | `identity` owns the user and the auth flows, so it owns the answer to "who is this request?". The old seam in `personalization` was a placeholder waiting to be replaced |
| What happens to the old seam | A delegation, not a copy | Two implementations would drift. The test asserts the two names are the *same object* |
| Whether sign-up establishes a session | No | The `Set-Cookie` header is a confirmed-password oracle. There is no way to keep the session and make the headers identical |
| Where the CSRF check lives | In the resolver, applied explicitly | Ninja exempts every view it builds, and Ninja's own cookie-CSRF check does not run for a plain-function resolver |
| How to implement the CSRF check | By calling Django's own methods | Re-implementing the origin rules would drift from Django and from `CSRF_TRUSTED_ORIGINS` |
| How to re-stamp the session after a reset | Write `HASH_SESSION_KEY` directly | `update_session_auth_hash`'s guard cannot be satisfied at that point in the request, and it fails *silently* |
| Where the caller's IP comes from | `REMOTE_ADDR` by default | `X-Forwarded-For` is attacker-controlled. The deployment has to say a proxy overwrites it |
| Whether to trust the forwarded header at all | Yes, but off by default and IP-validated | A deployment behind a proxy needs it; a directly-connected client must not be able to forge it |
| Whether `me` includes the onboarding status | Not yet | The work item says so: the status is read through `personalization`'s published interface once `onboarding-state-and-interests` exists |
| How errors become HTTP responses | One mapping in `config/errors.py` | No per-endpoint `try`/`except` building HTTP responses by hand |

---

## Deviations from Plan

1. **Sign-up no longer establishes a session.** The work item's acceptance criteria say
   "sign-up and sign-in establish a session". The review found that a session on sign-up
   leaks account existence through the response headers — a `Set-Cookie` on one response
   and not on another is an oracle of the same strength as a different body, and a
   stronger one, since it confirms the **password**. AD-18 requires byte-identical
   responses; the headers are part of the response.

   The criterion is met by the **frontend** signing in after signing up, which is one
   extra request and one place where a session is created rather than two.
   `frontend-auth-surfaces` carries the frontend side of that flow.

2. **Sign-up charges one throttle bucket instead of two.** A consequence of the same
   change, and a fix in its own right: an attacker naming a victim's address could
   otherwise spend the victim's own sign-in allowance and lock the real owner out.

3. **`TRUST_FORWARDED_FOR` is a new setting.** The per-IP throttle limit did not exist
   without it. It is off by default, so the default is the safe one, and a deployment
   behind a rewriting proxy can turn it on deliberately.

4. **The password reset's session is re-stamped at the edge, not in the service.** The
   service already kept the row. The hash is the edge's job because the edge is what
   knows the request's session.

---

## Dependencies Added

| Package | Why Needed |
|---------|------------|
| (none) | No new package. The implementation uses Django's own session, auth and CSRF machinery, which was already a dependency |

---

## How to Verify

1. **The whole backend suite, with coverage**
   ```bash
   cd backend && .venv/bin/python -m pytest --cov --cov-report=term
   ```
   Expected: `2710 passed`, coverage `98.99%`, and `apps/identity/api.py`,
   `apps/identity/api_auth.py`, `apps/identity/schemas.py` and
   `apps/personalization/auth.py` all at **100%**.

2. **This item's own tests**
   ```bash
   cd backend && .venv/bin/python -m pytest tests/identity/test_auth_api.py tests/identity/test_session_seam.py -v
   ```
   Expected: `61 passed`.

3. **The linter, the format check and the import contracts**
   ```bash
   make lint-backend
   ```
   Expected: `All checks passed!` and `Contracts: 17 kept, 0 broken.`

4. **The committed schema matches the live API** (AD-19)
   ```bash
   make client && git status --short frontend/lib/api/
   ```
   Expected: no drift. `tests/api/test_contract.py` asserts the same thing.

5. **The frontend suite**
   ```bash
   make test-web
   ```
   Expected: `149 passed (16 files)`.

6. **Manually: sign-up answers identically for a taken and a free address**
   ```bash
   curl -si -X POST http://127.0.0.1:8000/api/auth/signup \
     -H 'Content-Type: application/json' \
     -H "X-CSRFToken: $TOKEN" \
     -H 'Origin: http://127.0.0.1:3000' \
     -d '{"email":"taken@example.test","password":"correct-horse-battery"}'
   ```
   Expected: `201`, body `{"status":"accepted"}`, and **no `Set-Cookie: sessionid`** —
   whether or not the address is taken.

7. **Manually: a real session reaches a personal endpoint**
   ```bash
   curl -si -X POST http://127.0.0.1:8000/api/auth/signin \
     -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" \
     -H 'Origin: http://127.0.0.1:3000' \
     -d '{"email":"you@example.test","password":"..."}'
   curl -si http://127.0.0.1:8000/api/auth/me -H "Cookie: sessionid=$SESSIONID"
   ```
   Expected: the first returns `200` and a `sessionid`; the second returns `200` with
   the id and the email.

8. **Manually: the password reset keeps its own session**
   Sign in, request a reset, confirm it with the token from the email, then call
   `/api/auth/me` with the same cookie.
   Expected: `200`. Without the fix: `401`.

---

## Test Coverage

- Tests added: 61 (50 in `test_auth_api.py`, 11 in `test_session_seam.py`)
- Coverage: 100% on the item's four modules; 98.99% across the backend
- Status: passing — 2710 backend, 149 frontend, 0 failures

---

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated (if applicable)
- [x] Developer notes captured

---

## Developer Notes

**The Django session hash trap.** Django compares `user.get_session_auth_hash()` with
the session's stored `_auth_user_hash` on **every** request, and flushes the session on
a mismatch. That check happens in `AuthenticationMiddleware.process_request`, *before*
your view runs. So by the time you try to fix a changed password, `request.user` is
already anonymous and `update_session_auth_hash` will not stamp anything. Write
`session[HASH_SESSION_KEY] = user.get_session_auth_hash()` yourself.

**A helper that fails silently is worse than one that raises.** `update_session_auth_hash`
did not raise when its guard failed — it wrote nothing. The endpoint returned 200, the
service had done exactly what it was asked, and the session was gone. If a helper's
failure is a no-op, every caller has to verify the effect, and the test has to assert
the *effect* — not the status code.

**A body-identical response can still be an oracle.** The first implementation compared
`response.content` and passed. The `Set-Cookie` header told a different story. When
asserting enumeration safety, compare the whole header set and the cookie set too. And
remember *which* pair of requests exposes the difference: for sign-up it is a new
address against a taken address with a **wrong** password — one verifies, one does not.

**Django's CSRF check has two branches, not one.** The origin branch is the one people
remember. The referer branch is the one that protects HTTPS from a network attacker.
Read `CsrfViewMiddleware.process_view` rather than assuming.

**Ninja exempts every view it builds from Django's CSRF middleware.** `csrf_exempt = True`
in `ninja/operation.py`. If your router has no cookie-based `auth=`, nothing checks
CSRF for you.

**The test client can turn your protection off.** Django's test client sets
`request._dont_enforce_csrf_checks` unless it is built with
`enforce_csrf_checks=True`. `ninja.utils.check_csrf` honours that flag, so using it
means the protection silently vanishes under the default test client — the tests pass
without the check ever running. Apply the rules directly, and do not consult the flag.

**`X-Forwarded-For` is the caller's, not yours.** Next's rewrite forwards the browser's
headers as they arrived. If you key a rate limit on that header without an explicit
trust decision, there is no rate limit.

**A stale `.next/` breaks the frontend typecheck.** `rm -rf frontend/.next` and re-run
`next typegen` if `tsc` reports duplicate identifiers in `.next/types/`. The directory is
git-ignored, so it is a local artefact, not a change you committed.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-020*

---

# Implementation Walkthrough: Onboarding State, Interests & Digest Preferences (FR-1)

**Work Item:** onboarding-state-and-interests
**Intent:** onboarding-and-account
**Mode:** confirm
**Generated:** 2026-10-29

## Summary

The server-side state for FR-1's three-step onboarding flow: the ten interest chips as a
single constant, the user's picks, the digest delivery preference, and the progress that
says where they are — with a seven-day resume window and a terminal completion.

The item's central problem is that **the flow's rules must not live at the HTTP edge**.
"Interests replace", "at most three picks", "a completed onboarding is never reopened",
"the window is inclusive" — each of these is a rule the next caller will need, and a rule
that only the edge knows is a rule the next caller will not have. So all of them live in
one service module, and the endpoints are a thin projection of it.

The second problem was quieter: **a read that writes, and races that answer 500**. Both
were found in the code review and both are now properties of the module, not accidents.

## Structure Overview

The three tables are owned by `personalization` (AD-16). One service module is the only
way they change; seven endpoints under `/api/personal/onboarding` project its plain data
onto the wire; and `GET /api/auth/me` reads a two-field summary of it through the same
published service.

```text
┌──────────────────────────────────────────────────────────┐
│  Presentation                                            │
│  apps/personalization/api.py   — 7 endpoints, thin       │
│  apps/identity/api.py         — `me` reads the summary   │
├──────────────────────────────────────────────────────────┤
│  Application                                             │
│  apps/personalization/services/onboarding.py             │
│    · the only writer of the three tables                  │
│    · rules: replace · ≤3 · inclusive window · terminal    │
│    · per-user advisory lock (pg_advisory_xact_lock)       │
├──────────────────────────────────────────────────────────┤
│  Domain                                                  │
│  shared/constants.py   — the 10 chips, the window, the   │
│                          3 steps, the digest defaults    │
│  domain/timezones.py   — canonical_zone, the one         │
│                          validator (shared with events)  │
│  domain/errors.py      — 3 typed errors                  │
├──────────────────────────────────────────────────────────┤
│  Infrastructure                                          │
│  personal schema: interest · onboarding_progress ·       │
│                   digest_preference                      │
└──────────────────────────────────────────────────────────┘
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/apps/personalization/services/onboarding.py` | The commands and queries — the only way the three tables change |
| `backend/apps/personalization/migrations/0005_digestpreference_interest_onboardingprogress.py` | The three tables, their constraints, and the frozen step cap |
| `backend/tests/personalization/test_onboarding_constants.py` | The ten chips, the three-step cap, the window, the defaults |
| `backend/tests/personalization/test_onboarding_models.py` | The models' constraints, as the database holds them |
| `backend/tests/personalization/test_onboarding_commands.py` | The commands' rules |
| `backend/tests/personalization/test_onboarding_api.py` | The seven endpoints' contract |
| `backend/tests/personalization/test_onboarding_concurrency.py` | The commands under concurrency |

### Modified

| File | Purpose |
|------|---------|
| `backend/shared/constants.py` | The onboarding constants |
| `backend/apps/personalization/models.py` | `Interest`, `OnboardingProgress`, `DigestPreference` |
| `backend/apps/personalization/schemas.py` | The onboarding wire shapes |
| `backend/apps/personalization/api.py` | The seven endpoints |
| `backend/apps/identity/schemas.py` | `CurrentUserOut` gained the onboarding status |
| `backend/apps/identity/api.py` | `me` reads the onboarding status |
| `backend/domain/errors.py` | Three typed errors |
| `backend/tests/identity/test_auth_api.py` | `me`'s payload changed |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | Regenerated by `make client` |

## Architecture

### Pattern Used

**Service layer with a command/query split.** Commands are named functions in
`apps/personalization/services/`, each taking an explicit `Actor` and an explicit `now`,
each opening one `transaction.atomic(using=PERSONAL)`, each writing its audit row inside
that transaction, and each returning plain data rather than a model instance (AD-5).
Queries are the same functions without the writes.

### Layer Structure

```text
┌─────────────────────────────┐
│      Presentation           │  api.py — 7 endpoints
├─────────────────────────────┤
│      Application            │  services/onboarding.py
├─────────────────────────────┤
│        Domain               │  shared/constants.py, domain/timezones.py
├─────────────────────────────┤
│     Infrastructure          │  the personal schema
└─────────────────────────────┘
```

## Domain Model

### `Interest` — one chip the user picked

| Property | Type | Rule |
|----------|------|------|
| `user_id` | UUID | Held **by value** (OQ-8) — no FK to `User`, no `GenericForeignKey` |
| `chip_key` | str(64) | A stable slug from `INTEREST_CHIPS`; the **label is not stored** |
| — | constraint | `UNIQUE (user_id, chip_key)` — the same chip twice is held by the database |

The label is not stored because it is prose: a renamed label must not orphan a stored
pick. The key is the contract — what the API accepts, what the database holds, and what
identifies a chip forever.

### `OnboardingProgress` — where the user is

| Property | Type | Rule |
|----------|------|------|
| `user_id` | UUID | By value (OQ-8) |
| `current_step` | int | `CHECK (1 ≤ current_step ≤ 3)` — the database's copy of FR-1's cap |
| `last_advanced_at` | datetime | What the resume window is measured against |
| `completed_at` | datetime \| null | Set when onboarding ends; makes completion **terminal** |
| — | constraint | `UNIQUE (user_id)` — one row per user |

The row holds the *position*, not the step's name, because the resume rule is about the
position. The name is resolved through `ONBOARDING_STEPS`, so the two cannot drift.

### `DigestPreference` — when and where the digest arrives

| Property | Type | Rule |
|----------|------|------|
| `user_id` | UUID | By value (OQ-8) |
| `delivery_time` | time | A **local wall clock** — `tzinfo` is always null |
| `timezone` | str(64) | An IANA zone; validated by the command, not by a constraint |
| — | constraint | `UNIQUE (user_id)` — one row per user |

**The wall clock plus a zone is the whole preference.** Storing a UTC instant instead
would be wrong in a way that only shows up twice a year: the user says "9am", and a UTC
instant is "9am once, then 8am or 10am after a DST change".

**Why a dedicated model and not a `PREFERENCE_GRAPH`.** A graph is a structure for a
*set* of preferences with edges between them. A delivery time and a zone are a single
value with two parts, read as a unit and written as a unit. A graph would add a node
type, an edge type and a traversal for one row. The shape is reconsidered when a second,
genuinely separate preference arrives — and the reasoning is recorded in the model, so
the next reader knows the decision was deliberate.

## Security Considerations

| Concern | Approach |
|---------|----------|
| **Authentication** | All seven endpoints inherit the router's `auth=current_user` — the session resolver, never a user id from the body |
| **Scoping** | The user id comes from the session alone; no endpoint accepts one as input. `test_a_user_id_in_the_payload_is_ignored` pins it |
| **CSRF** | Every unsafe method is checked by `require_csrf`; the `GET`s are safe **by construction** — the read never writes (see below) |
| **Input validation** | The chip keys are checked against the constant; the zone by `canonical_zone` — the same validator personal events use; the delivery time by an explicit wall-clock check |
| **Enumeration** | Not applicable — every endpoint requires a session |
| **Cross-site writes** | **The read is read-only.** A write behind a `GET` would be a cross-site write, because Django Ninja exempts every view from Django's CSRF middleware and the resolver only checks unsafe methods |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| The chip list is read on every onboarding render | It is a module constant — no query at all |
| The user's chips are read | One indexed query on `user_id` |
| The progress row is read | One indexed query; `last_advanced_at` is compared in Python, not in SQL |
| Concurrent commands | One transaction-scoped advisory lock per user — a single `SELECT pg_advisory_xact_lock(...)` |
| `me` is on every authenticated request | It reads **and writes nothing** — no lock, no UPDATE |

The last row matters more than it looks. `me` is on the hot path; a read that took a row
lock and issued an `UPDATE` for every user whose flow had expired would put a write on
the endpoint every request passes through.

## Decisions Made

1. **`PUT` for the two setters, `POST` for the three movers.** `PUT` replaces a resource
   — that is what it means, and `POST` would imply a create. `POST` for the transitions,
   which are not idempotent replacements of a body.

2. **The chip key is the contract; the label is prose.** They are separate fields so a
   renamed label leaves every stored pick valid. The API takes the key and refuses the
   label (`test_a_label_is_not_a_key`).

3. **A duplicate key in one payload is deduplicated, not refused.** The database
   constraint forbids a duplicate *row*; a caller sending the same key twice has not made
   a mistake worth a refusal.

4. **The read never writes; the restart is a command.** The original design wrote the
   restart on read, so two reads a second apart agreed. The new design *derives* the
   answer from the stored facts, so they still agree — and the read is safe, which the
   old one was not.

5. **A transaction-scoped advisory lock, not a row lock.** A row lock can only lock a row
   that exists, and the case that matters most is the one where none does: a user with no
   interests and no progress row yet. The lock is on a *key*, so it works either way, and
   it is released when the transaction ends, so a crashed worker cannot wedge a user.

6. **The digest default is *written*, not assumed.** A user who skips step 3 gets a real
   row with a real value, so `delivery` reads one row rather than branching on "was it
   set?".

7. **Completion is terminal for the *flow*, not for the preferences.** The three movers
   refuse a completed user with a 409; the two setters do not. A user who finished
   onboarding may still change their interests or their digest time — FR-1 says the flow
   is never reopened, not that the preferences are frozen.

## Deviations from Plan

1. **The read became read-only.** The plan had the restart written on read, "so two reads
   a second apart agree about the step". The code review found that this made
   `GET /api/auth/me` a mutating method — and since a `GET` is never CSRF-checked, that
   was a **cross-site write**. The plan's *goal* (two reads agree) is now met more
   strongly: the answer is derived from `last_advanced_at` and the window, so it does not
   depend on a write having happened.

2. **The concurrency guarantee was added.** The plan did not mention concurrent requests.
   The review found that two concurrent writes for the same user produced a raw
   `IntegrityError` — a 500 — from a unique constraint. A new test file
   (`test_onboarding_concurrency.py`, 9 tests) and the per-user advisory lock were added.

3. **`DigestPreferenceOut` is nested inside `OnboardingStateOut`** rather than being a
   top-level endpoint response. The plan sketched the schema set; the nesting keeps the
   digest preference's shape in one place, since it is always read as part of the state.

4. **One existing test was rewritten, not just added.** `test_the_restart_is_written_not_recomputed`
   pinned the read's write. It was replaced by three tests of the new contract. The old
   assertion was not a regression guard for anything the work item asked for — it was a
   guard for the defect.

## Dependencies Added

**None.** No new Python packages, no new npm packages, no new infrastructure. The
advisory lock uses Postgres, which the project already depends on, through the same
pattern `apps.ingestion` already uses for its dedup locks.

## How to Verify

### The commands

```bash
cd backend

# The item's own tests
.venv/bin/python -m pytest \
    tests/personalization/test_onboarding_constants.py \
    tests/personalization/test_onboarding_models.py \
    tests/personalization/test_onboarding_commands.py \
    tests/personalization/test_onboarding_api.py \
    tests/personalization/test_onboarding_concurrency.py -q

# The whole suite, with coverage
.venv/bin/python -m pytest tests/ -q --cov --cov-report=term-missing

# The linter, the contracts, and the migration drift
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/lint-imports
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run

# AD-19: the client regenerates with no drift
make client && git status --short frontend/lib/api/

# The frontend
pnpm --dir frontend test
cd frontend && ./node_modules/.bin/tsc --noEmit
```

**Expected:** 104 item-scoped tests pass; 2819 backend tests pass; 98.96% coverage with
155 files at 100%; ruff clean; 17/17 contracts kept; no migration drift; the committed
schema matches the regenerated one; 149 frontend tests pass; the typecheck is clean.

### Manual scenarios

**The chip list comes from the server.** Sign in, `GET /api/personal/onboarding/interest-chips`
→ ten chips in the mockup's order, each with a `key` and a `label`. Change a label in
`shared/constants.py`, reload, and the change is in the response — the frontend holds no
second copy.

**Interests replace.** `PUT /api/personal/onboarding/interests` with two keys → 200 and
two chips. `PUT` again with one → 200 and **one** chip, not three. `PUT` with four →
422 `too_many_interests`, and nothing is written. `PUT` with `"underwater_basket_weaving"`
→ 422 `unknown_interest`, and the offending key is named.

**Zero picks is valid.** `PUT` with `[]` → 200, and the set is empty. That is how the
step is skipped.

**The digest preference.** `PUT /api/personal/onboarding/digest-preference` with
`{"delivery_time": "09:30", "timezone": "America/Los_Angeles"}` → 200. With
`"Mars/Olympus_Mons"` → 422. With `"Etc/UTC"` → 200, and the stored zone is `"UTC"`.

**The flow moves.** `POST /api/personal/onboarding/step` → step 2. Again → step 3.
Again → **complete**, `current_step` null. `POST` again → **409**
`onboarding_already_complete`.

**Skipping works with no input at all.** `POST /api/personal/onboarding/step/skip`
three times → complete, with an empty interest set and the default digest preference
written. `POST /api/personal/onboarding/skip-all` → complete in one call.

**The window.** Leave the flow at step 3, wait out the seven days (or move
`last_advanced_at` back in the database), then `GET /api/personal/onboarding` → **step 1**.
Check the `onboarding_progress` row: it is **unchanged** — the read reported the restart,
it did not perform one. Now `POST /api/personal/onboarding/step` → the row moves for
real.

**`me` carries the status and not the settings.** `GET /api/auth/me` → the id, the
email, and `{"onboarding": {"completed": false, "current_step": 1}}`. Give the user
interests and a digest preference first — neither appears.

**Concurrency.** Two `PUT`s for the same user at once → both answer 200, and the user
ends with one interest set. Two `POST`s to `/step` at once → one progress row.

## Test Coverage

- Tests added: 104 (11 constants, 17 models, 42 commands, 26 API, 9 concurrency — one
  command test was rewritten by the review)
- Coverage: 100% on `apps/personalization/services/onboarding.py`; 98.96% across the backend
- Status: passing — 2819 backend, 149 frontend, 0 failures

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues remaining — the review's five findings are all fixed and revert-verified
- [x] Documentation updated — the module docstring states both new guarantees
- [x] Developer notes captured

## Developer Notes

**A `GET` that writes is a cross-site write.** Django Ninja exempts every view it builds
from Django's `CsrfViewMiddleware`, and this project's own check — in
`apps.identity.api_auth.require_csrf` — runs on **unsafe methods only**. So any write
behind a `GET` can be triggered by a hostile page with a plain `<img src>`, and no token
is needed. If a read ever needs to mutate, that mutation has to become a command. The
tell is a service function named `get_*` that opens a transaction.

**A unique constraint is not an error handler.** The three models carry unique
constraints, and the commands were written as lookup-then-write. Two concurrent requests
both found no row and both inserted, and the loser got a raw `IntegrityError` — a 500
where the caller should have got an answer. The docstring even said the constraint
"caught" the second write. It raised; it did not catch. A constraint is the last line of
defence, and a race that reaches it is a race that was never designed for.

**A row lock cannot lock a row that does not exist.** The first fix for the race was
`select_for_update()` plus an `IntegrityError` retry. It worked — and it was redundant.
The case that matters most is a user with no rows *yet*, which is precisely the case a
row lock cannot cover. A `pg_advisory_xact_lock` on a key derived from the user id
covers both, and it is released when the transaction ends, so a crashed worker cannot
wedge a user. The codebase already used this pattern in `apps.ingestion`. A revert that
removed the row locks and kept the advisory lock still passed every test — which is how
the redundancy was found, and why the simpler version is the one that shipped.

**`UUIDv7Model` has no `created_at`.** It has `id`, and the id is a UUIDv7 — which is
time-ordered. So ordering by `id` *is* ordering by creation time. The original code
ordered by `created_at` and raised `FieldError` on every read — which broke seven tests
in three other areas, because they all reach `GET /api/auth/me`. If a model needs a
creation timestamp, `id` already is one.

**A thread's database connection outlives the thread.** The concurrency tests' first
version left each worker's connection open, and the suite failed in *teardown* with
`database "test_eventpulse24" is being accessed by other users` — a confusing message
for what is really "your test leaked a session". `connections[PERSONAL].close()` in the
worker's `finally` fixes it.

**Concurrent tests need `transaction=True`.** Without it pytest-django wraps every alias
in an outer atomic and nothing is ever committed — so the second thread cannot see the
first thread's rows, and the test passes vacuously. This is the same trap the calendar
polling test hit, and the reason the concurrency tests assert on the *outcome* (one row,
one whole set) and not only on the absence of an exception.
