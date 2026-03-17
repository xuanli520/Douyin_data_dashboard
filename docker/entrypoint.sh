#!/usr/bin/env sh
set -e

DB_HOST=${DB__HOST:-${DB_HOST:-db}}
DB_PORT=${DB__PORT:-${DB_PORT:-5432}}
DB_USER=${DB__USER:-${DB_USER:-postgres}}
DB_NAME=${DB__DATABASE:-${DB_DATABASE:-appdb}}
CACHE_BACKEND=${CACHE__BACKEND:-${CACHE_BACKEND:-redis}}
CACHE_HOST=${CACHE__HOST:-${CACHE_HOST:-redis}}
CACHE_PORT=${CACHE__PORT:-${CACHE_PORT:-6379}}
WAIT_TIMEOUT_SECONDS=${WAIT_TIMEOUT_SECONDS:-60}
WAIT_FOR_DB=${WAIT_FOR_DB:-1}
WAIT_FOR_CACHE=${WAIT_FOR_CACHE:-1}
RUN_DB_MIGRATIONS=${RUN_DB_MIGRATIONS:-0}

is_true() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

wait_for_postgres() {
  echo "Waiting for Postgres at ${DB_HOST}:${DB_PORT}..."
  i=1
  while [ "$i" -le "$WAIT_TIMEOUT_SECONDS" ]; do
    if pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" >/dev/null 2>&1; then
      echo "Postgres is ready"
      return 0
    fi
    echo "Postgres not ready yet (attempt: ${i}), sleeping 1s..."
    sleep 1
    i=$((i + 1))
  done
  echo "Postgres did not become ready in ${WAIT_TIMEOUT_SECONDS}s" >&2
  exit 1
}

wait_for_tcp() {
  service_name=$1
  host=$2
  port=$3
  echo "Waiting for ${service_name} at ${host}:${port}..."
  i=1
  while [ "$i" -le "$WAIT_TIMEOUT_SECONDS" ]; do
    if python - "$host" "$port" <<'PY'
import socket
import sys

with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=1):
    pass
PY
    then
      echo "${service_name} is ready"
      return 0
    fi
    echo "${service_name} not ready yet (attempt: ${i}), sleeping 1s..."
    sleep 1
    i=$((i + 1))
  done
  echo "${service_name} did not become ready in ${WAIT_TIMEOUT_SECONDS}s" >&2
  exit 1
}

if is_true "$WAIT_FOR_DB"; then
  wait_for_postgres
fi

if [ "$CACHE_BACKEND" = "redis" ] && is_true "$WAIT_FOR_CACHE"; then
  wait_for_tcp "Redis" "${CACHE_HOST}" "${CACHE_PORT}"
fi

if is_true "$RUN_DB_MIGRATIONS"; then
  echo "Running database migrations (alembic upgrade head)"
  alembic upgrade head
fi

exec "$@"
