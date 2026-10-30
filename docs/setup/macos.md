# Local setup — macOS

Works on Apple Silicon (M-series) and Intel Macs. Every Docker image the project uses is multi-arch, so no Rosetta or platform flags are needed.

EventPulse24 uses **hybrid local dev**:

- **Docker** runs the infrastructure: PostgreSQL 18 + pgvector, Redis and Mailpit.
- **Your Mac** runs the app processes (Django API, Celery worker and beat, Next.js) with hot reload. Later work items add these; this guide sets up the base they need.

Ubuntu? See [ubuntu.md](ubuntu.md). The steps are the same apart from installing the prerequisites.

## 1. Prerequisites

| Tool | Version | Why |
|---|---|---|
| Docker Desktop **or** OrbStack | Compose v2 (`docker compose`) | Postgres, Redis, Mailpit |
| `make` | any (Xcode Command Line Tools) | Project commands |
| `uv` | recent | Python 3.13 + backend dependencies |
| Node.js | **24 LTS** (≥ 24.15; the repo's `.nvmrc` says `24`) | Next.js frontend |
| `pnpm` | ≥ 10 | Frontend package manager |

Check what you already have at any time:

```bash
make doctor
```

### Homebrew and command line tools

If you don't have them yet:

```bash
xcode-select --install          # provides make, git
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Docker

Pick **one** and start it once so the daemon is running:

```bash
brew install --cask orbstack    # lighter and faster on Apple Silicon; recommended
# or
brew install --cask docker      # Docker Desktop
```

Both provide `docker compose` (v2).

### uv and Python 3.13

```bash
brew install uv
uv python install 3.13
```

uv manages its own Python 3.13, independent of the macOS system Python and any Homebrew Python.

### Node.js and pnpm

Using **nvm** (recommended; keeps other Node versions side by side):

```bash
nvm install 24          # Node 24 LTS
nvm alias default 24
corepack enable pnpm    # pnpm, at the version frontend/package.json names
```

Or with Homebrew: `brew install node@24 && brew link --overwrite node@24 && corepack enable pnpm`.

## 2. First run

From the repository root:

```bash
make env        # create .env from .env.example (never overwrites an existing one)
make doctor     # all [ ok ]? if a port is taken, change it in .env
make up         # start Postgres, Redis, Mailpit and wait until healthy
make db-check   # verify schemas, pgvector, roles and schema isolation
make migrate    # create the tables in both schemas (runs as the owner role)
```

Run `make` with no arguments to list every command.

| Service | Address |
|---|---|
| Postgres 18 + pgvector | `127.0.0.1:5440`, database `eventpulse24` |
| Redis (Celery broker) | `127.0.0.1:6380` |
| Mailpit SMTP | `127.0.0.1:1025` |
| Mailpit inbox (web) | <http://127.0.0.1:8025> |

All ports bind to `127.0.0.1` only.

## 3. Ports

The defaults avoid the usual Mac clashes: Postgres.app or Homebrew Postgres on 5432, Homebrew Redis on 6379. If a port is still taken:

1. Change the port in `.env` (`EP_PG_PORT`, `EP_REDIS_PORT`, `EP_SMTP_PORT`, `EP_MAILPIT_UI_PORT`, `API_PORT`, `WEB_PORT`).
2. **Also update the port inside the matching URL** (`DATABASE_URL_*`, `REDIS_URL`).
3. Run `make up` again.

`make doctor` lists what's taken. On macOS it uses `lsof`, which only sees processes owned by your user, so it falls back to a connection test (`nc -z`) to catch the rest.

`.env` is per machine and not committed, so the Mac and the Ubuntu box can use different ports.

## 4. Database layout

The init script (`docker/postgres/init/01-schemas-and-roles.sh`) runs on the first start of an empty volume and creates:

| Role | Can do |
|---|---|
| `ep_owner` | Owns schemas `catalog` and `personal`; runs migrations |
| `ep_catalog` | Read/write tables in `catalog` only |
| `ep_personal` | Read/write tables in `personal` only |

The `vector` extension lives in `public`, and both runtime roles can use it. `make db-check` proves each role is denied access to the other schema (architecture AD-3).

Connect with `make psql` (superuser) or any client, for example:

```bash
psql postgresql://ep_owner:ep_owner_local@127.0.0.1:5440/eventpulse24
```

No local `psql`? Run `brew install libpq` and follow its PATH hint, or just use `make psql`.

## 5. Updating an existing `.env`

`.env` is created once and never overwritten. When new settings are added to `.env.example`, `make doctor` reports them:

```
  [FAIL] .env is missing: DJANGO_SECRET_KEY ... — copy them from .env.example
```

Copy those lines from `.env.example` into your `.env`, then run `make doctor` again. Do this on each machine.

When the database setup itself changes (for example, the test template and `CREATEDB` added by the schema-router spike), `make db-check` reports what's missing. Apply it to your existing database without losing data, then migrate:

```bash
make db-init    # re-apply docker/postgres/init/01-schemas-and-roles.sh (safe to re-run)
make migrate
```

## 6. Everyday commands

```bash
make up         # start (data is kept between runs)
make down       # stop (data is kept)
make ps         # status
make logs       # follow logs
make reset-db   # DELETE all local data and re-create it (asks first; FORCE=1 skips the prompt)
make migrate    # apply migrations to both schemas as the owner role
make db-init    # re-apply the database init script (keeps data)
make api        # run the Django API on http://127.0.0.1:8000 (docs at /api/docs)
make worker     # run the Celery worker (background jobs), one job at a time
make beat       # run Celery beat, the 60-second tick scheduler (exactly ONE at a time)
make send-test-email   # send a test email to Mailpit (TO=… STREAM=bulk to vary it)
make web-install       # install the frontend dependencies (first time, and after pulls)
make web               # run the Next.js frontend on http://127.0.0.1:3000
make test-web          # frontend tests (Vitest)
make lint-web          # ESLint + typecheck + Prettier check
make test-backend
make coverage-backend # tests + coverage gates (>=80% overall, 100% domain/), as CI runs them
make lint-backend   # ruff + format check + import contracts (make lint-imports runs only the contracts)
```

### Everything at once: `make dev`

After `make up` (and `make migrate` once), `make dev` runs the API, the worker, beat and Next.js together, each line prefixed with `[api]`, `[worker]`, `[beat]` or `[web]`. Ctrl-C stops all four; beat removes its pidfile on the way out. If a beat is already running, `make dev` says so and starts the other three.

Open <http://127.0.0.1:3000/dev/health> (a developer page; it doesn't exist in production builds). Each component shows **OK** or **Down** with the reason. `docker compose stop redis` turns Redis to Down (the API answers 503); `docker compose start redis` brings it back.

- **The browser only talks to Next.js.** `frontend/proxy.ts` forwards `/api/*` to `API_BASE_URL` (default `http://127.0.0.1:8000`), read per request: change it in `.env` and restart, no rebuild.
- **Django must trust the frontend's origin.** The browser's writes arrive through the proxy carrying the Next.js origin, so `CSRF_TRUSTED_ORIGINS` lists it (`.env.example` has the local values). Without it every `POST` answers `403 csrf_failed`. In production it is the site's own origin.
- **After changing an API endpoint, run `make client`.** It exports the schema to `frontend/lib/api/openapi.json` and regenerates `schema.ts`. The backend suite fails until the committed schema matches the API.

### Frontend

`make web-install` once, then `make web` and open <http://127.0.0.1:3000>. The first run downloads the three fonts (Source Serif 4, Inter, JetBrains Mono) and serves them from the app itself, so it needs internet once.

- **Node 24 is enforced:** with an older Node, `pnpm install` stops with `ERR_PNPM_UNSUPPORTED_ENGINE`. Run `nvm install 24` (or `nvm use` in the repo, which reads `.nvmrc`).
- **Dark is the default theme.** To see light mode, set `data-theme="light"` on `<html>` in the browser's devtools. The theme never follows the OS setting.
- Styling uses only the design tokens in `frontend/styles/tokens.css`. Tailwind's own colors, shadows and animations are switched off (see `frontend/README.md`).

### Background worker and beat

Run `make worker` and `make beat` in two terminals (alongside `make api`). Every 60 seconds beat sends a `tick`; the worker logs a JSON line with `"message": "Tick"`. The tick does nothing else yet: later work hangs the reminder sweep on it (AD-7).

- **Run exactly one beat.** Two beats would send every tick twice. `make beat` writes a pidfile (`backend/.celery/beat.pid`), so a second `make beat` refuses to start while the first runs ("Pidfile … already exists"). If beat was killed hard and the pidfile is left behind with no beat running, delete it.
- **The worker runs one job at a time** (`--pool solo`), the same on macOS and Ubuntu. Celery 5.6.3's default multi-process pool breaks on macOS, where every task fails with `not enough values to unpack`.
- **Email:** with `ADAPTER_MODE=fake` (the default), email really goes out over SMTP to Mailpit, and nothing else needs an API key. `make send-test-email` sends one; open <http://127.0.0.1:8025>. Each message carries an `X-Eventpulse-Stream` header (`transactional` or `bulk`).

## 7. Using a native PostgreSQL 18 instead of Docker (optional)

Docker is the supported path, because it keeps both machines on identical versions. If you already run PostgreSQL 18 natively (Postgres.app or `brew install postgresql@18`) and have **pgvector ≥ 0.8.4** for it:

1. Create the database: `createdb eventpulse24`.
2. Apply the same init script with your connection settings:

   ```bash
   PGHOST=127.0.0.1 PGPORT=5432 POSTGRES_USER="$USER" POSTGRES_DB=eventpulse24 \
   EP_OWNER_PASSWORD=ep_owner_local EP_CATALOG_PASSWORD=ep_catalog_local \
   EP_PERSONAL_PASSWORD=ep_personal_local \
   sh docker/postgres/init/01-schemas-and-roles.sh
   ```

3. Point `DATABASE_URL_OWNER`, `DATABASE_URL_CATALOG` and `DATABASE_URL_PERSONAL` in `.env` at it.
4. Start only the other services: `docker compose up -d --wait redis mailpit`.

`make db-check` checks the Docker database only.

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot connect to the Docker daemon` | Open OrbStack / Docker Desktop and wait until it's running |
| `docker: command not found` right after installing Docker Desktop | Docker Desktop puts its CLI in `~/.docker/bin` and adds that to `~/.zprofile` on first launch: open a new terminal |
| `make doctor` shows `[FAIL] port … in use` | Change that port in `.env` (and in the matching URL), then `make up` |
| Postgres never becomes healthy | `make logs`; a volume from a different Postgres major version needs `make reset-db` |
| Changed passwords in `.env` but login fails | Roles are created only on first init. Run `make reset-db` |
| Slow file access later with app containers | Not applicable: app processes run natively on the Mac |
