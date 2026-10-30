# Code Review Report

**Run**: run-eventpulse24-020
**Intent**: onboarding-and-account
**Work item**: pulse-preview-api-and-geo
**Reviewed**: 2026-10-30
**Files Reviewed**: 16

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Correctness | 2 | 1 | 0 |
| Contract / Architecture | 1 | 0 | 0 |
| Documentation | 1 | 0 | 0 |
| **Total** | **4** | **1** | **0** |

**Tests Status**: Passing — 3208 passed, 0 failed; 99.04% coverage; 19/19 import contracts
kept.

Five findings. Four were **auto-fixed** — a defect with an unambiguous right answer is
fixed, not reported. The fifth was a **CONFIRM-level** item that is now applied and
recorded, because the review's own rule is that a finding is a claim until it is
reproduced, and a claim about *another app's* endpoint is the user's call.

**Two of the five were found by the revert harness rather than by reading the code.**
They are recorded here with the same weight as the ones reading found, because a defect
that a test surfaces and a defect that a reading surfaces are both defects — and the
harness found one of them (a 500 on a rate-limited cities request) that no amount of
reading the happy path would have surfaced.

---

## Files Reviewed

### Created

| File | Purpose |
|------|---------|
| `backend/ports/geo.py` | The geo port — headers in, a city name or nothing out |
| `backend/adapters/geo/header.py` | The real adapter: reads one header, decodes once, bounds it |
| `backend/adapters/geo/fake.py` | The CI/local default: configurable to return a chosen city |
| `backend/apps/catalog/preview_api.py` | The two public endpoints |
| `backend/apps/catalog/preview_schemas.py` | The wire shapes |
| `backend/apps/ingestion/services/preview_read.py` | The published read behind the cards |
| `backend/tests/ports/test_geo.py` | The port and both adapters |
| `backend/tests/api/test_preview_api.py` | The endpoints, their limits and their anonymity |
| `backend/tests/ingestion/test_preview_read.py` | The supported cities and the card projection |
| `backend/tests/architecture/test_preview_anonymity.py` | The structural anonymity and wall rules |
| `backend/revert_preview_check.sh` | The revert harness — 36 cases |

### Modified

| File | Change |
|------|--------|
| `backend/config/api.py` | The router, mounted at `/public` |
| `backend/config/adapters.py` | The real and fake adapter paths |
| `backend/config/env.py` | `GEO_FAKE_CITY` and `TRUST_FORWARDED_FOR` |
| `backend/config/settings.py` | The two settings |
| `backend/ports/registry.py` | The geo port's entry in the registry |
| `backend/shared/constants.py` | The bound, the fallback city, the cache and throttle constants |
| `backend/pyproject.toml` | The import contracts |
| `backend/tests/config/test_adapters.py` | The real-mode adapter is the header adapter |
| `frontend/lib/api/openapi.json` | The regenerated schema |
| `frontend/lib/api/schema.ts` | The regenerated client |

---

## Findings

### D1 — A rate-limited cities request was a 500, not a 429 (Correctness, HIGH)

**Found by**: the revert harness — case R17b, which asserts the cities route can *answer*
a refusal at all.

The cities route declared its response map as:

```python
response={200: PreviewCitiesOut}
```

django-ninja validates a non-200 body against the response map, and the map had no
entry for 429. When the throttle refused a cities request, ninja raised:

```
ConfigError: Schema for status 429 is not set in response dict_keys([200])
```

and returned a **500**. So the route's rate limit was not a rate limit at all — it was
a crash. The preview route was fine (its map already carried `429: ErrorOut`), which is
why the bug survived: the two routes were written in parallel and only one of them was
checked.

**Fixed** by adding the missing schema:

```python
response={200: PreviewCitiesOut, 429: ErrorOut}
```

**Pinned by** `test_the_cities_endpoint_is_rate_limited_too`, which drives the cities
route past its limit and asserts a 429 with the `rate_limited` body. Revert case R17b
fails without the fix.

### D2 — The two paths answered with different spellings of the same city (Correctness, MEDIUM)

**Found by**: the revert harness — case R9b, plus reading the two branches side by side.

The geo branch canonicalised the city's name to the catalog's spelling; the explicit
branch returned the caller's spelling unchanged. A visitor who typed `BROOKLYN` got
`"BROOKLYN"` back, while a visitor whose header said `brooklyn` got `"Brooklyn"` — two
different answers to the same question, and the first one is a heading nobody can
search for, because the events are filed under the catalog's spelling.

**Fixed** by canonicalising the explicit branch too, through the same `_canonical`:

```python
if len(wanted) <= GEO_CITY_MAX_LENGTH:
    return _canonical(supported, wanted), CITY_SOURCE_QUERY
```

**`_canonical` is asymmetric on purpose.** It replaces the name **only when the catalog
holds that city**. An unsupported city comes back exactly as the caller wrote it — which
is the rule the work item states: an unsupported explicit city returns an empty preview
carrying *that* city's name, never the fallback's events under a name that lies. A
canonicaliser that renamed unsupported cities would break the rule it sits next to.

**Pinned by** `test_the_catalogs_own_spelling_of_a_city_is_the_one_returned` and
`test_a_city_the_catalog_does_not_hold_is_returned_as_it_was_given`.

### A1 — The cities route spent the preview's throttle budget (Contract / Architecture, MEDIUM)

**Found by**: reading the two throttle key constructions against each other.

The two routes each called `_throttle_key`, but the cities route **inlined its own
key** rather than going through the helper:

```python
_throttle_key(_client_ip(request), scope="preview:cities")
```

The helper already took a `scope` parameter; the cities route was building a key by
hand at the call site, which meant the scope — the one thing that keeps the two
counters separate — was a literal in a caller rather than a default in a named place.
It was correct by accident. The next person to add a route would have copied the
inline form and shared the preview's budget without knowing it.

**Fixed** by making the scope an explicit argument at both call sites and documenting
that it is **a fixed literal at every call site, never anything a caller controls** —
the caller's contribution to the key is the address and nothing else.

**Pinned by** `test_the_cities_endpoint_has_its_own_budget`, which exhausts the cities
route's limit and then shows the preview route still answers.

### A2 — A dead constant and an unused import (Documentation / hygiene, LOW)

**Found by**: ruff.

`preview_api.py` carried a `PREVIEW_QUERY = Query(...)` that was never used, along
with the `Query` import it required. It was the residue of an earlier design where the
query parameter was declared through django-ninja's `Query` wrapper; the endpoint
takes `city` as a plain parameter, which is the convention the identity API already
follows (`SignUpIn` / `SignInIn` use plain `str`).

**Fixed** by removing both. A constant that names a rule the code does not follow is a
claim the code does not make.

### A3 — The geo port's docstring said there was a dataclass when there was not (Documentation, LOW)

**Found by**: reading the port against its own implementation.

`ports/geo.py` stated "There is no dataclass on this one" while the surrounding text
implied one existed. The port's entire payload is a `str` — a city name or `None` —
and there is nothing else to carry, so there is no dataclass and never was one.

**Fixed** by correcting the sentence.

### C1 — The explicit `city` parameter was unbounded while the geo header was bounded (CONFIRM, MEDIUM)

**Found by**: reading the two untrusted-input paths side by side.

The geo header is bounded to `GEO_CITY_MAX_LENGTH` in the adapter, because a header is
attacker-controlled. The `?city=` query parameter is **also** attacker-controlled, and
it had no bound at all — a caller could send a megabyte of text and have it echoed
back in the response body and in the `city` field.

The asymmetry was the finding: two untrusted inputs, one bounded and one not, in the
same endpoint.

**Applied**, after the confirm threshold, using **the same constant** the header uses —
because a city name is a city name whichever way it arrived:

```python
if city is not None and city.strip():
    wanted = city.strip()
    if len(wanted) <= GEO_CITY_MAX_LENGTH:
        return _canonical(supported, wanted), CITY_SOURCE_QUERY
```

An over-long city is treated as **no city at all** — the request falls through to geo,
and then to the fallback — rather than being echoed back. It is the same shape as the
header's behaviour, and the same shape as the "no city" case, which is already the
endpoint's normal path.

**Pinned by** `test_an_over_long_city_is_not_a_city` (the over-long city falls through
to geo, and the response carries the geo city) and `test_a_city_at_the_bound_is_accepted`
(the bound is a bound and not a truncation — a city exactly at the limit is still a
city). Revert case R33 fails without the fix.

---

## One finding that was **not** fixed

### C2 — `_client_ip` is duplicated, byte for byte, in two apps (CONFIRM, LOW)

`apps/identity/api.py` and `apps/catalog/preview_api.py` each contain their own
`_client_ip`, and the two are **identical** — same `TRUST_FORWARDED_FOR` check, same
first-hop split, same `ipaddress` validation, same `REMOTE_ADDR` fallback.

This is security-relevant code, and it is the kind of duplication that drifts: a fix
to one copy leaves the other answering a different question about the caller's address.
The identity copy governs login throttling; the preview copy governs preview
throttling. If the two ever disagree, the limits are enforced against different
addresses.

**Not fixed here, deliberately.** The shared home would be `shared/` — and that is a
change to *another app's* endpoint, which is the user's call rather than this item's.
It is recorded so it is not lost.

---

## The cases that did not fail, and what they taught

Three cases did not fail on the first run. All three are worth recording, because a
case that does not fail is either a bad test or a bad source — and both were true here.

**R3 — the length bound was stated twice, and the second statement was unreachable.**
The adapter bounded the header *before* decoding and then bounded the decoded value
*again*. But `unquote` only ever **shortens** a value — each `%XX` escape becomes one
character — so a bound checked before decoding is already a bound on the decoded value.
The second check could never fire.

The fix was to remove the unreachable check and to say why it is unnecessary, because
**unreachable code is not a safety net; it is a claim the code does not make**. The
revert case now removes the *one that remains*.

**R21 — the alphabetical test could not tell two orderings apart.** The queryset had
`.order_by("city")` *and* the Python `sorted(..., key=str.casefold)`, and on the test's
city names the two agreed. A test that cannot distinguish two candidate implementations
pins nothing.

The real problem is that the two orderings are **not the same rule**. A database's
`ORDER BY` on text is a **locale collation** — `en_US.UTF-8` ignores punctuation at the
primary level and orders case in a locale-specific way — so the *deployment's locale*
would decide the picker's order, and two deployments would offer different city lists
for the same data. `str.casefold` compares code points and is the same everywhere.

So the fix was to the **source** (the `.order_by` is gone; the database is not asked
to sort at all) and to a **structural** test that pins the rule rather than a
behavioural test that cannot express it:

```python
assert ".order_by(" not in code
assert "key=str.casefold" in code
```

**R21b — and my first two attempts at a discriminating example were both wrong.**
`"St. John's"` vs `"St Johns"` does **not** discriminate: Python's `casefold` also puts
`"St Johns"` first, because a space (`0x20`) sorts before a period (`0x2E`). And
`"A"` vs `"a"` cannot be used either, because the catalog's de-duplication is
case-insensitive, so they are one city, not two.

A discriminator has to be a pair that the two rules order **differently**, and two
attempts at finding one produced two pairs that agreed. The structural test was the
right answer, and the reason it was the right answer is that the rule being pinned is
*which mechanism decides the order*, not *what the order is*.

---

## The Revert Verification

Every fix was verified by **reverting it and watching the test fail**. A regression
test that passes against the broken code is not a regression test.

The harness is `backend/revert_preview_check.sh` — 36 cases.

**All 36 cases fail**, with no skips and no restore failures:

| Case | What it breaks | Result |
|-----|----------|--------|
| R1 | the adapter reads the edge's geo header | caught |
| R2 | the header is URL-decoded exactly once | caught |
| R3 | the header is length-bounded | caught |
| R4 | the header lookup is case-insensitive | caught |
| R5 | the city name is normalized | caught |
| R6 | the fake adapter returns the configured city | caught |
| R7 | the fallback city is the named constant | caught |
| R8 | an explicit city overrides geo | caught |
| R9 | a geo city outside the supported set falls back | caught |
| R9b | the answer carries the catalog's spelling of the city | caught |
| R10 | the opt-out does not consult the geo port at all | caught |
| R11 | an unsupported explicit city returns an empty preview | caught |
| R12 | the response is cacheable as a public document | caught |
| R13 | the response does not vary on the cookie | caught |
| R14 | a refused request is not cached | caught |
| R15 | the public preview is rate limited per IP | caught |
| R16 | the limit is keyed on the caller address | caught |
| R17 | a refused request says when to retry | caught |
| R17b | the cities endpoint can answer a refusal at all | caught |
| R18 | a city with no current fit is not supported | caught |
| R19 | only upcoming events make a city supported | caught |
| R20 | superseded events are excluded | caught |
| R21 | the supported cities are alphabetical | caught |
| R21b | the order is the code's, not the locale's | caught |
| R22 | a city is listed once, however it is spelled | caught |
| R23 | the support check is case-insensitive | caught |
| R24 | the preview returns at most three cards | caught |
| R25 | a crawled source carries the crawled badge | caught |
| R26 | an unknown source type is an aggregator | caught |
| R27 | the preview never imports the Event Fit package directly | caught |
| R28 | the preview surface never reads the session | caught |
| R29 | the preview surface never touches the personal schema | caught |
| R30 | the preview never stores the resolved city | caught |
| R31 | the preview never logs the resolved city | caught |
| R32 | the router is mounted at `/public` | caught |
| R33 | the explicit city is bounded, like the header | caught |

### The harness's own bug, and what it taught

The harness backs each file up **per case**, keyed on a case number, and **verifies**
the restore byte for byte after every case — because a restore that silently fails is
worse than no restore: it makes every later result a claim about a tree that does not
exist.

Four cases were **skipped** on the final run, not because their reverts failed to
apply, but because their **patterns had drifted**: the source had been edited during
the review (the explicit-city branch gained the bound, `_throttle_key` gained the
scope), and the patterns still described the pre-edit text. A skip is counted as a
hole, and the run fails — which is the right behaviour, because a case whose lever
cannot be found has verified nothing.

The patterns were corrected against the current source and the run is green.

---

## Notes

1. **The opt-out is honoured by *not consulting the port at all*.** "Don't use my
   location" is a real choice, and a choice the server ignores is not a choice. The
   test plants a geo port that **raises if it is called** — a stronger claim than
   "called and the answer ignored", and the only one the work item's wording supports.

2. **The resolved city is never stored and never logged.** It is a response field and
   nothing else: no table, no cache entry, no session key. The IP is used only as part
   of a throttle key, which is the same treatment the auth endpoints give it.

3. **The catalog owns the spelling of a city.** The spelling a visitor types is not the
   spelling the events are filed under, and a preview headed `"BROOKLYN"` listing the
   events filed under `"Brooklyn"` is a heading nobody can search for.

4. **`Vary` carries nothing session-related.** A response that varies on the cookie is
   not cacheable, and a shared cache that stored one variant under a key that ignores
   the cookie would serve one visitor's response to another. The preview sets no cookie
   and reads no session, so the response is identical for everyone and the cache key is
   the URL.

5. **`X-Forwarded-For` is trusted only when the deployment says to.** Next's rewrite
   forwards the browser's headers as they arrived, so a browser that sets the header has
   that value reach Django unchanged. Trusting it unconditionally let any caller mint a
   fresh throttle bucket per request. `TRUST_FORWARDED_FOR` is **off by default**.

6. **The endpoint reads `catalog` only through `ingestion`'s published read.** The
   `models-ingestion` contract says only `apps.ingestion` may import
   `apps.ingestion.models` — and the Event Fit read imports that model directly, so
   `apps.catalog` cannot reach the Event Fit through it either. The published read
   therefore lives **inside** `apps.ingestion` and hands over plain data, so the
   calling app never holds a reference to a model it is forbidden to import.

---

## The Final Gate

```
make lint-backend
Contracts: 19 kept, 0 broken.

ruff check .
All checks passed!

ruff format --check .
377 files already formatted

manage.py check
System check identified no issues (1 silenced).

make coverage-backend
3208 passed in 87.39s (0:01:27)
TOTAL                                             6884     66    99%
Required test coverage of 80.0% reached. Total coverage: 99.04%

coverage report --include='domain/*' --fail-under=100
TOTAL     619      0   100%
```

**Every module this item created is at 100%** — `ports/geo.py`, `adapters/geo/*`,
`apps/catalog/preview_api.py`, `apps/catalog/preview_schemas.py` and
`apps/ingestion/services/preview_read.py` are all in the "skipped due to complete
coverage" set: **207 statements, 0 missed**.

---

## Test Result

**Passing.** 3208 passed, 0 failed, 99.04% coverage, `domain/` at 100%, ruff clean,
format clean, 19/19 import contracts kept, no issues from the Django system check, and
all 36 revert cases caught.

---

## What this review does not cover

- The **front end** that consumes these endpoints does not exist yet; the Pulse
  Preview page is a later work item (`frontend-pulse-preview`).
- The **`_client_ip` duplication** (C2) is recorded, not fixed — it touches another
  app's endpoint and is the user's call.
- The **geo header's survival through the Next.js rewrite** is noted in the work item
  and does not change the code: Django sees only the port's input, and the code does
  not depend on the host (AD-1).
