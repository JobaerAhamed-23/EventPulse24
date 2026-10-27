---
run: run-eventpulse24-001
work_item: local-infra-and-setup-docs
intent: project-scaffold
generated: 2026-10-27
mode: confirm
---

# Implementation Walkthrough: Local Infrastructure & Setup Docs

## Summary

EventPulse24 now has a one-command local infrastructure that runs the same way on Ubuntu and macOS. It is made up of:

- PostgreSQL 18 with pgvector 0.8.6, Redis 8 and Mailpit in Docker Compose
- a Makefile entry point
- a POSIX prerequisite checker (`doctor.sh`) and a database verifier (`db-check.sh`)
- per-OS setup guides

The database already lays the groundwork for the architecture's public/personal data wall (AD-3): two schemas, each reachable only by its own runtime role. This is proven by negative tests.

## Structure Overview

The developer interacts only with `make`. `make up` starts the Compose stack. On the first start of an empty volume, Postgres runs the init script, which creates the schemas, roles, grants and the vector extension. `make doctor` checks the host before anything runs. `make db-check` checks the running database afterwards. All host ports and passwords come from a per-machine `.env`, created from the committed `.env.example`, so the Ubuntu box and the Mac can differ without touching tracked files. App processes (Django, Celery, Next.js) will run natively on the host and reach the containers through `127.0.0.1` ports. They arrive in later work items.

```text
make ──► doctor.sh            (host: tools + ports, read-only)
     ──► docker compose up    ──► postgres  :5440  ── init script (first boot) ─► catalog | personal | vector
                              ──► redis     :6380  (broker, no persistence)
                              ──► mailpit   :1025 smtp / :8025 web
     ──► db-check.sh          (inside postgres container: schemas, roles, isolation)
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Postgres 18 + pgvector 0.8.6, Redis 8, Mailpit v1.32; ports from `.env`, bound to 127.0.0.1; healthchecks |
| `docker/postgres/init/01-schemas-and-roles.sh` | Schemas `catalog`/`personal`, roles `ep_owner`/`ep_catalog`/`ep_personal`, grants, `vector` |
| `.env.example` | Every local setting with defaults |
| `.gitignore` | Ignores `.env`, Python/Node artifacts, FIRE tooling `node_modules` |
| `Makefile` | `help env doctor up down reset-db ps logs psql db-check` |
| `scripts/doctor.sh` | POSIX prerequisite + port checker (Linux and macOS) |
| `scripts/db-check.sh` | Database verifier, including negative isolation checks |
| `docs/setup/ubuntu.md` | Ubuntu guide (incl. this machine's existing services) |
| `docs/setup/macos.md` | macOS guide (Apple Silicon + Intel; OrbStack or Docker Desktop) |
| `README.md` | Project overview + quick start |

### Modified

| File | Changes |
|------|---------|
| `.specs-fire/intents/project-scaffold/brief.md` | Postgres port 5433 → 5440 |
| `.specs-fire/intents/project-scaffold/work-items/local-infra-and-setup-docs.md` | Same port correction |

## Key Implementation Details

### 1. Ports avoid every service already on the machine

Defaults are Postgres 5440, Redis 6380, Mailpit 1025/8025. They avoid:

- system PG12 on 5432
- the `pgdb_books` container on 5433
- system PG16 on 5434
- host Redis on 6379

Every container port binds to `127.0.0.1` only.

### 2. Roles model the AD-3 wall at the database level

- `ep_owner` owns both schemas and will run migrations (DDL).
- `ep_catalog` and `ep_personal` get DML on their own schema only. `ALTER DEFAULT PRIVILEGES FOR ROLE ep_owner` covers every table that migrations create later.
- CREATE on `public` is revoked from everyone.
- Each runtime role has `search_path = <own schema>, public` so the `vector` type in `public` resolves.

### 3. The checks are proven to fail

- **doctor.sh** reports a port as "ours" only if the project's container actually publishes that exact port (`docker compose port`). Otherwise a foreign process on that port is a FAIL, or a WARN for app ports.
- **db-check.sh** runs real cross-schema queries and expects `permission denied`. A deliberately broken grant during testing turned it red.

### 4. Healthy means initialized

The Postgres healthcheck uses `pg_isready -h 127.0.0.1`. During init scripts the server only listens on the unix socket, so `make up` (`--wait`) returns only after initialization has completed.

## Security Considerations

| Concern | Approach |
|---------|----------|
| Network exposure | All published ports bind to `127.0.0.1` |
| Secrets in git | `.env` ignored; `.env.example` holds clearly-labelled local-only defaults |
| Least privilege | Runtime roles are DML-only on one schema; no runtime role is superuser; `public` CREATE revoked |
| Destructive commands | `make reset-db` requires interactive confirmation (or explicit `FORCE=1`) |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Postgres host port | 5440 | 5433 was already taken by `pgdb_books` |
| Image pins | `pgvector/pgvector:0.8.6-pg18`, `redis:8-alpine`, `axllent/mailpit:v1.32` | Matches the spine's pgvector version exactly; tags verified with `docker manifest inspect` |
| PG18 volume mount | `/var/lib/postgresql` | The PG18 image moved PGDATA under `/var/lib/postgresql/18/docker` |
| Redis persistence | Off | Broker only. AD-7 keeps the reminder schedule in Postgres, so Redis loss is acceptable |
| Superuser vs owner | Separate `postgres` superuser; `ep_owner` is not superuser | Migrations shouldn't run as superuser; mirrors a managed DB like Neon |
| Port detection | `ss` on Linux, `lsof` then `nc -z` on macOS | Non-root `lsof` on Linux can't see root-owned listeners such as docker-proxy |
| Make + `.env` | `-include .env` + `export` | One config source for make, compose and the scripts. Values must not contain `$` (documented) |

## Deviations from Plan

- **Postgres port:** 5440 instead of 5433, which the brief assumed was free. The brief and work item were updated.
- **No other deviations.** Everything in the plan's file list was delivered, and the tests ran as planned, plus extra negative tests and a native-PG procedure test.

## Dependencies Added

| Package | Why Needed |
|---------|------------|
| `yaml` (npm, tooling only, outside the app) | Required by the FIRE run scripts; resolved for `.specsmd/fire` scripts and git-ignored |

No application dependencies yet.

## How to Verify

1. **Check prerequisites**
   ```bash
   make env && make doctor
   ```
   Expected: all `[ ok ]`

2. **Start infrastructure**
   ```bash
   make up && make ps
   ```
   Expected: postgres, redis, mailpit all `(healthy)`

3. **Verify the database**
   ```bash
   make db-check
   ```
   Expected: 13 `[ ok ]` lines and `Result: database ready.`

4. **Mail inbox**
   ```bash
   open http://127.0.0.1:8025   # or xdg-open on Ubuntu
   ```
   Expected: Mailpit web UI loads

## Test Coverage

- Tests added: 26 verification checks (2 static, 21 integration, 3 negative)
- Coverage: n/a (no application code yet; recorded as 0 in run metadata)
- Status: passing

## Ready for Review

- [ ] All acceptance criteria met (one open: run the macOS guide on the Mac)
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated (if applicable)
- [x] Developer notes captured

## Developer Notes

- **Roles are created only on first init.** Changing passwords in `.env` later needs `make reset-db`.
- **`db-check` checks the Docker database only.** If you switch to native Postgres, verify it manually or adapt the script.
- **macOS `lsof`** only sees your own processes, so doctor falls back to `nc -z`. A port held by another user's process is still caught.
- **`search_path` with `public`** is a placeholder. `schema-router-spike` decides the final per-connection `search_path` and where Django's own tables live, and may adjust the init script. `make reset-db` re-applies it.
- **Skipped review suggestion:** a `trap` cleanup in `db-check.sh`. Low value: leftovers only occur on Ctrl-C, the next run removes them, and CI starts from a fresh container.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-001*
