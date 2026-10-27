# EventPulse24

AI-powered event discovery and notification platform. It collects events from many sources, deduplicates them, and delivers personalized Pulse Digests, reminders and conflict-aware scheduling.

## Quick start

Prerequisites: Docker (Compose v2), `make`, `uv`, Node.js 24 LTS and `pnpm`. Follow the guide for your OS:

- **Ubuntu:** [docs/setup/ubuntu.md](docs/setup/ubuntu.md)
- **macOS:** [docs/setup/macos.md](docs/setup/macos.md)

```bash
make env        # create .env from .env.example
make doctor     # check prerequisites and ports
make up         # start Postgres 18 + pgvector, Redis, Mailpit
make db-check   # verify the database is ready
make migrate    # create the tables in both schemas (catalog, personal)
make api        # Django API on http://127.0.0.1:8000 (docs: /api/docs)
make worker     # Celery worker (another terminal)
make beat       # Celery beat, the 60s tick: run exactly ONE (another terminal)
make web-install && make web   # Next.js frontend on http://127.0.0.1:3000 (another terminal)
```

Already set up before? Run `make db-init && make migrate` to bring an existing database up to date (keeps data).

Run `make` to list all commands. The Mailpit inbox is at <http://127.0.0.1:8025>; `make send-test-email` puts a message there. With `ADAPTER_MODE=fake` (the default) the AI, embeddings, billing and calendar run on local stand-ins, so no API keys are needed.

Before pushing, run `make test-backend && make lint-backend && make test-web && make lint-web`. `lint-backend` covers Ruff, the format check and the architecture's import contracts (`make lint-imports` runs only the contracts).

## Repository layout

| Path | What |
|---|---|
| `backend/` | Django + Ninja backend (uv project, Python 3.13) |
| `frontend/` | Next.js 16 client (pnpm, Node 24); design tokens in `frontend/styles/` |
| `docker-compose.yml`, `docker/` | Local infrastructure |
| `scripts/` | `doctor.sh` (prerequisite checks), `db-check.sh` (database checks) |
| `docs/setup/` | Per-OS setup guides |
| `_bmad-output/planning-artifacts/` | PRD, UX design, architecture spine |
| `.specs-fire/` | FIRE intents, work items, runs and project standards |

## Architecture

The architecture spine is the binding reference for all code:
[`_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md`](_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md).
A condensed view and coding standards live in [`.specs-fire/standards/`](.specs-fire/standards/).
