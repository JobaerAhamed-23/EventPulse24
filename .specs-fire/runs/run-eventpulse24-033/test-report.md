---
run: run-eventpulse24-033
work_item: settings-sources-surface
intent: source-transparency-and-mute
generated: 2026-11-13
status: passed
---

# Test Report: Settings → Sources — A Designed Screen With No Endpoints

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit (backend) | 24 | 0 | 0 | 98% (`source_registry_read.py`) |
| Integration (backend) | 46 | 0 | 0 | 93.5% (new + touched modules) |
| Unit (frontend) | 20 | 0 | 0 | n/a (Vitest, no threshold) |
| **Total** | **90** | **0** | **0** | **93.5%** |

**Full-suite health.** The whole backend suite is **7044 passed, 4 failed**; the whole
frontend suite is **2504 passed, 0 failed** across 148 files. The 4 backend failures are
`tests/e2e/test_state_change_proof.py::TestTheStripAndTheBanner` and they are **pre-existing**
— verified by `git stash push -u` and re-running on a clean tree, which produces the same 4
failures. They are not caused by this work item.

## Acceptance Criteria Validation

- ✅ **The design checkpoint decides scope before any code**, including whether the 3-state mute is the same control FR-25's prompt reverses — Checkpoint 1 approved the design doc, which settled it as **two different subjects**: this screen mutes *sources*, FR-25's mockup reverses at `Settings → Taste` and mutes *categories* (`less-like-this-mute-prompt-desktop.html:122`, `:149`). The two are siblings under one settings nav and neither couples to the other.
- ✅ **A signed-in user can see the sources behind their events, grouped by acquisition type, with each source's reliability** — `GET /api/settings/sources` returns the four Source Badge groups in order, each source with its `trust.band` and `trust.score`. Proven by `test_source_registry_read.py` (24 tests) and `test_source_mutes_api.py` (18 tests).
- ✅ **A source can be set to Mute / Show less / Default, and the setting persists** — `PUT /api/settings/sources/{source_id}`; `default` **deletes** the row rather than storing a third state. Proven by `test_source_mutes.py` (15 tests).
- ✅ **The setting changes what the user is shown — proven against the composition or ranking path, not only by a test that the row was written** — `test_source_mute_composition.py` (13 tests) proves it at the composition seam in **both** surfaces: a muted source's events are **absent** from the composed digest *and* from Browse; a show-less source's events are **present but ordered lower** in both. The muted case is asserted as an exclusion, not a demotion — the muted event is the *only* candidate in its pool, so a demotion would still show it.
- ✅ **"Restore all defaults" exists and is confirmed before it completes (§10.4)** — `POST /api/settings/sources/restore-defaults`. The frontend sends **no request on the first press**; the confirmation replaces the button in place, and only "Reset them" calls the endpoint. Proven by both the backend API test and six frontend tests.
- ✅ **Reliability is rendered as the mockup specifies — 1–5 ink-primary dots, not the terracotta confidence pulse, and no new tokens** — `source-trust-dots.tsx` draws `--ink-primary` / `--ink-faint` dots and reuses the mono face. The test asserts the dots are `aria-hidden` with the reading on the group's `aria-label` ("4 of 5 reliability"), so a screen reader hears one sentence rather than five identical elements.
- ✅ **The route follows the five-step settings house pattern and is linked from an existing settings page** — `/settings/sources` with `force-dynamic` → `homeRoute(session)` redirect → signed-out branch → `unavailable` branch → the page. It has a row in `SETTINGS_SECTIONS`, a sibling `loading.tsx` (every other settings route has one), and it is linked from the settings index.
- ✅ **New endpoints go through the generated client (AD-19) with `make client` output committed** — `frontend/lib/api/openapi.json` and `frontend/lib/api/schema.ts` regenerated and committed. `make client` is idempotent: a second run produces no further change, so CI's `git diff --exit-code frontend/lib/api/` passes.
- ✅ **Every test is verified by a mutation probe that makes it fail** — **14 probes, all caught**. See "Mutation Probes" below.

## Tests Written

### Unit Tests

- `backend/tests/ingestion/test_source_registry_read.py` — 24 tests. The trust band at each of 11 score→band pairs including every exact boundary; the 0.50 prior for a never-scored source; the four groups always present in order; paused sources still listed; a score outside [0, 1] raises.
- `backend/tests/personalization/test_source_mutes.py` — 15 tests. `mute` / `show_less` write a row; setting the same state again reports `changed=False`; `default` **deletes** the row; one user's rows do not touch another's; `read_source_visibility` returns two separate frozensets; the bulk reset is scoped and idempotent.
- `frontend/components/settings/source-list.test.tsx` — 20 tests. Every group listed in order; a muted source still listed; the state shown via `aria-pressed`; the trust dots read "4 of 5 reliability"; the three options all present in a named group; the PUT sent with the right source id; **no request for the state already held**; the control moves **only** when the server confirms; the control **stays put** when the server refuses; restore sends no request on the first press, asks in place, resets on yes, resets nothing on no, puts every row back to default, and is not offered at all for an empty registry.

### Integration Tests

- `backend/tests/personalization/test_source_mutes_api.py` — 18 tests. The list's four groups in order; each source carrying its trust; **a muted source still listed with its state**; an empty registry lists four empty groups; anonymous is 401; a set state records the row and writes an audit row; a CSRF-less write is 403 `csrf_failed`; the bulk reset is scoped, idempotent, and audited.
- `backend/tests/personalization/test_source_mute_composition.py` — 13 tests. The acceptance criterion, at the composition seam, in both surfaces.

## Mutation Probes

`backend/tests/personalization/mutation_probe_source_mutes.py` — **14 probes, all caught**:

```
OK  the mute filter is dropped (a muted source's events reach the digest)
OK  the mute filter is dropped in Browse (the two surfaces disagree)
OK  the show-less penalty is dropped (a show-less source scores the same)
OK  the show-less penalty is dropped in Browse
OK  the show-less penalty subtracts nothing (the rule is applied but is a no-op)
OK  the penalty is applied inside the ranking formula (FR-22's weights move)
OK  the default state is stored as a row instead of deleting it
OK  the bulk reset is not scoped to the caller (it clears everybody's rows)
OK  the bulk reset forgets the show-less preferences
OK  the trust band uses exclusive bounds (0.50 lands in band 2, not band 3)
OK  the registry drops the paused sources (transparency fails)
OK  the registry drops the empty groups (the screen's shape depends on the data)
OK  the list drops the muted sources (the screen stops being transparent)
OK  the list reads another user's states (the scoping is broken)

All 14 probes were caught by the suite.
```

**One probe found a real gap.** "the show-less penalty is dropped in Browse" was initially
**not caught** — the browse test asserted only that a show-less source's events were
*present*, not that they were *deprioritised*. A test that would pass with the penalty
removed proves nothing about the penalty. `test_browse_deprioritises_a_show_less_source`
was added, and the probe is now caught.

## Test Commands

```bash
# Backend, this work item
cd backend && uv run pytest tests/personalization/test_source_mutes.py \
  tests/personalization/test_source_mutes_api.py \
  tests/personalization/test_source_mute_composition.py \
  tests/ingestion/test_source_registry_read.py -q

# The mutation probes
cd backend && uv run python tests/personalization/mutation_probe_source_mutes.py

# The whole backend suite
cd backend && uv run pytest -q

# The whole frontend suite
cd frontend && pnpm exec vitest run

# Typecheck, lint, and the generated client
cd frontend && pnpm exec tsc --noEmit && pnpm run lint
cd backend && uv run ruff check . && uv run ruff format --check .
make client
```

## Coverage Details

| Module | Statements | Branches | Functions | Lines |
|--------|------------|----------|-----------|-------|
| `apps/personalization/services/source_mutes.py` | 100% | 100% | 100% | 100% |
| `apps/personalization/source_mutes_api.py` | 100% | 100% | 100% | 100% |
| `apps/ingestion/services/source_registry_read.py` | 98% | — | — | 98% |
| `apps/personalization/services/browse_read.py` | 94% | — | — | 94% |
| `apps/personalization/services/digest_composition.py` | 88% | — | — | 88% |
| **Total** | **93.5%** | — | — | **93.5%** |

Target: 80%. Met.

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| `POST /sources/restore-defaults` returned **405**, not 404 | High | **Fixed.** Django resolves URL patterns in registration order and checks the method *after* the path matches — so `PUT /sources/{source_id}`, registered first, swallowed the literal path as a `source_id` of `"restore-defaults"`. The literal route is now declared first, and the module docstring records that the order is load-bearing. |
| The endpoints declared only a `200` response, so the generated client's `error` type was `never` | Medium | **Fixed.** The genuinely reachable codes are now declared (401 anonymous, 403 CSRF, 404/422 for the PUT). This was a real contract improvement — `apps/identity/api_auth.py` genuinely raises `HttpError(401)` and `CsrfError` → 403. |
| **`SourceList` rendered the prop, not its own state** — the `useState` copy was dead code and "Restore all defaults" moved nothing on screen | High | **Fixed.** The list now renders the local copy and computes `total` from it. Found by the frontend test asserting the *observable* outcome ("the row goes back to default") rather than the implementation detail. |
| **`SourceMuteControl` ignored a changed `state` prop** — the bulk reset rewrote the rows in the parent and the control kept the old position | High | **Fixed.** The control now holds no copy of the state: the prop is the state, and the only local state is the write in flight (`pending`), which is dropped the moment the prop catches up. |
| The browse query budget was exceeded (5 personal queries against a bound of 4) | Medium | **Fixed.** The bound is a *fixed number of user-preference reads*, and the new source-visibility read is one of them — it does not grow with the pool, which is the property the bound is for. The bound was raised to 5 with the reasoning recorded, rather than left failing or silently loosened. |
| `w-24` in the new `loading.tsx` was off the DESIGN.md spacing scale | Low | **Fixed.** The spacing-scale test caught it; changed to `w-20`. |
| `useEffect(() => setCurrent(state), [state])` violated `react-hooks/set-state-in-effect` | Medium | **Fixed by removing the effect entirely**, not by suppressing the rule. See below. |

**The eslint fix was a design improvement, not a workaround.** The rule was right: a
component that mirrors a prop into local state and then synchronises the two has two
sources of truth that can disagree. The control now renders the prop directly and holds
only `pending` — the state the server has confirmed but the parent has not yet adopted.
That removed the effect, the second source of truth, and the class of bug where the
control and the row disagree.

## Notes

- **The 4 e2e failures are pre-existing and not this work item's.** They reproduce on a
  clean tree (`git stash push -u` → run → same 4 failures → `git stash pop`).
- **`frontend/components/brand-topbar.tsx` and `brand-topbar.test.tsx` are uncommitted
  changes that are not this work item's** (a Dark Reader `suppressHydrationWarning`
  hydration fix). They are deliberately left out of this run's diff.
- **`TRACEABILITY.md` and the mockup headers are untouched**, per the work item's own
  instruction — editing a document to improve a matrix score in the same pass that
  measures it is how a matrix stops being trustworthy. FR-16's `PARTIAL` score is a
  citation problem and stays a citation problem. `EXPERIENCE.md`'s
  `Component.Settings.Sources` row **was** corrected, because it described an algorithm
  (a forthcoming ADR-0024 that does not exist) and a confirmation pattern (type-to-confirm,
  reserved for account deletion) that the implementation does not use.

## Ready for Completion

- [x] All tests passing
- [x] Coverage target met (93.5% against 80%)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-033*
