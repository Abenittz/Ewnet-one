#!/usr/bin/env bash
# Production / cloud start script (Render, Railway, Docker-less hosts).
# Does NOT use conda — uses the environment's `python` + pip packages.
#
# Render settings (example):
#   Root Directory: backend
#   Build Command:  pip install -r requirements.txt
#   Start Command:  bash start.sh
#
# Required env vars on the platform (Dashboard → Environment):
#   DATABASE_URL, SECRET_KEY, CORS_ORIGINS, ...

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-${RENDER_EXTERNAL_PORT:-8000}}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-1}"

if ! command -v python >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
  alias python=python3
fi

if ! command -v python >/dev/null 2>&1; then
  echo "python not found in PATH" >&2
  exit 1
fi

echo "[start] Python: $(python --version 2>&1)"
echo "[start] Host=${HOST} Port=${PORT}"

if [[ "${RUN_MIGRATIONS}" == "1" ]]; then
  echo "[start] Running Alembic migrations..."
  alembic upgrade head
fi

echo "[start] Starting uvicorn..."
exec uvicorn main:app --host "${HOST}" --port "${PORT}"
