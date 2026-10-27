#!/bin/sh
# Runs on first initialization of an empty data volume, and again via `make db-init`.
# Idempotent: safe to re-run against a live database; it never drops or rewrites data.
#
# Lays the AD-3 groundwork: public event data in schema `catalog`, personal user data in
# schema `personal`, each reachable by its own runtime role only. The same setup is applied
# to the template the test database is created from, so tests see the same wall.
#
# Roles:
#   ep_owner     owns both schemas; runs migrations (DDL); may create the test database
#   ep_catalog   runtime role, DML on `catalog` only
#   ep_personal  runtime role, DML on `personal` only
set -eu

TEMPLATE_DB="${POSTGRES_DB}_test_template"

psql_as_super() {
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" "$@"
}

# --- Cluster level: roles and the test template database ----------------------------
psql_as_super --dbname "$POSTGRES_DB" \
  -v owner_pw="$EP_OWNER_PASSWORD" \
  -v catalog_pw="$EP_CATALOG_PASSWORD" \
  -v personal_pw="$EP_PERSONAL_PASSWORD" \
  -v template_db="$TEMPLATE_DB" <<'SQL'
SELECT format('CREATE ROLE ep_owner LOGIN PASSWORD %L', :'owner_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ep_owner') \gexec
SELECT format('CREATE ROLE ep_catalog LOGIN PASSWORD %L', :'catalog_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ep_catalog') \gexec
SELECT format('CREATE ROLE ep_personal LOGIN PASSWORD %L', :'personal_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ep_personal') \gexec

-- Local/test only: lets the owner create the test database from the template.
-- Production owner roles must not have CREATEDB.
ALTER ROLE ep_owner CREATEDB;

-- Each role resolves unqualified names in its own schema first; `public` holds the vector type.
-- Role-level (not only per connection) so it also holds behind a transaction-mode pooler.
ALTER ROLE ep_catalog SET search_path = catalog, public;
ALTER ROLE ep_personal SET search_path = personal, public;

SELECT format('CREATE DATABASE %I OWNER ep_owner', :'template_db')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'template_db') \gexec
SQL

# --- Per database: access, schemas, grants, extension ---------------------------------
setup_database() {
  psql_as_super --dbname "$1" -v db="$1" <<'SQL'
-- Only the project roles may connect; nobody may create objects in `public`.
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE :"db" TO ep_owner, ep_catalog, ep_personal;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- The two schemas of the AD-3 wall, owned by the migration role.
CREATE SCHEMA IF NOT EXISTS catalog AUTHORIZATION ep_owner;
CREATE SCHEMA IF NOT EXISTS personal AUTHORIZATION ep_owner;
REVOKE ALL ON SCHEMA catalog FROM PUBLIC;
REVOKE ALL ON SCHEMA personal FROM PUBLIC;

-- Each runtime role gets DML on its own schema only. Default privileges cover
-- every table and sequence ep_owner creates later (i.e. by migrations).
GRANT USAGE ON SCHEMA catalog TO ep_catalog;
ALTER DEFAULT PRIVILEGES FOR ROLE ep_owner IN SCHEMA catalog
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ep_catalog;
ALTER DEFAULT PRIVILEGES FOR ROLE ep_owner IN SCHEMA catalog
  GRANT USAGE, SELECT ON SEQUENCES TO ep_catalog;

GRANT USAGE ON SCHEMA personal TO ep_personal;
ALTER DEFAULT PRIVILEGES FOR ROLE ep_owner IN SCHEMA personal
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ep_personal;
ALTER DEFAULT PRIVILEGES FOR ROLE ep_owner IN SCHEMA personal
  GRANT USAGE, SELECT ON SEQUENCES TO ep_personal;

-- pgvector, installed once in `public` so both schemas can use the `vector` type.
CREATE EXTENSION IF NOT EXISTS vector;
SQL
}

setup_database "$POSTGRES_DB"
setup_database "$TEMPLATE_DB"

# Mark the template so the owner (with CREATEDB) can copy it into the test database.
psql_as_super --dbname "$POSTGRES_DB" -v template_db="$TEMPLATE_DB" <<'SQL'
ALTER DATABASE :"template_db" WITH IS_TEMPLATE true;
SQL
