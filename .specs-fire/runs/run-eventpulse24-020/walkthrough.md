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

---

# Implementation Walkthrough: Calendar Connect API (FR-50)

**Work Item:** calendar-connect-api
**Intent:** onboarding-and-account
**Mode:** confirm
**Generated:** 2026-10-29

## Summary

Five endpoints that let a user connect a calendar, watch it sync, replace it when the
provider revokes it, and remove it — over a service that treats the ICS address as a
**credential** rather than as a label.

The item's central problem is that **the address is the secret**. A Google Calendar's
ICS URL contains a token; pasting it into a field is pasting a password. Every design
decision below follows from that one fact: the response shape has **no field** for the
address (not masked, not a fragment), the address never reaches a log, another user's
connection id answers 404 rather than 403, and the endpoint's errors name the *problem*
without echoing the input.

The second problem was quieter, and the code review found all of it: **a constraint that
squatted an address, a cap counted outside a lock, a reconnect that trusted a stale
status, and reads that decrypted secrets they had no use for.** Ten findings, each
reproduced with a failing test before it was fixed.

## Structure Overview

```
backend/
├── apps/personalization/
│   ├── api.py                    ← the five endpoints
│   ├── schemas.py                ← the wire shapes (no field for the address)
│   ├── models.py                 ← CalendarConnection; the constraint is PARTIAL
│   ├── migrations/0006_…         ← the constraint becomes partial
│   └── services/calendar_connections.py
│                                    ← the commands and queries
├── domain/
│   ├── address_policy.py         ← the SSRF pre-flight: scheme, host, port
│   └── errors.py                 ← three typed errors
├── adapters/crawl/address_policy.py  ← a re-export of the domain policy
└── tests/personalization/
    ├── test_calendar_connect_api.py        (56)
    ├── test_calendar_connection_reads.py    (16)
    ├── test_calendar_connect_concurrency.py ( 3)
    └── test_review_repro.py                 (12)  ← the review's reproductions
```

The request flow, and where each guarantee lives:

```
POST /api/personal/calendars  {provider, address}
   │
   ▼
current_user(request)              ← the session; the user id comes from nowhere else
   │
   ▼
connect_calendar(user_id, provider, url, actor)
   │
   ├─▶ _validated_url()            ← scheme · host · port  (domain/address_policy)
   │     └─ refuses calmly: 422, and the message never echoes the address
   │
   ├─▶ transaction.atomic(using=PERSONAL)
   │     ├─▶ _lock_user(user_id)   ← pg_advisory_xact_lock; the cap is decided HERE
   │     ├─▶ _slot_count(user_id)  ← the cap
   │     ├─▶ _refused_duplicate()  ← the address is already held
   │     └─▶ write the row         ← the credential is encrypted at rest
   │
   └─▶ enqueue the first sync      ← NOT inline (AD-11)

The response shape has no `address` field, so no endpoint can leak it by accident.
```

## Architecture

### Pattern Used

**Service layer with a command/query split** — the same shape the onboarding item
established, and the same rules (AD-5): each command takes an explicit `Actor` and an
explicit `now`, opens one `transaction.atomic(using=PERSONAL)`, and returns plain data
rather than a model instance. The API layer never imports `apps.personalization.models`
— the `models-personalization` contract enforces it — so the endpoint calls the service
and the service does the scoping.

### Layer Structure

```text
┌───────────────────────────────────────────────────────────┐
│  HTTP edge — apps/personalization/api.py                   │
│  five endpoints, thin; the shape is the projection         │
├───────────────────────────────────────────────────────────┤
│  Application — apps/personalization/services/              │
│  calendar_connections.py                                   │
│    · connect · disconnect · reconnect · list · get          │
│    · per-user advisory lock; the cap decided under it      │
├───────────────────────────────────────────────────────────┤
│  Domain — domain/address_policy.py, domain/errors.py       │
│  the SSRF pre-flight · three typed errors                  │
├───────────────────────────────────────────────────────────┤
│  Infrastructure — the personal schema, the encrypted column │
└───────────────────────────────────────────────────────────┘
```

## The Five Endpoints

| Method | Path | Answers |
|--------|------|---------|
| `GET` | `/api/personal/calendars` | The user's connections, oldest first |
| `POST` | `/api/personal/calendars` | Connect one; `201` with the connection and its state |
| `GET` | `/api/personal/calendars/{id}` | One of the user's own connections; `404` for anyone else's |
| `POST` | `/api/personal/calendars/{id}/reconnect` | A new address for a `needs_reconnect` connection |
| `DELETE` | `/api/personal/calendars/{id}` | Disconnect, and purge that connection's events |

The projection carries the id, the provider, the status, the display label, the last and
next sync times, the sync-in-progress flag, and a last-error **slug**. It carries no
address and no fingerprint.

## Domain Model

### `CalendarConnection` — one calendar the user has connected

| Property | Rule |
|----------|------|
| `user_id` | Held **by value** (OQ-8) — no FK to `User` |
| `provider` | `google` / `apple` / `outlook` — validated against the model's own enum |
| `credential` | The address, **encrypted at rest**; destroyed on disconnect |
| `credential_fingerprint` | A keyed HMAC of the address — how "the same address" is recognised |
| `status` | `active` / `needs_reconnect` / `disconnected` |
| — | constraint | `UNIQUE (user_id, credential_fingerprint)` **WHERE status ≠ 'disconnected'`** |

**The constraint is partial, and that is the whole point.** A disconnected row keeps its
fingerprint until the retention sweep removes it. Under an unpartial constraint that
fingerprint kept occupying the address, so the everyday sequence — connect, disconnect,
connect the same calendar again — hit the constraint and answered **500**. The user had
lost a working calendar and could not get it back. The partial form says what the
constraint always meant: *one **live** connection per address, per user*. It is the
same shape as `ingestion`'s `event_live_source_item_uq`.

## Key Implementation Details

### 1. The address never leaves the server — structurally, not carefully

The response shape has **no field** for the address. Not masked, not a fragment, not a
host. There is nothing to leak, because there is nowhere to put it.

`test_no_endpoint_in_the_router_returns_the_address` is the sweep the acceptance
criterion asks for: it calls the list, the one-connection GET, a failing connect and a
reconnect, one after the other, and asserts that not one response body carries the
secret segment or the host. A endpoint added later is covered by the same assertion.

The **fingerprint** is a keyed HMAC and so is not a secret — but it is not the user's
business either, and a digest in a response body is one more thing to leak in a
screenshot. It has no field either.

### 2. The errors name the problem and never echo the input

A refused address answers 422 with a typed code and a message about **what was wrong** —
the scheme, the network, the port — and the message never contains the address. The
same rule applies to the *already connected* refusal: the user already knows what they
pasted, and echoing it back would put it in the response body, in the browser history,
and in any screenshot of the error.

Three refusals, three calm answers:

| The problem | The answer |
|-------------|-----------|
| A bad scheme, a denied host, a refused port, a malformed host or port | 422 `invalid_calendar_credential` |
| The address is already connected | 422 `invalid_calendar_credential`, same code, same calmness |
| The plan's cap is reached | **409** `calendar_cap_reached`, with the upgrade copy |

**The cap is a 409, not a 400.** The address the user pasted is perfectly good; it is
the *state of the account* that refuses it, because the account already holds the one
calendar its plan allows. The request was well-formed and conflicts with the account,
which is what a 409 means. A 400 would say "your request was wrong", and it was not.
This is the same reasoning already applied to `OnboardingAlreadyCompleteError`.

### 3. The cap payload carries the copy and no modal semantics

The error's `details` are exactly `{"cap", "upgrade_hint"}` — the approved copy, taken
from the UX spine rather than written fresh. The key set is pinned **exactly**, so a
future edit cannot grow a modal-shaped field without failing a test. The client decides
whether to show a prompt, a banner, or a card; the server states the fact.

### 4. The cap is a count, so the count needs a lock

The Free cap is one calendar per account. The check is:

```python
occupying = _slot_count(user_id)
if existing is not None:
    # The row being reused is already counted, so it does not add a slot.
    occupying -= 1
if occupying >= FREE_TIER_CALENDAR_PROVIDER_CAP:
    raise CalendarProviderCapReached(...)
```

Three details, each of which was a defect before the review found it:

- **The reuse path is not a free pass.** A `needs_reconnect` row still occupies the
  user's slot, so the reuse path goes through the same check — it *subtracts the row it
  is reusing* and then checks. The review's first version short-circuited on
  `existing is None`, which let a user at their cap reuse a revoked row and turn a
  second live row into a third.
- **The count is read under a lock.** A count read without a lock is a race: two
  concurrent connects both read zero, both pass, and both write — leaving a Free
  account with two calendars, silently, against a rule the endpoint enforces. The lock
  is a `pg_advisory_xact_lock` on a `blake2b`-derived key, taken **before** the cap is
  decided and inside the same transaction that writes the row.
- **The lock is transaction-scoped.** A worker that dies mid-command releases it on
  rollback, so a crash cannot leave a user's calendar wedged.

### 5. The reconnect re-reads the status under a row lock

The reconnect used to check the row's status **before** its transaction opened, from the
row the caller had already fetched. Two things could go wrong in the gap: a disconnect
that committed in between was silently overwritten — resurrecting a calendar the user
had just removed and re-arming a credential they had asked to destroy — and a row that
**vanished** (the retention sweep removes disconnected rows) left the second read
holding `None`.

Both are fixed by re-reading the row under `select_for_update()` inside the
transaction, and answering "not found" when it is gone.

### 6. The reads do not decrypt the credential

`EncryptedTextField.from_db_value` decrypts every row it fetches. The reads used to
load the whole row — so a read **decrypted every address it touched**, for a projection
that has no field for it.

The consequence is a denial of service the user could not remedy: one row whose
envelope cannot be read (a rotated key id, a corrupted ciphertext) raised from the read
and took down the **whole list**. And because the same ownership lookup backed the
disconnect, the user could not disconnect the broken row either — **the remedy refused
itself**.

So the reads name the columns they need, and `credential` is not among them:

```python
_READ_COLUMNS = (
    "id", "provider", "status", "display_label",
    "last_polled_at", "next_poll_at", "sync_claimed_at", "last_error_kind", "created_at",
)
```

This is a performance fix and a safety fix at once, and the safety half is the one that
matters.

### 7. The pre-flight checks the port, not just the host

The real SSRF enforcement is `adapters.crawl.http.GuardedBackend`, which resolves the
host itself and refuses any denied address **on every redirect hop**, so DNS rebinding
cannot bypass it. That check was not weakened.

The pre-flight exists because a connect-time refusal is **invisible at connect time**:
the user pastes an address, the row is created, and the first poll — up to a minute
later, in a worker, with nobody watching — fails. The pre-flight refuses the obvious
problems at the moment the user would still be looking at the screen.

It refuses the denied network families, a bad scheme, embedded credentials, a malformed
bracketed IPv6 host (`urlsplit` raises a bare `ValueError` on those, which is not a
`DomainError` and would have escaped to the 500 handler), and **a port the fetch
adapter would not allow**. That last one was a review finding: the hardened fetch
client only connects to 80 and 443, so an address on `:8443` was accepted, stored with
a live encrypted credential, shown to the user as *connected* — and then refused on
**every single poll**, with the only evidence a slug in the error field. Precisely the
"invisible at connect time" failure the pre-flight exists to prevent.

### 8. The first sync is enqueued, not run inline

The connect returns with the connection's status and its sync state. The polling
happens on the tick, in the worker. The endpoint's job is to tell the user "we're
importing your calendar" — which is what onboarding step 1 needs, without leaving the
flow (FR-3). `test_connect_does_not_fetch_the_calendar` pins it: a slow or unreachable
provider cannot hold the request open.

### 9. Another user's connection is 404, not 403

Both the reads and the writes answer **404**, with the same body, for another user's
connection id and for an id that does not exist. A 403 would confirm the record exists,
so a caller could probe for other users' connection ids by watching for 403 instead of
404. The ownership lookup lives in the **service**, because the API layer may not import
the model — the API calls `reconnect_calendar_for_user` / `disconnect_calendar_for_user`
and the service does the `user_id` filter.

### 10. The address is excluded from the logs

The request body carries the address, so the body must never be logged. The test proves
it on a **failing** request, because that is where a log line is most likely: an
unhandled exception's traceback carries the arguments, and a validation error's `input`
carries the submitted value.

The same reason keeps the URL out of the error field: an `httpx` exception message
contains the full request URL, which **is** the credential. So `last_error_kind` is a
slug (`revoked`, `transient`), never a message and never a URL.

## Security Considerations

| Concern | Approach |
|---------|----------|
| **The address is a credential** | It is encrypted at rest, write-only in the API, and absent from every response shape and every log |
| **Enumeration** | Another user's connection id answers 404 — the same status and the same body as an id that does not exist |
| **SSRF** | The pre-flight refuses denied networks, bad schemes, embedded credentials and refused ports at connect time; `GuardedBackend` refuses on every redirect hop at fetch time |
| **CSRF** | Every unsafe method is checked by `require_csrf`, through the `current_user` resolver — one mechanism, not two |
| **Cross-site writes** | The reads never write. A write behind a `GET` is a cross-site write, because Ninja exempts every view from Django's CSRF middleware and the check runs on unsafe methods only |
| **Forged scoping** | The user id comes from the session alone; no endpoint accepts one as input |
| **The cap cannot be raced** | The count is read under a transaction-scoped advisory lock, in the same transaction that writes |
| **A revoked credential** | The reconnect re-reads the status under a row lock, so a disconnect that committed first is not overwritten |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| The list must not decrypt secrets | `.only(*_READ_COLUMNS)` — the credential column is never fetched |
| The list must not write | No transaction, no lock, no `UPDATE` — a read on a hot path |
| The connect must not hold the request open | The first sync is enqueued, not fetched inline |
| The cap check must not be a hot path | One advisory lock per connect; the count is one indexed query |
| A slow provider must not block | The endpoint never touches the network |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Whether the response carries the address | **No field at all** | The address is a credential. A masked form or a fragment is still a leak, and a shape that cannot carry it cannot leak it by accident |
| The cap's status | **409**, not 400 | The request was well-formed; it conflicts with the state of the account |
| Where the cap payload's shape stops | `{"cap", "upgrade_hint"}` | The server states the fact; the client decides the presentation. A modal-shaped field is a UI decision made on the server |
| Where the SSRF deny table lives | `domain/address_policy.py`, adapter re-exports it | An app may not reach into an adapter (AD-2). The policy is knowledge, not machinery — and there is still exactly one table |
| How the cap is serialised | A transaction-scoped advisory lock, before the count is read | The cap is a count, and a count read without a lock is a race |
| The unique constraint | **Partial** — the disconnected rows are excluded | It says what it means: one *live* connection per address, per user |
| Whether the reconnect trusts the caller's status | No — it re-reads under a row lock | The caller's copy is stale by definition; a disconnect that committed in between would be silently overwritten |
| Whether the reads decrypt the credential | No | A read that decrypts a secret it has no use for can be taken down by one corrupt row — and the remedy (disconnect) reads the same way |
| Where the CSRF check lives | Only in the `current_user` resolver | The router already declares `auth=current_user`; the endpoint-level calls were redundant duplicates, and a test cannot tell a duplicate from the thing it duplicates |
| The provider value | Carried, not branched on | The work item says the provider changes no server behaviour. The port and host rules come from the fetch adapter's policy, not from a per-provider table |

## Deviations from Plan

1. **The unique constraint became partial.** The plan did not mention it; the code review
   found that connect → disconnect → connect was a 500 for an everyday sequence. The
   migration `0006_…` makes the change.

2. **The concurrency guarantee was added.** The plan did not mention concurrent requests.
   The review found that the cap was counted outside a lock, so two concurrent connects
   could both take the only slot. A new test file
   (`test_calendar_connect_concurrency.py`, 3 tests) and the per-user advisory lock were
   added.

3. **The port pre-flight was added.** The review found that an address on a port the
   fetch adapter refuses was accepted at connect time and failed on every poll. The
   pre-flight now checks the port as well as the host.

4. **The reads stopped decrypting.** Not a plan deviation so much as a correction: the
   reads never had a use for the credential, and the ownership lookup's use of it was
   what made a corrupt row un-disconnectable.

5. **The redundant CSRF calls were removed.** The plan's shape had each endpoint calling
   `require_csrf` in its body; the router's resolver already does it. One mechanism is
   easier to reason about than two, and the review's revert case could not tell them
   apart — which is itself the argument for removing one.

## Dependencies Added

**None.** No new Python packages, no new npm packages, no new infrastructure. The
advisory lock uses Postgres, which the project already depends on, through the same
pattern `apps.personalization.services.onboarding` already uses.

## How to Verify

### The commands

```bash
cd backend

# The item's own tests
.venv/bin/python -m pytest \
    tests/personalization/test_calendar_connect_api.py \
    tests/personalization/test_calendar_connection_reads.py \
    tests/personalization/test_review_repro.py \
    tests/personalization/test_calendar_connect_concurrency.py -q

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

**Expected:** 87 item-scoped tests pass; 2909 backend tests pass; 98.98% coverage with
157 files at 100%; ruff clean; 17/17 contracts kept; no migration drift; the committed
schema matches the regenerated one; 149 frontend tests pass; the typecheck is clean.

### Manual scenarios

**The list carries the state and never the address.** Sign in, connect a calendar, then
`GET /api/personal/calendars` → 200 with the id, the provider, the status, the display
label, the sync times, and `sync_in_progress`. The address appears **nowhere** — not in
full, not masked, not as a fragment.

**The cap.** On a Free account, connect one calendar → 201. Connect a second → **409**
`calendar_cap_reached`, with `details` exactly `{"cap", "upgrade_hint"}` and no
`modal`, `title` or `actions` anywhere in the payload.

**A refused address never echoes itself.** `POST` with `https://127.0.0.1/feed.ics` →
422. The body names the problem; the body does **not** contain `127.0.0.1`.

**A port the fetch would refuse.** `POST` with `https://example.com:8443/feed.ics` → 422,
at connect time — not a connection that fails silently on every poll.

**Connect, disconnect, connect again.** The everyday sequence. All three answer 201/204/
201, and the re-add is **not** a 500.

**Another user's connection.** `GET`/`POST`/`DELETE` with someone else's connection id →
404, byte-identical to an id that does not exist.

**The log.** Connect with an address that will be refused, with the logs captured. The
address appears in **none** of them.

## Test Coverage

- Tests added: 87 (56 API, 16 reads, 12 review reproductions, 3 concurrency)
- Coverage: **100%** on `apps/personalization/services/calendar_connections.py` and
  `domain/address_policy.py`; 98.98% across the backend
- Status: passing — 2909 backend, 149 frontend, 0 failures
- Revert verification: **nine** item rules (R1–R9) and **nine** review rules (V1–V9) —
  every one reverted and watched to fail

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues remaining — the review's ten findings are all fixed and
      revert-verified
- [x] Documentation updated — the module docstrings state the new guarantees
- [x] Developer notes captured

## Developer Notes

**A partial unique constraint is `Q(status=...)` negated, and it is worth knowing why.**
`condition=~Q(status="disconnected")` means "the constraint applies to every row whose
status is *not* disconnected". The alternative — keeping the constraint total and
deleting the disconnected row — would have lost the audit trail and broken the
"disconnect then reconnect" sequence in a different way. The repo's precedent is
`apps/ingestion/models.py:246`.

**The test database is rebuilt from the migrations, not from the models.** This bit the
review's first revert case: patching the model's constraint left the *database* with the
partial index, so the test still passed and the case reported nothing. A revert case
that patches a model has to patch the migration, or it is not testing anything.

**A count is not a lock.** The Free cap is one calendar per account. The check was
`if existing is None and occupying >= CAP`. Two concurrent connects both read zero, both
passed, and both wrote — two calendars on a Free account, with no error anywhere. The
count has to be read under a lock, in the same transaction that writes the row. This is
the same lesson the onboarding item's races taught, in a different table.

**`urlsplit` raises a bare `ValueError`, and `.port` raises one too.** On a malformed
bracketed IPv6 host, and on a non-numeric or out-of-range port. Neither is a
`DomainError`, so both escaped to the 500 handler — a server fault for what is a typo.
Every other bad address gets a calm 422; these two did not, until the review found them.
When you wrap a stdlib parser, catch its `ValueError` explicitly.

**A read that decrypts a secret it does not use is a liability, not a cost.** The reads
loaded the whole row, and `EncryptedTextField` decrypts on the way out. One corrupt
envelope took down the whole list — and because the disconnect used the same lookup,
the user could not remove the broken row either. The remedy refused itself. `.only(*_READ_COLUMNS)`
is the fix, and it is worth noticing that it makes the read *cheaper* too.

**A test that passes against the broken code is not a test.** The review's V8 and V9
cases both passed against the unfixed code, because every credential in the fixture
decrypted cleanly — the tests were vacuous. They now write a corrupt envelope straight
to the column, so the decryption genuinely fails. The same lesson, in a different
shape, stopped the review's R9 case: the first version removed the explicit
`require_csrf` call and **all 72 tests still passed**, because the router's resolver
already does the check and no test can tell a duplicate from the thing it duplicates.

**A stale claim is a lost job, not a sync in progress.** The `sync_in_progress` flag is
a **fresh** claim — one whose `sync_claimed_at` is inside `CALENDAR_CLAIM_TTL`. A claim
older than that belongs to a worker that died holding it, and the connection becomes
claimable again. Showing a stale claim as "syncing" is a lie the user can see: the
spinner would never stop.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-020*

---

# Implementation Walkthrough: The Event Fit (AD-10, FR-26)

**Work Item:** event-fit
**Intent:** onboarding-and-account
**Mode:** confirm
**Generated:** 2026-10-30

## Summary

The Event Fit is the **public** explanation of an event: a 1–5 score and a short list of
generic tags — "Tonight", "Tomorrow", "This weekend", "In Brooklyn". It is computed per
`(event, city)`, persisted on the `catalog` schema, and served to visitors who have no
session at all.

The item's central problem is that **there are two kinds of explanation in this
product, and they look identical on screen.** The Event Fit says "this event is a good
fit for this city, right now". The Relevance Pulse — a later intent — says "this is a
good fit *for you*". AD-10 forbids substituting one for the other, and calls the
substitution the trust-collapse failure PRD Risk 11 calls company-ending: a signed-in
reader told a thing is a great match when nothing personal was ever computed.

So the separation had to be **structural**, not a naming convention — and the code review
found that the first attempt at structural was not structural enough. That is the most
important thing in this walkthrough.

The second problem was quieter and is worth understanding before writing the next
explanation: **"Tonight" is a statement about *now*, so a persisted tag goes stale as
time passes** — not only when the event changes. The answer is a **writer on a
cadence**, not a computation at render.

## Structure Overview

```text
┌──────────────────────────────────────────────────────────┐
│  Domain                                                  │
│  domain/event_fit.py  — the pure function                │
│    · score = min(proximity band, confidence band)        │
│    · tags: tonight · tomorrow · this_weekend · in_<city>│
│    · stdlib only (AD-2); no clock read; `now` explicit   │
├──────────────────────────────────────────────────────────┤
│  The wall — a package, not a list of names               │
│  apps/ingestion/event_fit/                               │
│    __init__.py  — the package docstring: why it exists   │
│    writes.py    — the ONLY writer of EventFit (AD-5)     │
│    reads.py     — the published read: top N for a city   │
├──────────────────────────────────────────────────────────┤
│  Writers                                                 │
│  apps/ingestion/services/ingest_item.py — on create and  │
│                            on change, inside the txn     │
│  worker/tasks.py           — the 15-minute staleness      │
│                            refresh, batched by pk         │
│  config/management/commands/backfill_event_fit.py        │
├──────────────────────────────────────────────────────────┤
│  Infrastructure                                          │
│  catalog schema: EventFit (event, city) → score, tags,   │
│                  event_version, computed_at               │
└──────────────────────────────────────────────────────────┘
```

## The wall, and why it is a package

The first version of the Event Fit put the read in
`apps/ingestion/services/event_fit_read.py` and forbade **two module names** from
`personalization`. A third module that re-exported the read — `event_fit_preview.py`,
two lines — gave `personalization` the Event Fit with the import contract **green** and
the architecture test **green**.

A wall made of names is opened by adding a name, and adding a name is the most ordinary
thing a developer does. So the Event Fit became a **package**, and the contract names
the package:

```toml
forbidden_modules = [
    "apps.ingestion.event_fit",
    "apps.ingestion.event_fit.*",
]
```

A package is **one name that covers everything inside it**, so a new Event Fit module is
inside the wall by default rather than outside it until somebody notices.

**And the two guards are complementary, each honest about its scope:**

| Bypass | Import contract | AST prefix test |
| --- | --- | --- |
| `import apps.ingestion.event_fit.reads` | caught | caught |
| `import apps.ingestion.event_fit` | caught | caught |
| `from apps.ingestion.event_fit import reads` | caught | caught |
| `import apps.ingestion.event_fit_preview` (a re-export) | **not caught — by design** | caught |

The import contract matches on *import names* and expands the forbidden package into the
modules inside it. It has no data-flow analysis, so it cannot see a module **outside**
the package that re-exports what is inside. That is a property of how a `forbidden`
contract works, not a gap in how it was configured — so the contract is not asked to
catch it. The AST test is what catches it, by checking the **package prefix**:
`apps.ingestion.event_fit_preview` starts with `apps.ingestion.event_fit`.

The bypass is **planted** in `test_the_wall_catches_a_re_export`, both halves — the module
that re-exports, and the module that imports *it* — so the claim is checked rather than
asserted.

## The score, and the band that is a duration

The score is the **lower** of two bands: how soon the event starts, and how well we know
its facts. Taking the lower is the honest rule — a badly-extracted event happening
tonight is not a good fit, however soon it is — and a `min` is a rule a person can state
out loud. A weighted sum would need weights nobody can justify without labelled data.

The proximity band was originally written as "starts today", and it was **wrong**. A
calendar day needs a day boundary, and a day boundary is exactly the thing this item
requires to be computed in the event's *own* IANA timezone — so the band would have
needed a second, different local-day rule from the one the tags use. The band is a
**duration** instead: the same quantity in every timezone, with the local day already
computed for the tags beside it.

## The staleness problem, and why the answer is a writer

"Tonight" is a statement about *now*. So a persisted tag goes stale as time passes — not
only when the event changes, and the latter is the easy half. AD-10 says the *render*
never computes, so the recompute cannot live in the read.

It lives in `worker.tasks.refresh_event_fits`, enqueued by the tick every fifteen
minutes, which recomputes the published events' fits and writes them. The render path
reads a persisted row and computes nothing — that rule is unchanged in substance. What
the refresh adds is the *writer* half, which is what makes "tonight" mean today's
evening rather than the evening it was written on.

**The staleness check is `event_version`.** Every fit records the Event version it was
computed from, and a row whose version no longer matches its Event is never served. The
check lives in the **read**, not in a trigger — because the refresh is a writer's work,
and a trigger cannot decide that a row *should* be refreshed; it can only say a row is
now out of date, which the read already knows how to skip.

**The refresh cost is bounded.** The published events are walked **by primary key**, not
by offset — the first batch of a run has to move forward, or the second read would return
the first batch again and the loop would never end — and each batch is written in its own
transaction.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/domain/event_fit.py` | The pure function — stdlib only (AD-2) |
| `backend/apps/ingestion/event_fit/__init__.py` | The package: the wall is this name |
| `backend/apps/ingestion/event_fit/writes.py` | The only writer of `EventFit` |
| `backend/apps/ingestion/event_fit/reads.py` | The published read: the top N for a city |
| `backend/apps/ingestion/migrations/0004_eventfit.py` | The table and its constraints |
| `backend/config/management/commands/backfill_event_fit.py` | The idempotent backfill |
| `backend/tests/domain/test_event_fit.py` | The pure function's rules and boundaries |
| `backend/tests/ingestion/test_event_fit.py` | The write, the hooks, the read, the refresh |
| `backend/tests/ingestion/test_event_fit_command.py` | The backfill command |
| `backend/tests/architecture/test_event_fit_separation.py` | The AD-10 wall, both directions |
| `backend/revert_event_fit_check.sh` | The revert harness — twenty-one cases |

### Modified

| File | Change |
|------|--------|
| `backend/apps/ingestion/models.py` | The `EventFit` model |
| `backend/apps/ingestion/services/ingest_item.py` | The fit is written on create and recomputed on change |
| `backend/worker/tasks.py` | The fifteen-minute staleness refresh |
| `backend/shared/constants.py` | The thresholds and the tag keys |
| `backend/pyproject.toml` | The contract now forbids the package |
| `backend/tests/architecture/test_import_contracts.py` | The contract's shape is pinned |

## Key Implementation Details

**The write is an upsert on `(event, city)`, and it retires the rows for cities the event
has left.** A venue edit does not bump `event_version`, so an orphaned row's version
still matches and the read's staleness guard would pass it straight through — the event
would appear in **two** previews, with the old city's place tag on one of them.

**A row that already says the same thing is not rewritten.** The plan's own words:
"a row that already matches is not rewritten (the `computed_at` does not move, so a test
can assert that)". A `computed_at` that moves on every run is a lie about when the fit
was last computed, and it means the refresh writes the whole published catalog every
fifteen minutes whether or not anything about it changed.

**An event with no venue city gets no row at all.** The city is not guessed from the
source, the title, or the source's city. An event in an unknown city is in no city's
preview, and a preview that puts it in the wrong one is worse than one that leaves it
out.

**The weekend is named by its Saturday, and the comparison is between dates.** Three
formulations were rejected first: a plain "within seven days" bound (wrong in both
directions), an ISO-week-number comparison (wraps at the year boundary — 2027-01-01 is
ISO week 53 of 2026), and a Monday-of-the-week comparison (wrong from a Saturday).

**The city tag is ASCII.** `"São Paulo"` → `in_sao_paulo`, `"München"` → `in_munchen`. A
tag key has to survive a JSON round-trip, a URL segment and a CSS selector unchanged.

## Security Considerations

- **The read never touches the `personal` schema.** It is served to visitors with no
  session (AD-12), so a read of `personal` would be a leak even if the value were
  discarded. Asserted statically, so the guarantee survives a future edit.
- **`personalization` cannot reach the Event Fit at all**, so it cannot use it as a
  Relevance Pulse substitute — which is the substitution AD-10 calls company-ending.
- **`ingestion` cannot reach `personalization`**, so the Event Fit is computed from
  catalog facts and nothing else.
- **The fit holds no user-derived data.** Its retention category is
  `SOURCE_REGISTRY` (AD-15): it is catalog content, and it is written only by
  `ingestion` (AD-16).

## Performance Considerations

- The read is a single indexed query with the stale-row skip applied **before** the
  limit, so stale rows cannot starve the result.
- The refresh walks published events by primary key in bounded batches, each in its own
  transaction, so a run over a large catalog holds no long transaction open.
- A row that has not changed is **not** rewritten, so an idle catalog costs a read per
  published event every fifteen minutes and no writes at all.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| The score's combination rule | The **lower** of the two bands, floored at 1 | A badly-extracted event tonight is not a good fit. A `min` is a rule a person can state; a weighted sum is not |
| The score's bands | 5 bands over proximity (24h / 2d / 7d / 14d / later), by **duration** | A duration is the same quantity in every timezone, so the band needs no second local-day rule — and the local day is already computed for the tags |
| The staleness handling | A **periodic refresh** from the tick, writing the row | AD-10 forbids a render-time computation; the writer half is what makes "tonight" mean today's evening |
| The wall's shape | A **package**, forbidden by name | A wall made of names is opened by adding a name. A third module that re-exported the read walked through the first version with the contract **green** |
| The city's tag | `in_<city>`, slugified | Place-based, generic, and ASCII so it survives a URL and a CSS selector |
| The default N | 3 | The Pulse Preview shows three cards |

## Deviations from Plan

**The plan's band table said "starts today". The plan was wrong, and it was corrected.**
The code says "starts within 24 hours", measured as a duration — a duration is
timezone-independent, the local day is already computed for the tags, and "how soon" is
what the preview answers. The reasoning is recorded in the plan, not just here.

**The Event Fit became a package during the review.** The plan originally put the read in
its own module and forbade two module names. That wall was open, so the structure
changed: `apps/ingestion/event_fit/{__init__,writes,reads}.py`.

## Dependencies Added

None. No new package, no new service, no new table beyond `EventFit` itself.

## How to Verify

```bash
# The item's own tests
cd backend && .venv/bin/python -m pytest \
    tests/domain/test_event_fit.py \
    tests/ingestion/test_event_fit.py \
    tests/ingestion/test_event_fit_command.py \
    tests/architecture/test_event_fit_separation.py \
    tests/architecture/test_import_contracts.py -q

# The whole suite, with coverage
cd backend && .venv/bin/python -m pytest -q --cov --cov-report=term-missing

# The linter, the contracts, and Django's own checks
cd backend && .venv/bin/python -m ruff check .
cd backend && .venv/bin/python -m ruff format --check .
cd backend && .venv/bin/python manage.py check
make lint-backend

# The coverage gates
make coverage-backend

# The revert verification — twenty-one cases, each watched to fail
cd backend && bash revert_event_fit_check.sh
```

## Test Coverage

| Module | Coverage |
|--------|----------|
| `domain/event_fit.py` | 100% |
| `apps/ingestion/event_fit/__init__.py` | 100% |
| `apps/ingestion/event_fit/writes.py` | 100% |
| `apps/ingestion/event_fit/reads.py` | 100% |
| `config/management/commands/backfill_event_fit.py` | 100% |
| `worker/tasks.py` | 100% |

**236 item-scoped tests**, 3098 in the whole backend suite, 99.01% total coverage,
19/19 import contracts kept.

**Twenty-one revert cases, all caught** — sixteen for the item's own rules and five for
the review's fixes.

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues remaining — the review's four findings are all fixed and
      revert-verified
- [x] Documentation updated — the module docstrings state the new guarantees
- [x] Developer notes captured

## Developer Notes

**A wall made of names is opened by adding a name.** The first version of the AD-10 wall
forbade two module names, and a two-line re-export gave `personalization` the Event Fit
with the contract green. A package is one name that covers everything inside it, so a
new module is inside the wall by default. This is worth remembering for every future
boundary in this codebase.

**A forbidden contract matches on import names, and that is its whole reach.** It has no
data-flow analysis, so it cannot see a module outside the forbidden package that
re-exports what is inside. Do not ask it to; ask a different question of a different
tool. Here that was the AST test's package-prefix check — and the bypass is planted, so
the claim is checked rather than asserted.

**The strongest version of a guard is the one the suite can see.** The package contract
was in place, the architecture test was in place, and reverting the contract to name-only
left **all 212 tests passing**. The wall was load-bearing and the suite could not tell.
The contract's *shape* is now pinned in `test_import_contracts.py`, the way
`single-ics-parser` and `redis-sdk` already are, so narrowing the wall is an observable
failure.

**A restore that is not verified is not a restore.** The revert harness keyed its
backups on the file's **basename**, so three cases targeting `writes.py` shared one
backup path; case A's restore overwrote case B's backup, and the file was left
**reverted** for every case that followed. The harness was silently corrupting the tree
it was supposed to be verifying. Now every case gets a unique backup and **compares the
restored file against it byte for byte** before moving on. A restore that silently fails
is worse than no restore: it makes every later result a claim about a tree that does not
exist.

**A test that cannot distinguish two implementations pins nothing.** The ordering test
had the better-fit event as the *sooner* one, so ordering by score and ordering by start
time gave the same answer and the test passed whichever way the query was written. The
fix was in the test, not the source. **A revert case that does not fail is not a revert
case; it is a hole in the suite wearing a harness's clothes.** That sentence has now
been earned three times in this run.

**A plan can be wrong and the code right.** The band table said "starts today" and the
implementation said "within 24 hours". The plan was the one that needed changing, and
the reason was structural: a calendar-day band would have needed a *second* local-day
rule beside the one the tags already compute. When the plan and the code disagree, ask
which one is inventing a second rule.

**A relative tag needs a writer, not a cleverer reader.** "Tonight" is a fact about
*now*. Persisting it makes it go stale with the passage of time, not only with a change
to the event. The fix is not a smarter read; it is a writer on a cadence, and a
staleness check that says which rows are out of date.

---

# Implementation Walkthrough: The Pulse Preview API & Geo Port (FR-2, AD-12)

**Work Item:** pulse-preview-api-and-geo
**Intent:** onboarding-and-account
**Mode:** confirm
**Generated:** 2026-10-30

## Summary

The Pulse Preview is **the first thing a visitor gets, before they have an account**.
This item is the backend behind it: two public endpoints, a geo port that turns the
edge's location header into a city name, and the published read that produces the
cards.

The item's central constraint is **AD-12**: the public surface renders fully without a
session. That is not one property — it is *two* facts that happen to be the same fact.
The endpoint never reads `request.user`, never reads `personal`, and sets no cookie;
and that is exactly what makes its response cacheable, because the cache key can be the
URL. A surface that touched the session would be neither anonymous nor cacheable.

The second thing worth understanding before writing the frontend is that **the preview
does not guess.** It has one table of what happens when, and an explicit city is never
silently replaced. If a visitor picks a city the catalog does not cover, the answer is
an empty preview carrying **that** city's name — not the fallback's events under the
requested name, which would be a heading that lies.

The third is the **opt-out**. "Don't use my location" is a real choice, and a choice the
server ignores is not a choice. So `use_geo=false` means the geo port is **not called
at all** — a stronger claim than "called and the answer ignored", and the only one a
test can check. The test replaces the port with one that raises.

## Structure Overview

```text
┌──────────────────────────────────────────────────────────┐
│  The port — no Django, no host                           │
│  ports/geo.py                                             │
│    resolve_city(headers: Mapping[str,str]) -> str | None │
│    · a bag of headers, NOT a request (AD-1)               │
│    · "is this city supported?" is NOT the port's job     │
├──────────────────────────────────────────────────────────┤
│  The adapters                                            │
│  adapters/geo/header.py  (real)  — reads ONE header     │
│    · length-bounded BEFORE decoding (decode only shrinks)│
│    · URL-decoded exactly ONCE                            │
│    · no database lookup, no vendor call                  │
│  adapters/geo/fake.py    (local/CI default)              │
│    · configurable: GEO_FAKE_CITY                         │
├──────────────────────────────────────────────────────────┤
│  The public surface — no session (AD-12)                 │
│  apps/catalog/preview_api.py                              │
│    GET /api/public/preview            → up to 3 cards    │
│    GET /api/public/preview/cities     → the city picker  │
│    · one resolution table, one function                 │
│    · cacheable; Vary carries nothing session-related    │
│    · rate-limited per IP; each route its own budget      │
│  apps/catalog/preview_schemas.py — the wire shapes       │
├──────────────────────────────────────────────────────────┤
│  The published read — lives INSIDE ingestion              │
│  apps/ingestion/services/preview_read.py                 │
│    · cards = Event Fit rows + Source Badge inputs        │
│    · supported cities = derived, not configured           │
│    · hands over plain data, so catalog never holds a     │
│      model it is forbidden to import                     │
└──────────────────────────────────────────────────────────┘
```

## The resolution table

There is **one** table of what happens when, and it is implemented in one function
(`_resolve_city`), so there is one rule and not three:

| Situation | Resolved city | `city_source` | Cards |
|---|---|---|---|
| `use_geo=false` | the fallback | `fallback` | the fallback city's |
| `city` given, supported | that city | `query` | that city's |
| `city` given, **not** supported | that city (unchanged) | `query` | **none** |
| no `city`, geo → supported | that city | `geo` | that city's |
| no `city`, geo → unsupported | the fallback | `fallback` | its own |
| no `city`, geo → nothing | the fallback | `fallback` | the fallback city's |

The fallback is used for a **geo** city the catalog cannot serve, because the visitor
did not choose it — the edge guessed, and a guess the catalog cannot serve should not
produce an empty page. It is **not** used for an **explicit** unsupported city, because
there the visitor did choose it and deserves to be told the truth about it.

## The spelling of a city belongs to the catalog

The spelling a visitor types is not the spelling the events are filed under, and a
preview headed `"BROOKLYN"` listing the events filed under `"Brooklyn"` is a heading
nobody can search for. So both paths answer with **the catalog's spelling**.

The canonicaliser is **asymmetric on purpose**: it replaces the name only when the
catalog holds that city. An unsupported city comes back exactly as the caller wrote
it — otherwise the canonicaliser would break the rule it sits next to (an unsupported
city must never be silently renamed into a supported one).

## The wall: the read lives *inside* `apps.ingestion`

AD-2's `models-ingestion` contract protects `apps.ingestion.models` to
`apps.ingestion`. The obvious place for the preview's read is `apps/catalog` — and it
does not work, because the Event Fit read imports that model directly, so
`apps.catalog` cannot reach the Event Fit through it either.

So the read lives at `apps/ingestion/services/preview_read.py`: inside
`apps.ingestion`, so the contract holds, and handing over **frozen dataclasses**
rather than model instances, so the calling app never holds a reference to a model it
may not import. The wall holds without either side knowing the other's models.

## The privacy rules are structural, not aspirational

PRD §10.2 says the resolved city is never stored server-side for an anonymous visitor
and never logged with the IP. A promise in a docstring is not a guarantee, so the rules
are **checked on the code**: the architecture suite fails if the preview surface reads
the session, imports the personal schema, writes to a cache, or logs the city.

The IP is used only as part of a throttle key — the same treatment the auth endpoints
give it — and it comes from `X-Forwarded-For` **only when the deployment says to trust
it**. Next's rewrite forwards the browser's headers as they arrived, so a browser that
sets the header has that value reach Django unchanged; trusting it unconditionally let
any caller mint a fresh throttle bucket per request. `TRUST_FORWARDED_FOR` is **off by
default**.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| The supported cities | **Derived** from the catalog, never configured | A hard-coded list goes stale the moment a source in a new city is ingested, and the picker would then offer a city the preview cannot fill |
| What makes a city supported | An **upcoming, published, non-superseded** event with a **current** Event Fit | A city with events but no fits is a city the preview cannot serve; a fit whose `event_version` no longer matches its event describes an event that no longer exists |
| The order of the city list | Python's `sorted(..., key=str.casefold)`; the database is **not** asked to sort | A database's `ORDER BY` on text is a **locale collation** — `en_US.UTF-8` ignores punctuation at the primary level — so the deployment's locale would decide the picker's order |
| The opt-out | A branch that **skips the call** | A geo lookup is a request to the edge, and "the visitor said not to" should mean the request is never made |
| The explicit `city` parameter | **Bounded** by the same constant as the header, and falls through rather than truncating | Two untrusted inputs into one endpoint, one bounded and one not, is the asymmetry; truncating would answer with a different city than the one asked for |
| The Source Badge | A **type**, derived in the read | The fit read deliberately does not join the source — a fit is about an event's fit, not about where it came from |

## Dependencies Added

None. No new package, no new table, no new service beyond the published read.

## How to Verify

```bash
# The item's own tests
cd backend && .venv/bin/python -m pytest \
    tests/ports/test_geo.py \
    tests/api/test_preview_api.py \
    tests/ingestion/test_preview_read.py \
    tests/architecture/test_preview_anonymity.py -q

# The whole suite, with coverage
cd backend && .venv/bin/python -m pytest -q --cov --cov-report=term-missing

# The linter, the contracts, and Django's own checks
cd backend && .venv/bin/python -m ruff check .
cd backend && .venv/bin/python -m ruff format --check .
cd backend && .venv/bin/python manage.py check
make lint-backend

# The coverage gates
make coverage-backend

# The revert verification — thirty-six cases, each watched to fail
cd backend && bash revert_preview_check.sh
```

## Test Coverage

| Module | Coverage |
|--------|----------|
| `ports/geo.py` | 100% |
| `adapters/geo/header.py` | 100% |
| `adapters/geo/fake.py` | 100% |
| `apps/catalog/preview_api.py` | 100% |
| `apps/catalog/preview_schemas.py` | 100% |
| `apps/ingestion/services/preview_read.py` | 100% |

**100 item-scoped tests**, 3208 in the whole backend suite, 99.04% total coverage,
19/19 import contracts kept.

**Thirty-six revert cases, all caught** — thirty-two for the item's own rules and four
for the review's fixes.

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues remaining — the review's five findings are all fixed and
      revert-verified
- [x] Documentation updated — the module docstrings state the new guarantees
- [x] Developer notes captured

## Developer Notes

**A refusal that cannot be rendered is a crash.** The cities endpoint declared
`response={200: PreviewCitiesOut}` with no 429 schema, so every rate-limited request to
it raised `ConfigError: Schema for status 429 is not set` and returned a **500**. The
preview route was fine, which is why the bug survived: the two routes were written in
parallel and only one was tested past its limit. **Two parallel routes need two
parallel tests** — a limit that is never reached is a limit that has never run.

**A response map is a contract, and ninja enforces it.** `Status(429, body)` tells
ninja which schema to validate the body against; if the map has no entry for that
status, ninja raises rather than guessing. The 429 was in the map for one route and not
the other, and nothing about the code said so.

**Unreachable code is not a safety net; it is a claim the code does not make.** The
adapter bounded the header *before* decoding and then bounded the decoded value
*again* — but `unquote` only ever **shortens** a value, so the second check could never
fire. The second check was removed and the reason recorded, because the next reader
would otherwise assume it was load-bearing.

**Two untrusted inputs into one endpoint should have the same bound.** The geo header
was bounded to 64 characters; the `?city=` parameter was not bounded at all. Reading the
two paths side by side is how that asymmetry showed up — the header was bounded because
the review of an *earlier* item had noticed headers are attacker-controlled, and nobody
had carried the lesson to the query parameter. **A bound is a property of the input,
not of the parameter it arrived in.**

**An over-long value should fall through, not truncate.** Truncating would answer with
a different city than the caller asked for — and could answer with one the catalog
happens to hold. Echoing would put an arbitrarily long value into the response body.
Treating it as *no city at all* makes it the same shape as the endpoint's normal path.

**A database's `ORDER BY` on text is a locale collation.** `en_US.UTF-8` ignores
punctuation at the primary level and orders case in a locale-specific way, so two
deployments with different locales would offer the same cities in a different order.
`str.casefold` compares code points and is the same everywhere. **The rule being pinned
is *which mechanism decides the order*, not *what the order is*** — and two attempts at
finding a behavioural discriminator failed, because `"St. John's"` and `"St Johns"` do
not discriminate (the space sorts before the period) and `"A"` and `"a"` cannot (the
catalog's dedup makes them one city). The check is structural now: the read must not
ask the database to sort at all.

**A harness whose levers drift with the source has stopped verifying anything.** After
the review phase edited the source, four cases' patterns no longer matched and the
harness reported four skips. A skip is counted as a **hole**, and the run fails — which
is the right behaviour, because a case whose patch cannot be found has verified nothing
and reporting it as a pass would be a lie.

**A restore that is not verified is not a restore.** Every case gets a unique backup and
**compares the restored file against it byte for byte** before moving on. A restore that
silently fails is worse than no restore: it makes every later result a claim about a
tree that does not exist.

**Duplicated security code drifts.** `_client_ip` is byte-identical in
`apps/identity/api.py` and `apps/catalog/preview_api.py`. It is recorded rather than
fixed, because the shared home would change another app's endpoint — and a security
helper that is copied twice is a security helper that will be fixed in one place only.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-020*
