#!/bin/sh
# make dev: run the API, Celery worker, Celery beat and Next.js together, each line prefixed
# with its process name. Ctrl-C stops all of them. POSIX sh: the same on Linux and macOS.
# Infrastructure (Postgres, Redis, Mailpit) is `make up`, not this script.
set -eu

cd "$(dirname "$0")/.."

CONCURRENTLY=frontend/node_modules/.bin/concurrently
BEAT_PIDFILE=backend/.celery/beat.pid
: "${API_CMD:?run this through make dev}" "${WORKER_CMD:?}" "${BEAT_CMD:?}" "${WEB_CMD:?}"

if [ ! -x "$CONCURRENTLY" ]; then
  echo "Frontend dependencies are missing: run make web-install first." >&2
  exit 1
fi

# Infrastructure hint only; the health page shows exactly what's down.
if command -v docker >/dev/null 2>&1; then
  running=$(docker compose ps --status running --services 2>/dev/null || true)
  for service in postgres redis; do
    if ! printf '%s\n' "$running" | grep -qx "$service"; then
      echo "Note: the $service container isn't running. Start the infrastructure with: make up"
    fi
  done
fi

names="api,worker,beat,web"
colors="blue,magenta,yellow,cyan"
start_beat=1

# Exactly one beat: two would fire every tick twice (AD-7).
if [ -f "$BEAT_PIDFILE" ]; then
  pid=$(cat "$BEAT_PIDFILE")
  if kill -0 "$pid" 2>/dev/null; then
    echo "Celery beat is already running (pid $pid); not starting another."
    start_beat=0
  else
    echo "Removing a stale beat pidfile (pid $pid isn't running)."
    rm -f "$BEAT_PIDFILE"
  fi
fi

if [ "$start_beat" -eq 1 ]; then
  exec "$CONCURRENTLY" --names "$names" --prefix-colors "$colors" --kill-others-on-fail \
    "$API_CMD" "$WORKER_CMD" "$BEAT_CMD" "$WEB_CMD"
fi
exec "$CONCURRENTLY" --names "api,worker,web" --prefix-colors "blue,magenta,cyan" \
  --kill-others-on-fail "$API_CMD" "$WORKER_CMD" "$WEB_CMD"
