---
run: run-eventpulse24-018
work_item: real-feeds-and-e2e-proof
intent: event-catalog-ingestion
generated: 2026-10-28
mode: confirm
---

# Implementation Walkthrough: Real Feeds & End-to-End Proof

## Summary

The intent now has a proof. An idempotent management command registers the proof sources,
their venues, the `editorial` group and the local operator; a sixteen-test end-to-end suite
drives the whole chain — command → tick → ingest → catalog API → tick again — against
recorded fixtures, so CI never opens a socket. Two real, ToS-safe public feeds (the
Montgomery Museum of Fine Arts' JSON-LD page and its iCal feed) are registered by the same
command with `--real`, and they ingest successfully on the local stack. The README has a new
"Local ingestion" section so an operator can do the same on Ubuntu or macOS.

## Structure Overview

The change is one command, two data files and one test suite, wired into the architecture
that the earlier work items of this intent built.

The **seed command** is a *client* of the published ingestion services, never a direct
writer. It asks the source registry to register or update each feed, the venue registry to
register or correct each venue, and it assigns the `editorial` group's permissions through
`ContentType`, so the permission codenames are derived rather than hard-coded. Because it
goes through the services, every source, venue and ToS review it creates gets its audit
row, and the AD-14 rule holds in the seed path exactly as it does in the admin path.

The **two feed files** carry the ToS/robots note and the ingestion cadence with the feed
itself, so the note travels with the source rather than living in prose. The fixtures file
is the CI set; the real file is the manual set. The command picks one and behaves
identically either way — `--real` swaps the feed set, not the behaviour.

The **end-to-end suite** runs the real seams: the management command, the registry
services, the 60-second tick, the scheduling claim, the ingest pipeline, the catalog read
service and the HTTP API. Only two things are substituted, both deliberately — the fetch
(serve the recorded fixtures through `FakeFetchAdapter`) and the broker (record the
enqueued jobs and run them inline). The suite's central claim is that a second tick
changes nothing, and it is deliberately *not* vacuous: the test backdates each source's
last attempt so the second tick genuinely re-ingests the same bytes.

The **JSON-LD fixture** adds a third acquisition method to the recorded set, with an
`@graph` containing a plain event, an event with a different schema type and an
`EventSeries` whose `subEvent` array expands into two instances. It also carries a
deliberately broken JSON-LD block and a `text/javascript` decoy, so the parser's refusal
path is exercised by the fixture rather than only by a unit test.

## Architecture

### Pattern Used

The command is a **client of a service layer** — the same pattern the Django admin uses
(AD-5, AD-14). It holds no ORM queries of its own beyond the two published lookups; every
mutation goes through a named command in `apps/ingestion/services/`, so the audit trail is
not optional and cannot be bypassed by a shortcut in the seed path.

### Layer Structure

```text
┌─────────────────────────────────────────────┐
│  Presentation                                │
│  seed_local_stack · Django admin · catalog API│
├─────────────────────────────────────────────┤
│  Application                                 │
│  source_registry · venue_registry            │
│  scheduling · ingest_source · ingest_item    │
├─────────────────────────────────────────────┤
│  Domain (pure, stdlib only)                  │
│  dedup · timezones · identity · lifecycle    │
├─────────────────────────────────────────────┤
│  Infrastructure                              │
│  ports/ (fetch) · adapters/ (fake + http)    │
│  worker/ (Celery) · shared/db (2 schemas)    │
└─────────────────────────────────────────────┘
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/config/management/commands/seed_local_stack.py` | The idempotent seed: sources, venues, the `editorial` group, the operator. Flags `--real` and `--list`. |
| `backend/config/local_feeds.json` | The real feed set: the MMFA JSON-LD page and its iCal feed, with the recorded robots/ToS note. |
| `backend/config/local_feeds.fixtures.json` | The CI feed set: one fixture per acquisition method, plus the four fixture venues. |
| `backend/tests/e2e/test_end_to_end.py` | The sixteen end-to-end tests: the seed, the editorial group, the whole chain, the second tick. |
| `backend/tests/e2e/conftest.py` | The two seam recordings — the broker and the outbox. |
| `backend/tests/e2e/mutation_probe_e2e.py` | Nine mutation probes: each applies one real bug and checks that the suite catches it. |
| `backend/tests/e2e/__init__.py` | Makes `tests/e2e` a package so its `conftest.py` is scoped to it. |
| `backend/tests/ingestion/test_seed_local_stack.py` | The command's own logic: the duration parser, `--list`, and the four refusals. |
| `backend/tests/fixtures/sources/events.jsonld.html` | The JSON-LD fixture: an `@graph` with two plain events and a two-instance series, plus a broken block and a decoy. |

### Modified

| File | Changes |
|------|---------|
| `backend/apps/ingestion/services/source_registry.py` | Added `find_source_by_url(url)` — a published lookup so a client can find a source before registering a duplicate. |
| `backend/apps/ingestion/services/venue_registry.py` | Added `find_venue(name=, city=, country_code=)` — the same, by the venue's fingerprint. |
| `backend/tests/fixtures/sources/index.json` | Registered the JSON-LD fixture's URL → file mapping for the fake fetch adapter. |
| `README.md` | The new "Local ingestion" section: seeding, triggering, reading, the fetch adapter, and the manual real-feed run. |

## Domain Model

No new entities. The command creates rows in the models the earlier work items of this
intent defined — `Source`, `Venue`, `TosReview` — and the domain rules it must respect
were already in place:

| Entity | Properties | Business Rules |
|--------|------------|----------------|
| `Source` | url, acquisition_method, source_type, city, tz_coverage, ingestion_cadence, tos_status, status, last_attempted_at, last_ingested_at | A `crawl` source needs an approved ToS review (FR-17); `delete` is never granted (FR-13); a method or host change resets `tos_status`. |
| `Venue` | name, city, country_code, tz, venue_fingerprint | The fingerprint is the identity and is fixed at registration; only `tz` can be corrected later. |
| `TosReview` | source, decision, evidence_url, notes | An approval needs a valid `https://` evidence URL; one review per source, never stacked by a re-run. |

## Key Implementation Details

### 1. The editorial group's twelve permissions, derived not hard-coded

The command asks `ContentType` for the six ingestion models it needs and builds each
codename as `<action>_<model>` — so `TosReview` becomes `add_tosreview` and
`EventStateChange` becomes `view_eventstatechange`. If a content type or a permission is
missing, the command refuses with a `CommandError` rather than seeding a group with the
wrong permissions. The permissions are then **assigned** (`group.permissions.set(...)`),
not appended, so a stale grant added by hand does not survive the next run.

`delete` is deliberately absent from every model: sources are paused, never deleted.

### 2. Idempotency through published lookups

The command cannot import `Source` or `Venue` — the `models-ingestion` import contract
forbids it. So the two registries that own those models publish a lookup, and the command
asks "does this already exist?" before it registers. A source is found by its
*canonicalized* URL, so a trailing slash or a `www.` prefix does not create a duplicate; a
venue is found by its fingerprint, which is the identity rule the data model already
defines.

### 3. The second tick that is not vacuous

A source is due when its last attempt is older than its cadence, so after the first
ingest the source is not due and a second tick would claim nothing. The "nothing changed"
assertion would then be proving only that the scheduler was idle. The test backdates
`last_attempted_at` by five hours, so the second tick genuinely re-ingests the same
fixtures — and the assertion then proves the *ingest path* is idempotent. The paired test
`test_a_corrected_venue_timezone_re_resolves_its_events` proves the same path does
change events when it should: correcting the venue's timezone from New York to Chicago
moves every start.

### 4. The mutation probes, and the one that could not be caught

Nine probes each apply one real bug to the implementation and require the end-to-end suite
to fail. The original eighth probe — "an unchanged item is re-resolved and rewritten, so a
re-ingest bumps the version" — **could not be caught**, and the reason turned out to be the
finding of the run: the ingest path is idempotent by *two* independent mechanisms. The
content-hash short-circuit returns `unchanged` before resolution, and even when that is
disabled the change classifier returns `None` for identical facts, so nothing is rewritten.
A test that cannot fail is worse than no test, so the probe was replaced by two that are
genuinely reachable — one that breaks the JSON-LD `subEvent` expansion, and one that drops
the venue's timezone from the content hash — and a new test was added that reaches the
second one.

### 5. The real feeds and their robots note

The MMFA's `robots.txt` disallows only `/wp-admin/` for `User-agent: *` and asks for a
`Crawl-delay: 10`. The registered cadence is four hours, so the crawl delay is honoured
with room to spare, and the manual step fetches each URL once. The JSON-LD URL redirects
once, to `/programs-events/calendar/`; the fetcher follows it and the source keeps its
registered URL. The iCal feed is the publisher's own advertised subscription.

**RSS was dropped from the real set**, and the reason is recorded rather than hidden: the
MMFA's WordPress feeds return HTTP 500, and every reachable robots-clear RSS feed lacks
the `ev:` namespace that the parser requires. A fixture RSS source still exercises the
method in CI, and the real set covers two of the three methods as the acceptance criteria
require.

## Security Considerations

| Concern | Approach |
|---------|----------|
| Who may register a source | The `editorial` group holds exactly twelve permissions; `delete` is absent on every model. The operator uses the group, never superuser, and the command demotes it if something else granted it superuser. |
| Superuser escalation | The seed command forces `is_superuser = False` on every run, and a test proves the demotion happens. |
| ToS provenance | Every real feed carries a recorded decision, an `https://` evidence URL and a note that names the robots rule it relies on. A `crawl` source without an approved review is refused by the registry service (FR-17). |
| Untrusted source content | The fetch runs behind a port with a fake adapter and an HTTP adapter; the parser treats the payload as untrusted (AD-9). The JSON-LD fixture carries a broken block and a decoy to exercise that. |
| Credentials | The committed operator password is a local `example.test` account, created only by the seed command on a developer's machine. It is not a real credential. |
| Write path | Every write goes through a published service with an audit row, so the seed path cannot bypass the audit trail (AD-5, AD-14). |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| The seed command is idempotent and cheap to re-run | The lookups are indexed queries on the canonicalized URL and the venue fingerprint; no scan, no re-registration. |
| A re-ingest must not rewrite the catalog | The content hash short-circuits before resolution, so an unchanged feed costs one hash and no writes. The ICS fixture additionally returns `304 Not Modified` through the conditional-request path, so a second fetch transfers no body at all. |
| The scheduler must not claim work twice | The claim uses `FOR UPDATE SKIP LOCKED` and is keyed on the last attempt, so concurrent ticks cannot double-claim. |
| The catalogue read stays a plain read | `GET /api/catalog/events` is session-free and cookie-free, so it does not touch `personal` at all. |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Which real feeds | The MMFA's JSON-LD page and its iCal feed | Both are the publisher's own public listings; the robots note allows them and the crawl delay is honoured. |
| Which real methods | JSON-LD and ICS, not RSS | MMFA's WordPress feeds return 500; every reachable robots-clear RSS feed lacks the `ev:` namespace the parser requires. The fixture set still covers all three. |
| How the feed data is stored | Two committed JSON files, one per feed set | The ToS/robots note and the cadence travel with the feed instead of living in prose. |
| How the editorial group's permissions are named | Derived from `ContentType` at run time | A hard-coded codename breaks the moment a model is renamed; deriving it also lets the command refuse a half-migrated database. |
| Assigned or appended | Assigned (`permissions.set`) | A stale grant must not survive; the test proves the next run removes one added by hand. |
| The local operator's rights | Staff, in the `editorial` group, never superuser | AD-14 and plan decision D2. The command demotes it if something else made it a superuser. |
| How the second tick is forced | Backdate `last_attempted_at` | Without it the "nothing changed" assertion would pass vacuously. |
| Whether CI touches the network | Never | The fetch adapter's fake is the default; the real run is a documented manual step with `SOURCE_FETCH=http`. |

## Deviations from Plan

1. **The mutation probe for "a re-ingest rewrites the event" was replaced.** The planned
   probe applied a bug that the suite provably could not catch, because the ingest path is
   idempotent by two independent mechanisms (the content-hash short-circuit *and* the
   change classifier). It was replaced with two reachable probes — the JSON-LD `subEvent`
   expansion and the content hash's omission of the venue timezone — and a new test
   (`test_a_corrected_venue_timezone_re_resolves_its_events`) was added to reach the
   second one. *Reason:* a probe that passes the suite is a false assurance; the
   replacement proves two rules the original could not.

2. **The real feed set is two feeds, not three.** The plan's D1 named MMFA JSON-LD and
   ICS, and this was confirmed against the live site during implementation: MMFA's
   WordPress RSS feeds return HTTP 500. No reachable robots-clear RSS feed carries the
   `ev:` namespace the parser requires. *Reason:* the acceptance criteria ask for at least
   two of the three methods; the third is covered by the fixture set in CI.

3. **Two published lookups were added to the registries** (`find_source_by_url`,
   `find_venue`) rather than querying the models from the command. *Reason:* the
   `models-ingestion` import contract forbids the command from importing the models, and
   a lookup that bypasses the service layer would be a second, unaudited path.

4. **The unit tests for the two refusals delete rows instead of patching a queryset.**
   The first version monkeypatched `ContentType.objects.db_manager(PERSONAL).filter`,
   which the command never calls, so the tests asserted nothing. *Reason:* the patch
   target was wrong; deleting the row exercises the real path.

## Dependencies Added

None. No new package was added to `backend/pyproject.toml` or `frontend/package.json`.
The command uses only Django's own `ContentType`, `Group` and `Permission`; the suite uses
only pytest, pytest-django and the existing `FakeFetchAdapter`.

## How to Verify

1. **The seed command works and is idempotent**

   ```bash
   make db-init && make migrate
   make manage ARGS="seed_local_stack"
   make manage ARGS="seed_local_stack"     # again: the same output, no duplicates
   ```

   Expected: `Seeded 3 source(s), the editorial group and the operator account.` — twice,
   with the same three lines listing `fixture-jsonld`, `fixture-rss` and `fixture-ics`.

2. **The feed set and its ToS notes print**

   ```bash
   make manage ARGS="seed_local_stack --list"
   ```

   Expected: the operator line, the four venues, then per feed its URL, its `PT4H` cadence,
   its `approved` decision with an `https://` evidence URL and its note.

3. **The editorial group holds exactly twelve permissions and no delete**

   ```bash
   cd backend && uv run python manage.py shell -c "
   from django.contrib.auth.models import Group
   g = Group.objects.using('personal').get(name='editorial')
   print(sorted(g.permissions.values_list('codename', flat=True)))
   "
   ```

   Expected: twelve codenames — `add_source`, `change_source`, `view_source`, the same
   three for `venue` and `tosreview`, and `view_event`, `view_eventstatechange`,
   `view_ingestionauditentry`. No `delete_*` anywhere.

4. **The end-to-end proof passes**

   ```bash
   uv run --directory backend pytest tests/e2e tests/ingestion/test_seed_local_stack.py -q
   ```

   Expected: `37 passed`.

5. **The suite really proves the rules (mutation probes)**

   ```bash
   uv run --directory backend python tests/e2e/mutation_probe_e2e.py
   ```

   Expected: `All 9 probes were caught by the suite.` and exit code 0.

6. **The real feeds ingest (the manual, networked step)**

   ```bash
   SOURCE_FETCH=http make manage ARGS="seed_local_stack --real"
   make manage ARGS="ingest_source <source-id> --sync"    # for each source
   curl "http://127.0.0.1:8000/api/catalog/events?city=Montgomery"
   ```

   Expected: the JSON-LD source reports 9 new events and the ICS source 21 new with 9
   bound to the other source; `total: 9` for Montgomery in the API.

## Observed Counts (the real-feed run)

From the manual `SOURCE_FETCH=http` run against `mmfa.org` on 2026-10-28:

| Metric | Count |
|--------|-------|
| Sources registered | 2 (1 JSON-LD, 1 ICS) |
| Extracted records | 39 (9 from JSON-LD, 30 from ICS) |
| Events created | 30 new |
| Cross-source bindings | 9 (ICS instances bound to the JSON-LD events) |
| Events published | 30 (`published`) |
| Held `in_review` (tz review pending) | 0 |
| Rejected | 0 (`reject_reason` empty on all 39 records) |
| Ambiguous (unresolved) | 0 (all 39 `resolved`) |
| Event state changes | 0 (nothing changed on the re-read) |
| Timezone | 30 × `America/Chicago` |
| API result | `GET /api/catalog/events?city=Montgomery` → 200, `total: 9` |

The two sources agree on 9 events, which is the cross-source dedup rule working on real
data: the same event appears in the JSON-LD page and in the iCal feed, and the second
occurrence binds to the existing Event instead of creating a second one.

## Test Coverage

- Tests added: 37 (16 end-to-end + 21 seed-command unit tests), plus 9 mutation probes
- Coverage: 99.08% overall (gate 80%); `domain/` at 100% (gate 100%); the seed command at 96%
- Status: passing — 1691 backend tests, 0 failures, 0 skipped

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated (the README's "Local ingestion" section)
- [x] Developer notes captured

### The intent's success criteria, checked off

- [x] **Source Registry (FR-13):** sources are managed in Django admin; every write goes
  through a named `ingestion` command with an audit row; a `crawl` source without an
  approved ToS review is refused and the acquisition-hierarchy guard holds.
- [x] **Structured acquisition:** JSON-LD, RSS and ICS all ingest with no LLM call; the
  fetch goes through a port with a fake adapter, and source content is treated as
  untrusted.
- [x] **Scheduling:** sources ingest on their declared cadence; due sources are picked up
  from the single 60-second beat tick and the work runs as Celery jobs, never in a request.
- [x] **Dedup (FR-15):** Event Identity is computed in pure `domain/dedup.py`; re-ingesting
  the same feed is idempotent (proven by the second-tick test); recurring instances stay
  distinct `event_id`s sharing a `series_id` (proven by the JSON-LD series fixture).
- [x] **Timezone (FR-60, AD-6):** events are stored as UTC `timestamptz` with an IANA
  `start_time_tz` and a `tz_inference_confidence`; the tiers resolve as specified; each
  source carries a `tz_coverage`.
- [x] **Lifecycle:** a changed event bumps `event_version` and appends an
  `EVENT_STATE_CHANGE` with `propagated_at = NULL` in the same catalog transaction;
  nothing writes to `personal`.
- [x] **Freshness:** a source with no ingestion within 2× its cadence is flagged.
- [x] **Read API:** a public, session-free, read-only catalog endpoint exists and is
  exposed through the generated TS client.
- [x] **Proof:** recorded fixtures drive the tests for all three acquisition methods; two
  real, ToS-safe public feeds are registered and ingest successfully on the local stack;
  CI stays green, coverage gates included.

### The work item's acceptance criteria, checked off

- [x] The end-to-end test registers sources through commands, runs the tick with the jobs
  inline, reads `GET /api/catalog/events` and asserts the events, the tz fields and the
  dedup results, then re-runs the tick and asserts nothing changes.
- [x] Two real public feeds were picked at the plan checkpoint, each with a recorded
  ToS/robots note, covering JSON-LD and ICS.
- [x] The feeds are registered by an idempotent management command, not a data migration,
  so CI never touches the network.
- [x] The `editorial` group holds `add`/`change`/`view` on `Source`, `Venue` and
  `TosReview` and `view` on `Event`, `EventStateChange` and `IngestionAuditEntry`; the
  operator uses that group and not superuser; a test asserts the exact permission set.
- [x] On the local stack the real sources ingest via the worker and the events appear in
  the API.
- [x] The observed counts are recorded above.
- [x] Live network calls are never part of CI; the real-feed check is a documented manual
  step.
- [x] The README has a section on registering a source, triggering ingestion and reading
  the catalog API, and the fake-vs-HTTP fetch adapter settings are explained.
- [x] The full CI pipeline is green: lint, types, `import-linter`, tests, the coverage
  gates and the OpenAPI/client contract check.
- [x] The intent's success criteria are checked off above.

## Developer Notes

- **`manage.py migrate` only migrates `default`.** The catalog schema needs
  `make migrate`, which migrates both aliases as the owner role. A `seed_local_stack` on
  an unmigrated catalog fails with `The ingestion content types are missing` — that error
  is exactly the "run migrate first" case, not a bug.
- **`ingest_source.py` imports `ingest_item` by value.** `from apps.ingestion.services.ingest_item import
  ingest_item` binds the name at import time, so patching `ingest_item.ingest_item` has no
  effect on `ingest_source`. Patch `ingest_source.ingest_item` instead. This cost an
  hour of confused diagnostics during the probe work.
- **`ExtractedRecord` has no `notes` field** — it is `match_notes`. `resolution`,
  `reject_reason` and `content_hash` are the fields worth reading when counting outcomes.
- **The pytest database guard bites hard.** A test that touches `catalog` without
  `pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])` fails with
  `DatabaseOperationForbidden`, which looks like a product bug and is not.
- **The fake fetch adapter follows RFC 9110 conditional requests.** `calendar.ics` carries a
  `last_modified`, so its second fetch returns `304` — the ICS source's idempotency is
  proven by the conditional-request path, while JSON-LD and RSS prove theirs through the
  content-hash path. Two different mechanisms, both real.
- **The e2e conftest patches two seams, and both are needed.** The broker
  (`worker.tasks._enqueue`) and the outbox (`apps.ingestion.services.outbox._send`) are
  separate seams; patching only the broker leaves outbox writes escaping to Redis.
- **A refused command is a feature.** The seed command refuses an unreadable feed file, a
  non-JSON feed file, a missing content type and a missing permission. Each refusal has a
  test. When adding a new way for the command to fail, add the refusal and its test too.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-018*
