#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"

curl -fsS "$BASE_URL/health/ready"
echo
