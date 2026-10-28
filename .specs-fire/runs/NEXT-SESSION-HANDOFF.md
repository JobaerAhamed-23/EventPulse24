# Next Session Handoff — EventPulse24

Paste everything below into the new context window, then run `/specsmd-fire-planner`
(or `/specsmd-fire-builder` if you want to go straight to the remaining work item).

---

## Prompt to paste

```
Continue the EventPulse24 project on the branch `event-catalog-ingestion`.

Use the FIRE flow: run `/specsmd-fire-planner` to plan the next work item, then
`/specsmd-fire-builder` to execute it.

## Where the project is

The `event-catalog-ingestion` intent has 8 of 9 work items complete. The only
remaining work item is:

- **real-feeds-and-e2e-proof** (medium, mode `confirm`, status `pending`)
  File: `.specs-fire/intents/event-catalog-ingestion/work-items/real-feeds-and-e2e-proof.md`
  Depends on: `source-registry-commands-admin`, `ingestion-scheduling`,
  `public-catalog-read-api` — all three are now completed, so it is unblocked.

All state lives in `.specs-fire/state.yaml` (runs.active is empty; runs.completed
holds runs 001-017).

## What just landed (run-eventpulse24-017, "Public Catalog Read API")

Committed as `d9474e5` (implementation + tests) and `c5d95ff` (FIRE artifacts).

The public catalog read API is live:
- `GET /api/catalog/events` — paginated list of upcoming published events,
  filters `city`, `starts_after`, `starts_before`, `page`, `page_size`.
  Envelope: `{items, page, page_size, total, has_next}`.
- `GET /api/catalog/events/{event_id}` — one event, 404 via the shared
  `{code, message}` error shape.

The read query lives behind the published interface
`backend/apps/ingestion/services/catalog_read.py`, which returns a frozen
dataclass `PublicEvent` — NOT model instances. The `catalog` app never imports
`apps.ingestion.models`, so the `models-ingestion` import contract holds.

Artifacts for that run are in `.specs-fire/runs/run-eventpulse24-017/`:
`plan.md`, `run.md`, `test-report.md`, `review-report.md`, `walkthrough.md`.

### Carry-over to respect in the next work item

1. **CONFIRM-1 (from the run-017 code review, not applied).** The list endpoint
   echoes the *unclamped* `page`/`page_size` while `list_public_events` clamps
   them, and computes `has_next` from the unclamped values. It is currently
   unreachable via HTTP (the `EventPage` schema rejects out-of-range values with
   a 422 first), but it is a latent inconsistency. If you touch the catalog read
   path, make the service return the values it actually used.
2. **`config.api` is now part of the API surface.** The `worker-not-api`
   import contract forbids it, because `config/api.py` assembles the app routers
   and reaches `apps.*.api` transitively. Don't add the worker to the API.
3. **`Query(...)` is load-bearing** on `EventPage` in
   `backend/apps/catalog/schemas.py`. Without it, Ninja treats the schema-typed
   argument as a request body and the filters silently stop working.

## Current state of the code

- Backend: Django + Django Ninja. `backend/apps/` has the six MVP apps
  (ingestion, catalog, personalization, delivery, identity, editorial).
  `backend/domain/` is pure (stdlib only, plus `shared.constants`/`shared.ids`).
- Two Postgres schemas on one database: `personal` (default) and `catalog`.
  Always pass `using=` (`PERSONAL`/`CATALOG` from `shared.db`).
- The generated frontend client lives in `frontend/lib/api/` and is produced by
  `make client`. NEVER hand-edit it. `backend/tests/api/test_contract.py`
  fails until the committed schema matches the live API.
- `beat_schedule` is exactly one 60s tick. `backend/tests/worker/test_tick.py`
  enforces it. Source scheduling hangs off that tick; do not add beat entries.
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
cd frontend && pnpm lint && pnpm typecheck

# the local stack (postgres + redis + api + worker + beat + next)
docker compose up -d && make dev
```

Current baseline: **1649 backend tests pass, 98.95% coverage, 13 import
contracts kept, 0 broken.** The gates are 80% overall and 100% on `domain/`.

## Facts about the next work item you need

The AC file is at
`.specs-fire/intents/event-catalog-ingestion/work-items/real-feeds-and-e2e-proof.md`.
Read it first. Key points:

- **It needs a plan checkpoint (confirm mode).** The AC says "The user picks 2-3
  real public feeds at the plan checkpoint." Ask me which feeds, or propose
  candidates with a ToS/robots note, and get my decision before implementing.
  The set must cover at least two of JSON-LD, RSS and ICS.
- **CI must never touch the network.** The real-feed ingestion is a documented
  MANUAL step. The automated e2e test uses the fake fetch adapter only.
- **The e2e test must be idempotent**: register sources via commands → run the
  tick → read `GET /api/catalog/events` → re-run the tick → assert nothing
  changed.
- **An editorial group is also in scope** (handed on from run-014, AD-14): the
  same idempotent command (or a sibling) creates a group with `add`/`change`/
  `view` on `ingestion.Source`, `ingestion.Venue`, `ingestion.TosReview`, and
  `view` on `Event`, `EventStateChange`, `IngestionAuditEntry`. The local
  operator account uses that group, not superuser. A test asserts the exact
  permission set.
- **Existing pieces to reuse:**
  - `backend/config/management/commands/ingest_source.py` — `ingest_source
    <source_id> [--sync]`; `--sync` runs inline, otherwise it enqueues the
    worker job.
  - `backend/apps/ingestion/services/source_registry.py` — `register_source`,
    `update_source`, `pause_source`, `resume_source`, `record_tos_review`.
    A `crawl` source without an approved ToS review is refused; the ToS
    approval must be passed in the SAME command call.
  - `backend/apps/ingestion/services/venue_registry.py` —
    `register_venue`, `set_venue_timezone`.
  - `backend/worker/tasks.py` + `backend/apps/ingestion/services/scheduling.py`
    — the tick, the claim, the cadence.
  - `backend/adapters/crawl/fake.py` — the fake fetch adapter (CI default).
  - `backend/adapters/crawl/http.py` — the real HTTP adapter.
- **Adapter selection:** `ADAPTER_MODE=fake|real` in the env, and
  `SOURCE_FETCH=fake|http` overrides the fetch port alone
  (`backend/config/env.py`, `backend/config/adapters.py`). The fetch limits and
  the identifying user-agent are `SOURCE_FETCH_*` settings.
- **Respect the feeds:** use the source's declared cadence, an identifying
  user-agent, and no aggressive polling.
- **Docs to update:** `README.md` (or `docs/`) — registering a source,
  triggering ingestion, reading the catalog API, and the fake vs HTTP fetch
  adapter settings.

## Open questions carried on the intent

- **OQ-5 is still open.** The feeds you pick are LOCAL PROOF SOURCES, not the
  launch corpus. The 40-source / 15-per-city launch floor is untouched, and the
  beachhead city is still undecided.
- The PRD amendment for the FR-60 tier table is still owed
  (`prd.md:556` vs `prd.md:576`).
- Automatic re-gating vs editorial decisions (run-015, plan P1) — the editorial
  review queue (FR-57) does not exist yet.

## Standards

Read `.specs-fire/standards/` before writing code: `constitution.md`,
`tech-stack.md`, `coding-standards.md`, `testing-standards.md`,
`system-architecture.md`. The architecture spine is at
`_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md`.

## How the last few runs went (so you can match the bar)

Each run produces a folder in `.specs-fire/runs/` with `plan.md`, `run.md`,
`test-report.md`, `review-report.md` and `walkthrough.md`, and `state.yaml` is
updated ONLY through the scripts in
`.specsmd/fire/agents/builder/skills/run-execute/scripts/` — never by hand.

The bar the project holds itself to, and that the last runs met:
- A mutation probe per planted bug, proving the tests actually catch it
  (see `backend/tests/api/mutation_probe_catalog.py` for the pattern — 9 probes,
  all caught).
- The full gate set green: ruff, ruff format, import-linter, `manage.py check`,
  `makemigrations --check`, coverage with both gates, the OpenAPI/client
  contract check, and the frontend lint + typecheck.
- Deviations from the plan recorded with the reason, not silently absorbed.
```

---

## Quick reference for you (not for pasting)

**Committed:** `c5d95ff docs: close the public catalog read API run (run-eventpulse24-017)`
— 6 files, +654/−27. Working tree clean. Not pushed (no push was requested).

**The one thing to decide early:** which 2–3 real feeds to use. The AC makes it
an explicit plan checkpoint, and it's the only part of the next work item that
needs your judgement — everything else is mechanical once that's chosen.
