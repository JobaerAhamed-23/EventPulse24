#!/bin/sh
# Checks local prerequisites and ports for EventPulse24. Read-only: installs nothing.
# POSIX sh — runs the same on Ubuntu and macOS. Exit code is non-zero on any FAIL.
set -u

cd "$(dirname "$0")/.." || exit 1

# Load .env (or the example defaults) for port numbers.
if [ -f .env ]; then ENV_FILE=.env; else ENV_FILE=.env.example; fi
env_get() {
  v=$(grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2-)
  if [ -n "$v" ]; then printf '%s' "$v"; else printf '%s' "$2"; fi
}

FAILS=0
WARNS=0
ok()   { printf '  [ ok ] %s\n' "$1"; }
warn() { printf '  [warn] %s\n' "$1"; WARNS=$((WARNS + 1)); }
fail() { printf '  [FAIL] %s\n' "$1"; FAILS=$((FAILS + 1)); }
have() { command -v "$1" >/dev/null 2>&1; }

# version_ge "20.20.0" "20.9" -> true when $1 >= $2 (major.minor compare)
version_ge() {
  a_major=$(echo "$1" | cut -d. -f1); a_minor=$(echo "$1" | cut -d. -f2)
  b_major=$(echo "$2" | cut -d. -f1); b_minor=$(echo "$2" | cut -d. -f2)
  [ "$a_major" -gt "$b_major" ] || { [ "$a_major" -eq "$b_major" ] && [ "${a_minor:-0}" -ge "${b_minor:-0}" ]; }
}

OS=$(uname -s)
case "$OS" in
  Darwin) OS_NAME="macOS $(sw_vers -productVersion 2>/dev/null) ($(uname -m))"; GUIDE=docs/setup/macos.md ;;
  Linux)  OS_NAME="Linux $(uname -m)"; GUIDE=docs/setup/ubuntu.md ;;
  *)      OS_NAME="$OS"; GUIDE=README.md ;;
esac
printf 'EventPulse24 doctor — %s (config: %s)\n\n' "$OS_NAME" "$ENV_FILE"

printf 'Tools\n'
if have docker; then
  if docker info >/dev/null 2>&1; then ok "Docker daemon running ($(docker version --format '{{.Server.Version}}' 2>/dev/null))"
  else fail "Docker is installed but the daemon is not running — start Docker Desktop / OrbStack / dockerd"; fi
  if docker compose version >/dev/null 2>&1; then ok "Docker Compose v2 ($(docker compose version --short 2>/dev/null))"
  else fail "Docker Compose v2 plugin missing ('docker compose' must work, not 'docker-compose')"; fi
else
  fail "docker not found — see $GUIDE"
fi

if have make; then ok "make"; else fail "make not found — see $GUIDE"; fi

if have uv; then
  ok "uv $(uv --version 2>/dev/null | cut -d' ' -f2)"
  if uv python find 3.13 >/dev/null 2>&1; then ok "Python 3.13 available to uv"
  else warn "Python 3.13 not installed yet — run: uv python install 3.13"; fi
else
  fail "uv not found — install: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

if have node; then
  NODE_V=$(node -v 2>/dev/null | sed 's/^v//')
  if version_ge "$NODE_V" "24.15"; then ok "Node.js $NODE_V"
  else fail "Node.js $NODE_V is too old — need Node 24 LTS (>= 24.15): nvm install 24 (see $GUIDE)"; fi
else
  fail "node not found — need Node.js 24 LTS (>= 24.15), see $GUIDE"
fi

if have pnpm; then ok "pnpm $(pnpm --version 2>/dev/null)"
else fail "pnpm not found — run: corepack enable pnpm   (ships with Node; see $GUIDE)"; fi

# --- Ports -----------------------------------------------------------------
# port_in_use PORT: true if something listens on 127.0.0.1:PORT.
# ss sees every process on Linux without root; lsof is the macOS default; nc is the fallback.
port_in_use() {
  if [ "$OS" = Linux ] && have ss; then
    ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]$1\$"
  elif have lsof; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1 || { have nc && nc -z 127.0.0.1 "$1" >/dev/null 2>&1; }
  elif have nc; then
    nc -z 127.0.0.1 "$1" >/dev/null 2>&1
  else
    return 1
  fi
}

# ours HOST_PORT SERVICE CONTAINER_PORT: true if this project's running compose service
# publishes CONTAINER_PORT on exactly HOST_PORT (so the port is held by us, not something else).
ours() {
  have docker || return 1
  published=$(docker compose port "$2" "$3" 2>/dev/null) || return 1
  [ "${published##*:}" = "$1" ]
}

# check_port PORT LABEL SERVICE CONTAINER_PORT SEVERITY(fail|warn)
check_port() {
  if port_in_use "$1"; then
    if [ -n "$3" ] && ours "$1" "$3" "$4"; then ok "port $1 ($2) — in use by eventpulse24 '$3'"
    elif [ "$5" = warn ]; then warn "port $1 ($2) is in use — stop that process or change it in .env"
    else fail "port $1 ($2) is in use by another process — pick a free port in .env"; fi
  else
    ok "port $1 ($2) free"
  fi
}

printf '\nPorts\n'
check_port "$(env_get EP_PG_PORT 5440)"          "Postgres"     postgres 5432 fail
check_port "$(env_get EP_REDIS_PORT 6380)"       "Redis"        redis    6379 fail
check_port "$(env_get EP_SMTP_PORT 1025)"        "Mailpit SMTP" mailpit  1025 fail
check_port "$(env_get EP_MAILPIT_UI_PORT 8025)"  "Mailpit UI"   mailpit  8025 fail
check_port "$(env_get API_PORT 8000)"            "Django API"   ""       ""   warn
check_port "$(env_get WEB_PORT 3000)"            "Next.js"      ""       ""   warn

# --- Config ----------------------------------------------------------------
# Every key in .env.example must exist in .env, so an older .env is caught after new keys land.
printf '\nConfig\n'
if [ -f .env ]; then
  missing=$(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' .env.example | cut -d= -f1 | while read -r key; do
    grep -Eq "^$key=" .env || printf ' %s' "$key"
  done)
  if [ -z "$missing" ]; then ok ".env has every key from .env.example"
  else fail ".env is missing:$missing — copy them from .env.example"; fi
else
  fail 'no .env yet — run "make env" to create it from .env.example'
fi

printf '\n'
if [ "$FAILS" -gt 0 ]; then
  printf 'Result: %d failure(s), %d warning(s). Fix the [FAIL] lines above (see %s).\n' "$FAILS" "$WARNS" "$GUIDE"
  exit 1
fi
printf 'Result: all required checks passed (%d warning(s)).\n' "$WARNS"
