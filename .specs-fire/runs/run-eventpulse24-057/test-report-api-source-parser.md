---
run: run-eventpulse24-057
work_item: api-source-parser
intent: city-picker-and-auto-collection
generated: 2026-11-20
status: passed
---

# Test Report: A parser for api-method sources

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Parser unit — dispatch (new) | 27 | 0 | 0 | 100% |
| Parser unit — Ticketmaster (new) | 32 | 0 | 0 | 100% |
| Pipeline / key handling (new) | 15 | 0 | 0 | 100% |
| Backend suite (full) | 7875 | 0 | 0 | 97.43% |
| **Total** | **7875** | **0** | **0** | **97.43%** |

74 tests in three new files. The suite grew by 120 because registering `api` in `PARSERS`
also widens existing parametrized tests that enumerate it — measured at +19 collected
tests by toggling the registration, with the rest in the new files and their parametrize
expansions.

New modules at **100%** statement coverage (`providers.py`, `ticketmaster.py`,
`provider_keys.py`). `domain/` still 100%. `lint-imports`: 21 contracts kept, 0 broken.

## Acceptance Criteria Validation

- ✅ **`PARSERS["api"]` exists and dispatches by host from `SourceContext.source_url`** — `parse_api` in `parsers/providers.py`. `test_api_has_a_parser_at_last` pins the registration; `TestDispatch` pins the routing.
- ✅ **A per-provider reader for Ticketmaster Discovery turns responses into `ParsedCandidate`s** — `parsers/ticketmaster.py`, checked field by field against a recorded fixture rather than a hand-built dict, so a change in the provider's shape surfaces here.
- ✅ **An unrecognised host returns `ParseResult(error=...)` rather than raising** — `unknown_api_provider`. Four lookalike hosts are pinned, including `app.ticketmaster.com.evil.test` and bare `ticketmaster.com`, because dispatch is an **exact-match** dict: a suffix match would hand an attacker-chosen document to a reader that trusts its shape.
- ✅ **Malformed JSON, an empty result set and a provider error envelope each return a clean `ParseResult`** — five malformed inputs (empty, prose, truncated, invalid UTF-8, JSON that is not an object); `fault` and `errors` envelopes from recorded fixtures → `provider_error`; an empty page → **no error and no candidates**, because "the provider said no" and "this city has no events" are different claims and conflating them would make a rate limit look like an empty city.
- ✅ **The parser stays pure** — `json.loads` and dict access only. No Django import, no database, no network, no LLM. `TestItIsTotal` feeds six malformed shapes and asserts candidates drop rather than exceptions rise.
- ✅ **Times are handed over as written, with `start_zone` where the provider supplies a zone** — all four shapes pinned: exact instant + zone; local date + time, naive, with zone; date only → midnight + `all_day`; nothing → skipped `no_event_start` rather than guessed. `start_raw` carries the provider's own string in every case.
- ✅ **Ticketmaster's exact-instant + zone response resolves at FULL with no venue — asserted end to end** — `test_an_api_event_publishes_at_full_confidence_with_nothing_else_known`: confidence `1.00`, published, `tz_review_pending` False, zone `America/New_York`, with no `Venue` row and `city_tz` empty. `test_every_event_on_the_page_resolves_at_the_full_tier` strengthens it — **all four** events on the page reach 1.00, not one lucky row.
- ✅ **`venue_city` and `venue_country` are populated where supplied** — from `_embedded.venues[0]`; country upper-cased to two letters; an event with no venue block is still a candidate with empty strings.
- ✅ **The API key is read from configuration, never committed, never reaches a log line** — `TICKETMASTER_API_KEY` via `config/env.py` → `config/settings.py` (the `voyage_api_key` pattern). Added to the URL for one fetch by `provider_keys.authorized_url`, which also returns `credential=True` so the transport stops the HTTP library writing that URL. `Source.url` and `fetched_url` are asserted key-free, including when the provider echoes the parameter back in its own final URL.
- ✅ **`source_event_id` uses the provider's own event id** — `item_id(event["id"])`. An event with no id is skipped `no_source_event_id` rather than given a derived one: without the provider's id it cannot be followed between runs, so a re-ingest would duplicate it.
- ✅ **No fixture contains a live API key** — `TestNoFixtureCarriesAKey` scans every `ticketmaster-*.json` for `apikey=` or any 24+ character alphanumeric run, and `test_the_scan_would_catch_one` proves the scan is not vacuous.
- ✅ **`partnership` and `crawl` remain unregistered** — `test_partnership_and_crawl_stay_unsupported` asserts both are real `AcquisitionMethod` values and both still return `unsupported_method`.

## The two risks the work item asked to be verified

Both checked against the live Ticketmaster developer documentation before implementation:

| Risk | Finding | Consequence |
|---|---|---|
| "`city` appears in third-party guides but **not** in the official v2 parameter table" | **It is in the official table** — `city`, array, "Filter by city", alongside `countryCode`, `stateCode`, `marketId`, `dmaId`, `radius`/`unit`, `localStartDateTime` | `city-provider-templates` can template the city directly. The feared `countryCode`-plus-filtering fallback is not needed. Also for that item: `latlong` is **deprecated** in favour of `geoPoint` (a geohash), so no template should use it |
| "Check whether the API key needs to travel as a header — if so that is a fetch-port concern and may widen this item" | **Query parameter** (`apikey=`); no header form is documented | The fetch port needs no change. But a working URL is then a credential, which is what the plan checkpoint decided how to handle |

## Tests Written

### `tests/ingestion/parsers/test_providers.py` (27)

Registration (`PARSERS["api"]`, `partnership`/`crawl` still unsupported, every registered
method is a real `AcquisitionMethod`); dispatch (known host, four lookalike hosts, an
unregistered host, an unparseable URL, case-insensitivity, every reader host lowercase);
documents we cannot read (five malformed inputs, two error envelopes, an empty page, and
`parse()` never falling back to `parser_failure`); and the fixture key scan.

### `tests/ingestion/parsers/test_ticketmaster.py` (32)

The whole recorded page; the four time shapes; status mapping including both `canceled`
spellings and an unknown code; `offsale` never read as sold out; venue, description and
URL mapping; country-code normalisation; six malformed shapes; no title; no id; the
`MAX_ITEMS` cap; a repeated provider id.

### `tests/ingestion/test_ingest_api.py` (15)

The API tier resolving cold end to end; the key added for the fetch and flagged as a
credential; the stored URL and `fetched_url` key-free; no key configured → URL untouched
and `credential=False`; a non-provider source untouched; a provider error failing the run
rather than emptying the city; an empty page as a successful empty run; and the key lookup
being total over unparseable URLs.

## Existing Tests Changed

Four, each because it encoded a truth this item deliberately changed. Flagged here because
editing an existing assertion is exactly where a regression hides.

| Test | Change | Why it is not a regression |
|---|---|---|
| `tests/formats/ics/test_helpers.py::test_dispatch_covers_every_structured_method` | `AcquisitionMethod.API` added to the expected set | The test asserts `PARSERS` matches the structured methods. `api` becoming structured **is** this item |
| `tests/formats/ics/test_helpers.py::test_unsupported_methods_return_an_error` | `"api"` removed from the parametrize | It is now supported. `partnership`, `crawl` and `nonsense` remain, and `test_providers.py` asserts the first two separately |
| `tests/ingestion/test_ingest_source.py::test_success_stores_validators_final_url_and_clears_failure_state` | Expected call dict gains `"credential": False` | `ScriptedFetchPort` now records the flag. The assertion got **stronger**: an ordinary source fetch is explicitly not flagged as credential-bearing |
| `tests/e2e/test_state_detection_window.py` (docstring) | Rewritten; no assertion changed | Its premise — "no high-priority method has a parser yet" — became false. See the review report |

## Mutation Check

| Removed | Tests that failed |
|---|---|
| `strip_key` on the fetch result | 1 — `test_the_key_is_stripped_from_whatever_the_fetch_reports_back` |
| `authorized_url` (fetch the stored URL, `credential=False`) | 1 — `test_the_key_is_added_for_the_fetch_and_marked_as_a_credential` |
| Exact-match dispatch, replaced with a suffix match | 2 lookalike-host cases |

Each failure was the test written for that behaviour, and nothing else moved.

## Test Commands

```bash
uv run --directory backend pytest tests/ingestion/parsers tests/ingestion/test_ingest_api.py -q
make test-backend
make coverage-backend
uv run --directory backend coverage report --include='domain/*' --fail-under=100
uv run --directory backend lint-imports
```

## Issues Found

**One real one, caught by the architecture tests**: the dispatcher was first written as
`apps/ingestion/parsers/api.py`, and `tests/architecture` discovers the AD-5 surface by
filename shape — anything under `apps/` ending in `api.py` is treated as an HTTP router
that may not write directly. The new parser was silently enrolled in that list and two
architecture tests failed. **The guard was right and the filename was wrong**, so the
module was renamed to `providers.py` rather than the discovery being taught an exception.
Details in `review-report-api-source-parser.md`.

**One recurrence of a known trap**: a repo-wide `ruff format` again reformatted
`backend/tests/shared/test_retention_published.py`, which has pre-existing drift on this
branch. Reverted, and formatting is now run only over the directories this work touches.

## Ready for Completion

- [x] All tests passing (7875, zero failures)
- [x] Coverage target met (100% for `domain/` and for all three new modules; 97.43% overall)
- [x] All 12 acceptance criteria validated
- [x] Both flagged risks verified against live documentation
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
