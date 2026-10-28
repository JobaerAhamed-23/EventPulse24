# Code Review Report

**Run**: run-eventpulse24-013
**Intent**: event-catalog-ingestion
**Reviewed**: 2026-10-28
**Files Reviewed**: 24 (19 created, 5 modified)

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 0 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture (identity correctness) | 0 | 3 | 0 |
| Testing | 0 | 0 | 0 |
| **Total** | **0** | **3** | **0** |

**Tests Status**: Passing (1315/1315 after the applied suggestions)

---

## Files Reviewed

**Production code:**
- `backend/apps/ingestion/parsers/`: `__init__.py`, `types.py`, `text.py`, `times.py`, `jsonld.py`, `feeds.py`, `ics.py`, `windows_zones.py`

**Tests and fixtures:**
- `backend/tests/ingestion/parsers/`: 4 test modules
- 8 fixtures, plus updates to `index.json`

**Configuration:**
- `backend/pyproject.toml`, `uv.lock`, `.specs-fire/standards/tech-stack.md`, `coding-standards.md`

---

## Auto-Fixed Issues

No auto-fixes applied. ruff and the 13 import contracts were already clean.

---

## Suggestions (all 3 approved by the user and applied)

All three were confirmed by probes. Each one makes rule (a), identity by source item, merge different events or fail the insert.

### 1. [Architecture] JSON-LD `@id` values that aren't global identifiers are used as item IDs

- **File**: `backend/apps/ingestion/parsers/jsonld.py`
- **Finding**: blank nodes (`_:b0`) and fragment-only or relative IDs (`#event`) are local to one document. Probe: two different events both get `source_event_id = "_:b0"`, so rule (a) would merge them.
- **Change**: use `@id` only when it is an absolute IRI (it has a scheme and is not `_:`). Otherwise fall back to the derived ID.
- **Risk**: Low
- **Applied**: `text.absolute_iri()` is used for item and series IDs. Tests: `_:b0`, `#event`, `/e/1` and `event-1` each give two distinct derived IDs; URN and `tag:` IRIs are accepted.

### 2. [Architecture] IDs longer than `source_event_id`'s `varchar(512)` pass through

- **Files**: all three parsers
- **Finding**: probe: a 1,000-character `@id` gives a 1,000-character `source_event_id`. The insert in item 6 would fail on the column length.
- **Change**: one shared `item_id()` step that turns any ID over 512 characters into `long:` + sha256 (69 characters, stable).
- **Risk**: Low
- **Applied**: `text.item_id()` is applied in all three parsers. Tests: exactly 512 characters is kept, 513 is hashed (`long:`, 69 characters, stable).

### 3. [Architecture] Duplicate IDs within one document, and ICS overrides losing to their master

- **Files**: `types.py` (`ParseResult`), `ics.py`
- **Finding**: probe: when a `RECURRENCE-ID` override comes *before* its RRULE master in the file, both candidates share an ID and the master comes last, so an upsert in order keeps the master and loses the correction ("Moved indoors" → "Run Club"). A feed that reuses one `guid` for different items also yields duplicates.
- **Change**: `ParseResult.add(candidate, priority=0)` keeps one candidate per ID. A higher priority replaces an existing one; otherwise the first is kept and the later one is counted as `duplicate_id`. ICS overrides are added with priority 1, so an override wins regardless of file order.
- **Risk**: Low
- **Applied**: `ParseResult.add()`, with ICS overrides at priority 1. Tests: the override wins in both file orders, and a reused `guid`, `@id` or `UID` keeps the first and counts `duplicate_id`. The fixture now yields 8 candidates, because the first-week override replaces its master's instance.

**Re-run after applying:** ruff clean; 13 contracts kept; 1315 passed; parsers 100%.

---

## Notes (no action)

- **Relative RSS links** resolve against `SourceContext.source_url`. Item 6 must pass the source's own URL, or the final URL after fetching, as the base.
- **Generic RSS feeds** with only `pubDate` yield no candidates (S3). That is by design, and their skip counts make it visible.
