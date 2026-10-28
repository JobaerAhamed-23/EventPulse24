# Code Review Report

**Run**: run-eventpulse24-011
**Intent**: event-catalog-ingestion
**Reviewed**: 2026-10-28
**Files Reviewed**: 22 (11 created, 11 modified)

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 0 | 2 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 1 | 0 |
| Testing | 0 | 0 | 0 |
| **Total** | **0** | **3** | **0** |

**Tests Status**: Passing (845/845 after the applied suggestions)

---

## Files Reviewed

**Production code:**
- `backend/domain/confidence.py`, `dedup.py`, `lifecycle.py`, `timezones.py` (created)
- `backend/domain/errors.py`, `backend/shared/constants.py`, `backend/config/apps.py` (modified)

**Tests:**
- `backend/tests/domain/`: `test_confidence.py`, `test_dedup.py`, `test_lifecycle.py`, `test_timezones.py`, `test_domain_api.py` (created)
- `backend/tests/ingestion/test_domain_parity.py` (created)
- `backend/tests/shared/test_constants.py`, `backend/tests/config/test_project.py` (modified)

**Configuration:** `backend/pyproject.toml`, `backend/uv.lock` (modified; `tzdata==2026.5`)

---

## Auto-Fixed Issues

No auto-fixes applied. ruff and import-linter were already clean.

---

## Suggestions (all 3 approved by the user and applied)

Each was confirmed by a probe before it was reported.

### 1. [Architecture] An alias zone name counts as a lifecycle change

- **File**: `backend/domain/lifecycle.py` (`classify_change`)
- **Finding**: `start_time_tz` is compared as a literal string, so `US/Eastern` → `America/New_York` returns `detail_changed` with `is_lifecycle=True`. Item 6 would bump `event_version` and AD-17 would queue a notice for a non-change.
- **Change**: compare zones through `domain.timezones.canonical_zone()`. Add a test showing that an alias is no change and a real zone change still is one.
- **Risk**: Low
- **Applied**: `_comparable` canonicalizes `start_time_tz`. Tests: `test_classify_change_zone_alias_is_no_change` and `test_classify_change_real_zone_change_is_still_a_change`.

### 2. [Code Quality] Percent-encoded unreserved characters stop URLs matching

- **File**: `backend/domain/dedup.py` (`canonical_url`)
- **Finding**: `/~bob` and `/%7Ebob` are the same URL (RFC 3986 §6.2.2.2) but normalize differently, so rule (c) misses the match. The failure is safe (no wrong merge) but lossy.
- **Change**: decode the percent-escapes of unreserved characters (`A–Z a–z 0–9 - . _ ~`) in the path. Keep the remaining escapes uppercased. Add a test.
- **Risk**: Low
- **Applied**: `_normalize_escape` (`%7E` becomes `~` and `%41` becomes `A`; `%2F` stays escaped). Golden case added.

### 3. [Code Quality] IPv6 hosts lose their brackets, so the port merges into the address

- **File**: `backend/domain/dedup.py` (`canonical_url`)
- **Finding**: `https://[2001:db8::1]:8080/x` becomes `https://2001:db8::1:8080/x`, which is malformed and indistinguishable from the address `2001:db8::1:8080` with no port.
- **Change**: re-bracket IP-literal hosts (any host containing `:`) before the optional port is added. Add a test.
- **Risk**: Low
- **Applied**: IPv6 literals keep their brackets and skip IDNA. Tests: two golden cases, plus `test_canonical_url_ipv6_port_never_merges_into_the_address`.

**Re-run after applying:** ruff clean; import-linter 12 kept; 845 passed; coverage 98.16% overall, 100% `domain/` (457 statements).

---

## Notes (no action)

- `canonical_url` re-encodes the query with `urlencode`, so spaces become `+`. That is consistent on both sides of a comparison.
- Title fingerprints drop accents from Latin, Greek and Cyrillic letters only. Vietnamese tones fold too ("Hà Nội" equals "Ha Noi"), which is intended for matching.
