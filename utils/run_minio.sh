#!/usr/bin/env bash
# Local MinIO launcher: reads S3_MINIO_* settings from .env
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
[ -f "$ENV_FILE" ] || { echo ".env not found: $ENV_FILE" >&2; exit 1; }

get_var() {
  grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2- | tr -d '\r' \
    | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

for name in S3_MINIO_PORT S3_MINIO_CONSOLE_PORT S3_MINIO_ACCESS_KEY S3_MINIO_SECRET_KEY; do
  value="$(get_var "$name" || true)"
  [ -n "$value" ] || { echo "$name is not set in .env" >&2; exit 1; }
  printf -v "$name" '%s' "$value"
done

export MINIO_ROOT_USER="$S3_MINIO_ACCESS_KEY"
export MINIO_ROOT_PASSWORD="$S3_MINIO_SECRET_KEY"

DATA_DIR="$ROOT/storage/minio"
mkdir -p "$DATA_DIR"

MINIO_BIN="$(command -v minio || echo "$HOME/go/bin/minio")"
[ -x "$MINIO_BIN" ] || { echo "minio not found: $MINIO_BIN" >&2; exit 1; }

echo "MinIO: S3 http://127.0.0.1:$S3_MINIO_PORT, console http://127.0.0.1:$S3_MINIO_CONSOLE_PORT"
exec "$MINIO_BIN" server "$DATA_DIR" --address "127.0.0.1:$S3_MINIO_PORT" --console-address "127.0.0.1:$S3_MINIO_CONSOLE_PORT"
