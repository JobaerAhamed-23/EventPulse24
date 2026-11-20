---
run: run-eventpulse24-046
work_item: timeline-why-this-tag
intent: traceability-gap-closure
generated: 2026-11-19
status: passed
---

# Test Report: The Timeline block's Why-this tag — deferred, with the reason

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Backend (full suite) | 7476 | 3 (pre-existing) | 7 | unchanged |
| Tests added by this run | 0 | 0 | 0 | n/a |
| **Total** | **7476** | **3 (pre-existing)** | 7 | unchanged |

**No test was added, because no behaviour changed.** This run amends two planning
documents. The correct proof is not a new assertion but a demonstration that nothing
executable moved, plus the full suite still passing.

## The change, and why it has no test

Three documents changed, and zero lines of code:

```
 _bmad-output/.../EXPERIENCE.md                             | 6 +++---
 _bmad-output/.../TRACEABILITY.md                           | 2 +-   (then the open-items bullet)
 .specs-fire/.../work-items/timeline-why-this-tag.md        | 2 +-
```

`git diff HEAD -- backend frontend` is **empty**. No module, schema, migration or
component was touched, so the generated API client is unchanged and
`tests/api/test_contract.py` sees no schema drift.

**No test reads these documents.** `grep -rn "_bmad-output" backend/tests frontend/` returns
nothing. The 10 test files that mention `EXPERIENCE.md` or `TRACEABILITY` cite them in
docstrings as the source of a rule; none opens the file. So no assertion could have been
invalidated by editing them.

## Acceptance Criteria Validation

- ✅ **A decision is recorded before any code: either build the per-user tag, or amend §13 to say the Timeline block reveals location only, and why** — amended. §13's hover/focus row is location-only under Amendment A-24, with the reason stated in the row and argued in full in the `updated_note` entry.
- ➖ **If built:** the tag is the Relevance Pulse kind, computed with `why_this_tags` — *not applicable; the amend branch was taken.*
- ➖ **If built:** the week read does not become N+1 — *not applicable.*
- ➖ **If built:** a personal block shows no tag, and a block whose catalog event is gone shows none — *not applicable.*
- ✅ **If amended:** §13's line is changed in place with an Amendment ID, and TRACEABILITY.md's O-2 is updated to say the shortfall is now the spec's position rather than a gap — both done. §13 line 1107 carries **Amendment A-24**; the FR-32 row reads **O-2 closed (2026-11-19)**.

## Tests Written

### Unit Tests

None. No behaviour changed.

### Integration Tests

None. No behaviour changed.

## Test Commands

```bash
# Full backend suite (venv on PATH — see "Issues Found")
cd backend && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest -q

# The suites most closely related to this surface
cd backend && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest \
  tests/personalization/test_timeline.py \
  tests/personalization/test_timeline_place.py \
  tests/domain/test_ranking.py \
  tests/architecture/ -q
```

## Verification performed

| Check | Result |
|---|---|
| `git diff HEAD -- backend frontend` | **empty** — zero code change |
| `git status --porcelain` | 4 modified (2 planning docs, 1 work item, state.yaml) + this run's artifacts |
| Full backend suite | **7476 passed**, 3 pre-existing failures, 7 skipped (5:04) |
| Timeline + ranking + architecture suites | 1197 passed |
| `tests/architecture/test_preview_anonymity.py` | 22 passed (after starting Redis) |
| EXPERIENCE.md frontmatter parses as YAML | ✅ — `updated: 2026-11-19`, `updated_note` a single scalar, 0 unescaped inner quotes |
| A-24 unused before writing | ✅ — `grep -rno "A-24" _bmad-output docs` returned nothing |
| Nothing still lists the tag as open work | ✅ — see below |

### The grep that found something

The plan's checklist included *"verify no other document still lists `timeline-why-this-tag`
as open work."* It did. `TRACEABILITY.md:227` carried an **"Open items that are decisions,
not work"** bullet describing the tag as outstanding — and repeating the "four extra reads"
claim the design doc had already disproved. Leaving it would have contradicted the FR-32
row three sections earlier in the same file.

It is now rewritten as **DECIDED 2026-11-19, Amendment A-24**, carrying both corrections
(one extra query, not four; AD-10 bars the Event Fit, not the Relevance Pulse path) and the
real reason.

One reference remains at `TRACEABILITY.md:19`, and it is **left deliberately**: it narrates
what the 2026-11-17 regeneration raised at the time. It is accurate as history, and
rewriting history to match today's decision is how a ledger stops being trustworthy.

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| Postgres and Redis were not running; 56 DB-backed tests errored on connection refused | Environment | **Resolved** — started `postgres` and `redis` via compose. Note `docker compose up` (no service named) would now also try MinIO, whose image cannot be pulled here. |
| 6 tests failed on the first full run: 3 `test_blob.py` client-caching, 3 `test_the_import_contracts_still_hold` | **Operator error, not code** | **Resolved** — I invoked `.venv/bin/python -m pytest` without `.venv/bin` on PATH, so `lint-imports` was not found. With PATH set, all 65 pass. Worth recording: the Makefile uses `uv run`, which sets PATH; invoking the venv python directly does not. |
| 3 `tests/delivery/test_preferences_api.py` failures — `ScheduledSend.DoesNotExist` | Pre-existing | **Not caused by this run.** Identical failure mode to the one run-041 verified against base commit `b8c6b21` in a separate worktree. This run changed zero Python, so it cannot have caused them. **Still open and still unowned** — they belong to no current work item. |

## Ready for Completion

- [x] All tests passing (3 failures pre-existing and verified unrelated)
- [x] Coverage target met (n/a — no code changed)
- [x] All acceptance criteria validated (the amend branch; the build branch is not applicable)
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-046*
