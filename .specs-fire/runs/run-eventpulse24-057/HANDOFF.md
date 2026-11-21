# Handoff — run-eventpulse24-057

**This run is complete.** 11 of 11 items delivered, the run-level `walkthrough.md` is
written, and the run is closed.

Branch `city-picker-and-auto-collection`, working tree clean, nothing pushed.

## Where things stand

| # | Item | Mode | Commit |
|---|---|---|---|
| 1 | `city-catalog-dataset` | confirm | `e39d367` |
| 2 | `source-city-timezone` | validate | `6dd8d96` |
| 3 | `api-source-parser` | confirm | `2a0a647` |
| 4 | `city-choices-endpoint` | confirm | `d1a9218` |
| 5 | `stored-city-is-the-picked-city` | validate | `0478ca2` |
| 6 | `city-provider-templates` | confirm | `016ae08` |
| 7 | `city-provisioning-service` | validate | `76496e4` |
| 8 | `provisioning-probation` | confirm | `4635600` |
| 9 | `browse-collecting-states` | confirm | `0a6579b` |
| 10 | `city-coverage-request` | confirm | `618eb2d` |
| 11 | `home-city-dropdown-catalog` | confirm | `ec02e54` |

Suite at HEAD: **9091 backend passed**, **2957 frontend passed** (184 files), typecheck
clean, lint 0 errors, **39 mutations — 39 caught, 0 survived**, 21 import contracts kept.

**The run-level `walkthrough.md` is in this folder** and is the summary of all eleven
items — read it first.

## The intent's guarantee, and where it is held

> **"The stored city is the picked city. Never silently rewritten to anything else."**

- **The rule** — `backend/apps/personalization/services/digest_preferences.py`. A city the
  catalog holds is stored verbatim (682 whole-dataset cases); a city it does not hold is
  **refused** with a 422, and nothing is stored. A *geo guess* and a *backfill* still
  fall back — only a *choice* is refused.
- **The world it is checked against** — `backend/domain/city_catalog.py`, 166 cities.
- **The offering** — `GET /api/public/cities`, session-free. The picker reads it
  (item 11); the preview keeps its own list, because it answers a different question.
- **The consequence** — `backend/apps/ingestion/services/city_provisioning.py`: a pick
  provisions the city. `city_probation.py`: the city is `live`, `yielded_nothing`,
  `paused`, or still `collecting`.
- **The surface** — Browse says one of four honest things, and the no-sources dead end
  offers a coverage request.

## Decisions already taken (do not re-litigate)

Every one of these is recorded in the run's `walkthrough-<item-id>.md` and in `run.md`'s
Decisions list. The ones most likely to be re-litigated:

| Decision | Taken | Where |
|---|---|---|
| A city outside the catalog is **refused** (422), not substituted | item 5 | `walkthrough-stored-city-is-the-picked-city.md` |
| A **geo guess** and a **backfill** still fall back | item 5 | same |
| The catalog's two forms are **different strings** — value stored, label read | items 1, 11 | `walkthrough-home-city-dropdown-catalog.md` |
| The Eventbrite template is **disabled**, not omitted | item 6 | `walkthrough-city-provider-templates.md` |
| A pick **provisions**; it is **not** a retry request | item 7 | `walkthrough-city-provisioning-service.md` |
| `unchanged` **is** yield; a 304 **leaves** the counter alone | item 8 | `walkthrough-provisioning-probation.md` |
| Publication is narrow — only `new` and `superseded` make a city `live` | item 8 | same |
| The coverage request is **one row per city**, not per reader | item 10 | `walkthrough-city-coverage-request.md` |
| The coverage-request **count is on the wire, not on the screen** | item 10 | same |
| The picker reads the **catalog**, not the preview's list | item 11 | `walkthrough-home-city-dropdown-catalog.md` |

## Environment gotchas (unchanged)

- **Docker on this machine is macOS** — use `open -a Docker`, not `systemctl`.
- **Never run `ruff format .` from the repo root.** Format only the directories being
  worked in. `backend/tests/shared/test_retention_published.py` has pre-existing drift.
- Backend commands go through `uv run --directory backend …`.
- Changing the API surface requires `make client` (regenerates `openapi.json` **and**
  `schema.ts`); `tests/api/test_contract.py` fails until you do.
- `pnpm` commands must be run from `frontend/`. The scripts are `pnpm test`,
  `pnpm typecheck` (not `type-check`), `pnpm lint`, `pnpm format:check`.

## Practices this run held to

- **Every whole-dataset invariant is mutation-checked** before a test report is written.
  **39 mutations, 39 caught, 0 survived.** A mutation that survives is a missing test.
- Architecture guards are treated as right by default; they were changed only with the
  reason recorded next to them.
- Every work item's artifacts are `plan-`, `test-report-`, `review-report-` and
  `walkthrough-<item-id>.md` in this folder, plus the run-level `walkthrough.md`.

## Still open

- **Nothing is pushed and no PR exists.** Eleven commits sit on
  `city-picker-and-auto-collection`.
- **The Eventbrite template waits for a person** — its Terms restrict automated access.
  The shape is in the registry; enabling it is one constant after a review.
- **The coverage-request queue has no editor UI.** The row, the counter, the read-only
  admin and the throttled endpoint all exist; acting on the queue does not.
- **The catalog is hand-maintained.** 166 cities is a snapshot, with a whole-dataset test
  behind every invariant.
- **`pnpm format:check` reports 44 unformatted files** — one *fewer* than the branch
  started with. The remainder is pre-existing drift and is not this run's to fix.
