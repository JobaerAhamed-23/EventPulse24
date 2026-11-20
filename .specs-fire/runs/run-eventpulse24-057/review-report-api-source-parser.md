---
run: run-eventpulse24-057
work_item: api-source-parser
intent: city-picker-and-auto-collection
generated: 2026-11-20
status: complete
---

# Code Review: A parser for api-method sources

## Files Reviewed

| File | Change |
|------|--------|
| `backend/apps/ingestion/parsers/providers.py` | New — host→reader dispatch |
| `backend/apps/ingestion/parsers/ticketmaster.py` | New — Discovery v2 reader |
| `backend/apps/ingestion/services/provider_keys.py` | New — key added at fetch time, stripped on the way back |
| `backend/apps/ingestion/parsers/__init__.py` | `PARSERS["api"]`; a note on why `partnership`/`crawl` are absent |
| `backend/apps/ingestion/services/ingest_source.py` | `authorized_url` before the fetch, `strip_key` after it |
| `backend/config/env.py`, `backend/config/settings.py`, `.env.example` | `TICKETMASTER_API_KEY` |
| `backend/tests/fixtures/sources/ticketmaster-*.json` | New — 4 recorded fixtures |
| 3 new + 4 edited test files | +74 tests |

## Project Tooling

| Tool | Result |
|------|--------|
| `ruff check .` | All checks passed |
| `ruff format --check` | Every file this work touched is clean |
| `lint-imports` | 21 contracts kept, 0 broken |
| `tests/architecture` | 1091 passed |
| `manage.py check` | No issues |
| `pytest` (full) | 7875 passed, 0 failed |
| Coverage | New modules 100%; `domain/` 100%; overall 97.43% |

## Findings

### 1. [Architecture] The dispatcher's filename enrolled it in the AD-5 HTTP surface — FIXED

**File**: `apps/ingestion/parsers/providers.py` (was `api.py`)

The obvious name for the `api` method's parser is `api.py`. But `tests/architecture`
discovers the AD-5 surface **by filename shape** — anything under `apps/` ending in
`admin.py`, `api.py` or `*_api.py` is an HTTP router that may not write to the database
directly — and both `test_no_direct_writes.py` and `test_digest_composition_separation.py`
assert the discovered set against a hand-maintained list. A parser landed in that set, and
two architecture tests failed with "27 != 26" and an extra module.

**The guard was right and the name was wrong.** The alternative was teaching the discovery
to skip `parsers/`, which would have carved a hole in a rule whose whole value is that it
has no holes: a file exempted from the surface list is exempt from AD-5, and nothing else
would catch it. Renamed to `providers.py`, which also describes it better — it is the
host→provider dispatch, not "the API".

The module docstring now records why it is not called `api.py`, so the next person does not
rename it back.

**Risk**: none. A rename plus two import sites, before anything shipped.

### 2. [Documentation] An e2e test's stated premise became false — FIXED

**File**: `tests/e2e/test_state_detection_window.py` (docstring only)

That file explains at length why it proves two halves of a scenario separately rather than
together: "No high-priority method has a parser yet — `api` and `partnership` have no
adapter in this codebase (`PARSERS` holds `jsonld`, `rss`, `ics` and `email_ics`). So a
high-priority source cannot be ingested today, and a single test that drove both halves at
once would have to fake the parser."

This item made that false. The test still passes and its structure is still defensible, but
its *justification* is gone — and a stale justification is worse than none, because the
next person reads it as a current constraint.

Rewritten to say what was true when it was written, that `api-source-parser` closed it,
that unifying the halves is now possible and merely not done, and that `partnership` and
`crawl` remain parserless deliberately. **No assertion changed.**

### 3. [Correctness] `offsale` is not `sold_out` — DECIDED, NOT CHANGED

**File**: `apps/ingestion/parsers/ticketmaster.py`

Tempting mapping, and wrong. Ticketmaster's `offsale` means "outside the public on-sale
window", which covers an event that has **not gone on sale yet** as much as one that has
sold out, and presale inventory can exist during it. Reading it as `sold_out` would put a
false claim on the event page for every not-yet-on-sale event.

`sold_out` stays `False` and the catalog says only what the provider actually claimed.
Recorded in the `STATUS` docstring and pinned by `test_offsale_is_never_read_as_sold_out`.

## Deliberately Not Changed

- **An event with no provider id is skipped, not given a derived one.** `parsers/text.py`
  has `derived_id` for exactly this, and the other parsers use it. Here it would be wrong:
  a derived id is a hash of the item's own fields, so the next run's slightly-edited title
  mints a *different* id and the event duplicates. AC 10 asks for re-ingests to dedupe, and
  an event the provider will not name cannot be followed. It is counted `no_source_event_id`.
- **The reader returns no `end`.** Discovery v2's search response carries no reliable end
  time. Inventing one from a duration or a default length would put a wrong end on every
  event; `domain.conflict` compares intervals, so a fabricated end would create false
  conflicts in a reader's timeline.
- **`strip_key` runs on every fetch result, not only the keyed ones.** It is a no-op for a
  non-provider host. The point is that no stored URL carries a key *however it got there* —
  including a provider echoing the parameter through its own redirect.
- **No key means the URL is fetched unchanged and the provider answers 401.** The
  alternative — refusing to fetch — hides the misconfiguration inside this service. A 401
  lands in `last_error_code` where an editor can see it. `city-provisioning-service` is the
  right place to refuse to *create* an API source with no key configured, and that is noted
  for item 7.
- **`TICKETMASTER_API_KEY` is optional with an empty default**, unlike `stripe_api_key` and
  `voyage_api_key`, which abort the boot when missing. Every deployment bills and embeds;
  no deployment today has an API source. Making it required would break every existing
  environment to guard a feature none of them use.

## Security

The one real surface here, and it got the attention:

- **The key never persists.** Not in `Source.url`, not in the `register_source` audit row
  (retained 24 months under AD-5), not in `fetched_url`. Added for one call, stripped from
  whatever comes back. Four tests.
- **The key never logs.** `credential=True` is passed on the keyed fetch — the flag
  `SourceFetchPort` documents for the calendar address whose path *is* the token — so the
  transport stops httpx writing the request URL.
- **Host matching is exact, in both places that matter.** `providers.READERS` decides whose
  parser reads a document; `provider_keys.PROVIDER_KEYS` decides who receives our API key.
  A suffix match in the second would send the key to `app.ticketmaster.com.evil.test`. Both
  are literal dicts keyed on the full lowercase host, with tests for the lookalikes.
- **Untrusted input throughout.** The response is an attacker-influenced document if DNS or
  TLS is ever subverted, so the reader indexes nothing without checking the type, caps every
  text field at the column size, and passes URLs through `http_url`, which rejects anything
  that is not absolute http(s) — `test_the_canonical_url_is_kept_when_absolute_and_dropped_otherwise`
  pins a `javascript:` URL being dropped.
- **No fixture carries a credential**, asserted by a scan whose own ability to fail is
  tested.

## Architecture

Clean. The parser package keeps its contract — bytes in, candidates out, never an
exception, no database, no network, no LLM — and `provider_keys` reads `settings`, never
the environment, which is the direction the `layers` contract requires. FR-17's hierarchy
is not widened: `partnership` and `crawl` are still unregistered, now with a comment at the
registration site saying why, so the next person does not add them as a tidy-up.

The import contracts and the full architecture suite pass, including the two tests that
caught finding 1.

## Summary

| | Count |
|---|---|
| Fixed | 2 (module rename out of the AD-5 surface; a false premise in an e2e docstring) |
| Decided and documented | 1 (`offsale` is not `sold_out`) |
| Pending suggestions | 0 |

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
