#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_ARGS=(-f docker-compose.yml)

warn_short_secret() {
  local key="$1"
  local value

  if [[ ! -f .env ]]; then
    return
  fi

  value="$(grep -E "^${key}=" .env | tail -n 1 | cut -d= -f2- || true)"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"

  if [[ -n "$value" && ${#value} -lt 32 ]]; then
    echo "Warning: ${key} is shorter than 32 characters. Run ./scripts/rotate-jwt-secrets.sh, then restart backend."
  fi
}

if [[ -f backend/firebase-service-account.json ]]; then
  COMPOSE_ARGS+=(-f docker-compose.firebase.yml)
  echo "Using Firebase service account mount from backend/firebase-service-account.json"
fi

warn_short_secret "JWT_SECRET"
warn_short_secret "JWT_REFRESH_SECRET"

docker compose "${COMPOSE_ARGS[@]}" build backend
docker compose "${COMPOSE_ARGS[@]}" up -d postgres redis
docker compose "${COMPOSE_ARGS[@]}" run --rm backend alembic upgrade head
docker compose "${COMPOSE_ARGS[@]}" up -d backend

echo "Backend is starting on http://localhost:8000"
echo "Readiness: curl http://localhost:8000/health/ready"
