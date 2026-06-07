#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"

if [[ ! -x ".venv/bin/python" ]]; then
  python3 -m venv .venv
fi

if ! .venv/bin/python -c "import websockets" >/dev/null 2>&1; then
  .venv/bin/pip install websockets
fi

cd "$ROOT_DIR"
backend/.venv/bin/python scripts/smoke-messages.py "${1:-http://localhost:8000}"
