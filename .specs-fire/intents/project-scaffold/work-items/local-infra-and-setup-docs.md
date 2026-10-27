---
id: local-infra-and-setup-docs
title: Local Infrastructure & Setup Docs
intent: project-scaffold
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-10-27
run_id: run-eventpulse24-001
completed_at: 2026-10-27T09:05:49.710Z
---

# Work Item: Local Infrastructure & Setup Docs

## Description

Run the project's infrastructure (Postgres 18 + pgvector, Redis, Mailpit) in Docker Compose on ports that don't clash with the services already on the Ubuntu machine (PG12 :5432, `pgdb_books` container :5433, PG16 :5434, Redis :6379). Provide one setup path that works the same on Ubuntu 20.04 and macOS (Intel + Apple Silicon).

## Acceptance Criteria

- [ ] `docker-compose.yml` defines `postgres` (`pgvector/pgvector:pg18`, host port **5440**), `redis` (host port **6380**) and `mailpit` (SMTP **1025**, UI **8025**), each with a healthcheck and a named volume where state matters
- [ ] A Postgres init script creates schemas `catalog` and `personal`, a login role per schema (`ep_catalog`, `ep_personal`) granted on its own schema only, a migration/owner role, and `CREATE EXTENSION vector`
- [ ] `.env.example` lists every variable (DB URLs per schema, Redis URL, SMTP host/port, adapter mode = fake) with local defaults; `.env` is git-ignored
- [ ] Root `Makefile` with at least `up`, `down`, `reset-db` (`down -v` + `up`), `doctor`, `logs`; later items add `dev`, `api`, `worker`, `beat`, `web`
- [ ] `scripts/doctor.sh` runs on both Linux and macOS (POSIX-safe; no GNU-only flags) and reports: Docker running, compose v2, uv, Node ≥20.9, pnpm, and whether ports 5440/6380/1025/8025/8000/3000 are free
- [ ] `docs/setup/ubuntu.md` and `docs/setup/macos.md` give step-by-step prerequisite installs (macOS via Homebrew; Docker Desktop or OrbStack) and the run steps; Ubuntu doc notes the existing PG12/PG16/Redis and why the project uses different ports
- [ ] Both docs explain how to point `DATABASE_URL`s at a native PG18 + pgvector instead of Docker
- [ ] README has a Quick start section linking both guides
- [ ] Verified: `make doctor` passes, `docker compose up -d` brings all three containers to healthy, `psql` on :5440 shows both schemas and `vector` extension

## Technical Notes

- Compose file must use no host-specific paths; the same file runs on both OSes.
- Redis in Docker is separate from the host Redis on :6379 — do not reuse the host one.
- Mailpit replaces any real email provider locally (AD-20 streams are still distinguished at the port level; see ports-fakes-and-worker).

## Dependencies

(none)
