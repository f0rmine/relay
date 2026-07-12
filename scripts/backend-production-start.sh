#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Missing .env. Create it from .env.example and replace every placeholder secret."
  exit 1
fi

COMPOSE_ARGS=(-f docker-compose.yml -f docker-compose.production.yml)
if [[ -f backend/firebase-service-account.json ]]; then
  COMPOSE_ARGS+=(-f docker-compose.firebase.yml)
  echo "Using Firebase service account mount from backend/firebase-service-account.json"
fi

docker compose "${COMPOSE_ARGS[@]}" config --quiet
docker compose "${COMPOSE_ARGS[@]}" build backend
docker compose "${COMPOSE_ARGS[@]}" up -d postgres redis
docker compose "${COMPOSE_ARGS[@]}" run --rm backend alembic upgrade head
docker compose "${COMPOSE_ARGS[@]}" up -d backend

echo "Production backend is bound to http://127.0.0.1:${BACKEND_PORT:-8000}"
echo "Place an HTTPS/WSS reverse proxy in front of this loopback port."
