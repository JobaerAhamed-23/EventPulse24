# Next Session Handoff — EventPulse24

Paste everything below into the new context window, then run `/specsmd-fire-planner`.

---

## Prompt to paste

```
Continue the EventPulse24 project on the branch `city-picker-and-auto-collection`.

Use the FIRE flow: run `/specsmd-fire-planner` to plan the next work item, then
`/specsmd-fire-builder` to execute it.

## Where the project is

The intent `city-picker-and-auto-collection` is **complete**: run-eventpulse24-057
closed all 11 of its work items. There is no active run.

- `.specs-fire/state.yaml` — `runs.active` is empty; `runs.completed` holds runs
  001–057.
- The run's own summary is `.specs-fire/runs/run-eventpulse24-057/walkthrough.md` —
  **read it first.** It names the spine of the eleven items and every decision
  that should not be re-litigated.
- Nothing is pushed and no PR exists. Eleven commits sit on the branch.

The next run needs a new intent, or the next item of an existing one — see
"Still open" below for what the last run left for a person.

## What just landed (run-eventpulse24-057, "City Picker Over a Curated World List")

**Eleven items, one guarantee:**

> The stored city is the picked city. Never silently rewritten to anything else.

The chain, end to end:

1. `city-catalog-dataset` — 166 hand-verified cities, each with a canonical value
   ("Portland, OR"), a human label ("Portland, Oregon"), a country, a region and a
   time zone.
2. `source-city-timezone` — a source carries its city's zone, so a city we have not
   collected for can still publish.
3. `api-source-parser` — FR-17 puts the API first, so the API got its own parser
   rather than borrowing the crawler's.
4. `city-choices-endpoint` — `GET /api/public/cities`, session-free, throttled.
5. `stored-city-is-the-picked-city` — the guarantee. A catalog city is stored
   **verbatim**; a city outside the catalog is **refused** with a 422 and nothing is
   stored. A *geo guess* and a *backfill* still fall back — only a *choice* is refused.
6. `city-provider-templates` — a registry of which provider serves which city.
7. `city-provisioning-service` — a pick provisions: mints the `City`, registers the
   `Source`s, writes the `CityProvisioning` row.
8. `provisioning-probation` — the city's four honest statuses: `live`,
   `yielded_nothing`, `paused`, and `collecting`.
9. `browse-collecting-states` — Browse says one of four honest things, in three
   treatments across two families.
10. `city-coverage-request` — the no-sources dead end gains a way out: one row per
    city, throttled, never minting a city.
11. `home-city-dropdown-catalog` — the picker reads the catalog rather than the
    preview's list, so a reader in an uncollected city is offered their own city.

### Carry-over to respect in the next work item

1. **The endpoint-coverage test is two-sided.** `frontend/tests/endpoint-coverage.test.ts`
   fails both when an endpoint has no caller and no declaration (an orphan) and when
   a declaration has a caller (a stale exemption). **Both halves are under test**, and
   the removal is the half that is easy to undo by accident.
2. **A city's name is not in an audit trail.** The provisioning and coverage-request
   audit rows carry the city *id*; a person's city is weak location data about a real
   person (AD-13), while a *source's* city is a public fact about a place.
3. **A pick is not a retry request.** The `CityProvisioning` row's existence means
   "provisioned", whatever its status says. A retry belongs to a person or to the
   scheduler.
4. **`unchanged` is yield** and **a 304 leaves the counter alone.** These two lines
   are what keep a healthy source from being paused for doing its job perfectly.
5. **A request never mints a city.** A city we have never heard of is a *pick*, and a
   pick provisions immediately.

## Current state of the code

- Backend: Django + Django Ninja. `backend/apps/` has the MVP apps (ingestion,
  catalog, personalization, delivery, identity, editorial).
  `backend/domain/` is pure (stdlib only, plus `shared.constants`/`shared.ids`).
- Two Postgres schemas on one database: `personal` (default) and `catalog`.
  Always pass `using=` (`PERSONAL`/`CATALOG` from `shared.db`).
- The generated frontend client lives in `frontend/lib/api/` and is produced by
  `make client`. NEVER hand-edit it. `backend/tests/api/test_contract.py`
  fails until the committed schema matches the live API.
- `beat_schedule` is exactly one 60s tick. `backend/tests/worker/test_tick.py`
  enforces it. Source scheduling hangs off that tick; do not add beat entries —
  item 8's probation was deliberately kept off it for that reason.
- Ingestion is the SOLE writer of catalog entities (AD-16). Read surfaces must
  not write: `apps/*/api.py` and `apps/*/admin.py` are scanned syntactically by
  `tests/architecture/test_no_direct_writes.py`.

## Commands that matter

```bash
# backend tests
cd backend && uv run --directory . python -m pytest -q
cd backend && uv run --directory . python -m pytest --cov=. --cov-report=term-missing -q

# architecture + linters
cd backend && uv run --directory . lint-imports
cd backend && uv run --directory . ruff check .
cd backend && uv run --directory . ruff format --check .
cd backend && uv run --directory . python manage.py check
cd backend && uv run --directory . python manage.py makemigrations --check --dry-run

# regenerate the frontend client (after ANY API change)
make client && git diff --exit-code frontend/lib/api/

# frontend
cd frontend && pnpm lint && pnpm typecheck && pnpm test

# the local stack (postgres + redis + api + worker + beat + next)
docker compose up -d && make dev
```

Current baseline: **9091 backend tests pass, 2957 frontend tests pass (184 files),
21 import contracts kept, 0 broken.**

## Standards

Read `.specs-fire/standards/` before writing code: `constitution.md`,
`tech-stack.md`, `coding-standards.md`, `testing-standards.md`,
`system-architecture.md`. The architecture spine is at
`_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md`.

## How the last run went (so you can match the bar)

Each run produces a folder in `.specs-fire/runs/` with a `plan-<item>.md`,
`test-report-<item>.md`, `review-report-<item>.md` and `walkthrough-<item>.md` per work
item, plus a run-level `walkthrough.md`, and `state.yaml` is updated ONLY through the
scripts in `.specsmd/fire/agents/builder/skills/run-execute/scripts/` — never by hand.

The bar the project holds itself to, and that run-057 met:
- **Every whole-dataset invariant is mutation-checked** before a test report is
  written — *a mutation that survives is a missing test*. Run-057's probe grew to
  **39 mutations, 39 caught, 0 survived**
  (`.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py`).
- The full gate set green: backend 9091 passed, frontend 2957 passed (184 files),
  typecheck clean, lint 0 errors, 21 import contracts kept.
- Deviations from the plan recorded with the reason, not silently absorbed.
```

---

## Quick reference for you (not for pasting)

**Committed:** the eleven item commits `e39d367` … `ec02e54`, plus the run's
documentation. Working tree clean at the time of writing. **Not pushed** — no push was
requested.

**The thing to decide early:** the next intent. Run-057 closed a guarantee and left
three things that are a *person's* job rather than code's — the Eventbrite template's
Terms review, the coverage-request queue's editor UI, and the catalog's ongoing
maintenance. Any of the three could be the next run's scope, and each is a better
candidate than a fourth pass over the same chain.

## Still open, for a human

- **The Eventbrite template is disabled** and waits for a review of the provider's
  Terms. The shape is in the registry, so enabling it is one constant.
- **The coverage-request queue has no editor UI.** The row, the counter, the read-only
  admin and the throttled endpoint all exist; acting on the queue does not.
- **The catalog is hand-maintained.** 166 cities is a snapshot, with a whole-dataset
  test behind every invariant.
- **A paused or `yielded_nothing` city's sources are audited, never deleted** — the
  pause reason is a column (state) and not the audit trail (accountability), because
  the trail is retained 24 months and the column is not.
- **`pnpm format:check` reports 44 unformatted files** — one *fewer* than the branch
  started with. The remainder is pre-existing drift and is not this run's to fix.
