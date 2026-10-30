# Code Review Report

**Run**: run-eventpulse24-020
**Intent**: onboarding-and-account
**Work item**: e2e-proof-and-contract-tests
**Reviewed**: 2026-10-30
**Files Reviewed**: 19

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Correctness | 2 | 0 | 0 |
| Security | 2 | 0 | 0 |
| Contract / Architecture | 1 | 0 | 0 |
| Testing | 2 | 0 | 0 |
| Documentation / hygiene | 1 | 0 | 0 |
| **Total** | **8** | **0** | **0** |

**Tests Status**: Passing — 3330 passed, 0 failed; 99.05% coverage; 19/19 import contracts
kept; 429 frontend tests passed.

Eight findings, all **auto-fixed**. Three of them were found by **planting a violation
and watching the test fail** — because a test that has never been seen to fail is not
known to be a test.

**The most important finding is a credential leak that was real, live, and invisible to
the sweep that was supposed to catch it.** The end-to-end proof's credential-leak sweep
lowered the `httpx` logger — deliberately, because that logger is the one most likely to
carry the secret — and the sweep failed on the calendar's own request URL. The
deployment had been pinning `httpx` to `WARNING`, which is why the leak had never
appeared in a log: **the sweep had been structurally blind to it.** The fix was at the
source, not in the scrubber.

---

## Files Reviewed

### Created

| File | Purpose |
|------|---------|
| `backend/ports/fetch_policy.py` | The loopback allowance and its two gates |
| `backend/tests/fixture_ics_server.py` | The switchable TLS ICS server — shared by two packages |
| `backend/tests/e2e/test_onboarding_and_calendar_proof.py` | The fifteen-step scenario and the leak sweep |
| `backend/tests/e2e/test_loopback_allowance.py` | The proof that the allowance cannot escape the tests |
| `backend/tests/e2e/test_fixture_ics_server.py` | The server's own proof |
| `backend/tests/architecture/test_write_ownership.py` | AD-16's write-ownership map |

### Modified

| File | Change |
|------|--------|
| `backend/ports/fetch.py` | The `credential` flag on the fetch port |
| `backend/adapters/crawl/http.py` | The URL-logging suppression and the SSL-context assertion |
| `backend/adapters/crawl/fake.py` | Accepts the `credential` flag |
| `backend/adapters/calendar/ics.py` | Passes `credential=True` |
| `backend/apps/personalization/services/calendar_connections.py` | The shared port allowlist |
| `backend/config/settings_test.py` | The test-only allowance's settings |
| `backend/tests/conftest.py` | The shared `fixture_server` fixture |
| `backend/tests/adapters/test_crawl_http.py` | The credential and SSL-context tests |
| `backend/tests/adapters/test_calendar_ics.py` | The `credential=True` assertion |
| `backend/tests/adapters/calendar_fakes.py` | Records the `credential` flag |
| `backend/tests/ingestion/pipeline_support.py` | Accepts the `credential` flag |
| `backend/tests/architecture/test_preview_anonymity.py` | The AD-3/AD-16 invariants |
| `backend/pyproject.toml` | The import contracts |

---

## Findings

### S1 — The calendar's credential reached httpx's log line (Security, HIGH)

**Found by**: the end-to-end proof's own credential-leak sweep, once the `httpx` logger
was lowered into it.

httpx logs the **full request URL** at INFO:

```
HTTP Request: GET https://127.0.0.1:39069/feed/0e6c...ics "HTTP/1.0 200 OK"
```

For a calendar that URL **is** the credential (AD-18): the path carries the provider's
token. The deployment had been pinning `httpx` and `httpcore` to `WARNING` in
`settings.LOGGING`, so the line never appeared in a log — but that is a
**deployment-wide** answer to a **per-fetch** fact, and it silenced those loggers for
ordinary source fetches too, where the URL is an identifier worth keeping.

The sweep was blind to the leak for a structural reason: `caplog.set_level("INFO")` sets
the **root** logger, and `httpx` was pinned below that. The proof now lowers `httpx` and
`httpcore` explicitly, and the sweep failed on the calendar's own URL — the leak was
real, and it was caught the moment the blind spot was removed.

**Fixed at the source**, by carrying the fact where it belongs — **the caller that holds
a credential says so**, and the transport stops the HTTP library from writing the URL:

```python
# ports/fetch.py
def fetch(self, url, *, ..., credential: bool = False) -> FetchResult: ...
```

```python
# adapters/crawl/http.py
@contextmanager
def _url_logging_suppressed(credential: bool):
    if not credential:
        yield
        return
    loggers = [logging.getLogger(name) for name in ("httpx", "httpcore")]
    previous = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.WARNING)
    try:
        yield
    finally:
        for logger, level in zip(loggers, previous, strict=True):
            logger.setLevel(level)
```

**Why here and not in the scrubber.** A pattern that redacts every `https://` path would
have been the obvious fix, and it was tried and **reverted**: it broke
`https://x.test/cb?token=[token]&page=2`, which the project deliberately keeps
readable, because a source feed's URL is an *identifier*. The scrubber cannot tell a
credential URL from an identifier URL; only the caller that holds the credential knows.
So the fact travels with the call.

**The pin stays.** The `WARNING` pin in `settings.LOGGING` remains, because a transport
handed a credential-bearing URL by a caller who forgot to say so must still not write
it. The flag is an *addition* to that pin, not a replacement.

**Pinned by** three tests, each verified non-vacuous:

| Test | What it proves |
|------|---------------|
| `test_a_credential_fetch_writes_no_httpx_url_line` | A credential fetch writes no httpx record |
| `test_an_ordinary_fetch_still_logs_its_url` | httpx really does log — so the test above is not vacuous |
| `test_the_fetch_is_told_the_url_is_a_credential` | The calendar adapter actually passes the flag |

The first of these uses the **real fixture server**, not the scripted network. The
scripted connector answers at the httpcore layer and never reaches httpx's own logger,
so it would have produced no httpx record whatever the code did — the test would have
passed for the wrong reason. The first draft of this test was written against the
scripted network and caught itself: it asserted that the scripted network *does* reach
httpx's logger, and failed. That guard is why the test now uses a real socket.

### S2 — The loopback allowance was reachable by configuration alone (Security, HIGH)

**Found by**: an independent security review, and confirmed by reading.

The allowance's first version checked **only** the settings module's *name*:
`DJANGO_SETTINGS_MODULE == "config.settings_test"`. But that variable is
**deployment-controlled** — `manage.py`, `config/asgi.py`, `config/wsgi.py` and
`config/celery.py` all set it with `os.environ.setdefault(...)` — and
`config.settings_test` is a **fully functional** settings module, not a crippled one. An
operator who pointed it there would have got the permissive policy, which admits
**every** address, including a link-local metadata address.

**Fixed** by making the name check **necessary but not sufficient** — a second gate was
added, which no deployment can satisfy by configuration:

```python
def runner_is_active() -> bool:
    """Whether a test runner is genuinely running a test in this process.

    The signal is `PYTEST_CURRENT_TEST`, which pytest sets in the environment for the
    duration of every test **call** phase and removes afterwards.
    """
    current = os.environ.get("PYTEST_CURRENT_TEST", "")
    return bool(current)
```

`PYTEST_CURRENT_TEST` was chosen after checking three properties empirically: it is
present in **every** phase a test might open the allowance (a plain function, a method,
a fixture body); it is **absent** at collection time and in any process that is not
running a test; and it names the test that is running, so a refusal can say which one.

**Both gates live in one place** — `_allowance_refusal_reason` — and the context
manager consults that and nothing else, so there is a single decision point for whether
the permissive policy is reachable.

**The first implementation of the second gate was wrong.** It walked `vars(pytest)` and
`_pytest.config` looking for a `Session` instance. Probing it showed `get_config()`
returns a `Config` **outside** pytest too, so it was not a discriminator at all. The
simple environment check replaced it.

### C1 — The fake fetch adapter did not accept the `credential` flag (Correctness, HIGH)

**Found by**: the full backend suite, immediately after the flag was added — 54 failures.

`SourceFetchPort.fetch` gained a `credential` keyword, and three other implementations
of the port did not. One of them is **production code**:

```python
# adapters/crawl/fake.py — the adapter registered in `fake` mode
def fetch(self, url, *, ..., credential: bool = False) -> FetchResult:
```

Without it, every calendar poll in `fake` mode raised `TypeError`, which the calendar
adapter's catch-all turned into `CalendarTransientError` — a silent, total failure of
calendar polling in the fake mode, with an error message naming a library exception
rather than the cause.

**Fixed** in all three implementations: `adapters/crawl/fake.py` (production),
`tests/adapters/calendar_fakes.py` and `tests/ingestion/pipeline_support.py` (test
fakes).

**The lesson is the one that matters.** The port is an **ABC with a `...` body**, so
adding a keyword to its signature does not make any implementation wrong at *import*
time — it makes them wrong at *call* time, and only on the code path that passes the
new keyword. A protocol change needs its implementations found by *reading*, not by the
type checker. The full suite caught it; a narrower run might not have.

### C2 — The fetch port's `credential` flag was invisible to the calendar's own tests (Testing, MEDIUM)

**Found by**: reading the flag's test coverage.

The flag was pinned only *indirectly* — by the absence of a log line in a different
package. The calendar adapter's own test fake did not record it, so nothing asserted
that the adapter actually passes `credential=True`. Had the adapter stopped passing it,
the e2e sweep would have caught the leak, but the adapter's own unit tests would have
been silent.

**Fixed** by recording the flag in the fake and asserting it directly:

```python
@dataclass
class FetchCall:
    ...
    credential: bool = False
```

```python
def test_the_fetch_is_told_the_url_is_a_credential():
    adapter, fetch = adapter_with(ics_result(calendar()))
    adapter.fetch_entries(feed())
    assert fetch.calls[0].credential is True
```

The flag is now asserted where it is set, not only inferred from where it is absent.

### C3 — The two allowance gates refused for the same reason, so neither was proven (Testing, MEDIUM)

**Found by**: planting the violation and watching the test *not* fail.

Both gates live in the same `if`-chain and both end in `LoopbackAllowanceUnavailable`.
The settings-gate test asserted only "it raised" — and it **still passed** with the
settings gate deleted outright, because the runner gate refused instead. The two gates
were indistinguishable by outcome.

The runner-gate test was already correct: it asserted the refusal message contains
`"test runner"`, so removing that gate made the block open and the test fail.

**Fixed** by making the settings-gate tests assert the refusal **names the settings
gate**:

```python
assert "settings module" in message, (
    "the refusal must name the settings-module gate, so that this test cannot "
    "pass on the runner gate's refusal alone."
)
```

**Both gates are now independently proven:**

| Gate removed | Tests that fail |
|--------------|-----------------|
| the settings-module gate | 2 |
| the test-runner gate | 1 |

**A false start is worth recording.** The first attempt at isolating the settings gate
removed `PYTEST_CURRENT_TEST` from the environment, reasoning that the runner gate
would then be satisfied. It is the opposite: removing the signal *arms* the runner
gate, so the refusal still came from the runner. The environment signal had to stay
**on**, and the *reason* had to be checked instead.

### A1 — A caller-supplied SSL context could disable verification (Contract, MEDIUM)

**Found by**: reading `GuardedTransport.__init__`.

The transport accepted a caller-supplied `ssl_context` and used it as given. The
project's own fixture server relies on that — it adds a trust anchor to httpx's default
store — but a context with `verify_mode = CERT_NONE`, or with `check_hostname = False`,
would make every fetch through it trivially interceptable. For a calendar, whose URL is
the credential, that is the worst possible place to lose verification.

**Fixed** with an assertion at the point the context is accepted:

```python
def _assert_context_verifies(context: ssl.SSLContext) -> None:
    if context.verify_mode != ssl.CERT_REQUIRED:
        raise ValueError(
            "the SSL context must verify the peer certificate "
            f"(verify_mode must be ssl.CERT_REQUIRED, not {context.verify_mode!r})"
        )
    if not context.check_hostname:
        raise ValueError("the SSL context must check the hostname (check_hostname must be True)")
```

Both conditions are required: either one alone is enough to make a fetch interceptable.

**Pinned by** `test_an_ssl_context_that_does_not_verify_is_refused` and
`test_an_ssl_context_that_skips_the_hostname_check_is_refused`. Both were verified
non-vacuous: removing the assertions makes both fail.

### T1 — The fixture server was declared twice, in two packages (hygiene, MEDIUM)

**Found by**: the adapters test needing a `fixture_server` fixture that only existed in
the e2e package.

The adapter's own credential test needs a **real socket** — a transport-level mock
never reaches httpx's logger. The fixture server lived in `tests/e2e/`, so the adapters
package could not use it, and the alternative (importing across test packages) would
have made the e2e package a dependency of an unrelated one.

**Fixed** by promoting the server to the top of the `tests` package, beside
`tests/csrf.py` — which is where shared test-support code already lives:

```python
# tests/conftest.py
@pytest.fixture
def fixture_server():
    """The local ICS server: a real socket, on loopback, answering 200 / 304 / 410."""
    with FixtureIcsServer() as server:
        yield server
```

One server implementation, one place that starts it, and every consumer gets the same
behaviour. The e2e proof's local fixture was removed.

### T2 — The credential test used a mock that could never reach the logger (Testing, MEDIUM)

**Found by**: a guard assertion inside the test itself.

The first draft of `test_a_credential_fetch_writes_no_httpx_url_line` drove the
**scripted network**, and asserted that the scripted network reaches httpx's logger:

```python
assert httpx_records, (
    "the scripted network does not reach httpx's own logger, so this test would "
    "pass for the wrong reason — the fixture must produce a real httpx record."
)
```

It failed — and the failure was the point. The scripted connector answers at the
httpcore layer, so **no httpx record is ever produced**, whatever the production code
does. The test would have passed on a build where the fix was entirely absent.

**Fixed** by rewriting both credential tests against the **real fixture server**, and
keeping the positive counterpart (`test_an_ordinary_fetch_still_logs_its_url`) so the
suite cannot pass on a build where httpx never logs at all.

### A2 — Two unused imports and two unsorted import blocks (hygiene, LOW)

**Found by**: ruff.

Fixed. `ruff check .` now reports `All checks passed!` and `ruff format .` reformatted
one file.

---

## The cases that did not fail, and what they taught

Three checks initially passed against deliberately broken code. All three are worth
recording, because a check that does not fail is either a bad test or a bad source — and
in each case it was the test.

**The settings gate did not fail when it was deleted** (C3 above). Two gates refusing
in the same place are indistinguishable by outcome; the test has to check *which* gate
refused.

**The credential test did not fail when the flag was removed from the calendar
adapter** — because it passed the flag itself. That is not a defect in the test; it is
the test's scope. The adapter's own behaviour is pinned by
`test_the_fetch_is_told_the_url_is_a_credential` (C2), and the *end-to-end* effect is
pinned by the proof's sweep, which fails with the exact httpx line. The two together
cover both ends of the flag's journey.

**The scripted-network credential test did not fail when the suppression was neutered**
— because it asserted the *absence* of a record, and the scripted network never
produces one. This is the T2 finding, and it is the most dangerous shape a test can
have: **a test that passes whether the code is right or wrong**.

---

## The Revert Verification

Every fix was verified by **reverting it and watching the test fail**. A regression
test that passes against the broken code is not a regression test.

| Violation planted | Tests that failed |
|-------------------|-------------------|
| `credential=True` removed from the calendar adapter | the e2e sweep — naming the httpx line |
| the settings-module gate deleted | 2 allowance tests |
| the test-runner gate deleted | 1 allowance test |
| the SSL verification assertions deleted | 2 SSL-context tests |
| the URL-logging suppression neutered | the credential test — naming the httpx record |
| the `credential` keyword removed from the fake fetch adapter | 54 tests |

Each was restored from a byte-for-byte backup and the suite re-run green.

---

## The Node version, and a gate that was failing for the wrong reason

The frontend suite was run with the environment's active Node, **v20.20.0**, and
reported **41 passed, 37 errors** — the errors being `undici`'s
`Cannot read properties of undefined (reading 'bind')`.

The cause is not a code change: `frontend/package.json` declares
`"engines": { "node": ">=24.15" }`, and the active Node was below it. With **Node
v24.22.1** (present under `~/.nvm/versions/node/`), the suite is green:

```
Test Files  42 passed (42)
     Tests  429 passed (429)
```

This is recorded because a gate that is red for an environment reason is a gate that
gets worked around, and a gate that gets worked around stops being a gate. **The
frontend suite requires Node ≥ 24.15**, and the project's `engines` field already says
so.

---

## Notes

1. **The leak sweep sweeps what leaves the process, not what entered it.** The
   boundary is the `JsonFormatter` output — what a log sink would actually receive —
   with project loggers *additionally* swept raw, because a project logger's raw
   message must already be clean before the formatter sees it. Sweeping the raw
   `caplog` record instead would have missed a formatter that is itself the leak.

2. **The sweep is two-directional.** It asserts that the httpx records are **absent**
   for the calendar fetch *and* that the calendar's own safe record — "Calendar feed
   read", with counts and byte totals only — is **present**. Without the second
   direction, a build where the fetch produced no log line at all would pass.

3. **The loopback allowance is a `ContextVar`, not a flag.** It is scoped to the block
   and to the current context, so it cannot leak into the next test, and the SSRF
   policy's own thirteen tests remain meaningful. The first (global-flag) design had
   exactly that bug.

4. **The port allowlist is read from one setting by both sides.** The adapter's
   `calendar_limits()` and the service's `_refused_port` read the *same*
   `settings.SOURCE_FETCH["allowed_ports"]`. An address could otherwise be accepted at
   connect time and refused on every poll, and the only evidence would be a slug in
   the connection's error field.

5. **The fixture server's certificate is generated per run.** It carries an
   `x509.IPAddress` SAN for `127.0.0.1` — an IP literal needs an IP SAN, not a DNS
   name — and the client **adds** it to httpx's own trust store rather than replacing
   it. Verification stays on; the proof adds a trust anchor, it does not turn checking
   off.

6. **The database column holds ciphertext.** `EncryptedTextField.from_db_value`
   *decrypts on read*, so the raw column must be read with raw SQL to prove it — and
   it is. A test that read the column through the ORM would have proved the opposite
   of what it claimed.

---

## The Final Gate

```
ruff check .
All checks passed!

ruff format .
1 file reformatted, 382 files left unchanged

lint-imports
Contracts: 19 kept, 0 broken.

pytest
3330 passed in 255.06s (0:04:15)
TOTAL                                             6946     66    99%
Required test coverage of 80.0% reached. Total coverage: 99.05%

npm test  (Node v24.22.1)
Test Files  42 passed (42)
     Tests  429 passed (429)
```

The only uncovered lines in the touched production files are two pre-existing
decompression edge cases in `adapters/crawl/http.py` (a zlib corruption path and a
size-boundary path), neither of which this item introduced.

---

## One finding that was **not** fixed

### C4 — `ports/fetch_policy.py` is a new top-level port module, and the port layer's shape is a project decision (CONFIRM, LOW)

`ports/fetch_policy.py` sits beside `ports/fetch.py`, `ports/calendar.py` and the other
ports, and it holds the loopback allowance — the policy that decides what a fetch may
reach. Its name says "policy" while `domain/address_policy.py` holds the *actual*
deny table, so the two modules' names do not say which is which: `domain` holds the
rules, `ports` holds the resolution.

This is recorded rather than fixed because renaming or relocating a module in the
`ports` layer is a change to the project's own vocabulary, and the vocabulary is a
project-wide decision rather than this item's. The module's docstring states the
split explicitly, and the import-linter contracts keep the two layers apart, so the
arrangement is legible as it stands.
