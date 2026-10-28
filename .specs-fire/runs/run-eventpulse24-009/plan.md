---
run: run-eventpulse24-009
work_item: ci-pipeline
intent: project-scaffold
mode: confirm
checkpoint: plan
revision: 2 (plan review: 4 points)
approved_at: 2026-10-28
---

# Implementation Plan: CI Pipeline (GitHub Actions)

## Approach

One workflow, `.github/workflows/ci.yml`, with three parallel jobs. **Each job runs the same `make` targets you run locally**, so CI and your machine can't drift apart.

```text
on: push (any branch) · pull_request (→ main)          permissions: contents: read
┌ backend ─────────────────────────┐ ┌ contract ───────────────────────┐ ┌ frontend ──────────────────────┐
│ services: pgvector 0.8.6-pg18,   │ │ uv + Node 24 + pnpm             │ │ Node 24 (.nvmrc) + pnpm        │
│           redis 8-alpine         │ │ make client (no database)       │ │ make web-install               │
│ init script into the PG service  │ │ git diff --exit-code            │ │ make lint-web                  │
│ make lint-backend (ruff+imports) │ │   frontend/lib/api/  (AD-19)    │ │ make test-web                  │
│ manage.py check                  │ └─────────────────────────────────┘ │ pnpm --dir frontend build      │
│ makemigrations --check --dry-run │                                     └────────────────────────────────┘
│ make coverage-backend            │
│   (≥80% overall, 100% domain/)   │
└──────────────────────────────────┘
```

**Run 009 was started by another session** this morning. It left `pytest-cov>=7.1.0` in `backend/pyproject.toml`. This plan keeps it but pins it exactly, **`pytest-cov==7.1.0`** (the current release), to match the other dev dependencies.

### 1. Triggers and safety

- **`push` to any branch, plus `pull_request` to `main`.**
  - Any pushed branch gets CI, which the verification below uses: a throwaway branch with a broken contract.
  - A branch with an open PR runs twice, once for the push and once for the PR. That's an accepted cost.
  - A `concurrency` group per workflow and ref cancels outdated runs, **except on `main`**: `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}` *(review 2)*.
    - On a feature branch, only the newest push matters.
    - On `main`, two merges a minute apart must **both** finish. Otherwise the first merge's commit never shows whether it passed.
- **`permissions: contents: read`** at the top level. No job can write to the repo.
- **Every third-party action is pinned to a full commit SHA**, with its version as a comment:
  - `actions/checkout` v7.0.1 `3d3c42e5…`
  - `actions/setup-node` v7.1.0 `949feb24…`
  - `actions/cache` v6.1.0 `55cc8345…`
  - `astral-sh/setup-uv` v10.3.2 `07a047e6…`

  A tag can be moved to different code; a SHA can't (supply-chain safety, per the constitution's "trusted sources").
- **`.github/dependabot.yml`** proposes action updates weekly, so the pins don't rot. It covers GitHub Actions only, not app dependencies, to keep the PR volume low.
- `NEXT_TELEMETRY_DISABLED=1`; `timeout-minutes` on each job.

### 2. Backend job

- **Services:** the same images as `docker-compose.yml`, `pgvector/pgvector:0.8.6-pg18` and `redis:8-alpine`, with health checks on the default ports.
- **Database init** (hand-off from schema-router-spike): Actions can't mount `docker/postgres/init/`, so a step runs **`docker exec -i <pg container> sh -s < docker/postgres/init/01-schemas-and-roles.sh`**, passing `POSTGRES_USER`, `POSTGRES_DB` and the `EP_*_PASSWORD` values.
  - That's the same script and the same `psql` as on your machines, not whatever `psql` the runner happens to have.
  - It creates the schemas, roles, test template and `ep_owner CREATEDB`.
- **Environment:**
  - test-only values for `DJANGO_SECRET_KEY`, the three `DATABASE_URL_*` and `REDIS_URL`, pointing at the services
  - `ADAPTER_MODE=fake`
  - no real secrets anywhere
- **Steps:**
  1. `setup-uv` with cache keyed on `backend/uv.lock`, then `uv sync --locked`
  2. `make lint-backend` (ruff check, format check, `lint-imports`)
  3. `make manage ARGS=check`
  4. `makemigrations --check --dry-run` as the owner role (the hand-off says it needs the live database)
  5. **`make coverage-backend`**, a new target

**Coverage** *(new: `[tool.coverage.*]` in `pyproject.toml` and a `make coverage-backend` target)*:
- **Measured over the application packages only:** `domain`, `apps`, `ports`, `adapters`, `config`, `worker`, `shared`. Plain `--cov=.` would also count the test files and inflate the number.
- **Overall gate `fail_under = 80`**, as testing-standards says. Today it's **97%** (884 statements, 27 missed, mostly the empty `apps/*/api.py` stubs and `wsgi`/`asgi`).
- **`domain/` gate 100%:** a second `coverage report --include='domain/*' --fail-under=100`. Coverage has no per-folder thresholds, so this is a separate step. It's 100% today.
- **Line coverage, not branch coverage,** matching the standard as written. Switching to branch coverage later is a one-line change.
- **Locally:** `make coverage-backend` runs exactly what CI runs.

### 3. Contract job (AD-19)

- **Steps:** uv sync, Node 24, pnpm install, then **`make client`** (exports `openapi.json` and regenerates `schema.ts`), then **`git diff --exit-code frontend/lib/api/`**. If the diff is non-empty, the job fails and prints it.
- **No database service:** the export only imports Django. It gets the same test-only env values as the backend job, for `config.env`.
- `backend/tests/api/test_contract.py` already catches the schema half inside the backend job; this job also catches a stale `schema.ts`.

### 4. Frontend job

- **Node from `.nvmrc`** via `setup-node` (`node-version-file`), which resolves the latest 24.x (≥24.15 for `engineStrict`). Then `corepack enable` for pnpm at `packageManager`.
- **pnpm store cached** with `actions/cache`, keyed on `frontend/pnpm-lock.yaml`. setup-node's own `cache: pnpm` needs pnpm before Node is set up, which corepack can't provide.
- **Steps:**
  1. `make web-install` (`--frozen-lockfile`)
  2. `make lint-web` (ESLint, `next typegen` + `tsc`, Prettier)
  3. `make test-web` (Vitest; `tokens.test.ts` reads DESIGN.md from the full checkout)
  4. `pnpm --dir frontend build`
- **The build isn't in the acceptance criteria**, but the frontend-skeleton hand-off asked for it: it catches errors only a production build sees. It downloads the Google fonts, so it needs network, which Actions has. It runs without `API_BASE_URL`, which run 008 proved works.

### 5. Verification on GitHub (needs your go-ahead at that point)

The acceptance criterion "green on a PR; a deliberately broken contract makes it red" needs **pushing to GitHub**. That's outward-facing, so **I'll stop and ask before each push**:

1. **Push `setup-specsmd`** and open a PR to `main`. Today it has **3** commits that aren't on GitHub (runs 006–008; `origin/setup-specsmd` is at `36b99f6`). Once this run is committed, that's **4** *(review 1)*.
   - **The `gh` CLI isn't installed on this Mac.** Either you open the PR on github.com from the pushed branch, or you install `gh` (`brew install gh && gh auth login`) and I open it.
   - **Expected:** all three jobs green.
2. **Push a throwaway branch** off it, with one planted contract break: change the health endpoint's `summary` without running `make client`.
   - **Expected:** the contract job and the backend job's `test_contract.py` go red, and the frontend job stays green.
   - Then I delete the throwaway branch, locally and on GitHub. That's a deletion, so I'll confirm it with you too.

Before any push, the workflow file is checked locally with `actionlint`, a static checker for GitHub workflows.
- It runs in a throwaway Docker container (`rhysd/actionlint`, pinned by digest), so nothing is installed on your Mac.
- It catches YAML, expression and shell (`shellcheck`) mistakes before they cost a CI run.

## Files to Create

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | The workflow |
| `.github/dependabot.yml` | Weekly updates for the pinned actions |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/pyproject.toml`, `uv.lock` | `pytest-cov==7.1.0` (pinning the other session's `>=`); `[tool.coverage.run]` (the seven application packages as sources) and `[tool.coverage.report]` (`fail_under = 80`, `show_missing`) |
| `Makefile` | `coverage-backend` |
| `README.md`, `docs/setup/{macos,ubuntu}.md` | `make coverage-backend`; "CI runs these same targets" |
| `.specs-fire/standards/testing-standards.md` | Coverage measured over application packages; the two gates and where they run; which CI job runs each gate. **The constitution isn't touched:** it's the governing document, and a CI task shouldn't edit it, even for wording *(review 4)*. |

**Migrations in coverage:** they're executed by the test database setup, so they count as covered, and that's correct. They stay in.

## Tests

The workflow itself is the test. Locally first:
- `make coverage-backend` passes (≥80%, `domain/` 100%), and fails when the threshold is raised above the current number (a mutation check)
- `actionlint` is clean on `ci.yml`
- the contract step's commands run locally from a clean checkout of `lib/api/` and produce no diff; a planted summary change makes `git diff --exit-code` fail

On GitHub (step 5): green on the PR, red on the planted branch.

## Bookkeeping note *(review 3)*

`state.yaml` shows this run's checkpoint as `awaiting_approval` while `run.md` still says `checkpoint_state: none`. That's how the FIRE scripts work:
- `update-checkpoint.cjs` and `update-phase.cjs` write **only** `state.yaml`
- only `complete-run.cjs` rewrites `run.md`, at the end
- the builder rules forbid editing run artifacts by hand

So `state.yaml` is authoritative while a run is open, and `run.md` catches up at completion. Runs 006–008 behaved the same way.

## Not in this item

- **Playwright + axe-core:** with the first real surfaces (the work item says so)
- **Branch protection** (required checks, no self-merge per the constitution): a GitHub repository setting that you switch on in the repo's settings once CI is green. I'll list the exact check names to require.
- **Deploy workflows:** the deployment intent

---
*`approved_at` is set when you approve at the checkpoint; until then this plan is a draft.*
