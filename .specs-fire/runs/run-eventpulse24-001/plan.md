---
run: run-eventpulse24-001
work_item: local-infra-and-setup-docs
intent: project-scaffold
mode: confirm
checkpoint: plan
approved_at: 2026-10-27
---

# Implementation Plan: Local Infrastructure & Setup Docs

## Approach

Docker Compose runs the infrastructure: Postgres 18 + pgvector, Redis and Mailpit. Every published port comes from `.env` with a default that avoids what's already on the Ubuntu machine:

| Existing on Ubuntu | Port |
|---|---|
| PostgreSQL 12 | 5432 |
| PostgreSQL 16 | 5434 |
| Docker container `pgdb_books` | **5433** (found at plan time) |
| Host Redis | 6379 |

So the project uses **Postgres :5440**, **Redis :6380**, and **Mailpit :1025 (SMTP) / :8025 (UI)**. The same compose file runs unchanged on macOS (Intel and Apple Silicon). A Postgres init script creates the two AD-3 schemas, the per-schema roles and the `vector` extension. A root `Makefile` is the single entry point. A POSIX `scripts/doctor.sh` checks prerequisites and ports on both OSes. Two setup guides and a README quick start document the flow.

**Deviation from the brief:** the brief says Postgres :5433, which turned out to be in use. The brief and the work item will be updated to **5440**, and the port stays overridable via `EP_PG_PORT`.

## Files to Create

| File | Purpose |
|------|---------|
| `docker-compose.yml` | `name: eventpulse24`. Services: `postgres` (pinned `pgvector/pgvector:<0.8.6>-pg18`; volume mounted at `/var/lib/postgresql` per the PG18 image layout), `redis` (`redis:8-alpine`, AOF off, used as broker only), `mailpit` (pinned `axllent/mailpit`). Each has a healthcheck; Postgres and Redis use named volumes. Ports via `${EP_*_PORT:-default}` |
| `docker/postgres/init/01-schemas-and-roles.sh` | Runs on first DB init. Creates schemas `catalog` and `personal` owned by the owner/migration role `ep_owner`, plus LOGIN roles `ep_catalog` and `ep_personal`, each granted USAGE and default DML privileges on **its own schema only**. Revokes all on the other schema and `CREATE` on `public`. Runs `CREATE EXTENSION vector`. Passwords come from env, never hard-coded beyond local defaults in `.env.example` |
| `.env.example` | Every variable with local defaults: ports, owner/catalog/personal DB URLs, `REDIS_URL`, `SMTP_HOST`/`SMTP_PORT`, `ADAPTER_MODE=fake`, `API_PORT=8000`, `WEB_PORT=3000` |
| `.gitignore` | `.env`, Python/Node build artifacts, `.venv`, `node_modules`, `.DS_Store`, `.specsmd/fire/node_modules` |
| `Makefile` | `help` (default), `env` (copy `.env.example` → `.env` if missing), `up` (`compose up -d --wait`), `down`, `reset-db` (`down -v` + `up`), `ps`, `logs`, `psql`, `db-check`, `doctor`. Includes `.env` |
| `scripts/doctor.sh` | POSIX `sh`, no GNU-only flags. Checks Docker daemon, compose v2, make, uv, Python 3.13 reachable via uv, Node ≥20.9, pnpm (hints `corepack enable`). Port check uses `lsof`, falling back to `ss`. A port held by this project's own containers counts as OK. Exits non-zero on a hard failure; 8000/3000 conflicts are warnings |
| `scripts/db-check.sh` | Verifies via `docker compose exec`: both schemas exist, `vector` extension installed, roles exist, `ep_catalog` is **denied** on `personal` and `ep_personal` is **denied** on `catalog`. Exits non-zero on any miss |
| `docs/setup/ubuntu.md` | Prerequisites (Docker Engine + compose plugin, uv, Node via nvm or NodeSource, pnpm via corepack), then run steps, port notes for this machine's PG12/PG16/`pgdb_books`/Redis, how to use a native PG18 + pgvector instead, troubleshooting |
| `docs/setup/macos.md` | Homebrew, Docker Desktop **or** OrbStack, uv, Node, pnpm; Apple Silicon vs Intel notes (the images are multi-arch); same run steps and native-PG notes |
| `README.md` | Project one-liner, Quick start (`make env && make doctor && make up && make db-check`), links to both guides and the planning artifacts |

## Files to Modify

| File | Changes |
|------|---------|
| `.specs-fire/intents/project-scaffold/brief.md` | Postgres port 5433 → 5440 (with reason) |
| `.specs-fire/intents/project-scaffold/work-items/local-infra-and-setup-docs.md` | Same port correction in the acceptance criteria |

## Tests

| Test File | Coverage |
|-----------|----------|
| `scripts/doctor.sh` (run) | Prerequisite and port detection on this Ubuntu machine |
| `docker compose up -d --wait` | All three containers report healthy |
| `scripts/db-check.sh` (run) | Schemas, extension and roles, plus **negative** cross-schema access checks |
| `shellcheck` (via `koalaman/shellcheck` container) | Both scripts POSIX-clean, so they're safe on macOS `/bin/sh` |
| `docker compose config` | Compose file valid with and without `.env` |

## Technical Details

- **Image pins:** the exact `pgvector/pgvector` tag for 0.8.6 on PG18 and the Mailpit version are confirmed with `docker manifest inspect` at implementation time. If the 0.8.6 tag isn't published, I pick the newest ≥0.8.4 (the HNSW vacuum fix) and record it.
- **Volume path:** the PG18 official image moved `PGDATA` to `/var/lib/postgresql/18/docker` and expects the volume at `/var/lib/postgresql`. Mounting the old `/var/lib/postgresql/data` path breaks upgrades, so the mount follows the new layout.
- **What the spike decides:** the init script only lays groundwork (schemas, roles, grants). The Django-side router, `search_path` per connection, which schema Django's own tables live in, and test-database creation belong to `schema-router-spike`. Its design doc may adjust the roles; the init script is idempotent and `make reset-db` re-applies it.
- **No app processes:** `make dev/api/worker/beat/web` arrive in later items. `make help` lists only the targets that exist.
- **Out of scope:** nothing is installed on the host by this item. The guides tell you what to install; `doctor.sh` only reports.

---
*Plan approved at checkpoint. Execution follows.*
