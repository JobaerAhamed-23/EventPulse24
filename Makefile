# EventPulse24 — single entry point for local development. Run `make` to list targets.
# Infrastructure runs in Docker Compose; app processes (API now; worker and web later) run on the host.

-include .env
export

EP_DB_NAME ?= eventpulse24

.DEFAULT_GOAL := help
.PHONY: help env doctor up down reset-db ps logs psql db-check db-init api manage migrate makemigrations \
        test-backend lint-backend lint-imports fmt-backend

UV_BACKEND := uv run --directory backend

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
	$(UV_BACKEND) python manage.py runserver 127.0.0.1:$(or $(API_PORT),8000)

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

lint-backend: ## Lint, format-check and import-contract-check the backend (ruff + import-linter)
	$(UV_BACKEND) ruff check .
	$(UV_BACKEND) ruff format --check .
	$(UV_BACKEND) lint-imports

lint-imports: ## Check the AD-1/AD-2/AD-8 import contracts (import-linter)
	$(UV_BACKEND) lint-imports

fmt-backend: ## Auto-fix lint issues and format the backend (ruff)
	$(UV_BACKEND) ruff check --fix .
	$(UV_BACKEND) ruff format .
