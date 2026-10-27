#!/bin/sh
# Verifies the local Postgres matches the AD-3 groundwork laid by docker/postgres/init:
# schemas, pgvector, roles, and that each runtime role is locked out of the other schema.
# POSIX sh. Requires the compose stack to be up (`make up`). Exit code is non-zero on any FAIL.
set -u

cd "$(dirname "$0")/.." || exit 1

if [ -f .env ]; then ENV_FILE=.env; else ENV_FILE=.env.example; fi
env_get() {
  v=$(grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2-)
  if [ -n "$v" ]; then printf '%s' "$v"; else printf '%s' "$2"; fi
}

DB=$(env_get EP_DB_NAME eventpulse24)
SUPER_PW=$(env_get EP_PG_SUPERUSER_PASSWORD postgres_local)
OWNER_PW=$(env_get EP_OWNER_PASSWORD ep_owner_local)
CATALOG_PW=$(env_get EP_CATALOG_PASSWORD ep_catalog_local)
PERSONAL_PW=$(env_get EP_PERSONAL_PASSWORD ep_personal_local)

FAILS=0
ok()   { printf '  [ ok ] %s\n' "$1"; }
fail() { printf '  [FAIL] %s\n' "$1"; FAILS=$((FAILS + 1)); }

# q ROLE PASSWORD SQL -> prints the scalar result; exit status of psql.
# Connects over TCP inside the container so password auth is really exercised.
q() {
  docker compose exec -T -e PGPASSWORD="$2" postgres \
    psql -h 127.0.0.1 -U "$1" -d "$DB" -v ON_ERROR_STOP=1 -tAqc "$3" 2>&1
}
as_super()    { q postgres "$SUPER_PW" "$1"; }
as_owner()    { q ep_owner "$OWNER_PW" "$1"; }
as_catalog()  { q ep_catalog "$CATALOG_PW" "$1"; }
as_personal() { q ep_personal "$PERSONAL_PW" "$1"; }

# expect_denied LABEL OUTPUT STATUS
expect_denied() {
  if [ "$3" -ne 0 ] && echo "$2" | grep -q "permission denied"; then ok "$1 — denied"
  else fail "$1 — expected 'permission denied', got: $2"; fi
}

if [ -z "$(docker compose ps --status running -q postgres 2>/dev/null)" ]; then
  echo "Postgres container is not running — run: make up"
  exit 1
fi

printf 'Postgres (%s)\n' "$(as_super 'SHOW server_version' | cut -d' ' -f1)"

for s in catalog personal; do
  owner=$(as_super "SELECT nspowner::regrole FROM pg_namespace WHERE nspname = '$s'")
  if [ "$owner" = ep_owner ]; then ok "schema '$s' exists, owned by ep_owner"
  else fail "schema '$s' missing or wrong owner (got '$owner')"; fi
done

ver=$(as_super "SELECT extversion FROM pg_extension WHERE extname = 'vector'")
if [ -n "$ver" ]; then ok "extension 'vector' $ver installed"; else fail "extension 'vector' not installed"; fi

TEMPLATE_DB="${DB}_test_template"
if [ "$(as_super "SELECT 1 FROM pg_database WHERE datname = '$TEMPLATE_DB' AND datistemplate")" = 1 ]; then
  ok "test template '$TEMPLATE_DB' exists (IS_TEMPLATE)"
else fail "test template '$TEMPLATE_DB' missing or not a template — run: make db-init"; fi

if [ "$(as_super "SELECT 1 FROM pg_roles WHERE rolname = 'ep_owner' AND rolcreatedb")" = 1 ]; then
  ok "ep_owner can create the test database (CREATEDB)"
else fail "ep_owner lacks CREATEDB — run: make db-init"; fi

for r in ep_owner ep_catalog ep_personal; do
  if [ "$(as_super "SELECT 1 FROM pg_roles WHERE rolname = '$r' AND rolcanlogin AND NOT rolsuper")" = 1 ]; then
    ok "role '$r' can log in (not superuser)"
  else fail "role '$r' missing, cannot log in, or is superuser"; fi
done

printf '\nSchema isolation\n'
# Probe tables created by the migration role, exactly as migrations will.
as_owner "DROP TABLE IF EXISTS catalog.__db_check; DROP TABLE IF EXISTS personal.__db_check;
          CREATE TABLE catalog.__db_check (id int); CREATE TABLE personal.__db_check (id int);" >/dev/null

out=$(as_catalog "INSERT INTO catalog.__db_check VALUES (1); SELECT count(*) FROM catalog.__db_check")
if [ "$out" = 1 ]; then ok "ep_catalog can read/write catalog"; else fail "ep_catalog cannot use catalog: $out"; fi

out=$(as_personal "INSERT INTO personal.__db_check VALUES (1); SELECT count(*) FROM personal.__db_check")
if [ "$out" = 1 ]; then ok "ep_personal can read/write personal"; else fail "ep_personal cannot use personal: $out"; fi

out=$(as_catalog "SELECT * FROM personal.__db_check"); expect_denied "ep_catalog reading personal" "$out" $?
out=$(as_personal "SELECT * FROM catalog.__db_check"); expect_denied "ep_personal reading catalog" "$out" $?
out=$(as_catalog "CREATE TABLE catalog.__ddl_probe (id int)"); expect_denied "ep_catalog running DDL" "$out" $?
out=$(as_personal "CREATE TABLE public.__ddl_probe (id int)"); expect_denied "ep_personal creating in public" "$out" $?

out=$(as_catalog "SELECT '[1,2,3]'::vector(3)")
if [ "$out" = "[1,2,3]" ]; then ok "vector type usable from ep_catalog"; else fail "vector type not usable: $out"; fi

as_owner "DROP TABLE catalog.__db_check; DROP TABLE personal.__db_check;" >/dev/null

printf '\n'
if [ "$FAILS" -gt 0 ]; then printf 'Result: %d failure(s).\n' "$FAILS"; exit 1; fi
printf 'Result: database ready.\n'
