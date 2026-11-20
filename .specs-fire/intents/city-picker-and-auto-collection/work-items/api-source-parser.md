---
id: api-source-parser
title: A parser for api-method sources
intent: city-picker-and-auto-collection
complexity: medium
mode: confirm
status: pending
depends_on: []
created: 2026-11-20
---

# Work Item: A parser for api-method sources

## Description

`parsers/__init__.py` registers four parsers — `jsonld`, `rss`, `ics`, `email_ics` — but
`AcquisitionMethod` has seven values. **`api`, `partnership` and `crawl` have no parser**,
so `parse()` returns `unsupported_method` for them and an `api` source can never produce a
single event.

This was missed when `city-provider-templates` was first written. FR-17 puts `api` at the
top of the acquisition hierarchy, and the provider stack is meant to lead with it, so
without this item the highest-priority tier of the whole intent is inert.

A provider API returns its own JSON shape, not schema.org, so this is a dispatching parser:
one entry in `PARSERS` for `api`, routing by the source's host to a per-provider reader.

## Acceptance Criteria

- [ ] `PARSERS["api"]` exists and dispatches by host derived from `SourceContext.source_url`.
- [ ] A per-provider reader for Ticketmaster Discovery turns its response into `ParsedCandidate`s.
- [ ] An unrecognised host returns `ParseResult(error=...)` rather than raising — the module's standing promise is "bytes in, candidates out, never an exception".
- [ ] Malformed JSON, an empty result set, and an error envelope from the provider each return a clean `ParseResult`, not a crash — asserted by tests with recorded fixtures.
- [ ] The parser stays **pure**: no database, no network, no LLM, consistent with the module docstring.
- [ ] Times are handed over **as written**, with `start_zone` populated where the provider supplies a zone. The parser does not resolve timezones — `domain.timezones` does.
- [ ] Ticketmaster's exact-instant + zone response resolves at the FULL tier with no venue required — asserted end-to-end, since this is the whole reason the API tier leads.
- [ ] `venue_city` and `venue_country` are populated where the provider supplies them, so `_venue_for` and `EventFit` get the right city.
- [ ] The provider API key is read from configuration, never committed, and never reaches a log line.
- [ ] `source_event_id` uses the provider's own event id so re-ingests dedupe rather than duplicate.
- [ ] No fixture used in tests contains a live API key.
- [ ] `partnership` and `crawl` remain unregistered and still return `unsupported_method` — this item does not widen the pipeline beyond `api`.

## Technical Notes

`SourceContext` carries only `source_id` and `source_url`. The host in `source_url` is
enough to pick the reader, so **no schema change is needed** — resist adding a provider
field to the context for this.

Keep the per-provider readers in their own module(s) under `parsers/`, so adding a second
API provider later is a new reader plus a dispatch entry, not a rewrite.

The fetch itself is unchanged: `adapters/crawl/http.py` already fetches arbitrary URLs and
the API tier is just another URL. Check whether the API key needs to travel as a header
rather than a query parameter — if so, that is a fetch-port concern and may widen this
item; surface it early rather than hiding a header mechanism inside the parser.

Verify Ticketmaster's `city` parameter against live documentation during this run. It
appears in third-party guides but **not** in the official v2 parameter table. If it is
absent, the fallback is `countryCode` plus filtering, and `city-provider-templates` must be
told.

## Dependencies

(none)
