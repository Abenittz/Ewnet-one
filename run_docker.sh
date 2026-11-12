#!/usr/bin/env bash
# Start EWNet API with Docker Compose.
# Usage:
#   bash run_docker.sh              # API only (needs Neon / reachable DATABASE_URL in .env)
#   bash run_docker.sh --with-db    # API + local Postgres container
#   bash run_docker.sh --db-only    # Postgres only (for local conda: bash run_app.sh)
#   bash run_docker.sh --build      # force rebuild
#   bash run_docker.sh --down       # stop stack
#   bash run_docker.sh --logs       # follow API logs

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

WITH_DB=0
DB_ONLY=0
DO_BUILD=0
DO_DOWN=0
DO_LOGS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-db) WITH_DB=1; shift ;;
    --db-only) DB_ONLY=1; WITH_DB=1; shift ;;
    --build) DO_BUILD=1; shift ;;
    --down) DO_DOWN=1; shift ;;
    --logs) DO_LOGS=1; shift ;;
    -h|--help)
      echo "Usage: bash run_docker.sh [--with-db|--db-only] [--build] [--down] [--logs]"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# Prefer docker in PATH; fall back to Docker Desktop on Windows/WSL.
if command -v docker >/dev/null 2>&1; then
  DOCKER=(docker)
elif [[ -x "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]]; then
  DOCKER=("/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe")
else
  echo "Docker not found. Start Docker Desktop and enable WSL integration." >&2
  exit 1
fi

COMPOSE_FILES=(-f docker-compose.yml)
if [[ "$WITH_DB" -eq 1 || "$DB_ONLY" -eq 1 ]]; then
  COMPOSE_FILES+=(-f docker-compose.with-db.yml)
fi

compose() {
  "${DOCKER[@]}" compose "${COMPOSE_FILES[@]}" "$@"
}

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example and set DATABASE_URL:" >&2
  echo "  cp .env.example .env" >&2
  exit 1
fi

if [[ "$DO_DOWN" -eq 1 ]]; then
  compose down
  exit 0
fi

if [[ "$DO_LOGS" -eq 1 ]]; then
  compose logs -f api
  exit 0
fi

if [[ "$DB_ONLY" -eq 1 ]]; then
  echo "Starting Postgres only (for local conda API)..."
  compose up -d db
  echo
  compose ps
  echo
  echo "DB: localhost:5432  (user/db from compose defaults or POSTGRES_* env)"
  echo "Then run the API with:  bash run_app.sh"
  exit 0
fi

ARGS=(up -d)
if [[ "$DO_BUILD" -eq 1 ]]; then
  ARGS=(up --build -d)
fi

echo "Starting EWNet API with Docker..."
compose "${ARGS[@]}"

echo
compose ps
echo
echo "API:    http://localhost:8000"
echo "Docs:   http://localhost:8000/docs"
echo "Health: http://localhost:8000/health"
echo
echo "Logs:   bash run_docker.sh --logs$([ "$WITH_DB" -eq 1 ] && echo ' --with-db')"
echo "Stop:   bash run_docker.sh --down$([ "$WITH_DB" -eq 1 ] && echo ' --with-db')"
