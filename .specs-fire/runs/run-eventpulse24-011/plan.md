---
run: run-eventpulse24-011
work_item: event-identity-and-tz-domain
intent: event-catalog-ingestion
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at: 2026-10-28T08:46:25Z
revision: 2 (plan review: P1–P4 recommendations, 13 must-fix, 5 should-fix applied)
---

# Implementation Plan: Event Identity & Timezone Domain Logic

## Approach

> **Needs your approval:** the [departures from the ACs, the PRD and the design](#departures-needing-approval) table. Everything else below applies your review.

This item is pure, stdlib-only decision logic in `backend/domain/`. It has no Django and no I/O, and must reach 100% coverage.

| Module | Responsibility |
|---|---|
| `domain/dedup.py` | Title and venue fingerprints (versioned), URL normalization, Jaccard, rules (a)/(b)/(c), `resolve()`, advisory-lock keys, `ics_item_id()` |
| `domain/lifecycle.py` | Postponement measured from the **original** start; the change classifier |
| `domain/timezones.py` | Zone validation and canonicalization; tier resolution; DST detection; start and end conversion |
| `domain/confidence.py` | `tz_gate()`, `extraction_gate()`, `combine_gates()` (the stricter gate wins) |
| `domain/errors.py` | Adds `InvalidTimezoneError(ValidationError)`, code `invalid_timezone` |

**Constants:** every threshold, score and cap lives in `shared/constants.py`, as a two-decimal `Decimal` (or a `Fraction` or `timedelta`). The domain receives plain values and frozen dataclasses: no models. `series_id()` already exists in `shared/ids.py` and is tested in `tests/shared/test_ids.py`; the domain doesn't import it, because the parsers and the pipeline are its callers.

### P1–P4, as you decided

- **P1. Rule (c) is accepted.** It matches only on equal normalized URLs **and** equal instants. On top of that:
  - Rules (b) and (c) **never match an Event that already has an item bound from the candidate's own source**. That stops a venue feed that links every item to one calendar page from merging different rooms at the same time.
  - Instants are **truncated to whole seconds** before any comparison.
- **P2 is changed:**
  - **UTC instants (`Z` or `+00:00`)** are absolute. They are never compared against a zone's offset and never produce `Etc/GMT`.
  - **A non-zero whole-hour offset with no zone and no venue tz** maps to `Etc/GMT∓N`, capped at **0.85** (publishes, flagged). The valid range is −12 to +14 hours.
  - **A non-whole-hour or out-of-range offset** is rejected (`offset_without_iana_zone`).
- **P3 is fixed:**
  - Conflicts go to review:
    - a source zone vs a disagreeing offset (A2)
    - a source zone vs a disagreeing venue tz (new row A3)
    - an offset vs a disagreeing venue tz (B2)

    Each is scored **0.60**, so it goes `in_review`, and the explicit zone wins for the instant.
  - Every score and cap is a `Decimal` in `shared/constants.py`, and a test checks that each one lands in its intended gate band.
- **P4 is accepted.** `ChangeKind.REINSTATED` is domain-only. A test requires every `ChangeKind` to map to a model `Kind` or to appear in an explicit `NOT_YET_STORED` set, so item 6 can't miss it.

### Timezone resolution table

**Inputs:**
- `start`: a naive local time, or an aware time with an offset
- `source_zone`: the source's zone name, if any
- `venue_tz`: the venue's tz, if known

**Output:**
- a `TzResolution` with `tier`, `zone`, `start_utc`, `end_utc`, `start_time_local`, `confidence` and `reason`
- or a `TzRejection` with a `reason`

"Agree" means the zone's `utcoffset()` at the instant equals the given offset. All scores are named `Decimal` constants.

| Row | Inputs | Tier | Zone / instant | Score | Gate |
|---|---|---|---|---|---|
| A1 | Valid `source_zone`; naive, a UTC instant, or an agreeing offset; venue tz absent or agreeing | `full` | source zone | 1.00 | publish |
| A2 | Valid `source_zone`; non-UTC offset **disagrees** | `full` | the wall-clock time read in the **source zone** | 0.60 | in_review |
| A3 | Valid `source_zone`; known venue tz **disagrees** at the instant | `full` | source zone | 0.60 | in_review |
| U1 | UTC instant; no source zone; venue tz known | `full` | venue tz (instant exact) | 1.00 | publish |
| U2 | UTC instant; no source zone; no venue tz | `full` | `UTC` | 0.85 | publish, flagged |
| B1 | Non-UTC offset; no source zone; venue tz agrees | `full` | venue tz | 1.00 | publish |
| B2 | Non-UTC offset; no source zone; venue tz **disagrees** | `full` | the wall-clock time read in the **venue tz** | 0.60 | in_review |
| B3 | Non-UTC whole-hour offset in [−12, +14]; no venue tz | `full` | `Etc/GMT∓N` (instant exact) | 0.85 | publish, flagged |
| B4 | Non-UTC offset that is not a whole hour or out of range; no venue tz | `none` | — | — | reject `offset_without_iana_zone` |
| C1 | Naive; no valid source zone; venue tz known | `partial` | venue tz | 0.95 | publish |
| C2 | Naive; nothing known | `none` | — | — | reject `tz_unresolvable` |

**DST**

DST caps apply **only when a naive wall-clock time is read in a zone** (A1-naive, A2, B2, C1). Detection works as follows:
1. Build the time with `fold=0` and with `fold=1`.
2. If their `utcoffset()` values differ, round-trip the `fold=0` result through UTC.
   - If it comes back to a different wall-clock time, that is a **gap** (cap **0.65**, so `in_review`).
   - Otherwise it is a **fold** (take `fold=0`, cap **0.80**, so flagged).

The final score is the minimum of the row's score and any cap.

**End time:** converted with the **same zone and policy**. Its cap also lowers the final score. The parsers have already rolled overnight end times forward.

**`start_time_local`:** this is **derived**: `start_utc` read in `zone`, at second precision, with no offset. So `start_time_local` plus `start_time_tz` always converts back to `start_time_utc`. The text exactly as the source wrote it stays in `ExtractedRecord.payload`.

**Zone validity**, via `canonical_zone(name) -> str | None`:
- An unknown name is caught as `ZoneInfoNotFoundError`, `ValueError` or `OSError`.
- `UTC`, `Etc/UTC`, `Etc/GMT`, `Etc/GMT±0` and `Etc/Zulu` all canonicalize to `UTC`.
- Otherwise the name must contain `/`, with an area in {Africa, America, Antarctica, Arctic, Asia, Atlantic, Australia, Europe, Indian, Pacific}, or be `Etc/GMT±N` with N in range. That rejects `EST`, `localtime`, `Factory` and `posixrules`.
- `US/*` and `Canada/*` aliases canonicalize to their targets through an explicit, tested table.
- Other in-area legacy links, such as `Asia/Calcutta`, are kept as given. That is harmless for identity, which compares instants, not names.
- An invalid `source_zone` is treated as absent. An invalid `venue_tz` raises `InvalidTimezoneError`, because the registry validates on write.

**Pinned tz database:**
- `tzdata==2026.5` becomes a direct dependency (today it is only installed transitively via kombu).
- `ConfigConfig.ready()` calls `zoneinfo.reset_tzpath(to=())`, so every process uses the pinned package and never the OS database. Dev, CI and production then compute the same instants.

### Identity

- **Title fingerprint** (`v1:`). The steps are:
  1. NFKC, then casefold.
  2. Strip combining marks **only from Latin, Greek and Cyrillic base letters** (so "Café" equals "Cafe", while ド stays ド), then recompose with NFC.
  3. Split on anything that isn't a letter or a digit.
  4. Turn runs of Han, Hiragana, Katakana and Thai into overlapping character **bigrams**. A run of one character becomes a unigram.
  5. Separate the **content** tokens from the **stop** tokens, using a small fixed English list (a, an, the, and, or, of, at, in, on, for, with, to, by, from, &).

  The stored form is `v1:<sorted content tokens>|<sorted stop tokens>`, capped at 512 characters on a token boundary.
- **Jaccard:**
  - It compares content sets.
  - If **either** side's content set is empty, it compares content ∪ stop for **both** sides, which makes it symmetric.
  - Different version tags give 0, and two empty sets give 0.
  - It uses `Fraction`, so 4/5 is exact.
- **Venue fingerprint:** `v1:` + `sha256(name|city|COUNTRY)`, so Portland, Oregon and Portland, Maine differ. An **empty name gives `""`**, and an empty fingerprint never matches.
- **URL normalization:**
  - **Rejected, giving `""` (never matches):**
    - malformed input (`ValueError` from `urlsplit` or `.port`)
    - an IDNA failure
    - a scheme other than `http`/`https`
  - **Treated as the same URL:** the scheme is set to `https`, so http and https match. A leading `www.` is stripped from the host.
  - **Cleaned up:**
    - the host is lowercased and IDNA-encoded
    - userinfo and the default port are dropped
    - percent-encoding is uppercased
    - an empty path becomes `/`, and a trailing `/` is stripped except from the root
  - **Query:** `utm_*` (case-insensitive), `fbclid` and `gclid` are dropped; the remaining parameters are sorted, and blank values are kept.
  - **Fragment:** dropped, unless it is a route fragment (`#/…` or `#!…`).
- **`resolve(candidate, bound_event_id, live)`:**
  - `live` arrives with superseded Events already filtered out. The domain also ignores any marked superseded.
  - **Rule (a)** comes from the `ExtractedRecord` binding (`bound_event_id`, design D2), never from an Event's origin fields. When the item is bound, the result is `Match(bound, A)`, and any (b)/(c) match to *another* Event becomes `review_signals` (a possible duplicate), not `Ambiguous`.
  - **When the item is not bound:**
    - (b)/(c) are evaluated, skipping Events bound to the candidate's source.
    - 0 matching Events gives `New`. 1 gives `Match(event, rule)`, reporting the rule by fixed priority b > c. More than 1 distinct Event gives `Ambiguous`.
- **Lock keys:** `blake2b(digest_size=8, person=b"ep-ident")` over `"<rule>:<parts>"`, read as a signed 64-bit integer. Never `hash()`, which is salted per process.
  - Keys come from the source item, venue + instant, and URL + instant. **Empty parts are skipped**, and the keys are returned **sorted**.
  - The pipeline (item 6) commits **one transaction per item**, so transaction-scoped locks never span items. If it ever batches several items in one transaction, it must take the union of their keys in global sorted order up front. That becomes an AC on item 6.
- **`ics_item_id(uid, recurrence_start_utc)`** returns `uid` alone, or `uid#<ISO-8601 UTC>` for a recurring instance. Weekly instances that reuse one UID therefore stay distinct under rule (a). This becomes an AC on item 4.

### Lifecycle

- **`classify_time_move(original_start_utc, new_start_utc)`:**
  - It is measured from the **original** start (AD-4), so drift across several moves still supersedes at ±30 days.
  - Both values must be aware (`TypeError` otherwise) and are compared in UTC.
  - Exactly ±30 days keeps the Event.
- **Original start:** the Event has no column for it. Item 6 must supply it, either as a new `Event.original_start_utc` column or from `state_history`. That becomes an AC on item 6.
- **`classify_change(stored, incoming, original_start_utc)`:**
  - It returns `None`, or `Change(kinds, fields, is_lifecycle)` with `kinds` ordered by precedence: **cancelled > superseded > reinstated > postponed > time_moved > sold_out > detail_changed**.
  - Every applicable kind is kept, so a time move plus sold out yields both.
  - Specific cases:
    - **tz-only change:** `detail_changed`, lifecycle
    - **end-only change:** `time_moved`
    - **sold out turning back off:** `sold_out`, with the direction in `fields`
    - **postponed → scheduled at the same start:** `reinstated`; at a different start: `time_moved`
    - **cancelled → scheduled:** `reinstated`
  - A `stored` that is already superseded raises `ValueError` (a programming error).
- **Lifecycle field parity:** a Django-side test asserts that the domain's lifecycle field set maps onto `Event.LIFECYCLE_FIELDS`.

### Gates

- `tz_gate(c)` and `extraction_gate(c)` take a **`Decimal` with exactly two decimal places in [0, 1]**. A float, `int`, `bool`, `None`, NaN, an out-of-range value or extra precision raises `TypeError`/`ValueError`.
- `extraction_gate`: below 0.50 rejects, below 0.70 goes `in_review`, otherwise publishes (AD-8).
- `combine_gates(*gates)` returns the strictest: reject > in_review > publish flagged > publish.

### Departures needing approval

| # | Source | Says | This plan |
|---|---|---|---|
| 1 | Work item AC, FR-60 | A `full`-tier source gives confidence 1.0 | Rows A2, A3 and B2 give 0.60; U2 and B3 give 0.85; DST caps apply to naive times; B4 rejects |
| 2 | Work item AC | `partial`: "a computed confidence" | Fixed at 0.95 (C1), with DST caps |
| 3 | PRD §3 identity tuple | `start_time_with_tz` | Rule (b) compares UTC instants truncated to seconds. The same instant under a different zone name is a match. |
| 4 | FR-15 rule (c) | Same canonical URL | Same normalized URL **and** same instant (P1); never against an Event already bound from the candidate's source |
| 5 | Design D8 | `start_time_local` is the source's wall-clock time as written, normalized | Derived from `start_utc` and `zone`, so it always converts back. The as-written text stays in `payload`. This amends D8. |
| 6 | Design D14 / model | `venue_fingerprint` is opaque | Defined as `v1:` + sha256, including `country_code`; empty when there's no venue name |
| 7 | Tech stack | Uses the OS tz database | Pinned `tzdata==2026.5` as a direct dependency, with `reset_tzpath(to=())` |
| 8 | Work item scope | tz gate only | Adds `extraction_gate` and `combine_gates` (AD-8), so item 6 combines them one way |

ACs this item adds to later work items:
- **Item 4:** use `ics_item_id`; map Windows zone names to IANA.
- **Item 6:** an original-start source, one transaction per item (or globally sorted locks), the `REINSTATED` mapping, and one state change per returned kind.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/domain/dedup.py` | Identity |
| `backend/domain/lifecycle.py` | Postponement and the change classifier |
| `backend/domain/timezones.py` | Zones, tiers, DST |
| `backend/domain/confidence.py` | Gates |
| `backend/tests/domain/test_dedup.py` | Identity tests |
| `backend/tests/domain/test_lifecycle.py` | Lifecycle tests |
| `backend/tests/domain/test_timezones.py` | Timezone tests |
| `backend/tests/domain/test_confidence.py` | Gate tests |
| `backend/tests/domain/test_domain_api.py` | No embedding, cosine, vector or similarity parameter or field anywhere in the public domain API (AD-4) |
| `backend/tests/ingestion/test_domain_parity.py` | Domain lifecycle fields ↔ `Event.LIFECYCLE_FIELDS`; every `ChangeKind` maps to a model `Kind` or is in `NOT_YET_STORED` |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/domain/errors.py` | `InvalidTimezoneError` |
| `backend/shared/constants.py` | `TITLE_JACCARD_MIN`, `POSTPONEMENT_WINDOW`, and the tz scores and caps (`Decimal`) |
| `backend/config/apps.py` | `zoneinfo.reset_tzpath(to=())` in `ready()` |
| `backend/pyproject.toml`, `backend/uv.lock` | `tzdata==2026.5` |
| `backend/tests/shared/test_constants.py` | New constants; every score and cap lands in its intended gate band |
| `backend/tests/config/test_project.py` | `zoneinfo.TZPATH == ()` once Django is ready |
| `.specs-fire/standards/coding-standards.md`, `tech-stack.md` | Where identity and tz decisions live, the fingerprint versioning rule, the tzdata pin |
| `catalog-data-model-design.md` | Amend D8 (departure 5) |
| `structured-parsers.md`, `ingest-pipeline-and-lifecycle.md` | The ACs handed on (see above) |

## Tests

| Test File | Coverage |
|-----------|----------|
| `test_dedup.py` | Golden fingerprints: accents, ß, ligatures, ド, CJK bigrams, an all-stop-word title, a 600-character title capped at 512, "Night at the Museum" = "Night of the Museum". Symmetric fallback ("The The" vs "The The Live"). Jaccard at 4/5 and just below; a version mismatch gives 0. Venue: empty → `""`; the two Portlands differ. Every URL rule, including the malformed, IDNA, userinfo, route-fragment and http/www cases. Rules (a)/(b)/(c) positive and negative; same-source exclusion; second truncation; P1. `resolve()`: new, match, ambiguous, the bound item with review signals, superseded ignored, rule priority. Lock keys: stable values pinned, sorted, empty parts skipped. `ics_item_id`. |
| `test_lifecycle.py` | ±30 days exactly and 30 days + 1 s, both directions; drift across two moves measured from the original; a naive datetime raises. Every kind and the precedence order; cancelled + a 40-day move gives cancelled; a move + sold out keeps both; tz-only; end-only; sold out turning off; reinstated (both paths); a superseded input raises; no change gives `None`. |
| `test_timezones.py` | Every table row; the gap (New York, 2026-03-08 02:30) and the fold (2026-11-01 01:30); caps applied only to naive times; the end-time policy; the `start_time_local` round trip. Zones: `EST`, `localtime`, `Factory`, `posixrules`, an unknown name; `US/Eastern` → `America/New_York`; `Etc/GMT+13` rejected; `Etc/GMT` sign inversion. An invalid venue tz raises `InvalidTimezoneError`. |
| `test_confidence.py` | 0.69 / 0.70 / 0.89 / 0.90 / 1.00 and the extraction gate boundaries; float, NaN, `None`, `bool`, 0.705 and 1.01 rejected; `combine_gates` |
| `test_domain_api.py`, `test_domain_parity.py` | As described in Files to Create |
| Existing | `test_ids.py` covers the `series_id` AC. Domain purity, the stdlib-only check, import-linter and the 100% `domain/` gate stay green. |

## Technical Details

**Stdlib only:** `unicodedata`, `re`, `hashlib`, `fractions`, `decimal`, `urllib.parse`, `zoneinfo`, `dataclasses`, `enum`, `datetime`. Domain imports `shared.constants` only.

**Order:**
1. Dependency and constants
2. `confidence.py`
3. `timezones.py`
4. `dedup.py`
5. `lifecycle.py`
6. Tests alongside each module
7. Parity and API tests
8. Doc and AC edits
9. Gates: `make lint-backend`, `manage.py check`, `make coverage-backend` (100% `domain/`)

---
*Plan approved at Checkpoint 1 (2026-10-28T08:46:25Z).
