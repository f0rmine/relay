#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SERVICE_ACCOUNT_FILE="${1:-backend/firebase-service-account.json}"

env_value() {
  local key="$1"
  local file="${2:-.env}"

  if [[ ! -f "$file" ]]; then
    return 0
  fi

  grep -E "^${key}=" "$file" | tail -n 1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//" || true
}

if [[ ! -f "$SERVICE_ACCOUNT_FILE" ]]; then
  echo "Firebase service account file not found: $SERVICE_ACCOUNT_FILE"
  echo "For Docker, place the ignored JSON at backend/firebase-service-account.json"
  exit 1
fi

METADATA="$(python3 - "$SERVICE_ACCOUNT_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text())

for key in ("type", "project_id", "client_email"):
    print(f"{key}={data.get(key, '')}")
PY
)"

json_type="$(printf '%s\n' "$METADATA" | grep '^type=' | cut -d= -f2-)"
json_project_id="$(printf '%s\n' "$METADATA" | grep '^project_id=' | cut -d= -f2-)"
json_client_email="$(printf '%s\n' "$METADATA" | grep '^client_email=' | cut -d= -f2-)"
env_project_id="$(env_value FIREBASE_PROJECT_ID)"
env_service_file="$(env_value FIREBASE_SERVICE_ACCOUNT_FILE)"
push_enabled="$(env_value PUSH_NOTIFICATIONS_ENABLED)"

echo "Firebase service account metadata"
echo "File: $SERVICE_ACCOUNT_FILE"
echo "Type: ${json_type:-missing}"
echo "Project ID: ${json_project_id:-missing}"
echo "Client email: ${json_client_email:-missing}"
echo
echo "Local .env Firebase settings"
echo "PUSH_NOTIFICATIONS_ENABLED=${push_enabled:-unset}"
echo "FIREBASE_PROJECT_ID=${env_project_id:-unset}"
echo "FIREBASE_SERVICE_ACCOUNT_FILE=${env_service_file:-unset}"
echo

if [[ "$json_type" != "service_account" ]]; then
  echo "Warning: JSON type is not service_account."
fi

if [[ -n "$env_project_id" && -n "$json_project_id" && "$env_project_id" != "$json_project_id" ]]; then
  echo "Warning: .env FIREBASE_PROJECT_ID does not match the JSON project_id."
fi

if [[ "$SERVICE_ACCOUNT_FILE" == "backend/firebase-service-account.json" ]]; then
  echo "Docker expected FIREBASE_SERVICE_ACCOUNT_FILE=/app/firebase-service-account.json"
fi

echo
echo "IAM fix command"
echo "gcloud projects add-iam-policy-binding ${json_project_id:-PROJECT_ID} \\"
echo "  --member=\"serviceAccount:${json_client_email:-CLIENT_EMAIL}\" \\"
echo "  --role=\"roles/firebasecloudmessaging.admin\""
echo
echo "API enable command"
echo "gcloud services enable fcm.googleapis.com --project ${json_project_id:-PROJECT_ID}"
