#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR/backend"
if [[ ! -x ".venv/bin/python" ]]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'from importlib.metadata import version; raise SystemExit(tuple(map(int, version("pip").split(".")[:2])) < (26, 1))'; then
  .venv/bin/python -m pip install --upgrade "pip>=26.1.2"
fi
if ! .venv/bin/python -c "import bandit, pip_audit" >/dev/null 2>&1; then
  .venv/bin/pip install -e ".[dev]"
fi

.venv/bin/pip-audit
.venv/bin/bandit -q -r app -x app/tests,app/scripts_delete_dummy.py

cd "$ROOT_DIR/mobile"
npm audit
