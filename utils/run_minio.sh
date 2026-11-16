#!/usr/bin/env bash
# Local MinIO launcher: reads S3_ACCESS_KEY and S3_SECRET_KEY from .env
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
[ -f "$ENV_FILE" ] || { echo ".env not found: $ENV_FILE" >&2; exit 1; }

get_var() {
  grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2- | tr -d '\r' \
    | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

S3_ACCESS_KEY="$(get_var S3_ACCESS_KEY || true)"
S3_SECRET_KEY="$(get_var S3_SECRET_KEY || true)"
[ -n "$S3_ACCESS_KEY" ] || { echo "S3_ACCESS_KEY is not set in .env" >&2; exit 1; }
[ -n "$S3_SECRET_KEY" ] || { echo "S3_SECRET_KEY is not set in .env" >&2; exit 1; }

export MINIO_ROOT_USER="$S3_ACCESS_KEY"
export MINIO_ROOT_PASSWORD="$S3_SECRET_KEY"

DATA_DIR="$ROOT/storage/minio"
mkdir -p "$DATA_DIR"

MINIO_BIN="$(command -v minio || echo "$HOME/go/bin/minio")"
[ -x "$MINIO_BIN" ] || { echo "minio not found: $MINIO_BIN" >&2; exit 1; }

exec "$MINIO_BIN" server "$DATA_DIR" --address 127.0.0.1:9000 --console-address 127.0.0.1:9001