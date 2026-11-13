# EventPulse24 — single entry point for local development. Run `make` to list targets.
# Infrastructure runs in Docker Compose; app processes (API, worker, beat, web) run on the host.

-include .env
export

EP_DB_NAME ?= eventpulse24
# Where the Next.js proxy (frontend/proxy.ts) forwards /api/*; read per request, no rebuild needed.
API_BASE_URL ?= http://127.0.0.1:$(or $(API_PORT),8000)

.DEFAULT_GOAL := help
.PHONY: help env doctor up down reset-db ps logs psql db-check db-init api worker beat send-test-email \
        manage migrate makemigrations test-backend lint-backend lint-imports fmt-backend \
        web web-install lint-web test-web test-e2e openapi client dev coverage-backend seed-browse seed-browse-for-test

UV_BACKEND := uv run --directory backend

# The four app processes, defined once: their own targets run them, and `make dev` runs them
# side by side (scripts/dev.sh reads these from the environment; `export` above passes them).
API_CMD = $(UV_BACKEND) python manage.py runserver 127.0.0.1:$(or $(API_PORT),8000)
WORKER_CMD = $(UV_BACKEND) celery -A config worker --pool solo --hostname eventpulse24-worker --loglevel INFO
BEAT_CMD = mkdir -p backend/.celery && $(UV_BACKEND) celery -A config beat --loglevel INFO --schedule .celery/beat-schedule --pidfile .celery/beat.pid
WEB_CMD = pnpm --dir frontend dev --hostname 127.0.0.1 --port $(or $(WEB_PORT),3000)

help: ## List available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

env: ## Create .env from .env.example (never overwrites an existing .env)
	@if [ -f .env ]; then echo ".env already exists — leaving it unchanged"; \
	else cp .env.example .env && echo "Created .env from .env.example"; fi

doctor: ## Check prerequisites and ports (installs nothing)
	@sh scripts/doctor.sh

up: ## Start Postgres, Redis and Mailpit and wait until healthy
	docker compose up -d --wait

down: ## Stop the containers (data is kept)
	docker compose down

reset-db: ## Delete all local data and re-initialize (asks first; FORCE=1 to skip)
	@if [ "$(FORCE)" != "1" ]; then \
		printf "This deletes ALL local EventPulse24 data (Postgres volume). Continue? [y/N] "; \
		read ans; [ "$$ans" = "y" ] || [ "$$ans" = "Y" ] || { echo "Aborted."; exit 1; }; \
	fi
	docker compose down -v
	docker compose up -d --wait

ps: ## Show container status
	docker compose ps

logs: ## Follow container logs
	docker compose logs -f --tail=100

psql: ## Open psql in the database as the superuser
	docker compose exec postgres psql -U postgres -d $(EP_DB_NAME)

db-check: ## Verify schemas, pgvector, roles and schema isolation
	@sh scripts/db-check.sh

db-init: ## Re-apply the database init script to the running container (idempotent, keeps data)
	docker compose exec -T postgres sh /docker-entrypoint-initdb.d/01-schemas-and-roles.sh

api: ## Run the Django API on 127.0.0.1:$API_PORT (default 8000)
	$(API_CMD)

# --pool solo: one job at a time, in one process, the same on macOS and Ubuntu. Celery 5.6.3's
# prefork pool breaks on macOS (billiard spawns children; every task fails with "not enough
# values to unpack"). The node name has no ".host" part, so the log scrubber can't read it as
# an email address.
worker: ## Run the Celery worker (background jobs and the tick), one job at a time
	$(WORKER_CMD)

# Exactly ONE beat may run (two would fire every tick twice). The pidfile makes a second
# `make beat` refuse to start while the first is running.
beat: ## Run Celery beat, the 60s tick scheduler — exactly one at a time
	$(BEAT_CMD)

send-test-email: ## Send a test email to Mailpit: make send-test-email [TO=you@example.test] [STREAM=bulk]
	$(UV_BACKEND) python manage.py send_test_email --to $(or $(TO),dev@example.test) \
		--stream $(or $(STREAM),transactional)

dev: ## Run API, worker, beat and web together (Ctrl-C stops all); needs `make up` first
	@sh scripts/dev.sh

# AD-19: the OpenAPI schema is the contract; the frontend client is generated from it.
openapi: ## Export the API's OpenAPI schema to frontend/lib/api/openapi.json
	$(UV_BACKEND) python manage.py export_openapi_schema --api config.api.api --indent 2 --sorted \
		--output ../frontend/lib/api/openapi.json

client: openapi ## Regenerate the TypeScript client types (frontend/lib/api/schema.ts) from the schema
	pnpm --dir frontend exec openapi-typescript lib/api/openapi.json --output lib/api/schema.ts

# Frontend (Node 24 LTS, see .nvmrc; pnpm version from frontend/package.json "packageManager").
web-install: ## Install the frontend dependencies exactly as locked
	pnpm --dir frontend install --frozen-lockfile

web: ## Run the Next.js dev server on http://127.0.0.1:$WEB_PORT (default 3000)
	$(WEB_CMD)

lint-web: ## Lint, typecheck and format-check the frontend
	pnpm --dir frontend lint
	pnpm --dir frontend typecheck
	pnpm --dir frontend format:check

test-web: ## Run the frontend tests (Vitest)
	pnpm --dir frontend test

# The Browse walk-through. These tests drive the real stack — the real frontend against the
# real backend against the real database — so they need the infrastructure up and the
# catalog seeded. That is why they are a separate target from `test-web`: the Vitest
# suite is hermetic and runs on every commit, and these are not.
#
# `seed-browse` is a prerequisite, so the data the tests sign in against is the committed
# seed file's and never whatever the database happened to hold.
#
# The four accounts are the Free one (the save cap), the second Free one (a separate
# save allowance, so two tests can each spend one), the Pro one (no cap) and the
# `no-city` one (the city's emptiness, which no browser flow can produce).
seed-browse: ## Seed the Browse catalog (city, week of events, four accounts)
	$(UV_BACKEND) python manage.py seed_browse_catalog

# The end-to-end run starts from an **empty Pulse**. The seed always puts the save
# *allowance* back, but it leaves the *saved rows* alone — deliberately, because a seed
# that un-saved a reader's events would change what the surface shows, and the
# walk-through is about seeing a saved event. A test suite has the opposite need: a
# leftover row puts the Save button in the `saved` state, so the suite's first press
# takes the unsave branch and the button correctly goes back to "Save" — a failure with
# nothing to do with the code under test.
seed-browse-for-test: ## Seed the Browse catalog and clear the accounts' saved events
	$(UV_BACKEND) python manage.py seed_browse_catalog --reset-saves

test-e2e: seed-browse-for-test ## Run the Browse end-to-end tests (Playwright); needs `make up` and the API running
	pnpm --dir frontend exec playwright test

manage: ## Run a manage.py command: make manage ARGS="check"
	$(UV_BACKEND) python manage.py $(ARGS)

migrate: ## Apply migrations to both schemas as the owner role (personal, then catalog)
	DJANGO_DB_ROLE=owner $(UV_BACKEND) python manage.py migrate --database=default
	DJANGO_DB_ROLE=owner $(UV_BACKEND) python manage.py migrate --database=catalog

makemigrations: ## Create migrations, then sort imports and format: make makemigrations ARGS="identity"
	$(UV_BACKEND) python manage.py makemigrations $(ARGS)
	$(UV_BACKEND) ruff check --select I --fix --quiet .
	$(UV_BACKEND) ruff format .

test-backend: ## Run the backend test suite
	$(UV_BACKEND) pytest

coverage-backend: ## Run the backend tests with coverage gates: >=80% overall, 100% for domain/
	$(UV_BACKEND) pytest --cov --cov-report=term
	$(UV_BACKEND) coverage report --include='domain/*' --fail-under=100

lint-backend: ## Lint, format-check and import-contract-check the backend (ruff + import-linter)
	$(UV_BACKEND) ruff check .
	$(UV_BACKEND) ruff format --check .
	$(UV_BACKEND) lint-imports

lint-imports: ## Check the AD-1/AD-2/AD-8 import contracts (import-linter)
	$(UV_BACKEND) lint-imports

fmt-backend: ## Auto-fix lint issues and format the backend (ruff)
	$(UV_BACKEND) ruff check --fix .
	$(UV_BACKEND) ruff format .
