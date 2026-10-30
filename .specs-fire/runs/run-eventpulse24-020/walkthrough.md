---
run: run-eventpulse24-020
work_item: all-13
intent: onboarding-and-account
generated: 2026-10-30
mode: wide
---

# Implementation Walkthrough: Onboarding, Account & Calendar Connect

## Summary

Thirteen work items, one intent: a visitor arrives, previews the events near them,
signs up, tells the product what they care about, connects their own calendar, and
sees their own events alongside the catalog's — with the calendar's secret URL
encrypted at rest and absent from every log line, response body and DOM node.

The run's central problem is that **a session is a security boundary, a credential is
a secret, and a personal calendar is someone else's data**. Each of the thirteen
items put one of those boundaries in exactly one place and then *proved* it: a
published session resolver no endpoint may reimplement, a deny-list no second copy
may exist beside, and — in the last item — one end-to-end scenario that walks the
whole flow, because the failures that matter live in the seams between the pieces.

**The final item's code review found a live credential leak.** httpx logs the request
URL at INFO, and for a calendar that URL *is* the credential. The deployment pinned
httpx to `WARNING`, so the leak never appeared in a log — and the proof's own
credential-leak sweep was *structurally blind to it*, because it read the root logger
while httpx was pinned below it. The fix was at the source: the caller that holds a
credential now says so, and the transport keeps the URL out of the log for that call
only.

---

## Structure Overview

```
backend/
├── domain/                         ← the rules. Pure: stdlib plus shared.constants
│   ├── address_policy.py           ← THE SSRF deny-list. One table, no second copy
│   ├── dedup.py                    ← the one id rule (ics_item_id), shared by both importers
│   └── timezones.py                ← zone resolution, and the rejection that skips an event
│
├── ports/                          ← the seams. The layer everything may reach
│   ├── fetch.py                    ← SourceFetchPort: one hardened client, two callers
│   ├── fetch_policy.py             ← the TEST-ONLY loopback allowance, with its two gates
│   ├── calendar.py                  ← CalendarPort: entries, feeds, and the three outcomes
│   └── geo.py                       ← the geo port: headers in, a city name out
│
├── adapters/                       ← the outside world. One adapter per dependency
│   ├── crawl/http.py               ← THE hardened client: SSRF, sizes, deadlines, TLS
│   ├── crawl/fake.py               ← the fixture mode, same policy
│   ├── calendar/ics.py             ← ONE ICS adapter for Google, Apple and Outlook
│   └── logging/formatter.py        ← THE redaction boundary: allowlist + patterns
│
├── formats/ics/                    ← one parser, shared by the catalog and the calendar
├── apps/
│   ├── identity/                   ← the accounts: sign-up, sessions, password reset
│   ├── personalization/            ← the user's own events, connections, conflicts
│   ├── catalog/                    ← the public catalog and its Event Fit
│   └── ingestion/                  ← the source pipeline
│
├── worker/tasks.py                 ← the beat: the poll, the pipeline, the digest
└── tests/
    ├── e2e/                        ← the fifteen-step proof and the leak sweep
    ├── architecture/               ← the invariants: AD-3, AD-12, AD-16
    └── fixture_ics_server.py       ← a real TLS ICS server, switchable 200/304/410

frontend/
├── app/preview/                    ← the public preview: anonymous, no session
├── components/preview/             ← the cards, the geo banner, the skeleton
├── lib/event-fit.ts                ← the score's labels and bands
└── lib/preview-{choice,labels}.ts  ← the client-side decision logic
```

The layering is enforced, not merely documented: **19 import-linter contracts**, so a
violation fails the build rather than being noticed later.

```
config | worker
      │
      ▼
apps | adapters        ← the world
      │
      ▼
formats                ← the shapes
      │
      ▼
ports                  ← the seams
      │
      ▼
domain                 ← the rules
      │
      ▼
shared                 ← the constants
```

---

## Architecture

### Pattern Used

**Ports and adapters (hexagonal), with a domain that is pure by construction.** The
dependency rule points *inward*: `domain` imports nothing but the standard library and
`shared.constants`, and that is enforced by a contract rather than by convention.

The reason is specific rather than fashionable. Three things in this project are
**facts about the outside world** — an HTTP response, an SMTP conversation, a geo
header — and each of them can be hostile. If the rule that decides "is this address
allowed?" lived next to the code that opens the socket, then the rule would be
reachable from the code that needs to be wrong. So the rule is in `domain`, the
socket is in `adapters`, and between them is a `port` that both `apps` and `adapters`
can reach — and which neither may redefine.

### Layer Structure

```text
┌─────────────────────────────────────────┐
│  worker/tasks.py   config/              │  the entry points
├─────────────────────────────────────────┤
│  apps/            adapters/             │  the world, and the policies
│   identity          crawl/http           │
│   personalization   calendar/ics         │
│   catalog           logging/formatter    │
│   ingestion         geo/header           │
├─────────────────────────────────────────┤
│  formats/ics/                         │  the shapes
├─────────────────────────────────────────┤
│  ports/                               │  the seams
│   fetch  calendar  geo  fetch_policy    │
├─────────────────────────────────────────┤
│  domain/                               │  the rules, and nothing else
│   address_policy  dedup  timezones      │
├─────────────────────────────────────────┤
│  shared/                               │  the constants
└─────────────────────────────────────────┘
```

### The thirteen items, and what each one owned

| # | Item | Mode | The boundary it put in one place |
|---|------|------|----------------------------------|
| 1 | `account-auth-core` | validate | The account, the session, the password hash |
| 2 | `calendar-connection-model` | validate | The credential, and its encryption |
| 3 | `ics-calendar-adapter` | validate | The ICS parser — one, shared |
| 4 | `calendar-sync-and-polling` | validate | The poll, and the sync's transaction |
| 5 | `auth-api-and-session-seam` | confirm | The session resolver: one, published |
| 6 | `onboarding-state-and-interests` | confirm | The onboarding state, and the digest preferences |
| 7 | `calendar-connect-api` | confirm | The connect endpoint, and the pre-flight |
| 8 | `event-fit` | confirm | The score — session-free, and on the catalog side |
| 9 | `pulse-preview-api-and-geo` | confirm | The public preview, and the geo port |
| 10 | `frontend-auth-surfaces` | confirm | The sign-in surfaces, and the signed-in home |
| 11 | `frontend-onboarding-flow` | confirm | The three-step flow, and the soft wall |
| 12 | `frontend-pulse-preview` | confirm | The preview page, the cards, the geo banner |
| 13 | `e2e-proof-and-contract-tests` | confirm | **The proof that the thirteen compose** |

---

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/ports/fetch_policy.py` | The test-only loopback allowance, gated on the settings module name **and** an active test runner |
| `backend/tests/fixture_ics_server.py` | The switchable TLS ICS server — shared by the e2e proof and the adapter tests |
| `backend/tests/e2e/test_onboarding_and_calendar_proof.py` | The fifteen-step end-to-end scenario and the four-layer credential-leak sweep |
| `backend/tests/e2e/test_loopback_allowance.py` | The proof that the loopback allowance cannot be reached outside a test |
| `backend/tests/e2e/test_fixture_ics_server.py` | The fixture server's own proof, over real TLS through the real client |
| `backend/tests/architecture/test_write_ownership.py` | AD-16: only the owning app writes each table |
| `frontend/app/preview/page.tsx` | The public preview page |
| `frontend/app/preview/page.test.tsx` | Its tests |
| `frontend/components/preview/preview-card.tsx` | One event card |
| `frontend/components/preview/preview-section.tsx` | A titled section of cards |
| `frontend/components/preview/geo-banner.tsx` | The geo banner, and the opt-out |
| `frontend/components/preview/card-skeleton.tsx` | The loading skeleton |
| `frontend/lib/event-fit.ts` | The score's labels and bands |
| `frontend/lib/preview-choice.ts` | The client-side choice logic |
| `frontend/lib/preview-labels.ts` | The display labels |

### Modified

| File | Changes |
|------|---------|
| `backend/ports/fetch.py` | The `credential` flag on the fetch port: the caller that holds a credential says so |
| `backend/adapters/crawl/http.py` | The URL-logging suppression for a credential fetch, and the refusal of a non-verifying SSL context |
| `backend/adapters/crawl/fake.py` | Accepts the `credential` keyword |
| `backend/adapters/calendar/ics.py` | Passes `credential=True`; reads `allowed_ports` from the shared setting |
| `backend/apps/personalization/services/calendar_connections.py` | The pre-flight consults the same deny-policy helper |
| `backend/config/settings_test.py` | The test-only allowance's settings |
| `backend/tests/conftest.py` | The shared `fixture_server` fixture |
| `backend/tests/adapters/test_crawl_http.py` | The credential and SSL-context tests, against a real socket |
| `backend/tests/adapters/test_calendar_ics.py` | The assertion that the adapter passes `credential=True` |
| `backend/tests/adapters/calendar_fakes.py` | Records the `credential` flag |
| `backend/tests/ingestion/pipeline_support.py` | Accepts the `credential` keyword |
| `backend/tests/architecture/test_preview_anonymity.py` | The AD-3/AD-12 invariants |
| `backend/pyproject.toml` | The import contracts; one banned-API exemption |

---

## Key Implementation Details

### 1. The credential is the URL, and the URL is the thing that leaks

A personal calendar's ICS address is pasted by hand, often carries a provider token in
its path, and is often the **only** way to read the feed. It is therefore encrypted at
rest (`EncryptedTextField`), and it is **never** returned by the API.

The subtle part is that the URL also travels through the **HTTP client's logger**.
httpx emits, at INFO:

```
HTTP Request: GET https://provider/calendar/ical/<token>/basic.ics "HTTP/1.0 200 OK"
```

The deployment's answer had been to pin `httpx` and `httpcore` to `WARNING`. That
works — but it is a **deployment-wide** answer to a **per-fetch** fact, and it silences
those loggers for ordinary source fetches too, where the URL is an *identifier* worth
keeping.

The run's last item found this because its credential-leak sweep deliberately lowered
the `httpx` logger, and the sweep failed on the calendar's own request URL. The fix
was to carry the fact where it belongs:

- `SourceFetchPort.fetch` gained a `credential` keyword, defaulting to `False`.
- The calendar adapter passes `credential=True`.
- The transport raises the httpx/httpcore loggers' level for that call only, and
  restores them afterwards.

The scrubber was **not** the right place: a pattern that redacts every `https://` path
breaks `https://x.test/cb?token=[token]&page=2`, which the project deliberately keeps
readable. A scrubber cannot tell a credential URL from an identifier URL — only the
caller that holds the credential knows.

### 2. The test-only allowance has two gates, because one is not enough

The proof needs a calendar on loopback, which the SSRF policy rightly denies. The
allowance that makes it reachable has to be **impossible to enable outside tests**.

The first version checked one thing: the settings module's *name*. The review found
that insufficient, because `DJANGO_SETTINGS_MODULE` is a **deployment-controlled**
environment variable, and `config.settings_test` is a fully functional settings module.
An operator pointing it there would have reached the permissive policy — which admits
*every* address, including a link-local metadata address.

So the name check became **necessary but not sufficient**, and a second gate was added
that no deployment can satisfy by configuration: a test runner must be executing a test
right now (`PYTEST_CURRENT_TEST`).

**Both gates must be independently provable**, and they were not, at first: both refuse
in the same place, so the settings-gate test **still passed with the settings gate
deleted outright** — the runner gate refused instead. The fix was to assert *which*
gate refused. Now:

| Gate removed | Tests that fail |
|--------------|-----------------|
| the settings-module gate | 2 |
| the test-runner gate | 1 |

### 3. The leak sweep sweeps what leaves the process

The sweep looks in **four** places, because they are four separate leaks: the **logs**,
the **database column** (read with raw SQL — `from_db_value` *decrypts on read*, so an
ORM read would have returned the plaintext and proved nothing), **every API response
body**, and the **served markup**.

Two things about the log sweep are worth stating, because both were learned by having
them be wrong:

- **It sweeps the formatter's output, not the raw record.** The boundary is what a log
  sink actually receives. Project loggers are *additionally* swept raw, because their
  raw message must already be clean before the formatter sees it.
- **It is two-directional.** It asserts the httpx records are **absent** for the
  calendar fetch *and* that the calendar's own safe record — "Calendar feed read",
  counts only — is **present**. Without the second direction, a build where the fetch
  produced no log line at all would pass.

### 4. The preview is anonymous, and the proof is byte-identity

AD-12 says the public preview must not read the session. The check is not "looks the
same with and without a session" — it is that the **response bodies are byte-identical**,
over **every** route on the `/public` prefix, discovered from the URLconf rather than
from a hand-written list.

The preview also never stores or logs the resolved city: the IP is used only as part
of a throttle key, which is the same treatment the auth endpoints give it.

### 5. One ICS implementation, two importers

Google, Apple and Outlook all serve iCalendar, and all three redirect the address the
user pasted to a CDN host. So the adapter resolves `SourceFetchPort` from the registry
and asks for one thing a source fetch does not: `allow_cross_host_redirect=True`.
That relaxes the **host**, never the address.

The parser is `formats.ics.parser` — the same one the catalog pipeline uses — so the
two importers cannot fork. The parser hands over times *as written*; the calendar
adapter resolves them, because a personal calendar has no venue registry to resolve
them later.

---

## Security Considerations

| Concern | Approach |
|---------|----------|
| **The session** | One published resolver. Every authed endpoint asks through it; no endpoint accepts a user id from the request. |
| **The calendar credential at rest** | `EncryptedTextField` — encrypted in the column, decrypted on read. The raw column is asserted to be ciphertext by reading it with raw SQL. |
| **The credential in logs** | The caller marks the URL a credential; the transport suppresses httpx's URL line for that call. The sweep covers the **formatter's output**, two-directionally. |
| **The credential in responses** | The stored credential is never returned. The connect API returns the connection, not the address. |
| **The credential in the DOM** | The frontend never receives it, and the served markup is scanned. |
| **SSRF** | **One** deny-list in `domain/address_policy.py`. The resolve-time check and the connect-time pre-flight consult the same helper, so they cannot disagree. The pre-flight's own docstring says it "cannot be bypassed", so it is not the thing that is relaxed. |
| **The test-only allowance** | Two gates: the settings module's name **and** an active test runner. Both independently proven. The `domain` deny-list is untouched by it. |
| **TLS** | A caller-supplied SSL context may **add** a trust anchor; it may not disable verification. The transport refuses `CERT_NONE` or `check_hostname = False`. |
| **Enumeration** | A password-reset request for a known and an unknown email answer `202` with **byte-identical** bodies. |
| **Reset-token reuse** | The token is single-use and bound to its account. The scenario completes a reset and then **replays** the link, asserting the refusal. |
| **Log redaction** | An **allowlist** of fields plus pattern scrubbing. Project loggers never interpolate their args; exception messages are never logged. |
| **CSRF** | Django's own rules, checked in one place — including the branch Django-ninja's cookie check does not cover. |

---

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| **The calendar's own budget** | 5 MB decoded, 5 redirects, 5 s connect, 15 s read, 30 s total — tighter than the source fetch's, because a user-supplied URL gets less room. |
| **The decompression budget** | The *same code* as the source fetch's, with the calendar's numbers. There is one decompression implementation, not two. |
| **Conditional polling** | The connection stores the `ETag` and `Last-Modified`; the poll sends them and the provider answers `304` with no body. The fixture server records the request, so the test asserts the validator was really sent. |
| **The public preview** | Cacheable, and `Vary` carries nothing session-related — so a shared cache cannot serve one visitor's response to another. |
| **Throttling** | Per-IP budgets, keyed on the caller's address, with the scope as a **fixed literal at every call site** — never anything a caller controls. |
| **The poll interval** | **Provisional at one hour.** Recorded as provisional, not as researched. OQ-7 is still open. |

---

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| The session's home | A published resolver in `identity` | "Who is asking?" is asked by every authed endpoint. If each answered differently, scoping could be forged. |
| The credential's home | Encrypted in the column, never returned | The address is the only way to read the feed, and it is the user's secret. |
| The ICS parser | **One**, in `formats/ics`, used by both importers | Two parsers would fork. |
| The SSRF deny-list | **One**, in `domain/address_policy.py` | A second copy is one fix away from being wrong. |
| The test allowance | A per-call **context manager** with two gates | A settings flag was tried and is wrong: it is global, so it weakens the policy for the whole suite. |
| Where the allowance lives | `ports/fetch_policy.py` | The **table** stays in `domain`; the **resolution** must read the environment, and `domain` may not import Django. |
| The credential's leak fix | At the **caller**, not in the scrubber | A scrubber cannot tell a credential URL from an identifier URL. |
| The preview's anonymity check | **Byte-identical bodies**, over every route | An identical body is a stronger claim than similar markup. |
| The browser tests | Vitest + jsdom; **no Playwright** | A browser dependency is a scope decision a proof item should not make silently. |
| The fixture server | A real TLS socket, switchable 200/304/410 | The parts being proven — the SSRF guard, the conditional request, the status mapping, the log — only exist on a real socket. |
| The `X-Forwarded-For` header | Trusted **only** when the deployment says to | Next's rewrite forwards the browser's headers unchanged, so unconditional trust let any caller mint a fresh throttle bucket. Off by default. |
| The resolved city | Never stored, never logged | A response field and nothing else. |

---

## Deviations from Plan

The run's plans were corrected in two places, and both corrections are recorded in
`plan.md` rather than left implicit.

**1. "No production behaviour changes" was wrong (four items' plans).** The proof
needed a real TLS socket, and two production files changed as a result — the *ability*
to add a trust anchor, and the *source* of the port allowlist. The last item's review
then found two more: the `credential` flag on the fetch port, and the refusal of a
non-verifying SSL context. **Four production files changed in total**, and the
production path's *behaviour* is unchanged: the default trust store is still httpx's
own, verification is still on, the `domain` deny-list is untouched.

**2. The allowance's design changed (the last item's plan).** The plan said "a
per-call context manager that refuses to open outside `config.settings_test`". The
review found the name check was necessary but not sufficient, and a second gate was
added. The plan now records this as an amendment.

**3. The last item's scope grew from one plan to four production files** — and that is
recorded as a change rather than as a surprise.

**4. The frontend suite requires Node ≥ 24.15**, which `frontend/package.json` already
declared. Under the environment's default Node v20.20.0 it reports `41 passed, 37
errors` — the errors are `undici`'s, not the project's.

---

## Dependencies Added

**None.** No new Python package, no new npm package, no new system dependency. The
run added one `ruff` banned-API exemption (`ports/fetch_policy.py` for `TID251`), which
is a *configuration* change rather than a dependency.

The fixture server's TLS certificate is generated at runtime with `cryptography`,
which the project already depended on.

---

## How to Verify

1. **The whole backend suite, with coverage**

   ```bash
   cd backend
   uv run pytest --cov --cov-report=term-missing
   ```

   Expected: `3330 passed`, `Required test coverage of 80.0% reached. Total coverage: 99.05%`,
   and **100.00% on `domain/`**.

2. **The layers contract**

   ```bash
   cd backend
   uv run lint-imports
   ```

   Expected: `Contracts: 19 kept, 0 broken.`

3. **The lint and format gates**

   ```bash
   cd backend
   uv run ruff check . && uv run ruff format --check .
   ```

   Expected: `All checks passed!` and `383 files already formatted`.

4. **The frontend suite** — **requires Node ≥ 24.15**

   ```bash
   cd frontend
   npm test
   ```

   Expected: `Test Files 42 passed (42)`, `Tests 429 passed (429)`.

5. **The end-to-end proof alone**, with the leak sweep

   ```bash
   cd backend
   uv run pytest tests/e2e/test_onboarding_and_calendar_proof.py -v
   ```

   Expected: the fifteen-step scenario passes, and the sweep confirms the credential
   appears in no log line, no response body, no served markup, and that the database
   column holds ciphertext.

6. **The allowance cannot escape the tests**

   ```bash
   cd backend
   uv run pytest tests/e2e/test_loopback_allowance.py -v
   ```

   Expected: ten tests pass — the block opens under the test settings, refuses under
   the production settings, refuses with no settings module, refuses with no test
   runner, and leaves the real deny-table policy in force every time.

7. **Manual: the leak the review found**

   Comment out `credential=True` in `backend/adapters/calendar/ics.py` and re-run
   step 5. Expected: the sweep **fails**, naming the httpx line that carried the URL.
   Restore the line and re-run: it passes.

---

## Test Coverage

- **Tests added across the run**: 141 in the final item; the run's suite grew from 3322 to **3330** in the backend and to **429** in the frontend
- **Coverage**: **99.05%** overall, **100.00% on `domain/`**, 328 files at 100%
- **Status**: passing — 3330 backend passed, 429 frontend passed, 19/19 contracts kept

---

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated (`plan.md`, `test-report.md`, `review-report.md`)
- [x] Developer notes captured

---

## Developer Notes

**The frontend suite needs Node ≥ 24.15.** Under Node 20 it fails with `undici`
errors that look like project failures and are not. `frontend/package.json` already
says so.

**`SourceFetchPort.fetch` is an ABC with a `...` body.** Adding a keyword to it makes
every implementation wrong at *call* time, not at *import* time — and one of them was
production code (`adapters/crawl/fake.py`). A protocol change needs its
implementations found by **reading**, not by the type checker.

**`caplog.set_level("INFO")` sets the *root* logger.** A logger pinned below that in
`settings.LOGGING` produces **no records at all**, so a sweep over `caplog` cannot see
it. This is how the credential leak survived a sweep that was looking for exactly
that.

**`EncryptedTextField.from_db_value` decrypts on read.** To assert that a column holds
ciphertext, read it with raw SQL. An ORM read returns the plaintext and proves the
opposite of what it claims.

**`PYTEST_CURRENT_TEST` is set for the whole test *call* phase** and removed
afterwards — so it is present in a fixture body, a plain function, and a test method,
and absent at collection and in any process that is not running a test. It is the
signal the allowance's second gate uses. **It does not begin with `test_`**, because
pytest would collect it as a test.

**The fixture server's certificate needs an `x509.IPAddress` SAN**, not a DNS name:
the proof connects to `127.0.0.1`, and a certificate with only a DNS name fails the
hostname check against an IP literal.

**The fixture server's port is read back from the socket**, never guessed — it binds to
`127.0.0.1:0`, so parallel runs cannot collide.

**The two sides of the port allowlist must read the same setting.** `_refused_port` and
`calendar_limits()` both read `settings.SOURCE_FETCH["allowed_ports"]`. If they did
not, an address could be accepted at connect time and refused on every poll, and the
only evidence would be a slug in the connection's error field.

**A test that cannot fail is not a test.** Every property in this run was planted and
caught — including the three that *did not* fail at first, which turned out to be the
most informative results of the review.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-020*
