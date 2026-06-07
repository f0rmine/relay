#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
EXAMPLE_FILE="$ROOT_DIR/.env.example"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$EXAMPLE_FILE" "$ENV_FILE"
fi

generate_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
    return
  fi
  LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 64
  printf '\n'
}

set_env_value() {
  local key="$1"
  local value="$2"
  local tmp_file
  tmp_file="$(mktemp)"
  if grep -q "^${key}=" "$ENV_FILE"; then
    awk -v key="$key" -v value="$value" '
      BEGIN { replaced = 0 }
      $0 ~ "^" key "=" {
        print key "=" value
        replaced = 1
        next
      }
      { print }
      END {
        if (!replaced) print key "=" value
      }
    ' "$ENV_FILE" >"$tmp_file"
  else
    cp "$ENV_FILE" "$tmp_file"
    printf '%s=%s\n' "$key" "$value" >>"$tmp_file"
  fi
  mv "$tmp_file" "$ENV_FILE"
}

set_env_value "JWT_SECRET" "$(generate_secret)"
set_env_value "JWT_REFRESH_SECRET" "$(generate_secret)"

echo "Rotated JWT_SECRET and JWT_REFRESH_SECRET in .env without printing values."
echo "Restart the backend after this script so the new secrets are used."
