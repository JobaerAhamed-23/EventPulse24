---
run: run-eventpulse24-020
work_item: pulse-preview-api-and-geo
intent: onboarding-and-account
generated: 2026-10-30
status: passing
---

# Test Report: Pulse Preview API & Geo Port (FR-2, AD-12)

> **These are the post-review figures.** The revert harness found two real defects and
> one hole in the suite during this phase; the numbers below are the ones the tree
> produces **now**, not the ones it produced before those were fixed.

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Item-scoped | 100 | 0 | 0 | 100% (every module this item created) |
| **Total (whole backend)** | **3208** | **0** | **0** | **99.04%** |

The 100 item-scoped tests are a subset of the 3208-test backend suite. The whole
backend suite is **3208 passed, 0 failed** in 87.39s; coverage is **99.04%** across
6884 statements, with **169 files at 100%**.

**Every module this item created is at 100%**:

| Module | Coverage |
|--------|----------|
| `ports/geo.py` | 100% |
| `adapters/geo/header.py` | 100% |
| `adapters/geo/fake.py` | 100% |
| `adapters/geo/__init__.py` | 100% |
| `apps/catalog/preview_api.py` | 100% |
| `apps/catalog/preview_schemas.py` | 100% |
| `apps/ingestion/services/preview_read.py` | 100% |

The 66 uncovered statements are pre-existing gaps elsewhere in the codebase
(`source_registry.py`, `venue_registry.py` and the `real` adapter mode's unreachable
line).

## Test Commands

```bash
# The item's own tests
cd backend && .venv/bin/python -m pytest \
    tests/ports/test_geo.py \
    tests/api/test_preview_api.py \
    tests/ingestion/test_preview_read.py \
    tests/architecture/test_preview_anonymity.py -q

# The whole backend suite, with coverage
cd backend && .venv/bin/python -m pytest -q --cov --cov-report=term-missing

# The linter and the format check
cd backend && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .

# The import contracts
make lint-backend

# Django's own checks
cd backend && .venv/bin/python manage.py check

# The coverage gates
make coverage-backend

# The revert verification harness
cd backend && bash revert_preview_check.sh
```

## What Was Added

| File | Tests | Covers |
|------|-------|--------|
| `backend/tests/ports/test_geo.py` | 20 | The port and its two adapters: the header read, the case-insensitive lookup, the length bound, the **once-only** decode, the normalization, and the fake's configurability |
| `backend/tests/api/test_preview_api.py` | 39 | The two endpoints: the geo hit, the geo miss, the explicit override, the unsupported city, the opt-out, the identical-bytes session test, the per-IP limit, fewer than three events, the cache headers, the bound on the explicit city |
| `backend/tests/ingestion/test_preview_read.py` | 21 | The published read: the cards, the fit's ordering, every Source Badge mapping, the supported cities |
| `backend/tests/architecture/test_preview_anonymity.py` | 14 | AD-12: no session, no `personal`, no cookie, no adapter import, no Event Fit package import, no storing, no logging |

`backend/revert_preview_check.sh` is the **revert verification harness** — thirty-six
cases, each of which patches a rule out of the source, runs the tests, records the
outcome, and restores. It is how the revert table below was produced.

## What Was Changed in the Existing Tests

| File | Change |
|------|--------|
| `backend/tests/config/test_adapters.py` | Two new tests: the real table has the header geo adapter, and it implements the port. The `real` mode is not yet selectable (four ports still have no real adapter), so the real table is checked one entry at a time. |

**No existing test's expectations were weakened.** The OpenAPI schema and the
TypeScript client were regenerated (`make openapi`, `make client`) because the
endpoints are new — that is AD-19, and `test_committed_openapi_schema_matches_the_live_api`
is what checks it.

## The Properties Pinned

### The geo header is untrusted input, and it is bounded before it is expanded

The header came from the caller. Three things happen to it before it is allowed near
anything, and each has its own test.

- `test_the_header_value_is_length_bounded` — a 10 KB "city" is not a city, it is an
  attempt to put a value somewhere it should not go.
- `test_a_value_at_the_bound_is_accepted` — the bound is a bound and not a truncation.
- `test_the_header_is_url_decoded_exactly_once` — **the one that matters most.**
  `%2520` is a space that was encoded twice. One decode turns it into `%20`, still
  encoded; a second decode would turn it into a space, and that is the same shape of
  mistake that turns `%252e%252e%252f` into `../`.
- `test_a_double_encoded_traversal_is_not_decoded_into_one` — the end-to-end version.
  After one decode the value is `%2e%2e%2f`, which contains a path separator only after
  a *second* decode, so it must never become `../`.
- `test_the_header_is_read_case_insensitively` — HTTP header names are case-insensitive,
  and the port takes a plain mapping, so the adapter does the folding itself.

**The `?city=` parameter is untrusted input too, and it is bounded by the same
constant.** Two untrusted inputs into one endpoint, one bounded and one not, is the
asymmetry that prompted the bound — and the bound is the *same* `GEO_CITY_MAX_LENGTH`
the header uses, because a city name is a city name whichever way it arrived.

- `test_an_over_long_city_is_not_a_city` — an over-long city is treated as **no city
  at all**: the request falls through to geo, and the response carries the geo city.
  It is not echoed back.
- `test_a_city_at_the_bound_is_accepted` — the bound is a bound and not a truncation:
  a city exactly at the limit is still a city, and is answered as the query's city.

### The opt-out is honoured by *not consulting the geo port at all*

"Don't use my location" is a real choice, and a choice the server ignores is not a
choice. The stronger claim — the port is **not called** — is the one a test can check.

- `test_the_opt_out_does_not_consult_the_geo_port` — the geo port is **replaced with a
  port that raises if it is called**. A test that merely asserted the *result* would
  pass against an implementation that called the port and threw the answer away, which
  is exactly the implementation the work item is worried about.
- `test_the_opt_out_ignores_a_geo_city_that_would_otherwise_win` — the end-to-end
  version: even a good geo city loses to the opt-out.

### The response is identical signed-in and unsigned — compared **byte for byte**

- `test_the_response_is_identical_signed_in_and_unsigned` — `response.content`, not
  `response.json()`. Two different bodies can compare equal as JSON and differ in
  bytes, and the byte comparison is the one that catches a whitespace or key-order
  difference that a cache would treat as two responses.
- `test_the_preview_sets_no_session_cookie` — a response that sets a cookie is a
  response that depends on something.

### The response is cacheable, and does not vary on the cookie

- `test_the_response_is_cacheable_as_a_public_document` — `public` and `max-age`.
- `test_the_response_does_not_vary_on_the_cookie` — a response that varies on the
  cookie is not cacheable. Worse: a shared cache that stored one variant under a key
  that ignores the cookie would serve one visitor's response to another.
- `test_a_refused_request_is_not_cached` — a 429 is not content.

### The limit is per IP, and the address it uses is the real one

- `test_the_ip_limit_is_enforced` — 60 requests are served, the 61st is refused.
- `test_the_limit_is_per_ip` — one host cannot spend another host's budget.
- `test_the_forwarded_header_is_ignored_by_default` — **the security one.** Next's
  rewrite forwards the browser's headers as they arrived, so a browser that sets
  `X-Forwarded-For` has that value reach Django unchanged. Trusting it
  unconditionally let any caller mint a fresh throttle bucket per request, and the
  limit would have been no limit at all.
- `test_a_forwarded_header_that_is_not_an_address_is_refused` — the value must parse
  as an IP address, so a caller cannot pad the key with arbitrary text.
- `test_the_cities_endpoint_is_rate_limited_too` — the limit protects the endpoint
  *family*, not one route. Otherwise the cities endpoint would be a way around it.

### An unsupported explicit city returns an empty preview with its own name

- `test_an_unsupported_explicit_city_returns_an_empty_preview_with_its_own_name` — the
  frontend shows "No preview available in {city} yet.", and it needs the requested
  city's name to say it.
- `test_an_unsupported_explicit_city_does_not_show_the_fallback_s_events` — **the
  failure this rule exists to prevent.** If the fallback's cards appeared under
  "Queens", the heading would be a lie — and a visitor would tap "Save" on an event
  that is not near them.

### The answer carries the catalog's spelling of the city

- `test_the_catalogs_own_spelling_of_a_city_is_the_one_returned` — the spelling a
  visitor types is not the spelling the events are filed under, and a preview headed
  `"BROOKLYN"` listing the events filed under `"Brooklyn"` is a heading nobody can
  search for. `_canonical` replaces the name only when the catalog holds that city;
  when it does not, the name the visitor gave is returned unchanged.

### The supported cities are derived, not configured

A hard-coded city list goes stale the moment a source in a new city is ingested, and
the picker would then offer a city the preview cannot fill.

- `test_a_city_with_no_upcoming_fit_is_not_supported` — a city with events but no fits
  is a city the preview cannot serve.
- `test_a_stale_fit_does_not_make_its_city_supported` — a fit whose `event_version` no
  longer matches its event describes an event that no longer exists.
- `test_a_past_event_does_not_support_its_city` — a city whose only event has already
  started has no upcoming preview.
- `test_the_same_city_spelled_two_ways_is_listed_once` — two spellings of one city
  would put the city in the picker twice.

### The Source Badge is a type, and the server states the fact

The server names the type; the client owns the label and the glyph. Every mapping has
its own test, including the two that are about restraint.

- `test_a_crawled_source_is_the_crawled_badge` — *how* the facts were obtained is what
  the ⚠ means: scraped, not published to us. The crawl wins over the source's type,
  because a crawled venue site is still a scrape.
- `test_an_unknown_source_type_is_an_aggregator` — the least specific claim, and the
  one that asserts no verification the registry has not made.
- `test_the_badge_is_never_the_user_imported_one` — a user-imported event is a
  *personal* event, and FR-2 puts personal events out of scope, so this surface can
  only ever produce four of the five badge types. The mapping says so rather than
  pretending the fifth is reachable.

### The privacy rules are structural, not aspirational

PRD §10.2 and the work item's own note: the resolved city is **never** stored and
**never** logged — not "never logged with the IP", because a log line that pairs a
city with a request *is* a geo-log, and the point of not storing the city is that it is
not stored.

- `test_the_preview_does_not_log_the_resolved_city` and
  `test_the_preview_does_not_store_the_resolved_city` — checked on the **code**, with
  the docstrings stripped, so the checks cannot trip over their own explanation.

## Acceptance Criteria Validation

| Criterion | Result | Where it is pinned |
|-----------|--------|-------------------|
| A **geo port** maps a request's edge geo header to a city name or nothing | ✅ | `ports/geo.py` — `resolve_city(headers: Mapping[str, str]) -> str | None`; `test_the_port_takes_headers_and_not_a_request` |
| A **fake adapter** is the local/CI default and is **configurable to return a chosen city** | ✅ | `adapters/geo/fake.py`; `test_the_fake_reports_its_configured_city`, `GEO_FAKE_CITY` in `config/env.py` and `config/settings.py` |
| The **real adapter** only reads a header — no database lookup, no vendor call | ✅ | `adapters/geo/header.py`; `test_the_header_adapter_does_no_lookup_and_calls_no_vendor` (asserts the module's source contains no `django.db`, `httpx`, `requests`, `urllib.request` or `socket`) |
| The decoded header is **length-bounded** and **URL-decoded once** | ✅ | `test_the_header_value_is_length_bounded`, `test_the_header_is_url_decoded_exactly_once`, `test_a_double_encoded_traversal_is_not_decoded_into_one` |
| The explicit `city` parameter is **bounded by the same constant** | ✅ | `test_an_over_long_city_is_not_a_city`, `test_a_city_at_the_bound_is_accepted` — an over-long city is treated as no city and falls through to geo |
| **Supported cities** = the cities with at least one upcoming public event that has Event Fit | ✅ | `apps/ingestion/services/preview_read.py`; `test_the_supported_cities_are_the_cities_with_a_current_fit` |
| A geo city outside that set falls back to **NYC**; NYC is a **named constant** | ✅ | `PREVIEW_FALLBACK_CITY` in `shared/constants.py`; `test_a_geo_city_outside_the_supported_set_falls_back` |
| `GET /api/public/preview?city=` returns **up to 3 cards** | ✅ | `PREVIEW_SIZE = 3`; `test_the_preview_returns_at_most_three_cards` |
| Each card has title, venue, local start time with timezone, fit score and tags | ✅ | `test_a_card_carries_the_event_fit_and_the_source_badge` — the card's keys are pinned **exactly** |
| …and Source Badge inputs | ✅ | `PreviewCard.source_name` / `source_badge`; `test_the_cards_carry_the_fit_and_the_badge` |
| The response returns the resolved city **and whether it came from geo, the query, or the fallback** | ✅ | `city_source` ∈ `{geo, query, fallback}`; `test_the_preview_body_carries_the_city_and_its_source` |
| With no `city` param it uses geo | ✅ | `test_the_geo_city_is_used_when_there_is_no_city_parameter` |
| An explicit `city` overrides geo | ✅ | `test_an_explicit_city_overrides_geo` |
| An unsupported explicit city returns an **empty preview with the resolved city** — never another city's events | ✅ | `test_an_unsupported_explicit_city_returns_an_empty_preview_with_its_own_name`, `test_an_unsupported_explicit_city_does_not_show_the_fallback_s_events` |
| `GET /api/public/preview/cities` lists the supported cities | ✅ | `test_the_cities_endpoint_lists_the_supported_cities` |
| **No session.** A test calls both endpoints signed-in and unsigned and gets identical responses | ✅ | `test_the_response_is_identical_signed_in_and_unsigned`, `test_the_cities_response_is_identical_signed_in_and_unsigned` — compared **byte for byte** |
| The endpoint doesn't touch `request.user` or `personal` | ✅ | `test_the_preview_surface_never_reads_the_session`, `test_the_preview_surface_never_touches_the_personal_schema` — checked on the **code** |
| **Cacheable.** Cache headers suited to a public per-city response; varies on the city input and nothing session-related | ✅ | `test_the_response_is_cacheable_as_a_public_document`, `test_the_response_does_not_vary_on_the_cookie` |
| **Rate-limited per IP** (PRD §11.2) | ✅ | `test_the_ip_limit_is_enforced`, `test_the_limit_is_per_ip`, `test_the_cities_endpoint_is_rate_limited_too` |
| The **"Don't use my location"** choice is honoured — geo is not consulted | ✅ | `test_the_opt_out_does_not_consult_the_geo_port` — the port is **replaced with one that raises** |
| Router registered, client regenerated (AD-19) | ✅ | `config/api.py` mounts it at `/public`; `test_the_preview_modules_are_reachable_from_the_router`; `make openapi` + `make client`; `test_committed_openapi_schema_matches_the_live_api` |
| `make lint-imports` passes | ✅ | 19 kept, 0 broken |
| The endpoint reads `catalog` only through `ingestion`'s published read interface | ✅ | `apps/ingestion/services/preview_read.py`; `test_the_preview_never_reads_the_ingestion_models`, `test_the_preview_read_hands_over_plain_data`, `test_the_preview_never_imports_the_event_fit_package_directly` |
| The resolved city is **never stored** server-side, and **never logged** with the IP | ✅ | `test_the_preview_does_not_store_the_resolved_city`, `test_the_preview_does_not_log_the_resolved_city` |
| Tests cover: geo hit, geo miss → NYC, explicit override, unsupported city → empty, opt-out skipping geo, identical with and without a session, the per-IP limit, fewer than 3 events | ✅ | 100 tests across four files |

## Reverting Each Rule

Every rule was verified by **reverting it and watching the test fail**. A regression test
that passes against the broken code is not a regression test — and the run's standing
rule is that **a revert case that does not fail is not a revert case; it is a hole in
the suite wearing a harness's clothes.** The harness is
`backend/revert_preview_check.sh`; it patches the source, runs the test files, records
the outcome, restores, and ends with a `git diff --stat` that proves every patch was put
back.

| # | Rule | Reverted | Result |
|---|------|----------|--------|
| R1 | The real adapter reads the edge's geo header | the header read returns `None` | **7 tests fail** ✓ |
| R2 | The header value is URL-decoded exactly once | `unquote(unquote(raw))` | **2 tests fail** ✓ |
| R3 | The header value is length-bounded before it is used | the bound check disabled | **1 test fails** ✓ |
| R4 | The header lookup is case-insensitive | `headers.get(name)` | **1 test fails** ✓ |
| R5 | The header value is normalized into a city shape | the character filter removed | **5 tests fail** ✓ |
| R6 | The fake adapter is configurable to return a chosen city | the setting ignored | **3 tests fail** ✓ |
| R7 | The fallback city is the named constant | a literal city name | **4 tests fail** ✓ |
| R8 | An explicit city overrides geo | the explicit city replaced by the first supported one | **3 tests fail** ✓ |
| R9 | A geo city outside the supported set falls back | the support check removed | **1 test fails** ✓ |
| R9b | The answer carries the catalog's spelling of the city | the canonicalisation removed | **1 test fails** ✓ |
| R10 | The opt-out does not consult the geo port at all | `if use_geo:` → `if True:` | **2 tests fail** ✓ |
| R11 | An unsupported explicit city returns an empty preview, not the fallback's cards | the unsupported city replaced by the fallback | **4 tests fail** ✓ |
| R12 | The response is cacheable as a public document | `Cache-Control` not set | **1 test fails** ✓ |
| R13 | The response does not vary on the cookie | `Vary: Cookie` | **1 test fails** ✓ |
| R14 | A refused request is not cached | `Cache-Control: no-store` removed | **1 test fails** ✓ |
| R15 | The public preview is rate limited per IP | the limit raised to 10⁹ | **6 tests fail** ✓ |
| R16 | The limit is keyed on the caller address | one key for every caller | **1 test fails** ✓ |
| R17 | A refused request says when to retry | `Retry-After` not set | **1 test fails** ✓ |
| R17b | The cities endpoint can answer a refusal at all | the 429 schema removed from the response map | **2 tests fail** ✓ |
| R18 | A city is supported only when it has a current Event Fit | the staleness check disabled | **2 tests fail** ✓ |
| R19 | A city with no upcoming event is not supported | the future filter removed | **6 tests fail** ✓ |
| R20 | A superseded event does not support its city | the exclusion removed | **6 tests fail** ✓ |
| R21 | The supported cities are listed alphabetically | the Python sort removed | **3 tests fail** ✓ |
| R21b | The order is the Python one, not the database's locale collation | the database's `ORDER BY` put back | **1 test fails** ✓ |
| R22 | One city spelled two ways is listed once | the case-insensitive dedup removed | **1 test fails** ✓ |
| R23 | The support check is case-insensitive | `city in self.cities` | **1 test fails** ✓ |
| R24 | The preview shows at most three cards | `PREVIEW_SIZE = 99` | **1 test fails** ✓ |
| R25 | A crawled source gets the crawled badge, whatever its type | the crawl check disabled | **1 test fails** ✓ |
| R26 | An unknown source type is the least specific claim, the aggregator | the fallback badge changed to "official" | **1 test fails** ✓ |
| R27 | The catalog does not reach the Event Fit package directly | the import pointed at `event_fit.reads` | **28 tests fail** ✓ |
| R28 | The preview surface never reads the session | `_ = request.user` planted | **1 test fails** ✓ |
| R29 | The preview surface never touches the personal schema | `from shared.db import PERSONAL` planted | **1 test fails** ✓ |
| R30 | The preview never stores the resolved city | `cache.set("preview:city", resolved)` planted | **1 test fails** ✓ |
| R31 | The preview never logs the resolved city | a `logging` call planted | **1 test fails** ✓ |
| R32 | The router is mounted at `/public` | the mount path changed | **35 tests fail** ✓ |
| R33 | The explicit city is bounded, like the header | the bound check disabled | **1 test fails** ✓ |

**All thirty-six reverts were restored** and the suite re-run green afterwards;
`git diff --stat` confirmed no revert artifacts remained.

### The cases that did not fail, and what they taught

**Seven of the thirty-six cases did not fail on the first run.** Five were holes in the
suite; two were holes in the harness itself. All seven are now caught.

**R3 — the bound was stated twice, so removing one check left the other.**
The adapter bounded the raw value *and* the decoded value. Decoding only ever
*shortens* a value — each `%XX` escape becomes one character — so the second check
could never fire: it was unreachable code. An unreachable check is not a safety net,
it is a claim the code does not make. The second check was **removed**, the comment
rewritten to say why one check is enough, and the revert case now removes the one that
remains.

**R8, R11, R21 — the tests could not tell two behaviours apart.**

- *R8 and R11* reverted the wrong branch: the lever was the city-resolution function,
  but the pattern was written against a version of the source from before an edit, so
  the patch never applied and the case was **skipped** rather than run. A skipped case
  is not a passing case, and the harness says so — it counts a skip as a hole and
  fails the run. The patterns were corrected against the current source.
- *R21* was a genuine hole. The supported cities were sorted **twice**: once by the
  database (`ORDER BY city`) and once in Python (`sorted(..., key=str.casefold)`). The
  two orderings agreed on the test's city names, so removing the Python sort changed
  nothing observable and the test passed. The fix was in the **source**: the database
  is no longer asked to sort at all, because a text `ORDER BY` is a **locale
  collation** — `en_US.UTF-8` ignores punctuation at the primary level and orders case
  in a locale-specific way — so two deployments with different locales would list the
  same cities in a different order. `str.casefold` is the same everywhere, so it is the
  sort that decides. The Python sort is now the only sort, and removing it breaks the
  test.

**R21b — the same rule, the other lever.** With the database's sort gone, putting it
back is caught by a **structural** check (`test_the_supported_cities_are_not_ordered_by_the_database`),
not by a behavioural one.

**The discriminator that was not usable.** The attempt to make the behavioural
alphabetical test discriminate between the two orderings failed, and the reason is
worth recording. The obvious candidate — `"St. John's"` against `"St Johns"` — does
**not** discriminate: Python's `str.casefold` puts `"St Johns"` first as well, because
the comparison reaches the space (0x20) before the period (0x2E). The candidate that
*does* discriminate — `"A"` against `"a"` — cannot be used either, because the
catalog's dedup is case-insensitive, so the two are **one** city and only one is ever
listed. A test cannot use a pair the data will not hold. The rule was therefore made
**structural**: the read must not ask the database to sort, and that is checked on the
code.

### Two real defects the harness found, and one the review found
**The cities endpoint could not answer a refusal at all.** It declared
`response={200: PreviewCitiesOut}` with no 429 schema, so when the throttle refused a
request, django-ninja raised `ConfigError: Schema for status 429 is not set` and the
endpoint returned a **500**. Every rate-limited request to `/api/public/preview/cities`
was a server error rather than a refusal. The fix is one line — the 429 schema — and
`test_the_cities_endpoint_is_rate_limited_too` is what found it. It is the only reason
the case exists: the cities endpoint had never been tested past its limit.

**The two paths answered with different spellings.** The geo path returned the
catalog's spelling of the city (`"Brooklyn"`); the explicit path returned the caller's
(`"BROOKLYN"`). A visitor typing `brooklyn` got a preview headed `brooklyn` listing the
events filed under `Brooklyn`. Both paths now answer with the catalog's spelling —
**and only when the catalog holds that city**, so an unsupported city is never silently
renamed.

**The third defect was found by reading the two untrusted-input paths side by side.**
The geo header was bounded to `GEO_CITY_MAX_LENGTH`; the `?city=` query parameter was
not bounded at all, so a caller could send an arbitrarily long value and have it echoed
back in the response. Two untrusted inputs into one endpoint, one bounded and one not,
is the asymmetry that prompted it. The bound is the **same constant** the header uses,
and an over-long city is treated as **no city at all** — the request falls through to
geo and then to the fallback, rather than being echoed back.

### The harness had a bug, and it was the same bug as before

The event-fit harness keyed its backup on the file's **basename** alone, so two cases
touching the same file shared one backup path, and case A's restore overwrote case B's
backup. This harness is written the other way round from the start: **a unique backup
per case**, and — the important one — **the restore is verified, not assumed**. Each
case compares the restored file against its backup byte for byte and aborts the run if
they differ. A restore that silently fails is worse than no restore: it makes every
later result a claim about a tree that does not exist.

The harness also **counts a skipped case as a hole**. A case whose pattern drifted is
not a passing case; it is a case that did not run. Three cases skipped on the first
run for exactly that reason, and the run failed.

After the review phase edited the source — the explicit-city branch gained the bound,
and `_throttle_key` gained its `scope` parameter — **four more cases' patterns drifted**
and the run failed again with four skips. The patterns were corrected against the
current source; the run is green with **36 cases, 36 caught, 0 holes**.

The lesson is the same one the previous item's harness taught: **a harness whose levers
drift with the source is a harness that has stopped verifying anything.** The skip is
counted as a hole for exactly that reason — a case whose patch cannot be found has
verified nothing, and reporting it as a pass would be a lie.

## Notes on the Implementation

Five decisions are worth recording, because each one could reasonably have gone the
other way.

### The published read lives *inside* `apps.ingestion`, not in `apps.catalog`

AD-2's `models-ingestion` contract protects `apps.ingestion.models` to `apps.ingestion`
— so `apps.catalog` cannot import `apps.ingestion.models`, and it cannot import
`apps.ingestion.event_fit.reads` either, because *that* module imports the model
directly. The obvious placement for the preview's read is `apps/catalog`, and it does
not work.

So the read lives at `apps/ingestion/services/preview_read.py`: inside `apps.ingestion`,
so the contract holds, and handing over **frozen dataclasses** rather than model
instances, so the calling app never holds a reference to a model it may not import. The
wall holds without either side knowing the other's models. The work item asks that "the
endpoint reads `catalog` only through `ingestion`'s published read interface", and this
module is that interface.

### The Source Badge is derived in the read, because the fit read does not join the source

The Event Fit read carries the score, the tags and the event's public facts. It
deliberately does **not** join the source — a fit is about an event's fit, not about
where it came from. The preview needs the badge, so the published read joins the source
(one query, keyed by event id) and derives the badge type.

### The opt-out is a branch that skips the call, not a flag on the answer

The temptation is to call the geo port and ignore its answer when `use_geo=false`. The
rule here is that the port is **not called**, and the test replaces it with a port that
raises if it is. The difference matters for a reason that is not theoretical: a geo
lookup is a request to the edge, and "the visitor said not to" should mean the request
is never made — not that the answer was discarded afterwards.

### The `user_imported` badge is not producible here, and the mapping says so

A user-imported event is a *personal* event, and FR-2 puts personal events out of scope
for the preview. The UX spec names five badge types; this surface can only ever produce
four of them. Rather than map the fifth and pretend it is reachable, the mapping
leaves it out and `test_the_badge_is_never_the_user_imported_one` states it.

### The explicit city is bounded by the same constant as the header, and falls through rather than truncating

Two untrusted inputs reach this endpoint — the edge's geo header and the `?city=`
parameter — and the header was bounded while the parameter was not. The bound is the
**same** `GEO_CITY_MAX_LENGTH`, because a city name is a city name whichever way it
arrived.

An over-long city is treated as **no city at all**, so the request falls through to geo
and then to the fallback — the same shape as the "no city" case, which is the
endpoint's normal path. The alternatives were both worse: **truncating** would answer
with a different city than the caller asked for (and could answer with one the catalog
happens to hold), and **echoing** would put an arbitrarily long value into the response
body and into the `city` field.

## The Final Gate

| Check | Command | Result |
|-------|---------|--------|
| The item's tests | `pytest tests/ports/test_geo.py tests/api/test_preview_api.py tests/ingestion/test_preview_read.py tests/architecture/test_preview_anonymity.py` | **100 passed** |
| The whole backend suite | `pytest -q` | **3208 passed, 0 failed** |
| Coverage | `make coverage-backend` | 99.04% overall (≥80%), `domain/` 100% |
| The item's own modules | `pytest --cov=apps.catalog.preview_api ...` | **207 statements, 0 missed, 100%** |
| The linter | `ruff check .` | All checks passed |
| The formatter | `ruff format --check .` | 377 files already formatted |
| The import contracts | `make lint-backend` | **19 kept, 0 broken** |
| Django's own checks | `manage.py check` | no issues (1 silenced) |
| The revert verification | `bash revert_preview_check.sh` | **36 cases, 36 caught, 0 holes** |
| The committed API contract | `test_committed_openapi_schema_matches_the_live_api` | ✅ the schema and the TypeScript client are regenerated |

## What This Item Does Not Cover

- **The frontend.** The Pulse Preview's *pages* are the `frontend-pulse-preview` work
  item. This item is the backend the pages will call: the two endpoints, the geo port
  and its adapters, the published read, and the wire contract.
- **The `real` adapter mode as a whole.** Four ports (`billing`, `email`, `embedding`,
  `llm`) still have no real adapter, so `ADAPTER_MODE=real` cannot be selected yet.
  The real *geo* adapter exists and is wired into the real table; the table itself
  cannot be reached.
- **A geolocation vendor.** The real adapter reads the edge's header and does nothing
  else — no lookup, no vendor call. That is a deliberate answer to PRD §10.2, not a
  gap: a geo-IP vendor would mean sending every visitor's address to a third party on
  every page load.
- **The city picker's UI.** `/api/public/preview/cities` returns the names; drawing
  the picker is the frontend item's.
- **Persisting the resolved city.** PRD §10.2 forbids it for an anonymous visitor, and
  the endpoint does not do it. The privacy rules are enforced structurally, so a later
  edit that adds a `cache.set` or a `logger.info` fails the architecture suite.

---

### Test Result

**PASS.** 100 item-scoped tests, 3208 in the whole backend suite, 0 failures. Every
module this item created is at 100% coverage. All 36 revert cases were caught; the
seven that were not caught on the first run were holes in the suite or in the harness,
and each is now closed — two of them by real fixes to the source, one of which was a
500 on every rate-limited request to the cities endpoint.


---

## Work Item: frontend-auth-surfaces

**Mode:** confirm · **Gates:** `make test-web`, `make lint-web`, `make test-backend`

### Test Results

| Suite | Result |
|---|---|
| `make test-web` (Vitest) | **259 passed**, 0 failed, 0 skipped (29 files) |
| `make lint-web` (ESLint + `next typegen` + `tsc --noEmit` + Prettier) | **clean** |
| `make test-backend` (pytest) | **3208 passed**, 0 failed |

The frontend suite was 149 tests before this item and is 259 after: **110 added**, and
one existing test extended. The backend suite grew from 3199 to 3208 — not from new
backend tests, but because the auth endpoints' declared responses changed and the
contract test regenerated (see "The contract fix" below).

New and changed test files:

| File | Tests | Covers |
|---|---|---|
| `lib/csrf.test.ts` | 14 | Cookie reading, the unsafe-method rule, the fresh read per request, the token fetch |
| `lib/backend-client.test.ts` | 3 | The middleware is **registered on the real client**, reads and writes both |
| `lib/session.test.ts` | 10 | Cookie forwarding, the three-way fold, every `homeRoute` branch |
| `lib/api-errors.test.ts` | 14 | The API's words and field errors, and every malformed shape |
| `components/auth/signin-form.test.tsx` | 12 | Success, the enumeration rule, 429, offline, in-flight, the reveal toggle |
| `components/auth/signup-form.test.tsx` | 13 | The locked copy, the API's `details`, the two-call flow, the hold, no OIDC buttons |
| `components/auth/reset-request-form.test.tsx` | 4 | The locked sentence, said identically for any address |
| `components/auth/reset-confirm-form.test.tsx` | 6 | Success, expired-or-used, the token leaving the URL, the validators |
| `components/auth/sign-out-button.test.tsx` | 3 | Sign-out, the destination, the failure path |
| `components/saved-events-section.test.tsx` | 7 | The session-carrying read and every quiet-failure branch |
| `components/pre-auth/pre-auth-topbar.test.tsx` | 6 | The topbar-quiet rule, the footer's links, `aria-current` |
| `app/page.test.tsx` | 9 | All four routing branches, the placeholder's contents, the duplicate-list fix |
| `app/signin/page.test.tsx` | 8 | The silent redirect on `/signin` and `/signup` |
| `app/reset-password/page.test.tsx` | 5 | Token / no token / empty / repeated, and `no-referrer` |
| `components/personal-events-section.test.tsx` | 5 (was 4) | **+1**: the read carries the visitor's session |

### Acceptance Criteria Validation

| Criterion | Status | Where |
|---|---|---|
| `/signup` and `/signin` implement their mockups, pre-auth topbar, footer and CTAs as drawn | **Met** | `app/signup/page.tsx`, `app/signin/page.tsx`, `components/pre-auth/*`; `pre-auth-topbar.test.tsx` pins the topbar-quiet rule by looking for its inversion |
| Space for OIDC buttons, nothing wired, no dead buttons, choice recorded | **Met** | A marked slot comment in `signup-form.tsx`; the test asserts no "Continue with …" button renders |
| Error states use the API's calm messages verbatim; no wording reveals whether an account exists | **Met** | `lib/api-errors.ts`; `signin-form.test.tsx` and `signup-form.test.tsx` each scan the rendered page for "already exists", "don't see an account", "no account", "registered" |
| `/reset-password` covers request, sent, set-new, and expired-or-used | **Met** | `reset-request-form.tsx`, `reset-confirm-form.tsx`; six tests, plus the live Mailpit run-through |
| Routing: anonymous `/` → `/preview` | **Met** | `homeRoute`; live: `307 → /preview` |
| Routing: signed in, not onboarded → `/onboarding` | **Met** | live: `307 → /onboarding` |
| Routing: signed in and onboarded → the placeholder home | **Met** | live: `200`, with the heading, both sections and sign-out |
| Routing: signed-in `/signin` → silent redirect to `/` | **Met** | live: `307 → /` |
| The placeholder home is calm, has no fake digest cards or data, reuses the personal-events components, has sign-out | **Met** | `app/page.tsx`; a test scans for "why this", "relevance", "pulse score", "tonight's pulse" |
| CSRF tokens sent on every state-changing call | **Met** | One middleware on the client; proven on the real client for an auth write **and** a personal write |
| Only the generated client; no hand-written API types (AD-19) | **Met** | ESLint's `no-restricted-imports`/`no-restricted-globals` still pass; the contract was fixed rather than cast around |
| Design tokens and vanilla components only; no component library | **Met** | `tests/architecture.test.ts` unchanged and passing; no dependency added |
| WCAG: labelled inputs, visible focus, errors announced | **Met** | Every input has `htmlFor`; errors are `role="alert"` + `aria-describedby`; the reveal toggle's `aria-pressed` and destination-state label are tested |
| Vitest covers each form's success and error rendering, enumeration-neutral copy, each routing branch, the expired-token state | **Met** | The table above |
| `make lint-web` and `make test-web` pass | **Met** | Both clean |

### Revert Verification

Every rule was broken in the source and its test watched to fail. The harness backs each
file up per case and verifies the restore byte for byte; a restore mismatch aborts the
run, because a silent restore failure makes every later result a claim about a tree that
does not exist.

**26 of 26 cases failed their tests, as they must.** One case (26) reported a *setup*
failure on the first run — the mutator's indentation did not match the file, so nothing
was changed — which the harness caught by comparing the file before and after rather
than trusting the edit. It was corrected and re-run; a mutation that silently applies to
nothing would otherwise have been reported as a passing revert case.

| # | Rule reverted | Test that caught it |
|---|---|---|
| 1 | The CSRF middleware is never registered on the client | `backend-client.test.ts` |
| 2 | The CSRF token is cached at load instead of read per request | `csrf.test.ts` |
| 3 | The header goes on reads instead of writes | `csrf.test.ts` |
| 4 | The personal read drops the session cookie | `personal-events-section.test.tsx` |
| 5 | The saved read drops the session cookie | `saved-events-section.test.tsx` |
| 6 | `getSession` forwards no cookies | `session.test.ts` |
| 7 | "Unavailable" is folded into "anonymous" | `session.test.ts` |
| 8 | The `homeRoute` branches are swapped | `session.test.ts` |
| 9 | The `/onboarding` redirect is dropped | `session.test.ts` |
| 10 | The sign-in error moves to the Email field | `signin-form.test.tsx` |
| 11 | An enumeration string is planted in the sign-in form | `signin-form.test.tsx` |
| 12 | Sign-up skips the follow-up sign-in | `signup-form.test.tsx` |
| 13 | The hold ignores `prefers-reduced-motion` | `signup-form.test.tsx` |
| 14 | Sign-up routes to `/` instead of `/onboarding` | `signup-form.test.tsx` |
| 15 | A dead OIDC button is rendered | `signup-form.test.tsx` |
| 16 | The reset token is left in the address bar | `reset-confirm-form.test.tsx` |
| 17 | The expired-token branch is lost | `reset-confirm-form.test.tsx` |
| 18 | The topbar grows a "Sign in" link | `pre-auth-topbar.test.tsx` |
| 19 | The home redirects when the API is down | `page.test.tsx` |
| 20 | The duplicate personal-events list returns | `page.test.tsx` |
| 21 | The home loses `force-dynamic` | `page.test.tsx` |
| 22 | The silent redirect on `/signin` is dropped | `signin/page.test.tsx` |
| 23 | The reset page sends a referrer | `reset-password/page.test.tsx` |
| 24 | A token in the URL is ignored | `reset-password/page.test.tsx` |
| 25 | Sign-out routes to `/` | `sign-out-button.test.tsx` |
| 26 | The API's field errors are replaced with our own wording | `api-errors.test.ts` |

The harness is at
`/tmp/claude-1001/-home-bs1346-Documents-P-project-EventPulse24/ede4680d-7995-49c2-9cb2-855b0550830c/scratchpad/revert-check.sh`.
It is a session artefact, not a committed file: it mutates working-tree sources, so it
belongs outside the repository.

### The Live Run-through

Against the real stack (Django on `127.0.0.1:8000`, `next dev` on `127.0.0.1:3000`,
Postgres/Redis/Mailpit in Docker), through the browser's own path — the proxy, the
cookie jar, the CSRF header:

| Step | Result |
|---|---|
| Anonymous `GET /` | `307 → /preview` |
| `/signin`, `/signup`, `/reset-password` render | Forms present; **no** "Continue with …" button on `/signup` |
| `/reset-password?token=…` | The set-new form, and `<meta name="referrer" content="no-referrer">` |
| Sign-up, then sign-in (the form's two calls) | `201`, then `200` with `sessionid` |
| `GET /` before onboarding | `307 → /onboarding` |
| `GET /` after finishing onboarding | `200`, "Your Pulse is being prepared.", both sections, "Signed in as …", "Sign out" |
| `GET /signin` while signed in | `307 → /` |
| Create a personal event, then reload `/` | The event **appears on the home** — the bug this item fixed |
| Reset request → the Mailpit link → set a new password | `202`, the link renders the set-new form, `200` |
| Reuse the same token | `422 invalid_reset_token`, "That reset link isn't valid anymore. Ask for a new one." |
| Sign out, then sign in with the new password | `200`; the old password answers `401` |

### The Contract Fix (a deviation, approved mid-run)

`tsc` rejected three call sites: `POST /api/auth/signup`, `/signout` and
`/password-reset` declared only their success status, so the generated client typed their
`error` as `never` — the contract claimed they could not fail. They can: the probe got a
`422` from sign-up with a weak password, and all three can answer `403 csrf_failed`, with
`429` on sign-up and the reset request.

The plan said this item would change no backend code. Rather than cast around a contract
that was wrong, the endpoints now declare the statuses they can actually produce, which
is what every other endpoint in the project already does. Each declaration was read out
of the service, not guessed:

| Endpoint | Declared | Why exactly these |
|---|---|---|
| `/signup` | `201, 403, 422, 429` | CSRF; `ValidationError` from the password validators or a non-address; the sign-up throttle |
| `/signin` | `200, 401, 403, 429` | The enumeration-safe credential refusal; CSRF; the sign-in throttle. `authenticate` raises nothing else |
| `/signout` | `200, 403` | It cannot fail on its merits — an anonymous caller gets `200` — so CSRF is the only error |
| `/password-reset` | `202, 403, 429` | No validation happens (an unknown address is answered identically), so there is no `422` |
| `/password-reset/confirm` | `200, 403, 422` | A spent or expired token and a weak password are both `422`; no throttle of its own |

`make client` regenerated `openapi.json` and `schema.ts`, and the full backend suite
passes (3208) with the contract test satisfied by the regenerated schema.

### Notes

- **Node 24 is required to run the suite.** Under Node 20 every Vitest file fails to
  start: undici 8.12.3 reads `createZstdDecompress`, which Node 20 does not have. The
  repo already says so (`.nvmrc` is `24`, `package.json` requires `>=24.15`); it is
  recorded here because the failure mode is an unhelpful `Cannot read properties of
  undefined (reading 'bind')` rather than a version message.
- **No dependency was added.** `@testing-library/user-event` was installed, then removed
  when the existing component tests turned out to drive interactions with `fireEvent`;
  `package.json` and the lockfile are unchanged.
- **The local database was four `personalization` migrations behind** at the start of the
  run, which made `/api/auth/me` answer `500`. `make migrate` fixed it. That is the
  environment, not the code.


---

## Work Item: frontend-onboarding-flow

**Mode:** confirm · **Gates:** `make test-web`, `make lint-web`, `make test-backend`

### Test Results

| Suite | Result |
|---|---|
| `make test-web` (Vitest) | **342 passed**, 0 failed, 0 skipped (36 files) |
| `make lint-web` | **clean** (ESLint, `next typegen` + `tsc --noEmit`, Prettier) |
| `make test-backend` (pytest) | **3209 passed**, 0 failed |

The frontend suite was 262 after the previous item and is 342 now: **80 added**. The
backend gained one test for the new projection field, and one existing test was extended.

| File | Tests | Covers |
|---|---|---|
| `components/onboarding/onboarding-flow.test.tsx` | 19 | Resume, Back, the two step numbers in both directions, saving, finishing, 409, skip-all |
| `components/onboarding/calendar-step.test.tsx` | 23 | Providers, guidance, masking and non-persistence, the poll, the cap, the refusals, an existing connection |
| `components/onboarding/interests-step.test.tsx` | 12 | The cap rule as a pure function, the chips, `aria-pressed`, the disabled state |
| `components/onboarding/digest-step.test.tsx` | 11 | The time control, presets, the zone default, a stored preference |
| `components/onboarding/step-shell.test.tsx` | 8 | The progress dots, the announcement, focus, the footer's actions |
| `app/onboarding/page.test.tsx` | 8 | The three gates, the session-carrying reads, resume on first paint |
| `backend/tests/personalization/test_personal_events_api.py` | +1, 1 changed | An imported event carries its connection; the contracted field set |

### Acceptance Criteria Validation

| Criterion | Status | Where |
|---|---|---|
| Each step implements its mockup; Back / Skip / Continue in the **footer**, never the topbar | **Met** | `step-shell.tsx`; a test asserts each action sits after the step body in document order |
| Step 1: three providers, equal weight | **Met** | `calendar-providers.ts`, `calendar-step.tsx` |
| Step 1: choosing one reveals **that** provider's guidance and a masked input | **Met** | Tested, including switching providers |
| Step 1: the address is never echoed into the DOM after submission, never in `localStorage` | **Met** | Cleared on success; tests read both storages and the DOM, and one drives the real path back to the form |
| Step 1: connecting shows the sync state, then the imported events | **Met** | The bounded poll, then this connection's events (via the new projection field) |
| Step 1: the Free cap shows the calm upgrade message, no modal | **Met** | Inline alert + "Upgrade" link; a test asserts no `dialog` role |
| Step 1: "Connection failed. Skip for now?" is the error state | **Met** | The locked copy, with equal-weight "Try again" and the footer's Skip |
| Step 2: chips come from the API; a 4th pick is prevented; zero picks is a valid Continue | **Met** | The cap rule is a pure function with its own tests; the chips' `disabled` is tested separately |
| Step 3: delivery time and an IANA picker defaulting to the browser's zone, reusing `lib/timezones.ts` | **Met** | `digest-step.tsx`; `browserZone()` and `ZONE_CHOICES` |
| Skip all reaches the skip-all state and then `/` | **Met (with a deviation)** | The mockup's "skip-all state" is the cold-start Pulse Digest, which this intent does not build; `/skip-all` → the placeholder home, as the brief directs |
| Resume: reloading opens the recorded step | **Met** | The server read is the first paint; a test mocks step 2 and asserts step 2 renders |
| A completed user visiting `/onboarding` goes to `/` | **Met** | Tested, and proven live (`307 → /`) |
| The Personal tone is paired with the visible "Personal" label | **Met** | Tested on the imported-event rows |
| Chips are toggle buttons with `aria-pressed`; progress announced; focus moves to the step heading | **Met** | `step-shell.test.tsx`, `interests-step.test.tsx` |
| Generated client only; tokens and vanilla components only | **Met** | ESLint and the architecture tests unchanged and passing; no dependency added |
| Vitest covers each step's render and skip path, masking, the cap, the 3-pick limit, resume, skip-all, the completed redirect | **Met** | The table above |

### Revert Verification

**38 of 38 cases failed their tests, as they must** — after two were fixed. The first run
reported **two holes**, and both were real gaps rather than harness noise:

1. **"the address is kept after connecting"** passed against broken code. The DOM check
   only passed because the form unmounts into the sync state once connected, so retaining
   the credential in component state was invisible to it. There *is* a reachable way back
   to that form — connect succeeds, the first poll reports the feed revoked, "Try again"
   returns to the form — and the secret would have been sitting in the field. A test now
   drives exactly that path, and a second test pins the opposite case: a **refused**
   address is deliberately kept so the user can fix a typo.
2. **"a fourth pick is allowed"** passed because the test clicked a `disabled` button,
   which fires nothing — the guard behind the attribute was never exercised. The cap rule
   is now a pure exported function (`nextSelection`) tested directly, and the chips'
   `disabled` attribute is tested separately, with a revert case each. A rule that can
   only be reached through a disabled control cannot be tested through the UI, and
   pretending otherwise is how a cap silently stops holding.

| # | Rule reverted | Caught by |
|---|---|---|
| 1 | Continue advances the server while revisiting an earlier step | `onboarding-flow.test.tsx` |
| 2 | Skip calls the API while revisiting | `onboarding-flow.test.tsx` |
| 3 | Back posts a step call | `onboarding-flow.test.tsx` |
| 4 | The view ignores the server's answer | `onboarding-flow.test.tsx` |
| 5 | The flow always starts at step 1 | `onboarding-flow.test.tsx` |
| 6 | The page reads no state | `page.test.tsx` |
| 7 | The server reads drop the session cookie | `page.test.tsx` |
| 8 | A completed user is let into the flow | `page.test.tsx` |
| 9 | An anonymous visitor is let into the flow | `page.test.tsx` |
| 10 | Finishing does not go home | `onboarding-flow.test.tsx` |
| 11 | A 409 is shown as an error instead of going home | `onboarding-flow.test.tsx` |
| 12 | Skip-all does not finish | `onboarding-flow.test.tsx` |
| 13–15 | The interests / digest are not saved; a refused save still advances | `onboarding-flow.test.tsx` |
| 16–19 | The address is unmasked / kept / stored / revealable | `calendar-step.test.tsx` |
| 20 | Every personal event is claimed as imported | `calendar-step.test.tsx` |
| 21 | The poll never gives up | `calendar-step.test.tsx` |
| 22 | A revoked connection is treated as a slow import | `calendar-step.test.tsx` |
| 23 | The cap message becomes a dialog | `calendar-step.test.tsx` |
| 24 | The locked failure copy is replaced | `calendar-step.test.tsx` |
| 25 | The provider guidance does not switch | `calendar-step.test.tsx` |
| 26 | An existing connection shows an empty form | `calendar-step.test.tsx` |
| 27 | A fourth pick is allowed (the rule) | `interests-step.test.tsx` |
| 28 | The chips are not disabled at the cap (the attribute) | `interests-step.test.tsx` |
| 29 | The chips are hard-coded instead of the API's | `interests-step.test.tsx` |
| 30 | Picks are reported by label | `interests-step.test.tsx` |
| 31 | `aria-pressed` never flips | `interests-step.test.tsx` |
| 32–34 | The zone ignores the browser; a stored time keeps its seconds; a preset does nothing | `digest-step.test.tsx` |
| 35 | Focus does not move to the new step | `step-shell.test.tsx` |
| 36 | The progress dots lose their state words | `step-shell.test.tsx` |
| 37 | The actions move above the step body | `step-shell.test.tsx` |
| 38 | The busy state does not disable the actions | `step-shell.test.tsx` |

Harness:
`/tmp/claude-1001/-home-bs1346-Documents-P-project-EventPulse24/ede4680d-7995-49c2-9cb2-855b0550830c/scratchpad/revert-check-onboarding.sh`
(a session artefact — it mutates working-tree sources, so it lives outside the repo).

### The Live Run-through

Against the real stack, with **the worker and beat running**, through the browser's own
path (the proxy, the cookie jar, the CSRF header). `ADAPTER_MODE=fake` locally, so the
calendar adapter returns its two fixed entries for any address — which exercises the
whole import path without a public feed.

| Step | Result |
|---|---|
| Sign up, sign in, `GET /` | `307 → /onboarding` |
| `/onboarding` renders step 1 | All three providers; **no** "1-click OAuth" anywhere |
| `POST /api/personal/calendars` | `201`, status `active` |
| The first import | Landed after **~18 s** — the tick picked it up well inside the 75 s bound |
| The imported events | Both carry `calendar_connection_id` = the new connection; the user's own events carry `null` |
| Advance to step 2 | `200`, `current_step: 2`; the page resumes there, with the API's ten chips (no "Music", no "Food & dining") |
| Two interests saved | `200` |
| A fourth pick | `422 too_many_interests` — the API refuses it even though the UI prevents it |
| Advance to step 3, save `07:30` / `America/New_York` | `200`, stored |
| Finish | `completed: true`, the digest and interests persisted |
| `GET /` | `200`, the placeholder home, with both imported events on it |
| A finished user at `/onboarding` | `307 → /` |
| **Skip all** from step 1 (second account) | `completed: true`, default digest `09:00 UTC`, no interests; `/` shows "Your Pulse is being prepared." and **no** digest cards |
| **Skip each step** in turn (third account) | step 1 → 2 → 3 → completed |

### A defect the live run found

Returning to step 1 with a calendar already connected said *"Connected. Nothing upcoming
in that calendar yet."* over a connection that had just imported two events. The page
hands the step a connection, not its events, and the component only knew about events it
had watched arrive. It now reads that connection's events on mount. Three tests cover it:
the events show, the count is right, and a genuinely empty calendar still says so.

This is the kind of defect only a run-through finds: every unit test passed, because each
one set up the state it was asserting about.

### Notes

- **Node 24** is required for the suite (`.nvmrc`); under Node 20 every Vitest file fails
  to start inside undici.
- **No dependency was added.**
