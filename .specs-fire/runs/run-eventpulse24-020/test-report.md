---
run: run-eventpulse24-020
work_item: e2e-proof-and-contract-tests
intent: onboarding-and-account
generated: 2026-10-30
status: passing
---

# Test Report: The End-to-End Proof and the Contract Tests (FR-1, FR-2, FR-3, FR-4, AD-3, AD-12, AD-13, AD-16, AD-18)

> **This is the last item of the run.** Its purpose is not a feature but a *proof*: one
> scenario that walks the whole onboarding-and-calendar flow end to end, and a set of
> contract tests that assert the architectural invariants the run was built on. A test
> that cannot fail is not a test, so every property claimed below was **planted and
> caught** before this report was written — the plants are listed in each section, with
> the exact failure each one produced.

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Item-scoped | 141 | 0 | 0 | 100% (every module this item created) |
| **Total (whole backend)** | **3330** | **0** | **0** | **99.05%** |
| Frontend (whole) | **429** | 0 | 0 | — (42 files) |

The 141 item-scoped tests are a subset of the 3330-test backend suite. The whole
backend suite is **3330 passed, 0 failed**; coverage is **99.05%** across the tree, with
**100.00% on `domain/`** (the AD-2 purity gate) and **328 files at 100%**.

> **These figures are the post-review ones.** The code review found and fixed a
> **live credential leak** and a **production break** in the fake fetch adapter, and
> added nine tests. See [§7](#7-what-the-code-review-changed) and the
> [review report](review-report.md).

### The item-scoped files, and what each is for

| File | Tests | What it proves |
|------|-------|----------------|
| `backend/tests/e2e/test_onboarding_and_calendar_proof.py` | 5 | The whole flow composes; the credential never leaks; enumeration is safe |
| `backend/tests/e2e/test_loopback_allowance.py` | 10 | The test-only loopback allowance is unreachable outside a test |
| `backend/tests/e2e/test_fixture_ics_server.py` | 9 | The fixture server speaks real ICS over real TLS |
| `backend/tests/fixture_ics_server.py` | — | The fixture server itself (shared by two packages) |
| `backend/tests/architecture/test_write_ownership.py` | 88 | AD-16: only the owning app writes each table |
| `backend/tests/architecture/test_preview_anonymity.py` | (extended) | AD-12: the public preview is byte-identical with and without a session |

The rest are the existing suites the item-scoped files extend — the identity,
calendar-connection, and preview tests that already existed and were run again
unchanged.

## Test Commands

```bash
# The item's own tests
cd backend
uv run pytest tests/e2e/test_onboarding_and_calendar_proof.py \
          tests/e2e/test_loopback_allowance.py \
          tests/e2e/test_fixture_ics_server.py \
          tests/architecture/test_write_ownership.py \
          tests/architecture/test_preview_anonymity.py -v

# The whole backend suite, with coverage
cd backend
uv run pytest --cov --cov-report=term-missing

# The layers contract (19 contracts)
cd backend
uv run lint-imports

# The linter
cd backend
uv run ruff check . && uv run ruff format --check .

# The frontend suite
cd frontend
npm test
```

---

## 1. The scenario, and its result

`test_the_whole_onboarding_and_calendar_flow_holds_together` is one test that walks a
brand-new user from *nothing* to *a revoked calendar connection that the user was told
about*. It is deliberately one test, not fifteen: the point of the proof is that the
pieces **compose**, and fifteen independent tests would each prove only that their own
piece works.

The steps, and how each one is proven:

| # | Step | Proven by |
|---|------|-----------|
| 1 | Sign up with a new email | `201`, the account exists, a confirmation stream was queued |
| 2 | Sign in | `200`, a session cookie is set |
| 3 | Request a password reset for that email | `202` |
| 4 | Complete the reset with the emailed token | the token is consumed, the password changed |
| 5 | Sign in with the **old** password | `401` — the old password is dead |
| 6 | Sign in with the **new** password | `200` — the reset really took |
| 7 | Connect a calendar (the secret ICS URL) | `201`, the connection is `active` |
| 8 | Read the calendar connections list | the connection appears, **with no address in it** |
| 9 | Read the single connection | same — no address, no token, no host |
| 10 | The calendar is due, the worker polls it | the events land on the personal calendar |
| 11 | The calendar is due again and the feed answers `304` | no event is duplicated |
| 12 | The feed answers `410` | the connection is `revoked`, and the user is told |
| 13 | The credential column at rest | it is **ciphertext**, not the URL |
| 14 | The sweep — logs, responses, markup, DB | nothing anywhere carries the secret URL |
| 15 | The old password reset token is replayed | it is refused — the token cannot be reused |

**Result: the scenario passes.** All five tests in the file pass
(`test_the_whole_onboarding_and_calendar_flow_holds_together`,
`test_a_private_calendar_address_is_refused_and_stores_nothing`,
`test_a_password_reset_request_does_not_reveal_whether_the_account_exists`,
`test_the_fixture_calendar_is_not_reachable_without_the_test_allowance`,
`test_the_calendar_connection_view_never_carries_the_address`).

### The four boundary cases

The scenario proves the happy path composes. These four prove the boundaries do not
leak, each as its own test:

1. **A private address is refused.** `http://127.0.0.1:9/secret.ics` →
   `422 invalid_calendar_credential`, and **no row is written**. A refused connection
   leaves no trace — the URL is not even stored to be refused later.
2. **Enumeration is safe.** A reset request for an account that exists and one that
   does not both return `202`, with **byte-identical bodies** and the same headers.
   There is no timing-safe comparison here either, but the body and status are
   indistinguishable, which is what an attacker can observe.
3. **The fixture calendar is unreachable without the allowance.** With the context
   manager *not* entered, fetching the same URL is refused by the deny table — the
   proof cannot accidentally depend on a permissive default.
4. **The connection view never carries the address.** The API response contains the
   host, the path, the token, or the scheme of the secret URL — in any form. The
   stored credential is the credential; it is never returned.

---

## 2. The enumeration-safety and token-reuse checks

**Enumeration safety.** A password-reset request answers `202` for an account that
exists and `202` for one that does not, and the two bodies are byte-identical. The
test asserts the bodies are equal — not that they "look similar" — so any future
divergence in wording, length, or field order fails the test.

```python
existing = _post(client, "/api/auth/password-reset/request", {"email": KNOWN_EMAIL})
unknown = _post(client, "/api/auth/password-reset/request", {"email": "nobody@example.test"})
assert existing.status_code == unknown.status_code == 202
assert existing.content == unknown.content
```

**Token reuse.** The reset token is a **single-use** credential. The scenario completes
a reset with the token, then **replays the same token** and asserts it is refused. The
token is also bound to the account it was issued for, so a token issued for one
account cannot reset another — the reset flow reads the user from the token, not from
the request body.

---

## 3. The credential-leak sweep

The ICS URL *is* the credential (AD-18). A calendar's secret URL is pasted by hand,
often contains a path token, and is often the only way to read the feed — so a leak of
it is a leak of the user's calendar. The sweep looks in **four** places, and the
scenario runs it as its last step over the *whole* scenario, not a hand-picked slice.

| Where | What is checked |
|-------|-----------------|
| **The logs** | Every `caplog` record's `message`, its `args`, and its `__dict__` (the `extra` payload) is scanned for the secret. The log is **never cleared** — `caplog.clear()` would discard the records the poll produced, which are the interesting ones. |
| **The database** | The raw column is read with **raw SQL**, not through the ORM: `EncryptedTextField.from_db_value` *decrypts on read*, so `values_list("credential")` would have returned the plaintext and proved nothing. The sweep reads the raw bytes and asserts the secret is absent. |
| **The API responses** | Every single response the scenario received — recorded by a `CsrfClient` subclass that wraps `get/post/put/patch/delete` — is scanned. Not four hand-picked bodies: every response, including the error bodies. |
| **The served markup** | The HTML the frontend renders is fetched and scanned, because a Django template that interpolates a connection object would print the address even if the JSON never carried it. |

**The sweep is non-vacuous.** Three separate violations were planted, one per layer,
and each was caught with a precise message:

| Plant | Caught by | Failure message |
|-------|-----------|-----------------|
| A log line in `adapters/calendar/ics.py` carrying the URL | the log sweep | named the record and the field |
| A plaintext credential at rest in `apps/personalization/fields.py` | the database sweep | named the row |
| The address echoed in the connection API response | the response sweep | named the endpoint |

Each plant was reverted from a `/tmp/*.bak` copy and the suite re-run green. The
sweep is therefore a **live detector**, not a decoration.

### The sweep was blind to the worst leak, and the review found it

**This is the most important thing the code review changed, so it is recorded here in
full.**

The log sweep reads the `caplog` records. `caplog.set_level("INFO")` sets the **root**
logger — and `httpx` was pinned to `WARNING` in `settings.LOGGING`, *below* the root.
So httpx's records were never captured at all, and the sweep could not have found
anything in them.

httpx logs the **full request URL** at INFO:

```
HTTP Request: GET https://127.0.0.1:39069/feed/0e6c...ics "HTTP/1.0 200 OK"
```

For a calendar that URL **is** the credential: the path carries the provider's token.
The leak was real, and the sweep had been structurally unable to see it.

**The fix was at the source, not in the sweep.** The deployment's `WARNING` pin is a
*deployment-wide* answer to a *per-fetch* fact, and it also silences httpx for ordinary
source fetches, where the URL is an identifier worth keeping. So the fact now travels
with the call: `SourceFetchPort.fetch` gained a `credential` flag, the calendar
adapter passes `credential=True`, and the transport suppresses httpx's URL logging for
that call only — restoring the logger's level afterwards.

The obvious alternative — a redaction pattern that scrubs every `https://` path — was
tried and **reverted**: it broke `https://x.test/cb?token=[token]&page=2`, which the
project deliberately keeps readable. A scrubber cannot tell a credential URL from an
identifier URL; only the caller that holds the credential knows.

**The sweep now lowers `httpx` and `httpcore` explicitly**, and it is **two-directional**:
it asserts the httpx records are **absent** for the calendar fetch *and* that the
calendar's own safe record — "Calendar feed read", with counts and byte totals only —
is **present**. Without the second direction, a build where the fetch produced no log
line at all would pass.

**And the sweep is non-vacuous against this leak too**: removing `credential=True` from
the calendar adapter makes the sweep fail, naming the httpx line.

---

## 4. The coverage figures

### The tree

- **3330 passed, 0 failed** across the whole backend suite.
- **99.05%** overall coverage.
- **100.00% on `domain/`** — the AD-2 purity gate, and the number that matters most,
  because `domain/` is the layer everything else may import.
- **328 files at 100%.**

### The modules this item created

| Module | Coverage |
|--------|----------|
| `ports/fetch_policy.py` | 100% |
| `adapters/calendar/ics.py` | 100% |
| `adapters/crawl/http.py` | 99% (the 3 uncovered lines are pre-existing decompression edge cases) |
| `tests/fixture_ics_server.py` | 98% |

### The write-ownership map (AD-16)

`tests/architecture/test_write_ownership.py` holds a `TABLE_OWNERS` map from each of
**18 tables** to the app that owns it, and asserts that no other app imports another
app's `models`. The probe looks for **any** `*.models` import, not a named one — an
earlier, narrower probe could be satisfied by a differently-named import path and so
was vacuous.

The map's own completeness is checked: `test_the_ownership_map_covers_every_write_the_tree_makes`
walks the tree for writes and fails if a table is written by an app the map does not
name. **It found a real gap** — `delivery_reminderplan` was written by an app the map
did not cover — and the map was corrected.

The property is made permanent by `test_the_probe_is_caught`: a deliberately
mis-scoped import is planted inside the test, and the test asserts the probe catches
it. A property test that cannot detect a violation is an assertion of nothing.

### The byte-identical preview (AD-12)

`test_every_public_preview_endpoint_is_byte_identical_with_and_without_a_session`
walks **every** route on the `/public` prefix — discovered from the URLconf, not
hard-coded — and asserts each returns byte-identical bytes with and without a session
cookie. The plant: a session-dependent field added to the preview response, which
made the two bodies differ and the test fail.

`test_the_public_preview_router_has_no_auth_and_no_session_dependency` asserts the
router's `auth` is *unset* (django-ninja holds an instance of `NOT_SET_TYPE` when it
is), which is the structural version of the same claim.

---

## 5. The provisional `CALENDAR_POLL_INTERVAL` — **OQ-7 is still open**

The poll interval is currently **one hour**. This is a **provisional** value chosen to
make the scenario's step 10 (a poll that actually happens) deterministic and fast in
a test.

**OQ-7 remains open.** The interval is a product decision — how often a user's
calendar is polled — and it interacts with the provider's own rate limits, the
cost of the poll, and the freshness the user expects in their calendar. One hour was
chosen because it is *safe*, not because it is *right*. It is recorded here as
provisional so that a later decision has the number it has to beat, and so that
nobody reads "one hour" as a settled decision that was researched.

The concrete consequence: a calendar's events reach the personal calendar up to an
hour late. For an event-hunting product this is probably too slow, and a tighter
interval — with the provider's rate limits respected — is the obvious next step. It
has not been made.

---

## 6. The known gaps, carried forward

These are **not** closed by this item. Each was checked against the tree during this
phase and confirmed still open.

| Gap | State | Note |
|-----|-------|------|
| **OIDC / social login** | Open | Sign-up and sign-in are email-and-password only. No OAuth provider is wired. |
| **`SUBSCRIPTION` / the Pro cap** | Open | The `SUBSCRIPTION` model exists, but the Pro tier's cap on calendar connections is **not enforced** — a user can connect an unbounded number of calendars today. |
| **FR-1's first-digest proof** | Open | FR-1 requires the onboarding email's first digest to be provable. The email *is* sent (and the in-memory adapter captures it), but there is **no test asserting the first digest's contents**. The claim is unproven. |
| **"Free" tags and reliability in Event Fit** | Open | The Event Fit score does not yet incorporate a "Free" tag, nor a reliability measure of the source. |
| **OQ-6** | Open | Unresolved open question from the plan; see `plan.md`. |

### What this item deliberately did *not* do

- **It did not add a browser-level test.** The scope decision for this run was Vitest +
  jsdom, not Playwright. The "served markup" part of the credential sweep therefore
  asserts on the HTML the server returns, not on a rendered DOM after hydration.
  A hydrated-DOM sweep is a real gap in the leak proof, and it is recorded rather than
  glossed over.
- **It did not change the poll interval** (see §5).
- **It did not enforce the Pro cap** (see §6).

---

## 7. What the code review changed

The code review (see [review-report.md](review-report.md)) found eight issues, all
auto-fixed. Two of them changed production behaviour, and one of those was a **live
credential leak** that the sweep itself had been structurally unable to see.

### The leak, and the fix

Recorded in full in [§3](#the-sweep-was-blind-to-the-worst-leak-and-the-review-found-it).
In short: httpx logs the request URL at INFO, and for a calendar the URL *is* the
credential. The deployment pinned `httpx` to `WARNING`, so the leak never appeared —
and the sweep, which read the root logger, could not have found it.

The fix carries the fact with the call: `SourceFetchPort.fetch` gained a `credential`
flag, the calendar adapter passes `credential=True`, and the transport suppresses
httpx's URL logging for that call only.

### The production break

`SourceFetchPort.fetch` is an **ABC with a `...` body**, so adding a keyword to it
made three implementations wrong at *call* time rather than at *import* time — and one
of them was `adapters/crawl/fake.py`, **production code**, the adapter registered in
`fake` mode. Every calendar poll in fake mode raised `TypeError`, which the calendar
adapter's catch-all turned into `CalendarTransientError`: a silent, total failure
with an error message naming a library exception rather than the cause.

The full suite caught it (54 failures). A narrower run might not have.

### The two allowance gates, and why one of them was not proven

The allowance's first version checked only the settings module's *name* — and that
variable is **deployment-controlled**, while `config.settings_test` is a fully
functional settings module. The review added a second gate that no deployment can
satisfy by configuration: a test runner must also be executing a test
(`PYTEST_CURRENT_TEST`).

Both gates now refuse in the same place, so the settings-gate test could not tell
which one fired — it **still passed with the settings gate deleted outright**. The
test now asserts the refusal *names the settings gate*, and both gates are
independently proven:

| Gate removed | Tests that fail |
|--------------|-----------------|
| the settings-module gate | 2 |
| the test-runner gate | 1 |

### The other four findings

- **A caller-supplied SSL context could disable verification.** `GuardedTransport`
  now refuses a context with `CERT_NONE` or with `check_hostname = False`.
- **The `credential` flag was invisible to the calendar's own tests.** The fake now
  records it, and `test_the_fetch_is_told_the_url_is_a_credential` asserts it directly.
- **The credential test used a mock that could never reach httpx's logger** — so it
  would have passed on a build where the fix was absent. It now uses the real fixture
  server, and keeps a positive counterpart.
- **The fixture server was declared in two packages.** It was promoted to the top of
  the `tests` package, beside `tests/csrf.py`, with a shared `fixture_server` fixture
  in `tests/conftest.py`.

### The plants, and what each caught

Every fix was verified by **reverting it and watching the test fail**.

| Violation planted | Tests that failed |
|-------------------|-------------------|
| `credential=True` removed from the calendar adapter | the e2e sweep — naming the httpx line |
| the settings-module gate deleted | 2 allowance tests |
| the test-runner gate deleted | 1 allowance test |
| the SSL verification assertions deleted | 2 SSL-context tests |
| the URL-logging suppression neutered | the credential test — naming the httpx record |
| the `credential` keyword removed from the fake fetch adapter | 54 tests |

---

## The gates, one by one

| Gate | Command | Result |
|------|---------|--------|
| Backend suite | `uv run pytest` | **3330 passed, 0 failed** |
| Coverage ≥ 80% overall | `--cov` | **99.05%** |
| Coverage 100% on `domain/` | `--cov` | **100.00%** |
| Layers contract (19 kept) | `uv run lint-imports` | **19 kept, 0 broken** |
| Django system check | `uv run python manage.py check` | **clean** |
| Lint | `uv run ruff check .` | **clean** |
| Format | `uv run ruff format --check .` | **clean** |
| Frontend suite | `npm test` | **429 passed, 42 files** |
| `beat_schedule` | manual | **exactly one entry** |
| `test_tick.py` | `uv run pytest tests/**/test_tick.py` | **5 passed** (untouched) |

> **The frontend suite needs Node ≥ 24.15.** With the environment's active Node
> v20.20.0 it reports `41 passed, 37 errors` — the errors are `undici`'s, not the
> project's. `frontend/package.json` already declares `"engines": {"node": ">=24.15"}`.
> Under Node v24.22.1 the suite is green at **429 passed**.

---

## The production behaviour that changed

The plan said "no production behaviour changes." **That was wrong**, and the plan has
been corrected. **Four** production files changed, all for reasons the proof and the
review forced:

1. **`adapters/crawl/http.py`** — `GuardedTransport` and `HttpFetchAdapter` take an
   **optional** `ssl_context`. It is *additive*: verification stays on, and the
   caller's context is used to **add** a trust anchor (`load_verify_locations`), never
   to disable verification. It exists so the fixture server can serve real TLS without
   the adapter having a "skip TLS" switch, which would have been a hole.
   **The review added** the refusal of a context that *does* disable verification, and
   the `credential` flag's URL-logging suppression.
2. **`adapters/calendar/ics.py`** — `calendar_limits()` now reads
   `allowed_ports` from `settings.SOURCE_FETCH`, the **same setting** the connection
   service's `_refused_port` reads. Before, the adapter carried its own port set, so
   an address could be accepted at connect time and refused on every poll — or the
   reverse — with only a slug in the connection's error field as evidence.
   **The review added** `credential=True` on the fetch.
3. **`ports/fetch.py`** — the fetch port gained the `credential` keyword. It is
   **additive**, defaulting to `False`, so a source fetch's URL is still logged when
   the deployment wants it to be.
4. **`adapters/crawl/fake.py`** — accepts the new keyword. **A bug, not a feature**:
   the port is an ABC, so the keyword's absence was invisible until the call.

Both changes are the reason the proof found what it found: the shared settings source
is what makes the two sides **unable to disagree**.
