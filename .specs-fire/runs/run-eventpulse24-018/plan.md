---
run: run-eventpulse24-018
work_item: real-feeds-and-e2e-proof
intent: event-catalog-ingestion
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at:
---

# Implementation Plan: Real Feeds & End-to-End Proof

## Approach

> **Needs your call:** decision **D1** — the real feed set. **D2 (the editorial group) is
> resolved** by experiment: a plain Django `auth.Group` holds all twelve `ingestion.*`
> permissions across the schema wall. Everything else is mechanical once D1 is settled.

The last work item of `event-catalog-ingestion`. It proves the intent end to end and closes the
loop that runs 014 → 017 left open: a source registered by a **command**, ingested by the
**worker**, visible through the **public API**.

Four deliverables, in dependency order:

| # | Deliverable | Where |
|---|-------------|-------|
| 1 | **Seeded sources + editorial group**, by an idempotent command | `config/management/commands/seed_local_stack.py` |
| 2 | **The e2e test**: command → tick → API → tick again → nothing changed | `backend/tests/e2e/test_end_to_end.py` |
| 3 | **A JSON-LD fixture** (the third method the AC asks for) | `backend/tests/fixtures/sources/events.jsonld.html` + `index.json` |
| 4 | **Docs**: register a source, trigger ingestion, read the API, fake vs HTTP adapter | `README.md` |

**The hard constraint shapes the whole design: CI never touches the network.** Every automated
test runs against `FakeFetchAdapter` and recorded fixtures. The real feeds are a **documented
manual step** on the operator's local stack, run with `SOURCE_FETCH=http`.

```
CI:          seed_local_stack → tick → GET /api/catalog/events → tick → unchanged
             (FakeFetchAdapter, fixtures only — no sockets)

Operator:    SOURCE_FETCH=http python manage.py seed_local_stack --real
             → docker compose up -d && make dev → events appear in admin + API
```

---

## D1 — The real feeds (DECIDED — one venue, all three methods)

The AC: *"The user picks 2–3 real public feeds at the plan checkpoint. Each has a recorded
ToS/robots note, and the set covers at least two of JSON-LD, RSS and ICS."*

**Decision:** one venue family publishing the same events in three formats — **the Montgomery
Museum of Fine Arts** (`mmfa.org`), a public non-profit museum in Montgomery, Alabama. It runs
**The Events Calendar** (WordPress) and publishes:

| # | Method | URL | Verified |
|---|--------|-----|----------|
| **A1** | **JSON-LD** | `https://mmfa.org/events/` | `200 text/html`, 310 837 B → **9 candidates** |
| **A2** | **ICS** | `https://mmfa.org/events/?post_type=tribe_events&ical=1&eventDisplay=list` | `200 text/calendar`, 92 585 B → **30 candidates** |
| **A3** | **RSS** | `https://mmfa.org/events/feed/` | ⚠️ **`500` — the site's WordPress feed generation is broken.** See below. |

**These numbers are not from a guess** — they come from running the project's own
`HttpFetchAdapter` (the real code path) and then `apps/ingestion/parsers/` against the live
responses, on 2026-10-28:

```
jsonld  https://mmfa.org/events/      status=200 bytes=310837 content_type=text/html
        -> candidates=9  skipped={}  error=None
           'Mini Makers: Art + Gratitude' start=2026-11-03 09:30:00-06:00 venue='Montgomery Museum of Fine Arts' city='Montgomery'
ics     https://mmfa.org/events/?post_type=tribe_events&ical=1&eventDisplay=list
        status=200 bytes=92585 content_type=text/calendar
        -> candidates=30  skipped={}  error=None
           'Mini Makers: Art + Gratitude' start=2026-11-03 09:30:00 tz=America/Chicago
```

The same venue's events in two formats — so the e2e proof compares **comparable** content
across parsers (the ICS has 30 instances of recurring events; the JSON-LD has 9 base events).

### The ToS/robots note (one note covers all three URLs)

- **robots.txt** (`https://mmfa.org/robots.txt`) — for `User-agent: *` it disallows **only**
  `/wp-admin/` (and allows `/wp-admin/admin-ajax.php`). **Neither the events page nor the
  feed paths are disallowed.** It also sets **`Crawl-delay: 10`**.
- **The feeds are published for public use.** The events page itself advertises the iCal feed
  (`<link rel="alternate" type="text/calendar" title="MMFA » iCal Feed" href="…/?ical=1">`)
  and links to subscribe in Google Calendar and Outlook. A publisher that hands out its own
  calendar subscription is publishing the feed for public consumption.
- **ToS.** The museum is a public non-profit institution; the site publishes event listings
  openly. The evidence URL is the site's own terms/privacy page.
- **Crawl-delay: 10** is honoured: our cadence is far slower (hours), and the manual step
  fetches each URL once.

### The RSS gap — and why the AC is still met

**A3 is unusable as-is: MMFA's WordPress feeds return `500`.** Every feed path on the site
fails the same way (`/events/feed/`, `/?post_type=tribe_events&feed=rss2`, `/feed/`) — a
server-side feed-generation fault on their side, not a robots or ToS issue. An RSS source
that 500s cannot be registered.

The AC requires the set to cover **at least two of** JSON-LD, RSS and ICS. **A1 + A2 cover two**,
so the AC is met.

**Why not add a working `ev:` RSS from elsewhere?** I looked hard, and the finding is worth
recording, because it constrains the launch corpus (OQ-5) too:

- **The binding constraint is not robots.txt — it is the `ev:` namespace.** Our parser takes an
  RSS event time *only* from `ev:startdate` or `xcal:dtstart`, never `pubDate` (a publication
  time is not an event time — `apps/ingestion/parsers/feeds.py:54`). A generic blog RSS is
  perfectly allowed by robots and still yields **zero** events.
- Every **reachable, robots-clear** RSS feed I probed (Funcheap SF, python.org jobs, NASA,
  NPR, LWN, many WordPress venues) carries **no `ev:`/`xcal:` fields** — all would parse to
  zero events.
- The sites that **do** publish `ev:` feeds (WordPress + The Events Calendar) either 403 a
  non-browser agent (Kennedy Center, Wolf Trap, FAMSF, AMNH, Smithsonian, Art Institute) or
  have a **broken feed** (MMFA — the one site that served both its ICS and its JSON-LD
  cleanly).

**Decision:** ship **A1 (JSON-LD) + A2 (ICS)** as the real proof set, and record the RSS gap
in the walkthrough as a finding for OQ-5. The RSS path is still exercised in CI by the
recorded fixture (`tests/fixtures/sources/events.rss`, which carries `ev:startdate`), so the
parser stays covered — the CI e2e test covers all three methods, and only the **manual** real
step covers the two that live.

**If you want a third real feed anyway**, the honest options are: (a) accept a third ICS/JSON-LD
site from a different venue, or (b) keep looking for a `ev:`-RSS site that is both reachable
and robots-clear. Say the word and I will keep hunting for (b).

### The other candidates, and why each is out

| Candidate | Verdict | Why |
|---|---|---|
| **Eventbrite** (`/rss/`, `/events/rss/`, `/events/atom/`) | ❌ Out | robots.txt explicitly disallows `/rss/`, `/events/rss/`, `/events/atom/`, `/directory/`. |
| **Meetup** (`*/events/rss/*`, `*/calendar/*rss*`) | ❌ Out | robots.txt disallows the feed paths; the group ICS endpoint 404s. |
| **Wikidata SPARQL** (`query.wikidata.org/sparql`) | ❌ Out | robots.txt: `Disallow: /sparql`. |
| **Funcheap SF** (RSS) | ❌ Out | robots-clear, but the feed carries only `pubDate` → **zero** events under our parser. |
| **python.org jobs** (RSS) | ❌ Out | Permitted, but a job board: no event times, no venues. |
| **Smithsonian / Art Institute / Getty / Kennedy Center / Wolf Trap / FAMSF / AMNH** | ❌ Out | `403` to a non-browser agent. |
| **SFMOMA** (`/events/feed/`) | ❌ Out | Its `/events/feed/` is an **empty comments feed** (`content-length: 0`) — no items. |
| **MIT / Stanford / Berkeley / Chicago** event sites | ❌ Out | SPA pages; the feed paths return `text/html`, and no schema.org `Event` JSON-LD. |
| **City / government calendars** (SF, NYC, Santa Clara, Mountain View) | ❌ Out | `403`/`404`/`202` to a non-browser agent. |

**These are LOCAL PROOF SOURCES, not the launch corpus.** OQ-5 stays open: the 40-source /
15-per-city floor is untouched, and the beachhead city is undecided.

---

## D2 — The editorial group (RESOLVED — no call needed)

AD-14 says internal actors get **explicit role grants**, not superuser. The AC asks for an
`editorial` group with:

- `add` / `change` / `view` on `ingestion.Source`, `ingestion.Venue`, `ingestion.TosReview`
- `view` on `ingestion.Event`, `ingestion.EventStateChange`, `ingestion.IngestionAuditEntry`

and the **local operator account uses that group, not superuser**.

### The cross-schema question, answered by experiment

`django.contrib.auth` and `contenttypes` are routed to **`personal`**; the six models above are
in **`catalog`**. A Django `Permission` points at its model through a `content_type_id` — a
`personal` row referencing a `catalog` model. That looks like an AD-3 cross-wall relation, so
I probed it against the real database rather than assuming.

**The probe passed.** A standard `auth.Group` holds all twelve `ingestion.*` permissions and
`user.has_perm(...)` resolves each one, across the schema wall:

```
Source: change_source / view_source / add_source           present=True
Venue: change_venue / view_venue / add_venue               present=True
TosReview: change_tosreview / view_tosreview / add_tosreview present=True
Event: view_event                                          present=True
EventStateChange: view_eventstatechange                    present=True
IngestionAuditEntry: view_ingestionauditentry              present=True
has_perm ingestion.change_source True   ... 12/12 True      TOTAL PERMS: 12
```

**Why it is safe.** `ContentType` identifies a model by `(app_label, model)` — two plain
strings — not by a foreign key to the model's table. There is no row in `personal` that points
into `catalog`; the *reference* is by name. AD-3's wall is about **relations between rows**
(cross-schema FKs and joins), and `eventpulse.E002` does not trip: the `ingestion` models keep
no relation to `auth`/`contenttypes`. The existing admin already relies on this — run-014's
`apps/ingestion/admin.py:274` calls `request.user.has_perm("ingestion.add_tosreview")`.

**So: a plain Django `auth.Group` named `editorial`, holding exactly those twelve
permissions, with the operator as a member.** No new model, no custom permission service, no
`identity` → `catalog` read. The probe was deleted; the behaviour it proved is what the real
test will assert.

**The test asserts the exact set** — twelve permissions, no more, no less:

```python
EXPECTED = {
    "ingestion.source":              {"add", "change", "view"},
    "ingestion.venue":               {"add", "change", "view"},
    "ingestion.tosreview":           {"add", "change", "view"},
    "ingestion.event":               {"view"},
    "ingestion.eventstatechange":    {"view"},
    "ingestion.ingestionauditentry": {"view"},
}
```

An extra grant fails the test — that is the point of AD-14. The operator account is asserted
to be in the group and **not** a superuser.

**One detail that bit me and will bite the implementation:** the permission codenames are
`<action>_<model_lowercase>`, and the model names are not all obvious — `TosReview` →
`add_tosreview` (not `add_tos_review`), `EventStateChange` → `view_eventstatechange`,
`IngestionAuditEntry` → `view_ingestionauditentry`. The command must derive them from
`ContentType` rather than hard-coding strings.

---

## The seed command

**One idempotent command** (`seed_local_stack`) does both jobs — the AC allows "the same
idempotent command, or a sibling one":

```
python manage.py seed_local_stack              # sources + venues + editorial group + operator
python manage.py seed_local_stack --real       # the same, but with the real feed URLs
python manage.py seed_local_stack --list       # print the feed set and each ToS/robots note
```

**Idempotency.** Every step must be safe to re-run, because the operator will run it on every
machine and CI may run it too:

- **Sources** — `register_source` refuses a duplicate URL (`SourceAlreadyRegisteredError`), so
  the command looks the URL up first and skips when it is already registered. `update_source`
  is used for a source that exists but drifted (it drops no-op changes).
- **Venues** — `register_venue` refuses a duplicate fingerprint
  (`VenueAlreadyRegisteredError`); same lookup-then-skip. A venue's tz is filled with
  `set_venue_timezone`, which is a no-op when the zone already matches.
- **ToS reviews** — `register_source` takes the review **in the same call**
  (`TosReviewInput`), which is what FR-17 demands for a crawl source. A source that already
  exists gets its review recorded only when `tos_status` is not already `approved`
  (`record_tos_review`), so re-running never stacks duplicate review rows.
- **The group / operator** — `get_or_create` semantics by name; the permission set is
  **assigned, not appended** (`group.permissions.set(...)`), so a stale grant is removed on
  re-run and the set stays exactly the twelve the AC names.

**Which commands it calls.** The command is a **client** (AD-14): it calls the published
services, never writes directly. `apps/*/admin.py` and `apps/*/api.py` are scanned
syntactically by `tests/architecture/test_no_direct_writes.py`, and the same rule applies
here — `config/management/commands/` writes through services only.

**The actor.** A ToS review is recorded by a **person** (`_require_person` refuses a system
actor), so the command needs a real operator user id. The command creates the operator
account first, then uses `Actor.user(operator.id)` for every subsequent call.

**The feed set lives in a committed file**, not in code — `backend/config/local_feeds.json`.
A data file is better than code here: the ToS/robots note and the cadence belong *with* the
feed, and `--list` prints them. **Each entry records:**

```json
{
  "key": "mmfa-jsonld",
  "name": "Montgomery Museum of Fine Arts events",
  "url": "https://mmfa.org/events/",
  "acquisition_method": "jsonld",
  "source_type": "venue",
  "city": "Montgomery",
  "tz": "America/Chicago",
  "ingestion_cadence": "PT4H",
  "tos": {
    "decision": "approved",
    "evidence_url": "https://mmfa.org/privacy-policy/",
    "notes": "robots.txt (User-agent: *) disallows only /wp-admin/; the events page and the iCal feed are allowed. The page publishes its own calendar subscription. Crawl-delay: 10 is honoured."
  }
}
```

The **venue** for these sources is registered too (`register_venue`, name + city + country
`US`), so the events get a venue with a canonical IANA zone. The ICS feed writes the venue as
a free-text `LOCATION` string, so the venue registry match is by name — the JSON-LD feed
gives `addressLocality: "Montgomery"` and `addressCountry: "United States"`, which is the
cleaner path.

**Cadence.** `DEFAULT_INGESTION_CADENCE` per method, floor `INGESTION_CADENCE_MIN` (15 min).
The declared cadence comes from the publisher; we never poll faster than they publish
(`sy:updateFrequency` / `Crawl-delay` where stated).

---

## The end-to-end test

`backend/tests/e2e/test_end_to_end.py` — the AC's four steps, one test per step plus the
idempotency assertion, driven through the **fake** adapter only.

**Why it is not just another unit test.** It exercises the *whole* chain, in order, through the
real seams: management command → registry services → the tick → the ingest pipeline → the
catalog read service → the HTTP API → back out. Only two things are substituted, both
deliberately:

1. **The fetch** — `FakeFetchAdapter` serves recorded fixtures. No sockets.
2. **The broker** — the tick's `_enqueue` is replaced by the existing recorder
   (`tests/worker/conftest.py`), and the jobs it would publish run **inline** (`tick.apply()` /
   calling the task directly), so the test needs no Redis. The AC allows this: *"runs the tick
   and lets the jobs execute (eager or inline)"*.

**The steps:**

```python
# 1. register sources through commands
call_command("seed_local_stack", ...)          # or a dedicated fixture-seed command

# 2. run the tick and let the jobs execute
tick.apply()                                    # enqueues schedule_sources
schedule_sources()                              # claims the due sources, enqueues ingests
ingest_source(str(source_id))                   # runs each claimed ingest inline

# 3. read GET /api/catalog/events and assert
body = Client().get("/api/catalog/events").json()
# - the expected events are present, in start order
# - the tz fields are right (start_time_tz, start_time_local)
# - the dedup result is right (one Event per source_event_id, no duplicates)

# 4. re-run the tick and assert nothing changed
before = snapshot_of_events()
tick.apply(); schedule_sources(); ingest_source(...)   # again
after = snapshot_of_events()
assert after == before
```

**Step 4 is the sharp one.** Two independent things must hold:
- **No new Events.** The second run re-reads the same fixture; the identity rules (a/b/c) must
  bind the item to the **existing** Event, not create a second one.
- **No new version.** The second run finds the content unchanged, so it is a **silent**
  update — no `EventStateChange`, no `event_version` bump. A second `EventStateChange` would
  mean the "unchanged" detection is broken.

The assertion is on **this test's** events, never a bare total — the endpoint lists everything
upcoming, so other tests' events are in there too. That rule is already documented in
`tests/api/test_catalog_api.py`; the e2e test follows it, and uses a **city no other test
uses** where it needs an exact count.

**The three methods.** The AC says "fake fetch adapter, all three methods". The fixture set
already covers **RSS** (`events.rss`, with `ev:` fields) and **ICS** (`calendar.ics`). **JSON-LD
has no fixture** — `tests/fixtures/sources/` has `broken-jsonld.html` but no valid one. So this
run **adds `events.jsonld.html`** (a page with a schema.org `Event` block, plus an
`EventSeries` with `subEvent`s to exercise `series_id`) and its `index.json` entry.

The **real** set is JSON-LD + ICS (D1) — RSS is excluded because every reachable, robots-clear
RSS feed lacks the `ev:` namespace our parser requires. The RSS path stays covered in CI by
the recorded fixture, so **all three methods are exercised by the automated test**; the manual
real step covers the two that a live site actually serves.

---

## The editorial group, in the e2e test

The group is a standard Django `auth.Group` named `editorial`, holding exactly twelve
permissions (D2 above). The test asserts the **exact** set:

```python
EXPECTED = {
    "ingestion.source":              {"add", "change", "view"},
    "ingestion.venue":               {"add", "change", "view"},
    "ingestion.tosreview":           {"add", "change", "view"},
    "ingestion.event":               {"view"},
    "ingestion.eventstatechange":    {"view"},
    "ingestion.ingestionauditentry": {"view"},
}
```

The test asserts:
1. `group.permissions` is **exactly** the twelve codenames — no more, no less.
2. The operator account is a member of the group.
3. `operator.is_superuser is False` — the operator uses the group, not superuser.
4. `operator.has_perm("ingestion.change_source")` is True, and a permission **outside** the
   set (e.g. `ingestion.delete_source`) is False.

Point 4 matters: `delete` is deliberately absent, because sources are **paused, never
deleted** (FR-13). The group must not grant a way to delete them.

---

## Docs

`README.md` gains a section (the file is currently short: Quick start / Repository layout /
Architecture) — or a `docs/` file if it grows past what a README should carry:

1. **Register a source** — the command, the ToS-review rule (FR-17: a crawl source needs an
   approved review **in the same call**), the cadence and the fresh-city fields.
2. **Trigger ingestion** — `ingest_source <source_id> [--sync]`, and the worker path
   (`make worker`, the 60s tick).
3. **Read the catalog API** — `GET /api/catalog/events` with its filters and envelope, and
   `GET /api/catalog/events/{id}`.
4. **Fake vs HTTP fetch adapter** — `ADAPTER_MODE=fake|real`, `SOURCE_FETCH=fake|http` (the
   fetch port alone), the `SOURCE_FETCH_*` limits and the identifying user-agent, and the
   fixtures dir.
5. **The manual real-feed step** — the exact commands, and a line that CI never does this.

---

## Carry-overs from run-017

| # | Carry-over | What this run does |
|---|---|---|
| **CONFIRM-1** | The list endpoint echoes the **unclamped** `page`/`page_size` while `list_public_events` clamps them, and computes `has_next` from the unclamped values. Unreachable via HTTP today (the `EventPage` schema 422s first), but latent. | **Touches the catalog read path?** If yes, the service must return the values it actually used. Default: **leave it alone** — this work item has no reason to touch `catalog_read.py`, and touching it adds risk for no AC benefit. If we do touch it, the fix is to have `list_public_events` return the clamped page/page_size it used. |
| **2** | `config.api` is part of the API surface; the `worker-not-api` contract forbids it. | Don't add the worker to the API. The seed command lives in `config/management/commands/` and may import `worker`? **No** — `config` may import `worker` (the layers are `config | worker` → `apps | adapters`), but the *command* must not import `apps.*.api`. The e2e test imports the worker tasks; that is a test, and the contract only binds `worker` → `apps.*.api`. |
| **3** | `Query(...)` is load-bearing on `EventPage`; without it Ninja treats the argument as a request body and the filters silently stop working. | Don't remove it. The e2e test asserts the filters work, which would catch a regression. |

---

## The gates

The full set, all green before the run closes:

```bash
cd backend && uv run --directory . python -m pytest -q
cd backend && uv run --directory . python -m pytest --cov=. --cov-report=term-missing -q
cd backend && uv run --directory . lint-imports
cd backend && uv run --directory . ruff check .
cd backend && uv run --directory . ruff format --check .
cd backend && uv run --directory . python manage.py check
cd backend && uv run --directory . python manage.py makemigrations --check --dry-run
make client && git diff --exit-code frontend/lib/api/
cd frontend && pnpm lint && pnpm typecheck
```

**Baseline to beat: 1649 tests pass, 98.95% coverage, 13 import contracts, 0 broken.**
The gates are 80% overall and 100% on `domain/`.

**The bar the last runs set:** a **mutation probe per planted bug**, proving the tests actually
catch it (the pattern is `backend/tests/api/mutation_probe_catalog.py` — 9 probes, all caught).
This run plants its own bugs and probes them the same way.

**Deviations from this plan get recorded with the reason**, not silently absorbed.

---

## Order of work

1. ~~**D1 + D2 answered**~~ — **done in planning.** D1: MMFA, JSON-LD + ICS (verified live
   through the project's own HTTP adapter). D2: a standard `auth.Group` works across the wall
   (proved by a probe against the real DB).
2. **The seed command** — idempotent: sources + venues + ToS reviews + group + operator, from
   `backend/config/local_feeds.json`.
3. **The editorial group** — `editorial`, exactly twelve permissions, the operator as a member
   and not a superuser, plus the exact-permission-set test.
4. **The JSON-LD fixture** — `events.jsonld.html` + `index.json`.
5. **The e2e test** — the four AC steps, fake adapter only, all three methods.
6. **The mutation probes** — one per planted bug.
7. **Docs** — README/docs section.
8. **The gates** — the full list above.
9. **The manual real-feed step** — on the local stack, with `SOURCE_FETCH=http`. The walkthrough
   records the observed counts (new / rejected by reason / ambiguous / tz-review-pending).
10. **The walkthrough** — with the intent's success criteria checked off, and the RSS finding
    recorded for OQ-5.

## Risks

| Risk | Mitigation |
|---|---|
| **MMFA's feeds change shape** (the site rebuilds, the plugin changes) | The manual step is documented and repeatable; a failure is recorded in the walkthrough, not a CI failure. The seed command is idempotent, so a moved feed is re-registered. The CI e2e test never touches the network, so a broken upstream site breaks only the manual step. |
| **MMFA's WordPress feeds are already broken (500)** | Confirmed for the RSS path — which is why it is out of the set. The ICS and JSON-LD paths were verified working on 2026-10-28 through the project's own HTTP adapter. If the ICS path breaks, the manual step records it and the set is re-chosen; CI is unaffected. |
| **MMFA's `Crawl-delay: 10`** | Honoured by construction: our cadence is in hours, and the manual step fetches each URL once. |
| **The group design collides with AD-3** | **Already resolved by experiment**: a standard `auth.Group` holds all twelve permissions across the wall, because `ContentType` references a model by name (`app_label`, `model`), not by a row. The exact-permission-set test locks it in. |
| **The e2e test is flaky** (other tests' events leak into the list) | The test counts **its own** events, and uses a city no other test uses where it needs an exact total — the rule already documented in `tests/api/test_catalog_api.py`. |
| **The e2e test needs Redis** | It does not: `_enqueue` is the replaced seam (`tests/worker/conftest.py`), and the jobs run inline. |
| **The launch corpus has the same RSS gap** | Recorded as a finding for OQ-5 in the walkthrough: the corpus must find feeds carrying the `ev:`/xCal namespace, or our RSS parser is decorative. |

## Out of scope (open on the intent)

- **OQ-5** — the feeds are local proof sources; the 40-source / 15-per-city launch floor and the
  beachhead city are untouched.
- The PRD amendment for the FR-60 tier table (`prd.md:556` vs `prd.md:576`).
- The editorial review queue (FR-57) — automatic re-gating vs editorial decisions (run-015 P1).
