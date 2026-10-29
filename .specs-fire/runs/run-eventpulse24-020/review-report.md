# Code Review Report

**Run**: run-eventpulse24-020
**Intent**: onboarding-and-account
**Work item**: ics-calendar-adapter
**Reviewed**: 2026-10-29
**Files Reviewed**: 24

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Correctness | 2 | 0 | 0 |
| Contract / Architecture | 2 | 0 | 0 |
| Security | 1 | 0 | 0 |
| Observability | 1 | 0 | 0 |
| Code Quality | 0 | 0 | 0 |
| Documentation | 1 | 0 | 0 |
| **Total** | **7** | **0** | **0** |

**Tests Status**: Passing — 2536 passed, 0 failed; 98.87% coverage; 17/17 import contracts kept.

Every finding was a **defect**, not a style preference, and every one was fixed in the same
pass rather than deferred. Each was verified by reading the code and reproducing the
failure before being acted on — a review finding is a claim, not a fact, and a finding
that cannot be reproduced is a finding that cannot be fixed.

---

## Files Reviewed

### Created

- `backend/formats/__init__.py` (new)
- `backend/formats/ics/__init__.py` (new)
- `backend/formats/ics/events.py` (new)
- `backend/formats/ics/parser.py` (new)
- `backend/formats/text.py` (new)
- `backend/formats/times.py` (new)
- `backend/adapters/calendar/ics.py` (new)
- `backend/tests/adapters/calendar_fakes.py` (new)
- `backend/tests/adapters/test_calendar_fetch.py` (new)
- `backend/tests/adapters/test_calendar_ics.py` (new)
- `backend/tests/architecture/test_formats_pure.py` (new)
- `backend/tests/formats/__init__.py` (new)
- `backend/tests/formats/ics/__init__.py` (new)

### Modified

- `backend/ports/calendar.py` — the port: the three typed outcomes, the entry, the feed
- `backend/ports/fetch.py` — `FetchLimits` moved here; the refusal vocabulary
- `backend/adapters/crawl/http.py` — per-call limits threaded through
- `backend/adapters/crawl/fake.py`
- `backend/adapters/calendar/fake.py`
- `backend/adapters/logging/formatter.py` — the project-logger roots
- `backend/adapters/logging/redaction.py` — the allowlist
- `backend/apps/ingestion/parsers/ics.py` — the catalog's ICS parser
- `backend/apps/ingestion/parsers/types.py`
- `backend/apps/ingestion/parsers/text.py`, `feeds.py`, `jsonld.py` — the moved helpers
- `backend/apps/personalization/services/calendar_connections.py`
- `backend/config/adapters.py`, `backend/config/checks.py`
- `backend/pyproject.toml` — the `formats` layer's coverage config
- `backend/tests/architecture/checkers.py`, `test_import_contracts.py`
- `backend/tests/adapters/test_fakes.py`, `test_logging.py`
- `backend/tests/config/test_adapters.py`
- `backend/tests/personalization/test_calendar_connection_commands.py`
- `backend/tests/ingestion/pipeline_support.py`

---

## Findings and Fixes

### B1 — A floating-time `RRULE` master was silently dropped from the catalog

**Severity**: BLOCKER · **Category**: Correctness · **Status**: Fixed

The catalog parser's `_instance_utc` assumed a `datetime` and reached for
`value.astimezone(UTC)`. The shared parser hands a floating master over with
`start_instant = None` — a floating time names no moment — so the catalog fell back to
`event.start`, which is a *naive* datetime.

The naive value was read as UTC in the shared parser. In the catalog's copy, the fallback
path raised, the event was counted as `unreadable_event`, and **no candidate was produced
at all**. A floating recurring event simply vanished from the catalog: no import, no
warning that the user could act on.

This was a silent regression introduced by the move — the parser module's own docstring
claimed "behaviour is unchanged", and it was not.

**Reproduced** before fixing: a floating `RRULE` master parsed to zero candidates.

**Fix** — `backend/apps/ingestion/parsers/ics.py`:

```python
def _instance_utc(value) -> datetime:
    """The UTC instant identifying a recurrence instance (floating/date read as UTC, id only)."""
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return at_midnight(value).replace(tzinfo=UTC)
    raise TypeError("a recurrence instance needs a date or a datetime")
```

and in `_candidate`, the instance key falls back to the wall clock read as UTC — exactly
the reading a floating `RECURRENCE-ID` gets:

```python
instance = recurrence_id if recurrence_id is not None else event.start_instant
if instance is None:
    instance = event.start
source_item = ics_item_id(uid, _instance_utc(instance))
```

**Tests added** — `backend/tests/ingestion/parsers/test_ics.py`:

- `test_a_floating_series_master_is_read_and_keyed_as_utc` — the master is imported, its
  id is the wall clock read as UTC, and it is not counted as skipped.
- `test_a_recurrence_instance_that_names_no_day_is_refused` — the guard raises rather
  than producing a wrong id.

---

### B2 — The calendar's own limits were dead constants

**Severity**: BLOCKER · **Category**: Contract / Architecture · **Status**: Fixed

The design decision D7 requires the calendar to hand *its own* bounds to the shared
hardened client — a 5 MB decoded budget instead of the source's 10 MB, a 5 s connect
timeout instead of the source's, a 30 s total deadline. The adapter declared all six as
named constants, and **none of them was ever used**: `SourceFetchPort.fetch` had no
`limits` parameter, so `MAX_ICS_BYTES` and the five timeouts were decoration, and the
calendar silently fetched with the *source's* budget.

The six constants were the most visible part of the adapter and did nothing.

**Fix** — the *shape* of the limits moved into the port, so a caller whose content is a
different shape can hand the adapter its own bounds, and `ports` still never imports
Django. `backend/ports/fetch.py`:

```python
@dataclass(frozen=True)
class FetchLimits:
    user_agent: str
    max_bytes: int = 10 * 1024 * 1024
    dns_timeout: float = 3.0
    connect_timeout: float = 5.0
    read_timeout: float = 15.0
    write_timeout: float = 5.0
    total_timeout: float = 30.0
    max_redirects: int = 5
    allowed_ports: frozenset[int] = field(default_factory=lambda: frozenset({80, 443}))
```

`backend/adapters/crawl/http.py` keeps a thin subclass whose only job is *reading the
settings*, and `fetch()` gained a `limits` parameter that is threaded through the
deadline, the backend, the headers, the target check, the redirect cap, the httpx timeout
and `_read_body`.

**Tests added** — `backend/tests/adapters/test_calendar_fetch.py` and
`backend/tests/adapters/test_calendar_ics.py`:

- `test_a_per_call_limit_is_the_one_that_applies` — a per-call budget is honoured.
- `test_the_default_limit_still_applies_when_no_limit_is_given` — a source fetch without
  a limit keeps the source budget.
- `test_the_fetch_carries_the_calendar_s_own_limits` — the adapter hands its own bounds.
- `test_the_calendar_limits_are_tighter_than_the_source_limits` — the 5 MB budget is
  actually tighter.

---

### B3 — The connect endpoint and the adapter disagreed about `http://`

**Severity**: BLOCKER · **Category**: Contract · **Status**: Fixed

`apps.personalization.services.calendar_connections` accepted `http://` when a user
pasted a calendar address; `adapters/calendar/ics.py` refused it. The user was told
their address was accepted, the connection was stored, and the first poll failed — with
the credential on the wire in cleartext in the meantime.

The secret ICS URL *is* the credential, so `http://` is not a downgrade to be silently
upgraded to `https://` — it is a credential sent in the clear on every poll, forever.

**Fix** — the service's shape check now refuses `http://` at *write* time, so the user
hears about it while they are still typing rather than at the first poll with a stored
connection they cannot use:

```python
ALLOWED_SCHEMES = frozenset({"https", "webcal", "webcals"})
```

`webcal://` and `webcals://` are the iCloud spelling; the adapter normalises them to
`https://` at fetch time.

**Tests changed** — `backend/tests/personalization/test_calendar_connection_commands.py`:

- `test_the_three_schemes_are_accepted` — https, webcal, webcals.
- `test_a_plain_http_address_is_refused` — http is refused at write time.

---

### B4 — The new `formats` layer would have bypassed the project-logger redaction

**Severity**: BLOCKER · **Category**: Security · **Status**: Fixed

`adapters/logging/formatter.py` keeps a list of the project's own logger roots. A logger
under one of those roots never interpolates its arguments — they are rendered as
`[redacted]`, because a project logger may be handed a title, a uid or a URL.

The new `formats` layer was not on that list, so a logger in `formats/` — ours, with the
same exposure — would have interpolated its arguments and written a user-visible value
into a log line. The list was maintained by hand and the new layer was not added to it.

**Fix** — `backend/adapters/logging/formatter.py`:

```python
PROJECT_LOGGER_ROOTS = ("apps", "domain", "adapters", "config", "worker", "shared", "formats")
```

**Test added** — `backend/tests/adapters/test_logging.py`:
`test_every_own_package_is_a_project_logger` — parametrizes over every root, including
`formats` and `formats.ics`, and asserts the args are redacted and the title never
appears in the line.

---

### B5 — The refusal vocabulary was a hand-copied fiction

**Severity**: BLOCKER · **Category**: Contract · **Status**: Fixed

The adapter decided "was this refusal ours?" from a hand-copied frozenset of reason
strings:

```python
_REFUSED_REASONS = frozenset({"scheme", "userinfo", "port", "address", "oversized"})
```

Two copies of one vocabulary drift, and this one had already drifted: the set contained
`oversized`, which the transport never produces as a *blocked* error (an oversized body
is a `FetchTooLargeError`, a different class), and it **omitted** `cross_host_redirect`,
which the transport does produce. The accompanying test asserted a reason the transport
never raises — so it proved nothing about the real behaviour.

**Fix** — the transport became the single authority. `backend/ports/fetch.py`:

```python
class FetchBlockedError(FetchError):
    code = "fetch_blocked"

    POLICY_REFUSAL_REASONS = frozenset(
        {"scheme", "userinfo", "port", "address", "cross_host_redirect"}
    )

    @property
    def is_policy_refusal(self) -> bool:
        """Whether this refusal was ours — so a caller must not blame the provider."""
        return self.reason in self.POLICY_REFUSAL_REASONS
```

The adapter now asks the transport rather than keeping its own list:

```python
except FetchBlockedError as exc:
    reason = exc.reason
    if exc.is_policy_refusal:
        raise CalendarRefusedError(details={"reason": reason}) from None
    raise CalendarTransientError(details={"reason": reason}) from None
```

**Test changed** — `backend/tests/adapters/test_calendar_ics.py`:
`test_the_refusal_reasons_are_the_transport_s_own` — asserts the adapter's notion of a
policy refusal is the transport's, not a copy.

---

### B6 — The calendar's log fields were unreadable in production

**Severity**: BLOCKER · **Category**: Observability · **Status**: Fixed

The adapter logs `entry_count`, `skipped_count` and `skipped`. The redaction allowlist in
`adapters/logging/redaction.py` did not include them, so in production **every one of
those fields was `[redacted]`** — the log line said nothing. The test that covered this
read the raw `LogRecord` instead of the formatted line, so it passed against the
unformatted record while production saw nothing.

A reason-slug → count map is safe to log: a slug is one of our own names
(`no_event_start`, `floating_time`, `unplaceable_time`) — never a title, a uid, a URL or
a zone. That distinction is exactly what the allowlist is for, so it belongs there.

**Fix** — `backend/adapters/logging/redaction.py`:

```python
"entry_count",
"skipped_count",
"skipped",
```

**Test changed** — the log assertion now reads the *formatted* line, which is what
production sees, and asserts the slugs are present and a title is not.

---

### C1 — `normalise_url` returned the URL unstripped for `https://`

**Severity**: CONFIRM · **Category**: Code Quality · **Status**: Fixed

`url.strip()` was applied to the `webcal://` branch but not the `https://` branch, so a
trailing space in a pasted address reached the transport as part of the URL. The
transport's URL parser tolerates it, but the two branches of one function should behave
the same way.

**Fix** — the `https://` branch returns `url.strip()` too.

---

### N3 / N4 — The moved helpers claimed a generality they did not have

**Severity**: NIT · **Category**: Documentation · **Status**: Fixed

`formats/text.py` and `formats/times.py` were moved out of `formats/ics/` because they are
format-agnostic — RSS, JSON-LD and iCalendar all carry a title, a description, a venue
name, an all-day span and an overnight end. Their docstrings still said "the ICS
format's", which contradicted the move and would have led the next reader to think the
modules were ICS-specific after all.

**Fix** — both docstrings now open with "**This module is format-agnostic.**" and name
the formats that share the shape.

---

### N5 — The `_uid` docstring described the rule inaccurately

**Severity**: NIT · **Category**: Documentation · **Status**: Fixed

The `_uid` docstring said an `RRULE` master "carries the instance instant, so the
override of a master's *own* instance gets the **same** id as that master" — true — but
omitted that a plain event keeps its bare UID and that an override of a *later* instance
gets its own id. All three branches are in the code; the docstring named one.

**Fix** — the docstring now states all three branches.

---

### N8 — `CROSS_HOST_REDIRECT_NOTE` was a constant that was never used

**Severity**: NIT · **Category**: Code Quality · **Status**: Fixed

`ports/fetch.py` carried a module-level `CROSS_HOST_REDIRECT_NOTE` string that nothing
imported or read. It was documentation wearing a constant's clothes.

**Fix** — converted to a plain comment block attached to the parameter that actually
means it.

---

## Architecture Verification

The layering conflict at the centre of this item — *the catalog parses ICS in `apps`, the
calendar adapter parses ICS in `adapters`, and `adapters` may not import `apps`* — is
resolved by the new `formats` layer, and the fork is prevented **structurally**:

```
AD-2 only formats.ics parses iCalendar files KEPT (1 ignored import)
```

The one ignored import is the catalog parser calling into `formats.ics` — the only
direction allowed. The calendar adapter calls the same module. Neither importer can grow
its own ICS parser without breaking the contract.

The `formats` layer is also proved to be a **leaf** by an AST-level allowlist
(`backend/tests/architecture/test_formats_pure.py`): a format module may import the
stdlib, `icalendar` (the format's own grammar) and its own siblings — and nothing else.
No socket, no database, no Django, no `httpx`. The same parser therefore behaves
identically in the API process, the worker process and a test with no database at all.

**One SSRF implementation remains.** The calendar adapter resolves `SourceFetchPort` from
the registry and never imports `httpx`, `httpcore` or `adapters.crawl`; the address
policy, the deadline, the size cap and the decompression budget are all the *same code*
as the source fetch's, with only the numbers differing.

---

## Security Verification

- **The credential never leaks.** The secret ICS URL *is* the credential (AD-18). Every
  exception leaving `adapters/calendar/ics.py` is a `CalendarError` carrying a reason
  slug — never the URL, the host or the path — and each is raised `from None`, so no
  traceback can carry it either.
- **The fetch logs no URL.** The hardened client's log line carries ids and counts only.
- **The adapter's own log line carries counts and slugs**, never a title, a uid, a URL or
  a zone.
- **`http://` is refused at write time**, so the credential is never put on the wire in
  cleartext.
- **The SSRF policy is not relaxed by the calendar.** The one relaxation — cross-host
  redirects — is about the *host* only; the address policy still runs at connect time on
  every hop, so a redirect to a private address is refused, and a host that resolves to a
  private address is refused too (DNS rebinding).

---

## Test Result

**Passing.** 2536 passed, 0 failed, 98.87% coverage (148 files at 100%), ruff clean,
17/17 import contracts kept.
