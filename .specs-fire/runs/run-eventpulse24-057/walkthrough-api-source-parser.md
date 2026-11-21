---
run: run-eventpulse24-057
work_item: api-source-parser
intent: city-picker-and-auto-collection
generated: 2026-11-20
mode: confirm
---

# Implementation Walkthrough: A parser for api-method sources

## Summary

`AcquisitionMethod` had seven values and `PARSERS` had four. `api` was one of the three
without a parser, so `parse()` returned `unsupported_method` and an `api` source could
never produce a single event — while FR-17 puts `api` at the **top** of the acquisition
hierarchy and the whole provider stack is meant to lead with it. The highest-priority tier
of this intent was inert.

It isn't now. `PARSERS["api"]` dispatches by host to a per-provider reader, and the first
reader is Ticketmaster Discovery v2.

The satisfying part is what the API tier gives back. Discovery returns
`dates.start.dateTime` — an exact UTC instant — **and** `dates.timezone`, an IANA zone.
That is FR-60 row A1: confidence 1.00 at `Tier.FULL`, with no registered venue and no
`source.city_tz`. It is the only acquisition method that resolves perfectly in a city we
have never seen, which is why FR-17 ranks it first and why item 2's city zone is a safety
net rather than the plan.

## Structure Overview

```text
backend/
├── apps/ingestion/
│   ├── parsers/
│   │   ├── __init__.py        PARSERS["api"] = parse_api
│   │   ├── providers.py       NEW — host → reader dispatch
│   │   └── ticketmaster.py    NEW — Discovery v2 reader
│   └── services/
│       ├── provider_keys.py   NEW — key added for the fetch, stripped on the way back
│       └── ingest_source.py   calls both
├── config/{env,settings}.py   TICKETMASTER_API_KEY
└── tests/fixtures/sources/ticketmaster-{events,empty,fault,errors}.json
```

## The two risks the work item asked me to verify

Both checked against the live Ticketmaster developer documentation before any code was
written, because both could have changed the plan.

**1. `city` is a real parameter.** The item suspected it might exist only in third-party
guides. It is in the official v2 Event Search table — `city`, array type, "Filter by city"
— alongside `countryCode`, `stateCode`, `marketId`, `dmaId`, `radius`/`unit` and
`localStartDateTime`. **`city-provider-templates` can template the city directly**; the
feared fallback of `countryCode` plus client-side filtering is not needed. One more thing
for that item: `latlong` is deprecated in favour of `geoPoint` (a geohash), so no template
should use it.

**2. The key is a query parameter, not a header.** So the fetch port needs no widening —
the risk the item flagged does not materialise. But it creates a different one, below.

## Architecture

### Two levels of dispatch, both exact

```text
parse("api", body, context)
   └─ providers.parse_api        host of context.source_url → a reader
         └─ ticketmaster.read    Discovery v2 → ParsedCandidates
```

**Exact host matching, never a suffix**, in both places it matters:

| Table | Decides | What a suffix match would cost |
|---|---|---|
| `providers.READERS` | whose parser reads this document | `app.ticketmaster.com.evil.test` gets read by a reader that trusts its shape |
| `provider_keys.PROVIDER_KEYS` | who receives **our API key** | the same host gets handed the key |

Both are literal dicts keyed on the full lowercase host, and both have tests for the
lookalikes.

### Where the API key lives — the checkpoint decision

**You chose: a key-less URL is stored, and the key is added for the one fetch.**

The problem the query-parameter answer creates is that a *working* source URL is a
credential, and a source URL normally goes three places that are all wrong for a secret:
`Source.url` is a column, `register_source` writes its fields into an audit row kept 24
months under AD-5, and `fetched_url` records where the last fetch landed — plus httpx logs
request URLs.

So:

```text
Source.url      https://app.ticketmaster.com/discovery/v2/events.json?city=New+York
                                 │
     authorized_url(url)  ───────┤  appends apikey=…, returns credential=True
                                 ▼
     port.fetch(url, credential=True)     ← the transport stops httpx writing the URL
                                 │
     strip_key(result.final_url) ─┤  removes it again, whoever put it there
                                 ▼
Source.fetched_url, SourceContext.source_url, logs — all key-free
```

`credential=True` is not new machinery. `SourceFetchPort` already documents that flag, and
its docstring explains why it exists: "httpx logs the request URL", and for a personal
calendar "that URL *is* the credential". A keyed Ticketmaster URL is the same shape of
fact, so it reuses the mechanism rather than inventing one.

`strip_key` runs on **every** fetch result, not only keyed ones. It is a no-op for other
hosts; the point is that no stored URL carries a key however it got there — including a
provider echoing the parameter back through its own redirect. There is a test for exactly
that.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/parsers/providers.py` | `parse_api`, exact-host dispatch to a reader |
| `backend/apps/ingestion/parsers/ticketmaster.py` | Discovery v2 → `ParsedCandidate`s |
| `backend/apps/ingestion/services/provider_keys.py` | `authorized_url` / `strip_key` |
| `backend/tests/fixtures/sources/ticketmaster-{events,empty,fault,errors}.json` | Recorded responses, trimmed, key-free |
| 3 test files | 74 tests |

### Modified

| File | Changes |
|------|---------|
| `backend/apps/ingestion/parsers/__init__.py` | `PARSERS["api"]`, plus a note on why `partnership`/`crawl` stay out |
| `backend/apps/ingestion/services/ingest_source.py` | `authorized_url` before the fetch, `strip_key` after |
| `backend/config/env.py`, `config/settings.py`, `.env.example` | `TICKETMASTER_API_KEY`, optional |
| 4 existing test files | See "Existing tests changed" |

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Where the key lives** | Stored key-less, injected at fetch, stripped on return | **Your checkpoint call.** The two rejected options are in the plan: baking it into `Source.url` puts a secret in a column and a 24-month audit row; deferring it would have let item 6 bake it into a URL template, which is the trap the work item's own notes warned about |
| **Module named `providers.py`, not `api.py`** | Renamed during review | `tests/architecture` discovers the AD-5 HTTP surface by filename shape, so `apps/**/api.py` is assumed to be a router that may not write directly. The parser was silently enrolled and two architecture tests failed. **The guard was right and the name was wrong** — teaching the discovery an exception would have carved a hole in a rule whose value is having none |
| **`offsale` is not `sold_out`** | `sold_out` stays False | `offsale` means "outside the public on-sale window", which covers an event that has not gone on sale **yet** as much as one that sold out, and presale inventory can exist during it. Reading it as sold out would put a false claim on every not-yet-on-sale event |
| **An event with no provider id is skipped** | Not given a derived id | The other parsers use `derived_id` for this, and here it would be wrong: a derived id hashes the item's own fields, so next run's edited title mints a different id and the event duplicates. AC 10 wants re-ingests to dedupe |
| **No `end` time** | Left `None` | Discovery's search response carries no reliable end. A fabricated one would create false conflicts, since `domain.conflict` compares intervals |
| **A provider error envelope is an error, not an empty page** | `provider_error` | A bad key or a rate limit must not reach a reader as "this city has no events". One is our problem; the other is a claim about the world |
| **`TICKETMASTER_API_KEY` is optional** | Empty default | `stripe_api_key` and `voyage_api_key` abort the boot when missing because every deployment bills and embeds. No deployment today has an API source; requiring it would break every environment to guard a feature none of them use. Refusing to *create* an API source without a key belongs in item 7 |

## Existing tests changed

Four, each because it encoded a truth this item deliberately changed — flagged because
editing an existing assertion is where a regression hides.

- Two in `tests/formats/ics/test_helpers.py`: `api` moved from "unsupported" to "structured".
  That move *is* the item.
- One in `tests/ingestion/test_ingest_source.py`: `ScriptedFetchPort` now records the
  `credential` flag, so the expected call dict gains `"credential": False`. The assertion
  got stronger — an ordinary source fetch is now explicitly *not* flagged as credential-bearing.
- One docstring in `tests/e2e/test_state_detection_window.py`, no assertion touched. It
  explained at length that the two halves of its scenario are proved separately because "no
  high-priority method has a parser yet". That is no longer true, and a stale justification
  reads as a current constraint. Rewritten to say what was true, what closed it, and that
  unifying the halves is now merely undone rather than impossible.

## Verification

```bash
make test-backend                                   # 7875 passed
make coverage-backend                               # 97.43% overall
uv run --directory backend lint-imports             # 21 kept, 0 broken
uv run --directory backend pytest tests/architecture -q   # 1091 passed
```

New modules at 100% coverage. Mutation check: removing `strip_key` fails exactly 1 test,
removing `authorized_url` fails exactly 1, and replacing exact-host dispatch with a suffix
match fails 2 lookalike-host cases.

## What This Unblocks, and What It Tells Item 6

`city-provider-templates` (item 6) now has somewhere to send an `api` source's bytes, and
three facts it should be built on:

1. **Use `city`** — it is official. Not `countryCode` plus filtering.
2. **Do not use `latlong`** — deprecated; `geoPoint` takes a geohash.
3. **Put no key in the template.** The URL it builds is stored on the `Source`, and the key
   is added at fetch time by `provider_keys`. A template that carries one would write a
   secret into a column and an audit row.

For `city-provisioning-service` (item 7): refusing to create an `api` source when
`TICKETMASTER_API_KEY` is empty belongs there — this layer fetches without the key and lets
the provider's 401 land in `last_error_code`, which is visible, rather than hiding the
misconfiguration.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
