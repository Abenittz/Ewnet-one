#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] Ensuring storage directories..."
mkdir -p "${STORAGE_PATH:-/app/storage}"/{books,raw,extracted}

if [[ "${RUN_MIGRATIONS:-1}" == "1" ]]; then
  echo "[entrypoint] Running Alembic migrations..."
  alembic upgrade head
else
  echo "[entrypoint] Skipping migrations (RUN_MIGRATIONS=${RUN_MIGRATIONS})"
fi

echo "[entrypoint] Starting: $*"
exec "$@"
