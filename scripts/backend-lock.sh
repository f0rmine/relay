#!/usr/bin/env bash
# Regenerate the hashed backend lock files from backend/pyproject.toml.
# Run after changing dependencies; pass --upgrade to refresh all pins.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"

if ! .venv/bin/python -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))'; then
  echo "backend/.venv must run Python 3.12 (matches Docker and CI)" >&2
  exit 1
fi

COMMON=(--quiet --generate-hashes --allow-unsafe --strip-extras "$@")
.venv/bin/pip-compile "${COMMON[@]}" --output-file=requirements.txt pyproject.toml
.venv/bin/pip-compile "${COMMON[@]}" --extra=dev --output-file=requirements-dev.txt pyproject.toml
echo "Updated backend/requirements.txt and backend/requirements-dev.txt"
