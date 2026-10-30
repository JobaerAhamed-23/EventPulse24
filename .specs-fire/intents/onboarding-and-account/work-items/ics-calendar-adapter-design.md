# Design: ICS/Webcal Calendar Adapter

**Work item**: `ics-calendar-adapter`
**Intent**: `onboarding-and-account`
**Mode**: validate (Checkpoint 1 of 2 — this document)
**Date**: 2026-10-29

---

## 1. What this item delivers

The real implementation of `ports.calendar.CalendarPort`: one ICS/webcal adapter, used
uniformly for Google, Apple and Outlook (AD-18).

**In scope**: the fetch, the SSRF policy, the response limits, the HTTP-status →
outcome mapping, the ICS parsing, the mapping to `CalendarEntry`, the credential's
non-leakage, and the tests that prove all of it.

**Out of scope** (separate work items): the polling loop and the import write
(`calendar-sync-and-polling`), the HTTP endpoints (`calendar-connect-api`), the
calendar UI (`frontend-onboarding-flow`).

---

## 2. The problem, stated precisely

This is the project's **first fetch of an arbitrary, user-supplied URL**. Every other
fetch in the system fetches a URL an *operator* configured. This one fetches a URL a
*user* typed, and a user can type `http://169.254.169.254/` as easily as a real
calendar link.

Two things follow, and they drive every decision below:

1. **The address is a secret.** The secret ICS URL *is* the credential (AD-18). It must
   not reach a log line, an exception message, a span attribute, or a trace.
2. **The target is hostile.** The response is arbitrary bytes from an arbitrary server,
   reached through an arbitrary redirect chain, possibly compressed. Every limit that
   `adapters/crawl/` enforces for *sources* must apply here at least as strictly — with
   the reasoning inverted: for a source, a hostile response is a bug in someone's feed;
   for a user-supplied calendar, a hostile response is the expected case.

### The layering conflict

The work item names it, and it is real:

- `pyproject.toml` has the contract **"AD-9 only `adapters.crawl` imports an HTTP client"**.
  The calendar adapter therefore cannot import `httpx`.
- It also cannot import `adapters.crawl`, because **"adapters never import each other"**.
- The ICS parser lives in `apps/ingestion/parsers/ics.py` and imports
  `apps.ingestion.parsers.*`; an adapter must not import `apps`.

Three sub-problems, each with a decision below:

- **D1** — how to fetch, without two SSRF implementations.
- **D2** — where the ICS parsing lives, so the catalog parser and the calendar parser
  cannot fork.
- **D3** — how a `CalendarEntry` differs from a catalog `ParsedCandidate`.

---

## 3. Decisions

### D1 — The fetch goes through `SourceFetchPort`; the calendar adapter never opens a socket

**Decision.** The calendar adapter resolves `SourceFetchPort` from the registry and calls
`fetch()`. It never imports `httpx`, `httpcore`, or `adapters.crawl`.

**The alternatives, weighed:**

| | Option A: fetch through `SourceFetchPort` | Option B: amend the contract, share the client |
|---|---|---|
| SSRF implementations | **One.** The crawl adapter's `GuardedBackend` vets every resolved address at connect time, on every redirect hop. | Two, or one shared module with a new contract. |
| Import contracts | Untouched. `http-client` and `adapters-independent` both stay green as written. | `adapters-independent` must be amended — deliberately, in writing. |
| gzip-bomb protection | Already there: the body is decompressed under an output budget. | Duplicated, or extracted into a shared module (more churn). |
| Redirect limits, timeouts, deadline | Already there, as `FetchLimits`. | Duplicated. |
| Credential in the fetch | The URL is a secret, so the crawl adapter's log line must not carry it. | Same problem, same answer needed. |
| The fetch's own semantics | The crawl adapter fetches **public sources**. It follows same-host redirects only. A calendar provider might redirect `webcal://` → `https://` → a *different* host. | The calendar adapter needs different redirect semantics, which the crawl adapter does not provide. |

**Option A wins on the thing that matters most: one SSRF implementation.** The whole
point of the hardened crawl client is that it was reviewed, tested, and hardened against
DNS rebinding, gzip bombs, cross-host redirects, and unbounded decompression. A second
copy would be a second place for the same class of bug — and the *calendar* copy would
be the one a user can aim at.

**The one thing Option A costs** is the redirect policy: `HttpFetchAdapter` refuses a
cross-host redirect (`FetchBlockedError("cross_host_redirect")`).

**Decision on that point:** a cross-host redirect is **allowed for a calendar**, because
the three providers all do it — Apple's `webcal://p01-calendars.icloud.com` 302s to an
`icloud.com` CDN host, and Google's private ICS address 302s to `googleusercontent.com`.
The address is the user's own credential; they are pointing it at a provider, and the
provider is entitled to move the file.

**So the calendar adapter gets its own redirect policy, expressed as a parameter to the
shared hardened client — not a second client.** See D1b.

### D1b — The hardened client gains a redirect policy parameter, and the address policy is shared

**Decision.** `adapters/crawl/http.py` grows one option:

```python
@dataclass(frozen=True)
class FetchLimits:
    ...
    cross_host_redirects: bool = False   # sources: same host only. Calendars: allow.
```

and `HttpFetchAdapter` takes it from the constructor. The **default is unchanged** —
`False`, same-host only — so every existing source fetch keeps its exact behaviour and
every existing test still holds.

The alternative — a separate `CalendarFetchLimits` subclass or a second adapter class
wrapping `HttpFetchAdapter` — was rejected: it would either fork the fetch loop or push
the difference into the adapter's constructor in a way that makes the SSRF-critical
default easy to change by accident.

**What does NOT change:** the address policy (`is_denied`) is shared verbatim, the
`GuardedBackend` vets addresses at connect time on every hop, the ports are checked on
every hop, the body is decompressed under a budget, and the deadline covers DNS,
connect, TLS, headers, body and every hop. The cross-host relaxation changes **only**
whether the *host* may differ between hops. It never relaxes the address check: a
redirect to `http://169.254.169.254/` is still refused, because the address policy is
applied at connect time regardless of which host it came from.

**The contracts stay green, untouched:**

- `http-client` — the calendar adapter still imports no HTTP client. It imports
  `ports.fetch`, which is a port, not a client.
- `adapters-independent` — the calendar adapter still imports no other adapter. It goes
  through the registry.

**Wait — there is a problem.** The calendar adapter needs the *cross-host* mode of the
HTTP fetch adapter, but it may only reach it through `SourceFetchPort`. The port's
`fetch()` has no parameter for it, and adding one changes a port that the source pipeline
also uses.

**Resolution: the port stays as it is, and the calendar adapter reaches the **concrete**
fetch adapter through the registry, not through the port's interface.**

Hmm. That would make `adapters.calendar` import `adapters.crawl` — which the
`adapters-independent` contract forbids.

**The real resolution.** The cross-host redirect is not a property of the *transport*; it
is a property of the *caller*. And the caller cannot express it through the current port.

So the port grows one optional parameter — and this is the **right** change, because the
port's signature should describe what the caller needs, and "this fetch may cross hosts"
is a genuine caller need that the current signature cannot express:

```python
class SourceFetchPort(ABC):
    @abstractmethod
    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        source_id: UUID | None = None,
        allow_cross_host_redirect: bool = False,
    ) -> FetchResult: ...
```

The default is `False`, so every existing caller is unaffected. The fake adapter ignores
it (it has no redirects). The HTTP adapter honours it. The port's docstring states
*why* it exists: a calendar credential may be redirected to a CDN by its provider, while
a public source may not.

**This is the smallest honest change.** It keeps one SSRF implementation, keeps both
contracts green *as written*, and puts the difference where it belongs — in the request,
not in a fork of the transport.

**Decision D1 (final).** The calendar adapter resolves `SourceFetchPort` from the
registry and calls `fetch(url, allow_cross_host_redirect=True)`. The port gains that one
keyword with a default of `False`; `HttpFetchAdapter` honours it; the address policy,
the size limits, the deadline and the decompression budget are **shared, unchanged**.

**Cost, stated honestly:** the crawl adapter's log line is written for sources, and its
`extra` dict carries `source_id`. The calendar fetch passes no `source_id`, so the log
line identifies the fetch by nothing. That is fixed in D5 (the calendar adapter logs its
own line, and the crawl adapter's line must not carry the URL).

### D2 — The ICS parsing moves down to a neutral package, and the calendar adapter imports it there

**Decision.** The pure ICS parsing moves to a new top-level package, **`domain/ics/`** —
no. Wait. `domain` is pure stdlib (AD-2, contract `domain-pure`), and the ICS parser
needs the `icalendar` library. So `domain` is out.

**Decision.** The parsing moves to **`shared/ics/`**? `shared` is stdlib-only too
(`tests/architecture/test_stdlib_only.py` pins it), so `shared` is out as well.

So the neutral package must be a **new top-level package** that is allowed to use a
third-party library: **`adapters/ical/`**? That is an adapter, and adapters never import
each other.

**The resolution.** The parsing is not an adapter — it is a *format library*, one layer
above `domain` and below `apps`/`adapters`. The layers contract is:

```
config | worker  →  apps | adapters  →  ports  →  domain  →  shared
```

`adapters` and `apps` are the **same layer**. So a module that both `apps.ingestion` and
`adapters.calendar` can import must be at or below the `ports` layer — or in a layer of
its own that both may point at.

**Decision.** A new top-level package **`formats/`**, sitting between `ports` and `apps`:

```
config | worker  →  apps | adapters  →  formats  →  ports  →  domain  →  shared
```

- `formats` may import `ports` and `domain` and `shared`, and third-party libraries.
- `apps` and `adapters` may import `formats`.
- `formats` may import **neither `apps` nor `adapters`**.

This is the clean answer: it is a *format* concern (ICS is a format, like JSON-LD or RSS),
it has no I/O, no Django, and no database — it is the shared implementation that stops
the catalog parser and the calendar parser from forking.

**What moves:** `apps/ingestion/parsers/ics.py` → `formats/ics/parser.py`, together with
the modules it needs that are pure format concerns:
- `apps/ingestion/parsers/times.py` → `formats/ics/times.py` (`all_day_span`,
  `roll_overnight`, `at_midnight`)
- `apps/ingestion/parsers/windows_zones.py` → `formats/ics/windows_zones.py`
- the ICS-specific parts of `apps/ingestion/parsers/text.py` (`plain_text`, and the text
  caps)

**What stays in `apps.ingestion`:** `parsers/types.py` (`ParsedCandidate`,
`SourceContext`, `ParseResult` — the *catalog* shape, used only by the catalog
pipeline), `parsers/text.py`'s catalog-specific helpers (`item_id`, `derived_id`,
`http_url`), and the pipeline itself.

**The fork is prevented structurally**, not by discipline: there is exactly one ICS
implementation, in `formats/ics/`, and both callers import it. A second implementation
would have to be written from scratch, in a place that is not the shared one — and the
import contract `single-ics-parser` (below) fails the build if a module outside
`formats.ics` imports `icalendar`.

**The contract:**

```toml
[[tool.importlinter.contracts]]
id = "single-ics-parser"
name = "AD-9 one ICS parser: only formats.ics imports the icalendar library"
type = "forbidden"
source_modules = ["domain","apps","ports","config","worker","shared","adapters"]
forbidden_modules = ["icalendar"]
allow_indirect_imports = true
```

`formats` is deliberately absent from `source_modules` — it is the one module allowed to
read ICS.

### D3 — `CalendarEntry` is produced by a *separate* mapping over the same parsed VEVENTs

**Decision.** The ICS parser produces one shared intermediate — a **`IcsEvent`** — and
**two** mappers consume it:

- `apps/ingestion` maps `IcsEvent` → `ParsedCandidate` (the catalog shape).
- `adapters/calendar` maps `IcsEvent` → `CalendarEntry` (the personal shape).

**The mapping, stated exactly:**

| `IcsEvent` field | `CalendarEntry` | `ParsedCandidate` |
|---|---|---|
| `uid` | `uid` | `source_event_id` (via `ics_item_id`) |
| `summary` | `title` | `title` |
| `start` (aware UTC) | `starts_at` | `start` (naive, as written) |
| `end` (aware UTC) | `ends_at` | `end` (naive, as written) |
| `tz` (IANA) | `tz` | `start_zone` |
| `all_day` | *(folded into the times)* | `all_day` |
| `status` | *(not carried)* | `status` |
| `location` | *(not carried)* | `venue_name` |
| `description` | *(not carried)* | `description` |

**The key difference, and why the two mappers are genuinely different:** the catalog
keeps times **as written** — a naive wall clock plus a zone name — because
`domain.timezones.resolve_tz` decides the instant later, in the pipeline, where the
venue's zone is known. A personal calendar has **no venue registry**, so its times must
be resolved **at parse time**, by the adapter, using the event's own `TZID`.

**So the shared parser produces times as written, and the two mappers resolve them
differently:**

- The catalog mapper passes the naive time + zone to the pipeline, which calls
  `resolve_tz`.
- The calendar mapper calls `resolve_tz` **itself**, with `source_zone` set and no
  `venue_tz`, and gets an aware UTC instant.

`resolve_tz` is in `domain` — pure, stdlib-only, and already the project's single
authority on turning a written time into an instant. The calendar adapter using it is
the *point*: **there is one timezone resolver in the codebase, and the calendar adapter
does not invent a second.**

**All-day events.** An all-day event has no time of day, so its instant is the local
midnight of its zone. The catalog mapper already handles this (`all_day_span` +
`resolve_tz` on the naive midnight). The calendar mapper does the same thing through
the same code: the day is read in the event's zone.

**Floating times.** A time with no `TZID` and no `Z` is floating: it is a wall-clock
time with no zone. `resolve_tz` **rejects** it (`TZ_UNRESOLVABLE`) — and that is the
right answer for both callers, because a floating time with no zone cannot be placed on
a timeline. The calendar adapter **skips** the event (it cannot be placed); the catalog
pipeline sends it to review. The calendar adapter's skip is counted, not silent.

**Rejected times are counted, not hidden.** The calendar adapter reports how many events
it skipped and why, in a log line with counts only.

### D4 — The three provider outcomes: revoked, transient, and refused

**Decision.** The port grows a typed outcome, and the adapter maps HTTP status to it.

The work item requires that **401, 403, 404 and 410 all map to one "revoked" outcome**
(FR-3: "detected on next poll and the user is prompted to reconnect"), and that **every
other failure is transient** — a transient failure must not mark the connection revoked,
because marking a calendar revoked because the provider had a bad afternoon would make
the user reconnect a calendar that works.

**The port's shape.** `CalendarPort.fetch_entries` currently returns `list[CalendarEntry]`
and raises nothing declared. It needs to express three outcomes. Two shapes are possible:

- **Return a result object** with `entries` and `outcome`.
- **Raise typed errors** for revoked and transient, return entries on success.

**Decision: raise typed errors.** The failure modes are exceptional — a revoked
credential is not a normal result — and the existing `FetchError` hierarchy in
`ports/fetch.py` is exactly this shape, so the calendar port follows the codebase's
established pattern rather than inventing a second one.

```python
class CalendarError(DomainError):
    """Base for every calendar failure. Never carries the URL (AD-13)."""

class CalendarRevokedError(CalendarError):
    """The provider says the credential is no longer valid. The user must reconnect."""

class CalendarTransientError(CalendarError):
    """A temporary failure: 5xx, a timeout, a network error, a malformed response."""

class CalendarRefusedError(CalendarError):
    """We refused to fetch: a blocked scheme, a blocked address, an oversized body."""
```

**The mapping, exactly:**

| HTTP status | Outcome |
|---|---|
| 401, 403, 404, 410 | **Revoked.** The user is prompted to reconnect. |
| 429 | **Transient.** The provider is rate-limiting us. |
| 5xx | **Transient.** |
| 2xx | Success (the body is parsed). |
| 3xx (final) | **Transient.** The redirect chain ended somewhere unexpected. |
| other 4xx | **Transient.** Not one of the four revoked codes, so it is not a revocation. |

**Why "other 4xx is transient" and not revoked.** The requirement names exactly four
status codes. Treating every 4xx as revoked would mark a connection revoked for, say, a
`400 Bad Request` caused by our own request — which is our fault, not the user's, and
would ask the user to reconnect for nothing. The four named codes are the ones that mean
"this credential is not usable any more".

**The non-HTTP failures map too:**

| Failure | Outcome |
|---|---|
| Timeout | Transient |
| Network error | Transient |
| DNS failure | Transient |
| Too many redirects | Transient |
| Blocked address (SSRF) | **Refused** — and it is *our* refusal, not the provider's. It must never mark the calendar revoked. |
| Blocked scheme | **Refused** |
| Body too large | **Refused** |
| Corrupt / unparseable ICS | **Transient** — the file may be truncated by a flaky connection, and the next poll may succeed. |

**The "blocked" cases being *refused* rather than *revoked* is the important one.** A
user could point their calendar at a private address. The fetch is blocked, the
connection is **not** revoked, and the user is told the address was refused — not that
their calendar expired.

### D5 — The credential never reaches a log line, an exception, or a span

**Decision.** Three rules, each with a test.

1. **The crawl adapter's log line carries no URL.** It already carries none: the `extra`
   dict has `job`, `source_id`, `status_code`, `byte_count`, `duration_ms`,
   `error_code`. The calendar fetch passes no `source_id`, and **no URL is ever added**.
   A test asserts the URL is absent from the log record's `extra` *and* from its message.

2. **`httpx`'s own loggers stay at WARNING.** `httpx` logs request URLs at INFO. The
   project's `settings.LOGGING` already sets `httpx` and `httpcore` to WARNING — for the
   *source* fetch. The calendar fetch uses the same client, so the same setting covers
   it. **But** the calendar adapter must not lower it. The test asserts that with the
   `httpx` logger at INFO, the URL is still absent from the captured output.

3. **No exception message carries the URL.** Every error the adapter raises
   (`CalendarError` and its subclasses, and the `FetchError`s it wraps) carries a
   **reason slug** and never the URL, the host, or the path. This matches the `FetchError`
   convention exactly: *"Error `details` carry only a reason slug (and an HTTP status),
   never a host, IP or URL (AD-13)."*

**The traceback is the last place a URL can hide.** If the fetch raises a raw
`httpx` exception, its message contains the URL, and a traceback handler would log it.
The adapter therefore converts **every** exception to a typed error at the boundary —
the same `_as_fetch_error` discipline the crawl adapter uses — and the crawl adapter's
own `_MAPPED` tuple catches `httpx.HTTPError` and `OSError` and re-raises them as
`FetchError`s. The calendar adapter converts the `FetchError`s into `CalendarError`s.
So **no `httpx` exception ever escapes the adapter**, and no traceback carries the URL.

**A test drives each failure path with log capture** and asserts the URL is absent —
revoked, transient, refused, too-large, malformed ICS, and a timeout.

### D6 — The scheme rules

**Decision.**

| Scheme | Behaviour |
|---|---|
| `webcal://` | Normalised to `https://` |
| `webcals://` | Normalised to `https://` |
| `https://` | Used as is |
| `http://` | **Refused** |
| anything else | **Refused** |

**Why `webcal://` becomes `https://` and not `http://`.** `webcal://` is the iCloud
spelling, and iCloud serves the feed over TLS. Normalising it to `http://` would
downgrade a secure fetch and produce a redirect to `https://` anyway.

**Why plain `http://` is refused rather than upgraded.** The work item asks for a
justification, and this is it: an `http://` calendar address would carry the credential
in cleartext on the wire, on every poll, forever. Upgrading it to `https://` would
silently change the host the user typed — and a user who typed `http://` for a host that
does not serve HTTPS would get a confusing TLS error instead of a clear "we need an
HTTPS address". The refusal names the reason (`scheme`) and the user can paste the
`https://` form.

**Where the normalisation happens.** The adapter normalises `webcal://` → `https://`
**before** the fetch, so the *stored* credential is unchanged and the *fetched* URL is
the secure one. This matches what `connect_calendar` says in its docstring: *"The
adapter normalises `webcal://` to `https://` at fetch time, so the stored form and the
fetched form can differ — which is right, because the stored form is what the user
recognises."*

**Why the normalisation is not in `connect_calendar`.** The credential is stored as the
user typed it. Normalising at write time would change the stored form, and the stored
form is what the user recognises and what the fingerprint was computed over.

### D7 — The limits are named constants, and they are *calendar* limits

**Decision.** The calendar fetch uses its **own** limit values, not the source fetch's.
The source limits are tuned for RSS feeds and web pages; a calendar is a different
shape.

```python
MAX_ICS_BYTES = 5 * 1024 * 1024     # 5 MB decoded
MAX_RAW_BYTES = 5 * 1024 * 1024     # 5 MB on the wire
MAX_REDIRECTS = 5
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 15.0
TOTAL_TIMEOUT = 30.0
DNS_TIMEOUT = 3.0
```

**The decompression budget is the important one.** A calendar feed is a file that
compresses extremely well — a year of events is a few hundred kilobytes of XML that
gzips to a few tens of kilobytes. The budget must be on the **decoded** size, and the
crawl adapter already enforces it: `FetchLimits.max_bytes` bounds both the raw bytes
and the decoded bytes, and `_Decoder` never produces more than the caller's budget + 1.
Reusing it means the gzip-bomb protection is the *same code*, not a similar one.

**Why the calendar adapter needs its own `FetchLimits` and not the source's.** The
source `max_bytes` is 10 MB and its `total_timeout` is 30 s. A calendar at 5 MB is
still generous (it is roughly ten years of events), and the tighter bound is worth
having on a user-supplied URL. The limits are *named constants in the calendar
adapter*, as the work item requires, and they are passed into the shared client rather
than configured in settings — because they are a property of the adapter, not of the
deployment.

### D8 — Conditional requests are used, and the ETag is stored per connection

**Decision.** The fetch sends `If-None-Match` / `If-Modified-Since` when the caller
supplies them, and the adapter returns the new validators.

**Where the validators live.** The `CalendarConnection` model gains two nullable
columns, `etag` and `last_modified`. This item does **not** implement the polling loop
(that is `calendar-sync-and-polling`), but the *adapter* must support the validators,
and the port must be able to carry them.

**The port's shape.** `CalendarPort.fetch_entries(feed)` takes only a `CalendarFeed`,
which holds a `Credential`. To pass validators in and get them out, the port grows:

```python
@dataclass(frozen=True)
class CalendarFeed:
    url: Credential
    etag: str | None = None
    last_modified: str | None = None

@dataclass(frozen=True)
class CalendarResult:
    entries: list[CalendarEntry]
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False
```

**Why `not_modified` is a flag rather than an exception.** A 304 is a **success**, not a
failure: the feed has not changed and the caller keeps what it has. Raising would
force the caller to catch an exception to learn that nothing happened. The crawl
adapter returns a `FetchResult` with `status=304` and a `not_modified` property; the
calendar port follows the same convention, so the two ports read alike.

**The credential's `ETag` is not a secret**, but it is still stored per connection and
never in a log line. The validators are opaque strings from the provider.

### D9 — The adapter is registered; the fake stays the default

**Decision.** `config/adapters.py` gains:

```python
CALENDAR_ADAPTER = "adapters.calendar.ics.IcsCalendarAdapter"
```

in `REAL_ADAPTERS`, so `ADAPTER_MODE=real` uses it and `ADAPTER_MODE=fake` keeps
`FakeCalendarAdapter`.

**The fake stays the local and CI default**, exactly as the work item requires.

**One dependency to state.** The ICS adapter needs a `SourceFetchPort`. It resolves it
from `ports.registry.get_fetch_port()` — **not** by constructing `HttpFetchAdapter`
itself. That keeps the adapter mode meaningful: in `fake` mode the calendar adapter
fetches from the fixture server, and in `real` mode it fetches over the network, with
the *same* SSRF protections either way.

**But `ports.registry` is in `ports`, and `adapters` may import `ports`** — the layers
contract puts `adapters` above `ports`, so `adapters → ports` is allowed. And
`ports.registry` imports Django settings, which is fine: the crawl adapter's
`HttpFetchAdapter` already imports `django.conf.settings`.

**The dependency is injected, not looked up inside the adapter.** The adapter's
constructor takes the fetch port, defaulting to the registry. That makes the adapter
testable with a scripted fetch, without a socket.

### D10 — The mapping to `CalendarEntry`: the `uid` and the recurrence

**Decision.** `CalendarEntry.uid` is the ICS `UID`, exactly as written.

**RRULE is not expanded** (FR-31 is out of scope). The work item asks the design doc to
state exactly what is produced for an `RRULE`, and this is it:

> A `VEVENT` with an `RRULE` produces **exactly one** `CalendarEntry`: the master
> event's own `DTSTART`. No instances beyond the first are generated. The entry's `uid`
> is the master `UID`, unmodified — **no `#instance` suffix**.
>
> A `VEVENT` with a `RECURRENCE-ID` produces **one** `CalendarEntry` for that
> override, whose `uid` is `UID#<RECURRENCE-ID>` — the same shape the catalog uses for
> `ics_item_id`, so a recurring instance never collides with its master.

**Why the master and the override need different `uid`s.** The `(connection, uid)`
constraint on `PersonalEvent` is unique. If the master and its override both carried the
bare `UID`, the second import would violate the constraint and the user would lose an
event. The catalog already solved this: `domain.dedup.ics_item_id(uid, instance_start)`
appends `#<YYYYMMDDTHHMMSSZ>` for a recurring instance.

**The calendar adapter uses the same rule, and the same function.** `domain.dedup` is
in `domain` — pure, stdlib-only, and already the project's authority on ICS item
identity. The adapter calls `ics_item_id`, so:

- a plain event → `uid` (bare);
- an `RRULE` master → `uid` + `#` + its own `DTSTART` in UTC — **not** the bare UID,
  because the master is an instance of the series, and the catalog treats it that way;
- a `RECURRENCE-ID` override → `uid` + `#` + the `RECURRENCE-ID` instant in UTC.

**This makes the two importers agree on identity.** The catalog's
`ics_item_id` and the calendar adapter's `uid` are the same string for the same event,
so the same event imported by both paths lands on the same identity.

**Why the master's `uid` carries its instance suffix.** Because the *next* import of the
same feed must produce the *same* `uid` — it is the master, and its `DTSTART` does not
move. And an override must produce a *different* `uid` from the master, or the unique
constraint would reject it.

### D11 — The tests run against a local server and recorded fixtures; no live network

**Decision.** Three layers of test, all offline:

1. **A scripted fetch** (a fake `SourceFetchPort`) for the adapter's own logic: the
   status mapping, the scheme rules, the parsing, the credential's non-leakage. Fast,
   and it can simulate any status.
2. **A local HTTP server** for the *real* `HttpFetchAdapter` under the calendar's
   limits: the gzip bomb, the oversized body, the redirect chain, the timeout. The
   crawl adapter's tests use a scripted network (`httpcore` mock transports); the
   calendar adapter reuses the same technique, so no socket is opened.
3. **Recorded fixtures** — a Google-shaped, an Apple-shaped and an Outlook-shaped ICS
   file — for the parsing. Three real-world shapes, because the three providers differ:
   - **Google**: `DTSTART;TZID=America/Los_Angeles`, an `RRULE`, a `RECURRENCE-ID`
     override, and a `VTIMEZONE` block.
   - **Apple**: `DTSTART;VALUE=DATE` (all-day), a floating time, and a
     `TZID=Europe/London` time.
   - **Outlook**: a **Windows** `TZID` (`"W. Europe Standard Time"`), which
     `windows_zones.map_zone` must convert to `Europe/London`.

**No live network in CI.** Every test either injects a fake fetch or drives the local
scripted network.

---

## 4. What the port looks like after this item

```python
# ports/calendar.py

class CalendarError(DomainError): ...
class CalendarRevokedError(CalendarError): ...
class CalendarTransientError(CalendarError): ...
class CalendarRefusedError(CalendarError): ...

@dataclass(frozen=True)
class CalendarFeed:
    url: Credential
    etag: str | None = None
    last_modified: str | None = None

@dataclass(frozen=True)
class CalendarResult:
    entries: list[CalendarEntry]
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False

class CalendarPort(ABC):
    @abstractmethod
    def fetch_entries(self, feed: CalendarFeed) -> CalendarResult: ...
```

**The break with the current signature** — `fetch_entries` returned `list[CalendarEntry]`
and now returns a `CalendarResult` — is deliberate, and it is a break with
`FakeCalendarAdapter` too, which is updated in the same change. There is one caller
(the polling item, not yet written), so the break costs nothing today.

**Why the result is a dataclass and not the entries directly.** Two reasons, both
needed: the **validators** must come back so the caller can store them (D8), and the
**304 case** must be expressible as a success with no entries (D8).

---

## 5. The contracts after this item

| Contract | Change |
|---|---|
| `layers` | **Amended**: a new `formats` layer between `apps \| adapters` and `ports`. |
| `http-client` | **Unchanged.** The calendar adapter imports no HTTP client. |
| `adapters-independent` | **Unchanged.** The calendar adapter imports no other adapter. |
| `domain-pure` | **Unchanged.** `formats` is not `domain`. |
| `single-ics-parser` | **New.** Only `formats.ics` imports `icalendar`. |

**The `layers` amendment** is the one that needs writing down carefully:

```toml
layers = [
    "config | worker",
    "apps | adapters",
    "formats",
    "ports",
    "domain",
    "shared",
]
```

`formats` sits below `apps`/`adapters` and above `ports`. `domain` remains pure, and
`formats` may import `ports` (it does not need to, but the layer allows it).

**Is a new layer worth it?** The alternative is putting the shared ICS parser in
`ports` — but `ports` is a set of **ABCs over frozen dataclasses**, not a library of
implementations; putting a parser there would be a category error. The alternative of
putting it in `shared` fails because `shared` is stdlib-only and the parser needs
`icalendar`. So `formats` is the answer, and it is a small, honest layer: *formats that
more than one consumer parses*.

---

## 6. The risk register

| Risk | Mitigation |
|---|---|
| A second SSRF implementation creeps in | `http-client` and `adapters-independent` contracts stay green **as written**; the calendar adapter cannot import `httpx` at all. |
| The calendar and the catalog fork into two ICS parsers | `single-ics-parser` contract: only `formats.ics` may import `icalendar`. |
| A time is resolved two different ways | One resolver: `domain.timezones.resolve_tz`, called by both mappers. |
| The URL leaks into a log | Three tests drive each failure path with log capture; the `httpx` logger is asserted to stay at WARNING. |
| A revoked calendar is not detected | The four status codes are mapped explicitly, one test each. |
| A transient failure wrongly marks a calendar revoked | Everything that is not one of the four codes is transient. |
| The cross-host relaxation weakens the SSRF policy | The relaxation is about the **host**, not the **address**: the address policy still applies at connect time on every hop. A redirect to `169.254.169.254` is still blocked. |
| A gzip bomb in a calendar feed | The shared client's decompression budget, unchanged. |

---

## 7. The decisions, in one table

| # | Decision |
|---|---|
| D1 | The calendar adapter fetches through `SourceFetchPort`, resolved from the registry. One SSRF implementation. |
| D1b | The port's `fetch()` gains `allow_cross_host_redirect: bool = False`. The HTTP adapter honours it; every existing caller is unaffected. |
| D2 | The ICS parsing moves to a new `formats/ics/` package. `apps.ingestion` and `adapters.calendar` both import it. |
| D3 | The shared parser produces `IcsEvent`s; two mappers produce `ParsedCandidate` (catalog) and `CalendarEntry` (personal). Both use `domain.timezones.resolve_tz`. |
| D4 | 401/403/404/410 → **revoked**. Everything else → **transient**. Our own refusals (blocked address, blocked scheme, too large) → **refused**, which never marks a calendar revoked. |
| D5 | The URL never reaches a log, an exception message, or a span. Every `httpx` exception is converted at the boundary. |
| D6 | `webcal://`/`webcals://` → `https://`. `http://` and every other scheme → refused. |
| D7 | Calendar-specific named limits (5 MB decoded, 5 redirects, 5 s connect, 15 s read, 30 s total, 3 s DNS). The decompression budget is the shared one. |
| D8 | Conditional requests are supported: `CalendarFeed` carries the validators, `CalendarResult` returns them, and a 304 is a success with `not_modified=True`. |
| D9 | The adapter is registered in `REAL_ADAPTERS`; the fake stays the default. The fetch port is injected. |
| D10 | `uid` follows `domain.dedup.ics_item_id`: bare for a plain event, `#<instant>` for an `RRULE` master and for a `RECURRENCE-ID` override. No RRULE expansion. |
| D11 | Three offline test layers: a scripted fetch, the scripted network, and three recorded provider-shaped fixtures. |

---

## 8. What is deliberately *not* done here

- **No RRULE expansion** (FR-31). A master produces one entry.
- **No polling, no scheduling, no import write** — `calendar-sync-and-polling`.
- **No HTTP endpoints** — `calendar-connect-api`.
- **No `CalendarConnection.etag` column** — that belongs to the polling item, which owns
  the write. This item makes the *adapter* capable of conditional requests; the polling
  item stores the validators.
- **No venue lookup.** A personal calendar has no venue registry, so the calendar's
  `CalendarEntry` carries no venue at all.

---

## 9. Standards Referenced

- `docs/ARCHITECTURE-SPINE.md` — AD-2 (layers), AD-6 (UTC + the zone preserved), AD-9
  (SSRF, sizes, the HTTP client), AD-13 (no PII in logs), AD-16 (write ownership), AD-18
  (the calendar is a port; the credential is a secret), AD-21 (UTC)
- `run-eventpulse24-012` — the hardened fetch's history, including the `httpx` URL-logging
  and gzip-bomb findings, both of which apply again here
- `.specs-fire/runs/run-eventpulse24-020/plan.md` — the run's plan
