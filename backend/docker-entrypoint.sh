#!/bin/sh
set -eu

upload_dir="${UPLOAD_DIR:-/app/uploads}"
mkdir -p "$upload_dir"
chown -R relay:relay "$upload_dir"

exec gosu relay "$@"
