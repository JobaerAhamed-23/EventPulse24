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
| Node.js | ≥ 20.9 (22 LTS recommended) | Next.js frontend |
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

```bash
brew install node@22
brew link --overwrite node@22   # if another Node version is already linked
brew install pnpm
```

Or, if you use **nvm**: `nvm install 22 && corepack enable pnpm`.

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
make test-backend
make lint-backend   # ruff + format check + import contracts (make lint-imports runs only the contracts)
```

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
| `make doctor` shows `[FAIL] port … in use` | Change that port in `.env` (and in the matching URL), then `make up` |
| Postgres never becomes healthy | `make logs`; a volume from a different Postgres major version needs `make reset-db` |
| Changed passwords in `.env` but login fails | Roles are created only on first init. Run `make reset-db` |
| Slow file access later with app containers | Not applicable: app processes run natively on the Mac |
