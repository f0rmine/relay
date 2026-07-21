#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_ARGS=(-f "$ROOT_DIR/docker-compose.yml")
ASSUME_YES=false
BACKUP_PATH=""

usage() {
  cat <<'EOF'
Usage: ./scripts/restore.sh [options] BACKUP_DIRECTORY

Verify a Relay backup's SHA-256 checksums, stop the backend, replace the
PostgreSQL database, and safely stage and replace the uploads volume. The
backend is started again when the restore succeeds or fails.

Options:
  --yes              Required explicit confirmation for destructive restore
  --production       Include docker-compose.production.yml
  -h, --help         Show this help

Example:
  ./scripts/restore.sh --production --yes backups/relay-20260722T120000Z

The target postgres service must be running. Restoring replaces the configured
POSTGRES_DB and all current uploads. Keep an independent backup before use.
EOF
}

while (($#)); do
  case "$1" in
    --yes)
      ASSUME_YES=true
      shift
      ;;
    --production)
      COMPOSE_ARGS+=(-f "$ROOT_DIR/docker-compose.production.yml")
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      [[ -z "$BACKUP_PATH" ]] || { echo "Only one backup directory is accepted" >&2; exit 2; }
      BACKUP_PATH="$1"
      shift
      ;;
  esac
done

[[ -n "$BACKUP_PATH" ]] || { usage >&2; exit 2; }
[[ "$ASSUME_YES" == true ]] || {
  echo "Restore is destructive; rerun with --yes after verifying the target." >&2
  exit 2
}

BACKUP_PATH="$(cd "$BACKUP_PATH" 2>/dev/null && pwd)" || {
  echo "Backup directory does not exist" >&2
  exit 1
}

for file in database.dump uploads.tar.gz SHA256SUMS manifest.txt; do
  [[ -f "$BACKUP_PATH/$file" ]] || { echo "Missing backup file: $file" >&2; exit 1; }
done

grep -qx 'format_version=1' "$BACKUP_PATH/manifest.txt" || {
  echo "Unsupported or missing backup format version" >&2
  exit 1
}

(
  cd "$BACKUP_PATH"
  sha256sum --check --strict SHA256SUMS
)

# Reject absolute paths and parent traversal before passing the archive to tar.
if tar -tzf "$BACKUP_PATH/uploads.tar.gz" | awk '
  /^\// { bad=1 }
  { count=split($0, parts, "/"); for (i=1; i<=count; i++) if (parts[i] == "..") bad=1 }
  END { exit bad }
'; then
  :
else
  echo "Uploads archive contains an unsafe path" >&2
  exit 1
fi

compose=(docker compose "${COMPOSE_ARGS[@]}")
backend_was_running=false
if [[ "$("${compose[@]}" ps --status running --quiet backend)" != "" ]]; then
  backend_was_running=true
fi

restart_backend() {
  if [[ "$backend_was_running" == true ]]; then
    "${compose[@]}" start backend >/dev/null || true
  fi
}
trap restart_backend EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"${compose[@]}" stop backend >/dev/null

"${compose[@]}" exec -T postgres sh -eu -c '
  psql --username="$POSTGRES_USER" --dbname=postgres \
    --set=ON_ERROR_STOP=1 --set=db="$POSTGRES_DB" <<SQL
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = :'"'"'db'"'"' AND pid <> pg_backend_pid();
SQL
  exec pg_restore \
    --clean \
    --if-exists \
    --create \
    --exit-on-error \
    --no-owner \
    --no-privileges \
    --username="$POSTGRES_USER" \
    --dbname=postgres
' <"$BACKUP_PATH/database.dump"

"${compose[@]}" run --rm --no-deps -T --entrypoint sh backend -eu -c '
  uploads=/app/uploads
  stage="$uploads/.relay-restore-stage"
  previous="$uploads/.relay-restore-previous"
  rm -rf "$stage" "$previous"
  mkdir "$stage" "$previous"
  replacement_started=false
  rollback() {
    if [ "$replacement_started" = true ]; then
      find "$uploads" -mindepth 1 -maxdepth 1 \
        ! -name .relay-restore-stage ! -name .relay-restore-previous \
        -exec rm -rf -- {} +
      find "$previous" -mindepth 1 -maxdepth 1 -exec mv -- {} "$uploads"/ \;
    fi
    rm -rf "$stage" "$previous"
  }
  trap rollback EXIT
  trap "exit 1" HUP INT TERM
  tar -xzf - -C "$stage"
  replacement_started=true
  find "$uploads" -mindepth 1 -maxdepth 1 \
    ! -name .relay-restore-stage ! -name .relay-restore-previous \
    -exec mv -- {} "$previous"/ \;
  find "$stage" -mindepth 1 -maxdepth 1 -exec mv -- {} "$uploads"/ \;
  rm -rf "$stage" "$previous"
  replacement_started=false
  trap - EXIT HUP INT TERM
' <"$BACKUP_PATH/uploads.tar.gz"

restart_backend
trap - EXIT INT TERM
echo "Restore completed from: $BACKUP_PATH"
