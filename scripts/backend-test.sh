#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"

if [[ ! -x ".venv/bin/python" ]]; then
  python3 -m venv .venv
fi

if ! .venv/bin/python -c "import pytest, ruff" >/dev/null 2>&1; then
  .venv/bin/pip install -e ".[dev]"
fi

.venv/bin/pytest
.venv/bin/ruff check app
