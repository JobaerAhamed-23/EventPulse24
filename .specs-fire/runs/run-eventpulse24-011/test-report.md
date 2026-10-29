---
run: run-eventpulse24-011
work_item: event-identity-and-tz-domain
intent: event-catalog-ingestion
generated: 2026-10-28
status: passed
---

# Test Report: Event Identity & Timezone Domain Logic

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit: `domain/` (no database) | 256 new | 0 | 0 | **100%** of `domain/` (457 statements) |
| Integration (Django / Postgres) | 10 new | 0 | 0 | parity, constants, tz path |
| **Total suite** | **845** (579 before + 266 new) | 0 | 0 | **98.16%** overall |

The 266 new tests (6 of them added by the code-review fixes) include 8 generated automatically by the architecture checks (stdlib-only and alias) for the four new domain modules.

## Acceptance Criteria Validation

From `event-identity-and-tz-domain.md`, as amended by the approved plan (revision 2):

- ✅ **`title_fingerprint`, `venue_fingerprint`, `jaccard`:** golden values cover accents, ß, ligatures, ド, CJK and Thai bigrams, Devanagari, stop words and the 512-character cap. Jaccard is symmetric and exact (`Fraction`).
- ✅ **The match function and its rules:**
  - Rule (a) comes from the binding and wins.
  - Rule (b) is tested positive and negative, including Jaccard exactly at 4/5 and just below it (3/4).
  - Rule (c) needs the same URL **and** instant (P1).
  - Items from the same source are never merged, and comparisons use whole seconds.
- ✅ **No embedding or cosine input** anywhere in the domain API (`test_domain_api.py` scans every public name, dataclass field and parameter).
- ✅ **Recurring instances never merge:** a weekly instance with the same URL and venue doesn't match, and `ics_item_id` keeps UID-sharing instances distinct.
- ✅ **`series_id` is deterministic UUIDv5:** already covered by `tests/shared/test_ids.py` (golden value, from run 010).
- ✅ **Postponement classifier:** exactly ±30 days stays within the window, 30 days + 1 s supersedes, measured from the **original** start (two 20-day moves supersede), and aware datetimes are required.
- ✅ **Change classifier:**
  - every kind
  - the precedence order (a cancellation that also moves the date is only a cancellation)
  - multiple kinds kept together
  - tz-only, end-only and sold-out-off changes
  - both REINSTATED paths
  - superseded input rejected
  - no change returns `None`
- ✅ **Timezone tiers:** every table row (A1–A3, U1–U2, B1–B4, C1–C2), including the invalid source zone and invalid venue tz cases.
- ✅ **Gates:** 0.69 / 0.70 / 0.89 / 0.90 / 1.00. Exactly 0.90 auto-publishes. Floats, NaN, `None`, `bool` and three-decimal values are refused. `combine_gates`: the strictest wins.
- ✅ **DST:** the gap (New York 2026-03-08 02:30) caps at 0.65 and goes to review. The fold (2026-11-01 01:30) takes the first occurrence and caps at 0.80. An aware time in a fold is exact and uncapped. End times follow the same policy. `start_time_local` round-trips.
- ✅ **Non-existent zones:** `EST`, `EST5EDT`, `localtime`, `Factory`, `posixrules`, unknown names, `Etc/GMT+13`/`-15` and a path traversal are rejected. `US/*` and `Canada/*` canonicalize, and each alias is verified offset-identical to its target.
- ✅ **`domain-pure` and stdlib-only:** import-linter 12 kept; `test_domain_is_django_free` passes; the stdlib-only check covers the four new modules.

## Tests Written

### Unit Tests

- `tests/domain/test_confidence.py` (28): gate boundaries, input validation, `combine_gates`
- `tests/domain/test_timezones.py` (94): the table rows, tiers, rejections, DST, end time, round trip, zone validity, legacy aliases, `Etc/GMT` sign
- `tests/domain/test_dedup.py` (82): fingerprints, Jaccard, venue, URL, `ics_item_id`, rules, `resolve()`, lock keys (golden values pinned)
- `tests/domain/test_lifecycle.py` (37): time move, change kinds, status transitions, precedence
- `tests/domain/test_domain_api.py` (1): AD-4, no embedding or similarity inputs

### Integration Tests

- `tests/ingestion/test_domain_parity.py` (2): domain lifecycle facts ↔ `Event.LIFECYCLE_FIELDS`; every `ChangeKind` is stored or in `NOT_YET_STORED`
- `tests/shared/test_constants.py` (+7): thresholds, and every tz score and cap landing in its intended gate band
- `tests/config/test_project.py` (+1): `zoneinfo.TZPATH == ()`, and tzdata is IANA 2026e

## Test Commands

```bash
make test-backend
make coverage-backend   # ≥80% overall, 100% domain/
```

## Coverage Details

| Module | Lines |
|--------|-------|
| `domain/confidence.py` | 100% |
| `domain/dedup.py` | 100% |
| `domain/lifecycle.py` | 100% |
| `domain/timezones.py` | 100% |
| `domain/` total | 100% (457 statements) |
| Overall | 98.16% |

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| The regex tokenizer (`\w`) split Thai and Indic words at combining vowel marks (`สวัสดี` → `สว`, `สด`) | Medium | Fixed: tokenize by Unicode category (letters, numbers, marks); golden tests added |
| A test fixture used `a`, which is a stop word | Low | Fixed in the test |
| The venue golden test was first written with a placeholder hash and an `or` fallback, so it could never fail | Low | Fixed: the real value is pinned |

## Ready for Completion

- [x] All tests passing (845/845, re-run after the code-review fixes)
- [x] Coverage target met (98.16% overall; 100% `domain/`)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-011*
