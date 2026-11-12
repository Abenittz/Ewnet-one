#!/usr/bin/env bash
# Start the EWNet Reader API with the conda env.
# Usage:
#   ./run_app.sh              # run with reload
#   ./run_app.sh --migrate    # apply Alembic migrations, then run
#   ./run_app.sh --host 0.0.0.0 --port 8000

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

CONDA_ENV="${CONDA_ENV:-ewnetapi}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RUN_MIGRATE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --migrate)
      RUN_MIGRATE=1
      shift
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: ./run_app.sh [--migrate] [--host HOST] [--port PORT]"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# Load conda into this shell (works even when conda isn't initialized in the terminal).
if ! command -v conda >/dev/null 2>&1; then
  for candidate in \
    "${HOME}/miniconda3/etc/profile.d/conda.sh" \
    "${HOME}/anaconda3/etc/profile.d/conda.sh" \
    "/opt/conda/etc/profile.d/conda.sh"
  do
    if [[ -f "$candidate" ]]; then
      # shellcheck source=/dev/null
      source "$candidate"
      break
    fi
  done
fi

if ! command -v conda >/dev/null 2>&1; then
  echo "conda not found. Install Miniconda or set CONDA_ENV path manually." >&2
  exit 1
fi

# shellcheck source=/dev/null
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example and set DATABASE_URL:" >&2
  echo "  cp .env.example .env" >&2
  exit 1
fi

if [[ "$RUN_MIGRATE" -eq 1 ]]; then
  echo "Running migrations..."
  alembic upgrade head
fi

echo "Starting EWNet API on http://${HOST}:${PORT}  (env: ${CONDA_ENV})"
echo "Docs: http://localhost:${PORT}/docs"
exec uvicorn main:app --reload --host "$HOST" --port "$PORT"
