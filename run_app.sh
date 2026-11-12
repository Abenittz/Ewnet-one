#!/usr/bin/env bash
# Start the EWNet Reader API with the conda env.
# Usage:
#   ./run_app.sh              # run with reload
#   ./run_app.sh --migrate    # apply Alembic migrations, then run
#   ./run_app.sh --host 127.0.0.1 --port 8000

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

CONDA_ENV="${CONDA_ENV:-ewnetapi}"
HOST="${HOST:-}"
PORT="${PORT:-}"
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

# Load HOST and PORT defaults from .env if not specified via CLI flags or env vars
if [[ -z "$HOST" ]]; then
  ENV_HOST="$(grep -E '^\s*HOST=' .env | cut -d '=' -f2- | tr -d ' "\r' || true)"
  HOST="${ENV_HOST:-127.0.0.1}"
fi
if [[ -z "$PORT" ]]; then
  ENV_PORT="$(grep -E '^\s*PORT=' .env | cut -d '=' -f2- | tr -d ' "\r' || true)"
  PORT="${ENV_PORT:-8000}"
fi

if [[ "$RUN_MIGRATE" -eq 1 ]]; then
  echo "Running migrations..."
  alembic upgrade head
fi

# Detect PC / LAN IP for easy network access if listening on all interfaces
PC_IP=""
if [[ "$HOST" == "0.0.0.0" ]]; then
  if [[ -f /mnt/c/Windows/System32/ipconfig.exe ]]; then
    PC_IP="$(timeout 2 /mnt/c/Windows/System32/ipconfig.exe < /dev/null 2>/dev/null | grep -i "IPv4" | grep -v "172.1" | awk -F': ' '{print $2}' | tr -d '\r' | head -n1 || true)"
  fi
  if [[ -z "$PC_IP" ]]; then
    PC_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  fi
fi

echo "====================================================="
echo " Starting EWNet API (env: ${CONDA_ENV})"
echo " Listening on:   http://${HOST}:${PORT}"
echo " Local URL:      http://localhost:${PORT}"
if [[ -n "$PC_IP" && "$PC_IP" != "127.0.0.1" ]]; then
echo " PC / LAN URL:   http://${PC_IP}:${PORT}"
fi
echo " API Docs:       http://localhost:${PORT}/docs"
if [[ -n "$PC_IP" && "$PC_IP" != "127.0.0.1" ]]; then
echo " API Docs (LAN): http://${PC_IP}:${PORT}/docs"
fi
echo "====================================================="
exec uvicorn main:app --reload --host "$HOST" --port "$PORT"
