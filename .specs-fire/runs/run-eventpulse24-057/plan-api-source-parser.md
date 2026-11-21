---
run: run-eventpulse24-057
work_item: api-source-parser
intent: city-picker-and-auto-collection
mode: confirm
checkpoint: plan-approval
status: approved
approved_at: 2026-11-20
---

# Implementation Plan: A parser for api-method sources

## The two risks the work item flagged, both now resolved

The item asked for both to be checked against live documentation during this run. Done,
before planning the rest:

**1. Ticketmaster's `city` parameter exists.** It is in the official v2 Event Search
parameter table — `city`, array type, "Filter by city" — alongside `countryCode`,
`stateCode`, `marketId`, `dmaId`, `radius`/`unit` and `localStartDateTime`. The fallback
the item feared (`countryCode` plus client-side filtering) is **not** needed, and
`city-provider-templates` can template the city directly. Worth noting for that item:
`latlong` is deprecated in favour of `geoPoint` (a geohash), so no template should use it.

**2. The key travels as a query parameter, not a header.** Authentication is `apikey=` on
the query string; the docs describe no header form. So the fetch port needs **no** change —
the widening the item warned about does not happen.

But the query-parameter answer creates a different problem, which is the one open call
below: a URL that carries the key is a credential, and `Source.url` is stored in the
database and written into `register_source`'s audit row.

## The open call, decided at the checkpoint: where the API key lives

**Option A was chosen.** The sections below are kept as written, because the options that
were rejected are part of the record.

AC 9 of this item says the key is "read from configuration, never committed, and never
reaches a log line". The parser never sees a key — parsers take bytes — so this AC is
really about the path around it, and it has to be decided here or `city-provider-templates`
will bake a key into a URL template.

**Recommendation: Option A.** It is what the AC asks for, and the mechanism it needs
already exists.

### Option A — key-less URL stored, key injected at fetch time (recommended)

`Source.url` holds `https://app.ticketmaster.com/discovery/v2/events.json?city=Dhaka&...`
with no key. `ingest_source` asks a `config`-level helper for the key for that host,
appends `apikey=` for the fetch only, and passes **`credential=True`**.

That flag already exists on `SourceFetchPort.fetch` and does exactly this job: the port's
own docstring explains it was added because "httpx logs the request URL" and for a calendar
"that URL *is* the credential". A Ticketmaster URL with a key is the same shape of fact.
Nothing new is invented; an existing mechanism is reused for the case it was built for.

`fetched_url` is stored **key-stripped**, and `SourceContext.source_url` is built from the
stripped URL, so the key never reaches the database, the audit row, the parser, or a log.

- Cost: `config/env.py` + `config/settings.py` (one key, the `voyage_api_key` pattern), a
  small host→key lookup, ~15 lines in `ingest_source`, and tests.
- Honest downside: this is more than "a parser", and it touches the ingest service.

### Option B — key baked into `Source.url`

Simplest, and wrong. The key lands in the `Source` row in plaintext, in
`register_source`'s audit `details.fields.url` (AD-5 keeps those for 24 months), and in
`fetched_url`. Rotating the key means rewriting every source row. Listed to be rejected
explicitly rather than drifted into.

### Option C — parser only; defer the key mechanism to `city-provisioning-service`

Keeps this item to its title. The risk is that item 6 writes URL templates with nowhere to
put a key and the easy answer becomes Option B — the exact trap the item's technical note
warns about ("surface it early rather than hiding a header mechanism inside the parser").
If this is chosen, the constraint must be written into the item-6 and item-7 work items
now, not left in a walkthrough.

## Approach

A dispatching parser, flat beside the existing ones — no `providers/` subpackage for a
single provider.

```text
parse("api", body, context)
   └─ parsers/api.py   parse_api: host of context.source_url → a reader
         └─ parsers/ticketmaster.py   read(payload, context) → ParseResult
```

**Dispatch is on an exact host, never a suffix.** `urlsplit(source_url).hostname`,
lowercased, matched against a literal dict. A suffix match would route
`app.ticketmaster.com.evil.test` to the Ticketmaster reader and let an attacker-chosen
document be read with a trusted shape.

**The reader is pure and total.** `json.loads` inside a `try`, every field access through
`.get`, and the module keeps the package's standing promise — bytes in, candidates out,
never an exception.

### Why the API tier leads (AC 7)

Ticketmaster returns `dates.start.dateTime` (an exact UTC instant) **and** `dates.timezone`
(an IANA zone). That is FR-60 row **A1**: an explicit zone, confidence 1.00, `Tier.FULL`,
with no venue registered and no `city_tz` needed. It is the only tier that resolves
perfectly cold, which is why FR-17 puts it first and why item 2's fallback is a safety net
rather than the plan.

The chain the reader hands over, in order:

| Provider fields | `start` | `start_zone` | `all_day` |
|---|---|---|---|
| `dates.start.dateTime` + `dates.timezone` | the instant, as written | the IANA zone | False |
| `localDate` + `localTime` + `dates.timezone` | naive wall-clock | the IANA zone | False |
| `localDate` only (`noSpecificTime`/`timeTBA`) | midnight, naive | the zone if given | True |
| none of these (`dateTBA`) | — | — | skipped `no_event_start` |

The parser does not resolve anything. It hands times over as written, which is the module
docstring's rule and the reason `start_raw` exists.

### Field mapping

| `ParsedCandidate` | Ticketmaster |
|---|---|
| `source_event_id` | `id`, through `item_id` — the provider's own id, so a re-ingest dedupes (AC 10) |
| `title` | `name` → `plain_text`; empty is skipped `no_title` |
| `canonical_url` | `url` → `http_url` |
| `venue_name` / `venue_city` / `venue_country` | `_embedded.venues[0]`: `name`, `city.name`, `country.countryCode` |
| `description` | `info`, else `pleaseNote` |
| `status` | `dates.status.code`: `canceled` → CANCELLED, `postponed`/`rescheduled` → POSTPONED, else SCHEDULED |
| `sold_out` | always `False` — `offsale` means "outside the on-sale window", which is not the same claim as sold out, and inventing it would mislabel events |
| `raw` | the as-written date fields and status code, for the payload |

`dates.status.code` is spelled **`canceled`**, one "l", in Discovery v2. Both spellings are
accepted anyway, since the adjacent Discovery Feed docs use two.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/parsers/providers.py` | `parse_api`, the host→reader dispatch. **Not** `api.py` — see the walkthrough; `tests/architecture` treats any `apps/**/api.py` as an AD-5 HTTP surface |
| `backend/apps/ingestion/parsers/ticketmaster.py` | The Discovery v2 reader |
| `backend/tests/ingestion/parsers/test_providers.py` | Dispatch, unknown host, malformed JSON, error envelopes, empty page |
| `backend/tests/ingestion/parsers/test_ticketmaster.py` | Field mapping, the four time shapes, status mapping, venue fields, caps |
| `backend/tests/fixtures/sources/ticketmaster-*.json` | Recorded, hand-trimmed responses. **No key in any fixture**, asserted by a test that greps every fixture |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/ingestion/parsers/__init__.py` | `PARSERS["api"] = parse_api` |
| `backend/config/env.py`, `backend/config/settings.py` | `ticketmaster_api_key`, the `voyage_api_key` pattern *(Option A)* |
| `backend/apps/ingestion/services/ingest_source.py` | Inject the key for the fetch, pass `credential=True`, store and parse the stripped URL *(Option A)* |

## Tests

| Test File | Coverage |
|-----------|----------|
| `test_api.py` | `PARSERS["api"]` registered; dispatch by host; an unrecognised host returns `error=...` and does not raise; `app.ticketmaster.com.evil.test` is **not** routed to the reader; malformed JSON, a `fault` envelope, an `errors` array and an empty page each return a clean `ParseResult`; `partnership` and `crawl` still return `unsupported_method` (AC 12) |
| `test_ticketmaster.py` | Every field in the mapping table; all four time shapes; both `canceled` spellings; an event with no venue; an event with no title skipped; `source_event_id` is the provider id; a 6,000-event page stops at `MAX_ITEMS`; no fixture contains anything matching an API key |
| `tests/ingestion/test_ingest_tz.py` or a new pipeline test | **AC 7 end to end**: an `api` source with a recorded response produces an Event at `Tier.FULL`, confidence 1.00, with no venue registered and no `city_tz` — the claim that the API tier resolves cold |
| *(Option A)* `tests/ingestion/test_ingest_source.py` | The key is appended for the fetch, `credential=True` is passed, and the stored `fetched_url` and the parser's `source_url` carry no key |

## Risks

| Risk | Mitigation |
|---|---|
| Recorded fixtures drift from the live API | They are recorded, trimmed and committed, and the reader is total — an unexpected shape yields fewer candidates, never an exception. The pipeline counts `skipped:*` reasons, so drift shows up as a count rather than a crash |
| A key leaks into a fixture | A test scans every fixture file for anything key-shaped. Fixtures are hand-trimmed from the public documentation examples, which carry no key |
| Suffix-matching the host | Dispatch is an exact-match dict, with a test for the lookalike host |

---
*Plan approved at the checkpoint (confirm mode). Execution follows.*
