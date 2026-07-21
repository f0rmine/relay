#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${BACKUP_DIR:-$ROOT_DIR/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
COMPOSE_ARGS=(-f "$ROOT_DIR/docker-compose.yml")

usage() {
  cat <<'EOF'
Usage: ./scripts/backup.sh [options]

Create a PostgreSQL custom-format dump and a compressed archive of the uploads
volume. The files, metadata, and SHA-256 checksums are published atomically as
one timestamped directory.

Options:
  --output DIR       Backup parent directory (default: ./backups)
  --retention DAYS   Delete relay-* backup directories older than DAYS
                     (default: 14; use 0 to disable retention)
  --production       Include docker-compose.production.yml
  -h, --help         Show this help

The postgres and backend images must exist, and the postgres service must be
running. A running backend is stopped briefly so the database and uploads are
captured without application writes, then restarted. Environment variables
BACKUP_DIR and BACKUP_RETENTION_DAYS provide the same defaults as the options.
EOF
}

while (($#)); do
  case "$1" in
    --output)
      [[ $# -ge 2 ]] || { echo "Missing value for --output" >&2; exit 2; }
      BACKUP_ROOT="$2"
      shift 2
      ;;
    --retention)
      [[ $# -ge 2 ]] || { echo "Missing value for --retention" >&2; exit 2; }
      RETENTION_DAYS="$2"
      shift 2
      ;;
    --production)
      COMPOSE_ARGS+=(-f "$ROOT_DIR/docker-compose.production.yml")
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || {
  echo "Retention must be a non-negative whole number" >&2
  exit 2
}

command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }
command -v sha256sum >/dev/null || { echo "sha256sum is required" >&2; exit 1; }

umask 077
mkdir -p "$BACKUP_ROOT"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
final_dir="$BACKUP_ROOT/relay-$timestamp"
temp_dir="$(mktemp -d "$BACKUP_ROOT/.relay-$timestamp.XXXXXX")"

cleanup() {
  rm -rf -- "$temp_dir"
}

compose=(docker compose "${COMPOSE_ARGS[@]}")
backend_was_running=false
if [[ "$("${compose[@]}" ps --status running --quiet backend)" != "" ]]; then
  backend_was_running=true
fi

finish() {
  cleanup
  if [[ "$backend_was_running" == true ]]; then
    "${compose[@]}" start backend >/dev/null || true
  fi
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "$backend_was_running" == true ]]; then
  "${compose[@]}" stop backend >/dev/null
fi

"${compose[@]}" exec -T postgres sh -eu -c '
  exec pg_dump \
    --format=custom \
    --compress=9 \
    --create \
    --no-owner \
    --no-privileges \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB"
' >"$temp_dir/database.dump"

"${compose[@]}" run --rm --no-deps -T --entrypoint sh backend -eu -c '
  cd /app/uploads
  exec tar -czf - .
' >"$temp_dir/uploads.tar.gz"

(
  cd "$temp_dir"
  sha256sum database.dump uploads.tar.gz >SHA256SUMS
)

cat >"$temp_dir/manifest.txt" <<EOF
format_version=1
created_at=$timestamp
database_format=postgresql-custom
uploads_format=tar-gzip
compose_project=${COMPOSE_PROJECT_NAME:-$(basename "$ROOT_DIR")}
EOF

chmod 600 "$temp_dir"/*
mv -T -- "$temp_dir" "$final_dir"
if [[ "$backend_was_running" == true ]]; then
  "${compose[@]}" start backend >/dev/null
  backend_was_running=false
fi
trap - EXIT INT TERM

if ((RETENTION_DAYS > 0)); then
  find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d \
    -name 'relay-*' -mtime "+$RETENTION_DAYS" -exec rm -rf -- {} +
fi

echo "Backup created: $final_dir"
